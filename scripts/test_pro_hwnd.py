"""HWND protocol fixtures, never launches or controls vendor software."""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import pro_hwnd

native = pro_hwnd.backend_module()
WORK = None


class FakeWindows:
    def __init__(self):
        self.identity = {'pid': 22, 'creation_filetime': 10, 'executable': 'fixture.exe'}
        self.calls, self.windows_calls, self.active, self.menu_id = [], 0, 3, 871
        self.retained_buffers = []
        self.rows = {
            1: self.row(1, 0, 'FixtureFrame', 'Fixture'),
            2: self.row(2, 1, 'MDIClient', ''),
            3: self.row(3, 2, 'FixturePage', 'Old'),
            4: self.row(4, 2, 'FixturePage', 'Target'),
            5: self.row(5, 4, 'FixtureCanvas', ''),
            6: self.row(6, 4, 'Edit', 'before'),
            7: self.row(7, 4, 'Scintilla', 'old source'),
        }
        self.fail_message = None
        self.rows[21] = self.row(21, 1, 'ToolbarWindow32', '')
        self.toolbar_id = 551
        self.toolbar_enabled = True

    def toolbar_buttons(self, hwnd):
        assert hwnd == 21 and self.snapshot(hwnd)['parent'] == 1
        return [{'toolbar': hwnd, 'parent': 1, 'id': self.toolbar_id,
                 'screen_rect': [20, 10, 44, 34], 'enabled': self.toolbar_enabled, 'style': 0}]

    def toolbar_labels(self, hwnd):
        assert hwnd == 21
        return [{'label': 'Fixture tool', 'screen_rect': [22, 12, 43, 32], 'enabled': True}]

    def toolbar_resource_labels(self, command_ids):
        return {}

    @staticmethod
    def row(hwnd, parent, cls, text, owner=0):
        return {'hwnd': hwnd, 'parent': parent, 'owner': owner, 'class_name': cls, 'text': text,
                'visible': True, 'enabled': True, 'control_id': hwnd, 'password': False}

    def close(self):
        pass

    def snapshot(self, hwnd):
        if hwnd not in self.rows:
            raise native.BackendError('missing', status='stale_window')
        return dict(self.rows[hwnd])

    def top_windows(self):
        return [dict(row) for row in self.rows.values() if not row['parent']]

    def children(self, hwnd):
        result = []
        for row in self.rows.values():
            parent = row['parent']
            while parent and parent != hwnd:
                parent = self.rows[parent]['parent']
            if parent == hwnd:
                result.append(dict(row))
        return result

    def windows(self):
        self.windows_calls += 1
        return [dict(row) for row in self.rows.values()]

    def menu(self, hwnd):
        return [{'path': ['Edit', 'Copy'], 'text': 'Copy', 'id': self.menu_id, 'enabled': True,
                 'checked': False, 'submenu': False}] if hwnd == 1 else []

    def send(self, hwnd, message, wparam=0, lparam=0, **kwargs):
        self.calls.append((hwnd, message, wparam, lparam))
        if message == self.fail_message:
            raise native.UnknownOutcome('fixture message timeout', hwnd=hwnd, message=message)
        if message == native.WM_MDIACTIVATE:
            self.active = wparam
        return self.active if message == native.WM_MDIGETACTIVE else 0

    def post(self, hwnd, message, wparam=0, lparam=0):
        self.calls.append((hwnd, message, wparam, lparam))
        if message == native.BM_CLICK or (hwnd, message, wparam, lparam) == (8, native.WM_COMMAND, 10, 10):
            self.rows[8]['visible'] = False
            self.rows[1]['enabled'] = True

    def text(self, hwnd):
        return self.rows[hwnd]['text']

    def set_text(self, hwnd, text):
        self.calls.append((hwnd, native.WM_SETTEXT, text))
        self.rows[hwnd]['text'] = text

    scintilla_text = text
    replace_scintilla = set_text

    def add_dialog(self, body):
        self.rows[1]['enabled'] = False
        self.rows[8] = self.row(8, 0, '#32770', 'Native question', owner=1)
        self.rows[9] = self.row(9, 8, 'Static', body)
        self.rows[10] = self.row(10, 8, 'Button', '&Yes')


class HwndTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeWindows()
        self.project = r'D:\Example\Fixture.mcp'
        self.actual_project = self.project
        self.probe_calls = []
        self.backend = native.Backend(22, api=self.api, project_probe=self.probe)

    def test_inventory_keeps_live_windows_when_a_dialog_closes_mid_read(self):
        windows = object.__new__(native.Win32)
        live = {'hwnd': 1}
        dialog = {'hwnd': 2}
        child = {'hwnd': 3}
        windows.top_windows = lambda: [live, dialog]
        windows.snapshot = self.api.snapshot
        windows.children = lambda hwnd: [child] if hwnd == 1 else []
        def check(hwnd):
            if hwnd == 2:
                raise native.BackendError('Dialog closed', status='stale_window', hwnd=hwnd)
            return hwnd
        windows.check = check
        self.assertEqual(windows.windows(), [live, child])
        self.assertEqual(windows._observed_windows([1, 20, 1]), [self.api.rows[1]])
        with self.assertRaisesRegex(native.BackendError, 'missing'):
            windows.snapshot(20)
        with patch.object(windows, 'children', side_effect=native.BackendError(
                'Editor exited', status='process_exited')):
            with self.assertRaisesRegex(native.BackendError, 'Editor exited'):
                windows.windows()

    def probe(self, expected):
        self.probe_calls.append(expected)
        return {'op': 'engineering-edit-inspect', 'ok': True, 'process_id': 22,
                'creation_filetime': 10, 'actual_project': self.actual_project}

    def run_plan(self, steps, **options):
        return self.backend.run({'schema': native.SCHEMA, 'steps': steps,
                                 'expected_project': self.project, **options})

    def test_inventory_is_read_only_and_capabilities_do_not_claim_project_checks(self):
        report = self.backend.inventory()
        self.assertFalse(report['project_written'])
        self.assertIsNone(report['project_check_passed'])
        self.assertFalse(report['capabilities']['native_object_tree_readback'])
        self.assertTrue(all(message == native.WM_MDIGETACTIVE for _, message, *unused in self.api.calls))

    def test_dynamic_menu_text_path_uses_observed_command_id(self):
        for command_id in (871, 41239):
            self.api.menu_id = command_id
            result = self.run_plan([{'op': 'menu_command', 'path': ['Edit', 'Copy']}])
            self.assertEqual(result['status'], 'completed')
            self.assertIn((1, native.WM_COMMAND, command_id, 0), self.api.calls)
            self.assertFalse(result['steps'][0]['verified'])
            self.assertIsNone(result['project_check_passed'])

    def test_canvas_activates_internal_page_and_reuses_control_cache(self):
        result = self.run_plan([{'op': 'draw', 'canvas': {'class_name': 'FixtureCanvas'}, 'points': [[1, 2], [9, 10]]},
                                {'op': 'draw', 'canvas': {'class_name': 'FixtureCanvas'}, 'points': [[2, 3], [10, 11]]}])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(self.api.active, 4)
        self.assertEqual(self.api.windows_calls, 1)
        self.assertEqual(sum(message == native.WM_MDIACTIVATE for _, message, *unused in self.api.calls), 1)
        self.assertFalse(result['system_foreground_changed'])
        self.assertFalse(result['physical_input_sent'])

    def test_edit_and_scintilla_require_exact_readback(self):
        result = self.run_plan([{'op': 'property_set', 'target': {'hwnd': 6}, 'text': '新文本'},
                                {'op': 'scintilla_replace', 'target': {'hwnd': 7}, 'text': 'x = 1\n'}])
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(all(step['verified'] for step in result['steps']))
        self.assertEqual(self.api.rows[7]['text'], 'x = 1\n')
        self.assertEqual(result['native_project_check'], 'not_performed')

    def test_unknown_modal_is_not_answered(self):
        self.api.add_dialog('Unexpected destructive question')
        result = self.run_plan([{'op': 'menu_command', 'path': ['Edit', 'Copy']}],
                               dialog_responses=[{'match': {'title': 'Native question', 'body_texts': ['Known question']}, 'button': 'Yes'}])
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual(result['steps'][0]['status'], 'blocked_unknown_dialog')
        self.assertEqual(self.api.calls, [])
        self.assertEqual(self.probe_calls, [])

    def test_exact_modal_button_is_posted_and_disappearance_verified(self):
        self.api.add_dialog('Known question')
        result = self.run_plan([{'op': 'respond_dialog', 'match': {'title': 'Native question', 'body_texts': ['Known question']},
                                 'button': 'Yes'}])
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['steps'][0]['verified'])
        self.assertEqual(self.api.calls, [(8, native.WM_COMMAND, 10, 10)])

    def test_unknown_mouse_outcome_stops_without_replay_or_final_save(self):
        self.api.fail_message = native.WM_LBUTTONUP
        result = self.run_plan([{'op': 'draw', 'canvas': {'hwnd': 5}, 'points': [[1, 2], [9, 10]]}],
                               save_command={'path': ['Edit', 'Copy']})
        self.assertEqual(result['status'], 'stopped')
        self.assertTrue(result['unknown_outcome'])
        self.assertEqual(result['remaining_steps'], 1)
        self.assertEqual(sum(message == native.WM_LBUTTONUP for _, message, *unused in self.api.calls), 1)
        self.assertFalse(any(message == native.WM_COMMAND for _, message, *unused in self.api.calls))

    def test_project_path_not_basename_is_required(self):
        self.actual_project = r'D:\Another\Fixture.mcp'
        result = self.run_plan([{'op': 'menu_command', 'path': ['Edit', 'Copy']}])
        self.assertEqual(result['steps'][0]['status'], 'project_identity_mismatch')
        self.assertFalse(any(call[1] == native.WM_COMMAND for call in self.api.calls))
        with self.assertRaises(ValueError):
            self.run_plan([{'op': 'menu_command', 'path': ['Edit', 'Copy']}], expected_project='Fixture.mcp')

    def test_semantic_toolbar_read_only_and_current_dynamic_id(self):
        selector = {'hwnd': 21}
        result = self.run_plan([{'op': 'toolbar_inventory', 'toolbar': selector}], expected_project=None)
        self.assertEqual(result['steps'][0]['items'][0]['label'], 'Fixture tool')
        self.assertEqual(self.probe_calls, [])
        self.api.toolbar_id = 619
        result = self.run_plan([{'op': 'toolbar_command', 'toolbar': selector, 'label': 'Fixture tool',
                                 'page': {'hwnd': 4}}])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(self.api.active, 4)
        self.assertIn((1, native.WM_COMMAND, 619, 0), self.api.calls)
        self.assertFalse(result['steps'][0]['verified'])

    def test_resource_label_falls_back_to_the_current_toolbar_id(self):
        self.api.toolbar_labels = lambda hwnd: []
        calls = []

        def labels(command_ids):
            calls.append(command_ids)
            return {command_id: 'Resource action' for command_id in command_ids}

        self.api.toolbar_resource_labels = labels
        self.api.toolbar_id = 217
        result = self.run_plan([{'op': 'toolbar_command', 'toolbar': {'hwnd': 21},
                                 'label': 'Resource action'}])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(calls, [{217}])
        self.assertIn((1, native.WM_COMMAND, 217, 0), self.api.calls)
        self.assertEqual(result['steps'][0]['toolbar_button']['label_source'], 'executable_command_resource')

    def test_disabled_toolbar_and_unknown_outcome_do_not_retry(self):
        steps = [{'op': 'toolbar_command', 'toolbar': {'hwnd': 21}, 'label': 'Fixture tool'}]
        self.api.toolbar_enabled = False
        result = self.run_plan(steps)
        self.assertEqual(result['steps'][0]['status'], 'toolbar_command_unavailable')
        self.assertFalse(any(call[1] == native.WM_COMMAND for call in self.api.calls))
        self.api.toolbar_enabled = True
        self.api.fail_message = native.WM_COMMAND
        result = self.run_plan(steps + steps)
        self.assertTrue(result['unknown_outcome'])
        self.assertEqual(sum(call[1] == native.WM_COMMAND for call in self.api.calls), 1)

    def test_composite_tool_rejects_conflicting_nested_page_without_mouse_input(self):
        result = self.run_plan([{'op': 'draw', 'canvas': {'hwnd': 5}, 'points': [[1, 2], [9, 10]],
                                'tool_toolbar': {'toolbar': {'hwnd': 21}, 'label': 'Fixture tool',
                                                 'page': {'hwnd': 3}}}])
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual(result['steps'][0]['status'], 'canvas_page_conflict')
        self.assertFalse(any(call[1] in (native.WM_COMMAND, native.WM_LBUTTONDOWN, native.WM_MOUSEMOVE)
                             for call in self.api.calls))

    def test_composite_tool_rechecks_active_page_and_modals_before_mouse_input(self):
        for effect, status in ((lambda: setattr(self.api, 'active', 3), 'canvas_page_changed'),
                               (lambda: self.api.add_dialog('Unexpected tool modal'), 'blocked_unknown_dialog')):
            self.api.calls.clear()
            original = self.api.send

            def send(hwnd, message, wparam=0, lparam=0, **options):
                returned = original(hwnd, message, wparam, lparam, **options)
                if message == native.WM_COMMAND:
                    effect()
                return returned

            with patch.object(self.api, 'send', send):
                result = self.run_plan([{'op': 'draw', 'canvas': {'hwnd': 5}, 'points': [[1, 2], [9, 10]],
                                        'tool_toolbar': {'toolbar': {'hwnd': 21}, 'label': 'Fixture tool'}}])
            self.assertEqual(result['steps'][0]['status'], status)
            self.assertFalse(any(call[1] in (native.WM_MOUSEMOVE, native.WM_LBUTTONDOWN, native.WM_LBUTTONUP)
                                 for call in self.api.calls))
            self.assertFalse(result['system_foreground_changed'])

    def test_composite_tool_same_page_is_kept_active(self):
        result = self.run_plan([{'op': 'draw', 'page': {'hwnd': 4}, 'canvas': {'hwnd': 5},
                                'points': [[1, 2], [9, 10]], 'tool_toolbar': {
                                    'toolbar': {'hwnd': 21}, 'label': 'Fixture tool', 'page': {'hwnd': 4}}}])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(self.api.active, 4)
        command_index = next(index for index, call in enumerate(self.api.calls) if call[1] == native.WM_COMMAND)
        mouse_index = next(index for index, call in enumerate(self.api.calls) if call[1] == native.WM_MOUSEMOVE)
        self.assertTrue(any(call[1] == native.WM_MDIGETACTIVE for call in self.api.calls[command_index + 1:mouse_index]))

    def test_run_cli_binds_connection_before_submitting_project_identity(self):
        base = WORK / uuid.uuid4().hex
        plan, receipt = base.with_suffix('.plan.json'), base.with_suffix('.receipt.json')
        plan.write_text(json.dumps({'schema': native.SCHEMA, 'expected_project': self.project,
                                    'steps': [{'op': 'menu_command', 'path': ['Edit', 'Copy']}]}),
                        encoding='utf-8')
        scope = str(base.with_suffix('.scope.json'))
        digest = '1' * 64
        calls = []

        def configure(path, expected):
            calls.append(('configure', path, expected))

        def load_client():
            self.assertEqual(calls, [('configure', scope, digest)])
            return SimpleNamespace(SubmissionError=RuntimeError, QueueTimeout=TimeoutError)

        def submit(request, request_id, timeout):
            calls.append(('submit', request, timeout))
            self.assertTrue(request_id.startswith('hwnd_identity_'))
            return self.probe(request['expected_project'])

        modules = {'native_delivery_config': SimpleNamespace(configure=configure),
                   'edit_batch_client': SimpleNamespace(load_client=load_client, submit=submit)}
        module = SimpleNamespace(Backend=lambda pid, timeout, project_probe:
                                 native.Backend(pid, timeout, api=self.api, project_probe=project_probe))
        arguments = ['pro_hwnd.py', 'run', '--pid', '22', '--plan', str(plan), '--receipt', str(receipt),
                     '--scope-config', scope, '--scope-sha256', digest]
        self.addCleanup(pro_hwnd.project_client.cache_clear)
        with patch.dict(sys.modules, modules), patch.object(sys, 'argv', arguments), \
                patch.object(pro_hwnd, 'backend_module', return_value=module), redirect_stdout(io.StringIO()):
            self.assertEqual(pro_hwnd.main(), 0)
        self.assertEqual(pro_hwnd.read(receipt)['status'], 'completed')
        self.assertEqual(calls[1], ('submit', {'op': 'engineering-edit-inspect',
                                              'expected_project': self.project}, 3.0))

    def test_existing_receipt_returns_result_without_replaying(self):
        path = WORK / (uuid.uuid4().hex + '.json')
        plan = {'schema': native.SCHEMA, 'expected_project': self.project, 'steps': [{'op': 'menu_command', 'path': ['Edit', 'Copy']}]}
        pro_hwnd.run_plan(self.backend, plan, path)
        before = list(self.api.calls)
        result = pro_hwnd.run_plan(self.backend, plan, path)
        self.assertTrue(result['reused_receipt'])
        self.assertEqual(before, self.api.calls)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    WORK = args.work.resolve()
    WORK.mkdir(parents=True, exist_ok=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HwndTests))
    report = {'tests_run': result.testsRun, 'passed': result.wasSuccessful(), 'failures': len(result.failures),
              'errors': len(result.errors), 'vendor_software_executed': False, 'compiler_executed': False}
    (WORK / 'test-result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
