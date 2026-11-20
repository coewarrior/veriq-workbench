"""Pure work-stage projections; saved cases remain the sole result authority.

Stages do not create queue entries, accounts, verdicts or another execution.
Only structural changes advance the plan revision.
"""
import copy
import hashlib
import json

from .ui_case_scope import active_cases
from . import ui_dependencies, testing_policy


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def _ids(value, field):
    if (not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in value)
            or len(value) != len(set(value))):
        raise ValueError(field + ' 必须是无重复的非空文本 ID 数组')
    return list(value)


def normalize_work_plan(plan, record, previous=None):
    if not isinstance(plan, dict) or plan.get('schema_version') != 1:
        raise ValueError('work_plan.schema_version 必须为 1')
    if (not record.get('id') or plan.get('execution_id') != record['id']
            or not plan.get('project_id') or record.get('project_id', plan['project_id']) != plan['project_id']):
        raise ValueError('阶段计划必须属于原项目及执行记录')
    if previous and any(previous.get(k) != plan.get(k) for k in ('project_id', 'execution_id')):
        raise ValueError('不能将原节点阶段计划替换为其他执行')
    cases = {c['case_id']: c for c in active_cases(record.get('cases', []))}
    old = {u['id']: u for u in (previous or {}).get('units', [])}
    next_order = max((u['created_order'] for u in old.values()), default=0)
    values = plan.get('units')
    if not isinstance(values, list) or not values:
        raise ValueError('work_plan.units 必须是非空阶段数组')
    units, seen, occupied = [], set(), set()
    for value in values:
        if not isinstance(value, dict):
            raise ValueError('阶段必须是对象')
        uid = value.get('id')
        _ids([uid], '阶段 ID')
        if uid in seen:
            raise ValueError('阶段 ID 不能重复')
        seen.add(uid)
        purpose = value.get('purpose', 'assertion')
        if purpose not in {'assertion', 'cleanup'}:
            raise ValueError('阶段 purpose 使用 assertion 或 cleanup')
        if purpose == 'cleanup' and not value.get('cleanup_responsibility_ids'):
            raise ValueError('清理阶段必须引用本轮已登记的对象责任')
        case_ids = _ids(value.get('case_ids', []), 'case_ids')
        points = value.get('checkpoint_refs', [])
        if not isinstance(points, list) or any(not isinstance(p, dict) or set(p) != {'case_id', 'checkpoint_id'} for p in points):
            raise ValueError('checkpoint_refs 需要 case_id 和 checkpoint_id')
        refs = [(cid, None) for cid in case_ids] + [(p['case_id'], p['checkpoint_id']) for p in points]
        if not refs:
            raise ValueError('阶段必须引用原用例或检查点')
        for cid, point_id in refs:
            if not isinstance(cid, str) or cid not in cases:
                raise ValueError('阶段引用了不存在或已替换的用例')
            if point_id is not None and (not isinstance(point_id, str) or not any(p['id'] == point_id for p in cases[cid].get('checkpoints', []))):
                raise ValueError('阶段引用了不存在的检查点')
            if ((purpose, cid, point_id) in occupied or (purpose, cid, None) in occupied
                    or point_id is None and any(kind == purpose and c == cid for kind, c, _ in occupied)):
                raise ValueError('同一业务断言不能重复安排到多个阶段')
            occupied.add((purpose, cid, point_id))
        requires = value.get('requires')
        if not isinstance(requires, dict) or requires.get('phase') not in {'exploration', 'execution'}:
            raise ValueError('阶段必须明确 exploration/execution 资源要求，未知需求不能当作单账号可做')
        allowed = {'phase', 'requirements', 'account_ids', 'account_selection', 'account_scope', 'locks', 'exclusive_exploration'}
        if set(requires) - allowed:
            raise ValueError('阶段资源包含未知字段')
        accounts = _ids(requires.get('account_ids', []), 'account_ids')
        requirements = requires.get('requirements', [])
        if not isinstance(requirements, list) or len(requirements) > 16 or len(accounts) > 16:
            raise ValueError('每阶段最多 16 个身份需求')
        normalized = []
        for requirement in requirements:
            if not isinstance(requirement, dict) or set(requirement) != {'target', 'environment', 'tenant', 'role'}:
                raise ValueError('身份需求必须明确 target/environment/tenant/role')
            if any(not isinstance(v, str) or not v.strip() or len(v) > 500 for v in requirement.values()):
                raise ValueError('身份需求字段必须为非空文本')
            normalized.append({k: v.strip() for k, v in requirement.items()})
        selection = requires.get('account_selection', 'required')
        scope = requires.get('account_scope')
        if scope not in (None, 'single_account'):
            raise ValueError('阶段 account_scope 仅支持明确的 single_account；多账号场景按全局规则不测')
        project_single = scope == 'single_account' and selection == 'preferred' and not normalized
        if project_single:
            # The caller explicitly declares interchangeable single-account work.
            # Never reinterpret existing required selections or cleanup bindings.
            if (len(accounts) > 1 or purpose == 'cleanup' or value.get('resume_ref')
                    or any(cases[cid].get('account_scope') != 'single_account'
                           and not testing_policy.case_excluded(cases[cid]) for cid, _ in refs)):
                raise ValueError('项目内可替换阶段必须明确为独立单账号用例；原现场续接和清理责任保留原账号绑定')
        if not accounts and not normalized and not project_single:
            raise ValueError('阶段需明确完整账号集合或身份需求')
        if selection not in {'required', 'preferred'} or selection == 'preferred' and not normalized and not project_single:
            raise ValueError('偏好账号不能代替完整身份需求')
        exclusive = requires.get('exclusive_exploration', False)
        if type(exclusive) is not bool or exclusive and requires['phase'] != 'exploration':
            raise ValueError('exclusive_exploration 只能用于探索阶段')
        resource = {'phase': requires['phase'], 'requirements': normalized, 'account_ids': accounts,
                    'account_selection': selection, 'locks': _ids(requires.get('locks', []), 'locks'),
                    'exclusive_exploration': exclusive}
        if scope:
            resource['account_scope'] = scope
        if uid not in old:
            next_order += 1
        resume = value.get('resume_ref', '')
        if not isinstance(resume, str) or len(resume) > 2000:
            raise ValueError('resume_ref 必须是原现场引用文本')
        units.append({'id': uid, 'created_order': old[uid]['created_order'] if uid in old else next_order,
                      'case_ids': case_ids, 'checkpoint_refs': copy.deepcopy(points), 'requires': resource,
                      'depends_on': _ids(value.get('depends_on', []), 'depends_on'), 'resume_ref': resume,
                      **({'purpose': 'cleanup', 'cleanup_responsibility_ids': _ids(value.get('cleanup_responsibility_ids', []), 'cleanup_responsibility_ids')} if purpose == 'cleanup' else {})})
    by_id = {u['id']: u for u in units}
    visiting, visited = set(), set()
    def visit(uid):
        if uid not in by_id or uid in visiting:
            raise ValueError('阶段依赖不存在或形成循环')
        if uid in visited:
            return
        visiting.add(uid)
        for parent in by_id[uid]['depends_on']:
            visit(parent)
        visiting.remove(uid)
        visited.add(uid)
    for uid in by_id:
        visit(uid)
    units.sort(key=lambda u: u['created_order'])
    return {'schema_version': 1, 'project_id': plan['project_id'], 'execution_id': record['id'],
            'plan_revision': (previous or {}).get('plan_revision', 0) + int(not previous or previous['units'] != units),
            'validated_record_revision': record['revision'], 'units': units}


def project_work_candidates(node, record_view):
    work = node.get('checkpoint', {}).get('work_plan')
    if not work or not record_view:
        return []
    # Revalidate active references, but never overwrite or advance a saved plan.
    work = normalize_work_plan(work, record_view, work)
    cases = {c['case_id']: c for c in active_cases(record_view['cases'])}
    # Codex explicitly chooses these work stages. Business prerequisite notes
    # are diagnostics, not a second resource authorization or verdict engine.
    runnable = {cid for cid, case in cases.items() if case['status'] not in {'passed', 'failed'}}
    point_ready = {(cid, p['id']) for cid, case in cases.items()
                   for p in case.get('checkpoints', []) if p['status'] not in {'passed', 'failed'}}
    def statuses(unit):
        return [cases[c]['status'] for c in unit['case_ids']] + [
            next(p['status'] for p in cases[r['case_id']]['checkpoints'] if p['id'] == r['checkpoint_id'])
            for r in unit['checkpoint_refs']]
    receipts = node.get('work_unit_receipts', {})
    def cleanup_done(unit):
        receipt = receipts.get(unit['id'], {})
        return receipt.get('completed') is True and receipt.get('unit_digest') == _digest(unit)
    finished_before = {u['id']: cleanup_done(u) if u.get('purpose') == 'cleanup' else
                       all(s in {'passed', 'failed'} for s in statuses(u)) for u in work['units']}
    result = []
    for unit in work['units']:
        cids = [cid for cid in unit['case_ids'] if cid in runnable]
        points = [p for p in unit['checkpoint_refs'] if (p['case_id'], p['checkpoint_id']) in point_ready]
        cleanup = unit.get('purpose') == 'cleanup'
        if cleanup:
            cids, points = unit['case_ids'], unit['checkpoint_refs']
        finished = cleanup_done(unit) if cleanup else all(s in {'passed', 'failed'} for s in statuses(unit))
        eligible = not finished and bool(cids or points) and all(finished_before[d] for d in unit['depends_on'])
        req = unit['requires']
        referenced = unit['case_ids'] + [p['case_id'] for p in unit['checkpoint_refs']]
        excluded = not cleanup and (testing_policy.resource_excluded(req)
                    or all(testing_policy.case_excluded(cases[cid]) for cid in referenced))
        from .resource_projection import copy_node
        projected = copy_node(node)
        projected.update(phase=req['phase'], requirements=copy.deepcopy(req['requirements']),
                         requested_account_ids=req['account_ids'] if req['account_selection'] == 'required' else [],
                         preferred_account_ids=req['account_ids'] if req['account_selection'] == 'preferred' else [],
                         locks=list(dict.fromkeys([*node.get('inherited_locks', []), *req['locks']])),
                         exclusive_exploration=req['exclusive_exploration'], exploration_complete=req['phase'] != 'exploration')
        projected['policy_cleanup_unit_id'] = unit['id'] if cleanup else ''
        token = {'work_unit_id': unit['id'], 'plan_revision': work['plan_revision'], 'requirements_digest': _digest(req)}
        result.append({**token, 'unit_id': unit['id'], 'unit_digest': _digest(unit), 'created_order': unit['created_order'],
                       'projected_node': projected, 'eligibility': 'completed' if finished else 'excluded' if excluded else 'ready' if eligible else 'waiting_prerequisite',
                       'exclusion_reason': testing_policy.REASON if excluded else '',
                       'case_ids': cids if eligible else [], 'checkpoint_refs': points if eligible else [],
                       'source_revision': record_view['revision'],
                       **({'purpose': 'cleanup', 'cleanup_responsibility_ids': unit.get('cleanup_responsibility_ids', [])} if cleanup else {})})
    return result


def _lease_matches(projected, lease):
    accounts = lease.get('account_ids', [])
    if not set(projected['requested_account_ids']) <= set(accounts):
        return False
    if not set(projected['locks']) <= set(lease.get('locks', [])):
        return False
    if lease.get('mode') == 'shared' and (projected['phase'] != 'exploration'
            or projected['exclusive_exploration'] or projected['locks'] or len(projected['requested_account_ids']) > 1):
        return False
    available = lease.get('accounts', [])
    # Assign a distinct physical login to each required identity, just like the scheduler.
    def assign(index, used):
        reqs = projected['requirements']
        if index == len(reqs):
            return True
        req = reqs[index]
        for account in available:
            key = (account.get('target', '').rstrip('/').lower(), account.get('identity'))
            if key not in used and account.get('id') in accounts and all(
                    account.get(k, '').rstrip('/') == req[k].rstrip('/') for k in ('target', 'environment', 'tenant')) and req['role'] in account.get('roles', []):
                if assign(index + 1, used | {key}):
                    return True
        return False
    return assign(0, set())


def select_next_work(record, work_plan, lease_view):
    candidates = project_work_candidates({'checkpoint': {'work_plan': work_plan},
        'work_unit_receipts': lease_view.get('work_unit_receipts', {})}, record)
    runnable, points, waiting_resource, waiting_prerequisite, completed, units = [], [], [], [], [], []
    excluded = []
    for candidate in candidates:
        if candidate['eligibility'] == 'excluded':
            excluded.append(candidate['unit_id'])
        elif candidate['eligibility'] == 'completed':
            completed.append(candidate['unit_id'])
        elif candidate['eligibility'] != 'ready':
            waiting_prerequisite.append(candidate['unit_id'])
        elif not _lease_matches(candidate['projected_node'], lease_view):
            waiting_resource.append(candidate['unit_id'])
        else:
            units.append(candidate['unit_id'])
            runnable.extend(candidate['case_ids'])
            points.extend(candidate['checkpoint_refs'])
    return {'runnable_case_ids': runnable, 'runnable_checkpoints': points, 'runnable_unit_ids': units,
            'waiting_resource_unit_ids': waiting_resource, 'waiting_prerequisite_unit_ids': waiting_prerequisite,
            'completed_unit_ids': completed, 'excluded_unit_ids': excluded,
            'testing_policy': testing_policy.snapshot(), 'source_revision': record['revision']}
