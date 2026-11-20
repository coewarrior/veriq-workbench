"""Report writes retain original ownership independently of account occupancy."""
import copy
import pytest
from api_test_tool import ui_records
from api_test_tool.orchestration import Conflict
from test_native_finalization import prepare, browser_environment


def released(tmp_path, outcome='yield'):
    c, service, owner, project, tid, saved = prepare(tmp_path)
    node = c.snapshot(owner)['nodes'][0]
    identity = dict(task_id=tid, node_id=node['id'], holder_id='worker',
                    executor_ref='thread:01a17111-5ac7-79d0-9ac8-48eaaddc22b8')
    claim = service.direct.call(owner, {**identity, 'action': 'claim',
        'arguments': {'browser_environment': browser_environment('context', True)}})
    context = service.direct.call(owner, {**identity, 'action': 'context', 'lease_id': claim['lease_id']})
    project = context['project']; record = context['record']
    saved = service.direct.call(owner, {**identity, 'lease_id': claim['lease_id'], 'action': 'record',
        'record_action': 'cases', 'arguments': {'revision': record['revision'],
            'cases': [{'case_id': 'A', 'scenario': 'observed prerequisite', 'status': 'not_run'}]}})
    current = c.snapshot(owner)['nodes'][0]
    identity.update(dispatch_id=current['executor_dispatch']['dispatch_id'], lease_id=claim['lease_id'])
    service.direct.call(owner, {**identity, 'action': 'finish', 'outcome': outcome,
        'reason': 'Original pages actually closed', 'arguments': {'browser_stopped': True,
            **({'report_pending': True} if outcome == 'completed' else {})}})
    args = {**identity, 'action': 'record', 'record_action': 'cases', 'arguments': {
        'project_id': project['id'], 'execution_id': saved['execution_id'], 'revision': saved['revision'],
        'cases': [{'case_id': 'A', 'actual': 'Original observed correction'}]}}
    return c, service, owner, args


@pytest.mark.parametrize('state', ['queued', 'stopped', 'paused', 'completed', 'blocked'])
def test_original_observations_save_without_reacquiring_or_changing_control(tmp_path, state):
    c, service, owner, args = released(tmp_path)
    with c.transaction() as (_, raw):
        raw['nodes'][args['node_id']]['state'] = state
        if state in {'stopped', 'paused'}:
            raw['nodes'][args['node_id']]['control_intent'] = 'stop' if state == 'stopped' else 'pause'
            raw['nodes'][args['node_id']]['revision'] += 1
    saved = service.direct.call(owner, args)
    assert saved['revision'] == args['arguments']['revision'] + 1
    snapshot = c.snapshot(owner)
    assert not snapshot['leases'] and snapshot['nodes'][0]['state'] == state
    with pytest.raises((Conflict, ValueError)):
        service.direct.call(owner, args)  # Original revision is still CAS-fenced.


def test_same_dispatch_reclaim_does_not_revoke_old_observation_write(tmp_path):
    c, service, owner, args = released(tmp_path)
    new = service.direct.call(owner, {**{k: args[k] for k in ('task_id','node_id','holder_id','dispatch_id','executor_ref')},
        'action': 'claim', 'arguments': {'browser_environment': browser_environment('context2', True)}})
    assert new['lease_id'] != args['lease_id']
    saved = service.direct.call(owner, args)
    assert saved['revision'] == args['arguments']['revision'] + 1
    assert c.snapshot(owner)['leases'][0]['id'] == new['lease_id']


@pytest.mark.parametrize('change', ['successor', 'dispatch', 'executor', 'record', 'wrong_task', 'wrong_caller'])
def test_replaced_report_writer_cannot_modify_original_record(tmp_path, change):
    c, service, owner, args = released(tmp_path, 'completed')
    with c.transaction() as (_, raw):
        node = raw['nodes'][args['node_id']]
        if change == 'successor': node['record_successor_node_id'] = 'next'
        if change == 'dispatch': node['executor_dispatch']['dispatch_id'] = 'new-dispatch'
        if change == 'executor': node['executor_dispatch']['executor_ref'] = 'other-worker'
        if change == 'record': node['record_execution_id'] = 'new-record'
    if change == 'wrong_task': args['task_id'] = 'foreign'
    if change == 'wrong_caller': args['executor_ref'] = 'other-worker'
    with pytest.raises((Conflict, PermissionError)):
        service.direct.call(owner, args)
    record = ui_records.load(c.store, owner, args['arguments']['project_id'], args['arguments']['execution_id'])
    assert record['revision'] == args['arguments']['revision']


@pytest.mark.parametrize('reclaim', [False, True])
def test_report_correction_permission_does_not_allow_publishing_unfinished_node(tmp_path, reclaim):
    c, service, owner, args = released(tmp_path)
    if reclaim:
        service.direct.call(owner, {**{k: args[k] for k in ('task_id','node_id','holder_id','dispatch_id','executor_ref')},
            'action': 'claim', 'arguments': {'browser_environment': browser_environment('context2', True)}})
    with pytest.raises(Conflict, match='report_not_settled'):
        service.direct.call(owner, {**args, 'record_action': 'publish'})


def test_report_writer_rechecked_inside_write_transaction(tmp_path, monkeypatch):
    from api_test_tool.native_execution import NativeExecution
    c, service, owner, args = released(tmp_path, 'completed')
    original = NativeExecution.record_after_release
    def replaced(native, *params):
        with c.transaction() as (_, raw):
            raw['nodes'][args['node_id']]['record_successor_node_id'] = 'new-writer'
        return original(native, *params)
    monkeypatch.setattr(NativeExecution, 'record_after_release', replaced)
    with pytest.raises(Conflict): service.direct.call(owner, args)
    assert ui_records.load(c.store, owner, args['arguments']['project_id'], args['arguments']['execution_id'])['revision'] == args['arguments']['revision']
