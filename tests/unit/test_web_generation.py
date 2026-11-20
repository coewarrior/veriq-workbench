"""Offline contract/model tests: no provider calls or business HTTP requests."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from api_test_tool.execution import validate_bundle

if Path(__file__).with_name("web_generation.py").exists():
    spec = importlib.util.spec_from_file_location("api_test_tool.web_generation", Path(__file__).with_name("web_generation.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    auto_bundle, approve_cases, compile_model_bundle, model_prompts = (
        module.auto_bundle, module.approve_cases, module.compile_model_bundle, module.model_prompts)
    refresh_approval_eligibility = module.refresh_approval_eligibility
else:
    from api_test_tool.web_generation import auto_bundle, approve_cases, compile_model_bundle, model_prompts, refresh_approval_eligibility


@pytest.fixture
def contract():
    return {"schema_version": "1.0", "title": "测试接口", "sources": {
        "SRC-1": {"path": "/not-read/openapi.yaml", "sha256": "f" * 64,
                  "kind": "openapi-operation", "location": "#/paths/~1health/get",
                  "excerpt": 'GET /health returns 200 and JSON {"ok": true}. Returns a boolean ok.'}},
        "operations": {"get_health": {"id": "get_health", "method": "GET", "path": "/health",
            "parameters": [], "request_schema": {}, "request_example": {}, "auth": {},
            "responses": {"200": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}},
            "response_schema": {"type": "object"}, "source_ids": ["SRC-1"]}}, "issues": []}


def proposal(oid="get_health"):
    return {"schema_version": "1.0", "cases": [{"id": "AI-001", "title": "正常读取", "operation_id": oid,
        "scenario": "normal", "variables": {}, "steps": [{"id": "request", "operation_id": oid,
        "request": {}, "assertions": [{"kind": "status", "expected": 200,
            "evidence": [{"source_id": "SRC-1", "quote": "returns 200"}]}], "extract": []}],
        "cleanup_steps": [], "notes": ""}]}


def compile_plan(contract, plan=None):
    return compile_model_bundle(contract, json.dumps(plan or proposal()))


def test_auto_get_uses_explicit_response(contract):
    original = copy.deepcopy(contract)
    bundle = auto_bundle(contract)
    assert bundle["cases"][0]["state"] == "READY"
    assert [a["kind"] for a in bundle["cases"][0]["steps"][0]["assertions"]] == ["status", "json_schema"]
    assert not validate_bundle(bundle)
    assert contract == original


@pytest.mark.parametrize("change,reason", [
    ({"responses": {}}, "状态码"),
    ({"responses": {"200": {}, "202": {}}}, "多个成功"),
    ({"auth": {"type": "http", "scheme": "bearer"}}, "鉴权"),
    ({"path": "/health/{id}"}, "变量"),
    ({"method": "POST"}, "清理"),
])
def test_auto_gaps_remain_non_executable(contract, change, reason):
    contract["operations"]["get_health"].update(change)
    bundle = auto_bundle(contract)
    assert bundle["cases"][0]["state"] == "NEEDS_RULE"
    assert reason in bundle["cases"][0]["reason"] or reason == "变量" and "variable" in bundle["cases"][0]["reason"]
    with pytest.raises(ValueError):
        approve_cases(bundle, ["AUTO-001"])


def test_auto_required_query_example_is_schema_checked(contract):
    contract["operations"]["get_health"]["parameters"] = [
        {"name": "limit", "in": "query", "required": True, "schema": {"type": "integer", "minimum": 1}, "example": 5}]
    bundle = auto_bundle(contract)
    assert bundle["cases"][0]["state"] == "READY"
    assert bundle["cases"][0]["steps"][0]["request"]["params"] == {"limit": 5}
    contract["operations"]["get_health"]["parameters"][0]["example"] = "wrong type"
    assert auto_bundle(contract)["cases"][0]["state"] == "NEEDS_RULE"


def test_unsupported_schema_is_not_silently_approved(contract):
    contract["issues"] = [{"operation_id": "get_health", "severity": "error", "message": "unsupported ref"}]
    assert auto_bundle(contract)["cases"][0]["state"] == "UNSUPPORTED"
    model = compile_plan(contract)
    assert model["cases"][0]["state"] == "UNSUPPORTED"
    with pytest.raises(ValueError):
        approve_cases(model, ["AI-001"])


def test_model_is_candidate_until_explicit_selection(contract):
    bundle = compile_plan(contract)
    assert bundle["cases"][0]["state"] == "NEEDS_RULE"
    assert bundle["cases"][0]["web"]["approval_eligible"] is True
    assert bundle["rules"][0]["state"] == "needs_review"
    reviewed = approve_cases(bundle, ["AI-001"], "我核对了文档：200")
    assert reviewed["cases"][0]["state"] == "READY"
    assert bundle["cases"][0]["state"] == "NEEDS_RULE"
    assert not validate_bundle(reviewed)
    source = reviewed["contract"]["sources"][reviewed["cases"][0]["web"]["review_source_id"]]
    assert source["kind"] == "user-reviewed"
    assert "200" in source["excerpt"]


def test_only_selected_case_is_approved(contract):
    raw = proposal()
    second = copy.deepcopy(raw["cases"][0]); second["id"] = "AI-002"
    raw["cases"].append(second)
    reviewed = approve_cases(compile_plan(contract, raw), ["AI-001"])
    assert [c["state"] for c in reviewed["cases"]] == ["READY", "NEEDS_RULE"]


def test_independent_policy_is_validated_and_included_in_review_evidence(contract):
    raw = proposal()
    policy = {"mode": "independent", "reason": "读取固定健康状态，无共享账号、数据变化或跨用例时序。"}
    raw["cases"][0]["execution_policy"] = policy
    reviewed = approve_cases(compile_plan(contract, raw), ["AI-001"])
    case = reviewed["cases"][0]
    assert case["execution_policy"] == policy and case["state"] == "READY"
    evidence = json.loads(reviewed["contract"]["sources"][case["web"]["review_source_id"]]["excerpt"])
    assert evidence["execution_policy"] == policy
    assert not validate_bundle(reviewed)


@pytest.mark.parametrize("policy", [True, [], {"mode": []}, {"mode": "independent"},
                                    {"mode": "independent", "reason": " "},
                                    {"mode": "serial", "reason": 123},
                                    {"mode": "independent", "reason": "isolated", "threads": 1000}])
def test_invalid_concurrency_policy_is_rejected_without_executing(contract, policy):
    raw = proposal()
    raw["cases"][0]["execution_policy"] = policy
    with pytest.raises(ValueError):
        compile_plan(contract, raw)


@pytest.mark.parametrize("evidence", [
    [{"source_id": "SRC-invented", "quote": "returns 200"}],
    [{"source_id": "SRC-1", "quote": "returns 404"}],
    [{"source_id": "SRC-1", "quote": ""}],
    [{"source_id": "SRC-1", "quote": "returns 200", "file": "/etc/passwd"}],
])
def test_fabricated_or_path_sources_rejected(contract, evidence):
    raw = proposal()
    raw["cases"][0]["steps"][0]["assertions"][0]["evidence"] = evidence
    with pytest.raises(ValueError):
        compile_plan(contract, raw)


@pytest.mark.parametrize("path", ["http://attacker.example/health", "//attacker.example/health", "/../health", "/%2e%2e/health", "/other", "/health?target=evil"])
def test_path_escape_is_rejected(contract, path):
    raw = proposal()
    raw["cases"][0]["steps"][0]["request"]["path"] = path
    with pytest.raises(ValueError):
        compile_plan(contract, raw)


def test_unknown_interface_or_executable_extension_is_rejected(contract):
    with pytest.raises(ValueError):
        compile_plan(contract, proposal("invented"))
    raw = proposal(); raw["cases"][0]["steps"][0]["request"]["python"] = "print(1)"
    with pytest.raises(ValueError):
        compile_plan(contract, raw)
    raw = proposal(); raw["cases"][0]["variables"] = {"x": {"kind": "environment", "value": "HOME"}}
    with pytest.raises(ValueError):
        compile_plan(contract, raw)


def test_unresolved_variables_are_visible_and_not_approvable(contract):
    raw = proposal(); raw["cases"][0]["steps"][0]["request"]["params"] = {"id": "${item_id}"}
    bundle = compile_plan(contract, raw)
    assert not bundle["cases"][0]["web"]["approval_eligible"]
    with pytest.raises(ValueError, match="结构缺口"):
        approve_cases(bundle, ["AI-001"])


def test_missing_expected_stays_gap(contract):
    raw = proposal(); raw["cases"][0]["steps"][0]["assertions"] = []
    bundle = compile_plan(contract, raw)
    assert bundle["cases"][0]["state"] == "NEEDS_RULE"
    assert not bundle["cases"][0]["web"]["approval_eligible"]
    with pytest.raises(ValueError):
        approve_cases(bundle, ["AI-001"])


def test_documented_body_expectation_does_not_require_invented_status(contract):
    raw = proposal()
    raw["cases"][0]["steps"][0]["assertions"] = [{"kind": "json_exists", "pointer": "/ok",
        "evidence": [{"source_id": "SRC-1", "quote": "boolean ok"}]}]
    bundle = compile_plan(contract, raw)
    assert bundle["cases"][0]["state"] == "NEEDS_RULE"
    assert bundle["cases"][0]["web"]["approval_eligible"]
    reviewed = approve_cases(bundle, ["AI-001"])
    assert reviewed["cases"][0]["state"] == "READY"
    assert not validate_bundle(reviewed)


def gomoku_contract(contract):
    new = copy.deepcopy(contract)
    for oid, method, path in [("get_info", "GET", "/info"), ("post_reg", "POST", "/reg"), ("post_login", "POST", "/login")]:
        new["operations"][oid] = copy.deepcopy(new["operations"]["get_health"])
        new["operations"][oid].update(id=oid, method=method, path=path)
    return new


@pytest.mark.parametrize("token", ["", "abc", "-1", "99999999", "9" * 1000, "1 OR 1=1", "${ssid}"])
def test_bad_ssid_category_cannot_be_approved(contract, token):
    raw = proposal("get_info"); raw["cases"][0]["steps"][0]["request"]["headers"] = {"Cookie": "SSID=" + token}
    raw["cases"][0]["variables"] = {"ssid": {"kind": "unique", "prefix": "x_"}}
    bundle = compile_plan(gomoku_contract(contract), raw)
    assert bundle["cases"][0]["state"] == "QUARANTINED"
    with pytest.raises(ValueError):
        approve_cases(bundle, ["AI-001"])


@pytest.mark.parametrize("username", [" ", "x"])
def test_fixed_gomoku_username_boundary_stays_isolated(contract, username):
    raw = proposal("post_reg"); raw["cases"][0]["steps"][0]["request"]["json"] = {"username": username, "password": "test"}
    bundle = compile_plan(gomoku_contract(contract), raw)
    assert bundle["cases"][0]["state"] == "QUARANTINED"


def test_trusted_cleanup_marker_can_reassess_owned_gomoku_case(contract):
    raw = proposal("post_reg")
    raw["cases"][0]["variables"] = {"username": {"kind": "unique", "prefix": "mvp_"}}
    raw["cases"][0]["steps"][0]["request"]["json"] = {"username": "${username}", "password": "test"}
    bundle = compile_plan(gomoku_contract(contract), raw)
    assert not bundle["cases"][0]["web"]["approval_eligible"]
    with pytest.raises(ValueError):
        approve_cases(bundle, ["AI-001"])
    bundle["web"]["trusted_cleanup"] = "gomoku"  # server-authorized only
    refreshed = refresh_approval_eligibility(bundle)
    assert refreshed["cases"][0]["web"]["approval_eligible"] is True
    assert refreshed["cases"][0]["state"] == "NEEDS_RULE"
    assert bundle["cases"][0]["web"]["approval_eligible"] is False
    assert approve_cases(bundle, ["AI-001"])["cases"][0]["state"] == "READY"
    bundle["cases"][0]["steps"][0]["request"]["json"]["username"] = "fixed-user"
    with pytest.raises(ValueError):
        approve_cases(bundle, ["AI-001"])
    raw["web"] = {"trusted_cleanup": "gomoku"}
    with pytest.raises(ValueError):
        compile_plan(gomoku_contract(contract), raw)


@pytest.mark.parametrize("path,oid,payload", [
    ("/%69nfo", "get_info", {"headers": {"Cookie": "SSID=abc"}}),
    ("/%2569nfo", "get_info", {"headers": {"Cookie": "SSID=abc"}}),
    ("/%72eg", "post_reg", {"json": {"username": "x", "password": "test"}}),
])
def test_encoded_known_paths_cannot_bypass_quarantine(contract, path, oid, payload):
    adapted = gomoku_contract(contract)
    adapted["operations"][oid]["path"] = path
    raw = proposal(oid)
    raw["cases"][0]["steps"][0]["request"] = payload
    bundle = compile_plan(adapted, raw)
    assert bundle["cases"][0]["state"] == "QUARANTINED"
    assert refresh_approval_eligibility(bundle)["cases"][0]["web"]["approval_eligible"] is False
    with pytest.raises(ValueError):
        approve_cases(bundle, ["AI-001"])


def test_path_extraction_preserves_variable_name_and_json_types(contract):
    contract["operations"]["get_health"]["path"] = "/items/{id}"
    raw = proposal()
    case = raw["cases"][0]
    case["variables"] = {"item_id": {"kind": "literal", "value": 17}}
    case["steps"][0]["request"] = {"path": "/items/${item_id}"}
    case["steps"][0]["assertions"].append({"kind": "json_schema", "expected": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}, "evidence": [{"source_id": "SRC-1", "quote": "boolean ok"}]})
    bundle = approve_cases(compile_plan(contract, raw), ["AI-001"])
    assert not validate_bundle(bundle)
    assert bundle["cases"][0]["variables"]["item_id"]["value"] == 17


@pytest.mark.parametrize("schema", [{"type": "not-json"}, {"$ref": "file:///etc/passwd"}, {"format": "unrecognized-format"}, "object"])
def test_bad_or_remote_json_schema_is_rejected(contract, schema):
    raw = proposal()
    raw["cases"][0]["steps"][0]["assertions"][0].update(kind="json_schema", expected=schema)
    with pytest.raises(ValueError):
        compile_plan(contract, raw)


@pytest.mark.parametrize("schema", [
    {"type": "string", "pattern": "^(a+)+$"},
    {"type": "object", "patternProperties": {"^(a+)+$": {"type": "string"}}},
    {"type": "object", "properties": {"value": {"type": "string", "pattern": "(a|aa)+$"}}},
])
def test_regex_schema_never_reaches_auto_or_model_execution(contract, schema):
    contract["operations"]["get_health"]["responses"]["200"] = schema
    assert auto_bundle(contract)["cases"][0]["state"] == "UNSUPPORTED"
    raw = proposal()
    raw["cases"][0]["steps"][0]["assertions"].append({"kind": "json_schema", "expected": schema,
        "evidence": [{"source_id": "SRC-1", "quote": "returns 200"}]})
    bundle = compile_plan(contract, raw)
    assert bundle["cases"][0]["state"] == "UNSUPPORTED"
    assert not refresh_approval_eligibility(bundle)["cases"][0]["web"]["approval_eligible"]
    with pytest.raises(ValueError):
        approve_cases(bundle, ["AI-001"])


def test_strict_json_rejects_duplicates_nonfinite_and_excess_cases(contract):
    for text in ['{"schema_version":"1.0","schema_version":"2.0","cases":[]}',
                 '{"schema_version":"1.0","cases":[],"x":NaN}', "text {\"cases\":[]}"]:
        with pytest.raises(ValueError):
            compile_model_bundle(contract, text)
    raw = proposal(); raw["cases"] *= 41
    with pytest.raises(ValueError):
        compile_plan(contract, raw)
    fenced = "```json\n" + json.dumps(proposal()) + "\n```"
    assert compile_model_bundle(contract, fenced)["cases"][0]["state"] == "NEEDS_RULE"


def test_prompt_does_not_lose_source_or_mutate_contract(contract):
    before = copy.deepcopy(contract)
    system, user = model_prompts(contract, "document", "补充")
    assert "逐字" in system and "cleanup_steps" in system
    data = json.loads(user)
    assert data["contract"] == before
    assert data["supplement"] == "补充"
    assert contract == before
