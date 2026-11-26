"""Stu native command routing against program-owned queue responses."""

from argparse import Namespace
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import stu_native_client as stu


class SubmissionError(ValueError):
    pass


class QueueTimeout(TimeoutError):
    def __init__(self, state):
        super().__init__('Outcome unknown')
        self.state = state


class StuNativeClientTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.project = self.root / '审核.MCS'
        self.project.touch()
        self.editor = self.root / 'Program/McgsSetStu.exe'
        self.scope = self.root / 'engine.scope.json'
        self.connection_file = self.root / 'connection.json'
        self.descriptor = {
            'status': 'connected', 'scope_config': str(self.scope), 'scope_sha256': 'a' * 64,
            'active_engine': {'engine_scope_sha256': 'a' * 64, 'sha256': 'b' * 64, 'bootstrap_scope_sha256': 'c' * 64},
            'target': {'editor': str(self.editor), 'pid': 17, 'ui_thread': 34, 'creation_filetime': 1234567890},
        }
        self.connection = self.read_connection()
        self.layout = SimpleNamespace(runtime_root=self.root)
        self.queue = Mock()
        self.queue.load_client.return_value = SimpleNamespace(SubmissionError=SubmissionError, QueueTimeout=QueueTimeout)

    def read_connection(self):
        self.connection_file.write_text(json.dumps(self.descriptor), encoding='utf-8')
        return stu.Connection.read(self.connection_file)

    def receipt(self, operation, **fields):
        return {
            'ok': True, 'op': operation, 'engine_family': 'McgsStu', 'project_path': str(self.project),
            'application_project_path': str(self.project), 'process_id': 17, 'thread_id': 34,
            'creation_filetime': 1234567890, 'engineering_delivery_scope_sha256': 'a' * 64,
            'bridge_bootstrap_scope_sha256': 'c' * 64, 'engine_sha256': 'b' * 64, 'read_only': True,
            'request_id': 'stu-request', 'queue_request_sha256': 'd' * 64, **fields,
        }

    def execute(self, operation, **fields):
        args = {'command': operation, 'project': self.project, 'out': None, 'id': 'stu-request', 'timeout': 9, **fields}
        return stu.execute(Namespace(**args), self.connection, self.layout, self.queue)

    def batch_spec(self, *changes):
        options = {'page_id': 2, 'page': '显示页', 'changes': list(changes)}
        path = self.root / 'changes.json'
        path.write_text(json.dumps(options, ensure_ascii=False), encoding='utf-8')
        return path, options

    def page_spec(self, options):
        spec = self.root / 'page-change.json'
        spec.write_text(json.dumps(options, ensure_ascii=False), encoding='utf-8')
        return spec

    def label(self, caption='确认', primary='确认', color=0x121314, **after):
        return {'control_name': '状态文字', 'native_type_id': 39,
                'before': {'caption': caption, 'caption_primary': primary, 'text_color_bgr': color}, 'after': after}

    def geometry(self, path=None, before=None, after=None, native_type=0x5008):
        return {'control_name': '控件41', 'native_type_id': native_type,
                'top_level_path': [28] if path is None else path,
                'before': {'rect': [219, 262, 297, 282] if before is None else before},
                'after': {'rect': [230, 262, 308, 282] if after is None else after}}

    def lifecycle_receipt(self, operation):
        closed = operation == stu.lifecycle.CLOSE
        action = 'close' if closed else 'open'
        confirm = 'close_confirmed_empty' if closed else 'open_confirmed_same_project'
        return self.receipt(operation, expected_project=str(self.project), read_only=False,
                            project_path=None if closed else str(self.project),
                            application_project_path=None if closed else str(self.project),
                            lifecycle_state='closed' if closed else 'open',
                            state_after={'roots_agree': True, 'current_root_present': not closed,
                                         'canonical_root_present': not closed, 'open_in_progress': False,
                                         'verified_same_project': not closed},
                            **{action + '_entered': True, action + '_returned': True, confirm: True})

    def lifecycle_queue(self):
        committed = {}
        reserved = self.root / 'client-submissions'
        reserved.mkdir()
        self.queue.load_client.return_value.RESERVED = set()
        self.queue.owned_file.side_effect = lambda path, exists=True: Path(path)
        self.queue.request_bytes.side_effect = lambda request, identifier, **kwargs: json.dumps(
            [identifier, request], sort_keys=True).encode()

        def write(path, value):
            path.parent.mkdir(exist_ok=True)
            with path.open('x', encoding='utf-8') as record:
                json.dump(value, record)

        self.queue.write_new.side_effect = write
        self.queue.read_json.side_effect = lambda path: (json.loads(path.read_text(encoding='utf-8')), None)
        self.queue.read_existing_result.side_effect = lambda identifier, digest: (
            {'ok': True, 'result': committed[identifier]} if identifier in committed
            else {'ok': False, 'status': 'no_correlated_response_yet'})

        def submit(request, identifier, timeout):
            (reserved / (identifier + '.json')).touch(exist_ok=False)
            outcome = self.lifecycle_receipt(request['op'])
            committed[identifier] = outcome
            return outcome

        self.queue.submit.side_effect = submit
        return committed, reserved, submit

    def test_project_reopen_uses_separate_correlated_stages(self):
        self.lifecycle_queue()
        result = self.execute(stu.lifecycle.REOPEN)
        self.assertTrue(result['ok'])
        self.assertEqual(result['status'], 'same_project_reopened')
        self.assertEqual([call.args[1] for call in self.queue.submit.call_args_list],
                         ['stu-request-close', 'stu-request-open'])
        close, opened = [call.args[0] for call in self.queue.submit.call_args_list]
        self.assertIs(close['verify_reopen'], True)
        self.assertNotIn('verify_reopen', opened)
        self.assertEqual(close['expected_engine_sha256'], opened['expected_engine_sha256'])
        read = self.execute(stu.lifecycle.READ_REOPEN, continue_open=False)
        self.assertTrue(read['ok'])
        self.assertEqual(self.queue.submit.call_count, 2)

    def test_project_reopen_close_timeout_is_observed_before_any_open(self):
        committed, reserved, send = self.lifecycle_queue()

        def delayed_close(request, identifier, timeout):
            if request['op'] == stu.lifecycle.CLOSE:
                (reserved / (identifier + '.json')).touch(exist_ok=False)
                raise QueueTimeout({'request_id': identifier})
            return send(request, identifier, timeout)

        self.queue.submit.side_effect = delayed_close
        first = self.execute(stu.lifecycle.REOPEN)
        self.assertEqual(first['status'], 'close_not_confirmed')
        blocked = self.execute(stu.lifecycle.READ_REOPEN, continue_open=True)
        self.assertEqual(blocked['status'], 'close_not_confirmed')
        self.assertEqual(self.queue.submit.call_count, 1)
        committed['stu-request-close'] = self.lifecycle_receipt(stu.lifecycle.CLOSE)
        seen = self.execute(stu.lifecycle.READ_REOPEN, continue_open=False)
        self.assertEqual(seen['open']['status'], 'not_submitted')
        resumed = self.execute(stu.lifecycle.READ_REOPEN, continue_open=True)
        self.assertEqual(resumed['status'], 'same_project_reopened')
        self.assertEqual([call.args[0]['op'] for call in self.queue.submit.call_args_list],
                         [stu.lifecycle.CLOSE, stu.lifecycle.OPEN])

    def test_project_reopen_does_not_resubmit_an_open_after_timeout(self):
        committed, reserved, send = self.lifecycle_queue()

        def delayed_open(request, identifier, timeout):
            if request['op'] == stu.lifecycle.OPEN:
                (reserved / (identifier + '.json')).touch(exist_ok=False)
                raise QueueTimeout({'request_id': identifier})
            return send(request, identifier, timeout)

        self.queue.submit.side_effect = delayed_open
        first = self.execute(stu.lifecycle.REOPEN)
        self.assertEqual(first['status'], 'open_not_confirmed')
        pending = self.execute(stu.lifecycle.READ_REOPEN, continue_open=True)
        self.assertEqual(pending['open']['status'], 'no_correlated_response_yet')
        self.assertEqual(self.queue.submit.call_count, 2)
        committed['stu-request-open'] = self.lifecycle_receipt(stu.lifecycle.OPEN)
        finished = self.execute(stu.lifecycle.READ_REOPEN, continue_open=True)
        self.assertTrue(finished['ok'])
        self.assertEqual(self.queue.submit.call_count, 2)

    def test_rejects_pro_and_wrong_selected_scope(self):
        self.descriptor['target']['editor'] = str(self.editor.with_name('McgsSetPro.exe'))
        with self.assertRaisesRegex(ValueError, 'McgsSetStu'):
            self.read_connection()
        self.descriptor['target']['editor'] = str(self.editor)
        self.descriptor['active_engine']['engine_scope_sha256'] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'different scope'):
            self.read_connection()

    def test_bind_supplies_a_text_path_to_the_shared_scope_parser(self):
        layout = SimpleNamespace(editor_executable=self.editor)
        configure = Mock(return_value=layout)
        queue = SimpleNamespace()
        with patch.dict(sys.modules, {'native_delivery_config': SimpleNamespace(configure=configure),
                                       'edit_batch_client': queue}):
            self.assertEqual(stu.bind(self.connection), (layout, queue))
        configure.assert_called_once_with(str(self.scope), 'a' * 64)

    def test_control_catalog_submits_exact_family_and_page_once(self):
        receipt = self.receipt('control-catalog')
        self.queue.submit.return_value = receipt
        self.assertEqual(self.execute('control-catalog', page_id=0, page='显示页'), receipt)
        self.queue.submit.assert_called_once_with({
            'op': 'control-catalog', 'expected_project': str(self.project), 'expected_engine_family': 'McgsStu',
            'expected_process_id': 17, 'expected_ui_thread_id': 34, 'expected_creation_filetime': 1234567890,
            'options': {'page_id': 0, 'page': '显示页'},
        }, 'stu-request', 9)

    def test_view_activation_checks_native_page_identity_and_active_flag(self):
        view = {'page_id': 2, 'page': '显示页', 'exact_page_is_active': True, 'opened_new_view': False}
        self.queue.submit.return_value = self.receipt('page-view-open', page_view=view)
        self.assertEqual(stu.exit_status(self.execute('page-view-open', page_id=2, page='显示页')), 0)
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], {'page_id': 2, 'page': '显示页'})
        self.queue.submit.assert_called_once()
        self.assertEqual(stu.exit_status(self.receipt('page-view-open', page_view=dict(view, exact_page_is_active=False))), 2)
        result = self.execute('page-view-open', page_id=3, page='显示页')
        self.assertEqual(result['mismatches'], ['page_view'])

    def test_label_batch_submits_one_options_body_and_reports_saves_separately(self):
        spec, options = self.batch_spec(self.label(caption='前值', primary='前值', text_color_bgr=0x112233))
        self.queue.submit.return_value = self.receipt('label-properties-batch', read_only=False, write_attempted=True,
            completed_count=1, view_refresh_verified=True, page_save_verified=True, root_save_verified=False)
        result = self.execute('label-properties-batch', spec=spec)
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        self.queue.submit.assert_called_once()
        self.assertTrue(result['write_attempted'])
        self.assertTrue(result['page_save_verified'])
        self.assertFalse(result['root_save_verified'])
        self.assertEqual(stu.exit_status(result), 2)
        self.assertEqual(stu.exit_status(dict(result, root_save_verified=True)), 0)

    def test_label_batch_guards_both_original_captions_and_the_color_word(self):
        inconsistent = self.label(caption='编辑器值', primary='主语言值')
        inconsistent['after'] = {'caption': '新的值'}
        high_byte_change = self.label(color=-1, text_color_bgr=0x112233)
        duplicate = self.label(text_color_bgr=0x112233)
        for changes in ((inconsistent,), (high_byte_change,), (duplicate, duplicate)):
            with self.subTest(changes=changes):
                spec, _ = self.batch_spec(*changes)
                with self.assertRaises(ValueError):
                    self.execute('label-properties-batch', spec=spec)
        self.queue.submit.assert_not_called()

    def test_no_change_uses_no_save_and_preserves_the_original_full_color(self):
        change = self.label(color=-1)
        change['after'] = {'caption': '确认'}
        spec, options = self.batch_spec(change)
        self.queue.submit.return_value = self.receipt('label-properties-batch', status='no_changes', read_only=True,
            write_attempted=False, completed_count=0, view_refresh_verified=False, page_save_verified=False,
            root_save_verified=False)
        result = self.execute('label-properties-batch', spec=spec)
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        self.assertFalse(result['write_attempted'])
        self.assertEqual(stu.exit_status(result), 0)

    def test_geometry_batch_sends_native_paths_and_exact_rectangles_once(self):
        changes = (self.geometry(), self.geometry(path=[16], before=[-12, -8, 2, 3], after=[-9, -8, 5, 3],
                                                  native_type=0x5025))
        spec, options = self.batch_spec(*changes)
        actual = [{'top_level_path': row['top_level_path'], 'actual': row['after']} for row in changes]
        self.queue.submit.return_value = self.receipt('control-geometry-batch', read_only=False, write_attempted=True,
            completed_count=2, view_refresh_verified=True, page_save_verified=True, root_save_verified=True,
            changes=actual)
        result = self.execute('control-geometry-batch', spec=spec)
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        self.queue.submit.assert_called_once()
        self.assertEqual(result['changes'], actual)
        self.assertEqual(stu.exit_status(result), 0)

    def test_geometry_rejects_nested_paths_and_unrepresentable_rectangles(self):
        for changes in ((self.geometry(path=[57, 3]),), (self.geometry(path=[False]),),
                        (self.geometry(), self.geometry()), (self.geometry(after=[1, 2, 1, 3]),),
                        (self.geometry(after=[-0x80000000, 2, 3, 4]),), (self.geometry(before=[0, 1, 2, 0x80000000]),)):
            with self.subTest(changes=changes):
                spec, _ = self.batch_spec(*changes)
                with self.assertRaises(ValueError):
                    self.execute('control-geometry-batch', spec=spec)
        self.queue.submit.assert_not_called()

    def test_geometry_saved_and_partial_results_stay_distinct(self):
        spec, _ = self.batch_spec(self.geometry())
        partial = {'ok': False, 'operation_phase': 'root-save', 'write_attempted': True,
                   'native_result_may_be_partial': True, 'view_refresh_verified': True, 'page_save_verified': True,
                   'root_save_verified': False, 'changes': [{'top_level_path': [28], 'actual': {'rect': [230, 262, 308, 282]}}]}
        self.queue.submit.return_value = partial
        result = self.execute('control-geometry-batch', spec=spec)
        self.assertEqual(result, partial)
        self.assertEqual(stu.exit_status(result), 1)
        self.queue.submit.assert_called_once()

    def clone_receipt(self, changes):
        cloned = []
        for offset, source in enumerate(changes):
            row = {key: source[key] for key in ('control_name', 'native_type_id', 'top_level_path', 'before')}
            row['actual'] = {'control_name': f'原厂名称{offset}', 'native_type_id': source['native_type_id'],
                             'native_class': '.?AVCDrawLabel@@', 'top_level_path': [61 + offset],
                             'rect': source['after']['rect'], 'original_payload_preserved': True}
            cloned.append(row)
        view = {'page_id': 2, 'page': '显示页', 'exact_page_is_active': True}
        return self.receipt(stu.CLONE_COMMAND, status='applied_and_saved', read_only=False, write_attempted=True,
                            changes=cloned, completed_count=len(cloned), page_view=view, view_refresh_verified=True,
                            page_save_verified=True, root_save_verified=True)

    def test_clone_submits_repeated_source_and_identical_target_rectangles_once(self):
        source = self.geometry()
        spec, options = self.batch_spec(source, deepcopy(source))
        self.queue.submit.return_value = self.clone_receipt(options['changes'])
        result = self.execute(stu.CLONE_COMMAND, spec=spec)
        self.queue.submit.assert_called_once()
        body = self.queue.submit.call_args.args[0]
        self.assertEqual(body['op'], stu.CLONE_COMMAND)
        self.assertEqual(body['options'], options)
        self.assertEqual([row['actual']['top_level_path'] for row in result['changes']], [[61], [62]])
        self.assertEqual(stu.exit_status(result), 0)

    def test_clone_accepts_only_a_native_top_level_source_and_rectangle_target(self):
        custom_name = self.geometry()
        custom_name['after']['control_name'] = '不能指定复制名称'
        for source in (custom_name, self.geometry(path=[9, 0]), self.geometry(after=[0, 0, 0, 1])):
            with self.subTest(source=source):
                spec, _ = self.batch_spec(source)
                with self.assertRaises(ValueError):
                    self.execute(stu.CLONE_COMMAND, spec=spec)
        self.queue.submit.assert_not_called()

    def test_clone_checks_exact_requested_target_and_original_append_identity(self):
        spec, options = self.batch_spec(self.geometry(), self.geometry(path=[16]))
        receipt = self.clone_receipt(options['changes'])
        cases = (
            ('top_level_path', [61]),
            ('control_name', '原厂名称0'),
            ('native_type_id', 0x5025),
            ('native_class', '.?AVCDrawEdit@@'),
            ('rect', [230, 262, 309, 282]),
            ('original_payload_preserved', False),
        )
        for key, value in cases:
            with self.subTest(key=key):
                changed = deepcopy(receipt)
                changed['changes'][1]['actual'][key] = value
                self.queue.submit.return_value = changed
                result = self.execute(stu.CLONE_COMMAND, spec=spec)
                self.assertFalse(result['ok'])
                self.assertEqual(result['mismatches'], ['clone_changes'])
                self.assertEqual(result['native_receipt'], changed)
                self.assertFalse(result['automatic_retry'])
        changed = deepcopy(receipt)
        changed['page_view']['page_id'] = 1
        self.queue.submit.return_value = changed
        self.assertEqual(self.execute(stu.CLONE_COMMAND, spec=spec)['mismatches'], ['page_view'])
        self.assertEqual(self.queue.submit.call_count, len(cases) + 1)

    def test_clone_activation_refresh_and_both_saves_are_independent(self):
        source = self.geometry()
        receipt = self.clone_receipt([source])
        self.assertEqual(stu.exit_status(receipt), 0)
        receipt['page_view']['exact_page_is_active'] = False
        self.assertEqual(stu.exit_status(receipt), 2)
        receipt['page_view']['exact_page_is_active'] = True
        for flag in ('view_refresh_verified', 'page_save_verified', 'root_save_verified'):
            with self.subTest(flag=flag):
                self.assertEqual(stu.exit_status(dict(receipt, **{flag: False})), 2)
        self.assertEqual(stu.exit_status(dict(receipt, completed_count=0, status='no_changes')), 2)

    def test_clone_timeout_and_partial_outcome_reuse_original_request_without_replay(self):
        source = self.geometry()
        spec, _ = self.batch_spec(source)
        state = {'request_id': 'stu-request', 'queue_request_sha256': 'd' * 64, 'automatic_retry': False}
        self.queue.submit.side_effect = QueueTimeout(state)
        initial = self.execute(stu.CLONE_COMMAND, spec=spec)
        self.assertEqual(initial['transport_state'], state)
        partial = self.clone_receipt([source, source])
        partial.update(ok=False, native_result_may_be_partial=True, completed_count=1,
                       view_refresh_verified=False, page_save_verified=False, root_save_verified=False)
        partial['changes'][1]['actual'] = None
        self.queue.read_existing_result.return_value = {'ok': True, 'status': 'correlated_response_observed',
                                                        'result': partial}
        seen = self.execute('request-result', request_sha256='d' * 64)
        self.assertEqual(seen['result'], partial)
        self.assertEqual(stu.exit_status(seen), 1)
        self.queue.submit.assert_called_once()
        self.queue.read_existing_result.assert_called_once_with('stu-request', 'd' * 64)

    def creation_sources(self):
        return (
            {'native_type_id': 0x5008, 'after': {'rect': [12, 10, 65, 36]}},
            {'native_type_id': 0x5025, 'after': {'rect': [30, 40, 105, 56]}},
            {'native_type_id': 0x5027, 'after': {'rect': [30, 65, 104, 95]}},
        )

    def creation_receipt(self, changes):
        native_classes = {0x5008: '.?AVCDrawLabel@@', 0x5025: '.?AVCDrawEdit@@', 0x5027: '.?AVCDrawButton@@'}
        result = []
        for offset, requested in enumerate(changes):
            native_type = requested['native_type_id']
            result.append({'native_type_id': native_type, 'phase': 'verified',
                           'actual': {'control_name': f'控件{offset + 200}', 'top_level_path': [12 + offset],
                                      'native_type_id': native_type, 'native_class': native_classes[native_type],
                                      'rect': requested['after']['rect'], 'original_defaults_preserved': True}})
        view = {'page_id': 2, 'page': '显示页', 'exact_page_is_active': True}
        return self.receipt(stu.CREATE_COMMAND, status='applied_and_saved', read_only=False, write_attempted=True,
                            changes=result, completed_count=len(result), page_view=view, view_refresh_verified=True,
                            page_save_verified=True, root_save_verified=True)

    def test_native_creation_submits_three_native_types_and_repeated_targets_once(self):
        choices = self.creation_sources()
        spec, options = self.batch_spec(*choices, deepcopy(choices[0]))
        self.queue.submit.return_value = self.creation_receipt(options['changes'])
        result = self.execute(stu.CREATE_COMMAND, spec=spec)
        self.queue.submit.assert_called_once()
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        self.assertEqual([row['actual']['top_level_path'] for row in result['changes']], [[12], [13], [14], [15]])
        self.assertTrue(all(row['actual']['original_defaults_preserved'] for row in result['changes']))
        self.assertEqual(stu.exit_status(result), 0)

    def test_native_creation_checks_type_and_rectangle_without_accepting_initial_values(self):
        source = self.creation_sources()[0]
        for change in (dict(source, native_type_id=True), dict(source, native_type_id=0x5009),
                       dict(source, before={'rect': [0, 0, 0, 0]}),
                       dict(source, after={'rect': [2, 4, 6, 8], 'caption': 'override'}),
                       dict(source, after={'rect': [-0x80000000, 0, 1, 1]})):
            with self.subTest(change=change):
                spec, _ = self.batch_spec(change)
                with self.assertRaises(ValueError):
                    self.execute(stu.CREATE_COMMAND, spec=spec)
        self.queue.submit.assert_not_called()

    def test_native_creation_receipt_requires_original_defaults_and_exact_append(self):
        choices = self.creation_sources()
        spec, _ = self.batch_spec(*choices)
        receipt = self.creation_receipt(choices)
        invalid = (
            ('original_defaults_preserved', False),
            ('rect', [30, 40, 105, 57]),
            ('top_level_path', [12]),
            ('control_name', '控件200'),
            ('native_class', '.?AVCDrawLabel@@'),
        )
        for key, value in invalid:
            with self.subTest(key=key):
                changed = deepcopy(receipt)
                changed['changes'][1]['actual'][key] = value
                self.queue.submit.return_value = changed
                result = self.execute(stu.CREATE_COMMAND, spec=spec)
                self.assertEqual(result['mismatches'], ['creation_changes'])
                self.assertEqual(result['native_receipt'], changed)
                self.assertFalse(result['automatic_retry'])
        wrong_page = deepcopy(receipt)
        wrong_page['page_view']['page'] = '另一个页面'
        self.queue.submit.return_value = wrong_page
        self.assertEqual(self.execute(stu.CREATE_COMMAND, spec=spec)['mismatches'], ['page_view'])

    def test_native_creation_timeout_preserves_partial_results_and_save_flags(self):
        choices = self.creation_sources()
        spec, _ = self.batch_spec(*choices)
        state = {'request_id': 'stu-request', 'queue_request_sha256': 'd' * 64, 'automatic_retry': False}
        self.queue.submit.side_effect = QueueTimeout(state)
        initial = self.execute(stu.CREATE_COMMAND, spec=spec)
        self.assertEqual(initial['transport_state'], state)
        receipt = self.creation_receipt(choices)
        for flag in ('view_refresh_verified', 'page_save_verified', 'root_save_verified'):
            self.assertEqual(stu.exit_status(dict(receipt, **{flag: False})), 2)
        inactive = dict(receipt['page_view'], exact_page_is_active=False)
        self.assertEqual(stu.exit_status(dict(receipt, page_view=inactive)), 2)
        partial = dict(receipt, ok=False, native_result_may_be_partial=True, completed_count=1,
                       view_refresh_verified=False, page_save_verified=False, root_save_verified=False)
        for row in partial['changes'][1:]:
            row['actual'] = None
        self.queue.read_existing_result.return_value = {'ok': True, 'status': 'correlated_response_observed',
                                                        'result': partial}
        seen = self.execute('request-result', request_sha256='d' * 64)
        self.assertEqual(seen['result'], partial)
        self.assertEqual(stu.exit_status(seen), 1)
        self.queue.submit.assert_called_once()
        self.queue.read_existing_result.assert_called_once_with('stu-request', 'd' * 64)

    def created_page_receipt(self, operation, **fields):
        outcome = dict(status='applied_and_saved', read_only=False, write_attempted=True,
                       new_page_id=37, new_page_name='原厂新页', page_count=5, top_level_control_count=0,
                       native_saved=True, page_save_verified=True, native_page_save_called=False,
                       root_save_verified=True, post_save_page_readback_verified=True,
                       original_active_view_preserved=True, completed_count=1)
        if operation == stu.PAGE_COPY_COMMAND:
            outcome.update(source_page_id=2, source_page_name='原完整页名称', top_level_control_count=3,
                           copy_mode='native-page-archive')
        return self.receipt(operation, **(outcome | fields))

    def test_native_page_create_submits_exact_count_and_reports_only_actual_page_save(self):
        options = {'page_name': '原厂新页', 'expected_page_count': 4}
        native = self.created_page_receipt(stu.PAGE_CREATE_COMMAND)
        self.queue.submit.return_value = native
        result = self.execute(stu.PAGE_CREATE_COMMAND, spec=self.page_spec(options))
        self.assertEqual(result, native)
        self.assertTrue(result['page_save_verified'])
        self.assertFalse(result['native_page_save_called'])
        self.assertEqual(stu.exit_status(result), 0)
        self.queue.submit.assert_called_once()
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        self.assertEqual(self.queue.submit.call_args.args[0]['expected_project'], str(self.project))

    def test_native_page_copy_checks_source_and_distinct_new_page(self):
        options = {'page_name': '原厂新页', 'expected_page_count': 4,
                   'source_page_id': 2, 'source_page_name': '原完整页名称'}
        spec = self.page_spec(options)
        original = self.created_page_receipt(stu.PAGE_COPY_COMMAND)
        self.queue.submit.return_value = original
        self.assertEqual(stu.exit_status(self.execute(stu.PAGE_COPY_COMMAND, spec=spec)), 0)
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        invalid = ({'source_page_id': 3}, {'source_page_name': '同 ID 其它源'},
                   {'new_page_id': 2}, {'new_page_name': '自动替换了新页'}, {'page_count': 6},
                   {'copy_mode': 'other'}, {'top_level_control_count': False})
        for mismatch in invalid:
            with self.subTest(mismatch=mismatch):
                native = dict(original, **mismatch)
                self.queue.submit.return_value = native
                failure = self.execute(stu.PAGE_COPY_COMMAND, spec=spec)
                self.assertEqual(failure['mismatches'], ['created_page'])
                self.assertEqual(failure['native_receipt'], native)
                self.assertFalse(failure['automatic_retry'])

    def test_native_page_create_and_copy_reject_ambiguous_specs_before_submission(self):
        create = {'page_name': '新页', 'expected_page_count': 4}
        copy_page = dict(create, source_page_id=2, source_page_name='完整源页名')
        for operation, options in (
                (stu.PAGE_CREATE_COMMAND, dict(create, expected_page_count=True)),
                (stu.PAGE_CREATE_COMMAND, dict(create, page_name='')),
                (stu.PAGE_CREATE_COMMAND, dict(create, width=1024)),
                (stu.PAGE_COPY_COMMAND, create),
                (stu.PAGE_COPY_COMMAND, dict(copy_page, source_page_id=-1)),
                (stu.PAGE_COPY_COMMAND, dict(copy_page, source_page_name=''))):
            with self.subTest(operation=operation, options=options):
                with self.assertRaises(ValueError):
                    self.execute(operation, spec=self.page_spec(options))
        self.queue.submit.assert_not_called()

    def test_native_page_creation_timeout_and_unsaved_results_are_not_repeated(self):
        spec = self.page_spec({'page_name': '原厂新页', 'expected_page_count': 4})
        request = {'request_id': 'stu-request', 'queue_request_sha256': 'd' * 64, 'automatic_retry': False}
        self.queue.submit.side_effect = QueueTimeout(request)
        initial = self.execute(stu.PAGE_CREATE_COMMAND, spec=spec)
        self.assertEqual(initial['transport_state'], request)
        native = self.created_page_receipt(stu.PAGE_CREATE_COMMAND)
        for flag in ('native_saved', 'page_save_verified', 'root_save_verified',
                     'post_save_page_readback_verified', 'original_active_view_preserved'):
            self.assertEqual(stu.exit_status(dict(native, **{flag: False})), 2)
        self.assertEqual(stu.exit_status(dict(native, completed_count=True)), 2)
        self.assertEqual(stu.exit_status(dict(native, native_page_save_called=None)), 2)
        self.assertEqual(stu.exit_status(dict(native, top_level_control_count=1)), 2)
        partial = dict(native, ok=False, native_saved=False, page_save_verified=False, root_save_verified=False,
                       native_result_may_be_partial=True)
        self.queue.read_existing_result.return_value = {'ok': True, 'status': 'correlated_response_observed',
                                                        'result': partial}
        seen = self.execute('request-result', request_sha256='d' * 64)
        self.assertEqual(seen['result'], partial)
        self.assertEqual(stu.exit_status(seen), 1)
        self.queue.submit.assert_called_once()
        self.queue.read_existing_result.assert_called_once_with('stu-request', 'd' * 64)

    def test_page_properties_read_reports_logical_dimensions_and_the_full_color_word(self):
        display = {'page_id': 21, 'page': '公共窗口_主页', 'width': 1024, 'height': 600,
                   'background_color_bgr': 0xff123456}
        native = self.receipt(stu.PAGE_PROPERTIES_READ_COMMAND, page_properties=display)
        self.queue.submit.return_value = native
        result = self.execute(stu.PAGE_PROPERTIES_READ_COMMAND, page_id=21, page='公共窗口_主页')
        self.assertEqual(result, native)
        self.assertEqual(stu.exit_status(result), 0)
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], {'page_id': 21, 'page': '公共窗口_主页'})
        self.assertEqual(self.execute(stu.PAGE_PROPERTIES_READ_COMMAND, page_id=20, page='公共窗口_主页')['mismatches'],
                         ['page_properties'])

    def test_page_background_edit_checks_exact_color_active_view_and_each_save(self):
        options = {'page_id': 21, 'page': '公共窗口_主页', 'before': {'background_color_bgr': 3223857},
                   'after': {'background_color_bgr': 0xf2eee7}}
        spec = self.page_spec(options)
        view = {'page_id': 21, 'page': '公共窗口_主页', 'exact_page_is_active': True}
        before = {'page_id': 21, 'page': '公共窗口_主页', 'width': 1024, 'height': 600, **options['before']}
        native = self.receipt(stu.PAGE_BACKGROUND_EDIT_COMMAND, status='applied_and_saved',
            read_only=False, write_attempted=True, page_view=view, before=before,
            page_properties={**before, **options['after']}, completed_count=1,
            view_refresh_verified=True, page_save_verified=True, root_save_verified=True)
        self.queue.submit.return_value = native
        result = self.execute(stu.PAGE_BACKGROUND_EDIT_COMMAND, spec=spec)
        self.queue.submit.assert_called_once()
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        self.assertEqual(stu.exit_status(result), 0)
        for flag in ('view_refresh_verified', 'page_save_verified', 'root_save_verified'):
            self.assertEqual(stu.exit_status(dict(result, **{flag: False})), 2)
        self.assertEqual(stu.exit_status(dict(result, page_view=dict(view, exact_page_is_active=False))), 2)
        changed = dict(native, page_properties=dict(native['page_properties'], width=1025))
        self.queue.submit.return_value = changed
        rejection = self.execute(stu.PAGE_BACKGROUND_EDIT_COMMAND, spec=spec)
        self.assertEqual(rejection['mismatches'], ['page_background'])
        self.assertEqual(rejection['native_receipt'], changed)
        self.assertFalse(rejection['automatic_retry'])

    def test_page_background_no_change_stays_read_only_and_nonordinary_colors_are_rejected(self):
        options = {'page_id': 21, 'page': '公共窗口_主页', 'before': {'background_color_bgr': 3223857},
                   'after': {'background_color_bgr': 3223857}}
        display = {'page_id': 21, 'page': '公共窗口_主页', 'width': 1024, 'height': 600, **options['before']}
        self.queue.submit.return_value = self.receipt(stu.PAGE_BACKGROUND_EDIT_COMMAND, status='no_changes',
            write_attempted=False, before=display, page_properties=display, completed_count=0,
            view_refresh_verified=False, page_save_verified=False, root_save_verified=False)
        self.assertEqual(stu.exit_status(self.execute(stu.PAGE_BACKGROUND_EDIT_COMMAND, spec=self.page_spec(options))), 0)
        for after in ({'background_color_bgr': True}, {'background_color_bgr': 0x101ffff}, {'width': 2048}):
            with self.subTest(after=after), self.assertRaises(ValueError):
                self.execute(stu.PAGE_BACKGROUND_EDIT_COMMAND, spec=self.page_spec(dict(options, after=after)))
        self.queue.submit.assert_called_once()

    def data_selector(self):
        return {'name': '十进制输入右上', 'native_id': 16, 'native_type': 2}

    def data_record(self, **fields):
        return {**self.data_selector(), 'index': 11, 'comment': '', 'unit': '', 'initial_text': '30', **fields}

    def test_data_catalog_default_and_filtered_options_share_the_bound_queue(self):
        result = self.receipt(stu.DATA_CATALOG_COMMAND, records=[self.data_record()], data_count=28)
        self.queue.submit.return_value = result
        self.assertEqual(self.execute(stu.DATA_CATALOG_COMMAND), result)
        self.assertNotIn('options', self.queue.submit.call_args.args[0])
        options = {'name': '十进制', 'offset': 0, 'limit': 20}
        self.assertEqual(self.execute(stu.DATA_CATALOG_COMMAND, spec=self.page_spec(options)), result)
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)

    def test_data_read_rejects_wrong_native_id_and_matches_exact_type(self):
        spec = self.page_spec(self.data_selector())
        self.queue.submit.return_value = self.receipt(stu.DATA_READ_COMMAND, record=self.data_record(native_id=17))
        self.assertEqual(self.execute(stu.DATA_READ_COMMAND, spec=spec)['mismatches'], ['variable_record'])
        self.queue.submit.return_value = self.receipt(stu.DATA_READ_COMMAND, record=self.data_record())
        self.assertEqual(stu.exit_status(self.execute(stu.DATA_READ_COMMAND, spec=spec)), 0)

    def test_data_batch_updates_only_requested_metadata_with_one_save_per_scope(self):
        options = {**self.data_selector(), 'before': {'comment': '', 'unit': ''},
                   'after': {'comment': '输入测试备注', 'unit': 's'}}
        spec = self.page_spec(options)
        native = self.receipt(stu.DATA_EDIT_COMMAND, status='applied_and_saved', read_only=False,
                              write_attempted=True, data_module_saved=True, project_saved=True,
                              unselected_native_records_verified=True,
                              modified_fields=['unit', 'comment'], record=self.data_record(**options['after']))
        self.queue.submit.return_value = native
        result = self.execute(stu.DATA_EDIT_COMMAND, spec=spec)
        self.queue.submit.assert_called_once()
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        self.assertEqual(result['record']['initial_text'], '30')
        self.assertEqual(stu.exit_status(result), 0)
        self.assertEqual(stu.exit_status(dict(result, project_saved=False)), 2)
        self.assertEqual(stu.exit_status(dict(result, unselected_native_records_verified=False)), 2)
        self.queue.submit.return_value = dict(native, modified_fields=['comment'])
        mismatch = self.execute(stu.DATA_EDIT_COMMAND, spec=spec)
        self.assertEqual(mismatch['mismatches'], ['variable_record'])
        self.assertEqual(mismatch['native_receipt']['modified_fields'], ['comment'])
        self.assertFalse(mismatch['automatic_retry'])

    def test_data_edit_no_change_and_unsupported_fields_are_distinct(self):
        options = {**self.data_selector(), 'before': {'comment': ''}, 'after': {'comment': ''}}
        spec = self.page_spec(options)
        self.queue.submit.return_value = self.receipt(stu.DATA_EDIT_COMMAND, status='no_changes',
            write_attempted=False, data_module_saved=False, project_saved=False, modified_fields=[],
            record=self.data_record())
        result = self.execute(stu.DATA_EDIT_COMMAND, spec=spec)
        self.assertEqual(stu.exit_status(result), 0)
        self.assertEqual(stu.exit_status(dict(result, data_module_saved=True)), 2)
        for invalid in (dict(options, native_type=-1), dict(options, native_id=True),
                        dict(options, after={'unit': ''}),
                        dict(options, before={'initial_text': '30'}, after={'initial_text': '31'})):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.execute(stu.DATA_EDIT_COMMAND, spec=self.page_spec(invalid))
        self.queue.submit.assert_called_once()

    def test_recipe_catalog_summary_and_exact_read_paging(self):
        summary = {'group_name': 'AuditStuMemo', 'row_count': 2, 'column_count': 2}
        catalog = self.receipt(stu.RECIPE_CATALOG_COMMAND, recipe_count=1, recipes=[summary])
        self.queue.submit.return_value = catalog
        self.assertEqual(stu.exit_status(self.execute(stu.RECIPE_CATALOG_COMMAND)), 0)
        self.assertNotIn('options', self.queue.submit.call_args.args[0])
        self.assertEqual(stu.exit_status(dict(catalog, recipe_count=2)), 2)
        record = {**summary, 'columns': [{'index': 0, 'variable_name': '', 'caption': '配方名称', 'native_kind': 3},
                                         {'index': 1, 'variable_name': '字符型输入', 'caption': '备注', 'native_kind': 3}],
                  'rows': [['审计行', '原值']], 'row_offset': 1}
        options = {'group_name': 'AuditStuMemo', 'offset': 1, 'limit': 1}
        spec = self.page_spec(options)
        self.queue.submit.return_value = self.receipt(stu.RECIPE_READ_COMMAND, record=record)
        self.assertEqual(stu.exit_status(self.execute(stu.RECIPE_READ_COMMAND, spec=spec)), 0)
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        self.queue.submit.return_value = self.receipt(stu.RECIPE_READ_COMMAND, record=dict(record, row_offset=0))
        self.assertEqual(self.execute(stu.RECIPE_READ_COMMAND, spec=spec)['mismatches'], ['recipe_record'])

    def recipe_cell_receipt(self, options, **overrides):
        changed = options['expected'] != options['after']
        body = {key: value for key, value in options.items() if key != 'after'}
        body.update(value=options['after'], changed=changed, native_named_recipe_readback=True,
                    other_target_recipe_bytes_preserved=True, recipe_save_verified=changed,
                    root_save_verified=changed, project_saved=changed, read_only=not changed,
                    write_attempted=changed, native_result_may_be_partial=False,
                    status='applied_and_saved' if changed else 'no_changes')
        return self.receipt(stu.RECIPE_CELL_COMMAND, **(body | overrides))

    def test_recipe_cell_edit_checks_exact_target_readback_and_separate_saves(self):
        options = {'group_name': 'AuditStuMemo', 'row_index': 0, 'column_index': 1, 'expected': '原值', 'after': '验收值'}
        spec = self.page_spec(options)
        native = self.recipe_cell_receipt(options)
        self.queue.submit.return_value = native
        result = self.execute(stu.RECIPE_CELL_COMMAND, spec=spec)
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        self.queue.submit.assert_called_once()
        self.assertEqual(stu.exit_status(result), 0)
        for flag in ('recipe_save_verified', 'root_save_verified', 'project_saved',
                     'native_named_recipe_readback', 'other_target_recipe_bytes_preserved'):
            self.assertEqual(stu.exit_status(dict(result, **{flag: False})), 2)
        for mismatch in ({'group_name': 'Other'}, {'column_index': 0}, {'value': '别的值'}, {'expected': '不是原值'}):
            self.queue.submit.return_value = dict(native, **mismatch)
            rejected = self.execute(stu.RECIPE_CELL_COMMAND, spec=spec)
            self.assertEqual(rejected['mismatches'], ['recipe_cell'])
            self.assertEqual(rejected['native_receipt'], dict(native, **mismatch))
            self.assertFalse(rejected['automatic_retry'])

    def test_recipe_cell_no_change_requires_readback_and_reports_no_saves(self):
        options = {'group_name': 'AuditStuMemo', 'row_index': 0, 'column_index': 1, 'expected': '', 'after': ''}
        self.queue.submit.return_value = self.recipe_cell_receipt(options)
        result = self.execute(stu.RECIPE_CELL_COMMAND, spec=self.page_spec(options))
        self.queue.submit.assert_called_once()
        self.assertEqual(stu.exit_status(result), 0)
        self.assertFalse(result['changed'])
        self.assertEqual(stu.exit_status(dict(result, root_save_verified=True)), 2)
        self.assertEqual(stu.exit_status(dict(result, native_named_recipe_readback=False)), 2)

    def test_recipe_rejects_unknown_shapes_before_submitting_and_keeps_unknown_outcome(self):
        valid = {'group_name': 'AuditStuMemo', 'row_index': 0, 'column_index': 1, 'expected': '原值', 'after': '验收值'}
        for invalid in (dict(valid, row_index=True), dict(valid, column_index=-1), dict(valid, after=123),
                        dict(valid, group_name=''), dict(valid, expected={'value': '原值'})):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.execute(stu.RECIPE_CELL_COMMAND, spec=self.page_spec(invalid))
        with self.assertRaises(ValueError):
            self.execute(stu.RECIPE_READ_COMMAND, spec=self.page_spec({'group_name': 'AuditStuMemo', 'limit': 0}))
        self.queue.submit.assert_not_called()
        state = {'request_id': 'stu-request', 'queue_request_sha256': 'd' * 64, 'automatic_retry': False}
        self.queue.submit.side_effect = QueueTimeout(state)
        self.assertEqual(self.execute(stu.RECIPE_CELL_COMMAND, spec=self.page_spec(valid))['transport_state'], state)
        partial = self.recipe_cell_receipt(valid, ok=False, project_saved=False, native_result_may_be_partial=True)
        self.queue.read_existing_result.return_value = {'ok': True, 'status': 'correlated_response_observed',
                                                        'result': partial}
        seen = self.execute('request-result', request_sha256='d' * 64)
        self.assertEqual(seen['result'], partial)
        self.assertEqual(stu.exit_status(seen), 1)
        self.queue.submit.assert_called_once()
        self.queue.read_existing_result.assert_called_once_with('stu-request', 'd' * 64)

    def strategy_receipt(self, operation, source, **overrides):
        summary = {'block_id': 3, 'block_name': '公共窗口按钮恢复', 'block_comment': '',
                   'row_count': 1, 'changed': False}
        digest = hashlib.sha256(source.encode('utf-16-le')).hexdigest()
        base = {'strategy': summary, 'row_index': 0, 'source': source, 'source_sha256_utf16le': digest}
        if operation == stu.STRATEGY_EDIT_COMMAND:
            base.update(source_before_sha256_utf16le='e' * 64, source_after=source,
                        source_after_sha256_utf16le=digest, source_requested_sha256_utf16le=digest,
                        source_normalization='exact', read_only=False, write_attempted=True,
                        status='applied_and_saved', native_script_compile_passed=True, native_strategy_compiled=True,
                        native_strategy_saved=True, root_save_verified=True, native_saved=True,
                        native_project_compile_required=True, unselected_strategy_nodes_verified=True,
                        original_project_compile_state_before=1, original_project_compile_state_after=1)
        return self.receipt(operation, **(base | overrides))

    def test_strategy_catalog_and_read_return_exact_selector_and_utf16le_source(self):
        source = '状态监控=0\r\n参数设置=0'
        read = self.strategy_receipt(stu.STRATEGY_READ_COMMAND, source)
        self.queue.submit.return_value = self.receipt(stu.STRATEGY_CATALOG_COMMAND, strategy_count=1,
                                                     strategies=[read['strategy']])
        self.assertEqual(stu.exit_status(self.execute(stu.STRATEGY_CATALOG_COMMAND)), 0)
        self.assertNotIn('options', self.queue.submit.call_args.args[0])
        options = {'block_id': 3, 'block_name': '公共窗口按钮恢复', 'row_index': 0}
        spec = self.page_spec(options)
        self.queue.submit.return_value = read
        self.assertEqual(stu.exit_status(self.execute(stu.STRATEGY_READ_COMMAND, spec=spec)), 0)
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        self.queue.submit.return_value = dict(read, source_sha256_utf16le='f' * 64)
        self.assertEqual(self.execute(stu.STRATEGY_READ_COMMAND, spec=spec)['mismatches'], ['strategy_source'])

    def test_strategy_edit_needs_exact_original_source_and_separate_native_results(self):
        source = "状态监控=0\r\n' Stu 原厂策略验收"
        options = {'block_id': 3, 'block_name': '公共窗口按钮恢复', 'row_index': 0,
                   'expected_source_sha256_utf16le': 'e' * 64, 'source': source}
        spec = self.page_spec(options)
        successful = self.strategy_receipt(stu.STRATEGY_EDIT_COMMAND, source)
        self.queue.submit.return_value = successful
        result = self.execute(stu.STRATEGY_EDIT_COMMAND, spec=spec)
        self.assertEqual(stu.exit_status(result), 0)
        self.queue.submit.assert_called_once()
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        for flag in ('native_script_compile_passed', 'native_strategy_compiled', 'native_strategy_saved',
                     'root_save_verified', 'native_saved', 'native_project_compile_required',
                     'unselected_strategy_nodes_verified'):
            self.assertEqual(stu.exit_status(dict(result, **{flag: False})), 2)
        self.queue.submit.return_value = self.strategy_receipt(stu.STRATEGY_EDIT_COMMAND, source + '\r\n')
        mismatch = self.execute(stu.STRATEGY_EDIT_COMMAND, spec=spec)
        self.assertEqual(mismatch['mismatches'], ['strategy_source'])
        self.assertEqual(mismatch['native_receipt']['source'], source + '\r\n')
        self.assertFalse(mismatch['automatic_retry'])

    def test_strategy_accepts_only_the_original_right_trim_projection(self):
        stored = '状态监控=0'
        requested = stored + '\r\n \t'
        before = hashlib.sha256(stored.encode('utf-16-le')).hexdigest()
        request_hash = hashlib.sha256(requested.encode('utf-16-le')).hexdigest()
        option = {'block_id': 3, 'block_name': '公共窗口按钮恢复', 'row_index': 0,
                  'expected_source_sha256_utf16le': before, 'source': requested}
        projected = self.strategy_receipt(stu.STRATEGY_EDIT_COMMAND, stored,
            source_before_sha256_utf16le=before, source_requested_sha256_utf16le=request_hash,
            source_normalization='native_trim_right', status='no_changes', read_only=True, write_attempted=False,
            native_script_compile_passed=False, native_strategy_compiled=False, native_strategy_saved=False,
            root_save_verified=False, native_saved=False, native_project_compile_required=False)
        self.queue.submit.return_value = projected
        self.assertEqual(stu.exit_status(self.execute(stu.STRATEGY_EDIT_COMMAND, spec=self.page_spec(option))), 0)
        bad = dict(option, source=' ' + stored + '\t')
        altered = dict(projected, source_requested_sha256_utf16le=hashlib.sha256(bad['source'].encode('utf-16-le')).hexdigest())
        self.queue.submit.return_value = altered
        self.assertEqual(self.execute(stu.STRATEGY_EDIT_COMMAND, spec=self.page_spec(bad))['mismatches'], ['strategy_source'])

    def test_strategy_unchanged_source_keeps_compile_and_save_flags_false(self):
        source = '状态监控=0'
        digest = hashlib.sha256(source.encode('utf-16-le')).hexdigest()
        options = {'block_id': 3, 'block_name': '公共窗口按钮恢复', 'row_index': 0,
                   'expected_source_sha256_utf16le': digest, 'source': source}
        self.queue.submit.return_value = self.strategy_receipt(stu.STRATEGY_EDIT_COMMAND, source,
            source_before_sha256_utf16le=digest, status='no_changes', read_only=True, write_attempted=False,
            native_script_compile_passed=False, native_strategy_compiled=False, native_strategy_saved=False,
            root_save_verified=False, native_saved=False, native_project_compile_required=False)
        result = self.execute(stu.STRATEGY_EDIT_COMMAND, spec=self.page_spec(options))
        self.assertEqual(stu.exit_status(result), 0)
        self.assertEqual(stu.exit_status(dict(result, native_strategy_compiled=True)), 2)
        self.assertEqual(stu.exit_status(dict(result, read_only=None)), 2)

    def test_strategy_source_edit_revalidates_input_and_preserves_unknown_queue_result(self):
        options = {'block_id': 3, 'block_name': '公共窗口按钮恢复', 'row_index': 0,
                   'expected_source_sha256_utf16le': 'e' * 64, 'source': '状态监控=0'}
        for invalid in (dict(options, row_index=True), dict(options, block_name=''),
                        dict(options, expected_source_sha256_utf16le='wrong'), dict(options, source='\0')):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.execute(stu.STRATEGY_EDIT_COMMAND, spec=self.page_spec(invalid))
        self.queue.submit.assert_not_called()
        state = {'request_id': 'stu-request', 'queue_request_sha256': 'd' * 64, 'automatic_retry': False}
        self.queue.submit.side_effect = QueueTimeout(state)
        unknown = self.execute(stu.STRATEGY_EDIT_COMMAND, spec=self.page_spec(options))
        self.assertEqual(unknown['transport_state'], state)
        partial = self.strategy_receipt(stu.STRATEGY_EDIT_COMMAND, options['source'], ok=False,
                                        native_saved=False, native_result_may_be_partial=True)
        self.queue.read_existing_result.return_value = {'ok': True, 'status': 'correlated_response_observed',
                                                        'result': partial}
        result = self.execute('request-result', request_sha256='d' * 64)
        self.assertEqual(result['result'], partial)
        self.assertEqual(stu.exit_status(result), 1)
        self.queue.submit.assert_called_once()
        self.queue.read_existing_result.assert_called_once_with('stu-request', 'd' * 64)

    def test_visibility_edit_matches_the_exact_existing_animation_and_owner_flag(self):
        selector = {'page_id': 21, 'page': '公共窗口_主页', 'top_level_path': [1],
                    'control_name': '标签', 'native_type_id': 0x5008, 'animation_index': 0}
        options = dict(selector, expected_expression='1', expected_mode=0, mode=1)
        page = {key: selector[key] for key in ('page_id', 'page')}
        record = {key: value for key, value in selector.items() if key not in page}
        record.update(native_class='CAniVisible', expression='1', mode=1)
        native = self.receipt(
            stu.VISIBILITY_EDIT_COMMAND, **page, record=record, changed=True, before_mode=0,
            before_owner_flags=4, applied_owner_flags=5, status='applied_and_saved',
            page_view=dict(page, exact_page_is_active=True), read_only=False, write_attempted=True,
            native_result_may_be_partial=False, completed_count=1, view_refresh_verified=True,
            page_save_verified=True, root_save_verified=True,
        )
        self.queue.submit.return_value = native
        spec = self.page_spec(options)
        result = self.execute(stu.VISIBILITY_EDIT_COMMAND, spec=spec)
        self.assertEqual(stu.exit_status(result), 0)
        self.assertEqual(self.queue.submit.call_args.args[0]['options'], options)
        self.assertEqual(stu.exit_status(dict(result, applied_owner_flags=1)), 2)
        self.assertEqual(stu.exit_status(dict(result, page_view=dict(page, exact_page_is_active=False))), 2)
        self.queue.submit.return_value = dict(native, record=dict(record, animation_index=1))
        self.assertEqual(self.execute(stu.VISIBILITY_EDIT_COMMAND, spec=spec)['mismatches'], ['visibility'])

    def test_visibility_can_observe_an_unknown_mode_but_cannot_write_it(self):
        page = {'page_id': 21, 'page': '公共窗口_主页'}
        record = {'top_level_path': [1], 'control_name': '标签', 'native_type_id': 0x5008, 'animation_index': 0}
        self.queue.submit.return_value = self.receipt(
            stu.VISIBILITY_READ_COMMAND, **page, record=dict(record, native_class='CAniVisible', expression='1', mode=17),
        )
        self.assertEqual(stu.exit_status(self.execute(stu.VISIBILITY_READ_COMMAND, spec=self.page_spec({**page, **record}))), 0)
        invalid = {**page, **record, 'expected_expression': '1', 'expected_mode': 17, 'mode': 0}
        with self.assertRaisesRegex(ValueError, 'modes of 0 or 1'):
            self.execute(stu.VISIBILITY_EDIT_COMMAND, spec=self.page_spec(invalid))
        self.queue.submit.assert_called_once()

    def test_rejects_unexposed_edits_and_wrong_family_files(self):
        with self.assertRaisesRegex(ValueError, 'does not expose'):
            self.execute('write-label')
        other_product = self.project.with_suffix('.MCP')
        other_product.touch()
        with self.assertRaisesRegex(ValueError, r'Stu \.MCS'):
            self.execute('inspect', project=other_product)
        self.queue.submit.assert_not_called()

    def test_rejects_positive_reply_for_another_process_or_project(self):
        self.queue.submit.return_value = self.receipt('inspect', process_id=19, project_path=str(self.root / 'Other.MCS'))
        result = self.execute('inspect')
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'native_receipt_identity_mismatch')
        self.assertEqual(set(result['mismatches']), {'process_id', 'project_path'})
        self.assertEqual(result['queue_request_sha256'], 'd' * 64)
        self.assertFalse(result['automatic_retry'])
        self.queue.submit.assert_called_once()

    def test_timeout_is_returned_verbatim_and_result_read_does_not_submit(self):
        state = {'request_id': 'stu-request', 'queue_request_sha256': 'd' * 64, 'automatic_retry': False}
        self.queue.submit.side_effect = QueueTimeout(state)
        result = self.execute('page-catalog')
        self.assertEqual(result['transport_state'], state)
        self.assertFalse(result['automatic_retry'])
        self.queue.submit.assert_called_once()
        self.project.unlink()
        receipt = self.receipt('page-catalog')
        self.queue.read_existing_result.return_value = {'ok': True, 'status': 'correlated_response_observed', 'result': receipt}
        result = self.execute('request-result', request_sha256='d' * 64)
        self.assertEqual(result['result'], receipt)
        self.queue.read_existing_result.assert_called_once_with('stu-request', 'd' * 64)
        self.queue.submit.assert_called_once()

    def test_compile_exit_status_reports_actual_native_check(self):
        self.queue.submit.return_value = self.receipt('compile', native_compile_verified=True, errors=1, read_only=False)
        issue = self.execute('compile')
        self.assertTrue(issue['ok'])
        self.assertEqual(stu.exit_status(issue), 2)
        self.assertEqual(stu.exit_status(dict(issue, errors=0)), 0)


if __name__ == '__main__':
    unittest.main()
