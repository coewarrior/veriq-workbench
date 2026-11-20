"""Ordered browser commands with durable, individually authorized step receipts.

A batch reduces model/transport round trips, never the operation ledger, request
policy, required observations or per-case assertions. Unknown steps are not replayed.
"""
from __future__ import annotations
import asyncio
import hashlib
import time

ACTIONS = {'navigate','snapshot','screenshot','click','fill','press','select','wait',
           'back','upload','tabs','switch_tab','check'}
REQUIRED = {'navigate':('url',), 'click':('selector',), 'fill':('selector','value'),
            'press':('selector','key'), 'select':('selector','value'), 'wait':('selector',),
            'upload':('selector',), 'switch_tab':('page_index',), 'check':('selector','expect')}


def steps(parameters):
    if isinstance(parameters,dict) and 'cases' in parameters:
        from .case_execution import validate
        return validate(parameters)
    value = parameters.get('steps') if isinstance(parameters, dict) else None
    if not isinstance(value, list) or not value:
        raise ValueError('batch 需要非空 steps，每步包含 id、action、parameters')
    seen = set()
    for step in value:
        if not isinstance(step, dict) or step.get('action') not in ACTIONS:
            raise ValueError('batch 只支持普通受控动作，不能嵌套 batch 或共享准备')
        identity = step.get('id')
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise ValueError('batch 每步需要独立且不重复的 id')
        seen.add(identity)
        args = step.get('parameters', {})
        if not isinstance(args, dict) or any(k not in args for k in REQUIRED.get(step['action'], ())):
            raise ValueError('batch 步骤参数不完整')
        if step['action']=='check' and (not isinstance(args['expect'],dict) or not args['expect']
                or set(args['expect'])-{'visible','enabled','text','value','count'}):
            raise ValueError('check 的 expect 需要明确的受支持断言')
        if args.get('response', 'full') not in {'full','summary'}:
            raise ValueError('response 只支持 full 或 summary')
    return value


def operation_id(request, step):
    # A bounded deterministic ID keeps the existing ledger's 160-char limit.
    return 'batch-' + hashlib.sha256((request + '\0' + step).encode()).hexdigest()


async def execute(broker, lid, aid, parameters, request):
    if 'cases' in parameters:
        from .case_execution import execute as execute_cases
        return await execute_cases(broker,lid,aid,parameters)
    plan = steps(parameters)  # Validate the whole plan before its first side effect.
    receipts = []
    for index, step in enumerate(plan):
        oid = operation_id(request, step['id'])
        args = dict(step.get('parameters', {}))
        # Final observation stays complete. Explicit evidence/snapshot/check
        # steps retain their own requested observation and independent result.
        if step['action'] not in {'snapshot','screenshot'}:
            args.setdefault('response', 'full' if index == len(plan)-1 else 'summary')
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(broker.operate(lid, aid, step['action'], args, oid), timeout=75)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            from .browser_policy import ExclusiveRequired
            state = 'blocked' if isinstance(exc, ExclusiveRequired) or getattr(exc, 'operation_state', '') == 'not_sent' else 'unknown'
            receipts.append({'id':step['id'], 'operation_id':oid, 'state':state,
                             'error_type':type(exc).__name__, 'elapsed_seconds':round(time.monotonic()-started,3)})
            return {'_command_state':state, 'steps':receipts, 'stopped_at':step['id'],
                    'unexecuted_steps':[item['id'] for item in plan[index+1:]],
                    'requires_exclusive':isinstance(exc, ExclusiveRequired),
                    'business_failure':False,
                    'instruction':'保留已完成步骤的原回执；核对失败步骤，未发送的后续步骤尚未执行。未知步骤不重放。'}
        receipts.append({'id':step['id'], 'operation_id':oid, 'state':'completed',
                         'result':result, 'elapsed_seconds':round(time.monotonic()-started,3)})
        if result.get('requires_exclusive') or result.get('assertion_passed') is False:
            return {'_command_state':'completed', 'steps':receipts, 'stopped_at':step['id'],
                    'unexecuted_steps':[item['id'] for item in plan[index+1:]],
                    'requires_exclusive':bool(result.get('requires_exclusive')),
                    'business_failure':bool(result.get('business_failure')),
                    'continue_exploration':bool(result.get('continue_exploration'))}
    return {'_command_state':'completed', 'steps':receipts, 'unexecuted_steps':[]}
