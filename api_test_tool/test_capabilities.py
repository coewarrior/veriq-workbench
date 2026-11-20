"""Documented, target-bound test adapters; no arbitrary SQL or executable code.

A payment adapter belongs to the tested application in dev/test. It translates
the simulated event into that application's real payment notification path.
This service never synthesizes orders, balances or successful business results.
"""
from __future__ import annotations

import copy
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit
from uuid import uuid4

import jsonschema
import requests

from .execution import Redactor
from .network_transport import pinned_session
from .parsers import _pointer
from . import requirement_design, test_checkpoints

KINDS = {'http', 'observation', 'prepare', 'cleanup', 'payment_control'}
LAB_ENVIRONMENTS = {'local', 'dev', 'test', 'qa', 'uat', 'staging'}
SCENARIOS = {
    'cancel': ['cancel'], 'unknown': ['unknown'], 'delayed_success': ['pending'],
    'release_success': ['success'], 'duplicate_callback': ['success', 'success'],
    'out_of_order': ['pending', 'success', 'pending'],
    'entitlement_failure': ['enable_entitlement_fault', 'success', 'disable_entitlement_fault'],
}
MAX_RESPONSE = 1024 * 1024


def load(store, owner, pid):
    try:
        return store.load_asset(owner, pid, 'test-capabilities')
    except FileNotFoundError:
        return {'revision': 0, 'items': []}


def view(store, owner, pid):
    from .ui_records import ui_project
    project = ui_project(store, owner, pid)
    state = load(store, owner, pid)
    return {**state, 'items': [{k: v for k, v in c.items() if k != 'headers_ciphertext'} | {
            'has_credentials': bool(c.get('headers_ciphertext'))} for c in state['items']],
            'target_url': project.get('ui_target_url', ''), 'base_url': project.get('task', {}).get('base_url', ''),
            'payment_scenarios': list(SCENARIOS),
            'guidance': '业务查询、准备、清理与支付控制需被测系统提供有文档的 HTTP 适配器；只访问本任务已绑定目标。'
                        '支付模拟仅验证被测应用的业务处理，不证明真实微信通道可用。响应缺失或无业务断言保留部分验证。'}


def _schema(value):
    if not isinstance(value, dict) or len(json.dumps(value)) > 30000:
        raise ValueError('parameters_schema 必须是有限的 JSON Schema')
    if re.search(r'"\$(?:ref|dynamicRef)"', json.dumps(value)):
        raise ValueError('测试适配器参数 Schema 不支持外部或递归引用')
    if value.get('type') != 'object' or value.get('additionalProperties') is not False:
        raise ValueError('参数 Schema 需为 object 并设置 additionalProperties:false')
    try:
        jsonschema.Draft202012Validator.check_schema(value)
    except jsonschema.SchemaError as exc:
        raise ValueError('parameters_schema 格式不正确') from exc


def validate_parameters(params, schema):
    try:
        jsonschema.validate(params, schema)
    except jsonschema.ValidationError as exc:
        # Validation errors may contain account or authentication values.
        raise ValueError('参数不符合已保存的适配器 Schema，请核对必填项和类型') from exc


def save(store, owner, pid, revision, items):
    from .ui_records import ui_project
    with store._lock:
        project = ui_project(store, owner, pid)
        state = load(store, owner, pid)
        if type(revision) is not int or state['revision'] != revision:
            raise ValueError('测试能力已更新，请刷新后重试')
        if not isinstance(items, list) or len(items) > 50:
            raise ValueError('每批最多配置 50 个测试适配器')
        merged = {c['key']: c for c in state['items']}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('测试适配器需为对象')
            c = {k: test_checkpoints.text(item.get(k, ''), k, 4000, True)
                 for k in ('key', 'title', 'kind', 'path', 'method', 'environment', 'verification_mode')}
            c['source_quote'] = test_checkpoints.text(item.get('source_quote', ''), 'source_quote', 4000)
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', c['key']) or c['kind'] not in KINDS:
                raise ValueError('测试适配器 key 或 kind 无效')
            if c['verification_mode'] not in {'real', 'sandbox', 'mock'}:
                raise ValueError('测试能力 verification_mode 仅支持 real/sandbox/mock')
            if c['kind'] == 'payment_control' and c['verification_mode'] != 'mock':
                raise ValueError('模拟支付适配器必须标记为 mock')
            if c['kind'] in {'payment_control', 'prepare', 'cleanup'} and c['environment'] not in LAB_ENVIRONMENTS:
                raise ValueError('故障控制和数据准备/清理适配器仅适用于开发、测试环境')
            if c['method'] not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}:
                raise ValueError('测试能力 method 无效')
            if c['kind'] == 'observation' and c['method'] != 'GET':
                raise ValueError('业务观察适配器使用只读 GET 接口')
            if (not c['path'].startswith('/') or c['path'].startswith('//') or '\\' in c['path'] or
                    any(ord(v) < 33 for v in c['path']) or '?' in c['path'] or '#' in c['path'] or
                    any(v in {'.', '..'} for v in c['path'].split('/'))):
                raise ValueError('测试能力 path 必须是文档中的相对路径')
            schema = item.get('parameters_schema', {'type': 'object', 'properties': {}, 'additionalProperties': False})
            _schema(schema)
            c['parameters_schema'] = schema
            for key in ('query_template', 'body_template'):
                value = item.get(key, {})
                if not isinstance(value, dict) or len(json.dumps(value)) > 30000:
                    raise ValueError(key + ' 必须是有限 JSON 对象')
                if Redactor().snapshot(value) != value:
                    raise ValueError('请求模板不能包含明文凭据；使用加密 headers 或临时参数占位符')
                c[key] = value
            headers = item.get('headers')
            if headers is not None:
                if not isinstance(headers, dict) or len(headers) > 20 or any(
                        not isinstance(k, str) or not isinstance(v, str) or len(v) > 4000 or '\n' in v or '\r' in v
                        or k.lower() in {'host', 'proxy-authorization'} for k, v in headers.items()):
                    raise ValueError('认证请求头格式无效')
                c['headers_ciphertext'] = store._cipher.encrypt(json.dumps(headers).encode()).decode() if headers else ''
            else:
                c['headers_ciphertext'] = merged.get(c['key'], {}).get('headers_ciphertext', '')
            # Bind once; switching the task address invalidates the adapter.
            c['target_url'] = project.get('ui_target_url', '')
            c['base_url'] = project.get('task', {}).get('base_url', '')
            if not (c['target_url'] or c['base_url']):
                raise ValueError('先绑定测试地址，再配置执行适配器；需求设计不受影响')
            merged[c['key']] = c
        state = {'revision': state['revision'] + 1, 'items': list(merged.values())}
        store.save_asset(owner, pid, 'test-capabilities', state)
        return view(store, owner, pid)


def render(value, params):
    if isinstance(value, dict):
        return {k: render(v, params) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, params) for v in value]
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r'\$\{([\w.-]+)\}', value)
    if match:
        if match[1] not in params:
            raise ValueError('请求模板缺少参数：' + match[1])
        return params[match[1]]
    def replace(m):
        if m[1] not in params:
            raise ValueError('请求模板缺少参数：' + m[1])
        return str(params[m[1]])
    return re.sub(r'\$\{([\w.-]+)\}', replace, value)


def request(c, params, headers, base, trusted, redactor):
    validate_parameters(params, c['parameters_schema'])
    def path_value(m):
        if m[1] not in params or not isinstance(params[m[1]], (str, int)):
            raise ValueError('路径参数缺失或类型错误：' + m[1])
        value = str(params[m[1]])
        if value in {'.', '..'}:
            raise ValueError('路径参数不能为目录跳转')
        return quote(value, safe='')
    path = re.sub(r'\{([\w.-]+)\}', path_value, c['path'])
    target = base.rstrip('/') + path
    begin = time.monotonic()
    try:
        with pinned_session(base, trusted) as session:
            with session.request(c['method'], target, params=render(c['query_template'], params),
                                 json=render(c['body_template'], params) if c['method'] != 'GET' else None,
                                 headers=headers, timeout=(5, 15), stream=True) as response:
                content = bytearray()
                for chunk in response.iter_content(1):
                    if time.monotonic() - begin > 20:
                        raise ValueError('适配器观察超时，执行结果未知，未自动重试')
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE:
                        raise ValueError('适配器响应超过 1 MiB，尚未完成业务观察')
                raw = bytes(content)
                try:
                    data = json.loads(raw)
                except (ValueError, UnicodeError):
                    data = None
                return redactor.snapshot({'http_status': response.status_code, 'data': data,
                    'elapsed_ms': round((time.monotonic() - begin) * 1000),
                    'verification_mode': c['verification_mode'], 'capability_key': c['key']})
    except requests.RequestException:
        # Mutation outcome may be unknown. Never automatically retry it.
        return {'http_status': None, 'data': None, 'error': '请求未取得可信响应；执行结果未知，未自动重试',
                'verification_mode': c['verification_mode'], 'capability_key': c['key']}


def assertions(point, response, case):
    """All comparisons are from the saved design, not runtime supplied truths."""
    results = []
    for a in point.get('assertions', []):
        try:
            actual = response.get('http_status') if a['kind'] == 'http_status' else _pointer(response['data'], a['pointer'])
            if a['kind'] == 'delta':
                baseline = next(p for p in case['checkpoints'] if p['id'] == a['baseline_checkpoint_id'])
                evidence = next(e for e in reversed(baseline.get('evidence', [])) if 'data' in e)
                actual = actual - _pointer(evidence['data'], a['pointer'])
            if a['kind'] == 'length':
                actual = len(actual)
            results.append({'expected': a['expected'], 'actual': actual, 'passed': type(actual) is type(a['expected']) and actual == a['expected']})
        except (KeyError, TypeError, ValueError, StopIteration, IndexError):
            results.append({'expected': a['expected'], 'actual': None, 'passed': False, 'missing_evidence': True})
    status = ('failed' if any(not a['passed'] and not a.get('missing_evidence') for a in results) else
              'partial' if not results or any(a.get('missing_evidence') for a in results) else 'passed')
    http_status = response.get('http_status')
    if http_status is None:
        status = 'partial'
    elif not 200 <= http_status < 300 and not any(
            a['kind'] == 'http_status' and a['expected'] == http_status for a in point.get('assertions', [])):
        # A negative HTTP test may explicitly expect a 4xx. Successful business
        # fields alone cannot turn an unexpected failed observation into a pass.
        status = 'failed' if status == 'failed' else 'partial'
    return status, results


def experiments(store, owner, pid, execution_id):
    from .ui_records import root_for
    path = root_for(store, owner, pid, execution_id) / 'experiments.json'
    return path, store._read(path) if path.exists() else {'items': {}}


def run(store, owner, pid, execution_id, revision, case_id, checkpoint_id, capability_key, parameters,
        invocation_id, trusted=(), experiment='single', scenario='', workers=2, mutation_lock=None):
    """Reserve before I/O. Repeated invocation IDs read outcome; they never resend."""
    from .ui_records import now
    invocation_id = test_checkpoints.text(invocation_id, 'invocation_id', 100, True)
    with (mutation_lock or store._lock), store._lock:
        path, history = experiments(store, owner, pid, execution_id)
        if invocation_id in history['items']:
            prior = history['items'][invocation_id]
            if prior.get('case_id') != case_id or prior.get('checkpoint_id') != checkpoint_id:
                raise ValueError('invocation_id 已属于另一检查点，不能用于新操作')
            return {**history['items'][invocation_id], 'reused': True}
        if any(j['case_id'] == case_id and j['checkpoint_id'] == checkpoint_id and j['status'] == 'running'
               for j in history['items'].values()):
            raise ValueError('该检查点已有执行记录尚未完成，请查询原 invocation_id，不能重复发送')
        project, record = test_checkpoints.current(store, owner, pid, execution_id, revision)
        case = next((c for c in record['cases'] if c['case_id'] == case_id), None)
        from .testing_policy import case_excluded, excluded_response
        if case and case_excluded(case):
            return excluded_response(case_id=case_id, checkpoint_id=checkpoint_id, invocation_id=invocation_id)
        point = next((p for p in (case or {}).get('checkpoints', []) if p['id'] == checkpoint_id), None)
        if not point or point.get('capability_key') != capability_key:
            raise ValueError('请先将真实测试能力关联到已保存的检查点')
        if point['status'] in {'passed', 'failed'}:
            raise ValueError('该检查点已有结果；需要重测时先建立续跑计划')
        c = next((c for c in load(store, owner, pid)['items'] if c['key'] == capability_key), None)
        if not c or c['target_url'] != project.get('ui_target_url', '') or c['base_url'] != project.get('task', {}).get('base_url', ''):
            raise ValueError('测试能力未配置或目标已变化，请重新绑定并检查')
        if c['environment'] != case.get('environment'):
            raise ValueError('测试能力和用例环境不一致')
        if c['method'] != 'GET' and (project.get('ui_execution_permission') or {}).get('key') == 'safe':
            raise ValueError('本轮安全权限不包含适配器写入操作')
        if c['kind'] == 'http' and c['method'] != 'GET' and c['verification_mode'] == 'real' and (project.get('ui_execution_permission') or {}).get('key') != 'maximum':
            raise ValueError('真实业务写入适配器需本轮最大权限；测试数据使用开发/测试环境 prepare/cleanup 适配器')
        if experiment not in {'single', 'concurrent', 'payment_scenario'}:
            raise ValueError('experiment 仅支持 single/concurrent/payment_scenario')
        if experiment != 'single' and c['environment'] not in LAB_ENVIRONMENTS:
            raise ValueError('并发竞争和模拟故障仅在开发、测试环境执行')
        if experiment == 'payment_scenario' and (c['kind'] != 'payment_control' or scenario not in SCENARIOS):
            raise ValueError('请配置模拟支付适配器并选择支持的场景')
        if experiment == 'concurrent' and (type(workers) is not int or not 2 <= workers <= 8):
            raise ValueError('受控并发数为 2–8；这不是压测')
        if not isinstance(parameters, dict):
            raise ValueError('parameters 必须是对象')
        # Continuations stay on the original order. Replacing payer/order here
        # could silently launch another payment while reconciling an unknown one.
        correlation = {k: v for p in case['checkpoints'] for k, v in p.get('correlation', {}).items()}
        for key in ('order_id', 'payer_id', 'provider_transaction_id'):
            if key in correlation and key in parameters and correlation[key] != parameters[key]:
                raise ValueError('续跑关联与原订单不一致：' + key)
        if experiment == 'payment_scenario' and not parameters.get('order_id'):
            raise ValueError('模拟支付必须关联被测应用已创建的真实测试订单')
        if experiment == 'payment_scenario' and not parameters.get('provider_transaction_id'):
            raise ValueError('模拟通知需明确稳定的模拟交易 ID；重复和延迟回调使用同一交易')
        calls = [copy.deepcopy(parameters)]
        if experiment == 'concurrent':
            calls *= workers
        if experiment == 'payment_scenario':
            calls = [{**parameters, 'event': event, 'scenario': scenario} for event in SCENARIOS[scenario]]
        for params in calls:
            validate_parameters(params, c['parameters_schema'])
            render(c['body_template'], params)
            render(c['query_template'], params)
        headers = json.loads(store._cipher.decrypt(c['headers_ciphertext'].encode())) if c.get('headers_ciphertext') else {}
        redactor = Redactor()
        for v in headers.values():
            redactor.add_secret(v)
        redactor.remember(parameters)
        target = c['base_url'] or (lambda p: f'{p.scheme}://{p.netloc}')(urlsplit(c['target_url']))
        job = {'id': str(uuid4()), 'invocation_id': invocation_id, 'execution_id': execution_id,
               'case_id': case_id, 'checkpoint_id': checkpoint_id, 'status': 'running',
               'experiment': experiment, 'scenario': scenario, 'verification_mode': c['verification_mode'],
               'created_at': now(), 'correlation': redactor.snapshot({k: parameters[k] for k in
                   ('order_id', 'payer_id', 'provider_transaction_id') if k in parameters})}
        history['items'][invocation_id] = job
        store._write(path, history)
    responses, starts = [], []
    try:
        if experiment == 'concurrent':
            barrier = threading.Barrier(workers)
            def send(params):
                # Resolve/pin each session before entering the barrier in request
                # is not guaranteed; record launch skew, never claim server atomicity.
                barrier.wait(timeout=10)
                begin = time.monotonic()
                return begin, request(c, params, headers, target, trusted, redactor)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(send, calls))
            starts, responses = map(list, zip(*results))
        else:
            for params in calls:
                try:
                    responses.append(request(c, params, headers, target, trusted, redactor))
                except ValueError as exc:
                    responses.append({'http_status': None, 'data': None,
                        'error': redactor.snapshot(str(exc)[:400]) + '；结果未知，未自动重试'})
                # Keep later cleanup events in the sequence even if notification
                # failed, so an entitlement fault does not leak into other tests.
    except (ValueError, jsonschema.ValidationError, threading.BrokenBarrierError):
        responses.append({'http_status': None, 'data': None, 'error': '测试适配器未完成；请核对条件和原订单，未自动重试'})
    checks = [assertions(point, r, case) for r in responses]
    status = 'failed' if any(s == 'failed' for s, _ in checks) else 'passed' if checks and all(s == 'passed' for s, _ in checks) else 'partial'
    with (mutation_lock or store._lock), store._lock:
        _, history = experiments(store, owner, pid, execution_id)
        job.update(status='completed', responses=responses, assertion_results=[a for _, a in checks],
                   result=status, launch_skew_ms=round((max(starts) - min(starts)) * 1000, 2) if starts else None)
        # Concurrent edits/publication may have occurred during network I/O.
        # Keep the durable outcome, but never overwrite a newer design or report.
        try:
            test_checkpoints.current(store, owner, pid, execution_id, revision)
            result = test_checkpoints.record_result(store, owner, pid, execution_id, revision, case_id, checkpoint_id,
                {'status': status, 'actual': f'执行适配器 {c["title"]}，{len(responses)} 次请求；业务比较结果：{status}。',
                 'method': experiment + (' / ' + scenario if scenario else ''), 'verification_mode': c['verification_mode'],
                 'evidence': responses, 'correlation': job['correlation']})
            job['saved_result'] = result
        except ValueError:
            job['save_gap'] = '结果未能回写当前用例；请读取执行记录核对轮次、设计和证据容量，不能重复发送请求'
        history['items'][invocation_id] = job
        store._write(path, history)
        return job
