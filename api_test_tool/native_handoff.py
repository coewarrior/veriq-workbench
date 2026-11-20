"""Durable lifecycle handoff; the existing desktop message tool sends it.

The server records delivery reports and consumption, never pretends to wake a
desktop chat. No browser transport, account reservation or polling is added.
"""
from __future__ import annotations

import copy
import json
from .resource_projection import copy_node
from .native_identity import thread_id

from .orchestration import Conflict, digest

DELIVERY_PENDING = {'pending', 'sending', 'unknown', 'blocked', 'unbound'}


def execution_contract(node):
    reference = coordinator_ref(node)
    return {
        'capability': 'native_handoff_exec_v1',
        'direct_capability': 'native_direct_handoff_exec_v1',
        'coordinator_binding': 'bound' if thread_id(reference) else 'unbound' if reference or node.get('dispatch_offer') else 'single_chat',
        'client_update_url': '/static/api-test-client.py',
        'finish_executor': 'functions.exec',
        'role': 'worker' if node.get('dispatch_offer') else 'single',
        'instruction': (
            '本模块真实退出后，在同次functions.exec执行当前已核验CLI native-closeout-script或原native-handoff-script；'
            'MCP用handoff_script生成原finish参数编排。解析script后显式注入tools/text/ALL_TOOLS执行，不输出全文重写。'
            '生成器机械完成交还、发送占用、真实桌面通知及回执，再整理报告；执行者不负责其他模块调度。'
            '已发送不等于后继实际领取。needs_handoff/handoff_failures保留原事件、目标和失败阶段；未知不重发。'
            '缺真实工具不能发送，沿原协调会话处理；单独finish、本地文件和生成脚本不是送达。'
            '保持原模型、范围、账号集合和检查点，旧在途和单模块入口继续兼容。'),
    }


def coordinator_ref(node):
    return ((node.get('executor_dispatch') or {}).get('coordinator_ref')
            or (node.get('dispatch_offer') or {}).get('coordinator_ref') or '')


def register_group(controller, state, owner, task, reference, value):
    """Persist the coordinator's explicit authorized set, never infer all tasks."""
    if not isinstance(value, dict) or not isinstance(value.get('task_ids'), list):
        raise ValueError('continuation_group 需包含本轮全部 task_ids')
    ids = value['task_ids']
    if not ids or len(ids) != len(set(ids)) or task['id'] not in ids or not thread_id(reference):
        raise ValueError('接续组需包含当前任务、无重复的任务标识和真实协调会话')
    members = {}
    pending = []
    project = task.get('account_project_id') or task['project_id']
    for tid in ids:
        member = controller.owned(state['tasks'], owner, tid)
        if (member.get('execution_route') != 'native_browser' or member['intent'] != 'run'
                or (member.get('account_project_id') or member['project_id']) != project):
            raise Conflict('接续组仅包含本轮同账号项目且仍获授权的原生任务')
        leaves = [state['nodes'][nid] for nid in member['node_ids'] if not state['nodes'][nid].get('child_ids')]
        if any(thread_id(binding.get('coordinator_ref')) not in {'', thread_id(reference)}
               for node in leaves
               for binding in (node.get('executor_dispatch') or {}, node.get('dispatch_offer') or {})):
            raise PermissionError('接续组任务已绑定另一真实协调会话，不能覆盖')
        for node in leaves:
            for binding in (node.get('executor_dispatch'), node.get('dispatch_offer')):
                if binding and not thread_id(binding.get('coordinator_ref')):
                    binding['coordinator_ref'] = reference
            if not thread_id(coordinator_ref(node)):
                raise Conflict('先登记全部原模块及执行会话，再绑定本轮接续组')
            for event in node.get('native_handoffs', {}).values():
                if event['delivery_state'] == 'unbound' and not thread_id(event.get('coordinator_ref')):
                    event.update(coordinator_ref=reference, delivery_state='pending')
                refresh(state, node, event, controller.clock(), controller)
                if event['delivery_state'] in {'pending', 'sent', 'unbound'}:
                    pending.append({'task_id': event['task_id'], 'node_id': event['node_id'],
                                    'event_id': event['id']})
        members[tid] = member['revision']
    key = digest({'owner': owner, 'coordinator': thread_id(reference), 'task_ids': sorted(ids)})
    state.setdefault('native_continuation_groups', {})[key] = {
        'id': key, 'owner': owner, 'coordinator_ref': reference, 'members': members,
        'account_project_id': project, 'created_at': controller.clock()}
    for tid in ids:
        state['tasks'][tid]['native_continuation_group'] = key
    return {'continuation_group_id': key, 'pending_handoffs': pending}


def same_scope(state, source, target, reference):
    if target['id'] == source['id']:
        return True
    key = source.get('native_continuation_group')
    group = state.get('native_continuation_groups', {}).get(key, {})
    return bool(key and target.get('native_continuation_group') == key
                and group.get('owner') == source['owner'] == target['owner']
                and thread_id(group.get('coordinator_ref')) == thread_id(reference)
                and group.get('account_project_id') == (source.get('account_project_id') or source['project_id'])
                    == (target.get('account_project_id') or target['project_id'])
                and group.get('members', {}).get(source['id']) == source['revision']
                and group.get('members', {}).get(target['id']) == target['revision'])


def matches_target(state, event):
    from .native_work_plan import token_matches
    target = state['nodes'].get(event['node_id'], {})
    task = state['tasks'].get(target.get('task_id'), {})
    receipt = target.get('executor_dispatch') or target.get('dispatch_offer') or {}
    bound = event['claim_arguments']
    return bool(target and task.get('revision') == event['task_revision']
                and target.get('revision') == event['node_revision']
                and receipt.get('holder_id') == bound['holder_id']
                and (receipt.get('dispatch_id') or receipt.get('id')) == bound['dispatch_id']
                and thread_id(receipt.get('executor_ref')) == thread_id(bound['executor_ref'])
                and token_matches(target, (bound.get('arguments') or {}).get('work_token'))
                and task.get('intent') == 'run' and target.get('control_intent', 'run') == 'run'
                and not task.get('account_project_deleted') and not target.get('session_removed'))


def obsolete(event):
    if event['delivery_state'] != 'obsolete':
        event['delivery_state_before_obsolete'] = event['delivery_state']
        event['delivery_state'] = 'obsolete'


def notices(event):
    return event.get('continuations', []) or ([event['continuation']] if event.get('continuation') else [])


def refresh(state, node, event, now, controller=None):
    """Keep invalidation durable without turning stale delivery into a resume."""
    if event.get('delivery_state') == 'obsolete':
        return event
    task = state['tasks'].get(event['task_id'], {})
    invalid = (
        not task or task.get('owner') != node.get('owner')
        or task.get('execution_route') != 'native_browser'
        or task.get('revision') != event['task_revision']
        or task.get('intent') != 'run'
        or node.get('control_intent', 'run') != 'run'
        or task.get('account_project_deleted') or node.get('session_removed')
    )
    if not invalid and controller is not None:
        try:
            controller.sessions.assert_available(state, task, [node['id']])
        except (Conflict, ValueError):
            # Missing/deleted or malformed stored session references cannot be
            # wake targets; leave other storage/runtime failures visible.
            invalid = True
    if invalid:
        event.update(delivery_state='obsolete', obsolete_at=now)
    return event


def released(state, node, lease_id, now, account_ids=()):
    reference = coordinator_ref(node)
    # An ordinary single-chat run has no coordinator handoff to deliver.
    if not reference and not node.get('dispatch_offer'):
        return None
    event = node.setdefault('native_handoffs', {}).setdefault(lease_id, {
        'id': lease_id, 'task_id': node['task_id'], 'node_id': node['id'],
        'coordinator_ref': reference, 'created_at': now,
        'task_revision': state['tasks'][node['task_id']]['revision'],
        'resource_change': {'kind': 'account_released', 'at': now, 'account_ids': list(account_ids)},
        'delivery_state': 'pending' if thread_id(reference) else 'unbound',
    })
    refresh(state, node, event, now)
    return response(event)


def response(event):
    result = copy.deepcopy(event)
    required = not event.get('direct_dispatch') or event.get('coordinator_notification_required', False)
    result['delivery_required'] = required and event['delivery_state'] in DELIVERY_PENDING
    result['automatic_delivery'] = False
    result['required_client_capability'] = 'native_handoff_exec_v1'
    if event.get('direct_dispatch'):
        result['required_direct_capability'] = 'native_direct_handoff_exec_v1'
    result['client_update_url'] = '/static/api-test-client.py'
    if required and event['delivery_state'] == 'pending' and thread_id(event['coordinator_ref']):
        prompt = (
            '原生测试模块已确认退出并交还账号。'
            f'原 task_id={event["task_id"]}，node_id={event["node_id"]}，'
            f'event_id={event["id"]}。'
            '收到后先核对本轮 task_id/node_id/event_id 与原派发绑定，下一次工作调用立即确认消费；不要先读取完整报告、统计耗时或整理总结。'
            '请通过当前客户端 native-handoff-script 生成并执行一次 functions.exec 编排，'
            '以原协调会话调用 direct_test_session(action="dispatch",'
            'holder_id=原协调者标识,coordinator_ref=当前真实会话标识,'
            f'task_id="{event["task_id"]}",request_id=稳定消费请求ID,'
            'arguments={handoff_ack:{'
            f'task_id:"{event["task_id"]}",node_id:"{event["node_id"]}",'
            f'event_id:"{event["id"]}"'
            '}}) 消费此交接，并由同一编排发送返回的 continuation、提交真实发送回执。'
            '无 continuation 就没有可唤醒的后继；不恢复停止任务，不重建节点，不唤醒全部等待者。'
            '消费回执的coordination_plan区分原控制、接续、协调者本地问题与继续运行者；不要向正常会话广播本模块阻塞或重复核实提醒。'
            '通知消费不等于账号领取成功。'
        )
        if event.get('kind') == 'resume_original_worker':
            prompt = (
                '原测试轮次出现账号可用事件，请接续本会话原节点。'
                '先由统一恢复入口机械接入本通知，禁止只给旧 prepare 加 resume 而丢失阶段。'
                '已有 native-cycle.js 时执行 input={action:"resume",notification:'
                + json.dumps(event['claim_arguments'], ensure_ascii=False) + '}；'
                'CLI 使用当前客户端 native-resume --assignment-file 原文件 --directory 原目录 --notification-json 本通知JSON。'
                '入口核对原任务/派发/执行者、完整 work_token 和账号集合；返回 excluded=true 时标记不测且不等资源；其他 stage_ready=false 才结束回合等真实事件。'
                'stage_ready=true 已完成阶段核对，不再单独 stage_ready/context，随后准备环境和原 prepare --resume。'
                + ('原浏览器已确认退出，本通知只表示账号可供申请，不表示浏览器已经就绪。'
                   '先复用当前执行包 environment_setup 在原任务目录准备真实独立环境，'
                   '成功后再执行下面原 prepare --resume；不改写旧环境版本冒充可用、不重建基线。'
                   if event.get('environment_preparation_required') else '')
                + ('环境准备成功后，' if event.get('environment_preparation_required') else '')
                + '若已有 native-run-kit，直接复用原 native-cycle.js，input={action:"prepare",resume:true}；'
                '若本轮已使用 native-prepare，直接复用原 prepare 命令并加 --resume；'
                '它内部按下列原绑定领取并复用准备，不再单独拆 claim/context/基线，也不重做已保存用例。'
                '原领取参数已由入口写入 assignment，不手抄或删减；原始通知参数为：'
                + json.dumps(event['claim_arguments'], ensure_ascii=False)
                + '。仅以本次真实领取结果判断可执行；若无账号，结束当前轮次，不轮询。'
                '沿用原用例、现场检查点和范围，保留已完成结果，不重放未知业务操作。'
                '若任务已停止、删除或范围改变，旧通知不构成恢复授权。'
            )
        elif event.get('kind') == 'resource_change':
            prompt = ('原任务资源条件已变化，平台已保存待接续事件，尚未唤醒执行者。'
                      f'原task_id={event["task_id"]}，node_id={event["node_id"]}，event_id={event["id"]}。'
                      '由原协调会话沿 native-handoff-script 和原 dispatch.handoff_ack 消费此事件；'
                      '同次真实工具发送和ACK才是送达，收到通知后仍须原执行者实际领取。'
                      '不重发 sending/unknown，不恢复停止范围，不重放已完成或未知动作。')
        elif event.get('direct_dispatch'):
            prompt = (
                '原生执行者已交还账号，并在同次工具编排直接处理可用原后继；'
                '本通知仅用于最终汇总或需要协调处理的异常，不要再次派发已发送或未知的通知。'
                f'原task_id={event["task_id"]}，node_id={event["node_id"]}，event_id={event["id"]}。'
                f'协调原因：{event["direct_dispatch"].get("reason", "")}。'
                '收到后先核对原 task_id/node_id/event_id，下一次工作调用沿原dispatch及handoff_ack消费同一事件，再整理报告；unknown或sending不得换事件重发。'
                '只按当前真实结果处理原任务，保留原范围、用例和检查点，不恢复停止项。'
                '按消费回执coordination_plan定向处理：coordinator_only不转发，keep_running不打扰；原停止控制仍须传达。'
            )
        result.update(
            message_tool='send_message_to_thread',
            message_arguments={
                'threadId': thread_id(event['coordinator_ref']),
                'prompt': prompt,
            },
        )
    return result


def delivery(event, receipt, now):
    """Fence a message attempt before invoking the real desktop tool.

    Repeating a begin never grants permission to send again. A lost response
    leaves the attempt uncertain; only a positive delivery receipt or the
    recipient's consumption resolves it.
    """
    if (not isinstance(receipt, dict) or receipt.get('event_id') != event['id']
            or thread_id(receipt.get('thread_id')) != thread_id(event.get('coordinator_ref'))
            or not thread_id(event.get('coordinator_ref'))):
        raise PermissionError('发送回执不属于原交接事件或目标会话')
    attempt = receipt.get('attempt_id')
    if not isinstance(attempt, str) or not attempt or len(attempt) > 160:
        raise ValueError('交接发送需使用稳定 attempt_id')
    status = receipt.get('state')
    if status not in {'sending', 'sent', 'unknown', 'blocked'}:
        raise ValueError('未知交接发送状态')
    if event['delivery_state'] in {'obsolete', 'received'}:
        return False
    failure_stage = receipt.get('failure_stage')
    if failure_stage is not None and failure_stage not in {
            'message_target', 'message_tool', 'delivery_begin', 'desktop_send', 'delivery_receipt'}:
        raise ValueError('未知交接失败阶段')
    # A preflight failure never sent a message. Record it on the SAME notice so
    # the releasing tool can expose/notify its original coordinator event.
    if status == 'blocked' and failure_stage in {'message_target', 'message_tool'} and event['delivery_state'] == 'pending':
        event.update(delivery_attempt_id=attempt, delivery_state='blocked',
                     failure_stage=failure_stage, failure_observed_at=now,
                     delivery_source='desktop_tool_chain')
        return False
    if status == 'sending':
        if event['delivery_state'] != 'pending':
            return False
        event.update(delivery_state='sending', delivery_attempt_id=attempt,
                     delivery_started_at=now)
        return True
    if event.get('delivery_attempt_id') != attempt:
        raise PermissionError('发送结果不属于原发送尝试')
    if event['delivery_state'] == 'sent':
        return False
    event.update(delivery_state=status, delivery_source='desktop_tool_chain')
    if failure_stage:
        event.update(failure_stage=failure_stage, failure_observed_at=now)
    if status == 'sent':
        event.setdefault('sent_at', now)
    return False


def settlement_response(controller, state, node, lease_id, notification=None, delivery_receipt=None,
                        *, enable_direct=False):
    event = node.get('native_handoffs', {}).get(lease_id)
    if notification is not None:
        if (not isinstance(notification, dict) or notification.get('sent') is not True
                or not event or notification.get('event_id') != event['id']
                or not thread_id(event['coordinator_ref'])
                or thread_id(notification.get('thread_id')) != thread_id(event['coordinator_ref'])):
            raise PermissionError('交接发送回执不属于原事件或协调会话')
    if not event:
        return {}
    refresh(state, node, event, controller.clock(), controller)
    # Only the original, newly confirmed finish may choose this route. Retrying
    # a legacy event must not create another route around an uncertain send.
    if (enable_direct and event['delivery_state'] == 'pending'
            and not event.get('delivery_attempt_id') and not event.get('direct_dispatch')):
        event['direct_dispatch'] = {'source': 'executor_finish', 'started_at': controller.clock()}
        event['coordinator_notification_required'] = False
    if event.get('direct_dispatch'):
        return direct_settlement_response(controller, state, node, event, delivery_receipt)
    authorized = delivery(event, delivery_receipt, controller.clock()) if delivery_receipt else False
    if notification is not None and event['delivery_state'] != 'obsolete':
        event.setdefault('sent_at', controller.clock())
        event['delivery_source'] = 'executor_reported'
        if event['delivery_state'] != 'received':
            event['delivery_state'] = 'sent'
    result = {'handoff': response(event),
              'handoff_complete': event['delivery_state'] in {'sent', 'received', 'obsolete'}}
    result['needs_handoff'] = not result['handoff_complete']
    if delivery_receipt is not None:
        result['handoff']['send_authorized'] = authorized
    if not result['handoff_complete']:
        result['next_action'] = 'complete_native_handoff'
    return result


def direct_settlement_response(controller, state, node, event, delivery_receipt=None):
    """Plan/send under the releasing holder; never claim coordinator receipt."""
    task = state['tasks'][node['task_id']]
    if event['delivery_state'] == 'obsolete':
        return {'handoff': response(event), 'continuations': [], 'continuation': None,
                'handoff_route': 'direct_successors', 'needs_handoff': False,
                'handoff_complete': True}
    resumes = successors(controller, state, task, event, add=not delivery_receipt)
    authorized = False
    scope = [candidate for candidate in state['tasks'].values()
             if same_scope(state, task, candidate, event['coordinator_ref'])]
    group = state.get('native_continuation_groups', {}).get(task.get('native_continuation_group'), {})
    scoped = {item['id'] for item in scope}
    scope_mismatch = any(tid not in scoped and state['tasks'].get(tid, {}).get('intent') != 'stop'
                         for tid in group.get('members', {}))
    leaves = [state['nodes'][nid] for candidate in scope for nid in candidate['node_ids']
              if not state['nodes'][nid].get('child_ids')]
    ids = {item['id'] for item in leaves}
    has_leases = any(lease['node_id'] in ids for lease in state['leases'].values())
    reports_pending = any(item.get('native_report_pending') for item in leaves)
    terminal = bool(leaves) and not scope_mismatch and not has_leases and not reports_pending and all(
        item['state'] in {'completed', 'blocked', 'stopped'} for item in leaves)
    missing_binding = any(item['state'] == 'queued' and item.get('control_intent', 'run') == 'run'
                          and not thread_id((item.get('executor_dispatch') or item.get('dispatch_offer') or {}).get('executor_ref'))
                          for item in leaves)
    blocked = any(item['state'] in {'blocked', 'isolated', 'retained', 'waiting_human'}
                  or (item.get('native_executor_status') or {}).get('state') == 'unavailable' for item in leaves)
    def update_status():
        uncertain = any(item['delivery_state'] in {'sending', 'unknown', 'blocked', 'unbound'} for item in resumes)
        attention = uncertain or missing_binding or blocked or scope_mismatch
        reason = ('原授权组已结束，汇总原结果' if terminal else
                  '通知结果待核实或原任务需要协调处理，不重发未知通知' if attention else
                  '已直接安排有资源的原后继' if resumes else
                  '账号已交还，原执行者正在补充报告；报告齐全后通知协调者' if reports_pending else
                  '原任务仍在进行或等待资源/依赖；当前无可通知后继')
        event['direct_dispatch'].update(
            state='attention_required' if attention else 'group_finished' if terminal else
                  'successors_selected' if resumes else 'waiting_resources',
            reason=reason, checked_at=controller.clock())
        event['coordinator_notification_required'] = bool(terminal or attention)
    update_status()
    if delivery_receipt is not None:
        target = event if delivery_receipt.get('event_id') == event['id'] else next(
            (item for item in event['continuations'] if item['id'] == delivery_receipt.get('event_id')), None)
        if target is None:
            raise Conflict('发送回执不属于本次直接接续事件')
        # Check current need before a new coordinator send, but never discard
        # a real attempt's later receipt merely because its worker has progressed.
        if (target is not event or delivery_receipt.get('state') != 'sending'
                or event['coordinator_notification_required']):
            authorized = delivery(target, delivery_receipt, controller.clock())
        resumes = [response(item) for item in event['continuations']]
        update_status()
    handoff = response(event)
    pending = any(item['delivery_required'] for item in resumes) or handoff['delivery_required']
    result = {'handoff_route': 'direct_successors', 'handoff': handoff,
              'continuations': resumes, 'continuation': resumes[0] if resumes else None,
              'needs_handoff': pending, 'handoff_complete': not pending}
    result['handoff_recovery'] = {
        'event_id': event['id'], 'task_id': event['task_id'], 'node_id': event['node_id'],
        'entry': 'original_finish_or_coordinator_handoff_ack',
        'instruction': '后续合法进入原执行/协调会话时，只补偿同一事件；pending可发，sending/unknown不重发。协调工具可有限观察，退出后无后台唤醒。',
    }
    if delivery_receipt is not None:
        result['send_authorized'] = authorized
    if pending:
        result['next_action'] = 'complete_native_handoff'
    return result


def continuation(controller, state, task, event, nominations=()):
    """Return the original eligible worker, without allocating or changing scope.

    Real claims alone own accounts. Notification attempts fence duplicate sends,
    not resource capacity. Only new candidates in this matching pass share a
    temporary preview budget; it is discarded before returning.
    """
    from .resource_scheduler import ResourceScheduler
    from .native_contexts import lease_context_fields
    current = event.get('continuation')
    outstanding = set()
    for source in state['nodes'].values():
        for item in source.get('native_handoffs', {}).values():
            for pending in notices(item):
                target = state['nodes'].get(pending['node_id'], {})
                if item['delivery_state'] == 'obsolete' or not matches_target(state, pending):
                    obsolete(pending)
                elif target.get('state') == 'running':
                    pending['delivery_state'] = 'received'
                    pending.setdefault('claimed_at', now_claimed(state, target, controller.clock()))
                elif target.get('state') != 'queued':
                    obsolete(pending)
                if pending['delivery_state'] in {'pending', 'waiting_resources', 'sending', 'sent', 'unknown', 'blocked'}:
                    outstanding.add(pending['node_id'])
    # Invalidation above remains global. Once this scope has no possible queued
    # recipient, copying every historical node/account and running a resource
    # preview cannot produce a successor. Do not skip existing-event validation.
    if not current and not any(
            target.get('state') == 'queued' and not target.get('child_ids')
            and target['id'] not in outstanding
            and same_scope(state, task, state['tasks'][target['task_id']], event['coordinator_ref'])
            and thread_id((target.get('executor_dispatch') or target.get('dispatch_offer') or {}).get('executor_ref'))
            and thread_id(coordinator_ref(target)) == thread_id(event['coordinator_ref'])
            for target in state['nodes'].values()):
        return None
    def resource_preview():
        reservations = {}
        for nomination in nominations:
            if current and nomination['id'] == current['id']:
                continue
            target = state['nodes'][nomination['node_id']]
            key = 'preview:' + nomination['id']
            reservations[key] = {
                'id': key, 'node_id': target['id'], 'native_browser': True,
                'account_ids': nomination['candidate_account_ids'],
                'mode': nomination['resource_mode'], 'revoked': False,
                **(lease_context_fields(state, target, nomination['candidate_account_ids']) or {})}
        preview = {**state, 'nodes': {key: copy_node(value) for key, value in state['nodes'].items()},
                   'accounts': copy.deepcopy(state['accounts']), 'leases': {**state['leases'], **reservations}}
        return preview, ResourceScheduler(controller, preview, controller.clock())

    def respect_prior(target, preview, scheduler):
        # Scope restricts who may be messaged, never who has queue priority.
        # Mirror admissible earlier registered workers in the preview only.
        for prior in scheduler.queue():
            if prior['id'] == target['id']:
                break
            binding = prior.get('executor_dispatch') or prior.get('dispatch_offer') or {}
            if (prior['id'] in outstanding
                    or state['tasks'][prior['task_id']].get('execution_route') != 'native_browser'
                    or not thread_id(binding.get('executor_ref'))):
                continue
            accounts, shared, _ = scheduler.native_availability(prior, for_wake=True)
            if accounts is not None:
                key = 'priority:' + prior['id']
                preview['leases'][key] = {
                    'id': key, 'node_id': prior['id'], 'native_browser': True,
                    'account_ids': accounts, 'mode': 'shared' if shared else 'exclusive', 'revoked': False,
                    **(lease_context_fields(preview, prior, accounts) or {})}
    if current:
        target = state['nodes'].get(current['node_id'], {})
        target_task = state['tasks'].get(target.get('task_id'), {})
        receipt = target.get('executor_dispatch') or target.get('dispatch_offer') or {}
        bound = current['claim_arguments']
        if (event['delivery_state'] == 'obsolete' or not target
                or not matches_target(state, current)
                or target.get('control_intent', 'run') != 'run'
                or target.get('session_removed') or target_task.get('intent') != 'run'
                or not same_scope(state, task, target_task, event['coordinator_ref'])
                or target_task.get('revision') != current['task_revision']
                or target.get('revision') != current['node_revision']
                or receipt.get('holder_id') != bound['holder_id']
                or (receipt.get('dispatch_id') or receipt.get('id')) != bound['dispatch_id']
                or thread_id(receipt.get('executor_ref')) != thread_id(bound['executor_ref'])):
            obsolete(current)
        elif target.get('state') != 'queued':
            current['delivery_state'] = 'received' if target.get('state') == 'running' else 'obsolete'
        elif current['delivery_state'] in {'pending', 'waiting_resources'}:
            try:
                controller.sessions.assert_available(state, target_task, [target['id']])
            except (Conflict, ValueError):
                obsolete(current)
                return response(current)
            preview, scheduler = resource_preview()
            respect_prior(target, preview, scheduler)
            accounts, shared, reason = scheduler.native_availability(preview['nodes'][target['id']], for_wake=True)
            if accounts is None:
                current.update(delivery_state='waiting_resources', wait_reason=reason, candidate_account_ids=[])
            else:
                current.pop('wait_reason', None)
                selected = preview['nodes'][target['id']].get('work_selection')
                if target.get('checkpoint', {}).get('work_plan') and selected:
                    from .native_work_plan import TOKEN_FIELDS
                    current['claim_arguments']['account_ids'] = list(accounts)
                    current['claim_arguments'].setdefault('arguments', {})['work_token'] = {
                        k: selected[k] for k in TOKEN_FIELDS}
                current.update(delivery_state='pending', candidate_account_ids=accounts, resource_mode='shared' if shared else 'exclusive',
                    environment_preparation_required=lease_context_fields(preview, target, accounts) is None,
                    required_context_count=len(accounts))
        return response(current)
    if event['delivery_state'] != 'received' and not event.get('direct_dispatch'):
        return None
    preview, scheduler = resource_preview()
    for target in scheduler.queue():
        receipt = target.get('executor_dispatch') or target.get('dispatch_offer') or {}
        target_task = state['tasks'][target['task_id']]
        if target['id'] in outstanding:
            continue
        if (not same_scope(state, task, target_task, event['coordinator_ref'])
                or not thread_id(receipt.get('executor_ref'))
                or thread_id(coordinator_ref(target)) != thread_id(event['coordinator_ref'])):
            if (target_task.get('execution_route') == 'native_browser'
                    and thread_id(receipt.get('executor_ref'))):
                accounts, shared, _ = scheduler.native_availability(target, for_wake=True)
                if accounts is not None:
                    key = 'priority:' + target['id']
                    preview['leases'][key] = {
                        'id': key, 'node_id': target['id'], 'native_browser': True,
                        'account_ids': accounts, 'mode': 'shared' if shared else 'exclusive', 'revoked': False,
                        **(lease_context_fields(preview, target, accounts) or {})}
            continue
        accounts, shared, _ = scheduler.native_availability(target, for_wake=True)
        if accounts is None:
            continue
        try:
            controller.sessions.assert_available(state, target_task, [target['id']])
        except (Conflict, ValueError):
            continue
        claim = {'action': 'claim', 'task_id': target_task['id'], 'node_id': target['id'],
                 'holder_id': receipt['holder_id'], 'dispatch_id': receipt.get('dispatch_id') or receipt.get('id'),
                 'executor_ref': receipt['executor_ref'], 'coordinator_ref': event['coordinator_ref']}
        if target.get('checkpoint', {}).get('work_plan'):
            from .native_work_plan import TOKEN_FIELDS
            claim.update(account_ids=list(accounts), arguments={'work_token':
                {k: target['work_selection'][k] for k in TOKEN_FIELDS}})
        generation = sum(item['node_id'] == target['id'] for item in notices(event))
        current = {'id': event['id'] + ':resume:' + target['id'] + (':' + str(generation) if generation else ''),
                   'source_event_id': event['id'], 'task_id': target_task['id'],
                   'node_id': target['id'], 'task_revision': target_task['revision'],
                   'node_revision': target['revision'],
                   'coordinator_ref': receipt['executor_ref'], 'created_at': controller.clock(),
                   'delivery_state': 'pending', 'kind': 'resume_original_worker',
                   'candidate_account_ids': accounts, 'resource_mode': 'shared' if shared else 'exclusive',
                   'required_context_count': len(accounts),
                   'environment_preparation_required': lease_context_fields(preview, target, accounts) is None,
                   'claim_arguments': claim}
        event['continuation'] = current
        return response(current)
    return None


def successors(controller, state, task, event, *, add=True, nominations=None):
    existing = event.setdefault('continuations', notices(event))
    # Historical sends never reserve accounts. Limit only this pass's newly
    # sendable candidates to the actual complete resource bundles available now.
    fingerprint = resource_fingerprint(state)
    add = add and event.get('match_fingerprint') != fingerprint
    if nominations is None:
        nominations = [notice for source in state['nodes'].values()
                       for original in source.get('native_handoffs', {}).values() for notice in notices(original)
                       if notice.get('matched_resource_fingerprint') == fingerprint
                       and notice['delivery_state'] in {'pending', 'sending', 'sent', 'unknown', 'blocked'}]
    for item in existing:
        previous_state = item['delivery_state']
        continuation(controller, state, task, {**event, 'continuation': item}, nominations)
        if previous_state in {'pending', 'waiting_resources'} and item['delivery_state'] == 'pending':
            item['matched_resource_fingerprint'] = fingerprint
            if not any(saved['id'] == item['id'] for saved in nominations):
                nominations.append(item)
    if add:
        while True:
            candidate = continuation(controller, state, task, {**event, 'continuation': None}, nominations)
            if not candidate:
                break
            # response() is a view; persist only stable notification facts.
            saved = {key: value for key, value in candidate.items()
                     if key not in {'message_tool', 'message_arguments', 'delivery_required',
                                    'automatic_delivery', 'required_client_capability', 'client_update_url'}}
            saved['matched_resource_fingerprint'] = fingerprint
            existing.append(saved)
            nominations.append(saved)
    if add:
        event['match_fingerprint'] = fingerprint
        event['matched_at'] = controller.clock()
    event['continuation'] = existing[0] if existing else None
    return [response(item) for item in existing]


def acknowledge(controller, state, owner, task, args):
    ack = (args.get('arguments') or {}).get('handoff_ack')
    if not isinstance(ack, dict) or ack.get('task_id') != task['id']:
        raise ValueError('handoff_ack 需包含原 task_id、node_id 和 event_id')
    node = controller.owned(state['nodes'], owner, ack.get('node_id'))
    if node['task_id'] != task['id']:
        raise PermissionError('交接事件不属于当前任务')
    event = node.get('native_handoffs', {}).get(ack.get('event_id'))
    reference = args.get('coordinator_ref') or args.get('holder_id')
    if (not event or not thread_id(reference)
            or thread_id(reference) != thread_id(event['coordinator_ref'])):
        raise PermissionError('交接事件不属于当前协调会话')
    refresh(state, node, event, controller.clock(), controller)
    def plan(resumes=()):
        from .module_dispatch import coordination_plan
        leaves = [candidate for candidate in state['nodes'].values()
                  if same_scope(state, task, state['tasks'][candidate['task_id']], event['coordinator_ref'])
                  and thread_id(coordinator_ref(candidate)) == thread_id(event['coordinator_ref'])]
        observation = handoff_observation(leaves, state['tasks'].values(), state['leases'].values(),
                                           controller.clock(), events=[event])
        return coordination_plan(leaves, resumes, observation)
    if event['delivery_state'] == 'obsolete':
        return {'accepted': False, 'handoff': response(event), 'continuation': None,
                'continuations': [], 'needs_handoff': False, 'coordination_plan': plan()}
    event.update(delivery_state='received')
    event.setdefault('received_at', controller.clock())
    result = {'accepted': True, 'handoff': response(event)}
    delivery_receipt = (args.get('arguments') or {}).get('handoff_delivery')
    resumes = successors(controller, state, task, event, add=not delivery_receipt)
    if delivery_receipt:
        resume = next((item for item in event['continuations'] if item['id'] == delivery_receipt.get('event_id')), None)
        if not resume:
            raise Conflict('此交接没有可发送的后继会话')
        result['send_authorized'] = delivery(resume, delivery_receipt, controller.clock())
        resumes = [response(item) for item in event['continuations']]
    result['continuations'] = resumes
    result['continuation'] = resumes[0] if resumes else None
    result['needs_handoff'] = any(item['delivery_required'] for item in resumes)
    result['handoff_complete'] = not result['needs_handoff']
    result['coordination_plan'] = plan(resumes)
    return result


def latest(node):
    events = node.get('native_handoffs', {})
    for attempt in reversed(node.get('attempts', [])):
        if attempt.get('lease_id') in events:
            return copy.deepcopy(events[attempt['lease_id']])
    return copy.deepcopy(max(events.values(), key=lambda event: event['created_at'])) if events else None


def now_claimed(state, node, fallback):
    return next((lease['created'] for lease in state['leases'].values()
                 if lease['node_id'] == node['id']), fallback)


def resource_fingerprint(state):
    """Only matching inputs, excluding reports, heartbeats and notification state."""
    return digest({
        'accounts': [{key: account.get(key) for key in
                      ('id', 'owner', 'projects', 'target', 'environment', 'tenant', 'identity', 'roles', 'state', 'pool')}
                     for account in state['accounts'].values()],
        'leases': [{key: lease.get(key) for key in
                    ('id', 'node_id', 'account_ids', 'mode', 'revoked', 'native_context_binding')}
                   for lease in state['leases'].values()],
        'nodes': [{key: node.get(key) for key in
                   ('id', 'task_id', 'state', 'revision', 'control_intent', 'depends_on', 'locks', 'phase',
                    'requirements', 'requested_account_ids', 'preferred_account_ids', 'protected', 'reservation',
                    'native_environment_keys', 'native_environment_lifecycle', 'native_executor_status')}
                  for node in state['nodes'].values()],
        'tasks': [{key: task.get(key) for key in
                   ('id', 'revision', 'intent', 'native_continuation_group', 'account_project_deleted')}
                  for task in state['tasks'].values()],
        'work_plans': [(n['id'], n.get('checkpoint', {}).get('work_plan', {}).get('plan_revision'),
                        (state.get('_work_record_views', {}).get(n['id'], {}).get('record') or {}).get('revision'))
                       for n in state['nodes'].values() if n['state'] == 'queued' and n.get('checkpoint', {}).get('work_plan')]})


def pending_handoffs(nodes):
    return [{'task_id': event['task_id'], 'node_id': event['node_id'], 'event_id': event['id'],
             'automatic_delivery': False, 'delivery_state': event['delivery_state']}
            for node in nodes for event in node.get('native_handoffs', {}).values()
            if event['delivery_state'] != 'obsolete' and
            (response(event)['delivery_required'] or any(response(item)['delivery_required'] for item in notices(event)))]


def handoff_observation(nodes, tasks, leases, now, *, events=None):
    """Compact, read-only facts. A desktop turn is never an account claim.

    Observation age is diagnostic only; no matching, expiry, allocation or
    mutation occurs here. Keep original source and target bindings in every row.
    """
    from .direct_execution import START_TIMEOUT
    by_node = {node['id']: node for node in nodes}
    by_task = {task['id']: task for task in tasks}
    leased = {lease['node_id']: lease for lease in leases}
    rows = []
    originals = events if events is not None else [event for node in nodes
        for event in node.get('native_handoffs', {}).values()]
    for event in originals:
        source_task = by_task.get(event['task_id'], {})
        source_node = by_node.get(event['node_id'], {})
        source_current = (source_task.get('revision') == event['task_revision']
            and source_task.get('intent') == 'run' and source_node.get('control_intent', 'run') == 'run'
            and not source_task.get('account_project_deleted') and not source_node.get('session_removed'))
        for notice in [event, *notices(event)]:
            worker = notice.get('kind') == 'resume_original_worker'
            target = by_node.get(notice['node_id'], {})
            claim = notice.get('claim_arguments', {})
            current = source_current and notice['delivery_state'] not in {'obsolete', 'transferred'}
            if worker:
                current = current and matches_target({'nodes': by_node, 'tasks': by_task}, notice)
            lease = leased.get(notice['node_id']) if worker and current else None
            binding = target.get('executor_dispatch') or target.get('dispatch_offer') or {}
            consumed = notice.get('claim_received_at') if worker else notice.get('received_at')
            started = notice.get('delivery_started_at', notice.get('created_at', now))
            age = max(0, now - started)
            state = notice['delivery_state']
            reason = None
            if not current:
                phase = 'obsolete'
            elif worker and lease:
                phase = 'claimed'
            elif worker and consumed:
                phase = 'claim_attempted_waiting_resources' if target.get('state') == 'queued' else 'claim_consumed'
            elif worker and (target.get('native_executor_status') or {}).get('state') == 'unavailable':
                phase, reason = 'model_unavailable', 'original_model_error'
            elif state == 'waiting_resources':
                phase = 'waiting_resources'
            elif worker and target.get('state') in {'completed', 'stopped', 'blocked'}:
                phase = 'target_ended'
            elif state in {'blocked', 'unbound', 'unknown'}:
                phase, reason = state, 'delivery_' + state
            elif state == 'sending':
                phase = 'sending_unconfirmed'
                reason = 'delivery_begin_without_receipt' if age >= START_TIMEOUT else None
            elif worker and state == 'sent':
                phase = 'sent_awaiting_claim'
                reason = 'sent_without_actual_claim' if age >= START_TIMEOUT else None
            elif worker and state == 'pending':
                phase = 'pending_delivery'
                # Let the live releasing tool perform the primary direct send.
                # Age only surfaces a missing delivery, never authorizes resend.
                reason = 'original_notice_pending' if not event.get('direct_dispatch') or age >= START_TIMEOUT else None
            elif not worker and response(event)['delivery_required']:
                phase, reason = 'coordinator_event_pending', 'original_event_unconsumed'
            else:
                phase = 'consumed' if consumed else 'no_delivery_required'
            row = {'task_id': event['task_id'], 'node_id': event['node_id'], 'event_id': event['id'],
                'notice_id': notice['id'], 'kind': notice.get('kind', 'release'),
                'target_task_id': notice['task_id'], 'target_node_id': notice['node_id'],
                'target_thread_id': thread_id(notice.get('coordinator_ref')),
                'coordinator_ref': event.get('coordinator_ref'), 'delivery_state': state,
                'phase': phase, 'attention_reason': reason, 'current_binding': bool(current),
                'has_lease': bool(lease), 'claim_received_at': notice.get('claim_received_at'),
                'claimed_at': lease.get('created') if lease else notice.get('claimed_at'),
                'sent_at': notice.get('sent_at'), 'received_at': notice.get('received_at'),
                'delivery_started_at': notice.get('delivery_started_at'),
                'created_at': notice.get('created_at'), 'failure_stage': notice.get('failure_stage'),
                'resource_change': event.get('resource_change'), 'matched_at': event.get('matched_at'),
                'wait_reason': notice.get('wait_reason') or (target.get('reason') if worker and not lease else None),
                'holder_id': claim.get('holder_id'), 'dispatch_id': claim.get('dispatch_id'),
                'task_revision': notice.get('task_revision'), 'node_revision': notice.get('node_revision'),
                'executor_exit_confirmed': bool(binding.get('exit_acknowledged_at'))}
            if phase in {'obsolete', 'no_delivery_required'}:
                continue
            if phase in {'consumed', 'claim_consumed', 'claim_attempted_waiting_resources', 'claimed', 'target_ended'} and now - (consumed or notice.get('claimed_at') or notice.get('created_at', now)) > START_TIMEOUT:
                continue
            rows.append(row)
    return {'observed_at': now, 'observation_seconds': START_TIMEOUT,
            'time_is_not_failure_or_release': True, 'events': rows,
            'attention': [row for row in rows if row['attention_reason']],
            'automatic_delivery': False}


def reconcile_resources(controller, state, *, preferred=None):
    """Match once when actual resource/control inputs change, on the old scheduler.

    Persist only: the existing desktop tool chain still owns actual delivery.
    No new timer, relay or model turn is started by this reconciliation.
    """
    fingerprint = resource_fingerprint(state)
    previous = state.get('native_resource_change') or {}
    if previous.get('fingerprint') == fingerprint and not preferred:
        return
    now = controller.clock()
    change = {'fingerprint': fingerprint, 'sequence': previous.get('sequence', 0) + 1, 'at': now}
    state['native_resource_change'] = change
    covered = set()
    nominations = []
    events = [(node, event) for node in state['nodes'].values()
              for event in node.get('native_handoffs', {}).values()]
    source = next(((node, event) for node, event in events if preferred
                   and node['id'] == preferred['node_id'] and event['id'] == preferred['event_id']), None)
    if source:
        node, event = source
        if (preferred.get('enable_direct') and event['delivery_state'] == 'pending'
                and not event.get('delivery_attempt_id') and not event.get('direct_dispatch')):
            event['direct_dispatch'] = {'source': 'executor_finish', 'started_at': now}
            event['coordinator_notification_required'] = False
        # The live releasing tool owns this resource change. Move only notices
        # with no send attempt to that event; uncertain/sent messages stay fenced
        # under their original event and are never transferred or resent.
        if event.get('direct_dispatch'):
            adopted = event.setdefault('continuations', notices(event))
            task = state['tasks'][event['task_id']]
            for _, original in events:
                if original is event or original['delivery_state'] == 'obsolete':
                    continue
                for notice in notices(original):
                    target = state['tasks'].get(notice['task_id'], {})
                    if (notice['delivery_state'] not in {'pending', 'waiting_resources'}
                            or notice.get('delivery_attempt_id') or not matches_target(state, notice)
                            or not same_scope(state, task, target, event['coordinator_ref'])):
                        continue
                    moved = copy.deepcopy(notice)
                    moved.update(id=event['id'] + ':resume:' + notice['node_id'] + ':transfer:' + str(len(adopted)),
                                 source_event_id=event['id'], delivery_state='waiting_resources')
                    moved.pop('matched_resource_fingerprint', None)
                    notice.update(delivery_state='transferred', transferred_to=event['id'], transferred_at=now)
                    adopted.append(moved)
        events.remove(source)
        events.insert(0, source)
    for node, event in events:
        refresh(state, node, event, now, controller)
        if event['delivery_state'] == 'obsolete':
            continue
        task = state['tasks'][event['task_id']]
        covered.update(target['id'] for target in state['tasks'].values()
                       if same_scope(state, task, target, event['coordinator_ref']))
        if event.get('direct_dispatch') or event['delivery_state'] == 'received':
            successors(controller, state, task, event, nominations=nominations)
    # A new account/environment may become ready before any module has finished.
    # Use the same coordinator handoff/ACK path, accurately labelled as a resource
    # event rather than an executor exit. One event covers its authorized scope.
    from .resource_scheduler import ResourceScheduler
    scheduler = ResourceScheduler(controller, state, now)
    for node in scheduler.queue():
        task = state['tasks'][node['task_id']]
        reference = coordinator_ref(node)
        binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
        if (task['id'] in covered or task.get('execution_route') != 'native_browser'
                or not thread_id(reference) or not thread_id(binding.get('executor_ref'))):
            continue
        accounts, _, _ = scheduler.native_availability(node, for_wake=True)
        if accounts is None:
            continue
        key = 'resource:' + node['id'] + ':' + str(change['sequence'])
        event = {'id': key, 'kind': 'resource_change', 'task_id': task['id'], 'node_id': node['id'],
                 'task_revision': task['revision'], 'coordinator_ref': reference, 'created_at': now,
                 'delivery_state': 'pending', 'resource_change': copy.deepcopy(change)}
        node.setdefault('native_handoffs', {})[key] = event
        covered.update(target['id'] for target in state['tasks'].values()
                       if same_scope(state, task, target, reference))


def consume_on_claim(state, node, now):
    """A real original worker call ends its previous wake wait, even if it loses
    the account race. This is claim evidence, not a fabricated desktop send ACK.
    A later actual resource change can nominate it again under a new notice ID.
    """
    for source in state['nodes'].values():
        for event in source.get('native_handoffs', {}).values():
            for notice in notices(event):
                if (notice['node_id'] == node['id'] and matches_target(state, notice)
                        and notice['delivery_state'] in {'pending', 'waiting_resources', 'sending', 'sent', 'unknown', 'blocked'}):
                    notice.update(delivery_state='received', claim_received_at=now,
                                  consumption_source='original_executor_claim')
