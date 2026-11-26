"""Compose native engineering sessions and verify fresh business preimages."""

from hashlib import sha256
import json
from pathlib import Path
import re

from page_plan import fields, identifier, path_key, require, require_native_length

DESIGN = 'mcgs-project-design/v1'
REVIEW = 'mcgs-project-plan-review/v1'
PURPOSE = 'native-engineering-session-program'
DOMAINS = ('pages', 'data', 'strategies', 'recipes', 'pictures', 'languages', 'devices', 'references')
FLUSH = {
    'page-flush', 'main-control-flush', 'data-flush', 'strategy-flush', 'strategy-working-flush',
    'strategy-trigger-context-flush', 'recipe-flush', 'device-flush', 'device-tree-flush',
    'picture-flush', 'language-flush',
}
LIFECYCLE = {'project-close-reopen', 'project-check-original-root85'}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')


def read_json(raw):
    return json.loads(raw.decode('utf-8-sig'))


def action_list(spec, inspection=False):
    require(isinstance(spec, dict), 'Each native step needs a specification object')
    require(spec.get('commit', False) is False and 'save_scope' not in spec and 'root_save' not in spec
            and 'trial_id' not in spec, 'Use the project persistence section and let staging assign trial IDs')
    actions = spec.get('actions')
    require(isinstance(actions, list) and actions, 'Each native step needs a nonempty action list')
    seen = set()
    for action in actions:
        fields(action, ('action_id', 'kind', 'target'), ('after', 'source', 'depends_on'))
        name = action['action_id']
        kind = action['kind']
        require(isinstance(name, str) and re.fullmatch('[A-Za-z0-9_-]{1,80}', name) and name not in seen,
                'Native action IDs must be unique within a step')
        seen.add(name)
        require(isinstance(kind, str) and re.fullmatch('[a-z][a-z0-9-]{0,79}', kind)
                and kind not in LIFECYCLE, 'Use a compiled business action kind')
        require(isinstance(action['target'], dict) and
                (inspection and 'after' not in action or isinstance(action.get('after'), dict)),
                'Use a target object and provide an after object for edits')
    require_native_length(spec)
    return actions


def session_program(project, steps):
    return {'schema': 1, 'purpose': PURPOSE, 'project_path': project, 'steps': steps}


def compile_project(design):
    fields(design, ('schema', 'project_path', 'sections', 'checks'), ('persistence',))
    require(design['schema'] == DESIGN, 'Unsupported project design schema')
    project = design['project_path']
    project_key = path_key(project)
    sections, checks = design['sections'], design['checks']
    require(isinstance(sections, list) and sections and isinstance(checks, list) and checks,
            'Provide business edit sections and separate native readback checks')
    steps, scopes, seen = [], {}, set()
    for section in sections:
        fields(section, ('domain', 'program'))
        domain, fragment = section['domain'], section['program']
        require(domain in DOMAINS and domain not in scopes, 'Choose a unique project domain')
        fields(fragment, ('schema', 'purpose', 'project_path', 'steps'))
        require(fragment['schema'] == 1 and fragment['purpose'] == PURPOSE
                and path_key(fragment['project_path']) == project_key, 'Fragment belongs to another project')
        require(isinstance(fragment['steps'], list) and fragment['steps'], 'Fragment must contain steps')
        scopes[domain] = []
        for step in fragment['steps']:
            fields(step, ('step_id', 'specification'), ('mode', 'description'))
            step_id = identifier(step['step_id'])
            mode = step.get('mode', 'edit')
            require(step_id not in seen and mode in ('edit', 'inspect'), 'Repeated step ID or invalid mode')
            actions = action_list(step['specification'], mode == 'inspect')
            require(all(not action['kind'].endswith('-flush') for action in actions),
                    'Move all flush actions to the final persistence section')
            seen.add(step_id)
            scopes[domain].extend(action['kind'] for action in actions)
            steps.append(step)

    persistence = design.get('persistence')
    saves = []
    if persistence is not None:
        fields(persistence, ('flush', 'root_save'))
        flush = persistence['flush']
        require(isinstance(flush, list) and type(persistence['root_save']) is bool,
                'Provide explicit module flushes and a Boolean root_save')
        written = set()
        for item in flush:
            fields(item, ('kind', 'target'))
            require(item['kind'] in FLUSH and isinstance(item['target'], dict),
                    'Use a known module flush and the original native selector')
            key = (item['kind'], json.dumps(item['target'], sort_keys=True, allow_nan=False))
            require(key not in written, 'A native module flush was repeated')
            written.add(key)
            saves.append(item)
        if persistence['root_save']:
            saves.append({'kind': 'root-flush', 'target': {}})
    # Separate steps allow the existing runner to merge supported save combinations.
    for index, save in enumerate(saves, 1):
        name = f'persist-{index}'
        require(name not in seen, 'Step ID conflicts with final persistence')
        steps.append({'step_id': name, 'specification': {'commit': False, 'actions': [
            dict(save, action_id=name, after={})]}})

    require(any(step.get('mode', 'edit') == 'edit' for step in steps), 'Project plan has no edit step')
    readback = []
    checked = set()
    seen_checks = set()
    for check in checks:
        fields(check, ('id', 'domain', 'selector', 'expected'))
        name, domain = identifier(check['id']), check['domain']
        require(domain in scopes and name not in seen_checks, 'Readback must identify a planned domain and unique ID')
        selector = check['selector']
        fields(selector, ('kind', 'target'), ('after',))
        action = dict(selector, action_id=name)
        specification = {'commit': False, 'actions': [action]}
        action_list(specification, inspection=True)
        require(not action['kind'].endswith('-flush'), 'Select an independent native readback')
        expected = check['expected']
        require(isinstance(expected, list) and expected, 'Choose business fields to compare')
        pointers = set()
        for item in expected:
            fields(item, ('pointer', 'value'))
            pointer = item['pointer']
            require(isinstance(pointer, str) and pointer.startswith('/')
                    and not re.search(r'~(?![01])', pointer) and pointer not in pointers,
                    'Use unique JSON Pointers relative to the captured before object')
            pointers.add(pointer)
        readback.append({'step_id': name, 'mode': 'inspect', 'specification': specification})
        seen_checks.add(name)
        checked.add(domain)
    require(checked == scopes.keys(), 'Provide at least one independent readback per planned domain')
    edit = session_program(project, steps)
    verify = session_program(project, readback)
    review = {'schema': REVIEW, 'project_path': project, 'scopes': scopes, 'persistence': saves,
              'edit_sha256': sha256(json_bytes(edit)).hexdigest(),
              'readback_sha256': sha256(json_bytes(verify)).hexdigest(), 'checks': checks}
    return edit, verify, review


def pointer_value(value, pointer):
    for token in pointer.split('/')[1:]:
        key = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list) and re.fullmatch(r'0|[1-9][0-9]*', key):
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise KeyError(key)
    return value


def report_readback(review, session):
    require(review.get('schema') == REVIEW, 'Unsupported project review')
    project_key = path_key(review['project_path'])
    session = Path(session)

    def read(name):
        return read_json((session / name).read_bytes())

    manifest, status = read('manifest.json'), read('execution-result.json')
    staged_bytes = (session / 'program.json').read_bytes()
    staged = read_json(staged_bytes)
    require(manifest['purpose'] == PURPOSE and path_key(manifest['project_path']) == project_key
            and manifest['source_program_sha256'] == review['readback_sha256']
            and manifest['program_sha256'] == sha256(staged_bytes).hexdigest()
            and staged['purpose'] == PURPOSE and path_key(staged['project_path']) == project_key
            and len(staged['steps']) == len(review['checks'])
            and status['session_id'] == manifest['session_id'] and status['execution_mode'] == 'direct',
            'Use the independent readback session generated by this project review')
    outcomes = []
    for index, check in enumerate(review['checks'], 1):
        name = identifier(check['id'])
        result = {'id': name, 'domain': check['domain'], 'status': 'unverified', 'fields': []}
        outcomes.append(result)
        if name not in status['completed_steps']:
            continue
        prefix = f'{index:04d}-{name}'
        specification = (session / (prefix + '-specification.json')).read_bytes()
        expected_spec = {'commit': False, 'actions': [dict(check['selector'], action_id=name)]}
        step = staged['steps'][index - 1]
        begin = read(prefix + '-begin.json')
        receipt = read(prefix + '-inspect.json')
        rows = receipt.get('action_preimages', [])
        expected_id = f"eng_{manifest['session_id']}_{index - 1:04d}_read"
        valid = (step['step_id'] == begin['step_id'] == name and step['mode'] == 'inspect'
                 and step['specification'] == read_json(specification) == expected_spec
                 and begin['specification_sha256'] == sha256(specification).hexdigest()
                 and receipt.get('ok') is True and receipt.get('op') == 'engineering-edit-inspect'
                 and receipt.get('write_attempted') is False and receipt.get('request_id') == expected_id
                 and receipt.get('actual_project') and path_key(receipt['actual_project']) == project_key
                 and receipt.get('engineering_delivery_scope_sha256') == manifest['engineering_delivery_scope_sha256']
                 and len(rows) == 1 and rows[0]['action_id'] == name
                 and all(rows[0].get(key) == check['selector'][key] for key in ('kind', 'target')))
        if not valid:
            continue
        for item in check['expected']:
            row = dict(item, matched=False)
            result['fields'].append(row)
            try:
                row['actual'] = pointer_value(rows[0]['before'], item['pointer'])
            except (KeyError, IndexError):
                continue
            # Serialized form keeps JSON booleans distinct from numbers.
            row['matched'] = json.dumps(row['actual'], sort_keys=True) == json.dumps(item['value'], sort_keys=True)
        result['status'] = 'matched' if all(row['matched'] for row in result['fields']) else 'different'
    return {'schema': 'mcgs-project-readback/v1', 'project_path': review['project_path'],
            'business_readback_passed': status.get('ok') is True
            and all(item['status'] == 'matched' for item in outcomes),
            'checks': outcomes, 'file_readback': 'unverified', 'native_project_check': 'unverified',
            'close_reopen': 'unverified', 'simulation': 'unverified'}
