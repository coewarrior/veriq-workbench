"""Synthetic Store report batches: no business, model, browser or network calls."""
from collections import Counter
import socket

import pytest

from api_test_tool import ui_records, ui_report_corrections
from api_test_tool.pingcode import PingCode
from api_test_tool.web_storage import Store


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Synthetic report checks must not use the network')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report', lambda *a, **kw: {'status': 'disabled'})
    store = Store(tmp_path)
    session, _ = store.session(None)
    return store, session['id']


def project(store, owner, title):
    item = store.create_project(owner, title, title + '.md', 'Synthetic docs')
    return store.update_project(owner, item['id'], {
        'test_kind': 'ui', 'ui_target_url': 'https://example.invalid',
        'execution_round': {'id': title}})


def cases(status):
    return [dict(case_id=f'C{i}', scenario=f'Synthetic {i}', status=status,
                 actual='Synthetic observation' if status != 'not_run' else '',
                 expected='Synthetic expected') for i in range(10)]


def publish(store, owner, item, status):
    saved = ui_records.save_cases(store, owner, item['id'], cases(status), refresh_report=False)
    item = store.get_project(owner, item['id'])
    result = ui_records.publish(store, owner, item, saved['execution_id'], title='Synthetic',
                               summary='Synthetic summary', notify=False)
    return store.get_project(owner, item['id']), saved, result['report']


def count_reads(store, monkeypatch):
    read, counts = store._read, Counter()
    def counted(path):
        if path.name in {'report.json', 'cases.json'}:
            counts[(path.parent.name, path.name)] += 1
        return read(path)
    monkeypatch.setattr(store, '_read', counted)
    return read, counts


def test_published_save_reuses_current_locked_record_and_original_report(workspace, monkeypatch):
    store, owner = workspace
    item, saved, entry = publish(store, owner, project(store, owner, 'source'), 'failed')
    root = store.project_dir(owner, item['id']) / 'analyses' / entry['id']
    original = store._read(root / 'report.json')
    read, counts = count_reads(store, monkeypatch)
    result = ui_records.save_cases(store, owner, item['id'], cases('passed'),
                                  saved['execution_id'], saved['revision'], response='summary')
    assert result['revision'] == saved['revision'] + 1
    assert result['report']['id'] == entry['id']
    assert read(root / 'revisions' / '1.json') == original
    assert counts[(saved['execution_id'], 'cases.json')] == 1
    # One original snapshot plus one fresh view after the report rewrite.
    assert counts[(entry['id'], 'report.json')] == 2


def regression(workspace):
    store, owner = workspace
    source, _, source_entry = publish(store, owner, project(store, owner, 'source'), 'failed')
    target = project(store, owner, 'target')
    target = store.update_project(owner, target['id'], {'regression_round': {
        'report_project_id': source['id'], 'report_id': source_entry['id']}})
    target, saved, entry = publish(store, owner, target, 'not_run')
    return source, source_entry, target, saved, entry


def test_linked_save_batches_reads_preserves_archive_and_observes_next_correction(workspace, monkeypatch):
    store, owner = workspace
    source, source_entry, target, saved, entry = regression(workspace)
    source_root = store.project_dir(owner, source['id']) / 'analyses' / source_entry['id']
    root = store.project_dir(owner, target['id']) / 'analyses' / entry['id']
    original = store._read(root / 'report.json')
    read, counts = count_reads(store, monkeypatch)
    result = ui_records.save_cases(store, owner, target['id'], cases('passed'),
                                  saved['execution_id'], saved['revision'], response='summary')
    report = read(root / 'report.json')
    assert result['revision'] == saved['revision'] + 1
    assert [f['case_id'] for f in report['findings']] == [f'C{i}' for i in range(10)]
    assert {link['outcome'] for link in report['regression_links']} == {'regression_passed'}
    assert read(root / 'revisions' / '1.json') == original
    assert sum(n for (_, name), n in counts.items() if name == 'report.json') <= 6
    assert counts[(saved['execution_id'], 'cases.json')] == 1
    # The next independent operation must read a correction, not a previous batch.
    ui_report_corrections.save(store, owner, source['id'], source_entry['id'],
        read(source_root / 'report.json'), 'C0', {'status': 'passed'}, 0)
    states = PingCode(store).lifecycle_for_report(owner, source['id'], source_entry['id'])
    assert states[0]['triage_status'] == 'result_corrected'
    assert states[1]['triage_status'] == 'regression_passed'


def test_lifecycle_batch_reuses_report_but_not_changed_correction(workspace, monkeypatch):
    store, owner = workspace
    source, source_entry, target, saved, _ = regression(workspace)
    ui_records.save_cases(store, owner, target['id'], cases('passed'),
                          saved['execution_id'], saved['revision'], response='summary')
    root = store.project_dir(owner, source['id']) / 'analyses' / source_entry['id']
    read, counts = count_reads(store, monkeypatch)
    original = read(root / 'report.json')
    service = PingCode(store)
    summarize = service.record_summary
    summarized = 0
    def correct_after_first(record):
        nonlocal summarized
        value = summarize(record)
        summarized += 1
        if summarized == 1:
            for i in range(10):
                ui_report_corrections.save(store, owner, source['id'], source_entry['id'],
                                          original, f'C{i}', {'status': 'passed'}, i)
        return value
    monkeypatch.setattr(service, 'record_summary', correct_after_first)
    states = service.lifecycle_for_report(owner, source['id'], source_entry['id'])
    assert sum(s['triage_status'] == 'result_corrected' for s in states) == 9
    assert counts[(source_entry['id'], 'report.json')] <= 2


def test_lifecycle_report_rewrite_drops_deleted_source_dependencies(workspace, monkeypatch):
    store, owner = workspace
    source, _, target, saved, entry = regression(workspace)
    ui_records.save_cases(store, owner, target['id'], cases('passed'),
                          saved['execution_id'], saved['revision'], response='summary')
    path = store.project_dir(owner, target['id']) / 'analyses' / entry['id'] / 'report.json'
    replacement = store._read(path)
    replacement.pop('regression_links')
    service = PingCode(store)
    summarize = service.record_summary
    summarized = 0
    def rewrite_after_first(record):
        nonlocal summarized
        value = summarize(record)
        summarized += 1
        if summarized == 1:
            store._write(path, replacement)
            store.recycle_project(owner, source['id'])
        return value
    monkeypatch.setattr(service, 'record_summary', rewrite_after_first)
    states = service.lifecycle_for_report(owner, target['id'], entry['id'])
    assert sum(s['triage_status'] == 'regression_passed' for s in states) == 1
    assert sum(s['triage_status'] == 'result_corrected' for s in states) == 9


def test_new_observations_expire_stale_corrections_and_keep_other_manual_edits(workspace):
    store, owner = workspace
    item, saved, entry = publish(store, owner, project(store, owner, 'current'), 'failed')
    path = store.project_dir(owner, item['id']) / 'analyses' / entry['id'] / 'report.json'
    original = store._read(path)
    ui_report_corrections.save(store, owner, item['id'], entry['id'], original,
                               'C0', {'status': 'partial', 'evidence': 'Earlier incomplete'}, 0)
    ui_report_corrections.save(store, owner, item['id'], entry['id'], original,
                               'C1', {'steps': 'Manual verified steps'}, 1)
    updated = ui_records.save_cases(store, owner, item['id'], [
        {'case_id': 'C0', 'status': 'passed', 'actual': 'New complete observation'}],
        saved['execution_id'], saved['revision'], response='summary')
    effective = PingCode(store).analysis_report(owner, item['id'], entry['id'])
    current = {c['case_id']: c for c in effective['imported_results']['cases']}
    assert current['C0']['status'] == 'passed'
    assert current['C0']['evidence'] == 'New complete observation'
    assert current['C1']['steps'] == 'Manual verified steps'
    corrections = ui_report_corrections.load(store, owner, item['id'], entry['id'])
    assert 'C0' not in corrections['cases']
    assert corrections['history'][-1]['scope'] == 'continuation'
    assert store._read(path.parent / 'revisions' / '1.json') == original
    # An independent save must start from the new on-disk revision.
    with pytest.raises(ValueError, match='revision'):
        ui_records.save_cases(store, owner, item['id'], cases('failed'),
                              saved['execution_id'], saved['revision'])
    assert updated['revision'] == saved['revision'] + 1


def test_lifecycle_batch_rechecks_current_project_deletion(workspace, monkeypatch):
    store, owner = workspace
    _, _, target, saved, entry = regression(workspace)
    ui_records.save_cases(store, owner, target['id'], cases('passed'),
                          saved['execution_id'], saved['revision'], response='summary')
    service = PingCode(store)
    summarize = service.record_summary
    def delete_after_first(record):
        value = summarize(record)
        store.recycle_project(owner, target['id'])
        return value
    monkeypatch.setattr(service, 'record_summary', delete_after_first)
    with pytest.raises(FileNotFoundError, match='recycle bin'):
        service.lifecycle_for_report(owner, target['id'], entry['id'])
