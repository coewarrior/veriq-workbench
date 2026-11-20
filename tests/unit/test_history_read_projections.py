"""Read consumers keep current authority without decoding archived node cases."""
from pg_support import observe
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api_test_tool.managed_service import ManagedService
from api_test_tool.native_execution import NativeExecution
from api_test_tool.native_work_plan import load_record_views
from api_test_tool.orchestration import Controller
from api_test_tool.web_storage import Store
from api_test_tool import ui_records

STATIC = Path(__file__).parents[2] / 'api_test_tool' / 'static'
JOURNAL = 'archived-case-body-must-stay-in-sql'


@pytest.fixture
def rounds(tmp_path):
    store = Store(tmp_path)
    c = Controller(store)
    owner, other = (store.session(None)[0]['id'] for _ in range(2))
    items = []
    for index, who in enumerate((owner, owner, other)):
        p = store.create_project(who, 'Fixture', 'fixture.md', 'Original scope')
        store.update_project(who, p['id'], {'test_kind': 'ui', 'ui_target_url': 'https://fixture.test/login'})
        tid = c.create_task(who, {'project_id': p['id'], 'goal': 'Original scope', 'request_id': str(index),
            'modules': [{'key': 'session', 'title': 'Fixture', 'requirements': []}]})['task_id']
        nid = c.snapshot(who, tid)['nodes'][0]['id']
        saved = ui_records.save_cases(store, who, p['id'], [
            {'case_id': 'A', 'scenario': 'Original assertion', 'status': 'not_run'}])
        items.append((who, p['id'], tid, nid, saved['execution_id']))
    with c.transaction() as (_, state):
        state['host_tokens'] = {hashlib.sha256(b'fixture-token').hexdigest(): {'owner': owner, 'host_id': 'host'}}
        for who, pid, tid, nid, eid in items:
            state['tasks'][tid]['execution_route'] = 'native_browser'
            state['nodes'][nid].update(record_project_id=pid, record_execution_id=eid,
                case_history={'1': {'cases': [{'actual': JOURNAL + 'x' * 1000000}]}})
    return c, ManagedService(c, STATIC), items


def forbid_journal_decode(monkeypatch):
    loads = json.loads
    def guarded(raw, *args, **kwargs):
        assert JOURNAL not in raw, 'unrelated archived node cases reached the JSON decoder'
        return loads(raw, *args, **kwargs)
    monkeypatch.setattr(json, 'loads', guarded)


def test_snapshot_filters_in_sql_and_explicit_history_remains_complete(rounds, monkeypatch):
    c, _, items = rounds
    owner, _, tid, nid, _ = items[0]
    original = c.snapshot(owner, tid, include_history=True)
    with monkeypatch.context() as guard:
        forbid_journal_decode(guard)
        snap = c.snapshot(owner, tid)
        assert [n['id'] for n in snap['nodes']] == [nid]
        assert len(c.snapshot(owner)['nodes']) == 2
        with pytest.raises(PermissionError):
            c.snapshot(owner, items[2][2])
    assert {k: v for k, v in original['nodes'][0].items() if k != 'case_history'} == snap['nodes'][0]
    assert c.snapshot(owner, tid, include_history=True) == original


def test_work_record_bindings_include_active_nodes_without_work_plan(rounds, monkeypatch):
    c, _, items = rounds
    forbid_journal_decode(monkeypatch)
    views = load_record_views(c)
    assert set(views) == {item[3] for item in items}
    for owner, pid, tid, nid, eid in items:
        assert views[nid]['binding'] == {'owner': owner, 'task_id': tid, 'revision': 1,
            'record_project_id': pid, 'record_execution_id': eid}
        assert views[nid]['record']['id'] == eid


@pytest.mark.parametrize('consumer', ['native_authorization', 'unleased_context', 'authenticate', 'lease', 'notify'])
def test_readonly_consumers_do_not_decode_node_journals(rounds, monkeypatch, consumer):
    c, service, items = rounds
    owner, _, tid, nid, _ = items[0]
    if consumer == 'lease':
        with c.transaction() as (_, state):
            state['leases']['fixture-lease'] = {'runner_id': 'host', 'node_id': nid}
    forbid_journal_decode(monkeypatch)
    if consumer == 'native_authorization':
        with NativeExecution(service.direct)._authorization_state(writable=False) as state:
            assert state['nodes'][nid]['task_id'] == tid
            assert 'case_history' not in state['nodes'][nid]
    elif consumer == 'unleased_context':
        result = service.direct._context_without_lease(owner, {'task_id': tid, 'node_id': nid, 'holder_id': 'worker'})
        assert result['state'] == 'queued' and result['lease_id'] is None
    elif consumer == 'authenticate':
        assert service.authenticate('fixture-token') == {'owner': owner, 'host_id': 'host'}
        with pytest.raises(PermissionError): service.authenticate('invalid')
    elif consumer == 'lease':
        lease, node, task, state = service.lease(owner, 'host', 'fixture-lease', active=False)
        assert node['id'] == nid and task['id'] == tid
        assert 'case_history' not in node
    else:
        # Notification swallows optional errors, so observe the real decoded reads.
        loaded = []
        read = json.loads
        def observed(raw, *args, **kwargs):
            loaded.append(len(raw)); return read(raw, *args, **kwargs)
        monkeypatch.setattr(json, 'loads', observed)
        service.notify_final_report(owner, nid)
        assert loaded and max(loaded) < 100000


def test_finalize_pending_reads_only_marked_bindings_without_other_history(rounds, monkeypatch):
    c, service, items = rounds
    with c.transaction() as (_, state):
        state['nodes'][items[0][3]]['finalization_pending'] = True
        state['nodes'][items[2][3]]['finalization_pending'] = True
    settled, notified = [], []
    monkeypatch.setattr(service, 'finalize_settlement', lambda owner, nid, **kwargs: settled.append((owner, nid)))
    monkeypatch.setattr(service, 'notify_final_report', lambda owner, nid: notified.append((owner, nid)))
    forbid_journal_decode(monkeypatch)
    service.finalize_pending()
    assert settled == notified == [(items[i][0], items[i][3]) for i in (0, 2)]


def test_rejected_idle_reconciliation_does_not_open_writer(rounds, monkeypatch):
    c, service, items = rounds
    owner, _, _, nid, _ = items[0]
    with c.transaction() as (_, state):
        state['nodes'][nid].update(finalization_pending=True, report_error='original-error')
    writers = []
    connect = c.connect
    def traced():
        db = connect(); return observe(db, lambda sql: writers.append(sql) if 'pg_advisory_xact_lock' in sql else None)
    monkeypatch.setattr(c, 'connect', traced)
    assert service.reconcile_idle_settlement(owner, nid) is False
    assert writers == []
    saved = c.snapshot(owner)['nodes'][0]
    assert saved['finalization_pending'] and saved['report_error'] == 'original-error'


def test_split_preserves_parent_history_without_copying_it(rounds):
    c, _, items = rounds
    owner, _, _, nid, _ = items[0]
    class OriginalHistory(dict):
        def __deepcopy__(self, memo):
            raise AssertionError('split must not copy then discard parent history')
    with c.transaction() as (db, state):
        node = state['nodes'][nid]
        original = copy.deepcopy(node['case_history'])
        node['case_history'] = OriginalHistory(original)
        result = c._split(db, state, owner, node, [{'key': 'child', 'title': 'Child', 'scope': 'Original sub-scope'}])
        child = state['nodes'][result['child_ids'][0]]
        assert node['case_history'] == original and child['case_history'] == {}
        assert child['outcome_history'] == [] and child['result'] == 'not_run'
        # The sentinel covers split; persistence may copy the explicit replacement.
        node['case_history'] = original


def test_dispatch_reuses_owner_snapshot_for_continuation_and_cross_task_observation(rounds, monkeypatch):
    from api_test_tool.module_dispatch import dispatch_view
    c, _, items = rounds
    owner, pid, tid, nid, _ = items[0]
    target = items[1]
    with c.transaction() as (_, state):
        state['tasks'][tid]['session_workflow'] = True
        state['tasks'][target[2]].update(project_id=pid, created=0)
        state['nodes'][nid]['native_handoffs'] = {'event': {
            'id': 'event', 'task_id': tid, 'node_id': nid, 'task_revision': 1, 'created_at': 1,
            'delivery_state': 'pending', 'coordinator_ref': '',
            'continuations': [{'id': 'target', 'task_id': target[2], 'node_id': target[3],
                'kind': 'resume_original_worker', 'delivery_state': 'unknown',
                'claim_arguments': {'holder_id': 'worker', 'dispatch_id': 'target-dispatch',
                                    'executor_ref': 'thread:worker'},
                'task_revision': 1, 'node_revision': 1}]}}
        state['nodes'][target[3]]['dispatch_offer'] = {'holder_id': 'worker',
            'id': 'target-dispatch', 'executor_ref': 'thread:worker', 'state': 'offered'}
    snapshots = []
    snapshot = c.snapshot
    def observed(who, task_id=None, **kwargs):
        snapshots.append(task_id); return snapshot(who, task_id, **kwargs)
    monkeypatch.setattr(c, 'snapshot', observed)
    view = dispatch_view(c, owner, tid)
    assert view['continuation_modules'][0]['source_node_id'] == target[3]
    assert any(row['target_node_id'] == target[3]
        for row in view['coordination_plan']['handoff_observation']['events'])
    assert snapshots.count(None) == 1


def test_progress_read_omits_journals_but_keeps_round_and_account_binding(rounds, monkeypatch):
    from api_test_tool.progress_view import current_progress
    c, _, items = rounds
    owner, pid, tid, nid, _ = items[0]
    project = c.store.get_project(owner, pid)
    before = current_progress(SimpleNamespace(store=c.store, controller=c), owner, project)
    forbid_journal_decode(monkeypatch)
    after = current_progress(SimpleNamespace(store=c.store, controller=c), owner, project)
    assert after == before
    assert after['managed']['tasks'][0]['id'] == tid
    assert after['managed']['nodes'][0]['id'] == nid


def test_work_ready_omits_journal_and_preserves_full_resource_selection(tmp_path, monkeypatch):
    from test_native_work_plan import setup, install
    from test_execution_work_plan import unit
    from test_ui_dependencies import case
    from api_test_tool.execution_work_plan import project_work_candidates
    c, owner, project, _, tid = setup(tmp_path, accounts=1, modules=1)
    service = ManagedService(c, STATIC)
    node = c.snapshot(owner, tid)['nodes'][0]
    aid = c.snapshot(owner)['accounts'][0]['id']
    record, work = install(c, owner, project, node['id'], [unit('read', ['A'], [aid])], [case('A', [])])
    candidate = project_work_candidates({'checkpoint': {'work_plan': work}}, record)[0]
    token = {k: candidate[k] for k in ('work_unit_id', 'plan_revision', 'requirements_digest')}
    with c.transaction() as (_, state):
        state['nodes'][node['id']]['case_history'] = {'1': {'cases': [{'actual': JOURNAL + 'x' * 1000000}]}}
    forbid_journal_decode(monkeypatch)
    result = NativeExecution(service.direct).work_ready(owner, {'task_id': tid, 'node_id': node['id'],
        'holder_id': 'worker', 'arguments': {'work_token': token}})
    assert result['stage_ready'] and result['account_ids'] == [aid]
    assert result['runnable_case_ids'] == ['A'] and result['required_context_count'] == 1


@pytest.mark.parametrize('mode', ['report_pending', 'publish_saved'])
def test_finish_publication_reads_do_not_materialize_journals(tmp_path, monkeypatch, mode):
    from test_native_finalization import prepare, browser_environment
    from api_test_tool import native_execution
    c, service, owner, _, tid, _ = prepare(tmp_path)
    claim = service.direct.call(owner, {'action': 'claim', 'task_id': tid, 'holder_id': 'original',
        'arguments': {'browser_environment': browser_environment('original', True)}})
    with c.transaction() as (_, state):
        state['nodes'][claim['node_id']]['case_history'] = {'1': {'cases': [{'actual': JOURNAL + 'x' * 1000000}]}}
    materialized = []
    def observed(raw):
        if JOURNAL in raw: materialized.append(len(raw))
        return json.loads(raw)
    monkeypatch.setattr(native_execution, 'json', SimpleNamespace(loads=observed), raising=False)
    monkeypatch.setattr(service, 'reconcile_idle_settlement', lambda *args: False)
    monkeypatch.setattr('api_test_tool.wecom.WeCom.auto_report', lambda *args: {'status': 'disabled'})
    result = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original',
        'lease_id': claim['lease_id'], 'reason': 'Own browser actually closed',
        'arguments': {'browser_stopped': True, mode: True}})
    assert result['released'] and not c.snapshot(owner)['leases']
    assert not materialized


def test_active_count_uses_current_leases_without_decoding_case_history(rounds, monkeypatch):
    c, _, items = rounds
    with c.transaction() as (_, state):
        state['leases'] = {
            'ordinary': {'node_id': items[0][3]},
            'held': {'node_id': items[1][3], 'resource_hold': True, 'executor_stopped': False},
            'stopped-hold': {'node_id': items[2][3], 'resource_hold': True, 'executor_stopped': True},
            'stopped-without-hold': {'node_id': items[0][3], 'executor_stopped': True},
        }
    with monkeypatch.context() as guard:
        forbid_journal_decode(guard)
        assert c.active_count() == 3
    with c.transaction() as (_, state):
        state['leases']['held']['executor_stopped'] = True
    forbid_journal_decode(monkeypatch)
    assert c.active_count() == 2
