"""Actual native login capacity is independent of account/tab/chat counts."""
import pytest

from api_test_tool.native_contexts import choose_context, lease_context_fields, origin, register_environment
from api_test_tool.orchestration import Conflict
from test_native_scheduler import claim, setup


def environment(context_id='tab-1', isolated=False):
    value = {'host_id': 'local', 'browser': 'iab', 'context_id': context_id,
             'origin': 'https://test.example',
             'isolation': 'isolated' if isolated else 'shared_profile',
             'evidence': '公开工具实际返回的浏览器环境；无凭据'}
    if isolated:
        value['capability_evidence'] = {
            'source': 'public_tool', 'capability': 'isolated_login_context',
            'context_id': context_id, 'reference': '测试替身公开独立上下文能力及实际返回'}
    return value


def register(controller, owner, node_id, value):
    with controller.transaction() as (_, state):
        return register_environment(state, state['nodes'][node_id], owner, value)


def test_hidden_tabs_do_not_multiply_shared_profile_capacity(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=2)
    nodes = c.snapshot(owner, tid)['nodes']
    first_env = register(c, owner, nodes[0]['id'], environment('hidden-tab-a'))
    second_env = register(c, owner, nodes[1]['id'], environment('hidden-tab-b'))
    assert first_env['environment_key'] == second_env['environment_key']
    first = claim(c, owner, nodes[0]['id'], 'first')
    assert first['browser_units'] == 1
    assert first['native_context_binding']['login_state'] == 'unverified'
    assert claim(c, owner, nodes[1]['id'], 'second') is None
    waiting = c.snapshot(owner, tid)['nodes'][1]
    assert waiting['resource_wait']['kind'] == 'native_environment_unavailable'
    assert '浏览器' in waiting['reason'] and '账号不一致' not in waiting['reason']
    c.return_account(owner, first['runner_id'], {
        'lease_id': first['id'], 'executor_stopped': True, 'browser_stopped': True,
        'outcome': 'completed', 'result': 'partial'})
    second = claim(c, owner, nodes[1]['id'], 'second')
    assert second['native_context_binding']['environment_key'] == first_env['environment_key']


def test_real_independent_contexts_enable_account_parallelism(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=2)
    nodes = c.snapshot(owner, tid)['nodes']
    for index, node in enumerate(nodes):
        register(c, owner, node['id'], environment('actual-context-' + str(index), True))
    leases = [claim(c, owner, node['id'], 'worker-' + str(index)) for index, node in enumerate(nodes)]
    assert all(leases)
    assert len({item['native_context_binding']['environment_key'] for item in leases}) == 2
    assert len({item['account_ids'][0] for item in leases}) == 2


def test_isolation_requires_public_capability_and_context_evidence(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    nid = c.snapshot(owner, tid)['nodes'][0]['id']
    value = environment('session-name', True)
    value.pop('capability_evidence')
    with pytest.raises(ValueError, match='独立登录上下文'):
        register(c, owner, nid, value)
    value = environment('actual-context', True)
    value['capability_evidence']['context_id'] = 'different-context'
    with pytest.raises(ValueError, match='独立登录上下文'):
        register(c, owner, nid, value)


def test_browser_aliases_share_capacity_and_numeric_ids_are_rejected(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    nodes = c.snapshot(owner, tid)['nodes']
    first = register(c, owner, nodes[0]['id'], environment())
    alias = environment('another-hidden-tab')
    alias['browser'] = 'In-App Browser'
    second = register(c, owner, nodes[1]['id'], alias)
    assert first['environment_key'] == second['environment_key']
    for browser in ('3', 'browser-3', 'iab-session-4'):
        with pytest.raises(ValueError, match='browser'):
            register(c, owner, nodes[1]['id'], {**alias, 'browser': browser})


@pytest.mark.parametrize('target', ['', None, 'https://test.example:invalid', 'https://test.example:65536'])
def test_malformed_legacy_origin_conservatively_occupies_context(tmp_path, target):
    c, owner, _, _, tid = setup(tmp_path, accounts=2)
    nodes = c.snapshot(owner, tid)['nodes']
    lease = claim(c, owner, nodes[0]['id'], 'legacy')
    register(c, owner, nodes[1]['id'], environment())
    with c.transaction() as (_, state):
        state['accounts'][lease['account_ids'][0]]['target'] = target
        new_account = next(aid for aid in state['accounts'] if aid not in lease['account_ids'])
        assert choose_context(state, state['nodes'][nodes[1]['id']], [new_account]) is None


@pytest.mark.parametrize('plain, explicit', [
    ('https://test.example', 'https://test.example:443'),
    ('http://test.example', 'http://test.example:80'),
    ('https://[::1]', 'https://[::1]:443'),
])
def test_default_ports_do_not_multiply_context_capacity(tmp_path, plain, explicit):
    c, owner, _, _, tid = setup(tmp_path)
    nodes = c.snapshot(owner, tid)['nodes']
    first = register(c, owner, nodes[0]['id'], {**environment(), 'origin': plain})
    second = register(c, owner, nodes[1]['id'], {**environment(), 'origin': explicit})
    assert first['origin'] == second['origin'] == plain
    assert first['environment_key'] == second['environment_key']


def test_origin_keeps_nondefault_port_and_rejects_invalid_ports():
    assert origin('https://TEST.example:8443/path') == 'https://test.example:8443'
    assert origin('http://[::1]:8080') == 'http://[::1]:8080'
    for value in ('https://test.example:invalid', 'https://test.example:65536', 'https://[invalid]'):
        with pytest.raises(ValueError, match='origin'):
            origin(value)


def test_new_protocol_missing_environment_waits_without_account_lease(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    nid = c.snapshot(owner, tid)['nodes'][0]['id']
    with c.transaction() as (_, state):
        state['nodes'][nid]['native_context_protocol'] = 1
    assert claim(c, owner, nid, 'worker') is None
    assert not c.snapshot(owner, tid)['leases']


def test_legacy_inflight_unknown_context_is_not_stolen_or_revoked(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=2)
    nodes = c.snapshot(owner, tid)['nodes']
    original = claim(c, owner, nodes[0]['id'], 'legacy')
    register(c, owner, nodes[1]['id'], environment())
    assert claim(c, owner, nodes[1]['id'], 'new') is None
    leases = c.snapshot(owner, tid)['leases']
    assert len(leases) == 1 and leases[0]['id'] == original['id'] and not leases[0]['revoked']


def test_retained_or_unknown_lease_keeps_native_context_reserved(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=2)
    nodes = c.snapshot(owner, tid)['nodes']
    for node in nodes:
        register(c, owner, node['id'], environment())
    first = claim(c, owner, nodes[0]['id'], 'first')
    with c.transaction() as (_, state):
        state['nodes'][nodes[0]['id']]['checkpoint']['must_preserve'] = ['原服务端结果仍需核实']
    result = c.return_account(owner, first['runner_id'], {
        'lease_id': first['id'], 'executor_stopped': True, 'browser_stopped': True,
        'outcome': 'blocked', 'result': 'blocked'})
    assert result['retained'] and not result['released']
    assert claim(c, owner, nodes[1]['id'], 'second') is None


def test_shared_exploration_keeps_independent_context_and_atomic_promotion(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=1, exploration=True)
    nodes = c.snapshot(owner, tid)['nodes']
    for index, node in enumerate(nodes):
        register(c, owner, node['id'], environment('isolated-' + str(index), True))
    first = claim(c, owner, nodes[0]['id'], 'first')
    second = claim(c, owner, nodes[1]['id'], 'second')
    assert first['mode'] == second['mode'] == 'shared'
    c.return_account(owner, first['runner_id'], {
        'lease_id': first['id'], 'executor_stopped': True, 'browser_stopped': True,
        'outcome': 'completed', 'result': 'partial'})
    promoted = c.request_resources(owner, second['id'], {'next_phase': 'execution'})
    assert promoted['continued'] and promoted['lease_id'] == second['id']
    lease = c.snapshot(owner, tid)['leases'][0]
    assert lease['context_id'] == second['context_id'] and lease['browser_units'] == 1
    assert lease['native_context_binding'] == second['native_context_binding']


def test_preview_occupies_same_context_before_next_candidate(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=2)
    nodes = c.snapshot(owner, tid)['nodes']
    for node in nodes:
        register(c, owner, node['id'], environment())
    with c.transaction() as (_, state):
        accounts = list(state['accounts'])
        first = state['nodes'][nodes[0]['id']]
        second = state['nodes'][nodes[1]['id']]
        fields = lease_context_fields(state, first, accounts[:1])
        preview = {**state, 'leases': {'wake:first': {
            'id': 'wake:first', 'node_id': first['id'], 'native_browser': True,
            'account_ids': accounts[:1], 'mode': 'exclusive', 'revoked': False, **fields}}}
        assert choose_context(preview, second, accounts[1:]) is None
        assert choose_context(state, second, accounts[1:]) is not None


def test_multi_account_stage_requires_complete_distinct_context_set(tmp_path):
    c, owner, _, _, tid = setup(tmp_path, accounts=2)
    nid = c.snapshot(owner, tid)['nodes'][0]['id']
    register(c, owner, nid, environment('first', True))
    with c.transaction() as (_, state):
        assert choose_context(state, state['nodes'][nid], list(state['accounts'])) is None
    register(c, owner, nid, environment('second', True))
    with c.transaction() as (_, state):
        binding = choose_context(state, state['nodes'][nid], list(state['accounts']))
        assert len(binding['contexts']) == 2


def test_active_binding_cannot_be_changed_to_another_context(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    nid = c.snapshot(owner, tid)['nodes'][0]['id']
    register(c, owner, nid, environment('first', True))
    lease = claim(c, owner, nid, 'first')
    with pytest.raises(Conflict, match='不能热迁移'):
        register(c, owner, nid, environment('second', True))
    assert c.snapshot(owner, tid)['leases'][0]['native_context_binding'] == lease['native_context_binding']
