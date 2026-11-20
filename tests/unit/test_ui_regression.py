import base64
from fastapi.testclient import TestClient
from api_test_tool.web import create_app
from api_test_tool import ui_records
from api_test_tool.pingcode import PingCode
from test_ui_testing import completed_results_xlsx


def test_regression_preserves_baseline_and_reuses_cases(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        imported = client.post('/api/ui-tests/import-results', json={
            'filename':'baseline.xlsx','content_base64':base64.b64encode(completed_results_xlsx()).decode(),
            'environment':'test','client':'B端'}).json()
        source = imported['project']
        report_url = imported['report']['report_url']
        before = client.get(report_url).text
        lifecycle_route = (f'/api/projects/{source["id"]}/reports/{imported["report"]["id"]}'
                           '/pingcode/finding-0/lifecycle')
        decision = client.patch(lifecycle_route, json={
            'status': 'rejected', 'reason': '产品规则如此，后续只复核规则未变化。'
        })
        assert decision.status_code == 200, decision.text
        project_count = len(client.get('/api/bootstrap?test_kind=ui').json()['projects'])
        endpoint = '/api/ui-tests/'+source['id']+'/regressions'
        assert client.post(endpoint, json={}).status_code == 400
        response = client.post(endpoint, json={'target_url':'https://example.test/ui','goal':'验证修复并回归原用例',
                                               'execution_permission':'maximum'})
        assert response.status_code == 200, response.text
        new = response.json()['project']
        assert response.json()['regression_round'] is True
        assert new['id'] != source['id']
        assert new['execution_round']['parent_project_id'] == source['id']
        assert not new.get('analysis_reports')
        assert client.get('/api/projects/' + source['id']).json()['project']['last_analysis']['id'] == imported['report']['id']
        assert new['regression_round']['report_id'] == imported['report']['id']
        assert new['ui_execution_id'] == ''
        assert new['ui_execution_permission']['key'] == 'maximum'
        assert len(client.get('/api/bootstrap?test_kind=ui').json()['projects']) == project_count + 1
        document = client.get(f"/api/projects/{new['id']}/artifacts/document").text
        assert 'W01' in document and 'W02' in document and '用户已注册' in document
        assert '输入账号 test01' in document and '进入首页' in document
        assert '所有用例本轮初始为未执行' in document
        assert '执行权限范围：最大权限（maximum）' in document
        assert 'defect_decisions' in document and '产品规则如此' in document and 'rejected' in document
        assert 'defect_lineage' in document and 'source_draft_id' in document and 'W02' in document
        assert client.get(report_url).text == before
        with TestClient(app) as other:
            other.headers['x-csrf-token'] = other.get('/api/bootstrap').json()['csrf']
            assert other.post(endpoint,json={'target_url':'https://example.test/ui'}).status_code in {403,404}


def test_regression_reuses_submitted_defect_and_records_outcome(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        imported = client.post('/api/ui-tests/import-results', json={
            'filename': 'baseline.xlsx', 'content_base64': base64.b64encode(completed_results_xlsx()).decode(),
            'environment': 'test', 'client': 'B端'}).json()
        source, report = imported['project'], imported['report']
        store = app.state.store
        owner = next(path.name for path in (tmp_path / 'sessions').iterdir())
        service = PingCode(store)
        _, _, old_path = service.source(owner, source['id'], report['id'], 'finding-0')
        store._write(old_path, {
            'status': 'submitted', 'triage_status': 'submitted', 'created_at': '2026-01-01T00:00:00Z',
            'updated_at': '2026-01-01T00:00:00Z', 'source': {
                'project_id': source['id'], 'run_id': report['id'], 'draft_id': 'finding-0'},
            'target': {'base_url': 'https://example.pingcode.com', 'api_version': 'pjm', 'project_id': 'p1'},
            'payload': {'project_id': 'p1', 'type_id': 'bug', 'title': '旧缺陷', 'description': '旧描述'},
            'item': {'id': 'remote-1', 'identifier': 'AIPIN-300',
                     'url': 'https://example.pingcode.com/pjm/workitems/remote-1'}, 'history': []})
        response = client.post(f'/api/ui-tests/{source["id"]}/regressions', json={
            'target_url': 'https://example.test/ui', 'goal': '复测原缺陷'})
        assert response.status_code == 200, response.text
        project = store.get_project(owner, response.json()['project']['id'])
        baseline = store._read(store.project_dir(owner, source['id']) / 'analyses' / report['id'] / 'report.json')
        failed = baseline['findings'][0]['case_id']
        execution = ui_records.save_cases(store, owner, project['id'], [{
            'case_id': failed, 'scenario': '复测原缺陷', 'environment': 'test', 'client': 'B端',
            'module': '回归', 'precondition': '已部署修复', 'test_data': '沿用原数据', 'steps': '重复原步骤',
            'expected': '问题消失', 'actual': '问题仍可复现', 'status': 'failed'}])
        result = ui_records.publish(store, owner, project, execution['execution_id'], '回归报告', '复测完成')
        new_report = store._read(store.project_dir(owner, project['id']) / 'analyses' /
                                 result['report']['id'] / 'report.json')
        assert new_report['regression_links'] == [{
            'draft_id': 'finding-0', 'case_id': failed, 'source_project_id': source['id'],
            'source_report_id': report['id'], 'source_draft_id': 'finding-0',
            'outcome': 'regression_failed'}]
        records = client.get(f'/api/projects/{project["id"]}/reports/{result["report"]["id"]}/pingcode').json()['values']
        assert records[0]['item']['identifier'] == 'AIPIN-300'
        assert records[0]['triage_status'] == 'regression_failed'
        route = f'/api/projects/{project["id"]}/reports/{result["report"]["id"]}/pingcode/finding-0'
        assert client.post(route, json={'reviewed': True, 'payload': {}}).status_code == 400


def test_regression_pass_adds_review_record_without_counting_a_new_defect(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        imported = client.post('/api/ui-tests/import-results', json={
            'filename': 'baseline.xlsx', 'content_base64': base64.b64encode(completed_results_xlsx()).decode(),
            'environment': 'test', 'client': 'B端'}).json()
        source, report, store = imported['project'], imported['report'], app.state.store
        owner = next(path.name for path in (tmp_path / 'sessions').iterdir())
        service = PingCode(store)
        _, _, old_path = service.source(owner, source['id'], report['id'], 'finding-0')
        store._write(old_path, {'status': 'submitted', 'triage_status': 'pending_regression',
            'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z',
            'source': {'project_id': source['id'], 'run_id': report['id'], 'draft_id': 'finding-0'},
            'item': {'id': 'remote-1', 'identifier': 'AIPIN-300', 'url': 'https://example.test/AIPIN-300'},
            'history': []})
        response = client.post(f'/api/ui-tests/{source["id"]}/regressions', json={'target_url': 'https://example.test/ui'})
        project = store.get_project(owner, response.json()['project']['id'])
        old_report = store._read(store.project_dir(owner, source['id']) / 'analyses' / report['id'] / 'report.json')
        case_id = old_report['findings'][0]['case_id']
        execution = ui_records.save_cases(store, owner, project['id'], [{
            'case_id': case_id, 'scenario': '复测原缺陷', 'environment': 'test', 'client': 'B端',
            'module': '回归', 'precondition': '已修复', 'test_data': '原数据', 'steps': '重复原步骤',
            'expected': '问题消失', 'actual': '问题未再出现', 'status': 'passed'}])
        result = ui_records.publish(store, owner, project, execution['execution_id'], '回归通过', '通过')
        assert result['report']['findings_count'] == 0
        saved = store._read(store.project_dir(owner, project['id']) / 'analyses' / result['report']['id'] / 'report.json')
        assert len(saved['findings']) == 1
        record = service.lifecycle_for_report(owner, project['id'], result['report']['id'])[0]
        assert record['triage_status'] == 'regression_passed'
        assert record['item']['identifier'] == 'AIPIN-300'
        total = client.get(f'/api/projects/{source["id"]}/reports/total/report.json').json()
        finding = next(item for item in total['findings'] if item['case_id'] == case_id)
        assert finding['draft_source']['report_id'] == result['report']['id']
        assert next(item for item in total['regression_links']
                    if item['case_id'] == case_id)['outcome'] == 'regression_passed'
        archived = store._read(store.project_dir(owner, source['id']) / 'analyses' / report['id'] / 'report.json')
        archived['consolidated_into'] = {'project_id': project['id'], 'report_id': result['report']['id']}
        store._write(store.project_dir(owner, source['id']) / 'analyses' / report['id'] / 'report.json', archived)
        total = client.get(f'/api/projects/{source["id"]}/reports/total/report.json').json()
        assert len(total['stage_reports']) == 1
        response = client.get(f'/api/projects/{source["id"]}/reports/{report["id"]}/index.html', follow_redirects=False)
        assert response.status_code == 307
        assert response.headers['location'].endswith(f'/{result["report"]["id"]}/index.html')


def test_legacy_regression_sessions_are_grouped_under_source(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        imported = client.post('/api/ui-tests/import-results', json={
            'filename':'baseline.xlsx','content_base64':base64.b64encode(completed_results_xlsx()).decode(),
            'environment':'test','client':'B端'}).json()
        source = imported['project']
        store = app.state.store
        owner = next(path.name for path in (tmp_path / 'sessions').iterdir())
        child = store.create_project(owner, source['title'] + ' · 回归测试', 'ui-regression.md', '# 回归')
        store.save_asset(owner, child['id'], 'contract', {
            'schema_version':'1.0','title':child['title'],'operations':{},'sources':{},'issues':[]})
        store.update_project(owner, child['id'], {
            'test_kind':'ui','ui_target_url':'https://example.test/ui',
            'regression_source':{'project_id':source['id'],'report_id':imported['report']['id']},
            'analysis_reports':[{'id':'legacy-report','title':'旧回归报告','kind':'analysis',
                                 'created_at':'2026-01-02T00:00:00+00:00','requests_sent':0,
                                 'findings_count':0,'report_url':'/legacy/report.html'}],
            'last_analysis':{'id':'legacy-report','title':'旧回归报告','kind':'analysis',
                             'created_at':'2026-01-02T00:00:00+00:00','requests_sent':0,
                             'findings_count':0,'report_url':'/legacy/report.html'}})
        projects = client.get('/api/bootstrap?test_kind=ui').json()['projects']
        assert [item['id'] for item in projects] == [source['id']]
        grouped = client.get('/api/projects/'+source['id']).json()['project']
        assert {entry['id'] for entry in grouped['analysis_reports']} == {
            imported['report']['id'], 'legacy-report'}
        assert grouped['legacy_regression_sessions'] == 1


def test_sidebar_entry_uses_three_column_structure(tmp_path):
    from html.parser import HTMLParser
    class Entry(HTMLParser):
        def __init__(self):
            super().__init__()
            self.active=False
            self.parts=[]
            self.entries=0
        def handle_starttag(self, tag, attrs):
            data=dict(attrs)
            # Integration settings now open inside the current workspace.
            if tag=='button' and data.get('data-stage')=='8':
                self.active=True
                self.entries+=1
            if self.active and data.get('class'):self.parts.append(data['class'])
        def handle_endtag(self, tag):
            if tag=='button':self.active=False
    with TestClient(create_app(tmp_path,start_fixture=False,testing=True)) as client:
        for page in ['/api-testing','/ui-testing']:
            response=client.get(page)
            assert response.status_code == 200
            parser=Entry();parser.feed(response.text)
            assert parser.entries == 1
            assert 'sidebar-action-icon' in parser.parts
            assert 'sidebar-action-label' in parser.parts
            assert 'sidebar-action-trailing' in parser.parts
