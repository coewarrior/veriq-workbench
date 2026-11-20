from concurrent.futures import ThreadPoolExecutor
import copy

from pg_support import full_state
from api_test_tool.storage_migrate import current_payload

import pytest
from fastapi.testclient import TestClient

from api_test_tool.orchestration import Controller, Conflict, DEFAULTS
from api_test_tool.web_storage import Store
from api_test_tool.web import create_app
from api_test_tool.mcp_access import MCPAccess


@pytest.fixture
def setup(tmp_path):
    store=Store(tmp_path)
    session,_=store.session(None)
    owner=session['id']
    project=store.create_project(owner,'test','test.md','test')
    now=[1000.0]
    ctl=Controller(store,lambda:now[0])
    return ctl,owner,project['id'],now


def requirement(role='user'):
    return dict(target='https://test.example',environment='test',tenant='tenant',role=role)


def create(ctl,owner,pid,key='create',modules=None,**kwargs):
    return ctl.create_task(owner,dict(project_id=pid,request_id=key,goal='test modules',
        modules=modules or [dict(key='one',title='one',requirements=[requirement()])],**kwargs))


def account(ctl,owner,pid,identity='first',roles=None,pool='execution'):
    a=ctl.add_account(owner,dict(project_id=pid,target='https://test.example',environment='test',tenant='tenant',
        identity=identity,roles=roles or ['user'],pool=pool,credential='private-test-credential'))
    ctl.verify_account(owner,a['id'],identity=identity,tenant='tenant')
    return a['id']


def host(ctl,owner,slots=8):
    ctl.register_host(owner,'host',enforcement_evidence=dict(network_isolation='fixture',credential_isolation='fixture',
        tool_gate='fixture',browser_context_isolation='fixture',version='fixture'),browser_slots=slots,model_slots=slots)


def started(ctl,owner):
    ctl.schedule()
    events=ctl.pending_events(owner,'host')
    event=next(e for e in events if e['kind']=='start')
    ctl.acknowledge_start(owner,event['id'],thread_id='thread-'+event['id'],turn_id='turn-'+event['id'])
    return event


SAFETY=dict(executor_fenced='verified',inflight_reconciled='verified',scene_verified='verified')


def test_idempotent_create_is_atomic_and_payload_conflicts(setup):
    ctl,owner,pid,_=setup
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:create(ctl,owner,pid),range(20)))
    assert len({r['task_id'] for r in results})==1
    with pytest.raises(Conflict):
        create(ctl,owner,pid,mode='design')
    assert len(ctl.snapshot(owner)['tasks'])==1


def test_no_host_never_allocates_or_claims_execution(setup):
    ctl,owner,pid,_=setup
    account(ctl,owner,pid)
    create(ctl,owner,pid)
    assert ctl.schedule()==[]
    snap=ctl.snapshot(owner)
    assert not snap['execution_ready'] and not snap['leases']
    assert snap['nodes'][0]['result']=='not_run'


def credential_session(ctl, owner, pid, count=1):
    ctl.store.update_project(owner,pid,{'ui_target_url':'https://test.example/login'})
    return create(ctl,owner,pid,modules=[dict(key=str(i),title=str(i),requirements=[],resource_planning=True)
                                       for i in range(count)])


def credential_host(ctl, owner, slots=8, supported=True):
    ctl.register_host(owner,'host',enforcement_evidence=dict(network_isolation='fixture',credential_isolation='fixture',
        tool_gate='fixture',browser_context_isolation='fixture',version='fixture',automatic_configuration=1,
        credential_execution=int(supported)),browser_slots=slots,model_slots=slots)


def test_password_accounts_allocate_without_manual_login_and_remain_exclusive(setup):
    ctl,owner,pid,_=setup
    for i in range(3):
        ctl.add_account(owner,dict(project_id=pid,target='https://test.example',identity=str(i),credential='fixture-password'))
    credential_host(ctl,owner)
    credential_session(ctl,owner,pid,5)
    with ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(lambda _:ctl.schedule(),range(5)))
    snap=ctl.snapshot(owner)
    assert len(snap['leases'])==3
    assert len({aid for l in snap['leases'] for aid in l['account_ids']})==3
    assert all(l['mode']=='exclusive' and l['browser_units']==1 for l in snap['leases'])
    assert sum(n['state']=='queued' for n in snap['nodes'])==2
    assert all(not a['verified_identity'] and not a['tenant'] and not a['roles'] for a in snap['accounts'])
    assert 'fixture-password' not in str(snap)


def test_credential_dispatch_needs_supported_host_and_browser_capacity(setup):
    ctl,owner,pid,_=setup
    ctl.add_account(owner,dict(project_id=pid,target='https://test.example',identity='one',credential='fixture-password'))
    credential_session(ctl,owner,pid)
    credential_host(ctl,owner,supported=False)
    assert ctl.schedule()==[]
    credential_host(ctl,owner,slots=0)
    assert ctl.schedule()==[]
    credential_host(ctl,owner,slots=1)
    assert len(ctl.schedule())==1


def test_only_live_exclusive_executor_can_read_assigned_password(setup):
    from pathlib import Path
    from api_test_tool.managed_service import ManagedService
    ctl,owner,pid,_=setup
    a=ctl.add_account(owner,dict(project_id=pid,target='https://test.example',identity='one',credential='fixture-password'))
    credential_host(ctl,owner)
    task=credential_session(ctl,owner,pid)
    ctl.schedule();event=ctl.pending_events(owner,'host')[0]
    service=ManagedService(ctl,Path(__file__).parents[2]/'api_test_tool/static')
    auth={'owner':owner,'host_id':'host'}
    args={'lease_id':event['lease_id'],'account_id':a['id']}
    with pytest.raises(Conflict):service.host_call(auth,'account_credentials',args)
    ctl.acknowledge_start(owner,event['id'],thread_id='fixture-thread',turn_id='fixture-turn')
    assert service.host_call(auth,'account_credentials',args)['password']=='fixture-password'
    with pytest.raises(PermissionError):service.host_call(auth,'account_credentials',{**args,'account_id':'not-assigned'})
    with pytest.raises(PermissionError):service.host_call({**auth,'host_id':'another'},'account_credentials',args)
    ctl.control(owner,task['task_id'],dict(action='stop',revision=1,request_id='stop-credential'))
    with pytest.raises(Conflict):service.host_call(auth,'account_credentials',args)
    assert len(ctl.snapshot(owner)['leases'])==1  # Stop never frees an unconfirmed scene.


def test_role_requirements_still_require_observed_identity(setup):
    ctl,owner,pid,_=setup
    ctl.add_account(owner,dict(project_id=pid,target='https://test.example',environment='test',tenant='tenant',
        identity='one',roles=['user'],credential='fixture-password'))
    credential_host(ctl,owner)
    create(ctl,owner,pid)
    assert ctl.schedule()==[]


def test_exclusive_grants_survive_restart_and_duplicate_host_events(setup):
    ctl,owner,pid,now=setup
    aid=account(ctl,owner,pid)
    host(ctl,owner)
    create(ctl,owner,pid,'one');create(ctl,owner,pid,'two')
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _:ctl.schedule(),range(10)))
    assert len(ctl.snapshot(owner)['leases'])==1
    restarted=Controller(ctl.store,lambda:now[0])
    restarted.schedule()
    assert len(restarted.snapshot(owner)['leases'])==1
    assert restarted.snapshot(owner)['leases'][0]['account_ids']==[aid]
    now[0]+=61
    restarted.schedule()
    assert restarted.snapshot(owner)['nodes'][0]['state']=='isolated'
    assert len(restarted.snapshot(owner)['leases'])==1


def test_stop_wins_over_late_start_and_stale_resume(setup):
    ctl,owner,pid,_=setup
    account(ctl,owner,pid);host(ctl,owner)
    task=create(ctl,owner,pid);ctl.schedule()
    event=ctl.pending_events(owner,'host')[0]
    ctl.control(owner,task['task_id'],dict(action='stop',revision=1,request_id='stop'))
    with pytest.raises(Conflict):
        ctl.acknowledge_start(owner,event['id'],thread_id='late',turn_id='late')
    with pytest.raises(Conflict):
        ctl.control(owner,task['task_id'],dict(action='resume',revision=1,request_id='old-resume'))
    assert ctl.active_count()==1
    assert all(e['kind']!='start' for e in ctl.pending_events(owner,'host'))


def test_multi_role_matching_does_not_take_only_admin_for_user(setup):
    ctl,owner,pid,_=setup
    a=account(ctl,owner,pid,'flexible',['user','admin'])
    b=account(ctl,owner,pid,'limited',['user'])
    host(ctl,owner)
    create(ctl,owner,pid,modules=[dict(key='roles',title='roles',requirements=[requirement(),requirement('admin')])])
    ctl.schedule()
    assert set(ctl.snapshot(owner)['leases'][0]['account_ids'])=={a,b}


def test_machine_capacity_counts_each_identity_context(setup):
    ctl,owner,pid,_=setup
    account(ctl,owner,pid,'a',['admin']);account(ctl,owner,pid,'b',['user']);host(ctl,owner,1)
    create(ctl,owner,pid,modules=[dict(key='roles',title='roles',requirements=[requirement(),requirement('admin')])])
    assert ctl.schedule()==[]
    ctl.host_heartbeat(owner,'host',2,1)
    assert len(ctl.snapshot(owner)['leases'])==1


def test_shared_exploration_requires_policy_and_has_distinct_contexts(setup):
    ctl,owner,pid,_=setup
    aid=account(ctl,owner,pid,pool='exploration');host(ctl,owner)
    policy=ctl.approve_policy(owner,pid,aid,version='1',operations={'read':{'effect':'verified_read','adapter':'fixture'}},evidence='verified locally')
    modules=[dict(key=str(i),title=str(i),requirements=[requirement()],shared_policy=policy) for i in range(3)]
    create(ctl,owner,pid,modules=modules)
    ctl.schedule()
    leases=ctl.snapshot(owner)['leases']
    assert len(leases)==3 and all(l['mode']=='shared' for l in leases)
    assert len({l['context_id'] for l in leases})==3
    event=ctl.pending_events(owner,'host')[0]
    ctl.acknowledge_start(owner,event['id'],thread_id='thread',turn_id='turn')
    lease=next(l for l in leases if l['id']==event['lease_id'])
    with pytest.raises(PermissionError):
        ctl.authorize_operation(owner,lease['id'],'unsafe','delete',{},adapter='fixture',epoch=lease['epoch'],revision=lease['revision'])
    ctl.revoke_policy(owner,policy)
    assert all(l['revoked'] for l in ctl.snapshot(owner)['leases'])


def test_last_explorer_pool_conversion_never_frees_other_explorers(setup):
    ctl,owner,pid,_=setup
    aid=account(ctl,owner,pid,pool='exploration');host(ctl,owner)
    policy=ctl.approve_policy(owner,pid,aid,version='1',operations={'read':{'effect':'verified_read','adapter':'fixture'}},evidence='local')
    create(ctl,owner,pid,modules=[dict(key=str(i),title=str(i),requirements=[requirement()],shared_policy=policy) for i in range(2)])
    ctl.schedule();leases=ctl.snapshot(owner)['leases']
    ctl.release(owner,leases[0]['id'],checkpoint={},safety=SAFETY,next_phase='execution')
    assert ctl.snapshot(owner)['accounts'][0]['pool']=='exploration'
    assert ctl.schedule()==[]
    ctl.release(owner,leases[1]['id'],checkpoint={},safety=SAFETY,next_phase='execution')
    assert ctl.snapshot(owner)['accounts'][0]['pool']=='execution'
    ctl.schedule()
    assert len(ctl.snapshot(owner)['leases'])==1


def test_unknown_operation_is_never_replayed_or_released(setup):
    ctl,owner,pid,_=setup
    account(ctl,owner,pid);host(ctl,owner);create(ctl,owner,pid)
    e=started(ctl,owner);l=ctl.snapshot(owner)['leases'][0]
    args=dict(adapter='fixture',epoch=l['epoch'],revision=l['revision'])
    assert ctl.authorize_operation(owner,l['id'],'op','submit',{},**args)['dispatch']
    assert not ctl.authorize_operation(owner,l['id'],'op','submit',{},**args)['dispatch']
    ctl.operation_result(owner,'op',state='unknown',result={'reason':'lost response'})
    with pytest.raises(Conflict):
        ctl.release(owner,l['id'],checkpoint={},safety=SAFETY)
    with pytest.raises(Conflict):
        ctl.begin_recovery(owner,e['node_id'],'retry','fault')
    assert ctl.active_count()==1


def test_recovery_budget_shared_by_split_and_success_never_resets(setup):
    ctl,owner,pid,now=setup
    create(ctl,owner,pid)
    n=ctl.snapshot(owner)['nodes'][0]
    ids=ctl.split(owner,n['id'],dict(revision=1,children=[dict(title='a',scope='a'),dict(title='b',scope='b')]))['child_ids']
    for i in range(6):
        nid=ids[i%2]
        assert ctl.begin_recovery(owner,nid,str(i),'fault-'+str(i))['start']
        now[0]+=10
        ctl.finish_recovery(owner,nid,str(i),recovered=True)
    with pytest.raises(Conflict):
        ctl.begin_recovery(owner,ids[0],'seven','new-fault')
    b=ctl.snapshot(owner)['budgets'][n['id']]
    assert b['attempts']==6 and b['seconds']==60


def test_recovery_time_aggregates_parallel_attempts_and_denies_stopped(setup):
    ctl,owner,pid,now=setup
    t=create(ctl,owner,pid);n=ctl.snapshot(owner)['nodes'][0]
    ctl.begin_recovery(owner,n['id'],'one','fault')
    now[0]+=1200
    with pytest.raises(Conflict):
        ctl.begin_recovery(owner,n['id'],'two','fault')
    ctl.schedule()
    assert ctl.snapshot(owner)['nodes'][0]['state']=='isolated'
    ctl.control(owner,t['task_id'],dict(action='stop',revision=1,request_id='stop'))
    with pytest.raises(Conflict):
        ctl.begin_recovery(owner,n['id'],'new','fault2')


def test_human_timeouts_create_notices_never_free_scene(setup):
    ctl,owner,pid,now=setup
    account(ctl,owner,pid);host(ctl,owner);create(ctl,owner,pid)
    e=started(ctl,owner)
    ctl.wait_human(owner,e['lease_id'],checkpoint={},reason='扫码')
    now[0]+=1801
    ctl.host_heartbeat(owner,'host',8,8)
    snap=ctl.snapshot(owner)
    assert {n['kind'] for n in snap['notices']}=={'human_reminder','human_review'}
    assert len(snap['leases'])==1


def test_incomplete_pass_rejected_and_retry_keeps_failure(setup):
    ctl,owner,pid,_=setup
    account(ctl,owner,pid);host(ctl,owner);create(ctl,owner,pid)
    e=started(ctl,owner)
    with pytest.raises(ValueError):
        ctl.release(owner,e['lease_id'],checkpoint={},safety=SAFETY,result='passed',completed=True)
    ctl.release(owner,e['lease_id'],checkpoint={},safety=SAFETY,result='failed',coverage_complete=True)
    e=started(ctl,owner)
    ctl.release(owner,e['lease_id'],checkpoint={},safety=SAFETY,result='passed',coverage_complete=True,completed=True)
    n=ctl.snapshot(owner)['nodes'][0]
    assert n['result']=='retry_passed'
    assert [x['result'] for x in n['outcome_history']]==['failed','passed']


def test_only_design_never_advances_to_execution(setup):
    ctl,owner,pid,_=setup
    account(ctl,owner,pid);host(ctl,owner);create(ctl,owner,pid,mode='design')
    e=started(ctl,owner)
    with pytest.raises(PermissionError):
        ctl.release(owner,e['lease_id'],checkpoint={},safety=SAFETY,next_phase='execution')


def test_private_account_deduplication_and_encrypted_credentials(setup):
    ctl,owner,pid,_=setup
    aid=account(ctl,owner,pid)
    second=ctl.store.create_project(owner,'second','second.md','second')['id']
    assert account(ctl,owner,second)==aid
    assert len(ctl.snapshot(owner)['accounts'])==1
    with ctl.connect() as db:
        stored = full_state(db)
    assert 'private-test-credential' not in str(stored)
    assert 'credential' not in str(ctl.snapshot(owner))
    other,_=ctl.store.session(None)
    assert ctl.snapshot(other['id'])['accounts']==[]


def test_web_mcp_share_receipts_scope_and_no_secret_route(tmp_path):
    app=create_app(tmp_path,testing=True,start_fixture=False)
    with TestClient(app) as c:
        bootstrap=c.get('/api/bootstrap').json()
        csrf=bootstrap['csrf']
        owner=app.state.store.session(c.cookies['api_test_session'])[0]['id']
        pid=app.state.store.create_project(owner,'test','test.md','test')['id']
        access=MCPAccess(app.state.store)
        token=access.redeem(access.issue(owner)['code'])['token']
        scoped=access.redeem(access.issue(owner,project_ids=[pid])['code'])['token']
        args=dict(project_id=pid,goal='test',request_id='same',modules=[dict(key='one',title='one')])
        first=c.post('/api/orchestration/tasks',json=args,headers={'x-csrf-token':csrf})
        assert first.status_code==200
        second=c.post('/api/mcp/call',json={'action':'managed_create','arguments':args},headers={'authorization':'Bearer '+token})
        assert second.status_code==200 and second.json()==first.json()
        assert c.post('/api/mcp/call',json={'action':'managed_status','arguments':{}},headers={'authorization':'Bearer '+scoped}).status_code==403
        assert c.post('/api/orchestration/tasks',json=args).status_code==403
        assert c.get('/orchestration').status_code==200
        assert c.post('/api/orchestration/register_host',json={},headers={'x-csrf-token':csrf}).status_code==404
        assert c.get('/api/orchestration').json()['summary']['total']==1


def test_stop_before_dispatch_reclaims_only_never_delivered_lease(setup):
    ctl,owner,pid,_=setup
    account(ctl,owner,pid);host(ctl,owner)
    task=create(ctl,owner,pid);ctl.schedule()
    ctl.control(owner,task['task_id'],dict(action='stop',revision=1,request_id='stop'))
    assert ctl.active_count()==0
    assert ctl.snapshot(owner)['nodes'][0]['state']=='stopped'


def test_reservation_deadline_not_renewed_and_same_evidence_cannot_loop(setup):
    ctl,owner,pid,now=setup
    aid=account(ctl,owner,pid)
    create(ctl,owner,pid,modules=[dict(key='both',title='both',requirements=[requirement(),requirement('admin')])])
    n=ctl.snapshot(owner)['nodes'][0]
    with ctl.transaction() as (_,s):
        s['nodes'][n['id']]['protected']=True
    first=ctl.reserve(owner,n['id'],[aid],release_evidence='observed-closeout-1')
    now[0]+=60
    assert ctl.reserve(owner,n['id'],[aid],release_evidence='observed-closeout-1')==first
    now[0]+=61;ctl.schedule()
    assert ctl.snapshot(owner)['nodes'][0]['reservation'] is None
    with pytest.raises(Conflict):
        ctl.reserve(owner,n['id'],[aid],release_evidence='observed-closeout-1')
    ctl.reserve(owner,n['id'],[aid],release_evidence='observed-closeout-2')
    now[0]+=121;ctl.schedule()
    with pytest.raises(Conflict):
        ctl.reserve(owner,n['id'],[aid],release_evidence='observed-closeout-3')


def test_dependency_cycle_rejected_and_read_does_not_mutate(setup):
    ctl,owner,pid,_=setup
    with pytest.raises(ValueError):
        create(ctl,owner,pid,modules=[dict(key='a',title='a',depends_on=['b']),dict(key='b',title='b',depends_on=['a'])])
    create(ctl,owner,pid)
    with ctl.connect() as db:
        before = current_payload(db)
    ctl.snapshot(owner)
    with ctl.connect() as db:
        assert current_payload(db) == before


def test_fixture_consumer_release_does_not_delete_other_consumers(setup):
    ctl,owner,pid,_=setup
    create(ctl,owner,pid,modules=[dict(key='a',title='a'),dict(key='b',title='b')])
    a,b=ctl.snapshot(owner)['nodes']
    f=ctl.fixture(owner,a['id'],dict(object_id='object-1',version='v1'))
    ctl.fixture(owner,b['id'],dict(id=f['id'],version='v1'))
    f=ctl.fixture(owner,a['id'],dict(id=f['id'],action='release'))
    assert f['consumers']==[b['id']] and f['state']=='available'


def test_bootstrap_lists_ui_and_api_without_model_secrets(tmp_path):
    app=create_app(tmp_path,testing=True,start_fixture=False)
    with TestClient(app) as c:
        c.get('/api/orchestration/bootstrap')
        owner=app.state.store.session(c.cookies['api_test_session'])[0]['id']
        api=app.state.store.create_project(owner,'API','api.md','api')
        ui=app.state.store.create_project(owner,'UI','ui.md','ui')
        app.state.store.update_project(owner,ui['id'],{'test_kind':'ui'})
        result=c.get('/api/orchestration/bootstrap').json()
        assert {p['id'] for p in result['projects']}=={api['id'],ui['id']}
        assert all(set(p)=={'id','title','test_kind'} for p in result['projects'])
        assert 'model' not in result and result['csrf']
