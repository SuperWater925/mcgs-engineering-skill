"""Current group-layout dataflow fixtures; no native process or vendor binary."""
import struct
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/pro-native-bridge/abi-adapter'))
from layout_adaptation import group_children_fields, group_receiver_uses
from pe32 import PE32


def write_image(path, code):
    raw = bytearray(4608)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, 0x80)
    raw[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', raw, 0x84, 0x14c, 1, 0, 0, 0, 96, 2)
    optional = 0x98
    struct.pack_into('<H', raw, optional, 0x10b)
    struct.pack_into('<III', raw, optional + 28, 0x400000, 4096, 512)
    struct.pack_into('<II', raw, optional + 56, 8192, 512)
    struct.pack_into('<8sIIII12xI', raw, optional + 96, b'.text', 4096, 4096, 4096, 512, 0x60000020)
    for rva, instructions in code.items():
        start = 512 + rva - 4096
        raw[start:start + len(instructions)] = instructions
    path.write_bytes(raw)


def receiver_method(start, offset, variant='stack', foreign=False):
    code = bytearray()
    def call(target):
        code.extend(b'\xe8' + struct.pack('<i', target - (start + len(code) + 5)))
    if variant == 'stack':
        code.extend(bytes.fromhex('558bec83ec08894df8'))
        code.extend(bytes.fromhex('8b4df881c1') + struct.pack('<I', offset))
        call(0x1800)
        code.extend(bytes.fromhex('8b75f88d8e') + struct.pack('<I', offset))
        call(0x1820)
        code.extend(bytes.fromhex('c9c3'))
    else:
        # A non-this receiver must never be accepted merely for calling the roles.
        code.extend(bytes.fromhex('be00006000') if foreign else bytes.fromhex('8bf1'))
        code.extend(bytes.fromhex('8d8e') + struct.pack('<I', offset))
        call(0x1800)
        code.extend(bytes.fromhex('8bc605') + struct.pack('<I', offset) + bytes.fromhex('8bc8'))
        call(0x1820)
        code.extend(b'\xc3')
    return bytes(code)


class GroupLayoutTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='mcgs-group-layout-')
        self.addCleanup(temporary.cleanup)
        self.file = Path(temporary.name) / 'fixture.exe'
        self.roles = [{0x1800}, {0x1820}]
        self.code = {0x1800: bytes.fromhex('8b4104c3'), 0x1820: bytes.fromhex('8b4108c20400')}
        self.resolution = {'rva_maps': {'editor': {
            '0x47c80': {'actual_rva': 0x1800}, '0x278b3': {'actual_rva': 0x1820}}}}

    def image(self):
        write_image(self.file, self.code)
        return PE32(self.file)

    def test_equivalent_stack_and_register_receivers(self):
        self.code[0x1100] = receiver_method(0x1100, 0x130)
        self.code[0x1200] = receiver_method(0x1200, 0x130, 'register')
        image = self.image()
        self.assertEqual(group_receiver_uses(image, 0x1100, self.roles), [0x130])
        self.assertEqual(group_receiver_uses(image, 0x1200, self.roles), [0x130])

    def test_branch_join_does_not_keep_a_this_alias_from_only_one_path(self):
        prefix = bytes.fromhex('8bf185c07405be00006000')
        # At the join ESI is this on one branch and a foreign address on another.
        tail = receiver_method(0x1100 + len(prefix) - 2, 0x130, 'register')[2:]
        self.code[0x1100] = prefix + tail
        self.assertEqual(group_receiver_uses(self.image(), 0x1100, self.roles), [])

    def test_partial_register_writes_invalidate_complete_this_alias(self):
        # MOV EAX,ECX; MOV AL,1 / XOR AX,AX; MOV ESI,EAX. Neither EAX is still this.
        for changed in ('b001', '6631c0'):
            with self.subTest(changed=changed):
                prefix = bytes.fromhex('8bc1' + changed + '8bf0')
                tail = receiver_method(0x1100 + len(prefix) - 2, 0x130, 'register')[2:]
                self.code[0x1100] = prefix + tail
                self.assertEqual(group_receiver_uses(self.image(), 0x1100, self.roles), [])

    def test_overlapping_or_unknown_memory_write_invalidates_spilled_this(self):
        # Save this at [EBP-8]; overwrite its second byte, or use an unknown address.
        for changed in ('c645f901', 'c60201'):
            with self.subTest(changed=changed):
                prefix = bytes.fromhex('558bec83ec08894df8' + changed + '8b75f8')
                tail = receiver_method(0x1100 + len(prefix) - 2, 0x130, 'register')[2:]
                self.code[0x1100] = prefix + tail
                self.assertEqual(group_receiver_uses(self.image(), 0x1100, self.roles), [])

    def test_native_style_loop_preserves_frame_across_child_writes_and_virtual_cleanup(self):
        start, offset = 0x1100, 0x130
        code = bytearray(bytes.fromhex('558bec83ec0c894df88b4df881c1') + struct.pack('<I', offset))
        def call(target):
            code.extend(b'\xe8' + struct.pack('<i', target - (start + len(code) + 5)))
        call(0x1800)
        code.extend(bytes.fromhex('8945f4'))
        loop = start + len(code)
        code.extend(bytes.fromhex('8d4df4518b4df881c1') + struct.pack('<I', offset))
        call(0x1820)
        # Load a CDraw* from GetNext's data slot, write its fields, then pass a
        # four-word argument block to the actual virtual role (RET 16).
        code.extend(bytes.fromhex('8b008945fcc740280100000083ec108bd431c089028b4dfc8b01ff501c'))
        code.extend(bytes.fromhex('8b45fcc7402800000000837df4000f85'))
        code.extend(struct.pack('<i', loop - (start + len(code) + 4)))
        code.extend(bytes.fromhex('c9c3'))
        self.code.update({start: bytes(code), 0x1900: bytes.fromhex('c21000')})
        self.assertEqual(group_receiver_uses(self.image(), start, self.roles, {7: 0x1900}), [offset])

    def test_moved_virtual_methods_and_independent_class_offsets(self):
        self.code.update({0x1100: receiver_method(0x1100, 0x130),
                          0x1200: receiver_method(0x1200, 0x130, 'register'),
                          0x1300: receiver_method(0x1300, 0x98),
                          0x1400: receiver_method(0x1400, 0x98, 'register')})
        def tables(image, name):
            entries = [0x1800] * 24
            entries[1], entries[19] = (0x1100, 0x1200) if name == '.?AVCDrawUnit@@' else (0x1300, 0x1400)
            return {'tables': [{'col_offset': 0, 'slot_entry_rvas': entries}]}
        with patch('layout_adaptation.locate_type', side_effect=tables):
            result = group_children_fields(self.image(), self.resolution)
        self.assertEqual(result['group.CDrawUnit.children']['offset'], 0x130)
        self.assertEqual(result['group.CDrawCell.children']['offset'], 0x98)
        self.assertEqual([row['primary_slot'] for row in result['group.CDrawUnit.children']['evidence']], [1, 19])

    def test_non_this_alias_and_missing_role_do_not_guess_layout(self):
        self.code[0x1100] = receiver_method(0x1100, 0xe4, 'register', foreign=True)
        self.assertEqual(group_receiver_uses(self.image(), 0x1100, self.roles), [])
        result = group_children_fields(self.image(), {'rva_maps': {}})
        self.assertTrue(all(row['status'] == 'unresolved' for row in result.values()))

    def test_disagreement_is_local_to_that_group_class(self):
        self.code.update({0x1100: receiver_method(0x1100, 0x130),
                          0x1200: receiver_method(0x1200, 0x134),
                          0x1300: receiver_method(0x1300, 0x98),
                          0x1400: receiver_method(0x1400, 0x98, 'register')})
        def tables(image, name):
            entries = [0x1100, 0x1200] if name == '.?AVCDrawUnit@@' else [0x1300, 0x1400]
            return {'tables': [{'col_offset': 0, 'slot_entry_rvas': entries}]}
        with patch('layout_adaptation.locate_type', side_effect=tables):
            result = group_children_fields(self.image(), self.resolution)
        self.assertEqual(result['group.CDrawUnit.children']['status'], 'unresolved')
        self.assertEqual(result['group.CDrawCell.children']['offset'], 0x98)


if __name__ == '__main__':
    unittest.main()
