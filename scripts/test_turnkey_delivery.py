"""Delivery regression fixtures; no compiler, vendor process or project mutation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid
import zipfile

import apply_turnkey_update as updater
import turnkey
import turnkey_bundle as bundle
import turnkey_delivery as delivery
from test_turnkey_bundle import make_bundle

WORK = None


def encoded(value):
    return (json.dumps(value, sort_keys=True) + '\n').encode()


def row(name, raw):
    return {'file': name, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def reindex(root):
    rows = [row(path.relative_to(root).as_posix(), path.read_bytes()) for path in root.rglob('*')
            if path.is_file() and path.name != 'bundle-files.json']
    (root / 'bundle-files.json').write_bytes(encoded({'schema': 1, 'files': rows}))


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.root = WORK / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.skill = self.root / 'skill'
        self.skill.mkdir()
        for key, relative in delivery.CONTRACT_PATHS.items():
            path = self.skill / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('current-' + key)
        (self.skill / 'scripts').mkdir()
        shutil.copy2(Path(updater.__file__), self.skill / 'scripts/apply_turnkey_update.py')
        self.wanted = delivery.source_contract(self.skill, bundle)
        self.base = make_bundle(self.root / 'base')
        self.target = make_bundle(self.root / 'target')
        info = bundle._read(self.target / 'bundle.json')
        info['release'] = 'new-fixture-release'
        (self.target / 'bundle.json').write_bytes(encoded(info))
        (self.target / 'engine/business.dll').write_bytes(b'current engine - fixture only')
        (self.target / 'engine/portable-engine-manifest.json').write_bytes(encoded({
            **self.wanted, 'sha256': bundle._sha(self.target / 'engine/business.dll')}))
        (self.target / 'skill/SKILL.md').write_text('new skill')
        reindex(self.target)
        self.patch = self.root / 'patch'
        payload = self.patch / 'payload'
        payload.mkdir(parents=True)
        names = ['bundle.json', 'bundle-files.json', 'engine/business.dll',
                 'engine/portable-engine-manifest.json', 'skill/SKILL.md']
        for name in names:
            path = payload / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.target / name, path)
        update = {'schema': updater.SCHEMA, 'base_bundle_sha256': bundle._sha(self.base / 'bundle.json'),
                  'base_files_sha256': bundle._sha(self.base / 'bundle-files.json'),
                  'target_files_sha256': bundle._sha(self.target / 'bundle-files.json'),
                  'target_release': info['release'], 'source_contract': self.wanted,
                  'payload': [row(name, (payload / name).read_bytes()) for name in names]}
        (self.patch / 'update.json').write_bytes(encoded(update))
        self.archive = self.root / 'update.zip'
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for path in self.patch.rglob('*'):
                if path.is_file():
                    archive.write(path, path.relative_to(self.patch).as_posix())
        spec = {'file': self.archive.name, 'size': self.archive.stat().st_size,
                'sha256': bundle._sha(self.archive), 'url': 'https://example.invalid/update.zip'}
        self.index = self.root / delivery.INDEX_NAME
        self.index.write_bytes(encoded({'schema': delivery.INDEX_SCHEMA, 'release_tag': 'v-fixture',
                                       'source_contract': self.wanted, 'update': spec}))
        self.env = patch.dict(os.environ, {'LOCALAPPDATA': str(self.root / 'local'),
            'MCGS_UPDATE_INDEX': str(self.index), 'MCGS_UPDATE_ARCHIVE': str(self.archive),
            'MCGS_BUNDLE_ROOT': '', 'MCGS_BUNDLE_ARCHIVE': ''})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_update_reuses_previous_release_with_different_metadata(self):
        metadata = bundle._read(self.base / 'bundle.json')
        metadata['release'] = 'previous-update-not-original-base'
        (self.base / 'bundle.json').write_bytes(encoded(metadata))
        (self.base / 'skill/SKILL.md').write_text('previous update')
        reindex(self.base)
        result = updater.apply_update(self.base, self.patch, self.root / 'received')
        self.assertFalse(result['base_modified'])
        root, info = bundle.verify_complete(self.root / 'received')
        self.assertTrue(delivery.matches(root, info, self.wanted, bundle))
        self.assertEqual(metadata, bundle._read(self.base / 'bundle.json'))

    def test_corrupt_reused_runtime_is_rejected_before_publication(self):
        (self.base / 'runtime/python/python.exe').write_bytes(b'wrong runtime')
        with self.assertRaisesRegex(ValueError, 'runtime/python/python.exe'):
            updater.apply_update(self.base, self.patch, self.root / 'received')
        self.assertFalse((self.root / 'received').exists())

    def test_local_index_automatically_upgrades_without_network_or_compilation(self):
        with patch.object(bundle, '_url', side_effect=AssertionError('Network is disabled')):
            root, info = delivery.ensure_matching(self.skill, self.base, bundle._read(self.base / 'bundle.json'),
                                                  bundle, allow_download=False, cache_dir=self.root / 'cache')
        self.assertTrue(delivery.matches(root, info, self.wanted, bundle))
        self.assertNotEqual(root, self.base)
        self.assertEqual((self.base / 'skill/SKILL.md').read_bytes(), b'fixture only, never execute: skill/SKILL.md')

    def test_new_cached_bundle_wins_over_stale_pointer_without_network(self):
        cache = self.root / 'cache'
        bundle._remember(self.target, bundle._read(self.target / 'bundle.json'), cache)
        (self.skill / 'turnkey-location.json').write_bytes(encoded({'bundle_root': str(self.base)}))
        with patch.object(bundle, '_url', side_effect=AssertionError('Network is disabled')):
            root, unused = delivery.ensure_matching(self.skill, self.base, bundle._read(self.base / 'bundle.json'),
                                                    bundle, cache_dir=cache)
        self.assertEqual(root, self.target)

    def test_unavailable_update_preserves_current_skill_instead_of_downgrading(self):
        self.index.write_bytes(encoded({'schema': delivery.INDEX_SCHEMA, 'source_contract': {}}))
        with self.assertRaises(bundle.BundleUnavailable) as error:
            delivery.ensure_matching(self.skill, self.base, bundle._read(self.base / 'bundle.json'),
                                      bundle, allow_download=False, cache_dir=self.root / 'cache')
        self.assertTrue(error.exception.report['current_skill_preserved'])
        self.assertFalse(error.exception.report['source_engine_rebuild_required'])

    def test_runtime_delegate_keeps_current_script_and_download_policy(self):
        args = argparse.Namespace(command='verify', full=False, no_download=True, cache_dir=str(self.root / 'cache'))
        with patch.object(turnkey.subprocess, 'run') as run:
            run.return_value.returncode = 0
            turnkey.delegate_to_bundle(self.base, bundle._read(self.base / 'bundle.json'), args)
        command = run.call_args.args[0]
        self.assertIn(str(Path(turnkey.__file__).resolve()), command)
        self.assertIn('--no-download', command)
        self.assertNotIn(str(self.base / 'skill/scripts/turnkey.py'), command)

    def test_existing_bridge_selection_preserves_queue_and_old_transport(self):
        task = self.root / 'connection'
        runtime, bootstrap = task / 'rt', task / 'boot'
        runtime.mkdir(parents=True)
        engines = bootstrap / 'engines'
        engines.mkdir(parents=True)
        old_scope = engines / 'old.scope.json'
        old_scope.write_text('{}')
        untouched_transport = runtime / 'bridge_client.py'
        untouched_transport.write_text('older transport')
        original = {'assembly': str(old_scope.with_suffix('.dll')), 'sha256': 'old'}
        selection = runtime / 'active-engine.json'
        selection.write_bytes(encoded(original))
        actual = {'task_root': str(task), 'runtime_root': str(runtime), 'install_root': str(self.root),
                  'editor_executable': str(self.root / 'McgsSetPro.exe')}
        prepared = {}

        def mocked_subprocess(argv, env, timeout=None):
            def option(name):
                return Path(argv[argv.index(name) + 1])
            if Path(argv[1]).name == 'materialize.py':
                scope = bundle._read(option('--scope-base-json'))
                transport = Path(scope['transport_client_file'])
                self.assertEqual(transport.parent, runtime)
                self.assertNotEqual(transport, untouched_transport)
                self.assertEqual(bundle._sha(transport), scope['transport_client_sha256'])
                self.assertTrue(option('--output-directory').is_relative_to(runtime))
                self.assertFalse(Path(scope['engineering_root']).is_relative_to(runtime))
                prepared.update(engine_file=str(engines / 'new.dll'), engine_scope_file=str(engines / 'new.scope.json'))
                Path(prepared['engine_scope_file']).write_bytes(encoded(scope))
                prepared['scope_sha256'] = bundle._sha(Path(prepared['engine_scope_file']))
                return prepared
            self.assertEqual(Path(argv[1]).name, 'select_engine.py')
            selection.write_bytes(encoded({'assembly': prepared['engine_file'], 'sha256': argv[argv.index('--engine-sha256') + 1]}))
            return {'selected': True}

        with patch.object(turnkey, 'run_json', side_effect=mocked_subprocess):
            result = turnkey.select_current_engine(self.target, bundle._read(self.target / 'bundle.json'),
                                                   actual, bootstrap, original, {'MCGS_PYTHON': 'fixture-python'})
        self.assertTrue(result['changed'])
        self.assertEqual(result['scope_config'], prepared['engine_scope_file'])
        self.assertEqual(untouched_transport.read_text(), 'older transport')

    def test_flat_and_program_installation_roots(self):
        self.assertEqual(turnkey.installation_root_from_editor(self.root / 'McgsSetPro.exe'), self.root)
        self.assertEqual(turnkey.installation_root_from_editor(self.root / 'PrOgRaM' / 'McgsSetPro.exe'), self.root)

    def test_patch_path_traversal_rejected_before_extraction(self):
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('../outside', b'bad')
        out = self.root / 'extraction'
        out.mkdir()
        with self.assertRaises(ValueError):
            delivery._extract_update(archive, out, bundle)
        self.assertEqual(list(out.iterdir()), [])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    WORK = args.work.resolve()
    WORK.mkdir(parents=True, exist_ok=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DeliveryTests))
    report = {'tests_run': result.testsRun, 'passed': result.wasSuccessful(),
              'failures': len(result.failures), 'errors': len(result.errors),
              'vendor_software_executed': False, 'compiler_executed': False}
    (WORK / 'test-result.json').write_bytes(encoded(report))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
