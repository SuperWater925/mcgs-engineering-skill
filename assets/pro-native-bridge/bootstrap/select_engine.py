"""Deploy/select an existing bridge's new own engine using files only.

Default execution is direct. --plan is read-only; --status reads the actual
selection. No bridge/native/project request, COM registration, process launch,
permit, approval file, claim cleanup or paused-project change is performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid
import sys

from managed_pe import verify_scope_binding
sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'portable-engine'))
from portable_support import PORTABLE_FIELDS, validate_portable_scope

NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.dll\Z')
SHA = re.compile(r'[a-f0-9]{64}\Z')


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')


def absolute(value):
    path = Path(value)
    need(path.is_absolute() and '\0' not in str(path), 'Use explicit absolute file/directory paths')
    return path.resolve()


def regular(path, maximum=None):
    path = absolute(path)
    before = path.stat()
    need(stat.S_ISREG(before.st_mode) and before.st_size > 0 and (maximum is None or before.st_size <= maximum), 'Expected regular file: '+str(path))
    raw = path.read_bytes()
    after = path.stat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    need(identity(before) == identity(after) and len(raw) == after.st_size, 'File changed while being read: '+str(path))
    return raw


def same(first, second):
    return os.path.normcase(str(absolute(first))) == os.path.normcase(str(absolute(second)))


def read_json(path, maximum=None):
    raw = regular(path, maximum)
    value = json.loads(raw.decode('utf-8-sig'))
    need(isinstance(value, dict), 'Expected JSON object: '+str(path))
    return value, raw


def write_new(path, raw):
    absolute(path)
    with Path(path).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def verify_bootstrap(boot):
    boot = absolute(boot)
    cfg, config_raw = read_json(boot/'McgsInternalBridge.bridge.json')
    config_sha = digest(config_raw)
    built, _ = read_json(boot/'build-manifest.json')
    need(cfg.get('schema') == 1 and built.get('bootstrap_scope_sha256') == config_sha,
         'Prepared bridge build/config binding differs')
    need(same(cfg['bootstrap_root'], boot), 'BootstrapRoot differs from the current bound configuration')
    task, runtime, install, editor = [absolute(cfg[key]) for key in ('task_root', 'runtime_root', 'install_root', 'editor_executable')]
    need(all(path.is_dir() for path in (boot, task, runtime, install)), 'Existing bridge directories must exist')
    need(runtime != task and runtime.is_relative_to(task) and boot != task and boot.is_relative_to(task)
         and not runtime.is_relative_to(boot) and not boot.is_relative_to(runtime), 'Current bridge task/runtime/bootstrap roots differ')
    need(editor.is_relative_to(install) and digest(regular(editor)) == cfg.get('editor_sha256'), 'Current bound editor executable identity changed')
    contract = absolute(cfg['loader_contract_file'])
    need(digest(regular(contract)) == cfg.get('loader_contract_sha256'), 'Current bridge loader capability changed')
    if cfg.get('entry_mode') == 'thread_specific_hot_attach':
        plan, plan_raw = read_json(boot/'hot-attach.json')
        need(built.get('config_sha256') == digest(plan_raw) and plan.get('bootstrap_scope_sha256') == config_sha,
             'Current hot-bridge plan/build identity changed')
        assembly = absolute(plan['bootstrap_dll'])
        need(assembly.parent == boot and digest(regular(assembly)) == plan.get('bootstrap_dll_sha256'), 'Current hot-bridge DLL changed')
        for field, pin in (('client', 'client_sha256'),):
            need(digest(regular(built[field])) == built.get(pin), 'Current bridge client changed')
        need(digest(regular(plan['hook_dll'])) == plan.get('hook_dll_sha256'), 'Current native hook changed')
    else:
        assembly = boot/'McgsInternalBridge.dll'
        for row in built.get('files', []):
            file = absolute(boot/row['relative_path'])
            need(file.is_relative_to(boot) and digest(regular(file)) == row['sha256'], 'Current built bridge file changed: '+str(file))
        need(any(row.get('relative_path') == 'McgsInternalBridge.dll' for row in built.get('files', [])), 'Current bridge build manifest omits its DLL')
    verify_scope_binding(regular(assembly), config_sha, bootstrap=True)
    return {'boot': boot, 'cfg': cfg, 'config_raw': config_raw, 'config_sha': config_sha,
            'runtime': runtime, 'manifest': runtime/'active-engine.json'}


def verify_selection(context):
    selected, raw = read_json(context['manifest'])
    need(selected.get('bootstrap_scope_sha256') == context['config_sha'], 'Active engine belongs to another bridge configuration')
    path = absolute(selected.get('assembly', ''))
    need(path.parent == context['boot']/'engines' and NAME.fullmatch(path.name), 'Active engine path escapes the current engine directory')
    expected = selected.get('sha256', '')
    need(isinstance(expected, str) and SHA.fullmatch(expected), 'Active engine SHA256 is missing or invalid')
    need(digest(regular(path)) == expected, 'Currently selected engine SHA differs from its manifest')
    if 'engine_scope_sha256' in selected:
        scope_raw = regular(path.with_suffix('.scope.json'))
        need(digest(scope_raw) == selected['engine_scope_sha256'], 'Currently selected engine scope differs from its manifest')
        verify_scope_binding(regular(path), selected['engine_scope_sha256'])
        verify_scope(scope_raw, context)
    return selected, raw


def verify_scope(raw, context):
    scope = json.loads(raw.decode('utf-8-sig'))
    keys = {'schema', 'task_root', 'engineering_root', 'runtime_root', 'install_root', 'transport_client_file', 'transport_client_sha256'}
    need(isinstance(scope, dict) and keys <= set(scope) <= keys|{'editor_executable'}|PORTABLE_FIELDS and scope['schema'] == 1,
         'Engine scope schema differs')
    for key in ('task_root', 'runtime_root', 'install_root'):
        need(same(scope[key], context['cfg'][key]), 'Engine and current bridge disagree on '+key)
    editor = scope.get('editor_executable', str(Path(scope['install_root'])/'Program'/'McgsSetPro.exe'))
    need(same(editor, context['cfg']['editor_executable']), 'Engine and current bridge disagree on the exact editor executable')
    engineering = absolute(scope['engineering_root'])
    need(engineering.is_dir() and not engineering.is_relative_to(context['runtime']) and not context['runtime'].is_relative_to(engineering),
         'Frozen engineering payload and current runtime must exist and be disjoint')
    transport = absolute(scope['transport_client_file'])
    need(transport.is_relative_to(absolute(scope['task_root'])) or transport.is_relative_to(engineering), 'Transport escapes the declared task/payload roots')
    need(SHA.fullmatch(scope['transport_client_sha256']) and digest(regular(transport)) == scope['transport_client_sha256'],
         'Selected scope transport identity differs')
    validate_portable_scope(scope)
    return scope


def select_engine(args):
    context = verify_bootstrap(args.bootstrap_root)
    selected, old_raw = verify_selection(context)
    status = {'schema': 1, 'status': 'actual_engine_selection_read', 'manifest': str(context['manifest']),
              'manifest_sha256': digest(old_raw), 'selection': selected,
              'bootstrap_scope_sha256': context['config_sha'], 'host_invoked': False, 'native_called': False}
    if args.status:
        return status
    for key in ('engine_file', 'engine_scope_file', 'engine_sha256', 'engine_scope_sha256', 'manifest_sha256'):
        need(getattr(args, key, None), 'Engine selection requires --'+key.replace('_', '-'))
    for key in ('engine_sha256', 'engine_scope_sha256', 'manifest_sha256'):
        need(SHA.fullmatch(getattr(args, key)), 'Expected a lowercase SHA256: '+key)
    engine, scope = absolute(args.engine_file), absolute(args.engine_scope_file)
    need(NAME.fullmatch(engine.name) and scope.name == engine.stem+'.scope.json', 'Use a fresh DLL basename with its exact sibling scope filename')
    engine_raw, scope_raw = regular(engine), regular(scope)
    need(digest(engine_raw) == args.engine_sha256 and digest(scope_raw) == args.engine_scope_sha256, 'Selected input DLL/scope SHA differs')
    verify_scope(scope_raw, context)
    pe = verify_scope_binding(engine_raw, args.engine_scope_sha256)
    target = context['boot']/'engines'/engine.name
    target_scope = target.with_suffix('.scope.json')
    value = {'assembly': str(target), 'sha256': args.engine_sha256,
             'bootstrap_scope_sha256': context['config_sha'], 'engine_scope_sha256': args.engine_scope_sha256}
    desired_raw = encoded(value)
    # Successful retry is recognized from actual files, without replaying any
    # native work or relying on a previous success receipt.
    already = same(selected['assembly'], target) and selected['sha256'] == args.engine_sha256
    if already:
        need(regular(target) == engine_raw and regular(target_scope) == scope_raw, 'Selected version has changed; never overwrite an engine filename')
        status.update(status='already_selected_verified', engine_scope_sha256=args.engine_scope_sha256, changed=False)
        return status
    need(digest(old_raw) == args.manifest_sha256, 'Active-engine preimage changed; read actual status before selecting again')
    need(not same(selected['assembly'], target), 'Use a fresh versioned DLL filename; loaded engine names cannot be reused')
    for file, raw in ((target, engine_raw), (target_scope, scope_raw)):
        if os.path.lexists(file):
            # A partial interrupted file-only copy may already exist. It is
            # reusable only if its complete immutable bytes are already exact.
            need(regular(file) == raw, 'Existing engine/scope version differs; choose a fresh filename: '+str(file))
    status.update(status='engine_selection_plan' if args.plan else 'engine_selected_file_only',
                  before_manifest_sha256=digest(old_raw), planned_selection=value, compiled_identity=pe, changed=not args.plan)
    if args.plan:
        return status
    lock = context['runtime']/'active-engine.selection.lock'
    lock_raw = encoded({'schema': 1, 'operation': 'file-only-engine-selection', 'nonce': uuid.uuid4().hex,
                        'before_sha256': digest(old_raw), 'after_sha256': digest(desired_raw)})
    write_new(lock, lock_raw)
    temp = context['runtime']/('active-engine.'+uuid.uuid4().hex+'.tmp')
    backup = context['runtime']/('active-engine.before-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex+'.json')
    try:
        # Recheck current bridge and manifest under the cooperating-writer lock.
        current = verify_bootstrap(context['boot'])
        _, current_raw = verify_selection(current)
        need(current['config_sha'] == context['config_sha'] and current_raw == old_raw, 'Current bridge/manifest changed before deployment')
        for file, raw in ((target, engine_raw), (target_scope, scope_raw)):
            if not os.path.lexists(file):
                write_new(file, raw)
            need(regular(file) == raw, 'Deployed engine/scope readback differs')
        write_new(backup, old_raw)
        write_new(temp, desired_raw)
        need(regular(context['manifest']) == old_raw, 'Active-engine preimage changed before atomic selection')
        os.replace(temp, context['manifest'])
        actual, actual_raw = verify_selection(context)
        need(actual_raw == desired_raw, 'Atomic engine selection readback differs; inspect actual status before any retry')
        status.update(selection=actual, manifest_sha256=digest(actual_raw), backup=str(backup), backup_sha256=digest(old_raw))
        return status
    finally:
        # Do not clean immutable outputs/backups or an unknown lock. Temporary
        # outputs remain evidence on failure; no automatic rollback is attempted.
        if os.path.lexists(lock) and regular(lock) == lock_raw:
            lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap-root', required=True)
    parser.add_argument('--status', action='store_true', help='Read and verify the actual current selection only')
    parser.add_argument('--plan', action='store_true', help='Validate and show the file-only selection without writing')
    for name in ('engine-file', 'engine-scope-file', 'engine-sha256', 'engine-scope-sha256', 'manifest-sha256'):
        parser.add_argument('--'+name)
    args = parser.parse_args(argv)
    need(not (args.status and args.plan), '--status and --plan are mutually exclusive')
    print(json.dumps(select_engine(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
