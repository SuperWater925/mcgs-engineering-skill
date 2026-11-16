"""One archive-aware geometry dispatch used by every offline entry point."""
from 原生界面样式 import CommonEnvelope, MultiState

SIMPLE_TYPES = frozenset((0x5002, 0x5004, 0x5008, 0x5025, 0x5027))
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
    value.set_rect(bounds)
    return value.to_record()
