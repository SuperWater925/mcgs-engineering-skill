"""Offline picture index lifecycle and typed reference checks."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

from test_state_resources import PictureResource, raster, states, string

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets/pro-3.5-cli/scripts'))
from native_format import archive, wrap_like
from offline_picture_library import LIST, PREFIX, edit_picture_library, library
from mcs_window_archive import WindowArchive
from picture_resources import Picture
from 原生界面样式 import CommonEnvelope, MultiState


def fixture():
    return json.loads((ROOT / 'assets/pro-3.5-cli/assets/blank-project-stu.json').read_text(encoding='utf-8-sig'))


def add(name, identity='abcdef0123456789abcdef0123456789'):
    q = PictureResource(string('Source native resource'), string(identity), 2, 2, 3, raster())
    return {'action': 'add', 'name': name, 'resource_hex': q.to_bytes().hex()}


class PictureLifecycle(unittest.TestCase):
    def test_add_rename_delete(self):
        baseline = fixture()
        data = copy.deepcopy(baseline)
        edit_picture_library(data, [add('Picture Alpha')])
        listing, names, resources = library(data['System']['rows'])
        self.assertEqual([n.value for n in names], ['Picture Alpha'])
        self.assertEqual(resources[0].payload, raster())
        edit_picture_library(data, [{'action': 'rename', 'name': 'Picture Alpha', 'new_name': 'Picture Beta'}])
        self.assertEqual(library(data['System']['rows'])[2][0].name.value, 'Picture Beta')
        edit_picture_library(data, [{'action': 'delete', 'name': 'Picture Beta'}])
        self.assertEqual(library(data['System']['rows'])[1:], ([], []))
        data['System']['rows'] = [r for r in data['System']['rows'] if r['strName'] != LIST]
        self.assertEqual(data, baseline)

    def test_add_image_file_bytes(self):
        for filename in ('blank-project-stu.json', 'blank-project.json'):
            path = ROOT / 'assets/pro-3.5-cli/assets' / filename
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            for image_format, kind in (('PNG', 2), ('JPEG', 2), ('BMP', 0)):
                payload = raster(image_format, (7, 5))
                edit_picture_library(data, [{'action': 'add', 'name': image_format, 'image_hex': payload.hex()}])
                q = library(data['System']['rows'])[2][-1]
                self.assertEqual((q.name.value, q.kind, q.width, q.height, q.payload),
                                 (image_format, kind, 7, 5, payload))
                original_digest = hashlib.md5(struct.pack('<4I', kind, 7, 5, len(payload)) + payload)
                self.assertEqual(q.identity.value, original_digest.hexdigest())
                self.assertTrue(q.name.wide and q.identity.wide)
            before = copy.deepcopy(data)
            with self.assertRaises((ValueError, OSError)):
                edit_picture_library(data, [{'action': 'add', 'name': 'bad', 'image_hex': '00'}])
            self.assertEqual(before, data)

    def test_native_bitmap_size_image_and_identical_content_under_distinct_names(self):
        data = fixture()
        complete = raster('BMP', (7, 5))
        omitted_length = complete[:34] + bytes(4) + complete[38:]
        edit_picture_library(data, [{'action': 'add', 'name': 'First', 'image_hex': omitted_length.hex()},
                                    {'action': 'add', 'name': 'Second', 'image_hex': complete.hex()}])
        _, names, resources = library(data['System']['rows'])
        self.assertEqual([name.value for name in names], ['First', 'Second'])
        self.assertEqual([item.kind for item in resources], [0, 0])
        self.assertEqual([item.payload for item in resources], [complete, complete])
        self.assertEqual(resources[0].identity.value, resources[1].identity.value)

    def test_native_bitmap_donor_preserves_record_while_renumbering_blank_library(self):
        data = fixture()
        donor = PictureResource.from_raster('Donor BMP', raster('BMP'))
        edit_picture_library(data, [add('Before', '1' * 32),
                                    {'action': 'add', 'name': 'NativeBmp', 'resource_hex': donor.to_bytes().hex()},
                                    add('After', '2' * 32)])
        _, _, resources = library(data['System']['rows'])
        donor.name.value = 'NativeBmp'
        self.assertEqual(resources[1].to_bytes(), donor.to_bytes())
        after = resources[2].to_bytes()
        edit_picture_library(data, [{'action': 'delete', 'name': 'NativeBmp'}])
        _, names, resources = library(data['System']['rows'])
        self.assertEqual([name.value for name in names], ['Before', 'After'])
        self.assertEqual(resources[1].to_bytes(), after)

    def test_native_rectangle_vector_adds_one_editable_shape(self):
        path = ROOT / 'assets/pro-3.5-cli/assets/blank-project.json'
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        action = {'action': 'add-vector-rectangle', 'name': 'AuditVector',
                  'bounds': [20, -30, 145, 50], 'fill': 0x2652ba, 'border': 0x30336b}
        edit_picture_library(data, [action])
        _, names, resources = library(data['System']['rows'])
        self.assertEqual([n.value for n in names], ['AuditVector'])
        q, = resources
        root, end = q.vector()
        rectangle, = root.children
        child = CommonEnvelope.parse(rectangle)
        self.assertEqual((q.kind, q.width, q.height), (16, 9, 9))
        self.assertEqual((root.common.rect, child.rect), ((20, -30, 145, 50), (0, 0, 10000, 10000)))
        self.assertEqual(struct.unpack_from('<II', q.payload, 62), (125, 80))
        self.assertEqual(root.common.metadata.value, bytes(12))
        self.assertEqual((rectangle.type_id, child.content, child.animations), (0x5004, b'', []))
        self.assertEqual(struct.unpack_from('<I', child.prefix, child.brush_offset+6)[0], 0x2652ba)
        self.assertEqual(struct.unpack_from('<I', child.prefix, child.pen_offset+14)[0], 0x30336b)
        self.assertEqual(q.payload[end:], bytes(len(q.payload)-end))
        canonical_payload = q.payload[:99] + struct.pack('<4i', 0, 0, 100, 100) + q.payload[115:]
        self.assertEqual(q.identity.value, hashlib.md5(struct.pack('<4I', 16, 9, 9, len(q.payload)) + canonical_payload).hexdigest())
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'identity already exists'):
            edit_picture_library(data, [dict(action, name='Same vector shifted', bounds=[0, 0, 125, 80])])
        with self.assertRaisesRegex(ValueError, 'positive'):
            edit_picture_library(data, [dict(action, name='Invalid vector', bounds=[4, 4, 4, 5])])
        self.assertEqual(before, data)
        stu = fixture()
        edit_picture_library(stu, [action])
        q, = library(stu['System']['rows'])[2]
        root, end = q.vector()
        stu_values = bytes(12) + struct.pack('<I', 10000)
        self.assertEqual(root.tail, bytes(12))
        self.assertEqual(root.common.metadata.value, stu_values)
        self.assertEqual(CommonEnvelope.parse(root.children[0]).metadata.value, stu_values)
        self.assertEqual(root.to_record().payload, q.payload[87:end])
        self.assertEqual(struct.unpack_from('<f', root.common.prefix)[0], 331.0)
        canonical_payload = q.payload[:99] + struct.pack('<4i', 0, 0, 100, 100) + q.payload[115:]
        self.assertEqual(q.identity.value, hashlib.md5(struct.pack('<4I', 16, q.width, q.height, len(q.payload)) + canonical_payload).hexdigest())

    def test_native_line_vector_preserves_directed_endpoints_and_archive(self):
        for filename in ('blank-project-stu.json', 'blank-project.json'):
            path = ROOT / 'assets/pro-3.5-cli/assets' / filename
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            keys = {'action': 'add-vector-line', 'bounds': [-2, -1, 1, 2], 'border': 0x315788}
            lines = [
                ('Horizontal', [1, 0, -1, 0], (10000, 3333, 3333, 3333)),
                ('Vertical', [0, -1, 0, 2], (6667, 0, 6667, 10000)),
                ('Diagonal', [1, -1, -2, 2], (10000, 0, 0, 10000)),
            ]
            edit_picture_library(data, [dict(keys, name=name, endpoints=points) for name, points, _ in lines])
            _, names, resources = library(data['System']['rows'])
            self.assertEqual([name.value for name in names], [name for name, _, _ in lines])
            for q, (_, _, expected) in zip(resources, lines):
                root, end = q.vector()
                shape, = root.children
                child = CommonEnvelope.parse(shape)
                extra = struct.pack('<I', 10000) if 'stu' in filename else b''
                self.assertEqual(root.common.rect, (-2, -1, 1, 2))
                self.assertEqual((q.kind, shape.type_id, child.rect), (16, 0x5002, expected))
                self.assertEqual((child.animations, child.content, child.metadata.value),
                                 ([], b'', bytes(12) + extra))
                self.assertEqual(root.to_record().payload, q.payload[87:end])
                self.assertEqual(struct.unpack_from('<I', child.prefix, child.pen_offset+14)[0], keys['border'])
                normalized = q.payload[:99] + struct.pack('<4i', 0, 0, 100, 100) + q.payload[115:]
                identity_input = struct.pack('<4I', 16, q.width, q.height, len(q.payload)) + normalized
                self.assertEqual(q.identity.value, hashlib.md5(identity_input).hexdigest())
            original = copy.deepcopy(data)
            for bounds, points in [([0, 0, 0, 1], [0, 0, 0, 1]),
                                   ([0, 0, 1, 1], [0, 0, 0, 0]),
                                   ([0, 0, 1, 1], [0, 0, 2, 1]),
                                   ([0, 0, 10**6, 1], [0, 0, 1, 0])]:
                with self.assertRaises(ValueError):
                    edit_picture_library(data, [dict(keys, name='Invalid', bounds=bounds, endpoints=points)])
            self.assertEqual(data, original)

    def test_typed_refs_and_opaque_use(self):
        data = fixture()
        edit_picture_library(data, [add('Picture1')])
        row = data['WndUser']['rows'][0]
        value = row['lbObjects']
        page = WindowArchive.parse(archive(value))
        page.controls[:] = [states()]
        row['lbObjects'] = wrap_like(value, page.to_bytes())
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'reference'):
            edit_picture_library(data, [{'action': 'delete', 'name': 'Picture1'}])
        self.assertEqual(data, before)
        rename = {'action': 'rename', 'name': 'Picture1', 'new_name': 'Picture1 changed'}
        edit_picture_library(data, [rename])
        page = WindowArchive.parse(archive(data['WndUser']['rows'][0]['lbObjects']))
        self.assertTrue(all(Picture.parse(items[0].picture).reference.value == 'Picture1 changed'
                            for items in MultiState.parse(page.controls[0]).images))
        page.trailer += 'PICTURE1 CHANGED'.encode('utf-16le')
        data['WndUser']['rows'][0]['lbObjects'] = wrap_like(value, page.to_bytes())
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'opaque picture reference'):
            edit_picture_library(data, [{'action': 'rename', 'name': 'Picture1 changed', 'new_name': 'Next'}])
        self.assertEqual(data, before)

    def test_compound_operation_atomic_on_bad_input(self):
        data = fixture()
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'identity'):
            edit_picture_library(data, [add('One'), add('Two')])
        self.assertEqual(before, data)
        edit_picture_library(data, [add('One'), add('Two', '1' * 32)])
        modified = copy.deepcopy(data)
        modified['WndUser']['rows'][0]['strName'] += ' modified'
        before = copy.deepcopy(modified)
        with self.assertRaisesRegex(ValueError, 'empty-project records'):
            edit_picture_library(modified, [{'action': 'delete', 'name': 'One'}])
        self.assertEqual(modified, before)
        for row in data['System']['rows']:
            if row['strName'] == LIST:
                row['lbContext'] = wrap_like(row['lbContext'], archive(row['lbContext'])[:-1])
        with self.assertRaises(ValueError):
            edit_picture_library(data, [{'action': 'delete', 'name': 'Two'}])

    def test_nonterminal_delete_preserves_identity_and_raster_bytes(self):
        for filename in ('blank-project-stu.json', 'blank-project.json'):
            data = json.loads((ROOT / 'assets/pro-3.5-cli/assets' / filename).read_text(encoding='utf-8-sig'))
            edit_picture_library(data, [add(name, str(i) * 32) for i, name in
                                       enumerate(('RasterAlpha', 'RasterBeta', 'RasterGamma', 'RasterDelta'), 1)])
            def identities():
                return {r['strName']: (r['iID'], r['lbContext']) for r in data['System']['rows']
                        if r['strName'].startswith(PREFIX)}
            before = identities()
            edit_picture_library(data, [{'action': 'delete', 'name': 'RasterBeta'}])
            self.assertEqual([n.value for n in library(data['System']['rows'])[1]],
                             ['RasterAlpha', 'RasterGamma', 'RasterDelta'])
            self.assertEqual(identities(), {PREFIX + str(i): before[PREFIX + str(old)]
                                            for i, old in enumerate((0, 2, 3))})

    def test_nonterminal_delete_accepts_exact_factory_vector_and_checks_full_archive(self):
        for filename in ('blank-project-stu.json', 'blank-project.json'):
            with self.subTest(filename=filename):
                data = json.loads((ROOT / 'assets/pro-3.5-cli/assets' / filename).read_text(encoding='utf-8-sig'))
                vector = {'action': 'add-vector-rectangle', 'name': 'RectVectorB',
                          'bounds': [8, 9, 12, 20], 'fill': 0x2189ab}
                edit_picture_library(data, [add('InitialImageA'), vector])
                changed = copy.deepcopy(data)
                item = next(r for r in changed['System']['rows'] if r['strName'] == PREFIX + '1')
                q = PictureResource.parse(archive(item['lbContext']))
                q.payload = q.payload[:-1] + b'\x01'
                item['lbContext'] = wrap_like(item['lbContext'], q.to_bytes())
                before = copy.deepcopy(changed)
                deletion = {'action': 'delete', 'name': 'InitialImageA'}
                with self.assertRaisesRegex(ValueError, 'exact factory shape vectors'):
                    edit_picture_library(changed, [deletion])
                self.assertEqual(before, changed)
                survivor = next(r for r in data['System']['rows'] if r['strName'] == PREFIX + '1')
                expected = dict(survivor, strName=PREFIX + '0')
                edit_picture_library(data, [deletion])
                names = [name.value for name in library(data['System']['rows'])[1]]
                self.assertEqual(names, ['RectVectorB'])
                self.assertIn(expected, data['System']['rows'])

    def test_grouped_factory_shapes_remain_editable_and_move_slots_without_reencoding(self):
        for filename in ('blank-project-stu.json', 'blank-project.json'):
            with self.subTest(filename=filename):
                path = ROOT / 'assets/pro-3.5-cli/assets' / filename
                data = json.loads(path.read_text(encoding='utf-8-sig'))
                action = {
                    'action': 'add-vector-shapes', 'name': 'ValveAndFlow', 'bounds': [0, 0, 100, 200],
                    'shapes': [
                        {'type': 'rectangle', 'bounds': [10, 30, 90, 120], 'fill': 0x214234},
                        {'type': 'line', 'endpoints': [90, 150, 20, 20], 'border': 0x30336b},
                        {'type': 'rectangle', 'bounds': [0, 20, 5, 50]},
                    ],
                }
                edit_picture_library(data, [add('InitialImageA'), action])
                survivor = next(row for row in data['System']['rows'] if row['strName'] == PREFIX + '1')
                q = PictureResource.parse(archive(survivor['lbContext']))
                root, _ = q.vector()
                self.assertEqual([child.type_id for child in root.children], [0x5004, 0x5002, 0x5004])
                self.assertEqual([CommonEnvelope.parse(child).rect for child in root.children],
                                 [(1000, 1500, 9000, 6000), (9000, 7500, 2000, 1000), (0, 1000, 500, 2500)])
                before = copy.deepcopy(data)
                invalid = dict(action, name='Bad', shapes=[{'type': 'rectangle', 'bounds': [4, 8, 3, 10]}])
                with self.assertRaisesRegex(ValueError, 'positive width'):
                    edit_picture_library(data, [add('ExtraImageA', '1' * 32), invalid])
                self.assertEqual(data, before)
                edit_picture_library(data, [{'action': 'delete', 'name': 'InitialImageA'}])
                self.assertIn(dict(survivor, strName=PREFIX + '0'), data['System']['rows'])

    def test_original_picture_trailer_survives_crossing_the_current_count(self):
        data = fixture()
        edit_picture_library(data, [add(name, str(i) * 32) for i, name in
                                   enumerate(('RasterAlpha', 'RasterBeta', 'RasterGamma'), 1)])
        listing, _, _ = library(data['System']['rows'])
        plain = archive(listing['lbContext'])
        historic = b'\x01\x00\x00\x00'
        listing['lbContext'] = wrap_like(listing['lbContext'], plain[:-4] + historic)
        _, names, resources = library(data['System']['rows'])
        self.assertEqual(len(names), 3)
        preserved = resources[0].to_bytes()
        edit_picture_library(data, [
            {'action': 'delete', 'name': 'RasterGamma'},
            {'action': 'delete', 'name': 'RasterBeta'},
            add('RasterDelta', '4' * 32),
        ])
        listing, names, resources = library(data['System']['rows'])
        self.assertEqual([name.value for name in names], ['RasterAlpha', 'RasterDelta'])
        self.assertEqual(archive(listing['lbContext'])[:4], b'\x02\x00\x00\x00')
        self.assertEqual(archive(listing['lbContext'])[-4:], historic)
        self.assertEqual(resources[0].to_bytes(), preserved)


if __name__ == '__main__':
    unittest.main()
