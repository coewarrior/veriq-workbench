"""Playwright broker. Browser/cookies stay outside the Codex sandbox.

Each task owns one account context; Chromium uses its normal network stack.
There is no arbitrary evaluate, shell, CDP, URL fetch or cookie export tool.
"""
from __future__ import annotations
import asyncio
import base64
import json
import mimetypes
import shutil
import re
from pathlib import Path
from uuid import uuid4
import time
from urllib.parse import urlsplit, urljoin
from .browser_policy import BrowserPolicy, ExclusiveRequired


class ManagedBrowser:
    def __init__(self, api, root, *, headed=False):
        self.api=api; self.root=Path(root); self.headed=headed
        self.bind_lock=asyncio.Lock()
        self.contexts={}; self.browsers={}; self.pages={}; self.active={}; self.pending={}; self.denied={}; self.requests={}; self.network_tasks=set(); self.redirects={}; self.captures={}
        self.login_contexts={}; self.login_pages={}; self.login_attempts={}; self.login_messages={}; self.playwright=None
        self.policies={}
        self.shared_writes={}
        self.exploration_observations={}
        self.private_sessions=set()
        self.session_credentials={}
        self.policy_documents={}
        self.bound_accounts={}
        self.prepared_local=set()
        self.login_associated={}
        self.learning=set()
        self.probe_contexts={}
        self.exploration_faults={}
        self.inflight={}
        self.network_idle={}
        self.network_changed={}
        self.source_draining=set()
        self.navigation_history={}
        self.last_operation_timing={}

    async def start(self):
        from playwright.async_api import async_playwright
        self.playwright=await async_playwright().start()
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)

    async def call(self, method, /, **args):
        return await asyncio.to_thread(self.api.call,method,**args)

    async def check_runtime(self):
        # Fail before registering capacity if Chromium cannot start. No business
        # navigation, credentials or model turn are needed for this check.
        browser=await self.playwright.chromium.launch(headless=True)
        try:
            context=await browser.new_context(service_workers='block',accept_downloads=False)
            await context.route('**/*',lambda route:route.abort())
            await context.route_web_socket('**/*',lambda ws:ws.close())
            await context.new_page()
            await context.close()
        finally:await browser.close()

    async def sync_accounts(self, generations):
        """Drop cached cookies/profiles after edits or permanent account removal."""
        path = self.root/'account-generations.json'
        previous = json.loads(path.read_text()) if path.exists() else {}
        known = set(previous) | {p.stem[5:] for p in self.root.glob('auth-*.json')} | {p.name[6:] for p in self.root.glob('login-*')}
        for aid in known:
            if not re.fullmatch(r'[a-f0-9]{32}', aid):continue
            if aid in generations and previous.get(aid, '') == generations[aid]:continue
            ctx = self.login_contexts.pop(aid, None)
            if ctx:await ctx.close()
            self.login_pages.pop(aid, None);self.login_attempts.pop(aid, None)
            (self.root/('auth-'+aid+'.json')).unlink(missing_ok=True)
            for directory in [self.root/('login-'+aid), *self.root.glob('*-'+aid)]:
                if directory.is_dir() and not directory.is_symlink():shutil.rmtree(directory)
        from .managed_runner import save
        if previous != generations or not path.exists():save(path, generations)

    async def bind(self, context):
        async with self.bind_lock:
            await self._bind(context)

    async def _bind(self, context):
        lease=context['lease'];lid=lease['id'];self.active[lid]=lease
        for account in context['accounts']:
            key=(lid,account['id'])
            if key in self.contexts:continue
            guarded=lease.get('mode','exclusive')=='shared' or lease.get('exploration_bootstrap')
            contract=context.get('shared_policy') or {}
            self.policy_documents[key]=contract
            self.bound_accounts[key]=account
            policy=BrowserPolicy(account,contract,lease['context_id']) if guarded else None
            if policy:self.policies[key]=policy
            # The account is exclusive. Chromium handles ordinary networking,
            # redirects, streaming and login dependencies without a proxy ledger.
            import psutil
            before={p.pid for p in psutil.Process().children(recursive=True)}
            try:
                browser=await self.playwright.chromium.launch(headless=not self.headed)
            finally:
                self._remember_processes(lid,before)
            self.browsers[key]=browser
            auth=self.root/('auth-'+account['id']+'.json')
            legacy=self.root/(lease['context_id']+'-'+account['id'])/'storage.json'
            saved=auth if auth.exists() else legacy
            independent=bool(policy and policy.builtin and contract.get('session_strategy')=='independent_login')
            copied=bool(policy and policy.builtin and contract.get('session_strategy')=='verified_storage_copy')
            if independent or copied:self.private_sessions.add(key)
            options={'service_workers':'block'} if guarded else {}
            storage={'storage_state':str(saved)} if saved.exists() and not independent else {}
            if copied and lease.get('mode')=='shared':
                prepared=await self.call('exploration_session',lease_id=lid,account_id=account['id'])
                from .exploration_learning import browser_storage
                storage={'storage_state':browser_storage(prepared['storage_state'])}
            if storage:self.login_associated[lid]=True
            ctx=await browser.new_context(**storage,accept_downloads=True,**options)
            self.contexts[key]=ctx
            if copied and lease.get('mode')=='shared':
                from .exploration_learning import install_session
                await install_session(ctx,prepared['storage_state'])
            await self._configure_context(ctx,lease,account,contract,copied,independent)

    async def _configure_context(self,ctx,lease,account,contract,copied,independent):
        lid=lease['id'];key=(lid,account['id'])
        guarded=lease.get('mode','exclusive')=='shared' or lease.get('exploration_bootstrap')
        if copied:
            self.inflight[lid]=set()
            self.network_idle[lid]=asyncio.Event();self.network_idle[lid].set()
            self.network_changed[lid]=asyncio.Event()
            def request_started(request,*,lease_id=lid):
                if lease_id not in self.inflight:return
                self.inflight[lease_id].add(request);self.network_idle[lease_id].clear()
                self.network_changed[lease_id].set()
            def request_ended(request,*,lease_id=lid):
                if lease_id not in self.inflight:return
                self.inflight[lease_id].discard(request)
                self.network_changed[lease_id].set()
                if not self.inflight[lease_id]:self.network_idle[lease_id].set()
            ctx.on('request',request_started)
            ctx.on('requestfinished',request_ended)
            ctx.on('requestfailed',request_ended)
            async def session_response(response,*,lease_id=lid,account_id=account['id'],target=contract['target_origin']):
                from .exploration_learning import candidate,rule_key,signature
                if self.active.get(lease_id,{}).get('mode')!='shared':return
                request=response.request
                rule=candidate(request.url,request.method,request.post_data,request.resource_type,target)
                if not rule:return
                if response.status in {401,403}:
                    reason=('共享会话的实时请求失去访问权限（'+str(response.status)+' '+request.method+' '+
                            urlsplit(request.url).path+'），平台已停止本批次共享')
                    self.mark_exploration_fault(lease_id,reason)
                expected=self.policy_documents.get((lease_id,account_id),{}).get('asset_fingerprints',{}).get(signature(rule_key(rule).encode()))
                if expected and request.resource_type in {'script','stylesheet'}:
                    try:changed=signature(await response.body())!=expected
                    except Exception:changed=True
                    if changed and self.active.get(lease_id,{}).get('mode')=='shared':
                        self.mark_exploration_fault(lease_id,'页面脚本或样式版本已变化，平台已停止本批次共享并安排重新核验')
            ctx.on('response',session_response)
        if independent:
            async def observed(response,*,lease_id=lid,checks=contract.get('observations',()),profile=contract.get('automatic_profile')):
                # Inspect only responses already requested by the real page.
                # Never persist tokens, response payloads or account data.
                from .exploration_profiles import observation_matches
                from .browser_policy import origin
                if lease_id not in self.active or self.active[lease_id].get('revoked'):return
                path=urlsplit(response.url).path
                try:target=origin(response.url)
                except ValueError:return
                matched=[check for check in checks if check['origin']==target and check['path']==path
                         and check['method']==response.request.method and check['status']==response.status]
                if not matched:return
                try:payload=await response.json()
                except Exception:return
                observation=self.exploration_observations.setdefault(lease_id,{'profile':profile})
                for check in matched:observation[check['key']]=observation_matches(check,payload)
            ctx.on('response',observed)
        if guarded:
            async def guard(route,request,*,lease_id=lid,account_id=account['id']):
                active=self.active.get(lease_id,{})
                if active.get('revoked',True) or lease_id in self.source_draining:await route.abort();return
                if active.get('mode')=='exclusive' and not active.get('exploration_bootstrap'):await route.continue_();return
                try:
                    contract=self.policies[(lease_id,account_id)]
                    document=self.policy_documents[(lease_id,account_id)]
                    from .exploration_learning import PROFILE, candidate
                    if (active.get('exploration_bootstrap') and document.get('automatic_profile')==PROFILE
                            and lease_id not in self.prepared_local):
                        if (lease_id in self.learning and not candidate(request.url,request.method,request.post_data,
                                                                      request.resource_type,document['target_origin'])):
                            await route.abort();return
                        await route.continue_();return
                    if active.get('exploration_fault'):
                        raise ExclusiveRequired(active['exploration_fault'])
                    rule=contract.match_request(request.url,request.method,request.post_data)
                    effect=rule['effect']
                    if effect=='isolated_session' and rule.get('credential_fields'):
                        # Wrong-password/lockout cases affect the shared account.
                        # Only its configured normal login is session-isolated.
                        # Resolve once at login, never a per-action remote gate.
                        if lease_id not in self.session_credentials:
                            credentials=await self.call('account_credentials',lease_id=lease_id,account_id=account_id)
                            self.session_credentials[lease_id]={k:credentials.get(k,'') for k in ('username','password')}
                        try:payload=json.loads(request.post_data or '{}')
                        except ValueError:
                            from urllib.parse import parse_qs
                            fields=parse_qs(request.post_data or '',keep_blank_values=True)
                            payload={k:v[0] if len(v)==1 else v for k,v in fields.items()}
                        for field,credential in rule['credential_fields'].items():
                            value=self.session_credentials[lease_id].get(credential)
                            if not value or payload.get(field)!=value:
                                raise ExclusiveRequired('非当前配置凭据的登录场景需要独占账号')
                except (PermissionError,ValueError) as exc:
                    self.denied[lease_id]=request.method+' '+urlsplit(request.url).path+': '+str(exc)
                    await route.abort();return
                if effect in {'isolated_write','isolated_session','prepared_read'} or (effect=='observed_read' and request.method!='GET'):
                    self.shared_writes[lease_id]=self.shared_writes.get(lease_id,0)+1
                await route.continue_()
            await ctx.route('**/*',guard)
            async def guard_socket(socket,*,lease_id=lid):
                active=self.active.get(lease_id,{})
                if not active.get('revoked',True) and active.get('mode')=='exclusive' and not active.get('exploration_bootstrap'):
                    socket.connect_to_server();return
                self.denied[lease_id]='共享探索中的双向连接尚未经核验，需独占资源继续'
                await socket.close()
            await ctx.route_web_socket('**/*',guard_socket)
        ctx.set_default_navigation_timeout(60000)
        page=await ctx.new_page()
        self.pages[key]=page

    async def restart_preparation_context(self,lid,aid,storage):
        """Dispose login-era keepalive traffic before copying a live session.

        Called only after unresolved non-read traffic has finished. The source
        context must really close before its replacement is created, so this
        never exceeds the scheduler's existing preparation reservation.
        """
        from .exploration_learning import PROFILE,browser_storage,install_session
        key=(lid,aid);lease=self.active[lid];contract=self.policy_documents[key]
        if (lease.get('mode')!='exclusive' or not lease.get('exploration_bootstrap')
                or contract.get('automatic_profile')!=PROFILE):
            raise RuntimeError('仅独占实时准备可重建已收敛的登录上下文')
        try:
            await self.contexts[key].close()
            # Context disposal is the actual cancellation boundary even when an old
            # document's keepalive request emits no page-level terminal event.
            self.contexts.pop(key,None);self.pages.pop(key,None)
            context=await self.browsers[key].new_context(storage_state=browser_storage(storage),
                                                       service_workers='block',accept_downloads=True)
            self.contexts[key]=context
            await install_session(context,storage)
            await self._configure_context(context,lease,self.bound_accounts[key],contract,True,False)
            return context,self.pages[key]
        except BaseException:
            await self.fence(lid)
            raise RuntimeError('源登录上下文重建退出未确认，已停止租约浏览器，原操作需核实') from None

    async def operate(self, lid, aid, action, p, operation_id=None, *, begin_receipt=None):
        from .orchestration import digest
        operation_id=operation_id or uuid4().hex
        if action=='batch':
            from .browser_batch import execute
            return await execute(self,lid,aid,p,operation_id)
        started=time.monotonic()
        receipt=begin_receipt if begin_receipt is not None else await self.call('operation_begin',lease_id=lid,operation_id=operation_id,
                                action=action,hash=digest([aid,action,p]))
        begin_seconds=time.monotonic()-started
        self._resource_receipt(lid,receipt)
        if not receipt.get('execute'):
            if receipt.get('state')=='confirmed':return receipt.get('result',{})
            raise RuntimeError('原操作结果未知或未发送；先核实原现场，不自动重放')
        self._sent=getattr(self,'_sent',set());self._sent.discard(operation_id)
        writes_before=self.shared_writes.get(lid,0)
        try:
            result=await self._operate(lid,aid,action,p,operation_id)
        except BaseException as exc:
            denied=self.denied.pop(lid,None) or (str(exc) if isinstance(exc,ExclusiveRequired) else '')
            sent=operation_id in self._sent and action not in {'snapshot','screenshot','tabs','wait','check'}
            if denied and action!='prepare_exploration' and self.shared_writes.get(lid,0)==writes_before:sent=False
            try:
                await self.call('operation_complete',lease_id=lid,operation_id=operation_id,state='unknown' if sent else 'not_sent',result={'requires_exclusive':True,'reason':denied} if denied else {})
                exc.operation_state='unknown' if sent else 'not_sent'
            except Exception:pass
            if denied:raise ExclusiveRequired(denied) from None
            raise
        result.setdefault('timing',{})['operation_begin_seconds']=round(begin_seconds,6)
        result['timing']['begin_piggybacked']=begin_receipt is not None
        verification=result.pop('_exploration_policy',None)
        seed=result.pop('_exploration_seed',None)
        if verification:
            account=self.bound_accounts[(lid,aid)]
            document={**self.policy_documents[(lid,aid)],**verification}
            self.policy_documents[(lid,aid)]=document
            self.policies[(lid,aid)]=BrowserPolicy(account,document,self.active[lid]['context_id'])
            self.prepared_local.add(lid)
        complete_started=time.monotonic()
        receipt=await self.call('operation_complete',lease_id=lid,operation_id=operation_id,state='confirmed',result=result,
                                exploration_observation=self.exploration_observations.get(lid),
                                exploration_verification=verification,exploration_seed=seed)
        self.last_operation_timing[lid]={'operation_id':operation_id,
            'operation_complete_seconds':round(time.monotonic()-complete_started,6)}
        self._resource_receipt(lid,receipt)
        if verification and not receipt.get('exploration_prepared'):
            result.update(exploration_prepared=False,requires_exclusive=True,
                          reason='核验完成时资源或控制状态已经变化，平台未开放共享；沿原检查点续接')
        self._sent.discard(operation_id)
        return result

    def _resource_receipt(self,lid,receipt):
        if lid not in self.active:return
        active=self.active[lid]
        if receipt.get('resource_version',1)<active.get('resource_version',1):return
        for field in ('mode','exploration_bootstrap','resource_version'):
            if field in receipt:active[field]=receipt[field]

    def mark_exploration_fault(self,lid,reason):
        self.exploration_faults[lid]=reason
        policy_id=self.active.get(lid,{}).get('policy_id')
        for active in self.active.values():
            if active.get('mode')=='shared' and active.get('policy_id')==policy_id:
                active['exploration_fault']=reason

    async def _operate(self, lid, aid, action, p, operation_id=None):
        key=(lid,aid)
        if key not in self.pages or self.active.get(lid,{}).get('revoked',True):
            raise RuntimeError('会话未绑定或已撤权')
        if action not in {'navigate','click','fill','press','select','wait','back','upload','snapshot','screenshot','tabs','switch_tab','prepare_exploration','check'}:
            raise ValueError('未知受控操作')
        if not isinstance(p,dict):raise ValueError('parameters 必须是对象')
        if action=='prepare_exploration':
            from .exploration_learning import prepare
            return await prepare(self,lid,aid,p.get('entry_urls'),operation_id)
        if action=='upload' and p.get('asset_id'):
            # Fetch only the current task's saved file, preserving exact fixture
            # bytes. The model never needs a host path or to regenerate samples.
            asset=await self.call('asset_content',lease_id=lid,asset_id=p['asset_id'])
            media=asset.get('content_type')
            if not media or media=='application/octet-stream':
                media=mimetypes.guess_type(asset['filename'])[0] or 'application/octet-stream'
            p={**p,**asset,'content_type':p.get('content_type') or media}
        required={'navigate':['url'],'click':['selector'],'fill':['selector','value'],'press':['selector','key'],'select':['selector','value'],'wait':['selector'],'upload':['selector','filename','content_base64'],'switch_tab':['page_index']}
        if any(k not in p for k in required.get(action,[])):raise ValueError(action+' 参数需要：'+', '.join(required.get(action,[]))+('；已有测试文件也可用 selector + asset_id' if action=='upload' else ''))
        if action=='switch_tab' and (type(p['page_index']) is not int or not 0<=p['page_index']<len(self.contexts[key].pages)):raise ValueError('页面不属于当前账号上下文')
        if action=='navigate':
            url=urlsplit(p['url'])
            if url.scheme not in {'http','https'} or not url.hostname or url.username or url.password:
                raise ValueError('请使用不含内嵌凭据的 HTTP(S) 网页地址')
        if action=='upload':base64.b64decode(p['content_base64'],validate=True)
        if action=='switch_tab':
            index=p.get('page_index')
            if type(index) is not int or not 0<=index<len(self.contexts[key].pages):raise ValueError('页面不属于当前账号上下文')
            self.pages[key]=self.contexts[key].pages[index]
        if p.get('response','full') not in {'full','summary'}:raise ValueError('response 只支持 full 或 summary')
        page=self.pages[key];upload_info=None
        action_started=time.monotonic()
        assertion=None
        locator=page.locator(p['selector']) if 'selector' in p else None
        if action=='click':
            # A failed actionability check sends no click. Keep a missing or
            # ambiguous locator from isolating the entire account lease.
            await locator.click(trial=True)
        self._sent.add(operation_id)
        if action=='navigate':
            await page.goto(p['url'],wait_until='domcontentloaded')
        elif action=='click':await locator.click()
        elif action=='fill':
            await locator.fill(p['value'])
            from .exploration_learning import PROFILE
            if (self.active[lid].get('exploration_bootstrap')
                    and self.policy_documents.get(key,{}).get('automatic_profile')==PROFILE
                    and await locator.get_attribute('type')=='password'):
                if lid not in self.session_credentials:
                    credentials=await self.call('account_credentials',lease_id=lid,account_id=aid)
                    self.session_credentials[lid]={k:credentials.get(k,'') for k in ('username','password')}
                self.login_associated[lid]=bool(self.session_credentials[lid]['password']
                                                and p['value']==self.session_credentials[lid]['password'])
        elif action=='press':await locator.press(p['key'])
        elif action=='select':await locator.select_option(p['value'])
        elif action=='wait':await locator.wait_for(state=p.get('state','visible'))
        elif action=='check':
            expected=p.get('expect')
            if not locator or not isinstance(expected,dict) or not expected or set(expected)-{'visible','enabled','text','value','count'}:
                raise ValueError('check 需要 selector 和 expect（visible/enabled/text/value/count）')
            observed={}
            for field in expected:
                if field=='visible':observed[field]=await locator.is_visible()
                elif field=='enabled':observed[field]=await locator.is_enabled()
                elif field=='text':observed[field]=await locator.inner_text()
                elif field=='value':
                    if await locator.get_attribute('type')=='password':raise ValueError('密码值不能进入断言回执')
                    observed[field]=await locator.input_value()
                else:observed[field]=await locator.count()
            assertion={'assertion_passed':all(observed[k]==v for k,v in expected.items()),'observed':observed,'expected':expected}
            assertion['business_failure']=not assertion['assertion_passed']
        elif action=='back':await page.go_back(wait_until='domcontentloaded')
        elif action=='upload':
            # Bytes, never arbitrary host filesystem paths.
            content=base64.b64decode(p['content_base64'],validate=True)
            upload_info={'filename':Path(p['filename']).name,'content_type':p.get('content_type','application/octet-stream'),'size':len(content)}
            await locator.set_input_files({'name':upload_info['filename'],'mimeType':upload_info['content_type'],'buffer':content})
        elif action not in {'snapshot','screenshot','tabs','switch_tab'}:raise ValueError('不支持此浏览器动作')
        action_seconds=time.monotonic()-action_started
        observation_started=time.monotonic()
        full=p.get('response','full')=='full' or action in {'snapshot','screenshot','tabs','switch_tab'}
        preparing=bool(self.active[lid].get('exploration_bootstrap'))
        result={'url':page.url}
        if full or preparing:result['title']=await page.title()
        if upload_info:result['submitted_file']=upload_info
        if assertion:result.update(assertion)
        if action=='screenshot':
            content=base64.b64encode(await page.screenshot(mask=[page.locator('input[type=password]')])).decode()
            capture=uuid4().hex;self.captures[capture]={'lease_id':lid,'content_base64':content}
            result.update(capture_id=capture,_image_url='data:image/png;base64,'+content)
        elif p.get('response','full')=='full' or action=='snapshot' or p.get('snapshot_selector'):
            result['snapshot']=await page.locator(p.get('snapshot_selector','body')).aria_snapshot()
        else:
            result['observation_omitted']=True
        if full:result['tabs']=[{'page_index':i,'url':p.url} for i,p in enumerate(self.contexts[key].pages)]
        result['timing']={'browser_action_seconds':round(action_seconds,6),
                          'observation_seconds':round(time.monotonic()-observation_started,6)}
        guard_started=time.monotonic()
        from .exploration_learning import PROFILE, links, visible_password
        document=self.policy_documents.get(key,{})
        if self.active[lid].get('exploration_bootstrap') and document.get('automatic_profile')==PROFILE:
            from .exploration_learning import candidate
            if candidate(page.url,'GET',None,'document',document['target_origin']):
                self.navigation_history.setdefault(lid,{})[page.url]=result['title']
            navigation={item['url']:item['label'] for item in await links(page,document['target_origin'])}
            navigation.update(self.navigation_history.get(lid,{}))
            result['navigation_links']=[{'url':url,'label':label} for url,label in navigation.items()]
            result['exploration_preparation']='登录完成后选择本轮所有模块的真实入口，以 prepare_exploration 和 entry_urls 一次交给平台核验'
        elif self.active[lid].get('mode')=='shared' and document.get('automatic_profile')==PROFILE:
            if await visible_password(page):
                reason='共享浏览器回到登录界面，平台已停止本批次共享'
                self.mark_exploration_fault(lid,reason)
            if self.active[lid].get('exploration_fault'):self.denied[lid]=self.active[lid]['exploration_fault']
        if self.denied.get(lid):
            # A blocked background request must not hide the actual page or end
            # every safe exploration branch. It is never reported as a pass.
            reason=self.denied.pop(lid)
            result.update(requires_exclusive=True,blocked_request_sent=False,business_failure=False,
                          continue_exploration=True,reason=reason,
                          exclusive_branches=[{'reason':reason,'operation_id':operation_id}],
                          exploration_next_action='保存受阻分支，继续已核验页面和本地交互；仅当其余共享探索完成或当前必要分支确需独占时申请资源。未知分支不代表整个模块探索完成。')
        result['timing']['session_guard_seconds']=round(time.monotonic()-guard_started,6)
        return result

    def _process_path(self,lid):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,160}',lid):raise ValueError('执行标识无效')
        return self.root/('processes-'+lid+'.json')

    def _remember_processes(self,lid,before):
        import psutil
        from .managed_runner import save
        path=self._process_path(lid);records=json.loads(path.read_text()) if path.exists() else []
        for process in psutil.Process().children(recursive=True):
            try:
                if process.pid not in before and any(x in process.name().lower() for x in ('chrom','headless')):
                    records.append({'pid':process.pid,'created':process.create_time()})
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        if records:self.root.mkdir(parents=True,exist_ok=True);save(path,records)

    def _stop_processes(self,lid):
        import psutil
        path=self._process_path(lid)
        if not path.exists():return
        processes={}
        for item in json.loads(path.read_text()):
            try:
                process=psutil.Process(item['pid'])
                if process.create_time()!=item['created']:continue
                processes[process.pid]=process
                for child in process.children(recursive=True):processes[child.pid]=child
            except psutil.NoSuchProcess:pass
        for process in processes.values():
            try:process.terminate()
            except psutil.NoSuchProcess:pass
        _,alive=psutil.wait_procs(list(processes.values()),timeout=5)
        for process in alive:
            try:process.kill()
            except psutil.NoSuchProcess:pass
        _,alive=psutil.wait_procs(alive,timeout=5)
        if alive:raise RuntimeError('本任务浏览器进程尚未退出，账号保持隔离')
        path.unlink(missing_ok=True)

    def register_auxiliary(self,lid,cid,channel):
        """Adopt only this helper's verified local process and its children."""
        import os
        import psutil
        from .managed_runner import save
        directory=Path(channel['directory']).resolve()
        binding=json.loads((directory/'lease-binding.json').read_text())
        if binding.get('lease_id')!=lid or binding.get('channel_id')!=cid or binding.get('pid')!=channel['pid']:
            raise RuntimeError('辅助浏览器归属核对失败，保留账号等待核实')
        if directory.stat().st_uid!=os.getuid():raise RuntimeError('辅助浏览器不属于本执行用户')
        closed=directory/'closed.json'
        # Registration can commit after its HTTP caller timed out. The helper
        # writes this only after browser.close resolves, before retrying its ACK.
        try:process=psutil.Process(channel['pid'])
        except psutil.NoSuchProcess:
            closed=directory/'closed.json'
            if closed.exists() and json.loads(closed.read_text()).get('browserClosed') is True:return True
            process_file=self._process_path(lid)
            if process_file.exists() and any(r.get('channel_id')==cid for r in json.loads(process_file.read_text())):
                # Previously adopted descendants remain identifiable after their
                # parent exits. Fence will check those creation times as well.
                return False
            raise RuntimeError('辅助进程丢失且没有浏览器退出证明，保留账号等待核实')
        command=process.cmdline()
        # macOS /tmp aliases /private/tmp. Compare the same filesystem path on
        # both sides; a valid helper must not revoke its live parent lease.
        owns_directory=any(Path(x).is_absolute() and Path(x).resolve()==directory for x in command)
        if not owns_directory or not any(Path(x).name=='browser-session.cjs' for x in command):
            raise RuntimeError('辅助浏览器进程已变化，不能按旧 PID 停止')
        if abs(process.create_time()-binding['process_started'])>2:
            raise RuntimeError('辅助浏览器 PID 已复用，不能停止其他任务')
        if closed.exists() and json.loads(closed.read_text()).get('browserClosed') is True:
            return True
        file=self._process_path(lid)
        records=json.loads(file.read_text()) if file.exists() else []
        for child in [process,*process.children(recursive=True)]:
            try:identity={'pid':child.pid,'created':child.create_time(),'channel_id':cid}
            except psutil.NoSuchProcess:continue
            if identity not in records:records.append(identity)
        save(file,records)
        return False

    def _suspend_auxiliaries(self,lid):
        import psutil
        path=self._process_path(lid)
        if not path.exists():return
        processes={}
        for item in json.loads(path.read_text()):
            if not item.get('channel_id'):continue
            try:
                process=psutil.Process(item['pid'])
                if process.create_time()!=item['created']:continue
                processes[process.pid]=process
                for child in process.children(recursive=True):processes[child.pid]=child
            except psutil.NoSuchProcess:pass
        for process in processes.values():
            try:process.suspend()
            except psutil.NoSuchProcess:pass

    async def fence(self, lid, *, close=True):
        if lid in self.active:self.active[lid]['revoked']=True
        if not close:
            # Retaining an auxiliary page must also stop its already-running
            # script and sockets, not just reject the next local HTTP request.
            await asyncio.to_thread(self._suspend_auxiliaries,lid)
            return True
        for key,browser in list(self.browsers.items()):
            if key[0]!=lid:continue
            ctx=self.contexts.get(key)
            if ctx:
                try:
                    auth=self.root/('auth-'+key[1]+'.json')
                    if key not in self.private_sessions:
                        await asyncio.wait_for(ctx.storage_state(path=str(auth)),timeout=5);auth.chmod(0o600)
                except Exception:pass
                try:await asyncio.wait_for(ctx.close(),timeout=5)
                except Exception:pass
            # Only remove the allocation after Chromium has actually exited.
            try:await asyncio.wait_for(browser.close(),timeout=10)
            except Exception:pass
            self.browsers.pop(key,None);self.contexts.pop(key,None);self.pages.pop(key,None)
            self.policies.pop(key,None)
            self.policy_documents.pop(key,None)
            self.bound_accounts.pop(key,None)
            self.private_sessions.discard(key)
        await asyncio.to_thread(self._stop_processes,lid)
        self.active.pop(lid,None)
        self.exploration_observations.pop(lid,None)
        self.session_credentials.pop(lid,None)
        self.login_associated.pop(lid,None)
        self.learning.discard(lid)
        self.probe_contexts.pop(lid,None)
        self.exploration_faults.pop(lid,None)
        self.prepared_local.discard(lid)
        self.inflight.pop(lid,None)
        self.network_idle.pop(lid,None)
        self.network_changed.pop(lid,None)
        self.source_draining.discard(lid)
        self.navigation_history.pop(lid,None)
        self.captures={k:v for k,v in self.captures.items() if v['lease_id']!=lid}
        return True

    def validate_console(self,item):
        target=item['target'];lid=target.get('lease_id');aid=target['account_id']
        ctx=self.contexts.get((lid,aid)) if lid else self.login_contexts.get(aid)
        if not ctx or not ctx.pages:raise RuntimeError('原浏览器现场尚未打开或已结束，请刷新任务状态')
        p=item.get('parameters',{})
        if item['action']!='view':
            frame=getattr(self,'console_frames',{}).get(item['session_id'])
            if not frame or p.get('frame_id')!=frame['id'] or frame['page'].is_closed() or frame['page'] not in ctx.pages or frame['page'].url!=frame['url']:
                raise RuntimeError('页面已经变化，请查看最新现场后操作')
            if item['action'] in {'click','drag'}:
                for suffix in ('','2') if item['action']=='drag' else ('',):
                    x,y=p.get('x'+suffix),p.get('y'+suffix)
                    if type(x) not in {int,float} or type(y) not in {int,float} or not 0<=x<frame['width'] or not 0<=y<frame['height']:raise ValueError('坐标不在当前现场内')
            if item['action']=='key' and p.get('key') not in {'Enter','Tab','Shift+Tab','Escape','Backspace','Delete','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Control+A','Meta+A','Space'}:raise ValueError('不支持此按键')
            if item['action']=='text' and not isinstance(p.get('text'),str):raise ValueError('输入文本无效')
        return ctx

    async def console(self,item,auth):
        ctx=self.validate_console(item);p=item.get('parameters',{});action=item['action'];sid=item['session_id']
        if not hasattr(self,'console_frames'):self.console_frames={}
        if action=='view':
            index=p.get('page_index',len(ctx.pages)-1)
            if type(index) is not int or not 0<=index<len(ctx.pages):raise ValueError('标签已关闭')
            page=ctx.pages[index]
            size=page.viewport_size or {'width':1280,'height':720}
            frame=uuid4().hex
            content=base64.b64encode(await page.screenshot(type='jpeg',quality=65,mask=[page.locator('input[type=password]')],timeout=10000)).decode()
            self.console_frames[sid]={'id':frame,'page':page,'url':page.url,**size}
            # Other sessions only hold ephemeral Page references, no screenshots.
            self.console_frames={k:v for k,v in self.console_frames.items() if not v['page'].is_closed()}
            return {'image':'data:image/jpeg;base64,'+content,'frame_id':frame,'url':page.url,**size,'editable':auth['editable'],
                'page_index':index,'tabs':[{'page_index':i,'url':x.url} for i,x in enumerate(ctx.pages)]}
        page=self.console_frames[sid]['page']
        if not auth['editable']:raise RuntimeError('当前现场只读')
        lid=item['target'].get('lease_id')
        if lid:
            if lid not in self.active:raise RuntimeError('原租约浏览器不存在，禁止重建人工现场')
            self.active[lid]['revoked']=False
        if action=='click':await page.mouse.click(p['x'],p['y'])
        elif action=='drag':
            await page.mouse.move(p['x'],p['y']);await page.mouse.down()
            try:await page.mouse.move(p['x2'],p['y2'],steps=15)
            finally:await page.mouse.up()
        elif action=='scroll':await page.mouse.wheel(max(-3000,min(3000,float(p.get('dx',0)))),max(-3000,min(3000,float(p.get('dy',0)))))
        elif action=='text':await page.keyboard.insert_text(p['text'])
        elif action=='key':await page.keyboard.press(p['key'])
        elif action=='navigate':
            target=urlsplit(p.get('url',''))
            if target.scheme not in {'http','https'} or target.username or target.password or f'{target.scheme}://{target.netloc.lower()}' not in auth['allowed_origins']:raise ValueError('地址越出已授权登录域')
            await page.goto(p['url'],wait_until='domcontentloaded',timeout=15000)
        else:raise ValueError('不支持此人工操作')
        if lid:
            for _ in range(20):
                destination=self.redirects.pop(lid,None)
                if not destination:break
                await page.goto(destination,wait_until='domcontentloaded',timeout=15000)
        return {'performed':True,'message':'操作已送达原浏览器，请根据页面结果核实业务状态'}

    async def close(self):
        for lid in list(self.active):await self.fence(lid)
        for ctx in self.login_contexts.values():await ctx.close()
        if self.playwright:await self.playwright.stop()
