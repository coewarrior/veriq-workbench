"""Bounded execution of reviewed cases; dependency steps always stay ordered."""

from __future__ import annotations

from .document_targets import normalize_base_url

import copy
import hashlib
import json
import math
import platform
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter

from .assertions import MISSING, evaluate_assertion, resolve_pointer, valid_pointer, validate_assertion
from .scheduling import CASE_WORKERS, execution_policy_problem


TEMPLATE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SECRET = re.compile(r"password|passwd|pwd|token|cookie|authorization|secret|session|ssid|api[_-]?key|credential", re.I)
PASSWORD_KEY = re.compile(r"password|passwd|pwd", re.I)
PUBLIC_PASSWORD_FIXTURES = {"", "wrong-password", "a", "1", "9", "12"}
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
STATES = {"READY", "NEEDS_RULE", "QUARANTINED", "UNSUPPORTED"}


class ExecutionProblem(ValueError):
    pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> bool:
    try:
        json.dumps(value, allow_nan=False)
        return True
    except (TypeError, ValueError, OverflowError):
        return False


def _provenance(bundle: Any, snapshot: Any) -> dict:
    def version(distribution: str) -> str:
        try:
            return metadata.version(distribution)
        except metadata.PackageNotFoundError:
            return "not-installed"
    def digest(value: Any) -> str | None:
        try:
            canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            return None
        return hashlib.sha256(canonical).hexdigest()
    code_hashes = {}
    for path in sorted(Path(__file__).resolve().parent.glob("*.py")):
        try:
            code_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            code_hashes[path.name] = "unavailable"
    return {
        "python_version": platform.python_version(),
        "tool_version": version("document-api-test"),
        "dependencies": {name: version(name) for name in ("requests", "PyYAML", "jsonschema", "pytest", "allure-pytest")},
        "bundle_sha256": digest(bundle),
        "bundle_snapshot_sha256": digest(snapshot),
        "bundle_hash_encoding": "SHA256 of UTF-8 JSON, sorted keys, compact separators, ensure_ascii=false",
        "code_sha256": code_hashes,
    }


def _template_names(value: Any) -> set[str]:
    if isinstance(value, str):
        if "${" in TEMPLATE.sub("", value):
            raise ExecutionProblem(f"Malformed template: {value!r}")
        return set(TEMPLATE.findall(value))
    if isinstance(value, list):
        return set().union(*(_template_names(item) for item in value)) if value else set()
    if isinstance(value, dict):
        if any(not isinstance(k, str) or "${" in k for k in value):
            raise ExecutionProblem("Template object keys must be literal strings")
        return set().union(*(_template_names(item) for item in value.values())) if value else set()
    return set()


def _contains_redacted(value: Any) -> bool:
    if isinstance(value, str):
        return "<redacted>" in value
    if isinstance(value, dict):
        return any(_contains_redacted(item) for item in value.values())
    return isinstance(value, list) and any(_contains_redacted(item) for item in value)


def render_template(value: Any, variables: dict) -> Any:
    """An exact template preserves JSON type; mixed strings accept scalars only."""
    if isinstance(value, str):
        _template_names(value)
        exact = TEMPLATE.fullmatch(value)
        if exact:
            if exact[1] not in variables:
                raise ExecutionProblem(f"Missing variable: {exact[1]}")
            return copy.deepcopy(variables[exact[1]])
        def replace(match):
            name = match[1]
            if name not in variables:
                raise ExecutionProblem(f"Missing variable: {name}")
            item = variables[name]
            if isinstance(item, (dict, list)):
                raise ExecutionProblem(f"Cannot interpolate non-scalar variable: {name}")
            if item is None:
                return "null"
            if isinstance(item, bool):
                return "true" if item else "false"
            return str(item)
        return TEMPLATE.sub(replace, value)
    if isinstance(value, dict):
        return {key: render_template(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [render_template(item, variables) for item in value]
    return copy.deepcopy(value)


def _path_problem(path: Any) -> str | None:
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        return "Request path must be a relative /path, never an absolute URL"
    if any(ord(char) < 32 or ord(char) == 127 for char in path):
        return "Control characters are forbidden in request paths"
    decoded = path
    for _ in range(3):
        decoded = unquote(decoded)
    parsed = urlsplit(decoded)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or "\\" in decoded or decoded.startswith("//"):
        return "Request paths cannot contain origins, queries, fragments or backslashes; use params"
    if any(segment in {".", ".."} for segment in decoded.split("/")):
        return "Path traversal is forbidden"
    return None


def _origin(url: str) -> str:
    try:
        part = urlsplit(url)
        if part.scheme not in {"http", "https"} or not part.hostname or part.username or part.password:
            raise ValueError()
        if part.port is not None and not 1 <= part.port <= 65535:
            raise ValueError()
        host = f"[{part.hostname}]" if ":" in part.hostname else part.hostname
        port = f":{part.port}" if part.port is not None else ""
        return f"{part.scheme}://{host}{port}"
    except (ValueError, AttributeError, TypeError):
        raise ExecutionProblem("Expected an HTTP(S) URL without embedded credentials") from None


def _validate_environment(environment: Any) -> dict:
    if not isinstance(environment, dict):
        raise ExecutionProblem("Environment must be an object")
    config = dict(environment)
    base = config.get("base_url")
    origin = _origin(base)
    try:
        base = normalize_base_url(base)
    except ValueError as exc:
        raise ExecutionProblem(str(exc)) from None
    allowed = config.get("allowed_origins")
    if not isinstance(allowed, list) or not allowed or any(not isinstance(item, str) or _origin(item) != item for item in allowed):
        raise ExecutionProblem("allowed_origins must contain exact origins with no trailing slash")
    if origin not in allowed:
        raise ExecutionProblem("base_url origin is not explicitly allowed")
    for key, default, upper in (("timeout", 5, 120), ("max_requests", None, None), ("max_response_bytes", 1048576, 10485760)):
        value = config.get(key, default)
        if key == "max_requests" and value is None:
            config[key] = None  # Derived from the selected plan, including cleanup.
            continue
        if type(value) not in {int, float} or not math.isfinite(value) or value <= 0 or upper is not None and value > upper:
            raise ExecutionProblem(f"{key} must be positive and at most {upper}")
        if key != "timeout" and type(value) is not int:
            raise ExecutionProblem(f"{key} must be an integer")
        config[key] = value
    for key in ("stop_on_5xx", "stop_on_network_error", "stop_on_cleanup_failure"):
        value = config.get(key, False)
        if type(value) is not bool:
            raise ExecutionProblem(f"{key} must be a boolean")
        config[key] = value
    workers = config.get("case_workers", 1)
    if type(workers) is not int or not 1 <= workers <= CASE_WORKERS:
        raise ExecutionProblem(f"case_workers must be an integer between 1 and {CASE_WORKERS}")
    # Explicit fail-fast preserves the CLI's strict serial stop semantics.
    config["case_workers"] = 1 if any(config[key] for key in
        ("stop_on_5xx", "stop_on_network_error", "stop_on_cleanup_failure")) else workers
    config.update(base_url=base, allowed_origins=allowed)
    return config


def validate_bundle(bundle: dict) -> list[dict]:
    """Return actionable validation errors even for malformed untrusted shapes."""
    try:
        return _validate_bundle(bundle)
    except (TypeError, ValueError, KeyError, AttributeError, RecursionError) as exc:
        return [{"case_id": "*", "message": f"Malformed bundle structure: {type(exc).__name__}: {exc}"}]


def _validate_bundle(bundle: dict) -> list[dict]:
    """Check the complete READY plan and dependencies before sending any request."""
    errors: list[dict] = []
    def add(case_id, message):
        errors.append({"case_id": case_id, "message": message})
    if not isinstance(bundle, dict) or bundle.get("schema_version") != "1.0":
        return [{"case_id": "*", "message": "Unsupported or missing bundle schema_version"}]
    if not _jsonable(bundle):
        return [{"case_id": "*", "message": "Bundle must contain finite JSON values"}]
    rules_list = bundle.get("rules")
    cases = bundle.get("cases")
    if not isinstance(rules_list, list) or not isinstance(cases, list):
        return [{"case_id": "*", "message": "Bundle rules and cases must be arrays"}]
    contract = bundle.get("contract", {})
    if not isinstance(contract, dict) or not isinstance(contract.get("sources", {}), dict):
        return [{"case_id": "*", "message": "Contract and sources must be objects"}]
    sources = contract.get("sources", {})
    rules = {}
    for rule in rules_list:
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str) or not rule["id"]:
            add("*", "Each rule requires a nonempty id")
            continue
        if rule["id"] in rules:
            add("*", f"Duplicate rule id: {rule['id']}")
        rules[rule["id"]] = rule
    ids = set()
    for case in cases:
        if not isinstance(case, dict):
            add("*", "Case must be an object")
            continue
        cid = case.get("id", "<missing>")
        if not isinstance(cid, str) or not cid or cid in ids:
            add("*", "Case ids must be unique nonempty strings")
            continue
        ids.add(cid)
        if "execution_policy" in case:
            problem = execution_policy_problem(case["execution_policy"])
            if problem:
                add(cid, problem)
        if case.get("state") not in STATES:
            add(cid, "Unknown case state")
            continue
        if case["state"] != "READY":
            continue
        if _contains_redacted({key: case.get(key) for key in ("variables", "steps", "cleanup_steps")}):
            add(cid, "Redacted credentials cannot execute; restore them through trusted configuration")
        rule_ids = case.get("rule_ids")
        if not isinstance(rule_ids, list) or not rule_ids or any(not isinstance(item, str) for item in rule_ids):
            add(cid, "READY cases require documented rule_ids")
            rule_ids = []
        for rid in rule_ids:
            rule = rules.get(rid)
            if not rule or rule.get("state") != "documented":
                add(cid, f"Rule {rid} is absent or not documented")
            elif not isinstance(rule.get("source_ids"), list) or not rule["source_ids"] or any(not isinstance(sid, str) or sid not in sources for sid in rule["source_ids"]):
                add(cid, f"Rule {rid} has no resolvable source evidence")
        declarations = case.get("variables", {})
        if not isinstance(declarations, dict):
            add(cid, "variables must be an object")
            declarations = {}
        for name, declaration in declarations.items():
            if not NAME.fullmatch(name) or not isinstance(declaration, dict) or declaration.get("kind") not in {"unique", "literal"}:
                add(cid, f"Invalid variable declaration: {name}")
            elif declaration["kind"] == "literal" and "value" not in declaration:
                add(cid, f"Literal variable {name} requires value")
            elif declaration["kind"] == "unique" and (not isinstance(declaration.get("prefix", "mvp_"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{0,48}", declaration.get("prefix", "mvp_"))):
                add(cid, f"Unique variable {name} prefix must be at most 48 safe characters")
        available = set(declarations)
        steps = case.get("steps")
        cleanup_steps = case.get("cleanup_steps", [])
        if not isinstance(steps, list) or not steps:
            add(cid, "READY case requires nonempty steps")
            steps = []
        if not isinstance(cleanup_steps, list):
            add(cid, "cleanup_steps must be an array")
            cleanup_steps = []
        step_ids = set()
        for step in steps + cleanup_steps:
            is_cleanup = any(step is item for item in cleanup_steps)
            if not isinstance(step, dict):
                add(cid, "Step must be an object")
                continue
            sid = step.get("id")
            if not isinstance(sid, str) or not sid or sid in step_ids:
                add(cid, "Step ids must be unique nonempty strings within a case")
            step_ids.add(sid if isinstance(sid, str) else "<invalid>")
            request = step.get("request")
            if not isinstance(request, dict):
                add(cid, f"Step {sid}: request must be an object")
                continue
            unknown = set(request) - {"method", "path", "params", "json", "headers", "raw_body", "session"}
            if unknown:
                add(cid, f"Step {sid}: unsupported request options {sorted(unknown)}")
            if request.get("method") not in METHODS:
                add(cid, f"Step {sid}: unsupported HTTP method")
            problem = _path_problem(request.get("path"))
            if problem:
                add(cid, f"Step {sid}: {problem}")
            if "raw_body" in request and ("json" in request or not isinstance(request["raw_body"], str)):
                add(cid, f"Step {sid}: raw_body must be a string, mutually exclusive with json")
            if "session" in request and type(request["session"]) is not bool:
                add(cid, f"Step {sid}: session must be a boolean")
            for field in ("headers", "params"):
                if field in request and not isinstance(request[field], dict):
                    add(cid, f"Step {sid}: {field} must be an object")
            headers = request.get("headers", {})
            if isinstance(headers, dict):
                for key, value in headers.items():
                    if key.lower() in {"host", "content-length", "transfer-encoding", "proxy-authorization"}:
                        add(cid, f"Step {sid}: reserved header {key}")
                    if not isinstance(value, str) or "\r" in key + str(value) or "\n" in key + str(value):
                        add(cid, f"Step {sid}: invalid HTTP header")
            assertions = step.get("assertions", [])
            if not isinstance(assertions, list) or (not assertions and not is_cleanup):
                add(cid, f"Step {sid}: business requests require assertions")
                assertions = []
            for assertion in assertions:
                for problem in validate_assertion(assertion):
                    add(cid, f"Step {sid}: {problem}")
                if isinstance(assertion, dict):
                    if assertion.get("rule_id") not in rule_ids:
                        add(cid, f"Step {sid}: assertion rule must be listed by the case")
                    if assertion.get("kind") == "equals_variable" and assertion.get("variable") not in available:
                        add(cid, f"Step {sid}: unknown assertion variable {assertion.get('variable')}")
            try:
                needed = _template_names(request) | _template_names(assertions)
                if needed - available:
                    add(cid, f"Step {sid}: unavailable template variables {sorted(needed - available)}")
                # Validate literal interpolation now, including literal hostile paths.
                literal_vars = {name: decl["value"] for name, decl in declarations.items() if isinstance(decl, dict) and decl.get("kind") == "literal" and "value" in decl}
                if _template_names(request.get("path")) <= literal_vars.keys():
                    problem = _path_problem(render_template(request.get("path"), literal_vars))
                    if problem:
                        add(cid, f"Step {sid}: {problem}")
                for field in ("headers", "raw_body"):
                    if field in request and _template_names(request[field]) <= literal_vars.keys():
                        rendered = render_template(request[field], literal_vars)
                        if field == "raw_body" and not isinstance(rendered, str):
                            add(cid, f"Step {sid}: rendered raw_body must be a string")
                        if field == "headers" and isinstance(rendered, dict) and any(not isinstance(value, str) or "\r" in value or "\n" in value for value in rendered.values()):
                            add(cid, f"Step {sid}: rendered headers must be strings without newlines")
            except ExecutionProblem as exc:
                add(cid, f"Step {sid}: {exc}")
            extracts = step.get("extract", [])
            if not isinstance(extracts, list):
                add(cid, f"Step {sid}: extract must be an array")
                extracts = []
            for extraction in extracts:
                if not isinstance(extraction, dict) or not isinstance(extraction.get("name"), str) or not NAME.fullmatch(extraction["name"]):
                    add(cid, f"Step {sid}: invalid extraction name")
                    continue
                source = extraction.get("from")
                if source not in {"json", "header", "cookie"}:
                    add(cid, f"Step {sid}: unsupported extraction source")
                if source == "json" and not valid_pointer(extraction.get("pointer", "")):
                    add(cid, f"Step {sid}: invalid extraction JSON pointer")
                if source in {"header", "cookie"} and (not isinstance(extraction.get("key"), str) or not extraction["key"]):
                    add(cid, f"Step {sid}: extraction requires key")
                if extraction["name"] in available:
                    add(cid, f"Step {sid}: extraction cannot overwrite variable {extraction['name']}")
                available.add(extraction["name"])
    return errors


class Redactor:
    def __init__(self):
        self.secrets: set[str] = set()
        self._lock = threading.Lock()

    def add_secret(self, value: str):
        with self._lock:
            self.secrets.add(value)

    def secret_values(self):
        with self._lock:
            return sorted(self.secrets, key=len, reverse=True)

    def remember(self, value: Any, key: str = ""):
        if isinstance(value, dict):
            for name, item in value.items():
                self.remember(item, str(name))
        elif isinstance(value, list):
            for item in value:
                self.remember(item, key)
        elif SECRET.search(key) and value is not None and str(value):
            if isinstance(value, str) and TEMPLATE.search(value):
                return
            if PASSWORD_KEY.search(key) and (type(value) in {bool, int, float} or isinstance(value, str) and value in PUBLIC_PASSWORD_FIXTURES):
                return
            self.add_secret(str(value))

    def clean(self, value: Any, key: str = "") -> Any:
        if SECRET.search(key) and value is not None:
            if isinstance(value, dict) and value.get("kind") in {"unique", "literal"}:
                return {name: "<redacted>" if name == "value" else self.clean(item) for name, item in value.items()}
            return "<redacted>"
        if isinstance(value, dict):
            return {name: self.clean(item, str(name)) for name, item in value.items()}
        if isinstance(value, list):
            return [self.clean(item, key) for item in value]
        if isinstance(value, str):
            for secret in self.secret_values():
                if len(secret) >= 4:
                    value = value.replace(secret, "<redacted>")
            # Free-form bodies and source excerpts may contain credential fields.
            value = re.sub(r'(?im)(["\']?(?:password|passwd|pwd|token|access_token|secret|SSID|authorization|api_key)["\']?\s*[:=]\s*)(["\']?)[^\s,;}\r\n"\']+\2', r'\1<redacted>', value)
            return value
        return value

    def url(self, value: str) -> str:
        parts = urlsplit(value)
        query = urlencode([(key, "<redacted>" if SECRET.search(key) else val) for key, val in parse_qsl(parts.query, keep_blank_values=True)])
        return self.clean(urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment)))

    def snapshot(self, value: Any, key: str = "") -> Any:
        """Preserve runnable templates and explicitly public negative-test fixtures."""
        if (SECRET.search(key) or key == "raw_body") and isinstance(value, str) and TEMPLATE.search(value):
            try:
                _template_names(value)
            except ExecutionProblem:
                return "<redacted>"
            return value
        if SECRET.search(key):
            if key == "session" and type(value) is bool:
                return value
            if isinstance(value, dict) and value.get("kind") in {"unique", "literal"}:
                result = {name: self.snapshot(item) for name, item in value.items()}
                if "value" in result:
                    result["value"] = self.snapshot(value["value"], key)
                return result
            if PASSWORD_KEY.search(key) and (value is None or type(value) in {bool, int, float} or isinstance(value, str) and value in PUBLIC_PASSWORD_FIXTURES):
                return value
            # Keep structural maps (operation ids and schema property names can
            # themselves contain "token" or "session"). Redact credential leaves.
            if isinstance(value, dict):
                return {name: self.snapshot(item, name) for name, item in value.items()}
            return "<redacted>" if value is not None else None
        if isinstance(value, dict):
            return {name: self.snapshot(item, str(name)) for name, item in value.items()}
        if isinstance(value, list):
            return [self.snapshot(item, key) for item in value]
        return self.clean(value)


def _session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.proxies = {}
    session.mount("http://", HTTPAdapter(max_retries=0))
    session.mount("https://", HTTPAdapter(max_retries=0))
    return session


def _body_value(body: Any) -> Any:
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    if isinstance(body, str):
        try:
            return json.loads(body, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (ValueError, TypeError):
            return body
    return body


class Runner:
    def __init__(self, config: dict, redactor: Redactor, session_factory=None, request_observer=None):
        self.config = config
        self.session_factory = session_factory or _session
        self.redactor = redactor
        self.count = 0
        self.request_observer = request_observer
        self._stop_reason = ""
        self._lock = threading.Lock()

    @property
    def stop_reason(self):
        with self._lock:
            return self._stop_reason

    @stop_reason.setter
    def stop_reason(self, reason):
        with self._lock:
            if not self._stop_reason:
                self._stop_reason = reason

    def reserve_request(self, cleanup):
        with self._lock:
            if self.count >= self.config["max_requests"]:
                self._stop_reason = self._stop_reason or "Request budget exhausted"
                raise ExecutionProblem(self._stop_reason)
            if self._stop_reason and not cleanup:
                raise ExecutionProblem(self._stop_reason)
            self.count += 1

    def step(self, step: dict, variables: dict, session: requests.Session, cleanup: bool = False) -> dict:
        record = {"id": step["id"], "status": "BROKEN", "request": {}, "response": {}, "assertions": []}
        own_session = None
        response = None
        sent = False
        started = time.monotonic()
        try:
            request = render_template(step["request"], variables)
            problem = _path_problem(request["path"])
            if problem:
                raise ExecutionProblem(problem)
            url = self.config["base_url"] + request["path"]
            if _origin(url) not in self.config["allowed_origins"]:
                raise ExecutionProblem("Rendered request origin is not allowed")
            if not request.get("session", True):
                own_session = self.session_factory()
            sender = own_session or session
            headers = dict(request.get("headers", {}))
            if any(not isinstance(v, str) or "\r" in k + v or "\n" in k + v for k, v in headers.items()):
                raise ExecutionProblem("Rendered HTTP headers must be strings without newlines")
            kwargs = {"method": request["method"], "url": url, "params": request.get("params"), "headers": headers}
            if "json" in request:
                # requests' json=None means no body. Serialize explicitly to preserve JSON null.
                kwargs["data"] = json.dumps(request["json"], ensure_ascii=False, allow_nan=False).encode("utf-8")
                if not any(key.lower() == "content-type" for key in headers):
                    headers["Content-Type"] = "application/json"
            elif "raw_body" in request:
                if not isinstance(request["raw_body"], str):
                    raise ExecutionProblem("Rendered raw_body must be a string")
                kwargs["data"] = request["raw_body"].encode("utf-8")
            prepared = sender.prepare_request(requests.Request(**kwargs))
            if _origin(prepared.url) not in self.config["allowed_origins"]:
                raise ExecutionProblem("Prepared request origin is not allowed")
            body = _body_value(prepared.body)
            self.redactor.remember(body)
            self.redactor.remember(dict(prepared.headers))
            record["request"] = {"method": prepared.method, "url": self.redactor.url(prepared.url), "headers": dict(prepared.headers), "body": body}
            try:
                self.reserve_request(cleanup)
            except ExecutionProblem:
                record["status"] = "BLOCKED"
                raise
            sent = True
            response = sender.send(prepared, stream=True, timeout=self.config["timeout"], allow_redirects=False, proxies={})
            raw_headers = dict(response.headers)
            cookies = response.cookies.get_dict()
            for value in cookies.values():
                if value:
                    self.redactor.add_secret(str(value))
            self.redactor.remember(raw_headers)
            record["response"] = {"status": response.status_code, "headers": raw_headers, "body": None, "elapsed_ms": round((time.monotonic() - started) * 1000, 2)}
            if response.status_code >= 500 and self.config["stop_on_5xx"]:
                self.stop_reason = f"Service availability failure: HTTP {response.status_code} at step {step['id']}"
            chunks = []
            size = 0
            for chunk in response.iter_content(chunk_size=8192):
                size += len(chunk)
                if size > self.config["max_response_bytes"]:
                    raise ExecutionProblem("Response exceeds max_response_bytes")
                if time.monotonic() - started > self.config["timeout"]:
                    message = "Response exceeded total request time budget"
                    if self.config["stop_on_network_error"]:
                        self.stop_reason = message
                    raise ExecutionProblem(message)
                chunks.append(chunk)
            text_body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
            body = _body_value(text_body)
            self.redactor.remember(body)
            observed = {"status": response.status_code, "headers": raw_headers, "cookies": cookies}
            try:
                observed["json"] = json.loads(text_body, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            except (TypeError, ValueError):
                pass
            record["response"].update(body=body, elapsed_ms=round((time.monotonic() - started) * 1000, 2), bytes=size)
            assertions = render_template(step.get("assertions", []), variables)
            record["assertions"] = [evaluate_assertion(item, observed, variables) for item in assertions]
            for definition, assertion_result in zip(assertions, record["assertions"]):
                if definition["kind"] == "cookie_present" or SECRET.search(definition.get("variable", "")) or SECRET.search(definition.get("pointer", "")) or SECRET.search(definition.get("name", "")):
                    if definition["kind"] != "cookie_present":
                        assertion_result["expected"] = "<redacted>"
                    assertion_result["actual"] = "<redacted>" if assertion_result["actual"] != "<missing>" else "<missing>"
            record["status"] = "PASS" if all(item["passed"] for item in record["assertions"]) else "FAIL"
            expected_server_error = any((a.get("kind") == "status" and a.get("expected") == response.status_code) or (a.get("kind") == "status_in" and response.status_code in a.get("expected", [])) for a in assertions)
            if response.status_code >= 500 and record["status"] == "PASS" and not expected_server_error:
                record["status"] = "BROKEN"
                record["error"] = "Unexpected server error; field assertions alone do not establish a successful response"
            # Extract even when an assertion fails so finally cleanup can remove resources.
            for extraction in step.get("extract", []):
                if extraction["from"] == "json":
                    value = resolve_pointer(observed.get("json", MISSING), extraction.get("pointer", ""))
                elif extraction["from"] == "header":
                    value = next((v for k, v in raw_headers.items() if k.lower() == extraction["key"].lower()), MISSING)
                else:
                    value = cookies.get(extraction["key"], MISSING)
                if value is MISSING:
                    record["status"] = "BROKEN"
                    record["error"] = f"Required extraction unavailable: {extraction['name']} ({extraction['from']})"
                    break
                variables[extraction["name"]] = value
                self.redactor.remember(value, extraction["name"])
                if extraction["from"] == "cookie" and value:
                    self.redactor.add_secret(str(value))
            return record
        except requests.RequestException as exc:
            message = f"Network availability failure: {type(exc).__name__}"
            if self.config["stop_on_network_error"]:
                self.stop_reason = message
            record["status"] = "BROKEN"
            record["error"] = f"{message}: {exc}"
            return record
        except (ExecutionProblem, ValueError, TypeError, KeyError, UnicodeError, LookupError) as exc:
            record["error"] = str(exc)
            return record
        finally:
            if sent and self.request_observer:
                observed_response = record.get("response") or {}
                self.request_observer({"completed_at": time.monotonic(), "failed": record["status"] != "PASS",
                                       "status_code": observed_response.get("status"),
                                       "elapsed_ms": observed_response.get("elapsed_ms")})
            if response is not None:
                response.close()
            if own_session is not None:
                own_session.close()


def run_bundle(bundle: dict, environment: dict, output_dir: Path, case_ids: list[str] | None = None, cleanup_callback=None, session_factory=None, request_observer=None) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    started_at = _timestamp()
    redactor = Redactor()
    redactor.remember(bundle)
    errors = validate_bundle(bundle)
    config = None
    try:
        config = _validate_environment(environment)
    except ExecutionProblem as exc:
        errors.append({"case_id": "*", "message": str(exc)})
    raw_cases = bundle.get("cases", []) if isinstance(bundle, dict) else []
    cases = [case for case in raw_cases if isinstance(case, dict)] if isinstance(raw_cases, list) else []
    if case_ids is not None:
        if not isinstance(case_ids, list) or any(not isinstance(cid, str) for cid in case_ids):
            errors.append({"case_id": "*", "message": "case_ids must be an array of case id strings"})
        else:
            unknown = set(case_ids) - {case.get("id") for case in cases if isinstance(case.get("id"), str)}
            if unknown:
                errors.append({"case_id": "*", "message": f"Unknown case ids: {sorted(unknown)}"})
            cases = [case for case in cases if case.get("id") in case_ids]
    if not cases:
        errors.append({"case_id": "*", "message": "No test cases selected"})
    if config and config["max_requests"] is None:
        config["max_requests"] = max(1, sum(len(c.get(key, [])) for c in cases if c.get("state") == "READY"
                                            for key in ("steps", "cleanup_steps") if isinstance(c.get(key, []), list)))
    runner = Runner(config, redactor, session_factory, request_observer) if config else None
    records = [None] * len(cases)
    contexts = [None] * len(cases)
    workers = config["case_workers"] if config else 1
    independent_ids = []
    overall_cleanup = {"status": "NOT_CONFIGURED", "details": "No end-of-run cleanup adapter configured"}

    def run_case(index, case):
        cid = case.get("id", f"invalid-{index}")
        if not isinstance(cid, str):
            cid = f"invalid-{index}"
        record = {"id": cid, "title": case.get("title", cid), "operation_id": case.get("operation_id"), "scenario": case.get("scenario"), "status": "BLOCKED", "reason": "", "rule_ids": case.get("rule_ids", []), "steps": []}
        records[index] = record
        from . import testing_policy
        if testing_policy.case_excluded(case):
            record.update(status='UNSUPPORTED', reason=testing_policy.REASON, execution_disposition=testing_policy.POLICY_ID)
            return
        state = case.get("state")
        if not isinstance(state, str):
            state = "INVALID"
        if state != "READY":
            record["status"] = state if state in {"QUARANTINED", "UNSUPPORTED"} else "BLOCKED"
            record["reason"] = case.get("reason") or f"Case state {state} is not executable"
            return
        relevant_errors = [e["message"] for e in errors if e["case_id"] in {"*", cid}]
        if relevant_errors:
            record["reason"] = "Preflight validation failed for this case: " + "; ".join(relevant_errors)
            return
        if runner.stop_reason:
            record["reason"] = runner.stop_reason
            return
        variables = {}
        for name, declaration in case.get("variables", {}).items():
            if declaration["kind"] == "unique":
                variables[name] = f"{declaration.get('prefix', 'mvp_')}{run_id[:12]}_{index + 1}_{name}"
            else:
                variables[name] = copy.deepcopy(declaration["value"])
            redactor.remember(variables[name], name)
        context = {"case_id": cid, "variables": variables, "status": "BROKEN"}
        contexts[index] = context
        try:
            session = runner.session_factory()
        except (ValueError, requests.RequestException) as exc:
            runner.stop_reason = "Cannot establish an approved network session: " + str(exc)
            record.update(status="BROKEN", reason=runner.stop_reason,
                          cleanup={"status": "NOT_CONFIGURED", "steps": []})
            return
        with session:
            try:
                record["status"] = "PASS"
                for step_index, step in enumerate(case["steps"]):
                    step_record = runner.step(step, variables, session)
                    record["steps"].append(step_record)
                    if step_record["status"] != "PASS":
                        record["status"] = step_record["status"]
                        record["reason"] = step_record.get("error") or f"Assertions failed in step {step['id']}"
                        for remaining in case["steps"][step_index + 1:]:
                            record["steps"].append({"id": remaining["id"], "status": "BLOCKED", "request": {}, "response": {}, "assertions": [], "error": "A prerequisite step did not pass"})
                        break
            finally:
                cleanup_records = []
                for step in case.get("cleanup_steps", []):
                    cleanup_records.append(runner.step(step, variables, session, cleanup=True))
                record["cleanup"] = {"status": "PASS" if cleanup_records and all(item["status"] == "PASS" for item in cleanup_records) else "FAIL" if cleanup_records else "NOT_CONFIGURED", "steps": cleanup_records}
                if record["cleanup"]["status"] == "FAIL" and config["stop_on_cleanup_failure"] and not runner.stop_reason:
                    runner.stop_reason = f"HTTP cleanup failed after case {cid}; environment isolation is no longer confirmed"
                context["status"] = record["status"]

    try:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="api-case") as case_pool:
            pending = set()

            def finish_pending(all_cases=False):
                nonlocal pending
                if not pending:
                    return
                done, pending = wait(pending) if all_cases else wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    future.result()

            for index, case in enumerate(cases):
                policy = case.get("execution_policy", {})
                independent = (workers > 1 and case.get("state") == "READY"
                               and not execution_policy_problem(policy) and policy["mode"] == "independent")
                if independent:
                    independent_ids.append(case["id"])
                    pending.add(case_pool.submit(run_case, index, case))
                    if len(pending) >= workers:
                        finish_pending()
                else:
                    # Unknown/shared-state cases are barriers in original order.
                    # Previous cases finish cleanup before this case can start.
                    finish_pending(all_cases=True)
                    run_case(index, case)
            finish_pending(all_cases=True)
    finally:
        if cleanup_callback is not None:
            try:
                result = cleanup_callback([context for context in contexts if context is not None])
                if not isinstance(result, dict) or result.get("status") not in {"PASS", "FAIL", "NOT_CONFIGURED"}:
                    raise ExecutionProblem("Cleanup adapter returned an invalid outcome")
                overall_cleanup = result
            except Exception as exc:
                overall_cleanup = {"status": "FAIL", "details": f"Cleanup adapter failed: {type(exc).__name__}: {exc}"}
    summary = {status: sum(record["status"] == status for record in records) for status in ("PASS", "FAIL", "BROKEN", "BLOCKED", "QUARANTINED", "UNSUPPORTED")}
    summary.update(total=len(records), complete=not errors and not any(summary[state] for state in ("BROKEN", "BLOCKED", "QUARANTINED", "UNSUPPORTED")) and overall_cleanup["status"] != "FAIL" and not any(case.get("cleanup", {}).get("status") == "FAIL" for case in records))
    result = {"schema_version": "1.0", "run_id": run_id, "started_at": started_at, "finished_at": _timestamp(), "title": bundle.get("title", "API test run") if isinstance(bundle, dict) else "API test run", "environment": {"name": environment.get("name", "unnamed") if isinstance(environment, dict) else "unnamed", "base_url": config["base_url"] if config else "<invalid>"}, "summary": summary, "cases": records, "cleanup": overall_cleanup, "generation": bundle.get("generation", {}) if isinstance(bundle, dict) else {}, "validation_errors": errors, "requests_sent": runner.count if runner else 0}
    result["execution"] = {"case_workers": workers, "independent_case_ids": independent_ids, "step_order": "serial"}
    safe_bundle = redactor.snapshot(bundle) if _jsonable(bundle) else {"validation_error": "Original input was not finite JSON", "description": redactor.clean(str(bundle))}
    result["provenance"] = _provenance(bundle, safe_bundle)
    safe_result = redactor.clean(result)
    (output_dir / "bundle.json").write_text(json.dumps(safe_bundle, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output_dir / "result.json").write_text(json.dumps(safe_result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return safe_result
