"""Finish the existing UI round once, after the existing executor settles.

No browser/business action is performed here. Saved outcomes stay authoritative.
The intent survives HTTP disconnects and is consumed by normal host settlement.
"""
import hashlib
import json
import math
import statistics
import time
from contextlib import nullcontext
from uuid import UUID
from . import ui_records, ui_closeout
from .orchestration import Conflict


def status(project):
    intent = project.get('ui_finish_request') or {}
    if not intent or intent.get('execution_id') != project.get('ui_execution_id'):
        return None
    if project.get('ui_execution_revision',intent['revision']) != intent['revision']:
        return {'phase':'changed','pending':False,'request_id':intent['request_id'],
                'execution_id':intent['execution_id'],'revision':project['ui_execution_revision'],
                'message':'本轮结果已更新，旧结束回执不代表新结果；沿用当前记录提交最终总结。'}
    if intent.get('error'):
        return {'phase':'failed','pending':False,'request_id':intent['request_id'],
                'execution_id':intent['execution_id'],'revision':intent['revision'],'error':intent['error']}
    if intent.get('result'):
        return intent['result']
    pending = {
        'phase': 'settling', 'pending': True, 'execution_id': intent['execution_id'],
        'revision': intent['revision'], 'request_id': intent['request_id'],
        'next_action': 'get_workflow_status',
        'message': '最后一批结果已保存；平台等待原执行器退出后生成最终报告，不需要再次保存或发布。',
    }
    return {**pending, **intent.get('native_closeout', {})}


def _native_closeout(snapshot, nodes):
    """Describe real native cleanup work; never manufacture an exit receipt."""
    native_tasks = {task['id'] for task in snapshot.get('tasks', [])
                    if task.get('execution_route') == 'native_browser'}
    leases = {lease['node_id']: lease for lease in snapshot['leases']}
    sessions, modules = [], []
    for node in nodes:
        lease = leases.get(node['id'])
        if node['task_id'] not in native_tasks and not node.get('native_browser'):
            continue
        if (lease and lease.get('resource_hold') and lease.get('executor_stopped')
                and lease.get('browser_stopped')):
            # A truthful final report can retain a known resource hold.
            continue
        receipt = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
        exited = bool(receipt.get('exit_acknowledged_at'))
        browser_stopped = (lease.get('browser_stopped') is True if lease else
                           bool(node.get('native_browser_stopped') or not node.get('attempts')))
        has_executor = bool(node.get('direct_holder') or receipt.get('holder_id')
                            or receipt.get('executor_ref'))
        if lease or (has_executor and (not exited or not browser_stopped)):
            ref = receipt.get('executor_ref', '')
            try:
                thread_url = 'codex://threads/' + str(UUID(ref.removeprefix('thread:')))
            except (ValueError, AttributeError, TypeError):
                thread_url = ''
            sessions.append({
                'node_id': node['id'], 'task_id': node['task_id'], 'title': node['title'],
                'lease_id': lease['id'] if lease else None,
                'holder_id': node.get('direct_holder') or receipt.get('holder_id'),
                'executor_ref': ref, 'thread_url': thread_url,
                'executor_exit_confirmed': exited, 'browser_stopped': browser_stopped,
                'accounts_released': lease is None,
                'exit_confirmation_source': node.get('native_exit_evidence', {}).get('source'),
                'desktop_api_cancelled': False,
                'next_action': 'finish_after_browser_stopped' if lease else 'finish_unallocated',
            })
        elif node['state'] not in {'completed', 'blocked', 'stopped'}:
            modules.append({
                'node_id': node['id'], 'task_id': node['task_id'], 'title': node['title'],
                'state': node['state'], 'next_action': 'finish_unallocated',
            })
    if not sessions and not modules:
        return {}
    return {
        'mode': 'native_browser', 'native_closeout_required': True,
        'manual_stop_required': bool(sessions),
        'required_sessions': sessions, 'required_modules': modules,
        'next_action': 'desktop_manual_stop' if sessions else 'finish_unallocated',
        'message': ('结果已保存，但原生模块尚未完成真实退出或交还。由原会话完成本任务浏览器收尾后提交 finish；'
                    'S1 停止则由用户停止列出的桌面会话并确认。未接单模块按原入口结束并保留未执行结果。'
                    '平台不会取消桌面会话，也不会通过轮询代替退出确认。'),
    }


def complete(service, owner, pid):
    completion_started = time.monotonic()
    store = service.store
    with store._lock:
        project = store.get_project(owner, pid)
        intent = project.get('ui_finish_request') or {}
        if not intent or intent.get('execution_id') != project.get('ui_execution_id'):
            return None
        if intent.get('result'):
            return intent['result']
        snap = service.controller.snapshot(owner)
        nodes = [n for n in snap['nodes'] if not n.get('child_ids') and
                 (n.get('record_project_id') == pid or n['project_id'] == pid)]
        native_closeout = _native_closeout(snap, nodes)
        if native_closeout != intent.get('native_closeout', {}):
            if native_closeout:
                intent['native_closeout'] = native_closeout
            else:
                intent.pop('native_closeout', None)
            store.update_project(owner, pid, {'ui_finish_request': intent})
            project = {**project, 'ui_finish_request': intent}
        if native_closeout:
            return status(project)
        held_nodes={l['node_id'] for l in snap['leases'] if l.get('resource_hold') and l.get('executor_stopped')}
        if any(n['state'] not in {'completed', 'blocked', 'stopped'} and n['id'] not in held_nodes for n in nodes):
            return status(project)
        if any(l['node_id'] in {n['id'] for n in nodes} and not l.get('resource_hold') for l in snap['leases']):
            return status(project)
        record = ui_records.load(store, owner, pid, intent['execution_id'])
        if record['revision'] != intent['revision']:
            # A later correction must not be overwritten or described by an old summary.
            return {'phase': 'changed', 'pending': False, 'execution_id': record['id'],
                    'revision': record['revision'], 'message': '结束请求后用例发生变化；请按新结果更新总结，不重跑业务。'}
        publish_started = time.monotonic()
        result = ui_records._publish(store, owner, project, record['id'], intent['title'], intent['summary'],
                                     notify=False, _record=record)
        store.update_project(owner, pid, {'ui_final_report': {
            'execution_id': record['id'], 'revision': record['revision']}})
        from .wecom import WeCom
        result['notification'] = WeCom(store).auto_report(owner, pid, result['report']['id'], 'reports')
        result.update(phase='published', pending=False, execution_id=record['id'],
                      revision=record['revision'], request_id=intent['request_id'],
                      execution_settlement={'released': not bool(held_nodes & {n['id'] for n in nodes}),
                          'resource_holds':[{'node_id':l['node_id'],'reason':l.get('hold',{}).get('reason','')}
                              for l in snap['leases'] if l.get('resource_hold') and l['node_id'] in {n['id'] for n in nodes}]},
                      completed_at=ui_records.now())
        result['processing_timing'] = {**intent.get('processing_timing', {}),
            'report_and_notification_seconds': round(time.monotonic() - publish_started, 6),
            'completion_wait_and_checks_seconds': round(publish_started - completion_started, 6),
            'basis': '平台实际处理分段；completion_total_seconds 含最终持久化，其他分段不可再相加到总耗时。最终写入耗时仅由本次实际返回回执提供，不为补计时再写报告；不包含 Codex、业务清理或浏览器退出等待。'}
        tool_started = time.monotonic()
        result['tool_timing'] = tool_timing(service, owner, [n['id'] for n in nodes])
        result['processing_timing']['tool_timing_read_seconds'] = round(time.monotonic() - tool_started, 6)
        progress_started = time.monotonic()
        from .mcp_progress import PHASES
        message = '最终报告已保存；' + (
            '业务影响待核实的账号仍保留，未验证部分已列明。' if result['execution_settlement']['resource_holds'] else '执行资源已交还。')
        event = {'phase': 'completed', 'label': PHASES['completed'], 'message': message, 'updated_at': time.time()}
        history = project.get('mcp_progress', {}).get('history', [])
        if history and history[-1]['phase'] == 'completed':
            history = history[:-1]
        progress = {**event, 'history': (history + [event])[-30:]}
        result['processing_timing']['progress_prepare_seconds'] = round(time.monotonic() - progress_started, 6)
        intent.pop('error',None)
        intent['result'] = result
        result['processing_timing']['completion_before_commit_seconds'] = round(time.monotonic() - completion_started, 6)
        commit_started = time.monotonic()
        # The final marker must precede WeCom's persisted-state check above.
        # Completion progress and its result can safely commit together here.
        store.update_project(owner, pid, {'mcp_progress': progress, 'ui_finish_request': intent})
        result['processing_timing']['final_commit_seconds'] = round(time.monotonic() - commit_started, 6)
        result['processing_timing']['completion_total_seconds'] = round(time.monotonic() - completion_started, 6)
        return result


def tool_timing(service, owner, node_ids):
    """Server command times only; never mislabel them as model/business duration."""
    values = []
    if node_ids:
        with service.controller.connect() as db:
            rows = db.execute("SELECT meta FROM state_history WHERE kind='direct_commands' "
                "AND meta::json->>'owner'=%s AND meta::json->>'node_id' IN (" +
                ','.join('%s' for _ in node_ids) + ')', [owner, *node_ids]).fetchall()
        values = [json.loads(row[0]) for row in rows]
    elapsed = sorted(v['completed']-v['created'] for v in values
                     if isinstance(v.get('completed'),(int,float)) and v['completed'] >= v['created'])
    return {'measured_commands':len(elapsed),'total_commands':len(values),
            'median_seconds':round(statistics.median(elapsed),3) if elapsed else None,
            'p95_seconds':round(elapsed[math.ceil(.95*len(elapsed))-1],3) if elapsed else None,
            'max_seconds':round(max(elapsed),3) if elapsed else None,
            'basis':'服务端收到浏览器命令至执行机提交结果，含等待和失败；不含模型思考、HTTP往返，不等于业务总耗时。旧命令未记录结束时间时不推算。'}


def begin(service, owner, project, arguments, *, settled_only=False, registration_guard=None):
    # Report-only callers bind the intent atomically to the released generation;
    # materialization stays outside the scheduler write transaction.
    with (registration_guard() if registration_guard else nullcontext(project)) as current:
        pid, reused = _register(service, owner, current, arguments)
    if not settled_only and not reused:
        service.direct.finish_project(owner, pid)
    return complete(service, owner, pid)


def _register(service, owner, project, arguments):
    store = service.store
    pid = project['id']
    eid = project.get('ui_execution_id')
    if not eid or arguments.get('execution_id') not in (None, '', eid):
        raise ValueError('请使用当前已保存的 UI 执行记录结束任务')
    from .task_reports import text_field
    title = text_field(arguments.get('title') or project['title'] + ' · UI 测试报告', '报告标题', 200, True)
    summary = text_field(arguments.get('summary', ''), '报告结论', 30000, False)
    payload = {k: arguments.get(k) for k in ('execution_id', 'title', 'summary', 'cases',
               'revision', 'coverage', 'review_notes', 'scene_outcome', 'experiment', 'evidence_refs')}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    changes = {k: arguments[k] for k in ('coverage', 'review_notes', 'scene_outcome', 'experiment')
               if arguments.get(k) is not None}
    identity_revision = (arguments.get('revision') if arguments.get('cases') or arguments.get('evidence_refs') or changes else
                         ui_records.load(store,owner,pid,eid)['revision'])
    request_id = arguments.get('request_id') or fingerprint + ':' + str(identity_revision)
    old = project.get('ui_finish_request') or {}
    if old.get('execution_id') == eid and old.get('request_id') == request_id:
        if old['fingerprint'] != fingerprint:
            raise Conflict('同一结束 request_id 不能改变结果；修正结果请使用新的 request_id')
        return pid, True
    processing_started = time.monotonic()
    assets = ui_closeout.receipt_assets(service, owner, pid, arguments.get('evidence_refs') or [])
    evidence_finished = time.monotonic()
    if arguments.get('cases') or changes or assets:
        ui_records.save_cases(store, owner, pid, arguments.get('cases') or [], eid,
            arguments.get('revision'), changes.get('coverage'), changes.get('review_notes'),
            changes.get('scene_outcome'), changes.get('experiment'), refresh_report=False, staged_assets=assets)
    record = ui_records.load(store, owner, pid, eid)
    preparation_finished = time.monotonic()
    intent = {'execution_id': eid, 'revision': record['revision'], 'request_id': request_id,
              'fingerprint': fingerprint, 'title': title,
              'summary': summary or ui_closeout.summary(record), 'requested_at': ui_records.now(),
              'processing_timing': {'receipt_packaging_seconds': round(evidence_finished-processing_started, 6),
                  'result_save_seconds': round(preparation_finished-evidence_finished, 6)}}
    store.update_project(owner, pid, {'ui_finish_request': intent})
    return pid, False
