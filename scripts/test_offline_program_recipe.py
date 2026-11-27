import copy
import json
import struct
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "assets/pro-3.5-cli"
sys.path.insert(0, str(BASE / "scripts"))
from offline_program_recipe import apply_program_recipe, recipe_state, strategy_state


class OfflineProgramRecipeTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((BASE / "assets/blank-project.json").read_text(encoding="utf-8-sig"))

    def test_recipe_group_and_rows(self):
        before = copy.deepcopy(self.data)
        apply_program_recipe(self.data, {"recipe_edits": [
            {"op":"add_group","name":"batch","records":[["one"]]},
            {"op":"insert_record","name":"batch","index":1,"values":["two"]},
            {"op":"update_record","name":"batch","index":0,"values":["three"]},
            {"op":"delete_record","name":"batch","index":1}]})
        self.assertEqual(recipe_state(self.data)[3]["batch"][1].records, [["three"]])
        apply_program_recipe(self.data, {"recipe_edits":[{"op":"delete_group","name":"batch"}]})
        self.assertEqual(self.data, before)

    def test_column_edits_on_existing_variable(self):
        import native_format as f
        row = next(r for r in self.data["System"]["rows"] if r["strName"] == "ObjData")
        var = next(v for v in f.variables(f.archive(row["lbContext"])) if v["kind"] in (1,2,3))
        col = dict(binding=var["name"],type=var["kind"],title="v")
        apply_program_recipe(self.data, {"recipe_edits":[
            {"op":"add_group","name":"batch","records":[["one"]]},
            {"op":"insert_column","name":"batch","index":1,"column":col,"values":["1"]},
            {"op":"update_column","name":"batch","index":1,"column":dict(col,title="renamed"),"values":["0"]}]})
        group = recipe_state(self.data)[3]["batch"][1]
        self.assertEqual(group.records,[["one","0"]])
        self.assertEqual(group.fields[1].title, "renamed")
        apply_program_recipe(self.data,{"recipe_edits":[{"op":"delete_column","name":"batch","index":1}]})
        self.assertEqual(recipe_state(self.data)[3]["batch"][1].records,[["one"]])

    def test_recipe_column_title_requires_a_text_id_in_the_target_project(self):
        import native_format as native

        rows = {row['strName']: row for row in self.data['System']['rows']}
        variables = native.variables(native.archive(rows['ObjData']['lbContext']))
        variable = next(row for row in variables if row['kind'] in (1, 2, 3))
        definition = struct.pack('<I', 0) + native.text('简体中文')
        definition += (native.text('Arial') + struct.pack('<II', 100, 0xffffffff)) * 2
        dictionary = bytes(12) + struct.pack('<III', 1, 0, 1) + definition
        dictionary += struct.pack('<IIII', 1, 10420, 1, 0) + native.text('当前项目标题') + struct.pack('<I', 1)
        rows['MCGSLINGUIST']['lbContext'] = native.wrap(dictionary)

        field = {'binding': variable['name'], 'type': variable['kind'], 'title': '\x0710420'}
        add = {'op': 'add_group', 'name': 'batch', 'columns': [field]}
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'title text ID 10421 is missing'):
            apply_program_recipe(self.data, {'recipe_edits': [dict(add, columns=[dict(field, title='\x0710421')])]})
        self.assertEqual(self.data, before)
        apply_program_recipe(self.data, {'recipe_edits': [add]})
        self.assertEqual(recipe_state(self.data)[3]['batch'][1].fields[1].title, '\x0710420')

        saved = copy.deepcopy(self.data)
        insert = {'op': 'insert_column', 'name': 'batch', 'index': 1, 'column': dict(field, title='\x0710421')}
        update = dict(insert, op='update_column')
        for edit in (insert, update):
            with self.assertRaisesRegex(ValueError, 'title text ID 10421 is missing'):
                apply_program_recipe(self.data, {'recipe_edits': [edit]})
            self.assertEqual(self.data, saved)

    def test_recipe_reorder_checks_exact_whole_record_release_program(self):
        from control_factory import primitive_record
        from mcs_button_control import ButtonArchive
        from offline_recipe_references import require_recipe_reorder_safe_button

        source = '\n'.join(['!RecipeLoad("Batch")', '!RecipeLoadByDialog("Batch", "Choose")',
                          'Position=!RecipeGetCurrentPosition("Batch")',
                          'BatchName = !RecipeGetName("Batch")', '!RecipeGetCurrentValue("Batch")',
                          'Main.Form.Refresh( )'])
        cache = bytes.fromhex(
            '000000000000000000000000'
            '130500000042617463680701000000020000000100000000'
            '13050000004261746368130600000043686f6f73650702000000020000000200000000'
            '1305000000426174636807030000000200000001000000473eaa000000'
            '13050000004261746368070400000004000000010000003fab000000'
            '130500000042617463680705000000020000000100000000'
            '050500000003fefffffffeffffff00000000000000000000000001')
        variables = {'Position': {'kind': 2, 'id': 170}, 'BatchName': {'kind': 3, 'id': 171}}
        release = primitive_record('button')
        button = ButtonArchive.parse(release)
        button.release_script.value = source
        button.release_compiled.value = cache
        release.payload = button.to_bytes()
        before = release.payload
        require_recipe_reorder_safe_button(release, 'Batch', {'Main.Form.Refresh'}, variables)
        self.assertEqual(release.payload, before)
        for bad in (source.replace('"Batch")\nMain.Form.Refresh', '"Batch",1)\nMain.Form.Refresh'),
                    source.replace('Main.Form.Refresh', 'Other.Form.Refresh'),
                    source.replace('!RecipeLoad("Batch")', '!RecipeLoadByNum("Batch",1)')):
            button.release_script.value = bad
            release.payload = button.to_bytes()
            with self.assertRaisesRegex(ValueError, 'Unsupported recipe release call'):
                require_recipe_reorder_safe_button(release, 'Batch', {'Main.Form.Refresh'}, variables)
        button.release_script.value = source
        button.release_compiled.value = cache.replace(b'\xaa\0\0\0', b'\xa9\0\0\0')
        release.payload = button.to_bytes()
        with self.assertRaisesRegex(ValueError, 'compilation does not match'):
            require_recipe_reorder_safe_button(release, 'Batch', {'Main.Form.Refresh'}, variables)
        button.release_compiled.value = cache
        button.metadata.properties.press_script.value = '!RecipeGetCurrentValue("Batch")'
        release.payload = button.to_bytes()
        with self.assertRaisesRegex(ValueError, 'Another field'):
            require_recipe_reorder_safe_button(release, 'Batch', {'Main.Form.Refresh'}, variables)

    def test_bound_column_transaction_and_undo(self):
        import struct
        import native_format as fmt
        from control_factory import primitive_record
        from mcs_plugin_controls import RecipeCore, RecipeColumn, buffer_write
        from mcs_window_archive import WindowArchive, write_cstring
        from 原生界面样式 import CommonEnvelope
        from offline_program_recipe import recipe_consumers

        variables = next(r for r in self.data["System"]["rows"] if r["strName"] == "ObjData")
        var = next(v for v in fmt.variables(fmt.archive(variables["lbContext"])) if v["kind"] in (1, 2, 3))
        col = dict(binding=var["name"], type=var["kind"], title="Old title")
        name = "BoundGroupAlpha"
        apply_program_recipe(self.data, {"recipe_edits": [
            {"op": "add_group", "name": name, "columns": [col], "records": [["item", "1"]]}]})
        group = recipe_state(self.data)[3][name][1]
        fields = {key: (b"font" if kind == "bytes" else "" if kind == "str" else 0)
                  for key, kind in RecipeCore.SPEC}
        columns = [RecipeColumn("", "序号", [3, 1, 2, 0, 4, 5, 6, 7])]
        for field in group.fields:
            columns.append(RecipeColumn(field.binding, field.title, [field.data_type] + list(range(7))))
        core = RecipeCore(bytes(16) + struct.pack("<I", 22), name, columns, fields)
        common = CommonEnvelope.parse(primitive_record("rectangle"))
        common.content = write_cstring("DrawRecipe.ui#配方") + buffer_write(core.to_bytes())
        control = common.to_record()
        control.type_id = 0x503d
        row = self.data["WndUser"]["rows"][0]
        window = WindowArchive.parse(fmt.archive(row["lbObjects"]))
        window.controls[:] = [control, copy.deepcopy(control)]
        row["lbObjects"] = fmt.wrap_like(row["lbObjects"], window.to_bytes())
        original = copy.deepcopy(self.data)
        update = dict(op="update_column", name=name, index=1, column=dict(col, title="Long new title"))
        with self.assertRaisesRegex(ValueError, "used on page"):
            apply_program_recipe(self.data, {"recipe_edits": [update]})
        update["sync_controls"] = True
        apply_program_recipe(self.data, {"recipe_edits": [update]})
        self.assertEqual([q.columns[2].title for _, q in recipe_consumers(self.data, name)],
                         ["Long new title"] * 2)
        apply_program_recipe(self.data, {"recipe_edits": [dict(update, column=col)]})
        self.assertEqual(self.data, original)
        insert = dict(op="insert_column", name=name, index=1, column=dict(col, title="Inserted"),
                      values=["2"], sync_controls=True, display_template_index=1)
        apply_program_recipe(self.data, {"recipe_edits": [insert]})
        for _, control_core in recipe_consumers(self.data, name):
            self.assertEqual(control_core.columns[2].values, columns[2].values)
            self.assertEqual(control_core.columns[3], columns[2])
        delete = dict(op="delete_column", name=name, index=1, sync_controls=True)
        apply_program_recipe(self.data, {"recipe_edits": [delete]})
        self.assertEqual(self.data, original)
        apply_program_recipe(self.data, {"recipe_edits": [delete]})
        self.assertEqual([q.columns for _, q in recipe_consumers(self.data, name)], [columns[:2]] * 2)
        self.assertEqual(recipe_state(self.data)[3][name][1].records, [["item"]])

    def test_bound_recipe_reorder_and_type_change_with_display_template(self):
        import mcgs_file as project
        import native_format as fmt
        from control_factory import primitive_record
        from mcs_plugin_controls import RecipeCore, RecipeColumn, buffer_write
        from mcs_window_archive import WindowArchive, write_cstring
        from offline_program_recipe import recipe_consumers
        from 原生界面样式 import CommonEnvelope

        for family in ("Stu", "Pro"):
            with self.subTest(family=family):
                name = "RecordColumnPlan"
                data = project.create_data({"pages": [{"name": "Main"}], "variables": [
                    {"name": "RecipeTemperature", "type": "number"},
                    {"name": "RecipeLabel", "type": "string"},
                ]}, family)
                number = {"binding": "RecipeTemperature", "title": "Numeric", "type": 2}
                text = {"binding": "RecipeLabel", "title": "Character", "type": 3}
                apply_program_recipe(data, {"recipe_edits": [{"op": "add_group", "name": name,
                    "columns": [number, text], "records": [["Item A", "12.5", "Alpha"], ["Item B", "23.25", "Beta"]]}]})
                group = recipe_state(data)[3][name][1]
                fields = {key: (b"font" if kind == "bytes" else "" if kind == "str" else 0)
                          for key, kind in RecipeCore.SPEC}
                columns = [RecipeColumn("", "序号", [3, 1, 2, 0, 4, 5, 6, 7])]
                columns.extend(RecipeColumn(entry.binding, entry.title, [entry.data_type, i + 90, 0, 1, 2, 3, 4, 5])
                               for i, entry in enumerate(group.fields))
                core = RecipeCore(bytes(16) + struct.pack("<I", 22), name, columns, fields)
                common = CommonEnvelope.parse(primitive_record("rectangle"))
                common.content = write_cstring("DrawRecipe.ui#配方") + buffer_write(core.to_bytes())
                control = common.to_record()
                control.type_id = 0x503d
                page = data["WndUser"]["rows"][0]
                window = WindowArchive.parse(fmt.archive(page["lbObjects"]))
                window.controls[:] = [control]
                page["lbObjects"] = fmt.wrap_like(page["lbObjects"], window.to_bytes())

                first = copy.deepcopy(data)
                move = {"op": "reorder_columns", "name": name, "order": [2, 1], "sync_controls": True}
                with self.assertRaisesRegex(ValueError, "permutation"):
                    apply_program_recipe(data, {"recipe_edits": [dict(move, order=[0, 2])]})
                with self.assertRaisesRegex(ValueError, "used on page"):
                    apply_program_recipe(data, {"recipe_edits": [dict(move, sync_controls=False)]})
                apply_program_recipe(data, {"recipe_edits": [move]})
                group = recipe_state(data)[3][name][1]
                self.assertEqual(group.records, [["Item A", "Alpha", "12.5"], ["Item B", "Beta", "23.25"]])
                current, = (core for _, core in recipe_consumers(data, name))
                self.assertEqual(current.columns, [*columns[:2], columns[3], columns[2]])
                self.assertEqual(current.fields, fields)
                apply_program_recipe(data, {"recipe_edits": [move]})
                self.assertEqual(data, first)

                convert = {"op": "update_column", "name": name, "index": 1, "sync_controls": True,
                           "column": dict(text, title="Converted"), "values": ["New A", "New B"]}
                with self.assertRaisesRegex(ValueError, "native display settings"):
                    apply_program_recipe(data, {"recipe_edits": [convert]})
                with self.assertRaisesRegex(ValueError, "type differs"):
                    apply_program_recipe(data, {"recipe_edits": [dict(convert, display_template_index=1)]})
                self.assertEqual(data, first)
                apply_program_recipe(data, {"recipe_edits": [dict(convert, display_template_index=2)]})
                current, = (core for _, core in recipe_consumers(data, name))
                self.assertEqual(current.columns[0:2], columns[0:2])
                self.assertEqual(current.columns[2], RecipeColumn(text["binding"], "Converted", columns[3].values))
                self.assertEqual(current.columns[3], columns[3])
                self.assertEqual(recipe_state(data)[3][name][1].records, [["Item A", "New A", "Alpha"], ["Item B", "New B", "Beta"]])

    def test_loop_and_event_metadata_preserve_both_trigger_archives(self):
        import mcgs_file as project

        for family in ("Stu", "Pro"):
            with self.subTest(family=family):
                data = project.create_data({"pages": [{"name": "Main"}], "variables": [
                    {"name": "LocalTrigger", "type": "boolean"}]}, family)
                ident = project.VariableCatalog(data)["LocalTrigger"]["id"]
                apply_program_recipe(data, {"strategy_edits": [
                    {"op": "add_loop_strategy", "name": "IntervalTrial", "interval_ms": 251},
                    {"op": "add_event_strategy", "name": "EventTrial", "variable": {"id": ident, "name": "LocalTrigger"}},
                ]})
                before = copy.deepcopy(data)
                before_rows = strategy_state(data)[2].triggers
                apply_program_recipe(data, {"strategy_edits": [
                    {"op": "rename_loop_strategy", "name": "IntervalTrial", "new_name": "IntervalFinal"},
                    {"op": "rename_event_strategy", "name": "EventTrial", "new_name": "EventFinal"},
                    {"op": "set_strategy_comment", "name": "IntervalFinal", "comment": "每251毫秒"},
                    {"op": "set_strategy_comment", "name": "EventFinal", "comment": "只保留原事件开关"},
                ]})
                registry = strategy_state(data)[2]
                self.assertEqual(data["Trigger"], before["Trigger"])
                self.assertEqual(registry.triggers, before_rows)
                self.assertEqual({b.fields["name"]: b.fields["comment"] for b in registry.strategies}["EventFinal"],
                                 "只保留原事件开关")
                with self.assertRaisesRegex(ValueError, "different native trigger"):
                    apply_program_recipe(data, {"strategy_edits": [
                        {"op": "rename_loop_strategy", "name": "EventFinal", "new_name": "WrongTrigger"}]})
                apply_program_recipe(data, {"strategy_edits": [
                    {"op": "set_strategy_comment", "name": "IntervalFinal", "comment": ""},
                    {"op": "set_strategy_comment", "name": "EventFinal", "comment": ""},
                    {"op": "rename_loop_strategy", "name": "IntervalFinal", "new_name": "IntervalTrial"},
                    {"op": "rename_event_strategy", "name": "EventFinal", "new_name": "EventTrial"},
                ]})
                self.assertEqual(data, before)

    def test_synchronized_recipe_rename_retargets_only_verified_consumer_group(self):
        import native_format as fmt
        from control_factory import primitive_record
        from mcs_plugin_controls import RecipeCore, RecipeColumn, buffer_write
        from mcs_window_archive import WindowArchive, write_cstring
        from 原生界面样式 import CommonEnvelope, GroupArchive
        from offline_program_recipe import recipe_consumers

        name, renamed = "ExactRecipeRename", "ExactRecipeRenamed"
        apply_program_recipe(self.data, {"recipe_edits":[
            {"op":"add_group","name":name,"records":[[name],[renamed],[f"Food {name}"]]}]})
        group = recipe_state(self.data)[3][name][1]
        settings = {key: (b"font" if kind == "bytes" else "" if kind == "str" else 0)
                    for key, kind in RecipeCore.SPEC}
        columns = [RecipeColumn("", "序号", [3,1,2,0,4,5,6,7]),
                   RecipeColumn("",group.fields[0].title,[3,1,2,3,4,5,6,7])]
        core = RecipeCore(bytes(16)+struct.pack("<I",22), name, columns, settings)
        common = CommonEnvelope.parse(primitive_record("rectangle"))
        page = self.data["WndUser"]["rows"][0]
        original_page = fmt.archive(page["lbObjects"])
        def configure(page_row, core):
            common.content = write_cstring("DrawRecipe.ui#配方") + buffer_write(core.to_bytes())
            control = common.to_record()
            control.type_id = 0x503d
            parent = primitive_record("rectangle")
            parent.type_id = 0x503a
            grouped = GroupArchive(CommonEnvelope.parse(parent),
                                   [copy.deepcopy(control), primitive_record("rectangle")], b"").to_record()
            window = WindowArchive.parse(original_page)
            window.controls[:] = [control, grouped]
            page_row["lbObjects"] = fmt.wrap_like(page_row["lbObjects"],window.to_bytes())
        configure(page,core)
        original = copy.deepcopy(self.data)
        rename = {"op":"rename_group","name":name,"new_name":renamed}
        with self.assertRaisesRegex(ValueError,"Possible name reference"):
            apply_program_recipe(self.data,{"recipe_edits":[rename]})
        self.assertEqual(self.data,original)

        sync = dict(rename,sync_controls=True)
        unrelated_text = copy.deepcopy(self.data)
        visible = copy.deepcopy(core)
        visible.fields["visible_expression"] = f'"{name}"'
        configure(unrelated_text["WndUser"]["rows"][0],visible)
        before = copy.deepcopy(unrelated_text)
        with self.assertRaisesRegex(ValueError,"Possible name reference"):
            apply_program_recipe(unrelated_text,{"recipe_edits":[sync]})
        self.assertEqual(unrelated_text,before)
        old_parent = GroupArchive.parse(WindowArchive.parse(fmt.archive(page["lbObjects"])).controls[1])
        row_id = recipe_state(self.data)[3][name][0]["iID"]
        apply_program_recipe(self.data,{"recipe_edits":[sync]})
        new_id, new_group = recipe_state(self.data)[3][renamed]
        self.assertEqual(new_id["iID"],row_id)
        self.assertEqual(new_group.records,group.records)
        expected = copy.deepcopy(core)
        expected.group = renamed
        self.assertEqual([observed for _, observed in recipe_consumers(self.data,renamed)], [expected,expected])
        new_page = self.data["WndUser"]["rows"][0]
        new_parent = GroupArchive.parse(WindowArchive.parse(fmt.archive(new_page["lbObjects"])).controls[1])
        self.assertEqual(new_parent.common.prefix, old_parent.common.prefix)
        self.assertEqual(new_parent.children[1].to_bytes(), old_parent.children[1].to_bytes())
        apply_program_recipe(self.data,{"recipe_edits":[dict(sync,name=renamed,new_name=name)]})
        self.assertEqual(self.data,original)

    def test_recipe_rename_ignores_only_proven_distinct_variable_declarations(self):
        import native_format as fmt
        from mcs_window_archive import write_cstring
        from offline_picture_library import mentions
        from offline_recipe_references import variable_name_projections

        term, symbol = "面包", "面包组"
        source = next(r for r in self.data["System"]["rows"] if r["strName"] == "ObjData")
        records = fmt.variables(fmt.archive(source["lbContext"]))
        var = dict(next(r for r in records if r["kind"] in (1, 2, 3)), name=symbol, note="", unit="")
        objdata = fmt.pack_variables(fmt.VariableRecords([var], records.document_header))
        wire = write_cstring(symbol)
        def u32s(*values):
            return struct.pack(f"<{len(values)}I", *values)
        empty = write_cstring("")
        typeinfo = (write_cstring("数据对象") + write_cstring("数据对象集合") + u32s(0x196f,19,19,1)
                    + wire + write_cstring(term) + u32s(0,21+var["kind"],var["id"]) + bytes(8))
        browse = (u32s(0x8000000a,0,0,1,1,1) + wire + u32s(0) + empty + empty + u32s(0,0))
        blobs = {"ObjData":objdata, "TYPEINFO":typeinfo, "BROWSEOBJECT":browse}
        rows = [{"strName":name,"lbContext":fmt.wrap(raw)} for name,raw in blobs.items()]
        projected = variable_name_projections(rows, (term, "配方新名"))
        for row in rows:
            label = row["strName"]
            raw = blobs[label]
            offset = raw.index(wire)
            self.assertEqual(projected[id(row), "lbContext"], raw[:offset] + bytes(len(wire)) + raw[offset+len(wire):])
            self.assertEqual(fmt.archive(row["lbContext"]), raw)
        self.assertTrue(mentions(projected[id(rows[1]), "lbContext"], term))
        self.assertFalse(mentions(projected[id(rows[2]), "lbContext"], term))
        self.assertFalse(variable_name_projections(rows, (symbol, "配方新名")))
        rows[2]["lbContext"] = fmt.wrap(browse + u32s(1))
        self.assertNotIn((id(rows[2]), "lbContext"), variable_name_projections(rows, (term, "配方新名")))

    def test_user_strategy_and_node_mutations(self):
        apply_program_recipe(self.data, {"strategy_edits":[
            {"op":"add_user_strategy","name":"test","source":"first"},
            {"op":"set_script","name":"test","row":0,"cell":0,"index":0,"value":"second"},
            {"op":"insert_script_row","name":"test","row":1,"source":"third"},
            {"op":"delete_script_row","name":"test","row":1},
            {"op":"set_condition","name":"test","row":0,"cell":0,"index":0,"value":"1"}]})
        registry = strategy_state(self.data)[2]
        cell = registry.strategies[-1].fields["rows"][0].fields["cells"][0]
        self.assertEqual(cell.fields["actions"][0].fields["source"], "second")
        self.assertEqual(cell.fields["conditions"][0].fields["expression"], "1")
        self.assertEqual(registry.triggers[-1].class_name, "CTriggerUser")

    def test_user_strategy_rename_preserves_ids_and_checks_script_references(self):
        old, new = "UnusedStrategyAlpha", "UnusedStrategyBeta"
        apply_program_recipe(self.data, {"strategy_edits": [
            {"op": "add_user_strategy", "name": old, "source": "1"}]})
        registry = strategy_state(self.data)[2]
        identity = registry.strategies[-1].fields["tail_words"]
        triggers = copy.deepcopy(self.data["Trigger"])
        rename = {"op": "rename_user_strategy", "name": old, "new_name": new}
        apply_program_recipe(self.data, {"strategy_edits": [rename]})
        block = strategy_state(self.data)[2].strategies[-1]
        self.assertEqual((block.fields["name"], block.fields["tail_words"]), (new, identity))
        self.assertEqual(self.data["Trigger"], triggers)
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, "name reference"):
            apply_program_recipe(self.data, {"strategy_edits": [
                {"op": "set_script", "name": new, "row": 0, "cell": 0, "index": 0, "value": new},
                {"op": "rename_user_strategy", "name": new, "new_name": old}]})
        self.assertEqual(self.data, before)

    def test_user_strategy_comment_keeps_trigger_notes_and_is_reversible(self):
        name = "ExistingStrategy"
        apply_program_recipe(self.data, {"strategy_edits": [
            {"op": "add_user_strategy", "name": name, "source": "1", "comment": "Original note"},
        ]})
        original = copy.deepcopy(self.data)
        before = strategy_state(original)[2].strategies[-1]
        update = {"op": "set_strategy_comment", "name": name, "comment": "只改策略内容注释"}
        for comment in (update["comment"], "", "Original note"):
            apply_program_recipe(self.data, {"strategy_edits": [{**update, "comment": comment}]})
            _, _, registry = strategy_state(self.data)
            actual = registry.strategies[-1]
            self.assertEqual(actual.fields["comment"], comment)
            self.assertEqual(registry.triggers[-1].fields["note"], "Original note")
            self.assertEqual(self.data["Trigger"], original["Trigger"])
            for key in ("name", "tail_words", "rows"):
                self.assertEqual(actual.fields[key], before.fields[key])
        self.assertEqual(self.data, original)
        default_cycle = next(t for t in registry.triggers if t.class_name == "CTriggerLoop").fields["strategy_id"]
        cycle = next(s for s in registry.strategies if s.fields["tail_words"][2] == default_cycle)
        with self.assertRaisesRegex(ValueError, "native user trigger"):
            apply_program_recipe(self.data, {"strategy_edits": [{**update, "name": cycle.fields["name"]}]})
        self.assertEqual(self.data, original)

    def test_event_variable_edit_keeps_independent_native_caches_until_source_changes(self):
        import mcgs_file as m
        import mcgs_recipe_strategy as archive
        from offline_program_recipe import read_trigger_row

        prefix = bytes.fromhex("030000000000000001000000030000000000000025")
        suffix = bytes.fromhex("472c0000000001")
        for family in ("Stu", "Pro"):
            with self.subTest(family=family):
                name = "ExampleEvent"
                data = m.create_data({"variables": [
                    {"name":"OldSwitch", "type":"boolean"},
                    {"name":"NewThreshold", "type":"number"},
                    {"name":"StringValue", "type":"string", "initial":""},
                ], "pages":[{"name":"Main"}]}, family)
                apply_program_recipe(data, {"strategy_edits":[
                    {"op":"add_user_strategy", "name":name, "source":"1"},
                ]})
                _, container, registry = strategy_state(data)
                identities = {var["name"]:{key:var[key] for key in ("id", "name")}
                              for var in m.f.variables(m.f.archive(m.system(data,"ObjData")["lbContext"]))}
                old, new, invalid = (identities[key] for key in ("OldSwitch", "NewThreshold", "StringValue"))
                event = registry.triggers[-1]
                event.class_name = "CTriggerEvent"
                event.fields.update(trigger_type=4, event_expression=old["name"], event_words=[0, 0],
                                    event_cache=prefix + struct.pack("<I", old["id"]) + suffix)
                container["lbContext"] = m.f.wrap_like(container["lbContext"], registry.serialize())
                row = data["Trigger"]["rows"][-1]
                row["lType"] = 4
                older = copy.deepcopy(event)
                older.fields["event_cache"] = prefix + struct.pack("<I", old["id"]+97) + suffix
                row["lbContext"] = m.f.wrap_like(row["lbContext"], archive.serialize_trigger_payload(older))
                baseline = copy.deepcopy(data)

                def edit(target):
                    return {"strategy_edits":[{"op":"set_event_trigger_variable","name":name,"variable":target}]}

                m.edit_data(data, edit(old))
                self.assertEqual(data, baseline)

                edge_edit = {"op":"set_event_trigger_edge", "name":name, "edge":"falling"}
                event_wire = archive.serialize_trigger_payload(event)
                registry_wire = m.f.archive(m.system(baseline,"StgyAndTrigger")["lbContext"])
                mirror_wire = m.f.archive(baseline["Trigger"]["rows"][-1]["lbContext"])
                self.assertEqual(registry_wire.count(event_wire), 1)
                edge_data = m.edit_data(copy.deepcopy(baseline), {"strategy_edits":[edge_edit]})
                self.assertEqual(m.f.archive(m.system(edge_data,"StgyAndTrigger")["lbContext"]),
                                 registry_wire.replace(event_wire, event_wire[:-4]+struct.pack("<I",1), 1))
                self.assertEqual(m.f.archive(edge_data["Trigger"]["rows"][-1]["lbContext"]),
                                 mirror_wire[:-4]+struct.pack("<I",1))
                self.assertEqual(edge_data["Stgy"], baseline["Stgy"])
                m.edit_data(edge_data, {"strategy_edits":[dict(edge_edit, edge="rising")]})
                self.assertEqual(edge_data, baseline)
                condition = m.edit_data(copy.deepcopy(baseline), {"strategy_edits":[dict(edge_edit, edge="change")]})
                wanted_word = struct.pack("<I", 4)
                self.assertEqual(m.f.archive(m.system(condition,"StgyAndTrigger")["lbContext"]),
                                 registry_wire.replace(event_wire, event_wire[:-4]+wanted_word, 1))
                self.assertEqual(m.f.archive(condition["Trigger"]["rows"][-1]["lbContext"]),
                                 mirror_wire[:-4]+wanted_word)
                m.edit_data(condition, {"strategy_edits":[dict(edge_edit, edge="rising")]})
                self.assertEqual(condition, baseline)
                for choice in ("rising_then_falling", "falling_then_rising"):
                    with self.assertRaisesRegex(ValueError, "reject both compound transitions"):
                        m.edit_data(edge_data, {"strategy_edits":[dict(edge_edit, edge=choice)]})
                with self.assertRaisesRegex(ValueError, "requires one of"):
                    m.edit_data(edge_data, {"strategy_edits":[dict(edge_edit, edge="alternate")]})
                self.assertEqual(edge_data, baseline)

                empty_mirror = copy.deepcopy(baseline)
                empty_row = empty_mirror["Trigger"]["rows"][-1]
                empty_copy = copy.deepcopy(event)
                empty_copy.fields["event_cache"] = b""
                empty_wire = archive.serialize_trigger_payload(empty_copy)
                empty_row["lbContext"] = m.f.wrap_like(empty_row["lbContext"], empty_wire)
                edited_empty = m.edit_data(empty_mirror, {"strategy_edits":[edge_edit]})
                saved_row = edited_empty["Trigger"]["rows"][-1]
                self.assertEqual(m.f.archive(saved_row["lbContext"]), empty_wire[:-4] + struct.pack("<I", 1))
                _, _, saved = strategy_state(edited_empty)
                self.assertEqual(saved.triggers[-1].fields["event_cache"], event.fields["event_cache"])

                # Real Stu stores a different database key for this Event.
                aliased = copy.deepcopy(baseline)
                alias_registry = copy.deepcopy(registry)
                alias_event = alias_registry.triggers[-1]
                row_key = aliased["Trigger"]["rows"][-1]["iID"]
                native_id = row_key+2
                alias_event.fields["trigger_id"] = native_id
                header = m.system(aliased,"StgyAndTrigger")
                header["lbContext"] = m.f.wrap_like(header["lbContext"], alias_registry.serialize())
                alias_row = aliased["Trigger"]["rows"][-1]
                alias_row["lbContext"] = m.f.wrap_like(alias_row["lbContext"], archive.serialize_trigger_payload(alias_event))
                bad_alias = copy.deepcopy(aliased)
                bad_alias["Trigger"]["rows"][-1]["strNote"] = "Wrong role"
                with self.assertRaisesRegex(ValueError, "Independently keyed Event"):
                    m.edit_data(bad_alias, {"strategy_edits":[edge_edit]})
                m.edit_data(aliased, {"strategy_edits":[edge_edit,
                    {"op":"add_loop_strategy", "name":"AfterAliasedEvent"},
                ]})
                modeled_event = strategy_state(aliased)[2].triggers[-2]
                retained_row, = [r for r in aliased["Trigger"]["rows"] if r["iID"] == row_key]
                self.assertEqual(modeled_event.fields["trigger_id"], native_id)
                self.assertEqual(modeled_event.fields["event_words"], [0,1])
                self.assertEqual(modeled_event.fields, read_trigger_row(retained_row,modeled_event).fields)
                self.assertEqual(aliased["Trigger"]["rows"][-1]["iID"], native_id+1)

                unrelated = copy.deepcopy(data)
                loop = next(node for node in registry.triggers if node.class_name == "CTriggerLoop")
                loop_name = next(block.fields["name"] for block in registry.strategies
                                 if block.fields["tail_words"][2] == loop.fields["strategy_id"])
                m.edit_data(unrelated, {"strategy_edits":[
                    {"op":"set_loop_interval", "name":loop_name, "interval_ms":731},
                ]})
                self.assertEqual(strategy_state(unrelated)[2].triggers[-1], event)
                self.assertEqual(unrelated["Trigger"]["rows"][-1], baseline["Trigger"]["rows"][-1])
                for wrong in (dict(new, id=old["id"]), invalid, dict(new, name="NewThreshold + 1")):
                    with self.assertRaisesRegex(ValueError, "Event trigger variable"):
                        m.edit_data(data, edit(wrong))
                    self.assertEqual(data, baseline)
                for field, value in (("event_words", [0, 1]), ("event_cache", b"unverified cache")):
                    mismatched = copy.deepcopy(baseline)
                    row = mismatched["Trigger"]["rows"][-1]
                    mirror = copy.deepcopy(older)
                    mirror.fields[field] = value
                    row["lbContext"] = m.f.wrap_like(row["lbContext"], archive.serialize_trigger_payload(mirror))
                    with self.assertRaisesRegex(ValueError, "Trigger duplicate payload differs"):
                        m.edit_data(mismatched, edit(new))

                m.edit_data(data, edit(new))
                _, _, after_registry = strategy_state(data)
                updated = after_registry.triggers[-1]
                row = data["Trigger"]["rows"][-1]
                self.assertEqual(updated.fields, dict(event.fields, event_expression=new["name"], event_cache=b""))
                self.assertEqual(read_trigger_row(row,updated).fields, updated.fields)
                self.assertEqual(after_registry.triggers[:-1], registry.triggers[:-1])
                self.assertEqual(after_registry.strategies, registry.strategies)
                self.assertEqual(data["Trigger"]["rows"][:-1], baseline["Trigger"]["rows"][:-1])
                self.assertEqual({key for key in data if data[key]!=baseline[key]}, {"System","Trigger"})

    def test_fixed_loop_interval_updates_both_archives_without_changing_packed_words(self):
        import mcgs_recipe_strategy as archive
        import native_format as fmt

        for filename in ("blank-project.json", "blank-project-stu.json"):
            with self.subTest(filename=filename):
                data = json.loads((BASE / "assets" / filename).read_text(encoding="utf-8-sig"))
                _, system, registry = strategy_state(data)
                loop, = [trigger for trigger in registry.triggers if trigger.class_name == "CTriggerLoop"]
                strategy_id = loop.fields["strategy_id"]
                block, = [node for node in registry.strategies if node.fields["tail_words"][2] == strategy_id]
                row, = [row for row in data["Trigger"]["rows"] if row["lStgyID"] == strategy_id]

                # Known original editor store difference: the registry can
                # have a different high WORD without an interval change.
                loop.fields["loop_tail"][0] += 0x10000
                raw = registry.serialize()
                system["lbContext"] = fmt.wrap_like(system["lbContext"], raw)
                loop_record = archive.serialize_trigger_payload(loop)
                mirror_record = fmt.archive(row["lbContext"])
                self.assertEqual(raw.count(loop_record), 1)
                interval = 725
                word = struct.pack("<I", interval)
                expected_registry = raw.replace(loop_record, loop_record[:-28] + word + loop_record[-24:])
                expected_mirror = mirror_record[:-28] + word + mirror_record[-24:]
                plan = {"strategy_edits": [{"op": "set_loop_interval", "name": block.fields["name"],
                                            "interval_ms": interval}]}
                before = copy.deepcopy(data)

                apply_program_recipe(data, plan)
                registry_row = next(row for row in data["System"]["rows"] if row["strName"] == "StgyAndTrigger")
                mirror_row = next(row for row in data["Trigger"]["rows"] if row["lStgyID"] == strategy_id)
                self.assertEqual(fmt.archive(registry_row["lbContext"]), expected_registry)
                self.assertEqual(fmt.archive(mirror_row["lbContext"]), expected_mirror)
                self.assertEqual(data["Stgy"], before["Stgy"])
                self.assertEqual({name for name in data if data[name] != before[name]}, {"System", "Trigger"})
                candidate = copy.deepcopy(data)
                apply_program_recipe(data, plan)
                self.assertEqual(data, candidate)
                with self.assertRaisesRegex(ValueError, "100..2147483647"):
                    apply_program_recipe(data, {"strategy_edits": [dict(plan["strategy_edits"][0], interval_ms=99)]})
                self.assertEqual(data, candidate)

    def test_event_creation_and_empty_deletion_use_exact_trigger_identity(self):
        import mcgs_file as m
        import mcgs_recipe_strategy as archive
        from offline_program_recipe import read_trigger_row

        for family in ("Stu", "Pro"):
            with self.subTest(family=family):
                project = {"variables":[{"name":"EventSwitch","type":"boolean"}], "pages":[{"name":"Main"}]}
                baseline = m.create_data(project,family)
                variable, = [v for v in m.inspect_data(baseline)["variables"] if v["name"]=="EventSwitch"]
                add = {"op":"add_event_strategy", "name":"AuditEmptyEvent",
                       "variable":{k:variable[k] for k in ("id","name")},
                       "edge":"falling", "comment":"Local event comment"}
                remove = {"op":"delete_event_strategy", "name":add["name"]}
                data = m.edit_data(copy.deepcopy(baseline),{"strategy_edits":[add]})
                via_create = m.create_data(dict(project, edits={"strategy_edits":[add]}),family)
                self.assertEqual(data,via_create)
                _, registry_row, registry = strategy_state(data)
                trigger = registry.triggers[-1]
                block = registry.strategies[-1]
                row = data["Trigger"]["rows"][-1]
                self.assertEqual((trigger.class_name,trigger.schema),("CTriggerEvent",0))
                self.assertEqual(trigger.fields["event_words"],[0,1])
                self.assertEqual(trigger.fields["event_expression"],"EventSwitch")
                self.assertEqual(trigger.fields["event_cache"],b"")
                self.assertEqual(trigger.fields["common_tail"],[0,0,0])
                self.assertEqual((block.fields["rows"],block.fields["comment"]),([],add["comment"]))
                self.assertEqual((row["iID"],row["lType"],row["lStgyID"]),
                                 (trigger.fields["trigger_id"],4,trigger.fields["strategy_id"]))
                self.assertEqual((row["strNote"],row["iTemp1"],row["iTemp2"]),("当确定的条件满足时运行",None,None))
                self.assertEqual(read_trigger_row(row,trigger).fields,trigger.fields)
                self.assertEqual(set(k for k in data if data[k]!=baseline[k]),{"Stgy","System","Trigger"})
                with self.assertRaisesRegex(ValueError,"Strategy name collision"):
                    m.edit_data(copy.deepcopy(data),{"strategy_edits":[add]})
                wrong_var = dict(add,variable=dict(add["variable"],id=variable["id"]+1))
                with self.assertRaisesRegex(ValueError,"Event trigger variable ID"):
                    m.edit_data(copy.deepcopy(baseline),{"strategy_edits":[wrong_var]})

                with_body = m.edit_data(copy.deepcopy(data),{"strategy_edits":[
                    {"op":"insert_script_row","name":add["name"],"row":0,"source":"EventSwitch=0"}]})
                self.assertEqual(m.edit_data(with_body,{"strategy_edits":[remove]}),baseline)
                referenced = m.edit_data(copy.deepcopy(data),{"pages":[{"id":1,"events":{"open":add["name"]}}]})
                with self.assertRaisesRegex(ValueError,"name reference"):
                    m.edit_data(referenced,{"strategy_edits":[remove]})

                # Hold both identities when an existing empty Event is stored under a different key.
                physical_id = row["iID"]
                trigger.fields["trigger_id"] += 2
                row["lbContext"] = m.f.wrap_like(row["lbContext"],archive.serialize_trigger_payload(trigger))
                registry_row["lbContext"] = m.f.wrap_like(registry_row["lbContext"],registry.serialize())
                aliased = copy.deepcopy(data)
                replacement = dict(add,name="AuditReplacementEvent")
                m.edit_data(aliased,{"strategy_edits":[remove,replacement]})
                self.assertGreater(aliased["Trigger"]["rows"][-1]["iID"],trigger.fields["trigger_id"])
                self.assertFalse(any(entry["iID"]==physical_id for entry in aliased["Trigger"]["rows"]))
                m.edit_data(aliased,{"strategy_edits":[dict(remove,name=replacement["name"])]})
                self.assertEqual(aliased,baseline)
                m.edit_data(data,{"strategy_edits":[remove]})
                self.assertEqual(data,baseline)

    def test_calendar_projects_use_native_clock_and_dual_archive_selectors(self):
        import mcgs_recipe_strategy as archive
        import native_format as fmt

        for filename, wire in (("blank-project.json", 0x10000), ("blank-project-stu.json", 0x2320000)):
            with self.subTest(filename=filename):
                data = json.loads((BASE / "assets" / filename).read_text(encoding="utf-8-sig"))
                original_strategy, system, registry = strategy_state(data)
                default, = [node for node in registry.triggers if node.class_name == "CTriggerLoop"]
                block = next(node for node in registry.strategies if node.fields["tail_words"][2] == 1)
                with self.assertRaisesRegex(ValueError, "default Loop locks"):
                    apply_program_recipe(data, {"strategy_edits":[{"op":"set_loop_calendar","name":block.fields["name"],
                                                                   "hour":23,"minute":58,"second":37}]})

                next_strategy_id = max(node.fields["tail_words"][2] for node in registry.strategies) + 1
                next_trigger_id = max(row["iID"] for row in data["Trigger"]["rows"]) + 1
                custom = copy.deepcopy(block)
                custom.fields["name"] = "AuditDailyCycle"
                custom.fields["rows"] = []
                custom.fields["tail_words"][2] = next_strategy_id
                archive.refresh_strategy_metadata_length(custom)
                trigger = copy.deepcopy(default)
                trigger.fields.update(trigger_id=next_trigger_id,strategy_id=next_strategy_id,
                                      loop_tail=[wire,60000,1,1,0,0,0,0])
                donor = next(row for row in data["Trigger"]["rows"] if row["lStgyID"] == 1)
                mirror = copy.deepcopy(trigger)
                if filename.endswith("-stu.json"):
                    mirror.fields["loop_tail"][0] -= 0x10000
                row = dict(donor, iID=next_trigger_id, lStgyID=next_strategy_id,
                           lbContext=fmt.wrap_like(donor["lbContext"], archive.serialize_trigger_payload(mirror)))
                data["Trigger"]["rows"].append(row)
                registry.strategies.append(custom)
                registry.triggers.append(trigger)
                original_strategy["lbObjects"] = fmt.wrap_like(
                    original_strategy["lbObjects"], archive.serialize_strategy_array(registry.strategies))
                system["lbContext"] = fmt.wrap_like(system["lbContext"], registry.serialize())
                before = copy.deepcopy(data)
                request = {"op":"set_loop_calendar","name":"AuditDailyCycle","hour":23,"minute":58,"second":37}
                with self.assertRaisesRegex(ValueError, "requires hour, minute and second"):
                    apply_program_recipe(data, {"strategy_edits":[{"op":"set_loop_calendar","name":"AuditDailyCycle","second":37}]})
                self.assertEqual(data,before)

                apply_program_recipe(data, {"strategy_edits":[request]})
                _, _, after = strategy_state(data)
                out = next(item for item in after.triggers if item.fields["strategy_id"] == next_strategy_id)
                self.assertEqual(out.fields["loop_tail"], [0x30001,60000,1,1,23,58,37,0])
                self.assertEqual(data["Stgy"],before["Stgy"])
                self.assertEqual({name for name in data if data[name] != before[name]}, {"System","Trigger"})
                expected = copy.deepcopy(data)
                partial = {"op":"set_loop_calendar","name":"AuditDailyCycle","second":38}
                apply_program_recipe(data, {"strategy_edits":[partial]})
                apply_program_recipe(data, {"strategy_edits":[dict(partial,second=37)]})
                self.assertEqual(data,expected)

                from offline_program_recipe import linked_loop_pair

                def wire():
                    _, _, registry = strategy_state(data)
                    active = next(item for item in registry.strategies if item.fields["name"] == request["name"])
                    canonical, _, mirror = linked_loop_pair(registry, data["Trigger"]["rows"], active)
                    return canonical.fields["loop_tail"], mirror.fields["loop_tail"]

                for patch, expected_words in (
                    (dict(calendar_period="year", month=11, day=17, hour=21, minute=43, second=27),
                     [0x10001, 60000, 11, 17, 21, 43, 27, 0]),
                    (dict(calendar_period="month", day=19, hour=20, minute=44, second=28),
                     [0x20001, 60000, 11, 19, 20, 44, 28, 0]),
                    (dict(calendar_period="hour", minute=45, second=29),
                     [0x40001, 60000, 11, 19, 20, 45, 29, 0]),
                    (dict(calendar_period="minute", second=31), [0x50001, 60000, 11, 19, 20, 45, 31, 0]),
                ):
                    apply_program_recipe(data, {"strategy_edits": [dict(op=request["op"], name=request["name"], **patch)]})
                    self.assertEqual(wire(), (expected_words, expected_words))

                minute = copy.deepcopy(data)
                interval = {"op": "set_loop_interval", "name": request["name"], "interval_ms": 71629}
                with self.assertRaisesRegex(ValueError, "requires the original interval mode"):
                    apply_program_recipe(data, {"strategy_edits": [interval]})
                self.assertEqual(data, minute)
                apply_program_recipe(data, {"strategy_edits": [dict(interval, switch_from_calendar=True)]})
                self.assertEqual(wire(), ([0x50000, 71629, 11, 19, 20, 45, 31, 0],
                                          [0x40000, 71629, 11, 19, 20, 45, 31, 0]))
                apply_program_recipe(data, {"strategy_edits": [dict(interval, interval_ms=60000),
                                     dict(request, calendar_period="minute", hour=20, minute=45, second=31)]})
                self.assertEqual(data, minute)

    def test_add_and_delete_empty_custom_loop(self):
        for fixture in ("blank-project.json", "blank-project-stu.json"):
            with self.subTest(fixture=fixture):
                data = json.loads((BASE / "assets" / fixture).read_text(encoding="utf-8-sig"))
                before = copy.deepcopy(data)
                name = "AuditCustomTimedLoop"
                create = dict(op="add_loop_strategy", name=name, interval_ms=1234, comment="scheduled")
                apply_program_recipe(data, {"strategy_edits": [create]})
                _, _, registry = strategy_state(data)
                block = registry.strategies[-1]
                trigger = registry.triggers[-1]
                self.assertEqual((block.fields["name"], block.fields["comment"], block.fields["rows"]),
                                 (name, "scheduled", []))
                self.assertEqual(trigger.class_name, "CTriggerLoop")
                self.assertEqual(trigger.fields["strategy_id"], block.fields["tail_words"][2])
                self.assertEqual(trigger.fields["loop_tail"], [65536, 1234, 1, 1, 0, 0, 0, 0])
                with self.assertRaisesRegex(ValueError, "name collision"):
                    apply_program_recipe(data, {"strategy_edits": [create]})
                apply_program_recipe(data, {"strategy_edits": [
                    dict(op="set_loop_calendar", name=name, calendar_period="hour", minute=15, second=20),
                    dict(op="delete_loop_strategy", name=name)]})
                self.assertEqual(data, before)

    def test_delete_nonempty_timed_strategies_preserves_survivors_and_blocks_references(self):
        import mcgs_file as m
        import mcgs_recipe_strategy as archive

        loop, event, survivor = "AuditTimedLoop", "AuditTimedEvent", "AuditSurvivingProg"
        for family in ("Stu", "Pro"):
            with self.subTest(family=family):
                data = m.create_data({"variables": [{"name": "AuditSwitch", "type": "boolean"}],
                                      "pages": [{"name": "Main"}]}, family)
                before = copy.deepcopy(data)
                switch = next(row for row in m.f.variables(m.f.archive(m.system(data, "ObjData")["lbContext"]))
                              if row["name"] == "AuditSwitch")
                apply_program_recipe(data, {"strategy_edits": [
                    {"op": "add_loop_strategy", "name": loop, "interval_ms": 1000},
                    {"op": "add_event_strategy", "name": event,
                     "variable": {"id": switch["id"], "name": switch["name"]}},
                    {"op": "add_user_strategy", "name": survivor, "source": "AuditSwitch=0"},
                    {"op": "insert_script_row", "name": loop, "row": 0, "source": "AuditSwitch=1"},
                    {"op": "insert_script_row", "name": event, "row": 0, "source": "AuditSwitch=0"},
                ]})
                row, system, registry = strategy_state(data)
                actions = {block.fields["name"]: archive.single_program_action(block)
                           for block in registry.strategies[-3:]}
                for index, action in enumerate(actions.values(), 1):
                    action.fields["compiled"] = bytes((index, 7, 0, 1))
                row["lbObjects"] = m.f.wrap_like(row["lbObjects"], archive.serialize_strategy_array(registry.strategies))
                system["lbContext"] = m.f.wrap_like(system["lbContext"], registry.serialize())
                selected = registry.strategies[-3:-1]
                removed_ids = {block.fields["tail_words"][2] for block in selected}
                survivors = registry.strategies[:-3] + registry.strategies[-1:]
                kept_triggers = [trigger for trigger in registry.triggers
                                 if trigger.fields["strategy_id"] not in removed_ids]
                kept_rows = [item for item in data["Trigger"]["rows"] if item["lStgyID"] not in removed_ids]
                deletions = [{"op": "delete_loop_strategy", "name": loop},
                             {"op": "delete_event_strategy", "name": event}]

                referenced = m.edit_data(copy.deepcopy(data), {
                    "pages": [{"id": 1, "events": {"open": f"!SetStgyMode({loop})"}}],
                    "strategy_edits": [{"op": "set_script", "name": survivor, "row": 0, "cell": 0,
                                        "index": 0, "value": f"!SetStgyMode({event})"}],
                })
                expected_unchanged = copy.deepcopy(referenced)
                for operation in deletions:
                    with self.assertRaisesRegex(ValueError, "name reference"):
                        apply_program_recipe(referenced, {"strategy_edits": [operation]})
                    self.assertEqual(referenced, expected_unchanged)

                shared = copy.deepcopy(data)
                other_row, other_system, other_registry = strategy_state(shared)
                program = archive.single_program_action(other_registry.strategies[-1])
                other_registry.strategies[-2].fields["rows"][0].fields["cells"][0].fields["actions"][0] = program
                other_row["lbObjects"] = m.f.wrap_like(other_row["lbObjects"],
                                                        archive.serialize_strategy_array(other_registry.strategies))
                other_system["lbContext"] = m.f.wrap_like(other_system["lbContext"], other_registry.serialize())
                expected_unchanged = copy.deepcopy(shared)
                with self.assertRaisesRegex(ValueError, "shared with another block"):
                    apply_program_recipe(shared, {"strategy_edits": deletions})
                self.assertEqual(shared, expected_unchanged)

                changed = m.edit_data(copy.deepcopy(data), {"strategy_edits": deletions})
                result = strategy_state(changed)[2]
                self.assertEqual((result.strategies, result.triggers), (survivors, kept_triggers))
                self.assertEqual(changed["Trigger"]["rows"], kept_rows)
                self.assertEqual({key for key in data if data[key] != changed[key]}, {"System", "Stgy", "Trigger"})
                restored = m.edit_data(changed, {"strategy_edits": [{"op": "delete_user_strategy", "name": survivor}]})
                self.assertEqual(restored, before)

    def test_rename_recipe_and_delete_user_strategy(self):
        for filename in ("blank-project.json", "blank-project-stu.json"):
            data = json.loads((BASE / "assets" / filename).read_text(encoding="utf-8-sig"))
            original = copy.deepcopy(data)
            old, new = "UnusedRecipeAlpha", "UnusedRecipeBeta"
            apply_program_recipe(data, {"recipe_edits": [{"op": "add_group", "name": old}]})
            row_id = recipe_state(data)[3][old][0]["iID"]
            rename = {"op": "rename_group", "name": old, "new_name": new}
            apply_program_recipe(data, {"recipe_edits": [rename]})
            self.assertEqual(recipe_state(data)[3][new][0]["iID"], row_id)
            apply_program_recipe(data, {"recipe_edits": [{"op": "delete_group", "name": new}]})
            st = "CustomUserStrategyAlpha"
            apply_program_recipe(data, {"strategy_edits": [{"op": "add_user_strategy", "name": st, "source": "1"}]})
            apply_program_recipe(data, {"strategy_edits": [{"op": "delete_user_strategy", "name": st}]})
            self.assertEqual(data, original)

    def test_delete_first_user_strategy_keeps_surviving_ids_and_fields(self):
        for filename in ("blank-project.json", "blank-project-stu.json"):
            with self.subTest(filename=filename):
                data = json.loads((BASE / "assets" / filename).read_text(encoding="utf-8-sig"))
                edits = [{"op": "add_user_strategy", "name": name, "source": name + "_body"}
                         for name in ("FirstUserAlpha", "SecondUserBeta", "ThirdUserGamma")]
                apply_program_recipe(data, {"strategy_edits": edits})
                registry = strategy_state(data)[2]
                target = registry.strategies[-3]
                target_id = target.fields["tail_words"][2]
                expected_blocks = [b for b in registry.strategies if b is not target]
                expected_triggers = [t for t in registry.triggers if t.fields["strategy_id"] != target_id]
                expected_rows = [r for r in data["Trigger"]["rows"] if r["lStgyID"] != target_id]
                apply_program_recipe(data, {"strategy_edits": [
                    {"op": "delete_user_strategy", "name": target.fields["name"]}]})
                result = strategy_state(data)[2]
                self.assertEqual(result.strategies, expected_blocks)
                self.assertEqual(result.triggers, expected_triggers)
                self.assertEqual(data["Trigger"]["rows"], expected_rows)

    def test_referenced_recipe_and_strategy_guard(self):
        group, st = "BoundRecipeAlpha", "BoundStrategyAlpha"
        apply_program_recipe(self.data, {"recipe_edits": [{"op": "add_group", "name": group}],
            "strategy_edits": [{"op": "add_user_strategy", "name": st, "source": group}]})
        with self.assertRaisesRegex(ValueError, "name reference"):
            apply_program_recipe(self.data, {"recipe_edits": [
                {"op": "rename_group", "name": group, "new_name": "OtherRecipeBeta"}]})
        apply_program_recipe(self.data, {"recipe_edits": [
            {"op": "insert_record", "name": group, "index": 0, "values": [st]}]})
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, "name reference"):
            apply_program_recipe(self.data, {"strategy_edits": [{"op": "delete_user_strategy", "name": st}]})
        self.assertEqual(before, self.data)

    def test_first_group_uses_real_family_layout(self):
        for file_name, expected in (("blank-project.json", (1134562542, ())),
                                    ("blank-project-stu.json", (1134564147, (0, 2, 0)))):
            with self.subTest(project=file_name):
                data = json.loads((BASE / "assets" / file_name).read_text(encoding="utf-8-sig"))
                apply_program_recipe(data, {"recipe_edits":[{"op":"add_group","name":"first"}]})
                recipe = recipe_state(data)[3]["first"][1]
                self.assertEqual((recipe.format_marker, recipe.log_tail), expected)

    def test_disagreement_leaves_batch_unchanged(self):
        self.data["Trigger"]["rows"][0]["lStgyID"] += 1
        before = copy.deepcopy(self.data)
        with self.assertRaises(ValueError):
            apply_program_recipe(self.data, {"recipe_edits":[{"op":"add_group","name":"batch"}],
                    "strategy_edits":[{"op":"add_user_strategy","name":"test","source":"one"}]})
        self.assertEqual(self.data,before)
