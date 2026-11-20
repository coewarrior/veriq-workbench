"""Offline transport faults: reads recover; lifecycle and uncertain writes never replay."""
import contextlib
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import socket
import ssl
import threading
import time
import urllib.error

import pytest


@pytest.fixture
def module():
    source = Path(__file__).parents[2] / 'api_test_tool/static/api-test-client.py'
    spec = importlib.util.spec_from_file_location('network_client', source)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@contextlib.contextmanager
def platform(replies):
    """A real local HTTP boundary records accepted payloads, including lost writes."""
    accepted = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def handle_request(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            accepted.append({'method': self.command, 'path': self.path,
                             'payload': json.loads(body) if body else None,
                             'time': time.monotonic()})
            reply = replies[min(len(accepted) - 1, len(replies) - 1)]
            if reply == 'disconnect':
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            status, headers, value = reply
            content = json.dumps(value).encode()
            self.send_response(status)
            for key, item in headers.items():
                self.send_header(key, item)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            try:
                if headers.get('X-Test-Partial'):
                    self.wfile.write(content[:5])
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                elif headers.get('X-Test-Trickle'):
                    for byte in content:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(.03)
                else:
                    self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:%d' % server.server_port, accepted
    finally:
        server.shutdown()
        server.server_close()
        thread.join(1)


OK = (200, {}, {'state': 'stopped', 'authorization': 'unchanged'})


def test_budget_expires_before_first_send_without_losing_diagnostic(module, monkeypatch):
    client = module.Client('http://127.0.0.1:1')
    ticks = iter([0.0, 31.0, 31.0])
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(ticks, 31.0))
    monkeypatch.setattr(client.http, 'open', lambda *a, **k: pytest.fail('expired request sent'))
    with pytest.raises(ValueError) as failure:
        client.request('/static/agent-tools.json')
    assert failure.value.recovery['stop_reason'] == 'budget_exhausted'
    assert failure.value.recovery['attempts'] == []
    assert failure.value.recovery['original_error']['type'] == 'TimeoutError'


def client_for(module, tmp_path, url, name='get_managed_test', action='managed_status'):
    credential = tmp_path / 'credential.json'
    credential.write_text(json.dumps({'url': url, 'token': 'private-test-token'}))
    client = module.Client(url, credential)
    client.manifest = {'tools': [{'name': name, 'inputSchema': {'properties': {}},
                                  'annotations': {'readOnlyHint': True}}],
                       'actions': {name: action}}
    return client


@pytest.mark.parametrize('first', ['disconnect', (429, {}, {'detail': 'limited'}),
                                   (502, {}, {'detail': 'gateway'}),
                                   (503, {}, {'detail': 'unavailable'}),
                                   (504, {}, {'detail': 'gateway timeout'})])
def test_explicit_platform_read_recovers_without_changing_stopped_state(module, tmp_path, first):
    with platform([first, OK]) as (url, accepted):
        client = client_for(module, tmp_path, url)
        assert client.call('get_managed_test', {'task_id': 'original'}) == OK[2]
        assert client.last_request_recovery['stop_reason'] == 'recovered'
        assert client.last_request_recovery['attempts'][0]['error']['type'] in {'HTTPError', 'RemoteDisconnected'}
        assert client.last_request_recovery['attempts'][1]['result'] == 'success'
        assert 'private-test-token' not in json.dumps(client.last_request_recovery)
        assert [item['payload'] for item in accepted] == [
            {'action': 'managed_status', 'arguments': {'task_id': 'original'}}] * 2


def test_manifest_read_has_the_same_bounded_recovery(module):
    with platform(['disconnect', (200, {}, {'tools': [], 'actions': {}})]) as (url, accepted):
        assert module.Client(url).tools() == {'tools': [], 'actions': {}}
        assert len(accepted) == 2


def test_truncated_read_response_recovers_from_original_query(module, tmp_path):
    with platform([(200, {'X-Test-Partial': 'yes'}, {'state': 'stopped'}), OK]) as (url, accepted):
        assert client_for(module, tmp_path, url).call('get_managed_test', {}) == OK[2]
        assert len(accepted) == 2


def test_truncated_save_response_keeps_write_unknown_without_resubmitting(module, tmp_path):
    with platform([(200, {'X-Test-Partial': 'yes'}, {'saved': True}), OK]) as (url, accepted):
        client = client_for(module, tmp_path, url, 'save_test_materials', 'save_materials')
        with pytest.raises(ValueError) as failure:
            client.call('save_test_materials', {})
        assert len(accepted) == 1
        assert failure.value.recovery['original_error']['type'] == 'IncompleteRead'


@pytest.mark.parametrize('status', [400, 401, 403, 409, 500])
def test_nontransient_http_status_is_preserved_without_retry(module, tmp_path, status):
    with platform([(status, {}, {'detail': 'original denial'}), OK]) as (url, accepted):
        client = client_for(module, tmp_path, url)
        with pytest.raises(module.ClientHTTPError) as failure:
            client.call('get_managed_test', {})
        assert failure.value.status == status
        assert 'original denial' in str(failure.value)
        assert len(accepted) == 1


@pytest.mark.parametrize('name,action,args', [
    ('direct_test_session', 'direct_session', {'action': 'claim', 'holder_id': 'holder', 'wait_seconds': 0}),
    ('direct_test_session', 'direct_session', {'action': 'record', 'record_action': 'cases'}),
    ('direct_test_session', 'direct_session', {'action': 'dispatch'}),
    ('direct_test_session', 'direct_session', {'action': 'dispatch', 'arguments': {'observe': True}}),
    ('control_managed_test', 'managed_control', {'action': 'stop'}),
    ('publish_ui_test_report', 'ui_publish', {}),
    ('save_test_materials', 'save_materials', {}),
    ('get_future_tool', 'future_query', {}),
    ('get_managed_test', 'managed_control', {'action': 'stop'}),
])
def test_writes_compound_actions_and_unknown_tools_send_once_after_lost_response(module, tmp_path, name, action, args):
    with platform(['disconnect', OK]) as (url, accepted):
        client = client_for(module, tmp_path, url, name, action)
        with pytest.raises(ValueError):
            client.call(name, args)
        assert len(accepted) == 1


def test_one_time_code_redemption_is_not_retried(module, tmp_path):
    with platform(['disconnect', OK]) as (url, accepted):
        client = module.Client(url, tmp_path / 'private' / 'credential.json')
        with pytest.raises(ValueError):
            client.connect('one-time-private-code')
        assert len(accepted) == 1
        assert not client.path.exists()


def test_real_lost_save_response_reconciles_exact_durable_receipt_without_second_write(module, tmp_path):
    payload = {'cases': [{'case_id': 'C1', 'status': 'not_run', 'scenario': '原设计'}],
               'review_notes': '原始观察'}
    record = {'id': 'execution', 'revision': 3, **payload}
    with platform(['disconnect', (200, {}, record)]) as (url, accepted):
        client = client_for(module, tmp_path, url, 'direct_test_session', 'direct_session')
        client.manifest['tools'][0]['inputSchema']['properties'] = {
            'action': {}, 'holder_id': {}, 'arguments': {}}
        binding_file, receipt_file = tmp_path / 'binding.json', tmp_path / 'receipt.json'
        module.write_private_json(binding_file, {'workspace_url': url, 'holder_id': 'holder',
            'task_id': 'task', 'node_id': 'node', 'lease_id': 'lease', 'project_id': 'project',
            'execution_id': 'execution', 'revision': 2})
        with pytest.raises(ValueError):
            client.native_record(binding_file, payload, receipt_file)
        assert json.loads(receipt_file.read_text())['state'] == 'unknown'
        assert json.loads(binding_file.read_text())['revision'] == 2
        result = client.native_record(binding_file, payload, receipt_file)
        assert result['saved'] and result['revision'] == 3
        assert [item['payload']['arguments']['record_action'] for item in accepted] == ['cases', 'record']
        receipt = json.loads(receipt_file.read_text())
        assert receipt['confirmation_source'] == 'platform_record_readback'
        assert receipt['original_transport_state'] == 'unknown'
        assert receipt['payload']['cases'] == payload['cases']


@pytest.mark.parametrize('retry_after', ['31', format_datetime(datetime.now(timezone.utc) + timedelta(minutes=2))])
def test_retry_after_exceeding_remaining_budget_never_sends_early(module, tmp_path, retry_after):
    with platform([(503, {'Retry-After': retry_after}, {'detail': 'later'}), OK]) as (url, accepted):
        client = client_for(module, tmp_path, url)
        with pytest.raises(module.ClientHTTPError) as failure:
            client.call('get_managed_test', {})
        assert failure.value.status == 503
        assert len(accepted) == 1
        assert failure.value.recovery['stop_reason'] == 'retry_after_exceeds_budget'


def test_retry_after_is_respected_within_budget(module, tmp_path):
    with platform([(429, {'Retry-After': '1'}, {'detail': 'later'}), OK]) as (url, accepted):
        assert client_for(module, tmp_path, url).call('get_managed_test', {}) == OK[2]
        assert accepted[1]['time'] - accepted[0]['time'] >= .99


def test_exhaustion_preserves_first_error_and_safe_attempt_summary(module, tmp_path):
    with platform([(503, {}, {'detail': 'first private-test-token'}),
                   (502, {}, {'detail': 'second'}), (504, {}, {'detail': 'last'})]) as (url, accepted):
        with pytest.raises(module.ClientHTTPError) as failure:
            client_for(module, tmp_path, url).call('get_managed_test', {})
        error = failure.value
        assert len(accepted) == 3
        assert error.status == 504
        assert error.recovery['original_error']['status'] == 503
        assert [attempt['error']['status'] for attempt in error.recovery['attempts']] == [503, 502, 504]
        assert 'first' in str(error) and 'last' in str(error)
        assert 'private-test-token' not in str(error) + json.dumps(error.recovery)


def test_a_slow_response_body_cannot_restart_the_original_budget(module, tmp_path, monkeypatch):
    monkeypatch.setattr(module, '_REQUEST_BUDGET_SECONDS', .12, raising=False)
    with platform([(200, {'X-Test-Trickle': 'yes'}, {'state': 'stopped'})]) as (url, accepted):
        started = time.monotonic()
        with pytest.raises(ValueError) as failure:
            client_for(module, tmp_path, url).call('get_managed_test', {})
        assert time.monotonic() - started < .35
        assert len(accepted) == 1
        assert failure.value.recovery['stop_reason'] == 'budget_exhausted'


@pytest.mark.parametrize('reason', [ssl.SSLCertVerificationError(1, 'private-test-token'),
                                    socket.gaierror(socket.EAI_NONAME, 'private-test-token'),
                                    OSError(22, 'private-test-token')])
def test_permanent_transport_faults_are_not_retried_and_do_not_leak_secrets(module, tmp_path, reason):
    class FailedTransport:
        accepted = 0
        def open(self, request, timeout):
            self.accepted += 1
            raise urllib.error.URLError(reason)
    client = client_for(module, tmp_path, 'http://127.0.0.1:1')
    client.http = FailedTransport()
    with pytest.raises(ValueError) as failure:
        client.call('get_managed_test', {})
    assert client.http.accepted == 1
    assert 'private-test-token' not in str(failure.value)
    assert failure.value.recovery['original_error']['type'] == 'URLError'


def test_each_retry_only_receives_the_original_deadline_remaining(module, tmp_path, monkeypatch):
    clock = [100.0]
    timeouts = []
    class FailedTransport:
        def open(self, request, timeout):
            timeouts.append(timeout)
            clock[0] += min(11, timeout)
            raise urllib.error.URLError(ConnectionResetError(54, 'synthetic reset'))
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(module.time, 'sleep', lambda delay: clock.__setitem__(0, clock[0] + delay))
    client = client_for(module, tmp_path, 'http://127.0.0.1:1')
    client.http = FailedTransport()
    with pytest.raises(ValueError) as failure:
        client.call('get_managed_test', {})
    assert len(timeouts) == 3
    assert timeouts[0] == 30 and 18 <= timeouts[1] < 19 and 6 <= timeouts[2] < 8
    assert failure.value.recovery['elapsed_seconds'] <= 30
    assert len(failure.value.recovery['attempts']) == 3
    assert failure.value.recovery['stop_reason'] == 'budget_exhausted'
