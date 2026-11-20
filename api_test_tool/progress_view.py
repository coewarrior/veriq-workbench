"""Read-only display data, independent of execution and its write transactions."""
from .mcp_progress import _progress_selection, project_progress
from .module_dispatch import node_dispatch
from .native_state import desktop_stop_view
from .orchestration_storage import read_metadata_without_history


def report_projects(projects):
    """Keep the existing session report projection without loading case bodies."""
    by_id = {p['id']: dict(p) for p in projects}
    hidden = {p['id'] for p in projects if p.get('managed_parent_project_id')}
    for child in projects:
        source = child.get('regression_source') or {'project_id': child.get('managed_parent_project_id')}
        parent = by_id.get(source.get('project_id'))
        if (child.get('test_kind') != 'ui' or not parent
                or parent.get('test_kind') != 'ui' or child['id'] == parent['id']):
            continue
        if not child.get('execution_round'):
            hidden.add(child['id'])
        reports = list(parent.get('analysis_reports', []))
        known = {(entry.get('report_url'), entry.get('id')) for entry in reports}
        for entry in child.get('analysis_reports', []):
            if (entry.get('report_url'), entry.get('id')) not in known:
                reports.append(dict(entry))
        reports.sort(key=lambda entry: entry.get('created_at', ''), reverse=True)
        parent['analysis_reports'] = reports[:30]
        if reports:
            parent['last_analysis'] = reports[0]
        parent['updated_at'] = max(parent.get('updated_at', ''), child.get('updated_at', ''))
        parent['legacy_regression_sessions'] = parent.get('legacy_regression_sessions', 0) + 1
    return by_id, hidden


def details_version(store, owner, project_id):
    """Cheap invalidation for rule/capability changes without a case revision."""
    root = store.project_dir(owner, project_id)
    versions = []
    for name in ('requirement-design', 'test-capabilities'):
        try:
            stat = (root / store._asset_name(name)).stat()
            versions.append(f'{stat.st_mtime_ns}:{stat.st_size}:{stat.st_ino}')
        except FileNotFoundError:
            versions.append(None)
    return versions


def current_progress(workflow, owner, project):
    store, controller = workflow.store, workflow.controller
    # Metadata contains the saved source links needed to select the original
    # round and its successors. Never build progress for unrelated sessions.
    projects = store.list_projects(owner)
    with controller.connect() as db:
        state = read_metadata_without_history(db)
    tasks = [t for t in state['tasks'].values() if t['owner'] == owner]
    tids = {t['id'] for t in tasks}
    nodes = [n for n in state['nodes'].values() if n['task_id'] in tids]
    nids = {n['id'] for n in nodes}
    leases = [l for l in state['leases'].values() if l['node_id'] in nids]
    candidates = [t for t in tasks if t['project_id'] == project['id']]
    current = max((t for t in candidates if not t.get('account_project_deleted')),
                  key=lambda t: t.get('created', 0), default=None)
    snapshot = {'tasks': tasks, 'nodes': nodes, 'leases': leases}
    scope = current['id'] if current else None
    selected = _progress_selection(project, snapshot, projects, scope)
    # Only selected records need dispatch labels. Historical node journals and
    # pending browser operations are not part of a progress read.
    dispatches = {}
    for _, _, node, _ in selected:
        if node:
            dispatches[node['id']] = node_dispatch(node)
            node.update(dispatches[node['id']])
    progress = project_progress(store, owner, project, snapshot, projects,
                                task_scope=scope, include_related_history=False)
    visible = current or max(candidates, key=lambda t: t.get('created', 0), default=None)
    visible_nodes = [n for n in nodes if visible and n['task_id'] == visible['id']]
    from .module_archive import current_task_nodes
    visible_nodes = current_task_nodes(visible_nodes, [visible] if visible else [])
    module_fields = ('id', 'task_id', 'title', 'state', 'reason', 'child_ids', 'resource_wait',
                     'record_successor_node_id', 'requested_account_ids')
    modules = []
    for node in visible_nodes:
        dispatch = dispatches.get(node['id'])
        if dispatch is None:
            dispatch = node_dispatch(node)
        item = {k: node[k] for k in module_fields if k in node}
        receipt = dispatch.get('executor')
        item['executor'] = {'executor_ref': receipt.get('executor_ref')} if receipt else None
        item['executor_exit_confirmed'] = dispatch['executor_exit_confirmed']
        handoff = dispatch.get('native_handoff')
        if handoff:
            item['native_handoff'] = {
                'delivery_state': handoff.get('delivery_state'),
                'coordinator_ref': handoff.get('coordinator_ref'),
                'direct_dispatch': {'state': (handoff.get('direct_dispatch') or {}).get('state')},
                'continuations': [{'delivery_state': value.get('delivery_state')}
                                  for value in handoff.get('continuations', [])]}
        modules.append(item)
    task_fields = ('id', 'revision', 'goal', 'created', 'execution_route', 'account_project_deleted')
    task = {k: visible[k] for k in task_fields if k in visible} if visible else None
    if task and task.get('execution_route') == 'native_browser':
        task['desktop_stop'] = desktop_stop_view(state, owner=owner, task_id=task['id'])
    # Binding resolution is a pure read here, not AccountProjects.binding's
    # transaction. No scheduler reconciliation or account grant on page reads.
    lineage = controller.account_projects.lineage(owner, project['id'])
    aid = controller.account_projects.resolve(owner, lineage, state)
    account_project = state.get('account_projects', {}).get(aid)
    ready = any(r['owner'] == owner and r['enabled'] and r['enforcement_verified']
                and controller.clock() - r['heartbeat'] <= 60 for r in state['runners'].values())
    metadata, hidden = report_projects(projects)
    display = metadata.get(project['id'], project) if project['id'] not in hidden else project
    fields = ('id', 'title', 'status', 'updated_at', 'last_job', 'last_analysis', 'analysis_reports',
              'ui_execution_id', 'ui_execution_revision')
    patch = {key: display.get(key) for key in fields}
    patch['mcp_progress'] = progress
    patch['ui_details_version'] = details_version(store, owner, project['id'])
    return {'project': patch, 'managed': {
        'tasks': [task] if task else [], 'nodes': modules, 'progress': progress,
        'leases': [{k: l[k] for k in ('id', 'node_id', 'account_ids')} for l in leases
                   if l['node_id'] in {n['id'] for n in visible_nodes}],
        'account_project': {'id': aid, 'name': account_project['name']} if account_project else None,
        'execution_mode': (visible or {}).get('execution_route', project.get('execution_route', 'native_browser')),
        'execution_ready': ready}}
