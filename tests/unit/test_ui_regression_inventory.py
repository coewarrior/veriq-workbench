"""Overall regression must not silently shrink after partial stage reports."""
import json
from hashlib import sha256

from fastapi.testclient import TestClient
from contextlib import ExitStack
import sys
import pytest


@pytest.fixture(autouse=True)
def client_lifespans(monkeypatch, postgres_database):
    factory = TestClient
    with ExitStack() as stack:
        monkeypatch.setattr(sys.modules[__name__], "TestClient",
                            lambda app: stack.enter_context(factory(app)))
        yield
from api_test_tool.web import create_app
from api_test_tool import ui_records, ui_report_corrections


def case(cid, status='not_run', suffix='original'):
    return {'case_id': cid, 'scenario': cid, 'module': 'synthetic', 'environment': 'test',
            'client': 'B端', 'executor': 'AI', 'precondition': 'synthetic only',
            'test_data': 'generated text', 'steps': 'steps ' + suffix,
            'expected': 'expected ' + suffix, 'actual': 'observation ' + suffix,
            'conclusion': 'conclusion ' + suffix, 'status': status}


def publish(store, owner, pid, cases):
    saved = ui_records.save_cases(store, owner, pid, cases)
    return ui_records.publish(store, owner, store.get_project(owner, pid),
                              saved['execution_id'], 'Synthetic stage', 'Synthetic results only')['report']


def setup(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    client = TestClient(app)
    client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
    store = app.state.store
    owner = next(path.name for path in (tmp_path / 'sessions').iterdir())
    project = store.create_project(owner, 'Synthetic regression', 'synthetic.md', 'Synthetic only')
    project = store.update_project(owner, project['id'], {
        'test_kind': 'ui', 'ui_target_url': 'https://example.test/ui'})
    return client, store, owner, project


def baseline(store, owner, pid):
    doc = (store.project_dir(owner, pid) / 'inputs/current-regression.md').read_text()
    return json.loads(doc[doc.index('{\n'):])


def test_overall_regression_keeps_stage_union_latest_design_and_history(tmp_path):
    client, store, owner, project = setup(tmp_path)
    pid = project['id']
    first = publish(store, owner, pid, [case('A', 'failed'), case('B', 'passed'), case('C')])
    second = publish(store, owner, pid, [case('B', 'passed', 'updated')])
    paths = [store.project_dir(owner, pid) / 'analyses' / r['id'] / 'report.json' for r in [first, second]]
    hashes = [sha256(p.read_bytes()).hexdigest() for p in paths]
    response = client.post(f'/api/ui-tests/{pid}/regressions', json={})
    assert response.status_code == 200, response.text
    saved = baseline(store, owner, response.json()['project']['id'])
    assert [c['case_id'] for c in saved['cases']] == ['A', 'B', 'C']
    assert [c['steps'] for c in saved['cases']] == ['steps original', 'steps updated', 'steps original']
    assert response.json()['project']['ui_execution_id'] == ''
    assert response.json()['project']['regression_round']['case_ids'] == ['A', 'B', 'C']
    assert [sha256(p.read_bytes()).hexdigest() for p in paths] == hashes
    assert [c['case_id'] for c in saved['defect_lineage']] == ['A']
    assert saved['defect_lineage'][0]['source_report_id'] == first['id']
    # Completing a formerly failed case still refers to its real prior draft.
    third = publish(store, owner, response.json()['project']['id'], [case('A', 'passed', 'rechecked')])
    report = store._read(store.project_dir(owner, response.json()['project']['id']) / 'analyses' / third['id'] / 'report.json')
    assert report['regression_links'] == [{'draft_id': 'finding-0', 'case_id': 'A',
        'source_project_id': pid, 'source_report_id': first['id'],
        'source_draft_id': 'finding-0', 'outcome': 'regression_passed'}]


def test_failed_scope_uses_latest_session_results_then_overall_recovers_inventory(tmp_path):
    client, store, owner, project = setup(tmp_path)
    pid = project['id']
    publish(store, owner, pid, [case('A', 'failed'), case('B', 'failed'), case('C', 'failed')])
    publish(store, owner, pid, [case('B', 'passed', 'updated')])
    response = client.post(f'/api/ui-tests/{pid}/regressions', json={'regression_scope': 'failed'})
    assert response.status_code == 200, response.text
    assert [c['case_id'] for c in baseline(store, owner, response.json()['project']['id'])['cases']] == ['A', 'C']
    assert [c['case_id'] for c in baseline(store, owner, response.json()['project']['id'])['defect_lineage']] == ['A', 'C']
    publish(store, owner, pid, [case('B', 'passed', 'rechecked')])
    response = client.post(f'/api/ui-tests/{pid}/regressions', json={'regression_scope': 'all'})
    assert response.status_code == 200, response.text
    assert [c['case_id'] for c in baseline(store, owner, response.json()['project']['id'])['cases']] == ['A', 'B', 'C']


def test_unpublished_baseline_still_used_when_no_stage_report_exists(tmp_path):
    client, store, owner, project = setup(tmp_path)
    pid = project['id']
    ui_records.save_cases(store, owner, pid, [case('A')])
    response = client.post(f'/api/ui-tests/{pid}/regressions', json={})
    assert response.status_code == 200, response.text
    assert [c['case_id'] for c in baseline(store, owner, response.json()['project']['id'])['cases']] == ['A']


def test_legacy_stage_sources_and_corrections_remain_case_specific(tmp_path):
    client, store, owner, project = setup(tmp_path)
    pid = project['id']
    first = publish(store, owner, pid, [case('A', 'failed'), case('B', 'failed')])
    first_record = store._read(store.project_dir(owner, pid) / 'analyses' / first['id'] / 'report.json')
    ui_report_corrections.save(store, owner, pid, first['id'], first_record, 'A',
                               {'expected': 'audited expected'}, 0)
    child = store.create_project(owner, 'Legacy partial round', 'synthetic.md', 'Synthetic only')
    child = store.update_project(owner, child['id'], {'test_kind': 'ui',
        'regression_source': {'project_id': pid}, 'ui_target_url': 'https://example.test/ui'})
    second = publish(store, owner, child['id'], [case('B', 'passed', 'newest'), case('C', 'failed')])
    response = client.post(f'/api/ui-tests/{pid}/regressions', json={})
    assert response.status_code == 200, response.text
    saved = baseline(store, owner, response.json()['project']['id'])
    assert [c['case_id'] for c in saved['cases']] == ['A', 'B', 'C']
    assert saved['cases'][0]['expected'] == 'audited expected'
    assert saved['cases'][1]['status'] == 'passed'
    assert [(x['case_id'], x['source_project_id'], x['source_report_id'])
            for x in saved['defect_lineage']] == [('A', pid, first['id']), ('C', child['id'], second['id'])]
    third = publish(store, owner, response.json()['project']['id'], [case('A', 'passed'), case('B', 'passed'), case('C', 'failed')])
    report = store._read(store.project_dir(owner, response.json()['project']['id']) / 'analyses' / third['id'] / 'report.json')
    links = {x['case_id']: x for x in report['regression_links']}
    assert set(links) == {'A', 'C'}
    assert links['A']['source_report_id'] == first['id']
    assert links['C']['source_report_id'] == second['id']
    assert links['C']['source_project_id'] == child['id']
