#!/usr/bin/env python3
"""API 测试台免安装客户端：Python 3.9+ 标准库；支持 CLI 与 MCP stdio。"""
import argparse
import base64
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import errno
import hashlib
import http.client
import json
import mimetypes
import os
from pathlib import Path
import random
import socket
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import unicodedata

# BEGIN GENERATED DIRECT WAIT
"""Client-side receipt waiting. No model turns, business retries or server locks.

The no-install client embeds this module via ci/export-agent-tools.py.
"""
import math
import time
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

# END GENERATED DIRECT WAIT
# BEGIN GENERATED NATIVE HANDOFF
"""Build the real desktop-tool chain, without impersonating a desktop API.

The downloadable client embeds this helper and template. Generating a script
does not execute it; the caller runs it once in functions.exec where the native
message tool is actually available.
"""
import json


NATIVE_HANDOFF_CAPABILITY = 'native_handoff_exec_v1'
NATIVE_DIRECT_HANDOFF_CAPABILITY = 'native_direct_handoff_exec_v1'
NATIVE_COORDINATOR_WAIT_CAPABILITY = 'native_coordinator_wait_v1'


def bound_handoff_arguments(binding, arguments):
    """Reuse the last successful local binding, never infer exit or timestamps."""
    fields = ('holder_id', 'task_id', 'node_id', 'lease_id', 'project_id', 'execution_id')
    if (not isinstance(binding, dict) or any(not isinstance(binding.get(k), str) or not binding[k] for k in fields)
            or type(binding.get('revision')) is not int or binding['revision'] < 1):
        raise ValueError('收尾使用原生记录的完整 binding-file 和成功保存的 revision')
    result = dict(arguments)
    for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'account_id'):
        if key in binding:
            if key in result and result[key] != binding[key]:
                raise ValueError('收尾参数与原绑定不一致：' + key)
            result[key] = binding[key]
    for key in ('dispatch_id', 'executor_ref'):
        if binding.get(key) and not result.get(key):
            result[key] = binding[key]
    values = dict(result.get('arguments') or {})
    if values.get('final_report') is not None:
        if result.get('action') != 'finish' or values.get('browser_stopped') is not True:
            raise ValueError('合并收尾须先真实停止本任务浏览器，再提交 finish')
        final = dict(values['final_report'])
        for key in ('project_id', 'execution_id', 'revision'):
            if key in final and final[key] != binding[key]:
                raise ValueError('收尾报告与最后保存绑定不一致：' + key)
            final[key] = binding[key]
        values['final_report'] = final
    if values.get('publish_saved') is True:
        values['publication_binding'] = {key: binding[key] for key in ('project_id', 'execution_id', 'revision')}
    result['arguments'] = values
    return result


def handoff_arguments(arguments):
    """Opt the new executable entry into direct delivery; bare calls stay legacy."""
    if arguments.get('action') != 'finish':
        return arguments
    values = arguments.get('arguments') or {}
    if 'result' in values and not isinstance(values['result'], str):
        raise ValueError('arguments.result 使用 passed/failed/partial/blocked/not_run 字符串；统计保留在用例结果中，尚未发送收尾请求')
    return {**arguments, 'arguments': {**(arguments.get('arguments') or {}),
                                      'handoff_route': 'direct_successors'}}


def native_mcp_script(template, arguments):
    if arguments.get('action') not in {'finish', 'dispatch'} or (
            arguments.get('action') == 'dispatch' and not (arguments.get('arguments') or {}).get('handoff_ack')):
        raise ValueError('交接编排仅接受原 finish 或 dispatch 参数')
    return template + '\n' + 'const nativeArguments = ' + json.dumps(handoff_arguments(arguments), ensure_ascii=False) + ';\n' + native_mcp_transport() + r"""
text(await completeNativeHandoff(callNative, nativeArguments,
  tools.mcp__codex_app__send_message_to_thread));
"""


def native_mcp_transport():
    return r"""
const nativeTools = ALL_TOOLS.filter(item => item.name.endsWith("__direct_test_session"));
if (nativeTools.length !== 1) throw new Error("先发现当前测试台 direct_test_session 工具，再执行原编排；不能猜工具名称");
const callNative = async args => {
  const result = await tools[nativeTools[0].name](args);
  if (result?.isError) throw new Error("原平台调用失败；不发送或重发");
  if (result?.structuredContent) return result.structuredContent;
  for (const item of result?.content || []) {
    if (item.type === "text") {
      try { return JSON.parse(item.text); } catch (_) {}
    }
  }
  if (result && typeof result === "object" && !result.content) return result;
  throw new Error("平台回执格式未知；不发送或重发");
};
"""

def native_handoff_script(template, command, arguments, receipt_directory=None, initial_result=None):
    action = arguments.get('action')
    if action not in {'finish', 'dispatch'} or (
            action == 'dispatch' and not (arguments.get('arguments') or {}).get('handoff_ack')):
        raise ValueError('原生交接编排仅接受原 finish 或包含 handoff_ack 的原 dispatch')
    return template + '\n' + native_cli_transport(command, receipt_directory) + (
        'const nativeArguments = ' + json.dumps(handoff_arguments(arguments), ensure_ascii=False) + ';\n'
        'const initialResult = ' + json.dumps(initial_result, ensure_ascii=False) + ';\n'
        'text(await completeNativeHandoff(callNative, nativeArguments, '
        'tools.mcp__codex_app__send_message_to_thread, initialResult));\n')


def native_cli_transport(command, receipt_directory=None):
    # command is an argv array from this running client, never a server-supplied
    # shell command. Quote every argument independently before invoking the CLI.
    import tempfile
    control_directory = str(receipt_directory) if receipt_directory else tempfile.mkdtemp(prefix='native-control-')
    template = globals().get('NATIVE_CONTROL_TEMPLATE')
    if template is None:
        from pathlib import Path
        template = (Path(__file__).parent / 'static/native-control-read.js').read_text()
    return template + '\n' + r'''
const nativeCommand = ''' + json.dumps(command, ensure_ascii=False) + r''';
const receiptDirectory = ''' + json.dumps(str(receipt_directory) if receipt_directory else None) + r''';
const controlDirectory = ''' + json.dumps(control_directory) + r''';
let controlSequence = 0;
const shellQuote = value => "'" + String(value).replace(/'/g, "'\\''") + "'";
const callNative = async args => {
  const phase = args.arguments?.handoff_delivery?.state;
  const receiptFile = receiptDirectory && receiptDirectory + '/' +
    (phase ? 'delivery-' + phase : args.record_action === 'publish' ? 'handoff-publication-result' : args.action === 'dispatch' ? 'ack-server-result' : 'closeout-result') + '.json';
  const controlFile = controlDirectory + '/control-' + Date.now() + '-' + (++controlSequence) + '.json';
  const command = [...nativeCommand, "--args", JSON.stringify(args), '--control-result-file', controlFile,
    ...(receiptFile ? ['--receipt-file', receiptFile] : [])].map(shellQuote).join(" ");
  let execution = await tools.exec_command({cmd: command, max_output_tokens: 12000, yield_time_ms: 10000});
  let output = execution.output;
  while (execution.session_id && execution.exit_code == null) {
    execution = await tools.write_stdin({session_id: execution.session_id, chars: "",
      max_output_tokens: 12000, yield_time_ms: 1000});
    output += execution.output;
  }
  if (execution.exit_code !== 0) {
    throw new Error("原平台调用未取得确定回执；保留原事件，不自动重发");
  }
  return await nativeReadControl(tools, nativeCommand.slice(0, -2), controlFile);
};
'''


def native_coordinator_script(template, handoff_template, arguments, *, command=None):
    from uuid import UUID
    config = dict(arguments)
    for key in ('holder_id', 'coordinator_ref'):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError('协调等待需原 holder_id 与真实 coordinator_ref')
    UUID(config['coordinator_ref'].removeprefix('thread:'))
    ids = config.get('task_ids')
    if not isinstance(ids, list) or not ids or any(not isinstance(tid, str) or not tid for tid in ids):
        raise ValueError('协调等待需本轮原 task_ids')
    config['task_ids'] = list(dict.fromkeys(ids))
    # Reuse the established startup observation basis, not an eligibility or
    # recovery deadline. The outer window bounds only this tool invocation.
    for key in ('observation_seconds', 'window_seconds'):
        if key not in config:
            continue
        value = config[key]
        if type(value) not in (int, float) or not 0 < value < float('inf'):
            raise ValueError(key + ' 必须是有限正数，仅用于本次观察')
    for target in config.get('targets', []):
        if not isinstance(target, dict) or not isinstance(target.get('threadId'), str):
            raise ValueError('targets 使用公开 wait_threads 的真实 threadId/hostId')
    transport = native_cli_transport(command) if command else native_mcp_transport()
    return handoff_template + '\n' + template + '\n' + transport + (
        'const coordinatorConfig = ' + json.dumps(config, ensure_ascii=False) + ';\n'
        'text(await waitNativeCoordinator(callNative, tools.mcp__codex_app__wait_threads, '
        'tools.mcp__codex_app__send_message_to_thread, coordinatorConfig));\n')


def native_client_status(result):
    if (result.get('mode') == 'native_browser' or result.get('handoff')
            or result.get('continuation')):
        result = {**result, 'execution_client': {
            **result.get('execution_client', {}),
            'native_handoff': NATIVE_HANDOFF_CAPABILITY,
            'native_direct_handoff': NATIVE_DIRECT_HANDOFF_CAPABILITY,
            'native_handoff_automatic': False,
            'handoff_executor': 'functions.exec',
            'handoff_command': 'native-handoff-script',
            'handoff_guidance': (
                '原生收尾或消费交接使用 native-handoff-script --args-file 原参数文件，'
                '把返回的 script 原样作为 functions.exec 代码执行一次。'
                '新版finish在同次工具执行直接通知有资源的原后继，无需先唤醒协调者；'
                '只在原组结束或异常需协调时通知协调者。旧事件保持原路线，旧v1能力不代表支持直达。'
                '同次工具执行完成平台调用、发送占用、真实桌面消息与回执；'
                '脚本生成、本地文件和CLI单独finish都不是送达。未知发送不重发。'),
        }}
    return result

"""Pure checkpoint result derivation shared by storage and receipt verification."""

CHECKPOINT_DONE = {'passed', 'failed'}


def checkpoint_point_gaps(record, case, point):
    checks = record.get('dependency_checks', {})
    gaps = []
    for qid in point.get('rule_updates', []):
        gaps.append({'kind': 'rule', 'id': qid, 'title': '更新本检查点预期及依据',
                     'reason': '规则已明确或变化，需要先修订受影响预期和依据，再重新验证', 'status': 'pending_rule'})
    for dep in [*case.get('dependencies', []), *point.get('dependencies', [])]:
        check = checks.get(dep['id'])
        if not check or check.get('status') != 'ready':
            gaps.append({'kind': 'dependency', 'id': dep['id'], 'title': dep['title'],
                         'reason': (check or {}).get('observed') or '尚未检查执行条件',
                         'status': (check or {}).get('status', 'unchecked')})
    questions = {q['id']: q for q in record.get('requirement_design', {}).get('questions', [])}
    for qid in [*case.get('question_ids', []), *point.get('question_ids', [])]:
        q = questions.get(qid)
        if not q or q.get('status') != 'resolved':
            gaps.append({'kind': 'rule', 'id': qid, 'title': (q or {}).get('title', qid),
                         'reason': '需要明确预期规则', 'status': 'pending_rule'})
    by_id = {p['id']: p for p in case.get('checkpoints', [])}
    for sid in point.get('depends_on', []):
        if by_id[sid]['status'] != 'passed':
            gaps.append({'kind': 'step', 'id': sid, 'title': by_id[sid]['title'],
                         'reason': '前序步骤尚未成功完成', 'status': by_id[sid]['status']})
    return gaps



def checkpoint_has_blocker_provenance(point):
    """Old persisted structured gaps are evidence; prose or empty gaps are not."""
    if point.get('status_source') == 'unstructured_blocker':
        return False
    return point.get('status_source') == 'prerequisite_check' or any(
        gap.get('kind') in {'dependency', 'step'} and gap.get('id') and
        gap.get('status') in {'blocked', 'failed', 'pending_action'}
        for gap in point.get('gaps', []) if isinstance(gap, dict))


def preserve_checkpoint_status_source(point, previous):
    """Only server-saved automatic provenance survives an unchanged blocked state."""
    point.pop('status_source', None)
    if point.get('status') == previous.get('status') == 'blocked':
        point['status_source'] = ('prerequisite_check' if checkpoint_has_blocker_provenance(previous)
                                  else 'unstructured_blocker')
    return point


def reconcile_checkpoint_results(record):
    """Attach prerequisite diagnostics without changing the executor's verdicts."""
    for case in record['cases']:
        for point in case.get('checkpoints', []):
            point['gaps'] = checkpoint_point_gaps(record, case, point)
    return record

"""Desktop thread identity at transport boundaries, without changing bindings.

Bare UUIDs and their thread: form identify the same real chat. Older opaque
identifiers remain exact-match only; stripping arbitrary prefixes could let a
different executor inherit another module's authority.
"""
from uuid import UUID


def thread_id(reference):
    if not isinstance(reference, str):
        return ''
    try:
        return str(UUID(reference.removeprefix('thread:')))
    except ValueError:
        return ''


def same_executor_ref(left, right):
    if not isinstance(left, str) or not isinstance(right, str) or not left or not right:
        return False
    return left == right or bool(thread_id(left) and thread_id(left) == thread_id(right))


def native_thread_target(reference):
    # Retain the generator's legacy explicit thread: identifiers, while
    # accepting the actual bare UUID emitted by the desktop/dispatch APIs.
    actual = thread_id(reference)
    if actual:
        return actual
    return reference[7:] if isinstance(reference, str) and reference.startswith('thread:') else ''

"""Pure active UI case projection, also embedded in the no-install client."""

def is_superseded(case):
    """Only explicit, unexecuted aggregates are inactive; observed verdicts win."""
    return bool(case.get('superseded_by')) and case.get('status') in {'not_run', 'blocked'} and not (
        case.get('executed_at') or any(p.get('status') not in {'not_run', 'blocked'}
                                     for p in case.get('checkpoints', [])))


def active_cases(cases):
    return [case for case in cases if not is_superseded(case)]

"""Shared, pure preflight for existing UI payload shape rules. No business verdicts."""
def validate_ui_payload(payload):
    issues = []
    def issue(path, message):
        issues.append({'path': path, 'message': message})
    if not isinstance(payload, dict):
        return [{'path': '$', 'message': '保存内容必须是对象'}]
    coverage = payload.get('coverage')
    if coverage is not None:
        if not isinstance(coverage, list) or len(coverage) > 200:
            issue('coverage', 'coverage 每批最多 200 项，可分批追加')
        else:
            seen = set()
            for index, area in enumerate(coverage):
                prefix = f'coverage[{index}]'
                if not isinstance(area, dict):
                    issue(prefix, 'coverage 项必须是对象')
                    continue
                for key in ('coverage_id', 'feature', 'entry', 'considerations', 'gap'):
                    value = area.get(key, '')
                    if not isinstance(value, str) or len(value) > 20000:
                        issue(prefix + '.' + key, 'coverage 文本字段无效')
                    elif key in {'coverage_id', 'feature'} and not value.strip():
                        issue(prefix + '.' + key, '填写 coverage_id 与 feature，同批 ID 不得重复')
                cid = area.get('coverage_id')
                if isinstance(cid, str):
                    if cid.strip() in seen:
                        issue(prefix + '.coverage_id', '填写 coverage_id 与 feature，同批 ID 不得重复')
                    seen.add(cid.strip())
                ids = area.get('case_ids', [])
                if not isinstance(ids, list) or any(not isinstance(cid, str) or not cid.strip() or len(cid) > 20000 for cid in ids):
                    issue(prefix + '.case_ids', 'coverage.case_ids 必须为用例 ID 数组')
    notes = payload.get('review_notes')
    if notes is not None and (not isinstance(notes, str) or len(notes) > 20000):
        issue('review_notes', 'review_notes 必须是文本，最多 20000 字符')
    return issues


def require_ui_payload_shape(payload):
    issues = validate_ui_payload(payload)
    if issues:
        raise ValueError('；'.join(item['path'] + ': ' + item['message'] for item in issues))

"""Pure cleanup event validation, shared with the exported native client.

Only shapes and explicit values are checked here. Account authority, object
ownership, user permission and state transitions remain server decisions.
"""
from urllib.parse import urlsplit


COMMANDS = {'capability', 'register', 'acquire_dependency', 'release_dependency',
            'prepare_cleanup', 'complete_cleanup', 'reconcile', 'residual', 'retain'}


class CleanupValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('清理事件格式错误：' + '; '.join(
            item['path'] + ' ' + item['message'] for item in errors))


class CleanupScopeError(PermissionError):
    """Only fixed safe cleanup reasons may be exposed over HTTP."""


def validate_cleanup_events(values):
    """Validate one event or an events envelope; return the original event list.

    Never resolves identifiers, mutates arguments, or performs I/O. Errors carry
    paths and fixed guidance, never input values, credentials or object details.
    """
    errors = []

    def fail(path, message):
        errors.append({'path': path, 'message': message})

    def obj(value, path):
        if not isinstance(value, dict):
            fail(path, '必须为对象')
            return None
        return value

    def string(value, key, path, *, required=True, blank=False, limit=2000):
        if key not in value and not required:
            return
        item = value.get(key)
        if not isinstance(item, str) or (not blank and not item.strip()) or len(item) > limit:
            fail(path + '.' + key, '必须为' + ('可空' if blank else '非空') + f'字符串，最多 {limit} 字符')

    def boolean(value, key, path):
        if key in value and type(value[key]) is not bool:
            fail(path + '.' + key, '必须为布尔值')

    def scoped(value, path, *, object_identity=False):
        if 'scope' in value:
            fail(path + '.scope', 'scope 字段直接放在 capability/object 内，不嵌套 scope')
        for key in ('origin', 'environment', 'tenant', 'role'):
            string(value, key, path, required=object_identity and key != 'role', blank=key != 'origin')
        if value.get('origin') and isinstance(value['origin'], str):
            try:
                parsed = urlsplit(value['origin'])
                valid = (parsed.scheme in {'http', 'https'} and parsed.hostname
                         and not parsed.username and not parsed.password and parsed.path in {'', '/'}
                         and not parsed.query and not parsed.fragment)
                parsed.port
            except ValueError:
                valid = False
            if not valid:
                fail(path + '.origin', '必须为无凭据、路径或查询参数的 HTTP origin')
        if object_identity:
            for key in ('object_type', 'object_id', 'account_id'):
                string(value, key, path)

    def consumer(value, path):
        if obj(value, path) is None:
            return
        for key in ('source_node_id', 'case_id'):
            string(value, key, path)
        for key in ('checkpoint_id', 'work_unit_id'):
            string(value, key, path, required=False, blank=True)

    def observation(value, path):
        if obj(value, path) is None:
            return
        string(value, 'evidence_ref', path)
        if obj(value.get('object_scope'), path + '.object_scope') is not None:
            scoped(value['object_scope'], path + '.object_scope', object_identity=True)
        if 'status' in value and value['status'] is not None and type(value['status']) is not int:
            fail(path + '.status', '必须为 HTTP 状态整数或 null')
        for key in ('business_completed', 'object_identity_verified', 'principal_verified',
                    'original_operation_resolved', 'scene_release_verified'):
            boolean(value, key, path)
        for key in ('effect_state', 'object_state', 'absence_contract_ref', 'scene_release_evidence_ref'):
            string(value, key, path, required=False, blank=True)

    if obj(values, 'arguments') is None:
        raise CleanupValidationError(errors)
    events = values.get('events', [values])
    if not isinstance(events, list) or not 1 <= len(events) <= 100:
        fail('events', '必须为 1–100 个已有证据事件的数组')
        raise CleanupValidationError(errors)
    for index, event in enumerate(events):
        path = f'events[{index}]'
        if obj(event, path) is None:
            continue
        command = event.get('command')
        if not isinstance(command, str) or command not in COMMANDS:
            fail(path + '.command', '使用 command 指定 capability/register/acquire_dependency/release_dependency/prepare_cleanup/complete_cleanup/reconcile/residual/retain')
            continue
        if 'action' in event:
            fail(path + '.action', '事件使用 command，不使用 action')
        for key in ('capability_id', 'responsibility_id', 'cleanup_attempt_id'):
            string(event, key, path, required=False)
        for key in ('scene_only', 'retain_scene'):
            boolean(event, key, path)
        if command in {'capability', 'register'}:
            name = 'capability' if command == 'capability' else 'object'
            spec = obj(event.get(name), path + '.' + name)
            if spec is None:
                continue
            sp = path + '.' + name
            scoped(spec, sp)
            for key in ('account_id', 'object_type'):
                string(spec, key, sp, required=command == 'capability' or not spec.get('capability_id'))
            if command == 'capability':
                for key in ('entry_source', 'evidence_ref'):
                    string(spec, key, sp)
                string(spec, 'revalidation_evidence_ref', sp, required=False, blank=True)
                methods = spec.get('methods')
                if not isinstance(methods, list) or not methods:
                    fail(sp + '.methods', '必须为有真实依据的方法数组')
                else:
                    for mi, method in enumerate(methods):
                        mp = sp + f'.methods[{mi}]'
                        if obj(method, mp) is None:
                            continue
                        if method.get('kind') not in ('ui', 'api'):
                            fail(mp + '.kind', '使用 kind: ui 或 api，不使用 method/channel 代替')
                        for key in ('entry', 'evidence_ref'):
                            string(method, key, mp)
            else:
                for key in ('case_id', 'object_id', 'creation_evidence_ref', 'ownership'):
                    string(spec, key, sp)
                string(spec, 'checkpoint_id', sp, required=False, blank=True)
                string(spec, 'capability_id', sp, required=False)
                string(spec, 'retention_evidence_ref', sp, required=False, blank=True)
                if spec.get('kind') not in ('test_data', 'file', 'shared_configuration', 'business_scene'):
                    fail(sp + '.kind', '使用 test_data/file/shared_configuration/business_scene')
                boolean(spec, 'retain_scene', sp)
                ids = spec.get('defect_case_ids', [])
                if not isinstance(ids, list) or any(not isinstance(cid, str) or not cid.strip() for cid in ids):
                    fail(sp + '.defect_case_ids', '必须为非空用例 ID 字符串数组')
                consumers = spec.get('consumers', [])
                if not isinstance(consumers, list):
                    fail(sp + '.consumers', '必须为消费者数组')
                else:
                    for ci, item in enumerate(consumers):
                        consumer(item, sp + f'.consumers[{ci}]')
                if spec.get('residual') is not None and obj(spec['residual'], sp + '.residual') is not None:
                    string(spec['residual'], 'reason', sp + '.residual', limit=4000)
                    observation(spec['residual'].get('observation'), sp + '.residual.observation')
        else:
            if 'responsibility_id' not in event:
                string(event, 'responsibility_id', path)
            if command in {'acquire_dependency', 'release_dependency'}:
                consumer(event.get('consumer'), path + '.consumer')
            if command == 'prepare_cleanup' and 'method_index' in event and (
                    type(event['method_index']) is not int or event['method_index'] < 0):
                fail(path + '.method_index', '必须为非负整数')
            if command in {'complete_cleanup', 'reconcile', 'residual'}:
                observation(event.get('observation'), path + '.observation')
            if command == 'complete_cleanup' or command == 'reconcile' and event.get('scene_only') is not True:
                if 'cleanup_attempt_id' not in event:
                    string(event, 'cleanup_attempt_id', path)
            if command == 'residual':
                string(event, 'reason', path, limit=4000)
    if errors:
        raise CleanupValidationError(errors)
    return events

"""Platform-wide scope exclusions, separate from resource availability and verdicts."""
import re

POLICY_ID = 'multi_account_excluded'
REASON = '不测（用户明确排除多账号场景）'
GUIDANCE = (
    '当前平台全局范围：多账号、双账号、跨账号及跨租户对照/隔离业务场景一律'
    + REASON + '。保留具体设计和已有真实结果；未执行项使用 not_run，'
    'not_run_reason 填写上述原因；UI cases.account_scope、API design.account_scope 使用 multi_account/cross_account/cross_tenant 明确范围。'
    '不算通过，不申请第二账号、不等待账号集合、'
    '不为其创建执行会话或续接，不另做替代测试。普通继续测试/重测不解除此规则。'
    '不同模块各用一个账号并发仍允许；单账号权限、匿名及其他适用风险覆盖保持。'
    '已有真实对象责任的必要清理和无需账号的报告仍按原授权及回收协议处理，不扩展业务测试。'
)

_MULTI = re.compile(
    r'(?:多|双|跨|两|两个|2个)[\s_-]*(?:账|帐)号|(?:跨|不同|多个|两个)[\s_-]*租户'
    r'|\b(?:multi|dual|cross|two)[\s_-]*accounts?\b|\bcross[\s_-]*tenant\b', re.I)


def snapshot():
    return {'id': POLICY_ID, 'multi_account_testing': False, 'reason': REASON,
            'guidance': GUIDANCE, 'independent_single_account_modules': True}


def resource_excluded(value, state=None):
    """Preferred account IDs are alternatives, not simultaneous requirements."""
    if value.get('requires_account') is False or value.get('phase') == 'report' or cleanup_allowed(state, value):
        return False
    required = value.get('requested_account_ids', value.get('account_ids', [])) or []
    if value.get('account_selection') == 'preferred':
        required = []
    return len(set(required)) > 1 or len(value.get('requirements') or []) > 1


def case_excluded(case):
    # Only the case's declared purpose/scope is used, not evidence, arbitrary
    # documents, module names, or dependency descriptions mentioning exclusions.
    design = case.get('design') or {}
    if not isinstance(design, dict):
        design = {}
    scope = case.get('account_scope') or design.get('account_scope')
    declared_multi = scope in {'multi_account', 'cross_account', 'cross_tenant'} or any(
        _MULTI.search(str(v or '')) for v in
        (case.get('scenario'), case.get('title'), design.get('title'), design.get('objective')))
    if declared_multi:
        return True
    if scope == 'single_account':
        return False  # A corrected design outranks a derived, stale exclusion marker.
    return case.get('execution_disposition') == POLICY_ID or case.get('not_run_reason') == REASON


def has_observations(case):
    return (case.get('status') in {'passed', 'failed', 'partial'} or bool(case.get('executed_at'))
            or any(p.get('status') in {'passed', 'failed', 'partial'} or p.get('actual') or p.get('observed')
                   for p in case.get('checkpoints', [])))


def annotate_unexecuted(case):
    """Normalize new saves or a detached report projection; retain real observations."""
    if has_observations(case):
        return False
    if case_excluded(case):
        case.update(status='not_run', not_run_reason=REASON,
                    execution_disposition=POLICY_ID, blocked_by=[], executed_at='')
        return True
    if case.get('execution_disposition') == POLICY_ID:
        case['execution_disposition'] = ''
        if case.get('not_run_reason') == REASON:
            case['not_run_reason'] = '已纠正为单账号场景，业务尚未验证。'
        return True
    return False


def excluded_response(**extra):
    return {'state': 'not_tested', 'excluded': True, 'reason': REASON,
            'testing_policy': snapshot(), 'account_ready': False,
            'stage_ready': False, 'continued': False, 'release_required': False,
            'account_ids': [], 'required_context_count': 0,
            'next_action': 'skip_excluded_scenario', 'end_turn': False, **extra}


def cleanup_allowed(state, node):
    """Only original, server-recorded cleanup responsibilities may use old resources."""
    if not state or not node.get('policy_cleanup_unit_id'):
        return False
    unit = next((u for u in node.get('checkpoint', {}).get('work_plan', {}).get('units', [])
                 if u['id'] == node['policy_cleanup_unit_id'] and u.get('purpose') == 'cleanup'), None)
    if not unit or not unit.get('cleanup_responsibility_ids'):
        return False
    from .cleanup_capabilities import continuation_sources
    sources = {node['id']} | continuation_sources(state, node)
    case_ids = set(unit['case_ids']) | {p['case_id'] for p in unit['checkpoint_refs']}
    objects = [state.get('cleanup_objects', {}).get(key) for key in unit['cleanup_responsibility_ids']]
    if not all(obj and obj['owner'] == node['owner'] and obj['task_id'] == node['task_id']
               and obj['source_node_id'] in sources and obj['case_id'] in case_ids for obj in objects):
        return False
    if all(obj['state'] in {'cleaned', 'retained', 'residual'} and not obj.get('consumers')
           and not obj.get('retain_scene') for obj in objects):
        return False
    req = unit['requires']
    if node.get('phase') != req['phase'] or node.get('requirements', []) != req['requirements']:
        return False
    requested = set(node.get('requested_account_ids', []))
    declared = set(req['account_ids']) if req['account_selection'] == 'required' else set()
    return requested == declared or not declared and requested <= {obj['account_id'] for obj in objects}


def node_excluded(node, state=None):
    if node.get('phase') == 'report' or cleanup_allowed(state, node):
        return False
    if node.get('checkpoint', {}).get('work_plan'):
        from .native_work_plan import record_view
        from .execution_work_plan import project_work_candidates
        record = record_view(state, node) if state else None
        if record is None:
            return False  # Unreadable evidence never converts a legitimate pending stage.
        try:
            candidates = project_work_candidates(node, record)
        except ValueError:
            return False  # Let the existing per-node invalid-plan path explain it.
        return (any(c['eligibility'] == 'excluded' for c in candidates)
                and all(c['eligibility'] in {'completed', 'excluded'} for c in candidates))
    return (node.get('execution_disposition') == POLICY_ID or case_excluded({'title': node.get('title')})
            or resource_excluded(node, state))


def exclude_unallocated_node(node, state=None):
    if node.get('state') == 'queued' and node_excluded(node, state):
        node.update(state='blocked', reason=REASON, result='not_run',
                    execution_disposition=POLICY_ID, reservation=None, protected=False)
        node.pop('resource_wait', None)
        return True
    return False

"""Deterministic native preparation and closeout, without browser automation.

Embedded in the downloadable client. Receipts, not model-written glue scripts,
carry identity/revision between steps. Unknown writes are never replayed.
"""
import copy
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path


def native_checkpoint_observations(cases, known):
    """Patch/append result observations; explicit designs retain replacement."""
    result = copy.deepcopy(cases)
    observations = {'id', 'status', 'actual', 'method', 'verification_mode', 'evidence',
                    'correlation', 'action_required', 'action_context'}
    for case in result:
        points = case.get('checkpoints')
        old = {p['id']: p for p in known.get(case['case_id'], {}).get('checkpoints', [])}
        if (not isinstance(points, list) or not points or not old
                or 'checkpoint_updates' in case
                or set(case) - {'case_id', 'status', 'actual', 'conclusion', 'ai_analysis', 'checkpoints', 'executed_at', 'not_run_reason'}
                or any(not isinstance(p, dict) or not isinstance(p.get('id'), str)
                       or not {'status', 'actual', 'verification_mode'} <= set(p)
                       or p['status'] == 'not_run' or p['verification_mode'] == 'design'
                       or (p['id'] not in old and not {'title', 'expected'} <= set(p))
                       or (p['id'] in old and any(old[p['id']].get(k) != v
                           for k, v in p.items() if k not in observations))
                       for p in points)):
            continue
        if len({p['id'] for p in points}) != len(points):
            continue  # Keep the server's duplicate-ID rejection authoritative.
        updates = {p['id']: {k: v for k, v in p.items() if k in observations}
                   for p in points if p['id'] in old}
        added = [p for p in points if p['id'] not in old]
        if added:
            case['checkpoints'] = [{**p, **updates.get(pid, {})} for pid, p in old.items()] + added
        else:
            case['checkpoint_updates'] = list(updates.values())
            del case['checkpoints']
    return result


def native_save_readback(receipt, record, known=None):
    """Confirm only an exact next revision and every submitted field; no replay."""
    bound = receipt['binding']
    if (not isinstance(record, dict) or record.get('id') != bound['execution_id']
            or type(record.get('revision')) is not int
            or record['revision'] != receipt['revision_before'] + 1):
        raise ValueError('只读记录未确认原执行 ID 与精确下一修订；原保存仍未知，不重发')
    submitted = receipt.get('request', {}).get('arguments', receipt['payload'])
    if submitted.get('assets'):
        raise ValueError('证据上传需核对原文件回执；不能仅凭用例读回确认保存')

    def matches(expected, actual):
        if isinstance(expected, dict):
            return isinstance(actual, dict) and all(k in actual and matches(v, actual[k]) for k, v in expected.items())
        if isinstance(expected, list):
            return isinstance(actual, list) and len(expected) == len(actual) and all(matches(a, b) for a, b in zip(expected, actual))
        return type(expected) is type(actual) and expected == actual

    # Paged public views retain explicit split originals outside the active list.
    all_cases = list({c['case_id']: c for c in [*record.get('superseded_cases', []),
                                              *record.get('cases', [])]}.values())
    saved = {c['case_id']: c for c in all_cases}
    baselines = receipt.get('case_baselines', known or {})
    for case in submitted.get('cases', []):
        actual = saved.get(case['case_id'], {})
        baseline = baselines.get(case['case_id'], {})
        points = copy.deepcopy(case.get('checkpoints', baseline.get('checkpoints', [])))
        updates = case.get('checkpoint_updates', [])
        if updates:
            by_id = {p['id']: p for p in points}
            if any(p['id'] not in by_id for p in updates):
                raise ValueError('缺少原检查点基线，无法核实局部保存；原保存仍未知')
            for update in updates:
                by_id[update['id']].update(update)
        expected = {k: v for k, v in case.items() if k != 'checkpoint_updates'}
        if points:
            # Storage adds prerequisite diagnostics, never rewrites the model's
            # submitted parent verdict. Compare the complete checkpoint payload.
            original_points = {p['id']: p for p in baseline.get('checkpoints', [])}
            for point in points:
                preserve_checkpoint_status_source(point, original_points.get(point['id'], {}))
                for key, default in (('status', 'not_run'), ('actual', ''), ('verification_mode', 'design'), ('action_required', '')):
                    point.setdefault(key, default)
            candidate = {**copy.deepcopy(baseline), **copy.deepcopy(expected), 'checkpoints': points}
            derived = reconcile_checkpoint_results({
                'cases': [candidate], 'dependency_checks': record.get('dependency_checks', {}),
                'requirement_design': record.get('requirement_design', {})})['cases'][0]
            expected['checkpoints'] = derived['checkpoints']
        elif actual.get('checkpoints') and 'checkpoints' not in case:
            raise ValueError('缺少原检查点基线，无法核实保存结果；原保存仍未知')
        normalized = {**copy.deepcopy(baseline), **copy.deepcopy(expected)}
        if annotate_unexecuted(normalized):
            expected.update({key: normalized[key] for key in
                             ('status', 'not_run_reason', 'execution_disposition', 'blocked_by', 'executed_at') if key in normalized})
        if not matches(expected, actual):
            raise ValueError('只读记录与提交用例或完整检查点结果不一致；原保存仍未知，不重发')
    coverage = {area['coverage_id']: area for area in record.get('coverage', [])}
    for area in submitted.get('coverage') or []:
        if not matches(area, coverage.get(area['coverage_id'])):
            raise ValueError('只读记录与提交覆盖字段不一致；原保存仍未知，不重发')
    for key in ('review_notes', 'scene_outcome', 'experiment'):
        if key in submitted and submitted[key] is not None and not matches(submitted[key], record.get(key)):
            raise ValueError('只读记录与提交元数据不一致；原保存仍未知，不重发')
    counts = {}
    for case in active_cases(all_cases):
        counts[case['status']] = counts.get(case['status'], 0) + 1
    return {'execution_id': record['id'], 'revision': record['revision'],
            'saved_cases': copy.deepcopy(all_cases), 'coverage': copy.deepcopy(record.get('coverage', [])),
            'execution_plan': {**copy.deepcopy(record.get('execution_plan') or {
                'execution_summary': {'status_counts': counts}, 'refresh_at_resource_boundary': True}),
                'source_revision': record['revision']},
            'confirmation_source': 'platform_record_readback'}


def native_design(source, *, allow_results=False):
    cases = copy.deepcopy(source.get('cases') if isinstance(source, dict) else source)
    if not isinstance(cases, list) or not cases:
        raise ValueError('准备需要明确选定的非空 cases 设计，不能默默缩减范围')
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError('用例必须是对象')
        cid = case.get('case_id')
        if not isinstance(cid, str) or not cid.strip() or cid in seen:
            raise ValueError('用例需要不同的文本 case_id')
        seen.add(cid)
        if 'title' in case:
            if case.get('scenario') and case['scenario'] != case['title']:
                raise ValueError('title 与 scenario 不一致，先核对设计')
            case['scenario'] = case.pop('title')
        for field in ('scenario', 'steps', 'expected'):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError('用例缺少 ' + field)
        if not allow_results and (case.get('status', 'not_run') != 'not_run' or case.get('actual')):
            raise ValueError('新轮准备只接受未执行设计；不可继承历史结果')
        case.setdefault('status', 'not_run')
    return cases


def native_isolated_options(assignment, directory):
    """Automatic for new kits; don't silently migrate a recorded live surface."""
    if assignment.get('browser_mode') == 'cua':
        return None  # Explicit legacy surface; new server tasks reject shared claims.
    if 'direct_browser' in assignment or assignment.get('browser_mode') == 'isolated':
        options = assignment.get('direct_browser') or {}
        if not isinstance(options, dict):
            raise ValueError('direct_browser 必须为环境选项对象')
        return options
    binding_file = Path(directory) / 'binding.json'
    if binding_file.exists():
        binding = json.loads(read_utf8(binding_file))
        if (binding.get('lease_id') and binding.get('account_ids') != []
                and (binding.get('native_context_binding') or {}).get('browser') != 'chromium'):
            return None
    return {}


def native_claim_configuration(assignment):
    """Accept both published claim shapes; never silently choose conflicting facts."""
    outer = assignment.get('claim_arguments') or {}
    if not isinstance(outer, dict) or not isinstance(outer.get('arguments', {}), dict):
        raise ValueError('claim_arguments 及其 arguments 必须为对象')
    for key in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref'):
        if key in outer and (not same_executor_ref(outer[key], assignment.get(key)) if key == 'executor_ref'
                             else outer[key] != assignment.get(key)):
            raise ValueError('领取通知的 %s 与原 assignment 不一致' % key)
    result = {k: copy.deepcopy(v) for k, v in outer.items() if k != 'arguments'}
    for key, value in outer.get('arguments', {}).items():
        if key in result and result[key] != value:
            raise ValueError('领取通知 %s 的内外层值冲突' % key)
        result[key] = copy.deepcopy(value)
    if 'work_token' in assignment:
        if 'work_token' in result and result['work_token'] != assignment['work_token']:
            raise ValueError('领取通知 work_token 与 assignment 阶段冲突')
        result['work_token'] = copy.deepcopy(assignment['work_token'])
    return result


def native_resume(client, assignment_file, directory, notice):
    """Consume the actual notice before environment setup; no model-transcribed token."""
    assignment = json.loads(read_utf8(assignment_file))
    if assignment.get('workspace_url', client.url) != client.url:
        raise ValueError('恢复通知不属于当前测试台')
    if not isinstance(notice, dict):
        raise ValueError('恢复入口需要原通知 claim_arguments 对象')
    claim = notice.get('claim_arguments', notice)
    if not isinstance(claim, dict) or claim.get('action') != 'claim':
        raise ValueError('恢复通知缺少原 claim_arguments')
    for key in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref'):
        if not claim.get(key) or (not same_executor_ref(claim[key], assignment.get(key)) if key == 'executor_ref'
                                 else claim[key] != assignment.get(key)):
            raise ValueError('恢复通知的 %s 与原执行绑定不一致' % key)
    candidate = copy.deepcopy(assignment)
    candidate.pop('work_token', None)
    candidate['claim_arguments'] = claim
    normalized = native_claim_configuration(candidate)
    # Only phase/resource facts come from a notification, never browser metadata.
    candidate['claim_arguments'] = {k: normalized[k] for k in ('work_token', 'account_ids', 'account_selection') if k in normalized}
    ready_path = Path(directory) / 'stage-ready.json'
    ready_path.unlink(missing_ok=True)
    if normalized.get('work_token'):
        result = native_stage_ready(client, assignment_file, directory, assignment=candidate)
    else:
        binding_path = Path(directory) / 'binding.json'
        previous = json.loads(read_utf8(binding_path)) if binding_path.exists() else {}
        if native_claim_configuration(assignment).get('work_token') or previous.get('work_plan'):
            raise ValueError('work_token_missing: 阶段恢复通知缺少 work_token；保留原记录')
        identity = {k: candidate[k] for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')}
        status = client.call('direct_test_session', {**identity, 'action': 'context', 'arguments': {'resume_notice': True}})
        if (status.get('task_id') != identity['task_id'] or status.get('node_id') != identity['node_id']
                or status.get('state') not in {'queued', 'running'} or status.get('authority_revoked')):
            raise ValueError('resume_not_runnable: 原任务已停止、暂停或执行绑定变化')
        available = status.get('state') == 'running' or (status.get('resource_wait') or {}).get('resources_available') is True
        accounts = normalized.get('account_ids') or status.get('account_ids') or []
        if available and accounts:
            candidate.setdefault('direct_browser', {})['context_count'] = len(accounts)
        if available:
            write_private_json(assignment_file, candidate)
        result = {'stage_ready': available, 'end_turn': not available, 'status': status}
    if result.get('excluded'):
        return result
    return {**result, 'next_action': 'environment_setup' if result['stage_ready'] else 'wait_for_resource_event'}


def native_stage_ready(client, assignment_file, directory, *, assignment=None):
    """Check a notified stage once before browser creation, never poll or claim."""
    assignment = copy.deepcopy(assignment) if assignment is not None else json.loads(read_utf8(assignment_file))
    configuration = native_claim_configuration(assignment)
    token = configuration.get('work_token')
    if not token:
        raise ValueError('缺少原阶段通知，不能猜测资源集合')
    identity = {k: assignment[k] for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')}
    path = Path(directory) / 'stage-ready.json'
    if path.exists():
        path.unlink()  # A failed new check cannot leave a usable old allowance.
    result = client.call('direct_test_session', {**identity, 'action': 'context', 'arguments': {'work_token': token}})
    if result.get('work_token') != token:
        raise ValueError('阶段核对回执不属于原通知')
    write_private_json(path, {**result, 'identity': identity})
    if result.get('stage_ready'):
        accounts = result.get('account_ids')
        if not isinstance(accounts, list) or not accounts or result.get('required_context_count') != len(accounts):
            path.unlink()
            raise ValueError('阶段回执没有完整账号集合及环境数量')
        assignment['claim_arguments'] = {**configuration, 'work_token': token, 'account_ids': accounts}
        assignment.setdefault('direct_browser', {})['context_count'] = len(accounts)
        write_private_json(assignment_file, assignment)
    return result


def reconcile_native_prepare(client, binding, *, status=None, claim_configuration=None, claim_request=None):
    """Read the original allocation and full context; never repeat a claim."""
    identity = {k: binding[k] for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref') if binding.get(k)}
    calls = 1
    if status is None:
        calls += 1
        try:
            status = client.call('direct_test_session', {**identity, 'action': 'context'})
        except Exception as error:
            raise ValueError('原领取只读核对未成功，后续步骤已停止；保留原回执，不重放') from error
    changed = bool(binding.get('lease_id') and binding['lease_id'] != status.get('lease_id'))
    if (status.get('task_id') != identity.get('task_id') or status.get('node_id') != identity.get('node_id')
            or status.get('state') != 'running' or not status.get('lease_id') or status.get('authority_revoked')
            or changed and not claim_request):
        raise ValueError('原领取结果尚未确认或已撤权，后续步骤已停止；保留原事实，不重领')
    if claim_request:
        if (claim_request.get('action') != 'claim'
                or any(claim_request.get(k) != identity.get(k) for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id'))
                or not same_executor_ref(claim_request.get('executor_ref'), identity.get('executor_ref'))):
            raise ValueError('原领取请求身份无法确认；保留原回执，不重放')
        original_configuration = {**(claim_request.get('arguments') or {}),
            **({'account_ids': claim_request['account_ids']} if 'account_ids' in claim_request else {})}
        if any(original_configuration.get(k) != (claim_configuration or {}).get(k) for k in
                ('account_ids', 'work_token', 'browser_environment', 'browser_environments', 'native_environment_replacement')):
            raise ValueError('未确认领取的请求条件已变化；先核对原请求，不接入另一组资源或浏览器')
        claim_configuration = original_configuration
    context = client.call('direct_test_session', {**identity, 'action': 'context', 'lease_id': status['lease_id'],
        **({'arguments': {'reconcile_from_lease_id': binding['lease_id']}} if changed else {})})
    node, lease = context.get('node') or {}, context.get('lease') or {}
    dispatch = node.get('executor_dispatch') or {}
    if (node.get('id') != identity['node_id'] or node.get('task_id') != identity['task_id']
            or lease.get('id') != status['lease_id'] or lease.get('node_id') != identity['node_id']
            or lease.get('revoked') or context.get('prior_operations')
            or any(dispatch.get(k) != identity.get(k) for k in ('holder_id', 'dispatch_id'))
            or not same_executor_ref(dispatch.get('executor_ref'), identity['executor_ref'])):
        raise ValueError('原领取绑定/代次/在途操作无法确认，后续步骤已停止，不重放')
    old_context = binding.get('native_context_binding') or {}
    current_context = context.get('native_context_binding') or lease.get('native_context_binding') or {}
    if not changed and old_context and any(old_context.get(k) != current_context.get(k) for k in ('context_id', 'environment_key')):
        raise ValueError('原浏览器环境绑定已变化，后续步骤已停止；先核对原环境')
    claim_configuration = claim_configuration or {}
    token = claim_configuration.get('work_token')
    if token and any((node.get('work_selection') or {}).get(k) != token.get(k)
                     for k in ('work_unit_id', 'plan_revision', 'requirements_digest')):
        raise ValueError('阶段通知与原活动租约不一致；保留原绑定，不重领或继续旧阶段')
    accounts = claim_configuration.get('account_ids')
    if accounts is not None and set(accounts) != set(lease.get('account_ids', [])):
        raise ValueError('阶段完整账号集合与原活动租约不一致；在原资源边界核对')
    if changed:
        project, record = context.get('project') or {}, context.get('record') or {}
        if (context.get('reconciled_from_lease_id') != binding['lease_id']
                or not binding.get('project_id') or not binding.get('execution_id')
                or project.get('id') != binding['project_id'] or record.get('id') != binding['execution_id']
                or project.get('ui_execution_id') != binding['execution_id']):
            raise ValueError('重新领取的原交还与报告绑定未确认；保留旧回执')
        expected = claim_configuration.get('browser_environments')
        if expected is None:
            expected = [claim_configuration['browser_environment']] if claim_configuration.get('browser_environment') else []
        actual = current_context.get('contexts') or ([current_context] if current_context else [])
        # These are the persisted original claim facts, never a later assignment.
        def environment_identity(value):
            from urllib.parse import urlsplit
            url = urlsplit(value.get('origin', ''))
            port = url.port
            target = (url.scheme.lower(), (url.hostname or '').lower(), port if port != {'http': 80, 'https': 443}.get(url.scheme) else None)
            browser = value.get('browser', '').strip().lower()
            browser = {'google chrome': 'chrome', 'microsoft edge': 'edge', 'in-app-browser': 'iab',
                'in_app_browser': 'iab', 'in-app browser': 'iab', 'in app browser': 'iab',
                'codex-iab': 'iab', 'codex in-app browser': 'iab'}.get(browser, browser)
            return (value.get('host_id'), browser, target, value.get('isolation'),
                'shared-profile' if value.get('isolation') == 'shared_profile' else value.get('context_id'),
                value.get('browser_generation', 0))
        if (not expected or len(actual) != len(lease.get('account_ids', []))
                or len({environment_identity(row) for row in actual}) != len(actual)
                or not {environment_identity(row) for row in actual} <= {environment_identity(row) for row in expected}):
            raise ValueError('重新领取的浏览器环境与原请求不一致；保留原回执，不继续业务')
    return {'claim': status, 'context': context, 'http_calls': calls}


def prepare_native(client, assignment, source, directory, *, resume=False):
    cases = native_design(source, allow_results=resume)  # Validate local shape before claiming.
    inventory = copy.deepcopy(source.get('coverage')) if isinstance(source, dict) else None
    if inventory is not None and not isinstance(inventory, list):
        raise ValueError('coverage 必须为功能覆盖清单')
    require_ui_payload_shape({'cases': cases, 'coverage': inventory})
    required = ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')
    if not isinstance(assignment, dict) or any(not assignment.get(k) for k in required):
        raise ValueError('assignment 缺少原任务、节点或执行会话绑定')
    if assignment.get('workspace_url', client.url) != client.url:
        raise ValueError('assignment 不属于当前测试台')
    assignment = {**assignment, 'claim_arguments': native_claim_configuration(assignment)}
    identity = {k: assignment[k] for k in (*required, 'coordinator_ref') if k in assignment}
    fingerprint = hashlib.sha256(json.dumps([client.url, identity, cases, inventory], sort_keys=True,
                                           ensure_ascii=False).encode()).hexdigest()
    root = Path(directory).absolute()
    if root.is_symlink():
        raise ValueError('准备目录不能为符号链接')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    environment = None
    if native_isolated_options(assignment, root) is not None:
        # Only the direct browser helper writes this after creating real
        # contexts. Loading metadata does not launch or proxy a browser.
        environment = json.loads(read_utf8(root / 'browser-environment.json'))
        if (environment.get('state') != 'open' or environment.get('browser_tool') != 'node_repl'
                or any(environment.get('identity', {}).get(k) != identity[k]
                       for k in ('task_id', 'node_id', 'holder_id'))
                or not same_executor_ref(environment.get('identity', {}).get('executor_ref'), identity['executor_ref'])
                or not environment.get('environments')):
            raise ValueError('直接浏览器尚未创建或不属于原执行者；不领取账号、不继续后续步骤')
        assignment = copy.deepcopy(assignment)
        claim_configuration = assignment.setdefault('claim_arguments', {})
        claim_configuration.pop('browser_environment', None)
        claim_configuration['browser_environments'] = environment['environments']
        assignment.pop('browser_environment', None)
    ledger = root / 'preparation.json'
    with batch_lock(ledger):
        binding_file = root / 'binding.json'
        previous = json.loads(read_utf8(binding_file)) if binding_file.exists() else {}
        reconciliation_calls = 0
        if resume:
            if previous and (any(previous.get(k) != identity[k] for k in
                                ('task_id', 'node_id', 'holder_id'))
                             or not same_executor_ref(previous.get('executor_ref'), identity['executor_ref'])):
                raise ValueError('恢复必须沿原任务、节点、持有人及执行会话绑定')
            if previous.get('workspace_url', client.url) != client.url:
                raise ValueError('原绑定不属于当前测试台')
            anchor = assignment.get('resume_record') or {}
            if previous.get('execution_id') and any(anchor.get(k, previous.get(k)) != previous.get(k)
                                                   for k in ('project_id', 'execution_id')):
                raise ValueError('恢复指定记录与原绑定不一致')
            review_receipt = (previous.get('final_review') or {}).get('receipt_file')
            known_receipts = {Path(review_receipt).resolve()} if isinstance(review_receipt, str) and review_receipt else set()
            receipt_paths = {p.resolve() for p in root.glob('*.json')} | known_receipts
            for receipt_path in sorted(receipt_paths):
                known_receipt = receipt_path.name.startswith('receipt') or receipt_path.resolve() in known_receipts
                try:
                    receipt = json.loads(read_utf8(receipt_path))
                except (ValueError, OSError):
                    if known_receipt:
                        raise ValueError('原保存回执无法读取：%s；核对原回执，不重放业务' % receipt_path.name) from None
                    # The private directory also holds fixtures, reports and
                    # shell stdout files (created empty before prepare starts).
                    # These are not evidence of an uncertain platform write.
                    continue
                if (isinstance(receipt, dict) and receipt.get('state') in {'pending', 'unknown', 'rejected'}
                        and (known_receipt
                             or ('binding' in receipt and 'payload' in receipt))):
                    if not isinstance(receipt.get('payload'), dict) or not receipt.get('fingerprint'):
                        raise ValueError('原观察保存未确认；核对原回执，不重放业务或继续准备')
                    reconciled = client.native_record(binding_file, receipt['payload'], receipt_path)
                    reconciliation_calls += reconciled.get('client_timing', {}).get('http_calls', 0)
                    previous = json.loads(read_utf8(binding_file))
            marker = root / 'observation-pending.json'
            clear_rejected_native_observation(root, previous)
            if marker.exists():
                observation = json.loads(read_utf8(marker))
                path = observation.get('receipt_file')
                receipt = json.loads(read_utf8(path)) if path and Path(path).exists() else {}
                if not native_pending_receipt_matches(observation, receipt, previous, client=client):
                    raise ValueError('原观察保存未确认；核对原回执，不重放业务或继续准备')
                marker.unlink()
        state = json.loads(read_utf8(ledger)) if ledger.exists() else {
            'fingerprint': fingerprint, 'state': 'new', 'stages': {}}
        legacy_fingerprint = hashlib.sha256(json.dumps([client.url, identity, cases], sort_keys=True,
            ensure_ascii=False).encode()).hexdigest() if inventory is None else None
        if state.get('fingerprint') not in {fingerprint, legacy_fingerprint} and not (resume and previous):
            raise ValueError('准备目录属于其他任务或设计；不能覆盖原观察')
        recovered = {}
        expected_claim = {**(assignment.get('claim_arguments') or {})}
        if 'work_token' in assignment and 'work_token' not in expected_claim:
            expected_claim['work_token'] = assignment['work_token']
        if state['state'] == 'ready' and resume and previous.get('work_plan'):
            status = client.call('direct_test_session', {**identity, 'action':'context'})
            reconciliation_calls += 1
            if status.get('lease_id'):
                recovered = reconcile_native_prepare(client, {**identity, **previous}, status=status,
                                                     claim_configuration=expected_claim)
                reconciliation_calls += recovered['http_calls']
        if state['state'] in {'pending', 'failed'} and state.get('claim_outcome') == 'rejected' and state.get('stage') == 'claim' and resume:
            state.setdefault('recovery_history', []).append({'stage': 'claim', 'original_state': state['state'],
                'outcome': 'rejected', 'at': datetime.now(timezone.utc).isoformat()})
            state['state'] = 'new'
        if state['state'] in {'pending', 'failed'}:
            if not resume:
                raise ValueError('准备在 %s 未成功，后续步骤已停止；保留原回执，核对原状态，不重放写入' % state.get('stage'))
            recovered = reconcile_native_prepare(client, {**identity, **previous}, claim_configuration=expected_claim,
                claim_request=state.get('stages', {}).get('claim', {}).get('request')
                if state.get('stage') == 'claim' and state.get('claim_outcome') == 'unknown' else None)
            reconciliation_calls += recovered['http_calls']
            recovered_record = recovered['context'].get('record')
            if state.get('stage') == 'baseline':
                payload = state['stages']['baseline'].get('request')
                baseline = state['stages']['baseline']
                failed_response = (state.get('baseline_outcome') == 'rejected'
                    or type(baseline.get('http_status')) is int and 400 <= baseline['http_status'] < 500)
                absent = ('record' in recovered['context'] and recovered_record is None
                          and not recovered['context']['project'].get('ui_execution_id'))
                if (not payload or recovered['context']['project']['id'] != payload.get('project_id')
                        or not recovered_record and not (failed_response and absent)):
                    raise ValueError('原基线保存仍未知，后续步骤已停止；不重发基线')
                if recovered_record:
                    confirmed = native_save_readback({'binding': {'execution_id': recovered_record['id']},
                        'revision_before': 0, 'payload': payload}, recovered_record)
                    previous.update(project_id=recovered['context']['project']['id'],
                                    execution_id=confirmed['execution_id'], revision=confirmed['revision'])
                    state['baseline_outcome'] = 'confirmed'
                else:
                    state['baseline_outcome'] = 'rejected'
                    baseline['rejection_confirmed'] = {'source': 'original_context_readback',
                        'project_id': recovered['context']['project']['id'], 'record_absent': True,
                        'checked_at': datetime.now(timezone.utc).isoformat()}
            state.setdefault('recovery_history', []).append({'stage': state.get('stage'),
                'original_state': state['state'], 'lease_id': recovered['claim']['lease_id'],
                **({'outcome': 'rejected', 'request': copy.deepcopy(payload),
                    'http_status': state['stages']['baseline'].get('http_status')}
                   if state.get('stage') == 'baseline' and state.get('baseline_outcome') == 'rejected' else {}),
                'at': datetime.now(timezone.utc).isoformat()})
            write_private_json(ledger, state)
        def reused_ready(calls):
            # The preparation receipt describes the original baseline. The
            # successful result receipt owns current revision/checkpoints.
            binding = json.loads(read_utf8(root / 'binding.json'))
            known = binding.get('case_results') or {}
            ready = state['ready']
            return {**ready, 'revision': binding['revision'], 'reused': True, 'http_calls': calls,
                    'coverage': copy.deepcopy(binding.get('coverage', ready.get('coverage', []))),
                    **({'native_context_binding': binding['native_context_binding']}
                       if binding.get('native_context_binding') else {}),
                    'cases': [*[{**case, **known.get(case['case_id'], {})} for case in ready['cases']],
                              *[case for cid, case in known.items() if cid not in {c['case_id'] for c in ready['cases']}]]}
        # One explicit lifecycle repair after verified exit. Ordinary reconnects
        # retain the profile/context ID and do not call the platform at all.
        replacement_calls = 0
        replacement = assignment.get('replace_exited_environment')
        if replacement and previous.get('lease_id'):
            if environment is None:
                raise ValueError('环境替换只用于原节点的真实隔离环境')
            if not isinstance(replacement, dict):
                raise ValueError('replace_exited_environment 必须为原退出依据')
            request = {**replacement, 'browser_environments': environment['environments']}
            if resume:
                # The claim transaction distinguishes an active original lease
                # from an ended lease; never checkpoint the ended one first.
                assignment.setdefault('claim_arguments', {})['native_environment_replacement'] = {
                    **request, 'lease_id': previous['lease_id']}
            else:
                repair = client.call('direct_test_session', {**identity, 'action': 'checkpoint',
                    'lease_id': previous['lease_id'], 'checkpoint': {'native_environment_replacement': request}})
                replacement_calls = 1
                previous['native_context_binding'] = repair['native_context_binding']
                write_private_json(binding_file, previous)
                write_private_json(root / 'environment-replacement.json', repair)
        if state['state'] == 'ready' and not resume:
            return reused_ready(replacement_calls + reconciliation_calls)
        if state['state'] == 'waiting' and not resume:
            return {'state': 'waiting', 'ready': False, 'end_turn': True, 'http_calls': 0}
        if state['state'] == 'stopped' and not resume:
            return {'state': 'stopped', 'ready': False, 'end_turn': True, 'http_calls': 0}
        started = time.monotonic()
        calls = reconciliation_calls

        def step(name, tool, args):
            nonlocal calls
            if name in recovered:
                response = recovered[name]
                write_private_json(root / (name + '.json'), response)
                return response
            state.update(state='pending', stage=name)
            if name in {'claim', 'baseline'}:
                state[name + '_outcome'] = 'unknown'
            state['stages'][name] = {'started_at': datetime.now(timezone.utc).isoformat(), 'request': copy.deepcopy(args)}
            write_private_json(ledger, state)
            begin = time.monotonic()
            try:
                calls += 1
                response = client.call(tool, args)
                write_private_json(root / (name + '.json'), response)
            except Exception as error:
                state.update(state='failed', error_type=type(error).__name__, error=str(error))
                if name in {'claim', 'baseline'} and getattr(error, 'status', None) in {400, 401, 403, 404, 409, 422}:
                    # Baseline persistence has post-write reporting work. A
                    # failed HTTP response alone cannot establish no write.
                    state[name + '_outcome'] = 'rejected' if name == 'claim' else 'unknown'
                    state['stages'][name]['http_status'] = error.status
                write_private_json(ledger, state)
                raise
            if name in {'claim', 'baseline'}:
                state[name + '_outcome'] = 'confirmed'
            state['stages'][name].update(finished_at=datetime.now(timezone.utc).isoformat(),
                                         seconds=round(time.monotonic() - begin, 3))
            return response

        claim_args = {**identity, 'action': 'claim'}
        claim_configuration = assignment.get('claim_arguments') or {}
        account_ids = claim_configuration.get('account_ids')
        if account_ids is not None:
            claim_args['account_ids'] = account_ids
        environments = {key: copy.deepcopy(claim_configuration.get(key, assignment.get(key)))
                        for key in ('browser_environment', 'browser_environments', 'native_environment_replacement', 'account_selection', 'work_token')
                        if key in claim_configuration or key in assignment}
        if environments:
            claim_args['arguments'] = environments
        claim = step('claim', 'direct_test_session', claim_args)
        if not claim.get('lease_id') or claim.get('state') != 'running':
            waiting = claim.get('state') in {'queued', 'waiting'}
            state['state'] = 'waiting' if waiting else 'stopped'
            write_private_json(ledger, state)
            return {'state': state['state'], 'ready': False, 'end_turn': True,
                    'http_calls': calls, 'receipt_file': str(root / 'claim.json')}
        changed_lease = bool(previous.get('lease_id') and previous['lease_id'] != claim['lease_id'])
        if changed_lease and not resume:
            raise ValueError('续接租约已变化；保留原准备和观察，先核对原任务')
        binding = {**({} if changed_lease else previous), **identity,
                   'workspace_url': client.url, 'lease_id': claim['lease_id']}
        if 'account_ids' in claim:
            binding['account_ids'] = list(claim['account_ids'])
        if claim.get('native_context_binding'):
            binding['native_context_binding'] = copy.deepcopy(claim['native_context_binding'])
        if claim_configuration.get('work_token'):
            binding['work_token'] = copy.deepcopy(claim_configuration['work_token'])
        recovered_node = (recovered.get('context') or {}).get('node') or {}
        if recovered_node.get('checkpoint', {}).get('work_plan'):
            binding['work_plan'] = copy.deepcopy(recovered_node['checkpoint']['work_plan'])
            selection = recovered_node.get('work_selection')
            if selection:
                binding['work_token'] = {k: selection[k] for k in ('work_unit_id', 'plan_revision', 'requirements_digest')}
        if changed_lease:
            binding['previous_bindings'] = [*previous.get('previous_bindings', []),
                {k: copy.deepcopy(v) for k, v in previous.items() if k != 'previous_bindings'}]
        write_private_json(binding_file, binding)  # Cleanup remains possible after any later failure.
        if state.get('ready') and not changed_lease:
            state['state'] = 'ready'
            write_private_json(ledger, state)
            return reused_ready(calls)
        context = step('context', 'direct_test_session', {**identity, 'action': 'context', 'lease_id': claim['lease_id']})
        if context.get('mode') != 'native_browser' or not (context.get('project') or {}).get('id'):
            raise ValueError('当前上下文不可执行；后续基线和业务已停止')
        if context.get('native_context_binding'):
            binding['native_context_binding'] = copy.deepcopy(context['native_context_binding'])
        if (context.get('node') or {}).get('checkpoint', {}).get('work_plan'):
            binding['work_plan'] = copy.deepcopy(context['node']['checkpoint']['work_plan'])
        if context.get('record') and resume:
            anchor = assignment.get('resume_record') or previous
            project, record = context['project'], context['record']
            node, lease = context.get('node') or {}, context.get('lease') or {}
            dispatch = node.get('executor_dispatch') or {}
            if (not anchor.get('project_id') or not anchor.get('execution_id')
                    or project['id'] != anchor['project_id']
                    or record.get('id') != anchor['execution_id']
                    or project.get('ui_execution_id') != anchor['execution_id']
                    or node.get('id') != identity['node_id'] or node.get('task_id') != identity['task_id']
                    or lease.get('id') != claim['lease_id'] or lease.get('node_id') != identity['node_id']
                    or any(dispatch.get(k) != identity[k] for k in ('holder_id', 'dispatch_id'))
                    or not same_executor_ref(dispatch.get('executor_ref'), identity['executor_ref'])
                    or type(record.get('revision')) is not int or record['revision'] < 1):
                raise ValueError('恢复上下文与原任务、执行会话或执行记录不一致；不能接入其他记录')
            if context.get('prior_operations'):
                raise ValueError('原操作仍有未知或待确认结果；先核对原操作，不重放业务')
            prepared = native_design({'cases': record.get('cases')}, allow_results=True)
            counts = {}
            for case in active_cases(prepared):
                counts[case['status']] = counts.get(case['status'], 0) + 1
            binding.update(project_id=project['id'], execution_id=record['id'], revision=record['revision'],
                           case_counts=counts, case_results={c['case_id']: c for c in prepared},
                           coverage=copy.deepcopy(record.get('coverage', [])))
            write_private_json(binding_file, binding)
            if (root / 'design.json').exists():
                history = state.setdefault('resume_history', [])
                history.append({'ready': copy.deepcopy(state.get('ready')),
                                'design': json.loads(read_utf8(root / 'design.json'))})
            write_private_json(root / 'design.json', {'cases': prepared,
                **{key: copy.deepcopy(record[key]) for key in
                   ('coverage', 'review_notes', 'review_revision', 'requirement_design') if key in record},
                'resumed_execution_id': record['id']})
            ready = {'state': 'ready', 'ready': True, 'resumed': True, 'binding_file': str(binding_file),
                     'design_file': str(root / 'design.json'), 'project_id': project['id'],
                     'execution_id': record['id'], 'revision': record['revision'], 'cases': prepared,
                     'coverage': binding['coverage'],
                     **({'native_context_binding': binding['native_context_binding']}
                        if binding.get('native_context_binding') else {}),
                     'accounts': [{key: account.get(key) for key in ('id', 'label', 'identity', 'tenant')}
                                  for account in context.get('accounts', [])],
                     'http_calls': calls, 'seconds': round(time.monotonic() - started, 3)}
            state.update(state='ready', ready=ready, fingerprint=fingerprint)
            write_private_json(ledger, state)
            return ready
        if context.get('record'):
            raise ValueError('已有执行记录，不能以新基线覆盖；沿原回执恢复')
        if resume and (assignment.get('resume_record') or previous.get('execution_id')):
            raise ValueError('原执行记录不可用；不能以新基线代替原轮次')
        pid = context['project']['id']
        prefix = context['case_id_prefix']
        id_map = {case['case_id']: prefix + str(index + 1).zfill(3) for index, case in enumerate(cases)}
        # Keep dependency structures intact. Rewrite only exact selected case IDs.
        def remap(value):
            if isinstance(value, dict): return {k: remap(v) for k, v in value.items()}
            if isinstance(value, list): return [remap(v) for v in value]
            return id_map.get(value, value) if isinstance(value, str) else value
        prepared = remap(cases)
        for case in prepared:
            check_case_batch([case])
        prepared_inventory = remap(inventory) if inventory is not None else []
        saved = step('baseline', 'save_ui_test_cases', {'project_id': pid, 'cases': prepared,
            **({'coverage': prepared_inventory} if inventory is not None else {}), 'response': 'summary'})
        if not saved.get('execution_id') or type(saved.get('revision')) is not int:
            raise ValueError('基线未返回有效执行记录；不生成可执行业务状态')
        binding.update(project_id=pid, execution_id=saved['execution_id'], revision=saved['revision'],
                       coverage=prepared_inventory, case_results={c['case_id']: c for c in prepared},
                       coverage_check=saved.get('coverage_check', {}))
        write_private_json(binding_file, binding)
        write_private_json(root / 'design.json', {'cases': prepared, 'coverage': prepared_inventory, 'source_case_ids': id_map})
        ready = {'state': 'ready', 'ready': True, 'binding_file': str(binding_file),
                 'design_file': str(root / 'design.json'), 'project_id': pid,
                 'execution_id': saved['execution_id'], 'revision': saved['revision'],
                 **({'native_context_binding': binding['native_context_binding']}
                    if binding.get('native_context_binding') else {}),
                 'accounts': [{key: account.get(key) for key in ('id', 'label', 'identity', 'tenant')}
                              for account in context.get('accounts', [])],
                 'cases': prepared, 'coverage': prepared_inventory,
                 'baseline_receipt': saved, 'http_calls': calls, 'seconds': round(time.monotonic() - started, 3)}
        state.update(state='ready', ready=ready)
        write_private_json(ledger, state)
        return ready


def native_pending_receipt_matches(pending, receipt, binding, *, request_id=None, client=None):
    fields = ('task_id', 'node_id', 'holder_id', 'lease_id', 'project_id', 'execution_id')
    if request_id is not None and pending.get('request_id', request_id) != request_id:
        return False
    if any(receipt.get('binding', {}).get(key) != binding.get(key) for key in fields):
        return False
    if pending.get('binding') and any(pending['binding'].get(key) != binding.get(key) for key in fields):
        return False
    expected = pending.get('payload') or {'cases': [{key: pending.get(key) for key in ('case_id', 'status', 'actual')}]}
    if 'asset_files' in expected:
        if client is None:
            return False
        try:
            expected = {**expected, 'assets': [client.asset_from_file(**{key: item[key] for key in
                ('file', 'case_id', 'step', 'kind', 'captured_at', 'filename', 'content_type') if key in item})
                for item in expected['asset_files']]}
            expected.pop('asset_files')
        except (ValueError, OSError):
            return False
    result = receipt.get('result') or {}
    before = receipt.get('revision_before')
    return (receipt.get('state') == 'saved' and receipt.get('payload') == expected
            and type(before) is int and type(result.get('revision')) is int
            and result['revision'] == before + 1 and result.get('execution_id') == binding.get('execution_id')
            and result['revision'] <= binding.get('revision', 0))


def native_rejection_proof_matches(proof, binding, fingerprint):
    return (isinstance(proof, dict) and proof.get('source') == 'platform_record_readback'
            and proof.get('fingerprint') == fingerprint and bool(fingerprint)
            and proof.get('execution_id') == binding.get('execution_id')
            and type(proof.get('revision')) is int and type(binding.get('revision')) is int
            and proof['revision'] <= binding['revision'])


def native_rejection_confirmed(receipt, binding):
    """Only an authenticated unchanged revision proves a failed POST did not save."""
    try:
        identity = {k: receipt[k] for k in ('workspace_url', 'binding', 'payload')}
        fields = ('holder_id', 'task_id', 'node_id', 'lease_id', 'project_id', 'execution_id')
        proof = receipt.get('rejection_confirmed')
        return (receipt.get('state') == 'rejected'
            and type(receipt.get('http_status')) is int and 400 <= receipt['http_status'] < 500
            and identity['workspace_url'] == binding.get('workspace_url')
            and all(receipt['binding'].get(k) == binding.get(k) for k in fields)
            and receipt.get('fingerprint') == hashlib.sha256(json.dumps(
                identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            and native_rejection_proof_matches(proof, binding, receipt['fingerprint'])
            and proof['revision'] == receipt.get('revision_before'))
    except (KeyError, TypeError, ValueError):
        return False


def native_final_review_unconfirmed(binding):
    review = binding.get('final_review') or {}
    return (review.get('state') in {'pending', 'unknown'}
        or review.get('state') == 'rejected' and not native_rejection_proof_matches(
            review.get('rejection_confirmed'), binding, review.get('fingerprint')))


def native_observation_settled(root, response, binding):
    if response.get('saved') is True or response.get('state') == 'not_sent':
        return True
    if response.get('state') != 'rejected' or not response.get('record_receipt_file'):
        return False
    try:
        receipt = json.loads(read_utf8(Path(response['record_receipt_file'])))
    except (ValueError, OSError):
        return False
    return native_rejection_confirmed(receipt, binding)


def clear_rejected_native_observation(root, binding):
    """A proved rejected request did not write; retain its receipt, clear only its fence."""
    marker = Path(root) / 'observation-pending.json'
    if not marker.exists():
        return False
    try:
        pending = json.loads(read_utf8(marker))
        receipt = json.loads(read_utf8(Path(pending['receipt_file'])))
        cases = receipt['payload'].get('cases', [])
        if (not native_rejection_confirmed(receipt, binding)
                or not any(all(case.get(k) == pending.get(k) for k in ('case_id', 'status', 'actual')) for case in cases)):
            return False
    except (KeyError, TypeError, ValueError, OSError):
        return False
    marker.unlink()
    return True


def observed_native(client, binding_file, case_id, status, actual, receipt_file, *, details=None, asset_files=None, request_id=None):
    if status not in {'passed', 'failed', 'partial', 'blocked', 'pending_action', 'pending_rule'}:
        raise ValueError('必须提供真实判定，不从动作成功猜测通过')
    if not isinstance(actual, str):
        raise ValueError('实际观察必须为文本')
    design = json.loads(read_utf8(Path(binding_file).parent / 'design.json'))
    if case_id not in {c['case_id'] for c in design['cases']}:
        raise ValueError('结果不属于本轮已准备设计')
    state = json.loads(read_utf8(Path(binding_file).parent / 'preparation.json'))
    if state.get('state') != 'ready':
        raise ValueError('准备未完成，不能继续保存业务结果')
    marker = Path(binding_file).parent / 'observation-pending.json'
    binding = json.loads(read_utf8(binding_file))
    clear_rejected_native_observation(marker.parent, binding)
    if details is not None and (not isinstance(details, dict) or {'case_id', 'status', 'actual'} & set(details)):
        raise ValueError('case_changes 仅包含本条用例的显式变化，身份、判定及实际观察沿用原观察')
    changes = {**(details or {}), 'case_id': case_id, 'status': status, 'actual': actual}
    content = {'cases': [changes], **({'asset_files': asset_files} if asset_files is not None else {})}
    current = {'case_id': case_id, 'status': status, 'actual': actual,
               'receipt_file': str(Path(receipt_file).absolute())}
    if request_id is not None:
        current['request_id'] = request_id
    if details or asset_files is not None:
        current['payload'] = content
    if marker.exists() and json.loads(read_utf8(marker)) != current:
        raise ValueError('前条结果未确认保存，后续步骤已停止；先核对原回执')
    write_private_json(marker, current)
    # Preserve supplied steps/checkpoints/evidence at the observation boundary.
    # The normal case and asset validators remain authoritative.
    try:
        result = client.native_record(binding_file, content, receipt_file)
        if result.get('saved') is False:
            raise ValueError('原请求已核实未保存；保留拒绝回执，修正后使用新回执补交，不重跑业务')
    except Exception as error:
        if clear_rejected_native_observation(marker.parent, binding):
            error.native_receipt_state = 'rejected'
            error.native_receipt_file = str(receipt_file)
        elif (type(error) is ValueError and not Path(receipt_file).exists()
                and json.loads(read_utf8(marker)) == current):
            marker.unlink()
            error.native_receipt_state = 'not_sent'
        raise
    marker.unlink()
    return result


def observation_actual(observation):
    """Render observations captured at the assertion boundary, without an LLM rewrite."""
    if not isinstance(observation, dict):
        raise ValueError('观察必须为对象')
    checks = observation.get('checks')
    if not isinstance(checks, list) or not checks:
        raise ValueError('缺少实际逐项观察 checks')
    lines = []
    for check in checks:
        if (not isinstance(check, dict) or not isinstance(check.get('name'), str)
                or not check['name'].strip() or 'expected' not in check or 'observed' not in check
                or type(check.get('ok')) is not bool):
            raise ValueError('检查项需要 name/expected/observed/ok；不猜测判定')
        lines.append(json.dumps(check, ensure_ascii=False, allow_nan=False))
    return '\n'.join(lines)


def observed_native_json(client, binding_file, observation, observation_file, receipt_file, *, request_id=None):
    # An incomplete case can later advance. Keep each real observation immutable;
    # equal observations retain their original receipt, unknown saves still fence the next one.
    payload = json.dumps(observation, sort_keys=True, ensure_ascii=False, allow_nan=False)
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    source, receipt = Path(observation_file), Path(receipt_file)
    protected = {Path(binding_file).resolve(), *(Path(binding_file).parent.joinpath(name).resolve()
                  for name in ('design.json', 'preparation.json', 'observation-pending.json'))}
    if source.resolve() in protected or receipt.resolve() in protected or source.resolve() == receipt.resolve():
        raise ValueError('观察与回执不能覆盖原绑定、设计或相互覆盖')
    source = source.with_name(source.stem + '-' + digest + source.suffix)
    receipt = receipt.with_name(receipt.stem + '-' + digest + receipt.suffix)
    if source.exists() and json.loads(read_utf8(source)) != observation:
        raise ValueError('已有不同观察，不覆盖或重跑')
    write_private_json(source, observation)
    actual = observation_actual(observation)
    result = observed_native(client, binding_file, observation.get('case_id'), observation.get('status'), actual, receipt,
        details=observation.get('case_changes'), asset_files=observation.get('asset_files'), request_id=request_id)
    return {**result, 'observation_file': str(source), 'receipt_file': str(receipt)}


def native_closeout_arguments(binding, *, browser_stopped, reason, save_unconfirmed=False, defer_report=False, outcome='completed'):
    if outcome not in {'completed', 'yield'}:
        raise ValueError('收尾 outcome 必须为 completed 或 yield')
    if browser_stopped is not True or not isinstance(reason, str) or not reason.strip():
        raise ValueError('必须在实际关闭本任务页面后明确 browser-stopped 和退出依据')
    fields = ('holder_id', 'task_id', 'node_id', 'lease_id')
    if any(not isinstance(binding.get(k), str) or not binding[k] for k in fields):
        raise ValueError('缺少原领取绑定，不能构造交还请求')
    save_unconfirmed = save_unconfirmed or native_final_review_unconfirmed(binding)
    counts = binding.get('case_counts') or {}
    result = ('partial' if save_unconfirmed else 'failed' if counts.get('failed') else 'passed' if counts.get('passed') and
              sum(counts.values()) == counts['passed'] else 'partial')
    publish = outcome == 'completed' and not (save_unconfirmed or defer_report)
    return {**{k: binding[k] for k in (*fields, 'dispatch_id', 'executor_ref') if k in binding},
            'action': 'finish', 'outcome': outcome,
            'reason': reason, 'arguments': {'browser_stopped': True, 'result': result,
                                           # Passing the registered cases does not prove all module branches were explored.
                                           'coverage_complete': False, 'publish_saved': publish,
                                           **({'publication_binding': {key: binding[key] for key in
                                                ('project_id', 'execution_id', 'revision')}}
                                              if publish and all(key in binding for key in
                                                ('project_id', 'execution_id', 'revision')) else {}),
                                           **({'report_pending': True} if defer_report and outcome == 'completed' else {}),
                                           **({'save_unconfirmed': True} if save_unconfirmed else {})}}


def native_review_state(binding_file):
    """Reuse saved receipts, without another platform read or invented review."""
    binding_file = Path(binding_file)
    binding = json.loads(read_utf8(binding_file))
    design_file = binding_file.parent / 'design.json'
    design = json.loads(read_utf8(design_file)) if design_file.exists() else {}
    cases = list(binding.get('case_results', {}).values()) if 'case_results' in binding else design.get('cases', [])
    remaining = {}
    pending_actions = []
    for case in active_cases(cases):
        points = [p for p in case.get('checkpoints', []) if p.get('status') == 'pending_action']
        # Saved checkpoints use manual_step semantics, not an action_type
        # field. The parent action is derived from the first pending point.
        for item in points or [case]:
            if item.get('status') == 'pending_action':
                pending_actions.append({'case_id': case['case_id'],
                    **({'checkpoint_id': item['id']} if item is not case else {}),
                    'action_type': 'manual_step' if item is not case else item.get('action_type') or 'unspecified',
                    'action_required': item.get('action_required') or ''})
        status = case.get('status', 'not_run')
        if status in {'passed', 'failed'}:
            continue
        category = (case.get('action_type') or 'pending_action_unspecified') if status == 'pending_action' else status
        remaining.setdefault(category, []).append(case['case_id'])
    by_id = {c['case_id']: c for c in active_cases(cases)}
    unfinished = []
    plan = binding.get('work_plan') or {}
    if all(plan.get(k) == binding.get(k) for k in ('project_id', 'execution_id')):
        for unit in plan.get('units', []):
            if unit.get('purpose') == 'cleanup':
                # Business assertions do not settle cleanup. The local cache has no
                # authoritative work_unit_receipts; reconcile existing proof only.
                unfinished.append({'unit_id': unit['id'],
                    'case_ids': list(dict.fromkeys([*unit.get('case_ids', []),
                        *(p['case_id'] for p in unit.get('checkpoint_refs', []))])),
                    'completion_requires_receipt': True})
                continue
            pending = []
            for cid in unit.get('case_ids', []):
                case = by_id.get(cid, {})
                if case and case.get('status') not in {'passed', 'failed'} and not case_excluded(case):
                    pending.append(cid)
            for ref in unit.get('checkpoint_refs', []):
                case = by_id.get(ref.get('case_id'), {})
                point = next((p for p in case.get('checkpoints', []) if p['id'] == ref.get('checkpoint_id')), {})
                if point and point.get('status') not in {'passed', 'failed'} and not case_excluded(case):
                    pending.append(ref['case_id'])
            if pending:
                unfinished.append({'unit_id': unit['id'], 'case_ids': list(dict.fromkeys(pending))})
    boundary = None
    boundary_file = binding_file.parent / 'work-boundary.json'
    if boundary_file.exists():
        saved = json.loads(read_utf8(boundary_file))
        if all(saved.get('request', {}).get(k) == binding.get(k) for k in ('task_id', 'node_id', 'lease_id')):
            boundary = saved.get('result')
    # Local material, not a semantic verdict. Keep every source area, including
    # areas without cases, and every case (not just failures). No platform read.
    review_file = binding_file.parent / 'scope-review.json'
    write_private_json(review_file, {
        'execution_id': binding.get('execution_id'), 'revision': binding.get('revision'),
        'coverage': binding.get('coverage', design.get('coverage', [])),
        'requirement_design': design.get('requirement_design', {}), 'cases': cases,
        'remaining_by_status': remaining, 'semantic_review_complete': False,
        'pending_actions': pending_actions, 'unfinished_work_units': unfinished, 'resource_boundary': boundary,
        'instruction': '对照本轮 get_test_document 原目标和附件逐项核对；本材料不是范围完整证明。'
            'review_notes 记录来源/独立分支/用例ID/证据/缺口及下一步；缺失来源必须补读，不能从用例标题反推。'
            '授权、人工步骤、规则、依赖和未准备分开核实；分组只沿已保存状态，不代表原因已确认。'
            'unfinished_work_units 是原计划仍需核对的工作；completion_requires_receipt=true 的清理阶段须核对原结算凭据，不能由业务通过推定完成，也不要求重跑清理。resource_boundary 是原租约最近保存的边界回执，不是当前资源授权。'
            '普通资源等待、共享转独占和可准备样本不能解释为测不了；在当前可做项结束后按原 yield 临时交还并等原事件。'
            '测不了就跳过/别问我不等于取消这些可续接阶段，也不要求只读样本必须本轮创建；Codex 逐分支判断真实缺口。'})
    return {'execution_id': binding.get('execution_id'), 'revision': binding.get('revision'),
            'counts': binding.get('case_counts', {}), 'coverage_check': binding.get('coverage_check', {}),
            'cases_file': str(binding_file.parent / 'design.json'),
            'scope_review_file': str(review_file), 'unfinished_work_units': unfinished,
            'resource_boundary': boundary,
            'binding_file': str(binding_file), 'final_review': binding.get('final_review', {}),
            'observation_pending': (binding_file.parent / 'observation-pending.json').exists(),
            'notice': '复用已存设计、结果和动态缺口；只补真实变化。统计不代表已完成覆盖回查。'}


def native_correction_scope(binding):
    """Pin confirmation to the current original identity, generation and revision."""
    return {key: binding[key] for key in ('workspace_url', 'holder_id', 'task_id', 'node_id',
        'lease_id', 'project_id', 'execution_id', 'revision', 'account_id', 'account_ids',
        'dispatch_id', 'executor_ref', 'coordinator_ref', 'native_context_binding') if key in binding}


def native_correction_evidence(root, request_id, binding, correction_file, *, confirmed_revision=None):
    """Validate explicit original/correction evidence without reading the platform."""
    import re
    if not isinstance(request_id, str) or not re.fullmatch(r'[0-9]+-[a-f0-9]+', request_id):
        raise ValueError('纠正关联缺少原观察 request_id')
    root = Path(root).resolve()
    paths = {'observation': root / ('observation-inbox-' + request_id + '.json'),
             'response': root / ('native-receiver-response-' + request_id + '.json'),
             'correction': Path(correction_file).absolute()}

    def load(path):
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
            raise ValueError('纠正关联仅使用原普通证据文件')
        return json.loads(read_utf8(path))

    response = load(paths['response'])
    if response.get('request_id') != request_id or response.get('state') != 'unknown' or response.get('saved') is not False:
        raise ValueError('纠正关联仅处理原请求的未知保存，不改原回执')
    paths['original'] = Path(response['record_receipt_file']).absolute()
    if paths['original'].resolve().parent != root or paths['original'].resolve() == paths['correction'].resolve():
        raise ValueError('独立纠正回执不能替换原未知保存')
    original, correction = load(paths['original']), load(paths['correction'])
    fields = ('holder_id', 'task_id', 'node_id', 'lease_id', 'project_id', 'execution_id')
    for receipt in (original, correction):
        identity = {key: receipt[key] for key in ('workspace_url', 'binding', 'payload')}
        if (receipt['workspace_url'] != binding.get('workspace_url') or any(
                receipt['binding'].get(key) != binding.get(key) for key in fields)
                or any(receipt['binding'].get(key) != binding.get(key) for key in ('account_id',)
                       if key in receipt['binding'] or key in binding)
                or receipt.get('fingerprint') != hashlib.sha256(json.dumps(
                    identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()):
            raise ValueError('纠正关联的原绑定、账号、测试台或指纹不一致')
        before, request = receipt.get('revision_before'), receipt.get('request') or {}
        arguments = request.get('arguments') or {}
        expected = {**receipt['payload'], 'project_id': binding['project_id'],
                    'execution_id': binding['execution_id'], 'revision': before,
                    'response': 'summary', 'include_saved_design': True}
        if 'cases' in expected:
            expected['cases'] = native_checkpoint_observations(expected['cases'], receipt.get('case_baselines', {}))
        if (type(before) is not int or before < 1 or arguments != expected
                or request.get('action') != 'record' or request.get('record_action') != 'cases'
                or any(request.get(key) != binding.get(key) for key in (*fields[:4], 'account_id'))):
            raise ValueError('纠正关联的原保存请求、载荷或修订不一致')
    observation = load(paths['observation'])
    expected_original = {'cases': [{**(observation.get('case_changes') or {}),
        'case_id': observation.get('case_id'), 'status': observation.get('status'),
        'actual': observation_actual(observation)}]}
    if original.get('state') != 'unknown' or original['payload'] != expected_original:
        raise ValueError('原观察与完整未知保存载荷不一致；资产须沿原证据入口核对')

    def contains(expected, actual):
        if isinstance(expected, dict):
            return isinstance(actual, dict) and all(k in actual and contains(v, actual[k]) for k, v in expected.items())
        return type(expected) is type(actual) and expected == actual

    old_case = expected_original['cases'][0]
    corrected_cases = correction['payload'].get('cases', [])
    if not any(contains(old_case, case) for case in corrected_cases):
        raise ValueError('独立纠正没有完整保留原用例的全部提交字段')
    result, before = correction.get('result') or {}, correction['revision_before']
    if (correction.get('state') != 'saved' or type(result.get('revision')) is not int
            or result['revision'] != before + 1
            or result['revision'] != (binding.get('revision') if confirmed_revision is None else confirmed_revision)
            or result.get('execution_id') != binding['execution_id'] or before < original['revision_before']):
        raise ValueError('纠正保存须为当前原记录的精确下一修订')
    try:
        old_end = datetime.fromisoformat(original['client_timing']['finished_at'].replace('Z', '+00:00'))
        new_start = datetime.fromisoformat(correction['started_at'].replace('Z', '+00:00'))
        new_end = datetime.fromisoformat(correction['client_timing']['finished_at'].replace('Z', '+00:00'))
        if old_end.tzinfo is None or new_start.tzinfo is None or new_end.tzinfo is None or not old_end < new_start <= new_end:
            raise ValueError('保存时序不一致')
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('独立纠正必须晚于原未知保存结束') from error
    evidence = {key: {'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                for key, path in paths.items()}
    return original, correction, evidence


def native_observation_correction(root, request_id, binding):
    """Revalidate a durable explicit resolution; no authority cache or network."""
    try:
        root = Path(root)
        path = root / ('native-observation-correction-' + str(request_id) + '.json')
        if path.is_symlink() or not path.is_file():
            return False
        proof = json.loads(read_utf8(path))
        original, correction, evidence = native_correction_evidence(
            root, request_id, binding, proof['evidence']['correction']['file'], confirmed_revision=proof['revision'])
        scope = native_correction_scope(binding)
        confirmed_scope = proof.get('binding') or {}
        if (proof.get('resolution') != 'corrected_by_saved_receipt' or proof.get('request_id') != request_id
                or {k:v for k,v in confirmed_scope.items() if k != 'revision'} != {k:v for k,v in scope.items() if k != 'revision'}
                or confirmed_scope.get('revision') != proof['revision']
                or type(binding.get('revision')) is not int or binding['revision'] < proof['revision']
                or proof.get('evidence') != evidence
                or proof.get('original_revision_before') != original['revision_before']
                or proof.get('revision') != correction['result']['revision']):
            return False
        native_save_readback(correction, proof['record'], correction.get('case_baselines', {}))
        return True
    except (KeyError, TypeError, ValueError, OSError):
        return False


def native_observation_corrected(root, request_id, binding, receipt):
    response = root / ('native-receiver-response-' + str(request_id) + '.json')
    observation = root / ('observation-inbox-' + str(request_id) + '.json')
    if not response.exists() or not observation.exists():
        return False
    saved = json.loads(read_utf8(response))
    if saved.get('request_id') != request_id or saved.get('state') not in {'not_sent', 'rejected'}:
        return False
    try:
        rejected_at = datetime.fromisoformat(saved['timing']['save_finished_at'].replace('Z', '+00:00'))
        corrected_at = datetime.fromisoformat(receipt['started_at'].replace('Z', '+00:00'))
        if corrected_at <= rejected_at:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    case_id = json.loads(read_utf8(observation)).get('case_id')
    return (receipt.get('state') == 'saved' and all(receipt.get('binding', {}).get(key) == binding.get(key)
            for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'project_id', 'execution_id'))
            and any(case.get('case_id') == case_id and 'status' in case and 'actual' in case
                    for case in receipt.get('payload', {}).get('cases', [])))


def remember_native_observation_corrections(binding_file, binding, receipt_file, receipt):
    root = Path(binding_file).parent
    for name in ('native-observation-awaiting.json', 'native-last-observation.json'):
        pointer = root / name
        if pointer.exists():
            request_id = json.loads(read_utf8(pointer)).get('request_id')
            if native_observation_corrected(root, request_id, binding, receipt):
                binding.setdefault('observation_corrections', {})[request_id] = str(receipt_file)


def native_publication_ready(binding_file, binding):
    """Confirm actual saves, including requests queued before a POST marker."""
    root = Path(binding_file).parent
    clear_rejected_native_observation(root, binding)
    if (root / 'observation-pending.json').exists() or native_final_review_unconfirmed(binding):
        return False
    checked = set()
    for name in ('native-observation-awaiting.json', 'native-last-observation.json'):
        pointer = root / name
        if not pointer.exists():
            continue
        request_id = json.loads(read_utf8(pointer)).get('request_id')
        if request_id in checked:
            continue
        checked.add(request_id)
        response = root / ('native-receiver-response-' + str(request_id) + '.json')
        saved = json.loads(read_utf8(response)) if response.exists() else {}
        if saved.get('request_id') == request_id and native_observation_settled(root, saved, binding):
            continue
        if native_observation_correction(root, request_id, binding):
            continue
        return False
    return True


def native_work_plan(client, binding_file, plan):
    """Register original stages without requiring an ended execution lease."""
    binding_file = Path(binding_file)
    with batch_lock(binding_file):
        binding = json.loads(read_utf8(binding_file))
        if binding.get('workspace_url', client.url) != client.url or not isinstance(plan, dict):
            raise ValueError('Work plan does not belong to the original binding')
        if not native_publication_ready(binding_file, binding):
            raise ValueError('Confirm original observations before a work-plan boundary')
        for key in ('project_id', 'execution_id'):
            if key in plan and plan[key] != binding[key]:
                raise ValueError('Work plan cannot replace the original execution record')
        plan = {'schema_version': 1, 'project_id': binding['project_id'], 'execution_id': binding['execution_id'],
                'units': copy.deepcopy(plan.get('units'))}
        request = {key: binding[key] for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'dispatch_id', 'executor_ref') if key in binding}
        revision = (binding.get('work_plan') or {}).get('plan_revision', 0)
        request.update(action='work_plan', arguments={'work_plan': plan, 'expected_plan_revision': revision})
        prior = binding.get('work_plan_request') or {}
        if (prior.get('action') == 'work_plan' and (prior.get('arguments') or {}).get('work_plan') == plan
                and binding.get('work_plan_request_revision') == revision):
            request = prior
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        receipt_file = binding_file.parent / ('work-plan-' + fingerprint + '.json')
        receipt = json.loads(read_utf8(receipt_file)) if receipt_file.exists() else None
        # A saved response describes the previous boundary, not the node's
        # current lifecycle. Every explicit call obtains one authoritative
        # response; pending/unknown recovery still uses the identical request.
        if receipt:
            request = receipt['request']
        receipt = {'state': 'pending', 'request': request}
        write_private_json(receipt_file, receipt)
        result = client.call('direct_test_session', request)
        if result.get('saved') is not True or not isinstance(result.get('work_plan'), dict):
            raise ValueError('Original work-plan receipt is not confirmed')
        receipt.update(state='saved', result=result)
        write_private_json(receipt_file, receipt)
        binding['work_plan'] = receipt['result']['work_plan']
        binding.update(work_plan_request=request, work_plan_request_revision=binding['work_plan']['plan_revision'],
                       work_plan_receipt_file=str(receipt_file))
        write_private_json(binding_file, binding)
        return {**receipt['result'], 'receipt_file': str(receipt_file)}


def native_continuation_kit(client, binding_file, result, command, entry_url=None):
    """Use the original queued run kit in a private formal-generation directory."""
    packet = result.get('continuation_packet')
    if not packet:
        return result
    root = Path(binding_file).absolute().parent
    assignment = packet['assignment']
    node_id = assignment['node_id']
    if not isinstance(node_id, str) or not node_id or any(c not in '0123456789abcdef' for c in node_id):
        raise ValueError('正式续接节点格式不正确')
    target = root / ('continuation-' + node_id)
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.is_symlink():
        raise ValueError('正式续接目录不能为符号链接')
    old_assignment = root / 'assignment.json'
    old = json.loads(read_utf8(old_assignment)) if old_assignment.exists() else {}
    options = {key: copy.deepcopy(old[key]) for key in (
        'direct_browser', 'browser_mode', 'local_artifact_io', 'local_observation_stream',
        'browser_routine_file', 'browser_call_file', 'browser_routine_api') if key in old}
    assignment = {**options, **assignment}
    record = result['source_record']
    assignment_path, design_path, next_binding = target / 'assignment.json', target / 'design.json', target / 'binding.json'
    if not assignment_path.exists():
        write_private_json(assignment_path, assignment)
        write_private_json(design_path, {'cases': record.get('cases', []), 'coverage': record.get('coverage', [])})
        write_private_json(next_binding, {**assignment, 'lease_id': '', 'workspace_url': client.url,
            'project_id': record['project_id'], 'execution_id': record['id'], 'revision': record['revision'],
            'case_results': {c['case_id']: c for c in record.get('cases', [])},
            'coverage': record.get('coverage', []), 'work_plan': result['work_plan']})
    elif json.loads(read_utf8(assignment_path)).get('node_id') != node_id:
        raise ValueError('不能覆盖其他模块的准备目录')
    stop_native_observation_receiver(binding_file)
    result.update(continuation_binding_file=str(next_binding), continuation_assignment_file=str(assignment_path))
    if result['next_action'] == 'prepare_formal_continuation':
        url = entry_url or packet.get('task_material', {}).get('ui_target_url')
        result['continuation_run_kit'] = native_run_kit(command, assignment_path, design_path, target, url)
    return result


def native_work_boundary(client, binding_file, unit_id):
    binding_file = Path(binding_file)
    with batch_lock(binding_file):
        binding = json.loads(read_utf8(binding_file))
        plan = binding.get('work_plan') or {}
        unit = next((u for u in plan.get('units', []) if u['id'] == unit_id), None)
        if not unit or any(plan.get(k) != binding.get(k) for k in ('project_id','execution_id')):
            raise ValueError('先保存原用例的完整阶段计划，不能推测资源要求')
        digest = hashlib.sha256(json.dumps(unit['requires'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        token = {'work_unit_id':unit_id, 'plan_revision':plan['plan_revision'], 'requirements_digest':digest}
        request = {key:binding[key] for key in ('holder_id','task_id','node_id','lease_id')}
        result = client.call('direct_test_session', {**request, 'action':'request_resources', 'arguments':{'work_token':token}})
        write_private_json(binding_file.parent / 'work-boundary.json', {'request':request,'work_token':token,'result':result})
        return result


def native_run_kit(command, assignment_file, design_file, directory, entry_url):
    """Prepare transport once at dispatch; the worker only supplies real observations."""
    from urllib.parse import urlsplit
    import shlex
    if urlsplit(entry_url).scheme not in {'https', 'http'} or not urlsplit(entry_url).netloc:
        raise ValueError('entry-url 必须为已核对的实际业务入口')
    assignment = json.loads(read_utf8(assignment_file))
    resume_existing = bool(assignment.get('resume_record'))
    selected_cases = native_design(json.loads(read_utf8(design_file)), allow_results=resume_existing)
    options = native_isolated_options(assignment, directory)
    isolated = options is not None
    if isolated:
        if options.get('playwright_module') and not Path(options['playwright_module']).is_absolute():
            raise ValueError('显式 Playwright 模块必须为绝对路径；省略则由执行主机自动发现')
        if (assignment.get('browser_routine_file') or assignment.get('browser_call_file')) and assignment.get('browser_routine_api') != 'playwright':
            raise ValueError('独立环境的业务例程须声明 browser_routine_api=playwright；不把旧 cua 控件 API 当作 Playwright Page')
    executor_ref = assignment.get('executor_ref', '')
    target_thread = native_thread_target(executor_ref)
    if not target_thread:
        raise ValueError('缺少原独立执行会话，不能生成派发消息')
    root = Path(directory).absolute()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    ledger_path = root / 'run-ledger.json'
    kit_started = datetime.now(timezone.utc).isoformat()
    if ledger_path.exists():
        ledger = json.loads(read_utf8(ledger_path))
        if any(ledger.get(k) != assignment.get(k) for k in ('task_id', 'node_id')):
            raise ValueError('计时账本属于其他任务，不能覆盖')
    else:
        started_at = assignment.get('lifecycle_started_at') or kit_started
        if datetime.fromisoformat(started_at.replace('Z', '+00:00')).tzinfo is None:
            raise ValueError('链路起点必须带实际时区')
        write_private_json(ledger_path, {'started_at': started_at,
            'start_basis': assignment.get('lifecycle_start_basis') or '执行包生成开始；不包含更早协调准备',
            'task_id': assignment['task_id'], 'node_id': assignment['node_id'], 'kit_started_at': kit_started})
    config = {'command': command, 'assignment_file': str(Path(assignment_file).absolute()),
              'design_file': str(Path(design_file).absolute()), 'directory': str(root), 'entry_url': entry_url}
    if assignment.get('local_observation_stream') is True:
        if assignment.get('local_artifact_io') is not True:
            raise ValueError('本地观察接收需要已核验的原生文件读写能力')
        config['observation_stream'] = True
    path = root / 'native-cycle.js'
    config['control_receipts'] = True
    source = 'const config = ' + json.dumps(config, ensure_ascii=False) + ';\n' + NATIVE_CONTROL_TEMPLATE + '\n' + NATIVE_CYCLE_TEMPLATE
    if path.exists() and read_utf8(path) != source:
        raise ValueError('已有不同执行包，不能覆盖原轮次')
    path.write_text(source, encoding='utf-8')
    path.chmod(0o600)
    browser_path = root / 'native-browser-case.js'
    if browser_path.exists() and read_utf8(browser_path) != NATIVE_BROWSER_TEMPLATE:
        raise ValueError('已有不同浏览器执行包，不能覆盖原轮次')
    browser_path.write_text(NATIVE_BROWSER_TEMPLATE, encoding='utf-8')
    browser_path.chmod(0o600)
    launch = ('const s=await tools.exec_command({cmd:' + json.dumps('cat ' + shlex.quote(str(path))) + ',max_output_tokens:12000});\n'
              'if(s.exit_code!==0)throw new Error("kit unavailable");\n'
              'store(' + json.dumps(str(path)) + ',s.output);\n'
              'const AF=Object.getPrototypeOf(async function(){}).constructor;\n'
              'await new AF("tools","text","ALL_TOOLS","input",s.output)(tools,text,ALL_TOOLS,{action:"prepare"'
              + (',resume:true' if resume_existing else '') + '});')
    # Capability is supplied only after this native environment's ordinary artifact IO
    # has been verified. Do not make every worker rediscover it or retype the helper.
    browser_bootstrap = None
    if assignment.get('local_artifact_io') is True:
        browser_bootstrap = (
            'var nativeArtifactFs=await import("node:fs/promises");\n'
            'var nativeEmit=async observation=>{await nativeArtifactFs.writeFile('
            + json.dumps(str(root / 'observation-native.json'))
            + ',JSON.stringify(observation),{encoding:"utf8",mode:0o600});};\n'
            + NATIVE_BROWSER_TEMPLATE)
    if config.get('observation_stream'):
        browser_bootstrap = (NATIVE_OBSERVATION_SEND_TEMPLATE + '\n'
            + 'var nativeEmit=observation=>nativeSendObservation(' + json.dumps(str(root)) + ',observation);\n'
            + NATIVE_BROWSER_TEMPLATE)
    prompt = (('沿原任务和原执行记录恢复已授权范围；保留全部用例、已执行结果和证据，不重建基线、不重复已完成业务。'
               if resume_existing else '执行本轮已授权范围；复用已有设计和客户端。')
              + '首个工作调用直接执行下列 functions.exec：\n'
              + launch + '\n等待即结束回合，原事件后复用同脚本 input={action:"prepare",resume:true}。'
              'ready 后直接在 entry_url 创建隐藏 IAB，不先开 about:blank；复用返回设计、账号、步骤和预期。'
              '会话首次初始化或重置后的入口须单独执行并阅读工具文档；返回的初始页面状态就是当前证据，不再单独重复 getAXState。'
              '首批设计不是完整模块的范围上限：完整探索需按实际页面补齐成功终点、状态变化、边界和关联链；'
              '明确选定用例的任务仍限原选例范围。复用公共函数，按新观察增量增加设计、coverage 和独立检查点，不重写整个执行脚本。'
              '复用已核验执行包中的纯函数 ' + str(browser_path) + '；它不连平台、不代理浏览器。\n'
              + (('本轮协调者已核验原生环境支持普通本地文件读写；直接使用以下静态函数和导出代码，'
                  '禁止 eval/new Function/动态加载函数；不要无实际失败就回退重抄观察。emit 使用 nativeEmit。\n'
                  + browser_bootstrap) if browser_bootstrap else NATIVE_BROWSER_TEMPLATE) + '\n'
              '可选用 nativeBrowserCase 记录已知步骤和完整逐项 j.check，也可由 Codex 直接观察和操作页面；'
              'j.step 记录耗时和失败位置，j.until 只等待真实状态，禁止重复提交。普通异常返回 interrupted 和原 observation，由 Codex 读取现场、修正定位后继续；'
              '不自动运行 recover/close，不新增失败断言，不因定位失败结束任务。仅决定结束任务时显式关闭并核实真实退出。'
              'emit 使用当前环境已经支持的本地文件输出把原观察直接导出至 ' + str(root / 'observation-native.json') + '，'
              '不在 cua 读取凭据、调用平台或导入平台客户端；若环境不支持文件输出，直接输出原观察并使用既有 JSON 保存。'
              '文件已输出后立即复用生命周期脚本 input={action:"record",observation_file:'
              + json.dumps(str(root / 'observation-native.json')) + '}；'
              '不重抄 checks、不重读文件核对、不再写总结、不中途截图输出整段 base64。原文件包含完整逐项断言和步骤时间。'
              '生命周期源码已在 functions.store 缓存；后续在 functions.exec 使用 load('
              + json.dumps(str(path)) + ') 交给同一 AsyncFunction，不再 cat 脚本。若执行上下文重置才重新读取。'
              '浏览器仅使用当前工具公开 API，未知分支才返回判断；已知操作、真实等待和逐项断言合并，完整状态勿用增量快照猜测。'
              '仅不支持本地导出时，断言现场输出 {case_id,status,checks:[{name,expected,observed,ok}],timing:{last_assertion_at,browser_closed_at}}，'
              '使用真实读取值、布尔比较和实际时间；随即复用上面脚本 input={action:"record",observation:原观察}，'
              '保存成功才做下一条；详细证据与检查点仍按原记录入口保存，不减少断言。'
              '仅在 Codex 明确决定结束任务时，实际清理关页，再给 record 输入 finish_task:true、browser_stopped:true 和真实 reason，'
              '脚本连续保存、交还、通知后继、发布，无需再拼参数或总结；未关页不能声明退出。'
              '未知保存不重发、不重跑，真实阻塞和未探索分支保留缺口；不越过用户授权范围，不另发通知。')
    if config.get('observation_stream'):
        manual_start = prompt.index('emit 使用当前环境已经支持的本地文件输出')
        manual_end = prompt.index('生命周期源码已在 functions.store 缓存', manual_start)
        prompt = prompt[:manual_start] + prompt[manual_end:]
        fallback_start = prompt.index('仅不支持本地导出时，断言现场输出')
        prompt = prompt[:fallback_start] + '未知保存不重发、不重跑，真实阻塞和未探索分支保留缺口；不越过用户授权范围，不另发通知。'
        prompt += ('\n本轮启用已核验本地观察接收器：prepare 已在工具进程中启动原绑定接收器，'
            'nativeEmit 仅通过普通本地文件和命名管道交付观察，并等待真实保存回执；没有网络、凭据、浏览器代理或后台模型。'
            '此模式不要再次调用 record、重抄结果或再保存文件。'
            '每条完成后 emit 在同次原生调用取得真实 save_receipt；saved=true 才允许下一条。'
            '保存失败或响应未知只暂停跨用例推进，保留浏览器和观察。读取原 request_id 的回执核实，不重发、不自动关页或判业务失败。'
            '最后立即执行缓存生命周期代码 input={action:"closeout",browser_stopped:实际关页结果,'
            'reason:真实退出依据,save_unconfirmed:save_receipt.saved!==true}，沿原工具编排交还发布通知。'
            '不要输出全部检查项，返回 case_id/status/检查数/save_receipt 的保存结果和时间；详细原观察已经保存。'
            '本地接收器沿原绑定复用，普通保存错误不退出，只有明确 closeout 才发送停止标记；未知写入仍由原 pending 回执防止重放。')
    review_guidance = ('\n最终回查只提交变化：复用生命周期脚本 input={action:"review",input_file:本地变化JSON绝对路径,receipt_file:本次私有回执绝对路径}。'
        'JSON 可只含 coverage/review_notes/scene_outcome，或 cases 变化批次与 asset_files 本地文件清单；原绑定锁下一次提交并自动更新 revision。'
        '逐条真实结果仍立即保存，不积到收尾。独立初态、输入、边界和预期分支分别使用独立 case_id；同一场景的连续断言才用检查点。'
        '回查从原目标/资料逐项映射独立分支、用例ID、本轮证据、缺口及下一步，写入现有 review_notes；不能仅统计失败或从用例标题反推范围。'
        '授权不足、人工步骤、规则未知、客观依赖、尚未准备与工具中断分开记录，不能混写为权限不足；缺样本或未验证分支保留非通过状态。'
        '保存成功后继续已授权业务或真实清理；明确结束且已核实浏览器退出时可同次带 finish_task:true、browser_stopped:true、reason。'
        '没有变化就直接 closeout；已存数据自动生成报告摘要，不重抄全量用例、不并行 upload-files 和裸 record/finish、不手写修订。'
        '校验失败保留原回执，按一次返回的具体问题修正已有观察，不读取未生成的成功回执、不重跑浏览器动作。')
    review_guidance += ('\n每条 observation 可带 case_changes（原记录字段，如 steps/test_data/checkpoints/action_context）和 asset_files；'
        '把本次已知的真实复现路径、输入、检查点及证据同次保存，不留到最后重写，不重新运行已完成业务。'
        '保存回执已返回动态缺口，原绑定缓存 coverage_check 和 design.json，最终回查直接复用，不为计数再读全量平台记录。'
        '浏览器实际退出后若仍需整理报告，立即调用 input={action:"release",from_observation:true}（或 browser_stopped:true、真实 reason）；'
        '它先交还并通知后继，返回原记录回查信息及本地 scope_review_file，报告保持待补；该材料不是原文核对结论。无需账号或新任务就可沿原绑定补保存。'
        '整理完成只调用 input={action:"complete",input_file:确实变化的JSON路径,receipt_file:本次回执路径}，同次保存变化并发布；'
        '没有变化则 input={action:"complete"} 直接发布。不要重新 claim、重抄汇总、重读全量结果或重复发送交接。'
        'review 带 finish_task:true 且已实际退出时也先交还再保存发布。普通 review 或定位错误仍不结束任务。')
    if assignment.get('browser_call_file'):
        call_source = read_utf8(assignment['browser_call_file'])
        prompt += ('\n以下是协调者按当前选定用例及已核验页面准备的静态调用；先核对与本轮范围一致。'
            '会话首次初始化并读完工具文档后直接复用这些已知步骤，不重新编写公共函数或结果整理逻辑。'
            'nativeCaseId 用本次 prepare 返回的真实编号，nativeTab 用本次专用标签；页面与前置条件变化则保留观察并停止相关步骤，'
            '不能据旧证据直接通过。仍需本次全部真实断言与证据；其他未知新用例继续探索设计，不要求提前编写全部模块脚本。\n'
            + call_source)
    runtime = None
    if assignment.get('browser_routine_file') or config.get('observation_stream'):
        if not config.get('observation_stream'):
            raise ValueError('已加载函数的短调用沿用已核验本地观察入口')
        routine = assignment.get('browser_routine_file') or assignment.get('browser_call_file')
        library = not routine
        call_source = (read_utf8(routine) if routine else
                       'return {run:args=>nativeBrowserCase({...args,preserve:async observation=>{const fs=await import("node:fs/promises");await fs.writeFile(directory+"/native-draft-"+encodeURIComponent(observation.case_id)+".json",JSON.stringify(observation),{encoding:"utf8",mode:0o600});}}),emit:observation=>nativeSendObservation(directory,observation),finish:close=>nativeFinishTask({close,directory}),receipt:(id,options)=>nativeReadObservationReceipt(directory,id,options)};')
        if assignment.get('browser_call_file') and not assignment.get('browser_routine_file'):
            call_source += '\nreturn typeof nativeSummary === "undefined" ? {executed:true} : nativeSummary;'
        receipt_file = assignment.get('browser_runtime_receipt')
        if not receipt_file:
            cache = Path.home() / '.cache' / 'api-test-workspace' / 'native-runtimes'
            cache.mkdir(mode=0o700, parents=True, exist_ok=True)
            identity = hashlib.sha256((executor_ref + NATIVE_BROWSER_TEMPLATE + NATIVE_OBSERVATION_SEND_TEMPLATE + call_source).encode()).hexdigest()
            receipt_file = cache / (identity + '.json')
        runtime = native_runtime_package(call_source, executor_ref, receipt_file,
                                         browser_mode='isolated' if isolated else 'cua')
        receipt_path = Path(runtime['receipt_file'])
        try:
            receipt = json.loads(read_utf8(receipt_path)) if receipt_path.exists() else {}
        except (OSError, ValueError):
            receipt = {}
        if not isinstance(receipt, dict):
            receipt = {}
        loaded = receipt.get('key') == runtime['key'] and same_executor_ref(receipt.get('executor_ref'), executor_ref)
        combined_entry = loaded and not library
        call = native_runtime_call(runtime['key'], root, library=library,
                                   entry_url=entry_url if combined_entry or isolated else None,
                                   browser_mode='isolated' if isolated else 'cua')
        runtime['kind'] = 'library' if library else 'routine'
        runtime['call_source'] = call
        runtime['loaded_receipt'] = loaded
        runtime['combined_entry'] = combined_entry
        if combined_entry and len(selected_cases) == 1:
            write_private_json(root / 'prepared-call.json', {'source': call, 'runtime_key': runtime['key'],
                'binding': {k: assignment[k] for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')}})
        else:
            (root / 'prepared-call.json').unlink(missing_ok=True)
        prompt = ('执行本轮已授权具体设计，首个工作调用直接执行以下 functions.exec：\n' + launch
            + '\n未获资源立即结束，只有原资源事件后 resume:true。ready 后用实际 case_id 设置 nativeCaseId，'
            + ('下面短调用已经包含创建本任务隐藏标签和调用已加载函数，作为一次原生调用执行；'
               '不在它前面另开标签、重复读取或外置原函数已有检查。'
               if combined_entry else '直接在 entry_url 创建本任务隐藏标签 nativeTab；首次初始化单独调用并阅读文档。')
            + '会话首次初始化或实际重置时仍严格遵循原生工具的单入口及文档要求；'
            '平台准备与原生函数加载分开计时；已有设计、账号、清单、步骤直接复用。'
            + ('以下函数已由本执行会话加载并有对应代码摘要回执，不输出、复制或重新定义函数；只执行下面短调用。'
               if loaded else '本原生会话尚无对应加载回执；先在原生工具中静态定义以下函数一次，不执行浏览器业务；首次加载耗时必须列出。\n'
               + runtime['registration_source'])
            + ('\nprepare 返回 native_call 已填入本轮实际 case_id；下一个原生调用直接执行它，不重新拼代码。' if combined_entry and len(selected_cases) == 1 else '\n' + call)
            + ('\n上面的短调用取得本轮公共函数；随后可选用 nativeBrowserCase({case_id:nativeCaseId,run,emit:nativeEmit})，或直接操作公开 Page API；它只是记录辅助函数。'
               '只编写本模块实际业务步骤和完整逐项断言，不重新输出公共函数。run(j) 用 j.step/j.check；j.until 只等待真实状态，不重复提交。'
               '普通操作错误返回 interrupted、observation 和 failed_step，不执行 recover/close、不自动保存失败结论。Codex 观察后决定继续，传 observation:原草稿复用断言与步骤；不重演未知提交。'
               '未知新模块仍侦察实际页面、保存具体设计并边执行边增补，首版不是封闭清单，不能套用其他模块的断言或历史通过。'
               if library else '')
            + '\n使用本次真实页面、账号和完整逐项断言，不复制历史通过；已知步骤连续，未知新范围仍探索增补。'
            '已加载用例内包含的账号、前置条件和结果检查直接在原函数内执行，不在短调用前再执行一遍；'
            '初始页面实际显示登录或其他变化时仅处理必要差异，恢复正常即回到原函数，不另加重复整页读取与账号菜单检查。'
            '保存回执成功才开始下一用例；未知保存先用 nativeReceipt(request_id) 读原回执；实际未知 POST 用 nativeReceipt(request_id,{reconcile:true}) 只读核对原平台记录，保留现场、不重发。函数仅保存代码，不捕获旧标签、账号或保存目录。'
            + ('若原生会话实际重置，使用 environment_recovery_tool_arguments 连接原浏览器并加载同版函数一次，保留旧观察，不重跑已完成业务。'
               '仅明确决定结束任务时，先显式 nativeFinish(()=>nativeBrowserEnvironment.close()) 保存真实退出依据，再在 functions.exec 复用 load('
               if isolated else '旧 cua 会话重置时按公开工具说明重取原标签并加载同版函数；不创建替代浏览器。'
               '仅明确结束时调用 nativeFinish(关闭本任务原标签并核实退出的函数)，保存真实依据，再在 functions.exec 复用 load(') + json.dumps(str(path))
            + ') 的生命周期代码，input={action:"closeout",from_observation:true}；'
            '它读取本轮真实观察回执的退出依据，不另写摘要或拼结果。已保存的完整检查保留。')
    if runtime is None:
        (root / 'prepared-call.json').unlink(missing_ok=True)
    # Both cached-runtime and plain native paths must expose the same review
    # operation. The cached-runtime prompt above replaces the initial prompt.
    prompt += ('\n准备/恢复返回 coverage 与原用例；完整模块按实际页面增补成功终点、状态变化、边界和关联，'
               '首批设计不是范围上限；明确选例仍限原授权范围。' + review_guidance)
    if resume_existing:
        prompt = ('沿原任务、节点和执行记录恢复；prepare 的服务端原记录是当前全部用例及结果，'
                  '保留 case_id、已执行结果和证据，不重建基线、不重跑已完成业务，未知保存先核实。\n' + prompt)
    environment_setup = None
    prompt += ('\n截图仅在关键结果或缺陷仍在时取证，优先 nativeCaptureEvidence({page,case_id,step,directory,preview})，'
        '保留控件与必要上下文，特写仅补充。preview 使用当前工具公开图片展示能力显示同一截图字节，就地看一次是否证明当前缺陷；'
        '不逐动作截图，不重复业务检查，不循环补图，已有证据够用就复用；失败或现场丢失写明缺口。')
    prompt += ('\n领取前复用原资料核对已知目标/账号项目/样本条件；首次登录侦察立即核实 UI 共同前置，不等执行阻塞后才核对。'
        '首版具体用例仍在实际侦察后保存，随后按随包 references/work-stages.md 保存原节点阶段计划；depends_on 只连接必要检查点，不挂无关整批通过条件：'
        '原生命周期 input={action:"work_plan",plan_file:绝对路径}。设计实质扩充时更新同一计划，不合并独立场景。'
        '跨账号/独占边界用 input={action:"work",unit_id:原阶段ID}；continue_current_work 就执行回执中的原场景，'
        '只有 release_required=true 且已真实退出才 input={action:"yield",from_observation:true}，不能冒用 completed/release。'
        '实际模块结束仍用原 release/complete，报告整理不重新占号。')
    environment_recovery = None
    stage_ready_script = None
    if native_claim_configuration(assignment).get('work_token'):
        stage_ready_script = launch.replace('{action:"prepare"' + (',resume:true' if resume_existing else '') + '}', '{action:"stage_ready"}')
    if isolated:
        digest = hashlib.sha256(NATIVE_ISOLATED_BROWSER_TEMPLATE.encode()).hexdigest()[:16]
        helper_path = root / ('native-isolated-browser-' + digest + '.mjs')
        helper_path.write_text(NATIVE_ISOLATED_BROWSER_TEMPLATE, encoding='utf-8')
        helper_path.chmod(0o600)
        environment_setup = ('var nativeIsolatedModule=await import(' + json.dumps(helper_path.as_uri()) + ');\n'
            'var nativeBrowserEnvironment=await nativeIsolatedModule.prepare(' + json.dumps({
                'assignment_file': str(Path(assignment_file).absolute()), 'directory': str(root), 'origin': entry_url})[:-1]
            + ',runtime_context:{cwd:nodeRepl.cwd,homeDir:nodeRepl.homeDir}});\n'
            'nodeRepl.write({environment_ready:true,receipt_file:' + json.dumps(str(root / 'browser-environment.json')) + '});')
        environment_recovery = environment_setup.replace('nativeIsolatedModule.prepare(', 'nativeIsolatedModule.reconnect(').replace(
            'environment_ready:true,receipt_file:',
            'environment_ready:true,recovery_receipt_file:nativeBrowserEnvironment.recovery_receipt_file,receipt_file:')
        # Replace only browser acquisition/exit wording. The existing cached
        # prepare/save/receiver/closeout/handoff instructions remain identical.
        prompt = prompt.replace('ready 后直接在 entry_url 创建隐藏 IAB，不先开 about:blank；',
            'ready 后使用 nativeBrowserEnvironment.enter(entry_url) 取得本任务 Playwright Page；')
        prompt = prompt.replace('直接在 entry_url 创建本任务隐藏标签 nativeTab；首次初始化单独调用并阅读文档。',
            '复用已创建的独立环境；下面短调用取得并复用 nativeTab（真实 Playwright Page）。')
        prompt = prompt.replace('下面短调用已经包含创建本任务隐藏标签和调用已加载函数',
            '下面短调用已经包含取得独立环境页面和调用已加载函数')
        prompt = prompt.replace('在原生 cua 同次调用', '在 node_repl 同次调用')
        prompt += ('\n普通定位失败、页面状态变化先返回 Codex 判断；不串联未知分支。外层工具 timeout_ms 应覆盖本次明确操作和保存预算并留返回余量；'
                   '不使用统一强制防卡计时器、不自动重试或关闭。准备入口给出 environment_tool_arguments；长业务分支按真实观察边界返回。')
        prompt += ('\n点击/截图超时或 REPL 重置后，先保留原始错误、阶段、时间、用例和未保存观察；使用执行包 environment_recovery_tool_arguments 显式重连原环境，'
            '读取本地 browser-diagnostic-*/browser-reconnect-* 回执，再重新取得原 Page、加载同版函数并核实未知提交结果。'
            '重连调用自己超时只表示恢复未确认，不能写成已证明不可恢复；记录最后阶段并继续针对故障排查。'
            '工具层、浏览器进程/连接层、被测接口响应分别报告；业务400不能当连接故障，进程或CDP可达不能当页面恢复或业务通过。'
            '不为恢复另建任务/账号/profile，不自动刷新或重放未知POST；明确停止立即走原收尾，不为了恢复延迟停止。')
        prompt = ('本轮由 Codex 使用原始 Playwright Page API 自己观察和操作；每个账号独立浏览器进程及私有 profile，默认持久上下文不会随 REPL 连接断开销毁。'
            '先阅读当前 node_repl 及 Playwright 公开使用说明，再在持久 node_repl 执行一次下面环境入口；'
            '这是账号 prepare 前的环境创建或连接入口，重复准备连接原 profile 和原页面，不登录、不重放导航或业务。\n'
            + environment_setup + '\n环境成功后继续以下原生命周期包，失败不领取账号；'
            '账号由原 prepare 分配，首次 enter 从原 binding.json 核对一次账号与环境，后续动作直接使用 Page，'
            '没有逐动作授权、HTTP 转发、Runner、心跳或登录前审批。多账号页面在 nativeBrowserEnvironment.pagesByAccount；'
            '凭据沿原 credentials 入口取得并用于实际 UI 登录，原 native_login 证据和状态语义不变。'
            '保留已加载代码、观察接收器、逐条保存、交还确认与计时；普通定位失败不改变任务/用例状态、不关闭浏览器、不交还账号；'
            '若没有启用短调用，ready 后执行 var nativeTab=await nativeBrowserEnvironment.enter('
            + json.dumps(entry_url) + ')，随后执行原用例。等待资源时保留该空环境，原事件续接；部分启动失败或连接丢失需要取消时，可显式 nativeIsolatedModule.closeOwned({assignment_file:原文件,directory:原目录}) 仅关闭存活归属进程，不必先重启死亡进程；'
            '明确取消或结束时才关闭本任务环境。REPL 重置重新连接原进程及 profile；真实进程退出才显式 restart_exited:true，'
            '保留原逻辑 context_id、账号与用例，实际新进程递增 browser_generation 证据；重新读取现场和核实登录，不自动重放业务。旧版确实退出后的替换使用原 assignment.replace_exited_environment 与 checkpoint 原子替换原绑定，不重新排队或新建任务。\n' + prompt)
    role_context = {key: assignment.get(key) for key in ('task_id', 'node_id', 'scope', 'source_project_id', 'project_id')}
    if stage_ready_script:
        prompt = ('首个工作调用先用 functions.exec 执行下列阶段核对；excluded=true 时标记不测且不等资源；其他 stage_ready=false 才结束回合等真实事件，'
                  'stage_ready=true 才执行后文环境准备。不得省略核对或用单账号代替完整集合。\n'
                  + stage_ready_script + '\n' + prompt)
    prompt = ('当前角色worker：仅负责原assignment的本模块。原绑定与资料归属：'
              + json.dumps(role_context, ensure_ascii=False) + '。使用平台随包references/worker.md；'
              '资料从get_test_document(role=worker)读取，保留原目标、附件、模型、权限、现场与范围。'
              '收尾生成器机械通知后继，不承担兄弟模块调度。\n' + prompt)
    delivery_path = root / 'native-delivery.js'
    delivery_config = {'command': command, 'assignment_file': str(Path(assignment_file).absolute()),
        'directory': str(root), 'task_id': assignment['task_id'], 'node_id': assignment['node_id'],
        'output_file': assignment.get('delivery_output_file')}
    delivery_path.write_text('const config = ' + json.dumps(delivery_config, ensure_ascii=False)
                            + ';\n' + NATIVE_DELIVERY_TEMPLATE, encoding='utf-8')
    delivery_path.chmod(0o600)
    return {'script_file': str(path), 'delivery_script_file': str(delivery_path),
            'entry_url': entry_url, 'first_action': 'stage_ready' if stage_ready_script else 'environment_setup' if isolated else 'prepare',
            'stage_ready_script': stage_ready_script,
            'runtime': runtime, 'environment_setup': environment_setup,
            'environment_recovery_tool_arguments': ({'code': environment_recovery, 'timeout_ms': max(60000, 45000 * (options.get('context_count') or len((assignment.get('claim_arguments') or {}).get('account_ids') or []) or 1))} if isolated else None),
            'environment_tool_arguments': ({'code': environment_setup, 'timeout_ms': max(60000, 35000 * (options.get('context_count') or len((assignment.get('claim_arguments') or {}).get('account_ids') or []) or 1))} if isolated else None),
            'browser_bootstrap': None if runtime else browser_bootstrap,
            'browser_helper_file': str(browser_path), 'observation_file': str(root / 'observation-native.json'),
            'message_arguments': {'threadId': target_thread, 'prompt': prompt},
            'instructions': (('先 stage_ready；就绪后才 environment_setup 和 prepare；' if stage_ready_script else
                             '先在持久 node_repl 执行 environment_setup，成功后沿原 prepare；' if isolated else '首个工作调用 prepare；')
                + ('保存复用本轮接收器，不再次 record。实际关页后立即 closeout；加载回执匹配时只调用已加载函数，收到交接核对后先确认再整理。' if config.get('observation_stream') else '等待时结束，原事件后 resume:true。真实观察立即 record；实际关页后立即交还并发布。'))}


def native_ack_arguments(assignment, binding, event):
    """Typed original-event ACK; never infer receipt from a completed case."""
    for key in ('task_id', 'node_id'):
        if not event.get(key) or event[key] != assignment.get(key) or event[key] != binding.get(key):
            raise ValueError('交接事件与原任务绑定不一致')
    if not event.get('event_id') or event['event_id'] != binding.get('lease_id'):
        raise ValueError('交接事件与原领取事件不一致')
    reference = assignment.get('coordinator_ref')
    if not native_thread_target(reference):
        raise ValueError('缺少原协调会话，不能代确认')
    if not same_executor_ref(binding.get('coordinator_ref'), reference):
        raise ValueError('原协调会话绑定已变化')
    return {'action': 'dispatch', 'task_id': event['task_id'],
        'holder_id': assignment.get('coordinator_holder_id') or reference,
        'coordinator_ref': reference, 'request_id': 'native-ack-' + event['event_id'],
        'arguments': {'handoff_ack': {k: event[k] for k in ('task_id', 'node_id', 'event_id')}}}


def native_prepared_summary(directory, prepared):
    """Keep full observations off the terminal transport without losing design."""
    import time
    root = Path(directory).absolute()
    receipt = root / ('prepared-result-%s.json' % time.time_ns())
    write_private_json(receipt, prepared)
    # Resource-wait replies carry their original continuation command/reason.
    if not prepared.get('ready'):
        return {**prepared, 'full_receipt_file': str(receipt)}
    counts = {}
    for case in active_cases(prepared.get('cases', [])):
        status = case.get('status', 'not_run')
        counts[status] = counts.get(status, 0) + 1
    result = {key: prepared[key] for key in (
        'state', 'ready', 'resumed', 'reused', 'binding_file', 'design_file',
        'project_id', 'execution_id', 'revision', 'http_calls', 'seconds',
        'observation_receiver') if key in prepared}
    result.update(case_count=sum(counts.values()), case_counts=counts,
        full_receipt_file=str(receipt), detail_fields=sorted(prepared),
        details_notice='完整用例、检查点、覆盖缺口和账号环境均保留在私有回执及原设计；按当前用例读取，不重新请求或重放准备。统计不代表覆盖完成。')
    if prepared.get('native_call'):
        if len(prepared['native_call']) <= 8000:
            result['native_call'] = prepared['native_call']
        else:
            result['native_call_field'] = 'full_receipt_file.native_call'
    return result


def native_prepared_call(directory, prepared):
    """Supply the already-written call with this preparation's actual case ID."""
    path = Path(directory) / 'prepared-call.json'
    cases = prepared.get('cases') or []
    if not prepared.get('ready') or not path.exists() or len(cases) != 1:
        return None
    call = json.loads(read_utf8(path))
    binding = json.loads(read_utf8(Path(directory) / 'binding.json'))
    if not call.get('binding') or any(binding.get(k) != v for k, v in call['binding'].items()):
        raise ValueError('预制调用不属于本轮准备绑定')
    if cases[0].get('status', 'not_run') != 'not_run':
        return None
    return 'var nativeCaseId=' + json.dumps(cases[0]['case_id']) + ';\n' + call['source']

"""Static registration and short calls for the native REPL's existing memory.

No eval, local code import, browser bridge, persisted page handle or credentials.
The caller installs the literal source once in its own native tool session.
"""
def native_runtime_package(call_source, executor_ref, receipt_file, *, browser_mode='cua'):
    import hashlib
    source = NATIVE_BROWSER_TEMPLATE + NATIVE_OBSERVATION_SEND_TEMPLATE + call_source
    key = hashlib.sha256((source if browser_mode == 'cua' else browser_mode + source).encode()).hexdigest()
    registration = (NATIVE_BROWSER_TEMPLATE + '\n' + NATIVE_OBSERVATION_SEND_TEMPLATE + '\n'
        + 'var nativeLoadedCases = typeof nativeLoadedCases === "undefined" ? new Map() : nativeLoadedCases;\n'
        + 'nativeLoadedCases.set(' + json.dumps(key) + ', ((nativeBrowserCase,nativeSendObservation,nativeFinishTask,nativeReadObservationReceipt) => '
        + 'async function({tab:nativeTab,case_id:nativeCaseId,directory}) {\n'
        + 'const nativeEmit = observation => nativeSendObservation(directory,observation);\n'
        + call_source + '\n})(nativeBrowserCase,nativeSendObservation,nativeFinishTask,nativeReadObservationReceipt));\n'
        + 'await (await import("node:fs/promises")).writeFile(' + json.dumps(str(receipt_file))
        + ',JSON.stringify({key:' + json.dumps(key) + ',executor_ref:' + json.dumps(executor_ref)
        + ',loaded_at:new Date().toISOString()}),{encoding:"utf8",mode:0o600});\n'
        + 'nodeRepl.write({runtime_loaded:true,key:' + json.dumps(key) + '});')
    return {'key': key, 'registration_source': registration, 'receipt_file': str(receipt_file)}


def native_runtime_call(key, directory, *, library=False, entry_url=None, browser_mode='cua'):
    if entry_url is not None and library and browser_mode != 'isolated':
        raise ValueError('未知业务的公共函数加载不能自动打开并执行用例')
    guard = ('if(typeof nativeLoadedCases==="undefined"||!nativeLoadedCases.has(' + json.dumps(key)
        + '))throw new Error("Native session reset: reinstall the verified static routine before business");\n'
    )
    acquire = ('var nativeTab=await nativeBrowserEnvironment.enter(' + json.dumps(entry_url) + ');\n'
               if browser_mode == 'isolated' else
               'var nativeTab=await cua.createBrowserTab("iab",' + json.dumps(entry_url) + ',{visible:false});\n')
    body = (
        'var nativeFinish=close=>nativeFinishTask({close,directory:' + json.dumps(str(directory)) + '});\n'
        + 'var nativeReceipt=(id,options)=>nativeReadObservationReceipt(' + json.dumps(str(directory)) + ',id,options);\n'
        + (acquire if entry_url is not None else '')
        + ('var nativeCurrent=' if library else 'var nativeSummary=') + 'await nativeLoadedCases.get(' + json.dumps(key)
        + ')({tab:nativeTab,case_id:nativeCaseId,directory:' + json.dumps(str(directory)) + '});\n'
        + ('var nativeBrowserCase=nativeCurrent.run;var nativeEmit=nativeCurrent.emit;'
           if library else 'nodeRepl.write(nativeSummary);'))
    if library:
        return guard + body
    # Actual native boundaries, captured without changing the cached function or
    # asking a model to reconstruct timestamps from its session transcript.
    return (guard + 'var nativeCallTiming={case_id:nativeCaseId,started_at:new Date().toISOString()};\ntry{\n' + body
        + '\n}catch(error){nativeCallTiming.error=String(error);throw error;}finally{\n'
        + 'nativeCallTiming.finished_at=new Date().toISOString();\n'
        + 'try{await (await import("node:fs/promises")).writeFile('
        + json.dumps(str(Path(directory) / 'native-call-timing-')) + '+Date.now()+"-"+Math.random().toString(16).slice(2)+".json"'
        + ',JSON.stringify(nativeCallTiming),{encoding:"utf8",mode:0o600});}'
        + 'catch(error){nodeRepl.write({timing_warning:String(error)});}\n}')

"""Read-only, deterministic full-cycle reconciliation and delivery report.

Two current reads; no replay, notification, rollout scan or inferred model timing.
"""

def audit_native_cycle(client, binding_file, output_file, ack_file=None, timeline_file=None):
    import html
    import time
    from datetime import timezone
    started = time.monotonic()
    audit_started_at = datetime.now(timezone.utc).isoformat()
    binding_file, output_file = Path(binding_file), Path(output_file)
    root, page_file = binding_file.parent, output_file.with_suffix('.html')
    if (output_file.suffix != '.json' or output_file.resolve() == binding_file.resolve()
            or output_file.exists() or page_file.exists()):
        raise ValueError('核验输出使用新的 JSON/HTML 文件，不能覆盖原绑定或历史证据')
    def read(path):
        return json.loads(read_utf8(path))
    def optional(name):
        path = root / name
        return read(path) if path.exists() else {}
    binding = read(binding_file)
    if binding.get('workspace_url', client.url) != client.url:
        raise ValueError('核验绑定不属于当前测试台')
    ledger = optional('run-ledger.json')
    if ledger and any(ledger.get(k) != binding[k] for k in ('task_id', 'node_id')):
        raise ValueError('计时台账不属于当前任务与节点')
    # Exactly two fresh reads. Missing artifacts stay missing, without polling.
    state = client.call('get_managed_test', {'task_id': binding['task_id']})
    record = client.call('get_ui_test_cases', {'project_id': binding['project_id'],
                                            'execution_id': binding['execution_id']})
    node = next(n for n in state['nodes'] if n['id'] == binding['node_id'])
    cases = active_cases(record.get('cases') or [])
    receiver = optional('native-receiver.json')
    ack = read(ack_file) if ack_file else {}
    event = ack.get('handoff') or {}
    ack_matches = all(event.get(k) == v for k, v in (
        ('id', binding['lease_id']), ('task_id', binding['task_id']), ('node_id', binding['node_id'])))
    checks = {
        'node_terminal': node.get('state') in {'completed', 'blocked', 'stopped'},
        'no_active_lease': not any(l['node_id'] == binding['node_id'] for l in state.get('leases', [])),
        'receiver_stopped': receiver.get('state') == 'stopped' and not (root / 'native-observations.fifo').exists(),
        'ack_received': ack_matches and ack.get('handoff_complete') is True and event.get('delivery_state') == 'received',
        'passed_state_consistent': (node.get('result') == 'passed') == (bool(cases) and all(c.get('status') == 'passed' for c in cases)),
    }
    stages, errors, warnings, unknown, publications, intervals = [], [], [], [], [], []
    def instant(value):
        if not isinstance(value, str):
            raise ValueError('missing timestamp')
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError('timestamp has no timezone')
        return result
    def stage(name, start, end, scope, top=None, details=None):
        try:
            a, b = instant(start), instant(end)
            if b < a:
                raise ValueError('negative interval')
        except (TypeError, ValueError):
            unknown.append({'stage': name, 'reason': '缺少有效起止时间', 'scope': scope})
            return
        item = {'stage': name, 'started_at': start, 'finished_at': end,
                'seconds': round((b - a).total_seconds(), 6), 'scope': scope}
        if details:
            for key in ('server_processing_timing', 'client_wait', 'case_id'):
                if key in details:
                    item[key] = details[key]
        stages.append(item)
        if top:
            intervals.append((a, b, top))
    def diagnostics(value, source):
        # Retain dynamic warnings at their original path; do not assume a fixed
        # success schema or expose unrelated context/account fields.
        if isinstance(value, dict):
            for key, child in value.items():
                path = source + '.' + key
                if key in {'warning', 'warnings'} and child:
                    warnings.append({'source': path, 'value': child})
                elif key in {'error', 'handoff_error', 'cleanup_error', 'close_error', 'recovery_error'} and child:
                    errors.append({'source': path, 'error': child})
                elif key in {'delivery_state', 'observed_delivery_state', 'operation_state'} and child in {'unknown', 'sending'}:
                    unknown.append({'source': path, 'reason': child})
                elif key == 'save_unconfirmed' and child is True:
                    unknown.append({'source': path, 'reason': '保存未确认'})
                elif isinstance(child, (dict, list)):
                    diagnostics(child, path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                diagnostics(child, source + '[' + str(index) + ']')
    for item in ledger.get('stages', []):
        stage(item['stage'], item.get('started_at'), item.get('finished_at'),
              'coordinator', item['stage'])
    environment = optional('browser-environment.json')
    if environment:
        if any(environment.get('identity', {}).get(k) != binding.get(k)
               for k in ('task_id', 'node_id', 'holder_id', 'executor_ref')):
            raise ValueError('浏览器环境计时不属于原执行者')
        stage('isolated_environment_create', environment.get('started_at'), environment.get('ready_at'),
              'browser_environment', '独立浏览器创建')
        stage('isolated_environment_close', environment.get('close_started_at'), environment.get('closed_at'),
              'browser_environment')
    cycles = []
    for path in sorted(root.glob('cycle-*.json')):
        cycle = read(path)
        cycles.append(cycle)
        diagnostics(cycle, path.name)
        label = {'prepare': '准备与接收器就绪', 'closeout': '交还、发布与通知', 'record': '结果保存',
                 'release': '交还与接续通知', 'review': '结果回查保存', 'complete': '报告补存与最终交付'}.get(cycle.get('action'))
        valid = []
        for item in cycle.get('stages', []):
            stage(item['stage'], item.get('started_at'), item.get('finished_at'), 'tool')
            try:
                a, b = instant(item.get('started_at')), instant(item.get('finished_at'))
                if b >= a:
                    valid.append((a, b))
            except (TypeError, ValueError):
                pass
        if label and valid:
            intervals.append((min(x[0] for x in valid), max(x[1] for x in valid), label))
        result = cycle.get('result') or {}
        for item in result.get('handoff_timing', []):
            stage(item['stage'], item.get('started_at'), item.get('finished_at'), 'handoff_detail', details=item)
        if result.get('publication'):
            published = result['publication']
            publications.append(published.get('publication', published))
    # This receipt is written before notification. A fast coordinator need not
    # wait for the worker's final cycle log merely to verify actual publication.
    closeout = optional('closeout-result.json')
    diagnostics(closeout, 'closeout-result.json')
    if closeout.get('publication'):
        publications.append(closeout['publication'])
    after_handoff = optional('handoff-publication-result.json')
    diagnostics(after_handoff, 'handoff-publication-result.json')
    if after_handoff.get('publication'):
        publications.append(after_handoff['publication'])
    # Report-only completion has its own receipt, persisted before coordinator
    # notification. Do not mistake the earlier release for the final publication.
    final = optional('publication-result.json')
    if final:
        identity = final.get('binding') or {}
        if any(identity.get(key) != binding.get(key) for key in ('holder_id', 'task_id', 'node_id', 'lease_id')):
            raise ValueError('最终发布回执不属于原执行绑定')
        values = identity.get('arguments') or {}
        if any(values.get(key) != binding.get(key) for key in ('project_id', 'execution_id', 'revision')):
            raise ValueError('最终发布回执与当前已保存修订不一致')
        diagnostics(final.get('result'), 'publication-result.json')
        if (final.get('result') or {}).get('publication'):
            publications.append(final['result']['publication'])
    for item in closeout.get('handoff_timing', []):
        stage(item['stage'], item.get('started_at'), item.get('finished_at'), 'handoff_detail',
              '交还、发布与通知' if not any(c.get('action') == 'closeout' for c in cycles) else None, details=item)
    native_paths = sorted(root.glob('native-call-timing*.json'))
    native_case_ids = set()
    for path in native_paths:
        native = read(path)
        stage('native_call', native.get('started_at'), native.get('finished_at'), 'native',
              '原生开页、完整检查、关页与保存', details=native)
        diagnostics(native, path.name)
        if native.get('case_id'):
            native_case_ids.add(native['case_id'])
    if not native_paths:
        unknown.append({'stage': 'native_call', 'reason': '缺少原生调用起止记录'})
    observations, observations_full = [], []
    for path in sorted(root.glob('observation-inbox-*.json')):
        observation = read(path)
        observations_full.append(observation)
        diagnostics(observation, path.name)
        timing = observation.get('timing') or {}
        observations.append({'case_id': observation.get('case_id'), 'status': observation.get('status'),
            'checks': len(observation.get('checks', [])),
            'passed_checks': sum(c.get('ok') is True for c in observation.get('checks', [])),
            'evidence_file': str(path)})
        stage('business', timing.get('started_at'), timing.get('last_assertion_at'), 'observation')
        stage('browser_close', timing.get('last_assertion_at'), timing.get('browser_closed_at'), 'observation')
    if native_case_ids:
        for case_id in sorted({o.get('case_id') for o in observations if o.get('case_id')} - native_case_ids):
            unknown.append({'stage': 'native_call', 'case_id': case_id, 'reason': '此用例缺少原生调用计时记录'})
    saved = optional('native-receiver-response.json')
    diagnostics(saved, 'native-receiver-response.json')
    timing = saved.get('timing') or {}
    stage('save', timing.get('save_started_at'), timing.get('save_finished_at'), 'observation')
    if timeline_file:
        for item in read(timeline_file):
            stage(item['stage'], item.get('started_at'), item.get('finished_at'), 'outer_tool')
    diagnostics(ack, 'ack')
    diagnostics(node, 'current_node')
    diagnostics(record, 'current_cases')
    for item in ack.get('handoff_timing', []):
        stage(item['stage'], item.get('started_at'), item.get('finished_at'), 'handoff_detail',
              '协调确认' if item['stage'] == 'coordinator_ack' and ack_matches else None, details=item)
    checks['report_published'] = bool(publications) and publications[-1].get('phase') == 'published'
    checks['save_confirmed'] = saved.get('saved') is True
    if not any(s.get('stage') in {'release_handoff', 'release_publish_handoff'}
               for c in cycles for s in c.get('stages', [])):
        unknown.append({'stage': 'closeout', 'reason': '完整交还调用日志尚未取得；已保存初始交还回执不等于全部发送回执完成'})
    start = None
    try:
        start = instant(ledger.get('started_at'))
    except (TypeError, ValueError):
        unknown.append({'stage': 'total', 'reason': '缺少本轮明确起点，总耗时未知'})
    case_statuses = {c['case_id']: c['status'] for c in cases}
    failed_cases = [key for key, status in case_statuses.items() if status != 'passed']
    failed_assertions = [{'case_id': o.get('case_id'), **c} for o in observations_full
                         for c in o.get('checks', []) if c.get('ok') is not True]
    remaining = [k for k, v in checks.items() if not v]
    def aggregate_timing(report_ready_at):
        finish = instant(report_ready_at)
        # Refresh only this audit's measured phase when the completed report
        # write is included in the final endpoint below.
        stages[:] = [s for s in stages if s['scope'] != 'audit']
        intervals[:] = [item for item in intervals if item[2] != '当前状态核验与报告整理']
        stage('audit_report', audit_started_at, report_ready_at, 'audit', '当前状态核验与报告整理')
        total, timeline = None, []
        if start is not None and start <= finish:
            total = round((finish - start).total_seconds(), 6)
            # Partition nested and parallel intervals. Every measured second
            # between the explicit start and report boundary appears once.
            boundaries = sorted({start, finish, *(max(start, min(finish, t)) for a, b, _ in intervals for t in (a, b))})
            for a, b in zip(boundaries, boundaries[1:]):
                if b <= a:
                    continue
                active = sorted({label for x, y, label in intervals if x < b and y > a})
                name = '、'.join(active) + ('（并行）' if len(active) > 1 else '') if active else '未归属间隔（含调用等待）'
                if timeline and timeline[-1]['stage'] == name:
                    timeline[-1]['finished_at'] = b.isoformat()
                    timeline[-1]['seconds'] = round((b - instant(timeline[-1]['started_at'])).total_seconds(), 6)
                else:
                    timeline.append({'stage': name, 'started_at': a.isoformat(), 'finished_at': b.isoformat(),
                                     'seconds': round((b - a).total_seconds(), 6), 'scope': 'whole_cycle',
                                     'attribution': 'measured' if active else 'unattributed'})
        elif start is not None and not any(item.get('reason') == '起点晚于报告时间，不能计算总耗时' for item in unknown):
            unknown.append({'stage': 'total', 'reason': '起点晚于报告时间，不能计算总耗时'})
        return total, timeline, round(sum(s['seconds'] for s in timeline if s['attribution'] == 'unattributed'), 6)
    report_ready_at = datetime.now(timezone.utc).isoformat()
    total, timeline, unassigned = aggregate_timing(report_ready_at)
    publication = publications[-1] if publications else None
    summary = {'started_at': ledger.get('started_at'), 'start_basis': ledger.get('start_basis', '未知'),
        'report_ready_at': report_ready_at, 'total_to_report_seconds': total,
        'case_count': len(cases), 'passed_cases': sum(s == 'passed' for s in case_statuses.values()),
        'check_count': sum(o['checks'] for o in observations), 'passed_checks': sum(o['passed_checks'] for o in observations),
        'case_statuses': case_statuses, 'failed_cases': failed_cases, 'failed_assertions': failed_assertions,
        'lifecycle_checks': checks, 'remaining': remaining, 'errors': errors, 'warnings': warnings,
        'unknown': unknown, 'unattributed_seconds': unassigned, 'timeline': timeline,
        'report_file': str(page_file), 'report_url': page_file.resolve().as_uri(),
        'data_file': str(output_file), 'publication': publication,
        'delivery_basis': '终点在报告正文首次写入完成后采样，随后只更新最终计时元数据；不包含聊天消息组织与发送。未归属间隔不等同于纯模型时间。'}
    result = {'task_id': binding['task_id'], 'node_id': binding['node_id'],
        'project_id': binding['project_id'], 'execution_id': binding['execution_id'],
        'node_result': node.get('result'), 'case_statuses': case_statuses,
        'checks': checks, 'observations': observations, 'stages': stages, 'errors': errors,
        'warnings': warnings, 'unknown': unknown, 'publication': publication, 'remaining': remaining,
        'summary': summary, 'timeline': timeline, 'report_ready_at': report_ready_at,
        'total_to_report_seconds': total, 'audit_seconds': round(time.monotonic() - started, 6),
        'timing_basis': '顶层时间轴覆盖明确起点到报告生成，重叠时间只计一次；细分与嵌套时间不可相加。缺失记录保持未知，不补零。'}
    def table(items):
        rows = ''.join('<tr>' + ''.join('<td>' + html.escape(str(x)) + '</td>' for x in
            (s['stage'], s['started_at'], s['finished_at'], s['seconds'])) + '</tr>' for s in items)
        return '<table><tr><th>阶段</th><th>开始（含时区）</th><th>结束</th><th>秒</th></tr>' + rows + '</table>'
    def details(value):
        return '<pre>' + html.escape(json.dumps(value, ensure_ascii=False, indent=2)) + '</pre>'
    def render_page():
        return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>原生完整链路交付核验</title>'
        '<style>body{font:16px system-ui;max-width:1300px;margin:40px auto;padding:20px;color:#172033}'
        'td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}table{width:100%;border-collapse:collapse}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f9;padding:16px}h2{margin-top:32px}</style>'
        '<h1>完整链路实际耗时与交付结果</h1><p>从 ' + html.escape(str(summary['started_at'] or '未知起点'))
        + ' 到 ' + html.escape(report_ready_at) + '，总耗时 <strong>' + (str(total) + ' 秒' if total is not None else '未知')
        + '</strong>。</p><p>' + html.escape(summary['start_basis']) + '；' + html.escape(summary['delivery_basis'])
        + '</p><p>独立用例 ' + str(summary['passed_cases']) + '/' + str(summary['case_count'])
        + ' 通过；实际检查 ' + str(summary['passed_checks']) + '/' + str(summary['check_count'])
        + ' 通过。生命周期核对通过不代替业务判定。</p><h2>完整顶层时间轴</h2><p>'
        + html.escape(result['timing_basis']) + '</p>' + table(timeline)
        + '<h2>失败、告警、未知与剩余问题</h2>' + details({k: summary[k] for k in
            ('failed_cases', 'failed_assertions', 'remaining', 'errors', 'warnings', 'unknown', 'unattributed_seconds')})
        + '<h2>当前结果与交还确认</h2>' + details({'case_statuses': case_statuses, 'lifecycle_checks': checks, 'publication': publication})
        + '<h2>原始阶段细分（不可累加到总耗时）</h2>' + table(stages)
        + '<h2>平台处理与客户端等待实测</h2>' + details([s for s in stages if
            'server_processing_timing' in s or 'client_wait' in s])
        + '<h2>独立观察证据</h2>' + details(observations) + '</html>')
    page_file.write_text(render_page(), encoding='utf-8')
    page_file.chmod(0o600)
    # Sample after the actual complete HTML exists. Only final timing metadata
    # is refreshed afterwards; this is not a claim of chat-message delivery.
    report_ready_at = datetime.now(timezone.utc).isoformat()
    total, timeline, unassigned = aggregate_timing(report_ready_at)
    summary.update(report_ready_at=report_ready_at, total_to_report_seconds=total,
                   timeline=timeline, unattributed_seconds=unassigned)
    result.update(report_ready_at=report_ready_at, total_to_report_seconds=total,
                  timeline=timeline, audit_seconds=round(time.monotonic() - started, 6))
    page_file.write_text(render_page(), encoding='utf-8')
    write_private_json(output_file, result)
    return {'report_file': str(page_file), 'data_file': str(output_file), 'checks': checks,
            'remaining': remaining, 'audit_seconds': result['audit_seconds'], 'summary': summary,
            'report_ready_at': report_ready_at, 'total_to_report_seconds': total}

"""One task's local observation receiver. No browser/model control or polling.

The owner starts it with the verified client. A FIFO carries only a short notification of a private observation
file; the existing record call owns credentials, lease validation and receipts.
"""
def start_native_observation_receiver(command, binding_file):
    root = Path(binding_file).resolve().parent
    with batch_lock(root / 'receiver-start'):
        status = root / 'native-receiver.json'
        try:
            with batch_lock(status):
                pass  # No live receiver owns the OS lock; safe to restart.
        except BlockingIOError:
            current = json.loads(read_utf8(status))
            if current.get('state') != 'ready' or not (root / 'native-observations.fifo').exists():
                raise ValueError('原接收器尚未就绪，保留现场，不启动第二个接收器')
            return {**current, 'reused': True}
        return _start_native_observation_receiver(command, binding_file)


def _start_native_observation_receiver(command, binding_file):
    """Return on the child's real readiness pipe, not a live terminal poll."""
    import os
    import subprocess
    root = Path(binding_file).resolve().parent
    read_fd, ready_fd = os.pipe()
    process = None
    try:
        log_fd = os.open(root / 'native-receiver.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(log_fd, 'ab') as log:
            process = subprocess.Popen([*command, 'native-observe-receive', '--binding-file', str(binding_file),
                '--ready-fd', str(ready_fd)], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                pass_fds=(ready_fd,), start_new_session=True)
        os.close(ready_fd)
        ready_fd = None
        with os.fdopen(read_fd, encoding='utf-8') as pipe:
            read_fd = None
            packet = json.loads(pipe.readline())
        if packet.get('receiver_ready') is not True or packet.get('pid') != process.pid:
            raise ValueError('接收器未确认就绪；停止在浏览器业务之前')
        return {'pid': process.pid, 'fifo': packet['fifo'], 'ready_at': packet['ready_at']}
    except BaseException:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait()
        raise
    finally:
        for fd in (read_fd, ready_fd):
            if fd is not None:
                os.close(fd)


def receive_native_observations(client, binding_file, prepared=None, ready_fd=None):
    import os
    import stat
    root = Path(binding_file).resolve().parent
    fifo = root / 'native-observations.fifo'
    status = root / 'native-receiver.json'
    response = root / 'native-receiver-response.json'
    with batch_lock(status):
        # Holding the original OS lock proves no active receiver owns this path.
        # A stopped/crashed receiver may be restarted without replaying its inbox.
        if fifo.is_symlink() or (fifo.exists() and not stat.S_ISFIFO(fifo.lstat().st_mode)):
            raise ValueError('观察入口类型改变，不能覆盖')
        if fifo.exists():
            fifo.unlink()
        os.mkfifo(fifo, 0o600)
        fd = os.open(fifo, os.O_RDWR)
        write_private_json(status, {'state': 'ready', 'pid': os.getpid(), 'fifo': str(fifo), 'protocol': 2, 'ready_at': datetime.now(timezone.utc).isoformat()})
        try:
            packet = {'receiver_ready': True, 'pid': os.getpid(), 'fifo': str(fifo),
                      'ready_at': datetime.now(timezone.utc).isoformat(),
                      **({'prepared': prepared} if prepared else {})}
            if ready_fd is None:
                print(json.dumps(packet), flush=True)
            else:
                with os.fdopen(ready_fd, 'w', encoding='utf-8') as ready:
                    ready.write(json.dumps(packet) + '\n')
            with os.fdopen(fd, 'r', encoding='utf-8') as stream:
                for line in stream:
                    if line.strip() == '{"stop":true}':
                        return {'stopped': True}
                    message = json.loads(line)
                    request_id = message['request_id']
                    import re
                    if not isinstance(request_id, str) or not re.fullmatch(r'[0-9]+-[a-f0-9]+', request_id):
                        raise ValueError('缺少本地观察请求标识')
                    if message.get('reconcile') is True:
                        try:
                            result = reconcile_native_observation(client, binding_file, request_id)
                        except Exception as error:
                            result = {'request_id': request_id, 'saved': False, 'state': 'unknown', 'reconciliation_error': str(error)}
                        write_private_json(root / ('native-receiver-response-' + request_id + '.json'), result)
                        write_private_json(response, result)
                        continue
                    pending_before = (root / 'observation-pending.json').exists()
                    timing = {'received_at': datetime.now(timezone.utc).isoformat()}
                    observation = {}
                    result = {'request_id': request_id, 'saved': False}
                    try:
                        observation = json.loads(read_utf8(root / ('observation-inbox-' + request_id + '.json')))
                        timing['save_started_at'] = datetime.now(timezone.utc).isoformat()
                        saved = observed_native_json(client, binding_file, observation,
                            root / 'observation-stream.json', root / ('receipt-stream-' + request_id + '.json'), request_id=request_id)
                        result.update(saved=True, receipt=saved)
                    except Exception as error:
                        # The original pending marker fences unknown writes.
                        # Do not retry or accept another business observation.
                        result.update(error=type(error).__name__, message=str(error), state='unknown')
                        marker = root / 'observation-pending.json'
                        pending = json.loads(read_utf8(marker)) if marker.exists() else {}
                        record_file = Path(pending['receipt_file']) if pending.get('receipt_file') else None
                        record = json.loads(read_utf8(record_file)) if record_file and record_file.exists() else {}
                        binding = json.loads(read_utf8(binding_file))
                        rejected = native_rejection_confirmed(record, binding)
                        if not pending_before and (rejected or
                                type(error) is ValueError and (not record_file or not record_file.exists())):
                            # Validation before the POST, or a definite HTTP rejection.
                            # Keep failure artifacts; allow Codex to correct the draft.
                            result['state'] = 'rejected' if rejected else 'not_sent'
                            marker.unlink(missing_ok=True)
                        if record_file:
                            result['record_receipt_file'] = str(record_file)
                        if getattr(error, 'native_receipt_state', None) in {'not_sent', 'rejected'}:
                            result['state'] = error.native_receipt_state
                            if getattr(error, 'native_receipt_file', None):
                                result['record_receipt_file'] = error.native_receipt_file
                    timing['save_finished_at'] = datetime.now(timezone.utc).isoformat()
                    result['timing'] = timing
                    result['exit'] = observation.get('exit') or {}
                    write_private_json(root / ('native-receiver-response-' + request_id + '.json'), result)
                    write_private_json(response, result)
                    # Keep the same receiver after a recoverable save error. The
                    # existing pending marker rejects new writes until reconciled.
                    # Only explicit lifecycle closeout sends the stop notification.
        finally:
            # Never remove a substituted path or an unrelated process's files.
            if fifo.exists() and stat.S_ISFIFO(fifo.lstat().st_mode):
                fifo.unlink()
            write_private_json(status, {'state': 'stopped', 'pid': os.getpid()})


def native_observed_closeout_arguments(binding_file):
    """Use only this run's actual saved exit, never a reconstructed success."""
    binding_file = Path(binding_file)
    binding = json.loads(read_utf8(binding_file))
    response_file = binding_file.parent / 'native-receiver-response.json'
    receipt = json.loads(read_utf8(response_file)) if response_file.exists() else {}
    exit_file = binding_file.parent / 'native-exit-observation.json'
    explicit_exit = binding_file.parent / 'native-explicit-exit.json'
    proof = (json.loads(read_utf8(explicit_exit)) if explicit_exit.exists() else
             json.loads(read_utf8(exit_file)) if exit_file.exists() else receipt)
    if explicit_exit.exists() and any(proof.get('binding', {}).get(key) != binding.get(key)
                                      for key in ('task_id', 'node_id', 'holder_id', 'lease_id')):
        raise ValueError('退出依据不属于当前原任务绑定')
    confirmed = {}
    def observation_saved(request_id):
        if request_id not in confirmed:
            answer_file = binding_file.parent / ('native-receiver-response-' + request_id + '.json')
            answer = json.loads(read_utf8(answer_file)) if answer_file.exists() else {}
            confirmed[request_id] = ((answer.get('request_id') == request_id and
                native_observation_settled(binding_file.parent, answer, binding))
                or native_observation_correction(binding_file.parent, request_id, binding))
        return confirmed[request_id]
    awaiting_file = binding_file.parent / 'native-observation-awaiting.json'
    waiting_saved = True
    if awaiting_file.exists():
        awaiting = json.loads(read_utf8(awaiting_file))
        waiting_saved = observation_saved(awaiting['request_id'])
    latest_file = binding_file.parent / 'native-last-observation.json'
    latest_saved = receipt.get('saved') is not False
    if latest_file.exists():
        latest = json.loads(read_utf8(latest_file))
        latest_saved = observation_saved(latest['request_id'])
    exit_state = proof.get('exit') or {}
    environment_file = binding_file.parent / 'browser-environment.json'
    if environment_file.exists():
        environment = json.loads(read_utf8(environment_file))
        if environment.get('schema') == 2 and (
                environment.get('state') != 'closed'
                or sorted(exit_state.get('context_ids') or []) != sorted(
                    row['context_id'] for row in environment.get('environments', []))):
            raise ValueError('退出依据不属于当前已关闭的浏览器环境，不能交还正在使用的账号')
    saved = (latest_saved and waiting_saved and not (binding_file.parent / 'observation-pending.json').exists() and
             (explicit_exit.exists() or (native_observation_settled(binding_file.parent, receipt, binding)
                and receipt.get('request_id') == proof.get('request_id'))))
    return native_closeout_arguments(binding, browser_stopped=exit_state.get('browser_stopped'),
        reason=exit_state.get('reason'), save_unconfirmed=not saved)


def stop_native_observation_receiver(binding_file):
    import os
    import stat
    fifo = Path(binding_file).resolve().parent / 'native-observations.fifo'
    if not fifo.exists():
        return
    if not stat.S_ISFIFO(fifo.lstat().st_mode):
        raise ValueError('观察入口类型改变，不能发送停止请求')
    try:
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
    except OSError as error:
        import errno
        if error.errno in {errno.ENOENT, errno.ENXIO}:
            return
        raise
    try:
        os.write(fd, b'{"stop":true}\n')
    finally:
        os.close(fd)


def reconcile_native_observation_correction(client, binding_file, request_id, correction_file):
    """Associate a later confirmed save, without converting the old unknown to ACK."""
    binding_file = Path(binding_file).absolute()
    root = binding_file.resolve().parent
    # Same order as receiver startup. A live receiver keeps sole ownership;
    # this explicit stopped-receiver operation never waits or runs a second writer.
    with batch_lock(root / 'receiver-start'), batch_lock(root / 'native-receiver.json'), batch_lock(binding_file):
        if binding_file.is_symlink() or binding_file.parent.is_symlink():
            raise ValueError('纠正关联不能替换原绑定文件')
        binding = json.loads(read_utf8(binding_file))
        if binding.get('workspace_url') != client.url:
            raise ValueError('纠正关联不属于当前测试台')
        import re
        if not isinstance(request_id, str) or not re.fullmatch(r'[0-9]+-[a-f0-9]+', request_id):
            raise ValueError('纠正关联缺少原观察 request_id')
        proof_file = root / ('native-observation-correction-' + request_id + '.json')
        previous = json.loads(read_utf8(proof_file)) if proof_file.exists() else None
        original, correction, evidence = native_correction_evidence(root, request_id, binding, correction_file,
            confirmed_revision=previous.get('revision') if previous else None)
        marker_file = root / 'observation-pending.json'
        marker = json.loads(read_utf8(marker_file)) if marker_file.exists() else None
        if marker is not None:
            case = original['payload']['cases'][0]
            if (marker_file.is_symlink() or marker.get('request_id') != request_id
                    or Path(marker.get('receipt_file', '')).resolve() != Path(evidence['original']['file']).resolve()
                    or any(marker.get(key) != case.get(key) for key in ('case_id', 'status', 'actual'))
                    or ('payload' in marker and marker['payload'] != original['payload'])
                    or (marker.get('binding') and any(marker['binding'].get(key) != binding.get(key)
                        for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'project_id', 'execution_id')))):
                raise ValueError('其他请求或内容不匹配的 pending 仍受保护')
        reused = proof_file.exists()
        if reused:
            if not native_observation_correction(root, request_id, binding):
                raise ValueError('已有纠正关联的身份、修订或证据已变化；保留原证明')
            proof = json.loads(read_utf8(proof_file))
            if marker is not None and marker != proof.get('pending_marker'):
                raise ValueError('pending 与原纠正关联不一致')
        else:
            request = {key: binding[key] for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'account_id', 'dispatch_id', 'executor_ref') if key in binding}
            manifest_calls = int(client.manifest is None)
            record = client.call('direct_test_session', {**request, 'action': 'record', 'record_action': 'record',
                'arguments': {'project_id': binding['project_id'], 'execution_id': binding['execution_id']}})
            native_save_readback(correction, record, correction.get('case_baselines', {}))
            # Only submitted cases and fields needed by the existing exact
            # validator belong in this durable proof, never unrelated history.
            ids = {case['case_id'] for case in correction['payload'].get('cases', [])}
            content = correction['payload']
            keys = ['id', 'revision', *(key for key in ('review_notes', 'scene_outcome', 'experiment') if key in content)]
            if any('checkpoints' in case or 'checkpoint_updates' in case or
                   (correction.get('case_baselines', {}).get(case['case_id']) or {}).get('checkpoints')
                   for case in content.get('cases', [])):
                keys.extend(('dependency_checks', 'requirement_design'))
            selected = {key: copy.deepcopy(record[key]) for key in keys if key in record}
            for key in ('cases', 'superseded_cases'):
                selected[key] = [copy.deepcopy(case) for case in record.get(key, []) if case['case_id'] in ids]
            areas = {area['coverage_id'] for area in correction['payload'].get('coverage', [])}
            selected['coverage'] = [copy.deepcopy(area) for area in record.get('coverage', []) if area['coverage_id'] in areas]
            if (native_correction_scope(json.loads(read_utf8(binding_file))) != native_correction_scope(binding)
                    or native_correction_evidence(root, request_id, binding, correction_file)[2] != evidence
                    or (json.loads(read_utf8(marker_file)) if marker_file.exists() else None) != marker):
                raise ValueError('只读期间原绑定或证据已变化；保留 pending')
            proof = {'schema': 1, 'resolution': 'corrected_by_saved_receipt', 'request_id': request_id,
                'original_transport_state': 'unknown', 'binding': native_correction_scope(binding),
                'original_revision_before': original['revision_before'], 'revision': correction['result']['revision'],
                'evidence': evidence, 'record': selected, 'pending_marker': marker,
                'confirmed_at': datetime.now(timezone.utc).isoformat()}
            write_private_json(proof_file, proof)
        # Crash after durable proof is recoverable without another platform read.
        if marker is not None:
            if json.loads(read_utf8(marker_file)) != marker:
                raise ValueError('pending 已改变，不清理其他请求')
            marker_file.unlink()
        return {'request_id': request_id, 'resolution': proof['resolution'],
            'original_transport_state': 'unknown', 'revision': proof['revision'],
            'correction_receipt_file': str(proof_file), 'reused_receipt': reused,
            'http_calls': 0 if reused else 1 + manifest_calls}


def reconcile_native_observation(client, binding_file, request_id):
    """Read the original receipt and record if needed; never resubmit a save."""
    root = Path(binding_file).resolve().parent
    response_file = root / ('native-receiver-response-' + request_id + '.json')
    previous = json.loads(read_utf8(response_file)) if response_file.exists() else {'request_id': request_id, 'saved': False, 'state': 'unknown'}
    if previous.get('request_id') != request_id:
        return {'request_id':request_id,'saved':False,'state':'unknown','reconciliation':'Receiver response belongs to another request'}
    binding = json.loads(read_utf8(binding_file))
    if previous.get('state') == 'not_sent' or (previous.get('state') == 'rejected'
            and native_observation_settled(root, previous, binding)):
        return previous
    cached_saved = previous.get('saved') is True
    previous = {**previous, 'saved':False, 'state':'unknown'}
    observation = json.loads(read_utf8(root / ('observation-inbox-' + request_id + '.json')))
    payload = json.dumps(observation, sort_keys=True, ensure_ascii=False, allow_nan=False)
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    receipt_file = root / ('receipt-stream-' + request_id + '-' + digest + '.json')
    marker_file = root / 'observation-pending.json'
    try:
        actual = observation_actual(observation)
    except ValueError:
        actual = None  # Invalid observations cannot have reached record POST.
    pending = json.loads(read_utf8(marker_file)) if marker_file.exists() else {}
    matching_pending = actual is not None and pending.get('request_id', request_id) == request_id and all(pending.get(key) == value for key, value in
        [('case_id', observation.get('case_id')), ('status', observation.get('status')), ('actual', actual)])
    candidates = [receipt_file]
    if matching_pending and pending.get('receipt_file'):
        candidates.append(Path(pending['receipt_file']))
    if previous.get('record_receipt_file'):
        candidates.append(Path(previous['record_receipt_file']))
    candidates.append(root / ('receipt-stream-' + digest + '.json'))  # Pre-0.17.71 receiver.
    for candidate in candidates:
        if candidate.resolve().parent != root or not candidate.exists():
            continue
        stored = json.loads(read_utf8(candidate))
        stored_cases = stored.get('payload', {}).get('cases') or []
        expected_case = {**(observation.get('case_changes') or {}), 'case_id': observation.get('case_id'),
                         'status': observation.get('status'), 'actual': actual}
        if len(stored_cases) == 1 and actual is not None and stored_cases[0] == expected_case:
            receipt_file = candidate
            break
        return {**previous, 'reconciliation': 'Existing write evidence differs; preserve original receipt'}
    def clear_own_marker():
        if marker_file.exists():
            pending = json.loads(read_utf8(marker_file))
            if (pending.get('receipt_file') == str(receipt_file)
                    and pending.get('request_id', request_id) == request_id):
                marker_file.unlink()
    # Receiver is the sole owner of its OS lock. No old local writer survives.
    # A POST always has its durable receipt first, so absence proves not sent.
    if not receipt_file.exists():
        if cached_saved:
            return {**previous, 'reconciliation':'Original saved write receipt is missing; preserve evidence'}
        clear_own_marker()
        return {**previous, 'saved': False, 'state': 'not_sent', 'reconciled': True}
    write_receipt = json.loads(read_utf8(receipt_file))
    binding = json.loads(read_utf8(binding_file))
    if native_rejection_confirmed(write_receipt, binding):
        clear_own_marker()
        return {**previous, 'saved': False, 'state': 'rejected', 'reconciled': True,
                'record_receipt_file': str(receipt_file)}
    if write_receipt.get('state') not in {'saved', 'pending', 'unknown', 'rejected'}:
        return {**previous, 'reconciliation': 'Original save state cannot be confirmed; preserve receipt'}
    # One implementation owns exact revision, full-field and checkpoint checks.
    # The existing receipt prevents native_record from issuing another save.
    try:
        saved = client.native_record(binding_file, write_receipt['payload'], receipt_file)
    except (ValueError, OSError) as error:
        return {**previous, 'saved': False, 'state': 'unknown', 'reconciliation': str(error)}
    current = json.loads(read_utf8(binding_file))
    confirmed = json.loads(read_utf8(receipt_file))
    if native_rejection_confirmed(confirmed, current):
        clear_own_marker()
        return {**previous, 'saved': False, 'state': 'rejected', 'reconciled': True,
                'record_receipt_file': str(receipt_file)}
    expected_payload = {'cases':[expected_case], **({'asset_files':observation['asset_files']} if 'asset_files' in observation else {})}
    if not native_pending_receipt_matches({'request_id':request_id,'payload':expected_payload},
                                          confirmed,current,request_id=request_id,client=client):
        return {**previous, 'reconciliation':'Original observation does not match the exact saved receipt'}
    if matching_pending:
        if not native_pending_receipt_matches(pending, confirmed, current, request_id=request_id, client=client):
            return {**previous, 'saved': False, 'state': 'unknown', 'reconciliation': 'Original pending marker does not match the exact saved receipt'}
    clear_own_marker()
    return {**previous, 'request_id': request_id, 'saved': True, 'state': 'saved', 'reconciled': True, 'receipt': saved}

NATIVE_CYCLE_TEMPLATE = '// Execute in functions.exec with tools/text/ALL_TOOLS/input explicitly supplied.\n// Browser actions stay in the supported native browser tool, never a proxy.\nconst quote = s => "\'" + String(s).replace(/\'/g, "\'\\\\\'\'") + "\'";\nconst now = () => new Date().toISOString();\nconst stages = [];\nasync function command(args, stage, awaitReceiver = false) {\n  const started_at = now();\n  const controlFile = config.control_receipts ? config.directory + \'/control-\' + stage + \'-\' + Date.now() + \'-\' + stages.length + \'.json\' : null;\n  if (controlFile) args = [...args, \'--control-result-file\', controlFile];\n  let r = await tools.exec_command({cmd: [...config.command, ...args].map(quote).join(\' \'),\n    max_output_tokens: 16000, yield_time_ms: 10000});\n  let output = r.output;\n  while (r.session_id && r.exit_code == null) {\n    if (awaitReceiver) {\n      let packet;\n      try { packet = JSON.parse(output); } catch (_) { /* stdout can arrive in chunks */ }\n      if (packet?.receiver_ready === true && packet.prepared?.ready === true) {\n        stages.push({stage, started_at, finished_at: now(), receiver_ready: true});\n        return {...packet.prepared, observation_receiver: {session_id: r.session_id, fifo: packet.fifo}};\n      }\n    }\n    r = await tools.write_stdin({session_id: r.session_id, chars: \'\', yield_time_ms: 1000, max_output_tokens: 16000});\n    output += r.output;\n  }\n  stages.push({stage, started_at, finished_at: now(), exit_code: r.exit_code});\n  if (r.exit_code !== 0) throw new Error(output.slice(-3000));\n  if (controlFile) return await nativeReadControl(tools, config.command, controlFile);\n  return JSON.parse(output);\n}\nconst binding = config.directory + \'/binding.json\';\nasync function closeout(saveUnconfirmed = false, deferReport = false, outcome = \'completed\') {\n  if (input.from_observation !== true && (input.browser_stopped !== true || typeof input.reason !== \'string\' || !input.reason.trim()))\n    throw new Error(\'Actual browser exit and reason required\');\n  const generated = await command([\'native-closeout-script\', \'--binding-file\', binding,\n    \'--outcome\', outcome,\n    ...(saveUnconfirmed ? [\'--save-unconfirmed\'] : []),\n    ...(deferReport ? [\'--defer-report\'] : []),\n    ...(input.from_observation === true ? [\'--observed-exit\'] :\n      [\'--browser-stopped\', \'--reason\', input.reason])], \'closeout_generate\');\n  let receipt;\n  const started_at = now();\n  const AF = Object.getPrototypeOf(async function() {}).constructor;\n  await new AF(\'tools\', \'text\', \'ALL_TOOLS\', generated.script)(tools, v => { receipt = v; }, ALL_TOOLS);\n  stages.push({stage: deferReport ? \'release_handoff\' : \'release_publish_handoff\', started_at, finished_at: now()});\n  return {...receipt, ...(generated.review_state ? {review_state: generated.review_state} : {})};\n}\nasync function publishSaved() {\n  const result = await command([\'native-publish-saved\', \'--binding-file\', binding,\n    \'--receipt-file\', config.directory + \'/publication-result.json\'], \'publish_saved\');\n  if (result.handoff_script) {\n    const started_at = now();\n    const AF = Object.getPrototypeOf(async function() {}).constructor;\n    let handoff;\n    await new AF(\'tools\', \'text\', \'ALL_TOOLS\', result.handoff_script)(tools, v => { handoff = v; }, ALL_TOOLS);\n    stages.push({stage: \'report_handoff\', started_at, finished_at: now()});\n    delete result.handoff_script;\n    result.handoff = handoff;\n  }\n  return result;\n}\nlet result, failure;\ntry {\n  if (input.action === \'work_plan\') {\n    if (typeof input.plan_file !== \'string\') throw new Error(\'Explicit work plan file required\');\n    result = await command([\'native-work-plan\',\'--binding-file\',binding,\'--plan-file\',input.plan_file,\n      \'--entry-url\', config.entry_url], \'work_plan\');\n  } else if (input.action === \'cleanup\') {\n    if (typeof input.events_file !== \'string\') throw new Error(\'Original cleanup evidence file required\');\n    result = await command([\'native-cleanup\',\'--binding-file\',binding,\'--events-file\',input.events_file], \'cleanup\');\n  } else if (input.action === \'work\') {\n    if (typeof input.unit_id !== \'string\') throw new Error(\'Original work unit id required\');\n    result = await command([\'native-work-boundary\',\'--binding-file\',binding,\'--unit-id\',input.unit_id], \'work_boundary\');\n  } else if (input.action === \'resume\') {\n    if (!input.notification || typeof input.notification !== \'object\') throw new Error(\'Original resume notification required\');\n    result = await command([\'native-resume\', \'--assignment-file\', config.assignment_file,\n      \'--directory\', config.directory, \'--notification-json\', JSON.stringify(input.notification)], \'resume\');\n  } else if (input.action === \'stage_ready\') {\n    result = await command([\'native-stage-ready\', \'--assignment-file\', config.assignment_file,\n      \'--directory\', config.directory], \'stage_ready\');\n  } else if (input.action === \'prepare\') {\n    result = await command([\'native-prepare\', \'--summary\', \'--assignment-file\', config.assignment_file,\n      \'--design-file\', config.design_file, \'--directory\', config.directory,\n      ...(input.resume === true ? [\'--resume\'] : []),\n      ...(config.observation_stream === true ? [\'--receive-observations\'] : [])], \'prepare\', config.observation_stream === true);\n    result.entry_url = config.entry_url;\n    if (result.ready && config.observation_stream === true && !result.observation_receiver)\n      throw new Error(\'Observation receiver not ready; stop before browser business\');\n  } else if (input.action === \'record\') {\n    // Persist the exact observation before attempting the POST, including failures.\n    const fromFile = input.observation_file !== undefined;\n    if (fromFile && input.observation) throw new Error(\'Ambiguous observation source\');\n    if (fromFile && input.observation_file !== config.directory + \'/observation-native.json\')\n      throw new Error(\'Observation must come from this run export\');\n    if (!fromFile && (!input.observation || typeof input.observation.case_id !== \'string\')) throw new Error(\'Missing observation\');\n    const key = fromFile ? \'native\' : encodeURIComponent(input.observation.case_id);\n    const observationFile = config.directory + \'/observation-\' + key + \'.json\';\n    const receiptFile = config.directory + \'/receipt-\' + key + \'.json\';\n    result = await command([\'native-observe\', \'--binding-file\', binding,\n      ...(fromFile ? [\'--source-file\', input.observation_file] : [\'--observation-json\', JSON.stringify(input.observation)]), \'--observation-file\', observationFile,\n      \'--receipt-file\', receiptFile], \'save\');\n    if (input.finish_task === true && input.browser_stopped === true) result = {saved: result, closeout: await closeout()};\n  } else if (input.action === \'review\' || input.action === \'complete\') {\n    const finishing = input.action === \'review\' && input.finish_task === true && input.browser_stopped === true;\n    if (finishing) {\n      result = {closeout: await closeout(false, true)};\n      if (result.closeout.released !== true) throw new Error(\'Resource release not confirmed; preserve the original receipt\');\n    }\n    // After explicit release, no account is required for original-record changes.\n    // No changes means publish the already saved record without another save.\n    if (input.action === \'complete\' && input.input_file === undefined) {\n      result = {publication: await publishSaved()};\n    } else {\n      if (typeof input.input_file !== \'string\' || typeof input.receipt_file !== \'string\')\n        throw new Error(\'Review requires existing changes and a private receipt path\');\n      const saved = await command([\'native-record\', \'--binding-file\', binding, \'--final-review\',\n        \'--input-file\', input.input_file, \'--receipt-file\', input.receipt_file], \'review_save\');\n      result = finishing || input.action === \'complete\' ? {...result, saved} : saved;\n      if (finishing || input.action === \'complete\') result.publication = await publishSaved();\n    }\n  } else if (input.action === \'yield\') result = await closeout(input.save_unconfirmed === true, false, \'yield\');\n  else if (input.action === \'release\') result = await closeout(input.save_unconfirmed === true, true);\n  else if (input.action === \'closeout\') result = await closeout(input.save_unconfirmed === true);\n  else throw new Error(\'Unknown cycle action\');\n} catch (error) {\n  failure = String(error);\n  // Only an explicitly requested finish may release a genuinely closed browser; a save error alone never ends a task.\n  // Never retry the save or publish an incomplete observation as a successful report.\n  if ([\'record\', \'review\'].includes(input.action) && input.finish_task === true && input.browser_stopped === true && !stages.some(s => s.stage === \'closeout_generate\')) {\n    try { result = {save_unconfirmed: true, closeout: await closeout(true)}; }\n    catch (cleanupError) { result = {save_unconfirmed: true, cleanup_error: String(cleanupError)}; }\n  }\n}\nconst record = {action: input.action, result, ...(failure ? {error: failure} : {}), stages};\n// Every invocation has its own artifact: no shared append race or overwritten failure receipt.\nconst log = config.directory + \'/cycle-\' + input.action + \'-\' + Date.now() + \'.json\';\nawait tools.apply_patch(\'*** Begin Patch\\n*** Add File: \' + log + \'\\n+\' + JSON.stringify(record, null, 2).replace(/\\n/g, \'\\n+\') + \'\\n*** End Patch\');\n// Keep the complete original receipt above. Omit only already-known static\n// instructions from model display; dynamic warnings/plans/results stay intact.\nconst display = JSON.parse(JSON.stringify(record));\nif (display.result?.baseline_receipt) delete display.result.baseline_receipt.title_guidance;\nif (display.result?.execution_client) delete display.result.execution_client.handoff_guidance;\n// These are invariant documentation strings repeated by every baseline save.\n// Keep every case, runtime gap, plan, warning and unknown field in the response;\n// the complete source receipt above remains available without another API call.\nconst baselineCoverage = display.result?.baseline_receipt?.coverage_check;\nif (baselineCoverage) {\n  for (const key of [\'ai_analysis_guidance\', \'requirement_basis_guidance\',\n    \'reproduction_guidance\', \'manual_action_guidance\', \'upload_fallback_guidance\',\n    \'not_run_guidance\', \'guidance\']) delete baselineCoverage[key];\n}\ndisplay.full_receipt_file = log;\ntext(display);\nif (failure) throw new Error(failure);\n'

NATIVE_CONTROL_TEMPLATE = '// Full control results are private files. Terminal text is never the result protocol.\nasync function nativeReadControl(tools, command, file) {\n  const quote = value => "\'" + String(value).replace(/\'/g, "\'\\\\\'\'") + "\'";\n  let offset = 0, content = \'\';\n  while (true) {\n    const args = [...command, \'native-control-read\', \'--file\', file, \'--offset\', String(offset)];\n    let execution = await tools.exec_command({cmd:args.map(quote).join(\' \'), max_output_tokens:12000, yield_time_ms:10000});\n    let output = execution.output;\n    while (execution.session_id && execution.exit_code == null) {\n      execution = await tools.write_stdin({session_id:execution.session_id, chars:\'\', max_output_tokens:12000, yield_time_ms:1000});\n      output += execution.output;\n    }\n    if (execution.exit_code !== 0) throw new Error(\'Original control receipt unavailable; do not replay the operation\');\n    const frames = output.split(\'\\n\').filter(line => line.startsWith(\'NATIVE_CONTROL_PART:\'));\n    if (frames.length !== 1) throw new Error(\'Control receipt frame missing or ambiguous; do not replay\');\n    const part = JSON.parse(frames[0].slice(\'NATIVE_CONTROL_PART:\'.length));\n    if (part.file !== file || part.offset !== offset || typeof part.text !== \'string\' ||\n        part.next !== offset + part.text.length || (!part.eof && part.next <= offset))\n      throw new Error(\'Control receipt sequence changed; preserve original files\');\n    content += part.text;\n    if (part.eof) return JSON.parse(content);\n    offset = part.next;\n  }\n}\n'

NATIVE_DELIVERY_TEMPLATE = '// Coordinator only: one invocation matches the event, acknowledges, then audits.\n// No browser work, business replay, model-written result text or receipt polling.\nconst quote = value => "\'" + String(value).replace(/\'/g, "\'\\\\\'\'") + "\'";\nasync function command(args) {\n  let r = await tools.exec_command({cmd: [...config.command, ...args].map(quote).join(\' \'),\n    yield_time_ms: 10000, max_output_tokens: 16000});\n  let output = r.output;\n  while (r.session_id && r.exit_code == null) {\n    r = await tools.write_stdin({session_id:r.session_id,chars:\'\',yield_time_ms:1000,max_output_tokens:16000});\n    output += r.output;\n  }\n  if (r.exit_code !== 0) throw new Error(output.slice(-3000));\n  return JSON.parse(output);\n}\nif (!input || input.task_id !== config.task_id || input.node_id !== config.node_id || !input.event_id)\n  throw new Error(\'Incoming handoff does not match original assignment\');\nconst generated = await command([\'native-ack-script\', \'--assignment-file\', config.assignment_file,\n  \'--binding-file\', config.directory + \'/binding.json\', \'--event-json\', JSON.stringify(input)]);\nlet ack;\nconst AF = Object.getPrototypeOf(async function(){}).constructor;\nawait new AF(\'tools\',\'text\',\'ALL_TOOLS\',generated.script)(tools,value=>{ack=value;},ALL_TOOLS);\nconst ackFile = config.directory + \'/coordinator-ack-\' + Date.now() + \'.json\';\nawait tools.apply_patch(\'*** Begin Patch\\n*** Add File: \' + ackFile + \'\\n+\'\n  + JSON.stringify(ack,null,2).replace(/\\n/g,\'\\n+\') + \'\\n*** End Patch\');\nconst outputFile = config.output_file || config.directory + \'/delivery-\' + Date.now() + \'.json\';\nconst delivered = await command([\'native-cycle-audit\',\'--binding-file\',config.directory+\'/binding.json\',\n  \'--ack-file\',ackFile,\'--output-file\',outputFile]);\n// This is already the deliverable. Display it directly; do not reconstruct it.\ntext(delivered);\n'

NATIVE_BROWSER_TEMPLATE = "// Helpers in the original native browser call. No platform proxy or credentials.\nasync function nativeBrowserCase({case_id, run, emit, observation: previous, preserve}) {\n  let receipt;\n  const observation = previous || {case_id, status: 'partial', checks: [], steps: [], timing: {started_at: new Date().toISOString()}};\n  if (observation.case_id !== case_id) throw new Error('Cannot resume another case journal');\n  delete observation.error;\n  observation.status = 'partial';\n  const stamp = () => new Date().toISOString();\n  const journal = {\n    check(name, expected, observed, ok) {\n      if (typeof ok !== 'boolean') throw new Error('Assertion must be boolean');\n      observation.checks.push({name, expected, observed, ok});\n      observation.timing.last_assertion_at = stamp();\n      return ok;\n    },\n    async step(name, action) {\n      const began = Date.now();\n      const step = {name, started_at: stamp()};\n      observation.steps.push(step);\n      try { const value = await action(); step.completed = true; return value; }\n      catch (error) { step.error = String(error); throw error; }\n      finally { step.finished_at = stamp(); step.duration_ms = Date.now() - began; }\n    },\n    // Only the read is repeated. Never replay a click, submit or navigation on timeout.\n    async until(read, ready, {timeout_ms = 10000, max_reads = 12} = {}) {\n      if (!(timeout_ms > 0 && timeout_ms <= 30000 && max_reads > 0 && max_reads <= 30))\n        throw new Error('Invalid bounded observation wait');\n      const began = Date.now(), deadline = began + timeout_ms;\n      for (let i = 0; i < max_reads; i++) {\n        // Spread read-only probes across the existing budget, with quick early\n        // checks and a final check at its boundary. Fast reads must not exhaust\n        // the count before the page has had its allowed time to settle.\n        if (i) {\n          const nextAt = began + timeout_ms * (i / (max_reads - 1)) ** 2;\n          const delay = Math.max(0, Math.min(nextAt, deadline) - Date.now());\n          if (delay) await new Promise(resolve => setTimeout(resolve, delay));\n        }\n        const state = await read();\n        if (ready(state)) return state;\n        if (Date.now() >= deadline) break;\n      }\n      throw new Error('Observed state did not reach the expected condition');\n    }\n  };\n  try {\n    await run(journal);\n    if (!observation.checks.length) throw new Error('No actual assertions');\n    observation.status = observation.checks.every(c => c.ok) ? 'passed' : 'failed';\n  } catch (error) {\n    observation.error = String(error);\n    observation.timing.interrupted_at = stamp();\n    if (preserve) {\n      try { await preserve(observation); } catch (error) { observation.preservation_error = String(error); }\n    }\n    // A tool/locator error is evidence for Codex's next decision, not a business\n    // assertion, a final case verdict, or permission to close/release anything.\n    return {case_id, status: 'interrupted', observation,\n      failed_step: [...observation.steps].reverse().find(step => step.error) || null,\n      browser_stopped: false, saved: false, error: String(error)};\n  }\n  observation.timing.finished_at = stamp();\n  if (emit) {\n    try { receipt = await emit(observation); }\n    catch (error) { receipt = {saved: false, error: String(error)}; }\n  }\n  return {case_id, status: observation.status, checks: observation.checks.length,\n    browser_stopped: false, save_receipt: receipt,\n    // Preserve a draft on missing/unknown save; don't require model reconstruction.\n    ...(!receipt?.saved ? {observation} : {})};\n}\n\n// Capture one already-observed state. No navigation, business replay, polling or retry.\n// A locator-only crop cannot establish the object's context. The default is the\n// current viewport; an optional detail is supplemental, never its replacement.\nasync function nativeCaptureEvidence({page, case_id, step, directory, detail, preview}) {\n  if (!case_id || typeof step !== 'string' || !step.trim()) throw new Error('Original case and evidence step required');\n  const fs=await import('node:fs/promises'), path=await import('node:path'), crypto=await import('node:crypto');\n  if (!path.isAbsolute(directory)) throw new Error('Private absolute evidence directory required');\n  const root=path.join(directory,'evidence');\n  await fs.mkdir(root,{recursive:true,mode:0o700});\n  const assets=[], result={assets,semantic_review_complete:false};\n  const capture=async (target,label,options)=>{\n    const file=path.join(root,crypto.randomUUID()+'.png'),captured_at=new Date().toISOString();\n    const bytes=await target.screenshot({...options,path:file});\n    await fs.chmod(file,0o600);\n    assets.push({file,case_id,step:label,kind:'screenshot',captured_at});\n    // Display the same captured bytes; do not take a second screenshot to inspect it.\n    if (preview) await preview(bytes);\n  };\n  try {\n    await capture(page,step,{fullPage:false});\n    if (detail) await capture(detail,step+'（补充特写）',{});\n  } catch (error) {result.capture_error=String(error);}\n  return result;\n}\n\n// Explicit final lifecycle boundary. Ordinary run/step errors never call this.\n// Recording a verdict and closing a task are separate decisions.\nasync function nativeFinishTask({close, directory}) {\n  const proof = await close();\n  if (!proof || proof.browser_stopped !== true || typeof proof.reason !== 'string' || !proof.reason.trim())\n    throw new Error('Actual exit proof required');\n  const fs = await import('node:fs/promises');\n  const binding = JSON.parse(await fs.readFile(directory + '/binding.json', 'utf8'));\n  await fs.writeFile(directory + '/native-explicit-exit.json', JSON.stringify({exit: proof,\n    binding: Object.fromEntries(['task_id','node_id','holder_id','lease_id'].map(key => [key,binding[key]])),\n    finished_at: new Date().toISOString()}), {encoding: 'utf8', mode: 0o600});\n  return proof;\n}\n"

NATIVE_ISOLATED_BROWSER_TEMPLATE = '// Imported once in Codex node_repl, never in restricted cua or a Runner.\n// Only browser lifecycle and local metadata live here. Page actions are direct\n// Playwright calls; this module has no platform client, transport or heartbeat.\nimport fs from \'node:fs/promises\';\nimport path from \'node:path\';\nimport {randomUUID} from \'node:crypto\';\nimport {homedir, hostname, platform} from \'node:os\';\nimport {createRequire} from \'node:module\';\nimport {spawn, execFile} from \'node:child_process\';\nimport {promisify} from \'node:util\';\nconst execute = promisify(execFile);\n\nasync function exists(file) {\n  try { await fs.access(file); return true; } catch (error) {\n    if (error.code === \'ENOENT\') return false;\n    throw error;\n  }\n}\nasync function installedRuntime(options, assignmentFile, runtimeContext) {\n  // Resolve only on the actual executor, once per created environment. No\n  // coordinator-machine paths, npm downloads or launch/probe round trips.\n  let modulePath = options.playwright_module;\n  const runtimeHome = runtimeContext.homeDir || homedir();\n  const runtimeCwd = runtimeContext.cwd || path.dirname(path.resolve(assignmentFile));\n  const packageRequire = createRequire(path.resolve(assignmentFile));\n  if (modulePath && !path.isAbsolute(modulePath)) throw new Error(\'Explicit Playwright module path must be absolute\');\n  if (!modulePath) {\n    for (const base of [path.resolve(assignmentFile), path.join(runtimeCwd, \'package.json\'),\n      path.join(runtimeHome, \'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/package.json\')]) {\n      try { modulePath = createRequire(base).resolve(\'playwright\'); break; }\n      catch (error) { if (error.code !== \'MODULE_NOT_FOUND\') throw error; }\n    }\n  }\n  if (!modulePath) throw new Error(\'Executor has no installed Playwright runtime; report capability gap, never use shared IAB or Runner\');\n  // Playwright\'s resolved entry is CommonJS. The REPL\'s ESM file loader\n  // does not supply module/exports; keep this package in Node\'s native loader.\n  const imported = packageRequire(modulePath);\n  const chromium = imported.chromium || imported.default?.chromium;\n  if (!chromium) throw new Error(\'Installed runtime does not expose Chromium\');\n  const launch = {headless: true};\n  if (options.channel && options.channel !== \'chrome\') throw new Error(\'Unsupported installed browser channel\');\n  if (options.channel || !await exists(chromium.executablePath())) {\n    const candidates = platform() === \'darwin\' ? [\'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome\',\n      path.join(runtimeHome, \'Applications/Google Chrome.app/Contents/MacOS/Google Chrome\')] :\n      platform() === \'win32\' ? [path.join(path.parse(runtimeHome).root, \'Program Files\'),\n        path.join(path.parse(runtimeHome).root, \'Program Files (x86)\'), path.join(runtimeHome, \'AppData/Local\')]\n        .map(base => path.join(base, \'Google/Chrome/Application/chrome.exe\')) :\n        [\'/usr/bin/google-chrome\', \'/usr/bin/google-chrome-stable\', \'/usr/bin/chromium\', \'/usr/bin/chromium-browser\'];\n    for (const candidate of candidates) {\n      if (await exists(candidate)) { launch.executablePath = candidate; break; }\n    }\n    if (!launch.executablePath) throw new Error(\'Executor has no installed Chromium/Chrome; report capability gap, never use a shared browser profile\');\n  }\n  return {chromium, executable: launch.executablePath || chromium.executablePath()};\n}\n\nconst environments = new Map();\nconst inflight = new Map();\nconst identityKeys = [\'task_id\', \'node_id\', \'holder_id\', \'executor_ref\'];\nconst executorIdentity = value => {\n  if (typeof value !== \'string\') return value;\n  const id = value.replace(/^thread:/, \'\');\n  return /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(id) ? id.toLowerCase() : value;\n};\nconst sameIdentity = (left, right) => identityKeys.every(key => key === \'executor_ref\'\n  ? executorIdentity(left?.[key]) === executorIdentity(right?.[key]) : left?.[key] === right?.[key]);\nconst now = () => new Date().toISOString();\nasync function persist(file, value) {\n  const temporary = file + \'.\' + randomUUID() + \'.tmp\';\n  await fs.writeFile(temporary, JSON.stringify(value), {encoding: \'utf8\', mode: 0o600});\n  await fs.rename(temporary, file);\n}\n\n// The browser process and its private profile outlive the REPL connection.\n// Default persistent contexts survive CDP disconnect; newContext() does not.\nconst PROCESS_TIMEOUT = 5000;\nasync function processRows(pid, timeout) {\n  const options = {maxBuffer: 8 * 1024 * 1024, timeout: Math.max(1, timeout), killSignal: \'SIGKILL\'};\n  if (platform() === \'win32\') {\n    const filter = pid ? \' -Filter "ProcessId = \' + pid + \'"\' : \'\';\n    const {stdout} = await execute(\'powershell.exe\', [\'-NoProfile\', \'-NonInteractive\', \'-Command\',\n      \'Get-CimInstance Win32_Process\' + filter + \' | Select-Object ProcessId,CommandLine,CreationDate | ConvertTo-Json -Compress\'], options);\n    const parsed = JSON.parse(stdout || \'[]\');\n    return (Array.isArray(parsed) ? parsed : [parsed]).filter(Boolean)\n      .map(row => ({pid: Number(row.ProcessId), command: row.CommandLine || \'\', started_at: row.CreationDate || null}));\n  }\n  let stdout;\n  try {\n    ({stdout} = await execute(\'ps\', [\'-ww\', ...(pid ? [\'-p\', String(pid)] : [\'-ax\']), \'-o\', \'pid=,lstart=,command=\'], {...options, env: {LC_ALL: \'C\'}}));\n  } catch (error) {\n    // ps returns 1 with no rows for a PID that genuinely no longer exists.\n    // Any timeout, signal, stderr or other failure leaves ownership unknown.\n    if (pid && error.code === 1 && !error.killed && !error.signal && !String(error.stdout || \'\').trim() && !String(error.stderr || \'\').trim()) return [];\n    throw error;\n  }\n  return stdout.split(\'\\n\').filter(line => line.trim()).map(line => {\n    const match = line.match(/^\\s*(\\d+)\\s+(\\w{3}\\s+\\w{3}\\s+\\d{1,2}\\s+\\d{2}:\\d{2}:\\d{2}\\s+\\d{4})\\s+(.*)$/);\n    if (!match) throw new Error(\'Invalid process query response\');\n    return {pid: Number(match[1]), started_at: match[2].replace(/\\s+/g, \' \'), command: match[3]};\n  });\n}\nfunction ownsProcess(row, profile) {\n  // Require complete argument boundaries, including profiles containing spaces.\n  // A PID alone, a substring of another profile, or a Chromium child is not proof.\n  const escaped = profile.replace(/[.*+?^${}()|[\\]\\\\]/g, \'\\\\$&\');\n  const argument = new RegExp(\'(?:^|\\\\s)(?:"--user-data-dir=\' + escaped + \'"|--user-data-dir="\' + escaped + \'"|--user-data-dir=\' + escaped + \')(?=\\\\s|$)\');\n  return argument.test(row.command) && /(?:^|\\s)--remote-debugging-port=0(?=\\s|$)/.test(row.command)\n    && !/(?:^|\\s)--type=/.test(row.command);\n}\nasync function ownedProcesses(slot, timeout = PROCESS_TIMEOUT, verifyLaunched = false) {\n  const started = Date.now(), deadline = started + Math.max(1, timeout);\n  const evidence = {process_state: \'unknown\', process_query: Number.isSafeInteger(slot.pid) && slot.pid > 0 ? \'saved_pid\' : \'profile_scan\'};\n  try {\n    let rows;\n    if (verifyLaunched && evidence.process_query !== \'saved_pid\') { evidence.process_reason = \'launched_process_unverified\'; return evidence; }\n    if (evidence.process_query === \'saved_pid\') {\n      rows = await processRows(slot.pid, deadline - Date.now());\n      if (rows.length) {\n        if (rows.length !== 1 || rows[0].pid !== slot.pid || !ownsProcess(rows[0], slot.profile)) {\n          evidence.process_reason = \'saved_pid_not_owned\'; return evidence;\n        }\n        if (slot.process_started_at && rows[0].started_at !== slot.process_started_at) {\n          evidence.process_reason = \'saved_pid_generation_changed\'; return evidence;\n        }\n      } else {\n        // A just-spawned PID must be verified directly; discovery cannot replace it.\n        if (verifyLaunched) { evidence.process_reason = \'launched_process_unverified\'; return evidence; }\n        evidence.process_query = \'saved_pid_absent_profile_scan\';\n      }\n    }\n    if (!rows?.length) {\n      if (Date.now() >= deadline) throw Object.assign(new Error(\'Process discovery deadline exceeded\'), {code: \'ETIMEDOUT\'});\n      rows = (await processRows(null, deadline - Date.now())).filter(row => ownsProcess(row, slot.profile));\n      if (rows.length === 1 && slot.process_started_at && (rows[0].started_at !== slot.process_started_at || rows[0].pid !== slot.pid)) {\n        evidence.process_reason = \'profile_process_generation_changed\'; return evidence;\n      }\n    }\n    if (rows.length && slot.process_identity_required && !slot.process_started_at && !verifyLaunched) {\n      evidence.process_reason = \'process_generation_unverified\'; return evidence;\n    }\n    if (verifyLaunched && (rows.length !== 1 || !rows[0].started_at)) {\n      evidence.process_reason = \'launched_process_unverified\'; return evidence;\n    }\n    evidence.process_state = !rows.length ? \'absent\' : rows.length === 1 ? \'present\' : \'ambiguous\';\n    evidence.pids = rows.map(row => row.pid);\n    if (rows.length === 1) { evidence.pid = rows[0].pid; evidence.process_started_at = rows[0].started_at; }\n    return evidence;\n  } catch (error) {\n    evidence.process_reason = \'query_failed\'; evidence.error_name = error.name;\n    evidence.error_code = error.code || error.cause?.code || null;\n    return evidence;\n  } finally { evidence.process_elapsed_ms = Date.now() - started; }\n}\nfunction requireKnownProcess(evidence) {\n  if (![\'present\', \'absent\'].includes(evidence.process_state))\n    throw Object.assign(new Error(\'Owned process state unknown or ambiguous; preserve original environment\'), {process_evidence: evidence});\n  return evidence.pids;\n}\nasync function bounded(operation, timeout, stage, lateCleanup) {\n  let timer, expired = false;\n  const pending = Promise.resolve().then(operation);\n  pending.then(value => { if (expired) return Promise.resolve().then(() => lateCleanup?.(value)); }).catch(() => {});\n  try {\n    return await Promise.race([pending, new Promise((_, reject) => {\n      timer = setTimeout(() => { expired = true; reject(Object.assign(new Error(stage + \' deadline exceeded; preserve original environment\'), {code: \'ETIMEDOUT\'})); }, Math.max(1, timeout));\n    })]);\n  } finally { clearTimeout(timer); }\n}\nasync function endpoint(slot) {\n  const [port, route] = (await fs.readFile(path.join(slot.profile, \'DevToolsActivePort\'), \'utf8\')).trim().split(\'\\n\');\n  if (!/^\\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535 || !route?.startsWith(\'/devtools/browser/\'))\n    throw new Error(\'Invalid owned browser endpoint\');\n  return \'ws://127.0.0.1:\' + port + route;\n}\nasync function targetId(context, page) {\n  const deadline = Date.now() + 15000;\n  const cdp = await bounded(() => context.newCDPSession(page), 15000, \'CDP target session\', session => session.detach());\n  try { return (await bounded(() => cdp.send(\'Target.getTargetInfo\'), deadline - Date.now(), \'CDP target identity\')).targetInfo.targetId; }\n  finally { await bounded(() => cdp.detach(), Math.max(1, deadline - Date.now()), \'CDP target detach\'); }\n}\n\n// Explicit, read-only fault evidence. Never inspect page content, credentials,\n// or unrelated browsers. Endpoint availability is not business success.\nexport async function diagnose({assignment_file, directory}) {\n  const root = path.resolve(directory);\n  const receipt = JSON.parse(await fs.readFile(path.join(root, \'browser-environment.json\'), \'utf8\'));\n  const assignment = JSON.parse(await fs.readFile(assignment_file, \'utf8\'));\n  if (receipt.schema !== 2 || !sameIdentity(receipt.identity, assignment))\n    throw new Error(\'Original owned environment receipt required\');\n  const started = Date.now();\n  const result = {started_at: now(), environment_state: receipt.state, business_result: \'unknown\', slots: []};\n  const file = path.join(root, \'browser-diagnostic-\' + randomUUID() + \'.json\');\n  for (const slot of receipt.slots) {\n    const slotStarted = Date.now();\n    const item = {context_id: slot.context_id, generation: slot.generation,\n      process_state: \'unknown\', endpoint_state: \'not_checked\', cdp_control_state: \'not_checked\', stage: \'process_discovery\'};\n    result.slots.push(item);\n    await persist(file, result);\n    try {\n      const evidence = await ownedProcesses(slot);\n      Object.assign(item, evidence);\n      if (evidence.process_state === \'present\') {\n        item.stage = \'endpoint_file\'; await persist(file, result);\n        const ws = new URL(await endpoint(slot));\n        item.stage = \'endpoint_probe\'; await persist(file, result);\n        const response = await fetch(\'http://127.0.0.1:\' + ws.port + \'/json/version\',\n          {signal: AbortSignal.timeout(3000), redirect: \'error\'});\n        item.http_status = response.status;\n        item.endpoint_state = response.ok ? \'reachable\' : \'http_error\';\n        await response.body?.cancel();\n      }\n    } catch (error) {\n      item.error_name = error.name;\n      item.error_code = error.code || error.cause?.code || null;\n      if (item.stage !== \'process_discovery\') item.endpoint_state = \'unavailable\';\n    }\n    item.elapsed_ms = Date.now() - slotStarted; item.finished_at = now(); await persist(file, result);\n  }\n  result.elapsed_ms = Date.now() - started; result.finished_at = now(); await persist(file, result);\n  return {...result, diagnostic_file: file};\n}\n\nfunction assignmentScope(assignment, target, existing) {\n  const options = assignment.direct_browser || {};\n  const hostId = options.host_id || hostname();\n  const url = new URL(target);\n  if (![\'http:\', \'https:\'].includes(url.protocol) || url.username || url.password)\n    throw new Error(\'Expected original HTTP(S) target without credentials\');\n  const identity = Object.fromEntries(identityKeys.map(key => [key, assignment[key]]));\n  if (identityKeys.some(key => typeof identity[key] !== \'string\' || !identity[key])) throw new Error(\'Original identity required\');\n  const count = options.context_count ?? assignment.claim_arguments?.account_ids?.length ?? 1;\n  if (!Number.isSafeInteger(count) || count < 1) throw new Error(\'Invalid account context count\');\n  const signature = JSON.stringify([{...identity, executor_ref:executorIdentity(identity.executor_ref)}, url.origin, hostId, count]);\n  if (existing && !existing.closed && existing.signature !== signature) throw new Error(\'Environment belongs to another assignment\');\n  return {options, hostId, url, identity, count, signature};\n}\nfunction receiptScope(receipt, {identity, url, hostId, count}) {\n  if (receipt && !sameIdentity(receipt.identity, identity)) throw new Error(\'Receipt belongs to another executor\');\n  if (receipt && receipt.state !== \'closed\' && receipt.schema !== 2)\n    throw new Error(\'Legacy live environment: keep original scene; only upgrade after its actual exit is confirmed\');\n  if (receipt?.schema === 2 && (receipt.origin !== url.origin || receipt.host_id !== hostId || (receipt.state !== \'closed\' && receipt.slots.length !== count)))\n    throw new Error(\'Original environment scope changed\');\n}\n\n// Deliberate connection recovery, including a connected-but-unresponsive REPL\n// handle. Disconnect CDP only; do not close Chrome, navigate, or restart it.\nexport async function reconnect(options) {\n  const root = path.resolve(options.directory);\n  if (inflight.has(root)) throw new Error(\'Environment preparation in progress; preserve original operation\');\n  const assignment = JSON.parse(await fs.readFile(options.assignment_file, \'utf8\'));\n  const receipt = JSON.parse(await fs.readFile(path.join(root, \'browser-environment.json\'), \'utf8\'));\n  const scope = assignmentScope(assignment, options.origin, environments.get(root));\n  receiptScope(receipt, scope);\n  const diagnosis = await diagnose(options);\n  if (diagnosis.environment_state === \'closed\') throw new Error(\'Original environment is closed; cannot reconnect\');\n  if (diagnosis.slots.some(slot => slot.process_state === \'absent\'))\n    throw new Error(\'Owned browser exited; inspect diagnostic receipt before explicit restart_exited:true\');\n  if (diagnosis.slots.some(slot => slot.process_state !== \'present\'))\n    throw new Error(\'Owned process state unknown or ambiguous; inspect diagnostic receipt\');\n  const file = path.join(root, \'browser-reconnect-\' + randomUUID() + \'.json\');\n  const started = Date.now();\n  const attempt = {started_at: now(), diagnostic_file: diagnosis.diagnostic_file, stage: \'disconnect\', state: \'pending\', cdp_control_state: \'not_checked\', stages: []};\n  await persist(file, attempt);\n  try {\n    const existing = environments.get(root);\n    if (existing) for (const browser of existing.browsers) await bounded(() => browser.close(), 5000, \'CDP disconnect\'); // CDP disconnect only.\n    attempt.stages.push({stage: \'disconnect\', elapsed_ms: Date.now() - started});\n    attempt.stage = \'connect_original\'; await persist(file, attempt);\n    const session = await prepare({...options, restart_exited: false});\n    attempt.stages.push({stage: \'connect_original\', elapsed_ms: Date.now() - started - attempt.stages[0].elapsed_ms});\n    attempt.state = \'connected\'; attempt.cdp_control_state = \'connected\'; attempt.elapsed_ms = Date.now() - started; attempt.finished_at = now(); await persist(file, attempt);\n    session.recovery_receipt_file = file;\n    return session;\n  } catch (error) {\n    attempt.state = \'failed\'; attempt.cdp_control_state = \'failed\'; attempt.error_name = error.name; attempt.error_code = error.code || null;\n    attempt.elapsed_ms = Date.now() - started; attempt.finished_at = now();\n    await persist(file, attempt);\n    throw error;\n  }\n}\nexport async function prepare({assignment_file, directory, origin, runtime_context = {}, restart_exited = false}) {\n  const root = path.resolve(directory);\n  if (inflight.has(root)) {\n    const pending = inflight.get(root);\n    if (pending.assignment_file !== assignment_file || pending.origin !== origin || pending.restart_exited !== restart_exited)\n      throw new Error(\'Another environment request owns this directory\');\n    return pending.operation;\n  }\n  const operation = create(assignment_file, root, origin, runtime_context, restart_exited);\n  inflight.set(root, {assignment_file, origin, restart_exited, operation});\n  try { return await operation; } finally { inflight.delete(root); }\n}\nasync function create(assignmentFile, root, target, runtimeContext, restartExited) {\n  const assignment = JSON.parse(await fs.readFile(assignmentFile, \'utf8\'));\n  const existing = environments.get(root);\n  const token = assignment.claim_arguments?.work_token;\n  if (token && (!existing || existing.closed)) {\n    let ready;\n    try { ready = JSON.parse(await fs.readFile(path.join(root, \'stage-ready.json\'), \'utf8\')); }\n    catch (_) { throw new Error(\'Work stage preflight missing; do not create browser\'); }\n    if (ready.stage_ready !== true || !sameIdentity(ready.identity, assignment) ||\n        [\'work_unit_id\',\'plan_revision\',\'requirements_digest\'].some(k => ready.work_token?.[k] !== token[k]) ||\n        JSON.stringify(ready.account_ids) !== JSON.stringify(assignment.claim_arguments.account_ids) ||\n        ready.required_context_count !== assignment.claim_arguments.account_ids?.length ||\n        (assignment.direct_browser?.context_count ?? ready.required_context_count) !== ready.required_context_count)\n      throw new Error(\'Work stage preflight mismatched; do not create browser\');\n  }\n  const {options, hostId, url, identity, count, signature} = assignmentScope(assignment, target, existing);\n  if (existing && !existing.closed && existing.browsers.every(browser => browser.isConnected())) return existing;\n  await fs.mkdir(root, {recursive: true, mode: 0o700});\n  const receiptFile = path.join(root, \'browser-environment.json\');\n  let receipt;\n  try { receipt = JSON.parse(await fs.readFile(receiptFile, \'utf8\')); }\n  catch (error) { if (error.code !== \'ENOENT\') throw error; }\n  receiptScope(receipt, {identity, url, hostId, count});\n  if (!receipt || receipt.state === \'closed\') {\n    const previous = receipt;\n    const slots = [];\n    for (let i = 0; i < count; i++) slots.push({context_id: randomUUID(), profile: await fs.mkdtemp(path.join(root, \'browser-profile-\')), generation: 0});\n    receipt = {schema: 2, identity, host_id: hostId, origin: url.origin, state: \'creating\', browser_tool: \'node_repl\',\n      started_at: now(), slots, environments: slots.map(slot => ({host_id: hostId, browser: \'chromium\', origin: url.origin,\n        isolation: \'isolated\', context_id: slot.context_id, evidence: \'Dedicated Chromium process and private persistent profile; direct local CDP connection\',\n        capability_evidence: {source: \'public_tool\', capability: \'isolated_login_context\', context_id: slot.context_id,\n          reference: \'Chromium --user-data-dir isolation; Playwright chromium.connectOverCDP default persistent context\'}})),\n      ...(previous ? {previous_environment: {environments: previous.environments, closed_at: previous.closed_at}} : {})};\n    await persist(receiptFile, receipt);\n  }\n  const {chromium, executable} = await installedRuntime(options, assignmentFile, runtimeContext);\n  const browsers = [], contexts = [], pages = [];\n  for (const slot of receipt.slots) {\n    const evidence = await ownedProcesses(slot);\n    slot.process_evidence = evidence;\n    await persist(receiptFile, receipt);\n    const pids = requireKnownProcess(evidence);\n    if (!pids.length) {\n      if (slot.generation && !restartExited)\n        throw new Error(\'Owned browser exited; inspect original receipts, then explicitly prepare with restart_exited:true. No business replay.\');\n      if (slot.generation) {\n        // Keep the logical context/profile for an active lease\'s reconnect;\n        // the new real process gets a distinct reported browser generation.\n        const previousId = slot.context_id;\n        const environment = receipt.environments.find(item => item.context_id === previousId);\n        if (!environment) throw new Error(\'Original environment evidence missing; preserve receipt for inspection\');\n        receipt.exited_environments ||= [];\n        receipt.exited_environments.push({context_id: previousId, generation: slot.generation,\n          exited_observed_at: now(), evidence: \'Owned profile has no live Chromium process before explicit restart\'});\n      }\n      // Remove only this owned stale endpoint. Chrome still enforces its profile lock.\n      await fs.rm(path.join(slot.profile, \'DevToolsActivePort\'), {force: true});\n      slot.generation += 1; slot.entered = false; delete slot.target_id; delete slot.process_started_at; delete slot.pid;\n      // Persist before spawn, so a crash cannot downgrade this generation to\n      // legacy discovery merely because its PID/birth receipt is incomplete.\n      slot.process_identity_required = true;\n      receipt.state = \'creating\';\n      receipt.environments.find(item => item.context_id === slot.context_id).browser_generation = slot.generation;\n      await persist(receiptFile, receipt);\n      const child = spawn(executable, [\'--user-data-dir=\' + slot.profile, \'--remote-debugging-address=127.0.0.1\',\n        \'--remote-debugging-port=0\', \'--headless=new\', \'--no-first-run\', \'--no-default-browser-check\',\n        \'--disable-background-networking\', \'about:blank\'], {detached: true, stdio: \'ignore\'});\n      await new Promise((resolve, reject) => { child.once(\'spawn\', resolve); child.once(\'error\', reject); });\n      child.unref(); slot.pid = child.pid; slot.launched_at = now();\n      await persist(receiptFile, receipt);\n      const launchedEvidence = await ownedProcesses(slot, PROCESS_TIMEOUT, true);\n      slot.process_evidence = launchedEvidence;\n      if (launchedEvidence.process_state === \'present\') slot.process_started_at = launchedEvidence.process_started_at;\n      await persist(receiptFile, receipt);\n      requireKnownProcess(launchedEvidence);\n    } else {\n      slot.pid = evidence.pid; slot.process_started_at = evidence.process_started_at;\n      await persist(receiptFile, receipt);\n    }\n    // Startup wait is only for the owned endpoint, never a page-action wrapper.\n    const connectionStarted = Date.now();\n    const connection = slot.connection_evidence = {started_at: now(), stage: \'endpoint_file\', cdp_control_state: \'not_checked\', stages: []};\n    let browser;\n    try {\n      await persist(receiptFile, receipt);\n      const deadline = Date.now() + 15000;\n      let ws;\n      while (!ws) {\n        try { ws = await endpoint(slot); }\n        catch (error) {\n          if (error.code !== \'ENOENT\' || Date.now() >= deadline) throw error;\n          await new Promise(resolve => setTimeout(resolve, 100));\n        }\n      }\n      connection.stages.push({stage: \'endpoint_file\', elapsed_ms: Date.now() - connectionStarted});\n      connection.stage = \'cdp_connect\'; await persist(receiptFile, receipt);\n      const connectStarted = Date.now();\n      browser = await bounded(() => chromium.connectOverCDP(ws, {timeout: 15000}), 15000, \'CDP connect\', late => late.close());\n      connection.stages.push({stage: \'cdp_connect\', elapsed_ms: Date.now() - connectStarted});\n      connection.stage = \'target_selection\'; await persist(receiptFile, receipt);\n      const selectionStarted = Date.now();\n      const context = browser.contexts()[0];\n      if (!context) throw new Error(\'Owned persistent browser context unavailable\');\n      let page;\n      for (const candidate of context.pages()) {\n        if (slot.target_id && await targetId(context, candidate) === slot.target_id) { page = candidate; break; }\n      }\n      if (page || !slot.target_id) {\n        page ||= context.pages()[0] || await bounded(() => context.newPage(), 15000, \'Owned blank page creation\');\n        slot.target_id = await targetId(context, page);\n      }\n      // A closed business tab is reported as null, never recreated or navigated.\n      browsers.push(browser); contexts.push(context); pages.push(page || null);\n      connection.stages.push({stage: \'target_selection\', elapsed_ms: Date.now() - selectionStarted});\n      connection.cdp_control_state = \'connected\'; connection.stage = \'ready\';\n      connection.elapsed_ms = Date.now() - connectionStarted; connection.finished_at = now();\n      await persist(receiptFile, receipt);\n    } catch (error) {\n      connection.cdp_control_state = connection.stage === \'endpoint_file\' ? \'not_checked\' : \'failed\';\n      connection.error_name = error.name; connection.error_code = error.code || null;\n      connection.elapsed_ms = Date.now() - connectionStarted; connection.finished_at = now();\n      await persist(receiptFile, receipt);\n      // Disconnect only connections created by this failed attempt. The browser\n      // processes, profiles and original business pages remain untouched.\n      await Promise.all([...new Set([...browsers, browser].filter(Boolean))].map(connected =>\n        bounded(() => connected.close(), 5000, \'Failed preparation CDP disconnect\').catch(() => {})));\n      throw error;\n    }\n  }\n  receipt.state = \'open\'; receipt.ready_at ||= now(); receipt.connected_at = now();\n  await persist(receiptFile, receipt);\n  let bound = false, activeIndex = 0, closePromise;\n  const pagesByAccount = new Map(), accountSlots = new Map();\n  const session = {signature, browsers, browser: browsers[0], contexts, pages, pagesByAccount, closed: false,\n    async enter(entryUrl) {\n      if (session.closed || browsers.some(browser => !browser.isConnected())) throw new Error(\'Connection lost; rerun environment_setup to reconnect original browser\');\n      if (!bound) {\n        const binding = JSON.parse(await fs.readFile(path.join(root, \'binding.json\'), \'utf8\'));\n        const assigned = binding.native_context_binding?.contexts || [];\n        if (!sameIdentity(binding, identity) || !binding.lease_id ||\n            assigned.length !== (binding.account_ids || []).length || assigned.length > pages.length ||\n            new Set(assigned.map(row => row.account_id)).size !== assigned.length ||\n            new Set(assigned.map(row => row.context_id)).size !== assigned.length)\n          throw new Error(\'Original account/environment assignment does not match\');\n        for (const row of assigned) {\n          const index = receipt.environments.findIndex(item => item.context_id === row.context_id && item.origin === row.origin &&\n            item.host_id === row.host_id && item.browser === row.browser && row.isolation === \'isolated\');\n          if (index < 0 || !binding.account_ids.includes(row.account_id)) throw new Error(\'Context not owned by this executor\');\n          pagesByAccount.set(row.account_id, pages[index]); accountSlots.set(row.account_id, index);\n          if (row === assigned[0]) activeIndex = index;\n        }\n        bound = true;\n      }\n      const page = pages[activeIndex], slot = receipt.slots[activeIndex];\n      if (!page || page.isClosed()) throw new Error(\'Original tab closed; inspect context.pages() and explicitly select a page with selectPage()\');\n      if (!slot.entered) {\n        const entry = new URL(entryUrl);\n        if (entry.origin !== url.origin || entry.username || entry.password) throw new Error(\'Entry target changed\');\n        slot.entered = true;\n        await persist(receiptFile, receipt); // Unknown navigation is never replayed.\n        await page.goto(entry.href, {waitUntil: \'domcontentloaded\', timeout: 15000});\n      }\n      return page;\n    },\n    async selectPage(index, page) {\n      if (!contexts[index]?.pages().includes(page)) throw new Error(\'Page is not in this owned context\');\n      pages[index] = page;\n      for (const [account, slot] of accountSlots) if (slot === index) pagesByAccount.set(account, page);\n      receipt.slots[index].target_id = await targetId(contexts[index], page);\n      receipt.slots[index].entered = true;\n      await persist(receiptFile, receipt);\n      return page;\n    },\n    async close() {\n      if (!closePromise) closePromise = closeOwned({assignment_file: assignmentFile, directory: root,\n        runtime_context: runtimeContext}).then(proof => { session.closed = true; return proof; })\n        .catch(error => { closePromise = undefined; throw error; });\n      return closePromise;\n    }\n  };\n  environments.set(root, session);\n  return session;\n}\n\n// For a genuinely exited browser, including partial startup. This only checks\n// owned processes and records evidence; it never kills or restarts a browser.\nexport async function confirmExit(directory) {\n  const root = path.resolve(directory), file = path.join(root, \'browser-environment.json\');\n  const receipt = JSON.parse(await fs.readFile(file, \'utf8\'));\n  if (receipt.schema !== 2) throw new Error(\'Legacy exit requires the original executor evidence\');\n  const evidence = await Promise.all(receipt.slots.map(slot => ownedProcesses(slot)));\n  if (evidence.some(item => requireKnownProcess(item).length)) throw new Error(\'Owned browser still running; no exit confirmed\');\n  return recordExit(root, file, receipt, evidence);\n}\nasync function recordExit(root, file, receipt, evidence) {\n  receipt.exit_process_evidence = evidence;\n  receipt.state = \'closed\'; receipt.closed_at = now();\n  await persist(file, receipt);\n  const session = environments.get(root); if (session) session.closed = true;\n  return {browser_stopped: true, reason: \'All original private-profile browser processes confirmed absent\',\n    context_ids: receipt.environments.map(row => row.context_id)};\n}\n\n// Explicit cleanup also works after partial startup or a lost REPL. It connects\n// only living owned profiles, never starts a dead slot or replays any business.\nexport async function closeOwned({assignment_file, directory, runtime_context = {}}) {\n  const root = path.resolve(directory), file = path.join(root, \'browser-environment.json\');\n  const receipt = JSON.parse(await fs.readFile(file, \'utf8\'));\n  const assignment = JSON.parse(await fs.readFile(assignment_file, \'utf8\'));\n  if (receipt.schema !== 2 || !sameIdentity(receipt.identity, assignment))\n    throw new Error(\'Original owned environment receipt required\');\n  const {chromium} = await installedRuntime(assignment.direct_browser || {}, assignment_file, runtime_context);\n  receipt.close_started_at = now(); await persist(file, receipt);\n  const errors = [];\n  for (const slot of receipt.slots) {\n    const evidence = await ownedProcesses(slot);\n    slot.close_process_evidence = evidence;\n    await persist(file, receipt);\n    if (![\'present\', \'absent\'].includes(evidence.process_state)) {\n      errors.push(\'Owned process state unknown or ambiguous; preserve original slot\'); continue;\n    }\n    const pids = evidence.pids;\n    if (!pids.length) continue;\n    let browser;\n    try {\n      const deadline = Date.now() + 5000;\n      const ws = await endpoint(slot);\n      browser = await bounded(() => chromium.connectOverCDP(ws, {timeout: 5000}), deadline - Date.now(), \'Cleanup CDP connect\', late => late.close());\n      const cdp = await bounded(() => browser.newBrowserCDPSession(), deadline - Date.now(), \'Cleanup CDP session\', late => late.detach());\n      await bounded(() => cdp.send(\'Browser.close\'), deadline - Date.now(), \'Owned browser close\');\n    } catch (error) { errors.push(String(error)); }\n    finally { if (browser?.isConnected()) await bounded(() => browser.close(), 5000, \'Cleanup CDP disconnect\').catch(() => {}); } // CDP disconnect only.\n  }\n  const deadline = Date.now() + 5000;\n  while (true) {\n    const evidence = await Promise.all(receipt.slots.map(slot => ownedProcesses(slot, deadline - Date.now())));\n    const states = evidence.map(item => requireKnownProcess(item));\n    if (states.every(pids => !pids.length)) return recordExit(root, file, receipt, evidence);\n    if (Date.now() >= deadline) throw new Error(\'Owned browser exit unconfirmed; preserve binding. \' + errors.join(\'; \'));\n    await new Promise(resolve => setTimeout(resolve, Math.min(100, deadline - Date.now())));\n  }\n}\n'

NATIVE_OBSERVATION_SEND_TEMPLATE = "// Local artifacts only. No browser control, platform credentials or model loop.\nasync function nativeReadObservationReceipt(directory, request_id, {reconcile = false} = {}) {\n  if (!/^[0-9]+-[a-f0-9]+$/.test(request_id)) throw new Error('Invalid observation request ID');\n  if (reconcile) {\n    const fs = await import('node:fs/promises');\n    const {constants} = await import('node:fs');\n    const abort = new AbortController(), events = fs.watch(directory, {signal: abort.signal});\n    let timer;\n    try {\n      const changed = events.next().catch(() => ({done:true}));\n      const fifo = await fs.open(directory + '/native-observations.fifo', constants.O_WRONLY | constants.O_NONBLOCK);\n      try { await fifo.writeFile(JSON.stringify({request_id,reconcile:true}) + '\\n'); } finally { await fifo.close(); }\n      await Promise.race([changed, new Promise(resolve => {timer = setTimeout(resolve, 10000);})]);\n    } finally {clearTimeout(timer);abort.abort();await events.return();}\n  }\n  const fs = await import('node:fs/promises');\n  for (const file of [directory + '/native-receiver-response-' + request_id + '.json', directory + '/native-receiver-response.json']) {\n    try { const value = JSON.parse(await fs.readFile(file, 'utf8'));\n      if (value.request_id === request_id) return value;\n    } catch (error) { if (error.code !== 'ENOENT') throw error; }\n  }\n  return {request_id, saved: false, pending: true};\n}\nasync function nativeSendObservation(directory, observation, {wait_ms = 10000} = {}) {\n  const fs = await import('node:fs/promises');\n  const {constants} = await import('node:fs');\n  const awaiting = directory + '/native-observation-awaiting.json';\n  try {\n    const previous = JSON.parse(await fs.readFile(awaiting, 'utf8'));\n    const result = await nativeReadObservationReceipt(directory, previous.request_id);\n    if (result.saved !== true && !['not_sent','rejected'].includes(result.state)) return {...result, new_observation_sent: false};\n    await fs.unlink(awaiting);\n  } catch (error) { if (error.code !== 'ENOENT') throw error; }\n  if (!Number.isFinite(wait_ms) || wait_ms < 0 || wait_ms > 20000) throw new Error('Invalid receipt observation budget');\n  const request_id = String(Date.now()) + '-' + Math.random().toString(16).slice(2);\n  const abort = new AbortController();\n  const events = fs.watch(directory, {signal: abort.signal});\n  const next = () => events.next().catch(error => ({done:true,error}));\n  let changed = next(), timer;\n  const deadline = new Promise(resolve => { timer = setTimeout(() => resolve({done:true}), wait_ms); });\n  try {\n    await fs.writeFile(directory + '/observation-inbox-' + request_id + '.json', JSON.stringify(observation), {encoding:'utf8',mode:0o600,flag:'wx'});\n    await fs.writeFile(directory + '/native-last-observation.json', JSON.stringify({request_id}), {encoding:'utf8',mode:0o600});\n    await fs.writeFile(awaiting, JSON.stringify({request_id}), {encoding:'utf8',mode:0o600,flag:'wx'});\n    let inbox;\n    try { inbox = await fs.open(directory + '/native-observations.fifo', constants.O_WRONLY | constants.O_NONBLOCK); }\n    catch (error) {\n      if (!['ENOENT','ENXIO'].includes(error.code)) throw error;\n      const result = {request_id, saved:false, state:'not_sent', error:String(error)};\n      await fs.writeFile(directory + '/native-receiver-response-' + request_id + '.json', JSON.stringify(result), {encoding:'utf8',mode:0o600});\n      await fs.unlink(awaiting);\n      return result; // No notification reached a receiver; Codex can repair it.\n    }\n    try { await inbox.writeFile(JSON.stringify({request_id}) + '\\n'); }\n    finally { await inbox.close(); }\n    let result = await nativeReadObservationReceipt(directory, request_id);\n    while (result.pending) {\n      const event = await Promise.race([changed, deadline]);\n      result = await nativeReadObservationReceipt(directory, request_id);\n      if (event.done) break;\n      changed = next();\n    }\n    if (result.saved === true || ['not_sent','rejected'].includes(result.state)) await fs.unlink(awaiting);\n    // Deadline means the save is still unknown. Keep the browser, journal and\n    // original request; read this receipt later, never send the business again.\n    return result;\n  } finally { clearTimeout(timer); abort.abort(); await events.return(); }\n}\n"

NATIVE_HANDOFF_TEMPLATE = '// Runs inside functions.exec, with callNative supplied by the current client.\n// The only desktop mutation is the existing send_message_to_thread tool.\nfunction nativeHandoffEvents(result, action) {\n  return result.handoff_route === \'direct_successors\'\n    ? [...(result.continuations || []), ...(result.handoff?.delivery_required ? [result.handoff] : [])]\n    : action === \'dispatch\'\n    ? (result.continuations || (result.continuation ? [result.continuation] : []))\n    : (result.handoff ? [result.handoff] : []);\n}\nfunction nativeHandoffBinding(event) {\n  return JSON.stringify([event?.task_id,event?.node_id,event?.task_revision,event?.node_revision,\n    event?.coordinator_ref,event?.claim_arguments?.holder_id,event?.claim_arguments?.dispatch_id,\n    event?.claim_arguments?.executor_ref]);\n}\nfunction nativeHandoffResult(result, action, failures = result.handoff_failures || []) {\n  const source = result.handoff;\n  const receipts = [source,...(result.continuations || (result.continuation ? [result.continuation] : []))].filter(Boolean);\n  for (const failure of failures) {\n    if (failure.resolved || !source || source.id !== failure.event_id ||\n        nativeHandoffBinding(source) !== failure.source_binding) continue;\n    const notice = receipts.find(item => item.id === failure.notice_id &&\n      nativeHandoffBinding(item) === failure.target_binding);\n    // An invalidated original source also invalidates its omitted notices.\n    // A different event or binding can never settle this attempt\'s history.\n    const evidence = source.delivery_state === \'obsolete\' ? source : notice;\n    if (evidence && ([\'received\',\'obsolete\'].includes(evidence.delivery_state) || evidence.claim_received_at)) {\n      failure.resolved = true;\n      failure.resolution = {event_id:source.id,notice_id:evidence.id,\n        delivery_state:evidence.delivery_state,claim_received_at:evidence.claim_received_at};\n    }\n  }\n  const pending = Boolean(result.handoff_error) || failures.some(item => !item.resolved) || nativeHandoffEvents(result, action).some(item =>\n    [\'pending\',\'sending\',\'unknown\',\'blocked\',\'unbound\'].includes(item.delivery_state));\n  return {...result, ...(failures.length ? {handoff_failures:failures} : {}),\n    needs_handoff:pending,handoff_complete:!pending};\n}\nasync function completeNativeHandoff(callNative, initialArguments, sendMessage, initialResult) {\n  const timing = [];\n  const measured = async (stage, call) => {\n    const item = {stage, started_at: new Date().toISOString()};\n    timing.push(item);\n    try {\n      const result = await call();\n      if (result?.server_processing_timing) item.server_processing_timing = result.server_processing_timing;\n      if (result?.client_wait) item.client_wait = result.client_wait;\n      return result;\n    }\n    finally { item.finished_at = new Date().toISOString(); }\n  };\n  const measuredCall = args => measured(args.arguments?.handoff_delivery ? \'delivery_\' + args.arguments.handoff_delivery.state :\n    args.arguments?.handoff_ack ? \'coordinator_ack\' : args.record_action === \'publish\' ? \'publication_after_handoff\' : \'release_publish\',\n    () => callNative(args));\n  const measuredSend = typeof sendMessage === \'function\' ? args => measured(\'desktop_send\', () => sendMessage(args)) : sendMessage;\n  const publicationBinding = initialArguments.arguments?.publication_binding;\n  const defer = !initialResult && initialArguments.action === \'finish\' && initialArguments.arguments?.publish_saved === true\n    && publicationBinding?.project_id && publicationBinding?.execution_id && Number.isInteger(publicationBinding?.revision);\n  const releaseArguments = defer ? {...initialArguments, arguments: {...initialArguments.arguments,\n    publish_saved: false, report_pending: true}} : initialArguments;\n  let result = await completeNativeHandoffSteps(measuredCall, releaseArguments, measuredSend, initialResult);\n  // Account return and actual successor delivery complete before report work.\n  // Use the existing released-holder record endpoint; no new claim or protocol.\n  if (defer && result.released === true) {\n    let published;\n    try {\n      published = await measuredCall({action: \'record\', record_action: \'publish\',\n        ...Object.fromEntries([\'holder_id\',\'task_id\',\'node_id\',\'lease_id\',\'dispatch_id\',\'executor_ref\']\n          .filter(key => key in initialArguments).map(key => [key, initialArguments[key]])),\n        arguments: publicationBinding});\n      result = {...result, ...published};\n    } catch (_) {\n      result = {...result, publication: {phase: \'unknown\', pending: true,\n        message: \'账号已交还，后继通知按原回执保留；报告发布未确认，沿原绑定核对，不重跑业务。\'}};\n    }\n    if (published?.handoff || published?.continuations) {\n      try {\n        const final = await completeNativeHandoffSteps(measuredCall, releaseArguments, measuredSend, published);\n        const failures = [...(result.handoff_failures || []),...(final.handoff_failures || [])];\n        result = {...result, ...final, ...(failures.length ? {handoff_failures:failures} : {})};\n      } catch (_) {\n        // Publication is already confirmed. A later delivery failure cannot\n        // turn it into a failed report or justify another publication.\n        result = {...result, needs_handoff: true, handoff_error: \'post_publication_delivery_unconfirmed\'};\n      }\n    }\n  }\n  result = nativeHandoffResult(result, initialArguments.action);\n  if (initialArguments.action === \'finish\') {\n    const compact = event => event && Object.fromEntries(\n      [\'id\',\'task_id\',\'node_id\',\'source_event_id\',\'kind\',\'delivery_state\',\'delivery_required\',\n       \'sent_at\',\'received_at\',\'claim_received_at\',\'claimed_at\',\'failure_stage\'].filter(key => key in event).map(key => [key,event[key]]));\n    result = {...result, handoff: compact(result.handoff),\n      continuations: (result.continuations || []).map(compact), continuation: compact(result.continuation)};\n    delete result.coordination_plan;\n    delete result.handoff_observation;\n  }\n  return {...result, handoff_timing: timing};\n}\nasync function completeNativeHandoffSteps(callNative, initialArguments, sendMessage, initialResult) {\n  let result = initialResult ?? await callNative(initialArguments);\n  const publication = result.publication;\n  const handled = new Set(), failures = [];\n  const failure = (event, stage, state, persisted = false) => {\n    const item = {event_id: result.handoff?.id || event.source_event_id || event.id,\n      source_task_id: result.handoff?.task_id || initialArguments.task_id,\n      source_node_id: result.handoff?.node_id || initialArguments.node_id,\n      notice_id: event.id, target_task_id: event.task_id, target_node_id: event.node_id,\n      target_thread_id: event.message_arguments?.threadId || event.coordinator_ref || null,\n      source_binding:nativeHandoffBinding(result.handoff),target_binding:nativeHandoffBinding(event),\n      failure_stage: stage, observed_delivery_state: state, failure_persisted: persisted};\n    failures.push(item);\n    return item;\n  };\n  const finish = () => nativeHandoffResult({...result, ...(publication ? {publication} : {})},\n    initialArguments.action, failures);\n  while (true) {\n    const direct = result.handoff_route === "direct_successors";\n    const events = nativeHandoffEvents(result, initialArguments.action);\n    const event = events.find(item => item.delivery_state === "pending" && !handled.has(item.id));\n    if (!event) return finish();\n    handled.add(event.id);\n    const attempt = event.id + ":desktop-exec-v1";\n    const notificationArguments = {...(initialArguments.arguments || {})};\n    for (const key of [\'modules\',\'continuation_group\',\'final_report\',\'publish_saved\',\'publication_binding\',\n      \'save_unconfirmed\',\'report_pending\']) delete notificationArguments[key];\n    const update = (state, failure_stage) => ({...initialArguments, arguments: {\n      ...notificationArguments, handoff_delivery: {event_id: event.id,\n        thread_id: event.message_arguments?.threadId || event.coordinator_ref,\n        attempt_id: attempt, state, ...(failure_stage ? {failure_stage} : {})}}});\n    const preflight = event.message_tool !== "send_message_to_thread" || !event.message_arguments?.threadId\n      ? \'message_target\' : typeof sendMessage !== \'function\' ? \'message_tool\' : null;\n    if (preflight) {\n      const item = failure(event, preflight, \'blocked\');\n      try { result = await callNative(update(\'blocked\', preflight)); item.failure_persisted = true; }\n      catch (_) { item.reconciliation = \'original_event_receipt_unconfirmed\'; }\n      // The persisted worker failure makes the SAME coordinator event sendable.\n      // A missing desktop tool also prevents that send; report both facts.\n      if (direct) continue;\n      return finish();\n    }\n    let begin;\n    try { begin = await callNative(update("sending")); }\n    catch (_) {\n      const item = failure(event, \'delivery_begin\', \'unknown\');\n      // No message was sent. A lost begin may have installed the original fence.\n      // Reconcile that exact attempt once, never repeat the sending begin.\n      try { result = await callNative(update(\'unknown\', \'delivery_begin\')); item.failure_persisted = true; }\n      catch (_) { item.reconciliation = \'original_event_receipt_unconfirmed\'; }\n      if (direct) continue;\n      return finish();\n    }\n    const authorized = direct || initialArguments.action === "dispatch"\n      ? begin.send_authorized : begin.handoff?.send_authorized;\n    if (authorized !== true) {\n      result = begin;\n      if (!direct) return finish();\n      continue;\n    }\n    let state = "unknown";\n    try {\n      const sent = await sendMessage(event.message_arguments);\n      const values = [sent, sent?.structuredContent];\n      for (const item of sent?.content || []) {\n        if (item.type === "text") { try { values.push(JSON.parse(item.text)); } catch (_) {} }\n      }\n      if (sent?.isError === true || values.some(value => value && (\n        value.success === false || value.sent === false ||\n        ["blocked", "denied", "rejected", "failed", "needs_approval"].includes(value.status)))) state = "blocked";\n      else if (values.some(value => value && (value.error ||\n        ["unknown", "pending", "sending", "needs_confirmation"].includes(value.status)))) state = "unknown";\n      else if (values.some(value => value && (value.sent === true || value.success === true ||\n        (value.threadId === event.message_arguments.threadId && Object.keys(value).length === 1) ||\n        ["sent", "queued", "started", "success", "submitted"].includes(value.status)))) state = "sent";\n    } catch (_) { /* An accepted desktop message can lose its response. */ }\n    let issue = state !== \'sent\' ? failure(event, \'desktop_send\', state) : null;\n    try {\n      result = await callNative(update(state, issue?.failure_stage));\n      if (issue) issue.failure_persisted = true;\n    } catch (_) {\n      issue = issue || failure(event, \'delivery_receipt\', state);\n      // Repeating the exact result ACK cannot send or replay business. A single\n      // read/write reconciliation also exposes the coordinator fault route.\n      try {\n        result = await callNative(update(state, \'delivery_receipt\'));\n        issue.failure_persisted = true;\n        issue.resolved = state === \'sent\';\n      }\n      catch (_) { result = begin; issue.reconciliation = \'original_event_receipt_unconfirmed\'; }\n    }\n    if (state !== \'sent\' && !direct) return finish();\n  }\n}\n'

NATIVE_COORDINATOR_TEMPLATE = "// Runs only inside the original coordinator's active functions.exec call.\n// Actual desktop end receipts are persisted; no resource claims or chat restarts.\nasync function waitNativeCoordinator(callNative, waitThreads, sendMessage, config) {\n  const started = Date.now(), cursors = {...(config.cursors || {})}, snapshots = new Map();\n  const seen = new Set(config.seen_attention || []);\n  const seenRecovery = {...(config.seen_recovery || {})};\n  const observed = new Set(config.observed_turns || []);\n  let windowMs;\n  let views = [], calls = 0, waits = 0;\n  const unpack = result => {\n    if (result?.isError) return {errors: [{reason: 'desktop_wait_tool_error',\n      message:(result.content || []).filter(item => item.type === 'text').map(item => item.text).join('\\n').slice(0,1000)}]};\n    if (result?.structuredContent) return result.structuredContent;\n    for (const item of result?.content || []) if (item.type === 'text') {\n      try { return JSON.parse(item.text); } catch (_) {}\n    }\n    return result;\n  };\n  const signature = item => JSON.stringify([item.task_id,item.node_id,item.event_id,item.notice_id,\n    item.attention_reason,item.delivery_state,item.failure_stage,item.claim_received_at]);\n  const observation = () => views.flatMap(view => view.coordination_plan?.handoff_observation?.events || []);\n  const desktopEvidence = events => [...new Set(events.map(event => event.target_thread_id))]\n    .map(id => snapshots.get(id)).filter(Boolean).map(item =>\n      ({cursor:item.cursor,revision:item.revision,thread:item.thread,latestTurn:item.latestTurn}));\n  const response = (reason, extra = {}) => ({reason, role: 'coordinator',\n    task_ids:config.task_ids,\n    elapsed_seconds: (Date.now() - started) / 1000, dispatch_reads: calls, desktop_waits: waits,\n    cursors, seen_attention: [...seen], seen_recovery: {...seenRecovery}, observation: observation(),\n    observed_turns:[...observed], closeout:views.map(view => ({task_id:view.task_id,...view.closeout})),\n    active_tool_wait: false, background_monitor: false,\n    ...extra});\n  const read = async () => {\n    views = [];\n    for (const task_id of config.task_ids) {\n      calls++;\n      views.push(await callNative({action:'dispatch', task_id, holder_id:config.holder_id,\n        coordinator_ref:config.coordinator_ref, arguments:{observe:true}}));\n    }\n  };\n  try { await read(); }\n  catch (_) { return response('platform_observation_unavailable', {action:'reconcile_original_tasks_no_restart'}); }\n  config = {observation_seconds:views[0]?.coordination_plan?.handoff_observation?.observation_seconds || 120,...config};\n  config.window_seconds ??= config.observation_seconds * 10;\n  windowMs = config.window_seconds * 1000;\n  let first = true;\n  while (true) {\n    const modules = views.flatMap(view => view.modules || []);\n    const events = observation();\n    const controls = views.flatMap(view => view.coordination_plan?.worker_actions || []);\n    const issues = views.flatMap(view => view.coordination_plan?.coordinator_only || []).filter(item =>\n      ['model_unavailable','blocked','isolated','retained','waiting_human','stopping'].includes(item.state));\n    const freshIssues = [...controls,...issues].filter(item => !seen.has(JSON.stringify(item)));\n    if (freshIssues.length) {\n      freshIssues.forEach(item => seen.add(JSON.stringify(item)));\n      return response('original_task_attention', {attention:freshIssues,\n        action:'handle_original_control_or_blocker_only_keep_other_workers_running'});\n    }\n    // Saved condition changes wake this existing finite wait; no automatic\n    // resend, case verdict rewrite or background recovery is started here.\n    const recoveryAttention = [], pendingRecovery = [];\n    for (const view of views) {\n      if (view.intent !== 'run' || view.closeout?.disposition === 'ended') continue;\n      for (const recovery of view.coordination_plan?.case_recovery || []) {\n        if (recovery.pending_refs?.length) pendingRecovery.push({task_id:view.task_id,...recovery});\n        for (const ref of recovery.pending_refs || []) {\n          if (!ref.condition_signature) continue;\n          const key = JSON.stringify([view.task_id,recovery.node_id,recovery.execution_id,\n            recovery.dispatch_id,recovery.executor_ref,\n            ref.case_id,ref.checkpoint_id || null]);\n          const previous = seenRecovery[key];\n          const available = (ref.conditions || []).filter(condition =>\n            ['ready','resolved','passed','confirmed'].includes(condition.status) ||\n            ['supplied_input','rule_update'].includes(condition.kind))\n            .map(condition => condition.fact_signature || JSON.stringify(condition));\n          seenRecovery[key] = {condition_signature:ref.condition_signature,available_conditions:available,\n            ready_for_review:ref.ready_for_review};\n          const newFacts = previous && available.some(fact => !(previous.available_conditions || []).includes(fact));\n          if (newFacts || (ref.ready_for_review && !previous?.ready_for_review))\n            recoveryAttention.push({task_id:view.task_id,node_id:recovery.node_id,\n              execution_id:recovery.execution_id,source_revision:recovery.source_revision,\n              executor_ref:recovery.executor_ref,dispatch_id:recovery.dispatch_id,...ref,\n              attention_reason:previous ? 'original_condition_changed' : 'original_remaining_review'});\n        }\n      }\n    }\n    if (recoveryAttention.length) return response('case_recovery_attention', {\n      attention:recoveryAttention,\n      action:'review_original_remaining_conditions_then_resume_original_executor'});\n    // A report-completed module can still contain original unfinished points.\n    // Review their changed conditions before treating all modules as settled.\n    if (!pendingRecovery.length && views.every(view => view.intent !== 'run' || view.closeout?.disposition === 'ended' ||\n      (view.modules || []).every(module => ['completed','blocked','stopped'].includes(module.state) && !module.has_lease)))\n      return response('original_tasks_ended_or_stopped', {action:'verify_original_exit_and_reports',\n        tasks:views.map(view => ({task_id:view.task_id,intent:view.intent,modules:view.modules}))});\n    const attention = events.filter(event => event.attention_reason && !seen.has(signature(event)));\n    if (attention.length && (!first || attention.some(event =>\n        ['pending_delivery','coordinator_event_pending'].includes(event.phase)))) {\n      // Consume only genuinely pending original events. The existing ACK chain\n      // rechecks bindings/resources and fences every real desktop send.\n      const pending = attention.filter(event => event.current_binding &&\n        ['pending_delivery','coordinator_event_pending'].includes(event.phase));\n      const consumed = new Set(), receipts = [];\n      for (const event of pending) {\n        const key = event.task_id + ':' + event.event_id;\n        if (consumed.has(key)) continue;\n        consumed.add(key);\n        try {\n          const receipt = await completeNativeHandoff(callNative, {\n            action:'dispatch', holder_id:config.holder_id, coordinator_ref:config.coordinator_ref,\n            task_id:event.task_id, request_id:'coordinator-wait:' + event.event_id,\n            arguments:{handoff_ack:{task_id:event.task_id,node_id:event.node_id,event_id:event.event_id}}}, sendMessage);\n          receipts.push({event_id:event.event_id, needs_handoff:receipt.needs_handoff,\n            handoff_failures:receipt.handoff_failures});\n        } catch (_) { receipts.push({event_id:event.event_id, reason:'original_handoff_ack_unconfirmed'}); }\n      }\n      if (consumed.size) {\n        try { await read(); } catch (_) { return response('platform_observation_unavailable', {receipts}); }\n        const remaining = observation().filter(event => event.attention_reason && !seen.has(signature(event)));\n        if (!remaining.length && receipts.every(receipt => !receipt.needs_handoff && !receipt.reason)) continue;\n        if (first && remaining.length && remaining.every(event =>\n            !['pending_delivery','coordinator_event_pending'].includes(event.phase))) continue;\n      }\n      const current = observation().filter(event => event.attention_reason && !seen.has(signature(event)));\n      current.forEach(event => seen.add(signature(event)));\n      return response('handoff_attention', {attention:current, receipts,desktop_evidence:desktopEvidence(current),\n        action:'inspect_only_original_target_evidence_no_unknown_resend'});\n    }\n    if (Date.now() - started >= windowMs)\n      return response(pendingRecovery.length ? 'continue_waiting_for_original_conditions' : 'observation_window_ended', {unchanged:true,\n        pending_recovery:pendingRecovery,\n        continuation:{...config,cursors,seen_attention:[...seen],seen_recovery:{...seenRecovery},observed_turns:[...observed]},\n        instruction:'本次工具内等待已结束；正常无变化不代表失败。若继续观察须保持原协调回合并重新等待；回合退出后不会后台执行。'});\n    if (typeof waitThreads !== 'function') return response('desktop_wait_tool_unavailable');\n    const targets = [];\n    for (const module of modules) {\n      const binding = module.binding || {}, ref = (binding.executor_ref || '').replace(/^thread:/, '');\n      const awaitingCondition = pendingRecovery.some(item => item.node_id === module.id && item.task_id === module.task_id);\n      if (!ref || ref === config.coordinator_ref.replace(/^thread:/,'') ||\n          (['completed','stopped','blocked'].includes(module.state) && !awaitingCondition)) continue;\n      const target = (config.targets || []).find(item => item.threadId === ref) || {threadId:ref};\n      if (!targets.some(item => item.threadId === ref && item.hostId === target.hostId))\n        targets.push({...target, ...(cursors[ref] ? {afterCursor:cursors[ref]} : {})});\n    }\n    if (!targets.length) return response(pendingRecovery.length ? 'continue_waiting_for_original_conditions' : 'no_bound_desktop_targets', {\n      pending_recovery:pendingRecovery,\n      continuation:{...config,cursors,seen_attention:[...seen],seen_recovery:{...seenRecovery},observed_turns:[...observed]},\n      action:'retain_original_coordinator_and_conditions_no_restart',\n      instruction:'没有可等待的原桌面目标时保留原条件，等待真实新事实；不结束为已全部处理，不紧循环重试或另建监听。'});\n    // More than eight is a batching concern, never a module concurrency cap.\n    const groups = [];\n    for (let index=0; index<targets.length; index+=8) groups.push(targets.slice(index,index+8));\n    for (const group of groups) {\n      const timeoutMs = first ? 0 : Math.max(0, Math.min(50000,\n        config.observation_seconds * 1000 / groups.length, windowMs - (Date.now() - started)));\n      let result;\n      const waitStarted = Date.now();\n      try { waits++; result = unpack(await waitThreads({targets:group,timeoutMs})); }\n      catch (_) { return response('desktop_host_unreachable', {targets:group,action:'preserve_original_binding'}); }\n      if (!result || typeof result !== 'object') return response('desktop_wait_receipt_unrecognized');\n      if (result.interrupted || result.reason === 'user_input' || result.status === 'interrupted' || result.userInput ||\n          (result.message === 'Wait interrupted by new input.' && result.timedOut === false && !result.errors) ||\n          /user.?input|interrupt/i.test(result.wake?.reason || ''))\n        return response('user_input', {action:'apply_latest_user_instruction_before_any_continuation'});\n      if (result.errors && Object.keys(result.errors).length) return response('desktop_target_errors', {errors:result.errors,\n        action:'inspect_original_host_or_target_no_restart'});\n      const updates = result.polls;\n      if (!Array.isArray(updates)) return response('desktop_wait_receipt_unrecognized',\n        {receipt:result,action:'inspect_public_wait_receipt_no_state_inference'});\n      for (const item of updates) {\n        const id = item.thread?.id;\n        if (!group.some(target => target.threadId === id)) continue;\n        if (item.cursor) cursors[id] = item.cursor;\n        snapshots.set(id,item);\n      }\n      try { await read(); }\n      catch (_) { return response('platform_observation_unavailable'); }\n      const issues = [];\n      for (const item of snapshots.values()) {\n        const id = item.thread?.id, status = item.latestTurn?.status;\n        const module = views.flatMap(view => view.modules || []).find(value =>\n          (value.binding?.executor_ref || '').replace(/^thread:/,'') === id &&\n          !['completed','blocked','stopped'].includes(value.state));\n        if (!module || ['completed','blocked','stopped'].includes(module.state)) continue;\n        const unclaimed = observation().filter(event => event.target_thread_id === id && event.current_binding &&\n          ['sent_awaiting_claim','sending_unconfirmed','unknown','pending_delivery'].includes(event.phase));\n        const endedValue = item.latestTurn?.completedAt;\n        // Public desktop timestamps are epoch seconds; durationMs is separate.\n        const ended = typeof endedValue === 'number' ? endedValue * 1000 :\n          typeof endedValue === 'string' ? Date.parse(endedValue) : NaN;\n        const afterSend = unclaimed.some(event => Number.isFinite(ended) &&\n          ended >= (event.delivery_started_at || event.created_at) * 1000);\n        const bindingAt = Math.max(module.binding?.created_at || 0, module.binding?.received_at || 0,\n          module.binding?.last_seen_at || 0) * 1000;\n        const currentTurn = bindingAt > 0 && Number.isFinite(ended) && ended >= bindingAt;\n        const endedTurn = currentTurn && ['completed','failed','error','interrupted'].includes(status);\n        const dispatchId = module.binding?.dispatch_id || module.binding?.id;\n        const receiptKey = JSON.stringify([module.task_id,module.id,dispatchId,item.latestTurn?.id,status,ended]);\n        if (endedTurn && dispatchId && item.latestTurn?.id && !observed.has(receiptKey)) {\n          try {\n            const receipt = await callNative({action:'dispatch',task_id:module.task_id,\n              holder_id:config.holder_id,coordinator_ref:config.coordinator_ref,\n              request_id:'desktop-observed:' + module.id + ':' + dispatchId + ':' + item.latestTurn.id + ':' + status,\n              arguments:{desktop_observations:[{node_id:module.id,dispatch_id:dispatchId,\n                executor_ref:module.binding.executor_ref,turn_id:item.latestTurn.id,status,completed_at:ended/1000}]}});\n            if (!receipt?.accepted) return response('desktop_receipt_unconfirmed', {action:'reconcile_original_binding'});\n            observed.add(receiptKey);\n          } catch (_) { return response('desktop_receipt_unconfirmed', {action:'reconcile_original_binding'}); }\n        }\n        const actualError = item.latestTurn?.error && currentTurn && (!unclaimed.length || afterSend);\n        const needsAttention = item.thread?.status?.type === 'needsAttention';\n        const desktopBinding = [module.task_id,module.id,module.binding?.holder_id,\n          module.binding?.dispatch_id || module.binding?.id];\n        // Carry this state in seen_attention across calls. Once attention has\n        // cleared, the same turn may legitimately need attention again.\n        if (!needsAttention) for (const key of seen) {\n          try {\n            const previous = JSON.parse(key);\n            if (previous[0] === 'desktop' && previous[8] === true &&\n                JSON.stringify(previous.slice(1,5)) === JSON.stringify(desktopBinding)) seen.delete(key);\n          } catch (_) { /* Other saved signatures are not desktop attention. */ }\n        }\n        const desktopKey = JSON.stringify(['desktop',...desktopBinding,item.latestTurn?.id,status,item.latestTurn?.error,\n          needsAttention,unclaimed.map(event => event.notice_id),\n          needsAttention ? item.latestToolMarkerId || item.latestToolMarker?.id || null : null]);\n        if (seen.has(desktopKey)) continue;\n        if (actualError || needsAttention || (endedTurn && (module.has_lease || status !== 'completed')) ||\n            (!module.has_lease && ['completed','failed','error','interrupted'].includes(status) && afterSend)) {\n          seen.add(desktopKey);\n          issues.push({task_id:module.task_id,node_id:module.id,thread_id:id,desktop_status:status,\n            original_handoffs:unclaimed, binding:module.binding,\n            desktop_evidence:{cursor:item.cursor,revision:item.revision,thread:item.thread,latestTurn:item.latestTurn,\n              latestToolMarkerId:item.latestToolMarkerId,latestToolMarker:item.latestToolMarker},\n            reason:actualError ? 'desktop_turn_error' : needsAttention ? 'desktop_needs_attention' :\n              module.has_lease ? 'desktop_turn_ended_with_lease' : status !== 'completed' ?\n                'desktop_turn_failed_or_interrupted' : 'desktop_ended_before_actual_claim'});\n        }\n      }\n      if (issues.length) return response('desktop_attention', {attention:issues,\n        action:'reconcile_original_exit_or_error_from_actual_receipt_no_model_switch'});\n      if (result.wake?.reason && !['inactiveStatus','completed','needsAttention','timeout'].includes(result.wake.reason))\n        return response('desktop_wake', {wake:result.wake,action:'inspect_original_wake_before_continuation'});\n      if (!first && observation().some(event => event.attention_reason && !seen.has(signature(event)))) break;\n      if (Date.now() - started >= windowMs) break;\n      // Some inactive desktop statuses return immediately even with a cursor.\n      // Do not turn that into a rapid dispatch/read loop. This delay is inside\n      // this finite tool invocation, never a model wake or persistent timer.\n      if (timeoutMs && Date.now() - waitStarted < timeoutMs)\n        await new Promise(resolve => setTimeout(resolve, Math.min(timeoutMs - (Date.now() - waitStarted),\n          windowMs - (Date.now() - started))));\n    }\n    first = false;\n  }\n}\n"

# END GENERATED NATIVE HANDOFF


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ClientHTTPError(ValueError):
    def __init__(self, status, message):
        super().__init__('HTTP %s: %s' % (status, message))
        self.status = status


# These dispatcher actions only read saved platform facts. Do not infer safety
# from POST/GET, a get_ prefix, a manifest annotation, or a nested action name.
# In particular direct_session and all other compound lifecycle tools stay out.
# workflow_status/context/document/workspace/list_sessions call deeper workflow
# projections and are deliberately not granted recovery by this transport layer.
_RECOVERABLE_READ_ACTIONS = frozenset({
    'managed_status', 'managed_report', 'requirement_design', 'test_capabilities',
    'test_experiment', 'test_attachment', 'ui_retest_inputs', 'ui_retest_file',
    'job', 'ui_read',
})
_REQUEST_BUDGET_SECONDS = 30
_TRANSIENT_HTTP_STATUSES = frozenset({429, 502, 503, 504})
_TRANSIENT_NETWORK_ERRNOS = frozenset({
    errno.ECONNRESET, errno.ECONNREFUSED, errno.ECONNABORTED, errno.ETIMEDOUT,
    errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ENETDOWN, errno.EPIPE,
})


def _recoverable_platform_read(path, data):
    if path == '/static/agent-tools.json' and data is None:
        return True
    return (path == '/api/mcp/call' and isinstance(data, dict)
            and data.get('action') in _RECOVERABLE_READ_ACTIONS
            and isinstance(data.get('arguments'), dict))


def _transient_network_error(error):
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, ssl.SSLError):
        return False
    if isinstance(reason, socket.gaierror):
        return reason.errno == socket.EAI_AGAIN
    return (isinstance(reason, (TimeoutError, ConnectionError, http.client.IncompleteRead))
            or isinstance(reason, OSError) and reason.errno in _TRANSIENT_NETWORK_ERRNOS)


def _retry_after_seconds(value):
    if not value:
        return None
    try:
        if value.strip().isdigit():
            return float(value)
        stamp = parsedate_to_datetime(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return max(0.0, (stamp - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def _response_json_with_deadline(response, deadline):
    """Keep body reads inside the same request budget, including slow streams."""
    chunks = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('platform response budget exhausted')
        # HTTPError wraps HTTPResponse; ordinary responses expose fp directly.
        stream = response
        while getattr(stream, 'fp', None) is not None:
            stream = stream.fp
        transport = getattr(getattr(stream, 'raw', None), '_sock', None)
        if transport is not None:
            transport.settimeout(remaining)
        chunk = response.read1(65536)
        if not chunk:
            pending = getattr(response, 'length', None)
            if isinstance(pending, int) and pending > 0:
                raise http.client.IncompleteRead(b'', pending)
            break
        chunks.append(chunk)
    if time.monotonic() >= deadline:
        raise TimeoutError('platform response budget exhausted')
    return json.loads(b''.join(chunks))


def read_utf8(path):
    if str(path) == '-':
        stream = getattr(sys.stdin, 'buffer', None)
        return stream.read().decode('utf-8-sig') if stream else sys.stdin.read()
    return Path(path).read_text(encoding='utf-8-sig')


def write_private_json(destination, value):
    destination = Path(destination).absolute()
    if destination.is_symlink() or destination.parent.is_symlink():
        raise ValueError('结果文件位置不能是符号链接')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.test-input-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            os.chmod(temporary, 0o600)
            json.dump(value, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def prepare_round_files(destination, result, arguments):
    """Materialize the returned baseline once; no more API reads or model scripts."""
    prepared = result['prepared_execution']
    identity = hashlib.sha256(str(prepared['execution_id']).encode()).hexdigest()[:12]
    root = destination.parent / (destination.stem + '.round-' + identity)
    if root.is_symlink():
        raise ValueError('本轮工作目录不能为符号链接')
    root.mkdir(mode=0o700, exist_ok=True)
    claim = result.get('claim') or {}
    context = {'holder_id': arguments.get('holder_id', ''),
               'task_id': (result.get('execution') or {}).get('task_id', '')}
    context.update({k: claim[k] for k in ('lease_id', 'node_id') if claim.get(k)})
    values = {'design.json': prepared,
              'results.json': prepared.get('result_template', {'cases': [], 'evidence_refs': []}),
              'browser.json': context}
    for name, value in values.items():
        path = root / name
        if path.is_symlink():
            raise ValueError('本轮文件不能为符号链接')
        # A repeated startup receipt must never overwrite observations in progress.
        if not path.exists():
            write_private_json(path, value)
    return {**{name: str(root / name) for name in values},
            'project_id': result['project_id'], 'execution_id': prepared['execution_id'],
            'revision': prepared['revision'],
            'notice': '原设计已保存；只填写实际结果和原回执引用。重复启动回执不覆盖文件。排队仍按原 resume_arguments 续接。'}


def check_case_batch(cases):
    if not isinstance(cases, list):
        raise ValueError('cases 必须是 JSON 列表')
    seen = {}
    for position, case in enumerate(cases, 1):
        if not isinstance(case, dict) or not isinstance(case.get('case_id'), str) or not case['case_id'].strip():
            raise ValueError('第 %s 项缺少文本 case_id；不自动生成编号或补写结果' % position)
        case_id = case['case_id'].strip()
        if case_id in seen:
            raise ValueError('同批 case_id 重复：%s（第 %s、%s 项）；请核对真实结果后只提交一次，不自动取最后一项' %
                             (case_id, seen[case_id], position))
        seen[case_id] = position


def check_file_manifest(entries, cases=None):
    """Local preflight only: do not encode, upload, invent references or results."""
    if not isinstance(entries, list) or not entries:
        raise ValueError('manifest 必须是非空 JSON 列表')
    by_id = None
    if cases is not None:
        check_case_batch(cases)
        by_id = {case['case_id'].strip(): case for case in cases}
    issues = []
    total_bytes = 0
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) and entry[k].strip()
                                                for k in ('file', 'case_id', 'step')):
            issues.append({'item': index, 'code': 'missing_file_case_or_step'})
            continue
        file = Path(entry['file']).expanduser()
        try:
            with file.open('rb') as stream:
                total_bytes += os.fstat(stream.fileno()).st_size
                stream.read(1)
        except OSError:
            issues.append({'item': index, 'code': 'file_not_readable'})
        kind = entry.get('kind', 'screenshot')
        if kind not in {'screenshot', 'video', 'fixture', 'observation'}:
            issues.append({'item': index, 'code': 'invalid_kind'})
        if by_id is not None:
            case = by_id.get(entry['case_id'].strip())
            if case is None:
                issues.append({'item': index, 'code': 'unknown_case_id'})
    return {'valid': not issues, 'files': len(entries), 'bytes': total_bytes,
            'case_references_checked': by_id is not None, 'issues': issues}


def screenshot_metadata(asset):
    """Describe the original bytes accurately; never convert or edit evidence."""
    if not isinstance(asset, dict) or asset.get('kind', 'screenshot') != 'screenshot':
        return asset
    encoded = asset.get('content_base64')
    filename = asset.get('filename')
    if not isinstance(encoded, str) or not isinstance(filename, str) or not filename:
        return asset
    try:
        # Only sniff the header. Full content, size and association validation
        # remains on the server, including invalid Base64 after this prefix.
        header = base64.b64decode(encoded[:24], validate=True)
    except ValueError:
        return asset
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        content_type, suffixes = 'image/png', ('.png',)
    elif header.startswith(b'\xff\xd8\xff'):
        content_type, suffixes = 'image/jpeg', ('.jpg', '.jpeg')
    elif header.startswith(b'RIFF') and header[8:12] == b'WEBP':
        content_type, suffixes = 'image/webp', ('.webp',)
    else:
        return asset
    # Do not turn an invalid path into a valid basename. Server validation
    # still rejects directory separators, NUL and other invalid metadata.
    if not any(char in filename for char in ('/', '\\', '\x00')) and filename not in {'.', '..'}:
        path = Path(filename)
        if path.suffix.lower() not in suffixes:
            filename = str(path.with_suffix(suffixes[0]))
    return {**asset, 'filename': filename, 'content_type': content_type}


def summarize_ui_finalization(result, receipt_file):
    """Display returned facts once; keep the full, unchanged result in its receipt."""
    summary = {
        'receipt_file': str(Path(receipt_file).absolute()),
        'notice': '仅整理已返回的收尾信息，不作质量判定，不能替代覆盖、证据或资源审查；完整结果仍在回执。',
    }
    prominent_sources = {}
    details = []
    grouped = {}

    def add(field, value, source, prominent=False):
        # JSON identity keeps false/0, null/empty and different future fields distinct.
        identity = (field, json.dumps(value, ensure_ascii=False, sort_keys=True))
        if identity in grouped:
            grouped[identity].append(source)
            return
        sources = [source]
        grouped[identity] = sources
        if prominent:
            summary[field] = value
            prominent_sources[field] = sources
        else:
            details.append({'field': field, 'sources': sources, 'value': value})

    for field, value in result.items():
        if field not in ('save_result', 'publication'):
            add(field, value, field, field in ('execution_id', 'revision'))
    for container in ('publication', 'save_result'):
        if container not in result:
            continue
        node = result[container]
        if not isinstance(node, dict):
            add(container, node, container)
            continue
        for field, value in node.items():
            add(field, value, container + '.' + field,
                container == 'publication' and field in ('report', 'total_report', 'summary'))
    summary.update(sources=prominent_sources, details=details)
    return summary


class Client:
    def __init__(self, url, credential_file=None):
        self.url = url.rstrip('/')
        parsed = urllib.parse.urlsplit(self.url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError('测试台地址必须是 HTTP(S) origin，例如 http://192.0.2.20:18089')
        digest = hashlib.sha256(self.url.encode()).hexdigest()[:16]
        self.path = Path(credential_file) if credential_file else Path.home()/'.local/state/api-test-mcp'/(digest+'.json')
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.manifest = None
        self.last_request_recovery = None
        # Session-only cache; never persist evidence or share it across clients.
        self._encoded_files = OrderedDict()
        self._encoded_file_bytes = 0

    def load_manifest(self, path):
        """Use the explicitly supplied manifest for this downloaded client."""
        manifest = json.loads(read_utf8(path))
        expected = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if not isinstance(manifest, dict) or manifest.get('client_sha256') != expected:
            raise ValueError('manifest-file 与本客户端不匹配；使用本次从同一测试台下载的客户端和完整工具清单')
        tools, actions = manifest.get('tools'), manifest.get('actions')
        if not isinstance(tools, list) or not isinstance(actions, dict):
            raise ValueError('manifest-file 缺少完整 tools/actions')
        names = []
        for tool in tools:
            if (not isinstance(tool, dict) or not isinstance(tool.get('name'), str)
                    or not isinstance(tool.get('inputSchema'), dict)
                    or not isinstance(tool['inputSchema'].get('properties'), dict)):
                raise ValueError('manifest-file 工具格式无效')
            names.append(tool['name'])
        if len(set(names)) != len(names) or set(names) != set(actions) or any(
                not isinstance(action, str) or not action for action in actions.values()):
            raise ValueError('manifest-file 工具与 action 不一致')
        self.manifest = manifest

    def native_record(self, binding_file, payload, receipt_file, *, final_review=False):
        """Save actual changes once under the original binding; never control a browser."""
        started, started_at = time.monotonic(), datetime.now(timezone.utc).isoformat()
        binding_file, receipt_file = Path(binding_file).absolute(), Path(receipt_file).absolute()
        if binding_file.resolve() == receipt_file.resolve() or any(path.is_symlink() or path.parent.is_symlink()
                                               for path in (binding_file, receipt_file)):
            raise ValueError('绑定与回执须为不同的普通文件，不能使用符号链接')
        allowed = {'cases', 'coverage', 'review_notes', 'scene_outcome', 'experiment', 'asset_files', 'assets', 'project_id', 'execution_id', 'revision', 'response'}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise ValueError('native-record 接受 cases 变化、coverage/review_notes/scene_outcome/experiment 与 asset_files；身份和修订沿用 binding-file')
        require_ui_payload_shape(payload)
        cases = payload.get('cases', [])
        check_case_batch(cases)
        final_review = final_review or len(cases) != 1 or any(key in payload for key in
            ('coverage', 'review_notes', 'scene_outcome'))
        if len(cases) > 200 or (not cases and not any(payload.get(k) is not None for k in
                ('coverage', 'review_notes', 'scene_outcome', 'experiment', 'asset_files', 'assets'))):
            raise ValueError('逐条保存结果；最终回查可只传元数据或最多 200 条变化，不截断用例')
        # Serialize writers to this original binding; do not allow two saved
        # cases to consume the same local revision or overwrite each other's ACK.
        with batch_lock(binding_file):
            binding = json.loads(read_utf8(binding_file))
            fields = ('holder_id', 'task_id', 'node_id', 'lease_id', 'project_id', 'execution_id')
            if (not isinstance(binding, dict) or any(not isinstance(binding.get(key), str) or not binding[key] for key in fields)
                    or type(binding.get('revision')) is not int or binding['revision'] < 1):
                raise ValueError('binding-file 需有原 holder_id/task_id/node_id/lease_id/project_id/execution_id 和已保存 revision')
            if binding.get('workspace_url', self.url) != self.url:
                raise ValueError('binding-file 不属于当前测试台')
            for key in ('project_id', 'execution_id'):
                if key in payload and payload[key] != binding[key]:
                    raise ValueError('结果的 %s 与原绑定不一致' % key)
            if payload.get('response', 'summary') != 'summary':
                raise ValueError('native-record 使用 summary 回执；完整读取仍使用原 record 入口')
            content = {key: value for key, value in payload.items()
                       if key not in {'project_id', 'execution_id', 'revision', 'response', 'asset_files'}}
            # Evidence and final changes share one POST/revision. No separate
            # upload can race this binding's observation receiver or final review.
            if 'asset_files' in payload:
                if 'assets' in payload:
                    raise ValueError('证据使用 asset_files 或已编码 assets，不能同时提供')
                entries = payload['asset_files']
                checked = check_file_manifest(entries)
                if not checked['valid'] or len(entries) > 50:
                    raise ValueError('证据批次最多 50 项，文件预检问题：' + json.dumps(checked['issues'], ensure_ascii=False))
                content['assets'] = [self.asset_from_file(**{key: entry[key] for key in (
                    'file', 'case_id', 'step', 'kind', 'captured_at', 'filename', 'content_type') if key in entry})
                    for entry in entries]
            identity = {'workspace_url': self.url,
                        'binding': {key: binding[key] for key in (*fields, 'account_id') if key in binding},
                        'payload': content}
            fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

            def summary(receipt, *, reused=False, readback=0):
                result = receipt['result']
                return {'saved': True, 'execution_id': result['execution_id'], 'revision': result['revision'],
                        'binding_revision': binding['revision'], 'receipt_file': str(receipt_file),
                        'reused_receipt': reused,
                        'result': {key: value for key, value in result.items() if key not in {'saved_cases', 'coverage'}},
                        'client_timing': {**receipt['client_timing'],
                                          'http_calls': readback or (0 if reused else receipt['client_timing']['http_calls'])}}

            def update_binding(receipt):
                before, after = receipt['revision_before'], receipt['result']['revision']
                if binding['revision'] < before:
                    raise ValueError('本地绑定早于已保存回执；先核对原轮修订，不回退或覆盖绑定')
                if binding['revision'] == before or (receipt.get('confirmation_source') == 'platform_record_readback'
                                                    and binding['revision'] == after):
                    binding['revision'] = after
                    if receipt['result'].get('execution_plan'):
                        binding['execution_plan'] = receipt['result']['execution_plan']
                    counts = receipt['result'].get('execution_plan', {}).get('execution_summary', {}).get('status_counts')
                    if isinstance(counts, dict):
                        binding['case_counts'] = counts
                    known = binding.setdefault('case_results', {})
                    for case in receipt.get('payload', {}).get('cases', []):
                        known[case['case_id']] = {**known.get(case['case_id'], {}), **case}
                    for case in receipt['result'].get('saved_cases', []):
                        known[case['case_id']] = case
                    if 'coverage' in receipt['result']:
                        binding['coverage'] = receipt['result']['coverage']
                    if 'coverage_check' in receipt['result']:
                        binding['coverage_check'] = receipt['result']['coverage_check']
                    # A case correction invalidates any earlier complete-scope claim.
                    binding.pop('coverage_complete', None)
                    if (binding.get('final_review') or {}).get('fingerprint') == fingerprint:
                        binding['final_review']['state'] = 'saved'
                    remember_native_observation_corrections(binding_file, binding, receipt_file, receipt)
                    design_file = binding_file.parent / 'design.json'
                    if design_file.exists():
                        design = json.loads(read_utf8(design_file))
                        designs = {case['case_id']: case for case in design.get('cases', [])}
                        for cid, case in known.items():
                            designs[cid] = {**designs.get(cid, {}), **case}
                        binding['case_results'] = designs
                        write_private_json(design_file, {**design, 'cases': list(designs.values()),
                            'coverage': binding.get('coverage', design.get('coverage', []))})
                    write_private_json(binding_file, binding)

            def sync_review(receipt):
                review = binding.get('final_review') or {}
                if review.get('fingerprint') == fingerprint:
                    review['state'] = receipt['state']
                    review.pop('rejection_confirmed', None)
                    if native_rejection_confirmed(receipt, binding):
                        review['rejection_confirmed'] = copy.deepcopy(receipt['rejection_confirmed'])
                    write_private_json(binding_file, binding)

            def rejected_summary(receipt, *, readback=0):
                sync_review(receipt)
                return {'saved': False, 'state': 'rejected', 'receipt_file': str(receipt_file),
                        'rejection_confirmed': receipt['rejection_confirmed'],
                        'execution_id': binding['execution_id'], 'revision': binding['revision'],
                        'client_timing': {'http_calls': readback}}

            def reconcile_receipt(receipt):
                # A status code may come from reporting after cases.json has
                # committed. Read once under the original binding; never POST again.
                original_state = receipt['state']
                receipt.update(state='unknown', pending=True)
                receipt.pop('rejection_confirmed', None)
                write_private_json(receipt_file, receipt)
                sync_review(receipt)
                try:
                    if binding['revision'] not in {receipt['revision_before'], receipt['revision_before'] + 1}:
                        raise ValueError('本地修订与原未知保存不一致；先核对原记录，不覆盖后续修订')
                    request = {key: binding[key] for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'account_id', 'dispatch_id', 'executor_ref') if key in binding}
                    readback_calls = 1 + int(self.manifest is None)
                    record = self.call('direct_test_session', {**request, 'action': 'record', 'record_action': 'record',
                        'arguments': {'project_id': binding['project_id'], 'execution_id': binding['execution_id']}})
                    if (isinstance(record, dict) and record.get('id') == binding['execution_id']
                            and type(record.get('revision')) is int and record['revision'] == receipt['revision_before']
                            and type(receipt.get('http_status')) is int and 400 <= receipt['http_status'] < 500):
                        receipt.update(state='rejected', pending=False, rejection_confirmed={
                            'source': 'platform_record_readback', 'execution_id': record['id'],
                            'revision': record['revision'], 'fingerprint': fingerprint,
                            'checked_at': datetime.now(timezone.utc).isoformat()})
                        write_private_json(receipt_file, receipt)
                        return rejected_summary(receipt, readback=readback_calls)
                    confirmed = native_save_readback(receipt, record,
                        binding.get('case_results', {}) if binding['revision'] == receipt['revision_before'] else {})
                    receipt.update(original_transport_state=original_state, state='saved', pending=False,
                                   result=confirmed, confirmation_source='platform_record_readback',
                                   reconciled_at=datetime.now(timezone.utc).isoformat())
                    receipt.setdefault('client_timing', {'started_at': receipt.get('started_at'), 'http_calls': 1})
                    write_private_json(receipt_file, receipt)
                    update_binding(receipt)
                    return summary(receipt, reused=True, readback=readback_calls)
                except (ValueError, OSError) as error:
                    receipt.update(state='unknown', pending=True, readback_error=str(error))
                    write_private_json(receipt_file, receipt)
                    sync_review(receipt)
                    raise

            if receipt_file.exists():
                receipt = json.loads(read_utf8(receipt_file))
                if not isinstance(receipt, dict) or receipt.get('fingerprint') != fingerprint:
                    raise ValueError('回执属于其他绑定或结果；保留原回执，不覆盖或重复提交')
                if receipt.get('state') == 'saved' and isinstance(receipt.get('result'), dict):
                    before = receipt.get('revision_before')
                    if (type(before) is not int or receipt['result'].get('revision') != before + 1
                            or receipt['result'].get('execution_id') != binding['execution_id']):
                        raise ValueError('原保存成功回执的执行 ID 或精确修订不一致；保留回执，不重发')
                    update_binding(receipt)
                    return summary(receipt, reused=True)
                if native_rejection_confirmed(receipt, binding):
                    return rejected_summary(receipt)
                if receipt.get('state') in {'pending', 'unknown', 'rejected'}:
                    return reconcile_receipt(receipt)
                raise ValueError('原保存回执 state=%s；先核对平台原记录是否已保存。明确未保存后，修正原因及绑定修订并用新回执补交已有观察，不重放浏览器动作。' % receipt.get('state'))
            if 'revision' in payload and payload['revision'] != binding['revision']:
                raise ValueError('结果 revision 与当前原绑定不一致；先核对已保存回执')
            manifest_calls = int(self.manifest is None)
            manifest = self.tools()
            tool = next((item for item in manifest.get('tools', []) if item.get('name') == 'direct_test_session'), None)
            if (not tool or manifest.get('actions', {}).get('direct_test_session') != 'direct_session'
                    or not {'action', 'holder_id', 'arguments'} <= set(tool.get('inputSchema', {}).get('properties', {}))):
                raise ValueError('本次工具清单未提供有效的 direct_test_session 记录契约')
            if not self.path.exists():
                raise ValueError('尚未连接测试台，先沿原连接入口完成连接')
            credential = json.loads(read_utf8(self.path))
            if credential.get('url') != self.url or not credential.get('token'):
                raise ValueError('现有凭据不属于此测试台或已无效')
            arguments = {key: binding[key] for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'account_id', 'dispatch_id', 'executor_ref') if key in binding}
            arguments.update(action='record', record_action='cases',
                             arguments={**content, 'project_id': binding['project_id'],
                                        'execution_id': binding['execution_id'], 'revision': binding['revision'],
                                        'response': 'summary', 'include_saved_design': True})
            if 'cases' in content:
                arguments['arguments']['cases'] = native_checkpoint_observations(content['cases'], binding.get('case_results', {}))
            receipt = {**identity, 'fingerprint': fingerprint, 'state': 'pending', 'pending': True,
                       'revision_before': binding['revision'], 'request': arguments,
                       'started_at': started_at}
            baselines = {case['case_id']: {key: copy.deepcopy(old[key]) for key in
                ('case_id', 'checkpoints', 'dependencies', 'question_ids') if key in old}
                for case in cases if (old := binding.get('case_results', {}).get(case['case_id'], {})).get('checkpoints')}
            if baselines:
                receipt['case_baselines'] = baselines
            write_private_json(receipt_file, receipt)
            if final_review:
                binding['final_review'] = {'state': 'pending', 'fingerprint': fingerprint, 'receipt_file': str(receipt_file)}
                write_private_json(binding_file, binding)
            try:
                result = self.call('direct_test_session', arguments)
                if (not isinstance(result, dict) or result.get('execution_id') != binding['execution_id']
                        or type(result.get('revision')) is not int or result['revision'] != binding['revision'] + 1):
                    raise ValueError('保存响应未确认原执行 ID 与下一修订，先核对平台记录')
            except (ValueError, OSError) as error:
                # HTTP errors can occur after persistence. Only an original
                # record readback can prove a 4xx did not advance the revision.
                rejected = isinstance(error, ClientHTTPError) and 400 <= error.status < 500
                receipt.update(state='unknown', error_type=type(error).__name__,
                               error=str(error),
                               client_timing={'started_at': started_at,
                                              'finished_at': datetime.now(timezone.utc).isoformat(),
                                              'elapsed_seconds': round(time.monotonic() - started, 3),
                                              'http_calls': 1 + manifest_calls})
                if isinstance(error, ClientHTTPError):
                    receipt['http_status'] = error.status
                write_private_json(receipt_file, receipt)
                if final_review:
                    binding['final_review']['state'] = receipt['state']
                    write_private_json(binding_file, binding)
                if rejected:
                    try:
                        recovered = reconcile_receipt(receipt)
                    except (ValueError, OSError):
                        pass  # Keep the original HTTP error and unknown write.
                    else:
                        if recovered.get('saved') is True:
                            recovered['client_timing']['http_calls'] += 1 + manifest_calls
                            return recovered
                raise
            receipt.update(state='saved', pending=False, result=result,
                           client_timing={'started_at': receipt['started_at'],
                                          'finished_at': datetime.now(timezone.utc).isoformat(),
                                          'elapsed_seconds': round(time.monotonic() - started, 3),
                                          'http_calls': 1 + manifest_calls})
            # Persist the ACK before advancing the binding. An interruption
            # between them is repaired from this same successful receipt.
            write_private_json(receipt_file, receipt)
            update_binding(receipt)
            return summary(receipt)

    def asset_from_file(self, file, *, case_id, step, kind='screenshot',
                        captured_at='', filename=None, content_type=None):
        """Build one independent association, reusing unchanged local bytes."""
        if not case_id or not step or kind not in {'screenshot', 'video', 'fixture', 'observation'}:
            raise ValueError('文件关联需要 case_id、step 和有效 kind')
        path = Path(file).expanduser()
        resolved = path.resolve()

        def identity(info):
            return (resolved, info.st_dev, info.st_ino, info.st_size,
                    info.st_mtime_ns, info.st_ctime_ns)

        key = identity(resolved.stat())
        encoded = self._encoded_files.get(key)
        if encoded is None:
            with resolved.open('rb') as source:
                if identity(os.fstat(source.fileno())) != key:
                    raise ValueError('上传文件在读取前发生变化，请重新准备')
                content = source.read()
                if identity(os.fstat(source.fileno())) != key:
                    raise ValueError('上传文件在读取中发生变化，请重新准备')
            if identity(resolved.stat()) != key:
                raise ValueError('上传文件在读取后发生变化，请重新准备')
            encoded = base64.b64encode(content).decode('ascii')
            # Bound retained Base64 to 128 MiB. Oversized evidence is still
            # sent through the existing server checks, without caching it.
            limit = 128 * 1024 * 1024
            if len(encoded) <= limit:
                for old in list(self._encoded_files):
                    if old[0] == resolved:
                        self._encoded_file_bytes -= len(self._encoded_files.pop(old))
                while self._encoded_files and self._encoded_file_bytes + len(encoded) > limit:
                    _, previous = self._encoded_files.popitem(last=False)
                    self._encoded_file_bytes -= len(previous)
                self._encoded_files[key] = encoded
                self._encoded_file_bytes += len(encoded)
        else:
            self._encoded_files.move_to_end(key)
        return screenshot_metadata({
            'case_id': case_id, 'step': step, 'kind': kind,
            'captured_at': captured_at, 'filename': filename or path.name,
            'content_type': content_type or mimetypes.guess_type(path)[0] or 'application/octet-stream',
            'content_base64': encoded,
        })

    def upload_assets_from_files(self, project_id, execution_id, entries, cases=None):
        """Upload a local manifest using the existing per-asset server checks."""
        # Validate the whole manifest before the first write, as upload-batch
        # does. Server validation/atomicity remains per batch of at most 50.
        checked = check_file_manifest(entries, cases)
        if not checked['valid']:
            raise ValueError('文件预检失败，尚未上传：' + json.dumps(checked['issues'], ensure_ascii=False))
        # Prepare all files before writing, so an unreadable/changed local
        # file cannot leave an earlier batch uploaded unexpectedly.
        assets = [self.asset_from_file(**{key: entry[key] for key in (
            'file', 'case_id', 'step', 'kind', 'captured_at', 'filename', 'content_type'
        ) if key in entry}) for entry in entries]
        totals = {'total': 0, 'created': 0, 'reused': 0}
        for start in range(0, len(entries), 50):
            result = self.call('upload_ui_test_assets', {
                'project_id': project_id, 'execution_id': execution_id, 'assets': assets[start:start + 50]})
            for key in ('total', 'created', 'reused'):
                totals[key] += result[key]
            if 'revision' in result:
                totals.update(execution_id=result['execution_id'], revision=result['revision'])
        return totals

    def finalize_ui_test_round(self, project_id, execution_id, revision, payload, receipt_file):
        """Persist explicit final observations, then publish that same round once."""
        allowed = {'cases', 'coverage', 'review_notes', 'scene_outcome', 'experiment', 'title', 'summary', 'evidence_refs'}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise ValueError('收尾 JSON 仅支持 cases、coverage、review_notes、scene_outcome、experiment、title、summary、evidence_refs')
        require_ui_payload_shape(payload)
        if not isinstance(payload.get('summary', ''), str) or not isinstance(payload.get('title', ''), str):
            raise ValueError('收尾 JSON 的 summary、title 为可选文本；省略 summary 按真实结果自动汇总')
        if not project_id or not execution_id or type(revision) is not int or revision < 1:
            raise ValueError('收尾需使用已保存的 project_id、execution_id 和 revision，不新建轮次')
        cases = payload.get('cases', [])
        check_case_batch(cases)
        if len(cases) > 200:
            raise ValueError('先按原约定保存结果批次；收尾变化用例每批最多 200 条，不截断或删减')
        if payload.get('coverage') is not None and not isinstance(payload['coverage'], list):
            raise ValueError('coverage 必须是列表或 null')
        if payload.get('review_notes') is not None and not isinstance(payload['review_notes'], str):
            raise ValueError('review_notes 必须是文本或 null')
        if payload.get('experiment') is not None and not isinstance(payload['experiment'], dict):
            raise ValueError('experiment 必须是对象或 null')
        scene = payload.get('scene_outcome')
        if scene is not None:
            if not isinstance(scene, dict) or not isinstance(scene.get('items', []), list):
                raise ValueError('scene_outcome 必须是对象，items 必须是列表')
        identity = {'workspace_url': self.url, 'project_id': project_id, 'execution_id': execution_id,
                    'revision': revision, 'payload': payload}
        fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
        receipt_file = Path(receipt_file)
        if receipt_file.is_symlink() or receipt_file.parent.is_symlink():
            raise ValueError('收尾回执位置不能是符号链接')
        if receipt_file.exists():
            receipt = json.loads(read_utf8(receipt_file))
            if not isinstance(receipt, dict):
                raise ValueError('收尾回执格式无效；先只读核对平台记录，不覆盖回执')
            if receipt.get('fingerprint') != fingerprint:
                raise ValueError('收尾回执属于不同输入；先核对原回执和平台记录，不覆盖或重复提交')
            if receipt.get('phase') == 'published' and isinstance(receipt.get('result'), dict):
                return receipt['result']
            if receipt.get('phase') == 'settling':
                current = self.call('get_workflow_status', {'project_id': project_id}).get('finalization') or {}
                if current.get('request_id') != fingerprint:
                    raise ValueError('当前结束请求已变化；保留原回执，不重复写入')
                result = {'execution_id':execution_id, 'revision':current.get('revision',revision),
                          'publication':current, 'save_result':None}
                receipt.update(phase='published' if current.get('phase') == 'published' else 'settling',result=result)
                write_private_json(receipt_file,receipt)
                return result
            raise ValueError('已有收尾回执，phase=%s、revision=%s；先只读核对平台是否已保存/发布，不重跑整段收尾。已保存时直接调用 finish_test_workflow。' %
                             (receipt.get('phase'), receipt.get('revision')))
        receipt = {'fingerprint': fingerprint, 'project_id': project_id, 'execution_id': execution_id, 'revision': revision}

        def checkpoint(phase, **fields):
            receipt.update(phase=phase, **fields)
            write_private_json(receipt_file, receipt)

        changes = {key: payload[key] for key in ('coverage', 'review_notes', 'scene_outcome', 'experiment') if payload.get(key) is not None}
        checkpoint('publish_unverified')
        # This composite request may save before report publication fails.
        # A response status alone cannot prove that no result was persisted.
        publication = self.call('finish_test_workflow', {
            'project_id': project_id, 'execution_id': execution_id,
            'revision':revision, 'cases':cases, **changes, 'request_id':fingerprint,
            'title': payload.get('title', ''), 'summary': payload.get('summary', ''), 'evidence_refs': payload.get('evidence_refs', [])})
        result = {'execution_id': execution_id, 'revision': publication.get('revision',revision),
                  'publication': publication, 'save_result': None}
        checkpoint('published' if publication.get('report') else 'settling', result=result)
        return result

    def request(self, path, data=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer '+token
        body = None if data is None else json.dumps(data, ensure_ascii=False).encode()
        req = urllib.request.Request(self.url+path, data=body, headers=headers)
        readonly = _recoverable_platform_read(path, data)
        started = time.monotonic()
        deadline = started + _REQUEST_BUDGET_SECONDS
        attempts = []
        self.last_request_recovery = None
        stop_reason = 'not_recoverable'
        last_error = ValueError('请求预算在发送前已耗尽；未发送请求。')
        def recovery_receipt(reason):
            return {'original_error': attempts[0]['error'] if attempts else {'type': 'TimeoutError', 'stage': 'before_send'},
                    'attempts': list(attempts),
                    'elapsed_seconds': round(time.monotonic() - started, 3),
                    'stop_reason': reason, 'read_only': readonly}
        # Only known credentials are redacted; arbitrary transport exception text,
        # headers, request bodies and URLs never enter the diagnostic receipt.
        secrets = [token, data.get('code') if isinstance(data, dict) else None]
        def safe_message(value):
            message = str(value)
            for secret in secrets:
                if secret:
                    message = message.replace(str(secret), '[redacted]')
            return message[:8000]
        for attempt in range(1, 4):
            retry_after = None
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    stop_reason = 'budget_exhausted'
                    break
                with self.http.open(req, timeout=remaining) as response:
                    result = _response_json_with_deadline(response, deadline)
                if attempts:
                    attempts.append({'attempt': attempt, 'elapsed_seconds': round(time.monotonic() - started, 3),
                                     'result': 'success'})
                    self.last_request_recovery = recovery_receipt('recovered')
                return result
            except urllib.error.HTTPError as error:
                retry_after = _retry_after_seconds(error.headers.get('Retry-After')) if error.headers else None
                try:
                    detail = _response_json_with_deadline(error, deadline).get('detail', '测试台请求失败')
                except (ValueError, AttributeError, OSError, http.client.HTTPException):
                    detail = '测试台请求失败'
                finally:
                    error.close()
                last_error = ClientHTTPError(error.code, safe_message(detail))
                summary = {'type': 'HTTPError', 'status': error.code, 'message': safe_message(detail)}
                transient = error.code in _TRANSIENT_HTTP_STATUSES
            except (urllib.error.URLError, TimeoutError, OSError,
                    http.client.RemoteDisconnected, http.client.IncompleteRead) as error:
                reason = error.reason if isinstance(error, urllib.error.URLError) else error
                summary = {'type': type(error).__name__, 'reason_type': type(reason).__name__}
                if isinstance(reason, OSError) and isinstance(reason.errno, int):
                    summary['errno'] = reason.errno
                last_error = ValueError('无法连接测试台。请确认此电脑能访问 '+self.url+'；写入和执行操作未自动重试。')
                transient = _transient_network_error(error)
            attempts.append({'attempt': attempt, 'elapsed_seconds': round(time.monotonic() - started, 3),
                             'error': summary})
            if time.monotonic() >= deadline:
                stop_reason = 'budget_exhausted'
                break
            if not readonly or not transient:
                stop_reason = 'not_recoverable'
                break
            if attempt == 3:
                stop_reason = 'attempts_exhausted'
                break
            delay = random.uniform(.2, .4) * (2 ** (attempt - 1))
            if retry_after is not None:
                delay = max(delay, retry_after)
            if delay >= deadline - time.monotonic():
                stop_reason = 'retry_after_exceeds_budget' if retry_after is not None else 'budget_exhausted'
                break
            time.sleep(delay)
        recovery = self.last_request_recovery = recovery_receipt(stop_reason)
        last_error.recovery = recovery
        last_error.args = (str(last_error) + ' 请求尝试摘要：' + json.dumps(recovery, ensure_ascii=False),)
        raise last_error from None

    def tools(self):
        if self.manifest is None:
            self.manifest = self.request('/static/agent-tools.json')
        return self.manifest

    def connect(self, code):
        # Check destination before redeeming a one-use code.
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ValueError('凭据位置不能是符号链接')
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        result = self.request('/api/mcp/redeem', {'code': code})
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix='.credential-')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                os.chmod(name, 0o600)
                json.dump({'url': self.url, 'token': result['token']}, output)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return {'connected': True, 'workspace_url': self.url, 'message': '已连接。按任务读取文档并推进到最终报告；不要输出凭据。',
                'usage_guide': result.get('usage_guide', {})}

    def call(self, name, arguments):
        manifest = self.tools()
        tool = next((t for t in manifest['tools'] if t['name'] == name), None)
        if tool is None or not isinstance(arguments, dict):
            raise ValueError('工具名称无效或参数不是 JSON 对象；请读取 tools')
        arguments = dict(arguments)
        if name == 'direct_test_session' and arguments.get('action') == 'coordinator_wait_script':
            command = [sys.executable, str(Path(__file__).resolve()), '--url', self.url,
                       '--credential-file', str(self.path), 'call', 'direct_test_session']
            config = {**(arguments.get('arguments') or {}),
                      'holder_id': arguments.get('holder_id'),
                      'coordinator_ref': arguments.get('coordinator_ref') or arguments.get('holder_id')}
            if arguments.get('task_id') and 'task_ids' not in config:
                config['task_ids'] = [arguments['task_id']]
            return {'capability': NATIVE_COORDINATOR_WAIT_CAPABILITY, 'executed': False,
                    'tool': 'functions.exec', 'script': native_coordinator_script(
                        NATIVE_COORDINATOR_TEMPLATE, NATIVE_HANDOFF_TEMPLATE, config, command=command)}
        if name == 'direct_test_session' and arguments.get('action') == 'handoff_script':
            command = [sys.executable, str(Path(__file__).resolve()), '--url', self.url,
                       '--credential-file', str(self.path), 'call', 'direct_test_session']
            return {'capability': NATIVE_HANDOFF_CAPABILITY, 'direct_capability': NATIVE_DIRECT_HANDOFF_CAPABILITY, 'executed': False,
                    'tool': 'functions.exec', 'script': native_handoff_script(
                        NATIVE_HANDOFF_TEMPLATE, command, arguments.get('arguments') or {})}
        if name == 'direct_test_session' and arguments.get('action') == 'claim' and not arguments.get('executor_ref'):
            if os.environ.get('CODEX_THREAD_ID'):
                arguments['executor_ref'] = 'thread:' + os.environ['CODEX_THREAD_ID']
        schema = tool['inputSchema']
        for key, prop in schema.get('properties', {}).items():
            if key not in arguments and 'default' in prop:
                arguments[key] = prop['default']
        missing = [key for key in schema.get('required', []) if key not in arguments]
        if missing:
            raise ValueError('缺少参数：'+', '.join(missing))
        if name == 'save_ui_test_cases':
            check_case_batch(arguments['cases'])
        if name == 'connect_workspace':
            return self.connect(arguments['code'])
        if not self.path.exists():
            raise ValueError('尚未连接：使用消息中的连接码执行 connect --code-file 文件路径')
        credential = json.loads(self.path.read_text(encoding='utf-8'))
        if credential.get('url') != self.url:
            raise ValueError('凭据不属于此测试台，请重新连接')
        if name == 'import_document':
            goal = arguments.pop('goal', '')
            if goal:
                arguments['task'] = {'goal': goal}
        if name == 'configure_task' and arguments.get('base_url') is None:
            arguments.pop('base_url', None)
        if name in {'publish_task_report', 'finish_test_workflow'}:
            for field in ('sections', 'findings', 'run_ids'):
                arguments[field] = arguments.get(field) or []
        if name == 'upload_ui_test_asset':
            arguments = screenshot_metadata(arguments)
        elif name == 'upload_ui_test_assets' and isinstance(arguments.get('assets'), list):
            arguments['assets'] = [screenshot_metadata(asset) for asset in arguments['assets']]
        def send(values):
            return self.request('/api/mcp/call', {'action': manifest['actions'][name], 'arguments': values}, credential['token'])
        if name in {'start_regression_test', 'finish_test_workflow'}:
            result = lifecycle_call_and_wait(lambda action, values: self.request('/api/mcp/call',
                {'action':action,'arguments':values},credential['token']),manifest['actions'][name],arguments)
        else:
            result = direct_call_and_wait(send, arguments, batch_root=self.path.parent /
                ('browser-batches-' + hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()[:16])) if name == 'direct_test_session' else send(arguments)
        def links(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == 'report_url' and isinstance(value, str) and value.startswith('/api/projects/'):
                        node[key] = self.url+value
                    else:
                        links(value)
            elif isinstance(node, list):
                for item in node:
                    links(item)
        links(result)
        return native_client_status(result)

    def upload_attachments(self, project_id, files):
        """Sync task originals without exposing local paths or Base64 in output."""
        if not files or len(files) > 10:
            raise ValueError('测试要求附件每批需为 1–10 个文件')
        attachments, expected, total = [], {}, 0
        for file in files:
            path = Path(file).expanduser()
            if not path.is_file():
                raise ValueError('测试要求附件必须是可读取的普通文件')
            with path.open('rb') as source:
                content = source.read(50_000_001)
            if not content or len(content) > 50_000_000:
                raise ValueError('测试要求附件不能为空，单个文件最多 50 MB')
            digest = hashlib.sha256(content).hexdigest()
            identity = (path.name, digest)
            if identity in expected:
                continue
            total += len(content)
            if total > 50_000_000:
                raise ValueError('测试要求附件总大小不能超过 50 MB')
            expected[identity] = len(content)
            attachments.append({'filename': path.name, 'content_base64': base64.b64encode(content).decode('ascii')})
        result = self.call('save_test_materials', {'project_id': project_id, 'attachments': attachments})
        saved = result.get('project', {}).get('ui_requirement_attachments', [])
        matched = [item for item in saved if (item['filename'], item['sha256']) in expected
                   and item['size'] == expected[(item['filename'], item['sha256'])]]
        if {(item['filename'], item['sha256']) for item in matched} != set(expected):
            raise ValueError('附件同步回执不完整，请读取会话附件核对；不要宣称全部已保存')
        return {'project_id': project_id, 'synced': len(matched), 'attachments': matched}

    def download_attachment(self, project_id, attachment_id, destination):
        destination = Path(destination).absolute()
        if destination.is_symlink() or destination.parent.is_symlink():
            raise ValueError('附件文件位置不能是符号链接')
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.requirement-', dir=destination.parent)
        digest, size, offset, expected = hashlib.sha256(), 0, 0, None
        try:
            with os.fdopen(fd, 'wb') as handle:
                os.fchmod(handle.fileno(), 0o600)
                while True:
                    chunk = self.call('get_test_attachment', {'project_id':project_id, 'attachment_id':attachment_id, 'offset':offset})
                    identity = (chunk['size'], chunk['sha256'])
                    if expected is None:
                        expected = identity
                    if identity != expected or chunk['offset'] != offset:
                        raise ValueError('附件读取结果不一致，请重新下载')
                    content = base64.b64decode(chunk['content_base64'], validate=True)
                    handle.write(content)
                    digest.update(content)
                    size += len(content)
                    next_offset = chunk['next_offset']
                    if next_offset is None:
                        break
                    if not content or next_offset != size:
                        raise ValueError('附件分页无效')
                    offset = next_offset
                handle.flush()
                os.fsync(handle.fileno())
            if size != expected[0] or digest.hexdigest() != expected[1]:
                raise ValueError('附件完整性校验失败')
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return {'saved_to':str(destination), 'size':size, 'sha256':digest.hexdigest()}


def serve(client):
    """Newline-delimited MCP JSON-RPC; stdout is protocol output only."""
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            print(json.dumps({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Invalid JSON'}}), flush=True)
            continue
        if not isinstance(message, dict):
            print(json.dumps({'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Invalid request'}}), flush=True)
            continue
        if 'id' not in message:
            continue
        reply = {'jsonrpc':'2.0', 'id':message['id']}
        try:
            method, params = message.get('method'), message.get('params') or {}
            if method == 'initialize':
                requested = params.get('protocolVersion')
                version = requested if requested in {'2024-11-05','2025-03-26','2025-06-18'} else '2025-06-18'
                result = {'protocolVersion':version, 'capabilities':{'tools':{}},
                          'serverInfo':{'name':'api-test-workspace','version':'0.7.0'},
                          'instructions':client.tools()['instructions']}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools':client.tools()['tools']}
            elif method == 'tools/call':
                try:
                    value = client.call(params.get('name'), params.get('arguments') or {})
                    result = {'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}], 'structuredContent':value,'isError':False}
                except (ValueError, OSError) as error:
                    result = {'content':[{'type':'text','text':str(error)}],'isError':True}
            else:
                reply['error'] = {'code':-32601,'message':'Method not found'}
                result = None
            if 'error' not in reply:
                reply['result'] = result
        except (ValueError, OSError) as error:
            reply['error'] = {'code':-32603,'message':str(error)}
        print(json.dumps(reply, ensure_ascii=False), flush=True)


def main():
    # JSON CLI/protocol output is UTF-8 even under a legacy ASCII locale.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--credential-file')
    parser.add_argument('--manifest-file', help='复用本次同源下载且 client_sha256 匹配的完整工具清单，避免重复获取')
    commands = parser.add_subparsers(dest='command')
    connect = commands.add_parser('connect', help='兑换连接码，不打印凭据')
    connect.add_argument('--code-file', required=True, help='仅含连接码的 UTF-8 文件，- 表示 stdin')
    call = commands.add_parser('call', help='使用与 MCP 相同的工具名称和参数')
    call.add_argument('tool')
    call_args = call.add_mutually_exclusive_group()
    call_args.add_argument('--args-file', help='JSON 参数文件，- 表示 stdin；省略则 {}')
    call_args.add_argument('--args', help='直接传 JSON 参数；与 args-file 二选一')
    call.add_argument('--base-args-file', help='direct_test_session 复用原参数文件中的 holder/task/node/lease/account ID；不复用旧动作或请求 ID')
    call.add_argument('--receipt-file', type=Path, help='保存原调用回执并保持原JSON输出；公共生命周期编排使用')
    call.add_argument('--output-file', help='将结果写入权限为 0600 的本地 JSON 文件，终端只显示保存路径；用于读取测试凭据或文件')
    call.add_argument('--show-result', action='store_true', help='保存回执同时显示结果，省掉再次读文件；凭据及图像字节不显示，完整内容保留在回执')
    handoff = commands.add_parser('native-handoff-script', help='生成一次 functions.exec 原生交接编排；生成本身不发送消息')
    handoff_args = handoff.add_mutually_exclusive_group(required=True)
    handoff_args.add_argument('--args-file', help='原 finish 或 handoff_ack dispatch 的 JSON 参数；- 表示 stdin')
    handoff_args.add_argument('--args', help='原 finish 或 handoff_ack dispatch 的 JSON 参数')
    handoff.add_argument('--binding-file', type=Path, help='复用 native-record 最后成功保存的身份与修订；不补造退出事实')
    coordinator_wait = commands.add_parser('native-coordinator-wait-script', help='生成原协调回合内的有限事件等待；生成本身不等待或发送')
    coordinator_wait.add_argument('--args-file', required=True, help='原 holder_id/coordinator_ref/task_ids、真实 targets/cursors 及可选观察窗口；- 表示 stdin')
    prepare = commands.add_parser('native-prepare', help='连续领取/上下文/保存原设计；失败立即停止，不执行浏览器')
    stage_ready = commands.add_parser('native-stage-ready', help='资源阶段入口一次只读核对，完整集合就绪后才准备浏览器')
    stage_ready.add_argument('--assignment-file', required=True, type=Path)
    stage_ready.add_argument('--directory', required=True, type=Path)
    resume_entry = commands.add_parser('native-resume', help='机械接入原恢复通知，核对阶段后再准备环境')
    resume_entry.add_argument('--assignment-file', required=True, type=Path)
    resume_entry.add_argument('--directory', required=True, type=Path)
    notice_source = resume_entry.add_mutually_exclusive_group(required=True)
    notice_source.add_argument('--notification-json')
    notice_source.add_argument('--notification-file', type=Path)
    prepare.add_argument('--assignment-file', required=True, type=Path)
    prepare.add_argument('--design-file', required=True, type=Path)
    prepare.add_argument('--directory', required=True, type=Path)
    prepare.add_argument('--receive-observations', action='store_true')
    prepare.add_argument('--summary', action='store_true', help='完整准备结果写入私有回执，只显示继续执行所需摘要，避免终端截断')
    prepare.add_argument('--resume', action='store_true', help='仅收到原资源接续事件后重新领取，复用原准备')
    observe = commands.add_parser('native-observe', help='按本轮 case-id 保存实际判定；自动生成固定参数')
    observe.add_argument('--binding-file', required=True, type=Path)
    observe.add_argument('--case-id')
    observe.add_argument('--status')
    observe.add_argument('--actual')
    observe.add_argument('--observation-json', help='直接复用浏览器断言输出的 case_id/status/checks，不重复写实际结果文案')
    observe.add_argument('--source-file', type=Path, help='直接读取本轮浏览器导出的原始观察，不经模型转录')
    observe.add_argument('--observation-file', type=Path, help='原始观察的私有持久文件；结构化观察必填')
    observe.add_argument('--receipt-file', required=True, type=Path)
    receiver = commands.add_parser('native-observe-receive', help='本轮本地观察单通道接收；事件驱动，无浏览器或模型控制')
    receiver.add_argument('--binding-file', required=True, type=Path)
    receiver.add_argument('--ready-fd', type=int, help=argparse.SUPPRESS)
    correction = commands.add_parser('native-reconcile-observation', help='显式关联原未知观察与独立成功补存；一次只读核对，不重发保存')
    correction.add_argument('--binding-file', required=True, type=Path)
    correction.add_argument('--request-id', required=True)
    correction.add_argument('--correction-receipt-file', required=True, type=Path)
    audit = commands.add_parser('native-cycle-audit', help='同轮一次只读对账并生成耗时报告，不重放测试或轮询')
    audit.add_argument('--binding-file', required=True, type=Path)
    audit.add_argument('--output-file', required=True, type=Path)
    audit.add_argument('--ack-file', type=Path)
    audit.add_argument('--timeline-file', type=Path)
    ack = commands.add_parser('native-ack-script', help='核对原交接绑定后生成一次确认编排')
    ack.add_argument('--assignment-file', required=True, type=Path)
    ack.add_argument('--binding-file', required=True, type=Path)
    ack.add_argument('--event-json', required=True)
    closeout = commands.add_parser('native-closeout-script', help='关页后立即交还并发布已存结果，不再拼 finish JSON')
    closeout.add_argument('--binding-file', required=True, type=Path)
    closeout.add_argument('--browser-stopped', action='store_true')
    closeout.add_argument('--reason')
    closeout.add_argument('--observed-exit', action='store_true', help='复用本轮原观察回执中的实际退出依据')
    closeout.add_argument('--save-unconfirmed', action='store_true', help='结果保存未确认时只交还，不发布完整报告')
    closeout.add_argument('--defer-report', action='store_true', help='实际退出后先交还与通知，保留原记录补保存及发布能力')
    closeout.add_argument('--outcome', choices=['completed', 'yield'], default='completed')
    publish_saved = commands.add_parser('native-publish-saved', help='交还后发布原绑定已存记录，不领取账号或重写结果')
    publish_saved.add_argument('--binding-file', required=True, type=Path)
    publish_saved.add_argument('--receipt-file', required=True, type=Path)
    kit = commands.add_parser('native-run-kit', help='派发前一次生成可执行生命周期包，工作者不再临时拼命令')
    kit.add_argument('--assignment-file', required=True, type=Path)
    kit.add_argument('--design-file', required=True, type=Path)
    kit.add_argument('--directory', required=True, type=Path)
    kit.add_argument('--entry-url', required=True)
    native_record = commands.add_parser('native-record', help='逐条保存真实结果或一次保存最终变化/证据；不控制浏览器、不重试未知提交')
    native_record.add_argument('--binding-file', required=True, type=Path)
    native_record.add_argument('--input-file', required=True, help='逐条结果或最终变化 JSON，可带 asset_files；- 表示 stdin')
    native_record.add_argument('--receipt-file', required=True, type=Path)
    native_record.add_argument('--final-review', action='store_true', help='记住最终回查保存状态，未确认时交还但不发布完整报告')
    native_record.add_argument('--output-file', type=Path)
    download = commands.add_parser('download-attachment', help='下载原始测试要求附件，不打印文件内容')
    download.add_argument('--project-id', required=True)
    download.add_argument('--attachment-id', required=True)
    download.add_argument('--output-file', required=True)
    sync_files = commands.add_parser('upload-attachments', help='同步任务原始附件并核对回执；重复文件复用，不打印 Base64')
    sync_files.add_argument('--project-id', required=True)
    sync_files.add_argument('--file', action='append', required=True, type=Path, help='本次任务提供的原文件，可重复指定')
    tool_help = commands.add_parser('tools', help='读取完整工具格式和执行说明')
    tool_help.add_argument('--name', help='只展示精确名称对应的完整工具与 action，保留全部全局说明；省略则输出完整清单')
    upload = commands.add_parser('upload-files', help='从本地清单批量上传；复用文件读取与编码')
    upload.add_argument('--project', required=True)
    upload.add_argument('--execution', required=True)
    upload.add_argument('--manifest', required=True, type=Path)
    upload.add_argument('--cases-file', help='本轮已保存用例 JSON 列表或含 cases 的读取结果；上传前核对引用')
    check_files = commands.add_parser('check-files', help='仅本地预检文件与用例引用；不编码、不上传、不改结果')
    check_files.add_argument('--manifest', required=True, type=Path)
    check_files.add_argument('--cases-file', help='本轮已保存用例 JSON 列表或含 cases 的读取结果')
    finalize = commands.add_parser('finalize-ui', help='一次保存已核实收尾记录并发布同轮报告；不执行测试或清理')
    finalize.add_argument('--project', required=True)
    finalize.add_argument('--execution', required=True)
    finalize.add_argument('--revision', required=True, type=int)
    finalize.add_argument('--input-file', required=True, help='UTF-8 JSON 收尾记录，- 表示 stdin')
    finalize.add_argument('--receipt-file', required=True, type=Path, help='任务私有回执；中断后核对，不自动重发')
    finalize.add_argument('--summary', action='store_true', help='仅精简终端展示；完整回执不变，相同返回内容注明来源后展示一次，不代判质量')
    commands.add_parser('mcp', help='启动 MCP stdio；也是默认行为')
    work_plan = commands.add_parser('native-work-plan', help='登记原用例阶段；结束后正式续接沿原账号队列')
    work_plan.add_argument('--binding-file', required=True, type=Path)
    work_plan.add_argument('--plan-file', required=True, type=Path)
    work_plan.add_argument('--entry-url')
    cleanup = commands.add_parser('native-cleanup', help='按原模块与租约登记清理证据，不执行业务请求')
    cleanup.add_argument('--binding-file', required=True, type=Path)
    cleanup.add_argument('--events-file', required=True, type=Path)
    work_boundary = commands.add_parser('native-work-boundary', help='阶段边界先继续当前合法可做用例，再交还等完整资源')
    work_boundary.add_argument('--binding-file', required=True, type=Path)
    work_boundary.add_argument('--unit-id', required=True)
    control_read = commands.add_parser('native-control-read', help='分块读取本次私有控制回执，不访问平台或重发请求')
    control_read.add_argument('--file', required=True, type=Path)
    control_read.add_argument('--offset', type=int, default=0)
    for subparser in commands.choices.values():
        subparser.add_argument('--control-result-file', type=Path)
    args = parser.parse_args()
    client = Client(args.url, args.credential_file)
    try:
        if args.command == 'native-control-read':
            content = json.dumps(json.loads(read_utf8(args.file)), ensure_ascii=True, allow_nan=False)
            if not 0 <= args.offset <= len(content):
                raise ValueError('控制回执 offset 越界')
            part = content[args.offset:args.offset + 6000]
            print('NATIVE_CONTROL_PART:' + json.dumps({'file': str(args.file), 'offset': args.offset,
                'text': part, 'next': args.offset + len(part), 'eof': args.offset + len(part) == len(content)}))
            return
        if args.manifest_file:
            client.load_manifest(args.manifest_file)
        if args.command in (None, 'mcp'):
            serve(client)
            return
        if args.command == 'native-work-plan':
            result = native_work_plan(client, args.binding_file, json.loads(read_utf8(args.plan_file)))
            command = [sys.executable, str(Path(__file__).resolve()), '--url', client.url,
                       '--credential-file', str(client.path)]
            if args.manifest_file:
                command += ['--manifest-file', str(Path(args.manifest_file).resolve())]
            result = native_continuation_kit(client, args.binding_file, result, command, args.entry_url)
        elif args.command == 'native-cleanup':
            binding = json.loads(read_utf8(args.binding_file))
            if binding.get('workspace_url', client.url) != client.url:
                raise ValueError('清理登记不属于当前平台')
            events = json.loads(read_utf8(args.events_file))
            validate_cleanup_events({'events': events})
            result = client.call('direct_test_session', {
                **{key: binding[key] for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'dispatch_id', 'executor_ref') if key in binding},
                'action': 'cleanup', 'arguments': {'events': events}})
        elif args.command == 'native-work-boundary':
            result = native_work_boundary(client, args.binding_file, args.unit_id)
        elif args.command == 'connect':
            code = read_utf8(args.code_file)
            result = client.connect(code.strip())
        elif args.command == 'tools':
            result = client.tools()
            if args.name is not None:
                tool = next((item for item in result['tools'] if item['name'] == args.name), None)
                if tool is None:
                    raise ValueError('未知工具名称：%s；使用 tools 查看完整清单' % args.name)
                # Project only CLI display; keep the complete cached manifest for calls/MCP.
                result = {**result, 'tools': [tool],
                          'actions': {key: value for key, value in result['actions'].items() if key == args.name}}
        elif args.command == 'native-reconcile-observation':
            result = reconcile_native_observation_correction(client, args.binding_file,
                args.request_id, args.correction_receipt_file)
        elif args.command == 'native-publish-saved':
            with batch_lock(args.binding_file):
                binding = json.loads(read_utf8(args.binding_file))
                if binding.get('workspace_url', client.url) != client.url:
                    raise ValueError('原绑定不属于当前测试台')
                if not native_publication_ready(args.binding_file, binding):
                    raise ValueError('原保存尚未确认；保留回执，不发布未确认结果，不重新领取账号')
                values = {key: binding[key] for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'dispatch_id', 'executor_ref') if key in binding}
                values.update(action='record', record_action='publish', arguments={key: binding[key]
                              for key in ('project_id', 'execution_id', 'revision')})
                result = client.call('direct_test_session', values)
                write_private_json(args.receipt_file, {'binding': values, 'result': result})
                if result.get('publication', {}).get('phase') == 'published':
                    stop_native_observation_receiver(args.binding_file)
                if result.get('needs_handoff'):
                    command = [sys.executable, str(Path(__file__).resolve()), '--url', client.url,
                               '--credential-file', str(client.path)]
                    if args.manifest_file:
                        command += ['--manifest-file', str(Path(args.manifest_file).resolve())]
                    command += ['call', 'direct_test_session']
                    finish = {key: binding[key] for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'dispatch_id', 'executor_ref') if key in binding}
                    finish['action'] = 'finish'
                    result['handoff_script'] = native_handoff_script(NATIVE_HANDOFF_TEMPLATE, command, finish,
                        args.binding_file.parent, initial_result=result)
        elif args.command in ('native-handoff-script', 'native-closeout-script'):
            values = ((native_observed_closeout_arguments(args.binding_file) if args.observed_exit else
                       native_closeout_arguments(json.loads(read_utf8(args.binding_file)),
                      browser_stopped=args.browser_stopped, reason=args.reason, save_unconfirmed=args.save_unconfirmed,
                      defer_report=args.defer_report, outcome=args.outcome)
                       ) if args.command == 'native-closeout-script' else
                      json.loads(read_utf8(args.args_file) if args.args_file else args.args))
            if args.command == 'native-closeout-script' and args.save_unconfirmed:
                values['arguments'].update(save_unconfirmed=True, publish_saved=False, result='partial', coverage_complete=False)
            if args.command == 'native-closeout-script' and args.defer_report:
                values['arguments'].update(report_pending=True, publish_saved=False)
            if args.command == 'native-closeout-script' and args.outcome == 'yield':
                values['outcome'] = 'yield'
                values['arguments']['publish_saved'] = False
                values['arguments'].pop('report_pending', None)
                values['arguments'].pop('publication_binding', None)
            if args.binding_file:
                binding = json.loads(read_utf8(args.binding_file))
                if binding.get('workspace_url', client.url) != client.url:
                    raise ValueError('binding-file 不属于当前测试台')
                if args.command == 'native-handoff-script':
                    values = bound_handoff_arguments(binding, values)
                if args.command == 'native-closeout-script' and not args.defer_report:
                    stop_native_observation_receiver(args.binding_file)
            command = [sys.executable, str(Path(__file__).resolve()), '--url', client.url,
                       '--credential-file', str(client.path)]
            if args.manifest_file:
                command += ['--manifest-file', str(Path(args.manifest_file).resolve())]
            command += ['call', 'direct_test_session']
            result = {'capability': NATIVE_HANDOFF_CAPABILITY, 'direct_capability': NATIVE_DIRECT_HANDOFF_CAPABILITY, 'executed': False,
                      'tool': 'functions.exec',
                      'script': native_handoff_script(NATIVE_HANDOFF_TEMPLATE, command, values,
                          args.binding_file.parent if args.command == 'native-closeout-script' else None)}
            if args.command == 'native-closeout-script' and args.defer_report:
                result['review_state'] = native_review_state(args.binding_file)
        elif args.command == 'native-coordinator-wait-script':
            command = [sys.executable, str(Path(__file__).resolve()), '--url', client.url,
                       '--credential-file', str(client.path)]
            if args.manifest_file:
                command += ['--manifest-file', str(Path(args.manifest_file).resolve())]
            command += ['call', 'direct_test_session']
            result = {'capability': NATIVE_COORDINATOR_WAIT_CAPABILITY, 'executed': False,
                      'tool': 'functions.exec', 'script': native_coordinator_script(
                          NATIVE_COORDINATOR_TEMPLATE, NATIVE_HANDOFF_TEMPLATE,
                          json.loads(read_utf8(args.args_file)), command=command)}
        elif args.command == 'native-ack-script':
            assignment = json.loads(read_utf8(args.assignment_file))
            binding = json.loads(read_utf8(args.binding_file))
            if assignment.get('workspace_url', client.url) != client.url or binding.get('workspace_url', client.url) != client.url:
                raise ValueError('原交接绑定不属于当前测试台')
            values = native_ack_arguments(assignment, binding, json.loads(args.event_json))
            command = [sys.executable, str(Path(__file__).resolve()), '--url', client.url,
                       '--credential-file', str(client.path)]
            if args.manifest_file:
                command += ['--manifest-file', str(Path(args.manifest_file).resolve())]
            command += ['call', 'direct_test_session']
            result = {'script': native_handoff_script(NATIVE_HANDOFF_TEMPLATE, command, values, args.binding_file.parent)}
        elif args.command == 'native-run-kit':
            command = [sys.executable, str(Path(__file__).resolve()), '--url', client.url,
                       '--credential-file', str(client.path)]
            if args.manifest_file:
                command += ['--manifest-file', str(Path(args.manifest_file).resolve())]
            result = native_run_kit(command, args.assignment_file, args.design_file, args.directory, args.entry_url)
        elif args.command == 'native-stage-ready':
            result = native_stage_ready(client, args.assignment_file, args.directory)
        elif args.command == 'native-resume':
            notice = json.loads(read_utf8(args.notification_file) if args.notification_file else args.notification_json)
            result = native_resume(client, args.assignment_file, args.directory, notice)
        elif args.command == 'native-prepare':
            result = prepare_native(client, json.loads(read_utf8(args.assignment_file)),
                json.loads(read_utf8(args.design_file)), args.directory, resume=args.resume)
            if result.get('ready') and args.receive_observations:
                command = [sys.executable, str(Path(__file__).resolve()), '--url', client.url,
                           '--credential-file', str(client.path)]
                if args.manifest_file:
                    command += ['--manifest-file', str(Path(args.manifest_file).resolve())]
                result['observation_receiver'] = start_native_observation_receiver(command, Path(args.directory)/'binding.json')
            prepared_call = native_prepared_call(args.directory, result)
            if prepared_call:
                result['native_call'] = prepared_call
            if result.get('state') == 'waiting':
                result['resume_command'] = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
                if not args.resume:
                    result['resume_command'].append('--resume')
                result['resume_when'] = '仅收到原资源可用事件后执行此 argv；现在结束回合，不轮询、不另拼 claim 参数'
            if args.summary:
                result = native_prepared_summary(args.directory, result)
        elif args.command == 'native-observe-receive':
            result = receive_native_observations(client, args.binding_file, ready_fd=args.ready_fd)
        elif args.command == 'native-cycle-audit':
            result = audit_native_cycle(client, args.binding_file, args.output_file, args.ack_file, args.timeline_file)
        elif args.command == 'native-observe':
            if args.observation_json is not None or args.source_file is not None:
                if args.observation_json is not None and args.source_file is not None:
                    raise ValueError('不能混用观察文件和 JSON')
                if any(x is not None for x in (args.case_id, args.status, args.actual)) or not args.observation_file:
                    raise ValueError('结构化观察不能混用手工判定参数，且必须保留 observation-file')
                observation = json.loads(read_utf8(args.source_file) if args.source_file else args.observation_json)
                result = observed_native_json(client, args.binding_file, observation,
                                              args.observation_file, args.receipt_file)
            else:
                result = observed_native(client, args.binding_file, args.case_id, args.status, args.actual, args.receipt_file)
        elif args.command == 'native-record':
            if args.output_file:
                inputs = {args.binding_file.resolve(), args.receipt_file.resolve()}
                if args.input_file != '-':
                    inputs.add(Path(args.input_file).resolve())
                if args.output_file.resolve() in inputs:
                    raise ValueError('output-file 不能覆盖绑定、输入或持久保存回执')
            result = client.native_record(args.binding_file, json.loads(read_utf8(args.input_file)), args.receipt_file,
                                          final_review=args.final_review)
            if args.output_file:
                write_private_json(args.output_file, result)
                result = {'saved_to': str(args.output_file.absolute()),
                          **{key: result[key] for key in ('saved', 'execution_id', 'revision', 'binding_revision',
                                                         'reused_receipt', 'client_timing')},
                          'progress_message': result.get('result', {}).get('progress_message', '')}
        elif args.command in ('upload-files', 'check-files'):
            entries = json.loads(read_utf8(args.manifest))
            cases = json.loads(read_utf8(args.cases_file)) if args.cases_file else None
            if isinstance(cases, dict):
                cases = cases.get('cases')
                if cases is None:
                    raise ValueError('cases-file 缺少 cases 列表')
            if args.command == 'check-files':
                result = check_file_manifest(entries, cases)
                if not result['valid']:
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    raise SystemExit(1)
            else:
                result = client.upload_assets_from_files(args.project, args.execution, entries, cases)
        elif args.command == 'finalize-ui':
            result = client.finalize_ui_test_round(args.project, args.execution, args.revision,
                                                  json.loads(read_utf8(args.input_file)), args.receipt_file)
            if args.summary:
                result = summarize_ui_finalization(result, args.receipt_file)
        elif args.command == 'upload-attachments':
            result = client.upload_attachments(args.project_id, args.file)
        elif args.command == 'download-attachment':
            result = client.download_attachment(args.project_id, args.attachment_id, args.output_file)
        else:
            raw = read_utf8(args.args_file) if args.args_file else args.args or '{}'
            values = json.loads(raw)
            if args.base_args_file:
                if args.tool != 'direct_test_session' or not isinstance(values, dict):
                    raise ValueError('base-args-file 仅用于 direct_test_session 的 JSON 对象参数')
                base = json.loads(read_utf8(args.base_args_file))
                values = {**{key: base[key] for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'account_id') if key in base}, **values}
            result = client.call(args.tool, values)
        if args.command == 'call' and args.receipt_file:
            write_private_json(args.receipt_file, result)
        if args.control_result_file:
            write_private_json(args.control_result_file, result)
            print(json.dumps({'control_result_file': str(args.control_result_file), 'complete': True}))
            return
        if args.command == 'call' and args.output_file:
            destination = Path(args.output_file).absolute()
            write_private_json(destination, result)
            display = {'saved_to': str(destination)}
            if args.tool == 'start_regression_test' and result.get('prepared_execution'):
                display['round_files'] = prepare_round_files(destination, result, values)
            if args.show_result:
                if args.tool == 'direct_test_session' and values.get('action') in {'browser', 'result', 'claim', 'finish'}:
                    def readable(value):
                        if isinstance(value, dict):
                            return {key: ('[图像字节保存在完整回执]' if key == '_image_url' else readable(item)) for key, item in value.items()}
                        if isinstance(value, list):
                            return [readable(item) for item in value]
                        return value
                    display['result'] = readable(result)
                else:
                    display['notice'] = '完整结果已保存；此动作可能包含凭据，不自动显示。'
            print(json.dumps(display, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
