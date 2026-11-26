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
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from turnkey_installation import installation_root_from_editor

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
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['MCGS_BUNDLE_ROOT'] = str(root)
    return env


def cache_root():
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'mcgs-engineering'
    root.mkdir(parents=True, exist_ok=True)
    return root


def probe_queue(runtime, python, transport_file=None, expected=None):
    """One correlated read-only ping; preserves unknown outcomes for inspection."""
    transport = Path(transport_file).resolve() if transport_file else Path(runtime) / 'bridge_client.py'
    if transport.parent != Path(runtime).resolve() or not transport.is_file():
        return {'verified': False, 'status': 'transport_not_at_runtime_root'}
    request_id = 'turnkey-ping-' + uuid.uuid4().hex
    try:
        receipt = run_json([python, '-B', '-X', 'utf8', transport, 'ping', '--id', request_id, '--timeout', '10'], timeout=20)
        identity = {'request_id': request_id, 'op': 'ping', **(expected or {})}
        mismatches = [key for key, value in identity.items() if receipt.get(key) != value]
        return {'verified': receipt.get('ok') is True and not mismatches, 'request_id': request_id,
                'receipt': receipt, 'identity_mismatches': mismatches}
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
        selected_family = online_family(editor, family)
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


def processes(editor=None, family='pro'):
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
    wanted = os.path.normcase(str(Path(editor).resolve())) if editor else None
    wanted_name = Path(editor).name.casefold() if editor else {'pro': 'mcgssetpro.exe', 'stu': 'mcgssetstu.exe'}[family]
    result = []
    snap = k.CreateToolhelp32Snapshot(2, 0)
    if snap == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        more = k.Process32FirstW(snap, ctypes.byref(entry))
        while more:
            if entry.szExeFile.casefold() == wanted_name:
                handle = k.OpenProcess(0x1000, False, entry.th32ProcessID)
                if handle:
                    try:
                        buffer = ctypes.create_unicode_buffer(32768)
                        size = wintypes.DWORD(len(buffer))
                        times = [wintypes.FILETIME() for _ in range(4)]
                        if k.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) and (wanted is None or os.path.normcase(str(Path(buffer.value).resolve())) == wanted) and k.GetProcessTimes(handle, *[ctypes.byref(item) for item in times]):
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


def connection_task_directory(local_cache, key, process_key):
    local_cache = local_cache.resolve()
    identifier = hashlib.sha256((key + '\n' + process_key).encode()).hexdigest()[:24]
    legacy = local_cache / 'connections' / key / process_key
    normal = local_cache / 'c' / identifier
    # Discover and recover any existing journal before choosing a fresh root.
    for candidate in (legacy, normal):
        if (candidate / 'connection.json').is_file():
            return candidate
    # The complete native receipt can include an 80-character request ID
    # and a GUID staging suffix. Reserve their space before attaching the host.
    receipt = Path('rt/engineering/reply-payloads') / ('x' * 80 + '.json.' + '0' * 32 + '.staging')
    def fits(candidate):
        return os.name != 'nt' or len(str(candidate.resolve() / receipt).encode('utf-16-le')) < 520

    if fits(normal):
        return normal
    user_key = hashlib.sha256(str(local_cache).casefold().encode()).hexdigest()[:10]
    fallback = Path(tempfile.gettempdir()).resolve() / ('m-' + user_key) / identifier
    if (fallback / 'connection.json').is_file() or fits(fallback):
        return fallback
    raise ValueError('The native queue path would exceed .NET limits. Use a shorter local TEMP directory for a new connection.')


def reusable_engine_scope(asset, actual, bootstrap, selected, expected_sha, wanted, transport_sha):
    """Fast path only for the current immutable binding on this live queue."""
    if not selected or selected.get('sha256') != expected_sha:
        return None
    assembly = Path(selected['assembly']).resolve()
    scope_file = assembly.with_suffix('.scope.json')
    if (assembly.parent != (Path(bootstrap) / 'engines').resolve()
            or not assembly.is_file() or digest(assembly) != expected_sha
            or not scope_file.is_file() or digest(scope_file) != selected.get('engine_scope_sha256')):
        return None
    scope = read(scope_file)
    for key in ('task_root', 'runtime_root', 'install_root', 'editor_executable'):
        path = Path(scope.get(key, ''))
        if not path.is_absolute() or path.resolve() != Path(actual[key]).resolve():
            return None
    transport = Path(scope.get('transport_client_file', ''))
    if (not transport.is_absolute() or transport.resolve().parent != Path(actual['runtime_root']).resolve()
            or scope.get('transport_client_sha256') != transport_sha
            or not transport.is_file() or digest(transport) != transport_sha):
        return None
    support = load_module('mcgs_turnkey_portable_support', asset / 'portable-engine/portable_support.py')
    data = support.validate_portable_scope(scope)
    if (data and all(data.get(key) == wanted.get(key) for key in ('source_manifest_sha256', 'source_catalog_sha256'))
            and data.get('preparation_input_sha256')
            and data['preparation_input_sha256'] == support.preparation_input_sha256()):
        return scope_file
    return None


def stu_business_engine(root, info):
    if 'stu' not in info.get('business_engines', {}):
        return None
    return bundle_helper().verify_stu_engine(root, info, skill_root=SKILL)


def stu_locator_inputs():
    profile = SKILL / 'assets/stu-native/profile'
    return hashlib.sha256((digest(profile / 'locate.py') + digest(profile / 'reference.json')).encode('ascii')).hexdigest()


def materialize_stu_engine(base, engine, output, name, env, preparation_timeout=0):
    """Bind the precompiled Stu adapter to the shared queue and actual installation."""
    payload = Path(base['engineering_root'])
    evidence = payload / 'task-evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    locator = SKILL / 'assets/stu-native/profile/locate.py'
    editor = Path(base['editor_executable'])
    before_sha = digest(editor)
    inputs_sha = stu_locator_inputs()
    report = run_json([env['MCGS_PYTHON'], '-B', '-X', 'utf8', locator, '--editor', editor],
                      env, timeout=preparation_timeout or None)
    if report.get('product') != 'stu' or report.get('schema') != 1:
        raise ValueError('Current Stu native locator returned a different product or schema')
    if digest(editor) != before_sha or stu_locator_inputs() != inputs_sha:
        raise ValueError('The selected Stu executable or locator changed during file-only preparation')
    index = evidence / 'stu-roles.json'
    save(index, report)
    contract = 'mcgs-portable-engine/v1'
    binding = payload / 'stu-binding.json'
    save(binding, {'schema': 'mcgs-portable-engine-binding/v1', 'engine_contract': contract,
                   'family': 'stu', 'profile_index_file': str(index), 'profile_index_sha256': digest(index),
                   'editor_sha256': before_sha, 'locator_inputs_sha256': inputs_sha})
    output.mkdir(parents=True, exist_ok=True)
    assembly = output / name
    scope = assembly.with_suffix('.scope.json')
    with assembly.open('xb') as target, engine.open('rb') as source:
        shutil.copyfileobj(source, target)
    if digest(assembly) != digest(engine):
        raise ValueError('Materialized Stu engine differs from the packaged bytes')
    save(scope, {**base, 'portable_engine_contract': contract,
                 'portable_binding_file': str(binding), 'portable_binding_sha256': digest(binding)})
    return {'engine_file': str(assembly), 'engine_scope_file': str(scope),
            'scope_sha256': digest(scope), 'receiver_compilation_required': False,
            'capabilities': report.get('capabilities', {})}


def reusable_stu_scope(actual, bootstrap, selected, expected_sha, transport_sha):
    if not selected or selected.get('sha256') != expected_sha:
        return None
    assembly = Path(selected['assembly']).resolve()
    scope_file = assembly.with_suffix('.scope.json')
    if (assembly.parent != (Path(bootstrap) / 'engines').resolve()
            or not assembly.is_file() or digest(assembly) != expected_sha
            or not scope_file.is_file() or digest(scope_file) != selected.get('engine_scope_sha256')):
        return None
    scope = read(scope_file)
    if any(scope.get(key) != actual[key] for key in ('task_root', 'runtime_root', 'install_root', 'editor_executable')):
        return None
    transport = Path(scope.get('transport_client_file', ''))
    if (not transport.is_absolute() or transport.resolve().parent != Path(actual['runtime_root']).resolve()
            or scope.get('transport_client_sha256') != transport_sha
            or not transport.is_file() or digest(transport) != transport_sha):
        return None
    payload = Path(scope.get('engineering_root', ''))
    if not payload.is_absolute() or not (payload / 'task-evidence').is_dir():
        return None
    support = load_module('mcgs_turnkey_portable_support', SKILL / 'assets/pro-native-bridge/portable-engine/portable_support.py')
    binding = support.validate_portable_scope(scope)
    if (not binding or binding.get('family') != 'stu'
            or binding.get('editor_sha256') != actual.get('editor_sha256')
            or binding.get('locator_inputs_sha256') != stu_locator_inputs()):
        return None
    return scope_file


def select_current_engine(root, info, actual, bootstrap, selected, env, preparation_timeout=0, family='pro'):
    """Select the current precompiled business engine on the existing host.

    Materialize paths for this live connection rather than importing another
    machine's scope. Selection is atomic/file-only and does not replay requests.
    """
    asset = SKILL / 'assets/pro-native-bridge'
    runtime, task = Path(actual['runtime_root']), Path(actual['task_root'])
    engine = stu_business_engine(root, info) if family == 'stu' else contained(root, info['business_engine'])
    expected_sha = digest(engine)
    source_transport = asset / 'transport/bridge_client.py'
    transport_sha = digest(source_transport)
    selection_file = runtime / 'active-engine.json'
    selected_digest = digest(selection_file) if selected else None
    if selected and read(selection_file) != selected:
        raise ValueError('Engine selection changed during discovery; inspect the current selection before continuing')
    if family == 'stu':
        current_scope = reusable_stu_scope(actual, bootstrap, selected, expected_sha, transport_sha)
    else:
        wanted = read(engine.parent / 'portable-engine-manifest.json')
        current_scope = reusable_engine_scope(asset, actual, bootstrap, selected, expected_sha, wanted, transport_sha)
    if current_scope is not None:
        if digest(selection_file) != selected_digest:
            raise ValueError('Engine selection changed during discovery; inspect the current selection before continuing')
        return {'changed': False, 'scope_config': str(current_scope),
                'scope_sha256': selected['engine_scope_sha256'], 'active_engine': selected}
    # Each selected DLL basename is immutable while loaded. A short fresh name
    # also permits rematerializing the same DLL after a local path change.
    identifier = expected_sha[:10] + '-' + uuid.uuid4().hex[:6]
    work = task / ('u-' + identifier)
    payload, output = work / 'data', runtime / ('u-' + identifier)
    payload.mkdir(parents=True)
    # The transport uses its own directory as the durable queue root. Keep a
    # content-qualified copy alongside the old client in that same directory.
    transport = runtime / ('bridge_client_' + transport_sha[:16] + '.py')
    try:
        with transport.open('xb') as destination, source_transport.open('rb') as source:
            shutil.copyfileobj(source, destination)
    except FileExistsError:
        pass
    if digest(transport) != transport_sha:
        raise ValueError('The versioned native queue client differs from the current skill: ' + str(transport))
    base = {key: actual[key] for key in ('task_root', 'runtime_root', 'install_root', 'editor_executable')}
    base.update(schema=1, engineering_root=str(payload), transport_client_file=str(transport),
                transport_client_sha256=transport_sha)
    if family == 'stu':
        prepared = materialize_stu_engine(base, engine, output, 'McgsStu.' + identifier + '.dll', env, preparation_timeout)
    else:
        scope_base = work / 'base.json'
        save(scope_base, base)
        prepared = run_json([env['MCGS_PYTHON'], asset / 'portable-engine/materialize.py',
            '--scope-base-json', scope_base, '--engine-file', engine, '--engine-sha256', expected_sha,
            '--engine-file-name', 'McgsEngineering.' + identifier + '.dll',
            '--output-directory', output, '--abi-cache-root', cache_root() / 'native-abi',
            '--progress-file', work / 'prep.json'], env, timeout=preparation_timeout or None)
    if selected:
        result = run_json([env['MCGS_PYTHON'], asset / 'bootstrap/select_engine.py',
            '--bootstrap-root', bootstrap, '--engine-file', prepared['engine_file'],
            '--engine-scope-file', prepared['engine_scope_file'], '--engine-sha256', expected_sha,
            '--engine-scope-sha256', prepared['scope_sha256'],
            '--manifest-sha256', selected_digest], env)
    else:
        result = run_json([env['MCGS_PYTHON'], asset / 'bootstrap/stage_engine.py',
            '--bootstrap-root', bootstrap, '--engine-file', prepared['engine_file'],
            '--engine-scope-file', prepared['engine_scope_file']], env)
    selected = read(runtime / 'active-engine.json')
    active_scope = Path(selected['assembly']).with_suffix('.scope.json')
    return {'changed': True, 'scope_config': str(active_scope), 'scope_sha256': digest(active_scope),
            'active_engine': selected, 'engine_preparation': prepared, 'engine_selection': result,
            'same_pro_process': family == 'pro', 'same_editor_process': True,
            'local_paths_materialized': True, 'receiver_compilation_required': False}


def online_target(editor=None, install_root=None, pid=None, family='pro'):
    """Discover a unique live editor without starting or focusing it."""
    editor = Path(editor).resolve(strict=True) if editor else None
    install_root = Path(install_root).resolve(strict=True) if install_root else None
    if editor and install_root and not editor.is_relative_to(install_root):
        raise ValueError('Editor is outside selected installation')
    if editor and ((editor.name.casefold() == 'mcgssetstu.exe') != (family == 'stu')):
        raise ValueError('The selected editor executable belongs to a different product family')
    candidates = [row for row in processes(editor, family) if (pid is None or row['pid'] == pid)
                  and (install_root is None or Path(row['editor']).resolve().is_relative_to(install_root))]
    if len(candidates) == 1 and candidates[0].get('ui_thread'):
        selected = Path(candidates[0]['editor']).resolve(strict=True)
        return selected, install_root or installation_root_from_editor(selected), candidates[0], None
    installations = []
    if not candidates and not editor:
        module = load_module('mcgs_turnkey_installation', SKILL / 'scripts/turnkey_installation.py')
        installations = [row for row in module.discover_installations()['installations']
                         if row['family'] == family and (install_root is None or
                             Path(row['editor_executable']).resolve().is_relative_to(install_root))]
    return None, None, None, {'status': 'select_or_start_editor', 'processes': candidates,
        'installations': installations, 'editor': str(editor) if editor else None,
        'selected_installation': installations[0] if len(installations) == 1 else None,
        'software_started': False, 'project_written': False,
        'meaning': 'Open the selected editor normally. If several editor processes are running, supply --pid or --editor from these exact candidates.'}


def online_family(editor=None, family=None):
    return family or ('stu' if editor and Path(editor).name.casefold() == 'mcgssetstu.exe' else 'pro')


def prepare_online(root, editor=None, install_root=None, pid=None, preparation_timeout=0, family=None):
    started = time.perf_counter()
    elapsed = {}

    def record_phase(name, phase_start):
        elapsed[name] = round((time.perf_counter() - phase_start) * 1000, 2)

    root, info = bundle(root)
    family = online_family(editor, family)
    stu_engine = stu_business_engine(root, info) if family == 'stu' else None
    if family == 'stu' and stu_engine is None:
        return {'status': 'stu_business_engine_missing', 'family': family, 'online_ready': False,
                'software_started': False, 'project_written': False}
    editor, install_root, target, unresolved = online_target(editor, install_root, pid, family)
    if unresolved:
        return {**unresolved, 'family': family}
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
    phase_start = time.perf_counter()
    discovered = run_json([packaged_client, '--discover', str(target['pid']),
                           str(target['creation_filetime'])], env, timeout=20)
    record_phase('discover', phase_start)
    if discovered.get('host_attached'):
        live = discovered['existing_bridge']
        bootstrap = Path(live['bootstrap_root'])
        runtime = Path(live['runtime_root'])
        config = Path(live['bootstrap_config'])
        if not config.is_file() or digest(config) != live['bootstrap_scope_sha256']:
            raise ValueError('Live bridge configuration changed or is absent; preserve this connection and inspect it, do not attach another bridge')
        actual = read(config)
        if (actual.get('host_kind', 'pro') != family or
                Path(actual['editor_executable']).resolve() != editor):
            raise ValueError('The existing native bridge belongs to another editor family or executable')
        selected_file = runtime / 'active-engine.json'
        selected = read(selected_file) if selected_file.is_file() else None
        state = {'schema': 1, 'family': family, 'status': 'bridge_discovered', 'phase': 'queue_not_probed',
                 'target': target, 'task_root': actual['task_root'],
                 'runtime_root': str(runtime), 'bootstrap_root': str(bootstrap),
                 'bootstrap_config': str(config),
                 'bootstrap_scope_sha256': live['bootstrap_scope_sha256'],
                 'hot_attach_config': str(bootstrap / 'hot-attach.json'),
                 'client': str(bootstrap / bridge_identity['client_file']),
                 'receiver_compilation_required': False, 'actual_bridge_status': discovered,
                 'reused_connection': True, 'project_written': False,
                 'native_project_check': 'not_performed',
                 'meaning': 'Reusing the actual live bridge and selecting the current precompiled engine; no new process or attach attempt was created'}
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
        phase_start = time.perf_counter()
        selected_result = select_current_engine(root, info, actual, bootstrap, selected, env, preparation_timeout, family)
        record_phase('engine_selection', phase_start)
        state.update({key: selected_result[key] for key in ('scope_config', 'scope_sha256', 'active_engine')})
        state.update(engine_scope_ready=True, engine_update=selected_result)
        phase_start = time.perf_counter()
        selected_scope = read(selected_result['scope_config'])
        state['queue_liveness'] = probe_queue(runtime, py, selected_scope['transport_client_file'], {
            'process_id': target['pid'], 'engine_sha256': state['active_engine']['sha256'],
            'engineering_delivery_scope_sha256': state['scope_sha256'],
            'bridge_bootstrap_scope_sha256': state['bootstrap_scope_sha256'],
        })
        record_phase('queue_probe', phase_start)
        record_phase('total', started)
        state['elapsed_ms'] = elapsed
        if state['queue_liveness']['verified']:
            state.update(status='connected', phase='ready')
        else:
            state.update(status='bridge_attached_queue_not_confirmed', phase='inspect_queue')
        return state
    key = hashlib.sha256((str(editor) + '\n' + digest(editor) + '\n' + info['release']).encode()).hexdigest()[:20]
    local_cache = cache_root()
    process_key = str(target['pid']) + '-' + str(target['creation_filetime'])
    task = connection_task_directory(local_cache, key, process_key)
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
    runtime, payload, boot = task / 'rt', task / 'pkg', task / 'boot'
    state = {'schema': 1, 'family': family, 'status': 'preparing', 'phase': 'bridge_materialization',
             'target': target, 'task_root': str(task), 'runtime_root': str(runtime),
             'receiver_compilation_required': False,
             'local_paths_materialized': True,
             'elapsed_ms': elapsed,
             'preparation_progress_file': str(task / 'prep.json'),
             'preparation_timeout_seconds': preparation_timeout,
             'meaning': 'Verifying current modules and preparing the native binding. Read the progress file before resuming an interrupted preparation.'}
    save(journal, state)
    for path in (runtime, payload, task / 'tools'):
        path.mkdir(exist_ok=True)
    transport = runtime / 'bridge_client.py'
    shutil.copy2(asset / 'transport/bridge_client.py', transport)
    phase_start = time.perf_counter()
    bridge_result = run_json([py, asset / 'portable-bridge/materialize.py',
        '--artifacts', artifacts, '--task-root', task,
        '--runtime-root', runtime, '--bootstrap-root', boot, '--install-root', install_root,
        '--editor', editor, '--pid', str(target['pid']), '--ui-thread', str(target['ui_thread']),
        '--creation-filetime', str(target['creation_filetime']), '--host-kind', family], env)
    record_phase('bridge_materialization', phase_start)
    hot = boot / 'hot-attach.json'
    hot_data = read(hot)
    state.update(phase='business_materialization', hot_attach_config=str(hot), client=hot_data['client'])
    save(journal, state)
    print(json.dumps({'phase': 'business_materialization', 'task_root': str(task),
                      'progress_file': state['preparation_progress_file'],
                      'meaning': 'Verifying current modules and reusing matching ABI evidence when available; inspect this progress file instead of starting another binding.'},
                     ensure_ascii=False), file=sys.stderr, flush=True)
    scope = {'schema': 1, 'task_root': str(task), 'engineering_root': str(payload),
             'runtime_root': str(runtime), 'install_root': str(install_root),
             'transport_client_file': str(transport), 'transport_client_sha256': digest(transport),
             'editor_executable': str(editor)}
    phase_start = time.perf_counter()
    if family == 'stu':
        prepared = materialize_stu_engine(scope, stu_engine, runtime / 'engine', stu_engine.name, env, preparation_timeout)
    else:
        scope_base = task / 'base.json'
        save(scope_base, scope)
        engine = contained(root, info['business_engine'])
        prepared = run_json([py, asset / 'portable-engine/materialize.py',
            '--scope-base-json', scope_base, '--engine-file', engine, '--engine-sha256', digest(engine),
            '--output-directory', runtime / 'engine',
            '--abi-cache-root', local_cache / 'native-abi',
            '--progress-file', state['preparation_progress_file']], env,
            timeout=preparation_timeout or None)
    record_phase('business_materialization', phase_start)
    state.update(phase='engine_staging', engine_preparation=prepared)
    save(journal, state)
    phase_start = time.perf_counter()
    staged = run_json([py, asset / 'bootstrap/stage_engine.py', '--bootstrap-root', boot,
        '--engine-file', prepared['engine_file'], '--engine-scope-file', prepared['engine_scope_file']], env)
    record_phase('engine_staging', phase_start)
    active_scope = boot / 'engines' / Path(prepared['engine_scope_file']).name
    state.update(status='connect_requested', phase='host_attach', scope_config=str(active_scope),
                 scope_sha256=digest(active_scope), bridge_preparation=bridge_result, engine_staging=staged)
    save(journal, state)  # An unknown result must never silently reattach/replay.
    phase_start = time.perf_counter()
    connected = run_json([state['client'], '--connect', hot], env, timeout=90)
    record_phase('host_attach', phase_start)
    phase_start = time.perf_counter()
    active_engine = read(runtime / 'active-engine.json')
    liveness = probe_queue(runtime, py, expected={
        'process_id': target['pid'], 'engine_sha256': staged['engine_sha256'],
        'engineering_delivery_scope_sha256': state['scope_sha256'],
        'bridge_bootstrap_scope_sha256': staged['bootstrap_scope_sha256'],
    })
    record_phase('queue_probe', phase_start)
    record_phase('total', started)
    state.update(status='connected' if liveness['verified'] else 'bridge_attached_queue_not_confirmed',
                 phase='ready' if liveness['verified'] else 'inspect_queue', connection=connected,
                 queue_liveness=liveness,
                 active_engine=active_engine,
                 project_written=False, native_project_check='not_performed')
    save(journal, state)
    return state


def migrate_legacy_skill_backups(scan_root, destination, transaction_root):
    """Move only identifiable MCGS installer backups, retaining a durable journal."""
    records = []
    pattern = re.compile(re.escape(destination.name) + r'\.backup-\d{8}-\d{6}(?:-[A-Za-z0-9]+)?\Z')
    for candidate in sorted(scan_root.iterdir()):
        if not pattern.fullmatch(candidate.name):
            continue
        record = {'source': str(candidate), 'status': 'preserved_unrecognized_backup'}
        records.append(record)
        try:
            # Junctions and symlinks must never redirect a migration out of this root.
            if (candidate.is_symlink() or getattr(candidate.lstat(), 'st_file_attributes', 0) & 0x400
                    or not candidate.is_dir() or candidate.resolve().parent != scan_root):
                record['reason'] = 'not_a_plain_direct_child_directory'
                continue
            skill = candidate / 'SKILL.md'
            identity_files = [skill, candidate / 'scripts/turnkey.py',
                              candidate / 'assets/pro-native-bridge/delivery/source/source-and-dependency-manifest.json']
            if any(not path.is_file() or not path.resolve().is_relative_to(candidate) for path in identity_files):
                record['reason'] = 'missing_or_redirected_skill_identity_files'
                continue
            header = skill.read_text(encoding='utf-8-sig').split('---', 2)
            if len(header) != 3 or header[0].strip() or not re.search(
                    r'^name:\s*[\"\']?mcgs-engineering[\"\']?\s*$', header[1], re.MULTILINE):
                record['reason'] = 'different_skill_identity'
                continue
            if candidate.stat().st_dev != transaction_root.stat().st_dev:
                raise ValueError('Legacy backup migration requires the same volume: ' + str(candidate))
            target = transaction_root / (candidate.name + '-migrated-' + uuid.uuid4().hex)
            receipt = transaction_root / (target.name + '.migration.json')
            record.update(destination=str(target), receipt=str(receipt), status='migration_prepared',
                          skill_sha256=digest(skill), user_files_preserved=True)
            save(receipt, record)
            candidate.rename(target)
            record['status'] = 'migrated'
            save(receipt, record)
        except (OSError, ValueError) as error:
            # Never delete or copy-delete; a prepared receipt identifies either location.
            record.update(status='migration_failed', error=str(error))
            raise ValueError('Legacy skill backup migration failed at ' + str(candidate) + ': ' + str(error)) from error
    return records


def install_skill(root, destination=None, *, family='pro'):
    destination = Path(destination or Path.home() / '.codex/skills/mcgs-engineering').expanduser().resolve()
    if destination.is_dir() and ((destination / '.system').is_dir() or any(
            (child / 'SKILL.md').is_file() for child in destination.iterdir() if child.is_dir())):
        child_destination = destination / 'mcgs-engineering'
        raise ValueError(f'Skill destination {destination} is a skill scan directory. Pass a child path such as {child_destination}.')
    root, info = bundle(root)
    if not source_matches_engine(root, info):
        raise ValueError('Fetch the matching precompiled update before installing; the current skill will not be downgraded')
    source = SKILL
    delivery = load_module('mcgs_turnkey_delivery', SKILL / 'scripts/turnkey_delivery.py')
    helper = bundle_helper()
    contract = delivery.source_contract(source, helper, family=family)
    engine = contained(root, info['business_engine'])
    location = {'schema': 1, 'bundle_root': str(root), 'release': info['release'],
                'source_contract': contract, 'packaged_engine_sha256': digest(engine)}
    if family == 'stu':
        stu = stu_business_engine(root, info)
        if stu is None or not delivery.matches(root, info, contract, helper):
            raise ValueError('The bundle needs the matching precompiled Stu engine before installing')
        location['packaged_stu_engine_sha256'] = digest(stu)
    if destination != source and (destination.is_relative_to(source) or source.is_relative_to(destination)):
        raise ValueError('Skill source and installation directories cannot contain each other')
    scan_root = destination.parent
    transaction_root = (scan_root.parent / '.mcgs-skill-install').resolve()
    if transaction_root.is_relative_to(scan_root) or transaction_root.is_relative_to(source):
        raise ValueError('Skill installation needs a transaction directory outside the skill scan root and source')
    scan_root.mkdir(parents=True, exist_ok=True)
    transaction_root.mkdir(parents=True, exist_ok=True)
    if transaction_root.stat().st_dev != scan_root.stat().st_dev:
        raise ValueError('Skill installation needs a transaction directory on the same volume as the destination')
    migrated = migrate_legacy_skill_backups(scan_root, destination, transaction_root)
    if destination == source:
        save(destination / 'turnkey-location.json', location)
        return {'status': 'skill_already_at_destination', 'directory': str(destination), **location,
                'legacy_backups': migrated}
    backup = None
    with tempfile.TemporaryDirectory(prefix='staging-', dir=transaction_root) as staging:
        prepared = Path(staging) / 'skill'
        shutil.copytree(source, prepared, ignore=shutil.ignore_patterns(
            '__pycache__', '*.pyc', '*.pyo', '.git', '.venv', 'local-artifacts', 'turnkey-location.json'))
        if delivery.source_contract(prepared, helper, family=family) != contract:
            raise ValueError('The copied skill source contract differs from the chosen source')
        save(prepared / 'turnkey-location.json', location)
        if destination.exists():
            backup = transaction_root / (
                destination.name + '.backup-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex)
            destination.rename(backup)
        try:
            prepared.rename(destination)
        except OSError:
            if backup is not None and not destination.exists():
                backup.rename(destination)
            raise
    return {'status': 'skill_installed', 'directory': str(destination), **location,
            'previous_backup': str(backup) if backup else None, 'legacy_backups': migrated}


def source_matches_engine(root, info):
    """Compare our own release data contract, never vendor version or hash."""
    try:
        engine = contained(root, info['business_engine'])
        release = read(engine.parent / 'portable-engine-manifest.json')
        return (digest(engine) == release['sha256']
                and digest(SKILL / 'assets/pro-native-bridge/delivery/source/source-and-dependency-manifest.json') == release['source_manifest_sha256']
                and digest(SKILL / 'assets/pro-native-bridge/abi-adapter/catalogs/source-addresses.json') == release['source_catalog_sha256'])
    except (OSError, ValueError, KeyError):
        return False


def delegate_to_bundle(root, info, args):
    """Use bundled Python with the current entry; never delegate to an old skill."""
    script = Path(__file__).resolve()
    python = contained(root, info['python'])
    if Path(sys.executable).resolve() == python:
        return None
    argv = [python, '-B', '-X', 'utf8', script,
            '--bundle-root', root, args.command]
    if getattr(args, 'no_download', False):
        argv.append('--no-download')
    if getattr(args, 'cache_dir', None):
        argv.extend(['--cache-dir', args.cache_dir])
    parameters = {
        'verify': ('full',),
        'setup': ('family', 'editor', 'interactive', 'mode'),
        'prepare-online': ('editor', 'install_root', 'pid', 'preparation_timeout', 'family'),
        'install-skill': ('destination', 'family'),
    }
    for name in parameters.get(args.command, ()):
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
    fetch = sub.add_parser('fetch-bundle', help='Locate or download and verify the published complete bundle; no software installation')
    fetch.add_argument('--family', choices=('pro', 'stu'))
    v = sub.add_parser('verify'); v.add_argument('--full', action='store_true')
    i = sub.add_parser('inventory'); i.add_argument('--family', choices=('pro', 'stu')); i.add_argument('--editor')
    s = sub.add_parser('setup'); s.add_argument('--family', choices=('pro', 'stu'), required=True); s.add_argument('--editor'); s.add_argument('--interactive', action='store_true'); s.add_argument('--mode', choices=('offline', 'online'))
    p = sub.add_parser('prepare-online'); p.add_argument('--editor'); p.add_argument('--install-root'); p.add_argument('--pid', type=int)
    p.add_argument('--family', choices=('pro', 'stu'))
    p.add_argument('--preparation-timeout', type=float, default=0,
                   help='Pure-file interface preparation timeout in seconds; 0 waits with progress, native request timeouts are unchanged')
    ins = sub.add_parser('install-skill'); ins.add_argument('--destination'); ins.add_argument('--family', choices=('pro', 'stu'))
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
    can_fetch = args.command in ('fetch-bundle', 'setup', 'prepare-online', 'install-skill') and not args.no_download
    root, info = bundle(args.bundle_root, allow_download=can_fetch, cache_dir=args.cache_dir)
    family = online_family(getattr(args, 'editor', None), getattr(args, 'family', None))
    needs_engine = (args.command in ('fetch-bundle', 'prepare-online', 'install-skill')
                    or args.command == 'setup' and args.mode == 'online')
    if needs_engine:
        delivery = load_module('mcgs_turnkey_delivery', SKILL / 'scripts/turnkey_delivery.py')
        helper = bundle_helper()
        try:
            root, info = delivery.ensure_matching(SKILL, root, info, helper,
                                                  allow_download=can_fetch, cache_dir=args.cache_dir, family=family)
        except helper.BundleUnavailable as error:
            if args.command != 'setup' or family != 'stu':
                raise
            result = {**error.report, 'status': 'unsupported_mode', 'family': family, 'mode': 'online',
                      'mode_options': ['offline'], 'environment_ready': False, 'online_ready': False,
                      'missing_component': 'precompiled_stu_business_engine',
                      'software_changed': False, 'project_written': False}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2
    if args.command == 'fetch-bundle':
        result = {'status': 'complete_bundle_ready', 'bundle_root': str(root), 'release': info['release'],
                  'family': family,
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
        result = install_skill(root, args.destination, family=family)
    elif args.command == 'prepare-online':
        result = prepare_online(root, args.editor, args.install_root, args.pid, args.preparation_timeout, args.family)
    else:
        module = load_module('mcgs_turnkey_installation', SKILL / 'scripts/turnkey_installation.py')
        result = module.setup_bundle(root, args.family, explicit_editor=args.editor, interactive=args.interactive)
        result['runtime'] = {key: str(contained(root, info[key])) for key in ('python', 'powershell')}
        try:
            online_available = args.family == 'pro' or stu_business_engine(root, info) is not None
        except (OSError, ValueError, KeyError, TypeError) as error:
            online_available = False
            result['online_preparation_detail'] = str(error)
        result['mode'] = args.mode if online_available else 'offline'
        editor_ready = result.get('editor_ready', result.get('environment_ready', False))
        if editor_ready and result['mode'] == 'offline':
            probe = load_module('mcgs_ace_probe', SKILL / 'scripts/ace_probe.py')
            result.update(probe.offline_status(powershell=contained(root, info['powershell'])))
            result['environment_ready'] = bool(result.get('offline_ready'))
        elif editor_ready and result['mode'] == 'online':
            result['environment_ready'] = True
            result['online_ready'] = None  # prepare-online must inspect the live bridge.
            result['online_preparation_required'] = True
            result['ace_required'] = False
        result['mode_prompt'] = None if result['mode'] or not editor_ready else '环境已准备好，你选择离线修改还是在线修改？离线直接批量编辑工程文件。在线接入已打开的编辑器，使用当前支持的原生功能。'
        result['mode_options'] = ['offline', 'online'] if online_available else ['offline']
        result['mode_selection_required'] = bool(editor_ready and result['mode'] is None)
        result['project_written'] = False
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == 'setup' and not result.get('environment_ready'):
        return 2
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        report = getattr(error, 'report', None) or {'status': 'not_complete', 'error': type(error).__name__ + ': ' + str(error),
                          'unknown_mutations_must_not_be_retried': True}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)
