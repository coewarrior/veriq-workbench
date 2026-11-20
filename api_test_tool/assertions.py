"""Explicit, strict assertions over HTTP responses. No learned expectations."""

from __future__ import annotations

import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, validators
from jsonschema.exceptions import SchemaError


MISSING = object()
KINDS = {
    "status", "json_equal", "json_schema", "response_schema", "json_exists", "cookie_present",
    "header_equal", "equals_variable", "status_in", "status_not_in",
}


def valid_pointer(pointer: Any) -> bool:
    return isinstance(pointer, str) and (pointer == "" or pointer.startswith("/")) and not re.search(r"~(?![01])", pointer)


def resolve_pointer(value: Any, pointer: str) -> Any:
    """RFC 6901 lookup; missing remains distinct from an explicit JSON null."""
    if not valid_pointer(pointer):
        return MISSING
    if pointer == "":
        return value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            if token not in value:
                return MISSING
            value = value[token]
        elif isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                return MISSING
            index = int(token)
            if index >= len(value):
                return MISSING
            value = value[index]
        else:
            return MISSING
    return value


def strict_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(strict_equal(actual[k], expected[k]) for k in actual)
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(strict_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def schema_problem(schema: Any) -> str | None:
    if not isinstance(schema, (dict, bool)):
        return "JSON Schema must be an object or boolean"
    def refs(item: Any) -> bool:
        if isinstance(item, dict):
            return any(k in {"$ref", "$dynamicRef", "$recursiveRef"} or refs(v) for k, v in item.items())
        return isinstance(item, list) and any(refs(v) for v in item)
    if refs(schema):
        return "JSON Schema references must be resolved before execution"
    try:
        if isinstance(schema, dict) and "$schema" in schema and schema["$schema"].rstrip("#") not in {
            "http://json-schema.org/draft-04/schema", "http://json-schema.org/draft-06/schema",
            "http://json-schema.org/draft-07/schema", "https://json-schema.org/draft/2019-09/schema",
            "https://json-schema.org/draft/2020-12/schema",
        }:
            return "Unsupported JSON Schema dialect"
        validator = validators.validator_for(schema, default=Draft202012Validator)
        validator.check_schema(schema)
        annotation_keys = {"$schema", "$id", "id", "$anchor", "$dynamicAnchor", "$comment", "title", "description", "default", "examples", "deprecated", "readOnly", "writeOnly", "$defs", "definitions", "contentEncoding", "contentMediaType", "contentSchema"}
        known = set(validator.VALIDATORS) | annotation_keys
        def check_keywords(item: Any) -> str | None:
            if isinstance(item, bool):
                return None
            for key in item:
                if key not in known and not key.startswith("x-"):
                    return f"Unsupported JSON Schema keyword: {key}"
            if "format" in item and item["format"] not in FormatChecker.checkers:
                return f"Unsupported JSON Schema format: {item['format']}"
            children = []
            for key in {"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"}:
                children.extend(item.get(key, {}).values())
            for key in {"allOf", "anyOf", "oneOf", "prefixItems"}:
                children.extend(item.get(key, []))
            for key in {"items", "additionalItems", "additionalProperties", "unevaluatedProperties", "unevaluatedItems", "contains", "not", "if", "then", "else", "propertyNames"}:
                if key in item:
                    children.extend(item[key] if isinstance(item[key], list) else [item[key]])
            for child in children:
                issue = check_keywords(child)
                if issue:
                    return issue
            return None
        issue = check_keywords(schema)
        if issue:
            return issue
    except (SchemaError, TypeError, ValueError) as exc:
        return f"Invalid JSON Schema: {str(exc).splitlines()[0]}"
    return None


def validate_assertion(assertion: Any) -> list[str]:
    if not isinstance(assertion, dict):
        return ["Assertion must be an object"]
    kind = assertion.get("kind")
    if kind not in KINDS:
        return [f"Unsupported assertion kind: {kind!r}"]
    errors = []
    if not isinstance(assertion.get("rule_id"), str) or not assertion["rule_id"]:
        errors.append("Assertion requires a rule_id")
    if kind == "status" and (type(assertion.get("expected")) is not int or not 100 <= assertion["expected"] <= 599):
        errors.append("Status expectation must be an integer HTTP status")
    if kind in {"status_in", "status_not_in"}:
        values = assertion.get("expected")
        if not isinstance(values, list) or not values or any(type(v) is not int or not 100 <= v <= 599 for v in values):
            errors.append("Status set must be a nonempty array of integer HTTP statuses")
    if kind in {"json_equal", "json_schema", "response_schema", "header_equal"} and "expected" not in assertion:
        errors.append(f"{kind} requires expected")
    if kind in {"json_equal", "json_exists", "equals_variable"} and not valid_pointer(assertion.get("pointer", "")):
        errors.append("Invalid JSON pointer")
    if kind in {"cookie_present", "header_equal"} and (not isinstance(assertion.get("name"), str) or not assertion["name"]):
        errors.append(f"{kind} requires name")
    if kind == "equals_variable" and not isinstance(assertion.get("variable"), str):
        errors.append("equals_variable requires variable")
    if kind in {"json_schema", "response_schema"}:
        problem = schema_problem(assertion.get("expected"))
        if problem:
            errors.append(problem)
    return errors


def evaluate_assertion(assertion: dict, response: dict, variables: dict) -> dict:
    kind = assertion["kind"]
    expected = assertion.get("expected")
    actual: Any = MISSING
    passed = False
    message = ""
    data = response.get("json", MISSING)
    if kind == "status":
        actual = response["status"]
        passed = strict_equal(actual, expected)
    elif kind in {"status_in", "status_not_in"}:
        actual = response["status"]
        contained = any(strict_equal(actual, value) for value in expected)
        passed = contained if kind == "status_in" else not contained
    elif kind in {"json_equal", "json_exists", "equals_variable"}:
        actual = resolve_pointer(data, assertion.get("pointer", "")) if data is not MISSING else MISSING
        if kind == "json_exists":
            expected = "present (null is allowed)"
            passed = actual is not MISSING
        else:
            if kind == "equals_variable":
                expected = variables.get(assertion["variable"], MISSING)
            passed = actual is not MISSING and expected is not MISSING and strict_equal(actual, expected)
    elif kind in {"json_schema", "response_schema"}:
        actual = data if kind == "json_schema" else {key: response[key] for key in ("status", "json") if key in response}
        if actual is not MISSING:
            validator = validators.validator_for(expected, default=Draft202012Validator)
            failures = list(validator(expected, format_checker=FormatChecker()).iter_errors(actual))
            passed = not failures
            if failures:
                message = "; ".join(f"/{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in failures[:10])
    elif kind == "header_equal":
        actual = next((value for key, value in response["headers"].items() if key.lower() == assertion["name"].lower()), MISSING)
        passed = actual is not MISSING and strict_equal(actual, expected)
    elif kind == "cookie_present":
        expected = "present"
        # The check concerns this response's Set-Cookie, not an earlier session cookie.
        actual = response.get("cookies", {}).get(assertion["name"], MISSING)
        passed = actual is not MISSING and actual != ""
    if not message:
        message = "Expectation satisfied" if passed else ("Required value is absent or response is not JSON" if actual is MISSING else "Actual value does not match the documented expectation")
    return {
        "kind": kind, "rule_id": assertion["rule_id"], "passed": passed,
        "expected": "<missing>" if expected is MISSING else expected,
        "actual": "<missing>" if actual is MISSING else actual, "message": message,
    }
