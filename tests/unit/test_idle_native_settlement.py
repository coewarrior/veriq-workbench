"""Waiting for report prose is idle; actual exit and report work stay distinct."""
from pathlib import Path

import pytest

from api_test_tool.deployment_activity import activity
from api_test_tool.managed_service import ManagedService
from test_native_finalization import prepare, browser_environment


def idle_round(tmp_path, before_finish=None):
    c, service, owner, project, tid, saved = prepare(tmp_path)
    node = c.snapshot(owner)['nodes'][0]
    service.direct.call(owner, {'action': 'dispatch', 'task_id': tid, 'holder_id': 'coordinator',
        'request_id': 'dispatch', 'arguments': {'modules': [{'node_id': node['id'],
            'holder_id': 'worker', 'dispatch_id': 'dispatch-one',
            'executor_ref': '01a17111-5ac7-79d0-9ac8-48eaaddc22b8'}]}})
    identity = {'holder_id': 'worker', 'node_id': node['id'], 'task_id': tid,
        'dispatch_id': 'dispatch-one', 'executor_ref': '01a17111-5ac7-79d0-9ac8-48eaaddc22b8'}
    claim = service.direct.call(owner, {**identity, 'action': 'claim',
        'arguments': {'browser_environment': browser_environment('context', True)}})
    service.direct.call(owner, {**identity, 'action': 'context', 'lease_id': claim['lease_id']})
    saved = service.direct.call(owner, {**identity, 'action': 'record', 'record_action': 'cases',
        'lease_id': claim['lease_id'], 'arguments': {'cases': [{
            'case_id': 'A', 'scenario': 'observed prerequisite', 'status': 'not_run'}], 'revision': saved['revision']}})
    if before_finish:
        before_finish(c, service, owner, project, saved)
    result = service.direct.call(owner, {**identity, 'action': 'finish', 'lease_id': claim['lease_id'],
        'reason': 'Own browser actually closed', 'arguments': {'browser_stopped': True, 'report_pending': True}})
    assert result['released']
    if not before_finish:
        assert result['publication']['phase'] == 'awaiting_report'
        assert result['publication']['pending'] is False
    return c, service, owner, project, node['id'], saved


def test_idle_report_is_not_queued_as_running_finalization(tmp_path):
    c, service, owner, project, nid, _ = idle_round(tmp_path)
    node = c.snapshot(owner)['nodes'][0]
    assert node['native_report_pending'] and not node.get('finalization_pending')
    assert not c.snapshot(owner)['leases']
    assert activity(c.store.root)['finalizations'] == 0
    assert not c.store.get_project(owner, project['id']).get('ui_finish_request')


@pytest.mark.parametrize('invalid', [None, 'unknown_exit', 'changed_generation', 'active_publication'])
def test_restart_reconciles_only_proven_idle_markers_without_changing_saved_reports(tmp_path, invalid):
    c, service, owner, project, nid, saved = idle_round(tmp_path)
    with c.transaction() as (_, state):
        node = state['nodes'][nid]
        node['finalization_pending'] = True  # Existing 0.17.98 persistent marker.
        if invalid == 'unknown_exit':
            node['native_browser_stopped'] = False
        elif invalid == 'changed_generation':
            node['revision'] += 1
    if invalid == 'active_publication':
        c.store.update_project(owner, project['id'], {'ui_finish_request': {
            'execution_id': saved['execution_id'], 'revision': saved['revision'], 'request_id': 'original'}})
    directory = c.store.project_dir(owner, project['id'])
    before = {p: p.read_bytes() for p in directory.rglob('*') if p.is_file()}
    restarted = ManagedService(c, Path(service.static))
    if invalid == 'active_publication':
        assert restarted.reconcile_idle_settlement(owner, nid) is False
    else:
        restarted.finalize_pending()
    node = next(n for n in c.snapshot(owner)['nodes'] if n['id'] == nid)
    assert node['native_report_pending']
    assert bool(node.get('finalization_pending')) is bool(invalid)
    assert all(p.read_bytes() == content for p, content in before.items())
    assert activity(c.store.root)['finalizations'] == int(bool(invalid))


@pytest.mark.parametrize('lost_marker', [False, True])
def test_explicit_report_request_recovers_after_interruption(tmp_path, monkeypatch, lost_marker):
    from api_test_tool import ui_finalization
    c, service, owner, project, nid, saved = idle_round(tmp_path)
    node = c.snapshot(owner)['nodes'][0]
    original = ui_finalization.complete
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report', lambda *args: {'status': 'disabled'})
    def interrupted(*args):
        raise OSError('request ended after durable registration')
    monkeypatch.setattr(ui_finalization, 'complete', interrupted)
    with pytest.raises(OSError):
        service.direct.call(owner, {'action': 'record', 'record_action': 'publish',
            'holder_id': 'worker', 'task_id': node['task_id'], 'node_id': nid,
            'lease_id': node['native_report_pending']['lease_id'], 'arguments': {
                'project_id': project['id'], 'execution_id': saved['execution_id'], 'revision': saved['revision']}})
    assert c.snapshot(owner)['nodes'][0]['finalization_pending']
    if lost_marker:
        # The project file committed but the scheduler marker did not survive.
        with c.transaction() as (_, state):
            state['nodes'][nid].pop('finalization_pending', None)
    monkeypatch.setattr(ui_finalization, 'complete', original)
    service.finalize_pending()
    node = c.snapshot(owner)['nodes'][0]
    assert not node.get('native_report_pending') and not node.get('finalization_pending')
    assert ui_finalization.status(c.store.get_project(owner, project['id']))['phase'] == 'published'
    assert not c.snapshot(owner)['leases']


def test_report_registered_before_browser_exit_keeps_recovery_queue(tmp_path, monkeypatch):
    from api_test_tool import ui_finalization
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report', lambda *args: {'status': 'disabled'})
    def request(c, service, owner, project, saved):
        result = ui_finalization.begin(service, owner, c.store.get_project(owner, project['id']), {
            'execution_id': saved['execution_id'], 'request_id': 'before-exit'}, settled_only=True)
        assert result['pending'] is True
    c, service, owner, project, nid, _ = idle_round(tmp_path, request)
    assert c.snapshot(owner)['nodes'][0]['finalization_pending']
    service.finalize_pending()
    assert ui_finalization.status(c.store.get_project(owner, project['id']))['phase'] == 'published'
    assert not c.snapshot(owner)['nodes'][0].get('native_report_pending')


def test_pure_parent_and_idle_children_leave_queue_without_new_reports(tmp_path):
    c, service, owner, _, tid, _ = prepare(tmp_path)
    parent = c.snapshot(owner)['nodes'][0]
    children = c.split(owner, parent['id'], {'revision': parent['revision'], 'children': [
        {'key': 'a', 'title': 'A', 'scope': 'A'}, {'key': 'b', 'title': 'B', 'scope': 'B'}]})['child_ids']
    for index, nid in enumerate(children):
        identity = {'task_id': tid, 'node_id': nid, 'holder_id': 'worker-' + str(index),
                    'dispatch_id': 'dispatch-' + str(index), 'executor_ref': 'thread:worker-' + str(index)}
        service.direct.call(owner, {'action': 'dispatch', 'task_id': tid, 'holder_id': 'coordinator',
            'request_id': 'dispatch-' + str(index), 'arguments': {'modules': [identity]}})
        claim = service.direct.call(owner, {**identity, 'action': 'claim',
            'arguments': {'browser_environment': browser_environment('context-' + str(index), True)}})
        identity['lease_id'] = claim['lease_id']
        context = service.direct.call(owner, {**identity, 'action': 'context'})
        service.direct.call(owner, {**identity, 'action': 'record', 'record_action': 'cases',
            'arguments': {'cases': [{'case_id': context['case_id_prefix'] + '001',
                'scenario': 'Original unexecuted assertion', 'status': 'not_run'}]}})
        service.direct.call(owner, {**identity, 'action': 'finish', 'reason': 'Own browser closed',
            'arguments': {'browser_stopped': True, 'report_pending': True}})
    before = {p: p.read_bytes() for p in (c.store.root / 'sessions').rglob('*') if p.is_file()}
    service.finalize_pending()
    nodes = {n['id']: n for n in c.snapshot(owner)['nodes']}
    assert not any(n.get('finalization_pending') for n in nodes.values())
    assert all(nodes[nid]['native_report_pending'] for nid in children)
    assert not nodes[parent['id']].get('record_project_id')
    assert all(p.read_bytes() == content for p, content in before.items())
    assert not list((c.store.root / 'sessions').rglob('report.json'))


def test_busy_database_is_not_recorded_as_report_generation_failure(tmp_path, monkeypatch):
    from api_test_tool import database
    c, service, owner, project, nid, _ = idle_round(tmp_path)
    before = c.snapshot(owner)['nodes'][0]
    def busy(*args):
        raise database.OperationalError('database is locked')
    monkeypatch.setattr(service, 'reconcile_idle_settlement', busy)
    with pytest.raises(database.OperationalError, match='database is locked'):
        service.finalize_settlement(owner, nid, raise_storage_errors=True)
    after = c.snapshot(owner)['nodes'][0]
    assert after == before
    assert not c.store.get_project(owner, project['id']).get('ui_finish_request')


def test_busy_settlement_does_not_erase_committed_native_return_receipt(tmp_path, monkeypatch):
    from api_test_tool import database
    c, service, owner, project, tid, saved = prepare(tmp_path)
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': tid, 'holder_id': 'original',
        'arguments': {'browser_environment': browser_environment('original', True)}})
    def busy(*args):
        raise database.OperationalError('database is locked')
    monkeypatch.setattr(service, 'reconcile_idle_settlement', busy)
    result = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original',
        'lease_id': claim['lease_id'], 'reason': 'Own browser actually closed',
        'arguments': {'browser_stopped': True}})
    assert result['released'] is True
    state = c.snapshot(owner)
    assert not state['leases']
    assert not state['nodes'][0].get('report_error')
    assert c.last_error == 'OperationalError'
    assert not c.store.get_project(owner, project['id']).get('ui_finish_request', {}).get('error')
    with pytest.raises(database.OperationalError, match='database is locked'):
        service.finalize_pending()
