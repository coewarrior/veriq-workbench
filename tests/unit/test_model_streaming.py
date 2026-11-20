"""Real HTTP streaming, inactivity, terminal markers and private-data regression tests."""
import json
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from api_test_tool import models
from api_test_tool.network_transport import pinned_session

KEY = 'stream-fixture-key-only'


def event(data, kind=None):
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False)
    return ((f'event: {kind}\n' if kind else '') + f'data: {data}\n\n').encode()


def chat(text='', finish=None, **extra):
    return {'choices': [{'index': 0, 'delta': {'content': text, **extra}, 'finish_reason': finish}]}


@pytest.fixture
def provider():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.server.calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            plan = self.server.plan
            self.send_response(self.server.status)
            self.send_header('Content-Type', self.server.content_type)
            self.send_header('Content-Length', str(sum(len(b) for _, b in plan)))
            self.end_headers()
            for delay, chunk in plan:
                time.sleep(delay)
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.calls, server.plan = [], []
    server.status, server.content_type = 200, 'text/event-stream; charset=utf-8'
    server.origin = f'http://127.0.0.1:{server.server_port}'
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def generate(provider, protocol='openai_chat', progress=None):
    cfg = models.ModelConfig('custom', protocol, provider.origin, 'fixture-model', KEY, max_tokens=6000, timeout=1)
    return models.generate_text(cfg, 'system', 'user', on_progress=progress,
        session_factory=lambda: pinned_session(provider.origin, (provider.origin,)))


def test_active_reasoning_and_small_text_chunks_outlive_timeout(provider):
    provider.plan = [(0, event(chat(reasoning_content='private thought'))),
        (.6, event(chat('你'))), (.6, event(chat('好'))),
        (.6, event(chat('', 'stop')) + event({'choices': [], 'usage': {'prompt_tokens': 3, 'completion_tokens': 2}}) + event('[DONE]'))]
    progress = []
    result = generate(provider, progress=progress.append)
    assert result['text'] == '你好'
    assert result['elapsed_ms'] >= 1600  # Exceeds the configured 1-second timeout.
    assert result['usage']['total_tokens'] == 5
    assert any('思考中' in p for p in progress)
    assert any('接收模型结果' in p for p in progress)
    assert 'private thought' not in str(progress) + str(result)
    assert len(provider.calls) == 1 and provider.calls[0]['stream'] is True


def test_keepalive_waiting_for_first_token_does_not_time_out(provider):
    provider.plan = [(0, b': keep-alive\n\n'), (.6, b': keep-alive\n\n'),
        (.6, b': keep-alive\n\n'), (.6, event(chat('OK', 'stop')) + event('[DONE]'))]
    assert generate(provider)['text'] == 'OK'


def test_genuinely_idle_connection_times_out_without_claiming_provider_failed(provider):
    provider.plan = [(0, event(chat(reasoning_content='thinking'))), (1.4, event(chat('late', 'stop')))]
    with pytest.raises(models.ModelAPIError) as exc:
        generate(provider)
    assert exc.value.code == 'timeout'
    assert '连续 1 秒未收到' in str(exc.value)
    assert '不代表模型返回了错误' in str(exc.value)
    assert len(provider.calls) == 1


def test_json_gateway_fallback_keeps_reading_without_total_deadline_or_retry(provider):
    provider.content_type = 'application/json'
    provider.plan = [(0, b'{"choices":['), (.6, b'{"message":'),
        (.6, b'{"content":"OK"}'), (.6, b',"finish_reason":"stop"}]}')]
    assert generate(provider)['text'] == 'OK'
    assert len(provider.calls) == 1


@pytest.mark.parametrize('protocol,frames', [
    ('openai_chat', [chat('OK', 'stop'), '[DONE]']),
    ('openai_responses', [
        {'type': 'response.reasoning_summary_text.delta', 'delta': 'private thought'},
        {'type': 'response.output_text.delta', 'delta': 'OK'},
        {'type': 'response.completed', 'response': {'status': 'completed', 'model': 'fixture-model',
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'OK'}]}],
            'usage': {'input_tokens': 2, 'output_tokens': 1}}}]),
    ('anthropic', [
        {'type': 'message_start', 'message': {'model': 'fixture-model', 'usage': {'input_tokens': 2}}},
        {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'thinking', 'thinking': ''}},
        {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'thinking_delta', 'thinking': 'private thought'}},
        {'type': 'content_block_start', 'index': 1, 'content_block': {'type': 'text', 'text': ''}},
        {'type': 'content_block_delta', 'index': 1, 'delta': {'type': 'text_delta', 'text': 'OK'}},
        {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}, 'usage': {'output_tokens': 1}},
        {'type': 'message_stop'}]),
    ('gemini', [
        {'candidates': [{'index': 0, 'content': {'parts': [{'thought': True, 'text': 'private thought'}]}}]},
        {'candidates': [{'index': 0, 'content': {'parts': [{'text': 'OK'}]}, 'finishReason': 'STOP'}],
            'usageMetadata': {'promptTokenCount': 2, 'candidatesTokenCount': 1}}]),
])
def test_all_four_stream_protocols_exclude_reasoning_and_return_final_text(provider, protocol, frames):
    provider.plan = [(0, b': ping\r\n\r\n' + b''.join(event(d) for d in frames))]
    progress = []
    result = generate(provider, protocol, progress.append)
    assert result['text'] == 'OK'
    assert 'private thought' not in str(result) + str(progress)
    if protocol != 'openai_chat':
        assert result['usage']['total_tokens'] == 3


@pytest.mark.parametrize('protocol,frames,expected', [
    ('openai_chat', [chat('partial')], 'stream_interrupted'),
    ('openai_chat', [chat('partial'), '[DONE]'], 'stream_interrupted'),
    ('openai_chat', [chat('partial', 'length')], 'incomplete_output'),
    ('openai_chat', [chat('partial', 'content_filter')], 'incomplete_output'),
    ('openai_responses', [{'type': 'response.output_text.delta', 'delta': 'partial'}], 'stream_interrupted'),
    ('openai_responses', [{'type': 'response.incomplete', 'response': {'status': 'incomplete'}}], 'incomplete_output'),
    ('anthropic', [{'type': 'message_delta', 'delta': {'stop_reason': 'max_tokens'}}], 'incomplete_output'),
    ('anthropic', [{'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}}], 'stream_interrupted'),
    ('gemini', [{'candidates': [{'content': {'parts': [{'text': 'partial'}]}}]}], 'stream_interrupted'),
    ('gemini', [{'candidates': [{'finishReason': 'MAX_TOKENS'}]}], 'incomplete_output'),
])
def test_partial_or_truncated_stream_is_never_success(provider, protocol, frames, expected):
    provider.plan = [(0, b''.join(event(d) for d in frames))]
    with pytest.raises(models.ModelAPIError) as exc:
        generate(provider, protocol)
    assert exc.value.code == expected


def test_provider_error_after_http_200_and_partial_output_is_authoritative(provider):
    provider.plan = [(0, event(chat('partial')) + event({'type': 'error', 'error': {
        'type': 'overloaded_error', 'message': KEY + ' private prompt'}}))]
    with pytest.raises(models.ModelAPIError) as exc:
        generate(provider)
    assert exc.value.code == 'upstream_error'
    assert 'overloaded_error' in str(exc.value)
    assert KEY not in str(exc.value) and 'private prompt' not in str(exc.value)
    assert len(provider.calls) == 1


def test_http_error_is_reported_without_waiting_for_slow_error_body(provider):
    provider.status = 429
    provider.plan = [(1.4, event({'error': {'message': KEY}}))]
    with pytest.raises(models.ModelAPIError) as exc:
        generate(provider)
    assert exc.value.http_status == 429
    assert exc.value.code == 'http_error'
    assert KEY not in str(exc.value)


def test_sse_split_unicode_multiline_comments_and_crlf():
    source = (b': keep-alive\r\nevent: sample\r\ndata: {"text":\r\ndata: "' + '你'.encode() + b'"}\r\n\r\n')
    parsed = list(models._sse_events(bytes([b]) for b in source))
    assert parsed == [('sample', '{"text":\n"你"}')]


def test_stream_response_size_is_still_bounded(provider, monkeypatch):
    monkeypatch.setattr(models, 'MAX_RESPONSE_BYTES', 256)
    provider.plan = [(0, event(chat('x' * 500, 'stop')))]
    with pytest.raises(models.ModelAPIError) as exc:
        generate(provider)
    assert exc.value.code == 'response_too_large'
