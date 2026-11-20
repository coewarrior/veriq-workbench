"""Owner-paired Mode-A execution host. No model has the host bearer or browser profile."""
from __future__ import annotations
import argparse
import asyncio
import fcntl
import getpass
import json
import os
from pathlib import Path
import queue
import signal
import time
import threading
from uuid import uuid4
from urllib.parse import urlsplit

import requests
from .managed_sandbox import create_sandbox
from .managed_browser import ManagedBrowser
from .codex_appserver import ThreadNotFound


def save(path, value):
    path=Path(path);tmp=path.with_suffix('.new')
    with open(tmp,'w',opener=lambda p,f:os.open(p,f,0o600)) as f:
        json.dump(value,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

class HostAPI:
    def __init__(self, base, token=''):
        p=urlsplit(base)
        if p.scheme not in {'http','https'} or not p.hostname or p.username or p.password or p.query or p.fragment:
            raise ValueError('平台地址无效')
        self.base=base.rstrip('/');self.token=token;self.connections=threading.local()
    def post(self,path,data):
        # No automatic redirect or mutation retry; a lost response is reconciled.
        if not hasattr(self.connections,'session'):self.connections.session=requests.Session()
        r=self.connections.session.post(self.base+path,json=data,headers={'Authorization':'Bearer '+self.token} if self.token else {},timeout=(10,35),allow_redirects=False)
        if not 200<=r.status_code<300:
            detail=''
            try:
                payload=r.json()
                if isinstance(payload,dict) and isinstance(payload.get('detail'),str):detail=payload['detail'][:800]
            except ValueError:pass
            # Return the platform's validation explanation to the task so it can
            # correct its record. Never echo request data, bearer or HTML bodies.
            raise RuntimeError(f'平台调用失败 HTTP {r.status_code}'+('；'+detail if detail else ''))
        return r.json()
    def call(self,method,/,**args):return self.post('/api/managed-host/call',{'action':method,'arguments':args})

TOOLS=[{'name':name,'description':description,'inputSchema':schema} for name,description,schema in [
    ('account_credentials','读取当前分配账号的登录地址、账号和密码，用于由你在受控浏览器自行登录。共享探索须沿已核验会话兼容策略。不得写入聊天说明、用例、报告或截图。',
     {'type':'object','properties':{'account_id':{'type':'string'}},'required':['account_id']}),
    ('browser','通过已绑定账号的受控浏览器操作。parameters.selector 为 Playwright CSS 选择器；快照中的按钮名称可能来自 aria-label，图标按钮应使用 button[aria-label="名称"]，不要把可访问名称当成文本内容。upload 使用 parameters={selector,asset_id} 直接上传 context.record.assets 中的原文件；也支持 {selector,filename,content_base64,content_type} 上传字节。navigate 传 url；fill/select 传 selector,value；press 传 selector,key；wait 必须传 selector；click 返回后应核实页面变化，首次页面加载须等待交互初始化。页面由浏览器正常联网；业务提交后核对结果再决定是否重试。通用探索准备阶段正常登录后，从实际 navigation_links 选择本轮模块入口，以 prepare_exploration 和 parameters.entry_urls 一次提交；平台实际核验后自动开放共享，执行者不提交自批规则。batch 使用 steps=[{id,action,parameters}] 合并已知顺序动作；沿用已有业务授权，每步保存回执，异常或断言失败停止余下步骤，未知结果不重放。check 使用 selector 与 expect（visible/enabled/text/value/count），先等待目标状态再断言。中间动作默认摘要，最后动作完整观察；不减少用例、断言或证据。operation_id 为同一业务动作稳定标识；响应丢失沿用 ID 查询，未知操作先读取现场核实，用 test_record reconcile 提交 operation_id、operation_state=confirmed/not_sent、reason，不能盲重试。',
     {'type':'object','properties':{'account_id':{'type':'string'},'action':{'type':'string','enum':['navigate','snapshot','screenshot','click','fill','press','select','wait','back','upload','tabs','switch_tab','prepare_exploration','batch','check']},'parameters':{'type':'object','properties':{**{k:{'type':'string'} for k in ('selector','url','value','key','state','asset_id','filename','content_base64','content_type')},'entry_urls':{'type':'array','items':{'type':'string'}},'steps':{'type':'array','items':{'type':'object'}},'expect':{'type':'object'},'response':{'type':'string','enum':['full','summary']},'snapshot_selector':{'type':'string'}}},'operation_id':{'type':'string'}},'required':['account_id','action','parameters']}),
    ('test_record','保存用例、检查点、证据和报告。record 读取版本；cases 必须传当前 revision。既有完整测试规范和字段见上下文。',
     {'type':'object','properties':{'action':{'type':'string','enum':['record','cases','assets','publish','reference','requirements','save_requirements','dependency','reconcile','fixture','shared_policy']},'arguments':{'type':'object'}},'required':['action','arguments']}),
    ('request_resources','仅共享探索需要独占，或真实下一阶段资源集合改变时申请。普通独占测试不调用。保留原检查点；continued=true沿用原浏览器，release_required=true以原checkpoint安全交还后排队，不重复探索或重放未知业务动作。',
     {'type':'object','properties':{'exclusive_exploration':{'type':'boolean'},'next_phase':{'type':'string','enum':['exploration','execution','report']},'requirements':{'type':'array','items':{'type':'object'}},'account_ids':{'type':'array','items':{'type':'string'}},'locks':{'type':'array','items':{'type':'string'}},'checkpoint':{'type':'object'}}}),
    ('checkpoint','保存任务进度。普通独占无需例行阶段交接。完成任务用 finish=true,completed=true；确实受阻用 finish=true,wait_reason；主动交还账号排队续跑用 finish=true。children 用于拆分任务。平台回收安全资源；未知提交或明确保留现场如实记录隔离原因，不阻止提交最终报告。',
     {'type':'object','properties':{'finish':{'type':'boolean'},'completed':{'type':'boolean'},'checkpoint':{'type':'object'},'wait_reason':{'type':'string'},'children':{'type':'array','items':{'type':'object','properties':{'title':{'type':'string'},'scope':{'type':'string'}},'required':['title','scope']}}},'required':['checkpoint']})
]]

class Runner:
    def __init__(self,root,api,sandbox,*,headed,max_browsers,max_models):
        self.root=root;self.api=api;self.sandbox=sandbox
        self.browser=ManagedBrowser(api,root/'browser',headed=headed)
        self.max_browsers=max_browsers;self.max_models=max_models
        self.jobs={};self.servers={};self.logins={};self.login_versions={};self.stopping=False;self.last_contact=time.monotonic()
        self.journal_path=root/'journal.json'
        self.journal=json.loads(self.journal_path.read_text()) if self.journal_path.exists() else {}
        self.status='starting';self.progress={};self.browser_memory=768*1024**2
        self.retiring=set()
    async def call(self,method,/,**args):return await asyncio.to_thread(self.api.call,method,**args)
    def remember(self,lid,**values):
        self.journal.setdefault(lid,{}).update(values);save(self.journal_path,self.journal)
    def capacity(self):
        # Running allocations remain counted. Only currently free memory increases
        # the admission allowance; no fixed task count or batch timer.
        try:
            import psutil
            free=psutil.virtual_memory().available
            # Measure local browser RSS; models run remotely. A model session is
            # not a 2 GiB local allocation. Explicit operator caps remain optional.
            auxiliary=[c for l in self.browser.active.values() for c in l.get('auxiliary_channels',{}).values()
                       if c['state']!='exited']
            count=len(self.browser.contexts)+len(self.browser.probe_contexts)+len(auxiliary)
            if count:
                processes=psutil.Process().children(recursive=True)
                for channel in auxiliary:
                    try:processes.extend(psutil.Process(channel['pid']).children(recursive=True))
                    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                rss=0
                for p in {p.pid:p for p in processes}.values():
                    try:
                        if any(x in p.name().lower() for x in ('chrom','headless')):rss+=p.memory_info().rss
                    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                if rss:self.browser_memory=max(self.browser_memory,rss//count)
            available=count+max(0,int(free//self.browser_memory))
            if psutil.cpu_percent()>95:available=count
            browsers=min(1024,available,max(0,self.max_browsers-len(self.browser.login_contexts)) if self.max_browsers else 1024)
            models=self.max_models or browsers
        except ImportError:
            raise RuntimeError('安装 runner 可选依赖后再启动')
        return browsers,models
    async def run(self):
        try:
            evidence=await asyncio.to_thread(self.sandbox.prepare)
            identity=self.root/'machine.json'
            if not identity.exists():save(identity,{'id':uuid4().hex})
            evidence['machine_id']=json.loads(identity.read_text())['id']
            evidence['remote_browser']=True
            evidence['automatic_configuration']=1
            evidence['account_management']=1
            evidence['credential_execution']=1
            evidence['simple_dispatch']=1
            evidence['direct_execution']=1
            evidence['browser_batch']=1
            evidence['case_execution']=1
            evidence['inline_operation_begin']=1
            evidence['shared_exploration']=1
            from .exploration_profiles import ADAPTER_SCHEMA
            evidence['automatic_exploration']=ADAPTER_SCHEMA
            evidence['auxiliary_channels']=1
            evidence['capacity_basis']='browser RSS + free memory + CPU; model cap explicit, no local model-memory estimate'
            await self.browser.start()
            await self.browser.check_runtime()
            b,m=self.capacity();protocol=await self.call('register',evidence=evidence,browser_slots=b,model_slots=m)
            if protocol.get('simple_dispatch')!=1:raise RuntimeError('平台需先升级到简单任务分配协议')
        except BaseException:
            await self.browser.close();await asyncio.to_thread(self.sandbox.close)
            raise
        console=asyncio.create_task(self.console_loop())
        receipts=asyncio.create_task(self.receipt_loop())
        try:
            while not self.stopping:
                try:
                    acknowledgements=[lid for lid,j in self.journal.items() if j.get('phase')=='settled' and not j.get('ack_reported')]
                    observations={lid:value.copy() for lid,value in self.browser.exploration_observations.items()
                                  if self.browser.active.get(lid,{}).get('exploration_bootstrap')}
                    b,m=self.capacity();state=await self.call('heartbeat',browser_slots=b,model_slots=m,progress=self.progress,settlement_acks=acknowledgements,
                                                             exploration_observations=observations,
                                                             exploration_faults=dict(self.browser.exploration_faults))
                    for lid in state.get('settlement_acks',[]):self.remember(lid,ack_reported=True)
                    self.receive_settlement_updates(state.get('settlement_updates',[]))
                    self.last_contact=time.monotonic();self.status='connected'
                    if 'account_generations' in state:await self.browser.sync_accounts(state['account_generations'])
                    live={l['id']:l for l in state['leases']}
                    for lid,lease in live.items():
                        if lid in self.browser.active:
                            self.browser.active[lid].update({k:v for k,v in lease.items() if k not in {'mode','exploration_bootstrap','resource_version'}})
                            self.browser._resource_receipt(lid,lease)
                        auxiliaries_bound = await self.bind_auxiliaries(lid,lease.get('auxiliary_channels',{}))
                        if not auxiliaries_bound:lease['revoked']=True
                        if auxiliaries_bound and lease.get('resource_hold') and lease.get('close_browser_requested'):
                            await self.browser.fence(lid)
                            await self.call('retained_browser_closed',lease_id=lid,
                                            auxiliary_stopped=list(lease.get('auxiliary_channels',{})))
                        if lease.get('resource_hold') and not lease.get('resolution_requested'):
                            # A verified stopped worker is not a queued job. A retained
                            # page stays fenced; an unknown result remains only a hold.
                            continue
                        job=self.jobs.get(lid)
                        if lease['revoked'] or not lease.get('simple_dispatch'):
                            await self.interrupt(lid)
                            if job is None or job.done():
                                self.jobs[lid]=asyncio.create_task(self.retire(lid))
                            continue
                        if job is None or job.done():
                            event=next((e for e in state['events'] if e['kind']=='start' and e['lease_id']==lid),None)
                            if self.journal.get(lid,{}).get('return_request') or self.journal.get(lid,{}).get('phase')=='return_pending' or (job is None and self.journal.get(lid,{}).get('phase')=='running'):
                                self.jobs[lid]=asyncio.create_task(self.retire(lid))
                            elif event or job is None:
                                self.jobs[lid]=asyncio.create_task((self.execute_direct if lease.get('direct') else self.execute)(event or {'lease_id':lid}))
                    for lid in list(self.browser.active):
                        if lid not in live and lid not in self.servers:await self.browser.fence(lid)
                    # A committed return can disappear from live leases before its
                    # HTTP reply reaches us. Reconcile the SAME durable request,
                    # including after restart; never restart the business worker.
                    for lid,record in list(self.journal.items()):
                        job=self.jobs.get(lid)
                        if (lid not in live and record.get('return_request') and
                                record.get('phase')!='settled' and (job is None or job.done())):
                            self.jobs[lid]=asyncio.create_task(self.retire(lid))
                    save(self.root/'status.json',{'state':self.status,'updated':time.time(),'running':list(self.servers),'direct_browsers':[lid for lid in self.browser.active if lid not in self.servers],'capacity_basis':'browser RSS/free memory/CPU; explicit model cap','browser_rss_estimate':self.browser_memory,'browser_slots':b,'model_slots':m,'headless':not self.browser.headed})
                except Exception:
                    self.status='disconnected'
                    # Before server's 60 s lease timeout, revoke local tool access.
                    if time.monotonic()-self.last_contact>40:
                        for lid in list(self.browser.active):await self.interrupt(lid)
                await asyncio.sleep(3)
        finally:
            console.cancel();receipts.cancel()
            await asyncio.gather(console,receipts,return_exceptions=True)
            for lid in list(self.browser.active):await self.interrupt(lid)
            await asyncio.gather(*self.jobs.values(),return_exceptions=True)
            for server in list(self.servers.values()):await asyncio.to_thread(server.close)
            await self.browser.close();await asyncio.to_thread(self.sandbox.close)
            save(self.root/'status.json',{'state':'stopped','updated':time.time(),'running':[]})
    def save_direct_receipt(self, lid, request_id, state, result):
        import hashlib
        directory=self.root/'direct-receipts';directory.mkdir(exist_ok=True,mode=0o700)
        path=directory/(hashlib.sha256((lid+'\0'+request_id).encode()).hexdigest()+'.json')
        save(path,dict(lease_id=lid,request_id=request_id,state=state,result=result))
        return path

    async def receipt_loop(self):
        # This durable outbox retries observations only. It never starts a
        # browser, submits an action or restores a retired lease's authority.
        while not self.stopping:
            for path in (self.root/'direct-receipts').glob('*.json'):
                try:
                    receipt=json.loads(path.read_text())
                    await self.call('direct_result',**receipt)
                    path.unlink(missing_ok=True)
                except Exception:pass
            await asyncio.sleep(3)

    async def console_loop(self):
        while not self.stopping:
            try:
                item=(await self.call('console_poll')).get('command')
                if item:
                    identity={k:item[k] for k in ('session_id','request_id')}
                    result={};status='not_sent'
                    try:
                        # A view can inspect an active model, but input can never
                        # race a model turn or revive a stale browser context.
                        lid=item['target'].get('lease_id')
                        if item['action']!='view' and lid in self.servers:raise RuntimeError('模型尚未停止')
                        self.browser.validate_console(item)
                        auth=await self.call('console_authorize',**identity)
                        if item['expires']<time.time():raise RuntimeError('现场操作已超时')
                        status='unknown'
                        result=await asyncio.wait_for(self.browser.console(item,auth),timeout=20)
                        status='confirmed'
                    except Exception as exc:
                        result={'error':str(exc)[:300]}
                    try:await self.call('console_result',**identity,state=status,result=result)
                    except Exception:pass # Never repeat a claimed command after response loss.
            except Exception:pass
            await asyncio.sleep(.5)

    async def interrupt(self,lid):
        job=self.jobs.get(lid)
        # Repeated revoke heartbeats must not cancel fencing/return/ACK writes.
        # Cancellation of to_thread cannot undo the already committed HTTP call.
        if lid not in self.retiring and lid not in self.servers and job and not job.done():job.cancel()
        if lid in self.browser.active:self.browser.active[lid]['revoked']=True
        server=self.servers.get(lid);j=self.journal.get(lid,{})
        if server and not j.get('interrupt_sent'):
            self.remember(lid,interrupt_sent=True,interrupt_at=time.monotonic())
            try:await asyncio.to_thread(server.interrupt,j['thread_id'],j['turn_id'])
            except Exception:pass
    async def return_account(self,lid,request):
        self.remember(lid,return_request=request,phase='returning',ack_reported=False)
        result=await self.call('return_account',**request)
        self.remember(lid,phase='settled',settlement=result)
        return result

    def receive_settlement_updates(self, updates):
        # A retained/isolated return was acknowledged before its later release.
        # Persist the server's actual release receipt before acknowledging it;
        # never turn the old retained receipt into a release by inference.
        for receipt in updates:
            lid=receipt['lease_id']
            if receipt.get('released') and self.journal.get(lid,{}).get('return_request'):
                self.remember(lid,phase='settled',settlement={k:v for k,v in receipt.items() if k!='lease_id'},ack_reported=False)

    async def retire(self,lid):
        """Restart/migration recovery closes the original worker before requeueing."""
        self.retiring.add(lid)
        try:
            old=self.journal.get(lid,{})
            if old.get('return_request'):
                if not old.get('settlement',{}).get('retained'):
                    await self.return_account(lid,old['return_request']);return
            context=await self.call('read',lease_id=lid)
            if not await self.bind_auxiliaries(lid,context['lease'].get('auxiliary_channels',{})):
                raise RuntimeError('辅助进程无法核实，保留原资源')
            await asyncio.to_thread(self.sandbox.stop,context['node']['id'])
            checkpoint=context['node']['checkpoint']
            keep=self.retain_browser(context,checkpoint)
            if keep:await self.browser.fence(lid,close=False)
            else:await self.browser.fence(lid)
            uncertain=[]
            for cid,channel in context['lease'].get('auxiliary_channels',{}).items():
                for path in (Path(channel['directory'])/'jobs').glob('*.json'):
                    record=json.loads(path.read_text())
                    if record.get('status') in {'running','uncertain'}:
                        uncertain.append({'id':cid+':'+record['id'],'hash':record.get('fingerprint','')})
            checkpoint={**checkpoint,'resume_note':'后台执行器已退出，账号已回收后重新排队。保留原用例和历史；继续前查看实际业务状态，不能把旧未知操作当作成功或盲目重放。'}
            finish=context['lease'].get('direct_finish') or {}
            outcome=finish.get('outcome','blocked')
            reason=finish.get('reason') or context['lease'].get('timeout_reason') or '执行连接已恢复并确认旧进程退出；保留原进度，请核实后继续'
            request=dict(lease_id=lid,executor_stopped=True,browser_stopped=not keep,
                         scene_retained=keep,outcome=outcome,checkpoint=finish.get('checkpoint',checkpoint),reason=reason)
            if not keep:request['auxiliary_stopped']=list(context['lease'].get('auxiliary_channels',{}))
            request['auxiliary_uncertain']=uncertain
            if context['lease'].get('resolution_requested'):request['resource_resolution']=True
            if finish.get('children'):request['children']=finish['children']
            if outcome=='completed':request.update(self.result(context))
            await self.return_account(lid,request)
        except Exception:
            # Retry fencing/return, never execute the old business turn again.
            self.remember(lid,phase='return_pending')
        finally:
            self.retiring.discard(lid)

    async def bind_auxiliaries(self,lid,channels):
        for cid,channel in channels.items():
            if channel.get('state') in {'bound','exited'}:continue
            try:stopped=await asyncio.to_thread(self.browser.register_auxiliary,lid,cid,channel)
            except Exception as exc:
                self.remember(lid,auxiliary_binding_failure={'channel_id':cid,'error_type':type(exc).__name__})
                await self.call('auxiliary_bound',lease_id=lid,channel_id=cid,error=True,error_type=type(exc).__name__)
                return False
            await self.call('auxiliary_bound',lease_id=lid,channel_id=cid,stopped=stopped)
        return True

    @staticmethod
    def result(context):
        cases=(context.get('record') or {}).get('cases',[])
        complete=bool(cases) and all(c['status'] in {'passed','failed'} and all(p.get('status') in {'passed','failed'} for p in c.get('checkpoints',[])) for c in cases)
        return dict(result='failed' if any(c['status']=='failed' for c in cases) else 'passed' if complete else 'partial',coverage_complete=complete)

    @staticmethod
    def retain_browser(context,checkpoint):
        if context.get('lease',{}).get('resolution_requested') or context.get('node',{}).get('session_removed'):return False
        finish=context.get('lease',{}).get('direct_finish') or {}
        checkpoint={**checkpoint,**finish.get('checkpoint',{})}
        return bool(checkpoint.get('retain_browser') or checkpoint.get('retain_scene')
                    or context.get('node',{}).get('state')=='retained')

    async def recover_unstarted(self,lid,fault_id):
        """Retry only after the old process exited and no business action was sent.

        This is reached solely on a failed attempt. Ordinary commands, receipt
        polling and successful completion incur no additional calls or checks.
        """
        operations=(await self.call('operations',lease_id=lid)).get('operations',[])
        if any(op['state']!='not_sent' for op in operations):return None
        rid=uuid4().hex
        budget=await self.call('recover_begin',lease_id=lid,recovery_id=rid,fault_id=fault_id)
        if not budget.get('start'):return None
        self.remember(lid,phase='recovering',recovery_id=rid,fault_id=fault_id)
        await asyncio.sleep(budget.get('delay_seconds',0))
        if self.stopping:
            await self.call('recover_finish',lease_id=lid,recovery_id=rid,recovered=False)
            return None
        return rid

    async def execute_direct(self,event,recovery_id=None):
        lid=event['lease_id'];error=False;recovery_finished=False
        try:
            context=await self.call('read',lease_id=lid)
            self.remember(lid,node_id=context['node']['id'],phase='running',direct=True)
            await asyncio.wait_for(self.browser.bind(context),timeout=90)
            dispatch=event if event.get('id') else context['dispatch']
            await self.call('browser_ready',lease_id=lid,event_id=dispatch['id'])
            if recovery_id:
                await self.call('recover_finish',lease_id=lid,recovery_id=recovery_id,recovered=True)
                recovery_finished=True
            while not self.stopping and not self.browser.active.get(lid,{}).get('revoked',True):
                command=(await self.call('direct_poll',lease_id=lid)).get('command')
                if command:
                    state='completed'
                    try:
                        from .exploration_learning import command_timeout
                        timeout=command_timeout(command['action'],command.get('parameters',{}))
                        options={'begin_receipt':command['begin_receipt']} if 'begin_receipt' in command else {}
                        result=await asyncio.wait_for(self.browser.operate(lid,command['account_id'],command['action'],command.get('parameters',{}),command['id'],**options),timeout=timeout)
                        state=result.pop('_command_state',state)
                        measured=getattr(self.browser,'last_operation_timing',{}).pop(lid,{})
                        if measured.get('operation_id')==command['id']:
                            result={**result,'runner_timing':measured}
                    except Exception as exc:
                        from .browser_policy import ExclusiveRequired
                        if isinstance(exc,ExclusiveRequired):
                            state='blocked';result={'error':str(exc)[:600],'requires_exclusive':True,'business_failure':False}
                        else:
                            state='unknown';result={'error':(str(exc) or type(exc).__name__)[:600],'instruction':'先读取现场核实原动作，不得更换请求 ID 盲重试业务提交'}
                    receipt_path=self.save_direct_receipt(lid,command['id'],state,result)
                    # A lost receipt is retried, never its browser action.
                    for attempt in range(3):
                        try:
                            await self.call('direct_result',lease_id=lid,request_id=command['id'],state=state,result=result)
                            receipt_path.unlink(missing_ok=True);break
                        except Exception:
                            if attempt==2:raise
                            await asyncio.sleep(1)
                    self.progress[lid]=self.progress.get(lid,0)+1
                else:await asyncio.sleep(.3)
        except asyncio.CancelledError:
            pass
        except Exception:
            error=True
        finally:
            if recovery_id and not recovery_finished:
                try:await self.call('recover_finish',lease_id=lid,recovery_id=recovery_id,recovered=False)
                except Exception:pass
            if error and not self.stopping:
                try:
                    await self.browser.fence(lid)
                    retry=await self.recover_unstarted(lid,'direct-start:'+lid)
                    if retry:
                        await self.execute_direct(event,recovery_id=retry)
                        return
                except Exception:pass
            await self.retire(lid)

    async def execute(self,event,recover=False,recovery_id=None):
        lid=event['lease_id'];server=None;context=None;finished=None;error=None;checkpoint={};recovery_finished=False
        try:
            context=await self.call('read',lease_id=lid)
            if context['lease']['revoked']:return
            node=context['node'];checkpoint=node.get('checkpoint',{})
            # Stop only this node's old process group; never run two consumers of
            # the same account, including after a host restart.
            await asyncio.to_thread(self.sandbox.stop,node['id'])
            server=await asyncio.to_thread(self.sandbox.open,node['id']);self.servers[lid]=server
            thread_id=node.get('thread_id') if node.get('thread_host',context['lease']['runner_id'])==context['lease']['runner_id'] else None
            if thread_id:
                try:await asyncio.to_thread(server.resume_thread,thread_id)
                except ThreadNotFound:
                    thread_id=await asyncio.to_thread(server.start_thread,cwd=self.sandbox.cwd(node['id']),tools=TOOLS,model=self.sandbox.model)
                # The old process group is already stopped. Resume preserves
                # its history internally; do not hydrate all turns or interrupt
                # historical inProgress entries on a new idle App Server.
            else:
                thread_id=await asyncio.to_thread(server.start_thread,cwd=self.sandbox.cwd(node['id']),tools=TOOLS,model=self.sandbox.model)
            await self.browser.bind(context)
            turn_id=await asyncio.to_thread(server.start_turn,thread_id,self.prompt(context,[],recover))
            dispatch=event if event.get('id') else context['dispatch']
            self.remember(lid,node_id=node['id'],event_id=dispatch['id'],thread_id=thread_id,turn_id=turn_id,
                          phase='running',interrupt_sent=False)
            ack=dict(lease_id=lid,event_id=dispatch['id'],thread_id=thread_id,turn_id=turn_id)
            if recovery_id:ack['recovery_id']=recovery_id
            await self.call('ack',**ack)
            if recovery_id:
                await self.call('recover_finish',lease_id=lid,recovery_id=recovery_id,recovered=True)
                recovery_finished=True
            last_progress=time.monotonic()
            while True:
                if time.monotonic()-last_progress>600:raise TimeoutError('任务无进展超时')
                if server.closed:raise RuntimeError('Codex 执行连接中断')
                if self.journal[lid].get('interrupt_sent') and time.monotonic()-self.journal[lid]['interrupt_at']>15:break
                try:packet=server.events.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(.1);continue
                last_progress=time.monotonic();self.progress[lid]=self.progress.get(lid,0)+1
                method=packet['method'];params=packet.get('params',{})
                if method=='item/tool/call':
                    try:
                        if finished:raise RuntimeError('本轮已交还，请结束回复')
                        if params.get('threadId')!=thread_id or params.get('turnId')!=turn_id:raise RuntimeError('工具调用不属于当前任务')
                        name=params['tool'];args=params['arguments']
                        if isinstance(args,str):args=json.loads(args)
                        if name=='account_credentials':
                            value=await self.call(name,lease_id=lid,account_id=args['account_id'])
                        elif name=='browser':
                            value=await self.browser.operate(lid,args['account_id'],args['action'],args.get('parameters',{}),args.get('operation_id') or turn_id+':'+str(packet['id']))
                        elif name=='test_record':
                            if args['action'] not in {'record','cases','assets','publish','reference','requirements','save_requirements','dependency','reconcile','fixture','shared_policy'}:raise ValueError('未知记录动作')
                            arguments=args.get('arguments',{})
                            if args['action']=='assets':
                                arguments=json.loads(json.dumps(arguments))
                                for asset in arguments.get('assets',[]):
                                    if asset.get('capture_id'):
                                        capture=self.browser.captures.get(asset.pop('capture_id'))
                                        if not capture or capture['lease_id']!=lid:raise ValueError('截图不属于当前任务')
                                        asset.update(content_base64=capture['content_base64'],content_type='image/png')
                            value=await self.call(args['action'],**{**arguments,'lease_id':lid})
                        elif name=='request_resources':
                            value=await self.call('request_resources',**{**args,'lease_id':lid})
                        elif name=='checkpoint':
                            checkpoint=args['checkpoint']
                            value=await self.call('save_checkpoint',lease_id=lid,checkpoint=checkpoint)
                            # Old threads can still use phase metadata. It is not
                            # a workflow gate or a reason to restart the model.
                            phase_only=args.get('next_phase') and not any(args.get(k) for k in ('completed','children','wait_reason'))
                            if args.get('finish') and not phase_only:
                                finished=args
                                self.remember(lid,finish=args)
                            elif phase_only:value['continue']='进度已保存，继续当前任务；无需阶段交接。'
                        else:raise ValueError('未知工具')
                        server.tool_response(packet['id'],value,True)
                    except Exception as exc:
                        # Ordinary locator, page and report errors stay local to
                        # the call. Codex can inspect and correct them itself.
                        from .browser_policy import ExclusiveRequired
                        if isinstance(exc,ExclusiveRequired):
                            value={'error':str(exc),'requires_exclusive':True,'business_failure':False}
                        else:
                            value={'error':str(exc),'instruction':'任务仍可操作。核对实际页面或记录后自行修正；可能已提交的业务操作先查看结果再决定是否重试。'}
                        server.tool_response(packet['id'],value,False)
                elif method=='turn/completed' and params.get('turn',{}).get('id')==turn_id:break
            if finished and finished.get('completed'):
                try:await self.call('publish',lease_id=lid,title=node['title'],summary='按本轮实际用例和证据生成；未执行项保持原状态。')
                except Exception:checkpoint={**checkpoint,'report_note':'报告发布失败，已保存用例保留，可稍后重新发布。'}
        except Exception as exc:
            # No page data or credentials in operational logs.
            error=type(exc).__name__
        finally:
            if server:
                try:await asyncio.to_thread(server.close)
                except Exception:pass # sandbox.stop below still confirms process-group exit.
                self.servers.pop(lid,None)
            if context:
                try:
                    await asyncio.to_thread(self.sandbox.stop,context['node']['id'])
                    keep=self.retain_browser(context,checkpoint)
                    if keep:await self.browser.fence(lid,close=False)
                    else:await self.browser.fence(lid)
                    if recovery_id and not recovery_finished:
                        await self.call('recover_finish',lease_id=lid,recovery_id=recovery_id,recovered=False)
                    if error and not keep and not self.stopping:
                        try:retry=await self.recover_unstarted(lid,'managed-start:'+lid)
                        except Exception:retry=None
                        if retry:
                            await self.execute(event,recover=True,recovery_id=retry)
                            return
                    outcome='yield'
                    reason=''
                    if finished and finished.get('completed'):outcome='completed'
                    elif finished and finished.get('wait_reason'):outcome='blocked';reason=finished['wait_reason']
                    elif error and not self.stopping:outcome='blocked';reason='执行器错误（'+error+'），账号已回收；可继续原任务'
                    if not finished and not error and not self.stopping:
                        outcome='blocked';reason='Codex 本轮已结束但未提交完成或安全交还检查点；保留已有进度，不自动重复启动相同业务。'
                    request=dict(lease_id=lid,executor_stopped=True,browser_stopped=not keep,
                                 scene_retained=keep,outcome=outcome,checkpoint=checkpoint,reason=reason)
                    if finished and finished.get('children'):request['children']=finished['children']
                    if outcome=='completed':
                        # Completion of a task is distinct from passing its tests.
                        request.update(result='partial',coverage_complete=False)
                        try:
                            current=await self.call('read',lease_id=lid)
                            cases=(current.get('record') or {}).get('cases',[])
                            complete=bool(cases) and all(c['status'] in {'passed','failed'} and all(p.get('status') in {'passed','failed'} for p in c.get('checkpoints',[])) for c in cases)
                            request.update(result='failed' if any(c['status']=='failed' for c in cases) else 'passed' if complete else 'partial',coverage_complete=complete)
                        except Exception:pass # Report availability never holds an exited worker's account.
                    await self.return_account(lid,request)
                except Exception:
                    # Preserve the allocation until process exit is confirmed.
                    # Heartbeat retries a durable return, without replaying work.
                    self.remember(lid,phase='return_pending')

    @staticmethod
    def prompt(context,operations=None,recover=False):
        context={**context,
                 'lease':{k:v for k,v in context.get('lease',{}).items() if k in {'id','account_ids','mode','policy_id','resource_version','exploration_bootstrap'}},
                 'node':{k:v for k,v in context.get('node',{}).items() if k in {'id','title','scope','depends_on','checkpoint','result'}},
                 'accounts':[{k:v for k,v in a.items() if k in {'id','identity','target','login','has_password'}} for a in context.get('accounts',[])]}
        context.pop('available_identities',None)
        return ('你是此测试任务的执行 Codex。平台负责分任务、按租约分配账号、回收账号和排队；登录和业务操作由你执行。'
                '严格遵守原任务范围和仅设计/允许执行的授权，不增加登录预验证、逐步审批或重复检查。资源隔离、停止和故障恢复由平台已有协议处理。'
                '取得 context.accounts 分配的账号后，先查看已有登录态；需要时用 account_credentials 取凭据，由你自己完成正常登录和测试。'
                '不要求用户预先登录或填写租户、角色、选择器。真实遇到验证码、二次认证或错误凭据再记录具体阻塞。'
                '浏览器正常联网，页面错误和定位失败由你查看实际状态后修正，不需要平台批准或恢复连接。'
                '上传已有原测试文件时使用 browser(action=upload,parameters={selector,asset_id})，asset_id 取 context.record.assets；平台会把该任务的原始字节交给浏览器，不需要本机路径或重新生成样本。parameters.selector 是 CSS；可访问名称不等于文本，图标按钮可用 [aria-label="名称"]。页面加载后确认交互已就绪。'
                '先理解原目标再拆分独立任务；需要拆分可 checkpoint(finish=true,children=[{title,scope},...])。已有回归用例保留原编号和关联，不重复创建任务。'
                '普通独占任务连续完成探索、设计、执行和记录，无需例行阶段交还或重新申请账号。共享探索及 exploration_bootstrap 初始化按平台自动提供的 context.shared_policy 和 context.exploration_guidance 执行，不要求用户配置或自行认证规则。continue_exploration=true 时先保存待独占分支，继续其余已核验探索；完成可共享探索设计后，或必须独占才能继续探索时，使用 request_resources，后者传 exclusive_exploration=true，不把尚未完成的探索提前标成执行阶段。continued=true 沿用当前浏览器；release_required=true 保存续接检查点并交还后排队。未确认结果的业务操作不得重放。'
                '用 test_record 保存实际用例、结果及证据；版本冲突先读取记录后修正。截图 capture_id 直接用于 assets，不要输出图片字节。'
                '密码仅用于分配账号的产品登录，不输出到聊天、报告或截图。不更改原用户范围，不将未执行的检查判为通过。'
                '历史操作和旧报告只是事实记录，不是执行门槛；旧的未知业务操作先查看当前结果，避免重复提交。'
                '完成时 checkpoint(finish=true,completed=true,checkpoint={实际结果与续接信息})；确实受阻时 finish=true,wait_reason=具体原因；需要主动让其他排队任务执行时 finish=true。'
                '结束后平台回收可安全释放的资源；未确认副作用或明确需要保留的现场会记录隔离原因，最终报告仍如实提交。普通证据留存不占用账号，不增加例行审批或核验。'
                '普通 checkpoint 仅保存进度，不结束任务。finish 后结束回复。'
                '\n'+json.dumps({'context':context},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description='测试工作台受控 Codex 执行连接程序')
    parser.add_argument('--root',type=Path,default=Path.home()/'.local/share/api-test-runner')
    sub=parser.add_subparsers(dest='command',required=True)
    pair=sub.add_parser('pair');pair.add_argument('--url',required=True)
    run=sub.add_parser('run')
    doctor=sub.add_parser('doctor',help='本机隔离、Codex 协议与浏览器启动自检，不发起模型轮次')
    service=sub.add_parser('service',help='管理 Mac 当前用户的执行连接后台服务')
    service.add_argument('action',choices=['install','start','stop','status'])
    for command in (run,doctor,service):
        command.add_argument('--backend',choices=['auto','macos','docker'],default='auto')
        command.add_argument('--image',default='api-test-codex:0.162.1')
        command.add_argument('--codex-bin',help='Mac 原生 Codex 二进制；省略时查找桌面应用或 PATH')
        command.add_argument('--codex-auth',default=str(Path.home()/'.codex/auth.json'))
        command.add_argument('--model')
    run.add_argument('--headless',action='store_true',help='兼容参数；登录和测试浏览器默认无窗口运行')
    run.add_argument('--max-browsers',type=int,default=0,help='0 自动按实测浏览器与机器资源分配');run.add_argument('--max-models',type=int,default=0,help='0 不额外限制远端推理并发；可显式设置服务额度')
    sub.add_parser('status')
    args=parser.parse_args();root=args.root.expanduser().resolve();root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if args.command=='pair':
        api=HostAPI(args.url);code=getpass.getpass('平台连接码（不回显）：')
        result=api.post('/api/managed-host/redeem',{'code':code});save(root/'connection.json',{'url':args.url,**result})
        print('执行连接已配对；启动 run 后才报告容量。');return
    if args.command=='status':
        path=root/'status.json';print(path.read_text() if path.exists() else '尚未启动');return
    if args.command=='service':
        from .managed_macos_service import service as manage_service
        manage_service(args.action,root,auth_file=args.codex_auth,codex_bin=args.codex_bin,model=args.model);return
    if args.command=='run' and (not 0<=args.max_models<=1024 or not 0<=args.max_browsers<=1024):parser.error('容量上限须为 0–1024（0 自动）')
    with open(root/'runner.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        sandbox=create_sandbox(root/'codex',args.image,args.codex_auth,model=args.model,backend=args.backend,codex_bin=args.codex_bin)
        if args.command=='doctor':
            async def check():
                browser=ManagedBrowser(None,root/'browser',headed=False)
                try:
                    evidence=await asyncio.to_thread(sandbox.prepare)
                    await browser.start();await browser.check_runtime()
                    print(json.dumps({'state':'ready','backend':evidence['version'].split(':')[0],
                        'codex_protocol':'ready','browser':'ready','isolation':'verified',
                        'model_turn_started':False,'paired':(root/'connection.json').exists()},ensure_ascii=False))
                finally:
                    await browser.close();await asyncio.to_thread(sandbox.close)
            asyncio.run(check());return
        connection=json.loads((root/'connection.json').read_text())
        api=HostAPI(connection['url'],connection['token'])
        runner=Runner(root,api,sandbox,headed=False,max_browsers=args.max_browsers,max_models=args.max_models)
        def stop(*_):runner.stopping=True
        signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
        asyncio.run(runner.run())

if __name__=='__main__':main()
