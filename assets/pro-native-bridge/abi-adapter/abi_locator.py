"""Prepare current-PE function/RTTI locations without starting the application.

The shipped catalog has sparse published guard fragments and RTTI metadata, not
vendor sections or local paths. SHA values identify observations/configurations;
vendor SHA equality is never required as an admission condition for a new PE.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import struct
import sys

sys.dont_write_bytecode = True
from pe32 import PE32, resolve_export
import rtti
import x86_signature as xs
from preparation_progress import PreparationProgress

CATALOG_SCHEMA = 'mcgs-native-reference-catalog/v1'
RESULT_SCHEMA = 'mcgs-native-abi-adaptation/v1'
ATTESTATION_SCHEMA = 'mcgs-native-resolved-profiles/v1'
DEFAULT_CATALOG = Path(__file__).resolve().parent / 'catalogs/reference.json.gz'
PROFILE_FIELD_MODULES = Path(__file__).resolve().parent / 'catalogs/profile-field-modules.json'
BYTE_KEYS = ('expected_first_32_bytes', 'expected_first32', 'first32', 'bytes', 'expected_bytes', 'code_bytes', 'bytes_hex')
RELOC_KEYS = ('relocatable_dword_offsets_in_first32', 'relocation_offsets', 'reloc_offsets', 'relocations', 'highlow_offsets')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError('Not an RVA integer')
    return int(value, 0) if isinstance(value, str) else int(value)


def pointer(parts):
    return '/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in parts) if parts else ''


def unpointer(value):
    return [p.replace('~1', '/').replace('~0', '~') for p in value.strip('/').split('/')] if value else []


def get_at(document, path):
    value = document
    for key in unpointer(path):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def set_at(document, path, value):
    parts = unpointer(path)
    owner = document
    for key in parts[:-1]:
        owner = owner[int(key)] if isinstance(owner, list) else owner[key]
    key = int(parts[-1]) if isinstance(owner, list) else parts[-1]
    owner[key] = value


def _format_number(original, actual):
    if isinstance(original, str):
        return hex(actual) if original.lower().startswith('0x') else str(actual)
    return actual


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def load_catalog(file):
    """Read plain or gzip storage without changing the expanded catalog data.

    Result/attestation catalog_sha256 retains the existing expanded canonical
    JSON meaning. The compressed storage digest belongs to package metadata.
    """
    path = Path(file)
    raw = path.read_bytes()
    if path.suffix.lower() == '.gz' or raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    document = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(document, dict) or document.get('schema') != CATALOG_SCHEMA:
        raise ValueError('Unsupported reference catalog schema')
    return document


def write_catalog(file, document):
    """Write deterministic gzip when requested; plain JSON remains supported."""
    path = Path(file)
    raw = _json_bytes(document)
    if path.suffix.lower() == '.gz':
        raw = gzip.compress(raw, compresslevel=9, mtime=0)
    path.write_bytes(raw)


def _walk(value, path=(), inherited='editor', modules=None):
    if isinstance(value, dict):
        if modules is not None:
            inherited = _hint(value, inherited, modules)
        yield path, value, inherited
        for key, child in value.items():
            hint = str(key).lower() if str(key).lower() in ('mfc', 'common', 'editor', 'driver') else inherited
            yield from _walk(child, path + (key,), hint, modules)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, path + (index,), inherited, modules)


def _modules(paths):
    return {str(alias).lower(): PE32(Path(path)) for alias, path in paths.items()}


def _module_alias(value, modules):
    if not isinstance(value, str):
        return None
    item = value.lower()
    if item in modules:
        return item
    if item in ('exe', 'mcgs', 'main', 'mcgssetpro', 'mcgssetpro.exe') and 'editor' in modules:
        return 'editor'
    base = PureWindowsPath(value).name.lower()
    found = [alias for alias, pe in modules.items() if pe.path and pe.path.name.lower() == base]
    return found[0] if len(found) == 1 else None


def _hint(row, inherited, modules):
    for key in ('module', 'module_name', 'file', 'binary', 'path', 'relative_file'):
        found = _module_alias(row.get(key), modules)
        if found:
            return found
    return inherited if inherited in modules else None


def discover_reference_modules(reference_modules, profile_root):
    """Resolve declared PE dependencies from the selected installation, read only.

    Logical driver-ui inherits its containing driver record's exact path.  A
    root driver_path is merely a dependency declaration, never the owner of
    unrelated editor object addresses.  Nothing in the public catalog retains
    an author's absolute path.
    """
    paths = {str(k).lower(): Path(v).resolve() for k, v in reference_modules.items()}
    editor = paths.get('editor')
    install = editor.parent.parent if editor and editor.parent.name.lower() == 'program' else None
    program = editor.parent if editor else None
    declarations, gaps = {}, []
    for file in sorted(Path(profile_root).rglob('*.json')):
        try:
            document = json.loads(file.read_text('utf-8-sig'))
        except (ValueError, UnicodeError):
            continue
        relative = file.relative_to(profile_root).as_posix()
        for parts, row, _ in _walk(document):
            for key in ('module', 'module_name', 'file', 'binary', 'path', 'driver_path', 'relative_file'):
                value = row.get(key)
                if not isinstance(value, str) or PureWindowsPath(value).suffix.lower() not in ('.exe', '.dll', '.ui'):
                    continue
                name = PureWindowsPath(value).name
                declarations.setdefault(name.lower(), []).append((value, relative, pointer(parts + (key,))))
    existing_names = {p.name.lower(): alias for alias, p in paths.items()}
    for base, rows in declarations.items():
        if base in existing_names:
            continue
        candidates = set()
        for declared, _, _ in rows:
            parts = PureWindowsPath(declared).parts
            program_at = next((i for i, p in enumerate(parts) if p.lower() == 'program'), None)
            if install and program_at is not None:
                candidate = install.joinpath(*parts[program_at:])
                if candidate.is_file():
                    candidates.add(candidate.resolve())
        # Exact installation-relative declarations take priority over basename
        # fallback; similarly named driver plugins must not be arbitrarily used.
        if not candidates and program:
            candidates.update(p.resolve() for p in program.iterdir() if p.is_file() and p.name.lower() == base)
        if not candidates and install:
            candidates.update(p.resolve() for p in install.rglob('*') if p.is_file() and p.name.lower() == base)
        if len(candidates) != 1:
            gaps.append({'kind': 'reference_module_dependency', 'basename': base,
                'reason': 'Declared module not found in selected installation' if not candidates else 'More than one installation module has the declared basename',
                'declarations': [{'profile': r, 'json_pointer': p} for _, r, p in rows]})
            continue
        candidate = next(iter(candidates))
        try:
            PE32(candidate)
        except ValueError as exc:
            gaps.append({'kind': 'reference_module_dependency', 'basename': base,
                'reason': 'Declared dependency is not a usable PE32/I386 image: ' + str(exc)})
            continue
        paths[base] = candidate;existing_names[base] = base
    identities = {}
    for alias, file in paths.items():
        if install and file.is_relative_to(install):
            identities[alias] = {'install_relative_path': file.relative_to(install).as_posix()}
        else:
            identities[alias] = {}
    return paths, identities, gaps


def _hex_bytes(value):
    if not isinstance(value, str):
        return None
    value = ''.join(value.split())
    if not value or len(value) % 2 or not re.fullmatch('[0-9a-fA-F]+', value):
        return None
    return bytes.fromhex(value)


def _virtual_zero_span(pe, address, length):
    try:
        section = pe.section_for_rva(address)
        offset = address - section.rva
        return section.raw_size <= offset and offset + length <= section.virtual_size
    except ValueError:
        return False


def semantic_address_fields(row, path=()):
    """Explicit native-consumer address shapes beyond *_rva names.

    Slot dictionary keys remain indexes. Values are RVAs only in a declared
    table/method contract; arbitrary numeric arrays, IDs and offsets are never
    inferred to be addresses. Preferred-VA fields keep the reference-base
    encoding used by their consumers, independently of guard rebasing.
    """
    table = any(key in row for key in ('vtable_rva', 'primary_vtable_rva')) or (
        'rva' in row and (any(key in row for key in ('col_rva', 'rtti', 'slot_entry_rvas')) or
                          path and str(path[-1]) in ('table', 'drawing_view')))
    for key in ('entries', 'slots', 'vtable_entries'):
        if table and isinstance(row.get(key), list):
            for index, value in enumerate(row[key]):
                if not isinstance(value, (dict, list)) and value is not None:
                    yield (key, index), value, 'virtual-slot', None
    # Some native profiles use singular *_rva for a declared array. These are
    # slot/branch targets, not the slot-index keys or object-field offsets.
    for key in ('entries_rva', 'slots_rva', 'vtable_entries_rva', 'targets_rva'):
        if isinstance(row.get(key), list):
            for index, value in enumerate(row[key]):
                if not isinstance(value, (dict, list)) and value is not None:
                    yield (key, index), value, 'function' if key == 'targets_rva' else 'virtual-slot', None
    if 'picture_preload_vtable_rva' in row and isinstance(row.get('picture_preload_entries'), list):
        for index, value in enumerate(row['picture_preload_entries']):
            if value is not None:
                yield ('picture_preload_entries', index), value, 'virtual-slot', None
    if path and str(path[-1]) in ('methods', 'slots', 'metadata_slots'):
        kind = 'function' if path[-1] == 'methods' else 'virtual-slot'
        for key, value in row.items():
            if not isinstance(value, (dict, list)) and value is not None:
                yield (key,), value, kind, None
    if 'runtime_class_rva' in row and 'factory_name' in row:
        for key in ('primary', 'iobject'):
            if key in row and not isinstance(row[key], (dict, list)):
                yield (key,), row[key], 'vtable', None
    if 'entry_va' in row and 'slot' in row and 'object_tables' in path:
        yield ('entry_va',), row['entry_va'], 'virtual-slot', 'reference-preferred-VA'
    if table and isinstance(row.get('col_fields'), list):
        for index in (3, 4):
            if index < len(row['col_fields']):
                yield ('col_fields', index), row['col_fields'][index], 'RTTI-pointer', 'reference-preferred-VA'


def _signature_imports(model):
    for relocation in model.get('relocations', []):
        if relocation.get('import'):
            yield relocation['import']
    for transfer in model.get('transfers', []):
        for part in transfer.get('target_signature_chain', []):
            yield from _signature_imports(part)


def create_catalog(reference_modules, profile_root, *, explicit_fields=None):
    """Extract sparse guard and RTTI catalogs from the published profile files.

    explicit_fields optionally supplies classified source functions:
      {module,reference_rva,kind:'function',length:32,name}
    or a profile field {profile,json_pointer,module,kind,reference_rva}.
    No generic Number()/object-offset rewrite is performed.
    """
    root = Path(profile_root).resolve()
    if not root.is_dir():
        raise ValueError('Existing reference profile directory required')
    reference_modules, module_metadata, dependency_gaps = discover_reference_modules(reference_modules, root)
    modules = _modules(reference_modules)
    profiles, signatures, types, gaps, explicit_addresses = [], {}, {}, list(dependency_gaps), []
    import_slots = {}
    owner_document = json.loads(PROFILE_FIELD_MODULES.read_text('utf-8')) if PROFILE_FIELD_MODULES.is_file() else {'entries': []}
    declared_field_owners = {(r['profile'], r['json_pointer']): r for r in owner_document['entries']}
    table_owner_cache = {}

    def table_owner(address, preferred):
        if address not in table_owner_cache:
            owners = []
            for candidate, pe in modules.items():
                try:
                    rtti.describe_vtable(pe, address, 1);owners.append(candidate)
                except (ValueError, IndexError):
                    pass
            table_owner_cache[address] = owners
        owners = table_owner_cache[address]
        return preferred if preferred in owners else owners[0] if len(owners) == 1 else preferred

    def add_signature(alias, rva, length, name, origin):
        key = f'{alias}:0x{rva:x}:{length}'
        if key not in signatures:
            try:
                # Sparse instruction context distinguishes common MSVC EH
                # prologues. The regenerated guard still has its original span.
                pe = modules[alias]
                section = pe.section_for_rva(rva)
                match_span = min(max(length, 96), section.raw_size - (rva - section.rva))
                model = xs.attach_reference_contexts(pe, xs.decode_signature(pe, rva, match_span))
                model['guard_length'] = length
                model.update(id=key, module=alias, names=[], origins=[], exports=[name for name, entry in modules[alias].exports.items()
                    if entry['rva'] == rva and not entry.get('forwarder') and not name.startswith('#')])
                signatures[key] = model
            except (ValueError, IndexError) as exc:
                gaps.append({'kind': 'reference_signature', 'module': alias, 'reference_rva': rva, 'reason': str(exc), 'origin': origin})
                return None
        if name and name not in signatures[key]['names']:
            signatures[key]['names'].append(name)
        if origin not in signatures[key]['origins']:
            signatures[key]['origins'].append(origin)
        return key

    def add_table(alias, table, count, origin, *, report_gap=True):
        key = f'{alias}:vtable:0x{table:x}'
        if key not in types:
            try:
                model = rtti.describe_vtable(modules[alias], table, count)
                types[key] = {'id': key, 'module': alias, 'reference': model, 'origins': []}
                for index, target in enumerate(model['slot_entry_rvas']):
                    add_signature(alias, target, 32, model['decorated_name'] + f'/slot{index}', 'rtti-slot:' + key)
            except (ValueError, IndexError) as exc:
                if report_gap:
                    gaps.append({'kind': 'reference_RTTI', 'module': alias, 'reference_rva': table, 'reason': str(exc), 'origin': origin})
                return
        if origin not in types[key]['origins']:
            types[key]['origins'].append(origin)

    for file in sorted(root.rglob('*.json')):
        relative = file.relative_to(root).as_posix()
        raw = file.read_bytes()
        try:
            document = json.loads(raw.decode('utf-8-sig'))
        except (ValueError, UnicodeError):
            continue
        if not isinstance(document, dict):
            continue
        item = {'relative_path': relative, 'reference_sha256': digest(raw), 'fields': [], 'guards': [], 'raw_guards': [], 'virtual_guards': [], 'exports': [], 'entry_paths': [], 'pe_metadata_fields': [], 'reference_gaps': []}
        row_hints, field_hints = {}, {}
        for path, row, inherited in _walk(document, modules=modules):
            alias = _hint(row, inherited, modules)
            if alias:
                row_hints[pointer(path) if path else ''] = alias
            # Code byte guards are validated against the actual reference PE,
            # not accepted because its whole-file SHA matches a sample.
            if 'rva' in row:
                try:
                    rva = number(row['rva'])
                except (ValueError, TypeError):
                    rva = None
                byte_key = next((key for key in BYTE_KEYS if _hex_bytes(row.get(key)) is not None), None)
                if rva is not None and byte_key:
                    data = _hex_bytes(row[byte_key])
                    matches, data_matches = [], []
                    for candidate, pe in modules.items():
                        try:
                            if pe.read(rva, len(data)) == data:
                                (matches if pe.is_executable(rva) else data_matches).append(candidate)
                        except ValueError:
                            pass
                    if alias in matches:
                        matches = [alias]
                    if len(matches) == 1:
                        alias = matches[0];row_hints[pointer(path) if path else ''] = alias
                        guard = add_signature(alias, rva, len(data), str(row.get('name', path[-1] if path else relative)), relative + pointer(path))
                        if guard:
                            item['guards'].append({'json_pointer': pointer(path), 'byte_key': byte_key,
                                'relocation_keys': [key for key in RELOC_KEYS if key in row and isinstance(row[key], list) and all(isinstance(v, int) for v in row[key])],
                                'guard_id': guard, 'module': alias, 'reference_rva': rva})
                    elif data_matches and (alias in data_matches or len(data_matches) == 1):
                        alias = alias if alias in data_matches else data_matches[0]
                        row_hints[pointer(path) if path else ''] = alias
                        item['raw_guards'].append({'json_pointer': pointer(path), 'byte_key': byte_key, 'module': alias,
                            'reference_rva': rva, 'length': len(data), 'guard_kind': 'PE-data',
                            'relocation_keys': [key for key in RELOC_KEYS if key in row and isinstance(row[key], list) and all(isinstance(v, int) for v in row[key])]})
                    elif alias and row.get('initial_value_source', {}).get('runtime_exact_zero_required') is True and not any(data) and _virtual_zero_span(modules[alias], rva, len(data)):
                        item['virtual_guards'].append({'json_pointer': pointer(path), 'byte_key': byte_key, 'module': alias,
                            'reference_rva': rva, 'length': len(data), 'guard_kind': 'loader-zero-initialized-virtual-data',
                            'runtime_exact_zero_required': True, 'bytes_were_not_read_from_file': True})
                    else:
                        gap = {'kind': 'reference_guard', 'profile': relative, 'json_pointer': pointer(path + (byte_key,)),
                            'reason': 'Published byte fragment has no unique matching supplied reference module', 'candidate_modules': matches}
                        gaps.append(gap);item['reference_gaps'].append(gap)
            if alias:
                for key in ('vtable_rva', 'primary_vtable_rva', 'object_vtable_rva'):
                    if key in row:
                        try:
                            address = number(row[key]);owner = table_owner(address, alias)
                            field_hints[pointer(path + (key,))] = owner
                            add_table(owner, address, None, relative + pointer(path + (key,)))
                        except (ValueError, TypeError): pass
                for key in row:
                    if key.endswith('_vtable_rva') and key not in ('primary_vtable_rva', 'object_vtable_rva'):
                        try:
                            address = number(row[key]);declaration = declared_field_owners.get((relative, pointer(path + (key,))))
                            owner = declaration['module'] if declaration else table_owner(address, alias)
                            field_hints[pointer(path + (key,))] = owner
                            if not declaration:
                                add_table(owner, address, None, relative + pointer(path + (key,)))
                        except (ValueError, TypeError): pass
                if 'rva' in row and (any(k in row for k in ('slot_entry_rvas', 'entries', 'slots')) or 'vtable_guards' in path):
                    try:
                        count = len(row['slot_entry_rvas']) if isinstance(row.get('slot_entry_rvas'), list) else None
                        add_table(alias, number(row['rva']), count, relative + pointer(path))
                    except (ValueError, TypeError):
                        pass
            if alias and isinstance(row.get('ordinal'), int):
                for address_key in ('rva', 'export_rva', 'target_rva'):
                    if address_key not in row:
                        continue
                    try:
                        export_rva = number(row[address_key]);ordinal = number(row['ordinal'])
                        exported = modules[alias].exports_by_ordinal.get(ordinal)
                        if exported and exported['rva'] == export_rva and not exported.get('forwarder'):
                            item['exports'].append({'json_pointer': pointer(path), 'module': alias, 'reference_rva': export_rva,
                                'reference_ordinal': ordinal, 'names': [n for n, e in modules[alias].exports.items()
                                    if not n.startswith('#') and e['ordinal'] == ordinal]})
                            break
                    except (ValueError, TypeError):
                        pass
        for path, row, inherited in _walk(document, modules=modules):
            prefix = pointer(path) if path else ''
            alias = next((row_hints[p] for p in sorted(row_hints, key=len, reverse=True)
                          if prefix == p or prefix.startswith(p + '/')), _hint(row, inherited, modules))
            for key, value in row.items():
                if key == 'rva' or key.endswith('_rva'):
                    try: value_rva = number(value)
                    except (ValueError, TypeError, OverflowError): continue
                    declaration = declared_field_owners.get((relative, pointer(path + (key,))))
                    owner = declaration['module'] if declaration else field_hints.get(pointer(path + (key,)), alias)
                    if key.lower().endswith('iat_rva'):
                        owners = [m for m, pe in modules.items() if value_rva in pe.imports_by_iat]
                        owner = owner if owner in owners else owners[0] if len(owners) == 1 else None
                        if owner:
                            imported = modules[owner].imports_by_iat[value_rva]
                            target_module = _module_alias(imported['dll'], modules)
                            imported_pe = modules.get(target_module)
                            imported_export = (imported_pe.exports.get(imported.get('name')) if imported.get('name') is not None else
                                               imported_pe.exports_by_ordinal.get(imported.get('ordinal'))) if imported_pe else None
                            import_slots[owner, value_rva] = {'module': owner, 'reference_rva': value_rva,
                                'dll': imported['dll'], 'name': imported.get('name'), 'ordinal': imported.get('ordinal'),
                                'target_module': target_module,
                                'reference_target_rva': imported_export['rva'] if imported_export and not imported_export.get('forwarder') else None,
                                'target_names': [n for n, e in imported_pe.exports.items() if not n.startswith('#') and imported_export and
                                                 e['rva'] == imported_export['rva'] and not e.get('forwarder')] if imported_pe else []}
                    item['fields'].append({'json_pointer': pointer(path + (key,)), 'module': owner,
                        'kind': 'IAT-slot' if key.lower().endswith('iat_rva') else 'rva', 'reference_rva': value_rva})
                elif key.endswith('_rvas') and isinstance(value, list):
                    for index, entry in enumerate(value):
                        try: value_rva = number(entry)
                        except (ValueError, TypeError, OverflowError): continue
                        item['fields'].append({'json_pointer': pointer(path + (key, index)), 'module': alias,
                            'kind': 'rva', 'reference_rva': value_rva})
            for suffix, value, kind, encoding in semantic_address_fields(row, path):
                try: value_rva = number(value)
                except (ValueError, TypeError, OverflowError): continue
                if alias not in modules:
                    continue
                if encoding == 'reference-preferred-VA':
                    value_rva -= modules[alias].image_base
                if value_rva < 0:
                    continue
                field = {'json_pointer': pointer(path + suffix), 'module': alias,
                         'kind': kind, 'reference_rva': value_rva}
                if encoding:
                    field['encoding'] = encoding
                item['fields'].append(field)
                if kind in ('function', 'virtual-slot'):
                    add_signature(alias, value_rva, 32, prefix + pointer(suffix), relative + prefix)
                elif kind == 'vtable':
                    add_table(alias, value_rva, None, relative + prefix)
            if path == ('allocator', 'mfc') and 'size_of_image' in row:
                item['pe_metadata_fields'].append({'json_pointer': prefix + '/size_of_image',
                                                  'module': alias, 'identity_key': 'image_size'})
        # Explicit root aliases have separate RVA/ordinal names. Their module
        # and export role come from audited native consumers, never a prefix
        # heuristic or a global numeric-parser rewrite.
        for declaration in owner_document['entries']:
            if declaration['profile'] != relative:
                continue
            alias = declaration['module']
            address_path = declaration['json_pointer']
            if declaration.get('identity_key'):
                item['pe_metadata_fields'].append({'json_pointer': address_path, 'module': alias,
                                                  'identity_key': declaration['identity_key']})
                continue
            if declaration.get('kind') != 'export-function':
                continue
            ordinal_path = declaration.get('ordinal_pointer')
            try:
                old = number(get_at(document, address_path))
                ordinal = number(get_at(document, ordinal_path)) if ordinal_path else None
                exported = (modules[alias].exports_by_ordinal.get(ordinal) if ordinal_path else
                            modules[alias].exports.get(declaration.get('export_name')))
                if not exported or exported['rva'] != old or exported.get('forwarder'):
                    raise ValueError('Declared native RVA/ordinal alias lacks the matching reference export role')
                if ordinal_path:
                    item['exports'].append({'json_pointer': '', 'rva_pointer': address_path, 'ordinal_pointer': ordinal_path,
                        'module': alias, 'reference_rva': old, 'reference_ordinal': ordinal,
                        'names': [n for n, e in modules[alias].exports.items() if not n.startswith('#') and
                                  e['ordinal'] == ordinal and not e.get('forwarder')]})
                add_signature(alias, old, 32, address_path, relative + address_path)
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                gap = {'kind': 'reference_export_alias', 'profile': relative, 'json_pointer': ordinal_path or address_path,
                       'module': alias, 'reason': str(exc)}
                gaps.append(gap);item['reference_gaps'].append(gap)
        # Partial profile readers validate the exact requested dictionary. All
        # dictionary owners receive subtree status, including nested guards,
        # classes and layout-only rows. No numeric value is rewritten here.
        native_paths = [f['json_pointer'] for f in item['fields']] + [
            g['json_pointer'] + '/' + g['byte_key'] for key in ('guards', 'raw_guards', 'virtual_guards') for g in item[key]]
        structured_collections = ('functions', 'vtable_guards', 'guards', 'code_guards', 'data_guards', 'classes', 'tables', 'methods')
        for path, row, _ in _walk(document):
            if not path:
                continue
            prefix = pointer(path)
            # These are key/value maps, not native row dictionaries. Their
            # consumers enumerate every value as an RVA or every key as a slot.
            if str(path[-1]) in ('methods', 'slots', 'metadata_slots') and all(not isinstance(v, (dict, list)) for v in row.values()):
                continue
            # Name->row collections (for example driver exports, table maps
            # and operation maps) enumerate every member as a native row. The
            # collection itself is not a row and must stay unmodified.
            if row and all(isinstance(value, (dict, list)) for value in row.values()):
                continue
            if (len(path) == 2 and path[0] in structured_collections or
                    any(p.startswith(prefix + '/') for p in native_paths)):
                item['entry_paths'].append({'json_pointer': prefix, 'name': row.get('name', row.get('class_name', prefix))})
        item['fields'] = list({f['json_pointer']: f for f in item['fields']}.values())
        if item['fields'] or item['guards']:
            profiles.append(item)
    if isinstance(explicit_fields, dict):
        explicit_fields = list(explicit_fields.get('entries', [])) + list(explicit_fields.get('source_guards', [])) + [dict(row, kind='export-ordinal-target') for row in explicit_fields.get('source_ordinals', [])]
    for row in explicit_fields or []:
        alias = str(row['module']).lower();rva = number(row['reference_rva'])
        if alias not in modules:
            gaps.append({'kind': 'explicit_field', 'reason': 'Reference module was not supplied', **row});continue
        explicit_kind = row.get('kind', row.get('address_kind', 'rva'))
        explicit_addresses.append({'module': alias, 'reference_rva': rva, 'kind': explicit_kind,
            'name': row.get('name'), 'origin': 'classified-source-PE-address'})
        if explicit_kind != 'PE_data_RVA_literal' and (explicit_kind in ('function', 'code', 'code-rva') or modules[alias].is_executable(rva)):
            add_signature(alias, rva, int(row.get('length', 32)), row.get('name'), 'explicit-classified-source')
        else:
            # A PE data/global address is not automatically a vtable. Try the
            # real RTTI parser as supporting evidence, without misreporting
            # ordinary globals/BSS as missing RTTI capabilities.
            add_table(alias, rva, None, 'explicit-classified-source', report_gap=explicit_kind in ('vtable', 'RTTI-vtable'))
        if row.get('profile'):
            profile = next((p for p in profiles if p['relative_path'] == row['profile']), None)
            if profile is None:
                raise ValueError('Explicit field profile is not in the supplied profile root: ' + row['profile'])
            field = {'json_pointer': row['json_pointer'], 'module': alias, 'kind': row.get('kind', 'rva'), 'reference_rva': rva}
            profile['fields'] = [old for old in profile['fields'] if old['json_pointer'] != field['json_pointer']] + [field]
    # Import operands need logical current-export roles when ordinals or the
    # dependency basename move. Add the target function to the same conservative
    # locator, rather than treating an ordinal as an address-independent alias.
    pending_import_models = list(signatures.values());seen_import_models = set()
    while pending_import_models:
        model = pending_import_models.pop()
        if id(model) in seen_import_models:
            continue
        seen_import_models.add(id(model))
        for imported in _signature_imports(model):
            target = _module_alias(imported['dll'], modules)
            pe = modules.get(target)
            exported = (pe.exports.get(imported.get('name')) if imported.get('name') is not None else
                        pe.exports_by_ordinal.get(imported.get('ordinal'))) if pe else None
            if exported and exported['rva'] and not exported.get('forwarder'):
                imported['export_role'] = {'module': target, 'reference_rva': exported['rva'],
                    'names': [n for n, e in pe.exports.items() if not n.startswith('#') and e['rva'] == exported['rva'] and not e.get('forwarder')]}
                before = set(signatures)
                if pe.is_executable(exported['rva']):
                    add_signature(target, exported['rva'], 32, imported.get('name'), 'import-export-role')
                pending_import_models.extend(signatures[k] for k in sorted(signatures.keys() - before))
    return {'schema': CATALOG_SCHEMA, 'catalog_scope': 'sparse selected guards and RTTI; no vendor sections',
        'normalization': {'architecture': 'PE32/I386', 'decoder': 'capstone', 'decoder_version_observed': xs.DECODER_VERSION,
            'HIGHLOW': 'PE relocation entries only', 'relative_calls_and_jumps': 'decoded operands plus target/body/import proof',
            'ordinary_object_displacements': 'exact; never wildcarded', 'whole_file_sha_admission': False},
        'reference_modules': {alias: {**pe.identity(), 'basename': pe.path.name if pe.path else None, **module_metadata[alias]} for alias, pe in modules.items()}, 'profiles': profiles,
        'signatures': list(signatures.values()), 'types': list(types.values()), 'explicit_addresses': explicit_addresses,
        'profile_field_module_declarations': owner_document, 'import_slots': list(import_slots.values()), 'catalog_gaps': gaps}


def resolve_catalog(catalog, actual_modules, *, reference_modules=None, prefer_content_cache=True, progress_callback=None):
    if catalog.get('schema') != CATALOG_SCHEMA:
        raise ValueError('Unsupported reference catalog schema')
    progress_report = PreparationProgress(progress_callback)
    progress_report('module_loading', 0, len(actual_modules), force=True)
    actual = {}
    for index, (alias, path) in enumerate(actual_modules.items()):
        actual[alias] = PE32(path)
        progress_report('module_loading', index + 1, len(actual_modules), module=alias)
    reference = _modules(reference_modules) if reference_modules else {}
    progress_report('module_loading', len(actual_modules), len(actual_modules), force=True)
    identities = {alias: pe.identity() for alias, pe in actual.items()}
    equal_modules = {alias for alias in actual if alias in catalog['reference_modules'] and
        identities[alias]['sha256'] == catalog['reference_modules'][alias]['sha256']}
    dependency_names = {}
    for alias, pe in actual.items():
        names = {pe.path.name.casefold()} if pe.path else set()
        if getattr(pe, 'export_module_name', None):
            names.add(pe.export_module_name.casefold())
        for name in names:
            dependency_names.setdefault(name, []).append((alias, pe))
    dependencies = {}
    for name, rows in dependency_names.items():
        owners = {str(pe.path.resolve()) if pe.path else id(pe) for _, pe in rows}
        if len(owners) == 1:
            dependencies[name] = rows[0]
    for alias, pe in actual.items():
        pe._abi_module_alias = alias
        pe._abi_module_aliases = tuple(a for a, other in actual.items()
                                      if other.path == pe.path and identities[a]['sha256'] == identities[alias]['sha256'])
    proven_export_targets = {}
    for pe in actual.values():
        pe._abi_import_dependencies = dependencies
        pe._abi_import_role_targets = proven_export_targets
    # Unchanged export-table bytes can prove an ordinal's role immediately.
    # Changed dependencies still need their actual function proof below.
    for entry in catalog['signatures']:
        if entry['module'] in equal_modules:
            proven_export_targets.setdefault((entry['module'], entry['reference_rva']), set()).add(entry['reference_rva'])
    # The reference PE is only required to verify out-of-prefix branch bodies.
    # The portable catalog can instead carry target signatures in future schemas;
    # do not silently skip that proof when the reference file is not supplied.
    result = {'schema': RESULT_SCHEMA, 'catalog_sha256': digest(_json_bytes(catalog)),
        'modules': {alias: {'reference': catalog['reference_modules'].get(alias), 'actual': {**pe.identity(), 'basename': pe.path.name if pe.path else None}}
                    for alias, pe in actual.items()}, 'rva_maps': {alias: {} for alias in actual},
        'functions': [], 'types': [], 'proofs': [], 'gaps': [],
        'capabilities': {'code_and_RTTI_locations_are_not_object_layout_or_call_semantics': True,
            'existing_object_layout_contracts_preserved': True, 'object_layout_verified': False,
            'calling_semantics_verified': False, 'evidence_flags_are_not_new_global_permission_gates': True},
        'adaptation_policy': {'strict_evidence_first': True,
            'automatic_fallback': 'independently-identified-structure-preserving-x86',
            'unrelated_hierarchy_and_callee_metadata_not_global_gates': True,
            'unresolved_entries_block_only_the_consuming_feature': True,
            'unresolved_reference_addresses_callable': False},
        'local_actual_module_paths': {alias: str(Path(path).resolve()) for alias, path in actual_modules.items()}}
    suggestions, anchors, anchor_identities, candidate_suggestions, table_members = {}, {}, {}, {}, {}
    signature_models = {}
    for model in catalog['signatures']:
        signature_models.setdefault((model['module'], model['reference_rva']), []).append(model)

    def suggest(alias, old, new, kind, proof_id):
        key = (alias, int(old));value = suggestions.setdefault(key, {})
        value.setdefault(int(new), []).append({'kind': kind, 'proof_id': proof_id})
        if kind == 'function':
            proven_export_targets.setdefault((alias, int(old)), set()).add(int(new))

    def complete_function(row, entry, current, context, method, *, identity=None, adaptive_evidence=None):
        alias, old, identifier = entry['module'], entry['reference_rva'], entry['id']
        pe = actual[alias]
        try:
            canonical, reloc = xs.normalized_guard_bytes(pe, current, entry['guard_length'], catalog['reference_modules'][alias]['image_base'])
            raw = pe.read(current, entry['guard_length'])
        except (ValueError, struct.error) as exc:
            row.update(status='unresolved', failure_category='guard_extent_unavailable',
                candidate_rvas=[current], required_guard_length=entry['guard_length'],
                reason='Located function cannot provide the unchanged consumer guard extent: '+str(exc))
            return False
        terminal = terminal_contract(entry, current, identity, adaptive_evidence)
        if terminal['required'] and not terminal['satisfied']:
            row.update(status='unresolved', failure_category='terminal_body_contract_unresolved',
                candidate_rvas=[current], terminal_body_contract=terminal,
                reason='Entry role was located, but its known complete terminal body contract was not preserved')
            return False
        row.update(status='resolved', actual_rva=current,
            actual_guard_bytes=raw.hex(), guard_bytes_at_reference_preferred_base=canonical.hex(),
            actual_relocation_offsets=reloc, proof_id=identifier, resolution_method=method,
            identity_anchors={'RTTI_slot': current in anchors.get((alias, old), set()),
                'named_export': [name for name in entry.get('exports', []) if name in pe.exports and
                                 not pe.exports[name].get('forwarder') and pe.exports[name]['rva'] == current]},
            normalization=context['normalization_proofs'])
        if 'reason' in row:
            row['initial_locator_observation'] = row.pop('reason')
        row.pop('candidate_rvas', None)
        row['failure_category'] = None
        row['address_proof_scope'] = 'direct-function-location'
        row['virtual_slot_numbers_adapted'] = False
        if terminal['required']:
            row['terminal_body_contract'] = terminal
        if identity is not None:
            row['adaptive_identity'] = copy.deepcopy(identity)
            row['adaptive_evidence'] = copy.deepcopy(adaptive_evidence or {})
        result['proofs'].append({'id': identifier, 'kind': method, 'module': alias,
            'reference_rva': old, 'actual_rva': current, 'object_displacements_preserved': True,
            'address_proof_scope': 'direct-function-location', 'virtual_slot_numbers_adapted': False,
            'normalization': context['normalization_proofs']})
        suggest(alias, old, current, 'function', identifier)
        for ref in context['referents']:
            if pe.is_executable(ref['actual_rva']):
                # Nested branch contexts may contain only a short body prefix.
                # Even a strict CALL/code-pointer comparison is therefore a
                # candidate for the callee's own complete catalog signature,
                # never an independently callable address proof.
                values = candidate_suggestions.setdefault((alias, int(ref['reference_rva'])), {})
                values.setdefault(int(ref['actual_rva']), set()).add(identifier)
            else:
                suggest(alias, ref['reference_rva'], ref['actual_rva'], ref['kind'], identifier)
        for ref in context.get('candidate_referents', []):
            if ref.get('kind') == 'code-reference' and pe.is_executable(ref['actual_rva']):
                values = candidate_suggestions.setdefault((alias, int(ref['reference_rva'])), {})
                values.setdefault(int(ref['actual_rva']), set()).add(identifier)
        if terminal['required']:
            values = candidate_suggestions.setdefault((alias, terminal['reference_body_rva']), {})
            values.setdefault(terminal['actual_body_rva'], set()).add(identifier)
        return True

    not_decoded = object()

    def match_candidate(entry, current, identity=None, *, verify_targets=True, allow_adaptive=True, local_actual=not_decoded):
        alias = entry['module'];pe = actual[alias]
        matched = xs.local_match(entry, pe, current) if local_actual is not_decoded else local_actual
        context = xs.verify_context(reference.get(alias), pe, entry, matched,
                                    entry['reference_rva'], current,
                                    verify_targets=verify_targets) if matched else None
        if context is not None:
            selected = {'actual': matched, 'context': context, 'adaptive': False}
            if identity is not None:
                selected['identity'] = identity
            return selected
        if allow_adaptive and identity is not None:
            relaxed = xs.adaptive_match(entry, pe, current, identity_proof=identity)
            if relaxed is not None:
                return {**relaxed, 'adaptive': True, 'identity': identity}
        return None

    def anchor_identity(alias, old, current):
        proofs = anchor_identities.get((alias, old), {}).get(current, [])
        # Named API identity can justify localized diagnostic/helper changes;
        # a same-numbered RTTI slot alone cannot establish method semantics.
        selected = next((proof for proof in proofs if proof['kind']=='named-export'), proofs[0] if proofs else None)
        return copy.deepcopy(selected) if selected is not None else None

    def terminal_contract(entry, current, identity=None, adaptive_evidence=None):
        """Close a known thunk body with its own longest supplied contract.

        This is an inline PE witness, not a callable body-address proof and not
        a dependency on the body's row.  It prevents a short 24-byte context
        from overriding a known longer body contract without wrapper/body
        callable-proof cycles.  Actual CALLs are never treated as entry JMPs.
        """
        old_body = None
        if entry.get('first_is_direct_thunk'):
            transfer = entry['transfers'][0]
            chain = transfer.get('target_signature_chain', [])
            if transfer.get('target_context_status') == 'complete' and chain:
                old_body = chain[-1]['reference_rva']
        if adaptive_evidence and adaptive_evidence.get('reference_body_rva') != entry['reference_rva']:
            old_body = adaptive_evidence.get('reference_body_rva')
        models = [model for model in signature_models.get((entry['module'], old_body), [])
                  if model['id'] != entry['id']]
        if old_body is None or old_body == entry['reference_rva'] or not models:
            return {'required': False, 'satisfied': True}
        longest = max(model['match_length'] for model in models)
        models = [model for model in models if model['match_length'] == longest]
        pe = actual[entry['module']]
        new_body = adaptive_evidence.get('actual_body_rva') if adaptive_evidence else None
        if new_body is None:
            cursor, seen = current, set()
            while cursor not in seen and pe.is_executable(cursor):
                seen.add(cursor)
                section = pe.section_for_rva(cursor)
                remaining = section.raw_size - (cursor-section.rva)
                try:
                    part = xs.decode_signature(pe, cursor, min(32, remaining))
                except (ValueError, struct.error):
                    break
                if not part['first_is_direct_thunk']:
                    new_body = cursor;break
                cursor = part['transfers'][0]['reference_target_rva']
        witness = {'required': True, 'satisfied': False, 'reference_body_rva': old_body,
                   'actual_body_rva': new_body, 'contract_ids': [model['id'] for model in models],
                   'complete_supplied_match_length': longest,
                   'scope': 'preparation-time-current-PE-terminal-contract',
                   'body_address_mapping_emitted': False, 'callable_body_row_dependency': False}
        if new_body is None or not pe.is_executable(new_body):
            witness['reason'] = 'Current entry has no verified terminal reached through actual direct JMPs'
            return witness
        body_identity = {**identity, 'actual_rva': new_body, 'relation': 'actual-entry-terminal-body'} if identity else None
        for model in models:
            selected = match_candidate(model, new_body, body_identity)
            if selected is None:
                continue
            try:
                xs.normalized_guard_bytes(pe, new_body, model['guard_length'],
                                          catalog['reference_modules'][entry['module']]['image_base'])
            except (ValueError, struct.error):
                continue
            witness.update(satisfied=True, verified_contract_id=model['id'],
                           normalization=selected['context']['normalization_proofs'])
            return witness
        witness['reason'] = 'Known complete terminal model or its unchanged guard extent is not available'
        return witness

    type_cache, thunk_member_cache = {}, {}
    progress_report('RTTI_tables', 0, len(catalog['types']), force=True)
    for type_index, entry in enumerate(catalog['types']):
        progress_report('RTTI_tables', type_index, len(catalog['types']), module=entry['module'], entry_id=entry['id'])
        alias, old = entry['module'], entry['reference'];proof_id = entry['id']
        if alias not in actual:
            result['types'].append({'id': proof_id, 'module': alias, 'status': 'unresolved',
                'failure_category': 'module_unavailable', 'blocked_scope': 'consuming-feature',
                'reason': 'Actual module not supplied'});continue
        key = (alias, old['decorated_name'])
        role_only = False;role_evidence = None
        if prefer_content_cache and alias in equal_modules:
            exact, different = [copy.deepcopy(old)], []
        else:
            if key not in type_cache:
                type_cache[key] = rtti.locate_type(actual[alias], old['decorated_name'])
            exact, different = rtti.pair_table(old, type_cache[key]['tables'])
            # A primary/interface identity is narrower than the complete
            # inheritance metadata.  Extra unrelated bases do not make every
            # getter/setter unavailable.  Their private fields and actual
            # methods still require their independent contracts below.
            if not exact:
                exact, different = rtti.pair_table_roles(old, type_cache[key]['tables'])
                role_only = bool(exact)
        if len(exact) != 1:
            result['types'].append({'id': proof_id, 'module': alias, 'status': 'ambiguous' if len(exact) > 1 else 'unresolved',
                'failure_category': 'table_identity_ambiguous' if len(exact) > 1 else 'table_role_not_located',
                'blocked_scope': 'consuming-feature',
                'decorated_name': old['decorated_name'], 'reference_vtable_rva': old['vtable_rva'],
                'candidate_vtable_rvas': [t['vtable_rva'] for t in exact],
                'observed_layout_differences': [{'vtable_rva': t['vtable_rva'], 'col_offset': t['col_offset'], 'hierarchy': t['hierarchy']} for t in different],
                'adaptation_attempts': ['exact-RTTI-hierarchy', 'stable-RTTI-table-subobject-role'],
                'reason': 'Current RTTI class/interface subobject role is not unique; private fields were not inferred'});continue
        new = exact[0]
        if role_only:
            role_evidence = rtti.table_role_proof(old, new)
        # COL, type and hierarchy identify this table independently of methods
        # which this particular request may never call. A shorter trailing
        # method list cannot invalidate that identity. Only slots actually
        # present on both sides may provide function anchors; native callers
        # still prove every slot they use against the live table.
        reference_slots = len(old['slot_entry_rvas'])
        actual_slots = len(new['slot_entry_rvas'])
        slots = {'reference_count': reference_slots, 'actual_count': actual_slots,
                 'shared_prefix_count': min(reference_slots, actual_slots),
                 'missing_reference_tail_indexes': list(range(actual_slots, reference_slots)),
                 'identity_is_not_proof_of_all_reference_slots': True}
        proof = {'id': proof_id, 'kind': 'RTTI-stable-table-subobject-role' if role_only else 'RTTI-class-COL-hierarchy-vtable', 'module': alias,
            'decorated_name': old['decorated_name'], 'reference': old, 'actual': new, 'slot_coverage': slots}
        if role_evidence is not None:
            proof['role_evidence'] = role_evidence
        result['proofs'].append(proof)
        result['types'].append({'id': proof_id, 'module': alias, 'status': 'resolved', 'reference': old, 'actual': new,
                                'resolution_method': proof['kind'], 'slot_coverage': slots,
                                'unrelated_hierarchy_changes_observed': role_only,
                                'private_member_layout_verified': False})
        address_pairs = rtti.role_address_pairs(old, new) if role_only else rtti.address_pairs(old, new)
        for before, after, kind in address_pairs:
            suggest(alias, before, after, kind, proof_id)
        members = set(new['slot_entry_rvas'])
        for start in (() if prefer_content_cache and alias in equal_modules else new['slot_entry_rvas']):
            if (alias, start) in thunk_member_cache:
                members.update(thunk_member_cache[alias, start]);continue
            cursor, seen = start, set()
            while cursor not in seen:
                seen.add(cursor)
                try:
                    part = xs.decode_signature(actual[alias], cursor, 32)
                except (ValueError, struct.error):
                    break
                if not part['first_is_direct_thunk']:
                    break
                cursor = part['transfers'][0]['reference_target_rva']
                if not actual[alias].is_executable(cursor):
                    break
                members.add(cursor)
            thunk_member_cache[alias, start] = seen
            members.update(seen)
        for slot_index, (before, after) in enumerate(zip(old['slot_entry_rvas'], new['slot_entry_rvas'])):
            table_members.setdefault((alias, before), set()).update(members)
            anchors.setdefault((alias, before), set()).add(after)
            identity = {'kind': 'rtti-slot', 'proof_id': proof_id, 'independent': True,
                        'actual_rva': after, 'decorated_name': old['decorated_name'],
                        'col_offset': old['col_offset'], 'slot_index': slot_index,
                        'table_identity_does_not_prove_method_or_private_fields': True}
            anchor_identities.setdefault((alias, before), {}).setdefault(after, []).append(identity)
            # Do not promote the reference thunk's intermediate bodies to
            # independent RTTI identities.  The actual entry may have lost its
            # JMP and start with CALL; body correspondence belongs to the
            # entry's returned actual_body_rva candidate and must pass the
            # body's own full catalog signature with a caller dependency.

    progress_report('RTTI_tables', len(catalog['types']), len(catalog['types']), force=True)
    pending = []
    local_candidates = {}
    identity_candidates = {}
    progress_report('functions', 0, len(catalog['signatures']), force=True)
    for function_index, entry in enumerate(catalog['signatures']):
        progress_report('functions', function_index, len(catalog['signatures']), module=entry['module'], entry_id=entry['id'])
        alias, old, identifier = entry['module'], entry['reference_rva'], entry['id']
        row = {'id': identifier, 'module': alias, 'reference_rva': old, 'names': entry.get('names', []),
               'blocked_scope': 'consuming-feature', 'adaptation_attempts': []}
        if alias not in actual:
            row.update(status='unresolved', failure_category='module_unavailable', reason='Actual module not supplied');result['functions'].append(row);continue
        pe = actual[alias]
        role_anchors = set(anchors.get((alias, old), set()))
        export_anchors = [pe.exports[name]['rva'] for name in entry.get('exports', [])
                          if name in pe.exports and not pe.exports[name].get('forwarder')]
        if len(set(export_anchors)) > 1:
            row.update(status='ambiguous', failure_category='export_alias_roles_diverged',
                candidate_rvas=sorted(set(export_anchors)),
                reason='Reference export aliases now name different functions; this shared RVA needs per-role adaptation')
            result['functions'].append(row);continue
        if role_anchors and export_anchors and not role_anchors.intersection(export_anchors):
            # A named direct-call entry may remain stable while its virtual
            # slot moved.  Preserve that observation, but do not turn a slot
            # ABI change into a global ban on the named direct function.
            row['RTTI_slot_mismatch_observed'] = {'slot_candidates': sorted(role_anchors),
                                                  'named_export_candidates': sorted(set(export_anchors)),
                                                  'virtual_slot_mapping_not_inferred': True}
            row['adaptation_attempts'].append('named-export-identity-with-observed-slot-difference')
            role_anchors = set(export_anchors)
        for current in set(export_anchors):
            names = sorted(name for name in entry.get('exports', [])
                           if name in pe.exports and not pe.exports[name].get('forwarder') and
                           pe.exports[name]['rva'] == current)
            export_id = identifier + ':named-export:' + ','.join(names)
            export_identity = {'kind': 'named-export', 'proof_id': export_id, 'independent': True,
                               'actual_rva': current, 'names': names}
            anchor_identities.setdefault((alias, old), {}).setdefault(current, []).append(export_identity)
            result['proofs'].append({'id': export_id, 'kind': 'current-named-export-identity',
                                    'module': alias, 'actual_rva': current, 'names': names,
                                    'identity_is_not_a_function_layout_proof': True})
        if export_anchors:
            role_anchors = role_anchors.intersection(export_anchors) if role_anchors else set(export_anchors)
        identity_candidates[identifier] = set(role_anchors)
        if prefer_content_cache and alias in equal_modules:
            context = {'normalization_proofs': [{'kind': 'complete-PE-content-equivalence-cache',
                'same_content_sha256': catalog['reference_modules'][alias]['sha256']}], 'referents': []}
            complete_function(row, entry, old, context, 'identical-PE-content-cache')
            result['functions'].append(row)
            continue
        candidates = xs.candidates(pe, entry, role_anchors)
        # Include a stable prefix fallback for instruction-length changes; this
        # is also checked for true ambiguity, never a reference-address fallback.
        if not role_anchors:
            candidates = sorted(set(candidates + xs.candidates(pe, entry, prefix_fallback=True)))
        local_candidates[identifier] = []
        primary_candidates = candidates[:]
        strict_matches = []
        for candidate_index, candidate in enumerate(candidates):
            progress_report('function_candidates', function_index, len(catalog['signatures']),
                            module=alias, entry_id=identifier, candidates_completed=candidate_index, candidates_total=len(candidates))
            local_actual = xs.local_match(entry, pe, candidate)
            if local_actual is not None:
                local_candidates[identifier].append(candidate)
            selected = match_candidate(entry, candidate, anchor_identity(alias, old, candidate), allow_adaptive=False, local_actual=local_actual)
            if selected is not None:
                strict_matches.append((candidate, selected))
        row['adaptation_attempts'].append('exact-decoded-instructions-and-context')
        if role_anchors:
            row['adaptation_attempts'].append('independent-identity-structure-preserving-fallback')
        if role_anchors and not export_anchors:
            # A direct-call function can remain unchanged while unrelated
            # virtual methods were inserted before its old slot.  A full,
            # unique strict body proof can locate it independently; this does
            # not claim the old slot number is valid for a virtual caller.
            fallback = sorted((set(xs.candidates(pe, entry) +
                                   xs.candidates(pe, entry, prefix_fallback=True)) - set(candidates)) &
                              table_members.get((alias, old), set()))
            for candidate_index, candidate in enumerate(fallback):
                progress_report('same_class_candidates', function_index, len(catalog['signatures']),
                                module=alias, entry_id=identifier, candidates_completed=candidate_index, candidates_total=len(fallback))
                local_actual = xs.local_match(entry, pe, candidate)
                if local_actual is not None:
                    local_candidates[identifier].append(candidate)
                selected = match_candidate(entry, candidate, allow_adaptive=False, local_actual=local_actual)
                if selected is not None:
                    strict_matches.append((candidate, selected))
            candidates = sorted(set(candidates + fallback))
            row['adaptation_attempts'].append('same-class-strict-method-search-before-slot-adaptation')
        # Complete same-class strict identity outranks an old slot number's
        # relaxed structural candidate.  A newly inserted B must not mask A
        # merely because their push/call/ret skeletons look alike.
        matches = strict_matches[:]
        if not matches:
            for candidate in primary_candidates:
                identity = anchor_identity(alias, old, candidate)
                if identity is None:
                    continue
                selected = match_candidate(entry, candidate, identity)
                if selected is not None:
                    matches.append((candidate, selected))
        if len(matches) != 1:
            row.update(status='ambiguous' if len(matches) > 1 else 'missing',
                failure_category='function_identity_ambiguous' if len(matches) > 1 else 'function_structure_not_located',
                candidate_rvas=[v[0] for v in matches], candidates_examined=len(candidates),
                reason='Normalized instruction/body/RTTI/export proof is not unique' if matches else
                    'No independently identified candidate preserves required instruction/field/stack roles; unresolved reference value is not callable')
            result['functions'].append(row);pending.append((row, entry));continue
        current, selected = matches[0]
        row['candidates_examined'] = len(candidates)
        completed = complete_function(row, entry, current, selected['context'],
            'identity-anchored-adaptive-x86' if selected['adaptive'] else 'decoded-x86-function',
            identity=selected.get('identity'), adaptive_evidence=selected.get('evidence'))
        result['functions'].append(row)
        if not completed and row.get('failure_category') == 'terminal_body_contract_unresolved':
            pending.append((row, entry))
    # A uniquely identified caller's same decoded CALL/absolute operand can
    # constrain a generic callee. Iterate the proof graph, without old-RVA bias.
    progress_report('functions', len(catalog['signatures']), len(catalog['signatures']), force=True)
    progress = True
    fixed_point_round = 0
    progress_report('caller_proof_fixed_point', 0, len(pending), force=True)
    while progress:
        progress = False
        fixed_point_round += 1
        for pending_index, (row, entry) in enumerate(pending):
            progress_report('caller_proof_fixed_point', pending_index, len(pending), iteration=fixed_point_round,
                            module=entry['module'], entry_id=entry['id'])
            if row['status'] == 'resolved' or row.get('failure_category') == 'guard_extent_unavailable':
                continue
            alias, old = entry['module'], entry['reference_rva']
            values = suggestions.get((alias, old), {})
            advisory = candidate_suggestions.get((alias, old), {})
            constrained = values if values else advisory
            candidates = ([next(iter(constrained))] if len(constrained) == 1 else
                          sorted(set(local_candidates.get(entry['id'], [])) | identity_candidates.get(entry['id'], set())))
            matches = []
            for current in candidates:
                if not actual[alias].is_executable(current):
                    continue
                identity = anchor_identity(alias, old, current)
                supporting_ids = []
                if len(constrained) == 1 and current in constrained:
                    supporting_ids = (sorted({proof['proof_id'] for proof in values[current]}) if values else
                                      sorted(advisory[current]))
                    supporting_ids = [value for value in supporting_ids if value != entry['id']]
                    if identity is None and supporting_ids:
                        identity = {'kind': 'proven-caller-role', 'proof_id': supporting_ids[0],
                                    'independent': True, 'actual_rva': current,
                                    'supporting_proof_ids': supporting_ids,
                                    'candidate_is_not_callable_until_own_structure_matches': True}
                selected = match_candidate(entry, current, identity)
                if selected is not None:
                    matches.append((current, selected, supporting_ids))
            if len(matches) != 1:
                continue
            current, selected, supporting_ids = matches[0]
            row['adaptation_attempts'].append('proven-caller-target-candidate' if constrained else 'current-import-role-fixed-point')
            completed = complete_function(row, entry, current, selected['context'],
                'caller-anchored-adaptive-x86' if selected['adaptive'] else
                'unique-decoded-callgraph-referent' if len(constrained) == 1 else 'decoded-x86-current-import-role',
                identity=selected.get('identity'), adaptive_evidence=selected.get('evidence'))
            if not completed:
                continue
            if selected.get('identity', {}).get('kind') in ('named-export', 'rtti-slot'):
                supporting_ids = []
            if supporting_ids:
                # This candidate was selected by a live caller/operand proof,
                # rather than unique standalone signature identity. Keep its
                # alternatives as dependencies instead of promoting it to an
                # independent root proof that could survive its caller.
                row['supporting_proof_ids'] = supporting_ids
                result['proofs'][-1]['supporting_proof_ids'] = list(row['supporting_proof_ids'])
            progress = True
    # Exact whole-file equality is a cache-equivalence proof, never admission:
    # unknown files still take all dynamic paths above and remain partial where
    # their actual code is ambiguous. No version number is consulted.
    result['content_equivalence_cache'] = {'used_as_admission': False, 'equivalent_modules': sorted(equal_modules),
        'unknown_modules_refused_by_hash': False}
    for row, entry in pending:
        if row['status'] == 'resolved' or entry['module'] not in equal_modules:
            continue
        row['dynamic_status_before_cache'] = row['status']
        context = {'normalization_proofs': [{'kind': 'complete-PE-content-equivalence-cache',
            'same_content_sha256': catalog['reference_modules'][entry['module']]['sha256']}], 'referents': []}
        complete_function(row, entry, entry['reference_rva'], context, 'identical-PE-content-cache')
    # An import proof cannot retain a transiently unique export body if a later
    # signature produced conflicting evidence. Recheck those dependencies to a
    # fixed point and withdraw their originating address suggestions on failure.
    signatures_by_id = {entry['id']: entry for entry in catalog['signatures']}
    functions_by_id = {row['id']: row for row in result['functions']}
    invalidated = True
    validation_round = 0
    progress_report('proof_dependency_validation', 0, len(result['functions']), force=True)
    while invalidated:
        invalidated = False
        validation_round += 1
        proven_export_targets.clear()
        for row in result['functions']:
            if row['status'] == 'resolved':
                proven_export_targets.setdefault((row['module'], row['reference_rva']), set()).add(row['actual_rva'])
        for validation_index, row in enumerate(result['functions']):
            progress_report('proof_dependency_validation', validation_index, len(result['functions']),
                            iteration=validation_round, module=row['module'], entry_id=row['id'])
            if row['status'] != 'resolved' or row['resolution_method'] == 'identical-PE-content-cache':
                continue
            entry = signatures_by_id[row['id']]
            supporting = row.get('supporting_proof_ids', [])
            dependency_lost = bool(supporting) and not any(
                (identifier not in functions_by_id or functions_by_id[identifier]['status'] == 'resolved') and
                any(proof['id'] == identifier and proof.get('status') != 'withdrawn' for proof in result['proofs'])
                for identifier in supporting)
            if dependency_lost:
                independent = []
                candidates = sorted(set(local_candidates.get(row['id'], [])) |
                                    identity_candidates.get(row['id'], set()))
                for candidate in candidates:
                    identity = anchor_identity(row['module'], entry['reference_rva'], candidate)
                    selected = match_candidate(entry, candidate, identity)
                    if selected is not None:
                        independent.append((candidate, selected))
                if [candidate for candidate, _ in independent] == [row['actual_rva']]:
                    # Retain a genuinely unique standalone/export/RTTI proof
                    # if one has become available; caller loss alone does not
                    # override independent surviving identity evidence.
                    row.pop('supporting_proof_ids', None)
                    selected = independent[0][1]
                    row['resolution_method'] = ('identity-anchored-adaptive-x86-independent' if selected['adaptive']
                                                else 'decoded-x86-independent-proof')
                    if selected.get('identity') is not None:
                        row['adaptive_identity'] = selected['identity']
                        row['adaptive_evidence'] = selected.get('evidence', {})
                    else:
                        row.pop('adaptive_identity', None)
                        row.pop('adaptive_evidence', None)
                    for proof in result['proofs']:
                        if proof['id'] == row['id']:
                            proof.pop('supporting_proof_ids', None)
                            proof['kind'] = row['resolution_method']
                    dependency_lost = False
            has_import_roles = any(imported.get('export_role') for imported in _signature_imports(entry))
            import_valid = True
            if has_import_roles and not dependency_lost:
                import_valid = match_candidate(entry, row['actual_rva'], row.get('adaptive_identity')) is not None
            terminal_valid = True
            if row.get('terminal_body_contract', {}).get('required') and not dependency_lost:
                terminal_valid = terminal_contract(entry, row['actual_rva'], row.get('adaptive_identity'),
                                                   row.get('adaptive_evidence'))['satisfied']
            if not dependency_lost and import_valid and terminal_valid:
                continue
            row.update(status='unresolved', failure_category='identity_dependency_withdrawn' if dependency_lost else
                       'terminal_body_contract_unresolved' if not terminal_valid else 'import_role_unavailable',
                       reason='All originating caller/operand proofs were withdrawn' if dependency_lost else
                       'Known complete terminal body contract became unavailable' if not terminal_valid else
                       'Current import export-role proof became unavailable or conflicting')
            for proof in result['proofs']:
                if proof['id'] == row['id']:
                    proof.update(status='withdrawn', reason=row['reason'])
            invalidated = True
            for key, values in list(suggestions.items()):
                for value, proofs in list(values.items()):
                    retained = [proof for proof in proofs if proof['proof_id'] != row['id']]
                    if retained:
                        values[value] = retained
                    else:
                        del values[value]
                if not values:
                    del suggestions[key]
    cache_addresses = [field for p in catalog['profiles'] for field in p['fields']] + catalog.get('explicit_addresses', [])
    for field in cache_addresses:
        alias, address = field.get('module'), field['reference_rva']
        if alias in equal_modules and 0 <= address < actual[alias].image_size:
            proof_id = alias + ':complete-PE-content-equivalence'
            suggest(alias, address, address, 'identical-PE-content-cache', proof_id)
    for alias in equal_modules:
        result['proofs'].append({'id': alias + ':complete-PE-content-equivalence', 'kind': 'complete-PE-content-equivalence-cache',
            'module': alias, 'same_content_sha256': catalog['reference_modules'][alias]['sha256'],
            'meaning': 'Known source bytes are unchanged; not a whitelist and not required for unknown files'})
    # IAT storage belongs to the importing image, whereas its row's module
    # usually names the destination DLL. Match true import identities, not an
    # accidental same numeric RVA inside the destination image.
    for imported in catalog.get('import_slots', []):
        alias, old = imported['module'], imported['reference_rva']
        if alias not in actual:
            continue
        symbol = {key: imported.get(key) for key in ('dll', 'name', 'ordinal')}
        if imported.get('target_module') and imported.get('reference_target_rva') is not None:
            symbol['export_role'] = {'module': imported['target_module'],
                'reference_rva': imported['reference_target_rva'], 'names': imported.get('target_names', [])}
        candidates = [rva for rva, row in actual[alias].imports_by_iat.items()
                      if xs.import_symbol_match(symbol, row, actual[alias])]
        if len(candidates) == 1:
            proof_id = f'{alias}:IAT:0x{old:x}'
            suggest(alias, old, candidates[0], 'current-import-identity', proof_id)
            result['proofs'].append({'id': proof_id, 'kind': 'current-import-identity', 'module': alias,
                'reference_rva': old, 'actual_rva': candidates[0], 'dll': imported['dll'], 'name': imported.get('name')})
    # Conflicting referents never silently overwrite a previous mapping.
    reverse = {}
    for (alias, before), values in suggestions.items():
        if len(values) == 1:
            after = next(iter(values));reverse.setdefault((alias, after), set()).add(before)
    for (alias, before), values in suggestions.items():
        if len(values) != 1:
            result['gaps'].append({'module': alias, 'reference_rva': before, 'reason': 'Conflicting current-RVA proofs', 'actual_candidates': list(values)});continue
        after, proofs = next(iter(values.items()))
        operand_only = all(p['kind'] in ('operand-reference', 'code-reference') for p in proofs)
        if operand_only and len(reverse[alias, after]) > 1:
            result['gaps'].append({'module': alias, 'reference_rva': before, 'reason': 'Operand referent is not one-to-one', 'actual_rva': after});continue
        result['rva_maps'][alias][hex(before)] = {'actual_rva': after, 'kind': proofs[0]['kind'],
            'proof_id': proofs[0]['proof_id'], 'proof_ids': sorted({p['proof_id'] for p in proofs})}
    result['summary'] = {'functions': len(result['functions']),
        'functions_resolved': sum(f['status'] == 'resolved' for f in result['functions']),
        'RTTI_tables': len(result['types']), 'RTTI_tables_resolved': sum(t['status'] == 'resolved' for t in result['types']),
        'mapped_addresses': sum(len(m) for m in result['rva_maps'].values()), 'whole_file_sha_used_as_admission': False,
        'functions_using_dynamic_proof': sum(f.get('resolution_method') != 'identical-PE-content-cache' and f['status'] == 'resolved' for f in result['functions']),
        'functions_using_content_equivalence_cache': sum(f.get('resolution_method') == 'identical-PE-content-cache' for f in result['functions']),
        'functions_using_identity_anchored_adaptation': sum(f['status'] == 'resolved' and 'adaptive-x86' in f.get('resolution_method', '') for f in result['functions']),
        'tables_using_stable_role_adaptation': sum(t['status'] == 'resolved' and t.get('unrelated_hierarchy_changes_observed', False) for t in result['types']),
        'unsupported_entries_do_not_disable_other_features': True,
        'all_code_locations_resolved': all(f['status'] == 'resolved' for f in result['functions'])}
    decode_caches = [getattr(pe, '_abi_signature_decode_cache', {}) for pe in actual.values()]
    progress_report('native_resolution_complete', len(result['functions']), len(result['functions']), force=True,
                    functions_resolved=result['summary']['functions_resolved'],
                    decode_calls=sum(cache.get('calls', 0) for cache in decode_caches),
                    decode_cache_hits=sum(cache.get('hits', 0) for cache in decode_caches),
                    actual_decodes=sum(cache.get('decodes', 0) for cache in decode_caches))
    return result


def _rows_by_profile_entry(entries, rows, *, include_exact=False):
    """Group rows by matching JSON pointer ancestors, preserving input order."""
    grouped = {}
    for row in rows:
        pointer = row['json_pointer']
        end = len(pointer) if include_exact else pointer.rfind('/')
        while end >= 0:
            prefix = pointer[:end]
            if prefix in entries:
                grouped.setdefault(prefix, []).append(row)
            end = pointer.rfind('/', 0, end)
    return grouped


def write_resolved_profiles(catalog, result, output_dir, *, profile_root, compact_names=False):
    """All profiles get a real SHA, with per-field/entry partial-state evidence."""
    if catalog.get('schema') != CATALOG_SCHEMA or result.get('schema') != RESULT_SCHEMA:
        raise ValueError('Catalog/adaptation schema differs')
    out = Path(output_dir).resolve();root = Path(profile_root).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Resolved profile output must be new or empty')
    out.mkdir(parents=True, exist_ok=True)
    attestation = {'schema': ATTESTATION_SCHEMA, 'catalog_sha256': result['catalog_sha256'],
        'reference_profiles': [], 'modules': result['modules'], 'rva_maps': result['rva_maps'],
        'capabilities': result['capabilities'], 'gaps': result['gaps'],
        'local_actual_module_paths': result.get('local_actual_module_paths', {}),
        'resolved_profile_root': str(out), 'vendor_whole_file_sha_admission': False}
    functions = {f['id']: f for f in result['functions']}
    functions_by_address = {}
    for item in result['functions']:
        if 'reference_rva' in item:
            functions_by_address.setdefault((item['module'], item['reference_rva']), []).append(item)

    def address_diagnostics(alias, address):
        rows = functions_by_address.get((alias, address), [])
        return [{'entry': item['id'], 'status': item['status'],
                 'failure_category': item.get('failure_category'),
                 'adaptation_attempts': item.get('adaptation_attempts', []),
                 'reason': item.get('reason')} for item in rows if item['status'] != 'resolved']
    actual_pes = {}
    for ordinal, profile in enumerate(catalog['profiles']):
        source = (root / profile['relative_path']).resolve()
        if not source.is_relative_to(root):
            raise ValueError('Reference profile source changed: ' + profile['relative_path'])
        source_raw = source.read_bytes()
        if digest(source_raw) != profile['reference_sha256']:
            raise ValueError('Reference profile source changed: ' + profile['relative_path'])
        document = json.loads(source_raw.decode('utf-8-sig'))
        record = {'relative_path': profile['relative_path'], 'reference_sha256': profile['reference_sha256'],
            'resolved_relative_path': f'{ordinal:03x}.json' if compact_names else profile['relative_path'],
            'resolved_fields': [], 'unresolved_fields': [], 'entry_resolutions': []}
        record['unresolved_fields'].extend(copy.deepcopy(profile.get('reference_gaps', [])))
        for field in profile['fields']:
            alias, old = field.get('module'), field['reference_rva'];path = field['json_pointer']
            mapping = result['rva_maps'].get(alias, {}).get(hex(old))
            if mapping is None:
                record['unresolved_fields'].append({'json_pointer': path, 'module': alias, 'reference_rva': old,
                    'failure_category': 'address_not_located', 'blocked_scope': 'consuming-entry',
                    'locator_diagnostics': address_diagnostics(alias, old),
                    'reason': 'No unique current PE address proof; retained reference value is not an actual address'})
                continue
            original = get_at(document, path)
            encoded = mapping['actual_rva'] + (catalog['reference_modules'][alias]['image_base']
                       if field.get('encoding') == 'reference-preferred-VA' else 0)
            set_at(document, path, _format_number(original, encoded))
            record['resolved_fields'].append({'json_pointer': path, 'module': alias, 'reference_rva': old,
                'actual_rva': mapping['actual_rva'], 'proof_id': mapping['proof_id']})
        for field in profile.get('pe_metadata_fields', []):
            alias, path = field.get('module'), field['json_pointer']
            identity = result['modules'].get(alias, {}).get('actual', {})
            if field['identity_key'] not in identity:
                record['unresolved_fields'].append({'json_pointer': path, 'module': alias,
                    'reason': 'Selected current PE identity is unavailable for required module metadata'})
                continue
            current = identity[field['identity_key']]
            set_at(document, path, _format_number(get_at(document, path), current))
            record['resolved_fields'].append({'json_pointer': path, 'module': alias,
                'actual_value': current, 'proof_id': alias + ':selected-current-PE-header',
                'proof_kind': 'selected-current-PE-header-' + field['identity_key']})
        for guard in profile['guards']:
            located = functions.get(guard['guard_id'])
            if not located or located['status'] != 'resolved':
                record['unresolved_fields'].append({'json_pointer': guard['json_pointer'] + '/' + guard['byte_key'],
                    'failure_category': (located or {}).get('failure_category', 'function_guard_not_located'),
                    'blocked_scope': 'consuming-entry',
                    'locator_diagnostics': [{'entry': guard['guard_id'], 'status': (located or {}).get('status', 'missing'),
                        'adaptation_attempts': (located or {}).get('adaptation_attempts', [])}],
                    'reason': 'Function byte guard was not uniquely resolved'})
                continue
            row = get_at(document, guard['json_pointer'])
            row[guard['byte_key']] = located['guard_bytes_at_reference_preferred_base']
            for key in guard['relocation_keys']:
                row[key] = list(located['actual_relocation_offsets'])
        for guard in profile.get('raw_guards', []):
            alias = guard['module'];mapping = result['rva_maps'].get(alias, {}).get(hex(guard['reference_rva']))
            if mapping is None:
                record['unresolved_fields'].append({'json_pointer': guard['json_pointer'] + '/' + guard['byte_key'],
                    'reason': 'PE data guard has no unique current address proof'})
                continue
            if alias not in actual_pes:
                actual_pes[alias] = PE32(result['local_actual_module_paths'][alias])
            try:
                canonical, offsets = xs.normalized_guard_bytes(actual_pes[alias], mapping['actual_rva'], guard['length'], catalog['reference_modules'][alias]['image_base'])
            except (ValueError, struct.error) as exc:
                record['unresolved_fields'].append({'json_pointer': guard['json_pointer'] + '/' + guard['byte_key'],
                    'failure_category': 'guard_extent_unavailable', 'blocked_scope': 'consuming-entry',
                    'reason': 'Current data guard cannot provide the unchanged consumer extent: '+str(exc)})
                continue
            row = get_at(document, guard['json_pointer']);row[guard['byte_key']] = canonical.hex()
            for key in guard['relocation_keys']:
                row[key] = offsets
        for export in profile.get('exports', []):
            alias, old = export['module'], export['reference_rva']
            path = export['json_pointer'];ordinal_path = export.get('ordinal_pointer', path + '/ordinal')
            mapping = result['rva_maps'].get(alias, {}).get(hex(old))
            if alias not in actual_pes and alias in result.get('local_actual_module_paths', {}):
                actual_pes[alias] = PE32(result['local_actual_module_paths'][alias])
            candidates = []
            if mapping and alias in actual_pes:
                pe = actual_pes[alias]
                named = [pe.exports[n] for n in export['names'] if n in pe.exports and
                    pe.exports[n]['rva'] == mapping['actual_rva'] and not pe.exports[n].get('forwarder')]
                entries = named if export['names'] else [e for e in pe.exports_by_ordinal.values()
                    if e['rva'] == mapping['actual_rva'] and not e.get('forwarder')]
                candidates = sorted({e['ordinal'] for e in entries})
                # Multiple ordinal aliases can legitimately share one MFC
                # body. Complete content equivalence proves the old export
                # table entry is unchanged, without choosing one on a new PE.
                if alias in result.get('content_equivalence_cache', {}).get('equivalent_modules', []):
                    old_export = pe.exports_by_ordinal.get(export['reference_ordinal'])
                    if old_export and old_export['rva'] == mapping['actual_rva'] and not old_export.get('forwarder'):
                        candidates = [export['reference_ordinal']]
            if len(candidates) == 1:
                set_at(document, ordinal_path, _format_number(get_at(document, ordinal_path), candidates[0]))
                record['resolved_fields'].append({'json_pointer': ordinal_path, 'module': alias,
                    'reference_ordinal': export['reference_ordinal'], 'actual_ordinal': candidates[0],
                    'proof_id': mapping['proof_id'], 'proof_kind': 'resolved-function-and-current-export-table'})
            else:
                record['unresolved_fields'].append({'json_pointer': ordinal_path, 'module': alias,
                    'reason': 'Resolved function and current export table do not prove one export ordinal',
                    'candidate_ordinals': candidates})
        for guard in profile.get('virtual_guards', []):
            alias = guard['module'];mapping = result['rva_maps'].get(alias, {}).get(hex(guard['reference_rva']))
            if alias not in actual_pes and alias in result.get('local_actual_module_paths', {}):
                actual_pes[alias] = PE32(result['local_actual_module_paths'][alias])
            if not mapping or alias not in actual_pes or not _virtual_zero_span(actual_pes[alias], mapping['actual_rva'], guard['length']):
                record['unresolved_fields'].append({'json_pointer': guard['json_pointer'] + '/' + guard['byte_key'],
                    'reason': 'Mapped data has not preserved the declared loader-zero virtual section role'})
            # Preserve the published zero expectation. The existing runtime
            # guard still reads actual memory; no bytes are invented on disk.
        entry_paths = profile['entry_paths']
        if entry_paths:
            prefixes = {entry['json_pointer'] for entry in entry_paths}
            details_by_entry = _rows_by_profile_entry(prefixes, record['unresolved_fields'], include_exact=True)
            resolved_by_entry = _rows_by_profile_entry(prefixes, record['resolved_fields'])
            fields_by_entry = _rows_by_profile_entry(prefixes, profile['fields'])
            direct_fields = {}
            for field in profile['fields']:
                direct_fields.setdefault(field['json_pointer'], field)
        for entry in entry_paths:
            prefix = entry['json_pointer']
            details = details_by_entry.get(prefix, [])
            resolved = resolved_by_entry.get(prefix, [])
            direct_details = [u for u in details if '/' not in u['json_pointer'][len(prefix) + 1:]]
            state = {'status': 'unresolved' if details else 'resolved', 'details': details,
                     'direct_status': 'unresolved' if direct_details else 'resolved', 'direct_details': direct_details,
                     'profile': profile['relative_path'], 'entry': entry['name'], 'json_pointer': prefix,
                     'no_native_address_fields': prefix not in fields_by_entry,
                     'proof_ids': sorted({r['proof_id'] for r in resolved})}
            state['blocked_scope'] = 'consuming-entry'
            state['failure_categories'] = sorted({item.get('failure_category', 'required_contract_unresolved') for item in details})
            direct_rva = direct_fields.get(prefix + '/rva')
            if direct_rva is not None:
                state['reference_rva'] = direct_rva['reference_rva']
                state['module'] = direct_rva['module']
            get_at(document, prefix)['_abi_resolution'] = state
            record['entry_resolutions'].append({'json_pointer': prefix, 'name': entry['name'], **state})
        record['status'] = 'resolved' if not record['unresolved_fields'] else 'partial' if record['resolved_fields'] else 'unresolved'
        document['_mcgs_abi_resolution'] = {'schema': ATTESTATION_SCHEMA, 'status': record['status'],
            'reference_sha256': profile['reference_sha256'], 'unresolved_fields': record['unresolved_fields'],
            'retained_unresolved_values_are_reference_only': True, 'guard_bytes_preferred_base_policy': 'reference module preferred base',
            'unresolved_entries_do_not_disable_other_features': True}
        target = (out / record['resolved_relative_path']).resolve()
        if not target.is_relative_to(out):
            raise ValueError('Resolved profile path escapes output')
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = _json_bytes(document);target.write_bytes(raw)
        record['resolved_sha256'] = digest(raw)
        attestation['reference_profiles'].append(record)
    (out / 'attestation.json').write_bytes(_json_bytes(attestation))
    return attestation


def _module_args(values):
    result = {}
    for value in values:
        alias, sep, path = value.partition('=')
        if not sep or not alias or not path or alias.lower() in result:
            raise ValueError('Use distinct alias=absolute-file module arguments')
        result[alias.lower()] = Path(path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    catalog_cmd = sub.add_parser('catalog')
    catalog_cmd.add_argument('--reference-module', action='append', required=True)
    catalog_cmd.add_argument('--profiles', type=Path, required=True)
    catalog_cmd.add_argument('--explicit-fields', type=Path)
    catalog_cmd.add_argument('--out', type=Path, required=True)
    locate_cmd = sub.add_parser('locate')
    locate_cmd.add_argument('--catalog', type=Path, default=DEFAULT_CATALOG)
    locate_cmd.add_argument('--actual-module', action='append', required=True)
    locate_cmd.add_argument('--reference-module', action='append', default=[])
    locate_cmd.add_argument('--no-content-cache', action='store_true', help='Exercise dynamic instruction/RTTI proofs even for byte-identical reference files')
    locate_cmd.add_argument('--profiles', type=Path)
    locate_cmd.add_argument('--resolved-directory', type=Path)
    locate_cmd.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Output must be a new file')
    if args.command == 'catalog':
        extra = json.loads(args.explicit_fields.read_text('utf-8-sig')) if args.explicit_fields else None
        result = create_catalog(_module_args(args.reference_module), args.profiles, explicit_fields=extra)
    else:
        catalog = load_catalog(args.catalog)
        result = resolve_catalog(catalog, _module_args(args.actual_module), reference_modules=_module_args(args.reference_module) or None,
                                 prefer_content_cache=not args.no_content_cache)
        if args.resolved_directory:
            if not args.profiles:
                raise ValueError('--resolved-directory requires --profiles for exact original documents')
            attest = write_resolved_profiles(catalog, result, args.resolved_directory, profile_root=args.profiles)
            result['attestation_file'] = str(args.resolved_directory / 'attestation.json')
            result['attestation_sha256'] = digest(_json_bytes(attest))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.command == 'catalog':
        write_catalog(args.out, result)
    else:
        args.out.write_bytes(_json_bytes(result))
    print(json.dumps({'output': str(args.out), 'schema': result['schema'],
        'summary': result.get('summary'), 'function_count': len(result.get('signatures', [])),
        'profile_count': len(result.get('profiles', [])), 'Pro_started_or_called': False}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc), 'Pro_started_or_called': False}), file=sys.stderr)
        raise SystemExit(1)
