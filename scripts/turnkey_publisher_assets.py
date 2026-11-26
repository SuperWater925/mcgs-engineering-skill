"""Verify explicitly supplied precompiled Stu and shared bridge publisher assets."""

import hashlib
import json
from pathlib import Path

import turnkey_bundle as bundle


STU_MANIFEST = 'stu-engine-manifest.json'
BRIDGE_MANIFEST = 'portable-bridge-manifest.json'
BRIDGE_ROOT = 'assets/pro-native-bridge'
BRIDGE_CONTRACT = f'{BRIDGE_ROOT}/portable-bridge/contract.json'
BOOTSTRAP_SOURCES = ('Bootstrap.cs', 'BootstrapLayout.cs', 'DurableQueuePump.cs',
                     'EngineLoader.cs', 'NullSafeDispatch.cs')
BRIDGE_SOURCE_FILES = (
    BRIDGE_CONTRACT,
    f'{BRIDGE_ROOT}/portable-bridge/build.py',
    f'{BRIDGE_ROOT}/portable-bridge/build_hook.py',
    f'{BRIDGE_ROOT}/portable-bridge/source/PortableClient.cs',
    f'{BRIDGE_ROOT}/portable-bridge/source/PortableEntry.cs',
    f'{BRIDGE_ROOT}/bootstrap/build_native_wrapper.py',
    *(f'{BRIDGE_ROOT}/bootstrap/source/{name}' for name in BOOTSTRAP_SOURCES),
)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def read_directory(directory):
    root = Path(directory).resolve(strict=True)
    return lambda name: bundle._inside(root, name).read_bytes()


def bridge_source_inputs(skill):
    return [{'file': name, 'sha256': sha256(bundle._inside(skill, name).read_bytes())}
            for name in sorted(BRIDGE_SOURCE_FILES)]


def source_rows(manifest, field, *, windows_paths=False):
    entries = manifest.get(field)
    if not isinstance(entries, list) or not entries:
        raise ValueError(f'Publisher manifest is missing {field}')
    result = {}
    for row in entries:
        if not isinstance(row, dict) or not isinstance(row.get('file'), str) or not isinstance(row.get('sha256'), str):
            raise ValueError(f'Publisher manifest has an invalid {field} row')
        name = row['file'].replace('\\', '/') if windows_paths else row['file']
        parts = bundle._relative(name)
        if '/'.join(parts) != name or name in result:
            raise ValueError(f'Invalid or duplicate publisher {field} path: {name}')
        result[name] = row['sha256']
    return result


def stu_engine_payload(skill, read):
    manifest_bytes = read(STU_MANIFEST)
    manifest = json.loads(manifest_bytes.decode('utf-8-sig'))
    name = manifest.get('file')
    if manifest.get('family') != 'stu' or len(bundle._relative(name)) != 1 or not name.lower().endswith('.dll'):
        raise ValueError('The Stu publisher manifest must identify one own DLL')
    sources = source_rows(manifest, 'sources')
    manifest_inputs = json.dumps(sorted(sources.items()), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if sha256(manifest_inputs) != bundle.stu_engine_source_sha256(skill):
        raise ValueError('The precompiled Stu engine does not match the complete current source contract')
    engine = read(name)
    if not engine or sha256(engine) != manifest.get('sha256'):
        raise ValueError('The precompiled Stu DLL differs from its publisher manifest')
    return name, {name: engine, STU_MANIFEST: manifest_bytes}


def shared_bridge_payload(skill, read, *, verify_generated=False):
    manifest_bytes = read(BRIDGE_MANIFEST)
    manifest = json.loads(manifest_bytes.decode('utf-8-sig'))
    contract = bundle._read(bundle._inside(skill, BRIDGE_CONTRACT))
    if (manifest.get('schema') != 1 or manifest.get('identity') != contract
            or manifest.get('contract') != contract['release']
            or manifest.get('receiver_compilation_required') is not False
            or manifest.get('vendor_files_included') is not False):
        raise ValueError('The precompiled bridge differs from the current shared transport contract')
    recorded = source_rows(manifest, 'source_inputs')
    expected = {row['file']: row['sha256'] for row in bridge_source_inputs(skill)}
    if recorded != expected:
        raise ValueError('The precompiled bridge was built from different shared bridge inputs')

    generated = source_rows(manifest, 'sources', windows_paths=True)
    if set(generated) != {f'source/{name}' for name in (*BOOTSTRAP_SOURCES, 'PortableEntry.cs')}:
        raise ValueError('The portable bootstrap generated-source list differs')
    if verify_generated:
        for name, digest in generated.items():
            if sha256(read(name)) != digest:
                raise ValueError('The generated portable bootstrap source differs: ' + name)

    names = {contract[key] for key in ('bridge_file', 'hook_file', 'client_file')}
    entries = manifest.get('artifacts')
    if (not isinstance(entries, list) or len(entries) != len(names)
            or any(not isinstance(row, dict) or not isinstance(row.get('file'), str) for row in entries)
            or {row['file'] for row in entries} != names):
        raise ValueError('The current bridge DLL, hook and client must be present exactly once')
    result = {BRIDGE_MANIFEST: manifest_bytes}
    for row in entries:
        name = row['file']
        if len(bundle._relative(name)) != 1:
            raise ValueError('A shared bridge artifact needs one basename')
        raw = read(name)
        if not raw or len(raw) != row.get('bytes') or sha256(raw) != row.get('sha256'):
            raise ValueError('The precompiled bridge artifact differs: ' + name)
        result[name] = raw
    return result
