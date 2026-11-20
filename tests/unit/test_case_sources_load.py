"""Four case sources and opt-in load runs against isolated local services."""
import copy
import json
import threading
import time

import pytest
import requests
from fastapi.testclient import TestClient

from api_test_tool.case_import import candidates_from_bundle, import_candidates
from api_test_tool.load_testing import load_config, run_load
from test_web_api import client, _wait, _import_items
from test_items_integration import items_bundle, ItemsServer, environment


def details(c, pid):
    return c.get(f'/api/projects/{pid}').json()


def upload(c, pid, cases, **extra):
    return c.post(f'/api/projects/{pid}/import-cases', json={
        'filename': 'cases.json', 'content': json.dumps({'cases': cases}),
        'revision': details(c, pid)['bundle_revision'], **extra})


def source_cases(items_bundle):
    return candidates_from_bundle(items_bundle)['cases']


def test_own_import_review_real_chain_execution_and_edit(client, items_bundle):
    pid = _import_items(client)
    assert client.put(f'/api/projects/{pid}/case-workflow',json={'mode':'own'}).status_code == 200
    assert client.post(f'/api/projects/{pid}/generate',json={'mode':'baseline'}).status_code == 400
    raw = next(c for c in source_cases(items_bundle) if c['id']=='ITEM-FLOW-001')
    raw['state']='READY';raw['web']={'approval_eligible':True,'source':'ai'}
    response=upload(client,pid,[raw]);assert response.status_code==200,response.text
    case=response.json()['bundle']['cases'][0]
    assert case['state']=='NEEDS_RULE' and case['web']['source']=='user' and case['web']['approval_eligible']
    approved=client.post(f'/api/projects/{pid}/approve',json={'case_ids':[raw['id']]})
    assert approved.status_code==200,approved.text
    run=_wait(client,client.post(f'/api/projects/{pid}/run',json={'environment':'items'}))['result']
    assert run['summary']['PASS']==1 and run['summary']['complete']
    evidence=client.get(run['report_url'].replace('index.html','result.json')).json()
    chain=evidence['cases'][0]
    assert [s['response']['status'] for s in chain['steps']]==[200,201,200,409]
    assert [s['response']['status'] for s in chain['cleanup']['steps']]==[204,404]
    # Editing returns the changed case to review and leaves immutable evidence intact.
    raw.pop('state');raw.pop('web');raw['title']='用户修改后的链路'
    response=upload(client,pid,[raw],replace_id=raw['id'])
    assert response.status_code==200,response.text
    assert response.json()['bundle']['cases'][0]['state']=='NEEDS_RULE'
    assert client.get(run['report_url'].replace('index.html','result.json')).json()==evidence
    assert not response.json()['project'].get('load_runs')


@pytest.mark.parametrize('mode',['import_ai','ai_import'])
def test_append_generated_or_import_preserves_user_baseline(client,items_bundle,mode):
    pid=_import_items(client)
    raw=source_cases(items_bundle)[0];raw['id']='MY-BASELINE'
    assert client.put(f'/api/projects/{pid}/case-workflow',json={'mode':mode}).status_code==200
    if mode=='ai_import':_wait(client,client.post(f'/api/projects/{pid}/generate',json={'mode':'baseline'}))
    response=upload(client,pid,[raw]);assert response.status_code==200,response.text
    assert client.post(f'/api/projects/{pid}/approve',json={'case_ids':['MY-BASELINE']}).status_code==200
    original=next(c for c in details(client,pid)['bundle']['cases'] if c['id']=='MY-BASELINE')
    _wait(client,client.post(f'/api/projects/{pid}/generate',json={'mode':'baseline'}))
    current=details(client,pid)['bundle']['cases']
    assert next(c for c in current if c['id']=='MY-BASELINE')==original
    assert len(current)>1 and any(c['web']['source']=='rules' for c in current)
    assert len({c['id'] for c in current})==len(current)


def test_import_conflict_stale_revision_and_invalid_file_are_atomic(client,items_bundle):
    pid=_import_items(client);raw=source_cases(items_bundle)[0]
    assert upload(client,pid,[raw]).status_code==200
    before=details(client,pid)['bundle']
    assert upload(client,pid,[raw]).status_code==400
    assert upload(client,pid,[raw],revision='outdated').status_code==409
    for content in ['{bad','null','[]','{"cases":[null]}']:
        assert upload(client,pid,[],content=content).status_code==400
    assert details(client,pid)['bundle']==before


def test_csv_import_preserves_explicit_expectation_without_inventing_one(items_bundle):
    c,b=import_candidates(items_bundle['contract'],'用例.csv',
        '编号,用例名称,请求方法,接口路径,预期状态码\nOWN-1,不存在的资源,GET,/items/{id},404\nOWN-2,待补充预期,GET,/items/{id},\n')
    assert b['cases'][0]['steps'][0]['assertions'][0]['expected']==404
    assert not b['cases'][1]['steps'][0]['assertions']
    assert b['cases'][1]['state']=='NEEDS_RULE'
    assert any(s.get('kind')=='user_test_expectation' for s in c['sources'].values())
    for text in ['id,title,method,path\nA,a,GET,/items/{id},EXTRA','id,title,method,path,assertions\nA,a,GET,/items/{id},{}']:
        with pytest.raises(ValueError):import_candidates(items_bundle['contract'],'bad.csv',text)


def test_mcp_replace_retains_user_cases_and_cannot_rewrite_them(client,items_bundle):
    pid=_import_items(client);raw=source_cases(items_bundle)[0];raw['id']='USER-KEEP'
    client.put(f'/api/projects/{pid}/case-workflow',json={'mode':'import_ai'})
    assert upload(client,pid,[raw]).status_code==200
    assert client.post(f'/api/projects/{pid}/approve',json={'case_ids':[raw['id']]}).status_code==200
    baseline=details(client,pid)['bundle']['cases'][0]
    code=client.post('/api/mcp/pair').json()['code']
    token=client.post('/api/mcp/redeem',json={'code':code}).json()['token']
    def call(action,args):return client.post('/api/mcp/call',headers={'Authorization':'Bearer '+token},json={'action':action,'arguments':{'project_id':pid,**args}})
    ctx=call('context',{}).json()
    new=copy.deepcopy(ctx['candidates']['cases'][0]);new['id']='AI-ADDITION'
    saved=call('submit',{'revision':ctx['revision'],'replace':True,'cases':[new]})
    assert saved.status_code==200,saved.text
    assert next(c for c in details(client,pid)['bundle']['cases'] if c['id']=='USER-KEEP')==baseline
    ctx=call('context',{}).json();changed=copy.deepcopy(raw);changed['title']='overwrite attempt'
    denied=call('submit',{'revision':ctx['revision'],'cases':[changed]})
    assert denied.status_code==400 and '用户用例' in denied.text


@pytest.mark.parametrize('data',[{},None,{'enabled':False},{'enabled':True,'virtual_users':21},{'enabled':True,'duration_seconds':True}])
def test_load_requires_explicit_opt_in_and_valid_config(data):
    with pytest.raises(ValueError):load_config(data)


def test_real_load_replays_token_chains_in_parallel_and_cleans(items_bundle,tmp_path):
    with ItemsServer() as server:
        result=run_load(items_bundle,environment(server),tmp_path,
            load_config({'enabled':True,'virtual_users':3,'duration_seconds':10,'max_rounds':6,'think_time_ms':0}),
            case_ids=['ITEM-FLOW-001'],session_factory=requests.Session)
        assert result['rounds_finished']==6 and result['rounds_passed']==6
        assert result['requests_sent']==36 and result['requests_failed']==0
        assert result['latency_ms']['count']==36 and result['latency_ms']['p95'] is not None
        assert result['status_codes']=={'200':12,'201':6,'409':6,'204':6,'404':6}
        assert not server.items and len(set(server.tokens.values()))==6
        assert sum(p['requests'] for p in result['series'])==result['requests_sent']
        for token in server.tokens:assert token not in (tmp_path/'result.json').read_text()
        assert '</head>' in (tmp_path/'index.html').read_text()


def test_user_stop_finishes_inflight_chain_and_cleanup(items_bundle,tmp_path):
    stop=threading.Event()
    with ItemsServer() as server:
        result=run_load(items_bundle,environment(server),tmp_path,
            load_config({'enabled':True,'virtual_users':1,'duration_seconds':10,'max_rounds':100,'think_time_ms':0}),
            case_ids=['ITEM-FLOW-001'],session_factory=requests.Session,stop=stop,progress=lambda _:stop.set())
        assert result['rounds_finished']==1 and result['stop_reason']=='用户停止'
        assert not server.items and result['requests_sent']==6


def test_load_endpoint_separate_report_and_owner_isolation(client):
    pid=_import_items(client)
    _wait(client,client.post(f'/api/projects/{pid}/generate',json={'mode':'baseline'}))
    payload={'environment':'items','case_ids':['ITEM-FLOW-001'],'load':{'enabled':True,'virtual_users':2,'max_rounds':2,'duration_seconds':10,'think_time_ms':0}}
    assert client.post(f'/api/projects/{pid}/load-test',json={**payload,'load':{'enabled':False}}).status_code==400
    assert client.post(f'/api/projects/{pid}/load-test',json={**payload,'case_ids':[]}).status_code==400
    assert client.post(f'/api/projects/{pid}/run',json={**payload,'_load':payload['load']}).status_code==400
    job=_wait(client,client.post(f'/api/projects/{pid}/load-test',json=payload))
    report=job['result']['report_url']
    assert client.get(report).status_code==200
    result=client.get(report.replace('index.html','result.json')).json()
    assert result['requests_sent']==12 and result['rounds_passed']==2
    project=details(client,pid)['project']
    assert project['last_load']['id']==job['result']['id'] and not project.get('last_run')
    other=TestClient(client.app)
    other.headers['x-csrf-token']=other.get('/api/bootstrap').json()['csrf']
    shared=other.get(report)
    assert shared.status_code==200
    assert 'name="api-test-public-report" content="read-only"' in shared.text
    assert other.get(report.replace('index.html','result.json')).status_code in {403,404}
    assert other.post(f"/api/jobs/{job['id']}/stop-load").status_code in {403,404}
    other.close()


def test_all_existing_cases_export_and_reimport_without_step_loss(items_bundle):
    _, imported=import_candidates(items_bundle['contract'],'cases.json',json.dumps(candidates_from_bundle(items_bundle)))
    assert len(imported['cases'])==len(items_bundle['cases'])
    for old,new in zip(items_bundle['cases'],imported['cases']):
        assert [s['request'] for s in old['steps']]==[s['request'] for s in new['steps']]
        assert len(new['cleanup_steps'])==len(old.get('cleanup_steps',[]))
        assert new['state']=='NEEDS_RULE'


@pytest.mark.parametrize('mode',['ai','import_ai','ai_import'])
def test_model_generation_sources_use_existing_expectations_and_append(tmp_path,monkeypatch,mode):
    from api_test_tool import web
    origin='http://127.0.0.1:19000'
    app=web.create_app(tmp_path,start_fixture=False,testing=True,trusted_model_origins=(origin,))
    calls=[]
    def model(config,system,prompt,**kwargs):
        p=json.loads(prompt);calls.append(p)
        if p['phase']=='design':
            cases=[{'id':'D1','operation_id':'read','title':'AI 补充业务字段校验','design':{'category':'正向','inputs':'GET /health','procedure':'检查字段','expected':'ok 为 true','basis':'文档'}}]
        else:
            source=p['contract']['operations']['read']['source_ids'][0]
            cases=copy.deepcopy(p['supplied_cases'])
            for case in cases:case['steps']=[{'id':'read','request':{},'assertions':[{'kind':'json_equal','pointer':'/ok','expected':True,'evidence':[{'source_id':source,'quote':p['contract']['sources'][source]['excerpt']}]}]}]
        return {'text':json.dumps({'schema_version':'1.0','cases':cases}),'model':'mock','protocol':'openai_chat','usage':{}}
    monkeypatch.setattr(web,'generate_text',model)
    with TestClient(app) as c:
        c.headers['x-csrf-token']=c.get('/api/bootstrap').json()['csrf']
        saved=c.put('/api/model',json={'provider':'custom','protocol':'openai_chat','base_url':origin+'/v1','model':'offline-test','api_key':'dummy-key'})
        assert saved.status_code==200,saved.text
        document={'openapi':'3.0.3','info':{'title':'Health','version':'1'},'paths':{'/health':{'get':{'operationId':'read','responses':{'200':{'description':'ok is true'}}}}}}
        pid=c.post('/api/projects',json={'filename':'api.json','content':json.dumps(document)}).json()['project']['id']
        c.put(f'/api/projects/{pid}/case-workflow',json={'mode':mode})
        raw={'id':'USER-1','operation_id':'read','title':'用户状态码预期','steps':[{'id':'read','request':{},'assertions':[{'kind':'status','expected':200}]}]}
        if mode=='import_ai':
            assert upload(c,pid,[raw]).status_code==200
            assert c.post(f'/api/projects/{pid}/approve',json={'case_ids':['USER-1']}).status_code==200
            before=details(c,pid)['bundle']['cases'][0]
        _wait(c,c.post(f'/api/projects/{pid}/generate',json={'mode':'model','supplement':'健康接口返回 ok=true'}))
        bundle=details(c,pid)['bundle']
        assert set(bundle['contract']['sources']) <= set(details(c,pid)['contract']['sources'])
        assert any(x['web']['source']=='ai' and x['steps'] for x in bundle['cases'])
        if mode=='import_ai':
            assert next(x for x in bundle['cases'] if x['id']=='USER-1')==before
            assert calls[0]['existing_cases'][0]['steps'][0]['assertions'][0]['expected']==200
        if mode=='ai_import':
            before=copy.deepcopy(bundle['cases'])
            r=upload(c,pid,[raw]);assert r.status_code==200,r.text
            assert r.json()['bundle']['cases'][:-1]==before
            assert r.json()['bundle']['cases'][-1]['web']['source']=='user'


def test_cleanup_failure_stops_load_and_reports_real_failed_requests(items_bundle,tmp_path):
    with ItemsServer(fault='cleanup_error') as server:
        result=run_load(items_bundle,environment(server),tmp_path,
            load_config({'enabled':True,'virtual_users':1,'duration_seconds':10,'max_rounds':100,'think_time_ms':0}),
            case_ids=['ITEM-FLOW-001'],session_factory=requests.Session)
        assert result['rounds_finished']==1 and result['rounds_passed']==0
        assert result['cleanup_failures']==1 and result['requests_failed']>0
        assert '清理失败' in result['stop_reason']
        assert result['failure_samples'][0]['cases'][0]['cleanup']['status']=='FAIL'
        assert result['error_rate']==result['requests_failed']/result['requests_sent']


def test_remove_restore_cases_preserves_other_cases_reviews_and_snapshots(client, items_bundle):
    pid = _import_items(client)
    raw = next(c for c in source_cases(items_bundle) if c['id'] == 'ITEM-FLOW-001')
    assert upload(client, pid, [raw]).status_code == 200
    assert client.post(f'/api/projects/{pid}/approve', json={'case_ids': [raw['id']]}).status_code == 200
    run = _wait(client, client.post(f'/api/projects/{pid}/run', json={'environment': 'items'}))['result']
    evidence_url = run['report_url'].replace('index.html', 'result.json')
    evidence = client.get(evidence_url).json()
    before = details(client, pid)
    removed = client.post(f'/api/projects/{pid}/cases/remove', json={'case_id': raw['id'], 'revision': before['bundle_revision']})
    assert removed.status_code == 200, removed.text
    after = removed.json()
    assert after['bundle']['cases'] == []
    assert after['project']['runs'] == before['project']['runs']
    assert client.get(f'/api/projects/{pid}/editable-cases').json()['cases'] == []
    assert client.get(evidence_url).json() == evidence
    archive_id = after['deleted_cases'][0]['id']
    assert client.post(f'/api/projects/{pid}/cases/restore', json={'id': archive_id, 'revision': 'stale'}).status_code == 409
    with TestClient(client.app) as other:
        boot = other.get('/api/bootstrap').json(); other.headers['x-csrf-token'] = boot['csrf']
        assert other.post(f'/api/projects/{pid}/cases/restore', json={'id': archive_id, 'revision': after['bundle_revision']}).status_code in (403, 404)
    restored = client.post(f'/api/projects/{pid}/cases/restore', json={'id': archive_id, 'revision': after['bundle_revision']})
    assert restored.status_code == 200, restored.text
    assert restored.json()['bundle']['cases'] == before['bundle']['cases']
    assert restored.json()['deleted_cases'] == []
    assert client.get(evidence_url).json() == evidence
    assert client.post(f'/api/projects/{pid}/cases/remove', json={'case_id': raw['id'], 'revision': 'stale'}).status_code == 409


def test_delete_one_case_keeps_other_and_rejects_restore_id_collision(client, items_bundle):
    pid = _import_items(client)
    cases = source_cases(items_bundle)[:2]
    assert upload(client, pid, cases).status_code == 200
    before = details(client, pid)
    after = client.post(f'/api/projects/{pid}/cases/remove', json={'case_id': cases[0]['id'], 'revision': before['bundle_revision']}).json()
    assert after['bundle']['cases'] == before['bundle']['cases'][1:]
    assert upload(client, pid, [cases[0]]).status_code == 200
    current = details(client, pid)
    assert client.post(f'/api/projects/{pid}/cases/restore', json={'id': after['deleted_cases'][0]['id'], 'revision': current['bundle_revision']}).status_code == 409
    assert details(client, pid)['bundle'] == current['bundle']


def test_load_charts_use_real_measurements_and_preserve_historical_evidence(client):
    pid=_import_items(client)
    _wait(client,client.post(f'/api/projects/{pid}/generate',json={'mode':'baseline'}))
    job=_wait(client,client.post(f'/api/projects/{pid}/load-test',json={
        'environment':'items','case_ids':['ITEM-FLOW-001'],
        'load':{'enabled':True,'virtual_users':1,'max_rounds':1,'duration_seconds':10,'think_time_ms':0}}))
    url=job['result']['report_url']
    saved=client.get(url.replace('index.html','result.json')).json()
    assert saved['series_basis']=='request_completed'
    assert sum(p['latency_ms']['count'] for p in saved['series'])==saved['requests_sent']==6
    assert all(p['latency_ms']['p50']<=p['latency_ms']['p95']<=p['latency_ms']['p99'] for p in saved['series'])
    page=client.get(url).text
    for text in ['吞吐量趋势','响应时间趋势','未通过比例趋势','HTTP 状态码分布','<svg','返回压测']:
        assert text in page
    assert client.get(url.replace('index.html','result.json')).json()==saved
