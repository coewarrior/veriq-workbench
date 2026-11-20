"""Total report optimizations must preserve source, order and frozen evidence."""
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

from api_test_tool import ui_report_corrections, ui_total_reports
from api_test_tool.web_storage import Store


def case(cid, status, stage):
    return {'case_id': cid, 'scenario': cid, 'status': status,
            'evidence': f'{cid} observation {stage}', 'conclusion': f'{cid} conclusion {stage}',
            'checkpoints': [{'id': 'point', 'assertions': [{'expected': stage}]}]}


def asset(cid, aid):
    return {'case_id': cid, 'id': aid, 'kind': 'fixture', 'filename': aid + '.txt'}


def stage(store, owner, project, day, cases, assets, **extra):
    rid = str(uuid4())
    report = {'id': rid, 'project_id': project['id'], 'title': f'Stage {day}',
              'report_type': 'stage', 'created_at': f'2026-01-{day:02d}T00:00:00Z',
              'imported_results': {'cases': cases}, 'findings': [],
              'ui_snapshot': {'id': 'execution-' + rid, 'cases': cases, 'assets': assets,
                              'coverage': [{'case_ids': [c['case_id'] for c in cases]}],
                              'experiment': {'variant': 'stage only'}}, **extra}
    path = store.project_dir(owner, project['id']) / 'analyses' / rid / 'report.json'
    path.parent.mkdir(parents=True)
    store._write(path, report)
    return report, path


def workspace(tmp_path):
    store = Store(tmp_path)
    session, _ = store.session(None)
    owner = session['id']
    project = store.create_project(owner, 'Synthetic reports', 'synthetic.md', 'Synthetic only')
    project = store.update_project(owner, project['id'], {'test_kind': 'ui'})
    return store, owner, project


def test_total_preserves_mixed_stage_origin_order_corrections_and_snapshot(tmp_path):
    store, owner, project = workspace(tmp_path)
    old, old_path = stage(store, owner, project, 1,
        [case('A', 'passed', 1), case('B', 'failed', 1), case('C', 'not_run', 1)],
        [asset('A', 'a-1'), asset('B', 'old-b'), asset('A', 'a-2')])
    new, new_path = stage(store, owner, project, 2,
        [case('B', 'passed', 2), case('D', 'partial', 2)],
        [asset('D', 'd-1'), asset('B', 'b-1'), asset('B', 'b-2')],
        custom_metadata={'nested': ['preserved']})
    ui_report_corrections.save(store, owner, project['id'], old['id'], old, 'A',
                               {'conclusion': 'audited correction'}, 0)
    originals = {path: sha256(path.read_bytes()).hexdigest() for path in (old_path, new_path)}
    total = ui_total_reports.build(store, owner, project)
    cases = total['imported_results']['cases']
    assert [(c['case_id'], c['status']) for c in cases] == [
        ('A', 'passed'), ('B', 'passed'), ('C', 'not_run'), ('D', 'partial')]
    assert [c['source_report']['id'] for c in cases] == [old['id'], new['id'], old['id'], new['id']]
    assert [c['conclusion'] for c in cases] == [
        'audited correction', 'B conclusion 2', 'C conclusion 1', 'D conclusion 2']
    assert [s['id'] for s in total['stage_reports']] == [new['id'], old['id']]
    assets = total['ui_snapshot']['assets']
    assert [a['id'] for a in assets] == ['a-1', 'a-2', 'b-1', 'b-2', 'd-1']
    assert [a['source_execution_id'] for a in assets] == [
        old['ui_snapshot']['id'], old['ui_snapshot']['id'],
        new['ui_snapshot']['id'], new['ui_snapshot']['id'], new['ui_snapshot']['id']]
    for item in assets:
        source = old if item['case_id'] == 'A' else new
        assert item['source_project_id'] == project['id']
        assert item['url'] == f"/api/projects/{project['id']}/reports/{source['id']}/asset-{item['id']}"
    assert total['ui_snapshot']['id'] == ''
    assert 'experiment' not in total['ui_snapshot']
    assert total['ui_snapshot']['coverage'] == new['ui_snapshot']['coverage']
    assert total['custom_metadata'] == {'nested': ['preserved']}
    assert {path: sha256(path.read_bytes()).hexdigest() for path in originals} == originals


def test_total_does_not_alias_selected_nested_cases_or_inherited_metadata(tmp_path, monkeypatch):
    store, owner, project = workspace(tmp_path)
    report, path = stage(store, owner, project, 1, [case('A', 'passed', 1)], [],
                         custom_metadata={'nested': ['preserved']})
    original = deepcopy(report)
    read = store._read
    monkeypatch.setattr(store, '_read', lambda location: report if location == path else read(location))
    total = ui_total_reports.build(store, owner, project)
    total['imported_results']['cases'][0]['checkpoints'][0]['assertions'][0]['expected'] = 'changed'
    total['ui_snapshot']['coverage'][0]['case_ids'].append('changed')
    total['custom_metadata']['nested'].append('changed')
    assert report == original


def test_total_keeps_empty_latest_analysis_and_distinct_project_asset_sources(tmp_path):
    store, owner, project = workspace(tmp_path)
    first, _ = stage(store, owner, project, 1, [case('A', 'passed', 1)], [asset('A', 'same-name')])
    child = store.create_project(owner, 'Legacy regression', 'synthetic.md', 'Synthetic only')
    child = store.update_project(owner, child['id'], {
        'test_kind': 'ui', 'regression_source': {'project_id': project['id']}})
    second, _ = stage(store, owner, child, 2, [case('B', 'passed', 2)], [asset('B', 'same-name')])
    latest, _ = stage(store, owner, project, 3, [], [], summary='Latest empty analysis')
    total = ui_total_reports.build(store, owner, child)
    assert total['project_id'] == project['id']
    assert [(a['case_id'], a['source_project_id']) for a in total['ui_snapshot']['assets']] == [
        ('A', project['id']), ('B', child['id'])]
    assert [c['source_report']['id'] for c in total['imported_results']['cases']] == [first['id'], second['id']]
    assert total['ui_snapshot']['coverage'] == latest['ui_snapshot']['coverage']
    assert total['created_at'] == latest['created_at']
    empty = store.create_project(owner, 'Empty analysis', 'synthetic.md', 'Synthetic only')
    empty = store.update_project(owner, empty['id'], {'test_kind': 'ui'})
    finding = {'title': 'An analysis finding', 'detail': 'No executed cases'}
    stage(store, owner, empty, 1, [], [], summary='Retain this analysis', findings=[finding])
    empty_total = ui_total_reports.build(store, owner, empty)
    assert empty_total['summary'] == 'Retain this analysis'
    assert empty_total['findings'] == [finding]
    assert empty_total['imported_results']['cases'] == []
