"""Actual Apache JMeter against disposable loopback services; no paid/shared targets."""
import copy
import json
import threading
import time
import xml.etree.ElementTree as ET
import pytest
from api_test_tool.jmeter_engine import configuration,selected_cases,write_plan,run_jmeter
from test_items_integration import items_bundle,ItemsServer,environment
from test_execution import local_api,bundle,step,status
from test_web_api import client,_wait,_import_items


def config(**extra):return configuration({'enabled':True,'virtual_users':2,'duration_seconds':15,'ramp_up_seconds':0,'max_rounds':2,'think_time_ms':0,**extra})


def test_jmeter_plan_accepts_scale_beyond_builtin_and_rejects_unsupported_semantics(tmp_path,items_bundle):
    assert config(virtual_users=10000)['virtual_users']==10000
    with pytest.raises(ValueError):config(ramp_up_seconds=20)
    original=copy.deepcopy(items_bundle)
    write_plan(items_bundle,{'base_url':'http://example.test','name':'test'},tmp_path,config(),['ITEM-FLOW-001'],['127.0.0.1'])
    assert items_bundle==original
    root=ET.parse(tmp_path/'plan.jmx').getroot()
    assert len(root.findall('.//HTTPSamplerProxy'))==6
    assert root.find('.//stringProp[@name="StaticHost.Name"]').text=='example.test'
    assert not root.findall('.//stringProp[@name="script"]')[0].text
    bad=copy.deepcopy(items_bundle);bad['web']={'trusted_cleanup':'gomoku'}
    with pytest.raises(ValueError,match='数据库清理'):selected_cases(bad,['ITEM-FLOW-001'])
    bad=copy.deepcopy(items_bundle)
    bad['cases'][0]['steps'][0]['assertions'].append({'kind':'json_schema','rule_id':bad['cases'][0]['rule_ids'][0],'expected':{'type':'string','format':'email'}})
    with pytest.raises(ValueError,match='format'):selected_cases(bad,[bad['cases'][0]['id']])


def test_real_jmeter_token_chains_schema_cleanup_and_pinned_dns(items_bundle,tmp_path):
    with ItemsServer() as server:
        env=environment(server);env['base_url']=env['base_url'].replace('127.0.0.1','jmeter-fixture.invalid')
        r=run_jmeter(items_bundle,env,tmp_path,config(virtual_users=32,max_rounds=32),case_ids=['ITEM-FLOW-001'],addresses=['127.0.0.1'])
        assert r['engine_status']=='completed',r
        assert r['requests_sent']==192 and r['requests_failed']==0
        assert r['rounds_finished']==r['rounds_passed']==32 and not server.items
        assert sum(p['requests'] for p in r['series'])==192
        assert '<svg' in (tmp_path/'index.html').read_text()
        assert (tmp_path/'jmeter'/'plan.zip').is_file()
        for token in server.tokens:assert token not in (tmp_path/'result.json').read_text()


def test_real_jmeter_cookie_header_variables_and_explicit_no_session(local_api,tmp_path):
    env,seen=local_api
    login=step('login','/session',json={'username':'tester'})
    login['request']['method']='POST'
    login['assertions'] += [{'kind':'cookie_present','name':'SSID','rule_id':'R-1'}]
    login['extract']=[{'name':'token','from':'header','key':'X-Access-Token'}]
    who=step('who','/who',headers={'Authorization':'Bearer ${token}'},assertions=[status(),{'kind':'json_equal','pointer':'/username','expected':'tester','rule_id':'R-1'}])
    anonymous=step('anonymous','/who',session=False,assertions=[status(),{'kind':'json_equal','pointer':'/username','expected':None,'rule_id':'R-1'}])
    plan=bundle(login,who,anonymous)
    r=run_jmeter(plan,env,tmp_path,config(virtual_users=1,max_rounds=1),case_ids=['C-1'])
    assert r['engine_status']=='completed' and r['requests_failed']==0,r
    assert len(seen)==3 and seen[1]['cookie']=='SSID=test-cookie-secret'
    assert seen[1]['authorization']=='Bearer test-token-secret' and seen[2]['cookie'] is None
    assert 'test-token-secret' not in (tmp_path/'result.json').read_text()


def test_real_jmeter_failed_assertion_skips_dependencies_but_cleans(local_api,tmp_path):
    env,seen=local_api
    plan=bundle(step('fail','/echo',assertions=[status(201)]),step('skip','/should-not-run'))
    plan['cases'][0]['cleanup_steps']=[step('cleanup','/cleanup')]
    r=run_jmeter(plan,env,tmp_path,config(virtual_users=1,max_rounds=1),case_ids=['C-1'])
    assert [s['path'] for s in seen]==['/echo','/cleanup']
    assert r['requests_sent']==2 and r['requests_failed']==1
    assert r['engine_status']=='completed' and r['rounds_passed']==0


def test_real_jmeter_stop_finishes_current_chain(local_api,tmp_path):
    env,seen=local_api;stop=threading.Event()
    plan=bundle(step('first','/echo'),step('next','/next'))
    plan['cases'][0]['cleanup_steps']=[step('cleanup','/cleanup')]
    def cancel():
        deadline=time.monotonic()+10
        while not seen and time.monotonic()<deadline:time.sleep(.01)
        stop.set()
    thread=threading.Thread(target=cancel);thread.start()
    try:r=run_jmeter(plan,env,tmp_path,config(virtual_users=1,max_rounds=1000),case_ids=['C-1'],stop=stop)
    finally:thread.join(timeout=12)
    assert r['requests_sent']>=3 and r['requests_sent']%3==0
    assert seen[-1]['path']=='/cleanup' and r['cleanup_failures']==0
    assert '用户停止' in r['stop_reason'] and r['engine_status']=='completed'


def test_jmeter_web_job_report_and_private_artifact_access(client):
    pid=_import_items(client);_wait(client,client.post(f'/api/projects/{pid}/generate',json={'mode':'baseline'}))
    job=_wait(client,client.post(f'/api/projects/{pid}/load-test',json={'environment':'items','case_ids':['ITEM-FLOW-001'],'load':{'enabled':True,**config()}}))
    entry=job['result'];assert entry['engine']=='jmeter' and entry['engine_status']=='completed'
    assert 'Apache JMeter' in client.get(entry['report_url']).text
    url=f'/api/projects/{pid}/jmeter-artifacts/{entry["id"]}/plan.zip'
    assert client.get(url).status_code==200
    from fastapi.testclient import TestClient
    with TestClient(client.app) as other:
        assert other.get(url).status_code in (401,403,404)
    assert client.get(url.replace('plan.zip','jmeter.log')).status_code==404
