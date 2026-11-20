"""Published native reports recover stale markers without business/report replay."""
from api_test_tool.orchestration_storage import read_metadata
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from api_test_tool import ui_records
from api_test_tool.deployment_activity import activity
from test_native_finalization import prepare, browser_environment


def published_round(tmp_path, monkeypatch):
    c, service, owner, project, task_id, saved = prepare(tmp_path)
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report', lambda *args: {'status': 'disabled'})
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': task_id,
        'holder_id': 'original-holder',
        'arguments': {'browser_environment': browser_environment('isolated-context', True)}})
    lease = copy.deepcopy(c.snapshot(owner)['leases'][0])
    result = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original-holder',
        'lease_id': claim['lease_id'], 'reason': 'Own browser actually closed',
        'arguments': {'browser_stopped': True, 'publish_saved': True}})
    with c.transaction() as (_, state):
        node = state['nodes'][result['node_id']]
        node['finalization_pending'] = True
        node['native_report_pending'] = {'lease_id': claim['lease_id'], 'since': c.clock()}
    project = c.store.get_project(owner, project['id'])
    directory = c.store.project_dir(owner, project['id'])
    record_file = directory / 'ui-executions' / saved['execution_id'] / 'cases.json'
    report_file = directory / 'analyses' / project['ui_finish_request']['result']['report']['id'] / 'report.json'
    def no_publish(*args, **kwargs):
        raise AssertionError('Published evidence must not be rebuilt')
    monkeypatch.setattr(ui_records, 'publish', no_publish)
    return c, service, owner, project, result['node_id'], lease, record_file, report_file


def test_readonly_release_probe_and_scheduler_recover_exact_published_round(tmp_path, monkeypatch):
    c, service, owner, project, nid, _, record_file, report_file = published_round(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in (record_file, report_file,
        c.store.project_dir(owner, project['id']) / 'metadata.json')}
    assert activity(c.store.root) == {'rounds': 0, 'channels': 0, 'finalizations': 0, 'acknowledgements': 0}
    probe = Path(__file__).parents[2] / 'api_test_tool' / 'deployment_activity.py'
    standalone = subprocess.run([sys.executable, '-'], input=probe.read_text(), text=True,
        capture_output=True, check=True, cwd=tmp_path,
        env={**os.environ, 'API_TEST_DATA_DIR': str(c.store.root)})
    assert json.loads(standalone.stdout) == {'rounds': 0, 'channels': 0, 'finalizations': 0, 'acknowledgements': 0}
    assert all(path.read_bytes() == value for path, value in before.items())
    assert c.snapshot(owner)['nodes'][0]['native_report_pending']
    service.finalize_pending()
    node = next(n for n in c.snapshot(owner)['nodes'] if n['id'] == nid)
    assert not node.get('native_report_pending') and not node.get('finalization_pending')
    assert all(path.read_bytes() == value for path, value in before.items())


def test_stale_marker_storage_failure_preserves_original_publication(tmp_path, monkeypatch):
    c, service, owner, project, nid, _, _, _ = published_round(tmp_path, monkeypatch)
    metadata = c.store.project_dir(owner, project['id']) / 'metadata.json'
    before = metadata.read_bytes()
    def unavailable(*args):
        raise OSError('settlement storage unavailable')
    monkeypatch.setattr(service, 'complete_published_settlement', unavailable)
    service.finalize_settlement(owner, nid)
    assert metadata.read_bytes() == before
    node = next(n for n in c.snapshot(owner)['nodes'] if n['id'] == nid)
    assert node['native_report_pending'] and node['finalization_pending']
    assert not node.get('report_error')


@pytest.mark.parametrize('change', [
    'missing_report', 'result_revision', 'record_revision', 'report_revision',
    'missing_final_marker', 'browser_exit_unknown', 'active_lease', 'unknown_channel',
    'unfinished_node',
])
def test_real_unfinished_evidence_still_blocks_release_and_marker_cleanup(tmp_path, monkeypatch, change):
    c, service, owner, project, nid, lease, record_file, report_file = published_round(tmp_path, monkeypatch)
    if change == 'missing_report':
        report_file.unlink()
    elif change == 'result_revision':
        c.store.update_project(owner, project['id'], {'ui_execution_revision': project['ui_execution_revision'] + 1})
    elif change in {'record_revision', 'report_revision'}:
        path = record_file if change == 'record_revision' else report_file
        value = c.store._read(path)
        target = value if change == 'record_revision' else value['ui_snapshot']
        target['revision'] += 1
        c.store._write(path, value)
    elif change == 'missing_final_marker':
        c.store.update_project(owner, project['id'], {'ui_final_report': {}})
    else:
        with c.transaction() as (_, state):
            if change == 'browser_exit_unknown':
                state['nodes'][nid]['native_browser_stopped'] = False
            elif change == 'unfinished_node':
                state['nodes'][nid]['state'] = 'running'
            else:
                if change == 'unknown_channel':
                    lease.update(resource_hold=True, executor_stopped=True, browser_stopped=True,
                        auxiliary_channels={'browser': {'state': 'unknown'}})
                state['leases'][lease['id']] = lease
    assert activity(c.store.root)['finalizations'] == 1
    service.finalize_settlement(owner, nid)
    node = next(n for n in c.snapshot(owner)['nodes'] if n['id'] == nid)
    assert node['native_report_pending'] and node['finalization_pending']


def test_exited_resource_hold_keeps_unknown_evidence_without_blocking_published_cleanup(tmp_path, monkeypatch):
    c, service, owner, project, nid, lease, record_file, report_file = published_round(tmp_path, monkeypatch)
    lease.update(resource_hold=True, executor_stopped=True, browser_stopped=True,
        hold={'pending_operation_ids': ['unresolved-submission']},
        auxiliary_channels={'browser': {'state': 'exited'}})
    with c.transaction() as (_, state):
        state['leases'][lease['id']] = lease
        state['operations']['unresolved-submission'] = {'id': 'unresolved-submission',
            'owner': owner, 'node_id': nid, 'lease_id': lease['id'], 'state': 'unknown', 'historical': True}
    before = {path: path.read_bytes() for path in (record_file, report_file)}
    assert activity(c.store.root) == {'rounds': 0, 'channels': 0, 'finalizations': 0, 'acknowledgements': 0}
    service.finalize_settlement(owner, nid)
    snapshot = c.snapshot(owner, include_history=True)
    node = next(n for n in snapshot['nodes'] if n['id'] == nid)
    assert not node.get('native_report_pending') and not node.get('finalization_pending')
    assert snapshot['leases'][0]['hold']['pending_operation_ids'] == ['unresolved-submission']
    with c.connect() as db:
        retained = json.loads(db.execute("SELECT meta FROM state_history WHERE kind='operations' AND key=%s",
            ('unresolved-submission',)).fetchone()[0])
    assert retained['state'] == 'unknown' and retained['historical'] is True
    assert all(path.read_bytes() == value for path, value in before.items())


def published_split(tmp_path, monkeypatch):
    c, service, owner, project, task_id, _ = prepare(tmp_path)
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report', lambda *args: {'status': 'disabled'})
    parent = c.snapshot(owner)['nodes'][0]
    children = c.split(owner, parent['id'], {'revision': parent['revision'], 'children': [
        {'key': 'first', 'title': 'First module', 'scope': 'First scope'},
        {'key': 'second', 'title': 'Second module', 'scope': 'Second scope'},
    ]})['child_ids']
    reports = []
    for index, nid in enumerate(children):
        identity = {'task_id': task_id, 'node_id': nid, 'holder_id': 'child-' + str(index)}
        claim = service.direct.call(owner, {**identity, 'action': 'claim',
            'arguments': {'browser_environment': browser_environment('child-context-' + str(index), True)}})
        identity['lease_id'] = claim['lease_id']
        context = service.direct.call(owner, {**identity, 'action': 'context'})
        service.direct.call(owner, {**identity, 'action': 'record', 'record_action': 'cases',
            'arguments': {'cases': [{'case_id': context['case_id_prefix'] + '001', 'scenario': 'Unexecuted original design', 'status': 'not_run'}]}})
        service.direct.call(owner, {**identity, 'action': 'finish', 'reason': 'Own child browser closed',
            'arguments': {'browser_stopped': True, 'publish_saved': True}})
    with c.transaction() as (_, state):
        state['nodes'][children[-1]]['native_report_pending'] = {'lease_id': identity['lease_id']}
        state['nodes'][children[-1]]['finalization_pending'] = True
        for nid in children:
            node = state['nodes'][nid]
            p = c.store.get_project(owner, node['record_project_id'])
            reports.append(c.store.project_dir(owner, p['id']) / 'analyses' /
                p['ui_finish_request']['result']['report']['id'] / 'report.json')
    def no_publish(*args, **kwargs):
        raise AssertionError('A pure container must not create its own report')
    monkeypatch.setattr(ui_records, 'publish', no_publish)
    return c, service, owner, parent['id'], children, reports


def test_pure_split_container_uses_all_original_child_reports_without_creating_one(tmp_path, monkeypatch):
    c, service, owner, parent, children, reports = published_split(tmp_path, monkeypatch)
    before = {path: path.read_bytes() for path in reports}
    projects = {p['id'] for p in c.store.list_projects(owner)}
    assert activity(c.store.root)['finalizations'] == 0
    service.finalize_settlement(owner, parent)
    nodes = {n['id']: n for n in c.snapshot(owner)['nodes']}
    assert not nodes[parent].get('finalization_pending')
    assert not nodes[parent].get('record_project_id') and not nodes[parent].get('record_execution_id')
    assert nodes[children[-1]]['native_report_pending'] and nodes[children[-1]]['finalization_pending']
    assert {p['id'] for p in c.store.list_projects(owner)} == projects
    assert all(path.read_bytes() == value for path, value in before.items())


@pytest.mark.parametrize('history', ['attempts', 'case_history'])
def test_executed_parent_without_record_keeps_original_report_generation_path(tmp_path, monkeypatch, history):
    original_publish = ui_records.publish
    c, service, owner, parent, children, _ = published_split(tmp_path, monkeypatch)
    monkeypatch.setattr(ui_records, 'publish', original_publish)
    with c.transaction() as (_, state):
        state['nodes'][parent][history] = (copy.deepcopy(state['nodes'][children[0]]['attempts'])
            if history == 'attempts' else {'original-observation': {}})
        for nid in children:
            state['nodes'][nid].pop('native_report_pending', None)
            state['nodes'][nid].pop('finalization_pending', None)
    service.finalize_settlement(owner, parent)
    node = next(n for n in c.snapshot(owner)['nodes'] if n['id'] == parent)
    assert not node.get('finalization_pending')
    assert node['record_project_id'] and node['record_execution_id']
    record = ui_records.load(c.store, owner, node['record_project_id'], node['record_execution_id'])
    assert (c.store.project_dir(owner, node['record_project_id']) / 'analyses' / record['report_id'] / 'report.json').is_file()


@pytest.mark.parametrize('change', ['missing_child', 'omitted_child', 'foreign_task', 'cycle', 'active_child', 'unknown_exit', 'missing_child_report', 'parent_observation'])
def test_split_container_keeps_pending_when_any_original_child_proof_is_incomplete(tmp_path, monkeypatch, change):
    c, service, owner, parent, children, reports = published_split(tmp_path, monkeypatch)
    if change == 'missing_child_report':
        reports[0].unlink()
    else:
        with c.transaction() as (_, state):
            child = state['nodes'][children[0]]
            if change == 'missing_child':
                del state['nodes'][children[0]]
            elif change == 'omitted_child':
                state['nodes'][parent]['child_ids'].remove(children[0])
            elif change == 'foreign_task':
                state['tasks']['another-task'] = {**copy.deepcopy(state['tasks'][child['task_id']]),
                    'id': 'another-task', 'node_ids': [child['id']]}
                child['task_id'] = 'another-task'
            elif change == 'cycle':
                child.update(child_ids=[parent], attempts=[], case_history={}, outcome_history=[])
                child.pop('record_project_id', None)
                child.pop('record_execution_id', None)
                state['nodes'][parent]['parent_id'] = child['id']
            elif change == 'active_child':
                child['state'] = 'running'
            elif change == 'unknown_exit':
                child['native_browser_stopped'] = False
            else:
                state['nodes'][parent]['case_history'] = {'unpublished-observation': {}}
    assert activity(c.store.root)['finalizations'] >= 1
    service.finalize_settlement(owner, parent)
    with c.connect() as db:
        state = read_metadata(db)
    assert state['nodes'][parent]['finalization_pending']
