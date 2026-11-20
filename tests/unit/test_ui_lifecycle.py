"""Local lifecycle acceptance: no browser, model or shared business environment."""
import base64
import copy
import json
import pytest
from fastapi.testclient import TestClient
from api_test_tool.web import create_app
from api_test_tool import ui_records, ui_finalization, direct_wait
from test_direct_execution import setup, claim_ready
from test_ui_testing import completed_results_xlsx
from test_platform_control import paired


def test_regression_prepares_exact_selected_design_and_creation_is_idempotent(tmp_path):
    app = create_app(tmp_path,start_fixture=False,testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token']=client.get('/api/bootstrap').json()['csrf']
        imported=client.post('/api/ui-tests/import-results',json={'filename':'old.xlsx',
            'content_base64':base64.b64encode(completed_results_xlsx()).decode(),
            'environment':'test','client':'B端'}).json()
        call=paired(client)
        args=dict(project_id=imported['project']['id'],target_url='https://example.test/ui',
                  case_ids=['W02'],request_id='regression-once')
        result=call('start_regression',**args)
        baseline=result['prepared_execution']
        assert baseline['total']==1 and baseline['revision']==1
        assert baseline['cases'][0]['case_id']=='W02'
        assert baseline['cases'][0]['status']=='not_run'
        assert baseline['cases'][0]['actual']=='' and baseline['cases'][0]['cleanup']==''
        assert call('start_regression',**args)['project_id']==result['project_id']
        record=call('ui_read',project_id=result['project_id'])
        assert record['execution_id']==baseline['execution_id']
        assert len(record['cases'])==1
        original=app.state.store._read(app.state.store.project_dir(
            next(p.name for p in (tmp_path/'sessions').iterdir()), imported['project']['id'])/
            'analyses'/imported['report']['id']/'report.json')['imported_results']['cases']
        old=next(c for c in original if c['case_id']=='W02')
        for field in ('precondition','test_data','steps','expected'):
            assert record['cases'][0][field]==old[field]
        business=client.post('/api/account-projects',json={'name':'fixture','login_url':'https://example.test/ui'}).json()
        call('managed_bind_project',project_id=imported['project']['id'],account_project_id=business['id'])
        ready=call('start_regression',**{**args,'request_id':'direct-round','holder_id':'chat'})
        assert ready['execution']['mode']=='local_browser'
        assert ready['execution']['task_id']
        repeat=call('start_regression',**{**args,'request_id':'direct-round','holder_id':'chat'})
        assert repeat['execution']['task_id']==ready['execution']['task_id']
        assert repeat['project_id']==ready['project_id']


@pytest.mark.parametrize('unknown_operation',[False,True])
def test_finish_saves_once_releases_before_report_and_preserves_summary(tmp_path,monkeypatch,unknown_operation):
    c,s,o,p,clock,task=setup(tmp_path)
    initial=ui_records.save_cases(c.store,o,p['id'],[
        {'case_id':'A','scenario':'first','status':'not_run'},
        {'case_id':'B','scenario':'remaining','status':'not_run'}])
    ids=claim_ready(c,s,o,task())
    # Complete one synthetic host receipt; timing is collected from persisted
    # commands, not additional page observations or local file scripts.
    s.direct.call(o,{**ids,'action':'browser','browser_action':'snapshot','request_id':'observe','parameters':{}})
    s.host_call({'owner':o,'host_id':'host'},'direct_poll',{'lease_id':ids['lease_id']})
    clock[0]+=1.25
    s.host_call({'owner':o,'host_id':'host'},'direct_result',{'lease_id':ids['lease_id'],
        'request_id':'observe','state':'completed','result':{'snapshot':'synthetic'}})
    if unknown_operation:
        with c.transaction() as (_,state):
            node=state['leases'][ids['lease_id']]['node_id']
            state['operations']['uncertain']={'node_id':node,'lease_id':ids['lease_id'],'state':'unknown'}
    sends=[]
    def notify(self,owner,pid,rid,kind):
        assert not c.snapshot(o)['leases']
        sends.append(rid)
        return {'status':'sent','sent':True}
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report',notify)
    args={'execution_id':initial['execution_id'],'request_id':'finish-once',
          'summary':'Partial result; original remaining case unverified',
          'revision':initial['revision'],'cases':[{'case_id':'A','status':'blocked','actual':'fixture unavailable'}],
          'scene_outcome':{'status':'partial','items':[{'name':'retained','state':'retained','reason':'evidence'}]}}
    first=ui_finalization.begin(s,o,c.store.get_project(o,p['id']),args)
    assert first['pending'] and not sends
    assert not c.store.get_project(o,p['id']).get('last_analysis')
    second=ui_finalization.begin(s,o,c.store.get_project(o,p['id']),args)
    assert second['revision']==initial['revision']+1
    s.host_call({'owner':o,'host_id':'host'},'return_account',{
        'lease_id':ids['lease_id'],'executor_stopped':True,'outcome':'completed'})
    end=ui_finalization.status(c.store.get_project(o,p['id']))
    assert end['phase']=='published' and end['execution_settlement']['released']
    assert end['tool_timing']['measured_commands']==1
    assert end['tool_timing']['median_seconds']==1.25
    assert len(sends)==1
    saved=ui_records.load(c.store,o,p['id'],initial['execution_id'])
    assert saved['revision']==initial['revision']+1
    assert [v['status'] for v in saved['cases']]==['blocked','not_run']
    report=c.store._read(c.store.project_dir(o,p['id'])/'analyses'/end['report']['id']/'report.json')
    assert report['summary']==args['summary']
    assert ui_finalization.begin(s,o,c.store.get_project(o,p['id']),args)==end
    assert len(sends)==1
    with pytest.raises(Exception,match='request_id'):
        ui_finalization.begin(s,o,c.store.get_project(o,p['id']),{**args,'summary':'different'})


def test_start_wait_keeps_original_queue_without_second_task():
    calls=[]
    def send(action,args):
        calls.append((action,args))
        if action=='start_regression':return {'project_id':'new-round','execution':{'task_id':'original-task'}}
        return {'state':'queued','lease_id':None}
    result=direct_wait.lifecycle_call_and_wait(send,'start_regression',{
        'project_id':'source','holder_id':'this-chat','request_id':'once','wait_seconds':0})
    assert [a for a,_ in calls]==['start_regression','direct_session']
    assert result['client_wait']['pending']
    assert result['client_wait']['resume_arguments']['task_id']=='original-task'


def test_later_correction_is_not_hidden_by_old_final_receipt(tmp_path):
    from api_test_tool.wecom import WeCom
    c,s,o,p,clock,task=setup(tmp_path)
    saved=ui_records.save_cases(c.store,o,p['id'],[{'case_id':'A','scenario':'case','status':'not_run'}])
    args={'execution_id':saved['execution_id'],'summary':'Actual final results'}
    first=ui_finalization.begin(s,o,c.store.get_project(o,p['id']),args)
    ui_records.save_cases(c.store,o,p['id'],[{'case_id':'A','status':'blocked','actual':'missing prerequisite'}],
                          saved['execution_id'],saved['revision'],refresh_report=False)
    project=c.store.get_project(o,p['id'])
    assert ui_finalization.status(project)['phase']=='changed'
    record=ui_records.load(c.store,o,p['id'],saved['execution_id'])
    assert not WeCom(c.store)._ui_final(o,project,record)
    corrected=ui_finalization.begin(s,o,project,args)
    assert corrected['request_id']!=first['request_id']
    assert corrected['report']['id']==first['report']['id']
    assert corrected['revision']==saved['revision']+1
    assert WeCom(c.store)._ui_final(o,c.store.get_project(o,p['id']),record)


def test_finish_wait_only_polls_status_without_repeating_write(monkeypatch):
    now=[0.]
    monkeypatch.setattr(direct_wait.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(direct_wait.time,'sleep',lambda seconds:now.__setitem__(0,now[0]+seconds))
    calls=[]
    def send(action,args):
        calls.append((action,args))
        if len(calls)<3:return {'pending':True,'request_id':'end'}
        return {'pending':False,'phase':'published','report':{'id':'real'}}
    result=direct_wait.lifecycle_call_and_wait(send,'finish_workflow',{'project_id':'p','summary':'actual','wait_seconds':5})
    assert [a for a,_ in calls]==['finish_workflow','workflow_status','workflow_status']
    assert result['phase']=='published' and result['client_wait']['elapsed_seconds']==2
    assert calls[1][1]['finalization_only']


def test_baseline_drops_historical_checkpoint_evidence_without_rewriting_steps():
    original={'case_id':'C','scenario':'test','precondition':'new blank chat','steps':'select; remove; send',
              'status':'passed','actual':'old answer','upload_attempts':[{'old':True}],
              'checkpoints':[{'id':'point','status':'passed','actual':'old',
                              'evidence':['old.png'],'correlation':{'thread':'old'}}]}
    frozen=copy.deepcopy(original)
    new=ui_records.regression_design([original])[0]
    assert original==frozen and new['steps']==original['steps']
    assert new['precondition']=='new blank chat'
    assert new['checkpoints'][0]['status']=='not_run'
    assert new['checkpoints'][0]['evidence']==[] and new['checkpoints'][0]['correlation']=={}
