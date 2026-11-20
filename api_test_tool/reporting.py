"""Self-contained, escaped HTML reports from frozen test assets and evidence."""
from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path

from .report_theme import REPORT_THEME_CSS
from .defect_drafts import DRAFT_CSS, DRAFT_SCRIPT, case_defect_draft, draft_panel


def _e(value) -> str:
    return html.escape(str(value), quote=True)


def _json(value) -> str:
    return _e(json.dumps(value, ensure_ascii=False, indent=2))


LABELS = {"PASS": "通过", "FAIL": "失败", "BROKEN": "执行异常", "BLOCKED": "未执行",
          "QUARANTINED": "隔离", "UNSUPPORTED": "暂不支持", "NEEDS_RULE": "待补预期", "READY": "可执行",
          "NOT_CONFIGURED": "未配置", "documented": "依据已确认"}

SCENARIO_LABELS = {"normal": "正常流程", "missing": "缺少必填字段", "empty": "空值测试",
                   "null": "空值（null）测试", "wrong_type": "字段类型错误", "boundary": "边界值测试",
                   "duplicate": "重复提交", "auth_missing": "缺少登录凭证", "invalid_enum": "非法枚举值",
                   "custom": "自定义场景"}
ASSERTION_LABELS = {"status": "HTTP 状态码", "json_equal": "响应字段值匹配", "json_schema": "响应结构校验", "response_schema": "状态与响应分支校验",
                    "json_exists": "响应字段存在", "cookie_present": "Cookie 存在", "header_equal": "响应头匹配",
                    "equals_variable": "响应值与已保存变量一致"}


def _badge(status: str) -> str:
    return f'<span class="badge {_e(status)}">{_e(LABELS.get(status, status))}</span>'


def _is_network_stop(reason: str) -> bool:
    return reason.startswith(("Network availability failure:", "Cannot establish an approved network session:"))


def _display_reason(status: str, asset_state: str, reason: str) -> str:
    if _is_network_stop(reason):
        return "前序请求无法连接测试环境，本用例未执行" if status == "BLOCKED" else "无法连接测试环境，执行中断"
    if status == "BLOCKED" and reason.startswith("HTTP cleanup failed after case"):
        return "前序用例清理失败，为保护测试环境，本用例未执行"
    if status == "BLOCKED" and reason.startswith("Preflight validation failed"):
        return "执行前检查未通过，本用例未发送请求"
    if status == "BLOCKED" and asset_state == "NEEDS_RULE":
        return "预期结果缺少明确依据，本用例未执行"
    return reason or ("所有已声明断言均通过" if status == "PASS" else "展开查看执行证据")


def _unexecuted_explanation(status: str, asset_state: str, reason: str) -> str:
    if _is_network_stop(reason):
        message = "前序请求无法连接测试环境，执行器已停止。本用例没有发出请求；服务恢复后重新执行即可，无需修改规则。"
    elif reason.startswith("HTTP cleanup failed after case"):
        message = "前序用例清理失败，测试环境的隔离状态无法确认。本用例没有发出请求；先处理清理问题，再重新执行。"
    elif reason.startswith("Preflight validation failed"):
        message = "执行前检查没有通过，因此本用例没有发出请求。修正下方技术原因后重新执行。"
    elif asset_state == "NEEDS_RULE":
        message = "文档或已确认信息不足以确定预期结果，因此本用例没有发出请求。补充明确预期后重新执行。"
    elif status == "QUARANTINED":
        message = "本用例处于隔离状态，没有发出请求。解除隔离并确认执行条件后重新执行。"
    elif status == "UNSUPPORTED":
        message = "当前执行器暂不支持这个场景，因此没有发出请求。"
    else:
        message = "前置条件未满足，本用例没有发出请求。处理下方原因后重新执行。"
    technical = (f'<details class="technical-reason"><summary>查看技术原因</summary><code>{_e(reason)}</code></details>'
                 if reason else "")
    return f'<section class="execution-note"><strong>为什么没有执行</strong><p>{_e(message)}</p>{technical}</section>'


def _rule_conclusion(rule: dict) -> str:
    description = str(rule.get("description") or "").strip()
    if description.startswith("模型候选："):
        description = description.removeprefix("模型候选：").split(" / ", 1)[0].strip()
    return description or "本用例的预期结果已核对"


def _source_label(source_id: str, source: dict) -> str:
    path = str(source.get("path") or source_id)
    if path.startswith("inputs/"):
        return "接口文档"
    if path == "web:user-review":
        return "人工确认记录"
    return path


def _render_judgement_basis(rule_ids: list[str], rules: dict, sources: dict) -> tuple[str, set[str]]:
    selected_rules = [rules.get(rule_id, {}) for rule_id in rule_ids]
    conclusions = Counter(_rule_conclusion(rule) for rule in selected_rules)
    source_items = []
    source_keys = set()
    source_paths = set()
    for rule in selected_rules:
        for source_id in rule.get("source_ids", []):
            source = sources.get(source_id, {})
            key = (str(source.get("path", source_id)), str(source.get("location", "")),
                   str(source.get("sha256", "")), str(source.get("excerpt", "")))
            if key in source_keys:
                continue
            source_keys.add(key)
            source_paths.add(key[0])
            source_items.append((source_id, source))
    conclusion_items = ""
    for text, count in conclusions.items():
        shared = f' <span class="muted">（{count} 条断言共用）</span>' if count > 1 else ""
        conclusion_items += f'<li>{_e(text)}{shared}</li>'
    source_details = "".join(
        f'<details class="source"><summary>{_e(_source_label(source_id, source))}</summary>'
        f'<p class="muted"><code>{_e(source.get("path", source_id))}</code> · {_e(source.get("location", ""))}</p>'
        f'<p class="hash">SHA-256 {_e(source.get("sha256", ""))}</p><pre>{_e(source.get("excerpt", ""))}</pre></details>'
        for source_id, source in source_items
    )
    technical_rules = "".join(
        f'<li><code>{_e(rule_id)}</code> · {_e(LABELS.get(rule.get("state", ""), rule.get("state", "")))}</li>'
        for rule_id, rule in zip(rule_ids, selected_rules)
    )
    rendered = (
        f'<details class="sources"><summary>查看判断依据（{len(conclusions)} 项结论 · {len(source_items)} 处来源）</summary>'
        f'<div class="basis-summary"><h4>检查结论</h4><ul>{conclusion_items}</ul></div>'
        f'<h4>依据来源</h4><p class="muted">这些结论共享以下依据；相同来源只列一次。</p>{source_details}'
        f'<details class="technical-rules"><summary>技术规则（{len(rule_ids)} 条）</summary><ul>{technical_rules}</ul></details></details>'
    )
    return rendered, source_paths


def write_report(result: dict, bundle: dict, path: Path, *, display_titles: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(result, bundle, display_titles=display_titles), encoding="utf-8")
    return path


def render_report(result: dict, bundle: dict, *, display_titles: dict | None = None,
                  case_sources: dict | None = None) -> str:
    counts = result.get("summary", {})
    contract = bundle.get("contract", {})
    sources = contract.get("sources", {})
    rules = {rule["id"]: rule for rule in bundle.get("rules", [])}
    assets = {case["id"]: case for case in bundle.get("cases", [])}
    cases = result.get("cases", [])
    operation_rows = []
    evidence_paths = set()
    for op_id, op in contract.get("operations", {}).items():
        matching = [case for case in cases if case.get("operation_id") == op_id]
        stats = Counter(case.get("status") for case in matching)
        operation_rows.append(f'<tr><td><span class="method">{_e(op.get("method", ""))}</span> '
                              f'<code>{_e(op.get("path", ""))}</code></td><td>{len(matching)}</td>'
                              f'<td>{stats["PASS"]}</td><td>{stats["FAIL"] + stats["BROKEN"]}</td>'
                              f'<td>{len(matching) - stats["PASS"] - stats["FAIL"] - stats["BROKEN"]}</td></tr>')
    cards = []
    for case_index, case in enumerate(cases):
        case_id = case["id"]
        origin = (case_sources or {}).get(case_id)
        case_bundle = origin["bundle"] if origin else bundle
        case_result = origin["result"] if origin else result
        case_rules = {rule["id"]: rule for rule in case_bundle.get("rules", [])}
        case_documents = case_bundle.get("contract", {}).get("sources", {})
        asset = next((c for c in case_bundle.get("cases", []) if c["id"] == case_id), {})
        title = (display_titles or {}).get(case_id, case.get("title", case_id))
        scenario = SCENARIO_LABELS.get(case.get("scenario", ""), case.get("scenario", ""))
        step_assets = {s["id"]: s for s in asset.get("steps", [])}
        status = case.get("status", "BROKEN")
        rule_ids = list(dict.fromkeys(case.get("rule_ids", []) + [
            a.get("rule_id") for step in case.get("steps", []) for a in step.get("assertions", []) if a.get("rule_id")]))
        basis_html, case_evidence_paths = _render_judgement_basis(rule_ids, case_rules, case_documents) if rule_ids else ("", set())
        evidence_paths.update(case_evidence_paths)
        steps = []
        for step in case.get("steps", []):
            request, response = step.get("request", {}), step.get("response", {}) or {}
            assertion_rows = []
            for a in step.get("assertions", []):
                assertion_rows.append(f'<tr><td>{_badge("PASS" if a.get("passed") else "FAIL")}</td>'
                    f'<td>{_e(ASSERTION_LABELS.get(a.get("kind", ""), a.get("kind", "")))}<small>{_e(a.get("rule_id", ""))}</small></td>'
                    f'<td><pre>{_json(a.get("expected"))}</pre></td><td><pre>{_json(a.get("actual"))}</pre>'
                    f'<small>{_e(a.get("message", ""))}</small></td></tr>')
            steps.append(f'<details class="step"><summary>{_badge(step.get("status", "BROKEN"))} '
                         f'<strong>{_e(step_assets.get(step.get("id"), {}).get("title", step.get("id", "")))}</strong> · {_e(request.get("method", ""))} '
                         f'{_e(request.get("url", ""))}<span class="timing">HTTP {_e(response.get("status", "—"))} · '
                         f'{_e(response.get("elapsed_ms", "—"))} ms</span></summary>'
                         f'<div class="io"><div><h4>请求 · 已脱敏</h4><pre>{_json(request)}</pre></div>'
                         f'<div><h4>响应 · 已脱敏</h4><pre>{_json(response)}</pre></div></div>'
                         f'<p class="error">{_e(step.get("error", ""))}</p>'
                         '<div class="table-wrap"><table><thead><tr><th>结果</th><th>断言 / 规则</th><th>期望</th><th>实际</th></tr></thead>'
                         f'<tbody>{"".join(assertion_rows)}</tbody></table></div></details>')
        reason = case.get("reason") or asset.get("reason") or ""
        cleanup_failed = case.get("cleanup", {}).get("status") == "FAIL"
        cleanup_badge = '<span class="badge FAIL">清理失败</span>' if cleanup_failed else ''
        if cleanup_failed:
            reason = (reason + "；" if reason else "") + "本用例数据清理失败，请查看清理证据"
        asset_state = str(asset.get("state", ""))
        body = "".join(steps) or _unexecuted_explanation(status, asset_state, reason)
        if case.get("cleanup"):
            body += f'<details class="source"><summary>本用例清理证据</summary><pre>{_json(case["cleanup"])}</pre></details>'
        body += basis_html
        if origin:
            base = origin["base"]
            body = (f'<p class="muted">结果来源：<a href="{_e(base)}/index.html">{_e(case_result.get("started_at", ""))} · 原始执行</a>'
                    f' · <a href="{_e(base)}/bundle.json">冻结用例 JSON</a>'
                    f' · <a href="{_e(base)}/result.json">执行证据 JSON</a></p>') + body
        draft = case_defect_draft(case_result, case_bundle, case, title)
        draft_html = draft_panel(f"defect-{case_index}", *draft) if draft else ""
        if origin and draft_html:
            draft_html = draft_html.replace('class="defect-draft"',
                f'class="defect-draft" data-pingcode-report="{_e(origin["id"])}" data-pingcode-draft="defect-{origin["index"]}"', 1)
        cards.append(f'<article class="case" data-status="{_e(status)}" data-search="{_e(case_id + " " + title + " " + case.get("title", "") + " " + case.get("operation_id", "") + " " + scenario + " " + case.get("scenario", ""))}">'
                     f'<details><summary><div class="case-top">{_badge(status)}{cleanup_badge}<code>{_e(case_id)}</code>'
                     f'<span class="scenario">{_e(scenario)}</span></div>'
                     f'<h3>{_e(title)}</h3>'
                     f'<p>{_e(_display_reason(status, asset_state, reason))}</p></summary>'
                     f'<div class="case-body">{body}</div></details>{draft_html}</article>')
    kpis = "".join(f'<button class="kpi" data-filter="{key}"><b>{counts.get(key, 0)}</b><span>{LABELS[key]}</span></button>'
                   for key in ("PASS", "FAIL", "BROKEN", "BLOCKED", "QUARANTINED", "UNSUPPORTED"))
    gap_count = sum(1 for c in cases if assets.get(c["id"], {}).get("state") == "NEEDS_RULE")
    cleanup = result.get("cleanup", {})
    http_cleanup = Counter(c.get("cleanup", {}).get("status", "NOT_CONFIGURED") for c in cases if c.get("steps"))
    cleanup_status = ("FAIL" if cleanup.get("status") == "FAIL" or http_cleanup["FAIL"] else
                      "PASS" if cleanup.get("status") == "PASS" or http_cleanup["PASS"] else "NOT_CONFIGURED")
    cleanup_view = {"status": cleanup_status, "HTTP_cleanup_cases": dict(http_cleanup), "end_of_run_cleanup": cleanup}
    complete = counts.get("complete", False)
    success = (complete and not counts.get("FAIL", 0) and not counts.get("BROKEN", 0)
               and not result.get("validation_errors") and cleanup.get("status") != "FAIL"
               and not any(c.get("cleanup", {}).get("status") == "FAIL" for c in cases))
    headline = "本轮全部通过" if success else "本轮包含未通过或未执行用例"
    subtitle = "通过只代表本轮已声明的断言，不代表接口全部行为已覆盖。"
    issues = bundle.get("issues", []) + contract.get("issues", []) + result.get("validation_errors", [])
    filter_options = ''.join(f'<option value="{k}">{LABELS[k]}</option>' for k in ("PASS", "FAIL", "BROKEN", "BLOCKED", "QUARANTINED", "UNSUPPORTED"))
    rendered = TEMPLATE.replace("</style>", DRAFT_CSS + "</style>").replace("</script>", DRAFT_SCRIPT + "</script>")
    rendered = rendered.replace("{{TITLE}}", _e(result.get("title", "接口测试报告")))
    values = {
        "HEADLINE": headline, "SUBTITLE": subtitle, "RUN_ID": _e(result.get("run_id", "")),
        "ENV": _e(result.get("environment", {}).get("name", "")),
        "BASE_URL": _e(result.get("environment", {}).get("base_url", "")),
        "STARTED": _e(result.get("started_at", "")), "FINISHED": _e(result.get("finished_at", "")),
        "TOTAL": str(counts.get("total", len(cases))), "OP_COUNT": str(len(contract.get("operations", {}))),
        "REQUESTS": str(result.get("requests_sent", sum(len(c.get("steps", [])) for c in cases))),
        "RULES": str(len(evidence_paths)), "GAPS": str(gap_count), "KPIS": kpis,
        "OPERATIONS": ''.join(operation_rows), "CASES": ''.join(cards),
        "CLEANUP": _json(cleanup_view), "CLEANUP_BADGE": _badge(cleanup_status),
        "ISSUES": _json(issues), "FILTER_OPTIONS": filter_options,
        "ENGINE": _e(bundle.get("generation", {}).get("engine", "rules-v1")),
        "GENERATION_NOTE": (_e("使用者的模型 API · " + bundle["generation"]["model"] + " · " + bundle["generation"].get("protocol", ""))
                            if bundle.get("generation", {}).get("model") else "依据文档与规则生成，未调用模型 API。"),
        "SEED": _e(bundle.get("generation", {}).get("seed", "")),
    }
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    if bundle.get("web", {}).get("experience"):
        notice = ('<section class="panel demo-notice"><h2>演示环境说明</h2><p>'
                  '演示服务注入了可控故障，以下为真实 HTTP 执行结果，不代表业务系统存在这些缺陷。'
                  '点击失败项的问题描述旁「提交到 PingCode」，人工审核后可体验推送。'
                  '临时服务已在运行结束后销毁，需重新体验来复测。</p></section>')
        rendered = rendered.replace("<main>", "<main>" + notice, 1)
    rendered = rendered.replace("</head>", "<style>" + REPORT_THEME_CSS + "</style></head>", 1)
    return rendered


TEMPLATE = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{TITLE}} · 接口测试工作台</title>
<style>
:root{--bg:#f3f5fa;--ink:#152440;--muted:#65738b;--line:#e0e5ef;--blue:#385fea;--green:#13785e;--orange:#955319;--red:#b7314c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;color:var(--ink)}
header{background:#111f3b;color:white;padding:42px max(5vw,24px) 34px}header .brand{font-size:12px;letter-spacing:2px;color:#a8b7d4;font-weight:700}.report-back{display:inline-block;color:#dbe6ff;margin-bottom:10px;text-decoration:none}.report-back:hover{text-decoration:underline}h1{font-size:32px;line-height:1.3;margin:14px 0 12px}header p{color:#becae0;margin:0;max-width:850px}.meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:25px}.meta span{border:1px solid #41516d;border-radius:6px;padding:5px 11px;font-size:12px;overflow-wrap:anywhere}.meta code{color:#b8caff}
main{max-width:1280px;margin:28px auto;padding:0 24px 60px}.overview{display:grid;grid-template-columns:2fr 1fr;gap:20px}.panel{background:white;border:1px solid var(--line);border-radius:14px;padding:22px}h2{font-size:19px;margin:0 0 12px}h3{font-size:16px;margin:10px 0 4px}h4{font-size:13px;margin:10px 0}.muted,small{color:var(--muted)}.summary-line{display:flex;gap:28px;flex-wrap:wrap}.summary-line strong{font-size:26px}.summary-line span{display:block;font-size:12px;color:var(--muted)}.notice{background:#f3f6ff;border-left:3px solid var(--blue);padding:10px 13px;margin:17px 0 0;color:#465976;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:20px 0}.kpi{text-align:left;border:1px solid var(--line);border-radius:12px;background:white;padding:17px 20px;color:var(--ink);cursor:pointer}.kpi:hover,.kpi.active{border-color:var(--blue);box-shadow:0 2px 8px #385fea15}.kpi b{display:block;font-size:28px;line-height:1.3}.kpi span{font-size:13px;color:var(--muted)}.kpi[data-filter=PASS] b{color:var(--green)}.kpi[data-filter=FAIL] b,.kpi[data-filter=BROKEN] b{color:var(--red)}
table{width:100%;border-collapse:collapse;text-align:left;font-size:13px}th{font-weight:500;color:var(--muted);background:#f8f9fc}td,th{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}table small{display:block}.table-wrap{overflow:auto}.method{font-size:11px;color:var(--blue);font-weight:700;margin-right:6px}code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;margin:6px 0}td pre{max-width:400px}
.toolbar{display:flex;align-items:center;gap:12px;margin:30px 0 15px;flex-wrap:wrap}.toolbar h2{margin:0;margin-right:auto}.toolbar input,.toolbar select,.toolbar button{font:inherit;border:1px solid var(--line);border-radius:8px;background:white;padding:9px 12px}.toolbar input{min-width:260px}.toolbar button{cursor:pointer}.case{background:white;border:1px solid var(--line);border-radius:12px;margin:10px 0;overflow:hidden}.case>details>summary{padding:18px 22px;list-style:none;cursor:pointer}.case>details>summary::after{content:"展开证据 ＋";float:right;color:var(--muted);font-size:12px;margin-top:-22px}.case>details[open]>summary::after{content:"收起 －"}.case-top{display:flex;align-items:center;gap:12px}.case h3{padding-right:80px}.case summary p{font-size:13px;color:var(--muted);margin:5px 0;padding-right:90px}.scenario{margin-left:auto;font-size:12px;color:var(--muted)}.badge{display:inline-block;border-radius:5px;background:#edf0f6;color:#59667d;padding:2px 9px;font-size:11px;font-weight:600;white-space:nowrap}.PASS{background:#e5f4ed;color:var(--green)}.FAIL,.BROKEN{background:#fce9ee;color:var(--red)}.BLOCKED,.NEEDS_RULE{background:#fff0db;color:var(--orange)}.QUARANTINED{background:#eeeafb;color:#7150a2}.case-body{border-top:1px solid var(--line);padding:18px 22px;background:#fbfcfe}.step{background:white;border:1px solid var(--line);border-radius:8px;margin:0 0 12px;padding:12px}.step>summary{cursor:pointer;font-size:12px;overflow-wrap:anywhere}.timing{display:block;margin-left:19px;color:var(--muted)}.io{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:15px 0}.io>div{min-width:0;background:#f4f6fa;border-radius:7px;padding:10px 14px}.error{color:var(--red)}.execution-note{border-left:3px solid var(--orange);border-radius:8px;background:#fff8ed;padding:14px 16px}.execution-note p{margin:6px 0}.technical-reason{margin-top:8px}.source,.sources{font-size:12px;overflow-wrap:anywhere;margin-top:12px}.source summary,.sources>summary,.technical-rules>summary{cursor:pointer;color:var(--blue)}.basis-summary{margin:12px 0;padding:12px 16px;border-radius:8px;background:#f4f6fa}.basis-summary h4,.sources>h4{margin:0 0 6px}.basis-summary ul,.technical-rules ul{margin:6px 0;padding-left:20px}.source pre{max-height:330px;overflow:auto;background:#f2f4f9;padding:12px}.technical-rules{margin-top:14px}.technical-rules li{margin:4px 0}.hash{font-size:10px;color:var(--muted)}.foot{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:25px}.foot pre{max-height:280px;overflow:auto}footer{font-size:12px;color:var(--muted);padding:20px 0}#empty{display:none;text-align:center;padding:40px}.hidden{display:none!important}
@media(max-width:760px){header{padding:28px 22px}h1{font-size:25px}main{padding:0 14px}.overview,.io,.foot{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(3,1fr)}.kpi{padding:13px}.toolbar input{min-width:160px;width:100%}.case>details>summary::after{display:none}.case summary p,.case h3{padding-right:0}.case-top{flex-wrap:wrap}.scenario{margin-left:0}.summary-line{gap:20px}}
@media print{header{background:white;color:var(--ink)}header p{color:var(--muted)}.toolbar{display:none}.case{break-inside:avoid}main{max-width:none}}
</style></head><body>
<header><a class="report-back" href="/api-testing">← 返回测试台</a><div class="brand">API TEST STUDIO / 第一版</div><h1>{{TITLE}}</h1><p>从接口文档到可执行测试。每条断言保留规则来源，每次运行保留请求、响应和未执行原因。</p>
<div class="meta"><span>环境 {{ENV}}</span><span><code>{{BASE_URL}}</code></span><span>RUN {{RUN_ID}}</span></div></header>
<main><div class="overview"><section class="panel"><h2>{{HEADLINE}}</h2><div class="summary-line"><div><strong>{{TOTAL}}</strong><span>本轮用例</span></div><div><strong>{{OP_COUNT}}</strong><span>文档接口</span></div><div><strong>{{REQUESTS}}</strong><span>已发送请求</span></div><div><strong>{{RULES}}</strong><span>依据来源</span></div></div><p class="notice">{{SUBTITLE}}其中 <b>{{GAPS}}</b> 条因预期不明确而未执行；未执行、隔离和暂不支持均未计入通过。</p></section>
<section class="panel"><h2>本轮资产</h2><p class="muted">引擎 <code>{{ENGINE}}</code> · seed {{SEED}}<br>{{GENERATION_NOTE}}</p><p class="muted">开始 {{STARTED}}<br>结束 {{FINISHED}}</p><a href="bundle.json">冻结用例 JSON</a> · <a href="result.json">执行证据 JSON</a></section></div>
<section class="kpis">{{KPIS}}</section><section class="panel"><h2>接口覆盖</h2><div class="table-wrap"><table><thead><tr><th>接口</th><th>本轮用例</th><th>通过</th><th>失败 / 异常</th><th>未执行</th></tr></thead><tbody>{{OPERATIONS}}</tbody></table></div></section>
<div class="toolbar"><h2>用例与证据 <small id="visible-count"></small></h2><input id="search" placeholder="搜索编号、接口或场景" aria-label="搜索用例"><select id="filter" aria-label="结果筛选"><option value="all">全部结果</option>{{FILTER_OPTIONS}}</select><button id="expand">展开全部</button></div>
<section id="cases">{{CASES}}</section><p id="empty">没有匹配的用例</p><div class="foot"><section class="panel"><h2>数据清理 {{CLEANUP_BADGE}}</h2><pre>{{CLEANUP}}</pre></section><section class="panel"><h2>契约与静态检查提示</h2><pre>{{ISSUES}}</pre></section></div><footer>报告可离线查看。响应中的敏感字段已脱敏；规则快照用于回放同一测试设计，运行时创建新的数据命名空间。{{SUBTITLE}}</footer></main>
<script>
const cards=[...document.querySelectorAll('.case')],search=document.querySelector('#search'),filter=document.querySelector('#filter');
function update(){let visible=0;const q=search.value.trim().toLowerCase();cards.forEach(c=>{const show=(filter.value==='all'||c.dataset.status===filter.value)&&c.dataset.search.toLowerCase().includes(q);c.classList.toggle('hidden',!show);if(show)visible++});document.querySelector('#visible-count').textContent=visible+' / '+cards.length;document.querySelector('#empty').style.display=visible?'none':'block';document.querySelectorAll('.kpi').forEach(k=>k.classList.toggle('active',k.dataset.filter===filter.value));}
search.addEventListener('input',update);filter.addEventListener('change',update);document.querySelectorAll('.kpi').forEach(k=>k.addEventListener('click',()=>{filter.value=filter.value===k.dataset.filter?'all':k.dataset.filter;update()}));
let expanded=false;document.querySelector('#expand').addEventListener('click',e=>{expanded=!expanded;cards.filter(c=>!c.classList.contains('hidden')).forEach(c=>c.firstElementChild.open=expanded);e.target.textContent=expanded?'收起全部':'展开全部'});update();
</script></body></html>'''
