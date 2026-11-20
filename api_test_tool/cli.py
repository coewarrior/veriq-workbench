"""Inspectable CLI pipeline. Import/generate/validate never send HTTP requests."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

from api_test_tool.cleanup import build_cleanup
from api_test_tool.execution import run_bundle, validate_bundle
from api_test_tool.generation import generate_bundle
from api_test_tool.parsers import parse_document
from api_test_tool.reporting import write_report
from api_test_tool.cli_web_extension import add_web_subcommands, run_web_command


def read_asset(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected an object in {path}")
    return data


def write_asset(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".yaml", ".yml"}:
        content = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    else:
        content = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(content + "\n", encoding="utf-8")


def result_exit_code(result: dict) -> int:
    counts = result.get("summary", {})
    if (any(counts.get(key, 0) for key in ("FAIL", "BROKEN"))
            or result.get("validation_errors") or result.get("cleanup", {}).get("status") == "FAIL"
            or any(case.get("cleanup", {}).get("status") == "FAIL" for case in result.get("cases", []))):
        return 1
    return 0 if counts.get("complete", False) else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="api-test", description="文档 → 用例 → 执行 → 报告；模型仅在显式配置和选择时调用")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="解析 Markdown / OpenAPI，生成可追踪接口契约")
    imp.add_argument("--document", type=Path, required=True)
    imp.add_argument("--output", type=Path, required=True)
    gen = sub.add_parser("generate", help="依据规则配置生成冻结的测试资产")
    gen.add_argument("--contract", type=Path, required=True)
    gen.add_argument("--rules", type=Path, required=True)
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate", help="静态预检，无 HTTP 请求")
    validate.add_argument("--bundle", type=Path, required=True)
    for name in ("run", "replay"):
        run = sub.add_parser(name, help="执行冻结用例" if name == "run" else "从冻结资产重放，使用新测试数据命名空间")
        if name == "run":
            run.add_argument("--bundle", type=Path, required=True)
        else:
            run.add_argument("--run", type=Path, required=True, help="含 bundle.json 的历史运行目录")
        run.add_argument("--env", type=Path, required=True)
        run.add_argument("--output", type=Path, required=True)
        run.add_argument("--case", action="append", dest="case_ids", help="按用例编号选择，可重复")
    report = sub.add_parser("report", help="从证据生成独立 HTML 报告，无需联网")
    report.add_argument("--run", type=Path, required=True)
    report.add_argument("--output", type=Path)
    add_web_subcommands(sub)
    args = parser.parse_args(argv)
    try:
        outcome = run_web_command(args)
        if outcome is not None:
            return outcome
        if args.command == "import":
            contract = parse_document(args.document)
            write_asset(contract, args.output)
            print(json.dumps({"operations": len(contract.get("operations", {})), "issues": contract.get("issues", []), "output": str(args.output)}, ensure_ascii=False))
            return 0
        if args.command == "generate":
            bundle = generate_bundle(read_asset(args.contract), args.rules, args.seed)
            write_asset(bundle, args.output)
            print(json.dumps({"cases": dict(Counter(c["state"] for c in bundle["cases"])), "output": str(args.output)}, ensure_ascii=False))
            return 0
        if args.command == "validate":
            bundle = read_asset(args.bundle)
            errors = validate_bundle(bundle)
            print(json.dumps({"valid": not errors, "http_requests": 0, "cases": dict(Counter(c.get("state", "INVALID") for c in bundle.get("cases", []))), "errors": errors}, ensure_ascii=False, indent=2))
            return 3 if errors else 0
        if args.command == "report":
            output = args.output or args.run / "index.html"
            write_report(read_asset(args.run / "result.json"), read_asset(args.run / "bundle.json"), output)
            print(str(output.resolve()))
            return 0
        bundle_path = args.bundle if args.command == "run" else args.run / "bundle.json"
        bundle = read_asset(bundle_path)
        environment = read_asset(args.env)
        # Validate before creating an adapter or attempting network access.
        errors = validate_bundle(bundle)
        if any(error["case_id"] == "*" for error in errors):
            print(json.dumps({"valid": False, "http_requests": 0, "errors": errors}, ensure_ascii=False), file=sys.stderr)
            return 3
        callback = build_cleanup(bundle, environment)
        if args.output.exists() and any(args.output.iterdir()):
            raise ValueError("Output directory must be empty; preserve prior run evidence")
        result = run_bundle(bundle, environment, args.output, case_ids=args.case_ids, cleanup_callback=callback)
        write_report(result, read_asset(args.output / "bundle.json"), args.output / "index.html")
        print(json.dumps({"run_id": result["run_id"], "summary": result["summary"], "cleanup": result.get("cleanup"), "report": str((args.output / "index.html").resolve())}, ensure_ascii=False, indent=2))
        return result_exit_code(result)
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        print(f"配置或输入错误：{exc}", file=sys.stderr)
        return 3
