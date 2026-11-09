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
from abi_locator import CATALOG_SCHEMA
from module_selection import select_module_files


def write_pe(path, *, dll=False, marker=0):
    raw = bytearray(1024)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, 0x80)
    raw[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', raw, 0x84, 0x14c, 1, 0, 0, 0, 96, 0x2002 if dll else 2)
    optional = 0x98
    struct.pack_into('<H', raw, optional, 0x10b)
    struct.pack_into('<III', raw, optional + 28, 0x400000, 4096, 512)
    struct.pack_into('<II', raw, optional + 56, 8192, 512)
    struct.pack_into('<8sIIII12xI', raw, optional + 96, b'.text', 512, 4096, 512, 512, 0x60000020)
    raw[-1] = marker
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


if __name__ == '__main__':
    unittest.main()
