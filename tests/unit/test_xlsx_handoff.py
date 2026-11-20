"""Synthetic core-field handoff; no business data or external execution."""
import base64
import json
import re
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from api_test_tool.task_reports import render_task_report
from api_test_tool.ui_records import LABELS, export_xlsx
from api_test_tool.web import create_app
from api_test_tool.xlsx_results import parse_xlsx_results, result_findings


UI_RESULTS = {
    'passed': '通过', 'failed': '不通过', 'partial': '验证未完成',
    'blocked': '阻塞', 'not_run': '未执行', 'pending_rule': '待确认规则',
    'pending_action': '待用户确认',
}
CORE_FIELDS = (
    'case_id', 'scenario', 'module', 'executor', 'precondition', 'test_data',
    'steps', 'expected', 'evidence', 'conclusion', 'not_run_reason', 'result',
)


def synthetic_cases(use_status_keys=False):
    results = {**UI_RESULTS, 'skipped': '跳过', 'other': '未识别的外部状态'}
    return [{
        'case_id': f'SYNTHETIC-{index}', 'scenario': f'合成存储夹具 {status}',
        'module': '数据交接', 'executor': '合成结果导入，不执行业务',
        'precondition': '仅本地隔离测试\n无业务系统连接',
        'test_data': '=1+1\n包含 <文本> & "引号"',
        'steps': '1. 导出合成记录。\n2. 导入并比较核心字段。',
        'expected': '状态及结论保留\n不将未执行改为通过',
        'evidence': '仅验证存储与展示\n没有实际业务执行',
        'conclusion': f'{status} 的合成结论\n第二行含 <说明> & "原文"',
        'not_run_reason': '合成存储夹具，未执行业务',
        'result': status if use_status_keys and status != 'other' else result,
        'status': status,
    } for index, (status, result) in enumerate(results.items(), 1)]


@pytest.mark.parametrize('status,label', UI_RESULTS.items())
@pytest.mark.parametrize('use_status_key', [False, True])
def test_parser_accepts_every_native_ui_status_without_rewriting_result(status, label, use_status_key):
    assert UI_RESULTS == LABELS
    raw_result = status if use_status_key else label
    parsed = parse_xlsx_results(export_xlsx({'imported_results': {'cases': [{
        'case_id': 'SYNTHETIC', 'result': raw_result, 'conclusion': '独立结论\n第二行',
    }]}}))
    assert parsed['cases'][0]['status'] == status
    assert parsed['cases'][0]['result'] == raw_result
    assert parsed['cases'][0]['conclusion'] == '独立结论\n第二行'
    assert parsed['counts'][status] == 1
    assert sum(value for key, value in parsed['counts'].items() if key != 'total') == 1


@pytest.mark.parametrize('use_status_keys', [False, True])
def test_xlsx_import_report_and_second_export_keep_core_fields(tmp_path, use_status_keys):
    cases = synthetic_cases(use_status_keys)
    content = export_xlsx({'imported_results': {'cases': cases}})
    parsed = parse_xlsx_results(content)
    expected_counts = {'total': len(cases), **Counter(case['status'] for case in cases)}
    assert parsed['counts'] == expected_counts
    assert [item['case_id'] for item in result_findings(parsed)] == ['SYNTHETIC-2']
    with TestClient(create_app(tmp_path, start_fixture=False, testing=True)) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        payload = {'filename': 'synthetic-results.xlsx',
                   'content_base64': base64.b64encode(content).decode()}
        imported = client.post('/api/ui-tests/import-results', json=payload)
        assert imported.status_code == 200, imported.text
        result = imported.json()
        assert result['counts'] == expected_counts
        assert result['project']['last_job'] == {}
        report_url = result['report']['report_url']
        saved_response = client.get(report_url.replace('index.html', 'report.json'))
        assert saved_response.status_code == 200
        saved = saved_response.json()
        assert saved['runs'] == []
        assert len(saved['findings']) == 1
        assert saved['findings'][0]['case_id'] == 'SYNTHETIC-2'
        for label in ('验证未完成', '待确认规则', '待用户确认', '其他'):
            assert f'{label} 1 条' in saved['summary']
        static_html = render_task_report(saved)
        for status, label in UI_RESULTS.items():
            assert f'class="result-count result-{status}"><b>1</b>{label if status != "failed" else "失败"}' in static_html

        page = client.get(report_url)
        assert page.status_code == 200
        review = json.loads(re.search(r'id="report-review-data">(.*?)</script>', page.text, re.S).group(1))
        assert review['imported'] is True
        assert Counter(case['status'] for case in review['cases']) == Counter(case['status'] for case in cases)
        assert [case['conclusion'] for case in review['cases']] == [case['conclusion'] for case in cases]
        second_export = client.get(report_url.replace('index.html', 'cases.xlsx'))
        assert second_export.status_code == 200
        reparsed = parse_xlsx_results(second_export.content)
        assert reparsed['counts'] == expected_counts
        for rows in (parsed['cases'], saved['imported_results']['cases'], reparsed['cases']):
            assert len(rows) == len(cases)
            for original, actual in zip(cases, rows):
                assert {key: actual[key] for key in CORE_FIELDS} == {key: original[key] for key in CORE_FIELDS}
                assert actual['status'] == original['status']

        # A later import creates its own record and cannot rewrite the first snapshot.
        payload['content_base64'] = base64.b64encode(second_export.content).decode()
        later = client.post('/api/ui-tests/import-results', json=payload)
        assert later.status_code == 200
        assert later.json()['report']['report_url'] != report_url
        assert client.get(report_url.replace('index.html', 'report.json')).content == saved_response.content
