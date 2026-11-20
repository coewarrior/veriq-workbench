"""Native default and S1 across the HTTP entry points used by MCP and the UI."""
from api_test_tool.orchestration_storage import read_metadata
import json

from fastapi.testclient import TestClient

from api_test_tool.web import create_app
from test_native_contexts import environment as browser_environment


def test_default_native_http_and_desktop_stop_contract(tmp_path, monkeypatch):
    monkeypatch.setenv('API_TEST_DRAIN_FILE', str(tmp_path / 'deploy-drain'))
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        account_project = client.post('/api/account-projects', json={
            'name': 'fixture', 'login_url': 'https://test.example/login',
        }).json()
        code = client.post('/api/mcp/pair').json()['code']
        token = client.post('/api/mcp/redeem', json={'code': code}).json()['token']
        headers = {'Authorization': 'Bearer ' + token}

        def mcp(tool_action, **arguments):
            return client.post('/api/mcp/call', headers=headers, json={
                'action': tool_action, 'arguments': arguments,
            })

        start = dict(request_id='native-once', goal='Inspect fixture', test_kind='ui',
                     account_project_id=account_project['id'])
        response = mcp('start_workflow', **start)
        assert response.status_code == 200, response.text
        created = response.json()
        assert created['execution']['mode'] == 'native_browser'
        assert created['execution']['scheduled'] is False
        assert all(module['reason'] == '等待桌面 Codex 会话领取账号'
                   for module in created['execution']['modules'])
        assert mcp('start_workflow', **start).json()['project_id'] == created['project_id']
        task_id = created['execution']['task_id']
        project_id = created['project_id']
        ref = 'thread:01a1576c-6fb5-7ce3-9ade-3f4e6c5dab60'

        def direct(**arguments):
            if arguments.get('action') == 'claim':
                arguments['arguments'] = {'browser_environment': browser_environment()}
            return mcp('direct_session', holder_id='desktop-chat', executor_ref=ref,
                       task_id=task_id, **arguments)

        waiting = direct(action='claim').json()
        assert waiting['state'] == 'queued'
        assert waiting['resource_wait']['end_turn'] is True
        assert waiting['next_action'] == 'end_turn_until_resources'
        assert waiting['lease_id'] is None
        controller = app.state.orchestration
        with controller.connect() as db:
            state = read_metadata(db)
        owner = state['tasks'][task_id]['owner']
        controller.add_account(owner, dict(account_project_id=account_project['id'],
                                          identity='fixture', credential=''))

        ready_response = direct(action='claim', node_id=waiting['node_id'])
        assert ready_response.status_code == 200, ready_response.text
        ready = ready_response.json()
        lease_id = ready['lease_id']
        node_id = ready['node_id']
        assert lease_id and ready['account_ready']
        assert ready['browser_ready'] is False  # Allocation is not a browser observation.
        context = direct(action='context', lease_id=lease_id).json()
        assert context['execution_host']['browser_tool'] == 'cua_repl'
        assert context['dispatch'] is None
        other = mcp('direct_session', action='context', holder_id='other-chat',
                    task_id=task_id, lease_id=lease_id)
        assert other.status_code == 403
        forbidden = direct(action='browser', lease_id=lease_id, browser_action='snapshot')
        assert forbidden.status_code == 400 and '原生' in forbidden.json()['detail']
        with controller.transaction() as (_, state):
            assert not state['runners'] and not state['outbox']
            assert not list(state['direct_commands']) and not list(state['operations'])

        control_url = '/api/orchestration/tasks/' + task_id + '/control'
        confirmation = dict(action='confirm_native_exit', revision=1, node_ids=[node_id],
                            executor_stopped=True, browser_stopped=True,
                            reason='已在桌面停止会话并关闭本任务测试浏览器')
        assert client.post(control_url, json=confirmation).status_code == 409
        stopped = client.post(control_url, json={
            'action': 'stop', 'revision': 1, 'request_id': 'native-stop',
        })
        assert stopped.status_code == 200, stopped.text

        def managed():
            result = client.get('/api/projects/' + project_id + '/managed')
            assert result.status_code == 200, result.text
            return result.json()

        snapshot = managed()
        stop = snapshot['tasks'][0]['desktop_stop']
        assert stop['platform_scheduling_stopped'] is True
        assert stop['manual_stop_required'] is True
        row = stop['required_sessions'][0]
        assert row['node_id'] == node_id and row['executor_ref'] == ref
        assert row['thread_url'] == 'codex://threads/01a1576c-6fb5-7ce3-9ade-3f4e6c5dab60'
        assert not row['executor_exit_confirmed'] and not row['browser_stopped']
        assert not row['accounts_released'] and row['desktop_api_cancelled'] is False
        assert snapshot['leases']  # The stop button alone never frees a desktop account.

        incomplete = client.post(control_url, json={
            **confirmation, 'revision': 2, 'browser_stopped': False,
        })
        assert incomplete.status_code == 400
        assert managed()['leases']
        confirmed = client.post(control_url, json={**confirmation, 'revision': 2})
        assert confirmed.status_code == 200, confirmed.text
        snapshot = managed()
        assert not snapshot['leases']
        stop = snapshot['tasks'][0]['desktop_stop']
        assert stop['manual_stop_required'] is False
        row = stop['required_sessions'][0]
        assert row['accounts_released'] and row['executor_exit_confirmed']
        assert row['browser_stopped'] and row['exit_confirmation_source'] == 'user_confirmation'
        assert row['desktop_api_cancelled'] is False

        # Another session for the same owner cannot inherit this S1 receipt.
        second = mcp('start_workflow', **{**start, 'request_id': 'another-session'}).json()
        isolated = client.get('/api/projects/' + second['project_id'] + '/managed').json()
        assert isolated['desktop_stop']['required_sessions'] == []
        assert isolated['tasks'][0]['desktop_stop']['required_sessions'] == []
