import copy
import json

import pytest

from api_test_tool.model_planning import generate_plan
from api_test_tool.models import ModelAPIError, _extract
from test_web_generation import contract, proposal


def response(cases):
    return {"text": json.dumps({"schema_version": "1.0", "cases": cases}),
            "model": "offline", "protocol": "openai_chat", "usage": {"output_tokens": 10}}


def design(oid, n):
    return {"id": str(n), "title": f"独立场景 {n}", "operation_id": oid,
            "design": {"category": "逆向", "inputs": f"参数 {n}", "procedure": "发送请求并检查业务结果",
                       "expected": "符合文档", "basis": "原文要求"}}


def single_contract(contract):
    contract = copy.deepcopy(contract)
    contract['operations'] = {'get_health': contract['operations']['get_health']}
    return contract


def test_batches_never_drop_designs_when_model_omits_or_miscompiles(contract):
    contract = single_contract(contract)
    checkpoints, calls = [], []
    def model(system, prompt):
        p = json.loads(prompt);calls.append(p['phase'])
        if p['phase'] == 'design':
            return response([design('get_health', n) for n in range(25)])
        batch = p['supplied_cases']
        if len(batch) > 1:
            # Lost IDs cause smaller independent compilation batches.
            return response([])
        case = copy.deepcopy(batch[0])
        case['design']['execution_gap'] = '需要补齐前置数据'
        case['design']['inputs'] = '编译模型试图改写原始设计'
        if case['id'].endswith('005'):
            case['untrusted_field'] = 'invalid'
        return response([case])
    result = generate_plan(contract, '完整原文', '', model, checkpoint=checkpoints.append)
    assert len(result['cases']) == 25
    assert len({c['id'] for c in result['cases']}) == 25
    assert all(c['design']['inputs'].startswith('参数 ') for c in result['cases'])
    assert '不支持的字段' in result['cases'][4]['design']['execution_gap']
    assert len(checkpoints[0]['cases']) == 25 and not checkpoints[0]['compiled']
    assert result['generation']['compiled_count'] == 0
    assert result['generation']['design_count'] == 25
    assert calls.count('design') == 1


def test_resume_does_not_regenerate_completed_designs_or_batches(contract):
    contract = single_contract(contract);saved=[];calls=[]
    def model(system, prompt):
        p=json.loads(prompt);calls.append(p['phase'])
        if p['phase']=='design':
            return response([design('get_health', n) for n in range(9)])
        if len(p['supplied_cases'])==1:
            raise ModelAPIError('连接中断','connection_error')
        return response(p['supplied_cases'])
    with pytest.raises(ModelAPIError):
        generate_plan(contract, '原文', '', model, checkpoint=saved.append)
    assert calls == ['design','compile','compile']
    assert len(saved[-1]['compiled'])==8
    resumed=[]
    def recover(system,prompt):
        p=json.loads(prompt);resumed.append(p)
        return response(p['supplied_cases'])
    result=generate_plan(contract,'原文','',recover,state=saved[-1])
    assert len(resumed)==1 and len(resumed[0]['supplied_cases'])==1
    assert len(result['cases'])==9


def test_only_length_failure_splits_not_refusal_or_auth(contract):
    contract=single_contract(contract)
    for limited,expected_calls in [(True,4),(False,2)]:
        calls=[]
        def model(system,prompt):
            p=json.loads(prompt);calls.append(p)
            if p['phase']=='design':return response([design('get_health',n) for n in range(2)])
            if len(p['supplied_cases'])>1:
                raise ModelAPIError('上游响应未完成','incomplete_output',output_limited=limited)
            return response(p['supplied_cases'])
        if limited:
            assert len(generate_plan(contract,'原文','',model)['cases'])==2
        else:
            with pytest.raises(ModelAPIError):generate_plan(contract,'原文','',model)
        assert len(calls)==expected_calls


@pytest.mark.parametrize('reason,limited',[('length',True),('content_filter',False),('tool_calls',False)])
def test_provider_reason_controls_split(reason,limited):
    with pytest.raises(ModelAPIError) as error:
        _extract({'choices':[{'finish_reason':reason,'message':{'content':'partial'}}]},'openai_chat')
    assert error.value.output_limited is limited


def test_supplement_can_find_no_gap_and_sees_existing_requests(contract):
    contract=single_contract(contract);seen=[]
    existing=[{'id':'USER-1','steps':[{'request':{'method':'GET','path':'/health'},'assertions':[{'kind':'status','expected':200}]}]}]
    def model(system,prompt):
        payload=json.loads(prompt);seen.append(payload)
        return response([])
    result=generate_plan(contract,'原文','',model,existing_cases=existing)
    assert result['cases']==[] and seen[0]['existing_cases']==existing
    assert '已有用例' in seen[0]['addition_policy']
