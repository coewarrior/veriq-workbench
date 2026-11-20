"""Client-side receipt waiting. No model turns, business retries or server locks.

The no-install client embeds this module via ci/export-agent-tools.py.
"""
import math
import time
from .direct_batch import batch_path, client_capabilities, compatible_batch, save_batch


def direct_call_and_wait(send, arguments, *, batch_root=None):
    seconds = arguments.get('wait_seconds', 45)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 <= seconds <= 50:
        raise ValueError('wait_seconds 为 0–50 秒')
    batch = arguments.get('action') == 'browser' and arguments.get('browser_action') == 'batch'
    resume = (batch_root is not None and arguments.get('action') == 'result'
              and batch_path(batch_root, arguments).exists())
    if batch and batch_root is not None:
        if any(not isinstance(arguments.get(k), str) or not arguments[k] for k in ('holder_id','lease_id','request_id')):
            raise ValueError('batch 需要原 holder_id、lease_id 和稳定 request_id')
        # Existing local receipts own continuation even if the host is upgraded.
        if not batch_path(batch_root, arguments).exists():
            # Capabilities are stable for the lifetime of a lease. An upgrade
            # cannot move an active lease; every browser submission still checks
            # its live authority server-side. Do not re-fetch the full record
            # just to discover the same native-batch bit on every batch.
            import hashlib, json
            from pathlib import Path
            identity = hashlib.sha256((arguments['holder_id']+'\0'+arguments['lease_id']).encode()).hexdigest()
            capability_file = Path(batch_root)/('capabilities-'+identity+'.json')
            if capability_file.exists():
                context = json.loads(capability_file.read_text())
            else:
                context = send({k:v for k,v in {**arguments,'action':'context'}.items()
                                if k in {'action','holder_id','lease_id'}})
                save_batch(capability_file,{'execution_host':context.get('execution_host',{})})
            if context.get('mode') == 'native_browser' or context.get('execution_host', {}).get('action_transport') == 'native':
                raise ValueError('原生浏览器直接使用 cua 工具；本客户端不接收 browser batch')
            if context.get('execution_host', {}).get('browser_batch'):
                return _single_direct_call_and_wait(send, arguments)
        return compatible_batch(send, arguments, batch_root, _single_direct_call_and_wait)
    if resume:
        return compatible_batch(send, arguments, batch_root, _single_direct_call_and_wait)
    result = _single_direct_call_and_wait(send, arguments)
    return client_capabilities(result) if batch_root is not None else result


def _single_direct_call_and_wait(send, arguments):
    """Send once; poll the same receipt, claim or idempotent settlement only."""
    args = dict(arguments)
    seconds = args.pop('wait_seconds', 45)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 <= seconds <= 50:
        raise ValueError('wait_seconds 为 0–50 秒；仅控制本次工具等待，0 立即返回，不改变任务超时或容量。')
    action = args.get('action')
    started = time.monotonic()
    calls = 1
    # A lost submission is never retried here. The caller retains its original ID.
    result = send(args)
    def resource_wait(value):
        return action == 'claim' and value.get('state') == 'queued' and not value.get('lease_id')

    def parked(value):
        # No browser/account to work with: do not spend a model turn repeatedly
        # polling this queue. The coordinator retains ownership of wake-up.
        return {**value, 'next_action':'end_turn_until_resources', 'resource_wait': {
            **value.get('resource_wait', {}),
            'end_turn': True, 'reason': value.get('reason', 'waiting_for_resources'),
            'resume_arguments': args,
            'instruction': '未取得账号，停止本地领取循环并结束当前轮次；协调者保留原节点和顺位，确认资源可分配后再唤醒原会话。不得反复自唤醒或轮询。',
        }, 'client_wait': {'elapsed_seconds': round(time.monotonic()-started, 3),
                           'http_calls': calls, 'pending': False}}
    if resource_wait(result):
        return parked(result)
    if result.get('mode') == 'native_browser':
        return {**result, 'client_wait': {'elapsed_seconds': round(time.monotonic()-started, 3),
                                        'http_calls': 1, 'pending': False}}
    if action not in {'browser', 'result', 'claim', 'finish'} or seconds == 0:
        return result

    def pending(value):
        if action in {'browser', 'result'}:
            return value.get('state') in {'queued', 'running'}
        if action == 'claim':
            return not resource_wait(value) and not value.get('browser_ready') and value.get('state') in {'queued', 'starting', 'running'}
        return bool(args.get('lease_id')) and not value.get('released') and value.get('state') == 'stopping'

    query = dict(args)
    if action in {'browser', 'result'}:
        query = {key: args[key] for key in ('holder_id', 'lease_id', 'request_id') if key in args}
        query['action'] = 'result'
    error = None
    while pending(result):
        remaining = seconds - (time.monotonic() - started)
        if remaining <= 0:
            break
        # Queue scheduling is heavier than reading one command receipt. Keep
        # its polling modest without making models perform the wait themselves.
        interval = 2 if action == 'claim' else .25 if calls == 1 else .5
        time.sleep(min(interval, remaining))
        if time.monotonic() - started >= seconds:
            break
        calls += 1
        try:
            result = send(query)
        except (ValueError, OSError) as exc:
            # Preserve the last actual receipt, not a fabricated operation failure.
            error = str(exc)
            break
    if resource_wait(result):
        return parked(result)
    waiting = pending(result)
    result = {**result, 'client_wait': {
        'elapsed_seconds': round(time.monotonic() - started, 3),
        'http_calls': calls, 'pending': waiting,
    }}
    if waiting:
        result['client_wait']['resume_arguments'] = query
    if error is not None:
        result['client_wait']['poll_error'] = error
    return result


def lifecycle_call_and_wait(send, action, arguments):
    """Reuse original start/claim/context and finish/status calls without model turns."""
    args = dict(arguments)
    seconds = args.pop('wait_seconds', 45)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 <= seconds <= 50:
        raise ValueError('wait_seconds 为 0–50 秒')
    started = time.monotonic()
    calls = 0
    def invoke(name, values):
        nonlocal calls
        calls += 1
        return send(name, values)
    result = invoke(action, args)  # Never retry the write after a lost response.
    if action == 'start_regression' and args.get('holder_id') and result.get('execution', {}).get('task_id'):
        claim = direct_call_and_wait(lambda values: invoke('direct_session', values), {
            'action': 'claim', 'holder_id': args['holder_id'], 'task_id': result['execution']['task_id'],
            'wait_seconds': max(0, seconds - (time.monotonic() - started))})
        result['claim'] = claim
        if claim.get('browser_ready') or claim.get('account_ready'):
            result['execution_context'] = invoke('direct_session', {
                'action': 'context', 'holder_id': args['holder_id'], 'lease_id': claim['lease_id']})
        result['next_action'] = 'direct_test_session'
    elif action == 'finish_workflow' and result.get('pending') and not (
            result.get('manual_stop_required') or result.get('native_closeout_required')):
        query = {'project_id': args['project_id'], 'finalization_only': True,
                 'request_id': result['request_id']}
        while result.get('pending'):
            remaining = seconds - (time.monotonic() - started)
            if remaining <= 0:
                break
            time.sleep(min(1, remaining))
            if time.monotonic() - started >= seconds:
                break
            try:
                result = invoke('workflow_status', query)
            except (ValueError, OSError) as exc:
                result = {**result, 'poll_error': str(exc)}
                break
    claim = result.get('claim', {})
    claim_pending = bool(claim and not claim.get('resource_wait', {}).get('end_turn') and not claim.get('browser_ready') and not claim.get('account_ready') and claim.get('state') in {'queued','starting','running'})
    manual = bool(result.get('manual_stop_required') or result.get('native_closeout_required'))
    result['client_wait'] = {'elapsed_seconds': round(time.monotonic() - started, 3),
                            'http_calls': calls, 'pending': not manual and bool(result.get('pending') or
                                claim_pending)}
    if claim.get('resource_wait'):
        result['resource_wait'] = claim['resource_wait']
        result['next_action'] = 'end_turn_until_resources'
    if claim_pending:
        result['client_wait']['resume_tool'] = 'direct_test_session'
        result['client_wait']['resume_arguments'] = claim.get('client_wait', {}).get('resume_arguments') or {
            'action':'claim','holder_id':args['holder_id'],'task_id':result['execution']['task_id']}
    if result.get('manual_stop_required'):
        result['next_action'] = 'desktop_manual_stop'
    if action == 'finish_workflow' and result.get('pending') and not manual:
        result['client_wait']['resume_tool'] = 'get_workflow_status'
        result['client_wait']['resume_arguments'] = {'project_id': args['project_id']}
    return result
