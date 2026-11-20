"""Service integration of held resources and final reports, without business I/O."""
from api_test_tool import ui_finalization, ui_records
from test_direct_execution import setup, claim_ready


def test_observation_only_does_not_authorize_closing_a_held_browser(tmp_path):
    c, service, owner, project, clock, task = setup(tmp_path)
    ids = claim_ready(c, service, owner, task())
    c.return_account(owner, 'host', {
        'lease_id': ids['lease_id'], 'executor_stopped': True,
        'browser_stopped': False, 'scene_retained': True, 'outcome': 'blocked'})
    result = service.resolve(owner, ids['lease_id'], {
        'evidence': 'An observation only; the retained browser is still needed.'})
    lease = c.snapshot(owner)['leases'][0]
    assert not result['released']
    assert not lease.get('resolution_requested')
    assert not lease.get('resource_release_evidence')
    assert lease['browser_stopped'] is False


def test_unknown_resource_hold_does_not_block_truthful_final_report(tmp_path):
    c, service, owner, project, clock, task = setup(tmp_path)
    saved = ui_records.save_cases(c.store, owner, project['id'], [
        {'case_id': 'uncertain', 'scenario': 'Original operation', 'status': 'not_run'}])
    ids = claim_ready(c, service, owner, task())
    service.host_call({'owner': owner, 'host_id': 'host'}, 'operation_begin', {
        'lease_id': ids['lease_id'], 'operation_id': 'submit', 'action': 'click', 'hash': 'original'})
    project = c.store.get_project(owner, project['id'])
    ui_finalization.begin(service, owner, project, {
        'execution_id': saved['execution_id'], 'request_id': 'original-finish',
        'summary': 'Execution ended with the original submission still unknown.'})
    service.host_call({'owner': owner, 'host_id': 'host'}, 'return_account', {
        'lease_id': ids['lease_id'], 'executor_stopped': True, 'browser_stopped': True,
        'outcome': 'blocked'})
    result = ui_finalization.complete(service, owner, project['id'])
    assert result['phase'] == 'published' and not result['pending']
    assert result['notification']['status'] == 'disabled'
    assert not result['execution_settlement']['released']
    assert result['execution_settlement']['resource_holds']
    assert c.snapshot(owner)['leases'][0]['resource_hold']
    assert ui_records.load(c.store, owner, project['id'], saved['execution_id'])['cases'][0]['status'] == 'not_run'
