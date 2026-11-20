"""Real local model HTTP -> reviewed cases -> real probe HTTP -> report.

This test does not replace generate_text, the model adapters or the network
session. Only the upstream model response is provided by a local HTTP fixture.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from api_test_tool import web


MOCK_KEY = "offline-provider-test-key-no-real-account"


@contextmanager
def _server(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _wait(client, response):
    assert response.status_code == 200, response.text
    job_id = response.json()["id"]
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        polled = client.get(f"/api/jobs/{job_id}")
        assert polled.status_code == 200, polled.text
        job = polled.json()
        if job["status"] in {"completed", "failed"}:
            assert job["status"] == "completed", job
            return job["result"]
        time.sleep(0.01)
    pytest.fail("Local model workflow exceeded 20 seconds")


@pytest.mark.parametrize("large_response", [False, True])
def test_web_model_generation_uses_pinned_http_and_executes_reviewed_bundle(tmp_path, monkeypatch, large_response):
    provider_audit = []
    probe_audit = []

    class QuietHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, value, *, cookie=False):
            body = json.dumps(value).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if cookie:
                self.send_header("Set-Cookie", "probe_session=first-request; Path=/")
            self.end_headers()
            self.wfile.write(body)

    class Provider(QuietHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            provider_audit.append({"path": self.path, "headers": dict(self.headers), "payload": payload})
            context = json.loads(payload["messages"][-1]["content"])
            contract = context["contract"]
            operation = contract["operations"]["get_probe"]
            source_id = operation["source_ids"][0]
            evidence = [{"source_id": source_id, "quote": contract["sources"][source_id]["excerpt"]}]
            assertions = [{"kind": "status", "expected": 200, "evidence": evidence},
                          {"kind": "json_schema", "expected": operation["responses"]["200"], "evidence": evidence}]
            proposal = {"schema_version": "1.0", "cases": [{
                "id": "AI-001-001", "title": "模型生成的两次只读检查", "operation_id": "get_probe",
                "scenario": "normal", "variables": {}, "steps": [
                    {"id": "read", "operation_id": "get_probe", "request": {}, "assertions": assertions, "extract": []},
                    {"id": "read-without-session", "operation_id": "get_probe", "request": {"session": False},
                     "assertions": assertions, "extract": []}], "cleanup_steps": [], "notes": "两个 GET 均不写入持久数据"}]}
            if large_response:
                # Unused literal data proves long responses survive compilation, storage,
                # review and report creation without making large target HTTP requests.
                proposal["cases"][0]["variables"]["long_fixture"] = {"kind":"literal", "value":"x" * (3 * 1024 * 1024)}
            if context.get("phase") == "design":
                proposal["cases"][0]["design"] = {"category": "正向", "inputs": "GET /probe", "procedure": "两次读取", "expected": "200 和 Schema", "basis": "接口文档"}
            text = json.dumps(proposal)
            frames = [{"choices": [{"index": 0, "delta": {"reasoning_content": "private fixture reasoning"}}]}]
            frames += [{"choices": [{"index": 0, "delta": {"content": text[i:i + 4096]}}]} for i in range(0, len(text), 4096)]
            frames.append({"model": "local-fixture-model", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 60, "total_tokens": 100}})
            raw = b"".join(("data: " + json.dumps(frame) + "\n\n").encode() for frame in frames) + b"data: [DONE]\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    class Probe(QuietHandler):
        def do_GET(self):
            probe_audit.append({"path": self.path, "host": self.headers.get("Host"), "cookie": self.headers.get("Cookie")})
            self.respond({"ok": True, "count": 2}, cookie=True)

    document = {"openapi": "3.0.3", "info": {"title": "Real HTTP integration probe", "version": "1"},
        "paths": {"/probe": {"get": {"operationId": "get_probe", "responses": {"200": {
            "description": "A successful read-only status probe", "content": {"application/json": {"schema": {
                "type": "object", "required": ["ok", "count"],
                "properties": {"ok": {"type": "boolean"}, "count": {"type": "integer"}}}}}}}}}}}

    with _server(Provider) as provider, _server(Probe) as probe:
        provider_origin = f"http://localhost:{provider.server_port}"
        target_origin = f"http://localhost:{probe.server_port}"
        data_dir = tmp_path / "web-model-http"
        app = web.create_app(data_dir, start_fixture=False, testing=True,
                             trusted_model_origins=(provider_origin,), extra_test_origins=(target_origin,))
        actual_factory = web.pinned_session
        factory_audit = []

        def traced_factory(url, trusted_origins=()):
            session = actual_factory(url, trusted_origins)
            factory_audit.append({"url": url, "ips": session._pinned_ips, "trust_env": session.trust_env})
            return session

        monkeypatch.setattr(web, "pinned_session", traced_factory)
        actual_resolve = socket.getaddrinfo
        dns_audit = []

        def traced_resolve(host, *args, **kwargs):
            if host == "localhost":
                dns_audit.append(host)
            return actual_resolve(host, *args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", traced_resolve)
        with TestClient(app) as client:
            boot = client.get("/api/bootstrap")
            assert boot.status_code == 200
            client.headers["x-csrf-token"] = boot.json()["csrf"]
            imported = client.post("/api/projects", json={"filename": "probe.json", "content": json.dumps(document)})
            assert imported.status_code == 200, imported.text
            project_id = imported.json()["project"]["id"]
            saved = client.put("/api/model", json={"provider": "deepseek", "protocol": "openai_chat",
                "base_url": provider_origin + "/v1", "model": "deepseek-v4-flash", "api_key": MOCK_KEY, "max_tokens": None})
            assert saved.status_code == 200, saved.text
            assert saved.json()["has_key"] is True
            assert MOCK_KEY not in saved.text
            assert not provider_audit and not probe_audit  # Saving never spends a model call.

            generated = _wait(client, client.post(f"/api/projects/{project_id}/generate", json={"mode": "model"}))
            assert generated["summary"]["NEEDS_RULE"] == 1
            assert len(provider_audit) == 2
            assert not probe_audit  # Import / model generation never touch the target API.
            request = provider_audit[0]
            assert request["path"] == "/v1/chat/completions"
            assert request["headers"]["Host"] == f"localhost:{provider.server_port}"
            assert request["headers"]["Authorization"] == "Bearer " + MOCK_KEY
            assert request["payload"]["max_tokens"] == 384000
            assert request["payload"]["stream"] is True
            assert MOCK_KEY not in json.dumps(request["payload"])
            detail = client.get(f"/api/projects/{project_id}").json()
            messages = [entry["message"] for entry in detail["project"]["last_job"]["logs"]]
            assert "模型思考中" in messages
            assert any("正在接收模型结果" in message for message in messages)
            assert "private fixture reasoning" not in json.dumps(detail)
            assert detail["bundle"]["generation"]["usage"] == {"input_tokens": 80, "output_tokens": 120, "total_tokens": 200}
            assert detail["bundle"]["cases"][0]["web"]["approval_eligible"] is True
            assert detail["bundle"]["cases"][0]["steps"][1]["request"]["session"] is False
            if large_response:
                assert len(detail["bundle"]["cases"][0]["variables"]["long_fixture"]["value"]) == 3 * 1024 * 1024

            approval = client.post(f"/api/projects/{project_id}/approve", json={"case_ids": ["AI-001-001"]})
            assert approval.status_code == 200, approval.text
            assert approval.json()["summary"]["READY"] == 1
            assert not probe_audit
            execution = _wait(client, client.post(f"/api/projects/{project_id}/run",
                                                  json={"environment": "custom", "base_url": target_origin}))
            assert execution["summary"]["PASS"] == 1
            assert execution["summary"]["complete"] is True
            assert execution["requests_sent"] == 2
            assert probe_audit == [{"path": "/probe", "host": f"localhost:{probe.server_port}", "cookie": None}] * 2
            # Model request + primary case session + explicitly isolated second step.
            assert [call["url"] for call in factory_audit] == [provider_origin + "/v1", provider_origin + "/v1", target_origin, target_origin]
            assert all(call["trust_env"] is False and "127.0.0.1" in call["ips"] for call in factory_audit)
            assert dns_audit == ["localhost"] * 4  # One DNS resolution per real pinned session.

            report = client.get(execution["report_url"])
            result = client.get(execution["report_url"].replace("index.html", "result.json"))
            assert report.status_code == 200 and "text/html" in report.headers["content-type"]
            assert result.status_code == 200
            assert len(result.json()["cases"][0]["steps"]) == 2
            assert all(step["response"]["body"] == {"ok": True, "count": 2} for step in result.json()["cases"][0]["steps"])
            for response in (report, result, client.get("/api/bootstrap"), client.get(f"/api/projects/{project_id}")):
                assert MOCK_KEY not in response.text
        assert all(MOCK_KEY.encode() not in path.read_bytes() for path in data_dir.rglob("*") if path.is_file())
