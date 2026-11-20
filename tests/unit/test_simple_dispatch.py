"""Simple dispatch contracts, using local storage and fake browsers only."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from api_test_tool.orchestration import Controller, Conflict
from api_test_tool.web_storage import Store
from api_test_tool.managed_browser import ManagedBrowser
from api_test_tool.managed_runner import Runner


def environment(tmp_path, accounts=1, tasks=2):
    store=Store(tmp_path);session,_=store.session(None);owner=session['id']
    p=store.create_project(owner,'test','test.md','test')
    store.update_project(owner,p['id'],{'ui_target_url':'https://test.example/login'})
    clock=[1000.];c=Controller(store,lambda:clock[0])
    for i in range(accounts):c.add_account(owner,dict(project_id=p['id'],target='https://test.example',identity=str(i),credential=''))
    c.register_host(owner,'host',enforcement_evidence=dict(network_isolation='fixture',credential_isolation='fixture',tool_gate='fixture',browser_context_isolation='fixture',version='fixture',simple_dispatch=1),browser_slots=3,model_slots=3)
    ids=[]
    for i in range(tasks):
        ids.append(c.create_task(owner,dict(project_id=p['id'],request_id=str(i),goal='test',modules=[dict(key=str(i),title=str(i),requirements=[])])))
    return c,owner,ids,clock


def test_assign_without_login_identity_or_password_and_yield_to_queue_tail(tmp_path):
    c,o,tasks,clock=environment(tmp_path,3,5)
    c.schedule();s=c.snapshot(o)
    assert len(s['leases'])==3
    assert len({a for l in s['leases'] for a in l['account_ids']})==3
    assert all(not a['verified_identity'] and not a['roles'] for a in s['accounts'])
    lease=s['leases'][0]
    request=dict(lease_id=lease['id'],executor_stopped=True,outcome='yield',checkpoint={'step':'preserved'})
    assert c.return_account(o,'host',request)['released']
    assert c.return_account(o,'host',request)['released'] # lost response
    c.schedule();s=c.snapshot(o)
    resumed={l['node_id'] for l in s['leases']}
    fourth=next(n for n in s['nodes'] if n['task_id']==tasks[3]['task_id'])
    assert fourth['id'] in resumed and lease['node_id'] not in resumed
    assert next(n for n in s['nodes'] if n['id']==lease['node_id'])['checkpoint']['step']=='preserved'


def test_return_keeps_unknown_operation_isolated_until_original_result_is_known(tmp_path):
    c,o,tasks,_=environment(tmp_path);c.schedule();lease=c.snapshot(o)['leases'][0]
    with c.transaction() as (_,s):
        s['operations']['old']={'id':'old','lease_id':lease['id'],'node_id':lease['node_id'],'state':'unknown','action':'click'}
    req=dict(lease_id=lease['id'],executor_stopped=True,outcome='blocked',reason='Login rejected')
    with pytest.raises(PermissionError):c.return_account(o,'other',req)
    with pytest.raises(Conflict):c.return_account(o,'host',{**req,'executor_stopped':False})
    assert len(c.snapshot(o)['leases'])==1
    c.return_account(o,'host',req);c.schedule();snap=c.snapshot(o)
    assert len(snap['leases'])==1 and snap['leases'][0]['node_id']==lease['node_id']
    assert snap['leases'][0]['resource_hold'] and snap['leases'][0]['browser_units']==0
    assert snap['operations'][0]['state']=='unknown'
    with c.connect() as db:
        import json
        op=json.loads(db.execute('SELECT value FROM state').fetchone()[0])['operations']['old']
    assert op['state']=='unknown' and not op.get('historical')
    with c.transaction() as (_,s):
        s['operations']['old'].update(state='not_sent',result={'evidence':'原动作未发出'})
    assert c.resolve_resource_hold(o,lease['id'],'已核实原动作未发出且无保留条件')['released']
    c.schedule()
    assert c.snapshot(o)['leases'][0]['node_id']!=lease['node_id']


def test_completed_does_not_mean_passed_and_pause_returns_account(tmp_path):
    c,o,tasks,_=environment(tmp_path);c.schedule();l=c.snapshot(o)['leases'][0]
    c.return_account(o,'host',dict(lease_id=l['id'],executor_stopped=True,outcome='completed',result='passed',coverage_complete=False))
    assert next(n for n in c.snapshot(o)['nodes'] if n['id']==l['node_id'])['result']=='partial'
    c.schedule();event=c.pending_events(o,'host')[0];c.acknowledge_start(o,event['id'],thread_id='thread',turn_id='turn')
    c.control(o,tasks[1]['task_id'],dict(action='pause',revision=1,request_id='pause'))
    c.return_account(o,'host',dict(lease_id=event['lease_id'],executor_stopped=True,outcome='yield'))
    assert not c.snapshot(o)['leases']
    assert next(n for n in c.snapshot(o)['nodes'] if n['task_id']==tasks[1]['task_id'])['state']=='paused'


def test_split_returns_account_and_queues_children(tmp_path):
    c,o,_,_=environment(tmp_path,tasks=1);c.schedule();l=c.snapshot(o)['leases'][0]
    c.return_account(o,'host',dict(lease_id=l['id'],executor_stopped=True,children=[{'title':'one','scope':'one'},{'title':'two','scope':'two'}]))
    s=c.snapshot(o);assert not s['leases']
    assert sum(n['state']=='queued' for n in s['nodes'])==2
    c.schedule();assert len(c.snapshot(o)['leases'])==1


def test_resume_unfinished_coverage_keeps_original_thread_record_and_history(tmp_path):
    c,o,tasks,clock=environment(tmp_path,tasks=2);c.schedule()
    event=c.pending_events(o,'host')[0]
    c.acknowledge_start(o,event['id'],thread_id='original',turn_id='first')
    c.return_account(o,'host',dict(lease_id=event['lease_id'],executor_stopped=True,
        outcome='completed',result='failed',coverage_complete=False,checkpoint={'evidence':'preserved'}))
    before=next(n for n in c.snapshot(o)['nodes'] if n['task_id']==tasks[0]['task_id'])
    clock[0]+=10
    request=dict(action='resume',revision=1,request_id='continue',instruction='Only finish missing assertions')
    c.control(o,tasks[0]['task_id'],request)
    assert c.control(o,tasks[0]['task_id'],request)['revision']==2
    after=next(n for n in c.snapshot(o)['nodes'] if n['id']==before['id'])
    assert after['state']=='queued' and after['thread_id']=='original'
    assert after['checkpoint']=={**before['checkpoint'],'user_continuation':'Only finish missing assertions'}
    assert after['outcome_history']==before['outcome_history'] and after['result']=='failed'
    c.schedule();assert c.snapshot(o)['leases'][0]['node_id']!=after['id']


def test_resume_does_not_replay_completed_coverage(tmp_path):
    c,o,tasks,_=environment(tmp_path,tasks=1);c.schedule();l=c.snapshot(o)['leases'][0]
    c.return_account(o,'host',dict(lease_id=l['id'],executor_stopped=True,outcome='completed',result='failed',coverage_complete=True))
    c.control(o,tasks[0]['task_id'],dict(action='resume',revision=1,request_id='continue'))
    c.schedule();assert not c.snapshot(o)['leases']
    assert c.snapshot(o)['nodes'][0]['state']=='completed'


def test_browser_normal_network_and_locator_failure_does_not_revoke(tmp_path):
    async def run():
        calls=[]
        def receipt(method,**args):
            assert method in {'operation_begin','operation_complete'} # No policy/login approval.
            calls.append((method,args));return {'execute':True}
        api=SimpleNamespace(call=receipt)
        b=ManagedBrowser(api,tmp_path)
        locator=SimpleNamespace(click=AsyncMock(side_effect=RuntimeError('missing')),aria_snapshot=AsyncMock(return_value='page'))
        page=SimpleNamespace(url='https://test.example',locator=lambda _:locator,title=AsyncMock(return_value='test'))
        ctx=SimpleNamespace(new_page=AsyncMock(return_value=page),set_default_navigation_timeout=lambda _:None,pages=[page],storage_state=AsyncMock(side_effect=RuntimeError('cannot save cookies')),close=AsyncMock())
        browser=SimpleNamespace(new_context=AsyncMock(return_value=ctx),close=AsyncMock())
        b.playwright=SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        await b.bind({'lease':{'id':'lease','context_id':'ctx','revoked':False},'accounts':[{'id':'account'}]})
        b.playwright.chromium.launch.assert_awaited_once_with(headless=True)
        browser.new_context.assert_awaited_once_with(accept_downloads=True)
        with pytest.raises(RuntimeError):await b.operate('lease','account','click',{'selector':'missing'})
        assert not b.active['lease']['revoked']
        assert calls[-1][1]['state']=='not_sent' # Missing locator never sent a click.
        for url in ('file:///private/credentials','javascript:alert(1)','https://user:pass@test.example'):
            with pytest.raises(ValueError):await b.operate('lease','account','navigate',{'url':url})
        assert (await b.operate('lease','account','snapshot',{}))['snapshot']=='page'
        await b.fence('lease');browser.close.assert_awaited_once();assert not b.active
    asyncio.run(run())


def test_read_failure_after_completed_turn_still_returns_account(tmp_path):
    async def run():
        import queue
        from unittest.mock import Mock
        events=queue.Queue()
        events.put({'method':'item/tool/call','id':1,'params':{'threadId':'thread','turnId':'turn','tool':'checkpoint','arguments':{'checkpoint':{},'finish':True,'completed':True}}})
        events.put({'method':'turn/completed','params':{'turn':{'id':'turn'}}})
        server=SimpleNamespace(closed=False,events=events,start_thread=lambda **_: 'thread',start_turn=lambda *_:'turn',close=lambda:None,tool_response=Mock())
        sandbox=SimpleNamespace(stop=lambda _:None,open=lambda _:server,cwd=lambda _:'/tmp',model=None)
        runner=Runner(tmp_path,None,sandbox,headed=False,max_browsers=1,max_models=1)
        ctx={'lease':{'id':'l','runner_id':'host','revoked':False},'node':{'id':'n','title':'test','checkpoint':{}},'dispatch':{'id':'e'}}
        reads=0;returns=[]
        async def call(method,**args):
            nonlocal reads
            if method=='read':
                reads+=1
                if reads>1:raise RuntimeError('report unavailable')
                return ctx
            if method=='publish':raise RuntimeError('report unavailable')
            if method=='return_account':returns.append(args)
            return {}
        runner.call=call;runner.browser=SimpleNamespace(bind=AsyncMock(),fence=AsyncMock())
        await runner.execute({'lease_id':'l'})
        assert len(returns)==1 and returns[0]['outcome']=='completed'
        assert returns[0]['result']=='partial'
        runner.browser.fence.assert_awaited_once_with('l')
    asyncio.run(run())


def test_runner_returns_validation_detail_without_request_or_html(monkeypatch):
    from api_test_tool.managed_runner import HostAPI
    monkeypatch.setattr('api_test_tool.managed_runner.requests.post',lambda *a,**kw:SimpleNamespace(status_code=400,json=lambda:{'detail':'检查点依赖不存在'}))
    with pytest.raises(RuntimeError,match='检查点依赖不存在') as e:HostAPI('https://platform.example','secret').call('cases',private='request-secret')
    assert 'secret' not in str(e.value)
    monkeypatch.setattr('api_test_tool.managed_runner.requests.post',lambda *a,**kw:SimpleNamespace(status_code=503,json=lambda:[]))
    with pytest.raises(RuntimeError,match='HTTP 503'):HostAPI('https://platform.example').call('record')


def test_no_accounts_keeps_automatic_task_in_background_queue(tmp_path):
    from api_test_tool.managed_service import ManagedService
    from api_test_tool.managed_workflow import ManagedWorkflow
    c,o,tasks,_=environment(tmp_path,accounts=0,tasks=1)
    pid=c.snapshot(o)['tasks'][0]['project_id']
    workflow=ManagedWorkflow(ManagedService(c,tmp_path))
    assert workflow.status(o,pid)['execution_mode']=='managed'
    c.schedule();assert c.snapshot(o)['nodes'][0]['state']=='queued'


def test_upload_reads_only_current_task_asset_with_exact_bytes(tmp_path,monkeypatch):
    import base64
    from api_test_tool.managed_service import ManagedService
    c,o,_,_=environment(tmp_path);c.schedule();event=c.pending_events(o,'host')[0]
    c.acknowledge_start(o,event['id'],thread_id='thread',turn_id='turn')
    svc=ManagedService(c,tmp_path)
    svc.report_project=lambda *args:{'id':'project','ui_execution_id':'execution'}
    blob=b'original invalid PNG\x00\xff'
    (tmp_path/'fixture').write_bytes(blob)
    monkeypatch.setattr('api_test_tool.managed_service.ui_records.load',lambda *a:{'assets':[{'id':'fixture','filename':'bad.png','content_type':'application/octet-stream'}]})
    monkeypatch.setattr('api_test_tool.managed_service.ui_records.root_for',lambda *a:tmp_path)
    auth={'owner':o,'host_id':'host'};args={'lease_id':event['lease_id'],'asset_id':'fixture'}
    result=svc.host_call(auth,'asset_content',args)
    assert base64.b64decode(result['content_base64'])==blob
    with pytest.raises(PermissionError):svc.host_call(auth,'asset_content',{**args,'asset_id':'../another-file'})
    with pytest.raises(PermissionError):svc.host_call({**auth,'host_id':'other'},'asset_content',args)
    async def upload():
        b=ManagedBrowser(None,tmp_path)
        b.active['l']={'revoked':False}
        locator=SimpleNamespace(set_input_files=AsyncMock(),aria_snapshot=AsyncMock(return_value='uploaded'))
        page=SimpleNamespace(url='https://test.example',locator=lambda _:locator,title=AsyncMock(return_value='test'))
        b.pages['l','a']=page;b.contexts['l','a']=SimpleNamespace(pages=[page])
        b.call=AsyncMock(side_effect=lambda method,**args: {'execute':True} if method=='operation_begin' else result)
        uploaded=await b.operate('l','a','upload',{'selector':'input[type=file]','asset_id':'fixture'})
        assert uploaded['submitted_file']['content_type']=='image/png'
        assert uploaded['submitted_file']['size']==len(blob)
        locator.set_input_files.assert_awaited_once_with({'name':'bad.png','mimeType':'image/png','buffer':blob})
    asyncio.run(upload())


def test_resume_keeps_history_on_server_without_full_control_response():
    from api_test_tool.codex_appserver import AppServer
    server=object.__new__(AppServer)
    def call(method,args):
        assert method=='thread/resume'
        assert args['excludeTurns'] is True
        assert 'history' not in args # Preserve original stored history.
        return {'thread':{'id':args['threadId'],'status':{'type':'idle'}}}
    server.call=call
    assert server.resume_thread('original-thread')['thread']['status']['type']=='idle'
