"""Preserve event graphs while locating a bounded native property extension."""
from mcs_window_archive import Reader, FormatError
from mcs_button_control import ByteArray


def split_metadata(data, validate_properties, mirror=None):
    # Known event classes give an exact boundary. Unknown events remain opaque;
    # only a unique, independently validated length-framed property block may
    # identify their end. No event or unknown tail is rewritten by style edits.
    start = Reader(data)
    count = start.count()
    start.count_extent(count, 2, 'Generic event')
    offsets = None; opaque_events = False
    try:
        from 原生界面样式 import GenericMetadata
        events = GenericMetadata.parse(data)
        offsets = [len(data)-len(events.tail)]
    except (ValueError, UnicodeError):
        opaque_events = True
        offsets = range(start.pos, max(start.pos, len(data)-11))
    candidates = []
    for offset in offsets:
        try:
            r = Reader(data, offset)
            words = r.take(8)
            extension = ByteArray.parse(r)
            nested = Reader(extension.value)
            properties = ByteArray.parse(nested)
            extension_tail = ByteArray.parse(nested)
            if opaque_events and mirror is not None and properties.value != mirror:
                raise FormatError('Opaque-event property block lacks an exact independent mirror')
            validated = validate_properties(properties.value)
            candidates.append((data[:offset], words, extension, properties,
                               extension_tail, data[r.pos:], extension.value[nested.pos:], validated))
        except (ValueError, UnicodeError, IndexError):
            continue
    if len(candidates) != 1:
        raise FormatError('Ambiguous metadata property extension' if candidates else
                          'No independently validated metadata property extension')
    return candidates[0]
