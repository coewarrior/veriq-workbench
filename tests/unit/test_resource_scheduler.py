"""Isolated resource contracts: no model, browser, or business environment calls."""
from api_test_tool.orchestration_storage import read_metadata
import pytest
from api_test_tool.orchestration import Controller, Conflict, DEFAULTS
from api_test_tool.resource_scheduler import ResourceScheduler
from api_test_tool.web_storage import Store


def env(tmp_path):
    store = Store(tmp_path)
    session, _ = store.session(None)
    owner = session['id']
    project = store.create_project(owner, 'resources', 'test.md', 'test')
    store.update_project(owner, project['id'], {'ui_target_url': 'https://target.test/login'})
    now = [1000.]
    controller = Controller(store, lambda: now[0])
    controller.register_host(owner, 'host', enforcement_evidence={
        'network_isolation': 'fixture', 'credential_isolation': 'fixture', 'tool_gate': 'fixture',
        'browser_context_isolation': 'fixture', 'version': 'fixture', 'simple_dispatch': 1,
        'direct_execution': 1, 'shared_exploration': 1, 'machine_id': 'machine'}, browser_slots=20, model_slots=20)
    return controller, owner, project['id'], now


def account(c, owner, pid, username, roles=('member',), pool='execution', tenant='tenant'):
    return c.add_account(owner, {'project_id': pid, 'target': 'https://target.test', 'identity': username,
                                'roles': list(roles), 'tenant': tenant, 'environment': 'test', 'pool': pool})['id']


def requirement(role='member', tenant='tenant'):
    return {'target': 'https://target.test', 'environment': 'test', 'tenant': tenant, 'role': role}


def task(c, owner, pid, key, requirements=None, **module):
    result = c.create_task(owner, {'project_id': pid, 'request_id': key, 'goal': key,
                                 'modules': [{'key': key, 'title': key, 'scope': key,
                                              'requirements': requirements or [], **module}]})
    node = next(n for n in c.snapshot(owner)['nodes'] if n['task_id'] == result['task_id'])
    return result['task_id'], node['id']


def policy(c, owner, pid, aid, compatible=True):
    policy_id = c.approve_policy(owner, pid, aid, version='fixture', evidence='isolated fixture proof',
                                 operations={'snapshot': {'adapter': 'playwright', 'effect': 'verified_read'}})
    with c.transaction() as (_, state):
        state['policies'][policy_id]['session_compatible'] = compatible
        state['policies'][policy_id]['id'] = policy_id
    return policy_id


def start_all(c, owner):
    for event in c.pending_events(owner, 'host'):
        if event['kind'] == 'start':
            c.acknowledge_start(owner, event['id'], thread_id='thread-' + event['node_id'], turn_id=event['id'])


def test_closed_batch_timestamp_is_stable_and_new_holders_are_still_reconciled(tmp_path):
    c, owner, pid, now = env(tmp_path)
    aid = account(c, owner, pid, 'batch-owner')
    with c.transaction() as (_, state):
        item = state['accounts'][aid]
        item['pool'] = 'exploration'
        batch = item['exploration_batch'] = {'id': 'batch', 'state': 'open', 'target_node': None}
        ResourceScheduler(c, state, now[0]).refresh()
        assert batch['closed'] == now[0]
        assert batch['state'] == 'closed' and item['pool'] == 'execution'
    with c.connect() as db:
        before = read_metadata(db)
    now[0] += 5
    with c.transaction() as (_, state):
        ResourceScheduler(c, state, now[0]).refresh()
    with c.connect() as db:
        assert read_metadata(db) == before
    with c.transaction() as (_, state):
        item = state['accounts'][aid]
        batch = item['exploration_batch']
        # A later real holder still refreshes membership and revocation, even
        # if the old batch is closed. No closed-state shortcut may skip it.
        state['leases']['fixture'] = {'id': 'fixture', 'node_id': 'new-member',
            'account_ids': [aid], 'mode': 'shared', 'revoked': True}
        ResourceScheduler(c, state, now[0]).refresh()
        assert batch['members'] == ['new-member']
        assert batch['state'] == 'draining'
        del state['leases']['fixture']
        item['pool'] = 'exploration'
        now[0] += 5
        ResourceScheduler(c, state, now[0]).refresh()
        assert batch['closed'] == now[0]
        assert batch['state'] == 'closed' and item['pool'] == 'execution'


@pytest.mark.parametrize('slots,ordinary,preparing', [(1,1,0), (2,0,1), (3,1,1), (4,2,1)])
def test_account_overflow_reserves_live_probe_within_actual_capacity(tmp_path, slots, ordinary, preparing):
    c, owner, pid, _ = env(tmp_path)
    with c.transaction() as (_, state):
        state['runners']['host']['browser_slots'] = slots
        state['runners']['host']['evidence']['automatic_exploration'] = 3
    for index in range(3):account(c, owner, pid, str(index))
    for index in range(5):task(c, owner, pid, str(index))
    c.schedule()
    leases = c.snapshot(owner)['leases']
    assert sum(l['browser_units'] for l in leases) <= slots
    assert sum(bool(l.get('exploration_bootstrap')) for l in leases) == preparing
    assert sum(not l.get('exploration_bootstrap') for l in leases) == ordinary


def test_no_overflow_keeps_free_execution_accounts_exclusive(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    with c.transaction() as (_, state):
        state['runners']['host']['browser_slots'] = 3
        state['runners']['host']['evidence']['automatic_exploration'] = 3
    for index in range(3):
        account(c, owner, pid, str(index))
        task(c, owner, pid, str(index))
    c.schedule()
    leases = c.snapshot(owner)['leases']
    assert len(leases) == 3
    assert all(l['mode'] == 'exclusive' and not l.get('exploration_bootstrap') for l in leases)


def test_capacity_growth_does_not_open_another_preparation_account(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    with c.transaction() as (_, state):
        state['runners']['host']['browser_slots'] = 3
        state['runners']['host']['evidence']['automatic_exploration'] = 3
    for index in range(3):account(c, owner, pid, str(index))
    for index in range(5):task(c, owner, pid, str(index))
    c.schedule()
    before = c.snapshot(owner)['leases']
    bootstrap = next(l['id'] for l in before if l.get('exploration_bootstrap'))
    with c.transaction() as (_, state):state['runners']['host']['browser_slots'] = 6
    c.schedule()
    leases = c.snapshot(owner)['leases']
    assert [l['id'] for l in leases if l.get('exploration_bootstrap')] == [bootstrap]
    assert len(leases) == 3
    assert sum(l['browser_units'] for l in leases) == 4



@pytest.mark.parametrize('exclusive_index', range(5))
@pytest.mark.parametrize('slots', [3,4,5,7])
def test_exclusive_only_member_cannot_consume_preparation_opportunity(tmp_path, exclusive_index, slots):
    c, owner, pid, _ = env(tmp_path)
    with c.transaction() as (_, state):
        state['runners']['host']['browser_slots'] = slots
        state['runners']['host']['evidence']['automatic_exploration'] = 3
    for index in range(3):account(c, owner, pid, str(index))
    nodes = [task(c, owner, pid, str(index))[1] for index in range(5)]
    with c.transaction() as (_, state):
        state['nodes'][nodes[exclusive_index]]['exclusive_exploration'] = True
    c.schedule()
    snapshot = c.snapshot(owner)
    leases = snapshot['leases']
    assert sum(l['browser_units'] for l in leases) <= slots
    assert sum(bool(l.get('exploration_bootstrap')) for l in leases) == 1
    assert sum(not l.get('exploration_bootstrap') for l in leases) == (1 if slots == 3 else 2)
    assert all(not l.get('exploration_bootstrap') for l in leases if l['node_id'] == nodes[exclusive_index])
    assert next(n for n in snapshot['nodes'] if n['id'] == nodes[exclusive_index])['exclusive_exploration']


def test_mixed_exclusive_requirements_without_overflow_keep_ordinary_grants(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    with c.transaction() as (_, state):
        state['runners']['host']['evidence']['automatic_exploration'] = 3
    for index in range(3):account(c, owner, pid, str(index))
    nodes = [task(c, owner, pid, str(index))[1] for index in range(3)]
    with c.transaction() as (_, state):state['nodes'][nodes[2]]['exclusive_exploration'] = True
    c.schedule()
    leases = c.snapshot(owner)['leases']
    assert len(leases) == 3 and not any(l.get('exploration_bootstrap') for l in leases)


@pytest.mark.parametrize('protected', [False, True])
def test_released_last_account_can_prepare_overflow_but_respects_protection(tmp_path, protected):
    c, owner, pid, _ = env(tmp_path)
    with c.transaction() as (_, state):
        state['runners']['host']['evidence']['automatic_exploration'] = 3
    account(c, owner, pid, 'last-free')
    _, waiting = task(c, owner, pid, 'execution-first')
    task(c, owner, pid, 'explorer-one')
    task(c, owner, pid, 'explorer-two')
    with c.transaction() as (_, state):
        state['nodes'][waiting].update(phase='execution', exploration_complete=True, protected=protected)
    c.schedule()
    leases = c.snapshot(owner)['leases']
    assert len(leases) == 1
    if protected:
        assert leases[0]['node_id'] == waiting and not leases[0].get('exploration_bootstrap')
    else:
        assert leases[0]['node_id'] != waiting and leases[0]['exploration_bootstrap']


@pytest.mark.parametrize('exclusive_index', [None,0,1,2,3,4])
def test_incremental_capacity_preserves_a_preparation_opportunity(tmp_path, exclusive_index):
    c, owner, pid, _ = env(tmp_path)
    with c.transaction() as (_, state):
        state['runners']['host']['browser_slots'] = 1
        state['runners']['host']['evidence']['automatic_exploration'] = 3
    for index in range(3):account(c, owner, pid, str(index))
    nodes = [task(c, owner, pid, str(index))[1] for index in range(5)]
    if exclusive_index is not None:
        with c.transaction() as (_, state):state['nodes'][nodes[exclusive_index]]['exclusive_exploration'] = True
    for slots in [1,2,3,6]:
        with c.transaction() as (_, state):state['runners']['host']['browser_slots'] = slots
        c.schedule()
        leases = c.snapshot(owner)['leases']
        assert sum(l['browser_units'] for l in leases) <= slots
        assert sum(bool(l.get('exploration_bootstrap')) for l in leases) <= 1
        assert len(leases) < 3 or any(l.get('exploration_bootstrap') for l in leases)
    assert sum(bool(l.get('exploration_bootstrap')) for l in leases) == 1
    assert sum(not l.get('exploration_bootstrap') for l in leases) == 2

def test_identity_matching_without_prelogin_and_preserves_unique_role(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    flexible = account(c, owner, pid, 'admin', ('member', 'admin'))
    limited = account(c, owner, pid, 'member')
    _, member = task(c, owner, pid, 'member', [requirement()])
    _, admin = task(c, owner, pid, 'admin', [requirement('admin')])
    c.schedule()
    leases = {l['node_id']: l for l in c.snapshot(owner)['leases']}
    assert leases[member]['account_ids'] == [limited]
    assert leases[admin]['account_ids'] == [flexible]
    assert all(not a['verified_identity'] for a in c.snapshot(owner)['accounts'])


def test_environment_label_cannot_duplicate_real_login_capacity(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    account(c, owner, pid, 'same')
    with pytest.raises(Conflict, match='不可通过不同角色或租户'):
        c.add_account(owner, {'project_id': pid, 'target': 'https://target.test', 'identity': 'same', 'environment': 'renamed'})
    assert len(c.snapshot(owner)['accounts']) == 1


def test_shared_exploration_uses_verified_policy_and_distinct_contexts(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    aid = account(c, owner, pid, 'explorer', pool='exploration')
    approved = policy(c, owner, pid, aid)
    task(c, owner, pid, 'one'); task(c, owner, pid, 'two')
    c.schedule()
    leases = c.snapshot(owner)['leases']
    assert len(leases) == 2
    assert all(l['mode'] == 'shared' and l['policy_id'] == approved for l in leases)
    assert len({l['context_id'] for l in leases}) == 2
    assert all(l['account_ids'] == [aid] for l in leases)


def test_unknown_shared_login_compatibility_keeps_exclusive_path(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    aid = account(c, owner, pid, 'explorer', pool='exploration')
    policy(c, owner, pid, aid, compatible=False)
    task(c, owner, pid, 'one'); task(c, owner, pid, 'two')
    c.schedule()
    leases = c.snapshot(owner)['leases']
    assert len(leases) == 1 and leases[0]['mode'] == 'exclusive'


def test_last_explorer_promotes_existing_lease_after_members_exit(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    aid = account(c, owner, pid, 'explorer', pool='exploration'); policy(c, owner, pid, aid)
    task(c, owner, pid, 'one'); task(c, owner, pid, 'two')
    c.schedule(); start_all(c, owner)
    first, second = c.snapshot(owner)['leases']
    result = c.request_resources(owner, first['id'], {'next_phase': 'execution'})
    assert not result['continued']
    with c.transaction() as (_, state):
        assert state['accounts'][aid]['exploration_batch']['state'] == 'draining'
    task(c, owner, pid, 'late'); c.schedule()
    assert len(c.snapshot(owner)['leases']) == 2
    c.return_account(owner, 'host', {'lease_id': second['id'], 'executor_stopped': True, 'outcome': 'completed'})
    c.schedule()
    lease = next(l for l in c.snapshot(owner)['leases'] if l['id'] == first['id'])
    assert lease['mode'] == 'exclusive' and lease['context_id'] == first['context_id']
    assert lease['account_ids'] == [aid]


def test_protected_waiter_prevents_second_exploration_bypass(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    aid = account(c, owner, pid, 'explorer', pool='exploration'); policy(c, owner, pid, aid)
    _, explorer = task(c, owner, pid, 'one'); task(c, owner, pid, 'two')
    c.schedule(); start_all(c, owner)
    first, second = c.snapshot(owner)['leases']
    _, waiter = task(c, owner, pid, 'waiting', exclusive_exploration=True)
    with c.transaction() as (_, state): state['nodes'][waiter]['protected'] = True
    c.return_account(owner, 'host', {'lease_id': second['id'], 'executor_stopped': True, 'outcome': 'completed'})
    result = c.request_resources(owner, first['id'], {'next_phase': 'execution'})
    assert result['release_required'] and not result['continued']
    c.return_account(owner, 'host', {'lease_id': first['id'], 'executor_stopped': True, 'outcome': 'yield'})
    c.schedule()
    assert c.snapshot(owner)['leases'][0]['node_id'] == waiter


def test_unknown_operation_holds_account_after_browser_exit_and_resolves_once(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    account(c, owner, pid, 'one'); task(c, owner, pid, 'one'); task(c, owner, pid, 'two')
    c.schedule(); lease = c.snapshot(owner)['leases'][0]
    with c.transaction() as (_, state):
        state['operations']['write'] = {'id': 'write', 'lease_id': lease['id'], 'node_id': lease['node_id'], 'state': 'unknown'}
    request = {'lease_id': lease['id'], 'executor_stopped': True, 'outcome': 'blocked'}
    assert c.return_account(owner, 'host', request)['retained']
    assert c.return_account(owner, 'host', request)['retained']
    c.schedule(); held = c.snapshot(owner)['leases']
    assert len(held) == 1 and held[0]['resource_hold'] and held[0]['browser_units'] == 0
    assert c.active_count() == 0  # durable resource evidence must not block deployment draining
    with pytest.raises(Conflict, match='仍未核实'):
        c.resolve_resource_hold(owner, lease['id'], 'browser exited')
    with c.transaction() as (_, state): state['operations']['write']['state'] = 'confirmed'
    assert c.resolve_resource_hold(owner, lease['id'], 'original object result verified')['released']
    c.schedule()
    assert c.snapshot(owner)['leases'][0]['node_id'] != lease['node_id']


def test_invalid_child_plan_does_not_rollback_account_return(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    account(c, owner, pid, 'one'); task(c, owner, pid, 'one')
    c.schedule(); lease = c.snapshot(owner)['leases'][0]
    result = c.return_account(owner, 'host', {'lease_id': lease['id'], 'executor_stopped': True,
                                           'children': [{'title': 'bad', 'scope': 'bad', 'depends_on': ['missing']}]})
    assert result['released'] and result['plan_error']
    assert not c.snapshot(owner)['leases']
    node = c.snapshot(owner)['nodes'][0]
    assert node['state'] == 'blocked' and node['finalization_pending']


def test_whole_set_is_atomic_and_identity_mismatch_is_explicit(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    aid = account(c, owner, pid, 'member')
    _, missing = task(c, owner, pid, 'admin', [requirement('admin')])
    _, multi = task(c, owner, pid, 'two', [requirement(), requirement()])
    c.schedule()
    assert not c.snapshot(owner)['leases']
    assert all('资源配置不足' in n['reason'] for n in c.snapshot(owner)['nodes'])
    assert not c.snapshot(owner)['accounts'][0]['verified_identity']


def test_resource_wait_cycle_is_recorded_without_releasing_preserved_scene(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    a = account(c, owner, pid, 'a'); b = account(c, owner, pid, 'b')
    task(c, owner, pid, 'one'); task(c, owner, pid, 'two'); c.schedule(); start_all(c, owner)
    first, second = c.snapshot(owner)['leases']
    one = c.request_resources(owner, first['id'], {'account_ids': [a, b], 'checkpoint': {'retained_conditions': ['keep object']}})
    two = c.request_resources(owner, second['id'], {'account_ids': [a, b], 'checkpoint': {'retained_conditions': ['keep other object']}})
    assert not one['continued'] and two['cycle']
    assert not two['release_required']
    assert len(c.snapshot(owner)['leases']) == 2


def test_stop_unallocated_module_finalizes_without_stopping_other_module(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    result = c.create_task(owner, {'project_id': pid, 'request_id': 'pair', 'goal': 'pair',
                                  'modules': [{'key': str(i), 'title': str(i), 'requirements': []} for i in range(2)]})
    nodes = c.snapshot(owner)['nodes']
    c.control(owner, result['task_id'], {'action': 'stop', 'revision': 1, 'request_id': 'stop-one', 'node_ids': [nodes[0]['id']]})
    state = c.snapshot(owner)
    assert state['tasks'][0]['intent'] == 'run'
    stopped = next(n for n in state['nodes'] if n['id'] == nodes[0]['id'])
    assert stopped['state'] == 'stopped' and stopped['finalization_pending']
    account(c, owner, pid, 'one'); c.schedule()
    assert c.snapshot(owner)['leases'][0]['node_id'] == nodes[1]['id']


def test_direct_uses_browser_budget_not_background_model_slots(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    account(c, owner, pid, 'one'); account(c, owner, pid, 'two')
    for key in ('one', 'two'):
        result = c.create_task(owner, {'project_id': pid, 'request_id': key, 'goal': key, 'execution_route': 'local_browser',
                                      'modules': [{'key': key, 'title': key, 'requirements': []}]})
        with c.transaction() as (_, state):
            node = state['nodes'][state['tasks'][result['task_id']]['node_ids'][0]]
            node.update(direct_holder=key, actor_seen=1000.)
    with c.transaction() as (_, state): state['runners']['host']['model_slots'] = 0
    c.schedule()
    assert len(c.snapshot(owner)['leases']) == 2


def test_default_mcp_resource_arguments_do_not_add_identity_gate(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    account(c, owner, pid, 'one'); task(c, owner, pid, 'one'); c.schedule(); start_all(c, owner)
    lease = c.snapshot(owner)['leases'][0]
    result = c.request_resources(owner, lease['id'], {'next_phase': 'execution', 'requirements': None,
                                                     'account_ids': [], 'locks': [], 'checkpoint': {}})
    assert result['continued'] and result['account_ids'] == lease['account_ids']


def test_changed_identity_set_requires_old_browser_return_before_new_grant(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    a = account(c, owner, pid, 'one'); b = account(c, owner, pid, 'two')
    task(c, owner, pid, 'one'); c.schedule(); start_all(c, owner)
    lease = c.snapshot(owner)['leases'][0]
    other = next(x for x in [a, b] if x not in lease['account_ids'])
    result = c.request_resources(owner, lease['id'], {'account_ids': [other]})
    assert result['release_required'] and not result['continued']
    assert c.snapshot(owner)['leases'][0]['account_ids'] == lease['account_ids']
    c.return_account(owner, 'host', {'lease_id': lease['id'], 'executor_stopped': True, 'outcome': 'yield'})
    c.schedule()
    assert c.snapshot(owner)['leases'][0]['account_ids'] == [other]


def test_observing_retained_scene_never_implicitly_requests_close(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    account(c, owner, pid, 'one'); task(c, owner, pid, 'one'); c.schedule()
    lease = c.snapshot(owner)['leases'][0]
    c.return_account(owner, 'host', {'lease_id': lease['id'], 'executor_stopped': True, 'outcome': 'blocked',
                                   'checkpoint': {'retain_browser': True}, 'browser_stopped': False, 'scene_retained': True})
    result = c.resolve_resource_hold(owner, lease['id'], 'observation only', release=False)
    assert not result['close_required'] and not result['released']
    held = c.snapshot(owner)['leases'][0]
    assert not held.get('resolution_requested') and not held.get('resource_release_evidence')
    assert held['browser_units'] == 1


def test_reservation_blocks_competitor_and_expires_without_stealing_active_account(tmp_path):
    c, owner, pid, now = env(tmp_path)
    a = account(c, owner, pid, 'one'); b = account(c, owner, pid, 'two')
    _, active = task(c, owner, pid, 'active')
    with c.transaction() as (_, state): state['nodes'][active]['requested_account_ids'] = [b]
    c.schedule(); start_all(c, owner)
    _, waiting = task(c, owner, pid, 'pair', [requirement(), requirement()])
    with c.transaction() as (_, state): state['nodes'][waiting]['protected'] = True
    c.reserve(owner, waiting, [a], release_evidence='observed original closeout')
    _, other = task(c, owner, pid, 'other')
    c.schedule()
    assert len(c.snapshot(owner)['leases']) == 1
    now[0] += DEFAULTS['reservation_seconds'] + 1
    with c.transaction() as (_, state): state['runners']['host']['heartbeat'] = now[0]
    c.schedule()
    snapshot = c.snapshot(owner)
    assert any(l['node_id'] == active and l['account_ids'] == [b] for l in snapshot['leases'])
    assert any(l['node_id'] == other and l['account_ids'] == [a] for l in snapshot['leases'])
    node = next(n for n in snapshot['nodes'] if n['id'] == waiting)
    assert node['reservation'] is None and node['reservation_expirations'] == 1 and node['protected']


def test_machine_connections_do_not_double_browser_budget(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    account(c, owner, pid, 'one'); account(c, owner, pid, 'two')
    with c.transaction() as (_, state):
        import copy
        state['runners']['host']['browser_slots'] = 1
        second = copy.deepcopy(state['runners']['host']); second['id'] = 'same-machine-second-connection'
        state['runners'][second['id']] = second
    task(c, owner, pid, 'one'); task(c, owner, pid, 'two'); c.schedule()
    assert len(c.snapshot(owner)['leases']) == 1


def test_free_execution_accounts_remain_exclusive_before_overflow_batch(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    for name in ('one', 'two', 'three'):
        aid = account(c, owner, pid, name)
        policy(c, owner, pid, aid)
    for key in ('one', 'two', 'three', 'four', 'five'):
        task(c, owner, pid, key)
    c.schedule()
    leases = c.snapshot(owner)['leases']
    assert len(leases) == 5
    assert sum(l['mode'] == 'exclusive' for l in leases) == 2
    shared = [l for l in leases if l['mode'] == 'shared']
    assert len(shared) == 3 and len({l['account_ids'][0] for l in shared}) == 1


def test_dedicated_explorer_does_not_take_free_execution_accounts_into_shared_mode(tmp_path):
    c, owner, pid, _ = env(tmp_path)
    for name in ('one', 'two', 'three'): account(c, owner, pid, name)
    aid = account(c, owner, pid, 'explorer', pool='exploration'); policy(c, owner, pid, aid)
    for key in ('one', 'two', 'three', 'four', 'five'): task(c, owner, pid, key)
    c.schedule()
    leases = c.snapshot(owner)['leases']
    assert len(leases) == 5 and sum(l['mode'] == 'exclusive' for l in leases) == 3
    assert all(l['account_ids'] == [aid] for l in leases if l['mode'] == 'shared')
