import unittest
from unittest.mock import Mock, patch
from native_check_result import capture, list_items, parse_dialog


DIALOG = dict(hwnd=123, owner=90, visible=True, class_name='#32770', text='提示')
SUMMARY = '组态检查通过！发现错误：0个，警告：0个'


def static(text, **extra):
    return dict(dict(hwnd=124, parent=123, class_name='Static', visible=True, control_id=9,
                     text=text), **extra)


class DialogChecks(unittest.TestCase):
    def test_provider_error_survives_summary_capture(self):
        api = Mock(pid=17)
        api.check.return_value = 124
        failure = Mock(returncode=1, stderr=b'AccessibleChildren HRESULT 0x80004005')
        with patch('native_check_result.subprocess.run', return_value=failure), \
                patch('native_check_result.subprocess.CREATE_NO_WINDOW', 0, create=True):
            evidence = list_items(api, {'hwnd': 124}, 'pwsh')
        result = parse_dialog(DIALOG, [static(SUMMARY), static('', class_name='SysListView32', **evidence)])
        self.assertTrue(result['counts_observed'])
        detail = result['detail_controls_unread'][0]
        self.assertEqual(detail['reason'], 'accessibility_helper_failed')
        self.assertEqual(detail['provider_failure']['stderr'], failure.stderr.decode())
        self.assertEqual(detail['provider_failure']['exit_code'], 1)

    def test_observed_counts_preserve_exact_rows(self):
        items = [{'type': 'ControlType.DataItem', 'text': '窗口1   第3行', 'runtime_id': [42, 9]}]
        result = parse_dialog(DIALOG, [static(SUMMARY), static('', hwnd=125, class_name='SysListView32', items=items)])
        self.assertTrue(result['check_passed'])
        self.assertEqual((result['error_count'], result['warning_count']), (0, 0))
        self.assertEqual(result['observed_rows'][1]['text'], items[0]['text'])
        self.assertEqual(result['observed_rows'][1]['runtime_id'], [42, 9])

    def test_incomplete_or_inconsistent_counts(self):
        for rows in ([static('组态检查通过！')], [static(SUMMARY, visible=False)],
                     [static('组态检查通过！发现错误：1个，警告：0个')],
                     [static(SUMMARY), static('组态检查未通过！发现错误：1个，警告：0个')],
                     [static('组态检查通过！发现错误：-1个，警告：0个')]):
            result = parse_dialog(DIALOG, rows)
            self.assertFalse(result['counts_observed'])
            self.assertIsNone(result['error_count'])
        result = parse_dialog(DIALOG, [static('组态检查未通过！发现错误：2个，警告：3个')])
        self.assertFalse(result['check_passed'])
        self.assertEqual((result['error_count'], result['warning_count']), (2, 3))

    def test_ownership_and_ambiguity(self):
        class API:
            identity = {'pid': 111, 'creation_filetime': 12, 'executable': 'fixture'}
            def __init__(self):
                self.tops = [dict(hwnd=90, class_name='MDI', visible=True), DIALOG, dict(DIALOG, hwnd=80, owner=12)]
            def top_windows(self):
                return self.tops
            def check(self, hwnd):
                return hwnd
            def children(self, hwnd):
                return [static(SUMMARY, parent=hwnd)]
            def snapshot(self, hwnd):
                return next(row for row in self.tops if row['hwnd'] == hwnd)
        api = API()
        result = capture(api, 90)
        self.assertEqual(result['status'], 'observed')
        self.assertEqual([r['dialog']['hwnd'] for r in result['results']], [123])
        api.tops.append(dict(DIALOG, hwnd=126))
        self.assertEqual(capture(api, 90)['status'], 'result_unconfirmed')
        self.assertEqual(capture(api, 90, 123)['status'], 'observed')


    def test_separate_details_are_stable_and_scoped_to_the_selected_window(self):
        main = dict(hwnd=90, class_name='MDI', visible=True)
        details = dict(DIALOG, hwnd=126, text='组态检查列表(双击打开修改)')
        listing = static('', hwnd=127, parent=126, class_name='SysListView32')
        class API:
            identity = {'pid': 111, 'creation_filetime': 12}
            def top_windows(self):
                return [main, DIALOG, details]
            def children(self, hwnd):
                return [listing.copy()] if hwnd == 126 else [static(SUMMARY)]
            def snapshot(self, hwnd):
                return {123: DIALOG, 126: details, 127: listing}[hwnd]
            def check(self, hwnd):
                return hwnd
        api = API()
        item = {'items': [{'text': '一行', 'provider': 'MSAA', 'accessible_path': [1]}]}
        with patch('native_check_result.list_items', return_value=item):
            result = capture(api, 90, details_hwnd=126, detail_control_hwnd=127)
            self.assertEqual(result['status'], 'observed')
            self.assertEqual(result['selected_details']['items'], item['items'])
            self.assertFalse(result['selected_details']['same_check_operation_verified'])
            self.assertEqual(result['results'][1]['observed_rows'][0]['accessible_path'], [1])
        with patch('native_check_result.list_items', side_effect=[item, {'items': []}]):
            result = capture(api, 90, 123, details_hwnd=126, detail_control_hwnd=127)
            self.assertEqual(result['selected_details']['detail_read_error'], 'details_changed_during_capture')
        details['owner'] = 12
        with self.assertRaisesRegex(ValueError, 'ownership chain'):
            capture(api, 90, 123, details_hwnd=126, detail_control_hwnd=127)


if __name__ == '__main__':
    unittest.main()
