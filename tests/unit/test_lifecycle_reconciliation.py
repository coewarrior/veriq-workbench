"""Isolated regression of the actual direct/Runner entry points; no business I/O."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from api_test_tool.browser_policy import BrowserPolicy, ExclusiveRequired
from api_test_tool.managed_runner import Runner
from api_test_tool.managed_browser import ManagedBrowser
from api_test_tool.orchestration import Conflict
from test_direct_execution import setup, claim_ready


def test_browser_ready_never_fabricates_codex_or_business_ack(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path)
    tid=task()
    receipt=s.direct.call(o,dict(action='claim',holder_id='worker',task_id=tid,executor_ref='thread:actual'))
    event=c.pending_events(o,'host')[0]
    s.host_call({'owner':o,'host_id':'host'},'browser_ready',{'lease_id':receipt['lease_id'],'event_id':event['id']})
    node=c.snapshot(o)['nodes'][0]
    assert not node.get('thread_id') and not node.get('business_started_at')
    assert node['executor_dispatch']['executor_ref']=='thread:actual'
    status=s.direct.call(o,dict(action='claim',holder_id='worker',task_id=tid))
    assert status['browser_ready'] and not status['business_started']
    auth={'owner':o,'host_id':'host'}
    operation={'lease_id':receipt['lease_id'],'operation_id':'first-page','action':'navigate','hash':'original'}
    s.host_call(auth,'operation_begin',operation)
    s.host_call(auth,'operation_complete',{**operation,'state':'confirmed','result':{'url':'https://test.example/app'}})
    assert c.snapshot(o)['nodes'][0]['business_started_at']==clock[0]


def test_stop_ack_is_attached_to_existing_executor_finish(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);tid=task()
    ids=claim_ready(c,s,o,tid)
    c.control(o,tid,dict(action='stop',revision=1,request_id='stop'))
    response=s.direct.call(o,{**ids,'action':'finish'})
    assert response['authority_revoked'] and not response['released']
    node=c.snapshot(o)['nodes'][0]
    assert all(x['state']=='exited' for x in node['executor_controls'].values())
    with pytest.raises(Conflict):s.direct.call(o,{**ids,'action':'credentials'})


def test_finish_held_resources_returns_terminal_fact_without_wait_loop(tmp_path):
    from api_test_tool.direct_wait import direct_call_and_wait
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    s.host_call({'owner':o,'host_id':'host'},'operation_begin',dict(lease_id=ids['lease_id'],operation_id='unknown-write',action='click',hash='same'))
    s.direct.call(o,{**ids,'action':'finish','outcome':'blocked'})
    held=c.return_account(o,'host',dict(lease_id=ids['lease_id'],executor_stopped=True,outcome='blocked'))
    assert held['retained']
    response=direct_call_and_wait(lambda args:s.direct.call(o,args),{**ids,'action':'finish'})
    assert response['state']=='isolated' and response['execution_ended'] and response['retained']
    assert response['client_wait']['http_calls']==1 and not response['client_wait']['pending']


def test_resolved_hold_delivers_new_release_receipt_before_second_local_ack(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    lid=ids['lease_id'];auth={'owner':o,'host_id':'host'}
    s.host_call(auth,'operation_begin',dict(lease_id=lid,operation_id='preparation',action='prepare_exploration',hash='same'))
    s.direct.call(o,{**ids,'action':'finish','outcome':'blocked'})
    request=dict(lease_id=lid,executor_stopped=True,browser_stopped=True,outcome='blocked')
    held=c.return_account(o,'host',request)
    assert held['retained']
    heartbeat=dict(browser_slots=4,model_slots=1,settlement_acks=[lid])
    assert not s.host_call(auth,'heartbeat',heartbeat)['settlement_updates']
    (tmp_path/'runner').mkdir()
    runner=Runner(tmp_path/'runner',None,SimpleNamespace(),headed=False,max_browsers=0,max_models=0)
    runner.remember(lid,phase='settled',return_request=request,settlement=held,ack_reported=True)
    node=next(n for n in c.snapshot(o)['nodes'] if n['id']==held['node_id'])
    s.resolve(o,lid,{'operations':{node['id']+':preparation':'confirmed'},'scene_verified':True,'evidence':'Known cancelled verification; original browser and worker have exited.'})
    update=s.host_call(auth,'heartbeat',{**heartbeat,'settlement_acks':[]})['settlement_updates']
    assert len(update)==1 and update[0]['released']
    runner.receive_settlement_updates(update)
    assert runner.journal[lid]['settlement']['released'] and not runner.journal[lid]['ack_reported']
    final=s.host_call(auth,'heartbeat',heartbeat)
    assert final['settlement_acks']==[lid] and not final['settlement_updates']
    assert not c.snapshot(o)['leases']


def test_late_observation_never_rebinds_or_reopens_task(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);tid=task();ids=claim_ready(c,s,o,tid)
    auth={'owner':o,'host_id':'host'}
    operation={'lease_id':ids['lease_id'],'operation_id':'old-write','action':'click','hash':'original'}
    s.host_call(auth,'operation_begin',operation)
    # Compatibility with a previously retired lease whose response arrives late.
    with c.transaction() as (_,state):
        lease=state['leases'].pop(ids['lease_id'])
        node=state['nodes'][lease['node_id']];node.update(state='stopped',revision=node['revision']+1)
    answer=s.host_call(auth,'operation_complete',{**operation,'state':'confirmed','result':{'receipt':'old-object'}})
    assert answer['historical'] and not answer['authority_restored']
    assert not c.snapshot(o)['leases'] and c.snapshot(o)['nodes'][0]['state']=='stopped'
    with pytest.raises(PermissionError):s.host_call({'owner':o,'host_id':'another'},'operation_complete',{**operation,'state':'confirmed','result':{}})


def test_claim_additional_locks_cannot_erase_inherited_lock(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);tid=task()
    with c.transaction() as (_,state):state['nodes'][state['tasks'][tid]['node_ids'][0]]['locks']=['tenant-config']
    s.direct.call(o,dict(action='claim',holder_id='worker',task_id=tid,locks=['own-object']))
    assert c.snapshot(o)['nodes'][0]['locks']==['tenant-config','own-object']


def test_shared_policy_is_local_and_checks_saved_fields():
    policy=BrowserPolicy({'target':'https://test.example'},dict(enabled=True,version='v1',rules=[
        {'origin':'https://test.example','path':'/list','method':'GET','effect':'verified_read','query_equals':{'tab':'mine'}},
        {'origin':'https://test.example','path':'/draft','method':'POST','effect':'isolated_write','namespace_field':'namespace','body_patterns':{'title':'.{1,30}'}},
    ]),'private-namespace')
    assert policy.request('https://test.example/list?tab=mine','GET')=='verified_read'
    assert policy.request('https://test.example/draft','POST',{'namespace':'private-namespace','title':'ours'})=='isolated_write'
    for url,method,body in [
        ('https://test.example/list?tab=all','GET',None),
        ('https://test.example/draft','POST',{'namespace':'other','title':'not ours'}),
        ('https://test.example/delete','POST',{}),
    ]:
        with pytest.raises(ExclusiveRequired):policy.request(url,method,body)


def test_recovery_has_durable_fault_budget_and_never_retries_sent_work(tmp_path,monkeypatch):
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    api=SimpleNamespace(call=lambda action,**args:s.host_call({'owner':o,'host_id':'host'},action,args))
    (tmp_path/'runner').mkdir()
    runner=Runner(tmp_path/'runner',api,SimpleNamespace(),headed=False,max_browsers=0,max_models=0)
    monkeypatch.setattr(asyncio,'sleep',AsyncMock())
    for _ in range(2):
        rid=asyncio.run(runner.recover_unstarted(ids['lease_id'],'one-fault'))
        assert rid
        s.host_call({'owner':o,'host_id':'host'},'recover_finish',dict(lease_id=ids['lease_id'],recovery_id=rid,recovered=False))
    with pytest.raises(Conflict):asyncio.run(runner.recover_unstarted(ids['lease_id'],'one-fault'))
    s.host_call({'owner':o,'host_id':'host'},'operation_begin',dict(lease_id=ids['lease_id'],operation_id='submitted',action='click',hash='same'))
    assert asyncio.run(runner.recover_unstarted(ids['lease_id'],'another-fault')) is None


def test_only_explicit_live_scene_preserves_browser():
    context={'lease':{},'node':{'state':'running'}}
    assert not Runner.retain_browser(context,{'scene_outcome':{'status':'retained'}})
    assert Runner.retain_browser(context,{'retain_scene':True})
    assert not Runner.retain_browser({'lease':{'resolution_requested':True},'node':{'state':'retained'}},{'retain_scene':True})


def test_real_runner_registration_advertises_implemented_shared_broker(tmp_path):
    received={}
    def call(action,**arguments):
        assert action=='register'
        received.update(arguments)
        runner.stopping=True
        return {'simple_dispatch':1}
    runner=Runner(tmp_path,SimpleNamespace(call=call),SimpleNamespace(prepare=lambda:{'version':'fixture'},close=lambda:None),headed=False,max_browsers=0,max_models=0)
    runner.browser.start=AsyncMock();runner.browser.check_runtime=AsyncMock();runner.browser.close=AsyncMock()
    runner.capacity=lambda:(4,4)
    asyncio.run(runner.run())
    assert received['evidence']['shared_exploration']==1
    assert received['evidence']['direct_execution']==1
    runner.browser.check_runtime.assert_awaited_once()


def test_background_executor_routes_optional_resource_tools_through_original_lease(tmp_path):
    import json
    import queue
    from unittest.mock import Mock
    events=queue.Queue()
    arguments=[('request_resources',{'next_phase':'execution'}),
               ('test_record',{'action':'shared_policy','arguments':{'rules':[],'session_compatible':True}}),
               ('checkpoint',{'checkpoint':{'next':'original-progress'},'finish':True})]
    for index,(tool,args) in enumerate(arguments):
        events.put({'method':'item/tool/call','id':index,'params':{'threadId':'thread','turnId':'turn','tool':tool,'arguments':args}})
    events.put({'method':'turn/completed','params':{'turn':{'id':'turn'}}})
    server=SimpleNamespace(closed=False,events=events,start_thread=Mock(return_value='thread'),
                           start_turn=Mock(return_value='turn'),close=lambda:None,tool_response=Mock())
    sandbox=SimpleNamespace(stop=lambda _:None,open=lambda _:server,cwd=lambda _:'/tmp',model=None)
    runner=Runner(tmp_path,None,sandbox,headed=False,max_browsers=1,max_models=1)
    ctx={'lease':{'id':'l','runner_id':'host','revoked':False,'mode':'shared'},
         'node':{'id':'n','title':'test','checkpoint':{}},'dispatch':{'id':'e'}}
    calls=[]
    async def call(action,**args):
        calls.append((action,args))
        return ctx if action=='read' else {'saved':True}
    runner.call=call;runner.browser=SimpleNamespace(bind=AsyncMock(),fence=AsyncMock())
    asyncio.run(runner.execute({'lease_id':'l'}))
    assert ('request_resources',{'next_phase':'execution','lease_id':'l'}) in calls
    assert ('shared_policy',{'rules':[],'session_compatible':True,'lease_id':'l'}) in calls
    assert all(receipt.args[-1] is True for receipt in server.tool_response.call_args_list)
    prompt=server.start_turn.call_args.args[1]
    assert json.loads(prompt.split('\n',1)[1])['context']['lease']['mode']=='shared'
    assert 'request_resources' in {tool['name'] for tool in server.start_thread.call_args.kwargs['tools']}
    assert len([action for action,args in calls if action=='return_account'])==1


def test_ordinary_browser_operation_keeps_original_two_rpc_path(tmp_path):
    broker=ManagedBrowser(SimpleNamespace(),tmp_path)
    broker.active['lease']={'mode':'exclusive','revoked':False}
    broker.call=AsyncMock(side_effect=[{'execute':True,'mode':'exclusive'},{'saved':True}])
    broker._operate=AsyncMock(return_value={'url':'https://external-login.example/continue','snapshot':'actual'})
    result=asyncio.run(broker.operate('lease','account','navigate',{'url':'https://external-login.example/continue'},'original-operation'))
    assert result['snapshot']=='actual'
    assert [c.args[0] for c in broker.call.call_args_list]==['operation_begin','operation_complete']
    broker._operate.assert_awaited_once()


@pytest.mark.parametrize('mode',['exclusive','shared'])
def test_only_shared_browser_installs_local_policy(tmp_path,mode):
    from unittest.mock import Mock
    context=SimpleNamespace(route=AsyncMock(),route_web_socket=AsyncMock(),new_page=AsyncMock(return_value=object()),set_default_navigation_timeout=lambda value:None)
    browser=SimpleNamespace(new_context=AsyncMock(return_value=context))
    broker=ManagedBrowser(SimpleNamespace(),tmp_path)
    broker.playwright=SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
    broker._remember_processes=lambda *args:None
    broker.call=AsyncMock(side_effect=AssertionError('bind must not add remote validation'))
    asyncio.run(broker.bind({'lease':{'id':'lease','mode':mode,'context_id':'context','revoked':False},
                            'accounts':[{'id':'account','target':'https://test.example'}],
                            'shared_policy':{'enabled':True,'rules':[]}}))
    assert context.route.await_count==(1 if mode=='shared' else 0)
    assert context.route_web_socket.await_count==(1 if mode=='shared' else 0)
    assert broker.call.await_count==0
    if mode=='shared':
        socket=SimpleNamespace(close=AsyncMock(),connect_to_server=Mock())
        handler=context.route_web_socket.call_args.args[1]
        asyncio.run(handler(socket))
        socket.close.assert_awaited_once()
        socket.connect_to_server.assert_not_called()
        broker.active['lease']['mode']='exclusive'
        asyncio.run(handler(socket))
        socket.connect_to_server.assert_called_once()
