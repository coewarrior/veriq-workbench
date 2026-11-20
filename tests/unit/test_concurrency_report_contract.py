"""Isolated recorded-state checks; no browser, model or tested application calls."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest

from api_test_tool import ui_records, ui_total_reports
from api_test_tool.module_dispatch import receive, command, observe_control, node_dispatch
from api_test_tool.orchestration import Controller, Conflict
from api_test_tool.shared_fixtures import apply_fixture
from api_test_tool.ui_case_results import annotate
from api_test_tool.ui_round_report import task_records
from api_test_tool.web_storage import Store


def setup(tmp_path):
    store = Store(tmp_path); session, _ = store.session(None); owner = session['id']
    root = store.create_project(owner, 'Complete module scope', 'scope.md', 'Synthetic scope')
    root = store.update_project(owner, root['id'], {'test_kind': 'ui', 'ui_target_url': 'https://example.test', 'task': {'goal': 'all modules'}})
    c = Controller(store)
    return store, owner, root, c


def case(cid, status='not_run'):
    return {'case_id': cid, 'scenario': cid, 'status': status, 'actual': 'observation' if status != 'not_run' else '',
        'steps': '1. Open synthetic page.', 'expected': 'synthetic expected', 'environment': 'test',
        'module': 'synthetic', 'client': 'B端'}


def new_task(c, owner, root, key):
    return c.create_task(owner, {'project_id': root['id'], 'request_id': key,
        'goal': 'all modules', 'execution_route': 'local_browser', 'session_workflow': True,
        'modules': [{'key': 'a', 'title': 'A', 'scope': 'A'}, {'key': 'b', 'title': 'B', 'scope': 'B'}]})['task_id']


def record_module(store, c, owner, root, task_id, node_id, cases):
    p = store.create_project(owner, 'A module', 'module.md', 'Synthetic')
    p = store.update_project(owner, p['id'], {'test_kind': 'ui', 'ui_target_url': 'https://example.test',
        'managed_node_id': node_id, 'managed_task_id': task_id, 'managed_parent_project_id': root['id']})
    saved = ui_records.save_cases(store, owner, p['id'], cases)
    with c.transaction() as (_, state):
        state['nodes'][node_id].update(record_project_id=p['id'], record_execution_id=saved['execution_id'])
    return p, saved


def test_total_contains_unpublished_and_stopped_modules_without_historical_passes(tmp_path):
    store, owner, root, c = setup(tmp_path)
    old_id = new_task(c, owner, root, 'old')
    old_node = c.snapshot(owner, old_id)['nodes'][0]
    old, old_saved = record_module(store, c, owner, root, old_id, old_node['id'], [case('old-case', 'passed')])
    ui_records.publish(store, owner, old, old_saved['execution_id'], 'old report', 'old round only')
    current_id = new_task(c, owner, root, 'new')
    nodes = c.snapshot(owner, current_id)['nodes']
    record_module(store, c, owner, root, current_id, nodes[0]['id'], [case('new-case')])
    with c.transaction() as (_, state):
        state['nodes'][nodes[1]['id']].update(state='stopped', reason='cancelled while queued')
    total = ui_total_reports.build(store, owner, root)
    assert total['task_id'] == current_id
    assert [m['title'] for m in total['modules']] == ['A', 'B']
    assert total['modules'][1]['state'] == 'stopped'
    assert [x['case_id'] for x in total['imported_results']['cases']] == ['new-case']
    assert total['stage_reports'] == []
    assert total['imported_results']['counts'] == {'not_run': 1, 'total': 1}
    from api_test_tool.task_reports import render_task_report
    page = render_task_report(total)
    assert 'cancelled while queued' in page and 'old-case' not in page


def test_split_parent_facts_stay_in_round_once(tmp_path):
    store, owner, root, c = setup(tmp_path)
    tid = new_task(c, owner, root, 'task')
    node = c.snapshot(owner, tid)['nodes'][0]
    p, saved = record_module(store, c, owner, root, tid, node['id'], [case('already-observed', 'failed')])
    with c.transaction() as (db, state):
        c._split(db, state, owner, state['nodes'][node['id']], [{'key': 'new', 'title': 'Remaining', 'scope': 'untouched'}])
    total = ui_total_reports.build(store, owner, root)
    assert total['imported_results']['counts'] == {'failed': 1, 'total': 1}
    parent = next(m for m in total['modules'] if m['node_id'] == node['id'])
    assert parent['fact_only'] is True
    assert any(m['title'] == 'Remaining' for m in total['modules'])


def test_every_batched_save_keeps_failure_before_finish_patch(tmp_path):
    store, owner, root, c = setup(tmp_path)
    saved = ui_records.save_cases(store, owner, root['id'], [case('case', 'failed')])
    updated = ui_records.save_cases(store, owner, root['id'], [{'case_id': 'case', 'status': 'passed', 'actual': 'retry success'}],
        saved['execution_id'], saved['revision'], refresh_report=False)
    record = ui_records.load(store, owner, root['id'], saved['execution_id'])
    result = annotate(record['cases'][0], record)
    assert result['managed_status'] == 'retry_passed'
    assert record['case_history'][str(saved['revision'])]['cases'][0]['status'] == 'failed'
    assert len(record['cases']) == 1
    assert updated['total'] == 1


def test_claim_receipt_is_not_browser_or_business_ack_and_control_uses_existing_call():
    node = {'id': 'n', 'revision': 1, 'state': 'queued'}
    receive({}, node, 'holder', 1)
    assert node_dispatch(node)['dispatch_state'] == 'waiting_resource'
    assert node_dispatch(node)['executor'].get('executor_ref') is None
    receive({}, node, 'holder', 2, executor_ref='agent:actual')
    command({}, node, 'stop', 3)
    observe_control(node, 'other-holder', 4)
    assert node_dispatch(node)['pending_controls'][0]['state'] == 'pending'
    observe_control(node, 'holder', 5)
    assert node_dispatch(node)['pending_controls'][0]['state'] == 'received'
    observe_control(node, 'holder', 6, exited=True)
    assert node_dispatch(node)['pending_controls'] == []
    assert node['executor_dispatch']['received_at'] == 1


def test_last_consumer_cleanup_is_serialized_with_new_acquire():
    nodes = {'creator': {'id': 'creator', 'owner': 'o', 'project_id': 'p', 'task_id': 't'},
             'consumer': {'id': 'consumer', 'owner': 'o', 'project_id': 'p', 'task_id': 't'}}
    def owned(values, owner, key):
        assert values[key]['owner'] == owner
        return values[key]
    c = SimpleNamespace(clock=lambda: 1, audit=lambda *args: None, owned=owned)
    s = {'fixtures': {}, 'nodes': nodes}
    def act(node, **data):
        return apply_fixture(c, None, s, 'o', nodes[node], data)
    f = act('creator', object_id='object', version='v1', cleanup_authorized=True, cleanup_authorization='original test cleanup')
    act('consumer', id=f['id'], version='v1')
    act('creator', id=f['id'], action='release')
    with pytest.raises(Conflict):
        act('creator', id=f['id'], action='prepare_cleanup', evidence='verified')
    f = act('consumer', id=f['id'], action='release')
    assert f['cleanup_ready']
    act('creator', id=f['id'], action='prepare_cleanup', evidence='no in-flight work or retained scene')
    with pytest.raises(Conflict):
        act('consumer', id=f['id'], version='v1')
    result = act('creator', id=f['id'], action='complete_cleanup', evidence='actual delete failed', succeeded=False)
    assert result['object_id'] == 'object' and result['cleanup_pending']
    assert result['cleanup_owner_node_id'] == 'creator'


def test_confirmed_executor_exit_is_distinct_from_an_unknown_disconnection():
    node = {'id': 'n', 'state': 'isolated', 'business_started_at': 1}
    assert node_dispatch(node)['dispatch_state'] == 'business_started'
    node['execution_ended'] = True
    assert node_dispatch(node)['dispatch_state'] == 'ended_resource_hold'


def test_round_evidence_links_to_its_actual_execution(tmp_path):
    import base64
    store, owner, root, c = setup(tmp_path)
    tid = new_task(c, owner, root, 'evidence')
    node = c.snapshot(owner, tid)['nodes'][0]
    project, saved = record_module(store, c, owner, root, tid, node['id'], [case('evidence-case')])
    asset = ui_records.add_asset(store, owner, project['id'], saved['execution_id'], 'evidence-case', '1',
        'observation.json', 'application/json', base64.b64encode(b'{"observed":true}').decode(), kind='observation')
    ui_records.publish(store, owner, project, saved['execution_id'], 'evidence report', 'saved evidence')
    total = ui_total_reports.build(store, owner, root)
    projected = total['ui_snapshot']['assets'][0]
    assert projected['url'] == '/api/ui-tests/%s/executions/%s/asset-%s' % (project['id'], saved['execution_id'], asset['id'])
    assert (ui_records.root_for(store, owner, project['id'], saved['execution_id']) / asset['id']).is_file()
