"""Native picture envelopes and bounded existing-library resource edits.

No runtime-package decoding or conversion. Unknown payloads round-trip untouched.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import io
from math import isqrt
import struct
from mcs_window_archive import Reader, ControlRecord, FormatError, write_count, write_cstring
from mcs_button_control import CString

# Native mode-2 and library envelopes serialize width, height and byte count
# as DWORDs. Decoder limits remain Pillow's actual limits, not a product gate.
NATIVE_DWORD_MAX = 0xffffffff
CELL_TAG = bytes.fromhex('0100ffff00000900434472617743656c6c')
STU_VECT_METADATA_WORD = struct.pack('<I', 10000)


def _vector_canvas(bounds):
    if (not isinstance(bounds, list) or len(bounds) != 4 or
            not all(type(x) is int and -2**31 <= x < 2**31 for x in bounds)):
        raise ValueError('Vector bounds require four signed 32-bit integers')
    left, top, right, bottom = bounds
    width, height = right-left, bottom-top
    if not all(0 < n < 2**31 for n in (width, height)):
        raise ValueError('Vector bounds require positive signed 32-bit width and height')
    return width, height


def rectangle_vector(family, name, bounds, colors):
    """Construct a detached CDrawCell containing one editable CDrawRect."""
    return _static_vector(family, name, bounds, [(0x5004, (0, 0, 10000, 10000), colors)])


def line_vector(family, name, bounds, endpoints, colors):
    """Construct an editable CDrawLine from ordered endpoints in a positive canvas."""
    coordinates = _vector_relative_coordinates(bounds, endpoints)
    return _static_vector(family, name, bounds, [(0x5002, coordinates, colors)])


def _vector_relative_coordinates(bounds, points):
    width, height = _vector_canvas(bounds)
    if not isinstance(points, list) or len(points) != 4 or any(type(n) is not int for n in points):
        raise ValueError('Vector shape requires four integer coordinates')
    x1, y1, x2, y2 = points
    left, top, right, bottom = bounds
    if not (left <= x1 <= right and left <= x2 <= right and
            top <= y1 <= bottom and top <= y2 <= bottom):
        raise ValueError('Vector shape coordinates must be within the supplied canvas')
    # Native CDrawObj slot5 translates by the origin and applies Win32 MulDiv.
    # Each numerator is nonnegative inside the caller-supplied canvas.
    return tuple(((value - origin) * 10000 + span // 2) // span for value, origin, span in
                 zip(points, (left, top, left, top), (width, height, width, height)))


def shape_vector(family, name, bounds, shapes):
    """Build one editable CDrawCell whose independent children retain list order."""
    if not isinstance(shapes, list) or not shapes:
        raise ValueError('Vector shapes must be a nonempty array')
    children = []
    for shape in shapes:
        if not isinstance(shape, dict):
            raise ValueError('Vector shapes must be objects')
        kind = shape.get('type')
        if kind == 'rectangle' and {'type', 'bounds'} <= shape.keys() <= {'type', 'bounds', 'fill', 'border'}:
            coordinates = _vector_relative_coordinates(bounds, shape['bounds'])
            children.append((0x5004, coordinates, {key: shape[key] for key in ('fill', 'border') if key in shape}))
        elif kind == 'line' and {'type', 'endpoints'} <= shape.keys() <= {'type', 'endpoints', 'border'}:
            coordinates = _vector_relative_coordinates(bounds, shape['endpoints'])
            children.append((0x5002, coordinates, {'border': shape['border']} if 'border' in shape else {}))
        else:
            raise ValueError('Vector shapes require rectangle bounds or directed line endpoints')
    return _static_vector(family, name, bounds, children)


def exact_factory_vector(resource, family):
    """Recognize only independent vectors this factory can reconstruct byte for byte."""
    from 原生界面样式 import CommonEnvelope

    try:
        root, _ = resource.vector()
        if not root.children:
            return False
        children = []
        for record in root.children:
            if record.type_id not in (0x5002, 0x5004):
                return False
            child = CommonEnvelope.parse(record)
            colors = {'border': struct.unpack_from('<I', child.prefix, child.pen_offset + 14)[0]}
            if record.type_id == 0x5004:
                colors['fill'] = struct.unpack_from('<I', child.prefix, child.brush_offset + 6)[0]
            children.append((record.type_id, child.rect, colors))
        rebuilt = _static_vector(family, resource.name.value, list(root.common.rect), children)
        return resource.to_bytes() == rebuilt.to_bytes()
    except (ValueError, struct.error):
        return False


def _static_vector(family, name, bounds, shapes):
    from control_patch import edit
    from 原生界面样式 import CommonEnvelope, GroupArchive

    if family not in ('Pro', 'Stu'):
        raise ValueError('Unrecognized native vector archive family')
    canvas_width, canvas_height = _vector_canvas(bounds)
    # Neutral original drawable defaults, with no embedded project fields.
    cell_version = 331.0 if family == 'Stu' else 317.1
    metadata = bytes(12) + (STU_VECT_METADATA_WORD if family == 'Stu' else b'')
    cell_tail = bytes(12) if family == 'Stu' else b''
    pen = struct.pack('<H4I', 1, 6, 1, 1, 0)
    brush = struct.pack('<H3I', 1, 0, 0xc0c0c0, 0)
    def drawable(version, rect, state, label):
        return (struct.pack('<fII4i', version, 0, 0, *rect) + pen + brush +
                struct.pack('<3H', 0, 0, state) + write_cstring(label) + write_count(len(metadata)) + metadata)

    children = []
    for index, (kind, coordinates, colors) in enumerate(shapes):
        x1, y1, x2, y2 = coordinates
        if any(value < 0 or value > 10000 for value in coordinates):
            raise ValueError('Vector shape coordinate is outside the native canvas')
        if kind == 0x5004:
            if x1 >= x2 or y1 >= y2:
                raise ValueError('Vector rectangle requires positive width and height at native canvas precision')
            state = 0x8001
        else:
            if x1 == x2 and y1 == y2:
                raise ValueError('Vector line endpoints must differ at native canvas precision')
            state = 0x8000
        child_payload = drawable(1.0, coordinates, state, '控件' + str(index))
        child = ControlRecord(kind, child_payload, write_count(len(child_payload)), 0)
        children.append(edit(child, colors) if colors else child)
    root_base = drawable(cell_version, bounds, 0x8000, '')
    root = GroupArchive(CommonEnvelope.parse(ControlRecord(0x503a, root_base, b'', 0)), children, cell_tail)
    body = CELL_TAG + root.to_record().payload

    # The original allocation uses square BMP dimensions rounded from the
    # number of 24-bit pixels, then extends height to fit and aligns each row.
    pixel_count = (len(body) + 18) // 3
    width = isqrt(pixel_count)
    if pixel_count > width * width + width:
        width += 1
    height = max(width, (pixel_count + width - 1) // width)
    allocation = ((width * 3 + 3) // 4 * 4) * height
    bmp = (struct.pack('<2sIII', b'BM', 54+allocation, 0, 54) +
           struct.pack('<IiiHHIIiiII', 40, width, height, 1, 24, 0, allocation, 0, 0, 0, 0))
    vector = b'VECT' + struct.pack('<3I', len(body), canvas_width, canvas_height) + body
    payload = bmp + vector + bytes(allocation-len(vector))

    # ImageHash serializes the picture envelope without its names, with the
    # root's +44/+48 already zero and its rectangle temporarily normalized.
    normalized = bytearray(payload)
    struct.pack_into('<4i', normalized, 87+root.common.rect_offset, 0, 0, 100, 100)
    digest = hashlib.md5(struct.pack('<4I', 16, width, height, len(payload)) + normalized).hexdigest()
    resource = PictureResource(CString.parse(Reader(write_cstring(name))),
                               CString.parse(Reader(write_cstring(digest))), 16, width, height, payload)
    resource.vector()
    return resource


def raster_details(data):
    """Validate a complete BMP/PNG/JPEG and its native DWORD representation."""
    if not isinstance(data, bytes) or not 0 < len(data) <= NATIVE_DWORD_MAX:
        raise ValueError('Image payload is empty or its length does not fit the native DWORD')
    if data[:2] == b'BM' and data[54:58] == b'VECT':
        raise ValueError('VECT is a native vector archive, not a raster')
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        if im.format not in ('BMP', 'PNG', 'JPEG'):
            raise ValueError('Only complete BMP, PNG and JPEG raster files are supported')
        kind = im.format
        width, height = im.size
        if not all(0 < value <= NATIVE_DWORD_MAX for value in (width, height)):
            raise ValueError('Image dimensions do not fit the native DWORD fields')
        im.verify()
    # verify() checks format framing; load() also detects truncated pixel data.
    with Image.open(io.BytesIO(data)) as im:
        im.load()
    if kind == 'BMP':
        if len(data) < 54 or struct.unpack_from('<I', data, 2)[0] != len(data):
            raise ValueError('BMP file length differs from its header')
    elif kind == 'PNG' and data[-12:] != bytes.fromhex('0000000049454e44ae426082'):
        raise ValueError('PNG must end at its complete IEND chunk')
    elif kind == 'JPEG' and data[-2:] != b'\xff\xd9':
        raise ValueError('JPEG must end at its EOI marker')
    return {'format': kind, 'width': width, 'height': height, 'bytes': len(data)}


def _native_bitmap_payload(data):
    """Return the original kind-0 BMP layout, normalizing an omitted biSizeImage."""
    if len(data) < 54 or data[:2] != b'BM':
        return None
    size, reserved, offset = struct.unpack_from('<III', data, 2)
    header, width, height, planes, depth, compression, pixels, _, _, colors, _ = struct.unpack_from(
        '<IiiHHIIiiII', data, 14)
    if (size != len(data) or reserved != 0 or offset != 54 or header != 40
            or min(width, height) <= 0 or planes != 1 or depth != 24 or compression != 0 or colors != 0):
        return None
    allocation = ((width * 3 + 3) & ~3) * height
    if allocation != len(data) - offset or pixels not in (0, allocation):
        return None
    if not pixels:
        return data[:34] + struct.pack('<I', allocation) + data[38:]
    return data


@dataclass
class Picture:
    mode: int
    reference: CString | None = None
    width: int = 0
    height: int = 0
    payload: bytes = b''

    @classmethod
    def read(cls, r):
        mode = r.u32()
        if mode == 0x80:
            return cls(mode, CString.parse(r))
        if mode == 2:
            width, height, size = r.u32(), r.u32(), r.u32()
            return cls(mode, None, width, height, r.take(size))
        if mode == 3 and r.u32() == 0 and r.u32() == 0:
            return cls(mode)
        raise FormatError('Unsupported native picture envelope')

    @classmethod
    def parse(cls, raw):
        r = Reader(raw); value = cls.read(r)
        if r.pos != len(raw) or value.to_bytes() != raw:
            raise FormatError('Native picture must consume and round-trip its complete envelope')
        return value

    def to_bytes(self):
        if self.mode == 0x80:
            return struct.pack('<I', self.mode) + self.reference.to_bytes()
        if self.mode == 2:
            return struct.pack('<4I', self.mode, self.width, self.height, len(self.payload)) + self.payload
        if self.mode == 3:
            return struct.pack('<3I', 3, 0, 0)
        raise ValueError('Unsupported picture mode')


def image_hex(value):
    if not isinstance(value,str):
        raise ValueError('Image hex payload must be a string')
    payload=bytes.fromhex(value)
    if len(payload)>NATIVE_DWORD_MAX:
        raise ValueError('Image payload length does not fit the native DWORD')
    return payload


def uses_picture_reference(value):
    if isinstance(value, dict):
        return 'reference' in value or any(uses_picture_reference(child) for child in value.values())
    if isinstance(value, list):
        return any(uses_picture_reference(child) for child in value)
    return False


def replace_picture(original, spec, references=None):
    old = Picture.parse(original)
    if not isinstance(spec, dict):
        raise ValueError('Picture edit must be an object')
    if set(spec) == {'reference'}:
        name = spec['reference']
        if not isinstance(name, str) or not name or '\0' in name:
            raise ValueError('Picture reference must be a nonempty resource name')
        if references is None or name not in references:
            raise ValueError('Picture reference must resolve to an existing library resource name')
        if old.mode == 0x80:
            old.reference.value = name
            return old.to_bytes()
        return struct.pack('<I', 0x80) + write_cstring(name)
    if set(spec) == {'embedded_hex'} and isinstance(spec['embedded_hex'], str):
        payload = image_hex(spec['embedded_hex'])
        info = raster_details(payload)
        return Picture(2, None, info['width'], info['height'], payload).to_bytes()
    raise ValueError('Picture edit requires reference or embedded_hex')


def _vector_bitmap_bounds(record, bounds):
    from 原生界面样式 import CommonEnvelope, GenericMetadata

    if (not isinstance(bounds, (list, tuple)) or len(bounds) != 4 or
            any(type(v) is not int or not -2**31 <= v < 2**31 for v in bounds) or
            bounds[0] >= bounds[2] or bounds[1] >= bounds[3]):
        raise ValueError('Vector bitmap bounds require positive native Int32 geometry')
    common = CommonEnvelope.parse(record)
    if (common.to_record().payload != record.payload or common.animations or
            struct.unpack_from('<I', common.prefix, 4)[0] & 0x100 or
            GenericMetadata.parse(common.metadata.value).events):
        raise FormatError('Vector bitmap bounds require a round-tripping static, unlinked child')
    picture = Picture.parse(common.content)
    if picture.mode != 2 or not picture.payload or not picture.width or not picture.height:
        raise FormatError('Vector bitmap bounds require a complete native embedded image')
    # The image can be an original VS stream. Geometry only changes the
    # shared CDrawObj rectangle and keeps the whole original image envelope.
    expected = bytearray(record.payload)
    struct.pack_into('<4i', expected, common.rect_offset, *bounds)
    common.set_rect(bounds)
    result = common.to_record()
    if result.payload != expected:
        raise FormatError('Vector bitmap bounds changed bytes outside the rectangle')
    return result


def _vector_label_font(record, font):
    import control_patch as cp
    from mcs_input_text import LabelRecord
    from 原生界面样式 import CommonEnvelope

    if not isinstance(font, dict) or not font or set(font) - {'height', 'weight', 'italic', 'underline', 'strikeout'}:
        raise ValueError('Vector label fonts require fixed-size height, weight, italic, underline or strikeout edits')
    before = CommonEnvelope.parse(record)
    label = LabelRecord.parse(before.project_without_animations())
    if record.payload.count(label.font) != 1:
        raise FormatError('Vector label font has no unique native byte span')
    result = cp.edit(record, {'font': font})
    after = CommonEnvelope.parse(result)
    changed_font = LabelRecord.parse(after.project_without_animations()).font
    expected = record.payload.replace(label.font, changed_font, 1)
    if len(changed_font) != len(label.font) or result.payload != expected:
        raise FormatError('Vector label font changed bytes outside its fixed-size font span')
    return result


@dataclass
class PictureResource:
    name: CString
    identity: CString
    kind: int
    width: int
    height: int
    payload: bytes

    @classmethod
    def parse(cls, raw):
        r = Reader(raw); name, identity = CString.parse(r), CString.parse(r)
        kind, width, height, size = r.u32(), r.u32(), r.u32(), r.u32()
        value = cls(name, identity, kind, width, height, r.take(size))
        if r.pos != len(raw) or value.to_bytes() != raw:
            raise FormatError('Picture resource length or byte roundtrip differs')
        return value

    @classmethod
    def from_raster(cls, name, data):
        info = raster_details(data)
        bmp = _native_bitmap_payload(data) if info['format'] == 'BMP' else None
        kind, payload = (0, bmp) if bmp is not None else (2, data)
        width, height = info['width'], info['height']
        # The persisted digest excludes both CString names. Original JPEG and
        # PNG have the same kind-2 archive header and keep their encoded bytes.
        body = struct.pack('<4I', kind, width, height, len(payload))
        digest = hashlib.md5()
        digest.update(body)
        digest.update(payload)
        return cls(CString.parse(Reader(write_cstring(name))),
                   CString.parse(Reader(write_cstring(digest.hexdigest()))),
                   kind, width, height, payload)

    def to_bytes(self):
        return self.name.to_bytes() + self.identity.to_bytes() + struct.pack(
            '<4I', self.kind, self.width, self.height, len(self.payload)) + self.payload

    def vector(self):
        """Read only the existing native VECT/CDrawCell allocation; never VE."""
        from 原生界面样式 import GroupArchive
        p = self.payload
        if self.kind != 16 or len(p) < 87 or p[:2] != b'BM' or p[54:58] != b'VECT':
            raise FormatError('Expected an existing native BMP/VECT resource')
        size, reserved, offset = struct.unpack_from('<III', p, 2)
        header, width, height, planes, depth, compression, pixels = struct.unpack_from('<IiiHHII', p, 14)
        if (size != len(p) or reserved != 0 or offset != 54 or header != 40 or
            (width, height) != (self.width, self.height) or min(width, height) <= 0 or
            planes != 1 or depth != 24 or compression != 0 or
            pixels != ((width * 3 + 3) // 4 * 4) * height or len(p) != 54 + pixels):
            raise FormatError('Unproven VECT BMP allocation')
        length = struct.unpack_from('<I', p, 58)[0]
        end = 70 + length
        if not 87 <= end <= len(p) or p[70:87] != CELL_TAG:
            raise FormatError('Unproven VECT root envelope')
        root = ControlRecord(0x503a, p[87:end], b'', 0)
        group = GroupArchive.parse(root)
        # The Stu VECT CDrawCell stores a 10000 metadata word and three
        # zero DWORDs after its children. Keep those bytes inside the root.
        metadata = group.common.metadata.value
        has_stu_root_metadata = len(metadata) == 16 and metadata[-4:] == STU_VECT_METADATA_WORD
        expected_tail = bytes(12) if has_stu_root_metadata else b''
        if group.tail != expected_tail or group.to_record().payload != root.payload:
            raise FormatError('VECT root is not a complete native group')
        return group, end

    def edit_vector(self, operations):
        import control_patch as cp
        group, end = self.vector()
        if not isinstance(operations, list) or not operations:
            raise ValueError('Vector edit requires child operations')
        paths = []
        for item in operations:
            if not isinstance(item, dict) or set(item) != {'path', 'sha256', 'edits'}:
                raise ValueError('Vector child requires path/sha256/edits')
            path = item['path']; original = cp.at_path(group.children, path)
            if any(path[:len(p)] == p or p[:len(path)] == path for p in paths):
                raise ValueError('Overlapping vector child paths')
            paths.append(path)
            if hashlib.sha256(original.payload).hexdigest() != item['sha256']:
                raise ValueError('Vector child preimage SHA differs')
            allowed = {'bounds', 'fill', 'border'}
            if original.type_id == 0x5008:
                allowed.add('font')
            if not isinstance(item['edits'], dict) or not item['edits'] or set(item['edits']) - allowed:
                raise ValueError('Vector edits support child geometry/fill/border and fixed-size native label fonts')
            changes = dict(item['edits'])
            selected = original
            if original.type_id == 0x5009 and 'bounds' in changes:
                selected = _vector_bitmap_bounds(selected, changes.pop('bounds'))
            font = changes.pop('font', None)
            if changes:
                selected = cp.edit(selected, changes)
            if 'font' in item['edits']:
                selected = _vector_label_font(selected, font)
            cp.replace_path(group.children, path, selected)
        root = group.to_record().payload
        if len(root) != end - 87:
            raise ValueError('Vector edit would change allocation; original padding must be preserved')
        self.payload = self.payload[:87] + root + self.payload[end:]
        self.vector()

    def validate_raster(self):
        if self.kind not in (0, 2):
            raise ValueError('Expected an existing kind-0 BMP or kind-2 raster resource')
        info = raster_details(self.payload)
        if self.kind == 0 and _native_bitmap_payload(self.payload) is None:
            raise ValueError('Kind-0 resource requires the original 24-bit BMP layout')
        if (info['width'], info['height']) != (self.width, self.height):
            raise ValueError('Original raster dimensions disagree with its resource envelope')

    def replace_raster(self, data):
        self.validate_raster()
        after = raster_details(data)
        if self.kind == 0:
            data = _native_bitmap_payload(data)
            if data is None:
                raise ValueError('Kind-0 raster replacement requires a standard 24-bit BMP')
        # Keep the existing kind and identity, including earlier kind-2 BMPs.
        self.width, self.height, self.payload = after['width'], after['height'], data
