"""Edit the file-backed MCGS picture library and its typed window references."""
import copy
import json
import re
import struct
from pathlib import Path

from native_format import archive, wrap_like
from mcs_window_archive import Reader, WindowArchive, write_cstring
from mcs_button_control import ButtonArchive, CString
from mcgs_text import narrow_encoding
from picture_resources import Picture, PictureResource, exact_factory_vector, image_hex, line_vector, rectangle_vector, shape_vector
from 原生界面样式 import CommonEnvelope, GroupArchive, MultiState
from control_patch import edit

LIST = 'MCGS_PICTURE_LIST'
PREFIX = 'MCGS_PICTURE_DATA_'
MANAGER = 'MCGS_PICTURE_MANAGER_INFO'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def name_value(name):
    require(isinstance(name, str) and name and '\0' not in name, 'Invalid picture name')
    return name


def library(rows):
    indexed = {}
    listings = []
    for row in rows:
        key = row['strName']
        if not isinstance(key, str):
            continue
        if key.casefold() == LIST.casefold():
            require(key == LIST, 'Unexpected picture index key casing')
            listings.append(row)
        if key.casefold().startswith(PREFIX.casefold()):
            suffix = key[len(PREFIX):]
            require(re.fullmatch(r'0|[1-9][0-9]*', suffix) and key.startswith(PREFIX)
                    and int(suffix) not in indexed, 'Ambiguous picture data key')
            indexed[int(suffix)] = row
    require(len(listings) <= 1, 'Multiple picture indexes')
    if not listings:
        require(not indexed, 'Picture data without an index')
        return None, [], []
    listing = listings[0]
    plain = archive(listing['lbContext'])
    reader = Reader(plain)
    count = reader.u32()
    require(count == len(indexed) and set(indexed) == set(range(count)), 'Picture index/data count or order differs')
    names = [CString.parse(reader) for _ in range(count)]
    trailer = reader.take(4)
    require(reader.pos == len(plain), 'Unrecognized picture index trailer')
    require(index_bytes(names, trailer=trailer) == plain, 'Picture index does not round-trip')
    resources = [PictureResource.parse(archive(indexed[i]['lbContext'])) for i in range(count)]
    require(all(name_value(n.value) == q.name.value for n, q in zip(names, resources)), 'Picture index/data names differ')
    require(len({n.value.casefold() for n in names}) == count, 'Ambiguous picture names')
    return listing, names, resources


def index_bytes(names, *, trailer=None):
    count = struct.pack('<I', len(names))
    return count + b''.join(n.to_bytes() for n in names) + (count if trailer is None else trailer)


def native_row(data, key, value):
    system = data['System']
    fields = {f['name']: f for f in system['fields']}
    require(set(fields) == {'iID', 'strName', 'lbContext'} and fields['iID']['type'] == 3
            and fields['iID'].get('auto_increment') is True and fields['lbContext']['type'] == 205
            and fields['strName']['type'] in (130, 202) and len(key) <= fields['strName']['size'],
            'Unrecognized System picture row schema')
    ids = [row['iID'] for row in system['rows']]
    require(all(type(i) is int for i in ids) and len(set(ids)) == len(ids), 'Ambiguous System identities')
    new_id = max(ids, default=0) + 1
    require(0 < new_id < 2**31, 'No available System LONG identity')
    row = {'iID': new_id, 'strName': key, 'lbContext': value}
    system['rows'].append(row)
    return row


def mentions(raw, old):
    # Decoding both UTF-16 alignments also detects non-canonical CString lengths
    # and case variants in a larger opaque record. False positives block writes.
    target = old.casefold()
    return (target in raw.decode(narrow_encoding(), errors='replace').casefold()
            or target in raw.decode('utf-8', errors='replace').casefold()
            or any(target in raw[i:].decode('utf-16le', errors='replace').casefold() for i in (0, 1)))


def matching(picture, old):
    if not picture:
        return False
    q = Picture.parse(picture)
    return q.mode == 0x80 and q.reference.value.casefold() == old.casefold()


def rewrite_record(record, old, new):
    if not mentions(record.payload, old):
        return record
    if record.type_id == 0x503a:
        group = GroupArchive.parse(record)
        group.children[:] = [rewrite_record(child, old, new) for child in group.children]
        return group.to_record()
    changes = {}
    if record.type_id == 0x5027:
        common = CommonEnvelope.parse(record)
        button = ButtonArchive.parse(common.project_without_animations())
        slots = {slot: {'reference': new} for slot, raw in (
            ('primary', button.picture), ('properties', button.metadata.properties.picture)) if matching(raw, old)}
        if slots:
            changes['button_pictures'] = slots
    if record.type_id in (0x5028, 0x502a):
        states = []
        for state, children in enumerate(MultiState.parse(record).images):
            images = [{'child': i, 'picture': {'reference': new}} for i, child in enumerate(children)
                      if matching(child.picture, old)]
            if images:
                states.append({'state': state, 'images': images})
        if states:
            changes['state_edits'] = states
    return edit(record, changes, picture_references={new}) if changes else record


def rewrite_window(raw, old, new):
    window = WindowArchive.parse(raw)
    require(window.to_bytes() == raw, 'Window archive does not round-trip')
    window.controls[:] = [rewrite_record(record, old, new) for record in window.controls]
    result = window.to_bytes()
    require(WindowArchive.parse(result).to_bytes() == result, 'Changed window archive does not round-trip')
    return result


def check_references(data, old, new, resources):
    for table, content in data.items():
        for row in content['rows']:
            key = row.get('strName')
            for field, value in row.items():
                if table == 'System' and field == 'lbContext' and isinstance(key, str) and (key == LIST or key.startswith(PREFIX)):
                    if key == LIST:
                        continue
                    # DATA name and identity are structural fields. Inspect the payload separately.
                    resource = resources[int(key[len(PREFIX):])]
                    require(not mentions(resource.payload, old), 'Picture referenced by an opaque library resource')
                    continue
                if isinstance(value, str):
                    require(old.casefold() not in value.casefold(), f'Possible text reference in {table}.{field}')
                if not isinstance(value, dict) or 'binary' not in value:
                    continue
                raw = archive(value)
                if not mentions(raw, old):
                    continue
                require(new is not None and table == 'WndUser' and field == 'lbObjects',
                        f'Picture reference requires resolution in {table}.{field}')
                # Remove known references in a disposable projection and rescan
                # for residual mentions independently of the requested new name.
                probe = '\ue001' if old == '\ue000' else '\ue000'
                require(not mentions(rewrite_window(raw, old, probe), old),
                        'Window contains an additional opaque picture reference')
                row[field] = wrap_like(value, rewrite_window(raw, old, new))


def require_unreferenced_slots(data, resources):
    """Prove the non-library projection is an original project with an empty library."""
    from mcgs_file import canonical, project_family
    family = project_family(data)
    templates = {"Stu": "blank-project-stu.json", "Pro": "blank-project.json"}
    original = json.loads((Path(__file__).resolve().parents[1] / "assets" / templates[family])
                          .read_text(encoding="utf-8-sig"))
    identities = set()
    for resource in resources:
        identity = resource.identity.value.casefold()
        require(re.fullmatch(r'[0-9a-f]{32}', identity) and identity not in identities,
                'Slot renumbering requires unique native picture identities')
        if resource.kind in (0, 2):
            resource.validate_raster()
        else:
            require(resource.kind == 16 and exact_factory_vector(resource, family),
                    'Slot renumbering requires independent native rasters or exact factory shape vectors')
        identities.add(identity)
    rows = data['System']['rows']
    require(len({r['iID'] for r in rows}) == len(rows), 'Ambiguous System identities')
    managers = [r for r in rows if r['strName'] == MANAGER]
    require(len(managers) == 1 and archive(managers[0]['lbContext']) == struct.pack('<II', 0, 1),
            'Unsupported picture manager for slot renumbering')
    has_original_manager = any(r['strName'] == MANAGER for r in original['System']['rows'])
    others = [r for r in rows if r['strName'] != LIST and not str(r['strName']).startswith(PREFIX)
              and (r['strName'] != MANAGER or has_original_manager)]
    projected = dict(data, System=dict(data['System'], rows=others))
    require(canonical(projected) == canonical(original),
            'Nonterminal deletion requires the original empty-project records outside the picture library')


def edit_picture_library(data, actions):
    require(isinstance(actions, list) and actions, 'picture_library requires a nonempty action array')
    staged = dict(data)
    for table in ('System', 'WndUser'):
        staged[table] = copy.deepcopy(data[table])
    rows = staged['System']['rows']
    listing, names, resources = library(rows)
    trailer = None
    if listing is not None:
        original_trailer = archive(listing['lbContext'])[-4:]
        # An original native import can keep this separate word unchanged.
        # Decide from the initial index so an equality crossing within the
        # edit cannot turn its original trailer into a count mirror.
        if int.from_bytes(original_trailer, 'little') != len(names):
            trailer = original_trailer
    for action in actions:
        require(isinstance(action, dict), 'Expected a picture action')
        op = action.get('action')
        keys = {'add': {'action', 'name', 'resource_hex'}, 'rename': {'action', 'name', 'new_name'},
                'delete': {'action', 'name'}}
        raw_add = op == 'add' and set(action) == {'action', 'name', 'image_hex'}
        rectangle_fields = {'action', 'name', 'bounds'}
        line_fields = rectangle_fields | {'endpoints'}
        rectangle_add = op == 'add-vector-rectangle' and rectangle_fields <= set(action) <= rectangle_fields | {'fill', 'border'}
        line_add = op == 'add-vector-line' and line_fields <= set(action) <= line_fields | {'border'}
        shapes_add = op == 'add-vector-shapes' and set(action) == rectangle_fields | {'shapes'}
        vector_add = rectangle_add or line_add or shapes_add
        require(raw_add or vector_add or (isinstance(op, str) and op in keys and set(action) == keys[op]),
                'Invalid picture action fields')
        name = name_value(action['name'])
        positions = {n.value.casefold(): i for i, n in enumerate(names)}
        if op == 'add' or vector_add:
            require(name.casefold() not in positions, 'Picture name already exists')
            if vector_add:
                from mcgs_file import project_family
                family = project_family(staged)
                colors = {key: action[key] for key in ('fill', 'border') if key in action}
                if shapes_add:
                    q = shape_vector(family, name, action['bounds'], action['shapes'])
                elif line_add:
                    q = line_vector(family, name, action['bounds'], action['endpoints'], colors)
                else:
                    q = rectangle_vector(family, name, action['bounds'], colors)
            elif raw_add:
                q = PictureResource.from_raster(name, image_hex(action['image_hex']))
            else:
                q = PictureResource.parse(image_hex(action['resource_hex']))
            if not vector_add:
                require(re.fullmatch('[0-9A-Fa-f]{32}', q.identity.value), 'Expected native raster resource identity')
                if not raw_add:
                    q.validate_raster()
            for existing in resources:
                if q.identity.value.casefold() == existing.identity.value.casefold():
                    # The original editor can import identical files under
                    # distinct names with the same content digest.
                    same_content = ((q.kind, q.width, q.height, q.payload)
                                    == (existing.kind, existing.width, existing.height, existing.payload))
                    require(raw_add and same_content, 'Picture identity already exists')
            q.name.value = name
            if listing is None:
                manager = [r for r in rows if r.get('strName') == MANAGER]
                if not manager:
                    # The blank Pro create template omits the picture module
                    # until first use. Both native families use this same
                    # manager payload, independent of the number of images.
                    donor, = [r for r in rows if r.get('strName') == 'ObjData']
                    manager = [native_row(staged, MANAGER, wrap_like(donor['lbContext'], struct.pack('<II', 0, 1)))]
                require(len(manager) == 1 and archive(manager[0]['lbContext']) == struct.pack('<II', 0, 1),
                        'First picture requires the recognized empty native picture manager')
                listing = native_row(staged, LIST, wrap_like(manager[0]['lbContext'], index_bytes([])))
            exemplar = (next(r['lbContext'] for r in rows if r['strName'] == PREFIX + '0')
                        if names else listing['lbContext'])
            native_row(staged, PREFIX + str(len(names)), wrap_like(exemplar, q.to_bytes()))
            names.append(CString.parse(Reader(write_cstring(name, q.name.wide))))
        else:
            require(name.casefold() in positions, 'Picture name does not exist')
            i = positions[name.casefold()]
            require(names[i].value == name, 'Picture preimage name casing differs')
            row = next(r for r in rows if r['strName'] == PREFIX + str(i))
            if op == 'rename':
                new = name_value(action['new_name'])
                require(new != name and positions.get(new.casefold(), i) == i, 'Picture name unchanged or occupied')
                check_references(staged, name, new, resources)
                names[i].value = resources[i].name.value = new
                row['lbContext'] = wrap_like(row['lbContext'], resources[i].to_bytes())
            else:
                if i < len(names) - 1:
                    require_unreferenced_slots(staged, resources)
                check_references(staged, name, None, resources)
                if resources[i].identity.value:
                    check_references(staged, resources[i].identity.value, None, resources)
                rows.remove(row)
                names.pop(i)
                for slot in range(i + 1, len(resources)):
                    survivor = next(r for r in rows if r['strName'] == PREFIX + str(slot))
                    survivor['strName'] = PREFIX + str(slot - 1)
        listing['lbContext'] = wrap_like(listing['lbContext'], index_bytes(names, trailer=trailer))
        listing, names, resources = library(rows)
    for table in ('System', 'WndUser'):
        data[table] = staged[table]
