"""Scheduling must not traverse archived case bodies while holding the writer."""
import copy
from contextlib import contextmanager

from api_test_tool.resource_scheduler import ResourceScheduler, request_resources
from api_test_tool.native_handoff import successors
from test_native_work_plan import setup, install
from test_native_scheduler import claim
from test_native_handoff import environment, bind_waiting_thread
from test_execution_work_plan import unit
from test_ui_dependencies import case


class ArchivedCases(dict):
    def __deepcopy__(self, memo):
        raise AssertionError('resource matching copied archived case results')


@contextmanager
def archive(state):
    for node in state['nodes'].values():
        node['case_history'] = ArchivedCases({'1': {'cases': [{'case_id': 'OLD', 'actual': 'preserved'}]}})
    try:
        yield
    finally:
        # Keep the guard around resource matching, then persist ordinary JSON.
        for node in state['nodes'].values():
            if isinstance(node.get('case_history'), ArchivedCases):
                node['case_history'] = dict(node['case_history'])


def test_stage_matching_keeps_history_out_of_trial_without_mutating_resources(tmp_path):
    c, owner, project, _, tid = setup(tmp_path, accounts=1, modules=1)
    node = c.snapshot(owner, tid)['nodes'][0]
    aid = c.snapshot(owner)['accounts'][0]['id']
    record, _ = install(c, owner, project, node['id'], [unit('read', ['A'], [aid])], [case('A', [])])
    with c.transaction() as (_, state):
        with archive(state):
            original = state['nodes'][node['id']]
            before = copy.deepcopy({k: v for k, v in original.items() if k != 'case_history'})
            accounts = copy.deepcopy(state['accounts'])
            selected = ResourceScheduler(c, state, c.clock()).select_work_candidate(original, {**record, 'project_id': project['id']})
            assert selected['account_ids'] == [aid]
            assert selected['unit_id'] == 'read'
            selected['projected_node']['checkpoint']['work_plan']['units'][0]['case_ids'].append('TRIAL')
            assert {k: v for k, v in original.items() if k != 'case_history'} == before
            assert state['accounts'] == accounts
            assert original['case_history']['1']['cases'][0]['actual'] == 'preserved'


def test_successor_matching_does_not_copy_history_or_allocate_accounts(tmp_path):
    c, service, owner, _, _, requests, finish = environment(tmp_path)
    bind_waiting_thread(c, requests)
    event = service.direct.call(owner, finish)['handoff']
    with c.transaction() as (_, state):
        with archive(state):
            saved = state['nodes'][finish['node_id']]['native_handoffs'][event['id']]
            saved['delivery_state'] = 'received'
            accounts = copy.deepcopy(state['accounts'])
            successor = successors(c, state, state['tasks'][finish['task_id']], saved)[0]
            assert successor['node_id'] == requests[1]['node_id']
            assert successor['candidate_account_ids']
            assert not state['leases']
            assert state['accounts'] == accounts
            assert state['nodes'][requests[1]['node_id']]['state'] == 'queued'
    persisted = c.snapshot(owner, finish['task_id'], include_history=True)
    assert all(n['case_history']['1']['cases'][0]['actual'] == 'preserved' for n in persisted['nodes'])


def test_resource_boundary_reuses_lease_without_copying_archived_results(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=1, modules=1)
    node = c.snapshot(owner, tid)['nodes'][0]
    lease = claim(c, owner, node['id'], 'worker')
    with c.transaction() as (db, state):
        with archive(state):
            result = request_resources(c, db, state, state['leases'][lease['id']], {'next_phase': 'execution'})
            assert result['continued'] is True
            assert result['lease_id'] == lease['id']
            assert state['nodes'][node['id']]['case_history']['1']['cases'][0]['actual'] == 'preserved'


def test_native_account_selection_does_not_copy_archived_results(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from api_test_tool.managed_service import ManagedService
    from api_test_tool.native_execution import NativeExecution
    from test_native_execution import STATIC
    from test_native_contexts import environment as browser_environment
    c, owner, _, _, tid = setup(tmp_path, accounts=1, modules=1)
    node = c.snapshot(owner, tid)['nodes'][0]
    account_id = c.snapshot(owner)['accounts'][0]['id']
    transaction = c.transaction
    @contextmanager
    def archived_transaction(**kwargs):
        with transaction(**kwargs) as (db, state):
            with archive(state):
                yield db, state
    monkeypatch.setattr(c, 'transaction', archived_transaction)
    result = NativeExecution(ManagedService(c, STATIC).direct).claim(owner, {
        'task_id': tid, 'node_id': node['id'], 'account_ids': [account_id],
        'arguments': {'browser_environment': browser_environment('selected-context', True)}}, 'original')
    assert result['account_ready'] and result['account_ids'] == [account_id]
    persisted = c.snapshot(owner, tid, include_history=True)
    assert persisted['nodes'][0]['queue_sequence'] == node['queue_sequence']
    assert persisted['nodes'][0]['case_history']['1']['cases'][0]['actual'] == 'preserved'


def test_environment_replacement_keeps_history_and_original_account_set(tmp_path):
    from api_test_tool.native_contexts import replace_exited_environment
    from test_native_contexts import environment as browser_environment, register
    from test_native_scheduler import setup as base_setup
    c, owner, _, _, tid = base_setup(tmp_path, accounts=1, modules=1, current_protocol=True)
    node_id = c.snapshot(owner, tid)['nodes'][0]['id']
    register(c, owner, node_id, browser_environment('original-context', True))
    live = claim(c, owner, node_id, 'original-holder')
    with c.transaction() as (_, state):
        with archive(state):
            node = state['nodes'][node_id]
            sequence = node['queue_sequence']
            value = {'browser_stopped': True, 'reason': 'original context exited',
                     'previous_context_ids': ['original-context'],
                     'browser_environments': [browser_environment('replacement-context', True)]}
            audit = replace_exited_environment(state, node, state['leases'][live['id']], owner, value, c.clock())
            assert audit['previous_binding']['context_id'] == 'original-context'
            assert state['leases'][live['id']]['native_context_binding']['context_id'] == 'replacement-context'
            assert state['leases'][live['id']]['account_ids'] == live['account_ids']
            assert node['direct_holder'] == 'original-holder' and node['queue_sequence'] == sequence
            assert node['case_history']['1']['cases'][0]['actual'] == 'preserved'
    persisted = c.snapshot(owner, tid, include_history=True)
    assert persisted['nodes'][0]['case_history']['1']['cases'][0]['actual'] == 'preserved'
