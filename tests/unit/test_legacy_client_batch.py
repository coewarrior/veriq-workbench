"""Only the requested old-host compatibility and interruption boundaries."""
from pathlib import Path
import importlib.util
import pytest
from api_test_tool.direct_wait import direct_call_and_wait


@pytest.fixture(params=['installed', 'standalone'])
def engine(request):
    if request.param == 'installed': return direct_call_and_wait
    path = Path(__file__).parents[2]/'api_test_tool/static/api-test-client.py'
    spec = importlib.util.spec_from_file_location('legacy_batch_client', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.direct_call_and_wait


def arguments():
    return dict(action='browser', browser_action='batch', holder_id='holder', lease_id='lease', request_id='batch',
        parameters={'steps':[{'id':'fill','action':'fill','parameters':{'selector':'input','value':'test'}},
                             {'id':'read','action':'snapshot','parameters':{}}]})


def test_old_host_executes_once_and_keeps_full_receipts(engine,tmp_path):
    sent=[]
    def send(args):
        sent.append(args)
        if args['action']=='context': return {'execution_host':{'browser_batch':False}}
        return {'state':'completed','result':{'url':'https://fixture.test','text':args['browser_action']}}
    result=engine(send,arguments(),batch_root=tmp_path)
    assert result['state']=='completed' and result['batch_transport']=='compatible'
    assert len(result['steps'])==2 and not result['unexecuted_steps']
    assert [s['browser_action'] for s in sent if s['action']=='browser']==['fill','snapshot']
    assert all(s['browser_action']!='batch' for s in sent if s['action']=='browser')
    assert engine(send,arguments(),batch_root=tmp_path)['state']=='completed'
    assert len(sent)==3
    assert next(tmp_path.glob('*.json')).stat().st_mode & 0o777 == 0o600
    changed=arguments();changed['parameters']['steps'][0]['parameters']['value']='other'
    with pytest.raises(ValueError,match='不能改变'): engine(send,changed,batch_root=tmp_path)


def test_lost_response_queries_original_command_and_never_resubmits(engine,tmp_path):
    calls=[]; failed=[False]
    def send(args):
        calls.append(args.copy())
        if args['action']=='context': return {'execution_host':{'browser_batch':False}}
        if args['action']=='browser' and not failed[0]:
            failed[0]=True; raise OSError('lost')
        return {'state':'completed','result':{'url':'https://fixture.test'}}
    first=engine(send,arguments(),batch_root=tmp_path)
    assert first['state']=='unknown' and first['unexecuted_steps']==['read']
    resumed=engine(send,first['client_wait']['resume_arguments'],batch_root=tmp_path)
    assert resumed['state']=='completed'
    assert [c['action'] for c in calls]==['context','browser','result','browser']
    assert calls[1]['request_id']==calls[2]['request_id']
    assert 'parameters' not in first['client_wait']['resume_arguments']


def test_blocked_or_revoked_batch_does_not_send_remaining_steps(engine,tmp_path):
    calls=[]
    def send(args):
        calls.append(args)
        if args['action']=='context': return {'execution_host':{'browser_batch':False}}
        return {'state':'blocked','result':{'requires_exclusive':True}}
    result=engine(send,arguments(),batch_root=tmp_path)
    assert result['stopped_at']=='fill' and result['unexecuted_steps']==['read']
    assert result['requires_exclusive'] is True
    assert len(calls)==2
    assert engine(send,result['client_wait']['resume_arguments'],batch_root=tmp_path)['state']=='blocked'
    assert len(calls)==2


def test_native_batch_remains_native_and_old_host_prevalidates(engine,tmp_path):
    calls=[]
    def native(args):
        calls.append(args)
        return {'execution_host':{'browser_batch':True}} if args['action']=='context' else {'state':'completed'}
    assert engine(native,arguments(),batch_root=tmp_path)['state']=='completed'
    assert calls[1]['browser_action']=='batch'
    second=arguments();second['request_id']='second-batch'
    assert engine(native,second,batch_root=tmp_path)['state']=='completed'
    assert sum(c['action']=='context' for c in calls)==1
    args=arguments();args['parameters']['steps'].append({'id':'assert','action':'check','parameters':{}})
    args['lease_id']='different-old-host-lease'
    sent=[]
    def old(values): sent.append(values); return {'execution_host':{'browser_batch':False}}
    with pytest.raises(ValueError,match='不能省略断言'): engine(old,args,batch_root=tmp_path)
    assert len(sent)==1 and sent[0]['action']=='context'
