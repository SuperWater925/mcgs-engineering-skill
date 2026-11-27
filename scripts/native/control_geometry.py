"""One archive-aware geometry dispatch used by every offline entry point."""
import struct

from 原生界面样式 import CommonEnvelope, GenericMetadata, MultiState

STATIC_BODY_TYPES = frozenset((0x5006, 0x5009))
SIMPLE_TYPES = frozenset((0x5002, 0x5004, 0x5008, 0x5025, 0x5027)) | STATIC_BODY_TYPES
GEOMETRY_TYPES = SIMPLE_TYPES | {0x5028, 0x502a}


def resize(record, bounds):
    if (not isinstance(bounds, (list, tuple)) or len(bounds) != 4 or
            any(type(v) is not int or not -0x80000000 <= v <= 0x7fffffff for v in bounds)):
        raise ValueError('Bounds require four native Int32 values')
    if record.type_id == 0x5002:
        if tuple(bounds[:2]) == tuple(bounds[2:]):
            raise ValueError('Line endpoints must differ')
    elif bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        raise ValueError('Positive control dimensions required')
    if record.type_id in (0x5028, 0x502a):
        value = MultiState.parse(record)
        value.resize(bounds)
        return value.to_record()
    if record.type_id not in SIMPLE_TYPES:
        raise ValueError('No geometry adapter for native class ' + hex(record.type_id))
    value = CommonEnvelope.parse(record)
    if value.to_record().payload != record.payload:
        raise ValueError('Geometry envelope does not round-trip')
    if record.type_id in STATIC_BODY_TYPES:
        if (value.animations or struct.unpack_from('<I', value.prefix, 4)[0] & 0x100
                or GenericMetadata.parse(value.metadata.value).events):
            raise ValueError('Ellipse or bitmap bounds require a static unlinked control without dispatch events')
        if record.type_id == 0x5006 and value.content:
            raise ValueError('Ellipse has an unrecognized geometry body')
        if record.type_id == 0x5009:
            from picture_resources import Picture
            picture = Picture.parse(value.content)
            named = picture.mode == 0x80 and bool(picture.reference.value)
            embedded = picture.mode == 2 and bool(picture.width and picture.height and picture.payload)
            if not (named or embedded):
                raise ValueError('Bitmap geometry requires an existing named or embedded image')
    value.set_rect(bounds)
    result = value.to_record()
    if record.type_id in STATIC_BODY_TYPES:
        start = value.rect_offset
        expected = record.payload[:start] + struct.pack('<4i', *bounds) + record.payload[start+16:]
        if result.payload != expected:
            raise ValueError('Ellipse or bitmap changed outside its original rectangle slice')
    return result
