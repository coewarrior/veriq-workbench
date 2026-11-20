"""Exercise actual dispatch/claim boundaries; no browser, network or model."""
import importlib.util
import json
from pathlib import Path

import pytest

from api_test_tool.managed_service import ManagedService
from api_test_tool.orchestration import Conflict
from test_native_scheduler import setup
from test_native_contexts import environment

THREAD = '01a17111-5ac7-79d0-9ac8-48eaaddc22b8'
OTHER = '01a17111-6d87-7b83-968e-5f6c2a107a77'
STATIC = Path(__file__).parents[2] / 'api_test_tool' / 'static'


@pytest.mark.parametrize('offered,claimed', [(THREAD, 'thread:' + THREAD), ('thread:' + THREAD, THREAD)])
def test_platform_packet_generates_and_claims_same_real_chat_without_rewriting(tmp_path, offered, claimed):
    c, owner, _, _, tid = setup(tmp_path, modules=2)
    service = ManagedService(c, STATIC)
    node, sibling = c.snapshot(owner)['nodes']
    dispatch = service.direct.call(owner, {'action': 'dispatch', 'task_id': tid,
        'holder_id': 'coordinator', 'request_id': 'dispatch', 'arguments': {'modules': [{
            'node_id': node['id'], 'holder_id': 'worker', 'dispatch_id': 'dispatch-one', 'executor_ref': offered}]}})
    assignment = dispatch['modules'][0]['worker_packet']['assignment']
    assert assignment['executor_ref'] == offered
    spec = importlib.util.spec_from_file_location('identity_client', STATIC / 'api-test-client.py')
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    assignment_file, design = tmp_path / 'assignment.json', tmp_path / 'design.json'
    assignment_file.write_text(json.dumps(assignment))
    design.write_text(json.dumps({'cases': [{'case_id': 'A', 'title': 'Original design',
        'steps': 'Open target', 'expected': 'Original assertion', 'status': 'not_run'}]}))
    before = assignment_file.read_bytes()
    kit = client.native_run_kit(['python3', '/client.py'], assignment_file, design, tmp_path / 'kit', 'https://test.example')
    assert kit['message_arguments']['threadId'] == THREAD
    assert assignment_file.read_bytes() == before
    request = {'action': 'claim', 'task_id': tid, 'node_id': node['id'], 'holder_id': 'worker',
        'dispatch_id': 'dispatch-one', 'executor_ref': claimed,
        'arguments': {'browser_environment': environment('context', True)}}
    with pytest.raises(Conflict, match='另一 Codex'):
        service.direct.call(owner, {**request, 'executor_ref': OTHER})
    accepted = service.direct.call(owner, request)
    assert accepted['lease_id'] and c.snapshot(owner)['leases'][0]['node_id'] == node['id']
    with pytest.raises(Conflict, match='独立 Codex'):
        service.direct.call(owner, {'action': 'dispatch', 'task_id': tid, 'holder_id': 'coordinator',
            'request_id': 'other-module', 'arguments': {'modules': [{
                'node_id': sibling['id'], 'holder_id': 'other-worker', 'dispatch_id': 'dispatch-two',
                'executor_ref': offered}]}})


def test_foreign_and_opaque_executor_identifiers_are_not_equated():
    from api_test_tool.native_identity import same_executor_ref
    assert not same_executor_ref(THREAD, OTHER)
    assert not same_executor_ref('worker', 'thread:worker')
    assert not same_executor_ref(None, None)
    assert same_executor_ref(THREAD.upper(), 'thread:' + THREAD)
