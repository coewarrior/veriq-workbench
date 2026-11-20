"""Regression tests for complete design storage and environment-bound execution."""
import copy
import json
import pytest
from fastapi.testclient import TestClient
from api_test_tool import web
from api_test_tool.assertions import validate_assertion, evaluate_assertion
from api_test_tool.web_generation import compile_model_bundle, approve_cases, refresh_approval_eligibility
from test_web_generation import contract, proposal, gomoku_contract


def test_empty_username_is_rejected_input_not_fixed_registration(contract):
    plan = proposal('post_reg')
    case = plan['cases'][0]
    case['steps'][0]['request']['json'] = {'username': '', 'password': 'test'}
    case['cleanup_policy'] = {'strategy':'none', 'reason':'文档明确拒绝空用户名，无账号创建'}
    bundle = compile_model_bundle(gomoku_contract(contract), json.dumps(plan))
    assert bundle['cases'][0]['web']['approval_eligible']
    assert approve_cases(bundle, ['AI-001'])['cases'][0]['state'] == 'READY'
    # Re-open a persisted candidate affected by the old classifier, without auto approval.
    bundle['cases'][0].update(state='QUARANTINED', reason='五子棋固定空白或单字符用户名需要完整隔离重置，网页保持隔离')
    repaired = refresh_approval_eligibility(bundle)['cases'][0]
    assert repaired['state'] == 'NEEDS_RULE' and repaired['web']['approval_eligible']


@pytest.mark.parametrize('kind,expected,status,passed', [
    ('status_in',[200,400],200,True), ('status_in',[200,400],400,True),
    ('status_in',[200,400],500,False), ('status_not_in',[500],500,False),
    ('status_not_in',[500],200,True),
])
def test_http_status_sets(kind, expected, status, passed):
    assertion = {'kind':kind, 'expected':expected, 'rule_id':'documented'}
    assert not validate_assertion(assertion)
    assert evaluate_assertion(assertion, {'status':status}, {})['passed'] is passed


@pytest.mark.parametrize('values',[[],[True],[99],[600],['200'],200,None])
def test_invalid_http_status_sets(values):
    for kind in ('status_in','status_not_in'):
        assert validate_assertion({'kind':kind,'expected':values,'rule_id':'r'})


@pytest.fixture
def workspace(tmp_path):
    with TestClient(web.create_app(tmp_path, start_fixture=False, testing=True)) as browser:
        browser.headers['x-csrf-token'] = browser.get('/api/bootstrap').json()['csrf']
        code = browser.post('/api/mcp/pair').json()['code']
        token = browser.post('/api/mcp/redeem',json={'code':code}).json()['token']
        def call(action, **arguments):
            result = browser.post('/api/mcp/call', headers={'Authorization':'Bearer '+token},
                                  json={'action':action,'arguments':arguments})
            assert result.status_code == 200, result.text
            return result.json()
        doc = {'openapi':'3.0.3','info':{'title':'上传的接口文档','version':'1'},'paths':{
            '/reg':{'post':{'operationId':'post_reg','responses':{'200':{'description':'注册成功'}}}},
            '/info':{'get':{'operationId':'get_info','responses':{'200':{'description':'读取成功'}}}}}}
        imported = call('import', title='上传接口回归', filename='uploaded.json', content=json.dumps(doc))
        pid = imported['project']['id']
        assert not imported['project'].get('template')
        yield browser, call, pid


def owned_registration(context):
    op = context['contract']['operations']['post_reg']
    sid = op['source_ids'][0]
    return {'id':'REG-OWNED','title':'独立账号注册','operation_id':'post_reg',
            'variables':{'username':{'kind':'unique','prefix':'mvp_'}},
            'steps':[{'id':'reg','operation_id':'post_reg','request':{'json':{'username':'${username}','password':'test-password'}},
            'assertions':[{'kind':'status','expected':200,'evidence':[{'source_id':sid,'quote':context['contract']['sources'][sid]['excerpt']}]}]}]}


def test_uploaded_document_binding_refreshes_cleanup_and_prevents_target_switch(workspace, monkeypatch):
    browser, call, pid = workspace
    context = call('context', project_id=pid)
    assert context['execution_capabilities']['gomoku_cleanup'] is None
    saved = call('submit', project_id=pid, revision=context['revision'], cases=[owned_registration(context)])
    assert saved['summary']['approval_eligible'] == 0
    call('task', project_id=pid, environment='gomoku')
    context = call('context', project_id=pid)
    assert context['execution_capabilities']['gomoku_cleanup']
    assert context['case_status'][0]['review']['approval_eligible']
    assert context['case_status'][0]['state'] == 'NEEDS_RULE'
    review = call('approve', project_id=pid, case_ids=['REG-OWNED'])
    assert review['accepted_case_ids'] == ['REG-OWNED']
    # A selected target with cleanup cannot silently execute on another server.
    result = browser.post(f'/api/projects/{pid}/run',json={'environment':'custom','base_url':'http://127.0.0.1:18082'})
    assert result.status_code == 400 and '不能切换' in result.json()['detail']
    # Reach the actual execution adapter with an uploaded document. No shared HTTP in CI.
    calls=[]
    def cleanup(bundle):
        calls.append(('cleanup', bundle['web']['trusted_cleanup']))
        raise ValueError('regression reached cleanup adapter')
    monkeypatch.setattr(web,'gomoku_mysql_cleanup',cleanup)
    monkeypatch.setenv('GOMOKU_CLEANUP_MODE','mysql')
    result = browser.post(f'/api/projects/{pid}/run',json={'environment':'gomoku'})
    assert result.status_code == 400 and 'reached cleanup adapter' in result.json()['detail']
    assert calls == [('cleanup','gomoku')]
    call('task', project_id=pid, environment='custom', base_url='http://127.0.0.1:18082')
    context = call('context', project_id=pid)
    assert context['execution_capabilities']['gomoku_cleanup'] is None
    assert context['case_status'][0]['state'] == 'NEEDS_RULE'
    assert not context['case_status'][0]['review']['approval_eligible']
    assert call('approve',project_id=pid,case_ids=['REG-OWNED'])['accepted_case_ids'] == []


def test_complete_design_survives_batching_and_individual_compilation(workspace):
    browser, call, pid = workspace
    context=call('context',project_id=pid)
    designs=[{'id':f'DESIGN-{i:03}', 'title':f'独立场景 {i}', 'operation_id':'post_reg', 'steps':[],
              'design':{'category':['正向','逆向','边界','安全'][i%4], 'inputs':f'用户名参数组合 {i}',
                        'procedure':'设置输入后注册，再校验响应与数据影响', 'expected':'返回文档规定的业务结果',
                        'execution_gap':'尚未编译请求步骤'}} for i in range(92)]
    revision=context['revision']
    for start in range(0,len(designs),20):
        result=call('submit',project_id=pid,revision=revision,cases=designs[start:start+20])
        revision=result['revision']
    assert result['summary']['total']==92
    read=[]
    offset=0
    while True:
        context=call('context',project_id=pid,offset=offset,limit=17)
        read+=context['candidates']['cases']
        offset=context['pagination']['next_offset']
        if offset is None: break
    assert read==designs
    reviewed=call('approve',project_id=pid,case_ids=[c['id'] for c in designs])
    assert not reviewed['accepted_case_ids'] and len(reviewed['skipped_cases'])==92
    # Compiling one case updates its stable ID, keeping all remaining designs intact.
    call('task',project_id=pid,environment='gomoku')
    context=call('context',project_id=pid)
    compiled=owned_registration(context)
    compiled['id']=designs[0]['id'];compiled['design']=copy.deepcopy(designs[0]['design'])
    compiled['design']['execution_gap']=''
    saved=call('submit',project_id=pid,revision=context['revision'],cases=[compiled])
    assert saved['summary']['total']==92 and saved['summary']['approval_eligible']==1
    bundle=browser.get(f'/api/projects/{pid}').json()['bundle']
    assert len(bundle['cases'])==92
    assert bundle['cases'][1]['design']==designs[1]['design']
    assert bundle['cases'][0]['design']['execution_gap']==''
    published=call('task_report',project_id=pid,title='设计与执行状态',summary='设计保存完成，尚未发送业务请求')
    report=browser.get(published['report']['report_url'])
    assert '92 条具体设计' in report.text
    snapshot_url=published['report']['report_url'].replace('index.html','cases.html')
    snapshot=browser.get(snapshot_url)
    assert snapshot.status_code==200 and '用户名参数组合 91' in snapshot.text
    assert '完整测试设计' in snapshot.text
    # Report design is frozen, even after later session edits.
    context=call('context',project_id=pid)
    changed=copy.deepcopy(compiled);changed['design']['inputs']='后来改写的输入'
    call('submit',project_id=pid,revision=context['revision'],cases=[changed])
    assert '后来改写的输入' not in browser.get(snapshot_url).text
    progress=browser.get(f'/api/projects/{pid}').json()['project']['mcp_progress']
    assert any('0 次真实请求' in event.get('message','') for event in progress['history'])


def test_failed_login_then_success_is_not_brute_force_quarantine(contract):
    from api_test_tool.web_generation import _quarantine
    def login(success):
        return {"request":{"path":"/login"},"assertions":[{"kind":"json_equal","pointer":"/result","expected":success}]}
    case={"title":"错误登录后使用正确密码恢复", "steps":[login(False),login(True)]}
    assert _quarantine(case) is None
    case['steps']=[login(False),login(False)]
    assert _quarantine(case) == '连续错误登录场景保持隔离'


def test_gomoku_disconnect_stops_later_requests_through_web(workspace, monkeypatch):
    import time
    import requests
    browser, call, pid = workspace
    call('task', project_id=pid, environment='gomoku')
    ctx=call('context',project_id=pid)
    first=owned_registration(ctx);second=copy.deepcopy(first);second['id']='REG-SECOND'
    call('submit',project_id=pid,revision=ctx['revision'],cases=[first,second])
    call('approve',project_id=pid,case_ids=[first['id'],second['id']])
    sent=[];cleaned=[]
    class Offline(requests.Session):
        def send(self, request, **kwargs):
            sent.append(request.url)
            raise requests.ConnectionError('controlled service outage')
    monkeypatch.setattr(web,'pinned_session',lambda *args:Offline())
    monkeypatch.setenv('GOMOKU_CLEANUP_MODE','mysql')
    monkeypatch.setattr(web,'gomoku_mysql_cleanup',lambda bundle: lambda contexts: cleaned.append(contexts) or {'status':'PASS','details':{}})
    job=call('run',project_id=pid,environment='gomoku')
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        done=call('job',job_id=job['id'])
        if done['status'] in {'failed','completed'}:break
        time.sleep(.01)
    assert done['status']=='completed',done
    counts=done['result']['summary']
    assert counts['BROKEN']==1 and counts['BLOCKED']==1 and not counts['complete']
    assert done['result']['requests_sent']==1 and len(sent)==1 and len(cleaned)==1
    assert browser.get(f'/api/projects/{pid}/artifacts/environment.json').json()['stop_on_network_error'] is True


def response_branches():
    return {'anyOf':[
        {'type':'object','required':['status'],'properties':{'status':{'type':'integer','minimum':400,'maximum':499},'json':{'not':{'type':'object','required':['username']}}}},
        {'type':'object','required':['status','json'],'properties':{'status':{'const':200},'json':{'type':'object','required':['username'],'properties':{'username':{'const':'owner'}}}}}
    ]}


@pytest.mark.parametrize('status,body,expected',[(200,{'username':'owner'},True),(200,{'username':'another'},False),(200,{},False),(404,None,True),(403,{'username':'another'},False),(500,{'username':'owner'},False)])
def test_response_branches_reject_identity_leak_and_server_error(status,body,expected):
    a={'kind':'response_schema','expected':response_branches(),'rule_id':'document'}
    assert validate_assertion(a)==[]
    observed={'status':status}
    if body is not None:observed['json']=body
    assert evaluate_assertion(a,observed,{})['passed'] is expected


def test_response_schema_cannot_bypass_regex_or_reference_validation(contract):
    plan=proposal()
    a=plan['cases'][0]['steps'][0]['assertions'][0]
    a.update(kind='response_schema',expected={'properties':{'json':{'properties':{'username':{'pattern':'(a+)+$'}}}}})
    bundle=compile_model_bundle(contract,json.dumps(plan))
    assert bundle['cases'][0]['state']=='UNSUPPORTED'
    a['expected']={'$ref':'https://example.invalid/schema'}
    with pytest.raises(ValueError):compile_model_bundle(contract,json.dumps(plan))
