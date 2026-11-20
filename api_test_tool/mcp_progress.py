"""Saved activity and read-only progress views of the current execution."""
from collections import Counter
from datetime import datetime
import time

PHASES = {
    "reading": "读取与分析文档", "designing": "设计测试用例", "reviewing": "核对测试用例",
    "executing": "执行接口测试", "reporting": "分析结果与整理报告",
    "completed": "报告已保存", "waiting": "等待补充信息", "failed": "执行异常",
}
ACTIONS = {"submit": "designing",
           "approve": "reviewing", "run": "executing", "rules": "designing", "ui_cases": "designing", "ui_asset": "executing", "ui_dependency_check": "executing",
           "start_workflow": "reading", "save_materials": "reading", "start_regression": "reading"}
ACTIONS.update(save_requirement_design='designing',
               resolve_rule_question='reviewing', resume_requirement_test='reading',
               record_checkpoint='executing', run_test_capability='executing')


def record_progress(store, owner, pid, phase, message=""):
    if not isinstance(phase, str) or phase not in PHASES:
        raise ValueError("未知执行阶段")
    if not isinstance(message, str) or len(message) > 1000:
        raise ValueError("进度说明必须是最多 1000 字的文本")
    with store._lock:
        project = store.get_project(owner, pid)
        previous = project.get("mcp_progress", {})
        if not message and previous.get("phase") == phase:
            message = previous.get("message", "")
        event = {"phase": phase, "label": PHASES[phase], "message": message, "updated_at": time.time()}
        if phase == 'executing' and project.get('test_kind') == 'ui':
            event['label'] = '执行页面测试'
        history = previous.get("history", [])
        if history and history[-1]["phase"] == phase:
            history = history[:-1]
        progress = {**event, "history": (history + [event])[-30:]}
        store.update_project(owner, pid, {"mcp_progress": progress})
        return progress


def record_case_progress(store, owner, pid, saved, prefix="", *, reporting=False):
    """Use saved outcomes, including checkpoint deltas; a sibling's design is not a reset."""
    with store._lock:
        project = store.get_project(owner, pid)
        previous = project.get('mcp_progress', {})
        if saved.get('execution_id') != project.get('ui_execution_id'):
            return previous
        if saved.get('revision', 0) < project.get('ui_execution_revision', 0):
            return previous
        counts = saved.get('execution_plan', {}).get('execution_summary', {}).get('status_counts', {})
        phase = 'executing' if any(counts.get(k, 0) for k in ('passed', 'failed', 'partial')) else previous.get('phase', 'designing')
        if phase in {'waiting', 'reading', 'completed', 'failed'}:
            phase = 'designing'
        if reporting:
            phase = 'reporting'
        return record_progress(store, owner, pid, phase, (prefix + saved['progress_message'])[:1000])


def _timestamp(value):
    if isinstance(value, (float, int)):
        return value
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0


def _progress_selection(project, snapshot, projects, task_scope=None):
    """Select actual task records and their saved successor relationships."""
    by_id = {p['id']: p for p in projects}
    project = by_id.get(project['id'], project)
    related = {project['id']}
    if task_scope:
        task = next(t for t in snapshot.get('tasks', []) if t['id'] == task_scope)
        node_ids = {n['id'] for n in snapshot.get('nodes', []) if n['task_id'] == task_scope}
        related.update(n['record_project_id'] for n in snapshot.get('nodes', [])
                       if n['id'] in node_ids and n.get('record_project_id') in by_id)
        related.update(p['id'] for p in projects if p.get('managed_node_id') in node_ids)
    def source_project(p):
        return (p.get('execution_round', {}).get('source_project_id') or
                p.get('regression_source', {}).get('project_id'))
    while True:
        if task_scope:
            # The shared session is not evidence that two task runs share a
            # module. Only this task's records and actual source successors
            # belong to its progress. A whole-session successor must also have
            # been created after this task, not an earlier use of the session.
            descendants = related - {project['id']}
            expanded = related | {p['id'] for p in projects if (
                p.get('managed_parent_project_id') in descendants or
                (source_project(p) in related and
                 (source_project(p) != project['id'] or
                  _timestamp(p.get('created_at')) >= _timestamp(task.get('created')))))}
        else:
            expanded = related | {p['id'] for p in projects if any(parent in related for parent in (
                p.get('managed_parent_project_id'),
                p.get('execution_round', {}).get('parent_project_id'),
                p.get('regression_source', {}).get('project_id')))}
        if expanded == related:
            break
        related = expanded

    def identity(p):
        seen = set()
        while p['id'] not in seen:
            seen.add(p['id'])
            source = p.get('execution_round', {}).get('source_project_id')
            if source not in by_id:
                break
            p = by_id[source]
        return 'node:' + p['managed_node_id'] if p.get('managed_node_id') else 'project:' + p['id']

    def generation(p, task):
        # Managed report projects are created lazily; their creation time is
        # not the start of a new test round.
        origin = by_id.get(p.get('managed_parent_project_id'), p)
        return (_timestamp(origin.get('created_at')), _timestamp(task.get('created')), origin['id'])

    def descends_from(p, source):
        pending, seen = [p['id']], set()
        while pending:
            pid = pending.pop()
            if pid == source:
                return True
            if pid in seen or pid not in by_id:
                continue
            seen.add(pid)
            item = by_id[pid]
            pending.extend(parent for parent in (item.get('managed_parent_project_id'),
                item.get('execution_round', {}).get('source_project_id'),
                item.get('execution_round', {}).get('parent_project_id'),
                item.get('regression_source', {}).get('project_id')) if parent)
        return False

    tasks = {}
    for task in snapshot.get('tasks', []):
        if task.get('account_project_deleted'):
            continue
        pid = task['project_id']
        if task_scope and task['id'] != task_scope and pid not in related - {project['id']}:
            continue
        if pid not in tasks or task.get('created', 0) > tasks[pid].get('created', 0):
            tasks[pid] = task
    task_ids = {t['id']: t for t in tasks.values()}
    report_projects = {p['managed_node_id']: p for p in projects if p.get('managed_node_id')}
    candidates, represented, scheduled = {}, set(), set()
    current_nodes = {n['id']: n for n in snapshot.get('nodes', [])}
    for node in snapshot.get('nodes', []):
        task = task_ids.get(node['task_id'])
        successor = current_nodes.get(node.get('record_successor_node_id'), {})
        if not task or node.get('child_ids') or successor.get('task_id') == node['task_id']:
            continue
        p = by_id.get(node.get('record_project_id')) or report_projects.get(node['id']) or by_id.get(task['project_id'])
        if not p or (p['id'] not in related and task['project_id'] not in related):
            continue
        key = identity(p)
        if p['id'] == task['project_id'] and len(task.get('node_ids', [])) > 1:
            key = 'node:' + node['id']
        candidates.setdefault(key, []).append((generation(p, task), p, node, task))
        represented.add(p['id'])
        scheduled.add(task['project_id'])
    for p in projects:
        if p['id'] not in related or p['id'] in represented or p['id'] in scheduled:
            continue
        if task_scope and p['id'] == project['id']:
            continue
        if p.get('execution_round', {}).get('kind') or (p['id'] == project['id'] and not candidates):
            candidates.setdefault(identity(p), []).append((generation(p, {}), p, {}, {}))
    rounds = [p for p in projects if p['id'] in related and p.get('execution_round', {}).get('source_project_id')]
    selected = []
    for items in candidates.values():
        current = [item for item in items if not any(
            item[0][0] < _timestamp(round_project.get('created_at')) and
            descends_from(item[1], round_project['execution_round']['source_project_id'])
            for round_project in rounds)]
        if current:
            selected.append(max(current, key=lambda item: item[0]))
    return selected


def project_progress(store, owner, project, snapshot, projects, record_cache=None, *, task_scope=None,
                     include_related_history=True):
    """Project scheduler/record facts without mutating progress on a read.

    A module's later round wins by its saved source relationship and creation
    order, never by the time an old worker last read or published something.
    """
    record_cache = {} if record_cache is None else record_cache
    selected = _progress_selection(project, snapshot, projects, task_scope)
    historical = []
    if task_scope and include_related_history:
        current = {(p['id'], node.get('id')) for _, p, node, _ in selected}
        historical = [item for item in _progress_selection(project, snapshot, projects)
                      if (item[1]['id'], item[2].get('id')) not in current]
    live_round = any(node.get('state') in {'queued', 'starting', 'running', 'stopping', 'paused', 'blocked', 'stopped',
                                         'retained', 'isolated', 'waiting_human'} or
                     (p.get('ui_progress_record', {}).get('execution_id') == p.get('ui_execution_id') and p.get('ui_execution_id'))
                     for _, p, node, _ in selected)
    leases = {lease['node_id']: lease for lease in snapshot.get('leases', [])}
    units, history_units = [], []
    for index, (_, p, node, task) in enumerate(selected + historical):
        is_history = index >= len(selected)
        # Match report_project's normal single-session record reuse. Snapshot
        # omits baseline bodies, but retains their source_task_id.
        session_record = (len(task.get('node_ids', [])) == 1 and
                          task.get('session_workflow', True) and not task.get('source_task_id') and
                          not node.get('parent_id') and node.get('id') in task.get('node_ids', []))
        owns_record = (not node or node.get('record_project_id') == p['id'] or
                       p.get('managed_node_id') == node.get('id') or session_record)
        saved = (p.get('mcp_progress') or {}) if owns_record else {}
        eid = p.get('ui_execution_id') if owns_record else None
        record = (p.get('ui_progress_record') or {}) if owns_record else {}
        if eid and (record.get('execution_id') != eid or record.get('revision') != p.get('ui_execution_revision')):
            record = {}
        key = (p['id'], eid, p.get('ui_execution_revision'))
        if eid and not record and ((live_round and not is_history) or key in record_cache):
            # Existing rounds predate the compact record summary. Read their
            # current saved record, without rewriting it or restarting work.
            from . import ui_records
            if key not in record_cache:
                try:
                    current = ui_records.load(store, owner, p['id'], eid)
                    record_cache[key] = {'execution_id': eid, 'revision': current['revision'],
                        'counts': dict(Counter(c.get('status', 'not_run') for c in ui_records.active_cases(current['cases']))),
                        'saved_at': max((c.get('updated_at', '') for c in current['cases']), default=''),
                        'report_id': current.get('report_id')}
                except FileNotFoundError:
                    record_cache[key] = {}
            record = record_cache[key]
        counts = record.get('counts', {})
        lease = leases.get(node.get('id'))
        state = node.get('state')
        finish = p.get('ui_finish_request') or {}
        finishing = (finish.get('execution_id') == eid and eid and
                     finish.get('revision') == p.get('ui_execution_revision'))
        report = (p.get('last_analysis') or {}) if owns_record else {}
        final_result = finish.get('result') or {}
        finalized_report = (finishing and final_result.get('phase') == 'published' and
                            final_result.get('execution_id') == eid and
                            final_result.get('revision') == p.get('ui_execution_revision') and
                            report.get('id') and
                            (final_result.get('report') or {}).get('id') == report['id'])
        published = bool(finalized_report or
                         (record.get('report_id') and record['report_id'] == report.get('id')) or
                         (not record and report and _timestamp(report.get('created_at')) >= _timestamp(saved.get('updated_at'))))
        phase, label = saved.get('phase', 'waiting'), saved.get('label', '等待执行者接手')
        message = node.get('reason') or saved.get('message', '')
        if finishing and finish.get('error'):
            phase, label, message = 'failed', '报告生成失败', finish['error']
        elif (finishing and not finish.get('result')) or state == 'stopping' or (lease and lease.get('revoked')):
            phase, label = 'settling', '正在收尾与交还资源'
        elif node.get('native_report_pending') and not lease and not published:
            phase, label, message = 'awaiting_report', '执行已结束，报告未发布', '账号已交还；没有报告正在生成，可沿原记录补充并发布，不重跑业务。'
        elif state in {'blocked', 'isolated', 'waiting_human', 'retained'}:
            phase, label = 'blocked', {'blocked': '执行受阻', 'isolated': '现场待核实',
                                      'waiting_human': '等待人工处理', 'retained': '现场保留待处理'}[state]
        elif state in {'paused', 'stopped'}:
            phase, label = state, '已暂停' if state == 'paused' else '已停止'
        elif state == 'queued':
            dispatch = node.get('dispatch_state', '')
            phase = 'waiting'
            label = ('资源可用，等待原会话接续' if node.get('resource_wait', {}).get('resources_available')
                     else '等待执行者' if dispatch in {'awaiting_executor', 'waiting_executor_capacity',
                                                      'awaiting_executor_ack', 'dispatch_expired'}
                     else '等待账号或执行资源')
        elif state in {'running', 'starting'}:
            if node.get('business_started_at') or any(counts.get(k, 0) for k in ('passed', 'failed', 'partial')):
                phase, label = 'executing', '执行页面测试'
            elif lease and lease.get('mode') == 'shared':
                phase, label = 'designing', '探索页面与设计用例'
            else:
                phase, label = 'preparing', '账号已分配，准备测试' if lease else '正在启动执行'
        elif published:
            phase, label = 'completed', '报告已保存'
        elif state == 'completed' and task.get('execution_route') == 'native_browser' and not node.get('finalization_pending'):
            phase, label = 'awaiting_report', '执行已结束，报告未发布'
        elif state == 'completed':
            phase, label = 'reporting', '执行已结束，等待报告'
        elif eid and counts:
            phase = 'executing' if any(counts.get(k, 0) for k in ('passed', 'failed', 'partial')) else 'designing'
            label = PHASES[phase] if phase != 'executing' else '执行页面测试'
        updated = max(_timestamp(saved.get('updated_at')) if not node else 0, _timestamp(record.get('saved_at')),
                      _timestamp(node.get('native_last_case_saved_at')), _timestamp(node.get('actor_seen')),
                      _timestamp(node.get('last_case_saved_at')),
                      _timestamp(lease.get('progress_at')) if lease else 0,
                      _timestamp(task.get('created')), _timestamp(finish.get('requested_at')))
        # Report corrections affect the displayed result, not executor state or
        # last-save times. Share this read within a response, never across polls.
        from .ui_report_corrections import progress_record
        correction_key = ('corrections', *key, record.get('report_id'))
        if correction_key not in record_cache:
            record_cache[correction_key] = progress_record(store, owner, p['id'], record)
        effective_record = record_cache[correction_key]
        (history_units if is_history else units).append({'project_id': p['id'], 'task_id': task.get('id'), 'node_id': node.get('id'),
                      'title': node.get('title') or p['title'], 'phase': phase, 'label': label,
                      'message': message, 'updated_at': updated, 'execution_id': eid,
                      'active': (phase in {'executing', 'designing', 'preparing', 'settling', 'reporting'} and
                                 (state in {'running', 'starting', 'stopping'} or bool(finishing and not finish.get('result')) or
                                  (not node and time.time() - updated < 120))),
                      'revision': record.get('revision'), 'case_counts': effective_record.get('counts', {}),
                      'correction_revision': effective_record.get('correction_revision', 0),
                      'case_counts_complete': not eid or bool(record),
                      'last_case_saved_at': _timestamp(record.get('saved_at')) or None,
                      'report_url': (f"/api/projects/{p['id']}/reports/{report['id']}/index.html"
                                     if published and report.get('id') else
                                     f"/api/ui-tests/{p['id']}/executions/{eid}/cases.html" if eid else
                                     f"/ui-testing?project={p['id']}"),
                      'report_saved': published, 'coverage_complete': node.get('coverage_complete') is True})
    progress = _summarize_progress(project if units or not task_scope else {}, units)
    if not progress and task_scope:
        task = next(t for t in snapshot.get('tasks', []) if t['id'] == task_scope)
        progress = {'source': 'execution_records', 'phase': 'waiting', 'label': '等待模块记录',
                    'message': '当前任务尚无可显示的执行模块记录', 'updated_at': _timestamp(task.get('created')),
                    'active': False, 'modules': [], 'case_counts': {}, 'case_counts_complete': False,
                    'last_case_saved_at': None}
    if progress and task_scope:
        progress = {**progress, 'scope': {'kind': 'task', 'task_id': task_scope},
                    'message': '本轮任务：' + progress['message']}
        if history_units:
            progress['related_history'] = {
                **_summarize_progress({}, history_units), 'scope': {'kind': 'related_history'},
                'label': '其他关联轮次（不计入本轮）'}
            if not progress['related_history']['case_counts_complete']:
                progress['related_history']['message'] += '；未载入的历史用例计数请查看原记录。'
    return progress


def _summarize_progress(project, units):
    if not units:
        return project.get('mcp_progress')
    # Active modules remain visible beside blocked/finished siblings. Reporting
    # alone never claims all coverage passed.
    priority = ['executing', 'designing', 'preparing', 'settling', 'blocked', 'failed',
                'waiting', 'paused', 'stopped', 'reporting', 'reading', 'reviewing', 'awaiting_report', 'completed']
    current = min(units, key=lambda unit: priority.index(unit['phase']) if unit['phase'] in priority else len(priority))
    counts = dict(sum((Counter(unit['case_counts']) for unit in units), Counter()))
    counts_complete = all(unit['case_counts_complete'] for unit in units)
    message = current['message']
    if len(units) > 1:
        labels = Counter(unit['label'] for unit in units)
        message = '；'.join(f'{label} {count} 个模块' for label, count in labels.items())
    if counts:
        from .ui_records import LABELS
        message = (message + ('；' if message else '') +
                   f"{'已保存' if counts_complete else '已载入部分'} {sum(counts.values())} 条用例：" +
                   '、'.join(f'{LABELS.get(status,status)} {count}' for status,count in counts.items() if count) +
                   '；报告保存不代表覆盖通过。')
    saved = {key: value for key, value in (project.get('mcp_progress') or {}).items()
             if key not in {'scope', 'related_history'}}
    return {**saved, 'phase': current['phase'], 'label': current['label'],
            'message': message, 'updated_at': max(unit['updated_at'] for unit in units),
            'source': 'execution_records', 'active': any(unit['active'] for unit in units),
            'modules': units, 'case_counts': counts,
            'case_counts_complete': counts_complete,
            'last_case_saved_at': max((unit['last_case_saved_at'] or 0 for unit in units), default=0) or None}
