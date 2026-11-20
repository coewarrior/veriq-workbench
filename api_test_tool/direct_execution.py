"""Current-chat execution over the existing host/browser and shared account leases.

The host never launches a model for a direct lease. Command receipts are durable;
unknown operations are reconciled, not replayed. Expiration revokes authority;
only the original host's confirmed browser/process exit releases an account.
"""
from __future__ import annotations
import copy
import json
from .orchestration_storage import select_records, read_entries, read_sections, read_metadata_without_history
from .orchestration import Conflict, text, digest

START_TIMEOUT = 120
PROGRESS_TIMEOUT = 600
HUMAN_TIMEOUT = 1800


class DirectExecutionDenied(PermissionError):
    """Public, non-secret explanation of a direct-call ownership mismatch."""


def expire_leases(state, now):
    for lease in list(state['leases'].values()):
        if lease.get('resource_hold') or lease.get('native_browser'):continue
        node=state['nodes'][lease['node_id']]
        runner=state['runners'].get(lease['runner_id'],{})
        reason=''
        if now-runner.get('heartbeat',0)>60:
            reason='执行连接失联；旧权限已撤销，等待原执行机确认退出，不能重派未知业务操作'
        elif node['state']=='starting' and now-lease['created']>START_TIMEOUT:
            reason='启动确认超时；结束原执行后回收账号，本次没有确认的操作保持未知'
        elif not lease.get('revoked'):
            channels=lease.get('auxiliary_channels',{}).values()
            if any(c['state']!='exited' and now-c.get('last_seen',c['created_at'])>40 for c in channels):
                reason='辅助浏览器执行连接失联；撤权并由原执行机确认所有通道退出'
            if lease.get('waiting'):
                if now-lease['waiting']['since']>HUMAN_TIMEOUT:reason='等待人工超时；任务阻塞结束，原进度和未验证项保留'
            elif lease.get('direct') and (now-lease.get('actor_seen',lease['created'])>PROGRESS_TIMEOUT or now-lease.get('progress_at',lease['created'])>PROGRESS_TIMEOUT):
                reason='当前 Codex 会话失联或无进展超时；撤销旧权限并回收浏览器，原任务可核实后继续'
            elif not lease.get('direct') and now-lease.get('progress_at',lease['created'])>PROGRESS_TIMEOUT:
                reason='Codex 任务无进展超时；撤销旧权限并结束执行，未知提交不自动重试'
        if reason:
            from .module_dispatch import command
            command(state, node, 'timeout', now)
            events=[e for e in state['outbox'].values() if e['lease_id']==lease['id'] and e['kind']=='start']
            if events and all(e['status']=='pending' and 'delivered_at' not in e for e in events):
                for e in events:e['status']='cancelled'
                node.setdefault('undelivered_leases',[]).append(lease['id'])
                del state['leases'][lease['id']]
                node.update(state='blocked',reason='派发未送达且已超时；确认没有启动执行，账号已回收',finalization_pending=True)
                node.pop('direct_holder',None)
                continue
            lease.update(revoked=True,timeout_reason=lease.get('timeout_reason') or reason)
            node.update(state='isolated' if now-runner.get('heartbeat',0)>60 else 'stopping',reason=reason)


class DirectExecution:
    def __init__(self, service):
        self.service=service;self.c=service.controller;self.store=service.store

    def _owned(self,s,owner,args,active=True):
        if not args.get('lease_id'):
            raise ValueError('缺少 lease_id；未领取账号时结束当前轮次，由协调者确认资源可用后沿用原 task_id/node_id/holder_id/dispatch_id 唤醒领取，不循环 claim；action=wait 仅用于已分配浏览器等待人工操作，不是排队等待。未分配时不调用浏览器或凭据接口。')
        l=s['leases'].get(args.get('lease_id'))
        if not l:raise Conflict('指定的 lease_id 不存在或已结束；请核对原任务回执，不重复提交业务操作。')
        n=self.c.owned(s['nodes'],owner,l['node_id']);t=s['tasks'][n['task_id']]
        if not l.get('direct') or n.get('direct_holder')!=args.get('holder_id'):
            raise DirectExecutionDenied('holder_id 与领取此任务的聊天不一致；请沿用原 claim 的 holder_id。')
        if active and (l['revoked'] or t['intent']!='run' or n.get('control_intent','run')!='run' or l['revision']!=n['revision'] or (not l.get('native_browser') and l['epoch']!=s['epoch'])):
            raise Conflict('旧执行权限已撤销；查询结果并等待账号回收，不能继续操作')
        return l,n,t

    @staticmethod
    def _account(lease,args):
        aid=args.get('account_id')
        if not aid:
            if len(lease['account_ids'])==1:return lease['account_ids'][0]
            raise ValueError('当前租约包含多个账号，请从 context.accounts 中指定本次操作的 account_id。')
        if aid not in lease['account_ids']:
            raise DirectExecutionDenied('account_id 不属于当前租约；请使用 context.accounts 中已分配的账号，不需重新登录或重新配对。')
        return aid

    @staticmethod
    def _status(node,lease):
        from .module_dispatch import node_dispatch
        return {'state':node['state'],'node_id':node['id'],'task_id':node['task_id'],'reason':node['reason'],
                'lease_id':lease['id'] if lease else None,'account_ids':list(lease['account_ids']) if lease else [],
                'browser_ready':bool(lease and node['state']=='running' and not lease['revoked']),
                'mode':'local_browser','executor':'current_codex',
                'resource_mode':lease.get('mode') if lease else None,
                'business_started':bool(node.get('business_started_at')),
                'business_started_at':node.get('business_started_at'),
                **node_dispatch(node),
                'next_action':('context' if lease and node['state']=='running' and not lease['revoked'] else
                               'end_turn_until_resources' if not lease and node['state']=='queued' else 'claim'),
                **({'resource_wait':{'end_turn':True,'wake_owner':'coordinator',
                     'task_id':node['task_id'],'node_id':node['id'],'reason':node['reason']}}
                   if not lease and node['state']=='queued' else {}),
                **({'queue_guidance':'未取得账号时结束当前轮次并停止领取循环；协调者保留原节点及顺位，资源可分配后才唤醒原会话。不调用 action=wait（仅用于已分配浏览器等待人工）。'} if not lease and node['state']=='queued' else {}),
                'timeouts':{'startup_seconds':START_TIMEOUT,'progress_seconds':PROGRESS_TIMEOUT,'human_wait_seconds':HUMAN_TIMEOUT}}

    def _context_without_lease(self,owner,args):
        # A premature context read is a status read, not evidence of an ended lease.
        # It must not allocate resources, renew a holder or create another task.
        with self.c.connect() as db:
            state=read_metadata_without_history(db)
        if args.get('node_id'):
            node=self.c.owned(state['nodes'],owner,args['node_id'])
            if args.get('task_id') and node['task_id']!=args['task_id']:
                raise ValueError('node_id 与 task_id 不匹配，请沿用同一 claim 回执。')
        elif args.get('task_id'):
            task=self.c.owned(state['tasks'],owner,args['task_id'])
            nodes=[state['nodes'][nid] for nid in task['node_ids'] if not state['nodes'][nid].get('child_ids')]
            mine=[n for n in nodes if n.get('direct_holder')==args['holder_id']]
            candidates=mine or nodes
            if len(candidates)!=1:raise ValueError('请提供原 claim 回执中的 node_id，以读取对应节点状态。')
            node=candidates[0]
        else:
            raise ValueError('context 缺少 lease_id；排队时请传入原 task_id/node_id 查询状态。')
        if node.get('direct_holder') not in {None,args['holder_id']}:
            raise DirectExecutionDenied('holder_id 与领取此任务的聊天不一致；请沿用原 claim 的 holder_id。')
        if (args.get('arguments') or {}).get('resume_notice') is True:
            from .native_identity import same_executor_ref
            if state['tasks'][node['task_id']]['intent'] != 'run' or node.get('control_intent', 'run') != 'run':
                raise Conflict('task_not_running: 任务已停止或暂停；旧通知不恢复执行')
            binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
            if (binding.get('holder_id') != args.get('holder_id')
                    or (binding.get('dispatch_id') or binding.get('id')) != args.get('dispatch_id')
                    or not same_executor_ref(binding.get('executor_ref'), args.get('executor_ref'))):
                raise Conflict('resume_writer_changed: 恢复通知不属于当前派发及实际执行者')
            self.c.sessions.assert_available(state, state['tasks'][node['task_id']], [node['id']])
            if node.get('checkpoint', {}).get('work_plan'):
                raise Conflict('work_token_missing: 原任务已有阶段计划，恢复通知缺少完整阶段令牌')
        lease=next((l for l in state['leases'].values() if l['node_id']==node['id']),None)
        result=self._status(node,lease)
        if state['tasks'][node['task_id']].get('execution_route') == 'native_browser':
            from .native_execution import NativeExecution
            result.update(NativeExecution.status(node, lease))
            result.pop('timeouts', None)
        if node['state'] in {'completed','blocked','paused','stopped','isolated','stopping'}:
            result['next_action']='get_managed_test'
        return result

    def call(self,owner,args):
        from .native_execution import NativeExecution
        native = NativeExecution(self)
        if native.applies(owner,args):
            return native.call(owner,args)
        if args.get('action') in {'wait','continue'}:
            with self.service.console.lock:
                if args['action']=='continue':self.service.console.assert_idle(owner,args.get('lease_id'))
                return self._call(owner,args)
        return self._call(owner,args)

    def _call(self,owner,args):
        action=args.get('action');holder=text(args.get('holder_id'),'holder_id',160)
        if action=='dispatch':
            from .module_dispatch import offer_modules
            return offer_modules(self.c,owner,args)
        if action=='channel':return self.channel(owner,args)
        if action=='request_resources':
            with self.c.transaction() as (_,state):
                self._owned(state,owner,args)
            return self.c.request_resources(owner,args['lease_id'],args)
        if action=='context' and not args.get('lease_id'):
            return self._context_without_lease(owner,args)
        if action=='claim':
            with self.c.transaction() as (_,s):
                t=self.c.owned(s['tasks'],owner,args.get('task_id'))
                if t.get('execution_route')!='local_browser':raise Conflict('原任务属于后台执行，不可创建第二个执行者')
                if t['intent']!='run':raise Conflict('任务已暂停或停止；连接或领取不能恢复执行，请沿原任务明确继续')
                candidates=[s['nodes'][i] for i in t['node_ids'] if not s['nodes'][i].get('child_ids') and s['nodes'][i].get('control_intent','run')=='run' and s['nodes'][i]['state'] not in {'completed','blocked','paused','stopped','isolated','stopping'}]
                if args.get('node_id'):candidates=[n for n in candidates if n['id']==args['node_id']]
                mine=[n for n in candidates if n.get('direct_holder')==holder]
                available=[n for n in candidates if not n.get('direct_holder')]
                node=next(iter(mine or available),None)
                if node is None:return {'state':'unavailable','message':'没有可领取的节点；查询原任务或明确继续阻塞任务，不重复创建。'}
                from .testing_policy import node_excluded, resource_excluded, excluded_response
                proposed = {**node, **({'requested_account_ids': args['account_ids']} if args.get('account_ids') else {})}
                if node_excluded(proposed, s) or resource_excluded(proposed, s):
                    return excluded_response(node_id=node['id'], task_id=t['id'])
                self.c.sessions.assert_available(s,t,[node['id']])
                if args.get('account_ids'):
                    requested=args['account_ids']
                    if not isinstance(requested,list) or len(set(requested))!=len(requested):raise ValueError('account_ids 必须是无重复列表')
                    if any(aid not in s['accounts'] or s['accounts'][aid]['owner']!=owner or (t.get('account_project_id') or t['project_id']) not in s['accounts'][aid]['projects'] for aid in requested):raise PermissionError('请求账号不属于当前项目')
                    if node['state']!='queued' and requested!=node.get('requested_account_ids'):raise Conflict('已执行阶段不能追加部分占用；在安全检查点交还后申请完整集合')
                    node['requested_account_ids']=requested
                if args.get('locks'):
                    from .orchestration import strings
                    if node['state']!='queued':raise Conflict('请在安全检查点申请完整资源集合')
                    node['locks']=list(dict.fromkeys([*node.get('locks',[]),*strings(args['locks'],'业务资源锁')]))
                from .module_dispatch import receive
                receive(s,node,holder,self.c.clock(),executor_ref=args.get('executor_ref',''),
                        coordinator_ref=args.get('coordinator_ref',''),dispatch_id=args.get('dispatch_id',''))
                node.update(direct_holder=holder,actor_seen=self.c.clock())
                nid=node['id']
            self.c.schedule()
            with self.c.transaction() as (_,s):
                n=s['nodes'][nid];l=next((l for l in s['leases'].values() if l['node_id']==nid),None)
                if l:l['actor_seen']=self.c.clock()
                result=self._status(n,l)
            return result
        if action=='finish' and not args.get('lease_id'):
            return self.finish_unallocated(owner,args)
        if action in {'finish','reconcile'}:
            with self.c.transaction() as (_,s):
                ended=s.get('direct_settlements',{}).get(args.get('lease_id'))
                if ended:
                    if ended['owner']!=owner or ended['holder_id']!=holder:raise PermissionError('回执不属于此聊天')
                    if action=='reconcile':
                        key=args.get('operation_id','')
                        op=s['operations'].get(key) or s['operations'].get(ended['node_id']+':'+key)
                        if not op or op.get('lease_id')!=args['lease_id']:raise PermissionError('操作不属于原租约')
                        if op['state']!=args.get('operation_state') or op['state'] not in {'confirmed','not_sent'}:
                            raise Conflict('原资源已交还，不能以重试改写已核实结果')
                        return {'recorded':True,'state':op['state'],'released':True}
                    from .module_dispatch import observe_control
                    observe_control(s['nodes'][ended['node_id']],holder,self.c.clock(),exited=True)
                    return {'released':True,'state':ended['state'],'node_id':ended['node_id']}
        if action=='result':
            # A receipt read neither updates a lease nor needs the write lock.
            # Extract this one receipt in SQL instead of loading/serializing
            # every historical screenshot twice in the global state document.
            key=text(args.get('lease_id'),'lease_id',160)+':'+text(args.get('request_id'),'request_id',160)
            with self.c.connect() as db:
                from .orchestration_storage import read_record
                db.execute('BEGIN')
                version=read_sections(db, ('version',))['version']
                if version!=1:raise Conflict('调度数据版本不兼容，拒绝读取回执')
                cmd=read_record(db,'direct_commands',key)
            if not cmd or cmd.get('owner')!=owner or cmd.get('holder_id')!=holder:raise PermissionError('操作回执不存在或不属于当前聊天')
            return self._receipt(cmd)
        with self.c.transaction() as (_,s):
            l,n,t=self._owned(s,owner,args,active=action not in {'finish','reconcile','context'})
            if action in {'finish','context'}:
                from .module_dispatch import observe_control
                observe_control(n,holder,self.c.clock(),exited=action=='finish')
            if l.get('resource_hold') and action in {'finish','context'}:
                return {**self._status(n,l),'released':False,'retained':True,'execution_ended':True,
                        'authority_revoked':True,'resource_hold':copy.deepcopy(l.get('hold',{})),
                        'next_action':'get_managed_test'}
            if action=='finish' and l.get('direct_finish'):return {'state':'stopping','released':False,'already_received':True}
            if l['revoked'] and action in {'context','finish'}:
                return {**self._status(n,l),'released':False,'authority_revoked':True,
                        'next_action':'get_managed_test','message':'停止要求已收到；不再发起业务操作，等待原浏览器退出及资源状态核实。'}
            if l['revoked'] and action!='reconcile':raise Conflict('旧执行权限已撤销')
            l['actor_seen']=self.c.clock();n['actor_seen']=self.c.clock()
            lid=l['id'];hid=l['runner_id']
            if action in {'browser','credentials'}:aid=self._account(l,args)
            if action=='wait':
                reason=text(args.get('reason'),'人工待办',4000)
                if bool(select_records(s.get('direct_commands',{}),lease_id=lid,state=('queued','running'))):raise Conflict('原浏览器操作尚在途；先核实回执再交给人工')
                l.update(human_mode=True,executor_fenced=True)
                l['waiting']={'since':self.c.clock(),'reason':reason}
                n.update(state='waiting_human',reason=reason)
                return {'state':'waiting_human','reason':reason,'scene_retained':True,'timeout_seconds':HUMAN_TIMEOUT}
            if action=='continue':
                l['progress_at']=self.c.clock()
                l.update(human_mode=False,executor_fenced=False)
                l.pop('waiting',None);n.update(state='running',reason='')
                return {'state':'running'}
            if action=='reconcile':
                key=args.get('operation_id','')
                op=s['operations'].get(key) or s['operations'].get(n['id']+':'+key)
                if not op or op['node_id']!=n['id']:raise PermissionError('操作不属于当前任务')
                state=args.get('operation_state')
                if state not in {'confirmed','not_sent'}:raise ValueError('只能根据证据确认已完成或明确未发送')
                evidence=text(args.get('reason'),'实际核实依据',4000)
                op.setdefault('history',[]).append({'state':op['state'],'at':self.c.clock()})
                op.update(state=state,result={'reconciliation':evidence})
                return {'recorded':True,'state':state}
            if action=='checkpoint':
                updated={**n.get('checkpoint',{}),**copy.deepcopy(args.get('checkpoint',{}))}
                changed=updated!=n.get('checkpoint',{})
                if changed:l['progress_at']=self.c.clock()
                n['checkpoint']=updated
                return {'saved':True,'changed':changed}
            if action=='finish':
                outcome=args.get('outcome','completed')
                if outcome not in {'completed','blocked','yield'}:raise ValueError('outcome 必须为 completed/blocked/yield')
                reason=args.get('reason','')
                if outcome=='completed' and bool(select_records(s['operations'],node_id=n['id'],state=('pending','unknown'))):
                    outcome='blocked';reason='存在未核实的业务操作；保留原证据和未验证项，不自动重试'
                l['direct_finish']={'outcome':outcome,'reason':reason,'children':args.get('children'),
                                    'checkpoint':copy.deepcopy(n.get('checkpoint',{}))}
                n.update(state='stopping',reason='等待浏览器确认退出后交还账号')
                l['revoked']=True
                return {'state':'stopping','released':False,'message':'已收到结束请求；浏览器退出后自动交还账号，不重跑业务。'}
            if action=='browser':
                if n['state']!='running':raise Conflict('浏览器尚未就绪或等待人工，请先读取状态')
                request=text(args.get('request_id'),'request_id',160)
                payload={'account_id':aid,'action':args.get('browser_action'),'parameters':args.get('parameters',{})}
                key=lid+':'+request;commands=s.setdefault('direct_commands',{})
                old=commands.get(key)
                if old:
                    if old['hash']!=digest(payload):raise Conflict('同一 request_id 不能用于不同操作')
                    return self._receipt(old)
                if payload['action']=='batch':
                    from .browser_batch import steps
                    steps(payload['parameters'])
                    if 'cases' in payload['parameters'] and not s['runners'][l['runner_id']].get('evidence',{}).get('case_execution'):
                        raise Conflict('当前执行机未支持逐条自动执行与回写；保留原现场，不能把用例计划降为无断言单步')
                if (payload['action'] in {'batch','check'} or 'response' in payload['parameters']
                        or 'snapshot_selector' in payload['parameters']):
                    host=s['runners'].get(l['runner_id'],{})
                    if not host.get('evidence',{}).get('browser_batch'):
                        raise Conflict('原执行连接尚未支持批量动作或摘要观察；当前租约继续用既有单步动作，本轮结束后升级')
                pending=select_records(commands,lease_id=lid,state=('queued','running'))
                if pending:raise Conflict('原操作仍在途，先按原 request_id 查询回执；不可重发业务操作')
                l['progress_at']=self.c.clock()
                commands[key]={'id':request,'lease_id':lid,'node_id':n['id'],'browser_action':payload['action'],
                               'owner':owner,'holder_id':holder,'hash':digest(payload),'state':'queued','created':self.c.clock(),
                               'payload':self.store._cipher.encrypt(json.dumps(payload).encode()).decode()}
                return self._receipt(commands[key])
            if action=='record' and args.get('record_action') not in {'record','reference','requirements'}:l['progress_at']=self.c.clock()
        auth={'owner':owner,'host_id':hid}
        if action=='context':return self.service.host_call(auth,'read',{'lease_id':lid})
        if action=='credentials':return self.service.host_call(auth,'account_credentials',{'lease_id':lid,'account_id':aid})
        if action=='record':
            method=args.get('record_action')
            if method not in {'record','cases','assets','publish','reference','requirements','save_requirements','dependency','fixture','shared_policy'}:raise ValueError('未知记录动作')
            values=copy.deepcopy(args.get('arguments',{}))
            # Captures are persisted by the host; arbitrary screenshot bytes remain
            # handled by the existing upload API with unchanged provenance rules.
            return self.service.host_call(auth,method,{**values,'lease_id':lid})
        raise ValueError('未知直接执行动作')

    def channel(self,owner,args):
        """Lease-bound auxiliary helper heartbeat, separate from browser calls."""
        values=args.get('arguments',{});cid=text(values.get('channel_id'),'channel_id',160)
        action=values.get('event')
        with self.c.transaction() as (_,state):
            ended=state.get('direct_settlements',{}).get(args.get('lease_id'))
            if ended:
                if ended['owner']!=owner or ended['holder_id']!=args.get('holder_id'):raise PermissionError('通道归属不一致')
                return {'allowed':False,'released':True,'closed':True}
            lease,node,task=self._owned(state,owner,args,active=False)
            channels=lease.setdefault('auxiliary_channels',{})
            valid=(not lease['revoked'] and task['intent']=='run' and node.get('control_intent','run')=='run'
                   and lease['revision']==node['revision'] and lease['epoch']==state['epoch'])
            if action=='register':
                if not valid or lease.get('direct_finish'):raise Conflict('租约已撤权，不能新增辅助浏览器')
                if not state['runners'][lease['runner_id']].get('evidence',{}).get('auxiliary_channels'):
                    raise Conflict('原执行连接尚未升级到租约辅助浏览器协议；不能启动不受管理的辅助通道')
                if lease['mode']!='exclusive' or lease.get('exploration_bootstrap'):raise Conflict('共享探索及初始化使用原受控浏览器；辅助脚本没有共享请求约束，先申请独占')
                if type(values.get('pid')) is not int or values['pid']<=0:raise ValueError('pid 无效')
                directory=text(values.get('directory'),'私有会话目录',3000)
                prior=channels.get(cid)
                if prior and (prior['pid']!=values['pid'] or prior['directory']!=directory):raise Conflict('通道 ID 不能替换进程')
                if not prior:
                    from .resource_scheduler import ResourceScheduler
                    available=ResourceScheduler(self.c,state,self.c.clock()).runner_candidates(node,1)
                    if not any(r['id']==lease['runner_id'] for r in available):raise Conflict('当前执行机没有额外浏览器容量，请继续使用原受控浏览器')
                    channels[cid]={'id':cid,'pid':values['pid'],'directory':directory,'created_at':self.c.clock(),'state':'pending','last_seen':self.c.clock(),'progress':0}
                    lease['browser_units']=lease.get('browser_units',1)+1
            channel=channels.get(cid)
            if not channel:raise Conflict('辅助通道尚未登记')
            if action=='closed':
                if channel['state']!='exited':lease['browser_units']=max(1,lease.get('browser_units',1)-1)
                channel.update(state='exited',exited_at=self.c.clock())
            elif action in {'register','heartbeat'}:
                channel['last_seen']=self.c.clock()
                if valid and channel['state']=='bound':
                    lease['actor_seen']=self.c.clock();node['actor_seen']=self.c.clock()
                    progress=values.get('progress',0)
                    if type(progress) is int and progress>channel.get('progress',0):
                        channel['progress']=progress;lease['progress_at']=self.c.clock()
                        node.setdefault('auxiliary_started_at',self.c.clock())
            else:raise ValueError('通道事件必须为 register/heartbeat/closed')
            return {'allowed':valid and channel['state']=='bound','state':channel['state'],
                    'revoked':not valid,'closed':channel['state']=='exited',
                    'retain_scene': bool(node.get('checkpoint',{}).get('retain_browser') or
                                         node.get('checkpoint',{}).get('retain_scene'))}

    def finish_unallocated(self,owner,args):
        holder=text(args.get('holder_id'),'holder_id',160)
        with self.c.transaction() as (_,state):
            task=self.c.owned(state['tasks'],owner,args.get('task_id'))
            if task.get('execution_route') not in {'local_browser','native_browser'}:raise Conflict('原任务属于后台执行')
            nodes=[state['nodes'][nid] for nid in task['node_ids'] if not state['nodes'][nid].get('child_ids')]
            if args.get('node_id'):nodes=[n for n in nodes if n['id']==args['node_id']]
            if len(nodes)!=1:raise ValueError('请指定本次结束的 node_id，不结束其他模块')
            n=nodes[0]
            offer=n.get('dispatch_offer')
            binding=n.get('executor_dispatch') or {}
            if (binding.get('resumed_from_dispatch_id')
                    and args.get('dispatch_id') != binding.get('dispatch_id')):
                raise Conflict('退出回执属于原节点的旧派发；请使用本次续测绑定')
            if (offer and not n.get('executor_dispatch') and offer.get('holder_id') == holder
                    and args.get('dispatch_id') and args['dispatch_id'] != offer['id']):
                raise Conflict('退出回执不属于当前派发，请沿用原 dispatch_id')
            if offer and (offer.get('holder_id')!=holder or offer['state'] in {'expired','cancelled'}):
                from .module_dispatch import observe_control
                observe_control(n,holder,self.c.clock(),exited=True)
                return {'released':True,'state':n['state'],'node_id':n['id'],'executor_exit_only':True}
            if n.get('direct_holder') not in {None,holder}:raise PermissionError('节点由另一聊天持有')
            from .module_dispatch import observe_control
            observe_control(n,holder,self.c.clock(),exited=True)
            if any(l['node_id']==n['id'] for l in state['leases'].values()):raise Conflict('账号已分配，请使用原 lease_id 结束并等待退出确认')
            if n['state'] not in {'completed','blocked','stopped'}:
                n.update(state='blocked' if args.get('outcome')=='blocked' else 'completed',
                         reason=args.get('reason') or '本轮已结束；未取得执行资源的用例保持未验证',
                         result='partial',coverage_complete=False,finalization_pending=True,revision=n['revision']+1)
            n.pop('direct_holder',None)
            nid=n['id'];result={'released':True,'state':n['state'],'node_id':nid}
        self.service.finalize_settlement(owner,nid);self.service.notify_final_report(owner,nid)
        return result

    def finish_project(self,owner,pid):
        with self.c.connect() as db:
            db.execute('BEGIN')
            state=read_metadata_without_history(db)
        results=[]
        for lease in state['leases'].values():
            node=state['nodes'][lease['node_id']]
            if lease.get('direct') and node['owner']==owner and (node.get('record_project_id')==pid or (node['project_id']==pid and not node.get('parent_id'))):
                results.append(self.call(owner,{'action':'finish','holder_id':node['direct_holder'],'lease_id':lease['id'],'outcome':'completed'}))
        for node in state['nodes'].values():
            if node['owner']!=owner or node.get('child_ids') or node.get('parent_id'):continue
            if node['project_id']!=pid or state['tasks'][node['task_id']].get('execution_route')!='local_browser':continue
            if node['state'] not in {'queued','paused'} or any(l['node_id']==node['id'] for l in state['leases'].values()):continue
            results.append(self.finish_unallocated(owner,{'holder_id':node.get('direct_holder') or 'workflow-finish','task_id':node['task_id'],'node_id':node['id'],'outcome':'completed'}))
        return results

    @staticmethod
    def _receipt(command):
        receipt={k:copy.deepcopy(command[k]) for k in ('id','state','result','error') if k in command}
        timing={k:command[k] for k in ('created','started','completed') if k in command}
        if 'started' in timing and 'created' in timing:
            timing['queue_seconds']=round(max(0,timing['started']-timing['created']),3)
        if 'completed' in timing and 'started' in timing:
            timing['execution_seconds']=round(max(0,timing['completed']-timing['started']),3)
        receipt['timing']=timing
        result=command.get('result',{})
        if isinstance(result,dict) and result.get('resource_wait',{}).get('end_turn'):
            receipt['resource_wait']=copy.deepcopy(result['resource_wait'])
        return receipt

    @staticmethod
    def _command_outcome(state,node_id,lease_id,args):
        value=args['state'];result=copy.deepcopy(args.get('result',{}))
        # The browser's durable operation ledger is more precise than a host's
        # generic exception. Only the same command on the same lease qualifies.
        operation=state['operations'].get(node_id+':'+args['request_id'])
        if (value=='unknown' and operation and operation['lease_id']==lease_id
                and operation['state']=='not_sent'):
            value='blocked'
            result.update(operation_state='not_sent',business_failure=False,
                          instruction='原动作确认未发送。根据当前页面修正操作；原请求不自动重放。')
        return value,result

    def host(self,owner,hid,action,args):
        if action=='direct_poll' and self._empty_poll(owner,hid,args):
            return {}
        # Completion may arrive after revocation; it remains evidence, never authority.
        # Validate once, atomically with the state transition below.
        with self.c.transaction() as (_,s):
            l=s['leases'].get(args['lease_id'])
            if not l and action in {'direct_result','operation_complete'}:
                return self._late_evidence(s,owner,hid,action,args)
            if not l or l['runner_id']!=hid:raise PermissionError('执行归属已变化')
            n=self.c.owned(s['nodes'],owner,l['node_id'])
            if action=='browser_ready':
                event=s['outbox'].get(args.get('event_id'))
                if not l.get('direct') or not event or event['lease_id']!=l['id'] or event['kind']!='start':
                    raise PermissionError('浏览器回执不属于当前直接执行派发')
                if l['revoked'] or event['epoch']!=s['epoch'] or event['revision']!=n['revision'] or s['tasks'][n['task_id']]['intent']!='run':
                    raise Conflict('派发已撤销，浏览器就绪不能恢复执行权限')
                event.update(status='acknowledged',browser_ready=True,browser_ready_at=self.c.clock())
                l['browser_ready_at']=self.c.clock()
                n['browser_ready_at']=self.c.clock()
                n.update(state='running',reason='浏览器已就绪，等待当前执行者开展业务操作')
                return {'browser_ready':True,'business_started':bool(n.get('business_started_at'))}
            if action in {'direct_poll','operation_begin','reconcile'} and (l['revoked'] or l['epoch']!=s['epoch'] or l['revision']!=n['revision'] or s['tasks'][n['task_id']]['intent']!='run'):raise Conflict('旧执行权限已撤销')
            if action=='direct_poll':
                if not l.get('direct'):raise PermissionError('不是当前聊天执行任务')
                if l.get('waiting'):return {}
                cmd=next(iter(select_records(s.setdefault('direct_commands',{}),lease_id=l['id'],state='queued')),None)
                if not cmd:return {}
                cmd.update(state='running',started=self.c.clock())
                payload=json.loads(self.store._cipher.decrypt(cmd['payload'].encode()))
                command={**payload,'id':cmd['id']}
                if (s['runners'].get(hid,{}).get('evidence',{}).get('inline_operation_begin')
                        and payload['action'] not in {'batch','prepare_exploration'}):
                    # Same transaction/guards as operation_begin, piggybacked on
                    # command delivery. Old hosts retain their original protocol.
                    key=n['id']+':'+text(cmd['id'],'operation_id',160)
                    command['begin_receipt']=self._begin_operation(s,l,n,owner,hid,key,
                        {'action':payload['action'],'hash':digest([payload['account_id'],payload['action'],payload.get('parameters',{})])})
                return {'command':command}
            if action=='direct_result':
                cmd=s.get('direct_commands',{}).get(l['id']+':'+args['request_id'])
                if not cmd:raise Conflict('操作回执不存在')
                if cmd['state'] in {'running','unknown'}:
                    value,result=self._command_outcome(s,n['id'],l['id'],args)
                    cmd.update(state=value,result=result,completed=self.c.clock())
                    cmd.pop('payload',None)
                return self._receipt(cmd)
            key=args.get('operation_id','')
            if not key.startswith(l['node_id']+':'):key=l['node_id']+':'+text(key,'operation_id',160)
            if action=='reconcile':
                op=s['operations'].get(key)
                if not op or op['node_id']!=n['id']:raise PermissionError('操作不属于当前任务')
                state=args.get('operation_state')
                if state not in {'confirmed','not_sent'}:raise ValueError('核实结果须为 confirmed/not_sent')
                evidence=text(args.get('reason'),'核实依据',4000)
                op.setdefault('history',[]).append({'state':op['state'],'at':self.c.clock()})
                op.update(state=state,result={'reconciliation':evidence})
                return {'recorded':True}

            if action=='operation_begin':
                return self._begin_operation(s,l,n,owner,hid,key,args)
            if action=='operation_complete':
                op=s['operations'].get(key)
                if not op or op['lease_id']!=l['id']:raise PermissionError('操作不属于当前租约')
                if op['action']=='prepare_exploration' and op['state']=='confirmed':
                    return {'saved':True,'mode':l['mode'],'exploration_bootstrap':l.get('exploration_bootstrap',False),
                            'resource_version':l.get('resource_version',1),
                            'exploration_prepared':bool((op.get('result') or {}).get('exploration_prepared'))}
                if op['state'] in {'pending','unknown'}:
                    op.update(state=args['state'],result=copy.deepcopy(args.get('result',{})))
                    l['progress_at']=self.c.clock()
                    observed=args.get('result') or {}
                    if args['state']=='confirmed' and observed.get('url','').startswith(('http://','https://')):
                        n.setdefault('business_started_at',self.c.clock())
                        n['last_business_observation']={'operation_id':key,'at':self.c.clock(),'action':op['action']}
                        if n['state']=='running' and not l['revoked'] and s['tasks'][n['task_id']]['intent']=='run':
                            n['reason']='已开始页面操作，当前执行者正在推进测试'
                from .exploration_profiles import promote, accept_observed
                prepared=False
                if op['action']=='prepare_exploration' and args['state']=='confirmed' and args.get('exploration_verification'):
                    prepared=accept_observed(self.c,s,l,n,args['exploration_verification'],args.get('exploration_seed'))
                    if not prepared:
                        op['result']={**op.get('result',{}),'exploration_prepared':False,'requires_exclusive':True,
                                      'reason':'核验完成时资源或控制状态已经变化，平台未开放共享'}
                elif (op['action']=='prepare_exploration' and args['state']=='confirmed'
                      and (op.get('result') or {}).get('exploration_prepared') is False
                      and not (op.get('result') or {}).get('preparation_pending')):
                    policy=s['policies'].get(l.get('policy_id'),{})
                    if l.get('exploration_bootstrap') and l['mode']=='exclusive':
                        policy.update(enabled=False,automatic_fault=True,preparation='failed',
                                      preparation_reason=op['result'].get('reason','实时核验未通过'))
                        l.update(exploration_bootstrap=False,browser_units=len(l['account_ids']),
                                 resource_version=l.get('resource_version',1)+1)
                        # The existing lease stays exclusive; an automatic
                        # failure is not a permanent user request for exclusive
                        # exploration on every later attempt.
                        n.update(reason=policy['preparation_reason']+'；当前账号独占续接')
                else:promote(self.c,s,l,n,args.get('exploration_observation'))
                return {'saved':True,'mode':l['mode'],'exploration_bootstrap':l.get('exploration_bootstrap',False),
                        'resource_version':l.get('resource_version',1),'exploration_prepared':prepared}

    def _late_evidence(self,state,owner,hid,action,args):
        """A retired host can append its original observation, never regain a lease."""
        lid=args['lease_id']
        dispatch=next((e for e in state['outbox'].values() if e['lease_id']==lid and e['runner_id']==hid and e['kind']=='start'),None)
        if not dispatch:raise PermissionError('历史回执不属于此执行连接')
        self.c.owned(state['nodes'],owner,dispatch['node_id'])
        if action=='direct_result':
            item=state.get('direct_commands',{}).get(lid+':'+text(args.get('request_id'),'request_id',160))
            allowed={'completed','blocked','unknown'}
        else:
            key=args.get('operation_id','')
            if not key.startswith(dispatch['node_id']+':'):key=dispatch['node_id']+':'+text(key,'operation_id',160)
            item=state['operations'].get(key);allowed={'confirmed','not_sent','unknown'}
        if not item or item['lease_id']!=lid:raise PermissionError('历史操作不属于原租约')
        value=args.get('state');result=copy.deepcopy(args.get('result',{}))
        if action=='direct_result':
            value,result=self._command_outcome(state,dispatch['node_id'],lid,args)
        if value not in allowed:raise ValueError('历史回执状态错误')
        if item['state'] in {'completed','blocked','confirmed','not_sent','cancelled'}:
            if item['state']!=value or item.get('result',{})!=result:raise Conflict('已确认历史回执不可覆盖')
        else:
            item.setdefault('history',[]).append({'state':item['state'],'at':self.c.clock()})
            item.update(state=value,result=result,late_evidence=True,completed=self.c.clock())
            item.pop('payload',None)
        return {'saved':True,'historical':True,'authority_restored':False}

    def _empty_poll(self,owner,hid,args):
        """Fast idle path; queued delivery still rechecks under the write lock.

        All fields come from one database snapshot. No history pruning or caller heartbeat/progress renewal.
        """
        lid=text(args.get('lease_id'),'lease_id',160)
        with self.c.connect() as db:
            db.execute('BEGIN')
            state=read_sections(db, ('version', 'epoch'))
            if state['version']!=1:raise Conflict('调度数据版本不兼容，拒绝派发')
            lease=read_entries(db, 'leases', keys=[lid]).get(lid)
            if not lease or lease['runner_id']!=hid:raise PermissionError('租约不属于此执行连接')
            nodes=read_entries(db, 'nodes', keys=[lease['node_id']])
            node=self.c.owned(nodes,owner,lease['node_id'])
            task=read_entries(db, 'tasks', keys=[node['task_id']])[node['task_id']]
            queued=db.execute("""SELECT EXISTS(SELECT 1 FROM state_history
                    WHERE kind='direct_commands' AND meta::json->>'lease_id'=%s
                    AND meta::json->>'state'='queued')""",(lid,)).fetchone()[0]
        if lease['revoked'] or task['intent']!='run' or lease['epoch']!=state['epoch'] or lease['revision']!=node['revision']:
            raise Conflict('执行授权已撤销')
        if not lease.get('direct'):raise PermissionError('不是当前聊天执行任务')
        return bool(lease.get('waiting')) or not queued

    def _begin_operation(self,s,l,n,owner,hid,key,args):
        op=s['operations'].get(key)
        if op:
            if op['hash']!=args['hash']:raise Conflict('操作标识已用于其他动作')
            return {'execute':False,'state':op['state'],'result':op.get('result',{}),'mode':l['mode'],'exploration_bootstrap':l.get('exploration_bootstrap',False),'resource_version':l.get('resource_version',1)}
        # Reads remain available to reconcile an uncertain business write.
        if args['action'] not in {'snapshot','screenshot','tabs','wait','check'} and bool(select_records(s['operations'],node_id=n['id'],state=('pending','unknown'))):
            raise Conflict('存在结果未知的操作；先读取页面核实，不能盲目重放')
        s['operations'][key]={'id':key,'node_id':n['id'],'lease_id':l['id'],'hash':args['hash'],'action':args['action'],'state':'pending','owner':owner,'runner_id':hid,'created':self.c.clock()}
        return {'execute':True,'mode':l['mode'],'exploration_bootstrap':l.get('exploration_bootstrap',False),'resource_version':l.get('resource_version',1)}
