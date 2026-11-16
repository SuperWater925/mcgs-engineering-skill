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


def match_control(rows, identity, same_generation):
    if not identity:
        return None
    keys = ('native_id', 'name', 'class')
    if same_generation:
        keys += ('complete', 'owner_document')
    if not all(key in identity for key in keys):
        return None
    matching = [row for row in rows if all(key in row and row[key] == identity[key] for key in keys)]
    return matching[0] if len(matching) == 1 else None


def compare(expected, actual):
    if expected is None or actual is None:
        return UNKNOWN
    return MATCH if expected == actual else DIFFERENCE


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


def reopen_verified(row):
    return row.get('normal_project_closed_then_reopened_verified') is True and row.get('open_confirmed_same_project') is True


def evidence_html(project, evidence):
    observed = evidence or {}
    checks = [
        ('原厂保存', 'save', lambda row: row.get('native_save_return_verified') is True and row.get('root_modified') == 0
         and bool(row.get('sha256_after'))),
        ('文件回读', 'file', lambda row: row.get('independent_file_readback_verified') is True and bool(row.get('sha256'))),
        ('原生工程检查', 'check', lambda row: all(row.get(key) is True for key in (
            'native_check_passed', 'original_worker_call_entered', 'original_worker_returned'))
            and type(row.get('original_worker_return_int32')) is int and row['original_worker_return_int32'] == 0
            and row.get('state_after', {}).get('root_compile_valid_raw') == 1),
        ('正常关闭重开', 'reopen', reopen_verified),
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


def report_page(designed, actual, identities, same_process, verified_reopen):
    same_generation = bool(actual and same_process and (actual['complete'], actual['document']) ==
                           (designed['complete'], designed['document']) and not verified_reopen)
    if not (same_generation or verified_reopen):
        actual = None
    size = actual['resolution'] if actual else None
    captured = forest_paths(actual['forest'], actual['document']) if actual else {}
    rows = list(captured.values())
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
        if binding and expected_binding:
            binding = {key: binding[key] for key in expected_binding if key in binding}
            if binding.keys() != expected_binding.keys():
                binding = None
        expected_path = control.get('existing', {}).get('path')
        layer = (UNKNOWN if row is None else '待核对顺序' if len(row['path']) == 1 else
                 compare(expected_path[:-1] if expected_path else None, row['path'][:-1]))
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
        checks.append(f'<tr><th>{text(control["id"])}</th><td>{text(control["layer"])}</td>'
                      f'<td>{text(requested)}</td><td>{text(observed) if observed is not None else UNKNOWN}</td>'
                      f'<td>{" · ".join(details)}</td></tr>')

    original = designed['original_forest']
    original_paths = forest_paths(original, designed['document'])
    mapped_original = {path: match_control(rows, row, same_generation) for path, row in original_paths.items()}
    addressed = {tuple(control['existing']['path']): control for control in designed['controls'] if 'existing' in control}
    new_controls = [item for item, row in planned.values() if 'existing' not in item]
    retained = []
    for path, original_row in original_paths.items():
        actual_row = mapped_original[path]
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
    expected_order = ([matched.get(item['id']) for item in new_controls if item['layer_placement'] == 'back'] +
                      [mapped_original[(index,)] for index in range(len(original))] +
                      [matched.get(item['id']) for item in new_controls if item['layer_placement'] == 'append'])
    if any(row is None for row in expected_order):
        order = UNKNOWN
    else:
        ordered_ids = [row['complete'] for row in expected_order]
        order = compare(ordered_ids, [row['complete'] for row in actual['forest']] if actual else None)
    retained_info = ', '.join(f'{text(path)} {state}' for path, state in retained if state != MATCH)
    if not retained_info:
        retained_info = '已识别对象的几何与所属层一致' if retained else '前像中无控件'
    mode = '重开后唯一原生 ID、类与名称' if actual and verified_reopen else '当前文档实例' if actual else UNKNOWN
    bounds = [0, 0, *size] if size else None
    outside = [row['path'] for row in (actual['forest'] if actual else [])
               if clip_status(row.get('rectangle'), bounds) == '超出边界']
    viewport_clipping = ('有裁切' if not all((visible[0] <= 0, visible[1] <= 0,
                                            visible[2] >= size[0], visible[3] >= size[1])) else '完整覆盖'
                         ) if visible is not None and size else UNKNOWN
    return (f'<section><h2>{text(designed["name"])} <small>页 ID {designed["id"]}</small></h2>'
            f'<p>页面分辨率 {compare(designed["resolution"], size)} · 原生层序 {order} · 视口 {viewport_clipping}'
            f' · 越界路径 {text(outside) if actual else UNKNOWN}</p>'
            f'<p>身份匹配 {mode} · 现有对象 {retained_info}</p>'
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
        keys = ('process_id', 'creation_filetime')
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
    reopened = bool(reopen.get('source') and reopen_verified(reopen))
    sections = ''.join(report_page(page, actual.get((page['id'], page['name'])), identities,
                                   same_generation, reopened) for page in review['pages'])
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
{evidence_html(project, evidence)}</section>
{sections}
</html>
'''
