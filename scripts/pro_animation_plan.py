"""Prepare one control-animation-list session action from an exact native inspection."""
import argparse
from collections import Counter
from copy import deepcopy
import json
import re
import struct
from pathlib import Path


OUTPUT_CLONE_WORDS = {"5c": 0, "60": 1, "68": 1, "6c": 1}
SIZE_CLONE_WORDS = {"8", "c", "30", "34", "38", "3c", "40", "44", "48", "4c"}
VMOVE_CLONE_WORDS = {"8", "c", "30", "34", "38", "3c", "40"}
PALETTE_CLASSES = {"CAniBrush", "CAniTextColor"}
BLINK_WORDS = frozenset("8 c 30 34 38 3c 40 44 48 4c 50".split())
BLINK_ENUMS = {"speed": ("40", ("fast", "normal", "slow")), "mode": ("44", ("visibility", "properties"))}
BLINK_COLORS = {"text_color": "48", "border_color": "4c", "fill_color": "50"}
BLINK_EDITABLE_WORDS = {offset for offset, _ in BLINK_ENUMS.values()} | set(BLINK_COLORS.values())
INPUT_WORDS = frozenset("8 c 30 4c 50 54 88 8c 90 94 98 9c".split())
INPUT_STRINGS = frozenset("2c 38 40 48 58 5c".split())
INPUT_CACHES = {"14": "", "60": "", "74": ""}
SCALAR_KINDS = {1, 2, 3}


def variable_catalog(records):
    """Normalize unique names from the current native data-catalog records."""
    if not isinstance(records, list):
        raise ValueError("Native data catalog records must be a list")
    variables = {}
    counts = Counter()
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("Invalid native data catalog record")
        name, number, kind = row.get("name"), row.get("native_id"), row.get("native_type")
        if (not isinstance(name, str) or not name or "\0" in name
                or type(number) is not int or type(kind) is not int):
            raise ValueError("Native data catalog record needs a name, ID and type")
        counts[name] += 1
        variables[name] = {"id": number, "kind": kind}
    return {name: value for name, value in variables.items() if counts[name] == 1}


def catalog_from_receipt(document):
    catalogs = [row["before"]["records"] for row in document.get("action_preimages", [])
                if row.get("kind") == "data-catalog" and row.get("before", {}).get("module_id") == 2]
    if not catalogs:
        return None
    catalog = variable_catalog(catalogs[0])
    if any(variable_catalog(records) != catalog for records in catalogs[1:]):
        raise ValueError("Conflicting native data catalogs in the inspection receipt")
    return catalog


def observed_output_clone(record, changes):
    words = record["words_uint32"]
    cache = record["byte_arrays_hex"]
    if (len(words) != 14 or words.get("c") != 0 or set(cache) != {"14"} or len(cache["14"]) != 64
            or any(words.get(key) != value for key, value in OUTPUT_CLONE_WORDS.items())):
        raise ValueError("This compiled CAniOutput does not match the observed original serializer layout")
    requested_words = changes.get("words_uint32", {})
    if any(requested_words.get(key, value) != value for key, value in OUTPUT_CLONE_WORDS.items()):
        raise ValueError("Changing these output flags and restoring a compiled original clone requires separate edits")
    return {**changes, "words_uint32": {**requested_words, **OUTPUT_CLONE_WORDS}}


def observed_size_clone(record, changes):
    source = record["strings"]
    requested = changes.get("strings")
    if set(changes) != {"strings"} or not isinstance(requested, dict) or set(requested) != {"2c"}:
        return None
    expression = requested["2c"]
    if not isinstance(expression, str) or not expression.strip() or "\0" in expression:
        raise ValueError("Size expression must be nonempty text without NUL")
    if (set(source) != {"2c"} or set(record["words_uint32"]) != SIZE_CLONE_WORDS or
            record["arrays"] or set(record["byte_arrays_hex"]) != {"14"}):
        raise ValueError("Compiled CAniSize does not match the observed original serialization layout")
    if expression == source["2c"]:
        raise ValueError("Size expression is unchanged")
    # The original private serializer clears these two dimensions. Keep
    # their current values and leave the derived expression cache to Root85.
    return {**changes, "words_uint32": {key: record["words_uint32"][key] for key in ("48", "4c")}}


def validate_observed_vmove_clone(record, changes):
    words = record["words_uint32"]
    dimension = words.get("40")
    caches = record["byte_arrays_hex"]
    if (set(words) != VMOVE_CLONE_WORDS or type(dimension) is not int or not 0 < dimension <= 0xffffffff
            or set(record["strings"]) != {"2c"} or record["arrays"] or set(caches) != {"14"}
            or not isinstance(caches["14"], str) or (caches["14"] and not re.fullmatch(
                r"030000000000000001000000030000000000000026[0-9a-f]{8}2c0000000001", caches["14"]))):
        raise ValueError("CAniVMove does not match the observed original serialization layout")
    expression = changes["strings"]["2c"]
    if expression == record["strings"]["2c"]:
        raise ValueError("Vertical movement expression is unchanged")


def observed_palette_clone(record, changes):
    arrays = changes.get("arrays")
    if set(changes) != {"arrays"} or not isinstance(arrays, dict) or not arrays or arrays.keys() - {"30", "44"}:
        return False
    original = record["arrays"]
    if (set(original) != {"30", "44"} or len(original["30"]) != len(original["44"])
            or set(record["strings"]) != {"2c"} or set(record["byte_arrays_hex"]) != {"14"}):
        raise ValueError("Compiled palette does not match the observed original serialization layout")
    if any(not isinstance(values, list) or len(values) != len(original[key]) for key, values in arrays.items()):
        raise ValueError("Palette edit must retain each native array length")
    if "44" in arrays and any(type(new) is not int or not 0 <= new <= 0xffffffff or (new ^ old) & 0xff000000
                              for old, new in zip(original["44"], arrays["44"])):
        raise ValueError("Palette color edit must retain each native high byte")
    if all(values == original[key] for key, values in arrays.items()):
        raise ValueError("Palette arrays are unchanged")
    return True


def observed_blink_clone(record, changes):
    if changes.keys() - {"strings", "words_uint32"}:
        return False
    words, strings, caches = record.get("words_uint32", {}), record.get("strings", {}), record.get("byte_arrays_hex", {})
    if (set(words) != BLINK_WORDS or {key: words[key] for key in ("8", "c", "30", "3c")}
            != {"8": 0x3001, "c": 0x3f800000, "30": 0, "3c": 0}
            or record.get("enabled_raw_byte") != 10 or set(strings) != {"2c"} or record.get("arrays") != {}
            or set(caches) != {"14"} or not isinstance(caches["14"], str)):
        return False
    requested_strings, requested_words = changes.get("strings", {}), changes.get("words_uint32", {})
    if (not isinstance(requested_strings, dict) or "strings" in changes and set(requested_strings) != {"2c"}
            or not isinstance(requested_words, dict) or requested_words.keys() - BLINK_EDITABLE_WORDS):
        return False
    if "2c" in requested_strings:
        expression = requested_strings["2c"]
        if not isinstance(expression, str) or not expression.strip() or "\0" in expression:
            raise ValueError("Blink expression must be nonempty text without NUL")
    for key, value in requested_words.items():
        if type(value) is not int or not 0 <= value <= 0xffffffff:
            raise ValueError("Blink updates must use exact native unsigned words")
        if (key == "40" and value not in (0, 1, 2)) or (key == "44" and value not in (0, 1)):
            raise ValueError("Unknown native Blink speed or mode")
        if key in BLINK_COLORS.values() and (value ^ words[key]) & 0xff000000:
            raise ValueError("A Blink color update must preserve its native high byte")
    if not (any(strings[key] != value for key, value in requested_strings.items())
            or any(words[key] != value for key, value in requested_words.items())):
        raise ValueError("Keep an unchanged Blink animation instead of replacing it")
    return True


def visible_factory_record():
    # Factory readback for the verified CAniVisible layout, before compilation.
    return {"class": "CAniVisible", "words_uint32": {"8": 12299, "c": 1065353216, "30": 0},
            "enabled_raw_byte": 10, "strings": {"2c": ""}, "arrays": {},
            "byte_arrays_hex": {"14": ""}}


def visible_definition(record, fields):
    if record["class"] != "CAniVisible" or not isinstance(fields, dict) or not fields:
        raise ValueError("visibility requires a CAniVisible record and expression or mode")
    if fields.keys() - {"expression", "mode"}:
        raise ValueError("Unknown visibility field")
    changes = {}
    if "expression" in fields:
        expression = fields["expression"]
        if not isinstance(expression, str) or not expression.strip() or "\0" in expression:
            raise ValueError("Visible expression must be nonempty and contain no NUL")
        changes["strings"] = {"2c": expression}
    if "mode" in fields:
        mode = fields["mode"]
        if type(mode) is not int or mode not in (0, 1):
            raise ValueError("Visible mode must be 0 or 1")
        changes["words_uint32"] = {"30": mode}
    return changes


def rebuild_visible_update(source, expected, changes, clone=False):
    """Replace a compiled visible condition through its native factory.

    The original serializer does not retain the derived expression cache.
    Check every other expected member against the private factory result.
    """
    cache = source.get("byte_arrays_hex", {})
    if (source["class"] != "CAniVisible" or set(cache) != {"14"} or not cache["14"]
            or (source == expected and not clone) or set(changes) - {"strings", "words_uint32"}):
        return None
    if set(changes.get("strings", {})) - {"2c"} or set(changes.get("words_uint32", {})) - {"30"}:
        return None
    layout = visible_factory_record()
    if any(set(source.get(field, {})) != set(layout[field])
           for field in ("strings", "words_uint32", "arrays")):
        return None
    expression = expected["strings"]["2c"]
    mode = expected["words_uint32"]["30"]
    if not isinstance(expression, str) or not expression.strip() or "\0" in expression:
        raise ValueError("Visible expression must be nonempty and contain no NUL")
    if type(mode) is not int or mode not in (0, 1):
        raise ValueError("Visible mode must be 0 or 1")
    expected["byte_arrays_hex"]["14"] = ""
    return {"new_class": "CAniVisible",
            "native_member_updates": {"strings": {"2c": expression}, "words_uint32": {"30": mode}}}


def input_binding_preimage(record, fields, catalog):
    if not isinstance(fields, dict) or fields.keys() != {"binding"}:
        raise ValueError("Input animation business fields require a binding")
    name = fields["binding"]
    if not isinstance(name, str) or not name.strip() or "\0" in name:
        raise ValueError("binding must be nonempty text without NUL")
    strings = record.get("strings", {})
    words = record.get("words_uint32", {})
    original_name = strings.get("2c")
    if name == original_name:
        return None
    if (strings.keys() != INPUT_STRINGS or words.keys() != INPUT_WORDS or record.get("arrays") != {}
            or record.get("byte_arrays_hex") != INPUT_CACHES):
        raise ValueError("Input binding requires the observed CAniInput layout with empty caches")
    if catalog is None:
        raise ValueError("Input binding needs the current native data-catalog inspection")
    source, target = catalog.get(original_name), catalog.get(name)
    if source is None or target is None:
        raise ValueError("Both input bindings must be unique names in the current native data catalog")
    if source["id"] != words["88"]:
        raise ValueError("Original input binding ID differs from the current data catalog")
    if source["kind"] not in SCALAR_KINDS or target["kind"] != source["kind"]:
        raise ValueError("Input binding must use a variable of the same scalar type")
    if not 0 <= target["id"] <= 0x7fffffff or target["id"] == source["id"]:
        raise ValueError("Replacement input binding must have a distinct native variable ID")
    return {"source": {"name": original_name, "native_id": source["id"], "native_type": source["kind"]},
            "target": {"name": name, "native_id": target["id"], "native_type": target["kind"]}}


def animation_definition(record, fields):
    """Compile named fields against the actual inspected object's member map."""
    name = record["class"]
    palettes = PALETTE_CLASSES
    supported = palettes | {"CAniOutput", "CAniBlink", "CAniVMove", "CAniSize"}
    allowed = {"expression"}
    if name in palettes:
        allowed.update(("thresholds", "colors"))
    if name == "CAniBlink":
        allowed.update(BLINK_ENUMS)
        allowed.update(BLINK_COLORS)
    if name not in supported or not isinstance(fields, dict) or not fields or fields.keys() - allowed:
        raise ValueError("Unsupported business animation fields for " + name)
    changes = {}
    if "expression" in fields:
        value = fields["expression"]
        if not isinstance(value, str) or not value.strip() or "\0" in value:
            raise ValueError("expression must be nonempty text without NUL")
        changes["strings"] = {"2c": value}
    if name == "CAniBlink":
        updates = {}
        for key, (offset, labels) in BLINK_ENUMS.items():
            if key in fields:
                value = fields[key]
                if value not in labels:
                    raise ValueError("Blink " + key + " must be " + ", ".join(labels))
                updates[offset] = labels.index(value)
        for key, offset in BLINK_COLORS.items():
            if key in fields:
                value = fields[key]
                if type(value) is not int or not 0 <= value <= 0xffffff:
                    raise ValueError("Blink colors require integer COLORREF")
                updates[offset] = (record["words_uint32"][offset] & 0xff000000) | value
        if updates:
            changes["words_uint32"] = updates
    if "thresholds" in fields or "colors" in fields:
        arrays = record.get("arrays", {})
        if set(arrays) != {"30", "44"} or len(arrays["30"]) != len(arrays["44"]):
            raise ValueError("Expected aligned native threshold and COLORREF arrays")
        count = len(arrays["30"])
        updates = {}
        if "thresholds" in fields:
            values = fields["thresholds"]
            if not isinstance(values, list) or len(values) != count:
                raise ValueError("Threshold count must match the captured palette")
            bits = []
            rounded = []
            for value in values:
                if type(value) not in (int, float) or not -3.4028234663852886e38 <= value <= 3.4028234663852886e38:
                    raise ValueError("Expected a finite float32 threshold")
                packed = struct.pack("<f", value)
                bits.append(int.from_bytes(packed, "little"))
                rounded.append(struct.unpack("<f", packed)[0])
            if any(a >= b for a, b in zip(rounded, rounded[1:])):
                raise ValueError("Thresholds must increase after float32 rounding")
            updates["30"] = bits
        if "colors" in fields:
            values = fields["colors"]
            if (not isinstance(values, list) or len(values) != count
                    or any(type(v) is not int or not 0 <= v <= 0xffffff for v in values)):
                raise ValueError("Expected one 24-bit COLORREF per captured entry")
            updates["44"] = [(old & 0xff000000) | color for old, color in zip(arrays["44"], values)]
        changes["arrays"] = updates
    return changes


def select_capture(document, capture_action_id=None):
    if "action_preimages" not in document:
        if capture_action_id is not None:
            raise ValueError("--capture-action-id requires a full inspection receipt")
        return document
    if document.get("ok") is not True:
        raise ValueError("Need a successful animation inspection receipt")
    rows = [row for row in document["action_preimages"]
            if row.get("kind") == "control-animation-list"
            and (capture_action_id is None or row.get("action_id") == capture_action_id)]
    if len(rows) != 1:
        raise ValueError("Select exactly one inspected animation action with --capture-action-id")
    return rows[0]["before"]


def prepare(capture, items, action_id="edit-animations", *, variable_catalog=None):
    page = capture["page"]
    control = capture["target_control"]
    original = capture["items"]
    target = {"page_id": page["page_id"], "page_name": page["page_name"],
              "control_path": control["path"], "control_name": control["name"],
              "class": control["class"], "native_id": control["native_id"], "complete": control["complete"]}
    if not isinstance(items, list) or not isinstance(original, list):
        raise ValueError("Both the captured items and ordered design must be lists")
    rows = []
    retained = set()
    for design in items:
        if not isinstance(design, dict):
            raise ValueError("Each ordered item must be an object")
        choices = {"keep", "clone", "update", "add"} & design.keys()
        if len(choices) != 1:
            raise ValueError("Specify one of keep, clone, update or add")
        op = choices.pop()
        if set(design) - {op, "native_member_updates", "expected_record", "visibility", "fields"}:
            raise ValueError("Unknown animation item field")
        if op == "add":
            if "visibility" in design and design["add"] == "CAniVisible":
                expected = visible_factory_record()
                if not isinstance(design["visibility"], dict) or "expression" not in design["visibility"]:
                    raise ValueError("New visibility animation requires expression")
            elif "expected_record" in design:
                expected = deepcopy(design["expected_record"])
            else:
                raise ValueError("New animation requires an exact factory record")
            if design["add"] != expected["class"]:
                raise ValueError("New class must match the exact expected record")
            row = {"new_class": design["add"]}
        else:
            index = design[op]
            if type(index) is not int or not 0 <= index < len(original):
                raise ValueError("Source index outside the captured list")
            row = {"source": {"control": target, "index": index}}
            expected = deepcopy(original[index])
            if op == "clone":
                row["clone_source"] = True
            else:
                if index in retained:
                    raise ValueError("Repeated source needs an explicit clone")
                retained.add(index)
        changes = design.get("native_member_updates", {})
        if "fields" in design:
            if op not in ("clone", "update") or "visibility" in design or "native_member_updates" in design:
                raise ValueError("Business fields require a captured clone or update with one field notation")
            if expected["class"] == "CAniInput":
                binding = input_binding_preimage(expected, design["fields"], variable_catalog)
                if binding is not None:
                    row["input_binding_preimage"] = binding
                    selected = binding["target"]
                    changes = {"strings": {"2c": selected["name"]}, "words_uint32": {"88": selected["native_id"]}}
            else:
                changes = animation_definition(expected, design["fields"])
        if "visibility" in design:
            if "native_member_updates" in design:
                raise ValueError("Specify visibility or native_member_updates")
            changes = visible_definition(expected, design["visibility"])
            if op == "add":
                changes.setdefault("words_uint32", {"30": 0})
        if not isinstance(changes, dict) or set(changes) - {"strings", "arrays", "words_uint32", "enabled_raw_byte"}:
            raise ValueError("Invalid animation member updates")
        if op == "keep" and changes or op == "update" and not changes:
            raise ValueError("Use keep for unchanged items and update for changed items")
        if op in ("clone", "update") and expected["class"] == "CAniOutput" and expected["byte_arrays_hex"].get("14"):
            changes = observed_output_clone(expected, changes)
            row["restore_observed_output_clone"] = True
            expected["byte_arrays_hex"]["14"] = ""
        if op == "update" and expected["class"] == "CAniSize" and expected["byte_arrays_hex"].get("14"):
            projected = observed_size_clone(expected, changes)
            if projected is not None:
                if index != len(rows):
                    raise ValueError("Keep the original Size animation slot when changing its compiled expression")
                changes = projected
                row["restore_observed_size_clone"] = True
                expected["byte_arrays_hex"]["14"] = ""
        if (op == "update" and "fields" in design and expected["class"] == "CAniVMove"
                and expected["words_uint32"].get("40")):
            if index != len(rows):
                raise ValueError("Keep the original VMove animation slot when changing its expression")
            validate_observed_vmove_clone(expected, changes)
            row["restore_observed_vmove_clone"] = True
            expected["byte_arrays_hex"]["14"] = ""
        if (op == "update" and expected["class"] in PALETTE_CLASSES and expected.get("byte_arrays_hex", {}).get("14")
                and observed_palette_clone(expected, changes)):
            if index != len(rows):
                raise ValueError("Keep the original palette animation slot when changing its compiled palette")
            row["restore_observed_palette_clone"] = True
            expected["byte_arrays_hex"]["14"] = ""
        if op == "update" and expected["class"] == "CAniBlink" and observed_blink_clone(expected, changes):
            if index != len(rows):
                raise ValueError("Keep the original Blink animation slot when changing its properties")
            row["restore_observed_blink_clone"] = True
            expected["byte_arrays_hex"]["14"] = ""
        if changes:
            row["native_member_updates"] = deepcopy(changes)
            for field, value in changes.items():
                if field == "enabled_raw_byte":
                    if type(value) is not int or value not in (0, 1):
                        raise ValueError("enabled_raw_byte must be 0 or 1")
                    expected[field] = value
                else:
                    if not isinstance(value, dict) or value.keys() - expected[field].keys():
                        raise ValueError("Member offsets must exist in the captured record")
                    expected[field].update(deepcopy(value))
        if op in ("update", "clone"):
            factory = rebuild_visible_update(original[index], expected, changes, clone=op == "clone")
            if factory is not None:
                row = factory
        if "expected_record" in design and expected != design["expected_record"]:
            raise ValueError("Expected record differs from the declared changes")
        row["expected_record"] = expected
        rows.append(row)
    after = {"items": rows, "expected_existing_items": deepcopy(original),
             "allow_original_owned_list_rebuild": True,
             "defer_native_final_compile_and_reference_rebuild": True}
    history = page["attributes"][9] & 0xffffffff
    if history:
        after["history_property13_projection"] = {"before_raw_uint32": history, "after_raw_uint32": 0}
    return {"action_id": action_id, "kind": "control-animation-list", "target": target, "after": after}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True, help="Successful inspection receipt or its animation before object (JSON)")
    parser.add_argument("--capture-action-id", help="Select an animation action in a multi-action receipt")
    parser.add_argument("--items", type=Path, required=True, help="Ordered design array (JSON)")
    parser.add_argument("--output", type=Path, required=True, help="Session action output (JSON)")
    parser.add_argument("--action-id", default="edit-animations")
    args = parser.parse_args()
    document = json.loads(args.capture.read_text(encoding="utf-8-sig"))
    capture = select_capture(document, args.capture_action_id)
    items = json.loads(args.items.read_text(encoding="utf-8-sig"))
    catalog = (catalog_from_receipt(document)
               if isinstance(items, list) and any(isinstance(item, dict) and isinstance(item.get("fields"), dict)
                                                  and "binding" in item["fields"] for item in items)
               else None)
    action = prepare(capture, items, args.action_id, variable_catalog=catalog)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(action, output, ensure_ascii=False, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
