"""PostgreSQL-only diagnostics. No runner, browser, model or external calls."""
from unittest.mock import patch

import pytest

from api_test_tool.managed_service import ManagedService
from api_test_tool.orchestration import Controller
from api_test_tool.database import begin_write
from api_test_tool.orchestration_storage import read_metadata
from api_test_tool.web_storage import Store
from pg_support import observe


def environment(tmp_path):
    store = Store(tmp_path)
    session, _ = store.session(None)
    owner = session['id']
    clock = [1000.0]
    c = Controller(store, lambda: clock[0])
    c.register_host(owner, 'host', enforcement_evidence=dict(network_isolation=1,
        credential_isolation=1, tool_gate=1, browser_context_isolation=1, version='fixture'),
        browser_slots=3, model_slots=1)
    return c, ManagedService(c, tmp_path), owner, clock


def traced(c, statements):
    original = c.connect
    def connect():
        return observe(original(), statements.append)
    return patch.object(c, 'connect', connect)


def test_idle_heartbeat_keeps_scheduler_but_removes_empty_writers(tmp_path):
    c, service, owner, clock = environment(tmp_path)
    auth = dict(owner=owner, host_id='host')
    args = dict(browser_slots=3, model_slots=1)
    service.host_call(auth, 'heartbeat', args)
    clock[0] += 3
    sql = []
    with traced(c, sql):
        result = service.host_call(auth, 'heartbeat', args)
    assert result['leases'] == [] and result['events'] == []
    assert sum('pg_advisory_xact_lock' in s for s in sql) == 2
    assert any('FROM state_sections' in s for s in sql)
    assert not any('state_case_history' in s for s in sql)
    assert not any(s.startswith(('UPDATE state_sections', 'UPDATE state_history')) for s in sql)


def test_empty_event_read_does_not_wait_for_writer(tmp_path):
    c, _, owner, _ = environment(tmp_path)
    with c.connect() as writer:
        begin_write(writer)
        with traced(c, []):
            assert c.pending_events(owner, 'host') == []
            with pytest.raises(PermissionError):
                c.pending_events('another-owner', 'host')


def test_heartbeat_keeps_original_immediate_scheduling(tmp_path):
    c, _, owner, clock = environment(tmp_path)
    with patch.object(c, 'schedule', wraps=c.schedule) as schedule:
        c.host_heartbeat(owner, 'host', 3, 1)
        assert schedule.call_count == 1
        clock[0] += 3
        c.host_heartbeat(owner, 'host', 3, 1)
        assert schedule.call_count == 2
        c.host_heartbeat(owner, 'host', 4, 1)
        assert schedule.call_count == 3
        clock[0] += 61
        c.host_heartbeat(owner, 'host', 4, 1)
        assert schedule.call_count == 4


def test_heartbeat_preserves_unrelated_state_and_rolls_back(tmp_path):
    c, _, owner, _ = environment(tmp_path)
    with c.transaction() as (_, state):
        state['diagnostic_history'] = {'unchanged': 'x' * 100000}
    c.host_heartbeat(owner, 'host', 3, 1)
    with c.connect() as db:
        before = read_metadata(db)
    with pytest.raises(PermissionError):
        c.host_heartbeat('another-owner', 'host', 9, 9)
    with c.connect() as db:
        after = read_metadata(db)
    assert after == before
    assert after['diagnostic_history'] == {'unchanged': 'x' * 100000}


def test_partial_write_failure_never_commits(tmp_path):
    c, _, owner, _ = environment(tmp_path)
    with pytest.raises(RuntimeError):
        with c.heartbeat_transaction() as state:
            state['runners']['host']['browser_slots'] = 99
            raise RuntimeError('abort before commit')
    assert c.snapshot(owner)['runners'][0]['browser_slots'] == 3


def test_empty_hold_scan_does_not_wait_for_writer(tmp_path):
    from api_test_tool.resource_holds import settle
    c, _, _, _ = environment(tmp_path)
    with c.connect() as writer:
        begin_write(writer)
        with traced(c, []):
            settle(c)


def test_progress_updates_only_original_host_lease(tmp_path):
    c, _, owner, clock = environment(tmp_path)
    with c.transaction() as (_, state):
        state['leases'] = {'mine': {'runner_id': 'host', 'progress_sequence': 1},
                           'foreign': {'runner_id': 'other', 'progress_sequence': 1}}
    with patch.object(c, 'schedule', return_value=[]):
        c.host_heartbeat(owner, 'host', 3, 1, {'mine': 2, 'foreign': 2})
    with c.connect() as db:
        from api_test_tool.orchestration_storage import read_sections
        leases = read_sections(db, ('leases',))['leases']
    assert leases['mine']['progress_sequence'] == 2
    assert leases['mine']['progress_at'] == clock[0]
    assert leases['foreign'] == {'runner_id': 'other', 'progress_sequence': 1}
