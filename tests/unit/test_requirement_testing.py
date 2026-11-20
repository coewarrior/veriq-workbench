"""Requirements → checkpoints → adapters → focused continuation, local data only."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from api_test_tool import web
from api_test_tool.requirement_design import classify

PRD = '''# 付款需求（合成测试资料）
## 业务规则
- 打开充值弹窗，展示可购买服务。
- 只有收款确认且权益到账才完成。
- 重复成功通知只增加一次权益。
- 相同业务键并发发起只创建一单。
## 测试适配器契约
- GET /orders/{order_id} 返回 order_id、payer_id、amount、credits、state。
- POST /payment-control 接受 order_id、scenario、event、provider_transaction_id，模拟通道控制，响应 ack=true。
- POST /init 接受 key，并发创建测试订单，返回 order_id。
- POST /prepare 创建独立测试订单，响应 ack=true。
- DELETE /cleanup 删除本轮订单，响应 ack=true。
- 适配器成功的 HTTP 状态为 200。
'''


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'generate_text', lambda *a, **kw: pytest.fail('No paid model calls'))
    app = web.create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        token = client.post('/api/mcp/redeem', json={'code': client.post('/api/mcp/pair').json()['code']}).json()['token']
        def call(action, **args):
            response = client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token}, json={'action': action, 'arguments': args})
            assert response.status_code == 200, response.text
            return response.json()
        call.client = client
        def raw(action, **args):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token}, json={'action': action, 'arguments': args})
        yield client, app, call, raw


def create(call, **extra):
    extra.setdefault('target_url', 'https://example.test/pay')
    if 'account_project_id' not in extra:
        project = call.client.post('/api/account-projects', json={
            'name': '需求测试合成项目', 'login_url': extra['target_url']})
        assert project.status_code == 200, project.text
        extra['account_project_id'] = project.json()['id']
    return call('start_workflow', goal='按需求设计付款测试，先执行独立项目', filename='payment.md', content=PRD, **extra)['project_id']


def point(pid='view', **extra):
    return {'id': pid, 'title': '展示服务' if pid == 'view' else pid, 'kind': 'browser',
            'expected': '展示可购买服务', 'basis': '打开充值弹窗，展示可购买服务。', **extra}


def case(cid='PAY', **extra):
    return {'case_id': cid, 'scenario': '充值与到账', 'environment': 'test', 'client': 'C端',
            'module': '充值', 'executor': 'AI', 'precondition': '独立合成订单', 'test_data': '测试用户 user-1',
            'steps': '打开弹窗、发起测试付款、核对本订单到账', 'expected': '收款和权益均确认',
            'checkpoints': [point()], **extra}


def result(call, pid, saved, sid='view', cid='PAY', **extra):
    return call('record_checkpoint', project_id=pid, execution_id=saved['execution_id'], revision=saved['revision'],
                case_id=cid, checkpoint_id=sid, result={'status': 'passed', 'actual': '可购买服务已显示', 'verification_mode': 'real', **extra})


def test_prd_requires_owning_project_and_preserves_complete_traceability_and_design_report(workspace):
    client, app, call, raw = workspace
    text = '# 验收（合成）\n' + '\n'.join(f'- 验收 {i}：字段 {i} 按配置显示。' for i in range(1, 17))
    missing = call('start_workflow', goal='测试验收字段', filename='requirements.md', content=text)
    assert missing['created'] is False and missing['required_inputs'] == ['account_project_id']
    assert call('list_sessions', test_kind='ui')['sessions'] == []
    account_project = client.post('/api/account-projects', json={
        'name': '验收字段合成项目', 'login_url': 'https://example.test/fields'}).json()
    started = call('start_workflow', goal='测试验收字段', filename='requirements.md', content=text,
                   account_project_id=account_project['id'], target_url='https://example.test/fields')
    pid = started['project_id']
    assert started['status']['ready_for_design'] is True
    assert started['status']['ready_for_execution'] is True
    assert started['project']['document_kind'] == 'requirements'
    design = call('save_requirement_design', project_id=pid, revision=0, requirements=[{
        'id': f'AC{i}', 'title': f'字段 {i}', 'kind': 'acceptance', 'source_quote': f'验收 {i}：字段 {i} 按配置显示。'} for i in range(1, 17)])
    assert len(design['requirements_without_cases']) == 16
    saved = call('ui_cases', project_id=pid, cases=[case(f'C{i}', requirement_ids=[f'AC{i}'],
        checkpoints=[point(expected=f'字段 {i} 按配置显示')]) for i in range(1, 17)])
    inventory = call('requirement_design', project_id=pid)
    assert inventory['requirements_without_cases'] == [] and len(inventory['traceability']) == 16
    owner = app.state.store.session(client.cookies['api_test_session'])[0]['id']
    app.state.store.update_project(owner, pid, {'ui_target_url': ''})  # Saving an observation does not launch execution.
    observed = raw('record_checkpoint', project_id=pid, execution_id=saved['execution_id'], revision=saved['revision'],
                   case_id='C1', checkpoint_id='view', result={'status': 'passed', 'actual': '执行者已有观察', 'verification_mode': 'real'})
    assert observed.status_code == 200, observed.text
    assert call('ui_read', project_id=pid)['cases'][0]['checkpoints'][0]['actual'] == '执行者已有观察'
    call('save_materials', project_id=pid, target_url='https://example.test/fields')
    report = call('ui_publish', project_id=pid, execution_id=saved['execution_id'], title='设计报告', summary='仅设计，未执行')['report']
    rendered = client.get(report['report_url']).text
    assert '需求覆盖与未完成检查' in rendered and '仅设计' in rendered
    assert client.get(report['report_url'].replace('index.html', 'cases.xlsx')).status_code == 200


def test_classifier_routes_openapi_and_never_treats_prd_keywords_as_interfaces(workspace):
    client, app, call, raw = workspace
    assert classify(PRD, 'prd.md') == 'requirements'
    doc = json.dumps({'openapi': '3.0.3', 'info': {'title': '合成', 'version': '1'}, 'paths': {'/health': {'get': {'responses': {'200': {'description': 'OK'}}}}}})
    api = call('start_workflow', goal='设计接口测试', content=doc, filename='openapi.json')
    assert api['status']['test_kind'] == 'api'
    route = client.post('/api/requirement-tests', json={'filename': 'api.json', 'content': doc, 'title': '结构识别'}).json()
    assert route['document_kind'] == 'api' and route['workspace_url'] == '/api-testing'
    assert call('start_workflow', goal='按需求设计', test_kind='requirements')['required_inputs'] == ['filename+content', 'account_project_id']


def test_missing_ledger_is_diagnostic_and_checkpoint_updates_preserve_parent_verdict(workspace):
    client, app, call, raw = workspace
    pid = create(call)
    call('save_materials', project_id=pid, target_url='https://example.test/pay')
    dep = {'key': 'ledger', 'title': '权益账本查询', 'kind': 'observation', 'environment': 'test'}
    saved = call('ui_cases', project_id=pid, cases=[case(ai_analysis='执行者原解读', checkpoints=[point(), point('ledger', kind='observation', dependencies=[dep])]),
        case('GUEST', checkpoints=[point('reject-login', expected='未登录不能创建订单')])])
    gid = saved['dependency_groups'][0]['id']
    saved = call('ui_dependency_check', project_id=pid, execution_id=saved['execution_id'], revision=saved['revision'],
                 dependency_id=gid, status='blocked', observed='当前未接入账本查询', method='只读核对能力配置')
    assert {p['checkpoint_id'] for p in saved['execution_plan']['runnable_checkpoints']} == {'view', 'reject-login'}
    saved = result(call, pid, saved)
    read = call('ui_read', project_id=pid)
    assert read['cases'][0]['status'] == 'not_run' and read['cases'][0]['checkpoints'][1]['status'] == 'not_run'
    assert read['cases'][0]['checkpoints'][0]['status'] == 'passed'
    assert read['cases'][0]['checkpoints'][1]['gaps'][0]['status'] == 'blocked'
    assert read['cases'][0]['ai_analysis'] == '执行者原解读'
    saved = call('ui_dependency_check', project_id=pid, execution_id=saved['execution_id'], revision=saved['revision'],
                 dependency_id=gid, status='ready', observed='查询已接通，角色与订单范围已核对', method='查询当前合成订单')
    assert call('ui_read', project_id=pid)['cases'][0]['status'] == 'not_run'
    saved = result(call, pid, saved, 'ledger', actual='同一订单权益增加一次')
    read = call('ui_read', project_id=pid)['cases'][0]
    assert read['status'] == 'not_run' and read['ai_analysis'] == '执行者原解读'
    assert [p['status'] for p in read['checkpoints']] == ['passed', 'passed']


def test_rule_resolution_preserves_observations_and_explicit_continuation_keeps_history(workspace):
    client, app, call, raw = workspace
    pid = create(call, target_url='https://example.test/pay')
    call('save_requirement_design', project_id=pid, revision=0, requirements=[{'id': 'R1', 'title': '到账', 'kind': 'rule', 'source_quote': '只有收款确认且权益到账才完成。'}],
         questions=[{'id': 'Q1', 'title': '未到账状态是什么', 'requirement_ids': ['R1']}])
    saved = call('ui_cases', project_id=pid, cases=[case(requirement_ids=['R1'], checkpoints=[point(), point('state', question_ids=['Q1'])]), case('INDEPENDENT')])
    saved = result(call, pid, saved)
    saved = result(call, pid, saved, cid='INDEPENDENT')
    report = call('ui_publish', project_id=pid, execution_id=saved['execution_id'], title='阶段报告', summary='规则待确认')['report']
    old = client.get(report['report_url'].replace('index.html', 'report.json')).content
    before_resolution = call('ui_read', project_id=pid)['cases']
    resolved = call('resolve_rule_question', project_id=pid, question_id='Q1', revision=1, resolution='收款确认但权益未到账保持确认中', basis='合成产品确认')
    assert resolved['affected_case_ids'] == ['PAY']
    assert call('ui_read', project_id=pid)['cases'] == before_resolution
    resumed = call('resume_requirement_test', project_id=pid, execution_id=saved['execution_id'], revision=saved['revision'],
        question_id='Q1', reason='规则已明确')
    read = call('ui_read', project_id=pid)
    assert read['id'] == saved['execution_id'] and [c['case_id'] for c in read['cases']] == ['PAY', 'INDEPENDENT']
    assert read['cases'][1]['status'] == 'not_run'
    assert read['cases'][1]['checkpoints'][0]['status'] == 'passed'
    assert read['cases'][0]['checkpoints'][0]['status'] == 'passed'
    assert read['cases'][0]['checkpoints'][1]['status'] == 'not_run'
    assert '修订' in read['cases'][0]['checkpoints'][1]['gaps'][0]['reason']
    assert client.get(report['report_url'].replace('index.html', 'report.json')).content != old
    archived = list((app.state.store.project_dir(app.state.store.find_project_owner(pid), pid) / 'analyses' / report['id'] / 'revisions').glob('*.json'))
    assert archived
    updated = read['cases'][0]
    updated['checkpoints'][1].update(expected='收款确认但权益未到账保持确认中', basis='合成产品确认')
    saved = call('ui_cases', project_id=pid, execution_id=resumed['execution_id'], revision=resumed['revision'], cases=[updated])
    saved = result(call, pid, saved, 'state', actual='页面显示确认中')
    read = call('ui_read', project_id=pid)['cases'][0]
    assert read['status'] == 'not_run'
    assert [p['status'] for p in read['checkpoints']] == ['passed', 'passed']


def test_manual_scan_continuation_preserves_order_and_cannot_replace_target(workspace):
    client, app, call, raw = workspace
    pid = create(call, target_url='https://example.test/pay')
    saved = call('ui_cases', project_id=pid, cases=[case(checkpoints=[point('start'), point('scan', kind='manual', depends_on=['start']),
        point('settle', kind='observation', depends_on=['scan'])])])
    saved = result(call, pid, saved, 'start', correlation={'order_id': 'order-original', 'payer_id': 'user-1'})
    saved = result(call, pid, saved, 'scan', status='pending_action', actual='', action_required='使用测试设备完成原订单扫码', correlation={'order_id': 'order-original'})
    read = call('ui_read', project_id=pid)
    assert read['cases'][0]['status'] == 'not_run'
    assert read['cases'][0]['checkpoints'][1]['status'] == 'pending_action'
    report = call('ui_publish', project_id=pid, execution_id=saved['execution_id'], title='等待扫码', summary='原订单等待人工扫码')['report']
    resumed = call('resume_requirement_test', project_id=pid, execution_id=saved['execution_id'], revision=saved['revision'],
                   case_ids=['PAY'], reason='继续原订单核对')
    points = call('ui_read', project_id=pid)['cases'][0]['checkpoints']
    assert points[0]['inherited_from']['execution_id'] == saved['execution_id']
    assert points[1]['correlation']['order_id'] == 'order-original'
    changed = call('ui_read', project_id=pid)['cases'][0]
    changed['checkpoints'][1]['correlation'] = {'order_id':'different-order'}
    assert raw('ui_cases', project_id=pid, execution_id=resumed['execution_id'], revision=resumed['revision'], cases=[changed]).status_code == 400
    saved = result(call, pid, resumed, 'scan', actual='用户在测试设备完成扫码', action_required='', correlation={'order_id': 'order-original'})
    finished_manual = call('ui_read', project_id=pid)['cases'][0]
    assert finished_manual['status'] == 'not_run'
    assert finished_manual['checkpoints'][1]['status'] == 'passed'
    assert finished_manual['checkpoints'][1]['action_required'] == ''
    call('save_materials', project_id=pid, target_url='https://other.example.test/pay')
    current = call('ui_read', project_id=pid)
    assert all(p['status'] != 'passed' for p in current['cases'][0]['checkpoints'])
    assert all(not p['correlation'] for p in current['cases'][0]['checkpoints'])


@pytest.fixture
def payment_target():
    state = {'credits': 0, 'collected': False, 'fault': False, 'requests': [], 'orders': {}, 'lock': threading.Lock()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            if self.path.startswith('/orders/'):
                value = {'order_id': self.path.split('/')[-1], 'payer_id': 'user-1', 'amount': 1000,
                         'credits': state['credits'], 'state': 'completed' if state['credits'] else 'pending'}
            else:
                value = {}
            data = json.dumps(value).encode(); self.send_response(200); self.end_headers(); self.wfile.write(data)
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers.get('content-length', 0))) or b'{}')
            with state['lock']:
                state['requests'].append((self.path, payload))
                if self.path == '/init':
                    state['orders'].setdefault(payload['key'], 'unique-order')
                    value = {'order_id': state['orders'][payload['key']]}
                else:
                    event = payload.get('event')
                    if event == 'enable_entitlement_fault': state['fault'] = True
                    elif event == 'disable_entitlement_fault': state['fault'] = False
                    elif event == 'success':
                        state['collected'] = True
                        if not state['fault']: state['credits'] = 1
                    value = {'ack': True, 'authorization_echo': self.headers.get('Authorization')}
            data = json.dumps(value).encode(); self.send_response(200); self.end_headers(); self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', state
    finally:
        server.shutdown(); server.server_close(); thread.join()


def capability(key='observe', kind='observation', **extra):
    return {'key': key, 'title': '合成订单查询', 'kind': kind, 'method': 'GET', 'path': '/orders/{order_id}',
            'environment': 'test', 'verification_mode': 'mock', 'source_quote': 'GET /orders/{order_id} 返回 order_id、payer_id、amount、credits、state。',
            'parameters_schema': {'type': 'object', 'properties': {'order_id': {'type': 'string'}}, 'required': ['order_id'], 'additionalProperties': False}, **extra}


def compare(pointer='/credits', expected=1, **extra):
    return {'kind': 'equal', 'pointer': pointer, 'expected': expected, 'source_quote': '重复成功通知只增加一次权益。', **extra}


@pytest.fixture
def local_workspace(tmp_path, payment_target):
    url, state = payment_target
    app = web.create_app(tmp_path, start_fixture=False, testing=True, extra_test_origins=(url,))
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        token = client.post('/api/mcp/redeem', json={'code': client.post('/api/mcp/pair').json()['code']}).json()['token']
        def call(action, **args):
            r = client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token}, json={'action': action, 'arguments': args})
            assert r.status_code == 200, r.text
            return r.json()
        call.client = client
        pid = create(call, target_url=url+'/pay')
        yield client, call, pid, state


def payment_control():
    return capability('control', 'payment_control', title='模拟通知', method='POST', path='/payment-control',
        source_quote='POST /payment-control 接受 order_id、scenario、event、provider_transaction_id，模拟通道控制，响应 ack=true。',
        parameters_schema={'type': 'object', 'properties': {k: {'type': 'string'} for k in ('order_id', 'event', 'scenario', 'provider_transaction_id')},
                           'required': ['order_id', 'event', 'scenario', 'provider_transaction_id'], 'additionalProperties': False},
        body_template={k: '${'+k+'}' for k in ('order_id', 'event', 'scenario', 'provider_transaction_id')})


@pytest.mark.parametrize(('scenario','events','credits'),[
    ('cancel',['cancel'],0), ('unknown',['unknown'],0), ('delayed_success',['pending'],0),
    ('out_of_order',['pending','success','pending'],1),
    ('entitlement_failure',['enable_entitlement_fault','success','disable_entitlement_fault'],0),
])
def test_payment_fault_schedule_and_cleanup_are_actual_adapter_requests(local_workspace, scenario, events, credits):
    client, call, pid, target = local_workspace
    call('save_test_capabilities', project_id=pid, revision=0, items=[payment_control()])
    saved = call('ui_cases', project_id=pid, cases=[case(checkpoints=[point('control', kind='payment', capability_key='control')])])
    ran = call('run_test_capability', project_id=pid, execution_id=saved['execution_id'], revision=saved['revision'], case_id='PAY',
        checkpoint_id='control', capability_key='control', parameters={'order_id':'original','provider_transaction_id':'stable-tx'},
        invocation_id='fault', experiment='payment_scenario', scenario=scenario)
    assert [p['event'] for _,p in target['requests']] == events
    assert all(p['order_id']=='original' and p['provider_transaction_id']=='stable-tx' for _,p in target['requests'])
    assert target['credits'] == credits and target['fault'] is False
    assert ran['result'] == 'partial'  # Injection alone proves no business assertion.
    if scenario == 'delayed_success':
        current = call('ui_read', project_id=pid)
        call('run_test_capability', project_id=pid, execution_id=saved['execution_id'], revision=current['revision'], case_id='PAY',
            checkpoint_id='control', capability_key='control', parameters={'order_id':'original','provider_transaction_id':'stable-tx'},
            invocation_id='release', experiment='payment_scenario', scenario='release_success')
        assert target['credits'] == 1 and target['requests'][-1][1]['order_id']=='original'


def test_controlled_same_key_race_and_stale_target_binding(local_workspace):
    client, call, pid, target = local_workspace
    create_cap = capability('race', 'http', method='POST', path='/init', verification_mode='sandbox',
        source_quote='POST /init 接受 key，并发创建测试订单，返回 order_id。',
        parameters_schema={'type':'object','properties':{'key':{'type':'string'}},'required':['key'],'additionalProperties':False},
        body_template={'key':'${key}'})
    call('save_test_capabilities', project_id=pid, revision=0, items=[create_cap])
    saved = call('ui_cases', project_id=pid, cases=[case(checkpoints=[point('race', kind='concurrency', capability_key='race',
        assertions=[compare('/order_id','unique-order',source_quote='相同业务键并发发起只创建一单。')])])])
    args=dict(project_id=pid,execution_id=saved['execution_id'],revision=saved['revision'],case_id='PAY',checkpoint_id='race',
        capability_key='race',parameters={'key':'same-order-key'},invocation_id='race',experiment='concurrent',workers=8)
    ran=call('run_test_capability',**args)
    assert len(target['requests']) == 8 and len(target['orders']) == 1
    assert ran['launch_skew_ms'] is not None and ran['verification_mode']=='sandbox'
    assert call('run_test_capability',**args)['reused'] is True and len(target['requests'])==8
    # Changing target invalidates old results AND the adapter binding.
    call('save_materials',project_id=pid,target_url='https://new.example.test/pay')
    read=call('ui_read',project_id=pid)
    assert read['cases'][0]['status']=='not_run'
    token=client.post('/api/mcp/redeem',json={'code':client.post('/api/mcp/pair').json()['code']}).json()['token']
    args.update(invocation_id='new',revision=read['revision'])
    rejected=client.post('/api/mcp/call',headers={'Authorization':'Bearer '+token},json={'action':'run_test_capability','arguments':args})
    assert rejected.status_code==400 and len(target['requests'])==8


def test_ledger_delta_and_mismatch_cannot_hide_behind_missing_evidence():
    from api_test_tool.test_capabilities import assertions
    baseline={'id':'before','evidence':[{'data':{'credits':4}}]}
    assertion=compare(kind='delta',baseline_checkpoint_id='before')
    p={'assertions':[assertion]}
    assert assertions(p,{'http_status':200,'data':{'credits':5}},{'checkpoints':[baseline]})[0]=='passed'
    assert assertions(p,{'http_status':200,'data':{'credits':6}},{'checkpoints':[baseline]})[0]=='failed'
    p['assertions'].append(compare('/missing',1))
    assert assertions(p,{'http_status':200,'data':{'credits':6}},{'checkpoints':[baseline]})[0]=='failed'


def test_local_mock_duplicate_callback_and_independent_ledger_evidence(tmp_path, monkeypatch, payment_target):
    url, target = payment_target
    app = web.create_app(tmp_path, start_fixture=False, testing=True, extra_test_origins=(url,))
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        token = client.post('/api/mcp/redeem', json={'code': client.post('/api/mcp/pair').json()['code']}).json()['token']
        def call(action, **args):
            r = client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token}, json={'action': action, 'arguments': args})
            assert r.status_code == 200, r.text
            return r.json()
        call.client = client
        pid = create(call, target_url=url+'/pay')
        control = capability('control', 'payment_control', title='模拟通知', method='POST', path='/payment-control',
            source_quote='POST /payment-control 接受 order_id、scenario、event、provider_transaction_id，模拟通道控制，响应 ack=true。',
            parameters_schema={'type': 'object', 'properties': {k: {'type': 'string'} for k in ('order_id', 'event', 'scenario', 'provider_transaction_id')},
                               'required': ['order_id', 'event', 'scenario', 'provider_transaction_id'], 'additionalProperties': False},
            body_template={k: '${'+k+'}' for k in ('order_id', 'event', 'scenario', 'provider_transaction_id')},
            headers={'Authorization': 'Bearer synthetic-test-secret'})
        caps = call('save_test_capabilities', project_id=pid, revision=0, items=[control, capability()])
        assert 'synthetic-test-secret' not in json.dumps(caps)
        saved = call('ui_cases', project_id=pid, cases=[case(checkpoints=[point('notify', kind='payment', capability_key='control',
            assertions=[compare('/ack', True, source_quote='响应 ack=true。')]), point('ledger', kind='observation', capability_key='observe', depends_on=['notify'],
            assertions=[compare(), compare('/order_id', 'order-1'), compare('/payer_id', 'user-1'), compare('/amount', 1000)])])])
        args = dict(project_id=pid, execution_id=saved['execution_id'], revision=saved['revision'], case_id='PAY',
                    checkpoint_id='notify', capability_key='control', parameters={'order_id': 'order-1', 'provider_transaction_id': 'mock-tx'},
                    invocation_id='notify-1', experiment='payment_scenario', scenario='duplicate_callback')
        ran = call('run_test_capability', **args)
        assert ran['result'] == 'passed' and len(target['requests']) == 2
        assert 'synthetic-test-secret' not in json.dumps(ran)
        read = call('ui_read', project_id=pid)['cases'][0]
        assert read['status'] == 'not_run' and read['checkpoints'][0]['status'] == 'passed'
        assert call('run_test_capability', **args)['reused'] is True and len(target['requests']) == 2
        observed = call('run_test_capability', project_id=pid, execution_id=saved['execution_id'], revision=ran['saved_result']['revision'], case_id='PAY',
                        checkpoint_id='ledger', capability_key='observe', parameters={'order_id': 'order-1'}, invocation_id='observe-1')
        assert observed['result'] == 'passed'
        report = call('ui_publish', project_id=pid, execution_id=saved['execution_id'], title='模拟链路', summary='仅本地模拟')['report']
        assert '模拟支付' in client.get(report['report_url']).text
        assert target['credits'] == 1


def test_unknown_response_missing_business_assertions_and_redirects_are_not_passes():
    from api_test_tool.test_capabilities import assertions
    point = {'assertions': [compare()]}
    status, values = assertions(point, {'http_status': 200, 'data': {}}, {'checkpoints': []})
    assert status == 'partial' and values[0]['missing_evidence']
    assert assertions({'assertions': []}, {'http_status': 200, 'data': {'ok': True}}, {'checkpoints': []})[0] == 'partial'
    assert assertions(point, {'http_status': None, 'data': None}, {'checkpoints': []})[0] == 'partial'
    assert assertions(point, {'http_status': 500, 'data': {'credits':1}}, {'checkpoints': []})[0] == 'partial'
    negative = {'assertions':[{'kind':'http_status', 'expected':403}]}
    assert assertions(negative, {'http_status':403, 'data':{}}, {'checkpoints':[]})[0] == 'passed'


def test_quotes_are_executor_owned_while_paths_schema_revision_and_ownership_stay_protected(workspace):
    client, app, call, raw = workspace
    pid = create(call, target_url='https://example.test/pay')
    bad = capability(path='//evil.test/secret')
    assert raw('save_test_capabilities', project_id=pid, revision=0, items=[bad]).status_code == 400
    bad = capability(source_quote='杜撰 GET /orders/{order_id}')
    quoted = raw('save_test_capabilities', project_id=pid, revision=0, items=[bad])
    assert quoted.status_code == 200, quoted.text
    assert quoted.json()['items'][0]['source_quote'] == bad['source_quote']
    capability_revision = quoted.json()['revision']
    bad = capability(parameters_schema={'type':'object', 'properties':{'order_id':{'type':'invalid'}}, 'additionalProperties':False})
    assert raw('save_test_capabilities', project_id=pid, revision=capability_revision, items=[bad]).status_code == 400
    bad = capability(query_template={'token':'synthetic-secret'})
    assert raw('save_test_capabilities', project_id=pid, revision=capability_revision, items=[bad]).status_code == 400
    design = call('save_requirement_design', project_id=pid, revision=0,
                  requirements=[{'id': 'R', 'title': '执行者引用', 'source_quote': '不存在原文'}])
    assert design['requirements'][0]['source_quote'] == '不存在原文'
    saved = call('ui_cases', project_id=pid, cases=[case()])
    assert raw('record_checkpoint', project_id=pid, execution_id=saved['execution_id'], revision=0, case_id='PAY', checkpoint_id='view',
               result={'status': 'passed', 'actual': '旧版本', 'verification_mode': 'real'}).status_code == 400
    with TestClient(app) as other:
        assert other.get(f'/api/ui-tests/{pid}/requirements').status_code in {403,404}
        assert other.get(f'/api/ui-tests/{pid}/capabilities').status_code in {403,404}


def test_dag_is_validated_but_unchecked_dependencies_do_not_reject_saved_observations(workspace):
    client, app, call, raw = workspace
    pid = create(call, target_url='https://example.test/pay')
    bad = case(checkpoints=[point(depends_on=['future'])])
    assert raw('ui_cases', project_id=pid, cases=[bad]).status_code == 400
    dep = {'key': 'ledger', 'title': '账本查询', 'kind': 'observation', 'environment': 'test'}
    observed = case(checkpoints=[point(status='passed', actual='执行者已有观察', verification_mode='real', dependencies=[dep])])
    saved = raw('ui_cases', project_id=pid, cases=[observed])
    assert saved.status_code == 200, saved.text
    read = call('ui_read', project_id=pid)['cases'][0]['checkpoints'][0]
    assert read['status'] == 'passed' and read['actual'] == '执行者已有观察'
    assert read['gaps'][0]['status'] == 'unchecked'


def test_adapter_wait_does_not_block_independent_case_or_overwrite_publication(workspace, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from api_test_tool import test_capabilities
    client, app, call, raw = workspace
    # This test exercises the legacy in-process adapter, not a live native executor.
    pid = create(call, target_url='https://example.test/pay', execution_route='local_browser')
    call('save_test_capabilities', project_id=pid, revision=0, items=[capability()])
    saved = call('ui_cases', project_id=pid, cases=[
        case(checkpoints=[point(kind='observation', capability_key='observe', assertions=[compare()])]),
        case('INDEPENDENT')])
    entered, release = threading.Event(), threading.Event()

    def slow_observation(*args):
        entered.set()
        assert release.wait(5)
        return {'http_status':200, 'data':{'credits':1}, 'verification_mode':'mock'}

    monkeypatch.setattr(test_capabilities, 'request', slow_observation)
    args = dict(project_id=pid, execution_id=saved['execution_id'], revision=saved['revision'],
                case_id='PAY', checkpoint_id='view', capability_key='observe',
                parameters={'order_id':'original-order'}, invocation_id='slow-1')
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(call, 'run_test_capability', **args)
        assert entered.wait(2)
        try:
            reused = pool.submit(call, 'run_test_capability', **args).result(timeout=2)
            assert reused['status'] == 'running' and reused['reused']
            refused = pool.submit(raw, 'run_test_capability', **{**args, 'invocation_id':'new-id'}).result(timeout=2)
            assert refused.status_code == 400
            unrelated = pool.submit(result, call, pid, saved, cid='INDEPENDENT').result(timeout=2)
            published = pool.submit(call, 'finish_workflow', project_id=pid, summary='独立项目已完成，业务观察尚未返回').result(timeout=2)
            before = client.get(published['report']['report_url']).text
        finally:
            release.set()
        finished = running.result(timeout=2)
    assert 'save_gap' in finished
    assert client.get(published['report']['report_url']).text == before
    assert call('workflow_status', project_id=pid)['progress']['phase'] == 'completed'
    cases = call('ui_read', project_id=pid)['cases']
    assert cases[1]['status'] == 'not_run' and cases[0]['status'] == 'not_run'
    assert cases[1]['checkpoints'][0]['status'] == 'passed'
    # Parameter errors must not echo values into responses or execution records.
    with pytest.raises(ValueError) as failure:
        test_capabilities.validate_parameters({'order_id':{'password':'synthetic-private'}}, capability()['parameters_schema'])
    assert 'synthetic-private' not in str(failure.value)
