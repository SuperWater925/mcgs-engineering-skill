"""Assemble an unpublished local review bundle from a verified base and current source.

This command does not compile, install, publish or connect to a vendor process.
The source snapshot is identified by its file manifest, never by claiming the
working tree is the current Git commit. Official releases keep their clean-tree
requirement in build_turnkey_update.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from build_turnkey_update import encoded, file_sha, publisher_tools
from check_repository import MANIFEST, file_manifest, package_files
import turnkey_bundle as bundle
from turnkey_delivery import source_contract


def build_candidate(base, engine_build, tools, output, label='local-review', repo=None,
                    stu_engine_build=None, bridge_build=None):
    repo = Path(repo or Path(__file__).resolve().parents[1]).resolve(strict=True)
    base, metadata = bundle.verify_complete(base)
    output = Path(output).resolve()
    engine_build = Path(engine_build).resolve(strict=True)
    stu_engine_build = Path(stu_engine_build).resolve(strict=True) if stu_engine_build else None
    bridge_build = Path(bridge_build).resolve(strict=True) if bridge_build else None
    if output.exists():
        raise ValueError('Use a fresh local candidate output directory: ' + str(output))
    inputs = tuple(path for path in (repo, base, engine_build, stu_engine_build, bridge_build) if path)
    if any(output.is_relative_to(path) or path.is_relative_to(output) for path in inputs):
        raise ValueError('Candidate output must not overlap source, base or engine build')
    files = package_files(repo)
    manifest = file_manifest(repo, files)
    if manifest != bundle._read(repo / MANIFEST):
        raise ValueError('Current source package manifest differs; complete source verification first')
    wanted = source_contract(repo, bundle)
    generated = bundle._read(engine_build / 'release-source-manifest.json')
    if any(generated.get(key) != value for key, value in wanted.items()):
        raise ValueError('Fresh engine build differs from the current source contract')
    engine = bundle._inside(engine_build, generated['engine_file_name'])
    if not engine.is_file():
        raise ValueError('Compile the prepared engine before assembling this local candidate')
    # The source listing identifies the exact generated C# that was compiled.
    for entry in generated['sources']:
        path = bundle._inside(engine_build / 'sources', entry['name'])
        if file_sha(path) != entry['sha256']:
            raise ValueError('Prepared engine source changed: ' + entry['name'])
    tools_payload = publisher_tools(repo, engine_build, tools)
    base_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo, text=True)
    provenance = {'schema': 'mcgs-local-review-bundle/v1', 'local_only': True,
        'release_published': False, 'source_commit': None, 'source_base_commit': base_commit,
        'source_dirty': bool(status.strip()), 'source_worktree_status': status,
        'source_package_sha256': file_sha(repo / MANIFEST),
        'source_package_descriptor_sha256': manifest['descriptor_sha256'],
        'source_contract': wanted, 'engine_sha256': file_sha(engine),
        'engine_build_manifest_sha256': file_sha(engine_build / 'release-source-manifest.json'),
        'publisher_tools_manifest_sha256': hashlib.sha256(tools_payload['tools/publisher-tools-manifest.json']).hexdigest(),
        'base_bundle_sha256': file_sha(base / 'bundle.json'),
        'base_files_sha256': file_sha(base / 'bundle-files.json'),
        'vendor_validation': 'not_performed_by_this_builder'}
    updated = dict(metadata, release=label, release_tag=None, source_commit=None,
                   local_only=True, source_base_commit=base_commit, source_dirty=provenance['source_dirty'],
                   source_package_sha256=provenance['source_package_sha256'])
    engine_relative = metadata['business_engine']
    release_relative = (Path(engine_relative).parent / 'portable-engine-manifest.json').as_posix()
    release = bundle._read(bundle._inside(base, release_relative))
    release.update(wanted, sha256=provenance['engine_sha256'], size=engine.stat().st_size,
                   file=Path(engine_relative).name, local_only=True)
    for key in ('selected_source_count', 'runtime_lookup_counts', 'evidence_layout', 'engine_contract'):
        release[key] = generated[key]
    stu_assets = {}
    if stu_engine_build:
        manifest_path = stu_engine_build / 'stu-engine-manifest.json'
        stu_release = bundle._read(manifest_path)
        filename = stu_release['file']
        if stu_release.get('family') != 'stu' or Path(filename).name != filename or Path(filename).suffix.lower() != '.dll':
            raise ValueError('The Stu engine manifest must identify one own DLL')
        studio = bundle._inside(stu_engine_build, filename)
        if file_sha(studio) != stu_release['sha256'] or not stu_release['sources']:
            raise ValueError('Precompiled Stu engine or source evidence differs')
        for row in stu_release['sources']:
            if file_sha(bundle._inside(repo, row['file'])) != row['sha256']:
                raise ValueError('Stu engine source changed: ' + row['file'])
        stu_root = 'engine/business/stu/'
        stu_relative = stu_root + filename
        if metadata.get('business_engines', {}).get('stu', stu_relative) != stu_relative:
            raise ValueError('The Stu DLL basename must be stable across local bundles')
        stu_assets = {stu_relative: studio.read_bytes(), stu_root + manifest_path.name: manifest_path.read_bytes()}
        updated['business_engines'] = {**metadata.get('business_engines', {}), 'stu': stu_relative}
        provenance['stu_engine_sha256'] = stu_release['sha256']
    bridge_assets = {}
    if bridge_build:
        manifest_path = bridge_build / 'portable-bridge-manifest.json'
        bridge = bundle._read(manifest_path)
        expected_identity = bundle._read(repo / 'assets/pro-native-bridge/portable-bridge/contract.json')
        expected_files = {expected_identity[key] for key in ('bridge_file', 'hook_file', 'client_file')}
        if bridge.get('identity') != expected_identity or {row['file'] for row in bridge['artifacts']} != expected_files:
            raise ValueError('Precompiled shared bridge differs from the repository transport contract')
        bridge_root = metadata['bridge_artifacts'].rstrip('/') + '/'
        for row in bridge['artifacts']:
            path = bundle._inside(bridge_build, row['file'])
            if file_sha(path) != row['sha256']:
                raise ValueError('Precompiled bridge artifact differs: ' + row['file'])
            bridge_assets[bridge_root + row['file']] = path.read_bytes()
        bridge_assets[bridge_root + manifest_path.name] = manifest_path.read_bytes()
        provenance['bridge_manifest_sha256'] = file_sha(manifest_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mcgs-local-candidate-', dir=output.parent) as staging:
        staging = Path(staging)
        target = staging / 'bundle'
        target.mkdir()
        skill_prefix = metadata['skill_directory'].rstrip('/') + '/'
        replacements = {**tools_payload, **stu_assets, **bridge_assets, 'bundle.json': encoded(updated),
            'local-candidate.json': encoded(provenance), release_relative: encoded(release),
            engine_relative: engine.read_bytes(),
            '使用说明.md': (repo / 'references/turnkey-start-zh.md').read_bytes(),
            '第三方许可说明.md': (repo / 'references/turnkey-third-party.md').read_bytes()}
        for entry in bundle._read(base / 'bundle-files.json')['files']:
            name = entry['file']
            if name.startswith(skill_prefix) or name in replacements:
                continue
            dest = bundle._inside(target, name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundle._inside(base, name), dest)
        for name, raw in replacements.items():
            dest = bundle._inside(target, name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        for entry in manifest['files']:
            source = bundle._inside(repo, entry['file'])
            dest = bundle._inside(target, skill_prefix + entry['file'])
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            if file_sha(dest) != entry['sha256']:
                raise ValueError('Source changed while preparing candidate: ' + entry['file'])
        dest_manifest = bundle._inside(target, skill_prefix + MANIFEST)
        dest_manifest.write_bytes((repo / MANIFEST).read_bytes())
        if file_sha(dest_manifest) != provenance['source_package_sha256']:
            raise ValueError('Source package manifest changed while preparing candidate')
        for product in updated.get('products', []):
            index = bundle._inside(target, product['media_manifest'])
            for directory in bundle._read(index).get('directories', []):
                bundle._inside(index.parent / 'media', directory).mkdir(parents=True, exist_ok=True)
        rows = [{'file': path.relative_to(target).as_posix(), 'size': path.stat().st_size, 'sha256': file_sha(path)}
                for path in sorted(target.rglob('*')) if path.is_file()]
        (target / 'bundle-files.json').write_bytes(encoded({'schema': 1, 'files': rows}))
        bundle.verify_complete(target)
        target.rename(output)
    return {'status': 'local_candidate_verified', 'bundle_root': str(output),
            'local_only': True, 'source_commit': None, 'source_base_commit': base_commit,
            'source_dirty': provenance['source_dirty'], 'provenance': str(output / 'local-candidate.json'),
            'files': len(rows), 'project_written': False, 'software_started': False, 'release_published': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, type=Path)
    parser.add_argument('--engine-build', required=True, type=Path)
    parser.add_argument('--tools', required=True, type=Path)
    parser.add_argument('--stu-engine-build', type=Path)
    parser.add_argument('--bridge-build', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--label', default='local-review')
    args = parser.parse_args()
    print(json.dumps(build_candidate(args.base, args.engine_build, args.tools, args.output, args.label,
                                     stu_engine_build=args.stu_engine_build, bridge_build=args.bridge_build), indent=2))
