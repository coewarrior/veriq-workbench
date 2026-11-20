"""Execute an explicit known case plan without model turns between cases.

Uses the existing browser ledger and case-save endpoint. No inferred assertions,
business retries, new test rounds or hidden coverage reduction.
"""
import json
import time
from datetime import datetime, timezone


def validate(parameters, record=None):
    from .browser_batch import steps
    cases = parameters.get('cases')
    plan_id = parameters.get('plan_id')
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise ValueError('用例执行计划需要稳定 plan_id；续接复用原 ID')
    if not isinstance(cases, list) or not cases:
        raise ValueError('cases 必须是已知步骤与检查点的非空计划')
    seen = set()
    known = {c['case_id']:c for c in (record or {}).get('cases', [])}
    flattened = []
    for case in cases:
        cid = case.get('case_id') if isinstance(case, dict) else None
        if not isinstance(cid,str) or not cid or cid in seen:
            raise ValueError('每条计划需有唯一的原 case_id')
        seen.add(cid)
        plan = steps({'steps':case.get('steps')})
        assertions = {s['id'] for s in plan if s['action']=='check'}
        mapping = case.get('checkpoints')
        if not isinstance(mapping,dict) or not mapping or any(
                not isinstance(k,str) or not isinstance(v,list) or not v or
                any(x not in assertions for x in v) for k,v in mapping.items()):
            raise ValueError('checkpoints 将原检查点 ID 映射到实际 check 步骤 ID 数组')
        if assertions != {sid for ids in mapping.values() for sid in ids}:
            raise ValueError('每个实际断言必须关联原检查点')
        if record is not None:
            original = known.get(cid)
            if not original or not set(mapping).issubset({p['id'] for p in original.get('checkpoints',[])}):
                raise ValueError('计划只能更新原用例已有检查点，未安排的检查点原样保留')
        flattened.extend({**s,'id':cid+':'+s['id']} for s in plan)
    return flattened


async def execute(broker, lid, aid, parameters):
    from .browser_batch import execute as execute_steps, operation_id
    record = await broker.call('record', lease_id=lid)
    validate(parameters, record)  # Validate every case before any browser action.
    originals = {c['case_id']:c for c in record['cases']}
    results = []
    for case in parameters['cases']:
        cid = case['case_id']; original = originals[cid]
        from .testing_policy import case_excluded, excluded_response
        if case_excluded(original):
            results.append({'case_id': cid, **excluded_response()})
            continue
        if original['status'] in {'passed','failed'} and all(
                p['status'] in {'passed','failed'} for p in original.get('checkpoints',[])):
            results.append({'case_id':cid,'state':'already_saved','status':original['status']})
            continue
        started = time.monotonic()
        request = operation_id(parameters['plan_id'], cid)
        result = await execute_steps(broker,lid,aid,{'steps':case['steps']},request)
        receipts = {s['id']:s for s in result['steps']}
        updates = []
        for point, ids in case['checkpoints'].items():
            observed = [receipts.get(sid,{}) for sid in ids]
            checks = [s.get('result',{}) for s in observed]
            failed = any(x.get('assertion_passed') is False for x in checks)
            complete = all(s.get('state')=='completed' and 'assertion_passed' in x
                           for s,x in zip(observed,checks))
            if failed or complete:
                updates.append({'id':point,'status':'failed' if failed else 'passed',
                    'verification_mode':'real','actual':json.dumps([
                        {'step':sid,'observed':x.get('observed'),'expected':x.get('expected')}
                        for sid,x in zip(ids,checks)],ensure_ascii=False)})
        final_points = {p['id']:p for p in original.get('checkpoints',[])}
        final_points.update({p['id']:p for p in updates})
        complete = all(p['status'] in {'passed','failed'} for p in final_points.values()) and not result.get('unexecuted_steps')
        failed = any(p['status']=='failed' for p in final_points.values())
        status = 'failed' if failed else 'passed' if complete else 'partial'
        actual = json.dumps({'plan_id':parameters['plan_id'],'request_id':request,
            'checkpoints':updates,'stopped_at':result.get('stopped_at'),
            'unexecuted_steps':result.get('unexecuted_steps',[])},ensure_ascii=False)
        patch = {'case_id':cid,'status':status,'actual':actual,'checkpoint_updates':updates,
                 'executed_at':datetime.now(timezone.utc).isoformat(),
                 'conclusion':'已按原检查点执行并读回实际结果' if complete else '本条验证未完成，保留已观察结果与未执行步骤',
                 'action_type':'','action_required':''}
        # Save before the next case, including failures and partial observations.
        # A transport failure stops this command. Operation IDs remain stable,
        # so a later explicit continuation reads prior results, not replayed UI.
        save_started = time.monotonic()
        try:
            saved = await broker.call('cases',lease_id=lid,cases=[patch],revision=record['revision'])
        except Exception as exc:
            return {'_command_state':'blocked','cases':results,'pending_save':patch,
                    'stopped_case_id':cid,'browser_result':result,'error_type':type(exc).__name__,
                    'resource_wait':{'end_turn':True,'reason':'case_save_failed'},
                    'instruction':'本条结果未确认保存，后续未执行；修复保存后按原 plan_id 续接，不更换 ID 重跑。'}
        record['revision']=saved['revision']
        results.append({'case_id':cid,'status':status,'state':'saved','revision':saved['revision'],
                        'browser_result':result,
                        'elapsed_seconds':round(time.monotonic()-started,3),
                        'save_seconds':round(time.monotonic()-save_started,3)})
        if result.get('unexecuted_steps') or result.get('_command_state') in {'blocked','unknown'} or any(p['status']=='failed' for p in updates):
            return {'_command_state':result.get('_command_state','completed'),'cases':results,
                    'stopped_case_id':cid,'resource_wait':{'end_turn':True,'reason':'case_difference'},
                    'instruction':'差异或未完成步骤已保存，停止本计划自动调用；核对具体差异后续接，其他独立计划不受影响。'}
    return {'_command_state':'completed','cases':results,'remaining_cases':[],
            'saved_cases':sum(c['state']=='saved' for c in results)}
