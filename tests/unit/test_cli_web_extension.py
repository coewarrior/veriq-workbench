"""CLI additions exercise explicit secrets, no-network drafts, review and serve."""
import argparse
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from api_test_tool import models
from api_test_tool.parsers import parse_document

if Path(__file__).with_name("cli_web_extension.py").exists():
    spec = importlib.util.spec_from_file_location("api_test_tool.cli_web_extension", Path(__file__).with_name("cli_web_extension.py"))
    extension = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extension)
else:
    from api_test_tool import cli_web_extension as extension


@pytest.fixture
def document(tmp_path):
    raw = {"openapi": "3.0.3", "info": {"title": "CLI probe", "version": "1"}, "paths": {
        "/health": {"get": {"operationId": "get_health", "responses": {"200": {"description": "ok", "content": {
            "application/json": {"schema": {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}}}}}}}}}
    path = tmp_path / "openapi.json"
    path.write_text(json.dumps(raw))
    return path


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "model.json"
    path.write_text(json.dumps({"provider": "custom", "protocol": "openai_chat", "base_url": "https://api.example.test/v1",
        "model": "explicit-model", "api_key_env": "UNIT_TEST_MODEL_KEY"}))
    monkeypatch.setenv("UNIT_TEST_MODEL_KEY", "test-secret-do-not-print")
    return path


def execute(*argv):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    extension.add_web_subcommands(sub)
    return extension.run_web_command(parser.parse_args(list(map(str, argv))))


def test_legacy_dispatch_is_left_untouched():
    assert extension.run_web_command(argparse.Namespace(command="run")) is None
    assert extension.run_web_command(argparse.Namespace(command="generate")) is None


def test_auto_draft_uses_document_and_never_calls_provider(document, tmp_path, monkeypatch, capsys):
    def forbidden(*args):
        pytest.fail("Auto mode attempted a model call")
    monkeypatch.setattr(models, "generate_text", forbidden)
    out = tmp_path / "auto.json"
    assert execute("draft", "--document", document, "--out", out) == 0
    bundle = json.loads(out.read_text())
    assert bundle["cases"][0]["state"] == "READY"
    summary = json.loads(capsys.readouterr().out)
    assert summary["business_http_requests"] == 0
    assert summary["engine"] == "openapi-rules-v1"


def _provider_double(calls):
    def generate(config, system, prompt):
        calls.append(config)
        contract = json.loads(prompt)["contract"]
        source_id = contract["operations"]["get_health"]["source_ids"][0]
        quote = contract["sources"][source_id]["excerpt"]
        raw = {"schema_version": "1.0", "cases": [{"id": "AI-001-001", "title": "HTTP status", "operation_id": "get_health",
            "scenario": "normal", "variables": {}, "steps": [{"id": "read", "operation_id": "get_health", "request": {},
                "assertions": [{"kind": "status", "expected": 200, "evidence": [{"source_id": source_id, "quote": quote}]}],
                "extract": []}], "cleanup_steps": [], "notes": ""}]}
        if json.loads(prompt).get("phase") == "design":
            raw["cases"][0]["design"] = {"category": "正向", "inputs": "GET /health", "procedure": "读取健康状态", "expected": "200", "basis": "原文"}
        return {"text": json.dumps(raw), "model": config.model, "protocol": config.protocol, "usage": {"input_tokens": 1}}
    return generate


def test_model_draft_uses_only_named_environment_and_needs_explicit_approval(document, config, tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(models, "generate_text", _provider_double(calls))
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key-must-not-be-used")
    out, approved = tmp_path / "candidate.json", tmp_path / "approved.json"
    assert execute("draft", "--document", document, "--mode", "model", "--model-config", config,
                   "--supplement", "用户补充的规则说明", "--out", out) == 0
    assert len(calls) == 2 and calls[0].api_key == "test-secret-do-not-print"
    bundle = json.loads(out.read_text())
    assert bundle["cases"][0]["state"] == "NEEDS_RULE"
    assert any(source["kind"] == "user_requirement" for source in bundle["contract"]["sources"].values())
    assert execute("approve", "--bundle", out, "--case-ids", "AI-001-001", "--out", approved) == 0
    assert json.loads(approved.read_text())["cases"][0]["state"] == "READY"
    assert json.loads(out.read_text())["cases"][0]["state"] == "NEEDS_RULE"
    captured = capsys.readouterr()
    assert calls[0].api_key not in captured.out + captured.err + out.read_text() + approved.read_text()


def test_contract_mode_does_not_read_source_paths(document, config, tmp_path, monkeypatch):
    contract = parse_document(document)
    for source in contract["sources"].values():
        source["path"] = "/do-not-read/ambient-private-file"
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(contract))
    original = Path.read_text
    def guarded_read(path, *args, **kwargs):
        assert not str(path).startswith("/do-not-read")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", guarded_read)
    calls = []
    monkeypatch.setattr(models, "generate_text", _provider_double(calls))
    assert execute("draft", "--contract", contract_file, "--mode", "model", "--model-config", config,
                   "--out", tmp_path / "contract-draft.json") == 0
    assert len(calls) == 2


def test_missing_explicit_key_does_not_fall_back_to_ambient(document, config, tmp_path, monkeypatch):
    monkeypatch.delenv("UNIT_TEST_MODEL_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-secret")
    monkeypatch.setattr(models, "generate_text", lambda *a: pytest.fail("Missing-key mode sent a request"))
    with pytest.raises(ValueError, match="UNIT_TEST_MODEL_KEY"):
        execute("draft", "--document", document, "--mode", "model", "--model-config", config, "--out", tmp_path / "out.json")


@pytest.mark.parametrize("content", [
    '{"api_key":"literal-key"}',
    '{"api_key_env":"ONE","api_key_env":"TWO"}',
    '{"api_key_env":"${OPENAI_API_KEY}"}',
    '{"api_key_env":"UNIT_TEST_MODEL_KEY","timeout":NaN}',
])
def test_unsafe_or_ambiguous_model_config_is_rejected(document, tmp_path, content):
    config = tmp_path / "bad-model.json"; config.write_text(content)
    with pytest.raises(ValueError):
        execute("draft", "--document", document, "--mode", "model", "--model-config", config, "--out", tmp_path / "out.json")


def test_model_mode_requires_explicit_config(document, tmp_path):
    with pytest.raises(ValueError, match="model-config"):
        execute("draft", "--document", document, "--mode", "model", "--out", tmp_path / "out.json")


def test_auto_mode_rejects_ignored_paid_or_supplement_config(document, config, tmp_path):
    for arguments in (("--model-config", config), ("--supplement", "unclear rule")):
        with pytest.raises(ValueError):
            execute("draft", "--document", document, *arguments, "--out", tmp_path / "out.json")


def test_web_command_imports_server_only_when_dispatched(tmp_path, monkeypatch):
    captured = []
    fake_web = types.ModuleType("api_test_tool.web")
    fake_web.serve = lambda **kwargs: captured.append(kwargs)
    monkeypatch.setitem(sys.modules, "api_test_tool.web", fake_web)
    assert execute("web", "--host", "127.0.0.1", "--port", "18100", "--data-dir", tmp_path) == 0
    assert captured == [{"host": "127.0.0.1", "port": 18100, "data_dir": tmp_path}]
    with pytest.raises(ValueError, match="端口"):
        execute("web", "--port", "0")
    assert len(captured) == 1


def test_provider_failure_redacts_key_in_cli_error(document, config, tmp_path, monkeypatch):
    def failure(model, *args):
        raise models.ModelAPIError("provider failed " + model.api_key)
    monkeypatch.setattr(models, "generate_text", failure)
    with pytest.raises(ValueError) as error:
        execute("draft", "--document", document, "--mode", "model", "--model-config", config, "--out", tmp_path / "out.json")
    assert "test-secret-do-not-print" not in str(error.value)
    assert "<redacted>" in str(error.value)
