"""Real resume/preparation consumer; external platform calls stay at transport boundary."""
import copy
import json
import pytest

from test_native_lifecycle import mod, lifecycle, inputs, Fake, ExistingRecord, resume_cases

TOKEN = {'work_unit_id': 'ab', 'plan_revision': 2, 'requirements_digest': 'digest'}


def notice(assignment):
    return {'kind': 'resume_original_worker', 'claim_arguments': {
        **{k: assignment[k] for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')},
        'action': 'claim', 'account_ids': ['A', 'B'], 'arguments': {'work_token': TOKEN}}}


@pytest.mark.parametrize('shape', ['nested', 'flat'])
def test_old_assignment_consumes_notice_and_claims_full_stage_without_resaving(lifecycle, tmp_path, shape):
    a, source = inputs()
    a['resume_record'] = {'project_id': 'project', 'execution_id': 'execution'}
    event = notice(a)
    if shape == 'flat':
        event['claim_arguments']['work_token'] = event['claim_arguments'].pop('arguments')['work_token']
    path = tmp_path/'assignment.json'
    lifecycle.write_private_json(path, a)
    class Transport(ExistingRecord):
        def call(self, tool, args):
            if args['action'] == 'context' and not args.get('lease_id'):
                self.calls.append(('stage', args))
                assert args['arguments']['work_token'] == TOKEN
                return {'stage_ready': True, 'work_token': TOKEN, 'account_ids': ['A', 'B'], 'required_context_count': 2}
            if args['action'] == 'claim':
                assert args['arguments']['work_token'] == TOKEN
                assert args['account_ids'] == ['A', 'B']
            return super().call(tool, args)
    client = Transport(a, resume_cases())
    result = lifecycle.native_resume(client, path, tmp_path, event)
    assert result['stage_ready'] and result['next_action'] == 'environment_setup'
    saved = json.loads(path.read_text())
    assert saved['direct_browser']['context_count'] == 2
    ready = lifecycle.prepare_native(client, saved, source, tmp_path, resume=True)
    assert ready['cases'] == resume_cases()
    assert [action for action, _ in client.calls] == ['stage', 'claim', 'context']


@pytest.mark.parametrize('change', ['task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref', 'conflicting_token'])
def test_foreign_or_ambiguous_notice_cannot_mutate_assignment(lifecycle, tmp_path, change):
    a, _ = inputs(); event = notice(a)
    if change == 'conflicting_token':
        event['claim_arguments']['work_token'] = {**TOKEN, 'plan_revision': 1}
    else:
        event['claim_arguments'][change] = 'foreign'
    path = tmp_path/'assignment.json'; lifecycle.write_private_json(path, a)
    before = path.read_bytes(); client = Fake()
    with pytest.raises(ValueError): lifecycle.native_resume(client, path, tmp_path, event)
    assert path.read_bytes() == before and not client.calls


def test_stale_notice_clears_old_ready_receipt_without_replacing_assignment(lifecycle, tmp_path):
    a, _ = inputs(); path = tmp_path/'assignment.json'; lifecycle.write_private_json(path, a)
    lifecycle.write_private_json(tmp_path/'stage-ready.json', {'stage_ready': True})
    class Rejected(Fake):
        def call(self, tool, args): raise ValueError('work_token_stale: 阶段计划已变化')
    with pytest.raises(ValueError, match='work_token_stale'):
        lifecycle.native_resume(Rejected(), path, tmp_path, notice(a))
    assert json.loads(path.read_text()) == a
    assert not (tmp_path/'stage-ready.json').exists()


def test_nested_assignment_prepare_does_not_drop_stage_token(lifecycle, tmp_path):
    a, source = inputs(); a['claim_arguments'] = notice(a)['claim_arguments']
    client = Fake(queued=True)
    lifecycle.prepare_native(client, a, source, tmp_path)
    assert client.calls[0][1]['arguments']['work_token'] == TOKEN


def test_confirmed_claim_rejection_can_resume_but_unknown_cannot_replay(lifecycle, mod, tmp_path):
    a, source = inputs()
    class Rejected(Fake):
        def call(self, tool, args): raise mod.ClientHTTPError(409, 'work_token_missing')
    with pytest.raises(ValueError): lifecycle.prepare_native(Rejected(), a, source, tmp_path)
    state = json.loads((tmp_path/'preparation.json').read_text())
    assert state['claim_outcome'] == 'rejected'
    client = Fake(queued=True)
    assert lifecycle.prepare_native(client, a, source, tmp_path, resume=True)['state'] == 'waiting'
    assert [action for action, _ in client.calls] == ['claim']
    unknown = tmp_path/'unknown'
    with pytest.raises(OSError): lifecycle.prepare_native(Fake(fail='claim'), a, source, unknown)
    client = Fake()
    with pytest.raises(ValueError): lifecycle.prepare_native(client, a, source, unknown, resume=True)
    assert [action for action, _ in client.calls] == ['context']


@pytest.mark.parametrize('duplicate_change', [None, 'shared_peer', 'revoked', 'other_stage', 'accounts', 'stale_notice'])
def test_real_handoff_through_downloaded_resume_preserves_stage_and_record(mod, tmp_path, duplicate_change):
    from test_native_handoff import environment, bind_waiting_thread, consume
    from test_native_work_plan import install, unit, case
    from api_test_tool import ui_records
    c, service, owner, project, _, requests, finish = environment(tmp_path/'server')
    bind_waiting_thread(c, requests)
    aid = c.snapshot(owner)['accounts'][0]['id']; nid = requests[1]['node_id']
    with c.connect() as db:
        from api_test_tool.orchestration_storage import read_metadata_without_history
        state = read_metadata_without_history(db)
    project = service.report_project(owner, state['nodes'][nid], state['tasks'][requests[1]['task_id']])
    record, _ = install(c, owner, project, nid, [unit('execute', ['A'], [aid])], [case('A', [])])
    c.schedule()
    released = service.direct.call(owner, finish)
    event = consume(c, owner, finish, released['handoff'])['continuation']
    original = event['claim_arguments']
    assignment = {k: original[k] for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')}
    assignment.update(workspace_url='http://fixture.test', browser_mode='cua',
                      resume_record={'project_id': project['id'], 'execution_id': record['id']})
    directory = tmp_path/'client'; directory.mkdir(); path = directory/'assignment.json'
    mod.write_private_json(path, assignment)
    class Transport:
        url = 'http://fixture.test'
        def call(self, tool, args):
            assert tool == 'direct_test_session'
            return service.direct.call(owner, args)
    assert mod.native_resume(Transport(), path, directory, event)['stage_ready']
    result = mod.prepare_native(Transport(), json.loads(path.read_text()), {'cases': record['cases']}, directory, resume=True)
    assert result['ready'] and result['execution_id'] == record['id']
    assert ui_records.load(c.store, owner, project['id'], record['id'])['revision'] == record['revision']
    current = next(n for n in c.snapshot(owner)['nodes'] if n['id'] == nid)
    assert current['work_selection']['work_unit_id'] == 'execute'
    lease_id = c.snapshot(owner)['leases'][0]['id']
    if duplicate_change == 'shared_peer':
        with c.transaction() as (_, raw):
            raw['leases'][lease_id]['mode'] = 'shared'
            raw['leases']['peer'] = {**copy.deepcopy(raw['leases'][lease_id]), 'id': 'peer', 'node_id': requests[0]['node_id']}
        assert mod.native_resume(Transport(), path, directory, event)['stage_ready']
        assert len(c.snapshot(owner)['leases']) == 2
    elif duplicate_change:
        from api_test_tool.orchestration import Conflict
        with c.transaction() as (_, raw):
            if duplicate_change == 'revoked': raw['leases'][lease_id]['revoked'] = True
            if duplicate_change == 'other_stage': raw['nodes'][nid]['work_selection']['work_unit_id'] = 'other'
            if duplicate_change == 'accounts': raw['leases'][lease_id]['account_ids'] = []
        if duplicate_change == 'stale_notice': event['claim_arguments']['arguments']['work_token']['plan_revision'] += 1
        with pytest.raises(Conflict): mod.native_resume(Transport(), path, directory, event)
    else:
        assert mod.native_resume(Transport(), path, directory, event)['stage_ready']
        assert c.snapshot(owner)['leases'][0]['id'] == lease_id


@pytest.mark.parametrize('mismatch', [None, 'environment', 'account', 'dispatch', 'settlement', 'record'])
def test_uncertain_reclaim_adopts_only_confirmed_original_request(mod, tmp_path, mismatch):
    from test_native_report_authority import released, browser_environment
    from api_test_tool.orchestration import Conflict
    c, service, owner, args = released(tmp_path/'server')
    source = {'cases': [{'case_id': 'A', 'scenario': 'observed prerequisite', 'steps': 'Open original page',
                         'expected': 'Original observation retained', 'status': 'not_run'},
                        {'case_id': 'B', 'scenario': 'remaining original design', 'steps': 'Read remaining page',
                         'expected': 'Remaining design retained', 'status': 'not_run'}]}
    saved = service.direct.call(owner, {**args, 'arguments': {**args['arguments'], **source}})
    args['arguments']['revision'] = saved['revision']
    identity = {k: args[k] for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')}
    assignment = {**identity, 'workspace_url': 'http://fixture.test', 'browser_mode': 'cua',
                  'claim_arguments': {'browser_environment': browser_environment('new-context', True),
                                      'account_ids': [c.snapshot(owner)['accounts'][0]['id']]}}
    directory = tmp_path/'client'; directory.mkdir()
    previous = {**identity, 'workspace_url': assignment['workspace_url'], 'lease_id': args['lease_id'],
                **{k: args['arguments'][k] for k in ('project_id', 'execution_id', 'revision')},
                'native_context_binding': {'context_id': 'context', 'environment_key': 'old-environment'}}
    mod.write_private_json(directory/'binding.json', previous)
    class Transport:
        url = assignment['workspace_url']
        calls = []
        lose = True
        def call(self, tool, request):
            self.calls.append(copy.deepcopy(request))
            response = service.direct.call(owner, request)
            if request['action'] == 'claim' and self.lose:
                self.lose = False
                raise OSError('Claim committed; response lost')
            return response
    client = Transport()
    with pytest.raises(OSError): mod.prepare_native(client, assignment, source, directory, resume=True)
    assert json.loads((directory/'binding.json').read_text()) == previous
    current_id = c.snapshot(owner)['leases'][0]['id']
    with c.transaction() as (_, raw):
        node = raw['nodes'][args['node_id']]; lease = raw['leases'][current_id]
        if mismatch == 'environment': lease['native_context_binding']['contexts'][0]['context_id'] = 'foreign'
        if mismatch == 'account': lease['account_ids'] = []
        if mismatch == 'dispatch': node['executor_dispatch']['dispatch_id'] = 'foreign'
        if mismatch == 'settlement': raw['direct_settlements'].pop(args['lease_id'])
        if mismatch == 'record': node['record_execution_id'] = 'foreign'
    before = len(client.calls)
    if mismatch:
        with pytest.raises((ValueError, Conflict, PermissionError)):
            mod.prepare_native(client, assignment, source, directory, resume=True)
        assert json.loads((directory/'binding.json').read_text()) == previous
    else:
        ready = mod.prepare_native(client, assignment, source, directory, resume=True)
        assert ready['ready'] and ready['resumed']
        binding = json.loads((directory/'binding.json').read_text())
        assert binding['lease_id'] == current_id != args['lease_id']
        assert binding['previous_bindings'] == [previous]
        assert binding['revision'] == previous['revision']
    assert all(call['action'] == 'context' for call in client.calls[before:])
    assert len(client.calls) - before <= 2


def test_generated_cleanup_rejects_bad_event_before_transport(mod, tmp_path):
    import subprocess
    import sys
    mod.write_private_json(tmp_path/'binding.json', {'workspace_url': 'http://127.0.0.1:1',
        'holder_id': 'h', 'task_id': 't', 'node_id': 'n', 'lease_id': 'l'})
    mod.write_private_json(tmp_path/'events.json', [{'action': 'capability'}])
    result = subprocess.run([sys.executable, mod.__file__, '--url', 'http://127.0.0.1:1',
        '--credential-file', str(tmp_path/'absent-credential.json'), 'native-cleanup',
        '--binding-file', str(tmp_path/'binding.json'), '--events-file', str(tmp_path/'events.json')], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'events[0].command' in result.stdout + result.stderr
    assert '尚未连接' not in result.stdout + result.stderr


@pytest.mark.parametrize('change', ['dispatch', 'missing_stage', 'paused_task', 'paused_node'])
def test_non_stage_resume_still_rejects_changed_server_binding(mod, tmp_path, change):
    from test_native_report_authority import released
    from api_test_tool.orchestration import Conflict
    c, service, owner, args = released(tmp_path/'server')
    identity = {k: args[k] for k in ('task_id','node_id','holder_id','dispatch_id','executor_ref')}
    with c.transaction() as (_, raw):
        node = raw['nodes'][args['node_id']]
        if change == 'dispatch': node['executor_dispatch']['dispatch_id'] = 'new-dispatch'
        if change == 'missing_stage': node.setdefault('checkpoint', {})['work_plan'] = {'plan_revision': 1, 'units': []}
        if change == 'paused_task': raw['tasks'][args['task_id']]['intent'] = 'pause'
        if change == 'paused_node': node['control_intent'] = 'pause'
    directory = tmp_path/'client'; directory.mkdir(); path = directory/'assignment.json'
    mod.write_private_json(path, {**identity, 'workspace_url': 'http://fixture.test', 'browser_mode': 'cua'})
    class Transport:
        url = 'http://fixture.test'
        def call(self, tool, args): return service.direct.call(owner, args)
    with pytest.raises(Conflict):
        mod.native_resume(Transport(), path, directory, {'claim_arguments': {**identity, 'action': 'claim'}})
