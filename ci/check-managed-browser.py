"""Opt-in controlled browser acceptance using only an isolated localhost fixture.
Requires runner extras and installed Chromium; never calls a model or business system.
Run with: python ci/check-managed-browser.py
"""
import asyncio,json,tempfile,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from api_test_tool.managed_browser import ManagedBrowser
from api_test_tool.managed_service import ManagedService
from api_test_tool.orchestration import Controller
from api_test_tool.web_storage import Store
import api_test_tool
hits={'read':0,'write':0}
class Page(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  hits['read']+=1
  body=b'<html><title>Local connection check</title><body><h1>Local check</h1><form action="/write" method="POST"><label>Draft<input name="draft"></label><button>Save</button></form></body></html>'
  self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_POST(self):
  hits['write']+=1;self.send_response(200);self.end_headers()
server=ThreadingHTTPServer(('127.0.0.1',0),Page);threading.Thread(target=server.serve_forever,daemon=True).start()
target=f'http://127.0.0.1:{server.server_port}'
async def check(root):
 store=Store(root/'store');session,_=store.session(None);owner=session['id'];project=store.create_project(owner,'Mac connection fixture','fixture.md','Local synthetic fixture, no business environment.')
 ctl=Controller(store);svc=ManagedService(ctl,Path(api_test_tool.__file__).parent/'static');hid='local-check'
 account=ctl.add_account(owner,dict(project_id=project['id'],target=target,environment='local',tenant='fixture',identity='fixture',roles=['reader'],pool='exploration',credential=''))
 aid=account['id'];ctl.verify_account(owner,aid,identity='fixture',tenant='fixture')
 policy=svc.save_policy(owner,{'account_id':aid,'project_id':project['id'],'version':'local-read-v1','evidence':'This temporary server only renders a fixed form on GET; POST must never reach it.','rules':[{'origin':target,'path':'/fixture','method':'GET','effect':'verified_read'}]})
 ctl.register_host(owner,hid,enforcement_evidence=dict(network_isolation='local fixture',credential_isolation='local fixture',tool_gate='local fixture',browser_context_isolation='local fixture',version='local fixture'),browser_slots=2,model_slots=2)
 task=ctl.create_task(owner,dict(project_id=project['id'],request_id='local-fixture',goal='Local connection validation',modules=[dict(key=x,title=x,requirements=[dict(target=target,environment='local',tenant='fixture',role='reader')]) for x in ('first','second')]))
 ctl.schedule();events=ctl.pending_events(owner,hid);assert len(events)==2
 class API:
  def call(self,method,/,**args):return svc.host_call({'owner':owner,'host_id':hid},method,args)
 api=API();browser=ManagedBrowser(api,root/'browser',headed=False)
 await browser.start();(root/'browser'/f'auth-{aid}.json').write_text(json.dumps({'cookies':[],'origins':[]}))
 try:
  leases=[]
  for e in events:
   ctl.acknowledge_start(owner,e['id'],thread_id='fixture-'+e['id'],turn_id='fixture-turn')
   c=api.call('read',lease_id=e['lease_id']);assert c['lease']['mode']=='shared';await browser.bind(c);leases.append(e['lease_id'])
  for lid in leases:
   r=await browser.operate(lid,aid,'navigate',{'url':target+'/fixture'},lid+'-open');assert 'Local check' in r['snapshot']
  before=hits['read'];r=await browser.operate(leases[0],aid,'navigate',{'url':target+'/fixture'},leases[0]+'-open');assert r['replayed'] is False and hits['read']==before
  await browser.operate(leases[0],aid,'fill',{'selector':'input','value':'only-first'},'fill-first')
  other=await browser.operate(leases[1],aid,'snapshot',{},'snapshot-second');assert 'only-first' not in other['snapshot']
  try:r=await browser.operate(leases[0],aid,'click',{'selector':'button'},'denied-write')
  except Exception:pass
  assert hits['write']==0
  ctl.control(owner,task['task_id'],{'action':'stop','request_id':'fixture-stop','revision':task['revision']})
  try:await browser.operate(leases[1],aid,'snapshot',{},'after-stop')
  except Exception:pass
  else:raise AssertionError('revoked lease accepted an action')
  print(json.dumps({'shared_contexts':2,'independent_drafts':True,'duplicate_not_replayed':True,'unapproved_writes_sent':hits['write'],'revoked_action_blocked':True,'paid_model_calls':0}))
 finally:
  await browser.close()
try:
 with tempfile.TemporaryDirectory(prefix='mac-browser-acceptance-') as d:asyncio.run(check(Path(d)))
finally:server.shutdown();server.server_close()
