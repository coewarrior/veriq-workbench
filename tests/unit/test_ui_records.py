import base64
import importlib.util
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from api_test_tool.web import create_app
from api_test_tool.ui_records import AI_ANALYSIS_GUIDANCE, as_results
from api_test_tool.defect_drafts import finding_draft
from api_test_tool.xlsx_results import parse_xlsx_results

PNG = base64.b64encode(b'\x89PNG\r\n\x1a\nsynthetic-unit-test').decode()


def create_ui_record_project(client, *, json):
    """Historical record fixtures still need today's real owning-project setup."""
    project = client.post('/api/account-projects', json={
        'name': json['title'], 'login_url': json['target_url']})
    assert project.status_code == 200, project.text
    return client.post('/api/ui-tests', json={**json, 'account_project_id': project.json()['id']})


@pytest.mark.parametrize('value', [
    '观察到错误，复现2/2。现场截图已关联。缺陷标题：[prod]【B端】【模块】问题',
    '现场复现1/1并已先截图。影响：按钮仍可点击。',
    '截图显示错误提示内容发生变化。',
])
def test_result_view_preserves_executor_observation_verbatim(value):
    record = {'cases': [{'case_id': 'C1', 'status': 'failed', 'actual': value,
                         'rule_basis': '', 'method': ''}]}
    displayed = as_results(record)['cases'][0]
    assert displayed['actual'] == displayed['evidence'] == value
    assert record['cases'][0]['actual'] == value


@pytest.mark.parametrize('analysis', [
    '这条用例确认没有资料时，系统不会编造答案。页面已正确拦住提问，但历史记录仍有残留。',
    '提问被拦截，但历史记录仍有残留。残留的具体原因还没查明。',
    # Writing guidance must not become a lossy automatic rewrite or a save gate.
    '旧解读包含夹具、断言和工具名 pypdf；原因未知。',
])
def test_ai_analysis_guidance_does_not_rewrite_case_or_result(tmp_path, analysis):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        project = create_ui_record_project(client, json={
            'title': '知识库', 'target_url': 'https://example.test/knowledge', 'goal': '验证无资料状态'
        }).json()['project']
        pid = project['id']
        code = client.post('/api/mcp/pair').json()['code']
        token = client.post('/api/mcp/redeem', json={'code': code}).json()['token']

        def call(action, **arguments):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                               json={'action': action, 'arguments': {'project_id': pid, **arguments}})

        saved = call('ui_cases', cases=[{
            'case_id': 'KB01', 'scenario': '无资料时禁止提问', 'test_data': '空知识库',
            'steps': '打开知识库并尝试提问', 'expected': '提示先上传资料',
            'actual': '提问被拦截，历史记录仍有残留。', 'conclusion': '部分符合预期。',
            'ai_analysis': analysis, 'status': 'partial'}])
        assert saved.status_code == 200, saved.text
        assert saved.json()['coverage_check']['ai_analysis_guidance'] == AI_ANALYSIS_GUIDANCE
        readback = call('ui_read', execution_id=saved.json()['execution_id']).json()
        assert readback['coverage_check']['ai_analysis_guidance'] == AI_ANALYSIS_GUIDANCE
        assert readback['cases'][0]['ai_analysis'] == analysis
        published = call('ui_publish', execution_id=saved.json()['execution_id'],
                         title='知识库报告', summary='无资料状态部分符合预期').json()
        assert published['coverage_check']['ai_analysis_guidance'] == AI_ANALYSIS_GUIDANCE
        report = client.get(f"/api/projects/{pid}/reports/{published['report']['id']}/report.json").json()
        case = report['imported_results']['cases'][0]
        assert case['ai_analysis'] == analysis
        assert case['status'] == 'partial'
        assert case['evidence'] == '提问被拦截，历史记录仍有残留。'
        assert case['test_data'] == '空知识库'
        assert report['imported_results']['counts'] == {'partial': 1, 'total': 1}


@pytest.mark.parametrize('actual', [
    '预览以图像呈现，不是解析失败。已核对内容。',
    '不是解析失败',
    '并非“提取失败”；内容可查看。',
    '内容可查询， 并非检索失败。',
    '不是索引失败！结果已就绪。',
    '未出现解析失败。内容核对正确。',
    '没有出现“解析失败”，内容核对正确。',
    '未发生提取失败。',
    '并未发生索引失败。',
    '没有检索失败。',
    '不存在解析失败。',
    '未见解析失败。',
    '没有发生解析失败。',
    '解析失败未发生。',
    '暂未出现解析失败。',
    '不是解析失败，而是提取失败。',
    '不是解析失败。随后检索失败。',
    '不是解析失败，但返回 MINERU_PARSE_FAILED。',
    '不是解析失败吗？',
    '不是解析失败就是索引失败。',
    '不能说不是解析失败。',
    '并非不是解析失败。',
    '页面提示“解析失败”。',
    '没有出现解析失败，而是索引失败。',
    '未出现解析失败，但返回 MINERU_PARSE_FAILED。',
    '未出现解析失败。随后检索失败。',
    '并非未出现解析失败。',
    '不能说没有出现解析失败。',
    '没有出现解析失败？',
    '不是所有文件都没有出现解析失败。',
    '没有解析失败是不可能的。',
    '没有出现解析失败就算通过，实际索引失败。',
    '没有出现EXTRACTION_LIMIT。',
    '未发生MINERU_PARSE_FAILED。',
    '不能说解析失败未发生。',
    '解析失败未发生是不可能的。',
    '解析失败未发生吗？',
    '解析失败未发生，但检索失败。',
])
def test_processing_keywords_do_not_override_executor_result(tmp_path, actual):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        project = create_ui_record_project(client, json={
            'title': '合成文件', 'target_url': 'https://example.test/files', 'goal': '验证上传解析'
        }).json()['project']
        code = client.post('/api/mcp/pair').json()['code']
        token = client.post('/api/mcp/redeem', json={'code': code}).json()['token']

        def call(action, **arguments):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                               json={'action': action, 'arguments': {'project_id': project['id'], **arguments}})

        saved = call('ui_cases', cases=[{
            'case_id': 'FILE', 'scenario': '上传解析后内容可用', 'steps': '上传合成文件并查看内容',
            'expected': '解析后可读取原文', 'actual': actual,
            'conclusion': '必要内容检查通过。', 'status': 'passed'}])
        assert saved.status_code == 200, saved.text
        case = call('ui_read', execution_id=saved.json()['execution_id']).json()['cases'][0]
        assert case['actual'] == actual
        assert case['status'] == 'passed'
        assert case['conclusion'] == '必要内容检查通过。'


def test_processing_failure_wording_preserves_explicit_verdict_and_scope(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        project = create_ui_record_project(client, json={
            'title': '知识库', 'target_url': 'https://example.test/knowledge', 'goal': '验证文件上传'
        }).json()['project']
        code = client.post('/api/mcp/pair').json()['code']
        token = client.post('/api/mcp/redeem', json={'code': code}).json()['token']

        def save(case):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                               json={'action': 'ui_cases', 'arguments': {'project_id': project['id'], 'cases': [case]}})

        base = {'case_id': 'KB15', 'scenario': '32 MiB TXT 上传大小校验',
                'precondition': '已登录', 'test_data': '32 MiB TXT', 'steps': '上传文件并查看解析状态',
                'expected': '32 MiB 文件允许上传',
                'actual': '文件上传成功，但解析失败，错误 EXTRACTION_LIMIT。', 'status': 'passed'}
        assert save(base).status_code == 200
        accepted = save({**base, 'conclusion': '大小校验通过，但文档处理失败，不能用于检索。'})
        assert accepted.status_code == 200, accepted.text
        broad = save({**base, 'scenario': '32 MiB TXT 上传解析与就绪',
                      'conclusion': '上传成功，但解析失败，文档不可用。'})
        assert broad.status_code == 200, broad.text
        usable = save({**base, 'scenario': '上传 32 MiB TXT 到知识库并正常使用',
                       'conclusion': '上传成功，但解析失败，文档不可用。'})
        assert usable.status_code == 200, usable.text


@pytest.mark.parametrize('channel', ['browser', 'mcp'])
def test_published_case_wording_can_be_corrected_without_changing_frozen_result(tmp_path, channel):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        project = create_ui_record_project(client, json={
            'title': '知识库', 'target_url': 'https://example.test/knowledge', 'goal': '验证文件大小'
        }).json()['project']
        pid = project['id']
        code = client.post('/api/mcp/pair').json()['code']
        token = client.post('/api/mcp/redeem', json={'code': code}).json()['token']

        def call(action, **arguments):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                               json={'action': action, 'arguments': {'project_id': pid, **arguments}})

        first = call('ui_cases', cases=[{
            'case_id': 'KB15', 'scenario': '32 MiB 边界', 'precondition': '已登录',
            'test_data': '33554432 字节文件', 'steps': '上传文件', 'expected': '边界允许上传',
            'actual': '上传成功；随后 EXTRACTION_LIMIT。',
            'conclusion': '大小校验通过，但文档处理失败，不能用于检索。', 'status': 'passed'}])
        assert first.status_code == 200, first.text
        published = call('ui_publish', execution_id=first.json()['execution_id'],
                         title='知识库报告', summary='已验证上传边界').json()
        rid = published['report']['id']
        path = f'/api/projects/{pid}/reports/{rid}'
        correction = {key: value for key, value in {
            'scenario': '32 MiB TXT 文件能否通过大小校验', 'precondition': '已登录知识库',
            'test_data': '32 MiB TXT 文件，33,554,432 字节。',
            'steps': '1. 打开知识库。\n2. 上传文件。\n3. 检查解析状态。',
            'expected': '32 MiB 文件应允许上传。',
            'evidence': '32 MiB 文件上传成功，但解析失败，错误码 EXTRACTION_LIMIT。',
            'conclusion': '大小校验通过；文档处理失败，不能用于检索。'
        }.items()}
        def correct(revision):
            if channel == 'mcp':
                return call('ui_correct', report_id=rid, case_id='KB15', revision=revision, fields=correction)
            return client.post(f'{path}/case-corrections/KB15', json={'revision': revision, 'fields': correction})
        updated = correct(0)
        assert updated.status_code == 200, updated.text
        assert updated.json()['revision'] == 1
        assert correct(0).status_code == 400
        readback = call('report').json()['analysis']
        assert readback['case_corrections']['revision'] == 1
        assert readback['imported_results']['cases'][0]['test_data'] == correction['test_data']
        with TestClient(app) as other:
            other.headers['x-csrf-token'] = other.get('/api/bootstrap').json()['csrf']
            other_token = other.post('/api/mcp/redeem', json={
                'code': other.post('/api/mcp/pair').json()['code'],
            }).json()['token']
            denied = other.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + other_token},
                                json={'action': 'ui_correct', 'arguments': {'project_id': pid,
                                      'report_id': rid, 'case_id': 'KB15', 'revision': 1, 'fields': correction}})
            assert denied.status_code in {403, 404}
        visible = client.get(f'{path}/index.html').text
        assert '32 MiB 文件上传成功，但解析失败' in visible
        assert '编辑用例描述' not in visible  # rendered by the live report script
        assert '文档处理失败，不能用于检索' in client.get(f'{path}/cases.html').text
        assert '文档处理失败，不能用于检索' in client.get(f'{path}/report.json').json()['imported_results']['cases'][0]['conclusion']
        owner = app.state.store.find_project_owner(pid)
        original = app.state.store._read(app.state.store.project_dir(owner, pid) / 'analyses' / rid / 'report.json')
        assert original['imported_results']['cases'][0]['scenario'] == '32 MiB 边界'
        regression = client.post(f'/api/ui-tests/{pid}/regressions', json={
            'target_url': 'https://example.test/knowledge', 'goal': '回归 32 MiB 上传边界'
        })
        assert regression.status_code == 200, regression.text
        source = regression.json()['project']
        document = (app.state.store.project_dir(owner, source['id']) / source['effective_document_file']).read_text()
        assert '32 MiB TXT 文件能否通过大小校验' in document


def test_published_false_pass_can_be_downgraded_with_consistent_counts(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        project = create_ui_record_project(client, json={
            'title': '知识库', 'target_url': 'https://example.test/knowledge', 'goal': '验证批量上传'
        }).json()['project']
        pid = project['id']
        code = client.post('/api/mcp/pair').json()['code']
        token = client.post('/api/mcp/redeem', json={'code': code}).json()['token']

        def call(action, **arguments):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                               json={'action': action, 'arguments': {'project_id': pid, **arguments}})

        first = call('ui_cases', cases=[{
            'case_id': 'KB18', 'scenario': '多文件批量上传独立结果',
            'precondition': '已登录', 'test_data': '两个文件', 'steps': '同时选择两个文件',
            'expected': '每个文件有独立结果', 'actual': '只支持单选，改为依次上传。',
            'status': 'passed'}])
        assert first.status_code == 200, first.text
        published = call('ui_publish', execution_id=first.json()['execution_id'],
                         title='知识库报告', summary='共1条，实际通过1、验证未完成0。').json()
        rid = published['report']['id']
        path = f'/api/projects/{pid}/reports/{rid}'
        fields = {'scenario': '单文件上传成功，批量上传未验证', 'precondition': '已登录',
                  'test_data': '两个文件', 'steps': '查看选择器并依次上传两个文件',
                  'expected': '批量选择后各文件应有独立结果',
                  'evidence': '选择器只支持单选；两个文件依次上传成功，未执行批量上传。',
                  'conclusion': '仅单文件顺序上传通过；原批量上传目标未验证，改为验证未完成。',
                  'status': 'partial'}
        update = client.post(f'{path}/case-corrections/KB18', json={'revision': 0, 'fields': fields})
        assert update.status_code == 200, update.text
        effective = client.get(f'{path}/report.json').json()
        assert effective['imported_results']['counts']['passed'] == 0
        assert effective['imported_results']['counts']['partial'] == 1
        assert effective['imported_results']['cases'][0]['result'] == '验证未完成'
        assert effective['imported_results']['cases'][0]['status_before_correction'] == 'passed'
        assert '验证未完成1' in effective['summary']
        assert '原始报告总结（修正前）' not in effective['summary']
        assert '实际通过1' not in effective['summary']
        assert '验证未完成' in client.get(f'{path}/index.html').text
        assert '验证未完成' in client.get(f'{path}/cases.html').text
        owner = app.state.store.find_project_owner(pid)
        frozen = app.state.store._read(app.state.store.project_dir(owner, pid) / 'analyses' / rid / 'report.json')
        assert frozen['imported_results']['cases'][0]['status'] == 'passed'
        rejected = client.post(f'{path}/case-corrections/KB18', json={'revision': 1,
                               'fields': {'status': 'failed', 'module': '资料上传', 'executor': '人工'}})
        assert rejected.status_code == 200, rejected.text
        effective = client.get(f'{path}/report.json').json()
        assert effective['imported_results']['counts']['failed'] == 1
        assert effective['imported_results']['counts']['partial'] == 0
        assert effective['imported_results']['cases'][0]['result'] == '不通过'
        assert effective['imported_results']['cases'][0]['module'] == '资料上传'
        assert effective['imported_results']['cases'][0]['executor'] == '人工'
        assert '不通过1' in effective['summary']
        with ZipFile(BytesIO(client.get(f'{path}/cases.xlsx').content)) as exported:
            sheet = exported.read('xl/worksheets/sheet1.xml').decode()
        assert '不通过' in sheet and '资料上传' in sheet
        assert client.post(f'{path}/case-corrections/KB18', json={'revision': 2,
                           'fields': {'status': 'not_a_status'}}).status_code == 400
        revised = client.post(f'{path}/report-corrections', json={'revision': 2,
                              'fields': {'title': '人工复核后的知识库报告',
                                         'summary': '批量上传未达到预期，记为不通过。'}})
        assert revised.status_code == 200, revised.text
        assert revised.json()['revision'] == 3
        corrected = client.get(f'{path}/report.json').json()
        assert corrected['title'] == '人工复核后的知识库报告'
        assert corrected['summary'] == '批量上传未达到预期，记为不通过。'
        assert '人工复核后的知识库报告' in client.get(f'{path}/index.html').text
        assert client.post(f'{path}/report-corrections', json={'revision': 2,
                           'fields': {'title': '过期', 'summary': ''}}).status_code == 400
        frozen = app.state.store._read(app.state.store.project_dir(owner, pid) / 'analyses' / rid / 'report.json')
        assert frozen['title'] == '知识库报告' and frozen['imported_results']['cases'][0]['status'] == 'passed'


def test_old_report_draft_preserves_actual_result_verbatim():
    text = finding_draft({'imported_results': {'cases': []}}, {
        'actual': '观察到错误。现场截图已关联。缺陷标题：[prod]【B端】【模块】问题',
    })
    assert '【实际结果】\n观察到错误。' in text
    assert '现场截图已关联。缺陷标题：[prod]【B端】【模块】问题' in text


def test_ui_round_storage_export_evidence_and_freeze(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as c:
        c.headers['x-csrf-token'] = c.get('/api/bootstrap').json()['csrf']
        project = create_ui_record_project(c, json={'title':'页面回归', 'target_url':'https://example.test', 'goal':'测试登录'}).json()['project']
        pid = project['id']
        code = c.post('/api/mcp/pair').json()['code']
        token = c.post('/api/mcp/redeem', json={'code':code}).json()['token']
        def call(action, **args):
            return c.post('/api/mcp/call', headers={'Authorization':'Bearer '+token}, json={'action':action,'arguments':{'project_id':pid,**args}})
        skill = call('document').json()['testing_skill']
        assert skill['name'] == 'web-exploratory-testing'
        assert any(f['path'].endswith('scripts/bootstrap.py') for f in skill['files'])
        assert c.get(skill['path']).status_code == 200
        first = call('ui_cases', cases=[{'case_id':'W01','scenario':'异常提示','precondition':'已登录', 'test_data':'=1+1\n测试账号甲\n文件：empty.txt',
                                      'steps':'1.点击\n2.观察','expected':'显示提示',
                                      'not_run_reason':'上轮报告 R1 的 W01 通过；本轮仅回归其他失败项'}])
        assert first.status_code == 200, first.text
        assert first.json()['title_attribute_gaps'] == [{'case_id':'W01', 'fields':['environment','client','module']}]
        assert 'B端/C端' in first.json()['title_guidance']
        assert 'defect_title_guidance' in call('document').json()
        assert 'defect_title_guidance' in call('context').json()
        execution = first.json()['execution_id']
        assert call('ui_read').json()['cases'][0]['status'] == 'not_run'
        assert call('ui_read').json()['cases'][0]['not_run_reason'] == '上轮报告 R1 的 W01 通过；本轮仅回归其他失败项'
        assert first.json()['coverage_check']['not_run_without_reason'] == []
        assert call('ui_cases', execution_id=execution, revision=0, cases=[{'case_id':'W02','scenario':'冲突'}]).status_code == 400
        update = call('ui_cases', execution_id=execution, revision=1, cases=[{'case_id':'W01','scenario':'异常提示','test_data':'=1+1\n测试账号甲\n文件：empty.txt',
                      'precondition':'已登录','steps':'1.点击\n2.观察','expected':'显示提示',
                      'actual':'未显示提示。现场截图已关联。缺陷标题：[test]【B端】【登录】错误标题',
                      'status':'failed',
                      'test_environment':'macOS Chrome桌面'}])
        assert update.status_code == 200, update.text
        assert update.json()['coverage_check']['failed_without_screenshot'] == ['W01']
        assert call('ui_read', execution_id=execution).json()['cases'][0]['actual'] == (
            '未显示提示。现场截图已关联。缺陷标题：[test]【B端】【登录】错误标题')
        args = dict(execution_id=execution, case_id='W01', step='2.观察', filename='error.png', content_type='image/png',content_base64=PNG,
                    captured_at='2026-09-21T03:00:00Z')
        asset = call('ui_asset', **args)
        assert asset.status_code == 200, asset.text
        aid = asset.json()['id']
        assert call('ui_read', execution_id=execution).json()['coverage_check']['failed_without_screenshot'] == []
        assert call('ui_asset', **args).json()['id'] == aid
        assert call('ui_asset', **{**args,'case_id':'other'}).status_code == 400
        fixture = call('ui_asset', execution_id=execution, case_id='W01', step='1.选择空文件',
                       filename='empty.txt', content_type='application/octet-stream', content_base64='',
                       kind='fixture', captured_at='2026-09-21T02:59:00Z')
        assert fixture.status_code == 200, fixture.text
        fixture_id = fixture.json()['id']
        url = f'/api/ui-tests/{pid}/executions/{execution}/cases.html'
        case_page = c.get(url).text
        assert '测试账号甲' in case_page and 'empty.txt' in case_page
        report = call('ui_publish', execution_id=execution, title='实际测试报告', summary='已执行一条，存在一项问题；临时数据已清理')
        assert report.status_code == 200, report.text
        report = report.json()['report']
        assert call('ui_publish', execution_id=execution, title='重复', summary='重复').json()['report']['id'] == report['id']
        assert call('ui_cases', execution_id=execution, revision=2, cases=[{'case_id':'W01','scenario':'覆盖'}]).status_code == 200
        assert call('ui_asset', **args).status_code == 200
        page = c.get(report['report_url'])
        assert 'asset-'+aid in page.text
        assert 'class="report-image-preview"' in page.text
        assert 'target="_blank"' not in page.text
        assert '/static/report-image-preview.js' in page.text
        review = json.loads(__import__('re').search(r'id="report-review-data">(.*?)</script>', page.text, __import__('re').S).group(1))
        assert {asset['kind'] for asset in review['assets']} == {'screenshot', 'fixture'}
        frozen = c.get(report['report_url'].replace('index.html', 'report.json')).json()
        assert review['timing'] is None
        assert '无法计算' in review['timingNotice']
        fixture_download = c.get(report['report_url'].replace('index.html', 'asset-' + fixture_id))
        assert fixture_download.status_code == 200 and fixture_download.content == b''
        assert 'attachment' in fixture_download.headers['content-disposition']
        data_zip = c.get(report['report_url'].replace('index.html', 'test-data.zip'))
        assert data_zip.status_code == 200
        with ZipFile(BytesIO(data_zip.content)) as archive:
            names = archive.namelist()
            assert '测试数据.json' in names
            assert any(name.endswith('-empty.txt') for name in names)
            manifest = json.loads(archive.read('测试数据.json'))
            assert manifest['fixture_count'] == 1
            assert manifest['cases'][0]['test_data'] == '=1+1\n测试账号甲\n文件：empty.txt'
        xlsx = c.get(report['report_url'].replace('index.html','cases.xlsx'))
        assert xlsx.status_code == 200
        parsed = parse_xlsx_results(xlsx.content)
        assert parsed['cases'][0]['test_data'] == '=1+1\n测试账号甲\n文件：empty.txt'
        assert parsed['cases'][0]['evidence'] == (
            '未显示提示。现场截图已关联。缺陷标题：[test]【B端】【登录】错误标题')
        draft = c.get(report['report_url'].replace('index.html','pingcode/finding-0')).json()
        assert draft['screenshots'][0]['content_base64'] == PNG
        assert draft['report_reference']['url'] == 'http://testserver' + report['report_url']
        assert draft['report_reference']['case_id'] == 'W01'
        assert '用例编号：W01' in draft['description']
        assert draft['report_reference']['url'] in draft['description']
        linked_download = c.get(draft['report_reference']['url'].replace('index.html', 'test-data.zip'))
        assert linked_download.status_code == 200
        with ZipFile(BytesIO(linked_download.content)) as archive:
            assert json.loads(archive.read('测试数据.json')) == manifest
        assert draft['screenshots'][0]['asset_id'] == aid
        assert '未显示提示' in draft['description']
        assert '【测试环境】\nmacOS Chrome桌面' in draft['description']
        assert 'macOS' not in draft['title']
        with TestClient(app) as other:
            other.get('/api/bootstrap')
            assert other.get(url).status_code in {403,404}
            # Shared report evidence has exactly the same read access as its public HTML.
            assert other.get(report['report_url'].replace('index.html','asset-'+aid)).status_code == 200
            assert other.get(report['report_url'].replace('index.html','test-data.zip')).status_code == 200
            assert other.get(report['report_url'].replace('index.html','asset-not-found')).status_code == 404


def test_report_confirmation_is_actionable_and_persisted_into_continuation(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        project = create_ui_record_project(client, json={
            'title': '删除确认', 'target_url': 'https://example.test/history', 'goal': '验证删除',
        }).json()['project']
        pid = project['id']
        token = client.post('/api/mcp/redeem', json={
            'code': client.post('/api/mcp/pair').json()['code'],
        }).json()['token']

        def call(action, **arguments):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                               json={'action': action, 'arguments': {'project_id': pid, **arguments}})

        incomplete = call('ui_cases', cases=[{
            'case_id': 'DELETE-1', 'scenario': '删除共享历史', 'steps': '打开删除确认框',
            'expected': '明确确认后删除', 'status': 'pending_action',
        }])
        assert incomplete.status_code == 200, incomplete.text
        incomplete_case = call('ui_read', execution_id=incomplete.json()['execution_id']).json()['cases'][0]
        assert incomplete_case['status'] == 'pending_action' and not incomplete_case.get('required_action')
        saved = call('ui_cases', cases=[{
            'case_id': 'DELETE-1', 'scenario': '删除共享历史', 'steps': '打开删除确认框',
            'expected': '明确确认后删除', 'status': 'pending_action',
            'action_type': 'authorization', 'action_required': '授权删除该共享历史记录',
        }]).json()
        published = call('ui_publish', execution_id=saved['execution_id'], title='待确认报告', summary='等待用户决定').json()['report']
        page = client.get(published['report_url'])
        review = json.loads(__import__('re').search(
            r'id="report-review-data">(.*?)</script>', page.text, __import__('re').S).group(1))
        assert review['cases'][0]['required_action']['prompt'] == '授权删除该共享历史记录'
        assert review['actionBase'].endswith('/ui-actions')
        endpoint = review['actionBase'] + '/DELETE-1'
        assert client.post(endpoint, json={'decision': 'completed'}).status_code == 400
        confirmed = client.post(endpoint, json={'decision': 'authorized'})
        assert confirmed.status_code == 200, confirmed.text
        continuation = confirmed.json()['project']
        assert continuation['id'] == pid
        assert continuation['action_continuation']['decision'] == 'authorized'
        repeated = client.post(endpoint, json={'decision': 'authorized'}).json()
        assert repeated['project']['id'] == continuation['id'] and repeated['reused'] is True
        continuation_owner = app.state.store.find_project_owner(continuation['id'])
        document = (app.state.store.project_dir(continuation_owner, continuation['id']) /
                    continuation['effective_document_file']).read_text()
        assert '已明确授权' in document and '不得再以“未获得用户确认”标记阻塞' in document
        assert 'DELETE-1' in document


def test_maximum_permission_does_not_reclassify_executor_authorization_pause(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        project = create_ui_record_project(client, json={
            'title':'最大权限', 'target_url':'https://example.test', 'goal':'完整测试',
            'execution_permission':'maximum',
        }).json()['project']
        token = client.post('/api/mcp/redeem', json={
            'code':client.post('/api/mcp/pair').json()['code'],
        }).json()['token']
        response = client.post('/api/mcp/call', headers={'Authorization':'Bearer '+token}, json={
            'action':'ui_cases', 'arguments':{'project_id':project['id'], 'cases':[{
                'case_id':'MAX-1', 'scenario':'启动真实任务', 'steps':'点击启动',
                'expected':'任务启动', 'status':'pending_action', 'action_type':'authorization',
                'action_required':'请再次授权',
            }]}
        })
        assert response.status_code == 200, response.text
        owner = app.state.store.find_project_owner(project['id'])
        from api_test_tool.ui_records import load
        case = load(app.state.store, owner, project['id'], response.json()['execution_id'])['cases'][0]
        assert case['status'] == 'pending_action'
        assert case['action_type'] == 'authorization' and case['action_required'] == '请再次授权'


def test_legacy_confirmation_prose_does_not_change_status_or_invent_action():
    from api_test_tool.ui_records import cases_with_actions
    original = {'case_id': 'OLD', 'scenario': '历史删除', 'status': 'blocked',
                'actual': '已打开确认删除框，需用户确认，本轮未点击。'}
    rendered = cases_with_actions([original])[0]
    assert rendered['status'] == 'blocked'
    assert not rendered.get('required_action')
    assert original['status'] == 'blocked' and 'required_action' not in original


def test_ui_asset_batch_is_atomic_and_equivalent_to_single_upload(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as c:
        c.headers['x-csrf-token'] = c.get('/api/bootstrap').json()['csrf']
        pid = create_ui_record_project(c, json={'title': '批量证据', 'target_url': 'https://example.test', 'goal': '验证'}).json()['project']['id']
        token = c.post('/api/mcp/redeem', json={'code': c.post('/api/mcp/pair').json()['code']}).json()['token']
        def call(action, **args):
            return c.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                          json={'action': action, 'arguments': {'project_id': pid, **args}})
        saved = call('ui_cases', cases=[
            {'case_id': 'B1', 'scenario': '截图', 'steps': '观察页面', 'expected': '页面正确'},
            {'case_id': 'B2', 'scenario': '夹具', 'test_data': 'fixture.txt', 'steps': '上传 fixture.txt', 'expected': '上传成功'},
        ]).json()
        execution = saved['execution_id']
        screenshot = {'case_id': 'B1', 'step': '观察页面', 'filename': 'page.png',
                      'content_type': 'image/png', 'content_base64': PNG, 'kind': 'screenshot'}
        fixture = {'case_id': 'B2', 'step': '上传 fixture.txt', 'filename': 'fixture.txt',
                   'content_type': 'text/plain', 'content_base64': base64.b64encode(b'data').decode(), 'kind': 'fixture'}
        invalid = {**fixture, 'case_id': 'missing'}
        failed = call('ui_assets', execution_id=execution, assets=[screenshot, invalid])
        assert failed.status_code == 400
        assert '第 2 个证据无效' in failed.text
        assert call('ui_read', execution_id=execution).json()['assets'] == []

        uploaded = call('ui_assets', execution_id=execution, assets=[screenshot, fixture])
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()['total'] == 2
        assert uploaded.json()['created'] == 2
        repeated = call('ui_assets', execution_id=execution, assets=[screenshot, fixture]).json()
        assert repeated['created'] == 0 and repeated['reused'] == 2
        stored = call('ui_read', execution_id=execution).json()['assets']
        assert len(stored) == 2
        assert {item['kind'] for item in stored} == {'screenshot', 'fixture'}

        assert call('ui_assets', execution_id=execution, assets=[]).status_code == 400
        assert call('ui_assets', execution_id=execution, assets=[screenshot] * 51).status_code == 400


def bootstrap_module():
    path=Path(__file__).parents[2]/'api_test_tool/static/skills/web-exploratory-testing/scripts/bootstrap.py'
    spec=importlib.util.spec_from_file_location('ui_bootstrap',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_bootstrap_compatible_version_reuses_without_install(tmp_path,monkeypatch):
    m=bootstrap_module()
    monkeypatch.setattr(m.shutil,'which',lambda _: '/existing/node')
    monkeypatch.setattr(m,'find_working',lambda *_: {'module':'/existing/playwright','node':'/existing/node','channel':'chrome'})
    download=Mock(side_effect=AssertionError('must not download'));monkeypatch.setattr(m,'download',download)
    assert m.prepare(tmp_path/'cache')['reused'] is True
    assert not (tmp_path/'cache').exists()
    download.assert_not_called()


def test_bootstrap_probe_only_never_installs(tmp_path,monkeypatch):
    m=bootstrap_module();monkeypatch.setattr(m.shutil,'which',lambda _:None)
    with pytest.raises(RuntimeError,match='尚未下载'):
        m.prepare(tmp_path/'cache',False)
    assert not (tmp_path/'cache').exists()


def test_coverage_is_incremental_advice_not_case_quota_or_publication_gate(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as c:
        c.headers['x-csrf-token'] = c.get('/api/bootstrap').json()['csrf']
        pid = create_ui_record_project(c, json={'title': '合成覆盖回归', 'target_url': 'https://example.test', 'goal': '设计'}).json()['project']['id']
        token = c.post('/api/mcp/redeem', json={'code': c.post('/api/mcp/pair').json()['code']}).json()['token']
        def call(action, **args):
            return c.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                          json={'action': action, 'arguments': {'project_id': pid, **args}})

        # The inventory exists before any cases, including a feature we cannot execute yet.
        areas = [{'coverage_id': 'upload', 'feature': '<script>上传</script>', 'entry': '资料 / 上传',
                  'considerations': '格式、大小、失败恢复及独立结果', 'case_ids': ['C0', 'later'], 'gap': ''},
                 {'coverage_id': 'isolation', 'feature': '租户隔离', 'case_ids': [], 'gap': '第二租户暂不可用'}]
        first = call('ui_cases', cases=[], coverage=areas)
        assert first.status_code == 200, first.text
        execution = first.json()['execution_id']
        check = first.json()['coverage_check']
        assert check['areas_without_cases'] == ['isolation']
        assert check['unknown_case_ids'] == ['C0', 'later']
        assert not check['review_current']

        # More than ten cases and more than one transport batch are retained. No method quotas.
        def case(n):
            return {'case_id': 'C' + str(n), 'scenario': '合成独立场景 ' + str(n),
                    'precondition': '合成测试账号', 'test_data': str(n), 'steps': '1. 输入该数据\n2. 检查提示', 'expected': '符合合成规则'}
        batch = call('ui_cases', execution_id=execution, revision=1, cases=[case(n) for n in range(200)])
        assert batch.status_code == 200, batch.text
        extra = call('ui_cases', execution_id=execution, revision=2, cases=[case(n) for n in range(200, 213)])
        assert extra.json()['total'] == 213
        assert extra.json()['coverage_check']['unknown_case_ids'] == ['later']
        page = call('ui_read', execution_id=execution, offset=200).json()
        assert len(page['cases']) == 13
        assert len(page['coverage']) == 2  # Inventory does not disappear on pagination.

        review = call('ui_cases', execution_id=execution, revision=3, cases=[],
                      coverage=[{**areas[0], 'case_ids': ['C' + str(n) for n in range(213)]}],
                      review_notes='已逐项核对上传规则；隔离设计仍缺独立账号与具体步骤，保留缺口。')
        assert review.status_code == 200, review.text
        assert review.json()['coverage_check']['review_current']
        assert review.json()['coverage_check']['cases_without_area'] == []
        # A later edit makes the earlier review stale, but does not erase it or reject useful cases.
        updated = call('ui_cases', execution_id=execution, revision=4, cases=[{**case(0), 'status': 'blocked', 'actual': '工具不可用'}])
        assert not updated.json()['coverage_check']['review_current']
        stored = call('ui_read', execution_id=execution).json()
        assert stored['review_notes'].startswith('已逐项')
        assert stored['coverage'][1]['gap'] == '第二租户暂不可用'
        assert call('ui_cases', execution_id=execution, revision=4, cases=[], review_notes='旧版本').status_code == 400

        # Gaps and stale review remain visible, never a new workflow approval or hard publishing gate.
        published = call('ui_publish', execution_id=execution, title='合成未执行设计', summary='仅设计，未宣称完整执行。')
        assert published.status_code == 200, published.text
        assert not published.json()['coverage_check']['review_current']
        url = published.json()['report']['report_url']
        page = c.get(url.replace('index.html', 'cases.html')).text
        assert '&lt;script&gt;上传&lt;/script&gt;' in page and '<script>上传</script>' not in page
        assert '第二租户暂不可用' in page and '需重新回查' in page
        assert 'C212' in page and '覆盖清单与回查' in page
        assert '"hasCoverage": true' in c.get(url).text
        assert call('ui_cases', execution_id=execution, revision=5, cases=[], coverage=areas).status_code == 200


def test_coverage_shape_validation_and_missing_design_reminders(tmp_path):
    from api_test_tool.ui_records import merge_coverage, coverage_check
    with pytest.raises(ValueError):
        merge_coverage([], [{'coverage_id': 'a', 'feature': '上传', 'case_ids': 'C1'}])
    with pytest.raises(ValueError):
        merge_coverage([], [{'coverage_id': 'a', 'feature': '上传'}, {'coverage_id': 'a', 'feature': '重复'}])
    legacy = {'revision': 1, 'cases': [{'case_id': 'old', 'scenario': '原用例', 'status': 'passed', 'actual': '历史结果'}]}
    check = coverage_check(legacy)
    assert check['missing_inventory'] and not check['review_current']
    assert check['incomplete_designs'][0]['missing'] == ['precondition', 'test_data', 'steps', 'expected']
    assert 'score' not in check and 'coverage_percent' not in check


def test_design_baseline_precedes_results_and_can_expand_without_user_gate(tmp_path):
    """Exercise design baseline -> result -> discovery -> refinement."""
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as c:
        c.headers['x-csrf-token'] = c.get('/api/bootstrap').json()['csrf']
        pid = create_ui_record_project(c, json={'title': '探索式执行回归', 'target_url': 'https://example.test',
                                          'goal': '按实际界面测试引导'}).json()['project']['id']
        token = c.post('/api/mcp/redeem', json={'code': c.post('/api/mcp/pair').json()['code']}).json()['token']

        def call(action, **args):
            response = c.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                              json={'action': action, 'arguments': {'project_id': pid, **args}})
            assert response.status_code == 200, response.text
            return response.json()

        entry = {'case_id': 'ENTRY', 'scenario': '手动进入教学模式', 'status': 'not_run', 'executor': 'AI',
                 'precondition': '已登录测试账号', 'test_data': '无', 'steps': '1.打开帮助入口', 'expected': '显示教学欢迎步骤'}
        selection = {'case_id': 'SELECTION', 'scenario': '选择对象后才能继续', 'status': 'not_run', 'executor': 'AI',
                     'precondition': '已进入对象选择页', 'test_data': '空选择', 'steps': '1.不选择对象\n2.点击继续',
                     'expected': '根据页面提示，不允许继续'}
        partial = {'case_id': 'KEYBOARD', 'scenario': '键盘完整路径', 'status': 'not_run', 'executor': '人工',
                   'precondition': '使用真实键盘及辅助技术', 'test_data': 'Tab、Shift+Tab、Enter、Escape',
                   'steps': '1.仅使用键盘完成教学流程', 'expected': '所有操作可达且焦点顺序合理'}
        first = call('ui_cases', cases=[entry, selection, partial])
        eid = first['execution_id']
        assert first['total'] == 3
        assert first['coverage_check']['missing_inventory']

        # Execute the AI subset, while the human case stays concrete and unexecuted.
        call('ui_cases', execution_id=eid, revision=1, cases=[
            {**entry, 'status': 'passed', 'actual': '教学模式已显示，当前为欢迎步骤'},
            {**selection, 'status': 'failed', 'actual': '未选择也进入下一页'},
            {'case_id': 'RECOVERY', 'scenario': '刷新后的选择状态', 'status': 'blocked',
             'executor': 'AI', 'actual': '当前浏览器连接中断，未验证'},
            {'case_id': 'LATER', 'scenario': '新增的独立返回路径', 'executor': 'AI'}],
             coverage=[{'coverage_id': 'selection', 'feature': '对象选择规则',
                        'case_ids': ['SELECTION', 'RECOVERY'], 'gap': '恢复未验证'}])
        record = call('ui_read', execution_id=eid)
        assert record['total'] == 5
        assert record['cases'][0]['status'] == 'passed'
        assert not record['coverage_check']['review_current']
        assert record['cases'][1]['actual'] == '未选择也进入下一页'
        assert record['cases'][2]['executor'] == '人工'

        # Gaps do not block an honest interim report and are not defect drafts.
        result = call('ui_publish', execution_id=eid, title='阶段性结果', summary='一项规则差异；键盘与恢复尚未完成。')
        assert result['coverage_check']['failed_without_screenshot'] == ['SELECTION']
        report = call('report')['analysis']
        assert report['imported_results']['counts'] == {'passed': 1, 'failed': 1,
                                                       'blocked': 1, 'not_run': 2, 'total': 5}
        assert len(report['findings']) == 1
        assert report['findings'][0]['case_id'] == 'SELECTION'
        assert '未选择也进入下一页' in str(report['findings'][0])
        assert call('ui_publish', execution_id=eid, title='重复', summary='重复')['report']['id'] == result['report']['id']


def test_partial_execution_keeps_unexecuted_design_in_report_and_export(tmp_path):
    """Executing a subset must not reduce the designed scope or invent results."""
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as c:
        c.headers['x-csrf-token'] = c.get('/api/bootstrap').json()['csrf']
        pid = create_ui_record_project(c, json={'title': '设计与执行分离', 'target_url': 'https://example.test',
                                          'goal': '测试教学流程'}).json()['project']['id']
        token = c.post('/api/mcp/redeem', json={'code': c.post('/api/mcp/pair').json()['code']}).json()['token']

        def call(action, **args):
            r = c.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                       json={'action': action, 'arguments': {'project_id': pid, **args}})
            assert r.status_code == 200, r.text
            return r.json()

        designs = [dict(case_id=cid, scenario=name, executor=executor, precondition='教学数据，已进入对象选择步骤',
                        test_data=data, steps=steps, expected=expected, status='not_run')
                   for cid, name, executor, data, steps, expected in [
                       ('SELECT', '选择可发送对象', 'AI', '合成对象A', '1.选择A\n2.检查计数', '已选数为1'),
                       ('EMPTY', '取消最后一项选择', 'AI', '只选中合成对象A', '1.取消A\n2.检查发送按钮', '已选数为0，发送禁用'),
                       ('ISOLATION', '另一租户不读取本租户教学状态', '人工', '隔离的合成租户A和B',
                        '1.在A选择对象\n2.用独立会话登录B\n3.查看教学状态', 'B不继承A的选择')]]
        first = call('ui_cases', cases=designs)
        eid = first['execution_id']
        call('ui_cases', execution_id=eid, revision=1,
             cases=[{**designs[0], 'status': 'passed', 'actual': '选择A后显示已选1'}])
        published = call('ui_publish', execution_id=eid, title='阶段性结果', summary='设计3项，仅验证选择；其余未执行。')
        report = call('report')['analysis']
        assert report['imported_results']['counts'] == {'passed': 1, 'not_run': 2, 'total': 3}
        assert report['findings'] == []
        assert report['ui_snapshot']['cases'][1]['steps'] == designs[1]['steps']
        assert report['ui_snapshot']['cases'][2]['actual'] == ''
        url = published['report']['report_url']
        exported = parse_xlsx_results(c.get(url.replace('index.html', 'cases.xlsx')).content)
        assert len(exported['cases']) == 3
        by_id = {row['case_id']: row for row in exported['cases']}
        assert by_id['ISOLATION']['steps'] == designs[2]['steps']
        assert by_id['ISOLATION']['evidence'] == ''
        assert by_id['ISOLATION']['executor'] == '人工'


def test_packaged_skill_has_all_references(tmp_path):
    import re
    root = Path(__file__).parents[2] / 'api_test_tool/static/skills/web-exploratory-testing'
    for source in [root / 'SKILL.md', *root.glob('references/*.md')]:
        for link in re.findall(r'\]\(([^)]+)\)', source.read_text()):
            if not link.startswith(('https:', 'http:', '#')):
                assert (source.parent / link.split('#', 1)[0]).is_file(), (source, link)


def test_ui_skill_optimizes_execution_without_reducing_results():
    root = Path(__file__).parents[2] / 'api_test_tool/static/skills/web-exploratory-testing'
    skill = (root / 'SKILL.md').read_text() + (root / 'references/worker.md').read_text() + (root / 'references/coverage-design.md').read_text()
    optimization = (root / 'references/execution-optimization.md').read_text()
    platform = (root / 'references/platform.md').read_text()
    assert 'execution-optimization.md' in skill
    for promise in ['一次预检', '依赖图', '等待真实完成条件', '安全并发', 'blocked', '失败复现']:
        assert promise in optimization
    assert '首批用例不是最终范围' in skill
    assert '不为每次点击单独保存' in platform
    assert '不再因为生产环境或出现确认弹窗重复索要同一授权' in skill
    assert 'target.getScreenshot({emit:false})' in platform
    assert 'node:fs/promises.writeFile' in platform
    assert '不需要用户保存截图' in platform


def test_fixture_uses_explicit_case_id_without_matching_filename_in_prose(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as c:
        c.headers['x-csrf-token'] = c.get('/api/bootstrap').json()['csrf']
        pid = create_ui_record_project(c, json={'title': '夹具归属', 'target_url': 'https://example.test',
                                           'goal': '验证测试数据归属'}).json()['project']['id']
        token = c.post('/api/mcp/redeem', json={'code': c.post('/api/mcp/pair').json()['code']}).json()['token']

        def call(action, **args):
            return c.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                          json={'action': action, 'arguments': {'project_id': pid, **args}})

        first = call('ui_cases', cases=[
            {'case_id': 'A', 'scenario': '执行者显式关联资料', 'test_data': '应使用 a.txt'},
            {'case_id': 'B', 'scenario': '共享数据一', 'steps': '上传 shared.txt'},
            {'case_id': 'C', 'scenario': '共享数据二', 'rule_basis': '以 SHARED.TXT 作为共同输入'},
        ])
        assert first.status_code == 200, first.text
        execution = first.json()['execution_id']
        common = dict(execution_id=execution, step='上传文件', content_type='text/plain',
                      content_base64=base64.b64encode(b'shared fixture').decode(), kind='fixture')
        unmentioned = call('ui_asset', case_id='A', filename='shared.txt', **common)
        assert unmentioned.status_code == 200, unmentioned.text
        one = call('ui_asset', case_id='B', filename='shared.txt', **common)
        two = call('ui_asset', case_id='C', filename='shared.txt', **common)
        assert one.status_code == two.status_code == 200
        assert one.json()['sha256'] == two.json()['sha256']
        # Editing narrative fields does not change the explicit asset ownership.
        update = call('ui_cases', execution_id=execution, revision=1,
                      cases=[{'case_id': 'B', 'scenario': '共享数据一', 'steps': '上传文件'}])
        assert update.status_code == 200, update.text
        record = call('ui_read', execution_id=execution).json()
        assert next(case for case in record['cases'] if case['case_id'] == 'B')['steps'] == '上传文件'
        assert {asset['case_id'] for asset in record['assets']} == {'A', 'B', 'C'}


def test_public_report_app_exposes_only_read_only_report_surface(tmp_path):
    data = tmp_path / 'data'
    internal = create_app(data, start_fixture=False, testing=True)
    with TestClient(internal) as c:
        c.headers['x-csrf-token'] = c.get('/api/bootstrap').json()['csrf']
        pid = create_ui_record_project(c, json={'title': '公网只读报告', 'target_url': 'https://example.test',
                                           'goal': '验证隔离端口'}).json()['project']['id']
        token = c.post('/api/mcp/redeem', json={'code': c.post('/api/mcp/pair').json()['code']}).json()['token']

        def call(action, **args):
            return c.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                          json={'action': action, 'arguments': {'project_id': pid, **args}})

        saved = call('ui_cases', cases=[{'case_id': 'PUBLIC-1', 'scenario': '只读报告',
                                         'precondition': '已登录', 'test_data': '公开合成数据',
                                         'steps': '1.检查页面', 'expected': '显示结果',
                                         'actual': '未显示', 'status': 'failed'}]).json()
        asset = call('ui_asset', execution_id=saved['execution_id'], case_id='PUBLIC-1', step='1.检查页面',
                     filename='public-error.png', content_type='image/png', content_base64=PNG,
                     captured_at='2026-09-21T12:00:00Z').json()
        report_url = call('ui_publish', execution_id=saved['execution_id'], title='公网只读报告',
                          summary='合成验证报告').json()['report']['report_url']

    public_app = create_app(data, start_fixture=False, testing=True, auth_enabled=True, report_only=True)
    with TestClient(public_app) as public:
        report = public.get(report_url, headers={'host': '203.0.113.10:18090'})
        assert report.status_code == 200
        assert 'name="api-test-public-report" content="read-only"' in report.text
        assert '/static/report-review.js' in report.text
        assert '/static/account-bar.js' not in report.text
        assert '/static/pingcode.js' not in report.text
        assert public.get(report_url.replace('index.html', 'cases.html')).status_code == 200
        assert public.get(report_url.replace('index.html', 'cases.xlsx')).status_code == 200
        screenshot = public.get(report_url.replace('index.html', 'asset-' + asset['id']))
        assert screenshot.status_code == 200 and screenshot.content.startswith(b'\x89PNG')
        assert public.get('/static/report-theme.css').status_code == 200
        assert public.get('/static/report-image-preview.css').status_code == 200
        assert public.get('/static/report-image-preview.js').status_code == 200
        for path in ('/', '/login', '/api/bootstrap', f'/api/projects/{pid}', '/integrations/pingcode',
                     '/static/index.html', '/static/app.js', '/static/api-test-client.py'):
            denied = public.get(path)
            assert denied.status_code == 404, (path, denied.text)
        assert public.post(report_url).status_code == 404


def test_large_fixture_can_be_supplemented_and_downloaded_without_rewriting_history(tmp_path):
    import hashlib
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        pid = create_ui_record_project(client, json={
            'title': '大文件归档', 'target_url': 'https://example.test', 'goal': '保存边界文件',
        }).json()['project']['id']
        token = client.post('/api/mcp/redeem', json={
            'code': client.post('/api/mcp/pair').json()['code'],
        }).json()['token']

        def call(action, **args):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                               json={'action': action, 'arguments': {'project_id': pid, **args}})

        saved = call('ui_cases', cases=[{
            'case_id': 'KB16', 'scenario': '32 MiB 加一字节', 'test_data': 'boundary.txt',
            'steps': '上传 boundary.txt', 'expected': '拒绝超过大小上限的文件', 'status': 'not_run',
        }]).json()
        eid = saved['execution_id']
        # Empty files remain valid fixtures before publication.
        empty = call('ui_asset', execution_id=eid, case_id='KB16', kind='fixture',
                     filename='boundary.txt', step='空文件对照', content_base64='', content_type='text/plain')
        assert empty.status_code == 200, empty.text
        # The missing large input belongs to a separate case, not a replacement of frozen evidence.
        updated = call('ui_cases', execution_id=eid, revision=saved['revision'], cases=[{
            'case_id': 'KB15', 'scenario': '边界文件归档', 'test_data': 'boundary.txt',
            'steps': '下载 boundary.txt', 'expected': '字节数和摘要一致', 'status': 'not_run',
        }])
        assert updated.status_code == 200, updated.text
        published = call('ui_publish', execution_id=eid, title='大小边界', summary='尚未执行').json()['report']
        rid = published['id']
        base = f'/api/projects/{pid}/reports/{rid}'
        owner = app.state.store.find_project_owner(pid)
        root = app.state.store.project_dir(owner, pid)
        # An inactive historical execution retains the fixture-only supplement path.
        app.state.store.update_project(owner, pid, {'ui_execution_id': ''})
        frozen_paths = [root / 'analyses' / rid / 'report.json', root / 'ui-executions' / eid / 'cases.json']
        frozen = {path: path.read_bytes() for path in frozen_paths}
        progress = app.state.store.get_project(owner, pid)['mcp_progress']
        content = b'x' * (32 * 1024 * 1024 + 1)
        asset = {'case_id': 'KB15', 'kind': 'fixture', 'filename': 'boundary.txt',
                 'step': '补存原始测试输入', 'content_type': 'text/plain',
                 'content_base64': base64.b64encode(content).decode()}
        invalid = call('ui_assets', execution_id=eid, assets=[asset, {**asset, 'case_id': 'missing'}])
        assert invalid.status_code == 400
        assert not (root / 'analyses' / rid / 'fixture-supplements.json').exists()
        uploaded = call('ui_asset', execution_id=eid, **asset)
        assert uploaded.status_code == 200, uploaded.text
        aid = uploaded.json()['id']
        assert uploaded.json()['size'] == len(content)
        repeated = call('ui_assets', execution_id=eid, assets=[asset]).json()
        assert repeated['created'] == 0 and repeated['reused'] == 1
        assert call('ui_asset', execution_id=eid, **{**asset, 'content_base64': 'eQ=='}).status_code == 400
        assert call('ui_asset', execution_id=eid, **{**asset, 'kind': 'screenshot',
                    'filename': 'page.png', 'content_base64': PNG}).status_code == 400
        assert call('ui_asset', execution_id=eid, **{**asset, 'filename': '../boundary.txt',
                    'content_base64': 'eA=='}).status_code == 400
        assert all(path.read_bytes() == before for path, before in frozen.items())
        assert app.state.store.get_project(owner, pid)['mcp_progress'] == progress
        supplements = app.state.store._read(root / 'analyses' / rid / 'fixture-supplements.json')
        assert len(supplements['history']) == 1
        assert supplements['history'][0]['asset_ids'] == [aid]
        assert supplements['assets'][0]['uploaded_at']
        assert len(call('ui_read', execution_id=eid).json()['assets']) == 2
        effective = client.get(base + '/report.json').json()
        assert effective['imported_results']['counts']['not_run'] == 2
        assert effective['fixture_supplements'][0]['id'] == aid
        assert 'boundary.txt' in client.get(base + '/index.html').text
        assert 'asset-' + aid in client.get(base + '/cases.html').text
        downloaded = client.get(base + '/asset-' + aid)
        assert downloaded.content == content
        assert 'attachment;' in downloaded.headers['content-disposition']
        with ZipFile(BytesIO(client.get(base + '/test-data.zip').content)) as archive:
            manifest = json.loads(archive.read('测试数据.json'))
            assert manifest['fixture_count'] == 2
            name = next(name for name in archive.namelist() if '/KB15/' in name)
            assert hashlib.sha256(archive.read(name)).hexdigest() == uploaded.json()['sha256']
        # Wording edits after supplementation must not copy or lose the independent appendix.
        correction = client.post(base + '/case-corrections/KB15', json={
            'revision': 0, 'fields': {'test_data': 'boundary.txt：32 MiB 加一字节'},
        })
        assert correction.status_code == 200, correction.text
        correction_file = root / 'analyses' / rid / 'case-corrections.json'
        assert 'fixture_supplements' not in json.loads(correction_file.read_text())
        assert len(client.get(base + '/report.json').json()['ui_snapshot']['assets']) == 2
        with TestClient(app) as other:
            other.headers['x-csrf-token'] = other.get('/api/bootstrap').json()['csrf']
            other_token = other.post('/api/mcp/redeem', json={
                'code': other.post('/api/mcp/pair').json()['code'],
            }).json()['token']
            denied = other.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + other_token},
                                json={'action': 'ui_asset', 'arguments': {'project_id': pid,
                                      'execution_id': eid, **asset, 'content_base64': 'eA=='}})
            assert denied.status_code in {403, 404}


def test_asset_limit_checks_encoded_and_decoded_size_per_kind(monkeypatch):
    from api_test_tool import ui_records
    record = {'cases': [{'case_id': 'C1', 'test_data': 'boundary.txt'}], 'assets': []}
    monkeypatch.setitem(ui_records.ASSET_BYTE_LIMITS, 'fixture', 8)
    def prepare(content):
        return ui_records._prepare_asset(record, 'C1', '上传', 'boundary.txt', 'text/plain',
                                         base64.b64encode(content).decode(), kind='fixture')
    assert prepare(b'x' * 8)[0]['size'] == 8
    # 8 and 9 bytes both encode to 12 characters; decoded size still needs validation.
    with pytest.raises(ValueError, match='测试文件上限'):
        prepare(b'x' * 9)
    with pytest.raises(ValueError, match='测试文件上限'):
        prepare(b'x' * 10)
    with pytest.raises(ValueError, match='Base64'):
        ui_records._prepare_asset(record, 'C1', '上传', 'boundary.txt', 'text/plain', '??', kind='fixture')
