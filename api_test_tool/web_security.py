"""Constraints for the HTTP-facing application, beyond the local CLI trust model."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import yaml

from .document_limits import MAX_DOCUMENT_BYTES, DOCUMENT_LIMIT_LABEL

LEGACY_HOST = "198.51.100.10"


def check_public_endpoint(url: str, trusted_origins=()) -> None:
    part = urlsplit(url)
    try:
        port = part.port or (443 if part.scheme == "https" else 80)
    except ValueError:
        raise ValueError("API 地址的端口无效") from None
    if (not part.hostname or part.username or part.password or part.query or part.fragment
            or part.scheme not in {"http", "https"} or "\\" in url
            or any(ord(char) < 33 for char in url)):
        raise ValueError("请填写不含账号、查询参数或片段的 HTTP(S) API 地址")
    if part.hostname == LEGACY_HOST:
        raise ValueError("旧共享测试服务已停用，请选择独立测试环境")
    origin = part.scheme + "://" + part.netloc
    if origin in trusted_origins:
        return
    if part.scheme != "https":
        raise ValueError("自定义 API 必须使用 HTTPS；内网 HTTP 仅开放已配置的独立示例服务")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(part.hostname, port, type=socket.SOCK_STREAM)}
    except OSError:
        raise ValueError("API 地址无法解析，请检查域名") from None
    if not addresses or any(address == LEGACY_HOST or not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("该地址指向未授权内网或系统网络，不能从网页访问；请由管理员配置独立环境")


def check_document(text: str, filename: str) -> None:
    if not text.strip():
        raise ValueError("接口文档不能为空")
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"单份文档不能超过 {DOCUMENT_LIMIT_LABEL}")
    if filename.lower().endswith((".md", ".markdown")):
        return
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        raise ValueError("文档不是有效的 JSON / YAML") from None
    seen = set()
    count = 0

    def visit(value, depth=0):
        nonlocal count
        count += 1
        if count > 30000 or depth > 50:
            raise ValueError("文档结构过大或嵌套过深")
        if isinstance(value, (dict, list)):
            if id(value) in seen:
                raise ValueError("请展开 YAML 锚点引用后导入")
            seen.add(id(value))
            if isinstance(value, dict):
                if "pattern" in value or "patternProperties" in value:
                    raise ValueError("这一版网页暂不支持 Schema 正则 pattern / patternProperties，请移除后导入；其他类型与边界仍可校验")
                if "$ref" in value and (not isinstance(value["$ref"], str) or not value["$ref"].startswith("#/")):
                    raise ValueError("网页只接受文档内部 #/ 引用，跨文件引用请先合并；不会读取服务器文件")
                for item in value.values():
                    visit(item, depth + 1)
            else:
                for item in value:
                    visit(item, depth + 1)
            seen.remove(id(value))

    visit(document)


def check_web_bundle(bundle: dict) -> None:
    cases = bundle.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("cases 必须是数组")
    for case in cases:
        if case.get("state") != "READY":
            continue
        for step in case.get("steps", []) + case.get("cleanup_steps", []):
            request = step.get("request", {})
            if len(str(request)) > 65536:
                raise ValueError("单次请求输入超过 64 KB")
            forbidden = {"host", "proxy-authorization", "connection", "transfer-encoding", "content-length"}
            if forbidden & {name.lower() for name in request.get("headers", {})}:
                raise ValueError("网页测试不允许覆盖 Host、代理或传输控制请求头")
