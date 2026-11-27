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
    def test_variable_array_uses_original_naming_and_existing_scalar_layout(self):
        for family in ("Stu", "Pro"):
            with self.subTest(family=family):
                created = m.create_data({"pages": [{"name": "Main"}], "variable_arrays": [{
                    "name_template": "Hex{R}Copy{R}", "type": "number", "start": 10,
                    "step": 3, "number_mode": 1, "zero_padding_width": 2, "count": 3,
                    "initials": ["1.25", "-2.5", "0"],
                }]}, family)
                catalog = m.VariableCatalog(created)
                self.assertEqual([catalog[name]["initial"] for name in ("Hex0aCopy0a", "Hex0dCopy0d", "Hex10Copy10")],
                                 ["1.25", "-2.5", "0"])
                before = m.canonical(created)
                edit = {"variable_arrays": [
                    {"name_template": "Oct", "type": "boolean", "start": 7, "step": 2, "number_mode": 2,
                     "count": 2, "initial": 1},
                    {"name_template": "ExactName", "type": "string", "count": 1, "start": 7, "initial": "测试"},
                ]}
                edited = m.edit_data(copy.deepcopy(created), edit)
                rows = m.VariableCatalog(edited)
                checks = {"Oct7": "1", "Oct11": "1", "ExactName": "测试"}
                self.assertEqual({name: rows[name]["initial"] for name in checks}, checks)
                removal = [{"id": rows[name]["id"], "name": name} for name in checks]
                self.assertEqual(m.canonical(m.edit_data(edited, {"delete_variables": removal})), before)
                with self.assertRaisesRegex(ValueError, "Duplicate variable"):
                    m.edit_data(copy.deepcopy(created), {"variable_arrays": [{
                        "name_template": "hex0ACopy0a", "type": "number", "count": 1}]})
                for change in ({"count": True}, {"start": 2147483647}, {"initials": ["0"]}):
                    bad = {"name_template": "Example{R}", "count": 3, "type": "number", **change}
                    with self.assertRaises(ValueError):
                        m.edit_data(copy.deepcopy(created), {"variable_arrays": [bad]})

    def test_native_pro_window_click_and_common_slot_share_the_same_framed_trailer(self):
        from mcs_window_archive import WindowArchive, WindowSettings
        from 窗口事件归档 import 窗口事件, 读取公共窗口槽

        # Pro's native page dispatch frame has a compiled event and a separate Title ID after it.
        extension = bytes.fromhex(
            '8a000100ffff00000e00434576656e74446973706174636818000000000000000000000000001101000000473edb'
            '0000000100000000000012000000fffeff0543006c00690063006b0000000000fffeff00ffffffff'
            'fffeff1741007500640069007400500061006700650043006c00690063006b00560061006c007500650020003d00200031000000000006000300000000000000')
        data = project('Pro')
        row = data['WndUser']['rows'][1]
        original = WindowArchive.parse(m.f.archive(row['lbObjects']))
        settings = WindowSettings.parse(original.trailer)
        body = 窗口事件.解析(settings.event_tail)
        body.扩展 = extension
        settings.event_tail = body.序列化()
        original.trailer = settings.to_bytes()
        row['lbObjects'] = m.f.wrap_like(row['lbObjects'], original.to_bytes())
        row['iCompileFlag'] = 1
        inspected = m.inspect_data(data)['pages'][1]
        click = inspected['click_event_source']
        self.assertEqual((click['event_type_id'], click['event_id'], click['compiled_size']), (18, 0, 24))
        self.assertEqual(inspected['common_page'], {'id': 3, 'name': 'SparePage'})
        before = {key: click[key] for key in ('event_type_id', 'event_id', 'name', 'sha256')}
        pending = []
        step = {'id': row['iID'], 'events': {'click_event_source': dict(before, source='UnboundScalar = 14')},
                'common_page': {'owner_name': row['strName'], 'source': inspected['common_page'],
                                'target': {'id': 1, 'name': 'StartupPage'}}}
        updated = m.edit_data(copy.deepcopy(data), {'pages': [step]}, pending_event_generation=pending)
        self.assertEqual(pending, [{'page_id': 2, 'page_name': 'AuxiliaryPage', 'owner': 'window',
                                    'operation': 'click_event_source', 'event_type_id': 18, 'event_id': 0,
                                    'event_name': 'Click', 'required_action': 'reference-sync'}])
        target = m.inspect_data(updated)['pages'][1]
        self.assertEqual(target['click_event_source']['source'], 'UnboundScalar = 14')
        self.assertEqual(target['click_event_source']['compiled_size'], 0)
        self.assertEqual(target['common_page'], {'id': 1, 'name': 'StartupPage'})
        self.assertEqual(updated['WndUser']['rows'][1]['iCompileFlag'], 0)
        after = WindowArchive.parse(m.f.archive(updated['WndUser']['rows'][1]['lbObjects']))
        after_settings = WindowSettings.parse(after.trailer)
        after_body = 窗口事件.解析(after_settings.event_tail)
        self.assertEqual(读取公共窗口槽(after_settings.event_tail), (1,))
        after_body.扩展 = extension
        after_settings.event_tail = after_body.序列化()
        after.trailer = after_settings.to_bytes()
        self.assertEqual(after.to_bytes(), original.to_bytes())

        with self.assertRaisesRegex(ValueError, 'event preimage differs'):
            m.edit_data(copy.deepcopy(updated), {'pages': [{'id': 2, 'events': step['events']}]})
        with self.assertRaisesRegex(ValueError, 'Referenced'):
            m.edit_data(copy.deepcopy(data), {'delete_pages': [{'id': 3, 'name': 'SparePage'}]})
        fresh = m.edit_data(copy.deepcopy(data), {'add_pages': [{'template_page_id': 2, 'name': 'Fresh'}]})
        fresh_page = m.inspect_data(fresh)['pages'][-1]
        self.assertNotIn('click_event_source', fresh_page)
        self.assertEqual(fresh_page['common_page'], inspected['common_page'])

    def test_native_pro_window_click_add_remove_and_private_framing(self):
        data = project('Pro')
        source = 'UnboundScalar = 23'
        pending = []
        event_spec = {'add_click_event_source': source}
        created = m.edit_data(copy.deepcopy(data), {'pages': [{'id': 2, 'events': event_spec}]},
                              pending_event_generation=pending)
        self.assertEqual(pending[0]['operation'], 'add_click_event_source')
        clicks = m.inspect_data(created)['pages'][1]['click_event_source']
        self.assertEqual((clicks['source'], clicks['compiled_size']), (source, 0))
        identity = {key: clicks[key] for key in ('event_type_id', 'event_id', 'name', 'sha256')}
        pending.clear()
        deleted = m.edit_data(copy.deepcopy(created), {'pages': [{'id': 2, 'events': {'delete_click_event': identity}}]},
                              pending_event_generation=pending)
        self.assertEqual(deleted, data)
        self.assertEqual(pending[0]['operation'], 'delete_click_event')
        with self.assertRaisesRegex(ValueError, 'dispatch list'):
            m.edit_data(copy.deepcopy(created), {'pages': [{'id': 2, 'events': event_spec}]})

    def test_native_stu_window_click_preserves_the_three_public_window_slots(self):
        from mcs_button_control import ByteArray
        from mcs_window_archive import Reader, WindowArchive, WindowSettings
        from 窗口事件归档 import 窗口事件
        from 原生界面样式 import EventDispatch, GenericMetadata

        # CEventDispatch saved by Stu on AuditMain with the local script AuditSample = 17.
        native_click = bytes.fromhex(
            'ffff00000e00434576656e74446973706174636818000000000000000000000000001111000000473e'
            '060000000100000000000012000000fffeff0543006c00690063006b0000000000fffeff00ffffffff'
            'fffeff1041007500640069007400530061006d0070006c00650020003d002000310037000000')
        page_id = 2
        page_name = 'AuxiliaryPage'
        data = m.edit_data(project('Stu'), {'pages': [{'id': page_id, 'events': {
            'open': 'UnboundScalar = 2', 'cycle': 'UnboundScalar = 3', 'close': 'UnboundScalar = 4',
            'period_ms': 375,
        }}]})
        common = {'id': 1, 'name': 'StartupPage'}
        link = {'owner_name': page_name, 'layer': 'middle', 'source': None, 'target': common}
        baseline = m.edit_data(copy.deepcopy(data), {'pages': [{'id': page_id, 'common_page': link}]})
        row = baseline['WndUser']['rows'][1]
        original = WindowArchive.parse(m.f.archive(row['lbObjects']))
        settings = WindowSettings.parse(original.trailer)
        body = 窗口事件.解析(settings.event_tail)
        wire = Reader(body.扩展)
        dispatch = ByteArray.parse(wire)
        suffix = body.扩展[wire.pos:]
        dispatch.value = b'\x01\x00' + native_click + bytes(2)
        body.扩展 = dispatch.to_bytes() + suffix
        settings.event_tail = body.序列化()
        original.trailer = settings.to_bytes()
        native = copy.deepcopy(baseline)
        native_row = native['WndUser']['rows'][1]
        native_row['lbObjects'] = m.f.wrap_like(native_row['lbObjects'], original.to_bytes())
        native_row['iCompileFlag'] = 1
        page = m.inspect_data(native)['pages'][1]
        click = page['click_event_source']
        layers = {'bottom': None, 'middle': common, 'top': None}
        self.assertEqual(page['common_page_layers'], layers)
        self.assertEqual((click['source'], click['compiled_size']), ('AuditSample = 17', 24))
        identity = {key: click[key] for key in ('event_type_id', 'event_id', 'name', 'sha256')}

        pending = []
        change = {'id': page_id, 'events': {'click_event_source': dict(identity, source='UnboundScalar = 14')}}
        updated = m.edit_data(copy.deepcopy(native), {'pages': [change]}, pending_event_generation=pending)
        self.assertEqual(pending[0]['required_action'], 'page-native-generate')
        self.assertEqual(updated['WndUser']['rows'][1]['iCompileFlag'], 0)
        page = m.inspect_data(updated)['pages'][1]
        self.assertEqual(page['common_page_layers'], layers)
        click = page['click_event_source']
        self.assertEqual((click['source'], click['compiled_size']), ('UnboundScalar = 14', 0))
        with self.assertRaisesRegex(ValueError, 'event preimage differs'):
            m.edit_data(copy.deepcopy(updated), {'pages': [change]})

        identity = {key: click[key] for key in ('event_type_id', 'event_id', 'name', 'sha256')}
        removal = {'id': page_id, 'events': {'delete_click_event': identity}}
        self.assertEqual(m.edit_data(copy.deepcopy(updated), {'pages': [removal]}), baseline)
        add = {'id': page_id, 'common_page': link, 'events': {'add_click_event_source': 'UnboundScalar = 14'}}
        self.assertEqual(m.edit_data(data, {'pages': [add]}), updated)

        fresh = m.edit_data(copy.deepcopy(native), {'add_pages': [{'template_page_id': page_id, 'name': 'FreshStu'}]})
        page = m.inspect_data(fresh)['pages'][-1]
        self.assertEqual(page['common_page_layers'], layers)
        self.assertNotIn('click_event_source', page)

        event = EventDispatch.parse(Reader(native_click))
        event.event_id = 19
        metadata = GenericMetadata.parse(dispatch.value)
        metadata.events = [event]
        dispatch.value = metadata.to_bytes()
        body.扩展 = dispatch.to_bytes() + suffix
        settings.event_tail = body.序列化()
        original.trailer = settings.to_bytes()
        native_row['lbObjects'] = m.f.wrap_like(native_row['lbObjects'], original.to_bytes())
        with self.assertRaisesRegex(ValueError, 'Expected one unparameterized'):
            m.edit_data(copy.deepcopy(native), {'pages': [change]})
        with self.assertRaisesRegex(ValueError, 'Expected one unparameterized'):
            m.edit_data(copy.deepcopy(native), {'add_pages': [{'template_page_id': page_id, 'name': 'FreshStu'}]})
        dispatch.value = b'\x01\x00' + native_click + bytes(2)
        body.扩展 = dispatch.to_bytes() + suffix
        settings.event_tail = body.序列化()
        settings.password_data = b'opaque-test-envelope'
        original.trailer = settings.to_bytes()
        native_row['lbObjects'] = m.f.wrap_like(native_row['lbObjects'], original.to_bytes())
        with self.assertRaisesRegex(ValueError, 'unprotected window settings'):
            m.edit_data(copy.deepcopy(native), {'pages': [change]})
        with self.assertRaisesRegex(ValueError, 'unprotected window settings'):
            m.edit_data(copy.deepcopy(native), {'add_pages': [{'template_page_id': page_id, 'name': 'FreshStu'}]})

    def test_native_window_mouse_down_preserves_argument_arrays_and_shared_click_declaration(self):
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                self._verify_native_window_mouse_down(family)

    def _verify_native_window_mouse_down(self, family):
        from mcs_button_control import ByteArray
        from mcs_window_archive import Reader, WindowArchive
        from 窗口事件归档 import 窗口事件, 读取页面Click, 读取页面MouseDown
        from 原生界面样式 import GenericMetadata

        # Exact Stu CEventDispatch collection saved on AuditMain. MouseDown reuses the Click class tag.
        native_dispatch = bytes.fromhex(
            '0200ffff00000e00434576656e74446973706174636818000000000000000000000000001111000000473e060000000100000000000012'
            '000000fffeff0543006c00690063006b0000000000fffeff00fffffffffffeff1041007500640069007400530061006d0070006c006500'
            '20003d0020003100370000000180170000000000040000000000000026060000003e04000000010400fffeff0b410075006400690074'
            '00530061006d0070006c006500fffeff00fffeff00fffeff00040006000000ffffffffffffffffffffffff0400020000000000000000'
            '0000000000000012000000fffeff094d006f0075007300650044006f0077006e0003000000fffeff00fffffffffffeff174100750064006900'
            '74005400690063006b0020003d00200041007500640069007400530061006d0070006c00650000000000')
        if family == 'Pro':
            # Original Pro ordered records match Stu except byte 130 of the compiled MouseDown cache.
            self.assertEqual(native_dispatch[130], 4)
            native_dispatch = native_dispatch[:130] + bytes(1) + native_dispatch[131:]
        data = m.edit_data(project(family), {'add_variables': [
            {'name': 'AuditTick', 'type': 'number'}, {'name': 'AuditSample', 'type': 'number'}]})
        self.assertEqual(m.VariableCatalog(data)['AuditSample']['id'], 6)
        row = data['WndUser']['rows'][0]
        original = WindowArchive.parse(m.f.archive(row['lbObjects']))
        settings = original.settings()
        body = 窗口事件.解析(settings.event_tail)
        wire = Reader(body.扩展)
        dispatch = ByteArray.parse(wire)
        suffix = body.扩展[wire.pos:]
        self.assertEqual(len(suffix), 78 if family == 'Stu' else 10)
        dispatch.value = native_dispatch
        body.扩展 = dispatch.to_bytes() + suffix
        settings.event_tail = body.序列化()
        original.trailer = settings.to_bytes()
        row['lbObjects'] = m.f.wrap_like(row['lbObjects'], original.to_bytes())
        row['iCompileFlag'] = 1

        page = m.inspect_data(data)['pages'][0]
        click = page['click_event_source']
        mouse = page['mouse_down_event_source']
        self.assertEqual((click['source'], click['compiled_size']), ('AuditSample = 17', 24))
        self.assertEqual((mouse['source'], mouse['compiled_size']), ('AuditTick = AuditSample', 23))
        self.assertEqual(mouse['parameter_bindings'], [{'name': 'AuditSample', 'id': 6, 'native_type_word': 2},
                                                     None, None, None])
        identity = {key: mouse[key] for key in ('event_type_id', 'event_id', 'name', 'sha256')}
        change = {'id': 1, 'events': {'mouse_down_event_source': dict(identity, source='AuditTick = AuditSample + 1')}}
        pending = []
        edited = m.edit_data(copy.deepcopy(data), {'pages': [change]}, pending_event_generation=pending)
        inspected = m.inspect_data(edited)['pages'][0]
        self.assertEqual((inspected['mouse_down_event_source']['source'], inspected['mouse_down_event_source']['compiled_size']),
                         ('AuditTick = AuditSample + 1', 0))
        self.assertEqual(inspected['click_event_source'], click)
        self.assertEqual(edited['WndUser']['rows'][0]['iCompileFlag'], 0)
        required_action = 'page-native-generate' if family == 'Stu' else 'reference-sync'
        self.assertEqual(pending, [{'page_id': 1, 'page_name': 'StartupPage', 'owner': 'window',
                                    'operation': 'mouse_down_event_source', 'event_type_id': 18, 'event_id': 3,
                                    'event_name': 'MouseDown', 'required_action': required_action}])
        actual = WindowArchive.parse(m.f.archive(edited['WndUser']['rows'][0]['lbObjects']))
        before_click = 读取页面Click(settings.event_tail)
        actual_click = 读取页面Click(actual.settings().event_tail)
        before_mouse, _ = 读取页面MouseDown(settings.event_tail, family=family)
        actual_mouse, _ = 读取页面MouseDown(actual.settings().event_tail, family=family)
        other_family = 'Pro' if family == 'Stu' else 'Stu'
        with self.assertRaisesRegex(ValueError, 'suffix does not match the project family'):
            读取页面MouseDown(actual.settings().event_tail, family=other_family)
        self.assertEqual(actual_click.to_bytes(), before_click.to_bytes())
        self.assertEqual(actual_mouse.header, before_mouse.header)
        self.assertEqual(actual_mouse.argument_arrays, before_mouse.argument_arrays)
        self.assertEqual(窗口事件.解析(actual.settings().event_tail).扩展[-len(suffix):], suffix)
        click_identity = before_click.identity()
        altered_click = {'id': 1, 'events': {'click_event_source': dict(click_identity, source='AuditSample = 18')}}
        changed = m.edit_data(copy.deepcopy(data), {'pages': [altered_click]})
        self.assertEqual(m.inspect_data(changed)['pages'][0]['mouse_down_event_source'], mouse)
        with self.assertRaisesRegex(ValueError, 'MouseDown event preimage differs'):
            m.edit_data(copy.deepcopy(edited), {'pages': [change]})
        with self.assertRaisesRegex(ValueError, 'declaration used by MouseDown'):
            m.edit_data(copy.deepcopy(data), {'pages': [{'id': 1, 'events': {'delete_click_event': click_identity}}]})
        with self.assertRaisesRegex(ValueError, f'single unparameterized {family} Click'):
            m.edit_data(copy.deepcopy(data), {'add_pages': [{'template_page_id': 1, 'name': 'FreshNative'}]})
        with self.assertRaisesRegex(ValueError, 'Nonempty generic-event argument arrays'):
            GenericMetadata.parse(native_dispatch)
        settings.password_data = b'\x01\0'
        original.trailer = settings.to_bytes()
        row['lbObjects'] = m.f.wrap_like(row['lbObjects'], original.to_bytes())
        with self.assertRaisesRegex(ValueError, 'unprotected window settings'):
            m.edit_data(copy.deepcopy(data), {'pages': [change]})

    def test_native_ellipse_and_bitmap_group_geometry_preserve_their_class_body(self):
        from mcs_window_archive import WindowArchive, write_cstring
        from 原生界面样式 import CommonEnvelope

        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                ellipse = {'type': 'ellipse', 'name': 'EllipseLeaf', 'bounds': [1, 2, 31, 22]}
                data = m.create_data({'pages': [{'name': 'StaticGeometry', 'controls': [
                    ellipse, rect('BitmapLeaf'), {'type': 'group', 'name': 'Sink',
                                                  'bounds': [1, 2, 61, 42], 'children': [
                            {'type': 'rectangle', 'name': 'Anchor', 'bounds': [0, 0, 1000, 1000]},
                        ]},
                ]}]}, family)
                row = data['WndUser']['rows'][0]
                archived = WindowArchive.parse(m.f.archive(row['lbObjects']))
                bitmap = CommonEnvelope.parse(archived.controls[1])
                bitmap.record.type_id = 0x5009
                bitmap.content = struct.pack('<I', 0x80) + write_cstring('Fixture named image')
                bitmap.set_rect([31, 22, 61, 42])
                archived.controls[1] = bitmap.to_record()
                row['lbObjects'] = m.f.wrap_like(row['lbObjects'], archived.to_bytes())
                entries = controls(data)
                group = {'action': 'group', 'name': 'StaticGroup', 'members': [selector(item) for item in entries[:2]]}
                grouped = m.edit_data(copy.deepcopy(data), {'pages': [{'id': 1, 'group_operations': [group]}]})
                group_entry = controls(grouped)[0]
                self.assertEqual([child['kind'] for child in group_entry['children']], ['0x5006', '0x5009'])
                ungroup = {'action': 'ungroup', 'member': selector(group_entry)}
                restored = m.edit_data(grouped, {'pages': [{'id': 1, 'group_operations': [ungroup]}]})
                self.assertEqual(restored, data)

                # Test another normal consumer, moving a static image into an existing group.
                move = {'action': 'move', 'source': [selector(entries[1])],
                        'destination': [selector(entries[2])], 'insert_at': 0}
                moved = m.edit_data(copy.deepcopy(data), {'pages': [{'id': 1, 'group_operations': [move]}]})
                group_now = controls(moved)[1]
                self.assertEqual([item['name'] for item in group_now['children']], ['BitmapLeaf', 'Anchor'])
                reverse = {'action': 'move', 'source': [selector(group_now), selector(group_now['children'][0])],
                           'destination': [], 'insert_at': 1}
                self.assertEqual(m.edit_data(moved, {'pages': [{'id': 1, 'group_operations': [reverse]}]}), data)

    def test_existing_native_rectangle_click_preserves_metadata_and_clears_its_cache(self):
        from mcs_window_archive import WindowArchive, write_count
        from 原生界面样式 import CommonEnvelope, GenericMetadata

        # One vendor-generated rectangle Click that writes a local number.
        wire = bytes.fromhex(
            'ffff00000e00434576656e74446973706174636818000000000000000000000000001111000000473eb6'
            '0000000100000000000013010000fffeff0543006c00690063006b0000000000fffeff00ffffffff'
            'fffeff13410075006400690074004500760065006e0074004500630068006f0020003d002000310037000000')
        data = project('Pro')
        page = data['WndUser']['rows'][0]
        original_window = WindowArchive.parse(m.f.archive(page['lbObjects']))
        original = CommonEnvelope.parse(original_window.controls[0])
        metadata = GenericMetadata.parse(original.metadata.value)
        original.metadata.value = write_count(1) + wire + metadata.tail
        original_window.controls[0] = original.to_record()
        page['lbObjects'] = m.f.wrap_like(page['lbObjects'], original_window.to_bytes())
        page['iCompileFlag'] = 1
        target = controls(data)[0]
        event = target['click_event_source']
        self.assertEqual((event['event_type_id'], event['event_id'], event['name'], event['source'], event['compiled_size']),
                         (275, 0, 'Click', 'AuditEventEcho = 17', 24))
        selector = {key: event[key] for key in ('event_type_id', 'event_id', 'name', 'sha256')}
        spec = {'name': target['name'], 'sha256': target['sha256'], 'edits': {
            'click_event_source': dict(selector, source='UnboundScalar = 21')}}
        pending = []
        after = m.edit_data(copy.deepcopy(data), {'pages': [{'id': page['iID'], 'controls': [spec]}]},
                            pending_event_generation=pending)
        self.assertEqual(pending, [{'page_id': page['iID'], 'control_name': target['name'],
                                    'event_type_id': 275, 'event_id': 0,
                                    'event_name': 'Click', 'required_action': 'reference-sync'}])
        self.assertEqual(after['WndUser']['rows'][0]['iCompileFlag'], 0)
        updated = controls(after)[0]['click_event_source']
        self.assertEqual((updated['source'], updated['compiled_size']), ('UnboundScalar = 21', 0))
        window = WindowArchive.parse(m.f.archive(after['WndUser']['rows'][0]['lbObjects']))
        common = CommonEnvelope.parse(window.controls[0])
        self.assertEqual(GenericMetadata.parse(common.metadata.value).tail, metadata.tail)
        common.metadata.value = original.metadata.value
        window.controls[0] = common.to_record()
        self.assertEqual(window.to_bytes(), original_window.to_bytes())
        spec['edits']['click_event_source']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'preimage differs'):
            m.edit_data(copy.deepcopy(data), {'pages': [{'id': page['iID'], 'controls': [spec]}]})

    def test_native_label_and_multi_state_button_click_requires_both_fingerprints(self):
        from control_patch import at_path, replace_path
        from mcs_button_control import ByteArray, CString
        from mcs_window_archive import Reader, WindowArchive, write_count, write_cstring
        from 原生界面样式 import CommonEnvelope, EventDispatch, GenericMetadata

        event_header = bytes.fromhex('ffff00000e00434576656e744469737061746368')
        def string(value):
            return CString.parse(Reader(write_cstring(value)))

        def attach(window, path, event_type, compiled_size, arguments=bytes(6)):
            common = CommonEnvelope.parse(at_path(window.controls, path))
            metadata = GenericMetadata.parse(common.metadata.value)
            self.assertEqual(metadata.events, [])
            compiled = bytes([0x11]) * compiled_size
            event = EventDispatch(event_header, ByteArray(compiled, compiled, write_count(compiled_size)),
                                  arguments, event_type, string('Click'), 0, string(''), 0xffffffff,
                                  string('UnboundScalar = 1'), ByteArray(b'', b'', write_count(0)))
            common.metadata.value = write_count(1) + event.to_bytes() + metadata.tail
            replace_path(window.controls, path, common.to_record())

        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                data = m.create_data({'variables': [{'name': 'UnboundScalar', 'type': 'number'}],
                    'pages': [{'name': 'Main', 'controls': [
                        {'type': 'group', 'name': 'Container', 'bounds': [1, 2, 100, 100], 'children': [
                            {'type': 'label', 'name': 'ClickLabel', 'text': 'Visible text',
                             'bounds': [100, 200, 3000, 2200]}, rect('Neighbor')]},
                        {'type': 'multi-state-button', 'name': 'ClickButton', 'bounds': [2, 3, 23, 43]},
                    ]}]}, family)
                row = data['WndUser']['rows'][0]
                window = WindowArchive.parse(m.f.archive(row['lbObjects']))
                attach(window, [0, 0], 282, 24)
                attach(window, [1], 262, 138)
                row['lbObjects'] = m.f.wrap_like(row['lbObjects'], window.to_bytes())
                row['iCompileFlag'] = 1
                entries = controls(data)
                targets = [entries[0]['children'][0], entries[1]]
                changes = []
                for path, target, event_type, compiled_size in zip(([0, 0], [1]), targets, (282, 262), (24, 138)):
                    click = target['click_event_source']
                    self.assertEqual((click['event_type_id'], click['compiled_size']), (event_type, compiled_size))
                    identity = {key: click[key] for key in ('event_type_id', 'event_id', 'name', 'sha256')}
                    changes.append({'path': path, 'name': target['name'], 'sha256': target['sha256'],
                        'edits': {'click_event_source': dict(identity, source='UnboundScalar = 42')}})
                spec = {'pages': [{'id': row['iID'], 'controls': changes}]}
                pending = []
                changed = m.edit_data(copy.deepcopy(data), spec, pending_event_generation=pending)
                after = WindowArchive.parse(m.f.archive(changed['WndUser']['rows'][0]['lbObjects']))
                self.assertEqual(changed['WndUser']['rows'][0]['iCompileFlag'], 0)
                self.assertEqual([x['control_path'] for x in pending], [[0, 0], [1]])
                self.assertEqual({x['required_action'] for x in pending},
                                 {'compile' if family == 'Stu' else 'reference-sync'})
                for path in ([0, 0], [1]):
                    before_leaf = at_path(window.controls, path)
                    after_leaf = at_path(after.controls, path)
                    _, metadata, click = m.control_click_event(after_leaf)
                    self.assertEqual((click.source.value, click.compiled.value), ('UnboundScalar = 42', b''))
                    self.assertEqual(metadata.tail, m.control_click_event(before_leaf)[1].tail)
                    replace_path(after.controls, path, before_leaf)
                self.assertEqual(after.to_bytes(), window.to_bytes())
                for index in (0, 1):
                    for key in ('event_type_id', 'event_id', 'sha256'):
                        bad = copy.deepcopy(spec)
                        bad['pages'][0]['controls'][index]['edits']['click_event_source'][key] = 1
                        with self.assertRaisesRegex(ValueError, 'event preimage differs'):
                            m.edit_data(copy.deepcopy(data), bad)
                bad = copy.deepcopy(spec)
                bad['pages'][0]['controls'][0]['path'] = [0, 1]
                with self.assertRaisesRegex(ValueError, 'path/name/SHA'):
                    m.edit_data(copy.deepcopy(data), bad)
                for path, event_type in (([0, 0], 282), ([1], 262)):
                    raw = CommonEnvelope.parse(at_path(window.controls, path))
                    parsed = GenericMetadata.parse(raw.metadata.value)
                    parsed.events[0].argument_arrays = struct.pack('<3H', 1, 0, 0)
                    raw.metadata.value = parsed.to_bytes()
                    with self.assertRaisesRegex(ValueError, 'argument arrays'):
                        m.control_click_event(raw.to_record())

    def test_native_history_range_and_visibility_preserve_source_and_every_other_field(self):
        from mcs_window_archive import WindowArchive, write_count, write_cstring
        from 原生界面样式 import CommonEnvelope
        from 原生趋势样式 import HistoryCurveStyle

        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                data = m.create_data({'pages': [{'name': 'Main', 'controls': [{
                    'type': 'history-curve', 'name': 'ArchiveTrend', 'bounds': [10, 10, 300, 200]}]}]}, family)
                row = data['WndUser']['rows'][0]
                window = WindowArchive.parse(m.f.archive(row['lbObjects']))
                common = CommonEnvelope.parse(window.controls[0])
                curve = HistoryCurveStyle(common.content)
                authored = {'bindings': write_count(2) + write_cstring('MCGS_Time') + write_cstring('TraceA'),
                            '158': write_cstring('ExistingHistory'), '1b4': write_cstring('MCGS_Time'),
                            '160': write_cstring('SelectedSeconds'), '164': write_cstring('SelectedMillis'),
                            'curve0_type': struct.pack('<I', 2), 'curve0_visible': struct.pack('<I', 1),
                            'curve0_source': write_cstring('TraceA'), 'curve0_min': write_cstring('-10'),
                            'curve0_max': write_cstring('100')}
                for span in curve.spans:
                    if span.name in authored:
                        span.raw = authored[span.name]
                common.content = curve.to_bytes()
                window.controls[0] = common.to_record()
                row['lbObjects'] = m.f.wrap_like(row['lbObjects'], window.to_bytes())
                before = controls(data)[0]
                self.assertEqual(before['history_curve_configuration'], {
                    'data_group': 'ExistingHistory', 'time_column': 'MCGS_Time',
                    'selected_seconds_output': 'SelectedSeconds', 'selected_milliseconds_output': 'SelectedMillis'})
                self.assertEqual(before['history_curve_ranges'], [dict(trace_index=0, data_name='TraceA', minimum=-10, maximum=100)])

                def specification(change, target):
                    control = {'name': target['name'], 'sha256': target['sha256'],
                               'edits': {'history_curve_ranges': [change]}}
                    return {'pages': [{'id': row['iID'], 'controls': [control]}]}

                after = m.edit_data(copy.deepcopy(data), specification({'trace_index':0, 'minimum':-12.5, 'maximum':125.75}, before))
                found = controls(after)[0]
                self.assertEqual(found['history_curve_configuration'], before['history_curve_configuration'])
                self.assertEqual(found['history_curve_ranges'], [dict(trace_index=0, data_name='TraceA', minimum=-12.5, maximum=125.75)])
                changed_window = WindowArchive.parse(m.f.archive(after['WndUser']['rows'][0]['lbObjects']))
                changed = HistoryCurveStyle(CommonEnvelope.parse(changed_window.controls[0]).content)
                self.assertEqual([name for name, value in curve.fields().items() if changed.fields()[name] != value],
                                 ['curve0_min', 'curve0_max'])
                inverse = m.edit_data(after, specification({'trace_index':0, 'minimum':-10.0, 'maximum':100.0}, found))
                self.assertEqual(m.canonical(inverse), m.canonical(data))
                bad = ({'trace_index':1, 'minimum':10}, {'trace_index':0, 'maximum':float('inf')},
                       {'trace_index':0, 'minimum':100}, {'trace_index':0, 'minimum':True},
                       {'trace_index':0, 'minimum':99.9999999})
                for change in bad:
                    with self.assertRaises(ValueError):
                        m.edit_data(copy.deepcopy(data), specification(change, before))

                def visibility_spec(mutations, target):
                    return {'pages': [{'id': row['iID'], 'controls': [
                        {'name': target['name'], 'sha256': target['sha256'],
                         'edits': {'history_curve_visibility': mutations}}]}]}

                self.assertEqual(before['history_curve_visibility'], [
                    dict(trace_index=0, data_name='TraceA', visible=True)])
                hide = {'trace_index': 0, 'visible': False}
                hidden = m.edit_data(copy.deepcopy(data), visibility_spec([hide], before))
                hidden_control = controls(hidden)[0]
                self.assertEqual(hidden_control['history_curve_visibility'], [
                    dict(trace_index=0, data_name='TraceA', visible=False)])
                self.assertEqual(hidden_control['history_curve_ranges'], [])
                self.assertEqual(hidden_control['history_curve_configuration'], before['history_curve_configuration'])
                hidden_window = WindowArchive.parse(m.f.archive(hidden['WndUser']['rows'][0]['lbObjects']))
                hidden_spans = HistoryCurveStyle(CommonEnvelope.parse(hidden_window.controls[0]).content).fields()
                self.assertEqual([name for name, value in curve.fields().items() if hidden_spans[name] != value],
                                 ['curve0_visible'])
                self.assertEqual(hidden_spans['curve0_visible'], bytes(4))
                with self.assertRaisesRegex(ValueError, 'visible numeric'):
                    m.edit_data(copy.deepcopy(hidden), specification({'trace_index': 0, 'minimum': -20}, hidden_control))
                shown = m.edit_data(hidden, visibility_spec([dict(hide, visible=True)], hidden_control))
                self.assertEqual(m.canonical(shown), m.canonical(data))
                for mutations in ([], [hide, hide], [dict(hide, trace_index=1)], [dict(hide, visible=0)]):
                    with self.assertRaises(ValueError):
                        m.edit_data(copy.deepcopy(data), visibility_spec(mutations, before))

    def test_native_history_x_length_edits_only_its_dword_with_original_unit_bounds(self):
        from mcs_window_archive import WindowArchive, write_count, write_cstring
        from 原生界面样式 import CommonEnvelope
        from 原生趋势样式 import HistoryCurveStyle

        for family in ('Stu', 'Pro'):
            template = m.create_data({'pages': [{'name': 'Main', 'controls': [{
                'type': 'history-curve', 'name': 'ArchiveTrend', 'bounds': [10, 10, 300, 200]}]}]}, family)

            def fixture(unit, length):
                data = copy.deepcopy(template)
                row = data['WndUser']['rows'][0]
                window = WindowArchive.parse(m.f.archive(row['lbObjects']))
                common = CommonEnvelope.parse(window.controls[0])
                style = HistoryCurveStyle(common.content)
                values = {'bindings': write_count(2) + write_cstring('MCGS_Time') + write_cstring('TraceA'),
                          '158': write_cstring('ExistingHistory'), '1b4': write_cstring('MCGS_Time'),
                          '1b8': struct.pack('<I', length), '1bc': struct.pack('<I', unit)}
                for span in style.spans:
                    if span.name in values:
                        span.raw = values[span.name]
                common.content = style.to_bytes()
                window.controls[0] = common.to_record()
                row['lbObjects'] = m.f.wrap_like(row['lbObjects'], window.to_bytes())
                return data, window.controls[0]

            def edit_length(data, value):
                target, = controls(data)
                return m.edit_data(copy.deepcopy(data), {'pages': [{'id': data['WndUser']['rows'][0]['iID'],
                    'controls': [{'name': target['name'], 'sha256': target['sha256'],
                                  'edits': {'history_curve_x_length': value}}]}]})

            for unit, maximum in enumerate((10000, 10000, 10000, 10000, 801, 66)):
                with self.subTest(family=family, unit=unit):
                    source, original = fixture(unit, 1)
                    self.assertEqual(controls(source)[0]['history_curve_x_length'], 1)
                    requested = 7 if unit == 1 else maximum
                    edited = edit_length(source, requested)
                    self.assertEqual(controls(edited)[0]['history_curve_x_length'], requested)
                    expected = CommonEnvelope.parse(original)
                    style = HistoryCurveStyle(expected.content)
                    span, = (span for span in style.spans if span.name == '1b8')
                    span.raw = struct.pack('<I', requested)
                    expected.content = style.to_bytes()
                    row = edited['WndUser']['rows'][0]
                    saved = WindowArchive.parse(m.f.archive(row['lbObjects'])).controls[0]
                    self.assertEqual(saved.to_bytes(), expected.to_record().to_bytes())
                    self.assertEqual(m.canonical(edit_length(edited, 1)), m.canonical(source))
                    with self.assertRaisesRegex(ValueError, f'1..{maximum}'):
                        edit_length(source, maximum + 1)

            source, _ = fixture(1, 1)
            for bad in (False, 0, -1, 1.5, '7'):
                with self.subTest(family=family, invalid=bad), self.assertRaises(ValueError):
                    edit_length(source, bad)
            for unit, invalid_length in ((6, 1), (1, 0), (5, 67)):
                malformed, _ = fixture(unit, invalid_length)
                self.assertNotIn('history_curve_x_length', controls(malformed)[0])
                with self.subTest(family=family, original=(unit, invalid_length)), self.assertRaises(ValueError):
                    edit_length(malformed, 7)
            with self.assertRaises(ValueError):
                edit_length(template, 7)

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
                anchor = by_name["EncodingAnchor"]
                if family == "Pro":
                    records.document_header = struct.pack("<f", 13.0)
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

    def test_first_pro_empty_group_preserves_native_encoding_on_each_side_of_cutoff(self):
        data = m.edit_data(project("Pro"), {"add_variables":[{"name":"SoleGroup", "type":"group"}]})
        slot = m.system(data, "ObjData")
        native = m.f
        before = native.archive(slot["lbContext"])
        flat = native.variables(before)
        variable = next(record for record in flat if record["name"] == "UnboundScalar")
        group = next(record for record in flat if record["name"] == "SoleGroup")
        member = {"id":variable["id"], "name":variable["name"]}
        change = {"id":group["id"], "name":group["name"], "before":[], "after":[member]}
        first, last = flat.empty_group_spans[group["id"]]
        self.assertEqual(first, last)
        linked_ids = m.edit_data(copy.deepcopy(data), {"data_group_members":change})
        ids_blob = native.archive(m.system(linked_ids, "ObjData")["lbContext"])
        self.assertEqual(ids_blob[8:], before[8:first-4] + struct.pack("<II", 1, member["id"]) + before[first:])
        self.assertEqual(native.variables(ids_blob).group_id_member_spans[group["id"]], (first, first + 4))
        self.assertEqual(m.inspect_data(linked_ids)["data_groups"][0]["members"], [member])
        self.assertEqual(native.archive(m.system(m.edit_data(linked_ids, {"data_group_members":
            dict(change, before=[member], after=[])}), "ObjData")["lbContext"]), before)

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


    def test_stu_history_storage_presets_compare_and_restore_exact_native_preimage(self):
        data = m.edit_data(project("Stu"), {"add_variables":[{"type":"group", "name":"HistoryGroup"}]})
        catalog = m.VariableCatalog(data)
        member = {"id":catalog["UnboundScalar"]["id"], "name":"UnboundScalar"}
        identity = {"id":catalog["HistoryGroup"]["id"], "name":"HistoryGroup"}
        data = m.edit_data(data, {"data_group_members":dict(identity, before=[], after=[member])})
        original = copy.deepcopy(data)
        self.assertEqual(m.inspect_data(data)["data_groups"][0]["history_storage"], "default")
        enable = {"data_group_storage":dict(identity, before="default", after="archive")}
        edited = m.edit_data(data, enable)
        self.assertEqual(m.inspect_data(edited)["data_groups"][0]["history_storage"], "archive")

        old_group = m.VariableCatalog(original)["HistoryGroup"]
        new_group = m.VariableCatalog(edited)["HistoryGroup"]
        expected_prefix = bytearray(old_group["prefix"])
        for offset, value in ((8, 1), (20, 1), (48, 1), (52, 25600), (56, 1)):
            struct.pack_into("<I", expected_prefix, offset, value)
        self.assertEqual(new_group, dict(old_group, prefix=bytes(expected_prefix)))
        with self.assertRaisesRegex(ValueError, "storage preimage"):
            m.edit_data(copy.deepcopy(edited), enable)
        inverse = {"data_group_storage":dict(identity, before="archive", after="default")}
        self.assertEqual(m.canonical(m.edit_data(edited, inverse)), m.canonical(original))

        pro = m.edit_data(project("Pro"), {"add_variables":[{"type":"group", "name":"HistoryGroup"}]})
        with self.assertRaisesRegex(ValueError, "verified project release"):
            m.edit_data(pro, enable)

    def test_pro_current_history_storage_preset_only_uses_original_disk_fields(self):
        data = m.edit_data(project("Pro"), {"add_variables":[{"type":"group", "name":"HistoryGroup"}]})
        variable_row = m.system(data, "ObjData")
        archive = m.f.archive(variable_row["lbContext"])
        variable_row["lbContext"] = m.f.wrap_like(variable_row["lbContext"], struct.pack("<f", 13.0) + archive[4:])
        version_row = m.system(data, "MCGSVER")
        version_row["lbContext"] = m.f.wrap_like(version_row["lbContext"], "McgsPro 3.5.2.12210\0".encode("utf-16le"))
        catalog = m.VariableCatalog(data)
        member = {"id":catalog["UnboundScalar"]["id"], "name":"UnboundScalar"}
        group = {"id":catalog["HistoryGroup"]["id"], "name":"HistoryGroup"}
        data = m.edit_data(data, {"data_group_members":dict(group, before=[], after=[member])})
        original = copy.deepcopy(data)
        self.assertEqual(m.inspect_data(data)["data_groups"][0]["history_storage"], "default")
        m.edit_data(data, {"data_group_storage":dict(group, before="default", after="archive")})
        self.assertEqual(m.inspect_data(data)["data_groups"][0]["history_storage"], "archive")
        old_group = m.VariableCatalog(original)["HistoryGroup"]
        new_group = m.VariableCatalog(data)["HistoryGroup"]
        expected = bytearray(old_group["prefix"])
        struct.pack_into("<I", expected, 20, 1)
        struct.pack_into("<I", expected, 52, 2000)
        self.assertEqual(new_group, dict(old_group, prefix=bytes(expected)))
        self.assertEqual(m.edit_data(data, {"data_group_storage":dict(group, before="archive", after="default")}), original)

    def test_edit_group_archive_settings_preserves_members_flags_and_existing_references(self):
        for family, before, after in (
                ("Pro", {"period_100ms": 100}, {"period_100ms": 30}),
                ("Stu", {"period_100ms": 1, "capacity_kb": 25600}, {"period_100ms": 20, "capacity_kb": 26000})):
            with self.subTest(family=family):
                data = m.edit_data(project(family), {"add_variables": [
                    {"type": "number", "name": "AnotherScalar"},
                    {"type": "group", "name": "TimedGroup"},
                ]})
                if family == "Pro":
                    obj = m.system(data, "ObjData")
                    archive = m.f.archive(obj["lbContext"])
                    obj["lbContext"] = m.f.wrap_like(obj["lbContext"], struct.pack("<f", 13.0) + archive[4:])
                    version = m.system(data, "MCGSVER")
                    version["lbContext"] = m.f.wrap_like(version["lbContext"], "McgsPro 3.5.2.12210\0".encode("utf-16le"))
                catalog = m.VariableCatalog(data)
                identity = {"id": catalog["TimedGroup"]["id"], "name": "TimedGroup"}
                member = {"id": catalog["UnboundScalar"]["id"], "name": "UnboundScalar"}
                second = {"id": catalog["AnotherScalar"]["id"], "name": "AnotherScalar"}
                default = m.edit_data(data, {"data_group_members": dict(identity, before=[], after=[member])})
                spec = {"data_group_archive_settings": dict(identity, before=before, after=after)}
                with self.assertRaisesRegex(ValueError, "enabled timed disk storage"):
                    m.edit_data(copy.deepcopy(default), spec)
                archived = m.edit_data(default, {"data_group_storage": dict(identity, before="default", after="archive")})
                referenced = copy.deepcopy(archived)
                referenced["Data"]["rows"].append({"iDataID": identity["id"]})
                edited = m.edit_data(copy.deepcopy(referenced), spec)
                expected = copy.deepcopy(referenced)
                holder = m.system(expected, "ObjData")
                records = m.f.variables(m.f.archive(holder["lbContext"]))
                group = next(record for record in records if record["id"] == identity["id"])
                prefix = bytearray(group["prefix"])
                struct.pack_into("<I", prefix, 8, after["period_100ms"])
                if family == "Stu":
                    struct.pack_into("<I", prefix, 52, after["capacity_kb"])
                group["prefix"] = bytes(prefix)
                holder["lbContext"] = m.f.wrap_like(holder["lbContext"], m.f.pack_variables(records))
                self.assertEqual(edited, expected)

                edited = m.edit_data(copy.deepcopy(archived), spec)
                report, = m.inspect_data(edited)["data_groups"]
                self.assertEqual((report["members"], report["history_storage"], report["archive_settings"]),
                                 ([member], "archive", after))
                with self.assertRaisesRegex(ValueError, "before values differ"):
                    m.edit_data(copy.deepcopy(edited), spec)
                edited = m.edit_data(edited, {"data_group_members": dict(identity, before=[member], after=[member, second])})
                self.assertEqual(m.inspect_data(edited)["data_groups"][0]["archive_settings"], after)
                for invalid in (0, -1, True, 2**31):
                    with self.assertRaisesRegex(ValueError, "positive signed 32-bit integers"):
                        m.edit_data(copy.deepcopy(archived), {"data_group_archive_settings": dict(
                            identity, before={"period_100ms": before["period_100ms"]}, after={"period_100ms": invalid})})
                if family == "Pro":
                    with self.assertRaisesRegex(ValueError, "supported fields"):
                        m.edit_data(copy.deepcopy(archived), {"data_group_archive_settings": dict(
                            identity, before={"capacity_kb": 2000}, after={"capacity_kb": 2500})})
                else:
                    capacity_only = {"data_group_archive_settings": dict(
                        identity, before={"capacity_kb": 25600}, after={"capacity_kb": 26000})}
                    capacity_group, = m.inspect_data(m.edit_data(copy.deepcopy(archived), capacity_only))["data_groups"]
                    self.assertEqual(capacity_group["archive_settings"], {"period_100ms": 1, "capacity_kb": 26000})

    def test_data_group_members_preserves_timed_storage_and_actual_dependency_guard(self):
        for family in ("Stu", "Pro"):
            with self.subTest(family=family):
                data = m.edit_data(project(family), {"add_variables": [
                    {"name": "KeepTimedMember", "type": "number"},
                    {"name": "AddTimedMember", "type": "string"},
                    {"name": "TimedArchiveGroup", "type": "group"},
                ]})
                f = m.f
                obj = m.system(data, "ObjData")
                if family == "Pro":
                    plain = f.archive(obj["lbContext"])
                    obj["lbContext"] = f.wrap_like(obj["lbContext"], struct.pack("<f", 13.0) + plain[4:])
                    version = m.system(data, "MCGSVER")
                    version["lbContext"] = f.wrap_like(version["lbContext"], "McgsPro 3.5.2.12210\0".encode("utf-16le"))
                catalog = m.VariableCatalog(data)
                pick = lambda name: {"id": catalog[name]["id"], "name": name}
                group = pick("TimedArchiveGroup")
                initial_members = [pick("UnboundScalar"), pick("KeepTimedMember")]
                final_members = [pick("KeepTimedMember"), pick("AddTimedMember")]
                data = m.edit_data(data, {
                    "data_group_members": dict(group, before=[], after=initial_members),
                    "data_group_storage": dict(group, before="default", after="archive"),
                })
                initial = copy.deepcopy(data)
                operation = dict(group, before=initial_members, after=final_members)
                member_edit = {"data_group_members": operation}
                edited = m.edit_data(copy.deepcopy(data), member_edit)
                before, after = (f.archive(m.system(item, "ObjData")["lbContext"]) for item in (initial, edited))
                span = f.variables(before).group_member_spans[group["id"]]
                vector = struct.pack("<I", len(final_members)) + b"".join(f.text(member["name"]) for member in final_members)
                self.assertEqual(after[8:span[0]-4], before[8:span[0]-4])
                self.assertEqual(after[span[0]-4:], vector + before[span[1]:])
                group_report = m.inspect_data(edited)["data_groups"][0]
                self.assertEqual(group_report["history_storage"], "archive")
                self.assertEqual(group_report["members"], final_members)
                inverse = {"data_group_members": dict(operation, before=final_members, after=initial_members)}
                self.assertEqual(m.edit_data(edited, inverse), initial)

                if family == "Stu":
                    custom = m.edit_data(copy.deepcopy(initial), {
                        "data_group_archive_settings": dict(group, before={"capacity_kb": 25600},
                                                            after={"capacity_kb": 26000}),
                    })
                    updated = m.edit_data(custom, member_edit)
                    custom_report = m.inspect_data(updated)["data_groups"][0]
                    self.assertEqual(custom_report["archive_settings"]["capacity_kb"], 26000)
                    self.assertEqual(custom_report["members"], final_members)

                blocked = copy.deepcopy(initial)
                blocked["Data"]["rows"].append({"iDataID": group["id"]})
                with self.assertRaisesRegex(ValueError, "Data.iDataID"):
                    m.edit_data(blocked, member_edit)
                with self.assertRaisesRegex(ValueError, "must retain at least one member"):
                    m.edit_data(copy.deepcopy(initial), {"data_group_members": dict(operation, after=[])})

                unknown = copy.deepcopy(initial)
                slot = m.system(unknown, "ObjData")
                records = f.variables(f.archive(slot["lbContext"]))
                selected = next(row for row in records if row["id"] == group["id"])
                changed_prefix = bytearray(selected["prefix"])
                struct.pack_into("<I", changed_prefix, 56, f.u32(changed_prefix, 56) + 1)
                selected["prefix"] = bytes(changed_prefix)
                slot["lbContext"] = f.wrap_like(slot["lbContext"], f.pack_variables(records))
                with self.assertRaisesRegex(ValueError, "verified default or timed storage preimage"):
                    m.edit_data(unknown, member_edit)


if __name__ == '__main__':
    unittest.main()
