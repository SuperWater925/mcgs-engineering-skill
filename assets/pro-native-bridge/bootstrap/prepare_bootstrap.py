"""Prepare explicitly located OWN bridge sources and registration plans. Files only.

Does not register, deploy into Addins, load a vendor module, open a project or start Pro.
Run build_bootstrap.ps1 separately to compile the prepared own sources.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

HERE = Path(__file__).resolve().parent
ROOTS = [r'Software\Classes\CLSID\{52119C44-5875-4DA6-9F72-E97D2E2182B4}',
         r'Software\Classes\McgsInternalBridge.AddInObj',
         r'Software\Classes\TypeLib\{4D2519E0-CC21-4F82-A19C-1AF9801C64E1}']
MARKER = 'CodexBridgeTransactionId'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def absolute(value):
    if os.name != 'nt':
        raise ValueError('Prepare this Windows native bridge on Windows')
    drive, tail = os.path.splitdrive(value)
    if len(drive) != 2 or drive[1] != ':' or not tail.startswith(('\\', '/')):
        raise ValueError('An explicit local drive absolute path is required: ' + value)
    path = Path(os.path.abspath(value))
    if path == Path(path.anchor):
        raise ValueError('A volume root is not an owned workspace')
    for item in [path, *path.parents]:
        if item.exists() and (item.stat(follow_symlinks=False).st_file_attributes & 0x400):
            raise ValueError('Reparse point is outside this preparation contract: ' + str(item))
    return path


def inside(path, root):
    return path != root and str(path).casefold().startswith(str(root).rstrip('\\/').casefold() + '\\')


def regular(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError('Input is not a regular file: ' + str(path))
    return path


def write_new(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def json_new(path, value):
    write_new(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def registration(boot):
    cls, prog, lib = ROOTS
    dll = boot / 'McgsInternalBridge.dll'
    codebase = 'file:///' + str(dll).replace('\\', '/')
    common = {'Class': 'McgsInternalBridge.AddInObj',
              'Assembly': 'McgsInternalBridge, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null',
              'RuntimeVersion': 'v4.0.30319', 'CodeBase': codebase}
    return [
        {'key': cls, 'values': {'': 'McgsInternalBridge.AddInObj'}},
        {'key': prog, 'values': {'': 'McgsInternalBridge.AddInObj'}},
        {'key': lib, 'values': {}},
        {'key': prog + r'\CLSID', 'values': {'': '{52119C44-5875-4DA6-9F72-E97D2E2182B4}'}},
        {'key': cls + r'\InprocServer32', 'values': dict(common, **{
            '': str(Path(os.environ['WINDIR']) / 'SysWOW64/mscoree.dll'), 'ThreadingModel': 'Both'})},
        {'key': cls + r'\ProgId', 'values': {'': 'McgsInternalBridge.AddInObj'}},
        {'key': cls + r'\TypeLib', 'values': {'': '{4D2519E0-CC21-4F82-A19C-1AF9801C64E1}'}},
        {'key': lib + r'\1.0', 'values': {'': 'McgsInternalBridge'}},
        {'key': cls + r'\InprocServer32\1.0.0.0', 'values': common},
        {'key': lib + r'\1.0\0', 'values': {}},
        {'key': lib + r'\1.0\FLAGS', 'values': {'': '0'}},
        {'key': lib + r'\1.0\0\win32', 'values': {'': str(dll)}},
    ]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['task-root', 'runtime-root', 'bootstrap-root', 'install-root',
                 'editor-executable', 'addins-directory', 'addins-ini-file',
                 'startup-registry-path', 'loader-contract-file']:
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    paths = {key: absolute(getattr(a, key)) for key in [
        'task_root', 'runtime_root', 'bootstrap_root', 'install_root',
        'editor_executable', 'addins_directory', 'addins_ini_file', 'loader_contract_file']}
    task, runtime, boot, install = [paths[k] for k in ['task_root', 'runtime_root', 'bootstrap_root', 'install_root']]
    if not inside(runtime, task) or not inside(boot, task) or runtime == boot or inside(runtime, boot) or inside(boot, runtime):
        raise ValueError('Runtime and Bootstrap must be disjoint children of the explicit owned TaskRoot')
    if not task.is_dir() or not install.is_dir() or not inside(paths['editor_executable'], install) or not inside(paths['addins_directory'], install):
        raise ValueError('Explicit existing task/install/editor/Addins scope is inconsistent')
    if paths['addins_ini_file'].parent != paths['addins_directory']:
        raise ValueError('Addins.ini must be in the exact Addins directory')
    for key in ['editor_executable', 'loader_contract_file', 'addins_ini_file']:
        regular(paths[key])
    if boot.exists() or runtime.exists():
        raise ValueError('Fresh BootstrapRoot and RuntimeRoot are required; do not overwrite prior task state/claims')
    startup = a.startup_registry_path
    if not startup.casefold().startswith('software\\') or not startup.casefold().endswith('\\startup') or '\0' in startup:
        raise ValueError('Supply the exact original existing per-user Startup key from loader evidence')
    capability = json.loads(paths['loader_contract_file'].read_text(encoding='utf-8-sig'))
    editor_sha = sha(paths['editor_executable'])
    if capability.get('schema') != 1 or capability.get('static_loader_contract_supported') is not True or capability.get('binary_sha256') != editor_sha:
        raise ValueError('Actual executable has no matching derived native loader capability contract')
    boot.mkdir(parents=True, exist_ok=False)
    (boot / 'engines').mkdir()
    (boot / 'bound-source').mkdir()
    contract_copy = boot / 'loader-capability.json'
    write_new(contract_copy, paths['loader_contract_file'].read_bytes())
    config = {'schema': 1, **{k: str(v) for k, v in paths.items() if k != 'loader_contract_file'},
              'loader_contract_file': str(contract_copy), 'loader_contract_sha256': sha(contract_copy),
              'editor_sha256': editor_sha, 'startup_registry_path': startup,
              'addins_ini_sha256': sha(paths['addins_ini_file'])}
    config_file = boot / 'McgsInternalBridge.bridge.json'
    json_new(config_file, config)
    config_sha = sha(config_file)
    sources = []
    for source in sorted((HERE / 'source').glob('*.cs')):
        content = source.read_text(encoding='utf-8-sig')
        if source.name == 'BootstrapLayout.cs':
            token = '__BOUND_CONFIGURATION_SHA256__'
            if content.count(token) != 1:
                raise ValueError('Configuration SHA binding token is not unique')
            content = content.replace(token, config_sha)
        target = boot / 'bound-source' / source.name
        write_new(target, content.encode('utf-8'))
        sources.append({'source_name': source.name, 'template_sha256': sha(source), 'bound_sha256': sha(target)})
    token = uuid.uuid4().hex
    entries = registration(boot)
    json_new(boot / 'hklm-registration-plan.json', {
        'schema': 1, 'hive': 'HKLM', 'view': 'Registry32', 'requires_absent_roots': ROOTS,
        'registration': entries, 'bootstrap_scope_sha256': config_sha,
        'unknown_existing_registration_policy': 'reject; uninstall old owned task explicitly first'})
    owned_entries = json.loads(json.dumps(entries))
    for root in ROOTS:
        next(x for x in owned_entries if x['key'] == root)['values'][MARKER] = token
    json_new(boot / 'prepared-registration-contract.json', {
        'schema': 1, 'state': 'prepared_not_registered', 'hive': 'HKLM', 'view': 'Registry32',
        'roots': ROOTS, 'transaction_id': token, 'expected_entries': owned_entries,
        'bootstrap_scope_sha256': config_sha, 'registry_written': False})
    for name in ['build_bootstrap.ps1', 'install_bootstrap.ps1', 'remove_bootstrap.ps1', 'stage_engine.py', 'build_native_wrapper.py']:
        shutil.copyfile(HERE / name, boot / name)
    report = {'schema': 1, 'status': 'prepared_source_and_plans_only', 'config_file': str(config_file),
              'config_sha256': config_sha, 'bootstrap_root': str(boot), 'sources': sources,
              'runtime_root_not_created_by_prepare': True, 'editor_sha256': editor_sha,
              'vendor_modules_loaded': False, 'registry_written': False, 'deployed': False,
              'host_started': False, 'native_project_opened': False,
              'next': 'Run build_bootstrap.ps1 -PreparedRoot <bootstrap_root>; inspect its build manifest. Installation and launch are separate explicit commands.'}
    json_new(boot / 'preparation-record.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
