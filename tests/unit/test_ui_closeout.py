"""Closeout acceptance using saved synthetic receipts; no business calls."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import pytest
from api_test_tool import ui_closeout, ui_finalization, ui_records
from test_direct_execution import setup, claim_ready


def baseline(store, owner, pid):
    return ui_records.save_cases(store, owner, pid, [
        {'case_id':'A','scenario':'two observations','status':'not_run','precondition':'original initial state',
         'steps':'1. Original operation','expected':'Original expectation',
         'checkpoints':[{'id':'one','title':'first','expected':'visible'},
                        {'id':'two','title':'second','expected':'read state','depends_on':['one']}]},
        {'case_id':'B','scenario':'independent','status':'not_run'}])


def receipt(c,s,o,clock,ids,request='observed',state='completed'):
    s.direct.call(o,{**ids,'action':'browser','browser_action':'snapshot','request_id':request,'parameters':{}})
    s.host_call({'owner':o,'host_id':'host'},'direct_poll',{'lease_id':ids['lease_id']})
    clock[0]+=1
    s.host_call({'owner':o,'host_id':'host'},'direct_result',{'lease_id':ids['lease_id'],
        'request_id':request,'state':state,'result':{'snapshot':'actual synthetic page','password':'private-value'}})
    return {'case_id':'A','lease_id':ids['lease_id'],'request_id':request,'step':'first observation'}


def test_compact_finish_keeps_design_unfinished_steps_and_packages_original_receipt(tmp_path,monkeypatch):
    c,s,o,p,clock,task=setup(tmp_path)
    base=baseline(c.store,o,p['id']);ids=claim_ready(c,s,o,task())
    ref=receipt(c,s,o,clock,ids,state='unknown')
    sent=[]
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report',lambda *a:sent.append(1) or {'sent':True})
    args={'execution_id':base['execution_id'],'revision':base['revision'],'request_id':'finish',
        'cases':[{'case_id':'A','checkpoint_updates':[{'id':'one','status':'failed',
            'actual':'Observed mismatch','verification_mode':'real'}]}],
        'evidence_refs':[ref,ref], 'scene_outcome':{'status':'partial','items':[
            {'name':'test draft','state':'retained','reason':'cleanup unavailable'}]}}
    result=ui_finalization.begin(s,o,c.store.get_project(o,p['id']),args)
    assert result['pending'] and not sent
    saved=ui_records.load(c.store,o,p['id'],base['execution_id'])
    assert saved['cases'][0]['precondition']=='original initial state'
    assert saved['cases'][0]['expected']=='Original expectation'
    assert [p['status'] for p in saved['cases'][0]['checkpoints']]==['failed','not_run']
    assert saved['cases'][0]['status']=='not_run'
    assert saved['cases'][0]['checkpoints'][1]['gaps'][0]['status']=='failed'
    assert saved['cases'][1]['status']=='not_run'
    assert len(saved['assets'])==1 and saved['assets'][0]['kind']=='observation'
    evidence=json.loads((ui_records.root_for(c.store,o,p['id'],base['execution_id'])/saved['assets'][0]['id']).read_text())
    assert evidence['state']=='unknown' and 'private-value' not in json.dumps(evidence)
    s.host_call({'owner':o,'host_id':'host'},'return_account',{'lease_id':ids['lease_id'],
        'executor_stopped':True,'outcome':'completed'})
    end=ui_finalization.begin(s,o,c.store.get_project(o,p['id']),args)
    assert end['phase']=='published' and len(sent)==1
    report=c.store._read(c.store.project_dir(o,p['id'])/'analyses'/end['report']['id']/'report.json')
    assert '未执行 2' in report['summary']
    assert '1 个保留或未核实清理的现场对象' in report['summary']
    assert not any(t in report['summary'] for t in ['test draft', 'cleanup unavailable'])
    assert report['ui_snapshot']['scene_outcome']['items'][0]['reason'] == 'cleanup unavailable'
    assert saved['revision']==base['revision']+1
    assert not c.snapshot(o)['leases']


@pytest.mark.parametrize('invalid',['wrong_round','wrong_case','wrong_point','bad_evidence'])
def test_bad_reference_never_partially_saves_results_or_releases_resources(tmp_path,invalid):
    c,s,o,p,clock,task=setup(tmp_path)
    base=baseline(c.store,o,p['id']);ids=claim_ready(c,s,o,task());ref=receipt(c,s,o,clock,ids)
    updates=[{'case_id':'B','status':'blocked','actual':'missing prerequisite'}]
    if invalid=='wrong_round':
        other=c.store.create_project(o,'another','a.md','content')
        c.store.update_project(o,other['id'],{'test_kind':'ui'})
        baseline(c.store,o,other['id']);p=other;base=ui_records.load(c.store,o,p['id'],c.store.get_project(o,p['id'])['ui_execution_id']);base={'execution_id':base['id'],'revision':base['revision']}
    elif invalid=='wrong_case':ref['case_id']='missing'
    elif invalid=='wrong_point':updates=[{'case_id':'A','checkpoint_updates':[{'id':'missing','status':'blocked'}]}]
    else:updates=[{'case_id':'A','checkpoint_updates':[{'id':'one','evidence':['not-an-object']}]}]
    before=copy.deepcopy(ui_records.load(c.store,o,p['id'],base['execution_id']))
    with pytest.raises((ValueError,PermissionError)):
        ui_finalization.begin(s,o,c.store.get_project(o,p['id']),{'execution_id':base['execution_id'],
            'revision':base['revision'],'cases':updates,'evidence_refs':[ref]})
    assert ui_records.load(c.store,o,p['id'],base['execution_id'])==before
    assert c.snapshot(o)['leases']
    assert not c.store.get_project(o,p['id']).get('ui_finish_request')


def test_observation_upload_does_not_require_fixture_design_rewrite(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path);base=baseline(c.store,o,p['id'])
    payload={'case_id':'A','step':'observed','filename':'result.json','content_type':'application/json',
        'content_base64':base64.b64encode(b'{"actual":"blocked"}').decode(),'kind':'observation'}
    result=ui_records.add_assets(c.store,o,p['id'],base['execution_id'],[payload])
    assert result['created']==1
    assert ui_records.add_assets(c.store,o,p['id'],base['execution_id'],[payload])['reused']==1
    fixture=ui_records.add_assets(c.store,o,p['id'],base['execution_id'],[{**payload,'kind':'fixture'}])
    assert fixture['created']==1
    stored=ui_records.load(c.store,o,p['id'],base['execution_id'])
    assert {asset['kind'] for asset in stored['assets']}=={'observation','fixture'}
    assert {asset['case_id'] for asset in stored['assets']}=={'A'}


def test_start_files_preserve_user_results_and_contain_no_credentials(tmp_path):
    spec=importlib.util.spec_from_file_location('download_client',Path(__file__).parents[2]/'api_test_tool/static/api-test-client.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    cases=[{'case_id':'A','scenario':'original','status':'failed','actual':'old'}]
    template=ui_closeout.result_template(cases)
    prepared={'execution_id':'round','revision':1,'cases':cases,'result_template':template}
    result={'project_id':'p','prepared_execution':prepared,'execution':{'task_id':'t'},
        'claim':{'lease_id':'l','node_id':'n'},'execution_context':{'password':'do-not-copy'}}
    paths=module.prepare_round_files(tmp_path/'start.json',result,{'holder_id':'chat'})
    target=Path(paths['results.json']);value=json.loads(target.read_text())
    assert value['cases'][0]=={'case_id':'A'}
    assert target.stat().st_mode&0o777==0o600
    value['cases'][0]['actual']='new observation';target.write_text(json.dumps(value))
    module.prepare_round_files(tmp_path/'start.json',result,{'holder_id':'chat'})
    assert json.loads(target.read_text())==value
    assert 'do-not-copy' not in Path(paths['browser.json']).read_text()


def test_twenty_case_closeout_measures_only_local_platform_processing(tmp_path,monkeypatch):
    import time
    c,s,o,p,clock,task=setup(tmp_path)
    cases=[{'case_id':f'C{i}','scenario':f'synthetic {i}','status':'not_run',
            'precondition':'preserved initial state','steps':'1. original synthetic step',
            'expected':'original expectation'} for i in range(20)]
    start=time.perf_counter()
    base=ui_records.save_cases(c.store,o,p['id'],cases)
    prepared=ui_closeout.result_template(cases)
    preparation=time.perf_counter()-start
    ids=claim_ready(c,s,o,task());refs=[]
    for i in range(20):
        ref=receipt(c,s,o,clock,ids,request=f'r{i}');ref['case_id']=f'C{i}';refs.append(ref)
    # These receipts are synthetic in-process host responses, not browser work.
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report',lambda *a:{'status':'disabled','sent':False})
    updates=[{'case_id':f'C{i}','status':'blocked' if i==19 else 'passed',
              'actual':'synthetic prerequisite absent' if i==19 else 'synthetic observation'} for i in range(20)]
    args={'execution_id':base['execution_id'],'revision':base['revision'],
          'cases':updates,'evidence_refs':refs,'request_id':'one-finish'}
    start=time.perf_counter()
    pending=ui_finalization.begin(s,o,c.store.get_project(o,p['id']),args)
    assert pending['pending']
    s.host_call({'owner':o,'host_id':'host'},'return_account',{'lease_id':ids['lease_id'],
        'executor_stopped':True,'outcome':'completed'})
    end=ui_finalization.begin(s,o,c.store.get_project(o,p['id']),args)
    elapsed=time.perf_counter()-start
    saved=ui_records.load(c.store,o,p['id'],base['execution_id'])
    assert len(saved['assets'])==20
    assert saved['cases'][-1]['status']=='blocked'
    assert end['phase']=='published'
    measurement={'synthetic_cases':20,'business_operations':0,'model_calls':0,
        'external_notifications':0,'preparation_seconds':round(preparation,6),
        'finish_and_simulated_host_exit_seconds':round(elapsed,6),
        'finish_write_calls':1,'processing_timing':end['processing_timing']}
    Path('/tmp/api-test-closeout-acceptance.json').write_text(json.dumps(measurement,ensure_ascii=False,indent=2))
    print(json.dumps(measurement,ensure_ascii=False))


def test_untouched_template_does_not_reset_previously_saved_observations(tmp_path):
    c,s,o,p,clock,task=setup(tmp_path)
    base=baseline(c.store,o,p['id'])
    original=ui_records.load(c.store,o,p['id'],base['execution_id'])
    template=ui_closeout.result_template(original['cases'])
    changed=ui_records.save_cases(c.store,o,p['id'],[{'case_id':'B','status':'passed','actual':'already observed'}],base['execution_id'],base['revision'])
    ui_records.save_cases(c.store,o,p['id'],template['cases'],base['execution_id'],changed['revision'])
    saved=ui_records.load(c.store,o,p['id'],base['execution_id'])
    assert saved['cases'][1]['status']=='passed'
    assert saved['cases'][1]['actual']=='already observed'
