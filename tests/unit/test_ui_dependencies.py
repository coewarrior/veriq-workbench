import base64
from functools import partial
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api_test_tool import ui_records, ui_retests
from api_test_tool.web import create_app


def dependency(**updates):
    return {'key': 'hr-login', 'title': '缺少 HR 管理员账号', 'kind': 'account',
            'environment': 'test', 'tenant': '演示企业', 'role': 'HR 管理员', **updates}


def case(cid, deps=None, **updates):
    return {'case_id': cid, 'scenario': '验证 ' + cid, 'environment': 'test', 'client': 'B端',
            'module': '用户中心', 'precondition': '对应前置条件满足', 'test_data': '演示测试数据',
            'steps': '完成本用例操作并核对结果', 'expected': '业务规则符合预期', 'status': 'not_run',
            'dependencies': [dependency()] if deps is None else deps, **updates}


@pytest.fixture
def workspace(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        account_project = client.post('/api/account-projects', json={
            'name': '共同阻塞合成项目', 'login_url': 'https://demo.example.test/account'}).json()
        pid = client.post('/api/ui-tests', json={'account_project_id': account_project['id'], 'title': '共同阻塞检查', 'goal': '检查共享前置条件',
            'target_url': 'https://demo.example.test/account'}).json()['project']['id']
        store = app.state.store
        owner = store.find_project_owner(pid)
        token = client.post('/api/mcp/redeem', json={'code': client.post('/api/mcp/pair').json()['code']}).json()['token']
        def call(action, **arguments):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                               json={'action': action, 'arguments': {'project_id': pid, **arguments}})
        yield client, store, owner, pid, call


def check(call, saved, gid, status='blocked', **updates):
    return call('ui_dependency_check', execution_id=saved['execution_id'], revision=saved['revision'],
                dependency_id=gid, status=status, observed='没有可用的 HR 管理员凭据' if status == 'blocked' else '对应角色登录成功，租户与权限已核对',
                method='只读核对本轮角色凭据和登录态', **updates)


def publish_blocked(call, cases):
    saved = call('ui_cases', cases=cases).json()
    for group in saved['dependency_groups']:
        saved = check(call, saved, group['id']).json()
    report = call('ui_publish', execution_id=saved['execution_id'], title='共同阻塞报告', summary='前置检查阻塞').json()['report']
    return report


def credentials(revision=0, **updates):
    return {'revision': revision, 'case_ids': ['AUTH'], 'account_mode': 'credentials',
            'account': {'role': 'HR 管理员', 'tenant': '演示企业', 'username': 'demo.hr',
                        'password': 'synthetic-shared-secret'}, 'business_data': '', 'files': [], **updates}


def test_shared_check_skips_only_dependencies_and_new_cases_use_same_result(workspace):
    client, store, owner, pid, call = workspace
    saved = call('ui_cases', cases=[case('AUTH'), case('UPLOAD'), case('INDEPENDENT', []),
        case('STAFF', [dependency(role='普通员工')]), case('OTHER-TENANT', [dependency(tenant='另一企业')]),
        case('PRE', [dependency(environment='pre')]),
        case('DONE', status='passed', actual='先前已真实完成业务断言')]).json()
    assert len(saved['dependency_groups']) == 4
    gid = next(g['id'] for g in saved['dependency_groups'] if 'AUTH' in g['case_ids'])
    blocked = check(call, saved, gid)
    assert blocked.status_code == 200, blocked.text
    saved = blocked.json()
    plan = saved['execution_plan']
    assert {c['case_id'] for c in plan['skipped_cases']} == {'AUTH', 'UPLOAD'}
    assert all(c['business_steps_executed'] is False for c in plan['skipped_cases'])
    assert plan['runnable_case_ids'] == ['INDEPENDENT'] and plan['completed_case_ids'] == ['DONE']
    assert len(plan['dependencies_to_check']) == 3
    late = call('ui_cases', execution_id=saved['execution_id'], revision=saved['revision'], cases=[case('LATE')])
    assert late.status_code == 200, late.text
    saved = late.json()
    assert {c['case_id'] for c in saved['execution_plan']['skipped_cases']} == {'AUTH', 'UPLOAD', 'LATE'}
    read = call('ui_read', limit=1).json()
    assert read['total'] == 8 and len(read['execution_plan']['skipped_cases']) == 3  # paging never truncates the skip plan
    assert read['cases'][0]['executed_at'] == '' and read['cases'][0]['not_run_reason'] == ''
    assert read['cases'][0]['status'] == 'not_run'
    observed = call('ui_cases', execution_id=saved['execution_id'], revision=saved['revision'],
                    cases=[case('AUTH', status='passed', actual='执行者独立观察，前置检查未更新')])
    assert observed.status_code == 200, observed.text
    saved = observed.json()
    ready = check(call, saved, gid, 'ready')
    assert ready.status_code == 200, ready.text
    assert set(ready.json()['execution_plan']['runnable_case_ids']) == {'UPLOAD', 'LATE', 'INDEPENDENT'}
    assert ready.json()['execution_plan']['skipped_cases'] == []
    record = ui_records.load(store, owner, pid, saved['execution_id'])
    assert next(c for c in record['cases'] if c['case_id'] == 'DONE')['status'] == 'passed'
    assert next(c for c in record['cases'] if c['case_id'] == 'AUTH')['status'] == 'passed'
    assert next(c for c in record['cases'] if c['case_id'] == 'AUTH')['actual'] == '执行者独立观察，前置检查未更新'
    assert len(record['dependency_check_history']) == 2


def test_multiple_blockers_release_independently_and_frozen_round_cannot_change(workspace):
    client, store, owner, pid, call = workspace
    file_dep = dependency(key='employee-fixture', kind='file', title='缺少员工资料文件', role='', tenant='')
    saved = call('ui_cases', cases=[case('UPLOAD', [dependency(), file_dep])]).json()
    gids = [g['id'] for g in saved['dependency_groups']]
    stale = dict(saved)
    for gid in gids:
        saved = check(call, saved, gid).json()
    assert check(call, stale, gids[0]).status_code == 400
    saved = check(call, saved, gids[0], 'ready').json()
    assert saved['execution_plan']['skipped_cases'][0]['dependency_ids'] == [gids[1]]
    report = call('ui_publish', execution_id=saved['execution_id'], title='依赖报告', summary='文件仍阻塞').json()['report']
    assert check(call, saved, gids[1], 'ready').status_code == 200
    new = call('ui_cases', cases=[case('UPLOAD', [dependency(), file_dep])]).json()
    assert new['execution_id'] == saved['execution_id']
    assert new['execution_plan']['skipped_cases'] == [] and len(new['execution_plan']['dependencies_to_check']) == 0
    assert check(call, saved, gids[1]).status_code == 400


def test_group_save_once_and_edit_syncs_all_with_explicit_single_override(workspace):
    client, store, owner, pid, call = workspace
    report = publish_blocked(call, [case('AUTH'), case('UPLOAD'), case('STAFF', [dependency(role='普通员工')])])
    endpoint = f"/api/projects/{pid}/reports/{report['id']}"
    original = client.get(report['report_url']).text
    view = client.get(endpoint + '/retest-inputs').json()
    group = next(g for g in view['groups'] if 'AUTH' in g['case_ids'])
    response = client.put(endpoint + '/retest-inputs', json=credentials(group_id=group['id']))
    assert response.status_code == 200, response.text
    view = response.json()
    input_id = view['group_bindings'][group['id']]
    assert view['bindings'] == {'AUTH': input_id, 'UPLOAD': input_id}
    assert 'STAFF' not in view['bindings'] and 'synthetic-shared-secret' not in response.text
    edit = credentials(1, group_id=group['id'], reuse_id=input_id, business_data='新增订单')
    edit['account']['password'] = ''
    view = client.put(endpoint + '/retest-inputs', json=edit).json()
    updated_id = view['group_bindings'][group['id']]
    assert updated_id != input_id and view['case_input_ids']['UPLOAD'] == [updated_id]
    individual = client.put(endpoint + '/retest-inputs', json=credentials(2, reuse_id=updated_id, business_data='仅 AUTH'))
    assert individual.status_code == 200, individual.text
    view = individual.json()
    assert view['case_overrides'] == ['AUTH'] and view['case_input_ids']['UPLOAD'] == [updated_id]
    assert view['case_input_ids']['AUTH'] != [updated_id]
    wrong = credentials(3, group_id=group['id'])
    wrong['account']['role'] = '普通员工'
    assert client.put(endpoint + '/retest-inputs', json=wrong).status_code == 400
    assert client.get(report['report_url']).text == original  # data does not change original verdicts
    with TestClient(client.app) as other:
        assert other.get(endpoint + '/retest-inputs').status_code in {403, 404}


def test_account_and_file_inputs_are_kept_separate_and_retest_checks_afresh(workspace):
    client, store, owner, pid, call = workspace
    file_dep = dependency(key='employee-fixture', kind='file', title='缺少员工资料文件', role='', tenant='')
    report = publish_blocked(call, [case('AUTH'), case('UPLOAD', [dependency(), file_dep])])
    endpoint = f"/api/projects/{pid}/reports/{report['id']}"
    view = client.get(endpoint + '/retest-inputs').json()
    account = next(g for g in view['groups'] if g['kind'] == 'account')
    file = next(g for g in view['groups'] if g['kind'] == 'file')
    view = client.put(endpoint + '/retest-inputs', json=credentials(group_id=account['id'])).json()
    account_id = view['group_bindings'][account['id']]
    response = client.put(endpoint + '/retest-inputs', json={'revision': 1, 'case_ids': ['UPLOAD'],
        'group_id': file['id'], 'account_mode': 'none', 'account': {}, 'business_data': '',
        'files': [{'filename': 'employees.csv', 'content_base64': base64.b64encode(b'name\nDemo').decode()}]})
    assert response.status_code == 200, response.text
    view = response.json()
    file_id = view['group_bindings'][file['id']]
    assert view['case_input_ids']['AUTH'] == [account_id]
    assert view['case_input_ids']['UPLOAD'] == [account_id, file_id]
    task = client.post(endpoint + '/retests', json={'revision': 2, 'case_ids': ['AUTH', 'UPLOAD'], 'request_id': str(uuid4())}).json()['task']
    pid = task['project_id']
    call = partial(call, project_id=pid)
    assert task['case_input_ids']['UPLOAD'] == [account_id, file_id]
    inputs = call('ui_retest_inputs', task_id=task['task_id']).json()
    assert inputs['inputs'][account_id]['account']['password'] == 'synthetic-shared-secret'
    assert inputs['inputs'][file_id]['files'][0]['filename'] == 'employees.csv'
    assert inputs['dependency_inputs'] == {account['id']: account_id, file['id']: file_id}
    file_info = inputs['inputs'][file_id]['files'][0]
    assert call('ui_retest_file', task_id=task['task_id'], input_id=file_id, file_id=file_info['id']).status_code == 200
    # Omitted associations in an executor's first write still inherit the selected baseline.
    saved = call('ui_cases', cases=[{k: v for k, v in case('AUTH').items() if k != 'dependencies'},
                                   {k: v for k, v in case('UPLOAD').items() if k != 'dependencies'}]).json()
    assert saved['execution_plan']['skipped_cases'] == []
    assert len(saved['execution_plan']['dependencies_to_check']) == 2


def test_dependencies_require_explicit_context_and_target_changes_invalidate_checks(workspace):
    client, store, owner, pid, call = workspace
    assert call('ui_cases', cases=[case('NO-TENANT', [dependency(tenant='')])]).status_code == 400
    assert call('ui_cases', cases=[case('NO-ROLE', [dependency(role='')])]).status_code == 400
    saved = call('ui_cases', cases=[case('AUTH'), case('LOGIN-NEGATIVE', [])]).json()
    gid = saved['dependency_groups'][0]['id']
    store.update_project(owner, pid, {'ui_target_url': 'https://other.example.test/account'})
    assert check(call, saved, gid).status_code == 400


def test_shared_retest_scope_is_not_limited_by_case_transport_batch_size():
    cases = [case(str(i), status='blocked') for i in range(201)]
    chosen = ui_retests.selection({'imported_results': {'cases': cases}}, [c['case_id'] for c in cases])
    assert len(chosen) == 201


def test_new_retest_report_reuses_shared_data_and_preserves_single_case_exception(workspace):
    client, store, owner, pid, call = workspace
    report = publish_blocked(call, [case('AUTH'), case('UPLOAD')])
    endpoint = f"/api/projects/{pid}/reports/{report['id']}"
    group = client.get(endpoint + '/retest-inputs').json()['groups'][0]
    shared = client.put(endpoint + '/retest-inputs', json=credentials(group_id=group['id'])).json()
    shared_id = shared['group_bindings'][group['id']]
    exceptional = client.put(endpoint + '/retest-inputs', json=credentials(1, business_data='AUTH 的专用订单')).json()
    exception_id = exceptional['bindings']['AUTH']
    task = client.post(endpoint + '/retests', json={'revision': 2, 'case_ids': ['AUTH', 'UPLOAD'], 'request_id': str(uuid4())}).json()['task']
    pid = task['project_id']
    call = partial(call, project_id=pid)
    saved = call('ui_cases', cases=[case('AUTH'), case('UPLOAD')]).json()
    # The single-case input has its own prerequisite check; a shared account
    # failure must not skip a case intentionally using different credentials.
    assert len(saved['dependency_groups']) == 2
    for g in saved['dependency_groups']:
        saved = check(call, saved, g['id']).json()
    new_report = call('ui_publish', execution_id=saved['execution_id'], title='仍然阻塞', summary='新轮前置检查仍阻塞').json()['report']
    new_endpoint = f"/api/projects/{pid}/reports/{new_report['id']}"
    view = client.get(new_endpoint + '/retest-inputs').json()
    assert view['case_input_ids'] == {'AUTH': [exception_id], 'UPLOAD': [shared_id]}
    assert view['case_overrides'] == ['AUTH']
    shared_group = next(g for g in view['groups'] if g['affected_case_ids'] == ['UPLOAD'])
    assert shared_group['input_id'] == shared_id
    updated = client.put(new_endpoint + '/retest-inputs', json=credentials(view['revision'],
        case_ids=['UPLOAD'], group_id=shared_group['id'], business_data='更新共同数据')).json()
    latest_id = updated['group_bindings'][shared_group['id']]
    old_view = client.get(endpoint + '/retest-inputs').json()
    assert old_view['case_input_ids'] == {'AUTH': [exception_id], 'UPLOAD': [latest_id]}
    assert ui_retests.execution_inputs(store, owner, store.get_project(owner, pid), task['task_id'])['case_inputs']['UPLOAD'] == [shared_id]
    # Prepared executions keep immutable references even as future common data changes.


def test_legacy_report_keeps_account_when_retest_discovers_a_missing_file(workspace):
    client, store, owner, pid, call = workspace
    old = call('ui_cases', cases=[case('UPLOAD', [], status='blocked', actual='缺少登录账号')]).json()
    report = call('ui_publish', execution_id=old['execution_id'], title='旧格式报告', summary='缺少账号').json()['report']
    endpoint = f"/api/projects/{pid}/reports/{report['id']}"
    initial = client.put(endpoint + '/retest-inputs', json=credentials(case_ids=['UPLOAD'])).json()
    account_id = initial['bindings']['UPLOAD']
    task = client.post(endpoint + '/retests', json={'case_ids': ['UPLOAD'], 'revision': 1, 'request_id': str(uuid4())}).json()['task']
    pid = task['project_id']
    call = partial(call, project_id=pid)
    file_dep = dependency(key='employee-fixture', kind='file', title='缺少员工文件', role='', tenant='')
    saved = call('ui_cases', cases=[case('UPLOAD', [dependency(), file_dep])]).json()
    for g in saved['dependency_groups']:
        saved = check(call, saved, g['id'], 'ready' if g['kind'] == 'account' else 'blocked').json()
    new = call('ui_publish', execution_id=saved['execution_id'], title='账号已补齐', summary='账号可用，员工文件缺失').json()['report']
    endpoint = f"/api/projects/{pid}/reports/{new['id']}"
    view = client.get(endpoint + '/retest-inputs').json()
    file_group = view['groups'][0]
    uploaded = client.put(endpoint + '/retest-inputs', json={'revision': view['revision'], 'case_ids': ['UPLOAD'],
        'group_id': file_group['id'], 'account_mode': 'none', 'account': {}, 'business_data': '',
        'files': [{'filename': 'employees.csv', 'content_base64': 'bmFtZQpEZW1v'}]}).json()
    assert account_id in uploaded['case_input_ids']['UPLOAD']
    assert len(uploaded['case_input_ids']['UPLOAD']) == 2


@pytest.mark.parametrize('points', [[], [{'id': 'read', 'title': 'read', 'kind': 'browser',
    'status': 'passed', 'expected': 'visible', 'depends_on': [], 'dependencies': [], 'question_ids': []}]])
def test_partial_verdict_is_review_work_not_automatic_report_completion(points):
    from api_test_tool.ui_dependencies import plan
    record = {'cases': [case('PARTIAL', [], status='partial', actual='only first assertion observed', checkpoints=points)]}
    result = plan(record)
    assert result['review_required_case_ids'] == ['PARTIAL']
    assert result['next_action']['action'] == 'review_remaining'
    assert result['runnable_case_ids'] == []  # Model chooses whether/how to continue; never auto-retest.
    assert record['cases'][0]['status'] == 'partial'
