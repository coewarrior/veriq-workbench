"""Session interface edits, with current documents and immutable run history."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from .execution import _path_problem
from .parsers import METHODS, add_source, parse_document
from .web_security import check_document


def revision(contract):
    return hashlib.sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def current_document_path(store, owner, project):
    return store.project_dir(owner, project["id"]) / project.get("effective_document_file", project["document_file"])


def operation_document(data, oid):
    if not isinstance(data, dict):
        raise ValueError("请填写接口信息")
    allowed = {"method", "path", "title", "description", "parameters", "request_example", "response_status", "response_example", "request_schema"}
    if set(data) - allowed:
        raise ValueError("接口包含未知字段")
    method, path, title = data.get("method", ""), data.get("path", ""), data.get("title", "")
    if not isinstance(method, str) or method.lower() not in METHODS:
        raise ValueError("请选择有效的 HTTP 方法")
    if not isinstance(path, str) or len(path) > 2000 or _path_problem(path):
        raise ValueError("接口路径应以 / 开头，不含域名、查询串或路径跳转；查询参数在参数中填写")
    if any(c in re.sub(r"\{[^{}]+\}", "", path) for c in "{}"):
        raise ValueError("路径参数请使用 {参数名} 格式")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError("请填写 1–200 字的接口名称")
    description = data.get("description", "")
    if not isinstance(description, str) or len(description) > 12000:
        raise ValueError("接口说明最多 12000 字符")
    parameters = data.get("parameters", [])
    if not isinstance(parameters, list) or len(parameters) > 100:
        raise ValueError("参数应为 JSON 数组，最多 100 项")
    parameters = copy.deepcopy(parameters)
    known = set()
    for p in parameters:
        if (not isinstance(p, dict) or not isinstance(p.get("name"), str) or not p["name"]
                or p.get("in") not in {"query", "path", "header", "cookie"} or not isinstance(p.get("schema"), dict)
                or ("required" in p and type(p["required"]) is not bool)):
            raise ValueError("每个参数需包含 name、in 和 schema；required 为布尔值")
        key = (p["in"], p["name"])
        if key in known:
            raise ValueError("参数名称和位置不能重复")
        known.add(key)
        if p["in"] == "path":
            if "{" + p["name"] + "}" not in path:
                raise ValueError("路径参数必须出现在接口路径中")
            p["required"] = True
    for name in re.findall(r"\{([^{}]+)\}", path):
        if ("path", name) not in known:
            parameters.append({"name": name, "in": "path", "required": True, "schema": {"type": "string"}})
    op = {"operationId": oid, "summary": title.strip(), "description": description, "parameters": parameters, "responses": {}}
    if "request_example" in data or "request_schema" in data:
        schema = data.get("request_schema", {})
        if not isinstance(schema, (dict, bool)):
            raise ValueError("请求 Schema 必须是 JSON 对象或布尔值")
        media = {"schema": schema}
        if "request_example" in data:
            media["example"] = data["request_example"]
        op["requestBody"] = {"content": {"application/json": media}}
    status = data.get("response_status")
    if status is not None:
        if type(status) is not int or not 100 <= status <= 599:
            raise ValueError("预期 HTTP 状态码应为 100–599，未确定时留空")
        response = {"description": "使用者填写的预期响应"}
        if "response_example" in data:
            response["content"] = {"application/json": {"example": data["response_example"]}}
        op["responses"][str(status)] = response
    elif "response_example" in data:
        raise ValueError("填写预期响应时，请同时填写对应 HTTP 状态码")
    return {"openapi": "3.0.3", "info": {"title": title.strip(), "version": "1.0"}, "paths": {path: {method.lower(): op}}}


def effective_document(contract, original):
    """Only active operations appear in paths; original prose remains reference data."""
    document = {"openapi": "3.0.3", "info": {"title": contract.get("title", "接口文档"), "version": "1.0",
        "description": "接口管理后的当前文档。测试范围以 paths 中的接口为准；x-original-document 为导入时原文，仅供对照，不得重新加入已删除接口。"},
        "paths": {}, "components": {"securitySchemes": {}}, "x-original-document": original}
    for oid, op in contract["operations"].items():
        entry = {"operationId": oid, "summary": op.get("summary", op.get("title", oid)),
                 "description": op.get("business_rules", ""), "parameters": op.get("parameters", []), "responses": {}}
        if op.get("request_schema") or op.get("has_request_body") or op.get("request_example") not in ({}, None):
            entry["requestBody"] = {"content": {"application/json": {"schema": op.get("request_schema", {}), "example": op.get("request_example")}}}
        for status, schema in op.get("responses", {}).items():
            entry["responses"][str(status)] = {"description": "已记录的响应约定", "content": {"application/json": {"schema": schema}}}
        # Markdown may not specify status codes. Preserve that gap, without inventing one.
        entry["x-response-schema"] = op.get("response_schema", {})
        entry["x-response-examples"] = op.get("response_examples", [])
        if op.get("auth"):
            key = "auth_" + oid
            document["components"]["securitySchemes"][key] = op["auth"]
            entry["security"] = [{key: []}]
        document["paths"].setdefault(op["path"], {})[op["method"].lower()] = entry
    return json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)


def patch_operation(op, changes):
    """Patch editable fields without losing other responses, auth or constraints."""
    if not isinstance(changes, dict):
        raise ValueError("请填写接口修改内容")
    allowed = {"title", "method", "path", "description", "parameters", "request_schema", "request_example",
               "response_status", "response_example"}
    clear = changes.get("_clear", [])
    if (set(changes) - allowed - {"_clear"} or not isinstance(clear, list)
            or any(k not in {"parameters", "request_schema", "request_example", "response_status", "response_example"} for k in clear)
            or set(clear) & set(changes)):
        raise ValueError("接口修改包含无效字段")
    if not changes or changes == {"_clear": []}:
        return copy.deepcopy(op)
    result = copy.deepcopy(op)
    # Reuse path/method/parameter validation; response fields are handled separately
    # because imported Markdown can have examples without a documented status code.
    fields = {"title": op.get("summary", op.get("title", op["id"])), "method": op["method"],
              "path": op["path"], "description": op.get("business_rules", ""), "parameters": op.get("parameters", [])}
    fields.update({k: v for k, v in changes.items() if k in fields or k in {"request_schema", "request_example"}})
    if "parameters" in clear:
        fields["parameters"] = []
    validated = operation_document(fields, op["id"])["paths"][fields["path"]][fields["method"].lower()]
    result.update(summary=fields["title"].strip(), method=fields["method"].upper(), path=fields["path"],
                  business_rules=fields["description"], parameters=validated["parameters"])
    for key in ("request_schema", "request_example"):
        if key in changes:
            result[key] = copy.deepcopy(changes[key])
        if key in clear:
            result[key] = {}
    if "request_example" in changes or "request_example" in clear:
        result["has_request_example"] = "request_example" not in clear
    if any(k in changes or k in clear for k in ("request_example", "request_schema")):
        result["has_request_body"] = bool(result.get("request_schema") or result.get("has_request_example"))
    statuses = sorted(result.get("responses", {}), key=str)
    primary = next((k for k in statuses if str(k).startswith("2")), statuses[0] if len(statuses) == 1 else None)
    if "response_status" in changes or "response_status" in clear:
        status = changes.get("response_status")
        if status is not None and (type(status) is not int or not 100 <= status <= 599):
            raise ValueError("预期 HTTP 状态码应为 100–599")
        if "response_status" in changes and status is None:
            raise ValueError("状态码不能为空值，请留空清除")
        responses = result.setdefault("responses", {})
        if status is not None and str(status) != primary and str(status) in responses:
            raise ValueError("该响应状态码已经存在，请保留原值或选择其他状态码")
        schema = responses.pop(primary, result.get("response_schema", {})) if primary is not None else result.get("response_schema", {})
        if status is not None:
            responses[str(status)] = schema
        result["response_schema"] = next((v for k, v in responses.items() if str(k).startswith("2")), {})
    if "response_example" in changes:
        examples = result.get("response_examples", [])
        result["response_examples"] = [copy.deepcopy(changes["response_example"])] + examples[1:]
    if "response_example" in clear:
        result["response_examples"] = result.get("response_examples", [])[1:]
    return result


def change_operation(store, owner, project, data=None, delete_id=None, edit_id=None):
    pid = project["id"]
    location = store.project_dir(owner, pid)
    contract = store.load_asset(owner, pid, "contract")
    if edit_id is not None:
        if edit_id not in contract["operations"]:
            raise FileNotFoundError("接口不存在")
        previous = contract["operations"][edit_id]
        op = patch_operation(previous, data)
        if op == previous:
            return contract
        if any(other_id != edit_id and other["path"] == op["path"] and other["method"] == op["method"]
               for other_id, other in contract["operations"].items()):
            raise ValueError("相同方法和路径的接口已存在")
        raw = effective_document({"operations": {edit_id: op}}, "")
        check_document(raw, "interface.json")
        source_path = location / "inputs" / ("edit_" + uuid4().hex + ".json")
        store._write_text(source_path, raw)
        sid = add_source(contract["sources"], source_path, "document", raw, "interface_edit")
        op["source_ids"] = [sid]
        contract["operations"][edit_id] = op
    elif delete_id is not None:
        if delete_id not in contract["operations"]:
            raise FileNotFoundError("接口不存在")
        removed = contract["operations"].pop(delete_id)
        contract.setdefault("removed_operations", {})[delete_id] = removed
        contract["issues"] = [i for i in contract.get("issues", []) if i.get("operation_id") != delete_id]
    else:
        if len(contract["operations"]) >= 200:
            raise ValueError("当前最多支持 200 个接口，请拆分会话")
        oid = "user_" + uuid4().hex[:16]
        document = operation_document(data, oid)
        path = next(iter(document["paths"]))
        method = next(iter(document["paths"][path])).upper()
        if any(op["path"] == path and op["method"] == method for op in contract["operations"].values()):
            raise ValueError("相同方法和路径的接口已存在")
        raw = json.dumps(document, ensure_ascii=False, allow_nan=False)
        check_document(raw, "interface.json")
        source_path = location / "inputs" / (oid + ".json")
        store._write_text(source_path, raw)
        parsed = parse_document(source_path)
        op = parsed["operations"][oid]
        op["summary"] = data["title"].strip()
        op["has_request_example"] = "request_example" in data
        op["has_request_body"] = "request_example" in data or "request_schema" in data
        if "response_example" in data:
            op["response_examples"] = [data["response_example"]]
        contract["operations"][oid] = op
        contract["sources"].update(parsed["sources"])
        contract["issues"].extend(parsed["issues"])
    contract["issues"] = [i for i in contract.get("issues", []) if i.get("code") != "NO_OPERATIONS"]
    original = (location / project["document_file"]).read_text()
    current = location / "inputs/current-interfaces.json"
    store._write_text(current, effective_document(contract, original))
    for source in contract["sources"].values():
        if source.get("kind") == "document":
            source["kind"] = "original_document"
    # The current document source is replaced; historical run snapshots are untouched.
    contract["sources"] = {sid: source for sid, source in contract["sources"].items()
                           if source.get("kind") != "managed_document"}
    add_source(contract["sources"], current, "document", current.read_text(), "managed_document")
    for source in contract["sources"].values():
        source["path"] = "inputs/" + Path(source["path"]).name
    store.save_asset(owner, pid, "contract", contract)
    store.invalidate_cases(owner, pid)
    store.update_project(owner, pid, {"interfaces_modified": True, "effective_document_file": "inputs/current-interfaces.json",
        "effective_filename": "current-interfaces.json", "status": "imported", "last_job": {}, "bundle_summary": {},
        "contract_summary": {"operations": len(contract["operations"]), "issues": len(contract["issues"])}})
    return contract
