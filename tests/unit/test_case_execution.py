import asyncio
import copy
from types import SimpleNamespace
from api_test_tool.browser_batch import execute


def fixture():
    record={'id':'execution','revision':1,'cases':[
        {'case_id':cid,'status':'not_run','checkpoints':[{'id':'p','status':'not_run'}]}
        for cid in ['A','B']]}
    plan={'plan_id':'original-plan','cases':[{'case_id':cid,'steps':[
        {'id':'check','action':'check','parameters':{'selector':'input','expect':{'value':cid}}}],
        'checkpoints':{'p':['check']}} for cid in ['A','B']]}
    events=[]
    async def call(action,**args):
        if action=='record':return copy.deepcopy(record)
        assert action=='cases'
        events.append(('save',args['cases'][0]['case_id']))
        assert args['revision']==record['revision']
        record['revision']+=1
        return {'revision':record['revision']}
    async def operate(lid,aid,action,args,oid):
        events.append(('check',args['expect']['value']))
        return {'assertion_passed':True,'expected':args['expect'],'observed':args['expect']}
    return SimpleNamespace(call=call,operate=operate),plan,record,events


def test_default_plan_saves_each_case_before_next_without_model_callback():
    broker,plan,record,events=fixture()
    result=asyncio.run(execute(broker,'lease','account',plan,'outer'))
    assert events==[('check','A'),('save','A'),('check','B'),('save','B')]
    assert result['saved_cases']==2
    assert all(c['status']=='passed' and c['elapsed_seconds']>=c['save_seconds'] for c in result['cases'])


def test_save_failure_stops_before_next_case_and_preserves_pending_result():
    broker,plan,record,events=fixture()
    base=broker.call
    async def call(action,**args):
        if action=='cases':raise TimeoutError()
        return await base(action,**args)
    broker.call=call
    result=asyncio.run(execute(broker,'lease','account',plan,'outer'))
    assert events==[('check','A')]
    assert result['pending_save']['case_id']=='A' and result['resource_wait']['end_turn']


def test_unknown_does_not_loop_or_run_remaining_cases():
    broker,plan,record,events=fixture()
    async def operate(*args):
        events.append(('unknown','A'));raise TimeoutError()
    broker.operate=operate
    result=asyncio.run(execute(broker,'lease','account',plan,'outer'))
    assert events==[('unknown','A'),('save','A')]
    assert result['cases'][0]['status']=='partial'
    assert result['resource_wait']['end_turn']


def test_unplanned_checkpoint_is_preserved_without_blocking_independent_case():
    broker,plan,record,events=fixture()
    record['cases'][0]['checkpoints'].append({'id':'unexplored','status':'not_run'})
    result=asyncio.run(execute(broker,'lease','account',plan,'outer'))
    assert result['cases'][0]['status']=='partial'
    assert result['cases'][1]['status']=='passed' and result['saved_cases']==2


def test_already_completed_case_is_not_reexecuted():
    broker,plan,record,events=fixture()
    record['cases'][0].update(status='passed',checkpoints=[{'id':'p','status':'passed'}])
    result=asyncio.run(execute(broker,'lease','account',plan,'outer'))
    assert events==[('check','B'),('save','B')]
    assert result['cases'][0]['state']=='already_saved'


def test_native_plan_persists_through_existing_host_and_store(tmp_path):
    from api_test_tool import ui_records
    from test_direct_execution import setup, claim_ready
    c, service, owner, project, clock, task = setup(tmp_path)
    baseline = ui_records.save_cases(c.store, owner, project['id'], [
        {'case_id':cid,'scenario':'Original '+cid,'status':'not_run','steps':'Open original page',
         'checkpoints':[{'id':'p','title':'Value','expected':cid}]} for cid in ['A','B']])
    ids = claim_ready(c,service,owner,task())
    broker,plan,_,events = fixture()
    async def host(action,**args):
        return service.host_call({'owner':owner,'host_id':'host'},action,args)
    broker.call=host
    result=asyncio.run(execute(broker,ids['lease_id'],'account',plan,'outer'))
    assert result['saved_cases']==2, result
    saved=ui_records.load(c.store,owner,project['id'],baseline['execution_id'])
    assert saved['revision']==baseline['revision']+2
    assert [row['status'] for row in saved['cases']]==['passed','passed']
    assert all(row['checkpoints'][0]['verification_mode']=='real' for row in saved['cases'])
    assert saved['cases'][0]['steps']=='Open original page'


def test_identical_checkpoint_does_not_extend_progress_timeout(tmp_path):
    from test_direct_execution import setup, claim_ready
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    args={**ids,'action':'checkpoint','checkpoint':{'cursor':'A'}}
    assert s.direct.call(o,args)['changed']
    before=c.snapshot(o)['leases'][0]['progress_at']
    clock[0]+=10
    assert not s.direct.call(o,args)['changed']
    assert c.snapshot(o)['leases'][0]['progress_at']==before


def test_late_auxiliary_bind_error_does_not_revoke_exited_channel_parent(tmp_path):
    from test_direct_execution import setup, claim_ready
    c,s,o,p,clock,task=setup(tmp_path);ids=claim_ready(c,s,o,task())
    with c.transaction() as (_,state):
        state['leases'][ids['lease_id']]['auxiliary_channels']={'closed':{'state':'exited'}}
    result=s.host_call({'owner':o,'host_id':'host'},'auxiliary_bound',{
        'lease_id':ids['lease_id'],'channel_id':'closed','error':True,'error_type':'ProcessLookupError'})
    assert result=={'acknowledged':True,'exited':True}
    assert not c.snapshot(o)['leases'][0].get('revoked')
