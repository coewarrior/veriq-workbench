"""UI case inventories, incremental task reports and step-owned evidence."""
from __future__ import annotations

from copy import deepcopy
from .ui_case_results import active_cases, is_superseded, validate_supersession, active_coverage_refs

import base64
import hashlib
import html
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

from .execution import Redactor
from .defect_results import current_outcome, round_id, prior_failure
from .report_reads import _ReportBatch
from .xlsx_results import result_findings
from .ui_xlsx import priority_label
from .defect_title import attributes, AI_TITLE_GUIDANCE
from . import ui_dependencies, ui_uploads, ui_experiments, ui_action_context
from .ui_payload_validation import require_ui_payload_shape

LABELS = {'passed': '通过', 'failed': '不通过', 'partial': '验证未完成', 'blocked': '阻塞',
          'not_run': '未执行', 'pending_rule': '待确认规则', 'pending_action': '待用户确认'}
FIELDS = ('case_id', 'scenario', 'module', 'environment', 'client', 'test_environment', 'priority', 'executor',
          'precondition', 'test_data', 'steps', 'expected', 'actual', 'conclusion', 'ai_analysis', 'cause_analysis', 'recommendation', 'status', 'not_run_reason', 'account_scope', 'rule_basis', 'method', 'cleanup', 'executed_at',
          'action_type', 'action_required')
FIXTURE_REFERENCE_FIELDS = ('precondition', 'test_data', 'steps', 'rule_basis', 'method')
MAX_FIXTURE_BYTES = 100 * 1024 * 1024
ASSET_BYTE_LIMITS = {'fixture': MAX_FIXTURE_BYTES, 'screenshot': 10 * 1024 * 1024,
                     'video': 20 * 1024 * 1024, 'observation': 10 * 1024 * 1024}
ACTION_TYPES = {'authorization', 'manual_step'}
REPRODUCTION_GUIDANCE = (
    '测试步骤必须让未参与测试的开发独立复现。steps 用编号逐行写出真实入口 URL、页面导航、'
    '控件名称及位置、操作、完整输入或明确的测试数据引用、等待的可观察状态和异常观察位置；'
    '一步一个主要动作，按实际先后顺序写到故障触发点，不用“进入受控状态”“核对相关结果”等概括代替操作。'
    '“沿用已登录账号”“当前测试账号已登录”只能作为补充前置，不能代替测试步骤；步骤必须写目标 URL、如何确认账号/登录状态、'
    '点击或选择的具体控件和对象、等待页面完成的可观察标志，以及在哪个区域读取结果。选择、刷新、核对必须拆成独立编号。'
    '如果原始记录没有保存按钮名、控件位置、账号显示标识或对象名称，明确写“原始记录未保存该信息”，不要凭经验补写。'
    'precondition 只写本缺陷实际依赖的账号角色、权限、数据和初态，并说明如何准备或确认；'
    'test_data 写具体对象、名称、输入值和可访问的文件，凭据脱敏，不用“同上”或“本轮数据”代替。'
    '键盘问题写明触发控件、起始焦点、已记录的按键顺序和关闭方式、关闭后的焦点观察方法；'
    'AI 对话问题保留实际发送的完整原文及必要上下文。预期与实际分栏，对应具体步骤。'
    '失败用例发布前依据操作记录、截图和输入逐条回查；故障后的绕行、恢复和复测写入 actual，'
    '不要混入首次复现步骤。未执行分支、未知按键或按钮名、未记录原话及历史初态明确标为缺口，'
    '不能把建议操作冒充实测。无固定步数或字数要求；详细程度以可独立操作为准。'
    '更正历史报告通过审计更正层，保留原始证据与真实状态；不为补写步骤自行重跑业务或推送缺陷。'
)
REQUIREMENT_BASIS_GUIDANCE = '对照 PRD 判断功能缺失、行为不符等问题时，rule_basis 应引用已读取的相关原句，并注明文档名称、版本（已知时）、章节/页码或可定位链接；原句与测试者解释分开写，说明它如何支持 expected。不要只写“复核原设计”或复制预期结果代替引用，不把代码、日志或观察现象冒充 PRD。未取得原文或原文未明确时如实注明，不能编造引文、出处或把推断说成需求。已有规则依据按原记录展示，不自动认定为已核实的 PRD 原文；不为补引用重跑测试。'

AI_ANALYSIS_GUIDANCE = (
    'ai_analysis 面向不懂测试术语的读者，用几句日常中文先说具体功能哪里成功或失败、'
    '对使用有什么影响，再说明已确认的事实和仍未验证的部分。'
    '失败发生在哪一步不等于已经找到根因；原因未查明就直说“具体原因还没查明”。'
    '不要用“夹具、断言、召回、注入、提交链路”等内部术语、工具名或用例编号代替解释；'
    '必要的错误码、工具名和关联编号留在详细记录。'
    '例如：文件格式检查通过，但平台在提交解析任务时失败，后面的搜索和问答没能继续验证。'
    '提交失败的具体原因还没查明。'
    '只说明实际观察，不编造原因、影响或恢复结果；修改执行结果后同步更新解读。'
    '此要求只改表达，不修改测试状态、判断标准、原始输入、错误信息或证据，'
    '也不是自动改写历史报告或阻止发布的规则。'
    '缺陷正文包含需求依据、ai_analysis（AI 解读）和 recommendation（建议优化）。'
    'AI 解读中说明原因，区分已确认事实、代码或日志依据、推测与未验证边界；未查明就说明未查明，不另设原因分析栏目。'
    '建议优化按条列出针对该问题的修复方向、交互改进和回归关注点；建议不代表已实现或验证。'
    '两项内容随缺陷正文展示、复制和提交，不新增按钮或模型调用，不为补分析擅自扩大排查范围。'
)
_LEGACY_CONFIRMATION = re.compile(r'(需|要|待|未).{0,12}(用户|人工).{0,12}(确认|点击)|(确认删除|永久删除).{0,24}(未点击|需确认|人工)', re.S)

_STEP_GENERIC = re.compile(r'^(?:进入(?:页面|系统)|检查结果|核对相关结果|按要求操作|执行操作|选择后刷新检查)[。；;：:，,、\s]*$', re.I)
_LOGIN_PRECONDITION = re.compile(r'(?:沿用|当前|已有|保持).{0,12}(?:已登录|登录账号|登录态|会话)|当前测试账号已登录', re.I)
_LOGIN_VERIFICATION = re.compile(r'(?:确认|检查|核对|验证).{0,20}(?:登录|账号|用户名|头像|账户|会话)', re.I)
_CONTROL_ACTION = re.compile(r'(?:点击|单击|双击|打开|进入|切换|选择|勾选|取消|清空|输入|粘贴|上传|下载|刷新|展开|收起|关闭|发送|提交|保存|删除|返回|滚动)', re.I)
_OBSERVATION = re.compile(r'(?:等待|显示|看到|核对|检查|观察|提示|保持|变为|出现|消失|字段|列表|弹窗|页面|结果|状态|内容)', re.I)


def reproduction_step_gaps(case):
    """Find missing facts that make UI steps impossible for a new tester/developer.

    This is an advisory diagnostic. It never invents a control name or changes the
    recorded execution; the caller can correct the saved text with real evidence.
    """
    steps = str(case.get('steps') or '').strip()
    precondition = str(case.get('precondition') or '')
    test_data = str(case.get('test_data') or '')
    lines = [line.strip(' -、') for line in re.split(r'\r?\n+', steps) if line.strip()]
    gaps = []
    urls = re.findall(r'https?://[^\s，。；；)）]+', precondition, flags=re.I)
    if not steps:
        return ['未记录测试步骤']
    if urls and not re.search(r'https?://', steps, re.I):
        gaps.append('步骤未写真实入口 URL；开发无法确认从哪个页面开始')
    if _LOGIN_PRECONDITION.search(precondition) and not _LOGIN_VERIFICATION.search(steps):
        gaps.append('前置条件提到已登录账号，但步骤未写如何确认登录账号或登录状态')
    if not any(_CONTROL_ACTION.search(line) for line in lines):
        gaps.append('步骤未写具体控件动作（例如点击哪个按钮、选择哪个列表项或输入什么值）')
    if not any(_OBSERVATION.search(line) for line in lines):
        gaps.append('步骤未写等待完成条件和观察位置（页面哪个区域、字段、提示或列表状态）')
    if any(_STEP_GENERIC.match(line) for line in lines):
        gaps.append('步骤含概括性短语，未说明具体入口、对象和操作')
    if re.search(r'选择[^\n。；]{0,30}刷新检查|刷新检查当前值|核对相关结果|沿用已登录账号', steps):
        gaps.append('步骤把多个动作合并成一句，需拆成选择、等待/刷新、核对三步并写明对象和观察位置')
    if test_data and not any(token in steps for token in re.findall(r'[\w\u4e00-\u9fff.-]{2,}', test_data)[:8]):
        gaps.append('测试数据未在步骤中明确指出实际对象或输入值')
    return list(dict.fromkeys(gaps))






def ui_project(store, owner, pid):
    project = store.get_project(owner, pid)
    if project.get('test_kind') != 'ui':
        raise ValueError('请选择 UI 测试会话')
    return project


def root_for(store, owner, pid, execution_id):
    ui_project(store, owner, pid)
    if not isinstance(execution_id, str) or not re.fullmatch(r'[a-f0-9-]{36}', execution_id):
        raise ValueError('执行记录 ID 无效')
    return store.project_dir(owner, pid) / 'ui-executions' / execution_id


def load(store, owner, pid, execution_id):
    record = store._read(root_for(store, owner, pid, execution_id) / 'cases.json')
    if record.get('report_id'):
        from .ui_report_corrections import load as load_corrections
        extra = load_corrections(store, owner, pid, record['report_id']).get('fixture_supplements', [])
        record['assets'] = list({a['id']: a for a in [*record['assets'], *extra]}.values())
    return record


def evidence_html(report, case_id):
    e = lambda value: html.escape(str(value), quote=True)
    assets = [a for a in report.get('ui_snapshot', {}).get('assets', []) if a['case_id'] == case_id]
    parts = []
    for asset in assets:
        url = e(asset.get('url') or 'asset-' + asset['id'])
        caption = e(asset['step'] + ' · ' + asset['captured_at'])
        if asset['kind'] == 'screenshot':
            parts.append(f'<button type="button" class="report-image-preview" data-image-src="{url}" aria-label="放大预览：{caption}"><img loading="lazy" src="{url}" alt="{caption}" style="max-width:220px;max-height:140px;margin:8px"></button>')
        elif asset['kind'] == 'video':
            parts.append(f'<details><summary>现场录屏 · {caption}</summary><video controls preload="none" src="{url}" style="max-width:100%"></video></details>')
        else:
            parts.append(f'<a href="{url}" download>{e(asset["filename"])}</a>')
    return ''.join(parts)


def fixture_reference_mismatches(record):
    """Return fixture assets whose exact filename is not owned by their case design."""
    cases = {case.get('case_id'): case for case in record.get('cases', [])}
    mismatches = []
    for asset in record.get('assets', []):
        if asset.get('kind') != 'fixture':
            continue
        case = cases.get(asset.get('case_id')) or {}
        filename = unicodedata.normalize('NFKC', str(asset.get('filename', ''))).casefold()
        references = '\n'.join(str(case.get(field, '')) for field in FIXTURE_REFERENCE_FIELDS)
        references = unicodedata.normalize('NFKC', references).casefold()
        if not filename or filename not in references:
            mismatches.append({'asset_id': asset.get('id', ''), 'case_id': asset.get('case_id', ''),
                               'filename': asset.get('filename', '')})
    return mismatches


def required_action(case):
    """Return structured user action, including narrow compatibility for old frozen reports."""
    from .testing_policy import case_excluded
    if case_excluded(case):
        return None
    point = next((p for p in case.get('checkpoints', []) if p.get('status') == 'pending_action'), None)
    if case.get('status') == 'pending_action' or point:
        action = {'type': 'manual_step' if point else case.get('action_type') or 'authorization',
                  'prompt': point.get('action_required') if point else case.get('action_required') or '请确认后继续本用例'}
        context = (point or {}).get('action_context') or case.get('action_context')
        if context:
            action['context'] = ui_action_context.normalize(context)
        if point:
            action['checkpoint_id'] = point['id']
        return action
    return None


def cases_with_actions(cases):
    result = []
    for case in cases:
        item = dict(case)
        from .testing_policy import case_excluded, annotate_unexecuted, POLICY_ID
        item['policy_excluded'] = case_excluded(item)
        if not item['policy_excluded'] and item.get('execution_disposition') == POLICY_ID:
            annotate_unexecuted(item)
            if item.get('execution_disposition') != POLICY_ID and item.get('result') == '不测':
                item['result'] = LABELS[item['status']]
        if item['policy_excluded']:
            item.pop('required_action', None)
        action = required_action(item)
        if action:
            item['required_action'] = action
        result.append(item)
    return result




def coverage_check(record):
    """Structural reminders for the agent, never a semantic score or a publishing gate."""
    cases = {c['case_id']: c for c in active_cases(record['cases'])}
    coverage = record.get('coverage', [])
    refs = active_coverage_refs(record)
    screenshot_cases = {asset.get('case_id') for asset in record.get('assets', [])
                        if asset.get('kind') == 'screenshot'}
    return {
        'ai_analysis_guidance': AI_ANALYSIS_GUIDANCE,
        'requirement_basis_guidance': REQUIREMENT_BASIS_GUIDANCE,
        'reproduction_guidance': REPRODUCTION_GUIDANCE,
        'reproduction_gaps': [{'case_id': cid, 'gaps': reproduction_step_gaps(c)}
                             for cid, c in cases.items() if reproduction_step_gaps(c)],
        'manual_action_guidance': ui_action_context.GUIDANCE,
        'manual_action_context_gaps': [cid for cid, c in cases.items()
                                       if (a := required_action(c)) and a['type'] == 'manual_step'
                                       and not any(a.get('context', {}).get(k) for k in ('page_url', 'tab_id'))],
        'upload_fallback_guidance': ui_uploads.GUIDANCE,
        'upload_fallback_gaps': [{'case_id': cid, 'missing_channels': missing}
                                 for cid, c in cases.items() if (missing := ui_uploads.missing_checks(c))],
        'missing_inventory': not coverage,
        'areas_without_cases': [a['coverage_id'] for a in coverage if not a['case_ids']],
        'unknown_case_ids': sorted(refs - cases.keys()),
        'cases_without_area': sorted(cases.keys() - refs),
        'design_gaps': [{'coverage_id': a['coverage_id'], 'gap': a['gap']} for a in coverage if a.get('gap')],
        'incomplete_designs': [{'case_id': cid, 'missing': missing} for cid, c in cases.items()
                               if (missing := [k for k in ('precondition', 'test_data', 'steps', 'expected') if not c.get(k)])],
        'not_run_without_reason': [cid for cid, c in cases.items()
                                   if c['status'] == 'not_run' and not c.get('not_run_reason')],
        'not_run_guidance': ui_dependencies.CASE_EXECUTION_GUIDANCE + '发布前为每条 not_run 填写 not_run_reason，说明本轮为何未执行。上轮通过需引用真实报告或轮次及用例编号，并说明本轮未选入回归的依据；上轮通过不等于本轮通过。无法核实时写具体缺口，不编造历史结论。基线设计阶段可暂空，不阻止保存或报告生成。',
        'remaining_cases': [{'case_id': cid, 'status': c['status']} for cid, c in cases.items()
                            if c['status'] not in {'passed', 'failed'}],
        # A reminder rather than a gate: crashes and unavailable capture channels
        # can be legitimate evidence limitations and must not block other work.
        'failed_without_screenshot': sorted(cid for cid, c in cases.items()
                                            if c['status'] == 'failed' and cid not in screenshot_cases),
        'fixture_reference_mismatches': fixture_reference_mismatches(record),
        'review_current': bool(record.get('review_notes')) and record.get('review_revision') == record['revision'],
        'guidance': '本字段仅提示结构缺口，不是语义覆盖评分或发布门槛。对照完整原资料、真实入口和 references/coverage-design.md 检查业务范围；用例数、通过率和已尝试比例不等于功能覆盖。缺少条件不删设计，未知规则不猜预期，真实缺口可以保留并发布。failed_without_screenshot 需补仍可取得的真实故障现场，无法取证说明原因，不重演已确定业务。',
    }


def merge_coverage(previous, incoming):
    if incoming is None:
        return previous
    if not isinstance(incoming, list) or len(incoming) > 200:
        raise ValueError('coverage 每批最多 200 项，可分批追加')
    merged = {a['coverage_id']: a for a in previous}
    seen = set()
    for area in incoming:
        if not isinstance(area, dict):
            raise ValueError('coverage 项必须是对象')
        item = {}
        for key in ('coverage_id', 'feature', 'entry', 'considerations', 'gap'):
            value = area.get(key, '')
            if not isinstance(value, str) or len(value) > 20000:
                raise ValueError('coverage 文本字段无效')
            item[key] = value.strip()
        if not item['coverage_id'] or not item['feature'] or item['coverage_id'] in seen:
            raise ValueError('填写 coverage_id 与 feature，同批 ID 不得重复')
        ids = area.get('case_ids', [])
        if not isinstance(ids, list) or any(not isinstance(cid, str) or not cid.strip() or len(cid) > 20000 for cid in ids):
            raise ValueError('coverage.case_ids 必须为用例 ID 数组')
        item['case_ids'] = list(dict.fromkeys(cid.strip() for cid in ids))
        seen.add(item['coverage_id'])
        merged[item['coverage_id']] = Redactor().snapshot(item)
    return list(merged.values())


def scene_outcome(value):
    if not isinstance(value, dict) or value.get('status') not in {'cleaned', 'retained', 'partial', 'unverified'}:
        raise ValueError('测试现场结果状态仅支持 cleaned/retained/partial/unverified')
    items = value.get('items', [])
    note = value.get('note', '')
    if not isinstance(items, list) or len(items) > 200 or not isinstance(note, str) or len(note) > 2000:
        raise ValueError('测试现场结果最多 200 项，说明最多 2000 字')
    checked = []
    for item in items:
        if not isinstance(item, dict) or item.get('state') not in {'retained', 'cleaned', 'unverified'}:
            raise ValueError('测试现场对象状态仅支持 retained/cleaned/unverified')
        fields = {key: item.get(key, '') for key in ('case_id', 'name', 'kind', 'reason')}
        if not fields['name'] or any(not isinstance(v, str) or len(v) > 500 for v in fields.values()):
            raise ValueError('测试现场对象需有名称，各字段最多 500 字')
        checked.append({**fields, 'state': item['state']})
    return Redactor().snapshot({'status': value['status'], 'items': checked, 'note': note.strip()})


def regression_design(cases):
    """Copy exact designs, never historical observations or completion evidence."""
    import copy
    result = []
    for original in cases:
        case = copy.deepcopy(original)
        for field in ('actual', 'evidence', 'executed_at', 'conclusion', 'ai_analysis',
                      'cause_analysis', 'recommendation', 'cleanup', 'action_type',
                      'action_required', 'not_run_reason', 'execution_disposition'):
            case[field] = ''
        case.update(status='not_run', required_action=None, blocked_by=[], upload_attempts=[], action_context={})
        for point in case.get('checkpoints', []):
            point.update(status='not_run', verification_mode='design', actual='',
                         action_required='', evidence=[], correlation={}, inherited_from={})
        result.append(case)
    return result


def save_cases(store, owner, pid, cases, execution_id='', revision=0, coverage=None, review_notes=None, scene_result=None, experiment=None, *, refresh_report=True, staged_assets=None, response='full', include_saved_design=False):
    with store._lock:
        return _save_cases(store, owner, pid, cases, execution_id, revision, coverage, review_notes, scene_result, experiment, refresh_report=refresh_report, staged_assets=staged_assets, response=response, include_saved_design=include_saved_design)


def _save_cases(store, owner, pid, cases, execution_id='', revision=0, coverage=None, review_notes=None, scene_result=None, experiment=None, *, refresh_report=True, staged_assets=None, response='full', include_saved_design=False):
    require_ui_payload_shape({'cases': cases, 'coverage': coverage, 'review_notes': review_notes})
    from . import test_checkpoints, requirement_design
    if response not in {'full', 'summary'}:
        raise ValueError('response 必须为 full 或 summary')
    if staged_assets is not None and (not isinstance(staged_assets, list)
            or any(not isinstance(asset, dict) for asset in staged_assets)):
        raise ValueError('证据必须是对象数组')
    project = ui_project(store, owner, pid)
    regression = project.get('regression_round') or {}
    if regression.get('scope') in {'failed','selected'} and isinstance(cases, list) and any(
            isinstance(case, dict) and case.get('case_id') not in regression.get('case_ids', []) for case in cases):
        raise ValueError('本轮仅回归选中的错误用例；必要前置步骤请记录在对应场景中')
    scope = (project.get('ui_retest_round') or {}).get('case_ids')
    resume = project.get('requirements_resume') or {}
    if resume.get('execution_id') == project.get('ui_execution_id'):
        scope = scope or resume.get('case_ids')
    if scope and isinstance(cases, list) and any(isinstance(c, dict) and c.get('case_id') not in scope for c in cases):
        raise ValueError('本轮仅补测选中的原用例；必要前置步骤请记录在对应场景中')
    if not isinstance(cases, list) or len(cases) > 200 or (not cases and not staged_assets and coverage is None and review_notes is None and scene_result is None and experiment is None):
        raise ValueError('每批保存最多 200 条用例，可分批追加；也可单独保存覆盖清单、回查、现场收尾或实验记录')
    if not execution_id and project.get('ui_execution_id'):
        execution_id = project['ui_execution_id']
        if revision == 0:
            revision = load(store, owner, pid, execution_id)['revision']
    if execution_id and project.get('ui_execution_id') != execution_id:
        raise ValueError('只能增量更新当前任务的执行记录')
    previous = load(store, owner, pid, execution_id) if execution_id else {
        'id': str(uuid4()), 'revision': 0, 'cases': [], 'assets': [], 'created_at': now(),
        'scene_retention': project.get('ui_scene_retention') or {'key': 'none', 'label': '不保留测试现场'}}
    requirement_inventory = requirement_design.load(store, owner, pid)
    if revision != previous['revision']:
        raise ValueError('用例已更新，请读取最新 revision 后重试')
    merged = {c['case_id']: deepcopy(c) for c in previous['cases']}
    previous_ids = set(merged)
    # Only the opt-in compact receipt needs the changed-ID index. It includes
    # derived checkpoint/dependency updates, not just the submitted case IDs.
    previous_values = ({cid: json.dumps(case, ensure_ascii=False, sort_keys=True)
                        for cid, case in merged.items()} if response == 'summary' or include_saved_design else {})
    seen = set()
    validation_issues = []
    for position, case in enumerate(cases, 1):
        try:
            if not isinstance(case, dict):
                raise ValueError('用例必须是对象')
            # Result batches can send only changed fields; preserve the saved design
            # and checkpoint inventory instead of regenerating it at every write.
            case_id = case.get('case_id')
            case = test_checkpoints.apply_updates(case, merged.get(case_id, {}) if isinstance(case_id, str) else {})
            case = {**(merged.get(case_id, {}) if isinstance(case_id, str) else {}), **case}
            item = {}
            for field in FIELDS:
                value = case.get(field, 'not_run' if field == 'status' else '')
                if not isinstance(value, str) or len(value) > 20000:
                    raise ValueError(field + ' 必须是文本，最多 20000 字符')
                item[field] = value.strip()
            if 'superseded_by' in case:
                item['superseded_by'] = case['superseded_by']
            old_case = merged.get(item['case_id'], {})
            if 'original_blocked_context' in old_case:
                item['original_blocked_context'] = deepcopy(old_case['original_blocked_context'])
            item['action_context'] = ui_action_context.normalize(case.get('action_context', {}))
            item['steps_issue'] = '；'.join(reproduction_step_gaps(item))
            if not item['case_id'] or not item['scenario'] or item['case_id'] in seen:
                raise ValueError('填写用例 ID 与名称，同批 ID 不得重复')
            seen.add(item['case_id'])
            item['status'] = {'失败': 'failed', '部分通过': 'partial', **{v: k for k, v in LABELS.items()}}.get(item['status'], item['status'])
            if item['status'] not in LABELS:
                raise ValueError('未知执行状态')
            item['upload_attempts'] = ui_uploads.normalize(case.get('upload_attempts', []))
            if item['action_type'] and item['action_type'] not in ACTION_TYPES:
                raise ValueError('action_type 仅支持 authorization 或 manual_step')
            item['updated_at'] = now()
            baseline = (project.get('ui_retest_round') or {}).get('case_dependencies', {}).get(item['case_id'], [])
            dependencies = case.get('dependencies', merged.get(item['case_id'], {}).get('dependencies', baseline))
            item['dependencies'] = ui_dependencies.normalize(dependencies, item, project.get('ui_target_url', ''))
            item.update(test_checkpoints.normalize({**case, 'environment': item['environment']},
                        merged.get(item['case_id'], {}), project.get('ui_target_url', '')))
            requirement_design.validate_refs(item, requirement_inventory)
            scoped_inputs = {d.get('resource_id', d['id']): d.get('input_ref', '') for d in baseline}
            retest = project.get('ui_retest_round') or {}
            if item['case_id'] in retest.get('case_overrides', []):
                for dep in item['dependencies']:
                    if dep['kind'] in {'account', 'permission'}:
                        scoped_inputs.setdefault(dep['resource_id'], retest['input_ids'][item['case_id']])
            if scoped_inputs:
                item['dependencies'] = ui_dependencies.normalize([
                    {**d, 'input_ref': scoped_inputs.get(d['resource_id'], d['input_ref'])} for d in item['dependencies']],
                    item, project.get('ui_target_url', ''))
            # Keep the provenance of automatic skips until a real prerequisite recheck
            # releases them. Clients must not erase a blocker by omitting its fields.
            for key in ('blocked_by', 'execution_disposition'):
                if key in merged.get(item['case_id'], {}) and item['status'] in {'not_run', 'blocked'}:
                    item[key] = merged[item['case_id']][key]
            merged[item['case_id']] = Redactor().snapshot(item)
        except ValueError as error:
            case_ref = case.get('case_id', '') if isinstance(case, dict) else ''
            validation_issues.append(f'第 {position} 条 {case_ref}：{error}')
    if validation_issues:
        # All validation precedes persistence. Return each affected case in one
        # rejection, rather than requiring another model turn per bad case.
        raise ValueError('本批未保存；请一次修正以下用例问题，不重跑业务：\n' + '\n'.join(validation_issues))
    record = {**previous, 'revision': previous['revision'] + 1, 'cases': list(merged.values()),
              'coverage': merge_coverage(previous.get('coverage', []), coverage)}
    validate_supersession(previous, record['cases'])
    record['requirement_design'] = requirement_inventory
    if review_notes is not None:
        if not isinstance(review_notes, str) or len(review_notes) > 20000:
            raise ValueError('review_notes 必须是文本，最多 20000 字符')
        record.update(review_notes=Redactor().snapshot(review_notes.strip()), review_revision=record['revision'])
    if scene_result is not None:
        record['scene_outcome'] = scene_outcome(scene_result)
    if experiment is not None:
        record['experiment'] = ui_experiments.merge(previous.get('experiment'), experiment)
    # Measurement/evidence-only saves do not change the reviewed designs or results.
    if not cases and coverage is None and review_notes is None and scene_result is None and previous.get('review_revision') == previous['revision']:
        record['review_revision'] = record['revision']
    prior_results = {c['case_id'] for c in previous['cases'] if c['status'] in {'passed', 'failed', 'partial'}}
    ui_dependencies.apply_checks(record, reject_executed=seen - prior_results)
    from .ui_case_results import preserve_history
    preserve_history(previous, record)
    root = root_for(store, owner, pid, record['id'])
    root.mkdir(parents=True, exist_ok=True)
    pending_files = []
    for asset_input in staged_assets or []:
        asset, content = _prepare_asset(record, **asset_input)
        if content is not None:
            record['assets'].append(asset)
            pending_files.append((asset, content))
    written = []
    try:
        for asset, content in pending_files:
            path = root / asset['id']
            path.write_bytes(content)
            written.append(path)
        store._write(root / 'cases.json', record)
    except OSError:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    progress = ui_dependencies.progress_record(store, owner, pid, record, requirement_design=requirement_inventory)
    store.update_project(owner, pid, {'ui_execution_id': record['id'], 'ui_execution_revision':record['revision'],
        'ui_progress_record': progress})
    reports = _ReportBatch(store)
    sync_regression_results(store, owner, project, record, _reports=reports)
    publication = _refresh_published(store, owner, ui_project(store, owner, pid), record, _reports=reports) if refresh_report else {}
    gaps = []
    for case in merged.values():
        valid = attributes(case.get('environment'), case.get('client'), case.get('module'))
        missing = [field for field, value in zip(('environment', 'client', 'module'), valid) if not value]
        if missing:
            gaps.append({'case_id': case['case_id'], 'fields': missing})
    plan = ui_dependencies.plan(record, recovery=progress['recovery'])
    counts = plan['execution_summary']['status_counts']
    added_ids = [c['case_id'] for c in record['cases'] if c['case_id'] not in previous_ids]
    progress_message = (f"本轮 {len(active_cases(record['cases']))} 条：通过 {counts['passed']}、不通过 {counts['failed']}、"
                        f"验证未完成 {counts['partial']}、未执行 {counts['not_run']}、阻塞 {counts['blocked']}、"
                        f"待规则 {counts['pending_rule']}、待人工 {counts['pending_action']}；本批新增 {len(added_ids)} 条。")
    result = {'execution_id': record['id'], 'revision': record['revision'], 'total': len(active_cases(record['cases'])),
            **publication,
            'scope_change': {'previous_total': len(active_cases(previous['cases'])), 'current_total': len(active_cases(record['cases'])), 'added_case_ids': added_ids},
            'progress_message': progress_message,
            **({'experiment': record['experiment']} if 'experiment' in record else {}),
            'title_attribute_gaps': gaps, 'title_guidance': AI_TITLE_GUIDANCE, 'coverage_check': coverage_check(record),
            'dependency_groups': ui_dependencies.groups(record['cases'], record.get('dependency_checks')),
            'blocking_summary': ui_dependencies.blocking_summary(record),
            'execution_plan': plan}
    if response == 'summary':
        result.pop('title_guidance')
        result['coverage_check'] = {
            key: value for key, value in result['coverage_check'].items()
            if key != 'guidance' and not key.endswith('_guidance')}
        result.update(
            response='summary',
            submitted_case_ids=[case['case_id'] for case in cases],
            changed_case_ids=[case['case_id'] for case in record['cases']
                              if previous_values.get(case['case_id']) !=
                              json.dumps(case, ensure_ascii=False, sort_keys=True)])
    if include_saved_design:
        result['saved_cases'] = [case for case in record['cases'] if previous_values.get(case['case_id']) !=
                                json.dumps(case, ensure_ascii=False, sort_keys=True)]
        result['coverage'] = record.get('coverage', [])
    return result


def now():
    return datetime.now(timezone.utc).isoformat()


def sync_regression_results(store, owner, project, record, *, _reports=None):
    reports = _reports if _reports is not None else _ReportBatch(store)
    from .pingcode import PingCode
    _, links = regression_findings(store, owner, project, record['cases'], [], _reports=reports)
    if links:
        PingCode(store).sync_regression_sources(owner, project['id'], record.get('report_id', ''),
                                               links, record['cases'], _reports=reports)


def refresh_published(store, owner, pid, record):
    if not record.get('report_id'):
        return {}
    with store._lock:
        project = ui_project(store, owner, pid)
        return _refresh_published(store, owner, project, load(store, owner, pid, record['id']))


def _refresh_published(store, owner, project, record, *, _reports=None):
    """Caller owns Store lock and has just loaded or saved this record."""
    if not record.get('report_id'):
        return {}
    saved = store._read(store.project_dir(owner, project['id']) / 'analyses' / record['report_id'] / 'report.json')
    from .ui_closeout import summary as closeout_summary
    result = _publish(store, owner, project, record['id'], saved['title'], closeout_summary(record),
                      _record=record, _prior_report=saved, _reports=_reports)
    return {'report': result['report'], 'total_report': result['total_report']}


def _prepare_asset(record, case_id, step, filename, content_type, content_base64,
                   kind='screenshot', captured_at=''):
    cases = {c['case_id']: c for c in record['cases']}
    if case_id not in cases:
        raise ValueError('请先保存对应的用例')
    if kind not in ASSET_BYTE_LIMITS:
        raise ValueError('未知证据类型')
    if any(not isinstance(v, str) or len(v) > 300 for v in (filename, step, captured_at, content_type)):
        raise ValueError('证据元信息无效')
    if not filename or '/' in filename or '\\' in filename or '\x00' in filename:
        raise ValueError('文件名称无效')
    byte_limit = ASSET_BYTE_LIMITS[kind]
    limit_message = '截图上限 10 MiB，测试文件上限 100 MiB，视频上限 20 MiB'
    if not isinstance(content_base64, str) or len(content_base64) > 4 * ((byte_limit + 2) // 3):
        raise ValueError(limit_message)
    try:
        content = base64.b64decode(content_base64, validate=True)
    except ValueError:
        raise ValueError('文件内容不是有效 Base64') from None
    if (not content and kind != 'fixture') or len(content) > byte_limit:
        raise ValueError(limit_message)
    if kind == 'screenshot':
        from .pingcode import PingCode
        PingCode.screenshots([{'content_type': content_type, 'content_base64': content_base64}])
    if kind == 'video' and (content_type != 'video/webm' or not content.startswith(b'\x1aE\xdf\xa3')):
        raise ValueError('录屏需为 WebM 视频')
    if kind == 'observation':
        try:
            value = json.loads(content.decode('utf-8'))
        except (UnicodeError, ValueError):
            raise ValueError('观察证据必须为 UTF-8 JSON，不是测试输入文件') from None
        content = json.dumps(Redactor().snapshot(value), ensure_ascii=False, indent=2).encode('utf-8')
        content_type = 'application/json'
    if kind == 'fixture':
        content_type = 'application/octet-stream'
    digest = hashlib.sha256(content).hexdigest()
    old = next((a for a in record['assets'] if a['sha256'] == digest and a['filename'] == filename and a['case_id'] == case_id
                and a['step'] == step and a['kind'] == kind and a['captured_at'] == captured_at), None)
    if old:
        return old, None
    asset = {'id': str(uuid4()), 'filename': filename, 'content_type': content_type, 'kind': kind,
             'case_id': case_id, 'step': step, 'captured_at': captured_at, 'uploaded_at': now(),
             'sha256': digest, 'size': len(content)}
    return asset, content


def add_assets(store, owner, pid, execution_id, assets):
    with store._lock:
        return _add_assets(store, owner, pid, execution_id, assets)


def _add_assets(store, owner, pid, execution_id, assets):
    """Validate a transport batch completely, then persist it as one record update."""
    if not isinstance(assets, list) or not 1 <= len(assets) <= 50:
        raise ValueError('每批需包含 1 到 50 个证据；可继续追加下一批')
    record = load(store, owner, pid, execution_id)
    report_id = record.get('report_id')
    supplements = None
    if record.get('report_id') and ui_project(store, owner, pid).get('ui_execution_id') != execution_id:
        # Append missing inputs separately; never rewrite published results or evidence.
        if any(not isinstance(item, dict) or item.get('kind') != 'fixture' for item in assets):
            raise ValueError('本轮已发布，仅允许补存测试文件，不能更改历史证据')
        project = ui_project(store, owner, pid)
        if report_id not in {r['id'] for r in project.get('analysis_reports', [])}:
            raise ValueError('已发布报告不存在，不能补存测试文件')
        from . import ui_report_corrections
        report_root = store.project_dir(owner, pid) / 'analyses' / report_id
        original = store._read(report_root / 'report.json')
        effective = ui_report_corrections.apply(original, ui_report_corrections.load(store, owner, pid, report_id))
        if effective.get('ui_snapshot', {}).get('id') != execution_id:
            raise ValueError('报告与执行记录不匹配')
        record = {**effective['ui_snapshot'], 'report_id': ''}
        supplement_path = report_root / 'fixture-supplements.json'
        supplements = store._read(supplement_path) if supplement_path.exists() else {'assets': [], 'history': []}
    working = {**record, 'assets': list(record['assets'])}
    prepared = []
    new_files = []
    for index, item in enumerate(assets):
        if not isinstance(item, dict):
            raise ValueError(f'第 {index + 1} 个证据参数无效')
        try:
            asset, content = _prepare_asset(
                working,
                **{key: item.get(key, '') for key in
                   ('case_id', 'step', 'filename', 'content_type', 'content_base64', 'captured_at')},
                kind=item.get('kind', 'screenshot'))
        except ValueError as error:
            raise ValueError(f'第 {index + 1} 个证据无效：{error}') from None
        prepared.append(asset)
        if content is not None:
            if supplements is not None and any(
                    old.get('kind') == 'fixture' and old['case_id'] == asset['case_id']
                    and old['filename'] == asset['filename'] and old['sha256'] != asset['sha256']
                    for old in working['assets']):
                raise ValueError('不能用不同内容替换已发布的同名测试文件')
            working['assets'].append(asset)
            new_files.append((asset, content))
    root = root_for(store, owner, pid, execution_id)
    written = []
    try:
        for asset, content in new_files:
            path = root / asset['id']
            path.write_bytes(content)
            written.append(path)
        if supplements is None:
            if report_id and new_files:
                if working.get('review_revision') == working['revision']:
                    working['review_revision'] = working['revision'] + 1
                working['revision'] += 1
            store._write(root / 'cases.json', working)
        elif new_files:
            store._write(supplement_path, {
                'assets': [*supplements['assets'], *(asset for asset, _ in new_files)],
                'history': [*supplements['history'], {'uploaded_at': now(),
                    'execution_id': execution_id, 'asset_ids': [asset['id'] for asset, _ in new_files]}],
            })
    except OSError:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    if supplements is None and report_id and new_files:
        # Evidence changes the current record revision too. Keep the lightweight
        # progress and finish-status identity in the same critical section.
        project = ui_project(store, owner, pid)
        if project.get('ui_execution_id') == execution_id:
            store.update_project(owner, pid, {'ui_execution_revision': working['revision'],
                'ui_progress_record': {**project.get('ui_progress_record', {}),
                    'execution_id': execution_id, 'revision': working['revision'],
                    'counts': dict(Counter(c['status'] for c in active_cases(working['cases']))),
                    'saved_at': now(), 'report_id': report_id}})
        refresh_published(store, owner, pid, working)
    return {'assets': prepared, 'total': len(prepared), 'created': len(new_files),
            'execution_id': execution_id, 'revision': working['revision'],
            'reused': len(prepared) - len(new_files), **({'report_id': report_id} if report_id else {})}


def add_asset(store, owner, pid, execution_id, case_id, step, filename, content_type,
              content_base64, kind='screenshot', captured_at=''):
    result = add_assets(store, owner, pid, execution_id, [{
        'case_id': case_id, 'step': step, 'filename': filename, 'content_type': content_type,
        'content_base64': content_base64, 'kind': kind, 'captured_at': captured_at}])
    return {**result['assets'][0], **({'report_id': result['report_id']} if result.get('report_id') else {})}


def as_results(record):
    cases = [{**c, 'source_row': i + 2, 'result': '不测' if c.get('execution_disposition') == 'multi_account_excluded' else LABELS[c['status']], 'evidence': c['actual'],
              'code_basis': c['rule_basis'], 'criterion': c['method']} for i, c in enumerate(active_cases(record['cases']))]
    return {'filename': '平台保存的测试用例', 'sheet_name': '测试用例', 'counts': {
        **dict(Counter(c['status'] for c in cases)), 'total': len(cases)}, 'quality': {}, 'cases': cases,
        'superseded_cases': [c for c in record['cases'] if is_superseded(c)],
        'blocking_summary': ui_dependencies.blocking_summary(record)}


def regression_findings(store, owner, project, cases, findings, *, _reports=None):
    """Carry prior defects by stable case ID and record this round's outcome."""
    round_info = project.get('regression_round') or {}
    source_project_id = round_info.get('report_project_id')
    source_report_id = round_info.get('report_id')
    if not source_project_id or not source_report_id:
        return findings, []
    reports = _reports if _reports is not None else _ReportBatch(store)
    prior = {}
    case_sources = round_info.get('case_sources', {})
    sources = {(item['project_id'], item['report_id']) for item in case_sources.values()}
    if not sources:
        sources = {(source_project_id, source_report_id)}
    for pid, rid in sorted(sources):
        source = reports.report(owner, pid, rid)
        if round_id(store.get_project(owner, pid)) == round_id(project):
            continue
        source_cases = {c['case_id']: c for c in source.get('imported_results', {}).get('cases', [])}
        from .pingcode import PingCode
        decisions = {r['draft_id']: r for r in PingCode(store).lifecycle_for_report(owner, pid, rid, _reports=reports)}
        for index, finding in enumerate(source.get('findings', [])):
            case_id = finding.get('case_id')
            if (source_cases.get(case_id, {}).get('status') != 'failed'
                    or source_cases.get(case_id, {}).get('status_before_correction') not in (None, 'failed')
                    or decisions.get(f'finding-{index}', {}).get('triage_status') in {'rejected', 'result_corrected'}):
                continue
            if case_id and (not case_sources or case_sources.get(case_id) == {'project_id': pid, 'report_id': rid}):
                prior[case_id] = (f'finding-{index}', finding, pid, rid)
    current_cases = {case.get('case_id'): case for case in cases}
    current_findings = {finding.get('case_id'): (index, finding) for index, finding in enumerate(findings)}
    links = []
    for case_id, (source_draft, old_finding, source_project_id, source_report_id) in prior.items():
        case = current_cases.get(case_id)
        if not case:
            continue
        outcome = {'passed': 'regression_passed', 'failed': 'regression_failed'}.get(
            case.get('status'), 'pending_regression')
        existing = current_findings.get(case_id)
        if existing is None:
            finding = {**old_finding,
                'actual': case.get('evidence') or case.get('actual') or case.get('not_run_reason') or '本轮尚未形成执行结论。',
                'evidence': case.get('evidence') or case.get('actual') or case.get('not_run_reason') or '本轮尚未形成执行结论。',
                'test_environment': case.get('test_environment', old_finding.get('test_environment', '')),
                **{key: case.get(key, '') for key in ('ai_analysis', 'cause_analysis', 'recommendation')}}
            findings.append(finding)
            finding_index = len(findings) - 1
            current_findings[case_id] = (finding_index, finding)
        else:
            finding_index, finding = existing
        draft_id = f'finding-{finding_index}'
        links.append({'draft_id': draft_id, 'case_id': case_id,
                      'source_project_id': source_project_id, 'source_report_id': source_report_id,
                      'source_draft_id': source_draft, 'outcome': outcome})
    return findings, links


def publish(store, owner, project, execution_id, title, summary, *, notify=True):
    with store._lock:
        return _publish(store, owner, ui_project(store, owner, project['id']), execution_id, title, summary, notify=notify)


def _publish(store, owner, project, execution_id, title, summary, *, notify=True,
             _record=None, _prior_report=None, _reports=None):
    from .task_reports import save_task_report
    from .ui_total_reports import canonical_project, entry as total_entry
    # Modern rounds keep their own total; legacy history keeps its old link.
    total_project = ({**project, 'id': project['managed_parent_project_id']}
                     if project.get('managed_parent_project_id') else project
                     if project.get('execution_round') else canonical_project(store, owner, project))
    total = total_entry(total_project)
    reports = _reports if _reports is not None else _ReportBatch(store)
    record = _record if _record is not None else load(store, owner, project['id'], execution_id)
    if project.get('ui_execution_id') != execution_id:
        raise ValueError('只能发布当前任务的执行记录')
    report_id = record.get('report_id', '')
    prior_report = None
    if report_id:
        entry = next((r for r in project.get('analysis_reports', []) if r['id'] == record['report_id']), None)
        if not entry:
            raise ValueError('本轮已经发布，原报告已不在当前历史列表中；不能重复发布覆盖证据')
        prior_report = (_prior_report if _prior_report is not None else
                        store._read(store.project_dir(owner, project['id']) / 'analyses' / report_id / 'report.json'))
        if (record.get('published_revision', prior_report.get('ui_snapshot', {}).get('revision')) == record['revision']
                and title == prior_report['title'] and summary == prior_report['summary']):
            return {'report': entry, 'total_report': total, 'coverage_check': coverage_check(record)}
    parsed = as_results(record)
    # Incomplete execution is a coverage gap, not evidence of a product defect.
    # Record an observed, justified discrepancy as failed (or as a separate failed case).
    draft_cases = parsed['cases']
    findings = result_findings({'cases': draft_cases}, maximum=len(draft_cases))
    findings, regression_links = regression_findings(store, owner, project, draft_cases, findings, _reports=reports)
    if prior_report:
        # Stable draft indexes preserve reviews, submitted item identities and
        # the historical defect even when its current case now passes.
        current = {f.get('case_id'): f for f in findings}
        cases_by_id = {c['case_id']: c for c in draft_cases}
        links_by_case = {link['case_id']: dict(link) for link in prior_report.get('regression_links', [])}
        links_by_case.update({link['case_id']: link for link in regression_links})
        prior_cases = {c['case_id']: c for c in prior_report.get('ui_snapshot', {}).get('cases', [])}
        stable = []
        for index, old in enumerate(prior_report.get('findings', [])):
            cid = old.get('case_id')
            case = cases_by_id.get(cid)
            finding = current.pop(cid, None)
            if finding is None:
                finding = dict(old)
                if case:
                    finding.update(actual=case['actual'], evidence=case['actual'],
                                   **{k: case.get(k, '') for k in ('ai_analysis', 'cause_analysis', 'recommendation', 'test_environment')})
            stable.append(finding)
            old_case = prior_cases.get(cid, {})
            if case and cid not in links_by_case and any(case.get(k) != old_case.get(k) for k in ('status', 'actual', 'checkpoints', 'executed_at')):
                links_by_case[cid] = {'case_id': cid, 'source_project_id': project['id'],
                    'source_report_id': report_id, 'source_draft_id': f'finding-{index}',
                    'outcome': current_outcome(case)}
            if case and cid in links_by_case:
                link = links_by_case[cid]
                valid_prior = prior_failure(store, owner, project['id'], link, _reports=reports)
                link['outcome'] = (current_outcome(case) if not valid_prior else
                    {'passed': 'regression_passed', 'failed': 'regression_failed'}.get(case['status'], 'pending_regression'))
        stable.extend(current.values())
        findings = stable
        regression_links = [{**links_by_case[finding['case_id']], 'draft_id': f'finding-{index}'}
                            for index, finding in enumerate(findings) if finding.get('case_id') in links_by_case]
        from .ui_report_corrections import advance_execution
        advance_execution(store, owner, project['id'], report_id, prior_report.get('ui_snapshot', {}), record)
    result = save_task_report(store, owner, project, {'title': title, 'summary': summary,
        'imported_results': parsed, 'findings': findings, 'regression_links': regression_links,
        'run_ids': []}, ui_snapshot=record, report_id=report_id, notify=notify, _previous_report=prior_report)
    from .ui_retests import inherit_inputs
    inherit_inputs(store, owner, project, result['report']['id'], record['cases'])
    if regression_links:
        from .pingcode import PingCode
        PingCode(store).inherit_regression(owner, project['id'], result['report']['id'], regression_links, record['cases'])
    record['report_id'] = result['report']['id']
    record['published_revision'] = record['revision']
    store._write(root_for(store, owner, project['id'], execution_id) / 'cases.json', record)
    current = store.get_project(owner, project['id'])
    if current.get('ui_execution_id') == execution_id:
        progress_record = current.get('ui_progress_record') or {}
        store.update_project(owner, project['id'], {'ui_progress_record': {
            'execution_id': execution_id, 'revision': record['revision'],
            'counts': dict(Counter(c['status'] for c in active_cases(record['cases']))),
            'saved_at': progress_record.get('saved_at') or max((c.get('updated_at', '') for c in record['cases']), default=''),
            'report_id': record['report_id']}})
    return {**result, 'total_report': total, 'coverage_check': coverage_check(record)}


def cases_html(report):
    e = lambda value: html.escape(str(value))
    cases = report['imported_results']['cases']
    fields = [('case_id', '编号'), ('scenario', '用例'), ('priority', '优先级'), ('module', '模块'), ('executor', '执行方式'), ('precondition', '前置条件'), ('test_data', '测试数据'),
              ('steps', '步骤'), ('steps_issue', '步骤待补充'), ('expected', '预期结果'), ('evidence', '实际结果'), ('conclusion', '测试结论'),
              ('not_run_reason', '本轮未执行原因'), ('result', '状态')]
    if report.get('aggregate'):
        fields = [('display_case_id' if key == 'case_id' else key, label) for key, label in fields]
        fields += [('source_session', '来源会话'), ('scope_label', '版本 / 环境 / 类型'), ('source_url', '来源报告')]
    rows = ''.join('<tr>' + ''.join('<td>' + e(priority_label(c.get(k)) if k == 'priority' else LABELS['partial'] if k == 'result' and c.get(k) == '部分通过' else c.get(k, '')) + '</td>' for k, _ in fields) +
                   '<td>' + evidence_html(report, c['case_id']) + '</td></tr>' for c in cases)
    return ('<!doctype html><meta charset="utf-8"><title>测试用例与数据</title>'
            '<link rel="stylesheet" href="/static/report-image-preview.css">'
            '<script src="/static/report-image-preview.js" defer></script>'
            '<style>body{font:14px sans-serif;padding:24px}td,th{border:1px solid #ddd;padding:10px;'
            'white-space:pre-wrap;min-width:110px;vertical-align:top}table{border-collapse:collapse}</style>'
            '<a href="index.html">返回报告</a> · <a href="cases.xlsx">导出 XLSX</a><h1>测试用例与数据</h1>'
            + requirements_html(report) + coverage_html(report) + blocking_html(report) + '<table><tr>'
            + ''.join('<th>' + name + '</th>' for _, name in fields) + '<th>证据与数据文件</th></tr>' + rows + '</table>' + superseded_html(report))


def export_test_data_zip(store, owner, pid, report):
    """Bundle readable case inputs and their generated fixture files for replay."""
    snapshot = report.get('ui_snapshot', {})
    cases = report.get('imported_results', {}).get('cases', [])
    assets = [a for a in snapshot.get('assets', []) if a.get('kind') == 'fixture']
    case_data = [{key: case.get(key, '') for key in
                  ('case_id', 'scenario', 'precondition', 'test_data', 'steps', 'expected')}
                 for case in cases if str(case.get('test_data', '')).strip()
                 or any(a.get('case_id') == case.get('case_id') for a in assets)]
    manifest = {'title': report.get('title', '测试报告'), 'case_count': len(case_data),
                'fixture_count': len(assets), 'cases': case_data,
                'fixtures': [{key: asset.get(key, '') for key in
                              ('id', 'filename', 'case_id', 'step', 'size', 'sha256', 'captured_at')}
                             for asset in assets]}
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('测试数据.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        root = root_for(store, owner, pid, snapshot['id']) if snapshot.get('id') else None
        for asset in assets:
            source = root / asset['id'] if root else None
            if not source or not source.is_file():
                continue
            case_id = re.sub(r'[^0-9A-Za-z._-]+', '_', asset.get('case_id', '未关联')) or '未关联'
            filename = re.sub(r'[^0-9A-Za-z._\-\u4e00-\u9fff]+', '_', asset['filename']) or asset['id']
            archive.writestr(f'文件/{case_id}/{asset["id"][:8]}-{filename}', source.read_bytes())
    return output.getvalue()


def coverage_html(report):
    record = report.get('ui_snapshot', {})
    if not record.get('coverage') and not record.get('review_notes'):
        return ''
    e = lambda value: html.escape(str(value), quote=True)
    rows = ''.join('<tr>' + ''.join('<td>' + e(value) + '</td>' for value in
                    (a['feature'], a['entry'], a['considerations'], '、'.join(a['case_ids']), a['gap'])) + '</tr>'
                   for a in record.get('coverage', []))
    stale = '（用例或清单已更新，需重新回查）' if record.get('review_revision') != record.get('revision') else ''
    return ('<details class="coverage-details"><summary>覆盖清单与回查</summary>'
            '<p>按实际功能和风险设计，不以用例数量或执行比例代表覆盖完整。</p><div style="overflow:auto"><table><tr>'
            '<th>功能 / 规则 / 风险</th><th>入口与状态</th><th>设计考虑与依据</th><th>对应用例</th><th>剩余缺口</th></tr>'
            + rows + '</table></div><p style="white-space:pre-wrap">' + e(record.get('review_notes') or '尚未保存回查记录')
            + e(stale) + '</p></details>')


def requirements_html(report):
    """Frozen traceability and every incomplete assertion, with provenance."""
    snapshot = report.get('ui_snapshot', {})
    design = snapshot.get('requirement_design', {})
    cases = active_cases(snapshot.get('cases', []))
    if not design.get('requirements') and not any(c.get('checkpoints') for c in cases):
        return ''
    e = lambda v: html.escape(str(v), quote=True)
    modes = {'real': '真实环境', 'sandbox': '沙箱通道', 'mock': '模拟环境', 'design': '仅设计'}
    rows = ''.join('<tr><td>' + e(r['title']) + '</td><td>' + e('、'.join(c['case_id'] for c in cases if r['id'] in c.get('requirement_ids', [])) or '尚未关联具体用例') + '</td></tr>'
                   for r in design.get('requirements', []))
    questions = ''.join('<li>' + e(q['title']) + '：' + e(q.get('resolution') or '待明确规则') + '</li>' for q in design.get('questions', []))
    items = []
    corrected = {c['case_id'] for c in report.get('imported_results', {}).get('cases', [])
                 if c.get('observations_corrected_at')}
    for case in cases:
        points = []
        for p in case.get('checkpoints', []):
            if case['case_id'] in corrected:
                points.append('<li><b>' + e(p['title']) + '</b> · ' + e(modes[p['verification_mode']])
                              + '<p>预期：' + e(p['expected']) + '<br>判定与观察以用例当前实际结果为准。</p></li>')
                continue
            gap = '；'.join(g['reason'] for g in p.get('gaps', []))
            detail = e(p['expected']) + '<br>观察：' + e(p.get('actual') or gap or '尚未验证')
            if p.get('action_required') and p['status'] == 'pending_action':
                detail += '<br>人工操作：' + e(p['action_required'])
            if p.get('correlation'):
                detail += '<br>原业务关联：' + e(json.dumps(p['correlation'], ensure_ascii=False))
            if p.get('inherited_from'):
                detail += '<br>前序观察沿用原轮次，本轮未重复执行：' + e(p['inherited_from']['execution_id'])
            points.append('<li><b>' + e(p['title']) + '</b> · ' + e(LABELS[p['status']]) + ' · ' + e(modes[p['verification_mode']]) + '<p>' + detail + '</p></li>')
        if points:
            items.append('<details><summary>' + e(case['case_id'] + ' · ' + case['scenario']) + '</summary><ol>' + ''.join(points) + '</ol></details>')
    return ('<section class="requirements-report"><h2>需求覆盖与未完成检查</h2><p>模拟支付只验证应用对模拟通道的处理；'
            '订单和权益仍需独立业务证据。旧轮次观察有明确来源，不计作本轮重新执行。</p>'
            + ('<table><tr><th>需求 / 验收条件</th><th>具体用例</th></tr>' + rows + '</table>' if rows else '')
            + ('<ul>' + questions + '</ul>' if questions else '') + ''.join(items) + '</section>')


def export_xlsx(report):
    """Inline strings prevent formulas in untrusted test data from executing in Excel."""
    from .ui_xlsx import workbook
    fields = [('case_id', '用例编号'), ('module', '模块'), ('scenario', '用例名称'), ('priority', '优先级'), ('executor', '执行方式'), ('precondition', '前置条件'),
              ('test_data', '测试数据'), ('steps', '测试步骤'), ('expected', '预期结果'),
              ('evidence', '实际结果'), ('conclusion', '测试结论'), ('not_run_reason', '本轮未执行原因'), ('result', '执行结果')]
    if report.get('aggregate'):
        fields = [('display_case_id' if key == 'case_id' else key, label) for key, label in fields]
        fields += [('source_session', '来源会话'), ('scope_label', '版本 / 环境 / 类型'), ('source_url', '来源报告')]
    fields += [('ai_analysis', 'AI 解读'), ('recommendation', '建议优化')]
    fields += [('requirement_refs', '需求编号'), ('checkpoint_details', '检查点、条件与验证方式')]
    snapshots = {c['case_id']: c for c in report.get('ui_snapshot', {}).get('cases', [])}
    values = [[v for _, v in fields]]
    for c in report['imported_results']['cases']:
        snapshot = snapshots.get(c['case_id'], {})
        extra = {'result': LABELS['partial'] if c.get('result') == '部分通过' else c.get('result', ''),
                 'requirement_refs': '、'.join(snapshot.get('requirement_ids', [])),
                 'checkpoint_details': '\n'.join(p['title'] + ' / ' + p['verification_mode']
                    + '\n预期：' + p['expected'] + '\n判定与观察以用例当前实际结果为准。'
                    if c.get('observations_corrected_at') else
                    p['title'] + '：' + LABELS[p['status']] + ' / ' + p['verification_mode']
                    + '\n预期：' + p['expected'] + '\n观察：' + (p.get('actual') or '；'.join(g['reason'] for g in p.get('gaps', [])) or '未执行')
                    for p in snapshot.get('checkpoints', []))}
        if c.get('wording_corrected_at'):
            extra.update({key: '' for key in ('ai_analysis', 'cause_analysis', 'recommendation')})
        values.append([{**c, **extra}.get(k, '') for k, _ in fields])
    return workbook(fields, values)


def blocking_html(report):
    summary = report.get('imported_results', {}).get('blocking_summary')
    if summary is None:
        summary = ui_dependencies.blocking_summary(report.get('ui_snapshot', {}))
    return ('<p>共同阻塞原因 %s 项 · 受影响独立用例 %s 条 · 无结构化原因待复核 %s 条。'
            '恢复条件不代表业务验证通过。</p>') % tuple(summary.get(k, 0) for k in (
                'reason_count', 'affected_case_count', 'unstructured_blocked_case_count'))


def superseded_html(report):
    cases = report.get('imported_results', {}).get('superseded_cases', [])
    if not cases:
        return ''
    e = lambda value: html.escape(str(value))
    return '<details><summary>已拆分的原聚合条目（保留历史，不计入活动用例）</summary><ul>' + ''.join(
        '<li>' + e(c['case_id']) + ' → ' + e('、'.join(c['superseded_by'])) + '<p>' +
        e(c.get('scenario', '')) + ' · ' + e(c.get('actual') or c.get('not_run_reason', '')) +
        '</p></li>' for c in cases) + '</ul></details>'
