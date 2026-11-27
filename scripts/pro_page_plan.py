"""Prepare a native engineering program or render its independent comparison."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets/pro-native-bridge/client'))

from page_plan import compile_design, compile_page_setup, normalize_receipts, record_viewports
from page_plan import (DESIGN, REVIEW, SNAPSHOT, FOLLOWUP_DETAIL_KINDS, fields, forest_paths, path_key,
                       require, require_native_length, selector)
from page_readback_report import applied_objects, match_control, render_review
from page_group_plan import compile_groups, inspect_groups, report_groups
from project_plan import compile_project, json_bytes, report_readback


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, content):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(content)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n'


def followup_targets(request, review, snapshot, receipts):
    fields(request, ('review_id', 'updates'), ('save', 'expected_reference_edges', 'native_derived_cache_contract'))
    require(review.get('schema') == REVIEW and snapshot.get('schema') == SNAPSHOT
            and request['review_id'] == review['review_id'] and bool(request['review_id']),
            'Follow-up must identify the original review')
    project = review['project_path']
    generation = ('process_id', 'creation_filetime', 'native_thread_id', 'editor_image_sha256', 'root')
    require(path_key(snapshot['actual_project']) == path_key(project) and
            all(review.get(key) is not None and review[key] == snapshot.get(key) for key in generation),
            'Follow-up requires a fresh capture of the same project generation')
    for receipt in receipts:
        inspection = receipt.get('direct_inspection') or {}
        require(path_key(receipt.get('actual_project') or inspection.get('actual_project')) == path_key(project)
                and all(review[key] == inspection.get(key) for key in generation),
                'Creation receipt belongs to another project or editor generation')
    planned = {action['id']: action for action in review['actions']}
    objects = applied_objects(receipts, planned)
    require(isinstance(request['updates'], list) and request['updates'], 'Provide follow-up updates')
    original_pages = {control['result_action']: page for page in review['pages']
                      for control in page['controls'] if 'result_action' in control}
    fresh_pages = {page['id']: page for page in snapshot['pages']}
    forests = {}
    seen = set()
    targets = []
    for update in request['updates']:
        fields(update, ('id', 'result_action'), ('binding_updates', 'component_updates', 'button_changes',
                                                'events', 'animations', 'depends_on'))
        action = update['result_action']
        require(action in objects, 'Missing successful creation or clone receipt')
        page_id = planned[action]['page_id']
        original = original_pages.get(action)
        fresh = fresh_pages.get(page_id)
        require(original and fresh and original['id'] == page_id
                and all(fresh[key] == original[key] for key in ('name', 'complete', 'document')),
                'Follow-up page identity differs')
        if page_id not in forests:
            rows = forest_paths(fresh['forest'], fresh['document']).values()
            by_complete = {row['complete']: row for row in rows}
            require(len(by_complete) == len(rows), 'Fresh capture repeats a complete native object')
            forests[page_id] = by_complete
        candidate = forests[page_id].get(objects[action].get('complete'))
        row = match_control([candidate] if candidate is not None else [], objects[action], True)
        require(row is not None, 'Fresh capture must identify the exact returned object uniquely')
        identity = page_id, row['complete']
        require(identity not in seen, 'Follow-up repeats the same returned object')
        seen.add(identity)
        targets.append((update, fresh, row))
    return targets


def followup_design(request, review, snapshot, receipts):
    pages = {}
    for update, fresh, row in followup_targets(request, review, snapshot, receipts):
        page_id = fresh['id']
        page = pages.setdefault(page_id, {key: fresh[key] for key in ('id', 'name', 'resolution')})
        layer = page.setdefault('layers', [{'id': 'followup', 'controls': []}])[0]
        layer['controls'].append({**{key: value for key, value in update.items() if key != 'result_action'},
                                  'existing': {key: row[key] for key in ('path', 'class', 'name', 'native_id', 'complete')}})
    return {'schema': DESIGN, 'project_path': review['project_path'], 'pages': list(pages.values()),
            'save': request.get('save', False),
            **{key: request[key] for key in ('expected_reference_edges', 'native_derived_cache_contract')
               if key in request}}


def followup_inspection(request, review, snapshot, receipts):
    actions = []
    compiled = set(snapshot['compiled_kinds'])

    def append(kind, target, after=None):
        # Read-only catalogs are routed separately from editable action kinds.
        require(kind == 'data-catalog' or kind in compiled, 'Current engine cannot inspect ' + kind)
        action = {'action_id': f'{kind}-{len(actions) + 1}', 'kind': kind, 'target': target}
        if after is not None:
            action['after'] = after
        actions.append(action)

    needs_data = False
    for update, page, row in followup_targets(request, review, snapshot, receipts):
        target = {'page_id': page['id'], 'page_name': page['name'], **selector(row), 'rtti': row['rtti']}
        for field, kind in FOLLOWUP_DETAIL_KINDS.items():
            if field not in update:
                continue
            if field == 'binding_updates':
                properties = [{key: prop[key] for key in ('native_key', 'native_type_tag', 'value')}
                              for prop in update[field]]
                append(kind, target, {'properties': properties})
                needs_data |= any('variable' in prop for prop in update[field])
            elif field == 'component_updates':
                for component in update[field]:
                    append(kind, {**target, 'component_path': component['path']},
                           {'properties': component['properties']})
            else:
                # The original event reader expects an empty template lookup.
                append(kind, target, {'events': []} if field == 'events' else None)
                if field == 'animations':
                    needs_data |= any('binding' in (item.get('fields') or {}) for item in update[field])
    require(actions, 'Provide native control details to inspect')
    if needs_data:
        append('data-catalog', {})
    specification = {'commit': False, 'actions': actions}
    require_native_length(specification)
    return specification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    compile_command = commands.add_parser('compile')
    compile_command.add_argument('--design', required=True)
    compile_command.add_argument('--snapshot', required=True)
    compile_command.add_argument('--program', required=True, type=Path)
    compile_command.add_argument('--review', required=True, type=Path)
    for mode in ('followup-inspect', 'followup'):
        followup = commands.add_parser(mode)
        followup.add_argument('--updates')
        followup.add_argument('--review', required=True)
        followup.add_argument('--snapshot', required=True)
        followup.add_argument('--receipts', required=True, nargs='+')
        followup.add_argument('--out', required=True, type=Path)
    setup = commands.add_parser('prepare-pages')
    setup.add_argument('--design', required=True)
    setup.add_argument('--snapshot', required=True)
    setup.add_argument('--program', required=True, type=Path)
    group_inspect = commands.add_parser('group-inspect')
    group_inspect.add_argument('--design', required=True)
    group_inspect.add_argument('--out', required=True, type=Path)
    groups = commands.add_parser('prepare-groups')
    groups.add_argument('--design', required=True)
    groups.add_argument('--capture', required=True)
    for output in ('program', 'readback', 'review'):
        groups.add_argument('--' + output, required=True, type=Path)
    group_report = commands.add_parser('group-report')
    group_report.add_argument('--review', required=True)
    group_report.add_argument('--capture', required=True)
    group_report.add_argument('--out', required=True, type=Path)
    capture = commands.add_parser('snapshot')
    capture.add_argument('--receipts', required=True, nargs='+')
    capture.add_argument('--viewport')
    capture.add_argument('--out', required=True, type=Path)
    report = commands.add_parser('report')
    report.add_argument('--review', required=True)
    report.add_argument('--snapshot')
    report.add_argument('--receipts', nargs='+', default=[])
    report.add_argument('--evidence')
    report.add_argument('--out', required=True, type=Path)
    project = commands.add_parser('project')
    project.add_argument('--design', required=True)
    project.add_argument('--program', required=True, type=Path)
    project.add_argument('--readback', required=True, type=Path)
    project.add_argument('--review', required=True, type=Path)
    project_report = commands.add_parser('project-report')
    project_report.add_argument('--review', required=True)
    project_report.add_argument('--readback-session', required=True, type=Path)
    project_report.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'snapshot':
        snapshot = normalize_receipts(read(path) for path in args.receipts)
        if args.viewport:
            record_viewports(snapshot, read(args.viewport))
        write(args.out, encoded(snapshot))
    elif args.command == 'compile':
        if args.program.resolve() == args.review.resolve() or args.program.exists() or args.review.exists():
            raise ValueError('Choose distinct new paths for program and review')
        program, review = compile_design(read(args.design), read(args.snapshot))
        if program['steps']:
            write(args.program, encoded(program))
        write(args.review, encoded(review))
        print(encoded({'actions': len(review['actions']), 'program_written': bool(program['steps']),
                       **({'deferred_updates': len(review['deferred_updates'])} if 'deferred_updates' in review else {}),
                       'native_execution_performed': False}))
    elif args.command in ('followup-inspect', 'followup'):
        snapshot = read(args.snapshot)
        review = read(args.review)
        request = (read(args.updates) if args.updates else
                   {'review_id': review['review_id'], 'updates': review.get('deferred_updates', [])})
        receipts = [read(path) for path in args.receipts]
        if args.command == 'followup-inspect':
            output = followup_inspection(request, review, snapshot, receipts)
        else:
            output = followup_design(request, review, snapshot, receipts)
            compile_design(output, snapshot)
        write(args.out, encoded(output))
    elif args.command == 'prepare-pages':
        program = compile_page_setup(read(args.design), read(args.snapshot))
        write(args.program, encoded(program))
        print(encoded({'actions': len(program['steps'][0]['specification']['actions']),
                       'native_execution_performed': False, 'recapture_after_setup': True}))
    elif args.command == 'group-inspect':
        write(args.out, encoded(inspect_groups(read(args.design))))
    elif args.command == 'prepare-groups':
        paths = (args.program, args.readback, args.review)
        require(len({path.resolve() for path in paths}) == len(paths) and not any(path.exists() for path in paths),
                'Choose three distinct new paths for the group program, readback and review')
        outputs = [encoded(value) for value in compile_groups(read(args.design), read(args.capture))]
        for path, content in zip(paths, outputs):
            write(path, content)
        print(encoded({'native_execution_performed': False, 'fresh_readback_required': True}))
    elif args.command == 'group-report':
        result = report_groups(read(args.review), read(args.capture))
        write(args.out, encoded(result))
        return 0 if result['business_readback_passed'] else 1
    elif args.command == 'project':
        paths = (args.program, args.readback, args.review)
        require(len({path.resolve() for path in paths}) == len(paths) and not any(path.exists() for path in paths),
                'Choose three distinct new paths for the program, readback and review')
        outputs = compile_project(read(args.design))
        contents = [json_bytes(value) for value in outputs]
        for path, data in zip(paths, contents):
            with path.open('xb') as stream:
                stream.write(data)
        print(encoded({'native_execution_performed': False, 'domains': list(outputs[2]['scopes']),
                       'edit_steps': len(outputs[0]['steps']), 'readback_steps': len(outputs[1]['steps'])}))
    elif args.command == 'project-report':
        result = report_readback(read(args.review), args.readback_session)
        write(args.out, encoded(result))
        return 0 if result['business_readback_passed'] else 1
    else:
        write(args.out, render_review(read(args.review), read(args.snapshot) if args.snapshot else None,
                                      [read(path) for path in args.receipts],
                                      read(args.evidence) if args.evidence else None))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
