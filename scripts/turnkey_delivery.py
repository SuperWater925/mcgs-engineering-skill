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
STU_CONTRACT = 'stu_engine_source_sha256'


def source_contract(skill, helper, *, family='pro'):
    contract = {key: helper._sha(Path(skill) / path) for key, path in CONTRACT_PATHS.items()}
    if family == 'stu':
        source = helper.stu_engine_source_sha256(skill)
        if source is None:
            raise helper.BundleUnavailable('This skill has no Stu native engine source contract',
                status='stu_native_skill_components_missing', family=family, current_skill_preserved=True)
        contract[STU_CONTRACT] = source
    return contract


def matches(root, info, wanted, helper):
    try:
        engine = helper._inside(root, info['business_engine'])
        release = helper._read(engine.parent / 'portable-engine-manifest.json')
        if (any(release.get(key) != wanted[key] for key in CONTRACT_PATHS)
                or helper._sha(engine) != release['sha256']):
            return False
        if STU_CONTRACT in wanted:
            skill = helper._inside(root, info['skill_directory'])
            return (helper.stu_engine_source_sha256(skill) == wanted[STU_CONTRACT]
                    and helper.verify_stu_engine(root, info, skill_root=skill) is not None)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _index(value, wanted, helper):
    indexed_contract = value.get('source_contract')
    if (value.get('schema') != INDEX_SCHEMA or not isinstance(indexed_contract, dict)
            or any(indexed_contract.get(key) != expected for key, expected in wanted.items())):
        return None
    spec = value['update']
    if (not re.fullmatch(r'[a-f0-9]{64}', spec['sha256'])
            or type(spec['size']) is not int or spec['size'] <= 0
            or len(helper._relative(spec['file'])) != 1):
        raise ValueError('Invalid release update size, name or digest')
    spec = dict(spec, tag=value['release_tag'])
    return spec


def _find_index(skill, wanted, cache, helper, allow_download, diagnostics=None):
    # Explicit local metadata also supports fully disconnected distributions.
    explicit = os.environ.get('MCGS_UPDATE_INDEX')
    diagnostics = diagnostics if diagnostics is not None else []
    paths = ([Path(explicit).expanduser()] if explicit else []) + [
        Path(skill) / INDEX_NAME, Path(skill).parent / INDEX_NAME,
        cache / INDEX_NAME, Path.cwd() / INDEX_NAME, Path.home() / 'Downloads' / INDEX_NAME,
    ]
    for position, path in enumerate(paths):
        is_explicit = bool(explicit) and position == 0
        try:
            if not path.is_file():
                if is_explicit:
                    raise ValueError('Index is not a regular file')
                continue
            candidate = _index(helper._read(path), wanted, helper)
            if candidate:
                candidate['index_directory'] = str(path.resolve().parent)
                return candidate
            if is_explicit:
                raise ValueError('Index schema or source contract does not match the current skill')
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            item = {'path': str(path.absolute()), 'explicit': is_explicit,
                    'status': 'release_index_rejected', 'detail': str(error)}
            diagnostics.append(item)
            if is_explicit:
                raise ValueError('Explicit MCGS_UPDATE_INDEX rejected at ' + str(path.absolute()) + ': ' + str(error)) from error
            print(json.dumps(item, ensure_ascii=False), file=sys.stderr)
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


def ensure_matching(skill, base, info, helper, allow_download=True, cache_dir=None, *, family='pro'):
    wanted = source_contract(skill, helper, family=family)
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
    diagnostics = []
    try:
        spec = _find_index(skill, wanted, cache, helper, allow_download, diagnostics)
        if spec is None:
            raise helper.BundleUnavailable('No published precompiled update matches the selected family and current skill source',
                status='matching_engine_update_unavailable', source_contract=wanted,
                family=family,
                selected_bundle=str(base), current_skill_preserved=True,
                recovery_command='run.ps1 turnkey fetch-bundle', download_enabled=allow_download,
                index_diagnostics=diagnostics)
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
            family=family,
            current_skill_preserved=True, source_engine_rebuild_required=False,
            index_diagnostics=diagnostics) from error
