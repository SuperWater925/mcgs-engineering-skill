"""Stu factory checks; set MCGS_STU_FACTORY_FIXTURE to the vendor standard/cool template for the ACE integration test."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets/pro-3.5-cli/scripts'))
import control_factory
import mcgs_file as project


class StuFactory(unittest.TestCase):
    def test_family_and_missing_local_primitive(self):
        with self.assertRaisesRegex(ValueError, 'neutral Stu primitive'):
            control_factory.primitive_record('label', source_pages=project.SourcePages([], 'Stu'))
        self.assertEqual(control_factory.primitive_record('label').type_id, 0x5008)
        data=project.create_data({'pages':[{'name':'试验首页'}], 'variables':[{'name':'新数值','type':'number'}]},'Stu')
        self.assertEqual(project.project_family(data),'Stu')
        self.assertEqual(project.VariableCatalog(data)['新数值']['kind'],2)
        self.assertTrue(all(not row['strPassword'] for row in data['SecurityUser']['rows']))
        self.assertEqual([r['strName'] for r in data['WndUser']['rows']],['试验首页'])

    def test_new_buttons_close_both_picture_gates(self):
        for family in ('Stu','Pro'):
            with self.subTest(family=family):
                presets=project.load_factory_asset('primitives',family)
                record=control_factory.primitive_record('button',presets)
                button=control_factory.ButtonArchive.parse(record)
                self.assertEqual(button.metadata.properties.words[0],0)
                self.assertEqual(button.metadata.properties.words[16],0)
                self.assertTrue(button.picture)
                self.assertEqual(button.metadata.properties.picture,b'')

    def test_native_default_data_displays_write_both_names_without_donors(self):
        from mcs_window_archive import Reader, WindowArchive
        from 原生界面样式 import Array, CommonEnvelope
        from 原生趋势样式 import HistoryCurveStyle
        from 当前存盘浏览样式 import parse_record

        curve = {'type': 'history-curve', 'name': '独立历史曲线甲乙', 'bounds': [20, 30, 369, 211]}
        browse = {'type': 'saved-data-browser', 'name': '独立存盘浏览甲乙丙', 'bounds': [380, 52, 753, 265]}
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                data = project.create_data({'pages': [{'name': '独立显示', 'controls': [curve, browse]}]}, family)
                page, = data['WndUser']['rows']
                history, saved = WindowArchive.parse(project.f.archive(page['lbObjects'])).controls
                a, b = CommonEnvelope.parse(history), CommonEnvelope.parse(saved)
                for envelope, spec in ((a, curve), (b, browse)):
                    self.assertEqual(envelope.name.value, spec['name'])
                    self.assertEqual(envelope.rect, tuple(spec['bounds']))
                    self.assertFalse(envelope.animations)
                his = HistoryCurveStyle(a.content)
                self.assertEqual(his.curve_count, 16)
                self.assertEqual(Reader(his.fields()['4c']).cstring()[0], curve['name'])
                self.assertEqual(Array.parse(Reader(his.fields()['bindings']), True).items, [])
                browser = parse_record(saved)
                self.assertEqual(browser.metadata['native_name'], browse['name'])
                self.assertEqual(browser.metadata['native_field_list'], [])
                self.assertEqual(len(browser.metadata['columns']), 8)
                self.assertEqual(browser.values['m2a8'], (380, 52, 725, 237))
                self.assertEqual(browser.metadata['trailing_binding_present'], family == 'Stu')

    def test_saved_data_columns_share_the_style_transaction(self):
        from control_patch import edit
        from mcs_window_archive import write_cstring
        from 原生界面样式 import CommonEnvelope
        from 当前存盘浏览样式 import parse_record, saved_data_style

        combined = {'row_height': 38, 'saved_data_colors': {'grid': 0x123456},
                    'saved_data_fonts': {'header_font': {'height': 23, 'weight': 600, 'italic': True}},
                    'saved_data_columns': [{'index': 2, 'width': 175},
                                           {'index': 0, 'width': 95, 'title': '新字面列标题', 'alignment': 'right',
                                            'unit': 'kPa', 'display_format': '3|2'}]}
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                source = control_factory.primitive_record('saved-data-browser', project.load_factory_asset('primitives', family))
                before = parse_record(source)
                old = saved_data_style(source)
                old_parts = old['saved_data_time_parts']
                selected_parts = {part: not old_parts[part] for part in ('year', 'second', 'millisecond')}
                selected_filter = {'mode': 'fixed', 'order': 'descending',
                                   'fixed_period': 'previous_month', 'fixed_split_point': 24, 'recent_minutes': 45}
                changes = dict(combined, saved_data_time_parts=selected_parts, saved_data_time_filter=selected_filter)
                updated = edit(source, changes)
                self.assertEqual(updated.payload, control_factory.edit_control(source.type_id, source.payload, changes))
                result = saved_data_style(updated)
                self.assertEqual(result['saved_data_columns'][0],
                                 {'index': 0, 'width': 95, 'title': '新字面列标题', 'title_editable': True, 'alignment': 'right',
                                  'unit': 'kPa', 'unit_editable': True, 'display_format': '3|2',
                                  'data_name': old['saved_data_columns'][0]['data_name'], 'output_variable': ''})
                self.assertEqual(result['saved_data_columns'][2]['width'], 175)
                self.assertEqual(result['row_height'], 38)
                self.assertEqual(result['saved_data_colors']['grid'], 0x123456)
                self.assertEqual(result['saved_data_time_parts'], dict(old_parts, **selected_parts))
                self.assertEqual(result['saved_data_time_filter'], dict(old['saved_data_time_filter'], **selected_filter))
                after = parse_record(updated)
                self.assertEqual(after.metadata['columns'][1], before.metadata['columns'][1])
                self.assertEqual(after.values['m228_font'], before.values['m228_font'])
                old_column = old['saved_data_columns'][0]
                prior_fonts = old['saved_data_fonts']['header_font']
                new_fonts = result['saved_data_fonts']['header_font']
                self.assertEqual(new_fonts, [dict(face, height=23, height_raw=-23, weight=600, italic=True)
                                             for face in prior_fonts])
                original_font = {key: prior_fonts[0][key] for key in ('height', 'weight', 'italic')}
                reverse = {'row_height': old['row_height'], 'saved_data_colors': {'grid': old['saved_data_colors']['grid']},
                           'saved_data_fonts': {'header_font': original_font},
                           'saved_data_time_parts': {part: old_parts[part] for part in selected_parts},
                           'saved_data_time_filter': {key: old['saved_data_time_filter'][key] for key in selected_filter},
                           'saved_data_columns': [{'index': 0, 'width': 100, 'title': '第0列',
                                                   **{key: old_column[key] for key in ('alignment', 'unit', 'display_format')}},
                                                  {'index': 2, 'width': 100}]}
                self.assertEqual(edit(updated, reverse).to_bytes(), source.to_bytes())

                common = CommonEnvelope.parse(source)
                begin, end = before.metadata['column_spans'][0]['title']
                common.content = common.content[:begin] + write_cstring('\x0710042') + common.content[end:]
                translated = common.to_record()
                with self.assertRaisesRegex(ValueError, 'language entry'):
                    edit(translated, {'saved_data_columns': [{'index': 0, 'title': '字面替换'}]})
                resized = edit(translated, {'saved_data_columns': [{'index': 0, 'width': 92}]})
                self.assertEqual(saved_data_style(resized)['saved_data_columns'][0],
                                 dict(old_column, width=92, title='\x0710042', title_editable=False))
                with self.assertRaisesRegex(ValueError, 'decimal places'):
                    edit(source, {'saved_data_columns': [{'index': 0, 'display_format': '16|0'}]})
                with self.assertRaisesRegex(ValueError, 'unique slot'):
                    edit(source, {'saved_data_columns': [{'index': 0, 'width': 20}, {'index': 0, 'width': 19}]})
                with self.assertRaisesRegex(ValueError, 'known display checkboxes'):
                    edit(source, {'saved_data_time_parts': {'timezone': True}})
                with self.assertRaisesRegex(ValueError, 'requires a Boolean'):
                    edit(source, {'saved_data_time_parts': {'year': 1}})

                common = CommonEnvelope.parse(source)
                offset, end, _ = before.spans['time_year']
                common.content = common.content[:offset] + b'\x02\0\0\0' + common.content[end:]
                uncertain = common.to_record()
                self.assertIsNone(saved_data_style(uncertain)['saved_data_time_parts']['year'])
                other = edit(uncertain, {'saved_data_time_parts': {'second': selected_parts['second']}})
                self.assertEqual(CommonEnvelope.parse(other).content[offset:end], b'\x02\0\0\0')
                with self.assertRaisesRegex(ValueError, 'native checkbox state'):
                    edit(uncertain, {'saved_data_time_parts': {'year': False}})
                with self.assertRaisesRegex(ValueError, 'fixed split point'):
                    edit(source, {'saved_data_time_filter': {'mode':'fixed', 'fixed_period':'previous_week',
                                                             'fixed_split_point':8}})
                with self.assertRaisesRegex(ValueError, 'recent time'):
                    edit(source, {'saved_data_time_filter': {'mode':'recent', 'recent_minutes':-1}})

                query_filter = {'mode': 'variables', 'start_variable': 'FromTime', 'end_variable': 'ToTime'}
                variables = {'FromTime': {'kind':3}, 'ToTime': {'kind':3}, 'Clock': {'kind':2}}
                query = {'saved_data_time_filter': query_filter}
                by_name = edit(source, query, variables=variables)
                self.assertEqual(by_name.payload,
                                 control_factory.edit_control(source.type_id, source.payload, query, variables))
                self.assertEqual(saved_data_style(by_name)['saved_data_time_filter'],
                                 dict(old['saved_data_time_filter'], **query_filter))
                clear = {'mode':'all', 'start_variable':'', 'end_variable':''}
                self.assertEqual(edit(by_name, {'saved_data_time_filter': clear}).to_bytes(), source.to_bytes())
                with self.assertRaisesRegex(ValueError, 'existing string variable'):
                    edit(source, query)
                with self.assertRaisesRegex(ValueError, 'existing string variable'):
                    edit(source, {'saved_data_time_filter': dict(query_filter, end_variable='Clock')},
                         variables=variables)

                column = {'saved_data_columns': [{'index': 0, 'output_variable': 'Clock'}]}
                bound = edit(source, column, variables=variables)
                self.assertEqual(saved_data_style(bound)['saved_data_columns'][0]['output_variable'], 'Clock')
                compiled = CommonEnvelope.parse(bound)
                start, end = parse_record(bound).metadata['column_spans'][0]['compiled_output']
                compiled.content = compiled.content[:start] + bytes.fromhex('0200000009000000') + compiled.content[end:]
                waiting = compiled.to_record()
                self.assertEqual(edit(waiting, column, variables=variables).to_bytes(), waiting.to_bytes())
                remove = {'saved_data_columns': [{'index': 0, 'output_variable': ''}]}
                expected = CommonEnvelope.parse(source)
                start, end = before.metadata['column_spans'][0]['compiled_output']
                expected.content = expected.content[:start] + bytes.fromhex('00000000ffffffff') + expected.content[end:]
                self.assertEqual(edit(waiting, remove).to_bytes(), expected.to_record().to_bytes())
                with self.assertRaisesRegex(ValueError, 'existing scalar project variable'):
                    edit(source, column)
                with self.assertRaisesRegex(ValueError, 'field declared by the current native data source'):
                    edit(source, {'saved_data_columns': [{'index': 0, 'data_name': 'UnrelatedField'}]})

                native = CommonEnvelope.parse(source)
                fields = [('MCGS序号', 1), ('MCGS_Time', 10), ('Clock', 2)]
                field_list = b''.join(write_cstring(name) + kind.to_bytes(4, 'little') for name, kind in fields)
                native.content = native.content[:6] + len(fields).to_bytes(4, 'little') + field_list + native.content[10:]
                with_fields = native.to_record()
                group = {'kind': 0xffffffff, 'extension': b'\x01\0\0\0' + write_cstring('Clock')}
                selection = {'kind': 'group', 'group': 'NewCollection'}
                collect = {'saved_data_source': selection, 'saved_data_columns':[{'index': 0, 'data_name': 'Clock'}]}
                result = edit(with_fields, collect, variables=dict(variables, NewCollection=group))
                self.assertEqual(saved_data_style(result)['saved_data_source'], selection)
                self.assertEqual(saved_data_style(result)['saved_data_columns'][0]['data_name'], 'Clock')
                self.assertEqual(parse_record(result).metadata['native_field_list'], parse_record(with_fields).metadata['native_field_list'])
                with self.assertRaisesRegex(ValueError, 'same native column fields and types'):
                    group = dict(group, extension=b'\x01\0\0\0' + write_cstring('ToTime'))
                    edit(with_fields, collect, variables=dict(variables, NewCollection=group))

    def test_saved_data_system_sources_rebuild_fields_and_keep_compatible_columns(self):
        from control_patch import edit
        from 当前存盘浏览样式 import parse_record, saved_data_style

        sources = {
            'alarm_history': ('MCGS_ALARM', 'TIMES', (
                ('MCGS序号', 1), ('VALNAME', 3), ('TIMES', 10), ('TIMEE', 10), ('TIMEA', 10),
                ('ALARMTYPE', 1), ('VALUE', 2), ('STANDVALUE', 2), ('INFO', 3),
            )),
            'operation_log': ('MCGS_OPERATION_LOG', 'MCGS_Time', (
                ('MCGS序号', 1), ('MCGS_TIME', 10), ('MCGS_TIMEMS', 1),
                ('MCGS_LOG_USER_NAME', 3), ('MCGS_LOG_WND_NAME', 3), ('MCGS_LOG_OBJ_NAME', 3),
                ('MCGS_LOG_ACTION', 3), ('MCGS_LOG_INFO', 3),
            )),
        }
        variables = {'SelectedText': {'kind': 3}}
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                original = control_factory.primitive_record(
                    'saved-data-browser', project.load_factory_asset('primitives', family))
                alarm_plan = {'saved_data_source': {'kind': 'alarm_history'},
                              'saved_data_columns': [
                                  {'index': 0, 'data_name': 'VALNAME', 'title': '当前记录',
                                   'display_format': '0|1', 'output_variable': 'SelectedText'},
                                  {'index': 2, 'data_name': 'MCGS序号'},
                              ]}
                alarm = edit(original, alarm_plan, variables)
                self.assertEqual(alarm.payload,
                                 control_factory.edit_control(original.type_id, original.payload, alarm_plan, variables))
                with self.assertRaisesRegex(ValueError, 'explicit target field for column 0'):
                    edit(alarm, {'saved_data_source': {'kind': 'operation_log'}}, variables)
                log_plan = {'saved_data_source': {'kind': 'operation_log'},
                            'saved_data_columns': [{'index': 0, 'data_name': 'MCGS_LOG_INFO'}]}
                log = edit(alarm, log_plan, variables)
                for kind, record in (('alarm_history', alarm), ('operation_log', log)):
                    with self.subTest(kind=kind):
                        system_name, time_key, fields = sources[kind]
                        snapshot = saved_data_style(record)
                        self.assertEqual(snapshot['saved_data_source'], {'kind': kind, 'group': system_name})
                        self.assertEqual(snapshot['saved_data_fields'],
                                         [dict(name=name, native_type=word) for name, word in fields])
                        config = parse_record(record).metadata['native_config_member_map']
                        self.assertEqual([config[key]['value'] for key in ('1cc', '1d4')], [time_key, time_key])
                        self.assertEqual(snapshot['saved_data_columns'][2]['data_name'], 'MCGS序号')
                        self.assertEqual(snapshot['saved_data_columns'][0]['title'], '当前记录')
                        self.assertEqual(snapshot['saved_data_columns'][0]['display_format'], '0|1')
                        self.assertEqual(snapshot['saved_data_columns'][0]['output_variable'], 'SelectedText')
                        self.assertEqual(edit(record, {'saved_data_source': snapshot['saved_data_source']}).payload,
                                         record.payload)
                self.assertEqual(edit(log, {
                    'saved_data_source': {'kind': 'alarm_history'},
                    'saved_data_columns': [{'index': 0, 'data_name': 'VALNAME'}],
                }, variables).payload, alarm.payload)

                english = edit(original, {'saved_data_source': {'kind': 'operation_log', 'index_field': 'MCGSIndexID'},
                                          'saved_data_columns': [{'index': 0, 'data_name': 'MCGSIndexID'}]})
                self.assertEqual(saved_data_style(english)['saved_data_fields'][0],
                                 {'name': 'MCGSIndexID', 'native_type': 1})

    def test_failed_candidate_does_not_occupy_output(self):
        def fail(output, spec, source):
            output.write_bytes(b'partial')
            raise ValueError('readback failed')
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'project.mcs'
            with patch.object(project, '_build_candidate', fail), self.assertRaisesRegex(ValueError, 'readback failed'):
                project.write_project(output, {}, 'template.mcs')
            self.assertEqual(list(output.parent.iterdir()), [])

    @unittest.skipUnless(os.environ.get('MCGS_STU_FACTORY_FIXTURE'), 'requires original Stu template and ACE')
    def test_native_template_roundtrip(self):
        src = Path(os.environ['MCGS_STU_FACTORY_FIXTURE'])
        before = project.read(src)
        self.assertEqual(project.project_family(before), 'Stu')
        digest = project.sha(src)
        variables = [{'type': typ, 'name': name} for typ, name in
                     [('number', '试验数值'), ('boolean', '试验开关'), ('string', '试验字符')]]
        controls = []
        primitive_types = [typ for typ in control_factory.TYPES if typ not in control_factory.PLUGIN_PATHS]
        for typ in primitive_types:
            item = {'name': typ, 'type': typ, 'bounds': [10, 10, 110, 50]}
            if typ in control_factory.INPUT_TYPES:
                item['binding'] = '试验字符' if typ.startswith('character') else '试验数值'
            controls.append(item)
        page = {'id': 85, 'template_page_id': 2, 'name': '试验画面', 'controls': controls}
        spec = {'source_sha256': digest, 'add_variables': variables, 'add_pages': [page]}
        with tempfile.TemporaryDirectory() as folder:
            candidate = Path(folder) / 'created.mcs'
            receipt = project.write_project(candidate, spec, src)
            self.assertEqual(receipt['tables_checked'], len(before))
            after = project.read(candidate)
            self.assertEqual(project.sha(src), digest)
            self.assertEqual(before['WndUser']['rows'], [r for r in after['WndUser']['rows'] if r['iID'] != 85])
            unchanged = set(before) - {'System', 'WndUser'}
            self.assertEqual(project.canonical({k: before[k] for k in unchanged}),
                             project.canonical({k: after[k] for k in unchanged}))
            def unpack(data):
                return project.f.archive(project.system(data, 'ObjData')['lbContext'])
            original, updated = unpack(before), unpack(after)
            self.assertEqual(updated[12:12 + len(original) - 12], original[12:])
            self.assertEqual(original[:4], updated[:4])
            obj = next(r for r in after['WndUser']['rows'] if r['iID'] == 85)
            _, records, _ = project.f.window(project.f.archive(obj['lbObjects']))
            self.assertEqual([project.f.common(payload)['name'] for _, payload in records], primitive_types)
            for typ, (kind, payload) in zip(primitive_types, records):
                if typ in control_factory.INPUT_TYPES:
                    item = control_factory.InputRecord.parse(control_factory.record(kind, payload))
                    self.assertEqual(item.variable, '试验字符' if typ.startswith('character') else '试验数值')
            var_spec = {'source_sha256': project.sha(candidate), 'variables': [{'name': '试验数值', 'initial': '42'}]}
            second = Path(folder) / 'edited.mcs'
            project.write_project(second, var_spec, candidate)
            self.assertEqual(project.VariableCatalog(project.read(second))['试验数值']['initial'], '42')


if __name__ == '__main__':
    unittest.main()
