"""Isolated checks for the authorized evidence-withdrawal delivery boundary."""
import base64
import json
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from api_test_tool import ui_records
from api_test_tool.web import create_app


@pytest.fixture
def evidence(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        account = client.post('/api/account-projects', json={
            'name': 'synthetic', 'login_url': 'https://example.test'}).json()
        project = client.post('/api/ui-tests', json={'title': 'synthetic',
            'target_url': 'https://example.test', 'goal': 'synthetic',
            'account_project_id': account['id']}).json()['project']
        store = app.state.store
        owner = store.find_project_owner(project['id'])
        saved = ui_records.save_cases(store, owner, project['id'], [{
            'case_id': 'A', 'scenario': 'synthetic', 'steps': '打开页面并观察结果',
            'expected': '合成结果', 'actual': '合成结果已观察', 'status': 'partial',
            'test_data': 'private-input.txt'}])
        eid = saved['execution_id']
        asset = ui_records.add_asset(store, owner, project['id'], eid, 'A', '合成证据',
            'private-input.txt', 'text/plain', base64.b64encode(b'synthetic private bytes').decode(), kind='fixture')
        stage = ui_records.publish(store, owner, project, eid, 'synthetic', 'synthetic')['report']
        token = client.post('/api/mcp/redeem', json={'code': client.post('/api/mcp/pair').json()['code']}).json()['token']
        def call(action, **args):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                json={'action': action, 'arguments': {'project_id': project['id'], **args}})
        yield client, store, owner, project, eid, asset, stage, call


def args(evidence):
    _, _, _, project, eid, asset, _, _ = evidence
    return dict(project_id=project['id'], execution_id=eid, asset_id=asset['id'],
                case_id='A', sha256=asset['sha256'], reason='背景含不应交付的信息', request_id='withdraw-A')


def test_withdrawal_hides_all_delivery_paths_but_preserves_original_and_results(evidence):
    client, store, owner, project, eid, asset, stage, call = evidence
    root = ui_records.root_for(store, owner, project['id'], eid)
    original = (root / 'cases.json').read_bytes()
    report_path = store.project_dir(owner, project['id']) / 'analyses' / stage['id'] / 'report.json'
    original_report = report_path.read_bytes()
    base = f"/api/projects/{project['id']}/reports/{stage['id']}"
    assert client.get(base + '/asset-' + asset['id']).status_code == 200
    response = call('ui_asset_withdraw', **args(evidence))
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt['withdrawn'] and receipt['original_preserved']
    assert receipt['withdrawal']['actor'] and receipt['withdrawal']['withdrawn_at']
    assert call('ui_asset_withdraw', **args(evidence)).json() == receipt
    assert (root / asset['id']).read_bytes() == b'synthetic private bytes'
    assert (root / 'cases.json').read_bytes() == original
    assert report_path.read_bytes() == original_report
    assert client.get(base + '/asset-' + asset['id']).status_code == 410
    assert client.get(f"/api/ui-tests/{project['id']}/executions/{eid}/asset-{asset['id']}").status_code == 410
    for report_base in (base, f"/api/projects/{project['id']}/reports/total"):
        public = client.get(report_base + '/report.json').json()
        assert public['ui_snapshot']['assets'] == []
        assert public['imported_results']['cases'][0]['status'] == 'partial'
        for name in ('index.html', 'cases.html'):
            html = client.get(report_base + '/' + name)
            assert html.status_code == 200
            assert ('asset-' + asset['id']) not in html.text
        zipped = client.get(report_base + '/test-data.zip')
        assert zipped.status_code == 200
        assert all('private-input.txt' not in name for name in ZipFile(BytesIO(zipped.content)).namelist())
    readback = call('ui_read', execution_id=eid).json()
    assert readback['assets'] == []
    assert readback['cases'][0]['status'] == 'partial'
    inventory = client.get(f"/api/ui-tests/{project['id']}/executions/{eid}/inventory").json()
    assert inventory['assets'] == []
    assert inventory['cases'][0]['status'] == 'partial'
    ledger = store._read(store._owner_dir(owner) / 'ui-asset-withdrawals.json')
    assert len(ledger['assets']) == len(ledger['requests']) == 1
    assert ledger['assets'][asset['id']]['asset']['sha256'] == asset['sha256']


def test_withdrawal_rejects_wrong_identity_and_request_reuse(evidence):
    _, store, owner, project, eid, asset, _, call = evidence
    valid = args(evidence)
    for changes in ({'sha256': '0' * 64}, {'case_id': 'other'}, {'execution_id': '00000000-0000-0000-0000-000000000000'}):
        assert call('ui_asset_withdraw', **(valid | changes)).status_code in (400, 403, 404, 409)
    assert call('ui_asset_withdraw', **valid).status_code == 200
    assert call('ui_asset_withdraw', **(valid | {'reason': 'different'})).status_code == 409
    from api_test_tool.ui_asset_withdrawals import withdraw
    other, _ = store.session(None)
    with pytest.raises((FileNotFoundError, ValueError, PermissionError)):
        withdraw(store, other['id'], project['id'], eid, asset['id'], 'A', asset['sha256'], 'reason', 'other', actor=other['id'])
