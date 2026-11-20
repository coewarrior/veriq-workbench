"""Durable client batching for existing single-command execution hosts.

No browser connection, lease or server permission is replaced. The same server
checks every step; an uncertain submission is queried, never submitted again.
This standard-library module is embedded in the downloadable client.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


def client_capabilities(result):
    if result.get('mode') == 'native_browser' or result.get('execution_host', {}).get('action_transport') == 'native':
        return {**result, 'execution_client': {
            'browser_batch': False, 'action_transport': 'none',
            'guidance': '浏览器动作由桌面 Codex 直接执行：新任务默认 node_repl/Playwright 独立环境，旧在途沿原浏览器。本客户端仅同步账号、用例结果和退出报告，不中转或轮询浏览器动作。'}}
    if isinstance(result.get('execution_host'), dict):
        native = bool(result['execution_host'].get('browser_batch'))
        result = {**result, 'execution_client': {
            'browser_batch': True, 'batch_transport': 'native' if native else 'compatible',
            'browser_check': native, 'snapshot_selector': native,
            'guidance': 'batch steps 沿原账号和浏览器顺序执行；兼容旧执行机无需重启。每步保留原回执，未知或失败停止后续步骤。续接使用返回的 resume_arguments。旧机不支持 check/snapshot_selector，必须保留原实际观察和逐项判定，不能省略断言。'}}
    return result


def batch_path(root, args):
    identity = [args.get(k, '') for k in ('holder_id', 'lease_id', 'request_id')]
    return Path(root) / (hashlib.sha256(json.dumps(identity).encode()).hexdigest() + '.json')


def save_batch(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.batch-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            os.chmod(name, 0o600)
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


@contextlib.contextmanager
def batch_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path)+'.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name == 'nt':
            import msvcrt
            if os.fstat(fd).st_size == 0: os.write(fd, b'0')
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def compatible_batch(send, args, root, single):
    path = batch_path(root, args)
    with batch_lock(path):
        return _compatible_batch(send, args, path, single)


def _compatible_batch(send, args, path, single):
    started = time.monotonic()
    seconds = args.get('wait_seconds', 45)
    prior = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    if args['action'] == 'result':
        if prior is None: raise ValueError('本机没有该批次回执；使用原客户端和回执目录续接')
        plan_args = prior['arguments']
    else:
        plan_args = {k:v for k,v in args.items() if k != 'wait_seconds'}
        if prior and prior['arguments'] != plan_args:
            raise ValueError('同一批次 request_id 不能改变步骤、账号或参数')
    plan = plan_args.get('parameters', {}).get('steps')
    if not isinstance(plan, list) or not plan: raise ValueError('batch 需要非空 steps')
    required = {'navigate':('url',), 'click':('selector',), 'fill':('selector','value'),
                'press':('selector','key'), 'select':('selector','value'), 'wait':('selector',),
                'upload':('selector',), 'switch_tab':('page_index',)}
    allowed = set(required) | {'snapshot','screenshot','back','tabs'}
    seen = set()
    for step in plan:
        if not isinstance(step, dict) or step.get('action') not in allowed:
            raise ValueError('旧执行机兼容批次仅支持已有普通动作；check 等原生新动作需执行机声明支持，不能省略断言')
        identity, values = step.get('id'), step.get('parameters', {})
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise ValueError('每步必须有独立且不重复的 id')
        if not isinstance(values, dict) or any(k not in values for k in required.get(step['action'], ())):
            raise ValueError('batch 步骤参数不完整')
        if 'snapshot_selector' in values or 'expect' in values:
            raise ValueError('旧执行机不能执行局部快照或 check；保留实际观察与原断言')
        if values.get('response','full') not in {'full','summary'}: raise ValueError('response 必须为 full/summary')
        seen.add(identity)
    if prior is None:
        prior = {'arguments': plan_args, 'steps': [], 'transport': 'compatible'}
        save_batch(path, prior)
    resume = {k:plan_args[k] for k in ('holder_id','lease_id','request_id')}
    resume['action'] = 'result'
    calls = 0
    def counted(values):
        nonlocal calls
        calls += 1
        return send(values)
    for index, step in enumerate(plan):
        if index < len(prior['steps']):
            item = prior['steps'][index]
            receipt = item.get('receipt', {})
            if receipt.get('state') == 'completed':
                observed = receipt.get('result') or {}
                if observed.get('requires_exclusive') or observed.get('assertion_passed') is False: break
                continue
            if receipt.get('state') in {'blocked','unknown'}: break
            query = {**resume, 'request_id': item['request_id']}
        else:
            request = 'batch-' + hashlib.sha256((plan_args['request_id']+'\0'+step['id']).encode()).hexdigest()
            item = {'id':step['id'], 'request_id':request}
            prior['steps'].append(item)
            # Persist before sending. If this process exits or loses a reply,
            # the next invocation only queries this exact submitted command.
            save_batch(path, prior)
            query = {k:v for k,v in plan_args.items() if k not in {'parameters','browser_action','request_id'}}
            query.update(action='browser', request_id=request, browser_action=step['action'],
                         parameters={k:v for k,v in step.get('parameters',{}).items() if k!='response'})
        query['wait_seconds'] = max(0, seconds-(time.monotonic()-started))
        try:
            receipt = single(counted, query)
        except (OSError, ValueError) as exc:
            # No arbitrary transport text (or input secrets) in the public receipt.
            item['transport_uncertain'] = True
            item['error_type'] = type(exc).__name__
            save_batch(path, prior)
            break
        item['receipt'] = receipt
        item.pop('transport_uncertain', None)
        save_batch(path, prior)
        observed = receipt.get('result') or {}
        if (receipt.get('state') != 'completed' or observed.get('requires_exclusive')
                or observed.get('assertion_passed') is False): break
        if time.monotonic()-started >= seconds: break
    completed = len(prior['steps']) == len(plan) and all(s.get('receipt',{}).get('state')=='completed' for s in prior['steps'])
    last = prior['steps'][-1] if prior['steps'] else {}
    state = 'completed' if completed else last.get('receipt',{}).get('state','unknown')
    halted = state in {'unknown','blocked'} or bool((last.get('receipt',{}).get('result') or {}).get('requires_exclusive')) or (last.get('receipt',{}).get('result') or {}).get('assertion_passed') is False
    if not completed and state=='completed' and not halted: state='running'
    result = {'state':state, 'request_id':plan_args['request_id'], 'batch_transport':'compatible',
              'steps':prior['steps'], 'unexecuted_steps':[s['id'] for s in plan[len(prior['steps']):]],
              'client_wait':{'elapsed_seconds':round(time.monotonic()-started,3), 'http_calls':calls,
                             'pending':not completed and not halted}}
    if not completed: result['client_wait']['resume_arguments']=resume
    if halted: result['stopped_at']=last.get('id')
    for key in ('requires_exclusive', 'business_failure', 'continue_exploration'):
        if key in (last.get('receipt',{}).get('result') or {}):
            result[key] = last['receipt']['result'][key]
    return result
