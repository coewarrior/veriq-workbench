"""Batch contracts; fixtures only, no browser or business service."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from api_test_tool.browser_batch import execute, operation_id


def plan():
    return {'steps':[
        {'id':'fill','action':'fill','parameters':{'selector':'input','value':'sample'}},
        {'id':'verify','action':'check','parameters':{'selector':'input','expect':{'value':'sample'}}},
        {'id':'submit','action':'click','parameters':{'selector':'button'}}]}


def test_batch_preserves_assertions_and_stops_before_submit():
    broker=SimpleNamespace(operate=AsyncMock(side_effect=[{'url':'https://fixture.test'},
        {'assertion_passed':False,'business_failure':True,'observed':{'value':'unexpected'}}]))
    result=asyncio.run(execute(broker,'lease','account',plan(),'request'))
    assert result['stopped_at']=='verify' and result['unexecuted_steps']==['submit']
    assert result['business_failure'] is True and broker.operate.await_count==2
    assert result['steps'][1]['result']['observed']=={'value':'unexpected'}
    assert result['steps'][0]['operation_id']==operation_id('request','fill')
    assert broker.operate.await_args_list[0].args[3]['response']=='summary'


def test_batch_unknown_step_is_not_replayed_or_followed():
    broker=SimpleNamespace(operate=AsyncMock(side_effect=TimeoutError()))
    result=asyncio.run(execute(broker,'lease','account',plan(),'request'))
    assert result['_command_state']=='unknown'
    assert result['unexecuted_steps']==['verify','submit']
    assert broker.operate.await_count==1


def test_batch_rejects_duplicate_ids_before_any_action():
    value=plan();value['steps'][1]['id']='fill'
    broker=SimpleNamespace(operate=AsyncMock())
    with pytest.raises(ValueError):asyncio.run(execute(broker,'lease','account',value,'request'))
    broker.operate.assert_not_awaited()


def test_batch_keeps_last_observation_and_stable_step_ids():
    broker=SimpleNamespace(operate=AsyncMock(return_value={'url':'https://fixture.test'}))
    result=asyncio.run(execute(broker,'lease','account',plan(),'request'))
    assert len(result['steps'])==3 and result['unexecuted_steps']==[]
    assert broker.operate.await_args_list[-1].args[3]['response']=='full'
    assert len({r['operation_id'] for r in result['steps']})==3


def test_batch_cancellation_does_not_start_another_step():
    broker=SimpleNamespace(operate=AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(execute(broker,'lease','account',plan(),'request'))
    assert broker.operate.await_count==1
