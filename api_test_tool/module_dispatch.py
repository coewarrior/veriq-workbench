"""Expose the existing task tree to the connected Codex coordinator.

No model spawning or resource allocation here: each delegated worker claims its
own leaf through DirectExecution and the existing atomic account queue.
"""
from .orchestration import Conflict, digest


from .testing_policy import GUIDANCE as TESTING_POLICY_GUIDANCE


COORDINATION_GUIDANCE = TESTING_POLICY_GUIDANCE + (
    '协调通知按当前 coordination_plan 定向处理：worker_actions 仅列尚未收到的原控制指令，'
    'continuations 仅列原交接中真实可接续的目标，并继续使用原发送占用和回执。'
    'coordinator_only 的阻塞/待核实由协调者处理，不能把另一模块的登录疑问、进度或通用提醒转发给正常执行者。'
    'keep_running 中的模块继续原工作，不重复提醒或要求重新核实已确认事项。'
    '只有真实新事实使目标下一步或授权发生变化，才沿原任务控制/依赖更新后定向通知；'
    '用户停止仍传达全部实际受影响执行者，已收到的同一控制不重复发送。'
    '该计划不是桌面消息拦截器；不得绕过计划自行群发，也不把计划生成当成消息已送达。'
)


ROUND_SESSION_GUIDANCE = (
    '新独立测试（含明确新回归）首次派发时新建本轮协调聊天和每模块独立 Codex 聊天；'
    '当前聊天已为本轮新建时直接担任协调者，不递归另建。'
    '同轮续测、恢复或重复复制同一 MCP 任务消息，沿本轮真实 coordinator_ref/executor_ref 和检查点继续，不重复创建执行者。'
    '跨 task_id 的同轮续测沿 continuation_source/source_node_id/resume_record 追溯原绑定；'
    '相同项目、URL、模块名不证明同轮；当前 task_id 已有模块计划/设计不代表上一轮，历史记录或 continuation_modules 候选也不自动表示续测。'
)


GUIDANCE = (
    ROUND_SESSION_GUIDANCE
    + '协调者先按本轮选择真实模块聊天，再调用 direct_test_session(action="dispatch",holder_id=协调者标识,task_id=原任务,request_id=稳定请求ID,arguments={modules:[{node_id,dispatch_id,holder_id,executor_ref}]}) 保存实际派发；每个模块各自使用独立 Codex 会话（新建用 create_thread），不使用子 agent；实际 thread_id 写入 executor_ref；执行者 claim 携带同一 dispatch_id。无执行者槽位的叶子登记 state=waiting_capacity 及真实 reason，释放槽位后更新同一节点；不能混称账号等待。派发超时由协调者核对原执行者后重投，过期 dispatch_id 不再有效，不能重复启动未知执行者。停止时中断全部相关模块会话，各自 finish 确认退出；pending_controls、账号释放和 settlement_acknowledged 是不同事实。'
    '明确同轮续测且已有记录时读取 continuation_modules，以 source_node_id 绑定原模块；返回的 resume_record 合入 assignment，复用原聊天并为当前 task/node 使用独立目录沿原 --resume 续接。'
    '保留已有结果与业务关联，仅推进未完项和新增授权覆盖；明确新回归走原回归入口，不自动重跑历史通过。'
    '用户列出具体模块时，先用 start_session_test(modules=[{key,title,scope,depends_on,locks},...]) '
    '登记模块树，再由本轮协调者为每个返回的叶子节点按上述轮次规则安排独立 Codex 会话并行执行，不使用子 agent 合并分工；'
    '由协调者自动创建模块会话，不要求用户手工另开聊天，不启动后台 Codex。大任务先探索，再按真实业务独立性拆分。'
    '协调者不领取业务账号；每个执行者使用独立稳定 holder_id、明确 node_id 和独立本地目录，'
    '调用原 direct_test_session claim/context/credentials/browser/record/finish。'
    '账号与浏览器由原队列分配，无资源的模块排队；依赖或共享业务锁只约束相关模块。'
    '未取得账号的模块会话停止本地领取循环并结束当前轮次，不反复claim、wait_threads或自唤醒。协调者记录原节点、holder、dispatch和续测位置，使用原单节点暂停入口核实无租约并保留排队顺位；账号交还后按原公平顺位恢复并唤醒对应原会话，不让全部等待会话同时空转。暂停竞争中若已分配租约，必须核实退出，不能当作无账号直接释放。'
    '报告模块不等于账号数，不把一条聊天当成只能一个执行者。'
    '没有独立会话创建能力时如实说明缺失能力，不回退为子 agent 合并分工，不能把串行执行宣称为并发。'
    '模块会话只写 context.project.id 对应的模块记录，父会话汇总；不得共同修改父用例修订号。'
    '人工问题回到协调聊天，停止须传达所有模块会话并按原任务停止/退出确认回收；'
    '不得为了拆分重新执行已有结果、丢弃历史基线或提前删除其他模块仍使用的前置。'
    + COORDINATION_GUIDANCE
)

NATIVE_GUIDANCE = (
    ROUND_SESSION_GUIDANCE
    + 'executor_ref/coordinator_ref沿平台原值传递；真实裸UUID与thread:UUID等价，不要手工改写assignment或换会话规避冲突。'
    + '当前为协调者职责：读取平台随包 references/coordinator.md，先登记全部授权模块、本轮独立聊天及真实coordinator_ref。'
    '按每模块worker_packet的assignment/module/task_material/first_read分别派发给本轮绑定的执行者；明确模型及推理档位应用到本轮聊天，'
    '不要把其他模块调度说明放入worker包。协调者不领取业务账号，不使用Runner model_slots。'
    '跨task本轮授权集合沿原dispatch.arguments.continuation_group登记；已有续测沿continuation_modules/source_node_id/resume_record。'
    '派发后执行coordinator_wait入口，在原协调回合内有限wait_threads并只读对账；不退出后承诺后台运行。'
    '释放者原closeout编排直接通知可用原后继为主；协调者只兜底真实未落实交接、原控制或异常。'
    'sent、消费、claim尝试、实际获租约分别看，unknown/sending不重发；时间只用于观察，不能判模型失败或释放。'
    '用户继续已停止模块时，使用控制响应 resumed_modules 中的新 worker_packet 接续原会话，或读取当前派发包；旧 dispatch_id 不再领取，不另建同名模块。'
    '实际桌面模型错误沿原executor_status绑定/代际回报，不改模型、不重放未知动作。'
    '正常执行者继续，不广播兄弟模块疑问；S1平台停止、桌面停止、浏览器退出与账号交还分别核实。'
    '收尾对照原目标和资料消费逐项review_notes，核对独立场景case_id及本轮证据/缺口，不能只看失败列表和计数。'
    '待授权、待人工步骤、待规则、客观依赖和工具故障分开汇总；存在未解决pending_action不能称无需用户处理。'
    + COORDINATION_GUIDANCE
)


def coordination_plan(nodes, continuations=(), observation=None):
    """Project only real control/wake changes into worker notification targets.

    An issue in a sibling is coordinator work, not evidence that every worker
    needs a message. This is advice for the desktop sender, not a send receipt
    or a new authorization/dispatch mechanism. Existing control and durable
    continuation protocols keep their stop and uncertain-delivery semantics.
    """
    worker_actions, coordinator_only, keep_running, resumes = [], [], [], []
    wake_nodes = set()
    for event in continuations:
        # Sending/unknown/sent events must not become a fresh send suggestion.
        if (event.get('kind') == 'resume_original_worker'
                and event.get('delivery_state') == 'pending'
                and event.get('delivery_required') and event.get('message_arguments')):
            resumes.append({key: event.get(key) for key in
                            ('id', 'task_id', 'node_id', 'delivery_state')})
            wake_nodes.add(event['node_id'])
    for node in nodes:
        if node.get('child_ids'):
            continue
        binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
        target = {'task_id': node['task_id'], 'node_id': node['id'],
                  'executor_ref': binding.get('executor_ref', '')}
        controls = [control for control in node.get('executor_controls', {}).values()
                    if control.get('state') not in {'exited', 'obsolete'}]
        pending = [control for control in controls
                   if control.get('action') in {'stop', 'pause', 'timeout'}
                   and control.get('state') == 'pending']
        for control in pending:
            worker_actions.append({**target, 'kind': 'existing_executor_control',
                'control_id': control['id'], 'action': control['action'],
                'holder_id': control.get('holder_id'),
                'executor_ref': control.get('executor_ref') or target['executor_ref'],
                'entry': 'original_control_and_exit_ack'})
        if pending:
            continue
        if controls:
            coordinator_only.append({**target, 'reason': 'existing_control_waiting_for_exit_or_resume',
                                     'control_ids': [control['id'] for control in controls]})
        elif (node.get('native_executor_status') or {}).get('state') == 'unavailable':
            coordinator_only.append({**target, 'reason': node['native_executor_status']['reason'],
                                     'state': 'model_unavailable'})
        elif node.get('state') in {'blocked', 'isolated', 'retained', 'waiting_human', 'stopping'}:
            coordinator_only.append({**target, 'reason': node.get('reason', ''),
                                     'state': node['state']})
        elif node.get('state') == 'running' and node.get('control_intent', 'run') == 'run':
            keep_running.append(target)
        elif node.get('state') == 'queued' and node['id'] not in wake_nodes:
            coordinator_only.append({**target, 'state': 'queued',
                                     'reason': 'wait_for_original_resource_or_dependency_event'})
    return {'policy': 'targeted_state_change_only', 'worker_actions': worker_actions,
            'continuations': resumes, 'coordinator_only': coordinator_only,
            'keep_running': keep_running, 'automatic_delivery': False,
            **({'handoff_observation': observation} if observation is not None else {})}


def apply_initial_plan(workflow, owner, task_id, modules):
    """Replace only the unclaimed placeholder created by the normal UI start.

    Repeated delivery of an identical plan returns the same leaves. An active
    task is never replaced; it keeps the existing safe-checkpoint handoff.
    """
    with workflow.controller.transaction() as (db, state):
        apply_initial_plan_in_transaction(workflow.controller, db, state, owner, task_id, modules)


def apply_initial_plan_in_transaction(c, db, state, owner, task_id, modules):
    """Validate and bind within the caller's task-creation/plan transaction."""
    if not isinstance(modules, list) or not 1 <= len(modules) <= 100 or any(not isinstance(m, dict) for m in modules):
        raise ValueError('modules 需为 1–100 个模块对象；沿用原任务树格式上限，不是并发上限')
    signature = digest(modules)
    task = c.owned(state['tasks'], owner, task_id)
    if task.get('initial_module_plan_hash') == signature:
        return
    if task['intent'] != 'run':
        raise Conflict('原任务已暂停或停止；登记模块不能恢复执行')
    nodes = [state['nodes'][nid] for nid in task['node_ids']]
    if len(nodes) != 1 or nodes[0]['key'] != 'session':
        raise Conflict('原模块计划已存在；查询并沿用原节点，不重复派发')
    node = nodes[0]
    if node['state'] != 'queued' or node.get('direct_holder') or node.get('attempts'):
        raise Conflict('原节点已领取；沿原执行者在安全检查点交还后拆分，不创建竞争执行者')
    if any(l['node_id'] == node['id'] for l in state['leases'].values()):
        raise Conflict('原节点已有租约，先沿原执行者安全交还')
    project = c.store.get_project(owner, task['project_id'])
    from . import module_continuation
    if task.get('baseline'):
        raise Conflict('已有用例基线保留原归属；不能用新的初始模块计划覆盖已有轮次')
    sources = []
    if project.get('ui_execution_id') or module_continuation.candidates(state, task) or any(m.get('source_node_id') for m in modules):
        if not task.get('session_workflow'):
            raise Conflict('已有用例基线保留原归属；请沿原会话续测入口登记模块')
        sources = module_continuation.resolve(c, state, owner, task, modules)
    split = c._split(db, state, owner, node, modules)
    for index, (child_id, module) in enumerate(zip(split['child_ids'], modules)):
        state['nodes'][child_id]['plan_key'] = str(module.get('key', index))
    if sources:
        module_continuation.bind(state, task, split['child_ids'], sources)
    task['initial_module_plan_hash'] = signature


def browser_assignment(task, node):
    if task.get('native_browser_policy') != 'direct_isolated':
        return {}
    return {'browser_mode': 'isolated', 'direct_browser': {
        'context_count': max(1, len(node.get('requested_account_ids') or []), len(node.get('requirements') or []))}}


def record_assignment(node):
    if not node.get('record_project_id') or not node.get('record_execution_id'):
        return {}
    if (not node.get('continuation_source')
            and not (node.get('executor_dispatch') or {}).get('resumed_from_dispatch_id')):
        return {}
    return {'resume_record': {'project_id': node['record_project_id'], 'execution_id': node['record_execution_id']},
            **({'continuation_source': node['continuation_source']} if node.get('continuation_source') else {})}


def case_recovery(controller, owner, task, nodes):
    """Read the saved compact recovery projection, never poll full case bodies."""
    if task['intent'] != 'run':
        return []
    result = []
    for node in nodes:
        binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
        if (not binding.get('executor_ref') or node.get('child_ids') or node.get('record_successor_node_id')
                or node.get('control_intent', 'run') != 'run' or node.get('session_removed')
                or node.get('execution_disposition') == 'multi_account_excluded'
                or node['state'] in {'stopping', 'stopped', 'paused', 'isolated', 'retained'}):
            continue
        pid, eid = node.get('record_project_id'), node.get('record_execution_id')
        if not pid or not eid:
            continue
        try:
            project = controller.store.get_project(owner, pid)
        except FileNotFoundError:
            continue
        progress = project.get('ui_progress_record') or {}
        recovery = progress.get('recovery') or {}
        if (project.get('ui_execution_id') != eid or progress.get('execution_id') != eid
                or progress.get('revision') != project.get('ui_execution_revision')
                or recovery.get('source_revision') != progress.get('revision')):
            continue
        if recovery.get('pending_refs') or recovery.get('review_required_refs'):
            result.append({**recovery, 'task_id': task['id'], 'node_id': node['id'], 'execution_id': eid,
                'executor_ref': binding['executor_ref'],
                'dispatch_id': binding.get('dispatch_id') or binding.get('id')})
    return result


def dispatch_view(controller, owner, task_id, *, compact=False):
    snap = controller.snapshot(owner, task_id)
    task = snap['tasks'][0]
    node_ids = {n['id'] for n in snap['nodes']}
    leaves = [n for n in snap['nodes'] if not n.get('child_ids') and n.get('record_successor_node_id') not in node_ids]
    continuation_modules = []
    history = None
    if (task.get('session_workflow') and len(task['node_ids']) == 1 and
            len(leaves) == 1 and leaves[0]['key'] == 'session' and leaves[0]['state'] == 'queued'):
        from .module_continuation import candidates
        history = controller.snapshot(owner)
        continuation_modules = candidates({key: {item['id']: item for item in history[key]}
                                           for key in ('tasks', 'nodes')}, task)
    from .native_handoff import pending_handoffs, handoff_observation
    # Cross-task handoffs refer to targets outside this one task's snapshot.
    # Read their current facts once; do not schedule or claim while observing.
    cross_task = any(
        notice.get('task_id') != task_id for node in leaves
        for event in node.get('native_handoffs', {}).values()
        for notice in event.get('continuations', []) or ([event['continuation']] if event.get('continuation') else []))
    observation_snap = (history if history is not None else controller.snapshot(owner)) if cross_task else snap
    observation = handoff_observation(observation_snap['nodes'], observation_snap['tasks'],
        observation_snap['leases'], controller.clock(),
        events=[event for node in leaves for event in node.get('native_handoffs', {}).values()])
    from .testing_roles import worker_packet
    native = task.get('execution_route') == 'native_browser'
    project = controller.store.get_project(owner, task['project_id']) if native and not compact else None
    from .ui_design_references import catalog
    design_references = catalog(controller, owner, project) if project is not None else []
    result = {
        'pending_handoffs': pending_handoffs(leaves),
        'task_id': task_id,
        'task_revision': task['revision'],
        'intent': task['intent'],
        'modules': [{k: n.get(k) for k in ('id', 'key', 'title', 'scope', 'state',
                    'reason', 'revision', 'execution_disposition', 'depends_on', 'locks', 'record_project_id', 'record_execution_id', 'plan_key', 'continuation_source')}
                    | {'node_id': n['id'], 'browser_assignment': browser_assignment(task, n)}
                    | record_assignment(n) | node_dispatch(n)
                    | ({'worker_packet': worker_packet(task, n, project, design_references)} if project is not None and n.get('execution_disposition') != 'multi_account_excluded' else {}) for n in leaves],
        'continuation_modules': continuation_modules,
        'record_continuation': bool(task.get('record_continuation')),
        'native_browser_policy': task.get('native_browser_policy'),
        'dispatch_guidance': NATIVE_GUIDANCE if task.get('execution_route') == 'native_browser' else GUIDANCE if task.get('execution_route') == 'local_browser' else
            '原后台执行器领取这些模块；当前聊天查询进度与报告，不创建第二组执行者。',
        'dispatch_mode': ('delegate_leaf_nodes' if len(leaves) > 1 else 'single_leaf')
            if task.get('execution_route') in {'local_browser', 'native_browser'} else 'managed_executor',
        'executor_topology': 'independent_codex_threads' if task.get('execution_route') in {'local_browser', 'native_browser'}
            and len(leaves) > 1 else 'single_executor',
        'module_count': len(leaves),
        'coordination_plan': coordination_plan(leaves, observation=observation if native else None),
        'role': 'coordinator',
        'coordinator_wait': {'action': 'coordinator_wait_script',
            'arguments': {'task_ids': [task_id]},
            'instruction': '派发后在原协调回合生成并执行此工具内事件等待，沿原 holder_id/coordinator_ref；'
                '跨任务组传本轮全部 task_ids。普通无变化不启动工作模型；退出后无后台监听。'},
    }
    if not native:
        result.pop('coordinator_wait', None)
    if compact:
        result = {key: result[key] for key in ('task_id', 'task_revision', 'intent', 'coordination_plan', 'pending_handoffs')}
        result['modules'] = [{key: n.get(key) for key in ('id', 'task_id', 'state', 'revision', 'reason', 'control_intent')}
            | {'binding': n.get('executor_dispatch') or n.get('dispatch_offer') or {},
               'has_lease': any(lease['node_id'] == n['id'] for lease in snap['leases']),
               'dispatch_state': node_dispatch(n)['dispatch_state']} for n in leaves]
    if native:
        from .native_coordination import view
        result['closeout'] = view(controller, owner, task_id)
        result['coordination_plan']['case_recovery'] = case_recovery(controller, owner, task, leaves)
    if project is not None:
        by_id = {n['id']: n for n in leaves}
        pending = [module for module in result['modules'] if
            (module.get('worker_packet', {}).get('assignment') or {}).get('dispatch_id') and
            (by_id[module['node_id']].get('executor_dispatch') or {}).get('receipt_source')
                == 'explicit_control_resume']
        if pending:
            from .orchestration_storage import Metadata, History, KINDS
            with controller.connect() as db:
                db.execute('BEGIN')
                state = Metadata(db)
                state.update({kind: History(db, kind) for kind in KINDS})
                current_task = controller.owned(state['tasks'], owner, task_id)
                for module in pending:
                    node = controller.owned(state['nodes'], owner, module['node_id'])
                    assignment = module['worker_packet']['assignment']
                    if (current_task['revision'] != task['revision'] or node['revision'] != module['revision']
                            or (node.get('executor_dispatch') or {}).get('receipt_source') != 'explicit_control_resume'
                            or (node.get('executor_dispatch') or {}).get('dispatch_id') != assignment['dispatch_id']):
                        module.pop('worker_packet')
                        module['next_action'] = 'refresh_module_dispatch'
                    else:
                        module.update(resume_packet(controller, state, current_task, node, project, design_references))
    return result


def resume_packet(controller, state, task, node, project, design_references=None):
    """Project the original stage without claiming, reserving or replaying work."""
    from .testing_roles import worker_packet
    packet = worker_packet(task, node, project, design_references)
    result = {'worker_packet': packet, 'next_action': 'review_original_prerequisites'}
    if (task['intent'] != 'run' or node.get('control_intent') != 'run' or node['state'] != 'queued'
            or any(lease['node_id'] == node['id'] for lease in state['leases'].values())):
        return result
    result['next_action'] = 'prepare_formal_continuation'
    if node.get('checkpoint', {}).get('work_plan'):
        from . import ui_records
        from .native_work_plan import TOKEN_FIELDS
        from .resource_scheduler import ResourceScheduler
        result['next_action'] = 'review_original_prerequisites'
        pid, eid = node.get('record_project_id'), node.get('record_execution_id')
        if not pid or not eid:
            return result
        try:
            original = controller.store.get_project(node['owner'], pid)
            if original.get('ui_execution_id') != eid:
                return result
            record = {**ui_records.load(controller.store, node['owner'], pid, eid), 'project_id': pid}
            selected = ResourceScheduler(controller, state, controller.clock()).select_work_candidate(node, record, for_wake=True)
        except (FileNotFoundError, ValueError, OSError):
            return result  # Unreadable original facts never authorize a stage.
        if selected:
            packet['assignment']['claim_arguments'] = {'work_token': {key: selected[key] for key in TOKEN_FIELDS}}
            result['next_action'] = 'prepare_formal_continuation'
    return result


def resume_cancelled_dispatch(state, node, now):
    """Renew an exited original worker's cancelled offer in the resume transaction."""
    import copy
    from .orchestration import uid
    task = state['tasks'][node['task_id']]
    offer = node.get('dispatch_offer') or {}
    previous = node.get('executor_dispatch') or offer
    if (task.get('execution_route') != 'native_browser' or task['intent'] != 'run'
            or node.get('control_intent') != 'run' or node['state'] != 'queued'
            or offer.get('state') != 'cancelled' or not previous.get('holder_id')
            or previous.get('exit_acknowledged_at') is None
            or any(lease['node_id'] == node['id'] for lease in state['leases'].values())):
        return False
    # A new generation fences the old report writer too. Keep its authority
    # until the existing closeout has completed, as for explicit source resume.
    if node.get('native_report_pending') or node.get('finalization_pending'):
        raise Conflict('原报告仍在收尾；先沿原已交还绑定完成报告，再继续该模块')
    node.setdefault('dispatch_offer_history', []).append(copy.deepcopy(offer))
    if node.get('executor_dispatch'):
        node.setdefault('executor_dispatch_history', []).append(copy.deepcopy(node['executor_dispatch']))
    binding = {key: previous[key] for key in ('holder_id', 'executor_ref', 'coordinator_ref') if key in previous}
    binding.update(dispatch_id=uid(), received_at=now, last_seen_at=now,
        receipt_source='explicit_control_resume',
        resumed_from_dispatch_id=previous.get('dispatch_id') or offer['id'],
        resumed_from_lease_id=(node.get('attempts') or [{}])[-1].get('lease_id', ''))
    node['executor_dispatch'] = binding
    node['dispatch_offer'] = {key: binding[key] for key in ('holder_id', 'executor_ref', 'coordinator_ref') if key in binding}
    node['dispatch_offer'].update(id=binding['dispatch_id'], state='offered', created_at=now,
                                  executor_kind='codex_thread', reason='用户继续原模块')
    status = node.pop('native_executor_status', None)
    if status:
        node.setdefault('native_executor_status_history', []).append(status)
    return True


def receive(state, node, holder_id, now, *, executor_ref='', coordinator_ref='', dispatch_id=''):
    """Record the real caller on its existing claim; no extra round trip or gate.

    A holder is a protocol identity, not proof of a desktop thread/subagent. Only
    identifiers actually supplied by that caller are exposed as executor refs.
    """
    import copy
    from .native_identity import same_executor_ref
    current = node.get('executor_dispatch') or {}
    bound_ref = current.get('executor_ref') or (node.get('dispatch_offer') or {}).get('executor_ref')
    if (bound_ref and executor_ref and not same_executor_ref(bound_ref, executor_ref)
            and not current.get('exit_acknowledged_at')):
        raise Conflict('该模块已绑定另一 Codex 会话；可以查看进度，不能用相同 holder_id 替换执行者')
    assert_independent_executor(state, node, holder_id, executor_ref)
    offer = node.get('dispatch_offer')
    if offer:
        from .direct_execution import START_TIMEOUT
        if (state.get('tasks', {}).get(node.get('task_id'), {}).get('execution_route') != 'native_browser'
                and offer['state'] == 'offered' and now - offer['created_at'] > START_TIMEOUT):
            raise Conflict('派发接单已超时，先由协调者核对原派发')
        if offer['state'] not in {'offered', 'received'} or offer.get('holder_id') != holder_id or offer['id'] != dispatch_id:
            raise Conflict('派发已撤销或不属于当前执行者；沿原协调者核对，不重复领取')
        offer.update(state='received', received_at=offer.get('received_at', now))
    previous = node.get('executor_dispatch') or {}
    if state.get('tasks', {}).get(node.get('task_id'), {}).get('execution_route') == 'native_browser':
        from .native_handoff import thread_id
        # Keep the first actual return route, including a repaired legacy offer.
        # A worker's later claim must neither redirect it nor downgrade it.
        offered_ref = (offer or {}).get('coordinator_ref', '')
        received_ref = previous.get('coordinator_ref', '') if previous.get('holder_id') == holder_id else ''
        if thread_id(offered_ref):
            coordinator_ref = offered_ref
        elif thread_id(received_ref):
            coordinator_ref = received_ref
        elif not coordinator_ref:
            coordinator_ref = offered_ref
    if previous and (previous.get('holder_id') != holder_id or previous.get('exit_acknowledged_at')):
        node.setdefault('executor_dispatch_history', []).append(copy.deepcopy(previous))
        previous = {}
    receipt = {**previous, 'holder_id': holder_id,
               'dispatch_id': dispatch_id or previous.get('dispatch_id') or
                              digest({'node_id': node['id'], 'holder_id': holder_id}),
               'received_at': previous.get('received_at', now), 'last_seen_at': now,
               'receipt_source': 'executor_claim'}
    for key, value in (('executor_ref', executor_ref), ('coordinator_ref', coordinator_ref)):
        if value:
            if not isinstance(value, str) or len(value) > 500:
                raise ValueError(key + ' 必须是最多 500 字的实际执行者标识')
            receipt[key] = value
    node['executor_dispatch'] = receipt
    return copy.deepcopy(receipt)


def retire_obsolete_resumes(node, now):
    """Retire only resume requests issued after that executor already exited.

    Keep the original exit evidence and distinguish obsolescence from an ACK.
    Stop/pause/timeout requests without an executor ACK remain pending.
    """
    exited = {r['holder_id']: r['exit_acknowledged_at']
              for r in [*node.get('executor_dispatch_history', []), node.get('executor_dispatch') or {}]
              if r.get('holder_id') and r.get('exit_acknowledged_at') is not None}
    for control in node.get('executor_controls', {}).values():
        exit_time = exited.get(control.get('holder_id'))
        if (control.get('action') == 'resume' and control.get('state') in {'pending', 'received'}
                and exit_time is not None and exit_time <= control['created_at']):
            control.update(state='obsolete', resolved_at=now,
                           reason='恢复指令生成前原执行者已确认退出；由后续派发接续，不等待旧执行者')


def command(state, node, action, now):
    """Keep control intent for every known consumer, including unleased ones."""
    retire_obsolete_resumes(node, now)
    offer = node.get('dispatch_offer')
    if offer and action in {'stop', 'pause', 'timeout'}:
        offer.update(state='cancelled', cancelled_at=now)
    receipt = node.get('executor_dispatch') or offer
    if not receipt or not receipt.get('holder_id') or receipt.get('exit_acknowledged_at') is not None:
        return None
    key = '%s:%s:%s:%s' % (node['id'], node['revision'], action,
                          receipt.get('dispatch_id') or receipt.get('id') or receipt['holder_id'])
    commands = node.setdefault('executor_controls', {})
    value = commands.setdefault(key, {'id': key, 'action': action,
        'holder_id': receipt['holder_id'], 'executor_ref': receipt.get('executor_ref', ''),
        'created_at': now, 'state': 'pending'})
    return dict(value)


def observe_control(node, holder_id, now, *, exited=False):
    """Attach an ACK to an existing executor call, never to a browser-host ACK."""
    receipt = node.get('executor_dispatch')
    if not receipt and exited:
        # An offered worker can finish without ever claiming a resource. Its
        # exit is real, but must not manufacture an executor-claim receipt.
        receipt = node.get('dispatch_offer')
    if receipt and receipt.get('holder_id') == holder_id:
        receipt['last_seen_at'] = now
        if exited:
            receipt['exit_acknowledged_at'] = now
    for value in node.get('executor_controls', {}).values():
        if value['holder_id'] == holder_id and value.get('state') not in {'obsolete', 'exited'}:
            value.setdefault('received_at', now)
            value['state'] = 'exited' if exited else 'received'
            if exited:
                value['exited_at'] = now


def node_dispatch(node):
    """Distinguish dispatch backlog, account waiting, browser and business work."""
    import copy
    from .native_handoff import latest
    receipt = copy.deepcopy(node.get('executor_dispatch') or {})
    offer = node.get('dispatch_offer') or {}
    attempts=node.get('attempts',[])
    last_lease=attempts[-1].get('lease_id') if attempts else None
    local_ack=bool(last_lease and last_lease in node.get('settlement_acks',{}))
    ack_required=bool(last_lease and not node.get('native_browser')
                      and last_lease not in node.get('undelivered_leases',[]))
    controls = [copy.deepcopy(c) for c in node.get('executor_controls', {}).values()
                if c.get('state') not in {'exited', 'obsolete'}]
    if node.get('state') in {'completed', 'blocked', 'stopped'}:
        phase = 'ended'
    elif node.get('native_browser') and node.get('state') == 'stopping':
        phase = 'waiting_desktop_stop'
    elif node.get('execution_ended'):
        phase = 'ended_resource_hold'
    elif (node.get('native_executor_status') or {}).get('state') == 'unavailable':
        phase = 'model_unavailable'
    elif node.get('state') == 'queued' and offer.get('state') in {'waiting_capacity','offered','expired'}:
        phase = {'waiting_capacity':'waiting_executor_capacity','offered':'awaiting_executor_ack',
                 'expired':'dispatch_expired'}[node['dispatch_offer']['state']]
    elif node.get('state') == 'queued' and node.get('resource_wait'):
        phase = 'waiting_resource'
    elif node.get('business_started_at'):
        phase = 'business_started'
    elif node.get('browser_ready_at'):
        phase = 'browser_ready'
    elif receipt or node.get('direct_holder'):
        phase = ('waiting_resource' if node.get('state') == 'queued' else
                 'account_assigned' if node.get('native_browser') else 'starting_browser')
    elif offer.get('state') == 'waiting_capacity':
        phase = 'waiting_executor_capacity'
    elif offer.get('state') == 'offered':
        phase = 'awaiting_executor_ack'
    elif offer.get('state') == 'expired':
        phase = 'dispatch_expired'
    else:
        phase = 'awaiting_executor'
    return {'dispatch_state': phase, 'executor': receipt or None,
            'pending_controls': controls, 'dispatch_offer': copy.deepcopy(node.get('dispatch_offer')),
            'executor_exit_confirmed': bool((receipt or offer).get('exit_acknowledged_at')),
            'settlement_acknowledged': local_ack,
            'settlement_ack_required': ack_required,
            'exploration_gap': copy.deepcopy(node.get('exploration_gap')),
            'native_handoff': latest(node),
            'native_executor_status': copy.deepcopy(node.get('native_executor_status')),
            'stop_complete': (not controls and node['state'] in {'stopped','completed','blocked'} and
                              (not ack_required or local_ack)) if node.get('control_intent') == 'stop' else None}


def assert_independent_executor(state, node, holder_id, executor_ref=''):
    """One active module per declared executor; never infer a thread was created."""
    from .native_identity import same_executor_ref
    for other in state['nodes'].values():
        if other['id'] == node['id'] or other['task_id'] != node['task_id'] or other.get('child_ids'):
            continue
        if other['state'] in {'completed', 'blocked', 'stopped'}:
            continue
        receipt = other.get('executor_dispatch') or {}
        offer = other.get('dispatch_offer') or {}
        active = [r for r in (receipt, offer) if r and not r.get('exit_acknowledged_at')
                  and r.get('state') not in {'cancelled', 'expired', 'waiting_capacity'}]
        if other.get('direct_holder') == holder_id or any(
                r.get('holder_id') == holder_id or same_executor_ref(r.get('executor_ref'), executor_ref)
                for r in active):
            raise Conflict('每个模块须使用独立 Codex 会话；此执行者已绑定其他模块，请沿用各模块自己的会话及 holder_id，不合并分工。')


def offer_modules(controller, owner, args):
    """Persist coordinator intent before spawning; receipt comes only from claim."""
    import copy
    from .orchestration import text
    arguments = args.get('arguments') or {}
    lifecycle = {'coordinator_closeout', 'desktop_observations'} & set(arguments)
    if lifecycle:
        if len(lifecycle) != 1 or set(arguments) != lifecycle:
            raise ValueError('协调生命周期回执不能同时派发或修改其他状态')
        from .native_coordination import call
        return call(controller, owner, args)
    if arguments.get('observe') is True:
        if set(arguments) != {'observe'}:
            raise ValueError('只读协调对账不能同时派发、消费或登记状态')
        view = dispatch_view(controller, owner, args.get('task_id'), compact=True)
        from .native_handoff import thread_id
        reference = thread_id(args.get('coordinator_ref') or args.get('holder_id'))
        if not reference or any(thread_id(module['binding'].get('coordinator_ref')) not in {'', reference}
                                for module in view['modules']):
            raise PermissionError('只读协调对账需沿用原协调会话')
        return view
    handoff_ack = arguments.get('handoff_ack')
    values = arguments.get('modules', [])
    group = arguments.get('continuation_group')
    executor_status = arguments.get('executor_status')
    if not isinstance(values, list) or (not values and handoff_ack is None and group is None and executor_status is None):
        raise ValueError('arguments.modules 必须包含实际模块派发或等待安排')
    coordinator = text(args.get('holder_id'), 'coordinator holder_id', 160)
    if arguments.get('handoff_delivery') is not None:
        if values:
            raise ValueError('发送回执不能同时重派模块')
        from .native_handoff import acknowledge
        # Delivery begins are deliberately non-cacheable: after an uncertain
        # response, returning an old send_authorized would duplicate the message.
        with controller.transaction(work_records=True) as (_, state):
            task = controller.owned(state['tasks'], owner, args.get('task_id'))
            if task.get('execution_route') != 'native_browser':
                raise ValueError('仅原生路线消费桌面交接事件')
            return {'task_id': task['id'], 'modules': [],
                    **acknowledge(controller, state, owner, task, args)}
    reconciled = False
    def change(db, state):
        nonlocal reconciled
        task = controller.owned(state['tasks'], owner, args.get('task_id'))
        reference = (args.get('coordinator_ref') or coordinator
                     if task.get('execution_route') == 'native_browser' else coordinator)
        if not isinstance(reference, str) or len(reference) > 500:
            raise ValueError('coordinator_ref 必须是最多 500 字的实际执行者标识')
        handoff_result = {}
        if executor_status is not None:
            if values or handoff_ack is not None or group is not None:
                raise ValueError('执行者状态回执不能同时重派、交接或修改接续组')
            from .native_executor_status import report
            return {'task_id': task['id'], 'modules': [], 'accepted': True,
                    **report(controller, db, state, owner, task, args, executor_status)}
        if handoff_ack is not None:
            if task.get('execution_route') != 'native_browser':
                raise ValueError('仅原生路线消费桌面交接事件')
            from .native_handoff import acknowledge
            handoff_result = acknowledge(controller, state, owner, task, args)
            reconciled = True
            if not handoff_result['accepted'] or not values:
                return {'task_id': task['id'], 'modules': [], **handoff_result}
        if task.get('execution_route') not in {'local_browser', 'native_browser'} or task['intent'] != 'run':
            raise Conflict('只能安排仍在运行的当前聊天任务')
        result = []
        seen = set()
        for item in values:
            if not isinstance(item, dict):raise ValueError('模块派发项必须是对象')
            node = controller.owned(state['nodes'], owner, item.get('node_id'))
            if node['id'] in seen:raise ValueError('同一请求不能重复派发同一节点')
            seen.add(node['id'])
            controller.sessions.assert_available(state, task, [node['id']])
            if node['task_id'] != task['id'] or node.get('child_ids') or node.get('control_intent', 'run') != 'run':
                raise Conflict('派发节点不属于当前可执行叶子')
            from .testing_policy import node_excluded, excluded_response
            if node_excluded(node, state):
                result.append(excluded_response(node_id=node['id']))
                continue
            if node.get('direct_holder') or node['state'] != 'queued':
                raise Conflict('节点已接单或结束，不能创建竞争执行者')
            retire_obsolete_resumes(node, controller.clock())
            previous = node.get('dispatch_offer')
            if previous and previous['state'] == 'offered':
                raise Conflict('原派发尚待接单，查询原派发，不重复启动执行者')
            if previous:
                node.setdefault('dispatch_offer_history', []).append(copy.deepcopy(previous))
            receipt=node.pop('executor_dispatch',None)
            if receipt:node.setdefault('executor_dispatch_history',[]).append(receipt)
            waiting = item.get('state') == 'waiting_capacity'
            offer = {'id': text(item.get('dispatch_id'), 'dispatch_id', 160),
                     'coordinator_ref': reference, 'created_at': controller.clock(),
                     'state': 'waiting_capacity' if waiting else 'offered',
                     'reason': text(item.get('reason'), '真实执行者容量等待原因', 2000) if waiting else ''}
            if not waiting:
                offer['holder_id'] = text(item.get('holder_id'), 'worker holder_id', 160)
                prior = [*node.get('dispatch_offer_history',[]), *node.get('executor_dispatch_history',[])]
                if any(p.get('holder_id') == offer['holder_id'] for p in prior):
                    raise Conflict('重投须使用新的执行者 holder_id，避免旧执行者继承新权限')
                ref = item.get('executor_ref', '')
                if not isinstance(ref,str) or len(ref)>500:raise ValueError('executor_ref 必须是最多500字的实际执行者标识')
                assert_independent_executor(state, node, offer['holder_id'], ref)
                offer['executor_ref'] = ref
                offer['executor_kind'] = 'codex_thread'
            node['dispatch_offer'] = offer
            result.append({'node_id': node['id'], **copy.deepcopy(offer),
                           'browser_assignment': browser_assignment(task, node), **record_assignment(node)})
        controller.audit(db, owner, 'modules.dispatched', task['id'])
        group_result = {}
        if group is not None:
            from .native_handoff import register_group
            group_result = register_group(controller, state, owner, task, reference, group)
        return {'task_id': task['id'], 'modules': result, 'accepted': True, **handoff_result, **group_result}
    result = controller.request(owner, args.get('request_id'), args, change, work_records=handoff_ack is not None)
    if values and result.get('accepted'):
        view = dispatch_view(controller, owner, args['task_id'])
        packets = {module['node_id']: module['worker_packet'] for module in view['modules'] if 'worker_packet' in module}
        result['modules'] = [{**module, **({'worker_packet': packets[module['node_id']]} if module['node_id'] in packets else {})}
                             for module in result['modules']]
        result['role'] = 'coordinator'
        if view.get('coordinator_wait'):
            result['coordinator_wait'] = view['coordinator_wait']
        result['dispatch_guidance'] = view['dispatch_guidance']
    if executor_status is not None:
        controller.schedule()
        result['pending_handoffs'] = dispatch_view(controller, owner, args['task_id'])['pending_handoffs']
    if handoff_ack is not None:
        from .native_handoff import acknowledge
        # request() may return a cached receipt from before stop/deletion. Keep
        # original module offers idempotent, but never return stale wake advice.
        if not reconciled:
            with controller.transaction(work_records=True) as (_, state):
                task = controller.owned(state['tasks'], owner, args.get('task_id'))
                current = acknowledge(controller, state, owner, task, args)
                result = {**result, **current}
                if not current['accepted']:
                    result['modules'] = []
        if result.get('accepted'):
            controller.schedule()
    return result


def expire_dispatches(state, now):
    from .direct_execution import START_TIMEOUT, PROGRESS_TIMEOUT
    leased = {l['node_id'] for l in state['leases'].values()}
    for node in state['nodes'].values():
        retire_obsolete_resumes(node, now)
        if state.get('tasks', {}).get(node.get('task_id'), {}).get('execution_route') == 'native_browser':
            # Sleeping desktop chats are not Runner processes. Their queued
            # ownership survives without model heartbeat or polling turns.
            continue
        offer = node.get('dispatch_offer')
        if offer and offer['state'] == 'offered' and now - offer['created_at'] > START_TIMEOUT:
            command(state, node, 'timeout', now)
            offer.update(state='expired', expired_at=now)
            node['reason'] = '模块派发接单超时；原派发已失效，协调者核对后重投同一节点'
        if node['id'] not in leased and node.get('direct_holder') and node['state'] == 'queued' and now - node.get('actor_seen', 0) > PROGRESS_TIMEOUT:
            command(state, node, 'timeout', now)
            if offer: offer.update(state='expired', expired_at=now)
            node.pop('direct_holder', None)
            node['reason'] = '排队执行者失联；没有账号占用，原执行者需停止，协调者重投同一节点'
