"""Match the current skill to a published precompiled engine without downgrading.

The large complete bundle supplies unchanged runtimes/media. A small indexed
update supplies the matching skill and business engine; no receiver compiler
or vendor process is invoked. All extracted/reused bytes are verified.
"""
from __future__ import annotations

import importlib.util
import http.client
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile

INDEX_NAME = 'mcgs-engineering-index.json'
INDEX_SCHEMA = 'mcgs-engineering-release-index/v1'
CONTRACT_PATHS = {
    'source_manifest_sha256': 'assets/pro-native-bridge/delivery/source/source-and-dependency-manifest.json',
    'source_catalog_sha256': 'assets/pro-native-bridge/abi-adapter/catalogs/source-addresses.json',
}


def source_contract(skill, helper):
    return {key: helper._sha(Path(skill) / path) for key, path in CONTRACT_PATHS.items()}


def matches(root, info, wanted, helper):
    try:
        engine = helper._inside(root, info['business_engine'])
        release = helper._read(engine.parent / 'portable-engine-manifest.json')
        return (all(release.get(key) == value for key, value in wanted.items())
                and helper._sha(engine) == release['sha256'])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _index(value, wanted, helper):
    if value.get('schema') != INDEX_SCHEMA or value.get('source_contract') != wanted:
        return None
    spec = value['update']
    if (not re.fullmatch(r'[a-f0-9]{64}', spec['sha256'])
            or type(spec['size']) is not int or spec['size'] <= 0
            or len(helper._relative(spec['file'])) != 1):
        raise ValueError('Invalid release update size, name or digest')
    spec = dict(spec, tag=value['release_tag'])
    return spec


def _find_index(skill, wanted, cache, helper, allow_download):
    # Explicit local metadata also supports fully disconnected distributions.
    explicit = os.environ.get('MCGS_UPDATE_INDEX')
    paths = ([Path(explicit).expanduser()] if explicit else []) + [
        Path(skill) / INDEX_NAME, Path(skill).parent / INDEX_NAME,
        cache / INDEX_NAME, Path.cwd() / INDEX_NAME, Path.home() / 'Downloads' / INDEX_NAME,
    ]
    for path in paths:
        if path.is_file():
            candidate = _index(helper._read(path), wanted, helper)
            if candidate:
                candidate['index_directory'] = str(path.resolve().parent)
                return candidate
    if not allow_download:
        return None
    # /latest can deliberately remain the old complete package. Search release
    # assets independently; only indexes with the current source contract match.
    page = 1
    while True:
        url = f'https://api.github.com/repos/{helper.REPOSITORY}/releases?per_page=100&page={page}'
        with helper._url(url, Accept='application/vnd.github+json') as response:
            releases = json.load(response)
        for release in releases:
            if release.get('draft'):
                continue
            for asset in release.get('assets', []):
                if asset.get('name') == INDEX_NAME and asset.get('state') == 'uploaded':
                    with helper._url(asset['browser_download_url']) as response:
                        value = json.loads(response.read(1024 * 1024).decode('utf-8-sig'))
                    candidate = _index(value, wanted, helper)
                    if candidate:
                        helper._write(cache / INDEX_NAME, value)
                        return candidate
        if len(releases) < 100:
            break
        page += 1
    return None


def _extract_update(archive_file, directory, helper):
    seen, prefixes = set(), {}
    with zipfile.ZipFile(archive_file) as archive:
        for item in archive.infolist():
            helper._relative(item.orig_filename)
            parts = helper._relative(item.filename)
            key = '/'.join(parts).casefold()
            mode = item.external_attr >> 16
            if key in seen or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError('Update ZIP contains a duplicate or special path')
            seen.add(key)
            for count in range(1, len(parts) + 1):
                prefix = '/'.join(parts[:count])
                if prefixes.setdefault(prefix.casefold(), prefix) != prefix:
                    raise ValueError('Update ZIP contains a case alias')
        for item in archive.infolist():
            target = helper._inside(directory, item.filename)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open('xb') as output:
                    while raw := source.read(1024 * 1024):
                        output.write(raw)
    if not (directory / 'update.json').is_file():
        raise ValueError('Update ZIP must contain update.json at its root')


def _apply(skill, base, extracted, output, helper):
    # Execute the current reviewed updater, never a script taken from the ZIP.
    sys.modules['turnkey_bundle'] = helper
    spec = importlib.util.spec_from_file_location('mcgs_current_updater', Path(skill) / 'scripts/apply_turnkey_update.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.apply_update(base, extracted, output)


def ensure_matching(skill, base, info, helper, allow_download=True, cache_dir=None):
    wanted = source_contract(skill, helper)
    cache = Path(cache_dir).expanduser().resolve() if cache_dir else helper.default_cache().resolve()
    if matches(base, info, wanted, helper):
        return base, info
    cache.mkdir(parents=True, exist_ok=True)
    # An already upgraded body wins over a stale installed-skill pointer.
    candidates = [path for _, path in helper._candidate_paths(skill, cache)]
    if (cache / 'releases').is_dir():
        candidates.extend(path for path in (cache / 'releases').iterdir() if path.is_dir())
    for candidate in candidates:
        try:
            root, metadata = helper._bundle_metadata(candidate)
            if matches(root, metadata, wanted, helper):
                helper._remember(root, metadata, cache)
                return root, metadata
        except (OSError, ValueError, KeyError, TypeError):
            continue
    try:
        spec = _find_index(skill, wanted, cache, helper, allow_download)
        if spec is None:
            raise helper.BundleUnavailable('No published precompiled update matches the current skill source contract',
                status='matching_engine_update_unavailable', source_contract=wanted,
                selected_bundle=str(base), current_skill_preserved=True,
                recovery_command='run.ps1 turnkey fetch-bundle', download_enabled=allow_download)
        with helper._fetch_lock(cache):
            destination = cache / 'releases' / ('u-' + spec['sha256'][:20])
            if destination.exists():
                root, metadata = helper.verify_complete(destination)
            else:
                local = []
                if os.environ.get('MCGS_UPDATE_ARCHIVE'):
                    local.append(Path(os.environ['MCGS_UPDATE_ARCHIVE']).expanduser())
                if spec.get('index_directory'):
                    local.append(Path(spec['index_directory']) / spec['file'])
                archive = next((path for path in local if path.is_file() and path.stat().st_size == spec['size']
                                and helper._sha(path) == spec['sha256']), None)
                if archive is None:
                    archive = next(helper._local_archives(skill, cache, spec), None)
                if archive is None:
                    if not allow_download:
                        raise helper.BundleUnavailable('The matching update archive is not available locally', update=spec)
                    archive = helper._download(spec, cache)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='upd-', dir=cache) as temporary:
                    extracted = Path(temporary)
                    _extract_update(archive, extracted, helper)
                    _apply(skill, base, extracted, destination, helper)
                root, metadata = helper._bundle_metadata(destination)
            if not matches(root, metadata, wanted, helper):
                raise ValueError('Verified update engine does not match the requested source contract')
            helper._remember(root, metadata, cache, spec['sha256'])
            return root, metadata
    except helper.BundleUnavailable:
        raise
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, http.client.HTTPException) as error:
        raise helper.BundleUnavailable('Matching precompiled update could not be prepared', detail=str(error),
            status='matching_engine_update_unavailable', source_contract=wanted,
            current_skill_preserved=True, source_engine_rebuild_required=False) from error
