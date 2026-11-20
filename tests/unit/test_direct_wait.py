"""Receipt waiting must never become a second business execution."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from api_test_tool import direct_wait
from api_test_tool.mcp_server import WorkspaceClient

SOURCE = Path(__file__).parents[2] / 'api_test_tool/static/api-test-client.py'
spec = importlib.util.spec_from_file_location('direct_wait_client', SOURCE)
client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_module)


@pytest.fixture(params=[direct_wait, client_module], ids=['installed-mcp', 'standalone'])
def engine(request, monkeypatch):
    module = request.param
    clock = [0.]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    return module.direct_call_and_wait


def test_submit_once_and_read_same_receipt(engine):
    calls = []
    answers = iter([{'state': 'queued'}, {'state': 'running'}, {'state': 'completed', 'result': {'snapshot': 'actual'}}])
    def send(args):
        calls.append(args.copy())
        return next(answers)
    args = dict(action='browser', holder_id='chat', lease_id='lease', request_id='write-once', browser_action='click', parameters={'selector': 'button'})
    result = engine(send, args)
    assert result['result']['snapshot'] == 'actual'
    assert [c['action'] for c in calls] == ['browser', 'result', 'result']
    assert calls[1:] == [dict(action='result', holder_id='chat', lease_id='lease', request_id='write-once')] * 2
    assert 'wait_seconds' not in calls[0]
    assert result['client_wait'] == dict(elapsed_seconds=.75, http_calls=3, pending=False)
    assert args['action'] == 'browser'


def test_timeout_preserves_pending_and_query_identity(engine):
    calls = []
    def send(args):
        calls.append(args)
        return {'id': 'once', 'state': 'running'}
    result = engine(send, dict(action='browser', lease_id='lease', holder_id='chat', request_id='once', wait_seconds=.5))
    assert result['state'] == 'running'
    assert result['client_wait']['pending']
    assert result['client_wait']['resume_arguments'] == dict(action='result', lease_id='lease', holder_id='chat', request_id='once')
    assert [c['action'] for c in calls] == ['browser', 'result']


def test_unknown_stops_and_transport_never_replays(engine):
    calls = []
    def send(args):
        calls.append(args)
        if len(calls) == 1:
            return {'state': 'queued'}
        raise ValueError('network unavailable')
    result = engine(send, dict(action='browser', request_id='same', lease_id='lease', holder_id='chat'))
    assert len(calls) == 2 and calls[-1]['action'] == 'result'
    assert result['state'] == 'queued'
    assert result['client_wait']['poll_error'] == 'network unavailable'
    calls.clear()
    def unknown(args):
        calls.append(args)
        return {'state': 'unknown', 'error': 'inspect original operation'}
    result = engine(unknown, dict(action='browser'))
    assert len(calls) == 1 and result['state'] == 'unknown'
    assert not result['client_wait']['pending']
    calls.clear()
    def lost(args):
        calls.append(args)
        raise ValueError('lost submit response')
    with pytest.raises(ValueError, match='lost submit'):
        engine(lost, dict(action='browser'))
    assert len(calls) == 1


def test_claim_ack_and_finish_exit_are_actual_conditions(engine):
    for action, answers, expected in [
        ('claim', [{'state': 'starting', 'lease_id': 'l'}, {'state': 'starting', 'lease_id': 'l'}, {'state': 'running', 'browser_ready': True}], 'browser_ready'),
        ('finish', [{'state': 'stopping', 'released': False}, {'state': 'stopping', 'released': False}, {'state': 'completed', 'released': True}], 'released'),
    ]:
        calls = []
        def send(args):
            calls.append(args)
            return answers[len(calls)-1]
        result = engine(send, dict(action=action, lease_id='l', holder_id='chat', task_id='task'))
        assert result[expected] and len(calls) == 3
        assert all(call == calls[0] for call in calls)


def test_immediate_and_unrelated_actions_keep_original_behavior(engine):
    for args in [dict(action='browser', wait_seconds=0), dict(action='credentials'), dict(action='record'), dict(action='wait')]:
        with patch('builtins.print'):
            calls = []
            result = engine(lambda a: calls.append(a) or {'state': 'queued'}, args)
        assert result == {'state': 'queued'} and len(calls) == 1
    for seconds in [-1, float('nan'), float('inf'), True, 51]:
        with pytest.raises(ValueError):
            engine(lambda a: pytest.fail('invalid wait sent'), dict(action='browser', wait_seconds=seconds))


def test_download_is_generated_from_shared_source():
    embedded = SOURCE.read_text().split('# BEGIN GENERATED DIRECT WAIT\n', 1)[1].split('\n# END GENERATED DIRECT WAIT', 1)[0]
    expected = Path(direct_wait.__file__).read_text().replace(
        'from .direct_batch import batch_path, client_capabilities, compatible_batch, save_batch',
        Path(direct_wait.__file__).with_name('direct_batch.py').read_text())
    assert embedded == expected


def test_unallocated_claim_yields_without_polling(engine):
    calls = []
    args = dict(action='claim', holder_id='original', task_id='task', node_id='node', dispatch_id='dispatch')
    result = engine(lambda value: calls.append(value) or {'state': 'queued', 'lease_id': None}, args)
    assert calls == [args]
    assert result['resource_wait']['end_turn'] is True
    assert result['resource_wait']['resume_arguments'] == args
    assert result['client_wait']['pending'] is False


@pytest.mark.parametrize('installed', [True, False])
def test_real_client_adapter_uses_wait_without_leaking_option(tmp_path, installed):
    credential = tmp_path / 'credential.json'
    credential.write_text(json.dumps({'url': 'http://127.0.0.1:1', 'token': 'fixture'}))
    args = dict(action='browser', lease_id='lease', holder_id='chat', request_id='one', wait_seconds=1)
    answers = [{'state': 'queued'}, {'state': 'completed', 'result': {'snapshot': 'real receipt'}}]
    if installed:
        client = WorkspaceClient('http://127.0.0.1:1', credential)
        with patch.object(client, '_post', side_effect=answers) as send:
            result = client.call('direct_session', **args)
    else:
        client = client_module.Client('http://127.0.0.1:1', credential)
        client.manifest = json.loads(SOURCE.with_name('agent-tools.json').read_text())
        with patch.object(client, 'request', side_effect=answers) as send:
            result = client.call('direct_test_session', args)
    assert result['result']['snapshot'] == 'real receipt'
    assert send.call_count == 2
    assert send.call_args_list[0].args[1]['arguments']['request_id'] == 'one'
    assert 'wait_seconds' not in send.call_args_list[0].args[1]['arguments']
    assert send.call_args_list[1].args[1]['arguments']['action'] == 'result'


def test_cli_combines_original_identity_and_returns_saved_result(tmp_path, capsys):
    base = tmp_path / 'base.json'
    base.write_text(json.dumps(dict(holder_id='chat', lease_id='lease', action='browser', request_id='old-write', parameters={'value': 'stale'})))
    destination = tmp_path / 'receipt.json'
    original = dict(state='completed', result={'snapshot': 'visible result', '_image_url': 'data:image/png;base64,fixture'})
    args = ['client', '--url', 'http://127.0.0.1:1', 'call', 'direct_test_session', '--base-args-file', str(base), '--args', '{"action":"browser","request_id":"new-read","browser_action":"snapshot"}', '--output-file', str(destination), '--show-result']
    with patch.object(client_module.sys, 'argv', args), patch.object(client_module.Client, 'call', return_value=original) as call:
        client_module.main()
    actual = call.call_args.args[1]
    assert actual == dict(action='browser', holder_id='chat', lease_id='lease', request_id='new-read', browser_action='snapshot')
    output = json.loads(capsys.readouterr().out)
    assert output['result']['result']['snapshot'] == 'visible result'
    assert 'data:image' not in json.dumps(output)
    assert json.loads(destination.read_text()) == original
    assert destination.stat().st_mode & 0o777 == 0o600


def test_cli_does_not_display_credentials(tmp_path, capsys):
    destination = tmp_path / 'private.json'
    args = ['client', '--url', 'http://127.0.0.1:1', 'call', 'direct_test_session', '--args', '{"action":"credentials"}', '--output-file', str(destination), '--show-result']
    with patch.object(client_module.sys, 'argv', args), patch.object(client_module.Client, 'call', return_value={'password': 'secret-fixture'}):
        client_module.main()
    assert 'secret-fixture' not in capsys.readouterr().out
    assert json.loads(destination.read_text())['password'] == 'secret-fixture'
