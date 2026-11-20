"""The real source-plan -> stage preview -> fresh claim chain, in a private store."""
import copy

import pytest

from api_test_tool import ui_records
from test_native_finalization import prepare
from test_native_contexts import environment
from test_execution_work_plan import unit


def source(tmp_path, monkeypatch):
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report', lambda *a: {'status': 'disabled'})
    c, service, owner, project, tid, saved = prepare(tmp_path)
    with c.transaction() as (_, state):
        state['tasks'][tid]['native_browser_policy'] = 'direct_isolated'
    identity = {'task_id': tid, 'holder_id': 'original-worker',
                'executor_ref': '01a17111-5ac7-79d0-9ac8-48eaaddc22b8',
                'coordinator_ref': '01a17111-5ac7-79d0-9ac8-48eaaddc22b9'}
    env = {**environment('old-context', True), 'browser': 'chromium'}
    claimed = service.direct.call(owner, {**identity, 'action': 'claim',
        'arguments': {'browser_environment': env}})
    node = next(n for n in c.snapshot(owner)['nodes'] if n['id'] == claimed['node_id'])
    identity.update(node_id=node['id'], lease_id=claimed['lease_id'],
                    dispatch_id=node['executor_dispatch']['dispatch_id'])
    context = service.direct.call(owner, {**identity, 'action': 'context'})
    service.direct.call(owner, {**identity, 'action': 'record', 'record_action': 'cases',
        'arguments': {'revision': context['record']['revision'],
            'cases': [{'case_id': 'A', 'scenario': 'Original creation', 'status': 'not_run'}]}})
    context = service.direct.call(owner, {**identity, 'action': 'context'})
    return c, service, owner, identity, context


def continue_source(tmp_path, monkeypatch, outcome='completed'):
    c, service, owner, identity, context = source(tmp_path, monkeypatch)
    before = copy.deepcopy(context['record'])
    finished = service.direct.call(owner, {**identity, 'action': 'finish',
        'outcome': outcome, 'reason': 'Original browser actually exited',
        'arguments': {'browser_stopped': True, 'publish_saved': True,
            'publication_binding': {'project_id': context['project']['id'],
                'execution_id': before['id'], 'revision': before['revision']}}})
    assert finished['publication']['phase'] == 'published'
    aid = c.snapshot(owner)['accounts'][0]['id']
    plan = {'schema_version': 1, 'project_id': context['project']['id'],
            'execution_id': before['id'], 'units': [unit('remaining', ['B'], [aid])]}
    result = service.direct.call(owner, {**identity, 'action': 'work_plan',
        'arguments': {'work_plan': plan}})
    assignment = result['continuation_packet']['assignment']
    assert assignment['node_id'] == identity['node_id']
    assert assignment['dispatch_id'] != identity['dispatch_id']
    assert not next(n for n in c.snapshot(owner)['nodes'] if n['id'] == identity['node_id']).get('record_successor_node_id')
    claim = {k: assignment[k] for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')}
    claim['arguments'] = assignment['claim_arguments']
    return c, service, owner, identity, context, before, claim


@pytest.mark.parametrize('outcome', ['completed', 'blocked'])
def test_formal_continuation_prepares_before_real_environment_registration(tmp_path, monkeypatch, outcome):
    c, service, owner, original, context, before, claim = continue_source(tmp_path, monkeypatch, outcome)
    ready = service.direct.call(owner, {**claim, 'action': 'context'})
    assert ready['stage_ready'], 'An exited source must allow its original worker to prepare the new context'
    assert ready['required_context_count'] == 1
    assert not c.snapshot(owner)['leases']
    # A preparation allowance must never turn the old closed context into capacity.
    with pytest.raises(ValueError, match='environment_setup'):
        service.direct.call(owner, {**claim, 'action': 'claim'})
    assert not c.snapshot(owner)['leases']
    env = {**environment('new-context', True), 'browser': 'chromium'}
    claimed = service.direct.call(owner, {**claim, 'action': 'claim',
        'arguments': {**claim['arguments'], 'browser_environment': env}})
    assert claimed['lease_id']
    assert len(c.snapshot(owner)['leases']) == 1
    result = service.direct.call(owner, {**claim, 'action': 'context', 'lease_id': claimed['lease_id']})
    assert result['record']['id'] == before['id']
    assert result['record']['cases'] == before['cases']
    assert result['record']['revision'] == before['revision']
    current = next(n for n in c.snapshot(owner)['nodes'] if n['id'] == original['node_id'])
    assert current['state'] == 'running' and not current.get('native_browser_stopped')
    assert current['executor_dispatch_history'][-1]['exit_acknowledged_at']
    assert current['attempts'][0]['lease_id'] == original['lease_id']


@pytest.mark.parametrize('change', ['no_exit', 'source_dispatch', 'source_lease', 'stop', 'live_source'])
def test_preparation_does_not_borrow_foreign_or_unexited_source(tmp_path, monkeypatch, change):
    c, service, owner, original, _, _, claim = continue_source(tmp_path, monkeypatch)
    with c.transaction() as (_, state):
        old, node = state['nodes'][original['node_id']], state['nodes'][claim['node_id']]
        if change == 'no_exit': old['native_browser_stopped'] = False
        if change == 'source_dispatch': old['executor_dispatch_history'][-1]['executor_ref'] = 'other-worker'
        if change == 'source_lease': node['executor_dispatch']['resumed_from_lease_id'] = 'foreign-lease'
        if change == 'stop': old['control_intent'] = 'stop'
        if change == 'live_source':
            state['leases']['unexpected-source'] = {'id': 'unexpected-source', 'node_id': old['id'],
                'account_ids': [], 'native_browser': True, 'mode': 'exclusive', 'revoked': False}
    if change == 'stop':
        from api_test_tool.orchestration import Conflict
        with pytest.raises(Conflict, match='task_not_running'):
            service.direct.call(owner, {**claim, 'action': 'context'})
        return
    ready = service.direct.call(owner, {**claim, 'action': 'context'})
    assert not ready['stage_ready']


def test_independent_cleanup_case_can_reference_original_creation_responsibility(tmp_path, monkeypatch):
    from test_cleanup_event_contract import capability, register
    from api_test_tool.cleanup_capabilities import settle_units
    c, service, owner, identity, context = source(tmp_path, monkeypatch)
    pid, eid = context['project']['id'], context['record']['id']
    c.store.update_project(owner, pid, {'ui_execution_permission': {'key': 'full'}})
    aid = c.snapshot(owner)['leases'][0]['account_ids'][0]
    service.direct.call(owner, {**identity, 'action': 'cleanup',
        'arguments': {'events': [capability(aid), register(aid)]}})
    plan = {'schema_version': 1, 'project_id': pid, 'execution_id': eid,
        'units': [unit('cleanup', ['B'], [aid], purpose='cleanup', cleanup_responsibility_ids=['object-a'])]}
    result = service.direct.call(owner, {**identity, 'action': 'work_plan', 'arguments': {'work_plan': plan}})
    assert result['saved']
    with c.transaction() as (_, state):
        node = state['nodes'][identity['node_id']]
        assert not node.get('work_unit_receipts', {}).get('cleanup', {}).get('completed')
        obj = state['cleanup_objects']['object-a']
        assert obj['case_id'] == 'A'
        obj['state'] = 'cleaned'  # Fixture evidence; no business operation is performed.
        settle_units(state, node, c.clock())
        assert node['work_unit_receipts']['cleanup']['completed']
        obj['source_node_id'] = 'foreign-module'
        settle_units(state, node, c.clock())
        assert not node['work_unit_receipts']['cleanup']['completed']
    with pytest.raises(PermissionError):
        service.direct.call(owner, {**identity, 'action': 'work_plan', 'arguments': {'work_plan': plan}})


def test_resolved_blocker_returns_model_review_without_changing_case_result():
    from api_test_tool.ui_dependencies import plan
    record = {'cases': [{'case_id': 'A', 'status': 'blocked', 'actual': 'original service unavailable',
        'dependencies': [{'id': 'service', 'key': 'service', 'kind': 'network', 'title': 'service',
                          'scope': {}}]}],
        'dependency_checks': {'service': {'status': 'ready', 'observed': 'Original service restored'}}}
    before = copy.deepcopy(record)
    result = plan(record)
    assert result['next_action']['action'] == 'review_remaining'
    assert result['review_required_case_ids'] == ['A']
    assert result['runnable_case_ids'] == [] and record == before
    record['dependency_checks']['service']['status'] = 'blocked'
    assert plan(record)['review_required_case_ids'] == []
