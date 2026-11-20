"""Opt-in web/model CLI additions; existing CLI commands retain their behavior.

Integration in cli.py:
    add_web_subcommands(sub)                 # before parser.parse_args(argv)
    outcome = run_web_command(args)          # first statements in existing try
    if outcome is not None:
        return outcome

Use explicit --model-config JSON containing api_key_env; never discover a key,
read .env, use a browser session, or access a source file listed by a contract.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path


def add_web_subcommands(sub) -> None:
    web = sub.add_parser("web", help="启动四步网页工作台，与 CLI 共用执行器")
    web.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机")
    web.add_argument("--port", type=int, default=18089)
    web.add_argument("--data-dir", type=Path)
    draft = sub.add_parser("draft", help="从文档或已导入契约生成候选；模型模式不会自动采纳")
    source = draft.add_mutually_exclusive_group(required=True)
    source.add_argument("--document", type=Path, help="Markdown / OpenAPI 文档")
    source.add_argument("--contract", type=Path, help="import 命令生成的结构化契约")
    draft.add_argument("--mode", choices=("auto", "model"), default="auto")
    draft.add_argument("--model-config", type=Path, help="仅模型模式使用，JSON 内以 api_key_env 指定 Key 环境变量")
    draft.add_argument("--supplement", default="", help="补充业务要求文本；模型模式记录为用户提供的来源")
    draft.add_argument("--out", "--output", dest="out", type=Path, required=True)
    approve = sub.add_parser("approve", help="逐例采纳已核对的候选预期，隔离和缺口不能绕过")
    approve.add_argument("--bundle", type=Path, required=True)
    approve.add_argument("--case-ids", nargs="+", required=True, help="明确选择的用例 ID，可空格或逗号分隔")
    approve.add_argument("--note", default="使用者通过 CLI 核对并采纳了这些测试预期")
    approve.add_argument("--out", "--output", dest="out", type=Path, required=True)


def _model_config(path: Path):
    from .models import ModelConfig, validate_config

    if not isinstance(path, Path):
        raise ValueError("模型模式必须明确提供 --model-config JSON 文件")
    if path.stat().st_size > 16_384:
        raise ValueError("模型配置文件超过 16 KiB")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("模型配置包含重复 JSON 字段")
            result[key] = value
        return result
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("模型配置必须是有限 JSON")))
    except json.JSONDecodeError as exc:
        raise ValueError("模型配置必须是严格 JSON 对象") from exc
    allowed = {"provider", "protocol", "base_url", "model", "api_key_env", "max_tokens", "timeout"}
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError("模型配置仅接受 provider/protocol/base_url/model/api_key_env/max_tokens/timeout，不能内嵌 api_key")
    key_name = config.pop("api_key_env", None)
    if not isinstance(key_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key_name):
        raise ValueError("模型配置必须用 api_key_env 指定一个环境变量名称")
    key = os.environ.get(key_name, "")
    if not key.strip():
        raise ValueError(f"指定的模型 Key 环境变量 {key_name} 未设置或为空")
    missing = {"provider", "protocol", "base_url", "model"} - config.keys()
    if missing:
        raise ValueError("模型配置缺少字段：" + ", ".join(sorted(missing)))
    model = ModelConfig(**config, api_key=key)
    validate_config(model)
    return model


def _add_supplement(contract: dict, supplement: str) -> None:
    """The explicit CLI argument is user evidence without creating a side file."""
    import hashlib
    digest = hashlib.sha256(supplement.encode("utf-8")).hexdigest()
    contract["sources"]["CLI-SUPPLEMENT-" + digest[:16]] = {
        "path": "cli:--supplement", "location": "argument", "kind": "user_requirement",
        "sha256": digest, "excerpt": supplement}


def _summary(bundle: dict, path: Path) -> dict:
    return {"engine": bundle.get("generation", {}).get("engine"),
            "cases": dict(Counter(case["state"] for case in bundle.get("cases", []))),
            "business_http_requests": 0, "output": str(path.resolve())}


def run_web_command(args: argparse.Namespace) -> int | None:
    """Return None for legacy commands, so their original dispatch stays intact."""
    if args.command not in {"web", "draft", "approve"}:
        return None
    if args.command == "web":
        if not isinstance(args.port, int) or not 1 <= args.port <= 65535:
            raise ValueError("网页端口必须在 1–65535 之间")
        from .web import serve
        serve(host=args.host, port=args.port, data_dir=args.data_dir)
        return 0

    from .cli import read_asset, write_asset
    from .execution import validate_bundle
    from .web_generation import approve_cases, auto_bundle, compile_model_bundle, model_prompts

    if args.command == "approve":
        if args.out.resolve() == args.bundle.resolve():
            raise ValueError("--out 请使用新文件，保留采纳前的候选方案")
        case_ids = [value for item in args.case_ids for value in item.split(",") if value]
        bundle = approve_cases(read_asset(args.bundle), case_ids, args.note)
        errors = validate_bundle(bundle)
        if errors:
            raise ValueError("采纳后静态校验失败：" + "；".join(e["message"] for e in errors))
        write_asset(bundle, args.out)
        print(json.dumps(_summary(bundle, args.out), ensure_ascii=False))
        return 0

    if args.mode == "auto" and args.model_config:
        raise ValueError("--model-config 仅用于 --mode model；自动规则模式不会调用模型")
    if args.mode == "auto" and args.supplement:
        raise ValueError("--supplement 仅用于模型模式；自动规则模式只采用显式 OpenAPI 契约")
    if not isinstance(args.supplement, str) or len(args.supplement) > 12000:
        raise ValueError("补充要求最多 12000 字符")
    source_path = args.document or args.contract
    if args.out.resolve() == source_path.resolve():
        raise ValueError("输出文件不能覆盖输入文档或契约")
    # Validate provider settings before parsing or reading the document for a
    # paid call. No model operation occurs unless mode=model was explicit.
    config = _model_config(args.model_config) if args.mode == "model" else None
    if args.document:
        from .parsers import parse_document
        from .web_security import check_document
        from .document_limits import MAX_DOCUMENT_BYTES, DOCUMENT_LIMIT_LABEL
        if args.document.stat().st_size > MAX_DOCUMENT_BYTES:
            raise ValueError(f"单份文档上限为 {DOCUMENT_LIMIT_LABEL}")
        document_text = args.document.read_text(encoding="utf-8-sig")
        check_document(document_text, args.document.name)
        contract = parse_document(args.document)
    else:
        contract = read_asset(args.contract)
        # Use in-memory excerpts only. A contract's path fields are provenance,
        # never authority to read more user or server files.
        document_text = "\n\n".join(source.get("excerpt", "") for source in contract.get("sources", {}).values()
                                   if isinstance(source, dict) and source.get("kind") == "document")
    if args.mode == "auto":
        bundle = auto_bundle(contract)
    else:
        from .models import ModelAPIError, generate_text
        if args.supplement.strip():
            _add_supplement(contract, args.supplement)
        from .model_planning import generate_plan
        def checkpoint(state):
            if state["cases"]:
                partial = compile_model_bundle(contract, json.dumps({"schema_version": "1.0", "cases": state["cases"]}, ensure_ascii=False))
                partial["generation"].update(engine="model-staged-v1", partial=True)
                write_asset(partial, args.out)
        try:
            bundle = generate_plan(contract, document_text, args.supplement,
                lambda system, prompt: generate_text(config, system, prompt), checkpoint=checkpoint)
        except ModelAPIError as exc:
            raise ValueError(str(exc).replace(config.api_key, "<redacted>")) from None

    errors = validate_bundle(bundle)
    if errors:
        raise ValueError("生成后静态校验失败：" + "；".join(e["message"] for e in errors[:5]))
    write_asset(bundle, args.out)
    print(json.dumps(_summary(bundle, args.out), ensure_ascii=False))
    return 0
