import base64
import json
import re
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from api_test_tool.web import create_app
from api_test_tool.xlsx_results import parse_xlsx_results, result_findings


def xlsx_from_rows(rows):
    def cell(reference, value):
        return f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>'
    xml_rows = []
    for row_number, values in enumerate(rows, 1):
        cells = ''.join(cell(f'{chr(65 + index)}{row_number}', value) for index, value in enumerate(values))
        xml_rows.append(f'<row r="{row_number}">{cells}</row>')
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
             + ''.join(xml_rows) + '</sheetData></worksheet>')
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        archive.writestr('xl/workbook.xml', '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="测试用例" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="/xl/worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml', sheet)
    return output.getvalue()


def completed_results_xlsx():
    return xlsx_from_rows([
        ['用例ID', '模块', '优先级', '场景', '前置条件', '测试数据', '步骤', '预期结果/关键断言', '执行结果', '实际证据', '缺陷编号'],
        ['W01', '登录', 'P1', '正常登录', '用户已注册', '账号 test01 / 正确密码', '1. 输入账号 test01；2. 输入正确密码；3. 点击登录；4. 观察首页', '进入首页', '通过', '已进入首页', ''],
        ['W02', '登录', 'P0', '断网后提示', '登录页已打开', '账号 test02 / 正确密码', '1. 断开网络；2. 输入账号与密码；3. 点击登录；4. 观察错误提示', '显示网络错误', '失败', '页面持续转圈', ''],
        ['W03', '远程桌面', 'P1', '无测试设备', '设备列表为空', '', '1. 打开远程桌面详情；2. 观察设备连接区域', '连接测试设备', '阻塞', '环境没有测试设备', ''],
    ])


def test_ui_workspace_creates_session_and_keeps_it_out_of_api_workspace(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        bootstrap = client.get('/api/bootstrap').json()
        client.headers['x-csrf-token'] = bootstrap['csrf']

        page = client.get('/ui-testing')
        assert page.status_code == 200
        assert '/static/app.js?v=' in page.text
        assert '/static/ui-workflow.js?v=' in page.text
        assert 'id="project-list"' in page.text
        assert 'id="trash-dialog"' in page.text
        api_page = client.get('/api-testing')
        assert api_page.status_code == 200
        assert 'src="/static/signal-background/frame.html"' in page.text
        assert page.text == api_page.text
        assert '集成管理 · PingCode' in page.text

        created = client.post('/api/ui-tests', json={
            'title': 'BOSS 页面回归',
            'target_url': 'https://example.test/b/boss?platform=boss',
            'goal': '验证远程画面重连，并记录可复现缺陷。',
            'execution_permission': 'maximum',
        })
        assert created.status_code == 200, created.text
        project = created.json()['project']
        assert project['test_kind'] == 'ui'
        assert project['ui_target_url'] == 'https://example.test/b/boss?platform=boss'
        assert project['task']['goal'] == '验证远程画面重连，并记录可复现缺陷。'
        assert project['ui_execution_permission']['key'] == 'maximum'
        assert '不可逆操作' in project['ui_execution_permission']['description']

        listed = client.get('/api/ui-tests').json()['projects']
        assert [item['id'] for item in listed] == [project['id']]
        assert client.get('/api/bootstrap').json()['projects'] == []
        assert [item['id'] for item in client.get('/api/bootstrap?test_kind=ui').json()['projects']] == [project['id']]
        original = app.state.store.project_dir(
            app.state.store.session(client.cookies['api_test_session'])[0]['id'], project['id']) / project['document_file']
        assert 'https://example.test/b/boss?platform=boss' in original.read_text()
        assert '执行权限范围：最大权限（maximum）' in original.read_text()
        assert client.post('/api/ui-tests', json={
            'title':'错误权限', 'target_url':'https://example.test', 'goal':'验证',
            'execution_permission':'anything',
        }).status_code == 400


def test_ui_creation_requires_address_and_supports_exploration_without_documents(tmp_path):
    with TestClient(create_app(tmp_path, start_fixture=False, testing=True)) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        for target in (None, '', ' ', 'javascript:alert(1)'):
            ui = {'title': '页面探索', 'goal': '验证页面'}
            prd = {'title': '需求补充', 'filename': 'prd.md', 'content': '# 验收\n- 页面应显示商品。'}
            if target is not None:
                ui['target_url'] = prd['target_url'] = target
            assert client.post('/api/ui-tests', json=ui).status_code == 400
            assert client.post('/api/requirement-tests', json=prd).status_code == 400
        assert client.get('/api/ui-tests').json()['projects'] == []
        created = client.post('/api/ui-tests', json={'title': '页面探索', 'target_url': 'https://example.test'})
        assert created.status_code == 200, created.text
        project = created.json()['project']
        assert '完整的功能探索测试' in project['task']['goal']
        assert project['ui_target_url'] == 'https://example.test'
        response = client.put(f'/api/ui-tests/{project["id"]}/materials', json={'target_url': ''})
        assert response.status_code == 400
        assert client.get('/api/projects/' + project['id']).json()['project']['ui_target_url'] == 'https://example.test'


def test_ui_report_reuses_pingcode_review_and_submission_controls(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        project = client.post('/api/ui-tests', json={
            'title': '远程桌面 UI 测试',
            'target_url': 'https://example.test/remote',
            'goal': '验证重新进入页面后的自动重连。',
        }).json()['project']
        code = client.post('/api/mcp/pair').json()['code']
        token = client.post('/api/mcp/redeem', json={'code': code}).json()['token']
        report = client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token}, json={
            'action': 'task_report',
            'arguments': {
                'project_id': project['id'],
                'title': '远程桌面 UI 测试报告',
                'summary': '放大查看后重新进入页面，远程画面未恢复。',
                'sections': [{'title': '实际覆盖', 'content': '执行了进入、放大、关闭、重新进入。'}],
                'findings': [{
                    'title': '远程画面停留在 Connecting',
                    'detail': '重新进入后持续显示 Connecting。',
                    'evidence': '连续两次复现，等待 20 秒仍未恢复。',
                    'recommendation': '重建 noVNC 连接并展示失败状态。',
                    'severity': '严重',
                    'priority': '高',
                }],
                'run_ids': [],
            },
        }).json()['report']

        page = client.get(report['report_url'])
        assert page.status_code == 200
        assert 'CODEX · UI 测试报告' in page.text
        assert '目标页面：https://example.test/remote' in page.text
        assert 'href="/ui-testing"' in page.text
        assert '复制问题描述' in page.text
        assert '/static/pingcode.js' in page.text
        assert '0 份执行记录' not in page.text

        draft_url = report['report_url'].replace('index.html', 'pingcode/finding-0')
        draft = client.get(draft_url)
        assert draft.status_code == 200, draft.text
        assert '测试页面：https://example.test/remote' in draft.json()['description']
        assert '远程画面停留在 Connecting' in draft.json()['title']

        refreshed = client.get('/api/ui-tests').json()['projects'][0]
        assert refreshed['last_analysis']['report_url'] == report['report_url']
        assert refreshed['last_analysis']['findings_count'] == 1
        # UI sessions use the existing lifecycle and retain report history.
        removed = client.delete('/api/projects/' + project['id'])
        assert removed.status_code == 200
        assert client.get('/api/bootstrap?test_kind=ui').json()['projects'] == []
        assert client.get('/api/deleted-projects').json()['projects'][0]['id'] == project['id']
        restored = client.post('/api/projects/' + project['id'] + '/restore')
        assert restored.status_code == 200
        assert restored.json()['last_analysis']['report_url'] == report['report_url']
        assert client.get(report['report_url']).status_code == 200



def test_ui_target_requires_http_url(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        response = client.post('/api/ui-tests', json={
            'title': '无效地址', 'target_url': 'javascript:alert(1)', 'goal': '测试页面',
        })
        assert response.status_code == 400
        assert client.get('/api/ui-tests').json()['projects'] == []


def test_completed_xlsx_import_creates_result_report_and_pingcode_drafts(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        response = client.post('/api/ui-tests/import-results', json={
            'filename': 'BOSS_UI_执行结果.xlsx',
            'content_base64': base64.b64encode(completed_results_xlsx()).decode(),
            'target_url': 'https://example.test/boss',
            'environment': 'dev',
            'client': 'B端',
        })
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['counts'] == {'total': 3, 'passed': 1, 'failed': 1, 'blocked': 1,
                                    'not_run': 0, 'skipped': 0, 'other': 0}
        assert result['quality'] == {'missing_test_data': 1, 'brief_test_data': 0,
                                     'missing_steps': 0, 'brief_steps': 0}
        assert result['project']['ui_import_filename'] == 'BOSS_UI_执行结果.xlsx'

        page = client.get(result['report']['report_url'])
        assert page.status_code == 200
        assert '结果总结' in page.text
        assert '可提交缺陷' in page.text
        assert '账号 test02 / 正确密码' in page.text
        assert '【dev】【B端】【登录】 断网后提示' in page.text
        assert 'data-case-id="W02"' in page.text
        review = json.loads(re.search(r'id="report-review-data">(.*?)</script>', page.text, re.S).group(1))
        assert review['imported'] is True
        assert review['assets'] == []
        assert [case['case_id'] for case in review['cases']] == ['W01', 'W02', 'W03']
        assert page.text.count('class="copy-defect"') == 1
        assert '/static/report-review.js?v=' in page.text
        assert '/static/report-review.css?v=' in page.text
        assert '@layer report-legacy {' in page.text
        assert 'url("/static/report-theme.css") layer(report-legacy)' in page.text
        assert 'url("/static/shared-glass.css") layer(report-legacy)' in page.text
        assert 'class="report-overview"' in page.text
        assert '测试结果明细' not in page.text
        assert '<table' not in page.text
        assert '<h2>执行证据</h2>' not in page.text
        assert '/static/pingcode.js' in page.text

        failed_draft = client.get(result['report']['report_url'].replace('index.html', 'pingcode/finding-0'))
        assert failed_draft.status_code == 200
        assert failed_draft.json()['title'] == '【dev】【B端】【登录】 断网后提示'
        description = failed_draft.json()['description']
        report_reference = ('【平台报告】\n' + str(page.url) + '\n用例编号：W02\n'
                            '打开报告查看测试数据、复现步骤和执行证据；可下载的测试文件在报告中获取。')
        assert failed_draft.json()['report_reference'] == {
            'url': str(page.url), 'case_id': 'W02', 'text': report_reference,
        }
        assert description == ('【测试环境】\n未记录，可补充系统、浏览器及设备信息\n\n【前置条件】\n登录页已打开\n\n【测试数据】\n账号 test02 / 正确密码\n\n'
                               '【测试步骤】\n1. 断开网络；2. 输入账号与密码；3. 点击登录；4. 观察错误提示\n\n'
                               '【预期结果】\n显示网络错误\n\n【实际结果】\n页面持续转圈\n\n' + report_reference)
        assert description.count(str(page.url)) == 1
        assert '模块' not in description and '代码依据' not in description and '检查时间' not in description


def test_xlsx_import_rejects_invalid_workbook(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    content = b'not a workbook'
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        response = client.post('/api/ui-tests/import-results', json={
            'filename': 'bad.xlsx', 'content_base64': base64.b64encode(content).decode(),
        })
        assert response.status_code == 400
        assert '有效的 XLSX' in response.json()['detail']


def test_xlsx_import_preserves_report_with_missing_environment_and_client(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        content = base64.b64encode(completed_results_xlsx()).decode()
        missing_environment = client.post('/api/ui-tests/import-results', json={
            'filename': 'results.xlsx', 'content_base64': content, 'client': 'B端',
        })
        assert missing_environment.status_code == 200
        page = client.get(missing_environment.json()['report']['report_url'])
        assert '【待补充环境】【B端】【登录】' in page.text
        missing_client = client.post('/api/ui-tests/import-results', json={
            'filename': 'results.xlsx', 'content_base64': content, 'environment': 'dev',
        })
        assert missing_client.status_code == 200
        page = client.get(missing_client.json()['report']['report_url'])
        assert '【dev】【待补充端】【登录】' in page.text


def test_long_memory_headers_keep_real_input_steps_and_problem_description():
    workbook = xlsx_from_rows([
        ['序号', '用例名称', '测试目的', '前置条件', '完整测试输入', '逐步操作', '预期结果', '实际结果与缺陷', '状态'],
        ['2', '保存多字段稳定偏好', '验证长期记忆写入', '使用测试账号登录；新建空白对话',
         '请把宁波、P7、周二远程作为长期稳定招聘偏好保存。',
         '1. 打开新的对话。\n2. 粘贴完整测试输入。\n3. 点击发送并等待完成。',
         '识别为长期记忆写入请求；保存全部字段并明确回复已保存。',
         '系统错误识别为查询，返回“未找到匹配记忆”，没有保存。\n缺陷：稳定偏好写入被误判为查询（BUG-02，高）。',
         '失败'],
    ])

    parsed = parse_xlsx_results(workbook, environment='test', client='B端')
    case = parsed['cases'][0]
    assert case['case_id'] == '2'
    assert case['test_data'].startswith('请把宁波、P7')
    assert case['steps'].startswith('1. 打开新的对话')
    assert case['evidence'].startswith('系统错误识别为查询')
    assert parsed['quality'] == {'missing_test_data': 0, 'brief_test_data': 0,
                                 'missing_steps': 0, 'brief_steps': 0}

    finding = result_findings(parsed)[0]
    assert finding['title'] == '【test】【B端】【待补充模块】 保存多字段稳定偏好'
    assert finding['actual'] == case['evidence']
    assert 'XLSX 第' not in finding['actual']
