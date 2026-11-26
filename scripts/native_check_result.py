"""Read a visible check-result dialog from an explicitly selected editor process."""
import argparse
import subprocess
import json
import os
from pathlib import Path
import re
import shutil
import sys


SUMMARY = re.compile(
    r'(?P<label>组态检查(?:通过|未通过|失败|完成))\s*[!！。:：]?\s*'
    r'发现错误\s*[:：]\s*(?P<errors>[0-9]+)\s*个\s*[,，、]\s*'
    r'警告\s*[:：]\s*(?P<warnings>[0-9]+)\s*个\s*[。.!！]?'
)
IDENTITY_FIELDS = ('hwnd', 'parent', 'owner', 'class_name', 'control_id')
LIST_CONTROLS = {'listbox', 'syslistview32', 'systreeview32'}


def identity(row):
    return {key: row[key] for key in IDENTITY_FIELDS if key in row}


def parse_dialog(dialog, children):
    """Retain exact visible text, never derive counts from a truncated detail list."""
    result = {'dialog': {**identity(dialog), 'caption': dialog.get('text', '')},
              'counts_observed': False, 'error_count': None, 'warning_count': None,
              'check_passed': None, 'observed_rows': [], 'detail_controls_unread': []}
    if dialog.get('class_name') != '#32770' or dialog.get('visible') is not True:
        return {**result, 'status': 'not_visible_dialog'}
    summaries = []
    captions = [(dialog, [dialog.get('text', '')])]
    for row in children:
        if row.get('visible') is not True or row.get('password'):
            continue
        cls = row.get('class_name', '').casefold()
        if row.get('detail_read_error'):
            result['detail_controls_unread'].append({**identity(row), 'reason': row['detail_read_error'],
                **({'provider_failure': row['provider_failure']} if 'provider_failure' in row else {})})
        if cls == 'static' or cls in LIST_CONTROLS:
            captions.append((row, row.get('items', []) if cls in LIST_CONTROLS else [row.get('text', '')]))
    for row, strings in captions:
        for index, item in enumerate(strings):
            value = item['text'] if isinstance(item, dict) else item
            if not value.strip():
                continue
            entry = {**identity(row), 'item_index': index, 'text': value}
            if isinstance(item, dict):
                entry.update({key: item[key] for key in ('runtime_id', 'type', 'provider', 'cells', 'accessible_path') if key in item})
            if row is not dialog:
                result['observed_rows'].append(entry)
            if row is not dialog and row.get('class_name', '').casefold() != 'static':
                continue
            lines = [value] if SUMMARY.fullmatch(value.strip()) else value.splitlines()
            for line in lines:
                match = SUMMARY.fullmatch(line.strip())
                if match:
                    summaries.append((match['label'], int(match['errors']), int(match['warnings']), entry))
    if not summaries:
        return {**result, 'status': 'summary_not_observed'}
    if len({s[:3] for s in summaries}) != 1:
        return {**result, 'status': 'conflicting_summaries'}
    label, errors, warnings, source = summaries[0]
    passed = {'组态检查通过': True, '组态检查未通过': False, '组态检查失败': False}.get(label)
    if passed and errors:
        return {**result, 'status': 'contradictory_summary', 'summary_source': source}
    return {**result, 'status': 'observed', 'counts_observed': True, 'error_count': errors,
            'warning_count': warnings, 'check_passed': passed, 'summary_source': source}


def list_items(api, row, powershell=None):
    helper = Path(__file__).with_name('read_check_result_rows.ps1')
    exe = powershell or shutil.which('pwsh')
    if exe is None:
        return {'detail_read_error': 'powershell_not_available'}
    command = [str(exe), '-NoProfile', '-NonInteractive', '-File', str(helper),
               '-EditorPid', str(api.pid), '-ControlHwnd', str(api.check(row['hwnd']))]
    try:
        completed = subprocess.run(command, capture_output=True, timeout=15, check=False,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        if completed.returncode:
            error = completed.stderr.decode('utf-8-sig', errors='replace').strip()
            return {'detail_read_error': 'accessibility_helper_failed',
                    'provider_failure': {'exit_code': completed.returncode, 'stderr': error[-2000:]}}
        items = json.loads(completed.stdout.decode('utf-8-sig'))['rows']
        if not isinstance(items, list):
            raise ValueError('Expected accessible rows')
        return {'items': items} if items else {'items': [], 'detail_read_error': 'no_visible_accessible_rows'}
    except subprocess.TimeoutExpired:
        return {'detail_read_error': 'accessibility_read_timeout', 'provider_failure': {'timeout_seconds': 15}}
    except (OSError, KeyError, ValueError) as exc:
        return {'detail_read_error': 'accessibility_read_unavailable',
                'provider_failure': {'type': type(exc).__name__, 'message': str(exc)[:2000]}}


def capture(api, main_hwnd, dialog_hwnd=None, powershell=None, details_hwnd=None,
            detail_control_hwnd=None):
    if (details_hwnd is None) != (detail_control_hwnd is None):
        raise ValueError('Provide both the details window and list control handles')
    tops = {row['hwnd']: row for row in api.top_windows()}
    main = tops.get(main_hwnd)
    if not main or main.get('class_name') == '#32770' or not main['visible']:
        raise ValueError('Selected visible editor main window is missing')
    def owned(row, windows=tops):
        owner = row.get('owner')
        seen = set()
        while owner in windows and owner not in seen:
            if owner == main_hwnd:
                return True
            seen.add(owner)
            owner = windows[owner].get('owner')
        return False
    dialogs = [r for r in tops.values() if r['class_name'] == '#32770' and r['visible'] and owned(r)
               and (dialog_hwnd is None or r['hwnd'] == dialog_hwnd)]
    observed = []
    for dialog in dialogs:
        children = api.children(dialog['hwnd'])
        for row in children:
            if row['visible'] and row['class_name'].casefold() in LIST_CONTROLS:
                first = list_items(api, row, powershell)
                second = list_items(api, row, powershell)
                if first == second and identity(row) == identity(api.snapshot(row['hwnd'])):
                    row.update(second)
                else:
                    row['detail_read_error'] = 'details_changed_during_capture'
        result = parse_dialog(dialog, children)
        if (result['status'] != 'summary_not_observed' or dialog_hwnd is not None
                or dialog.get('text') == '组态检查列表(双击打开修改)'):
            observed.append(result)
    details = None
    if details_hwnd is not None:
        def read_details():
            current_tops = {row['hwnd']: row for row in api.top_windows()}
            top = current_tops.get(details_hwnd)
            if not top or not top['visible'] or details_hwnd != main_hwnd and not owned(top, current_tops):
                raise ValueError('Selected details window is outside the visible editor ownership chain')
            descendants = {row['hwnd']: row for row in api.children(details_hwnd)}
            row = descendants.get(detail_control_hwnd)
            if not row or not row['visible'] or row['class_name'].casefold() not in LIST_CONTROLS:
                raise ValueError('Selected details list is missing from its window')
            parent = row.get('parent')
            seen = set()
            while parent in descendants and parent not in seen:
                seen.add(parent)
                parent = descendants[parent].get('parent')
            if parent != details_hwnd:
                raise ValueError('Selected details control parent chain changed')
            return {'window': identity(top), 'control': identity(row), **list_items(api, row, powershell)}
        first, second = read_details(), read_details()
        if first != second:
            details = {'window': second['window'], 'control': second['control'], 'items': [],
                       'detail_read_error': 'details_changed_during_capture'}
        else:
            details = second
        details['visible_rows_observed'] = bool(details.get('items'))
        details['all_diagnostics_verified'] = False
        details['same_check_operation_verified'] = False
    api.check(main_hwnd)
    for dialog in dialogs:
        fresh = api.snapshot(dialog['hwnd'])
        if not fresh['visible'] or any(fresh[k] != dialog[k] for k in ('owner', 'class_name', 'text')):
            raise ValueError('Dialog changed during evidence capture')
    summaries = [result for result in observed if result['status'] != 'summary_not_observed']
    status = 'observed' if len(summaries) == 1 and summaries[0]['counts_observed'] else 'result_unconfirmed'
    return {'status': status, 'process': api.identity, 'main_window': identity(main),
            'candidate_dialogs': [identity(d) for d in dialogs], 'results': observed,
            'selected_details': details, 'native_compile_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--editor', type=Path, required=True)
    parser.add_argument('--main-hwnd', type=lambda v: int(v, 0), required=True)
    parser.add_argument('--dialog-hwnd', type=lambda v: int(v, 0))
    parser.add_argument('--details-hwnd', type=lambda v: int(v, 0), help='Visible top-level details window')
    parser.add_argument('--detail-control-hwnd', type=lambda v: int(v, 0), help='Exact list descendant of the details window')
    parser.add_argument('--powershell', type=Path, help='PowerShell 7 executable for Windows accessibility details')
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/pro-native-bridge/client'))
    from hwnd_backend import Win32
    api = Win32(args.pid)
    try:
        if not os.path.samefile(args.editor, api.identity['executable']):
            raise ValueError('PID executable differs from the selected editor')
        result = capture(api, args.main_hwnd, args.dialog_hwnd, args.powershell, args.details_hwnd, args.detail_control_hwnd)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] == 'observed' else 2
    finally:
        api.close()


if __name__ == '__main__':
    raise SystemExit(main())
