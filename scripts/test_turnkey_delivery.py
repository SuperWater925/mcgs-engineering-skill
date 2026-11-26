"""Delivery regression fixtures; no compiler, vendor process or project mutation."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid
import zipfile

import apply_turnkey_update as updater
import turnkey
import turnkey_bundle as bundle
import turnkey_delivery as delivery
from build_turnkey_update import publisher_tools
import build_local_candidate as candidate_builder
from check_repository import MANIFEST, file_manifest, package_files
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


class SetupReadinessTests(unittest.TestCase):
    def test_stu_online_requires_its_engine_before_setup_changes_software(self):
        out = io.StringIO()
        argv = ['setup', '--family', 'stu', '--mode', 'online']
        matcher = SimpleNamespace(ensure_matching=Mock(side_effect=bundle.BundleUnavailable('Stu engine is unavailable')))
        with (patch('sys.argv', ['turnkey.py', *argv]),
              patch.object(turnkey, 'bundle', return_value=(Path('fixture'), {})),
              patch.object(turnkey, 'bundle_helper', return_value=bundle),
              patch.object(turnkey, 'load_module', return_value=matcher) as setup, contextlib.redirect_stdout(out)):
            self.assertEqual(turnkey.main(), 2)
        setup.assert_called_once_with('mcgs_turnkey_delivery', turnkey.SKILL / 'scripts/turnkey_delivery.py')
        result = json.loads(out.getvalue())
        self.assertEqual(result['status'], 'unsupported_mode')
        self.assertEqual(result['missing_component'], 'precompiled_stu_business_engine')

    def test_stu_online_fetch_forwards_that_family_without_starting_software(self):
        out = io.StringIO()
        argv = ['fetch-bundle', '--family', 'stu', '--no-download']
        with (patch('sys.argv', ['turnkey.py', *argv]),
              patch.object(turnkey, 'bundle', return_value=(Path('fixture'), {})),
              patch.object(turnkey, 'bundle_helper', return_value=bundle),
              patch.object(turnkey, 'load_module') as modules, contextlib.redirect_stdout(out)):
            match = modules.return_value.ensure_matching
            match.return_value = (Path('matched').resolve(),
                                  {'release': 'with-stu', 'python': 'python.exe', 'powershell': 'pwsh.exe'})
            self.assertEqual(turnkey.main(), 0)
        self.assertEqual(match.call_args.kwargs['family'], 'stu')
        self.assertFalse(match.call_args.kwargs['allow_download'])
        result = json.loads(out.getvalue())
        self.assertEqual(result['family'], 'stu')
        self.assertFalse(result['software_changed'])

    def test_offline_setup_exit_status_tracks_actual_dependency(self):
        for ready in (False, True):
            with self.subTest(ready=ready):
                out = io.StringIO()
                argv = ['setup', '--family', 'stu', '--mode', 'offline', '--no-download']
                installation = SimpleNamespace(setup_bundle=lambda *args, **kwargs: {'editor_ready': True})
                probe = SimpleNamespace(offline_status=lambda **kwargs: {'offline_ready': ready})
                root = Path('fixture')
                info = {'python': 'python.exe', 'powershell': 'pwsh.exe'}
                with (patch('sys.argv', ['turnkey.py', *argv]),
                      patch.object(turnkey, 'bundle', return_value=(root, info)),
                      patch.object(turnkey, 'delegate_to_bundle', return_value=None),
                      patch.object(turnkey, 'load_module', side_effect=[installation, probe]),
                      patch.object(turnkey, 'contained', side_effect=lambda parent, name: parent / name),
                      contextlib.redirect_stdout(out)):
                    self.assertEqual(turnkey.main(), 0 if ready else 2)
                result = json.loads(out.getvalue())
                self.assertIs(result['environment_ready'], ready)
                self.assertFalse(result['mode_selection_required'])


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

    def test_stu_contract_is_independent_of_pro_and_picks_the_matching_bundle(self):
        current = self.skill / 'assets/stu-native'
        (current / 'src').mkdir(parents=True)
        (current / 'profile').mkdir()
        (current / 'src/build-engine.py').write_text('build')
        (current / 'src/Engine.cs').write_text('current design-time engine')
        (current / 'profile/locate.py').write_text('locate')
        (current / 'profile/reference.json').write_text('{}')
        shipped = self.target / 'skill/assets/stu-native'
        shutil.copytree(current, shipped)
        relative = 'engine/stu/fixture.dll'
        asset = self.target / relative
        asset.parent.mkdir()
        asset.write_bytes(b'current stu engine - fixture only')
        source = [{'file': path.relative_to(self.target / 'skill').as_posix(), 'sha256': bundle._sha(path)}
                  for path in sorted(shipped.rglob('*')) if path.is_file()]
        (asset.parent / 'stu-engine-manifest.json').write_bytes(encoded({
            'family': 'stu', 'file': asset.name, 'sha256': bundle._sha(asset), 'sources': source}))
        meta = bundle._read(self.target / 'bundle.json')
        meta['business_engines'] = {'stu': relative}
        (self.target / 'bundle.json').write_bytes(encoded(meta))
        reindex(self.target)
        wanted = delivery.source_contract(self.skill, bundle, family='stu')
        self.assertEqual(delivery.source_contract(self.skill, bundle), self.wanted)
        old_root, old_metadata = bundle._bundle_metadata(self.base)
        self.assertFalse(delivery.matches(old_root, old_metadata, wanted, bundle))
        self.assertTrue(delivery.matches(self.target, meta, wanted, bundle))
        with patch.object(bundle, '_candidate_paths', return_value=[('local', self.target)]):
            chosen, _ = delivery.ensure_matching(self.skill, old_root, old_metadata, bundle,
                                                allow_download=False, family='stu')
        self.assertEqual(chosen, self.target)
        (current / 'profile/reference.json').write_text('{"changed":true}')
        updated = delivery.source_contract(self.skill, bundle, family='stu')
        self.assertNotEqual(updated, wanted)
        self.assertFalse(delivery.matches(self.target, meta, updated, bundle))
        self.assertTrue(delivery.matches(self.target, meta, self.wanted, bundle))
        index = bundle._read(self.index)
        self.assertIsNone(delivery._index(index, wanted, bundle))
        index['source_contract'] = wanted
        self.assertIsNotNone(delivery._index(index, self.wanted, bundle))

    def test_install_keeps_backup_and_staging_outside_scan_root(self):
        scan_root = self.root / '.codex/skills'
        destination = scan_root / 'mcgs-engineering'
        destination.mkdir(parents=True)
        (destination / 'SKILL.md').write_bytes(b'previous skill')
        (self.skill / 'SKILL.md').write_bytes(b'current skill')
        rename = Path.rename
        promoted = []

        def track_promotion(source, target):
            if target == destination:
                self.assertFalse(source.is_relative_to(scan_root))
                self.assertEqual(source.stat().st_dev, scan_root.stat().st_dev)
                promoted.append(source.parent)
            return rename(source, target)

        with patch.object(turnkey, 'SKILL', self.skill), patch.object(turnkey, 'bundle_helper', return_value=bundle), \
             patch.object(turnkey, 'load_module', return_value=delivery), patch.object(Path, 'rename', track_promotion):
            result = turnkey.install_skill(self.target, destination)

        backup = Path(result['previous_backup'])
        self.assertFalse(backup.is_relative_to(scan_root))
        self.assertEqual((backup / 'SKILL.md').read_bytes(), b'previous skill')
        self.assertEqual((destination / 'SKILL.md').read_bytes(), b'current skill')
        self.assertEqual(list(scan_root.rglob('SKILL.md')), [destination / 'SKILL.md'])
        self.assertEqual(len(promoted), 1)
        self.assertFalse(promoted[0].exists())

    def test_install_rejects_a_scan_directory_before_any_migration(self):
        for label, relative in (('child_manifest', 'unrelated-skill/SKILL.md'), ('system', '.system/state.bin')):
            with self.subTest(marker=label):
                scan = self.root / label / 'profile/scan'
                marker = scan / relative
                marker.parent.mkdir(parents=True)
                marker.write_bytes(b'keep unrelated user files')
                (scan / 'notes.txt').write_bytes(b'keep every root file')
                before = {path.relative_to(scan): path.read_bytes() for path in scan.rglob('*') if path.is_file()}
                with (patch.object(turnkey, 'bundle') as find_bundle,
                      patch.object(turnkey, 'migrate_legacy_skill_backups') as migrate,
                      self.assertRaisesRegex(ValueError, 'is a skill scan directory') as error):
                    turnkey.install_skill(self.target, scan)
                self.assertIn(str(scan / 'mcgs-engineering'), str(error.exception))
                find_bundle.assert_not_called()
                migrate.assert_not_called()
                self.assertFalse((scan.parent.parent / '.mcgs-skill-install').exists())
                after = {path.relative_to(scan): path.read_bytes() for path in scan.rglob('*') if path.is_file()}
                self.assertEqual(after, before)

    def test_install_accepts_an_empty_custom_child_destination(self):
        destination = self.root / 'profile/scan/custom-name'
        destination.mkdir(parents=True)
        (self.skill / 'SKILL.md').write_bytes(b'current skill')
        with (patch.object(turnkey, 'SKILL', self.skill), patch.object(turnkey, 'bundle_helper', return_value=bundle),
              patch.object(turnkey, 'load_module', return_value=delivery)):
            result = turnkey.install_skill(self.target, destination)
        self.assertEqual(result['status'], 'skill_installed')
        self.assertEqual((destination / 'SKILL.md').read_bytes(), b'current skill')

    def test_legacy_backups_migrate_only_identified_skill_and_keep_user_files(self):
        scan = self.root / 'profile/skills'
        scan.mkdir(parents=True)
        destination = scan / 'mcgs-engineering'
        legacy = scan / 'mcgs-engineering.backup-20261101-120000-legacy'
        shutil.copytree(self.skill, legacy)
        (legacy / 'SKILL.md').write_text('---\nname: mcgs-engineering\n---\nOld skill\n')
        (legacy / 'scripts/turnkey.py').write_text('old source')
        (legacy / 'user-notes.bin').write_bytes(b'keep every user byte')
        other = scan / 'mcgs-engineering.backup-20261101-120001'
        shutil.copytree(legacy, other)
        (other / 'SKILL.md').write_text('---\nname: unrelated-skill\n---\n')
        transaction = scan.parent / '.mcgs-skill-install'
        transaction.mkdir()
        result = turnkey.migrate_legacy_skill_backups(scan, destination, transaction)
        moved = next(row for row in result if row['status'] == 'migrated')
        self.assertFalse(legacy.exists())
        self.assertTrue(other.exists())
        target = Path(moved['destination'])
        self.assertFalse(target.is_relative_to(scan))
        self.assertEqual((target / 'user-notes.bin').read_bytes(), b'keep every user byte')
        self.assertEqual(bundle._read(Path(moved['receipt'])), moved)
        self.assertEqual(target.stat().st_dev, scan.stat().st_dev)

    def test_legacy_backup_rename_failure_keeps_source_and_prepared_receipt(self):
        scan = self.root / 'skills'
        scan.mkdir()
        legacy = scan / 'mcgs-engineering.backup-20261101-120000'
        shutil.copytree(self.skill, legacy)
        (legacy / 'SKILL.md').write_text('---\nname: mcgs-engineering\n---\n')
        (legacy / 'scripts/turnkey.py').write_text('source')
        transaction = self.root / 'transactions'
        transaction.mkdir()
        with patch.object(Path, 'rename', side_effect=OSError('sharing violation')):
            with self.assertRaisesRegex(ValueError, 'Legacy skill backup migration failed'):
                turnkey.migrate_legacy_skill_backups(scan, scan / 'mcgs-engineering', transaction)
        self.assertTrue(legacy.exists())
        receipt, = transaction.glob('*.migration.json')
        self.assertEqual(bundle._read(receipt)['status'], 'migration_prepared')

    def test_auto_index_skips_corrupt_local_candidate_and_records_path(self):
        bad = self.skill / delivery.INDEX_NAME
        bad.write_text('{ corrupt json')
        cache = self.root / 'cache'
        cache.mkdir()
        shutil.copy2(self.index, cache / delivery.INDEX_NAME)
        self.index.unlink()
        diagnostic = []
        with patch.dict(os.environ, {'MCGS_UPDATE_INDEX': ''}), contextlib.redirect_stderr(io.StringIO()):
            selected = delivery._find_index(self.skill, self.wanted, cache, bundle, False, diagnostic)
        self.assertEqual(selected['index_directory'], str(cache.resolve()))
        self.assertEqual(diagnostic[0]['path'], str(bad.absolute()))
        self.assertFalse(diagnostic[0]['explicit'])

    def test_explicit_bad_or_missing_index_reports_exact_path_without_fallback(self):
        for raw in ('{ broken', None):
            path = self.root / 'explicit-bad.json'
            if raw is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(raw)
            with patch.dict(os.environ, {'MCGS_UPDATE_INDEX': str(path)}):
                with self.assertRaises(ValueError) as error:
                    delivery._find_index(self.skill, self.wanted, self.root / 'cache', bundle, True)
            self.assertIn(str(path.absolute()), str(error.exception))

    def test_unique_running_editor_discovery_and_ambiguous_pid_selection(self):
        editor = self.root / 'McgsSetPro.exe'
        editor.write_bytes(b'fixture')
        first = {'editor': str(editor), 'pid': 10, 'ui_thread': 20, 'creation_filetime': 1}
        second = dict(first, pid=11)
        with patch.object(turnkey, 'processes', return_value=[first]):
            selected, install, target, error = turnkey.online_target()
        self.assertEqual((selected, install, target, error), (editor, self.root, first, None))
        with patch.object(turnkey, 'processes', return_value=[first, second]):
            self.assertEqual(len(turnkey.online_target()[3]['processes']), 2)
            self.assertEqual(turnkey.online_target(pid=11)[2], second)

    def test_unique_installation_is_reported_without_starting_software(self):
        installed = {'family': 'pro', 'editor_executable': str(self.root / 'McgsSetPro.exe')}
        module = SimpleNamespace(discover_installations=lambda: {'installations': [installed]})
        with patch.object(turnkey, 'processes', return_value=[]), patch.object(turnkey, 'load_module', return_value=module), \
                patch.object(turnkey.subprocess, 'run', side_effect=AssertionError('Must not start software')):
            result = turnkey.online_target()[3]
        self.assertEqual(result['selected_installation'], installed)
        self.assertFalse(result['software_started'])

    def test_publisher_tools_require_current_source_and_ship_launcher_bytes(self):
        repo = Path(turnkey.__file__).resolve().parents[1]
        directory = self.root / 'tools'
        directory.mkdir()
        entries = []
        for name, source in [('McgsStart.exe', 'Launcher.cs'), ('InstallerChoice.exe', 'InstallerChoice.cs')]:
            (directory / name).write_bytes(('fresh fixture ' + name).encode())
            relative = 'assets/turnkey-setup/' + source
            entries.append({'file': name, 'source': relative, 'source_sha256': bundle._sha(repo / relative),
                            'sha256': bundle._sha(directory / name)})
        manifest = directory / 'publisher-tools-manifest.json'
        manifest.write_bytes(encoded({'schema': 'mcgs-publisher-tools/v1', 'artifacts': entries}))
        result = publisher_tools(repo, self.root / 'engine', directory)
        self.assertEqual(result['McgsStart.exe'], (directory / 'McgsStart.exe').read_bytes())
        self.assertEqual(result['tools/McgsStart.exe'], result['McgsStart.exe'])
        (directory / 'McgsStart.exe').write_bytes(b'stale')
        with self.assertRaisesRegex(ValueError, 'McgsStart.exe'):
            publisher_tools(repo, self.root / 'engine', directory)

    def test_local_candidate_records_dirty_snapshot_and_replaces_old_launcher(self):
        repo = self.skill
        for name in ('turnkey-start-zh.md', 'turnkey-third-party.md'):
            path = repo / 'references' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture documentation')
        tools = self.root / 'fresh-tools'
        tools.mkdir()
        entries = []
        for name, source in [('McgsStart.exe', 'Launcher.cs'), ('InstallerChoice.exe', 'InstallerChoice.cs')]:
            path = repo / 'assets/turnkey-setup' / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture source ' + source)
            (tools / name).write_bytes(('new binary fixture ' + name).encode())
            entries.append({'file': name, 'source': path.relative_to(repo).as_posix(),
                            'source_sha256': bundle._sha(path), 'sha256': bundle._sha(tools / name)})
        (tools / 'publisher-tools-manifest.json').write_bytes(encoded({'schema': 'mcgs-publisher-tools/v1', 'artifacts': entries}))
        (repo / MANIFEST).write_bytes(encoded(file_manifest(repo, package_files(repo))))
        engine = self.root / 'fresh-engine'
        (engine / 'sources').mkdir(parents=True)
        (engine / 'sources/Fixture.cs').write_text('fixture source')
        (engine / 'business.dll').write_bytes(b'fixture newly compiled engine')
        (engine / 'release-source-manifest.json').write_bytes(encoded({**self.wanted,
            'engine_file_name': 'business.dll', 'selected_source_count': 1, 'runtime_lookup_counts': {},
            'evidence_layout': 'flat-v1', 'engine_contract': 'mcgs-portable-engine/v1',
            'sources': [{'name': 'Fixture.cs', 'sha256': bundle._sha(engine / 'sources/Fixture.cs')}]}))
        (self.target / 'McgsStart.exe').write_bytes(b'old launcher that must not survive')
        reindex(self.target)
        output = self.root / 'local-candidate'
        with patch.object(candidate_builder.subprocess, 'check_output', side_effect=['a' * 40 + '\n', ' M modified.py\n']):
            result = candidate_builder.build_candidate(self.target, engine, tools, output, repo=repo)
        verified, metadata = bundle.verify_complete(output)
        provenance = bundle._read(verified / 'local-candidate.json')
        self.assertTrue(result['local_only'])
        self.assertTrue(metadata['source_dirty'])
        self.assertIsNone(metadata['source_commit'])
        self.assertIsNone(metadata['release_tag'])
        self.assertIsNone(provenance['source_commit'])
        self.assertEqual(provenance['source_base_commit'], 'a' * 40)
        self.assertEqual(provenance['source_package_sha256'], bundle._sha(repo / MANIFEST))
        self.assertEqual((output / 'McgsStart.exe').read_bytes(), (tools / 'McgsStart.exe').read_bytes())
        self.assertEqual((output / 'tools/McgsStart.exe').read_bytes(), (tools / 'McgsStart.exe').read_bytes())
        self.assertTrue(delivery.matches(output, metadata, self.wanted, bundle))

    @unittest.skipUnless(os.name == 'nt' and shutil.which('pwsh'), 'Windows PowerShell entry fixture')
    def test_source_entry_bootstraps_explicit_bundle_before_python(self):
        repo = Path(turnkey.__file__).resolve().parents[1]
        directory = self.root / 'runtime bundle'
        directory.mkdir()
        fake = directory / 'python.cmd'
        fake.write_text('@echo off\r\necho bundle-runtime-selected\r\nexit /b 23\r\n', encoding='ascii')
        pwsh = shutil.which('pwsh')
        (directory / 'pwsh.exe').write_bytes(b'not executed by this PowerShell 7 fixture')
        (directory / 'bundle.json').write_bytes(encoded({'schema': 'mcgs-turnkey-bundle/v1',
            'python': 'python.cmd', 'powershell': 'pwsh.exe'}))
        env = os.environ.copy()
        env.update(PATH='', MCGS_BUNDLE_ROOT='', MCGS_PYTHON='', MCGS_PWSH='', LOCALAPPDATA=str(self.root / 'no-pointer'))
        for arguments in [
                ['turnkey', '--bundle-root', str(directory), 'verify'],
                ['turnkey', 'verify', '--bundle-root', str(directory)],
                ['turnkey', 'verify', '--bundle-root=' + str(directory)]]:
            result = subprocess.run([pwsh, '-NoProfile', '-File', str(repo / 'run.ps1'), *arguments],
                                    env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 23, repr(arguments) + '\n' + result.stderr)
            self.assertIn('bundle-runtime-selected', result.stdout)

    def test_shared_entry_preserves_named_database_parameters_and_exit(self):
        repo = Path(turnkey.__file__).resolve().parents[1]
        target = self.root / 'offline entry'
        (target / 'scripts').mkdir(parents=True)
        shutil.copy2(repo / 'run.ps1', target / 'run.ps1')
        (target / 'scripts/stu_project.ps1').write_text(
            "param([string]$Command,[string]$Project,[string]$Out,[switch]$Commit)\n"
            "[pscustomobject]@{command=$Command;project=$Project;out=$Out;commit=$Commit.IsPresent} | ConvertTo-Json\n"
            "exit 24\n", encoding='utf-8')
        env = os.environ.copy()
        env.update(MCGS_BUNDLE_ROOT='', LOCALAPPDATA=str(self.root / 'no-pointer'))
        project = str(self.root / 'test project.mcs')
        output = str(self.root / 'new output.mcs')
        result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-File', str(target / 'run.ps1'),
                                 'apply', '-Project', project, '-Out', output, '-Commit'],
                                env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 24, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'command': 'apply', 'project': project,
                                                     'out': output, 'commit': True})

    def test_failed_skill_promotion_restores_previous_skill(self):
        scan_root = self.root / '.codex/skills'
        destination = scan_root / 'mcgs-engineering'
        destination.mkdir(parents=True)
        (destination / 'SKILL.md').write_bytes(b'previous skill')
        rename = Path.rename

        def fail_promotion(source, target):
            if source.name == 'skill' and target == destination:
                raise OSError('injected promotion failure')
            return rename(source, target)

        with patch.object(turnkey, 'SKILL', self.skill), patch.object(turnkey, 'bundle_helper', return_value=bundle), \
             patch.object(turnkey, 'load_module', return_value=delivery), patch.object(Path, 'rename', fail_promotion):
            with self.assertRaisesRegex(OSError, 'injected promotion failure'):
                turnkey.install_skill(self.target, destination)

        self.assertEqual((destination / 'SKILL.md').read_bytes(), b'previous skill')
        self.assertEqual(list(scan_root.rglob('SKILL.md')), [destination / 'SKILL.md'])
        self.assertEqual(list((scan_root.parent / '.mcgs-skill-install').iterdir()), [])

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

    def test_live_reuse_tracks_binding_inputs_and_queue_identity_with_same_engine(self):
        original_asset = turnkey.SKILL / 'assets/pro-native-bridge'
        asset = self.skill / 'assets/pro-native-bridge'
        for directory in ('abi-adapter', 'portable-engine'):
            shutil.copytree(original_asset / directory, asset / directory,
                            ignore=shutil.ignore_patterns('__pycache__'), dirs_exist_ok=True)
        for relative in ('delivery/bind_common_delivery.v5.py', 'delivery/delivery_file_support.py',
                         'delivery/device-entry-v2/native_delivery_config.py', 'transport/bridge_client.py'):
            file = asset / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original_asset / relative, file)
        support = turnkey.load_module('test_online_topology', asset / 'portable-engine/portable_support.py')
        task = self.root / 'connection'
        runtime, bootstrap = task / 'rt', task / 'boot'
        runtime.mkdir(parents=True)
        engines = bootstrap / 'engines'
        engines.mkdir(parents=True)
        actual = {'task_root': str(task), 'runtime_root': str(runtime), 'install_root': str(self.root),
                  'editor_executable': str(self.root / 'McgsSetPro.exe')}
        info = bundle._read(self.target / 'bundle.json')
        release_engine = self.target / info['business_engine']
        engine_sha = bundle._sha(release_engine)
        old_transport = runtime / 'bridge_client.py'
        shutil.copy2(asset / 'transport/bridge_client.py', old_transport)
        active = runtime / 'active-engine.json'
        calls = []

        def materialized_scope(current, scope_file, recorded_inputs):
            scope = dict(current)
            engineering = Path(scope['engineering_root'])
            evidence = engineering / 'task-evidence'
            evidence.mkdir(parents=True)
            index = evidence / 'abi-target-profile-index.json'
            index.write_bytes(b'{}')
            binding = engineering / 'portable-engine-binding.json'
            binding.write_bytes(encoded({**self.wanted, 'schema': support.BINDING_SCHEMA,
                                         'engine_contract': support.CONTRACT, 'profile_index_file': str(index),
                                         'profile_index_sha256': bundle._sha(index),
                                         **({'preparation_input_sha256': recorded_inputs} if recorded_inputs else {})}))
            scope.update(portable_engine_contract=support.CONTRACT, portable_binding_file=str(binding),
                         portable_binding_sha256=bundle._sha(binding))
            scope_file.write_bytes(encoded(scope))
            return scope_file

        def select_scope(scope_file):
            assembly = scope_file.with_name(scope_file.name.removesuffix('.scope.json') + '.dll')
            shutil.copy2(release_engine, assembly)
            selection = {'assembly': str(assembly), 'sha256': engine_sha,
                         'engine_scope_sha256': bundle._sha(scope_file)}
            active.write_bytes(encoded(selection))

        def fake_preparation(argv, env, timeout=None):
            def option(name):
                return Path(argv[argv.index(name) + 1])
            method = Path(argv[1]).name
            calls.append(method)
            if method == 'materialize.py':
                scope = bundle._read(option('--scope-base-json'))
                self.assertEqual(Path(scope['transport_client_file']).parent, runtime)
                scope_file = materialized_scope(scope, engines / ('mock-' + str(len(calls)) + '.scope.json'),
                                                support.preparation_input_sha256())
                return {'engine_file': str(scope_file.with_suffix('.dll')), 'engine_scope_file': str(scope_file),
                        'scope_sha256': bundle._sha(scope_file)}
            self.assertEqual(method, 'select_engine.py')
            self.assertEqual(option('--bootstrap-root'), bootstrap)
            self.assertEqual(str(option('--engine-sha256')), engine_sha)
            select_scope(option('--engine-scope-file'))
            return {'selected': True}

        select_scope(materialized_scope(dict(actual, schema=1, engineering_root=str(task / 'old'),
                                            transport_client_file=str(old_transport),
                                            transport_client_sha256=bundle._sha(old_transport)),
                                       engines / 'old.scope.json', None))
        with patch.object(turnkey, 'SKILL', self.skill), patch.object(turnkey, 'run_json', side_effect=fake_preparation):
            def reconnect():
                calls.clear()
                result = turnkey.select_current_engine(self.target, info, actual, bootstrap,
                                                       bundle._read(active), {'MCGS_PYTHON': 'fixture-python'})
                expected = ['materialize.py', 'select_engine.py'] if result['changed'] else []
                self.assertEqual(calls, expected)
                self.assertEqual(result['active_engine']['sha256'], engine_sha)
                return result['changed']

            self.assertTrue(reconnect())  # Compatible old receipt gets one refreshed binding.
            self.assertFalse(reconnect())
            for relative in ('abi-adapter/catalogs/reference.json.gz', 'abi-adapter/layout_adaptation.py',
                             'transport/bridge_client.py'):
                file = asset / relative
                file.write_bytes(file.read_bytes() + b'fixture updated input')
                self.assertTrue(reconnect(), relative)
                self.assertFalse(reconnect(), relative)
        self.assertTrue(old_transport.is_file())

    def test_queue_liveness_correlates_selected_scope_and_runtime_pid(self):
        transport = self.root / 'bridge_client.py'
        transport.touch()
        expected = {'process_id': 41, 'engine_sha256': 'engine',
                    'engineering_delivery_scope_sha256': 'current_scope', 'bridge_bootstrap_scope_sha256': 'bridge'}
        reply = dict(expected, op='ping', ok=True)
        with patch.object(turnkey, 'run_json', side_effect=lambda argv, **kwargs: dict(reply, request_id=argv[-3])):
            self.assertTrue(turnkey.probe_queue(self.root, 'fixture-python', expected=expected)['verified'])
            reply.update(process_id=42, engineering_delivery_scope_sha256='old_scope')
            result = turnkey.probe_queue(self.root, 'fixture-python', expected=expected)
            self.assertFalse(result['verified'])
            self.assertEqual(result['identity_mismatches'], ['process_id', 'engineering_delivery_scope_sha256'])

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
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case)
                               for case in (SetupReadinessTests, DeliveryTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'tests_run': result.testsRun, 'passed': result.wasSuccessful(),
              'failures': len(result.failures), 'errors': len(result.errors),
              'vendor_software_executed': False, 'compiler_executed': False}
    (WORK / 'test-result.json').write_bytes(encoded(report))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
