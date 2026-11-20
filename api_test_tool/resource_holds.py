"""Settle verified holds through the original durable return/ACK protocol."""
from .resource_scheduler import pending_operations, retention_conditions
from .orchestration_storage import select_records


def releasable(state, lease):
    node = state['nodes'][lease['node_id']]
    if not (lease.get('resource_hold') and lease.get('revoked')
            and lease.get('executor_stopped') is True and lease.get('executor_fenced') is True
            and lease.get('browser_stopped') is True):
        return False
    if any(c.get('state') != 'exited' for c in lease.get('auxiliary_channels', {}).values()):
        return False
    if retention_conditions(node, lease) or lease.get('hold', {}).get('retained_conditions'):
        return False
    if pending_operations(state, lease['id']):
        return False
    from .cleanup_capabilities import blockers
    if blockers(state, lease):
        return False
    # Missing evidence is not a successful reconciliation. Keep the original
    # isolation snapshot; only the current ledger can discharge its operations.
    for oid in lease.get('hold', {}).get('pending_operation_ids', []):
        op = state['operations'].get(oid)
        if not op or op.get('lease_id') != lease['id'] or op.get('state') not in {'confirmed', 'not_sent'}:
            return False
    return not select_records(state.get('direct_commands', {}), lease_id=lease['id'], state='running')


def settle(controller):
    # No new model/browser calls, no replay and no additional polling interval.
    from .orchestration_storage import read_sections
    with controller.connect() as db:
        state = read_sections(db, ('leases',))
    if not any(lease.get('resource_hold') for lease in state['leases'].values()):
        return
    with controller.transaction() as (db, state):
        for lease in state['leases'].values():
            if not lease.get('resource_hold'):
                continue
            node = state['nodes'][lease['node_id']]
            from .cleanup_capabilities import reconcile_saved_observations
            reconcile_saved_observations(controller, db, state, lease)
            remaining = pending_operations(state, lease['id'])
            hold = lease.setdefault('hold', {})
            hold['remaining_operation_ids'] = [op['id'] for op in remaining]
            from .cleanup_capabilities import blockers
            hold['cleanup_responsibility_ids'] = blockers(state, lease)
            hold.setdefault('original_reason', hold.get('reason', ''))
            if remaining:
                reason = '原操作结果仍待核实，账号保持隔离'
            elif retention_conditions(node, lease) or hold.get('retained_conditions') or any(
                    state['cleanup_objects'][oid].get('retain_scene') for oid in hold['cleanup_responsibility_ids']):
                reason = '原操作已核实；仍有业务现场保留条件，账号保持保留'
            elif hold['cleanup_responsibility_ids']:
                reason = '执行已结束；原清理操作尚未确认结束，等待原责任核实'
            elif (lease.get('executor_stopped') is not True or lease.get('browser_stopped') is not True
                  or any(c.get('state') != 'exited' for c in lease.get('auxiliary_channels', {}).values())):
                reason = '原操作已核实；等待原执行器及主辅助浏览器的退出确认'
            else:
                reason = '原执行通道已退出；正在按原账本核对并结算资源'
            hold['reason'] = reason
            unknown_cleanup = any(state['cleanup_objects'][oid]['state'] in {'creating', 'cleaning', 'unknown'}
                                  for oid in hold['cleanup_responsibility_ids'])
            node.update(state='isolated' if remaining or unknown_cleanup else 'retained', reason=reason)
            if lease.get('executor_stopped') is True:
                node['execution_ended'] = True
        candidates = [(state['nodes'][l['node_id']]['owner'], l['runner_id'], {
            **l.get('return_record', {}), 'lease_id': l['id'],
            'executor_stopped': True, 'browser_stopped': True,
            'resource_resolution': True, 'automatic_hold_resolution': True,
            'outcome': l.get('return_outcome', 'blocked'),
            'reason': '原操作已核实且全部执行通道已退出，自动完成资源交还',
        }) for l in state['leases'].values() if l.get('resource_hold') and releasable(state, l)]
    from .orchestration import Conflict
    for owner, host, request in candidates:
        try:
            # Rechecked under the return transaction; evidence may change
            # between this scan and a late host observation or user control.
            controller.return_account(owner, host, request)
        except (Conflict, PermissionError):
            # Another settlement or changed evidence wins; next tick rechecks.
            continue
