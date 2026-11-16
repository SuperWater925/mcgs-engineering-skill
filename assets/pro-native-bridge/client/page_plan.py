"""Compile incremental page designs into the existing native engineering program."""
from __future__ import annotations

import copy
import hashlib
import json
import ntpath
import re

DESIGN = 'mcgs-page-design/v1'
SNAPSHOT = 'mcgs-page-native-snapshot/v1'
REVIEW = 'mcgs-page-plan-review/v1'
IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{1,40}\Z')
IDENTITY = ('complete', 'native_id', 'name', 'class', 'owner_document')
# Same encoded request budget as the session runner's cross-step batching.
PLAN_BYTES = 8 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, required, optional=()):
    require(isinstance(value, dict), 'Expected an object')
    require(set(required) <= value.keys(), 'Missing fields: ' + ', '.join(sorted(set(required) - value.keys())))
    require(not (value.keys() - set(required) - set(optional)),
            'Unknown fields: ' + ', '.join(sorted(value.keys() - set(required) - set(optional))))
    return value


def path_key(path):
    require(isinstance(path, str), 'Project identity must include a full absolute .mcp path')
    drive, tail = ntpath.splitdrive(path)
    require(drive and tail.startswith(('/', '\\')) and ntpath.splitext(tail)[1].casefold() == '.mcp',
            'Project identity must include a full absolute .mcp path')
    return ntpath.normcase(ntpath.normpath(path))


def identifier(value):
    require(isinstance(value, str) and IDENTIFIER.fullmatch(value), 'Invalid design id')
    return value


def int_vector(value, count):
    require(isinstance(value, list) and len(value) == count and all(type(item) is int for item in value),
            f'Expected {count} integer values')
    return value


def forest_paths(forest, document, prefix=()):
    require(isinstance(forest, list), 'Native forest must be a list')
    rows = {}
    for index, row in enumerate(forest):
        path = (*prefix, index)
        require(row['path'] == list(path), 'Native path disagrees with actual forest order')
        require(row['owner_document'] == document, 'Native control has another document owner')
        rows[path] = row
        rows.update(forest_paths(row['children'], document, path))
    return rows


def native_page(page, forest, view=None):
    return {
        'id': page['page_id'], 'name': page['page_name'], 'complete': page['page_iobject'],
        'document': page['document'], 'resolution': page['attributes'][2:4],
        'forest': copy.deepcopy(forest), 'view': view or {},
    }


def root_properties(before):
    return [{key: row[key] for key in ('native_key', 'native_type_tag', 'value')}
            for row in before['properties'] if row['native_owner'] == before['selected_owner']
            and row['native_type_tag'] != 9]


def normalize_receipts(receipts):
    """Project actual inspect payloads into the page/compiler model."""
    pages, typed, button_states, factories = {}, [], [], []
    snapshot = {'schema': SNAPSHOT}
    generation = None
    for receipt in receipts:
        require(receipt.get('ok') is True and receipt.get('op') == 'engineering-edit-inspect'
                and receipt.get('inspection_completed') is True and receipt.get('write_attempted') is False,
                'Expected a completed native inspection receipt')
        current = (path_key(receipt['actual_project']), receipt['process_id'], receipt['creation_filetime'],
                   receipt['native_thread_id'], receipt['editor_image_sha256'])
        require(generation in (None, current), 'Capture receipts are from different projects or editor generations')
        generation = current
        kinds = receipt['compiled_kinds']
        if 'compiled_kinds' in snapshot:
            require(set(snapshot['compiled_kinds']) == set(kinds), 'Compiled kinds changed across native captures')
        snapshot.update(actual_project=receipt['actual_project'], process_id=current[1],
                        creation_filetime=current[2], native_thread_id=current[3],
                        editor_image_sha256=current[4], compiled_kinds=kinds)
        for action in receipt['action_preimages']:
            before, kind = action['before'], action['kind']
            if kind in ('control-geometry-batch', 'control-layer', 'control-native-create', 'control-geometry'):
                if 'forest' in before:
                    page = native_page(before['page'], before['forest'], before.get('view_state'))
                elif 'target_forest' in before:
                    page = native_page(before['target_page'], before['target_forest'], before.get('view_state'))
                else:
                    continue
                old = pages.get(page['id'])
                require(old is None or old == page, 'Conflicting page/forest captures for one page')
                pages[page['id']] = page
                if kind == 'control-native-create':
                    probe = {'page_id': page['id'], 'class': before['class']}
                    if probe not in factories:
                        factories.append(probe)
            elif kind == 'control-properties' and not action['target'].get('component_path'):
                typed.append(before)
            elif kind == 'button-actions-batch':
                button_states.append(before)
            elif kind == 'reference-graph' and before['graph'].get('complete_registered_native_graph') is True:
                edges = before['graph']['edges']
                require(snapshot.get('reference_edges', edges) == edges, 'Conflicting native graph captures')
                snapshot['reference_edges'] = edges
                aux = before.get('main_control', {}).get('arrays', {}).get('AuxIds', {}).get('values')
                if isinstance(aux, list) and all(type(value) is int for value in aux):
                    require(snapshot.get('configured_auxiliary_page_ids', aux) == aux,
                            'Conflicting native auxiliary-window captures')
                    snapshot['configured_auxiliary_page_ids'] = aux
            elif kind == 'data-catalog' and before.get('module_id') == 2:
                names = [row['name'] for row in before['records']]
                require(snapshot.get('variables', names) == names, 'Conflicting native data catalog captures')
                snapshot['variables'] = names
    require(pages, 'No full native drawing forest is present in the selected receipts')
    lookups = {page['id']: {row['complete']: row for row in forest_paths(page['forest'], page['document']).values()}
               for page in pages.values()}
    for before in typed:
        page, control = before['page'], before['control']
        row = lookups.get(page['page_id'], {}).get(control['complete'])
        require(row is not None and control['owner_document'] == row['owner_document'],
                'Typed capture does not belong to the captured forest')
        styles = root_properties(before)
        require(row.get('style', styles) == styles, 'Conflicting typed root property captures')
        row['style'] = styles
    for before in button_states:
        page, control = before['page'], before['control']
        row = lookups.get(page['page_id'], {}).get(control['complete'])
        require(row is not None and control['owner_document'] == row['owner_document'],
                'Button capture does not belong to the captured forest')
        row['button_phases'] = before['phases']
    snapshot['pages'] = list(pages.values())
    snapshot['factory_probes'] = factories
    return snapshot


def record_viewports(snapshot, evidence):
    require(evidence.get('schema') == 'mcgs-page-viewport-evidence/v1'
            and path_key(evidence['actual_project']) == path_key(snapshot['actual_project'])
            and evidence.get('process_id') == snapshot['process_id']
            and evidence.get('creation_filetime') == snapshot['creation_filetime'],
            'Viewport observation belongs to another project or editor generation')
    pages = {page['id']: page for page in snapshot['pages']}
    for row in evidence['pages']:
        fields(row, ('page_id', 'document', 'hwnd', 'visible_page_rect', 'source'), ('zoom',))
        page = pages[row['page_id']]
        rect = int_vector(row['visible_page_rect'], 4)
        require(page['document'] == row['document'] and page['view'].get('hwnd') == row['hwnd']
                and page['view'].get('hwnd') not in (None, '0x00000000')
                and isinstance(row['source'], str) and row['source']
                and rect[2] > rect[0] and rect[3] > rect[1] and 'viewport' not in page,
                'Viewport observation does not match the live drawing view')
        page['viewport'] = {key: value for key, value in row.items() if key in ('visible_page_rect', 'source', 'zoom')}
    return snapshot


def signed_i4(value):
    return type(value) is int and -(2 ** 31) <= value < 2 ** 31


def native_string(value):
    return isinstance(value, str) and '\0' not in value


def property_value(tag, value, previous=None):
    if tag == 0:
        require(type(value) is int and 0 <= value < 2 ** 32, 'Expected native UInt32')
    elif tag == 2:
        require(signed_i4(value), 'Expected native Int32')
    elif tag in (4, 11):
        require(type(value) is bool, 'Expected native Boolean')
    elif tag in (3, 5, 8, 10, 12):
        require(native_string(value), 'Expected native text without NUL')
    elif tag in (6, 7):
        fields(value, ('text', 'number'))
        require(native_string(value['text']) and signed_i4(value['number']), 'Invalid native text/number pair')
    elif tag == 1:
        fields(value, ('native_flag', 'rows'), ('row_count',))
        rows = value['rows']
        require(type(value['native_flag']) is bool and isinstance(rows, list) and rows
                and value.get('row_count', len(rows)) == len(rows), 'Invalid native font value')
        ids = set()
        for row in rows:
            fields(row, ('language_id', 'face_name', 'height', 'weight', 'italic'))
            language, face = row['language_id'], row['face_name']
            require(signed_i4(language) and language not in ids and signed_i4(row['height'])
                    and type(row['weight']) is int and 0 <= row['weight'] <= 1000 and type(row['italic']) is bool
                    and native_string(face) and 0 < len(face.encode('utf-16-le')) <= 62, 'Invalid native font row')
            ids.add(language)
        if previous is not None:
            require(value['native_flag'] == previous['native_flag']
                    and ids == {row['language_id'] for row in previous['rows']},
                    'Font style must retain original native flag and language rows')
        value = {**value, 'row_count': len(rows)}
    return value


def property_updates(requested, observed=None):
    require(isinstance(requested, list), 'Style must use a list of native typed property assignments')
    if observed is not None:
        available = {(row['native_key'], row['native_type_tag']): row['value'] for row in observed}
    assigned = set()
    result = []
    for row in requested:
        fields(row, ('native_key', 'native_type_tag', 'value'))
        key, tag, value = row['native_key'], row['native_type_tag'], row['value']
        require(native_string(key) and key and key not in assigned and type(tag) is int and 0 <= tag <= 12 and tag != 9,
                'Style requires unique native keys and a writable typed value')
        assigned.add(key)
        if observed is not None:
            require((key, tag) in available, 'Native getter key/tag not observed: ' + key)
        prior = available[(key, tag)] if observed is not None else None
        value = property_value(tag, value, prior)
        if observed is not None and type(value) is type(prior) and value == prior:
            continue
        result.append(copy.deepcopy({**row, 'value': value}))
    return result


def rectangle(value, resolution, class_name, factory=False):
    left, top, right, bottom = int_vector(value, 4)
    width, height = resolution
    positive = right > left or bottom > top if class_name == 'CDrawLine' and not factory else right > left and bottom > top
    require(0 <= left <= right <= width and 0 <= top <= bottom <= height and positive,
            f'Rectangle {value} is invalid for {class_name} in {width}×{height}')
    return value


def selector(row, include_path=True):
    result = {'class': row['class'], 'control_name': row['name'],
              'complete': row['complete'], 'native_id': row['native_id']}
    if include_path:
        result['control_path'] = row['path']
    return result


def native_result(action_id, branch, key):
    return {'$native_result': {'action_id': action_id, 'path': f'/apply/{branch}/{key}'}}


def result_selector(action_id, branch):
    return {name: native_result(action_id, branch, key) for name, key in
            (('complete', 'complete'), ('native_id', 'native_id'), ('class', 'class'), ('control_name', 'name'))}


def append_action(actions, kind, target, after, **extra):
    action_id = f'{kind}-{len(actions) + 1:05d}'
    actions.append({'action_id': action_id, 'kind': kind, 'target': target, 'after': after, **extra})
    return action_id


def compile_design(design, snapshot):
    fields(design, ('schema', 'project_path', 'pages'), ('save', 'expected_reference_edges', 'native_derived_cache_contract'))
    require(design['schema'] == DESIGN and snapshot.get('schema') == SNAPSHOT, 'Unsupported design or snapshot schema')
    require(path_key(design['project_path']) == path_key(snapshot['actual_project']), 'Native capture project path differs')
    save = design.get('save', False)
    require(type(save) is bool, 'Save must be a Boolean')
    pages = {row['id']: row for row in snapshot['pages']}
    require(len(pages) == len(snapshot['pages']), 'Duplicate native page IDs')
    require(isinstance(design['pages'], list) and design['pages'], 'Provide at least one designed page')
    actions, review_pages, changed, seen = [], [], [], set()
    for page_design in design['pages']:
        fields(page_design, ('id', 'name', 'resolution', 'layers'), ('common_page_ids',))
        page_id = page_design['id']
        require(type(page_id) is int and page_id in pages and page_id not in seen, 'Unknown or repeated native page')
        seen.add(page_id)
        page = pages[page_id]
        require(page_design['name'] == page['name'] and bool(page['complete']) and bool(page['document']),
                'Native page identity differs')
        size = int_vector(page_design['resolution'], 2)
        require(min(size) > 0 and size == page['resolution'], 'Design does not match the actual page resolution')
        common = page_design.get('common_page_ids', [])
        require(isinstance(common, list) and all(type(entry) is int for entry in common)
                and len(set(common)) == len(common), 'Common page IDs must be unique integers')
        require(all(entry in pages and entry != page_id for entry in common),
                'Unknown common page ID (include it in native capture)')
        require(all(entry in snapshot.get('configured_auxiliary_page_ids', []) for entry in common),
                'Requested common page is absent from the original MainCtrl auxiliary-window list')
        page_target = {'page_id': page_id, 'page_name': page['name']}
        start = len(actions)
        controls = compile_page(page_design, page, page_target, actions, snapshot)
        review_pages.append({'id': page_id, 'name': page['name'], 'resolution': size,
                             'complete': page['complete'], 'document': page['document'],
                             'common_page_ids': common, 'controls': controls,
                             'original_forest': page['forest']})
        if len(actions) > start:
            changed.append(page_target)
    edit_actions = actions
    sync_actions, save_actions = [], []
    if 'expected_reference_edges' in design and changed:
        edges = design['expected_reference_edges']
        require(isinstance(edges, list), 'Expected complete registered reference edges')
        for edge in edges:
            fields(edge, ('source', 'target'))
            require(all(isinstance(value, str) and value for value in edge.values()), 'Empty native reference endpoint')
        after = {'allow_original_full_generate': True, 'expected_reference_edges': edges}
        if 'native_derived_cache_contract' in design:
            require(isinstance(design['native_derived_cache_contract'], dict), 'Native derived-cache contract must be an object')
            after['native_derived_cache_contract'] = design['native_derived_cache_contract']
        append_action(sync_actions, 'reference-sync', {'page_ids': [page['page_id'] for page in changed], 'strategy_ids': []}, after)
    if save and changed:
        for page in changed:
            append_action(save_actions, 'page-flush', page, {})
        append_action(save_actions, 'root-flush', {}, {})
    actions = edit_actions + sync_actions + save_actions
    # A different design or input capture must not reuse these action IDs.
    namespace = hashlib.sha256(json.dumps([design, snapshot], sort_keys=True,
                                         ensure_ascii=False, allow_nan=False).encode()).hexdigest()[:12]
    for action in actions:
        action['action_id'] = scoped_id(action['action_id'], namespace)
        for key in ('target', 'source', 'after'):
            if key in action:
                action[key] = namespace_refs(action[key], namespace)
    for page in review_pages:
        for control in page['controls']:
            if 'result_action' in control:
                control['result_action'] = scoped_id(control['result_action'], namespace)
    kinds = set(snapshot['compiled_kinds'])
    missing = sorted({action['kind'] for action in actions} - kinds)
    require(not missing, 'The native capture lacks compiled action kinds: ' + ', '.join(missing))
    steps = []
    for name, stage_actions in (('page-plan', edit_actions), ('reference-sync', sync_actions), ('page-save', save_actions)):
        if stage_actions:
            spec = {'commit': False, 'actions': stage_actions}
            require(len(json.dumps(spec, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()) <= PLAN_BYTES,
                    'Program step exceeds the encoded request budget')
            steps.append({'step_id': name, 'specification': spec})
    program = {'schema': 1, 'purpose': 'native-engineering-session-program', 'project_path': design['project_path'],
               'steps': steps}
    review = {'schema': REVIEW, 'project_path': design['project_path'], 'process_id': snapshot.get('process_id'),
              'creation_filetime': snapshot.get('creation_filetime'),
              'native_thread_id': snapshot.get('native_thread_id'),
              'editor_image_sha256': snapshot.get('editor_image_sha256'), 'pages': review_pages,
              'actions': [{'id': action['action_id'], 'kind': action['kind'],
                           'page_id': action['target'].get('page_id')} for action in actions],
              'save_requested': save, 'reference_sync_requested': 'expected_reference_edges' in design,
              'native_execution_performed': False}
    return program, review


def scoped_id(identifier, namespace):
    return f'{identifier}-{namespace}'


def namespace_refs(value, namespace):
    if isinstance(value, dict):
        if '$native_result' in value:
            ref = value['$native_result']
            return {'$native_result': {**ref, 'action_id': scoped_id(ref['action_id'], namespace)}}
        return {key: namespace_refs(child, namespace) for key, child in value.items()}
    if isinstance(value, list):
        return [namespace_refs(child, namespace) for child in value]
    return value


def compile_page(design, page, target, actions, snapshot):
    require(isinstance(design['layers'], list) and design['layers'], 'A page needs at least one layer')
    observed = forest_paths(page['forest'], page['document'])
    require(len({row['complete'] for row in observed.values()}) == len(observed), 'Native forest repeats a complete object')
    ordered, resolved, layer_ids, existing, back = [], {}, set(), set(), []
    active = False
    first = len(actions)

    def activate():
        nonlocal active
        if not active:
            append_action(actions, 'page-view-open', target, {'open': True})
            active = True

    for layer in design['layers']:
        fields(layer, ('id', 'controls'), ('placement',))
        layer_id = identifier(layer['id'])
        require(layer_id not in layer_ids, 'Repeated layer id')
        layer_ids.add(layer_id)
        placement = layer.get('placement', 'append')
        require(placement in ('append', 'back'), 'Layer placement must be append or back')
        require(isinstance(layer['controls'], list), 'Layer controls must be an array')
        for control in layer['controls']:
            fields(control, ('id',), ('existing', 'class', 'rectangle', 'style', 'bindings',
                                      'depends_on', 'array', 'transform_group_children'))
            name = identifier(control['id'])
            require(name not in resolved, 'A design control id is repeated')
            dependencies = control.get('depends_on', [])
            require(isinstance(dependencies, list) and all(isinstance(dep, str) for dep in dependencies)
                    and len(set(dependencies)) == len(dependencies) and all(dep in resolved for dep in dependencies), 'Controls must follow their declared dependencies')
            base = {'id': name, 'layer': layer_id, 'layer_placement': placement, 'depends_on': dependencies}
            if 'array' in control:
                require(set(control) <= {'id', 'array', 'depends_on'}, 'Array instances inherit prototype values')
                activate()
                cells = compile_array(control['array'], resolved, page, target, actions, base)
                ordered.extend(cells)
                resolved[name] = None
                if placement == 'back':
                    back.extend(cells)
                continue
            row = None
            if 'existing' in control:
                require(placement == 'append', 'Back layers only move their own newly created controls')
                spec = control['existing']
                crit = spec if isinstance(spec, dict) else {'path': spec}
                fields(crit, ('path',), ('class', 'name', 'native_id', 'complete'))
                require(isinstance(crit['path'], list) and crit['path'] and all(type(value) is int for value in crit['path']),
                        'Use the observed native control path')
                path = tuple(crit['path'])
                row = observed.get(path)
                require(row is not None and path not in existing and all(key in row for key in IDENTITY)
                        and all(row.get(key) == value for key, value in crit.items()), 'Existing control identity differs')
                existing.add(path)
                class_name = row['class']
                require(control.get('class', class_name) == class_name, 'An existing control class cannot change')
            else:
                class_name = control.get('class')
                require(isinstance(class_name, str) and re.fullmatch(r'CDraw[A-Za-z0-9]+', class_name),
                        'A new primitive needs a concrete native draw class')
            bounds = page['resolution'] if row is None or len(row['path']) == 1 else [10000, 10000]
            geometry = rectangle(control.get('rectangle', row['rectangle'] if row else None), bounds, class_name, factory=row is None)
            require(type(control.get('transform_group_children', False)) is bool, 'Group transform flag must be Boolean')
            style = property_updates(control.get('style', []))
            if row is not None and style:
                require('style' in row, 'Read native typed properties before styling an existing control')
            if row is None:
                require({'page_id': page['id'], 'class': class_name} in snapshot.get('factory_probes', []),
                        'Inspect the native factory for this page and class before creating ' + class_name)
                if style:
                    # The type check comes from a real getter for this class. Its
                    # observed value is not the new object's constructor default.
                    getter = [prop for candidate in observed.values() if candidate['class'] == class_name
                              for prop in candidate.get('style', [])]
                    available = {(prop['native_key'], prop['native_type_tag']) for prop in getter}
                    require(all((prop['native_key'], prop['native_type_tag']) in available for prop in style),
                            'Read the requested native getter key/tag on an existing control of this class')
            assignments = property_updates(style, row.get('style') if row else None)
            binding = control.get('bindings', {})
            require(isinstance(binding, dict), 'Bindings require keyed native binding values')
            # Current explicit write support is a single proven Edit input getter.
            # Other controls retain captured native binding metadata as inherited evidence.
            if binding:
                require(row is not None, 'Explicit bindings require an observed native control')
                observed_bindings = native_bindings(row) or {}
                require(all(key in observed_bindings and observed_bindings[key] == value
                            for key, value in binding.items()),
                        'Binding declaration differs from the native getter or is unavailable')
                if 'input_variable' in binding and binding['input_variable']:
                    require(binding['input_variable'] in snapshot.get('variables', []),
                            'Edit input variable must exist in the native data catalog')
            expected = {**base, 'class': class_name, 'rectangle': geometry, 'style': style,
                        'bindings': binding or native_bindings(row)}
            if row is None:
                activate()
                action_id = append_action(actions, 'control-native-create', {**target, 'class': class_name},
                                          {'rectangle': geometry, 'properties': assignments})
                expected.update(result_action=action_id, result_branch='created')
                if placement == 'back':
                    back.append(expected)
            else:
                if geometry != row['rectangle'] or assignments:
                    require(all(resolved[dep] is not None and 'existing' in resolved[dep] for dep in dependencies),
                            'Existing path-based edits must precede additions; move the dependency to a new control')
                expected['existing'] = {**{key: row[key] for key in IDENTITY}, 'path': row['path']}
                if geometry != row['rectangle']:
                    group = bool(row['children'])
                    require(not group or control.get('transform_group_children') is True,
                            'A grouped control needs an explicit child transform')
                    activate()
                    append_action(actions, 'control-geometry', {**target, **selector(row, include_path=False)},
                                  {'rectangle': geometry, **({'transform_group_children': True} if group else {})})
                if assignments:
                    activate()
                    append_action(actions, 'control-properties',
                                  {**target, 'control_path': row['path'], 'control_name': row['name'],
                                   'rtti': row['rtti'], 'complete': row['complete'], 'native_id': row['native_id']},
                                  {'properties': assignments})
            ordered.append(expected)
            resolved[name] = expected
    # Existing path-based edits run before any native DocAdd, which can
    # displace paths. Keep order within each phase and all result dependencies.
    emitted = actions[first:]
    early = {'page-view-open', 'control-geometry', 'control-properties'}
    actions[first:] = [item for item in emitted if item['kind'] in early] + [
        item for item in emitted if item['kind'] not in early]
    for item in reversed(back):
        append_action(actions, 'control-layer', {**target, 'controls': [
            result_selector(item['result_action'], item['result_branch'])]}, {'direction': 'back'})
    return ordered


def native_bindings(row):
    if row is None:
        return None
    values = {key: row[key] for key in ('input_variable', 'button_phases') if key in row}
    if isinstance(row.get('bindings'), dict):
        values.update(row['bindings'])
    return values or None


def compile_array(array, resolved, page, target, actions, base):
    fields(array, ('source', 'rows', 'columns', 'column_gap', 'row_gap', 'origin'))
    source_id = identifier(array['source'])
    source = resolved.get(source_id)
    require(source is not None, 'Array source must name an earlier concrete control on this page')
    if source.get('existing'):
        require(len(source['existing']['path']) == 1, 'Array source must be a top-level native control')
        source_target = selector(source['existing'], include_path=False)
    else:
        source_target = result_selector(source['result_action'], source['result_branch'])
    counts = int_vector([array['rows'], array['columns']], 2)
    gaps = int_vector([array['column_gap'], array['row_gap']], 2)
    require(min(counts) > 0, 'Array counts must be positive')
    origin = int_vector(array['origin'], 2)
    left, top, right, bottom = source['rectangle']
    width, height = right - left, bottom - top
    original = source['rectangle']
    source_args = {**target, **source_target}
    minimum_action = {'action_id': 'control-template-clone-00000', 'kind': 'control-template-clone',
                      'target': target, 'source': source_args, 'after': {'rectangle': [0, 0, 0, 0],
                                                                      'transform_group_children': True}}
    minimum_bytes = len(json.dumps(minimum_action, ensure_ascii=False, separators=(',', ':')).encode())
    require(counts[0] * counts[1] * minimum_bytes <= PLAN_BYTES, 'Array exceeds the encoded request budget')
    cells = []
    for row in range(counts[0]):
        for col in range(counts[1]):
            x = origin[0] + col * (width + gaps[0])
            y = origin[1] + row * (height + gaps[1])
            rect = rectangle([x, y, x + width, y + height], page['resolution'], source['class'])
            key = append_action(actions, 'control-template-clone', target,
                                {'rectangle': rect, 'transform_group_children': True}, source=source_args)
            cells.append({**base, 'id': f"{base['id']}[{row + 1},{col + 1}]", 'source': source_id,
                          'class': source['class'], 'rectangle': rect, 'style': source['style'],
                          'bindings': source['bindings'], 'result_action': key, 'result_branch': 'resulting_control',
                          'overlaps_source': overlaps(original, rect) or original == rect})
    return cells


def overlaps(first, second):
    return max(first[0], second[0]) < min(first[2], second[2]) and max(first[1], second[1]) < min(first[3], second[3])
