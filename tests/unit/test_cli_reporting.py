import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from api_test_tool.cleanup import build_cleanup
from api_test_tool.cli import read_asset, result_exit_code
from api_test_tool.generation import generate_bundle
from api_test_tool.parsers import parse_document
from api_test_tool.reporting import render_report, write_report

ROOT = Path(__file__).resolve().parents[2]


def test_complete_execution_with_assertion_failure_is_not_reported_as_all_pass(tmp_path):
    result = {"title": "<script>alert(1)</script>", "summary": {"complete": True, "PASS": 0, "FAIL": 1, "total": 1},
              "cases": [{"id": "failure", "title": "<img src=x onerror=alert(2)>", "status": "FAIL"}], "cleanup": {"status": "PASS"}}
    output = write_report(result, {"contract": {}, "rules": [], "cases": []}, tmp_path / "index.html").read_text()
    assert "本轮全部通过" not in output
    assert "本轮包含未通过或未执行用例" in output
    assert "<script>alert(1)</script>" not in output
    assert "<img src=x" not in output
    assert '<a class="report-back" href="/api-testing">← 返回测试台</a>' in output
    assert result_exit_code(result) == 1


def test_unexecuted_network_case_is_plain_and_rule_sources_are_deduplicated():
    result = {
        "summary": {"complete": False, "BLOCKED": 1, "total": 1},
        "cases": [{"id": "case-1", "title": "身份检查", "status": "BLOCKED",
                   "reason": "Network availability failure: ConnectionError",
                   "rule_ids": ["rule-1", "rule-2"], "steps": []}],
    }
    bundle = {
        "contract": {"sources": {
            "document": {"path": "inputs/document.md", "location": "document", "sha256": "a" * 64,
                         "excerpt": "唯一接口文档原文"},
            "review": {"path": "web:user-review", "location": "case:case-1", "sha256": "b" * 64,
                       "excerpt": "唯一人工确认记录"},
        }},
        "rules": [
            {"id": "rule-1", "state": "documented", "description": "模型候选：身份检查 / s1 / json_equal",
             "source_ids": ["document", "review"]},
            {"id": "rule-2", "state": "documented", "description": "模型候选：身份检查 / s2 / json_schema",
             "source_ids": ["document", "review"]},
        ],
        "cases": [{"id": "case-1", "state": "READY", "steps": []}],
    }

    output = render_report(result, bundle)

    assert '<span class="badge BLOCKED">未执行</span>' in output
    assert "前序请求无法连接测试环境，本用例未执行" in output
    assert "服务恢复后重新执行即可，无需修改规则" in output
    assert "查看判断依据（1 项结论 · 2 处来源）" in output
    assert ".basis-summary { background: #111d30; color: #d8e3f3; border: 1px solid #2e3d56; }" in output
    assert "身份检查 <span class=\"muted\">（2 条断言共用）</span>" in output
    assert "技术规则（2 条）" in output
    assert output.count("唯一接口文档原文") == 1
    assert output.count("唯一人工确认记录") == 1
    assert "查看规则与原文依据" not in output
    assert "本用例未发送请求。请根据原因补充规则" not in output
    assert '<strong>2</strong><span>依据来源</span>' in output


def test_case_cleanup_failure_sets_nonzero_cli_exit():
    assert result_exit_code({"summary": {"PASS": 1, "complete": False}, "cases": [{"cleanup": {"status": "FAIL"}}]}) == 1


def test_cleanup_rejects_other_database_and_injected_username_without_ssh(tmp_path):
    identity = tmp_path / "key"
    identity.write_text("test fixture, not a real key")
    environment = read_asset(ROOT / "examples/gomoku/environment.yaml")
    environment["cleanup"]["identity_file"] = str(identity)
    bundle = {"cases": [{"id": "owned", "variables": {"username": {"kind": "unique", "prefix": "mvp_"}}}]}
    cleanup = build_cleanup(bundle, environment)
    with patch("api_test_tool.cleanup.subprocess.run") as ssh:
        result = cleanup([{"case_id": "owned", "variables": {"username": "mvp_x'; DROP TABLE user;--"}}])
        assert result["status"] == "FAIL"
        ssh.assert_not_called()
    environment["cleanup"]["database"] = "other_database"
    with pytest.raises(ValueError, match="dedicated"):
        build_cleanup(bundle, environment)


def test_cleanup_only_deletes_declared_unique_case_usernames(tmp_path):
    identity = tmp_path / "key"
    identity.write_text("test fixture")
    environment = read_asset(ROOT / "examples/gomoku/environment.yaml")
    environment["cleanup"]["identity_file"] = str(identity)
    bundle = {"cases": [
        {"id": "owned", "variables": {"username": {"kind": "unique", "prefix": "mvp_"}}},
        {"id": "literal", "variables": {"username": {"kind": "literal", "value": "mvp_existing_user"}}},
    ]}
    cleanup = build_cleanup(bundle, environment)
    with patch("api_test_tool.cleanup.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "1\n0\n", "")) as ssh:
        result = cleanup([{"case_id": "owned", "variables": {"username": "mvp_new_1_username"}},
                          {"case_id": "literal", "variables": {"username": "mvp_existing_user"}}])
        assert result["status"] == "PASS"
        sql = ssh.call_args.kwargs["input"]
        assert "mvp_new_1_username" in sql
        assert "mvp_existing_user" not in sql
        assert "DROP" not in sql


def test_pytest_invalid_environment_fails_ci_without_sending_requests(tmp_path):
    example = ROOT / "examples/items"
    bundle = generate_bundle(parse_document(example / "openapi.yaml"), example / "rules.yaml")
    asset = tmp_path / "bundle.json"
    asset.write_text(json.dumps(bundle))
    env = tmp_path / "env.json"
    env.write_text(json.dumps({"base_url": "http://127.0.0.1:1", "allowed_origins": []}))
    output = tmp_path / "run"
    process = subprocess.run([sys.executable, "-m", "pytest", "tests/test_generated.py", "-q", "-o", "addopts=",
                              "--api-bundle", str(asset), "--api-environment", str(env), "--api-output", str(output)],
                             cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert process.returncode != 0
    result = json.loads((output / "result.json").read_text())
    assert result["validation_errors"]
    assert result["requests_sent"] == 0
