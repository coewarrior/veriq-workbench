import base64
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api_test_tool.web import create_app
from api_test_tool import ui_records, ui_retests


@pytest.fixture
def workspace(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        project = client.post('/api/ui-tests', json={
            'title': '补测交互验证', 'goal': '验证账号权限与上传',
            'target_url': 'https://example.test/account'}).json()['project']
        store = app.state.store
        owner = next(p.name for p in (tmp_path / 'sessions').iterdir())
        cases = [{'case_id': cid, 'scenario': '验证 ' + cid, 'environment': 'test', 'client': 'B端',
                  'module': '账户', 'precondition': '需要 HR 账号', 'test_data': '需要测试文件',
                  'steps': '1. 登录\n2. 上传', 'expected': '上传成功', 'actual': '缺少登录账号' if status == 'blocked' else '上传成功',
                  'status': status} for cid, status in [('LOGIN-1', 'blocked'), ('UPLOAD-2', 'blocked'), ('PASS-3', 'passed')]]
        record = ui_records.save_cases(store, owner, project['id'], cases)
        report = ui_records.publish(store, owner, store.get_project(owner, project['id']), record['execution_id'], '首次报告', '存在阻塞')['report']
        endpoint = f"/api/projects/{project['id']}/reports/{report['id']}"
        yield client, store, owner, project['id'], report, endpoint, tmp_path


def payload(case_ids=None, revision=0, **updates):
    return {'case_ids': case_ids or ['LOGIN-1'], 'revision': revision,
            'account_mode': 'credentials', 'account': {'role': 'HR', 'username': 'synthetic-user',
                'password': 'synthetic-credential-unique', 'tenant': '测试租户'},
            'business_data': '订单 test-order-1', 'files': [], **updates}


def start(client, endpoint, ids, revision, request_id=None):
    return client.post(endpoint + '/retests', json={
        'case_ids': ids, 'revision': revision, 'request_id': request_id or str(uuid4())})


def test_save_is_private_and_preserves_original_report(workspace):
    client, store, owner, pid, report, endpoint, root = workspace
    original = client.get(report['report_url']).text
    project_before = store.get_project(owner, pid)
    response = client.put(endpoint + '/retest-inputs', json=payload())
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['revision'] == 1 and saved['bindings'].keys() == {'LOGIN-1'}
    assert saved['inputs'][saved['bindings']['LOGIN-1']]['account']['has_password'] is True
    assert 'synthetic-credential-unique' not in response.text
    assert client.get(report['report_url']).text == original
    assert store.get_project(owner, pid) == project_before
    for path in root.rglob('*.json'):
        assert 'synthetic-credential-unique' not in path.read_text()
    with TestClient(client.app) as other:
        other.headers['x-csrf-token'] = other.get('/api/bootstrap').json()['csrf']
        assert other.get(endpoint + '/retest-inputs').status_code in {403, 404}
        assert other.put(endpoint + '/retest-inputs', json=payload()).status_code in {403, 404}
        public = other.get(report['report_url']).text
        assert '"retestBase": ""' in public
        assert 'synthetic-user' not in public and '订单 test-order-1' not in public


def test_batch_binding_and_optimistic_updates(workspace):
    client, store, owner, pid, report, endpoint, root = workspace
    assert client.put(endpoint + '/retest-inputs', json=payload(['PASS-3'])).status_code == 400
    assert client.put(endpoint + '/retest-inputs', json=payload(['LOGIN-1', 'LOGIN-1'])).status_code == 400
    value = client.put(endpoint + '/retest-inputs', json=payload(['LOGIN-1', 'UPLOAD-2'])).json()
    input_id = value['bindings']['LOGIN-1']
    assert value['bindings']['UPLOAD-2'] == input_id
    assert client.put(endpoint + '/retest-inputs', json=payload()).status_code == 400
    update = payload(revision=1, reuse_id=input_id)
    update['account']['password'] = ''
    kept = client.put(endpoint + '/retest-inputs', json=update)
    assert kept.status_code == 200
    assert kept.json()['bindings']['UPLOAD-2'] == input_id
    update['revision'] = 2
    update['account']['username'] = 'another-user'
    assert client.put(endpoint + '/retest-inputs', json=update).status_code == 400
    store.update_project(owner, pid, {'ui_target_url': 'https://other.test/account'})
    assert client.put(endpoint + '/retest-inputs', json={**update, 'account': payload()['account']}).status_code == 400


def test_focused_round_is_idempotent_and_adds_a_separate_report(workspace):
    client, store, owner, pid, old_report, endpoint, root = workspace
    original = client.get(old_report['report_url']).text
    assert start(client, endpoint, ['LOGIN-1'], 0).status_code == 400
    client.put(endpoint + '/retest-inputs', json=payload())
    request_id = str(uuid4())
    first = start(client, endpoint, ['LOGIN-1'], 1, request_id)
    assert first.status_code == 200, first.text
    assert start(client, endpoint, ['LOGIN-1'], 1, request_id).json() == first.json()
    parent = store.get_project(owner, pid)
    pid = first.json()['project_id']
    assert pid != parent['id']
    project = store.get_project(owner, pid)
    assert project['ui_retest_round']['case_ids'] == ['LOGIN-1']
    document = client.get(f'/api/projects/{pid}/artifacts/document').text
    assert 'UPLOAD-2' not in document and 'PASS-3' not in document
    assert 'synthetic-credential-unique' not in document and 'get_ui_retest_inputs' in document
    inputs = ui_retests.execution_inputs(store, owner, project, project['ui_retest_round']['task_id'])
    assert next(iter(inputs['inputs'].values()))['account']['password'] == 'synthetic-credential-unique'
    with pytest.raises(ValueError):
        ui_records.save_cases(store, owner, pid, [{'case_id': 'PASS-3', 'scenario': '未选中的历史用例', 'status': 'passed'}])
    record = ui_records.save_cases(store, owner, pid, [{
        'case_id': 'LOGIN-1', 'scenario': '补测登录', 'steps': '登录后上传',
        'expected': '上传成功', 'actual': '上传成功', 'status': 'passed'}])
    result = ui_records.publish(store, owner, store.get_project(owner, pid), record['execution_id'], '补测报告', '本次通过')
    assert result['report']['id'] != old_report['id']
    assert result['report']['retest_task_id'] == first.json()['task']['task_id']
    assert len(store.get_project(owner, pid)['analysis_reports']) == 1
    assert len(store.get_project(owner, parent['id'])['analysis_reports']) == 1
    new = store._read(store.project_dir(owner, pid) / 'analyses' / result['report']['id'] / 'report.json')
    assert new['imported_results']['counts'] == {'passed': 1, 'total': 1}
    assert client.get(old_report['report_url']).text == original
    state = client.get(endpoint + '/retest-inputs').json()
    assert state['task']['report_url'] == result['report']['report_url']


def test_private_files_are_encrypted_and_bound_to_current_task(workspace):
    client, store, owner, pid, report, endpoint, root = workspace
    file_bytes = b'private synthetic fixture data'
    files = [{'filename': 'fixture.txt', 'content_base64': base64.b64encode(file_bytes).decode()}]
    saved = client.put(endpoint + '/retest-inputs', json=payload(files=files)).json()
    input_id = saved['bindings']['LOGIN-1']
    file_id = saved['inputs'][input_id]['files'][0]['id']
    assert 'content_base64' not in saved['inputs'][input_id]['files'][0]
    with pytest.raises(ValueError):
        ui_retests.file_content(store, owner, store.get_project(owner, pid), input_id, file_id, store.get_project(owner, pid).get('ui_retest_round', {}).get('task_id', ''))
    prepared = start(client, endpoint, ['LOGIN-1'], 1)
    assert prepared.status_code == 200
    pid = prepared.json()['project_id']
    contents = ui_retests.file_content(store, owner, store.get_project(owner, pid), input_id, file_id, store.get_project(owner, pid).get('ui_retest_round', {}).get('task_id', ''))
    assert base64.b64decode(contents['content_base64']) == file_bytes
    assert file_bytes not in (store.project_dir(owner, pid) / 'retest-files' / file_id).read_bytes()
    malformed = payload(revision=1, files=[{'filename': '../bad.txt', 'content_base64': 'YQ=='}])
    assert client.put(endpoint + '/retest-inputs', json=malformed).status_code == 400
    store.update_project(owner, pid, {'ui_target_url': 'https://changed.test/'})
    with pytest.raises(ValueError):
        ui_retests.execution_inputs(store, owner, store.get_project(owner, pid), store.get_project(owner, pid)['ui_retest_round']['task_id'])
    with pytest.raises(ValueError):
        ui_retests.file_content(store, owner, store.get_project(owner, pid), input_id, file_id, store.get_project(owner, pid).get('ui_retest_round', {}).get('task_id', ''))


def test_retest_does_not_replace_an_active_execution(workspace):
    client, store, owner, pid, report, endpoint, root = workspace
    client.put(endpoint + '/retest-inputs', json=payload())
    ui_records.save_cases(store, owner, pid, [{'case_id': 'ACTIVE', 'scenario': '正在测试', 'status': 'not_run'}])
    active = store.get_project(owner, pid)['ui_execution_id']
    prepared = start(client, endpoint, ['LOGIN-1'], 1)
    assert prepared.status_code == 200
    assert prepared.json()['project_id'] != pid
    assert store.get_project(owner, pid)['ui_execution_id'] == active


def prepared_continuation(store, owner, pid, selected):
    from api_test_tool import requirement_design
    from api_test_tool.mcp_progress import record_progress
    project = store.get_project(owner, pid)
    record = ui_records.load(store, owner, pid, project['ui_execution_id'])
    result = requirement_design.resume(store, owner, pid, record['id'], record['revision'],
                                       selected, reason='补齐条件后继续')
    record_progress(store, owner, pid, 'waiting', '任务已准备，等待 Codex 接手')
    return ui_records.load(store, owner, pid, result['execution_id'])


def test_retest_keeps_an_unstarted_continuation_without_losing_history(workspace):
    client, store, owner, pid, report, endpoint, root = workspace
    client.put(endpoint + '/retest-inputs', json=payload())
    original = client.get(report['report_url']).text
    pending = prepared_continuation(store, owner, pid, ['LOGIN-1', 'UPLOAD-2'])
    # Repeated handoff preparation is still not a business execution.
    pending = prepared_continuation(store, owner, pid, ['LOGIN-1', 'UPLOAD-2'])
    pending_path = ui_records.root_for(store, owner, pid, pending['id']) / 'cases.json'
    pending_before = pending_path.read_bytes()
    response = start(client, endpoint, ['LOGIN-1'], 1)
    assert response.status_code == 200, response.text
    task = response.json()['task']
    assert task['project_id'] != pid
    assert 'superseded_execution_id' not in task
    assert task['case_ids'] == ['LOGIN-1']
    project = store.get_project(owner, pid)
    assert project['ui_execution_id'] == pending['id']
    assert project['requirements_resume']
    assert pending_path.read_bytes() == pending_before
    assert client.get(report['report_url']).text != original
    assert len(project['analysis_reports']) == 1
    assert start(client, endpoint, ['LOGIN-1'], 1, task['request_id']).json() == response.json()


@pytest.mark.parametrize('change', ['case_edit', 'checkpoint', 'dependency', 'adapter',
                                  'executing', 'other_report', 'business_correlation', 'other_scope'])
def test_retest_preserves_continuations_with_activity_or_different_context(workspace, change):
    client, store, owner, pid, report, endpoint, root = workspace
    client.put(endpoint + '/retest-inputs', json=payload())
    pending = prepared_continuation(store, owner, pid, ['LOGIN-1', 'UPLOAD-2'])
    execution_root = ui_records.root_for(store, owner, pid, pending['id'])
    if change == 'case_edit':
        ui_records.save_cases(store, owner, pid, [{'case_id': 'LOGIN-1', 'scenario': '已开始验证',
            'status': 'blocked', 'actual': '本轮登录检查失败'}], pending['id'], pending['revision'])
    elif change == 'checkpoint':
        pending['checkpoint_history'] = [{'case_id': 'LOGIN-1'}]
    elif change == 'dependency':
        pending['dependency_check_history'] = [{'status': 'blocked'}]
    elif change == 'adapter':
        store._write(execution_root / 'experiments.json', {'items': {'probe': {'status': 'running'}}})
    elif change == 'executing':
        from api_test_tool.mcp_progress import record_progress
        record_progress(store, owner, pid, 'executing', '正在验证')
    elif change == 'other_report':
        pending['continuation']['source_report_id'] = str(uuid4())
    elif change == 'business_correlation':
        pending['cases'][0]['checkpoints'] = [{'correlation': {'order_id': 'original-order'}}]
    else:
        pending['continuation']['case_ids'] = ['UPLOAD-2']
    if change != 'case_edit':
        store._write(execution_root / 'cases.json', pending)
    current_before = (execution_root / 'cases.json').read_bytes()
    response = start(client, endpoint, ['LOGIN-1'], 1)
    assert response.status_code == 200
    assert response.json()['project_id'] != pid
    assert store.get_project(owner, pid)['ui_execution_id'] == pending['id']
    assert (execution_root / 'cases.json').read_bytes() == current_before


def test_mcp_access_and_report_redaction(workspace):
    client, store, owner, pid, report, endpoint, root = workspace
    client.put(endpoint + '/retest-inputs', json=payload())
    pid = start(client, endpoint, ['LOGIN-1'], 1).json()['project_id']
    code = client.post('/api/mcp/pair').json()['code']
    token = client.post('/api/mcp/redeem', json={'code': code}).json()['token']
    def call(action, arguments):
        return client.post('/api/mcp/call', json={'action': action, 'arguments': {'project_id': pid, **arguments}},
                           headers={'authorization': 'Bearer ' + token})
    private = call('ui_retest_inputs', {'task_id': store.get_project(owner, pid)['ui_retest_round']['task_id']})
    assert call('ui_retest_inputs', {'task_id': str(uuid4())}).status_code == 400
    assert private.status_code == 200 and 'synthetic-credential-unique' in private.text
    response = call('ui_cases', {'cases': [{'case_id': 'LOGIN-1', 'scenario': '登录补测', 'status': 'passed',
        'actual': '使用 synthetic-credential-unique 后通过', 'steps': '登录', 'expected': '成功'}]})
    assert response.status_code == 200, response.text
    assert 'synthetic-credential-unique' not in response.text
    result = call('ui_publish', {'execution_id': response.json()['execution_id'], 'title': '补测',
                                'summary': '使用 synthetic-credential-unique 成功'})
    assert result.status_code == 200, result.text
    assert 'synthetic-credential-unique' not in client.get(result.json()['report']['report_url']).text


def test_client_can_read_private_inputs_without_printing_them(tmp_path, monkeypatch, capsys):
    import importlib.util
    import json
    import stat
    from pathlib import Path
    from api_test_tool import web
    spec = importlib.util.spec_from_file_location('retest_client', web.STATIC / 'api-test-client.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.Client, 'call', lambda *args: {'password': 'synthetic-private-value'})
    output = tmp_path / 'inputs.json'
    monkeypatch.setattr(module.sys, 'argv', ['client', '--url', 'http://127.0.0.1:18797', 'call',
                                          'get_ui_retest_inputs', '--output-file', str(output)])
    module.main()
    assert 'synthetic-private-value' not in capsys.readouterr().out
    assert json.loads(output.read_text())['password'] == 'synthetic-private-value'
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    link = tmp_path / 'linked.json'
    link.symlink_to(output)
    monkeypatch.setattr(module.sys, 'argv', ['client', '--url', 'http://127.0.0.1:18797', 'call',
                                          'get_ui_retest_inputs', '--output-file', str(link)])
    with pytest.raises(SystemExit):
        module.main()
