"""Exercise persistent native locator reuse with minimal non-runnable PE fixtures."""
import os
from pathlib import Path
import struct
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/pro-native-bridge/abi-adapter'))

import abi_binding
from abi_locator import CATALOG_SCHEMA, PROPERTY_METHOD_ROLES, create_catalog, resolve_catalog
from layout_adaptation import field_operands, resolve_model
from module_selection import select_module_files
from pe32 import PE32
import rtti
from x86_signature import attach_reference_contexts, decode_signature


def write_pe(path, *, dll=False, marker=0, code=()):
    used = max((rva - 4096 + len(instructions) for rva, instructions in code), default=0)
    section_size = max(512, (used + 511) // 512 * 512)
    raw = bytearray(512 + section_size)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, 0x80)
    raw[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', raw, 0x84, 0x14c, 1, 0, 0, 0, 96, 0x2002 if dll else 2)
    optional = 0x98
    struct.pack_into('<H', raw, optional, 0x10b)
    struct.pack_into('<III', raw, optional + 28, 0x400000, 4096, 512)
    struct.pack_into('<II', raw, optional + 56, 8192, 512)
    struct.pack_into('<8sIIII12xI', raw, optional + 96, b'.text', section_size, 4096, section_size, 512, 0x60000020)
    raw[-1] = marker
    for rva, instructions in code:
        start = 512 + rva - 4096
        raw[start:start + len(instructions)] = instructions
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


class AbiCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.install = root / 'install'
        self.editor = self.install / 'app' / 'editor.exe'
        self.library = self.install / 'elsewhere' / 'abi-cache-fixture.dll'
        write_pe(self.editor)
        write_pe(self.library, dll=True)
        self.cache = root / 'native-abi'
        self.catalog = {'schema': CATALOG_SCHEMA, 'reference_modules': {
            'editor': {'basename': self.editor.name, 'sha256': 'reference-editor'},
            'control': {'basename': self.library.name, 'sha256': 'reference-library'}},
            'profiles': [], 'signatures': [], 'types': []}

    def select(self, scope='first'):
        layout = SimpleNamespace(editor_executable=self.editor, install_root=self.install, task_root=scope)
        return select_module_files(self.catalog, layout, cache_root=self.cache)

    def resolve(self, selection):
        return abi_binding.resolve_selected(self.catalog, selection, self.cache)

    def test_same_bytes_reuse_across_fresh_scopes(self):
        cold = self.select()
        expected, receipt = self.resolve(cold)
        self.assertEqual(receipt['status'], 'miss')
        warm = self.select('second')
        self.assertEqual(warm['report']['preparation_image_cache']['verified_disk_cache_hits'], 2)
        self.assertEqual(warm['report']['modules'], cold['report']['modules'])
        with patch.object(abi_binding, 'resolve_catalog', side_effect=AssertionError('unexpected rescan')):
            actual, receipt = self.resolve(warm)
        self.assertEqual(receipt['status'], 'hit')
        self.assertEqual(actual, expected)

    def test_changed_bytes_even_with_same_timestamp_invalidate_resolution(self):
        cold = self.select()
        self.resolve(cold)
        original = self.library.stat()
        write_pe(self.library, dll=True, marker=1)
        os.utime(self.library, ns=(original.st_atime_ns, original.st_mtime_ns))
        changed = self.select()
        self.assertNotEqual(changed['sha256']['control'], cold['sha256']['control'])
        self.assertEqual(self.resolve(changed)[1]['status'], 'miss')

    def test_new_preferred_location_is_selected_even_for_same_bytes(self):
        cold = self.select()
        self.resolve(cold)
        preferred = self.editor.parent / self.library.name
        preferred.write_bytes(self.library.read_bytes())
        current = self.select()
        self.assertEqual(current['files']['control'], preferred.resolve())
        self.assertEqual(current['sha256'], cold['sha256'])
        self.assertEqual(self.resolve(current)[1]['status'], 'miss')

    def test_corrupt_cache_rebuilds_and_changed_resolver_contract_misses(self):
        selected = self.select()
        expected, _ = self.resolve(selected)
        entry = next((self.cache / 'rva-resolution').glob('*.cache'))
        entry.write_bytes(entry.read_bytes()[:-1] + b'!')
        rebuilt, receipt = self.resolve(selected)
        self.assertEqual(receipt['status'], 'miss')
        self.assertEqual(rebuilt, expected)
        with patch.object(abi_binding, 'DECODER_VERSION', 'new-fixture-version'):
            self.assertEqual(self.resolve(selected)[1]['status'], 'miss')


class AbiRoleTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.reference = root / 'reference.exe'
        self.current = root / 'current.exe'

    def test_inserted_slot_and_short_changed_named_entry(self):
        old_named, old_internal = 0x1000, 0x1010
        new_inserted, new_internal, new_named = 0x1020, 0x1040, 0x11ff
        write_pe(self.reference, code=[
            (old_named, bytes.fromhex('31c0c3')), (old_internal, bytes.fromhex('b805000000c3'))])
        write_pe(self.current, code=[
            (new_inserted, bytes.fromhex('b812000000c3')),
            (new_internal, bytes.fromhex('b811000000c3')), (new_named, b'\xc3')])
        reference = PE32(self.reference)
        signatures = []
        for key, address, names in [
                ('named', old_named, ['?Method@Class@@QAEXXZ']), ('internal', old_internal, [])]:
            model = attach_reference_contexts(reference, decode_signature(reference, address, 16))
            model.update(id=key, module='editor', exports=names)
            signatures.append(model)
        before = {'decorated_name': '.?AVClass@@', 'col_offset': 0, 'constructor_displacement_offset': 0,
                  'vtable_rva': 0x1150, 'col_rva': 0x1170, 'type_descriptor_rva': 0x1190,
                  'slot_entry_rvas': [old_named, old_internal],
                  'hierarchy': {'rva': 0x11b0, 'base_array_rva': 0x11c0, 'attributes': 0, 'bases': []}}
        after = {**before, 'vtable_rva': 0x1160, 'slot_entry_rvas': [new_inserted, new_named, new_internal]}
        catalog = {'schema': CATALOG_SCHEMA, 'reference_modules': {'editor': reference.identity()},
                   'signatures': signatures, 'profiles': [],
                   'types': [{'id': 'table', 'module': 'editor', 'reference': before}]}

        def exports(image):
            image.exports['?Method@Class@@QAEXXZ'] = {'rva': new_named}

        with patch.object(PE32, '_parse_exports', exports), patch.object(rtti, 'locate_type', return_value={'tables': [after]}):
            resolved = resolve_catalog(catalog, {'editor': self.current})
        named, internal = resolved['functions']
        self.assertEqual(named['actual_rva'], new_named)
        self.assertEqual(named['actual_guard_length'], 1)
        self.assertEqual(named['actual_guard_bytes'], 'c3')
        self.assertNotEqual(internal['status'], 'resolved')
        self.assertEqual(resolved['types'][0]['slot_coverage']['identified_slots'], [{
            'reference_index': 0, 'actual_index': 1, 'actual_entry_rva': new_named, 'method_proof_id': 'named'}])

    def test_field_witness_follows_current_thunk_added_prologue(self):
        write_pe(self.reference, code=[(0x1000, bytes.fromhex('8b4120c3'))])
        write_pe(self.current, code=[(0x1000, bytes.fromhex('eb1e')),
                                    (0x1020, bytes.fromhex('558bec8b4130c3'))])
        reference, current = PE32(self.reference), PE32(self.current)
        model = attach_reference_contexts(reference, decode_signature(reference, 0x1000, 16))
        operands = field_operands(model, 'mem', 0x20)
        self.assertEqual(resolve_model(model, operands, current, {'actual_rva': 0x1000}),
                         (0x1023, {(0, 1): 0x30}, True))

    def test_reviewed_properties_publish_only_text_setter_with_or_without_cache(self):
        root = self.reference.parent
        profiles = root / 'profiles'
        profiles.mkdir()
        default_setter = 0x1080
        code = [(default_setter, bytes.fromhex('c20400'))]
        tables = {}
        templates = []
        entry_points = []
        role_count = len(PROPERTY_METHOD_ROLES)
        for index in range(role_count + 1):
            entry = 0x1000 + index * 0x10
            body = 0x1100 + index * 0x64
            # The discriminator lies after a real internal JMP. A prefix-only
            # declaration would see the same prologue in every fixture method.
            instructions = (bytes.fromhex('558beceb029090b8') + struct.pack('<I', index + 1)
                            + b'\x90' * 82 + bytes.fromhex('5dc20400'))
            code.extend([(entry, b'\xe9' + struct.pack('<i', body - entry - 5)), (body, instructions)])
            entry_points.append(entry)
        for index, (name, displacement, roles) in enumerate(PROPERTY_METHOD_ROLES):
            data_rva = 0x1800 + index * 0x100
            setter = entry_points[-1] if any(slot == 5 for slot, _, _ in roles) else default_setter
            tables[name] = {'decorated_name': name, 'vtable_rva': data_rva,
                            'col_offset': displacement, 'constructor_displacement_offset': 0,
                            'col_rva': data_rva + 0x24, 'type_descriptor_rva': data_rva + 0x38,
                            'slot_entry_rvas': [default_setter] * 5 + [setter, entry_points[index], default_setter],
                            'hierarchy': {'rva': data_rva + 0x58, 'base_array_rva': data_rva + 0x70,
                                          'attributes': 0, 'bases': [{
                                              'decorated_name': '.?AVIPropertyLinker@ObjectTree@@',
                                              'contained': 0, 'attributes': 0, 'pmd': [displacement, -1, 0],
                                              'descriptor_rva': data_rva + 0x78,
                                              'type_descriptor_rva': 0x1600}]}}
            templates.append((name, displacement, tuple((slot, role, len(instructions))
                                                        for slot, role, _ in roles)))
        write_pe(self.reference, code=code)
        mutated = code + [(0x1100 + role_count * 0x64 + 8, b'\xf0')]
        write_pe(self.current, marker=1, code=mutated)
        with patch('abi_locator.PROPERTY_METHOD_ROLES', templates), patch.object(
                rtti, 'locate_type', side_effect=lambda image, name: {'tables': [dict(tables[name])]}):
            catalog = create_catalog({'editor': self.reference}, profiles)
            self.assertEqual(len(catalog['types']), role_count)
            expected_slots = [sorted(slot for slot, _, _ in roles) for _, _, roles in PROPERTY_METHOD_ROLES]
            self.assertEqual(sum(slots.count(5) for slots in expected_slots), 1)
            for use_cache in (True, False):
                resolved = resolve_catalog(catalog, {'editor': self.reference}, prefer_content_cache=use_cache)
                self.assertEqual([[slot['reference_index'] for slot in row['slot_coverage']['identified_slots']]
                                  for row in resolved['types']], expected_slots)
                bodies = [row['terminal_body_contract'] for row in resolved['functions']
                          if row['names'][0].endswith(('/property-getter', '/property-setter'))]
                self.assertEqual([row['complete_supplied_match_length'] for row in bodies],
                                 [len(instructions)] * (role_count + 1))
                self.assertTrue(all(row['satisfied'] for row in bodies))
            changed = resolve_catalog(catalog, {'editor': self.current}, prefer_content_cache=False)
        self.assertEqual([[slot['reference_index'] for slot in row['slot_coverage']['identified_slots']]
                          for row in changed['types']], [[6]] * role_count)


if __name__ == '__main__':
    unittest.main()
