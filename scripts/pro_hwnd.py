"""Native Windows-message backend: inventory, one-plan run, or persistent JSONL.

Example: run.ps1 native-hwnd run --pid 1234 --plan plan.json --receipt receipt.json
No Pro process is started. Keep one serve process for repeated work and submit
the desired save menu once in plan.save_command. A sent message is not a
vendor project check. Existing receipts prevent accidental plan replay.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'assets/pro-native-bridge/client'


@lru_cache(maxsize=1)
def project_client(scope_config, scope_sha256):
    # Configure only for mutation. Inventory and exact dialog responses do not
    # require an active bridge connection.
    if not scope_config:
        raise ValueError('Choose the current bridge with --scope-config or MCGS_NATIVE_SCOPE_CONFIG')
    if str(CLIENT) not in sys.path:
        sys.path.insert(0, str(CLIENT))
    from native_delivery_config import configure
    pinned_sha = scope_sha256 or hashlib.sha256(Path(scope_config).read_bytes()).hexdigest()
    configure(scope_config, pinned_sha)
    import edit_batch_client
    return edit_batch_client


def project_probe(project, timeout, scope_config, scope_sha256):
    bridge = project_client(scope_config, scope_sha256)
    client = bridge.load_client()
    try:
        return bridge.submit({'op': 'engineering-edit-inspect', 'expected_project': project},
                             'hwnd_identity_' + uuid.uuid4().hex, timeout)
    except (client.SubmissionError, client.QueueTimeout) as error:
        raise RuntimeError('Live bridge project identity could not be confirmed') from error


def backend_module():
    spec = importlib.util.spec_from_file_location('mcgs_hwnd_backend', ROOT / 'assets/pro-native-bridge/client/hwnd_backend.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def run_plan(backend, plan, receipt):
    path = Path(receipt).resolve()
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    if path.exists():
        previous = read(path)
        if previous.get('plan_sha256') != digest:
            raise ValueError('Receipt belongs to a different plan; choose a new receipt path')
        return {**previous, 'reused_receipt': True, 'automatic_retry': False,
                'meaning': 'Recorded outcome returned without replay; inspect unfinished/unknown steps before preparing new work'}
    path.parent.mkdir(parents=True, exist_ok=True)
    # An execution record is created before dispatch. It is not a permission
    # file and never authorizes work; it preserves partial/unknown outcomes.
    initial = {'schema': 'mcgs-hwnd-receipt/v1', 'status': 'prepared', 'plan_sha256': digest,
               'process': backend.api.identity, 'automatic_retry': False}
    with path.open('x', encoding='utf-8') as output:
        json.dump(initial, output, ensure_ascii=False)
    def checkpoint(result):
        save(path, {**result, 'plan_sha256': digest})
    result = backend.run(plan, checkpoint=checkpoint)
    return {**result, 'plan_sha256': digest, 'receipt': str(path)}


def serve(backend, log=None):
    answers = {}
    for line in sys.stdin:
        if not line.strip():
            continue
        request = None
        try:
            request = json.loads(line)
            identity = request.get('id')
            if not isinstance(identity, str) or not identity:
                raise ValueError('JSONL requests require a nonempty id')
            fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
            if identity in answers:
                previous_fingerprint, previous = answers[identity]
                if previous_fingerprint != fingerprint:
                    raise ValueError('Request id was already used for different work')
                result = {**previous, 'reused_receipt': True, 'automatic_retry': False}
            elif request.get('op') == 'inventory':
                result = {'id': identity, **backend.inventory()}
                answers[identity] = fingerprint, result
            elif request.get('op') == 'toolbar-inventory':
                result = {'id': identity, 'status': 'inventory_read',
                          'items': backend.discover_toolbar(request['toolbar'])}
                answers[identity] = fingerprint, result
            elif request.get('op') == 'run':
                plan = read(request['plan_file']) if 'plan_file' in request else request['plan']
                result = {'id': identity, **run_plan(backend, plan, request['receipt'])}
                answers[identity] = fingerprint, result
            else:
                raise ValueError('JSONL op must be inventory, toolbar-inventory or run')
        except Exception as error:
            result = {'id': request.get('id') if isinstance(request, dict) else None,
                      'status': getattr(error, 'status', 'request_failed'), 'error': str(error),
                      'details': getattr(error, 'details', {}), 'automatic_retry': False}
        encoded = json.dumps(result, ensure_ascii=False)
        if log:
            path = Path(log).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as output:
                output.write(encoded + '\n')
        print(encoded, flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('inventory', 'toolbar-inventory', 'run', 'serve'):
        entry = commands.add_parser(command)
        entry.add_argument('--pid', type=int, required=True)
        entry.add_argument('--timeout-ms', type=int, default=3000)
        entry.add_argument('--receipt', required=command == 'run', help='JSON receipt; serve uses an optional JSONL log')
        if command in ('run', 'serve'):
            entry.add_argument('--scope-config', default=os.environ.get('MCGS_NATIVE_SCOPE_CONFIG'),
                               help='Existing native connection layout used for mutation identity')
            entry.add_argument('--scope-sha256', help='Optional exact connection-layout SHA256')
        if command == 'run':
            entry.add_argument('--plan', required=True)
        if command == 'toolbar-inventory':
            entry.add_argument('--toolbar', required=True, type=lambda value: int(value, 0))
    args = parser.parse_args()
    module = backend_module()
    backend = module.Backend(args.pid, args.timeout_ms,
                             project_probe=lambda project: project_probe(project, args.timeout_ms / 1000,
                                 args.scope_config, args.scope_sha256))
    try:
        if args.command == 'serve':
            return serve(backend, args.receipt)
        if args.command in ('inventory', 'toolbar-inventory'):
            result = (backend.inventory() if args.command == 'inventory' else
                      {'status': 'inventory_read', 'items': backend.discover_toolbar({'hwnd': args.toolbar})})
            if args.receipt:
                save(args.receipt, result)
        else:
            result = run_plan(backend, read(args.plan), args.receipt)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('status') in ('inventory_read', 'completed') else 1
    finally:
        backend.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        print(json.dumps({'status': getattr(error, 'status', 'request_failed'), 'error': str(error),
                          'details': getattr(error, 'details', {}), 'automatic_retry': False}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
