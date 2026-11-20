"""Real stdio MCP -> HTTP workspace -> real test API -> existing HTML report."""
import asyncio
import copy
import json
import socket
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
pytest.importorskip("mcp", reason="Install .[mcp] for MCP integration tests")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from api_test_tool import web
from api_test_tool.mcp_access import MCPAccess
from api_test_tool.web_storage import Store


def test_pair_once_expiry_and_revoke(tmp_path, monkeypatch):
    store = Store(tmp_path)
    session, _ = store.session(None)
    access = MCPAccess(store)
    code = access.issue(session['id'])['code']
    token = access.redeem(code)['token']
    assert access.authenticate(token) == session['id']
    with pytest.raises(PermissionError):
        access.redeem(code)
    access.revoke(session['id'])
    with pytest.raises(PermissionError):
        access.authenticate(token)
    code = access.issue(session['id'])['code']
    now = time.time()
    monkeypatch.setattr('api_test_tool.mcp_access.time.time', lambda: now + 601)
    with pytest.raises(PermissionError):
        access.redeem(code)


def test_mcp_auth_csrf_owner_isolation_and_no_model_tools(tmp_path):
    app = web.create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as owner, TestClient(app) as other:
        owner.headers['x-csrf-token'] = owner.get('/api/bootstrap').json()['csrf']
        other.headers['x-csrf-token'] = other.get('/api/bootstrap').json()['csrf']
        assert owner.post('/api/mcp/pair', headers={'x-csrf-token': ''}).status_code == 403
        assert owner.post('/api/mcp/pair', headers={'origin':'https://evil.example'}).status_code == 403
        assert owner.post('/api/mcp/call', json={'action':'workspace'}).status_code == 401
        code = owner.post('/api/mcp/pair').json()['code']
        assert other.post('/api/mcp/redeem', json={'code':code}, headers={'origin':'https://evil.example'}).status_code == 403
        token = other.post('/api/mcp/redeem', json={'code':code}).json()['token']
        headers={'Authorization':'Bearer '+token}
        def call(action, arguments={}):
            return other.post('/api/mcp/call', json={'action':action,'arguments':arguments}, headers=headers)
        imported = call('import', {'template':'items','title':'MCP isolation'}).json()
        pid = imported['project']['id']
        assert owner.get('/api/projects/'+pid).status_code == 200
        assert other.get('/api/projects/'+pid).status_code in {403,404}
        assert call('model').status_code == 400
        assert call('rules', {'project_id':pid,'mode':'model'}).status_code == 400
        assert call('run', {'project_id':pid,'environment':'items'}).status_code == 404
        owner.delete('/api/mcp/pair')
        assert call('workspace').status_code == 401


@contextmanager
def running_app(app):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets':[sock]}, daemon=True)
    thread.start()
    deadline=time.monotonic()+10
    while not server.started and time.monotonic()<deadline:
        time.sleep(.02)
    assert server.started
    try:
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit=True
        thread.join(10)
        sock.close()


@pytest.mark.parametrize("adapter", ["original", "standalone"])
def test_real_stdio_candidate_review_execution_report(tmp_path, monkeypatch, adapter):
    audit=[]
    class Probe(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            audit.append(self.path)
            raw=b'{"ok":true}'
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    probe=ThreadingHTTPServer(('127.0.0.1',0),Probe)
    thread=threading.Thread(target=probe.serve_forever,daemon=True)
    thread.start()
    target=f'http://127.0.0.1:{probe.server_port}'
    model_calls=[]
    def no_model(*a,**kw):
        model_calls.append(True)
        raise AssertionError('MCP must not call a model')
    monkeypatch.setattr(web,'generate_text',no_model)
    document={'openapi':'3.0.3','info':{'title':'MCP probe','version':'1'},'paths':{'/probe':{'get':{
        'operationId':'get_probe','responses':{'200':{'description':'successful read'}}}}}}
    app=web.create_app(tmp_path/'data',start_fixture=False,testing=True,extra_test_origins=(target,))
    credential=tmp_path/'client'/'token.json'
    try:
        with running_app(app) as url, httpx.Client(base_url=url,trust_env=False) as browser:
            browser.headers['x-csrf-token']=browser.get('/api/bootstrap').json()['csrf']
            code=browser.post('/api/mcp/pair').json()['code']
            async def scenario():
                params=StdioServerParameters(command=sys.executable,args=['-m','api_test_tool.mcp_server','--url',url,'--credential-file',str(credential)])
                if adapter == 'standalone':
                    params=StdioServerParameters(command=sys.executable,args=['-S',str(web.STATIC/'api-test-client.py'),'--url',url,'--credential-file',str(credential),'mcp'])
                async with stdio_client(params) as (reader,writer), ClientSession(reader,writer) as session:
                    await session.initialize()
                    tools=(await session.list_tools()).tools
                    assert {'get_requirement_design', 'record_test_checkpoint', 'resume_requirement_test',
                            'get_test_capabilities', 'run_test_capability', 'get_test_experiment'} <= {t.name for t in tools}
                    assert next(t for t in tools if t.name=='execute_tests').annotations.destructiveHint
                    async def invoke(name, **args):
                        result=await session.call_tool(name,args)
                        assert not result.isError, result
                        return result.structuredContent or json.loads(result.content[0].text)
                    connected=await invoke('connect_workspace',code=code)
                    assert 'token' not in json.dumps(connected)
                    imported=await invoke('import_document',title='MCP probe',filename='probe.json',content=json.dumps(document))
                    pid=imported['project']['id']
                    context=await invoke('get_test_context',project_id=pid)
                    sources=context['contract']['sources']
                    op=context['contract']['operations']['get_probe']
                    sid=next(sid for sid in op['source_ids'] if '200' in sources[sid]['excerpt'])
                    evidence=[{'source_id':sid,'quote':sources[sid]['excerpt']}]
                    case={'id':'MCP-001','title':'Read probe','operation_id':'get_probe','scenario':'normal','variables':{},
                          'steps':[{'id':'read','operation_id':'get_probe','request':{},'assertions':[{'kind':'status','expected':200,'evidence':evidence}],'extract':[]}],
                          'cleanup_steps':[],'notes':'Read-only probe'}
                    saved=await invoke('submit_test_cases',project_id=pid,revision=context['revision'],cases=[case])
                    assert saved['summary']['approval_eligible']==1
                    stale=await session.call_tool('submit_test_cases',{'project_id':pid,'revision':context['revision'],'cases':[case]})
                    assert stale.isError
                    invalid=copy.deepcopy(case);invalid['id']='INVALID';invalid['steps'][0]['operation_id']='invented'
                    rejected=await session.call_tool('submit_test_cases',{'project_id':pid,'revision':saved['revision'],'cases':[invalid]})
                    assert rejected.isError
                    context=await invoke('get_test_context',project_id=pid)
                    assert len(context['candidates']['cases'])==1
                    case2=copy.deepcopy(case);case2['id']='MCP-002'
                    blocked=copy.deepcopy(case);blocked['id']='MCP-GAP';blocked['steps'][0]['assertions']=[];blocked['notes']='文档缺少此项业务预期，保留为报告缺口'
                    merged=await invoke('submit_test_cases',project_id=pid,revision=context['revision'],cases=[case2,blocked])
                    assert merged['summary']['total']==3
                    assert not audit
                    approved=await invoke('review_test_cases',project_id=pid,case_ids=['MCP-001','MCP-002'])
                    assert approved['summary']['READY']==2
                    job=await invoke('execute_tests',project_id=pid,environment='custom',base_url=target)
                    for _ in range(100):
                        job=await invoke('get_test_job',job_id=job['id'])
                        if job['status'] in {'completed','failed'}: break
                        await asyncio.sleep(.05)
                    assert job['status']=='completed',job
                    report=await invoke('get_test_report',project_id=pid)
                    assert report['report']['summary']['PASS']==2
                    assert all('steps' not in c for c in report['cases'])
                    html=browser.get(report['report']['report_url'])
                    assert html.status_code==200 and 'text/html' in html.headers['content-type']
                    assert browser.get('/api/projects/'+pid).json()['project']['generation_mode']=='mcp'
                    detail=await invoke('get_test_report',project_id=pid,include_evidence=True)
                    assert len(detail['cases'][0]['steps'])==1
                    assert report['report']['summary']['BLOCKED']==1
                    final=await invoke('publish_task_report',project_id=pid,title='接口检查总报告',summary='已完成可执行检查，另有一项文档预期缺口。',
                        sections=[{'title':'测试范围','content':'2 条实际执行；1 条缺少预期未执行。'}],
                        findings=[{'title':'业务预期缺失','detail':'MCP-GAP 未执行，不能记为通过。'}],run_ids=[report['report']['id']])
                    assert final['report']['requests_sent']==2
                    assert browser.get(final['report']['report_url']).status_code==200
                    final_read=await invoke('get_test_report',project_id=pid)
                    assert final_read['analysis']['kind']=='execution_summary'
                    assert final_read['analysis']['requests_sent']==2
                    assert final_read['analysis']['runs'][0]['summary']['BLOCKED']==1
                    invalid_report=await session.call_tool('publish_task_report',{'project_id':pid,'title':'不能伪造执行','summary':'测试','run_ids':['invented-run']})
                    assert invalid_report.isError
                    review_doc='接口 /users：响应中有 name。示例却只有 id。请核对名称字段。'
                    doc=await invoke('import_document',title='只检查文档',filename='notes.yaml',content=review_doc,goal='检查文档内容，不发送请求')
                    did=doc['project']['id']
                    assert not doc['contract']['operations']
                    pieces=[];offset=0
                    while True:
                        page=await invoke('get_test_document',project_id=did,offset=offset,limit=13)
                        pieces.append(page['content'])
                        if page['next_offset'] is None:break
                        offset=page['next_offset']
                    assert ''.join(pieces)==review_doc
                    analyzed=await invoke('publish_task_report',project_id=did,title='文档一致性报告',summary='描述与示例存在字段不一致。',findings=[{
                        'title':'name 字段缺少示例','detail':'描述与示例需统一。','evidence':'示例却只有 id','recommendation':'补充 name 示例。','severity':'待确认'}])
                    assert analyzed['report']['kind']=='analysis' and analyzed['report']['requests_sent']==0
                    assert browser.get(analyzed['report']['report_url']).status_code==200
                    assert browser.get('/api/projects/'+did).json()['bundle'] is None
                    reviewed=await invoke('get_test_report',project_id=did)
                    assert reviewed['analysis']['findings'][0]['title']=='name 字段缺少示例'
                    browser.delete('/api/mcp/pair')
                    assert (await session.call_tool('get_test_workspace',{})).isError
            asyncio.run(scenario())
        assert audit==['/probe','/probe']
        assert not model_calls
        assert credential.stat().st_mode & 0o777 == 0o600
    finally:
        probe.shutdown();thread.join(3);probe.server_close()
