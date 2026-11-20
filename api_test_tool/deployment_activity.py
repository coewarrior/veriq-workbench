"""Read-only release probe, also runnable via stdin inside the previous image.

Only counts are printed. Never construct a Controller/Store, migrate a database,
load historical screenshots, schedule tasks, or change running test state.
"""
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import UUID

REPORT_RETRY_ERROR = '最终报告生成未完成；原始用例保留，账号不因此占用。可重试交还回执以重试报告。'


def published_settlement(root, node, state, _ancestors=frozenset()):
    """Prove a stale marker using existing artifacts only; missing facts fail closed.

    Shared by the release probe and the normal settlement callback. The probe
    remains standalone so Jenkins can run this candidate code in the old image.
    """
    try:
        owner = node['owner']
        if (not re.fullmatch(r'[a-f0-9]{64}', owner)
                or node['id'] in _ancestors
                or node['state'] not in {'completed', 'blocked', 'stopped', 'paused', 'isolated', 'retained'}
                or node.get('session_removed') or node.get('report_deferred_deleted')
                or node.get('record_successor_node_id')):
            return False
        if not node.get('record_project_id') and not node.get('record_execution_id'):
            # An unexecuted split container has no record of its own. Its
            # completed children, not the parent session's unrelated report,
            # supply every original execution/revision/publication proof.
            children = node.get('child_ids')
            if (not isinstance(children, list) or not children or len(set(children)) != len(children)
                    or set(children) != {item['id'] for item in state['nodes'].values() if item.get('parent_id') == node['id']}
                    or any(node.get(key) for key in ('attempts', 'case_history', 'outcome_history', 'direct_holder'))
                    or any(lease['node_id'] == node['id'] for lease in state['leases'].values())):
                return False
            task = state['tasks'][node['task_id']]
            return all(cid in task['node_ids'] and state['nodes'][cid].get('parent_id') == node['id']
                       and state['nodes'][cid]['task_id'] == node['task_id']
                       and state['nodes'][cid]['owner'] == owner
                       and (published_settlement(root, state['nodes'][cid], state, _ancestors | {node['id']})
                            or settled_stopped_child(root, state['nodes'][cid], state))
                       for cid in children)
        pid, eid = node['record_project_id'], node['record_execution_id']
        if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value) for value in (pid, eid)):
            return False
        related = [n for n in state['nodes'].values() if n['id'] == node['id'] or
                   (node.get('child_ids') and n['task_id'] == node['task_id'] and not n.get('child_ids'))]
        for current in related:
            if current['state'] not in {'completed', 'blocked', 'stopped', 'paused', 'isolated', 'retained'}:
                return False
            leases = [lease for lease in state['leases'].values() if lease['node_id'] == current['id']]
            if any(not (lease.get('resource_hold') is True and lease.get('executor_stopped') is True
                        and lease.get('browser_stopped') is True
                        and all(channel.get('state') == 'exited' for channel in lease.get('auxiliary_channels', {}).values()))
                   for lease in leases):
                return False
            # A stopped resource hold keeps unresolved business evidence; it
            # is not a running process and is never released by this check.
            task = state['tasks'][current['task_id']]
            dispatch = current.get('executor_dispatch') or current.get('dispatch_offer') or {}
            if (not current.get('child_ids') and (current.get('native_browser') or task.get('execution_route') == 'native_browser')
                    and (current.get('attempts') or dispatch)
                    and current.get('native_browser_stopped') is not True):
                return False
        directory = root / 'sessions' / owner / 'projects' / pid
        project = json.loads((directory / 'metadata.json').read_text())
        revision = project.get('ui_execution_revision')
        intent = project.get('ui_finish_request') or {}
        result = intent.get('result') or {}
        final = project.get('ui_final_report') or {}
        if (project.get('id') != pid or project.get('ui_execution_id') != eid
                or type(revision) is not int or intent.get('error')
                or result.get('phase') != 'published' or result.get('pending') is not False
                or not intent.get('request_id') or result.get('request_id') != intent['request_id']
                or any(value.get('execution_id') != eid or value.get('revision') != revision
                       for value in (intent, result, final))):
            return False
        rid = result.get('report', {}).get('id')
        if not isinstance(rid, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', rid):
            return False
        record = json.loads((directory / 'ui-executions' / eid / 'cases.json').read_text())
        report = json.loads((directory / 'analyses' / rid / 'report.json').read_text())
        snapshot = report.get('ui_snapshot') or {}
        return (record.get('id') == eid and record.get('revision') == revision
                and record.get('report_id') == rid and record.get('published_revision') == revision
                and snapshot.get('id') == eid and snapshot.get('revision') == revision)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def settled_stopped_child(root, node, state):
    """Prove an already-finalized legacy stop report for its pure parent.

    The ordinary stop callback publishes without ui_finish_request. It clears
    the child's queue only after saving the report. Never use this proof to
    clear a child's pending work or to label unpublished observations complete.
    """
    try:
        task = state['tasks'][node['task_id']]
        dispatch = node.get('executor_dispatch') or {}
        if (node['state'] != 'stopped' or not node.get('parent_id')
                or task.get('execution_route') != 'native_browser'
                or node.get('control_intent', task['intent']) != 'stop'
                or node.get('native_browser_stopped') is not True
                or not dispatch.get('exit_acknowledged_at') or not dispatch.get('holder_id')
                or any(node.get(key) for key in ('child_ids', 'finalization_pending', 'native_report_pending',
                    'report_error', 'session_removed', 'report_deferred_deleted', 'record_successor_node_id', 'direct_holder'))
                or any(lease['node_id'] == node['id'] for lease in state['leases'].values())
                or any(control.get('state') in {'pending', 'received'}
                       for control in node.get('executor_controls', {}).values())):
            return False
        owner, pid, eid = node['owner'], node['record_project_id'], node['record_execution_id']
        if (task['owner'] != owner or not re.fullmatch(r'[a-f0-9]{64}', owner)
                or any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value) for value in (pid, eid))):
            return False
        directory = root / 'sessions' / owner / 'projects' / pid
        project = json.loads((directory / 'metadata.json').read_text())
        revision = project.get('ui_execution_revision')
        if (project.get('id') != pid or project.get('ui_execution_id') != eid
                or type(revision) is not int or project.get('ui_finish_request') or project.get('ui_final_report')):
            return False
        record = json.loads((directory / 'ui-executions' / eid / 'cases.json').read_text())
        rid = record.get('report_id')
        if (not isinstance(rid, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', rid)
                or (project.get('last_analysis') or {}).get('id') != rid):
            return False
        report = json.loads((directory / 'analyses' / rid / 'report.json').read_text())
        snapshot = report.get('ui_snapshot') or {}
        return (record.get('id') == eid and record.get('revision') == revision
                and record.get('published_revision') == revision
                and snapshot.get('id') == eid and snapshot.get('revision') == revision)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def completed_earlier_finish(directory, project, eid, revision, *, include_current=False):
    """Prove an old finish is done, without treating newer saved work as final.

    Saving after publication may refresh that report's snapshot in place. Its
    old finish receipt is still complete, but does not request the new revision.
    Missing/conflicting publication artifacts remain active for release purposes.
    """
    intent = project.get('ui_finish_request') or {}
    result = intent.get('result') or {}
    final = project.get('ui_final_report') or {}
    prior = intent.get('revision')
    if (type(prior) is not int or type(revision) is not int
            or not 0 <= prior <= revision or (prior == revision and not include_current) or intent.get('error')
            or result.get('phase') != 'published' or result.get('pending') is not False
            or not intent.get('request_id') or result.get('request_id') != intent['request_id']
            or any(value.get('execution_id') != eid or type(value.get('revision')) is not int
                   or value['revision'] != prior for value in (intent, result, final))):
        return False
    rid = result.get('report', {}).get('id')
    if not isinstance(rid, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', rid):
        return False
    record = json.loads((directory / 'ui-executions' / eid / 'cases.json').read_text())
    report = json.loads((directory / 'analyses' / rid / 'report.json').read_text())
    snapshot = report.get('ui_snapshot') or {}
    published = record.get('published_revision')
    return (record.get('id') == eid and type(record.get('revision')) is int
            and record['revision'] == revision and record.get('report_id') == rid
            and type(published) is int and prior <= published <= revision
            and snapshot.get('id') == eid and type(snapshot.get('revision')) is int
            and snapshot['revision'] == published)


def dormant_native_report(root, node, state, _ancestors=frozenset(), *, allow_completed_earlier_finish=False):
    """An exited native worker has saved results but has not requested a report.

    This is durable idle work, not publication in progress. Do not clear its
    pending markers or manufacture a report. Unknown exit/binding facts still
    block deployment; an actual finish request uses the existing settlement gate.
    Only the read-only activity probe opts into older completed requests; normal
    reconciliation keeps its original behavior and cannot clear their markers.
    """
    try:
        owner = node['owner']
        task = state['tasks'][node['task_id']]
        report_error = node.get('report_error')
        if report_error and (not allow_completed_earlier_finish or report_error != REPORT_RETRY_ERROR):
            return False
        if (not re.fullmatch(r'[a-f0-9]{64}', owner)
                or node['id'] in _ancestors or task['owner'] != owner
                or task.get('execution_route') != 'native_browser'
                or node['state'] not in {'completed', 'blocked', 'stopped', 'paused'}
                or any(node.get(key) for key in ('session_removed', 'report_deferred_deleted',
                                                 'record_successor_node_id', 'direct_holder'))
                or any(lease['node_id'] == node['id'] for lease in state['leases'].values())
                or any(control.get('state') in {'pending', 'received'}
                       for control in node.get('executor_controls', {}).values())):
            return False
        children = node.get('child_ids')
        if children:
            if (report_error or not isinstance(children, list) or len(set(children)) != len(children)
                    or set(children) != {n['id'] for n in state['nodes'].values()
                                         if n.get('parent_id') == node['id']}
                    or any(node.get(key) for key in ('record_project_id', 'record_execution_id',
                                                     'attempts', 'case_history', 'outcome_history',
                                                     'executor_dispatch', 'dispatch_offer'))):
                return False
            return all(cid in task['node_ids']
                       and state['nodes'][cid]['task_id'] == task['id']
                       and state['nodes'][cid]['owner'] == owner
                       and (published_settlement(root, state['nodes'][cid], state)
                            or settled_stopped_child(root, state['nodes'][cid], state)
                            or dormant_native_report(root, state['nodes'][cid], state,
                                                     _ancestors | {node['id']},
                                                     allow_completed_earlier_finish=allow_completed_earlier_finish))
                       for cid in children)
        dispatch = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
        pid, eid = node['record_project_id'], node['record_execution_id']
        if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value) for value in (pid, eid)):
            return False
        directory = root / 'sessions' / owner / 'projects' / pid
        project = json.loads((directory / 'metadata.json').read_text())
        if (project.get('id') != pid or project.get('ui_execution_id') != eid
                or type(project.get('ui_execution_revision')) is not int
                or not (directory / 'ui-executions' / eid / 'cases.json').is_file()):
            return False
        earlier_completed = bool(project.get('ui_finish_request') and allow_completed_earlier_finish
                                 and completed_earlier_finish(directory, project, eid, project['ui_execution_revision']))
        # A legacy callback also stamped REPORT_RETRY_ERROR on bookkeeping DB
        # failures. Only complete older publication artifacts can disprove that
        # marker as active work. Preserve the marker and all report files.
        if report_error and not earlier_completed:
            return False
        if project.get('ui_finish_request') and not earlier_completed:
            return False
        if not node.get('native_report_pending'):
            # A cancelled, never-acquired child has no publication job. It
            # cannot strand a pure parent, and is not called a published report.
            return (node.get('parent_id') in _ancestors and node['state'] == 'stopped'
                    and not any(node.get(key) for key in ('attempts', 'case_history',
                                                          'outcome_history', 'native_report_pending',
                                                          'executor_dispatch'))
                    and dispatch.get('state') == 'cancelled'
                    and bool(dispatch.get('id') and dispatch.get('holder_id')
                             and dispatch.get('exit_acknowledged_at')))
        pending = node.get('native_report_pending') or {}
        receipt = state['direct_settlements'][pending['lease_id']]
        binding = receipt['report_binding']
        if (node.get('native_browser_stopped') is not True
                or not dispatch.get('exit_acknowledged_at')
                or not dispatch.get('holder_id')
                or receipt.get('holder_id') != dispatch['holder_id']
                or receipt.get('owner') != owner or receipt.get('node_id') != node['id']
                or receipt.get('native_browser') is not True or receipt.get('ack_required') is not False
                or binding.get('task_id') != task['id']
                or binding.get('node_revision') != node['revision']
                or binding.get('project_id') != pid or binding.get('execution_id') != eid
                or not binding.get('dispatch_id')
                or binding['dispatch_id'] != (dispatch.get('dispatch_id') or dispatch.get('id'))):
            return False
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def dormant_aggregate_report(root, node, state):
    """Read-only proof for a stopped, never-executed design/report container.

    Legacy containers can already own a published design-only report while
    their exited children retain newer observations. Preserve all markers and
    reports; this proves inactivity, not completion of those observations.
    """
    try:
        task = state['tasks'][node['task_id']]
        owner = node['owner']
        children = node.get('child_ids')
        if (task.get('execution_route') != 'native_browser' or task['intent'] not in {'stop', 'pause'}
                or task['owner'] != owner or not re.fullmatch(r'[a-f0-9]{64}', owner)
                or node['state'] not in {'completed', 'stopped', 'paused'}
                or not isinstance(children, list) or not children or len(set(children)) != len(children)
                or set(children) != {n['id'] for n in state['nodes'].values() if n.get('parent_id') == node['id']}
                or any(node.get(key) for key in ('attempts', 'case_history', 'outcome_history',
                    'direct_holder', 'executor_dispatch', 'dispatch_offer', 'native_report_pending',
                    'record_successor_node_id', 'session_removed', 'report_deferred_deleted', 'report_error'))
                or any(lease['node_id'] == node['id'] for lease in state['leases'].values())
                or any(c.get('state') in {'pending', 'received'} for c in node.get('executor_controls', {}).values())):
            return False
        pid, eid = node['record_project_id'], node['record_execution_id']
        if pid != task['project_id'] or any(not re.fullmatch(r'[a-zA-Z0-9_-]+', v) for v in (pid, eid)):
            return False
        directory = root / 'sessions' / owner / 'projects' / pid
        project = json.loads((directory / 'metadata.json').read_text())
        revision = project.get('ui_execution_revision')
        if (project.get('id') != pid or project.get('ui_execution_id') != eid
                or type(revision) is not int or project.get('ui_finish_request') or project.get('ui_final_report')):
            return False
        record = json.loads((directory / 'ui-executions' / eid / 'cases.json').read_text())
        rid = record.get('report_id')
        if (not isinstance(rid, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', rid)
                or (project.get('last_analysis') or {}).get('id') != rid
                or record.get('id') != eid or record.get('revision') != revision
                or record.get('published_revision') != revision
                or any(c.get('status') != 'not_run' or any(p.get('status') != 'not_run'
                    for p in c.get('checkpoints', [])) for c in record.get('cases', []))):
            return False
        snapshot = json.loads((directory / 'analyses' / rid / 'report.json').read_text()).get('ui_snapshot') or {}
        if snapshot.get('id') != eid or snapshot.get('revision') != revision:
            return False
        for cid in children:
            child = state['nodes'][cid]
            dispatch = child.get('executor_dispatch') or {}
            if (cid not in task['node_ids'] or child['owner'] != owner or child['task_id'] != task['id']
                    or child['state'] != 'stopped' or child.get('child_ids')
                    or child.get('control_intent', task['intent']) != 'stop'
                    or child.get('native_browser_stopped') is not True
                    or not dispatch.get('exit_acknowledged_at') or not dispatch.get('holder_id')
                    or any(child.get(k) for k in ('direct_holder', 'record_successor_node_id',
                        'session_removed', 'report_deferred_deleted'))
                    or any(l['node_id'] == cid for l in state['leases'].values())
                    or any(c.get('state') in {'pending', 'received'} for c in child.get('executor_controls', {}).values())):
                return False
            if (published_settlement(root, child, state) or settled_stopped_child(root, child, state)
                    or dormant_native_report(root, child, state, allow_completed_earlier_finish=True)):
                continue
            if any(child.get(k) for k in ('native_report_pending', 'finalization_pending', 'report_error')):
                return False
            cpid, ceid = child['record_project_id'], child['record_execution_id']
            if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', v) for v in (cpid, ceid)):
                return False
            child_dir = root / 'sessions' / owner / 'projects' / cpid
            child_project = json.loads((child_dir / 'metadata.json').read_text())
            if (child_project.get('id') != cpid or child_project.get('ui_execution_id') != ceid
                    or child_project.get('managed_parent_project_id') != pid
                    or not completed_earlier_finish(child_dir, child_project, ceid, child_project['ui_execution_revision'])):
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def stopped_split_is_idle(root, node, state):
    """A stopped pure container is idle after every phase has really exited.

    Cancelled continuations can share a published record with their predecessor;
    an older completed publication can also precede newer saved observations.
    Neither is an active parent publication. This release-only proof preserves
    all report files, pending markers and normal settlement behavior.
    """
    try:
        task = state['tasks'][node['task_id']]
        owner, children = node['owner'], node.get('child_ids')
        if (task.get('execution_route') != 'native_browser' or task['intent'] != 'stop'
                or task['owner'] != owner or not re.fullmatch(r'[a-f0-9]{64}', owner)
                or node['state'] not in {'completed', 'stopped'}
                or not isinstance(children, list) or not children or len(set(children)) != len(children)
                or set(children) != {n['id'] for n in state['nodes'].values() if n.get('parent_id') == node['id']}
                or any(node.get(k) for k in ('record_project_id', 'record_execution_id', 'attempts',
                    'case_history', 'outcome_history', 'direct_holder', 'executor_dispatch', 'dispatch_offer',
                    'native_report_pending', 'report_error', 'record_successor_node_id', 'session_removed',
                    'report_deferred_deleted'))):
            return False
        for current in [node, *(state['nodes'][cid] for cid in children)]:
            if (current['id'] not in task['node_ids'] or current['task_id'] != task['id']
                    or current['owner'] != owner
                    or current['state'] not in {'completed', 'stopped', 'blocked', 'paused'}
                    or any(l['node_id'] == current['id'] for l in state['leases'].values())
                    or any(c.get('state') in {'pending', 'received'}
                           for c in current.get('executor_controls', {}).values())):
                return False
            if current is node:
                continue
            dispatch = current.get('executor_dispatch') or current.get('dispatch_offer') or {}
            if (any(current.get(k) for k in ('child_ids', 'direct_holder', 'finalization_pending',
                    'native_report_pending', 'report_error', 'session_removed', 'report_deferred_deleted'))
                    or not dispatch.get('exit_acknowledged_at') or not dispatch.get('holder_id')
                    or (current.get('attempts') and current.get('native_browser_stopped') is not True)):
                return False
            pid, eid = current['record_project_id'], current['record_execution_id']
            if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', v) for v in (pid, eid)):
                return False
            successor_id = current.get('record_successor_node_id')
            source = current.get('continuation_source') or {}
            if successor_id:
                successor = state['nodes'][successor_id]
                if (successor_id not in children or successor_id == current['id']
                        or successor.get('continuation_source') != {
                            'source_task_id': task['id'], 'source_node_id': current['id'],
                            'project_id': pid, 'execution_id': eid}):
                    return False
            if source:
                predecessor = state['nodes'][source['source_node_id']]
                if (predecessor['id'] not in children
                        or predecessor.get('record_successor_node_id') != current['id']
                        or source.get('source_task_id') != task['id']
                        or source.get('project_id') != pid or source.get('execution_id') != eid
                        or predecessor.get('record_project_id') != pid or predecessor.get('record_execution_id') != eid):
                    return False
            directory = root / 'sessions' / owner / 'projects' / pid
            project = json.loads((directory / 'metadata.json').read_text())
            if (project.get('id') != pid or project.get('ui_execution_id') != eid
                    or project.get('managed_parent_project_id') != task['project_id']
                    or not completed_earlier_finish(directory, project, eid,
                        project.get('ui_execution_revision'), include_current=True)):
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def dormant_native_continuation(node, state, unsettled_node_ids):
    """Prove an untouched formal successor is asleep, without ending its queue.

    A predecessor's exit is not a successor's exit ACK. This release-only proof
    keeps both generations, their reports and their queue position unchanged.
    It deliberately does not cover ordinary offers, actual claims or browsers.
    """
    try:
        task = state['tasks'][node['task_id']]
        origin = node['continuation_source']
        source = state['nodes'][origin['source_node_id']]
        binding, previous = node['executor_dispatch'], source['executor_dispatch']
        ids = {node['id'], source['id']}
        if (len(ids) != 2 or task.get('execution_route') != 'native_browser' or task['intent'] != 'run'
                or node['state'] != 'queued' or node.get('native_browser') is not True
                or source['state'] != 'completed' or source.get('native_browser_stopped') is not True
                or task['owner'] != node['owner'] or source['owner'] != node['owner']
                or source['task_id'] != task['id'] or not ids.issubset(task['node_ids'])
                or source.get('record_successor_node_id') != node['id']
                or source.get('parent_id') != node.get('parent_id')
                or origin != {'source_task_id': task['id'], 'source_node_id': source['id'],
                    'project_id': source['record_project_id'], 'execution_id': source['record_execution_id']}
                or any(node[key] != source[key] for key in ('record_project_id', 'record_execution_id'))
                or binding.get('receipt_source') != 'explicit_source_continuation'
                or previous.get('receipt_source') != 'executor_claim'
                or not binding.get('dispatch_id') or not previous.get('dispatch_id')
                or binding['dispatch_id'] == previous['dispatch_id']
                or not binding.get('holder_id') or binding['holder_id'] != previous.get('holder_id')
                or binding.get('exit_acknowledged_at') is not None
                or any(node.get(key) for key in ('attempts', 'dispatch_offer', 'executor_dispatch_history',
                    'dispatch_offer_history', 'native_browser_stopped', 'reservation', 'protected',
                    'native_executor_status', 'record_successor_node_id'))
                or any(value for key, value in node.items()
                       if key.startswith(('native_environment', 'native_context')))
                or None in unsettled_node_ids or ids.intersection(unsettled_node_ids)
                or any(lease['node_id'] in ids for lease in state['leases'].values())):
            return False
        for current in (source, node):
            if (current.get('control_intent', 'run') != 'run'
                    or any(current.get(key) for key in ('child_ids', 'direct_holder', 'native_claim_pending',
                        'finalization_pending', 'native_report_pending', 'report_error',
                        'session_removed', 'report_deferred_deleted'))
                    or any(control.get('state') not in {'exited', 'obsolete'}
                           for control in current.get('executor_controls', {}).values())):
                return False
        for key in ('executor_ref', 'coordinator_ref'):
            if UUID(binding[key].removeprefix('thread:')) != UUID(previous[key].removeprefix('thread:')):
                return False
        exited = previous['exit_acknowledged_at']
        created = node['created']
        evidence = source['native_exit_evidence']
        if (type(exited) not in (int, float) or type(created) not in (int, float)
                or not 0 < exited <= created
                or evidence.get('source') not in {'executor_reported', 'user_confirmation'}
                or type(evidence.get('at')) not in (int, float) or not 0 < evidence['at'] <= created
                or binding.get('received_at') != created or binding.get('last_seen_at') != created):
            return False
        waiting = node['resource_wait']
        if (waiting.get('end_turn') is not True or waiting.get('resources_available') is not False
                or waiting.get('task_id') != task['id'] or waiting.get('node_id') != node['id']
                or waiting.get('wake_owner') != 'coordinator_handoff'
                or UUID(waiting['coordinator_ref'].removeprefix('thread:')) !=
                   UUID(binding['coordinator_ref'].removeprefix('thread:'))):
            return False
        # Notices may be stored on a different releasing node. Sent is not
        # consumed, and an unknown delivery must continue to protect release.
        for current in state['nodes'].values():
            for event in current.get('native_handoffs', {}).values():
                notices = [event, *event.get('continuations', [])]
                if event.get('continuation'):
                    notices.append(event['continuation'])
                for notice in notices:
                    targets = {notice.get('node_id'), (notice.get('claim_arguments') or {}).get('node_id')}
                    if (ids.intersection(targets)
                            and notice.get('delivery_state') not in {'obsolete', 'received', 'transferred'}):
                        return False
                    if (node['id'] in targets
                            and any(notice.get(key) is not None for key in ('claim_received_at', 'claimed_at'))):
                        return False
        return True
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def execution_lease_nodes(state):
    """Read original lease ownership from existing evidence, without mutation."""
    lease_nodes = {}
    def bind(lease_id, node_id):
        if lease_id and node_id:
            lease_nodes.setdefault(lease_id, set()).add(node_id)
    for node in state['nodes'].values():
        for attempt in node.get('attempts', []):
            bind(attempt.get('lease_id'), node['id'])
    for kind in ('leases', 'direct_settlements'):
        for lease_id, receipt in state.get(kind, {}).items():
            bind(lease_id, receipt.get('node_id'))
    for event in state.get('outbox', {}).values():
        bind(event.get('lease_id'), event.get('node_id'))
    return lease_nodes


def action_node_owner(lease_nodes, node_id, lease_id):
    """Resolve legacy node-less actions; absent/conflicting ownership is unknown."""
    bound = set(lease_nodes.get(lease_id, ()))
    if node_id:
        bound.add(node_id)
    return next(iter(bound)) if len(bound) == 1 else None


def read_activity_state(db, postgres=False):
    """Read one caller-owned snapshot without reconstructing archived cases.

    Keep this reader standalone: Jenkins runs this file through stdin in the
    previous image, whose package cannot provide the new storage helpers.
    """
    if not postgres:
        return json.loads(db.execute('SELECT value FROM state_metadata WHERE id=1').fetchone()[0])
    status = db.execute('SELECT schema_version,activation,verified FROM platform_storage WHERE id=1').fetchone()
    if status != (1, 'active', True):
        raise ValueError('PostgreSQL storage is not verified and active; release deferred')
    state = {key: {} if value is None else json.loads(value)
             for key, value in db.execute('SELECT key,value FROM state_sections ORDER BY ordinal')}
    for section, key, meta, history in db.execute(
            'SELECT section,key,meta,history FROM state_entries ORDER BY section,ordinal'):
        value = json.loads(meta)
        if section == 'nodes' and history == 1:
            value['case_history'] = {}
        state[section][key] = value
    # Every case_history consumer in this probe checks only truthiness when
    # proving a pure/unexecuted node. Preserve that fact without loading cases;
    # inline non-object histories remain untouched in their entry metadata.
    for (key,) in db.execute("""SELECT entry.key FROM state_entries AS entry
            WHERE entry.section='nodes' AND entry.history=1
            AND EXISTS(SELECT 1 FROM state_case_history AS history
                       WHERE history.node_key=entry.key)"""):
        state['nodes'][key]['case_history'] = {'_stored': True}
    return state


TERMINAL = {'completed', 'blocked', 'stopped', 'paused', 'isolated', 'retained'}


def lease_exited(lease):
    return (lease.get('executor_stopped') is True and lease.get('browser_stopped') is True
            and all(c.get('state') == 'exited' for c in lease.get('auxiliary_channels', {}).values()))


def control_obsolete(control, binding):
    """Only a receipt for this exact, already exited dispatch is obsolete."""
    return bool(binding.get('exit_acknowledged_at')
        and control.get('holder_id') == binding.get('holder_id')
        and str(control.get('executor_ref', '')).removeprefix('thread:') ==
            str(binding.get('executor_ref', '')).removeprefix('thread:')
        and control.get('created_at', float('inf')) <= binding['exit_acknowledged_at']
        and str(control.get('id', '')).endswith(':' + (binding.get('dispatch_id') or binding.get('id') or '\0')))


def executor_exited(node, task=None):
    if task is not None and task.get('execution_route') != 'native_browser' and not node.get('native_browser'):
        # Non-native release/ACK removes its lease only after fencing and
        # reconciliation. Native desktop fields do not exist on that route.
        return node['state'] in TERMINAL
    binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
    return bool(binding.get('exit_acknowledged_at') and
                (not node.get('attempts') or node.get('native_browser_stopped') is True))


def never_started(node):
    offer = node.get('dispatch_offer') or {}
    if offer and not (offer.get('state') == 'waiting_capacity'
                      and not offer.get('holder_id') and not offer.get('executor_ref')):
        return False
    return not any(node.get(k) for k in ('executor_dispatch', 'direct_holder', 'case_history', 'outcome_history',
        'attempts', 'native_claim_pending', 'native_environment', 'native_environment_keys',
        'executor_dispatch_history', 'dispatch_offer_history'))


def resumed_node_exit(node):
    """Original-node resume: old real exit, with no claim in the new dispatch.

    This proves preparation/waiting only, never a new executor exit ACK.
    Kept standalone for the read-only deployment probe.
    """
    binding = node.get('executor_dispatch') or {}
    history = node.get('executor_dispatch_history') or []
    previous = history[-1] if history else {}
    attempts = node.get('attempts') or []
    if (binding.get('receipt_source') not in {'explicit_source_resume', 'explicit_control_resume'}
            or not binding.get('resumed_from_dispatch_id')
            or binding['resumed_from_dispatch_id'] != previous.get('dispatch_id')
            or not binding.get('dispatch_id') or binding['dispatch_id'] == previous.get('dispatch_id')
            or not previous.get('exit_acknowledged_at')
            or previous['exit_acknowledged_at'] > binding.get('received_at', 0)
            or binding.get('received_at') != binding.get('last_seen_at')
            or binding.get('exit_acknowledged_at') is not None
            or node.get('native_browser_stopped') is not True
            or any(node.get(k) for k in ('direct_holder', 'native_claim_pending', 'reservation'))
            or not attempts or attempts[-1].get('lease_id') != binding.get('resumed_from_lease_id')
            or attempts[-1].get('created', float('inf')) > previous['exit_acknowledged_at']
            or any(not binding.get(k) or str(binding[k]).removeprefix('thread:') !=
                   str(previous.get(k, '')).removeprefix('thread:') for k in ('holder_id', 'executor_ref'))):
        return None
    return previous


def unclaimed_native_resume(node, state):
    return bool(state['tasks'][node['task_id']].get('execution_route') == 'native_browser'
        and node['state'] in {'queued', 'stopped', 'paused'} and resumed_node_exit(node)
        and not any(l['node_id'] == node['id'] for l in state['leases'].values()))


def cancelled_unclaimed(node, state):
    """Coordinator cancellation proves no claim, never a fabricated browser exit."""
    proof = node.get('unclaimed_cancellation') or {}
    task = state['tasks'][node['task_id']]
    binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
    closeout = task.get('coordinator_closeout') or {}
    return bool(proof and node['state'] == 'stopped' and task['intent'] == 'stop'
        and task['owner'] == node['owner'] and node.get('control_intent') == 'stop'
        and closeout.get('disposition') == 'ended' and proof.get('at') == closeout.get('at')
        and proof.get('at') == node.get('scheduling_cancelled_at')
        and proof.get('node_revision') == node['revision']
        and proof.get('dispatch_id') == (binding.get('dispatch_id') or binding.get('id'))
        and proof.get('holder_id') == binding.get('holder_id')
        and proof.get('executor_ref') == binding.get('executor_ref')
        and not any(node.get(k) for k in ('attempts', 'direct_holder', 'native_claim_pending',
            'native_environment', 'native_environment_keys', 'reservation'))
        and not any(l['node_id'] == node['id'] for l in state['leases'].values()))


def inactive_native_generation(node, state):
    """Recognize existing stop/return evidence across a never-claimed generation.

    Old deployments did not write unclaimed_cancellation. A previous worker's
    exit is evidence for that worker only; the new generation must independently
    prove it never received a claim or acquired an environment/lease.
    """
    task = state['tasks'][node['task_id']]
    if (task.get('intent') in {'stop', 'pause'}
            and node.get('control_intent', task['intent']) in {'stop', 'pause'}
            and unclaimed_native_resume(node, state)):
        return True
    if (task.get('execution_route') != 'native_browser' or task.get('intent') not in {'stop', 'pause'}
            or node['state'] not in {'queued', 'stopped', 'paused'}
            or node.get('control_intent', task['intent']) not in {'stop', 'pause'}
            or any(node.get(k) for k in ('direct_holder', 'native_claim_pending', 'reservation'))
            or any(v for k, v in node.items() if k.startswith(('native_environment', 'native_context')))
            or any(l['node_id'] == node['id'] for l in state['leases'].values())):
        return False
    offer = node.get('dispatch_offer') or {}
    if (offer.get('state') == 'cancelled' and offer.get('id') and offer.get('created_at')
            and not node.get('executor_dispatch') and not offer.get('received_at')):
        history = node.get('executor_dispatch_history') or []
        if any(not b.get('exit_acknowledged_at') or b['exit_acknowledged_at'] > offer['created_at'] for b in history):
            return False
        for attempt in node.get('attempts', []):
            receipt = state.get('direct_settlements', {}).get(attempt.get('lease_id'), {})
            if (receipt.get('node_id') != node['id'] or receipt.get('owner') != node['owner']
                    or receipt.get('native_browser') is not True
                    or not (receipt.get('ack_required') is False or receipt.get('local_ack_at'))
                    or not any(b.get('holder_id') == receipt.get('holder_id')
                        and b.get('exit_acknowledged_at', 0) >= attempt.get('created', float('inf')) for b in history)):
                return False
        return not node.get('attempts') or node.get('native_browser_stopped') is True
    binding = node.get('executor_dispatch') or {}
    origin = node.get('continuation_source') or {}
    source = state['nodes'].get(origin.get('source_node_id'), {})
    previous = source.get('executor_dispatch') or {}
    if (not source or node.get('attempts') or offer or node.get('executor_dispatch_history')
            or node.get('dispatch_offer_history') or node.get('native_browser_stopped')
            or binding.get('receipt_source') != 'explicit_source_continuation'
            or source.get('state') not in {'completed', 'blocked', 'stopped', 'paused'}
            or source.get('native_browser_stopped') is not True or not previous.get('exit_acknowledged_at')
            or source.get('record_successor_node_id') != node['id']
            or source.get('owner') != node['owner'] or source.get('task_id') != task['id']
            or origin != {'source_task_id': task['id'], 'source_node_id': source['id'],
                'project_id': source.get('record_project_id'), 'execution_id': source.get('record_execution_id')}
            or any(not node.get(k) or node[k] != source.get(k) for k in ('record_project_id', 'record_execution_id'))
            or not binding.get('dispatch_id') or binding['dispatch_id'] == previous.get('dispatch_id')
            or any(not binding.get(k) or str(binding[k]).removeprefix('thread:') !=
                   str(previous.get(k, '')).removeprefix('thread:') for k in ('holder_id', 'executor_ref', 'coordinator_ref'))
            or binding.get('received_at') != node.get('created') or binding.get('last_seen_at') != node.get('created')
            or previous['exit_acknowledged_at'] > node.get('created', 0)
            or any(l['node_id'] == source['id'] for l in state['leases'].values())):
        return False
    return True


def current_action(action, state, lease_nodes):
    if action.get('lease_id') in state['leases']:
        return True
    nid = action_node_owner(lease_nodes, action.get('node_id'), action.get('lease_id'))
    node = state['nodes'].get(nid)
    if not node or node['state'] in TERMINAL:
        return False
    task = state['tasks'].get(node['task_id'])
    if not task or executor_exited(node, task):
        return False
    attempts = node.get('attempts') or []
    latest = attempts[-1].get('lease_id') if attempts else None
    return not action.get('lease_id') or action['lease_id'] == latest


def durable_report(root, node, state, ancestors=frozenset()):
    """A saved job can survive restart; this proves recoverability, not publication.

    Callers must separately fence new workers and count actual report writers.
    No result bodies are needed to prove that the existing callback can retry.
    """
    try:
        if (node['id'] in ancestors or node['state'] not in TERMINAL
                or node.get('session_removed') or node.get('report_deferred_deleted')
                or any(l['node_id'] == node['id'] and not lease_exited(l) for l in state['leases'].values())
                or not (never_started(node) or cancelled_unclaimed(node, state) or inactive_native_generation(node, state)
                        or executor_exited(node, state['tasks'][node['task_id']]))):
            return False
        children = node.get('child_ids') or []
        if children and not node.get('record_project_id'):
            return all(state['nodes'][cid].get('parent_id') == node['id']
                       and state['nodes'][cid]['task_id'] == node['task_id']
                       and state['nodes'][cid]['owner'] == node['owner']
                       and durable_report(root, state['nodes'][cid], state, ancestors | {node['id']})
                       for cid in children)
        owner, pid, eid = node['owner'], node['record_project_id'], node['record_execution_id']
        if (not re.fullmatch(r'[a-f0-9]{64}', owner)
                or any(not re.fullmatch(r'[a-zA-Z0-9_-]+', v) for v in (pid, eid))):
            return False
        directory = root / 'sessions' / owner / 'projects' / pid
        project = json.loads((directory / 'metadata.json').read_text())
        return (project.get('id') == pid and project.get('ui_execution_id') == eid
                and type(project.get('ui_execution_revision')) is int
                and (directory / 'ui-executions' / eid / 'cases.json').is_file())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def classify_activity(root, state, actions=(), task_ids=None, report_workers=()):
    """One read-only explanation for coordinator, UI and admission-aware release.

    A queue is not an executor. A quiet executor is not an exit receipt. Historical
    action receipts remain evidence, but only current execution can stop a restart.
    """
    selected = set(task_ids) if task_ids is not None else set(state['tasks'])
    nodes = {key: n for key, n in state['nodes'].items() if n['task_id'] in selected}
    result = {key: [] for key in ('blockers', 'waiting', 'reports', 'residuals')}
    lease_nodes = execution_lease_nodes(state)
    actions = [a for a in actions if current_action(a, state, lease_nodes)]
    unresolved = {action_node_owner(lease_nodes, a.get('node_id'), a.get('lease_id')) for a in actions}
    leases = {}
    for lease in state['leases'].values():
        leases.setdefault(lease['node_id'], []).append(lease)
    def add(bucket, node, code, reason, next_action, category=None, **extra):
        binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
        result[bucket].append({'category': category or bucket, 'task_id': node['task_id'],
            'node_id': node['id'], 'title': node.get('title', ''), 'code': code, 'reason': reason,
            'next_action': next_action, 'executor_ref': binding.get('executor_ref', ''),
            'coordinator_ref': binding.get('coordinator_ref', ''), **extra})
    for node in nodes.values():
        task = state['tasks'][node['task_id']]
        held = leases.get(node['id'], [])
        for lease in held:
            if not lease_exited(lease):
                add('blockers', node, 'execution_channel_open', '原执行者、浏览器或辅助通道尚未确认退出',
                    '由原执行者完成实际退出和交还', 'channels', reference_id=lease['id'])
        binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
        pure = bool(node.get('child_ids') and never_started(node))
        inactive = cancelled_unclaimed(node, state) or inactive_native_generation(node, state)
        waiting = (node['state'] == 'queued' and not held and
                   (never_started(node) or dormant_native_continuation(node, state, unresolved)
                    or unclaimed_native_resume(node, state)
                    or (task.get('execution_route') != 'native_browser' and not node.get('native_browser'))))
        if inactive:
            add('residuals', node, 'unclaimed_generation_cancelled', '原轮已停止，当前派发代次未领取；旧执行代次已交还',
                '保留原结果和取消事实，不恢复旧派发')
        elif waiting:
            add('waiting', node, 'queue_wait', node.get('resource_wait', {}).get('reason') or
                node.get('reason') or '尚未开始执行，保留原等待顺位', '条件变化后沿原总调度续接')
        elif (not pure and not held and not executor_exited(node, task)
              and not inactive
              and not (node['state'] in TERMINAL and never_started(node))
              and not node.get('session_removed')):
            add('blockers', node, 'executor_exit_unknown', '原执行代次尚无确切退出依据',
                '原总调度核对当前代次，正常等待不按时间终止', 'rounds')
        for control in node.get('executor_controls', {}).values():
            if control.get('state') not in {'pending', 'received'}:
                continue
            stale = executor_exited(node, task) and control_obsolete(control, binding)
            add('residuals' if stale else 'blockers', node, 'obsolete_control' if stale else 'control_ack_pending',
                '当前代次已退出，旧控制标记尚未清理' if stale else '原控制指令尚未收到退出回执',
                '原总调度清理标记' if stale else '核对原控制回执', 'acknowledgements', reference_id=control['id'])
        if node['id'] in report_workers:
            add('blockers', node, 'report_writer_active', '原报告正在处理或写入', '等待原报告处理完成', 'finalizations')
        elif node.get('finalization_pending') or node.get('native_report_pending'):
            if durable_report(root, node, state):
                add('reports', node, 'saved_report_pending', '原执行已退出，已保存结果的报告待整理或重试',
                    '保留原请求和结果，沿原报告入口完成')
            elif published_settlement(root, node, state):
                add('residuals', node, 'published_marker', '原报告已发布，收尾标记尚未清理', '原总调度清理标记')
            elif (dormant_native_report(root, node, state, allow_completed_earlier_finish=True)
                  or dormant_aggregate_report(root, node, state) or stopped_split_is_idle(root, node, state)):
                add('reports', node, 'saved_report_pending', '原执行已退出，已保存结果的报告待整理或重试',
                    '保留原请求和结果，沿原报告入口完成')
            else:
                add('blockers', node, 'report_state_unknown', '收尾标记的原记录或退出依据尚未核实',
                    '核对原记录、退出及报告请求', 'finalizations')
    # Missing ownership is not proof of a closed physical channel. Only the
    # global release view can expose unattributed state, never another owner UI.
    if task_ids is None:
        for lease in state['leases'].values():
            if lease['node_id'] not in nodes and not lease_exited(lease):
                add('blockers', {'id': None, 'task_id': None}, 'channel_owner_unknown',
                    '实际通道的原节点归属缺失', '核对原租约归属和真实退出', 'channels', reference_id=lease['id'])
    for receipt in state.get('direct_settlements', {}).values():
        node = nodes.get(receipt.get('node_id'))
        if (node or task_ids is None) and receipt.get('ack_required') is not False and not receipt.get('local_ack_at'):
            add('blockers', node or {'id': None, 'task_id': None}, 'settlement_ack_pending', '原交还回执尚未确认', '核对原交还回执',
                'acknowledgements', reference_id=receipt.get('id') or receipt.get('lease_id'))
    for action in actions:
        nid = action_node_owner(lease_nodes, action.get('node_id'), action.get('lease_id'))
        node = nodes.get(nid)
        if not node:
            lease = state['leases'].get(action.get('lease_id'))
            linked = nodes.get(lease.get('node_id')) if lease else None
            if linked or (lease and task_ids is None):
                add('blockers', linked or {'id': None, 'task_id': None}, 'operation_owner_unknown',
                    '当前租约的未确认操作归属缺失或冲突', '核对原操作及归属，不重复执行',
                    'acknowledgements', reference_id=action.get('id'))
            continue
        add('blockers', node, 'operation_unknown', '本执行代次的原操作结果尚未核实',
            '只核实原操作，不重复执行', 'acknowledgements', reference_id=action.get('id'))
    for source in state['nodes'].values():
        for event in source.get('native_handoffs', {}).values():
            notices = [event, *(event.get('continuations') or ([event['continuation']] if event.get('continuation') else []))]
            for notice in notices:
                claim = notice.get('claim_arguments') or {}
                node = nodes.get(claim.get('node_id') or notice.get('node_id') or source['id'])
                if not node or source.get('owner') != node.get('owner'):
                    continue
                status = notice.get('delivery_state')
                if status not in {'pending', 'waiting_resources', 'blocked', 'unbound', 'sending', 'unknown', 'sent'}:
                    continue
                binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
                stale = bool(claim and (claim.get('dispatch_id') != (binding.get('dispatch_id') or binding.get('id'))
                    or claim.get('holder_id') != binding.get('holder_id')))
                # Even stale unknown sends retain their receipt; they cannot
                # authorize a new claim, but must not be resent or fabricated.
                if stale:
                    add('residuals', node, 'obsolete_handoff', '通知绑定已被当前代次替代', '撤销旧通知，不重发',
                        reference_id=notice.get('id') or event['id'])
                elif status in {'sending', 'unknown'} or (status == 'sent' and notice is not event):
                    add('blockers', node, 'handoff_unknown', '原续接通知尚未确认消费', '核对原通知和原执行代次，不重复发送',
                        'acknowledgements', reference_id=notice.get('id') or event['id'])
                elif status != 'sent':
                    add('waiting', node, 'handoff_pending', '原条件或交接通知待处理', '原总调度按条件变化处理原通知',
                        reference_id=notice.get('id') or event['id'])
    for obj in state.get('cleanup_objects', {}).values():
        node = nodes.get(obj.get('source_node_id'))
        if (node or task_ids is None) and obj.get('state') in {'creating', 'cleaning', 'unknown'}:
            add('blockers', node or {'id': None, 'task_id': None}, 'cleanup_operation_unknown', '原业务清理操作尚未核实',
                '核对原对象与原尝试，不再次删除', 'acknowledgements', reference_id=obj['id'])
    blockers = result['blockers']
    result['summary'] = {'rounds': len({r['task_id'] for r in blockers if r['category'] == 'rounds'}),
        **{k: sum(r['category'] == k for r in blockers) for k in ('channels', 'finalizations', 'acknowledgements')},
        'waiting': len(result['waiting']), 'dormant_reports': len(result['reports']), 'residuals': len(result['residuals'])}
    return result


def activity(root, details=False, admission=False):
    postgres = bool(os.environ.get('API_TEST_DB_HOST'))
    if postgres:
        # Standalone candidate probe: the old image may not have new package
        # helpers. Never fall back to retained SQLite after a PostgreSQL cutover.
        import psycopg
        connection = psycopg.connect(host=os.environ['API_TEST_DB_HOST'],
            port=int(os.environ.get('API_TEST_DB_PORT', '5432')),
            dbname=os.environ.get('API_TEST_DB_NAME', 'veriq'), user=os.environ.get('API_TEST_DB_USER', 'veriq'),
            password=Path(os.environ['API_TEST_DB_PASSWORD_FILE']).read_text().rstrip('\r\n'), connect_timeout=10)
        connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        connection.read_only = True
    else:
        path = root / 'orchestration.sqlite3'
        if not path.exists():
            return {'rounds': 0, 'channels': 0, 'finalizations': 0, 'acknowledgements': 0}
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    with connection as db:
        db.execute('BEGIN')
        state = read_activity_state(db, postgres)
        # Metadata and indexed action states must describe the same snapshot.
        # Never read large history results or instantiate/migrate a Controller.
        unsettled_node_ids = set()
        actions = []
        lease_nodes = execution_lease_nodes(state)
        terminal = {'operations': ('confirmed', 'not_sent'),
                    'direct_commands': ('completed', 'blocked', 'confirmed', 'not_sent', 'cancelled')}
        for kind, ended in terminal.items():
            actions.extend(item for item in state.get(kind, {}).values() if item.get('state') not in ended)
            unsettled_node_ids.update(action_node_owner(lease_nodes, item.get('node_id'), item.get('lease_id'))
                                      for item in state.get(kind, {}).values()
                                      if item.get('state') not in ended)
        if postgres or db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='state_history'").fetchone():
            for kind, ended in terminal.items():
                if postgres:
                    placeholders = ','.join('%s' for _ in ended)
                    query = ("SELECT key,meta::json->>'node_id',meta::json->>'lease_id',meta::json->>'state' FROM state_history WHERE kind=%s "
                             "AND COALESCE(meta::json->>'state','') NOT IN (" + placeholders + ")")
                else:
                    placeholders = ','.join('?' for _ in ended)
                    query = ("SELECT key,json_extract(meta,'$.node_id'),json_extract(meta,'$.lease_id'),json_extract(meta,'$.state') FROM state_history WHERE kind=? "
                             "AND COALESCE(json_extract(meta,'$.state'),'') NOT IN (" + placeholders + ")")
                for key, node_id, lease_id, status in db.execute(query, (kind, *ended)):
                    unsettled_node_ids.add(action_node_owner(lease_nodes, node_id, lease_id))
                    actions.append({'id': key, 'node_id': node_id, 'lease_id': lease_id, 'state': status})
    if state.get('version') != 1:
        raise ValueError('Unknown orchestration state version; release deferred')
    if admission:
        classified = classify_activity(root, state, actions)
        return classified if details else classified['summary']
    leases = state['leases'].values()
    by_node = {l['node_id']: l for l in leases}
    def exited(lease):
        return (lease.get('executor_stopped') is True and lease.get('browser_stopped') is True
                and all(c.get('state') == 'exited' for c in lease.get('auxiliary_channels', {}).values()))
    def exists(node):
        owner, pid = node['owner'], node.get('record_project_id') or node['project_id']
        if not re.fullmatch(r'[a-f0-9]{64}', owner) or not re.fullmatch(r'[a-zA-Z0-9_-]+', pid):
            raise ValueError('Invalid session identity; release deferred')
        return (root / 'sessions' / owner / 'projects' / pid / 'metadata.json').is_file()
    rounds = set()
    finalizations = 0
    dormant_reports = 0
    acknowledgements = 0
    for node in state['nodes'].values():
        lease = by_node.get(node['id'])
        live = exists(node)
        if (live and (node.get('finalization_pending') or node.get('native_report_pending'))
                and not published_settlement(root, node, state)):
            if (dormant_native_report(root, node, state, allow_completed_earlier_finish=True)
                    or dormant_aggregate_report(root, node, state)
                    or stopped_split_is_idle(root, node, state)):
                dormant_reports += 1
            else:
                finalizations += 1
        acknowledgements += sum(c.get('state') in {'pending', 'received'}
                                for c in node.get('executor_controls', {}).values())
        if node.get('child_ids') or not live or node.get('session_removed'):
            continue
        task = state['tasks'][node['task_id']]
        if (node.get('control_intent', task['intent']) == 'run'
                and node['state'] not in {'completed', 'blocked', 'stopped', 'paused', 'isolated', 'retained'}
                and not (lease and lease.get('resource_hold') and exited(lease))
                and not dormant_native_continuation(node, state, unsettled_node_ids)):
            rounds.add(task['id'])
    acknowledgements += sum(receipt.get('ack_required') is not False and not receipt.get('local_ack_at')
                            for receipt in state.get('direct_settlements', {}).values())
    return {'rounds': len(rounds), 'channels': sum(not exited(l) for l in leases),
            'finalizations': finalizations, 'acknowledgements': acknowledgements,
            **({'dormant_reports': dormant_reports} if dormant_reports else {})}


if __name__ == '__main__':
    print(json.dumps(activity(Path(os.environ.get('API_TEST_DATA_DIR', '/data')).resolve(),
        details=os.environ.get('VERIQ_ACTIVITY_DETAILS') == '1',
        admission=os.environ.get('VERIQ_ACTIVITY_ADMISSION_V1') == '1')))
