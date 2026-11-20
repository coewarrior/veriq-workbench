from __future__ import annotations

import copy
import hashlib
from collections import Counter
from pathlib import Path

import pytest
import yaml

from api_test_tool.generation import generate_bundle
from api_test_tool.parsers import parse_document

ROOT = Path(__file__).resolve().parents[2]


def write_yaml(path, value):
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def minimal_contract(tmp_path, schema=None):
    path = write_yaml(tmp_path / "api.yaml", {
        "openapi": "3.0.3", "info": {"title": "demo", "version": "1"},
        "paths": {"/things": {"post": {"operationId": "createThing",
            "requestBody": {"content": {"application/json": {"schema": schema or {
                "type": "object", "required": ["name", "count"], "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 5},
                    "count": {"type": "integer", "minimum": 1, "maximum": 5}}}}}},
            "responses": {201: {"description": "created"}, 422: {"description": "invalid"}}}}}})
    return parse_document(path)


def minimal_rules(tmp_path, generate=None):
    return write_yaml(tmp_path / "rules.yaml", {"schema_version": "1.0", "rules": [
        {"id": "R-OK", "state": "documented", "description": "Created", "sources": [
            {"file": "api.yaml", "anchor": "#/paths/~1things/post/responses/201"}],
            "assertions": [{"kind": "status", "expected": 201}]},
        {"id": "R-INVALID", "state": "documented", "description": "Rejected", "sources": [
            {"file": "api.yaml", "anchor": "#/paths/~1things/post/responses/422"}],
            "assertions": [{"kind": "status", "expected": 422}]}],
        "profiles": [{"id": "things", "operation_id": "createThing", "rule_ids": ["R-OK"],
            "request": {"json": {"name": "test", "count": 2}},
            "generate": generate or [{"scenario": "normal"}]}]})


def test_reads_actual_markdown_fields_without_sample_constants():
    document = ROOT / "examples/gomoku/evidence/接口文档.md"
    contract = parse_document(document)
    assert list(contract["operations"]) == ["post_reg", "post_login", "get_info"]
    register = contract["operations"]["post_reg"]
    assert register["request_schema"]["required"] == ["username", "password"]
    assert register["response_schema"]["properties"]["result"] == {"type": "boolean"}
    assert "const" not in register["response_schema"]["properties"]["reason"]
    info = contract["operations"]["get_info"]
    assert info["auth"] == {"type": "apiKey", "in": "cookie", "name": "SSID"}
    assert info["response_schema"]["properties"]["score"] == {"type": "integer"}
    digest = hashlib.sha256(document.read_bytes()).hexdigest()
    assert all(source["sha256"] == digest for source in contract["sources"].values())
    assert any("lines" in source["location"] for source in contract["sources"].values())


def test_local_references_resolve_with_source_bytes(tmp_path):
    model = write_yaml(tmp_path / "models.yaml", {"Thing": {"type": "object", "required": ["name"],
        "properties": {"name": {"type": "string", "maxLength": 7}}}})
    contract = minimal_contract(tmp_path, {"$ref": "models.yaml#/Thing"})
    assert contract["operations"]["createThing"]["request_schema"]["properties"]["name"]["maxLength"] == 7
    assert not contract["issues"]
    assert any(source["path"] == str(model) and source["location"] == "#/Thing" for source in contract["sources"].values())


@pytest.mark.parametrize("schema", [
    {"$ref": "https://example.invalid/schema.json"},
    {"oneOf": [{"type": "string"}, {"type": "integer"}]},
    {"type": "string", "format": "email"},
])
def test_unsupported_semantics_are_visible_and_stop_affected_cases(tmp_path, schema):
    contract = minimal_contract(tmp_path, schema)
    bundle = generate_bundle(contract, minimal_rules(tmp_path))
    assert bundle["cases"][0]["state"] == "UNSUPPORTED"
    assert any(issue["code"] == "UNSUPPORTED_OPENAPI" for issue in bundle["issues"])


def test_cyclic_ref_is_not_silently_truncated(tmp_path):
    write_yaml(tmp_path / "cycle.yaml", {"Node": {"type": "object", "properties": {
        "child": {"$ref": "#/Node"}}}})
    contract = minimal_contract(tmp_path, {"$ref": "cycle.yaml#/Node"})
    assert any("Cyclic" in issue["message"] for issue in contract["issues"])


def test_mutations_preserve_absent_null_wrong_type_and_explicit_boundaries(tmp_path):
    contract = minimal_contract(tmp_path)
    rules = minimal_rules(tmp_path, [
        {"scenario": "missing", "fields": ["name"], "rule_ids": ["R-INVALID"]},
        {"scenario": "null", "fields": ["name"], "rule_ids": ["R-INVALID"]},
        {"scenario": "wrong_type", "fields": ["count"], "values": [True], "rule_ids": ["R-INVALID"]},
        {"scenario": "boundary", "fields": ["count"], "values": [0, 6], "rule_ids": ["R-INVALID"]},
    ])
    bundle = generate_bundle(contract, rules)
    bodies = [case["steps"][0]["request"]["json"] for case in bundle["cases"]]
    assert "name" not in bodies[0]
    assert bodies[1]["name"] is None
    assert bodies[2]["count"] is True
    assert [body["count"] for body in bodies[3:]] == [0, 6]
    assert {case["state"] for case in bundle["cases"]} == {"READY"}


def test_auto_boundaries_are_candidates_until_expectations_are_grouped(tmp_path):
    contract = minimal_contract(tmp_path)
    bundle = generate_bundle(contract, minimal_rules(tmp_path, [{"scenario": "boundary", "fields": ["count"]}]))
    assert {case["state"] for case in bundle["cases"]} == {"NEEDS_RULE"}
    assert len(bundle["cases"]) == 4


def test_invalid_source_or_unreviewed_rule_never_becomes_ready(tmp_path):
    contract = minimal_contract(tmp_path)
    path = minimal_rules(tmp_path)
    config = yaml.safe_load(path.read_text())
    config["rules"][0]["sources"][0]["anchor"] = "missing anchor"
    write_yaml(path, config)
    bundle = generate_bundle(contract, path)
    assert bundle["rules"][0]["state"] == "needs_review"
    assert bundle["cases"][0]["state"] == "NEEDS_RULE"
    assert any(issue["code"] == "INVALID_RULE_SOURCE" for issue in bundle["issues"])


def test_generation_is_deterministic_and_does_not_mutate_contract(tmp_path):
    contract = minimal_contract(tmp_path)
    initial = copy.deepcopy(contract)
    rules = minimal_rules(tmp_path)
    first = generate_bundle(contract, rules)
    second = generate_bundle(contract, rules)
    assert first == second
    assert contract == initial
    assert first["cases"][0]["steps"][0]["assertions"][0]["rule_id"] == "R-OK"
    assert first["cases"][0]["source_ids"]


def test_generated_ids_do_not_depend_on_profile_scenario_order(tmp_path):
    contract = minimal_contract(tmp_path)
    specs = [{"scenario": "normal"}, {"scenario": "missing", "fields": ["name"], "rule_ids": ["R-INVALID"]}]
    rules = minimal_rules(tmp_path, specs)
    before = generate_bundle(contract, rules)
    rules = minimal_rules(tmp_path, list(reversed(specs)))
    after = generate_bundle(contract, rules)
    assert {case["id"] for case in before["cases"]} == {case["id"] for case in after["cases"]}


def test_legacy_coverage_and_explicit_gaps_remain_visible():
    bundle = generate_bundle(parse_document(ROOT / "examples/gomoku/evidence/接口文档.md"), ROOT / "examples/gomoku/rules.yaml")
    cases = {case["id"]: case for case in bundle["cases"]}
    for prefix, size in (("REG", 15), ("LOG", 14), ("INF", 12), ("FLOW", 3)):
        for number in range(1, size + 1):
            assert f"TC-{prefix}-{number:03d}" in cases
    assert cases["TC-REG-005"]["state"] == cases["TC-REG-006"]["state"] == "NEEDS_RULE"
    for number in (5, 8, 9, 10, 11):
        assert cases[f"TC-INF-{number:03d}"]["state"] == "QUARANTINED"
    assert cases["TC-REG-015"]["state"] == "UNSUPPORTED"
    assert cases["TC-INF-003"]["state"] == "NEEDS_RULE"
    assert cases["TC-LOG-013"]["state"] == "NEEDS_RULE"
    assert "基础集默认不执行连续错误登录" in cases["TC-LOG-013"]["reason"]
    assert cases["TC-INF-004"]["steps"][0]["request"]["headers"]["Cookie"] == "probe_cookie=${probe_cookie}"
    assert cases["TC-INF-004"]["variables"]["probe_cookie"]["kind"] == "unique"
    raw_request = cases["TC-REG-014"]["steps"][0]["request"]
    assert raw_request["raw_body"] == "username=${username}&password=${password}"
    assert raw_request["headers"]["Content-Type"] == "text/plain"
    assert Counter(case["state"] for case in cases.values()) == {
        "READY": 26, "NEEDS_RULE": 20, "QUARANTINED": 5, "UNSUPPORTED": 1}
    for case in cases.values():
        if case["state"] == "READY":
            assert case["source_ids"]
            assert all(step["assertions"] for step in case["steps"])
