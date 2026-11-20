"""Evidence-only cleanup control on the existing original-module lease."""
import copy

from .orchestration import Conflict
from .cleanup_contract import CleanupScopeError, validate_cleanup_events


def call(native, owner, args):
    from . import ui_records
    from .cleanup_capabilities import apply
    events = validate_cleanup_events(args.get('arguments', {}))
    observational = all(e.get('command') in {'complete_cleanup', 'reconcile', 'residual', 'retain'} for e in events)
    with native.c.transaction() as (_, state):
        ended = state.get('direct_settlements', {}).get(args.get('lease_id'))
        if ended and observational:
            report = ended.get('report_binding') or {}
            node, task, _ = native.released_report_scope(state, owner,
                {**args, 'record_action': 'record', 'arguments': {
                    'project_id': report.get('project_id'), 'execution_id': report.get('execution_id')}}, ended)
            lease = {'id': args['lease_id'], 'node_id': node['id'], 'native_browser': True,
                     'account_ids': node.get('checkpoint', {}).get('account_ids', [])}
        else:
            lease, node, task = native.direct._owned(state, owner, args, active=not observational)
        sources = {node['id']}
        for event in events:
            obj = state.get('cleanup_objects', {}).get(event.get('responsibility_id'))
            if obj:
                if obj.get('owner') != owner or obj.get('task_id') != task['id']:
                    raise CleanupScopeError('对象责任不属于当前授权轮次')
                sources.add(obj['source_node_id'])
        records, authorities = {}, {}
        for nid in sources:
            source = native.c.owned(state['nodes'], owner, nid)
            if source['task_id'] != task['id']:
                raise CleanupScopeError('清理责任不属于本轮原模块')
            pid, eid = source.get('record_project_id'), source.get('record_execution_id')
            project = native.service.store.get_project(owner, state['tasks'][source['task_id']]['project_id'])
            key = pid, eid
            if key not in records:
                records[key] = ui_records.load(native.service.store, owner, pid, eid)
            authorities[nid] = {'owner': owner, 'task_id': task['id'], 'source_node_id': nid,
                'project_id': task['project_id'], 'record': records[key],
                'scene_retention': copy.deepcopy(project.get('ui_scene_retention') or {'key': 'none'}),
                'execution_permission': copy.deepcopy(project.get('ui_execution_permission') or {'key': 'safe'})}
        state['_cleanup_authority'] = authorities
        try:
            results = [apply(state, lease, node, event, native.c.clock()) for event in events]
        finally:
            state.pop('_cleanup_authority', None)
        from .cleanup_capabilities import settle_units
        settle_units(state, node, native.c.clock())
        return {'saved': True, 'results': results, 'business_action_performed': False}
