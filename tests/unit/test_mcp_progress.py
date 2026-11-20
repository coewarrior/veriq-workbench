import time
from fastapi.testclient import TestClient
from api_test_tool.web import create_app


def test_progress_connection_isolation_completion_and_restart(tmp_path):
    with TestClient(create_app(tmp_path, start_fixture=False, testing=True)) as browser:
        browser.headers['x-csrf-token'] = browser.get('/api/bootstrap').json()['csrf']
        assert not browser.get('/api/mcp/status').json()['connected']
        code = browser.post('/api/mcp/pair').json()['code']
        assert not browser.get('/api/mcp/status').json()['connected']
        token = browser.post('/api/mcp/redeem', json={'code': code}).json()['token']
        def call(action, **arguments):
            return browser.post('/api/mcp/call', json={'action': action, 'arguments': arguments}, headers={'Authorization':'Bearer '+token})
        status = browser.get('/api/mcp/status').json()
        assert status['connected'] and status['active']
        imported = call('import', filename='notes.md', content='说明文档', title='进度验证', allow_unparsed=True).json()
        pid = imported['project']['id']
        def project():
            return browser.get('/api/projects/'+pid).json()['project']
        before = project().get('mcp_progress')
        assert call('document', project_id=pid).status_code == 200
        assert project().get('mcp_progress') == before
        assert call('document', project_id=pid, limit=-1).status_code == 400
        assert project().get('mcp_progress') == before
        assert call('progress', project_id=pid, phase='reporting', message='已核对响应示例，正在整理发现').status_code == 200
        assert project()['mcp_progress']['message'] == '已核对响应示例，正在整理发现'
        before = project()['mcp_progress']
        assert call('document', project_id=pid).status_code == 200
        assert project()['mcp_progress'] == before
        assert call('progress', project_id=pid, phase='completed').status_code == 400
        assert call('task_report', project_id=pid, title='文档检查', summary='检查完成').status_code == 200
        assert project()['mcp_progress']['phase'] == 'completed'
        assert call('report', project_id=pid).status_code == 200
        assert project()['mcp_progress']['phase'] == 'completed'
        browser.put('/api/projects/'+pid+'/task', json={'goal':'新一轮检查','restart_progress':True})
        assert project()['mcp_progress']['phase'] == 'waiting'
        assert len(project()['mcp_progress']['history']) == 1
        # A second browser identity shares this server; it must not start a
        # second background worker against the same data-directory lock.
        other = TestClient(browser.app)
        assert other.get('/api/projects/'+pid).status_code in {403,404}
        assert not other.get('/api/mcp/status').json()['connected']
        browser.delete('/api/mcp/pair')
        assert not browser.get('/api/mcp/status').json()['connected']
        assert call('document', project_id=pid).status_code == 401


def test_inactive_connection_survives_restart(tmp_path, monkeypatch):
    from api_test_tool.mcp_access import MCPAccess
    from api_test_tool.web_storage import Store
    store=Store(tmp_path)
    owner=store.session(None)[0]['id']
    access=MCPAccess(store)
    token=access.redeem(access.issue(owner)['code'])['token']
    now=time.time()
    monkeypatch.setattr('api_test_tool.mcp_access.time.time',lambda:now+121)
    assert access.status(owner)['connected']
    assert not access.status(owner)['active']
    access.authenticate(token)
    assert MCPAccess(Store(tmp_path)).status(owner)['active']


def _record_project(pid, counts, *, created=100, revision=1, **extra):
    return {'id': pid, 'title': pid, 'created_at': created, 'test_kind': 'ui',
            'ui_execution_id': pid + '-execution', 'ui_execution_revision': revision,
            'ui_progress_record': {'execution_id': pid + '-execution', 'revision': revision,
                                   'counts': counts, 'saved_at': created + 20}, **extra}


def test_live_progress_uses_saved_results_and_scheduler_not_document_activity():
    from api_test_tool.mcp_progress import project_progress
    p = _record_project('current', {'passed': 3, 'not_run': 51},
                        mcp_progress={'phase': 'reading', 'label': '读取文档', 'updated_at': 9999})
    task = {'id': 'task', 'project_id': p['id'], 'created': 100, 'node_ids': ['node']}
    node = {'id': 'node', 'task_id': task['id'], 'state': 'running', 'business_started_at': 110}
    snapshot = {'tasks': [task], 'nodes': [node], 'leases': [{'node_id': 'node', 'mode': 'exclusive'}]}
    progress = project_progress(None, 'owner', p, snapshot, [p])
    assert progress['phase'] == 'executing'
    assert progress['case_counts'] == {'passed': 3, 'not_run': 51}
    assert progress['last_case_saved_at'] == 120
    assert p['mcp_progress']['phase'] == 'reading'  # The read view does not write metadata.
    assert not progress['modules'][0]['coverage_complete']


def test_progress_distinguishes_allocation_wait_block_closeout_and_report(tmp_path):
    from api_test_tool.mcp_progress import project_progress
    from types import SimpleNamespace
    store = SimpleNamespace(project_dir=lambda *_: tmp_path)
    p = _record_project('current', {'not_run': 54})
    task = {'id': 'task', 'project_id': p['id'], 'created': 100, 'node_ids': ['node']}
    node = {'id': 'node', 'task_id': task['id'], 'state': 'running'}
    snapshot = {'tasks': [task], 'nodes': [node], 'leases': [{'node_id': 'node', 'mode': 'exclusive'}]}
    view = lambda: project_progress(store, 'owner', p, snapshot, [p])
    assert view()['phase'] == 'preparing'
    node.update(state='queued', dispatch_state='waiting_resource')
    snapshot['leases'] = []
    assert view()['phase'] == 'waiting'
    node.update(state='blocked', reason='前置条件未满足')
    assert view()['phase'] == 'blocked'
    p['ui_finish_request'] = {'execution_id': p['ui_execution_id'], 'revision': 1}
    assert view()['phase'] == 'settling'
    p.pop('ui_finish_request')
    node['state'] = 'completed'
    p['ui_progress_record']['report_id'] = 'report'
    p['last_analysis'] = {'id': 'report', 'created_at': 140}
    assert view()['phase'] == 'completed'
    assert view()['label'] == '报告已保存'
    assert view()['case_counts'] == {'not_run': 54}
    assert not view()['modules'][0]['coverage_complete']


def test_ended_native_report_wait_is_idle_and_explicit_publication_is_active():
    from api_test_tool.mcp_progress import project_progress
    p = _record_project('current', {'not_run': 2})
    task = {'id': 'task', 'project_id': p['id'], 'created': 100, 'node_ids': ['node'],
            'execution_route': 'native_browser'}
    node = {'id': 'node', 'task_id': 'task', 'state': 'completed', 'native_report_pending': {'lease_id': 'ended'}}
    snapshot = {'tasks': [task], 'nodes': [node], 'leases': []}
    view = lambda: project_progress(None, 'owner', p, snapshot, [p])
    assert view()['phase'] == 'awaiting_report' and not view()['active']
    assert view()['modules'][0]['report_saved'] is False
    p['ui_finish_request'] = {'execution_id': p['ui_execution_id'], 'revision': 1}
    assert view()['phase'] == 'settling' and view()['active']
    p['ui_finish_request']['error'] = 'Original report publication failed'
    assert view()['phase'] == 'failed' and not view()['active']


def test_parent_progress_selects_latest_round_by_source_not_late_old_updates():
    from api_test_tool.mcp_progress import project_progress
    root = {'id': 'root', 'title': '总任务', 'created_at': 90}
    module = _record_project('module', {'passed': 10}, managed_node_id='original',
                             managed_parent_project_id='root')
    old = _record_project('old', {'passed': 20}, created=200,
                          execution_round={'kind': 'regression', 'parent_project_id': 'root', 'source_project_id': 'module'},
                          mcp_progress={'phase': 'completed', 'updated_at': 9999})
    current = _record_project('current', {'passed': 3, 'not_run': 51}, created=300,
                              execution_round={'kind': 'regression', 'parent_project_id': 'root', 'source_project_id': 'module'})
    other = _record_project('other', {'failed': 99})
    projects = [root, module, old, current, other]
    tasks = [{'id': pid + '-task', 'project_id': pid, 'created': at, 'node_ids': [nid]}
             for pid, nid, at in [('root', 'original', 100), ('old', 'old-node', 200), ('current', 'new-node', 300), ('other', 'other-node', 400)]]
    nodes = [{'id': nid, 'task_id': pid + '-task', 'state': state, 'record_project_id': rid}
             for pid, nid, rid, state in [('root', 'original', 'module', 'completed'),
                 ('old', 'old-node', 'old', 'completed'), ('current', 'new-node', 'current', 'running'),
                 ('other', 'other-node', 'other', 'running')]]
    snapshot = {'tasks': tasks, 'nodes': nodes, 'leases': []}
    progress = project_progress(None, 'owner', root, snapshot, projects)
    assert progress['phase'] == 'executing'
    assert [unit['project_id'] for unit in progress['modules']] == ['current']
    assert progress['case_counts'] == {'passed': 3, 'not_run': 51}
    assert progress['updated_at'] < 9999


def test_whole_multimodule_round_does_not_include_previous_round_results():
    from api_test_tool.mcp_progress import project_progress
    root = {'id': 'root', 'title': '总任务', 'created_at': 90}
    regression = {'id': 'round', 'title': '整体回归', 'created_at': 300,
        'execution_round': {'kind': 'regression', 'parent_project_id': 'root', 'source_project_id': 'root'}}
    projects = [root, regression]
    tasks, nodes = [], []
    for parent, created, status in [('root', 100, 'passed'), ('round', 300, 'not_run')]:
        node_ids = [parent + '-one', parent + '-two']
        tasks.append({'id': parent + '-task', 'project_id': parent, 'created': created, 'node_ids': node_ids})
        for nid in node_ids:
            projects.append(_record_project(nid, {status: 5}, created=created + 10,
                                            managed_node_id=nid, managed_parent_project_id=parent))
            nodes.append({'id': nid, 'task_id': parent + '-task', 'state': 'completed' if parent == 'root' else 'queued',
                          'record_project_id': nid})
    progress = project_progress(None, 'owner', root, {'tasks': tasks, 'nodes': nodes, 'leases': []}, projects)
    assert len(progress['modules']) == 2
    assert progress['case_counts'] == {'not_run': 10}
    assert {unit['project_id'] for unit in progress['modules']} == {'round-one', 'round-two'}


def test_case_save_updates_current_lease_activity_without_fabricating_executor_heartbeat():
    from contextlib import contextmanager
    from types import SimpleNamespace
    from api_test_tool.managed_workflow import ManagedWorkflow
    p = _record_project('current', {'passed': 1}, revision=2)
    node = {'id': 'node', 'owner': 'owner', 'task_id': 'task', 'state': 'running', 'actor_seen': 100}
    lease = {'id': 'lease', 'node_id': 'node', 'progress_at': 100}
    state = {'nodes': {'node': node}, 'leases': {'lease': lease},
             'tasks': {'task': {'id': 'task', 'project_id': p['id'], 'node_ids': ['node']}}}
    @contextmanager
    def transaction():
        yield None, state
    store = SimpleNamespace(get_project=lambda owner, pid: p)
    controller = SimpleNamespace(transaction=transaction, clock=lambda: 200)
    workflow = ManagedWorkflow(SimpleNamespace(store=store, controller=controller))
    saved = {'execution_id': p['ui_execution_id'], 'revision': 2,
             'execution_plan': {'execution_summary': {'status_counts': {'passed': 1}}}}
    workflow.record_activity('owner', p['id'], {**saved, 'revision': 1})
    assert lease['progress_at'] == 100
    workflow.record_activity('owner', p['id'], saved)
    assert lease['progress_at'] == node['last_case_saved_at'] == node['business_started_at'] == 200
    assert node['actor_seen'] == 100


def test_legacy_sibling_counts_remain_after_last_active_module_ends(monkeypatch):
    from api_test_tool.mcp_progress import project_progress
    root = {'id': 'root', 'title': '总任务', 'created_at': 90}
    legacy = _record_project('legacy', {}, managed_node_id='one', managed_parent_project_id='root')
    legacy.pop('ui_progress_record')
    current = _record_project('current', {'not_run': 3}, managed_node_id='two', managed_parent_project_id='root')
    task = {'id': 'task', 'project_id': 'root', 'created': 100, 'node_ids': ['one', 'two']}
    nodes = [{'id': nid, 'task_id': 'task', 'state': 'completed', 'record_project_id': pid}
             for nid, pid in [('one', 'legacy'), ('two', 'current')]]
    reads = []
    def load(store, owner, pid, eid):
        reads.append(pid)
        return {'revision': 1, 'cases': [{'status': 'partial'}, {'status': 'pending_rule'}]}
    monkeypatch.setattr('api_test_tool.ui_records.load', load)
    cache = {}
    progress = project_progress(None, 'owner', root, {'tasks': [task], 'nodes': nodes}, [root, legacy, current], cache)
    assert progress['case_counts'] == {'partial': 1, 'pending_rule': 1, 'not_run': 3}
    assert progress['case_counts_complete']
    assert '验证未完成 1' in progress['message'] and '待确认规则 1' in progress['message']
    project_progress(None, 'owner', root, {'tasks': [task], 'nodes': nodes}, [root, legacy, current], cache)
    assert reads == ['legacy']


def test_legacy_paused_round_keeps_saved_counts_and_report_without_becoming_active(monkeypatch, tmp_path):
    from api_test_tool.mcp_progress import project_progress
    p = _record_project('current', {}, revision=7,
        mcp_progress={'phase': 'completed', 'updated_at': 301},
        last_analysis={'id': 'saved-report', 'created_at': 300})
    p.pop('ui_progress_record')
    unrelated = _record_project('unrelated-history', {'passed': 99})
    unrelated.pop('ui_progress_record')
    task = {'id': 'task', 'project_id': p['id'], 'created': 100, 'revision': 2,
            'intent': 'pause', 'node_ids': ['node']}
    node = {'id': 'node', 'task_id': 'task', 'state': 'paused'}
    counts = {'passed': 3, 'failed': 1, 'partial': 3, 'not_run': 47}
    reads = []
    def load(store, owner, pid, eid):
        reads.append(pid)
        return {'revision': 7, 'report_id': 'saved-report',
                'cases': [{'status': status} for status, count in counts.items() for _ in range(count)]}
    monkeypatch.setattr('api_test_tool.ui_records.load', load)
    from types import SimpleNamespace
    progress = project_progress(SimpleNamespace(project_dir=lambda *_: tmp_path), 'owner', p,
                                {'tasks': [task], 'nodes': [node]}, [p, unrelated])
    assert progress['phase'] == 'paused' and not progress['active']
    assert progress['case_counts'] == counts
    assert progress['modules'][0]['revision'] == 7 and progress['modules'][0]['report_saved']
    assert reads == ['current']


def test_completed_report_correction_updates_only_current_result_and_keeps_exit_history():
    from contextlib import contextmanager
    from types import SimpleNamespace
    from api_test_tool.managed_workflow import ManagedWorkflow
    p = _record_project('current', {'partial':1}, revision=3)
    node = {'id':'node','owner':'owner','task_id':'task','state':'completed','result':'failed',
            'record_project_id':'current','record_execution_id':p['ui_execution_id'],
            'actor_seen':100,'native_browser_stopped':True,'outcome_history':[{'result':'failed','at':100}],
            'coverage_complete':False}
    state={'nodes':{'node':node},'leases':{},'tasks':{'task':{'project_id':'root','node_ids':['node']}}}
    @contextmanager
    def transaction(): yield None,state
    workflow=ManagedWorkflow(SimpleNamespace(store=SimpleNamespace(get_project=lambda o,pid:p),
        controller=SimpleNamespace(transaction=transaction,clock=lambda:200)))
    saved={'execution_id':p['ui_execution_id'],'revision':3,
           'execution_plan':{'execution_summary':{'status_counts':{'partial':1}}}}
    workflow.record_activity('owner','current',saved)
    assert node['result']=='partial' and node['state']=='completed'
    assert node['native_browser_stopped'] and node['actor_seen']==100 and not state['leases']
    assert node['outcome_history']==[{'result':'failed','at':100}]
    assert node['record_revision']==3 and len(node['result_corrections'])==1
    workflow.record_activity('owner','current',saved)
    assert len(node['result_corrections'])==1
    workflow.record_activity('owner','current',{**saved,'revision':2})
    assert node['result']=='partial'
    # New execution or a still-owned lease cannot rewrite this ended attempt.
    node['record_revision']=1;node['result']='failed'
    state['leases']['l']={'node_id':'node'}
    workflow.record_activity('owner','current',saved)
    assert node['result']=='failed'
    state['leases'].clear();node['record_execution_id']='historical'
    workflow.record_activity('owner','current',saved)
    assert node['result']=='failed'
