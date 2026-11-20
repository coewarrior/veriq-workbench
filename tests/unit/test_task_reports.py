import json
from copy import deepcopy

from fastapi.testclient import TestClient

from api_test_tool.web import create_app
from api_test_tool.task_reports import render_task_report, save_task_report


def test_full_design_result_appendix_is_not_rendered():
    report = {
        'title': '接口报告', 'summary': '保留的分析结论',
        'sections': [
            {'title': '范围与结论', 'content': '保留这段分析'},
            {'title': '完整设计与逐条结果（1）', 'content': '不应出现在报告页面'},
        ],
        'findings': [], 'runs': [], 'requests_sent': 0,
        'goal': '', 'created_at': '2026-09-15T00:00:00+00:00',
        'document': {'filename': 'api.md', 'sha256': 'a' * 64},
    }

    page = render_task_report(report)

    assert '保留这段分析' in page
    assert '完整设计与逐条结果' not in page
    assert '不应出现在报告页面' not in page


def test_unparsed_document_and_free_report_need_no_cases_and_support_read_only_sharing(tmp_path):
    app=create_app(tmp_path,start_fixture=False,testing=True)
    with TestClient(app) as owner, TestClient(app) as other:
        owner.headers['x-csrf-token']=owner.get('/api/bootstrap').json()['csrf']
        code=owner.post('/api/mcp/pair').json()['code']
        token=owner.post('/api/mcp/redeem',json={'code':code}).json()['token']
        def call(action,**arguments):
            return owner.post('/api/mcp/call',headers={'Authorization':'Bearer '+token},json={'action':action,'arguments':arguments})
        # An existing MCP client without new tool definitions can still complete the review.
        imported=call('import',title='不完整文档',filename='broken.yaml',content='openapi: [invalid yaml',task={'goal':'检查文档，不发送请求'}).json()
        pid=imported['project']['id']
        assert not imported['contract']['operations']
        context=call('context',project_id=pid).json()
        assert 'submit_test_cases' in json.dumps(context['report_submission'])
        entry={'record_type':'task_report','title':'<script>alert(1)</script>','summary':'存在格式错误，尚未执行接口。',
            'sections':[{'title':'文档检查','content':'不需要生成固定格式用例'}],
            'findings':[{'title':'语法未闭合','evidence':'openapi: [invalid yaml','detail':'<img src=x onerror=alert(1)>'}]}
        saved=call('submit',project_id=pid,revision=context['revision'],cases=[entry])
        assert saved.status_code==200,saved.text
        report=saved.json()['report']
        assert report['kind']=='analysis' and report['requests_sent']==0
        response=owner.get(report['report_url'])
        assert response.status_code==200
        assert '<script>alert(1)</script>' not in response.text and '<img' not in response.text
        assert '复制问题描述' in response.text
        assert '&lt;script&gt;' in response.text
        assert '<a href="/api-testing">← 返回测试台</a>' in response.text
        other.get('/api/bootstrap')
        shared=other.get(report['report_url'])
        assert shared.status_code==200
        assert 'name="api-test-public-report" content="read-only"' in shared.text
        assert owner.get(report['report_url'].replace('index.html','bundle.json')).status_code==404
        details=owner.get('/api/projects/'+pid).json()
        assert details['bundle'] is None and details['project']['status']=='reported'
        assert not details['project'].get('runs')
        assert call('task_report',project_id=pid,title='伪造执行',summary='bad',run_ids=['../run']).status_code==400
        assert call('document',project_id=pid,offset=-1).status_code==400
        assert call('document',project_id=pid,limit=60001).status_code==400
        assert call('report',project_id=pid).json()['report']['id']==report['id']


def test_execution_summary_reuses_evidence_layout_and_existing_report_url(tmp_path):
    from uuid import uuid4
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client, TestClient(app) as other:
        client.get('/api/bootstrap')
        store = app.state.store
        owner = store.session(client.cookies['api_test_session'])[0]['id']
        project = store.create_project(owner, '测试', 'api.md', '# 接口')
        pid = project['id']
        entries = []
        for date, status in [('2026-09-10', 'PASS'), ('2026-09-11', 'FAIL')]:
            rid = str(uuid4())
            result = {'run_id': rid, 'title': '原执行标题', 'started_at': date,
                      'environment': {'name': '独立测试', 'base_url': 'http://localhost:1234'},
                      'requests_sent': 1, 'summary': {'total': 1, status: 1},
                      'cases': [{'id': 'CASE-1', 'title': '名称校验', 'operation_id': 'read', 'status': status,
                                 'steps': [{'id': 'get', 'status': status, 'request': {'method': 'GET', 'url': 'http://localhost:1234/items'},
                                            'response': {'status': 200, 'body': {'name': '<script>bad</script>'}},
                                            'assertions': [{'kind': 'json_equal', 'expected': '正确名称', 'actual': '错误名称', 'passed': status == 'PASS'}]}]}]}
            bundle = {'contract': {'operations': {'read': {'method': 'GET', 'path': '/items'}}}, 'cases': [], 'rules': []}
            root = store.project_dir(owner, pid) / 'runs' / rid
            store._mkdir(root)
            store._write(root / 'result.json', result)
            store._write(root / 'bundle.json', bundle)
            entries.append(dict(id=rid, created_at=date, environment=result['environment'], requests_sent=1,
                                summary=result['summary'], report_url=f'/api/projects/{pid}/reports/{rid}/index.html'))
        project = store.update_project(owner, pid, {'runs': entries})
        if project is None:
            project = store.get_project(owner, pid)
        report = save_task_report(store, owner, project, {'title': '正式测试报告', 'summary': '发现名称错误',
            'sections': [{'title': '分析范围', 'content': '<script>unsafe</script>'},
                         {'title': '完整设计与逐条结果（1）', 'content': '重复的完整设计附录'}],
            'findings': [{'title': '文档还需完善', 'detail': '字段含义未说明'}],
            'run_ids': [entries[1]['id'], entries[0]['id']]})['report']
        root = store.project_dir(owner, pid) / 'analyses' / report['id']
        frozen = (root / 'report.json').read_bytes()
        assert '接口覆盖' in (root / 'index.html').read_text()
        store._write_text(root / 'index.html', 'OLD_PROSE_LAYOUT')
        page = client.get(report['report_url'])
        assert page.status_code == 200
        text = page.text
        assert 'OLD_PROSE_LAYOUT' not in text
        assert '<h1>正式测试报告</h1>' in text
        assert '多轮执行合并结果' in text
        assert '完整设计与逐条结果' not in text
        assert '重复的完整设计附录' not in text
        assert '<strong>1</strong><span>去重用例</span>' in text
        assert text.count('← 返回测试台') == 1
        assert '<nav class="report-nav"><a class="report-back" href="/api-testing">← 返回测试台</a><a href="#codex-analysis">查看分析结论 ↓</a></nav>' in text
        assert text.index('class="overview"') < text.index('<h2>接口覆盖</h2>') < text.index('id="cases"') < text.index('id="codex-analysis"')
        assert '正确名称' in text and '错误名称' in text
        assert '<script>bad</script>' not in text and '&lt;script&gt;bad' in text
        assert '<script>unsafe</script>' not in text
        assert f'data-pingcode-report="{entries[1]["id"]}"' in text
        assert 'id="defect-0"' in text and 'id="finding-0"' in text
        for name in ['bundle.json', 'result.json']:
            url = f'/api/projects/{pid}/reports/{entries[1]["id"]}/{name}'
            assert f'href="{url}"' in text and client.get(url).status_code == 200
        assert client.get(f'/api/projects/{pid}/reports/{entries[1]["id"]}/pingcode/defect-0').status_code == 200
        assert client.get(report['report_url'].replace('index.html', 'pingcode/finding-0')).status_code == 200
        assert (root / 'report.json').read_bytes() == frozen
        assert '完整设计与逐条结果（1）' not in (root / 'report.json').read_text()
        assert '重复的完整设计附录' not in (root / 'report.json').read_text()
        assert (root / 'index.html').read_text() == 'OLD_PROSE_LAYOUT'
        other.get('/api/bootstrap')
        shared = other.get(report['report_url'])
        assert shared.status_code == 200
        assert 'name="api-test-public-report" content="read-only"' in shared.text


def test_existing_analysis_only_report_is_rerendered_without_hidden_appendix(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.get('/api/bootstrap')
        store = app.state.store
        owner = store.session(client.cookies['api_test_session'])[0]['id']
        project = store.create_project(owner, '测试', 'api.md', '# 接口')
        report = save_task_report(store, owner, project, {
            'title': '文档分析', 'summary': '结论',
            'sections': [{'title': '完整设计与逐条结果（1）', 'content': '历史附录'}],
            'findings': [], 'run_ids': [],
        })['report']
        root = store.project_dir(owner, project['id']) / 'analyses' / report['id']
        store._write_text(root / 'index.html', 'OLD_ANALYSIS_LAYOUT')

        page = client.get(report['report_url'])

        assert page.status_code == 200
        assert 'OLD_ANALYSIS_LAYOUT' not in page.text
        assert '完整设计与逐条结果' not in page.text
        assert '历史附录' not in page.text


def test_multi_run_report_preserves_other_batches_and_original_evidence(tmp_path):
    from api_test_tool.task_reports import _merge_run_evidence
    from api_test_tool.reporting import render_report
    from api_test_tool.web_storage import Store
    store = Store(tmp_path)
    owner = store.session(None)[0]['id']
    project = store.create_project(owner, '测试', 'api.md', '# 接口')
    runs = []
    def save(rid, day, states, cleanup='PASS', base='http://localhost:1234'):
        cases = [{'id': cid, 'operation_id': 'read', 'title': cid, 'status': status, 'rule_ids': ['rule'],
                  'steps': [{'id': 'get', 'status': status, 'request': {'method': 'GET', 'url': base},
                             'response': {'status': 200, 'body': {'rule_id': 'business-field-untouched'}},
                             'assertions': [{'kind': 'status', 'expected': 204, 'actual': 200, 'passed': status == 'PASS'}]}]}
                 for cid, status in states]
        result = {'run_id': rid, 'environment': {'name': '测试', 'base_url': base}, 'started_at': day,
                  'requests_sent': len(cases), 'cases': cases, 'cleanup': {'status': cleanup}}
        bundle = {'cases': [{'id': cid, 'state': 'READY'} for cid, _ in states],
                  'contract': {'operations': {'read': {'method': 'GET', 'path': '/items'}},
                               'sources': {'source': {'excerpt': f'原文-{rid}'}}},
                  'rules': [{'id': 'rule', 'description': f'规则-{rid}', 'source_ids': ['source']}]}
        root = store.project_dir(owner, project['id']) / 'runs' / rid
        store._mkdir(root)
        store._write(root / 'result.json', result)
        store._write(root / 'bundle.json', bundle)
        runs.append({'id': rid, 'created_at': day})
        return result, bundle
    first = save('old', '2026-09-10', [('A', 'FAIL'), ('B', 'FAIL')], 'FAIL')
    second = save('new', '2026-09-11', [('A', 'PASS'), ('C', 'FAIL')])
    original = deepcopy((first, second))
    merged, error = _merge_run_evidence(store, owner, project, list(reversed(runs)))
    assert error is None
    result, bundle, origins = merged
    assert result['summary'] == {'PASS': 1, 'FAIL': 2, 'total': 3, 'complete': True}
    assert result['requests_sent'] == 4
    assert len(bundle['rules']) == 2  # B uses old, A/C use one shared new snapshot
    assert result['cleanup']['status'] == 'FAIL'  # historical cleanup failure survives a later successful run
    assert [(c['id'], c['status']) for c in result['cases']] == [('A', 'PASS'), ('B', 'FAIL'), ('C', 'FAIL')]
    text = render_report(result, bundle, case_sources=origins)
    cards = text.split('<article class="case"')[1:]
    assert '规则-old' in cards[1] and '原文-old' in cards[1] and '规则-new' not in cards[1]
    assert '规则-new' in cards[2] and '原文-new' in cards[2] and '规则-old' not in cards[2]
    assert 'business-field-untouched' in cards[1] and 'business-field-untouched' in cards[2]
    assert 'id="defect-2"' in cards[2]
    assert 'data-pingcode-report="new" data-pingcode-draft="defect-1"' in cards[2]
    assert '/reports/old/result.json' in cards[1] and '/reports/new/result.json' in cards[2]
    assert (first, second) == original
    save('other-target', '2026-09-12', [('A', 'PASS')], base='http://localhost:4321')
    merged, error = _merge_run_evidence(store, owner, project, runs)
    assert merged is None and '不同环境' in error
    (store.project_dir(owner, project['id']) / 'runs' / 'old' / 'result.json').unlink()
    merged, error = _merge_run_evidence(store, owner, project, runs)
    assert merged is None and '证据文件不可用' in error
