"""HWND protocol fixtures, never launches or controls vendor software."""
import argparse
import json
from pathlib import Path
import unittest
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
        self.backend = native.Backend(22, api=self.api)

    def run_plan(self, steps, **options):
        return self.backend.run({'schema': native.SCHEMA, 'steps': steps, **options})

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

    def test_existing_receipt_returns_result_without_replaying(self):
        path = WORK / (uuid.uuid4().hex + '.json')
        plan = {'schema': native.SCHEMA, 'steps': [{'op': 'menu_command', 'path': ['Edit', 'Copy']}]}
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
