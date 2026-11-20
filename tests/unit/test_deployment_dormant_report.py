import json
import copy

import pytest

from api_test_tool.deployment_activity import activity, dormant_native_report, published_settlement


@pytest.fixture
def saved_after_publication(tmp_path):
    owner = 'a' * 64
    node = {'id': 'node', 'owner': owner, 'task_id': 'task', 'state': 'completed',
            'revision': 5, 'record_project_id': 'project', 'record_execution_id': 'execution',
            'native_browser_stopped': True, 'native_report_pending': {'lease_id': 'lease'},
            'executor_dispatch': {'holder_id': 'holder', 'dispatch_id': 'dispatch',
                                  'exit_acknowledged_at': 123}}
    state = {'tasks': {'task': {'id': 'task', 'owner': owner, 'execution_route': 'native_browser'}},
             'nodes': {'node': node}, 'leases': {},
             'direct_settlements': {'lease': {'owner': owner, 'node_id': 'node', 'holder_id': 'holder',
                 'native_browser': True, 'ack_required': False, 'report_binding': {
                     'task_id': 'task', 'node_revision': 5, 'project_id': 'project',
                     'execution_id': 'execution', 'dispatch_id': 'dispatch'}}}}
    project = {'id': 'project', 'ui_execution_id': 'execution', 'ui_execution_revision': 12,
               'ui_final_report': {'execution_id': 'execution', 'revision': 10},
               'ui_finish_request': {'execution_id': 'execution', 'revision': 10, 'request_id': 'finish',
                   'result': {'phase': 'published', 'pending': False, 'execution_id': 'execution',
                              'revision': 10, 'request_id': 'finish', 'report': {'id': 'report'}}}}
    record = {'id': 'execution', 'revision': 12, 'published_revision': 10, 'report_id': 'report'}
    report = {'ui_snapshot': {'id': 'execution', 'revision': 10}}
    directory = tmp_path / 'sessions' / owner / 'projects' / 'project'
    files = {directory / 'metadata.json': project,
             directory / 'ui-executions' / 'execution' / 'cases.json': record,
             directory / 'analyses' / 'report' / 'report.json': report}

    def save():
        for path, value in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value))

    save()
    return tmp_path, node, state, project, record, report, save, files


@pytest.mark.parametrize('published_revision', [10, 12])
def test_completed_earlier_finish_does_not_make_exited_new_draft_active(saved_after_publication, published_revision):
    root, node, state, project, record, report, save, files = saved_after_publication
    record['published_revision'] = report['ui_snapshot']['revision'] = published_revision
    save()
    before = {path: path.read_bytes() for path in files}
    assert not dormant_native_report(root, node, state)
    assert dormant_native_report(root, node, state, allow_completed_earlier_finish=True)
    assert not published_settlement(root, node, state)
    assert {path: path.read_bytes() for path in files} == before
    assert node['native_report_pending'] == {'lease_id': 'lease'}


@pytest.mark.parametrize('change', [
    'current_request', 'future_request', 'pending', 'error', 'different_execution',
    'different_request', 'different_final', 'wrong_record', 'wrong_report', 'wrong_snapshot',
    'future_snapshot', 'bool_revision', 'missing_report', 'lease', 'browser_alive', 'missing_exit',
    'wrong_binding',
])
@pytest.mark.parametrize('legacy_error', [False, True])
def test_incomplete_or_conflicting_evidence_still_blocks(saved_after_publication, change, legacy_error):
    root, node, state, project, record, report, save, files = saved_after_publication
    if legacy_error:
        node['report_error'] = '最终报告生成未完成；原始用例保留，账号不因此占用。可重试交还回执以重试报告。'
    intent = project['ui_finish_request']
    if change == 'current_request': intent['revision'] = 12
    elif change == 'future_request': intent['revision'] = 13
    elif change == 'pending': intent['result']['pending'] = True
    elif change == 'error': intent['error'] = 'failed'
    elif change == 'different_execution': intent['execution_id'] = 'other'
    elif change == 'different_request': intent['result']['request_id'] = 'other'
    elif change == 'different_final': project['ui_final_report']['revision'] = 9
    elif change == 'wrong_record': record['revision'] = 11
    elif change == 'wrong_report': record['report_id'] = 'other'
    elif change == 'wrong_snapshot': report['ui_snapshot']['revision'] = 11
    elif change == 'future_snapshot': record['published_revision'] = report['ui_snapshot']['revision'] = 13
    elif change == 'bool_revision': intent['revision'] = True
    elif change == 'lease': state['leases']['lease'] = {'node_id': 'node'}
    elif change == 'browser_alive': node['native_browser_stopped'] = False
    elif change == 'missing_exit': node['executor_dispatch'].pop('exit_acknowledged_at')
    elif change == 'wrong_binding': state['direct_settlements']['lease']['report_binding']['node_revision'] = 4
    save()
    if change == 'missing_report': next(path for path in files if path.name == 'report.json').unlink()
    assert not dormant_native_report(root, node, state, allow_completed_earlier_finish=True)


def test_unrequested_draft_keeps_existing_behavior(saved_after_publication):
    root, node, state, project, record, report, save, files = saved_after_publication
    project.pop('ui_finish_request')
    project.pop('ui_final_report')
    save()
    assert dormant_native_report(root, node, state)


@pytest.mark.parametrize('complete', [True, False])
def test_activity_classifies_only_proven_idle_work_without_writing(saved_after_publication, complete, postgres_database):
    root, node, state, project, record, report, save, files = saved_after_publication
    state['version'] = 1
    state['tasks']['task']['intent'] = 'stop'
    node.update(project_id='project', finalization_pending=True)
    if not complete:
        project['ui_finish_request']['result']['pending'] = True
    save()
    postgres_database.replace_state(root, state)
    stored = postgres_database.contents(root)
    before = {path: path.read_bytes() for path in files}
    counts = activity(root)
    assert postgres_database.contents(root) == stored
    assert counts['rounds'] == counts['channels'] == counts['acknowledgements'] == 0
    assert counts['finalizations'] == (0 if complete else 1)
    assert counts.get('dormant_reports', 0) == (1 if complete else 0)
    assert {path: path.read_bytes() for path in before} == before


def test_completed_old_request_with_legacy_callback_error_is_idle_without_mutation(saved_after_publication):
    root, node, state, project, record, report, save, files = saved_after_publication
    node.update(finalization_pending=True, report_error='最终报告生成未完成；原始用例保留，账号不因此占用。可重试交还回执以重试报告。')
    before = json.dumps(state, sort_keys=True)
    assert dormant_native_report(root, node, state, allow_completed_earlier_finish=True)
    assert not dormant_native_report(root, node, state)
    assert json.dumps(state, sort_keys=True) == before
    project['ui_finish_request']['error'] = 'actual publication failure'
    save()
    assert not dormant_native_report(root, node, state, allow_completed_earlier_finish=True)

    project['ui_finish_request'].pop('error')
    save()
    node['report_error'] = 'different unverified error'
    assert not dormant_native_report(root, node, state, allow_completed_earlier_finish=True)
    node['report_error'] = '最终报告生成未完成；原始用例保留，账号不因此占用。可重试交还回执以重试报告。'
    project.pop('ui_finish_request')
    save()
    assert not dormant_native_report(root, node, state, allow_completed_earlier_finish=True)


@pytest.mark.parametrize('change', [None, 'live_successor', 'missing_exit', 'browser_alive',
    'lease', 'pending_control', 'pending_publication', 'pending_marker', 'missing_report',
    'wrong_parent', 'foreign_task', 'foreign_owner', 'wrong_record', 'broken_link',
    'parent_executed', 'missing_child', 'not_stopped'])
def test_stopped_split_with_cancelled_continuation_is_idle_only_with_complete_proof(
        saved_after_publication, change, postgres_database):
    root, node, state, project, record, report, save, files = saved_after_publication
    task = state['tasks']['task']
    task.update(intent='stop', project_id='parent-project', node_ids=['parent', 'node', 'next'])
    node.update(parent_id='parent', project_id='parent-project', attempts=[{'lease_id': 'old'}],
                record_successor_node_id='next')
    node.pop('native_report_pending')
    successor = {**copy.deepcopy(node), 'id': 'next', 'state': 'stopped', 'attempts': [],
                 'continuation_source': {'source_task_id': 'task', 'source_node_id': 'node',
                                        'project_id': 'project', 'execution_id': 'execution'}}
    successor.pop('native_browser_stopped')  # Never acquired a browser for this phase.
    successor.pop('record_successor_node_id')
    parent = {'id': 'parent', 'owner': node['owner'], 'task_id': 'task', 'project_id': 'parent-project',
              'state': 'completed', 'child_ids': ['node', 'next'], 'finalization_pending': True}
    state['nodes'].update(parent=parent, next=successor)
    state['version'] = 1
    project['managed_parent_project_id'] = 'parent-project'
    files[root / 'sessions' / node['owner'] / 'projects' / 'parent-project' / 'metadata.json'] = {'id': 'parent-project'}
    if change == 'live_successor': successor['state'] = 'running'
    elif change == 'missing_exit': successor['executor_dispatch'].pop('exit_acknowledged_at')
    elif change == 'browser_alive': node['native_browser_stopped'] = False
    elif change == 'lease': state['leases']['active'] = {'node_id': 'next'}
    elif change == 'pending_control': successor['executor_controls'] = {'stop': {'state': 'pending'}}
    elif change == 'pending_publication': project['ui_finish_request']['result']['pending'] = True
    elif change == 'pending_marker': successor['finalization_pending'] = True
    elif change == 'wrong_parent': project['managed_parent_project_id'] = 'other'
    elif change == 'foreign_task':
        state['tasks']['other'] = {**task, 'id': 'other'}
        successor['task_id'] = 'other'
    elif change == 'foreign_owner': successor['owner'] = 'b' * 64
    elif change == 'wrong_record': successor['record_execution_id'] = 'other'
    elif change == 'broken_link': successor['continuation_source']['source_node_id'] = 'missing'
    elif change == 'parent_executed': parent['attempts'] = [{'lease_id': 'parent-lease'}]
    elif change == 'missing_child': parent['child_ids'].remove('next')
    elif change == 'not_stopped': task['intent'] = 'run'
    save()
    if change == 'missing_report': next(p for p in files if p.name == 'report.json').unlink()
    postgres_database.replace_state(root, state)
    stored = postgres_database.contents(root)
    before = {p: p.read_bytes() for p in files if p.exists()}
    assert activity(root)['finalizations'] == (0 if change is None else 1 + (change == 'pending_marker'))
    assert postgres_database.contents(root) == stored
    assert all(p.read_bytes() == data for p, data in before.items())
    assert parent['finalization_pending'] is True
