"""A task's report and original defect identity survive incremental continuation."""
import base64
from unittest.mock import Mock

from fastapi.testclient import TestClient
from contextlib import ExitStack
import sys
import pytest


@pytest.fixture(autouse=True)
def client_lifespans(monkeypatch, postgres_database):
    factory = TestClient
    with ExitStack() as stack:
        monkeypatch.setattr(sys.modules[__name__], "TestClient",
                            lambda app: stack.enter_context(factory(app)))
        yield

from api_test_tool import ui_records, ui_report_corrections
from api_test_tool.pingcode import PingCode
from api_test_tool.web import create_app


def case(cid, status='failed'):
    return dict(case_id=cid, scenario=cid, module='synthetic', environment='test', client='B端',
                precondition='合成数据', test_data='合成输入', steps='1. 打开合成页面。\n2. 观察结果。',
                expected='符合合成规则', actual='真实合成观察 ' + status, status=status)


def workspace(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    client = TestClient(app)
    client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
    project = client.post('/api/ui-tests', json=dict(title='合成任务', target_url='https://example.test/ui', goal='合成测试')).json()['project']
    store = app.state.store
    owner = store.find_project_owner(project['id'])
    return client, store, owner, project


def publish(store, owner, project, saved):
    return ui_records.publish(store, owner, store.get_project(owner, project['id']), saved['execution_id'], '合成报告', '合成实测结论')['report']


def report(store, owner, pid, rid):
    return store._read(store.project_dir(owner, pid) / 'analyses' / rid / 'report.json')


def test_continuation_updates_one_report_and_preserves_design_evidence_and_draft_ids(tmp_path):
    client, store, owner, project = workspace(tmp_path)
    pid = project['id']
    initial = ui_records.save_cases(store, owner, pid, [case('A'), case('B')])
    stage = publish(store, owner, project, initial)
    service = PingCode(store)
    service.request = Mock(side_effect=AssertionError('No remote PingCode writes'))
    _, _, rejected = service.source(owner, pid, stage['id'], 'finding-1')
    store._write(rejected, dict(status='draft', triage_status='rejected', triage_reason='人工拒绝',
        source=dict(project_id=pid, run_id=stage['id'], draft_id='finding-1'), history=[]))
    saved = ui_records.save_cases(store, owner, pid, [dict(case_id='A', status='passed', actual='复测通过'), case('C')],
                                   initial['execution_id'], initial['revision'])
    assert saved['report']['id'] == stage['id']
    current = report(store, owner, pid, stage['id'])
    assert [(c['case_id'], c['status']) for c in current['imported_results']['cases']] == [('A', 'passed'), ('B', 'failed'), ('C', 'failed')]
    assert current['ui_snapshot']['cases'][0]['steps'] == case('A')['steps']
    assert [f['case_id'] for f in current['findings']] == ['A', 'B', 'C']
    lifecycle = {r['draft_id']: r['triage_status'] for r in service.lifecycle_for_report(owner, pid, stage['id'])}
    assert lifecycle == {'finding-0': 'result_corrected', 'finding-1': 'rejected'}
    assert len(store.get_project(owner, pid)['analysis_reports']) == 1
    archive = store.project_dir(owner, pid) / 'analyses' / stage['id'] / 'revisions' / '1.json'
    assert store._read(archive)['imported_results']['cases'][0]['status'] == 'failed'
    assert client.get(stage['report_url']).status_code == 200
    assert '复测通过' in client.get(stage['report_url']).text
    implicit = ui_records.save_cases(store, owner, pid, [dict(case_id='C', status='passed', actual='增量通过')])
    assert implicit['execution_id'] == initial['execution_id']
    assert implicit['report']['id'] == stage['id']
    assert publish(store, owner, project, implicit)['id'] == stage['id']
    service.request.assert_not_called()


def test_regression_saves_sync_original_unsubmitted_defects_and_human_decisions(tmp_path, monkeypatch):
    client, store, owner, project = workspace(tmp_path)
    pid = project['id']
    saved = ui_records.save_cases(store, owner, pid, [case('A'), case('B'), case('C')])
    original = publish(store, owner, project, saved)
    service = PingCode(store)
    monkeypatch.setattr(PingCode, 'request', Mock(side_effect=AssertionError('No remote writes')))
    for index, triage in [(1, 'rejected'), (2, 'deferred')]:
        _, _, path = service.source(owner, pid, original['id'], f'finding-{index}')
        store._write(path, dict(status='draft', triage_status=triage, triage_reason='人工决定',
            source=dict(project_id=pid, run_id=original['id'], draft_id=f'finding-{index}'), history=[]))
    response = client.post(f'/api/ui-tests/{pid}/regressions', json={})
    assert response.status_code == 200, response.text
    child = store.get_project(owner, response.json()['project']['id'])
    result = ui_records.save_cases(store, owner, child['id'], [case('A', 'passed'), case('B', 'passed'), case('C')])
    states = {r['draft_id']: r['triage_status'] for r in service.lifecycle_for_report(owner, pid, original['id'])}
    assert states == {'finding-0': 'regression_passed', 'finding-1': 'rejected', 'finding-2': 'deferred'}
    stage = publish(store, owner, child, result)
    before = report(store, owner, pid, original['id'])
    incomplete = ui_records.save_cases(store, owner, child['id'], [dict(case_id='A', status='partial', actual='仅完成入口')],
                                        result['execution_id'], result['revision'])
    assert incomplete['report']['id'] == stage['id']
    assert service.lifecycle_for_report(owner, pid, original['id'])[0]['triage_status'] == 'pending_regression'
    failed = ui_records.save_cases(store, owner, child['id'], [dict(case_id='A', status='failed', actual='错误仍存在')],
                                   incomplete['execution_id'], incomplete['revision'])
    assert service.lifecycle_for_report(owner, pid, original['id'])[0]['triage_status'] == 'regression_failed'
    assert report(store, owner, pid, original['id']) == before
    assert len(store.get_project(owner, child['id'])['analysis_reports']) == 1
    assert len(client.get(f'/api/projects/{pid}/reports/total/report.json').json()['stage_reports']) == 2
    assert publish(store, owner, child, failed)['id'] == stage['id']


def test_published_task_accepts_new_screenshots_without_losing_old_assets(tmp_path):
    client, store, owner, project = workspace(tmp_path)
    pid = project['id']
    saved = ui_records.save_cases(store, owner, pid, [case('A')])
    image = lambda text: base64.b64encode(b'\x89PNG\r\n\x1a\n' + text).decode()
    args = dict(case_id='A', step='2. 观察', filename='first.png', content_type='image/png', content_base64=image(b'first'))
    old = ui_records.add_asset(store, owner, pid, saved['execution_id'], **args)
    stage = publish(store, owner, project, saved)
    new = ui_records.add_asset(store, owner, pid, saved['execution_id'], **{**args, 'filename':'second.png', 'content_base64':image(b'second')})
    current = report(store, owner, pid, stage['id'])
    assert [a['id'] for a in current['ui_snapshot']['assets']] == [old['id'], new['id']]
    for asset in [old, new]:
        assert client.get(stage['report_url'].replace('index.html', 'asset-' + asset['id'])).status_code == 200
    assert len(store.get_project(owner, pid)['analysis_reports']) == 1


def test_older_parallel_regression_cannot_replace_newer_original_defect_outcome(tmp_path):
    _, store, owner, project = workspace(tmp_path)
    saved = ui_records.save_cases(store, owner, project['id'], [case('A')])
    stage = publish(store, owner, project, saved)
    service = PingCode(store)
    link = dict(case_id='A', source_project_id=project['id'], source_report_id=stage['id'], source_draft_id='finding-0', outcome='regression_failed')
    service.sync_regression_sources(owner, project['id'], stage['id'], [link], [{**case('A'), 'updated_at':'2026-10-14T09:00:00+00:00'}])
    service.sync_regression_sources(owner, project['id'], stage['id'], [{**link, 'outcome':'regression_passed'}],
                                    [{**case('A', 'passed'), 'updated_at':'2026-10-14T08:00:00+00:00'}])
    assert service.lifecycle_for_report(owner, project['id'], stage['id'])[0]['triage_status'] == 'regression_failed'


def test_new_observations_supersede_stale_corrections_but_keep_other_manual_edits(tmp_path):
    client, store, owner, project = workspace(tmp_path)
    pid = project['id']
    saved = ui_records.save_cases(store, owner, pid, [case('A'), case('B')])
    stage = publish(store, owner, project, saved)
    original = report(store, owner, pid, stage['id'])
    ui_report_corrections.save(store, owner, pid, stage['id'], original, 'A', {'status':'partial', 'evidence':'此前未验证完成'}, 0)
    ui_report_corrections.save(store, owner, pid, stage['id'], original, 'B', {'steps':'1. 人工核实的原步骤。'}, 1)
    changed = ui_records.save_cases(store, owner, pid, [dict(case_id='A', status='passed', actual='已验证全部预期')],
                                     saved['execution_id'], saved['revision'])
    effective = client.get(stage['report_url'].replace('index.html', 'report.json')).json()
    assert effective['imported_results']['cases'][0]['status'] == 'passed'
    assert effective['imported_results']['cases'][0]['evidence'] == '已验证全部预期'
    assert effective['imported_results']['cases'][1]['steps'] == '1. 人工核实的原步骤。'
    assert ui_report_corrections.load(store, owner, pid, stage['id'])['history'][-1]['scope'] == 'continuation'
    again = ui_records.save_cases(store, owner, pid, [dict(case_id='A', status='failed', actual='再次复现错误')],
                                   changed['execution_id'], changed['revision'])
    assert again['report']['id'] == stage['id']
    states = PingCode(store).lifecycle_for_report(owner, pid, stage['id'])
    assert states[0]['triage_status'] == 'regression_failed'
