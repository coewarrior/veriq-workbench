"""Readable, self-contained test-case design reports from a frozen bundle."""
from __future__ import annotations

import html
import json
import re
from collections import Counter

from .report_theme import REPORT_THEME_CSS


STATUS_LABELS = {
    "READY": "可执行",
    "NEEDS_RULE": "执行条件待完善或核对",
    "QUARANTINED": "已隔离",
    "UNSUPPORTED": "暂不支持",
    "BLOCKED": "未执行",
}

SCENARIO_LABELS = {
    "normal": "正向",
    "missing": "逆向 · 缺少字段",
    "empty": "边界 · 空值",
    "null": "边界 · null",
    "wrong_type": "逆向 · 类型错误",
    "boundary": "边界",
    "duplicate": "逆向 · 重复提交",
    "auth_missing": "安全 · 缺少认证",
    "invalid_enum": "逆向 · 非法枚举",
    "custom": "扩展场景",
}

ASSERTION_LABELS = {
    "status": "HTTP 状态码",
    "status_in": "HTTP 状态码属于集合", "status_not_in": "HTTP 状态码不属于集合",
    "json_equal": "响应字段等于期望值",
    "json_schema": "响应结构符合 Schema", "response_schema": "HTTP 状态与响应分支",
    "json_exists": "响应字段存在",
    "cookie_present": "响应包含 Cookie",
    "header_equal": "响应头等于期望值",
    "equals_variable": "响应字段等于前序保存值",
}


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _json(value) -> str:
    return _e(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _display_value(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _operation_label(operation_id: str, operations: dict) -> str:
    operation = operations.get(operation_id, {})
    method, path = operation.get("method", ""), operation.get("path", "")
    return " ".join(part for part in (str(method).upper(), str(path)) if part) or operation_id


def _step_operation_id(step: dict, operations: dict) -> str:
    if step.get("operation_id") in operations:
        return str(step["operation_id"])
    request = step.get("request", {}) or {}
    method = str(request.get("method") or "").upper()
    path = re.sub(r"\$?\{[^{}]+\}", "{}", str(request.get("path") or ""))
    for operation_id, operation in operations.items():
        operation_path = re.sub(r"\$?\{[^{}]+\}", "{}", str(operation.get("path") or ""))
        if str(operation.get("method") or "").upper() == method and operation_path == path:
            return str(operation_id)
    return ""


def _case_operation_ids(case: dict, operations: dict) -> list[str]:
    return list(dict.fromkeys(
        str(operation_id) for operation_id in [case.get("operation_id")] + [
            _step_operation_id(step, operations)
            for step in (case.get("steps", []) or []) + (case.get("cleanup_steps", []) or [])
        ] if operation_id
    ))


def _request_text(step: dict, operations: dict) -> str:
    request = step.get("request", {}) or {}
    operation_id = step.get("operation_id", "")
    operation = operations.get(operation_id, {})
    method = str(request.get("method") or operation.get("method") or "").upper()
    path = request.get("path") or operation.get("path") or ""
    lines = [f"{method} {path}".strip()]
    visible = {key: request[key] for key in ("params", "headers", "json", "raw_body", "session") if key in request}
    if visible:
        lines.append(json.dumps(visible, ensure_ascii=False, indent=2, sort_keys=True))
    extracts = step.get("extract", []) or []
    if extracts:
        lines.append("保存变量：" + "、".join(str(item.get("name", "")) for item in extracts if item.get("name")))
    return "\n".join(line for line in lines if line)


def _assertion_text(assertion: dict) -> str:
    kind = assertion.get("kind", "")
    label = ASSERTION_LABELS.get(kind, kind or "断言")
    details = []
    for key in ("pointer", "header", "name", "expected", "variable"):
        if key in assertion:
            key_label = {"pointer": "位置", "header": "响应头", "name": "名称", "expected": "期望", "variable": "变量"}[key]
            details.append(f"{key_label}={_display_value(assertion[key])}")
    return label + ("（" + "；".join(details) + "）" if details else "")


def _preconditions(case: dict) -> str:
    lines = []
    variables = case.get("variables", {}) or {}
    for name, definition in variables.items():
        if definition.get("kind") == "unique":
            lines.append(f"准备本用例唯一变量 {name}（前缀 {definition.get('prefix', '')}）")
        else:
            lines.append(f"准备变量 {name}={_display_value(definition.get('value'))}")
    policy = case.get("execution_policy", {}) or {}
    if policy.get("reason"):
        lines.append(str(policy["reason"]))
    if not lines:
        lines.append("使用独立测试会话；目标测试服务可用")
    return "\n".join(lines)


def _steps(case: dict, operations: dict) -> str:
    rows = []
    for index, step in enumerate(case.get("steps", []) or [], 1):
        title = step.get("title") or step.get("id") or f"步骤 {index}"
        rows.append(f"{index}. {title}\n{_request_text(step, operations)}")
    return "\n\n".join(rows) or "尚未配置请求步骤"


def _assertions(case: dict) -> str:
    rows = []
    for index, step in enumerate(case.get("steps", []) or [], 1):
        assertions = step.get("assertions", []) or []
        title = step.get("title") or step.get("id") or f"步骤 {index}"
        if assertions:
            rows.append(f"{title}：" + "；".join(_assertion_text(item) for item in assertions))
        else:
            rows.append(f"{title}：未配置断言")
    return "\n".join(rows) or "尚未配置断言"


def _case_rules(case: dict, rules: dict) -> list[dict]:
    ids = list(case.get("rule_ids", []) or [])
    for step in (case.get("steps", []) or []) + (case.get("cleanup_steps", []) or []):
        ids.extend(a["rule_id"] for a in step.get("assertions", []) if a.get("rule_id"))
    return [rules[rid] for rid in dict.fromkeys(ids) if rid in rules]


def _source_groups(case: dict, rules: dict, sources: dict) -> list[dict]:
    """Combine adjacent/overlapping Markdown references from the same document revision."""
    ids = dict.fromkeys(sid for rule in _case_rules(case, rules) for sid in rule.get("source_ids", []))
    groups = {}
    for sid in ids:
        source = sources.get(sid, {})
        excerpt = str(source.get("excerpt") or "").strip()
        if not excerpt:
            continue
        key = (str(source.get("path") or "接口文档"), source.get("sha256", ""))
        group = groups.setdefault(key, {"path": key[0], "lines": {}, "other": []})
        location = str(source.get("location") or "")
        match = re.fullmatch(r"lines? (\d+)-(\d+)", location)
        lines = excerpt.splitlines()
        if match and len(lines) == int(match[2]) - int(match[1]) + 1:
            for number, line in enumerate(lines, int(match[1])):
                group["lines"].setdefault(number, line)
        elif (location, excerpt) not in group["other"]:
            group["other"].append((location, excerpt))
    return list(groups.values())


def _readable_excerpt(text: str) -> str:
    rows = []
    for line in text.splitlines():
        if re.fullmatch(r"[\s|:\-]+", line):
            continue
        if line.strip().startswith("|"):
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
            line = "：".join(cells[:2]) if len(cells) == 2 else " · ".join(cells)
        rows.append(line)
    text = "\n".join(rows).strip()
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    return text.replace("**", "").replace("`", "")


def _source_content(group: dict) -> tuple[str, str]:
    ranges, pieces = [], []
    start = end = None
    for number, line in sorted(group["lines"].items()):
        if end is not None and number != end + 1:
            ranges.append((start, end))
            pieces.append("…")
            start = None
        if start is None:
            start = number
        end = number
        pieces.append(line)
    if start is not None:
        ranges.append((start, end))
    locations = [f"第 {start} 行" if start == end else f"第 {start}–{end} 行" for start, end in ranges]
    for location, excerpt in group["other"]:
        locations.append(location)
        pieces.append(excerpt)
    return "；".join(locations), "\n".join(pieces)


def _rule_evidence(case: dict, rules: dict, sources: dict) -> str:
    descriptions = list(dict.fromkeys(str(rule.get("description") or "") for rule in _case_rules(case, rules)))
    descriptions = [row for row in descriptions if row and row != "OpenAPI 显式成功响应与 JSON Schema"]
    if descriptions:
        return "\n".join(descriptions)
    if _source_groups(case, rules, sources):
        return "参考接口文档中的请求与响应说明。"
    return "尚未关联具体文档说明"


def _source_details(case: dict, rules: dict, sources: dict) -> str:
    blocks = []
    for group in _source_groups(case, rules, sources):
        location, excerpt = _source_content(group)
        filename = group["path"].replace("\\", "/").rsplit("/", 1)[-1]
        label = filename + (" · " + location if location else "")
        blocks.append('<p>' + _e(label) + '</p><pre>' + _e(_readable_excerpt(excerpt)) + '</pre>')
    if not blocks:
        return ""
    return '<details class="source"><summary>查看来源</summary>' + ''.join(blocks) + '</details>'


def _execution_reasons(case: dict) -> str:
    values = [case.get("reason") or "", *(case.get("web", {}).get("blockers", []) or [])]
    rows = []
    for value in values:
        for part in re.split(r"[；;\n]+", str(value)):
            part = part.strip().rstrip("。")
            if not part:
                continue
            part = re.sub(r"Step ([^:]+): business requests require assertions", r"步骤 \1 尚未设置预期结果", part)
            part = re.sub(r"步骤 (\S+) 缺少有依据的预期", r"步骤 \1 尚未设置预期结果", part)
            if part in {"可验证业务字段、响应结构或 HTTP 状态", "不能猜测预期"}:
                continue
            part = part.replace("文档未明确本场景的成功 HTTP 状态码", "文档未说明成功时的 HTTP 状态码")
            part = part.replace("包含写操作，但尚未配置可验证的数据清理步骤", "尚未设置写入数据后的清理和验证步骤")
            if part not in rows:
                rows.append(part)
    return "\n".join("• " + row for row in rows)


def _cleanup(case: dict, operations: dict) -> str:
    steps = case.get("cleanup_steps", []) or []
    if steps:
        rows = []
        for index, step in enumerate(steps, 1):
            assertions = step.get("assertions", []) or []
            assertion_text = "；".join(_assertion_text(item) for item in assertions) or "未配置清理断言"
            rows.append(f"{index}. {step.get('title') or step.get('id') or '清理步骤'}\n{_request_text(step, operations)}\n验证：{assertion_text}")
        return "\n\n".join(rows)
    policy = case.get("cleanup_policy", {}) or {}
    if policy.get("strategy") == "none":
        return "无持久数据清理：" + str(policy.get("reason") or "本用例不产生持久数据")
    if not case.get("steps"):
        return "未发送请求，无运行后清理"
    return "未配置清理步骤；执行前需确认本用例不会留下测试数据"


def _case_card(case: dict, operations: dict, rules: dict, sources: dict) -> str:
    case_id = str(case.get("id", ""))
    title = str(case.get("title") or case_id)
    operation_id = str(case.get("operation_id", ""))
    operation = operations.get(operation_id, {})
    api = str(operation.get("path") or operation_id)
    state = str(case.get("state") or "BLOCKED")
    scenario = SCENARIO_LABELS.get(case.get("scenario", ""), str(case.get("scenario") or "未分类"))
    design = case.get("design", {})
    design_labels = {"category":"类别", "preconditions":"前置条件", "inputs":"输入", "procedure":"测试步骤",
                     "expected":"预期结果", "basis":"文档中的相关说明", "postconditions":"后置验证", "cleanup":"清理安排", "execution_gap":"未执行原因"}
    design_html = ''.join(f'<dt>{_e(design_labels[key])}</dt><dd><pre>{_e(value)}</pre></dd>' for key, value in design.items() if key in design_labels and value)
    status = STATUS_LABELS.get(state, state)
    execution = f"未执行 · 设计状态：{status}"
    reasons = _execution_reasons(case)
    if reasons:
        execution += "\n" + reasons
    operation_ids = _case_operation_ids(case, operations)
    search = " ".join((case_id, title, operation_id, api, scenario, state, status, *(_operation_label(item, operations) for item in operation_ids))).lower()
    return f'''<article class="case" data-apis="{_e(','.join(operation_ids))}" data-state="{_e(state)}" data-scenario="{_e(case.get('scenario', ''))}" data-search="{_e(search)}">
  <div class="case-title"><div><code>{_e(case_id)}</code><h2>{_e(title)}</h2></div><span class="state { _e(state) }">{_e(status)}</span></div>
  <p class="tags"><span class="method">{_e(str(operation.get('method', '')).upper())}</span><span>{_e(api)}</span><span>{_e(scenario)}</span><span>未执行</span></p>
  {"<h3>完整测试设计</h3><dl>" + design_html + "</dl><details class=source><summary>查看实际请求和检查项</summary>" if design_html else ""}
  <dl>
    <dt>前置条件</dt><dd>{_e(_preconditions(case))}</dd>
    <dt>输入与请求步骤</dt><dd><pre>{_e(_steps(case, operations))}</pre></dd>
    <dt>关键断言</dt><dd>{_e(_assertions(case))}</dd>
    <dt>文档中的相关说明</dt><dd>{_e(_rule_evidence(case, rules, sources))}{_source_details(case, rules, sources)}</dd>
    <dt>后置验证与清理</dt><dd><pre>{_e(_cleanup(case, operations))}</pre></dd>
    <dt>执行状态</dt><dd>{_e(execution)}</dd>
  </dl>
  {"</details>" if design_html else ""}
</article>'''


def render_case_report(project: dict, bundle: dict) -> str:
    """Render the current frozen design without claiming that requests ran."""
    contract = bundle.get("contract", {}) or {}
    operations = contract.get("operations", {}) or {}
    rules = {str(rule.get("id")): rule for rule in bundle.get("rules", []) or [] if rule.get("id")}
    sources = contract.get("sources", {}) or {}
    cases = bundle.get("cases", []) or []
    states = Counter(str(case.get("state") or "BLOCKED") for case in cases)
    used_operations = list(dict.fromkeys(operation_id for case in cases for operation_id in _case_operation_ids(case, operations)))

    operation_options = []
    operation_rows = []
    for operation_id in used_operations:
        label = _operation_label(operation_id, operations)
        matching = [case for case in cases if operation_id in _case_operation_ids(case, operations)]
        counts = Counter(str(case.get("state") or "BLOCKED") for case in matching)
        operation_options.append(f'<option value="{_e(operation_id)}">{_e(label)} · {len(matching)} 条</option>')
        operation_rows.append(
            f'<tr><td><code>{_e(label)}</code></td><td>{len(matching)}</td><td>{counts["READY"]}</td>'
            f'<td>{counts["NEEDS_RULE"]}</td><td>{counts["QUARANTINED"] + counts["UNSUPPORTED"] + counts["BLOCKED"]}</td></tr>'
        )
    state_options = "".join(
        f'<option value="{_e(state)}">{_e(STATUS_LABELS.get(state, state))} · {count} 条</option>'
        for state, count in states.items()
    )
    scenario_counts = Counter(str(case.get("scenario") or "") for case in cases)
    scenario_options = "".join(
        f'<option value="{_e(scenario)}">{_e(SCENARIO_LABELS.get(scenario, scenario or "未分类"))} · {count} 条</option>'
        for scenario, count in scenario_counts.items()
    )
    cards = "".join(_case_card(case, operations, rules, sources) for case in cases)
    title = project.get("title") or bundle.get("title") or "接口测试"
    project_id = project.get("id", "")
    bundle_url = f"/api/projects/{_e(project_id)}/artifacts/bundle.json"
    summary = " · ".join(
        f"{STATUS_LABELS.get(state, state)} {count} 条" for state, count in states.items() if count
    )

    return TEMPLATE.format(
        report_theme=REPORT_THEME_CSS,
        title=_e(title), total=len(cases), operation_count=len(used_operations), summary=_e(summary),
        ready=states["READY"], needs_rule=states["NEEDS_RULE"],
        unavailable=states["QUARANTINED"] + states["UNSUPPORTED"] + states["BLOCKED"],
        rules=len(rules), operation_options="".join(operation_options), state_options=state_options,
        scenario_options=scenario_options, operation_rows="".join(operation_rows), cards=cards,
        bundle_url=bundle_url,
    )


TEMPLATE = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · 测试用例设计报告</title>
<style>
:root{{--bg:#0a0a0a;--ink:#e2e8f4;--muted:#9caac1;--line:#2b3549;--blue:#91a8ff;--green:#72d5b1;--orange:#ebbe76;--red:#f297a9}}
*{{box-sizing:border-box}}body{{margin:0;background:#0a0a0a;color:var(--ink);font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
body>header{{padding:38px max(5vw,24px) 32px;border-bottom:1px solid var(--line);background:#0d121d}}.back{{color:#dbe6ff;text-decoration:none}}.eyebrow{{margin-top:18px;color:#91a8ff;font-size:11px;letter-spacing:2.5px;font-weight:700}}
h1{{font-size:32px;line-height:1.25;margin:8px 0}}header p{{color:var(--muted);margin:4px 0}}.meta{{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}}.meta span{{border:1px solid #40506b;border-radius:7px;padding:5px 10px;font-size:12px}}
main{{max-width:1280px;margin:28px auto;padding:0 24px 60px}}.overview{{display:grid;grid-template-columns:2fr 1fr;gap:18px}}.panel,.case{{background:rgba(18,25,39,.76);border:1px solid var(--line);border-radius:16px;box-shadow:0 12px 40px #0003}}.panel{{padding:22px}}h2{{color:#f5f7ff;margin:0 0 10px;font-size:19px}}.summary-line{{display:flex;gap:34px;flex-wrap:wrap}}.summary-line strong{{display:block;font-size:27px}}.summary-line span{{color:var(--muted);font-size:12px}}.notice{{margin-top:17px;padding:11px 14px;border-left:3px solid var(--blue);background:#162235;color:#b5c2d7;border-radius:8px}}
.toolbar{{position:sticky;top:0;z-index:5;display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:26px 0 14px;padding:14px 16px;background:#0d1523e8;border:1px solid #2e3b51;border-radius:14px;backdrop-filter:blur(10px)}}.toolbar h2{{margin:0 auto 0 0}}input,select,button{{font:inherit;color:var(--ink);background:#0e1624;border:1px solid #36425a;border-radius:9px;padding:9px 11px}}input{{min-width:240px}}button{{cursor:pointer}}button:hover{{border-color:var(--blue)}}
.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;text-align:left}}th,td{{padding:9px 11px;border-bottom:1px solid var(--line)}}th{{color:var(--muted);font-weight:500;background:#172234}}code,pre{{font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;overflow-wrap:anywhere}}
.case{{margin:11px 0;padding:20px 22px}}.case-title{{display:flex;align-items:flex-start;gap:15px}}.case-title>div{{min-width:0;flex:1}}.case-title code{{color:var(--blue)}}.case-title h2{{font-size:18px;margin:2px 0 0}}.state,.tags span{{display:inline-block;border-radius:6px;padding:3px 9px;font-size:11px;white-space:nowrap;background:#29374f;color:#b3c1d8}}.state.READY{{background:#1b3c34;color:#86dfba}}.state.NEEDS_RULE,.state.BLOCKED{{background:#413323;color:#f0c682}}.state.QUARANTINED{{background:#352b4b;color:#d0b6f5}}.state.UNSUPPORTED{{background:#442833;color:#f7a7b7}}.tags{{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0 14px}}.tags .method{{color:var(--blue);font-weight:700}}
dl{{display:grid;grid-template-columns:145px minmax(0,1fr);margin:0;border-top:1px solid var(--line)}}dt,dd{{margin:0;padding:11px 8px;border-bottom:1px solid var(--line)}}dt{{font-weight:700;color:#c7d2e6}}dd{{white-space:pre-wrap;color:#b5c2d7}}dd pre{{margin:0}}.source{{margin:8px 0 0}}.source summary{{cursor:pointer;color:var(--blue)}}.source pre{{max-height:260px;overflow:auto;padding:10px;background:#0d1727;border-radius:8px}}
.asset{{color:var(--blue)}}#empty{{display:none;text-align:center;color:var(--muted);padding:50px}}.hidden{{display:none}}footer{{padding:20px 0;color:var(--muted);font-size:12px}}
@media(max-width:780px){{main{{padding:0 14px}}.overview{{grid-template-columns:1fr}}input{{width:100%;min-width:0}}dl{{grid-template-columns:1fr}}dt{{padding-bottom:2px;border-bottom:0}}dd{{padding-top:2px}}.toolbar{{position:static}}}}
@media print{{body{{background:#fff;color:#183044}}body>header,.panel,.case{{background:#fff;color:#183044;box-shadow:none}}.toolbar{{display:none}}.case{{break-inside:avoid}}}}
{report_theme}
</style></head><body>
<header><a class="back" href="/api-testing">← 返回测试会话</a><div class="eyebrow">API TEST WORKSPACE / CASE DESIGN</div><h1>{title} · 测试用例</h1><p>{total} 条设计用例 · {operation_count} 个接口及关联链路 · 全部未执行</p><p>本页展示当前冻结的测试设计。执行结果以运行后的测试报告为准。</p><div class="meta"><span>{summary}</span><span>规则依据 {rules} 条</span></div></header>
<main><div class="overview"><section class="panel"><h2>用例设计概览</h2><div class="summary-line"><div><strong>{total}</strong><span>全部用例</span></div><div><strong>{operation_count}</strong><span>覆盖接口</span></div><div><strong>{ready}</strong><span>可执行</span></div><div><strong>{needs_rule}</strong><span>待确认</span></div><div><strong>{unavailable}</strong><span>隔离 / 暂不支持</span></div></div><p class="notice">每条用例均列出前置条件、请求步骤、关键断言、预期依据、清理方案和当前执行状态。</p></section><section class="panel"><h2>当前资产</h2><p>这是生成后冻结的用例版本，尚未发送测试请求。</p><a class="asset" href="{bundle_url}" download="bundle.json">下载用例 JSON ↓</a></section></div>
<section class="panel" style="margin-top:18px"><h2>接口覆盖</h2><div class="table-wrap"><table><thead><tr><th>接口</th><th>用例</th><th>可执行</th><th>待确认</th><th>其他</th></tr></thead><tbody>{operation_rows}</tbody></table></div></section>
<div class="toolbar"><h2>测试用例 <small id="visible-count"></small></h2><input id="search" placeholder="搜索 ID、场景、接口或断言" aria-label="搜索用例"><select id="api-filter" aria-label="接口筛选"><option value="">全部接口</option>{operation_options}</select><select id="scenario-filter" aria-label="场景筛选"><option value="">全部场景</option>{scenario_options}</select><select id="state-filter" aria-label="状态筛选"><option value="">全部状态</option>{state_options}</select><button id="reset" type="button">清空筛选</button></div>
<section id="cases">{cards}</section><p id="empty">没有匹配的测试用例</p><footer>页面中的请求内容已脱敏；原文依据来自当前冻结的契约与规则快照。</footer></main>
<script>
const cards=[...document.querySelectorAll('.case')],search=document.querySelector('#search'),api=document.querySelector('#api-filter'),scenario=document.querySelector('#scenario-filter'),state=document.querySelector('#state-filter');
function update(){{let visible=0,q=search.value.trim().toLowerCase();cards.forEach(card=>{{const show=(!q||card.textContent.toLowerCase().includes(q)||card.dataset.search.includes(q))&&(!api.value||card.dataset.apis.split(',').includes(api.value))&&(!scenario.value||card.dataset.scenario===scenario.value)&&(!state.value||card.dataset.state===state.value);card.classList.toggle('hidden',!show);if(show)visible++}});document.querySelector('#visible-count').textContent=`${{visible}} / ${{cards.length}}`;document.querySelector('#empty').style.display=visible?'none':'block'}}
[search,api,scenario,state].forEach(control=>control.addEventListener(control===search?'input':'change',update));document.querySelector('#reset').addEventListener('click',()=>{{search.value='';api.value='';scenario.value='';state.value='';update()}});update();
</script></body></html>'''
