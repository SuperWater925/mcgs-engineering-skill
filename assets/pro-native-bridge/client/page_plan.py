"""Compile incremental page designs into the existing native engineering program."""
from __future__ import annotations

import copy
import hashlib
import json
import ntpath
import re

from native_delivery_config import CLR_MAX_LENGTH

DESIGN = 'mcgs-page-design/v1'
PAGE_SETUP = 'mcgs-page-setup/v1'
SNAPSHOT = 'mcgs-page-native-snapshot/v1'
REVIEW = 'mcgs-page-plan-review/v1'
IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{1,40}\Z')
IDENTITY = ('complete', 'native_id', 'name', 'class', 'owner_document')
PLAN_FEATURE = 'plan-design-preflight/v1'
SELECTOR_FEATURE = 'strict-control-selector/v1'
CLONE_FEATURE = 'clone-target-eligibility/v1'
SOURCE_FEATURE = 'clone-source-native-result/v1'
GEOMETRY_FEATURE = 'geometry-batch-identity/v1'
FOLLOWUP_DETAIL_KINDS = {'binding_updates': 'control-properties', 'component_updates': 'control-properties',
                         'button_changes': 'button-actions-batch', 'events': 'control-event-list',
                         'animations': 'control-animation-list'}


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


def session_pointer_parts(pointer):
    require(isinstance(pointer, str) and pointer.startswith('/steps/'),
            'A result reference must start with /steps/')
    parts = []
    for part in pointer[1:].split('/'):
        require(not re.search(r'~(?![01])', part), 'Invalid JSON pointer escape')
        parts.append(part.replace('~1', '/').replace('~0', '~'))
    require(len(parts) >= 4 and parts[2] in ('inspect', 'apply'),
            "Reference must select a prior step's inspect/apply receipt")
    return parts


def session_references(value):
    if isinstance(value, dict):
        if '$ref' in value:
            require(set(value) == {'$ref'}, 'A result reference must contain only $ref')
            yield session_pointer_parts(value['$ref'])
        else:
            for child in value.values():
                yield from session_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from session_references(child)


def resolve_session_references(value, results, copy_value=copy.deepcopy):
    if isinstance(value, dict):
        if '$ref' in value:
            require(set(value) == {'$ref'}, 'A result reference must contain only $ref')
            selected = results
            for part in session_pointer_parts(value['$ref']):
                if isinstance(selected, list):
                    require(re.fullmatch(r'0|[1-9][0-9]*', part), 'Result reference array index is invalid')
                    selected = selected[int(part)]
                elif isinstance(selected, dict):
                    selected = selected[part]
                else:
                    raise ValueError('Result reference crosses a scalar')
            return copy_value(selected)
        return {key: resolve_session_references(child, results, copy_value) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve_session_references(child, results, copy_value) for child in value]
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
    pages, typed, button_states, control_events, animations, factories = {}, [], [], [], [], []
    components, page_operations = [], {}
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
        for key in ('features', 'project_sha256', 'root'):
            if key in receipt:
                require(key not in snapshot or snapshot[key] == receipt[key],
                        'Native contract or project preimage changed across captures: ' + key)
                snapshot[key] = copy.deepcopy(receipt[key])
        for action in receipt['action_preimages']:
            before, kind = action['before'], action['kind']
            if kind in ('page-create', 'page-size', 'page-delete'):
                target = before.get('target_page')
                key = kind if target is None else f"{kind}/{target['page_id']}"
                require(page_operations.get(key, before) == before, 'Conflicting native page operation captures')
                page_operations[key] = before
            elif kind in ('control-geometry-batch', 'control-layer', 'control-native-create', 'control-geometry'):
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
                    if 'clone_eligibility' in before:
                        probe['clone_eligibility'] = copy.deepcopy(before['clone_eligibility'])
                    existing_probe = next((item for item in factories if item['page_id'] == page['id']
                                           and item['class'] == before['class']), None)
                    require(existing_probe is None or existing_probe == probe, 'Conflicting native factory eligibility captures')
                    if existing_probe is None:
                        factories.append(probe)
            elif kind == 'control-properties':
                path = action['target'].get('component_path')
                if path:
                    components.append((path, before))
                else:
                    typed.append(before)
            elif kind == 'button-actions-batch':
                button_states.append(before)
            elif kind == 'control-event-list':
                control_events.append(before)
            elif kind == 'control-animation-list':
                animations.append(before)
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
                from pro_animation_plan import variable_catalog
                names = [row['name'] for row in before['records']]
                require(snapshot.get('variables', names) == names, 'Conflicting native data catalog captures')
                snapshot['variables'] = names
                catalog = variable_catalog(before['records'])
                require(snapshot.get('variable_catalog', catalog) == catalog, 'Conflicting native variable identities')
                snapshot['variable_catalog'] = catalog
                snapshot['variable_native_types'] = {name: record['kind'] for name, record in catalog.items()}
    require(pages or page_operations, 'No full native drawing forest or page operation is present in the receipts')
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
    for path, before in components:
        row = captured_control(lookups, before['page'], before['control'])
        items = row.setdefault('components', [])
        captured = {'path': path, 'style': root_properties(before)}
        previous = next((item for item in items if item['path'] == path), captured)
        require(previous == captured, 'Conflicting typed component property captures')
        if captured not in items:
            items.append(captured)
    for before in button_states:
        page, control = before['page'], before['control']
        row = lookups.get(page['page_id'], {}).get(control['complete'])
        require(row is not None and control['owner_document'] == row['owner_document'],
                'Button capture does not belong to the captured forest')
        row['button_phases'] = before['phases']
        row['button_history_raw13'] = before['page']['attributes'][9] if len(before['page']['attributes']) > 9 else None
    for before in control_events:
        page = before['target_page']['page']
        row = captured_control(lookups, page, before['target_control'])
        row['events'] = {key: before['target_control'][key] for key in ('events', 'native_definitions')}
        attributes = page['attributes']
        row['event_history_raw13'] = attributes[9] if len(attributes) > 9 else None
    for before in animations:
        row = captured_control(lookups, before['page'], before['target_control'])
        row['animation_capture'] = {key: before[key] for key in ('page', 'target_control', 'items')}
    snapshot['pages'] = list(pages.values())
    snapshot['factory_probes'] = factories
    snapshot['page_operations'] = page_operations
    return snapshot


def captured_control(lookups, page, control):
    row = lookups.get(page['page_id'], {}).get(control['complete'])
    require(row is not None and control['owner_document'] == row['owner_document'],
            'Control details do not belong to the captured forest')
    return row


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


class ActionBuffer(list):
    """Keep IDs monotonic while later batching shortens the wire action list."""
    def __init__(self):
        super().__init__()
        self.serial = 0


def append_action(actions, kind, target, after, **extra):
    if isinstance(actions, ActionBuffer):
        actions.serial += 1
        index = actions.serial
    else:
        index = len(actions) + 1
    action_id = f'{kind}-{index:05d}'
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
    actions, review_pages, changed, seen = ActionBuffer(), [], [], set()
    for page_design in design['pages']:
        fields(page_design, ('id', 'name', 'resolution', 'layers'), ('common_page_ids', 'remove', 'control_order'))
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
                             'original_forest': page['forest'], 'removed': page_design.get('remove', []),
                             'control_order': page_design.get('control_order')})
        if len(actions) > start:
            changed.append(page_target)
    edit_actions = actions
    sync_actions, save_actions = ActionBuffer(), ActionBuffer()
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
    deferred_updates, deferred_ids = [], {}
    for page in review_pages:
        for control in page['controls']:
            action_id = control.get('result_action')
            if action_id is not None:
                control['result_action'] = scoped_id(action_id, namespace)
            deferred = control.pop('deferred_details', None)
            if deferred:
                update_id = deferred_ids[action_id] = f'followup_control_{len(deferred_updates) + 1}'
                dependencies = [deferred_ids[previous] for previous in control.pop('deferred_dependencies')]
                deferred_updates.append({'id': update_id, 'result_action': control['result_action'],
                                         **({'depends_on': dependencies} if dependencies else {}), **deferred})
    kinds = set(snapshot['compiled_kinds'])
    needed = {action['kind'] for action in actions}
    needed.update(kind for key, kind in FOLLOWUP_DETAIL_KINDS.items()
                  if any(key in update for update in deferred_updates))
    missing = sorted(needed - kinds)
    require(not missing, 'The native capture lacks compiled action kinds: ' + ', '.join(missing))
    required_features = required_plan_features(actions)
    if actions:
        missing_features = sorted(required_features - set(snapshot.get('features', [])))
        require(not missing_features, 'Loaded engine lacks page-plan features: ' + ', '.join(missing_features) +
                '; use the matching engine selected by prepare-online/turnkey and recapture (no Pro version requirement)')
        preflight = design_preflight(snapshot, review_pages, actions, design)
    steps = []
    for name, stage_actions in (('page-plan', edit_actions), ('reference-sync', sync_actions), ('page-save', save_actions)):
        if stage_actions:
            spec = {'commit': False, 'actions': stage_actions}
            if name == 'page-plan':
                spec.update(design_preflight=preflight, required_features=sorted(required_features),
                            coalesce_native_properties=False)
            require_native_length(spec)
            steps.append({'step_id': name, 'specification': spec})
    program = {'schema': 1, 'purpose': 'native-engineering-session-program', 'project_path': design['project_path'],
               'steps': steps}
    review = {'schema': REVIEW, 'project_path': design['project_path'], 'process_id': snapshot.get('process_id'),
              'creation_filetime': snapshot.get('creation_filetime'),
              'native_thread_id': snapshot.get('native_thread_id'),
              'editor_image_sha256': snapshot.get('editor_image_sha256'),
              'root': snapshot.get('root'), 'project_sha256': snapshot.get('project_sha256'),
              'review_id': namespace, 'pages': review_pages,
              'actions': [{'id': action['action_id'], 'kind': action['kind'],
                           'page_id': action['target'].get('page_id')} for action in actions],
              'save_requested': save, 'reference_sync_requested': 'expected_reference_edges' in design,
              'native_execution_performed': False}
    if deferred_updates:
        review['deferred_updates'] = deferred_updates
    return program, review


def compile_page_setup(setup, snapshot):
    """Structural phase. The design phase uses a new capture after setup."""
    fields(setup, ('schema', 'project_path', 'operations'))
    require(setup['schema'] == PAGE_SETUP and snapshot.get('schema') == SNAPSHOT
            and path_key(setup['project_path']) == path_key(snapshot['actual_project']),
            'Page setup must use a capture from the same current project')
    operations = setup['operations']
    require(isinstance(operations, list) and operations, 'Provide page setup operations')
    compiled = set(snapshot['compiled_kinds'])
    require(PLAN_FEATURE in snapshot.get('features', []), 'Capture lacks native design preflight support')
    actions, seen, touched = ActionBuffer(), set(), set()
    evidence = snapshot.get('page_operations', {})
    namespace = hashlib.sha256(json.dumps([setup, snapshot], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    for item in operations:
        fields(item, ('operation', 'name'), ('id', 'resolution'))
        kind, name = 'page-' + item['operation'], item['name']
        require(kind in ('page-create', 'page-size', 'page-delete') and kind in compiled,
                'Current native capture does not support the page operation')
        require(native_string(name) and name.strip() and not any(c in name for c in '/\\'),
                'Page name must be nonempty and cannot contain path separators')
        if kind == 'page-create':
            require('id' not in item and kind in evidence and name.casefold() not in seen,
                    'Inspect native page creation and use a distinct new name')
            require(all(name.casefold() != row['name'].casefold() for row in evidence[kind]['pages']),
                    'A native page with that name already exists')
            seen.add(name.casefold())
            create = append_action(actions, kind, {}, {'page_name': name})
            if 'resolution' not in item:
                continue
            require('page-size' in compiled, 'This native capture does not support sizing the created page')
            fields(item, ('operation', 'name', 'resolution'))
            resize_target = {'page_name': name, 'page_id': native_result(create, 'target_page_after', 'page_id')}
        else:
            page_id = item.get('id')
            capture = evidence.get(f'{kind}/{page_id}')
            require(type(page_id) is int and capture is not None and page_id not in touched and
                    name == capture['target_page']['page_name'],
                    'Inspect the exact page/name and operation before resizing or deleting')
            touched.add(page_id)
            captured_page = capture['target_page']
            require(captured_page['view'] == '0x00000000', 'Close the internal page view before resizing or deleting')
            resize_target = {'page_name': name, 'page_id': page_id}
            if kind == 'page-delete':
                fields(item, ('operation', 'name', 'id'))
                require(capture['incoming_reference_status'] == 0 and captured_page['page_modified'] == 0 and
                        not captured_page['top_level_controls'], 'The native delete requires a saved empty, unreferenced page')
                append_action(actions, kind, resize_target, {})
                continue
        width, height = int_vector(item['resolution'], 2)
        require(0 < min(width, height) and max(width, height) <= CLR_MAX_LENGTH,
                'Page dimensions must use positive native integers')
        if kind == 'page-size':
            for row in captured_page['top_level_controls']:
                left, top, right, bottom = row['rectangle']
                require(left >= 0 and top >= 0 and right <= width and bottom <= height,
                        'Requested dimensions exclude an existing top-level control')
        append_action(actions, 'page-size', resize_target, {'width': width, 'height': height})
    for action in actions:
        action['action_id'] = scoped_id(action['action_id'], namespace)
        action['target'] = namespace_refs(action['target'], namespace)
    review_pages = [{**page, 'common_page_ids': [], 'controls': [], 'original_forest': page['forest']}
                    for page in snapshot['pages'] if page['id'] in touched]
    spec = {'commit': False, 'actions': actions, 'required_features': [PLAN_FEATURE],
            'design_preflight': design_preflight(snapshot, review_pages, actions, {'pages': []})}
    require_native_length(spec)
    program = {'schema': 1, 'purpose': 'native-engineering-session-program',
               'project_path': setup['project_path'],
               'steps': [{'step_id': 'page-setup', 'specification': spec}]}
    return program


def require_native_length(specification):
    rendered = dict(specification, trial_id='00000000-0000-0000-0000-000000000000')
    chunks = json.JSONEncoder(ensure_ascii=False, indent=2, allow_nan=False).iterencode(rendered)
    size = 1  # Session staging appends one newline to UTF-8 JSON.
    for chunk in chunks:
        size += len(chunk.encode())
        require(size <= CLR_MAX_LENGTH, 'Program step exceeds the native signed Int32 request length')


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
    require(isinstance(design['layers'], list) and (design['layers'] or design.get('remove') or design.get('control_order')),
            'A page needs a layer or a structural edit')
    observed = forest_paths(page['forest'], page['document'])
    require(len({row['complete'] for row in observed.values()}) == len(observed), 'Native forest repeats a complete object')
    ordered, resolved, layer_ids, existing, back = [], {}, set(), set(), []
    ancestors, emitted_by_control = {}, {}
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
                                      'depends_on', 'array', 'transform_group_children', 'binding_updates',
                                      'component_updates', 'button_changes', 'events', 'animations'))
            name = identifier(control['id'])
            require(name not in resolved, 'A design control id is repeated')
            dependencies = control.get('depends_on', [])
            require(isinstance(dependencies, list) and all(isinstance(dep, str) for dep in dependencies)
                    and len(set(dependencies)) == len(dependencies) and all(dep in resolved for dep in dependencies), 'Controls must follow their declared dependencies')
            ancestors[name] = set(dependencies).union(*(ancestors[dep] for dep in dependencies))
            action_start = len(actions)
            base = {'id': name, 'layer': layer_id, 'layer_placement': placement, 'depends_on': dependencies}
            if 'array' in control:
                require(set(control) <= {'id', 'array', 'depends_on'}, 'Array instances inherit prototype values')
                activate()
                cells = compile_array(control['array'], resolved, page, target, actions, base, snapshot, observed)
                ordered.extend(cells)
                resolved[name] = None
                if placement == 'back':
                    back.extend(cells)
                continue
            row = None
            if 'existing' in control:
                require(placement == 'append', 'Back layers only move their own newly created controls')
                row = observed_control(observed, control['existing'])
                path = tuple(row['path'])
                require(path not in existing, 'Existing control identity repeats')
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
                require(any(probe['page_id'] == page['id'] and probe['class'] == class_name
                            for probe in snapshot.get('factory_probes', [])),
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
            if row is not None:
                expected['clone_eligibility'] = copy.deepcopy(row.get('clone_eligibility'))
            else:
                probe = next(probe for probe in snapshot['factory_probes']
                             if probe['page_id'] == page['id'] and probe['class'] == class_name)
                expected['clone_eligibility'] = copy.deepcopy(probe.get('clone_eligibility'))
            if row is None:
                activate()
                action_id = append_action(actions, 'control-native-create', {**target, 'class': class_name},
                                          {'rectangle': geometry, 'properties': assignments})
                expected.update(result_action=action_id, result_branch='created')
                if placement == 'back':
                    back.append(expected)
            else:
                if geometry != row['rectangle'] or assignments:
                    require(all(resolved[dep] is not None and 'existing' in resolved[dep]
                                for dep in ancestors[name]),
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
            business = {key: control[key] for key in FOLLOWUP_DETAIL_KINDS if key in control}
            if business:
                validate_button_alignment(class_name, business.get('component_updates', []))
                if row is None:
                    expected['deferred_details'] = deferred_details(business)
                else:
                    require(all(resolved[dep] is not None and 'existing' in resolved[dep] for dep in ancestors[name]),
                            'Existing path-based business edits must precede additions')
                    activate()
                    compile_control_details(control, row, target, actions, expected, snapshot)
            ordered.append(expected)
            resolved[name] = expected
            emitted_by_control[name] = {'row': row, 'dependencies': ancestors[name],
                                        'actions': actions[action_start:], 'id': name}
    # Existing path-based edits run before any native DocAdd, which can
    # displace paths. Keep order within each phase and all result dependencies.
    emitted = actions[first:]
    history_editors = {'button-actions-batch', 'control-event-list', 'control-animation-list'}
    early = {'page-view-open', 'control-geometry', 'control-properties'} | history_editors
    def is_early(action):
        return action['kind'] in early and not any(isinstance(value, dict) and '$native_result' in value
                                                   for value in action['target'].values())
    visible = [item for item in emitted if item['kind'] == 'page-view-open']
    history = [item for item in emitted if item['kind'] in history_editors and is_early(item)]
    # A second history editor needs a fresh page preimage when the original
    # property is nonzero. An earlier action alone is no proof of its reset.
    if len(history) > 1:
        require(not any('history_property13_projection' in item['after'] for item in history),
                'Recapture page history between edits that change property 13')
    actions[first:] = visible + [
        item for item in emitted if item['kind'] != 'page-view-open' and is_early(item)] + [
        item for item in emitted if not is_early(item)]
    actions[first:] = batch_independent_edits(actions[first:], emitted_by_control, target)
    for item in reversed(back):
        append_action(actions, 'control-layer', {**target, 'controls': [
            result_selector(item['result_action'], item['result_branch'])]}, {'direction': 'back'})
    if design.get('remove') or 'control_order' in design:
        order_controls(design, observed, existing, resolved, ordered, target, actions, activate)
    pending = {}
    for control in ordered:
        if 'deferred_details' not in control:
            continue
        # Array cells share the declared array's dependencies, without depending
        # on unrelated siblings. All prior declared dependencies were validated above.
        name = control['id'].split('[', 1)[0]
        control['deferred_dependencies'] = [action_id for dep in pending if dep in ancestors[name]
                                            for action_id in pending[dep]]
        pending.setdefault(name, []).append(control['result_action'])
    return ordered


def observed_control(observed, identity):
    crit = identity if isinstance(identity, dict) else {'path': identity}
    fields(crit, ('path',), ('class', 'name', 'native_id', 'complete'))
    path = crit['path']
    require(isinstance(path, list) and path and all(type(index) is int for index in path),
            'Use the observed native control path')
    row = observed.get(tuple(path))
    require(row is not None and all(key in row for key in IDENTITY)
            and all(row.get(key) == value for key, value in crit.items()), 'Existing control identity differs')
    return row


def order_controls(design, observed, existing, resolved, new_controls, target, actions, activate):
    removals = design.get('remove', [])
    require(isinstance(removals, list), 'Control removals must be an array')
    removed = set()
    for identity in removals:
        fields(identity, ('path', 'name', 'class', 'native_id', 'complete'))
        row = observed_control(observed, identity)
        path = tuple(row['path'])
        require(len(path) == 1 and path not in removed and all(selected[:1] != path for selected in existing),
                'Remove a unique top-level control that the design does not retain')
        removed.add(path)
        activate()
        append_action(actions, 'control-template-delete', {**target, **selector(row, include_path=False)}, {})
    if 'control_order' not in design:
        return
    order = design['control_order']
    require(isinstance(order, list), 'Control order must be an array')
    ordered = {item['id']: item for item in (*resolved.values(), *new_controls)
               if item and 'result_action' in item}
    sources, identities, encountered = [], [], set()
    for value in order:
        if isinstance(value, str):
            require(value in ordered, 'Unknown newly created control in control order: ' + value)
            item = ordered[value]
            selection = result_selector(item['result_action'], item['result_branch'])
            identity = ('new', value)
        else:
            row = observed_control(observed, value)
            path = tuple(row['path'])
            require(len(path) == 1 and path not in removed, 'Only surviving top-level controls can be ordered')
            selection, identity = selector(row, include_path=False), ('original', path)
        require(identity not in encountered, 'Control order repeats a target')
        encountered.add(identity)
        sources.append(selection)
        identities.append(identity)
    retained = sorted(path for path in observed if len(path) == 1 and path not in removed)
    require(len(sources) == len(retained) + len(ordered), 'Order must cover every final top-level control')
    prefix = 0
    if not ordered:
        # Moving to the end preserves the relative order of the objects we leave in place.
        for path in retained:
            if identities[prefix] == ('original', path):
                prefix += 1
    for selection in sources[prefix:]:
        activate()
        append_action(actions, 'control-layer', {**target, 'controls': [selection]}, {'direction': 'front'})


def compile_control_details(control, row, page, actions, expected, snapshot, clone_target=None):
    target = {**page, **(clone_target or selector(row)), 'rtti': row['rtti']}
    details = expected.setdefault('details', {})
    if 'binding_updates' in control:
        updates = control['binding_updates']
        require(isinstance(updates, list) and updates and 'style' in row,
                'Read the native binding property before editing')
        requested = []
        for update in updates:
            fields(update, ('native_key', 'native_type_tag', 'value'), ('variable',))
            if 'variable' in update:
                value = update['value']
                if update['native_type_tag'] == 6 and isinstance(value, dict):
                    kind, value = value.get('number'), value.get('text')
                    if isinstance(value, str):
                        observed_kind = snapshot.get('variable_native_types', {}).get(value) if value else 0
                        require(type(kind) is int and kind == observed_kind,
                                'Binding native type must match the current variable catalog')
                require(isinstance(value, str) and update['variable'] == value and
                        (not value or value in snapshot.get('variables', [])),
                        'The binding variable must be present in the captured data catalog')
            requested.append({key: update[key] for key in ('native_key', 'native_type_tag', 'value')})
        require(not {item['native_key'] for item in requested} &
                {item['native_key'] for item in expected['style']}, 'Style and binding edits repeat a native key')
        assignments = property_updates(requested, row['style'])
        if clone_target:
            assignments = property_updates(requested)
        if assignments:
            append_action(actions, 'control-properties', target, {'properties': assignments})
        details['binding_properties'] = requested
        # The typed getter is authoritative for the write. The snapshot's
        # separate input_variable field is a preimage, without a key mapping.
        if assignments and 'input_variable' in (expected.get('bindings') or {}):
            expected['bindings'] = {key: value for key, value in expected['bindings'].items()
                                    if key != 'input_variable'} or None
    if 'component_updates' in control:
        updates = control['component_updates']
        require(isinstance(updates, list) and updates, 'Provide inspected component edits')
        details['components'] = []
        for update in updates:
            fields(update, ('path', 'properties'))
            matches = [entry for entry in row.get('components', []) if entry['path'] == update['path']]
            require(len(matches) == 1 and all(entry['path'] != update['path'] for entry in details['components']),
                    'Inspect this exact component path and edit it only once')
            assignments = property_updates(update['properties'], matches[0]['style'])
            if clone_target:
                assignments = property_updates(update['properties'])
            if assignments:
                append_action(actions, 'control-properties', {**target, 'component_path': update['path']},
                              {'properties': assignments})
            details['components'].append(copy.deepcopy(update))
    if 'button_changes' in control:
        phases = copy.deepcopy(row.get('button_phases'))
        changes = control['button_changes']
        require(isinstance(phases, list) and isinstance(changes, list) and changes,
                'Inspect the original button action phases before changing them')
        seen = set()
        for change in changes:
            fields(change, ('phase', 'action_index', 'enabled', 'text'))
            phase, index = change['phase'], change['action_index']
            require(type(phase) is int and 0 <= phase < len(phases) and type(index) is int and
                    0 <= index < len(phases[phase]['texts']) and (phase, index) not in seen
                    and type(change['enabled']) is bool and native_string(change['text']),
                    'Invalid or duplicate native button action slot')
            seen.add((phase, index))
            phases[phase]['texts'][index] = change['text']
            phases[phase]['enabled_raw_uint32'][index] = int(change['enabled'])
        after = {'changes': changes, 'defer_native_final_compile_and_reference_rebuild': True}
        history_projection(after, row.get('button_history_raw13') if not clone_target else 0)
        append_action(actions, 'button-actions-batch', target, after)
        # Action IDs are compiler outputs. Only compare logical slot values.
        details['button_phases'] = [{key: phase[key] for key in ('texts', 'enabled_raw_uint32')} for phase in phases]
        expected['bindings'] = {key: value for key, value in (expected.get('bindings') or {}).items()
                                if key != 'button_phases'}
    if 'events' in control:
        require(not clone_target and 'events' in row, 'Inspect the original event declarations on the target control')
        events, logical = event_design(control['events'], row['events'], target)
        after = {'events': events, 'allow_original_event_payload_rebuild': True,
                 'defer_native_final_compile_and_reference_rebuild': True}
        history_projection(after, row.get('event_history_raw13'))
        append_action(actions, 'control-event-list', target, after)
        details['events'] = logical
    if 'animations' in control:
        require(not clone_target and 'animation_capture' in row, 'Inspect the target control animation list before editing')
        from pro_animation_plan import prepare
        action = prepare(row['animation_capture'], control['animations'],
                         variable_catalog=snapshot.get('variable_catalog'))
        append_action(actions, action['kind'], action['target'], action['after'])
        details['animations'] = [item['expected_record'] for item in action['after']['items']]


def history_projection(after, raw):
    if raw:
        after['history_property13_projection'] = {'before_raw_uint32': raw & 0xffffffff, 'after_raw_uint32': 0}


def event_design(items, original, target):
    require(isinstance(items, list), 'Events must be the complete ordered native event list')
    definitions = {row['native_event_id']: row for row in original['native_definitions']}
    planned, logical, used = [], [], set()
    for item in items:
        fields(item, (), ('definition_id', 'existing_index', 'source10', 'text70', 'arguments'))
        require(('definition_id' in item) != ('existing_index' in item),
                'Choose a captured event definition or an existing event index')
        if 'existing_index' in item:
            index = item['existing_index']
            require(type(index) is int and 0 <= index < len(original['events']), 'Native event index is absent')
            event = original['events'][index]
            ident = event['intC']
            original_text = {field: event[field] for field in ('string10', 'string70', 'strings1C')}
            selector_value = {'source': {**target, 'event_index': index, 'event_intC': ident,
                                         'event_name': event['string8']}}
        else:
            ident = item['definition_id']
            require(type(ident) is int and ident in definitions and ident not in (1, 2),
                    'Original editor did not expose the requested event link')
            selector_value = {'definition': {'native_event_id': ident, 'native_name': definitions[ident]['native_name']}}
            original_text = {'string10': '', 'string70': '',
                             'strings1C': [''] * len(definitions[ident]['argument_descriptors_raw_uint16'])}
        require(ident not in used and ident in definitions, 'Repeated or unavailable native event ID')
        used.add(ident)
        for field in ('source10', 'text70'):
            require(field not in item or native_string(item[field]), 'Invalid event text')
        if 'arguments' in item:
            args = item['arguments']
            require(isinstance(args, list) and len(args) == len(definitions[ident]['argument_descriptors_raw_uint16'])
                    and all(native_string(arg) for arg in args), 'Event arguments differ from the original declaration')
        planned.append({**selector_value, **{key: value for key, value in item.items()
                                             if key not in ('definition_id', 'existing_index')}})
        result = {'intC': ident, **original_text}
        for field, key in (('source10', 'string10'), ('text70', 'string70'), ('arguments', 'strings1C')):
            if field in item:
                result[key] = item[field]
        for connection in [result['string10'], *result['strings1C']]:
            require(not any(mark in connection for mark in '\r\n') and
                    len(connection.encode('utf-16le')) <= 2 * 1048576, 'Event connection must be one native name')
        require(not result['string10'] or definitions[ident]['raw_word_10'] in (3, 4, 8),
                'The native declaration has no main event connection')
        require(len(result['string70'].encode('utf-16le')) <= 2 * 1048576, 'Event script exceeds its native text length')
        require(result['string10'] or result['string70'] or any(result['strings1C']),
                'The original event editor excludes a blank event')
        logical.append(result)
    return planned, logical


def required_plan_features(actions):
    if not actions:
        return set()
    features = {PLAN_FEATURE}
    def uses_identity(value):
        if isinstance(value, dict):
            return ('complete' in value or 'native_id' in value
                    or any(uses_identity(child) for child in value.values()))
        return isinstance(value, list) and any(uses_identity(child) for child in value)
    for action in actions:
        batch_targets = [item.get('target') for item in action['after'].get('controls', [])]
        if (uses_identity(action['target']) or uses_identity(action.get('source'))
                or any(uses_identity(target) for target in batch_targets)):
            features.add(SELECTOR_FEATURE)
        if action['kind'] == 'control-template-clone':
            features.add(CLONE_FEATURE)
            if any(isinstance(value, dict) and '$native_result' in value for value in action['source'].values()):
                features.add(SOURCE_FEATURE)
        if action['kind'] == 'control-geometry-batch':
            features.add(GEOMETRY_FEATURE)
        if action['kind'] == 'control-animation-list' and any(
                row.get('restore_observed_output_clone') for row in action['after'].get('items', [])):
            features.add('animation-output-serialize-projection/v1')
        if action['kind'] == 'control-animation-list' and any(
                row.get('restore_observed_size_clone') for row in action['after'].get('items', [])):
            features.add('animation-size-serialize-projection/v1')
        if action['kind'] == 'control-animation-list' and any(
                row.get('restore_observed_vmove_clone') for row in action['after'].get('items', [])):
            features.add('animation-vmove-serialize-projection/v1')
        if action['kind'] == 'control-animation-list' and any(
                'input_binding_preimage' in row for row in action['after'].get('items', [])):
            features.add('animation-input-binding-preimage/v1')
        if action['kind'] == 'control-animation-list' and any(
                row.get('restore_observed_palette_clone') for row in action['after'].get('items', [])):
            features.add('animation-palette-serialize-projection/v1')
    return features


def forest_preimage(forest):
    keys = (*IDENTITY, 'path', 'rectangle', 'caption', 'input_variable')
    return [{**{key: copy.deepcopy(row[key]) for key in keys if key in row},
             'children': forest_preimage(row['children'])} for row in forest]


def design_preflight(snapshot, review_pages, actions, design):
    require(all(snapshot.get(key) is not None for key in ('process_id', 'creation_filetime', 'root', 'project_sha256')),
            'Native capture lacks the project instance/file preimage; recapture with the matching engine')
    result = {key: snapshot[key] for key in ('process_id', 'creation_filetime', 'root', 'project_sha256')}
    result['project_path'] = snapshot['actual_project']
    selected_ids = {page['id'] for page in review_pages}
    selected_ids.update(common for page in review_pages for common in page['common_page_ids'])
    result['pages'] = [{'page_id': page['id'], 'page_name': page['name'], 'page_iobject': page['complete'],
                        'document': page['document'], 'resolution': page['resolution'],
                        'forest': forest_preimage(page['forest'])}
                       for page in snapshot['pages'] if page['id'] in selected_ids]
    result['style_preimages'], result['button_preimages'] = [], []
    for page in review_pages:
        original = forest_paths(page['original_forest'], page['document'])
        # Include getter samples only where the design actually uses a style,
        # and binding phases only where the review relies on their preservation.
        style_targets, button_targets, component_targets = {}, set(), []
        designed_controls = {control['id']: control for control in page['controls']}
        for control in page['controls']:
            source = designed_controls.get(control.get('source'), control)
            if control.get('style'):
                keys = {(prop['native_key'], prop['native_type_tag']) for prop in control['style']}
                if 'existing' in source:
                    style_targets.setdefault(tuple(source['existing']['path']), set()).update(keys)
                else:
                    for key in keys:
                        path = next(path for path, row in original.items() if row['class'] == control['class']
                                    and any((prop['native_key'], prop['native_type_tag']) == key for prop in row.get('style', [])))
                        style_targets.setdefault(path, set()).add(key)
            if 'existing' not in source:
                continue
            path = tuple(source['existing']['path'])
            details = control.get('details', {})
            if (control.get('bindings') or {}).get('button_phases') is not None or 'button_phases' in details:
                button_targets.add(path)
            if details.get('binding_properties'):
                style_targets.setdefault(path, set()).update((prop['native_key'], prop['native_type_tag'])
                                                             for prop in details['binding_properties'])
            for component in details.get('components', []):
                row = original[path]
                sample = next(item for item in row['components'] if item['path'] == component['path'])
                keys = {(prop['native_key'], prop['native_type_tag']) for prop in component['properties']}
                target = {'page_id': page['id'], 'page_name': page['name'], **selector(row), 'rtti': row['rtti'],
                          'component_path': component['path']}
                item = {'target': target, 'properties': [prop for prop in sample['style']
                                                        if (prop['native_key'], prop['native_type_tag']) in keys]}
                if item not in component_targets:
                    component_targets.append(copy.deepcopy(item))
        for path, row in original.items():
            if path not in style_targets and path not in button_targets:
                continue
            target = {'page_id': page['id'], 'page_name': page['name'], **selector(row), 'rtti': row['rtti']}
            if path in style_targets:
                properties = [prop for prop in row['style']
                              if (prop['native_key'], prop['native_type_tag']) in style_targets[path]]
                result['style_preimages'].append({'target': target, 'properties': copy.deepcopy(properties)})
            if path in button_targets:
                result['button_preimages'].append({'target': target, 'phases': copy.deepcopy(row['button_phases'])})
        result['style_preimages'].extend(component_targets)
    result['clone_sources'], result['clone_factory_classes'] = [], []
    by_id = {action['action_id']: action for action in actions}
    for action in actions:
        if action['kind'] != 'control-template-clone':
            continue
        source = action['source']
        if isinstance(source.get('complete'), dict):
            producer = by_id[source['complete']['$native_result']['action_id']]
            candidate = {key: producer['target'][key] for key in ('page_id', 'page_name', 'class')}
            bucket = result['clone_factory_classes']
        else:
            candidate, bucket = source, result['clone_sources']
        if candidate not in bucket:
            bucket.append(copy.deepcopy(candidate))
    if any(page['common_page_ids'] for page in review_pages):
        result['configured_auxiliary_page_ids'] = sorted({common for page in review_pages
                                                       for common in page['common_page_ids']})
    variables = {control.get('bindings', {}).get('input_variable') for page in design['pages']
                 for layer in page['layers'] for control in layer['controls']}
    for page in design['pages']:
        for layer in page['layers']:
            for control in layer['controls']:
                for item in (control, *control.get('array', {}).get('overrides', [])):
                    variables.update(update['variable'] for update in item.get('binding_updates', []) if 'variable' in update)
    variables.discard(None)
    variables.discard('')
    if variables:
        result['variables'] = sorted(variables)
    return result


def batch_independent_edits(actions, controls, page_target):
    """Batch only independent leaf subtrees; retain geometry-before-style semantics."""
    owners = {action['action_id']: control for control in controls.values() for action in control['actions']
              if action['kind'] in ('control-geometry', 'control-properties')}
    def independent(first, second):
        a, b = first['row'], second['row']
        if a is None or b is None or a['children'] or b['children']:
            return False
        pa, pb = tuple(a['path']), tuple(b['path'])
        return (pa[:len(pb)] != pb and pb[:len(pa)] != pa
                and first['id'] not in second['dependencies'] and second['id'] not in first['dependencies'])
    output, index = [], 0
    while index < len(actions):
        current = owners.get(actions[index]['action_id'])
        if current is None or current['row'] is None or current['row']['children']:
            output.append(actions[index]); index += 1
            continue
        end, members, group = index, [], []
        while end < len(actions):
            owner = owners.get(actions[end]['action_id'])
            if owner is None or owner['row'] is None or owner['row']['children']:
                break
            if owner not in members:
                if not all(independent(owner, other) for other in members):
                    break
                members.append(owner)
            group.append(actions[end]); end += 1
        if len(members) < 2:
            output.extend(group)
        else:
            for kind in ('control-geometry', 'control-properties'):
                selected = [action for action in group if action['kind'] == kind]
                if len(selected) < 2:
                    output.extend(selected)
                    continue
                items = []
                for action in selected:
                    target = action['target']
                    if kind == 'control-geometry':
                        row = owners[action['action_id']]['row']
                        control_target = selector(row)
                    else:
                        # Property batches use RTTI, complete identity and the
                        # native path. The single-operation class alias is not a
                        # field in the native batch target protocol.
                        control_target = {key: value for key, value in target.items()
                                          if key not in ('page_id', 'page_name', 'class')}
                    items.append({'target': control_target, **copy.deepcopy(action['after'])})
                output.append({'action_id': selected[0]['action_id'], 'kind': kind + '-batch',
                               'target': copy.deepcopy(page_target), 'after': {'controls': items}})
        index = end
    return output


def native_bindings(row):
    if row is None:
        return None
    values = {key: row[key] for key in ('input_variable', 'button_phases') if key in row}
    if isinstance(row.get('bindings'), dict):
        values.update(row['bindings'])
    return values or None


def deferred_details(updates):
    for key, items in updates.items():
        require(isinstance(items, list) and all(isinstance(item, dict) for item in items)
                and (items or key in ('events', 'animations')), 'Expected ordered native edits for ' + key)
    return copy.deepcopy(updates)


def validate_button_alignment(class_name, updates):
    if class_name != 'CDrawButton' or not isinstance(updates, list):
        return
    alignments = {}
    for item in updates:
        fields(item, ('path', 'properties'))
        path = item.get('path', [])
        if not (isinstance(path, list) and len(path) == 1 and isinstance(path[0], dict)
                and path[0].get('occurrence', 0) == 0):
            continue
        state = path[0].get('native_key')
        if state not in ('抬起状态', '按下状态'):
            continue
        for prop in property_updates(item['properties']):
            key = prop.get('native_key')
            if key in ('水平对齐', '垂直对齐'):
                alignments.setdefault(key, {})[state] = prop
    for related in alignments.values():
        require('抬起状态' in related and related['抬起状态'] == related.get('按下状态'),
                'Standard Button alignment is shared: declare the same value for lift and press BasicProxy')


def compile_array(array, resolved, page, target, actions, base, snapshot, observed):
    fields(array, ('source', 'rows', 'columns', 'column_gap', 'row_gap', 'origin'), ('overrides',))
    source_id = identifier(array['source'])
    source = resolved.get(source_id)
    require(source is not None, 'Array source must name an earlier concrete control on this page')
    eligibility = source.get('clone_eligibility') or {}
    require(eligibility.get('eligible') is True,
            'Array source is not eligible for native clone in the current adapter: ' +
            str(eligibility.get('reason', 'missing current clone eligibility; recapture with the matching engine')))
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
    require(counts[0] * counts[1] * minimum_bytes <= CLR_MAX_LENGTH,
            'Array exceeds the native signed Int32 request length')
    step_x, step_y = width + gaps[0], height + gaps[1]
    last_x, last_y = origin[0] + (counts[1] - 1) * step_x, origin[1] + (counts[0] - 1) * step_y
    rectangle([min(origin[0], last_x), min(origin[1], last_y), max(origin[0], last_x) + width,
               max(origin[1], last_y) + height], page['resolution'], source['class'])
    overrides = {}
    require(isinstance(array.get('overrides', []), list), 'Array overrides must be a list')
    for edit in array.get('overrides', []):
        fields(edit, ('cell',), FOLLOWUP_DETAIL_KINDS)
        cell_row, cell_col = int_vector(edit['cell'], 2)
        cell = cell_row - 1, cell_col - 1
        require(0 <= cell[0] < counts[0] and 0 <= cell[1] < counts[1] and cell not in overrides,
                'Array override must identify one distinct 1-based row/column')
        updates = {key: value for key, value in edit.items() if key != 'cell'}
        validate_button_alignment(source['class'], updates.get('component_updates', []))
        immediate = {key: value for key, value in updates.items()
                     if 'existing' in source and key not in ('events', 'animations')}
        deferred = deferred_details({key: value for key, value in updates.items() if key not in immediate})
        overrides[cell] = immediate, deferred
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
            if (row, col) in overrides:
                immediate, deferred = overrides[row, col]
                if deferred:
                    cells[-1]['deferred_details'] = deferred
                if not immediate:
                    continue
                prototype = dict(observed[tuple(source['existing']['path'])])
                phases = source.get('details', {}).get('button_phases')
                if phases is not None:
                    prototype['button_phases'] = phases
                selected = result_selector(key, 'resulting_control')
                selected['control_path'] = native_result(key, 'resulting_control', 'path')
                compile_control_details(immediate, prototype, target, actions, cells[-1], snapshot,
                                        clone_target=selected)
    return cells


def overlaps(first, second):
    return max(first[0], second[0]) < min(first[2], second[2]) and max(first[1], second[1]) < min(first[3], second[3])
