"""Native desktop allocation and S1 stop; no models, browsers or network calls."""
import pytest

from api_test_tool.orchestration import Controller, Conflict
from api_test_tool.web_storage import Store
from api_test_tool.module_dispatch import expire_dispatches, receive


def setup(tmp_path, accounts=1, modules=2, exploration=False, current_protocol=False):
    store = Store(tmp_path)
    session, _ = store.session(None)
    owner = session['id']
    project = store.create_project(owner, 'native fixture', 'test.md', 'native test')
    store.update_project(owner, project['id'], {'test_kind': 'ui', 'ui_target_url': 'https://test.example/login'})
    clock = [1000.]
    controller = Controller(store, lambda: clock[0])
    for index in range(accounts):
        controller.add_account(owner, {'project_id': project['id'], 'target': 'https://test.example',
                                      'identity': 'account-' + str(index), 'credential': ''})
    task = controller.create_task(owner, {
        'project_id': project['id'], 'request_id': 'native-task', 'goal': 'native fixture',
        'execution_route': 'native_browser', 'session_workflow': True,
        'modules': [{'key': 'm' + str(index), 'title': 'm' + str(index), 'requirements': []} for index in range(modules)],
    })
    with controller.transaction() as (_, state):
        # These historical scheduler fixtures intentionally exercise pre-context
        # leases. New protocol tests opt in and register actual isolated contexts.
        if not current_protocol:
            state['tasks'][task['task_id']]['native_browser_policy'] = 'legacy_reported'
        for nid in state['tasks'][task['task_id']]['node_ids']:
            if not current_protocol:
                state['nodes'][nid].pop('native_context_protocol', None)
            if not exploration:
                state['nodes'][nid]['phase'] = 'execution'
    return controller, owner, project, clock, task['task_id']


def claim(controller, owner, node_id, holder):
    with controller.transaction() as (_, state):
        node = state['nodes'][node_id]
        receive(state, node, holder, controller.clock(), executor_ref='thread-' + holder)
        node.update(direct_holder=holder, actor_seen=controller.clock(), native_claim_pending=True)
    controller.schedule()
    return next((lease for lease in controller.snapshot(owner)['leases'] if lease['node_id'] == node_id), None)


def test_native_claim_without_runner_or_action_dispatch(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    nodes = c.snapshot(owner, tid)['nodes']
    lease = claim(c, owner, nodes[0]['id'], 'first')
    state = c.snapshot(owner, tid)
    assert lease['native_browser'] and lease['runner_id'] == 'native:first'
    assert lease['browser_units'] == 0 and lease['mode'] == 'exclusive'
    assert state['runners'] == []
    assert state['nodes'][0]['state'] == 'running'
    assert state['nodes'][0]['dispatch_state'] == 'account_assigned'
    assert not state['nodes'][0].get('business_started_at')
    with c.transaction() as (_, raw):
        assert not raw['outbox']
        assert not list(raw['direct_commands'])
        assert not list(raw['operations'])


def test_sleeping_worker_gets_ready_notice_without_account_allocation(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    nodes = c.snapshot(owner, tid)['nodes']
    first = claim(c, owner, nodes[0]['id'], 'first')
    assert claim(c, owner, nodes[1]['id'], 'second') is None
    queued = c.snapshot(owner, tid)['nodes'][1]
    assert queued['resource_wait']['end_turn']
    assert queued['resource_wait']['resources_available'] is False
    position = queued['queue_sequence']
    c.return_account(owner, first['runner_id'], {
        'lease_id': first['id'], 'executor_stopped': True, 'browser_stopped': True,
        'outcome': 'completed', 'result': 'partial',
    })
    c.schedule()
    snapshot = c.snapshot(owner, tid)
    assert not snapshot['leases']
    second = snapshot['nodes'][1]
    assert second['resource_wait']['resources_available'] is True
    assert second['queue_sequence'] == position
    assert second['direct_holder'] == 'second'
    assert claim(c, owner, second['id'], 'second')['native_browser']


def test_s1_stop_keeps_account_and_lists_actual_desktop_session(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    node = c.snapshot(owner, tid)['nodes'][0]
    lease = claim(c, owner, node['id'], 'first')
    result = c.control(owner, tid, {'action': 'stop', 'revision': 1, 'request_id': 'stop'})
    view = result['desktop_stop']
    assert view['platform_scheduling_stopped']
    assert view['manual_stop_required']
    row = view['required_sessions'][0]
    assert row['executor_ref'] == 'thread-first'
    assert not row['executor_exit_confirmed'] and not row['browser_stopped']
    assert not row['accounts_released']
    assert c.snapshot(owner, tid)['leases'][0]['id'] == lease['id']
    with c.transaction() as (_, state):
        assert not state['outbox']
    with pytest.raises(Conflict, match='浏览器'):
        c.return_account(owner, lease['runner_id'], {
            'lease_id': lease['id'], 'executor_stopped': True, 'outcome': 'blocked',
        })
    assert c.snapshot(owner, tid)['leases']


def test_native_resource_boundary_reuses_same_lease_without_runner(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    node = c.snapshot(owner, tid)['nodes'][0]
    lease = claim(c, owner, node['id'], 'first')
    result = c.request_resources(owner, lease['id'], {'next_phase': 'execution'})
    assert result['continued'] is True
    assert result['lease_id'] == lease['id']
    assert c.snapshot(owner, tid)['leases'][0]['browser_units'] == 0
    with c.transaction() as (_, state):
        assert not state['outbox']


def test_native_sleep_does_not_expire_queued_holder(tmp_path):
    c, owner, _, clock, tid = setup(tmp_path, accounts=0)
    node = c.snapshot(owner, tid)['nodes'][0]
    assert claim(c, owner, node['id'], 'sleeper') is None
    clock[0] += 86400
    with c.transaction() as (_, state):
        expire_dispatches(state, clock[0])
        assert state['nodes'][node['id']]['direct_holder'] == 'sleeper'
        assert not state['nodes'][node['id']].get('executor_controls')


def test_recycle_keeps_native_account_until_s1_exit_confirmation(tmp_path):
    c, owner, project, _, tid = setup(tmp_path)
    node = c.snapshot(owner, tid)['nodes'][0]
    lease = claim(c, owner, node['id'], 'first')
    _, cleanup = c.sessions.recycle(owner, project['id'])
    assert cleanup['stopping'] == 1
    assert cleanup['desktop_stop']['manual_stop_required']
    snapshot = c.snapshot(owner, tid)
    assert snapshot['leases'][0]['id'] == lease['id']
    assert snapshot['desktop_stop']['manual_stop_required']
    with c.transaction() as (_, state):
        assert not state['outbox']


def test_native_five_modules_use_two_exclusive_and_three_shared_accounts(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=3, modules=5, exploration=True)
    nodes = c.snapshot(owner, tid)['nodes']
    leases = [claim(c, owner, node['id'], 'worker-' + str(index)) for index, node in enumerate(nodes)]
    assert all(leases)
    assert [lease['mode'] for lease in leases] == ['exclusive', 'exclusive', 'shared', 'shared', 'shared']
    assert len({tuple(lease['account_ids']) for lease in leases}) == 3
    assert len({tuple(lease['account_ids']) for lease in leases[2:]}) == 1
    assert all(lease['shared_enforcement'] == 'skill_only' for lease in leases[2:])
    with c.transaction() as (_, state):
        assert not state['policies'] and not state['runners'] and not state['outbox']


def test_shared_write_transition_waits_for_real_browser_release(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=1, exploration=True)
    nodes = c.snapshot(owner, tid)['nodes']
    first = claim(c, owner, nodes[0]['id'], 'first')
    second = claim(c, owner, nodes[1]['id'], 'second')
    assert first['mode'] == second['mode'] == 'shared'
    result = c.request_resources(owner, first['id'], {'next_phase': 'execution'})
    assert not result['continued'] and result['release_required']
    assert result['browser_stopped_required']
    assert result['next_action'] == 'finish_after_browser_stopped'
    assert len(c.snapshot(owner, tid)['leases']) == 2
    c.return_account(owner, first['runner_id'], {
        'lease_id': first['id'], 'executor_stopped': True, 'browser_stopped': True, 'outcome': 'yield',
    })
    snapshot = c.snapshot(owner, tid)
    assert snapshot['nodes'][0]['phase'] == 'execution'
    assert len(snapshot['leases']) == 1
    c.return_account(owner, second['runner_id'], {
        'lease_id': second['id'], 'executor_stopped': True, 'browser_stopped': True, 'outcome': 'completed',
    })
    c.schedule()
    assert c.snapshot(owner, tid)['leases'] == []
    resumed = claim(c, owner, nodes[0]['id'], 'first')
    assert resumed['mode'] == 'exclusive'


def test_last_shared_member_promotes_same_lease_without_action_check(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=1, exploration=True)
    nodes = c.snapshot(owner, tid)['nodes']
    first = claim(c, owner, nodes[0]['id'], 'first')
    assert first['mode'] == 'shared'
    result = c.request_resources(owner, first['id'], {'next_phase': 'execution'})
    assert result['continued'] is True
    assert result['lease_id'] == first['id']
    assert c.snapshot(owner, tid)['leases'][0]['mode'] == 'exclusive'


def test_restart_preserves_native_lease_and_stop_account_hold(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    node = c.snapshot(owner, tid)['nodes'][0]
    first = claim(c, owner, node['id'], 'first')
    reopened = Controller(c.store, c.clock)
    lease = reopened.snapshot(owner, tid)['leases'][0]
    assert lease['id'] == first['id'] and lease['epoch'] == first['epoch']
    assert not lease['revoked']
    reopened.control(owner, tid, {'action': 'stop', 'revision': 1, 'request_id': 'stop-after-restart'})
    again = Controller(c.store, c.clock).snapshot(owner, tid)
    assert again['desktop_stop']['manual_stop_required']
    assert again['leases'][0]['revoked']


def test_native_deployment_probe_does_not_invent_browser_exit(tmp_path):
    from api_test_tool.deployment_activity import activity
    c, owner, _, _, tid = setup(tmp_path)
    node = c.snapshot(owner, tid)['nodes'][0]
    claim(c, owner, node['id'], 'first')
    assert activity(c.store.root)['channels'] == 1
    c.control(owner, tid, {'action': 'stop', 'revision': 1, 'request_id': 'probe-stop'})
    snapshot = activity(c.store.root)
    assert snapshot['channels'] == 1
    assert snapshot['acknowledgements'] == 1


def test_native_stop_links_only_actual_thread_uuids_and_shows_confirmation_source(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    node = c.snapshot(owner, tid)['nodes'][0]
    claim(c, owner, node['id'], 'first')
    ref = '01a152f7-e927-7373-825c-e77eec1a1fd9'
    with c.transaction() as (_, state):
        state['nodes'][node['id']]['executor_dispatch']['executor_ref'] = 'thread:' + ref
        state['nodes'][node['id']]['native_exit_evidence'] = {'source': 'user_confirmation'}
    result = c.control(owner, tid, {'action': 'stop', 'revision': 1, 'request_id': 'link-stop'})
    row = result['desktop_stop']['required_sessions'][0]
    assert row['thread_url'] == 'codex://threads/' + ref
    assert row['exit_confirmation_source'] == 'user_confirmation'
    assert row['desktop_api_cancelled'] is False


def test_native_return_does_not_wait_for_nonexistent_runner_ack(tmp_path):
    from pathlib import Path
    from api_test_tool.deployment_activity import activity
    from api_test_tool.managed_service import ManagedService
    from api_test_tool.module_dispatch import observe_control
    c, owner, _, _, tid = setup(tmp_path, modules=1)
    node = c.snapshot(owner, tid)['nodes'][0]
    lease = claim(c, owner, node['id'], 'first')
    c.control(owner, tid, {'action': 'stop', 'revision': 1, 'request_id': 'stop-final'})
    with c.transaction() as (_, state):
        observe_control(state['nodes'][node['id']], 'first', c.clock(), exited=True)
        state['nodes'][node['id']]['native_exit_evidence'] = {'source': 'user_confirmation'}
    c.return_account(owner, lease['runner_id'], {
        'lease_id': lease['id'], 'executor_stopped': True, 'browser_stopped': True, 'outcome': 'blocked',
    })
    snapshot = c.snapshot(owner, tid)
    assert snapshot['nodes'][0]['stop_complete']
    assert not snapshot['nodes'][0]['settlement_ack_required']
    assert not snapshot['desktop_stop']['manual_stop_required']
    with c.transaction() as (_, state):
        receipt = state['direct_settlements'][lease['id']]
        assert receipt['native_browser'] and receipt['ack_required'] is False
        assert 'local_ack_at' not in receipt
    service = ManagedService(c, Path(__file__).parents[2] / 'api_test_tool' / 'static')
    service.finalize_settlement(owner, node['id'])
    assert activity(c.store.root) == {'rounds': 0, 'channels': 0, 'finalizations': 0, 'acknowledgements': 0}


def test_native_resume_rejects_unconfirmed_exit_atomically_but_other_node_can_resume(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=2)
    nodes = c.snapshot(owner, tid)['nodes']
    active = claim(c, owner, nodes[0]['id'], 'first')
    other = claim(c, owner, nodes[1]['id'], 'second')
    c.control(owner, tid, {'action': 'stop', 'revision': 1, 'request_id': 'stop-before-resume'})
    before = c.snapshot(owner, tid)
    with pytest.raises(Conflict, match='S1'):
        c.control(owner, tid, {'action': 'resume', 'revision': 2, 'request_id': 'too-early'})
    after = c.snapshot(owner, tid)
    assert after['tasks'][0]['revision'] == before['tasks'][0]['revision']
    assert after['tasks'][0]['intent'] == 'stop'
    assert after['desktop_stop']['manual_stop_required']
    c.return_account(owner, other['runner_id'], {
        'lease_id': other['id'], 'holder_id': 'second', 'executor_stopped': True,
        'browser_stopped': True, 'outcome': 'blocked',
        'native_exit_source': 'user_confirmation', 'control_revision': 2,
    })
    result = c.control(owner, tid, {
        'action': 'resume', 'revision': 2, 'request_id': 'resume-only-exited', 'node_ids': [nodes[1]['id']],
    })
    snapshot = c.snapshot(owner, tid)
    assert result['intent'] == 'run'
    assert snapshot['nodes'][0]['control_intent'] == 'stop'
    assert snapshot['nodes'][1]['state'] == 'queued'
    assert snapshot['leases'][0]['id'] == active['id']
    assert snapshot['desktop_stop']['manual_stop_required']


def test_native_aliases_count_one_physical_account_and_share_batch_identity(tmp_path):
    import copy
    c, owner, _, _, tid = setup(tmp_path, accounts=1, modules=3, exploration=True)
    with c.transaction() as (_, state):
        original = next(iter(state['accounts'].values()))
        duplicate = copy.deepcopy(original)
        duplicate['id'] = 'historical-duplicate'
        state['accounts'][duplicate['id']] = duplicate
    nodes = c.snapshot(owner, tid)['nodes']
    first = claim(c, owner, nodes[0]['id'], 'first')
    assert first['mode'] == 'shared'
    second = claim(c, owner, nodes[1]['id'], 'second')
    assert second['mode'] == 'shared'
    assert first['exploration_batch_id'] == second['exploration_batch_id']
    with c.transaction() as (_, state):
        aliases = list(state['accounts'].values())
        assert len({account['exploration_batch']['id'] for account in aliases}) == 1
        # A draining decision under either alias must close the physical account.
        aliases[1]['exploration_batch']['state'] = 'draining'
        aliases[1]['exploration_batch']['target_node'] = nodes[0]['id']
        state['nodes'][nodes[0]['id']]['phase'] = 'execution'
        from api_test_tool.resource_scheduler import ResourceScheduler
        scheduler = ResourceScheduler(c, state, c.clock())
        assert not scheduler.can_share(state['nodes'][nodes[2]['id']], aliases[0]['id'])
        assert not scheduler.can_share(state['nodes'][nodes[2]['id']], aliases[1]['id'])
