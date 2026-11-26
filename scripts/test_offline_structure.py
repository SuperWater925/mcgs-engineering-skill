"""Offline structural edit regressions on both unmodified native factory families."""
import copy
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets/pro-3.5-cli/scripts'))
import mcgs_file as m
import offline_structure as structure


def rect(name):
    return {'type': 'rectangle', 'name': name, 'bounds': [1, 2, 31, 22]}


def project(family):
    return m.create_data({'variables': [{'name': 'UnboundScalar', 'type': 'number', 'initial': '1'}],
                          'pages': [{'name': 'StartupPage', 'controls': [rect(n) for n in ('First', 'DropMe', 'Last')]},
                                    {'name': 'AuxiliaryPage'}, {'name': 'SparePage'}]}, family)


def selector(entry):
    return {'index': entry['index'], 'name': entry['name'], 'type_id': int(entry['kind'], 16), 'sha256': entry['sha256']}


def controls(data):
    return m.inspect_data(data)['pages'][0]['controls']


class OfflineStructureTests(unittest.TestCase):
    def test_native_default_data_group_can_be_added_without_inheriting_a_scalar(self):
        for family in ("Stu", "Pro"):
            with self.subTest(family=family):
                data = project(family)
                original = m.f.archive(m.system(data, "ObjData")["lbContext"])
                before = m.f.variables(original)
                spec = {"add_variables": [
                    {"name": "EmptyGroup", "type": "group"},
                    {"name": "AdditionalScalar", "type": "number", "initial": "123"},
                ]}
                changed = m.edit_data(copy.deepcopy(data), spec)
                output = m.f.archive(m.system(changed, "ObjData")["lbContext"])
                rewritten = m.f.variables(output)
                self.assertEqual(rewritten[:-2], before)
                self.assertEqual(output[12:len(original)], original[12:])
                group, scalar = rewritten[-2:]
                self.assertEqual(
                    (group["id"], group["name"], group["kind"], group["initial"], group["note"], group["unit"]),
                    (max(record["id"] for record in before)+1, "EmptyGroup", 0xffffffff, "0", "", ""))
                tail = struct.pack("<III", 0, 2, 0) if family == "Stu" else b""
                self.assertEqual(group["extension"], bytes(12) + m.f.text("") + tail)
                self.assertEqual((scalar["id"], scalar["initial"]), (group["id"]+1, "123"))
                self.assertEqual(m.inspect_data(changed)["data_groups"],
                                 [{"id": group["id"], "name": "EmptyGroup", "members": [], "order_editable": False}])
                expected = copy.deepcopy(data)
                m.system(expected, "ObjData")["lbContext"] = m.system(changed, "ObjData")["lbContext"]
                self.assertEqual(expected, changed)

                with self.assertRaisesRegex(ValueError, "accepts only name and type"):
                    m.edit_data(copy.deepcopy(data), {"add_variables": [
                        {"name": "EmptyGroup", "type": "group", "initial": "1"}]})
                with self.assertRaisesRegex(ValueError, "Duplicate variable"):
                    m.edit_data(changed, {"add_variables": [{"name": "emptygroup", "type": "group"}]})

    def test_delete_default_empty_data_group_preserves_other_groups_and_rejects_conflicts(self):
        for family in ("Stu", "Pro"):
            with self.subTest(family=family):
                original = project(family)
                spec = {"add_variables":[{"name":name, "type":"group"} for name in ("DiscardGroup", "KeepGroup")]}
                data = m.edit_data(copy.deepcopy(original), spec)
                discarded, keep = m.inspect_data(data)["data_groups"]
                target = {key:discarded[key] for key in ("id", "name")}
                delete = {"delete_data_groups":[target]}
                with self.assertRaisesRegex(ValueError, "added or edited and deleted"):
                    m.edit_data(copy.deepcopy(data), {**delete, "data_group_members":dict(target,before=[],after=[])})
                with self.assertRaisesRegex(ValueError, "added or edited and deleted"):
                    m.edit_data(copy.deepcopy(original), {**delete, **spec})
                with self.assertRaisesRegex(ValueError, "distinct integer IDs"):
                    m.edit_data(copy.deepcopy(data), {"delete_data_groups":[target,target]})

                linked = copy.deepcopy(data)
                linked["Data"]["rows"].append({"iDataID":discarded["id"]})
                with self.assertRaisesRegex(ValueError, "Data.iDataID"):
                    m.edit_data(linked, delete)
                custom = copy.deepcopy(data)
                slot = m.system(custom, "ObjData")
                custom_rows = m.f.variables(m.f.archive(slot["lbContext"]))
                member = next(row for row in custom_rows if row["id"] == discarded["id"])
                member["note"] = "Custom group"
                slot["lbContext"] = m.f.wrap_like(slot["lbContext"], m.f.pack_variables(custom_rows))
                with self.assertRaisesRegex(ValueError, "verified default empty user group"):
                    m.edit_data(custom, delete)

                output = m.edit_data(copy.deepcopy(data), delete)
                self.assertEqual(m.inspect_data(output)["data_groups"], [keep])
                all_removed = m.edit_data(output, {"delete_data_groups":[{key:keep[key] for key in ("id", "name")}]})
                self.assertEqual(all_removed, original)

    def test_data_group_members_uses_existing_scalars_and_rejects_actual_dependencies(self):
        for family in ("Stu", "Pro"):
            with self.subTest(family=family):
                data = m.edit_data(project(family), {"add_variables": [
                    {"name": "AdditionalScalar", "type": "number", "initial": "2"},
                    {"name": "EncodingAnchor", "type": "group"},
                    {"name": "IndependentGroup", "type": "group"},
                ]})
                obj = m.system(data, "ObjData")
                native = m.f
                unanchored = native.archive(obj["lbContext"])
                records = native.variables(unanchored)
                by_name = {record["name"]: record for record in records}
                desired = [{"id":by_name[name]["id"], "name":name} for name in ("UnboundScalar", "AdditionalScalar")]
                target = by_name["IndependentGroup"]
                operation = {"id":target["id"], "name":target["name"], "before":[], "after":desired}
                if family == "Pro":
                    with self.assertRaisesRegex(ValueError, "does not identify a native CString"):
                        m.edit_data(copy.deepcopy(data), {"data_group_members":operation})

                anchor = by_name["EncodingAnchor"]
                anchor["extension"] = (struct.pack("<I", 1) + native.text("UnboundScalar")
                                       + anchor["extension"][4:])
                before = native.pack_variables(records)
                obj["lbContext"] = native.wrap_like(obj["lbContext"], before)
                with self.assertRaisesRegex(ValueError, "must be distinct"):
                    m.edit_data(copy.deepcopy(data), {"data_group_members":dict(operation, after=desired[:1]*2)})
                blocked = copy.deepcopy(data)
                blocked["Data"]["rows"].append({"iDataID":target["id"]})
                with self.assertRaisesRegex(ValueError, "Data.iDataID"):
                    m.edit_data(blocked, {"data_group_members":operation})

                after = m.edit_data(copy.deepcopy(data), {"data_group_members":operation})
                body = native.archive(m.system(after, "ObjData")["lbContext"])
                start, end = native.variables(before).group_member_spans[target["id"]]
                wire = struct.pack("<I", 2) + b"".join(native.text(member["name"]) for member in desired)
                self.assertEqual(body[8:start-4], before[8:start-4])
                self.assertEqual(body[start-4:], wire + before[end:])
                self.assertEqual(m.inspect_data(after)["data_groups"][-1]["members"], desired)
                removed = m.edit_data(after, {"data_group_members":dict(operation, before=desired, after=[])})
                self.assertEqual(native.archive(m.system(removed, "ObjData")["lbContext"]), before)

    def test_first_pro_empty_group_uses_native_cstring_cutoff(self):
        data = m.edit_data(project("Pro"), {"add_variables":[{"name":"SoleGroup", "type":"group"}]})
        slot = m.system(data, "ObjData")
        native = m.f
        before = native.archive(slot["lbContext"])
        flat = native.variables(before)
        variable = next(record for record in flat if record["name"] == "UnboundScalar")
        group = next(record for record in flat if record["name"] == "SoleGroup")
        member = {"id":variable["id"], "name":variable["name"]}
        change = {"id":group["id"], "name":group["name"], "before":[], "after":[member]}
        with self.assertRaisesRegex(ValueError, "does not identify a native CString"):
            m.edit_data(copy.deepcopy(data), {"data_group_members":change})

        original = struct.pack("<f", 12.1) + before[4:]
        slot["lbContext"] = native.wrap_like(slot["lbContext"], original)
        parsed = native.variables(original)
        self.assertNotIn(group["id"], parsed.group_member_spans)
        begin, end = parsed.empty_group_spans[group["id"]]
        self.assertEqual(begin, end)
        self.assertEqual(original[begin-4:begin], bytes(4))
        linked = m.edit_data(copy.deepcopy(data), {"data_group_members":change})
        after = native.archive(m.system(linked, "ObjData")["lbContext"])
        vector = struct.pack("<I", 1) + native.text(member["name"])
        self.assertEqual(after[8:], original[8:begin-4] + vector + original[begin:])
        self.assertEqual(m.inspect_data(linked)["data_groups"][0]["members"], [member])
        cleared = m.edit_data(linked, {"data_group_members":dict(change,before=[member],after=[])})
        self.assertEqual(native.archive(m.system(cleared, "ObjData")["lbContext"]), original)

    def test_stu_empty_group_directory_can_store_its_first_named_member(self):
        data = m.edit_data(project("Stu"), {"add_variables":[
            {"name":"GroupA", "type":"group"}, {"name":"GroupB", "type":"group"}]})
        original = m.f.archive(m.system(data, "ObjData")["lbContext"])
        records = m.f.variables(original)
        first, second = [row for row in records if row["kind"] == 0xffffffff]
        self.assertEqual(records.document_header, struct.pack("<f", 16.0))
        self.assertEqual(records.group_member_spans, {})
        self.assertEqual(set(records.empty_group_spans), {first["id"], second["id"]})
        scalar = next(row for row in records if row["name"] == "UnboundScalar")
        wanted = {"id":scalar["id"], "name":scalar["name"]}
        plan = {"id":second["id"], "name":second["name"], "before":[], "after":[wanted]}
        linked = m.edit_data(copy.deepcopy(data), {"data_group_members":plan})
        actual = m.inspect_data(linked)["data_groups"]
        self.assertEqual({row["name"]: row["members"] for row in actual}, {"GroupA":[], "GroupB":[wanted]})
        inverse = m.edit_data(linked, {"data_group_members":dict(plan, before=[wanted], after=[])})
        self.assertEqual(m.f.archive(m.system(inverse, "ObjData")["lbContext"]), original)

    def test_existing_data_group_reorder_preserves_archive_outside_selected_span(self):
        for family in ("Stu", "Pro"):
            with self.subTest(family=family):
                data = m.create_data({"variables": [
                    {"name": "Temperature", "type": "number", "initial": "1"},
                    {"name": "Flow", "type": "number", "initial": "2"},
                    {"name": "ExistingGroup", "type": "number", "initial": "0"},
                ], "pages": [{"name": "StartupPage"}]}, family)
                objdata = m.system(data, "ObjData")
                native = m.f
                records = native.variables(native.archive(objdata["lbContext"]))
                group = next(record for record in records if record["name"] == "ExistingGroup")
                group.update(kind=0xffffffff, prefix=struct.pack("<I", 0xffffffff) + group["prefix"][4:])
                before_wire = native.text("Temperature") + native.text("Flow")
                group["extension"] = struct.pack("<I", 2) + before_wire + group["extension"][4:]
                before = native.pack_variables(records)
                objdata["lbContext"] = native.wrap_like(objdata["lbContext"], before)
                group_id = group["id"]
                start, end = native.variables(before).group_member_spans[group_id]
                self.assertEqual(before[start:end], before_wire)
                found, = m.inspect_data(data)["data_groups"]
                self.assertTrue(found["order_editable"])
                members = found["members"]
                self.assertEqual([member["name"] for member in members], ["Temperature", "Flow"])
                reorder = {"id": group_id, "name": group["name"],
                           "before": members, "after": members[::-1]}
                for invalid in (dict(reorder, before=members[::-1]),
                                dict(reorder, after=[members[0], members[0]]),
                                dict(reorder, after=[dict(members[0], name="Shift"), members[1]])):
                    with self.assertRaises(ValueError):
                        m.edit_data(copy.deepcopy(data), {"data_group_orders": [invalid]})
                changed_data = m.edit_data(copy.deepcopy(data), {"data_group_orders": [reorder]})
                after = native.archive(m.system(changed_data, "ObjData")["lbContext"])
                after_wire = native.text("Flow") + native.text("Temperature")
                self.assertEqual(after, before[:start] + after_wire + before[end:])
                self.assertEqual(m.inspect_data(changed_data)["data_groups"][0]["members"], members[::-1])
                expected = copy.deepcopy(data)
                m.system(expected, "ObjData")["lbContext"] = m.system(changed_data, "ObjData")["lbContext"]
                self.assertEqual(changed_data, expected)

                group["extension"] = (group["extension"][:8 + len(before_wire)]
                                      + struct.pack("<II", 1, members[0]["id"])
                                      + group["extension"][12 + len(before_wire):])
                objdata["lbContext"] = native.wrap_like(objdata["lbContext"], native.pack_variables(records))
                self.assertFalse(m.inspect_data(data)["data_groups"][0]["order_editable"])
                with self.assertRaisesRegex(ValueError, "empty alarm and auxiliary"):
                    m.edit_data(data, {"data_group_orders": [reorder]})

    def test_bounded_edit_and_structure_share_one_candidate_transaction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            before = project('Pro')
            source = root/'original.mcp'
            source.write_bytes(b'original fixture')
            baseline = m.sha(source)
            first = controls(before)[0]
            page = {'id':1, 'control_order':[2,0,1]}
            spec = {'source_sha256':baseline, 'pages':[page],
                    'add_pages':[{'template_page_id':1, 'name':'NewPage'}]}
            patch_spec = {'input_sha256':baseline, 'controls':[{'window':1, 'path':[0],
                          'sha256':first['sha256'], 'edits':{'fill':0x123456}}]}
            (root/'controls.json').write_text(json.dumps(patch_spec), encoding='utf-8')
            plan = root/'batch.json'
            plan.write_text(json.dumps({'input_sha256':baseline, 'steps':[
                {'command':'controls','spec':'controls.json'}]}), encoding='utf-8')

            expected_page = {**page, 'controls':[{'name':'First', 'sha256':first['sha256'],
                                                 'edits':{'fill':0x123456}}]}
            expected = m.edit_data(copy.deepcopy(before), {**spec, 'pages':[expected_page]})
            with patch.object(m, 'read', side_effect=[before,expected]) as read, patch.object(m, 'db') as db:
                result = m.write_project(root/'changed.mcp', spec, source, batch_plan=plan)
            self.assertEqual(read.call_count, 2)
            db.assert_called_once()
            request = db.call_args.args[0]
            self.assertEqual(request['expected_sha256'], baseline)
            self.assertEqual([change['action'] for change in request['changes']], ['update','insert-page'])
            self.assertEqual(request['changes'][0]['values']['lbObjects'], expected['WndUser']['rows'][0]['lbObjects'])
            self.assertEqual(result['bounded_batch'], {'step_count':1, 'fields':1})
            self.assertEqual(m.sha(source), baseline)

    def test_binding_assertions_and_reference_aware_rename(self):
        for family in ('Stu', 'Pro'):
            data = project(family)
            m.edit_data(data, {'pages':[{'id':1,'add_controls':[{**rect('Entry'),'type':'numeric-input','binding':'UnboundScalar'}]}]})
            entry = controls(data)[-1]
            def edit(edits):
                return {'pages':[{'id':1,'controls':[{'name':'Entry','sha256':entry['sha256'],'edits':edits}]}]}
            for edits in ({'binding':'Missing','binding_id':1,'binding_type':2},
                          {'binding':'UnboundScalar','binding_id':-1}):
                with self.assertRaises(ValueError):
                    m.edit_data(data,edit(edits))
            linked = copy.deepcopy(data)
            m.edit_data(linked,{'pages':[{'id':2,'events':{'open':'StartupPage.Entry=1'}}]})
            with self.assertRaisesRegex(ValueError,'WndUser/AuxiliaryPage'):
                m.edit_data(linked,edit({'name':'OtherEntry'}))
            m.edit_data(data,edit({'name':'OtherEntry'}))
            self.assertEqual(controls(data)[-1]['name'],'OtherEntry')

    def test_variable_rename_updates_only_exact_input_bindings(self):
        from mcs_input_text import InputRecord
        from mcs_window_archive import WindowArchive
        from 原生界面样式 import CommonEnvelope, GroupArchive

        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                def binding(typ, name, variable):
                    return {**rect(name), 'type':typ, 'binding':variable}

                original = m.create_data({'variables':[
                    {'name':'FixtureNumber','type':'number','initial':'1'},
                    {'name':'FixtureText','type':'string','initial':'One'}],
                    'pages':[{'name':'Main','controls':[
                        binding('numeric-input','Entry','FixtureNumber'),
                        {**rect('Group'),'type':'group','children':[
                            binding('character-display','TextEntry','FixtureText'), rect('Other')]}
                    ]},{'name':'OtherPage'}]}, family)
                catalog = m.VariableCatalog(original)
                renames = [
                    {'source':{'id':catalog[name]['id'],'name':name}, 'name':name+'New',
                     'update_input_bindings':True}
                    for name in ('FixtureNumber','FixtureText')]
                linked = copy.deepcopy(original)
                m.edit_data(linked,{'pages':[{'id':2,'events':{'open':'FixtureText = "Two"'}}]})
                pristine = copy.deepcopy(linked)
                with self.assertRaisesRegex(ValueError, 'WndUser/OtherPage'):
                    structure.remove_variables(linked, [], renames)
                self.assertEqual(linked, pristine)
                with self.assertRaisesRegex(ValueError, 'WndUser/Main'):
                    m.edit_data(copy.deepcopy(original), {'rename_variables':[
                        {k:v for k,v in renames[0].items() if k!='update_input_bindings'}]})

                updated = m.edit_data(copy.deepcopy(original), {'rename_variables':renames})
                new_catalog = m.VariableCatalog(updated)
                before, after = [WindowArchive.parse(m.f.archive(d['WndUser']['rows'][0]['lbObjects']))
                                 for d in (original,updated)]
                before_group = GroupArchive.parse(before.controls[1])
                after_group = GroupArchive.parse(after.controls[1])
                self.assertEqual((after.prefix,after.trailer),(before.prefix,before.trailer))
                self.assertEqual(after_group.tail,before_group.tail)
                self.assertEqual(after_group.children[1].to_bytes(),before_group.children[1].to_bytes())
                pairs = [(before.controls[0],after.controls[0]),
                         (before_group.children[0],after_group.children[0])]
                for (old,new), rename in zip(pairs,renames):
                    name = rename['source']['name']
                    self.assertEqual(new_catalog[rename['name']]['id'],catalog[name]['id'])
                    self.assertNotIn(name,new_catalog)
                    old_body,new_body = [InputRecord.parse(CommonEnvelope.parse(c).project_without_animations())
                                         for c in (old,new)]
                    self.assertEqual((new_body.variable,new_body.variable_id,new_body.variable_type),
                                     (rename['name'],old_body.variable_id,old_body.variable_type))
                    self.assertEqual(new_body.expression_cache,b'')
                    new_body.variable=old_body.variable
                    new_body.expression_cache=old_body.expression_cache
                    self.assertEqual(new_body.to_bytes(),old_body.to_bytes())

    def test_page_dimensions_main_retarget_and_scalar_rename(self):
        for family in ('Stu','Pro'):
            data = project(family)
            m.edit_data(data,{'pages':[{'id':2,'width':721,'height':421}],
                              'retarget_main_pages':[{'source':{'id':1,'name':'StartupPage'},
                                                      'target':{'id':2,'name':'AuxiliaryPage'}}],
                              'delete_pages':[{'id':1,'name':'StartupPage'}]})
            page = data['WndUser']['rows'][0]
            settings=m.WindowSettings.parse(m.f.window(m.f.archive(page['lbObjects']))[2],identity=(2,'AuxiliaryPage'))
            self.assertEqual([settings.field(k).value for k in ('width','height')],[721,421])
            old=next(v for v in m.inspect_data(data)['variables'] if v['name']=='UnboundScalar')
            sel={'id':old['id'],'name':old['name']}
            m.edit_data(data,{'rename_variables':[{'source':sel,'name':'NewScalar'}]})
            new=next(v for v in m.inspect_data(data)['variables'] if v['name']=='NewScalar')
            self.assertEqual(new,{**old,'name':'NewScalar'})
            with self.assertRaises(ValueError):
                m.edit_data(data,{'pages':[{'id':2,'width':None}]})

    def test_create_and_initial_edits(self):
        for family in ('Stu','Pro'):
            spec={'pages':[{'name':'Main','width':740,'height':420}],
                  'edits':{'add_pages':[{'template_page_id':1,'name':'Extra','width':940}]}}
            data=m.create_data(spec,family)
            dims=[]
            for row in data['WndUser']['rows']:
                tail=m.f.window(m.f.archive(row['lbObjects']))[2]
                props=m.WindowSettings.parse(tail,identity=(row['iID'],row['strName']))
                dims.append(tuple(props.field(k).value for k in ('width','height')))
            self.assertEqual(dims,[(740,420),(940,420)])
            with self.assertRaises(ValueError):
                m.create_data({**spec,'edits':{'source_sha256':'unused'}},family)

    def test_group_geometry_roundtrip_and_references(self):
        for family in ('Stu', 'Pro'):
            data = project(family)
            page = {'id':1,'group_operations':[{'action':'group','name':'Panel',
                     'members':[selector(c) for c in controls(data)[:2]]}]}
            before = copy.deepcopy(data['WndUser']['rows'][0]['lbObjects'])
            linked = copy.deepcopy(data)
            m.edit_data(linked,{'pages':[{'id':2,'events':{'open':'StartupPage.First=1'}}]})
            with self.assertRaisesRegex(ValueError,'Referenced'):
                m.edit_data(linked,{'pages':[page]})
            m.edit_data(data,{'pages':[page]})
            self.assertEqual([c['name'] for c in controls(data)], ['Panel','Last'])
            m.edit_data(data,{'pages':[{'id':1,'group_operations':[{
                'action':'ungroup','member':selector(controls(data)[0])}]}]})
            self.assertEqual(data['WndUser']['rows'][0]['lbObjects'],before)

    def test_group_factory_and_page_background(self):
        group = {'type':'group','name':'Panel','bounds':[10,20,110,220],
                 'children':[{**rect('Child'),'bounds':[1000,1000,5000,5000]}]}
        data = m.create_data({'pages':[{'name':'Main','controls':[group]}]},'Pro')
        m.edit_data(data,{'pages':[{'id':1,'group_operations':[{
            'action':'ungroup','member':selector(controls(data)[0])}]}]})
        self.assertEqual(controls(data)[0]['bounds'],[20,40,60,120])
        for family in ('Pro','Stu'):
            data = m.create_data({'pages':[{'name':'Main','background':0x123456}]},family)
            row=data['WndUser']['rows'][0]
            props=m.WindowSettings.parse(m.f.window(m.f.archive(row['lbObjects']))[2],identity=(1,'Main'))
            self.assertEqual(props.field('background').value,0x123456)

    def test_native_group_children(self):
        from control_factory import GroupArchive, CommonEnvelope, record
        for family in ('Stu','Pro'):
            data=project(family)
            row=data['WndUser']['rows'][0]
            head,records,tail=m.f.window(m.f.archive(row['lbObjects']))
            outer=record(0x503a,records[0][1])
            group=GroupArchive(CommonEnvelope.parse(outer),[record(*r) for r in records[1:]],b'kept')
            row['lbObjects']=m.f.wrap_like(row['lbObjects'],m.f.pack_window(head,[(0x503a,group.to_record().payload)],tail))
            group_sel=selector(controls(data)[0])
            import hashlib
            kind,body=records[1]
            removal={'index':0,'name':'DropMe','type_id':kind,'sha256':hashlib.sha256(body).hexdigest()}
            spec={'pages':[{'id':1,'groups':[{'path':[group_sel],'remove_controls':[removal],'control_order':[1],
                                               'add_controls':[{**rect('Inserted'),'insert_at':0}]}]}]}
            linked=copy.deepcopy(data)
            m.edit_data(linked,{'pages':[{'id':2,'events':{'open':'StartupPage.First.DropMe=1'}}]})
            with self.assertRaisesRegex(ValueError,'Referenced'):
                m.edit_data(linked,spec)
            m.edit_data(data,spec)
            result=GroupArchive.parse(record(*m.f.window(m.f.archive(row['lbObjects']))[1][0]))
            self.assertEqual([m.f.common(c.payload)['name'] for c in result.children],['Inserted','Last'])
            self.assertEqual(result.children[1].payload,records[-1][1])
            self.assertEqual(result.tail,b'kept')

    def test_original_indexes_and_insertion_point(self):
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                data = project(family)
                before = controls(data)
                change = {'id': 1, 'remove_controls': [selector(before[1])], 'control_order': [2, 0],
                          'add_controls': [{**rect('Inserted'), 'insert_at': 1}]}
                m.edit_data(data, {'pages': [change]})
                after = controls(data)
                self.assertEqual([r['name'] for r in after], ['Last', 'Inserted', 'First'])
                self.assertEqual([after[0]['sha256'], after[2]['sha256']], [before[2]['sha256'], before[0]['sha256']])

    def test_control_preimages_and_permutation(self):
        data = project('Pro')
        sel = selector(controls(data)[1])
        for field, value in [('index', True), ('name', 'Wrong'), ('type_id', 0), ('sha256', '0' * 64)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.edit_data(copy.deepcopy(data), {'pages': [{'id': 1, 'remove_controls': [{**sel, field: value}]}]})
        for order in ([0, 1], [0, 0], [0, True], [2]):
            with self.subTest(order=order), self.assertRaises(ValueError):
                m.edit_data(copy.deepcopy(data), {'pages': [{'id': 1, 'remove_controls': [sel], 'control_order': order}]})

    def test_new_pages_inherit_or_override_the_native_description_in_both_copies(self):
        for family in ('Stu','Pro'):
            with self.subTest(family=family):
                data=m.create_data({'pages':[{'name':'SourcePage','description':'Original native note'}]},family)
                note_column=m.page_columns(data)[2]
                source=data['WndUser']['rows'][0]
                source[note_column]='Stale row note'
                output=m.edit_data(data,{'add_pages':[
                    {'id':2,'name':'Inherited','template_page_id':1},
                    {'id':3,'name':'Cleared','template_page_id':1,'description':''}]})
                pages={page['id']:page for page in m.inspect_data(output)['pages']}
                self.assertFalse(pages[1]['description_mirror_matches'])
                self.assertTrue(pages[2]['description_mirror_matches'])
                self.assertEqual(pages[2]['description'],'Original native note')
                self.assertTrue(pages[3]['description_mirror_matches'])
                self.assertEqual(pages[3]['description'],'')

    def test_page_rename_updates_startup_and_inverse_restores_archive(self):
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                data = project(family)
                baseline = copy.deepcopy(data)
                prefix = m.load_factory_asset('primitives', family)['root_prefix_size']
                for old, new in [('StartupPage', 'Wide Name'), ('Wide Name', 'StartupPage')]:
                    m.edit_data(data, {'rename_pages': [{'source': {'id': 1, 'name': old}, 'name': new}]})
                    root = m.f.archive(data['WndControl']['rows'][0]['lbObjects'])
                    arrays, _ = structure.startup_lists(root, prefix)
                    self.assertIn((new, 1), [(n.value, i) for names, ids in arrays for n, i in zip(names, ids)])
                self.assertEqual(data, baseline)
                with self.assertRaises(ValueError):
                    m.edit_data(data, {'delete_pages': [{'id': 1, 'name': 'StartupPage'}]})
                m.edit_data(data, {'delete_pages': [{'id': 3, 'name': 'SparePage'}]})
                self.assertEqual(data['WndUser']['rows'], baseline['WndUser']['rows'][:2])

    def test_main_page_lists_replace_preimages_and_remove_registered_pages(self):
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                data = project(family)
                root = data['WndControl']['rows'][0]
                baseline = copy.deepcopy(data)
                first = {'id':1,'name':'StartupPage'}
                second = {'id':2,'name':'AuxiliaryPage'}
                third = {'id':3,'name':'SparePage'}
                prefix = m.load_factory_asset('primitives', family)['root_prefix_size']
                old = m.f.archive(root['lbObjects'])
                _, old_end = structure.startup_lists(old, prefix)
                registration = {'startup':{'before':[first],'after':[second,first]},
                                'memory':{'before':[],'after':[third,second]}}
                m.edit_data(data, {'main_page_lists':registration})
                registered = copy.deepcopy(data)
                self.assertEqual(m.inspect_data(data)['main_page_lists'],
                                 {'startup':[second,first], 'memory':[third,second]})
                changed = m.f.archive(root['lbObjects'])
                _, changed_end = structure.startup_lists(changed, prefix)
                self.assertEqual((changed[:prefix],changed[changed_end:]),(old[:prefix],old[old_end:]))
                for bad in (
                    {'memory':{'before':[second,third],'after':[]}},
                    {'memory':{'before':[third,second],'after':[second,second]}},
                    {'memory':{'before':[third,second],'after':[{'id':True,'name':'StartupPage'}]}},
                    {'startup':{'before':[second,first],'after':[]}},
                ):
                    with self.subTest(bad=bad), self.assertRaises(ValueError):
                        m.edit_data(data, {'main_page_lists':bad})
                    self.assertEqual(data, registered)
                m.edit_data(data, {'main_page_lists':{
                    role:{'before':value['after'],'after':value['before']} for role,value in registration.items()}})
                self.assertEqual(data, baseline)
                with self.assertRaisesRegex(ValueError, 'startup or memory window'):
                    m.edit_data(copy.deepcopy(registered), {'delete_pages':[third]})
                m.edit_data(registered, {'main_page_lists':{'startup':{'before':[second,first],'after':[second]},
                                                           'memory':{'before':[third,second],'after':[]}},
                                         'delete_pages':[first,third]})
                self.assertEqual(m.inspect_data(registered)['main_page_lists'], {'startup':[second],'memory':[]})
                self.assertEqual([p['iID'] for p in registered['WndUser']['rows']], [second['id']])

    def test_retarget_public_window_preserves_other_pages_and_rejects_cycles(self):
        def change(host, source, target):
            return {'id':host['id'],'common_page':{'owner_name':host['name'],'source':source,'target':target}}
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                data = project(family)
                original = copy.deepcopy(data)
                host = {'id':1,'name':'StartupPage'}
                second = {'id':2,'name':'AuxiliaryPage'}
                third = {'id':3,'name':'SparePage'}
                m.edit_data(data, {'pages':[change(host,None,second)]})
                self.assertEqual(m.inspect_data(data)['pages'][0]['common_page'],second)
                linked = copy.deepcopy(data)
                with self.assertRaisesRegex(ValueError, 'reference cycle'):
                    m.edit_data(data, {'pages':[change(second,None,host)]})
                with self.assertRaisesRegex(ValueError, 'source selection'):
                    m.edit_data(data, {'pages':[change(host,None,third)]})
                self.assertEqual(data,linked)
                m.edit_data(data, {'pages':[change(host,second,third)]})
                self.assertEqual(m.inspect_data(data)['pages'][0]['common_page'],third)
                self.assertEqual(data['WndControl'],original['WndControl'])
                self.assertEqual(data['WndUser']['rows'][1:],original['WndUser']['rows'][1:])
                m.edit_data(data, {'pages':[change(host,third,None)]})
                self.assertEqual(data,original)

    def test_stu_common_window_layers_follow_every_slot_and_allow_shared_targets(self):
        host, branch, path, sink = [
            {'id': ident, 'name': name}
            for ident, name in enumerate(('HostPage', 'BranchPage', 'PathPage', 'SinkPage'), 1)
        ]
        data = m.create_data({'variables': [], 'pages': [
            {'name': page['name']} for page in (host, branch, path, sink)
        ]}, 'Stu')
        baseline = copy.deepcopy(data)

        def change(owner, layer, before, after):
            return {'id': owner['id'], 'common_page': {
                'owner_name': owner['name'], 'layer': layer, 'source': before, 'target': after,
            }}

        def host_event_tail(project):
            row = project['WndUser']['rows'][0]
            _, _, trailer = m.f.window(m.f.archive(row['lbObjects']))
            return m.WindowSettings.parse(trailer, identity=(host['id'], host['name'])).event_tail

        m.edit_data(data, {'pages': [
            change(branch, 'bottom', None, path),
            change(branch, 'middle', None, sink),
            change(path, 'top', None, sink),
            change(host, 'top', None, branch),
        ]})
        pages = m.inspect_data(data)['pages']
        self.assertIsNone(pages[0]['common_page'])
        self.assertEqual(pages[0]['common_page_layers'], {'bottom': None, 'middle': None, 'top': branch})
        self.assertEqual(pages[1]['common_page_layers'], {'bottom': path, 'middle': sink, 'top': None})
        self.assertEqual(pages[2]['common_page_layers'], {'bottom': None, 'middle': None, 'top': sink})
        before = host_event_tail(baseline)
        top_slot = len(before) - 84 + 16
        self.assertEqual(host_event_tail(data), before[:top_slot] + struct.pack('<i', branch['id']) + before[top_slot+4:])

        linked = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'reference cycle'):
            m.edit_data(data, {'pages': [change(sink, 'middle', None, host)]})
        with self.assertRaisesRegex(ValueError, 'already occupies'):
            m.edit_data(data, {'pages': [change(branch, 'top', None, sink)]})
        self.assertEqual(data, linked)
        m.edit_data(data, {'pages': [
            change(host, 'top', branch, None),
            change(path, 'top', sink, None),
            change(branch, 'middle', sink, None),
            change(branch, 'bottom', path, None),
        ]})
        self.assertEqual(data, baseline)

    def test_named_consumers_on_another_page(self):
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                data = project(family)
                sel = selector(controls(data)[1])
                m.edit_data(data, {'pages': [{'id': 2, 'events': {'open': 'StartupPage.DropMe=1'}}]})
                for spec in ({'pages': [{'id': 1, 'remove_controls': [sel]}]},
                             {'rename_pages': [{'source': {'id': 1, 'name': 'StartupPage'}, 'name': 'Other'}]}):
                    with self.assertRaisesRegex(ValueError, '(?i)reference'):
                        m.edit_data(copy.deepcopy(data), spec)
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    m.edit_data(data, {'rename_pages': [{'source': {'id': 3, 'name': 'SparePage'}, 'name': 'auxiliarypage'}]})

    def test_variable_deletion_checks_real_consumers(self):
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                data = project(family)
                before = m.inspect_data(data)['variables']
                variable = next(v for v in before if v['name'] == 'UnboundScalar')
                sel = {k: variable[k] for k in ('id', 'name')}
                spec = {'delete_variables': [sel]}
                linked = copy.deepcopy(data)
                m.edit_data(linked, {'pages': [{'id': 1, 'events': {'open': 'UnboundScalar=1'}}]})
                with self.assertRaises(ValueError):
                    m.edit_data(linked, spec)
                for table, column in [('Alarm', 'iDataObjID'), ('Alarm', 'iRelatePointID'),
                                      ('DDEConnection', 'iDataID'), ('Data', 'iDataID'), ('Data', 'ArgvObjID')]:
                    with self.subTest(table=table, column=column):
                        linked = copy.deepcopy(data)
                        linked[table]['rows'].append({column: sel['id']})
                        with self.assertRaises(ValueError):
                            m.edit_data(linked, spec)
                m.edit_data(data, spec)
                self.assertEqual(m.inspect_data(data)['variables'], [v for v in before if v != variable])


if __name__ == '__main__':
    unittest.main()
