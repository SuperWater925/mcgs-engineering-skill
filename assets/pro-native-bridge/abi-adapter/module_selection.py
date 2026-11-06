"""Choose current on-disk PE modules without loading vendor code.

Selection is evidence for ABI preparation, not proof of Windows loader search
order or ABI compatibility. Runtime must still verify the actually loaded
module's identity. Explicit alias=path mappings handle renamed components;
no vendor libraries are copied or installed by this module.
"""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
import re
import stat
from collections import deque

from pe32 import PE32
from preparation_progress import PreparationProgress


def parse_module_overrides(values, known_aliases=None):
    """Parse repeated CLI alias=absolute-path values, rejecting duplicate aliases."""
    result = {}
    for value in values or ():
        if not isinstance(value, str) or '=' not in value:
            raise ValueError('Module mapping requires alias=absolute-path')
        alias, name = value.split('=', 1)
        if not alias or alias in result or not name or '\0' in alias + name:
            raise ValueError('Empty or duplicate module mapping: ' + alias)
        if known_aliases is not None and alias not in known_aliases:
            raise ValueError('Unknown logical module alias: ' + alias)
        path = Path(name)
        if not path.is_absolute():
            raise ValueError('Module mapping requires an absolute path: ' + alias)
        result[alias] = path
    return result


def _regular_image(path, *, editor=False):
    # Bind the actual target of a legitimate symlink/junction. The selected
    # bytes and the loaded module are still checked against this identity.
    path = Path(path).resolve(strict=True)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Module is not a regular file')
    image = PE32(path)
    if editor and image.is_dll:
        raise ValueError('The selected editor must be an EXE, not a DLL')
    if not editor and not image.is_dll:
        raise ValueError('The selected dependency must be a PE32/I386 DLL')
    return path, image


class _PreparationImages:
    """Reuse parsing only within one selection while file identities stay fixed.

    No cached observation is carried to a later invocation or used to admit a
    vendor build. A replacement during this invocation remains an explicit
    unavailable-file result instead of mixing two versions of a dependency.
    """
    def __init__(self, progress_callback=None):
        self.rows = {}
        self.hits = 0
        self.parses = 0
        self.progress = PreparationProgress(progress_callback)

    @staticmethod
    def identity(path):
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Module is not a regular file')
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def load(self, path, *, editor=False):
        path = Path(path).resolve(strict=True)
        identity = self.identity(path)
        key = os.path.normcase(str(path))
        cached = self.rows.get(key)
        if cached is not None:
            if cached[0] != identity:
                raise ValueError('Module file identity changed during this preparation: ' + str(path))
            image = cached[1]
            self.hits += 1
        else:
            image = PE32(path)
            if self.identity(path) != identity:
                raise ValueError('Module file identity changed while parsing: ' + str(path))
            self.rows[key] = (identity, image)
            self.parses += 1
        if editor and image.is_dll:
            raise ValueError('The selected editor must be an EXE, not a DLL')
        if not editor and not image.is_dll:
            raise ValueError('The selected dependency must be a PE32/I386 DLL')
        self.progress('module_discovery', self.parses, None,
                      image_cache_hits=self.hits, current_module=path.name)
        return path, image


def _family(name):
    name = name.casefold()
    if re.fullmatch(r'mfc\d+u?d?\.dll', name):
        return 'mfc'
    match = re.fullmatch(r'(msvcr|msvcp|vcruntime|ucrtbase)(?:\d+(?:_\d+)?)?d?\.dll', name)
    if match:
        return match[1]
    match = re.fullmatch(r'qt\d+([a-z][a-z0-9]*?)d?\.dll', name)
    if match:
        return 'qt:' + match[1]
    return None


def _import_names(alias, reference, imported):
    basename = reference.get('basename', '')
    family = _family(basename) or ('mfc' if alias == 'mfc' else None)
    # A different runtime family (e.g. MSVCR -> VCRUNTIME+UCRT) is not guessed:
    # one legacy module may have split into several modules. Map it explicitly.
    matches = [name for name in imported if name.casefold() == basename.casefold()
               or family is not None and _family(name) == family]
    return list(dict.fromkeys(matches))


def _dependency_imports(editor, image, roots, install, *, image_loader=None):
    """Inspect the local import graph before considering reference fallbacks."""
    pending = deque([(editor, image)])
    seen = {os.path.normcase(str(editor))}
    names, rows, name_keys = [], [], set()
    while pending:
        importer, current = pending.popleft()
        forwarded = []
        for exported in current.exports_by_ordinal.values():
            value = exported.get('forwarder')
            if value and '.' in value:
                module = value.rsplit('.', 1)[0]
                forwarded.append(module if module.casefold().endswith('.dll') else module + '.dll')
        for name in dict.fromkeys([*current.import_modules, *forwarded]):
            if name.casefold() not in name_keys:
                names.append(name)
                name_keys.add(name.casefold())
            # Never interpret an import string as an arbitrary filesystem path.
            if PureWindowsPath(name).name != name or name in ('.', '..'):
                rows.append({'importer': str(importer), 'name': name, 'status': 'non-basename-import'})
                continue
            search = list(dict.fromkeys((importer.parent, *roots)))
            path = next((root/name for root in search if os.path.lexists(root/name)), None)
            if path is None:
                continue
            path = Path(path).resolve()
            key = os.path.normcase(str(path))
            if key in seen:
                continue
            seen.add(key)
            try:
                path, dependency = (image_loader or _regular_image)(path)
                rows.append({'importer': str(importer), 'name': name, 'path': str(path), 'status': 'read'})
                # Cycle detection bounds traversal by the finite actual graph,
                # including explicit dependencies outside the installation.
                pending.append((path, dependency))
            except (OSError, ValueError) as error:
                rows.append({'importer': str(importer), 'name': name, 'path': str(path), 'status': 'unavailable', 'error': str(error)})
    return names, rows


def select_module_files(catalog, layout, module_overrides=None, *, progress_callback=None):
    """Return valid files plus per-alias unavailable/ambiguity diagnostics.

    The explicitly bound editor is mandatory. Optional dependencies never abort
    unrelated preparation because of absent/unreadable/wrong-architecture bytes.
    A present highest-priority candidate that is invalid stays unavailable;
    silently substituting an older installation copy would attest the wrong DLL.
    """
    references = catalog['reference_modules']
    overrides = (parse_module_overrides(module_overrides, references)
                 if not isinstance(module_overrides, dict) else dict(module_overrides))
    unknown = set(overrides) - set(references)
    if unknown:
        raise ValueError('Unknown logical module aliases: ' + ', '.join(sorted(unknown)))
    for alias, path in overrides.items():
        if not Path(path).is_absolute() or '\0' in str(path):
            raise ValueError('Module mapping requires an absolute path: ' + alias)
    editor = Path(layout.editor_executable or Path(layout.install_root) / 'Program' / 'McgsSetPro.exe')
    if 'editor' in overrides and os.path.normcase(os.path.abspath(overrides['editor'])) != os.path.normcase(os.path.abspath(editor)):
        raise ValueError('Editor override must equal the explicitly bound editor executable')
    images = _PreparationImages(progress_callback)
    images.progress('module_discovery', 0, None, force=True)
    editor, image = images.load(editor, editor=True)
    install = Path(os.path.abspath(layout.install_root))
    roots = list(dict.fromkeys((editor.parent, install, install / 'Program')))
    local_roots = tuple(roots)
    windows = os.environ.get('WINDIR')
    if windows:
        # x86 System32 redirects on 64-bit Windows; SysWOW64 is explicit first.
        roots.extend(root for root in (Path(windows) / 'SysWOW64', Path(windows) / 'System32') if root not in roots)
    # PATH supplies additional explicit loader search directories; it is still
    # candidate evidence, never proof that Windows selected a particular file.
    for item in os.environ.get('PATH', '').split(os.pathsep):
        path = Path(item.strip('"'))
        if path.is_absolute() and path.is_dir() and path not in roots:
            roots.append(path.resolve())
    files = {'editor': editor}
    rows = {'editor': {'status': 'selected', 'source': 'bound-editor', 'path': str(editor),
                       'sha256': image.identity()['sha256'], 'candidates': []}}
    base_images = {editor: image}
    # Explicit mappings are discovery roots even when they rename a runtime or
    # a dynamically loaded plugin. Invalid optional mappings remain isolated.
    for alias, path in overrides.items():
        if alias == 'editor':
            continue
        try:
            path, dependency = images.load(path)
            base_images[path] = dependency
        except (OSError, ValueError):
            # Its per-alias row below records the exact invalid candidate.
            pass

    def collect_imports(seed_images):
        names, evidence = [], []
        for path, dependency in seed_images.items():
            found, graph = _dependency_imports(path, dependency, roots, install, image_loader=images.load)
            names.extend(name for name in found if name.casefold() not in {item.casefold() for item in names})
            evidence.extend(graph)
        return names, evidence

    def graph_identity(names, evidence):
        return (frozenset(name.casefold() for name in names),
                frozenset((row.get('importer'), row.get('name', '').casefold(), row.get('path'), row.get('status')) for row in evidence))

    imported, dependency_rows = collect_imports(base_images)
    aliases = sorted(alias for alias in references if alias != 'editor')
    runtime_aliases = {alias for alias in aliases if alias == 'mfc' or _family(references[alias].get('basename', '')) is not None}
    blocked_dynamic = set()
    history = {}
    root_history = []
    discovery_passes = 0
    # Discover catalogued dynamic components before committing runtime/library
    # aliases. MFC/CRT/Qt fallbacks are hypotheses, never independent import roots:
    # an old provisional MFC must not keep its old CRT alive after replacement.
    # Rebuild from current roots each pass so retired paths leave no evidence.
    while True:
        discovery_passes += 1
        selected_images = {}
        current_graph = graph_identity(imported, dependency_rows)
        for alias in aliases:
            files.pop(alias, None)
            if alias in blocked_dynamic:
                rows[alias] = {'status': 'unavailable', 'candidates': [],
                               'reason': 'Dynamic dependency discovery cycles between conflicting module paths; supply an explicit alias=path mapping'}
                continue
            reference = references[alias]
            candidates = []
            def add(path, source, rank):
                path = Path(os.path.abspath(path))
                if all(os.path.normcase(str(row['path'])) != os.path.normcase(str(path)) for row in candidates):
                    candidates.append({'path': str(path), 'source': source, 'rank': rank})
            if alias in overrides:
                add(overrides[alias], 'explicit-map', 0)
            else:
                # Reference importers identify a module's logical role. Avoid
                # flattening an unrelated plugin's different CRT into the
                # central runtime role when its actual importer is available.
                importer_roles = {item['module'] for item in catalog.get('import_slots', ())
                                  if item.get('target_module') == alias}
                role_names, role_paths = [], []
                for owner in sorted(importer_roles):
                    owner_path = files.get(owner)
                    if owner_path is None:
                        continue
                    try:
                        owner_image = base_images.get(owner_path) or images.load(owner_path, editor=owner == 'editor')[1]
                    except (OSError, ValueError):
                        continue
                    matched = _import_names(alias, reference, owner_image.import_modules)
                    role_names.extend(matched)
                    for name in matched:
                        if PureWindowsPath(name).name == name:
                            adjacent = Path(owner_path).parent / name
                            if adjacent.is_file():
                                role_paths.append(adjacent)
                names = list(dict.fromkeys(role_names)) or _import_names(alias, reference, imported)
                for path in role_paths:
                    add(path, 'logical-importer-adjacent', 5)
                basename = reference.get('basename')
                for index, root in enumerate(roots):
                    for name in names:
                        # A system-wide runtime is a later fallback than the
                        # dependency actually found beside its importing plugin.
                        rank = 10 + index if root in local_roots else 25 + index
                        add(root / name, 'actual-import', rank)
                imported_names = {name.casefold() for name in names}
                for dependency in dependency_rows:
                    if dependency.get('name', '').casefold() in imported_names and dependency.get('path'):
                        add(dependency['path'], 'actual-import-adjacent', 20)
                # Actual EXE-adjacent exact names also precede reference layout.
                if basename:
                    add(editor.parent / basename, 'editor-adjacent', 30)
                declared = reference.get('install_relative_path')
                relative = PureWindowsPath(declared) if isinstance(declared, str) else None
                if relative and not relative.is_absolute() and '..' not in relative.parts:
                    add(install / Path(*relative.parts), 'reference-layout-fallback', 40)
                if basename:
                    for index, root in enumerate(roots[1:]):
                        add(root / basename, 'basename-fallback', 50 + index)
                    try:
                        found = sorted((p for p in install.rglob('*') if p.name.casefold() == basename.casefold()), key=lambda p: str(p).casefold())
                        for path in found:
                            add(path, 'recursive-basename-fallback', 60)
                    except OSError as error:
                        candidates.append({'source': 'recursive-search', 'status': 'unreadable', 'error': str(error), 'rank': 99})
            present = []
            for candidate in candidates:
                if 'path' not in candidate:
                    continue
                try:
                    candidate['status'] = 'present' if os.path.lexists(candidate['path']) else 'absent'
                except OSError as error:
                    candidate.update(status='unreadable', error=str(error))
                if candidate['status'] != 'absent':
                    present.append(candidate)
            row = {'status': 'unavailable', 'candidates': candidates}
            if present:
                best = min(candidate['rank'] for candidate in present)
                chosen = [candidate for candidate in present if candidate['rank'] == best]
                # Several directory aliases/equal copies are interchangeable
                # on disk; runtime still requires one loaded content owner.
                if len(chosen) > 1:
                    equal = []
                    for candidate in chosen:
                        try:
                            path, candidate_image = images.load(candidate['path'])
                            equal.append((path, candidate_image.identity()['sha256']))
                        except (OSError, ValueError):
                            equal = []
                            break
                    if equal and len({sha for _, sha in equal}) == 1:
                        chosen = [chosen[0]]
                        row['equivalent_candidate_paths'] = [str(path) for path, _ in equal]
                if len(chosen) != 1:
                    row['reason'] = 'Several equally preferred module candidates; supply an explicit alias=path mapping'
                    row['ambiguity'] = [candidate['path'] for candidate in chosen]
                else:
                    candidate = chosen[0]
                    try:
                        path, selected = images.load(candidate['path'])
                        files[alias] = path
                        selected_images[alias] = selected
                        row.update(status='selected', source=candidate['source'], path=str(path), sha256=selected.identity()['sha256'])
                        candidate['status'] = 'selected'
                    except (OSError, ValueError) as error:
                        candidate.update(status='invalid', error=str(error))
                        row['reason'] = 'Preferred module is unavailable: ' + str(error)
            else:
                row['reason'] = 'No current module file was found; explicit alias=path mapping is supported'
            rows[alias] = row
        discovery_roots = {alias: files[alias] for alias in aliases
                           if alias in files and alias not in runtime_aliases and alias not in overrides}
        seed_images = dict(base_images)
        seed_images.update((path, selected_images[alias]) for alias, path in discovery_roots.items())
        next_imported, next_rows = collect_imports(seed_images)
        next_graph = graph_identity(next_imported, next_rows)
        if next_graph == current_graph:
            break
        state = (next_graph, tuple(sorted((alias, str(path)) for alias, path in discovery_roots.items())))
        if state in history:
            # A self-referential dynamic import may alternate its root path.
            # Isolate only varying dynamic aliases; retain unrelated modules.
            cycle = root_history[history[state]:] + [dict(discovery_roots)]
            cycle_aliases = {alias for roots_state in cycle for alias in roots_state}
            varying = {alias for alias in cycle_aliases if len({roots_state.get(alias) for roots_state in cycle}) > 1}
            blocked_dynamic.update(varying or discovery_roots)
            history.clear()
            root_history.clear()
        else:
            history[state] = len(root_history)
            root_history.append(dict(discovery_roots))
        imported, dependency_rows = next_imported, next_rows
    # Keep non-catalogued terminal libraries as explicit PE owners for forwarder
    # proof. They do not acquire old profile layouts or new callable adapters.
    selected_paths = {os.path.normcase(str(Path(path).resolve())) for path in files.values()}
    for dependency in dependency_rows:
        if dependency.get('status') != 'read' or not dependency.get('path'):
            continue
        path = Path(dependency['path']).resolve()
        if os.path.normcase(str(path)) in selected_paths:
            continue
        alias = 'dependency:' + str(path).casefold()
        files[alias] = path
        selected_paths.add(os.path.normcase(str(path)))
    images.progress('module_discovery_complete', images.parses, images.parses, force=True,
                    image_cache_hits=images.hits)
    return {'files': files, 'report': {'schema': 'mcgs-native-module-selection/v1', 'modules': rows,
                                     'preparation_image_cache': {'unique_files_parsed': images.parses, 'cache_hits': images.hits,
                                                                 'scope': 'single_selection_stable_file_identity'},
                                     'dependency_imports': dependency_rows,
                                     'dependency_discovery_passes': discovery_passes,
                                     'dependency_roots': [{'alias': alias, 'path': str(path)} for alias, path in sorted(discovery_roots.items())],
                                     'loaded_target_identity_check_required': True,
                                     'vendor_files_copied': False, 'vendor_whole_file_sha_admission': False}}
