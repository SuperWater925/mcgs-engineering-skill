"""Locate or fetch a complete release without compiling or installing software.

The source skill can live in any agent's skill directory. Complete releases
are cached outside that directory and shared through a small location pointer.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import time
import urllib.error
import urllib.request
import uuid
import zipfile

REPOSITORY = 'SuperWater925/mcgs-engineering-skill'
RELEASES_URL = 'https://github.com/' + REPOSITORY + '/releases/latest'
API_RELEASE = 'https://api.github.com/repos/' + REPOSITORY + '/releases/latest'
FALLBACK = {
    'tag': 'v2026.11.06-turnkey',
    'file': 'mcgs-engineering-turnkey-2026.11.06-win-x64.zip',
    'size': 686364835,
    'sha256': 'de1f2c1fac7b001d27e58cbe15a4c573e5147ae5ee3818c2595a021ecc051beb',
    'url': 'https://github.com/' + REPOSITORY + '/releases/download/v2026.11.06-turnkey/mcgs-engineering-turnkey-2026.11.06-win-x64.zip',
}
SCHEMA = 'mcgs-turnkey-bundle/v1'
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', 'CLOCK$'} | {
    prefix + str(number) for prefix in ('COM', 'LPT') for number in range(1, 10)}


class BundleUnavailable(ValueError):
    def __init__(self, reason, **details):
        self.report = {
            'status': 'complete_bundle_unavailable', 'reason': reason,
            'download_available': True, 'manual_url': RELEASES_URL,
            'recovery_command': 'run.ps1 turnkey fetch-bundle',
            'software_reinstallation_required': False,
            'source_engine_rebuild_required': False,
            **details,
        }
        super().__init__(reason)


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def _sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def default_cache():
    parent = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData/Local'))
    return parent / 'mcgs-engineering/bundles'


def _remember(root, metadata, cache, archive_sha256=None):
    pointer = {'schema': 1, 'bundle_root': str(root), 'release': metadata['release'],
               'receiver_compilation_required': False}
    if not archive_sha256 and (cache / 'current.json').is_file():
        try:
            previous = _read(cache / 'current.json')
            if Path(previous['bundle_root']).resolve() == root.resolve():
                pointer.update({key: previous[key] for key in ('archive_sha256', 'verified_at') if key in previous})
        except (OSError, ValueError, TypeError, KeyError):
            pass
    if archive_sha256:
        pointer['archive_sha256'] = archive_sha256
        pointer['verified_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    _write(cache / 'current.json', pointer)
    shared = default_cache().resolve()
    if shared != cache.resolve():
        # A short/custom body directory still has a normal per-user discovery
        # record, so subsequent run.ps1 commands find the same runtime.
        _write(shared / 'current.json', pointer)
    return pointer


def _relative(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('Archive/manifest path must use nonempty relative slash components')
    windows = PureWindowsPath(value)
    parts = value.rstrip('/').split('/')
    if windows.drive or windows.root or PurePosixPath(value).is_absolute():
        raise ValueError('Archive/manifest path is absolute')
    for part in parts:
        if not part or part in ('.', '..') or part.endswith((' ', '.')) or ':' in part:
            raise ValueError('Archive/manifest path has a Windows alias or traversal component')
        if any(character in part for character in '<>"|?*') or any(ord(character) < 32 for character in part):
            raise ValueError('Archive/manifest path has an invalid Windows component')
        if part.split('.', 1)[0].upper() in RESERVED:
            raise ValueError('Archive/manifest path has a reserved Windows component')
    return parts


def _inside(root, relative):
    parts = _relative(relative)
    target = Path(root).joinpath(*parts).resolve()
    if not target.is_relative_to(Path(root).resolve()):
        raise ValueError('Archive/manifest path escapes its selected root')
    return target


def _bundle_metadata(root):
    root = Path(root).expanduser().resolve()
    metadata = _read(root / 'bundle.json')
    if metadata.get('schema') != SCHEMA:
        raise ValueError('Unknown complete bundle schema')
    for key in ('python', 'powershell', 'business_engine', 'choice_helper', 'bridge_artifacts', 'skill_directory'):
        path = _inside(root, metadata[key])
        expected = path.is_dir() if key in ('bridge_artifacts', 'skill_directory') else path.is_file()
        if not expected:
            raise ValueError('Complete bundle component is missing: ' + key)
    if not (root / 'bundle-files.json').is_file():
        raise ValueError('Complete bundle file manifest is missing')
    return root, metadata


def verify_complete(root):
    """Full file verification after extraction; never executes a packaged EXE."""
    root, metadata = _bundle_metadata(root)
    listing = _read(root / 'bundle-files.json')
    seen = set()
    for row in listing['files']:
        relative = row['file']
        folded = '/'.join(_relative(relative)).casefold()
        if folded in seen:
            raise ValueError('Duplicate complete bundle manifest file: ' + relative)
        seen.add(folded)
        path = _inside(root, relative)
        if path.is_symlink() or not path.is_file() or path.stat().st_size != row['size'] or _sha(path) != row['sha256']:
            raise ValueError('Complete bundle file differs: ' + relative)
    actual = {path.relative_to(root).as_posix().casefold() for path in root.rglob('*') if path.is_file()}
    if actual != seen | {'bundle-files.json'}:
        raise ValueError('Complete bundle files and manifest disagree')
    for product in metadata.get('products', []):
        index = _inside(root, product['media_manifest'])
        for relative in _read(index).get('directories', []):
            if not _inside(index.parent / 'media', relative).is_dir():
                raise ValueError('Complete vendor media directory is missing: ' + relative)
    return root, metadata


def _candidate_paths(skill_root, cache):
    skill = Path(skill_root).expanduser().resolve()
    values = []
    if os.environ.get('MCGS_BUNDLE_ROOT'):
        values.append(('environment', Path(os.environ['MCGS_BUNDLE_ROOT'])))
    pointer = skill / 'turnkey-location.json'
    if pointer.is_file():
        try:
            values.append(('skill_pointer', Path(_read(pointer)['bundle_root'])))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    values.extend([('skill_directory', skill), ('adjacent_directory', skill.parent)])
    pointer = cache / 'current.json'
    if pointer.is_file():
        try:
            values.append(('shared_cache', Path(_read(pointer)['bundle_root'])))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    seen = set()
    for origin, value in values:
        normalized = os.path.normcase(str(value.expanduser().resolve()))
        if normalized not in seen:
            seen.add(normalized)
            yield origin, value.expanduser().resolve()


def resolve(skill_root, explicit_root=None, allow_download=False, cache_dir=None):
    cache = Path(cache_dir).expanduser().resolve() if cache_dir else default_cache().resolve()
    if explicit_root is not None:
        try:
            result = _bundle_metadata(explicit_root)
            if allow_download:
                _remember(*result, cache)
            return result
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise BundleUnavailable('The explicit complete bundle directory is invalid',
                explicit_root=str(Path(explicit_root).expanduser().resolve()), detail=str(error)) from error
    attempted = []
    for origin, root in _candidate_paths(skill_root, cache):
        try:
            result = _bundle_metadata(root)
            if allow_download:
                _remember(*result, cache)
            return result
        except (OSError, ValueError, KeyError, TypeError) as error:
            attempted.append({'origin': origin, 'directory': str(root), 'detail': str(error)})
    if not allow_download:
        raise BundleUnavailable('The installed source skill has no complete runtime bundle yet',
            attempted_locations=attempted, cache_directory=str(cache))
    try:
        return _obtain(skill_root, cache)
    except BundleUnavailable:
        raise
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, urllib.error.URLError, http.client.HTTPException) as error:
        raise BundleUnavailable('Complete bundle acquisition did not finish', detail=str(error),
            cache_directory=str(cache), partial_work_preserved=True) from error


def available_bundle(skill_root, explicit_root=None, cache_dir=None):
    """Read-only discovery for inventory; callers can catch BundleUnavailable."""
    return resolve(skill_root, explicit_root, False, cache_dir)


def fetch(skill_root, explicit_root=None, cache_dir=None):
    return resolve(skill_root, explicit_root, True, cache_dir)


def _url(url, **headers):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'mcgs-engineering-bundle-bootstrap', **headers})
    return urllib.request.urlopen(request, timeout=60)


def _release_info():
    try:
        with _url(API_RELEASE, Accept='application/vnd.github+json') as response:
            release = json.load(response)
        matches = [row for row in release['assets'] if
            re.fullmatch(r'mcgs-engineering-turnkey-.+-win-x64\.zip', row['name']) and row.get('state') == 'uploaded']
        if len(matches) != 1:
            raise ValueError('Latest release has no unique complete Windows x64 bundle')
        asset = matches[0]
        raw_digest = asset.get('digest') or ''
        checksum = raw_digest[7:] if re.fullmatch(r'sha256:[a-fA-F0-9]{64}', raw_digest) else None
        if checksum is None:
            sums = next(row for row in release['assets'] if row['name'] == 'SHA256SUMS.txt')
            with _url(sums['browser_download_url']) as response:
                text = response.read().decode('utf-8-sig')
            checksum = next(match.group(1) for line in text.splitlines() if
                (match := re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?' + re.escape(asset['name']), line.strip())))
        return {'tag': release['tag_name'], 'file': asset['name'], 'size': asset['size'],
                'sha256': checksum.lower(), 'url': asset['browser_download_url']}
    except (OSError, ValueError, KeyError, TypeError, StopIteration, urllib.error.URLError, http.client.HTTPException):
        # A known, complete release remains useful if latest metadata is offline
        # or a later source-only release intentionally has no full attachment.
        return dict(FALLBACK)


@contextmanager
def _fetch_lock(cache):
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / 'fetch.lock'
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise BundleUnavailable('Another complete-bundle fetch is active',
                status='bundle_fetch_in_progress', state_file=str(cache / 'fetch-state.json')) from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_UN)


def _local_archives(skill_root, cache, spec):
    skill = Path(skill_root).expanduser().resolve()
    explicit = os.environ.get('MCGS_BUNDLE_ARCHIVE')
    candidates = ([Path(explicit).expanduser()] if explicit else []) + [
        cache / 'downloads' / (spec['sha256'][:16] + '-' + spec['file']),
        skill / spec['file'], skill.parent / spec['file'], Path.cwd() / spec['file'],
        Path.home() / 'Downloads' / spec['file'],
    ]
    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        key = os.path.normcase(str(candidate))
        if key not in seen:
            seen.add(key)
            if candidate.is_file() and candidate.stat().st_size == spec['size'] and _sha(candidate) == spec['sha256']:
                yield candidate


def _download(spec, cache):
    directory = cache / 'downloads'
    directory.mkdir(exist_ok=True)
    final = directory / (spec['sha256'][:16] + '-' + spec['file'])
    marker = final.with_suffix(final.suffix + '.download.json')
    partial = final.with_suffix(final.suffix + '.part')
    if marker.is_file():
        old = _read(marker)
        if old.get('sha256') != spec['sha256'] or old.get('url') != spec['url']:
            raise ValueError('Download journal belongs to another source; existing bytes were preserved')
        partial = Path(old['partial_file'])
        if partial.parent != directory:
            raise ValueError('Download journal partial path is outside its cache')
    if partial.exists() and partial.stat().st_size > spec['size']:
        raise ValueError('Partial archive is larger than its release metadata; existing bytes were preserved')
    if partial.is_symlink() or partial.exists() and not partial.is_file():
        raise ValueError('Download partial path is not a regular cache file')
    offset = partial.stat().st_size if partial.is_file() else 0
    if offset == spec['size'] and _sha(partial) == spec['sha256']:
        os.replace(partial, final)
        return final
    if offset == spec['size']:
        # A previous transfer completed with a bad digest. Preserve it, but let
        # this new invocation fetch clean bytes rather than issue bytes=N-.
        partial = directory / (final.name + '.' + uuid.uuid4().hex + '.part')
        offset = 0
    headers = {'Range': 'bytes=' + str(offset) + '-'} if offset else {}
    _write(marker, {**spec, 'partial_file': str(partial), 'phase': 'download_requested', 'bytes_present': offset})
    with _url(spec['url'], **headers) as response:
        response_status = getattr(response, 'status', 200) or 200
        if offset and response_status == 206:
            content_range = response.headers.get('Content-Range', '')
            if not content_range.startswith('bytes ' + str(offset) + '-'):
                raise ValueError('HTTP resume range does not match preserved partial bytes')
            mode = 'ab'
        elif response_status == 200:
            mode = 'xb'
            if partial.exists():
                # A server may ignore Range. Download to a new file and retain
                # previous partial bytes instead of appending a whole archive.
                partial = directory / (final.name + '.' + uuid.uuid4().hex + '.part')
                offset = 0
        else:
            raise ValueError('Unexpected bundle download status: ' + str(response_status))
        _write(marker, {**spec, 'partial_file': str(partial), 'phase': 'downloading', 'bytes_present': offset})
        with partial.open(mode) as stream:
            while data := response.read(1024 * 1024):
                stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    if partial.stat().st_size != spec['size'] or _sha(partial) != spec['sha256']:
        _write(marker, {**spec, 'partial_file': str(partial), 'phase': 'unverified_bytes_preserved',
                        'bytes_present': partial.stat().st_size})
        raise ValueError('Downloaded archive size/SHA differs; partial bytes remain for inspection')
    if final.exists():
        if not final.is_file() or final.is_symlink():
            raise ValueError('Cached archive destination is not a regular file')
        os.replace(final, final.with_name(final.name + '.invalid-' + uuid.uuid4().hex))
    os.replace(partial, final)
    _write(marker, {**spec, 'partial_file': str(partial), 'phase': 'archive_verified', 'archive_file': str(final)})
    return final


def _extract(archive_file, staging):
    with zipfile.ZipFile(archive_file) as archive:
        seen, prefixes = set(), {}
        for item in archive.infolist():
            _relative(item.orig_filename)  # ZipInfo normalizes backslashes on Windows.
            parts = _relative(item.filename)
            key = '/'.join(parts).casefold()
            if key in seen:
                raise ValueError('Duplicate archive path: ' + item.filename)
            seen.add(key)
            for count in range(1, len(parts) + 1):
                prefix = '/'.join(parts[:count])
                previous = prefixes.setdefault(prefix.casefold(), prefix)
                if previous != prefix:
                    raise ValueError('Case-alias archive path: ' + item.filename)
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError('Archive link or special file is unsupported: ' + item.filename)
        for item in archive.infolist():
            path = _inside(staging, item.filename)
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, path.open('xb') as target:
                    while data := source.read(1024 * 1024):
                        target.write(data)
    candidates = [staging] if (staging / 'bundle.json').is_file() else [
        path for path in staging.iterdir() if path.is_dir() and (path / 'bundle.json').is_file()]
    if len(candidates) != 1:
        raise ValueError('Archive must contain one complete bundle root')
    return verify_complete(candidates[0])


def _obtain(skill_root, cache):
    with _fetch_lock(cache):
        # A concurrent caller may have finished while this process was waiting
        # for its nonblocking lock. Rediscovery never downloads or executes.
        try:
            return resolve(skill_root, allow_download=False, cache_dir=cache)
        except BundleUnavailable:
            pass
        spec = _release_info()
        if not re.fullmatch(r'[a-f0-9]{64}', spec['sha256']) or not isinstance(spec['size'], int) or spec['size'] <= 0:
            raise ValueError('Release archive metadata is incomplete')
        if len(_relative(spec['file'])) != 1:
            raise ValueError('Release archive name must be a single filename')
        slug = re.sub(r'[^A-Za-z0-9_.-]+', '_', spec['tag']) + '-' + spec['sha256'][:16]
        destination = cache / 'releases' / slug
        state = cache / 'fetch-state.json'
        if destination.exists():
            root, metadata = verify_complete(destination)
        else:
            _write(state, {'phase': 'locating_archive', **spec})
            archive_file = next(_local_archives(skill_root, cache, spec), None)
            if archive_file is None:
                _write(state, {'phase': 'downloading_archive', **spec})
                archive_file = _download(spec, cache)
            staging = cache / ('staging-' + uuid.uuid4().hex)
            staging.mkdir()
            _write(state, {'phase': 'extracting_and_verifying', **spec,
                           'archive_file': str(archive_file), 'staging_directory': str(staging)})
            root, metadata = _extract(archive_file, staging)
            destination.parent.mkdir(exist_ok=True)
            os.replace(root, destination)
            root = destination
        pointer = _remember(root, metadata, cache, spec['sha256'])
        _write(state, {'phase': 'ready', **pointer})
        return root, metadata
