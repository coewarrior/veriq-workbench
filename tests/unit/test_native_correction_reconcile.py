"""Synthetic separate correction receipts: no network, browser, lease or save replay."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from test_native_result_continuity import client_module, prepared_client


def fixture_evidence(m, tmp_path):
    client, binding = prepared_client(m, tmp_path)
    binding.update(revision=31, account_ids=['account'])
    m.write_private_json(tmp_path / 'binding.json', binding)
    observation = {'case_id': 'C1', 'status': 'passed', 'checks': [
        {'name': 'original check', 'expected': 'yes', 'observed': 'yes', 'ok': True}]}
    payload = {'cases': [{'case_id': 'C1', 'status': 'passed', 'actual': m.observation_actual(observation)}]}
    old = tmp_path / 'original.json'
    client.call = lambda *a: (_ for _ in ()).throw(m.ClientHTTPError(500, 'synthetic'))
    with pytest.raises(m.ClientHTTPError):
        client.native_record(tmp_path / 'binding.json', payload, old)
    rid = '123-abc'
    m.write_private_json(tmp_path / f'observation-inbox-{rid}.json', observation)
    m.write_private_json(tmp_path / f'native-receiver-response-{rid}.json', {
        'request_id': rid, 'state': 'unknown', 'saved': False, 'record_receipt_file': str(old)})
    m.write_private_json(tmp_path / 'observation-pending.json', {
        **payload['cases'][0], 'request_id': rid, 'receipt_file': str(old)})
    for name in ('native-last-observation.json', 'native-observation-awaiting.json'):
        m.write_private_json(tmp_path / name, {'request_id': rid})
    binding['revision'] = 34
    m.write_private_json(tmp_path / 'binding.json', binding)
    correction = tmp_path / 'correction.json'
    corrected = copy.deepcopy(payload)
    corrected['cases'][0]['steps'] = 'Preserved original steps, submitted separately'
    client.call = lambda *a: {'execution_id': 'execution', 'revision': 35,
                              'saved_cases': copy.deepcopy(corrected['cases'])}
    client.native_record(tmp_path / 'binding.json', corrected, correction)
    record = {'id': 'execution', 'revision': 35, 'cases': copy.deepcopy(corrected['cases'])}
    calls = []
    def read(tool, args):
        calls.append(args)
        assert args['action'] == 'record' and args['record_action'] == 'record'
        return copy.deepcopy(record)
    client.call = read
    return client, rid, correction, record, calls


def test_separate_correction_resolves_observation_without_rewriting_unknown(client_module, tmp_path):
    m = client_module
    client, rid, correction, record, calls = fixture_evidence(m, tmp_path)
    immutable = {p: p.read_bytes() for p in tmp_path.glob('*.json') if p.name != 'observation-pending.json'}
    result = m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)
    assert result['resolution'] == 'corrected_by_saved_receipt'
    assert len(calls) == 1 and not (tmp_path / 'observation-pending.json').exists()
    assert all(p.read_bytes() == content for p, content in immutable.items())
    binding = json.loads((tmp_path / 'binding.json').read_text())
    assert m.native_publication_ready(tmp_path / 'binding.json', binding)
    m.write_private_json(tmp_path / 'native-explicit-exit.json', {
        'binding': binding, 'exit': {'browser_stopped': True, 'reason': 'real fixture exit'}})
    assert 'save_unconfirmed' not in m.native_observed_closeout_arguments(tmp_path / 'binding.json')['arguments']
    assert m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)['reused_receipt']
    assert len(calls) == 1
    record['revision'] = 36  # already confirmed proof needs no new HTTP
    binding['revision'] = 36
    m.write_private_json(tmp_path / 'binding.json', binding)
    assert m.native_publication_ready(tmp_path / 'binding.json', binding)
    assert m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)['reused_receipt']
    binding['revision'] = 34
    m.write_private_json(tmp_path / 'binding.json', binding)
    assert not m.native_publication_ready(tmp_path / 'binding.json', binding)
    with pytest.raises(ValueError):
        m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)
    assert len(calls) == 1


@pytest.mark.parametrize('difference', ['binding', 'field', 'revision', 'fingerprint', 'time', 'pending',
                                       'record_revision', 'record_field', 'generation', 'account'])
def test_correction_rejects_mismatches_without_clearing_evidence(client_module, tmp_path, difference):
    m = client_module
    client, rid, correction, record, calls = fixture_evidence(m, tmp_path)
    data = json.loads(correction.read_text())
    if difference == 'binding': data['binding']['node_id'] = 'other'
    if difference == 'field':
        data['payload']['cases'][0]['actual'] = 'different'
        data['request']['arguments']['cases'][0]['actual'] = 'different'
        data['result']['saved_cases'][0]['actual'] = 'different'
    if difference == 'revision': data['result']['revision'] = 36
    if difference == 'fingerprint': data['fingerprint'] = 'forged'
    if difference == 'time': data['started_at'] = '2000-01-01T00:00:00+00:00'
    if difference in {'binding', 'field'}:
        data['fingerprint'] = hashlib.sha256(json.dumps({k:data[k] for k in
            ('workspace_url', 'binding', 'payload')}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    m.write_private_json(correction, data)
    if difference == 'pending':
        marker = json.loads((tmp_path / 'observation-pending.json').read_text())
        marker['request_id'] = '456-def'
        m.write_private_json(tmp_path / 'observation-pending.json', marker)
    if difference == 'record_revision': record['revision'] = 36
    if difference == 'record_field': record['cases'][0]['steps'] = 'different'
    if difference in {'generation', 'account'}:
        # Generation/account changes must invalidate an already confirmed association.
        m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)
        b = json.loads((tmp_path / 'binding.json').read_text())
        b['dispatch_id' if difference == 'generation' else 'account_ids'] = 'other'
        m.write_private_json(tmp_path / 'binding.json', b)
    before = {p:p.read_bytes() for p in tmp_path.glob('*.json')}
    with pytest.raises(ValueError):
        m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)
    assert all(p.read_bytes() == content for p, content in before.items())
    assert len(calls) <= 1
    b = json.loads((tmp_path / 'binding.json').read_text())
    assert not m.native_publication_ready(tmp_path / 'binding.json', b)


@pytest.mark.parametrize('changed', ['original', 'correction', 'observation'])
def test_confirmed_evidence_hash_changes_never_trigger_another_read(client_module, tmp_path, changed):
    m = client_module
    client, rid, correction, record, calls = fixture_evidence(m, tmp_path)
    result = m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)
    proof = json.loads(Path(result['correction_receipt_file']).read_text())
    path = Path(proof['evidence'][changed]['file'])
    path.write_text(path.read_text() + '\n')  # same JSON, different immutable source bytes
    binding = json.loads((tmp_path / 'binding.json').read_text())
    assert not m.native_publication_ready(tmp_path / 'binding.json', binding)
    with pytest.raises(ValueError):
        m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)
    assert len(calls) == 1


def test_missing_marker_and_interrupted_marker_cleanup_are_idempotent(client_module, tmp_path):
    m = client_module
    client, rid, correction, record, calls = fixture_evidence(m, tmp_path)
    marker_file = tmp_path / 'observation-pending.json'
    marker = json.loads(marker_file.read_text())
    # Simulate durable proof written immediately before own-marker cleanup.
    result = m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)
    m.write_private_json(marker_file, marker)
    assert m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)['reused_receipt']
    assert not marker_file.exists() and len(calls) == 1
    Path(result['correction_receipt_file']).unlink()  # isolated fresh scenario with no marker
    assert not m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)['reused_receipt']
    assert len(calls) == 2


def test_live_receiver_keeps_exclusive_reconciliation_ownership(client_module, tmp_path):
    m = client_module
    client, rid, correction, record, calls = fixture_evidence(m, tmp_path)
    with m.batch_lock(tmp_path / 'native-receiver.json'):
        with pytest.raises(BlockingIOError):
            m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)
    assert not calls and (tmp_path / 'observation-pending.json').exists()


def test_duplicate_pointers_reuse_proof_only_inside_each_operation(client_module, tmp_path, monkeypatch):
    m = client_module
    client, rid, correction, record, calls = fixture_evidence(m, tmp_path)
    result = m.reconcile_native_observation_correction(client, tmp_path / 'binding.json', rid, correction)
    proof_path = Path(result['correction_receipt_file'])
    reads = []
    read = m.read_utf8
    def observe(path):
        if Path(path) == proof_path:
            reads.append(path)
        return read(path)
    monkeypatch.setattr(m, 'read_utf8', observe)
    binding = json.loads((tmp_path / 'binding.json').read_text())
    assert m.native_publication_ready(tmp_path / 'binding.json', binding)
    assert len(reads) == 1
    assert m.native_publication_ready(tmp_path / 'binding.json', binding)
    assert len(reads) == 2  # no cache across operations
    m.write_private_json(tmp_path / 'native-explicit-exit.json', {
        'binding': binding, 'exit': {'browser_stopped': True, 'reason': 'fixture exit'}})
    assert 'save_unconfirmed' not in m.native_observed_closeout_arguments(tmp_path / 'binding.json')['arguments']
    assert len(reads) == 3 and len(calls) == 1
