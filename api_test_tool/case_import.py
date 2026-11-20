"""User-authored cases: explicit expectations, append-only imports and traceable sources."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re

from .web_generation import compile_model_bundle, CASE_ID

WORKFLOWS = {"own", "ai", "import_ai", "ai_import"}
CASE_FIELDS = {"id", "title", "operation_id", "scenario", "variables", "steps", "cleanup_steps",
               "cleanup_policy", "execution_policy", "design", "notes"}
STEP_FIELDS = {"id", "title", "operation_id", "request", "assertions", "extract"}


def bundle_revision(bundle):
    return hashlib.sha256(json.dumps(bundle, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def candidates_from_bundle(bundle):
    rules = {r["id"]: r for r in bundle.get("rules", [])}
    result = []
    for original in bundle.get("cases", []):
        case = {k: copy.deepcopy(v) for k, v in original.items() if k in CASE_FIELDS}
        for group in ("steps", "cleanup_steps"):
            for step in case.get(group, []):
                if 'operation_id' not in step:
                    step['operation_id'] = _step_operation(bundle.get('contract', {}), step, case['operation_id'])
                for assertion in step.get("assertions", []):
                    rule = rules.get(assertion.pop("rule_id", None), {})
                    assertion["evidence"] = copy.deepcopy(rule.get("evidence") or [
                        {"source_id": sid, "quote": bundle["contract"]["sources"][sid]["excerpt"]}
                        for sid in rule.get("source_ids", []) if bundle["contract"]["sources"].get(sid, {}).get("excerpt")][:8])
        result.append(case)
    return {"schema_version": "1.0", "cases": result}


def _operation(contract, row):
    oid = row.get("operation_id")
    if isinstance(oid, str) and oid in contract["operations"]:
        return oid
    method, path = str(row.get("method", "GET")).upper(), row.get("path", "")
    for key, op in contract["operations"].items():
        if op["method"] == method and op["path"] == path:
            return key
    raise ValueError(f"用例未匹配文档接口：{oid or method + ' ' + str(path)}；请填写 operation_id 或文档中的 method/path")


def _step_operation(contract, step, fallback):
    request = step.get('request') or {}
    if not isinstance(request, dict):
        raise ValueError('request 必须是对象')
    if not request.get('method') or not request.get('path'):
        return fallback
    for oid, op in contract.get('operations', {}).items():
        pattern = '^' + re.sub(r"\\\{[^{}]+\\\}", "[^/]+", re.escape(op['path'])) + '$'
        if op['method'] == request['method'] and re.fullmatch(pattern, str(request['path'])):
            return oid
    return fallback


def _json_cell(value, name, default=None):
    if value in (None, ""):
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        raise ValueError(f"{name} 必须是 JSON，例如对象使用双引号") from None


def import_candidates(contract, filename, content):
    if not isinstance(content, str) or not content.strip() or len(content.encode()) > 4 * 1024 * 1024:
        raise ValueError("用例文件须为非空 UTF-8 文本，首版单文件最多 4 MB")
    if not isinstance(filename, str) or len(filename) > 150:
        raise ValueError("文件名无效")
    if filename.lower().endswith('.csv'):
        aliases = {"编号": "id", "用例ID": "id", "用例名称": "title", "请求方法": "method", "接口路径": "path",
                   "请求体": "json", "查询参数": "params", "请求头": "headers", "预期状态码": "expected_status", "断言": "assertions"}
        csv.field_size_limit(4 * 1024 * 1024)
        try:
            reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')), strict=True)
            fields = [aliases.get(k.strip(), k.strip()) for k in reader.fieldnames or []]
            if len(fields) != len(set(fields)):
                raise ValueError('CSV 表头不能重复')
            rows = [{aliases.get(k.strip(), k.strip()) if isinstance(k, str) else k: v
                     for k, v in row.items()} for row in reader]
        except csv.Error:
            raise ValueError('CSV 格式无效，请检查引号和列数，或改用 JSON') from None
    elif filename.lower().endswith('.json'):
        try:
            data = json.loads(content)
        except (ValueError, RecursionError):
            raise ValueError("用例 JSON 格式无效") from None
        rows = data if isinstance(data, list) else data.get('cases') if isinstance(data, dict) else None
    else:
        raise ValueError("首版支持 CSV、JSON；多步骤链路使用 JSON，CSV 模板可用 Excel 编辑后另存为 CSV UTF-8")
    if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("文件需要包含非空用例数组或 CSV 数据行")
    contract = copy.deepcopy(contract)
    digest = hashlib.sha256(content.encode()).hexdigest()
    cases, ids = [], set()
    for index, row in enumerate(rows, 1):
        cid = row.get('id') or f'USER-{digest[:8]}-{index:03d}'
        if not isinstance(cid, str) or not CASE_ID.fullmatch(cid) or cid in ids:
            raise ValueError(f"第 {index} 行编号无效或重复，请使用字母、数字、连字符或下划线组成的唯一 ID")
        ids.add(cid)
        if any(not isinstance(k, str) for k in row):
            raise ValueError(f'第 {index} 行 CSV 列数与表头不匹配')
        case = {k: copy.deepcopy(v) for k, v in row.items() if k in CASE_FIELDS}
        case.update(id=cid, title=row.get('title') or cid, operation_id=_operation(contract, row))
        if 'steps' not in case:
            request = {}
            for key in ('json', 'headers', 'params'):
                value = _json_cell(row.get(key), key)
                if value is not None:
                    request[key] = value
            if row.get('raw_body') is not None:
                request['raw_body'] = row['raw_body']
            assertions = _json_cell(row.get('assertions'), 'assertions', [])
            if not isinstance(assertions, list):
                raise ValueError('assertions 必须是 JSON 数组')
            if row.get('expected_status') not in (None, ''):
                try:
                    status = int(row['expected_status'])
                except (TypeError, ValueError):
                    raise ValueError('expected_status 必须为整数') from None
                assertions = [{'kind': 'status', 'expected': status}, *assertions]
            case['steps'] = [{'id': 'request', 'operation_id': case['operation_id'], 'request': request, 'assertions': assertions}]
        for group in ('steps', 'cleanup_steps'):
            if not isinstance(case.get(group, []), list):
                raise ValueError(f'{cid} 的 {group} 必须为数组')
            for n, step in enumerate(case.get(group, []), 1):
                if not isinstance(step, dict):
                    raise ValueError(f'{cid} 步骤必须是对象')
                case[group][n - 1] = step = {k: v for k, v in step.items() if k in STEP_FIELDS}
                step.setdefault('id', f'{group}-{n}')
                step.setdefault('operation_id', _step_operation(contract, step, case['operation_id']))
                if not isinstance(step.get('assertions', []), list):
                    raise ValueError(f'{cid} assertions 必须为数组')
                for ai, assertion in enumerate(step.get('assertions', []), 1):
                    if not isinstance(assertion, dict):
                        raise ValueError(f'{cid} 断言必须是对象')
                    assertion.pop('rule_id', None)
                    assertion.pop('evidence', None)
                    quote = json.dumps(assertion, ensure_ascii=False, sort_keys=True)
                    sid = f'USER-SRC-{digest[:16]}-{index}-{group}-{n}-{ai}'
                    contract['sources'][sid] = {'path': 'inputs/' + filename.split('/')[-1].split('\\')[-1],
                        'sha256': digest, 'location': f'{cid}/{group}/{n}/{ai}', 'excerpt': quote, 'kind': 'user_test_expectation'}
                    assertion['evidence'] = [{'source_id': sid, 'quote': quote}]
        cases.append(case)
    # Same structural, path and assertion checks as generated cases. Never trust imported READY/review flags.
    bundle = compile_model_bundle(contract, json.dumps({'schema_version': '1.0', 'cases': cases}, ensure_ascii=False))
    for case in bundle['cases']:
        case['web']['source'] = 'user'
    for rule in bundle['rules']:
        rule.update(origin='user-import', description=rule['description'].replace('模型候选：', '用户用例预期：'))
    return contract, bundle


def merge_bundles(existing, incoming, *, replace_id=None):
    result = copy.deepcopy(incoming)
    old = copy.deepcopy(existing or {})
    collisions = {c['id'] for c in old.get('cases', [])} & {c['id'] for c in incoming['cases']}
    if collisions - ({replace_id} if replace_id else set()):
        raise ValueError('用例 ID 已存在，不会覆盖原用例：' + ', '.join(sorted(collisions)[:5]))
    result['cases'] = [c for c in old.get('cases', []) if c['id'] != replace_id] + result['cases']
    retained_rule_ids = {r for c in old.get('cases', []) if c['id'] != replace_id for r in c.get('rule_ids', [])}
    result['rules'] = [r for r in old.get('rules', []) if r['id'] in retained_rule_ids] + result['rules']
    result['contract']['sources'] = {**old.get('contract', {}).get('sources', {}), **result['contract']['sources']}
    result.setdefault('web', {}).update(old.get('web', {}))
    result['generation']['engine'] = 'combined-cases-v1'
    return result


def append_generated(existing, incoming, prefix, source='ai'):
    """Namespace new IDs, preserve user cases and reviews; drop only identical executable scenarios."""
    def signature(case, context):
        value = candidates_from_bundle({'cases': [case], 'rules': [], 'contract': context['contract']})['cases'][0]
        for key in ('id', 'title', 'notes', 'design'):
            value.pop(key, None)
        for group in ('steps', 'cleanup_steps'):
            for step in value.get(group, []):
                step.pop('id', None); step.pop('title', None)
                for a in step.get('assertions', []):
                    a.pop('evidence', None)
        return json.dumps(value, sort_keys=True)
    previous = {signature(c, existing) for c in existing.get('cases', []) if c.get('steps')}
    incoming = copy.deepcopy(incoming)
    incoming['cases'] = [c for c in incoming['cases'] if not c.get('steps') or signature(c, incoming) not in previous]
    for case in incoming['cases']:
        old_id = case['id']
        new_id = prefix + old_id
        case['id'] = new_id if len(new_id) <= 80 else new_id[:67] + '-' + hashlib.sha256(new_id.encode()).hexdigest()[:12]
        case['rule_ids'] = [prefix + r for r in case.get('rule_ids', [])]
        case.setdefault('web', {})['source'] = source
        for group in ('steps', 'cleanup_steps'):
            for step in case.get(group, []):
                for a in step.get('assertions', []):
                    if 'rule_id' in a:a['rule_id'] = prefix + a['rule_id']
    for rule in incoming['rules']:rule['id'] = prefix + rule['id']
    return merge_bundles(existing, incoming)
