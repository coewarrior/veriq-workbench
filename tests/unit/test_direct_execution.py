"""Isolated acceptance of current-chat leases, timeouts and command receipts."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from api_test_tool.orchestration import Controller, Conflict
from api_test_tool.web_storage import Store
from api_test_tool.managed_service import ManagedService
from api_test_tool.managed_workflow import ManagedWorkflow
from api_test_tool.managed_runner import Runner

STATIC=Path(__file__).parents[2]/'api_test_tool'/'static'


def setup(tmp_path, count=2):
    store=Store(tmp_path);session,_=store.session(None);owner=session['id']
    p=store.create_project(owner,'test','test.md','test')
    store.update_project(owner,p['id'],{'test_kind':'ui','ui_target_url':'https://test.example/login','task':{'goal':'test'}})
    clock=[1000.];c=Controller(store,lambda:clock[0]);svc=ManagedService(c,STATIC)
    for i in range(count):c.add_account(owner,dict(project_id=p['id'],target='https://test.example',identity=str(i),credential=''))
    c.register_host(owner,'host',enforcement_evidence=dict(network_isolation='fixture',credential_isolation='fixture',tool_gate='fixture',browser_context_isolation='fixture',version='fixture',simple_dispatch=1,direct_execution=1),browser_slots=20,model_slots=1)
    def task(route='local_browser',key='task'):
        return c.create_task(owner,dict(project_id=p['id'],request_id=key,goal='test',execution_route=route,session_workflow=True,
            modules=[dict(key=key,title=key,requirements=[])]))['task_id']
    return c,svc,owner,p,clock,task


def claim_ready(c,svc,o,tid,holder='chat'):
    result=svc.direct.call(o,dict(action='claim',task_id=tid,holder_id=holder))
    e=next(e for e in c.pending_events(o,'host') if e['lease_id']==result['lease_id'])
    c.acknowledge_start(o,e['id'],thread_id='direct:'+holder,turn_id=e['lease_id'])
    return {'lease_id':e['lease_id'],'holder_id':holder}


def test_direct_claim_shared_pool_does_not_consume_model_slots(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path,4)
    background=task('managed','background');c.schedule()
    assert len(c.snapshot(o)['leases'])==1
    first=claim_ready(c,s,o,task(key='first'),'chat1')
    second=claim_ready(c,s,o,task(key='second'),'chat2')
    snap=c.snapshot(o)
    assert len(snap['leases'])==3
    assert len({a for l in snap['leases'] for a in l['account_ids']})==3
    assert s.direct.call(o,dict(action='claim',task_id=next(n['task_id'] for n in snap['nodes'] if n['id']==next(l['node_id'] for l in snap['leases'] if l['id']==first['lease_id'])),holder_id='other'))['state']=='unavailable'
    with pytest.raises(PermissionError):s.direct.call(o,{**second,'holder_id':'chat1','action':'context'})


def test_no_actor_does_not_occupy_account_or_launch_background(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path)
    task();c.schedule();assert not c.snapshot(o)['leases']
    assert '当前 Codex' in c.snapshot(o)['nodes'][0]['reason']


@pytest.mark.parametrize('timeout,mode',[(121,'startup'),(601,'progress'),(61,'lost')])
def test_timeout_revokes_before_release_and_rejects_late_actor(tmp_path,timeout,mode):
    c,s,o,p,clock,task=setup(tmp_path,1);tid=task()
    r=s.direct.call(o,dict(action='claim',task_id=tid,holder_id='chat'))
    e=c.pending_events(o,'host')[0] # Delivery without ACK is distinct from never delivered.
    if mode!='startup':
        c.acknowledge_start(o,e['id'],thread_id='chat',turn_id='turn')
    clock[0]+=timeout
    if mode!='lost':
        with c.transaction() as (_,state):state['runners']['host']['heartbeat']=clock[0]
    c.schedule();l=c.snapshot(o)['leases'][0]
    assert l['revoked'] and l['timeout_reason']
    with pytest.raises(Conflict):s.direct.call(o,dict(action='credentials',holder_id='chat',lease_id=l['id'],account_id=l['account_ids'][0]))
    assert len(c.snapshot(o)['leases'])==1 # No unverified timeout stealing.
    c.return_account(o,'host',dict(lease_id=l['id'],executor_stopped=True,outcome='yield'))
    assert not c.snapshot(o)['leases']
    assert c.snapshot(o)['nodes'][0]['state']=='blocked' # Not replayed automatically.


def test_lost_browser_response_is_not_reexecuted_and_old_receipt_survives(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    aid=c.snapshot(o)['leases'][0]['account_ids'][0]
    cmd={**ids,'action':'browser','request_id':'submit-once','account_id':aid,'browser_action':'click','parameters':{'selector':'button'}}
    assert s.direct.call(o,cmd)['state']=='queued'
    assert s.direct.call(o,cmd)['state']=='queued'
    auth=dict(owner=o,host_id='host')
    first=s.host_call(auth,'direct_poll',{'lease_id':ids['lease_id']})
    assert first['command']['id']=='submit-once'
    assert s.host_call(auth,'direct_poll',{'lease_id':ids['lease_id']})=={}
    assert s.direct.call(o,cmd)['state']=='running'
    with pytest.raises(Conflict):s.direct.call(o,{**cmd,'parameters':{'selector':'different'}})
    s.host_call(auth,'direct_result',dict(lease_id=ids['lease_id'],request_id='submit-once',state='completed',result={'value':'once'}))
    assert s.direct.call(o,cmd)['result']=={'value':'once'}
    c.return_account(o,'host',dict(lease_id=ids['lease_id'],executor_stopped=True,outcome='completed',result='partial'))
    assert s.direct.call(o,{**ids,'action':'result','request_id':'submit-once'})['state']=='completed'


def test_unknown_operation_requires_observation_not_blind_replay(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    auth=dict(owner=o,host_id='host');common={'lease_id':ids['lease_id'],'operation_id':'payment','action':'click','hash':'hash'}
    assert s.host_call(auth,'operation_begin',common)['execute']
    assert not s.host_call(auth,'operation_begin',common)['execute']
    with pytest.raises(Conflict):s.host_call(auth,'operation_begin',{**common,'operation_id':'new-id'})
    assert s.host_call(auth,'operation_begin',{**common,'action':'snapshot','operation_id':'read'})['execute']
    s.host_call(auth,'operation_complete',{**common,'operation_id':'read','state':'confirmed','result':{'snapshot':'receipt exists'}})
    s.direct.call(o,{**ids,'action':'reconcile','operation_id':'payment','operation_state':'confirmed','reason':'Read original receipt ID; submission already completed'})
    assert s.host_call(auth,'operation_begin',common)['state']=='confirmed'


def test_receipt_and_idle_poll_do_not_enter_write_transaction(tmp_path,monkeypatch):
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    auth=dict(owner=o,host_id='host')
    # Exact request keys, including punctuation, must not become JSON paths.
    request='read."[1]'
    s.direct.call(o,{**ids,'action':'browser','browser_action':'snapshot','request_id':request})
    assert s.host_call(auth,'direct_poll',{'lease_id':ids['lease_id']})['command']['id']==request
    payload={'snapshot':'历史现场'*2000,'_image_url':'data:image/png;base64,unchanged'}
    s.host_call(auth,'direct_result',dict(lease_id=ids['lease_id'],request_id=request,state='completed',result=payload))
    with c.connect() as db:
        before=db.execute('SELECT value FROM state WHERE id=1').fetchone()[0]
    def forbidden():raise AssertionError('Read/idle poll took a write transaction')
    monkeypatch.setattr(c,'transaction',forbidden)
    assert s.direct.call(o,{**ids,'action':'result','request_id':request})['result']==payload
    assert s.host_call(auth,'direct_poll',{'lease_id':ids['lease_id']})=={}
    with pytest.raises(PermissionError):s.direct.call(o,{**ids,'action':'result','request_id':request,'holder_id':'other'})
    with pytest.raises(PermissionError):s.direct.call('other',{**ids,'action':'result','request_id':request})
    with pytest.raises(PermissionError):s.host_call(dict(owner=o,host_id='other'),'direct_poll',{'lease_id':ids['lease_id']})
    with c.connect() as db:
        assert db.execute('SELECT value FROM state WHERE id=1').fetchone()[0]==before


@pytest.mark.parametrize('changed',['revoked','revision','epoch','intent','owner','direct','waiting'])
def test_idle_poll_keeps_all_lease_fences(tmp_path,changed):
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    with c.transaction() as (_,state):
        lease=state['leases'][ids['lease_id']];node=state['nodes'][lease['node_id']]
        if changed=='revoked':lease['revoked']=True
        elif changed=='revision':node['revision']+=1
        elif changed=='epoch':lease['epoch']='old'
        elif changed=='intent':state['tasks'][node['task_id']]['intent']='stop'
        elif changed=='owner':node['owner']='other'
        elif changed=='direct':lease['direct']=False
        elif changed=='waiting':lease['waiting']={'since':clock[0],'reason':'human'}
    def poll():return s.host_call(dict(owner=o,host_id='host'),'direct_poll',{'lease_id':ids['lease_id']})
    if changed=='waiting':assert poll()=={}
    else:
        with pytest.raises((PermissionError,Conflict)):poll()


def test_human_wait_preserves_browser_until_explicit_continue_or_timeout(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    s.direct.call(o,{**ids,'action':'wait','reason':'enter verification code in this chat'})
    clock[0]+=700
    with c.transaction() as (_,state):state['runners']['host']['heartbeat']=clock[0]
    c.schedule();assert not c.snapshot(o)['leases'][0]['revoked']
    s.direct.call(o,{**ids,'action':'continue'})
    assert c.snapshot(o)['nodes'][0]['state']=='running'


def test_direct_browser_lifecycle_never_opens_codex_and_returns_once(tmp_path):
    async def run():
        c,s,o,p,clock,task=setup(tmp_path)
        result=s.direct.call(o,dict(action='claim',task_id=task(),holder_id='chat'))
        runner=Runner(tmp_path/'runner',None,SimpleNamespace(stop=lambda _:None,open=lambda _:pytest.fail('Direct execution must not start Codex')),headed=False,max_browsers=0,max_models=0)
        runner.root.mkdir();runner.browser=SimpleNamespace(active={},bind=AsyncMock(),fence=AsyncMock())
        async def bind(ctx):runner.browser.active[ctx['lease']['id']]=ctx['lease']
        runner.browser.bind.side_effect=bind
        async def call(method,**args):return s.host_call({'owner':o,'host_id':'host'},method,args)
        runner.call=call
        event=c.pending_events(o,'host')[0]
        job=asyncio.create_task(runner.execute_direct(event));runner.jobs[event['lease_id']]=job
        for _ in range(20):
            if c.snapshot(o)['nodes'][0]['state']=='running':break
            await asyncio.sleep(.01)
        s.direct.call(o,dict(action='finish',holder_id='chat',lease_id=result['lease_id'],outcome='blocked',reason='fixture unavailable'))
        await runner.interrupt(result['lease_id']);await job
        assert not c.snapshot(o)['leases']
        assert c.snapshot(o)['nodes'][0]['state']=='blocked'
        assert not c.snapshot(o)['nodes'][0].get('report_error')
        runner.browser.fence.assert_awaited()
    asyncio.run(run())


def test_capacity_not_local_two_gib_per_model(tmp_path,monkeypatch):
    import psutil
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=3*1024**3))
    monkeypatch.setattr(psutil,'cpu_percent',lambda:5)
    r=Runner(tmp_path,None,None,headed=False,max_browsers=0,max_models=0)
    assert r.capacity()==(4,4) # Previously 4 browser slots but only 1 model slot.
    r.max_models=7
    assert r.capacity()==(4,7) # Explicit remote service quota, independent of browser RAM.


def test_real_headless_browser_current_chat_receipt_and_release(tmp_path):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import threading
    from api_test_tool.managed_browser import ManagedBrowser
    class Page(BaseHTTPRequestHandler):
        def do_GET(self):
            body=b'<html><body><button onclick="this.textContent=String(Number(this.textContent)+1)">0</button></body></html>'
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    http=ThreadingHTTPServer(('127.0.0.1',0),Page);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    async def run():
        c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
        api=SimpleNamespace(call=lambda method,**args:s.host_call({'owner':o,'host_id':'host'},method,args))
        browser=ManagedBrowser(api,tmp_path/'browser')
        await browser.start()
        try:
            context=api.call('read',lease_id=ids['lease_id']);await browser.bind(context)
            aid=context['accounts'][0]['id'];lid=ids['lease_id']
            await browser.operate(lid,aid,'navigate',{'url':f'http://127.0.0.1:{http.server_port}/'},'open')
            first=await browser.operate(lid,aid,'click',{'selector':'button'},'click-once')
            retry=await browser.operate(lid,aid,'click',{'selector':'button'},'click-once')
            assert first==retry
            snapshot=await browser.operate(lid,aid,'snapshot',{},'observe')
            assert '"1"' in snapshot['snapshot'] and '"2"' not in snapshot['snapshot']
            assert browser._process_path(lid).exists()
            # Recreated host has no in-memory browser reference: durable PID +
            # creation-time ownership must still fence the old browser.
            restarted=ManagedBrowser(api,tmp_path/'browser')
            await restarted.fence(lid)
            await browser.fence(lid)
            assert not browser._process_path(lid).exists()
            with pytest.raises(RuntimeError):await browser._operate(lid,aid,'click',{'selector':'button'})
        finally:await browser.close()
    try:asyncio.run(run())
    finally:http.shutdown();http.server_close();thread.join()


def test_mcp_http_default_route_and_owner_boundary(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from api_test_tool.web import create_app
    drain=tmp_path/'deploy-drain'
    monkeypatch.setenv('API_TEST_DRAIN_FILE',str(drain))
    app=create_app(tmp_path,start_fixture=False,testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token']=client.get('/api/bootstrap').json()['csrf']
        project=client.post('/api/account-projects',json={'name':'fixture','login_url':'https://test.example/login'}).json()
        code=client.post('/api/mcp/pair').json()['code']
        token=client.post('/api/mcp/redeem',json={'code':code}).json()['token']
        headers={'Authorization':'Bearer '+token}
        r=client.post('/api/mcp/call',headers=headers,json={'action':'start_workflow','arguments':{'request_id':'create-once','goal':'Inspect fixture','test_kind':'ui','account_project_id':project['id'],'execution_route':'local_browser'}})
        assert r.status_code==200,r.text
        data=r.json();assert data['execution']['mode']=='local_browser' and not data['execution']['scheduled']
        assert all(module['reason']=='等待已核验的执行连接程序' for module in data['execution']['modules'])
        replay=client.post('/api/mcp/call',headers=headers,json={'action':'start_workflow','arguments':{'request_id':'create-once','goal':'Inspect fixture','test_kind':'ui','account_project_id':project['id'],'execution_route':'local_browser'}}).json()
        assert replay['project_id']==data['project_id']
        task=data['execution']['task_id']
        claim=client.post('/api/mcp/call',headers=headers,json={'action':'direct_session','arguments':{'action':'claim','task_id':task,'holder_id':'chat'}})
        assert claim.status_code==200,claim.text
        assert claim.json()['state']=='queued'
        with app.state.orchestration.connect() as db:
            assert not json.loads(db.execute('SELECT value FROM state').fetchone()[0])['leases']
        def direct(**args):
            return client.post('/api/mcp/call',headers=headers,json={'action':'direct_session','arguments':{'holder_id':'chat',**args}})
        queued=direct(action='context',task_id=task,node_id=claim.json()['node_id'])
        assert queued.status_code==200 and queued.json()['lease_id'] is None
        assert queued.json()['next_action']=='end_turn_until_resources' and not queued.json()['browser_ready']
        missing=direct(action='browser',request_id='snapshot',browser_action='snapshot')
        assert missing.status_code==400 and '缺少 lease_id' in missing.json()['detail']
        c=app.state.orchestration
        with c.connect() as db:
            state=json.loads(db.execute('SELECT value FROM state').fetchone()[0])
        owner=state['tasks'][task]['owner']
        c.add_account(owner,dict(account_project_id=project['id'],identity='fixture',credential=''))
        c.register_host(owner,'host',enforcement_evidence=dict(network_isolation='fixture',credential_isolation='fixture',tool_gate='fixture',browser_context_isolation='fixture',version='fixture',simple_dispatch=1,direct_execution=1),browser_slots=2,model_slots=1)
        ready=direct(action='claim',task_id=task).json()
        assert ready['lease_id'] and len(ready['account_ids'])==1 and not ready['browser_ready']
        event=c.pending_events(owner,'host')[0]
        c.acknowledge_start(owner,event['id'],thread_id='direct:chat',turn_id=ready['lease_id'])
        assert direct(action='claim',task_id=task).json()['browser_ready']
        good=direct(action='browser',lease_id=ready['lease_id'],request_id='snapshot',browser_action='snapshot')
        assert good.status_code==200,good.text
        wrong=direct(action='browser',lease_id=ready['lease_id'],request_id='bad',browser_action='snapshot',account_id='not-assigned')
        assert wrong.status_code==403 and 'account_id 不属于当前租约' in wrong.json()['detail']
        other=direct(action='context',lease_id=ready['lease_id'],holder_id='other-chat')
        assert other.status_code==403 and 'holder_id' in other.json()['detail']
        drain.touch()
        assert direct(action='claim',task_id=task).status_code==200
        context=direct(action='context',lease_id=ready['lease_id'])
        assert context.status_code==200 and context.json()['lease']['id']==ready['lease_id']
        wrong=direct(action='context',lease_id=ready['lease_id'],holder_id='other-chat')
        assert wrong.status_code==403 # Drain exemption does not bypass ownership.
        service=app.state.managed_service;auth={'owner':owner,'host_id':'host'}
        service.host_call(auth,'direct_poll',{'lease_id':ready['lease_id']})
        service.host_call(auth,'direct_result',{'lease_id':ready['lease_id'],'request_id':'snapshot','state':'completed','result':{'text':'fixture'}})
        assert direct(action='result',lease_id=ready['lease_id'],request_id='snapshot').json()['state']=='completed'
        assert direct(action='checkpoint',lease_id=ready['lease_id'],checkpoint={'observed':'fixture'}).status_code==200
        finish=direct(action='finish',lease_id=ready['lease_id'],outcome='yield')
        assert finish.status_code==200 and not finish.json()['released']
        service.host_call(auth,'return_account',{'lease_id':ready['lease_id'],'executor_stopped':True,'outcome':'yield'})
        assert client.get('/healthz').json()['deployment']=={'draining':True,'active_writes':0,'active_jobs':0}


def test_multiple_accounts_are_acquired_as_one_complete_set(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path,2)
    first=claim_ready(c,s,o,task(key='one'),'one')
    all_accounts=[a['id'] for a in c.snapshot(o)['accounts']]
    tid=task(key='both')
    r=s.direct.call(o,dict(action='claim',task_id=tid,holder_id='two',account_ids=all_accounts))
    assert not r['lease_id']
    assert len(c.snapshot(o)['leases'])==1 # Free account is not partially grabbed.
    c.return_account(o,'host',dict(lease_id=first['lease_id'],executor_stopped=True,outcome='completed',result='partial'))
    c.schedule();leases=c.snapshot(o)['leases']
    assert len(leases)==1 and set(leases[0]['account_ids'])==set(all_accounts)
    assert leases[0]['browser_units']==2


def test_stale_browser_command_cannot_start_after_stop(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);tid=task();ids=claim_ready(c,s,o,tid)
    aid=c.snapshot(o)['leases'][0]['account_ids'][0]
    s.direct.call(o,{**ids,'action':'browser','account_id':aid,'request_id':'queued','browser_action':'click','parameters':{'selector':'button'}})
    c.control(o,tid,dict(action='stop',revision=1,request_id='stop'))
    with pytest.raises(Conflict):s.host_call({'owner':o,'host_id':'host'},'direct_poll',{'lease_id':ids['lease_id']})
    c.return_account(o,'host',dict(lease_id=ids['lease_id'],executor_stopped=True,outcome='yield'))
    assert s.direct.call(o,{**ids,'action':'result','request_id':'queued'})['state']=='cancelled'
    assert s.direct.call(o,{**ids,'action':'finish'})['released']


def test_recursive_split_preserves_dependencies_and_rejects_cycle(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);tid=task()
    n=c.snapshot(o)['nodes'][0]
    result=c.split(o,n['id'],{'revision':1,'children':[{'key':'a','title':'A','scope':'a'},{'key':'b','title':'B','scope':'b','depends_on':['a']}]})
    nodes={n['title']:n for n in c.snapshot(o)['nodes']}
    assert nodes['B']['depends_on']==[nodes['A']['id']]
    c.split(o,nodes['A']['id'],{'revision':nodes['A']['revision'],'children':[{'title':'A1','scope':'a1'}]})
    child=next(n for n in c.snapshot(o)['nodes'] if n['title']=='A1')
    with pytest.raises(ValueError):c.split(o,child['id'],{'revision':child['revision'],'children':[{'key':'x','title':'x','scope':'x','depends_on':['x']}]})


def test_current_actor_resume_reclaims_same_node_preserving_history(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);tid=task();ids=claim_ready(c,s,o,tid,'old-chat')
    c.return_account(o,'host',dict(lease_id=ids['lease_id'],executor_stopped=True,outcome='blocked',reason='needs input',checkpoint={'object':'original'}))
    c.control(o,tid,dict(action='resume',revision=1,request_id='resume',instruction='continue original'))
    result=s.direct.call(o,dict(action='claim',holder_id='new-chat',task_id=tid))
    assert result['lease_id']!=ids['lease_id']
    assert c.snapshot(o)['nodes'][0]['checkpoint']['object']=='original'


def test_never_delivered_start_releases_without_waiting_for_dead_host(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path)
    s.direct.call(o,dict(action='claim',task_id=task(),holder_id='chat'))
    clock[0]+=121;c.schedule()
    assert not c.snapshot(o)['leases']
    assert c.snapshot(o)['nodes'][0]['state']=='blocked'
    s.finalize_pending()
    assert not c.snapshot(o)['nodes'][0].get('report_error')


def test_final_push_waits_for_settlement_and_includes_blocked_empty_record(tmp_path,monkeypatch):
    from api_test_tool.wecom import WeCom
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    aid=c.snapshot(o)['leases'][0]['account_ids'][0]
    final=WeCom(c.store)
    assert not final._ui_final(o,c.store.update_project(o,p['id'],{'execution_route':'local_browser','ui_final_report':{'execution_id':'fake','revision':1}}),{'id':'fake','revision':1,'cases':[]})
    s.host_call({'owner':o,'host_id':'host'},'return_account',dict(lease_id=ids['lease_id'],executor_stopped=True,outcome='blocked',reason='fixture unavailable'))
    # Returning the original receipt must not synchronously regenerate reports.
    # The existing scheduler callback processes the durable finalization marker.
    assert not c.snapshot(o)['leases']
    assert c.snapshot(o)['nodes'][0]['finalization_pending']
    s.finalize_pending()
    node=c.snapshot(o)['nodes'][0]
    project=c.store.get_project(o,node['record_project_id'])
    from api_test_tool import ui_records
    record=ui_records.load(c.store,o,project['id'],node['record_execution_id'])
    assert record['cases']==[] and record['report_id']
    assert final._ui_final(o,project,record)
    assert record['coverage'][0]['gap']=='fixture unavailable'


def test_human_console_editing_is_exclusive_with_current_chat(tmp_path,monkeypatch):
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    with c.transaction() as (_,state):state['runners']['host']['evidence']['remote_browser']=True
    monkeypatch.setattr('api_test_tool.managed_console.time.time',lambda:clock[0])
    aid=c.snapshot(o)['leases'][0]['account_ids'][0];target={'lease_id':ids['lease_id'],'account_id':aid}
    with pytest.raises(Conflict):s.console.authorize(o,target,'click')
    s.direct.call(o,{**ids,'action':'wait','reason':'enter verification'})
    assert s.console.authorize(o,target,'click')['editable']
    with pytest.raises(Conflict):s.direct.call(o,{**ids,'action':'browser','account_id':aid,'request_id':'race','browser_action':'click','parameters':{'selector':'button'}})
    s.direct.call(o,{**ids,'action':'continue'})
    with pytest.raises(Conflict):s.console.authorize(o,target,'click')


def test_credentials_only_assigned_account_and_no_password_in_context(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    assigned=c.snapshot(o)['leases'][0]['account_ids'][0]
    other=next(a['id'] for a in c.snapshot(o)['accounts'] if a['id']!=assigned)
    with c.transaction() as (_,state):state['accounts'][assigned]['credential']=c.store._cipher.encrypt(b'fixture-password').decode()
    context=s.direct.call(o,{**ids,'action':'context'})
    assert 'fixture-password' not in json.dumps(context)
    credentials=s.direct.call(o,{**ids,'action':'credentials','account_id':assigned})
    assert credentials['password']=='fixture-password'
    with pytest.raises(PermissionError):s.direct.call(o,{**ids,'action':'credentials','account_id':other})


def test_queued_without_accounts_can_finish_with_truthful_final_report(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path,0);tid=task()
    queued=s.direct.call(o,dict(action='claim',task_id=tid,holder_id='chat'))
    assert not queued['lease_id']
    result=s.direct.call(o,dict(action='finish',task_id=tid,node_id=queued['node_id'],holder_id='chat',outcome='blocked',reason='没有可用账号，未验证'))
    assert result['released'] and result['state']=='blocked'
    node=c.snapshot(o)['nodes'][0]
    assert node['record_execution_id'] and not node.get('report_error')
    assert not c.snapshot(o)['leases']


def test_single_assigned_account_default_preserves_command_identity(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    assigned=c.snapshot(o)['leases'][0]['account_ids'][0]
    with c.transaction() as (_,state):state['accounts'][assigned]['credential']=c.store._cipher.encrypt(b'fixture-password').decode()
    assert s.direct.call(o,{**ids,'action':'credentials'})['password']=='fixture-password'
    cmd={**ids,'action':'browser','browser_action':'click','request_id':'once','parameters':{'selector':'button'}}
    assert s.direct.call(o,cmd)==s.direct.call(o,{**cmd,'account_id':assigned})
    first=s.host_call({'owner':o,'host_id':'host'},'direct_poll',{'lease_id':ids['lease_id']})
    assert first['command']['account_id']==assigned
    assert s.host_call({'owner':o,'host_id':'host'},'direct_poll',{'lease_id':ids['lease_id']})=={}


def test_multi_account_missing_selection_does_not_send_or_disclose_credentials(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path,2);tid=task()
    accounts=[a['id'] for a in c.snapshot(o)['accounts']]
    s.direct.call(o,dict(action='claim',task_id=tid,holder_id='chat',account_ids=accounts))
    ids=claim_ready(c,s,o,tid)
    for action in ('credentials','browser'):
        with pytest.raises(ValueError,match='多个账号'):
            s.direct.call(o,{**ids,'action':action,'browser_action':'snapshot','request_id':'not-sent'})
    assert s.host_call({'owner':o,'host_id':'host'},'direct_poll',{'lease_id':ids['lease_id']})=={}
    assert s.direct.call(o,{**ids,'action':'browser','browser_action':'snapshot','request_id':'selected','account_id':accounts[1]})['state']=='queued'


def test_context_without_lease_reports_queue_without_allocating_or_renewing(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path,0);tid=task()
    q=s.direct.call(o,dict(action='claim',task_id=tid,holder_id='chat'))
    clock[0]+=30
    r=s.direct.call(o,dict(action='context',task_id=tid,node_id=q['node_id'],holder_id='chat'))
    assert r['state']=='queued' and r['next_action']=='end_turn_until_resources' and r['lease_id'] is None
    assert '账号' in r['reason'] and r['account_ids']==[]
    assert not c.snapshot(o)['leases'] and c.snapshot(o)['nodes'][0]['actor_seen']==1000
    with pytest.raises(PermissionError):
        s.direct.call(o,dict(action='context',task_id=tid,node_id=q['node_id'],holder_id='another'))


@pytest.mark.parametrize('operation_state,wrong_lease,expected',[
    ('not_sent',False,'blocked'),('not_sent',True,'unknown'),
    ('unknown',False,'unknown'),('pending',False,'unknown'),(None,False,'unknown'),
])
def test_command_exception_uses_only_its_durable_unsent_evidence(tmp_path,operation_state,wrong_lease,expected):
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    auth=dict(owner=o,host_id='host');rid='hidden-radio'
    command={**ids,'action':'browser','browser_action':'click','parameters':{'selector':'input'},'request_id':rid}
    s.direct.call(o,command)
    s.host_call(auth,'direct_poll',{'lease_id':ids['lease_id']})
    if operation_state:
        op={'lease_id':ids['lease_id'],'operation_id':rid,'action':'click','hash':'hash'}
        s.host_call(auth,'operation_begin',op)
        if operation_state!='pending':s.host_call(auth,'operation_complete',{**op,'state':operation_state})
        if wrong_lease:
            with c.transaction() as (_,state):
                next(v for v in state['operations'].values() if v['lease_id']==ids['lease_id'])['lease_id']='other-lease'
    result={'error':'trial: element is not visible','instruction':'unknown'}
    receipt=s.host_call(auth,'direct_result',{'lease_id':ids['lease_id'],'request_id':rid,'state':'unknown','result':result})
    assert receipt['state']==expected
    assert receipt['result']['error']==result['error']
    if expected=='blocked':
        assert receipt['result']['operation_state']=='not_sent'
        assert receipt['result']['business_failure'] is False
    else:assert receipt['result']==result
    assert s.direct.call(o,command)==receipt
    assert s.host_call(auth,'direct_poll',{'lease_id':ids['lease_id']})=={}  # No replay.


def test_late_unsent_receipt_stays_terminal_without_restoring_lease(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    auth=dict(owner=o,host_id='host');rid='hidden-radio'
    s.direct.call(o,{**ids,'action':'browser','browser_action':'click','parameters':{'selector':'input'},'request_id':rid})
    s.host_call(auth,'direct_poll',{'lease_id':ids['lease_id']})
    op={'lease_id':ids['lease_id'],'operation_id':rid,'action':'click','hash':'hash'}
    s.host_call(auth,'operation_begin',op)
    s.host_call(auth,'operation_complete',{**op,'state':'not_sent'})
    c.return_account(o,'host',dict(lease_id=ids['lease_id'],executor_stopped=True,outcome='completed',result='partial'))
    args={'lease_id':ids['lease_id'],'request_id':rid,'state':'unknown','result':{'error':'trial failed'}}
    assert s.host_call(auth,'direct_result',args)['historical']
    assert s.host_call(auth,'direct_result',args)['historical']
    receipt=s.direct.call(o,{**ids,'action':'result','request_id':rid})
    assert receipt['state']=='blocked' and receipt['result']['operation_state']=='not_sent'
    assert not c.snapshot(o)['leases']
