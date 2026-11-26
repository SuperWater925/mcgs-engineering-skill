"""Reparent native page controls using current group identities and rectangles."""

import struct

from control_factory import CommonEnvelope, GroupArchive, record
from offline_structure import control_index, exact, key, transform_group_child


def group_path(records, selectors, groups):
    path = ()
    for selector in selectors:
        index = control_index(records, selector)
        path += (index,)
        kind, payload = records[index]
        group = groups.get(path)
        if group is None:
            group = GroupArchive.parse(record(kind, payload))
            if group.to_record().payload != payload:
                raise ValueError('Native group does not round-trip')
            groups[path] = group
        records = [(child.type_id, child.payload) for child in group.children]
    return path, records


def projected(item, frames, into_group):
    for frame in frames:
        if frame.animations or struct.unpack_from('<I', frame.prefix, 4)[0] & 0x100:
            raise ValueError('Moving across animated or linked groups requires a coordinate adapter')
        item = transform_group_child(item, frame.rect, into_group=into_group)
    return item


def move_between_groups(records, operation):
    exact(operation, ('action', 'source', 'destination', 'insert_at'), 'Move between groups')
    source, destination = operation['source'], operation['destination']
    if not isinstance(source, list) or not source or not isinstance(destination, list):
        raise ValueError('Move requires a source control path and a destination group path')
    groups = {}
    source_parent, siblings = group_path(records, source[:-1], groups)
    source_index = control_index(siblings, source[-1])
    source_path = source_parent + (source_index,)
    dest_parent, dest_siblings = group_path(records, destination, groups)
    insert_at = operation['insert_at']
    if dest_parent == source_parent or dest_parent[:len(source_path)] == source_path:
        raise ValueError('Choose a different parent outside the moved subtree')
    if type(insert_at) is not int or not 0 <= insert_at <= len(dest_siblings):
        raise ValueError('Move insertion index is outside the destination group')

    item = siblings[source_index]
    identity = CommonEnvelope.parse(record(*item)).name.value
    for kind, payload in dest_siblings:
        if key(CommonEnvelope.parse(record(kind, payload)).name.value) == key(identity):
            raise ValueError('Move would duplicate the destination sibling name')
    outgoing = [groups[source_parent[:i]].common for i in range(1, len(source_parent) + 1)]
    incoming = [groups[dest_parent[:i]].common for i in range(1, len(dest_parent) + 1)]
    shared = 0
    for left, right in zip(source_parent, dest_parent):
        if left != right:
            break
        shared += 1
    at_common_parent = projected(item, reversed(outgoing[shared:]), False)
    moved = projected(at_common_parent, incoming[shared:], True)
    check = projected(moved, reversed(incoming[shared:]), False)
    if CommonEnvelope.parse(record(*check)).rect != CommonEnvelope.parse(record(*at_common_parent)).rect:
        raise ValueError('Move cannot preserve the rectangle in the shared coordinate system')

    def rebuild(siblings, parent):
        result = []
        for index, value in enumerate(siblings):
            path = parent + (index,)
            if path == source_path:
                continue
            if path in groups:
                group = groups[path]
                previous = [(child.type_id, child.payload) for child in group.children]
                children = rebuild(previous, path)
                originals = {id(value): child for value, child in zip(previous, group.children)}
                group.children = [originals[id(value)] if id(value) in originals else record(*value)
                                  for value in children]
                value = (value[0], group.to_record().payload)
            result.append(value)
        if parent == dest_parent:
            result.insert(insert_at, moved)
        return result

    return rebuild(records, ()), item
