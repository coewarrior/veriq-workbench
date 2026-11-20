"""Native finalization receipts without browser, model or network activity."""
from pathlib import Path

import pytest

from api_test_tool import direct_wait, ui_finalization, ui_records
from api_test_tool.managed_service import ManagedService
from api_test_tool.native_execution import NativeExecution
from test_native_scheduler import setup
from test_native_contexts import environment as browser_environment


STATIC = Path(__file__).parents[2] / 'api_test_tool' / 'static'


def test_unconfirmed_save_releases_without_publishing_or_finalizing(tmp_path, monkeypatch):
    c, service, owner, project, task_id, saved = prepare(tmp_path)
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': task_id, 'holder_id': 'original-holder',
        'arguments': {'browser_environment': browser_environment(isolated=True)}})
    def forbidden(*args): raise AssertionError('Must not publish unknown observations')
    monkeypatch.setattr(ui_finalization, 'begin', forbidden)
    monkeypatch.setattr(service, 'finalize_settlement', forbidden)
    result = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original-holder',
        'lease_id': claim['lease_id'], 'reason': 'Own pages closed; save unknown',
        'arguments': {'browser_stopped': True, 'save_unconfirmed': True, 'result': 'partial'}})
    assert result['released'] and not c.snapshot(owner)['leases']
    assert result['publication']['phase'] == 'blocked'


def test_saved_closeout_releases_before_reporting_and_keeps_exit_on_report_failure(tmp_path, monkeypatch):
    c, service, owner, project, task_id, saved = prepare(tmp_path)
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': task_id, 'holder_id': 'original-holder',
        'arguments': {'browser_environment': browser_environment(isolated=True)}})
    observed = []
    def broken_report(*args):
        observed.append(c.snapshot(owner)['leases'])
        raise OSError('report storage unavailable')
    monkeypatch.setattr(ui_finalization, 'begin', broken_report)
    result = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original-holder',
        'lease_id': claim['lease_id'], 'reason': 'Own pages closed',
        'arguments': {'browser_stopped': True, 'publish_saved': True}})
    assert observed == [[]]
    assert result['released'] and not c.snapshot(owner)['leases']
    assert result['publication']['phase'] == 'failed'
    assert ui_records.load(c.store, owner, project['id'], saved['execution_id'])['revision'] == saved['revision']
    assert c.snapshot(owner)['nodes'][0]['finalization_pending']


def test_saved_closeout_uses_existing_results_without_metadata_rewrite(tmp_path, monkeypatch):
    c, service, owner, project, task_id, saved = prepare(tmp_path)
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': task_id, 'holder_id': 'original-holder',
        'arguments': {'browser_environment': browser_environment(isolated=True)}})
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report', lambda *args: {'status': 'disabled'})
    result = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original-holder',
        'lease_id': claim['lease_id'], 'reason': 'Own pages closed',
        'arguments': {'browser_stopped': True, 'publish_saved': True}})
    assert result['released'] and result['publication']['phase'] == 'published'
    assert result['publication']['revision'] == saved['revision']
    assert [case['status'] for case in ui_records.load(c.store, owner, project['id'], saved['execution_id'])['cases']] == ['not_run', 'not_run']
    assert not c.snapshot(owner)['nodes'][0].get('finalization_pending')
    def forbidden(*args):
        raise AssertionError('The published original round must not be finalized again')
    monkeypatch.setattr(service, 'finalize_settlement', forbidden)
    service.finalize_pending()
    assert set(result['server_processing_timing']) == {
        'authorization_wait_and_read_seconds', 'authorization_commit_seconds',
        'return_account_seconds', 'schedule_seconds', 'settlement_response_seconds', 'publication_seconds',
        'publication_detail_seconds'}


def test_completion_combines_progress_and_intent_after_notification_marker(tmp_path, monkeypatch):
    c, service, owner, project, task_id, saved = prepare(tmp_path)
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': task_id, 'holder_id': 'original-holder',
        'arguments': {'browser_environment': browser_environment(isolated=True)}})
    history = [{'phase': 'reading', 'index': index} for index in range(30)] + [{'phase': 'completed'}]
    c.store.update_project(owner, project['id'], {'mcp_progress': {'history': history}})
    writes, notifications = [], []
    update = c.store.update_project
    def observe_update(owner, pid, changes):
        writes.append(set(changes))
        return update(owner, pid, changes)
    monkeypatch.setattr(c.store, 'update_project', observe_update)
    def notify(self, owner, pid, rid, kind):
        marker = c.store.get_project(owner, pid)['ui_final_report']
        assert marker == {'execution_id': saved['execution_id'], 'revision': saved['revision']}
        notifications.append(rid)
        return {'status': 'disabled'}
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report', notify)
    def duplicate_read(*args):
        raise AssertionError('The fresh verified begin result should be reused')
    monkeypatch.setattr(NativeExecution, 'publication', duplicate_read)
    result = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original-holder',
        'lease_id': claim['lease_id'], 'reason': 'Own pages closed',
        'arguments': {'browser_stopped': True, 'publish_saved': True}})
    assert result['publication']['phase'] == 'published'
    assert writes.count({'mcp_progress', 'ui_finish_request'}) == 1
    assert not any(fields == {'mcp_progress'} for fields in writes)
    current = c.store.get_project(owner, project['id'])
    assert len(current['mcp_progress']['history']) == 30
    assert current['mcp_progress']['history'][-2]['index'] == 29
    assert current['mcp_progress']['history'][-1]['phase'] == 'completed'
    measured = result['publication']['processing_timing']
    assert measured['completion_total_seconds'] >= measured['completion_before_commit_seconds']
    assert measured['final_commit_seconds'] >= 0
    assert measured['tool_timing_read_seconds'] >= 0
    assert len(notifications) == 1


@pytest.mark.parametrize('change', ['result_revision', 'new_execution', 'deleted', 'failed', 'node_revision'])
def test_published_closeout_does_not_clear_changed_pending_settlement(tmp_path, monkeypatch, change):
    c, service, owner, project, task_id, saved = prepare(tmp_path)
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': task_id, 'holder_id': 'original-holder',
        'arguments': {'browser_environment': browser_environment(isolated=True)}})
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report', lambda *args: {'status': 'disabled'})
    original_complete = service.complete_published_settlement
    observed = []

    def race(owner, node, task, project, publication):
        if change == 'deleted':
            c.store.recycle_project(owner, project['id'])
        elif change == 'result_revision':
            c.store.update_project(owner, project['id'], {'ui_execution_revision': publication['revision'] + 1})
        elif change == 'new_execution':
            c.store.update_project(owner, project['id'], {'ui_execution_id': 'new-execution'})
        elif change == 'failed':
            current = c.store.get_project(owner, project['id'])
            intent = current['ui_finish_request']
            intent['error'] = 'new publication error'
            c.store.update_project(owner, project['id'], {'ui_finish_request': intent})
        else:
            with c.transaction() as (_, state):
                state['nodes'][node['id']]['revision'] += 1
        observed.append(original_complete(owner, node, task, project, publication))

    monkeypatch.setattr(service, 'complete_published_settlement', race)
    result = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original-holder',
        'lease_id': claim['lease_id'], 'reason': 'Own pages closed',
        'arguments': {'browser_stopped': True, 'publish_saved': True}})
    assert result['released']
    assert observed == [False]
    assert c.snapshot(owner)['nodes'][0]['finalization_pending']


def test_late_settlement_callback_reuses_exact_published_receipt(tmp_path, monkeypatch):
    c, service, owner, project, task_id, saved = prepare(tmp_path)
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': task_id, 'holder_id': 'original-holder',
        'arguments': {'browser_environment': browser_environment(isolated=True)}})
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report', lambda *args: {'status': 'disabled'})
    result = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original-holder',
        'lease_id': claim['lease_id'], 'reason': 'Own pages closed',
        'arguments': {'browser_stopped': True, 'publish_saved': True}})
    with c.transaction() as (_, state):
        state['nodes'][result['node_id']]['finalization_pending'] = True
    def forbidden(*args):
        raise AssertionError('The completed publication must not be processed again')
    monkeypatch.setattr(ui_finalization, 'complete', forbidden)
    service.finalize_settlement(owner, result['node_id'])
    node = c.snapshot(owner)['nodes'][0]
    assert not node.get('finalization_pending')
    assert not node.get('report_error')


def test_pending_marker_cleanup_failure_keeps_actual_published_receipt(tmp_path, monkeypatch):
    c, service, owner, project, task_id, saved = prepare(tmp_path)
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': task_id, 'holder_id': 'original-holder',
        'arguments': {'browser_environment': browser_environment(isolated=True)}})
    publications = []
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report',
                        lambda *args: publications.append(True) or {'status': 'disabled'})
    def unavailable(*args):
        raise OSError('settlement write unavailable')
    monkeypatch.setattr(service, 'complete_published_settlement', unavailable)
    result = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original-holder',
        'lease_id': claim['lease_id'], 'reason': 'Own pages closed',
        'arguments': {'browser_stopped': True, 'publish_saved': True}})
    assert result['released'] and result['publication']['phase'] == 'published'
    assert result['publication']['warning']
    assert publications == [True]
    assert c.snapshot(owner)['nodes'][0]['finalization_pending']
    assert ui_finalization.status(c.store.get_project(owner, project['id']))['phase'] == 'published'
    service.finalize_pending()
    assert publications == [True]
    assert c.snapshot(owner)['nodes'][0]['finalization_pending']
    assert ui_finalization.status(c.store.get_project(owner, project['id']))['phase'] == 'published'


def test_combined_native_finish_saves_metadata_publishes_once_and_keeps_untested(tmp_path, monkeypatch):
    c, service, owner, project, task_id, saved = prepare(tmp_path)
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': task_id, 'holder_id': 'original-holder',
        'arguments': {'browser_environment': browser_environment(isolated=True)}})
    notifications = []
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report',
                        lambda self, *args: notifications.append(args) or {'status': 'disabled'})
    request = {'action': 'finish', 'holder_id': 'original-holder', 'lease_id': claim['lease_id'],
        'reason': 'Own pages actually closed', 'arguments': {'browser_stopped': True,
            'final_report': {'project_id': project['id'], 'execution_id': saved['execution_id'],
                'revision': saved['revision'], 'summary': 'Partial verification only',
                'scene_outcome': {'status': 'cleaned', 'items': []},
                'experiment': {'execution_finished_at': '2026-10-21T01:00:00Z'}}}}
    result = service.direct.call(owner, request)
    assert result['released'] and not c.snapshot(owner)['leases']
    assert result['publication']['phase'] == 'published'
    assert result['publication']['revision'] == saved['revision'] + 1
    record = ui_records.load(c.store, owner, project['id'], saved['execution_id'])
    assert [case['status'] for case in record['cases']] == ['not_run', 'not_run']
    assert record['experiment']['execution_finished_at'] == '2026-10-21T01:00:00Z'
    assert service.direct.call(owner, request)['released']
    assert len(notifications) == 1
    assert ui_records.load(c.store, owner, project['id'], saved['execution_id'])['revision'] == record['revision']


def test_combined_finish_cannot_save_before_exit_or_to_another_record(tmp_path):
    import pytest
    from api_test_tool.orchestration import Conflict
    c, service, owner, project, task_id, saved = prepare(tmp_path)
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': task_id, 'holder_id': 'original-holder',
        'arguments': {'browser_environment': browser_environment(isolated=True)}})
    request = {'action': 'finish', 'holder_id': 'original-holder', 'lease_id': claim['lease_id'],
               'reason': 'closeout', 'arguments': {'final_report': {'project_id': 'another'}}}
    assert service.direct.call(owner, request)['released'] is False
    request['arguments']['browser_stopped'] = True
    with pytest.raises(Conflict):
        service.direct.call(owner, request)
    assert c.snapshot(owner)['leases']
    assert not c.store.get_project(owner, project['id']).get('ui_finish_request')
    request['arguments'].update(result={'passed': 1}, final_report={
        'project_id': project['id'], 'execution_id': saved['execution_id'],
        'revision': saved['revision'], 'scene_outcome': {'status': 'cleaned', 'items': []}})
    with pytest.raises(ValueError, match='result'):
        service.direct.call(owner, request)
    assert c.snapshot(owner)['leases']
    assert not c.store.get_project(owner, project['id']).get('ui_finish_request')
    assert ui_records.load(c.store, owner, project['id'], saved['execution_id'])['revision'] == saved['revision']
    from api_test_tool.native_client import handoff_arguments
    with pytest.raises(ValueError, match='result'):
        handoff_arguments(request)


def prepare(tmp_path, accounts=1):
    controller, owner, project, clock, task_id = setup(tmp_path, accounts=accounts, modules=1)
    service = ManagedService(controller, STATIC)
    saved = ui_records.save_cases(controller.store, owner, project['id'], [
        {'case_id': 'A', 'scenario': 'observed prerequisite', 'status': 'not_run'},
        {'case_id': 'B', 'scenario': 'remaining original design', 'status': 'not_run'},
    ])
    return controller, service, owner, project, task_id, saved


def test_native_finish_workflow_keeps_exit_pending_and_saves_once(tmp_path, monkeypatch):
    c, service, owner, project, task_id, saved = prepare(tmp_path)
    claim = service.direct.call(owner, {
        'action': 'claim', 'task_id': task_id, 'holder_id': 'original-holder',
        'arguments': {'browser_environment': browser_environment(isolated=True)},
        'executor_ref': 'thread:01a152f7-e927-7373-825c-e77eec1a1fd9',
    })
    notifications = []
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report',
                        lambda self, *args: notifications.append(args) or {'status': 'disabled'})
    arguments = {
        'execution_id': saved['execution_id'], 'revision': saved['revision'],
        'request_id': 'native-finish-once', 'summary': 'Keep actual incomplete coverage.',
        'cases': [{'case_id': 'A', 'status': 'blocked', 'actual': 'prerequisite unavailable'}],
    }
    calls = []

    def invoke(action, values):
        calls.append(action)
        assert action == 'finish_workflow', 'Native cleanup must not poll.'
        return ui_finalization.begin(service, owner, c.store.get_project(owner, project['id']), values)

    pending = direct_wait.lifecycle_call_and_wait(invoke, 'finish_workflow', {
        **arguments, 'project_id': project['id'],
    })
    assert calls == ['finish_workflow']
    assert pending['pending'] and pending['manual_stop_required']
    assert not pending['client_wait']['pending']
    assert 'resume_tool' not in pending['client_wait']
    assert pending['required_sessions'][0]['lease_id'] == claim['lease_id']
    assert pending['required_sessions'][0]['thread_url'].startswith('codex://threads/')
    assert not pending['required_sessions'][0]['executor_exit_confirmed']
    assert not pending['required_sessions'][0]['desktop_api_cancelled']
    current = c.store.get_project(owner, project['id'])
    persisted = ui_finalization.status(current)
    assert persisted['required_sessions'] == pending['required_sessions']
    assert not current.get('last_analysis') and not notifications
    assert ui_finalization.begin(service, owner, current, arguments) == persisted
    record = ui_records.load(c.store, owner, project['id'], saved['execution_id'])
    assert record['revision'] == saved['revision'] + 1
    assert [case['status'] for case in record['cases']] == ['blocked', 'not_run']
    assert c.snapshot(owner, task_id)['leases'][0]['id'] == claim['lease_id']

    finished = service.direct.call(owner, {
        'action': 'finish', 'holder_id': 'original-holder', 'lease_id': claim['lease_id'],
        'arguments': {'browser_stopped': True, 'reason': 'Synthetic task pages closed.'},
    })
    assert finished['released']
    published = ui_finalization.status(c.store.get_project(owner, project['id']))
    assert published['phase'] == 'published' and not published['pending']
    assert 'manual_stop_required' not in published
    assert published['execution_settlement']['released']
    assert ui_finalization.begin(service, owner, c.store.get_project(owner, project['id']), arguments) == published
    assert len(notifications) == 1
    node = c.snapshot(owner, task_id)['nodes'][0]
    assert node['result'] == 'partial' and not node['coverage_complete']
    assert [case['status'] for case in ui_records.load(
        c.store, owner, project['id'], saved['execution_id'])['cases']] == ['blocked', 'not_run']


def test_s1_unleased_holder_still_requires_actual_exit(tmp_path):
    c, service, owner, project, task_id, saved = prepare(tmp_path, accounts=0)
    claim = service.direct.call(owner, {
        'action': 'claim', 'task_id': task_id, 'holder_id': 'waiting-holder',
        'arguments': {'browser_environment': browser_environment(isolated=True)},
    })
    assert not claim['lease_id']
    c.control(owner, task_id, {'action': 'stop', 'revision': 1, 'request_id': 's1-stop'})
    arguments = {'execution_id': saved['execution_id'], 'request_id': 'finish-stopped',
                 'summary': 'No account allocated; preserve unexecuted cases.'}
    pending = ui_finalization.begin(service, owner, c.store.get_project(owner, project['id']), arguments)
    assert pending['manual_stop_required'] and pending['pending']
    row = pending['required_sessions'][0]
    assert row['lease_id'] is None and row['accounts_released']
    assert not row['executor_exit_confirmed']
    assert not c.store.get_project(owner, project['id']).get('last_analysis')
    task = c.snapshot(owner, task_id)['tasks'][0]
    NativeExecution(service.direct).confirm_exit(owner, task_id, {
        'revision': task['revision'], 'node_ids': [claim['node_id']],
        'executor_stopped': True, 'browser_stopped': True,
        'reason': 'User confirmed the original desktop turn is stopped.',
    })
    published = ui_finalization.complete(service, owner, project['id'])
    assert published['phase'] == 'published' and not published['pending']
    assert all(case['status'] == 'not_run' for case in ui_records.load(
        c.store, owner, project['id'], saved['execution_id'])['cases'])


def test_unclaimed_native_module_returns_closeout_without_poll_or_fake_stop(tmp_path):
    c, service, owner, project, task_id, saved = prepare(tmp_path, accounts=0)
    calls = []

    def invoke(action, values):
        calls.append(action)
        assert action == 'finish_workflow', 'An unclaimed module cannot finish by polling.'
        return ui_finalization.begin(service, owner, c.store.get_project(owner, project['id']), values)

    pending = direct_wait.lifecycle_call_and_wait(invoke, 'finish_workflow', {
        'project_id': project['id'], 'execution_id': saved['execution_id'],
        'summary': 'Original module has not been claimed.', 'request_id': 'finish-unclaimed',
    })
    assert calls == ['finish_workflow']
    assert pending['native_closeout_required'] and not pending['manual_stop_required']
    assert pending['required_sessions'] == []
    assert pending['required_modules'][0]['task_id'] == task_id
    assert pending['next_action'] == 'finish_unallocated'
    assert not pending['client_wait']['pending']
    assert 'resume_tool' not in pending['client_wait']
    assert c.snapshot(owner, task_id)['nodes'][0]['state'] == 'queued'
    assert not c.store.get_project(owner, project['id']).get('last_analysis')
