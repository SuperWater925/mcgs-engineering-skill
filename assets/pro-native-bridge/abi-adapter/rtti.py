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


def _role_bases(model):
    """Read the actual PMD roles, accepting the compact operand-anchor form."""
    values = model.get('hierarchy', {}).get('bases', model.get('bases', []))
    rows = []
    for value in values:
        if isinstance(value, dict):
            row = value
        elif isinstance(value, (tuple, list)) and len(value) == 4:
            row = {'decorated_name': value[0], 'contained': value[1],
                   'pmd': value[2], 'attributes': value[3]}
        else:
            return []
        pmd = row.get('pmd')
        if not isinstance(pmd, (tuple, list)) or len(pmd) != 3:
            return []
        rows.append({'decorated_name': row.get('decorated_name'), 'pmd': list(pmd),
                     'attributes': row.get('attributes')})
    return rows


def table_role_proof(reference, actual):
    """Identify one unchanged table subobject without requiring unrelated bases.

    A stable class name alone is insufficient.  The COL and constructor offsets,
    self PMD and flags must match.  A secondary table additionally needs an
    explicit unchanged nonvirtual base role at that COL offset.  Virtual-base
    roles which cannot be derived from these records retain the exact-hierarchy
    path.  This proves table identity, never private member layout or every slot.
    """
    name = reference.get('decorated_name')
    if not name or actual.get('decorated_name') != name:
        return None
    if ('constructor_displacement_offset' not in reference or
            'constructor_displacement_offset' not in actual):
        return None
    if (actual.get('col_offset') != reference.get('col_offset') or
            actual['constructor_displacement_offset'] != reference['constructor_displacement_offset']):
        return None
    before, after = _role_bases(reference), _role_bases(actual)
    old_self = [row for row in before if row['decorated_name'] == name]
    new_self = [row for row in after if row['decorated_name'] == name]
    if len(old_self) != 1 or new_self != old_self:
        return None
    required = old_self[:]
    offset = reference.get('col_offset')
    if offset != 0:
        # mdisp is a complete subobject offset only when pdisp=-1.  Do not
        # reinterpret virtual PMDs or the hierarchy's row order as that role.
        old_roles = [row for row in before
                     if row['decorated_name'] != name and row['pmd'][0] == offset and row['pmd'][1] == -1]
        stable = [row for row in old_roles if after.count(row) == 1]
        if not stable:
            return None
        required.extend(stable)
    return {'kind': 'RTTI-stable-table-subobject-role', 'decorated_name': name,
            'col_offset': offset,
            'constructor_displacement_offset': reference['constructor_displacement_offset'],
            'required_base_roles': required,
            'unrelated_hierarchy_rows_not_required': True,
            'private_object_fields_verified': False, 'virtual_slots_verified': False}


def anchor_role_proof(reference, actual):
    """The same role check for decoded RTTI-pointer operands."""
    if not isinstance(reference, dict) or not isinstance(actual, dict):
        return None
    return table_role_proof(reference, actual)


def pair_table_roles(reference, actual_tables):
    compatible, differing = [], []
    for row in actual_tables:
        (compatible if table_role_proof(reference, row) else differing).append(row)
    return compatible, differing


def role_address_pairs(reference, actual):
    """Map only addresses belonging to the proven role, never zipped bases.

    A changed hierarchy has a different record/array layout.  Its addresses are
    deliberately not promoted to a whole-hierarchy proof.  A consumer needing
    those arrays must independently adapt the fields it actually uses.
    """
    if table_role_proof(reference, actual) is None:
        return []
    pairs = [(reference[key], actual[key], key)
             for key in ('type_descriptor_rva', 'col_rva', 'vtable_rva')]
    for old in reference['hierarchy']['bases']:
        matching = [new for new in actual['hierarchy']['bases']
                    if new['decorated_name'] == old['decorated_name'] and
                    new['pmd'] == old['pmd'] and new['attributes'] == old['attributes']]
        if len(matching) == 1:
            # contained counts describe the changed subtree, not the identity
            # of its type descriptor.  Do not map its BCD record by this proof.
            pairs.append((old['type_descriptor_rva'], matching[0]['type_descriptor_rva'], 'stable-base-type-descriptor'))
    return pairs


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
