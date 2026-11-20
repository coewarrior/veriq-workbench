"""Scoped UI prerequisites, shared checks and explicit skipped-case outcomes."""
from __future__ import annotations

from copy import deepcopy
from .ui_case_results import active_cases, preserve_history
from . import testing_policy

import hashlib
import json
from datetime import datetime, timezone

KINDS = {'account', 'permission', 'file', 'data', 'service', 'observation', 'payment', 'capability', 'other', 'tool', 'network'}
FINISHED = {'passed', 'failed', 'partial', 'pending_rule', 'pending_action'}
EXECUTION_PRACTICE = (
    '默认执行规则见同源 /static/skills/web-exploratory-testing/SKILL.md。'
    '必要准备完成立即测试；复用本轮未变的页面、登录态、设计和证据。'
    '已知动作、真实完成等待和局部断言连续执行，未知分支或异常才返回判断。'
    '每条用例独立判定后立即增量保存，沿用最新 revision；不逐动作请求平台或重读全表。'
    '无账号结束当前回合，真实资源事件才续接，不循环领取或定时唤醒模型。'
)
CASE_EXECUTION_GUIDANCE = testing_policy.GUIDANCE + EXECUTION_PRACTICE + (
    '范围以目标及完整原资料为准，详见 references/coverage-design.md；先列已知功能范围，再分批设计和执行。'
    '目标内必要前置、关联流程、状态和副作用属于测试范围；可在授权内准备的数据先准备。'
    '真实缺失条件仅阻塞相关检查点，不删已知设计或改写业务终点。'
    '收尾对照原范围处理具体遗漏；已有确定结果不重测，真实缺口可保留并发布。'
    '用户明确限定流程、用例或只设计时遵守该范围，不扩展无关业务。'
)
EXECUTION_GUIDANCE = CASE_EXECUTION_GUIDANCE + (
    'execution_plan 是已保存状态的诊断建议，由 Codex 判断下一步，不是执行或保存准入；'
    'check_dependencies 提示共同条件，execute 提示可能可推进项；'
    'review_remaining 与 recovery.review_required_refs 提示原用例/检查点的剩余断言需要模型判断，不自动重测；report 仅表示记录中未列出可推进项，不证明目标覆盖完整。'
    'blocked_dependency_groups 复用真实检查，deferred_dependencies 不重复探测；条件变化才重查。'
    '首次真实关键阻塞说明影响与剩余分支；需要用户实际操作的项标 pending_action。'
    '任何类型条件解除或收到同轮对应恢复事实，都及时复核受影响的原剩余项；不限定故障码或依赖类型。'
    '未结构化阻塞、待人工和待规则也保留在 recovery.pending_refs，未核实解除不能猜测为就绪。'
    '协调者只在启动、首批设计、真实阻塞/资源事件、收尾介入，见 references/coordinator.md。'
)


def normalize(values, case, target_url):
    if not isinstance(values, list) or len(values) > 20:
        raise ValueError('dependencies 必须为最多 20 项的共同前置条件数组')
    result = {}
    for value in values:
        if not isinstance(value, dict):
            raise ValueError('共同前置条件必须是对象')
        fields = {key: value.get(key, '') for key in ('key', 'title', 'kind', 'tenant', 'role', 'input_ref', 'account_id', 'state_ref')}
        if any(not isinstance(v, str) or len(v) > 500 for v in fields.values()):
            raise ValueError('共同前置条件字段必须是最多 500 字的文本')
        fields = {key: val.strip() for key, val in fields.items()}
        environment = value.get('environment') or case.get('environment', '')
        if not isinstance(environment, str) or len(environment) > 100:
            raise ValueError('共同前置条件的环境无效')
        if not fields['key'] or not fields['title'] or fields['kind'] not in KINDS or not environment.strip():
            raise ValueError('共同前置条件需明确 key、title、kind 和 environment，不能按相似文案猜测关联')
        if fields['kind'] in {'account', 'permission'} and (not fields['role'] or not fields['tenant']):
            raise ValueError('共用账号或权限需明确角色和租户；单租户请填写实际范围，无租户填“无租户”')
        scope = {'target_url': target_url, 'environment': environment.strip(),
                 'tenant': fields['tenant'], 'role': fields['role']}
        identity = {'key': fields['key'], 'kind': fields['kind'], **scope}
        for field in ('account_id', 'state_ref'):
            if fields[field]:
                identity[field] = fields[field]
        if fields['kind'] in {'tool', 'network'}:
            explicit_scope = value.get('scope')
            if not isinstance(explicit_scope, str) or not explicit_scope.strip() or len(explicit_scope) > 500:
                raise ValueError('tool/network 需明确 scope，不能跨运行时或网络链路猜测共用')
            fields['scope'] = explicit_scope.strip()
            identity['scope'] = fields['scope']
        resource = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
        if fields['input_ref']:
            identity['input_ref'] = fields['input_ref']
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
        result[digest] = {**fields, 'environment': scope['environment'], 'target_url': target_url,
                         'id': 'dep-' + digest, 'resource_id': 'dep-' + resource}
    return list(result.values())


def case_dependencies(case):
    return [*case.get('dependencies', []), *(d for p in case.get('checkpoints', []) for d in p.get('dependencies', []))]


def remaining_dependencies(case):
    return [*case.get('dependencies', []), *(d for p in case.get('checkpoints', [])
            if p.get('status') not in {'passed', 'failed'} for d in p.get('dependencies', []))]


def recovery_plan(record, *, confirmations=None, requirement_design=None, supplied_inputs=None):
    """Describe original unfinished conditions; never grant execution or change verdicts.

    Confirmations are supplied only after the existing report/target/action check.
    Live rule answers may be supplied without changing a frozen report snapshot.
    Signatures contain only the relevant facts, so unrelated saves are not events.
    """
    from . import ui_records
    design = requirement_design if requirement_design is not None else record.get('requirement_design', {})
    questions = {q['id']: q for q in design.get('questions', [])}
    checks = record.get('dependency_checks', {})
    pending = []
    for case in active_cases(record.get('cases', [])):
        if testing_policy.case_excluded(case):
            continue
        points = [p for p in case.get('checkpoints', []) if p.get('status') not in {'passed', 'failed'}]
        if not points and case.get('status') in {'passed', 'failed'}:
            continue
        for point in points or [None]:
            item = point or case
            status = item.get('status', 'not_run')
            deps = [*case.get('dependencies', []), *(point or {}).get('dependencies', [])]
            qids = list(dict.fromkeys([*case.get('question_ids', []), *(point or {}).get('question_ids', []),
                *(qid for qid, q in questions.items() if case['case_id'] in q.get('report_case_ids', []))]))
            conditions = []
            for dep in deps:
                check = checks.get(dep['id']) or {}
                conditions.append({'kind': 'dependency', 'id': dep['id'], 'dependency_kind': dep['kind'],
                    'status': check.get('status', 'unchecked'), 'title': dep['title'],
                    'observed': check.get('observed', ''), 'checked_at': check.get('checked_at', '')})
            for qid in qids:
                question = questions.get(qid) or {}
                conditions.append({'kind': 'rule', 'id': qid, 'status': question.get('status', 'pending_rule'),
                    'title': question.get('title', qid), 'resolution': question.get('resolution', ''),
                    'basis': question.get('basis', '')})
            # Retain a predecessor after it passes: disappearance of a gap is
            # itself a recovery fact, not loss of the original condition.
            predecessors = {p['id']: p for p in case.get('checkpoints', [])}
            for predecessor_id in (point or {}).get('depends_on', []):
                predecessor = predecessors.get(predecessor_id) or {}
                conditions.append({'kind': 'step', 'id': predecessor_id,
                    'status': predecessor.get('status', 'not_run')})
            for qid in (point or {}).get('rule_updates', []):
                conditions.append({'kind': 'rule_update', 'id': qid, 'status': 'review_required',
                    'reason': '规则变化后需由 Codex 修订原检查点预期及依据'})
            action = ui_records.required_action({**case, 'checkpoints': [point] if point else []})
            if action:
                confirmation = ((confirmations or {}).get((case['case_id'], (point or {}).get('id')))
                                or (confirmations or {}).get(case['case_id']) or {})
                decision = 'authorized' if action['type'] == 'authorization' else 'completed'
                confirmed = confirmation.get('action') == action and confirmation.get('decision') == decision
                conditions.append({'kind': 'action', 'id': (point or {}).get('id', case['case_id']),
                    'status': 'confirmed' if confirmed else 'pending_action', 'action': action,
                    'decided_at': confirmation.get('decided_at', '') if confirmed else ''})
            inputs = ((supplied_inputs or {}).get((case['case_id'], (point or {}).get('id')))
                      or (supplied_inputs or {}).get(case['case_id'], []))
            if inputs:
                conditions.append({'kind': 'supplied_input', 'id': case['case_id'],
                    'status': 'requires_verification', 'input_ids': list(inputs)})
            unknown_decision = (status == 'pending_rule' and not qids or
                                status == 'pending_action' and not action)
            unstructured = unknown_decision or (not conditions and
                (status in {'blocked', 'pending_action', 'pending_rule'} or case.get('not_run_reason')))
            if unstructured:
                conditions.append({'kind': 'unstructured', 'id': (point or {}).get('id', case['case_id']),
                    'status': 'unverified', 'reason': item.get('actual') or case.get('not_run_reason') or '',
                    'action_required': item.get('action_required', '')})
            waiting = any((c['kind'] == 'dependency' and c['status'] != 'ready')
                or (c['kind'] == 'rule' and c['status'] != 'resolved')
                or (c['kind'] == 'step' and c['status'] != 'passed')
                or (c['kind'] == 'action' and c['status'] != 'confirmed') for c in conditions)
            established = (status in {'blocked', 'partial', 'pending_action', 'pending_rule'} or
                           case.get('status') in {'blocked', 'partial', 'pending_action', 'pending_rule'} or
                           bool(case.get('not_run_reason')))
            if not established and not conditions:
                continue  # Ordinary runnable designs already use the execution plan.
            # Unknown decisions remain visible for fact checking; never assume approval.
            review = case.get('executor') != '人工' and (bool(inputs) or
                     established and not waiting and not unknown_decision)
            for condition in conditions:
                facts = {k: value for k, value in condition.items()
                         if k not in {'title', 'observed', 'checked_at', 'decided_at', 'reason', 'action_required'}}
                condition['fact_signature'] = hashlib.sha256(json.dumps(facts, sort_keys=True,
                    ensure_ascii=False).encode()).hexdigest()[:24]
            ref = {'case_id': case['case_id'], **({'checkpoint_id': point['id']} if point else {}),
                'status': status, 'conditions': conditions, 'ready_for_review': review,
                'review_reason': ('supplied_input_needs_verification' if inputs else
                                  'original_blocker_needs_fact_check' if unstructured else
                                  'remaining_conditions_require_model_review') if review else '',
                'executor': case.get('executor', '')}
            signature = {**ref, 'conditions': [c['fact_signature'] for c in conditions]}
            ref['condition_signature'] = hashlib.sha256(json.dumps(signature, sort_keys=True,
                ensure_ascii=False).encode()).hexdigest()[:24]
            pending.append(ref)
    review = [ref for ref in pending if ref['ready_for_review']]
    signature = [(r['case_id'], r.get('checkpoint_id'), r['condition_signature']) for r in pending]
    return {'execution_id': record.get('id'), 'source_revision': record.get('revision'),
            'pending_refs': pending, 'review_required_refs': review,
            'condition_signature': hashlib.sha256(json.dumps(signature, ensure_ascii=False).encode()).hexdigest()[:24]}


def recovery_summary(record, *, confirmations=None, requirement_design=None, supplied_inputs=None):
    """Small metadata projection for the original coordinator, without case bodies."""
    result = recovery_plan(record, confirmations=confirmations, requirement_design=requirement_design,
                           supplied_inputs=supplied_inputs)
    pending = [{**ref, 'conditions': [{k: value for k, value in condition.items()
                if k in {'kind', 'id', 'dependency_kind', 'status', 'fact_signature'}} for condition in ref['conditions']]}
               for ref in result['pending_refs']]
    return {**result, 'pending_refs': pending,
            'review_required_refs': [ref for ref in pending if ref['ready_for_review']]}


def cached_recovery(project, record):
    """Use metadata only for this exact current execution and record revision."""
    progress = project.get('ui_progress_record') or {}
    recovery = progress.get('recovery') or {}
    if (record.get('id') and project.get('ui_execution_id') == record['id'] == progress.get('execution_id')
            == recovery.get('execution_id') and record.get('revision') == project.get('ui_execution_revision')
            == progress.get('revision') == recovery.get('source_revision')):
        return recovery
    return None


def progress_record(store, owner, pid, record, *, requirement_design=None, input_state=None):
    """Cache current condition facts during existing writes, never on wait polling."""
    from . import ui_records, ui_retests
    from . import requirement_design as rules
    project = store.get_project(owner, pid)
    candidates = [c for c in active_cases(record.get('cases', [])) if not testing_policy.case_excluded(c) and
                  (c.get('status') not in {'passed', 'failed'} or any(
                      p.get('status') not in {'passed', 'failed'} for p in c.get('checkpoints', [])))]
    if input_state is None and candidates:
        _, input_state = ui_retests._state(store, owner, pid)
    input_state = input_state or {'bindings': {}}
    confirmations, supplied = {}, {}
    for case in candidates:
        for point in [p for p in case.get('checkpoints', []) if p.get('status') not in {'passed', 'failed'}] or [None]:
            scoped = {**case, 'checkpoints': [point] if point else []}
            origin = (case.get('source_report') or {}).get('id') or record.get('report_id')
            supplied[(case['case_id'], (point or {}).get('id'))] = ui_retests.case_input_ids(
                input_state, origin, [scoped])[case['case_id']]
            if ui_records.required_action(scoped):
                confirmation = ui_retests.action_confirmation(input_state, project, record.get('report_id'), scoped)
                if confirmation:
                    confirmations[(case['case_id'], (point or {}).get('id'))] = confirmation
    design = requirement_design if requirement_design is not None else rules.load(store, owner, pid)
    return {'execution_id': record['id'], 'revision': record['revision'],
            'counts': {k: v for k, v in progress_summary(record)['status_counts'].items() if v},
            'saved_at': ui_records.now(), 'report_id': record.get('report_id'),
            'recovery': recovery_summary(record, confirmations=confirmations,
                                         requirement_design=design, supplied_inputs=supplied)}


def refresh_recovery_summary(store, owner, pid, *, requirement_design=None, input_state=None):
    """Refresh only the current record's metadata after an explicit condition update."""
    from . import ui_records
    project = store.get_project(owner, pid)
    eid = project.get('ui_execution_id')
    if not eid:
        return
    record = ui_records.load(store, owner, pid, eid)
    summary = progress_record(store, owner, pid, record, requirement_design=requirement_design, input_state=input_state)
    previous = project.get('ui_progress_record') or {}
    if previous.get('execution_id') == record['id'] and previous.get('revision') == record['revision']:
        summary = {**previous, 'recovery': summary['recovery']}
    # The existing write lock protects the record and this metadata projection.
    store.update_project(owner, pid, {'ui_execution_revision': record['revision'], 'ui_progress_record': summary})


def groups(cases, checks=None):
    result = {}
    for case in active_cases(cases):
        for dep in case_dependencies(case):
            group = result.setdefault(dep['id'], {**dep, 'case_ids': [], 'checkpoints': []})
            if case['case_id'] not in group['case_ids']:
                group['case_ids'].append(case['case_id'])
        for point in case.get('checkpoints', []):
            for dep in point.get('dependencies', []):
                groups_ref = result[dep['id']]['checkpoints']
                groups_ref.append({'case_id': case['case_id'], 'checkpoint_id': point['id']})
    for gid, group in result.items():
        group['check'] = (checks or {}).get(gid)
    return list(result.values())


def apply_checks(record, *, reject_executed=()):
    """Keep prerequisite diagnostics separate from model-owned business verdicts."""
    checks = record.get('dependency_checks', {})
    valid = {d['id'] for c in record['cases'] for d in case_dependencies(c)}
    record['dependency_checks'] = {gid: value for gid, value in checks.items() if gid in valid}
    from . import test_checkpoints
    test_checkpoints.reconcile({**record, 'cases': active_cases(record['cases'])})
    for case in active_cases(record['cases']):
        testing_policy.annotate_unexecuted(case)
    return record


def progress_summary(record):
    """Count saved verdicts, not scheduler eligibility, across the whole round."""
    record = {**record, 'cases': active_cases(record['cases'])}
    counts = {status: 0 for status in ('passed', 'failed', 'partial', 'not_run', 'blocked', 'pending_rule', 'pending_action')}
    remaining_groups = {}
    for case in active_cases(record['cases']):
        status = case['status']
        counts[status] = counts.get(status, 0) + 1
        if status not in {'passed', 'failed'} and not testing_policy.case_excluded(case):
            module = case.get('module') or '未标明模块'
            group = remaining_groups.setdefault(module, {'module': module, 'case_ids': [], 'status_counts': {}})
            group['case_ids'].append(case['case_id'])
            group['status_counts'][status] = group['status_counts'].get(status, 0) + 1
    excluded = sum(testing_policy.case_excluded(c) and c['status'] not in {'passed', 'failed'} for c in record['cases'])
    determined = counts['passed'] + counts['failed']
    return {'designed_cases': len(record['cases']), 'status_counts': counts,
            'determined_cases': determined, 'policy_excluded_cases': excluded,
            'remaining_cases': len(record['cases']) - determined - excluded,
            'remaining_groups': list(remaining_groups.values())}


def plan(record, *, recovery=None):
    original = {**record, 'cases': active_cases(record['cases'])}
    excluded = [c for c in original['cases'] if testing_policy.case_excluded(c)]
    record = {**original, 'cases': [c for c in original['cases'] if not testing_policy.case_excluded(c)]}
    checks = record.get('dependency_checks', {})
    runnable, skipped, completed, needs_check = [], [], [], set()
    recovery = recovery if recovery is not None else recovery_plan(record)
    review_required = list(dict.fromkeys(ref['case_id'] for ref in recovery['review_required_refs']))
    for case in active_cases(record['cases']):
        cid = case['case_id']
        if case.get('checkpoints'):
            continue
        if case['status'] in FINISHED:
            if case['status'] == 'partial':
                continue
            completed.append(cid)
            continue
        blocked = [d['id'] for d in case.get('dependencies', []) if checks.get(d['id'], {}).get('status') == 'blocked']
        if blocked:
            skipped.append({'case_id': cid, 'dependency_ids': blocked,
                            'reason': '；'.join(checks[d]['observed'] for d in blocked), 'business_steps_executed': False})
            continue
        if case.get('executor') == '人工':
            continue
        pending = [d['id'] for d in case.get('dependencies', []) if d['id'] not in checks]
        needs_check.update(pending)
        if not pending and case['status'] == 'not_run':
            runnable.append(cid)
    from . import test_checkpoints
    points = test_checkpoints.plan(record)
    manual_cases = {c['case_id'] for c in record['cases'] if c.get('executor') == '人工'}
    point_statuses = {(c['case_id'], p['id']): p['status'] for c in record['cases'] for p in c.get('checkpoints', [])}
    points['waiting_checkpoints'].extend({**p, 'status': point_statuses[p['case_id'], p['checkpoint_id']],
                                         'reason': '本用例指定人工执行。'}
                                        for p in points['runnable_checkpoints'] if p['case_id'] in manual_cases)
    points['runnable_checkpoints'] = [p for p in points['runnable_checkpoints'] if p['case_id'] not in manual_cases]
    for p in points['runnable_checkpoints']:
        if p['case_id'] not in runnable:
            runnable.append(p['case_id'])
    # Do not probe downstream prerequisites while a known blocker already makes
    # that path unavailable. Independent checkpoints still get their own checks.
    for case in active_cases(record['cases']):
        if case['case_id'] in manual_cases:
            continue
        unavailable = {}
        for point in case.get('checkpoints', []):
            gaps = test_checkpoints.point_gaps(record, case, point)
            unavailable[point['id']] = point['status'] in {'failed', 'pending_action', 'pending_rule'} or any(
                (g['kind'] == 'dependency' and g['status'] == 'blocked') or g['kind'] == 'rule'
                or (g['kind'] == 'step' and unavailable.get(g['id'], False)) for g in gaps)
            if point['status'] not in test_checkpoints.DONE and not unavailable[point['id']]:
                needs_check.update(g['id'] for g in gaps if g['kind'] == 'dependency' and g['status'] == 'unchecked')
    dependency_groups = groups(record['cases'], checks)
    pending = [g for g in dependency_groups if g['id'] in needs_check]
    # Stable ties preserve the saved design order. Completed cases do not make a
    # prerequisite appear more urgent than one blocking actual remaining work.
    outstanding = {c['case_id'] for c in record['cases']
                   if c['status'] not in {'passed', 'failed'} or c.get('checkpoints') and any(
                       p['status'] not in test_checkpoints.DONE for p in c['checkpoints'])}
    pending = [{**g, 'affected_case_ids': [cid for cid in g['case_ids'] if cid in outstanding]} for g in pending]
    pending.sort(key=lambda g: -len(g['affected_case_ids']))
    remaining_by_dependency = {}
    for case in record['cases']:
        if case['case_id'] in outstanding:
            for dep in remaining_dependencies(case):
                remaining_by_dependency.setdefault(dep['id'], set()).add(case['case_id'])
    blocked_groups = [{**g, 'affected_case_ids': [cid for cid in g['case_ids'] if cid in remaining_by_dependency.get(g['id'], set())]}
                      for g in dependency_groups if (g['check'] or {}).get('status') == 'blocked'
                      and remaining_by_dependency.get(g['id'])]
    deferred = [g for g in dependency_groups if not g['check'] and g['id'] not in needs_check
                and remaining_by_dependency.get(g['id'])]
    waiting_ids = [c['case_id'] for c in record['cases'] if c['case_id'] not in runnable
                   and c['status'] not in {'passed', 'failed'}]
    if not original['cases']:
        action, reason = 'design', '尚无具体用例；复用已确认准备，保存本批必要具体设计后直接执行，其他设计随原目标推进补齐。'
    elif pending:
        action, reason = 'check_dependencies', '优先检查影响范围最大的共同条件，一次记录后重新采用返回计划。'
    elif runnable:
        action, reason = 'execute', '继续可执行的独立用例或检查点；已确认阻塞的路径不重复尝试。'
    elif review_required:
        action, reason = 'review_remaining', '部分验证或原阻塞结论仍需核对；Codex 根据剩余断言、当前依赖及条件变化决定是否续接，保留原观察，不自动改判或重跑。'
    else:
        action, reason = 'report', '当前设计没有可自动推进项；核实结果与现场并及时发布，保留所有未验证范围。'
    return {'testing_policy': testing_policy.snapshot(),
            'excluded_cases': [{'case_id': c['case_id'], 'reason': testing_policy.REASON,
                                'observations_preserved': testing_policy.has_observations(c)} for c in excluded],
            'runnable_case_ids': runnable, 'review_required_case_ids': review_required, 'skipped_cases': skipped, 'completed_case_ids': completed, **points,
            'review_required_checkpoints': [ref for ref in recovery['review_required_refs'] if 'checkpoint_id' in ref],
            'recovery': recovery,
            'dependencies_to_check': pending, 'blocked_dependency_groups': blocked_groups,
            'deferred_dependencies': deferred, 'waiting_case_ids': waiting_ids,
            'next_action': {'action': action, 'reason': reason},
            'blocking_summary': blocking_summary(record),
            'execution_summary': {**progress_summary(original), **blocking_summary(record), 'runnable_cases': len(runnable),
                                  'policy_excluded_cases': len(excluded),
                                  'unchecked_dependency_cases': len({cid for g in pending for cid in g['affected_case_ids']}),
                                  'eligibility_note': '可调度仅表示已登记条件未阻断；未声明或未核实的实际依赖仍须检查，不能当作前置已就绪或业务已通过。',
                                  'dependency_skipped_cases': len(skipped), 'waiting_cases': len(waiting_ids),
                                  'blocked_dependency_groups': len(blocked_groups)}}


def record_check(store, owner, pid, execution_id, revision, dependency_id, status, observed, method):
    from . import ui_records, ui_retests
    with store._lock:
        project = ui_records.ui_project(store, owner, pid)
        record = ui_records.load(store, owner, pid, execution_id)
        if project.get('ui_execution_id') != execution_id:
            raise ValueError('只能记录当前任务的共同前置检查')
        if type(revision) is not int or revision != record['revision']:
            raise ValueError('用例已更新，请读取最新 revision 后重试')
        group = next((g for g in groups(record['cases']) if g['id'] == dependency_id), None)
        if not group or group['target_url'] != project.get('ui_target_url'):
            raise ValueError('共同前置条件不存在或目标已变更，请重新建立本轮设计')
        if status not in {'blocked', 'ready'}:
            raise ValueError('共同前置检查状态仅支持 blocked 或 ready')
        if any(not isinstance(v, str) or len(v) > 2000 for v in (observed, method)):
            raise ValueError('检查方法和观察结果必须为文本，各最多 2000 字')
        previous = deepcopy(record)
        checked = ui_retests.redact(store, owner, pid, {'status': status, 'observed': observed.strip(),
                    'method': method.strip(), 'checked_at': datetime.now(timezone.utc).isoformat()})
        record.setdefault('dependency_checks', {})[dependency_id] = checked
        record.setdefault('dependency_check_history', []).append({'dependency_id': dependency_id, **checked})
        before = {c['case_id']: c for c in previous['cases']}
        apply_checks(record)
        for case in active_cases(record['cases']):
            if case != before[case['case_id']]:
                case['updated_at'] = ui_records.now()
        preserve_history(previous, record)
        record['revision'] += 1
        store._write(ui_records.root_for(store, owner, pid, execution_id) / 'cases.json', record)
        progress = progress_record(store, owner, pid, record)
        store.update_project(owner, pid, {'ui_execution_revision': record['revision'], 'ui_progress_record': progress})
        ui_records.sync_regression_results(store, owner, project, record)
        publication = ui_records.refresh_published(store, owner, pid, record)
        return {'execution_id': execution_id, 'revision': record['revision'],
                **publication,
                'blocking_summary': blocking_summary(record),
                'dependency': {**group, 'check': checked}, 'execution_plan': plan(record, recovery=progress['recovery'])}


def blocking_summary(record):
    checks = record.get('dependency_checks', {})
    reasons, affected, unstructured = set(), set(), []
    for case in active_cases(record.get('cases', [])):
        dependencies = remaining_dependencies(case)
        blocked = {d['id'] for d in dependencies if checks.get(d['id'], {}).get('status') == 'blocked'}
        # A finished verdict is retained; partial observations may still have blocked work.
        if case.get('status') not in {'passed', 'failed'} and blocked:
            reasons.update(blocked)
            affected.add(case['case_id'])
        if case.get('status') == 'blocked' and not blocked:
            unstructured.append(case['case_id'])
    return {'reason_count': len(reasons), 'affected_case_count': len(affected),
            'unstructured_blocked_case_count': len(unstructured),
            'reason_ids': sorted(reasons), 'affected_case_ids': sorted(affected),
            'unstructured_blocked_case_ids': unstructured}


def merge_blocking_summaries(records):
    """Join selected report facts; equal titles/keys in another round stay distinct."""
    reasons, affected, unstructured = set(), set(), set()
    for project_id, record in records:
        summary = blocking_summary(record)
        scope = (project_id, record.get('id', ''))
        reasons.update((*scope, gid) for gid in summary['reason_ids'])
        affected.update((*scope, cid) for cid in summary['affected_case_ids'])
        unstructured.update((*scope, cid) for cid in summary['unstructured_blocked_case_ids'])
    return {'reason_count': len(reasons), 'affected_case_count': len(affected),
            'unstructured_blocked_case_count': len(unstructured)}
