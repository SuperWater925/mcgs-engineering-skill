"""Read-only MSVC x86 RTTI discovery from a PE's actual class names/relocations."""
from __future__ import annotations
import struct


def _rva(pe, value):
    return pe.va_to_rva(value)


def _td_name(pe, rva):
    pe.read(rva, 8)
    name = pe.cstring(rva + 8)
    if not name.startswith(('.?AV', '.?AU')) or not name.endswith('@@'):
        raise ValueError('Not a complete MSVC x86 decorated class type descriptor')
    return name


def hierarchy(pe, rva):
    signature, attributes, count, array_va = struct.unpack('<4I', pe.read(rva, 16))
    if signature != 0 or count == 0:
        raise ValueError('Unsupported MSVC x86 class hierarchy signature/count')
    array = _rva(pe, array_va)
    raw = pe.read(array, count * 4)
    pointers = struct.unpack('<' + 'I' * count, raw)
    bases = []
    for pointer in pointers:
        descriptor = _rva(pe, pointer)
        td, contained, mdisp, pdisp, vdisp, flags = struct.unpack('<IIiiiI', pe.read(descriptor, 24))
        td_rva = _rva(pe, td)
        bases.append({'descriptor_rva': descriptor, 'type_descriptor_rva': td_rva,
                      'decorated_name': _td_name(pe, td_rva), 'contained': contained,
                      'pmd': [mdisp, pdisp, vdisp], 'attributes': flags})
    return {'rva': rva, 'signature': signature, 'attributes': attributes,
            'base_array_rva': array, 'bases': bases}


def describe_vtable(pe, table_rva, slot_count=None):
    col = _rva(pe, pe.u32(table_rva - 4))
    signature, offset, cd_offset, td_va, hierarchy_va = struct.unpack('<5I', pe.read(col, 20))
    if signature != 0 or col + 12 not in pe.relocations:
        raise ValueError('COL is not a relocatable MSVC x86 absolute-pointer record')
    td, h = _rva(pe, td_va), _rva(pe, hierarchy_va)
    name = _td_name(pe, td)
    tree = hierarchy(pe, h)
    entries = []
    if slot_count is None:
        section = pe.section_for_rva(table_rva)
        maximum = (section.raw_size - (table_rva - section.rva)) // 4
    else:
        maximum = slot_count
    for index in range(maximum):
        va = pe.u32(table_rva + index * 4)
        try:
            target = _rva(pe, va)
        except ValueError:
            if slot_count is not None:
                raise ValueError('A requested vtable slot is not inside its PE module')
            break
        if not pe.is_executable(target):
            if slot_count is not None:
                raise ValueError('A requested vtable slot is not an executable entry')
            break
        entries.append(target)
    if not entries:
        raise ValueError('No executable slots in the candidate vtable')
    return {'decorated_name': name, 'type_descriptor_rva': td, 'col_rva': col,
            'col_offset': offset, 'constructor_displacement_offset': cd_offset,
            'vtable_rva': table_rva, 'slot_entry_rvas': entries, 'hierarchy': tree}


def _pointer_xrefs(pe, target_rva):
    value = struct.pack('<I', pe.image_base + target_rva)
    return [rva for rva in pe.find_bytes(value, executable=False) if rva in pe.relocations]


def locate_type(pe, decorated_name, slot_counts=()):
    """Find exact class names, then validated COL backlinks and vtable prefixes."""
    names = pe.find_bytes(decorated_name.encode('ascii') + b'\0', executable=False)
    descriptors = []
    for string_rva in names:
        td = string_rva - 8
        try:
            if pe.u32(td + 4) == 0 and _td_name(pe, td) == decorated_name:
                descriptors.append(td)
        except ValueError:
            pass
    tables = []
    for td in descriptors:
        for site in _pointer_xrefs(pe, td):
            col = site - 12
            try:
                signature, offset, cd, type_va, h = struct.unpack('<5I', pe.read(col, 20))
                if signature != 0 or type_va != pe.image_base + td:
                    continue
                hierarchy(pe, _rva(pe, h))
                for prefix in _pointer_xrefs(pe, col):
                    table = prefix + 4
                    try:
                        model = describe_vtable(pe, table)
                    except ValueError:
                        continue
                    if model['col_rva'] == col and model not in tables:
                        tables.append(model)
            except (ValueError, struct.error):
                continue
    return {'decorated_name': decorated_name, 'type_descriptor_candidates': sorted(set(descriptors)),
            'tables': sorted(tables, key=lambda row: (row['col_offset'], row['vtable_rva']))}


def pair_table(reference, actual_tables):
    """A primary/interface table role includes its COL offset and hierarchy.

    These offsets are observed layout contracts, not wildcarded object fields.
    A changed layout is reported instead of silently choosing another interface.
    """
    reference_bases = [(b['decorated_name'], b['contained'], b['pmd'], b['attributes'])
                       for b in reference['hierarchy']['bases']]
    exact, differing = [], []
    for row in actual_tables:
        bases = [(b['decorated_name'], b['contained'], b['pmd'], b['attributes']) for b in row['hierarchy']['bases']]
        same = (row['col_offset'] == reference['col_offset'] and
                row['constructor_displacement_offset'] == reference['constructor_displacement_offset'] and
                row['hierarchy']['attributes'] == reference['hierarchy']['attributes'] and bases == reference_bases)
        (exact if same else differing).append(row)
    return exact, differing


def address_pairs(reference, actual):
    pairs = []
    for key in ('type_descriptor_rva', 'col_rva', 'vtable_rva'):
        pairs.append((reference[key], actual[key], key))
    pairs += [(reference['hierarchy']['rva'], actual['hierarchy']['rva'], 'hierarchy_rva'),
              (reference['hierarchy']['base_array_rva'], actual['hierarchy']['base_array_rva'], 'base_array_rva')]
    for old, new in zip(reference['hierarchy']['bases'], actual['hierarchy']['bases']):
        for key in ('descriptor_rva', 'type_descriptor_rva'):
            pairs.append((old[key], new[key], key))
    return pairs
