"""Receiver entry for the complete, publisher-precompiled MCGS distribution.

No compiler is invoked here. Vendor setup/uninstall is a separate, explicitly
chosen state machine in turnkey_installation.py; project mutation is never an
environment setup side effect.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

SKILL = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_bundle_helper = None


def bundle_helper():
    global _bundle_helper
    if _bundle_helper is None:
        _bundle_helper = load_module('mcgs_turnkey_bundle', SKILL / 'scripts/turnkey_bundle.py')
    return _bundle_helper


def bundle(root=None, allow_download=False, cache_dir=None):
    return bundle_helper().resolve(SKILL, explicit_root=root, allow_download=allow_download, cache_dir=cache_dir)


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Bundle path escapes its root')
    return path


def verify(root, full=False):
    root, info = bundle(root)
    listing = read(root / 'bundle-files.json')['files']
    total = 0
    for row in listing:
        relative = row['file']
        if not full and relative.startswith('vendor/'):
            continue
        path = contained(root, relative)
        if not path.is_file() or path.stat().st_size != row['size'] or digest(path) != row['sha256']:
            raise ValueError('Bundle file differs or is missing: ' + relative)
        total += 1
    if full:
        for product in info['products']:
            media_index = contained(root, product['media_manifest'])
            media = media_index.parent / 'media'
            for relative in read(media_index).get('directories', []):
                if not contained(media, relative).is_dir():
                    raise ValueError('Vendor media directory is missing: ' + relative)
    return {'status': 'bundle_files_verified', 'files_verified': total,
            'vendor_media_verified': full, 'receiver_compilation_required': False}


def run_json(argv, env=None, timeout=180):
    result = subprocess.run([os.fspath(x) for x in argv], capture_output=True,
                            text=True, encoding='utf-8-sig', errors='strict',
                            env=env, timeout=timeout)
    try:
        value = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError('Tool did not return JSON; code=%s, diagnostic=%s' % (result.returncode, result.stderr[-1600:]))
    if result.returncode:
        raise RuntimeError(json.dumps(value, ensure_ascii=False))
    return value


def runtime_env(root, info):
    env = os.environ.copy()
    env['MCGS_PYTHON'] = str(contained(root, info['python']))
    env['MCGS_PWSH'] = str(contained(root, info['powershell']))
    env['PYTHONUTF8'] = '1'
    return env


def cache_root():
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'mcgs-engineering'
    root.mkdir(parents=True, exist_ok=True)
    return root


def probe_queue(runtime, python):
    """One correlated read-only ping; preserves unknown outcomes for inspection."""
    transport = Path(runtime) / 'bridge_client.py'
    if not transport.is_file():
        return {'verified': False, 'status': 'transport_not_at_runtime_root'}
    request_id = 'turnkey-ping-' + uuid.uuid4().hex
    try:
        receipt = run_json([python, transport, 'ping', '--id', request_id, '--timeout', '10'], timeout=20)
        return {'verified': bool(receipt.get('ok')), 'request_id': request_id, 'receipt': receipt}
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        return {'verified': False, 'request_id': request_id, 'status': 'queue_not_confirmed',
                'error': str(error), 'automatic_retry': False}


def inventory(root=None, family=None, editor=None, cache_dir=None):
    # Installed editors can be inventoried from any skill installation. This
    # read-only command does not require, fetch or fabricate a complete bundle.
    recovery = None
    try:
        root, info = bundle(root, cache_dir=cache_dir)
    except bundle_helper().BundleUnavailable as error:
        if root is not None:
            raise
        root, info, recovery = None, {'products': []}, error.report
    module = load_module('mcgs_turnkey_installation', SKILL / 'scripts/turnkey_installation.py')
    explicit = ()
    if editor:
        selected_family = family or ('stu' if Path(editor).name.casefold() == 'mcgssetstu.exe' else 'pro')
        explicit = ({'family': selected_family, 'editor_executable': str(Path(editor).resolve())},)
    discovered = module.discover_installations(explicit_paths=explicit)
    installations = discovered['installations']
    if family:
        installations = [item for item in installations if item['family'].casefold() == family.casefold()]
    return {'schema': 1, 'status': 'installation_inventory', 'installations': installations,
            'observations': discovered['observations'],
            'products': info['products'], 'version_policy': 'choice_not_admission',
            'bundle_available': root is not None, 'bundle_root': str(root) if root else None,
            'bundle_recovery': recovery, 'download_performed': False,
            'software_changed': False}


def processes(editor):
    """Read exact editor paths and their UI-thread identity; never switches focus."""
    if os.name != 'nt':
        raise OSError('Windows is required')
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    u = ctypes.WinDLL('user32', use_last_error=True)
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k.Process32FirstW.argtypes = k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    wanted = os.path.normcase(str(Path(editor).resolve()))
    result = []
    snap = k.CreateToolhelp32Snapshot(2, 0)
    if snap == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        more = k.Process32FirstW(snap, ctypes.byref(entry))
        while more:
            if entry.szExeFile.casefold() == Path(editor).name.casefold():
                handle = k.OpenProcess(0x1000, False, entry.th32ProcessID)
                if handle:
                    try:
                        buffer = ctypes.create_unicode_buffer(32768)
                        size = wintypes.DWORD(len(buffer))
                        times = [wintypes.FILETIME() for _ in range(4)]
                        if k.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) and os.path.normcase(str(Path(buffer.value).resolve())) == wanted and k.GetProcessTimes(handle, *[ctypes.byref(item) for item in times]):
                            result.append({'pid': entry.th32ProcessID, 'editor': buffer.value,
                                           'creation_filetime': (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime})
                    finally:
                        k.CloseHandle(handle)
            more = k.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k.CloseHandle(snap)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.GetWindowThreadProcessId.restype = wintypes.DWORD
    u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    u.GetWindow.restype = wintypes.HWND
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    def collect(hwnd, unused):
        pid = wintypes.DWORD()
        tid = u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not u.GetWindow(hwnd, 4) and u.IsWindowVisible(hwnd):
            for row in result:
                if row['pid'] == pid.value:
                    row.setdefault('ui_thread', tid)
        return True
    callback = callback_type(collect)
    u.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    u.EnumWindows(callback, 0)
    return result


def prepare_online(root, editor, install_root=None, pid=None, preparation_timeout=0):
    root, info = bundle(root)
    editor = Path(editor).resolve(strict=True)
    install_root = Path(install_root).resolve(strict=True) if install_root else editor.parent.parent
    if not editor.is_relative_to(install_root):
        raise ValueError('Editor is outside selected installation')
    candidates = [row for row in processes(editor) if pid is None or row['pid'] == pid]
    if len(candidates) != 1 or not candidates[0].get('ui_thread'):
        return {'status': 'select_or_start_editor', 'processes': candidates,
                'meaning': 'Open Pro normally, then supply --pid if several selected editor processes are running; no restart or maximization is required'}
    target = candidates[0]
    asset = SKILL / 'assets/pro-native-bridge'
    env = runtime_env(root, info)
    py = env['MCGS_PYTHON']
    artifacts = contained(root, info['bridge_artifacts'])
    published = read(artifacts / 'portable-bridge-manifest.json')
    bridge_identity = published['identity']
    packaged_client = artifacts / bridge_identity['client_file']
    client_pin = next(row for row in published['artifacts'] if row['file'] == packaged_client.name)
    if not packaged_client.is_file() or digest(packaged_client) != client_pin['sha256']:
        raise ValueError('Packaged portable bridge client differs from its publisher manifest')
    # Discover before creating any connection directory. The same Pro may have
    # been attached from another bundle path or a prior release's launcher.
    discovered = run_json([packaged_client, '--discover', str(target['pid']),
                           str(target['creation_filetime'])], env, timeout=20)
    if discovered.get('host_attached'):
        live = discovered['existing_bridge']
        bootstrap = Path(live['bootstrap_root'])
        runtime = Path(live['runtime_root'])
        config = Path(live['bootstrap_config'])
        if not config.is_file() or digest(config) != live['bootstrap_scope_sha256']:
            raise ValueError('Live bridge configuration changed or is absent; preserve this connection and inspect it, do not attach another bridge')
        actual = read(config)
        selected_file = runtime / 'active-engine.json'
        selected = read(selected_file) if selected_file.is_file() else None
        state = {'schema': 1, 'status': 'bridge_discovered', 'phase': 'queue_not_probed',
                 'target': target, 'task_root': actual['task_root'],
                 'runtime_root': str(runtime), 'bootstrap_root': str(bootstrap),
                 'bootstrap_config': str(config),
                 'bootstrap_scope_sha256': live['bootstrap_scope_sha256'],
                 'hot_attach_config': str(bootstrap / 'hot-attach.json'),
                 'client': str(bootstrap / bridge_identity['client_file']),
                 'receiver_compilation_required': False, 'actual_bridge_status': discovered,
                 'reused_connection': True, 'project_written': False,
                 'native_project_check': 'not_performed',
                 'meaning': 'Reusing the actual live bridge and its current engine scope; no new connection or attach attempt was created'}
        if selected:
            if selected.get('bootstrap_scope_sha256') != live['bootstrap_scope_sha256']:
                raise ValueError('Live bridge engine selection has a different bootstrap scope; inspect it without reattaching')
            engine_scope = Path(selected['assembly']).with_suffix('.scope.json')
            if engine_scope.is_file():
                scope_sha = digest(engine_scope)
                if selected.get('engine_scope_sha256', scope_sha) != scope_sha:
                    raise ValueError('Live engine scope differs from its selection manifest; do not create a competing bridge')
                state.update(scope_config=str(engine_scope), scope_sha256=scope_sha)
            else:
                state.update(phase='existing_engine_scope_unavailable', engine_scope_ready=False)
            state['active_engine'] = selected
        else:
            state.update(phase='existing_engine_not_selected', engine_scope_ready=False)
        state['queue_liveness'] = probe_queue(runtime, py)
        if state['queue_liveness']['verified'] and state.get('scope_config'):
            state.update(status='connected', phase='ready')
        return state
    key = hashlib.sha256((str(editor) + '\n' + digest(editor) + '\n' + info['release']).encode()).hexdigest()[:20]
    task = cache_root() / 'connections' / key / (str(target['pid']) + '-' + str(target['creation_filetime']))
    task.mkdir(parents=True, exist_ok=True)
    journal = task / 'connection.json'
    if journal.exists():
        state = read(journal)
        if state.get('status') in ('connected', 'connect_requested'):
            check = run_json([state['client'], '--status', state['hot_attach_config']])
            return {**state, 'actual_bridge_status': check, 'reused_connection': True,
                    'meaning': 'Inspect actual status after a timeout; never replay an unknown connect or project request'}
        return {**state, 'status': 'preparation_interrupted',
                'meaning': 'Inspect the recorded files and phase before resuming; no automatic retry or compiler fallback'}
    state = {'schema': 1, 'status': 'preparing', 'phase': 'bridge_materialization',
             'target': target, 'task_root': str(task), 'receiver_compilation_required': False,
             'preparation_progress_file': str(task / 'preparation-progress.json'),
             'preparation_timeout_seconds': preparation_timeout,
             'meaning': 'Precompiled engine still requires local interface analysis. Read the progress file; do not restart an uncertain existing preparation.'}
    save(journal, state)
    runtime, payload, boot = task / 'runtime', task / 'payload', task / 'bootstrap'
    for path in (runtime, payload, task / 'tools'):
        path.mkdir(exist_ok=True)
    transport = runtime / 'bridge_client.py'
    shutil.copy2(asset / 'transport/bridge_client.py', transport)
    bridge_result = run_json([py, asset / 'portable-bridge/materialize.py',
        '--artifacts', artifacts, '--task-root', task,
        '--runtime-root', runtime, '--bootstrap-root', boot, '--install-root', install_root,
        '--editor', editor, '--pid', str(target['pid']), '--ui-thread', str(target['ui_thread']),
        '--creation-filetime', str(target['creation_filetime'])], env)
    hot = boot / 'hot-attach.json'
    hot_data = read(hot)
    state.update(phase='business_materialization', hot_attach_config=str(hot), client=hot_data['client'])
    save(journal, state)
    print(json.dumps({'phase': 'business_materialization', 'task_root': str(task),
                      'progress_file': state['preparation_progress_file'],
                      'meaning': 'Local interface analysis is running; inspect this progress file instead of starting another binding.'},
                     ensure_ascii=False), file=sys.stderr, flush=True)
    scope = {'schema': 1, 'task_root': str(task), 'engineering_root': str(payload),
             'runtime_root': str(runtime), 'install_root': str(install_root),
             'transport_client_file': str(transport), 'transport_client_sha256': digest(transport),
             'editor_executable': str(editor)}
    scope_base = task / 'base.scope.json'
    save(scope_base, scope)
    engine = contained(root, info['business_engine'])
    prepared = run_json([py, asset / 'portable-engine/materialize.py',
        '--scope-base-json', scope_base, '--engine-file', engine, '--engine-sha256', digest(engine),
        '--output-directory', runtime / 'business-prepared',
        '--progress-file', task / 'preparation-progress.json'], env,
        timeout=preparation_timeout or None)
    state.update(phase='engine_staging', engine_preparation=prepared)
    save(journal, state)
    staged = run_json([py, asset / 'bootstrap/stage_engine.py', '--bootstrap-root', boot,
        '--engine-file', prepared['engine_file'], '--engine-scope-file', prepared['engine_scope_file']], env)
    active_scope = boot / 'engines' / Path(prepared['engine_scope_file']).name
    state.update(status='connect_requested', phase='host_attach', scope_config=str(active_scope),
                 scope_sha256=digest(active_scope), bridge_preparation=bridge_result, engine_staging=staged)
    save(journal, state)  # An unknown result must never silently reattach/replay.
    connected = run_json([state['client'], '--connect', hot], env, timeout=90)
    liveness = probe_queue(runtime, py)
    state.update(status='connected' if liveness['verified'] else 'bridge_attached_queue_not_confirmed',
                 phase='ready' if liveness['verified'] else 'inspect_queue', connection=connected,
                 queue_liveness=liveness,
                 project_written=False, native_project_check='not_performed')
    save(journal, state)
    return state


def install_skill(root, destination=None):
    root, info = bundle(root)
    source = SKILL if source_matches_engine(root, info) else contained(root, info['skill_directory'])
    destination = Path(destination).expanduser().resolve() if destination else Path.home() / '.codex/skills/mcgs-engineering'
    if destination == source:
        save(destination / 'turnkey-location.json', {'schema': 1, 'bundle_root': str(root), 'release': info['release']})
        return {'status': 'skill_already_at_destination', 'directory': str(destination)}
    if destination.exists():
        backup = destination.with_name(destination.name + '.backup-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
        destination.rename(backup)
    else:
        backup = None
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    save(destination / 'turnkey-location.json', {'schema': 1, 'bundle_root': str(root), 'release': info['release']})
    return {'status': 'skill_installed', 'directory': str(destination), 'previous_backup': str(backup) if backup else None}


def source_matches_engine(root, info):
    """Compare our own release data contract, never vendor version or hash."""
    try:
        engine = contained(root, info['business_engine'])
        release = read(engine.parent / 'portable-engine-manifest.json')
        return (digest(SKILL / 'assets/pro-native-bridge/delivery/source/source-and-dependency-manifest.json') == release['source_manifest_sha256']
                and digest(SKILL / 'assets/pro-native-bridge/abi-adapter/catalogs/source-addresses.json') == release['source_catalog_sha256'])
    except (OSError, ValueError, KeyError):
        return False


def delegate_to_bundle(root, info, args):
    """Run the source and runtime shipped with the selected precompiled engine.

    The receiving skill may be anywhere (including WorkBuddy). Reuse its newer
    Python entry when its own source-data contract matches the engine; otherwise
    use the matching bundled entry. Either way, use bundled Python/Capstone.
    """
    selected_skill = contained(root, info.get('skill_directory', 'skill'))
    script = Path(__file__).resolve() if source_matches_engine(root, info) else selected_skill / 'scripts/turnkey.py'
    python = contained(root, info['python'])
    if script.resolve() == Path(__file__).resolve() and Path(sys.executable).resolve() == python:
        return None
    argv = [python, '-B', '-X', 'utf8', script,
            '--bundle-root', root, args.command]
    parameters = {
        'verify': ('full',),
        'setup': ('family', 'editor', 'interactive', 'mode'),
        'prepare-online': ('editor', 'install_root', 'pid', 'preparation_timeout'),
        'install-skill': ('destination',),
    }
    for name in parameters.get(args.command, ()):
        if name == 'preparation_timeout' and script.resolve() != Path(__file__).resolve() and 'preparation-timeout' not in script.read_text(encoding='utf-8-sig'):
            continue
        value = getattr(args, name, None)
        if value is None or value is False:
            continue
        argv.append('--' + name.replace('_', '-'))
        if value is not True:
            argv.append(str(value))
    return subprocess.run(list(map(os.fspath, argv)), env=runtime_env(root, info)).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-root')
    parser.add_argument('--no-download', action='store_true', help='Discover local bundles only; never compile as fallback')
    parser.add_argument('--cache-dir', help='Shared complete-bundle cache; optional short local directory')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('fetch-bundle', help='Locate or download and verify the published complete bundle; no software installation')
    v = sub.add_parser('verify'); v.add_argument('--full', action='store_true')
    i = sub.add_parser('inventory'); i.add_argument('--family', choices=('pro', 'stu')); i.add_argument('--editor')
    s = sub.add_parser('setup'); s.add_argument('--family', choices=('pro', 'stu'), required=True); s.add_argument('--editor'); s.add_argument('--interactive', action='store_true'); s.add_argument('--mode', choices=('offline', 'online'))
    p = sub.add_parser('prepare-online'); p.add_argument('--editor', required=True); p.add_argument('--install-root'); p.add_argument('--pid', type=int)
    p.add_argument('--preparation-timeout', type=float, default=0,
                   help='Pure-file interface preparation timeout in seconds; 0 waits with progress, native request timeouts are unchanged')
    ins = sub.add_parser('install-skill'); ins.add_argument('--destination')
    for entry in sub.choices.values():
        entry.add_argument('--bundle-root', default=argparse.SUPPRESS)
        entry.add_argument('--no-download', action='store_true', default=argparse.SUPPRESS)
        entry.add_argument('--cache-dir', default=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.command == 'prepare-online' and args.preparation_timeout < 0:
        parser.error('Preparation timeout must be zero or positive')
    if args.command == 'inventory':
        result = inventory(args.bundle_root, args.family, args.editor, args.cache_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    can_fetch = args.command in ('fetch-bundle', 'setup', 'prepare-online') and not args.no_download
    root, info = bundle(args.bundle_root, allow_download=can_fetch, cache_dir=args.cache_dir)
    if args.command == 'fetch-bundle':
        result = {'status': 'complete_bundle_ready', 'bundle_root': str(root), 'release': info['release'],
                  'runtime': {key: str(contained(root, info[key])) for key in ('python', 'powershell')},
                  'receiver_compilation_required': False, 'software_changed': False, 'project_written': False}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    delegated = delegate_to_bundle(root, info, args)
    if delegated is not None:
        return delegated
    if args.command == 'verify':
        result = verify(root, args.full)
    elif args.command == 'install-skill':
        result = install_skill(root, args.destination)
    elif args.command == 'prepare-online':
        result = prepare_online(root, args.editor, args.install_root, args.pid, args.preparation_timeout)
    else:
        module = load_module('mcgs_turnkey_installation', SKILL / 'scripts/turnkey_installation.py')
        result = module.setup_bundle(root, args.family, explicit_editor=args.editor, interactive=args.interactive)
        result['runtime'] = {key: str(contained(root, info[key])) for key in ('python', 'powershell')}
        result['mode'] = 'offline' if args.family == 'stu' else args.mode
        result['mode_prompt'] = None if result['mode'] or not result.get('environment_ready') else '环境已准备好，你选择离线修改还是在线修改？离线直接批量编辑工程文件；在线通过内部接口修改已打开的Pro并可观察变化。'
        result['mode_options'] = ['offline'] if args.family == 'stu' else ['offline', 'online']
        result['project_written'] = False
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        report = getattr(error, 'report', None) or {'status': 'not_complete', 'error': type(error).__name__ + ': ' + str(error),
                          'unknown_mutations_must_not_be_retried': True}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)
