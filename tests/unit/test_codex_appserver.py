import os
import sys
import pytest
from api_test_tool.codex_appserver import AppServer, AppServerError


@pytest.fixture
def fake_server(tmp_path):
    script=tmp_path/'server.py'
    script.write_text('''import sys,json
for line in sys.stdin:
 p=json.loads(line)
 if 'id' not in p: continue
 method=p.get('method')
 if method=='initialize': r={'userAgent':'fake'}
 elif method=='thread/start':
  assert p['params']['sandbox']=='read-only'
  assert p['params']['approvalPolicy']=='never'
  r={'thread':{'id':'thread-1'}}
 elif method=='thread/resume': r={'thread':{'id':p['params']['threadId']}}
 elif method=='turn/start': r={'turn':{'id':'turn-1','status':'inProgress'}}
 elif method=='turn/interrupt': r={}
 elif method=='thread/read': r={'thread':{'id':'thread-1','turns':[]}}
 else: r={}
 print(json.dumps({'id':p['id'],'result':r}),flush=True)
''')
    return tmp_path,script


def test_managed_protocol_lifecycle_without_model_calls(fake_server):
    cwd,script=fake_server
    server=AppServer([sys.executable,str(script)],cwd=cwd,env=dict(os.environ),timeout=2)
    try:
        tid=server.start_thread(cwd=cwd,tools=[])
        assert tid=='thread-1'
        assert server.start_turn(tid,'test')=='turn-1'
        assert server.interrupt(tid,'turn-1')=={}
        assert server.resume_thread(tid)['thread']['id']==tid
        assert server.read_thread(tid)['thread']['turns']==[]
        with pytest.raises(AppServerError):
            server.call('command/exec',{'command':['unsafe']})
    finally:
        server.close()
    assert server.process.poll() is not None


def test_timeout_reports_unknown_instead_of_replaying(tmp_path):
    script=tmp_path/'silent.py'
    script.write_text('import time; time.sleep(30)')
    with pytest.raises(AppServerError):
        AppServer([sys.executable,str(script)],cwd=tmp_path,env=dict(os.environ),timeout=.05)
