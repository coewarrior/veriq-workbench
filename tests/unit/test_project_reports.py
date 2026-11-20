"""Project aggregation checks use synthetic local records, never business services."""
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api_test_tool.web import create_app
from api_test_tool.project_reports import ProjectReports
from api_test_tool import ui_report_corrections, ui_total_reports


def setup(tmp_path):
    app = create_app(tmp_path / 'data', start_fixture=False, testing=True)
    store = app.state.store
    session, token = store.session(None)
    owner = session['id']
    controller = app.state.orchestration
    product = controller.account_projects.create(owner, {'name': '测试产品', 'login_url': 'https://example.invalid/login'})
    return app, store, owner, product, token, session['csrf']


def session(app, owner, product, title='模块'):
    store = app.state.store
    p = store.create_project(owner, title, 'doc.md', '# synthetic')
    p = store.update_project(owner, p['id'], {'test_kind': 'ui', 'status': 'reported', 'ui_target_url': 'https://example.invalid', 'test_version': 'v1'})
    app.state.orchestration.account_projects.bind(owner, p['id'], product['id'])
    return p


def stage(store, owner, p, day, cases, **fields):
    rid = str(uuid4())
    rows = [{'case_id': cid, 'scenario': cid, 'status': status, 'environment': 'test',
             'actual': status, 'evidence': status, 'precondition': '', 'steps': '', 'expected': '',
             'test_data': '', 'conclusion': '', 'source_row': i + 2} for i, (cid, status) in enumerate(cases)]
    findings = [{'case_id': c['case_id'], 'title': '问题 '+c['case_id'], 'detail': '', 'severity': '',
                 'evidence': c['status'], 'recommendation': ''} for c in rows if c['status'] == 'failed']
    saved = {'id': rid, 'project_id': p['id'], 'test_kind': 'ui', 'title': '阶段报告', 'goal': '',
        'created_at': f'2026-01-{day:02d}T00:00:00+00:00', 'target_url': 'https://example.invalid',
        'summary': 'synthetic', 'test_version': p.get('test_version', ''), 'runs': [], 'sections': [], 'findings': findings,
        'imported_results': {'cases': rows, 'counts': {'total': len(rows)}, 'filename': 'synthetic', 'sheet_name': 'cases'},
        'ui_snapshot': {'id': str(uuid4()), 'cases': rows, 'assets': []}, **fields}
    root = store.project_dir(owner, p['id']) / 'analyses' / rid
    root.mkdir(parents=True)
    store._write(root / 'report.json', saved)
    prior = store.get_project(owner, p['id'])
    store.update_project(owner, p['id'], {'analysis_reports': [{'id': rid, 'title': saved['title'], 'created_at': saved['created_at'],
        'report_url': f'/api/projects/{p["id"]}/reports/{rid}/index.html'}] + prior.get('analysis_reports', [])})
    return saved


def total(app, owner, product):
    service = app.state.project_reports
    group = service.group(owner, product['id'])
    service.refresh(owner, group)
    return group, service.cached(owner, group)


def test_independent_sessions_partial_regression_and_original_drafts(tmp_path):
    app, store, owner, product, *_ = setup(tmp_path)
    first, second = session(app, owner, product, '模块甲'), session(app, owner, product, '模块乙')
    old = stage(store, owner, first, 1, [('SAME', 'failed'), ('KEEP', 'passed')])
    stage(store, owner, second, 1, [('SAME', 'failed')])
    stage(store, owner, first, 2, [('SAME', 'passed')])
    group, saved = total(app, owner, product)
    cases = saved['imported_results']['cases']
    assert len(cases) == 3 and len({c['case_id'] for c in cases}) == 3
    assert saved['imported_results']['counts'] == {'total': 3, 'passed': 2, 'failed': 1}
    assert len(saved['findings']) == 2  # Original failed defect remains reviewable after pass.
    assert any(f['draft_source']['report_id'] == old['id'] for f in saved['findings'])
    assert all(c['source_report']['case_id'] == c['display_case_id'] for c in cases)
    assert group['id'] not in {p['id'] for p in store.list_projects(owner)}


def test_incremental_reads_restart_and_atomic_retry(tmp_path, monkeypatch):
    app, store, owner, product, *_ = setup(tmp_path)
    p = session(app, owner, product)
    stage(store, owner, p, 1, [('ONE', 'passed')])
    group, old = total(app, owner, product)
    worker = ProjectReports(store, app.state.orchestration)
    read = worker._read_source
    seen = []
    monkeypatch.setattr(worker, '_read_source', lambda o, s: (seen.append(s['report_id']), read(o, s))[1])
    worker.refresh(owner, group)
    assert seen == []
    new = stage(store, owner, p, 2, [('TWO', 'blocked')])
    worker.refresh(owner, group)
    assert seen == [new['id']]
    assert len(worker.cached(owner, group)['imported_results']['cases']) == 2
    ui_report_corrections.save(store, owner, p['id'], new['id'], new, 'TWO', {'conclusion': 'corrected'}, 0)
    worker.refresh(owner, group)
    assert seen == [new['id'], new['id']]
    # A source changes after the worker read it: no mixed-version commit.
    stage(store, owner, p, 3, [('THREE', 'passed')])
    before = worker.cached(owner, group)['aggregate']['revision']
    def racing(o, source):
        value = read(o, source)
        root = store.project_dir(owner, source['project_id']) / 'analyses' / source['report_id'] / 'report.json'
        changed = deepcopy(value); changed['summary'] += ' concurrent change'
        store._write(root, changed)
        return value
    monkeypatch.setattr(worker, '_read_source', racing)
    worker.refresh(owner, group)
    assert worker.cached(owner, group)['aggregate']['revision'] == before
    assert worker.cached(owner, group)['aggregate']['status'] == 'updating'


def test_versions_environments_and_out_of_order_rounds(tmp_path):
    app, store, owner, product, *_ = setup(tmp_path)
    p = session(app, owner, product)
    stage(store, owner, p, 1, [('A', 'passed')])
    stage(store, owner, p, 2, [('A', 'failed')], test_version='v2')
    other = stage(store, owner, p, 3, [('A', 'blocked')], test_version='v2')
    other['imported_results']['cases'][0]['environment'] = 'pre'
    store._write(store.project_dir(owner, p['id']) / 'analyses' / other['id'] / 'report.json', other)
    group, saved = total(app, owner, product)
    assert len(saved['imported_results']['cases']) == 3
    assert len(saved['aggregate']['scopes']) == 3


def test_cached_read_does_not_aggregate_and_stale_revision_blocks(tmp_path, monkeypatch):
    app, store, owner, product, *_ = setup(tmp_path)
    p = session(app, owner, product)
    saved = stage(store, owner, p, 1, [('A', 'failed')])
    group, combined = total(app, owner, product)
    service = app.state.project_reports
    monkeypatch.setattr(service, '_read_source', lambda *_: pytest.fail('request reparsed sources'))
    assert ui_total_reports.build(store, owner, group)['aggregate']['revision'] == combined['aggregate']['revision']
    ui_report_corrections.save(store, owner, p['id'], saved['id'], saved, 'A', {'conclusion': 'new'}, 0)
    with pytest.raises(HTTPException) as failure:
        service.validate(owner, group['id'], combined['aggregate']['revision'])
    assert failure.value.status_code == 409


def test_deleted_source_and_removed_product_cannot_expose_old_cache(tmp_path):
    app, store, owner, product, *_ = setup(tmp_path)
    p = session(app, owner, product)
    stage(store, owner, p, 1, [('A', 'failed')])
    group, _ = total(app, owner, product)
    store.recycle_project(owner, p['id'])
    assert not app.state.project_reports.cached(owner, group)['imported_results']['cases']
    group, saved = total(app, owner, product)
    assert saved['aggregate']['notices']
    app.state.orchestration.account_projects.delete(owner, product['id'])
    with pytest.raises(FileNotFoundError):
        ui_total_reports.build(store, owner, group)


def test_original_ui_and_exact_correction_target(tmp_path):
    app, store, owner, product, token, csrf = setup(tmp_path)
    first, second = session(app, owner, product, '甲'), session(app, owner, product, '乙')
    one = stage(store, owner, first, 1, [('DUP', 'failed')])
    two = stage(store, owner, second, 1, [('DUP', 'failed')])
    group, combined = total(app, owner, product)
    case = next(c for c in combined['imported_results']['cases'] if c['source_report']['project_id'] == second['id'])
    with TestClient(app) as client:
        client.cookies.set('api_test_session', token)
        url = f'/api/projects/{group["id"]}/reports/total'
        page = client.get(url+'/index.html')
        assert page.status_code == 200, page.text
        assert 'report-review.js' in page.text and 'data-pingcode-project' in page.text
        assert first['id'] in page.text and second['id'] in page.text
        headers = {'X-CSRF-Token': csrf, 'X-Project-Report': group['id'], 'X-Project-Revision': combined['aggregate']['revision']}
        changed = client.post(url+'/case-corrections/'+case['case_id'], headers=headers,
            json={'fields': {'conclusion': '只修改乙'}, 'revision': 0, 'source_report': case['source_report']})
        assert changed.status_code == 200, changed.text
        assert ui_report_corrections.load(store, owner, second['id'], two['id'])['revision'] == 1
        assert ui_report_corrections.load(store, owner, first['id'], one['id'])['revision'] == 0
        stale = client.post(url+'/case-corrections/'+case['case_id'], headers=headers,
            json={'fields': {'conclusion': '过期操作'}, 'revision': 1, 'source_report': case['source_report']})
        assert stale.status_code == 409


def test_worker_failure_preserves_last_report_and_recovers(tmp_path):
    app, store, owner, product, *_ = setup(tmp_path)
    p = session(app, owner, product)
    source = stage(store, owner, p, 1, [('A', 'passed')])
    group, old = total(app, owner, product)
    path = store.project_dir(owner, p['id']) / 'analyses' / source['id'] / 'report.json'
    path.write_text('invalid JSON')
    app.state.project_reports.tick()
    saved = app.state.project_reports.cached(owner, group)
    assert saved['aggregate']['status'] == 'failed'
    assert saved['aggregate']['revision'] == old['aggregate']['revision']
    store._write(path, source)
    app.state.project_reports.tick()
    assert app.state.project_reports.cached(owner, group)['aggregate']['status'] == 'ready'


def test_queue_source_guard_and_cross_owner(tmp_path):
    app, store, owner, product, *_ = setup(tmp_path)
    p = session(app, owner, product)
    stage(store, owner, p, 1, [('A', 'passed')])
    group, saved = total(app, owner, product)
    service = app.state.project_reports
    context = {'project_id': group['id'], 'membership_revision': group['membership_revision']}
    item = {'project_id': p['id'], 'run_id': saved['stage_reports'][0]['id']}
    item['source_token'] = service.source_token(owner, item['project_id'], item['run_id'])
    service.validate_item(owner, context, item)
    path = store.project_dir(owner, p['id']) / 'analyses' / item['run_id'] / 'report.json'
    source = store._read(path); source['summary'] = 'changed'; store._write(path, source)
    with pytest.raises(HTTPException):
        service.validate_item(owner, context, item)
    other, _ = store.session(None)
    with pytest.raises(FileNotFoundError):
        service.group(other['id'], product['id'])


def test_confirmations_keep_each_source_and_repeat_is_idempotent(tmp_path):
    from api_test_tool.ui_records import required_action
    app, store, owner, product, token, csrf = setup(tmp_path)
    first, second = session(app, owner, product, '甲'), session(app, owner, product, '乙')
    reports = []
    for p in (first, second):
        r = stage(store, owner, p, 1, [('SAME', 'pending_action')])
        row = r['imported_results']['cases'][0]
        row.update(action_type='manual_step', action_required='请完成测试确认')
        store._write(store.project_dir(owner, p['id']) / 'analyses' / r['id'] / 'report.json', r)
        reports.append(r)
    group, saved = total(app, owner, product)
    with TestClient(app) as client:
        client.cookies.set('api_test_session', token)
        headers = {'X-CSRF-Token': csrf, 'X-Project-Report': group['id'], 'X-Project-Revision': saved['aggregate']['revision']}
        for case in saved['imported_results']['cases']:
            path = f'/api/projects/{group["id"]}/reports/total/ui-actions/{case["case_id"]}'
            payload = {'decision': 'completed', 'save_only': True, 'source_report': case['source_report'], 'expected_action': required_action(case)}
            first_response = client.post(path, headers=headers, json=payload)
            assert first_response.status_code == 200, first_response.text
            repeated = client.post(path, headers=headers, json=payload)
            assert repeated.status_code == 200 and repeated.json()['reused'] is True
        for p, r in zip((first, second), reports):
            decisions = store._read(store.project_dir(owner, p['id']) / 'ui-retest-inputs.json')
            assert list(decisions['confirmations'][r['id']]) == ['SAME']
            assert decisions['revision'] == 1
            assert not store.get_project(owner, p['id']).get('action_continuation')


def test_explicit_regression_defect_lineage_keeps_one_review_target(tmp_path):
    app, store, owner, product, *_ = setup(tmp_path)
    p = session(app, owner, product)
    first = stage(store, owner, p, 1, [('A', 'failed')])
    child = store.create_project(owner, '回归', 'doc.md', '# test', round_parent_id=p['id'])
    child = store.update_project(owner, child['id'], {'test_kind': 'ui', 'status': 'reported',
        'test_version': 'v1', 'regression_source': {'project_id': p['id']}})
    stage(store, owner, child, 2, [('A', 'passed')], findings=first['findings'], regression_links=[{
        'case_id': 'A', 'draft_id': 'finding-0', 'source_project_id': p['id'], 'source_report_id': first['id'],
        'source_draft_id': 'finding-0', 'outcome': 'regression_passed'}])
    _, saved = total(app, owner, product)
    assert saved['imported_results']['counts'] == {'passed': 1, 'total': 1}
    assert len(saved['findings']) == 1
    assert saved['findings'][0]['draft_source']['project_id'] == child['id']
    assert saved['regression_links'][0]['outcome'] == 'regression_passed'


def test_parallel_conflict_cannot_be_shown_as_passed(tmp_path):
    app, store, owner, product, *_ = setup(tmp_path)
    p = session(app, owner, product)
    stage(store, owner, p, 1, [('A', 'passed')])
    child = store.create_project(owner, '并行回归', 'doc.md', '# test', round_parent_id=p['id'])
    child = store.update_project(owner, child['id'], {'test_kind': 'ui', 'status': 'reported',
        'test_version': 'v1', 'regression_source': {'project_id': p['id']}})
    stage(store, owner, child, 1, [('A', 'failed')])
    _, saved = total(app, owner, product)
    assert saved['imported_results']['counts'] == {'other': 1, 'total': 1}
    assert saved['imported_results']['cases'][0]['conflicting_sources']
    assert saved['aggregate']['notices']


def test_api_history_outside_navigation_remains_accessible_and_reviewable(tmp_path):
    app, store, owner, product, token, csrf = setup(tmp_path)
    p = store.create_project(owner, 'API 历史', 'api.md', '# synthetic')
    app.state.orchestration.account_projects.bind(owner, p['id'], product['id'])
    rid = str(uuid4())
    root = store.project_dir(owner, p['id']) / 'runs' / rid
    root.mkdir()
    result = {'id': rid, 'run_id': rid, 'created_at': '2026-01-01T00:00:00+00:00',
        'finished_at': '2026-01-01T00:00:00+00:00', 'test_version': 'v1',
        'environment': {'name': 'test', 'base_url': 'https://example.invalid'},
        'cases': [{'id': 'API-OLD', 'title': '原始接口用例', 'status': 'FAIL', 'steps': []}]}
    store._write(root / 'result.json', result)
    store._write(root / 'bundle.json', {'cases': [{'id': 'API-OLD', 'title': '原始接口用例'}]})
    store._write_text(root / 'index.html', '<html><head><title>原报告</title></head><body><main>原执行证据</main></body></html>')
    assert not store.get_project(owner, p['id']).get('runs')
    group, saved = total(app, owner, product)
    assert saved['imported_results']['counts']['failed'] == 1
    assert saved['findings'][0]['draft_source'] == {'project_id': p['id'], 'report_id': rid, 'draft_id': 'defect-0'}
    with TestClient(app) as client:
        client.cookies.set('api_test_session', token)
        base = f'/api/projects/{p["id"]}/reports/{rid}'
        assert client.get(base + '/index.html').status_code == 200
        assert client.get(base + '/result.json').json()['cases'][0]['id'] == 'API-OLD'
        draft = client.get(base + '/pingcode/defect-0')
        assert draft.status_code == 200, draft.text
        assert draft.json()['report_reference']['case_id'] == 'API-OLD'
    other, _ = store.session(None)
    with pytest.raises(FileNotFoundError):
        store.has_saved_report(other['id'], p['id'], rid, kind='runs')
    assert not store.has_saved_report(owner, p['id'], '../escape', kind='runs')


def test_empty_product_does_not_claim_test_success(tmp_path):
    app, _, owner, product, *_ = setup(tmp_path)
    _, saved = total(app, owner, product)
    assert saved['imported_results']['counts']['total'] == 0
    assert '不能形成测试结论' in ''.join(saved['aggregate']['notices'])
