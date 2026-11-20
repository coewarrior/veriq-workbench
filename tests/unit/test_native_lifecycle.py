import importlib.util
import json
from pathlib import Path
import pytest


@pytest.fixture
def mod():
    path = Path(__file__).parents[2] / 'api_test_tool/static/api-test-client.py'
    spec = importlib.util.spec_from_file_location('prepared_native_client', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inputs():
    return ({'workspace_url': 'http://fixture.test', 'task_id': 'task', 'node_id': 'node',
             'holder_id': 'holder', 'dispatch_id': 'dispatch', 'executor_ref': 'thread:worker', 'browser_mode': 'cua'},
            {'cases': [{'case_id': 'original', 'title': '配置重开', 'steps': '打开并重开',
                        'expected': '显示一致', 'status': 'not_run'}]})


def test_explicit_yield_never_completes_or_publishes(mod):
    binding = dict(holder_id='h', task_id='t', node_id='n', lease_id='l',
                   project_id='p', execution_id='e', revision=3)
    result = mod.native_closeout_arguments(binding, browser_stopped=True, reason='stage boundary', outcome='yield')
    assert result['outcome'] == 'yield'
    assert result['arguments']['publish_saved'] is False
    assert 'report_pending' not in result['arguments']
    assert 'publication_binding' not in result['arguments']
    completed = mod.native_closeout_arguments(binding, browser_stopped=True, reason='done', defer_report=True)
    assert completed['outcome'] == 'completed' and completed['arguments']['report_pending']
    with pytest.raises(ValueError):
        mod.native_closeout_arguments(binding, browser_stopped=False, reason='unknown', outcome='yield')


def test_cli_control_result_is_private_and_bounded(mod, tmp_path):
    import subprocess
    import sys
    path = tmp_path / 'control.json'
    mod.write_private_json(path, {'long': '中文😀' * 9000})
    output = subprocess.run([sys.executable, mod.__file__, '--url', 'http://unused.invalid',
        'native-control-read', '--file', str(path), '--offset', '0'], capture_output=True, text=True)
    assert output.returncode == 0, output.stderr
    frame = json.loads(output.stdout.removeprefix('NATIVE_CONTROL_PART:'))
    assert frame['file'] == str(path) and frame['eof'] is False
    assert len(frame['text']) <= 6000 and frame['next'] == len(frame['text'])


def test_plan_and_boundary_use_original_binding_and_return_current_runnable_work(mod, tmp_path):
    binding = dict(holder_id='h', task_id='t', node_id='n', lease_id='l', project_id='p', execution_id='e', revision=3)
    mod.write_private_json(tmp_path/'binding.json', binding)
    plan = {'units':[{'id':'ab','case_ids':['c'], 'requires':{'phase':'execution','account_ids':['a','b']}}]}
    class Client:
        url='http://fixture.test'
        calls=[]
        def call(self,tool,args):
            self.calls.append(args)
            assert args['lease_id']=='l' and args['node_id']=='n'
            if args['action']=='work_plan':
                return {'saved':True,'work_plan':{**args['arguments']['work_plan'],'plan_revision':2,
                    'units':[{**plan['units'][0], 'requires':{**plan['units'][0]['requires'],'requirements':[],
                        'account_selection':'required','locks':[],'exclusive_exploration':False}}]}}
            assert args['action']=='request_resources'
            assert args['arguments']['work_token']['work_unit_id']=='ab'
            assert args['arguments']['work_token']['plan_revision']==2
            return {'continued':True,'next_action':'continue_current_work','runnable_case_ids':['other']}
    client=Client()
    assert hasattr(mod,'native_work_plan')
    mod.native_work_plan(client,tmp_path/'binding.json',plan)
    result=mod.native_work_boundary(client,tmp_path/'binding.json','ab')
    assert result['runnable_case_ids']==['other'] and len(client.calls)==2
    saved=json.loads((tmp_path/'binding.json').read_text())
    assert saved['work_plan']['execution_id']=='e' and saved['revision']==3


def test_stage_preflight_persists_exact_complete_accounts_before_setup(mod, tmp_path):
    assert hasattr(mod, 'native_stage_ready'), 'resource stage preflight missing'
    a, _ = inputs()
    token={'work_unit_id':'ab','plan_revision':2,'requirements_digest':'digest'}
    a['claim_arguments']={'work_token':token}
    path=tmp_path/'assignment.json';mod.write_private_json(path,a)
    class ReadOnly:
        url=a['workspace_url']
        def call(self,tool,args):
            assert args['action']=='context' and args['arguments']['work_token']==token
            return {'stage_ready':True,'work_token':token,'account_ids':['A','B'],
                    'required_context_count':2,'source_revision':3,'runnable_case_ids':['original']}
    result=mod.native_stage_ready(ReadOnly(),path,tmp_path)
    assert result['stage_ready']
    saved=json.loads(path.read_text())
    assert saved['claim_arguments']['account_ids']==['A','B']
    assert saved['direct_browser']['context_count']==2
    ready=json.loads((tmp_path/'stage-ready.json').read_text())
    assert ready['identity']['holder_id']==a['holder_id'] and ready['work_token']==token


def test_reverting_work_plan_is_a_new_revision_not_an_old_cached_receipt(lifecycle,tmp_path):
    m=lifecycle
    binding=dict(holder_id='h',task_id='t',node_id='n',lease_id='l',project_id='p',execution_id='e',revision=1)
    m.write_private_json(tmp_path/'binding.json',binding)
    class Client:
        url='http://fixture.test'
        calls=0
        def call(self,tool,args):
            self.calls+=1
            assert args['action']=='work_plan'
            return {'saved':True,'work_plan':{**args['arguments']['work_plan'],'plan_revision':self.calls}}
    client=Client()
    a={'units':[{'id':'a','case_ids':['A']}]};b={'units':[{'id':'b','case_ids':['B']}]}
    assert m.native_work_plan(client,tmp_path/'binding.json',a)['work_plan']['plan_revision']==1
    assert m.native_work_plan(client,tmp_path/'binding.json',b)['work_plan']['plan_revision']==2
    assert m.native_work_plan(client,tmp_path/'binding.json',a)['work_plan']['plan_revision']==3
    assert m.native_work_plan(client,tmp_path/'binding.json',a)['work_plan']['plan_revision']==4
    assert client.calls==4  # Explicit boundary must observe a possible formal successor (0.17.110).


def test_scope_review_keeps_unmapped_source_and_separates_actions(mod, tmp_path):
    cases = [
        {'case_id': 'a', 'scenario': '部分失败仍需人工', 'status': 'failed', 'checkpoints': [
            {'id': 'login', 'status': 'pending_action', 'action_required': '登录'}]},
        {'case_id': 'b', 'status': 'pending_action', 'action_type': 'authorization', 'action_required': '允许外发'},
        {'case_id': 'c', 'status': 'pending_action', 'action_type': 'manual_step', 'action_required': '完成第三方登录',
         'checkpoints': [{'id': 'login', 'status': 'pending_action', 'action_required': '完成第三方登录'},
                         {'id': 'device', 'status': 'pending_action', 'action_required': '连接设备'}]},
        {'case_id': 'd', 'status': 'pending_rule'},
        {'case_id': 'e', 'status': 'blocked', 'not_run_reason': '依赖服务不可用'},
        {'case_id': 'f', 'status': 'not_run', 'not_run_reason': '样本尚未准备'},
    ]
    binding = {'execution_id': 'run', 'revision': 7, 'case_results': {c['case_id']: c for c in cases},
               'coverage': [{'coverage_id': 'source-1', 'feature': '状态转换', 'case_ids': ['a']},
                            {'coverage_id': 'source-2', 'feature': '尚无设计的原始范围', 'case_ids': []}]}
    mod.write_private_json(tmp_path / 'binding.json', binding)
    mod.write_private_json(tmp_path / 'design.json', {'cases': cases, 'requirement_design': {'requirements': [{'id': 'r', 'source_quote': '原文独立规则'}]}})
    result = mod.native_review_state(tmp_path / 'binding.json')
    review = json.loads(Path(result['scope_review_file']).read_text())
    assert review['revision'] == 7
    assert review['coverage'] == binding['coverage']
    assert len(review['cases']) == 6
    assert review['requirement_design']['requirements'][0]['source_quote'] == '原文独立规则'
    assert review['remaining_by_status']['authorization'] == ['b']
    assert review['remaining_by_status']['manual_step'] == ['c']
    assert review['remaining_by_status']['pending_rule'] == ['d']
    assert review['remaining_by_status']['blocked'] == ['e']
    assert review['remaining_by_status']['not_run'] == ['f']
    assert review['pending_actions'][0] == {'case_id': 'a', 'checkpoint_id': 'login',
        'action_type': 'manual_step', 'action_required': '登录'}
    assert len(review['pending_actions']) == 4  # a + b + two real c checkpoints; no derived duplicate
    assert review['semantic_review_complete'] is False
    assert json.loads((tmp_path / 'binding.json').read_text()) == binding


def test_receiver_child_ready_returns_without_terminal_and_stops_on_original_fifo(mod, tmp_path):
    import os
    import sys
    binding = tmp_path / 'binding.json'
    command = [sys.executable, mod.__file__, '--url', 'http://unused.invalid',
               '--credential-file', str(tmp_path / 'unused.json')]
    ready = mod.start_native_observation_receiver(command, binding)
    try:
        assert Path(ready['fifo']).exists()
        assert json.loads((tmp_path / 'native-receiver.json').read_text())['pid'] == ready['pid']
        reused = mod.start_native_observation_receiver(command, binding)
        assert reused['reused'] is True and reused['pid'] == ready['pid']
        os.kill(ready['pid'], 0)  # duplicate launch did not kill the original
    finally:
        mod.stop_native_observation_receiver(binding)
        _, status = os.waitpid(ready['pid'], 0)
    assert status == 0
    assert not Path(ready['fifo']).exists()
    assert json.loads((tmp_path / 'native-receiver.json').read_text())['state'] == 'stopped'


def test_audit_keeps_wrong_event_and_missing_evidence_visible_without_writes(mod, tmp_path):
    binding = {'workspace_url':'http://fixture.test','task_id':'t','node_id':'n','lease_id':'l',
               'project_id':'p','execution_id':'e'}
    mod.write_private_json(tmp_path/'binding.json', binding)
    mod.write_private_json(tmp_path/'ack.json', {'handoff_complete':True,
        'handoff':{'id':'foreign','task_id':'t','node_id':'n','delivery_state':'received'}})
    class ReadOnly:
        url = 'http://fixture.test'
        calls = []
        def call(self, tool, args):
            self.calls.append(tool)
            if tool == 'get_managed_test':
                return {'nodes':[{'id':'n','state':'completed','result':'passed'}], 'leases':[]}
            assert tool == 'get_ui_test_cases'
            return {'cases':[{'case_id':'actual','status':'partial'}]}
    client = ReadOnly()
    result = mod.audit_native_cycle(client,tmp_path/'binding.json',tmp_path/'audit.json',tmp_path/'ack.json')
    assert client.calls == ['get_managed_test','get_ui_test_cases']
    assert {'ack_received','receiver_stopped','passed_state_consistent','save_confirmed','report_published'} <= set(result['remaining'])
    assert (tmp_path/'audit.html').exists()
    with pytest.raises(ValueError):
        mod.audit_native_cycle(client,tmp_path/'binding.json',tmp_path/'audit.json')


class Fake:
    url = 'http://fixture.test'
    def __init__(self, fail=None, queued=False):
        self.calls, self.fail, self.queued = [], fail, queued
    def call(self, tool, args):
        action = args.get('action', 'baseline')
        self.calls.append((action, args))
        if action == self.fail: raise OSError('uncertain receipt')
        if action == 'claim': return {'state': 'queued'} if self.queued else {'state': 'running', 'lease_id': 'lease'}
        if action == 'context': return {'mode': 'native_browser', 'record': None, 'project': {'id': 'project'}, 'case_id_prefix': 'Mnew-'}
        return {'execution_id': 'execution', 'revision': 1}


def test_prepare_normalizes_name_handles_null_and_reuses_receipts(mod, tmp_path):
    client = Fake()
    a, d = inputs()
    ready = mod.prepare_native(client, a, d, tmp_path)
    assert ready['ready'] and ready['http_calls'] == 3
    assert ready['cases'][0]['scenario'] == '配置重开'
    assert ready['cases'][0]['case_id'] == 'Mnew-001'
    assert 'title' not in ready['cases'][0]
    assert mod.prepare_native(client, a, d, tmp_path)['http_calls'] == 0
    assert len(client.calls) == 3
    binding = json.loads((tmp_path / 'binding.json').read_text())
    binding.update(revision=2, case_results={'Mnew-001': {'case_id': 'Mnew-001', 'status': 'passed', 'actual': '已保存观察'}})
    (tmp_path / 'binding.json').write_text(json.dumps(binding))
    reused = mod.prepare_native(client, a, d, tmp_path, resume=True)
    assert reused['http_calls'] == 1 and reused['revision'] == 2
    assert reused['cases'][0]['status'] == 'passed' and reused['cases'][0]['actual'] == '已保存观察'
    assert [c[0] for c in client.calls] == ['claim', 'context', 'baseline', 'claim']
    assert client.calls[2][1]['response'] == 'summary'


@pytest.fixture
def lifecycle(mod):
    # Exercise the source independently of when the downloadable client is exported.
    path = Path(__file__).parents[2] / 'api_test_tool/native_lifecycle.py'
    spec = importlib.util.spec_from_file_location('native_lifecycle_source', path)
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)
    for name in ('batch_lock', 'read_utf8', 'write_private_json', 'check_case_batch'):
        setattr(source, name, getattr(mod, name))
    return source


class ExistingRecord(Fake):
    def __init__(self, assignment, cases):
        super().__init__()
        self.context = {'mode': 'native_browser', 'project': {'id': 'project', 'ui_execution_id': 'execution'},
            'lease': {'id': 'lease-next', 'node_id': 'node'},
            'node': {'id': 'node', 'task_id': 'task', 'executor_dispatch': assignment.copy()},
            'record': {'id': 'execution', 'revision': 9, 'cases': cases}, 'prior_operations': []}
    def call(self, tool, args):
        self.calls.append((args['action'], args))
        if args['action'] == 'claim':
            return {'state': 'running', 'lease_id': 'lease-next'}
        assert args['action'] == 'context', 'resume must not save a new baseline'
        return self.context


def resume_cases():
    return [{'case_id': 'original-pass', 'scenario': '原已完成', 'steps': '原步骤', 'expected': '原预期',
             'status': 'passed', 'actual': '原观察', 'checkpoints': [{'id': 'check-1', 'status': 'passed'}]},
            {'case_id': 'original-blocked', 'scenario': '待恢复', 'steps': '原步骤2', 'expected': '原预期2',
             'status': 'blocked', 'actual': '原身份待核实', 'dependencies': [{'case_id': 'original-pass'}]}]


def test_resume_attaches_original_record_without_local_kit_or_recreating_cases(lifecycle, tmp_path):
    assignment, source = inputs()
    assignment['resume_record'] = {'project_id': 'project', 'execution_id': 'execution'}
    cases = resume_cases()
    client = ExistingRecord(assignment, cases)
    ready = lifecycle.prepare_native(client, assignment, source, tmp_path, resume=True)
    assert ready['resumed'] and ready['cases'] == cases
    assert ready['execution_id'] == 'execution' and ready['revision'] == 9
    assert [action for action, _ in client.calls] == ['claim', 'context']
    binding = json.loads((tmp_path/'binding.json').read_text())
    assert binding['case_counts'] == {'passed': 1, 'blocked': 1}
    assert binding['case_results']['original-pass']['actual'] == '原观察'


def test_resume_new_lease_preserves_previous_binding_and_all_server_results(lifecycle, tmp_path):
    assignment, source = inputs()
    lifecycle.prepare_native(Fake(), assignment, source, tmp_path)
    previous = json.loads((tmp_path/'binding.json').read_text())
    assignment['dispatch_id'] = 'new-dispatch'
    client = ExistingRecord(assignment, resume_cases())
    ready = lifecycle.prepare_native(client, assignment, source, tmp_path, resume=True)
    binding = json.loads((tmp_path/'binding.json').read_text())
    assert binding['lease_id'] == 'lease-next' and binding['previous_bindings'] == [previous]
    assert ready['cases'] == resume_cases() and binding['revision'] == 9
    assert json.loads((tmp_path/'preparation.json').read_text())['resume_history'][0]['design']['cases'][0]['case_id'] == 'Mnew-001'
    assert lifecycle.prepare_native(client, assignment, source, tmp_path)['cases'] == resume_cases()


@pytest.mark.parametrize('changed', ['project', 'execution', 'task', 'executor', 'lease'])
def test_resume_rejects_foreign_server_binding(lifecycle, tmp_path, changed):
    assignment, source = inputs()
    assignment['resume_record'] = {'project_id': 'project', 'execution_id': 'execution'}
    client = ExistingRecord(assignment, resume_cases())
    if changed == 'project': client.context['project']['id'] = 'foreign'
    if changed == 'execution': client.context['record']['id'] = 'foreign'
    if changed == 'task': client.context['node']['task_id'] = 'foreign'
    if changed == 'executor': client.context['node']['executor_dispatch']['executor_ref'] = 'thread:foreign'
    if changed == 'lease': client.context['lease']['id'] = 'foreign'
    with pytest.raises(ValueError, match='不一致'):
        lifecycle.prepare_native(client, assignment, source, tmp_path, resume=True)
    assert not (tmp_path/'design.json').exists()
    assert [action for action, _ in client.calls] == ['claim', 'context']


@pytest.mark.parametrize('pending', ['observation-pending.json', 'receipt-unknown.json'])
def test_resume_pending_observation_stops_before_new_claim(lifecycle, tmp_path, pending):
    assignment, source = inputs()
    lifecycle.write_private_json(tmp_path/pending, {'state': 'unknown'})
    client = Fake()
    with pytest.raises(ValueError, match='原观察保存未确认'):
        lifecycle.prepare_native(client, assignment, source, tmp_path, resume=True)
    assert not client.calls


def test_resume_missing_record_does_not_create_replacement(lifecycle, tmp_path):
    assignment, source = inputs()
    assignment['resume_record'] = {'project_id': 'project', 'execution_id': 'execution'}
    client = Fake()
    with pytest.raises(ValueError, match='不能以新基线代替'):
        lifecycle.prepare_native(client, assignment, source, tmp_path, resume=True)
    assert [action for action, _ in client.calls] == ['claim', 'context']


def test_resume_prior_unknown_operation_does_not_replay(lifecycle, tmp_path):
    assignment, source = inputs()
    assignment['resume_record'] = {'project_id': 'project', 'execution_id': 'execution'}
    client = ExistingRecord(assignment, resume_cases())
    client.context['prior_operations'] = [{'id': 'old-operation', 'state': 'unknown'}]
    with pytest.raises(ValueError, match='原操作仍有未知'):
        lifecycle.prepare_native(client, assignment, source, tmp_path, resume=True)
    assert not (tmp_path/'design.json').exists()


def test_existing_record_needs_explicit_resume_and_record_anchor(lifecycle, tmp_path):
    assignment, source = inputs()
    client = ExistingRecord(assignment, resume_cases())
    with pytest.raises(ValueError, match='已有执行记录'):
        lifecycle.prepare_native(client, assignment, source, tmp_path/'ordinary')
    with pytest.raises(ValueError, match='不一致'):
        lifecycle.prepare_native(client, assignment, source, tmp_path/'unbound', resume=True)


def test_resume_rejects_rebound_executor_before_claim(lifecycle, tmp_path):
    assignment, source = inputs()
    lifecycle.prepare_native(Fake(), assignment, source, tmp_path)
    assignment['executor_ref'] = 'thread:other'
    client = Fake()
    with pytest.raises(ValueError, match='原任务、节点、持有人及执行会话'):
        lifecycle.prepare_native(client, assignment, source, tmp_path, resume=True)
    assert not client.calls


@pytest.mark.parametrize('placement', ['claim_arguments', 'assignment'])
def test_prepare_passes_real_browser_environment_and_keeps_context_binding(lifecycle, tmp_path, placement):
    assignment, source = inputs()
    environment = {'provider': 'iab', 'context_id': 'actual-shared-context', 'isolated': False}
    configuration = {'browser_environment': environment, 'browser_environments': [environment]}
    if placement == 'claim_arguments': assignment['claim_arguments'] = configuration
    else: assignment.update(configuration)
    bound = {'context_id': 'actual-shared-context', 'account_id': 'actual-assigned-account'}
    class ContextFake(Fake):
        def call(self, tool, args):
            result = super().call(tool, args)
            if args.get('action') in {'claim', 'context'}:
                result['native_context_binding'] = bound.copy()
            return result
    client = ContextFake()
    ready = lifecycle.prepare_native(client, assignment, source, tmp_path)
    assert client.calls[0][1]['arguments'] == configuration
    assert ready['native_context_binding'] == bound
    assert json.loads((tmp_path/'binding.json').read_text())['native_context_binding'] == bound
    assert lifecycle.prepare_native(client, assignment, source, tmp_path)['native_context_binding'] == bound


def test_observed_closeout_requires_actual_exit_and_never_publishes_unknown_save(mod, tmp_path):
    binding = {'holder_id':'holder','task_id':'task','node_id':'node','lease_id':'lease','case_counts':{'passed':1}}
    mod.write_private_json(tmp_path / 'binding.json', binding)
    receipt = {'saved':False,'exit':{'browser_stopped':True,'reason':'owned tab absent'}}
    mod.write_private_json(tmp_path / 'native-receiver-response.json', receipt)
    result = mod.native_observed_closeout_arguments(tmp_path / 'binding.json')
    assert result['arguments']['save_unconfirmed'] is True
    assert result['arguments']['publish_saved'] is False
    receipt['exit']['browser_stopped'] = False
    mod.write_private_json(tmp_path / 'native-receiver-response.json', receipt)
    with pytest.raises(ValueError): mod.native_observed_closeout_arguments(tmp_path / 'binding.json')


def test_warm_runtime_kit_omits_source_and_invalidates_changed_code(mod, tmp_path):
    a,d=inputs()
    routine=tmp_path/'routine.js';routine.write_text('return await nativeBrowserCase({case_id:nativeCaseId});')
    receipt=tmp_path/'loaded.json'
    a.update(local_artifact_io=True,local_observation_stream=True,browser_routine_file=str(routine),browser_runtime_receipt=str(receipt))
    mod.write_private_json(tmp_path/'assignment.json',a);mod.write_private_json(tmp_path/'design.json',d)
    def kit(folder):
        return mod.native_run_kit(['python','client'],tmp_path/'assignment.json',tmp_path/'design.json',tmp_path/folder,'https://target.test')
    cold=kit('cold');runtime=cold['runtime']
    assert runtime['loaded_receipt'] is False
    assert not runtime['combined_entry']
    mod.write_private_json(receipt,{'key':runtime['key'],'executor_ref':'thread:worker'})
    warm=kit('warm');prompt=warm['message_arguments']['prompt']
    assert warm['runtime']['loaded_receipt'] is True
    assert warm['runtime']['combined_entry']
    assert 'cua.createBrowserTab' in warm['runtime']['call_source']
    assert 'native_call' in prompt and 'async function nativeBrowserCase' not in prompt
    mod.write_private_json(tmp_path/'warm'/'binding.json',a)
    prepared = mod.native_prepared_call(tmp_path/'warm', {'ready':True,'cases':[{'case_id':'actual-new'}]})
    assert 'nativeLoadedCases.get' in prepared and 'actual-new' in prepared
    assert mod.native_prepared_call(tmp_path/'warm', {'ready':False}) is None
    assert len(prompt)<len(cold['message_arguments']['prompt'])/2
    routine.write_text(routine.read_text()+'\n// version changed')
    assert kit('changed')['runtime']['loaded_receipt'] is False
    assert kit('warm')['runtime']['loaded_receipt'] is False
    assert not (tmp_path/'warm'/'prepared-call.json').exists()


def test_exit_before_notification_failure_releases_without_publishing_stale_receipt(mod, tmp_path):
    mod.write_private_json(tmp_path/'binding.json',{'holder_id':'h','task_id':'t','node_id':'n','lease_id':'l','case_counts':{'passed':1}})
    mod.write_private_json(tmp_path/'native-exit-observation.json',{'request_id':'new','exit':{'browser_stopped':True,'reason':'actual absence'}})
    assert mod.native_observed_closeout_arguments(tmp_path/'binding.json')['arguments']['save_unconfirmed']
    mod.write_private_json(tmp_path/'native-receiver-response.json',{'request_id':'old','saved':True})
    assert mod.native_observed_closeout_arguments(tmp_path/'binding.json')['arguments']['publish_saved'] is False


def test_registered_function_uses_each_calls_current_binding_without_source_reload(mod, tmp_path):
    import subprocess
    package=mod.native_runtime_package('return {tab:nativeTab,id:nativeCaseId,directory};','thread:worker',tmp_path/'ready.json')
    source='globalThis.nodeRepl={write:v=>console.log(JSON.stringify(v))};\n'+package['registration_source']
    source+='\nvar nativeTab="tab-a",nativeCaseId="case-a";\n'+mod.native_runtime_call(package['key'],'/run-a')
    source+='\nnativeTab="tab-b";nativeCaseId="case-b";\n'+mod.native_runtime_call(package['key'],'/run-b')
    script=tmp_path/'runtime.mjs';script.write_text(source)
    result=subprocess.run(['node',str(script)],text=True,capture_output=True,check=True)
    rows=[json.loads(line) for line in result.stdout.splitlines() if 'timing_warning' not in line]
    assert rows[1]=={'tab':'tab-a','id':'case-a','directory':'/run-a'}
    assert rows[2]=={'tab':'tab-b','id':'case-b','directory':'/run-b'}
    assert json.loads((tmp_path/'ready.json').read_text())['key']==package['key']


def test_default_library_reuses_across_modules_and_legacy_call_needs_no_new_settings(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod.Path,'home',classmethod(lambda cls:tmp_path))
    a,d=inputs();a.update(local_artifact_io=True,local_observation_stream=True)
    mod.write_private_json(tmp_path/'assignment.json',a);mod.write_private_json(tmp_path/'design.json',d)
    def kit(folder):
        return mod.native_run_kit(['python','client'],tmp_path/'assignment.json',tmp_path/'design.json',tmp_path/folder,'https://target.test')
    first=kit('module-a');runtime=first['runtime']
    assert runtime['kind']=='library' and not runtime['loaded_receipt']
    mod.write_private_json(runtime['receipt_file'],{'key':runtime['key'],'executor_ref':'thread:worker'})
    a['node_id']='another-module';mod.write_private_json(tmp_path/'assignment.json',a)
    d['cases'][0]['title']='另一个模块实际设计';mod.write_private_json(tmp_path/'design.json',d)
    second=kit('module-b')
    assert second['runtime']['key']==runtime['key'] and second['runtime']['loaded_receipt']
    assert not second['runtime']['combined_entry']
    assert 'cua.createBrowserTab' not in second['runtime']['call_source']
    assert 'async function nativeBrowserCase' not in second['message_arguments']['prompt']
    assert 'module-b' in second['runtime']['call_source'] and 'module-a' not in second['runtime']['call_source']
    routine=tmp_path/'legacy.js';routine.write_text('var nativeSummary={status:"actual"};')
    a['browser_call_file']=str(routine);mod.write_private_json(tmp_path/'assignment.json',a)
    legacy=kit('legacy')
    assert legacy['runtime']['kind']=='routine' and 'return typeof nativeSummary' in legacy['runtime']['registration_source']


@pytest.mark.parametrize('failed, expected', [('claim', ['claim']), ('context', ['claim', 'context']), ('baseline', ['claim', 'context', 'baseline'])])
def test_failure_stops_dependent_steps_and_unknown_writes_cannot_replay(mod, tmp_path, failed, expected):
    client = Fake(fail=failed)
    a, d = inputs()
    with pytest.raises(OSError): mod.prepare_native(client, a, d, tmp_path)
    with pytest.raises(ValueError, match='后续步骤已停止'): mod.prepare_native(client, a, d, tmp_path, resume=True)
    assert [c[0] for c in client.calls] == [*expected, 'context']  # one read-only reconciliation, no write replay
    assert not (tmp_path / 'design.json').exists()
    if failed != 'claim':
        b = json.loads((tmp_path / 'binding.json').read_text())
        assert mod.native_closeout_arguments(b, browser_stopped=True, reason='No browser opened')['lease_id'] == 'lease'


def test_queue_does_not_prepare_until_real_resume(mod, tmp_path):
    client = Fake(queued=True)
    a, d = inputs()
    assert mod.prepare_native(client, a, d, tmp_path)['state'] == 'waiting'
    assert mod.prepare_native(client, a, d, tmp_path)['http_calls'] == 0
    client.queued = False
    assert mod.prepare_native(client, a, d, tmp_path, resume=True)['ready']
    assert [c[0] for c in client.calls] == ['claim', 'claim', 'context', 'baseline']


def test_invalid_design_fails_before_any_resource_claim(mod, tmp_path):
    client = Fake()
    a, d = inputs()
    d['cases'][0]['status'] = 'passed'
    with pytest.raises(ValueError, match='历史结果'): mod.prepare_native(client, a, d, tmp_path)
    assert not client.calls


def test_result_failure_prevents_next_case_and_closeout_needs_actual_exit(mod, tmp_path):
    client = Fake()
    a, d = inputs()
    d['cases'].append({**d['cases'][0], 'case_id': 'second'})
    mod.prepare_native(client, a, d, tmp_path)
    calls = []
    def record(*args):
        calls.append(args)
        raise OSError('lost result')
    client.native_record = record
    with pytest.raises(OSError): mod.observed_native(client, tmp_path/'binding.json', 'Mnew-001', 'passed', '实际观察', tmp_path/'r1.json')
    with pytest.raises(ValueError, match='后续步骤已停止'): mod.observed_native(client, tmp_path/'binding.json', 'Mnew-002', 'passed', '另一观察', tmp_path/'r2.json')
    assert len(calls) == 1
    b = json.loads((tmp_path/'binding.json').read_text())
    with pytest.raises(ValueError, match='实际关闭'): mod.native_closeout_arguments(b, browser_stopped=False, reason='not closed')
    args = mod.native_closeout_arguments(b, browser_stopped=True, reason='own tabs closed')
    assert args['arguments']['publish_saved'] is True
    assert args['arguments']['result'] == 'partial'
    assert 'final_report' not in args['arguments']
    b['case_counts'] = {'passed': 1, 'not_run': 0, 'failed': 0}
    args = mod.native_closeout_arguments(b, browser_stopped=True, reason='own tabs closed')
    # Registered cases passing does not establish complete module exploration.
    assert args['arguments']['result'] == 'passed' and args['arguments']['coverage_complete'] is False
    b['case_counts']['not_run'] = 1
    args = mod.native_closeout_arguments(b, browser_stopped=True, reason='own tabs closed')
    assert args['arguments']['result'] == 'partial' and args['arguments']['coverage_complete'] is False


def test_structured_observation_preserves_model_verdict_and_each_check(mod):
    observation = {'case_id': 'A', 'status': 'passed', 'checks': [
        {'name': '中文/引号', 'expected': {'value': 2}, 'observed': {'value': 2}, 'ok': True}]}
    assert json.loads(mod.observation_actual(observation)) == observation['checks'][0]
    observation['checks'][0]['ok'] = False
    assert json.loads(mod.observation_actual(observation)) == observation['checks'][0]
    observation['checks'][0]['ok'] = 'true'
    with pytest.raises(ValueError, match='不猜测'): mod.observation_actual(observation)


def test_run_kit_reuses_same_inputs_without_claiming_and_unknown_save_is_partial(mod, tmp_path):
    a, d = inputs()
    assignment, design = tmp_path/'assignment.json', tmp_path/'selected.json'
    assignment.write_text(json.dumps(a))
    design.write_text(json.dumps(d))
    args = (['python3', '/verified/client.py'], assignment, design, tmp_path, 'https://target.test/page')
    kit = mod.native_run_kit(*args)
    assert kit['message_arguments']['threadId'] == 'worker'
    assert 'model' not in kit['message_arguments'] and 'thinking' not in kit['message_arguments']
    assert str(tmp_path/'native-cycle.js') in kit['message_arguments']['prompt']
    assert mod.native_run_kit(*args) == kit
    assert not (tmp_path/'preparation.json').exists()
    with pytest.raises(ValueError, match='不能覆盖'):
        mod.native_run_kit(*args[:-1], 'https://target.test/other')
    close = mod.native_closeout_arguments({'holder_id':'h','task_id':'t','node_id':'n','lease_id':'l',
        'case_counts':{'passed':1}},browser_stopped=True,reason='closed',save_unconfirmed=True)
    assert close['arguments']['result'] == 'partial'
    assert close['arguments']['publish_saved'] is False
    assert close['arguments']['save_unconfirmed'] is True


def test_same_case_can_advance_without_overwriting_observations_but_unknown_save_still_stops(mod, tmp_path):
    client = Fake()
    mod.prepare_native(client, *inputs(), tmp_path)
    calls = []
    client.native_record = lambda binding, payload, receipt: calls.append(str(receipt)) or {'saved': True}
    first = {'case_id': 'Mnew-001', 'status': 'partial', 'checks': [
        {'name': 'actual content', 'expected': 'ready', 'observed': 'pending', 'ok': False}]}
    later = {'case_id': 'Mnew-001', 'status': 'passed', 'checks': [
        {'name': 'actual content', 'expected': 'ready', 'observed': 'ready', 'ok': True}]}
    def save(value): return mod.observed_native_json(client, tmp_path/'binding.json', value, tmp_path/'observation.json', tmp_path/'receipt.json')
    one, two = save(first), save(later)
    assert one['receipt_file'] != two['receipt_file']
    assert json.loads(Path(one['observation_file']).read_text()) == first
    assert json.loads(Path(two['observation_file']).read_text()) == later
    assert save(later)['receipt_file'] == two['receipt_file']
    def uncertain(*args): raise OSError('unknown save')
    client.native_record = uncertain
    with pytest.raises(OSError): save(first)
    with pytest.raises(ValueError, match='后续步骤已停止'): save(later)


def test_verified_artifact_io_generates_load_and_export_without_retyping_helper(mod, tmp_path):
    a, d = inputs()
    a['local_artifact_io'] = True
    assignment, design = tmp_path/'assignment.json', tmp_path/'selected.json'
    assignment.write_text(json.dumps(a)); design.write_text(json.dumps(d))
    kit = mod.native_run_kit(['python3','/client.py'], assignment, design, tmp_path, 'https://target.test/page')
    assert 'writeFile' in kit['browser_bootstrap']
    assert 'mode:0o600' in kit['browser_bootstrap']
    assert 'async function nativeBrowserCase' in kit['message_arguments']['prompt']
    assert 'new Function' not in kit['browser_bootstrap']
    assert 'local_artifact_io' not in kit['browser_bootstrap']


def test_combined_runtime_fails_before_open_on_reset_and_stops_on_open_error(mod, tmp_path):
    import subprocess
    call=mod.native_runtime_call('verified',tmp_path,entry_url='https://target.test')
    source="let opens=0,runs=0;\nglobalThis.cua={createBrowserTab:async()=>{opens++;throw new Error('open failed')}};\nglobalThis.nodeRepl={write:()=>{}};\nvar nativeCaseId='case';\ntry { CALL } catch(e) { if(!e.message.includes('session reset'))throw e; }\nif(opens||runs)throw new Error('reset performed business');\nvar nativeLoadedCases=new Map([['verified',async()=>{runs++}]]);\ntry { CALL } catch(e) { if(e.message!=='open failed')throw e; }\nif(opens!==1||runs)throw new Error('failed open continued business');\ncua.createBrowserTab=async(_,url,options)=>{opens++;return {url,options}};\nnativeLoadedCases.set('verified',async input=>{runs++;if(input.tab.url!=='https://target.test'||input.tab.options.visible!==false||input.case_id!=='case')throw new Error('wrong binding');return {};});\nCALL\nif(opens!==2||runs!==1)throw new Error('extra invocation');\n".replace('CALL',call)
    script=tmp_path/'combined.mjs';script.write_text(source)
    subprocess.run(['node',str(script)],capture_output=True,text=True,check=True)


def test_ack_matches_original_event_before_any_action(mod):
    a={'task_id':'t','node_id':'n','coordinator_ref':'thread:coordinator','coordinator_holder_id':'holder'}
    b={**a,'lease_id':'event'}
    event={'task_id':'t','node_id':'n','event_id':'event'}
    args=mod.native_ack_arguments(a,b,event)
    assert args['holder_id']=='holder' and args['arguments']['handoff_ack']==event
    for key in event:
        with pytest.raises(ValueError):mod.native_ack_arguments(a,b,{**event,key:'foreign'})
    with pytest.raises(ValueError):mod.native_ack_arguments(a,{**b,'coordinator_ref':'thread:other'},event)


def test_prepared_call_rejects_other_binding_and_never_replays_saved_case(mod, tmp_path):
    a,_=inputs();mod.write_private_json(tmp_path/'prepared-call.json', {'source':'known','binding':a})
    mod.write_private_json(tmp_path/'binding.json',a)
    assert mod.native_prepared_call(tmp_path, {'ready':True,'cases':[{'case_id':'c','status':'passed'}]}) is None
    mod.write_private_json(tmp_path/'binding.json',{**a,'node_id':'other'})
    with pytest.raises(ValueError):mod.native_prepared_call(tmp_path, {'ready':True,'cases':[{'case_id':'c'}]})


def test_review_exposes_pending_stage_and_original_resource_wait_without_reclassifying(mod, tmp_path):
    cases = [{'case_id': 'done', 'status': 'passed'}, {'case_id': 'todo', 'status': 'not_run'},
             {'case_id': 'partial', 'status': 'partial'},
             {'case_id': 'excluded', 'status': 'not_run', 'account_scope': 'multi_account'}]
    binding = {'execution_id': 'e', 'project_id': 'p', 'revision': 4,
        'task_id': 't', 'node_id': 'n', 'lease_id': 'l',
        'case_results': {c['case_id']: c for c in cases},
        'work_plan': {'project_id': 'p', 'execution_id': 'e', 'plan_revision': 2,
            'units': [{'id': 'prepare', 'case_ids': ['done']},
                      {'id': 'write', 'case_ids': ['todo', 'partial', 'excluded']}]}}
    mod.write_private_json(tmp_path / 'binding.json', binding)
    boundary = {'request': {'task_id': 't', 'node_id': 'n', 'lease_id': 'l'},
                'result': {'release_required': True, 'waiting_resources': True}}
    mod.write_private_json(tmp_path / 'work-boundary.json', boundary)
    result = mod.native_review_state(tmp_path / 'binding.json')
    review = json.loads(Path(result['scope_review_file']).read_text())
    assert review['unfinished_work_units'] == [{'unit_id': 'write', 'case_ids': ['todo', 'partial']}]
    assert review['resource_boundary'] == boundary['result']
    assert result['unfinished_work_units'] == review['unfinished_work_units']
    assert json.loads((tmp_path / 'binding.json').read_text()) == binding
    # An old lease's receipt is not current resource truth after a real continuation.
    boundary['request']['lease_id'] = 'older'
    mod.write_private_json(tmp_path / 'work-boundary.json', boundary)
    mod.native_review_state(tmp_path / 'binding.json')
    assert json.loads(Path(result['scope_review_file']).read_text())['resource_boundary'] is None


def test_review_does_not_infer_cleanup_done_from_business_pass(mod, tmp_path):
    binding = {'execution_id': 'e', 'project_id': 'p', 'revision': 4,
        'case_results': {'a': {'case_id': 'a', 'status': 'passed'}},
        'work_plan': {'project_id': 'p', 'execution_id': 'e', 'units': [
            {'id': 'cleanup', 'purpose': 'cleanup', 'case_ids': ['a']}]}}
    mod.write_private_json(tmp_path / 'binding.json', binding)
    result = mod.native_review_state(tmp_path / 'binding.json')
    assert result['unfinished_work_units'] == [
        {'unit_id': 'cleanup', 'case_ids': ['a'], 'completion_requires_receipt': True}]
