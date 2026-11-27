"""Edit verified fields of existing ObjData alarm items."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import math
import struct

import native_format as native
from mcs_button_control import CString
from mcs_window_archive import Reader
from offline_structure import exact
from native_format import language_texts as _language_texts


BASE_VALUE_FORMATS = {40: "<f", 52: "<d"}
BASE_VALUE_OFFSET = 16
UPPER_LIMIT_FIELD = "upper_limit_value"
SWITCH_EQUALS_FIELD = "switch_equals_value"
MESSAGE_FIELD = "message_text_id"
UNVERIFIED_MIRROR = "Nonempty Alarm table has no verified mirror mapping to ObjData definitions"


def _physical_alarm_rows(data):
    rows = data.get("Alarm", {}).get("rows")
    if not isinstance(rows, list):
        raise ValueError("The project has no readable Alarm table")
    return rows


def _physical_object_id_counts(rows):
    if any(type(row.get("iDataObjID")) is not int for row in rows):
        return None
    return Counter(row["iDataObjID"] for row in rows)


def inspect_alarm_storage(data, records):
    rows = _physical_alarm_rows(data)
    result = {"physical_rows": len(rows), "objdata_alarm_items": None,
              "physical_to_objdata_mapping_verified": False}
    if records.alarm_spans is not None:
        result["objdata_alarm_items"] = sum(map(len, records.alarm_spans.values()))
    if not rows:
        return result
    result.update(physical_source="Alarm", objdata_source="System/ObjData",
                  active_storage_verified=False, objdata_write_unavailable=UNVERIFIED_MIRROR)
    ids = _physical_object_id_counts(rows)
    if ids is None:
        return result
    object_ids = {record["id"] for record in records}
    result["physical_rows_with_existing_object_id"] = sum(count for ident, count in ids.items() if ident in object_ids)
    if records.alarm_spans is not None:
        result["physical_rows_with_objdata_alarm_object_id"] = sum(count for ident, count in ids.items()
                                                                   if records.alarm_spans.get(ident))
    return result


def _require_objdata_alarms(records):
    if records.alarm_spans is None:
        raise ValueError("ObjData alarm items lack unique verified record boundaries")


def _require_alarm_layout(data, records):
    if _physical_alarm_rows(data):
        raise ValueError(UNVERIFIED_MIRROR)
    _require_objdata_alarms(records)


def _message_reference(record, span):
    start, end, item_width = span
    reader = Reader(record["extension"], start + item_width)
    message = CString.parse(reader)
    if reader.pos + (4 if item_width == 52 else 0) != end:
        raise ValueError("Native alarm message CString does not match its item boundary")
    return message, reader.pos, native.language_text_id(message.value)


def _snapshot(record, index, span, language_texts=None):
    start, end, item_width = span
    item = record["extension"][start:end]
    packed, enabled, alarm_type = struct.unpack_from("<III", item)
    group, priority = packed >> 16, packed & 0xffff
    result = {
        "variable": {"id": record["id"], "name": record["name"]},
        "index": index, "sha256": sha256(item).hexdigest(),
        "group": group, "priority": priority, "alarm_type": alarm_type,
        "enabled": bool(enabled) if enabled in (0, 1) else None,
        "editable": (record["kind"] in (1, 2) and enabled in (0, 1)
                     and 0 <= alarm_type <= 17 and group <= 255 and priority <= 100),
    }
    format_code = BASE_VALUE_FORMATS.get(item_width)
    result["upper_limit_value_editable"] = False
    result["switch_equals_value_editable"] = False
    if result["editable"] and format_code is not None and native.u32(item, 12) == 0xffffffff:
        value, = struct.unpack_from(format_code, item, BASE_VALUE_OFFSET)
        if record["kind"] == 2 and alarm_type == 2 and math.isfinite(value):
            result["upper_limit_value_editable"] = True
            result[UPPER_LIMIT_FIELD] = value
        if record["kind"] == 1 and alarm_type == 6 and value in (0, 1):
            result["switch_equals_value_editable"] = True
            result[SWITCH_EQUALS_FIELD] = int(value)
    result["message_text_id_editable"] = False
    if language_texts is not None:
        _, _, text_id = _message_reference(record, span)
        translations = language_texts.get(text_id)
        if translations:
            result[MESSAGE_FIELD] = text_id
            result["message_translations"] = translations
            result["message_text_id_editable"] = result["editable"]
    return result


def inspect_alarm_definitions(data, records):
    rows = _physical_alarm_rows(data)
    _require_objdata_alarms(records)
    if not records.alarm_spans:
        return []
    language_texts = None
    if not rows:
        try:
            language_texts = _language_texts(data)
        except ValueError:
            pass
    definitions = [_snapshot(record, index, span, language_texts)
                   for record in records
                   for index, span in enumerate(records.alarm_spans.get(record["id"], ()))]
    if rows:
        ids = _physical_object_id_counts(rows)
        for item in definitions:
            hits = ids[item["variable"]["id"]] if ids is not None else None
            item.update(storage_source="System/ObjData", physical_rows_with_same_object_id=hits,
                        editable=False, upper_limit_value_editable=False,
                        switch_equals_value_editable=False, message_text_id_editable=False)
    return definitions


def _encoded_upper_limit(value, item_width):
    if type(value) in (int, float):
        format_code = BASE_VALUE_FORMATS[item_width]
        try:
            encoded = struct.pack(format_code, value)
            if math.isfinite(struct.unpack(format_code, encoded)[0]):
                return encoded
        except (OverflowError, struct.error):
            pass
    raise ValueError("Alarm upper_limit_value must fit the native finite floating-point field")


def edit_alarm_definitions(data, operations):
    if not isinstance(operations, list) or not operations:
        raise ValueError("alarm_edits requires a nonempty array of existing alarm edits")
    row, = [item for item in data["System"]["rows"] if item["strName"] == "ObjData"]
    original = native.archive(row["lbContext"])
    records = native.variables(original)
    _require_alarm_layout(data, records)
    if native.pack_variables(records) != original:
        raise ValueError("Original ObjData alarm archive did not round-trip")
    by_id = {r["id"]:r for r in records}
    seen = set()
    language_texts = None
    fields = {"group":255, "priority":100}
    required = {"variable", "index", "sha256"}
    editable_fields = fields.keys() | {"enabled", UPPER_LIMIT_FIELD, SWITCH_EQUALS_FIELD, MESSAGE_FIELD}
    for operation in operations:
        if not isinstance(operation, dict) or not required <= set(operation):
            raise ValueError("Alarm edit requires variable, index and sha256")
        updates = set(operation) - required
        if not updates or updates - editable_fields:
            raise ValueError("Existing alarm edits accept group, priority, enabled, upper_limit_value, switch_equals_value and message_text_id")
        for name in updates & fields.keys():
            value = operation[name]
            if type(value) is not int or not 0 <= value <= fields[name]:
                raise ValueError("Alarm " + name + " is outside the verified integer range")
        if "enabled" in updates and type(operation["enabled"]) is not bool:
            raise ValueError("Alarm enabled must be a boolean")
        selector = operation["variable"]
        exact(selector, ("id", "name"), "Alarm variable identity")
        ident = selector["id"]
        record = by_id.get(ident) if type(ident) is int else None
        if record is None or record["name"] != selector["name"]:
            raise ValueError("Alarm variable ID or name differs from the current scalar")
        index = operation["index"]
        spans = records.alarm_spans.get(ident, ())
        if type(index) is not int or not 0 <= index < len(spans) or (ident, index) in seen:
            raise ValueError("Alarm index is nonexistent or repeated")
        seen.add((ident, index))
        before = _snapshot(record, index, spans[index])
        if not before["editable"]:
            raise ValueError("Selected native alarm is outside the verified metadata layout")
        if before["sha256"] != operation["sha256"]:
            raise ValueError("Alarm item preimage SHA differs")
        packed = (operation.get("group", before["group"]) << 16) | operation.get("priority", before["priority"])
        at, _, item_width = spans[index]
        extension = bytearray(record["extension"])
        struct.pack_into("<I", extension, at, packed)
        if "enabled" in updates:
            # Both editors serialize the "Enable" checkbox as the second UInt32.
            struct.pack_into("<I", extension, at + 4, operation["enabled"])
        if UPPER_LIMIT_FIELD in updates:
            if not before["upper_limit_value_editable"]:
                raise ValueError("Upper limit requires a floating upper-limit item with the verified default parameter source")
            encoded = _encoded_upper_limit(operation[UPPER_LIMIT_FIELD], item_width)
            start = at + BASE_VALUE_OFFSET
            extension[start:start + len(encoded)] = encoded
        if SWITCH_EQUALS_FIELD in updates:
            value = operation[SWITCH_EQUALS_FIELD]
            if type(value) is not int or value not in (0, 1):
                raise ValueError("Alarm switch_equals_value must be integer 0 or 1")
            if not before["switch_equals_value_editable"]:
                raise ValueError("Switch equals requires an integer switch item with the verified default parameter source")
            struct.pack_into(BASE_VALUE_FORMATS[item_width], extension, at + BASE_VALUE_OFFSET, value)
        if MESSAGE_FIELD in updates:
            text_id = operation[MESSAGE_FIELD]
            if type(text_id) is not int or not 0 <= text_id <= 0xffffffff:
                raise ValueError("Alarm message_text_id must be a native uint32 text ID")
            if language_texts is None:
                language_texts = _language_texts(data)
            old, text_end, old_id = _message_reference(record, spans[index])
            if not language_texts.get(old_id) or not language_texts.get(text_id):
                raise ValueError("Current or requested alarm text ID has no verified existing translations")
            old.value = "\x07" + str(text_id)
            encoded = old.to_bytes()
            text_start = at + item_width
            extension[text_start:text_end] = encoded
            size_delta = len(encoded) - (text_end - text_start)
            if size_delta:
                records.alarm_spans[ident] = tuple(
                    (start + (size_delta if ordinal > index else 0),
                     end + (size_delta if ordinal >= index else 0), width)
                    for ordinal, (start, end, width) in enumerate(spans))
        record["extension"] = bytes(extension)
    changed = native.pack_variables(records)
    actual = native.variables(changed)
    if (actual != records or actual.document_header != records.document_header
            or actual.alarm_spans != records.alarm_spans):
        raise ValueError("Alarm field readback changed another field or the archive boundaries")
    row["lbContext"] = native.wrap_like(row["lbContext"], changed)
