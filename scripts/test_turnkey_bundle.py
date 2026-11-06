"""File/network fixtures for complete-bundle bootstrap; never starts vendor code."""
import argparse
from contextlib import contextmanager
import hashlib
import http.server
import json
import os
from pathlib import Path
import stat
import threading
import unittest
from unittest.mock import patch
import uuid
import zipfile

import turnkey_bundle as boot

WORK = None


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def make_bundle(root):
    root.mkdir(parents=True)
    files = ['runtime/python/python.exe', 'runtime/pwsh/pwsh.exe', 'engine/business.dll',
             'tools/choice.exe', 'engine/bridge/bridge.dll', 'skill/SKILL.md']
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('fixture only, never execute: ' + name).encode())
    (root / 'empty-media-directory').mkdir()
    metadata = {'schema': boot.SCHEMA, 'release': 'fixture-release', 'python': files[0],
        'powershell': files[1], 'business_engine': files[2], 'choice_helper': files[3],
        'bridge_artifacts': 'engine/bridge', 'skill_directory': 'skill', 'products': []}
    (root / 'bundle.json').write_text(json.dumps(metadata), encoding='utf-8')
    rows = [{'file': path.relative_to(root).as_posix(), 'size': path.stat().st_size, 'sha256': digest(path)}
            for path in root.rglob('*') if path.is_file()]
    (root / 'bundle-files.json').write_text(json.dumps({'schema': 1, 'files': rows}), encoding='utf-8')
    return root


def pack(root, output):
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob('*')):
            archive.write(path, 'mcgs-engineering-turnkey/' + path.relative_to(root).as_posix())
    return {'tag': 'fixture-release', 'file': output.name, 'size': output.stat().st_size,
            'sha256': digest(output), 'url': output.as_uri()}


@contextmanager
def serve(data, range_enabled=True):
    class Handler(http.server.BaseHTTPRequestHandler):
        requests = []
        def log_message(self, *args):
            pass
        def do_GET(self):
            requested = self.headers.get('Range')
            self.requests.append(requested)
            start = int(requested[6:-1]) if requested and range_enabled else 0
            self.send_response(206 if start else 200)
            self.send_header('Content-Length', str(len(data) - start))
            if start:
                self.send_header('Content-Range', f'bytes {start}-{len(data)-1}/{len(data)}')
            self.end_headers()
            self.wfile.write(data[start:])
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port) + '/fixture.zip', Handler.requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.root = WORK / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.cache = self.root / 'cache'
        self.skill = self.root / '.workbuddy/skills/mcgs-engineering'
        self.skill.mkdir(parents=True)
        self.env = patch.dict(os.environ, {'LOCALAPPDATA': str(self.root / 'local'),
            'MCGS_BUNDLE_ROOT': '', 'MCGS_BUNDLE_ARCHIVE': ''})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_source_only_reports_recovery_without_file_not_found(self):
        with self.assertRaises(boot.BundleUnavailable) as result:
            boot.resolve(self.skill, cache_dir=self.cache)
        self.assertEqual(result.exception.report['status'], 'complete_bundle_unavailable')
        self.assertFalse(result.exception.report['software_reinstallation_required'])
        self.assertIn('fetch-bundle', result.exception.report['recovery_command'])
        self.assertFalse(self.cache.exists())

    def test_explicit_invalid_directory_does_not_silently_choose_another(self):
        os.environ['MCGS_BUNDLE_ROOT'] = str(make_bundle(self.root / 'valid'))
        with self.assertRaises(boot.BundleUnavailable) as result:
            boot.resolve(self.skill, explicit_root=self.root / 'missing', cache_dir=self.cache)
        self.assertIn('explicit_root', result.exception.report)

    def test_environment_and_arbitrary_skill_folder_find_complete_bundle(self):
        bundle = make_bundle(self.root / 'valid')
        os.environ['MCGS_BUNDLE_ROOT'] = str(bundle)
        self.assertEqual(boot.resolve(self.skill, cache_dir=self.cache)[0], bundle)
        os.environ['MCGS_BUNDLE_ROOT'] = ''
        self.assertEqual(boot.resolve(bundle / 'skill', cache_dir=self.cache)[0], bundle)

    def test_stale_automatic_pointers_recover_to_shared_cache(self):
        os.environ['MCGS_BUNDLE_ROOT'] = str(self.root / 'gone-env')
        (self.skill / 'turnkey-location.json').write_text(json.dumps({'bundle_root': str(self.root / 'gone-skill')}))
        bundle = make_bundle(self.root / 'valid')
        boot._write(self.cache / 'current.json', {'bundle_root': str(bundle)})
        self.assertEqual(boot.resolve(self.skill, cache_dir=self.cache)[0], bundle)

    def test_local_archive_fetch_verified_and_empty_directory_preserved(self):
        source = make_bundle(self.root / 'source')
        archive = self.root / 'fixture.zip'
        spec = pack(source, archive)
        os.environ['MCGS_BUNDLE_ARCHIVE'] = str(archive)
        with patch.object(boot, '_release_info', return_value=spec), patch.object(boot, '_url', side_effect=AssertionError('Network must not be needed')):
            root, metadata = boot.fetch(self.skill, cache_dir=self.cache)
        self.assertTrue((root / 'empty-media-directory').is_dir())
        self.assertEqual(metadata['release'], 'fixture-release')
        self.assertEqual(boot._read(self.cache / 'fetch-state.json')['phase'], 'ready')
        self.assertEqual(boot.resolve(self.skill, cache_dir=self.cache)[0], root)
        self.assertEqual(boot.resolve(self.skill)[0], root)
        self.assertEqual(boot._read(boot.default_cache() / 'current.json')['bundle_root'], str(root))

    def test_existing_custom_cache_registers_default_discovery_without_network(self):
        bundle = make_bundle(self.root / 'valid')
        boot._write(self.cache / 'current.json', {'bundle_root': str(bundle), 'archive_sha256': 'a' * 64})
        with patch.object(boot, '_url', side_effect=AssertionError('No network for cached bundle')):
            self.assertEqual(boot.fetch(self.skill, cache_dir=self.cache)[0], bundle)
        pointer = boot._read(boot.default_cache() / 'current.json')
        self.assertEqual(pointer['bundle_root'], str(bundle))
        self.assertEqual(pointer['archive_sha256'], 'a' * 64)

    def test_actual_http_fetch_verifies_archive_and_reuses_without_network(self):
        archive = self.root / 'fixture.zip'
        spec = pack(make_bundle(self.root / 'source'), archive)
        with serve(archive.read_bytes()) as (url, requests):
            spec['url'] = url
            with patch.object(boot, '_release_info', return_value=spec):
                root, unused = boot.fetch(self.skill, cache_dir=self.cache)
        self.assertEqual(len(requests), 1)
        with patch.object(boot, '_url', side_effect=AssertionError('Cached discovery must not network')):
            self.assertEqual(boot.fetch(self.skill, cache_dir=self.cache)[0], root)

    def test_partial_download_resumes_precise_range(self):
        archive = self.root / 'fixture.zip'
        spec = pack(make_bundle(self.root / 'source'), archive)
        data = archive.read_bytes()
        self.cache.mkdir()
        downloads = self.cache / 'downloads'
        downloads.mkdir()
        final = downloads / (spec['sha256'][:16] + '-' + spec['file'])
        partial = final.with_suffix('.zip.part')
        partial.write_bytes(data[:100])
        with serve(data) as (url, requests):
            spec['url'] = url
            boot._write(final.with_suffix('.zip.download.json'), {**spec, 'partial_file': str(partial)})
            result = boot._download(spec, self.cache)
        self.assertEqual(requests, ['bytes=100-'])
        self.assertEqual(digest(result), spec['sha256'])

    def test_range_ignored_does_not_append_full_archive_to_partial(self):
        archive = self.root / 'fixture.zip'
        spec = pack(make_bundle(self.root / 'source'), archive)
        data = archive.read_bytes()
        self.cache.mkdir()
        downloads = self.cache / 'downloads'
        downloads.mkdir()
        final = downloads / (spec['sha256'][:16] + '-' + spec['file'])
        partial = final.with_suffix('.zip.part')
        partial.write_bytes(data[:100])
        with serve(data, range_enabled=False) as (url, requests):
            spec['url'] = url
            boot._write(final.with_suffix('.zip.download.json'), {**spec, 'partial_file': str(partial)})
            result = boot._download(spec, self.cache)
        self.assertEqual(partial.read_bytes(), data[:100])
        self.assertEqual(digest(result), spec['sha256'])

    def test_bad_download_does_not_publish_ready_pointer(self):
        archive = self.root / 'fixture.zip'
        spec = pack(make_bundle(self.root / 'source'), archive)
        with serve(b'not the declared archive') as (url, unused):
            spec['url'] = url
            with patch.object(boot, '_release_info', return_value=spec), self.assertRaises(boot.BundleUnavailable):
                boot.fetch(self.skill, cache_dir=self.cache)
        self.assertFalse((self.cache / 'current.json').exists())
        self.assertTrue(list((self.cache / 'downloads').glob('*.part')))

    def test_full_bad_partial_can_recover_without_deleting_previous_bytes(self):
        archive = self.root / 'fixture.zip'
        spec = pack(make_bundle(self.root / 'source'), archive)
        data = archive.read_bytes()
        self.cache.mkdir()
        downloads = self.cache / 'downloads'
        downloads.mkdir()
        final = downloads / (spec['sha256'][:16] + '-' + spec['file'])
        partial = final.with_suffix('.zip.part')
        partial.write_bytes(b'x' * len(data))
        with serve(data) as (url, requests):
            spec['url'] = url
            boot._write(final.with_suffix('.zip.download.json'), {**spec, 'partial_file': str(partial)})
            result = boot._download(spec, self.cache)
        self.assertEqual(requests, [None])
        self.assertEqual(partial.read_bytes(), b'x' * len(data))
        self.assertEqual(digest(result), spec['sha256'])

    def test_manifest_file_tamper_is_detected(self):
        bundle = make_bundle(self.root / 'source')
        (bundle / 'engine/business.dll').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            boot.verify_complete(bundle)

    def test_unsafe_archive_paths_rejected_before_extraction(self):
        for index, name in enumerate(['../outside', '/absolute', 'C:/drive', 'root/../up',
                                      'root/CON.txt', 'root/trailing.', 'root/a\\b', 'root/file:stream']):
            archive = self.root / f'unsafe-{index}.zip'
            with zipfile.ZipFile(archive, 'x') as z:
                info = zipfile.ZipInfo('placeholder')
                info.filename = name  # Preserve raw backslashes on Windows too.
                z.writestr(info, b'bad')
            staging = self.root / f'staging-{index}'
            staging.mkdir()
            with self.assertRaises(ValueError):
                boot._extract(archive, staging)
            self.assertEqual(list(staging.iterdir()), [])

    def test_archive_alias_and_link_rejected(self):
        archive = self.root / 'alias.zip'
        with zipfile.ZipFile(archive, 'x') as z:
            z.writestr('root/A/file', b'a')
            z.writestr('root/a/other', b'b')
        staging = self.root / 'staging'
        staging.mkdir()
        with self.assertRaises(ValueError):
            boot._extract(archive, staging)
        link = self.root / 'link.zip'
        with zipfile.ZipFile(link, 'x') as z:
            info = zipfile.ZipInfo('root/link')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, 'target')
        with self.assertRaises(ValueError):
            boot._extract(link, staging)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    WORK = args.work.resolve()
    WORK.mkdir(parents=True, exist_ok=True)
    # Artifacts stay in the explicit test workspace; no cleanup touches software
    # installations, user projects, prior claims, downloads or old preparation.
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BootstrapTests))
    report = {'tests_run': result.testsRun, 'passed': result.wasSuccessful(),
              'failures': len(result.failures), 'errors': len(result.errors),
              'vendor_software_executed': False, 'compiler_executed': False}
    (WORK / 'test-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
