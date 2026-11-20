"""Coordinator closeout is scheduling, not a rewrite of business outcomes."""
import copy

import pytest

from api_test_tool.module_dispatch import offer_modules
from test_formal_continuation_environment import continue_source


def coordinator(original, arguments, request_id='closeout'):
    return {'task_id': original['task_id'], 'holder_id': 'coordinator',
            'coordinator_ref': original['coordinator_ref'], 'request_id': request_id,
            'arguments': arguments}


def test_closeout_inventory_and_explicit_end_preserve_saved_record(tmp_path, monkeypatch):
    c, _, owner, original, context, before, claim = continue_source(tmp_path, monkeypatch)
    from api_test_tool import ui_records
    saved_before = copy.deepcopy(ui_records.load(c.store, owner, context['project']['id'], before['id']))
    original_result = next(n for n in c.snapshot(owner)['nodes'] if n['id'] == original['node_id'])['result']
    with c.transaction() as (_, state):
        state.setdefault('cleanup_objects', {})['residual'] = {
            'id': 'residual', 'owner': owner, 'task_id': original['task_id'],
            'source_node_id': original['node_id'], 'case_id': 'A', 'state': 'residual',
            'object_id': 'draft-original'}
    view = offer_modules(c, owner, coordinator(original, {'observe': True}))
    assert view['closeout']['queued'][0]['node_id'] == claim['node_id']
    assert view['closeout']['cleanup_responsibilities'][0]['id'] == 'residual'
    result = offer_modules(c, owner, coordinator(original,
        {'coordinator_closeout': {'disposition': 'ended', 'reason': 'Partial results delivered; no further work in this round'}}))
    assert result['accepted'] and result['closeout']['disposition'] == 'ended'
    after = c.snapshot(owner, original['task_id'])
    assert after['tasks'][0]['intent'] == 'stop'
    child = next(n for n in after['nodes'] if n['id'] == claim['node_id'])
    assert child['state'] == 'stopped' and child['result'] == original_result
    assert not child.get('finalization_pending')
    assert not child['executor_dispatch'].get('exit_acknowledged_at')
    assert ui_records.load(c.store, owner, context['project']['id'], before['id']) == saved_before
    with c.transaction() as (_, state):
        assert state['cleanup_objects']['residual']['state'] == 'residual'


def test_waiting_closeout_does_not_cancel_or_reorder_queue(tmp_path, monkeypatch):
    c, _, owner, original, _, _, claim = continue_source(tmp_path, monkeypatch)
    before = c.snapshot(owner, original['task_id'])['nodes']
    result = offer_modules(c, owner, coordinator(original,
        {'coordinator_closeout': {'disposition': 'waiting', 'reason': 'Original environment prerequisite remains'}}))
    assert result['accepted']
    assert c.snapshot(owner, original['task_id'])['nodes'] == before
    assert c.snapshot(owner)['tasks'][0]['intent'] == 'run'


@pytest.mark.parametrize('hazard', ['claim', 'lease', 'unknown_send', 'operation', 'historical_operation',
                                  'command', 'cross_task_send', 'foreign_control', 'container_active', 'foreign_coordinator'])
def test_end_cannot_invent_an_exit_or_hide_unknown_work(tmp_path, monkeypatch, hazard):
    c, _, owner, original, _, _, claim = continue_source(tmp_path, monkeypatch)
    with c.transaction() as (_, state):
        node = state['nodes'][claim['node_id']]
        if hazard == 'claim':
            node['executor_dispatch']['receipt_source'] = 'executor_claim'
            node['direct_holder'] = claim['holder_id']
        elif hazard == 'lease':
            state['leases']['live'] = {'id': 'live', 'node_id': node['id'], 'account_ids': []}
        elif hazard == 'unknown_send':
            node['native_handoffs'] = {'event': {'id': 'event', 'delivery_state': 'unknown'}}
        elif hazard in {'operation', 'historical_operation', 'command'}:
            state['direct_commands' if hazard == 'command' else 'operations']['unknown'] = {
                'id': 'unknown', 'node_id': node['id'], 'state': 'unknown', 'historical': hazard == 'historical_operation'}
        elif hazard == 'cross_task_send':
            state['nodes']['external'] = {'id': 'external', 'task_id': 'external-task', 'owner': owner,
                'native_handoffs': {'event': {'id': 'event', 'node_id': 'external', 'delivery_state': 'received',
                    'continuations': [{'node_id': node['id'], 'delivery_state': 'unknown'}]}}}
        elif hazard == 'foreign_control':
            state['nodes'][original['node_id']]['executor_controls'] = {'old': {
                'id': 'old', 'holder_id': 'other-holder', 'executor_ref': 'other-thread',
                'created_at': 1, 'action': 'stop', 'state': 'pending'}}
        elif hazard == 'container_active':
            parent = copy.deepcopy(node)
            parent.update(id='active-container', state='container', child_ids=[node['id']], native_browser_stopped=False)
            parent['executor_dispatch'].pop('exit_acknowledged_at', None)
            state['nodes'][parent['id']] = parent
            state['tasks'][original['task_id']]['node_ids'].append(parent['id'])
    args = coordinator(original, {'coordinator_closeout': {'disposition': 'ended', 'reason': 'end'}})
    if hazard == 'foreign_coordinator':
        args['coordinator_ref'] = '01a17111-5ac7-79d0-9ac8-48eaaddc22b0'
        with pytest.raises(PermissionError):
            offer_modules(c, owner, args)
    else:
        result = offer_modules(c, owner, args)
        assert not result['accepted'] and result['closeout']['in_flight']
    with c.transaction() as (_, state):
        assert state['tasks'][original['task_id']]['intent'] == 'run'
        assert state['nodes'][claim['node_id']]['state'] == 'queued'


def test_same_closeout_request_rechecks_resolved_obligation_and_then_stays_idempotent(tmp_path, monkeypatch):
    c, _, owner, original, _, _, claim = continue_source(tmp_path, monkeypatch)
    with c.transaction() as (_, state):
        state['operations']['unknown'] = {'id': 'unknown', 'node_id': claim['node_id'], 'state': 'unknown'}
    args = coordinator(original, {'coordinator_closeout': {'disposition': 'ended', 'reason': 'partial delivered'}})
    assert not offer_modules(c, owner, args)['accepted']
    with c.transaction() as (_, state):
        state['operations']['unknown']['state'] = 'confirmed'
    result = offer_modules(c, owner, args)
    assert result['accepted']
    revision = c.snapshot(owner)['tasks'][0]['revision']
    assert offer_modules(c, owner, args) == result
    assert c.snapshot(owner)['tasks'][0]['revision'] == revision


def test_never_dispatched_excluded_leaf_does_not_require_a_new_chat_to_end(tmp_path, monkeypatch):
    c, _, owner, original, _, _, claim = continue_source(tmp_path, monkeypatch)
    with c.transaction() as (_, state):
        excluded = copy.deepcopy(state['nodes'][claim['node_id']])
        excluded.update(id='excluded', state='blocked', execution_disposition='multi_account_excluded')
        for key in ('executor_dispatch', 'dispatch_offer', 'executor_dispatch_history', 'dispatch_offer_history',
                    'attempts', 'case_history', 'outcome_history', 'native_environment', 'native_environment_keys',
                    'continuation_source'):
            excluded.pop(key, None)
        state['nodes']['excluded'] = excluded
        state['tasks'][original['task_id']]['node_ids'].append('excluded')
    result = offer_modules(c, owner, coordinator(original,
        {'coordinator_closeout': {'disposition': 'ended', 'reason': 'partial delivered'}}))
    assert result['accepted']


def test_foreign_unattributed_history_is_not_exposed_or_applied_to_this_coordinator(tmp_path, monkeypatch):
    c, _, owner, original, _, _, _ = continue_source(tmp_path, monkeypatch)
    with c.transaction() as (_, state):
        state['direct_commands']['foreign-secret-id'] = {'id': 'foreign-secret-id', 'owner': 'foreign-owner',
            'lease_id': 'missing-old-lease', 'state': 'unknown'}
    view = offer_modules(c, owner, coordinator(original, {'observe': True}))
    assert 'foreign-secret-id' not in str(view['closeout'])
    assert view['closeout']['can_end_scheduling']


def test_desktop_receipt_is_generation_bound_and_does_not_fake_browser_exit(tmp_path, monkeypatch):
    c, _, owner, original, _, _, claim = continue_source(tmp_path, monkeypatch)
    with c.transaction() as (_, state):
        binding = copy.deepcopy(state['nodes'][claim['node_id']]['executor_dispatch'])
    receipt = {'node_id': claim['node_id'], 'dispatch_id': binding['dispatch_id'],
               'executor_ref': claim['executor_ref'], 'turn_id': 'actual-turn',
               'status': 'completed', 'completed_at': binding['received_at'] + 1}
    args = coordinator(original, {'desktop_observations': [receipt]}, 'observed')
    assert offer_modules(c, owner, args)['accepted']
    with c.transaction() as (_, state):
        node = state['nodes'][claim['node_id']]
        assert node['desktop_observation']['status'] == 'completed'
        assert node['state'] == 'queued' and node['native_browser_stopped'] is True
        assert not node['executor_dispatch'].get('exit_acknowledged_at')
    receipt['dispatch_id'] = 'old-generation'
    args['request_id'] = 'stale-observed'
    with pytest.raises((PermissionError, ValueError)):
        offer_modules(c, owner, args)
