"""Structural mutations of project archives selected for offline editing."""
from __future__ import annotations

import hashlib
import re
import math
import struct

import native_format as native
from mcs_button_control import CString
from mcs_window_archive import Reader, WindowArchive, WindowSettings
from 窗口事件归档 import 读取公共窗口槽


def key(value):
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ValueError("Expected a nonempty native object name")
    return value.casefold()


def exact(row, fields, purpose):
    if not isinstance(row, dict) or set(row) != set(fields):
        raise ValueError(purpose + " requires " + ", ".join(fields))


def control_index(records, selector):
    exact(selector, ("index", "type_id", "name", "sha256"), "Control identity")
    index = selector["index"]
    if type(index) is not int or not 0 <= index < len(records):
        raise ValueError("Control index is outside the current page")
    kind, body = records[index]
    if (kind != selector["type_id"] or native.common(body)["name"] != selector["name"]
            or hashlib.sha256(body).hexdigest() != selector["sha256"]):
        raise ValueError("Control type, name or archive fingerprint changed")
    return index


def arrange_controls(records, removals, desired_order):
    """Use original sibling indexes for both selectors and the permutation."""
    indexes = [control_index(records, item) for item in removals]
    if len(set(indexes)) != len(indexes):
        raise ValueError("Control removal repeats a sibling")
    surviving = set(range(len(records))) - set(indexes)
    if desired_order is None:
        order = sorted(surviving)
    elif (not isinstance(desired_order, list) or any(type(i) is not int for i in desired_order)
          or len(desired_order) != len(surviving) or set(desired_order) != surviving):
        raise ValueError("control_order must be a full permutation of surviving original indexes")
    else:
        order = desired_order
    return [records[i] for i in order]


def group_siblings(records, path, operation):
    """Rebuild only the indexed CDrawUnit chain, preserving every sibling envelope."""
    from control_factory import GroupArchive, record
    if not isinstance(path, list) or not path:
        raise ValueError("Group path requires one or more control identities")
    index = control_index(records, path[0])
    kind, payload = records[index]
    group = GroupArchive.parse(record(kind, payload))
    if group.to_record().payload != payload:
        raise ValueError("Native group does not round-trip")
    children = [(child.type_id, child.payload) for child in group.children]
    updated = group_siblings(children, path[1:], operation) if len(path) > 1 else operation(children)
    originals = {id(item): child for item, child in zip(children, group.children)}
    group.children = [originals[id(item)] if id(item) in originals else record(*item) for item in updated]
    result = list(records)
    result[index] = (kind, group.to_record().payload)
    return result


def transform_group_child(item, bounds, *, into_group):
    from fractions import Fraction
    from control_factory import CommonEnvelope, record, resize
    from control_geometry import SIMPLE_TYPES
    kind, payload = item
    if kind not in SIMPLE_TYPES and kind != 0x503a:
        raise ValueError('Group coordinate conversion unavailable for ' + hex(kind))
    obj = record(kind, payload)
    cm = CommonEnvelope.parse(obj)
    if cm.animations or struct.unpack_from('<I',cm.prefix,4)[0] & 0x100:
        raise ValueError('Transforming animated or linked-object coordinates requires a class-specific adapter')
    converted = []
    for index, value in enumerate(cm.rect):
        axis = index % 2
        start = bounds[axis]
        size = bounds[axis + 2] - start
        if size <= 0:
            raise ValueError('Group needs positive bounds')
        if into_group:
            coordinate = round(Fraction((value - start) * 10000, size))
            if start + round(Fraction(coordinate * size, 10000)) != value:
                raise ValueError('Group scale loses an original coordinate')
        else:
            coordinate = start + round(Fraction(value * size, 10000))
        if not -0x80000000 <= coordinate <= 0x7fffffff:
            raise ValueError('Converted coordinate exceeds native Int32')
        converted.append(coordinate)
    if kind == 0x503a:
        if converted[0] >= converted[2] or converted[1] >= converted[3]:
            raise ValueError('Converted group dimensions collapsed')
        cm.set_rect(converted)
        return kind, cm.to_record().payload
    return kind, resize(obj, converted).payload


def regroup(records, operation, family):
    from control_factory import CommonEnvelope, GroupArchive, GROUP_SHELLS, new_group, record
    if operation.get('action') == 'group':
        exact(operation, ('action','members','name'), 'Group')
        indexes = [control_index(records, member) for member in operation['members']]
        if len(indexes) < 2 or indexes != list(range(indexes[0], indexes[-1] + 1)):
            raise ValueError('Group consecutive siblings in original layer order')
        members = records[indexes[0]:indexes[-1] + 1]
        rects = [CommonEnvelope.parse(record(*member)).rect for member in members]
        bounds = [min(min(r[0::2]) for r in rects), min(min(r[1::2]) for r in rects),
                  max(max(r[0::2]) for r in rects), max(max(r[1::2]) for r in rects)]
        group = new_group(operation['name'], bounds, [
            transform_group_child(member, bounds, into_group=True) for member in members], family)
        return records[:indexes[0]] + [group] + records[indexes[-1] + 1:]
    exact(operation, ('action','member'), 'Ungroup')
    if operation['action'] != 'ungroup':
        raise ValueError('Unknown grouping action')
    index = control_index(records, operation['member'])
    group = GroupArchive.parse(record(*records[index]))
    bounds = group.common.rect
    children = [(child.type_id, child.payload) for child in group.children]
    group.children = []
    group.common.set_rect([0,0,100,100])
    group.common.name.value = 'Group'
    if group.to_record().payload != GROUP_SHELLS[family]:
        raise ValueError('Ungroup would discard unverified group properties')
    return records[:index] + [transform_group_child(c, bounds, into_group=False)
                              for c in children] + records[index + 1:]


def without_control_names(kind, payload):
    from control_factory import CommonEnvelope, GroupArchive, record
    value = record(kind, payload)
    if kind == 0x503a:
        group = GroupArchive.parse(value)
        group.children = [record(child.type_id, without_control_names(child.type_id,child.payload))
                          for child in group.children]
        value = group.to_record()
    envelope = CommonEnvelope.parse(value)
    envelope.name.value = ''
    return envelope.to_record().payload


def control_names(kind, payload):
    from control_factory import GroupArchive, record
    yield native.common(payload)['name']
    if kind == 0x503a:
        for child in GroupArchive.parse(record(kind, payload)).children:
            yield from control_names(child.type_id, child.payload)


def occurrences(raw, name):
    """Conservative detection for raw native string and source fields.

    This is never used to replace archive bytes or to infer numeric references.
    """
    if not raw or not name:
        return False
    expression = re.compile(r"(?<![\w])" + re.escape(name) + r"(?![\w])", re.I)
    offset = raw.find(b"\xff\xfe\xff")
    while offset >= 0:
        try:
            value = CString.parse(Reader(raw, offset)).value
        except (ValueError, UnicodeError):
            pass
        else:
            if expression.search(value):
                return True
        offset = raw.find(b"\xff\xfe\xff", offset + 3)
    # Unicode CString content can start at either alignment. GBK is used by
    # some old native fields. Escaped identifier references remain visible.
    return any(expression.search(raw[align:].decode(encoding, errors="replace"))
               for encoding, align in (("utf-16le", 0), ("utf-16le", 1), ("gb18030", 0)))


def _consumer_blobs(data, excluded_page=None):
    skip_system = {"ObjData", "MCGSVER", "MCGSLINGUIST", "MCGS_PICTURE_LIST", "MCGS_PICTURE_MANAGER_INFO"}
    for table in ("WndUser", "WndControl", "WndDevice", "Stgy", "Trigger", "System", "Alarm", "Data"):
        for row in data.get(table, {}).get("rows", ()):
            if table == "WndUser" and row.get("iID") == excluded_page:
                continue
            if table == "System" and (row["strName"] in skip_system or row["strName"].startswith("MCGS_PICTURE_DATA_")):
                continue
            for field, value in row.items():
                if isinstance(value, dict) and "binary" in value:
                    yield f"{table}/{row.get('strName', row.get('iID', '?'))}/{field}", native.archive(value)
                elif isinstance(value, str) and field not in ("strNote", "strComment", "strName"):
                    yield f"{table}/{row.get('iID','?')}/{field}", value.encode("utf-16le")


def require_unreferenced(data, name, *, excluded_page=None, skip_main=False):
    hits = [owner for owner, raw in _consumer_blobs(data, excluded_page)
            if not (skip_main and owner.startswith("WndControl/")) and occurrences(raw, name)]
    if hits:
        raise ValueError("Referenced object requires an explicit retarget before changing " + name + ": " + ", ".join(hits))


def startup_lists(blob, prefix_size):
    """Read the two paired name/ID lists and preserve the remaining archive."""
    reader = Reader(blob, prefix_size)
    lists = []
    for _ in range(2):
        names = [CString.parse(reader) for _ in range(reader.u16())]
        ids = [reader.u32() for _ in range(reader.u16())]
        if len(names) != len(ids):
            raise ValueError("Main window startup names and IDs differ in extent")
        lists.append((names, ids))
    return lists, reader.pos


MAIN_PAGE_ROLES = ("startup", "memory")


def _pack_main_page_lists(blob, prefix, end, lists):
    encoded = bytearray(blob[:prefix])
    for names, ids in lists:
        encoded += struct.pack("<H", len(names)) + b"".join(name.to_bytes() for name in names)
        encoded += struct.pack("<H", len(ids)) + b"".join(struct.pack("<I", ident) for ident in ids)
    return bytes(encoded) + blob[end:]


def _main_list_entries(lists):
    return {role:[{"id":ident, "name":name.value} for name, ident in zip(names, ids)]
            for role, (names, ids) in zip(MAIN_PAGE_ROLES, lists)}


def _main_rows(data):
    roots = data.get("WndControl", {}).get("rows", [])
    if len(roots) != 1:
        raise ValueError("Exactly one supported MainCtrl row required")
    return roots[0]


def _main_list_archive(data, root_prefix):
    root = _main_rows(data)
    blob = native.archive(root["lbObjects"])
    if Reader(blob, 12).cstring()[0] != 'MCGS-SET DOCUMENT;VERSION 01.00':
        raise ValueError("Unexpected MainCtrl document marker")
    lists, end = startup_lists(blob, root_prefix)
    if _pack_main_page_lists(blob, root_prefix, end, lists) != blob:
        raise ValueError("MainCtrl page lists did not round-trip")
    return root, blob, lists, end


def main_page_lists(data, root_prefix):
    return _main_list_entries(_main_list_archive(data, root_prefix)[2])


def update_startup(data, prefix, page_id, old_name, new_name=None, new_id=None):
    root = _main_rows(data)
    blob = native.archive(root["lbObjects"])
    rows, end = startup_lists(blob, prefix)
    if occurrences(blob[end:], old_name):
        raise ValueError("An unhandled MainCtrl field references " + old_name)
    for names, ids in rows:
        for index, (name, ident) in enumerate(zip(names, ids)):
            if ident != page_id and name.value.casefold() != old_name.casefold():
                continue
            if ident != page_id or name.value != old_name:
                raise ValueError("MainCtrl page identity is inconsistent")
            if new_name is None:
                raise ValueError("Select another startup or memory window before deleting this page")
            if new_id is not None and new_id != ident and new_id in ids:
                raise ValueError("Replacement page already occurs in this MainCtrl list")
            name.value = new_name
            if new_id is not None:
                ids[index] = new_id
    if new_name is not None:
        root["lbObjects"] = native.wrap_like(root["lbObjects"], _pack_main_page_lists(blob, prefix, end, rows))


def _page(data, selector):
    exact(selector, ("id", "name"), "Page identity")
    matches = [row for row in data["WndUser"]["rows"]
               if row["iID"] == selector["id"] and row["strName"] == selector["name"]]
    if len(matches) != 1 or matches[0]["iDeleteFlag"]:
        raise ValueError("Expected exactly one current native page")
    return matches[0]


def _validate_main_list_entries(data, entries, role):
    if not isinstance(entries, list) or len(entries) > 0xffff:
        raise ValueError("MainCtrl " + role + " needs an array fitting the native count")
    seen = set()
    for entry in entries:
        exact(entry, ("id", "name"), "MainCtrl page identity")
        ident = entry["id"]
        if type(ident) is not int or not 0 < ident <= 0x7fffffff or ident in seen:
            raise ValueError("Missing, out-of-range or repeated MainCtrl page ID in " + role)
        key(entry["name"])
        _page(data, entry)
        seen.add(ident)


def replace_main_page_lists(data, changes, root_prefix):
    if not isinstance(changes, dict) or not changes or set(changes) - set(MAIN_PAGE_ROLES):
        raise ValueError("MainCtrl page lists require startup and/or memory")
    root, blob, lists, end = _main_list_archive(data, root_prefix)
    current = _main_list_entries(lists)
    if not any(current.values()):
        raise ValueError("Neither MainCtrl page list identifies a current native page")
    expected = dict(current)
    for index, role in enumerate(MAIN_PAGE_ROLES):
        _validate_main_list_entries(data, current[role], role)
        if role not in changes:
            continue
        edit = changes[role]
        exact(edit, ("before", "after"), "MainCtrl " + role + " update")
        _validate_main_list_entries(data, edit["before"], role)
        if edit["before"] != current[role]:
            raise ValueError("MainCtrl " + role + " list preimage changed")
        after = edit["after"]
        _validate_main_list_entries(data, after, role)
        if role == "startup" and current[role] and not after:
            raise ValueError("Select another verified startup page before removing the final entry")
        old_names, old_ids = lists[index]
        retained = {(ident, name.value):name for name, ident in zip(old_names, old_ids)}
        names, ids = [], []
        for page in after:
            name = retained.get((page["id"], page["name"]))
            if name is None:
                name = CString.parse(Reader(native.text(page["name"])))
            names.append(name)
            ids.append(page["id"])
        lists[index] = (names, ids)
        expected[role] = after
    changed = _pack_main_page_lists(blob, root_prefix, end, lists)
    reread, after_end = startup_lists(changed, root_prefix)
    if _main_list_entries(reread) != expected or changed[after_end:] != blob[end:]:
        raise ValueError("MainCtrl page list readback differs")
    root["lbObjects"] = native.wrap_like(root["lbObjects"], changed)


def retarget_main_pages(data, changes, root_prefix):
    for change in changes:
        exact(change, ("source", "target"), "Main window retarget")
        old = _page(data, change["source"])
        new = _page(data, change["target"])
        root = _main_rows(data)
        lists, _ = startup_lists(native.archive(root["lbObjects"]), root_prefix)
        if not any(old["iID"] in ids for _, ids in lists):
            raise ValueError("Source page is absent from the main window lists")
        update_startup(data, root_prefix, old["iID"], old["strName"], new["strName"], new["iID"])


def rename_pages(data, changes, root_prefix):
    for change in changes:
        exact(change, ("source", "name"), "Page rename")
        row = _page(data, change["source"])
        old, new = row["strName"], change["name"]
        if old == new:
            continue
        new_key = key(new)
        if any(other is not row and other["strName"].casefold() == new_key for other in data["WndUser"]["rows"]):
            raise ValueError("New page name already exists")
        require_unreferenced(data, old, excluded_page=row["iID"], skip_main=True)
        head, controls, tail = native.window(native.archive(row["lbObjects"]))
        props = WindowSettings.parse(tail, identity=(row["iID"], old))
        if occurrences(props.event_tail, old) or any(occurrences(body, old) for _, body in controls):
            raise ValueError("The page itself still contains a named reference")
        update_startup(data, root_prefix, row["iID"], old, new)
        renamed = props.clone(row["iID"], new)
        row["strName"] = new
        row["lbObjects"] = native.wrap_like(row["lbObjects"], native.pack_window(head, controls, renamed.to_bytes()))
        row["iCompileFlag"] = 0


def remove_pages(data, selectors, root_prefix):
    for selector in selectors:
        row = _page(data, selector)
        if len(data["WndUser"]["rows"]) == 1:
            raise ValueError("A native project must keep a user page")
        # Unknown window tails do not establish that a page is unused.
        for other in data["WndUser"]["rows"]:
            if other is row:
                continue
            _, _, tail = native.window(native.archive(other["lbObjects"]))
            events = WindowSettings.parse(tail, identity=(other["iID"], other["strName"])).event_tail
            try:
                auxiliary = 读取公共窗口槽(events)
            except (ValueError, struct.error) as error:
                raise ValueError("Cannot read auxiliary window slots for " + other["strName"]) from error
            if row["iID"] in auxiliary:
                raise ValueError("Referenced as an auxiliary window by " + other["strName"])
        require_unreferenced(data, row["strName"], excluded_page=row["iID"], skip_main=True)
        update_startup(data, root_prefix, row["iID"], row["strName"])
        data["WndUser"]["rows"].remove(row)


def _rebind_control_tree(controls, old_binding, new_name):
    """Rewrite an exact input binding, leaving other owners to the reference guard."""
    from control_patch import edit
    from mcs_input_text import InputRecord
    from 原生界面样式 import CommonEnvelope, GroupArchive

    old_name, ident, kind = old_binding
    changed = False
    for index, control in enumerate(controls):
        if control.type_id not in (0x5025, 0x503a) or not occurrences(control.payload, old_name):
            continue
        try:
            if control.type_id == 0x5025:
                projected = CommonEnvelope.parse(control).project_without_animations()
                value = InputRecord.parse(projected)
                if (value.variable, value.variable_id, value.variable_type) != old_binding:
                    continue
                replacement = edit(control, {"binding":new_name}, {new_name:{"id":ident, "kind":kind}})
            else:
                group = GroupArchive.parse(control)
                if group.to_record().payload != control.payload:
                    continue
                if not _rebind_control_tree(group.children, old_binding, new_name):
                    continue
                replacement = group.to_record()
        except (ValueError, struct.error):
            # The unchanged archive remains visible to require_unreferenced.
            continue
        controls[index] = replacement
        changed = True
    return changed


def _rebind_input_windows(pages, old_binding, new_name):
    for page in pages:
        original = native.archive(page["lbObjects"])
        if not occurrences(original, old_binding[0]):
            continue
        try:
            window = WindowArchive.parse(original)
        except (ValueError, struct.error):
            continue
        if window.to_bytes() != original or not _rebind_control_tree(window.controls, old_binding, new_name):
            continue
        changed = window.to_bytes()
        if WindowArchive.parse(changed).to_bytes() != changed:
            raise ValueError("Migrated input window does not round-trip")
        page["lbObjects"] = native.wrap_like(page["lbObjects"], changed)
        page["iCompileFlag"] = 0


def _data_group_members(group, span, by_name):
    extension = group["extension"]
    count = native.u32(extension, 0)
    if count and span is None:
        raise ValueError("Current group member vector is not an unambiguous native CString list")
    end = 4 + (span[1] - span[0] if span else 0)
    members, encoded = [], {}
    pos = 4
    for _ in range(count):
        member_name, next_pos = native.string(extension, pos)
        member = by_name.get(member_name)
        if member is None or member["kind"] not in (1, 2, 3):
            raise ValueError("Current group member does not identify an exact scalar")
        ident = member["id"]
        members.append({"id": ident, "name": member_name})
        encoded[ident] = extension[pos:next_pos]
        pos = next_pos
    if pos != end:
        raise ValueError("Current group member right boundary differs from the archive")
    # In the measured files the flag after the authoritative names and the
    # following auxiliary vector count are both zero.
    supported = (len(encoded) == count and extension[end:end+8] == bytes(8)
                 and not group["name"].startswith("$")
                 and all(not member["name"].startswith("$") for member in members))
    return members, encoded, supported


def inspect_data_groups(records):
    by_name = {record["name"]: record for record in records}
    groups = []
    for record in records:
        if record["kind"] != 0xffffffff:
            continue
        ident = record["id"]
        group = {"id": ident, "name": record["name"], "order_editable": False}
        try:
            members, _, supported = _data_group_members(record, records.group_member_spans.get(ident), by_name)
            group.update(members=members, order_editable=supported and len(members)>1)
        except ValueError as error:
            group["members_unavailable"] = str(error)
        groups.append(group)
    return groups


def _data_group_target(operation, by_id, purpose, fields=("id", "name", "before", "after")):
    exact(operation, fields, purpose)
    ident = operation["id"]
    group = by_id.get(ident) if type(ident) is int else None
    if group is None or group["kind"] != 0xffffffff or group["name"] != operation["name"]:
        raise ValueError(purpose + " requires a unique current group ID and name")
    return group


def _data_group_selectors(order, by_id):
    if not isinstance(order, list):
        raise ValueError("Data group member order requires a list")
    ids = []
    for selector in order:
        exact(selector, ("id", "name"), "Data group member identity")
        ident = selector["id"]
        if type(ident) is not int or ident not in by_id or by_id[ident]["name"] != selector["name"]:
            raise ValueError("Data group member identity differs from the current scalar")
        ids.append(ident)
    return ids


def _require_no_variable_table_references(data, ident, name):
    for table, fields in (("Alarm", ("iDataObjID", "iRelatePointID")),
                          ("DDEConnection", ("iDataID",)),
                          ("Data", ("iDataID", "ArgvObjID"))):
        for consumer in data.get(table, {}).get("rows", ()):
            for field in fields:
                if consumer.get(field) == ident:
                    raise ValueError(f"Variable {name} is referenced by {table}.{field} ({ident})")


def _data_object_id_vectors(record, records):
    extension = record["extension"]
    entries = native.u32(extension, 0)
    if record["kind"] == 0xffffffff:
        span = records.group_member_spans.get(record["id"])
        if entries and span is None:
            raise ValueError("Another data group has an unresolved member vector")
        pos = 4 + (span[1] - span[0] if span else 0)
        first = ()
    else:
        pos = 4 + entries * 4
        first = struct.iter_unpack("<I", extension[4:pos])
    enabled = native.u32(extension, pos)
    pos += 4
    if enabled:
        alarms = native.u32(extension, pos)
        pos += 4
        if alarms:
            known = records.alarm_spans and records.alarm_spans.get(record["id"])
            if not known or len(known)!=alarms or known[0][0]!=pos:
                raise ValueError("Another data object's alarm extent leaves its auxiliary vector unresolved")
            pos = known[-1][1]
    count = native.u32(extension, pos)
    second = struct.iter_unpack("<I", extension[pos+4:pos+4+count*4])
    return {item for (item,) in first} | {item for (item,) in second}


def _require_unreferenced_data_group(data, group, records):
    ident, name = group["id"], group["name"]
    _require_no_variable_table_references(data, ident, name)
    require_unreferenced(data, name)
    for other in records:
        if other is group:
            continue
        if occurrences(other["prefix"]+other["extension"], name) or ident in _data_object_id_vectors(other, records):
            raise ValueError(f"Data group {name} is referenced by variable {other['name']} ({other['id']})")


def _default_data_group_prefix(neutral, ident):
    prefix = bytes.fromhex(neutral["prefix"])
    _, middle = native.string(prefix, 36)
    _, initial_end = native.string(prefix, middle+28)
    native_id = initial_end + 12
    return prefix[:native_id] + struct.pack("<I", ident) + prefix[native_id+4:]


def data_group_deletions(spec):
    selectors = spec["delete_data_groups"]
    if not isinstance(selectors, list) or not selectors:
        raise ValueError("delete_data_groups requires a nonempty list of existing groups")
    ids, names = set(), set()
    for selector in selectors:
        exact(selector, ("id", "name"), "Data group deletion identity")
        ident, name = selector["id"], key(selector["name"])
        if type(ident) is not int or ident in ids or name in names:
            raise ValueError("Data group deletion identities must be distinct integer IDs and names")
        ids.add(ident)
        names.add(name)
    edits = spec.get("data_group_orders", [])
    if not isinstance(edits, list):
        raise ValueError("data_group_orders requires a list")
    for edit in [spec.get("data_group_members"), *edits, *(spec.get("add_variables") or [])]:
        if not isinstance(edit, dict):
            continue
        ident, name = edit.get("id"), edit.get("name")
        if ((type(ident) is int and ident in ids) or
                (isinstance(name, str) and name.casefold() in names)):
            raise ValueError("A data group cannot be added or edited and deleted in the same specification")
    return selectors


def delete_default_data_groups(data, selectors, neutral):
    row, = [item for item in data["System"]["rows"] if item["strName"] == "ObjData"]
    original = native.archive(row["lbContext"])
    records = native.variables(original)
    by_id = {record["id"]: record for record in records}
    if native.pack_variables(records) != original:
        raise ValueError("Original ObjData group archive did not round-trip")
    removed = set()
    for selector in selectors:
        group = _data_group_target(selector, by_id, "Data group deletion", ("id", "name"))
        ident = group["id"]
        if (group["name"].startswith("$") or group["note"] or group["unit"] or
                group["prefix"] != _default_data_group_prefix(neutral, ident) or
                group["extension"] != bytes.fromhex(neutral["extension"])):
            raise ValueError("Data group deletion requires a verified default empty user group")
        _require_unreferenced_data_group(data, group, records)
        removed.add(ident)
    remaining = native.VariableRecords(
        (record for record in records if record["id"] not in removed), records.document_header)
    changed = native.pack_variables(remaining)
    reread = native.variables(changed)
    if reread != remaining or reread.document_header != records.document_header:
        raise ValueError("Data group deletion did not preserve exact surviving records")
    row["lbContext"] = native.wrap_like(row["lbContext"], changed)


def replace_data_group_members(data, operation, neutral, family):
    row, = [item for item in data["System"]["rows"] if item["strName"] == "ObjData"]
    original = native.archive(row["lbContext"])
    records = native.variables(original)
    by_id = {record["id"]: record for record in records}
    by_name = {record["name"]: record for record in records}
    group = _data_group_target(operation, by_id, "Data group membership")
    ident = group["id"]
    span = records.group_member_spans.get(ident)
    # An archive with only empty groups can have a unique count boundary
    # without distinguishing an empty CString vector from an empty ID vector.
    # Each original reader switches from IDs to CString at its own archive schema boundary.
    archive_version, = struct.unpack("<f", records.document_header)
    pro_cutoff, = struct.unpack("<f", struct.pack("<f", 12.1))
    uses_names = ((family == "Stu" and archive_version > 12.5)
                  or (family == "Pro" and archive_version >= pro_cutoff))
    if (span is None and uses_names and math.isfinite(archive_version)
            and not group["note"] and not group["unit"]
            and all(record["id"] in records.empty_group_spans for record in records
                    if record["kind"] == 0xffffffff)):
        span = records.empty_group_spans.get(ident)
    if span is None:
        raise ValueError("Current ObjData does not identify a native CString group vector")
    members, encoded, supported = _data_group_members(group, span, by_name)
    begin, end = span
    suffix = 4 + end - begin
    extension = group["extension"]
    default_prefix = _default_data_group_prefix(neutral, ident)
    if (not supported or group["prefix"]!=default_prefix or
            extension[suffix:]!=bytes.fromhex(neutral["extension"])[4:]):
        raise ValueError("Data group membership requires the verified default storage and auxiliary fields")

    current = {member["id"]: member for member in members}
    if _data_group_selectors(operation["before"], current) != list(current):
        raise ValueError("Data group before order differs from the current group")
    scalars = {r["id"]: r for r in records if r["kind"] in (1, 2, 3) and not r["name"].startswith("$")}
    wanted = _data_group_selectors(operation["after"], scalars)
    if len(set(wanted))!=len(wanted):
        raise ValueError("Data group members must be distinct existing user scalars")
    _require_unreferenced_data_group(data, group, records)

    vector = struct.pack("<I", len(wanted)) + b"".join(
        encoded[member_id] if member_id in encoded else scalars[member_id]["_text_source"]["name"][1]
        for member_id in wanted)
    if original[begin-4:end] != extension[:suffix]:
        raise ValueError("Data group span does not match its native record")
    result = original[:begin-4] + vector + original[end:]
    result = result[:4] + struct.pack("<I", len(result)-8) + result[8:]
    reread = native.variables(result)
    edited = dict(group, extension=vector+extension[suffix:])
    expected = [edited if record is group else record for record in records]
    if reread!=expected or reread.document_header!=records.document_header or reread.alarm_spans!=records.alarm_spans:
        raise ValueError("Data group membership reread differs outside the selected vector")
    after, _, _ = _data_group_members(edited, reread.group_member_spans.get(ident), by_name)
    if after != operation["after"]:
        raise ValueError("Data group member identities differ after native reread")
    row["lbContext"] = native.wrap_like(row["lbContext"], result)


def reorder_data_groups(data, operations):
    if not isinstance(operations, list) or not operations:
        raise ValueError("data_group_orders requires a nonempty list of existing group reorders")
    row, = [item for item in data["System"]["rows"] if item["strName"] == "ObjData"]
    original = native.archive(row["lbContext"])
    records = native.variables(original)
    by_id = {record["id"]: record for record in records}
    by_name = {record["name"]: record for record in records}
    replacements = {}
    changed = bytearray(original)

    for operation in operations:
        group = _data_group_target(operation, by_id, "Data group reorder")
        ident = group["id"]
        if ident in replacements:
            raise ValueError("Data group reorder requires a unique current group ID and name")
        span = records.group_member_spans.get(ident)
        before, encoded, supported = _data_group_members(group, span, by_name)
        if not supported or len(before)<2:
            raise ValueError("Data group requires distinct user scalar members and empty alarm and auxiliary fields")
        by_member_id = {member["id"]: member for member in before}
        if _data_group_selectors(operation["before"], by_member_id) != list(by_member_id):
            raise ValueError("Data group before order differs from the current group")
        wanted = _data_group_selectors(operation["after"], by_member_id)
        if len(wanted) != len(before) or set(wanted) != set(by_member_id):
            raise ValueError("Data group after order must be a permutation of the current members")

        begin, end = span
        extension = group["extension"]
        suffix = 4 + end - begin
        if original[begin:end] != extension[4:suffix]:
            raise ValueError("Data group span does not match its native record")
        reordered = b"".join(encoded[member_id] for member_id in wanted)
        changed[begin:end] = reordered
        replacements[ident] = dict(group, extension=extension[:4] + reordered + extension[suffix:])

    changed = bytes(changed)
    reread = native.variables(changed)
    expected = [replacements.get(record["id"], record) for record in records]
    if (reread != expected or reread.document_header != records.document_header
            or reread.alarm_spans != records.alarm_spans
            or reread.group_member_spans != records.group_member_spans):
        raise ValueError("Data group reread did not preserve the native variable records and layout")
    row["lbContext"] = native.wrap_like(row["lbContext"], changed)


def remove_variables(data, selectors, renames=()):
    if not selectors and not renames:
        return
    row, = [item for item in data["System"]["rows"] if item["strName"] == "ObjData"]
    original = native.archive(row["lbContext"])
    variables = native.variables(original)
    operations = [(selector, None, False) for selector in selectors]
    for change in renames:
        fields = ("source", "name", "update_input_bindings")
        exact(change, fields if isinstance(change, dict) and fields[-1] in change else fields[:2],
              "Variable rename")
        key(change["name"])
        migrate = change.get("update_input_bindings", False)
        if type(migrate) is not bool:
            raise ValueError("update_input_bindings must be true or false")
        operations.append((change["source"], change["name"], migrate))
    projected = data
    if any(migrate for _, _, migrate in operations):
        pages = [dict(page) for page in data["WndUser"]["rows"]]
        projected = {**data, "WndUser":{**data["WndUser"], "rows":pages}}
    for selector, new_name, migrate in operations:
        exact(selector, ("id", "name"), "Variable identity")
        if type(selector["id"]) is not int:
            raise ValueError("Variable identity requires an integer ID")
        matches = [item for item in variables if item["id"] == selector["id"] and item["name"] == selector["name"]]
        if len(matches) != 1 or matches[0]["kind"] not in (1, 2, 3):
            raise ValueError("Variable deletion requires a unique current scalar")
        target = matches[0]
        ident, name = target["id"], target["name"]
        if target["extension"][:12] != bytes(12) or name.startswith("$"):
            raise ValueError("Variable deletion requires a user scalar without live group or alarm metadata")
        if new_name is not None and (new_name.startswith("$") or any(
                item is not target and key(item["name"]) == key(new_name) for item in variables)):
            raise ValueError("Variable name reserved or already in use")
        _require_no_variable_table_references(data, ident, name)
        if migrate and new_name != name:
            _rebind_input_windows(pages, (name, ident, target["kind"]), new_name)
        require_unreferenced(projected, name)
        for item in variables:
            if item is target:
                continue
            ext = item["extension"]
            if occurrences(ext, name) or (item["kind"] == 0xffffffff and struct.pack("<I", ident) in ext):
                raise ValueError("Variable deletion would break a current object group or expression reference")
        if new_name is None:
            variables.remove(target)
        else:
            target["name"] = new_name
            target["_text_source"]["name"] = (new_name, native.text(new_name))
    changed = native.pack_variables(variables)
    reread = native.variables(changed)
    if reread != variables or reread.document_header != variables.document_header:
        raise ValueError("Variable archive did not preserve exact surviving records")
    row["lbContext"] = native.wrap_like(row["lbContext"], changed)
    if projected is not data:
        data["WndUser"]["rows"] = pages
