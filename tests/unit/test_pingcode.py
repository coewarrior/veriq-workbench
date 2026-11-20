import base64
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import requests
from fastapi.testclient import TestClient

from api_test_tool.pingcode import PingCodeError
from api_test_tool.pingcode import DescriptionContent, description_html, with_report_reference
from api_test_tool.web import create_app


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('PINGCODE_ALLOWED_ORIGINS', 'https://pingcode.example')
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        store = app.state.store
        owner = store.session(client.cookies['api_test_session'])[0]['id']
        project = store.create_project(owner, '文档检查', 'api.md', '# 接口文档')
        rid = str(uuid4())
        report = dict(title='检查报告', document={'filename':'api.md'}, created_at='2026-09-10',
                      findings=[dict(title='响应码定义矛盾', detail='两处定义不一致', evidence='正文第2段', recommendation='统一约定')])
        root = store.project_dir(owner, project['id']) / 'analyses' / rid
        store._mkdir(root)
        store._write(root / 'report.json', report)
        store._write_text(root / 'index.html', '<html><body><textarea id="finding-0"></textarea></body></html>')
        store.update_project(owner, project['id'], {'analysis_reports':[{'id':rid}]})
        service = app.state.pingcode
        calls = []
        saved_description = ''
        def remote(cfg, method, path, **kw):
            nonlocal saved_description
            calls.append((method, path, kw))
            if method == 'GET' and path.endswith('/workitems/remote1'):
                return {'id': 'remote1', 'description': saved_description}
            if method == 'POST':
                saved_description = kw.get('body', {}).get('description', '')
                return {'id':'remote1','identifier':'BUG-42','html_url':'https://team.pingcode.com/pjm/workitems/remote1'}
            if path.endswith('/projects'):
                return {'values':[{'id':'p1','name':'接口项目'}], 'total':1}
            if path.endswith('/types'):
                return {'values':[{'id':'bug','name':'缺陷','group':'bug'}]}
            if path.endswith('/priorities'):
                return {'values':[{'id':'high','name':'高'}]}
            if path.endswith('/members'):
                return {'values':[{'type':'user','user':{'id':'u1','display_name':'测试人员'}}]}
            if path.endswith('/properties'):
                return {'values':[{'id':'severity','name':'严重程度','type':'select','is_required':True,
                                   'options':[{'_id':'normal','text':'一般'}]}]}
            raise AssertionError(path)
        monkeypatch.setattr(service,'request',remote)
        assert client.put('/api/integrations/pingcode',json={'base_url':'https://pingcode.example','auth_mode':'token','access_token':'top-secret-token'}).status_code == 200
        route=f'/api/projects/{project["id"]}/reports/{rid}/pingcode/finding-0'
        payload={'project_id':'p1','type_id':'bug','title':'审核后的标题','description':'审核后的证据','properties':{'severity':'normal'}}
        yield client, service, store, owner, route, payload, calls


def test_reviewed_publish_and_duplicate_protection(setup):
    client, service, store, owner, route, payload, calls=setup
    assert client.post(route,json={'payload':payload}).status_code == 400
    assert not any(c[0]=='POST' for c in calls)
    draft=client.get(route).json()
    assert '响应码定义矛盾' in draft['title']
    first=client.post(route,json={'reviewed':True,'payload':payload})
    assert first.status_code == 200, first.text
    assert first.json()['status']=='submitted'
    assert first.json()['description_verified'] is True
    assert first.json()['item']['identifier']=='BUG-42'
    reference = draft['report_reference']
    assert first.json()['payload']['description'] == with_report_reference(payload['description'], reference)
    assert reference['url'] == 'http://testserver' + route.rsplit('/pingcode/', 1)[0] + '/index.html'
    created = next(c[2]['body'] for c in calls if c[0] == 'POST')
    assert DescriptionContent(created['description']).links == [reference['url']]
    payload['title']='不要重复创建'
    assert client.post(route,json={'reviewed':True,'payload':payload}).json()['item']['id']=='remote1'
    assert len([c for c in calls if c[0]=='POST'])==1
    assert client.get(route).json()['record']['status']=='submitted'
    assert 'top-secret-token' not in first.text
    # A fresh service/app can recover the persisted record after restart.
    from api_test_tool.pingcode import PingCode
    _,_,path=PingCode(store).source(owner,first.json()['source']['project_id'],first.json()['source']['run_id'],'finding-0')
    assert store._read(path)['item']['id']=='remote1'


def test_defect_lifecycle_requires_reason_and_persists_without_pingcode_submission(setup):
    client, service, store, owner, route, payload, calls = setup
    assert client.patch(route + '/lifecycle', json={'status': 'rejected', 'reason': ''}).status_code == 400
    rejected = client.patch(route + '/lifecycle', json={
        'status': 'rejected', 'reason': '产品确认这是预期行为，回归时按新规则复核。'
    })
    assert rejected.status_code == 200, rejected.text
    record = rejected.json()
    assert record['status'] == 'draft'
    assert record['triage_status'] == 'rejected'
    assert record['triage_reason'].startswith('产品确认')
    assert not any(call[0] == 'POST' for call in calls)
    assert client.post(route, json={'reviewed': True, 'payload': payload}).status_code == 400
    listed = client.get(route.rsplit('/', 1)[0]).json()['values'][0]
    assert listed['triage_status'] == 'rejected'
    assert listed['triage_reason'] == record['triage_reason']
    reopened = client.patch(route + '/lifecycle', json={'status': 'pending_submission', 'reason': ''}).json()
    assert reopened['triage_status'] == 'pending_submission'
    submitted = client.post(route, json={'reviewed': True, 'payload': payload}).json()
    assert submitted['triage_status'] == 'submitted'
    assert submitted['history'][0]['action'] == 'triage_status'


@pytest.mark.parametrize('status', ['deferred', 'rejected'])
def test_defect_lifecycle_reason_is_required_for_human_decisions(setup, status):
    client, _, _, _, route, _, _ = setup
    assert client.patch(route + '/lifecycle', json={'status': status, 'reason': '  '}).status_code == 400


def test_submitted_lifecycle_cannot_be_faked(setup):
    client, _, _, _, route, _, _ = setup
    response = client.patch(route + '/lifecycle', json={'status': 'submitted', 'reason': ''})
    assert response.status_code == 400


def test_description_html_preserves_literal_multiline_and_escapes_image_attributes():
    text = '【步骤】\r\n输入 <script>alert("x")</script> & 1 < 2\r\n\r\n![原文](url)'
    rendered = description_html(text, [{'url': 'https://files.example/x?a=1&b="x"', 'title': '截图"<1>'}])
    assert '<script>' not in rendered
    assert '&lt;script&gt;' in rendered
    assert '<p><br></p>' in rendered
    parsed = DescriptionContent(rendered)
    assert ''.join(parsed.text) == text.replace('\r\n', '') + '【截图证据】'
    assert parsed.images == ['https://files.example/x?a=1&b="x"']


def test_only_server_supplied_report_url_is_rendered_as_safe_link():
    url = 'https://workspace.example/report?a=1&b="quoted"'
    text = '人工输入 <script>\n' + url + '\nhttps://unrelated.example'
    rendered = description_html(text, report_url=url)
    assert '<script>' not in rendered
    assert DescriptionContent(rendered).links == [url]
    assert 'rel="noopener noreferrer"' in rendered
    assert 'href="https://workspace.example/report?a=1&amp;b=&quot;quoted&quot;"' in rendered
    assert DescriptionContent(description_html('javascript:alert(1)', report_url='javascript:alert(1)')).links == []
    assert DescriptionContent(description_html('https://user:secret@example.test',
                                               report_url='https://user:secret@example.test')).links == []


@pytest.mark.parametrize('scheme', ['http', 'https'])
@pytest.mark.parametrize('kind', ['finding', 'defect'])
def test_report_link_uses_source_round_and_case_and_survives_manual_edits(setup, kind, scheme):
    client, service, store, owner, route, payload, calls = setup
    client.base_url = scheme + '://testserver'
    pid = route.split('/')[3]
    rid = str(uuid4())
    if kind == 'finding':
        root = store.project_dir(owner, pid) / 'analyses' / rid
        store._mkdir(root)
        report = dict(title='原轮报告', document={'filename': 'api.md'}, created_at='2026-10-08',
                      findings=[dict(title='处理文件失败', case_id='UPLOAD-06', detail='提交解析任务失败')])
        store._write(root / 'report.json', report)
        project = store.get_project(owner, pid)
        store.update_project(owner, pid, {'analysis_reports': [*project['analysis_reports'], {'id': rid}]})
        case_id = 'UPLOAD-06'
    else:
        root = store.project_dir(owner, pid) / 'runs' / rid
        store._mkdir(root)
        store._write(root / 'result.json', {'cases': [{'id': 'API-06', 'title': '处理文件失败', 'status': 'FAIL'}]})
        store._write(root / 'bundle.json', {'cases': []})
        store.update_project(owner, pid, {'runs': [{'id': rid}]})
        case_id = 'API-06'
    # The submitted round is not the project's latest analysis report.
    target = f'/api/projects/{pid}/reports/{rid}/pingcode/{kind}-0'
    draft = client.get(target).json()
    reference = draft['report_reference']
    assert reference['url'] == f'{scheme}://testserver/api/projects/{pid}/reports/{rid}/index.html'
    assert reference['case_id'] == case_id
    assert reference['text'] in draft['description']
    assert '用例编号：' + case_id in reference['text']
    edited = {**payload, 'description': '人工修改的步骤和观察结果。'}
    submitted = client.post(target, json={'reviewed': True, 'payload': edited}).json()
    assert submitted['status'] == 'submitted'
    assert submitted['description_verified'] is True
    assert submitted['payload']['description'] == with_report_reference(edited['description'], reference)
    assert submitted['source']['report_url'] == reference['url']
    assert submitted['source']['case_id'] == case_id
    remote_html = next(c[2]['body']['description'] for c in calls if c[0] == 'POST')
    assert DescriptionContent(remote_html).links == [reference['url']]
    # Already enriched input and a retry both remain single-link, single-create.
    repeated = client.post(target, json={'reviewed': True, 'payload': submitted['payload']}).json()
    assert repeated['payload']['description'].count(reference['url']) == 1
    assert len([c for c in calls if c[0] == 'POST']) == 1


def test_report_reference_does_not_duplicate_or_truncate_reviewed_text(setup):
    client, _, _, _, route, payload, calls = setup
    reference = client.get(route).json()['report_reference']
    enriched = with_report_reference('人工正文', reference)
    assert with_report_reference(enriched, reference) == enriched
    response = client.post(route, json={'reviewed': True, 'payload': {**payload, 'description': '字' * 150000}})
    assert response.status_code == 400
    assert not any(c[0] == 'POST' for c in calls)


@pytest.mark.parametrize('remote_description', ['', ')', '<p>审核后的</p>', None])
def test_description_loss_is_visible_and_never_recreates_item(setup, monkeypatch, remote_description):
    client, service, store, owner, route, payload, calls = setup
    original = service.request
    def remote(cfg, method, path, **kwargs):
        if method == 'GET' and path.endswith('/workitems/remote1'):
            return {'description': remote_description}
        return original(cfg, method, path, **kwargs)
    monkeypatch.setattr(service, 'request', remote)
    record = client.post(route, json={'reviewed': True, 'payload': payload}).json()
    assert record['status'] == 'submitted'
    assert record['description_verified'] is False
    assert '请勿重复提交' in record['description_error']
    assert client.get(route.rsplit('/', 1)[0]).json()['values'][0]['description_error']
    client.post(route, json={'reviewed': True, 'payload': payload})
    assert len([c for c in calls if c[0] == 'POST']) == 1


def test_verification_accepts_editor_markup_but_rejects_missing_images(setup):
    _, service, _, _, _, _, _ = setup
    expected = description_html('中文\n<输入> & 结果', [{'url': 'https://files.example/x', 'title': '图'}])
    service.request = lambda *args, **kwargs: {'description': '<div>中文<br>&lt;输入&gt; &amp; 结果</div><p>【截图证据】</p><img src="https://files.example/x">'}
    service.verify_description({'api_version': 'pjm'}, '', 'remote1', expected)
    service.request = lambda *args, **kwargs: {'description': '<p>中文&lt;输入&gt; &amp; 结果【截图证据】</p>'}
    with pytest.raises(PingCodeError, match='不一致'):
        service.verify_description({'api_version': 'pjm'}, '', 'remote1', expected)


def test_verification_detects_a_report_url_saved_without_a_clickable_link(setup):
    _, service, _, _, _, _, _ = setup
    url = 'https://workspace.example/report'
    expected = description_html(url, report_url=url)
    service.request = lambda *args, **kwargs: {'description': '<p>' + url + '</p>'}
    with pytest.raises(PingCodeError, match='不一致'):
        service.verify_description({'api_version': 'pjm'}, '', 'remote1', expected)
    service.request = lambda *args, **kwargs: {'description': '<div><a href="' + url + '">' + url + '</a></div>'}
    service.verify_description({'api_version': 'pjm'}, '', 'remote1', expected)


def test_pasted_screenshot_is_uploaded_and_embedded_in_description(setup, monkeypatch):
    client, service, store, owner, route, payload, calls = setup
    original = service.request
    png = b'\x89PNG\r\n\x1a\nclipboard-image'
    saved = {}

    def remote(cfg, method, path, **kwargs):
        if path == '/v1/attachments':
            calls.append((method, path, kwargs))
            assert kwargs['params'] == {'principal_type': 'workitem', 'principal_id': 'remote1'}
            assert kwargs['form'] == {'title': '截图-1.png'}
            assert kwargs['files']['file'] == ('截图-1.png', png, 'image/png')
            return {'id': 'attachment1', 'download_url': 'https://files.pingcode.example/screenshot.png'}
        if method == 'PATCH':
            calls.append((method, path, kwargs))
            saved['description'] = kwargs['body']['description']
            return {'id': 'remote1'}
        if method == 'GET' and path.endswith('/workitems/remote1'):
            return saved
        return original(cfg, method, path, **kwargs)

    monkeypatch.setattr(service, 'request', remote)
    response = client.post(route, json={
        'reviewed': True,
        'payload': payload,
        'screenshots': [{'content_type': 'image/png', 'content_base64': base64.b64encode(png).decode()}],
    })
    assert response.status_code == 200, response.text
    record = response.json()
    assert record['status'] == 'submitted'
    image_url = 'data:image/png;base64,' + base64.b64encode(png).decode('ascii')
    assert record['screenshots'] == [{'id': 'attachment1', 'title': '截图-1.png', 'url': image_url}]
    assert DescriptionContent(saved['description']).images == [image_url]
    assert 'https://files.pingcode.example/' not in saved['description']
    assert '<p>审核后的证据</p>' in saved['description']
    assert DescriptionContent(saved['description']).links == [record['source']['report_url']]
    assert record['description_verified'] is True
    assert record['payload']['description'].startswith('审核后的证据')
    assert [call[0:2] for call in calls if call[0] in {'POST', 'PATCH'}] == [
        ('POST', '/v1/pjm/workitems'), ('POST', '/v1/attachments'), ('PATCH', '/v1/pjm/workitems/remote1')]


def test_invalid_or_failed_screenshot_never_duplicates_work_item(setup, monkeypatch):
    client, service, store, owner, route, payload, calls = setup
    invalid = client.post(route, json={'reviewed': True, 'payload': payload,
                                      'screenshots': [{'content_type': 'image/png', 'content_base64': 'bm90LXBuZw=='}]})
    assert invalid.status_code == 400
    assert not any(call[0] == 'POST' for call in calls)

    original = service.request
    png = b'\x89PNG\r\n\x1a\nclipboard-image'

    def remote(cfg, method, path, **kwargs):
        if path == '/v1/attachments':
            calls.append((method, path, kwargs))
            raise PingCodeError('截图上传失败', False)
        return original(cfg, method, path, **kwargs)

    monkeypatch.setattr(service, 'request', remote)
    request = {'reviewed': True, 'payload': payload,
               'screenshots': [{'content_type': 'image/png', 'content_base64': base64.b64encode(png).decode()}]}
    first = client.post(route, json=request).json()
    assert first['status'] == 'submitted'
    assert first['screenshot_error'] == '截图上传失败'
    assert client.post(route, json=request).json()['item']['id'] == 'remote1'
    assert len([call for call in calls if call[0] == 'POST' and call[1].endswith('/workitems')]) == 1


def test_fields_and_owner_validation(setup):
    client, service, store, owner, route, payload, calls=setup
    payload['properties']={}
    assert '严重程度' in client.post(route,json={'reviewed':True,'payload':payload}).json()['detail']
    payload['properties']={'severity':'normal'}
    payload['assignee_id']='outsider'
    assert client.post(route,json={'reviewed':True,'payload':payload}).status_code==400
    assert client.get(route.replace('finding-0','finding-999')).status_code==400
    other=TestClient(client.app)
    other.headers['x-csrf-token']=other.get('/api/bootstrap').json()['csrf']
    assert other.get(route).status_code==404
    assert other.post(route,json={'reviewed':True,'payload':payload}).status_code==404
    assert not other.get('/api/integrations/pingcode').json()['configured']
    assert not any(c[0]=='POST' for c in calls)
    other.close()


def test_config_encryption_secret_retention_and_target_change(setup):
    client, service, store, owner, route, payload, calls=setup
    assert 'top-secret-token' not in client.get('/api/integrations/pingcode').text
    assert 'top-secret-token' not in (store._owner_dir(owner)/'pingcode.json').read_text()
    assert client.put('/api/integrations/pingcode',json={'default_project_id':'p1'}).json()['configured']
    assert client.put('/api/integrations/pingcode',json={'auth_mode':'client_credentials','client_id':'new'}).json()['has_access_token'] is False
    assert client.post(route,json={'reviewed':True,'payload':payload}).status_code==400
    client.headers.pop('x-csrf-token')
    assert client.put('/api/integrations/pingcode',json={}).status_code==403


def test_unknown_not_retried_and_human_resolution(setup,monkeypatch):
    client, service, store, owner, route, payload, calls=setup
    old=service.request
    def failure(cfg,method,path,**kw):
        if method=='POST':
            calls.append((method,path,kw))
            raise PingCodeError('网络中断', True)
        return old(cfg,method,path,**kw)
    monkeypatch.setattr(service,'request',failure)
    data={'reviewed':True,'payload':payload}
    assert client.post(route,json=data).json()['status']=='unknown'
    assert client.post(route,json=data).status_code==409
    assert len([c for c in calls if c[0]=='POST'])==1
    assert client.post(route+'/resolve',json={'confirmed_absent':True}).json()['status']=='failed'
    monkeypatch.setattr(service,'request',old)
    result=client.post(route,json=data).json()
    assert result['status']=='submitted' and result['attempts']==2
    assert result['history'][0]['action']=='human_confirmed_absent'


def test_known_failure_can_retry_and_success_url_safe(setup,monkeypatch):
    client, service, store, owner, route, payload, calls=setup
    old=service.request
    def failure(cfg,method,path,**kw):
        if method=='POST': raise PingCodeError('字段无效',False)
        return old(cfg,method,path,**kw)
    monkeypatch.setattr(service,'request',failure)
    assert client.post(route,json={'reviewed':True,'payload':payload}).json()['status']=='failed'
    monkeypatch.setattr(service,'request',old)
    assert client.post(route,json={'reviewed':True,'payload':payload}).json()['status']=='submitted'
    assert service.item({'id':'1','html_url':'javascript:alert(1)'})['url']==''


def test_concurrent_create_single_request(setup,monkeypatch):
    client, service, store, owner, route, payload, calls=setup
    old=service.request
    started=threading.Event();release=threading.Event()
    def remote(cfg,method,path,**kw):
        if method=='POST':
            started.set(); assert release.wait(5)
        return old(cfg,method,path,**kw)
    monkeypatch.setattr(service,'request',remote)
    with ThreadPoolExecutor(2) as pool:
        first=pool.submit(client.post,route,json={'reviewed':True,'payload':payload})
        assert started.wait(5)
        try: assert client.post(route,json={'reviewed':True,'payload':payload}).status_code==409
        finally: release.set()
        assert first.result().json()['status']=='submitted'
    assert len([c for c in calls if c[0]=='POST'])==1


def test_online_controls_do_not_modify_frozen_report(setup):
    client,service,store,owner,route,payload,calls=setup
    url=route.replace('/pingcode/finding-0','/index.html')
    assert '/static/pingcode.js' in client.get(url).text
    pid=route.split('/')[3];rid=route.split('/')[5]
    assert 'pingcode.js' not in (store.project_dir(owner,pid)/'analyses'/rid/'index.html').read_text()
    assert '集成管理' in client.get('/api-testing').text
    page = client.get('/integrations/pingcode').text
    assert 'Client Secret' in page
    assert 'id="pingcode-back" data-integration-back href="/">← 返回上一页</a>' in page
    assert '/static/integration-back.js' in page


def test_transport_errors_redact_credentials_and_no_retry(tmp_path,monkeypatch):
    from api_test_tool.pingcode import PingCode
    from api_test_tool.web_storage import Store
    import api_test_tool.pingcode as module
    service=PingCode(Store(tmp_path));cfg={'base_url':'https://pingcode.example','access_token':'sensitive'}
    monkeypatch.setattr(module,'check_public_endpoint',lambda *a:None)
    class Response:
        status_code=400
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def iter_content(self,*a):yield b'{"message":"invalid sensitive"}'
    class Session:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def request(self,*a,**kw):return Response()
    monkeypatch.setattr(module,'pinned_session',lambda *a:Session())
    with pytest.raises(PingCodeError) as exc: service.request(cfg,'POST','/v1/pjm/workitems',token='sensitive')
    assert not exc.value.uncertain and 'sensitive' not in str(exc.value)
    Response.status_code=500
    with pytest.raises(PingCodeError) as exc:service.request(cfg,'POST','/v1/pjm/workitems')
    assert exc.value.uncertain


def test_legacy_metadata_paths(setup):
    client,service,store,owner,route,payload,calls=setup
    client.put('/api/integrations/pingcode',json={'api_version':'project'})
    assert client.get('/api/integrations/pingcode/metadata?project_id=p1').status_code==200
    assert any(c[1]=='/v1/project/work_item/properties' and c[2]['params']['work_item_type_id']=='bug' for c in calls)
    assert any(c[1]=='/v1/project/priorities' for c in calls)


def test_record_summary_persists_without_publishing(setup):
    client, service, store, owner, route, payload, calls=setup
    summary=route.rsplit('/',1)[0]
    assert client.get(summary).json()=={'values':[]}
    client.post(route,json={'reviewed':True,'payload':payload})
    r=client.get(summary).json()['values'][0]
    assert r['draft_id']=='finding-0' and r['status']=='submitted'
    assert 'payload' not in r


def test_regression_failure_reopens_original_item_without_creating_another(setup, monkeypatch):
    client, service, store, owner, route, payload, calls = setup
    record = {
        'status': 'submitted', 'triage_status': 'regression_failed',
        'lineage': {'case_id': 'JD-001', 'source_report_id': 'old'},
        'target': {'base_url': service.config(owner, True)['base_url'], 'api_version': 'pjm', 'project_id': 'p1'},
        'payload': {**payload, 'type_id': 'bug'},
        'item': {'id': 'remote1', 'identifier': 'AIPIN-300'},
    }
    monkeypatch.setattr(service, 'collection', lambda cfg, token, path, params=None: [
        {'id': 'done', 'name': '已完成', 'type': 'completed'},
        {'id': 'reopened', 'name': '重新打开', 'type': 'pending'},
    ])
    sent = []
    monkeypatch.setattr(service, 'request', lambda cfg, method, path, **kwargs:
                        sent.append((method, path, kwargs.get('body'))) or {'id': 'remote1'})
    assert service.reopen_item(owner, record) == {'id': 'reopened', 'name': '重新打开'}
    assert sent == [('PATCH', '/v1/pjm/workitems/remote1', {'state_id': 'reopened'})]
    assert not any(method == 'POST' and path.endswith('/workitems') for method, path, _ in sent)


def test_reconcile_requires_source_marker(setup, monkeypatch):
    client, service, store, owner, route, payload, calls=setup
    source=client.get(route).json()
    old=service.request
    def remote(cfg, method, path, **kw):
        if method=='POST': raise PingCodeError('结果未知', True)
        if path.endswith('/remote1'): return {'id':'remote1','description':'其他缺陷'}
        return old(cfg,method,path,**kw)
    monkeypatch.setattr(service,'request',remote)
    pending = client.post(route,json={'reviewed':True,'payload':payload}).json()
    assert client.post(route+'/resolve',json={'item_id':'remote1'}).status_code==400
    monkeypatch.setattr(service,'request',lambda *a,**kw:{'id':'remote1','title':payload['title'],
        'project_id':'p1','description':description_html(pending['payload']['description'],
            report_url=pending['source']['report_url']),'identifier':'BUG-42'})
    assert client.post(route+'/resolve',json={'item_id':'remote1'}).json()['status']=='submitted'


def test_reconcile_legacy_marker(setup, monkeypatch):
    client, service, store, owner, route, payload, calls=setup
    source=client.get(route).json()
    old=service.request
    def remote(cfg, method, path, **kw):
        if method=='POST': raise PingCodeError('结果未知', True)
        return old(cfg,method,path,**kw)
    monkeypatch.setattr(service,'request',remote)
    client.post(route,json={'reviewed':True,'payload':payload})
    monkeypatch.setattr(service,'request',lambda *a,**kw:{'id':'remote1','description':source['marker'],'identifier':'BUG-42'})
    assert client.post(route+'/resolve',json={'item_id':'remote1'}).json()['status']=='submitted'


def test_enterprise_token_and_pagination(setup,monkeypatch):
    client,service,store,owner,route,payload,calls=setup
    cfg={**service.config(owner,True),'auth_mode':'client_credentials','client_id':'app','client_secret':'secret'}
    seen=[]
    def remote(cfg,method,path,**kw):
        seen.append((method,path,kw))
        if path=='/v1/auth/token':return {'access_token':'granted'}
        page=kw['params']['page_index']
        return {'values':[{'id':str(page)}], 'total':2}
    monkeypatch.setattr(service,'request',remote)
    assert service.token(cfg)=='granted'
    assert seen[0][2]['params']['grant_type']=='client_credentials'
    assert len(service.collection(cfg,'granted','/v1/pjm/projects'))==2


def test_draft_auto_assessment_and_invalid_severity(setup):
    client, service, store, owner, route, payload, calls = setup
    assessment = client.get(route).json()['assessment']
    assert assessment['severity'] == 'medium'
    assert assessment['priority'] == 'medium'
    payload['properties']['severity'] = 'not-a-project-option'
    response = client.post(route, json={'reviewed': True, 'payload': payload})
    assert response.status_code == 400
    assert '字段选项' in response.json()['detail']
    assert not any(c[0] == 'POST' for c in calls)


def test_batch_items_keep_independent_dedup_and_failure_state(setup, monkeypatch):
    client, service, store, owner, route, payload, calls = setup
    pid, rid = route.split('/')[3], route.split('/')[5]
    path = store.project_dir(owner, pid) / 'analyses' / rid / 'report.json'
    saved = store._read(path)
    saved['findings'] *= 3
    store._write(path, saved)
    old = service.request
    def partial(cfg, method, path, **kw):
        if method == 'POST' and '第二条' in kw['body']['title']:
            raise PingCodeError('字段拒绝', False)
        return old(cfg, method, path, **kw)
    monkeypatch.setattr(service, 'request', partial)
    for index, title, expected in [(0, '第一条', 'submitted'), (1, '第二条', 'failed'), (2, '第三条', 'submitted')]:
        target = route.replace('finding-0', f'finding-{index}')
        assert client.post(target, json={'reviewed': True, 'payload': {**payload, 'title':title}}).json()['status'] == expected
    assert len([c for c in calls if c[0]=='POST']) == 2
    # Repeating the complete batch cannot create duplicates for successful items.
    for index in [0,2]:
        assert client.post(route.replace('finding-0',f'finding-{index}'), json={'reviewed':True,'payload':payload}).json()['status'] == 'submitted'
    assert len([c for c in calls if c[0]=='POST']) == 2

@pytest.mark.parametrize('action,triage_status', [('accept', 'regression_passed'), ('reopen', 'regression_failed')])
def test_remote_batch_state_is_verified_and_idempotent(setup, monkeypatch, action, triage_status):
    client, service, store, owner, route, payload, calls = setup
    created = client.post(route, json={'reviewed': True, 'payload': payload}).json()
    parts = route.split('/')
    _, _, path = service.source(owner, parts[3], parts[5], parts[7])
    created.update(triage_status=triage_status, lineage={'source_draft_id': 'finding-0'})
    store._write(path, created)
    state = {'id': 'old'}
    writes = []
    target = {'id': 'done', 'name': '已验收' if action == 'accept' else '重新打开'}
    monkeypatch.setattr(service, 'collection', lambda *a, **kw: [target])
    def remote(cfg, method, remote_path, **kw):
        if method == 'PATCH':
            writes.append(kw['body'])
            state['id'] = kw['body']['state_id']
        return {'state_id': state['id']}
    monkeypatch.setattr(service, 'request', remote)
    result = client.post(route + '/' + action, json={'expected_updated_at': created['updated_at']})
    assert result.status_code == 200, result.text
    assert result.json()['triage_status'] == triage_status
    assert result.json()['remote_sync']['status'] == 'success'
    assert client.post(route + '/' + action, json={}).json()['remote_state']['id'] == 'done'
    assert writes == [{'state_id': 'done'}]


def test_unknown_remote_transition_requires_readback_before_replay(setup, monkeypatch):
    client, service, store, owner, route, payload, calls = setup
    created = client.post(route, json={'reviewed': True, 'payload': payload}).json()
    parts = route.split('/')
    _, _, path = service.source(owner, parts[3], parts[5], parts[7])
    created['triage_status'] = 'regression_passed'
    store._write(path, created)
    state = {'id': 'old'}
    writes = []
    monkeypatch.setattr(service, 'collection', lambda *a, **kw: [{'id': 'done', 'name': '已验收'}])
    def remote(cfg, method, remote_path, **kw):
        if method == 'PATCH':
            writes.append(kw['body'])
            state['id'] = 'done'
            raise PingCodeError('响应中断', uncertain=True)
        return {'state_id': state['id']}
    monkeypatch.setattr(service, 'request', remote)
    result = client.post(route + '/accept', json={}).json()
    assert result['remote_sync']['status'] == 'unknown'
    assert result['triage_status'] == 'regression_passed'
    assert client.post(route + '/accept', json={}).status_code == 409
    refreshed = client.post(route + '/refresh-state', json={}).json()
    assert refreshed['remote_sync']['status'] == 'success'
    assert client.post(route + '/accept', json={}).json()['remote_state']['id'] == 'done'
    assert len(writes) == 1
