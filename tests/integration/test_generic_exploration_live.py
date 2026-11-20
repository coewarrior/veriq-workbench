"""Live local HTTP + real Chromium through the platform's original lease protocol.

Only synthetic accounts/data; no model calls, target business or notifications.
Run with -x: a failed assertion stops the acceptance run and closes its browsers.
"""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import pytest
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from api_test_tool.exploration_profiles import ADAPTER_SCHEMA
from api_test_tool.managed_browser import ManagedBrowser
from api_test_tool.managed_service import ManagedService
from api_test_tool.orchestration import Controller
from api_test_tool.web_storage import Store

STATIC = Path(__file__).parents[2] / 'api_test_tool' / 'static'


@contextmanager
def live_site(*, rotate=False, multi_entry=False):
    state = dict(item='initial-stock', writes=0, reads=0, logins=0, script_version=1, requests=[], write_received=threading.Event(), page_delay=0,
                 pending_read=threading.Event(), finish_read=threading.Event())
    entries = ['/stock','/catalog'] + (['/catalog/one','/catalog/two','/catalog/three'] if multi_entry else [])

    class Handler(BaseHTTPRequestHandler):
        def send(self, code, body, content_type='text/html; charset=utf-8', **headers):
            body = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            for key, value in headers.items(): self.send_header(key.replace('_', '-'), value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            state['requests'].append(('GET', self.path))
            if path == '/login':
                return self.send(200, '<form method="post" action="/login"><input name="username"><input name="password" type="password"><button>Login</button></form>')
            if 'fixture-session=' not in self.headers.get('Cookie', ''):
                return self.send(302, '', Location='/login')
            if path == '/app.js':
                return self.send(200, '''async function load() {
                  const value=await (await fetch('/api/items')).json();
                  const query=await (await fetch('/api/query', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'inventory'})})).json();
                  document.querySelector('#ready').textContent=value.item+' '+query.kind;
                } load();\n// version '''+str(state['script_version']), 'application/javascript')
            if path == '/api/items':
                if state.get('deny_items'):return self.send(401,'{}','application/json')
                if state.get('hold_items'):
                    state['pending_read'].set()
                    state['finish_read'].wait(30)
                state['reads'] += 1
                headers = {'Set_Cookie': 'fixture-session=rotated-'+str(state['reads'])+'; Path=/; HttpOnly'} if rotate else {}
                return self.send(200, json.dumps({'item': state['item']}), 'application/json', **headers)
            if path == '/api/poll':
                state['pending_read'].set()
                state['finish_read'].wait(30)
                try:return self.send(200,'{}','application/json')
                except (BrokenPipeError,ConnectionResetError):return
            if path in entries:
                time.sleep(state['page_delay'])
                return self.send(200, '<html><head><title>Inventory</title><script src="/app.js" defer></script></head><body>'
                    '<h1>'+path[1:]+'</h1>'+''.join('<a href="'+url+'">'+url+'</a>' for url in entries)+
                    ('<script>fetch("/api/poll")</script>' if state.get('background_poll') else '')+
                    '<p id="ready"></p><button id="submit" onclick="fetch(\'/api/submit\',{method:\'POST\',body:\'{}\'})">Submit change</button></body></html>')
            return self.send(404, 'not found')

        def do_POST(self):
            payload = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            state['requests'].append(('POST', self.path))
            if self.path == '/login':
                values = parse_qs(payload.decode())
                if values.get('username', [''])[0] not in {'fixture-one', 'fixture-two', 'fixture-three'} or values.get('password') != ['synthetic-only']:
                    return self.send(403, 'invalid fixture login')
                state['logins'] += 1
                return self.send(303, '', Location='/stock', Set_Cookie='fixture-session='+values['username'][0]+'; Path=/; HttpOnly')
            if self.path == '/api/query':
                if json.loads(payload).get('kind') == 'pending':
                    state['pending_read'].set()
                    state['finish_read'].wait(30)
                return self.send(200, json.dumps(json.loads(payload)), 'application/json')
            if self.path == '/api/pending-submit':
                state['pending_read'].set()
                state['finish_read'].wait(30)
                try:return self.send(200, '{}', 'application/json')
                except (BrokenPipeError,ConnectionResetError):return
            if self.path == '/api/submit':
                state['writes'] += 1
                state['write_received'].set()
                return self.send(200, '{}', 'application/json')
            return self.send(404, 'not found')

        def log_message(self, *args): pass

    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:'+str(http.server_port), state
    finally:
        state['finish_read'].set()
        http.shutdown(); http.server_close(); thread.join()


class Execution:
    def __init__(self, root, target, *, accounts=2, modules=3, browser_slots=12):
        self.browser_slots = browser_slots
        store = Store(root/'store'); session, _ = store.session(None)
        self.owner = session['id']
        project = store.create_project(self.owner, 'Live pool acceptance', 'fixture.md', 'Synthetic inventory exploration')
        store.update_project(self.owner, project['id'], {'test_kind':'ui', 'ui_target_url':target+'/login', 'task':{'goal':'Explore stock and catalog'}})
        self.controller = Controller(store)
        self.service = ManagedService(self.controller, STATIC)
        self.auth = {'owner':self.owner, 'host_id':'fixture-host'}
        for name in ['fixture-one', 'fixture-two', 'fixture-three'][:accounts]:
            self.controller.add_account(self.owner, {'project_id':project['id'], 'target':target, 'identity':name, 'credential':'synthetic-only'})
        self.controller.register_host(self.owner, 'fixture-host', enforcement_evidence={
            'network_isolation':'fixture', 'credential_isolation':'fixture', 'tool_gate':'fixture',
            'browser_context_isolation':'fixture', 'version':'fixture', 'simple_dispatch':1,
            'direct_execution':1, 'shared_exploration':1, 'automatic_exploration':ADAPTER_SCHEMA,
            'machine_id':'isolated-fixture'}, browser_slots=browser_slots, model_slots=1)
        self.task = self.controller.create_task(self.owner, {'project_id':project['id'], 'request_id':'live-pool',
            'goal':'Explore stock and catalog', 'execution_route':'local_browser', 'session_workflow':True,
            'modules':[{'key':str(i), 'title':'Inventory '+str(i), 'scope':'Stock and catalog', 'requirements':[]} for i in range(modules)]})['task_id']
        self.nodes = [n['id'] for n in self.controller.snapshot(self.owner)['nodes']]
        self.browser = ManagedBrowser(SimpleNamespace(call=self.host), root/'browser')
        self.identities = {}; self.sequence = 0

    def host(self, method, **args):
        return self.service.host_call(self.auth, method, args)

    async def claim(self, index):
        result = self.service.direct.call(self.owner, {'action':'claim', 'task_id':self.task,
            'node_id':self.nodes[index], 'holder_id':'fixture-worker-'+str(index)})
        lid = result.get('lease_id')
        if not lid: return result
        event = next(e for e in self.controller.pending_events(self.owner, 'fixture-host') if e['lease_id']==lid)
        self.controller.acknowledge_start(self.owner, event['id'], thread_id='fixture-worker-'+str(index), turn_id=lid)
        context = self.host('read', lease_id=lid)
        await self.browser.bind(context)
        self.identities[index] = (lid, context['accounts'][0]['id'])
        return context

    async def command(self, index, action, parameters, request_id=None):
        self.sequence += 1
        lid, aid = self.identities[index]
        request_id = request_id or 'action-'+str(self.sequence)
        args = {'action':'browser', 'holder_id':'fixture-worker-'+str(index), 'lease_id':lid,
                'account_id':aid, 'request_id':request_id, 'browser_action':action, 'parameters':parameters}
        receipt = self.service.direct.call(self.owner, args)
        if receipt['state']=='completed': return receipt['result']
        command = self.host('direct_poll', lease_id=lid)['command']
        try:
            result = await self.browser.operate(lid, aid, command['action'], command['parameters'], request_id)
        except BaseException:
            self.host('direct_result', lease_id=lid, request_id=request_id, state='failed', result={'error':'fixture action failed'})
            raise
        self.host('direct_result', lease_id=lid, request_id=request_id, state='completed', result=result)
        return self.service.direct.call(self.owner, {**args,'action':'result'})['result']

    async def login(self, index, target):
        lid, aid = self.identities[index]
        credentials = self.host('account_credentials', lease_id=lid, account_id=aid)
        await self.command(index, 'navigate', {'url':target+'/login?reason=expired&returnTo=%2Fstock'})
        await self.command(index, 'fill', {'selector':'input[name=username]','value':credentials['username']})
        await self.command(index, 'fill', {'selector':'input[type=password]','value':credentials['password']})
        await self.command(index, 'click', {'selector':'button'})
        return await self.command(index, 'wait', {'selector':'#ready:text-is("initial-stock inventory")'})

    async def release(self, index, outcome='completed'):
        lid, _ = self.identities[index]
        await self.browser.fence(lid)
        assert not self.browser._process_path(lid).exists()
        result = self.host('return_account', lease_id=lid, executor_stopped=True, browser_stopped=True, outcome=outcome)
        assert result['released']
        heartbeat = self.host('heartbeat', browser_slots=self.browser_slots, model_slots=1, settlement_acks=[lid])
        assert lid in heartbeat['settlement_acks']


@pytest.mark.parametrize('accounts,modules,browser_slots', [(2,3,12), (3,5,3)])
def test_generic_account_only_live_pool_and_atomic_handoff(tmp_path, accounts, modules, browser_slots):
    with live_site() as (target, site):
        async def run():
            execution = Execution(tmp_path, target, accounts=accounts, modules=modules, browser_slots=browser_slots)
            await execution.browser.start()
            try:
                normal = await execution.claim(0)
                assert normal['lease']['mode']=='exclusive' and not normal['lease'].get('exploration_bootstrap')
                bootstrap = await execution.claim(1)
                assert bootstrap['lease']['exploration_bootstrap'] and bootstrap['lease']['browser_units']==2
                assert bootstrap['shared_policy']['preparation']=='pending'
                assert not (await execution.claim(2)).get('lease_id')
                await execution.login(1, target)
                prepared = await execution.command(1, 'prepare_exploration', {'entry_urls':[target+'/stock',target+'/catalog']}, 'prepare-once')
                assert prepared['exploration_prepared'], prepared
                before = len(site['requests'])
                assert await execution.command(1, 'prepare_exploration', {'entry_urls':[target+'/stock',target+'/catalog']}, 'prepare-once') == prepared
                assert len(site['requests']) == before
                second = await execution.claim(2)
                lid, aid = execution.identities[1]
                assert second['lease']['mode']=='shared' and second['accounts'][0]['id']==aid
                assert second['lease']['context_id']!=bootstrap['lease']['context_id']
                assert sum(l['browser_units'] for l in execution.controller.snapshot(execution.owner)['leases']) <= browser_slots
                assert 'session_seed' not in second['shared_policy']
                assert all('session_seed' not in p for p in execution.controller.snapshot(execution.owner)['policies'])
                await execution.command(2, 'navigate', {'url':target+'/catalog'})
                observed = await execution.command(2, 'wait', {'selector':'#ready:text-is("initial-stock inventory")'})
                assert 'initial-stock inventory' in observed['snapshot'] and site['logins']==1
                # A changed service response must appear in both native browsers.
                site['item']='changed-live-stock'
                for index in (1,2):
                    await execution.command(index,'navigate',{'url':target+'/stock'})
                    observed=await execution.command(index,'wait',{'selector':'#ready:text-is("changed-live-stock inventory")'})
                    assert 'changed-live-stock inventory' in observed['snapshot']
                blocked=await execution.command(2,'click',{'selector':'#submit'})
                assert blocked.get('requires_exclusive') and blocked.get('continue_exploration') and site['writes']==0
                await execution.release(1)
                survivor=execution.identities[2][0]
                context_before=execution.browser.contexts[execution.identities[2]]
                result=execution.service.direct.call(execution.owner, {'action':'request_resources','holder_id':'fixture-worker-2',
                    'lease_id':survivor,'arguments':{'next_phase':'execution','checkpoint':{'designed_entries':['stock','catalog']}}})
                assert result['continued'] and result['mode']=='exclusive',result
                execution.browser._resource_receipt(survivor,result)
                assert execution.browser.contexts[execution.identities[2]] is context_before
                await execution.command(2,'click',{'selector':'#submit'})
                assert await asyncio.to_thread(site['write_received'].wait,5)
                assert site['writes']==1
                execution.controller.schedule()
                assert all('session_seed' not in p for p in execution.controller.snapshot(execution.owner)['policies'])
                await execution.release(2); await execution.release(0)
                assert not execution.controller.snapshot(execution.owner)['leases']
            finally:
                await execution.browser.close()
                assert not execution.browser.browsers and not execution.browser.probe_contexts
        asyncio.run(run())



def test_five_live_modules_with_one_exclusive_only_member(tmp_path):
    """Real direct claims arrive separately; three overflow browsers share."""
    with live_site() as (target, site):
        async def run():
            execution=Execution(tmp_path,target,accounts=3,modules=5,browser_slots=5)
            with execution.controller.transaction() as (_,state):
                state['nodes'][execution.nodes[2]]['exclusive_exploration']=True
            await execution.browser.start()
            try:
                ordinary=await execution.claim(0)
                preparing=await execution.claim(1)
                required_exclusive=await execution.claim(2)
                assert not ordinary['lease']['exploration_bootstrap']
                assert preparing['lease']['exploration_bootstrap']
                assert not required_exclusive['lease']['exploration_bootstrap']
                assert not (await execution.claim(3)).get('lease_id')
                assert not (await execution.claim(4)).get('lease_id')
                for index in (0,1,2):await execution.login(index,target)
                prepared=await execution.command(1,'prepare_exploration',{'entry_urls':[target+'/stock',target+'/catalog']})
                assert prepared['exploration_prepared'],prepared
                for index in (3,4):
                    shared=await execution.claim(index)
                    assert shared['lease']['mode']=='shared'
                    assert shared['accounts'][0]['id']==execution.identities[1][1]
                leases=execution.controller.snapshot(execution.owner)['leases']
                assert len(leases)==5
                assert sum(l['mode']=='exclusive' for l in leases)==2
                assert sum(l['mode']=='shared' for l in leases)==3
                assert len({l['context_id'] for l in leases})==5
                site['item']='five-live-browsers'
                await asyncio.gather(*(execution.command(index,'navigate',{'url':target+('/catalog' if index%2 else '/stock')})
                                       for index in range(5)))
                views=await asyncio.gather(*(execution.command(index,'wait',{'selector':'#ready:text-is("five-live-browsers inventory")'})
                                              for index in range(5)))
                assert all('five-live-browsers inventory' in view['snapshot'] for view in views)
                assert site['logins']==3 and site['writes']==0
                await execution.release(1);await execution.release(3)
                lid,_=execution.identities[4]
                page=execution.browser.pages[execution.identities[4]]
                result=execution.service.direct.call(execution.owner,{'action':'request_resources','holder_id':'fixture-worker-4',
                    'lease_id':lid,'arguments':{'next_phase':'execution','checkpoint':{'designed_entries':['stock','catalog']}}})
                assert result['continued'] and result['mode']=='exclusive',result
                execution.browser._resource_receipt(lid,result)
                assert execution.browser.pages[execution.identities[4]] is page
                for index in (4,2,0):await execution.release(index)
                assert not execution.controller.snapshot(execution.owner)['leases']
            finally:await execution.browser.close()
        asyncio.run(run())

def test_five_real_entries_can_finish_without_single_action_deadline(tmp_path):
    """Reproduce the real five-module batch exceeding the old 75-second cap."""
    from api_test_tool.exploration_learning import command_timeout
    with live_site(multi_entry=True) as (target, site):
        async def run():
            execution=Execution(tmp_path,target,accounts=1,modules=2)
            await execution.browser.start()
            async def heartbeat():
                while True:
                    execution.host('heartbeat',browser_slots=12,model_slots=1)
                    await asyncio.sleep(3)
            pulse=asyncio.create_task(heartbeat())
            try:
                await execution.claim(0)
                await execution.login(0,target)
                parameters={'entry_urls':[target+path for path in ['/stock','/catalog','/catalog/one','/catalog/two','/catalog/three']]}
                site['page_delay']=7
                started=time.monotonic()
                prepared=await asyncio.wait_for(execution.command(0,'prepare_exploration',parameters),
                    timeout=command_timeout('prepare_exploration',parameters))
                assert time.monotonic()-started > 75
                assert prepared['exploration_prepared'],prepared
                assert len(prepared['accepted_entries'])==5,prepared['entry_checks']
                assert site['writes']==0 and not execution.browser.probe_contexts
                site['page_delay']=0
                shared=await execution.claim(1)
                assert shared['lease']['mode']=='shared'
                await execution.release(1);await execution.release(0)
            finally:
                pulse.cancel();await asyncio.gather(pulse,return_exceptions=True)
                await execution.browser.close()
        asyncio.run(run())


@pytest.mark.parametrize('pending_write,old_document', [(False,False),(False,True),(True,False),(True,True)])
def test_source_drain_cancels_old_reads_but_preserves_unfinished_writes(tmp_path, pending_write, old_document):
    with live_site() as (target, site):
        async def run():
            execution=Execution(tmp_path,target,accounts=1,modules=2)
            await execution.browser.start()
            try:
                await execution.claim(0)
                await execution.login(0,target)
                page=execution.browser.pages[execution.identities[0]]
                browser=execution.browser.browsers[execution.identities[0]]
                await page.evaluate("void fetch('/api/pending-submit',{method:'POST',body:'{}',keepalive:true})" if pending_write
                                    else "void fetch('/api/poll?private=do-not-return',{keepalive:true})")
                assert await asyncio.to_thread(site['pending_read'].wait,5)
                if old_document:
                    await execution.command(0,'navigate',{'url':target+'/catalog'})
                    await execution.command(0,'wait',{'selector':'#ready:text-is("initial-stock inventory")'})
                result=await execution.command(0,'prepare_exploration',{'entry_urls':[target+'/stock']},'unfinished-source')
                if pending_write:
                    assert result['exploration_prepared'] is False and result['requires_exclusive'],result
                    assert result['preparation_stage']=='source_requests'
                    assert result['verification_error']=='TimeoutError'
                    assert result['pending_requests']==[{'method':'POST','path':'/api/pending-submit','resource_type':'fetch'}]
                    assert not (await execution.claim(1)).get('lease_id')
                    assert execution.browser.pages[execution.identities[0]] is page and not page.is_closed()
                else:
                    assert result['exploration_prepared'],result
                    assert result['source_context_restarted'] and page.is_closed()
                    assert execution.browser.browsers[execution.identities[0]] is browser
                    assert not execution.browser.inflight[execution.identities[0][0]]
                    assert not any('/api/poll' in rule['path'] for rule in execution.controller.snapshot(execution.owner)['policies'][0]['rules'])
                    assert (await execution.claim(1))['lease']['mode']=='shared'
                    await execution.release(1)
                assert 'private' not in json.dumps(result)
                assert not execution.browser.probe_contexts and not site['writes']
                site['finish_read'].set()
                await execution.release(0)
            finally:
                site['finish_read'].set()
                await execution.browser.close()
        asyncio.run(run())



@pytest.mark.parametrize('late_request', ['verified_read','unknown_read','unknown_write','changed_read','source_mismatch'])
def test_final_handoff_drains_only_unverified_requests(tmp_path, monkeypatch, late_request):
    from api_test_tool import exploration_learning as learning
    with live_site() as (target,site):
        async def run():
            execution=Execution(tmp_path,target,accounts=1,modules=2)
            await execution.browser.start()
            triggered=False
            original=learning.export_session
            restart=execution.browser.restart_preparation_context
            async def restart_with_mismatch(*args):
                context,page=await restart(*args)
                if late_request=='source_mismatch':
                    await context.add_init_script("document.addEventListener('DOMContentLoaded',()=>document.querySelector('h1').textContent='wrong-source-view')")
                return context,page
            execution.browser.restart_preparation_context=restart_with_mismatch
            async def export(context,page):
                nonlocal triggered
                result=await original(context,page)
                lid=execution.identities[0][0]
                if not triggered and context is execution.browser.probe_contexts.get(lid):
                    triggered=True
                    source=execution.browser.pages[execution.identities[0]]
                    if late_request=='verified_read':
                        site['hold_items']=True
                        await source.evaluate("void fetch('/api/items')")
                    elif late_request in {'unknown_read','changed_read','source_mismatch'}:
                        if late_request=='changed_read':site['item']='changed-during-handoff'
                        await source.evaluate("void fetch('/api/poll',{keepalive:true})")
                    else:
                        await source.evaluate("void fetch('/api/query',{method:'POST',body:JSON.stringify({kind:'pending'}),keepalive:true})")
                    assert await asyncio.to_thread(site['pending_read'].wait,5)
                return result
            monkeypatch.setattr(learning,'export_session',export)
            try:
                await execution.claim(0);await execution.login(0,target)
                page=execution.browser.pages[execution.identities[0]]
                result=await execution.command(0,'prepare_exploration',{'entry_urls':[target+'/stock']})
                assert triggered
                if late_request=='source_mismatch':
                    assert result['exploration_prepared'] is False and result['preparation_stage']=='verified_source_restore',result
                    assert result['verification_detail']=='最终共享规则下源页面与同时核验页面不同'
                    assert not (await execution.claim(1)).get('lease_id')
                elif late_request=='unknown_write':
                    assert result['exploration_prepared'] is False and result['preparation_stage']=='verified_requests',result
                    assert not page.is_closed()
                    assert not (await execution.claim(1)).get('lease_id')
                else:
                    assert result['exploration_prepared'],result
                    if late_request=='verified_read':
                        assert not page.is_closed()
                        assert execution.browser.inflight[execution.identities[0][0]]
                    else:
                        assert page.is_closed() and result['source_context_restarted']
                    assert (await execution.claim(1))['lease']['mode']=='shared'
                    await execution.release(1)
                site['finish_read'].set()
                await execution.release(0)
            finally:
                site['finish_read'].set();await execution.browser.close()
        asyncio.run(run())

def test_rotating_session_stays_exclusive_and_releases_probe_capacity(tmp_path):
    with live_site(rotate=True) as (target, site):
        async def run():
            execution=Execution(tmp_path,target,accounts=1,modules=2)
            await execution.browser.start()
            try:
                first=await execution.claim(0)
                assert first['lease']['exploration_bootstrap']
                await execution.login(0,target)
                result=await execution.command(0,'prepare_exploration',{'entry_urls':[target+'/stock']})
                assert result['exploration_prepared'] is False and result['requires_exclusive']
                lease=execution.controller.snapshot(execution.owner)['leases'][0]
                assert lease['mode']=='exclusive' and not lease['exploration_bootstrap'] and lease['browser_units']==1
                assert not execution.browser.probe_contexts
                assert not (await execution.claim(1)).get('lease_id')
                assert site['writes']==0
                assert not execution.controller.snapshot(execution.owner)['nodes'][0].get('exclusive_exploration')
                task=execution.controller.snapshot(execution.owner)['tasks'][0]
                execution.controller.control(execution.owner,execution.task,{'action':'stop',
                    'revision':task['revision'],'request_id':'stop-failed-preparation'})
                await execution.release(0)
                snapshot=execution.controller.snapshot(execution.owner)
                task=snapshot['tasks'][0]
                execution.controller.control(execution.owner,execution.task,{'action':'resume',
                    'revision':task['revision'],'request_id':'retry-preparation','instruction':'Resume live verification after platform repair'})
                resumed=await execution.claim(0)
                assert resumed['lease']['exploration_bootstrap'],resumed
                await execution.release(0)
            finally:await execution.browser.close()
        asyncio.run(run())


def test_changed_script_closes_shared_batch_without_sending_unknown_write(tmp_path):
    with live_site() as (target, site):
        async def run():
            execution=Execution(tmp_path,target,accounts=1,modules=2)
            await execution.browser.start()
            try:
                await execution.claim(0)
                await execution.login(0,target)
                prepared=await execution.command(0,'prepare_exploration',{'entry_urls':[target+'/stock']})
                assert prepared['exploration_prepared']
                second=await execution.claim(1)
                assert second['lease']['mode']=='shared'
                fault_seen=asyncio.Event()
                original=execution.browser.mark_exploration_fault
                def observe_fault(lid,reason):
                    original(lid,reason)
                    fault_seen.set()
                execution.browser.mark_exploration_fault=observe_fault
                site['script_version']=2
                await execution.command(1,'navigate',{'url':target+'/stock'})
                await asyncio.wait_for(fault_seen.wait(),5)
                assert all(execution.browser.active[lid].get('exploration_fault')
                           for lid,_ in execution.identities.values())
                blocked=await execution.command(1,'click',{'selector':'#submit'})
                assert blocked['requires_exclusive'] and blocked['continue_exploration']
                assert site['writes']==0
                execution.host('heartbeat',browser_slots=12,model_slots=1,
                               exploration_faults=execution.browser.exploration_faults)
                snapshot=execution.controller.snapshot(execution.owner)
                policy=next(p for p in snapshot['policies'] if p['id']==second['lease']['policy_id'])
                assert not policy['enabled'] and policy['preparation']=='failed'
                assert all(l.get('exploration_fault') for l in snapshot['leases'])
                await execution.release(1); await execution.release(0)
                assert not execution.controller.snapshot(execution.owner)['leases']
            finally:await execution.browser.close()
        asyncio.run(run())


def test_shared_auth_fault_identifies_actual_response_without_query(tmp_path):
    with live_site() as (target,site):
        async def run():
            execution=Execution(tmp_path,target,accounts=1,modules=2)
            await execution.browser.start()
            try:
                await execution.claim(0);await execution.login(0,target)
                prepared=await execution.command(0,'prepare_exploration',{'entry_urls':[target+'/stock']})
                assert prepared['exploration_prepared']
                assert prepared['session_cookie_expires_at'] is None
                await execution.claim(1)
                site['deny_items']=True
                seen=asyncio.Event();original=execution.browser.mark_exploration_fault
                def observe(lid,reason):
                    original(lid,reason);seen.set()
                execution.browser.mark_exploration_fault=observe
                await execution.command(1,'navigate',{'url':target+'/stock'})
                await asyncio.wait_for(seen.wait(),5)
                reason=next(iter(execution.browser.exploration_faults.values()))
                assert '401 GET /api/items' in reason
                assert '/stock' not in reason
                await execution.release(1);await execution.release(0)
            finally:await execution.browser.close()
        asyncio.run(run())


def test_live_preparation_does_not_wait_for_background_poll(tmp_path):
    with live_site() as (target,site):
        async def run():
            execution=Execution(tmp_path,target,accounts=1,modules=2)
            await execution.browser.start()
            try:
                await execution.claim(0);await execution.login(0,target)
                site['background_poll']=True
                prepared=await execution.command(0,'prepare_exploration',{'entry_urls':[target+'/stock',target+'/catalog']})
                assert prepared['exploration_prepared'],prepared
                assert not site['finish_read'].is_set()
                assert prepared['accepted_entries']==[target+'/stock',target+'/catalog']
                assert all(rule['path']!='/api/poll' for rule in execution.browser.policy_documents[execution.identities[0]]['rules'])
                assert (await execution.claim(1))['lease']['mode']=='shared'
                await execution.command(1,'navigate',{'url':target+'/catalog'})
                view=await execution.command(1,'wait',{'selector':'#ready:text-is("initial-stock inventory")'})
                assert 'initial-stock inventory' in view['snapshot']
                assert site['writes']==0
                await execution.release(1);await execution.release(0)
            finally:
                site['finish_read'].set();await execution.browser.close()
        asyncio.run(run())
