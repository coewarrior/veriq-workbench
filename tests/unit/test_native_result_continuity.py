"""Small offline reproductions of uncertain saves and resumed environment setup."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


@pytest.fixture
def client_module():
    path = ROOT / 'api_test_tool/static/api-test-client.py'
    spec = importlib.util.spec_from_file_location('continuity_client', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Exercise the canonical helper before the release export embeds it.
    shared = ROOT / 'api_test_tool/checkpoint_results.py'
    if shared.exists():
        exec(compile(shared.read_text(), 'checkpoint_results.py', 'exec'), module.__dict__)
    exec(compile((ROOT / 'api_test_tool/native_lifecycle.py').read_text(), 'native_lifecycle.py', 'exec'), module.__dict__)
    exec(compile((ROOT / 'api_test_tool/native_observation_receiver.py').read_text(), 'native_observation_receiver.py', 'exec'), module.__dict__)
    return module


def prepared_client(module, tmp_path):
    binding = {'workspace_url': 'http://fixture.test', 'holder_id': 'holder', 'task_id': 'task',
               'node_id': 'node', 'lease_id': 'lease', 'project_id': 'project',
               'execution_id': 'execution', 'revision': 2, 'dispatch_id': 'dispatch', 'executor_ref': 'thread:worker'}
    module.write_private_json(tmp_path / 'binding.json', binding)
    module.write_private_json(tmp_path / 'credential.json', {'url': binding['workspace_url'], 'token': 'synthetic'})
    client = module.Client(binding['workspace_url'], tmp_path / 'credential.json')
    client.manifest = {'tools': [{'name': 'direct_test_session', 'inputSchema': {
        'properties': {'action': {}, 'holder_id': {}, 'arguments': {}}}}],
        'actions': {'direct_test_session': 'direct_session'}}
    return client, binding


@pytest.mark.parametrize('change', ['binding', 'payload', 'revision', 'request'])
def test_only_exact_saved_receipt_clears_pending_marker(client_module, tmp_path, change):
    m = client_module
    client, binding = prepared_client(m, tmp_path)
    payload = {'cases': [{'case_id': 'C1', 'status': 'passed', 'actual': '原观察'}]}
    marker = {'payload': payload, 'request_id': '123-abc', 'binding': binding}
    receipt = {'state': 'saved', 'binding': binding, 'payload': payload, 'revision_before': 2,
        'result': {'execution_id': 'execution', 'revision': 3}}
    current = {**binding, 'revision': 3}
    assert hasattr(m, 'native_pending_receipt_matches')
    assert m.native_pending_receipt_matches(marker, receipt, current, request_id='123-abc')
    bad = copy.deepcopy(receipt)
    if change == 'binding': bad['binding']['node_id'] = 'other'
    if change == 'payload': bad['payload']['cases'][0]['actual'] = '另一个观察'
    if change == 'revision': bad['result']['revision'] = 4
    assert not m.native_pending_receipt_matches(marker, bad, current,
        request_id='456-def' if change == 'request' else '123-abc')


def test_prepare_resume_reuses_original_confirmed_stages(client_module, tmp_path):
    m=client_module
    assignment={'workspace_url':'http://fixture.test','task_id':'task','node_id':'node','holder_id':'holder',
                'dispatch_id':'dispatch','executor_ref':'thread:worker','browser_mode':'cua'}
    design={'cases':[{'case_id':'c','scenario':'原设计','steps':'观察','expected':'一致','status':'not_run'}]}
    class Server:
        url='http://fixture.test'
        calls=[]
        def call(self,tool,args):
            self.calls.append((tool,args.get('action')))
            if args.get('action')=='claim':raise OSError('response lost after committed lease')
            if args.get('action')=='context' and not args.get('lease_id'):
                return {'state':'running','lease_id':'original-lease','task_id':'task','node_id':'node','account_ready':True}
            if args.get('action')=='context':
                return {'mode':'native_browser','project':{'id':'project'},'record':None,'case_id_prefix':'M-',
                    'node':{'id':'node','task_id':'task','executor_dispatch':assignment},
                    'lease':{'id':'original-lease','node_id':'node'},'accounts':[],'prior_operations':[]}
            assert tool=='save_ui_test_cases'
            return {'execution_id':'original-run','revision':1}
    server=Server()
    with pytest.raises(OSError):m.prepare_native(server,assignment,design,tmp_path)
    result=m.prepare_native(server,assignment,design,tmp_path,resume=True)
    assert result['ready'] and result['execution_id']=='original-run'
    assert server.calls==[('direct_test_session','claim'),('direct_test_session','context'),
        ('direct_test_session','context'),('save_ui_test_cases',None)]
    binding=json.loads((tmp_path/'binding.json').read_text())
    assert binding['lease_id']=='original-lease'


@pytest.mark.parametrize('stale',[True,False])
def test_ready_resume_checks_notified_stage_against_original_active_lease(client_module,tmp_path,stale):
    m=client_module
    client,binding=prepared_client(m,tmp_path)
    current={'work_unit_id':'ab','plan_revision':2,'requirements_digest':'ab-digest'}
    plan={'plan_revision':2,'units':[{'id':'ab'}]}
    binding['work_plan']={'plan_revision':1,'units':[{'id':'a'}]}
    m.write_private_json(tmp_path/'binding.json',binding)
    case={'case_id':'C1','scenario':'原场景','steps':'观察','expected':'一致','status':'not_run'}
    m.write_private_json(tmp_path/'preparation.json',{'state':'ready','fingerprint':'original','stages':{},
        'ready':{'ready':True,'cases':[case],'execution_id':'execution'}})
    assignment={**{k:binding[k] for k in ('workspace_url','task_id','node_id','holder_id','dispatch_id','executor_ref')},
        'browser_mode':'cua','claim_arguments':{'work_token':{**current,'plan_revision':1} if stale else current,
                                            'account_ids':['a','b']}}
    calls=[]
    def read(tool,args):
        calls.append(args)
        assert args['action']=='context','resume must not mutate claim or baseline'
        if not args.get('lease_id'):
            return {'state':'running','lease_id':'lease','task_id':'task','node_id':'node','account_ids':['a','b']}
        return {'mode':'native_browser','node':{'id':'node','task_id':'task','executor_dispatch':assignment,
                'work_selection':current,'checkpoint':{'work_plan':plan}},
            'lease':{'id':'lease','node_id':'node','account_ids':['a','b']},'prior_operations':[]}
    client.call=read
    if stale:
        with pytest.raises(ValueError,match='阶段'):m.prepare_native(client,assignment,{'cases':[case]},tmp_path,resume=True)
        assert json.loads((tmp_path/'binding.json').read_text())['work_plan']['plan_revision']==1
    else:
        assert m.prepare_native(client,assignment,{'cases':[case]},tmp_path,resume=True)['ready']
        saved=json.loads((tmp_path/'binding.json').read_text())
        assert saved['work_plan']==plan and saved['work_token']==current
    assert len(calls)==2


@pytest.mark.parametrize('corruption',[None,'missing_receipt','changed_inbox'])
def test_cached_receiver_success_still_requires_original_write_evidence(client_module,tmp_path,corruption):
    m=client_module
    client,binding=prepared_client(m,tmp_path)
    request_id='123-abc'
    observation={'case_id':'C1','status':'passed','checks':[
        {'name':'原检查','expected':'一致','observed':'一致','ok':True}]}
    payload={'cases':[{'case_id':'C1','status':'passed','actual':m.observation_actual(observation)}]}
    calls=[]
    def save(tool,args):
        calls.append(args)
        return {'execution_id':'execution','revision':3}
    client.call=save
    receipt=tmp_path/'receipt-original.json'
    client.native_record(tmp_path/'binding.json',payload,receipt)
    m.write_private_json(tmp_path/('native-receiver-response-'+request_id+'.json'),{
        'request_id':request_id,'saved':True,'state':'saved','record_receipt_file':str(receipt)})
    if corruption=='missing_receipt':receipt.unlink()
    if corruption=='changed_inbox':observation['case_id']='OTHER'
    m.write_private_json(tmp_path/('observation-inbox-'+request_id+'.json'),observation)
    result=m.reconcile_native_observation(client,tmp_path/'binding.json',request_id)
    assert result['saved'] is (corruption is None)
    if corruption:assert result['state']=='unknown'
    assert len(calls)==1


@pytest.mark.parametrize('mismatch',[False,True])
def test_unknown_baseline_is_read_back_exactly_without_reposting(client_module,tmp_path,mismatch):
    m=client_module
    assignment={'workspace_url':'http://fixture.test','task_id':'task','node_id':'node','holder_id':'holder',
                'dispatch_id':'dispatch','executor_ref':'thread:worker','browser_mode':'cua'}
    design={'cases':[{'case_id':'c','scenario':'原设计','steps':'观察','expected':'一致','status':'not_run'}]}
    class Server:
        url='http://fixture.test'
        record=None
        writes=0
        claims=0
        def call(self,tool,args):
            if args.get('action')=='claim':
                self.claims+=1
                return {'state':'running','lease_id':'lease'}
            if args.get('action')=='context' and not args.get('lease_id'):
                return {'state':'running','lease_id':'lease','task_id':'task','node_id':'node','account_ready':True}
            if args.get('action')=='context':
                return {'mode':'native_browser','project':{'id':'project','ui_execution_id':'run' if self.record else None},
                    'record':self.record,'case_id_prefix':'M-',
                    'node':{'id':'node','task_id':'task','executor_dispatch':assignment},
                    'lease':{'id':'lease','node_id':'node'},'accounts':[],'prior_operations':[]}
            assert tool=='save_ui_test_cases'
            self.writes+=1
            self.record={'id':'run','revision':1,'cases':copy.deepcopy(args['cases'])}
            if mismatch:self.record['cases'][0]['expected']='different'
            raise OSError('baseline response lost after save')
    server=Server()
    with pytest.raises(OSError):m.prepare_native(server,assignment,design,tmp_path)
    if mismatch:
        with pytest.raises(ValueError):m.prepare_native(server,assignment,design,tmp_path,resume=True)
        assert json.loads((tmp_path/'preparation.json').read_text())['state']=='failed'
    else:
        result=m.prepare_native(server,assignment,design,tmp_path,resume=True)
        assert result['ready'] and result['execution_id']=='run' and result['revision']==1
    assert server.writes==server.claims==1


def test_unknown_save_readback_advances_original_receipt_without_resubmission(client_module, tmp_path):
    m = client_module
    client, binding = prepared_client(m, tmp_path)
    payload = {'cases': [{'case_id': 'C1', 'status': 'not_run', 'scenario': '保留设计'}],
               'coverage': [{'coverage_id': 'area', 'feature': '完整功能', 'case_ids': ['C1']}],
               'review_notes': '原始回查'}
    record = {'id': 'execution', 'revision': 3, **copy.deepcopy(payload)}
    calls = []
    def call(name, args):
        calls.append(args['record_action'])
        if args['record_action'] == 'cases':
            raise m.ClientHTTPError(500, 'synthetic save response lost')
        assert args['record_action'] == 'record'
        return record
    client.call = call
    receipt_file = tmp_path / 'receipt.json'
    with pytest.raises(m.ClientHTTPError):
        client.native_record(tmp_path / 'binding.json', payload, receipt_file)
    result = client.native_record(tmp_path / 'binding.json', payload, receipt_file)
    receipt = json.loads(receipt_file.read_text())
    assert calls == ['cases', 'record']
    assert result['saved'] and result['revision'] == 3
    assert receipt['confirmation_source'] == 'platform_record_readback'
    assert receipt['original_transport_state'] == 'unknown' and receipt['http_status'] == 500
    latest = json.loads((tmp_path / 'binding.json').read_text())
    assert latest['revision'] == 3 and latest['case_results']['C1']['scenario'] == '保留设计'
    assert latest['final_review']['state'] == 'saved'
    client.native_record(tmp_path / 'binding.json', payload, receipt_file)
    assert calls == ['cases', 'record']


@pytest.mark.parametrize('difference', ['revision', 'execution', 'field', 'read_failure'])
def test_unknown_save_mismatch_stays_unknown_without_replaying(client_module, tmp_path, difference):
    m = client_module
    client, _ = prepared_client(m, tmp_path)
    payload = {'cases': [{'case_id': 'C1', 'status': 'passed', 'actual': '真实观察'}]}
    record = {'id': 'execution', 'revision': 3, 'cases': copy.deepcopy(payload['cases'])}
    if difference == 'revision': record['revision'] = 4
    if difference == 'execution': record['id'] = 'other'
    if difference == 'field': record['cases'][0]['actual'] = '不同观察'
    calls = []
    def call(name, args):
        calls.append(args['record_action'])
        if args['record_action'] == 'cases' or difference == 'read_failure':
            raise OSError('uncertain')
        return record
    client.call = call
    path = tmp_path / 'receipt.json'
    with pytest.raises(OSError): client.native_record(tmp_path / 'binding.json', payload, path)
    with pytest.raises((ValueError, OSError)): client.native_record(tmp_path / 'binding.json', payload, path)
    assert calls == ['cases', 'record']
    assert json.loads(path.read_text())['state'] == 'unknown'
    assert json.loads((tmp_path / 'binding.json').read_text())['revision'] == 2


@pytest.mark.parametrize('append_new', [False, True])
def test_partial_checkpoint_observation_preserves_other_required_points(client_module, tmp_path, append_new):
    from api_test_tool import test_checkpoints
    from api_test_tool.ui_dependencies import normalize as normalize_dependencies
    m = client_module
    client, binding = prepared_client(m, tmp_path)
    dependency = normalize_dependencies([{'key': 'role', 'kind': 'account', 'title': '独立身份',
        'environment': 'fixture', 'role': 'candidate', 'tenant': 'fixture', 'input_ref': 'fixture-role'}],
        {}, 'https://fixture.test')[0]
    points = [{'id': 'one', 'title': '已查看', 'expected': '显示', 'status': 'passed',
               'actual': '原观察', 'verification_mode': 'real'},
              {'id': 'two', 'title': '仍待验证', 'expected': '独立条件', 'status': 'blocked',
               'dependencies': [dependency]}]
    old = {'case_id': 'C1', 'checkpoints': points}
    binding['case_results'] = {'C1': old}
    m.write_private_json(tmp_path / 'binding.json', binding)
    observed = {**points[0], 'status': 'passed', 'actual': '已显示', 'verification_mode': 'real'}
    if append_new:
        observed = {**observed, 'id': 'three', 'title': '新增独立观察'}
    def call(name, args):
        case = args['arguments']['cases'][0]
        normalized = test_checkpoints.normalize(test_checkpoints.apply_updates(case, old), old, 'https://fixture.test')
        saved = test_checkpoints.reconcile({'cases': [{'case_id': 'C1', **normalized}],
            'dependency_checks': {dependency['id']: {'status': 'blocked', 'observed': '身份缺失'}}})['cases'][0]
        return {'execution_id': 'execution', 'revision': 3, 'saved_cases': [saved]}
    client.call = call
    result = client.native_record(tmp_path / 'binding.json', {'cases': [
        {'case_id': 'C1', 'status': 'passed', 'actual': '已显示', 'not_run_reason': '', 'checkpoints': [observed]}]}, tmp_path / 'receipt.json')
    saved = json.loads((tmp_path / 'binding.json').read_text())['case_results']['C1']
    assert result['saved'] and saved['status'] == 'partial'
    assert [p['id'] for p in saved['checkpoints']] == (['one', 'two', 'three'] if append_new else ['one', 'two'])
    assert saved['checkpoints'][1]['status'] == 'blocked'


def test_resume_replacement_uses_current_claim_not_ended_lease_checkpoint(client_module, tmp_path):
    m = client_module
    client, binding = prepared_client(m, tmp_path)
    assignment = {k: binding[k] for k in ('workspace_url', 'task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')}
    assignment.update(browser_mode='isolated', replace_exited_environment={
        'browser_stopped': True, 'reason': '原环境已退出', 'previous_context_ids': ['old']})
    environment = {'context_id': 'new'}
    m.write_private_json(tmp_path / 'browser-environment.json', {'state': 'open', 'browser_tool': 'node_repl',
        'identity': assignment, 'environments': [environment]})
    case = {'case_id': 'C1', 'scenario': '原设计', 'steps': '原步骤', 'expected': '原预期', 'status': 'not_run'}
    calls = []
    def call(name, args):
        calls.append(args['action'])
        assert args['action'] != 'checkpoint', 'old lease has ended'
        if args['action'] == 'claim':
            replacement = args['arguments']['native_environment_replacement']
            assert replacement['lease_id'] == 'lease' and replacement['browser_stopped'] is True
            return {'state': 'running', 'lease_id': 'new-lease'}
        return {'mode': 'native_browser', 'project': {'id': 'project', 'ui_execution_id': 'execution'},
                'record': {'id': 'execution', 'revision': 3, 'cases': [case]},
                'node': {'id': 'node', 'task_id': 'task', 'executor_dispatch': assignment},
                'lease': {'id': 'new-lease', 'node_id': 'node'}}
    client.call = call
    ready = m.prepare_native(client, assignment, {'cases': [case]}, tmp_path, resume=True)
    assert ready['ready'] and ready['resumed'] and calls == ['claim', 'context']
    latest = json.loads((tmp_path / 'binding.json').read_text())
    assert latest['previous_bindings'] == [binding] and latest['lease_id'] == 'new-lease'


def test_explicit_checkpoint_design_change_keeps_existing_replacement_semantics(client_module):
    old = {'C1': {'checkpoints': [{'id': 'one', 'title': '原设计'}, {'id': 'two', 'title': '另一设计'}]}}
    changes = [{'case_id': 'C1', 'status': 'passed', 'actual': '观察', 'checkpoints': [
        {'id': 'one', 'title': '明确修订设计', 'status': 'passed', 'actual': '观察', 'verification_mode': 'real'}]}]
    assert client_module.native_checkpoint_observations(changes, old) == changes


@pytest.mark.parametrize('different_lease', [False, True])
def test_claim_replacement_keeps_active_account_and_original_lease_guard(tmp_path, different_lease):
    from test_native_scheduler import setup
    from test_native_contexts import environment
    from api_test_tool.managed_service import ManagedService
    from api_test_tool.orchestration import Conflict
    c, owner, _, _, task_id = setup(tmp_path)
    service = ManagedService(c, ROOT / 'api_test_tool/static')
    args = {'task_id': task_id, 'node_id': c.snapshot(owner, task_id)['nodes'][0]['id'],
            'holder_id': 'native-chat', 'executor_ref': 'thread:worker',
            'arguments': {'browser_environments': [environment('original-context', True)]}}
    args['lease_id'] = service.direct.call(owner, {**args, 'action': 'claim'})['lease_id']
    before = next(l for l in c.snapshot(owner)['leases'] if l['id'] == args['lease_id'])
    new_environment = environment('actual-new-context', True)
    request = {**args, 'action': 'claim', 'arguments': {
        'browser_environments': [new_environment], 'native_environment_replacement': {
            'lease_id': 'foreign' if different_lease else args['lease_id'],
            'browser_stopped': True, 'reason': '原上下文实际退出',
            'previous_context_ids': ['original-context'], 'browser_environments': [new_environment]}}}
    if different_lease:
        with pytest.raises(Conflict): service.direct.call(owner, request)
    else:
        response = service.direct.call(owner, request)
        assert response['lease_id'] == args['lease_id']
        assert response['native_context_binding']['contexts'][0]['context_id'] == 'actual-new-context'
    after = next(l for l in c.snapshot(owner)['leases'] if l['id'] == args['lease_id'])
    assert after['account_ids'] == before['account_ids']
    if different_lease:
        assert after['native_context_binding'] == before['native_context_binding']


def test_prepare_reconciles_original_pending_observation_before_claim(client_module, tmp_path):
    m = client_module
    client, binding = prepared_client(m, tmp_path)
    case = {'case_id': 'C1', 'scenario': '原设计', 'steps': '原步骤', 'expected': '原预期', 'status': 'not_run'}
    payload = {'cases': [{'case_id': 'C1', 'status': 'passed', 'actual': '已观察'}]}
    receipt_file = tmp_path / 'receipt.json'
    client.call = lambda *args: (_ for _ in ()).throw(OSError('lost response'))
    with pytest.raises(OSError): client.native_record(tmp_path / 'binding.json', payload, receipt_file)
    m.write_private_json(tmp_path / 'observation-pending.json', {
        **payload['cases'][0], 'receipt_file': str(receipt_file)})
    assignment = {k: binding[k] for k in ('workspace_url', 'task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')}
    assignment['browser_mode'] = 'cua'
    m.write_private_json(tmp_path / 'preparation.json', {'state': 'ready', 'fingerprint': 'original',
        'stages': {}, 'ready': {'cases': [case]}})
    calls = []
    def call(name, args):
        calls.append((args['action'], args.get('record_action')))
        if args['action'] == 'record':
            return {'id': 'execution', 'revision': 3, 'cases': [{**case, **payload['cases'][0]}]}
        assert args['action'] == 'claim'
        return {'state': 'running', 'lease_id': 'lease'}
    client.call = call
    ready = m.prepare_native(client, assignment, {'cases': [case]}, tmp_path, resume=True)
    assert ready['revision'] == 3 and ready['cases'][0]['status'] == 'passed' and ready['http_calls'] == 2
    assert calls == [('record', 'record'), ('claim', None)]
    assert not (tmp_path / 'observation-pending.json').exists()


@pytest.mark.parametrize('route,corruption,point_mode', [
    ('record', None, 'append'), ('receiver', None, 'append'), ('receiver', 'missing_point', 'append'),
    ('receiver', 'derived_pass', 'append'), ('receiver', 'later_revision', 'append'),
    ('receiver', None, 'update')])
def test_unknown_checkpoint_normalization_uses_same_exact_reconciliation(client_module, tmp_path, route, corruption, point_mode):
    from api_test_tool import test_checkpoints
    m = client_module
    client, binding = prepared_client(m, tmp_path)
    old = {'case_id': 'C1', 'scenario': '保留全部断言', 'steps': '原步骤', 'expected': '原预期',
           'checkpoints': [{'id': 'one', 'title': '原已验证', 'expected': '可见', 'status': 'passed',
                            'actual': '原观察', 'verification_mode': 'real'},
                           {'id': 'two', 'title': '原未完成', 'expected': '独立分支', 'status': 'not_run'}]}
    old.update(test_checkpoints.normalize(old, {}, 'https://fixture.test'))
    old = test_checkpoints.reconcile({'cases': [old]})['cases'][0]
    binding['case_results'] = {'C1': old}
    m.write_private_json(tmp_path / 'binding.json', binding)
    observation = {'case_id': 'C1', 'status': 'passed', 'checks': [
        {'name': '新增观察', 'expected': '可见', 'observed': '可见', 'ok': True}],
        'case_changes': {'conclusion': '现场观察的说明', 'checkpoints': [
            {'id': 'three', 'title': '新增观察', 'expected': '可见', 'actual': '可见',
             'status': 'passed', 'verification_mode': 'real'}]}}
    if point_mode == 'update':
        observation['case_changes']['checkpoints'][0].update(id='one', title='原已验证')
    payload = {'cases': [{**observation['case_changes'], 'case_id': 'C1', 'status': 'passed',
                          'actual': m.observation_actual(observation)}]}
    calls, persisted = [], {}
    def call(name, args):
        calls.append(args['record_action'])
        if args['record_action'] == 'cases':
            change = args['arguments']['cases'][0]
            candidate = {**old, **test_checkpoints.normalize(test_checkpoints.apply_updates(change, old), old, 'https://fixture.test')}
            persisted.update(test_checkpoints.reconcile({'id': 'execution', 'revision': 3, 'cases': [candidate]}))
            if corruption == 'missing_point': persisted['cases'][0]['checkpoints'].pop(1)
            if corruption == 'derived_pass': persisted['cases'][0]['status'] = 'passed'
            if corruption == 'later_revision': persisted['revision'] = 4
            raise OSError('save response lost after persistence')
        assert args['record_action'] == 'record'
        return persisted
    client.call = call
    receipt_file = tmp_path / 'receipt.json'
    with pytest.raises(OSError): client.native_record(tmp_path / 'binding.json', payload, receipt_file)
    request_id = '123-abc'
    m.write_private_json(tmp_path / ('observation-inbox-' + request_id + '.json'), observation)
    m.write_private_json(tmp_path / ('native-receiver-response-' + request_id + '.json'), {
        'request_id': request_id, 'saved': False, 'state': 'unknown', 'record_receipt_file': str(receipt_file)})
    m.write_private_json(tmp_path / 'observation-pending.json', {
        **{k: payload['cases'][0][k] for k in ('case_id', 'status', 'actual')},
        'payload': payload, 'receipt_file': str(receipt_file)})
    def reconcile():
        return (client.native_record(tmp_path / 'binding.json', payload, receipt_file) if route == 'record'
                else m.reconcile_native_observation(client, tmp_path / 'binding.json', request_id))
    if corruption:
        try:
            result = reconcile()
        except ValueError:
            result = {'saved': False}
        assert result['saved'] is False
        assert json.loads(receipt_file.read_text())['state'] == 'unknown'
        assert json.loads((tmp_path / 'binding.json').read_text())['revision'] == 2
        assert (tmp_path / 'observation-pending.json').exists()
    else:
        assert reconcile()['saved'] is True
        saved = json.loads((tmp_path / 'binding.json').read_text())
        assert saved['revision'] == 3 and saved['case_results']['C1']['status'] == 'partial'
        assert len(saved['case_results']['C1']['checkpoints']) == (3 if point_mode == 'append' else 2)
        if route == 'receiver': assert not (tmp_path / 'observation-pending.json').exists()
    assert calls == ['cases', 'record']
