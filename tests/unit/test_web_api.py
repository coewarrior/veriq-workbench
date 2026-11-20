"""Browser HTTP API integration: real local execution, mock paid model only."""
from __future__ import annotations

import copy
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api_test_tool import web


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("API_TEST_FIXTURE_PORT", "0")
    app = web.create_app(tmp_path / "web-data", start_fixture=True, testing=True)
    with TestClient(app) as browser:
        boot = browser.get("/api/bootstrap")
        assert boot.status_code == 200
        browser.headers["x-csrf-token"] = boot.json()["csrf"]
        yield browser


def _wait(browser, response):
    assert response.status_code == 200, response.text
    jid = response.json()["id"]
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        response = browser.get(f"/api/jobs/{jid}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] in {"completed", "failed"}:
            assert job["status"] == "completed", job
            return job
        time.sleep(0.01)
    pytest.fail("Background API job did not finish within 20 seconds")


def _import_items(browser):
    template = browser.get("/api/templates/items")
    assert template.status_code == 200
    data = template.json()
    imported = browser.post("/api/projects", json={
        "filename": data["filename"], "content": data["content"], "template": "items"})
    assert imported.status_code == 200, imported.text
    assert imported.json()["contract"]["operations"]
    return imported.json()["project"]["id"]


def _run_items(browser):
    pid = _import_items(browser)
    generation = _wait(browser, browser.post(f"/api/projects/{pid}/generate", json={"mode": "baseline"}))
    assert generation["result"]["summary"]["READY"] == 19
    detail = browser.get(f"/api/projects/{pid}").json()
    assert len(detail["bundle"]["cases"]) == 19
    execution = _wait(browser, browser.post(f"/api/projects/{pid}/run", json={}))
    return pid, generation, execution


def test_items_four_stage_http_flow_and_owned_reports(client):
    pid, _, job = _run_items(client)
    run = job["result"]
    assert run["summary"]["PASS"] == 19
    assert run["summary"]["total"] == 19
    assert run["summary"]["complete"] is True
    assert not any(run["summary"][state] for state in ("FAIL", "BROKEN", "BLOCKED", "UNSUPPORTED", "QUARANTINED"))
    result_response = client.get(run["report_url"].replace("index.html", "result.json"))
    assert result_response.status_code == 200
    result = result_response.json()
    assert result["execution"]["case_workers"] == 16
    assert len(result["execution"]["independent_case_ids"]) == 18
    cleaned = [case for case in result["cases"] if case.get("cleanup", {}).get("steps")]
    assert len(cleaned) == 3
    assert all(case["cleanup"]["status"] == "PASS" for case in cleaned)
    assert all([step["response"]["status"] for step in case["cleanup"]["steps"]] == [204, 404]
               for case in cleaned)  # Deletion plus a read proving absence.
    assert result["requests_sent"] > 19
    report = client.get(run["report_url"])
    assert report.status_code == 200
    assert "text/html" in report.headers["content-type"]
    assert "19" in report.text
    snapshot = client.get(run["report_url"].replace("index.html", "bundle.json"))
    assert snapshot.status_code == 200 and len(snapshot.json()["cases"]) == 19
    exported = client.get(f"/api/projects/{pid}/artifacts/bundle.json")
    assert exported.status_code == 200 and "attachment" in exported.headers["content-disposition"]


def test_other_browser_cannot_read_projects_jobs_or_reports(client):
    pid, generation, execution = _run_items(client)
    # A second client shares the running app but has a different cookie jar.
    other = TestClient(client.app)
    try:
        boot = other.get("/api/bootstrap")
        assert boot.status_code == 200
        assert boot.json()["projects"] == []
        assert other.cookies.get("api_test_session") != client.cookies.get("api_test_session")
        shared = other.get(execution["result"]["report_url"])
        assert shared.status_code == 200
        assert 'name="api-test-public-report" content="read-only"' in shared.text
        for route in [f"/api/projects/{pid}", f"/api/jobs/{generation['id']}",
                      f"/api/jobs/{execution['id']}",
                      execution["result"]["report_url"].replace("index.html", "result.json"),
                      f"/api/projects/{pid}/artifacts/bundle.json"]:
            denied = other.get(route)
            assert denied.status_code in {403, 404}, (route, denied.text)
            assert '"PASS":19' not in denied.text
    finally:
        other.close()


def test_mutations_require_matching_csrf_and_origin(client):
    document = client.get("/api/templates/items").json()
    payload = {"filename": document["filename"], "content": document["content"]}
    for headers in ({"x-csrf-token": ""}, {"x-csrf-token": "wrong"},
                    {"origin": "https://another-site.example"}):
        response = client.post("/api/projects", json=payload, headers=headers)
        assert response.status_code == 403
    assert client.get("/api/bootstrap").json()["projects"] == []


@pytest.mark.parametrize("ref_kind", ["absolute", "parent", "remote"])
def test_external_ref_is_rejected_before_parser_reads_files(client, tmp_path, monkeypatch, ref_kind):
    sensitive = tmp_path / "private-schema.yaml"
    sensitive.write_text("type: object\n", encoding="utf-8")
    references = {"absolute": str(sensitive), "parent": "../../private-schema.yaml", "remote": "https://example.com/private-schema.yaml"}
    raw = {"openapi": "3.0.3", "info": {"title": "Unsafe ref", "version": "1"}, "paths": {
        "/safe": {"get": {"responses": {"200": {"description": "ok", "content": {
            "application/json": {"schema": {"$ref": references[ref_kind]}}}}}}}}}
    parser_calls = []
    def forbidden_parser(path):
        parser_calls.append(path)
        pytest.fail("Untrusted cross-file references reached filesystem-aware parser")
    monkeypatch.setattr(web, "parse_document", forbidden_parser)
    response = client.post("/api/projects", json={"filename": "unsafe.json", "content": json.dumps(raw)})
    assert response.status_code == 400
    assert "不会读取服务器文件" in response.json()["detail"]
    assert not parser_calls
    assert client.get("/api/bootstrap").json()["projects"] == []


def test_model_without_user_key_is_rejected_without_model_call(client, monkeypatch):
    pid = _import_items(client)
    calls = []
    def no_model(*args, **kwargs):
        calls.append(True)
        pytest.fail("A model must never be called without explicit user configuration")
    monkeypatch.setattr(web, "generate_text", no_model)
    response = client.post(f"/api/projects/{pid}/generate", json={"mode": "model"})
    assert response.status_code == 400
    assert not calls
    assert client.get(f"/api/projects/{pid}").json()["bundle"] is None
    assert not client.app.state.jobs


@pytest.fixture
def local_probe():
    audit = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            audit.append(self.path)
            body = b'{"ok":true,"count":2}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", audit
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_model_candidate_review_and_real_execution_pipeline(tmp_path, monkeypatch, local_probe):
    target, audit = local_probe
    monkeypatch.setenv("API_TEST_FIXTURE_PORT", "0")
    provider_origin = "http://127.0.0.1:19000"
    app = web.create_app(tmp_path / "model-web", start_fixture=True, testing=True,
                         trusted_model_origins=(provider_origin,), extra_test_origins=(target,))
    model_calls = []
    def fake_model(config, system, prompt, **kwargs):
        model_calls.append(config)
        context = json.loads(prompt)
        contract = context["contract"]
        sid = contract["operations"]["get_probe"]["source_ids"][0]
        source = contract["sources"][sid]["excerpt"]
        expected_schema = contract["operations"]["get_probe"]["responses"]["200"]
        def evidence():
            return [{"source_id": sid, "quote": source}]
        plan = {"schema_version": "1.0", "cases": [{"id": "AI-001-001", "title": "模型生成的读取检查",
            "operation_id": "get_probe", "scenario": "normal", "variables": {}, "steps": [{
                "id": "read", "operation_id": "get_probe", "request": {}, "extract": [],
                "assertions": [{"kind": "status", "expected": 200, "evidence": evidence()},
                    {"kind": "json_schema", "expected": expected_schema, "evidence": evidence()}]}],
            "cleanup_steps": [], "notes": "GET 无持久写操作"}]}
        if context.get("phase") == "design":
            plan["cases"][0]["design"] = {"category": "正向", "inputs": "GET /probe", "procedure": "读取状态", "expected": "200 且字段符合 Schema", "basis": "接口文档"}
        return {"text": json.dumps(plan), "model": config.model, "protocol": config.protocol,
                "usage": {"input_tokens": 10, "output_tokens": 20}}
    monkeypatch.setattr(web, "generate_text", fake_model)
    document = {"openapi": "3.0.3", "info": {"title": "Local probe", "version": "1"}, "paths": {
        "/probe": {"get": {"operationId": "get_probe", "responses": {"200": {
            "description": "A successful status probe", "content": {"application/json": {"schema": {
                "type": "object", "required": ["ok", "count"], "properties": {
                    "ok": {"type": "boolean"}, "count": {"type": "integer"}}}}}}}}}}}
    with TestClient(app) as browser:
        bootstrap = browser.get("/api/bootstrap").json()
        browser.headers["x-csrf-token"] = bootstrap["csrf"]
        key = "unit-test-provider-key-do-not-leak"
        saved = browser.put("/api/model", json={"provider": "custom", "protocol": "openai_chat",
            "base_url": provider_origin + "/v1", "model": "offline-model-double", "api_key": key})
        assert saved.status_code == 200, saved.text
        assert saved.json()["has_key"] is True and key not in saved.text
        imported = browser.post("/api/projects", json={"filename": "probe.json", "content": json.dumps(document)})
        assert imported.status_code == 200, imported.text
        pid = imported.json()["project"]["id"]
        generated = _wait(browser, browser.post(f"/api/projects/{pid}/generate", json={"mode": "model"}))
        assert len(model_calls) == 2
        assert generated["result"]["summary"]["NEEDS_RULE"] == 1
        assert not audit  # Import and generation never call the business API.
        pending = browser.get(f"/api/projects/{pid}").json()["bundle"]
        assert pending["cases"][0]["state"] == "NEEDS_RULE"
        assert pending["cases"][0]["web"]["approval_eligible"] is True
        approved = browser.post(f"/api/projects/{pid}/approve", json={"case_ids": ["AI-001-001"]})
        assert approved.status_code == 200, approved.text
        assert approved.json()["summary"]["READY"] == 1
        assert any(source["kind"] == "user-reviewed" for source in approved.json()["bundle"]["contract"]["sources"].values())
        executed = _wait(browser, browser.post(f"/api/projects/{pid}/run", json={"environment": "custom", "base_url": target}))
        assert executed["result"]["summary"]["PASS"] == 1
        assert audit == ["/probe"]
        result = browser.get(executed["result"]["report_url"].replace("index.html", "result.json"))
        assert result.status_code == 200
        assert result.json()["cases"][0]["steps"][0]["response"]["body"]["count"] == 2
        assert key not in result.text and key not in json.dumps(browser.get("/api/bootstrap").json())
        assert browser.get(executed["result"]["report_url"]).status_code == 200


def test_import_target_selection_persistence_and_cli_export(client):
    doc = json.dumps({'openapi': '3.0.3', 'info': {'title':'地址识别', 'version':'1'},
        'servers': [{'url':'https://first.example.com/v1'}, {'url':'https://second.example.com/api'}],
        'paths': {'/health': {'get': {'responses': {'200': {'description':'OK'}}}}}})
    preview = client.post('/api/document-targets', json={'filename':'api.json','content':doc})
    assert preview.status_code == 200
    assert len(preview.json()['candidates']) == 2
    imported = client.post('/api/projects', json={'filename':'api.json','content':doc}).json()
    pid = imported['project']['id']
    assert imported['project']['task']['base_url'] == 'https://first.example.com/v1'
    changed = client.put(f'/api/projects/{pid}/task', json={'base_url':'https://second.example.com/api/'})
    assert changed.json()['task']['base_url'] == 'https://second.example.com/api'
    # Changing only the Codex goal preserves the selected address.
    client.put(f'/api/projects/{pid}/task', json={'goal':'只检查文档'})
    assert client.get(f'/api/projects/{pid}').json()['project']['task']['base_url'] == 'https://second.example.com/api'
    exported = client.get(f'/api/projects/{pid}/artifacts/environment.json').json()
    assert exported['base_url'] == 'https://second.example.com/api'
    assert exported['allowed_origins'] == ['https://second.example.com']
    manual = client.post('/api/projects', json={'filename':'api.json','content':doc,'task':{'base_url':'https://manual.example.com/v3'}}).json()
    assert manual['project']['task']['base_url'] == 'https://manual.example.com/v3'
    review = client.post('/api/projects', json={'filename':'api.json','content':doc,'task':{'base_url':''}}).json()
    assert review['project']['task']['base_url'] == ''


def test_addressless_document_can_still_be_imported(client):
    response = client.post('/api/projects', json={'filename':'notes.md','content':'# 仅检查接口说明','allow_unparsed':True})
    assert response.status_code == 200
    assert response.json()['project']['task']['base_url'] == ''


def test_import_does_not_contact_or_authorize_document_server(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Import must not contact document servers')
    monkeypatch.setattr(web, 'check_public_endpoint', forbidden)
    response = client.post('/api/projects', json={'filename':'notes.md','content':'Base URL: http://10.20.30.40/api','allow_unparsed':True})
    assert response.status_code == 200
    assert response.json()['project']['task']['base_url'] == 'http://10.20.30.40/api'
