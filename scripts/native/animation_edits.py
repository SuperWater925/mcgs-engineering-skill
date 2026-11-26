"""Bounded edits of the serialized CDraw animation list."""
import copy
import hashlib
import struct

from mcs_window_archive import Reader, write_count, write_cstring
from 原生界面样式 import CommonEnvelope, animation
from 可见动画归档 import VisibleObject, SUPPORTED_TYPES, CLASS_HEADER


BLINK_ENUMS = (("speed", ("fast", "normal", "slow")), ("mode", ("visibility", "properties")))
BLINK_COLORS = ("text_color", "border_color", "fill_color")


def _blink_properties(words):
    properties = {}
    for (key, labels), value in zip(BLINK_ENUMS, words):
        if value < len(labels):
            properties[key] = labels[value]
        else:
            properties[key + "_raw"] = value
    properties.update({key: value & 0xffffff for key, value in zip(BLINK_COLORS, words[2:])})
    return properties


def _items(common):
    reader = Reader(common.prefix, common.animation_start)
    count = reader.count()
    result = [animation(reader) for _ in range(count)]
    if reader.pos != common.animation_end:
        raise ValueError("Animation list extent differs")
    return result


def _tag_kind(raw):
    reader = Reader(raw)
    tag = reader.u16()
    if tag == 0xffff:
        return "declaration", 2
    if tag == 0x7fff:
        return ("class" if reader.u32() & 0x80000000 else "object"), reader.pos
    return ("class" if tag & 0x8000 else "object"), reader.pos


def inspect_items(common):
    return [
        {"index": index, "class": detail["class_name"], "sha256": hashlib.sha256(raw).hexdigest(),
         "independent": raw.startswith(b"\xff\xff"), "tag": _tag_kind(raw)[0], "expression": detail["expression"],
         **{key: detail[key] for key in ("mode", "thresholds", "off_text", "on_text") if key in detail},
         **({"colors": [value & 0xffffff for value in detail["colors"]]} if "colors" in detail else {}),
         **(_blink_properties(detail["blink_words"]) if "blink_words" in detail else {})}
        for index, (detail, raw) in enumerate(_items(common))
    ]


def _visible_values(item, fields):
    if not isinstance(fields, dict) or not fields or set(fields) - {"expression", "mode"}:
        raise ValueError("Visible edits require expression or mode")
    if "expression" in fields:
        expression = fields["expression"]
        if not isinstance(expression, str) or not expression.strip() or "\0" in expression:
            raise ValueError("Expected a nonempty visibility expression without NUL")
        item.expression = expression
    if "mode" in fields:
        mode = fields["mode"]
        if type(mode) is not int or mode not in (0, 1):
            raise ValueError("Visibility mode must be 0 or 1")
        item.mode = mode
    return item.to_bytes()


def _edit_fields(name, raw, fields):
    kind, tag_end = _tag_kind(raw)
    if kind == "object":
        raise ValueError("Animation object-map references have no independent body")
    if kind == "class":
        # The common parser resolved this class and checked schema 0. Its body
        # has the same serializer as a declaration; preserve the original tag.
        label = name.encode("ascii")
        header = struct.pack("<HHH", 0xffff, 0, len(label)) + label
        edited = _edit_fields(name, header + raw[tag_end:], fields)
        return raw[:tag_end] + edited[len(header):]
    reader = Reader(raw)
    if name == "CAniVisible":
        visible = VisibleObject.parse(reader)
        if reader.pos != len(raw):
            raise ValueError("Visibility extent differs")
        return _visible_values(visible, fields)
    simple = {"CAniBrush", "CAniTextColor", "CAniOutput", "CAniBlink", "CAniVMove", "CAniSize"}
    if name not in simple:
        raise ValueError("Field editing is unsupported for " + name)
    allowed = {"expression"}
    if name in {"CAniBrush", "CAniTextColor"}:
        allowed |= {"colors", "thresholds"}
    if name == "CAniOutput":
        allowed |= {"off_text", "on_text"}
    if name == "CAniBlink":
        allowed.update(key for key, _ in BLINK_ENUMS)
        allowed.update(BLINK_COLORS)
    if name == "CAniVMove":
        allowed |= {"offsets", "values"}
    if not isinstance(fields, dict) or not fields or set(fields) - allowed:
        raise ValueError("Unsupported fields for " + name)
    reader.take(4)
    reader.take(reader.u16())
    reader.take(4)
    start = reader.pos
    original, wire, wide = reader.cstring()
    value = fields.get("expression", original)
    if "expression" in fields and (not isinstance(value, str) or not value.strip() or "\0" in value):
        raise ValueError("Expected nonempty animation expression without NUL")
    prefix = raw[:start] + (wire if original == value else write_cstring(value, wide))
    tail = bytearray(raw[reader.pos:])
    if name in {"CAniBrush", "CAniTextColor"}:
        scan = Reader(tail)
        for key in ("thresholds", "colors"):
            count = scan.count()
            pos = scan.pos
            scan.take(count * 4)
            if key not in fields:
                continue
            values = fields[key]
            if not isinstance(values, list) or len(values) != count:
                raise ValueError("Animation array length differs for " + key)
            for i, number in enumerate(values):
                if key == "colors":
                    if type(number) is not int or not 0 <= number <= 0xffffff:
                        raise ValueError("Expected integer COLORREF")
                    tail[pos + i*4:pos + i*4 + 3] = number.to_bytes(3, "little")
                else:
                    if type(number) not in (float, int) or not -3.4028234663852886e38 <= number <= 3.4028234663852886e38:
                        raise ValueError("Expected finite float32 threshold")
                    struct.pack_into("<f", tail, pos + i*4, number)
    if name == "CAniOutput" and fields.keys() & {"off_text", "on_text"}:
        scan = Reader(tail)
        parts = []
        for key in ("off_text", "on_text"):
            original_text, original_wire, text_wide = scan.cstring()
            replacement = fields.get(key, original_text)
            if not isinstance(replacement, str) or "\0" in replacement:
                raise ValueError("Expected output text without NUL")
            parts.append(original_wire if replacement == original_text else write_cstring(replacement, text_wide))
        if len(tail) - scan.pos != 16:
            raise ValueError("Unexpected output animation tail")
        tail = b"".join(parts) + tail[scan.pos:]
    if name == "CAniBlink":
        _edit_blink_properties(tail, fields)
    if name == "CAniVMove":
        if len(tail) != 16:
            raise ValueError("Unexpected vertical movement tail")
        for key, offset in (("offsets", 0), ("values", 8)):
            if key in fields:
                tail[offset:offset + 8] = _movement_pair(key, fields[key])
    return prefix + tail


def _edit_blink_properties(tail, fields):
    if len(tail) != 20:
        raise ValueError("Unexpected blink animation tail")
    for index, (key, labels) in enumerate(BLINK_ENUMS):
        if key in fields:
            value = fields[key]
            if value not in labels:
                raise ValueError("Blink " + key + " must be " + ", ".join(labels))
            struct.pack_into("<I", tail, index * 4, labels.index(value))
    for index, key in enumerate(BLINK_COLORS, start=2):
        if key in fields:
            value = fields[key]
            if type(value) is not int or not 0 <= value <= 0xffffff:
                raise ValueError("Blink colors require integer COLORREF")
            offset = index * 4
            tail[offset:offset + 3] = value.to_bytes(3, "little")


def _movement_pair(key, values):
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError("Vertical movement requires a pair of " + key)
    if key == "offsets":
        if any(type(v) is not int or not -2**31 <= v < 2**31 for v in values):
            raise ValueError("Vertical movement requires two signed 32-bit offsets")
        return struct.pack("<2i", *values)
    if any(type(v) not in (int, float) or not -3.4028234663852886e38 <= v <= 3.4028234663852886e38 for v in values):
        raise ValueError("Vertical movement requires two finite float32 values")
    return struct.pack("<2f", *values)


def _new_animation(record, spec):
    if not isinstance(spec, dict) or "class" not in spec or "expression" not in spec:
        raise ValueError("New animation requires class and expression")
    name = spec["class"]
    fields = {k: v for k, v in spec.items() if k != "class"}
    initial = struct.pack("<f", 1)
    # Default bodies independently measured in native page 20/26 archives.
    if name == "CAniBrush" and record.type_id in (0x5004, 0x5006, 0x5008):
        thresholds = spec.get("thresholds", [0.0, 1.0])
        colors = spec.get("colors", [255, 65280])
        if not isinstance(thresholds, list) or not isinstance(colors, list) or not thresholds or len(thresholds) != len(colors):
            raise ValueError("New palette requires nonempty aligned threshold and color arrays")
        if any(type(x) not in (int, float) or not -3.4028234663852886e38 <= x <= 3.4028234663852886e38 for x in thresholds):
            raise ValueError("Expected finite float32 thresholds")
        values = struct.pack(f"<{len(thresholds)}f", *thresholds)
        rounded = struct.unpack(f"<{len(thresholds)}f", values)
        if any(a >= b for a, b in zip(rounded, rounded[1:])):
            raise ValueError("Palette thresholds must increase after float32 conversion")
        if any(type(x) is not int or not 0 <= x <= 0xffffff for x in colors):
            raise ValueError("Expected integer COLORREF")
        tail = write_count(len(colors)) + values + write_count(len(colors)) + struct.pack(f"<{len(colors)}I", *colors)
    elif name == "CAniOutput" and record.type_id == 0x5008:
        tail = write_cstring("") * 2 + struct.pack("<4I", 1, 0, 1, 1)
    elif name == "CAniBlink" and record.type_id == 0x5039:
        tail = struct.pack("<5I", 1, 0, 0, 0, 0xffffff)
    elif name == "CAniVMove" and record.type_id == 0x5008:
        tail = _movement_pair("offsets", fields.pop("offsets", None)) + _movement_pair("values", fields.pop("values", None))
    elif name == "CAniSize" and record.type_id == 0x5004:
        # Identical complete size item in the Pro N-series and Stu 4.3-inch
        # vendor examples. Keep the initial DWORD and six body fields exact.
        initial = bytes.fromhex("79000000")
        tail = bytes.fromhex("0300000000000000000000000000c8426400000000000000")
    else:
        raise ValueError("No measured animation factory for class and control")
    label = name.encode("ascii")
    raw = struct.pack("<HHH", 0xffff, 0, len(label)) + label + initial + write_cstring("") + tail
    return _edit_fields(name, raw, fields)


def _reference(index, class_ref, large):
    if large or index >= 0x7fff:
        return struct.pack("<HI", 0x7fff, index | (0x80000000 if class_ref else 0))
    return struct.pack("<H", index | (0x8000 if class_ref else 0))


def _map_rows(previous):
    cursor = 1
    rows = []
    for _, raw in previous:
        kind, end = _tag_kind(raw)
        tag = int.from_bytes(raw[2:6] if end == 6 else raw[:2], "little")
        if kind == "object":
            rows.append((tag, None, b""))
            continue
        if kind == "declaration":
            cls = cursor
            cursor += 1
            end = 6 + int.from_bytes(raw[4:6], "little")
        else:
            cls = tag & (0x7fffffff if end == 6 else 0x7fff)
        rows.append((cursor, cls, raw[end:]))
        cursor += 1
    return rows


def edit_items(record, desired):
    """Desired list cites each retained original index, in final order."""
    if not isinstance(desired, list):
        raise ValueError("animations must be an ordered list")
    common = CommonEnvelope.parse(record)
    previous = _items(common)
    rows = _map_rows(previous)
    cursor = 1
    classes, objects = {}, {}
    seen = set()
    encoded = []
    for item in desired:
        if not isinstance(item, dict):
            raise ValueError("Expected an animation item")
        if set(item) == {"new_animation"}:
            raw = _new_animation(record, item["new_animation"])
            cursor += 2
        elif set(item) == {"new_visible"}:
            if record.type_id not in SUPPORTED_TYPES:
                raise ValueError("No visibility factory for this control class")
            fields = item["new_visible"]
            if not isinstance(fields, dict) or "expression" not in fields:
                raise ValueError("New visibility requires expression")
            raw = _visible_values(VisibleObject.new("1"), fields)
            cursor += 2
        else:
            clone = "clone_index" in item
            key = "clone_index" if clone else "index"
            if set(item) not in ({key, "sha256"}, {key, "sha256", "set"}):
                raise ValueError("Expected original animation index and sha256")
            index = item[key]
            if type(index) is not int or not 0 <= index < len(previous) or (not clone and index in seen):
                raise ValueError("Invalid or duplicate animation source index")
            if not clone:
                seen.add(index)
            detail, original = previous[index]
            if hashlib.sha256(original).hexdigest() != item["sha256"]:
                raise ValueError("Animation preimage differs")
            owner, cls, body = rows[index]
            kind, end = _tag_kind(original)
            if kind == "object":
                if clone or "set" in item or owner not in objects:
                    raise ValueError("Object references require their retained earlier owner")
                raw = _reference(objects[owner], False, end == 6)
            else:
                label = detail["class_name"].encode("ascii")
                header = struct.pack("<HHH", 0xffff, 0, len(label)) + label
                if "set" in item:
                    body = _edit_fields(detail["class_name"], header + body, item["set"])[len(header):]
                if cls in classes:
                    tag = _reference(classes[cls], True, kind == "class" and end == 6)
                else:
                    classes[cls] = cursor
                    cursor += 1
                    tag = header
                if not clone:
                    objects[owner] = cursor
                cursor += 1
                raw = tag + body
        encoded.append(raw)
    if encoded == [raw for _, raw in previous]:
        return copy.deepcopy(record)
    if any("new_visible" in item or ("clone_index" in item and previous[item["clone_index"]][0]["class_name"] == "CAniVisible") for item in desired):
        visible_count = 0
        for item in desired:
            index = item.get("index", item.get("clone_index"))
            if "new_visible" in item or (index is not None and previous[index][0]["class_name"] == "CAniVisible"):
                visible_count += 1
        if visible_count > 1:
            raise ValueError("A control may receive only one visible condition")
    offset = common.animation_end
    flags = struct.unpack_from("<H", record.payload, offset)[0]
    result = copy.deepcopy(record)
    count_reader = Reader(record.payload, common.animation_start)
    count = count_reader.count()
    count_wire = (record.payload[common.animation_start:count_reader.pos] if count == len(encoded)
                  else write_count(len(encoded)))
    result.payload = (record.payload[:common.animation_start] + count_wire
                      + b"".join(encoded) + struct.pack("<H", flags | 1) + record.payload[offset+2:])
    after = CommonEnvelope.parse(result)
    if [raw for _, raw in _items(after)] != encoded or after.to_record().payload != result.payload:
        raise ValueError("Changed animation list roundtrip differs")
    return result
