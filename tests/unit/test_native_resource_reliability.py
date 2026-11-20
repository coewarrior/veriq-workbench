"""Focused offline contracts; no browser, desktop sends or model calls."""
import copy

import pytest

from api_test_tool.module_dispatch import node_dispatch, offer_modules
from api_test_tool.native_contexts import choose_context, invalidate, register_environment, replace_exited_environment
from api_test_tool.native_handoff import consume_on_claim, notices, reconcile_resources
from api_test_tool.orchestration import Conflict
from api_test_tool.resource_scheduler import ResourceScheduler, apply_account_selection
from test_native_contexts import environment as browser_environment, register
from test_native_handoff import COORDINATOR, OTHER_THREAD, bind_waiting_thread, consume, environment
from test_native_scheduler import claim, setup


def model_receipt(c, owner, request):
    with c.transaction() as (_, state):
        node = state['nodes'][request['node_id']]
        task = state['tasks'][node['task_id']]
        binding = node['executor_dispatch']
        value = dict(node_id=node['id'], task_revision=task['revision'], node_revision=node['revision'],
                     holder_id=binding['holder_id'], dispatch_id=binding['dispatch_id'],
                     executor_ref=binding['executor_ref'], state='unavailable', model='original-model',
                     source='codex_turn_error', reference='desktop-turn-1', reason='capacity error', kind='capacity')
    return {'task_id': request['task_id'], 'holder_id': 'coordinator', 'coordinator_ref': COORDINATOR,
            'request_id': 'model-turn-1', 'arguments': {'executor_status': value}}


def test_model_error_has_own_state_and_original_claim_resolves_without_replay(tmp_path):
    c, service, owner, _, _, requests, finish = environment(tmp_path)
    bind_waiting_thread(c, requests)
    with c.transaction() as (_, state):
        node = state['nodes'][requests[1]['node_id']]
        node['checkpoint'] = {'completed': ['C1'], 'unknown': ['C2']}
        checkpoint = copy.deepcopy(node['checkpoint'])
    receipt = model_receipt(c, owner, requests[1])
    assert offer_modules(c, owner, receipt)['accepted']
    with c.transaction() as (_, state):
        node = state['nodes'][requests[1]['node_id']]
        assert node_dispatch(node)['dispatch_state'] == 'model_unavailable'
        assert not node.get('native_claim_pending') and not node.get('reservation')
        assert ResourceScheduler(c, state, c.clock()).native_availability(node)[0] is None
        assert node['checkpoint'] == checkpoint
    service.direct.call(owner, finish)
    result = service.direct.call(owner, {**requests[1], 'action': 'claim', 'executor_ref': 'thread:' + OTHER_THREAD})
    assert result['lease_id']
    with c.transaction() as (_, state):
        node = state['nodes'][requests[1]['node_id']]
        assert node['native_executor_status']['state'] == 'available'
        assert node['native_executor_status_history'][-1]['reference'] == 'desktop-turn-1'
        assert node['checkpoint'] == checkpoint


@pytest.mark.parametrize('field', ['task_revision', 'node_revision', 'holder_id', 'dispatch_id', 'executor_ref'])
def test_model_error_old_binding_cannot_change_current_state(tmp_path, field):
    c, _, owner, _, _, requests, _ = environment(tmp_path)
    bind_waiting_thread(c, requests)
    receipt = model_receipt(c, owner, requests[1])
    receipt['arguments']['executor_status'][field] = 'stale'
    before = c.snapshot(owner)['leases']
    with pytest.raises(Conflict):
        offer_modules(c, owner, receipt)
    assert c.snapshot(owner)['leases'] == before


def test_model_error_with_live_lease_never_releases_it(tmp_path):
    c, _, owner, _, _, requests, _ = environment(tmp_path)
    with c.transaction() as (_, state):
        node = state['nodes'][requests[0]['node_id']]
        node['executor_dispatch']['executor_ref'] = 'thread:' + OTHER_THREAD
    before = c.snapshot(owner)['leases']
    receipt = model_receipt(c, owner, requests[0])
    assert offer_modules(c, owner, receipt)['accounts_retained']
    assert c.snapshot(owner)['leases'] == before


def test_explicit_required_preferences_and_empty_clear_do_not_replace_fixed_bundle(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=2)
    with c.transaction() as (_, state):
        node = state['nodes'][state['tasks'][tid]['node_ids'][0]]
        accounts = list(state['accounts'])
        scheduler = ResourceScheduler(c, state, c.clock())
        apply_account_selection(node, accounts)
        assert set(scheduler.bundle(node)) == set(accounts)
        state['accounts'][accounts[0]]['state'] = 'disabled'
        scheduler = ResourceScheduler(c, state, c.clock())
        assert scheduler.bundle(node) is None
        apply_account_selection(node, [accounts[0]], 'preferred')
        assert scheduler.bundle(node) == [accounts[1]]
        apply_account_selection(node, [])
        assert node['requested_account_ids'] == node['preferred_account_ids'] == []


def test_environment_revision_changes_do_not_revive_exited_chromium(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    node_id = c.snapshot(owner, tid)['nodes'][0]['id']
    original = {**browser_environment('actual-old', True), 'browser': 'chromium', 'browser_generation': 1}
    register(c, owner, node_id, original)
    with c.transaction() as (_, state):
        node = state['nodes'][node_id]
        registered_revision = node['native_environment_revision']
        node['revision'] += 1
        accounts = list(state['accounts'])
        assert choose_context(state, node, accounts)
        assert node['native_environment_revision'] == registered_revision
        invalidate(node, 'exited', c.clock())
        assert choose_context(state, node, accounts) is None
        with pytest.raises(Conflict, match='已确认退出'):
            register_environment(state, node, owner, original)
        register_environment(state, node, owner, {**original, 'browser_generation': 2})
        assert choose_context(state, node, accounts)
        invalidate(node, 'exited', c.clock())
        with pytest.raises(Conflict, match='已确认退出'):
            register_environment(state, node, owner, {**original, 'browser_generation': 2})
        legacy = {key: value for key, value in original.items() if key != 'browser_generation'}
        register_environment(state, node, owner, legacy)
        assert choose_context(state, node, accounts)


def test_real_environment_replacement_remembers_old_exited_id(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    node_id = c.snapshot(owner, tid)['nodes'][0]['id']
    original = {**browser_environment('actual-old', True), 'browser': 'chromium', 'browser_generation': 1}
    replacement = {**browser_environment('actual-new', True), 'browser': 'chromium'}
    register(c, owner, node_id, original)
    live = claim(c, owner, node_id, 'first')
    with c.transaction() as (_, state):
        node = state['nodes'][node_id]
        replace_exited_environment(state, node, state['leases'][live['id']], owner, {
            'browser_stopped': True, 'reason': 'original process exited',
            'previous_context_ids': ['actual-old'], 'browser_environments': [replacement]}, c.clock())
        with pytest.raises(Conflict, match='已确认退出'):
            register_environment(state, node, owner, original)
        assert state['leases'][live['id']]['account_ids'] == live['account_ids']


def test_original_claim_consumes_unknown_notice_without_fabricating_send(tmp_path):
    c, service, owner, _, clock, requests, finish = environment(tmp_path)
    bind_waiting_thread(c, requests)
    event = service.direct.call(owner, finish)['handoff']
    consume(c, owner, finish, event)
    with c.transaction() as (_, state):
        saved = state['nodes'][finish['node_id']]['native_handoffs'][event['id']]
        notice = notices(saved)[0]
        notice.update(delivery_state='unknown', delivery_attempt_id='original-attempt')
        node = state['nodes'][requests[1]['node_id']]
        consume_on_claim(state, node, clock[0])
        assert node['state'] == 'queued'
        assert notice['delivery_state'] == 'received' and notice['claim_received_at'] == clock[0]
        assert 'sent_at' not in notice
        # A read/reconcile without a resource change cannot generate another wake.
        count = len(notices(saved))
        reconcile_resources(c, state)
        assert len(notices(saved)) == count
