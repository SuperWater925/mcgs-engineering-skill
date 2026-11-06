"""Discover MCGS installations and carry out an explicitly selected in-place reinstall.

Discovery/plan/status are read-only. Actual install phases are separate, journaled
operations. Vendor programs are never run merely to inspect their version.
"""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid


FAMILIES = {'pro': 'Pro', 'mcgspro': 'Pro', 'stu': 'Stu', 'mcgsstu': 'Stu'}
EDITOR_NAMES = {'Pro': 'McgsSetPro.exe', 'Stu': 'McgsSetStu.exe'}
UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall'
LOCAL_USER_DIRS = ('Work', 'Samples', 'Program/project', 'Program/bakprj_MCP',
                   'Program/bakprj_MCS', 'Program/export')


def utc():
    return datetime.now(timezone.utc).isoformat()


def family_name(value):
    key = str(value).strip().casefold()
    if key not in FAMILIES:
        raise ValueError('Choose McgsPro or McgsStu explicitly')
    return FAMILIES[key]


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(path, *, must_exist=False):
    value = Path(path)
    if not value.is_absolute():
        raise ValueError('Use an absolute path: ' + str(path))
    return value.resolve(strict=must_exist)


def inside(path, root):
    return canonical(path).is_relative_to(canonical(root))


def write_new_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def replace_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    write_new_json(temporary, value)
    os.replace(temporary, path)


def executable_version(path):
    """Read VS_FIXEDFILEINFO four-part versions, not the shorter ARP display string."""
    if os.name != 'nt':
        raise OSError('Windows file resources are required for executable discovery')
    path = str(canonical(path, must_exist=True))
    api = ctypes.WinDLL('version', use_last_error=True)
    api.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    api.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    api.GetFileVersionInfoW.restype = wintypes.BOOL
    api.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    api.VerQueryValueW.restype = wintypes.BOOL
    unused = wintypes.DWORD()
    size = api.GetFileVersionInfoSizeW(path, ctypes.byref(unused))
    if not size:
        return {'file_version': None, 'product_version': None, 'product_name': None, 'version_source': 'resource_absent'}
    data = ctypes.create_string_buffer(size)
    if not api.GetFileVersionInfoW(path, 0, size, data):
        raise ctypes.WinError(ctypes.get_last_error())
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if not api.VerQueryValueW(data, '\\', ctypes.byref(pointer), ctypes.byref(length)) or length.value < 52:
        raise ValueError('Executable has no complete VS_FIXEDFILEINFO')
    values = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD))
    if values[0] != 0xFEEF04BD:
        raise ValueError('Executable version resource signature differs')
    number = lambda high, low: '.'.join(str(v) for v in (high >> 16, high & 65535, low >> 16, low & 65535))
    result = {'file_version': number(values[2], values[3]), 'product_version': number(values[4], values[5]),
              'product_name': None, 'version_source': 'VS_FIXEDFILEINFO'}
    if api.VerQueryValueW(data, r'\VarFileInfo\Translation', ctypes.byref(pointer), ctypes.byref(length)) and length.value >= 4:
        translation = ctypes.cast(pointer, ctypes.POINTER(wintypes.WORD))
        for offset in range(0, length.value // 2 - 1, 2):
            key = r'\StringFileInfo\%04x%04x\ProductName' % (translation[offset], translation[offset + 1])
            if api.VerQueryValueW(data, key, ctypes.byref(pointer), ctypes.byref(length)) and length.value:
                result['product_name'] = ctypes.wstring_at(pointer, length.value).rstrip('\0')
                break
    return result


def registry_installations():
    if os.name != 'nt':
        raise OSError('Windows registry discovery is unavailable')
    import winreg
    result = []
    for hive_name, hive in [('HKLM', winreg.HKEY_LOCAL_MACHINE), ('HKCU', winreg.HKEY_CURRENT_USER)]:
        for bits, view in [(32, winreg.KEY_WOW64_32KEY), (64, winreg.KEY_WOW64_64KEY)]:
            try:
                root = winreg.OpenKey(hive, UNINSTALL_KEY, 0, winreg.KEY_READ | view)
            except (FileNotFoundError, PermissionError):
                continue
            with root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    name = winreg.EnumKey(root, index)
                    try:
                        with winreg.OpenKey(root, name) as key:
                            row = {'registry_hive': hive_name, 'registry_view': bits, 'registry_key': UNINSTALL_KEY + '\\' + name}
                            for item in ('DisplayName', 'DisplayVersion', 'InstallLocation', 'DisplayIcon',
                                         'UninstallString', 'QuietUninstallString', 'WindowsInstaller', 'Publisher'):
                                try:
                                    row[item] = winreg.QueryValueEx(key, item)[0]
                                except FileNotFoundError:
                                    row[item] = None
                        if re.search(r'mcgspro|mcgsstu', str(row['DisplayName']), re.I):
                            result.append(row)
                    except (FileNotFoundError, PermissionError):
                        continue
    return result


def registry_associations():
    if os.name != 'nt':
        raise OSError('Windows registry discovery is unavailable')
    import winreg
    result = []
    for family, extension in [('Pro', '.mcp'), ('Stu', '.mcs')]:
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, extension) as key:
                progid = winreg.QueryValueEx(key, '')[0]
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, str(progid) + r'\shell\open\command') as key:
                command = winreg.QueryValueEx(key, '')[0]
            result.append({'family': family, 'extension': extension, 'progid': progid, 'command': command})
        except (FileNotFoundError, PermissionError):
            continue
    return result


def _exe_prefix(command):
    """Separate a registered executable without passing registry text to a shell."""
    text = str(command or '').strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        if end < 0:
            raise ValueError('Registered executable has an unmatched quote')
        return text[1:end], text[end + 1:].strip()
    matches = list(re.finditer(r'(?i)\.exe(?=\s|$)', text))
    candidates = [(text[:m.end()], text[m.end():].strip()) for m in matches if Path(text[:m.end()]).is_file()]
    if len(candidates) != 1:
        raise ValueError('Registered unquoted executable path is absent or ambiguous')
    return candidates[0]


def _editor_from_command(command):
    try:
        file, unused = _exe_prefix(command)
        return canonical(file, must_exist=True)
    except (ValueError, OSError):
        return None


def _family_from_text(value):
    found = [family for token, family in [('mcgspro', 'Pro'), ('mcgsstu', 'Stu')] if token in str(value).casefold()]
    return found[0] if len(found) == 1 else None


def discover_installations(explicit_paths=(), registry_rows=None, associations=None, *, version_reader=None):
    """Inject snapshots/version_reader for file-only fixtures; production reads Windows."""
    rows = registry_installations() if registry_rows is None else registry_rows
    links = registry_associations() if associations is None else associations
    reader = version_reader or executable_version
    candidates = {}
    observations = []

    def add(file, family, origin, registry=None, root=None):
        try:
            image = canonical(file, must_exist=True)
            if not image.is_file():
                return
            info = reader(image)
            actual_family = _family_from_text(info.get('product_name')) or _family_from_text(image.name) or family
            if actual_family not in EDITOR_NAMES or actual_family != family:
                observations.append({'source': origin, 'status': 'different_product', 'executable': str(image)})
                return
            install = canonical(root) if root else (image.parent.parent if image.parent.name.casefold() == 'program' else image.parent)
            if not image.is_relative_to(install) or install == Path(install.anchor):
                raise ValueError('Installation root does not contain its editor or is a whole volume')
            identity = hashlib.sha256((family + '\0' + os.path.normcase(str(image))).encode('utf-8')).hexdigest()
            item = candidates.setdefault(identity, {'installation_id': identity, 'family': family, 'editor_executable': str(image),
                'install_root': str(install), 'file_version': info.get('file_version'), 'product_version': info.get('product_version'),
                'product_name': info.get('product_name'), 'version_source': info.get('version_source'),
                'editor_sha256': digest_file(image), 'discovery_sources': [], 'uninstall_records': []})
            item['discovery_sources'].append(origin)
            if registry is not None:
                record = {key: registry.get(key) for key in ('registry_hive','registry_view','registry_key','DisplayName',
                    'DisplayVersion','UninstallString','QuietUninstallString','WindowsInstaller','Publisher')}
                if record not in item['uninstall_records']:
                    item['uninstall_records'].append(record)
        except (OSError, ValueError) as error:
            observations.append({'source': origin, 'status': 'unavailable', 'reason': str(error)})

    for row in rows:
        family = _family_from_text(row.get('DisplayName'))
        if not family:
            continue
        root = row.get('InstallLocation')
        roots = []
        if root and Path(root).is_dir():
            roots.append(canonical(root))
        try:
            uninstall_exe, unused = _exe_prefix(row.get('UninstallString'))
            uninstall_path = canonical(uninstall_exe, must_exist=True)
            # Observed MCGS Wise layout: <root>/Program/<product>_Log/UNWISE.EXE.
            if uninstall_path.name.casefold() == 'unwise.exe' and uninstall_path.parent.parent.name.casefold() == 'program':
                roots.append(uninstall_path.parent.parent.parent)
        except (OSError, ValueError):
            pass
        for install in dict.fromkeys(roots):
            for image in (install/'Program'/EDITOR_NAMES[family], install/EDITOR_NAMES[family]):
                if image.is_file():
                    add(image, family, 'uninstall_registry', row, install)
        for link in links:
            if link.get('family') == family:
                image = _editor_from_command(link.get('command'))
                if image and any(image.is_relative_to(candidate) for candidate in roots):
                    add(image, family, 'file_association_and_registry', row,
                        next(candidate for candidate in roots if image.is_relative_to(candidate)))
    for link in links:
        image = _editor_from_command(link.get('command'))
        if image:
            add(image, family_name(link['family']), 'file_association')
    for selected in explicit_paths:
        family = family_name(selected['family'])
        add(selected['editor_executable'], family, 'explicit_path', root=selected.get('install_root'))
    result = sorted(candidates.values(), key=lambda item: (item['family'], item['editor_executable'].casefold()))
    for item in result:
        item['registered_installation'] = bool(item['uninstall_records'])
        item['uninstall_command_count'] = len({row.get('UninstallString') for row in item['uninstall_records'] if row.get('UninstallString')})
        item['selection_required'] = sum(other['family'] == item['family'] for other in result) > 1
    return {'schema': 'mcgs-installations/v1', 'installations': result, 'observations': observations,
            'software_started': False, 'registry_written': False}


def evaluate_installation(installation, product):
    family = family_name(product['family'])
    if installation is not None and installation['family'] != family:
        raise ValueError('Installed and bundled product families differ')
    bundled = str(product.get('version') or product.get('file_version') or '')
    local = installation.get('file_version') if installation else None
    if not bundled:
        raise ValueError('Bundle product must declare its full installed editor version')
    state = 'not_installed' if installation is None else 'unknown' if not local else 'same' if local == bundled else 'different'
    return {'family': family, 'installed_version': local, 'bundle_version': bundled, 'comparison': state,
            'comparison_source': 'editor_full_file_version', 'registry_display_version_used_as_gate': False,
            'file_hash_difference_triggers_reinstall': False, 'default_choice': 'current',
            'choices': ['install', 'cancel'] if installation is None else ['current', 'reinstall', 'cancel'] if state != 'same' else ['current', 'cancel'],
            'install_root': installation['install_root'] if installation else product.get('default_install_root', 'C:/Mcgs'+family),
            'editor_executable': installation['editor_executable'] if installation else None}


def parse_uninstall_command(installation):
    records = installation.get('uninstall_records', [])
    commands = {row.get('UninstallString') for row in records if row.get('UninstallString')}
    if len(commands) != 1:
        raise ValueError('Choose one registered uninstaller; portable/multiple records cannot be replaced by deleting a directory')
    command = next(iter(commands))
    bare_msi=re.match(r'^\s*msiexec(?:\.exe)?\s+(.*)$',command,re.IGNORECASE)
    if bare_msi:
        exe=str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32'/'msiexec.exe');remainder=bare_msi.group(1)
    else:exe, remainder = _exe_prefix(command)
    file = canonical(exe, must_exist=True)
    root = canonical(installation['install_root'], must_exist=True)
    if file.name.casefold() == 'unwise.exe':
        log = remainder.strip().strip('"')
        if not log or not Path(log).is_file():
            raise ValueError('Registered Wise command does not name one actual INSTALL.LOG')
        log = canonical(log, must_exist=True)
        if log.name.casefold() != 'install.log' or log.parent != file.parent or not file.is_relative_to(root):
            raise ValueError('Registered Wise log/uninstaller is outside the selected installation')
        return {'kind': 'registered-wise-log', 'executable': str(file), 'arguments': [str(log)],
                'working_directory': str(file.parent), 'silent_parameters_verified': False,
                'registered_command': command, 'log_sha256': digest_file(log), 'executable_sha256': digest_file(file)}
    msi = [row for row in records if row.get('WindowsInstaller') == 1]
    if file.name.casefold() == 'msiexec.exe' and msi:
        product_codes = {Path(str(row['registry_key'])).name for row in msi}
        if len(product_codes) != 1 or not re.fullmatch(r'\{[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}', next(iter(product_codes))):
            raise ValueError('Windows Installer product code is ambiguous')
        return {'kind': 'registered-msi', 'executable': str(file),
                'arguments': ['/x', next(iter(product_codes)), '/norestart'],
                'working_directory': str(file.parent), 'silent_parameters_verified': True,
                'registered_command': command, 'executable_sha256': digest_file(file)}
    raise ValueError('Registered uninstaller requires a product-specific reviewed adapter; no shell command or guessed switches will run')


def make_plan(installation, product, choice, *, backup_root=None, bundle_root=None, version_reader=None):
    if choice not in ('current', 'reinstall', 'install', 'cancel'):
        raise ValueError('Use an explicit current/reinstall/install/cancel choice')
    evaluation = evaluate_installation(installation, product)
    if choice not in evaluation['choices']:
        raise ValueError('This choice is unavailable for the selected installation state')
    plan = {'schema': 'mcgs-reinstall-plan/v1', 'plan_id': uuid.uuid4().hex, 'created_utc': utc(),
            'choice': choice, 'installation': installation, 'version_comparison': evaluation,
            'registry_or_software_changed': False}
    if choice == 'cancel':
        plan['next_step'] = 'cancelled'
        return plan
    if choice == 'current':
        plan.update(next_step='analyze_current_installation', analysis={
            'family': installation['family'], 'editor_executable': installation['editor_executable'],
            'install_root': installation['install_root'], 'file_version': installation.get('file_version'),
            'derive_current_function_and_RTTI_profiles': installation['family'] == 'Pro',
            'software_version_gate': False, 'recompile_or_reinstall_required_by_this_choice': False})
        return plan
    root = canonical(evaluation['install_root'], must_exist=choice == 'reinstall')
    if root == Path(root.anchor):
        raise ValueError('Installation root cannot be a whole drive')
    backup = canonical(backup_root) if backup_root is not None else None
    if choice == 'reinstall':
        if backup is None or backup == root or backup.is_relative_to(root) or root.is_relative_to(backup) or backup == Path(backup.anchor):
            raise ValueError('Backup must be a separate directory outside the complete selected installation tree')
        if backup.exists():
            raise FileExistsError('Choose a fresh backup path; existing backups are preserved')
    elif root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError('Fresh target contains files; identify its installation before choosing an installer')
    installer = product.get('installer') or {}
    file = Path(installer.get('file') or installer.get('path') or '')
    if not file.is_absolute():
        if bundle_root is None:
            raise ValueError('A relative installer needs an explicit bundle root')
        base = canonical(bundle_root, must_exist=True)
        file = (base/file).resolve(strict=True)
        if not file.is_relative_to(base):
            raise ValueError('Bundled installer escapes the bundle root')
    file = canonical(file, must_exist=True)
    expected = installer.get('sha256')
    if not re.fullmatch(r'[a-fA-F0-9]{64}', str(expected)) or digest_file(file) != expected.lower():
        raise ValueError('Bundled installer SHA differs from the selected manifest')
    if file.is_relative_to(root):
        raise ValueError('Installer must be outside the directory that the uninstaller may remove')
    uninstall = None
    if choice == 'reinstall':
        uninstall = parse_uninstall_command(installation)
        reader = version_reader or executable_version
        actual = reader(installation['editor_executable'])
        if actual.get('file_version') != installation.get('file_version') or digest_file(installation['editor_executable']) != installation['editor_sha256']:
            raise ValueError('Selected installation changed since discovery; refresh before making a new plan')
    editor = root/'Program'/product.get('editor_name', EDITOR_NAMES[evaluation['family']])
    plan.update(next_step='close_selected_editors_then_backup' if installation else 'launch_vendor_install_wizard',
        original_install_root=str(root), expected_editor_executable=str(editor),
        backup_root=str(backup) if backup else None, expected_installed_version=evaluation['bundle_version'], uninstall=uninstall,
        install={'kind': 'vendor-wizard', 'executable': str(file), 'arguments': [],
                 'working_directory': str(file.parent), 'executable_sha256': expected.lower(),
                 'target_directory': str(root), 'directory_parameter_verified': False,
                 'handoff': 'AI must select the recorded original directory in the vendor wizard; do not guess /D or MSI properties'},
        restore={'automatic_vendor_binary_overwrite': False, 'user_data_merge_after_version_verification': True,
                 'conflicting_library_config_and_driver_files': 'preserve_both_and_report'},
        summary='Back up the complete old root, run its registered uninstaller, and install the bundled product into the same root.' if installation else 'Install the bundled product into the selected default directory through its original wizard.')
    return plan


def _plan(path):
    value = read_json(path)
    if value.get('schema') != 'mcgs-reinstall-plan/v1' or value.get('choice') not in ('reinstall','install'):
        raise ValueError('This operation needs the explicit reinstall/install plan')
    root = canonical(value['original_install_root'])
    if root == Path(root.anchor):
        raise ValueError('The selected installation root cannot be a whole volume')
    return value


def _powershell_processes():
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,ExecutablePath,CreationDate | ConvertTo-Json -Compress"],
        capture_output=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise OSError('Could not enumerate current process paths without changing the system')
    rows = json.loads(result.stdout)
    return rows if isinstance(rows, list) else [rows]


def selected_processes(install_root, process_rows=None):
    root = canonical(install_root)
    result = []
    for row in _powershell_processes() if process_rows is None else process_rows:
        file = row.get('ExecutablePath') or row.get('executable')
        if file and canonical(file).is_relative_to(root):
            result.append({'pid': int(row.get('ProcessId', row.get('pid'))), 'executable': str(canonical(file)),
                           'creation': str(row.get('CreationDate', row.get('creation', '')))})
    return result


def backup_plan(plan_file, *, process_rows=None):
    plan = _plan(plan_file)
    if plan['choice'] != 'reinstall':
        raise ValueError('Fresh installation does not have an old root to back up')
    running = selected_processes(plan['original_install_root'], process_rows)
    if running:
        return {'ok': False, 'phase': 'awaiting_normal_editor_close', 'running': running,
                'force_terminate': False, 'installer_started': False}
    source = canonical(plan['original_install_root'], must_exist=True)
    target = canonical(plan['backup_root'])
    if target.is_relative_to(source) or source.is_relative_to(target) or target.exists():
        raise ValueError('Backup destination changed or is not a fresh separate directory')
    target.mkdir(parents=True, exist_ok=False)
    data_root = target/'installation'
    data_root.mkdir()
    rows, skipped = [], []
    try:
        for current, dirs, names in os.walk(source, followlinks=False):
            keep = []
            for name in dirs:
                path = Path(current)/name
                if path.is_symlink() or path.resolve() != path.absolute():
                    skipped.append({'path':path.relative_to(source).as_posix(), 'reason':'external_link_not_followed'})
                else:
                    keep.append(name)
            dirs[:] = keep
            for name in names:
                path = Path(current)/name
                relative = path.relative_to(source)
                if path.is_symlink() or not path.resolve().is_relative_to(source):
                    skipped.append({'path':relative.as_posix(), 'reason':'external_link_not_followed'})
                    continue
                destination = data_root/relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                before = path.stat()
                shutil.copy2(path, destination)
                after = path.stat()
                checksum = digest_file(destination)
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or checksum != digest_file(path):
                    raise ValueError('Source changed while backing up: ' + relative.as_posix())
                rows.append({'file':relative.as_posix(), 'bytes':after.st_size, 'sha256':checksum})
        if skipped:
            raise ValueError('Some installation links were not followed; review their targets before uninstalling')
        proof = {'schema':'mcgs-installation-backup/v1', 'plan_id':plan['plan_id'],
                 'source_root':str(source), 'backup_root':str(data_root), 'files':rows,
                 'complete':True, 'skipped':skipped, 'created_utc':utc(),
                 'restore_vendor_binary_overwrite':False}
        write_new_json(target/'backup-manifest.json', proof)
        return {'ok':True, 'phase':'backup_complete', 'manifest':str(target/'backup-manifest.json'),
                'files':len(rows), 'bytes':sum(row['bytes'] for row in rows), 'installer_started':False}
    except Exception as error:
        write_new_json(target/'backup-incomplete.json', {'complete':False,'plan_id':plan['plan_id'],
            'copied_files':len(rows),'skipped':skipped,'error':str(error),'uninstaller_started':False})
        raise


def _validate_backup(plan):
    manifest_file = Path(plan['backup_root'])/'backup-manifest.json'
    proof = read_json(manifest_file)
    if proof.get('plan_id') != plan['plan_id'] or proof.get('complete') is not True:
        raise ValueError('The selected reinstall has no completed backup')
    root = canonical(proof['backup_root'], must_exist=True)
    for row in proof['files']:
        file = (root/row['file']).resolve(strict=True)
        if not file.is_relative_to(root) or file.stat().st_size != row['bytes'] or digest_file(file) != row['sha256']:
            raise ValueError('Backup manifest content differs: ' + row['file'])
    return proof


def _state_file(plan_file, phase):
    return Path(plan_file).resolve().parent/('operation-'+phase+'.json')


def launch_phase(plan_file, phase, *, elevate=False, process_rows=None):
    """Spawn one monitor, which launches one vendor process in a retained JobObject."""
    plan = _plan(plan_file)
    if phase not in ('uninstall','install'):
        raise ValueError('Use uninstall or install')
    state_file = _state_file(plan_file, phase)
    previous_file=None
    if state_file.exists():
        previous=read_status(state_file)
        if elevate and previous.get('phase')=='elevation_required' and previous.get('vendor_started') is False:
            # Explicit elevation after CreateProcess reported 740 is a new,
            # recorded attempt. The old attempt and its claim are preserved.
            previous_file=Path(previous.get('resolved_state_file',state_file))
            state_file=state_file.with_name('operation-'+phase+'.elevated-'+uuid.uuid4().hex+'.json')
        else:
            return {'ok':False,'phase':'existing_operation','state':previous,
                    'automatic_retry':False,'meaning':'Read the actual existing result; do not launch again.'}
    if plan['choice'] == 'reinstall':
        _validate_backup(plan)
    elif phase == 'uninstall':
        raise ValueError('Fresh installation cannot invoke an uninstaller')
    running = selected_processes(plan['original_install_root'], process_rows)
    if running:
        return {'ok':False,'phase':'awaiting_normal_editor_close','running':running,'force_terminate':False}
    if phase == 'install' and plan['choice'] == 'reinstall':
        previous = read_status(_state_file(plan_file, 'uninstall'))
        if previous.get('phase') != 'completed' or previous.get('exit_code') != 0:
            raise ValueError('Original uninstall is not confirmed complete')
    task = plan[phase]
    file = canonical(task['executable'], must_exist=True)
    if digest_file(file) != task['executable_sha256']:
        raise ValueError('Selected vendor program changed after plan preparation')
    if phase == 'uninstall' and task.get('log_sha256') and digest_file(task['arguments'][0]) != task['log_sha256']:
        raise ValueError('Registered uninstall log changed after plan preparation')
    initial = {'schema':'mcgs-installer-operation/v1','plan_id':plan['plan_id'], 'plan_file':str(Path(plan_file).resolve()),
               'plan_sha256':digest_file(plan_file),'operation':phase,'phase':'monitor_requested','created_utc':utc(),
               'vendor_started':False,'automatic_retry':False,'timeout_is_cancellation':False,
               'job_name':'Local\\McgsTurnkeyInstall_'+uuid.uuid4().hex,'elevated_requested':bool(elevate)}
    write_new_json(state_file, initial)
    if previous_file:
        previous=read_json(previous_file);previous.update(replacement_state_file=str(state_file),
                     replacement_reason='explicit_elevation_after_confirmed_not_started_740')
        replace_json(previous_file,previous)
    command = [str(Path(__file__).resolve()), '_monitor', '--state', str(state_file)]
    if elevate:
        if os.name != 'nt':
            raise OSError('Elevation requires Windows')
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        shell.ShellExecuteW.argtypes=[wintypes.HWND,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.LPCWSTR,ctypes.c_int]
        shell.ShellExecuteW.restype=ctypes.c_void_p
        code = int(shell.ShellExecuteW(None,'runas',sys.executable,subprocess.list2cmdline(command),str(Path(__file__).parent),0) or 0)
        if code <= 32:
            initial.update(phase='elevation_cancelled_or_denied', vendor_started=False, shell_result=code)
            replace_json(state_file, initial)
            return {'ok':False,**initial,'state_file':str(state_file)}
    else:
        creationflags = getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name == 'nt' else 0
        output = state_file.with_suffix('.monitor.log').open('ab')
        try:
            monitor = subprocess.Popen([sys.executable,*command],stdin=subprocess.DEVNULL,stdout=output,stderr=output,
                                       creationflags=creationflags,close_fds=True)
        finally:
            output.close()
        initial['monitor_launcher_pid'] = monitor.pid
    return {'ok':True,'phase':'monitor_requested','state_file':str(state_file),'automatic_retry':False,
            'handoff':'Poll status. The original wizard is interactive; inspect it and set the recorded original directory.'}


def _winapi():
    if os.name != 'nt':
        raise OSError('Vendor execution requires Windows')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    class STARTUPINFO(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('lpReserved',wintypes.LPWSTR),('lpDesktop',wintypes.LPWSTR),('lpTitle',wintypes.LPWSTR),
                  ('dwX',wintypes.DWORD),('dwY',wintypes.DWORD),('dwXSize',wintypes.DWORD),('dwYSize',wintypes.DWORD),
                  ('dwXCountChars',wintypes.DWORD),('dwYCountChars',wintypes.DWORD),('dwFillAttribute',wintypes.DWORD),
                  ('dwFlags',wintypes.DWORD),('wShowWindow',wintypes.WORD),('cbReserved2',wintypes.WORD),
                  ('lpReserved2',ctypes.c_void_p),('hStdInput',wintypes.HANDLE),('hStdOutput',wintypes.HANDLE),('hStdError',wintypes.HANDLE)]
    class PROCESSINFO(ctypes.Structure):
        _fields_=[('hProcess',wintypes.HANDLE),('hThread',wintypes.HANDLE),('dwProcessId',wintypes.DWORD),('dwThreadId',wintypes.DWORD)]
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.CreateProcessW.argtypes=[wintypes.LPCWSTR,wintypes.LPWSTR,ctypes.c_void_p,ctypes.c_void_p,wintypes.BOOL,wintypes.DWORD,ctypes.c_void_p,wintypes.LPCWSTR,ctypes.POINTER(STARTUPINFO),ctypes.POINTER(PROCESSINFO)];kernel.CreateProcessW.restype=wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];kernel.AssignProcessToJobObject.restype=wintypes.BOOL
    kernel.ResumeThread.argtypes=[wintypes.HANDLE];kernel.ResumeThread.restype=wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];kernel.GetExitCodeProcess.restype=wintypes.BOOL
    kernel.QueryInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)];kernel.QueryInformationJobObject.restype=wintypes.BOOL
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT];kernel.TerminateProcess.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.FILETIME),ctypes.POINTER(wintypes.FILETIME),ctypes.POINTER(wintypes.FILETIME),ctypes.POINTER(wintypes.FILETIME)];kernel.GetProcessTimes.restype=wintypes.BOOL
    return kernel,STARTUPINFO,PROCESSINFO


def _job_pids(kernel, handle):
    count=8
    while True:
        data=ctypes.create_string_buffer(8+count*ctypes.sizeof(ctypes.c_size_t))
        needed=wintypes.DWORD()
        if kernel.QueryInformationJobObject(handle,3,data,len(data),ctypes.byref(needed)):
            actual=ctypes.cast(data,ctypes.POINTER(wintypes.DWORD))[1]
            array=(ctypes.c_size_t*actual).from_address(ctypes.addressof(data)+8)
            return list(array)
        if ctypes.get_last_error()!=234:
            raise ctypes.WinError(ctypes.get_last_error())
        count=max(count*2,ctypes.cast(data,ctypes.POINTER(wintypes.DWORD))[0])


def _monitor(state_file):
    state=read_json(state_file)
    plan_file=Path(state['plan_file'])
    if state.get('phase')!='monitor_requested' or digest_file(plan_file)!=state['plan_sha256']:
        raise ValueError('Monitor state or explicit plan changed before starting')
    # Never erase this record, including after a monitor crash or UAC denial.
    write_new_json(str(state_file)+'.monitor.claim', {'created_utc':utc(),'monitor_pid':os.getpid(),
                   'state_file':str(Path(state_file).resolve())})
    plan=_plan(plan_file);task=plan[state['operation']]
    kernel,STARTUPINFO,PROCESSINFO=_winapi()
    job=kernel.CreateJobObjectW(None,state['job_name'])
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    process=PROCESSINFO();startup=STARTUPINFO();startup.cb=ctypes.sizeof(startup)
    started=False
    try:
        if digest_file(task['executable'])!=task['executable_sha256']:
            raise ValueError('Vendor program changed immediately before launch')
        command=ctypes.create_unicode_buffer(subprocess.list2cmdline([task['executable'],*task['arguments']]))
        if not kernel.CreateProcessW(task['executable'],command,None,None,False,4,None,task['working_directory'],ctypes.byref(startup),ctypes.byref(process)):
            error=ctypes.get_last_error()
            state.update(phase='elevation_required' if error==740 else 'launch_failed',win32_error=error,vendor_started=False)
            replace_json(state_file,state);return
        # No vendor thread runs before the new process is attached to its own job.
        if not kernel.AssignProcessToJobObject(job,process.hProcess):
            error=ctypes.get_last_error();kernel.TerminateProcess(process.hProcess,1)
            state.update(phase='launch_tracking_failed',win32_error=error,vendor_started=False)
            replace_json(state_file,state);return
        times=[wintypes.FILETIME() for unused in range(4)]
        if not kernel.GetProcessTimes(process.hProcess,*(ctypes.byref(value) for value in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        creation=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
        state.update(phase='running',vendor_pid=process.dwProcessId,vendor_creation_filetime=str(creation),
                     monitor_pid=os.getpid(),vendor_started=True,started_utc=utc(),target_directory=plan['original_install_root'])
        replace_json(state_file,state)
        if kernel.ResumeThread(process.hThread)==0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        started=True
        deadline=time.monotonic()+1800
        while True:
            ids=_job_pids(kernel,job)
            exit_code=wintypes.DWORD()
            if not kernel.GetExitCodeProcess(process.hProcess,ctypes.byref(exit_code)):
                raise ctypes.WinError(ctypes.get_last_error())
            state.update(active_job_pids=ids,root_exit_code=None if exit_code.value==259 else exit_code.value,
                         observed_utc=utc())
            if not ids:
                state.update(phase='completed',exit_code=exit_code.value,completed_utc=utc(),
                             success_requires_post_verification=True,
                             restart_required=bool(task['kind']=='registered-msi' and exit_code.value in (1641,3010)))
                replace_json(state_file,state);return
            if time.monotonic()>deadline:
                state.update(phase='timeout_pending',outcome_unknown=True,
                             automatic_retry=False,processes_terminated=False)
            replace_json(state_file,state)
            time.sleep(0.5)
    except Exception as error:
        state.update(phase='outcome_unknown' if started else 'launch_failed',error=type(error).__name__+': '+str(error),
                     vendor_started=started,outcome_unknown=started,automatic_retry=False)
        replace_json(state_file,state)
    finally:
        if process.hProcess and not started:
            # This is only our still-suspended new process; no vendor code ran.
            kernel.TerminateProcess(process.hProcess,1)
        if process.hThread:kernel.CloseHandle(process.hThread)
        if process.hProcess:kernel.CloseHandle(process.hProcess)
        kernel.CloseHandle(job)


def read_status(state_file):
    current=canonical(state_file,must_exist=True);visited=set()
    while True:
        if current in visited:raise ValueError('Installer operation references form a cycle')
        visited.add(current);state=read_json(current)
        if not state.get('replacement_state_file'):break
        replacement=canonical(state['replacement_state_file'],must_exist=True)
        if replacement.parent!=current.parent:raise ValueError('Replacement installer operation escaped its plan directory')
        current=replacement
    if state.get('schema')!='mcgs-installer-operation/v1':
        raise ValueError('Installer operation schema differs')
    return {**state,'resolved_state_file':str(current),'read_only_status':True,'automatic_retry':False,
            'instruction':'Inspect the existing installer operation; timeout does not mean it did not run.'}


def verify_installation(plan_file, *, registry_rows=None, associations=None, version_reader=None):
    plan=_plan(plan_file)
    family=plan['version_comparison']['family'];root=canonical(plan['original_install_root'])
    image=canonical(plan.get('expected_editor_executable') or plan['installation']['editor_executable'])
    if not image.is_relative_to(root):
        raise ValueError('Expected editor must remain at the recorded installation root')
    if not image.is_file():
        return {'ok':False,'phase':'verification_pending','reason':'Editor is not at the original path',
                'expected_editor':str(image),'reinstall_retried':False}
    info=(version_reader or executable_version)(image)
    if info.get('file_version')!=plan['expected_installed_version']:
        return {'ok':False,'phase':'verification_failed','reason':'Actual installed editor version differs',
                'actual_version':info.get('file_version'),'expected_version':plan['expected_installed_version'],
                'install_root':str(root),'reinstall_retried':False}
    found=discover_installations([{'family':family,'editor_executable':str(image),'install_root':str(root)}],
        registry_rows=registry_rows,associations=associations,version_reader=version_reader)
    matches=[row for row in found['installations'] if canonical(row['editor_executable'])==image.resolve()]
    if len(matches)!=1:
        raise ValueError('Post-install discovery is ambiguous')
    return {'ok':True,'phase':'installed_at_original_root_verified','installation':matches[0],
            'original_root_preserved':True,'actual_version':info['file_version'],
            'user_data_restoration_pending':plan['choice']=='reinstall','native_business_ready':False,
            'next_step':'Merge user data without vendor binary overwrite, then initialize the selected offline/online mode.'}


def restore_user_data(plan_file):
    plan=_plan(plan_file)
    verification=verify_installation(plan_file)
    if not verification.get('ok'):
        return verification
    if plan['choice'] != 'reinstall':
        return {'ok':True,'phase':'fresh_install_has_no_old_user_data','vendor_binaries_overwritten':False}
    proof=_validate_backup(plan)
    source=canonical(proof['backup_root'],must_exist=True);target=canonical(plan['original_install_root'],must_exist=True)
    manifest_by_path={row['file']:row for row in proof['files']}
    copied,conflicts=[],[]
    for prefix in LOCAL_USER_DIRS:
        folder=source/prefix
        if not folder.is_dir():continue
        for path in folder.rglob('*'):
            if not path.is_file() or path.is_symlink():continue
            relative=path.relative_to(source);destination=(target/relative).resolve()
            if not destination.is_relative_to(target):raise ValueError('Restore target escapes original root')
            if path.suffix.casefold() in {'.dll','.exe','.ocx','.sys','.drv'}:continue
            expected=manifest_by_path.get(relative.as_posix())
            if not expected or digest_file(path)!=expected['sha256']:raise ValueError('Backup source differs during restore')
            destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists() and digest_file(destination)!=expected['sha256']:
                conflicts.append({'relative_file':relative.as_posix(),'backup_file':str(path),
                                  'installed_file':str(destination),'action':'preserved_both_for_AI_review'})
                continue
            if not destination.exists():
                shutil.copy2(path,destination);copied.append(relative.as_posix())
    return {'ok':True,'phase':'nonconflicting_user_data_merged','restored_files':copied,'conflicts':conflicts,
            'driver_library_config_review_required':True,'vendor_binaries_overwritten':False,
            'backup_preserved':True}


def run_ui_helper(helper, command, request, *, output=None, elevate=False):
    """The compiled own helper handles only selected editor roots or installer jobs."""
    file=canonical(helper,must_exist=True)
    if command not in {'choose','select-installation','inspect','click','set-directory','close-editor'}:
        raise ValueError('Unknown installation helper operation')
    args=[str(file),command,'--input',str(canonical(request,must_exist=True))]
    if output:args+=['--out',str(canonical(output))]
    if elevate:
        if os.name!='nt' or output is None:raise ValueError('An elevated helper needs Windows and a persistent receipt path')
        output=canonical(output);queue=Path(str(output)+'.elevation-request.json')
        identity={'command':command,'input_sha256':digest_file(request),'helper_sha256':digest_file(file)}
        if queue.exists():
            prior=read_json(queue)
            if any(prior.get(key)!=value for key,value in identity.items()):raise ValueError('Elevated helper request belongs to another action')
            if output.exists():return read_json(output)
            return {'ok':False,'phase':'elevated_helper_receipt_pending','receipt_file':str(output),
                    'automatic_retry':False,'next_step':'Inspect the existing UAC/helper operation; do not launch the action again.'}
        write_new_json(queue,{**identity,'created_utc':utc(),'phase':'elevation_requested'})
        shell=ctypes.WinDLL('shell32',use_last_error=True)
        shell.ShellExecuteW.argtypes=[wintypes.HWND,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.LPCWSTR,ctypes.c_int]
        shell.ShellExecuteW.restype=ctypes.c_void_p
        code=int(shell.ShellExecuteW(None,'runas',str(file),subprocess.list2cmdline(args[1:]),str(file.parent),0) or 0)
        return {'ok':code>32,'phase':'elevated_helper_receipt_pending' if code>32 else 'helper_elevation_cancelled_or_denied',
                'shell_result':code,'receipt_file':str(output),'automatic_retry':False,
                'next_step':'Read the receipt when available. UAC cancellation is not authorization to retry.'}
    completed=subprocess.run(args,capture_output=True,encoding='utf-8',errors='strict',
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
    if completed.returncode:
        raise RuntimeError(completed.stdout.strip() or completed.stderr.strip())
    return json.loads(completed.stdout)


def setup_bundle(bundle_root, family, explicit_editor=None, interactive=False):
    """Common-environment choice only; never starts a vendor installer implicitly."""
    root=canonical(bundle_root,must_exist=True);family=family_name(family)
    manifest=read_json(root/'bundle.json');products=manifest['products']
    if isinstance(products,dict):
        products=[dict(value,family=value.get('family',key)) for key,value in products.items()]
    matches=[item for item in products if family_name(item['family'])==family]
    if len(matches)!=1:raise ValueError('Bundle must identify one product for the selected family')
    product=matches[0]
    explicit=[]
    if explicit_editor:
        explicit=[dict(explicit_editor,family=family)] if isinstance(explicit_editor,dict) else [{'family':family,'editor_executable':str(explicit_editor)}]
    found=discover_installations(explicit)
    candidates=[item for item in found['installations'] if item['family']==family]
    if explicit:
        requested=canonical(explicit[0]['editor_executable'],must_exist=True)
        candidates=[item for item in candidates if canonical(item['editor_executable'])==requested]
        if not candidates:raise ValueError('Explicit editor could not be identified as the requested product')
    helper=root/'tools'/'InstallerChoice.exe'
    work=canonical(Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'mcgs-engineering'/'setup'/uuid.uuid4().hex)
    work.mkdir(parents=True,exist_ok=False)
    common={'family':family,'environment_ready':False,'business_adaptation_verified':False,
            'receiver_compilation_required':False,'automatic_reinstall':False,'work_directory':str(work)}
    if len(candidates)>1:
        if not interactive:
            return {**common,'ok':True,'status':'installation_selection_required','installations':candidates}
        request=work/'select-installation.json';write_new_json(request,{'installations':candidates})
        selected=run_ui_helper(helper,'select-installation',request,output=work/'selection.json')
        if selected.get('choice')=='cancel':return {**common,'ok':True,'status':'cancelled','software_changed':False}
        if selected.get('choice')!='selected':raise ValueError('Installation selector returned an unknown choice')
        candidates=[row for row in candidates if row['installation_id']==selected.get('installation_id')]
        if len(candidates)!=1:raise ValueError('Installation selector returned an unknown installation')
    installation=candidates[0] if candidates else None
    evaluation=evaluate_installation(installation,product)
    if evaluation['comparison']=='same':choice='current'
    elif not interactive:
        return {**common,'ok':True,'status':'choice_required','installation':installation,
                'version_comparison':evaluation,'choices':evaluation['choices'],'default_choice':'current' if installation else 'cancel'}
    else:
        request=work/'version-choice.json';write_new_json(request,{**evaluation,'not_installed':installation is None})
        response=run_ui_helper(helper,'choose',request,output=work/'choice.json');choice=response.get('choice')
        if choice not in evaluation['choices']:raise ValueError('Version selector returned an unknown or unavailable choice')
    plan=make_plan(installation,product,choice,backup_root=work/'backup',bundle_root=root)
    plan.update(ui_helper=str(helper),bundle_root=str(root),choice_source='interactive_user' if interactive else 'same_full_editor_version')
    plan_file=work/'plan.json';write_new_json(plan_file,plan)
    if choice=='cancel':return {**common,'ok':True,'status':'cancelled','plan_file':str(plan_file),'software_changed':False}
    if choice=='current':
        return {**common,'ok':True,'status':'current_installation_selected','environment_ready':True,
                'installation':installation,'selected_installation':installation,'analysis':plan['analysis'],
                'local_adaptation_required':True,'plan_file':str(plan_file),'software_changed':False}
    command=[sys.executable,str(Path(__file__).resolve()),'execute','--plan',str(plan_file)]
    return {**common,'ok':True,'status':'installation_plan_ready','choice':choice,'plan_file':str(plan_file),
            'installation':installation,'summary':plan['summary'],'target_directory':plan['original_install_root'],
            'backup_directory':plan.get('backup_root'),'execute_argv':command,'execute_command':subprocess.list2cmdline(command),
            'choice_authorizes_this_plan':True,'repeat_permission_prompt_required':False,
            'next_step':'AI executes this plan and drives the original wizard, then verifies the exact directory and full version.'}


def _creation_filetime(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    try:
        times=[wintypes.FILETIME() for unused in range(4)]
        if not kernel.GetProcessTimes(handle,*[ctypes.byref(t) for t in times]):raise ctypes.WinError(ctypes.get_last_error())
        return str((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)
    finally:kernel.CloseHandle(handle)


def request_editor_close(plan_file, *, process_rows=None):
    plan=_plan(plan_file);running=selected_processes(plan['original_install_root'],process_rows)
    editor=canonical(plan['installation']['editor_executable']);receipts=[]
    for row in running:
        if canonical(row['executable'])!=editor:continue
        creation=_creation_filetime(row['pid']);stem=Path(plan_file).parent/('close-editor-'+str(row['pid'])+'-'+creation)
        request=stem.with_suffix('.request.json');output=stem.with_suffix('.receipt.json')
        if not request.exists():write_new_json(request,{'plan_file':str(canonical(plan_file)),'pid':row['pid'],'creation_filetime':creation})
        receipts.append(run_ui_helper(plan['ui_helper'],'close-editor',request,output=output))
    return {'ok':False,'phase':'awaiting_normal_editor_close','running':running,'normal_close_receipts':receipts,
            'force_terminate':False,'environment_ready':False,'automatic_retry':False,
            'handoff':'AI resolves any unsaved-work prompt normally; other running tools under this root must also exit before backup.'}


def execute_plan(plan_file, *, elevate=False, process_rows=None):
    """Advance one selected plan. Existing vendor operations are observed, never rerun."""
    plan=_plan(plan_file);folder=Path(plan_file).resolve().parent
    if plan['choice']=='reinstall':
        unstate=_state_file(plan_file,'uninstall')
        if not unstate.exists():
            if selected_processes(plan['original_install_root'],process_rows):
                return request_editor_close(plan_file,process_rows=process_rows)
            backup=Path(plan['backup_root'])
            if not backup.exists():backup_plan(plan_file,process_rows=process_rows)
            _validate_backup(plan)
            return launch_phase(plan_file,'uninstall',elevate=elevate,process_rows=process_rows)
        old=read_status(unstate)
        if elevate and old.get('phase')=='elevation_required' and old.get('vendor_started') is False:
            return launch_phase(plan_file,'uninstall',elevate=True,process_rows=process_rows)
        if old.get('restart_required'):
            return {'ok':False,'phase':'restart_required','state':old,'environment_ready':False,'automatic_restart':False,
                    'next_step':'AI records the pending reboot and resumes this existing plan after Windows restarts; do not uninstall again.'}
        if old.get('phase')!='completed' or old.get('exit_code')!=0:
            return _wizard_handoff(plan,unstate,old)
        if not _state_file(plan_file,'install').exists() and Path(plan['installation']['editor_executable']).exists():
            return {'ok':False,'phase':'uninstall_postcondition_pending','environment_ready':False,'state':old,
                    'reason':'Old editor still exists; exit code alone does not establish successful uninstall.',
                    'automatic_retry':False,'next_step':'AI inspects the existing result and any retained/shared files. Do not relaunch or delete the installation root.'}
    state_file=_state_file(plan_file,'install')
    if not state_file.exists():return launch_phase(plan_file,'install',elevate=elevate,process_rows=process_rows)
    state=read_status(state_file)
    if elevate and state.get('phase')=='elevation_required' and state.get('vendor_started') is False:
        return launch_phase(plan_file,'install',elevate=True,process_rows=process_rows)
    if state.get('restart_required'):
        return {'ok':False,'phase':'restart_required','state':state,'environment_ready':False,'automatic_restart':False}
    if state.get('phase')!='completed' or state.get('exit_code')!=0:return _wizard_handoff(plan,state_file,state)
    result=verify_installation(plan_file)
    if not result.get('ok'):return {**result,'environment_ready':False}
    restoration=restore_user_data(plan_file)
    receipt=folder/'installation-verified.json'
    answer={**result,'environment_ready':True,'business_adaptation_verified':False,'user_data_restore':restoration,
            'mode_selection_required':True,'next_step':'Offer offline or online editing, and initialize only the selected mode against this installation.'}
    if not receipt.exists():write_new_json(receipt,answer)
    return answer


def _wizard_handoff(plan,state_file,state):
    active=state.get('resolved_state_file',str(state_file))
    return {'ok':False,'phase':'installer_handoff','environment_ready':False,'state_file':active,'state':state,
            'helper_executable':plan.get('ui_helper'),'target_directory':plan['original_install_root'],
            'inspect_request':{'state_file':active},'automatic_retry':False,
            'helper_requires_same_elevation':bool(state.get('elevated_requested')),
            'next_step':'AI uses helper inspect/click/set-directory for this installer job. Read and retain the vendor license; handle UAC or reboot explicitly. Preserve uncertain shared files. Unknown outcome or timeout means inspect status, never relaunch.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    discover=sub.add_parser('discover');discover.add_argument('--explicit-json',type=Path);discover.add_argument('--out',type=Path)
    make=sub.add_parser('plan');make.add_argument('--installation',type=Path);make.add_argument('--product',type=Path,required=True)
    make.add_argument('--choice',choices=['current','reinstall','install','cancel'],required=True);make.add_argument('--backup-root',type=Path)
    make.add_argument('--bundle-root',type=Path);make.add_argument('--out',type=Path,required=True)
    backup=sub.add_parser('backup');backup.add_argument('--plan',type=Path,required=True)
    for phase in ('uninstall','install'):
        run=sub.add_parser(phase);run.add_argument('--plan',type=Path,required=True);run.add_argument('--elevate',action='store_true')
    status=sub.add_parser('status');status.add_argument('--state',type=Path,required=True)
    verify=sub.add_parser('verify');verify.add_argument('--plan',type=Path,required=True)
    restore=sub.add_parser('restore-user-data');restore.add_argument('--plan',type=Path,required=True)
    monitor=sub.add_parser('_monitor');monitor.add_argument('--state',type=Path,required=True)
    execute=sub.add_parser('execute');execute.add_argument('--plan',type=Path,required=True);execute.add_argument('--elevate',action='store_true')
    ui=sub.add_parser('ui');ui.add_argument('--helper',type=Path,required=True);ui.add_argument('--action',choices=['inspect','click','set-directory','close-editor','choose','select-installation'],required=True)
    ui.add_argument('--request',type=Path,required=True);ui.add_argument('--out',type=Path,required=True);ui.add_argument('--elevate',action='store_true')
    args=p.parse_args(argv)
    if args.command=='_monitor':_monitor(args.state);return 0
    if args.command=='discover':
        explicit=read_json(args.explicit_json) if args.explicit_json else []
        result=discover_installations(explicit)
    elif args.command=='plan':result=make_plan(read_json(args.installation) if args.installation else None,read_json(args.product),args.choice,backup_root=args.backup_root,bundle_root=args.bundle_root)
    elif args.command=='backup':result=backup_plan(args.plan)
    elif args.command in ('uninstall','install'):result=launch_phase(args.plan,args.command,elevate=args.elevate)
    elif args.command=='status':result=read_status(args.state)
    elif args.command=='verify':result=verify_installation(args.plan)
    elif args.command=='execute':result=execute_plan(args.plan,elevate=args.elevate)
    elif args.command=='ui':result=run_ui_helper(args.helper,args.action,args.request,output=args.out,elevate=args.elevate)
    else:result=restore_user_data(args.plan)
    if getattr(args,'out',None):write_new_json(args.out,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,RuntimeError) as error:
        print(json.dumps({'ok':False,'error':type(error).__name__+': '+str(error),
                          'automatic_retry':False,'software_reinstall_claimed_complete':False},ensure_ascii=False),file=sys.stderr)
        raise SystemExit(1)
