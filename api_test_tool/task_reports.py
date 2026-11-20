"""Free-form Codex findings with server-owned execution evidence and escaped HTML."""
from __future__ import annotations

from .document_targets import normalize_base_url

import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

from .execution import Redactor
from .report_theme import REPORT_THEME_CSS
from .reporting import render_report
from .case_reporting import render_case_report
from .defect_drafts import DRAFT_CSS, DRAFT_SCRIPT, draft_panel, finding_draft

DEFAULT_GOAL = "按接口文档完成测试：先完整设计并保存每个接口的正向、逆向、边界、安全及业务扩展用例，再核对并执行所有具备条件的用例，修正可解决的执行问题，最后输出真实执行结果、问题分析和未执行原因的中文可视化报告；完整设计在独立用例页查看，逐条请求与断言在执行报告查看，不在任务报告中重复展开。"
REMOVED_REPORT_SECTION_PREFIXES = ("完整设计与逐条结果",)
SECTION_URL = re.compile(r'''(?<![\w:/])https?://[^\s<>"'`，。；：！？、（）【】《》“”‘’]+''', re.I)


def _section_content_html(value):
    """Link explicit HTTP(S) text only; preserve literal prose and saved data."""
    text = str(value)
    parts, previous = [], 0
    for match in SECTION_URL.finditer(text):
        candidate = match.group()
        # Keep prose punctuation outside links, including unmatched closing brackets.
        extra = {close: candidate.count(close) - candidate.count(opening)
                 for opening, close in (('(', ')'), ('[', ']'), ('{', '}'))}
        end = len(candidate)
        while end:
            last = candidate[end - 1]
            if last in '.,;!?':
                end -= 1
            elif extra.get(last, 0) > 0:
                extra[last] -= 1
                end -= 1
            else:
                break
        url = candidate[:end]
        linkable = False
        try:
            parsed = urlsplit(url)
            linkable = (parsed.scheme in {'http', 'https'} and bool(parsed.hostname)
                        and parsed.username is None and parsed.password is None
                        and (parsed.port is None or 1 <= parsed.port <= 65535)
                        and '%' not in parsed.netloc and '\\' not in url
                        and not any(ord(char) < 32 or ord(char) == 127 for char in url))
        except ValueError:
            pass
        parts.append(html.escape(text[previous:match.start()], quote=True))
        escaped = html.escape(url, quote=True)
        parts.append(f'<a href="{escaped}" target="_blank" rel="noopener noreferrer">{escaped}</a>'
                     if linkable else escaped)
        parts.append(html.escape(candidate[end:], quote=True))
        previous = match.end()
    parts.append(html.escape(text[previous:], quote=True))
    return ''.join(parts)


def _is_removed_report_section(title):
    return str(title).strip().startswith(REMOVED_REPORT_SECTION_PREFIXES)


def text_field(value, name, limit=12000, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f"{name} 必须是{'非空' if required else ''}文本，最多 {limit} 字符")
    return value.strip()


def task_config(data):
    if not isinstance(data, dict):
        raise ValueError("任务配置必须是对象")
    environment = data.get("environment", "auto")
    if environment not in {"auto", "items", "gomoku", "custom"}:
        raise ValueError("未知测试环境")
    return {"goal": text_field(data.get("goal", DEFAULT_GOAL), "任务目标", required=True),
            "environment": environment,
            "base_url": normalize_base_url(text_field(data.get("base_url", ""), "测试地址", 2000))}


def save_task_report(store, owner, project, data, *, ui_snapshot=None, report_id='', notify=True,
                     _previous_report=None):
    if project.get('test_kind') == 'ui':
        from .ui_retests import redact
        data = redact(store, owner, project['id'], data)
        if ui_snapshot is not None:
            ui_snapshot = redact(store, owner, project['id'], ui_snapshot)
    title = text_field(data.get("title", "任务报告"), "报告标题", 200, True)
    summary = text_field(data.get("summary", ""), "报告结论", 30000, True)
    # The UI publisher derives complete findings from already saved batches.
    # Its Python-only snapshot is not a free-form report submission allowance.
    finding_limit = None if project.get('test_kind') == 'ui' and ui_snapshot is not None else 200
    sections, findings = [], []
    for key, output, fields, maximum in (
        ("sections", sections, ("title", "content"), 60),
        ("findings", findings, ("title", "detail", "evidence", "recommendation", "ai_analysis", "cause_analysis", "severity", "priority",
                                "precondition", "test_data", "steps", "expected", "actual", "case_id", "rule_basis",
                                "environment", "client", "module", "test_environment"), finding_limit),
    ):
        values = data.get(key, [])
        if not isinstance(values, list) or (maximum is not None and len(values) > maximum):
            raise ValueError(f"{key} 必须是数组" + (f"，最多 {maximum} 项" if maximum is not None else ""))
        for value in values:
            if not isinstance(value, dict):
                raise ValueError(f"{key} 每项必须是对象")
            if key == "sections" and isinstance(value.get("title"), str) and _is_removed_report_section(value["title"]):
                continue
            item = {field: text_field(value.get(field, ""), field, 20000, field == "title") for field in fields}
            if key == "findings" and project.get("test_kind") == "ui":
                from .defect_title import normalize_title
                context = project.get("ui_report_context", {})
                item["title"] = normalize_title(item["title"],
                    context.get("environment") or item.get("environment", ""),
                    context.get("client") or item.get("client", ""), item.get("module", ""))
            output.append(item)
    run_ids = data.get("run_ids", [])
    if not isinstance(run_ids, list) or len(run_ids) > 30 or any(not isinstance(r, str) for r in run_ids):
        raise ValueError("run_ids 必须是已保存的执行记录 ID 数组")
    known = {run["id"]: run for run in project.get("runs", [])}
    if any(r not in known for r in run_ids):
        raise ValueError("只能引用本会话已有的执行记录，不能填写未知或其他会话的运行 ID")
    runs = [known[r] for r in dict.fromkeys(run_ids)]
    pid, rid = project["id"], report_id or str(uuid4())
    previous_report = None
    if report_id:
        if ui_snapshot is None or project.get('test_kind') != 'ui':
            raise ValueError('只有当前 UI 任务可以增量更新阶段报告')
        # Only the locked UI publisher supplies this freshly read snapshot.
        previous_report = (_previous_report if _previous_report is not None else
                           store._read(store.project_dir(owner, pid) / 'analyses' / rid / 'report.json'))
        if _previous_report is not None and previous_report.get('id') != rid:
            raise ValueError('报告不属于当前任务')
        if previous_report.get('project_id') != pid:
            raise ValueError('报告不属于当前任务')
    document = (store.project_dir(owner, pid) / project.get("effective_document_file", project["document_file"])).read_text()
    try:
        design_bundle = store.load_asset(owner, pid, "bundle")
    except FileNotFoundError:
        design_bundle = None
    inventory = {"total": len(design_bundle.get("cases", [])),
                 "ready": sum(c.get("state") == "READY" for c in design_bundle.get("cases", [])),
                 "report_url": f"/api/projects/{pid}/reports/{rid}/cases.html"} if design_bundle else None
    imported_results = data.get("imported_results")
    if imported_results is not None:
        if not isinstance(imported_results, dict) or not isinstance(imported_results.get("cases"), list):
            raise ValueError("imported_results 必须包含测试用例数组")
        if len(imported_results["cases"]) > 10000:
            raise ValueError("导入结果最多包含 10000 条测试用例")
        allowed_fields = {"case_id", "environment", "client", "module", "test_environment", "executor", "method", "priority", "category", "layer", "scenario", "precondition", "test_data",
                          "steps", "expected", "conclusion", "ai_analysis", "cause_analysis", "recommendation", "code_basis", "criterion", "result", "evidence", "defect_id",
                          "source_row", "source_sheet", "status", "not_run_reason", "test_data_issue", "steps_issue",
                          "action_type", "action_required"}
        safe_cases = []
        snapshot_cases = {c['case_id']: c for c in (ui_snapshot or {}).get('cases', [])}
        for case in imported_results["cases"]:
            if not isinstance(case, dict):
                raise ValueError("导入结果中的用例必须是对象")
            safe_case = {}
            for key in allowed_fields:
                value = case.get(key, "")
                if key == "source_row":
                    if not isinstance(value, int) or value < 1:
                        raise ValueError("导入结果行号无效")
                    safe_case[key] = value
                else:
                    safe_case[key] = text_field(value, key, 20000)
            # Structured dependency provenance comes from the validated execution,
            # never from arbitrary imported spreadsheets or prose.
            source_case = snapshot_cases.get(safe_case['case_id'], {})
            if source_case.get('updated_at'):
                safe_case['updated_at'] = source_case['updated_at']
            if source_case.get('dependencies'):
                safe_case.update(dependencies=source_case['dependencies'],
                                 blocked_by=source_case.get('blocked_by', []),
                                 execution_disposition=source_case.get('execution_disposition', ''))
            for field in ('checkpoints', 'requirement_ids', 'question_ids', 'verification_modes'):
                if field in source_case:
                    safe_case[field] = source_case[field]
            safe_cases.append(safe_case)
        imported_results = {
            "filename": text_field(imported_results.get("filename", ""), "filename", 255, True),
            "sheet_name": text_field(imported_results.get("sheet_name", ""), "sheet_name", 255, True),
            "header_row": imported_results.get("header_row"),
            "counts": imported_results.get("counts", {}),
            "quality": imported_results.get("quality", {}),
            "cases": safe_cases,
        }
    if imported_results is not None and ui_snapshot is not None:
        from .ui_case_scope import is_superseded
        from .ui_dependencies import blocking_summary
        imported_results['superseded_cases'] = [c for c in ui_snapshot.get('cases', []) if is_superseded(c)]
        imported_results['blocking_summary'] = blocking_summary(ui_snapshot)
    regression_links = data.get("regression_links", [])
    if not isinstance(regression_links, list) or (finding_limit is not None and len(regression_links) > finding_limit):
        raise ValueError("regression_links 必须是数组" + (f"，最多 {finding_limit} 项" if finding_limit is not None else ""))
    safe_links = []
    for value in regression_links:
        if not isinstance(value, dict):
            raise ValueError("regression_links 每项必须是对象")
        safe_links.append({key: text_field(value.get(key, ""), key, 4000, key in {
            "draft_id", "case_id", "source_project_id", "source_report_id", "source_draft_id", "outcome"
        }) for key in ("draft_id", "case_id", "source_project_id", "source_report_id",
                       "source_draft_id", "outcome")})
    if any(item["outcome"] not in {"pending_regression", "regression_passed", "regression_failed", "result_corrected", "pending_submission"}
           for item in safe_links):
        raise ValueError("回归结果状态无效")
    report = Redactor().snapshot({"id": rid, "project_id": pid, "title": title,
        **({'report_type': 'stage'} if project.get('test_kind') == 'ui' else {}),
        "kind": "execution_summary" if runs else "analysis", "summary": summary,
        "test_kind": project.get("test_kind", "api"), "test_version": project.get("test_version", ""),
        "target_url": project.get("ui_target_url", ""),
        "execution_permission": project.get("ui_execution_permission") if project.get("test_kind") == "ui" else None,
        "goal": project.get("task", {}).get("goal", ""), "sections": sections, "findings": findings,
        "created_at": (previous_report or {}).get('created_at') or datetime.now(timezone.utc).isoformat(),
        **({'updated_at': datetime.now(timezone.utc).isoformat(),
            'revision': previous_report.get('revision', 1) + 1} if previous_report else {'revision': 1}),
        "document": {"filename": project.get("effective_filename", project["filename"]), "sha256": hashlib.sha256(document.encode()).hexdigest()},
        "runs": runs, "requests_sent": sum(r.get("requests_sent", 0) for r in runs),
        "model_api_calls": 0, "case_inventory": inventory,
        **({"regression_links": safe_links} if safe_links else {}),
        **({"imported_results": imported_results} if imported_results is not None else {}),
        **({'ui_snapshot': ui_snapshot} if ui_snapshot is not None else {})})
    # Plain findings need no executable cases. Execution facts are copied only from saved runs.
    location = store.project_dir(owner, pid) / "analyses" / rid
    location.mkdir(parents=True, mode=0o700, exist_ok=True)
    if previous_report:
        # Keep the original observations and evidence in private storage while
        # the task's public report and draft identities remain stable.
        archive = location / 'revisions'
        archive.mkdir(mode=0o700, exist_ok=True)
        store._write(archive / f"{previous_report.get('revision', 1)}.json", previous_report)
    if design_bundle:
        store._write_text(location / "cases.html", render_case_report(project, Redactor().snapshot(design_bundle)))
    if imported_results is not None:
        from .ui_records import cases_html
        store._write_text(location / 'cases.html', cases_html(report))
    store._write(location / "report.json", report)
    store._write_text(location / "index.html", render_saved_task_report(store, owner, project, report))
    entry = {key: report[key] for key in ("id", "title", "kind", "created_at", "requests_sent", "revision")}
    if report.get('updated_at'):
        entry['updated_at'] = report['updated_at']
    if report.get('report_type'):
        entry['report_type'] = report['report_type']
    finding_count = imported_results.get("counts", {}).get("failed", 0) if safe_links else len(findings)
    entry.update(findings_count=finding_count, report_url=f"/api/projects/{pid}/reports/{rid}/index.html")
    if ui_snapshot is not None and project.get('ui_retest_round'):
        entry['retest_task_id'] = project['ui_retest_round']['task_id']
    store.update_project(owner, pid, {"status": "reported", "generation_mode": "mcp", "last_analysis": entry, "last_job": {},
        "analysis_reports": ([entry] + [r for r in project.get("analysis_reports", []) if r['id'] != rid])[:30]})
    from .wecom import WeCom
    if notify:
        WeCom(store).auto_report(owner, pid, rid, 'reports')
    return {"report": entry, "summary": summary, "execution_records": len(runs),
            "note": "报告已保存，包含分析结论和关联的真实执行证据。"}


def _merge_run_evidence(store, owner, project, runs):
    """Latest result per case, with immutable per-run evidence kept at its source."""
    selected, origins, operations, all_assets, all_rules, cleanups, errors = {}, {}, {}, {}, {}, [], []
    snapshots = []
    for run in sorted(runs, key=lambda r: (r.get("created_at", ""), r["id"])):
        root = store.project_dir(owner, project["id"]) / "runs" / run["id"]
        if not (root / "result.json").is_file() or not (root / "bundle.json").is_file():
            return None, "部分关联执行的证据文件不可用，未生成可能遗漏结果的合并统计。"
        result, bundle = store._read(root / "result.json"), store._read(root / "bundle.json")
        if snapshots and result.get("environment") != snapshots[0][0].get("environment"):
            return None, "关联执行使用了不同环境，请分别查看原始执行；不同环境的同名用例不相互覆盖。"
        for key, op in bundle.get("contract", {}).get("operations", {}).items():
            identity = {field: op.get(field, "") for field in ("method", "path")}
            if key in operations and operations[key] != identity:
                return None, "关联执行的接口标识发生变化，请分别查看原始执行，避免混合不同接口的结果。"
            operations[key] = identity
        assets = {case["id"]: case for case in bundle.get("cases", [])}
        for index, case in enumerate(result.get("cases", [])):
            selected[case["id"]] = case
            all_assets[case["id"]] = assets.get(case["id"], {"id": case["id"]})
            origins[case["id"]] = {"id": run["id"], "index": index, "result": result, "bundle": bundle,
                "base": f'/api/projects/{project["id"]}/reports/{run["id"]}'}
        cleanups.append({**result.get("cleanup", {}), "run_id": run["id"],
                         "failed_case_cleanups": [c["id"] for c in result.get("cases", []) if c.get("cleanup", {}).get("status") == "FAIL"]})
        errors.extend(result.get("validation_errors", []))
        snapshots.append((result, bundle))
    cases = list(selected.values())
    for case in cases:
        original = origins[case["id"]]["bundle"]
        referenced = set(case.get("rule_ids", [])) | {
            assertion.get("rule_id") for step in case.get("steps", []) for assertion in step.get("assertions", [])}
        for rule in original.get("rules", []):
            if rule["id"] not in referenced:
                continue
            sources = original.get("contract", {}).get("sources", {})
            # Identical snapshots across retries are one rule; changed source
            # contents stay distinct even when the rule ID is reused.
            signature = json.dumps([rule, {sid: sources.get(sid) for sid in rule.get("source_ids", [])}], sort_keys=True)
            all_rules[signature] = rule
    summary = dict(Counter(c.get("status", "BROKEN") for c in cases))
    summary.update(total=len(cases), complete=bool(cases) and all(c.get("status") in {"PASS", "FAIL"} for c in cases))
    cleanup_status = ("FAIL" if any(c.get("status") == "FAIL" or c["failed_case_cleanups"] for c in cleanups) else
                      "PASS" if all(c.get("status") == "PASS" for c in cleanups) else "NOT_CONFIGURED")
    result = {"cases": cases, "summary": summary, "environment": snapshots[0][0].get("environment", {}),
              "run_id": "多轮执行汇总（各轮证据见用例与执行记录）", "started_at": snapshots[0][0].get("started_at", ""),
              "finished_at": snapshots[-1][0].get("finished_at", ""),
              "requests_sent": sum(r.get("requests_sent", 0) for r, _ in snapshots),
              "cleanup": {"status": cleanup_status, "runs": cleanups}, "validation_errors": errors}
    # Only overview metadata is combined. Each case reads rules, sources and draft
    # identity from its original snapshot, so reused rule IDs cannot corrupt evidence.
    bundle = {"contract": {"operations": operations}, "cases": list(all_assets.values()),
              "rules": [{"id": str(index)} for index, _ in enumerate(all_rules)],
              "generation": {"engine": "saved-execution-summary"}}
    if any(b.get("web", {}).get("experience") for _, b in snapshots):
        bundle["web"] = {"experience": True}
    return (result, bundle, origins), None


def render_saved_task_report(store, owner, project, report):
    """Reuse execution evidence layout, including for reports saved before this renderer."""
    known = {run["id"]: run for run in project.get("runs", [])}
    if any(r.get("id") not in known for r in report.get("runs", [])):
        return render_task_report(report).replace('<section class="summary">',
            '<section class="summary"><p>部分关联执行记录不可用，未生成可能遗漏结果的合并统计。</p>', 1)
    runs = [known[r["id"]] for r in report.get("runs", []) if r.get("id") in known]
    if not runs:
        return render_task_report(report)
    merged, unavailable = _merge_run_evidence(store, owner, project, runs)
    if unavailable:
        return render_task_report(report).replace('<section class="summary">',
            '<section class="summary"><p>' + html.escape(unavailable) + '</p>', 1)
    result, bundle, origins = merged
    page = render_report({**result, "title": report["title"]}, bundle, case_sources=origins)
    page = page.replace('<a href="bundle.json">冻结用例 JSON</a> · <a href="result.json">执行证据 JSON</a>',
                        '<a href="report.json">关联执行清单 JSON</a> · <a href="#codex-analysis">查看各轮执行记录</a>')
    page = page.replace('本轮用例', '去重用例').replace('本轮资产', '汇总范围')
    page = page.replace('本轮全部通过', '当前汇总全部通过').replace('本轮包含未通过或未执行用例', '当前汇总包含未通过或未执行用例')
    page = page.replace('依据文档与规则生成，未调用模型 API。', '从保存的执行记录汇总；生成方式见各轮冻结用例。')
    report_back = '<a class="report-back" href="/api-testing">← 返回测试台</a>'
    report_nav = ('<nav class="report-nav">' + report_back +
                  '<a href="#codex-analysis">查看分析结论 ↓</a></nav>')
    page = page.replace(report_back, report_nav, 1)
    if len(runs) > 1:
        notice = ('<section class="panel"><h2>多轮执行合并结果</h2>'
                  f'<p>汇总 {len(runs)} 轮执行，按用例 ID 合并，同一用例采用最新结果。请求数包含所有轮次与重试；'
                  '用例数不重复累计。每条用例保留结果来源，各轮历史失败与清理证据可独立查看。</p></section>')
        page = page.replace('<main>', '<main>' + notice, 1)
    inventory = report.get("case_inventory")
    if inventory:
        inventory_notice = (f'<section class="panel"><h2>完整设计与执行范围</h2>'
            f'<p>本报告保存 <b>{inventory["total"]}</b> 条具体设计；当前关联执行汇总 <b>{len(result["cases"])}</b> 个用例 ID。'
            '下方结果只统计关联执行，未执行设计的条件保留在完整设计清单和分析结论中。</p>'
            f'<a href="{html.escape(str(inventory["report_url"]), quote=True)}">查看完整设计与未执行条件 →</a></section>')
        page = page.replace('<main>', '<main>' + inventory_notice, 1)
    analysis = render_task_report(report).split('<section class="summary">', 1)[1].split('</main>', 1)[0]
    analysis = '<section class="panel summary">' + analysis
    analysis = analysis.replace('<section>', '<section class="panel">').replace('<article>', '<article class="panel">')
    appendix = '<div id="codex-analysis" class="codex-analysis"><h2>Codex 分析与建议</h2>' + analysis + '</div>'
    page = page.replace('</main>', appendix + '</main>', 1)
    css = '<style>.report-nav{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px}.report-nav .report-back{margin-bottom:0}.codex-analysis{margin-top:32px}.codex-analysis>.panel{margin:18px 0}.codex-analysis .prose{white-space:pre-wrap;overflow-wrap:anywhere;margin:14px 0}</style>'
    return page.replace('</head>', css + '</head>', 1)


def render_task_report(report):
    e = lambda value: html.escape(str(value), quote=True)
    ui_test = report.get("test_kind") == "ui"
    back_url = "/ui-testing" if ui_test else "/api-testing"
    report_label = "UI 测试报告" if ui_test else ('执行与分析报告' if report['runs'] else '分析报告')
    source_label = (f"来源文件：{e(report['imported_results']['filename'])}" if report.get("imported_results") else
                    f"目标页面：{e(report.get('target_url', ''))}" if ui_test
                    else f"{e(report['document']['filename'])} · {e(report['created_at'])}")
    # Compatibility guard for reports created before the appendix was removed.
    sections = ''.join(
        f'<section><h2>{e(section["title"])}</h2><div class="prose">{_section_content_html(section["content"])}</div></section>'
        for section in report.get('sections', [])
        if not _is_removed_report_section(section.get("title", ""))
    )
    findings = ''.join('<article><div class="tag">'+e(f['severity'] or '检查发现')+'</div><h3>'+e(f['title'])+'</h3>'+
        ''.join(f'<div class="prose"><b>{label}</b>\n{e(f[key])}</div>' for key, label in (
            ('detail','说明'),('evidence','依据'),('recommendation','建议')) if f[key])+
        draft_panel(f'finding-{i}', '问题描述', finding_draft(report, f))+'</article>' for i, f in enumerate(report['findings']))
    if ui_test:
        from .ui_records import evidence_html
        regression = {item.get('draft_id'): item for item in report.get('regression_links', [])}
        def draft_source_attributes(finding):
            source = finding.get('draft_source') or {}
            if report.get('report_type') != 'total' or not source:
                return ''
            return (f' data-pingcode-project="{e(source["project_id"])}"'
                    f' data-pingcode-report="{e(source["report_id"])}"'
                    f' data-pingcode-draft="{e(source["draft_id"])}"')
        findings = ''.join('<article' + draft_source_attributes(f) + ' class="compact-finding" data-case-id="'+e(f.get('case_id', ''))+'" data-regression-status="'+e(regression.get(f'finding-{i}', {}).get('outcome', ''))+'">' +
            draft_panel(f'finding-{i}', f['title'], finding_draft(report, f), compact=True) +
            evidence_html(report, f.get('evidence_case_id') or f.get('case_id', '')) +
            '</article>' for i, f in enumerate(report['findings']))
    runs = ''.join(f'<li><a href="{e(r["report_url"])}">{e(r["environment"]["name"])} · {e(r["created_at"])}</a>'
        f' — {r["requests_sent"]} 次请求，{r["summary"].get("PASS",0)} 条通过，{r["summary"].get("FAIL",0)} 条失败，'
        f'{r["summary"].get("BROKEN",0)} 条执行异常</li>' for r in report['runs'])
    inventory = report.get("case_inventory")
    design_link = (f'<p>已保存 {inventory["total"]} 条具体设计；其中 {inventory["ready"]} 条已采纳可执行（不代表已经执行）。'
                   f'<a href="{e(inventory["report_url"])}">查看本报告对应的完整用例设计 →</a></p>') if inventory else ''
    evidence = (('关联以下已保存的执行记录：<ul>'+runs+'</ul>') if runs else
                f'结果来自导入的 XLSX 文件“{e(report["imported_results"]["filename"])}”；平台未重新执行这些用例。'
                if report.get("imported_results") else
                '本报告汇总 UI 测试分析与记录；实际执行范围、复现步骤和证据以报告正文及检查发现为准。'
                if ui_test else '本报告为文档分析或任务检查结论，未关联接口执行记录；分析结果不代表接口测试通过。')
    imported = report.get("imported_results")
    imported_html = ""
    if imported:
        status_labels = {"passed": "通过", "failed": "失败", "blocked": "阻塞", "not_run": "未执行",
                         "skipped": "跳过", "other": "其他", "partial": "验证未完成", "pending_rule": "待确认规则",
                         "pending_action": "待用户确认"}
        counts = imported.get("counts", {})
        cards = ''.join(f'<span class="result-count result-{e(key)}"><b>{e(counts.get(key, 0))}</b>{e(label)}</span>'
                        for key, label in status_labels.items() if counts.get(key, 0))
        imported_html = (f'<header class="report-overview"><div class="overview-title"><a href="{back_url}">← 返回测试台</a>'
                         f'<h1>{e(report["title"])}</h1></div><div class="result-counts" aria-label="结果总结">'
                         f'<span class="muted">共 {e(counts.get("total", 0))} 条</span>{cards}</div>'
                         '<a href="cases.html">用例与数据</a> · <a href="cases.xlsx">导出 XLSX</a></header>')
    findings_heading = "可提交缺陷" if imported else "检查发现"
    findings_html = (f'<h2>{findings_heading}</h2>{findings}' if findings else
                     '<section><h2>可提交缺陷</h2><p>本次没有失败用例，无需提交缺陷。</p></section>' if imported else '')
    report_content = (f'{imported_html}{findings_html}' if imported else
                      f'<section class="summary"><h2>任务结论</h2><p class="muted">任务目标：{e(report["goal"])}</p>'
                      f'<div class="prose">{e(report["summary"])}</div>{design_link}</section>{sections}{findings_html}'
                      f'<section><h2>执行证据</h2><p>{evidence}</p><p><a href="report.json" download>下载报告 JSON</a></p></section>')
    if report.get('aggregate') or report.get('round_project_id'):
        report_content += sections
    if report.get('ui_snapshot'):
        from .ui_records import requirements_html, blocking_html, superseded_html
        report_content += requirements_html(report) + blocking_html(report) + superseded_html(report)
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(report['title'])}</title><style>
body{{font:15px/1.8 system-ui,"Microsoft YaHei",sans-serif;background:#f5f7fb;color:#202e46;margin:0}}main{{max-width:1120px;margin:40px auto;padding:0 24px}}header,section,article{{background:white;border:1px solid #e0e6f0;border-radius:12px;padding:26px;margin:18px 0}}h1{{font-size:30px;line-height:1.4}}h2{{font-size:20px}}h3{{font-size:17px}}.muted{{color:#758196;font-size:13px}}.prose{{white-space:pre-wrap;overflow-wrap:anywhere;margin:14px 0}}a{{color:#365ee9}}.tag{{color:#365ee9;font-size:12px}}.summary{{border-left:4px solid #365ee9}}.facts{{display:flex;gap:24px;flex-wrap:wrap}}.facts b{{font-size:23px;color:#365ee9}}code{{overflow-wrap:anywhere}}.result-counts{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 0}}.result-count{{display:flex;gap:7px;align-items:baseline;padding:8px 12px;border-radius:9px;background:#edf1f8}}.result-count b{{font-size:19px}}.result-failed,.result-blocked{{color:#b42318;background:#fff0ed}}.result-passed{{color:#13795b;background:#ecfdf3}}@media(max-width:600px){{main{{padding:0 12px}}header,section,article{{padding:18px}}}}{DRAFT_CSS}
{REPORT_THEME_CSS}
body > main > article.compact-finding{{padding:14px 18px;margin:10px 0;border-radius:10px}}
body .compact-finding .compact-draft{{padding:0;margin:0;border:0;background:transparent;box-shadow:none;backdrop-filter:none}}
.compact-draft .draft-actions{{gap:8px}}.compact-draft .draft-actions strong{{flex:1;min-width:220px;font-size:14px;line-height:1.5}}
.compact-draft .draft-preview{{margin-top:6px}}.compact-draft .draft-preview textarea{{min-height:220px;margin-top:8px}}
body .compact-draft .draft-actions button{{padding:6px 10px;min-height:32px}}
body.compact-report main{{margin:22px auto}}
body.compact-report > main > header.report-overview{{padding:14px 18px;margin:0 0 12px;border-radius:10px}}
.overview-title{{display:flex;align-items:center;gap:20px;flex-wrap:wrap}}.overview-title a{{font-size:13px}}.overview-title h1{{font-size:20px;line-height:1.4;margin:0}}
.report-overview .result-counts{{align-items:center;gap:8px;margin:10px 0 0}}.report-overview .result-count{{padding:3px 9px;font-size:13px;border-radius:6px}}.report-overview .result-count b{{font-size:15px}}
body.compact-report main > h2{{font-size:15px;margin:14px 0 8px}}
body.compact-report .pc-batch-toolbar{{position:static;padding:8px 14px;margin:10px 0;gap:12px;border-radius:9px;font-size:13px}}
body.compact-report .pc-batch-toolbar button{{padding:6px 10px;min-height:32px}}
body .pc-batch-toolbar[hidden],body .pc-select-label[hidden]{{display:none}}
</style></head><body class="{'compact-report' if imported else ''}"><main>
{'' if imported else f'''
<header><a href="{back_url}">← 返回测试台</a><div class="tag">CODEX · {report_label}</div><h1>{e(report['title'])}</h1><p class="muted">{source_label}</p><div class="facts"><span><b>{len(report['findings'])}</b> {'项可提交缺陷' if imported else '项检查发现'}</span>{'' if ui_test else f'<span><b>{len(report["runs"])}</b> 份执行记录</span><span><b>{report["requests_sent"]}</b> 次关联请求</span>'}</div></header>
'''}
{report_content}{'' if imported else f'<footer class="muted">{"目标记录" if ui_test else "原文"} SHA-256：<code>{e(report["document"]["sha256"])}</code> · 报告内容由 Codex 整理。</footer>'}</main><script>{DRAFT_SCRIPT}</script></body></html>'''
