"""Explicit desktop status receipts on the existing dispatch boundary.

No desktop log reader, model switch, retry loop or synthetic capacity. A report
is attributed to its original binding and never releases an active browser.
"""
from __future__ import annotations

import copy

from .orchestration import Conflict, text


def unavailable(node):
    return (node.get('native_executor_status') or {}).get('state') == 'unavailable'


def report(controller, db, state, owner, task, args, value):
    from .native_handoff import coordinator_ref, thread_id
    if task.get('execution_route') != 'native_browser' or not isinstance(value, dict):
        raise ValueError('executor_status 仅用于原生桌面执行者的真实回执')
    node = controller.owned(state['nodes'], owner, value.get('node_id'))
    binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
    if (node['task_id'] != task['id'] or value.get('task_revision') != task['revision']
            or value.get('node_revision') != node['revision']
            or value.get('holder_id') != binding.get('holder_id')
            or value.get('dispatch_id') != (binding.get('dispatch_id') or binding.get('id'))
            or not thread_id(value.get('executor_ref'))
            or thread_id(value['executor_ref']) != thread_id(binding.get('executor_ref'))):
        raise Conflict('执行者状态回执不属于当前原任务、节点或派发代际')
    caller = args.get('holder_id')
    coordinator = thread_id(args.get('coordinator_ref'))
    if caller != binding.get('holder_id') and (not coordinator or coordinator != thread_id(coordinator_ref(node))):
        raise PermissionError('仅原执行者或绑定协调会话可报告模型状态')
    if (task.get('intent') != 'run' or node.get('control_intent', 'run') != 'run'
            or node.get('state') not in {'queued', 'running', 'isolated', 'retained', 'waiting_human'}):
        raise Conflict('已停止或暂停；模型状态回执不能恢复任务')
    status = value.get('state')
    if status not in {'unavailable', 'available'}:
        raise ValueError('executor_status.state 必须为 unavailable 或 available')
    source = value.get('source')
    if source not in {'codex_turn_error', 'codex_turn_started'} or (status == 'unavailable') != (source == 'codex_turn_error'):
        raise ValueError('模型异常须引用真实 codex_turn_error；恢复须引用原模型实际 codex_turn_started')
    reference = text(value.get('reference'), '真实桌面事件引用', 1000)
    reason = text(value.get('reason'), '真实模型状态说明', 2000)
    model = text(value.get('model'), '原会话实际模型', 200)
    kind = value.get('kind', 'runtime_error')
    if kind not in {'capacity', 'startup_error', 'runtime_error'}:
        raise ValueError('模型异常 kind 必须为 capacity/startup_error/runtime_error')
    previous = node.get('native_executor_status') or {}
    if status == 'available' and (previous.get('state') != 'unavailable'
            or value.get('resolves_reference') != previous.get('reference')
            or previous.get('model') != model):
        raise Conflict('恢复须对应当前原错误及原模型；旧回执不能清除新异常或自动切换模型')
    if any(item.get('reference') == reference for item in
           [previous, *node.get('native_executor_status_history', [])]):
        return {'node_id': node['id'], 'executor_status': copy.deepcopy(previous), 'duplicate_receipt': True}
    receipt = {key: copy.deepcopy(value[key]) for key in
               ('node_id', 'task_revision', 'node_revision', 'holder_id', 'dispatch_id', 'executor_ref')}
    receipt.update(state=status, source=source, reference=reference, reason=reason,
                   model=model, kind=kind, resolves_reference=value.get('resolves_reference'), reported_at=controller.clock(), observed_by='explicit_desktop_receipt')
    if previous:
        node.setdefault('native_executor_status_history', []).append(copy.deepcopy(previous))
    node['native_executor_status'] = receipt
    leased = any(lease['node_id'] == node['id'] for lease in state['leases'].values())
    if status == 'unavailable' and not leased:
        node.pop('native_claim_pending', None)
        node['reservation'] = None
    controller.audit(db, owner, 'native.executor_status', node['id'], status + ':' + kind)
    return {'node_id': node['id'], 'executor_status': copy.deepcopy(receipt),
            'accounts_retained': leased, 'automatic_delivery': False,
            'next_action': 'resolve_existing_hold' if leased and status == 'unavailable' else 'wait_for_original_executor'}


def received(node, now):
    """The original worker's real claim is evidence that its turn is running."""
    from .native_identity import same_executor_ref
    previous = node.get('native_executor_status')
    if not previous or previous.get('state') != 'unavailable':
        return
    binding = node.get('executor_dispatch') or {}
    if (previous.get('holder_id') != binding.get('holder_id')
            or previous.get('dispatch_id') != binding.get('dispatch_id')
            or not same_executor_ref(previous.get('executor_ref'), binding.get('executor_ref'))):
        return
    node.setdefault('native_executor_status_history', []).append(copy.deepcopy(previous))
    node['native_executor_status'] = {**previous, 'state': 'available', 'source': 'executor_claim',
        'reported_at': now, 'reason': '原执行会话已实际领取，沿原模型及检查点继续；不重放已完成或未知动作'}
