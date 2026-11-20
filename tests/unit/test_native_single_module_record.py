from pathlib import Path
from types import SimpleNamespace
from api_test_tool.orchestration import Controller
from api_test_tool.orchestration_web import dispatch
from api_test_tool.managed_service import ManagedService
from api_test_tool.web_storage import Store
from api_test_tool import ui_records


def test_explicit_single_module_has_own_record_and_legacy_session_keeps_parent(tmp_path, monkeypatch):
    store = Store(tmp_path)
    session, _ = store.session(None)
    owner = session['id']
    p = store.create_project(owner, 'source', 'source.md', 'original scope')
    p = store.update_project(owner, p['id'], {'test_kind':'ui','ui_target_url':'https://test.example'})
    old = ui_records.save_cases(store, owner, p['id'], [{'case_id':'original','scenario':'saved case',
        'steps':'read fixture','expected':'fixture present','status':'passed','actual':'original evidence'}])
    controller = Controller(store)
    controller.add_account(owner, {'project_id':p['id'],'target':'https://test.example','identity':'fixture','credential':''})
    service = ManagedService(controller, Path(__file__).parents[2]/'api_test_tool/static')
    request = SimpleNamespace(state=SimpleNamespace(owner=owner,mcp_scope=None))
    args = {'project_id':p['id'],'request_id':'new-plan','goal':'one selected case',
        'execution_route':'native_browser','modules':[{'key':'single','title':'single','requirements':[]}]}
    # At the existing top-level limit, a proper child round still works.
    monkeypatch.setattr('api_test_tool.web_storage._MAX_PROJECTS_PER_OWNER',1)
    created = dispatch(controller, request, 'managed_create', args)
    snapshot = controller.snapshot(owner,created['task_id'])
    task,node = snapshot['tasks'][0],snapshot['nodes'][0]
    assert task['independent_module_records']
    record = service.report_project(owner,node,task)
    assert record['id'] != p['id'] and not record.get('ui_execution_id')
    assert record['execution_round']['parent_project_id'] == p['id']
    assert service.report_project(owner,node,task)['id'] == record['id']
    assert ui_records.load(store,owner,p['id'],old['execution_id'])['cases'][0]['actual']=='original evidence'
    assert service.report_project(owner,node,{**task,'independent_module_records':False})['id']==p['id']
