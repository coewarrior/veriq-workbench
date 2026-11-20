"""Small, bounded text-only adapters for user-supplied model APIs.

No SDK globals, retries, provider fallback, disk storage, or raw response logging.
Provider presets are configuration conveniences, not evidence of live model tests.
"""
from __future__ import annotations

import ipaddress
import json
import math
import re
import time
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import HTTPError as UrllibHTTPError, ReadTimeoutError


PROTOCOLS = ("openai_responses", "openai_chat", "anthropic", "gemini")
MAX_PROMPT_BYTES = 262144
MAX_RESPONSE_BYTES = 128 * 1024 * 1024
# Published DeepSeek V4 capacity, verified 2026-09-10. Manual values are never clamped.
AUTO_OUTPUT_TOKENS = {name: 384_000 for name in (
    "deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp")}
PROVIDERS = [
    {"id": "openai", "name": "OpenAI", "protocol": "openai_responses", "base_url": "https://api.openai.com/v1", "model_hint": "填写账户可用的模型名称", "docs_url": "https://developers.openai.com/api/reference/cli/resources/responses/methods/create"},
    {"id": "deepseek", "name": "DeepSeek", "protocol": "openai_chat", "base_url": "https://api.deepseek.com/v1", "model_hint": "填写 DeepSeek 控制台中的模型名称", "docs_url": "https://api-docs.deepseek.com/"},
    {"id": "qwen", "name": "通义千问 Qwen", "protocol": "openai_chat", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model_hint": "填写百炼中已开通的模型名称", "docs_url": "https://help.aliyun.com/en/model-studio/base-url"},
    {"id": "glm", "name": "智谱 GLM", "protocol": "openai_chat", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model_hint": "填写智谱控制台中的模型名称", "docs_url": "https://docs.bigmodel.cn/cn/guide/develop/openai/introduction"},
    {"id": "kimi", "name": "Kimi", "protocol": "openai_chat", "base_url": "https://api.moonshot.cn/v1", "model_hint": "填写 Kimi 控制台中的模型名称", "docs_url": "https://platform.kimi.com/docs/get-api-key"},
    {"id": "doubao", "name": "豆包 / 火山方舟", "protocol": "openai_chat", "base_url": "https://ark.cn-beijing.volces.com/api/v3", "model_hint": "填写方舟中可调用的模型名称 或接入点 ID", "docs_url": "https://www.volcengine.com/docs/82379/1399008"},
    {"id": "minimax", "name": "MiniMax", "protocol": "openai_chat", "base_url": "https://api.minimaxi.com/v1", "model_hint": "填写 MiniMax 控制台中的模型名称", "docs_url": "https://platform.minimaxi.com/docs/api-reference/text-openai-api"},
    {"id": "claude", "name": "Anthropic Claude", "protocol": "anthropic", "base_url": "https://api.anthropic.com/v1", "model_hint": "填写 Claude API 可用的模型名称", "docs_url": "https://platform.claude.com/docs/en/api/http/messages/create"},
    {"id": "gemini", "name": "Google Gemini", "protocol": "gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta", "model_hint": "填写 Gemini API 可用的模型名称", "docs_url": "https://ai.google.dev/api/generate-content"},
    {"id": "custom", "name": "自定义 / OpenAI 兼容", "protocol": "openai_chat", "base_url": "", "model_hint": "填写服务支持的模型名称", "docs_url": "https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create"},
]


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    protocol: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    max_tokens: int | None = None  # None: provider capacity/default; never guess a small budget.
    timeout: float = 90  # Socket inactivity timeout, not total request duration.


class ModelConfigError(ValueError):
    """Invalid configuration, rejected before any network access."""


class ModelAPIError(RuntimeError):
    """Sanitized, user-visible failure without upstream payloads or headers."""

    def __init__(self, message: str, code: str = "model_api_error", http_status: int | None = None, *, output_limited: bool = False):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.output_limited = output_limited


def _loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_config(config: ModelConfig) -> None:
    if not isinstance(config, ModelConfig):
        raise ModelConfigError("模型配置格式不正确。")
    if not isinstance(config.provider, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", config.provider):
        raise ModelConfigError("供应商标识格式不正确。")
    if config.protocol not in PROTOCOLS:
        raise ModelConfigError("请选择支持的模型协议。")
    if not isinstance(config.base_url, str) or not config.base_url or len(config.base_url) > 2048:
        raise ModelConfigError("请填写模型 API 的 Base URL。")
    if re.search(r"[\s\\\x00-\x1f\x7f]", config.base_url):
        raise ModelConfigError("模型 Base URL 不能包含空白、控制字符或反斜杠。")
    try:
        parsed = urlsplit(config.base_url)
        host = parsed.hostname
        port = parsed.port
        if not host or parsed.username is not None or parsed.password is not None:
            raise ValueError
        if parsed.query or parsed.fragment or "?" in config.base_url or "#" in config.base_url:
            raise ValueError
        if parsed.scheme != "https" and not (parsed.scheme == "http" and _loopback(host)):
            raise ValueError
        if port is not None and not 1 <= port <= 65535:
            raise ValueError
        if "%" in parsed.netloc or any(part in (".", "..") for part in parsed.path.split("/")):
            raise ValueError
        # URL paths are configuration, not an encoded place to hide API keys.
        if "%" in parsed.path or "//" in parsed.path:
            raise ValueError
    except (ValueError, TypeError):
        raise ModelConfigError("Base URL 必须是 HTTPS 地址，且不能含账号、查询参数或片段；HTTP 仅允许本机 mock。") from None
    if not isinstance(config.model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", config.model):
        raise ModelConfigError("请填写有效模型名称（不能含空格或控制字符）。")
    if config.protocol == "gemini" and not re.fullmatch(r"(?:models/)?[A-Za-z0-9][A-Za-z0-9._-]{0,199}", config.model):
        raise ModelConfigError("Gemini 模型名称 格式不正确。")
    if not isinstance(config.api_key, str) or not 1 <= len(config.api_key) <= 8192 or re.search(r"[^\x21-\x7e]", config.api_key):
        raise ModelConfigError("请填写有效的 API Key，不能含空白或控制字符。")
    if config.max_tokens is not None and (type(config.max_tokens) is not int or config.max_tokens <= 0):
        raise ModelConfigError("单次输出额度请填写正整数，或留空使用自动配置。")
    if isinstance(config.timeout, bool) or not isinstance(config.timeout, (int, float)) or not math.isfinite(config.timeout) or not 1 <= config.timeout <= 180:
        raise ModelConfigError("无响应等待时间必须在 1–180 秒之间。")
    _endpoint(config)


def _endpoint(config: ModelConfig) -> str:
    parsed = urlsplit(config.base_url)
    path = parsed.path.rstrip("/")
    if config.protocol == "gemini":
        model = config.model.removeprefix("models/")
        if path.endswith(":streamGenerateContent"):
            path = path.removesuffix(":streamGenerateContent") + ":generateContent"
        if path.endswith(":generateContent"):
            if not path.endswith("/models/" + model + ":generateContent"):
                raise ModelConfigError("Base URL 中的 Gemini 模型与模型名称 不一致。")
        else:
            path = path or "/v1beta"
            if not path.endswith("/models"):
                path += "/models"
            path += "/" + quote(model, safe="") + ":generateContent"
    else:
        suffix = {"openai_responses": "/responses", "openai_chat": "/chat/completions", "anthropic": "/messages"}[config.protocol]
        if not path.endswith(suffix):
            if any(path.endswith(other) for other in ("/responses", "/chat/completions", "/messages")):
                raise ModelConfigError("Base URL 中的完整接口路径与所选协议不一致。")
            path = (path or "/v1") + suffix
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _request(config: ModelConfig, system_prompt: str, user_prompt: str) -> tuple[str, dict, dict]:
    tokens = config.max_tokens if config.max_tokens is not None else AUTO_OUTPUT_TOKENS.get(config.model)
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream, application/json"}
    if config.protocol == "openai_responses":
        headers["Authorization"] = "Bearer " + config.api_key
        payload = {"model": config.model, "instructions": system_prompt, "input": user_prompt,
                   "max_output_tokens": tokens, "store": False, "stream": True}
    elif config.protocol == "openai_chat":
        headers["Authorization"] = "Bearer " + config.api_key
        is_openai = config.provider == "openai" or urlsplit(config.base_url).hostname == "api.openai.com"
        # OpenAI now uses max_completion_tokens. Most compatible APIs document max_tokens.
        token_field = "max_completion_tokens" if is_openai or config.provider == "minimax" else "max_tokens"
        system_role = "developer" if is_openai and re.match(r"(?:o\d|gpt-[5-9])", config.model) else "system"
        payload = {"model": config.model, "messages": [{"role": system_role, "content": system_prompt}, {"role": "user", "content": user_prompt}],
                   token_field: tokens, "stream": True}
        if config.provider == "minimax":
            payload["reasoning_split"] = True
    elif config.protocol == "anthropic":
        headers.update({"x-api-key": config.api_key, "anthropic-version": "2023-06-01"})
        payload = {"model": config.model, "system": system_prompt,
                   "messages": [{"role": "user", "content": user_prompt}], "max_tokens": tokens, "stream": True}
    else:
        headers["x-goog-api-key"] = config.api_key
        payload = {"systemInstruction": {"parts": [{"text": system_prompt}]},
                   "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                   "generationConfig": {"maxOutputTokens": tokens, "candidateCount": 1}}
    payload = {k: v for k, v in payload.items() if v is not None}
    if config.protocol == "gemini" and tokens is None:
        payload["generationConfig"].pop("maxOutputTokens", None)
    endpoint = _endpoint(config)
    if config.protocol == "gemini":
        endpoint = endpoint.removesuffix(":generateContent") + ":streamGenerateContent?alt=sse"
    return endpoint, headers, payload


def _parts_text(parts: Any, kinds: tuple[str, ...] = ("text",)) -> str:
    if isinstance(parts, str):
        return parts
    if not isinstance(parts, list):
        return ""
    return "".join(part["text"] for part in parts if isinstance(part, dict) and part.get("type", "text") in kinds
                   and isinstance(part.get("text"), str) and part.get("thought") is not True)


def _extract(data: dict, protocol: str) -> tuple[str, dict]:
    if data.get("error") or (isinstance(data.get("base_resp"), dict) and data["base_resp"].get("status_code", 0) != 0):
        raise _provider_error(data)
    if protocol == "openai_responses":
        if data.get("status") in ("incomplete", "failed", "cancelled"):
            raise ModelAPIError("模型未完整生成结果，请核对输出 Token 上限和模型状态。", "incomplete_output",
                                output_limited=isinstance(data.get("incomplete_details"), dict) and data["incomplete_details"].get("reason") == "max_output_tokens")
        output = data.get("output", [])
        if isinstance(output, list) and any(isinstance(item, dict) and item.get("type") not in ("message", "reasoning") for item in output):
            raise ModelAPIError("模型返回了工具调用或其他非文本结果，当前生成流程需要完整文本。", "incomplete_output")
        result = "".join(_parts_text(item.get("content"), ("output_text",)) for item in output if isinstance(item, dict) and item.get("type") == "message") if isinstance(output, list) else ""
        if not result and isinstance(data.get("output_text"), str):
            result = data["output_text"]
        return result, data.get("usage", {})
    if protocol == "openai_chat":
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return "", {}
        choice = choices[0]
        if choice.get("finish_reason") in ("length", "content_filter", "tool_calls", "function_call"):
            reason = choice.get("finish_reason")
            explanation = {"length": "模型服务报告输出长度受限，未生成完整用例。请确认 API 管理使用自动额度；若已自动配置，可能达到服务商的输出或上下文上限，需要拆分文档。", "content_filter": "模型服务过滤了本次输出，请调整文档内容后重试。", "tool_calls": "模型返回了工具调用，当前生成流程需要完整文本。", "function_call": "模型返回了函数调用，当前生成流程需要完整文本。"}
            raise ModelAPIError(explanation[reason], "incomplete_output", output_limited=reason == "length")
        message = choice.get("message")
        return _parts_text(message.get("content")) if isinstance(message, dict) else "", data.get("usage", {})
    if protocol == "anthropic":
        if data.get("stop_reason") in ("max_tokens", "tool_use", "pause_turn", "refusal"):
            raise ModelAPIError("模型未完成纯文本输出，请核对 Token 上限及模型响应模式。", "incomplete_output", output_limited=data.get("stop_reason") == "max_tokens")
        return _parts_text(data.get("content")), data.get("usage", {})
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        return "", {}
    candidate = candidates[0]
    if candidate.get("finishReason") not in (None, "STOP"):
        raise ModelAPIError("Gemini 未完整生成文本，可能达到 Token 上限或被内容策略阻止。", "incomplete_output", output_limited=candidate.get("finishReason") == "MAX_TOKENS")
    content = candidate.get("content")
    return _parts_text(content.get("parts")) if isinstance(content, dict) else "", data.get("usageMetadata", {})


def _usage(usage: Any) -> dict:
    """Return numeric counters only; vendor metadata can contain arbitrary strings."""
    if not isinstance(usage, dict):
        return {}
    normalized = {}
    fields = {"input_tokens": ("input_tokens", "prompt_tokens", "promptTokenCount"),
              "output_tokens": ("output_tokens", "completion_tokens", "candidatesTokenCount"),
              "total_tokens": ("total_tokens", "totalTokenCount"),
              "reasoning_tokens": ("thoughtsTokenCount",),
              "cache_read_tokens": ("cache_read_input_tokens", "cachedContentTokenCount")}
    for name, aliases in fields.items():
        for alias in aliases:
            number = usage.get(alias)
            if type(number) is int and 0 <= number < 10**12:
                normalized[name] = number
                break
    for details_key in ("output_tokens_details", "completion_tokens_details"):
        details = usage.get(details_key)
        if isinstance(details, dict) and type(details.get("reasoning_tokens")) is int and 0 <= details["reasoning_tokens"] < 10**12:
            normalized["reasoning_tokens"] = details["reasoning_tokens"]
    if "total_tokens" not in normalized and "input_tokens" in normalized and "output_tokens" in normalized:
        normalized["total_tokens"] = normalized["input_tokens"] + normalized["output_tokens"]
    return normalized


def _http_error(status: int) -> ModelAPIError:
    hints = {400: "请求参数与模型不兼容，请核对协议、模型名称 和输出 Token 上限。",
             401: "API Key 无效或与所选区域、套餐不匹配。", 403: "账户没有调用该模型的权限。",
             404: "接口地址或模型不存在，请核对 Base URL 和模型名称。", 408: "模型服务处理超时。",
             413: "提示词超过模型服务允许的大小。", 429: "模型服务限流或账户额度不足。"}
    hint = hints.get(status, "模型服务暂时不可用。" if status >= 500 else "模型服务未接受请求。")
    return ModelAPIError(f"模型 API 返回 HTTP {status}：{hint}", "http_error", status)


class _Progress:
    """Publish phases/counts only; never publish model text or private reasoning."""
    def __init__(self, callback):
        self.callback = callback
        self.phase = "等待模型响应"
        self.last_phase = None
        self.last_at = 0
        self.count = 0

    def update(self, phase=None, count=None):
        if phase:
            self.phase = phase
        if count is not None:
            self.count = count
        now = time.monotonic()
        if self.callback and (self.last_phase != self.phase or now - self.last_at >= 5):
            suffix = f"（已接收 {self.count} 个字符）" if self.phase == "正在接收模型结果" else ""
            self.callback(self.phase + suffix)
            self.last_phase, self.last_at = self.phase, now


def _body_chunks(response, progress):
    """read1 returns available bytes without waiting to fill a 4 KiB buffer.

    The socket read timeout measures inactivity, not total generation duration.
    In particular, SSE heartbeats and reasoning deltas keep the connection alive.
    """
    total = 0
    while True:
        chunk = response.raw.read1(4096, decode_content=True)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise ModelAPIError("模型响应超过 128 MiB 接收保护阈值，已停止读取。", "response_too_large")
        progress.update()
        yield chunk


def _sse_events(chunks):
    """Bounded by _body_chunks; support split UTF-8, CR/LF, comments and multiline data."""
    pending = b""
    event, data = "", []
    for chunk in chunks:
        pending += chunk
        while True:
            match = re.search(b"[\r\n]", pending)
            if not match or (pending[match.start():] == b"\r"):
                break
            at = match.start()
            line = pending[:at].decode("utf-8-sig")
            width = 2 if pending[at:at + 2] == b"\r\n" else 1
            pending = pending[at + width:]
            if not line:
                if data:
                    yield event, "\n".join(data)
                event, data = "", []
            elif not line.startswith(":"):
                field, _, value = line.partition(":")
                value = value.removeprefix(" ")
                if field == "event":
                    event = value
                elif field == "data":
                    data.append(value)
    # An unterminated event is not evidence that the model completed its response.


def _stream_result(chunks, protocol, progress):
    parts, usage, model = [], {}, None
    finish, stopped = None, False
    blocks = {}
    char_count = 0

    def append(value):
        nonlocal char_count
        if value:
            parts.append(value)
            char_count += len(value)
            progress.update("正在接收模型结果", char_count)

    def assembled():
        if protocol == "openai_chat":
            return {"model": model, "usage": usage, "choices": [{"message": {"content": "".join(parts)}, "finish_reason": finish}]}
        if protocol == "anthropic":
            return {"model": model, "usage": usage, "content": [{"type": "text", "text": "".join(parts)}], "stop_reason": finish}
        return {"modelVersion": model, "usageMetadata": usage, "candidates": [{"content": {"parts": [{"text": "".join(parts)}]}, "finishReason": finish}]}

    for event, raw in _sse_events(chunks):
        if raw == "[DONE]":
            if protocol == "openai_chat" and finish == "stop":
                return assembled()
            break
        try:
            data = json.loads(raw)
        except ValueError:
            raise ModelAPIError("模型流式响应格式错误，未使用不完整结果。", "invalid_json") from None
        if not isinstance(data, dict):
            raise ModelAPIError("模型流式响应结构错误。", "invalid_response")
        kind = data.get("type", event)
        if data.get("error") or kind == "error" or (isinstance(data.get("base_resp"), dict) and data["base_resp"].get("status_code", 0)):
            raise _provider_error(data)
        if isinstance(data.get("model", data.get("modelVersion")), str):
            model = data.get("model", data.get("modelVersion"))

        if protocol == "openai_responses":
            if kind in ("response.completed", "response.failed", "response.incomplete", "response.cancelled"):
                final = data.get("response")
                if not isinstance(final, dict):
                    raise ModelAPIError("模型结束事件缺少完整响应。", "invalid_response")
                if kind != "response.completed" and final.get("status") == "completed":
                    raise ModelAPIError("模型结束状态不一致。", "invalid_response")
                _extract(final, protocol)
                if final.get("status") != "completed":
                    raise ModelAPIError("模型未完成响应。", "incomplete_output")
                return final
            if kind == "response.output_text.delta":
                # The completed response is authoritative; only count partial text.
                delta = data.get("delta")
                if isinstance(delta, str):
                    char_count += len(delta)
                    progress.update("正在接收模型结果", char_count)
            elif isinstance(kind, str) and kind.startswith("response.reasoning"):
                progress.update("模型思考中")
            elif kind in ("response.created", "response.in_progress"):
                progress.update("模型已接收请求，正在处理")

        elif protocol == "openai_chat":
            if isinstance(data.get("usage"), dict):
                usage.update(data["usage"])
            choices = data.get("choices")
            if not isinstance(choices, list):
                continue
            for choice in choices:
                if not isinstance(choice, dict) or choice.get("index", 0) != 0:
                    continue
                delta = choice.get("delta", {})
                if not isinstance(delta, dict):
                    raise ModelAPIError("模型增量内容格式错误。", "invalid_response")
                if delta.get("tool_calls") or delta.get("function_call") or delta.get("refusal"):
                    raise ModelAPIError("模型返回了工具调用或拒绝输出，未生成完整文本。", "incomplete_output")
                if delta.get("reasoning_content") or delta.get("reasoning"):
                    progress.update("模型思考中")
                append(_parts_text(delta.get("content")))
                if choice.get("finish_reason") is not None:
                    finish = choice["finish_reason"]
                    _extract(assembled(), protocol)
                    if finish != "stop":
                        raise ModelAPIError("模型返回了未支持的结束状态，未使用部分结果。", "incomplete_output")

        elif protocol == "anthropic":
            if kind == "message_start":
                message = data.get("message", {})
                if not isinstance(message, dict):
                    raise ModelAPIError("模型起始响应格式错误。", "invalid_response")
                model = message.get("model", model)
                if isinstance(message.get("usage"), dict):
                    usage.update(message["usage"])
                progress.update("模型已接收请求，正在处理")
            elif kind == "content_block_start":
                block = data.get("content_block", {})
                if not isinstance(block, dict):
                    raise ModelAPIError("模型内容块格式错误。", "invalid_response")
                blocks[data.get("index")] = block.get("type")
                if block.get("type") == "text":
                    append(_parts_text([block]))
                elif block.get("type") == "thinking":
                    progress.update("模型思考中")
                elif block.get("type") == "tool_use":
                    raise ModelAPIError("模型返回了工具调用，当前生成流程需要完整文本。", "incomplete_output")
            elif kind == "content_block_delta":
                delta = data.get("delta", {})
                if not isinstance(delta, dict):
                    raise ModelAPIError("模型增量内容格式错误。", "invalid_response")
                if delta.get("type") == "text_delta" and blocks.get(data.get("index")) == "text":
                    append(_parts_text(delta.get("text")))
                elif delta.get("type") == "thinking_delta":
                    progress.update("模型思考中")
            elif kind == "message_delta":
                delta = data.get("delta", {})
                if isinstance(delta, dict) and delta.get("stop_reason"):
                    finish = delta["stop_reason"]
                    _extract(assembled(), protocol)
                if isinstance(data.get("usage"), dict):
                    usage.update(data["usage"])
            elif kind == "message_stop":
                if finish not in ("end_turn", "stop_sequence"):
                    break
                return assembled()

        else:
            feedback = data.get("promptFeedback", {})
            if isinstance(feedback, dict) and feedback.get("blockReason"):
                raise ModelAPIError("Gemini 拒绝了本次输入，请检查内容策略。", "incomplete_output")
            if isinstance(data.get("usageMetadata"), dict):
                usage.update(data["usageMetadata"])
            candidates = data.get("candidates", [])
            if not isinstance(candidates, list):
                raise ModelAPIError("Gemini 流式响应结构错误。", "invalid_response")
            for candidate in candidates:
                if not isinstance(candidate, dict) or candidate.get("index", 0) != 0:
                    continue
                content = candidate.get("content", {})
                content_parts = content.get("parts", []) if isinstance(content, dict) else []
                if isinstance(content_parts, list):
                    if any(isinstance(p, dict) and p.get("functionCall") for p in content_parts):
                        raise ModelAPIError("Gemini 返回了函数调用，当前生成流程需要完整文本。", "incomplete_output")
                    if any(isinstance(p, dict) and p.get("thought") is True for p in content_parts):
                        progress.update("模型思考中")
                append(_parts_text(content_parts))
                if candidate.get("finishReason"):
                    finish = candidate["finishReason"]
                    _extract(assembled(), protocol)
                    stopped = finish == "STOP"
    if protocol == "gemini" and stopped:
        return assembled()
    if protocol == "openai_chat" and finish == "stop":
        return assembled()
    raise ModelAPIError("模型连接已结束，但没有收到完整结束标记；未使用部分结果。", "stream_interrupted")


def _provider_error(data):
    """Show classified provider codes, without copying arbitrary upstream payloads."""
    error = data.get("error", data)
    if not isinstance(error, dict):
        error = {}
    code = error.get("code") or error.get("type")
    reasons = {"invalid_api_key": "API Key 无效", "authentication_error": "身份验证失败",
               "permission_error": "账户没有调用权限", "invalid_request_error": "请求参数不符合模型要求",
               "insufficient_quota": "账户额度不足", "rate_limit_exceeded": "请求超过服务商速率限制",
               "rate_limit_error": "请求超过服务商速率限制", "overloaded_error": "模型服务当前过载",
               "server_error": "模型服务内部错误", "api_error": "模型服务内部错误",
               "context_length_exceeded": "输入与输出超过模型上下文容量"}
    if isinstance(code, str) and code in reasons:
        return ModelAPIError(f"模型服务返回错误：{reasons[code]}（{code}）。", "upstream_error")
    return ModelAPIError("模型服务返回错误，请核对模型、请求参数及账户状态。", "upstream_error")


def _anthropic_output_capacity(config, session):
    endpoint = _endpoint(config).removesuffix("/messages") + "/models/" + quote(config.model, safe="")
    failure = "该服务未提供模型输出额度信息。请在 API 管理中手动填写该模型支持的单次输出额度。"
    try:
        with session.get(endpoint, headers={"x-api-key": config.api_key, "anthropic-version": "2023-06-01"},
                         timeout=(10, min(config.timeout, 30)), allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise ModelConfigError(failure)
            body = bytearray()
            for chunk in response.iter_content(chunk_size=4096):
                body.extend(chunk)
                if len(body) > 1024 * 1024:
                    raise ModelConfigError(failure)
            data = json.loads(body)
            value = data.get("max_tokens") if isinstance(data, dict) else None
            if type(value) is not int or value <= 0:
                raise ModelConfigError(failure)
            return value
    except (requests.exceptions.RequestException, ValueError):
        raise ModelConfigError(failure) from None


def generate_text(config: ModelConfig, system_prompt: str, user_prompt: str, *, session_factory=None, on_progress=None) -> dict:
    validate_config(config)
    if not isinstance(system_prompt, str) or not isinstance(user_prompt, str) or not user_prompt.strip():
        raise ModelConfigError("请提供有效的文本提示词。")
    if len(system_prompt.encode("utf-8")) + len(user_prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise ModelConfigError("提示词过长，请缩小文档范围后重试（上限 256 KiB）。")
    started = time.monotonic()
    response = None
    progress = _Progress(on_progress)
    progress.update()
    try:
        with (session_factory or requests.Session)() as session:
            if session_factory is None:
                session.trust_env = False
                session.mount("https://", HTTPAdapter(max_retries=0))
                session.mount("http://", HTTPAdapter(max_retries=0))
            if config.max_tokens is None and config.protocol == "anthropic" and config.model not in AUTO_OUTPUT_TOKENS:
                progress.update("正在读取模型支持的输出额度")
                config = replace(config, max_tokens=_anthropic_output_capacity(config, session))
            url, headers, payload = _request(config, system_prompt, user_prompt)
            budget = payload.get("max_tokens", payload.get("max_completion_tokens", payload.get("max_output_tokens")))
            if config.protocol == "gemini":
                budget = payload["generationConfig"].get("maxOutputTokens")
            progress.update(f"本次输出额度：{budget:,} Token" if budget else "本次输出额度：由模型服务决定")
            progress.update("等待模型响应")
            response = session.post(url, headers=headers, json=payload, timeout=(min(10, config.timeout), config.timeout),
                                    allow_redirects=False, stream=True)
            if 300 <= response.status_code < 400:
                raise ModelAPIError("模型 API 返回重定向，已停止；请直接填写最终的 API 地址。", "redirect_blocked", response.status_code)
            if not 200 <= response.status_code < 300:
                raise _http_error(response.status_code)
            length = response.headers.get("Content-Length", "")
            if length.isdigit() and int(length) > MAX_RESPONSE_BYTES:
                raise ModelAPIError("模型响应超过 128 MiB 接收保护阈值，已停止读取。", "response_too_large")
            chunks = _body_chunks(response, progress)
            if response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() == "text/event-stream":
                try:
                    data = _stream_result(chunks, config.protocol, progress)
                except UnicodeError:
                    raise ModelAPIError("模型流式响应包含无效字符。", "invalid_response") from None
            else:
                # Some compatible gateways return JSON even when streaming was requested.
                # Consume the same response without an automatic second paid request.
                progress.update("正在接收模型响应（服务未返回流式内容）")
                try:
                    data = json.loads(b"".join(chunks))
                except (ValueError, UnicodeError):
                    raise ModelAPIError("模型 API 未返回有效 JSON，请核对协议和 Base URL。", "invalid_json") from None
                if not isinstance(data, dict):
                    raise ModelAPIError("模型 API 返回结构不符合所选协议。", "invalid_response")
            result_text, usage = _extract(data, config.protocol)
            if not result_text.strip():
                raise ModelAPIError("模型未返回可用文本，请核对协议、模型能力及输出 Token 上限。", "empty_output")
            # A gateway or model may echo the submitted credential. Never return it.
            result_text = result_text.replace(config.api_key, "[REDACTED]")
            actual_model = data.get("model", data.get("modelVersion", config.model))
            if not isinstance(actual_model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", actual_model):
                actual_model = config.model
            actual_model = actual_model.replace(config.api_key, "[REDACTED]")
            return {"text": result_text, "usage": _usage(usage), "model": actual_model, "protocol": config.protocol,
                    "elapsed_ms": round((time.monotonic() - started) * 1000)}
    except requests.exceptions.ConnectTimeout:
        raise ModelAPIError("连接模型服务超时，尚未建立连接。请检查地址和网络。", "connect_timeout") from None
    except (requests.exceptions.Timeout, ReadTimeoutError):
        raise ModelAPIError(f"连续 {config.timeout:g} 秒未收到模型服务数据，已结束等待；这不代表模型返回了错误。可在 API 管理中调整无响应等待时间。", "timeout") from None
    except (requests.exceptions.RequestException, UrllibHTTPError):
        raise ModelAPIError("无法连接模型服务，请检查地址、网络和 TLS 证书。", "connection_error") from None
    finally:
        if response is not None:
            response.close()


def test_connection(config: ModelConfig, *, session_factory=None, on_progress=None) -> dict:
    """One short paid API request when the user explicitly clicks Test Connection."""
    validate_config(config)
    return generate_text(replace(config, max_tokens=min(config.max_tokens or 256, 256)),
                         "This is a connection check. Respond with the word OK only.", "Reply OK.", session_factory=session_factory, on_progress=on_progress)


# Do not let pytest collect the public operation when imported into a test module.
test_connection.__test__ = False
