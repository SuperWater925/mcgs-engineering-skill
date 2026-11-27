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
    def test_default_alarm_table_uses_original_family_core_and_keeps_explicit_clone(self):
        import hashlib
        from mcs_plugin_controls import PluginControl
        from mcs_window_archive import WindowArchive
        from 原生界面样式 import CommonEnvelope

        expected = {
            'Pro': (0x55b1b, '376598c927b1c91275222f3dbcc736064b4056e1fc103a8e330601a8886c43f8'),
            'Stu': (0x55b36, 'a58b578ee63493afad274b0088809fac7baf8ea9f1fbf6750744b3ab4c481367'),
        }
        control = {'type': 'alarm-table', 'name': '报警浏览', 'bounds': [10, 20, 310, 150]}
        for family, (schema, digest) in expected.items():
            with self.subTest(family=family):
                data = project.create_data({'pages': [{'name': '报警页', 'controls': [control]}]}, family)
                raw = project.f.archive(data['WndUser']['rows'][0]['lbObjects'])
                original, = WindowArchive.parse(raw).controls
                common = CommonEnvelope.parse(original)
                plugin = PluginControl.parse(common.project_without_animations())
                self.assertEqual((original.type_id, common.name.value, common.rect),
                                 (0x503d, control['name'], tuple(control['bounds'])))
                self.assertEqual(common.animations, [])
                self.assertEqual(plugin.path, control_factory.PLUGIN_PATHS['alarm-table'])
                self.assertEqual((int.from_bytes(plugin.core[16:20], 'little'), hashlib.sha256(plugin.core).hexdigest()),
                                 (schema, digest))

                clone = {**control, 'name': '复制报警浏览', 'bounds': [35, 42, 436, 190],
                         'clone_from': {'page_id': 1, 'path': [0], 'name': control['name'], 'kind': '0x503d',
                                        'sha256': hashlib.sha256(original.payload).hexdigest()}}
                updated = project.edit_data(data, {'pages': [{'id': 1, 'add_controls': [clone]}]})
                raw = project.f.archive(updated['WndUser']['rows'][0]['lbObjects'])
                first, duplicate = WindowArchive.parse(raw).controls
                self.assertEqual(first.to_bytes(), original.to_bytes())
                copied = CommonEnvelope.parse(duplicate)
                self.assertEqual((copied.name.value, copied.rect), (clone['name'], tuple(clone['bounds'])))
                self.assertEqual(PluginControl.parse(copied.project_without_animations()).core, plugin.core)

                primitives = project.load_factory_asset('primitives', family)
                with self.assertRaisesRegex(ValueError, 'only type, name and bounds'):
                    control_factory.make_control({**control, 'row_height': 30}, {}, primitives)

    def test_vendor_default_recipe_and_xy_keep_unbound_native_core(self):
        import hashlib
        from mcs_plugin_controls import PluginControl, RecipeCore, XYCore
        from mcs_window_archive import WindowArchive
        from 原生界面样式 import CommonEnvelope

        expected = {
            'Stu': {
                'recipe-table': '3e60d8baae2091b6041b1dcba67ea1f7d58462a8c64febe5237766cb488102e9',
                'xy-curve': '4b2a6fc114505ff7989d9707de44dad015c504af3967f0699cb3473aa65ef724',
            },
            'Pro': {
                'recipe-table': 'a97dfc3c7a44ff6cc1b7b78fbea5dca0e6f1ba5a20180211a8a2be8741af3410',
                'xy-curve': '77bbbacb99a54ac47036d1df5a9c2fe29b256c6b1ea773696b920b0a4a28651b',
            },
        }
        specifications = [
            {'type': 'recipe-table', 'name': 'AuditRecipe', 'bounds': [26, 20, 176, 150]},
            {'type': 'xy-curve', 'name': 'AuditXY', 'bounds': [185, 20, 360, 150]},
        ]
        for family, native_digests in expected.items():
            with self.subTest(family=family):
                data = project.create_data({'pages': [{'name': 'AuditPlugins', 'controls': specifications}]}, family)
                raw = project.f.archive(data['WndUser']['rows'][0]['lbObjects'])
                controls = WindowArchive.parse(raw).controls
                for spec, saved in zip(specifications, controls, strict=True):
                    common = CommonEnvelope.parse(saved)
                    plugin = PluginControl.parse(common.project_without_animations())
                    self.assertEqual(saved.type_id, 0x503d)
                    self.assertEqual((common.name.value, common.rect, common.animations),
                                     (spec['name'], tuple(spec['bounds']), []))
                    self.assertEqual(plugin.path, control_factory.PLUGIN_PATHS[spec['type']])
                    self.assertEqual(hashlib.sha256(plugin.core).hexdigest(), native_digests[spec['type']])
                    if spec['type'] == 'recipe-table':
                        core = RecipeCore.parse(plugin.core)
                        self.assertEqual((core.group, core.columns, core.fields['visible_expression']), ('', [], ''))
                    else:
                        core = XYCore.parse(plugin.core)
                        self.assertEqual(len(core.curves), 8)
                        self.assertFalse(core.fields['m108'] or core.tail['visible_cache'])

                recipe, xy = controls
                clone = {**specifications[1], 'name': 'ClonedXY', 'bounds': [20, 160, 180, 300],
                         'clone_from': {'page_id': 1, 'path': [1], 'name': 'AuditXY', 'kind': '0x503d',
                                        'sha256': hashlib.sha256(xy.payload).hexdigest()}}
                updated = project.edit_data(data, {'pages': [{'id': 1, 'add_controls': [clone]}]})
                raw = project.f.archive(updated['WndUser']['rows'][0]['lbObjects'])
                first, second, copied = WindowArchive.parse(raw).controls
                self.assertEqual((first.payload, second.payload), (recipe.payload, xy.payload))
                copied = CommonEnvelope.parse(copied)
                self.assertEqual(copied.name.value, clone['name'])
                self.assertEqual(hashlib.sha256(PluginControl.parse(copied.project_without_animations()).core).hexdigest(),
                                 native_digests['xy-curve'])
                primitives = project.load_factory_asset('primitives', family)
                with self.assertRaisesRegex(ValueError, 'only type, name and bounds'):
                    control_factory.make_control({**specifications[0], 'row_height': 32}, {}, primitives)

    def test_new_embedded_bitmap_and_existing_bitmap_clone_use_native_geometry(self):
        import hashlib
        from test_state_resources import raster
        from mcs_window_archive import WindowArchive
        from picture_resources import Picture
        from 原生界面样式 import CommonEnvelope

        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                image = raster()
                bounds = [10, 20, 42, 62]
                data = project.create_data({'pages': [{'name': 'EmbeddedSource', 'controls': [
                    {'type': 'bitmap', 'name': 'EmbeddedImage', 'bounds': bounds,
                     'bitmap_picture': {'embedded_hex': image.hex()}},
                ]}]}, family)
                original = WindowArchive.parse(project.f.archive(data['WndUser']['rows'][0]['lbObjects'])).controls[0]
                common = CommonEnvelope.parse(original)
                picture = Picture.parse(common.content)
                self.assertEqual((original.type_id, common.name.value, common.rect), (0x5009, 'EmbeddedImage', tuple(bounds)))
                self.assertEqual((picture.mode, picture.width, picture.height, picture.payload), (2, 2, 3, image))
                clone = {'type': 'bitmap', 'name': 'EmbeddedClone', 'bounds': [10, 72, 42, 122],
                         'clone_from': {'page_id': 1, 'path': [0], 'name': 'EmbeddedImage',
                                        'kind': '0x5009', 'sha256': hashlib.sha256(original.payload).hexdigest()}}
                updated = project.edit_data(data, {'pages': [{'id': 1, 'add_controls': [clone]}]})
                records = WindowArchive.parse(project.f.archive(updated['WndUser']['rows'][0]['lbObjects'])).controls
                self.assertEqual(records[0].to_bytes(), original.to_bytes())
                duplicate = CommonEnvelope.parse(records[1])
                self.assertEqual((duplicate.name.value, duplicate.rect, duplicate.content),
                                 ('EmbeddedClone', tuple(clone['bounds']), common.content))

    def test_saved_data_column_layout_clones_drops_and_reorders_complete_existing_rows(self):
        from control_patch import edit
        from 原生界面样式 import CommonEnvelope
        from 当前存盘浏览样式 import parse_record, saved_data_style

        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                record = control_factory.primitive_record('saved-data-browser', project.load_factory_asset('primitives', family))
                before = parse_record(record)
                spec = {'saved_data_column_layout': [3, {'clone_index': 2}, 1],
                        'saved_data_columns': [{'index': 1, 'title': 'New column', 'width': 144}]}
                changed = edit(record, spec)
                after = parse_record(changed)
                columns = saved_data_style(changed)['saved_data_columns']
                self.assertEqual(len(columns), 3)
                self.assertEqual((columns[1]['title'], columns[1]['width']), ('New column', 144))
                self.assertEqual(after.metadata['columns'][0], before.metadata['columns'][3])
                self.assertEqual(after.metadata['columns'][2], before.metadata['columns'][1])
                before_content, after_content = (CommonEnvelope.parse(item).content for item in (record, changed))
                self.assertEqual(before_content[before.metadata['column_end_offset']:],
                                 after_content[after.metadata['column_end_offset']:])
                with self.assertRaisesRegex(ValueError, 'clone_index'):
                    edit(record, {'saved_data_column_layout': [0, 0]})
                bound = edit(record, {'saved_data_columns': [{'index': 0, 'output_variable': 'Result'}]},
                             {'Result': {'kind': 2}})
                with self.assertRaisesRegex(ValueError, 'without an output binding'):
                    edit(bound, {'saved_data_column_layout': [{'clone_index': 0}, 1]})

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
                with self.assertRaisesRegex(ValueError, 'full native member boundary'):
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

    def test_saved_data_alarm_secondary_time_formats_use_final_column_fields(self):
        from control_patch import edit
        from 当前存盘浏览样式 import saved_data_style

        date = 'yyyy-MM-dd hh:mm:ss'
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                original = control_factory.primitive_record(
                    'saved-data-browser', project.load_factory_asset('primitives', family))
                alarm = edit(original, {'saved_data_source': {'kind': 'alarm_history'},
                                        'saved_data_columns': [
                                            {'index': 1, 'data_name': 'TIMEE', 'display_format': date},
                                            {'index': 0, 'data_name': 'TIMES'},
                                            {'index': 2, 'data_name': 'TIMEA', 'display_format': 'yyyy-MM-dd hh-mm-ss'},
                                            {'index': 3, 'data_name': 'VALUE', 'display_format': '0|0'},
                                        ]})
                settings = saved_data_style(alarm)
                self.assertEqual(settings['saved_data_source']['group'], 'MCGS_ALARM')
                columns = settings['saved_data_columns']
                self.assertEqual([(row['data_name'], row['display_format']) for row in columns[1:4]],
                                 [('TIMEE', date), ('TIMEA', 'yyyy-MM-dd hh-mm-ss'), ('VALUE', '0|0')])
                self.assertEqual(columns[0]['display_format'],
                                 saved_data_style(original)['saved_data_columns'][0]['display_format'])
                self.assertEqual(columns[4:], saved_data_style(original)['saved_data_columns'][4:])

                for legacy in ('0|0', ''):
                    result = saved_data_style(edit(alarm, {'saved_data_columns': [
                        {'index': 1, 'display_format': legacy}]}))
                    self.assertEqual(result['saved_data_columns'][1]['display_format'], legacy)
                for arbitrary in ('yyyy hh whatever', 'foo|bar'):
                    with self.assertRaisesRegex(ValueError, 'alarm date format'):
                        edit(alarm, {'saved_data_columns': [{'index': 1, 'display_format': arbitrary}]})

                with self.assertRaisesRegex(ValueError, 'two values separated'):
                    edit(alarm, {'saved_data_columns': [
                        {'index': 0, 'data_name': ''}, {'index': 1, 'display_format': 'yyyy-MM-dd hh-mm-ss'}]})
                with self.assertRaisesRegex(ValueError, 'two values separated'):
                    edit(alarm, {'saved_data_columns': [
                        {'index': 2, 'data_name': 'VALUE', 'display_format': date}]})
                with self.assertRaisesRegex(ValueError, 'two values separated'):
                    edit(original, {'saved_data_source': {'kind': 'operation_log'}, 'saved_data_columns': [
                        {'index': 0, 'data_name': 'MCGS_TIME', 'display_format': date}]})

    def test_saved_data_groups_rebuild_in_native_member_order_after_system_sources(self):
        from control_patch import edit
        from mcs_window_archive import write_cstring
        from 当前存盘浏览样式 import parse_record, saved_data_style

        neutral_tail = bytes(8) + write_cstring('')
        variables = {'Material': {'kind': 3, 'id': 32}, 'Pressure': {'kind': 2, 'id': 48},
                     'Result': {'kind': 1, 'id': 61}, 'SelectedText': {'kind': 3, 'id': 72}}
        variables['OrderedGroup'] = {
            'kind': 0xffffffff,
            'extension': b'\x02\x00\x00\x00' + write_cstring('Pressure') + write_cstring('Material') + neutral_tail,
        }
        variables['AnotherGroup'] = {
            'kind': 0xffffffff,
            'extension': b'\x02\x00\x00\x00\x3d\x00\x00\x00\x20\x00\x00\x00' + neutral_tail,
        }
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                original = control_factory.primitive_record(
                    'saved-data-browser', project.load_factory_asset('primitives', family))
                alarm = edit(original, {
                    'saved_data_source': {'kind': 'alarm_history', 'index_field': 'MCGSIndexID'},
                    'saved_data_columns': [
                        {'index': 0, 'data_name': 'VALNAME', 'title': '记录', 'output_variable': 'SelectedText'},
                        {'index': 1, 'data_name': 'VALUE'}, {'index': 2, 'data_name': 'MCGSIndexID'},
                    ],
                }, variables)
                first_target = {'kind': 'group', 'group': 'OrderedGroup'}
                with self.assertRaisesRegex(ValueError, 'explicit target field for column 0'):
                    edit(alarm, {'saved_data_source': first_target}, variables)

                first = edit(alarm, {'saved_data_source': first_target, 'saved_data_columns': [
                    {'index': 0, 'data_name': 'Material'}, {'index': 1, 'data_name': 'Pressure'},
                ]}, variables)
                second_target = {'kind': 'group', 'group': 'AnotherGroup'}
                second = edit(first, {'saved_data_source': second_target,
                                      'saved_data_columns': [{'index': 1, 'data_name': ''}]}, variables)
                for record, target, membership, columns in [
                    (first, first_target, [('Pressure', 2), ('Material', 3)],
                     ['Material', 'Pressure', 'MCGSIndexID']),
                    (second, second_target, [('Result', 1), ('Material', 3)],
                     ['Material', '', 'MCGSIndexID']),
                ]:
                    native = parse_record(record)
                    snapshot = saved_data_style(record)
                    self.assertEqual(snapshot['saved_data_source'], target)
                    self.assertEqual(snapshot['saved_data_fields'], [
                        {'name': name, 'native_type': word} for name, word in
                        [('MCGSIndexID', 1), ('MCGS_Time', 10), *membership]])
                    self.assertEqual([column['data_name'] for column in snapshot['saved_data_columns'][:3]], columns)
                    self.assertEqual(len(snapshot['saved_data_columns']), 8)
                    self.assertEqual(snapshot['saved_data_columns'][0]['title'], '记录')
                    self.assertEqual(snapshot['saved_data_columns'][0]['output_variable'], 'SelectedText')
                    self.assertTrue(all(native.metadata['native_config_member_map'][key]['value'] == 'MCGS_Time'
                                        for key in ('1cc', '1d4')))
                    self.assertEqual(edit(record, {'saved_data_source': target}).payload, record.payload)

    def test_shared_controls_source_switch_reads_the_actual_project_variables(self):
        import copy
        import hashlib
        import struct
        from mcs_window_archive import WindowArchive
        from native_tool import BatchExport, ProjectBatchSource, controls_patch, unwrapped
        from 当前存盘浏览样式 import saved_data_style

        for family in ('Stu', 'Pro'):
            with self.subTest(family=family), tempfile.TemporaryDirectory() as folder:
                data = project.create_data({
                    'variables': [{'name': 'ProcessValue', 'type': 'number'},
                                  {'name': 'ResultValue', 'type': 'number'},
                                  {'name': 'StartTime', 'type': 'string'},
                                  {'name': 'EndTime', 'type': 'string'},
                                  {'name': 'ProcessGroup', 'type': 'group'}],
                    'pages': [{'name': 'Readback', 'controls': [
                        {'type': 'saved-data-browser', 'name': 'History', 'bounds': [0, 0, 180, 90]},
                        {'type': 'label', 'name': 'Keep', 'bounds': [0, 90, 100, 120]},
                    ]}],
                }, family)
                catalog = project.system(data, 'ObjData')
                rows = project.f.variables(project.f.archive(catalog['lbContext']))
                group, = [row for row in rows if row['name'] == 'ProcessGroup']
                group['extension'] = struct.pack('<I', 1) + project.f.text('ProcessValue') + group['extension'][4:]
                catalog['lbContext'] = project.f.wrap_like(catalog['lbContext'], project.f.pack_variables(rows))

                def page(current):
                    return WindowArchive.parse(project.f.archive(current['WndUser']['rows'][0]['lbObjects']))

                def edit_page(current, edits):
                    record = page(current).controls[0]
                    return project.edit_data(copy.deepcopy(current), {'pages': [{'id': 1, 'controls': [{
                        'name': 'History', 'sha256': hashlib.sha256(record.payload).hexdigest(), 'edits': edits,
                    }]}]})

                system_source = edit_page(data, {'saved_data_source': {'kind': 'alarm_history'},
                                                 'saved_data_columns': [{'index': 0, 'data_name': 'VALUE'}]})
                edits = {'saved_data_source': {'kind': 'group', 'group': 'ProcessGroup'},
                         'saved_data_time_filter': {'mode': 'variables', 'start_variable': 'StartTime',
                                                    'end_variable': 'EndTime'},
                         'saved_data_columns': [{'index': 0, 'data_name': 'ProcessValue',
                                                 'output_variable': 'ResultValue'}]}
                before = page(system_source)
                expected = page(edit_page(system_source, edits))
                baseline = '0' * 64
                export = BatchExport(ProjectBatchSource(system_source, baseline, family))
                spec = {'input_sha256': baseline, 'controls': [{
                    'window': 1, 'path': [0], 'sha256': hashlib.sha256(before.controls[0].payload).hexdigest(),
                    'edits': edits,
                }]}
                output = Path(folder) / 'controls'
                controls_patch(export, spec, output)
                candidate = WindowArchive.parse(unwrapped((output / 'window-1.bin').read_bytes()))
                self.assertEqual(candidate.to_bytes(), expected.to_bytes())
                self.assertEqual(candidate.controls[1].to_bytes(), before.controls[1].to_bytes())
                actual = saved_data_style(candidate.controls[0])
                self.assertEqual(actual['saved_data_source'], edits['saved_data_source'])
                self.assertEqual(actual['saved_data_columns'][0]['output_variable'], 'ResultValue')
                self.assertEqual(actual['saved_data_time_filter']['end_variable'], 'EndTime')

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
        from test_state_resources import raster

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
            if typ == 'bitmap':
                item['bitmap_picture'] = {'embedded_hex': raster().hex()}
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
