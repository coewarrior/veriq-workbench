"""Management changes the executable scope, preserves history and isolates owners."""
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api_test_tool import web
from api_test_tool.web_generation import auto_bundle


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    def no_model(*args, **kwargs):
        raise AssertionError('Management must never call a model')
    monkeypatch.setattr(web, 'generate_text', no_model)
    app = web.create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        doc = {'openapi':'3.0.3','info':{'title':'管理验收','version':'1'},'paths':{
            '/old':{'get':{'operationId':'read_old','parameters':[{'name':'q','in':'query','schema':{'type':'string'},'example':'你好'}],
                          'responses':{'200':{'description':'OK','content':{'application/json':{'schema':{'type':'object'}}}}}}},
            '/kept':{'get':{'operationId':'read_kept','responses':{'204':{'description':'No content'}}}}
        }}
        created=client.post('/api/projects',json={'title':'管理验收','filename':'api.json','content':json.dumps(doc)}).json()
        pid=created['project']['id'];url='/api/projects/'+pid
        owner=next(iter(app.state.store.root.glob('sessions/*'))).name
        yield app, client, owner, pid, url, created


def change(client,url,operation=None,delete=None,revision=None):
    revision=revision or client.get(url).json()['contract_revision']
    if delete:
        return client.request('DELETE',url+'/operations/'+delete,json={'revision':revision})
    return client.post(url+'/operations',json={'revision':revision,'operation':operation})


def mcp(client):
    code=client.post('/api/mcp/pair').json()['code']
    token=client.post('/api/mcp/redeem',json={'code':code}).json()['token']
    return lambda action, **arguments: client.post('/api/mcp/call',json={'action':action,'arguments':arguments},headers={'Authorization':'Bearer '+token})


def test_rename_session_updates_only_title_and_respects_owner(workspace):
    app, client, owner, pid, url, created = workspace
    before = app.state.store.get_project(owner, pid)
    with TestClient(app) as other:
        other.headers['x-csrf-token'] = other.get('/api/bootstrap').json()['csrf']
        assert other.patch(url+'/title', json={'title':'别人的名称'}).status_code == 404
    assert client.patch(url+'/title', json={'title':'未授权'}, headers={'x-csrf-token':''}).status_code == 403
    for title in ('', '  ', 'x'*121):
        assert client.patch(url+'/title', json={'title':title}).status_code == 400
    changed = client.patch(url+'/title', json={'title':'  新名称  '})
    assert changed.status_code == 200, changed.text
    assert changed.json()['project']['title'] == '新名称'
    after = client.get(url).json()
    assert after['project']['title'] == '新名称'
    assert after['contract'] == created['contract']
    assert after['project']['id'] == before['id']
    assert after['project']['task'] == before['task']
    assert client.get('/api/bootstrap').json()['projects'][0]['title'] == '新名称'
    assert client.delete(url).status_code == 200
    assert client.patch(url+'/title', json={'title':'不能修改回收站'}).status_code == 404


def test_recycle_restore_access_history_csrf_and_owner(workspace):
    app,c,owner,pid,url,created=workspace
    store=app.state.store;location=store.project_dir(owner,pid)
    rid=str(uuid4());directory=location/'runs'/rid;directory.mkdir(parents=True)
    (directory/'index.html').write_text('frozen report')
    store.update_project(owner,pid,{'runs':[{'id':rid}], 'status':'executed'})
    report=url+'/reports/'+rid+'/index.html'
    assert c.get(report).text=='frozen report'
    with TestClient(app) as other:
        other.headers['x-csrf-token']=other.get('/api/bootstrap').json()['csrf']
        assert other.delete(url).status_code==404
        assert other.post(url+'/restore').status_code==404
        assert other.get('/api/deleted-projects').json()['projects']==[]
    assert c.delete(url,headers={'x-csrf-token':''}).status_code==403
    assert c.delete(url).status_code==200
    assert c.get('/api/bootstrap').json()['projects']==[]
    assert c.get(url).status_code==404
    assert c.get(report).status_code==404
    assert c.get(url+'/artifacts/document').status_code==404
    assert c.get('/api/deleted-projects').json()['projects'][0]['id']==pid
    assert (directory/'index.html').read_text()=='frozen report'
    assert c.post(url+'/restore').status_code==200
    assert c.get(url).json()['contract']==created['contract']
    assert c.get(report).text=='frozen report'
    assert c.get('/api/deleted-projects').json()['projects']==[]


def test_interface_changes_preserve_history_and_mcp_scope(workspace):
    app,c,owner,pid,url,created=workspace
    store=app.state.store;location=store.project_dir(owner,pid)
    store.save_asset(owner,pid,'bundle',{'cases':[{'id':'old-case','state':'READY'}]})
    store.save_asset(owner,pid,'mcp-candidates',{'cases':[]})
    rid=str(uuid4());directory=location/'runs'/rid;directory.mkdir(parents=True)
    (directory/'bundle.json').write_text('{"frozen":true}')
    call=mcp(c);old_context=call('context',project_id=pid).json()
    deleted=change(c,url,delete='read_old');assert deleted.status_code==200,deleted.text
    data=deleted.json()
    assert data['bundle'] is None
    assert 'read_old' not in data['contract']['operations']
    assert data['contract']['operations']['read_kept']==created['contract']['operations']['read_kept']
    assert data['project']['status']=='imported'
    assert c.post(url+'/run',json={'environment':'items'}).status_code==404
    assert (directory/'bundle.json').read_text()=='{"frozen":true}'
    assert (location/'bundle.previous.json').exists()
    current=c.get(url+'/artifacts/document').json()
    assert set(current['paths'])=={'/kept'}
    assert c.get(url+'/artifacts/original-document').json()['paths']['/old']
    current_doc=call('document',project_id=pid,limit=60000).json()
    assert json.loads(current_doc['content'])['paths']==current['paths']
    assert current_doc['filename']=='current-interfaces.json'
    stale=call('submit',project_id=pid,revision=old_context['revision'],cases=[])
    assert stale.status_code==409,stale.text
    fresh=call('context',project_id=pid).json()
    removed_case={'id':'DELETED-1','title':'已经删除的接口','operation_id':'read_old','scenario':'normal','variables':{},
        'steps':[{'id':'read','operation_id':'read_old','request':{},'assertions':[],'extract':[]}],'cleanup_steps':[]}
    assert call('submit',project_id=pid,revision=fresh['revision'],cases=[removed_case]).status_code==400
    operation={'method':'POST','path':'/users/{id}','title':'更新用户','request_example':{'name':'张三'},
               'response_status':200,'response_example':{'ok':True},'parameters':[{'name':'q','in':'query','schema':{'type':'string'},'example':'hello'}]}
    added=change(c,url,operation);assert added.status_code==200,added.text
    ops=added.json()['contract']['operations'];op=next(v for v in ops.values() if v['path']=='/users/{id}')
    assert op['summary']=='更新用户' and op['request_example']=={'name':'张三'}
    assert {p['name'] for p in op['parameters']}=={'id','q'}
    assert next(p for p in op['parameters'] if p['name']=='id')['required'] is True
    # Rule generation really uses the new request body (even without a supplied Schema).
    bundle=auto_bundle(added.json()['contract'])
    case=next(case for case in bundle['cases'] if case['operation_id']==op['id'])
    assert case['steps'][0]['request']['json']=={'name':'张三'}
    assert 'read_old' not in {case['operation_id'] for case in bundle['cases']}
    # An edit from another tab cannot overwrite a more recent interface change.
    assert change(c,url,operation,revision=data['contract_revision']).status_code==409


@pytest.mark.parametrize('operation',[
    None, {}, {'method':'BOGUS','path':'/x','title':'x'}, {'method':'GET','path':'https://example.com','title':'x'},
    {'method':'GET','path':'/../x','title':'x'}, {'method':'GET','path':'/x?query=1','title':'x'},
    {'method':'GET','path':'/old','title':'duplicate'}, {'method':'GET','path':'/x/{oops','title':'x'},
    {'method':'GET','path':'/x','title':'x','response_example':{}},
    {'method':'GET','path':'/x','title':'x','parameters':[{'name':'q','in':'query','schema':'bad'}]},
])
def test_invalid_interface_does_not_mutate_contract(workspace,operation):
    app,c,owner,pid,url,created=workspace
    assert change(c,url,operation).status_code==400
    assert c.get(url).json()['contract']==created['contract']


def test_empty_scope_and_template_baseline(workspace):
    app,c,owner,pid,url,created=workspace
    store=app.state.store;store.update_project(owner,pid,{'template':'items'})
    for oid in created['contract']['operations']:
        assert change(c,url,delete=oid).status_code==200
    assert c.get(url).json()['contract']['operations']=={}
    assert c.post(url+'/generate',json={'mode':'baseline'}).status_code==400
    assert change(c,url,{'title':'新接口','method':'GET','path':'/new','response_status':204}).status_code==200
    assert c.get(url).json()['project']['template']=='items'


def test_active_job_prevents_management_changes(workspace):
    app,c,owner,pid,url,created=workspace
    app.state.jobs['running']={'id':'running','owner':owner,'project_id':pid,'status':'running'}
    assert c.delete(url).status_code==409
    assert change(c,url,delete='read_old').status_code==409
    assert c.get(url).json()['contract']==created['contract']
    app.state.jobs.clear()


def edit(client,url,oid,changes,revision=None):
    revision=revision or client.get(url).json()['contract_revision']
    return client.patch(url+'/operations/'+oid,json={'revision':revision,'operation':changes})


def test_edit_keeps_identity_auth_other_responses_and_history(workspace):
    app,c,owner,pid,url,created=workspace
    store=app.state.store
    contract=created['contract'];op=contract['operations']['read_old']
    op.update(auth={'type':'http','scheme':'bearer'},request_schema={'type':'object','required':['name']},
              request_example={'name':'old'},response_examples=[{'ok':True}])
    op['responses']['401']={'type':'object','properties':{'error':{'type':'string'}}}
    store.save_asset(owner,pid,'contract',contract)
    store.save_asset(owner,pid,'bundle',{'cases':[]})
    changed=edit(c,url,'read_old',{'title':'修改后的名称','method':'POST','path':'/changed',
                 'request_example':{'name':'新值'},'response_status':201})
    assert changed.status_code==200,changed.text
    data=changed.json();updated=data['contract']['operations']['read_old']
    assert updated['id']=='read_old' and updated['summary']=='修改后的名称'
    assert updated['method']=='POST' and updated['path']=='/changed'
    assert updated['auth']==op['auth'] and updated['request_schema']==op['request_schema']
    assert updated['responses']=={'201':op['responses']['200'],'401':op['responses']['401']}
    assert updated['request_example']=={'name':'新值'}
    assert data['bundle'] is None
    assert data['contract']['operations']['read_kept']==contract['operations']['read_kept']
    current=c.get(url+'/artifacts/document').json()
    assert '/old' not in current['paths'] and '/changed' in current['paths']
    assert current['paths']['/changed']['post']['operationId']=='read_old'
    assert updated['source_ids']!=op['source_ids']
    assert '新值' in data['contract']['sources'][updated['source_ids'][0]]['excerpt']
    assert edit(c,url,'read_old',{'path':'/kept','method':'GET'}).status_code==400
    assert edit(c,url,'missing',{'title':'不存在'}).status_code==404
    assert edit(c,url,'read_old',{'title':'old'},created['contract_revision']).status_code==409


def test_edit_noop_and_clear_preserve_other_fields(workspace):
    app,c,owner,pid,url,created=workspace
    app.state.store.save_asset(owner,pid,'bundle',{'cases':[]})
    unchanged=edit(c,url,'read_old',{}).json()
    assert unchanged['bundle']=={'cases':[]}
    assert unchanged['contract_revision']==created['contract_revision']
    response=edit(c,url,'read_old',{'_clear':['parameters','response_status']})
    assert response.status_code==200,response.text
    op=response.json()['contract']['operations']['read_old']
    assert op['parameters']==[] and op['responses']=={}
    assert edit(c,url,'read_old',{'request_example':None}).json()['contract']['operations']['read_old']['has_request_example'] is True
    cleared=edit(c,url,'read_old',{'_clear':['request_example']}).json()['contract']['operations']['read_old']
    assert not cleared['has_request_example'] and not cleared['has_request_body']


def test_edit_rejects_invalid_fields_and_busy_or_foreign_owner(workspace):
    app,c,owner,pid,url,created=workspace
    for changes in [{'path':'https://evil.test/x'},{'_clear':['auth']},{'response_status':'200'}, {'_clear':['request_example'],'request_example':{}},{'auth':{}},None]:
        assert edit(c,url,'read_old',changes).status_code==400
    assert c.get(url).json()['contract']==created['contract']
    with TestClient(app) as other:
        other.headers['x-csrf-token']=other.get('/api/bootstrap').json()['csrf']
        assert edit(other,url,'read_old',{},created['contract_revision']).status_code==404
    app.state.jobs['edit-test']={'owner':owner,'status':'running'}
    assert edit(c,url,'read_old',{'title':'忙碌'}).status_code==409
    app.state.jobs.clear()


def test_purge_removes_selected_assets_and_preserves_other_projects(workspace):
    app,c,owner,pid,url,_=workspace
    store=app.state.store
    location=store.project_dir(owner,pid)
    (location/'runs'/'evidence.json').write_text('{"sample":true}')
    keep=store.create_project(owner,'保留会话','keep.md','# keep')
    recycled=store.create_project(owner,'其他回收站会话','old.md','# old')
    store.recycle_project(owner,recycled['id'])
    assert c.delete(url).status_code==200
    payload={'project_ids':[pid], 'confirm':True}
    assert c.post('/api/deleted-projects/purge',json=payload,headers={'x-csrf-token':''}).status_code==403
    assert c.post('/api/deleted-projects/purge',json={'project_ids':[pid]}).status_code==400
    with TestClient(app) as other:
        other.headers['x-csrf-token']=other.get('/api/bootstrap').json()['csrf']
        assert other.post('/api/deleted-projects/purge',json=payload).status_code==404
    assert location.exists()
    app.state.jobs['old-job']={'id':'old-job','owner':owner,'project_id':pid,'status':'completed'}
    result=c.post('/api/deleted-projects/purge',json=payload)
    assert result.status_code==200,result.text
    assert result.json()['deleted_ids']==[pid]
    assert not location.exists()
    assert c.get('/api/jobs/old-job').status_code==404
    assert c.post(url+'/restore').status_code==404
    assert store.get_project(owner,keep['id'])['title']=='保留会话'
    assert [p['id'] for p in c.get('/api/deleted-projects').json()['projects']]==[recycled['id']]


def test_purge_validates_whole_batch_and_rejects_stale_selection(workspace):
    app,c,owner,pid,url,_=workspace
    store=app.state.store;location=store.project_dir(owner,pid)
    second=store.create_project(owner,'第二个会话','second.md','# second')
    c.delete(url)
    payload={'project_ids':[pid,second['id']], 'confirm':True}
    assert c.post('/api/deleted-projects/purge',json=payload).status_code==400
    assert location.exists()
    store.recycle_project(owner,second['id'])
    app.state.jobs['purge-test']={'owner':owner,'status':'running'}
    try:
        assert c.post('/api/deleted-projects/purge',json=payload).status_code==409
    finally:
        app.state.jobs.clear()
    assert location.exists()
    assert c.post('/api/projects/'+second['id']+'/restore').status_code==200
    assert c.post('/api/deleted-projects/purge',json=payload).status_code==400
    assert location.exists()
    store.recycle_project(owner,second['id'])
    assert c.post('/api/deleted-projects/purge',json=payload).status_code==200
    assert c.get('/api/deleted-projects').json()['projects']==[]


def test_purge_unlinks_nested_symlink_without_deleting_target(workspace,tmp_path):
    app,c,owner,pid,url,_=workspace
    store=app.state.store;location=store.project_dir(owner,pid)
    outside=tmp_path/'outside';outside.mkdir();(outside/'keep.txt').write_text('keep')
    (location/'runs'/'external').symlink_to(outside,target_is_directory=True)
    c.delete(url)
    assert c.post('/api/deleted-projects/purge',json={'project_ids':[pid], 'confirm':True}).status_code==200
    assert (outside/'keep.txt').read_text()=='keep'


def test_purge_waits_for_inflight_project_write(workspace):
    import threading
    app,c,owner,pid,url,_=workspace
    entered=threading.Event();finish=threading.Event()
    @app.post(url+'/slow-write-test')
    def slow_write():
        entered.set()
        assert finish.wait(5)
        return {'ok':True}
    c.delete(url)
    worker=threading.Thread(target=lambda:c.post(url+'/slow-write-test'))
    worker.start()
    try:
        assert entered.wait(5)
        result=c.post('/api/deleted-projects/purge',json={'project_ids':[pid],'confirm':True})
        assert result.status_code==409,result.text
    finally:
        finish.set();worker.join(5)
    assert c.post('/api/deleted-projects/purge',json={'project_ids':[pid],'confirm':True}).status_code==200
