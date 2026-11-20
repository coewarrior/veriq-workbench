import json
import re

from fastapi.testclient import TestClient

from api_test_tool.web import create_app


def test_scene_retention_is_round_scoped_recorded_and_visible_in_report(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        created = client.post('/api/ui-tests', json={
            'title': '资料测试', 'target_url': 'https://example.test/knowledge',
            'goal': '测试资料操作', 'scene_retention': 'defects',
        })
        assert created.status_code == 200, created.text
        project = created.json()['project']
        pid = project['id']
        assert project['ui_scene_retention'] == {'key': 'defects', 'label': '仅保留缺陷现场'}
        assert client.post('/api/ui-tests', json={
            'title': '错误范围', 'target_url': 'https://example.test',
            'goal': '测试', 'scene_retention': 'forever',
        }).status_code == 400

        code = client.post('/api/mcp/pair').json()['code']
        token = client.post('/api/mcp/redeem', json={'code': code}).json()['token']

        def call(action, **arguments):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                               json={'action': action, 'arguments': {'project_id': pid, **arguments}})

        assert call('document').json()['scene_retention']['key'] == 'defects'
        assert call('context').json()['scene_retention']['key'] == 'defects'
        first = call('ui_cases', cases=[{'case_id': 'KB01', 'scenario': '上传后出现缺陷'}])
        assert first.status_code == 200, first.text
        execution_id = first.json()['execution_id']
        assert call('ui_read', execution_id=execution_id).json()['scene_retention']['key'] == 'defects'
        changed = client.put(f'/api/projects/{pid}/task', json={'scene_retention': 'full'})
        assert changed.status_code == 400
        assert client.put(f'/api/projects/{pid}/task', json={'scene_retention': 'defects'}).status_code == 200

        outcome = {'status': 'retained', 'note': '复现对象保留，其他本轮数据已清理。',
                   'items': [{'case_id': 'KB01', 'name': 'kb-run-01', 'kind': '资料',
                              'state': 'retained', 'reason': '保留供缺陷复现'}]}
        bad = call('ui_cases', cases=[], execution_id=execution_id, revision=1,
                   scene_outcome={**outcome, 'status': 'done'})
        assert bad.status_code == 400
        saved = call('ui_cases', cases=[], execution_id=execution_id, revision=1,
                     scene_outcome=outcome)
        assert saved.status_code == 200, saved.text
        assert call('ui_read', execution_id=execution_id).json()['scene_outcome'] == outcome
        published = call('ui_publish', execution_id=execution_id,
                         title='资料报告', summary='发现资料操作问题')
        assert published.status_code == 200, published.text
        report = published.json()['report']
        path = f'/api/projects/{pid}/reports/{report["id"]}'
        saved_report = client.get(path + '/report.json').json()
        assert saved_report['ui_snapshot']['scene_retention']['key'] == 'defects'
        assert saved_report['ui_snapshot']['scene_outcome'] == outcome
        page = client.get(path + '/index.html').text
        view = json.loads(re.search(r'id="report-review-data">(.*?)</script>', page, re.S).group(1))
        assert view['sceneRetention']['key'] == 'defects'
        assert view['sceneOutcome']['items'][0]['name'] == 'kb-run-01'
        assert call('ui_cases', cases=[], execution_id=execution_id, revision=2,
                    scene_outcome={'status': 'cleaned', 'items': [], 'note': ''}).status_code == 400

        regression = client.post(f'/api/ui-tests/{pid}/regressions', json={
            'target_url': 'https://example.test/knowledge', 'goal': '回归验证'})
        assert regression.status_code == 200, regression.text
        assert regression.json()['project']['ui_scene_retention']['key'] == 'none'
        assert client.get(path + '/report.json').json()['ui_snapshot']['scene_retention']['key'] == 'defects'


def test_direct_ui_workflow_defaults_to_no_scene_retention(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        code = client.post('/api/mcp/pair').json()['code']
        token = client.post('/api/mcp/redeem', json={'code': code}).json()['token']
        result = client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token}, json={
            'action': 'start_workflow', 'arguments': {'test_kind': 'ui',
                'target_url': 'https://example.test', 'goal': '测试页面'}})
        assert result.status_code == 200, result.text
        assert result.json()['project']['ui_scene_retention']['key'] == 'none'
