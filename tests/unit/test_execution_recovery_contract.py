"""Isolated recovery of rejected preparation and exited cleanup responsibilities."""
from copy import deepcopy
import json

import pytest

from test_native_lifecycle import mod, inputs, Fake
from test_cleanup_event_contract import fixture, capability, register, scope, raw
from api_test_tool import resource_holds, ui_records


def test_bad_coverage_is_reported_before_claim(mod, tmp_path):
    assignment, design = inputs()
    design['coverage'] = [{'case_ids': ['original']}]
    client = Fake()
    with pytest.raises(ValueError, match='coverage'):
        mod.prepare_native(client, assignment, design, tmp_path)
    assert client.calls == []


def test_definitive_baseline_rejection_can_resume_without_new_claim(mod, tmp_path):
    assignment, design = inputs()
    class Client(Fake):
        reject = True
        def call(self, tool, args):
            self.calls.append((args.get('action', 'baseline'), deepcopy(args)))
            if tool == 'save_ui_test_cases':
                if self.reject:
                    raise mod.ClientHTTPError(400, 'synthetic validation rejection')
                return {'execution_id': 'execution', 'revision': 1}
            if args['action'] == 'claim':
                return {'state': 'running', 'lease_id': 'lease'}
            return {'mode': 'native_browser', 'task_id': 'task', 'node_id': 'node',
                'state': 'running', 'lease_id': 'lease', 'record': None,
                'project': {'id': 'project'}, 'case_id_prefix': 'Mnew-',
                'node': {'id': 'node', 'task_id': 'task', 'executor_dispatch': assignment},
                'lease': {'id': 'lease', 'node_id': 'node'}, 'prior_operations': []}
    client = Client()
    with pytest.raises(mod.ClientHTTPError):
        mod.prepare_native(client, assignment, design, tmp_path)
    failed = json.loads((tmp_path / 'preparation.json').read_text())
    assert failed['baseline_outcome'] == 'unknown'
    client.reject = False
    design['cases'][0]['expected'] = 'corrected original design'
    ready = mod.prepare_native(client, assignment, design, tmp_path, resume=True)
    assert ready['ready'] and ready['revision'] == 1
    assert [name for name, _ in client.calls].count('claim') == 1
    assert [name for name, _ in client.calls].count('baseline') == 2
    history = json.loads((tmp_path / 'preparation.json').read_text())['recovery_history']
    assert history[-1]['outcome'] == 'rejected'
    assert history[-1]['request'] == failed['stages']['baseline']['request']


@pytest.mark.parametrize('description', ['not_executed', '未删除，已归档', 'unknown', 'any new description'])
def test_resolved_cleanup_preserves_description_and_releases_original_lease(tmp_path, description):
    c, service, owner, project, claim, aid, send = fixture(tmp_path)
    c.store.update_project(owner, project['id'], {'ui_execution_permission': {'key': 'full'}})
    send([capability(aid), register(aid)])
    obj = send([{'command': 'prepare_cleanup', 'responsibility_id': 'object-a'}])['results'][0]['responsibility']
    observation = {'evidence_ref': 'asset:original-ended-without-deletion', 'object_scope': scope(aid),
        'status': None, 'business_completed': False, 'original_operation_resolved': True,
        'effect_state': description, 'object_state': 'archived',
        'object_identity_verified': True, 'principal_verified': True,
        'scene_release_verified': True, 'scene_release_evidence_ref': 'asset:pages-closed'}
    result = send([{'command': 'reconcile', 'responsibility_id': 'object-a',
        'cleanup_attempt_id': obj['cleanup_attempt_id'], 'observation': observation}])
    obj = result['results'][0]['responsibility']
    assert obj['state'] == 'residual'
    assert obj['last_observation'] == observation
    record = ui_records.load(c.store, owner, project['id'], project.get('ui_execution_id') or
        raw(c)['nodes'][claim['node_id']]['record_execution_id'])
    released = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original-holder',
        'lease_id': claim['lease_id'], 'arguments': {'browser_stopped': True, 'reason': 'Synthetic pages exited'}})
    assert released['released'] and not c.snapshot(owner)['leases']
    published = ui_records.load(c.store, owner, project['id'], record['id'])
    assert published['cases'] == record['cases'] and published['revision'] == record['revision']
    assert published['published_revision'] == record['revision']
    assert raw(c)['cleanup_objects']['object-a']['state'] == 'residual'


def test_saved_misclassification_settles_once_without_new_observation(tmp_path):
    c, service, owner, project, claim, aid, send = fixture(tmp_path)
    c.store.update_project(owner, project['id'], {'ui_execution_permission': {'key': 'full'}})
    send([capability(aid), register(aid)])
    obj = send([{'command': 'prepare_cleanup', 'responsibility_id': 'object-a'}])['results'][0]['responsibility']
    observation = {'evidence_ref': 'asset:original-resolved', 'object_scope': scope(aid),
        'business_completed': False, 'original_operation_resolved': True,
        'effect_state': 'not_executed', 'object_state': 'archived',
        'object_identity_verified': True, 'principal_verified': True,
        'scene_release_verified': True, 'scene_release_evidence_ref': 'asset:original-exit'}
    send([{'command': 'reconcile', 'responsibility_id': 'object-a',
        'cleanup_attempt_id': obj['cleanup_attempt_id'], 'observation': observation}])
    # Model the old persisted derivation without changing its authenticated history.
    with c.transaction() as (_, state):
        obj = state['cleanup_objects']['object-a']
        obj.update(state='unknown', classification='unknown')
        obj['history'][-1]['state'] = 'unknown'
    before = deepcopy(raw(c)['cleanup_objects']['object-a'])
    result = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original-holder',
        'lease_id': claim['lease_id'], 'arguments': {'browser_stopped': True, 'reason': 'Original pages exited'}})
    assert not result['released']
    resource_holds.settle(c)
    after = raw(c)['cleanup_objects']['object-a']
    assert after['state'] == 'residual' and not c.snapshot(owner)['leases']
    assert after['last_observation'] == before['last_observation']
    assert after['history'] == before['history']
    assert after['observed_at'] == before['observed_at']
    resource_holds.settle(c)
    assert raw(c)['cleanup_objects']['object-a'] == after


def test_unresolved_cleanup_is_not_released_by_legacy_description(tmp_path):
    from api_test_tool.cleanup_capabilities import _result_state
    assert _result_state('proxy_rejected', {'business_completed': False,
        'original_operation_resolved': False, 'effect_state': 'not_sent'}) == 'unknown'


@pytest.mark.parametrize('state,expected', [('rejected', False), ('unknown', False), ('pending', False)])
def test_final_review_rejection_is_not_an_unknown_write(mod, tmp_path, state, expected):
    binding = {'holder_id': 'h', 'task_id': 't', 'node_id': 'n', 'lease_id': 'l',
        'final_review': {'state': state}}
    assert mod.native_publication_ready(tmp_path / 'binding.json', binding) is expected
    args = mod.native_closeout_arguments(binding, browser_stopped=True, reason='Original pages exited')
    assert args['arguments']['publish_saved'] is expected


def test_rejected_observation_retains_failure_but_does_not_fence_next_save(mod, tmp_path):
    client = Fake()
    mod.prepare_native(client, *inputs(), tmp_path)
    def reject(binding_file, payload, receipt_file):
        binding = json.loads(binding_file.read_text())
        identity = {'workspace_url': client.url, 'binding': {k: binding[k] for k in
            ('holder_id', 'task_id', 'node_id', 'lease_id', 'project_id', 'execution_id')}, 'payload': payload}
        fingerprint = mod.hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        mod.write_private_json(receipt_file, {**identity, 'fingerprint': fingerprint, 'state': 'rejected',
            'http_status': 400, 'revision_before': binding['revision'], 'rejection_confirmed': {
                'source': 'platform_record_readback', 'fingerprint': fingerprint,
                'execution_id': binding['execution_id'], 'revision': binding['revision']}})
        raise mod.ClientHTTPError(400, 'synthetic rejection')
    client.native_record = reject
    with pytest.raises(mod.ClientHTTPError):
        mod.observed_native(client, tmp_path/'binding.json', 'Mnew-001', 'failed', 'Original observation', tmp_path/'receipt-rejected.json')
    assert not (tmp_path/'observation-pending.json').exists()
    assert json.loads((tmp_path/'receipt-rejected.json').read_text())['state'] == 'rejected'


from test_native_result_continuity import client_module, prepared_client


@pytest.mark.parametrize('outcome', ['saved', 'not_saved', 'later_revision', 'other_execution', 'different_payload', 'read_failed'])
def test_http_error_is_resolved_only_from_original_record(client_module, tmp_path, outcome):
    m = client_module
    client, binding = prepared_client(m, tmp_path)
    payload = {'cases': [{'case_id': 'C1', 'status': 'failed', 'actual': 'Original observation'}],
               'review_notes': 'Original review'}
    record = {'id': 'execution', 'revision': 3, **deepcopy(payload)}
    if outcome == 'not_saved':
        record['revision'] = 2
        record['cases'] = []
    elif outcome == 'later_revision': record['revision'] = 4
    elif outcome == 'other_execution': record['id'] = 'other'
    elif outcome == 'different_payload': record['cases'][0]['actual'] = 'Different observation'
    calls = []
    def call(tool, args):
        calls.append(args['record_action'])
        if args['record_action'] == 'cases':
            raise m.ClientHTTPError(400, 'Response error may follow persistence')
        if outcome == 'read_failed': raise OSError('Read unavailable')
        return record
    client.call = call
    path = tmp_path / 'receipt.json'
    if outcome == 'saved':
        result = client.native_record(tmp_path/'binding.json', payload, path)
        assert result['saved'] and result['revision'] == 3
    else:
        with pytest.raises(m.ClientHTTPError):
            client.native_record(tmp_path/'binding.json', payload, path)
    receipt = json.loads(path.read_text())
    current = json.loads((tmp_path/'binding.json').read_text())
    expected = 'saved' if outcome == 'saved' else 'rejected' if outcome == 'not_saved' else 'unknown'
    assert receipt['state'] == current['final_review']['state'] == expected
    assert current['revision'] == (3 if outcome == 'saved' else 2)
    assert bool(receipt.get('rejection_confirmed')) is (outcome == 'not_saved')
    assert m.native_publication_ready(tmp_path/'binding.json', current) is (outcome in {'saved', 'not_saved'})
    assert calls == ['cases', 'record']


@pytest.mark.parametrize('saved', [False, True])
def test_old_rejected_receipt_can_be_reconciled_without_resending(client_module, tmp_path, saved):
    m = client_module
    client, binding = prepared_client(m, tmp_path)
    payload = {'cases': [{'case_id': 'C1', 'status': 'failed', 'actual': 'Original observation'}],
               'review_notes': 'Original review'}
    def failed_read(tool, args):
        raise m.ClientHTTPError(400, 'Original error')
    client.call = failed_read
    path = tmp_path / 'receipt-old.json'
    with pytest.raises(m.ClientHTTPError): client.native_record(tmp_path/'binding.json', payload, path)
    receipt = json.loads(path.read_text())
    receipt.update(state='rejected')
    receipt.pop('rejection_confirmed', None)
    m.write_private_json(path, receipt)
    current = json.loads((tmp_path/'binding.json').read_text())
    current['final_review'] = {'state':'rejected', 'receipt_file':str(path), 'fingerprint':receipt['fingerprint']}
    m.write_private_json(tmp_path/'binding.json', current)
    assert not m.native_publication_ready(tmp_path/'binding.json', current)
    calls = []
    def read(tool, args):
        calls.append(args['record_action'])
        return {'id':'execution', 'revision':3 if saved else 2, **deepcopy(payload)}
    client.call = read
    result = client.native_record(tmp_path/'binding.json', payload, path)
    current = json.loads((tmp_path/'binding.json').read_text())
    assert result['saved'] is saved
    assert current['revision'] == (3 if saved else 2)
    assert m.native_publication_ready(tmp_path/'binding.json', current)
    assert calls == ['record']


@pytest.mark.parametrize('mismatch', [False, True])
def test_baseline_http_error_after_commit_uses_original_readback(client_module, tmp_path, mismatch):
    m = client_module
    assignment, design = inputs()
    class Server(Fake):
        record = None
        def call(self, tool, args):
            self.calls.append((args.get('action', 'baseline'), deepcopy(args)))
            if tool == 'save_ui_test_cases':
                self.record = {'id':'execution', 'revision':1, 'cases':deepcopy(args['cases'])}
                if mismatch: self.record['cases'][0]['expected'] = 'Different design'
                raise m.ClientHTTPError(404, 'Missing historical report after save')
            if args['action'] == 'claim': return {'state':'running', 'lease_id':'lease'}
            return {'mode':'native_browser', 'task_id':'task', 'node_id':'node', 'state':'running',
                'lease_id':'lease', 'record':self.record,
                'project':{'id':'project', 'ui_execution_id':'execution' if self.record else None},
                'case_id_prefix':'Mnew-', 'node':{'id':'node','task_id':'task','executor_dispatch':assignment},
                'lease':{'id':'lease','node_id':'node'}, 'prior_operations':[]}
    server = Server()
    with pytest.raises(m.ClientHTTPError): m.prepare_native(server, assignment, design, tmp_path)
    # Old clients persisted a rejected state based only on the status code.
    ledger = json.loads((tmp_path/'preparation.json').read_text())
    ledger['baseline_outcome'] = 'rejected'
    m.write_private_json(tmp_path/'preparation.json', ledger)
    if mismatch:
        with pytest.raises(ValueError): m.prepare_native(server, assignment, design, tmp_path, resume=True)
    else:
        assert m.prepare_native(server, assignment, design, tmp_path, resume=True)['ready']
    assert [name for name, _ in server.calls].count('baseline') == 1
    assert [name for name, _ in server.calls].count('claim') == 1


@pytest.mark.parametrize('saved', [False, True])
def test_receiver_reconciles_old_rejected_response_once(client_module, tmp_path, saved):
    m = client_module
    client, binding = prepared_client(m, tmp_path)
    observation = {'case_id':'C1', 'status':'failed', 'checks':[
        {'name':'original', 'expected':'ready', 'observed':'absent', 'ok':False}]}
    payload = {'cases':[{'case_id':'C1','status':'failed','actual':m.observation_actual(observation)}]}
    def error(tool, args): raise m.ClientHTTPError(400, 'Original save error')
    client.call = error
    receipt_file = tmp_path/'receipt-old.json'
    with pytest.raises(m.ClientHTTPError): client.native_record(tmp_path/'binding.json', payload, receipt_file)
    receipt = json.loads(receipt_file.read_text())
    receipt['state'] = 'rejected'
    m.write_private_json(receipt_file, receipt)
    response = {'request_id':'123-abc', 'saved':False, 'state':'rejected', 'record_receipt_file':str(receipt_file)}
    m.write_private_json(tmp_path/'native-receiver-response-123-abc.json', response)
    m.write_private_json(tmp_path/'observation-inbox-123-abc.json', observation)
    m.write_private_json(tmp_path/'native-observation-awaiting.json', {'request_id':'123-abc'})
    m.write_private_json(tmp_path/'observation-pending.json', {
        **payload['cases'][0], 'request_id':'123-abc','receipt_file':str(receipt_file),'payload':payload})
    assert not m.native_publication_ready(tmp_path/'binding.json', binding)
    calls = []
    def read(tool, args):
        calls.append(args['record_action'])
        return {'id':'execution', 'revision':3 if saved else 2, **deepcopy(payload)}
    client.call = read
    result = m.reconcile_native_observation(client, tmp_path/'binding.json', '123-abc')
    assert result['saved'] is saved
    assert result['state'] == ('saved' if saved else 'rejected')
    assert not (tmp_path/'observation-pending.json').exists()
    m.write_private_json(tmp_path/'native-receiver-response-123-abc.json', result)
    current = json.loads((tmp_path/'binding.json').read_text())
    assert m.native_publication_ready(tmp_path/'binding.json', current)
    assert calls == ['record']


def test_prepare_resume_reconciles_old_rejected_save_without_blocking_or_posting(client_module, tmp_path):
    m = client_module
    prepared = m.prepare_native(Fake(), *inputs(), tmp_path)
    binding_file = tmp_path/'binding.json'
    binding = json.loads(binding_file.read_text())
    m.write_private_json(tmp_path/'credential.json', {'url':binding['workspace_url'],'token':'synthetic'})
    client = m.Client(binding['workspace_url'], tmp_path/'credential.json')
    client.manifest = {'tools':[{'name':'direct_test_session','inputSchema':{
        'properties':{'action':{},'holder_id':{},'arguments':{}}}}],
        'actions':{'direct_test_session':'direct_session'}}
    payload = {'cases':[{'case_id':'Mnew-001','status':'failed','actual':'Original observation'}], 'review_notes':'Original review'}
    def error(tool, args): raise m.ClientHTTPError(400, 'Original error')
    client.call = error
    path = tmp_path/'receipt-old.json'
    with pytest.raises(m.ClientHTTPError): client.native_record(binding_file, payload, path)
    receipt = json.loads(path.read_text())
    receipt['state'] = 'rejected'
    m.write_private_json(path, receipt)
    current = json.loads(binding_file.read_text())
    current['final_review']['state'] = 'rejected'
    m.write_private_json(binding_file, current)
    calls = []
    def recover(tool, args):
        calls.append(args.get('record_action', args.get('action')))
        if args.get('record_action') == 'record':
            return {'id':'execution','revision':1,'cases':prepared['cases']}
        if args.get('action') == 'claim': return {'state':'running','lease_id':'lease'}
        raise AssertionError('Must not repeat baseline or result POST')
    client.call = recover
    assert m.prepare_native(client, *inputs(), tmp_path, resume=True)['ready']
    assert calls == ['record', 'claim']
    assert m.native_publication_ready(binding_file, json.loads(binding_file.read_text()))


def test_reused_rejected_observation_does_not_return_as_a_saved_receiver_result(mod, tmp_path):
    client = Fake()
    mod.prepare_native(client, *inputs(), tmp_path)
    client.native_record = lambda *args, **kwargs: {'saved': False, 'state': 'rejected'}
    with pytest.raises(ValueError, match='未保存'):
        mod.observed_native(client, tmp_path/'binding.json', 'Mnew-001', 'failed',
                            'Original observation', tmp_path/'receipt-rejected.json')
