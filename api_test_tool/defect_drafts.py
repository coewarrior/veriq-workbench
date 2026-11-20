"""Copyable issue drafts derived from recorded evidence, without model calls."""
from __future__ import annotations

import html
import json
import re
from urllib.parse import urlsplit

from .execution import Redactor


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def _clean_text(redactor, text):
    # The shared free-text redactor removes quotes around credential values.
    # Keep JSON snippets pasteable while retaining the redacted placeholder.
    return re.sub(r'("[^"\n]+"\s*:\s*)<redacted>(?=\s*[,}\n])',
                  r'\1"<redacted>"', redactor.clean(text))


def case_defect_draft(result, bundle, case, title=None):
    """Return (heading, text), or None when no failure was actually recorded."""
    cleanup_failed = case.get("cleanup", {}).get("status") == "FAIL"
    status = case.get("status")
    if status not in {"FAIL", "BROKEN"} and not cleanup_failed:
        return None
    asset = next((c for c in bundle.get("cases", []) if c["id"] == case["id"]), {})
    # Redact structured values before serializing. A regex over the final JSON
    # text would consume opening braces in fields such as password variables.
    redactor = Redactor()
    redactor.remember([asset, case])
    case = redactor.clean(case)
    asset = redactor.snapshot(asset)
    result = redactor.clean({"environment": result.get("environment") or {},
                             "started_at": result.get("started_at") or "未记录"})
    normal_steps = case.get("steps", [])
    steps = normal_steps + (case.get("cleanup", {}).get("steps", []) if cleanup_failed else [])
    step_assets = {s["id"]: s for s in asset.get("steps", []) + asset.get("cleanup_steps", [])}
    bad_steps = [s for s in steps if s.get("status") in {"FAIL", "BROKEN"}]
    first_bad = bad_steps[0] if bad_steps else {}
    request = first_bad.get("request", {})
    path = urlsplit(request.get("url", "")).path
    endpoint = " ".join(filter(None, [request.get("method"), path]))
    title = redactor.clean(title or case.get("title", case["id"]))
    if status == "FAIL":
        heading, category = "接口缺陷描述", "接口断言未通过"
        conclusion = "已记录本次请求与预期的差异；复现次数、业务影响和根因未进一步验证。"
    elif status == "BROKEN":
        heading, category = "执行异常描述", "接口执行异常，原因待确认"
        conclusion = "本次执行异常，尚不能据此认定接口功能缺陷；需结合下方错误和响应定位。"
    else:
        heading, category = "清理异常描述", "测试数据清理失败"
        conclusion = "异常发生在数据清理阶段，不能据此判定业务断言失败。"
    # A scenario title already describes the issue; keep transport/status metadata
    # in the body instead of presenting it as another issue in the title.
    is_demo = bool(bundle.get('web', {}).get('experience')) or title.startswith('【演示】')
    title = re.sub(r'^(?:【演示】\s*)+', '', title).strip()
    issue_title = title if status == "FAIL" else f"{category}：{title}"
    if not title or title == case["id"]:
        issue_title = f"{category}：{endpoint or case['id']}"
    if is_demo:
        issue_title = '【演示】' + issue_title
    lines = [f"【标题】{issue_title}",
             "", "【问题定位】", f"问题类型：{category}", f"接口：{endpoint or '未记录'}",
             "", "【测试环境】", f"环境：{result.get('environment', {}).get('name', '未记录')}",
             f"服务地址：{result.get('environment', {}).get('base_url', '未记录')}",
             f"执行时间：{result.get('started_at', '未记录')}",
             "", "【前置条件】",
             "在上述测试环境按以下顺序执行；请求参数以本次记录为准。"]
    if bundle.get('web', {}).get('experience'):
        lines[1:1] = ['', '【演示说明】', '本缺陷由专用演示服务注入可控故障产生，包含真实 HTTP 执行证据，不代表业务系统存在此缺陷。用于人工审核与 PingCode 提交体验。临时服务已销毁，请重新点击「体验完整流程」复测；不要直接请求历史地址。']
    for name, value in asset.get("variables", {}).items():
        if isinstance(value, dict) and value.get("kind") == "unique":
            lines.append(f"{name}：每次使用新生成的测试值（前缀 {value.get('prefix', '')}）。")
    lines.extend(["动态资源 ID 和登录凭证使用本次前序响应的新值，不能直接复用历史值。",
                  "凭证如标为 <redacted>，复现时填入有效的测试凭证。", "", "【复现步骤与请求】"])
    if not steps:
        lines.append("未记录请求步骤，无法从当前报告还原请求。")
    for index, step in enumerate(steps, 1):
        definition = step_assets.get(step.get("id"), {})
        req = step.get("request", {})
        cleanup_step = index > len(normal_steps)
        label = definition.get("title", step.get("id", "未命名步骤"))
        lines.append(f"{index}. {'[清理] ' if cleanup_step else ''}{label}")
        if not req:
            lines.append("未发送请求；" + (step.get("error") or "没有请求记录。"))
            continue
        lines.append(f"{req.get('method', '未记录方法')} {req.get('url', '未记录地址')}")
        lines.append("请求头：" + _json(req.get("headers", {})))
        lines.append("请求体：" + _json(req.get("body")))
        if definition.get("request", {}).get("session", True):
            lines.append("沿用本用例前序步骤的会话 Cookie（若有）。")
        else:
            lines.append("本步骤不沿用前序步骤的会话 Cookie。")
        if definition.get("extract"):
            lines.extend(["后续步骤使用的响应变量：", _json(definition["extract"])])
    expected, actual = [], []
    for step in bad_steps:
        definition = step_assets.get(step.get("id"), {})
        label = definition.get("title", step.get("id", "未命名步骤"))
        definitions = definition.get("assertions", [])
        for index, assertion in enumerate(step.get("assertions", [])):
            if assertion.get("passed") is not False:
                continue
            source = definitions[index] if index < len(definitions) else {}
            kind = assertion.get("kind", "断言")
            names = {"status": "HTTP 状态码", "json_equal": "响应字段值", "json_exists": "响应字段存在",
                     "json_schema": "响应结构", "response_schema": "状态与响应分支", "header_equal": "响应头", "cookie_present": "Cookie 存在",
                     "equals_variable": "响应值与变量一致"}
            target = source.get("pointer") or source.get("name") or ""
            prefix = f"{label} / {names.get(kind, kind)}{' ' + target if target else ''}"
            expected.append(f"- {prefix}：{_json(assertion.get('expected'))}")
            actual.append(f"- {prefix}：{_json(assertion.get('actual'))}")
            if assertion.get("message") and assertion["message"] != "Actual value does not match the documented expectation":
                actual.append("  断言说明：" + assertion["message"])
        if step.get("error"):
            actual.append(f"- {label}：{step['error']}")
        if step.get("response"):
            actual.extend([f"{label} 的响应（已脱敏）：", _json(step["response"])])
        else:
            actual.append(f"{label}：未取得有效响应记录。")
    lines.extend(["", "【预期结果】", "\n".join(expected) or
                  ("测试完成后清理本次创建的数据。" if cleanup_failed and status not in {"FAIL", "BROKEN"} else "本次记录缺少具体预期，请补充后提交。"),
                  "", "【实际结果】", "\n".join(actual) or case.get("reason") or "仅记录了失败状态，缺少具体响应证据。"])
    if cleanup_failed:
        lines.extend(["清理结果（已脱敏）：", _json(case["cleanup"])])
    if status != "FAIL":
        lines.extend(["", "【说明】", conclusion])
    return heading, "\n".join(lines)


def finding_test_environment(report, finding):
    if finding.get('test_environment'):
        return finding['test_environment']
    cases = report.get('ui_snapshot', {}).get('cases', []) or report.get('imported_results', {}).get('cases', [])
    case = next((c for c in cases if c.get('case_id') and c.get('case_id') == finding.get('case_id')), {})
    if case.get('test_environment'):
        return case['test_environment']
    # Old reports stored browser/device details under client or method.
    for source in (case, finding):
        for key in ('client', 'method'):
            value = source.get(key, '')
            if re.search(r'macOS|Windows|Linux|Chrome|Safari|Firefox|Edge|Android|iOS|浏览器|桌面|真机', value, re.I):
                return value
    return '未记录，可补充系统、浏览器及设备信息'


def finding_analysis_sections(report, finding):
    # Older findings did not copy analysis fields; recover them by stable case ID.
    case = next((c for c in report.get('imported_results', {}).get('cases', [])
                 if c.get('case_id') and c.get('case_id') == finding.get('case_id')), None)
    if case and case.get('wording_corrected_at'):
        values = ('用例说明已更正，需依据更正后的记录重新解读。',
                  '用例说明已更正，原优化建议需重新核对。')
    else:
        source = case if case is not None else finding
        values = (source.get('ai_analysis') or '尚未记录 AI 解读。',
                  source.get('recommendation') or '尚未记录针对该问题的优化建议。')
    return [part for name, value in zip(('AI 解读', '建议优化'), values)
            for part in ('', f'【{name}】', value)]


def finding_requirement_basis(report, finding):
    """Recover recorded sources by case ID, including reports predating this field."""
    for group in ('imported_results', 'ui_snapshot'):
        case = next((c for c in report.get(group, {}).get('cases', [])
                     if c.get('case_id') and c.get('case_id') == finding.get('case_id')), {})
        basis = case.get('rule_basis') or case.get('code_basis')
        if basis:
            return basis
    return finding.get('rule_basis') or '未记录 PRD 原文引用；需核对原文及出处，当前预期结果不能替代原文依据。'


def finding_draft(report, finding):
    if report.get("imported_results"):
        return _clean_text(Redactor(), "\n".join([
            "【测试环境】", finding_test_environment(report, finding), "",
            "【前置条件】", finding.get("precondition") or "无",
            "", "【测试数据】", finding.get("test_data") or "未填写",
            "", "【测试步骤】", finding.get("steps") or "未填写",
            "", "【预期结果】", finding.get("expected") or "未填写",
            "", "【需求依据】", finding_requirement_basis(report, finding),
            "", "【实际结果】", finding.get("actual") or finding.get("evidence") or "未填写",
        ] + finding_analysis_sections(report, finding)))
    target = (f"测试页面：{report.get('target_url', '')}" if report.get("test_kind") == "ui"
              else f"接口文档：{report['document']['filename']}")
    lines = [f"【标题】{finding['title']}", "", "【检查对象】",
             target, f"检查时间：{report['created_at']}",
             "", "【问题描述】", finding.get("detail") or "未补充说明。",
             "", "【依据与复核线索】", finding.get("evidence") or "未补充依据。",
             *(finding_analysis_sections(report, finding) if report.get("test_kind") == "ui" else
               ["", "【建议处理】", finding.get("recommendation") or "请结合文档约定和实际接口行为核对。"]),
             "", "【范围说明】", "此描述来自报告中的检查发现；未记录的接口请求、响应及复现次数不作推定。"]
    if report.get('test_kind') == 'ui':
        lines.extend(['', '【测试环境】', finding_test_environment(report, finding),
                      '', '【需求依据】', finding_requirement_basis(report, finding)])
    return _clean_text(Redactor(), "\n".join(lines))


def draft_panel(identifier, title, text, compact=False):
    e = lambda value: html.escape(str(value), quote=True)
    if compact:
        return (f'<div class="defect-draft compact-draft"><div class="draft-actions"><strong>{e(title)}</strong>'
                f'<button type="button" class="copy-defect" data-draft="{e(identifier)}">复制问题描述</button>'
                '<span class="copy-status" role="status" aria-live="polite"></span></div>'
                '<details class="draft-preview"><summary>查看 / 编辑问题描述</summary>'
                f'<textarea id="{e(identifier)}" aria-label="问题描述" spellcheck="false">{e(text)}</textarea>'
                '</details></div>')
    return (f'<div class="defect-draft"><div class="draft-actions"><strong>{e(title)}</strong>'
            f'<button type="button" class="copy-defect" data-draft="{e(identifier)}">复制{e(title)}</button>'
            '<span class="copy-status" role="status" aria-live="polite"></span></div>'
            '<details class="draft-preview"><summary>预览并编辑描述</summary>'
            f'<textarea id="{e(identifier)}" aria-label="{e(title)}" spellcheck="false">{e(text)}</textarea>'
            '<p>可直接复制到缺陷系统；编辑只影响本页草稿，原始执行证据保持不变。</p></details></div>')


DRAFT_CSS = '''
.defect-draft{margin:0 22px 18px;border:1px solid #e3cdd5;border-radius:9px;padding:14px 16px;background:#fff9fa;font-size:13px}
.draft-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.draft-actions strong{margin-right:auto}
.copy-defect{border:1px solid #365ee9;border-radius:7px;padding:8px 12px;background:#365ee9;color:white;font:inherit;cursor:pointer}
.copy-defect:focus-visible{outline:3px solid #92a8ff;outline-offset:2px}.copy-defect:disabled{opacity:.6;cursor:wait}
.copy-status{color:#536580;font-size:12px}.draft-preview{margin-top:10px}.draft-preview summary{cursor:pointer;color:#365ee9}
.draft-preview textarea{display:block;width:100%;min-height:300px;max-height:650px;resize:vertical;box-sizing:border-box;border:1px solid #d3dceb;border-radius:6px;margin-top:12px;padding:12px;background:white;color:#202e46;font:13px/1.7 ui-monospace,monospace}
.draft-preview p{margin:8px 0 0;color:#65738b;font-size:12px}@media(max-width:600px){.defect-draft{margin:0 12px 14px;padding:12px}.draft-actions strong{width:100%}}@media print{.copy-defect,.copy-status{display:none}}
'''

DRAFT_SCRIPT = '''
document.querySelectorAll('.copy-defect').forEach(button=>button.addEventListener('click',async()=>{
  const field=document.getElementById(button.dataset.draft),status=button.parentElement.querySelector('.copy-status');
  if(button.copyStatusTimer){clearTimeout(button.copyStatusTimer);button.copyStatusTimer=null}
  button.disabled=true;status.textContent='正在复制…';
  let copied=false;
  try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(field.value);copied=true}}catch(error){}
  if(!copied){
    const helper=document.createElement('textarea');helper.value=field.value;helper.setAttribute('aria-label','复制临时文本');
    helper.style.cssText='position:fixed;left:0;top:0;width:1px;height:1px;opacity:0';document.body.appendChild(helper);
    try{helper.focus();helper.select();copied=document.execCommand('copy')}catch(error){}finally{helper.remove()}
  }
  button.disabled=false;
  if(copied){
    status.textContent='已复制，可粘贴提交';button.focus();
    button.copyStatusTimer=setTimeout(()=>{status.textContent='';button.copyStatusTimer=null},2000)
  }
  else{field.closest('details').open=true;field.focus();field.select();status.textContent='未能自动复制，已选中文字，请按 Ctrl+C / ⌘C'}
}));
'''
