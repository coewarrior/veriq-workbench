"""Executor checks use a disposable loopback server, never the shared service."""

import copy
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from api_test_tool.assertions import MISSING, resolve_pointer, strict_equal
from api_test_tool.execution import render_template, run_bundle, validate_bundle


@pytest.fixture
def local_api():
    seen = []
    users = {}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            self.do_GET()

        def do_DELETE(self):
            self.do_GET()

        def do_GET(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = json.loads(raw) if raw else MISSING
            seen.append({"path": self.path, "method": self.command, "body": body, "cookie": self.headers.get("Cookie"), "authorization": self.headers.get("Authorization")})
            headers = {}
            status = 200
            if self.path == "/session":
                username = body["username"]
                users["test-cookie-secret"] = username
                headers = {"Set-Cookie": "SSID=test-cookie-secret; Path=/; HttpOnly", "X-Access-Token": "test-token-secret"}
                value = {"username": username, "token": "test-token-secret"}
            elif self.path == "/who":
                value = {"username": users.get("test-cookie-secret") if self.headers.get("Cookie") else None}
            elif self.path == "/boom":
                status, value = 503, {"error": "unavailable"}
            elif self.path == "/cleanup-fail":
                status, value = 400, {"error": "Cleanup rejected"}
            elif self.path == "/huge":
                value = {"data": "x" * 4096}
            elif self.path == "/redirect":
                status, value, headers = 302, {}, {"Location": "/followed"}
            elif self.path == "/text":
                value = b"not JSON"
            elif self.path == "/empty-password":
                status, value = (400, {"accepted": False}) if body["password"] == "" else (200, {"accepted": True})
            else:
                value = {"received": None if body is MISSING else body, "present_null": None, "value": True, "array": [1]}
            payload = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            for key, val in headers.items():
                self.send_header(key, val)
            self.end_headers()
            self.wfile.write(payload)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    yield {"name": "unit-loopback", "base_url": origin, "allowed_origins": [origin], "timeout": 2, "max_requests": 50, "max_response_bytes": 2048}, seen
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def status(expected=200):
    return {"kind": "status", "expected": expected, "rule_id": "R-1"}


def step(sid="read", path="/echo", assertions=None, **request):
    return {"id": sid, "request": {"method": "GET", "path": path, **request}, "assertions": assertions if assertions is not None else [status()], "extract": []}


def bundle(*steps):
    return {"schema_version": "1.0", "title": "loopback contract", "contract": {"sources": {"S-1": {"path": "fixture.md", "sha256": "a" * 64, "location": "1", "excerpt": "Fixture contract"}}, "operations": {}}, "rules": [{"id": "R-1", "state": "documented", "source_ids": ["S-1"], "description": "Public loopback test contract"}], "cases": [{"id": "C-1", "title": "Fixture request", "operation_id": "echo", "scenario": "normal", "state": "READY", "reason": "", "rule_ids": ["R-1"], "variables": {}, "steps": list(steps or [step()]), "cleanup_steps": []}], "generation": {"engine": "rules-v1", "seed": 42}}


def test_strict_types_and_pointer_missing_null():
    assert not strict_equal(True, 1)
    assert not strict_equal(1.0, 1)
    assert not strict_equal({"v": [True]}, {"v": [1]})
    assert strict_equal({"v": [None, False]}, {"v": [None, False]})
    assert resolve_pointer({"a/b": {"~": None}}, "/a~1b/~0") is None
    assert resolve_pointer({"a": None}, "/missing") is MISSING
    assert resolve_pointer([1], "/00") is MISSING
    assert resolve_pointer([1], "/0") == 1


def test_network_factory_failure_preserves_previous_evidence(local_api, tmp_path):
    from api_test_tool.execution import _session
    env, seen = local_api
    plan = bundle()
    for index in (2, 3):
        case = copy.deepcopy(plan["cases"][0])
        case["id"] = f"C-{index}"
        plan["cases"].append(case)
    created = 0
    def factory():
        nonlocal created
        created += 1
        if created > 1:
            raise ValueError("DNS destination no longer approved")
        return _session()
    result = run_bundle(plan, env, tmp_path, session_factory=factory)
    assert [case["status"] for case in result["cases"]] == ["PASS", "BROKEN", "BLOCKED"]
    assert len(seen) == 1
    assert (tmp_path / "result.json").is_file()
    assert result["requests_sent"] == 1


def test_typed_template_and_missing_dependency():
    values = {"n": 12, "items": [1, True], "nil": None}
    assert render_template({"n": "${n}", "items": "${items}", "v": "n=${n};nil=${nil}"}, values) == {"n": 12, "items": [1, True], "v": "n=12;nil=null"}
    with pytest.raises(ValueError, match="non-scalar"):
        render_template("items=${items}", values)
    invalid = bundle(step(json={"n": "${later}"}))
    assert any("unavailable template" in error["message"] for error in validate_bundle(invalid))


@pytest.mark.parametrize("alter", [
    lambda b: b["cases"][0]["steps"][0]["request"].update(path="https://example.com"),
    lambda b: b["cases"][0]["steps"][0]["request"].update(path="//example.com"),
    lambda b: b["cases"][0]["steps"][0]["request"].update(path="/%2e%2e/private"),
    lambda b: b["cases"][0]["steps"][0]["request"].update(headers={"Host": "example.com"}),
    lambda b: b["cases"][0]["steps"][0]["request"].update(json=None, raw_body="null"),
    lambda b: b["cases"][0]["steps"][0]["assertions"][0].update(expected=[200, 400]),
    lambda b: b["cases"][0]["steps"][0]["assertions"][0].update(kind="python_eval"),
    lambda b: b["cases"][0]["steps"][0]["assertions"][0].update(kind=["status"]),
    lambda b: b["cases"][0]["steps"][0]["assertions"][0].update(rule_id="unknown"),
    lambda b: b["rules"][0].update(state="needs_review"),
    lambda b: b["rules"][0].update(source_ids=[]),
    lambda b: b["cases"][0]["variables"].update(token={"kind": "literal", "value": "<redacted>"}),
    lambda b: b["cases"][0]["steps"][0].update(assertions=[{"kind": "json_schema", "expected": {"$ref": "https://example.com/schema"}, "rule_id": "R-1"}]),
    lambda b: b["cases"][0]["steps"][0].update(assertions=[{"kind": "json_schema", "expected": {"type": "object", "nullable": True}, "rule_id": "R-1"}]),
    lambda b: b["cases"][0]["steps"][0].update(assertions=[{"kind": "json_schema", "expected": {"type": "string", "format": "unknown-custom-format"}, "rule_id": "R-1"}]),
])
def test_invalid_plan_sends_no_requests(alter, local_api, tmp_path):
    config, seen = local_api
    frozen = bundle()
    alter(frozen)
    assert validate_bundle(frozen)
    called = []
    result = run_bundle(frozen, config, tmp_path, cleanup_callback=lambda contexts: called.append(contexts) or {"status": "PASS", "details": "done"})
    assert result["validation_errors"]
    assert result["summary"]["BLOCKED"] == 1
    assert result["requests_sent"] == 0
    assert called == [[]]
    assert seen == []


def test_invalid_origin_prevents_requests(local_api, tmp_path):
    config, seen = local_api
    config["allowed_origins"] = ["http://localhost:1"]
    result = run_bundle(bundle(), config, tmp_path)
    assert result["summary"]["BLOCKED"] == 1
    assert not seen


def test_session_isolation_typed_body_extract_and_cleanup(local_api, tmp_path):
    config, seen = local_api
    login = step("login", "/session", method="POST", json={"username": "${username}", "password": "${password}", "count": "${count}"}, assertions=[status(), {"kind": "cookie_present", "name": "SSID", "rule_id": "R-1"}])
    login["extract"] = [{"name": "token", "from": "json", "pointer": "/token"}, {"name": "header_token", "from": "header", "key": "X-Access-Token"}, {"name": "ssid", "from": "cookie", "key": "SSID"}]
    who = step("who", "/who", assertions=[status(), {"kind": "equals_variable", "pointer": "/username", "variable": "username", "rule_id": "R-1"}], headers={"Authorization": "Bearer ${token}"})
    fresh = step("fresh", "/who", session=False, assertions=[status(), {"kind": "json_equal", "pointer": "/username", "expected": None, "rule_id": "R-1"}])
    frozen = bundle(login, who, fresh)
    frozen["cases"][0]["variables"] = {"username": {"kind": "unique", "prefix": "mvp_"}, "password": {"kind": "unique", "prefix": "mvp_"}, "count": {"kind": "literal", "value": 7}}
    frozen["cases"][0]["cleanup_steps"] = [step("cleanup", "/echo", method="DELETE", headers={"Authorization": "Bearer ${token}"})]
    other = copy.deepcopy(frozen["cases"][0])
    other["id"] = "C-2"
    frozen["cases"].append(other)
    contexts = []
    result = run_bundle(frozen, config, tmp_path, cleanup_callback=lambda value: contexts.extend(value) or {"status": "PASS", "details": "cleaned"})
    assert result["summary"]["PASS"] == 2, result
    assert result["summary"]["complete"] is True
    assert seen[0]["body"]["count"] == 7
    assert seen[0]["cookie"] is None
    assert seen[1]["cookie"] == "SSID=test-cookie-secret"
    assert seen[2]["cookie"] is None
    assert seen[4]["cookie"] is None
    assert contexts[0]["variables"]["username"] != contexts[1]["variables"]["username"]
    persisted = (tmp_path / "result.json").read_text()
    assert "test-cookie-secret" not in persisted
    assert "test-token-secret" not in persisted
    assert contexts[0]["variables"]["password"] not in persisted
    saved = json.loads((tmp_path / "bundle.json").read_text())
    assert validate_bundle(saved) == []
    assert saved["cases"][0]["variables"]["password"]["kind"] == "unique"
    replay = run_bundle(saved, config, tmp_path / "replay")
    assert replay["summary"]["PASS"] == 2


def test_null_body_and_absent_body_are_distinct(local_api, tmp_path):
    config, seen = local_api
    result = run_bundle(bundle(step("null", json=None), step("absent")), config, tmp_path)
    assert result["summary"]["PASS"] == 1
    assert seen[0]["body"] is None
    assert seen[1]["body"] is MISSING


def test_empty_password_frozen_replay_preserves_boundary(local_api, tmp_path):
    config, seen = local_api
    frozen = bundle(step("empty", "/empty-password", method="POST", json={"password": ""}, assertions=[status(400)]))
    assert run_bundle(frozen, config, tmp_path)["summary"]["PASS"] == 1
    saved = json.loads((tmp_path / "bundle.json").read_text())
    assert saved["cases"][0]["steps"][0]["request"]["json"]["password"] == ""
    assert run_bundle(saved, config, tmp_path / "replay")["summary"]["PASS"] == 1
    assert all(request["body"]["password"] == "" for request in seen)


def test_5xx_stops_business_but_runs_finally_cleanup(local_api, tmp_path):
    config, seen = local_api
    config["stop_on_5xx"] = True  # Explicit fail-fast remains available to CLI callers.
    frozen = bundle(step("boom", "/boom"), step("never", "/never"))
    frozen["cases"][0]["cleanup_steps"] = [step("cleanup", "/cleanup", method="DELETE")]
    next_case = copy.deepcopy(frozen["cases"][0])
    next_case.update(id="C-2", steps=[step(path="/also-never")], cleanup_steps=[])
    frozen["cases"].append(next_case)
    calls = []
    result = run_bundle(frozen, config, tmp_path, cleanup_callback=lambda contexts: calls.append(contexts) or {"status": "PASS", "details": "done"})
    assert result["summary"]["FAIL"] == 1
    assert result["summary"]["BLOCKED"] == 1
    assert [request["path"] for request in seen] == ["/boom", "/cleanup"]
    assert len(calls) == 1
    assert result["cases"][0]["cleanup"]["status"] == "PASS"


def test_request_budget_includes_cleanup(local_api, tmp_path):
    config, seen = local_api
    config["max_requests"] = 1
    frozen = bundle()
    frozen["cases"][0]["cleanup_steps"] = [step("cleanup", "/cleanup")]
    result = run_bundle(frozen, config, tmp_path)
    assert result["summary"]["PASS"] == 1
    assert result["cases"][0]["cleanup"]["status"] == "FAIL"
    assert result["summary"]["complete"] is False
    assert len(seen) == 1


def test_cleanup_400_blocks_later_business_and_preserves_failure(local_api, tmp_path):
    config, seen = local_api
    config["stop_on_cleanup_failure"] = True
    frozen = bundle(step(assertions=[status(201)]))
    frozen["cases"][0]["cleanup_steps"] = [step("cleanup", "/cleanup-fail", method="DELETE")]
    later = copy.deepcopy(frozen["cases"][0])
    later.update(id="C-2", steps=[step(path="/never")], cleanup_steps=[])
    frozen["cases"].append(later)
    result = run_bundle(frozen, config, tmp_path)
    assert result["summary"]["FAIL"] == 1
    assert result["summary"]["BLOCKED"] == 1
    assert result["cases"][0]["status"] == "FAIL"
    assert result["cases"][0]["cleanup"]["status"] == "FAIL"
    assert result["cases"][0]["cleanup"]["steps"][0]["response"]["status"] == 400
    assert "cleanup failed" in result["cases"][1]["reason"]
    assert [item["path"] for item in seen] == ["/echo", "/cleanup-fail"]


def test_persisted_provenance_records_versions_and_canonical_hash(local_api, tmp_path):
    config, _ = local_api
    frozen = bundle()
    result = run_bundle(frozen, config, tmp_path)
    canonical = json.dumps(frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    provenance = result["provenance"]
    assert provenance["bundle_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert provenance["python_version"]
    assert provenance["dependencies"]["requests"] != "not-installed"
    for filename in ("execution.py", "assertions.py"):
        assert len(provenance["code_sha256"][filename]) == 64
    persisted = json.loads((tmp_path / "result.json").read_text())
    assert persisted["provenance"] == provenance


def test_nonready_cases_are_visible_without_blocking_ready(local_api, tmp_path):
    config, seen = local_api
    frozen = bundle()
    for state in ("NEEDS_RULE", "QUARANTINED", "UNSUPPORTED"):
        case = copy.deepcopy(frozen["cases"][0])
        case.update(id=state, state=state, reason="Not eligible", rule_ids=[], steps=[])
        frozen["cases"].append(case)
    result = run_bundle(frozen, config, tmp_path)
    assert result["summary"] == {"PASS": 1, "FAIL": 0, "BROKEN": 0, "BLOCKED": 1, "QUARANTINED": 1, "UNSUPPORTED": 1, "total": 4, "complete": False}
    assert len(seen) == 1


def test_response_limit_and_required_extract_fail_with_evidence(local_api, tmp_path):
    config, _ = local_api
    too_large = run_bundle(bundle(step(path="/huge")), config, tmp_path / "large")
    assert too_large["summary"]["BROKEN"] == 1
    assert "max_response_bytes" in too_large["cases"][0]["steps"][0]["error"]
    missing = step(path="/echo")
    missing["extract"] = [{"name": "resource_id", "from": "json", "pointer": "/absent"}]
    outcome = run_bundle(bundle(missing), config, tmp_path / "extract")
    assert outcome["summary"]["BROKEN"] == 1
    assert "Required extraction" in outcome["cases"][0]["steps"][0]["error"]
    assert outcome["cases"][0]["steps"][0]["response"]["status"] == 200


def test_json_type_mismatch_and_nonjson_response_fail(local_api, tmp_path):
    config, _ = local_api
    expected_integer = {"kind": "json_equal", "pointer": "/value", "expected": 1, "rule_id": "R-1"}
    result = run_bundle(bundle(step(assertions=[status(), expected_integer])), config, tmp_path / "type")
    assert result["summary"]["FAIL"] == 1
    assert result["cases"][0]["steps"][0]["assertions"][1]["actual"] is True
    schema = {"kind": "json_schema", "expected": {"type": "object", "required": ["id"]}, "rule_id": "R-1"}
    result = run_bundle(bundle(step(path="/text", assertions=[status(), schema])), config, tmp_path / "text")
    assert result["summary"]["FAIL"] == 1
    assert result["cases"][0]["steps"][0]["response"]["body"] == "not JSON"


def test_redirects_are_never_followed(local_api, tmp_path):
    config, seen = local_api
    result = run_bundle(bundle(step(path="/redirect", assertions=[status(302)])), config, tmp_path)
    assert result["summary"]["PASS"] == 1
    assert [item["path"] for item in seen] == ["/redirect"]


def test_known_jsonschema_format_is_enforced(local_api, tmp_path):
    config, _ = local_api
    assertion = {"kind": "json_schema", "expected": {"type": "object", "properties": {"received": {"type": "object", "properties": {"email": {"type": "string", "format": "email"}}}}}, "rule_id": "R-1"}
    result = run_bundle(bundle(step(method="POST", json={"email": "invalid"}, assertions=[status(), assertion])), config, tmp_path)
    assert result["summary"]["FAIL"] == 1
    assert "email" in result["cases"][0]["steps"][0]["assertions"][1]["message"]


def test_connection_failure_stops_remaining_cases_and_cleans(local_api, tmp_path, monkeypatch):
    import requests
    config, seen = local_api
    config["stop_on_network_error"] = True
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("Controlled mock outage")
    monkeypatch.setattr(requests.Session, "send", unavailable)
    frozen = bundle()
    second = copy.deepcopy(frozen["cases"][0])
    second["id"] = "C-2"
    frozen["cases"].append(second)
    calls = []
    result = run_bundle(frozen, config, tmp_path, cleanup_callback=lambda contexts: calls.append(contexts) or {"status": "PASS", "details": "done"})
    assert result["summary"]["BROKEN"] == 1
    assert result["summary"]["BLOCKED"] == 1
    assert result["requests_sent"] == 1
    assert len(calls) == 1
    assert not seen


def test_base_url_prefix_is_used_by_real_requests(local_api, tmp_path):
    config, seen = local_api
    config['base_url'] += '/v1/'
    result = run_bundle(bundle(step(path='/echo')), config, tmp_path / 'prefix')
    assert result['summary']['PASS'] == 1
    assert [request['path'] for request in seen] == ['/v1/echo']


def test_response_branch_schema_renders_owned_identity_template(local_api, tmp_path):
    config, seen = local_api
    assertion={'kind':'response_schema','rule_id':'R-1','expected':{
        'type':'object','required':['status','json'],'properties':{
            'status':{'const':200},'json':{'type':'object','required':['username'],
            'properties':{'username':{'const':'${username}'}}}}}}
    frozen=bundle(step(path='/session',method='POST',json={'username':'${username}'},assertions=[assertion]))
    frozen['cases'][0]['variables']={'username':{'kind':'unique','prefix':'mvp_'}}
    result=run_bundle(frozen,config,tmp_path)
    assert result['summary']['PASS']==1
    assert result['cases'][0]['steps'][0]['assertions'][0]['expected']['properties']['json']['properties']['username']['const']==seen[0]['body']['username']
