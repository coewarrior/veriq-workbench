"""Lifecycle handoff only: no business, browser, model or message-tool calls."""
from pathlib import Path

import pytest

from api_test_tool.managed_service import ManagedService
from api_test_tool.module_dispatch import offer_modules
from api_test_tool.orchestration import Controller
from test_native_scheduler import setup
from test_native_contexts import environment as browser_environment

STATIC = Path(__file__).parents[2] / 'api_test_tool' / 'static'
COORDINATOR = '01a1576c-6fb5-7ce3-9ade-3f4e6c5dab60'
OTHER_THREAD = '01a1576c-6fb5-7ce3-9ade-3f4e6c5dab61'


def environment(tmp_path, *, reference=COORDINATOR, offer=True):
    c, owner, project, clock, tid = setup(tmp_path)
    service = ManagedService(c, STATIC)
    nodes = c.snapshot(owner, tid)['nodes']
    if offer:
        offer_modules(c, owner, {
            'task_id': tid, 'holder_id': 'coordinator', 'coordinator_ref': reference,
            'request_id': 'offers',
            'arguments': {'modules': [
                {'node_id': node['id'], 'holder_id': 'worker-' + str(i),
                 'dispatch_id': 'dispatch-' + str(i), 'executor_ref': 'worker-ref-' + str(i)}
                for i, node in enumerate(nodes)]},
        })
    requests = [
        {'task_id': tid, 'node_id': node['id'], 'holder_id': 'worker-' + str(i),
         'arguments': {'browser_environment': browser_environment('context-' + str(i), True)},
         **({'dispatch_id': 'dispatch-' + str(i)} if offer else {})}
        for i, node in enumerate(nodes)]
    first = service.direct.call(owner, {**requests[0], 'action': 'claim'})
    waiting = service.direct.call(owner, {**requests[1], 'action': 'claim'})
    assert first['lease_id'] and not waiting['lease_id']
    finish = {**requests[0], 'lease_id': first['lease_id'], 'action': 'finish',
              'outcome': 'completed', 'reason': 'fixture browser already closed',
              'arguments': {'browser_stopped': True}}
    return c, service, owner, project, clock, requests, finish


def consume(c, owner, finish, event, *, reference=COORDINATOR, request_id='consume'):
    return offer_modules(c, owner, {
        'task_id': finish['task_id'], 'holder_id': 'coordinator',
        'coordinator_ref': reference, 'request_id': request_id,
        'arguments': {'handoff_ack': {
            'task_id': finish['task_id'], 'node_id': finish['node_id'],
            'event_id': event['id']}},
    })


def test_release_persists_handoff_and_lost_response_reuses_it(tmp_path):
    c, service, owner, _, _, requests, finish = environment(tmp_path)
    first = service.direct.call(owner, finish)
    event = first['handoff']
    assert first['released'] and event['delivery_state'] == 'pending'
    assert event['id'] == finish['lease_id']
    assert event['message_tool'] == 'send_message_to_thread'
    assert event['message_arguments']['threadId'] == COORDINATOR
    assert all(value in event['message_arguments']['prompt']
               for value in (finish['task_id'], finish['node_id'], event['id']))
    c2 = Controller(c.store, c.clock)
    service2 = ManagedService(c2, STATIC)
    retry = service2.direct.call(owner, finish)
    assert retry['handoff'] == event
    snapshot = c2.snapshot(owner)
    released = next(n for n in snapshot['nodes'] if n['id'] == finish['node_id'])
    assert len(released['native_handoffs']) == 1
    assert len(released['outcome_history']) == 1
    assert not snapshot['leases']
    waiting = service2.direct.call(owner, {**requests[1], 'action': 'context'})
    assert waiting['resource_wait']['end_turn']
    assert waiting['resource_wait']['wake_owner'] == 'coordinator_handoff'
    assert waiting['browser_launch']['options'] == {'headless': True}
    with c2.transaction() as (_, state):
        assert not state['outbox'] and not list(state['direct_commands'])
        assert not list(state['operations'])


def test_real_delivery_report_and_ack_do_not_allocate_or_replay(tmp_path):
    c, service, owner, _, clock, requests, finish = environment(tmp_path)
    event = service.direct.call(owner, finish)['handoff']
    notification = {'event_id': event['id'], 'thread_id': COORDINATOR, 'sent': True}
    receipt = service.direct.call(owner, {
        **finish, 'arguments': {'handoff_notification': notification}})
    assert receipt['handoff']['delivery_state'] == 'sent'
    assert receipt['handoff']['delivery_source'] == 'executor_reported'
    assert 'message_arguments' not in receipt['handoff']
    consumed = consume(c, owner, finish, event)
    assert consumed['accepted'] and consumed['modules'] == []
    assert consumed['handoff']['delivery_state'] == 'received'
    before = c.snapshot(owner)
    waiting = next(n for n in before['nodes'] if n['id'] == requests[1]['node_id'])
    assert not before['leases']
    assert waiting['resource_wait']['resources_available']
    assert waiting['resource_wait']['wake_owner'] == 'coordinator_handoff'
    assert waiting['executor']['coordinator_ref'] == COORDINATOR
    clock[0] += 10
    again = service.direct.call(owner, {
        **finish, 'arguments': {'handoff_notification': notification}})
    assert again['handoff']['delivery_state'] == 'received'
    assert again['handoff']['sent_at'] == receipt['handoff']['sent_at']
    assert again['handoff']['received_at'] == consumed['handoff']['received_at']
    assigned = service.direct.call(owner, {**requests[1], 'action': 'claim'})
    assert assigned['account_ready'] and assigned['lease_id']
    after = next(n for n in c.snapshot(owner)['nodes'] if n['id'] == waiting['id'])
    assert after['queue_sequence'] == waiting['queue_sequence']
    assert after['id'] == waiting['id']


def test_ack_can_arrive_before_executor_delivery_receipt(tmp_path):
    c, service, owner, _, _, _, finish = environment(tmp_path)
    event = service.direct.call(owner, finish)['handoff']
    result = consume(c, owner, finish, event)
    assert result['handoff']['delivery_state'] == 'received'
    assert 'sent_at' not in result['handoff']
    assert 'message_arguments' not in service.direct.call(owner, finish)['handoff']


def test_worker_cannot_redirect_original_coordinator_binding(tmp_path):
    c, service, owner, _, _, requests, finish = environment(tmp_path)
    service.direct.call(owner, {
        **requests[0], 'action': 'claim', 'coordinator_ref': OTHER_THREAD})
    event = service.direct.call(owner, finish)['handoff']
    assert event['coordinator_ref'] == COORDINATOR
    assert event['message_arguments']['threadId'] == COORDINATOR
    assert consume(c, owner, finish, event)['accepted']


@pytest.mark.parametrize('offer', [True, False])
def test_repaired_coordinator_binding_survives_later_claims(tmp_path, offer):
    c, service, owner, _, _, requests, finish = environment(
        tmp_path, reference='legacy-placeholder', offer=offer)
    service.direct.call(owner, {
        **requests[0], 'action': 'claim', 'coordinator_ref': COORDINATOR})
    service.direct.call(owner, {**requests[0], 'action': 'claim'})
    service.direct.call(owner, {
        **requests[0], 'action': 'claim', 'coordinator_ref': OTHER_THREAD})
    event = service.direct.call(owner, finish)['handoff']
    assert event['coordinator_ref'] == COORDINATOR
    assert event['message_arguments']['threadId'] == COORDINATOR
    assert consume(c, owner, finish, event)['accepted']


def test_cached_consumption_is_rechecked_after_stop(tmp_path):
    c, service, owner, _, _, _, finish = environment(tmp_path)
    event = service.direct.call(owner, finish)['handoff']
    assert consume(c, owner, finish, event)['accepted']
    c.control(owner, finish['task_id'], {'action': 'stop', 'revision': 1, 'request_id': 'stop'})
    result = consume(c, owner, finish, event)
    assert not result['accepted']
    assert result['handoff']['delivery_state'] == 'obsolete'
    assert not c.snapshot(owner)['leases']


def test_handoff_owner_holder_target_and_task_boundaries(tmp_path):
    c, service, owner, _, _, _, finish = environment(tmp_path)
    event = service.direct.call(owner, finish)['handoff']
    with pytest.raises(PermissionError):
        service.direct.call(owner, {**finish, 'holder_id': 'another-worker'})
    with pytest.raises(PermissionError):
        service.direct.call(owner, {**finish, 'arguments': {'handoff_notification': {
            'event_id': event['id'], 'thread_id': OTHER_THREAD, 'sent': True}}})
    with pytest.raises(PermissionError):
        consume(c, owner, finish, event, reference=OTHER_THREAD, request_id='wrong-target')
    other, _ = c.store.session(None)
    with pytest.raises(PermissionError):
        consume(c, other['id'], finish, event, request_id='wrong-owner')
    assert service.direct.call(owner, finish)['handoff']['delivery_state'] == 'pending'


@pytest.mark.parametrize('change', ['stop', 'revision', 'deleted', 'session_missing', 'session_invalid'])
def test_obsolete_event_never_resumes_old_task(tmp_path, change):
    c, service, owner, _, _, _, finish = environment(tmp_path)
    event = service.direct.call(owner, finish)['handoff']
    if change == 'stop':
        c.control(owner, finish['task_id'], {'action': 'stop', 'revision': 1, 'request_id': 'stop'})
    elif change == 'revision':
        with c.transaction() as (_, state):
            state['tasks'][finish['task_id']]['revision'] += 1
    elif change == 'deleted':
        with c.transaction() as (_, state):
            state['nodes'][finish['node_id']]['session_removed'] = True
    else:
        with c.transaction() as (_, state):
            state['nodes'][finish['node_id']]['record_project_id'] = (
                OTHER_THREAD if change == 'session_missing' else 'invalid-stored-session-id')
    result = consume(c, owner, finish, event)
    assert not result['accepted']
    assert result['handoff']['delivery_state'] == 'obsolete'
    assert 'message_arguments' not in result['handoff']
    assert not c.snapshot(owner)['leases']
    assert service.direct.call(owner, finish)['handoff']['delivery_state'] == 'obsolete'


def test_unbound_legacy_identifier_is_accepted_without_guessed_message_target(tmp_path):
    c, service, owner, _, _, _, finish = environment(tmp_path, reference='old-coordinator')
    result = service.direct.call(owner, finish)
    assert result['released']
    assert result['handoff']['delivery_state'] == 'unbound'
    assert 'message_arguments' not in result['handoff']
    assert not c.snapshot(owner)['leases']


def test_plain_run_does_not_create_unnecessary_handoff_and_exposes_background_policy(tmp_path):
    c, service, owner, _, _, _, finish = environment(tmp_path, offer=False)
    context = service.direct.call(owner, {**finish, 'action': 'context'})
    launch = context['execution_host']['browser_launch']
    assert launch['browser'] == 'iab' and launch['options'] == {'visible': False}
    assert launch['foreground_fallback'] is False
    assert launch['login_context_isolation'] == 'must_use_actual_browser_context'
    assert 'handoff' not in service.direct.call(owner, finish)
    assert 'handoff' not in service.direct.call(owner, finish)
    assert not c.snapshot(owner)['nodes'][0].get('native_handoffs')


def test_legacy_dispatch_keeps_original_coordinator_semantics(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    with c.transaction() as (_, state):
        state['tasks'][tid]['execution_route'] = 'local_browser'
    node = c.snapshot(owner)['nodes'][0]
    result = offer_modules(c, owner, {
        'task_id': tid, 'holder_id': 'legacy-coordinator',
        'coordinator_ref': COORDINATOR, 'request_id': 'legacy-offer',
        'arguments': {'modules': [{
            'node_id': node['id'], 'holder_id': 'worker',
            'dispatch_id': 'legacy-dispatch', 'executor_ref': 'legacy-worker'}]},
    })
    assert result['modules'][0]['coordinator_ref'] == 'legacy-coordinator'
    assert 'handoff' not in result


def test_delivery_begin_is_single_use_and_unknown_never_becomes_a_retry(tmp_path):
    c, service, owner, _, _, _, finish = environment(tmp_path)
    released = service.direct.call(owner, finish)
    assert released['needs_handoff'] and not released['handoff_complete']
    event = released['handoff']
    def deliver(status):
        return service.direct.call(owner, {**finish, 'arguments': {'handoff_delivery': {
            'event_id': event['id'], 'thread_id': COORDINATOR,
            'attempt_id': 'one-desktop-send', 'state': status}}})
    assert deliver('sending')['handoff']['send_authorized']
    assert not deliver('sending')['handoff']['send_authorized']
    assert deliver('unknown')['handoff']['delivery_state'] == 'unknown'
    assert not deliver('sending')['handoff']['send_authorized']
    assert 'message_arguments' not in service.direct.call(owner, finish)['handoff']
    assert not c.snapshot(owner)['leases']


def bind_waiting_thread(c, requests):
    with c.transaction() as (_, state):
        node = state['nodes'][requests[1]['node_id']]
        node['executor_dispatch']['executor_ref'] = 'thread:' + OTHER_THREAD
        node['dispatch_offer']['executor_ref'] = 'thread:' + OTHER_THREAD


def test_consumption_returns_original_successor_and_fences_changed_binding(tmp_path):
    c, service, owner, _, _, requests, finish = environment(tmp_path)
    bind_waiting_thread(c, requests)
    event = service.direct.call(owner, finish)['handoff']
    consumed = consume(c, owner, finish, event)
    resume = consumed['continuation']
    assert resume['message_arguments']['threadId'] == OTHER_THREAD
    assert resume['claim_arguments']['node_id'] == requests[1]['node_id']
    assert resume['claim_arguments']['dispatch_id'] == requests[1]['dispatch_id']
    assert not c.snapshot(owner)['leases']
    with c.transaction() as (_, state):
        state['nodes'][requests[1]['node_id']]['executor_dispatch']['holder_id'] = 'replacement'
    stale = consume(c, owner, finish, event)
    assert stale['continuation']['delivery_state'] == 'obsolete'
    assert 'message_arguments' not in stale['continuation']


def test_no_successor_notification_after_available_account_disappears(tmp_path):
    c, service, owner, _, _, requests, finish = environment(tmp_path)
    bind_waiting_thread(c, requests)
    event = service.direct.call(owner, finish)['handoff']
    resume = consume(c, owner, finish, event)['continuation']
    with c.transaction() as (_, state):
        aid = next(iter(state['accounts']))
        state['accounts'][aid]['state'] = 'disabled'
    response = offer_modules(c, owner, {
        'task_id': finish['task_id'], 'holder_id': 'coordinator',
        'coordinator_ref': COORDINATOR, 'request_id': 'send',
        'arguments': {'handoff_ack': {'task_id': finish['task_id'],
            'node_id': finish['node_id'], 'event_id': event['id']},
            'handoff_delivery': {'event_id': resume['id'], 'thread_id': OTHER_THREAD,
                'attempt_id': 'one-send', 'state': 'sending'}}})
    assert not response['send_authorized']
    assert response['continuation']['delivery_state'] == 'waiting_resources'
    with c.transaction() as (_, state):
        state['accounts'][aid]['state'] = 'active'
    resumed = consume(c, owner, finish, event, request_id='resource-returned')['continuation']
    assert resumed['id'] == resume['id'] and resumed['delivery_state'] == 'pending'


def test_explicit_group_repairs_placeholders_and_continues_cross_task(tmp_path):
    import copy
    c, service, owner, _, _, requests, finish = environment(tmp_path, reference='legacy-placeholder')
    bind_waiting_thread(c, requests)
    with c.transaction() as (_, state):
        source = state['tasks'][finish['task_id']]
        target = copy.deepcopy(source)
        target['id'] = 'other-task'
        target['node_ids'] = [requests[1]['node_id']]
        source['node_ids'] = [finish['node_id']]
        state['tasks'][target['id']] = target
        state['nodes'][requests[1]['node_id']]['task_id'] = target['id']
    event = service.direct.call(owner, finish)['handoff']
    assert event['delivery_state'] == 'unbound'
    group = offer_modules(c, owner, {
        'task_id': finish['task_id'], 'holder_id': 'coordinator', 'coordinator_ref': COORDINATOR,
        'request_id': 'authorized-group', 'arguments': {
            'continuation_group': {'task_ids': [finish['task_id'], 'other-task']}}})
    assert group['pending_handoffs'][0]['event_id'] == event['id']
    consumed = consume(c, owner, finish, event)
    assert consumed['continuation']['task_id'] == 'other-task'
    assert consumed['continuation']['claim_arguments']['task_id'] == 'other-task'
    assert consumed['continuation']['message_arguments']['threadId'] == OTHER_THREAD
    assert not c.snapshot(owner)['leases']


def test_multiple_released_accounts_nominate_only_the_admissible_original_workers(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=3, modules=4)
    service = ManagedService(c, STATIC)
    snapshot = c.snapshot(owner, tid)
    nodes = snapshot['nodes']
    offers = [{'node_id': node['id'], 'holder_id': 'worker-' + str(i),
               'dispatch_id': 'dispatch-' + str(i),
               'executor_ref': '00000000-0000-4000-8000-%012d' % i}
              for i, node in enumerate(nodes)]
    offer_modules(c, owner, {'task_id': tid, 'holder_id': 'coordinator',
        'coordinator_ref': COORDINATOR, 'request_id': 'offer-all',
        'arguments': {'modules': offers}})
    requests = [{**item, 'task_id': tid,
                 'arguments': {'browser_environments': [browser_environment('context-' + str(j), True)
                    for j in (range(3) if i == 0 else [i - 1])]}}
                for i, item in enumerate(offers)]
    first = service.direct.call(owner, {**requests[0], 'action': 'claim',
        'account_ids': [account['id'] for account in snapshot['accounts']]})
    assert len(first['account_ids']) == 3
    for request in requests[1:]:
        assert service.direct.call(owner, {**request, 'action': 'claim'})['lease_id'] is None
    finish = {**requests[0], 'action': 'finish', 'lease_id': first['lease_id'],
              'reason': 'all fixture browsers already closed', 'arguments': {'browser_stopped': True}}
    event = service.direct.call(owner, finish)['handoff']
    result = consume(c, owner, finish, event)
    assert len(result['continuations']) == 3
    assert len({tuple(item['candidate_account_ids']) for item in result['continuations']}) == 3
    assert not c.snapshot(owner)['leases']
    assert len(consume(c, owner, finish, event)['continuations']) == 3


def test_fresh_ack_reconciles_once_and_cached_ack_revalidates(tmp_path, monkeypatch):
    from api_test_tool import native_handoff
    c, service, owner, _, _, _, finish = environment(tmp_path)
    event = service.direct.call(owner, finish)['handoff']
    original = native_handoff.acknowledge
    calls = []
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(native_handoff, 'acknowledge', counted)
    assert consume(c, owner, finish, event)['accepted']
    assert len(calls) == 1
    c.control(owner, finish['task_id'], {'action':'stop','revision':1,'request_id':'stop-once'})
    assert not consume(c, owner, finish, event)['accepted']
    assert len(calls) == 2


def test_no_recipient_skips_preview_but_invalidates_stale_events(tmp_path, monkeypatch):
    from api_test_tool import native_handoff
    c, service, owner, _, _, requests, finish = environment(tmp_path)
    event = service.direct.call(owner, finish)['handoff']
    with c.transaction() as (_, state):
        first = state['nodes'][finish['node_id']]
        saved = first['native_handoffs'][event['id']]
        saved['delivery_state'] = 'obsolete'
        target = state['nodes'][requests[1]['node_id']]
        target['state'] = 'cancelled'
        stale = {'id':'stale','node_id':target['id'],'delivery_state':'pending'}
        saved['continuations'] = [stale]
        class NoPreview:
            def __init__(self, *args):
                raise AssertionError('no recipient needs no scheduler preview')
        from api_test_tool import resource_scheduler
        monkeypatch.setattr(resource_scheduler, 'ResourceScheduler', NoPreview)
        assert native_handoff.continuation(c,state,state['tasks'][finish['task_id']],saved) is None
        assert stale['delivery_state'] == 'obsolete'


@pytest.mark.parametrize('delivery_state', ['obsolete', 'sent', 'unknown'])
def test_existing_notice_skips_trial_when_resource_matching_cannot_change_it(tmp_path, monkeypatch, delivery_state):
    from api_test_tool import native_handoff
    c, service, owner, _, _, requests, finish = environment(tmp_path)
    bind_waiting_thread(c, requests)
    event = service.direct.call(owner, finish)['handoff']
    resume = consume(c, owner, finish, event)['continuation']
    with c.transaction() as (_, state):
        saved = state['nodes'][finish['node_id']]['native_handoffs'][event['id']]
        current = saved['continuation']
        current['delivery_state'] = delivery_state
        stale = {**current, 'id': 'unrelated-stale', 'node_id': finish['node_id'], 'delivery_state': 'pending'}
        saved['continuations'].append(stale)
        before_accounts = {key: dict(value) for key, value in state['accounts'].items()}
        def forbidden(*args):
            raise AssertionError('a fenced notification must not copy trial nodes')
        monkeypatch.setattr(native_handoff, 'copy_node', forbidden)
        result = native_handoff.continuation(c, state, state['tasks'][finish['task_id']], saved)
        assert result['id'] == resume['id'] and result['delivery_state'] == delivery_state
        assert 'message_arguments' not in result
        assert stale['delivery_state'] == 'obsolete'
        assert not state['leases'] and state['accounts'] == before_accounts
        assert state['nodes'][requests[1]['node_id']]['state'] == 'queued'
