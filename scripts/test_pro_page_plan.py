"""Page designer fixtures. These do not launch or mutate Pro."""
import copy
from contextlib import redirect_stdout
from hashlib import sha256
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pro_page_plan

from page_group_plan import COORDINATES, DESIGN as GROUP_DESIGN, FLATTEN_CELLS, compile_groups, inspect_groups, report_groups
from page_plan import compile_design, compile_page_setup, normalize_receipts, require_native_length
from page_readback_report import compare_animations, render_review
from project_plan import DESIGN as PROJECT_DESIGN, compile_project, json_bytes, report_readback, session_program

PROJECT = 'D:/sample/Evidence.mcp'
PAGE_LINKER = 'MCGS.User windows.Title'


def control(index, name, rectangle, complete=None, native_id=None, class_name='CDrawRect'):
    return {'path': [index], 'class': class_name, 'name': name, 'rectangle': rectangle,
            'complete': complete or f'0x{10 + index:08x}', 'owner_document': '0x00000001',
            'native_id': native_id if native_id is not None else index + 11, 'children': [],
            'rtti': f'.?AV{class_name}@@',
            'clone_eligibility': {'eligible': class_name != 'CDrawActiveX',
                                  'reason': 'fixture operation ABI evidence'}}


def capture(forest):
    page = {'page_id': 3, 'page_name': 'Title', 'page_iobject': '0x10000000', 'document': '0x00000001',
            'attributes': [0, 0, 200, 140]}
    return {'ok': True, 'op': 'engineering-edit-inspect', 'inspection_completed': True, 'write_attempted': False,
            'actual_project': PROJECT, 'process_id': 11, 'creation_filetime': 23, 'native_thread_id': 17,
            'editor_image_sha256': 'e' * 64, 'project_sha256': 'f' * 64, 'root': '0x10001000',
            'features': ['plan-design-preflight/v1', 'strict-control-selector/v1',
                         'clone-target-eligibility/v1', 'clone-source-native-result/v1',
                         'geometry-batch-identity/v1'],
            'compiled_kinds': ['page-view-open', 'control-geometry', 'control-properties', 'control-native-create',
                               'control-template-clone', 'control-layer', 'page-flush', 'root-flush',
                               'control-geometry-batch', 'control-properties-batch'],
            'action_preimages': [
                {'kind': 'control-geometry-batch', 'before': {'page': page, 'forest': forest}},
                {'kind': 'control-native-create',
                 'before': {'target_page': page, 'target_forest': forest, 'class': 'CDrawRect',
                            'clone_eligibility': {'eligible': True, 'reason': 'fixture factory ABI verified'}}},
                {'kind': 'button-actions-batch', 'target': {}, 'before': {
                    'page': page, 'control': forest[0], 'phases': [{'phase': 0, 'texts': ['Navigate']}]}}
            ]}


class GroupPlanTests(unittest.TestCase):
    def setUp(self):
        first = control(0, 'Box', [10, 10, 50, 50])
        second = control(1, 'Line', [90, 70, 70, 110], class_name='CDrawLine')
        first['type_id'], second['type_id'] = 0x5004, 0x5005
        self.original = [first, second]
        self.design = {'schema': GROUP_DESIGN, 'project_path': PROJECT, 'page': {'id': 3, 'name': 'Title'},
                       'operation': 'group', 'controls': [{key: row[key] for key in ('path', 'name', 'class')}
                                                          for row in reversed(self.original)]}

    def original_receipt(self, action, roots):
        receipt = capture(self.original)
        page = receipt['action_preimages'][0]['before']['page']
        page.update(view='0x00000002', pages=[{'id': 3, 'name': 'Title'}])
        rows = [row for root in roots for row in [root, *root['children']]]
        before = {'page': page, 'page_linker': PAGE_LINKER, 'forest': roots, 'group_preimage_sha256': '1' * 64,
                  'coordinate_roles': [{'complete': row['complete'], 'model': {
                      'CDrawRect': 'bounding-rectangle', 'CDrawLine': 'directed-line',
                      'CDrawCell': 'native-cell-container'}[row['class']]} for row in rows],
                  'control_properties': [{'complete': row['complete'], 'properties': []} for row in rows],
                  'control_linkers': [{'complete': row['complete'], 'linker': PAGE_LINKER + '.' + row['name']}
                                      for row in rows],
                  'reference_graph': {'edges': [], 'edge_count': 0, 'complete_registered_native_graph': True,
                                      'bidirectional_edges_consistent': True}}
        receipt['action_preimages'] = [{**action, 'before': before}]
        receipt['features'].append(COORDINATES)
        receipt['compiled_kinds'].extend(('control-group', 'control-ungroup'))
        receipt['all_requested_features_available'] = True
        return receipt

    def planned(self):
        action, = inspect_groups(self.design)['actions']
        receipt = self.original_receipt(action, self.original)
        program, inspection, review = compile_groups(self.design, receipt)
        return program, inspection, review

    def grouped_roots(self):
        group = control(0, 'Cell', [10, 10, 90, 110], complete='0x00000020', class_name='CDrawCell')
        group['type_id'] = 0x5039
        group['children'] = [{**old, 'path': [0, index], 'rectangle': rect} for index, (old, rect) in enumerate(
            zip(self.original, ([0, 0, 5000, 4000], [10000, 6000, 7500, 10000])))]
        return [group]

    def test_group_preserves_page_scoped_linkers_and_reversed_line_endpoints(self):
        program, inspection, review = self.planned()
        spec = program['steps'][0]['specification']
        activate, group = spec['actions']
        self.assertEqual(activate['kind'], 'page-view-open')
        self.assertIn(COORDINATES, spec['required_features'])
        self.assertEqual([row['control_path'] for row in group['target']['controls']], [[0], [1]])
        self.assertEqual(group['after']['surviving_controls'][1]['rectangle'], [10000, 6000, 7500, 10000])
        later = self.original_receipt(inspection['actions'][0], self.grouped_roots())
        self.assertTrue(report_groups(review, later)['business_readback_passed'])
        later['action_preimages'][0]['before']['control_linkers'][1]['linker'] = PAGE_LINKER + '.Cell.Box'
        self.assertEqual([row['field'] for row in report_groups(review, later)['differences']], ['linker'])

    def test_ungroup_against_exact_native_page_and_independent_graph(self):
        roots = self.grouped_roots()
        self.design.update(operation='ungroup', controls=[{'path': [0], 'class': 'CDrawCell', 'name': 'Cell'}],
                           save=True)
        action, = inspect_groups(self.design)['actions']
        program, inspection, review = compile_groups(self.design, self.original_receipt(action, roots))
        self.assertEqual([step['step_id'] for step in program['steps']], ['group-edit', 'group-save'])
        recovered = self.original_receipt(inspection['actions'][0], self.original)
        self.assertTrue(report_groups(review, recovered)['business_readback_passed'])
        recovered['action_preimages'][0]['before']['page']['view'] = '0x00000009'
        self.assertEqual([row['field'] for row in report_groups(review, recovered)['differences']], ['page_identity'])
        recovered['action_preimages'][0]['before']['reference_graph']['bidirectional_edges_consistent'] = False
        with self.assertRaisesRegex(ValueError, 'bidirectional'):
            report_groups(review, recovered)

    def test_group_flattens_only_explicit_static_cells_and_recomputes_world_bounds(self):
        cell, = self.grouped_roots()
        cell['children'][0]['rectangle'] = [1250, 1000, 5000, 4000]
        extra = control(1, 'Far box', [110, 120, 170, 160], complete='0x00000022')
        extra['type_id'] = 0x5004
        self.design['controls'] = [{key: row[key] for key in ('path', 'name', 'class')} for row in (extra, cell)]
        action, = inspect_groups(self.design)['actions']
        current = self.original_receipt(action, [cell, extra])
        current['features'].append(FLATTEN_CELLS)
        with self.assertRaisesRegex(ValueError, 'explicit flatten_selected_cells'):
            compile_groups(self.design, current)
        self.design['flatten_selected_cells'] = True
        program, _, review = compile_groups(self.design, current)
        spec = program['steps'][0]['specification']
        self.assertIn(FLATTEN_CELLS, spec['required_features'])
        group = spec['actions'][1]
        self.assertTrue(group['after']['flatten_selected_cells'])
        self.assertEqual(group['after']['group_rectangle'], [20, 20, 170, 160])
        self.assertEqual([row['name'] for row in group['after']['surviving_controls']], ['Box', 'Line', 'Far box'])
        self.assertEqual(group['after']['surviving_controls'][0]['rectangle'], [0, 0, 2000, 2143])
        self.assertEqual([row['name'] for row in review['expected_forest'][0]['children']], ['Box', 'Line', 'Far box'])
        graph = current['action_preimages'][0]['before']['reference_graph']
        graph.update(edge_count=1, edges=[{'source': PAGE_LINKER + '.Cell', 'target': 'MCGS.Resource'}])
        with self.assertRaisesRegex(ValueError, 'old group.*registered reference'):
            compile_groups(self.design, current)


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

    def test_history_editor_respects_transitive_geometry_dependency(self):
        sample = capture([self.source, control(1, 'A', [30, 30, 40, 40]), control(2, 'N', [50, 50, 60, 60])])
        snapshot = normalize_receipts([sample])
        snapshot['compiled_kinds'].append('button-actions-batch')
        snapshot['pages'][0]['forest'][0]['button_phases'][0]['enabled_raw_uint32'] = [0]
        design = self.simple_design([{'id': 'A', 'existing': [1], 'rectangle': [31, 31, 41, 41]},
                                     {'id': 'N', 'existing': [2], 'depends_on': ['A']},
                                     {'id': 'B', 'existing': [0], 'depends_on': ['N'], 'button_changes': [
                                         {'phase': 0, 'action_index': 0, 'enabled': True, 'text': 'Navigate'}]}])
        _, review = compile_design(design, snapshot)
        self.assertEqual([action['kind'] for action in review['actions']],
                         ['page-view-open', 'control-geometry', 'button-actions-batch'])

    def test_cache_requires_exact_observed_transition_and_evidence(self):
        before = {'class': 'CAniVisible', 'strings': {'2c': '1'}, 'byte_arrays_hex': {'14': ''},
                  'words_uint32': {'8': 12299, 'c': 1065353216, '30': 0}, 'arrays': {}, 'enabled_raw_byte': 10}
        after = {**before, 'byte_arrays_hex': {'14': '03000000000000000100000003000000000000001101000000472c0000000001'}}
        self.assertIn('业务一致', compare_animations([before], [after], True))
        self.assertEqual(compare_animations([before], [after], False), '有差异')
        self.assertEqual(compare_animations([before], [{**after, 'other': 1}], True), '有差异')
        self.assertEqual(compare_animations([before], [{**after, 'byte_arrays_hex': {'14': '00'*32}}], True), '有差异')

    def test_blink_compile_projection_keeps_all_style_words(self):
        source = {'class': 'CAniBlink', 'enabled_raw_byte': 10, 'strings': {'2c': '1'}, 'arrays': {},
                  'byte_arrays_hex': {'14': ''}, 'words_uint32': {
                      '8': 12289, 'c': 1065353216, '30': 0, '34': 13033312, '38': 8026746,
                      '3c': 0, '40': 0, '44': 0, '48': 0, '4c': 0, '50': 16777215}}
        saved = {**source, 'byte_arrays_hex': {'14': '03000000000000000100000003000000000000001101000000472c0000000001'}}
        self.assertIn('业务一致', compare_animations([source], [saved], True))
        self.assertEqual(compare_animations([source], [saved], False), '有差异')
        changed = {**saved, 'words_uint32': dict(saved['words_uint32'], **{'40': 1})}
        self.assertEqual(compare_animations([source], [changed], True), '有差异')
        zero = {**source, 'strings': {'2c': '0'}}
        zero_saved = {**zero, 'byte_arrays_hex': {'14': '03000000000000000100000003000000000000001100000000472c0000000001'}}
        self.assertIn('业务一致', compare_animations([zero], [zero_saved], True))
        self.assertEqual(compare_animations([zero], [{**zero_saved, 'byte_arrays_hex': saved['byte_arrays_hex']}], True),
                         '有差异')

    def test_palette_compiler_cache_matches_current_variable_id(self):
        source = {'class': 'CAniBrush', 'enabled_raw_byte': 10, 'strings': {'2c': '显示标识1'},
                  'byte_arrays_hex': {'14': ''}, 'words_uint32': {'8': 1, 'c': 0},
                  'arrays': {'30': [0, 1065353216], '44': [0, 255]}}
        saved = {**source, 'byte_arrays_hex': {'14': '0300000000000000010000000300000000000000261d0000002c0000000001'}}
        self.assertIn('已核验的 31 字节', compare_animations([source], [saved], True, {'显示标识1': {'id': 29, 'kind': 1}}))
        self.assertEqual(compare_animations([source], [saved], True, {'显示标识1': {'id': 1, 'kind': 1}}), '有差异')
        self.assertEqual(compare_animations([source], [saved], True), '有差异')

    def test_ambiguous_reopen_deletion_is_unknown(self):
        _, review = compile_design(self.simple_design([{'id': 'S', 'existing': [0]}]), self.original)
        review['pages'][0]['removed'] = [self.source]
        observed = copy.deepcopy(self.original)
        forest = observed['pages'][0]['forest']
        forest.append({**forest[0], 'path': [1], 'complete': '0x70000002'})
        html = render_review(review, observed, evidence={'reopen': self.reopen_evidence(review, observed)})
        self.assertIn('删除 [0] 未读到', html)

    def test_followup_binds_created_control_to_fresh_capture(self):
        _, review = compile_design(self.design, self.original)
        action = next(item['id'] for item in review['actions'] if item['kind'] == 'control-native-create')
        observed = copy.deepcopy(self.original)
        created = control(1, 'created', [0, 0, 198, 139])
        observed['pages'][0]['forest'].append(created)
        props = [{'native_key': 'A', 'native_type_tag': 8, 'value': 'new'}]
        created['style'] = [{**props[0], 'value': 'old'}]
        created['input_variable'] = 'old'
        observed['variables'] = ['new']
        request = {'review_id': review['review_id'], 'updates': [
            {'id': 'newbinding', 'result_action': action, 'binding_updates': [{**props[0], 'variable': 'new'}]}]}
        receipt = {'actual_project': PROJECT, 'direct_inspection': {
            key: observed[key] for key in ('process_id', 'creation_filetime', 'native_thread_id', 'editor_image_sha256', 'root')
        }, 'direct_action_results': [{'action_id': action, 'result': {'ok': True, 'actions': [
            {'apply': {'created': created}}]}}]}
        inspection = pro_page_plan.followup_inspection(request, review, observed, [receipt])
        self.assertEqual(inspection['actions'][0]['target']['complete'], created['complete'])
        self.assertEqual(inspection['actions'][0]['after']['properties'], props)
        self.assertNotIn('data-catalog', observed['compiled_kinds'])
        self.assertEqual(inspection['actions'][1]['kind'], 'data-catalog')
        design = pro_page_plan.followup_design(request, review, observed, [receipt])
        _, second = compile_design(design, observed)
        self.assertIsNone(second['pages'][0]['controls'][0]['bindings'])
        self.assertEqual(second['pages'][0]['controls'][0]['details']['binding_properties'], props)
        with self.assertRaisesRegex(ValueError, 'Missing successful'):
            pro_page_plan.followup_design(request, review, observed, [])

    def test_new_primitive_and_new_prototype_defer_their_own_business_edits(self):
        event = {'definition_id': 3, 'text70': 'x = 1'}
        binding = {'native_key': 'A', 'native_type_tag': 8, 'value': 'new', 'variable': 'new'}
        design = self.simple_design([
            {'id': 'prototype', 'class': 'CDrawRect', 'rectangle': [1, 1, 21, 21], 'events': [event]},
            {'id': 'copies', 'depends_on': ['prototype'],
             'array': {'source': 'prototype', 'rows': 1, 'columns': 1, 'column_gap': 0,
                                       'row_gap': 0, 'origin': [40, 40], 'overrides': [
                                           {'cell': [1, 1], 'binding_updates': [binding]}]}}])
        self.original['compiled_kinds'].append('control-event-list')
        first, review = compile_design(design, self.original)
        self.assertEqual([action['kind'] for action in first['steps'][0]['specification']['actions']],
                         ['page-view-open', 'control-native-create', 'control-template-clone'])
        controls = review['pages'][0]['controls']
        self.assertEqual(review['deferred_updates'], [
            {'id': 'followup_control_1', 'result_action': controls[0]['result_action'], 'events': [event]},
            {'id': 'followup_control_2', 'result_action': controls[1]['result_action'],
             'depends_on': ['followup_control_1'], 'binding_updates': [binding]}])
        self.assertIn('绑定 另见第二阶段回读', render_review(review))

    def test_typed_binding_checks_native_text_against_captured_variable(self):
        typed = {'native_key': '输入框连接变量', 'native_type_tag': 6, 'value': {'text': 'New', 'number': 1}}
        current = self.original['pages'][0]['forest'][0]
        current['style'] = [{**typed, 'value': {'text': 'Old', 'number': 1}}]
        self.original['variables'] = ['New']
        self.original['variable_native_types'] = {'New': 1}
        edit = {**typed, 'variable': 'New'}
        design = self.simple_design([{'id': 'current', 'existing': [0], 'binding_updates': [edit]}])
        program, review = compile_design(design, self.original)
        self.assertEqual(program['steps'][0]['specification']['actions'][-1]['after']['properties'], [typed])
        self.assertEqual(review['pages'][0]['controls'][0]['details']['binding_properties'], [typed])
        edit['variable'] = 'Old'
        with self.assertRaisesRegex(ValueError, 'binding variable'):
            compile_design(design, self.original)
        edit['variable'] = 'New'
        edit['value'] = {'text': 'New', 'number': 2}
        with self.assertRaisesRegex(ValueError, 'Binding native type'):
            compile_design(design, self.original)

    def test_typed_business_batch_uses_native_target_fields(self):
        new = control(1, 'other', [30, 30, 60, 90])
        snapshot = normalize_receipts([capture([self.source, new])])
        first, second = snapshot['pages'][0]['forest']
        prop = {'native_key': 'text', 'native_type_tag': 8, 'value': 'new'}
        alignment = {'native_key': 'align', 'native_type_tag': 5, 'value': 'left'}
        component_path = [{'native_key': 'raised', 'occurrence': 0}]
        first['style'] = [{**prop, 'value': 'old'}]
        second['components'] = [{'path': component_path, 'style': [{**alignment, 'value': 'middle'}]}]
        design = self.simple_design([
            {'id': 'bound', 'existing': [0], 'binding_updates': [prop]},
            {'id': 'aligned', 'existing': [1], 'component_updates': [
                {'path': component_path, 'properties': [alignment]}]}])
        program, _ = compile_design(design, snapshot)
        batch = program['steps'][0]['specification']['actions'][-1]
        self.assertEqual(batch['kind'], 'control-properties-batch')
        targets = [item['target'] for item in batch['after']['controls']]
        self.assertEqual(targets, [
            {'control_name': first['name'], 'rtti': first['rtti'], 'control_path': [0],
             'complete': first['complete'], 'native_id': first['native_id']},
            {'control_name': second['name'], 'rtti': second['rtti'], 'control_path': [1],
             'complete': second['complete'], 'native_id': second['native_id'], 'component_path': component_path}])

    def test_standard_button_alignment_requires_both_basic_states(self):
        current = self.original['pages'][0]['forest'][0]
        paths = [[{'native_key': key, 'occurrence': 0}] for key in ('抬起状态', '按下状态')]
        prop = {'native_key': '水平对齐', 'native_type_tag': 5, 'value': '靠左'}
        current['components'] = [{'path': path, 'style': [{**prop, 'value': '居中'}]} for path in paths]
        updates = [{'path': paths[0], 'properties': [prop]}]
        design = self.simple_design([{'id': 'current', 'existing': [0], 'component_updates': updates}])
        with self.assertRaisesRegex(ValueError, 'alignment is shared'):
            compile_design(design, self.original)
        updates.append({'path': paths[1], 'properties': [prop]})
        _, review = compile_design(design, self.original)
        self.assertEqual(review['pages'][0]['controls'][0]['details']['components'], updates)

    def test_array_deferred_edits_inspect_new_objects_not_the_prototype(self):
        event = {'definition_id': 3, 'text70': 'x = 1'}
        animation = {'add': 'CAniVisible', 'visibility': {'expression': '1'}}
        array = {'source': 'prototype', 'rows': 1, 'columns': 2, 'column_gap': 5, 'row_gap': 0,
                 'origin': [40, 40], 'overrides': [{'cell': [1, 1], 'events': [event]},
                                                   {'cell': [1, 2], 'animations': [animation]}]}
        design = self.simple_design([{'id': 'prototype', 'class': 'CDrawRect', 'rectangle': [1, 1, 21, 21]},
                                     {'id': 'cards', 'array': array}])
        with self.assertRaisesRegex(ValueError, 'lacks compiled action kinds'):
            compile_design(design, self.original)
        kinds = ['control-event-list', 'control-animation-list']
        self.original['compiled_kinds'].extend(kinds)
        first, review = compile_design(design, self.original)
        action_kinds = [action['kind'] for action in first['steps'][0]['specification']['actions']]
        self.assertEqual(action_kinds, ['page-view-open', 'control-native-create',
                                        'control-template-clone', 'control-template-clone'])
        updates = review['deferred_updates']
        self.assertEqual([u['result_action'] for u in updates],
                         [cell['result_action'] for cell in review['pages'][0]['controls'][1:]])
        self.assertEqual(updates[0]['events'], [event])
        self.assertEqual(updates[1]['animations'], [animation])
        first_report = render_review(review)
        self.assertIn('事件 另见第二阶段回读', first_report)
        self.assertIn('动画 另见第二阶段回读', first_report)

        a = control(2, 'first clone', [40, 40, 60, 60], native_id=-2)
        b = control(1, 'second clone', [65, 40, 85, 60], native_id=-2)
        fresh_receipt = capture([self.source, b, a])
        fresh_receipt['compiled_kinds'].extend(kinds)
        page = fresh_receipt['action_preimages'][0]['before']['page']
        page['attributes'] += [0] * 6
        snapshot = normalize_receipts([fresh_receipt])
        receipt = {'actual_project': PROJECT, 'direct_inspection': {
            key: snapshot[key] for key in ('process_id', 'creation_filetime', 'native_thread_id', 'editor_image_sha256', 'root')
        }, 'direct_action_results': [
            {'action_id': update['result_action'], 'result': {'ok': True, 'actions': [
                {'apply': {'resulting_control': {**cell, 'path': [receipt_index]}}}]}}
            for receipt_index, (update, cell) in enumerate(zip(updates, (a, b)), 1)]}
        request = {'review_id': review['review_id'], 'updates': updates}
        inspection = pro_page_plan.followup_inspection(request, review, snapshot, [receipt])
        self.assertFalse(inspection['commit'])
        actions = inspection['actions']
        self.assertEqual([x['kind'] for x in actions], kinds)
        self.assertEqual(actions[0]['after'], {'events': []})
        self.assertNotIn('after', actions[1])
        self.assertEqual([x['target']['complete'] for x in actions], [a['complete'], b['complete']])
        self.assertEqual([x['target']['control_path'] for x in actions], [[2], [1]])
        with self.assertRaisesRegex(ValueError, 'Inspect the original event declarations'):
            compile_design(pro_page_plan.followup_design(request, review, snapshot, [receipt]), snapshot)
        changed_root = copy.deepcopy(receipt)
        changed_root['direct_inspection']['root'] = '0x20001000'
        with self.assertRaisesRegex(ValueError, 'editor generation'):
            pro_page_plan.followup_inspection(request, review, snapshot, [changed_root])

        fresh_receipt['action_preimages'].extend([
            {'kind': 'control-event-list', 'before': {'target_page': {'page': page},
              'target_control': {**a, 'events': [],
                                 'native_definitions': [{'native_event_id': 3, 'native_name': 'Event',
                                     'argument_descriptors_raw_uint16': [], 'raw_word_10': 3}]}}},
            {'kind': 'control-animation-list', 'before': {'page': page, 'target_control': b, 'items': []}},
        ])
        snapshot = normalize_receipts([fresh_receipt])
        second_design = pro_page_plan.followup_design(request, review, snapshot, [receipt])
        second, _ = compile_design(second_design, snapshot)
        edits = second['steps'][0]['specification']['actions']
        self.assertEqual([x['kind'] for x in edits], ['page-view-open', *kinds])
        self.assertEqual(edits[1]['after']['events'][0]['text70'], 'x = 1')
        self.assertEqual(edits[2]['after']['items'][0]['expected_record']['strings']['2c'], '1')

    def test_prototype_uses_receipt_identity_in_source(self):
        main = self.design['pages'][0]['layers'][1]['controls']
        main[1]['array']['source'] = 'backdrop'
        main[1]['array'].update(rows=1, columns=1, origin=[0, 0])
        program, review = compile_design(self.design, self.original)
        actions = program['steps'][0]['specification']['actions']
        clone = next(item for item in actions if item['kind'] == 'control-template-clone')
        self.assertEqual(clone['source']['native_id']['$native_result']['path'], '/apply/created/native_id')
        self.assertTrue(review['pages'][0]['controls'][-1]['overlaps_source'])

    def test_native_length_does_not_reject_former_eight_mib_limit(self):
        require_native_length({'actions': [{'text': '汉' * (3 * 1024 * 1024)}]})

    def test_page_setup_sizes_the_id_returned_by_creation(self):
        self.original['compiled_kinds'] += ['page-create', 'page-size']
        self.original['page_operations']['page-create'] = {'pages': [{'id': 3, 'name': 'Title'}]}
        setup = {'schema': 'mcgs-page-setup/v1', 'project_path': PROJECT,
                 'operations': [{'operation': 'create', 'name': 'New', 'resolution': [512, 400]}]}
        actions = compile_page_setup(setup, self.original)['steps'][0]['specification']['actions']
        self.assertEqual([action['kind'] for action in actions], ['page-create', 'page-size'])
        self.assertEqual(actions[1]['target']['page_id']['$native_result'],
                         {'action_id': actions[0]['action_id'], 'path': '/apply/target_page_after/page_id'})

    def test_control_order_and_remove_use_current_identity_not_old_indexes(self):
        another = control(1, 'Remove', [25, 25, 50, 50])
        snapshot = normalize_receipts([capture([self.source, another])])
        snapshot['compiled_kinds'].append('control-template-delete')
        design = self.simple_design([])
        identity = {key: another[key] for key in ('path', 'name', 'native_id', 'class', 'complete')}
        design['pages'][0].update(remove=[identity], control_order=[[0]])
        program, review = compile_design(design, snapshot)
        actions = program['steps'][0]['specification']['actions']
        self.assertEqual([action['kind'] for action in actions], ['page-view-open', 'control-template-delete'])
        self.assertNotIn('control_path', actions[1]['target'])
        self.assertEqual(review['pages'][0]['removed'], [identity])

    def test_order_uses_only_the_required_front_moves(self):
        second = control(1, 'Second', [25, 25, 50, 50])
        third = control(2, 'Third', [50, 50, 75, 75])
        snapshot = normalize_receipts([capture([self.source, second, third])])
        design = self.simple_design([])
        design['pages'][0]['control_order'] = [[0], [1], [2]]
        program, _ = compile_design(design, snapshot)
        self.assertEqual(program['steps'], [])
        design['pages'][0]['control_order'] = [[0], [2], [1]]
        program, _ = compile_design(design, snapshot)
        actions = program['steps'][0]['specification']['actions']
        self.assertEqual([action['kind'] for action in actions], ['page-view-open', 'control-layer'])
        self.assertEqual(actions[-1]['target']['controls'][0]['control_name'], 'Second')

    def test_array_override_writes_all_capture_validated_cell_values(self):
        def prop(name, value):
            return {'native_key': name, 'native_type_tag': 8, 'value': value}
        observed = self.original['pages'][0]['forest'][0]
        observed['style'] = [prop('A', 'old'), prop('B', 'same')]
        first = {'id': 'source', 'existing': [0], 'binding_updates': [prop('A', 'source changed')]}
        cell_values = [prop('A', 'old'), prop('B', 'cell changed')]
        array = {'source': 'source', 'rows': 1, 'columns': 1, 'row_gap': 0,
                 'column_gap': 0, 'origin': [50, 50],
                 'overrides': [{'cell': [1, 1], 'binding_updates': cell_values}]}
        design = self.simple_design([first, {'id': 'clone', 'array': array, 'depends_on': ['source']}])
        program, review = compile_design(design, self.original)
        actions = program['steps'][0]['specification']['actions']
        self.assertEqual(actions[-1]['after']['properties'], cell_values)
        self.assertIn('$native_result', actions[-1]['target']['complete'])

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
        evidence = {'reopen': self.reopen_evidence(review, observed)}
        self.assertIn('重开后唯一原生 ID', render_review(review, observed, evidence=evidence))
        self.assertIn('身份匹配 未读到', render_review(review, observed))


    @staticmethod
    def reopen_evidence(review, observed):
        return {'actual_project': PROJECT, 'source': 'native lifecycle receipt', 'ok': True,
                'process_id': review['process_id'], 'creation_filetime': review['creation_filetime'],
                'review_id': review['review_id'], 'normal_project_closed_then_reopened_verified': True,
                'open_confirmed_same_project': True,
                'state_before': {**{key: review[key] for key in ('process_id', 'creation_filetime', 'root')},
                                 'actual_project': PROJECT, 'project_sha256': 'c' * 64},
                'state_after': {**{key: observed[key] for key in ('process_id', 'creation_filetime', 'root')},
                                'actual_project': PROJECT, 'project_sha256': observed['project_sha256']},
                'project_sha256_after_summary': observed['project_sha256']}

    def simple_design(self, controls):
        return {'schema': 'mcgs-page-design/v1', 'project_path': PROJECT,
                'pages': [{'id': 3, 'name': 'Title', 'resolution': [200, 140],
                           'layers': [{'id': 'main', 'controls': controls}]}]}

    def test_design_preimage_is_bound_once_and_includes_clone_and_binding_assumptions(self):
        program, review = compile_design(self.design, self.original)
        spec = program['steps'][0]['specification']
        before = spec['design_preflight']
        self.assertEqual(before['root'], self.original['root'])
        self.assertEqual(before['project_sha256'], self.original['project_sha256'])
        self.assertEqual(before['pages'][0]['document'], self.original['pages'][0]['document'])
        self.assertEqual(before['pages'][0]['forest'][0]['complete'], self.source['complete'])
        self.assertEqual(before['clone_sources'][0]['native_id'], self.source['native_id'])
        self.assertEqual(before['button_preimages'][0]['phases'], self.original['pages'][0]['forest'][0]['button_phases'])
        self.assertNotIn('design_preflight', program['steps'][1]['specification'])
        self.assertEqual(review['root'], before['root'])

    def test_capture_rejects_file_or_contract_drift(self):
        first, second = capture([self.source]), capture([self.source])
        for key, value in (('root', '0x99999999'), ('project_sha256', 'a' * 64), ('features', [])):
            changed = copy.deepcopy(second)
            changed[key] = value
            with self.assertRaisesRegex(ValueError, 'preimage changed'):
                normalize_receipts([first, changed])

    def test_reopen_rejects_stale_instance_root_hash_and_other_review(self):
        _, review = compile_design(self.design, self.original)
        observed = copy.deepcopy(self.original)
        observed['pages'][0]['document'] = '0x00000002'
        observed['pages'][0]['forest'][0]['owner_document'] = '0x00000002'
        evidence = self.reopen_evidence(review, observed)
        changes = [('state_before', 'root', '0x99999999'), ('state_after', 'root', '0x99999999'),
                   ('state_after', 'process_id', 901), ('state_after', 'creation_filetime', 902),
                   (None, 'project_sha256_after_summary', 'a' * 64), (None, 'review_id', 'other-review'),
                   (None, 'process_id', 900)]
        for branch, key, value in changes:
            bad = copy.deepcopy(evidence)
            (bad[branch] if branch else bad)[key] = value
            html = render_review(review, observed, evidence={'reopen': bad})
            self.assertNotIn('正常关闭重开 · 证据满足', html)
            self.assertNotIn('重开后唯一原生 ID', html)

    def test_reordered_group_siblings_are_reported(self):
        parent = control(0, 'group', [0, 0, 100, 100], class_name='CDrawUnit')
        parent['children'] = [{**control(index + 10, str(index), [0, 0, 100, 100]), 'path': [0, index]}
                              for index in range(2)]
        before = normalize_receipts([capture([parent])])
        _, review = compile_design(self.simple_design([{'id': 'left', 'existing': [0, 0]},
                                                       {'id': 'right', 'existing': [0, 1]}]), before)
        observed = copy.deepcopy(before)
        children = observed['pages'][0]['forest'][0]['children']
        children.reverse()
        for index, child in enumerate(children):
            child['path'] = [0, index]
        html = render_review(review, observed)
        self.assertIn('原生层序 有差异', html)
        self.assertIn('各父控件子序 [0] 有差异', html)
        self.assertNotIn('已识别对象的几何与所属层一致', html)
        self.assertNotIn('层次 一致', html)

    def test_clone_eligibility_rejects_target_subtree_before_any_program(self):
        before = copy.deepcopy(self.original)
        before['pages'][0]['forest'][0]['clone_eligibility'] = {
            'eligible': False, 'reason': 'subtree external object has no verified lifecycle'}
        with self.assertRaisesRegex(ValueError, 'subtree external object'):
            compile_design(self.design, before)
        before = copy.deepcopy(self.original)
        before['factory_probes'][0]['clone_eligibility'] = {'eligible': False, 'reason': 'factory clone not available'}
        design = copy.deepcopy(self.design)
        design['pages'][0]['layers'][1]['controls'][1]['array']['source'] = 'backdrop'
        with self.assertRaisesRegex(ValueError, 'factory clone not available'):
            compile_design(design, before)

    def test_transitive_noop_dependency_cannot_cross_creation(self):
        a, b = control(0, 'a', [0, 0, 10, 10]), control(1, 'b', [20, 20, 30, 30])
        before = normalize_receipts([capture([a, b])])
        design = self.simple_design([{'id': 'new', 'class': 'CDrawRect', 'rectangle': [1, 1, 11, 11]},
                                    {'id': 'noop', 'existing': [0], 'depends_on': ['new']},
                                    {'id': 'edit', 'existing': [1], 'depends_on': ['noop'], 'rectangle': [22, 22, 32, 32]}])
        with self.assertRaisesRegex(ValueError, 'must precede additions'):
            compile_design(design, before)

    def test_independent_geometry_and_style_use_native_batches(self):
        a, b = control(0, 'a', [0, 0, 10, 10]), control(1, 'b', [20, 20, 30, 30])
        before = normalize_receipts([capture([a, b])])
        prop = {'native_key': 'Fill', 'native_type_tag': 0, 'value': 1}
        for row in before['pages'][0]['forest']:
            row['style'] = [prop]
        controls = [{'id': 'a', 'existing': [0], 'rectangle': [1, 1, 11, 11], 'style': [{**prop, 'value': 2}]},
                    {'id': 'b', 'existing': [1], 'rectangle': [21, 21, 31, 31], 'style': [{**prop, 'value': 2}]}]
        program, _ = compile_design(self.simple_design(controls), before)
        actions = program['steps'][0]['specification']['actions']
        self.assertEqual([action['kind'] for action in actions],
                         ['page-view-open', 'control-geometry-batch', 'control-properties-batch'])
        self.assertEqual(actions[1]['after']['controls'][1]['target']['complete'], b['complete'])
        self.assertEqual(len(program['steps'][0]['specification']['design_preflight']['style_preimages']), 2)
        controls[1]['depends_on'] = ['a']
        program, _ = compile_design(self.simple_design(controls), before)
        self.assertEqual([action['kind'] for action in program['steps'][0]['specification']['actions']],
                         ['page-view-open', 'control-geometry', 'control-properties', 'control-geometry', 'control-properties'])

    def test_group_and_child_edits_remain_sequential(self):
        parent = control(0, 'parent', [0, 0, 100, 100], class_name='CDrawUnit')
        parent['children'] = [{**control(10, 'child', [0, 0, 1000, 1000]), 'path': [0, 0]}]
        before = normalize_receipts([capture([parent])])
        controls = [{'id': 'parent', 'existing': [0], 'rectangle': [0, 0, 110, 110],
                     'transform_group_children': True},
                    {'id': 'child', 'existing': [0, 0], 'rectangle': [10, 10, 1010, 1010]}]
        program, _ = compile_design(self.simple_design(controls), before)
        spec = program['steps'][0]['specification']
        self.assertEqual([action['kind'] for action in spec['actions']],
                         ['page-view-open', 'control-geometry', 'control-geometry'])
        self.assertFalse(spec['coalesce_native_properties'])
        self.assertEqual([action['target']['complete'] for action in spec['actions'][1:]],
                         [parent['complete'], parent['children'][0]['complete']])

    def test_execution_checks_loaded_features_before_submitting_any_mutation(self):
        with patch('native_delivery_config.current', return_value=SimpleNamespace(
                task_root=Path.cwd(), runtime_root=Path.cwd(), working_root=Path.cwd())):
            import engineering_session as session
        program, _ = compile_design(self.design, self.original)
        capability = {'ok': True, 'features': [], 'compiled_kinds': self.original['compiled_kinds']}
        with tempfile.TemporaryDirectory(prefix='mcgs-plan-contract-') as directory, \
                patch.object(session.batch, 'TASK', Path(directory)), \
                patch.object(session.batch, 'RUNTIME', Path(directory)), \
                patch.object(session.batch, 'submit', return_value=capability) as read, \
                patch.object(session.batch, 'execute') as execute, redirect_stdout(io.StringIO()):
            result = session.run_direct_program(program, {'session_id': 'feature-fixture'}, Path(directory),
                                                1, prepare_workers=0)
        self.assertFalse(result['ok'])
        self.assertFalse(result['execution_may_be_partial'])
        self.assertEqual(result['phase'], 'inspect-feature-contracts')
        self.assertTrue(read.call_args.args[0]['capability_only'])
        execute.assert_not_called()
        # Ordinary direct programs have no new mandatory feature contract.
        self.assertEqual(session.required_features({'actions': []}), set())

    def test_pure_creation_does_not_require_unused_selector_contract(self):
        before = copy.deepcopy(self.original)
        before['features'].remove('strict-control-selector/v1')
        program, _ = compile_design(self.simple_design([
            {'id': 'new', 'class': 'CDrawRect', 'rectangle': [30, 30, 40, 40]}]), before)
        self.assertEqual(program['steps'][0]['specification']['required_features'], ['plan-design-preflight/v1'])

    def test_kind_names_do_not_replace_native_feature_contracts(self):
        for feature in ('plan-design-preflight/v1', 'strict-control-selector/v1', 'clone-target-eligibility/v1'):
            before = copy.deepcopy(self.original)
            before['features'].remove(feature)
            with self.assertRaisesRegex(ValueError, feature):
                compile_design(self.design, before)
        design = copy.deepcopy(self.design)
        design['pages'][0]['layers'][1]['controls'][1]['array']['source'] = 'backdrop'
        design['pages'][0]['layers'][1]['controls'][1]['array'].update(rows=1, columns=1, origin=[0, 0])
        before = copy.deepcopy(self.original)
        before['features'].remove('clone-source-native-result/v1')
        with self.assertRaisesRegex(ValueError, 'clone-source-native-result/v1'):
            compile_design(design, before)

    def test_vmove_projection_requires_new_engine_feature_even_with_animation_kind(self):
        target = control(0, 'Label', [1, 1, 21, 21], class_name='CDrawLabel')
        receipt = capture([target])
        receipt['compiled_kinds'].append('control-animation-list')
        page = receipt['action_preimages'][0]['before']['page']
        page['attributes'].extend([0] * 7)
        animation = {'class':'CAniVMove','enabled_raw_byte':10,
                     'words_uint32':{'8':12293,'c':1,'30':0,'34':0,'38':0,'3c':0,'40':461},
                     'strings':{'2c':''},'arrays':{},'byte_arrays_hex':{'14':''}}
        receipt['action_preimages'].append({'kind':'control-animation-list','before':{
            'page':page,'target_control':target,'items':[animation]}})
        design = self.simple_design([{'id':'label','existing':[0],
            'animations':[{'update':0,'fields':{'expression':'循环加'}}]}])
        feature = 'animation-vmove-serialize-projection/v1'
        with self.assertRaisesRegex(ValueError, feature):
            compile_design(design, normalize_receipts([receipt]))
        receipt['features'].append(feature)
        program, _ = compile_design(design, normalize_receipts([receipt]))
        spec = program['steps'][0]['specification']
        self.assertIn(feature, spec['required_features'])
        action = next(row for row in spec['actions'] if row['kind']=='control-animation-list')
        self.assertTrue(action['after']['items'][0]['restore_observed_vmove_clone'])


class ProjectReadbackTests(unittest.TestCase):
    def design(self):
        action = {'action_id': 'page-edit', 'kind': 'page-document-properties',
                  'target': {'page_id': 32, 'page_name': 'Caller'}, 'after': {'fields': {}}}
        return {'schema': PROJECT_DESIGN, 'project_path': PROJECT, 'sections': [
            {'domain': 'pages', 'program': session_program(PROJECT, [
                {'step_id': 'edit', 'specification': {'actions': [action]}}])}], 'checks': [
            {'id': 'catalog', 'domain': 'pages',
             'selector': {'kind': 'page-catalog-read', 'target': {}},
             'expected': [{'pointer': '/page/id', 'value': 32}]},
            {'id': 'properties', 'domain': 'pages',
             'selector': {'kind': 'page-document-properties', 'target': {'page_name': 'Caller',
                          'page_id': {'$ref': '/steps/catalog/inspect/action_preimages/0/before/page/id'}}},
             'expected': [{'pointer': '/comment', 'value': 'current'}]}]}

    def test_readback_resolves_an_earlier_verified_receipt(self):
        design = self.design()
        _, program, review = compile_project(design)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)

            def write(name, value):
                data = json_bytes(value)
                (directory / f'{name}.json').write_bytes(data)
                return sha256(data).hexdigest()

            write('manifest', {'purpose': program['purpose'], 'project_path': PROJECT,
                  'source_program_sha256': review['readback_sha256'], 'program_sha256': write('program', program),
                  'session_id': 'readback', 'engineering_delivery_scope_sha256': 'scope'})
            write('execution-result', {'ok': True, 'session_id': 'readback', 'execution_mode': 'direct',
                  'completed_steps': ['catalog', 'properties']})
            for index, (target, before) in enumerate((({}, {'page': {'id': 32}}),
                    ({'page_name': 'Caller', 'page_id': 32}, {'comment': 'current'}))):
                step = program['steps'][index]
                name = step['step_id']
                prefix = f'{index + 1:04d}-{name}'
                specification = copy.deepcopy(step['specification'])
                action = specification['actions'][0]
                action['target'] = target
                spec_sha = write(prefix + '-specification', specification)
                write(prefix + '-begin', {'step_id': name, 'specification_sha256': spec_sha})
                receipt = {'ok': True, 'op': 'engineering-edit-inspect', 'write_attempted': False,
                           'request_id': f'eng_readback_{index:04d}_read', 'actual_project': PROJECT,
                           'engineering_delivery_scope_sha256': 'scope',
                           'action_preimages': [dict(action, before=before)]}
                write(prefix + '-inspect', receipt)
                if index == 0:
                    catalog_receipt = receipt
            self.assertTrue(report_readback(review, directory)['business_readback_passed'])
            catalog_receipt['request_id'] = 'another-request'
            write('0001-catalog-inspect', catalog_receipt)
            report = report_readback(review, directory)
            self.assertFalse(report['business_readback_passed'])
            self.assertEqual([check['status'] for check in report['checks']], ['unverified', 'unverified'])

    def test_readback_rejects_forward_or_apply_references_at_design_time(self):
        design = self.design()
        design['checks'].reverse()
        with self.assertRaisesRegex(ValueError, 'earlier check receipt'):
            compile_project(design)
        design = self.design()
        reference = design['checks'][1]['selector']['target']['page_id']
        reference['$ref'] = reference['$ref'].replace('/inspect/', '/apply/')
        with self.assertRaisesRegex(ValueError, 'earlier check receipt'):
            compile_project(design)


if __name__ == '__main__':
    unittest.main()
