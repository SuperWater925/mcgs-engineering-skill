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
import sys

sys.dont_write_bytecode = True
from pe32 import PE32
import rtti
import x86_signature as xs

CATALOG_SCHEMA = 'mcgs-native-reference-catalog/v1'
RESULT_SCHEMA = 'mcgs-native-abi-adaptation/v1'
ATTESTATION_SCHEMA = 'mcgs-native-resolved-profiles/v1'
DEFAULT_CATALOG = Path(__file__).resolve().parent / 'catalogs/reference.json.gz'
PROFILE_FIELD_MODULES = Path(__file__).resolve().parent / 'catalogs/profile-field-modules.json'
BYTE_KEYS = ('expected_first_32_bytes', 'expected_first32', 'first32', 'bytes', 'expected_bytes', 'code_bytes')
RELOC_KEYS = ('relocatable_dword_offsets_in_first32', 'relocation_offsets', 'reloc_offsets', 'relocations')


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
                    rtti.describe_vtable(pe, address, 0);owners.append(candidate)
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
        item = {'relative_path': relative, 'reference_sha256': digest(raw), 'fields': [], 'guards': [], 'raw_guards': [], 'virtual_guards': [], 'exports': [], 'entry_paths': [], 'reference_gaps': []}
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
                if 'rva' in row and ('slot_entry_rvas' in row or 'vtable_guards' in path):
                    try:
                        count = len(row['slot_entry_rvas']) if isinstance(row.get('slot_entry_rvas'), list) else None
                        add_table(alias, number(row['rva']), count, relative + pointer(path))
                    except (ValueError, TypeError):
                        pass
            if alias and 'rva' in row and isinstance(row.get('ordinal'), int):
                try:
                    export_rva = number(row['rva']);ordinal = number(row['ordinal'])
                    exported = modules[alias].exports_by_ordinal.get(ordinal)
                    if exported and exported['rva'] == export_rva and not exported.get('forwarder'):
                        item['exports'].append({'json_pointer': pointer(path), 'module': alias, 'reference_rva': export_rva,
                            'reference_ordinal': ordinal, 'names': [n for n, e in modules[alias].exports.items()
                                if not n.startswith('#') and e['ordinal'] == ordinal]})
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
                    owner = field_hints.get(pointer(path + (key,)), alias)
                    if key.lower().endswith('iat_rva'):
                        owners = [m for m, pe in modules.items() if value_rva in pe.imports_by_iat]
                        owner = owner if owner in owners else owners[0] if len(owners) == 1 else None
                        if owner:
                            imported = modules[owner].imports_by_iat[value_rva]
                            target_module = _module_alias(imported['dll'], modules)
                            imported_export = modules[target_module].exports_by_ordinal.get(imported['ordinal']) if target_module and imported.get('ordinal') is not None else None
                            import_slots[owner, value_rva] = {'module': owner, 'reference_rva': value_rva,
                                'dll': imported['dll'], 'name': imported.get('name'), 'ordinal': imported.get('ordinal'),
                                'target_module': target_module,
                                'reference_target_rva': imported_export['rva'] if imported_export and not imported_export.get('forwarder') else None}
                    item['fields'].append({'json_pointer': pointer(path + (key,)), 'module': owner,
                        'kind': 'IAT-slot' if key.lower().endswith('iat_rva') else 'rva', 'reference_rva': value_rva})
                elif key.endswith('_rvas') and isinstance(value, list):
                    for index, entry in enumerate(value):
                        try: value_rva = number(entry)
                        except (ValueError, TypeError, OverflowError): continue
                        item['fields'].append({'json_pointer': pointer(path + (key, index)), 'module': alias,
                            'kind': 'rva', 'reference_rva': value_rva})
            if path and len(path) == 2 and path[0] in ('functions', 'vtable_guards'):
                item['entry_paths'].append({'json_pointer': prefix, 'name': row.get('name')})
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
    return {'schema': CATALOG_SCHEMA, 'catalog_scope': 'sparse selected guards and RTTI; no vendor sections',
        'normalization': {'architecture': 'PE32/I386', 'decoder': 'capstone', 'decoder_version_observed': xs.DECODER_VERSION,
            'HIGHLOW': 'PE relocation entries only', 'relative_calls_and_jumps': 'decoded operands plus target/body/import proof',
            'ordinary_object_displacements': 'exact; never wildcarded', 'whole_file_sha_admission': False},
        'reference_modules': {alias: {**pe.identity(), 'basename': pe.path.name if pe.path else None, **module_metadata[alias]} for alias, pe in modules.items()}, 'profiles': profiles,
        'signatures': list(signatures.values()), 'types': list(types.values()), 'explicit_addresses': explicit_addresses,
        'profile_field_module_declarations': owner_document, 'import_slots': list(import_slots.values()), 'catalog_gaps': gaps}


def resolve_catalog(catalog, actual_modules, *, reference_modules=None, prefer_content_cache=True):
    if catalog.get('schema') != CATALOG_SCHEMA:
        raise ValueError('Unsupported reference catalog schema')
    actual = _modules(actual_modules)
    reference = _modules(reference_modules) if reference_modules else {}
    identities = {alias: pe.identity() for alias, pe in actual.items()}
    equal_modules = {alias for alias in actual if alias in catalog['reference_modules'] and
        identities[alias]['sha256'] == catalog['reference_modules'][alias]['sha256']}
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
        'local_actual_module_paths': {alias: str(Path(path).resolve()) for alias, path in actual_modules.items()}}
    suggestions, anchors = {}, {}

    def suggest(alias, old, new, kind, proof_id):
        key = (alias, int(old));value = suggestions.setdefault(key, {})
        value.setdefault(int(new), []).append({'kind': kind, 'proof_id': proof_id})

    def complete_function(row, entry, current, context, method):
        alias, old, identifier = entry['module'], entry['reference_rva'], entry['id']
        pe = actual[alias]
        canonical, reloc = xs.normalized_guard_bytes(pe, current, entry['guard_length'], catalog['reference_modules'][alias]['image_base'])
        raw = pe.read(current, entry['guard_length'])
        row.update(status='resolved', actual_rva=current,
            actual_guard_bytes=raw.hex(), guard_bytes_at_reference_preferred_base=canonical.hex(),
            actual_relocation_offsets=reloc, proof_id=identifier, resolution_method=method,
            identity_anchors={'RTTI_slot': bool(anchors.get((alias, old))), 'named_export': entry.get('exports', [])},
            normalization=context['normalization_proofs'])
        result['proofs'].append({'id': identifier, 'kind': method, 'module': alias,
            'reference_rva': old, 'actual_rva': current, 'object_displacements_preserved': True,
            'normalization': context['normalization_proofs']})
        suggest(alias, old, current, 'function', identifier)
        for ref in context['referents']:
            suggest(alias, ref['reference_rva'], ref['actual_rva'], ref['kind'], identifier)

    type_cache = {}
    for entry in catalog['types']:
        alias, old = entry['module'], entry['reference'];proof_id = entry['id']
        if alias not in actual:
            result['types'].append({'id': proof_id, 'module': alias, 'status': 'unresolved', 'reason': 'Actual module not supplied'});continue
        key = (alias, old['decorated_name'])
        if prefer_content_cache and alias in equal_modules:
            exact, different = [copy.deepcopy(old)], []
        else:
            if key not in type_cache:
                type_cache[key] = rtti.locate_type(actual[alias], old['decorated_name'])
            exact, different = rtti.pair_table(old, type_cache[key]['tables'])
        if len(exact) != 1:
            result['types'].append({'id': proof_id, 'module': alias, 'status': 'ambiguous' if len(exact) > 1 else 'unresolved',
                'decorated_name': old['decorated_name'], 'reference_vtable_rva': old['vtable_rva'],
                'candidate_vtable_rvas': [t['vtable_rva'] for t in exact],
                'observed_layout_differences': [{'vtable_rva': t['vtable_rva'], 'col_offset': t['col_offset'], 'hierarchy': t['hierarchy']} for t in different],
                'reason': 'Exact RTTI class/interface role and existing hierarchy layout is not unique'});continue
        new = exact[0]
        if len(new['slot_entry_rvas']) < len(old['slot_entry_rvas']):
            result['types'].append({'id': proof_id, 'module': alias, 'status': 'unresolved', 'reason': 'Actual table has fewer executable slots than the published contract'});continue
        proof = {'id': proof_id, 'kind': 'RTTI-class-COL-hierarchy-vtable', 'module': alias,
            'decorated_name': old['decorated_name'], 'reference': old, 'actual': new}
        result['proofs'].append(proof)
        result['types'].append({'id': proof_id, 'module': alias, 'status': 'resolved', 'reference': old, 'actual': new})
        for before, after, kind in rtti.address_pairs(old, new):
            suggest(alias, before, after, kind, proof_id)
        for before, after in zip(old['slot_entry_rvas'], new['slot_entry_rvas']):
            anchors.setdefault((alias, before), set()).add(after)
            if prefer_content_cache and alias in equal_modules:
                continue
            # Published virtual slots often point at E9 entry thunks, while
            # named profile functions refer to their bodies. Preserve that
            # composite identity instead of treating a generic body as unique.
            slot_signature = next((s for s in catalog['signatures'] if s['module'] == alias and s['reference_rva'] == before), None)
            if slot_signature and slot_signature['first_is_direct_thunk']:
                transfer = slot_signature['transfers'][0]
                parts = [slot_signature] + transfer.get('target_signature_chain', [])
                cursor = after;chain_pairs = [];valid = transfer.get('target_context_status') == 'complete'
                for part in parts:
                    matched = xs.local_match(part, actual[alias], cursor)
                    if matched is None:
                        valid = False;break
                    context = xs.verify_context(None, actual[alias], part, matched, part['reference_rva'], cursor, verify_targets=False)
                    if context is None:
                        valid = False;break
                    chain_pairs.append((part['reference_rva'], cursor))
                    if part['first_is_direct_thunk']:
                        cursor = matched['transfers'][0]['reference_target_rva']
                if valid:
                    for source, target in chain_pairs:
                        anchors.setdefault((alias, source), set()).add(target)

    pending = []
    for entry in catalog['signatures']:
        alias, old, identifier = entry['module'], entry['reference_rva'], entry['id']
        row = {'id': identifier, 'module': alias, 'reference_rva': old, 'names': entry.get('names', [])}
        if alias not in actual:
            row.update(status='unresolved', reason='Actual module not supplied');result['functions'].append(row);continue
        pe = actual[alias]
        role_anchors = set(anchors.get((alias, old), set()))
        export_anchors = [pe.exports[name]['rva'] for name in entry.get('exports', [])
                          if name in pe.exports and not pe.exports[name].get('forwarder')]
        if export_anchors:
            role_anchors = role_anchors.intersection(export_anchors) if role_anchors else set(export_anchors)
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
        matches = []
        for candidate in candidates:
            matched = xs.local_match(entry, pe, candidate)
            if matched is None:
                continue
            context = xs.verify_context(reference.get(alias), pe, entry, matched, old, candidate)
            if context is None:
                continue
            matches.append((candidate, context))
        if len(matches) != 1:
            row.update(status='ambiguous' if len(matches) > 1 else 'missing',
                candidate_rvas=[v[0] for v in matches], candidates_examined=len(candidates),
                reason='Normalized instruction/body/RTTI/export proof is not unique' if matches else
                    'No instruction-aware candidate preserves the reference contract; ordinary field offsets were not masked')
            result['functions'].append(row);pending.append((row, entry));continue
        current, context = matches[0]
        row['candidates_examined'] = len(candidates)
        complete_function(row, entry, current, context, 'decoded-x86-function')
        result['functions'].append(row)
    # A uniquely identified caller's same decoded CALL/absolute operand can
    # constrain a generic callee. Iterate the proof graph, without old-RVA bias.
    progress = True
    while progress:
        progress = False
        for row, entry in pending:
            if row['status'] == 'resolved':
                continue
            alias, old = entry['module'], entry['reference_rva']
            values = suggestions.get((alias, old), {})
            if len(values) != 1:
                continue
            current = next(iter(values))
            if not actual[alias].is_executable(current):
                continue
            matched = xs.local_match(entry, actual[alias], current)
            context = xs.verify_context(None, actual[alias], entry, matched, old, current) if matched else None
            if context is None:
                continue
            complete_function(row, entry, current, context, 'unique-decoded-callgraph-referent')
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
        entries = [(rva, row) for rva, row in actual[alias].imports_by_iat.items()
                   if row['dll'].lower() == imported['dll'].lower()]
        candidates = []
        if imported.get('name') is not None:
            candidates = [rva for rva, row in entries if row.get('name') == imported['name']]
        elif imported.get('target_module') in equal_modules:
            candidates = [rva for rva, row in entries if row.get('ordinal') == imported['ordinal']]
        elif imported.get('target_module') in actual and imported.get('reference_target_rva') is not None:
            target = imported['target_module'];mapped = suggestions.get((target, imported['reference_target_rva']), {})
            if len(mapped) == 1:
                target_rva = next(iter(mapped))
                candidates = [rva for rva, row in entries if row.get('ordinal') is not None and
                    actual[target].exports_by_ordinal.get(row['ordinal'], {}).get('rva') == target_rva]
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
        'all_code_locations_resolved': all(f['status'] == 'resolved' for f in result['functions'])}
    return result


def write_resolved_profiles(catalog, result, output_dir, *, profile_root):
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
    actual_pes = {}
    for profile in catalog['profiles']:
        source = (root / profile['relative_path']).resolve()
        if not source.is_relative_to(root) or digest(source.read_bytes()) != profile['reference_sha256']:
            raise ValueError('Reference profile source changed: ' + profile['relative_path'])
        document = json.loads(source.read_text('utf-8-sig'))
        record = {'relative_path': profile['relative_path'], 'reference_sha256': profile['reference_sha256'],
            'resolved_relative_path': profile['relative_path'], 'resolved_fields': [], 'unresolved_fields': [], 'entry_resolutions': []}
        record['unresolved_fields'].extend(copy.deepcopy(profile.get('reference_gaps', [])))
        for field in profile['fields']:
            alias, old = field.get('module'), field['reference_rva'];path = field['json_pointer']
            mapping = result['rva_maps'].get(alias, {}).get(hex(old))
            if mapping is None:
                record['unresolved_fields'].append({'json_pointer': path, 'module': alias, 'reference_rva': old,
                    'reason': 'No unique current PE address proof; retained reference value is not an actual address'})
                continue
            original = get_at(document, path)
            set_at(document, path, _format_number(original, mapping['actual_rva']))
            record['resolved_fields'].append({'json_pointer': path, 'module': alias, 'reference_rva': old,
                'actual_rva': mapping['actual_rva'], 'proof_id': mapping['proof_id']})
        for guard in profile['guards']:
            located = functions.get(guard['guard_id'])
            if not located or located['status'] != 'resolved':
                record['unresolved_fields'].append({'json_pointer': guard['json_pointer'] + '/' + guard['byte_key'],
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
            canonical, offsets = xs.normalized_guard_bytes(actual_pes[alias], mapping['actual_rva'], guard['length'], catalog['reference_modules'][alias]['image_base'])
            row = get_at(document, guard['json_pointer']);row[guard['byte_key']] = canonical.hex()
            for key in guard['relocation_keys']:
                row[key] = offsets
        for export in profile.get('exports', []):
            alias, old = export['module'], export['reference_rva']
            path = export['json_pointer'];mapping = result['rva_maps'].get(alias, {}).get(hex(old))
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
                get_at(document, path)['ordinal'] = candidates[0]
                record['resolved_fields'].append({'json_pointer': path + '/ordinal', 'module': alias,
                    'reference_ordinal': export['reference_ordinal'], 'actual_ordinal': candidates[0],
                    'proof_id': mapping['proof_id'], 'proof_kind': 'resolved-function-and-current-export-table'})
            else:
                record['unresolved_fields'].append({'json_pointer': path + '/ordinal', 'module': alias,
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
        for entry in profile['entry_paths']:
            prefix = entry['json_pointer']
            details = [u for u in record['unresolved_fields'] if u['json_pointer'] == prefix or u['json_pointer'].startswith(prefix + '/')]
            resolved = [r for r in record['resolved_fields'] if r['json_pointer'].startswith(prefix + '/')]
            state = {'status': 'unresolved' if details else 'resolved', 'details': details,
                     'proof_ids': sorted({r['proof_id'] for r in resolved})}
            get_at(document, prefix)['_abi_resolution'] = state
            record['entry_resolutions'].append({'json_pointer': prefix, 'name': entry['name'], **state})
        record['status'] = 'resolved' if not record['unresolved_fields'] else 'partial' if record['resolved_fields'] else 'unresolved'
        document['_mcgs_abi_resolution'] = {'schema': ATTESTATION_SCHEMA, 'status': record['status'],
            'reference_sha256': profile['reference_sha256'], 'unresolved_fields': record['unresolved_fields'],
            'retained_unresolved_values_are_reference_only': True, 'guard_bytes_preferred_base_policy': 'reference module preferred base'}
        target = (out / profile['relative_path']).resolve()
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
