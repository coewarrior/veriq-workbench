"""Cleanup evidence contract on real temporary controller/store transactions."""
from copy import deepcopy

import pytest

from api_test_tool.orchestration import Conflict
from test_native_finalization import prepare
from test_native_contexts import environment


def fixture(tmp_path, *, known=False):
    c, service, owner, project, tid, saved = prepare(tmp_path, accounts=2)
    if known:
        with c.transaction() as (_, state):
            for account in state['accounts'].values():
                account.update(environment='test', tenant='tenant-a', roles=['operator'])
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': tid,
        'holder_id': 'original-holder', 'arguments': {'browser_environment': environment(isolated=True)}})
    service.direct.call(owner, {'action': 'context', 'holder_id': 'original-holder', 'lease_id': claim['lease_id']})
    service.direct.call(owner, {'action': 'record', 'record_action': 'cases',
        'holder_id': 'original-holder', 'lease_id': claim['lease_id'], 'arguments': {
            'project_id': project['id'], 'execution_id': saved['execution_id'],
            'revision': saved['revision'], 'cases': [{'case_id': 'A', 'actual': 'Synthetic created draft evidence'}]}})
    aid = c.snapshot(owner)['leases'][0]['account_ids'][0]
    def send(events):
        return service.direct.call(owner, {'action': 'cleanup', 'holder_id': 'original-holder',
            'task_id': tid, 'node_id': claim['node_id'],
            'lease_id': claim['lease_id'], 'arguments': {'events': events}})
    return c, service, owner, project, claim, aid, send


def capability(aid, **fields):
    return {'command': 'capability', 'capability_id': 'cap-a', 'capability': {
        'account_id': aid, 'object_type': 'draft', 'entry_source': 'observed draft page',
        'evidence_ref': 'asset:delete-control',
        'methods': [{'kind': 'ui', 'entry': 'Draft > Delete', 'evidence_ref': 'asset:delete-control'}],
        **fields}}


def register(aid, **fields):
    return {'command': 'register', 'responsibility_id': 'object-a', 'object': {
        'account_id': aid, 'object_type': 'draft', 'object_id': 'draft-1',
        'case_id': 'A', 'creation_evidence_ref': 'asset:created',
        'ownership': 'created_this_round', 'kind': 'test_data', 'capability_id': 'cap-a', **fields}}


def scope(aid, **fields):
    return {'account_id': aid, 'origin': 'https://test.example',
        'environment': 'https://test.example', 'tenant': '',
        'object_type': 'draft', 'object_id': 'draft-1', **fields}


def raw(c):
    with c.transaction() as (_, state):
        return {key: deepcopy(dict(state.get(key, {}))) for key in (
            'accounts', 'nodes', 'leases', 'cleanup_capabilities', 'cleanup_objects')}


@pytest.mark.parametrize('event,path', [
    ({'action': 'capability'}, 'events[0].command'),
    ({'command': 'invented'}, 'events[0].command'),
    ({'command': 'register', 'object_id': 'draft-1'}, 'events[0].object'),
    ({'command': 'capability', 'capability': {'scope': {'origin': 'https://test.example'}}},
     'events[0].capability.scope'),
    ({'command': 'capability', 'capability': {'account_id': 'a', 'object_type': 'draft',
        'entry_source': 'page', 'evidence_ref': 'asset:control',
        'methods': [{'channel': 'ui', 'method': 'delete', 'entry': 'Delete', 'evidence_ref': 'asset:control'}]}},
     'events[0].capability.methods[0].kind'),
])
def test_malformed_cleanup_is_parameter_error_before_responsibility_lookup(tmp_path, event, path):
    c, _, _, _, _, _, send = fixture(tmp_path)
    before = raw(c)
    with pytest.raises(ValueError) as caught:
        send([event])
    assert path in {item['path'] for item in caught.value.errors}
    assert raw(c) == before


def test_batch_lists_each_shape_error_and_never_commits_earlier_event(tmp_path):
    c, _, _, _, _, aid, send = fixture(tmp_path, known=True)
    before = raw(c)
    event = capability(aid, origin='https://test.example', environment='test', tenant='tenant-a', role='operator')
    with pytest.raises(ValueError) as caught:
        send([event, {'action': 'register'}, {'command': 'prepare_cleanup', 'method_index': '0'}])
    paths = {item['path'] for item in caught.value.errors}
    assert {'events[1].command', 'events[2].responsibility_id', 'events[2].method_index'} <= paths
    assert raw(c) == before


def test_plain_project_account_can_register_honest_unknown_metadata(tmp_path):
    c, _, owner, project, _, aid, send = fixture(tmp_path)
    c.store.update_project(owner, project['id'], {'ui_execution_permission': {'key': 'full'}})
    result = send([capability(aid), register(aid)])
    cap, obj = result['results'][0]['capability'], result['results'][1]['responsibility']
    assert (cap['origin'], cap['environment'], cap['tenant'], cap['role']) == (
        'https://test.example', 'https://test.example', '', '')
    assert (obj['tenant'], obj['role'], obj['account_id']) == ('', '', aid)
    assert result['business_action_performed'] is False
    assert send([{'command': 'prepare_cleanup', 'responsibility_id': 'object-a'}])['results'][0]['responsibility']['state'] == 'cleaning'


@pytest.mark.parametrize('field,value', [('origin', 'https://other.example'), ('environment', 'prod'),
    ('tenant', 'invented-tenant'), ('role', 'HR')])
def test_explicit_scope_mismatch_stays_denied_with_precise_safe_reason(tmp_path, field, value):
    c, _, _, _, _, aid, send = fixture(tmp_path)
    with pytest.raises(PermissionError, match=field):
        send([capability(aid, **{field: value})])
    assert not raw(c).get('cleanup_capabilities')


def test_account_outside_original_lease_or_project_cannot_supply_cleanup_scope(tmp_path):
    c, _, _, _, _, aid, send = fixture(tmp_path)
    other = next(key for key in raw(c)['accounts'] if key != aid)
    with pytest.raises(PermissionError, match='account_id'):
        send([capability(other)])
    with c.transaction() as (_, state):
        state['accounts'][aid]['projects'] = []
    with pytest.raises(PermissionError, match='project'):
        send([capability(aid)])


def test_unknown_cleanup_remains_unknown_until_original_attempt_reconciled(tmp_path):
    c, _, owner, project, _, aid, send = fixture(tmp_path)
    c.store.update_project(owner, project['id'], {'ui_execution_permission': {'key': 'full'}})
    send([capability(aid), register(aid)])
    obj = send([{'command': 'prepare_cleanup', 'responsibility_id': 'object-a'}])['results'][0]['responsibility']
    observation = {'evidence_ref': 'asset:404', 'object_scope': scope(aid), 'status': 404}
    result = send([{'command': 'complete_cleanup', 'responsibility_id': 'object-a',
        'cleanup_attempt_id': obj['cleanup_attempt_id'], 'observation': observation}])
    assert result['results'][0]['responsibility']['state'] == 'unknown'
    c.store.update_project(owner, project['id'], {'ui_scene_retention': {'key': 'full'}})
    with pytest.raises(Conflict):
        send([{'command': 'retain', 'responsibility_id': 'object-a'}])
    with pytest.raises(Conflict):
        send([{'command': 'prepare_cleanup', 'responsibility_id': 'object-a'}])
    reconciled = send([{'command': 'reconcile', 'responsibility_id': 'object-a',
        'cleanup_attempt_id': obj['cleanup_attempt_id'], 'observation': {
            **observation, 'original_operation_resolved': True, 'status': 200,
            'business_completed': True, 'evidence_ref': 'asset:original-operation-complete'}}])
    assert reconciled['results'][0]['responsibility']['state'] == 'cleaned'


def test_valid_batch_rolls_back_when_later_scope_mismatch_is_denied(tmp_path):
    c, _, _, _, _, aid, send = fixture(tmp_path, known=True)
    event = capability(aid, origin='https://test.example', environment='test', tenant='tenant-a', role='operator')
    before = raw(c)
    with pytest.raises(PermissionError):
        send([event, {**register(aid), 'object': {**register(aid)['object'], 'role': 'other-role'}}])
    assert raw(c) == before


def test_http_cleanup_reports_field_errors_and_safe_scope_denial(tmp_path):
    from fastapi.testclient import TestClient
    from api_test_tool.web import create_app
    from api_test_tool.mcp_access import MCPAccess
    c, _, owner, _, claim, aid, _ = fixture(tmp_path)
    access = MCPAccess(c.store)
    token = access.redeem(access.issue(owner)['code'])['token']
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        def send(events):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token}, json={
                'action': 'direct_session', 'arguments': {'action': 'cleanup',
                    'holder_id': 'original-holder', 'lease_id': claim['lease_id'],
                    'arguments': {'events': events}}})
        malformed = send([{'action': 'register'}, {'command': 'prepare_cleanup'}])
        assert malformed.status_code == 400
        assert {item['path'] for item in malformed.json()['errors']} == {
            'events[0].command', 'events[1].responsibility_id'}
        forbidden = send([capability(aid, role='secret-other-role')])
        assert forbidden.status_code == 403
        assert 'role' in forbidden.json()['detail']
        assert 'secret-other-role' not in forbidden.text
        missing = send([{'command': 'prepare_cleanup', 'responsibility_id': 'missing'}])
        assert missing.status_code == 403
        assert '责任' in missing.json()['detail']
        assert send([capability(aid)]).status_code == 200
        conflict = send([capability(aid, object_type='different-object')])
        assert conflict.status_code == 409
        assert 'scope' in conflict.json()['detail']


def test_unknown_tenant_and_role_never_share_capability_or_object_identity_between_accounts(tmp_path):
    from api_test_tool.managed_service import ManagedService
    from test_native_scheduler import setup
    from test_native_finalization import STATIC
    c, owner, project, _, tid = setup(tmp_path, accounts=2, modules=2)
    c.store.update_project(owner, project['id'], {'ui_execution_permission': {'key': 'full'}})
    service = ManagedService(c, STATIC)
    caps, objects, senders = [], [], []
    for index, node in enumerate(c.snapshot(owner)['nodes']):
        holder = 'holder-' + str(index)
        claim = service.direct.call(owner, {'action': 'claim', 'task_id': tid,
            'node_id': node['id'], 'holder_id': holder,
            'arguments': {'browser_environment': environment('context-' + str(index), True)}})
        context = service.direct.call(owner, {'action': 'context', 'holder_id': holder, 'lease_id': claim['lease_id']})
        cid = context['case_id_prefix'] + 'created'
        service.direct.call(owner, {'action': 'record', 'record_action': 'cases', 'holder_id': holder,
            'lease_id': claim['lease_id'], 'arguments': {'project_id': context['project']['id'],
                'cases': [{'case_id': cid, 'scenario': 'created draft', 'status': 'not_run'}]}})
        aid = next(lease for lease in c.snapshot(owner)['leases'] if lease['id'] == claim['lease_id'])['account_ids'][0]
        def send(events, holder=holder, lid=claim['lease_id']):
            return service.direct.call(owner, {'action': 'cleanup', 'holder_id': holder,
                'lease_id': lid, 'arguments': {'events': events}})
        event = capability(aid)
        event.pop('capability_id')
        cap = send([event])['results'][0]['capability']
        assert send([event])['results'][0]['reused']
        event = register(aid, case_id=cid, capability_id=cap['id'])
        event.pop('responsibility_id')
        obj = send([event])['results'][0]['responsibility']
        caps.append(cap)
        objects.append(obj)
        senders.append(send)
    assert caps[0]['id'] != caps[1]['id']
    assert objects[0]['id'] != objects[1]['id']
    assert objects[0]['account_id'] != objects[1]['account_id']
    with pytest.raises(Conflict, match='scope'):
        senders[1]([{'command': 'prepare_cleanup', 'responsibility_id': objects[1]['id'],
            'capability_id': caps[0]['id']}])


def test_released_original_lease_can_observe_but_cannot_prepare_cleanup(tmp_path):
    c, service, owner, _, claim, aid, send = fixture(tmp_path)
    observed = {'evidence_ref': 'asset:no-cleanup-entry', 'object_scope': scope(aid),
                'effect_state': 'not_sent', 'object_state': 'present'}
    obj = register(aid, residual={'reason': 'No verified deletion entry', 'observation': observed})
    obj['object'].pop('capability_id')
    send([obj])
    released = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original-holder',
        'lease_id': claim['lease_id'], 'arguments': {'browser_stopped': True, 'reason': 'Synthetic pages exited'}})
    assert released['released']
    result = send([{'command': 'residual', 'responsibility_id': 'object-a',
                   'reason': 'Confirmed existing residual', 'observation': observed}])
    assert result['results'][0]['responsibility']['state'] == 'residual'
    with pytest.raises(Conflict):
        send([{'command': 'prepare_cleanup', 'responsibility_id': 'object-a'}])
    assert not c.snapshot(owner)['leases']


def test_cleanup_consumers_and_retention_still_prevent_preparation(tmp_path):
    c, _, owner, project, claim, aid, send = fixture(tmp_path)
    c.store.update_project(owner, project['id'], {'ui_execution_permission': {'key': 'full'}})
    consumer = {'source_node_id': claim['node_id'], 'case_id': 'B'}
    send([capability(aid), register(aid, consumers=[consumer])])
    with pytest.raises(Conflict, match='消费者'):
        send([{'command': 'prepare_cleanup', 'responsibility_id': 'object-a'}])
    send([{'command': 'release_dependency', 'responsibility_id': 'object-a', 'consumer': consumer}])
    c.store.update_project(owner, project['id'], {'ui_scene_retention': {'key': 'full'}})
    with pytest.raises(Conflict, match='保留'):
        send([{'command': 'prepare_cleanup', 'responsibility_id': 'object-a'}])


def test_validator_can_be_exported_standalone_without_server_imports(tmp_path):
    import importlib.util
    from pathlib import Path
    source = Path(__file__).parents[2] / 'api_test_tool' / 'cleanup_contract.py'
    exported = tmp_path / 'cleanup_contract.py'
    exported.write_bytes(source.read_bytes())
    spec = importlib.util.spec_from_file_location('exported_cleanup_contract', exported)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    values = {'events': [capability('original-account')]}
    assert module.validate_cleanup_events(values) == values['events']
    with pytest.raises(ValueError) as caught:
        module.validate_cleanup_events({'events': [{'command': 'register'}]})
    assert caught.value.errors == [{'path': 'events[0].object', 'message': '必须为对象'}]


def test_shape_errors_precede_lease_and_report_scope_resolution(tmp_path):
    from api_test_tool.native_execution import NativeExecution
    _, service, owner, _, _, _, _ = fixture(tmp_path)
    with pytest.raises(ValueError) as caught:
        NativeExecution(service.direct).call(owner, {'action': 'cleanup', 'holder_id': 'original-holder',
            'arguments': {'events': [{'command': 'register'}]}})
    assert caught.value.errors == [{'path': 'events[0].object', 'message': '必须为对象'}]


def test_foreign_responsibility_is_denied_before_resolving_its_source(tmp_path):
    from api_test_tool.cleanup_contract import CleanupScopeError
    c, _, _, _, _, _, send = fixture(tmp_path)
    with c.transaction() as (_, state):
        state.setdefault('cleanup_objects', {})['foreign-object'] = {
            'id': 'foreign-object', 'owner': 'other-owner', 'task_id': 'other-task',
            'source_node_id': 'private-other-node'}
    with pytest.raises(CleanupScopeError, match='对象责任'):
        send([{'command': 'prepare_cleanup', 'responsibility_id': 'foreign-object'}])
