"""Compile cited rules and declarative profiles into immutable executable cases."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import yaml

from .parsers import add_source, source_from_reference
from .scheduling import execution_policy_problem

STATES = {"READY", "NEEDS_RULE", "QUARANTINED", "UNSUPPORTED"}
SCENARIOS = {"normal", "missing", "empty", "null", "wrong_type", "boundary", "duplicate", "auth_missing", "invalid_enum", "custom"}


def _sample(schema: dict):
    if "example" in schema:
        return copy.deepcopy(schema["example"])
    if "default" in schema:
        return copy.deepcopy(schema["default"])
    if schema.get("enum"):
        return copy.deepcopy(schema["enum"][0])
    if "const" in schema:
        return copy.deepcopy(schema["const"])
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((t for t in kind if t != "null"), "null")
    if kind == "object" or "properties" in schema:
        return {key: _sample(value) for key, value in schema.get("properties", {}).items()
                if key in schema.get("required", schema.get("properties", {}))}
    if kind == "array":
        return [_sample(schema.get("items", {})) for _ in range(schema.get("minItems", 1))]
    if kind == "string":
        return "x" * max(1, schema.get("minLength", 1))
    if kind in ("integer", "number"):
        return schema.get("minimum", 1)
    if kind == "boolean":
        return True
    return None


def _request(operation: dict, override: dict | None = None) -> dict:
    request = {"method": operation["method"],
               "path": re.sub(r"(?<!\$)\{([^}]+)\}", r"${\1}", operation["path"])}
    if operation.get("request_schema"):
        example = operation.get("request_example")
        request["json"] = copy.deepcopy(example if example not in ({}, None) else _sample(operation["request_schema"]))
    for parameter in operation.get("parameters", []):
        if not parameter.get("required"):
            continue
        name, location = parameter["name"], parameter["in"]
        value = parameter.get("example", _sample(parameter.get("schema", {})))
        if location == "query":
            request.setdefault("params", {})[name] = value
        elif location == "header":
            request.setdefault("headers", {})[name] = value
        # Authentication cookies and path values must be provided/extracted in profiles.
    request.update(copy.deepcopy(override or {}))
    if "raw_body" in request:
        request.pop("json", None)
    return request


def _field_location(operation: dict, field: str) -> tuple[str, str, dict]:
    if ":" in field:
        location, name = field.split(":", 1)
        mapping = {"body": "json", "query": "params", "header": "headers", "path": "path"}
        if location not in mapping:
            raise ValueError(f"Unsupported field location: {field}")
    else:
        location, name = "body", field
    if location == "body":
        return "json", name, operation.get("request_schema", {}).get("properties", {}).get(name, {})
    for parameter in operation.get("parameters", []):
        if parameter["name"] == name and parameter["in"] == location:
            return mapping[location], name, parameter.get("schema", {})
    return mapping[location], name, {}


def _variants(operation: dict, request: dict, spec: dict):
    scenario = spec["scenario"]
    if scenario in ("normal", "duplicate", "custom", "auth_missing"):
        candidate = copy.deepcopy(request)
        if scenario == "auth_missing":
            candidate["session"] = False
            auth = operation.get("auth", {})
            headers = candidate.get("headers", {})
            for header in list(headers):
                if header.lower() in {"authorization", "cookie", str(auth.get("name", "")).lower()}:
                    del headers[header]
            if auth.get("in") == "query":
                candidate.get("params", {}).pop(auth.get("name"), None)
        yield "", candidate, ""
        return
    fields = spec.get("fields")
    if fields is None:
        fields = list(operation.get("request_schema", {}).get("properties", {}))
        fields += [p["in"] + ":" + p["name"] for p in operation.get("parameters", [])
                   if p["in"] in ("query", "header", "path")]
    if not fields:
        yield "", request, "No structured fields are available for this scenario"
    for field in fields:
        container, name, schema = _field_location(operation, field)
        if not schema:
            yield field, request, f"Field {field!r} has no source schema"
            continue
        kind = schema.get("type")
        if isinstance(kind, list):
            kind = next((t for t in kind if t != "null"), None)
        values = spec.get("values")
        if isinstance(values, dict):
            values = values.get(field)
        inferred_boundaries = scenario == "boundary" and values is None
        if values is None:
            if scenario == "missing":
                values = [None]
            elif scenario == "null":
                values = [None]
            elif scenario == "empty":
                values = [[] if kind == "array" else {} if kind == "object" else ""]
            elif scenario == "wrong_type":
                values = ["wrong-type" if kind in ("integer", "number", "boolean", "object", "array") else 123]
            elif scenario == "invalid_enum":
                if not schema.get("enum"):
                    yield field, request, f"No enum constraint for {field!r}"
                    continue
                value = "__invalid_enum__"
                while value in schema["enum"]:
                    value += "_"
                values = [value]
            elif scenario == "boundary":
                values = []
                if kind == "string":
                    if "minLength" in schema:
                        values.extend(["x" * max(0, schema["minLength"] - 1), "x" * schema["minLength"]])
                    if "maxLength" in schema:
                        values.extend(["x" * schema["maxLength"], "x" * (schema["maxLength"] + 1)])
                elif kind in ("number", "integer"):
                    for bound, delta in (("minimum", -1), ("maximum", 1)):
                        if bound in schema:
                            values.extend([schema[bound], schema[bound] + delta])
                if not values:
                    yield field, request, f"No explicit supported bounds for {field!r}; expected behavior needs a rule"
                    continue
        for n, value in enumerate(values):
            candidate = copy.deepcopy(request)
            suffix = field + (f"-{n + 1}" if len(values) > 1 else "")
            if container == "path":
                if scenario == "missing":
                    yield suffix, candidate, "Missing path segments require an explicit custom request"
                    continue
                candidate["path"] = candidate["path"].replace("${" + name + "}", str(value))
            elif scenario == "missing":
                candidate.setdefault(container, {}).pop(name, None)
            else:
                candidate.setdefault(container, {})[name] = copy.deepcopy(value)
            gap = "Boundary candidates include valid and invalid inputs; assign explicit values and sourced expectations per group" if inferred_boundaries else ""
            yield suffix, candidate, gap


def generate_bundle(contract: dict, rules_path: Path, seed: int = 42) -> dict:
    rules_path = Path(rules_path).resolve()
    config = yaml.safe_load(rules_path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict) or config.get("schema_version") != "1.0":
        raise ValueError("Rules file requires schema_version: '1.0'")
    bundle = {"schema_version": "1.0", "title": config.get("title", contract["title"]),
        "contract": copy.deepcopy(contract), "rules": [], "cases": [],
        "issues": copy.deepcopy(contract.get("issues", [])), "generation": {"engine": "rules-v1", "seed": seed}}
    sources = bundle["contract"]["sources"]
    add_source(sources, rules_path, "document", rules_path.read_text(encoding="utf-8-sig"), "rules-config")
    rule_map = {}
    for raw in config.get("rules", []):
        rule = copy.deepcopy(raw)
        rule_id = rule.get("id")
        if not rule_id or rule_id in rule_map:
            raise ValueError(f"Missing or duplicate rule id: {rule_id}")
        if rule.get("state", "documented") not in ("documented", "needs_review"):
            raise ValueError(f"Invalid rule state: {rule_id}")
        rule.setdefault("state", "documented")
        rule["source_ids"] = []
        for reference in rule.pop("sources", []):
            try:
                rule["source_ids"].append(source_from_reference(sources, rules_path.parent, reference))
            except (OSError, KeyError, ValueError, TypeError) as exc:
                rule["state"] = "needs_review"
                bundle["issues"].append({"code": "INVALID_RULE_SOURCE", "severity": "error",
                    "rule_id": rule_id, "message": str(exc)})
        if not rule["source_ids"]:
            rule["state"] = "needs_review"
            bundle["issues"].append({"code": "UNSOURCED_RULE", "severity": "warning",
                "rule_id": rule_id, "message": "A rule without source evidence cannot authorize executable assertions"})
        rule_map[rule_id] = rule
        bundle["rules"].append(rule)

    operations = bundle["contract"]["operations"]

    def assertions(rule_ids):
        result = []
        for rule_id in rule_ids:
            if rule_id in rule_map:
                for assertion in rule_map[rule_id].get("assertions", []):
                    result.append({**copy.deepcopy(assertion), "rule_id": rule_id})
        return result

    def step(spec, default_operation=None, fallback_rules=()):
        op_id = spec.get("operation_id", default_operation)
        if op_id not in operations:
            raise ValueError(f"Unknown operation_id in profile step: {op_id}")
        rules = spec.get("rule_ids", list(fallback_rules))
        return {"id": spec.get("id", op_id), "title": spec.get("title", op_id),
                "request": _request(operations[op_id], spec.get("request")),
                "assertions": assertions(rules), "extract": copy.deepcopy(spec.get("extract", []))}

    case_ids = set()
    profile_ids = set()
    for profile in config.get("profiles", []):
        profile_id = profile["id"]
        if profile_id in profile_ids:
            raise ValueError(f"Duplicate profile id: {profile_id}")
        profile_ids.add(profile_id)
        op_id = profile["operation_id"]
        if op_id not in operations:
            raise ValueError(f"Unknown operation_id: {op_id}")
        operation = operations[op_id]
        for spec in profile.get("generate", [{"scenario": "normal"}]):
            scenario = spec["scenario"]
            if scenario not in SCENARIOS:
                raise ValueError(f"Unsupported scenario: {scenario}")
            override = copy.deepcopy(profile.get("request", {}))
            override.update(copy.deepcopy(spec.get("request", {})))
            base_request = _request(operation, override)
            for variant, request, gap in _variants(operation, base_request, spec):
                mapped_id = spec.get("ids", {}).get(variant)
                case_id = mapped_id or spec.get("id")
                if not mapped_id and case_id and variant:
                    case_id += "-" + re.sub(r"[^\w-]+", "-", variant)
                if not case_id:
                    identity = json.dumps([profile_id, op_id, scenario, variant, request], sort_keys=True, ensure_ascii=False)
                    case_id = "GEN-" + hashlib.sha256(identity.encode()).hexdigest()[:14]
                if case_id in case_ids:
                    raise ValueError(f"Duplicate generated case id: {case_id}")
                case_ids.add(case_id)
                rule_ids = list(spec.get("rule_ids", profile.get("rule_ids", [])))
                setup_specs = profile.get("setup_steps", []) + spec.get("setup_steps", [])
                after_specs = profile.get("after_steps", []) + spec.get("after_steps", [])
                cleanup_specs = profile.get("cleanup_steps", []) + spec.get("cleanup_steps", [])
                setup = [step(s) for s in setup_specs]
                if scenario == "duplicate":
                    setup.append(step({"id": "first-submit", "request": base_request,
                                       "rule_ids": profile.get("rule_ids", [])}, op_id))
                primary = {"id": "test", "title": spec.get("title", scenario), "request": request,
                           "assertions": assertions(rule_ids), "extract": copy.deepcopy(spec.get("extract", []))}
                steps = setup + [primary] + [step(s) for s in after_specs]
                cleanup = [step(s) for s in cleanup_specs]
                all_rules = list(dict.fromkeys(rule_ids + [r for s in setup_specs + after_specs + cleanup_specs for r in s.get("rule_ids", [])]
                                               + (profile.get("rule_ids", []) if scenario == "duplicate" else [])))
                state = spec.get("state", profile.get("state", "READY"))
                reason = spec.get("reason", profile.get("reason", ""))
                if state not in STATES:
                    raise ValueError(f"Invalid case state: {state}")
                unknown_rules = [r for r in all_rules if r not in rule_map or rule_map[r]["state"] != "documented"]
                unsupported_ops = [op_id] + [s.get("operation_id") for s in setup_specs + after_specs + cleanup_specs]
                unsupported = [i for i in contract.get("issues", []) if i.get("severity") == "error"
                    and (not i.get("operation_id") or i.get("operation_id") in unsupported_ops)]
                if state == "READY":
                    if unsupported:
                        state, reason = "UNSUPPORTED", "; ".join(i["message"] for i in unsupported)
                    elif gap or unknown_rules or not primary["assertions"] or any(not s["assertions"] for s in steps):
                        state = "NEEDS_RULE"
                        reason = gap or ("Rules require review: " + ", ".join(unknown_rules) if unknown_rules else "Every request needs sourced assertions")
                variables = copy.deepcopy(profile.get("variables", {}))
                variables.update(copy.deepcopy(spec.get("variables", {})))
                execution_policy = copy.deepcopy(spec.get("execution_policy", profile.get("execution_policy", {"mode": "serial"})))
                problem = execution_policy_problem(execution_policy)
                if problem:
                    raise ValueError(problem)
                bundle["cases"].append({"id": case_id, "title": spec.get("titles", {}).get(variant, spec.get("title", profile.get("title", profile_id)) + (f" [{variant}]" if variant else "")),
                    "operation_id": op_id, "scenario": scenario, "state": state, "reason": reason,
                    "rule_ids": all_rules, "variables": variables, "steps": steps, "cleanup_steps": cleanup,
                    "execution_policy": execution_policy,
                    "source_ids": list(dict.fromkeys(operation.get("source_ids", []) + [sid for rid in all_rules if rid in rule_map for sid in rule_map[rid]["source_ids"]]))})
    return bundle
