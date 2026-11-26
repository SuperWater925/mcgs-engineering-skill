"""Render a standalone design/native comparison from explicit evidence."""
from __future__ import annotations

from html import escape
import json

from page_plan import REVIEW, SNAPSHOT, forest_paths, native_bindings, path_key, require

UNKNOWN = '未读到'
DIFFERENCE = '有差异'
MATCH = '一致'


def applied_objects(receipts, planned):
    objects = {}
    for receipt in receipts:
        for action in receipt.get('direct_action_results', []):
            result = action['result']
            plan = planned.get(action['action_id'])
            if result.get('ok') is not True or not plan or plan['kind'] not in ('control-native-create', 'control-template-clone'):
                continue
            key = 'created' if plan['kind'] == 'control-native-create' else 'resulting_control'
            for item in result.get('actions', []):
                payload = item.get('apply') or {}
                if isinstance(payload.get(key), dict):
                    old = objects.setdefault(action['action_id'], payload[key])
                    require(old == payload[key], 'Conflicting native object receipts')
    return objects


def matching_controls(rows, identity, same_generation):
    if not identity:
        return None
    keys = ('native_id', 'name', 'class')
    if same_generation:
        keys += ('complete', 'owner_document')
    if not all(key in identity for key in keys) or any(not all(key in row for key in keys) for row in rows):
        return None
    return [row for row in rows if all(key in row and row[key] == identity[key] for key in keys)]


def match_control(rows, identity, same_generation):
    matching = matching_controls(rows, identity, same_generation)
    return matching[0] if matching and len(matching) == 1 else None


def compare(expected, actual):
    if expected is None or actual is None:
        return UNKNOWN
    return MATCH if expected == actual else DIFFERENCE


ANIMATION_WORDS = {
    'CAniBlink': frozenset('8 c 30 34 38 3c 40 44 48 4c 50'.split()),
    'CAniSize': frozenset('8 c 30 34 38 3c 40 44 48 4c'.split()),
    'CAniVMove': frozenset('8 c 30 34 38 3c 40'.split()),
    'CAniOutput': frozenset('8 c 40 44 48 4c 50 54 58 5c 60 68 6c 70'.split()),
    'CAniBrush': frozenset(('8', 'c')),
    'CAniTextColor': frozenset(('8', 'c')),
}
CACHE_PREFIX = '0300000000000000010000000300000000000000'
CACHE_END = '2c0000000001'
LITERAL_ONE = CACHE_PREFIX + '110100000047' + CACHE_END


def original_animation_cache(record, variable_catalog):
    """Resolve the compiler output of the observed complete animation shapes."""
    if set(record) != {'class', 'words_uint32', 'enabled_raw_byte', 'strings', 'arrays', 'byte_arrays_hex'}:
        return None
    if record['byte_arrays_hex'] != {'14': ''}:
        return None
    kind, words, strings, arrays = (record[k] for k in ('class', 'words_uint32', 'strings', 'arrays'))
    if not all(isinstance(value, dict) for value in (words, strings, arrays)):
        return None
    expression = strings.get('2c')
    if not isinstance(expression, str):
        return None
    if kind == 'CAniVisible':
        if (words == {'8': 12299, 'c': 1065353216, '30': 0} and strings == {'2c': '1'}
                and arrays == {} and record['enabled_raw_byte'] == 10):
            return LITERAL_ONE
        return None
    if not isinstance(kind, str) or kind not in ANIMATION_WORDS or words.keys() != ANIMATION_WORDS[kind]:
        return None
    if any(type(value) is not int or not 0 <= value <= 0xffffffff for value in words.values()):
        return None
    string_keys = {'2c', '34', '3c', '64'} if kind == 'CAniOutput' else {'2c'}
    if strings.keys() != string_keys or any(not isinstance(value, str) for value in strings.values()):
        return None
    if kind in ('CAniBrush', 'CAniTextColor'):
        if (arrays.keys() != {'30', '44'} or not all(isinstance(item, list) for item in arrays.values())
                or len(arrays['30']) != len(arrays['44'])):
            return None
    elif arrays:
        return None
    if kind == 'CAniBlink':
        if ((words['8'], words['c'], words['30']) != (12289, 1065353216, 0)
                or words['40'] not in (0, 1, 2) or words['44'] not in (0, 1) or record['enabled_raw_byte'] != 10):
            return None
        return {'0': CACHE_PREFIX + '110000000047' + CACHE_END, '1': LITERAL_ONE}.get(expression)
    if kind == 'CAniSize':
        return CACHE_PREFIX + '120000000000804640' + CACHE_END if expression == '45.000' else None
    if kind == 'CAniOutput' and expression == '1':
        return LITERAL_ONE

    variable = variable_catalog.get(expression) if isinstance(variable_catalog, dict) else None
    if not isinstance(variable, dict) or type(variable.get('kind')) is not int or variable['kind'] not in (1, 2):
        return None
    ident = variable.get('id')
    if type(ident) is not int or not 0 <= ident <= 0x7fffffff:
        return None
    return CACHE_PREFIX + '26' + ident.to_bytes(4, 'little').hex() + CACHE_END


def compare_animations(expected, actual, verified_compile_reopen, variable_catalog=None):
    state = compare(expected, actual)
    if (state != DIFFERENCE or not verified_compile_reopen or not isinstance(expected, list)
            or not isinstance(actual, list) or len(expected) != len(actual)):
        return state
    lengths = set()
    for before, after in zip(expected, actual):
        if before == after:
            continue
        if not isinstance(before, dict) or not isinstance(after, dict):
            return DIFFERENCE
        cache = original_animation_cache(before, variable_catalog)
        if cache is None or after != {**before, 'byte_arrays_hex': {'14': cache}}:
            return DIFFERENCE
        lengths.add(len(cache) // 2)
    sizes = '、'.join(str(length) for length in sorted(lengths))
    return f'业务一致（原厂编译缓存由空变为已核验的 {sizes} 字节）'


def selected_properties(actual, expected):
    if actual is None or 'style' not in actual or not expected:
        return None
    fields = {(item['native_key'], item['native_type_tag']): item for item in actual['style']}
    keys = [(item['native_key'], item['native_type_tag']) for item in expected]
    if not all(key in fields for key in keys):
        return None
    return [fields[key] for key in keys]


def clip_status(rectangle, bounds):
    if rectangle is None or bounds is None:
        return UNKNOWN
    return '超出边界' if any((rectangle[0] < bounds[0], rectangle[1] < bounds[1],
                             rectangle[2] > bounds[2], rectangle[3] > bounds[3])) else '在范围内'


def text(value):
    return escape(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))


def draw_board(size, controls, title):
    if size is None:
        return f'<figure><figcaption>{text(title)} · {UNKNOWN}</figcaption></figure>'
    width, height = size
    if width <= 0 or height <= 0:
        return f'<figure><figcaption>{text(title)} · {UNKNOWN}</figcaption></figure>'
    marks = []
    for name, rect in controls:
        if rect is None:
            continue
        left, top, right, bottom = rect
        style = f'left:{left / width:.5%};top:{top / height:.5%};width:{(right-left) / width:.5%};height:{(bottom-top) / height:.5%}'
        marks.append(f'<div class="mark" style="{style}" title="{text(name)} {text(rect)}">{text(name)}</div>')
    return (f'<figure><figcaption>{text(title)} · {width} × {height}</figcaption>'
            f'<div class="drawing" style="aspect-ratio:{width}/{height}">{"".join(marks)}</div></figure>')


def reopen_verified(row, review=None, snapshot=None):
    if not (review and snapshot and row.get('source') and row.get('review_id') == review.get('review_id')
            and review.get('review_id') and row.get('normal_project_closed_then_reopened_verified') is True
            and row.get('open_confirmed_same_project') is True and row.get('ok') is True):
        return False
    before, after = row.get('state_before') or {}, row.get('state_after') or {}
    for state, expected in ((before, review), (after, snapshot)):
        if not all(expected.get(key) is not None and state.get(key) == expected[key]
                   for key in ('process_id', 'creation_filetime', 'root')):
            return False
        project = expected.get('actual_project', expected.get('project_path'))
        if not state.get('actual_project') or path_key(state['actual_project']) != path_key(project):
            return False
    if not before.get('project_sha256') or not all(
            row.get(key) == before.get(key) == after.get(key) for key in ('process_id', 'creation_filetime')):
        return False
    digest = row.get('project_sha256_after_summary', after.get('project_sha256'))
    return bool(digest and snapshot.get('project_sha256') == digest)


def evidence_html(project, evidence, review=None, snapshot=None):
    observed = evidence or {}
    checks = [
        ('原厂保存', 'save', lambda row: row.get('native_save_return_verified') is True and row.get('root_modified') == 0
         and bool(row.get('sha256_after'))),
        ('文件回读', 'file', lambda row: row.get('independent_file_readback_verified') is True and bool(row.get('sha256'))),
        ('原生工程检查', 'check', lambda row: all(row.get(key) is True for key in (
            'native_check_passed', 'original_worker_call_entered', 'original_worker_returned'))
            and type(row.get('original_worker_return_int32')) is int and row['original_worker_return_int32'] == 0
            and row.get('state_after', {}).get('root_compile_valid_raw') == 1),
        ('正常关闭重开', 'reopen', lambda row: reopen_verified(row, review, snapshot)),
        ('本机模拟', 'simulation', lambda row: row.get('simulation_executed') is True
            and row.get('observed_result_verified') is True),
    ]
    lines = []
    for label, field, evaluate in checks:
        row = observed.get(field)
        if row is None:
            lines.append(f'<li>{label} · 未验证</li>')
            continue
        require(path_key(row['actual_project']) == path_key(project), 'Validation evidence belongs to another project')
        state = '证据满足' if evaluate(row) and row.get('source') else '提供的记录不足以确认'
        lines.append(f'<li>{label} · {state} <small>{text(row.get("source", ""))}</small></li>')
    return '<ul>' + ''.join(lines) + '</ul>'


def report_page(designed, actual, identities, same_process, verified_reopen, verified_compile_reopen=False,
                deferred_updates=None, variable_catalog=None):
    same_generation = bool(actual and same_process and (actual['complete'], actual['document']) ==
                           (designed['complete'], designed['document']) and not verified_reopen)
    if not (same_generation or verified_reopen):
        actual = None
    size = actual['resolution'] if actual else None
    captured = forest_paths(actual['forest'], actual['document']) if actual else {}
    rows = list(captured.values())
    original = designed['original_forest']
    original_paths = forest_paths(original, designed['document'])
    mapped_original = {path: match_control(rows, row, same_generation) for path, row in original_paths.items()}
    viewport = actual.get('viewport', {}) if actual else {}
    visible = viewport.get('visible_page_rect')
    checks = []
    expected_geometry, actual_geometry = [], []
    planned, matched = {}, {}
    for control in designed['controls']:
        identity = control.get('existing') or identities.get(control.get('result_action'))
        row = match_control(rows, identity, same_generation)
        if row is not None:
            matched[control['id']] = row
        requested, observed = control['rectangle'], row['rectangle'] if row else None
        has_parent = bool(identity and len(identity.get('path', [])) > 1)
        expected_geometry.append((control['id'], requested if not has_parent else None))
        actual_geometry.append((control['id'], observed if not has_parent else None))
        styles = selected_properties(row, control['style'])
        binding = native_bindings(row)
        expected_binding = control['bindings']
        if control.get('details', {}).get('binding_properties') and expected_binding:
            # Older review files copied this pre-edit field into the expected outcome.
            expected_binding = {key: value for key, value in expected_binding.items() if key != 'input_variable'} or None
        if binding and expected_binding:
            binding = {key: binding[key] for key in expected_binding if key in binding}
            if binding.keys() != expected_binding.keys():
                binding = None
        expected_path = control.get('existing', {}).get('path')
        parent = mapped_original.get(tuple(expected_path[:-1])) if expected_path else None
        child_path = [*parent['path'], expected_path[-1]] if parent else None
        layer = (UNKNOWN if row is None else '待核对顺序' if len(row['path']) == 1 and not has_parent else
                 compare(child_path, row['path']))
        layer_path = row['path'] if row else None
        planned[control['id']] = (control, row)
        details = [
            f'几何 {compare(requested, observed)}',
            f'样式 {compare(control["style"] or None, styles)}',
            f'绑定 {compare(expected_binding, binding)}',
            f'层次 {layer} {text(layer_path)}',
            f'页面 {clip_status(observed, [0, 0, *size] if size and not has_parent else None)}',
            f'视口 {clip_status(observed, visible if not has_parent else None)}',
        ]
        if control.get('overlaps_source'):
            details.append('设计矩形与源件重叠')
        additional = control.get('details', {})
        if 'binding_properties' in additional:
            desired = additional['binding_properties']
            details.append(f'绑定字段 {compare(desired, selected_properties(row, desired))}')
        if 'components' in additional:
            captured_components = {tuple(str(part) for part in item['path']): item
                                   for item in (row or {}).get('components', [])}
            for item in additional['components']:
                selection = captured_components.get(tuple(str(part) for part in item['path']))
                details.append(f'组件属性 {compare(item["properties"], selected_properties(selection, item["properties"]))}')
        if 'button_phases' in additional:
            phases = (row or {}).get('button_phases')
            logical = [{key: phase[key] for key in ('texts', 'enabled_raw_uint32')} for phase in phases] if phases else None
            details.append(f'按钮动作 {compare(additional["button_phases"], logical)}')
        if 'events' in additional:
            events = (row or {}).get('events')
            logical = [{key: event[key] for key in ('intC', 'string10', 'string70', 'strings1C')}
                       for event in events['events']] if events is not None else None
            details.append(f'事件 {compare(additional["events"], logical)}')
        if 'animations' in additional:
            items = (row or {}).get('animation_capture', {}).get('items')
            result = compare_animations(additional['animations'], items, verified_compile_reopen, variable_catalog)
            details.append(f'动画 {result}')
        pending = (deferred_updates or {}).get(control.get('result_action'), {})
        for field, label in (('binding_updates', '绑定'), ('component_updates', '组件'),
                             ('button_changes', '按钮动作'), ('events', '事件'), ('animations', '动画')):
            if field in pending:
                details.append(f'{label} 另见第二阶段回读')
        checks.append(f'<tr><th>{text(control["id"])}</th><td>{text(control["layer"])}</td>'
                      f'<td>{text(requested)}</td><td>{text(observed) if observed is not None else UNKNOWN}</td>'
                      f'<td>{" · ".join(details)}</td></tr>')

    addressed = {tuple(control['existing']['path']): control for control in designed['controls'] if 'existing' in control}
    new_controls = [item for item, row in planned.values() if 'existing' not in item]
    retained, removed_checks = [], []
    deleted = {tuple(item['path']) for item in designed.get('removed', [])}
    for path, original_row in original_paths.items():
        actual_row = mapped_original[path]
        if path[:1] in deleted:
            candidates = matching_controls(rows, original_row, same_generation) if actual else None
            state = UNKNOWN if candidates is None or len(candidates) > 1 else compare(True, not candidates)
            removed_checks.append((path, state))
            continue
        if actual_row is None:
            retained.append((path, UNKNOWN))
            continue
        expected = addressed.get(path, {}).get('rectangle', original_row.get('rectangle'))
        parent_changed = any(original_paths[path[:n]].get('rectangle') != addressed.get(path[:n], {}).get(
            'rectangle', original_paths[path[:n]].get('rectangle')) for n in range(1, len(path)))
        parent = mapped_original.get(path[:-1])
        owner_verified = len(path) == 1 and len(actual_row['path']) == 1 or (
            parent and actual_row['path'][:-1] == parent['path'])
        state = DIFFERENCE if not owner_verified else compare(None if parent_changed else expected, actual_row.get('rectangle'))
        retained.append((path, state))
    sibling_checks = []
    for path, original_parent in original_paths.items():
        if path[:1] in deleted:
            continue
        parent = mapped_original[path]
        if not original_parent['children'] and not (parent and parent['children']):
            continue
        children = [mapped_original[tuple(child['path'])] for child in original_parent['children']]
        state = (UNKNOWN if parent is None or any(child is None for child in children) else
                 compare([child['complete'] for child in children],
                         [child['complete'] for child in parent['children']]))
        sibling_checks.append((path, state))
    requested_order = designed.get('control_order')
    if requested_order is not None:
        expected_order = [matched.get(item) if isinstance(item, str) else
                          mapped_original.get(tuple(item['path'] if isinstance(item, dict) else item))
                          for item in requested_order]
    else:
        expected_order = ([matched.get(item['id']) for item in new_controls if item['layer_placement'] == 'back'] +
                          [mapped_original[(index,)] for index in range(len(original)) if (index,) not in deleted] +
                          [matched.get(item['id']) for item in new_controls if item['layer_placement'] == 'append'])
    if any(row is None for row in expected_order):
        order = UNKNOWN
    else:
        ordered_ids = [row['complete'] for row in expected_order]
        order = compare(ordered_ids, [row['complete'] for row in actual['forest']] if actual else None)
    if any(state == DIFFERENCE for path, state in sibling_checks):
        order = DIFFERENCE
    elif order == MATCH and any(state == UNKNOWN for path, state in sibling_checks):
        order = UNKNOWN
    retained.extend((('children', *path), state) for path, state in sibling_checks if state != MATCH)
    sibling_info = ', '.join(f'{text(path)} {state}' for path, state in sibling_checks) or '无组内子序'
    retained_info = ', '.join(f'{text(path)} {state}' for path, state in retained if state != MATCH)
    if not retained_info:
        retained_info = '已识别对象的几何与所属层一致' if retained else '前像中无控件'
    mode = '重开后唯一原生 ID、类与名称' if actual and verified_reopen else '当前文档实例' if actual else UNKNOWN
    removed_info = ' · 删除 ' + ', '.join(f'{text(path)} {state}' for path, state in removed_checks) if removed_checks else ''
    bounds = [0, 0, *size] if size else None
    outside = [row['path'] for row in (actual['forest'] if actual else [])
               if clip_status(row.get('rectangle'), bounds) == '超出边界']
    viewport_clipping = ('有裁切' if not all((visible[0] <= 0, visible[1] <= 0,
                                            visible[2] >= size[0], visible[3] >= size[1])) else '完整覆盖'
                         ) if visible is not None and size else UNKNOWN
    return (f'<section><h2>{text(designed["name"])} <small>页 ID {designed["id"]}</small></h2>'
            f'<p>页面分辨率 {compare(designed["resolution"], size)} · 原生层序 {order} · 视口 {viewport_clipping}'
            f' · 越界路径 {text(outside) if actual else UNKNOWN}</p>'
            f'<p>身份匹配 {mode} · 现有对象 {retained_info}{removed_info}</p>'
            f'<p>各父控件子序 {sibling_info}</p>'
            f'<div class="boards">{draw_board(designed["resolution"], expected_geometry, "设计区域")}'
            f'{draw_board(size, actual_geometry, "原生回读区域")}</div>'
            '<table><thead><tr><th>控件</th><th>设计图层</th><th>设计矩形</th><th>回读矩形</th>'
            f'<th>核对</th></tr></thead><tbody>{"".join(checks)}</tbody></table></section>')


def render_review(review, snapshot=None, receipts=(), evidence=None):
    require(review.get('schema') == REVIEW, 'Unsupported review schema')
    project = review['project_path']
    actual = {}
    same_generation = False
    if snapshot is not None:
        require(snapshot.get('schema') == SNAPSHOT and path_key(snapshot['actual_project']) == path_key(project),
                'Native readback belongs to another project or schema')
        actual = {(row['id'], row['name']): row for row in snapshot['pages']}
        keys = ('process_id', 'creation_filetime', 'root')
        same_generation = all(review.get(key) is not None and review[key] == snapshot.get(key) for key in keys)
    for receipt in receipts:
        inspection = receipt.get('direct_inspection') or {}
        receipt_path = receipt.get('actual_project') or inspection.get('actual_project')
        keys = ('process_id', 'creation_filetime', 'native_thread_id', 'editor_image_sha256')
        require(receipt_path is not None and path_key(receipt_path) == path_key(project)
                and all(review.get(key) is not None and review[key] == inspection.get(key) for key in keys),
                'Action receipt belongs to another project or editor generation')
    identities = applied_objects(receipts, {action['id']: action for action in review['actions']})
    reopen = (evidence or {}).get('reopen') or {}
    reopened = reopen_verified(reopen, review, snapshot)
    check = (evidence or {}).get('check') or {}
    checked = check.get('state_after') or {}
    before_reopen = reopen.get('state_before') or {}
    compile_reopen = bool(reopened and check.get('source') and check.get('review_id') == review.get('review_id')
                          and check.get('kind') == 'project-check-original-root85'
                          and all(check.get(key) is True for key in ('native_check_passed',
                                  'original_worker_call_entered', 'original_worker_returned'))
                          and type(check.get('original_worker_return_int32')) is int
                          and check['original_worker_return_int32'] == 0 and checked.get('root_compile_valid_raw') == 1
                          and checked.get('actual_project') and path_key(checked['actual_project']) == path_key(project)
                          and all(checked.get(key) == before_reopen.get(key) for key in
                                  ('root', 'process_id', 'project_sha256')))
    deferred = {update['result_action']: update for update in review.get('deferred_updates', [])}
    variable_catalog = snapshot.get('variable_catalog') if snapshot else None
    sections = ''.join(report_page(page, actual.get((page['id'], page['name'])), identities,
                                   same_generation, reopened, compile_reopen, deferred, variable_catalog)
                       for page in review['pages'])
    return f'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pro 画面设计与原生回读</title>
<style>
body{{font:16px/1.55 "Segoe UI","Microsoft YaHei",sans-serif;margin:2rem auto;max-width:1100px;padding:0 1rem;color:#172635;background:#f6f8fa}}
section{{margin:1.25rem 0;padding:1.25rem;border:1px solid #d4dce5;border-radius:10px;background:white;overflow:auto}}
small{{color:#435770}} table{{width:100%;border-collapse:collapse;text-align:left}}
th,td{{padding:.65rem;border-bottom:1px solid #dee5ec}} th{{font-weight:600}}
.boards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:1rem}} figure{{margin:0 0 1rem}}
.drawing{{position:relative;overflow:hidden;background:#eef3f8;border:1px solid #8196ab}}
.mark{{position:absolute;box-sizing:border-box;border:1px solid #255b87;background:#9bd0ef55;color:#133b61;font-size:.72rem;white-space:nowrap;overflow:hidden}}
</style>
<h1>Pro 画面设计与原生回读</h1>
<p>{text(project)}</p>
<p>几何示意使用页坐标。组内归一化矩形列在表中。截图、字体渲染和动态值有各自的验收证据。</p>
<section><h2>验收记录</h2><ul><li>原生独立回读 · {"已提供，逐项结果见下方" if snapshot else "未验证"}</li></ul>
{evidence_html(project, evidence, review, snapshot)}</section>
{sections}
</html>
'''
