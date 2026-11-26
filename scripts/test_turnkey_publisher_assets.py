"""Verify complete/update publisher assets with tiny, file-only bundles."""

from argparse import Namespace
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from apply_turnkey_update import apply_update
import build_turnkey_bundle as full
import build_turnkey_update as update
from check_repository import MANIFEST, file_manifest, package_files
import turnkey_bundle as bundle
from turnkey_publisher_assets import (
    BOOTSTRAP_SOURCES, BRIDGE_CONTRACT, BRIDGE_MANIFEST, BRIDGE_SOURCE_FILES,
    STU_MANIFEST, bridge_source_inputs, read_directory, sha256, shared_bridge_payload,
)


def write(root, name, raw):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def dump(root, name, data):
    return write(root, name, update.encoded(data))


class PublisherAssetsTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.repo = self.root / 'repo'
        self.business = self.root / 'pro-build'
        self.stu = self.root / 'stu-build'
        self.bridge = self.root / 'bridge-build'
        self.old_bridge = self.root / 'old-bridge'
        self.tools = self.root / 'tools'
        self.stu_name = 'McgsStuBusinessEngine.dll'
        self.pro_name = 'McgsEngineering.Portable.dll'
        self.bridge_id = {'release': 'mcgs-portable-bridge/v6', 'bridge_file': 'Bridge_v6.dll',
                          'client_file': 'Attach_v6.exe', 'hook_file': 'Hook_v6.dll'}

        self.write_source()
        self.write_engines()
        self.write_bridge()
        self.write_tools()

    def write_source(self):
        for name in ('SKILL.md', 'references/turnkey-start-zh.md', 'references/turnkey-third-party.md',
                     'references/turnkey-update-zh.md', 'scripts/apply_turnkey_update.py', 'scripts/turnkey_bundle.py',
                     *BRIDGE_SOURCE_FILES):
            write(self.repo, name, name.encode())
        dump(self.repo, BRIDGE_CONTRACT, self.bridge_id)
        self.pro_inputs = {
            'source_manifest_sha256': 'assets/pro-native-bridge/delivery/source/source-and-dependency-manifest.json',
            'source_catalog_sha256': 'assets/pro-native-bridge/abi-adapter/catalogs/source-addresses.json',
        }
        for name in self.pro_inputs.values():
            write(self.repo, name, name.encode())
        self.stu_inputs = ('assets/stu-native/src/build-engine.py', 'assets/stu-native/src/Engine.cs',
                           'assets/stu-native/profile/reference.json', 'assets/stu-native/profile/locate.py')
        for name in self.stu_inputs:
            write(self.repo, name, name.encode())

    def write_engines(self):
        managed_pro = write(self.business, self.pro_name, b'current own Pro engine')
        pro_rows = {key: bundle._sha(self.repo / name) for key, name in self.pro_inputs.items()}
        dump(self.business, 'portable-engine-manifest.json', {'sha256': bundle._sha(managed_pro), **pro_rows})
        managed_stu = write(self.stu, self.stu_name, b'current own Stu engine')
        sources = [{'file': name, 'sha256': bundle._sha(self.repo / name)} for name in self.stu_inputs]
        dump(self.stu, STU_MANIFEST, {'family': 'stu', 'file': self.stu_name, 'sha256': bundle._sha(managed_stu),
                                      'sources': sources})

    def write_bridge(self):
        write(self.old_bridge, 'legacy-bridge.dll', b'base bridge')
        artifacts = []
        for key in ('bridge_file', 'client_file', 'hook_file'):
            name = self.bridge_id[key]
            raw = ('current own ' + name).encode()
            write(self.bridge, name, raw)
            artifacts.append({'file': name, 'bytes': len(raw), 'sha256': sha256(raw)})
        generated = []
        for name in (*BOOTSTRAP_SOURCES, 'PortableEntry.cs'):
            path = write(self.bridge, 'source/' + name, name.encode())
            generated.append({'file': 'source\\' + name, 'sha256': bundle._sha(path)})
        dump(self.bridge, BRIDGE_MANIFEST, {'schema': 1, 'contract': self.bridge_id['release'], 'identity': self.bridge_id,
                                           'receiver_compilation_required': False, 'vendor_files_included': False,
                                           'artifacts': artifacts, 'sources': generated,
                                           'source_inputs': bridge_source_inputs(self.repo)})

    def write_tools(self):
        tools = []
        for name, source in (('McgsStart.exe', 'Launcher.cs'), ('InstallerChoice.exe', 'InstallerChoice.cs')):
            path = write(self.tools, name, name.encode())
            relative = 'assets/turnkey-setup/' + source
            source_file = write(self.repo, relative, source.encode())
            tools.append({'file': name, 'sha256': bundle._sha(path), 'source': relative, 'source_sha256': bundle._sha(source_file)})
        dump(self.tools, 'publisher-tools-manifest.json', {'schema': 'mcgs-publisher-tools/v1', 'artifacts': tools})
        dump(self.repo, MANIFEST, file_manifest(self.repo, package_files(self.repo)))

    def complete(self, label, with_stu):
        inputs = self.root / 'runtime-inputs'
        inputs.mkdir(exist_ok=True)
        python, ps = inputs / 'python.zip', inputs / 'pwsh.zip'
        if not python.exists():
            with ZipFile(python, 'x') as archive:
                archive.writestr('python.exe', b'fixture Python')
                archive.writestr('python311._pth', 'python311.zip\n.\n#import site\n')
            with ZipFile(ps, 'x') as archive:
                archive.writestr('pwsh.exe', b'fixture PowerShell')
        for family, editor in (('pro', 'McgsSetPro.exe'), ('stu', 'McgsSetStu.exe')):
            write(inputs, f'{family}/Setup.exe', b'fixture installer')
            write(inputs, f'{family}/Bin/{editor}', b'fixture editor')
        ace = write(inputs, 'ace.exe', b'fixture ACE installer')
        output, archive_file = self.root / label, self.root / (label + '.zip')
        args = Namespace(output=output, release=label, python_zip=python, powershell_zip=ps, wheels=inputs,
                         business=self.business, tools=self.tools, pro_media=inputs / 'pro', stu_media=inputs / 'stu',
                         bridge=None if with_stu else self.old_bridge, bridge_build=self.bridge if with_stu else None,
                         stu_engine_build=self.stu if with_stu else None, ace_installer=ace, stage_only=False, zip=archive_file)
        with patch.object(full, '__file__', str(self.repo / 'scripts/build_turnkey_bundle.py')), redirect_stdout(io.StringIO()):
            full.assemble(args)
        bundle.verify_complete(output)
        return output, archive_file

    def small_update(self, base_zip, label, **options):
        output = self.root / label
        with (patch.object(update, '__file__', str(self.repo / 'scripts/build_turnkey_update.py')),
              patch.object(update.subprocess, 'check_output', side_effect=[b'', '1234\n'])):
            return update.build(base_zip, bundle._sha(base_zip), self.business, 'v2026.11.21-' + label,
                                output, self.tools, **options)

    def assert_precompiled_update(self, record, base, label):
        package = Path(record['archive'])
        self.assertTrue(record['stu_engine_included'] and record['shared_bridge_included'])
        with ZipFile(package) as tree:
            update_manifest = json.loads(tree.read('update.json'))
            self.assertIn('payload/engine/business/stu/' + self.stu_name, tree.namelist())
            self.assertIn('payload/engine/bridge/' + self.bridge_id['client_file'], tree.namelist())
            self.assertFalse(any(name.startswith(('payload/runtime/', 'payload/vendor/')) for name in tree.namelist()))
            tree.extractall(self.root / (label + '-extracted'))
        index = json.loads(Path(record['release_index']).read_bytes())
        self.assertEqual(index['source_contract'], update_manifest['source_contract'])
        self.assertEqual(index['source_contract']['stu_engine_source_sha256'], bundle.stu_engine_source_sha256(self.repo))
        applied = self.root / (label + '-applied')
        apply_update(base, self.root / (label + '-extracted'), applied)
        _, metadata = bundle.verify_complete(applied)
        self.assertEqual(bundle.verify_stu_engine(applied, metadata).read_bytes(), (self.stu / self.stu_name).read_bytes())
        for name in ('runtime/python/python.exe', 'vendor/stu/media/Setup.exe', 'vendor/pro/media/Setup.exe'):
            self.assertEqual(bundle._sha(base / name), bundle._sha(applied / name))
        self.assertFalse((applied / 'engine/bridge/legacy-bridge.dll').exists())

    def test_update_with_current_stu_and_bridge_applies_over_the_old_complete_bundle(self):
        base, base_zip = self.complete('base-without-stu', with_stu=False)
        record = self.small_update(base_zip, 'add-stu', stu_engine_build=self.stu, bridge_build=self.bridge)
        self.assert_precompiled_update(record, base, 'add-stu')

    def test_stu_complete_bundle_and_reused_publisher_assets_supply_old_base(self):
        base, _ = self.complete('base-old-pro', with_stu=False)
        current, current_zip = self.complete('base-with-stu', with_stu=True)
        self.assertFalse((current / 'engine/bridge/source').exists())
        record = self.small_update(current_zip, 'reuse-stu')
        self.assert_precompiled_update(record, base, 'reuse-stu')

    def test_legacy_pro_only_update_keeps_source_contract_and_base_bridge(self):
        base, base_zip = self.complete('base-pro', with_stu=False)
        result = self.small_update(base_zip, 'pro-only')
        self.assertFalse(result['stu_engine_included'] or result['shared_bridge_included'])
        with ZipFile(result['archive']) as tree:
            manifest = json.loads(tree.read('update.json'))
            self.assertEqual(set(manifest['source_contract']), set(self.pro_inputs))
            self.assertFalse(any(name.startswith('payload/engine/bridge') for name in tree.namelist()))
            tree.extractall(self.root / 'legacy-extracted')
        applied = self.root / 'legacy-applied'
        apply_update(base, self.root / 'legacy-extracted', applied)
        self.assertEqual((applied / 'engine/bridge/legacy-bridge.dll').read_bytes(), b'base bridge')

    def test_refuses_missing_bridge_and_detects_modified_client_input(self):
        _, base_zip = self.complete('old-base-bridge', with_stu=False)
        with self.assertRaisesRegex(ValueError, 'Stu-enabled update needs --bridge-build'):
            self.small_update(base_zip, 'missing-bridge', stu_engine_build=self.stu)
        write(self.repo, 'assets/pro-native-bridge/portable-bridge/source/PortableClient.cs', b'new own client source')
        with self.assertRaisesRegex(ValueError, 'different shared bridge inputs'):
            shared_bridge_payload(self.repo, read_directory(self.bridge), verify_generated=True)

    def test_rejects_omitted_stu_input_and_tampered_bridge_bytes(self):
        _, base_zip = self.complete('check-pins-base', with_stu=False)
        raw = json.loads((self.stu / STU_MANIFEST).read_bytes())
        raw['sources'].pop()
        dump(self.stu, STU_MANIFEST, raw)
        with self.assertRaisesRegex(ValueError, 'complete current source contract'):
            self.small_update(base_zip, 'omitted-source', stu_engine_build=self.stu, bridge_build=self.bridge)
        write(self.bridge, self.bridge_id['client_file'], b'wrong client')
        with self.assertRaisesRegex(ValueError, 'bridge artifact differs'):
            shared_bridge_payload(self.repo, read_directory(self.bridge), verify_generated=True)


if __name__ == '__main__':
    unittest.main()
