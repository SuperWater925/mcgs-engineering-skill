"""Coordinate one Stu close-and-reopen operation through two completed UI requests."""

import hashlib
import re
import uuid


PROJECT_STATE = 'project-lifecycle-state'
CLOSE = 'project-close-clean'
OPEN = 'project-open-closed'
REOPEN = 'project-reopen'
READ_REOPEN = 'project-reopen-result'
WIRE_ACTIONS = (PROJECT_STATE, CLOSE, OPEN)


def confirmed(receipt, operation):
    if (receipt.get('ok') is not True or receipt.get('native_result_may_be_partial') is True
            or receipt.get('native_outcome_unknown') is True):
        return False
    state = receipt.get('state_after')
    if not isinstance(state, dict) or state.get('roots_agree') is not True:
        return False
    closing = operation == CLOSE
    flags = ('close_entered', 'close_returned', 'close_confirmed_empty') if closing else (
        'open_entered', 'open_returned', 'open_confirmed_same_project')
    return (receipt.get('lifecycle_state') == ('closed' if closing else 'open')
            and all(receipt.get(key) is True for key in flags)
            and state.get('current_root_present') is (not closing)
            and state.get('canonical_root_present') is (not closing)
            and state.get('open_in_progress') is False
            and (closing or state.get('verified_same_project') is True))


def execute(args, project, connection, layout, queue, client):
    start = args.command == REOPEN
    job = args.id or 'stu-reopen-' + uuid.uuid4().hex
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', job) or job.upper() in client.RESERVED:
        raise ValueError('Invalid Stu reopen ID')
    target = layout.runtime_root / 'stu-reopen' / (job + '.json')
    plan_path = queue.owned_file(target, not start)
    requests = {}
    submitted = {}
    for phase, operation in (('close', CLOSE), ('open', OPEN)):
        request_id = f'{job}-{phase}'
        request = connection.request(operation, project)
        if phase == 'close':
            request['verify_reopen'] = True
        digest = hashlib.sha256(queue.request_bytes(request, request_id, client=client)).hexdigest()
        requests[phase] = request
        submitted[phase] = {'request_id': request_id, 'request_sha256': digest}

    plan = {'schema': 1, 'operation_id': job, 'project': str(project), 'scope_sha256': connection.scope_sha,
            'engine_sha256': connection.engine_sha, 'requests': submitted}
    if start:
        queue.write_new(plan_path, plan)
    else:
        stored, _ = queue.read_json(plan_path)
        if stored != plan:
            raise ValueError('The saved Stu reopen operation refers to a different project or connection')

    def observe(phase):
        step = submitted[phase]
        request_id, digest = step['request_id'], step['request_sha256']
        reservation = layout.runtime_root / 'client-submissions' / (request_id + '.json')
        if not queue.owned_file(reservation, False).is_file():
            return {'ok': False, 'status': 'not_submitted', **step}
        result = queue.read_existing_result(request_id, digest)
        if result.get('ok') is True:
            return connection.verify_receipt(result['result'], project, requests[phase])
        return result

    def send(phase):
        step = submitted[phase]
        try:
            result = queue.submit(requests[phase], step['request_id'], args.timeout)
        except (client.SubmissionError, client.QueueTimeout) as error:
            return {'ok': False, 'status': 'submission_or_response_unknown', 'error': str(error),
                    'transport_state': error.state, **step}
        return connection.verify_receipt(result, project, requests[phase])

    report = {'ok': False, 'operation_id': job, 'project': str(project), 'journal': str(plan_path),
              'requests': submitted, 'automatic_retry': False}
    close = send('close') if start else observe('close')
    report['close'] = close
    if not confirmed(close, CLOSE):
        report['status'] = 'close_not_confirmed'
        return report

    opened = observe('open')
    if opened.get('status') == 'not_submitted' and (start or args.continue_open):
        opened = send('open')
    report['open'] = opened
    report['ok'] = confirmed(opened, OPEN)
    report['status'] = 'same_project_reopened' if report['ok'] else 'open_not_confirmed'
    return report

