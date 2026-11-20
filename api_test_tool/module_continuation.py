"""Bind a session continuation to its original records, without a new baseline."""
from .orchestration import Conflict


def dependencies_completed(state, node):
    for dependency_id in node.get('depends_on', []):
        dependency, seen = state['nodes'][dependency_id], set()
        while dependency.get('record_successor_node_id'):
            successor = state['nodes'].get(dependency['record_successor_node_id'])
            if not successor or successor['task_id'] != node['task_id']:
                break
            if dependency['id'] in seen:
                return False
            seen.add(dependency['id'])
            dependency = successor
        if dependency['state'] != 'completed':
            return False
    return True


def candidates(state, task):
    """The latest earlier module tree, never another owner's/project's history."""
    sources = []
    for prior in state['tasks'].values():
        if (prior['id'] == task['id'] or prior['owner'] != task['owner']
                or prior['project_id'] != task['project_id']
                or prior.get('created', 0) > task.get('created', 0)):
            continue
        leaves = [state['nodes'][nid] for nid in prior['node_ids']
                  if not state['nodes'][nid].get('child_ids')
                  and state['nodes'][nid].get('record_successor_node_id') not in prior['node_ids']]
        if any(n.get('record_project_id') and n.get('record_execution_id') for n in leaves):
            sources.append((prior, leaves))
    if not sources:
        return []
    prior, leaves = max(sources, key=lambda item: (item[0].get('created', 0), item[0]['id']))
    return [{'source_node_id': n['id'], 'source_task_id': prior['id'],
             'key': n.get('plan_key', n['key']), 'title': n['title'], 'state': n['state'],
             'project_id': n.get('record_project_id'), 'execution_id': n.get('record_execution_id')}
            for n in leaves]


def resolve(controller, state, owner, task, modules):
    """Validate the complete mapping before the placeholder tree is changed."""
    options = candidates(state, task)
    by_id = {item['source_node_id']: item for item in options}
    chosen, records = [], set()
    for module in modules:
        source_id = module.get('source_node_id')
        if source_id is not None and not isinstance(source_id, str):
            raise ValueError('source_node_id 必须是原模块节点 ID')
        matches = [item for item in options if item['key'] == module.get('key')]
        source = by_id.get(source_id) if source_id else matches[0] if len(matches) == 1 else None
        if not source:
            raise Conflict('已有用例基线保留原归属；请读取 continuation_modules，'
                           '用原 source_node_id 登记续测模块，不能用新的初始模块计划覆盖已有轮次')
        node = controller.owned(state['nodes'], owner, source['source_node_id'])
        prior = controller.owned(state['tasks'], owner, source['source_task_id'])
        if (prior['intent'] != 'run' or prior.get('account_project_deleted')
                or node.get('control_intent', 'run') != 'run'
                or node['state'] != 'completed' or node.get('record_successor_node_id')
                or node.get('native_report_pending') or node.get('finalization_pending')
                or any(l['node_id'] == node['id'] for l in state['leases'].values())
                or any(control.get('state') not in {'exited', 'obsolete'}
                       for control in node.get('executor_controls', {}).values())):
            raise Conflict('原模块尚未完成退出/报告收尾、已停止或已有续接；沿原模块处理，不能创建竞争执行者')
        controller.sessions.assert_available(state, prior, [node['id']])
        pid, eid = source['project_id'], source['execution_id']
        if not pid or not eid or (pid, eid) in records:
            raise Conflict('续测模块必须分别绑定真实原记录，不能重复分配同一执行记录')
        project = controller.store.get_project(owner, pid)
        if (project.get('ui_execution_id') != eid
                or (pid != task['project_id'] and project.get('managed_parent_project_id') != task['project_id'])
                or not (controller.store.project_dir(owner, pid) / 'ui-executions' / eid / 'cases.json').is_file()):
            raise Conflict('原模块执行记录或父会话绑定已变化；保留历史，不能猜测续测来源')
        # No second live node may write the same record, including a successor
        # already prepared by another request before this transaction began.
        if any(other['id'] != node['id'] and other['task_id'] != task['id'] and other.get('record_project_id') == pid
               and other.get('record_execution_id') == eid
               and other['state'] not in {'completed', 'container'}
               for other in state['nodes'].values()):
            raise Conflict('原执行记录已有其他未结束模块绑定，不能并行覆盖同一记录')
        records.add((pid, eid))
        chosen.append(source)
    return chosen


def bind(state, task, child_ids, sources):
    for child_id, source in zip(child_ids, sources):
        child = state['nodes'][child_id]
        child['continuation_source'] = {
            key: source[key] for key in ('source_task_id', 'source_node_id', 'project_id', 'execution_id')}
        child.update(record_project_id=source['project_id'], record_execution_id=source['execution_id'])
        original = state['nodes'][source['source_node_id']]
        failed = set(original.get('continuation_failed_case_ids', []))
        failed.update(case['case_id'] for entry in original.get('case_history', {}).values()
                      for case in entry.get('cases', []) if case.get('status') == 'failed')
        child['continuation_failed_case_ids'] = sorted(failed)
        # Fence only the old execution authority. Its state, outcome, original
        # record ownership and historical report lookup remain unchanged.
        original['record_successor_node_id'] = child_id
    task['record_continuation'] = True


def report_project(store, owner, node, task):
    source = node['continuation_source']
    project = store.get_project(owner, source['project_id'])
    if (node.get('record_project_id') != project['id']
            or node.get('record_execution_id') != source['execution_id']
            or project.get('ui_execution_id') != source['execution_id']
            or (project['id'] != task['project_id']
                and project.get('managed_parent_project_id') != task['project_id'])):
        raise Conflict('续测记录绑定已变化；保留原观察，不能写入另一执行轮次')
    # Use the current authorized goal in the context, without rewriting the
    # original module project's metadata or completed case/checkpoint facts.
    return {**project, 'task': {**project.get('task', {}),
            'goal': task['goal'] + '\n当前模块：' + node['scope']}}
