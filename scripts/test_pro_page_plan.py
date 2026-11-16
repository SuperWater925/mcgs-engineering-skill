"""Page designer fixtures. These do not launch or mutate Pro."""
import copy
import unittest

import pro_page_plan

from page_plan import compile_design, normalize_receipts
from page_readback_report import render_review

PROJECT = 'D:/sample/Evidence.mcp'


def control(index, name, rectangle, complete=None, native_id=None, class_name='CDrawRect'):
    return {'path': [index], 'class': class_name, 'name': name, 'rectangle': rectangle,
            'complete': complete or f'0x{10 + index:08x}', 'owner_document': '0x00000001',
            'native_id': native_id if native_id is not None else index + 11, 'children': [],
            'rtti': f'.?AV{class_name}@@'}


def capture(forest):
    page = {'page_id': 3, 'page_name': 'Title', 'page_iobject': '0x10000000', 'document': '0x00000001',
            'attributes': [0, 0, 200, 140]}
    return {'ok': True, 'op': 'engineering-edit-inspect', 'inspection_completed': True, 'write_attempted': False,
            'actual_project': PROJECT, 'process_id': 11, 'creation_filetime': 23, 'native_thread_id': 17,
            'editor_image_sha256': 'e' * 64,
            'compiled_kinds': ['page-view-open', 'control-geometry', 'control-properties', 'control-native-create',
                               'control-template-clone', 'control-layer', 'page-flush', 'root-flush'],
            'action_preimages': [
                {'kind': 'control-geometry-batch', 'before': {'page': page, 'forest': forest}},
                {'kind': 'control-native-create',
                 'before': {'target_page': page, 'target_forest': forest, 'class': 'CDrawRect'}},
                {'kind': 'button-actions-batch', 'target': {}, 'before': {
                    'page': page, 'control': forest[0], 'phases': [{'phase': 0, 'texts': ['Navigate']}]}}
            ]}


class PagePlanTests(unittest.TestCase):
    def setUp(self):
        self.source = control(0, '<source>', [1, 1, 21, 21], class_name='CDrawButton')
        self.original = normalize_receipts([capture([self.source])])
        self.design = {
            'schema': 'mcgs-page-design/v1', 'project_path': PROJECT, 'save': True,
            'pages': [{'id': 3, 'name': 'Title', 'resolution': [200, 140], 'layers': [
                {'id': 'background', 'placement': 'back', 'controls': [
                    {'id': 'backdrop', 'class': 'CDrawRect', 'rectangle': [0, 0, 198, 139]}]},
                {'id': 'main', 'controls': [
                    {'id': 'source', 'existing': {'path': [0], 'name': '<source>', 'class': 'CDrawButton'},
                     'rectangle': [2, 2, 22, 22]},
                    {'id': 'cards', 'depends_on': ['source'],
                     'array': {'source': 'source', 'rows': 2, 'columns': 2, 'row_gap': -2,
                               'column_gap': 7, 'origin': [50, 50]}}
                ]}
            ]}]
        }

    def test_edit_order_batches_array_cells_and_save_boundary(self):
        program, review = compile_design(self.design, self.original)
        actions = program['steps'][0]['specification']['actions']
        kinds = [row['kind'] for row in actions]
        self.assertEqual(kinds, ['page-view-open', 'control-geometry', 'control-native-create'] +
                         ['control-template-clone'] * 4 + ['control-layer'])
        clone = actions[3]
        self.assertEqual(clone['source']['complete'], self.source['complete'])
        self.assertNotIn('control_path', clone['source'])
        self.assertEqual(actions[6]['after']['rectangle'], [77, 68, 97, 88])
        self.assertEqual(actions[-1]['target']['controls'][0]['complete']['$native_result']['path'],
                         '/apply/created/complete')
        self.assertEqual([row['kind'] for row in program['steps'][1]['specification']['actions']],
                         ['page-flush', 'root-flush'])
        self.assertEqual(review['pages'][0]['controls'][1]['bindings']['button_phases'][0]['texts'], ['Navigate'])

    def test_prototype_uses_receipt_identity_in_source(self):
        main = self.design['pages'][0]['layers'][1]['controls']
        main[1]['array']['source'] = 'backdrop'
        main[1]['array'].update(rows=1, columns=1, origin=[0, 0])
        program, review = compile_design(self.design, self.original)
        actions = program['steps'][0]['specification']['actions']
        clone = next(item for item in actions if item['kind'] == 'control-template-clone')
        self.assertEqual(clone['source']['native_id']['$native_result']['path'], '/apply/created/native_id')
        self.assertTrue(review['pages'][0]['controls'][-1]['overlaps_source'])

    def test_rejects_same_name_wrong_path_and_off_page(self):
        design = copy.deepcopy(self.design)
        design['project_path'] = 'D:/elsewhere/Evidence.mcp'
        with self.assertRaisesRegex(ValueError, 'project path'):
            compile_design(design, self.original)
        design['project_path'] = PROJECT
        design['pages'][0]['layers'][1]['controls'][1]['array']['origin'] = [198, 5]
        with self.assertRaisesRegex(ValueError, 'outside|invalid'):
            compile_design(design, self.original)

    def test_report_marks_unread_bindings_and_viewport_clipping(self):
        program, review = compile_design(self.design, self.original)
        action = next(action for action in program['steps'][0]['specification']['actions']
                      if action['kind'] == 'control-template-clone')
        clone = control(1, 'Native clone', [50, 50, 70, 70], class_name='CDrawButton')
        changed = {**self.source, 'rectangle': [2, 2, 22, 22]}
        observed = normalize_receipts([capture([changed, clone])])
        observed['pages'][0]['viewport'] = {'visible_page_rect': [0, 0, 55, 140]}
        receipt = {'actual_project': PROJECT, 'direct_inspection': {
            key: self.original[key] for key in ('process_id', 'creation_filetime', 'native_thread_id', 'editor_image_sha256')
        }, 'direct_action_results': [
            {'action_id': action['action_id'], 'result': {'ok': True, 'actions': [{'apply': {'resulting_control': clone}}]}}
        ]}
        html = render_review(review, observed, [receipt])
        self.assertIn('几何 一致', html)
        self.assertIn('绑定 未读到', html)
        self.assertIn('有裁切', html)
        self.assertIn('正常关闭重开 · 未验证', html)
        self.assertNotIn('<source>', html)

    def test_reopen_matches_persistent_identity_explicitly(self):
        _, review = compile_design(self.design, self.original)
        observed = copy.deepcopy(self.original)
        observed['pages'][0]['document'] = '0x00000002'
        observed['pages'][0]['forest'][0].update(complete='0x40000000', owner_document='0x00000002')
        evidence = {'reopen': {'actual_project': PROJECT, 'source': 'native lifecycle receipt',
                               'normal_project_closed_then_reopened_verified': True,
                               'open_confirmed_same_project': True}}
        self.assertIn('重开后唯一原生 ID', render_review(review, observed, evidence=evidence))
        self.assertIn('身份匹配 未读到', render_review(review, observed))


if __name__ == '__main__':
    unittest.main()
