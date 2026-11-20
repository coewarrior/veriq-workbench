"""Extract explicit document targets without contacting or authorizing them."""
from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

import yaml


def normalize_base_url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Base URL 必须为文本")
    value = value.strip()
    if not value:
        return ""
    if len(value) > 2000 or any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError("Base URL 不能包含空白、控制字符或反斜杠")
    try:
        part = urlsplit(value)
        if part.scheme not in {"http", "https"} or not part.hostname or part.username is not None or part.password is not None:
            raise ValueError()
        if "?" in value or "#" in value or "%" in part.netloc or "{" in value or "}" in value:
            raise ValueError()
        if part.port is not None and not 1 <= part.port <= 65535:
            raise ValueError()
        path = part.path
        decoded = unquote(path)
        if "\\" in decoded or any(ord(c) < 32 or ord(c) == 127 for c in decoded) or any(p in {".", ".."} for p in decoded.split("/")):
            raise ValueError()
        host = f"[{part.hostname}]" if ":" in part.hostname else part.hostname
        port = f":{part.port}" if part.port is not None else ""
        return f"{part.scheme}://{host}{port}{path.rstrip('/')}"
    except (ValueError, UnicodeError):
        raise ValueError("请填写完整 HTTP(S) Base URL，可含 /v1 等基础路径，不能含账号、查询参数或路径跳转") from None


def url_origin(value: str) -> str:
    part = urlsplit(normalize_base_url(value))
    return f"{part.scheme}://{part.netloc}"


def document_targets(content: str, filename: str) -> dict:
    candidates = []
    notes = []

    def add(url, source, description=""):
        try:
            normalized = normalize_base_url(url)
        except ValueError:
            notes.append("文档包含相对地址、未定义变量或不完整地址，请核对并补充 Base URL。")
            return
        if normalized and not any(c["url"] == normalized for c in candidates):
            candidates.append({"url": normalized, "source": source, "description": str(description)[:200]})

    if filename.lower().endswith((".md", ".markdown")):
        # Only labelled service addresses; arbitrary hyperlinks are not API targets.
        pattern = r"(?im)^\s*(?:[-*#>]\s*)*(?:\*\*)?(?:base[_ -]?url|基础地址|服务地址|接口根地址|接口基础地址)(?:\*\*)?\s*[:：=]\s*[`<\"']?(https?://[^\s`<>\"']+)"
        for match in re.finditer(pattern, content):
            add(match.group(1), "Markdown 地址声明")
    else:
        try:
            doc = yaml.load(content, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
        except (yaml.YAMLError, ValueError, RecursionError):
            return {"candidates": [], "notes": ["暂未识别到地址，可手动填写；文档仍可保存用于检查。"]}
        if isinstance(doc, dict):
            servers = doc.get("servers", [])
            if isinstance(servers, list):
                for i, server in enumerate(servers[:100]):
                    if not isinstance(server, dict) or not isinstance(server.get("url"), str):
                        continue
                    variables = server.get("variables", {})
                    variables = variables if isinstance(variables, dict) else {}
                    def substitute(match):
                        definition = variables.get(match.group(1), {})
                        return str(definition["default"]) if isinstance(definition, dict) and "default" in definition else match.group(0)
                    url = re.sub(r"\{([^{}]+)\}", substitute, server["url"])
                    add(url, f"OpenAPI servers[{i}]", server.get("description", ""))
    return {"candidates": candidates, "notes": list(dict.fromkeys(notes))}
