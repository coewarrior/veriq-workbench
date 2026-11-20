"""Isolated round metadata checks; no model or business-environment requests."""
import asyncio
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api_test_tool.ui_experiments import merge
from api_test_tool.web import create_app


@pytest.mark.parametrize('patch', [
    [], {'credentials': {'password': 'synthetic'}}, {'variant': {'nested': 'value'}},
    {'model': ['example-model']}, {'model_source': 'inferred'},
    {'tool_calls': -1}, {'tool_calls': True}, {'tool_calls': 1.5}, {'tool_errors': '0'},
    {'started_at': '2026-10-11T08:00:00'}, {'started_at': '2026-02-30T08:00:00Z'},
    {'execution_started_at': '2026-10-11'}, {'execution_finished_at': 1},
])
def test_invalid_optional_metadata_is_rejected_without_coercion(patch):
    with pytest.raises(ValueError):
        merge({}, patch)


def test_incremental_events_compare_timezones_and_allow_missing_events():
    saved = merge({}, {'started_at': '2026-10-11T16:00:00+08:00', 'tool_errors': 0})
    assert 'tool_calls' not in saved and 'model_source' not in saved
    saved = merge(saved, {'execution_finished_at': '2026-10-11T08:02:00Z'})
    with pytest.raises(ValueError, match='顺序'):
        merge(saved, {'execution_started_at': '2026-10-11T08:03:00Z'})
    assert 'execution_started_at' not in saved
    updated = merge(saved, {'started_at': None, 'tool_errors': None, 'model_source': 'verified'})
    assert updated == {'execution_finished_at': '2026-10-11T08:02:00Z', 'model_source': 'verified'}
    # Provenance completeness is not a publication gate, nor is wall clock skew.
    assert merge({}, {'started_at': '2099-01-01T00:00:00Z'})['started_at'].startswith('2099')
    assert merge({}, {'variant': 'token=synthetic-secret'})['variant'] == 'token=<redacted>'


def test_round_measurements_persist_freeze_and_do_not_leak_into_totals(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        pid = client.post('/api/ui-tests', json={
            'title': '合成实验', 'target_url': 'https://example.test', 'goal': '验证合成页面'
        }).json()['project']['id']
        code = client.post('/api/mcp/pair').json()['code']
        token = client.post('/api/mcp/redeem', json={'code': code}).json()['token']

        def call(action, **args):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                               json={'action': action, 'arguments': {'project_id': pid, **args}})

        def review(url):
            page = client.get(url)
            assert page.status_code == 200
            return json.loads(re.search(r'id="report-review-data">(.*?)</script>', page.text, re.S).group(1))

        # Saving/publication timestamps cannot stand in for an execution window.
        old = call('ui_cases', cases=[{'case_id': 'OLD', 'scenario': '已有未执行设计'}]).json()
        old_url = call('ui_publish', execution_id=old['execution_id'], title='旧阶段', summary='尚未执行').json()['report']['report_url']
        old_review = review(old_url)
        assert 'experiment' not in old_review
        assert old_review['timing'] is None
        assert '无法计算' in old_review['timingNotice']

        # A genuinely new task is explicit; continuation alone keeps one report.
        pid = client.post(f'/api/ui-tests/{pid}/regressions', json={}).json()['project']['id']
        experiment = {'experiment_id': 'synthetic-comparison', 'variant': 'A', 'model': 'example-model',
                      'reasoning_effort': 'example-effort', 'model_source': 'requested',
                      'started_at': '2026-10-11T08:00:00Z'}
        saved = call('ui_cases', cases=[], experiment=experiment).json()
        eid, revision = saved['execution_id'], saved['revision']
        assert eid != old['execution_id'] and saved['experiment'] == experiment
        saved = call('ui_cases', execution_id=eid, revision=revision,
                     cases=[{'case_id': 'NEW', 'scenario': '新设计', 'status': 'partial', 'actual': '只验证前半段'}],
                     review_notes='缺少后半段条件').json()
        before = call('ui_read', execution_id=eid).json()
        progress_before = call('workflow_status').json()['progress']
        assert before['experiment'] == experiment
        patch = {'execution_started_at': '2026-10-11T16:01:00+08:00',
                 'execution_finished_at': '2026-10-11T08:02:00Z', 'tool_errors': 0}
        saved = call('ui_cases', execution_id=eid, revision=saved['revision'], cases=[], experiment=patch).json()
        after = call('ui_read', execution_id=eid).json()
        assert call('workflow_status').json()['progress'] == progress_before
        assert after['cases'] == before['cases']
        assert after['review_revision'] == after['revision']
        assert after['experiment'] == {**experiment, **patch}
        assert 'tool_calls' not in after['experiment']
        rejected = call('ui_cases', execution_id=eid, revision=saved['revision'], cases=[],
                        experiment={'started_at': '2026-10-11T09:00:00Z'})
        assert rejected.status_code == 400
        assert call('ui_read', execution_id=eid).json()['revision'] == saved['revision']
        published = call('ui_publish', execution_id=eid, title='新阶段', summary='如实记录局部验证').json()
        url = published['report']['report_url']
        snapshot = client.get(url.replace('index.html', 'report.json')).json()
        assert snapshot['ui_snapshot']['experiment'] == after['experiment']
        assert snapshot['imported_results']['counts'] == {'partial': 1, 'total': 1}
        rendered = review(url)
        assert rendered['experiment'] == after['experiment']
        assert rendered['experimentPublishedAt'] == snapshot['created_at']
        assert rendered['timing']['startedAt'] == patch['execution_started_at']
        assert rendered['timing']['finishedAt'] == patch['execution_finished_at']
        assert call('ui_cases', execution_id=eid, revision=saved['revision'], cases=[], experiment={'variant': 'changed'}).status_code == 200
        assert review(url)['experiment']['variant'] == 'changed'
        total_url = published['total_report']['report_url']
        assert 'experiment' not in review(total_url)
        total = client.get(total_url.replace('index.html', 'report.json')).json()
        assert 'experiment' not in total['ui_snapshot']
        assert total['imported_results']['counts'] == {'not_run': 1, 'partial': 1, 'total': 2}
        new_round = call('ui_cases', cases=[{'case_id': 'NEXT', 'scenario': '下一轮'}]).json()
        assert new_round['execution_id'] == eid
        assert call('ui_read', execution_id=new_round['execution_id']).json()['experiment'] == {**experiment, **patch, 'variant': 'changed'}


def test_mcp_schema_and_adapter_preserve_sparse_metadata():
    from api_test_tool.mcp_server import create_server

    class Client:
        def call(self, action, **args):
            self.received = (action, args)
            return {'ok': True}

    client = Client()
    server = create_server(client)
    patch = {'variant': 'A', 'tool_errors': 0, 'model': None}
    asyncio.run(server.call_tool('save_ui_test_cases', {'project_id': 'synthetic', 'cases': [], 'experiment': patch}))
    assert client.received[0] == 'ui_cases'
    assert client.received[1]['experiment'] == patch
    tools = asyncio.run(server.list_tools())
    schema = next(t.inputSchema for t in tools if t.name == 'save_ui_test_cases')
    manifest = json.loads((Path(__file__).parents[2] / 'api_test_tool/static/agent-tools.json').read_text())
    assert next(t['inputSchema'] for t in manifest['tools'] if t['name'] == 'save_ui_test_cases') == schema
    fields = schema['$defs']['UIExperiment']
    assert fields['additionalProperties'] is False
    assert set(fields['properties']['model_source']['anyOf'][0]['enum']) == {'requested', 'reported', 'verified'}
