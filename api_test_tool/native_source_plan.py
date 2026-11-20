"""Original-module planning and formal continuation through the existing queue."""
import copy

from .orchestration import Conflict, digest, uid
from .native_identity import same_executor_ref


def authority(controller, state, owner, args):
    node = controller.owned(state['nodes'], owner, args.get('node_id'))
    task = controller.owned(state['tasks'], owner, args.get('task_id'))
    binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
    ended = state.get('direct_settlements', {}).get(args.get('lease_id')) or {}
    resumed = ended.get('same_node_resume') or {}
    prior = ended.get('report_binding') or {}
    # A lost work-plan reply can retrieve its already-resumed original node.
    # This does not authorize old claims or old report writes.
    replay = bool(resumed
        and ended.get('owner') == owner and ended.get('node_id') == node['id']
        and ended.get('holder_id') == args.get('holder_id')
        and prior.get('dispatch_id') == args.get('dispatch_id')
        and same_executor_ref(prior.get('executor_ref'), args.get('executor_ref'))
        and resumed.get('dispatch_id') == binding.get('dispatch_id')
        and resumed.get('plan_digest') == digest((args.get('arguments') or {}).get('work_plan')))
    if (node['task_id'] != task['id'] or binding.get('holder_id') != args.get('holder_id')
            or ((binding.get('dispatch_id') or binding.get('id')) != args.get('dispatch_id') and not replay)
            or not same_executor_ref(binding.get('executor_ref'), args.get('executor_ref'))):
        raise PermissionError('阶段计划仅属于原模块及其实际派发会话')
    controller.sessions.assert_available(state, task, [node['id']])
    if task['intent'] != 'run' or node.get('control_intent', 'run') != 'run':
        raise Conflict('任务已停止或暂停；登记阶段不能恢复执行')
    return node, task, replay


def continue_source(native, state, node, task, args, plan):
    """Resume the original module in normal FIFO, retaining its saved history."""
    controller = native.c
    ended = state.get('direct_settlements', {}).get(args.get('lease_id'))
    if not ended:
        raise Conflict('缺少原租约的真实交还凭据；先完成原退出核实')
    native.released_report_scope(state, node['owner'], {**args, 'record_action': 'record',
        'arguments': {'project_id': node['record_project_id'], 'execution_id': node['record_execution_id']}}, ended)
    native.require_report_settled(state, node)
    if node.get('native_report_pending') or node.get('finalization_pending'):
        raise Conflict('原报告仍在收尾；先沿原已交还绑定完成报告，不重新领取账号')
    if any(other['id'] != node['id'] and not other.get('record_successor_node_id')
           and other.get('record_project_id') == node['record_project_id']
           and other.get('record_execution_id') == node['record_execution_id']
           and other['state'] not in {'completed', 'blocked', 'container'} for other in state['nodes'].values()):
        raise Conflict('原记录已有其他执行代次；不能创建第二个写入者')
    now = controller.clock()
    state['next_queue_sequence'] = state.get('next_queue_sequence', 0) + 1
    node.update(state='queued', revision=node['revision'] + 1, queued=now,
        queue_sequence=state['next_queue_sequence'],
        protected=False, reservation=None, reservation_expirations=0, waiting_since=now,
        reason='原模块续测，等待原完整账号队列')
    for key in ('direct_holder', 'native_claim_pending', 'work_selection', 'work_protection',
                'resource_wait', 'execution_ended'):
        node.pop(key, None)
    offer = node.pop('dispatch_offer', None)
    if offer:
        node.setdefault('dispatch_offer_history', []).append(copy.deepcopy(offer))
    dispatch = node.get('executor_dispatch') or {}
    if dispatch:
        node.setdefault('executor_dispatch_history', []).append(copy.deepcopy(dispatch))
    node['executor_dispatch'] = {key: dispatch[key] for key in ('holder_id', 'executor_ref', 'coordinator_ref') if key in dispatch}
    node['executor_dispatch'].update(dispatch_id=uid(), received_at=now, last_seen_at=now,
                                     receipt_source='explicit_source_resume',
                                     resumed_from_dispatch_id=dispatch.get('dispatch_id'),
                                     resumed_from_lease_id=args['lease_id'])
    # Reuse the existing offer identity check on claim; old kits cannot replace
    # the current dispatch just because the module ID now stays the same.
    node['dispatch_offer'] = {key: value for key, value in node['executor_dispatch'].items()
                              if key in {'holder_id', 'executor_ref', 'coordinator_ref'}}
    node['dispatch_offer'].update(id=node['executor_dispatch']['dispatch_id'],
        state='received', created_at=now, received_at=now, executor_kind='codex_thread', reason='原节点续测')
    status = node.pop('native_executor_status', None)
    if status:
        node.setdefault('native_executor_status_history', []).append(status)
    ended['same_node_resume'] = {'dispatch_id': node['executor_dispatch']['dispatch_id'],
                                 'plan_digest': digest(plan), 'resumed_at': now}
    task['revision'] += 1
    if node.get('parent_id'):
        parent = state['nodes'][node['parent_id']]
        if parent['state'] == 'completed':
            parent['state'] = 'container'
            parent.pop('finalization_pending', None)
    return node


def call(native, owner, args):
    from . import ui_records
    from .native_work_plan import update_work_plan, TOKEN_FIELDS
    from .execution_work_plan import normalize_work_plan, project_work_candidates
    values = args.get('arguments') or {}
    plan = values.get('work_plan')
    if not isinstance(plan, dict):
        raise ValueError('work_plan 必须是原用例阶段对象')
    # An infrequent stage boundary uses the existing DB -> Store order and one
    # source record. No all-active-record preload or per-observation new call.
    with native.c.transaction() as (_, state):
        original, task, resumed = authority(native.c, state, owner, args)
        node = original
        continuation = node.get('record_successor_node_id')
        if continuation:
            node = state['nodes'][continuation]
            if node.get('continuation_plan_digest') != digest(plan):
                raise Conflict('原模块已正式续接；请沿返回的新模块绑定修改计划')
            native.c.sessions.assert_available(state, task, [node['id']])
            if node.get('control_intent', 'run') != 'run':
                raise Conflict('续接模块已停止，原请求不能恢复执行')
        pid, eid = node.get('record_project_id'), node.get('record_execution_id')
        project = native.service.store.get_project(owner, pid)
        if project.get('ui_execution_id') != eid:
            raise Conflict('原执行记录已变化，不能把阶段计划写入其他轮次')
        record = {**ui_records.load(native.service.store, owner, pid, eid), 'project_id': pid}
        if not continuation and not resumed:
            previous = node.get('checkpoint', {}).get('work_plan')
            proposed = normalize_work_plan(plan, record, previous)
            if (previous and values.get('expected_plan_revision') != previous['plan_revision']
                    and proposed['units'] != previous['units']):
                raise Conflict('阶段计划已被修订，保留原请求并核对当前计划')
            if node['state'] in {'completed', 'blocked'}:
                from .cleanup_capabilities import settle_units
                preview = {**node, 'checkpoint': {**node.get('checkpoint', {}), 'work_plan': proposed},
                           'work_unit_receipts': copy.deepcopy(node.get('work_unit_receipts', {}))}
                settle_units(state, preview, native.c.clock())
                if any(c['eligibility'] not in {'completed', 'excluded'} for c in project_work_candidates(preview, record)):
                    node = continue_source(native, state, node, task, args, plan)
                    continuation = node['id']
            elif node['state'] not in {'queued', 'running'}:
                raise Conflict('当前模块尚不允许规划或续接，先核对原退出状态')
            normalized = update_work_plan(native.c, state, node, plan, record)
        else:
            normalized = node['checkpoint']['work_plan']
        from .cleanup_capabilities import continuation_sources, settle_units, owns_plan_responsibility
        from .cleanup_contract import CleanupScopeError
        allowed_sources = {node['id']} | continuation_sources(state, node)
        original_case_ids = {case['case_id'] for case in record['cases']}
        for unit in normalized['units']:
            for responsibility_id in unit.get('cleanup_responsibility_ids', []):
                obj = state.get('cleanup_objects', {}).get(responsibility_id)
                if (not owns_plan_responsibility(state, node, obj, allowed_sources)
                        or obj['case_id'] not in original_case_ids):
                    raise CleanupScopeError('清理阶段只能引用本模块原执行记录内登记的对象责任；不能引用其他模块、任务或记录')
        settle_units(state, node, native.c.clock())
        result = {'saved': True, 'work_plan': copy.deepcopy(normalized), 'node_id': node['id']}
        if continuation or resumed:
            from .testing_roles import worker_packet
            from .resource_scheduler import ResourceScheduler
            packet = worker_packet(task, node, native.service.store.get_project(owner, task['project_id']))
            packet['assignment']['resume_record'] = {'project_id': pid, 'execution_id': eid}
            selected = ResourceScheduler(native.c, state, native.c.clock()).select_work_candidate(node, record, for_wake=True)
            if selected:
                packet['assignment']['claim_arguments'] = {'work_token': {key: selected[key] for key in TOKEN_FIELDS}}
            result.update(continuation_packet=packet, source_record=record,
                          resumed_original_node=node['id'] == original['id'],
                          next_action='prepare_formal_continuation' if selected else 'review_original_prerequisites')
        return result
