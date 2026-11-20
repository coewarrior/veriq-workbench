"""Retire superseded task members while preserving their historical evidence."""
from .orchestration import Conflict, strings
from .orchestration_storage import select_records


def current_task_nodes(nodes, tasks):
    """Use the retained member order only for explicitly archived task trees."""
    archived = {t['id']: t for t in tasks if t.get('archived_node_ids')}
    by_id = {n['id']: n for n in nodes}
    result, seen = [], set()
    for node in nodes:
        task_id = node['task_id']
        if task_id not in archived:
            result.append(node)
        elif task_id not in seen:
            seen.add(task_id)
            result.extend(by_id[nid] for nid in archived[task_id]['node_ids']
                          if nid in by_id and by_id[nid]['task_id'] == task_id
                          and not by_id[nid].get('module_archive'))
    return result


def archive(controller, db, state, owner, task_id, data):
    task = controller.owned(state['tasks'], owner, task_id)
    if task['intent'] != 'stop' or data.get('revision') != task['revision']:
        raise Conflict('仅可整理已结束轮次，且须使用当前任务版本；不停止或修改活动轮次')
    selected = strings(data.get('node_ids'), 'node_ids', 100)
    if not selected or len(set(selected)) != len(selected):
        raise ValueError('请明确指定无重复的旧节点 ID')
    replacements = {}
    affected = set()
    for node_id in selected:
        source = controller.owned(state['nodes'], owner, node_id)
        successor = controller.owned(state['nodes'], owner, source.get('record_successor_node_id'))
        if (node_id not in task['node_ids'] or successor['id'] not in task['node_ids']
                or successor['id'] in selected or source['task_id'] != task_id or successor['task_id'] != task_id
                or successor.get('record_successor_node_id') or source.get('module_archive')
                or source.get('child_ids') or successor.get('child_ids')
                or not source.get('parent_id') or source.get('parent_id') != successor.get('parent_id')
                or any(not source.get(k) or source[k] != successor.get(k)
                       for k in ('record_project_id', 'record_execution_id'))
                or successor.get('continuation_source') != {
                    'source_task_id': task_id, 'source_node_id': node_id,
                    'project_id': source.get('record_project_id'), 'execution_id': source.get('record_execution_id')}):
            raise Conflict('只能归档同轮、同记录、已被明确后继替代的旧叶子节点')
        for node in (source, successor):
            binding = node.get('executor_dispatch') or {}
            if (node['state'] != 'completed' or node.get('native_browser_stopped') is not True
                    or not binding.get('exit_acknowledged_at')
                    or any(node.get(k) for k in ('direct_holder', 'native_claim_pending',
                        'finalization_pending', 'native_report_pending', 'report_error'))
                    or any(c.get('state') in {'pending', 'received'}
                           for c in node.get('executor_controls', {}).values())):
                raise Conflict('相关节点尚未完成实际退出或收尾；不改动当前会话')
        parent = controller.owned(state['nodes'], owner, source['parent_id'])
        if (parent['task_id'] != task_id or parent['id'] not in task['node_ids']
                or not {node_id, successor['id']}.issubset(parent.get('child_ids', []))):
            raise Conflict('原父子关系已变化，请重新核对')
        replacements[node_id] = successor['id']
        affected.update((node_id, successor['id'], parent['id']))
    if (any(l['node_id'] in task['node_ids'] for l in state['leases'].values())
            or set(controller.report_worker_node_ids()).intersection(task['node_ids'])):
        raise Conflict('本轮仍有账号租约或实际报告处理，完成后再整理')
    lease_ids = {a['lease_id'] for nid in affected for a in state['nodes'][nid].get('attempts', [])}
    if any((receipt.get('node_id') in affected or lid in lease_ids)
           and receipt.get('ack_required') is not False and not receipt.get('local_ack_at')
           for lid, receipt in state.get('direct_settlements', {}).items()):
        raise Conflict('相关交还回执尚未确认，不能整理节点')
    for kind, pending in (('operations', ('pending', 'unknown')),
                          ('direct_commands', ('queued', 'running', 'unknown'))):
        if any(row.get('node_id') in affected or row.get('lease_id') in lease_ids
               for row in select_records(state.get(kind, {}), state=pending)):
            raise Conflict('相关历史仍有未确认操作，不能整理节点')
    for nid in affected:
        for event in state['nodes'][nid].get('native_handoffs', {}).values():
            notices = event.get('continuations') or ([event['continuation']] if event.get('continuation') else [])
            if any(n.get('delivery_state') in {'sending', 'unknown'} for n in [event, *notices]):
                raise Conflict('相关交接发送尚未确认，不能整理节点')

    def current_members(ids):
        return list(dict.fromkeys(replacements.get(nid, nid) for nid in ids))

    now = controller.clock()
    parents = {state['nodes'][nid]['parent_id'] for nid in selected}
    for parent_id in parents:
        parent = state['nodes'][parent_id]
        parent['child_ids'] = current_members(parent['child_ids'])
        parent['revision'] += 1
    for nid, successor_id in replacements.items():
        node = state['nodes'][nid]
        node['module_archive'] = {'at': now, 'successor_node_id': successor_id,
            'parent_id': node.pop('parent_id'), 'reason': '已结束轮次的重复前驱节点移出任务'}
        node['revision'] += 1
    task['node_ids'] = current_members(task['node_ids'])
    task.setdefault('archived_node_ids', []).extend(selected)
    task['revision'] += 1
    controller.audit(db, owner, 'modules.archived', task_id, ','.join(selected))
    return {'task_id': task_id, 'revision': task['revision'], 'archived_node_ids': selected,
            'kept_node_ids': list(replacements.values()), 'results_preserved': True}
