"""Build a complete bundle by reusing verified target files from an installed version."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

import turnkey_bundle as bundle


SCHEMA = 'mcgs-turnkey-update/v1'
FILES = 'bundle-files.json'
METADATA = 'bundle.json'
SHA256 = re.compile(r'[a-f0-9]{64}')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def object_json(raw, schema):
    value = json.loads(raw.decode('utf-8-sig'))
    require(isinstance(value, dict) and type(value.get('schema')) is type(schema) and value['schema'] == schema,
            'Unexpected JSON schema: ' + str(schema))
    return value


def file_rows(value):
    require(isinstance(value, list), 'File manifest must contain a list')
    rows = {}
    for row in value:
        require(isinstance(row, dict) and set(row) == {'file', 'size', 'sha256'}, 'Invalid file manifest entry')
        name = row['file']
        require('/'.join(bundle._relative(name)) == name, 'File manifest path is not canonical: ' + str(name))
        require(type(row['size']) is int and row['size'] >= 0 and isinstance(row['sha256'], str)
                and SHA256.fullmatch(row['sha256']), 'Invalid file size or SHA256: ' + name)
        key = name.casefold()
        require(key not in rows, 'Duplicate file manifest path: ' + name)
        rows[key] = row
    return rows


def is_reparse(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def source_file(root, name):
    path = root.joinpath(*bundle._relative(name))
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not is_reparse(info) and path.resolve() == path,
            'Expected a regular, directly contained file: ' + str(path))
    return path


def pin_bytes(path, expected):
    require(isinstance(expected, str) and SHA256.fullmatch(expected), 'Invalid SHA256 pin for ' + path.name)
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'Pinned file differs: ' + str(path))
    return raw


def restore_media_directories(root, metadata):
    for product in metadata.get('products', []):
        index = bundle._inside(root, product['media_manifest'])
        manifest = object_json(index.read_bytes(), 1)
        media = index.parent / 'media'
        media.mkdir(exist_ok=True)
        for name in manifest.get('directories', []):
            bundle._inside(media, name).mkdir(parents=True, exist_ok=True)


def apply_update(base, update_root, output):
    base = Path(base).expanduser().resolve(strict=True)
    update_root = Path(update_root).expanduser().resolve(strict=True)
    requested_output = Path(output).expanduser().absolute()
    require(not os.path.lexists(requested_output), 'Output must be a fresh directory: ' + str(requested_output))
    output = requested_output.resolve()
    require(not output.is_relative_to(base) and not output.is_relative_to(update_root),
            'Output must be outside both the base and the extracted update')

    update = object_json(source_file(update_root, 'update.json').read_bytes(), SCHEMA)
    # The publisher's base hashes describe how the delta was produced. Any
    # installed release can supply a reused file when its bytes match target.
    object_json(source_file(base, METADATA).read_bytes(), bundle.SCHEMA)
    payload = update_root / 'payload'
    require(payload.is_dir() and not is_reparse(payload.lstat()), 'Missing regular update payload directory')
    target_manifest = pin_bytes(source_file(payload, FILES), update['target_files_sha256'])
    target = file_rows(object_json(target_manifest, 1)['files'])
    require(FILES not in target and METADATA in target,
            'Bundle manifest must include bundle.json and exclude itself')
    expected = file_rows(update['payload'])
    require(METADATA in expected, 'Update must include the new bundle.json')
    require(expected.get(FILES) == {'file': FILES, 'size': len(target_manifest), 'sha256': update['target_files_sha256']},
            'Update target file manifest differs')
    for key, row in expected.items():
        require(key == FILES or target.get(key) == row, 'Payload file differs from target manifest: ' + row['file'])

    actual = set()
    for path in payload.rglob('*'):
        info = path.lstat()
        require(not is_reparse(info), 'Update payload contains a link or reparse point: ' + str(path))
        if stat.S_ISREG(info.st_mode):
            actual.add(path.relative_to(payload).as_posix())
        else:
            require(stat.S_ISDIR(info.st_mode), 'Update payload contains a non-file entry: ' + str(path))
    require(actual == {row['file'] for row in expected.values()}, 'Update payload has missing or extra files')
    for row in expected.values():
        file = source_file(payload, row['file'])
        require(file.stat().st_size == row['size'] and bundle._sha(file) == row['sha256'],
                'Update payload file differs: ' + row['file'])
    missing = []
    for key, row in target.items():
        if key in expected:
            continue
        try:
            file = source_file(base, row['file'])
            if file.stat().st_size != row['size'] or bundle._sha(file) != row['sha256']:
                missing.append(row['file'])
        except OSError:
            missing.append(row['file'])
    require(not missing, 'The installed bundle cannot supply these target files: ' + ', '.join(missing))
    target_release = update['target_release']
    target_metadata = pin_bytes(source_file(payload, METADATA), target[METADATA]['sha256'])
    metadata = object_json(target_metadata, bundle.SCHEMA)
    require(isinstance(target_release, str) and target_release and metadata.get('release') == target_release,
            'Target bundle release differs from the update declaration')

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.mcgs-update-', dir=output.parent)).resolve()
    try:
        for key, row in target.items():
            name = row['file']
            destination = staging.joinpath(*bundle._relative(name))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if key == METADATA:
                destination.write_bytes(target_metadata)
            else:
                shutil.copyfile(source_file(payload if key in expected else base, name), destination)
        (staging / FILES).write_bytes(target_manifest)
        restore_media_directories(staging, metadata)
        bundle.verify_complete(staging)
        require(staging.parent == output.parent and not os.path.lexists(output),
                'Output or staging location changed during verification: ' + str(output))
        staging.rename(output)
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as error:
        raise ValueError(f'{error}. Unpublished staging directory: {staging}') from error

    return {'status': 'update_applied', 'bundle_root': str(output), 'release': target_release,
            'files_verified': len(target), 'updated_files': len(expected),
            'unchanged_files_reused': len(target) + 1 - len(expected),
            'base_modified': False, 'receiver_compilation_required': False,
            'installer_executed': False, 'project_written': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-bundle', '--base', required=True, help='Previously extracted complete bundle')
    parser.add_argument('--update-root', default=str(Path(__file__).resolve().parents[1]), help='Extracted update directory')
    parser.add_argument('--output', required=True, help='New complete bundle directory')
    args = parser.parse_args()
    try:
        result = apply_update(args.base_bundle, args.update_root, args.output)
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as error:
        print(json.dumps({'status': 'update_not_applied', 'error': str(error)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
