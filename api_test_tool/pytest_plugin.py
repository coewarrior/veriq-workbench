"""One generic pytest entrypoint for generated assets and Allure evidence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from api_test_tool.cleanup import build_cleanup
from api_test_tool.cli import read_asset
from api_test_tool.execution import run_bundle
from api_test_tool.reporting import write_report


def pytest_addoption(parser):
    group = parser.getgroup("document-api-test")
    group.addoption("--api-bundle", help="Frozen generated bundle JSON/YAML")
    group.addoption("--api-environment", help="Explicit allowlisted environment YAML")
    group.addoption("--api-output", default="reports/pytest-generated", help="New, empty evidence directory")


def pytest_generate_tests(metafunc):
    if "generated_case" not in metafunc.fixturenames:
        return
    bundle_path = metafunc.config.getoption("--api-bundle")
    if not bundle_path:
        metafunc.parametrize("generated_case", [])
        return
    bundle = read_asset(Path(bundle_path))
    cases = bundle.get("cases", [])
    metafunc.parametrize("generated_case", cases, ids=[case["id"] for case in cases])


@pytest.fixture(scope="session")
def generated_run(request):
    config = request.config
    if not config.getoption("--api-environment"):
        pytest.fail("Generated execution requires --api-environment; no default live host is used")
    bundle = read_asset(Path(config.getoption("--api-bundle")))
    environment = read_asset(Path(config.getoption("--api-environment")))
    output = Path(config.getoption("--api-output"))
    if output.exists() and any(output.iterdir()):
        pytest.fail("--api-output must be empty to preserve prior evidence")
    selected = [item.callspec.params["generated_case"]["id"] for item in request.session.items
                if hasattr(item, "callspec") and "generated_case" in item.callspec.params]
    result = run_bundle(bundle, environment, output, selected, build_cleanup(bundle, environment))
    write_report(result, read_asset(output / "bundle.json"), output / "index.html")
    config._generated_api_result = result
    if result.get("validation_errors"):
        pytest.fail("Preflight validation failed; zero HTTP requests sent. See the generated report.")
    yield result
    if result.get("cleanup", {}).get("status") == "FAIL":
        pytest.fail("Run-level data cleanup failed; inspect the HTML/JSON evidence")


def pytest_sessionfinish(session, exitstatus):
    result = getattr(session.config, "_generated_api_result", None)
    if result and exitstatus == 0 and not result.get("summary", {}).get("complete", False):
        # Declared gaps are visible as skipped cases, while CI still sees an incomplete run.
        session.exitstatus = 2


def assert_generated_case(generated_case, generated_run):
    import allure

    case = next(case for case in generated_run["cases"] if case["id"] == generated_case["id"])
    allure.dynamic.title(case.get("title", case["id"]))
    allure.dynamic.feature(case.get("operation_id", "unknown"))
    allure.dynamic.story(case.get("scenario", "unknown"))
    allure.attach(json.dumps(case, ensure_ascii=False, indent=2), "执行证据（已脱敏）", allure.attachment_type.JSON)
    for rule_id in case.get("rule_ids", []):
        allure.dynamic.tag(rule_id)
    if case["status"] in {"BLOCKED", "QUARANTINED", "UNSUPPORTED"} and generated_case.get("state") != "READY":
        pytest.skip(f'{case["status"]}: {case.get("reason", "")}')
    assert case["status"] == "PASS", f'{case["status"]}: {case.get("reason", "")} — see attached evidence'
    assert case.get("cleanup", {}).get("status") != "FAIL", "Case cleanup failed; see attached evidence"
