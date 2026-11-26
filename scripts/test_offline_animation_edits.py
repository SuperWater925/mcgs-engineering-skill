"""Offline CDraw list tests with a packaged native control template."""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / path) for path in ("scripts/native", "assets/pro-3.5-cli/scripts")]
import control_factory
from animation_edits import inspect_items
from control_patch import edit
from mcs_window_archive import write_count, write_cstring
from 原生界面样式 import CommonEnvelope


def changes(record, items):
    return edit(record, {"animations": items})


def sources(record):
    return [{k: row[k] for k in ("index", "sha256")} for row in inspect_items(CommonEnvelope.parse(record))]


class AnimationEdits(unittest.TestCase):
    def setUp(self):
        self.control = control_factory.primitive_record("rectangle")
        self.visible = changes(self.control, [{"new_visible": {"expression": "Flag", "mode": 1}}])

    def test_same_control_caption_and_visibility_in_one_operation(self):
        from mcs_input_text import LabelRecord
        label = control_factory.primitive_record("label")
        result = edit(label, {"text": "Run", "animations": [{"new_visible": {"expression": "Flag"}}]})
        common = CommonEnvelope.parse(result)
        self.assertEqual(common.animations[0]["expression"], "Flag")
        self.assertEqual(LabelRecord.parse(common.project_without_animations()).caption, "Run")

    def test_visible_edit_and_remove(self):
        src = sources(self.visible)
        before = CommonEnvelope.parse(self.visible)
        src[0]["set"] = {"expression": "Changed", "mode": 0}
        result = CommonEnvelope.parse(changes(self.visible, src))
        self.assertEqual((result.animations[0]["expression"], result.animations[0]["mode"]), ("Changed", 0))
        self.assertEqual(before.prefix[before.animation_end:], result.prefix[result.animation_end:])
        self.assertEqual(before.content, result.content)
        self.assertEqual(before.metadata.to_bytes(), result.metadata.to_bytes())
        self.assertFalse(CommonEnvelope.parse(changes(self.visible, [])).animations)

    def test_reorder_and_palette(self):
        cm = CommonEnvelope.parse(self.visible)
        body = struct.pack("<HHH", 65535, 0, 9) + b"CAniBrush" + bytes(4) + write_cstring("Temp")
        body += write_count(1) + struct.pack("<f", 2) + write_count(1) + struct.pack("<I", 0xAB000004)
        r = cm.to_record()
        r.payload = r.payload[:cm.animation_start] + write_count(2) + r.payload[cm.animation_start+2:cm.animation_end] + body + r.payload[cm.animation_end:]
        a, b = sources(r)
        b["set"] = {"colors": [17], "thresholds": [-2.5]}
        result = CommonEnvelope.parse(changes(r, [b, a]))
        self.assertEqual(result.animations[0]["colors"], [0xAB000011])
        self.assertEqual(inspect_items(result)[0]["colors"], [17])
        self.assertEqual(result.animations[0]["thresholds"], [-2.5])
        self.assertEqual(inspect_items(result)[1]["sha256"], a["sha256"])

    def test_mapped_class_body_edits_preserve_short_and_large_tags(self):
        cm = CommonEnvelope.parse(self.visible)
        body = struct.pack("<f", 1.0) + write_cstring("Previous") + struct.pack("<I", 0)
        for tag in (b"\x01\x80", struct.pack("<HI", 0x7fff, 0x80000001)):
            r = cm.to_record()
            r.payload = (r.payload[:cm.animation_start] + struct.pack("<HI", 0xffff, 2)
                         + r.payload[cm.animation_start+2:cm.animation_end] + tag + body + r.payload[cm.animation_end:])
            source = sources(r)
            result = changes(r, [source[0], {**source[1], "set": {"expression": "New flag"}}])
            after = CommonEnvelope.parse(result)
            self.assertEqual(after.animations[1]["expression"], "New flag")
            self.assertEqual(sources(result)[0], source[0])
            self.assertEqual(result.payload[:cm.animation_end+4+len(tag)], r.payload[:cm.animation_end+4+len(tag)])
            reordered = CommonEnvelope.parse(changes(r, source[::-1]))
            self.assertEqual([v["expression"] for v in reordered.animations], ["Previous", "Flag"])
            self.assertEqual([v["tag"] for v in inspect_items(reordered)], ["declaration", "class"])

    def test_reject_stale_unknown_and_mapped_mutations(self):
        source = sources(self.visible)[0]
        for target in ([{**source, "sha256": "stale"}], [source, source], [{**source, "set": {"mode": True}}],
                       [source, {"new_visible": {"expression": "Duplicate"}}]):
            with self.subTest(target=target), self.assertRaises(ValueError):
                changes(self.visible, target)
        cm = CommonEnvelope.parse(self.visible)
        mapped = cm.to_record()
        mapped.payload = (mapped.payload[:cm.animation_start] + write_count(2)
                          + mapped.payload[cm.animation_start+2:cm.animation_end] + b"\x02\x00"
                          + mapped.payload[cm.animation_end:])
        self.assertEqual(len(sources(mapped)), 2)
        owner, alias = sources(mapped)
        self.assertEqual(len(sources(changes(mapped, [owner]))), 1)
        with self.assertRaisesRegex(ValueError, "references"):
            changes(mapped, [alias])
        inserted = {"new_animation": {"class": "CAniBrush", "expression": "Value"}}
        both = CommonEnvelope.parse(changes(mapped, [inserted, owner, alias]))
        self.assertEqual(both.animations[1], both.animations[2])
        self.assertEqual(both.prefix[both.animation_end-2:both.animation_end], b"\x04\x00")

    def test_clone_and_factory_match_independent_native_output(self):
        label = control_factory.primitive_record("label")
        item = {"new_animation": {"class": "CAniOutput", "expression": "$RunTime"}}
        result = changes(label, [item])
        source = sources(result)[0]
        self.assertEqual(source["sha256"], "8efd596bdff40b834a1a1f72e409806442528a7f6f6e29af812f22343a7dee90")
        clone = {"clone_index": 0, "sha256": source["sha256"], "set": {"expression": "Other"}}
        after = CommonEnvelope.parse(changes(result, [clone, source]))
        self.assertEqual([v["expression"] for v in after.animations], ["Other", "$RunTime"])

    def test_existing_output_text_and_vertical_intervals(self):
        label = control_factory.primitive_record("label")
        specs = [{"class": "CAniOutput", "expression": "$RunTime"},
                 {"class": "CAniVMove", "expression": "Level", "offsets": [0, -65], "values": [-100, 7000]}]
        result = changes(label, [{"new_animation": spec} for spec in specs])
        output, movement = sources(result)
        after = changes(result, [{**output, "set": {"off_text": "Stopped", "on_text": "Running"}},
                                 {**movement, "set": {"offsets": [-7, 4]}}])
        inspected = inspect_items(CommonEnvelope.parse(after))
        self.assertEqual((inspected[0]["off_text"], inspected[0]["on_text"]), ("Stopped", "Running"))
        details = CommonEnvelope.parse(after).animations
        self.assertEqual(details[0]["fields"], [1, 0, 1, 1])
        self.assertEqual(details[1]["movement_words"], [2**32-7, 4])
        self.assertEqual(details[1]["movement_float_bits"], struct.pack("<2f", -100, 7000).hex())
        with self.assertRaises(ValueError):
            changes(result, [output, {**movement, "set": {"values": [1, float("nan")]}}])

    def test_size_factory_matches_two_vendor_projects(self):
        result = changes(self.control, [{"new_animation": {"class": "CAniSize", "expression": "depth1"}}])
        self.assertEqual(sources(result)[0]["sha256"], "7f47c6590b6c25071734bb689eb4e8c79aba1b40fd883f8072b840187c16c389")

    def test_blink_semantic_fields_preserve_packed_color_high_bytes(self):
        common = CommonEnvelope.parse(self.control)
        body = (struct.pack("<HHH", 0xffff, 0, 9) + b"CAniBlink"
                + struct.pack("<f", 1) + write_cstring("Flag")
                + struct.pack("<5I", 1, 0, 0x12000000, 0x34000001, 0x56ffffff))
        record = common.to_record()
        record.payload = (record.payload[:common.animation_start] + write_count(1) + body
                          + record.payload[common.animation_end:])
        original = inspect_items(CommonEnvelope.parse(record))[0]
        self.assertEqual([original[key] for key in ("speed", "mode", "text_color", "border_color", "fill_color")],
                         ["normal", "visibility", 0, 1, 0xffffff])
        source = sources(record)[0]
        updates = {"speed": "slow", "mode": "properties", "text_color": 0x123456,
                   "border_color": 0x654321, "fill_color": 0x123}
        result = CommonEnvelope.parse(changes(record, [{**source, "set": updates}]))
        inspected = inspect_items(result)[0]
        self.assertEqual({key: inspected[key] for key in updates}, updates)
        self.assertEqual(result.animations[0]["blink_words"], [2, 1, 0x12123456, 0x34654321, 0x56000123])
        self.assertEqual(result.animations[0]["expression"], "Flag")
        for invalid in ({"speed": "medium"}, {"mode": 1}, {"fill_color": True}, {"text_color": 0x1000000}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                changes(record, [{**source, "set": invalid}])

    def test_native_vertical_movement_body(self):
        spec = {"class": "CAniVMove", "expression": "Level", "offsets": [0, -65], "values": [-100, 7000]}
        label = control_factory.primitive_record("label")
        result = changes(label, [{"new_animation": spec}])
        animation = CommonEnvelope.parse(result).animations[0]
        self.assertEqual(animation["movement_words"], [0, 4294967231])
        # Exact eight-byte native float pair independently read from a vendor-authored control.
        self.assertEqual(animation["movement_float_bits"], "0000c8c200c0da45")

    def test_new_palette_alignment_and_float_rounding(self):
        for levels, colors in (([1, 1.00000001], [1, 2]), ([1], [1, 2]), ([], [])):
            with self.assertRaises(ValueError):
                changes(self.control, [{"new_animation": {"class": "CAniBrush", "expression": "A",
                        "thresholds": levels, "colors": colors}}])


if __name__ == "__main__":
    unittest.main()
