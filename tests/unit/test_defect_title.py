import base64
import pytest
from fastapi.testclient import TestClient
from api_test_tool.defect_title import normalize_title, validate_title
from api_test_tool.web import create_app
from api_test_tool.xlsx_results import parse_xlsx_results, result_findings
from test_ui_testing import xlsx_from_rows


def test_device_and_same_as_above_are_not_business_attributes():
    title = normalize_title('[dev, 同上]【macOS Chrome桌面】【引导主流程】 完整16步')
    assert title == '【待补充环境】【待补充端】【引导主流程】 完整16步'
    with pytest.raises(ValueError):
        validate_title(title)
    validate_title('[test]【C端】【新手引导】 退出后未保存')


def test_explicit_selection_overrides_workbook_attributes():
    content = xlsx_from_rows([['用例ID','环境','客户端','功能/模块','场景','执行结果'],
                             ['1','dev, 同上','macOS Chrome桌面','引导主流程','完整16步','失败']])
    parsed = parse_xlsx_results(content, environment='test', client='B端')
    assert result_findings(parsed)[0]['title'] == '【test】【B端】【引导主流程】 完整16步'


def test_all_missing_still_generates_report_but_submission_requires_attributes(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    content = xlsx_from_rows([['用例ID','场景','执行结果'], ['1','按钮未响应','失败']])
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        response = client.post('/api/ui-tests/import-results', json={
            'filename':'results.xlsx','content_base64':base64.b64encode(content).decode()})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['counts']['total'] == 1
        route = result['report']['report_url'].replace('index.html','pingcode/finding-0')
        draft = client.get(route).json()
        assert draft['title'] == '【待补充环境】【待补充端】【待补充模块】 按钮未响应'
        assert draft['ui_title'] is True
        for title in [draft['title'], '[dev, 同上]【macOS Chrome桌面】【引导】 按钮未响应']:
            sent = client.post(route, json={'reviewed':True,'payload':{'title':title,'description':'实际结果'}})
            assert sent.status_code == 400
            assert '提交前请补齐标题' in sent.json()['detail']


@pytest.mark.parametrize('prefix', ['[prod]', '【prod】'])
def test_environment_brackets_normalize_without_duplicate_prefix(prefix):
    title = prefix + '【B端】【企业知识库】 文件解析失败'
    assert normalize_title(title) == '【prod】【B端】【企业知识库】 文件解析失败'
    validate_title(title)
