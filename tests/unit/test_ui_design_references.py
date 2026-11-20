"""Historical scope travels as design, never as another round's evidence."""
import copy
import pytest
from api_test_tool import ui_records
from test_native_scheduler import setup


def sources(tmp_path):
    c, owner, current, clock, tid = setup(tmp_path, modules=1)
    attachments = [{'id': 'doc', 'sha256': 'a' * 64, 'filename': 'scope.docx'}]
    current = c.store.update_project(owner, current['id'], {'ui_requirement_attachments': attachments})
    old = c.store.create_project(owner, 'older scope', 'old.md', 'original scope')
    old = c.store.update_project(owner, old['id'], {'test_kind': 'ui',
        'ui_target_url': 'https://test.example/older', 'ui_requirement_attachments': attachments})
    clock[0] = 900
    prior = c.create_task(owner, {'project_id': old['id'],
        'request_id': 'old', 'goal': 'original scope', 'execution_route': 'native_browser',
        'modules': [{'key': 'm0', 'title': 'm0', 'requirements': []}]})
    with c.transaction() as (_, state):
        state['tasks'][prior['task_id']]['account_project_id'] = current['id']
    clock[0] = 1000
    cases = [{'case_id': 'old-%s' % i, 'scenario': 'independent input %s' % i,
              'steps': 'Open form and submit explicit value', 'expected': 'documented result',
              'status': 'passed', 'actual': 'historical observation', 'conclusion': 'historical pass',
              'account_scope': 'single_account', 'checkpoints': [{'id': 'check', 'title': 'observe',
                  'kind': 'browser', 'expected': 'expected', 'status': 'passed', 'actual': 'old secret observation',
                  'verification_mode': 'executed', 'evidence': ['private historical evidence']}]} for i in range(205)]
    # Store real record shapes directly to isolate this read-only path from save validation.
    from uuid import uuid4
    eid = str(uuid4())
    record = {'id': eid, 'revision': 8, 'cases': cases, 'assets': [], 'coverage': []}
    ui_records.root_for(c.store, owner, old['id'], eid).mkdir(parents=True)
    c.store._write(ui_records.root_for(c.store, owner, old['id'], eid) / 'cases.json', record)
    old = c.store.update_project(owner, old['id'], {'ui_execution_id': eid,
        'ui_progress_record': {'counts': {'passed': 205}, 'revision': 8}})
    return c, owner, current, old, record


def test_reference_pages_preserve_all_designs_without_old_results(tmp_path):
    from api_test_tool import ui_design_references as refs
    c, owner, current, old, original = sources(tmp_path)
    before = copy.deepcopy(c.store.get_project(owner, current['id']))
    found = refs.catalog(c, owner, current)
    assert [x['project_id'] for x in found] == [old['id']]
    assert found[0]['case_count'] == 205
    first = refs.read(c, owner, current, old['id'], limit=200)
    second = refs.read(c, owner, current, old['id'], offset=first['next_offset'], limit=200)
    assert first['total'] == 205 and len(first['cases']) == 200 and len(second['cases']) == 5
    case = first['cases'][0]
    assert case['source_case_id'] == 'old-0' and case['expected'] == 'documented result'
    assert not {'status', 'actual', 'conclusion', 'evidence', 'executed_at'} & case.keys()
    assert not {'status', 'actual', 'evidence', 'correlation'} & case['checkpoints'][0].keys()
    assert c.store.get_project(owner, current['id']) == before
    assert ui_records.load(c.store, owner, old['id'], old['ui_execution_id']) == original


@pytest.mark.parametrize('change', ['document', 'origin', 'account_project', 'deleted', 'current_round', 'owner'])
def test_unrelated_or_current_records_are_not_history(tmp_path, change):
    from api_test_tool import ui_design_references as refs
    c, owner, current, old, _ = sources(tmp_path)
    if change == 'document':
        c.store.update_project(owner, old['id'], {'ui_requirement_attachments': [{'sha256': 'b' * 64}]})
    elif change == 'origin':
        c.store.update_project(owner, old['id'], {'ui_target_url': 'https://unrelated.example'})
    elif change == 'deleted':
        c.store.recycle_project(owner, old['id'])
    elif change == 'owner':
        owner = c.store.session(None)[0]['id']
    else:
        with c.transaction() as (_, state):
            task = next(t for t in state['tasks'].values() if t['project_id'] == old['id'])
            if change == 'account_project': task['account_project_id'] = 'foreign'
            else: task['created'] = 1001
    assert refs.catalog(c, owner, current) == []
    with pytest.raises((ValueError, FileNotFoundError)):
        refs.read(c, owner, current, old['id'])


def test_dispatch_packet_carries_readable_sources_not_seeded_results(tmp_path):
    from api_test_tool.module_dispatch import dispatch_view
    c, owner, current, old, _ = sources(tmp_path)
    task = next(t for t in c.snapshot(owner)['tasks'] if t['project_id'] == current['id'])
    packet = dispatch_view(c, owner, task['id'])['modules'][0]['worker_packet']
    assert packet['design_references'][0]['project_id'] == old['id']
    assert packet['design_references'][0]['read']['arguments']['project_id'] == current['id']
    assert 'ui_execution_id' not in c.store.get_project(owner, current['id'])


from test_ui_dependencies import workspace


def test_mcp_reference_route_preserves_source_authority(workspace):
    client, store, owner, pid, call = workspace
    context = call('context').json()
    assert context['design_references'] == []
    document = call('document').json()
    assert document['design_references'] == []
    response = call('ui_design_reference', source_project_id=pid)
    assert response.status_code == 400
    assert '历史设计' in response.json()['detail']


def test_report_scoped_connection_cannot_discover_or_read_other_session_designs(workspace):
    client, store, owner, pid, call = workspace
    other = store.create_project(owner, 'unshared prior round', 'prior.md', 'unshared material')
    store.update_project(owner, other['id'], {'test_kind': 'ui'})
    from api_test_tool.mcp_access import MCPAccess
    access = MCPAccess(store)
    pair = access.issue(owner, project_ids=[pid], actor='report-reader')
    token = client.post('/api/mcp/redeem', json={'code': pair['code']}).json()['token']
    def scoped(action, **args):
        return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
            json={'action': action, 'arguments': {'project_id': pid, **args}})
    response = scoped('ui_design_reference', source_project_id=other['id'])
    assert response.status_code == 403
    assert scoped('context').json()['design_references'] == []
    assert scoped('document').json()['design_references'] == []


@pytest.mark.parametrize('field,value', [('ui_requirement_attachments', [{'sha256': 'b' * 64}]),
                                        ('ui_target_url', 'https://another.example/login')])
def test_managed_child_uses_its_own_material_snapshot(tmp_path, field, value):
    from api_test_tool import ui_design_references as refs
    c, owner, current, old, _ = sources(tmp_path)
    task = next(t for t in c.snapshot(owner)['tasks'] if t['project_id'] == old['id'])
    child = c.store.create_project(owner, 'm0', 'managed.md', 'module material', round_parent_id=old['id'])
    child = c.store.update_project(owner, child['id'], {'test_kind': 'ui',
        'managed_task_id': task['id'], 'managed_node_id': 'module', 'managed_parent_project_id': old['id'],
        'ui_execution_id': old['ui_execution_id'], 'ui_requirement_attachments': old['ui_requirement_attachments'],
        'ui_target_url': old['ui_target_url'], field: value})
    assert child['id'] not in [x['project_id'] for x in refs.catalog(c, owner, current)]
    with pytest.raises(ValueError): refs.read(c, owner, current, child['id'])
