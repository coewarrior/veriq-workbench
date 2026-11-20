"""Reconcile session storage with the existing execution/return protocol.

Deletion revokes authority; it never invents browser exit or a safe account.
Restoring files does not resume a task. History remains available for settlement.
"""
from .orchestration import Conflict
from .orchestration_storage import read_metadata_without_history

TERMINAL = {'completed', 'blocked', 'stopped'}


class SessionLifecycle:
    def __init__(self, controller):
        self.c = controller
        self.store = controller.store

    def available(self, owner, pid):
        try:
            self.store.get_project(owner, pid)
            return True
        except FileNotFoundError:
            return False

    def assert_available(self, state, task, selected=None):
        if not self.available(task['owner'], task['project_id']):
            raise Conflict('会话已删除；请先恢复原会话，再明确继续，不能通过重连恢复执行')
        for nid in selected if isinstance(selected, list) else task['node_ids']:
            node = state['nodes'].get(nid, {})
            pid = node.get('record_project_id')
            if pid and not self.available(task['owner'], pid):
                raise Conflict('模块会话已删除；请恢复该模块或只继续其他模块')

    def reconcile(self, db, state):
        """Also repairs old trash/orphans and crashes between file/DB commits."""
        leased = {l['node_id'] for l in state['leases'].values()}
        for node in state['nodes'].values():
            if node['state'] in TERMINAL and node['id'] not in leased:
                node['reservation'] = None
                node.pop('resource_wait', None)
                node.pop('direct_holder', None)
                node.pop('actor_seen', None)
        for lease in state['leases'].values():
            node = state['nodes'][lease['node_id']]
            if lease.get('resource_hold') and lease.get('executor_stopped') and node['state'] == 'stopping':
                node.update(state='isolated' if lease.get('hold', {}).get('pending_operation_ids') else 'retained',
                            reason=lease.get('hold', {}).get('reason', '资源待核实'))
        settle_containers(state)
        availability = {}
        def available(owner, pid):
            key = owner, pid
            if key not in availability:
                availability[key] = self.available(owner, pid)
            return availability[key]
        for task in state['tasks'].values():
            root_missing = not available(task['owner'], task['project_id'])
            removed = []
            for nid in task['node_ids']:
                node = state['nodes'][nid]
                pid = node.get('record_project_id')
                if root_missing or (pid and not available(task['owner'], pid)):
                    if not node.get('session_removed'):
                        removed.append(nid)
                elif node.pop('session_removed', None):
                    # The stop intent survives restoration; only report work may resume.
                    if node.pop('report_deferred_deleted', None):
                        node['finalization_pending'] = True
            if not removed:
                continue
            data = {'revision': task['revision']}
            if not root_missing:
                data['node_ids'] = removed
            self.c._control(db, state, task['owner'], task['id'], data, 'stop')
            for nid in removed:
                node = state['nodes'][nid]
                node['session_removed'] = True
                # Deleting the session withdraws its window-retention request,
                # not explicit business conditions or unresolved operations.
                node.get('checkpoint', {}).pop('retain_browser', None)
                node.get('checkpoint', {}).pop('retain_scene', None)
                node['reservation'] = None
                node.pop('resource_wait', None)
                node['reason'] = '会话已删除；停止执行并回收资源，原结果与待核实事项保留'
                for lease in state['leases'].values():
                    if lease['node_id'] == nid and lease.get('resource_hold'):
                        # Do not turn a settled, unresolved account into an active worker.
                        node['state'] = 'isolated' if lease.get('hold', {}).get('pending_operation_ids') else 'retained'
                        lease['close_browser_requested'] = True
            self.c.audit(db, task['owner'], 'session.execution_stopped', task['id'])

    def recycle(self, owner, pid, *, restore=False):
        # DB then Store is the same lock order as scheduling and record creation.
        with self.c.transaction() as (db, state):
            project = self.store.recycle_project(owner, pid, restore=restore)
            self.reconcile(db, state)
            nodes = [n for n in state['nodes'].values() if n['owner'] == owner and
                     (n['project_id'] == pid or n.get('record_project_id') == pid)]
            nids = {n['id'] for n in nodes}
            leases = [l for l in state['leases'].values() if l['node_id'] in nids]
            from .native_state import desktop_stop_view
            return project, {'stopping': sum(not l.get('executor_stopped') for l in leases),
                             'resource_holds': sum(bool(l.get('resource_hold')) for l in leases),
                             'desktop_stop': desktop_stop_view(state, owner=owner, node_ids=nids),
                             'resumed': False}

    def trash(self, owner):
        projects = self.store.list_projects(owner, deleted=True)
        with self.c.connect() as db:
            db.execute('BEGIN')
            state = read_metadata_without_history(db)
        for project in projects:
            nodes = {n['id']: n for n in state['nodes'].values() if n['owner'] == owner and
                     (n['project_id'] == project['id'] or n.get('record_project_id') == project['id'])}
            leases = [l for l in state['leases'].values() if l['node_id'] in nodes]
            from .native_state import desktop_stop_view
            project['cleanup'] = {
                'stopping': sum(not l.get('executor_stopped') for l in leases),
                'resource_holds': sum(bool(l.get('resource_hold')) for l in leases),
                'desktop_stop': desktop_stop_view(state, owner=owner, node_ids=set(nodes)),
                'reasons': list(dict.fromkeys(l.get('hold', {}).get('reason') or
                                             nodes[l['node_id']]['reason'] for l in leases))}
        return projects

    def purge(self, owner, ids):
        with self.c.transaction() as (db, state):
            self.reconcile(db, state)
            if isinstance(ids, list):
                nodes = {n['id'] for n in state['nodes'].values() if n['owner'] == owner and
                         (n['project_id'] in ids or n.get('record_project_id') in ids)}
                if any(l['node_id'] in nodes for l in state['leases'].values()):
                    raise Conflict('会话正在回收资源或有待核实现场；暂不能彻底删除证据。可恢复会话查看具体占用并核实')
                if any(o['node_id'] in nodes and o['state'] in {'pending', 'unknown'}
                       and not o.get('historical') for o in state['operations'].values()):
                    raise Conflict('会话仍有待核实操作，不能彻底删除原始证据')
                if any(obj['source_node_id'] in nodes and
                       (obj['state'] in {'creating', 'cleaning', 'unknown'} or obj.get('retain_scene'))
                       for obj in state.get('cleanup_objects', {}).values()):
                    raise Conflict('原对象操作或现场仍待核实，不能彻底删除证据')
            return self.store.purge_projects(owner, ids)


def active_nodes(state, nodes):
    leased = {l['node_id'] for l in state['leases'].values()}
    return [n for n in nodes if not n.get('child_ids') and
            (n['id'] in leased or n['state'] not in TERMINAL)]


def legacy_progress_active(state, project):
    # Managed tasks are authoritative; old UI "executing" is not a resource lock.
    managed = (any(t['project_id'] == project['id'] for t in state['tasks'].values()) or
               any(n.get('record_project_id') == project['id'] for n in state['nodes'].values()))
    return not managed and (project.get('mcp_progress') or {}).get('phase') in {'executing', 'reporting'}


def settle_containers(state):
    # Aggregate completion means execution ended, never that assertions passed.
    changed = True
    while changed:
        changed = False
        for node in state['nodes'].values():
            if node['state'] == 'container' and node.get('child_ids') and all(
                    state['nodes'][nid]['state'] in TERMINAL for nid in node['child_ids']):
                node.update(state='completed', finalization_pending=True)
                changed = True
