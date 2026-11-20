"""Release may preserve an untouched sleeping continuation without ending it."""
import copy
import json

import pytest

from api_test_tool.deployment_activity import activity


@pytest.fixture
def continuation(tmp_path):
    owner = 'a' * 64
    worker = '11111111-1111-4111-8111-111111111111'
    coordinator = '22222222-2222-4222-8222-222222222222'
    original = {'holder_id': 'holder', 'executor_ref': worker, 'coordinator_ref': coordinator,
                'dispatch_id': 'original', 'receipt_source': 'executor_claim',
                'received_at': 10, 'last_seen_at': 20, 'exit_acknowledged_at': 20}
    source = {'id': 'source', 'owner': owner, 'task_id': 'task', 'project_id': 'project',
              'record_project_id': 'project', 'record_execution_id': 'execution',
              'native_browser': True, 'state': 'completed', 'revision': 1,
              'native_browser_stopped': True, 'executor_dispatch': original,
              'native_exit_evidence': {'source': 'executor_reported', 'at': 20},
              'attempts': [{'lease_id': 'old-lease'}], 'record_successor_node_id': 'next'}
    node = {'id': 'next', 'owner': owner, 'task_id': 'task', 'project_id': 'project',
            'record_project_id': 'project', 'record_execution_id': 'execution',
            'native_browser': True, 'state': 'queued', 'revision': 1, 'created': 30,
            'attempts': [], 'queue_sequence': 7, 'result': 'not_run',
            'executor_dispatch': {**original, 'dispatch_id': 'next-dispatch',
                'receipt_source': 'explicit_source_continuation', 'received_at': 30, 'last_seen_at': 30},
            'continuation_source': {'source_task_id': 'task', 'source_node_id': 'source',
                                    'project_id': 'project', 'execution_id': 'execution'},
            'resource_wait': {'end_turn': True, 'resources_available': False,
                'task_id': 'task', 'node_id': 'next', 'coordinator_ref': coordinator,
                'wake_owner': 'coordinator_handoff', 'kind': 'native_environment_unavailable'}}
    node['executor_dispatch'].pop('exit_acknowledged_at')
    state = {'version': 1, 'tasks': {'task': {'id': 'task', 'owner': owner, 'intent': 'run',
                'execution_route': 'native_browser', 'node_ids': ['source', 'next']}},
             'nodes': {'source': source, 'next': node}, 'leases': {}, 'direct_settlements': {}}
    directory = tmp_path / 'sessions' / owner / 'projects' / 'project'
    directory.mkdir(parents=True)
    (directory / 'metadata.json').write_text(json.dumps({'id': 'project'}))
    (directory / 'report.json').write_text(json.dumps({'cases': [{'case_id': 'C1', 'status': 'failed'}]}))
    return tmp_path, state, source, node


def probe(postgres_database, fixture, history=()):
    root, state, _, _ = fixture
    postgres_database.replace_state(root, state, history)
    stored = postgres_database.contents(root)
    before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
    counts = activity(root)
    assert postgres_database.contents(root) == stored
    assert {path: path.read_bytes() for path in before} == before
    return counts


def test_never_claimed_formal_continuation_is_idle_without_cancelling_or_writing(postgres_database, continuation):
    before = copy.deepcopy(continuation[1])
    assert probe(postgres_database, continuation) == {'rounds': 0, 'channels': 0, 'finalizations': 0, 'acknowledgements': 0}
    assert continuation[1] == before


@pytest.mark.parametrize('change', [
    'ordinary_queue', 'claimed', 'holder', 'attempt', 'environment', 'environment_keys',
    'environment_lifecycle', 'claim_pending', 'lease', 'source_lease', 'source_not_completed',
    'source_browser_unknown', 'source_exit_missing', 'source_exit_after_creation',
    'source_pending_report', 'target_pending_report', 'source_pending_control', 'pending_control',
    'wrong_source', 'wrong_source_task', 'wrong_successor', 'wrong_record', 'wrong_owner',
    'wrong_holder', 'wrong_thread', 'wrong_coordinator', 'same_dispatch', 'missing_wait',
    'wait_not_end_turn', 'resources_available', 'wrong_wait_node', 'new_offer',
    'source_holder', 'source_claim_pending', 'source_report_error', 'target_report_error',
    'previous_claim', 'unsupported_route', 'source_exit_evidence_missing',
    'missing_created', 'invalid_created', 'source_invalid_exit', 'source_wrong_exit_evidence',
    'source_wrong_thread', 'missing_wait_coordinator', 'source_not_in_task',
    'source_foreign_parent', 'node_context', 'source_unknown_control', 'reservation',
])
def test_missing_or_conflicting_idle_proof_keeps_round_protected(postgres_database, continuation, change):
    _, state, source, node = continuation
    if change == 'ordinary_queue': node.pop('continuation_source')
    elif change == 'claimed': node['executor_dispatch']['receipt_source'] = 'executor_claim'
    elif change == 'holder': node['direct_holder'] = 'holder'
    elif change == 'attempt': node['attempts'] = [{'lease_id': 'lease'}]
    elif change == 'environment': node['native_environment'] = {'environment_key': 'environment'}
    elif change == 'environment_keys': node['native_environment_keys'] = ['environment']
    elif change == 'environment_lifecycle': node['native_environment_lifecycle'] = {'state': 'ready'}
    elif change == 'claim_pending': node['native_claim_pending'] = True
    elif change in {'lease', 'source_lease'}: state['leases']['lease'] = {'node_id': 'next' if change == 'lease' else 'source'}
    elif change == 'source_not_completed': source['state'] = 'blocked'
    elif change == 'source_browser_unknown': source.pop('native_browser_stopped')
    elif change == 'source_exit_missing': source['executor_dispatch'].pop('exit_acknowledged_at')
    elif change == 'source_exit_after_creation': source['executor_dispatch']['exit_acknowledged_at'] = 40
    elif change == 'source_pending_report': source['native_report_pending'] = {'lease_id': 'old-lease'}
    elif change == 'target_pending_report': node['finalization_pending'] = True
    elif change in {'source_pending_control', 'pending_control'}:
        (source if change == 'source_pending_control' else node)['executor_controls'] = {'stop': {'state': 'pending'}}
    elif change == 'wrong_source': node['continuation_source']['source_node_id'] = 'missing'
    elif change == 'wrong_source_task': node['continuation_source']['source_task_id'] = 'other'
    elif change == 'wrong_successor': source['record_successor_node_id'] = 'other'
    elif change == 'wrong_record': node['record_execution_id'] = 'other'
    elif change == 'wrong_owner': source['owner'] = 'b' * 64
    elif change == 'wrong_holder': node['executor_dispatch']['holder_id'] = 'other'
    elif change == 'wrong_thread': node['executor_dispatch']['executor_ref'] = 'other'
    elif change == 'wrong_coordinator': node['executor_dispatch']['coordinator_ref'] = 'other'
    elif change == 'same_dispatch': node['executor_dispatch']['dispatch_id'] = 'original'
    elif change == 'missing_wait': node.pop('resource_wait')
    elif change == 'wait_not_end_turn': node['resource_wait']['end_turn'] = False
    elif change == 'resources_available': node['resource_wait']['resources_available'] = True
    elif change == 'wrong_wait_node': node['resource_wait']['node_id'] = 'other'
    elif change == 'new_offer': node['dispatch_offer'] = {'state': 'offered'}
    elif change == 'source_holder': source['direct_holder'] = 'holder'
    elif change == 'source_claim_pending': source['native_claim_pending'] = True
    elif change == 'source_report_error': source['report_error'] = 'unknown'
    elif change == 'target_report_error': node['report_error'] = 'unknown'
    elif change == 'previous_claim': node['executor_dispatch_history'] = [{'receipt_source': 'executor_claim'}]
    elif change == 'unsupported_route': state['tasks']['task']['execution_route'] = 'local_browser'
    elif change == 'source_exit_evidence_missing': source.pop('native_exit_evidence')
    elif change == 'missing_created': node.pop('created')
    elif change == 'invalid_created': node['created'] = float('inf')
    elif change == 'source_invalid_exit': source['executor_dispatch']['exit_acknowledged_at'] = True
    elif change == 'source_wrong_exit_evidence': source['native_exit_evidence']['source'] = 'heartbeat_timeout'
    elif change == 'source_wrong_thread': source['executor_dispatch']['executor_ref'] = 'different'
    elif change == 'missing_wait_coordinator': node['resource_wait'].pop('coordinator_ref')
    elif change == 'source_not_in_task': state['tasks']['task']['node_ids'].remove('source')
    elif change == 'source_foreign_parent': source['parent_id'] = 'other'
    elif change == 'node_context': node['native_context_binding'] = {'context_id': 'actual'}
    elif change == 'source_unknown_control': source['executor_controls'] = {'unknown': {'state': 'unknown'}}
    elif change == 'reservation': node['reservation'] = {'accounts': ['account']}
    assert probe(postgres_database, continuation)['rounds'] == 1


@pytest.mark.parametrize('delivery_state', ['pending', 'sending', 'unknown', 'sent', 'blocked', 'unbound'])
@pytest.mark.parametrize('target', ['source', 'next'])
def test_unconfirmed_handoff_anywhere_in_state_preserves_protection(postgres_database, continuation, delivery_state, target):
    _, state, _, _ = continuation
    state['nodes']['event-owner'] = {'id': 'event-owner', 'owner': 'a' * 64,
        'project_id': 'project', 'task_id': 'task', 'state': 'completed',
        'native_handoffs': {'release': {'node_id': 'event-owner', 'delivery_state': 'received',
            'continuations': [{'node_id': target, 'delivery_state': delivery_state}]}}}
    assert probe(postgres_database, continuation)['rounds'] == 1


@pytest.mark.parametrize('kind,status', [('operations', 'pending'), ('operations', 'unknown'),
    ('direct_commands', 'queued'), ('direct_commands', 'running'), ('direct_commands', 'unknown')])
@pytest.mark.parametrize('target', ['source', 'next', None])
def test_unsettled_action_metadata_still_blocks_without_loading_results(postgres_database, continuation, kind, status, target):
    assert probe(postgres_database, continuation, [(kind, {'node_id': target, 'state': status})])['rounds'] == 1


@pytest.mark.parametrize('command_state', ['completed', 'blocked', 'confirmed', 'not_sent', 'cancelled'])
def test_settled_history_and_obsolete_handoff_do_not_make_sleeping_continuation_active(postgres_database, continuation, command_state):
    _, _, source, node = continuation
    source['native_handoffs'] = {'release': {'node_id': 'source', 'delivery_state': 'obsolete',
        'continuations': [{'node_id': 'next', 'delivery_state': 'obsolete'}]}}
    node['executor_dispatch']['executor_ref'] = 'thread:' + node['executor_dispatch']['executor_ref']
    assert probe(postgres_database, continuation, [('operations', {'node_id': 'source', 'state': 'confirmed'}),
        ('direct_commands', {'node_id': 'next', 'state': command_state})])['rounds'] == 0


@pytest.mark.parametrize('change', ['missing_notice_target', 'different_notice_target', 'actual_claim_receipt'])
def test_inconsistent_handoff_evidence_cannot_prove_successor_never_claimed(postgres_database, continuation, change):
    _, _, source, _ = continuation
    notice = {'node_id': 'next', 'delivery_state': 'unknown', 'claim_arguments': {'node_id': 'next'}}
    if change == 'missing_notice_target': notice.pop('node_id')
    elif change == 'different_notice_target': notice['node_id'] = 'other'
    elif change == 'actual_claim_receipt': notice.update(delivery_state='received', claim_received_at=35)
    source['native_handoffs'] = {'release': {'node_id': 'source', 'delivery_state': 'received',
        'continuations': [notice]}}
    assert probe(postgres_database, continuation)['rounds'] == 1


def test_unknown_legacy_inline_operation_still_blocks(postgres_database, continuation):
    continuation[1]['operations'] = {'write': {'node_id': 'source', 'state': 'unknown'}}
    assert probe(postgres_database, continuation)['rounds'] == 1


def test_other_live_module_still_protects_same_round(postgres_database, continuation):
    _, state, source, _ = continuation
    state['nodes']['running'] = {**source, 'id': 'running', 'state': 'running'}
    assert probe(postgres_database, continuation)['rounds'] == 1


@pytest.mark.parametrize('binding_source', ['attempt', 'settlement', 'outbox'])
def test_legacy_unknown_command_proven_to_belong_to_other_round_does_not_block(postgres_database, continuation, binding_source):
    _, state, source, _ = continuation
    other = {**copy.deepcopy(source), 'id': 'historical', 'task_id': 'old-task', 'attempts': []}
    other.pop('record_successor_node_id')
    state['nodes']['historical'] = other
    state['tasks']['old-task'] = {**state['tasks']['task'], 'id': 'old-task',
        'execution_route': 'local_browser', 'node_ids': ['historical']}
    if binding_source == 'attempt': other['attempts'] = [{'lease_id': 'foreign-lease'}]
    elif binding_source == 'settlement': state['direct_settlements']['foreign-lease'] = {
        'node_id': 'historical', 'ack_required': False}
    elif binding_source == 'outbox': state['outbox'] = {'start': {
        'lease_id': 'foreign-lease', 'node_id': 'historical', 'status': 'acknowledged'}}
    assert probe(postgres_database, continuation, [('direct_commands', {'lease_id': 'foreign-lease', 'state': 'unknown'})])['rounds'] == 0


@pytest.mark.parametrize('change', ['related_lease', 'conflicting_lease', 'unknown_lease', 'mismatched_explicit_node'])
def test_unknown_command_cannot_be_discarded_when_lease_binding_is_related_or_uncertain(postgres_database, continuation, change):
    _, state, source, _ = continuation
    command = {'lease_id': 'old-lease', 'state': 'unknown'}
    if change == 'conflicting_lease': state['direct_settlements']['old-lease'] = {
        'node_id': 'different', 'ack_required': False}
    elif change == 'unknown_lease': command['lease_id'] = 'unmapped'
    elif change == 'mismatched_explicit_node': command['node_id'] = 'different'
    assert probe(postgres_database, continuation, [('direct_commands', command)])['rounds'] == 1
