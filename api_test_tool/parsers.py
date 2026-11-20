"""Local, deterministic contract ingestion. Unsupported semantics are never discarded."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
SCHEMA_KEYS = {
    "type", "properties", "required", "additionalProperties", "items", "enum", "const",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "uniqueItems",
    "minProperties", "maxProperties", "description", "title", "default", "example",
    "examples", "nullable", "readOnly", "writeOnly", "deprecated", "$schema", "$id",
}


def _pointer(value: Any, pointer: str) -> Any:
    if pointer in ("", "#"):
        return value
    pointer = pointer.removeprefix("#")
    if not pointer.startswith("/"):
        raise ValueError(f"Not a JSON Pointer: {pointer}")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            value = value[int(token)]
        elif token not in value and token.isdecimal() and int(token) in value:
            value = value[int(token)]  # PyYAML accepts unquoted OpenAPI response codes.
        else:
            value = value[token]
    return value


def add_source(sources: dict, path: Path, location: str, excerpt: str, kind: str) -> str:
    """Source identity includes actual bytes and exact location, never model output."""
    path = path.resolve()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    identity = f"{path.as_posix()}\0{digest}\0{location}"
    source_id = "SRC-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
    sources[source_id] = {"path": str(path), "sha256": digest, "location": location,
                          "excerpt": excerpt, "kind": kind}
    return source_id


def source_from_reference(sources: dict, base: Path, reference: dict) -> str:
    path = (base / reference["file"]).resolve()
    content = path.read_text(encoding="utf-8-sig")
    anchor = reference.get("anchor")
    if not anchor:
        raise ValueError(f"Source reference requires an anchor: {path}")
    if anchor.startswith("#/"):
        value = _pointer(yaml.safe_load(content), anchor)
        return add_source(sources, path, anchor, json.dumps(value, ensure_ascii=False), "rule")
    lines = content.splitlines()
    matches = [n for n, line in enumerate(lines) if anchor in line]
    if not matches:
        raise ValueError(f"Source anchor not found: {path}: {anchor}")
    n = matches[0]
    end = min(len(lines), n + 18)
    # A Markdown table row is a whole evidence unit; YAML captures the case block.
    if lines[n].lstrip().startswith("|"):
        end = n + 1
    else:
        for i in range(n + 1, end):
            if re.match(r"\s*- id:", lines[i]):
                end = i
                break
    return add_source(sources, path, f"lines {n + 1}-{end}", "\n".join(lines[n:end]), "rule")


def parse_document(path: Path) -> dict:
    path = Path(path).resolve()
    text = path.read_text(encoding="utf-8-sig")
    contract = {"schema_version": "1.0", "title": path.stem, "sources": {},
                "operations": {}, "issues": []}
    add_source(contract["sources"], path, "document", text, "document")
    if path.suffix.lower() in (".md", ".markdown"):
        _parse_markdown(path, text, contract)
    else:
        document = yaml.safe_load(text)
        if not isinstance(document, dict) or not str(document.get("openapi", "")).startswith("3."):
            raise ValueError("Expected a Markdown table document or OpenAPI 3 document")
        _parse_openapi(path, document, contract)
    if not contract["operations"]:
        contract["issues"].append({"code": "NO_OPERATIONS", "severity": "error",
                                    "message": "No supported operation definitions found"})
    return contract


def _parse_markdown(path: Path, text: str, contract: dict) -> None:
    lines = text.splitlines()
    title = re.search(r"^#\s+(.+)$", text, re.M)
    if title:
        contract["title"] = title.group(1)
    heads = [n for n, line in enumerate(lines) if line.startswith("## ")] + [len(lines)]
    for start, end in zip(heads, heads[1:]):
        rows = {}
        row_lines = {}
        for n in range(start, end):
            if lines[n].lstrip().startswith("|"):
                cols = [c.strip() for c in re.split(r"(?<!\\)\|", lines[n].strip().strip("|"))]
                if len(cols) == 2:
                    rows[cols[0]] = cols[1]
                    row_lines[cols[0]] = n
        if "URL" not in rows or "请求方法" not in rows:
            continue
        route = rows["URL"].strip("` ")
        method = rows["请求方法"].strip("` ").upper()
        operation_id = method.lower() + "_" + re.sub(r"[^a-zA-Z0-9]+", "_", route).strip("_")
        source_ids = []
        for key, n in row_lines.items():
            source_ids.append(add_source(contract["sources"], path, f"lines {n + 1}-{n + 1}", lines[n], "markdown-row"))
        request_text = rows.get("请求参数", "")
        request_schema = {"type": "object", "properties": {}, "required": []}
        for name, typename, rest in re.findall(r"•\s*`([^`]+)`\s+(string|int|integer|boolean|number)([^•]*?)(?=<br>|$)", request_text):
            if "Body" in request_text and name != "SSID":
                request_schema["properties"][name] = {"type": "integer" if typename == "int" else typename}
                if "必填" in rest:
                    request_schema["required"].append(name)
        examples = re.findall(r"`(\{[^`]*\})`", request_text)
        request_example = json.loads(examples[-1]) if examples else {}
        response_schema = {"type": "object", "properties": {}, "required": []}
        for name, typename in re.findall(r"•\s*`([^`]+)`\s+(string|int|integer|boolean|number)", rows.get("正确响应结构", "")):
            response_schema["properties"][name] = {"type": "integer" if typename == "int" else typename}
            response_schema["required"].append(name)
        auth = {}
        parameters = []
        if "Cookie" in request_text and "SSID" in request_text and "Body" not in request_text:
            auth = {"type": "apiKey", "in": "cookie", "name": "SSID"}
            parameters.append({"name": "SSID", "in": "cookie", "required": True, "schema": {"type": "string"}})
        if method not in {m.upper() for m in METHODS} or not route.startswith("/"):
            contract["issues"].append({"code": "UNSUPPORTED_MARKDOWN", "severity": "error",
                "operation_id": operation_id, "message": "Unsupported HTTP method or non-relative path"})
        contract["operations"][operation_id] = {"id": operation_id, "method": method, "path": route,
            "parameters": parameters, "request_schema": request_schema if request_schema["properties"] else {},
            "request_example": request_example, "response_schema": response_schema,
            "auth": auth, "source_ids": source_ids, "business_rules": rows.get("错误响应结构", ""),
            "response_examples": [json.loads(x) for x in re.findall(r"`(\{[^`]*\})`", rows.get("正确响应结构", ""))]}
        contract["issues"].append({"code": "HTTP_STATUS_UNSPECIFIED", "severity": "warning",
            "operation_id": operation_id, "message": "Markdown does not define HTTP status mapping; explicit sourced rules are required"})


def _parse_openapi(path: Path, document: dict, contract: dict) -> None:
    contract["title"] = document.get("info", {}).get("title", path.stem)
    cache = {path: document}

    def issue(op: str, message: str, pointer: str):
        contract["issues"].append({"code": "UNSUPPORTED_OPENAPI", "severity": "error",
            "operation_id": op, "location": pointer, "message": message})

    def resolve(value: Any, origin: Path, op: str, pointer: str, stack=()):
        if isinstance(value, list):
            return [resolve(v, origin, op, f"{pointer}/{n}", stack) for n, v in enumerate(value)]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            ref = value["$ref"]
            if not isinstance(ref, str) or re.match(r"^[a-zA-Z][\w+.-]*:", ref) or ref.startswith("//"):
                issue(op, f"Remote reference is not supported: {ref}", pointer)
                return copy.deepcopy(value)
            filename, _, fragment = ref.partition("#")
            target = (origin.parent / filename).resolve() if filename else origin
            marker = (str(target), fragment)
            if marker in stack:
                issue(op, f"Cyclic reference is not supported: {ref}", pointer)
                return copy.deepcopy(value)
            try:
                if target not in cache:
                    cache[target] = yaml.safe_load(target.read_text(encoding="utf-8-sig"))
                referenced = _pointer(cache[target], fragment)
                add_source(contract["sources"], target, "#" + fragment,
                           json.dumps(referenced, ensure_ascii=False), "openapi-ref")
                if len(value) > 1:
                    issue(op, "$ref siblings are not supported in this MVP", pointer)
                return resolve(referenced, target, op, "#" + fragment, stack + (marker,))
            except (OSError, KeyError, ValueError, TypeError, IndexError) as exc:
                issue(op, f"Unresolvable local reference {ref}: {exc}", pointer)
                return copy.deepcopy(value)
        return {k: resolve(v, origin, op, f"{pointer}/{k}", stack) for k, v in value.items()}

    def schema(value: Any, op: str, pointer: str):
        if isinstance(value, bool):
            return value
        if not isinstance(value, dict):
            issue(op, "Schema must be an object or boolean", pointer)
            return value
        for key in value:
            if key not in SCHEMA_KEYS and not key.startswith("x-"):
                issue(op, f"Schema keyword {key!r} is not supported", pointer)
        result = copy.deepcopy(value)
        if result.get("nullable"):
            if isinstance(result.get("type"), str):
                result["type"] = [result["type"], "null"]
            else:
                issue(op, "nullable requires an explicit type", pointer)
        result.pop("nullable", None)
        for key in ("properties",):
            if isinstance(result.get(key), dict):
                result[key] = {n: schema(s, op, f"{pointer}/{key}/{n}") for n, s in result[key].items()}
        for key in ("items", "additionalProperties"):
            if isinstance(result.get(key), (dict, bool)):
                result[key] = schema(result[key], op, f"{pointer}/{key}")
        return result

    for route, path_item in document.get("paths", {}).items():
        route_pointer = "#/paths/" + route.replace("~", "~0").replace("/", "~1")
        if not isinstance(path_item, dict):
            continue
        if "$ref" in path_item:
            path_item = resolve(path_item, path, "", route_pointer)
        for method, raw_op in path_item.items():
            if method.lower() not in METHODS:
                continue
            operation_id = raw_op.get("operationId") or method.lower() + "_" + re.sub(r"[^a-zA-Z0-9]+", "_", route).strip("_")
            pointer = route_pointer + "/" + method
            if operation_id in contract["operations"]:
                issue(operation_id, "Duplicate operationId", pointer)
                continue
            source_ids = [add_source(contract["sources"], path, pointer,
                json.dumps(raw_op, ensure_ascii=False), "openapi-operation")]
            op = resolve(raw_op, path, operation_id, pointer)
            parameters = []
            raw_params = path_item.get("parameters", []) + op.get("parameters", [])
            param_map = {}
            for n, raw_parameter in enumerate(raw_params):
                p = resolve(raw_parameter, path, operation_id, pointer + f"/parameters/{n}")
                if "schema" not in p or p.get("in") not in ("path", "query", "header", "cookie"):
                    issue(operation_id, "Only simple schema parameters in path/query/header/cookie are supported", pointer)
                    continue
                ps = schema(p["schema"], operation_id, pointer + "/parameters/" + p["name"])
                if p.get("style") not in (None, "simple", "form") or ps.get("type") in ("array", "object"):
                    issue(operation_id, "Complex parameter serialization is not supported", pointer)
                param_map[(p["in"], p["name"])] = {"name": p["name"], "in": p["in"],
                    "required": p.get("required", False), "schema": ps, **({"example": p["example"]} if "example" in p else {})}
            parameters = list(param_map.values())
            body = op.get("requestBody", {})
            content = body.get("content", {})
            if content and set(content) != {"application/json"}:
                issue(operation_id, "Only application/json request bodies are supported", pointer + "/requestBody")
            media = content.get("application/json", {})
            request_schema = schema(media.get("schema", {}), operation_id, pointer + "/requestBody/schema")
            request_example = media.get("example", request_schema.get("example", {}) if isinstance(request_schema, dict) else {})
            if "examples" in media:
                issue(operation_id, "Named media examples require an explicit profile request", pointer + "/requestBody/examples")
            responses = {}
            for status, response in op.get("responses", {}).items():
                rcontent = response.get("content", {})
                if rcontent and set(rcontent) != {"application/json"}:
                    issue(operation_id, "Only application/json response bodies are supported", pointer + f"/responses/{status}")
                if response.get("links"):
                    issue(operation_id, "OpenAPI links require explicit profile steps", pointer + f"/responses/{status}/links")
                responses[str(status)] = schema(rcontent.get("application/json", {}).get("schema", {}),
                                                 operation_id, pointer + f"/responses/{status}/schema")
            success = [v for k, v in responses.items() if k.startswith("2")]
            security = op.get("security", document.get("security", []))
            schemes = document.get("components", {}).get("securitySchemes", {})
            auth = {}
            if security:
                if len(security) != 1 or len(security[0]) != 1:
                    issue(operation_id, "Alternative or combined security schemes require explicit support", pointer + "/security")
                else:
                    name = next(iter(security[0]))
                    auth = resolve(schemes.get(name, {}), path, operation_id, "#/components/securitySchemes/" + name)
                    if not (auth.get("type") == "apiKey" and auth.get("in") in ("header", "query", "cookie") or
                            auth.get("type") == "http" and auth.get("scheme", "").lower() == "bearer"):
                        issue(operation_id, "Security scheme not supported", pointer + "/security")
            if op.get("callbacks") or document.get("webhooks"):
                issue(operation_id, "Callbacks/webhooks are not supported", pointer)
            contract["operations"][operation_id] = {"id": operation_id, "method": method.upper(),
                "path": route, "parameters": parameters, "request_schema": request_schema,
                "request_example": request_example, "response_schema": success[0] if success else {},
                "responses": responses, "auth": auth, "source_ids": source_ids,
                "business_rules": op.get("description", "")}
