from copy import deepcopy
import unittest
from pro_animation_plan import catalog_from_receipt, prepare, select_capture, variable_catalog


INPUT_RECORD = {
    "class": "CAniInput", "enabled_raw_byte": 10,
    "words_uint32": {"8": 12294, "c": 1134726349, "30": 0, "4c": 1343554297, "50": 3491037945,
                     "54": 0, "88": 91, "8c": 0, "90": 0, "94": 0, "98": 0, "9c": 4294967295},
    "strings": {"2c": "数字输入_开关型", "38": "\u000710096", "40": "\u000710095", "48": "\u000710094",
                "58": "", "5c": ""},
    "arrays": {}, "byte_arrays_hex": {"14": "", "60": "", "74": ""},
}
INPUT_SOURCE = {"name": "数字输入_开关型", "native_id": 91, "native_type": 1}
INPUT_TARGET = {"name": "数字输入_二进制", "native_id": 94, "native_type": 1}
COMPILED_BLINK = {
    "class": "CAniBlink", "enabled_raw_byte": 10, "strings": {"2c": "1"}, "arrays": {},
    "words_uint32": {"8": 0x3001, "c": 0x3f800000, "30": 0, "34": 0xc6df60, "38": 0x7a7a7a,
                     "3c": 0, "40": 0, "44": 0, "48": 0, "4c": 0, "50": 0xffffff},
    "byte_arrays_hex": {"14": "03000000000000000100000003000000000000001101000000472c0000000001"},
}


class AnimationPlanTests(unittest.TestCase):
    def setUp(self):
        self.record = {"class": "CAniVisible", "enabled_raw_byte": 1, "strings": {"30": "tag"}}
        self.capture = {"page": {"page_id": 24, "page_name": "p", "attributes": [0]*9 + [-1]},
                        "target_control": {"path": [2], "name": "c", "class": "CDrawLabel", "native_id": 6, "complete": "0x1234"},
                        "items": [self.record]}

    def test_compiled_blink_preserves_owner_fields_and_defers_only_derived_cache(self):
        # Current record from the original CAniBlink factory after save, check and reopen.
        record = deepcopy(COMPILED_BLINK)
        self.capture["items"] = [record, self.record]
        fields = {"expression": "0", "speed": "slow", "mode": "properties",
                  "text_color": 0x123456, "border_color": 0x654321, "fill_color": 0x223344}
        updates = {"strings": {"2c": "0"},
                   "words_uint32": {"40": 2, "44": 1, "48": 0x123456, "4c": 0x654321, "50": 0x223344}}
        for notation in ({"fields": fields}, {"native_member_updates": updates}):
            design = [{"update": 0, **notation}, {"keep": 1}]
            after = prepare(self.capture, design)["after"]
            target, retained = after["items"]
            self.assertTrue(target["restore_observed_blink_clone"])
            self.assertEqual(target["native_member_updates"], updates)
            self.assertEqual(target["expected_record"],
                             {**record, "strings": {"2c": "0"},
                              "words_uint32": {**record["words_uint32"], **updates["words_uint32"]},
                              "byte_arrays_hex": {"14": ""}})
            self.assertEqual(after["expected_existing_items"], [COMPILED_BLINK, self.record])
            self.assertEqual(retained["expected_record"], self.record)
            with self.assertRaisesRegex(ValueError, "original Blink animation slot"):
                prepare(self.capture, design[::-1])

        record["words_uint32"]["50"] = 0x7fffffff
        row = prepare(self.capture, [{"update": 0, "fields": {"fill_color": 1}}, {"keep": 1}])["after"]["items"][0]
        self.assertEqual(row["native_member_updates"], {"words_uint32": {"50": 0x7f000001}})
        for invalid in ({"40": 3}, {"44": True}, {"50": 1}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                prepare(self.capture, [{"update": 0, "native_member_updates": {"words_uint32": invalid}}])

    def test_size_projection_keeps_current_dimensions_and_all_other_words(self):
        record = {"class": "CAniSize", "enabled_raw_byte": 10,
                  "words_uint32": {"8": 12297, "c": 121, "30": 3, "34": 0, "38": 0, "3c": 1120403456,
                                   "40": 100, "44": 0, "48": 8642, "4c": 9417},
                  "strings": {"2c": "depth1"}, "arrays": {}, "byte_arrays_hex": {"14": "abcd"}}
        self.capture["items"] = [record, self.record]
        design = [{"update": 0, "fields": {"expression": "45.000"}}, {"keep": 1}]
        after = prepare(self.capture, design)["after"]
        row = after["items"][0]
        expected = deepcopy(record)
        expected["strings"]["2c"] = "45.000"
        expected["byte_arrays_hex"]["14"] = ""
        self.assertTrue(row["restore_observed_size_clone"])
        self.assertEqual(row["expected_record"], expected)
        self.assertEqual(row["native_member_updates"], {
            "strings": {"2c": "45.000"}, "words_uint32": {"48": 8642, "4c": 9417}})
        self.assertEqual(after["expected_existing_items"][0]["byte_arrays_hex"], {"14": "abcd"})
        with self.assertRaisesRegex(ValueError, "original Size animation slot"):
            prepare(self.capture, list(reversed(design)))

    def test_vmove_named_expression_preserves_live_dimension_limits_and_sibling(self):
        item = {"class": "CAniVMove", "enabled_raw_byte": 10,
                "words_uint32": {"8":12293,"c":1,"30":15,"34":26,"38":1065353216,"3c":1120403456,"40":761},
                "strings": {"2c":""}, "arrays": {}, "byte_arrays_hex": {"14":""}}
        self.capture["items"] = [item, self.record]
        design = [{"update":0, "fields":{"expression":"循环加"}}, {"keep":1}]
        action = prepare(self.capture, design)
        row, sibling = action["after"]["items"]
        self.assertTrue(row["restore_observed_vmove_clone"])
        self.assertEqual(row["native_member_updates"], {"strings":{"2c":"循环加"}})
        self.assertEqual(row["expected_record"], {**item,"strings":{"2c":"循环加"}})
        self.assertEqual(action["after"]["expected_existing_items"], [item,self.record])
        self.assertEqual(sibling["expected_record"], self.record)
        self.assertNotIn("clone_source", sibling)
        with self.assertRaisesRegex(ValueError, "original VMove animation slot"):
            prepare(self.capture, list(reversed(design)))

        compiled = {**item, "strings": {"2c": "循环加"}, "byte_arrays_hex": {
            "14": "030000000000000001000000030000000000000026190000002c0000000001"}}
        self.capture["items"] = [compiled, self.record]
        after = prepare(self.capture, [{"update": 0, "fields": {"expression": "another_tag"}}, {"keep": 1}])["after"]
        self.assertTrue(after["items"][0]["restore_observed_vmove_clone"])
        self.assertEqual(after["items"][0]["expected_record"], {
            **item, "strings": {"2c": "another_tag"}, "byte_arrays_hex": {"14": ""}})
        self.assertEqual(after["expected_existing_items"], [compiled, self.record])
        self.assertEqual(after["items"][1]["expected_record"], self.record)

        unknown = {**item,"byte_arrays_hex":{"14":"01"}}
        self.capture["items"] = [unknown]
        with self.assertRaisesRegex(ValueError, "observed original serialization layout"):
            prepare(self.capture, design[:1])
        zero = {**item,"words_uint32":{**item["words_uint32"],"40":0}}
        self.capture["items"] = [zero]
        row = prepare(self.capture, design[:1])["after"]["items"][0]
        self.assertNotIn("restore_observed_vmove_clone", row)

    def test_compiled_palette_checks_all_fields_and_keeps_color_high_byte(self):
        for clazz in ("CAniBrush", "CAniTextColor"):
            with self.subTest(clazz=clazz):
                source = {"class": clazz, "enabled_raw_byte": 10,
                          "words_uint32": {"8": 12297, "c": 0}, "strings": {"2c": "显示标识1"},
                          "arrays": {"30": [0, 1065353216, 1086324736], "44": [0x12000000, 16757656, 16771809]},
                          "byte_arrays_hex": {"14": "abcd"}}
                self.capture["items"] = [source]
                action = prepare(self.capture, [{"update": 0, "fields": {
                    "thresholds": [0, 2, 6], "colors": [0x123456, 16757656, 16771809]}}])
                row = action["after"]["items"][0]
                self.assertTrue(row["restore_observed_palette_clone"])
                wanted = deepcopy(source)
                wanted["byte_arrays_hex"]["14"] = ""
                wanted["arrays"] = {"30": [0, 1073741824, 1086324736],
                                     "44": [0x12123456, 16757656, 16771809]}
                self.assertEqual(row["expected_record"], wanted)
                self.assertEqual(action["after"]["expected_existing_items"][0]["byte_arrays_hex"], {"14": "abcd"})
                with self.assertRaisesRegex(ValueError, "retain each native high byte"):
                    prepare(self.capture, [{"update": 0, "native_member_updates": {
                        "arrays": {"44": [0x99000000, 16757656, 16771809]}}}])

    def test_clone_then_keep_preserves_original_identity(self):
        action = prepare(self.capture, [{"clone": 0}, {"keep": 0}])
        after = action["after"]
        self.assertTrue(after["items"][0]["clone_source"])
        self.assertNotIn("clone_source", after["items"][1])
        self.assertEqual(action["target"], after["items"][1]["source"]["control"])
        self.assertEqual(after["history_property13_projection"]["before_raw_uint32"], 4294967295)

    def test_complete_receipt_selection(self):
        row = {"kind": "control-animation-list", "action_id": "A", "before": self.capture}
        receipt = {"ok": True, "action_preimages": [row, dict(row, action_id="B")]}
        with self.assertRaises(ValueError):
            select_capture(receipt)
        self.assertEqual(select_capture(receipt, "B"), self.capture)
        self.assertEqual(prepare(select_capture(receipt, "A"), [])["target"]["complete"], "0x1234")

    def test_remove_all_retains_expected_preimage(self):
        after = prepare(self.capture, [])["after"]
        self.assertEqual(after["items"], [])
        self.assertEqual(after["expected_existing_items"], [self.record])

    def test_update_and_add_use_exact_records(self):
        rows = prepare(self.capture, [{"update": 0, "native_member_updates": {"strings": {"30": "new"}}},
                                      {"add": "CAniVisible", "expected_record": self.record}])["after"]["items"]
        self.assertEqual(rows[0]["expected_record"]["strings"]["30"], "new")
        self.assertEqual(rows[1]["expected_record"]["strings"]["30"], "tag")
        self.assertEqual(self.record["strings"]["30"], "tag")

    def test_compiled_visible_update_uses_native_factory_with_only_derived_cache_reset(self):
        record = {"class": "CAniVisible", "words_uint32": {"8": 12299, "c": 1065353216, "30": 1},
                  "enabled_raw_byte": 10, "strings": {"2c": "Flag"}, "arrays": {},
                  "byte_arrays_hex": {"14": "12345678"}}
        capture = {**self.capture, "items": [record]}
        after = prepare(capture, [{"update": 0, "native_member_updates": {"strings": {"2c": "Ready"}}}])["after"]
        row = after["items"][0]
        self.assertEqual(row["new_class"], "CAniVisible")
        self.assertNotIn("source", row)
        self.assertEqual(row["expected_record"], {**record, "strings": {"2c": "Ready"}, "byte_arrays_hex": {"14": ""}})
        self.assertEqual(after["expected_existing_items"], [record])
        self.assertEqual(record["byte_arrays_hex"]["14"], "12345678")

    def test_business_add_clone_and_update(self):
        added = prepare(self.capture, [{"add": "CAniVisible", "visibility": {"expression": "Ready"}}])
        record = added["after"]["items"][0]["expected_record"]
        self.assertEqual(record["words_uint32"]["30"], 0)
        record["byte_arrays_hex"]["14"] = "01ab"
        capture = {**self.capture, "items": [record]}
        rows = prepare(capture, [{"clone": 0}, {"keep": 0}])["after"]["items"]
        self.assertEqual(rows[0]["new_class"], "CAniVisible")
        self.assertEqual(rows[0]["expected_record"]["strings"]["2c"], "Ready")
        self.assertEqual(rows[0]["expected_record"]["byte_arrays_hex"]["14"], "")
        self.assertEqual(rows[1]["expected_record"], record)
        row = prepare(capture, [{"update": 0, "visibility": {"mode": 1}}])["after"]["items"][0]
        self.assertEqual(row["expected_record"]["words_uint32"]["30"], 1)

    def test_unproven_cache_layout_stays_exact(self):
        record = dict(self.record, byte_arrays_hex={"14": "01", "20": "02"})
        row = prepare({**self.capture, "items": [record]}, [{"clone": 0}])["after"]["items"][0]
        self.assertTrue(row["clone_source"])
        self.assertEqual(row["expected_record"], record)

    def test_palette_preserves_high_byte_and_uses_binary32(self):
        for kind in ("CAniBrush", "CAniTextColor"):
            record = dict(self.record, **{"class":kind, "strings":{"2c":"tag"},
                        "arrays":{"30":[0,1065353216],"44":[0xff123456,0x7fabcdef]}})
            capture = {**self.capture, "items":[record]}
            fields = {"thresholds":[-1,0.5],"colors":[0,255]}
            row = prepare(capture,[{"update":0,"fields":fields}])["after"]["items"][0]
            self.assertEqual(row["expected_record"]["arrays"], {"30":[3212836864,1056964608],"44":[0xff000000,0x7f0000ff]})
            with self.assertRaises(ValueError):
                prepare(capture,[{"update":0,"fields":{"thresholds":[1,1.00000001]}}])

    def test_input_binding_projects_both_fields_from_inspected_catalog(self):
        capture = {**self.capture, "items": [INPUT_RECORD]}
        receipt = {"ok": True, "action_preimages": [
            {"kind": "control-animation-list", "action_id": "input", "before": capture},
            {"kind": "data-catalog", "action_id": "variables",
             "before": {"module_id": 2, "records": [INPUT_SOURCE, INPUT_TARGET]}},
        ]}
        expected = deepcopy(INPUT_RECORD)
        expected["strings"]["2c"] = INPUT_TARGET["name"]
        expected["words_uint32"]["88"] = INPUT_TARGET["native_id"]
        original = deepcopy(INPUT_RECORD)
        for operation in ("update", "clone"):
            with self.subTest(operation=operation):
                after = prepare(select_capture(receipt), [{operation: 0, "fields": {"binding": INPUT_TARGET["name"]}}],
                                variable_catalog=catalog_from_receipt(receipt))["after"]
                row = after["items"][0]
                self.assertEqual(row["native_member_updates"],
                                 {"strings": {"2c": INPUT_TARGET["name"]}, "words_uint32": {"88": 94}})
                self.assertEqual(row["input_binding_preimage"], {"source": INPUT_SOURCE, "target": INPUT_TARGET})
                self.assertEqual(row["expected_record"], expected)
                self.assertEqual(after["expected_existing_items"], [original])
                self.assertEqual("clone_source" in row, operation == "clone")
        self.assertEqual(INPUT_RECORD, original)

    def test_input_binding_rejects_unknown_identity_type_or_cache(self):
        records = [INPUT_SOURCE, INPUT_TARGET]
        design = [{"update": 0, "fields": {"binding": INPUT_TARGET["name"]}}]
        cached = {**INPUT_RECORD, "byte_arrays_hex": {"14": "", "60": "ab", "74": ""}}
        bad_id = {**INPUT_SOURCE, "native_id": 92}
        bad_type = {**INPUT_TARGET, "native_type": 2}
        for record, catalog_records, error in (
            (INPUT_RECORD, None, "current native data-catalog"),
            (INPUT_RECORD, [bad_id, INPUT_TARGET], "Original input binding ID"),
            (INPUT_RECORD, [INPUT_SOURCE, bad_type], "same scalar type"),
            (INPUT_RECORD, records + [INPUT_TARGET], "unique names"),
            (cached, records, "layout with empty caches"),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                catalog = None if catalog_records is None else variable_catalog(catalog_records)
                prepare({**self.capture, "items": [record]}, design, variable_catalog=catalog)
        row = prepare({**self.capture, "items": [cached]}, [{"keep": 0}])["after"]["items"][0]
        self.assertEqual(row["expected_record"], cached)
        self.assertNotIn("input_binding_preimage", row)

    def test_same_input_binding_clone_needs_no_new_identity(self):
        design = [{"clone": 0, "fields": {"binding": INPUT_SOURCE["name"]}}]
        row = prepare({**self.capture, "items": [INPUT_RECORD]}, design)["after"]["items"][0]
        self.assertTrue(row["clone_source"])
        self.assertNotIn("input_binding_preimage", row)
        self.assertNotIn("native_member_updates", row)

    def test_compiled_output_retained_and_cache_free_output_is_editable(self):
        words = {k:i for i,k in enumerate("8 c 40 44 48 4c 50 54 58 5c 60 68 6c 70".split())}
        record = {"class":"CAniOutput","words_uint32":words,"enabled_raw_byte":10,"arrays":{},
                  "strings":{"2c":"level","34":"off","3c":"on","64":"unit"},"byte_arrays_hex":{"14":"ab"}}
        capture = {**self.capture, "items":[record]}
        rows = prepare(capture,[{"keep":0}])["after"]["items"]
        self.assertEqual(rows[0]["expected_record"],record)
        with self.assertRaisesRegex(ValueError, "observed original serializer layout"):
            prepare(capture,[{"clone":0,"fields":{"expression":"next"}}])
        record["byte_arrays_hex"]["14"] = ""
        guarded = prepare(capture,[{"clone":0,"fields":{"expression":"next"}}])["after"]["items"][0]
        self.assertTrue(guarded["clone_source"])
        self.assertEqual(guarded["expected_record"]["byte_arrays_hex"], {"14":""})

    def test_compiled_output_restores_only_the_four_observed_clone_fields(self):
        words = dict.fromkeys("8 c 40 44 48 4c 50 54 58 5c 60 68 6c 70".split(), 0)
        words.update({"60":1,"68":1,"6c":1})
        record = {"class":"CAniOutput","words_uint32":words,"enabled_raw_byte":10,"arrays":{},
                  "strings":{"2c":"level","34":"off","3c":"on","64":"unit"},"byte_arrays_hex":{"14":"ab" * 32}}
        capture = {**self.capture, "items":[record]}
        rows = prepare(capture,[{"clone":0,"fields":{"expression":"next"}},{"keep":0}])["after"]["items"]
        self.assertTrue(rows[0]["restore_observed_output_clone"])
        self.assertEqual(rows[0]["native_member_updates"]["words_uint32"], {"5c":0,"60":1,"68":1,"6c":1})
        self.assertEqual(rows[0]["expected_record"]["words_uint32"],words)
        self.assertEqual(rows[0]["expected_record"]["byte_arrays_hex"],{"14":""})
        self.assertEqual(rows[1]["expected_record"],record)

    def test_invalid_or_ambiguous_indexes(self):
        for design in ([{"keep": 0}, {"keep": 0}], [{"clone": -1}], [{"clone": True}],
                       [{"update": 0, "native_member_updates": {"strings": {"31": "invalid"}}}]):
            with self.subTest(design=design), self.assertRaises(ValueError):
                prepare(self.capture, design)


if __name__ == "__main__":
    unittest.main()
