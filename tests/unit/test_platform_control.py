import json

from fastapi.testclient import TestClient

from api_test_tool.web import create_app


def paired(client):
    code = client.post('/api/mcp/pair').json()['code']
    token = client.post('/api/mcp/redeem', json={'code': code}).json()['token']

    def call(action, **arguments):
        response = client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                               json={'action': action, 'arguments': arguments})
        assert response.status_code == 200, response.text
        return response.json()

    return call


def test_control_plane_creates_ui_session_and_finishes_without_web_setup(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        call = paired(client)

        missing_target = call('start_workflow', goal='验证登录', test_kind='ui')
        assert missing_target['created'] is False
        assert missing_target['required_inputs'] == ['target_url']
        assert call('list_sessions', test_kind='ui')['sessions'] == []

        started = call('start_workflow', goal='验证登录、退出与异常恢复', test_kind='auto',
                       target_url='https://example.test/login')
        pid = started['project_id']
        assert started['created'] is True
        assert started['status']['test_kind'] == 'ui'
        assert started['status']['ready_for_execution'] is True
        assert started['next_action'] == 'get_test_context'

        saved = call('save_materials', project_id=pid, requirements='登录后可安全退出',
                     business_rules='连续失败应显示可恢复提示', test_data='合成测试账号，由浏览器会话登录')
        assert saved['project']['task']['requirements'] == '登录后可安全退出'
        assert call('list_sessions', test_kind='ui', limit=10)['sessions'][0]['project_id'] == pid

        cases = call('ui_cases', project_id=pid, cases=[{
            'case_id': 'LOGIN-001', 'scenario': '正常登录', 'module': '登录',
            'environment': 'test', 'client': 'C端', 'test_environment': 'Chrome桌面',
            'priority': 'P0', 'executor': 'AI', 'precondition': '已打开登录页',
            'test_data': '合成账号', 'steps': '1. 输入账号\n2. 点击登录',
            'expected': '进入首页', 'actual': '进入首页', 'status': 'passed',
            'rule_basis': '页面登录承诺', 'method': '正向场景', 'cleanup': '退出账号',
            'executed_at': '2026-09-22T10:00:00+08:00',
        }])
        assert cases['total'] == 1
        status = call('workflow_status', project_id=pid)
        assert status['case_counts'] == {'passed': 1}
        assert status['next_action'] == 'publish_ui_test_report'

        published = call('finish_workflow', project_id=pid, summary='已完成登录验证并退出测试账号。')
        assert published['report']['report_url'].endswith('/index.html')
        assert call('workflow_status', project_id=pid)['progress']['phase'] == 'completed'
        decisions = call('defect_decisions', project_id=pid)
        assert decisions['decisions'] == []

        regression = call('start_regression', project_id=pid)
        assert regression['project_id'] != pid
        assert regression['project']['execution_round']['parent_project_id'] == pid
        assert regression['regression_round'] is True
        assert regression['project']['regression_round']['source_project_id'] == pid
        assert regression['project']['effective_filename'] == 'ui-regression.md'
        assert regression['status']['execution_id'] == ''
        assert regression['status']['case_counts'] == {}
        assert regression['status']['next_action'] == 'get_test_context'


def test_control_plane_creates_api_session_and_publishes_analysis(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        call = paired(client)
        document = json.dumps({'openapi': '3.0.3', 'info': {'title': '示例', 'version': '1'},
                               'paths': {'/health': {'get': {'responses': {'200': {'description': 'OK'}}}}}})
        started = call('start_workflow', goal='检查接口文档完整性', test_kind='api', title='接口检查',
                       filename='openapi.json', content=document)
        pid = started['project_id']
        assert started['status']['test_kind'] == 'api'
        assert started['status']['ready_for_design'] is True
        assert started['status']['ready_for_execution'] is False
        assert started['status']['next_action'] == 'get_test_document'

        report = call('finish_workflow', project_id=pid, summary='已检查文档，未发送真实请求。',
                      findings=[{'title': '缺少服务地址', 'detail': '文档未声明 servers。'}])
        assert report['report']['requests_sent'] == 0
        status = call('workflow_status', project_id=pid)
        assert status['latest_report']['id'] == report['report']['id']
        assert status['next_action'] == 'get_test_report'
