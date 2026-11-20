"""Shared report edits must preserve source evidence and private workspace boundaries."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api_test_tool import ui_records
from api_test_tool.web import create_app


def register(client, username):
    csrf = client.get('/api/auth/me').json()['csrf']
    response = client.post('/api/auth/register', json={
        'username': username, 'password': 'synthetic-password'}, headers={'x-csrf-token': csrf})
    assert response.status_code == 200
    client.headers['x-csrf-token'] = client.get('/api/auth/me').json()['csrf']


@pytest.fixture
def reports(tmp_path):
    app = create_app(tmp_path, testing=True, start_fixture=False, auth_enabled=True)
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as anonymous:
        register(alice, 'alice')
        register(bob, 'bob')
        project = alice.post('/api/ui-tests', json={
            'title': '共同编辑报告', 'target_url': 'https://example.test/account', 'goal': '验证共同修改'}).json()['project']
        store = app.state.store
        owner = app.state.accounts.authenticate(alice.cookies['api_test_auth'])['owner']
        record = ui_records.save_cases(store, owner, project['id'], [
            {'case_id': cid, 'scenario': '验证 ' + cid, 'environment': 'test', 'client': 'B端',
             'module': '账户', 'precondition': '需要测试账号', 'test_data': '测试资料',
             'steps': '登录并读取资料', 'expected': '资料正常显示', 'actual': '缺少账号' if status == 'blocked' else '资料错误',
             'status': status} for cid, status in [('BLOCK-1', 'blocked'), ('FAIL-2', 'failed')]])
        report = ui_records.publish(store, owner, store.get_project(owner, project['id']),
            record['execution_id'], '首轮报告', '仍有阻塞和缺陷')['report']
        base = f"/api/projects/{project['id']}/reports/{report['id']}"
        yield app, alice, bob, anonymous, owner, project, report, base


def test_cross_account_edits_are_shared_audited_and_do_not_transfer_workspace(reports):
    app, alice, bob, anonymous, owner, project, report, base = reports
    path = app.state.store.project_dir(owner, project['id']) / 'analyses' / report['id'] / 'report.json'
    frozen = path.read_bytes()
    page = bob.get(base + '/index.html')
    assert page.status_code == 200 and 'content="read-only"' not in page.text
    assert 'report-collaboration.js?v=' in page.text
    fields = {'status': 'passed', 'evidence': '人工确认资料正常'}
    saved = bob.post(base + '/case-corrections/BLOCK-1', json={'revision': 0, 'fields': fields})
    assert saved.status_code == 200
    shared = alice.get(base + '/report.json').json()
    assert shared['imported_results']['cases'][0]['status'] == 'passed'
    assert path.read_bytes() == frozen
    assert alice.post(base + '/case-corrections/BLOCK-1', json={'revision': 0, 'fields': fields}).status_code == 400
    history = alice.get(base + '/collaboration').json()['history']
    assert history[-1]['actor'] == 'bob'
    assert anonymous.get(base + '/report.json').status_code == 401
    assert anonymous.post(base + '/case-corrections/BLOCK-1', json={'revision': 1, 'fields': fields}).status_code == 401
    assert bob.get('/api/bootstrap').json()['projects'] == []
    assert bob.get('/api/projects/' + project['id']).status_code == 404
    assert bob.delete('/api/projects/' + project['id']).status_code == 404


def test_shared_defect_status_rejects_stale_write_and_keeps_result_separate(reports):
    app, alice, bob, _, owner, project, report, base = reports
    draft = base + '/pingcode/finding-0'
    assert bob.get(draft).status_code == 200
    decision = {'status': 'deferred', 'reason': '等待产品确认', 'expected_updated_at': ''}
    saved = bob.patch(draft + '/lifecycle', json=decision)
    assert saved.status_code == 200
    assert alice.get(base + '/pingcode').json()['values'][0]['triage_status'] == 'deferred'
    assert alice.patch(draft + '/lifecycle', json=decision).status_code == 409
    assert alice.get(base + '/report.json').json()['imported_results']['cases'][1]['status'] == 'failed'
    assert not bob.get('/api/integrations/pingcode').json()['configured']


def test_batch_titles_persist_for_regression_failure_and_preserve_shared_evidence(reports):
    app, alice, bob, anonymous, owner, project, report, base = reports
    store = app.state.store
    path = store.project_dir(owner, project['id']) / 'analyses' / report['id'] / 'report.json'
    frozen = path.read_bytes()
    draft = base + '/pingcode/finding-0'
    original = bob.get(draft).json()
    assert bob.patch(draft + '/lifecycle', json={'status': 'regression_failed',
        'expected_updated_at': '', 'reason': '合成复测失败'}).status_code == 200
    payload = {'revision': 0, 'draft_ids': ['finding-0'], 'attributes': {'environment': 'prod'}}
    saved = bob.post(base + '/title-corrections', json=payload)
    assert saved.status_code == 200, saved.text
    title = '【prod】【B端】【账户】 验证 FAIL-2'
    assert saved.json()['values'][0]['title'] == title
    refreshed = alice.get(draft).json()
    assert refreshed['title'] == title
    assert refreshed['title_corrected'] is True and refreshed['correction_revision'] == 1
    assert refreshed['record']['triage_status'] == 'regression_failed'
    assert refreshed['description'].split('\n', 1)[1] == original['description'].split('\n', 1)[1]
    assert path.read_bytes() == frozen
    assert title in alice.get(base + '/index.html').text
    total = alice.get(f"/api/projects/{project['id']}/reports/total/report.json").json()
    assert total['findings'][0]['title'] == title
    assert alice.post(base + '/title-corrections', json=payload).status_code == 400
    assert anonymous.post(base + '/title-corrections', json={**payload, 'revision': 1}).status_code == 401
    invalid = {**payload, 'revision': 1, 'draft_ids': ['finding-0', 'finding-999']}
    assert bob.post(base + '/title-corrections', json=invalid).status_code == 400
    assert alice.get(draft).json()['correction_revision'] == 1
    assert bob.get('/api/bootstrap').json()['projects'] == []


def test_total_correction_targets_origin_and_preserves_defect_decision(reports):
    app, alice, bob, _, owner, project, report, base = reports
    total = f"/api/projects/{project['id']}/reports/total"
    case = bob.get(total + '/report.json').json()['imported_results']['cases'][0]
    payload = {'revision': case['source_report']['correction_revision'],
               'source_report': case['source_report'], 'fields': {'status': 'passed'}}
    assert bob.post(total + '/case-corrections/BLOCK-1', json=payload).status_code == 200
    assert alice.get(base + '/report.json').json()['imported_results']['counts']['passed'] == 1
    assert alice.get(total + '/report.json').json()['imported_results']['counts']['passed'] == 1
    payload['source_report'] = {**case['source_report'], 'id': str(uuid4())}
    assert bob.post(total + '/case-corrections/BLOCK-1', json=payload).status_code == 409


def test_report_handoff_is_scoped_and_does_not_replace_creator_pair(reports):
    app, alice, bob, _, owner, project, report, base = reports
    private = app.state.store.create_project(owner, '私人资料', 'private.md', '# private')
    original_pair = alice.post('/api/mcp/pair').json()
    scoped_pair = bob.post(base + '/collaboration/pair').json()
    token = bob.post('/api/mcp/redeem', json={'code': scoped_pair['code']}).json()['token']
    assert alice.post('/api/mcp/redeem', json={'code': original_pair['code']}).status_code == 200
    headers = {'authorization': 'Bearer ' + token}
    listed = bob.post('/api/mcp/call', json={'action': 'workspace'}, headers=headers).json()
    assert {p['id'] for p in listed['projects']} == {project['id']}
    denied = bob.post('/api/mcp/call', json={'action': 'context', 'arguments': {'project_id': private['id']}}, headers=headers)
    assert denied.status_code == 403
    assert bob.post('/api/mcp/call', json={'action': 'start_workflow', 'arguments': {}}, headers=headers).status_code == 403


def test_shared_retest_inputs_are_masked_and_use_one_revision(reports):
    app, alice, bob, _, owner, project, report, base = reports
    payload = {'case_ids': ['BLOCK-1'], 'revision': 0, 'account_mode': 'credentials',
        'account': {'role': 'HR', 'username': 'test-user', 'password': 'synthetic-secret', 'tenant': '测试租户'},
        'business_data': '测试订单', 'files': []}
    saved = bob.put(base + '/retest-inputs', json=payload)
    assert saved.status_code == 200 and 'synthetic-secret' not in saved.text
    assert alice.get(base + '/retest-inputs').json()['revision'] == 1
    assert alice.put(base + '/retest-inputs', json=payload).status_code == 400
