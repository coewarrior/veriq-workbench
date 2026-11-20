"""A stopped module's existing legacy report can settle its pure parent."""
import json

import pytest

from api_test_tool import ui_records
from api_test_tool.deployment_activity import activity
from test_native_finalization import prepare, browser_environment


@pytest.mark.parametrize('invalid', [None, 'missing_report', 'changed_record',
    'changed_snapshot', 'unknown_exit', 'pending_control', 'new_request', 'child_pending'])
def test_mixed_stop_reports_settle_parent_only_with_complete_original_evidence(tmp_path, monkeypatch, invalid):
    c, service, owner, _, tid, _ = prepare(tmp_path)
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report', lambda *args: {'status': 'disabled'})
    parent = c.snapshot(owner)['nodes'][0]
    children = c.split(owner, parent['id'], {'revision': parent['revision'], 'children': [
        {'key': 'a', 'title': 'A', 'scope': 'A'}, {'key': 'b', 'title': 'B', 'scope': 'B'}]})['child_ids']
    for index, nid in enumerate(children):
        identity = {'task_id': tid, 'node_id': nid, 'holder_id': 'child-' + str(index),
            'dispatch_id': 'dispatch-' + str(index), 'executor_ref': 'thread:child-' + str(index)}
        service.direct.call(owner, {'action': 'dispatch', 'task_id': tid, 'holder_id': 'coordinator',
            'request_id': 'dispatch-' + str(index), 'arguments': {'modules': [identity]}})
        claim = service.direct.call(owner, {**identity, 'action': 'claim',
            'arguments': {'browser_environment': browser_environment('context-' + str(index), True)}})
        identity['lease_id'] = claim['lease_id']
        context = service.direct.call(owner, {**identity, 'action': 'context'})
        service.direct.call(owner, {**identity, 'action': 'record', 'record_action': 'cases',
            'arguments': {'cases': [{'case_id': context['case_id_prefix'] + '001',
                'scenario': 'Original assertion', 'status': 'not_run'}]}})
        if index:
            task = c.snapshot(owner)['tasks'][0]
            c.control(owner, tid, {'action': 'stop', 'revision': task['revision'], 'request_id': 'stop'})
        service.direct.call(owner, {**identity, 'action': 'finish', 'reason': 'Own browser closed',
            'arguments': {'browser_stopped': True, **({'publish_saved': True} if not index else {})}})
    node = next(n for n in c.snapshot(owner)['nodes'] if n['id'] == children[1])
    directory = c.store.project_dir(owner, node['record_project_id'])
    record_path = directory / 'ui-executions' / node['record_execution_id'] / 'cases.json'
    record = json.loads(record_path.read_text())
    report_path = directory / 'analyses' / record['report_id'] / 'report.json'
    assert not c.store.get_project(owner, node['record_project_id']).get('ui_finish_request')
    if invalid == 'missing_report':
        report_path.unlink()
    elif invalid in {'changed_record', 'changed_snapshot'}:
        path = record_path if invalid == 'changed_record' else report_path
        value = json.loads(path.read_text())
        (value if invalid == 'changed_record' else value['ui_snapshot'])['revision'] += 1
        c.store._write(path, value)
    elif invalid == 'new_request':
        c.store.update_project(owner, node['record_project_id'], {'ui_finish_request': {
            'execution_id': node['record_execution_id'], 'request_id': 'new-report'}})
    elif invalid:
        with c.transaction() as (_, state):
            current = state['nodes'][node['id']]
            if invalid == 'unknown_exit':
                current['native_browser_stopped'] = False
            elif invalid == 'pending_control':
                current['executor_controls'] = {'stop': {'state': 'pending'}}
            else:
                current['finalization_pending'] = True
    before = {p: p.read_bytes() for p in (c.store.root / 'sessions').rglob('*') if p.is_file()}
    def forbidden(*args, **kwargs):
        raise AssertionError('Existing reports must never be republished for parent cleanup')
    monkeypatch.setattr(ui_records, 'publish', forbidden)
    assert (activity(c.store.root)['finalizations'] == 0) is (invalid is None)
    service.finalize_settlement(owner, parent['id'])
    current = next(n for n in c.snapshot(owner)['nodes'] if n['id'] == parent['id'])
    assert bool(current.get('finalization_pending')) is bool(invalid)
    assert not current.get('record_project_id')
    assert all(p.read_bytes() == content for p, content in before.items())
