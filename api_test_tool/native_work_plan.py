"""Control-plane work-plan adapters. Read result files before taking the SQL writer."""
import copy

from .execution_work_plan import normalize_work_plan, project_work_candidates

RESOURCE_FIELDS = ('phase', 'requirements', 'requested_account_ids', 'preferred_account_ids',
                   'locks', 'exclusive_exploration', 'exploration_complete', 'policy_cleanup_unit_id')
TOKEN_FIELDS = ('work_unit_id', 'plan_revision', 'requirements_digest')
BINDING_FIELDS = ('owner', 'task_id', 'revision', 'record_project_id', 'record_execution_id')


def token_matches(node, token):
    from .execution_work_plan import _digest
    plan = node.get('checkpoint', {}).get('work_plan', {})
    if not plan:
        return token is None
    if not isinstance(token, dict) or token.get('plan_revision') != plan['plan_revision']:
        return False
    unit = next((u for u in plan['units'] if u['id'] == token.get('work_unit_id')), None)
    return bool(unit and token.get('requirements_digest') == _digest(unit['requires']))


def validate_token(controller, state, node, token):
    from .orchestration import Conflict
    task = state['tasks'][node['task_id']]
    if task['intent'] != 'run' or node.get('control_intent', 'run') != 'run':
        raise Conflict('task_not_running: 任务已停止或暂停；旧通知不恢复执行')
    if node['state'] not in {'queued', 'running'}:
        raise Conflict('node_not_resumable: 原节点已结束或正在退出；不能用领取恢复原终态')
    if not isinstance(token, dict) or any(not token.get(k) for k in TOKEN_FIELDS):
        raise Conflict('work_token_missing: 恢复请求缺少完整阶段令牌；请用 native-resume 接入原通知')
    if not token_matches(node, token):
        raise Conflict('work_token_stale: 阶段计划版本或资源要求已变化；保留原记录，不使用旧通知')
    record = record_view(state, node)
    if record is None:
        raise Conflict('stage_record_unavailable: 原阶段绑定的报告不可读或已变化；未授权恢复')
    candidates = project_work_candidates(node, record)
    candidate = next((c for c in candidates if c['unit_id'] == token['work_unit_id']), None)
    if candidate is None:
        raise Conflict('work_unit_missing: 通知阶段不在原计划中')
    if candidate['eligibility'] == 'completed':
        raise Conflict('work_unit_completed: 原阶段已完成；保留结果，不重跑')
    if candidate['eligibility'] not in {'ready', 'excluded'}:
        raise Conflict('work_prerequisite_unready: 原阶段的必要前置尚未通过；核对确实依赖的检查点，独立阶段可继续')
    return candidate


def load_record_views(controller, *, node_ids=None):
    from .orchestration_storage import read_node_fields
    from . import ui_records
    with controller.connect() as db:
        nodes = read_node_fields(db, ('id', *BINDING_FIELDS),
                                 states=('queued', 'running', 'starting', 'stopping'))
    views = {}
    for node in nodes.values():
        if node_ids is not None and node['id'] not in node_ids:
            continue
        pid, eid = node.get('record_project_id'), node.get('record_execution_id')
        if not pid or not eid:
            continue
        try:
            project = controller.store.get_project(node['owner'], pid)
            if project.get('ui_execution_id') != eid:
                continue
            record = ui_records.load(controller.store, node['owner'], pid, eid)
            views[node['id']] = {'binding': {k: node.get(k) for k in BINDING_FIELDS},
                                 'record': {**record, 'project_id': pid}}
        except (FileNotFoundError, ValueError, OSError):
            continue  # Unreadable facts never grant eligibility.
    return views


def record_view(state, node):
    view = state.get('_work_record_views', {}).get(node['id'], {})
    if view.get('binding') != {k: node.get(k) for k in BINDING_FIELDS}:
        return None
    return view.get('record')


def apply_selection(node, candidate):
    projected = candidate['projected_node']
    for key in RESOURCE_FIELDS:
        node[key] = copy.deepcopy(projected[key])
    node['work_selection'] = {k: candidate[k] for k in (*TOKEN_FIELDS, 'unit_digest')}
    if node.get('protected'):
        node['work_protection'] = copy.deepcopy(node['work_selection'])
    else:
        node.pop('work_protection', None)


def reconcile_protection(state, node):
    prior = node.get('work_protection')
    record = record_view(state, node)
    if not prior or not record:
        return
    try:
        valid = any(c['unit_id'] == prior['work_unit_id'] and c['unit_digest'] == prior['unit_digest']
                    and c['eligibility'] == 'ready' for c in project_work_candidates(node, record))
    except ValueError:
        valid = False
    if not valid:
        node.pop('work_protection', None)
        node.pop('work_selection', None)
        node['protected'] = False
        node['reservation'] = None


def update_work_plan(controller, state, node, plan, record):
    from .direct_execution import DirectExecutionDenied
    if (not record or node.get('record_project_id') != plan.get('project_id')
            or node.get('record_execution_id') != plan.get('execution_id')):
        raise ValueError('阶段计划与原节点记录绑定不一致或记录不可读')
    old = node.get('checkpoint', {}).get('work_plan')
    normalized = normalize_work_plan(plan, record, old)
    projected = {**node, 'checkpoint': {**node.get('checkpoint', {}), 'work_plan': normalized}}
    candidates = project_work_candidates(projected, record)
    from .resource_scheduler import ResourceScheduler
    scheduler = ResourceScheduler(controller, state, controller.clock())
    for candidate in candidates:
        target = candidate['projected_node']
        eligible = {a['id'] for a in scheduler.eligible(target)}
        if any(a not in eligible for a in [*target['requested_account_ids'], *target['preferred_account_ids']]):
            raise DirectExecutionDenied('stage_account_scope_mismatch: 阶段账号不属于本任务已绑定的账号项目、目标或可用范围；由原协调者核对项目/入口，不重复领取或扩权')
        if any(r['target'].rstrip('/') != scheduler.target(target) for r in target['requirements']):
            raise DirectExecutionDenied('stage_target_mismatch: 阶段身份需求越出本任务目标；不能把其他入口的账号硬塞入原模块')
    for field in ('work_selection', 'work_protection'):
        prior = node.get(field)
        if not prior:
            continue
        same = next((c for c in candidates if c['unit_id'] == prior['work_unit_id']
                     and c['unit_digest'] == prior.get('unit_digest') and c['eligibility'] == 'ready'), None)
        if same:
            node[field] = {k: same[k] for k in (*TOKEN_FIELDS, 'unit_digest')}
        else:
            node.pop(field, None)
            if field == 'work_protection':
                node['reservation'] = None
                node['protected'] = False
    node.setdefault('checkpoint', {})['work_plan'] = normalized
    return normalized
