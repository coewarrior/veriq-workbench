"""Behavioral coverage for partial execution and large MCP plans; local HTTP only."""
import copy
import json
import time

from fastapi.testclient import TestClient

from api_test_tool import web
from api_test_tool.execution import run_bundle
from api_test_tool.web_generation import approve_cases, compile_model_bundle
from tests.unit.test_execution import local_api, bundle, step, status
from tests.unit.test_web_generation import contract, proposal


def test_missing_evidence_and_expectations_do_not_reject_other_cases(contract):
    raw = proposal()
    for cid in ("NO-EVIDENCE", "NO-EXPECTED"):
        case = copy.deepcopy(raw["cases"][0])
        case["id"] = cid
        if cid == "NO-EVIDENCE":
            case["steps"][0]["assertions"][0].pop("evidence")
        else:
            case["steps"][0]["assertions"] = []
        raw["cases"].append(case)
    candidates = compile_model_bundle(contract, json.dumps(raw))
    reviewed = approve_cases(candidates, [c["id"] for c in raw["cases"]], partial=True)
    assert [c["state"] for c in reviewed["cases"]] == ["READY", "NEEDS_RULE", "NEEDS_RULE"]
    assert reviewed["web"]["last_review"]["accepted_case_ids"] == ["AI-001"]
    assert {c["id"] for c in reviewed["web"]["last_review"]["skipped_cases"]} == {"NO-EVIDENCE", "NO-EXPECTED"}


def test_login_without_persistent_changes_can_be_reviewed(contract):
    contract["operations"]["get_health"]["method"] = "POST"
    raw = proposal()
    raw["cases"][0]["cleanup_policy"] = {"strategy": "none", "reason": "该登录接口只建立当前用例会话，无持久资源变化"}
    reviewed = approve_cases(compile_model_bundle(contract, json.dumps(raw)), ["AI-001"])
    assert reviewed["cases"][0]["state"] == "READY"
    sid = reviewed["cases"][0]["web"]["review_source_id"]
    assert "cleanup_policy" in reviewed["contract"]["sources"][sid]["excerpt"]


def test_large_mcp_batches_keep_reviews_and_run_beyond_old_request_limit(local_api, tmp_path, monkeypatch):
    env, seen = local_api
    monkeypatch.setattr(web, "generate_text", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("No model calls")))
    app = web.create_app(tmp_path / "data", start_fixture=False, testing=True, extra_test_origins=(env["base_url"],))
    document = {"openapi": "3.0.3", "info": {"title": "批量检查", "version": "1"}, "paths": {"/echo": {"get": {
        "operationId": "read", "responses": {"200": {"description": "value is true", "content": {"application/json": {
            "schema": {"type": "object", "properties": {"value": {"type": "boolean"}}}}}}}}}}}
    with TestClient(app) as browser:
        browser.headers["x-csrf-token"] = browser.get("/api/bootstrap").json()["csrf"]
        token = browser.post("/api/mcp/redeem", json={"code": browser.post("/api/mcp/pair").json()["code"]}).json()["token"]
        def call(action, **args):
            response = browser.post("/api/mcp/call", headers={"Authorization": "Bearer " + token}, json={"action": action, "arguments": args})
            assert response.status_code == 200, response.text
            return response.json()
        imported = call("import", title="大量用例", filename="api.json", content=json.dumps(document))
        pid = imported["project"]["id"]
        context = call("context", project_id=pid)
        op = context["contract"]["operations"]["read"]
        sid = op["source_ids"][0]
        evidence = [{"source_id": sid, "quote": context["contract"]["sources"][sid]["excerpt"]}]
        def candidate(i):
            return {"id": f"C-{i}", "title": "字段值正确", "operation_id": "read", "steps": [{
                "id": "read", "assertions": [{"kind": "json_equal", "pointer": "/value", "expected": True, "evidence": evidence}]}]}
        first = call("submit", project_id=pid, revision=context["revision"], cases=[candidate(i) for i in range(120)])
        reviewed = call("approve", project_id=pid, case_ids=[f"C-{i}" for i in range(120)])
        assert reviewed["summary"]["READY"] == 120
        gap = candidate(240); gap["steps"][0]["assertions"] = []; gap["notes"] = "响应其他规则待确认"
        second = call("submit", project_id=pid, revision=first["revision"], cases=[candidate(i) for i in range(120, 240)] + [gap])
        assert second["summary"]["total"] == 241
        assert second["summary"]["READY"] == 120  # Adding a batch must not revoke previous reviews.
        assert len(second["cases"]) == 121
        page = call("context", project_id=pid, offset=200, limit=50)
        assert page["pagination"] == {"offset": 200, "limit": 50, "total": 241, "next_offset": None}
        assert len(page["candidates"]["cases"]) == 41
        assert page["testing_skill"]["name"] == "api-test-workspace"
        reviewed = call("approve", project_id=pid, case_ids=[f"C-{i}" for i in range(120, 241)])
        assert reviewed["summary"]["READY"] == 240
        assert [c["id"] for c in reviewed["skipped_cases"]] == ["C-240"]
        job = call("run", project_id=pid, environment="custom", base_url=env["base_url"])
        for _ in range(500):
            job = call("job", job_id=job["id"])
            if job["status"] in {"completed", "failed"}: break
            time.sleep(.02)
        assert job["status"] == "completed", job
        report = call("report", project_id=pid)
        assert report["report"]["summary"]["PASS"] == 240
        assert report["report"]["summary"]["BLOCKED"] == 1
        assert len(seen) == 240
        assert browser.get(report["report"]["report_url"]).status_code == 200
        # Updating one case resets just that review, even if other cases are still pending.
        changed = candidate(0); changed["title"] = "更新后的检查"
        final = call("submit", project_id=pid, revision=second["revision"], cases=[changed])
        assert final["summary"]["READY"] == 239


def test_case_validation_error_does_not_block_valid_neighbor(local_api, tmp_path):
    env, seen = local_api
    plan = bundle()
    invalid = copy.deepcopy(plan["cases"][0]); invalid["id"] = "invalid"
    invalid["steps"][0]["request"]["params"] = {"id": "${missing}"}
    plan["cases"].insert(0, invalid)
    result = run_bundle(plan, env, tmp_path)
    assert [c["status"] for c in result["cases"]] == ["BLOCKED", "PASS"]
    assert len(seen) == 1


def test_5xx_and_cleanup_failure_stay_local_to_case(local_api, tmp_path):
    env, seen = local_api
    plan = bundle(step("failed", "/boom"), step("dependent", "/never"))
    plan["cases"][0]["cleanup_steps"] = [step("cleanup", "/cleanup-fail", method="DELETE")]
    later = copy.deepcopy(plan["cases"][0]); later.update(id="independent", steps=[step("healthy", "/echo")], cleanup_steps=[])
    plan["cases"].append(later)
    result = run_bundle(plan, env, tmp_path)
    assert [c["status"] for c in result["cases"]] == ["FAIL", "PASS"]
    assert result["cases"][0]["cleanup"]["status"] == "FAIL"
    assert result["cases"][0]["steps"][1]["status"] == "BLOCKED"
    assert [r["path"] for r in seen] == ["/boom", "/cleanup-fail", "/echo"]


def test_network_error_does_not_hide_healthy_independent_case(local_api, tmp_path, monkeypatch):
    import requests
    env, seen = local_api
    original = requests.Session.send
    sent = []
    def first_request_disconnects(session, request, **kwargs):
        sent.append(request.url)
        if len(sent) == 1:
            raise requests.ConnectionError("Controlled one-request disconnect")
        return original(session, request, **kwargs)
    monkeypatch.setattr(requests.Session, "send", first_request_disconnects)
    plan = bundle()
    later = copy.deepcopy(plan["cases"][0]); later["id"] = "independent"
    plan["cases"].append(later)
    result = run_bundle(plan, env, tmp_path)
    assert [c["status"] for c in result["cases"]] == ["BROKEN", "PASS"]
    assert result["requests_sent"] == 2
    assert len(seen) == 1
