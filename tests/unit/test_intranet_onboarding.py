"""First-use browser and standalone Codex client acceptance paths."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from api_test_tool import web
from api_test_tool.mcp_access import MCPAccess
from api_test_tool.web_storage import Store
from tests.unit.test_mcp_workflow import running_app

CLIENT = web.STATIC / 'api-test-client.py'
spec = importlib.util.spec_from_file_location('standalone_test_client', CLIENT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_multiple_codex_connections_and_legacy_grant_survive(tmp_path):
    store=Store(tmp_path); owner=store.session(None)[0]['id']; access=MCPAccess(store)
    a=access.redeem(access.issue(owner)['code'])['token']
    b=access.redeem(access.issue(owner)['code'])['token']
    assert access.authenticate(a)==access.authenticate(b)==owner
    access.store._write(access._path(owner), {'token_digest':access._digest(a),'token_expires':time.time()+3600})
    c=access.redeem(access.issue(owner)['code'])['token']
    assert access.authenticate(a)==access.authenticate(c)==owner
    assert access.status(owner)['connected']
    access.revoke(owner)
    for token in (a,b,c):
        with pytest.raises(PermissionError): access.authenticate(token)


def test_fresh_browser_demo_reaches_real_report(tmp_path,monkeypatch):
    monkeypatch.setenv('API_TEST_FIXTURE_PORT','0')
    monkeypatch.setattr(web,'generate_text',lambda *a,**k:pytest.fail('Demo must never call models'))
    app=web.create_app(tmp_path,testing=True)
    with TestClient(app) as browser:
        bootstrap=browser.get('/api/bootstrap').json()
        assert bootstrap['projects']==[] and not bootstrap['model']['has_key']
        assert browser.post('/api/demo').status_code==403
        browser.headers['x-csrf-token']=bootstrap['csrf']
        response=browser.post('/api/demo'); assert response.status_code==200,response.text
        data=response.json(); pid=data['project']['id']; jid=data['job']['id']
        assert data['project']['template']=='items'
        for _ in range(200):
            job=browser.get('/api/jobs/'+jid).json()
            if job['status'] in {'completed','failed'}:break
            time.sleep(.02)
        assert job['status']=='completed',job
        saved=browser.get('/api/projects/'+pid).json()
        report=saved['project']['last_run']
        evidence=browser.get(report['report_url'].replace('index.html','result.json')).json()
        assert report['summary'] == {'PASS':20, 'FAIL':3, 'BROKEN':1, 'BLOCKED':1,
                                     'QUARANTINED':1, 'UNSUPPORTED':1, 'total':27, 'complete':False}, {
            c['id']:c.get('reason') for c in evidence['cases'] if c['status'] in {'FAIL','BROKEN'}}
        cases={c['id']:c for c in evidence['cases']}
        assert cases['DEMO-WRONG_TYPE']['status']=='FAIL'
        assert cases['DEMO-SERVICE-ERROR']['status']=='BROKEN'
        assert cases['DEMO-AFTER-ERROR']['status']=='PASS'
        assert cases['DEMO-AFTER-ERROR']['steps']
        assert all(c['cleanup']['status']=='PASS' for c in cases.values() if c.get('cleanup',{}).get('steps'))
        html=browser.get(report['report_url']).text
        assert '【演示】' in html and 'PingCode' in html
        for index in (19,20,21):
            draft_url=report['report_url'].replace('index.html',f'pingcode/defect-{index}')
            draft=browser.get(draft_url)
            assert draft.status_code==200,draft.text
            assert draft.json()['title'].startswith('【演示】')
            assert '可控故障' in draft.json()['description']
            assert '【复现步骤与请求】' in draft.json()['description']
            assert draft.json()['record'] is None  # Merely preparing the demo never publishes bugs.
        # Faults cannot be sent to a user-selected service.
        assert browser.post(f'/api/projects/{pid}/run',json={'environment':'custom','base_url':'https://example.com'}).status_code==400
        assert report['requests_sent']>0
        assert browser.get(report['report_url']).status_code==200
        cookie=browser.cookies.get('api_test_session')
    with TestClient(web.create_app(tmp_path,start_fixture=False,testing=True)) as restored:
        restored.cookies.set('api_test_session',cookie)
        assert restored.get('/api/projects/'+pid).json()['project']['last_run']['id']==report['id']
    with TestClient(web.create_app(tmp_path,start_fixture=False,testing=True)) as other:
        assert other.get('/api/projects/'+pid).status_code in {403,404}
        shared=other.get(report['report_url'])
        assert shared.status_code==200
        assert 'name="api-test-public-report" content="read-only"' in shared.text
        assert other.get(report['report_url'].replace('index.html','result.json')).status_code in {403,404}


def test_download_client_has_same_tools_and_hash():
    from api_test_tool.mcp_server import create_server,WorkspaceClient
    server=create_server(WorkspaceClient('http://127.0.0.1:18089'))
    manifest=json.loads((web.STATIC/'agent-tools.json').read_text())
    assert manifest['tools']==[t.model_dump(exclude_none=True) for t in asyncio.run(server.list_tools())]
    assert manifest['instructions']==server.instructions
    assert all(category in manifest['instructions'] for category in ('positive', 'negative', 'boundary', 'security'))
    assert 'assess all 22 dimensions' not in manifest['instructions']
    assert manifest['client_sha256']==hashlib.sha256(CLIENT.read_bytes()).hexdigest()
    assert set(manifest['actions'])=={t['name'] for t in manifest['tools']}


def test_no_install_client_document_review_and_mcp_protocol(tmp_path):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    app=web.create_app(tmp_path/'data',start_fixture=False)
    credential=tmp_path/'client-state'/'token.json'
    with running_app(app) as url,httpx.Client(base_url=url,trust_env=False) as browser:
        csrf=browser.get('/api/auth/me').json()['csrf']
        registered=browser.post('/api/auth/register',json={'username':'mcp_test','password':'test-password'},headers={'x-csrf-token':csrf})
        assert registered.status_code==200,registered.text
        browser.headers['x-csrf-token']=browser.get('/api/bootstrap').json()['csrf']
        # Fetch the artifact a new user receives, then run Python with no site packages.
        downloaded=tmp_path/'api-test-client.py';downloaded.write_bytes(browser.get('/static/api-test-client.py').content)
        client=module.Client(url,credential)
        code=browser.post('/api/mcp/pair').json()['code']
        connected=subprocess.run([sys.executable,'-S',str(downloaded),'--url',url,'--credential-file',str(credential),'connect','--code-file','-'],input=code,text=True,capture_output=True)
        assert connected.returncode==0,connected.stderr
        assert 'token' not in connected.stdout and code not in connected.stdout
        assert credential.stat().st_mode & 0o777==0o600
        imported=client.call('import_document',{'title':'内网文档检查','filename':'notes.md','content':'返回 name；示例只返回 id。','goal':'只检查文档，不发请求'})
        pid=imported['project']['id']
        assert imported['project']['task']['goal']=='只检查文档，不发请求'
        async def scenario():
            params=StdioServerParameters(command=sys.executable,args=['-S',str(downloaded),'--url',url,'--credential-file',str(credential),'mcp'])
            async with stdio_client(params) as (read,write),ClientSession(read,write) as session:
                await session.initialize()
                assert {'get_requirement_design','resume_requirement_test','run_test_capability'} <= {t.name for t in (await session.list_tools()).tools}
                doc=await session.call_tool('get_test_document',{'project_id':pid})
                assert not doc.isError and '返回 name' in str(doc)
                result=await session.call_tool('publish_task_report',{'project_id':pid,'title':'文档检查结果','summary':'描述与示例字段不一致。','findings':[{'title':'name 示例缺失','evidence':'返回 name；示例只返回 id。'}]})
                assert not result.isError,result
                data=json.loads(result.content[0].text)
                assert data['report']['report_url'].startswith(url)
                assert data['report']['requests_sent']==0
                assert browser.get(data['report']['report_url']).status_code==200
                browser.delete('/api/mcp/pair')
                assert (await session.call_tool('get_test_workspace',{})).isError
        asyncio.run(scenario())


def test_admin_origin_configuration_is_explicit(tmp_path,monkeypatch):
    monkeypatch.setenv('API_TEST_ALLOWED_ORIGINS','http://192.0.2.20:19090,https://test.internal')
    app=web.create_app(tmp_path,start_fixture=False)
    assert app is not None
    monkeypatch.setenv('API_TEST_ALLOWED_ORIGINS','http://test.internal/path')
    with pytest.raises(ValueError,match='HTTP'):
        web.create_app(tmp_path,start_fixture=False)
