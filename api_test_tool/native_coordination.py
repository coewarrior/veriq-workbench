"""Native coordinator lifecycle facts, separate from business result settlement.

An ended desktop turn is not a browser exit. Quiet resource waits never expire
by wall clock. Only the original coordinator can end its scheduling generation.
"""
import copy
import math
import json

from .native_identity import same_executor_ref
from .orchestration import text, digest, Conflict
from .orchestration_storage import History, select_records


TERMINAL = {'completed', 'blocked', 'stopped', 'paused'}


def inventory(state, task, root, report_workers=()):
    from .deployment_activity import classify_activity
    actions = []
    for kind, ended in (('operations', {'confirmed', 'not_sent'}),
                        ('direct_commands', {'completed', 'blocked', 'confirmed', 'not_sent', 'cancelled'})):
        # History stays lazy and filtered. Do not load saved case/result bodies.
        unresolved = ('pending', 'unknown') if kind == 'operations' else ('queued', 'running', 'unknown')
        actions.extend(operation for operation in select_records(state.get(kind, {}), state=unresolved)
                       if operation.get('owner', task['owner']) == task['owner'] and operation.get('state') not in ended)
    classified = classify_activity(root, state, actions, {task['id']}, report_workers)
    nodes = [n for n in state['nodes'].values() if n['task_id'] == task['id']]
    queued = [{'node_id': n['id'], 'reason': n.get('resource_wait', {}).get('reason') or n.get('reason'),
               'binding': copy.deepcopy(n.get('executor_dispatch') or n.get('dispatch_offer') or {})}
              for n in nodes if n['state'] == 'queued']
    fields = ('id', 'source_node_id', 'case_id', 'state', 'object_type', 'object_id', 'classification', 'retain_scene')
    cleanup = [{k: copy.deepcopy(obj[k]) for k in fields if k in obj}
               for obj in state.get('cleanup_objects', {}).values()
               if obj.get('owner') == task['owner'] and obj.get('task_id') == task['id'] and obj.get('state') != 'cleaned']
    return {'queued': queued, 'in_flight': classified['blockers'],
            'pending_handoffs': [row for row in classified['waiting'] if row['code'] == 'handoff_pending'],
            'activity': classified, 'cleanup_responsibilities': cleanup,
            'can_end_scheduling': not classified['blockers'],
            'disposition': (None if task.get('intent') == 'run' and
                            task.get('coordinator_closeout', {}).get('disposition') == 'ended'
                            else task.get('coordinator_closeout', {}).get('disposition')),
            'instruction': '协调者退出前核对原清理责任、阻塞恢复条件与剩余阶段；条件解除及时沿原执行者续测未完成项。'
                '本轮交付部分结果并结束时登记 coordinator_closeout.disposition=ended；'
                '继续等待则登记 waiting 和真实条件。结束调度不代表业务对象已清理或用例通过。'}


def view(controller, owner, task_id):
    from .deployment_activity import read_activity_state
    with controller.connect() as db:
        db.execute('BEGIN')
        state = read_activity_state(db, postgres=True)
        state['operations'] = History(db, 'operations')
        state['direct_commands'] = History(db, 'direct_commands')
        task = controller.owned(state['tasks'], owner, task_id)
        return inventory(state, task, controller.store.root, controller.report_worker_node_ids())


def call(controller, owner, args):
    """Keep successful receipts idempotent; recheck an unfinished closeout."""
    key, signature = text(args.get('request_id'), 'request_id', 160), digest(args)
    with controller.transaction() as (db, state):
        old = db.execute('SELECT hash,value FROM receipts WHERE owner=%s AND key=%s', (owner, key)).fetchone()
        if old:
            if old[0] != signature:
                raise Conflict('request_id 已用于不同内容，请读取原任务或使用新标识')
            saved = json.loads(old[1])
            if saved.get('accepted'):
                return saved
        task = controller.owned(state['tasks'], owner, args.get('task_id'))
        result = update(controller, db, state, owner, task, args)
        db.execute('INSERT INTO receipts(owner,key,hash,value) VALUES(%s,%s,%s,%s) '
                   'ON CONFLICT(owner,key) DO UPDATE SET hash=EXCLUDED.hash,value=EXCLUDED.value',
                   (owner, key, signature, json.dumps(result)))
        return result


def update(controller, db, state, owner, task, args):
    from .native_handoff import thread_id, obsolete, notices
    nodes = [n for n in state['nodes'].values() if n['task_id'] == task['id']]
    reference = thread_id(args.get('coordinator_ref'))
    bindings = []
    for node in nodes:
        binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
        if node.get('child_ids') and not binding and not node.get('direct_holder') and not node.get('attempts'):
            continue
        if not binding and not any(node.get(key) for key in
                ('attempts', 'direct_holder', 'executor_dispatch_history', 'dispatch_offer_history')):
            continue  # Excluded, never-dispatched leaves need no desktop identity.
        bindings.append(binding)
    if (task.get('execution_route') != 'native_browser' or not reference or not bindings
            or any(not same_executor_ref(b.get('coordinator_ref'), reference) for b in bindings)):
        raise PermissionError('生命周期回执仅属于本轮原协调会话')
    values = args['arguments']
    now = controller.clock()
    if 'desktop_observations' in values:
        rows = values['desktop_observations']
        if not isinstance(rows, list) or not rows:
            raise ValueError('desktop_observations 需要原桌面回执')
        for row in rows:
            node = controller.owned(state['nodes'], owner, row.get('node_id'))
            binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
            if (node['task_id'] != task['id'] or row.get('dispatch_id') != (binding.get('dispatch_id') or binding.get('id'))
                    or not same_executor_ref(row.get('executor_ref'), binding.get('executor_ref'))):
                raise PermissionError('桌面回执不属于本轮当前执行代次')
            ended = row.get('completed_at')
            if (row.get('status') not in {'completed', 'failed', 'error', 'interrupted'}
                    or not row.get('turn_id') or type(ended) not in {float, int} or not math.isfinite(ended)
                    or ended < max(binding.get('created_at', 0), binding.get('received_at', 0), binding.get('last_seen_at', 0))):
                raise ValueError('仅记录当前代次真实结束的桌面回合；不推断浏览器退出')
            old = node.get('desktop_observation') or {}
            if ended >= old.get('completed_at', 0):
                node['desktop_observation'] = {k: copy.deepcopy(row[k]) for k in
                    ('dispatch_id', 'executor_ref', 'turn_id', 'status', 'completed_at')}
                node['desktop_observation']['observed_at'] = now
        return {'accepted': True, 'task_id': task['id'], 'modules': []}
    closeout = values['coordinator_closeout']
    disposition = closeout.get('disposition')
    if disposition not in {'waiting', 'ended'}:
        raise ValueError('coordinator_closeout.disposition 必须是 waiting 或 ended')
    reason = text(closeout.get('reason'), '原协调者收尾说明', 2000)
    if task.get('intent') == 'stop' and task.get('coordinator_closeout', {}).get('disposition') == 'ended':
        # New request IDs do not create a new cancellation generation or turn
        # an explicitly ended round back into a wait. Only normal user resume
        # can restore task.intent, preserving the existing authorization path.
        return {'accepted': True, 'task_id': task['id'], 'modules': [],
                'closeout': inventory(state, task, controller.store.root, controller.report_worker_node_ids())}
    with controller.store._lock:
        summary = inventory(state, task, controller.store.root, controller.report_worker_node_ids())
        if disposition == 'ended' and not summary['in_flight']:
            # Clear only proofs from this locked snapshot; pending report jobs
            # and all results remain durable for their existing retry path.
            from .deployment_activity import published_settlement
            for row in [*summary['activity']['residuals'], *summary['activity']['reports']]:
                node = state['nodes'][row['node_id']]
                if row['code'] == 'published_marker' or (row['code'] == 'saved_report_pending'
                        and published_settlement(controller.store.root, node, state)):
                    node.pop('finalization_pending', None)
                    node.pop('native_report_pending', None)
                    node.pop('report_error', None)
    if disposition == 'ended' and summary['in_flight']:
        return {'accepted': False, 'task_id': task['id'], 'modules': [], 'closeout': summary}
    if disposition == 'ended':
        task['intent'] = 'stop'
        task['revision'] += 1
        for node in nodes:
            if not node.get('child_ids') and node['state'] == 'queued':
                node.update(state='stopped', control_intent='stop', revision=node['revision'] + 1,
                            reason=reason, scheduling_cancelled_at=now)
                if any(row['node_id'] == node['id'] and row['code'] == 'queue_wait'
                       for row in summary['activity']['waiting']):
                    binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
                    node['unclaimed_cancellation'] = {'at': now, 'node_revision': node['revision'],
                        'dispatch_id': binding.get('dispatch_id') or binding.get('id'),
                        'holder_id': binding.get('holder_id'), 'executor_ref': binding.get('executor_ref')}
                # Never fabricate finish/exit ACK or publish an unexecuted successor.
                offer = node.get('dispatch_offer')
                if offer and offer.get('state') in {'offered', 'received', 'waiting_capacity'}:
                    offer.update(state='cancelled', cancelled_at=now, reason='original_coordinator_ended')
            if node.get('child_ids') or node['state'] in TERMINAL:
                for key in ('reservation', 'native_claim_pending', 'resource_wait', 'direct_holder', 'actor_seen'):
                    node.pop(key, None)
                for control in node.get('executor_controls', {}).values():
                    if control.get('state') in {'pending', 'received'}:
                        control.update(state='obsolete', obsolete_at=now, reason='original_executor_exit_already_confirmed')
            for event in node.get('native_handoffs', {}).values():
                for notice in [event, *notices(event)]:
                    if notice.get('delivery_state') in {'pending', 'waiting_resources', 'blocked'}:
                        obsolete(notice)
        # Close pure scheduling containers without synthesizing a new report.
        for node in reversed(nodes):
            if node.get('child_ids') and all(state['nodes'][nid]['state'] in TERMINAL for nid in node['child_ids']):
                node['state'] = 'completed'
        for source in state['nodes'].values():
            if source.get('owner') != owner:
                continue
            for event in source.get('native_handoffs', {}).values():
                for notice in notices(event):
                    target_id = (notice.get('claim_arguments') or {}).get('node_id') or notice.get('node_id')
                    if target_id in {n['id'] for n in nodes} and notice.get('delivery_state') in {'pending', 'waiting_resources', 'blocked'}:
                        obsolete(notice)
                    elif any(row['code'] == 'obsolete_handoff' and row['reference_id'] == (notice.get('id') or event['id'])
                             for row in summary['activity']['residuals']):
                        obsolete(notice)
    task['coordinator_closeout'] = {'disposition': disposition, 'reason': reason, 'at': now,
        'coordinator_ref': reference, 'remaining_node_ids': [row['node_id'] for row in summary['queued']],
        'cleanup_responsibility_ids': [row['id'] for row in summary['cleanup_responsibilities']]}
    controller.audit(db, owner, 'native.coordinator_closeout', task['id'], disposition)
    return {'accepted': True, 'task_id': task['id'], 'modules': [],
            'closeout': {**summary, 'disposition': disposition}}
