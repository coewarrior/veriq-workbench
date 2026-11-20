"""Real controller / temporary store work-stage resource boundaries."""
from api_test_tool.orchestration_storage import read_metadata
import copy
import pytest

from api_test_tool import ui_records
from api_test_tool.execution_work_plan import normalize_work_plan
from api_test_tool.resource_scheduler import ResourceScheduler
from test_native_scheduler import setup as base_setup, claim
from test_native_contexts import register, environment
from test_execution_work_plan import unit
from test_ui_dependencies import case


def setup(tmp_path, **options):
    result = base_setup(tmp_path, current_protocol=True, **options)
    c, owner, _, _, tid = result
    for node in c.snapshot(owner, tid)['nodes']:
        for i in range(2):
            register(c, owner, node['id'], environment(node['id'] + '-' + str(i), True))
    return result


def install(c, owner, project, nid, units, cases):
    saved = ui_records.save_cases(c.store, owner, project['id'], cases)
    record = ui_records.load(c.store, owner, project['id'], saved['execution_id'])
    work = normalize_work_plan({'schema_version': 1, 'project_id': project['id'],
        'execution_id': record['id'], 'units': units}, record)
    with c.transaction() as (_, state):
        node = state['nodes'][nid]
        node.update(record_project_id=project['id'], record_execution_id=record['id'])
        node.setdefault('checkpoint', {})['work_plan'] = work
    return record, work


def test_busy_second_account_does_not_stall_current_work(tmp_path):
    c, owner, project, _, tid = setup(tmp_path, accounts=2, modules=2)
    nodes = c.snapshot(owner, tid)['nodes']
    first = claim(c, owner, nodes[0]['id'], 'first')
    second = claim(c, owner, nodes[1]['id'], 'second')
    a, b = first['account_ids'][0], second['account_ids'][0]
    ids = [f'A{i}' for i in range(12)]
    install(c, owner, project, nodes[0]['id'], [unit('a', ids, [a]), unit('ab', ['AB1','AB2','AB3'], [a,b])],
            [case(cid, []) for cid in [*ids, 'AB1','AB2','AB3']])
    result = c.request_resources(owner, first['id'], {'next_phase': 'execution', 'account_ids': [a,b]})
    assert result.get('next_action') == 'continue_current_work'
    assert result['runnable_case_ids'] == ids
    assert result['deferred_work_unit_id'] == 'ab'
    assert result['continued'] and not result['release_required']
    state = c.snapshot(owner, tid)
    original = next(l for l in state['leases'] if l['id'] == first['id'])
    assert original['account_ids'] == [a] and not original.get('resource_request')
    assert len(state['leases']) == 2


def test_work_boundary_token_cannot_change_full_resource_requirements(tmp_path):
    from api_test_tool.execution_work_plan import project_work_candidates
    c, owner, project, _, tid = setup(tmp_path, accounts=2, modules=2)
    nodes=c.snapshot(owner,tid)['nodes']
    first=claim(c,owner,nodes[0]['id'],'first');second=claim(c,owner,nodes[1]['id'],'second')
    a,b=first['account_ids'][0],second['account_ids'][0]
    record,work=install(c,owner,project,nodes[0]['id'],[unit('a',['A'],[a]),unit('ab',['AB'],[a,b])],
        [case('A',[]),case('AB',[])])
    candidate=project_work_candidates({'checkpoint':{'work_plan':work}},record)[1]
    token={k:candidate[k] for k in ('work_unit_id','plan_revision','requirements_digest')}
    result=c.request_resources(owner,first['id'],{'account_ids':[a],'arguments':{'work_token':token}})
    assert result.get('next_action')=='continue_current_work'
    assert result['runnable_case_ids']==['A'] and result['deferred_work_unit_id']=='ab'


def test_shared_work_continues_before_exclusive_transition(tmp_path):
    c, owner, project, _, tid = setup(tmp_path, accounts=1, modules=2, exploration=True)
    nodes = c.snapshot(owner, tid)['nodes']
    first = claim(c, owner, nodes[0]['id'], 'first')
    claim(c, owner, nodes[1]['id'], 'second')
    a = first['account_ids'][0]
    explore = unit('read', ['READ'], [a]); explore['requires']['phase'] = 'exploration'
    install(c, owner, project, nodes[0]['id'], [explore, unit('write', ['WRITE'], [a])],
            [case('READ', []), case('WRITE', [])])
    result = c.request_resources(owner, first['id'], {'next_phase':'execution', 'account_ids':[a]})
    assert result.get('next_action') == 'continue_current_work'
    assert result['runnable_case_ids'] == ['READ']
    assert next(l for l in c.snapshot(owner, tid)['leases'] if l['id']==first['id'])['mode'] == 'shared'


def test_protected_unit_cannot_be_replaced_by_new_work(tmp_path):
    c, owner, project, clock, tid = setup(tmp_path, accounts=2, modules=2)
    nodes = c.snapshot(owner, tid)['nodes']; nid = nodes[1]['id']
    busy = claim(c, owner, nodes[0]['id'], 'busy')
    a = next(a['id'] for a in c.snapshot(owner)['accounts'] if a['id'] not in busy['account_ids'])
    b = busy['account_ids'][0]
    record, work = install(c, owner, project, nid,
        [unit('ab', ['AB'], [a,b]), unit('a', ['A'], [a])], [case('AB', []),case('A', [])])
    assert hasattr(ResourceScheduler, 'select_work_candidate'), 'shared selection missing'
    with c.transaction() as (_, state):
        node=state['nodes'][nid]; scheduler=ResourceScheduler(c,state,clock[0])
        selected=scheduler.select_work_candidate(node,record,for_wake=True)
        assert selected['work_unit_id']=='a'  # AB unavailable, independent work can proceed
        candidates=__import__('api_test_tool.execution_work_plan',fromlist=['project_work_candidates']).project_work_candidates(node,record)
        ab=candidates[0]
        node.update(protected=True, work_protection={k:ab[k] for k in ('work_unit_id','plan_revision','requirements_digest','unit_digest')},
                    reservation={'accounts':[a], 'locks':[], 'until':clock[0]+60})
        selected=scheduler.select_work_candidate(node,record,for_wake=True)
        assert selected['work_unit_id']=='ab' and selected['account_ids'] is None
        before=copy.deepcopy(node['reservation']); sequence=node['queue_sequence']
        from api_test_tool.native_work_plan import update_work_plan
        extra=copy.deepcopy(work);extra['units'].append(unit('new', ['NEW'],[a]))
        record['cases'].append(case('NEW', []));record['revision']+=1
        update_work_plan(c,state,node,extra,record)
        assert node['reservation']==before and node['queue_sequence']==sequence
        assert node['work_protection']['work_unit_id']=='ab'
        assert node['work_protection']['plan_revision']==2


def test_work_views_are_transient_and_plan_does_not_hold_store_write_lock(tmp_path):
    c, owner, project, _, tid = setup(tmp_path,accounts=1,modules=1)
    nid=c.snapshot(owner,tid)['nodes'][0]['id']; aid=c.snapshot(owner)['accounts'][0]['id']
    install(c,owner,project,nid,[unit('a',['A'],[aid])],[case('A',[])])
    c.schedule()
    import json
    with c.connect() as db:
        raw=read_metadata(db)
    assert '_work_record_views' not in raw
    assert raw['nodes'][nid].get('work_selection',{}).get('work_unit_id')=='a'


def test_handoff_requires_complete_stage_resources(tmp_path):
    from test_native_handoff import environment as handoff_environment, bind_waiting_thread, consume
    c, service, owner, project, _, requests, finish=handoff_environment(tmp_path)
    bind_waiting_thread(c,requests)
    c.add_account(owner,{'project_id':project['id'],'target':'https://test.example','identity':'second','credential':''})
    accounts=[a['id'] for a in c.snapshot(owner)['accounts']]
    nid=requests[1]['node_id']
    register(c,owner,nid,environment('second-context',True))
    install(c,owner,project,nid,[unit('ab',['AB'],accounts)],[case('AB',[])])
    c.schedule()
    assert not next(n for n in c.snapshot(owner)['nodes'] if n['id']==nid)['resource_wait']['resources_available']
    released=service.direct.call(owner,finish)
    reply=consume(c,owner,finish,released['handoff'])
    notice=reply['continuation']
    assert set(notice['candidate_account_ids'])==set(accounts)
    assert notice.get('required_context_count')==2
    token=notice['claim_arguments']['arguments']['work_token']
    assert token['work_unit_id']=='ab' and token['plan_revision']==1
    assert set(notice['claim_arguments']['account_ids'])==set(accounts)
    ready=service.direct.call(owner,{**notice['claim_arguments'],'action':'context'})
    assert ready['stage_ready'] and ready['required_context_count']==2
    claimed=service.direct.call(owner,notice['claim_arguments'])
    assert claimed['lease_id'] and set(claimed['account_ids'])==set(accounts)


def test_stale_work_token_does_not_prepare_or_claim(tmp_path):
    from pathlib import Path
    from api_test_tool.managed_service import ManagedService
    from api_test_tool.orchestration import Conflict
    from api_test_tool.execution_work_plan import project_work_candidates
    c,owner,project,_,tid=setup(tmp_path,accounts=1,modules=1)
    node=c.snapshot(owner,tid)['nodes'][0];aid=c.snapshot(owner)['accounts'][0]['id']
    record,work=install(c,owner,project,node['id'],[unit('a',['A'],[aid])],[case('A',[])])
    c.schedule()
    node=c.snapshot(owner,tid)['nodes'][0]
    selected=project_work_candidates(node,record)[0]
    token={k:selected[k] for k in ('work_unit_id','plan_revision','requirements_digest')}
    service=ManagedService(c,Path(__file__).parents[2]/'api_test_tool/static')
    stale={**token,'plan_revision':0}
    args={'task_id':tid,'node_id':node['id'],'holder_id':'worker','executor_ref':'thread-worker',
          'arguments':{'work_token':stale}}
    before=c.snapshot(owner,tid)
    for action in ('context','claim'):
        with pytest.raises(Conflict):service.direct.call(owner,{**args,'action':action})
    after=c.snapshot(owner,tid)
    assert not after['leases'] and after['nodes'][0]['requirements']==before['nodes'][0]['requirements']


def test_six_modules_three_accounts_keep_one_queue_entry_and_progress(tmp_path):
    c,owner,_,_,tid=setup(tmp_path,accounts=3,modules=6)
    nodes=c.snapshot(owner,tid)['nodes'];a,b,d=[a['id'] for a in c.snapshot(owner)['accounts']]
    for i,(node,accounts) in enumerate(zip(nodes,[[a],[b],[d],[a,b],[d],[a]])):
        p=c.store.create_project(owner,'record '+str(i),'test.md','independent module')
        c.store.update_project(owner,p['id'],{'test_kind':'ui','ui_target_url':'https://test.example/login'})
        install(c,owner,p,node['id'],[unit('work',[str(i)],accounts)],[case(str(i),[])])
    active=[claim(c,owner,nodes[i]['id'],'worker'+str(i)) for i in range(3)]
    assert all(active) and len(c.snapshot(owner,tid)['leases'])==3
    for i in range(3,6):assert claim(c,owner,nodes[i]['id'],'worker'+str(i)) is None
    c.return_account(owner,active[0]['runner_id'],{'lease_id':active[0]['id'],'executor_stopped':True,
                     'browser_stopped':True,'outcome':'completed'})
    c.schedule()
    assert claim(c,owner,nodes[5]['id'],'worker5')['account_ids']==[a]
    waiting=next(n for n in c.snapshot(owner,tid)['nodes'] if n['id']==nodes[3]['id'])
    assert waiting['state']=='queued'
    assert len(c.snapshot(owner,tid)['nodes'])==6  # stages never become extra competitors
    c.control(owner,tid,{'action':'stop','revision':1,'request_id':'stop-all'})
    c.schedule()
    stopped=c.snapshot(owner,tid)
    assert stopped['tasks'][0]['intent']=='stop'
    assert all(n.get('control_intent')=='stop' for n in stopped['nodes'] if n['state']!='completed')
    assert all(l['revoked'] for l in stopped['leases'])


def test_closed_stage_can_prepare_more_contexts_without_claiming_half_bundle(tmp_path):
    from api_test_tool.native_contexts import can_prepare_for_wake
    c,owner,project,_,tid=setup(tmp_path,accounts=2,modules=1)
    nid=c.snapshot(owner,tid)['nodes'][0]['id'];accounts=[a['id'] for a in c.snapshot(owner)['accounts']]
    install(c,owner,project,nid,[unit('ab',['AB'],accounts)],[case('AB',[])])
    with c.transaction() as (_,state):
        node=state['nodes'][nid]
        keys=node['native_environment_keys'];node['native_environment_keys']=keys[:1]
        env=state['native_browser_environments'][keys[0]];env['browser']='chromium'
        node['native_browser_stopped']=True;node['executor_dispatch']={'exit_acknowledged_at':1000}
        assert can_prepare_for_wake(state,node,accounts)
        assert not state['leases']


def test_finished_stage_does_not_transfer_protection_to_another_stage(tmp_path):
    from api_test_tool.execution_work_plan import project_work_candidates
    c,owner,project,clock,tid=setup(tmp_path,accounts=2,modules=1)
    nid=c.snapshot(owner,tid)['nodes'][0]['id'];a,b=[a['id'] for a in c.snapshot(owner)['accounts']]
    record,_=install(c,owner,project,nid,[unit('ab',['AB'],[a,b]),unit('a',['A'],[a])],
                     [case('AB',[]),case('A',[])])
    with c.transaction() as (_,state):
        node=state['nodes'][nid];first=project_work_candidates(node,record)[0]
        node.update(protected=True,work_protection={k:first[k] for k in
            ('work_unit_id','plan_revision','requirements_digest','unit_digest')},
            reservation={'accounts':[a],'locks':[],'until':clock[0]+60})
    ui_records.save_cases(c.store,owner,project['id'],[{'case_id':'AB','status':'passed','actual':'实际完成'}],
                          record['id'],record['revision'])
    c.schedule()
    node=c.snapshot(owner,tid)['nodes'][0]
    assert node['work_selection']['work_unit_id']=='a'
    assert not node.get('protected') and not node.get('reservation') and not node.get('work_protection')


def test_claim_does_not_silently_switch_notified_work_stage(tmp_path):
    from pathlib import Path
    from api_test_tool.managed_service import ManagedService
    from api_test_tool.execution_work_plan import project_work_candidates
    c,owner,project,_,tid=setup(tmp_path,accounts=2,modules=2)
    nodes=c.snapshot(owner,tid)['nodes'];a,b=[a['id'] for a in c.snapshot(owner)['accounts']]
    with c.transaction() as (_,state):state['nodes'][nodes[0]['id']]['requested_account_ids']=[b]
    assert claim(c,owner,nodes[0]['id'],'busy')['account_ids']==[b]
    nid=nodes[1]['id']
    record,_=install(c,owner,project,nid,[unit('ab',['AB'],[a,b]),unit('a',['A'],[a])],
                     [case('AB',[]),case('A',[])])
    node=next(n for n in c.snapshot(owner,tid)['nodes'] if n['id']==nid)
    candidate=project_work_candidates(node,record)[0]
    token={k:candidate[k] for k in ('work_unit_id','plan_revision','requirements_digest')}
    service=ManagedService(c,Path(__file__).parents[2]/'api_test_tool/static')
    result=service.direct.call(owner,{'action':'claim','task_id':tid,'node_id':nid,'holder_id':'worker',
        'executor_ref':'thread:worker','account_ids':[a,b],'arguments':{'work_token':token}})
    assert not result['lease_id']  # B became busy after the original AB notification
    assert len(c.snapshot(owner,tid)['leases'])==1


def test_running_claim_cannot_replace_stage_under_existing_lease(tmp_path):
    from pathlib import Path
    from api_test_tool.managed_service import ManagedService
    from api_test_tool.execution_work_plan import project_work_candidates
    from api_test_tool.orchestration import Conflict
    c,owner,project,_,tid=setup(tmp_path,accounts=2,modules=1)
    nid=c.snapshot(owner,tid)['nodes'][0]['id']
    a,b=[x['id'] for x in c.snapshot(owner)['accounts']]
    record,_=install(c,owner,project,nid,[unit('a',['A'],[a]),unit('ab',['AB'],[a,b])],
                     [case('A',[]),case('AB',[])])
    service=ManagedService(c,Path(__file__).parents[2]/'api_test_tool/static')
    node=c.snapshot(owner,tid)['nodes'][0]
    tokens=[{k:x[k] for k in ('work_unit_id','plan_revision','requirements_digest')}
            for x in project_work_candidates(node,record)]
    args={'action':'claim','task_id':tid,'node_id':nid,'holder_id':'worker','executor_ref':'thread:worker'}
    first=service.direct.call(owner,{**args,'account_ids':[a],'arguments':{'work_token':tokens[0]}})
    assert first['account_ids']==[a]
    before=c.snapshot(owner,tid)
    with pytest.raises(Conflict,match='阶段|资源边界'):
        service.direct.call(owner,{**args,'account_ids':[a,b],'arguments':{'work_token':tokens[1]}})
    after=c.snapshot(owner,tid)
    assert after['leases']==before['leases']
    assert after['nodes'][0]['work_selection']==before['nodes'][0]['work_selection']
    same=service.direct.call(owner,{**args,'account_ids':[a],'arguments':{'work_token':tokens[0]}})
    assert same['lease_id']==first['lease_id'] and same['account_ids']==[a]


def test_stage_preflight_keeps_notified_stage_when_an_earlier_stage_becomes_available(tmp_path):
    from pathlib import Path
    from api_test_tool.managed_service import ManagedService
    from api_test_tool.execution_work_plan import project_work_candidates
    c,owner,project,_,tid=setup(tmp_path,accounts=2,modules=1)
    nid=c.snapshot(owner,tid)['nodes'][0]['id']
    a,b=[x['id'] for x in c.snapshot(owner)['accounts']]
    record,_=install(c,owner,project,nid,[unit('ab',['AB'],[a,b]),unit('a',['A'],[a])],
                     [case('AB',[]),case('A',[])])
    node=c.snapshot(owner,tid)['nodes'][0]
    selected=project_work_candidates(node,record)[1]
    token={k:selected[k] for k in ('work_unit_id','plan_revision','requirements_digest')}
    service=ManagedService(c,Path(__file__).parents[2]/'api_test_tool/static')
    result=service.direct.call(owner,{'action':'context','task_id':tid,'node_id':nid,
        'holder_id':'worker','executor_ref':'thread:worker','arguments':{'work_token':token}})
    assert result['stage_ready'] and result['account_ids']==[a]
    assert result['work_token']==token and result['runnable_case_ids']==['A']


def test_old_stage_notification_cannot_borrow_other_stages_protection(tmp_path):
    from pathlib import Path
    from api_test_tool.managed_service import ManagedService
    from api_test_tool.execution_work_plan import project_work_candidates
    from api_test_tool.orchestration import Conflict
    c,owner,project,clock,tid=setup(tmp_path,accounts=2,modules=1)
    nid=c.snapshot(owner,tid)['nodes'][0]['id'];a,b=[x['id'] for x in c.snapshot(owner)['accounts']]
    record,_=install(c,owner,project,nid,[unit('ab',['AB'],[a,b]),unit('a',['A'],[a])],
                     [case('AB',[]),case('A',[])])
    with c.transaction() as (_,state):
        node=state['nodes'][nid];ab,single=project_work_candidates(node,record)
        node.update(protected=True,work_protection={k:ab[k] for k in ('work_unit_id','plan_revision','requirements_digest','unit_digest')},
                    reservation={'accounts':[a],'locks':[],'until':clock[0]+60})
    token={k:single[k] for k in ('work_unit_id','plan_revision','requirements_digest')}
    args={'task_id':tid,'node_id':nid,'holder_id':'worker','executor_ref':'thread:worker','arguments':{'work_token':token}}
    service=ManagedService(c,Path(__file__).parents[2]/'api_test_tool/static')
    assert not service.direct.call(owner,{**args,'action':'context'})['stage_ready']
    with pytest.raises(Conflict):service.direct.call(owner,{**args,'action':'claim','account_ids':[a]})
    assert c.snapshot(owner,tid)['nodes'][0]['work_protection']['work_unit_id']=='ab'


def test_unsent_continuation_refresh_updates_complete_stage_binding(tmp_path):
    from test_native_handoff import environment as handoff_environment,bind_waiting_thread,consume
    from api_test_tool.native_handoff import continuation
    c,service,owner,project,_,requests,finish=handoff_environment(tmp_path)
    bind_waiting_thread(c,requests)
    a=c.snapshot(owner)['accounts'][0]['id']
    c.add_account(owner,{'project_id':project['id'],'target':'https://test.example','identity':'second','credential':''})
    b=next(x['id'] for x in c.snapshot(owner)['accounts'] if x['id']!=a)
    busy=c.create_task(owner,{'project_id':project['id'],'request_id':'busy','goal':'fixture',
        'execution_route':'native_browser','session_workflow':True,'modules':[{'key':'busy','title':'busy','requirements':[]}]})
    busy_nid=c.snapshot(owner,busy['task_id'])['nodes'][0]['id']
    with c.transaction() as (_,state):
        state['tasks'][busy['task_id']]['native_browser_policy']='legacy_reported'
        state['nodes'][busy_nid].update(requested_account_ids=[b],phase='execution')
        state['nodes'][busy_nid].pop('native_context_protocol',None)
    busy_lease=claim(c,owner,busy_nid,'busy')
    nid=requests[1]['node_id'];register(c,owner,nid,environment('extra',True))
    install(c,owner,project,nid,[unit('ab',['AB'],[a,b]),unit('a',['A'],[a])],[case('AB',[]),case('A',[])])
    released=service.direct.call(owner,finish)
    notice=consume(c,owner,finish,released['handoff'])['continuation']
    assert notice['claim_arguments']['arguments']['work_token']['work_unit_id']=='a'
    c.return_account(owner,busy_lease['runner_id'],{'lease_id':busy_lease['id'],
        'executor_stopped':True,'browser_stopped':True,'outcome':'completed','result':'partial'})
    with c.transaction(work_records=True) as (_,state):
        event=state['nodes'][finish['node_id']]['native_handoffs'][finish['lease_id']]
        current=event['continuations'][0]
        continuation(c,state,state['tasks'][finish['task_id']],{**event,'continuation':current})
        assert current['claim_arguments']['arguments']['work_token']['work_unit_id']=='ab'
        assert set(current['claim_arguments']['account_ids'])==set(current['candidate_account_ids'])=={a,b}
        assert current['required_context_count']==2
