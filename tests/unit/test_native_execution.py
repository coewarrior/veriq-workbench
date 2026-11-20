"""The native route never forwards browser actions or polls a runner."""
from pg_support import observe
from pathlib import Path
import pytest

from api_test_tool.direct_wait import direct_call_and_wait, lifecycle_call_and_wait
from api_test_tool.managed_service import ManagedService
from api_test_tool.native_execution import NativeExecution
from api_test_tool.orchestration import Conflict
from test_native_scheduler import setup

STATIC = Path(__file__).parents[2] / 'api_test_tool' / 'static'


def test_claim_registration_and_allocation_commit_together(tmp_path, monkeypatch):
    from api_test_tool import database
    from api_test_tool.resource_scheduler import ResourceScheduler
    from test_native_contexts import environment
    c, owner, _, _, tid=setup(tmp_path,modules=1,current_protocol=True)
    service=ManagedService(c,STATIC);node=c.snapshot(owner,tid)['nodes'][0]
    def conflict(*args,**kwargs):raise database.OperationalError('database is locked')
    monkeypatch.setattr(ResourceScheduler,'schedule',conflict)
    with pytest.raises(database.OperationalError):
        service.direct.call(owner,{'action':'claim','task_id':tid,'node_id':node['id'],
            'holder_id':'original','executor_ref':'thread:original',
            'arguments':{'browser_environment':environment('real-context',True)}})
    saved=c.snapshot(owner,tid)
    assert not saved['leases']
    assert not saved['nodes'][0].get('direct_holder')
    assert not saved['nodes'][0].get('native_claim_pending')
    assert not saved['nodes'][0].get('executor_dispatch')


def ready(tmp_path):
    controller, owner, project, clock, tid = setup(tmp_path)
    service = ManagedService(controller, STATIC)
    node = controller.snapshot(owner, tid)['nodes'][0]
    arguments = {'task_id': tid, 'node_id': node['id'], 'holder_id': 'native-chat',
                 'executor_ref': 'thread:01a1576c-6fb5-7ce3-9ade-3f4e6c5dab60',
                 'arguments': {'browser_environment': {
                     'host_id': 'local', 'browser': 'iab', 'context_id': 'default',
                     'origin': 'https://test.example', 'isolation': 'shared_profile',
                     'evidence': '测试替身公开 IAB 共享登录上下文'}}}
    lease = service.direct.call(owner, {**arguments, 'action': 'claim'})
    return controller, service, owner, project, clock, {**arguments, 'lease_id': lease['lease_id']}


@pytest.mark.parametrize('lease, node, task, expected', [
    ('active', 'other-node', 'other-task', True),
    ('non-native', 'native-node', 'native-task', False),
    ('settled', 'other-node', 'other-task', True),
    (None, 'native-node', 'other-task', True),
    (None, 'missing-node', 'native-task', True),
    (None, None, 'native-task', True),
    ('missing', None, 'missing-task', False),
])
def test_route_uses_current_projection_and_preserves_fallback_priority(
        tmp_path, monkeypatch, lease, node, task, expected):
    from types import SimpleNamespace
    from api_test_tool import native_execution
    c, owner, _, _, _ = setup(tmp_path)
    native = NativeExecution(ManagedService(c, STATIC).direct)
    with c.transaction() as (_, state):
        state['tasks'].update({
            'native-task': {'owner': owner, 'execution_route': 'native_browser'},
            'other-task': {'owner': owner, 'execution_route': 'local_browser'},
        })
        state['nodes'].update({'native-node': {'task_id': 'native-task'},
                               'other-node': {'task_id': 'other-task'}})
        state['leases'].update({'active': {'node_id': 'native-node'},
                                'non-native': {'node_id': 'other-node'}})
        state.setdefault('direct_settlements', {}).update({
            'active': {'node_id': 'other-node'}, 'non-native': {'node_id': 'native-node'},
            'settled': {'node_id': 'native-node'}})
    def forbidden(*args):
        raise AssertionError('routing must not materialize scheduler metadata')
    monkeypatch.setattr(native_execution, 'read_metadata_without_history', forbidden)
    args = {'lease_id': lease, 'node_id': node, 'task_id': task}
    assert native.applies(owner, args) is expected
    assert native.applies('another-owner', args) is False
    with c.transaction() as (_, state):
        state['tasks']['native-task']['execution_route'] = 'local_browser'
    assert native.applies(owner, args) is False


def test_route_parameters_treat_identifiers_as_literal_keys(tmp_path):
    c, owner, _, _, _ = setup(tmp_path)
    lease_id, node_id, task_id = 'lease.\"\'; --', 'node.\"雪', 'task.\"雪'
    with c.transaction() as (_, state):
        state['leases'][lease_id] = {'node_id': node_id}
        state['nodes'][node_id] = {'task_id': task_id}
        state['tasks'][task_id] = {'owner': owner, 'execution_route': 'native_browser'}
    assert NativeExecution(ManagedService(c, STATIC).direct).applies(owner, {'lease_id': lease_id})


@pytest.mark.parametrize('stopped', [False, True])
def test_fresh_finish_does_not_take_writer_before_actual_release(tmp_path, monkeypatch, stopped):
    c, service, owner, _, _, args = ready(tmp_path)
    writers, before_release = [], []
    connect, return_account = c.connect, c.return_account
    def traced_connect():
        db = connect()
        return observe(db, lambda sql: writers.append(sql) if 'pg_advisory_xact_lock' in sql else None)
    def release(*values, **kwargs):
        before_release.append(list(writers))
        return return_account(*values, **kwargs)
    monkeypatch.setattr(c, 'connect', traced_connect)
    monkeypatch.setattr(c, 'return_account', release)
    result = service.direct.call(owner, {**args, 'action': 'finish', 'reason': 'own pages closed',
        'arguments': {'browser_stopped': stopped}})
    if stopped:
        assert before_release == [[]]
        assert result['released'] and not c.snapshot(owner)['leases']
        exited = c.snapshot(owner)['nodes'][0]
        assert exited['native_browser_stopped'] is True
        assert exited['native_exit_evidence']['source'] == 'executor_reported'
    else:
        assert writers == []
        assert not result['released'] and result['manual_stop_required']
        assert c.snapshot(owner)['leases'][0]['id'] == args['lease_id']


def test_finish_retry_rechecks_settlement_holder_under_writer(tmp_path, monkeypatch):
    from contextlib import contextmanager
    c, service, owner, _, _, args = ready(tmp_path)
    request = {**args, 'action': 'finish', 'reason': 'own pages closed',
               'arguments': {'browser_stopped': True}}
    assert service.direct.call(owner, request)['released']
    native = NativeExecution(service.direct)
    authorize = native._authorization_state
    @contextmanager
    def raced_authorization(**kwargs):
        with authorize(**kwargs) as state:
            yield state
        if not kwargs['writable']:
            with c.transaction() as (_, current):
                current['direct_settlements'][args['lease_id']]['holder_id'] = 'replacement-holder'
    monkeypatch.setattr(native, '_authorization_state', raced_authorization)
    with pytest.raises(PermissionError, match='回执不属于当前聊天'):
        native.call(owner, request)
    with c.transaction() as (_, state):
        assert state['direct_settlements'][args['lease_id']]['holder_id'] == 'replacement-holder'
        assert len(state['nodes'][args['node_id']]['outcome_history']) == 1
        assert not state['leases']


def test_native_claim_context_credentials_no_browser_protocol(tmp_path):
    c, s, owner, _, _, args = ready(tmp_path)
    context = s.direct.call(owner, {**args, 'action': 'context'})
    assert context['mode'] == 'native_browser'
    assert context['execution_host']['browser_tool'] == 'cua_repl'
    assert 'default_known_flow' not in context['execution_host']
    assert context['dispatch'] is None
    secret = s.direct.call(owner, {**args, 'action': 'credentials'})
    assert secret['account_id'] == context['accounts'][0]['id']
    with pytest.raises(ValueError, match='原生'):
        s.direct.call(owner, {**args, 'action': 'browser', 'browser_action': 'click'})
    with pytest.raises(PermissionError):
        s.direct.call(owner, {**args, 'action': 'credentials', 'holder_id': 'other-chat'})
    with c.transaction() as (_, state):
        assert not state['outbox'] and not list(state['direct_commands']) and not list(state['operations'])


def test_native_no_heartbeat_timeout_but_explicit_stop_revokes_credentials(tmp_path):
    c, s, owner, _, clock, args = ready(tmp_path)
    clock[0] += 86400
    c.schedule()
    assert s.direct.call(owner, {**args, 'action': 'credentials'})['account_id']
    c.control(owner, args['task_id'], {'action': 'stop', 'revision': 1, 'request_id': 'stop'})
    with pytest.raises(Conflict):
        s.direct.call(owner, {**args, 'action': 'credentials'})
    assert s.direct.call(owner, {**args, 'action': 'context'})['manual_stop_required']
    assert c.snapshot(owner)['leases']


def test_native_finish_requires_real_cleanup_and_is_idempotent(tmp_path):
    c, s, owner, _, _, args = ready(tmp_path)
    pending = s.direct.call(owner, {**args, 'action': 'finish'})
    assert pending['manual_stop_required'] and not pending['released']
    assert c.snapshot(owner)['leases']
    request = {**args, 'action': 'finish', 'outcome': 'blocked',
               'reason': '本任务页面已关闭，未执行部分保留',
               'arguments': {'browser_stopped': True}}
    result = s.direct.call(owner, request)
    assert result['released'] and result['exit_source'] == 'executor_reported'
    assert not c.snapshot(owner)['leases']
    assert s.direct.call(owner, request)['released']
    node = c.snapshot(owner)['nodes'][0]
    assert node['native_exit_evidence']['source'] == 'executor_reported'


def test_s1_manual_confirmation_cannot_release_running_task(tmp_path):
    c, s, owner, _, _, args = ready(tmp_path)
    native = NativeExecution(s.direct)
    data = {'revision': 1, 'node_ids': [args['node_id']], 'executor_stopped': True,
            'browser_stopped': True, 'reason': '已在桌面停止本会话并关闭本任务页面'}
    with pytest.raises(Conflict):
        native.confirm_exit(owner, args['task_id'], data)
    c.control(owner, args['task_id'], {'action': 'stop', 'revision': 1, 'request_id': 'stop'})
    snapshot = native.confirm_exit(owner, args['task_id'], {**data, 'revision': 2})
    assert not snapshot['leases']
    assert not snapshot['desktop_stop']['manual_stop_required']
    assert snapshot['desktop_stop']['required_sessions'][0]['exit_confirmation_source'] == 'user_confirmation'
    assert snapshot['desktop_stop']['required_sessions'][0]['desktop_api_cancelled'] is False


def test_native_claim_and_pending_finish_never_poll():
    calls = []
    def send(args):
        calls.append(args)
        return {'mode': 'native_browser', 'state': 'running', 'account_ready': True,
                'browser_ready': False, 'lease_id': 'allocated'}
    result = direct_call_and_wait(send, {'action': 'claim'})
    assert len(calls) == 1 and result['client_wait']['http_calls'] == 1
    assert result['client_wait']['pending'] is False
    calls.clear()
    def finish(action, args):
        calls.append(action)
        return {'pending': True, 'manual_stop_required': True, 'request_id': 'finish'}
    result = lifecycle_call_and_wait(finish, 'finish_workflow', {'project_id': 'original'})
    assert calls == ['finish_workflow']
    assert result['next_action'] == 'desktop_manual_stop'
    assert result['client_wait']['pending'] is False
    assert 'resume_tool' not in result['client_wait']


def test_native_client_does_not_advertise_legacy_browser_batch(tmp_path):
    from api_test_tool.direct_batch import client_capabilities
    result = client_capabilities({'mode': 'native_browser',
                                 'execution_host': {'action_transport': 'native'}})
    assert result['execution_client']['browser_batch'] is False
    calls = []
    def send(args):
        calls.append(args)
        return result
    with pytest.raises(ValueError, match='原生'):
        direct_call_and_wait(send, {'action': 'browser', 'browser_action': 'batch',
                                   'holder_id': 'me', 'lease_id': 'lease', 'request_id': 'request',
                                   'parameters': {'steps': [{'id': 'one', 'action': 'snapshot'}]}},
                             batch_root=tmp_path)
    assert [call['action'] for call in calls] == ['context']


def test_each_case_saved_immediately_preserves_other_cases_and_stopped_evidence(tmp_path):
    c, s, owner, _, _, args = ready(tmp_path)
    context = s.direct.call(owner, {**args, 'action': 'context'})
    prefix = context['case_id_prefix']
    cases = [{'case_id': prefix + suffix, 'scenario': suffix, 'steps': '查看测试页面',
              'expected': '对应内容显示', 'status': 'not_run'} for suffix in ('01', '02')]
    save = lambda values: s.direct.call(owner, {**args, 'action': 'record',
                                                'record_action': 'cases', 'arguments': values})
    read = lambda: s.direct.call(owner, {**args, 'action': 'record', 'record_action': 'record'})
    first = save({'revision': 0, 'cases': cases})
    assert len(read()['cases']) == 2
    first_case = {**cases[0], 'status': 'passed', 'actual': '对应内容显示', 'conclusion': '符合预期'}
    second = save({'revision': first['revision'], 'cases': [first_case]})
    assert {item['case_id']: item['status'] for item in read()['cases']} == {
        prefix + '01': 'passed', prefix + '02': 'not_run'}
    assert c.snapshot(owner)['nodes'][0]['native_last_case_saved_at']
    c.control(owner, args['task_id'], {'action': 'stop', 'revision': 1, 'request_id': 'stop'})
    second_case = {**cases[1], 'status': 'failed', 'actual': '停止前观察对应内容未显示',
                   'conclusion': '不符合预期'}
    last = save({'revision': second['revision'], 'cases': [second_case]})
    assert [item['status'] for item in read()['cases']] == ['passed', 'failed']
    assert c.snapshot(owner)['leases'][0]['revoked']
