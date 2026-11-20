"""Protocol compatibility proof, with local HTTP only and no provider credentials."""
from __future__ import annotations

import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from api_test_tool import models as adapters


SECRET = "fixture-secret-not-a-real-key"


@pytest.fixture
def endpoint():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.server.recorded.append({"path": self.path, "headers": dict(self.headers), "body": json.loads(body)})
            status, response_body, headers = self.server.answer
            raw = response_body if isinstance(response_body, bytes) else json.dumps(response_body).encode()
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            if not self.server.omit_length:
                self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (ConnectionResetError, BrokenPipeError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.recorded = []
    server.answer = (200, {"choices": [{"message": {"content": "fixture OK"}, "finish_reason": "stop"}]}, {})
    server.omit_length = False
    server.url = "http://127.0.0.1:" + str(server.server_port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def config(base_url="https://models.example/v1", protocol="openai_chat", **kwargs):
    return adapters.ModelConfig(provider=kwargs.pop("provider", "custom"), protocol=protocol, base_url=base_url,
                                model=kwargs.pop("model", "fixture-model"), api_key=SECRET, max_tokens=kwargs.pop("max_tokens", 6000), **kwargs)


@pytest.mark.parametrize("protocol,body,path,token_field", [
    ("openai_responses", {"status": "completed", "model": "fixture-resolved", "output": [
        {"type": "reasoning", "summary": []}, {"type": "message", "content": [{"type": "output_text", "text": "fixture OK"}]}],
        "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}}, "/v1/responses", "max_output_tokens"),
    ("openai_chat", {"choices": [{"message": {"content": [{"type": "text", "text": "fixture OK"}], "reasoning_content": "private thought"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}, "/v1/chat/completions", "max_tokens"),
    ("anthropic", {"content": [{"type": "thinking", "thinking": "private thought"}, {"type": "text", "text": "fixture OK"}], "stop_reason": "end_turn",
        "usage": {"input_tokens": 5, "output_tokens": 2}}, "/v1/messages", "max_tokens"),
    ("gemini", {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "private thought", "thought": True}, {"text": "fixture OK"}]}}],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2, "totalTokenCount": 7}}, "/v1beta/models/fixture-model:streamGenerateContent?alt=sse", "maxOutputTokens"),
])
def test_protocol_roundtrip(endpoint, protocol, body, path, token_field):
    endpoint.answer = (200, body, {"Content-Type": "application/json"})
    result = adapters.generate_text(config(endpoint.url, protocol, max_tokens=512), "system instructions", "user request")
    assert set(result) == {"text", "usage", "model", "protocol", "elapsed_ms"}
    assert result["text"] == "fixture OK"
    assert result["usage"] == {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}
    assert result["protocol"] == protocol
    assert result["elapsed_ms"] >= 0
    assert len(endpoint.recorded) == 1
    request = endpoint.recorded[0]
    assert request["path"] == path
    assert "temperature" not in request["body"]
    assert "response_format" not in request["body"]
    if protocol == "gemini":
        assert request["headers"]["x-goog-api-key"] == SECRET
        assert request["body"]["generationConfig"][token_field] == 512
        assert request["body"]["systemInstruction"]["parts"] == [{"text": "system instructions"}]
    else:
        assert request["body"][token_field] == 512
        assert request["body"]["stream"] is True
    if protocol == "anthropic":
        assert request["headers"]["x-api-key"] == SECRET
        assert request["headers"]["anthropic-version"] == "2023-06-01"
        assert request["body"]["system"] == "system instructions"
    elif protocol != "gemini":
        assert request["headers"]["Authorization"] == "Bearer " + SECRET
    if protocol == "openai_responses":
        assert request["body"]["store"] is False
        assert request["body"]["input"] == "user request"


@pytest.mark.parametrize("base,protocol,expected", [
    ("https://example.test", "openai_chat", "https://example.test/v1/chat/completions"),
    ("https://example.test/v1/", "openai_chat", "https://example.test/v1/chat/completions"),
    ("https://example.test/api/paas/v4", "openai_chat", "https://example.test/api/paas/v4/chat/completions"),
    ("https://example.test/api/v3/chat/completions", "openai_chat", "https://example.test/api/v3/chat/completions"),
    ("https://example.test", "anthropic", "https://example.test/v1/messages"),
    ("https://example.test/v1/responses/", "openai_responses", "https://example.test/v1/responses"),
    ("https://example.test/v1beta/models", "gemini", "https://example.test/v1beta/models/fixture-model:generateContent"),
    ("https://example.test/v1", "gemini", "https://example.test/v1/models/fixture-model:generateContent"),
])
def test_endpoint_joins_without_duplicate_versions(base, protocol, expected):
    cfg = config(base, protocol)
    adapters.validate_config(cfg)
    assert adapters._endpoint(cfg) == expected


@pytest.mark.parametrize("changes", [
    {"base_url": "https://user:pass@example.test/v1"}, {"base_url": "https://example.test/v1?key=secret"},
    {"base_url": "https://example.test/v1#fragment"}, {"base_url": "http://192.168.1.20/v1"},
    {"base_url": "ftp://example.test/v1"}, {"base_url": "https://example.test/../v1"},
    {"base_url": "https://example.test/v1\n"}, {"base_url": "https://example.test:99999"},
    {"base_url": "https://example.test/v1?"}, {"base_url": "https://example.test/v1#"},
    {"base_url": "https://example.test/%2e%2e/v1"}, {"base_url": "https://example.test/v1/messages"},
    {"protocol": "unsupported"}, {"model": "../models/secret?bad"}, {"model": ""},
    {"api_key": "key\r\nInjected: yes"}, {"api_key": ""}, {"api_key": None},
    {"max_tokens": True}, {"max_tokens": 0}, {"max_tokens": 32.5},
    {"timeout": float("nan")}, {"timeout": True}, {"timeout": 0}, {"timeout": 181},
])
def test_configuration_rejected_before_network(changes, monkeypatch):
    def forbidden():
        raise AssertionError("network session should not be created")
    monkeypatch.setattr(adapters.requests, "Session", forbidden)
    with pytest.raises(adapters.ModelConfigError) as error:
        adapters.generate_text(replace(config(), **changes), "system", "user")
    assert SECRET not in str(error.value)


def test_openai_modern_token_field_and_developer_role(endpoint):
    adapters.generate_text(config(endpoint.url, provider="openai", model="gpt-5-example", max_tokens=6000), "system", "user")
    body = endpoint.recorded[0]["body"]
    assert body["max_completion_tokens"] == 6000
    assert "max_tokens" not in body
    assert body["messages"][0]["role"] == "developer"


def test_minimax_separates_reasoning(endpoint):
    adapters.generate_text(config(endpoint.url, provider="minimax", max_tokens=6000), "system", "user")
    assert endpoint.recorded[0]["body"]["reasoning_split"] is True
    assert endpoint.recorded[0]["body"]["max_completion_tokens"] == 6000


def test_redirect_is_not_followed_or_leaked(endpoint):
    endpoint.answer = (307, {"secret": SECRET}, {"Location": endpoint.url + "/stolen?key=" + SECRET})
    with pytest.raises(adapters.ModelAPIError) as error:
        adapters.generate_text(config(endpoint.url), "system", "user")
    assert error.value.code == "redirect_blocked"
    assert len(endpoint.recorded) == 1
    assert SECRET not in str(error.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500])
def test_http_errors_are_sanitized_without_retry(endpoint, status):
    endpoint.answer = (status, {"error": {"message": "Rejected credential " + SECRET}}, {})
    with pytest.raises(adapters.ModelAPIError) as error:
        adapters.generate_text(config(endpoint.url), "system", "user")
    assert error.value.http_status == status
    assert SECRET not in str(error.value)
    assert len(endpoint.recorded) == 1


@pytest.mark.parametrize("body,code", [
    (b"<html>" + SECRET.encode() + b"</html>", "invalid_json"),
    ([], "invalid_response"),
    ({"error": {"message": SECRET}}, "upstream_error"),
    ({"base_resp": {"status_code": 1000, "status_msg": SECRET}}, "upstream_error"),
    ({"choices": []}, "empty_output"),
    ({"choices": [{"message": {"content": SECRET}, "finish_reason": "length"}]}, "incomplete_output"),
])
def test_invalid_upstream_content_is_not_used(endpoint, body, code):
    endpoint.answer = (200, body, {})
    with pytest.raises(adapters.ModelAPIError) as error:
        adapters.generate_text(config(endpoint.url), "system", "user")
    assert error.value.code == code
    assert SECRET not in str(error.value)


@pytest.mark.parametrize("protocol,body", [
    ("openai_responses", {"status": "incomplete", "output_text": "partial"}),
    ("anthropic", {"stop_reason": "max_tokens", "content": [{"type": "text", "text": "partial"}]}),
    ("gemini", {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "partial"}]}}]}),
])
def test_truncation_cannot_become_a_generation_success(endpoint, protocol, body):
    endpoint.answer = (200, body, {})
    with pytest.raises(adapters.ModelAPIError) as error:
        adapters.generate_text(config(endpoint.url, protocol), "system", "user")
    assert error.value.code == "incomplete_output"


@pytest.mark.parametrize("omit_length", [False, True])
def test_response_limit_covers_declared_and_streamed_body(endpoint, omit_length, monkeypatch):
    monkeypatch.setattr(adapters, "MAX_RESPONSE_BYTES", 64)
    endpoint.omit_length = omit_length
    endpoint.answer = (200, {"choices": [{"message": {"content": "x" * 256}}]}, {})
    with pytest.raises(adapters.ModelAPIError) as error:
        adapters.generate_text(config(endpoint.url), "system", "user")
    assert error.value.code == "response_too_large"


def test_input_limit_sends_zero_requests(endpoint, monkeypatch):
    monkeypatch.setattr(adapters, "MAX_PROMPT_BYTES", 10)
    with pytest.raises(adapters.ModelConfigError):
        adapters.generate_text(config(endpoint.url), "system", "too much user input")
    assert endpoint.recorded == []


def test_environment_proxy_and_auth_are_not_inherited(endpoint, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    result = adapters.generate_text(config(endpoint.url), "system", "user")
    assert result["text"] == "fixture OK"


def test_key_is_hidden_from_repr_and_success_and_usage(endpoint):
    endpoint.answer = (200, {"choices": [{"message": {"content": "do not expose " + SECRET}}], "model": SECRET,
                              "usage": {"prompt_tokens": 5, "completion_tokens": 2, "extra": SECRET,
                                        "total_tokens": SECRET, "output_tokens_details": {"secret": SECRET}}}, {})
    cfg = config(endpoint.url)
    result = adapters.generate_text(cfg, "system", "user")
    assert SECRET not in repr(cfg)
    assert SECRET not in json.dumps(result)
    assert result["text"] == "do not expose [REDACTED]"
    assert result["usage"] == {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}


@pytest.mark.parametrize("exc,code", [(requests.exceptions.Timeout(SECRET), "timeout"),
                                     (requests.exceptions.ConnectionError(SECRET), "connection_error")])
def test_requests_exceptions_do_not_expose_keys(monkeypatch, exc, code):
    class FailingSession(requests.Session):
        def post(self, *args, **kwargs):
            assert self.trust_env is False
            assert kwargs["allow_redirects"] is False
            assert self.adapters["https://"].max_retries.total == 0
            raise exc
    monkeypatch.setattr(adapters.requests, "Session", FailingSession)
    with pytest.raises(adapters.ModelAPIError) as error:
        adapters.generate_text(config(), "system", "user")
    assert error.value.code == code
    assert SECRET not in str(error.value)
    assert error.value.__suppress_context__ is True


def test_connection_is_one_small_request(endpoint):
    result = adapters.test_connection(config(endpoint.url, max_tokens=1000))
    assert result["text"] == "fixture OK"
    assert len(endpoint.recorded) == 1
    assert endpoint.recorded[0]["body"]["max_tokens"] == 256


def test_presets_are_complete_and_configurable():
    assert {p["id"] for p in adapters.PROVIDERS} == {"openai", "deepseek", "qwen", "glm", "kimi", "doubao", "minimax", "claude", "gemini", "custom"}
    for provider in adapters.PROVIDERS:
        assert set(provider) == {"id", "name", "protocol", "base_url", "model_hint", "docs_url"}
        assert provider["protocol"] in adapters.PROTOCOLS
        if provider["base_url"]:
            adapters.validate_config(config(provider["base_url"], provider["protocol"], provider=provider["id"]))
