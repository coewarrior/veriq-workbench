"""Real loopback HTTP checks through the public document → bundle → runner API.

No item-specific request handling is imported by the parser or executor. The
entire executable plan comes from examples/items, including auth and cleanup.
"""

import importlib.util
import json
import socket
from http.client import HTTPResponse
from pathlib import Path

import pytest

from api_test_tool.execution import run_bundle, validate_bundle
from api_test_tool.generation import generate_bundle
from api_test_tool.parsers import parse_document


REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "items"
_spec = importlib.util.spec_from_file_location(
    "items_server_fixture", REPO / "tests" / "fixtures" / "items_server.py"
)
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)
ItemsServer = _fixture.ItemsServer


def test_demo_accepts_sixteen_connections_before_dispatching_handlers():
    server = ItemsServer()
    connections = []
    try:
        # Queue the whole burst before starting accept(), so a fast machine
        # cannot hide an undersized listener backlog.
        for index in range(16):
            connection = socket.create_connection(server.httpd.server_address, timeout=2)
            connections.append(connection)
            body = json.dumps({"owner": f"burst_{index}"}).encode()
            headers = ("POST /session HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                       "Content-Type: application/json\r\nConnection: close\r\n"
                       f"Content-Length: {len(body)}\r\n\r\n").encode()
            connection.sendall(headers + body)
        server.start()
        tokens = set()
        for connection in connections:
            with HTTPResponse(connection) as response:
                response.begin()
                assert response.status == 200
                tokens.add(json.loads(response.read())["token"])
        assert len(tokens) == 16
        assert set(server.tokens.values()) == {f"burst_{index}" for index in range(16)}
    finally:
        for connection in connections:
            connection.close()
        server.close()


@pytest.fixture(scope="module")
def items_bundle():
    contract = parse_document(EXAMPLE / "openapi.yaml")
    bundle = generate_bundle(contract, EXAMPLE / "rules.yaml")
    assert contract["issues"] == []
    assert set(contract["operations"]) == {"createSession", "createItem", "getItem", "deleteItem"}
    assert bundle["issues"] == []
    assert validate_bundle(bundle) == []
    assert all(case["state"] == "READY" for case in bundle["cases"])
    return bundle


def environment(server):
    return {
        "name": "integration-loopback",
        "base_url": server.base_url,
        "allowed_origins": [server.base_url],
        "timeout": 3,
        "max_requests": 120,
        "max_response_bytes": 1048576,
        "stop_on_5xx": True,
    }


def failed_assertions(case):
    return [assertion for step in case["steps"] for assertion in step["assertions"]
            if assertion["passed"] is False]


def test_document_only_onboarding_executes_generated_cases_and_cleans_resources(items_bundle, tmp_path):
    """New API docs/config drive boundaries, Token, extraction and cleanup."""
    with ItemsServer() as server:
        result = run_bundle(items_bundle, environment(server), tmp_path)
        assert result["summary"]["PASS"] == len(items_bundle["cases"]) == 19
        assert result["summary"]["complete"] is True
        assert all(case["status"] == "PASS" for case in result["cases"])
        assert server.items == {}
        assert sum(request["method"] == "DELETE" for request in server.requests) == 3
        flow = next(case for case in result["cases"] if case["id"] == "ITEM-FLOW-001")
        assert [step["response"]["status"] for step in flow["steps"]] == [200, 201, 200, 409]
        assert [step["response"]["status"] for step in flow["cleanup"]["steps"]] == [204, 404]
        # Evidence must be persisted, with usable numeric summary and without Tokens.
        saved = (tmp_path / "result.json").read_text(encoding="utf-8")
        assert json.loads(saved)["summary"]["PASS"] == 19
        for token in server.tokens:
            assert token not in saved
            assert token not in (tmp_path / "bundle.json").read_text(encoding="utf-8")


def test_frozen_bundle_replays_with_fresh_owner_and_valid_token_schema(items_bundle, tmp_path):
    """The saved asset is executable again; redaction must preserve schemas/templates."""
    with ItemsServer() as server:
        first = run_bundle(items_bundle, environment(server), tmp_path / "first", ["ITEM-FLOW-001"])
        assert first["summary"]["PASS"] == 1
        old_owners = set(server.tokens.values())
        frozen = json.loads((tmp_path / "first" / "bundle.json").read_text(encoding="utf-8"))
        assert validate_bundle(frozen) == []
        second = run_bundle(frozen, environment(server), tmp_path / "replay", ["ITEM-FLOW-001"])
        assert second["summary"]["PASS"] == 1
        assert second["summary"]["complete"] is True
        assert len(set(server.tokens.values()) - old_owners) == 1
        assert server.items == {}


@pytest.mark.parametrize(
    ("fault", "expected_kind"),
    [("wrong_owner", "equals_variable"), ("wrong_type", "json_schema"),
     ("missing_field", "json_schema"), ("non_json", "json_schema")],
)
def test_contract_violations_leave_evidence_and_still_cleanup(items_bundle, tmp_path, fault, expected_kind):
    with ItemsServer(fault=fault) as server:
        result = run_bundle(items_bundle, environment(server), tmp_path, ["ITEM-FLOW-001"])
        case = result["cases"][0]
        assert case["status"] == "FAIL"
        failures = failed_assertions(case)
        assert any(assertion["kind"] == expected_kind and assertion["rule_id"] == "R-ITEM-READ"
                   for assertion in failures)
        read = next(step for step in case["steps"] if step["id"] == "read")
        assert read["request"]["method"] == "GET"
        assert read["response"]["status"] == 200
        assert read["response"]["body"]
        assert case["cleanup"]["status"] == "PASS"
        assert server.items == {}
        if fault == "wrong_owner":
            failure = next(a for a in failures if a["kind"] == "equals_variable")
            assert failure["actual"] == "another_user"
            assert failure["expected"].startswith("mvp_items_")
        if fault == "non_json":
            assert read["response"]["body"] == "injected non-json upstream response"
        # Running the same frozen plan must not learn or weaken the expectation.
        frozen = json.loads((tmp_path / "bundle.json").read_text(encoding="utf-8"))
        assert next(rule for rule in frozen["rules"] if rule["id"] == "R-ITEM-READ")["assertions"] == next(
            rule for rule in items_bundle["rules"] if rule["id"] == "R-ITEM-READ"
        )["assertions"]


def test_5xx_stops_later_business_requests_but_attempts_declared_cleanup(items_bundle, tmp_path):
    with ItemsServer(fault="server_error") as server:
        result = run_bundle(items_bundle, environment(server), tmp_path)
        assert result["cases"][0]["status"] == "FAIL"
        assert result["summary"]["BLOCKED"] == len(items_bundle["cases"]) - 1
        assert result["summary"]["complete"] is False
        assert sum(request == {"method": "POST", "path": "/items"} for request in server.requests) == 1
        assert sum(request == {"method": "POST", "path": "/session"} for request in server.requests) == 1
        assert result["cases"][0]["cleanup"]["status"] == "PASS"
        assert server.items == {}
        assert any(assertion["kind"] == "status" and assertion["actual"] == 503
                   for assertion in failed_assertions(result["cases"][0]))


def test_cleanup_failure_prevents_complete_result_and_preserves_evidence(items_bundle, tmp_path):
    with ItemsServer(fault="cleanup_error") as server:
        result = run_bundle(items_bundle, environment(server), tmp_path, ["ITEM-FLOW-001"])
        case = result["cases"][0]
        assert case["status"] == "PASS"  # Business assertions and cleanup have distinct outcomes.
        assert case["cleanup"]["status"] == "FAIL"
        assert result["summary"]["complete"] is False
        assert len(server.items) == 1
        delete = case["cleanup"]["steps"][0]
        assert delete["request"]["method"] == "DELETE"
        assert delete["response"]["status"] == 500
        assert delete["response"]["body"] == {"error": "injected_cleanup_error"}
