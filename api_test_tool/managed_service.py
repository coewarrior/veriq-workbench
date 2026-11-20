"""Authenticated execution-host protocol and existing UI-report integration."""
from __future__ import annotations
import copy
from contextlib import contextmanager, nullcontext
import base64
import fnmatch
import hashlib
import json
import re
import secrets
import shutil
import time
from urllib.parse import urlsplit, parse_qs, unquote
from uuid import uuid4

from .orchestration import Conflict, text, digest, uid, queue_key
from . import database, ui_records
from .orchestration_storage import select_records, read_entries, read_sections, read_node_fields, read_metadata_without_history


def origin(url):
    p=urlsplit(url)
    if p.scheme not in {'http','https'} or not p.hostname or p.username or p.password:
        raise ValueError('仅允许无内嵌凭据的 HTTP(S) 地址')
    return f'{p.scheme}://{p.netloc.lower()}'


class ManagedService:
    def __init__(self, controller, static):
        self.controller=controller
        self.store=controller.store
        self.static=static
        from .managed_console import BrowserConsole
        self.console=BrowserConsole(controller)
        from .direct_execution import DirectExecution
        self.direct=DirectExecution(self)
        self._report_workers=set()
        controller.report_activity=self.report_activity
        controller.report_worker_node_ids=lambda: self.report_activity()['node_ids']
        controller.settlement_callback=self.finalize_pending

    def report_activity(self):
        with self.controller.admission_lock:
            return {'count': len(self._report_workers),
                    'node_ids': sorted({node_id for _, node_id in self._report_workers})}

    @contextmanager
    def report_worker(self, owner, node_id, *, background=False):
        """Count entered work, never a durable queue marker or report intent.

        Registration and drain admission share the HTTP/health lock. This lock
        is released before taking DB -> Store locks, and removal happens after
        all report work, including notification bookkeeping, has returned.
        """
        key=(owner, node_id)
        with self.controller.admission_lock:
            admitted=key not in self._report_workers and not (background and self.controller.draining())
            if admitted:
                self._report_workers.add(key)
        try:
            yield admitted
        finally:
            if admitted:
                with self.controller.admission_lock:
                    self._report_workers.remove(key)

    def pair(self, owner, host_id=None):
        code=owner+'.'+secrets.token_urlsafe(32)
        with self.controller.transaction() as (db,s):
            if host_id:
                host=self.controller.owned(s['runners'],owner,host_id)
                if host.get('platform_managed'):
                    raise Conflict('平台执行连接由服务器自动维护，无需重新配对')
            s.setdefault('host_pairs',{})[hashlib.sha256(code.encode()).hexdigest()]={'owner':owner,'host_id':host_id,'expires':time.time()+600}
            self.controller.audit(db,owner,'host.pair.issued','')
        return {'code':code,'expires_in':600}

    def redeem(self, code):
        if not isinstance(code,str):
            raise PermissionError('连接码无效')
        with self.controller.transaction() as (db,s):
            p=s.setdefault('host_pairs',{}).pop(hashlib.sha256(code.encode()).hexdigest(),None)
            if not p or p['expires']<time.time():
                raise PermissionError('连接码无效或已过期')
            hid=p.get('host_id') or uid()
            s['host_tokens']={k:v for k,v in s.get('host_tokens',{}).items() if v['host_id']!=hid}
            token=secrets.token_urlsafe(48)
            s.setdefault('host_tokens',{})[hashlib.sha256(token.encode()).hexdigest()]={'owner':p['owner'],'host_id':hid}
            self.controller.audit(db,p['owner'],'host.paired',hid)
        return {'host_id':hid,'token':token}

    def authenticate(self, token):
        with self.controller.connect() as db:
            s=read_sections(db, ('host_tokens',))
        item=s.get('host_tokens',{}).get(hashlib.sha256(token.encode()).hexdigest())
        if not item:
            raise PermissionError('执行连接已失效')
        return item

    def revoke(self, owner, host_id):
        with self.controller.transaction() as (db,s):
            r=self.controller.owned(s['runners'],owner,host_id)
            if r.get('platform_managed'):
                raise Conflict('平台执行连接由服务器维护；暂停或停止测试请操作对应任务')
            r['enabled']=False
            s['host_tokens']={k:v for k,v in s.get('host_tokens',{}).items() if v['host_id']!=host_id}
            for l in s['leases'].values():
                if l['runner_id']==host_id:
                    l['revoked']=True
                    l['human_mode']=False
                    n=s['nodes'][l['node_id']]
                    n.update(state='isolated',reason='执行连接授权已撤销，现场等待核实')
            self.controller.audit(db,owner,'host.revoked',host_id)
        return {'revoked':True}

    def lease(self, owner, host_id, lease_id, *, active=True, human=False, history_action=None, operation_id=None, include_baseline=False):
        with self.controller.connect() as db:
            db.execute('BEGIN')
            # Internal lease consumers do not use archived cases. Reporting and
            # recovery writes still read complete nodes in their transactions.
            s=read_metadata_without_history(db)
            l=s['leases'].get(lease_id)
            if not l or l['runner_id']!=host_id:
                raise PermissionError('租约不属于此执行连接')
            n=self.controller.owned(s['nodes'],owner,l['node_id'])
            t=s['tasks'][n['task_id']]
            if include_baseline:
                t=read_entries(db, 'tasks', keys=[n['task_id']], include_baseline=True,
                               baseline_fields=('cases', 'sources'))[n['task_id']]
                s['tasks'][n['task_id']]=t
            if active and not (human and l.get('human_mode') and n['state'] in {'retained','waiting_human','isolated'}) and (l['revoked'] or t['intent']!='run' or (not l.get('native_browser') and l['epoch']!=s['epoch']) or l['revision']!=n['revision']):
                raise Conflict('执行授权已撤销')
            if history_action in {'read','operations','operation_result'}:
                # Read only the requested evidence in the same database snapshot.
                # Lease/network authorization never materializes old screenshots.
                where="kind='operations' AND meta::json->>'node_id'=%s"
                params=[n['id']]
                if history_action=='read':
                    where+=" AND meta::json->>'lease_id'!=%s AND meta::json->>'state' IN ('pending','unknown')"
                    params.append(lease_id)
                elif history_action=='operations':
                    where+=" AND meta::json->>'lease_id'=%s"
                    params.append(lease_id)
                else:
                    where+=" AND key=%s"
                    params.append(operation_id)
                s['operations']={}
                for key,meta,result in db.execute('SELECT key,meta,result FROM state_history WHERE '+where,params):
                    item=json.loads(meta)
                    if result is not None:item['result']=json.loads(result)
                    s['operations'][key]=item
            return l,n,t,s

    def configure_account(self, owner, aid, data):
        # Reuse maintained adapters; ordinary users only request a login window.
        profile=data.get('login',{})
        if not isinstance(profile,dict):
            raise ValueError('登录配置必须为对象')
        with self.controller.transaction() as (db,s):
            a=self.controller.owned(s['accounts'],owner,aid)
            project_id=data.get('account_project_id')
            if project_id and project_id not in a['projects']:
                raise ValueError('账号未绑定到此项目')
            projects=[p for p in a['projects'] if p in s.get('account_projects',{})]
            urls={self.controller.account_projects.login(s,owner,p) for p in projects}
            if len(urls)>1:raise Conflict('账号关联项目的登录地址不一致，请先在项目管理中统一')
            login_url=next(iter(urls),a.get('login',{}).get('url') or a['target'])
            if profile.get('url') and profile['url']!=login_url:
                raise ValueError('登录地址由项目统一维护')
            profile={**a.get('login',{}),**profile,'url':login_url}
            profile.setdefault('url',a['target'])
            for field in ('identity_selector','tenant_selector','role_selector'):
                if profile.get(field):text(profile[field],field,2000)
            if origin(profile['url'])!=origin(a['target']):
                raise ValueError('登录入口必须属于登记系统')
            if any(aid in l['account_ids'] for l in s['leases'].values()):
                raise Conflict('账号占用中，不能替换登录与身份配置')
            if not isinstance(profile.get('allowed_origins',[]),list):raise ValueError('allowed_origins 须为列表')
            for value in profile.get('allowed_origins',[]):
                if origin(value)!=value:raise ValueError('附加域必须是规范 origin')
            a['login']=copy.deepcopy(profile)
            a['state']='needs_login'
            a['verified_identity']=False
            a['login_attempt']=uid()
            a['login_requested']=True
            a['login_message']='等待完成登录，系统将自动核验账号、租户和角色'
            a.pop('login_host',None)
            self.controller.audit(db,owner,'account.login.requested',aid)
        return {'account_id':aid,'status':'needs_login'}

    def change_account(self, owner, aid, data, *, delete=False):
        # Lock order matches console submission: console lock, then controller DB.
        with self.console.lock:
            self.console._prune()
            sessions=[sid for sid,x in self.console.sessions.items() if x['owner']==owner and x['target']['account_id']==aid]
            if any(v['state'] in {'queued','claimed'} for sid in sessions for v in self.console.sessions[sid]['commands'].values()):
                raise Conflict('登录现场仍有操作在途，请等待回执后再编辑或删除')
            manager=self.controller.account_management
            result=manager.delete(owner,aid,data) if delete else manager.edit(owner,aid,data)
            for sid in sessions:self.console.sessions.pop(sid,None)
            return result

    def save_policy(self, owner, data):
        aid=text(data.get('account_id'),'account_id')
        rules=data.get('rules')
        if not isinstance(rules,list) or not rules:
            raise ValueError('请登记经核验的具体请求规则，不把 GET 自动等同于无副作用')
        normalized=[]
        for r in rules:
            if not isinstance(r,dict) or r.get('effect') not in {'verified_read','isolated_write'}:
                raise ValueError('共享请求效果必须已核验')
            for field in ('origin','path','method'):
                text(r.get(field),field)
            if origin(r['origin'])!=r['origin'].rstrip('/') or not r['path'].startswith('/') or r['path']=='*':
                raise ValueError('请求规则须明确 origin 和路径')
            if r['effect']=='isolated_write' and not r.get('namespace_field'):
                raise ValueError('隔离写入须绑定当前执行命名空间字段')
            for key in ('query_equals','body_equals','query_patterns','body_patterns'):
                if not isinstance(r.get(key,{}),dict):raise ValueError(key+' 必须为对象')
            for pattern in [*r.get('query_patterns',{}).values(),*r.get('body_patterns',{}).values()]:
                text(pattern,'参数模式',256);re.compile(pattern)
            normalized.append(copy.deepcopy(r))
        evidence=text(data.get('evidence'),'核验依据',6000)
        compatible=data.get('session_compatible',False)
        if not isinstance(compatible,bool):raise ValueError('session_compatible 必须为布尔值')
        compatibility_evidence=(text(data.get('compatibility_evidence') or evidence,'并行会话兼容依据',6000)
                                if compatible else '')
        operations={k:{'effect':'verified_read' if k in {'snapshot','screenshot','wait'} else 'local','adapter':'playwright'}
                    for k in ('navigate','snapshot','screenshot','click','fill','press','select','wait','upload','back','tabs','switch_tab')}
        policy_id=uid()
        with self.controller.transaction() as (db,s):
            account=self.controller.owned(s['accounts'],owner,aid)
            if data['project_id'] not in account['projects']:raise PermissionError('账号未授权此项目')
            s['policies'][policy_id]={'id':policy_id,'owner':owner,'project_id':data['project_id'],
                'version':text(data.get('version'),'version'),'operations':operations,'evidence':evidence,
                'enabled':True,'rules':normalized,'approved_by':owner,
                'session_compatible':compatible,'compatibility_evidence':compatibility_evidence}
            account['policy_id']=policy_id
            self.controller.audit(db,owner,'policy.approved',policy_id)
        return {'policy_id':policy_id}

    def request_allowed(self, owner, host_id, args):
        l,n,t,s=self.lease(owner,host_id,args['lease_id'],human=True)
        aid=args['account_id']
        if aid not in l['account_ids']:
            raise PermissionError('账号不属于当前资源集合')
        a=s['accounts'][aid]
        if time.time()-s['runners'][host_id]['heartbeat']>60:raise Conflict('执行连接心跳失效')
        url=args['url']; target=origin(url)
        if n['state']!='running' and not l.get('human_mode'):raise Conflict('轮次尚未确认启动，禁止浏览器请求')
        if l['mode']=='exclusive':
            # Business domains and third-party assets require explicit project policy.
            allowed={origin(a['target'])}
            allowed.update(a.get('login',{}).get('allowed_origins',[]))
            if target not in allowed:
                raise PermissionError('请求越出当前账号目标域')
            return {'allowed':True,'effect':'unknown'}
        policy=s['policies'].get(l['policy_id'])
        if not policy or not policy['enabled']:
            raise PermissionError('共享策略已失效')
        p=urlsplit(url); query=parse_qs(p.query,keep_blank_values=True)
        body=args.get('body',{})
        decoded=unquote(p.path)
        if any(x in {'.','..'} for x in decoded.split('/')) or '\\' in decoded or re.search(r'%2f|%5c|%25',p.path,re.I):
            raise PermissionError('共享请求路径含未核验的编码或目录跳转')
        if not isinstance(body,dict):raise PermissionError('共享请求体结构未经核验')
        for r in policy.get('rules',[]):
            if r['origin'].rstrip('/')!=target or r['method'].upper()!=args['method'].upper() or not fnmatch.fnmatchcase(p.path,r['path']):
                continue
            permitted_query=set(r.get('query_equals',{}))|set(r.get('query_patterns',{}))
            permitted_body=set(r.get('body_equals',{}))|set(r.get('body_patterns',{}))|({r['namespace_field']} if r.get('namespace_field') else set())
            if set(query)-permitted_query or set(body)-permitted_body:continue
            if any(k not in query or any(not re.fullmatch(pattern,v) for v in query[k]) for k,pattern in r.get('query_patterns',{}).items()):continue
            if any(k not in body or not isinstance(body[k],str) or not re.fullmatch(pattern,body[k]) for k,pattern in r.get('body_patterns',{}).items()):continue
            if any(query.get(k)!=([v] if isinstance(v,str) else v) for k,v in r.get('query_equals',{}).items()):
                continue
            if any(not isinstance(body,dict) or body.get(k)!=v for k,v in r.get('body_equals',{}).items()):
                continue
            if r['effect']=='isolated_write' and (not isinstance(body,dict) or body.get(r['namespace_field'])!=l['context_id']):
                continue
            return {'allowed':True,'policy_version':policy['version'],'effect':r['effect']}
        raise PermissionError('此请求未进入共享允许集合；保存现场后申请独占探索')

    def report_project(self, owner, node, task):
        if node.get('record_successor_node_id'):
            raise Conflict('原模块记录已交给续测节点；旧执行者不能覆盖续测，历史报告仍可读取')
        if node.get('continuation_source'):
            from .module_continuation import report_project
            return report_project(self.store, owner, node, task)
        # A normal session's first module uses its existing record, including a
        # prepared regression/continuation baseline and original correlations.
        parent=self.store.get_project(owner,task['project_id'])
        if task.get('session_workflow') and not task.get('independent_module_records') and not task.get('_baseline_present', task.get('baseline')) and node['id'] in task['node_ids'] and not node.get('parent_id') and len(task['node_ids'])==1:
            return {**parent,**({'ui_execution_id':node['record_execution_id']} if node.get('record_execution_id') else {})}
        filename='managed-'+node['id']+'.md'
        with self.store._lock:
            p=None
            if node.get('record_project_id'):
                try:
                    bound=self.store.get_project(owner,node['record_project_id'])
                except FileNotFoundError:
                    bound=None
                if (bound and bound.get('filename')==filename and bound.get('managed_node_id')==node['id']
                        and bound.get('managed_task_id')==task['id']):
                    p=bound
            if p is None:
                p=next((p for p in self.store.list_projects(owner) if p.get('filename')==filename),None)
            parent=self.store.get_project(owner,task['project_id'])
            initialized=bool(p and p.get('managed_node_id'))
            source=(task.get('baseline') or {}).get('sources',{}).get(node['key'])
            material_parent=source['project'] if source else parent
            if not p:
                document=source['document'] if source else (self.store.project_dir(owner,parent['id'])/parent['document_file']).read_text()
                p=self.store.create_project(owner,node['title'],filename,document,
                    round_parent_id=parent['id'] if parent.get('test_kind')=='ui' else None)
                source_dir=self.store.project_dir(owner,material_parent['id'])/'inputs'/'requirements'
                if source_dir.is_dir():shutil.copytree(source_dir,self.store.project_dir(owner,p['id'])/'inputs'/'requirements',dirs_exist_ok=True)
                try:
                    design=source['requirements'] if source else self.store.load_asset(owner,parent['id'],'requirement-design')
                    self.store.save_asset(owner,p['id'],'requirement-design',copy.deepcopy(design))
                except FileNotFoundError:pass
            if not initialized:
                p=self.store.update_project(owner,p['id'],{
                    'test_kind':'ui','managed_node_id':node['id'],'managed_task_id':task['id'],
                    'managed_parent_project_id':parent['id'],
                    'ui_target_url':parent.get('ui_target_url') or (node['requirements'][0]['target'] if node['requirements'] else ''),
                    'ui_execution_permission':parent.get('ui_execution_permission',{'key':'full'}),
                    'ui_scene_retention':parent.get('ui_scene_retention',{'key':'none'}),
                    'ui_requirement_attachments':material_parent.get('ui_requirement_attachments',[]),
                    'task':{**material_parent.get('task',{}),'goal':task['goal']+'\n当前模块：'+node['scope']}})
            frozen=(task.get('baseline') or {}).get('cases',{}).get(node['key'],[])
            if frozen and not p.get('managed_baseline_seeded'):
                existing=ui_records.load(self.store,owner,p['id'],p['ui_execution_id']) if p.get('ui_execution_id') else {'cases':[],'revision':0,'id':''}
                known={c['case_id'] for c in existing['cases']}
                cases=[copy.deepcopy(c) for c in frozen if c['case_id'] not in known]
                for case in cases:
                    case.update(status='not_run',actual='',conclusion='',executed_at='',action_context={},upload_attempts=[])
                    for point in case.get('checkpoints',[]):
                        point.update(status='not_run',actual='',verification_mode='design',evidence=[],correlation={},inherited_from={},action_context={})
                revision=existing['revision'];eid=existing['id']
                for i in range(0,len(cases),200):
                    result=ui_records.save_cases(self.store,owner,p['id'],cases[i:i+200],eid,revision)
                    eid,revision=result['execution_id'],result['revision']
                p=self.store.update_project(owner,p['id'],{'managed_baseline_seeded':True})
            return {**p,**({'ui_execution_id':node['record_execution_id']} if node.get('record_execution_id') else {})}

    def report(self, owner, task_id):
        snap=self.controller.snapshot(owner,task_id,include_history=True)
        from .ui_round_report import task_records
        records=task_records(self.store,owner,snap)
        counts={k:0 for k in [*ui_records.LABELS,'retry_passed']}
        # Select the latest facts before excluding split aggregates; shared IDs count once.
        cases={}
        for module in records:
            for case in module['record']['cases']:
                previous=cases.get(case['case_id'])
                if previous and previous.get('updated_at','')>case.get('updated_at',''):
                    continue
                cases[case['case_id']]=case
        cases={case['case_id']:case for case in ui_records.active_cases(cases.values())}
        for case in cases.values():counts[case['managed_status']]+=1
        total=len(cases);complete=sum(bool(case['coverage_complete']) for case in cases.values())
        views=[{**module, 'record': {**module['record'],
            'cases':ui_records.active_cases(module['record']['cases']),
            'superseded_cases':[case for case in module['record']['cases'] if ui_records.is_superseded(case)]}}
            for module in records]
        return {'task':snap['tasks'][0],'modules':views,'counts':counts,'total':total,'coverage_complete':complete,
                'complete_pass_ratio':(counts['passed']+counts['retry_passed'])/total if total else None,'coverage_ratio':complete/total if total else None,
                'notices':snap['notices'],'unit':'已登记用例；未执行与不完整验证保留在分母',
                'coverage_basis':'动态探索尚未冻结范围时，不代表全部业务覆盖率'}

    def finalize_pending(self):
        if self.controller.draining():
            return
        with self.controller.connect() as db:
            nodes=read_node_fields(db, ('id', 'owner', 'finalization_pending', 'native_report_pending',
                                        'record_project_id', 'record_execution_id'))
        for n in nodes.values():
            # Only this protocol's newly settled tasks; do not resend old reports.
            pending = n.get('finalization_pending')
            if not pending and n.get('native_report_pending') and n.get('record_project_id'):
                # File registration can survive a lost database marker commit.
                # Idle records only require a read; an actual current intent
                # re-enters recovery without reclaiming resources or business.
                try:
                    from . import ui_finalization
                    project = self.store.get_project(n['owner'], n['record_project_id'])
                    publication = ui_finalization.status(project) or {}
                    pending = (publication.get('execution_id') == n.get('record_execution_id')
                               and publication.get('phase') in {'settling', 'published'})
                except (FileNotFoundError, ValueError, KeyError):
                    pending = False
            if pending:
                self.finalize_settlement(n['owner'],n['id'], raise_storage_errors=True,
                                         background=True, notify=True)

    def complete_published_settlement(self, owner, node, task, project, publication):
        """Acknowledge this exact already-published round, never a newer result.

        The normal callback remains the retry path for errors and changed
        evidence. This removes its work only after publication has completed.
        """
        if publication.get('phase') != 'published' or publication.get('pending') is not False:
            return False
        if (node.get('record_project_id') not in (None, project['id'])
                or node.get('record_execution_id') not in (None, publication.get('execution_id'))):
            return False
        with self.controller.transaction() as (_, state):
            current = self.controller.owned(state['nodes'], owner, node['id'])
            current_task = state['tasks'][current['task_id']]
            if (current['task_id'] != task['id'] or current_task['revision'] != task['revision']
                    or any(current.get(key) != node.get(key) for key in (
                        'revision', 'record_project_id', 'record_execution_id'))
                    or current['state'] not in {'completed', 'blocked', 'stopped', 'isolated', 'retained', 'paused'}
                    or current.get('session_removed') or current.get('report_deferred_deleted')
                    or any(lease['node_id'] == current['id'] and not lease.get('resource_hold')
                           for lease in state['leases'].values())):
                return False
            try:
                # Keep deletion and ownership checks current under the original
                # DB -> Store lock order; no authority is cached across calls.
                with self.store._lock:
                    self.store.get_project(owner, current_task['project_id'])
                    latest = self.store.get_project(owner, project['id'])
                    from . import ui_finalization
                    saved = ui_finalization.status(latest) or {}
                    if (latest.get('ui_execution_id') != publication.get('execution_id')
                            or latest.get('ui_execution_revision') != publication.get('revision')
                            or any(saved.get(key) != publication.get(key) for key in (
                                'phase', 'pending', 'execution_id', 'revision', 'request_id'))):
                        return False
                    from .deployment_activity import published_settlement
                    if not published_settlement(self.store.root, {**current,
                            'record_project_id': project['id'],
                            'record_execution_id': publication['execution_id']}, state):
                        return False
                    current.update(record_project_id=project['id'],
                                   record_execution_id=publication['execution_id'])
                    current.pop('native_report_pending', None)
                    current.pop('finalization_pending', None)
                    current.pop('report_error', None)
                    return True
            except (FileNotFoundError, ValueError):
                return False

    def reconcile_idle_settlement(self, owner, node_id):
        """Retire only an idle queue marker, preserving every report/receipt.

        Recheck under DB -> Store locks, so a new generation, active report
        request, deletion or unconfirmed exit cannot be cleared by a stale
        snapshot. This is also the upgrade path for old persistent markers.
        """
        from .deployment_activity import dormant_native_report
        with self.controller.connect() as db:
            nodes = read_node_fields(db, ('id', 'owner', 'report_error'), node_id=node_id)
        current = self.controller.owned(nodes, owner, node_id)
        if current.get('report_error'):
            # The default dormant proof rejects every report error. A negative
            # read grants no authority; successful clears still recheck below.
            return False
        with self.controller.transaction() as (_, state):
            current = self.controller.owned(state['nodes'], owner, node_id)
            with self.store._lock:
                if not dormant_native_report(self.store.root, current, state):
                    return False
                current.pop('finalization_pending', None)
                return True

    def finalize_settlement(self, owner, node_id, *, raise_storage_errors=False, background=False, notify=False):
        with self.report_worker(owner, node_id, background=background) as admitted:
            if not admitted:
                return
            self._finalize_settlement(owner, node_id, raise_storage_errors=raise_storage_errors)
            if notify:
                self._notify_final_report(owner, node_id)

    def _finalize_settlement(self, owner, node_id, *, raise_storage_errors=False):
        try:
            if self.reconcile_idle_settlement(owner, node_id):
                return
            snap=self.controller.snapshot(owner)
            n=next(n for n in snap['nodes'] if n['id']==node_id)
            if (n.get('child_ids') and not any(n.get(key) for key in (
                    'record_project_id','record_execution_id','attempts','case_history','outcome_history','direct_holder'))
                    and not any(lease['node_id']==node_id for lease in snap['leases'])):
                # A pure split container has only its original children's
                # reports; do not manufacture an empty additional report.
                pure_container=False
                try:
                    with self.controller.transaction() as (_,state):
                        current=self.controller.owned(state['nodes'],owner,node_id)
                        # The compact snapshot omits case_history. Recheck the
                        # original node before deciding to skip normal reporting.
                        pure_container=not any(current.get(key) for key in (
                            'record_project_id','record_execution_id','attempts','case_history','outcome_history','direct_holder'))
                        if pure_container:
                            with self.store._lock:
                                self.store.get_project(owner,state['tasks'][current['task_id']]['project_id'])
                                from .deployment_activity import published_settlement
                                if published_settlement(self.store.root,current,state):
                                    for key in ('native_report_pending','finalization_pending','report_error'):
                                        current.pop(key,None)
                except Exception:
                    return
                if pure_container:return
            if n.get('native_report_pending') or any(
                    child.get('native_report_pending') and child['task_id']==n['task_id']
                    for child in snap['nodes'] if n.get('child_ids')):
                # A successful publication can outlive its marker cleanup.
                # Reconcile the existing record before the pending guard, but
                # never create a project/report or replay unconfirmed results.
                if n.get('record_project_id'):
                    try:
                        t=next(t for t in snap['tasks'] if t['id']==n['task_id'])
                        p=self.store.get_project(owner,n['record_project_id'])
                        from . import ui_finalization
                        publication=ui_finalization.status(p) or {}
                    except Exception:
                        return
                    if publication.get('phase') == 'settling' and publication.get('pending') is True:
                        # A real registered request can survive an interrupted
                        # HTTP call. Resume its saved version, never business.
                        publication = ui_finalization.complete(self, owner, p['id']) or {}
                    if publication.get('phase') == 'published':
                        try:
                            self.complete_published_settlement(owner,n,t,p,publication)
                        except Exception:
                            # Published evidence remains successful even when
                            # its marker cleanup needs another callback.
                            return
                return
            if n['state'] not in {'completed','blocked','stopped','isolated','retained'}:return
            if n['state'] in {'isolated','retained'} and not any(
                    l['node_id']==node_id and l.get('resource_hold') for l in snap['leases']):return
            t=next(t for t in snap['tasks'] if t['id']==n['task_id'])
            if (not self.controller.sessions.available(owner,t['project_id']) or
                    (n.get('record_project_id') and not self.controller.sessions.available(owner,n['record_project_id']))):
                with self.controller.transaction() as (_,state):
                    state['nodes'][node_id].pop('finalization_pending',None)
                    state['nodes'][node_id]['report_deferred_deleted']=True
                return
            # Snapshot responses omit baseline bodies. Materialize only this
            # task's immutable report sources before the existing file work.
            with self.controller.connect() as db:
                t=read_entries(db, 'tasks', keys=[t['id']], include_baseline=True,
                               baseline_fields=('cases', 'sources'))[t['id']]
            p=self.report_project(owner,n,t);eid=p.get('ui_execution_id')
            from . import ui_finalization
            publication = ui_finalization.status(p) or {}
            if publication.get('phase') == 'published':
                try:
                    if self.complete_published_settlement(owner, n, t, p, publication):
                        return
                except Exception:
                    # Keep the actual publication and pending retry marker.
                    # An unavailable settlement write is not a report failure.
                    return
            if not eid:
                saved=ui_records.save_cases(self.store,owner,p['id'],[],coverage=[{'coverage_id':'execution-end','feature':'任务执行覆盖','gap':n.get('reason') or '任务结束，尚未记录可验证用例','case_ids':[]}])
                eid=saved['execution_id'];p=self.store.get_project(owner,p['id'])
            with self.controller.transaction() as (_,state):
                state['nodes'][node_id].update(record_project_id=p['id'],record_execution_id=eid)
            if ui_finalization.status(p):
                ui_finalization.complete(self, owner, p['id'])
            else:
                ui_records.publish(self.store,owner,p,eid,n['title'],
                    '任务已结束。'+(n.get('reason') or '按实际用例与检查点结果汇总；未验证部分保留，结束不等于通过。'))
            with self.controller.transaction() as (_,state):state['nodes'][node_id].pop('report_error',None);state['nodes'][node_id].pop('finalization_pending',None)
        except database.OperationalError as error:
            # A failed bookkeeping transaction says nothing about publication.
            # Preserve the original request/markers for the existing next tick;
            # Synchronous finish must retain the already-committed return ACK.
            # The background tick propagates the error to its existing handler.
            self.controller.last_error = type(error).__name__
            if raise_storage_errors:
                raise
        except Exception:
            from .deployment_activity import REPORT_RETRY_ERROR
            with self.controller.transaction() as (_,state):
                state['nodes'][node_id]['report_error']=REPORT_RETRY_ERROR
            if 'p' in locals() and p.get('ui_finish_request'):
                intent=self.store.get_project(owner,p['id']).get('ui_finish_request',{})
                intent['error']='最终报告生成未完成，账号回收不受影响；可按原 request_id 重试结束请求，不重跑业务。'
                self.store.update_project(owner,p['id'],{'ui_finish_request':intent})

    def notify_final_report(self, owner, node_id):
        with self.report_worker(owner, node_id) as admitted:
            if admitted:
                self._notify_final_report(owner, node_id)

    def _notify_final_report(self, owner, node_id):
        """After account return commits, notify only the latest published evidence."""
        try:
            with self.controller.connect() as db:
                state=read_metadata_without_history(db)
            node=self.controller.owned(state['nodes'],owner,node_id)
            if node.get('session_removed') or node.get('report_deferred_deleted'):return
            if node.get('native_report_pending') or any(
                    child.get('native_report_pending') and child['task_id']==node['task_id']
                    for child in state['nodes'].values() if node.get('child_ids')):return
            if node['state'] not in {'completed','blocked','stopped','isolated','retained'}:return
            if node['state'] in {'isolated','retained'} and not any(
                    l['node_id']==node_id and l.get('resource_hold') for l in state['leases'].values()):return
            pid=node.get('record_project_id')
            eid=node.get('record_execution_id')
            if not pid or not eid:return
            if self.store.get_project(owner,pid).get('ui_finish_request',{}).get('execution_id') == eid:
                # Explicit finish owns publication and notification together.
                from . import ui_finalization
                ui_finalization.complete(self,owner,pid)
                return
            record=ui_records.load(self.store,owner,pid,eid)
            rid=record.get('report_id')
            if not rid:return
            report=self.store._read(self.store.project_dir(owner,pid)/'analyses'/rid/'report.json')
            if report.get('ui_snapshot',{}).get('revision')!=record['revision']:return
            from .wecom import WeCom
            WeCom(self.store).auto_report(owner,pid,rid,'reports')
        except Exception:
            # Notification failures never undo settlement or hold the next account.
            pass

    @contextmanager
    def heartbeat_state(self, args):
        if any(args.get(key) for key in ('settlement_acks', 'exploration_faults', 'exploration_observations')):
            with self.controller.transaction() as (_, state):
                yield state
            return
        from .orchestration_storage import read_sections
        with self.controller.connect() as db:
            db.execute('BEGIN')
            state = read_sections(db, ('runners', 'leases', 'accounts', 'outbox', 'direct_settlements'))
            # No lease means no node result is needed for a heartbeat response.
            state['nodes'] = read_entries(db, 'nodes', keys={lease['node_id'] for lease in state['leases'].values()})
        yield state

    def host_call(self, auth, action, args):
        owner,hid=auth['owner'],auth['host_id']; c=self.controller
        if action in {'direct_poll','direct_result','operation_begin','operation_complete','reconcile','browser_ready'}:
            return self.direct.host(owner,hid,action,args)
        if action in {'console_poll','console_authorize','console_result'}:return self.console.host(auth,action,args)
        if action=='return_account':
            # Return the committed receipt promptly, including response-loss
            # recovery. The same transaction persists finalization_pending;
            # the existing scheduler callback handles publication/notification.
            # Re-reading an old receipt must not republish an old report.
            return c.return_account(owner,hid,args)
        if action=='retained_browser_closed':
            with c.transaction() as (db,s):
                l=s['leases'].get(args.get('lease_id'))
                if not l or l['runner_id']!=hid or not l.get('resource_hold') or not l.get('executor_stopped'):
                    raise Conflict('原保留租约不存在或尚未确认执行者退出')
                n=c.owned(s['nodes'],owner,l['node_id'])
                if not l.get('close_browser_requested') and not l.get('browser_stopped'):
                    raise Conflict('没有对应的关闭现场请求')
                l.update(browser_stopped=True,browser_units=0,close_browser_requested=False)
                for cid in args.get('auxiliary_stopped',[]):
                    if cid in l.get('auxiliary_channels',{}):
                        l['auxiliary_channels'][cid].update(state='exited',exited_at=c.clock())
                from .resource_scheduler import pending_operations, retention_conditions
                releasable = (n.get('session_removed') and not pending_operations(s,l['id'])
                              and not retention_conditions(n,l)
                              and all(x['state']=='exited' for x in l.get('auxiliary_channels',{}).values()))
                c.audit(db,owner,'retained_browser.closed',l['id'])
            if releasable:
                return c.resolve_resource_hold(owner,args['lease_id'],
                    '用户删除会话取消保留窗口；原主机已确认浏览器退出，且无未知操作或业务保留条件')
            return {'closed':True,'account_retained':True}
        if action=='register':
            c.register_host(owner,hid,enforcement_evidence=args['evidence'],browser_slots=args['browser_slots'],model_slots=args['model_slots'])
            return {'registered':True,'simple_dispatch':1}
        if action=='heartbeat':
            c.host_heartbeat(owner,hid,args['browser_slots'],args['model_slots'],args.get('progress'))
            with self.heartbeat_state(args) as s:
                acknowledged=[]
                from .exploration_profiles import promote, report_fault
                for lid,reason in (args.get('exploration_faults') or {}).items():
                    lease=s['leases'].get(lid)
                    if lease and lease['runner_id']==hid:
                        report_fault(s,lease,text(reason,'共享会话异常',600))
                for lid,observation in (args.get('exploration_observations') or {}).items():
                    lease=s['leases'].get(lid)
                    if lease and lease['runner_id']==hid:
                        node=c.owned(s['nodes'],owner,lease['node_id'])
                        promote(c,s,lease,node,observation)
                for lid in args.get('settlement_acks',[]):
                    receipt=s.get('direct_settlements',{}).get(lid)
                    event=next((e for e in s['outbox'].values() if e['lease_id']==lid and e['runner_id']==hid),None)
                    if receipt and receipt['owner']==owner and event:
                        receipt.setdefault('local_ack_at',c.clock())
                        s['nodes'][receipt['node_id']].setdefault('settlement_acks',{})[lid]=receipt['local_ack_at']
                        acknowledged.append(lid)
                    elif lid in s['leases'] and s['leases'][lid]['runner_id']==hid and s['leases'][lid].get('resource_hold'):
                        s['leases'][lid]['local_ack_at']=c.clock();acknowledged.append(lid)
                    elif event and lid not in s['leases']:
                        node=c.owned(s['nodes'],owner,event['node_id'])
                        node.setdefault('settlement_acks',{})[lid]=c.clock();acknowledged.append(lid)
                leases=[{**copy.deepcopy(l),'node_state':s['nodes'][l['node_id']]['state'],'node_reason':s['nodes'][l['node_id']]['reason']} for l in s['leases'].values() if l['runner_id']==hid]
                own_leases={e['lease_id'] for e in s['outbox'].values() if e['runner_id']==hid}
                settlements=[{'lease_id':lid,'released':True,'state':receipt['state'],'node_id':receipt['node_id']}
                             for lid,receipt in s.get('direct_settlements',{}).items()
                             if lid in own_leases and receipt['owner']==owner and not receipt.get('local_ack_at')]
                account_generations={a['id']:a.get('auth_generation','') for a in s['accounts'].values() if a['owner']==owner}
            return {'events':c.pending_events(owner,hid),'leases':leases,'logins':[],'draining':c.draining(),
                    'settlement_acks':acknowledged,
                    'settlement_updates':settlements,
                    'account_generations':account_generations}
        if action=='auxiliary_bound':
            with c.transaction() as (_,s):
                lease=s['leases'].get(args['lease_id'])
                if not lease or lease['runner_id']!=hid:raise PermissionError('辅助执行通道不属于此执行机')
                channel=lease.get('auxiliary_channels',{}).get(args['channel_id'])
                if not channel:raise Conflict('辅助执行通道不存在')
                # A close ACK can win the race against a host's stale bind error.
                # Never revoke the healthy parent for an already exited helper.
                if channel['state']=='exited':return {'acknowledged':True,'exited':True}
                if args.get('error'):
                    channel['binding_error_type']=str(args.get('error_type','Exception'))[:80]
                    lease['revoked']=True
                    s['nodes'][lease['node_id']].update(state='isolated',reason='辅助浏览器进程归属或退出无法核实，账号保留，不能重派')
                    return {'acknowledged':False,'isolated':True}
                if channel['state']!='exited':
                    if args.get('stopped'):lease['browser_units']=max(1,lease.get('browser_units',1)-1)
                    channel.update(state='exited' if args.get('stopped') else 'bound',host_ack_at=c.clock())
            return {'acknowledged':True}
        if action=='login_secret':
            with c.transaction() as (_,s):
                a=c.owned(s['accounts'],owner,args['account_id'])
                if not a.get('login_requested') or a.get('login_host')!=hid or a.get('login_attempt','')!=args.get('login_attempt','') or any(a['id'] in x['account_ids'] for x in s['leases'].values()):
                    raise PermissionError('凭据只交给当前账号的登录执行机')
                return {'credential':self.store._cipher.decrypt(a['credential'].encode()).decode() if a.get('credential') else ''}
        if action=='login_status':
            with c.transaction() as (_,s):
                a=c.owned(s['accounts'],owner,args['account_id'])
                if a.get('login_host')!=hid or not a.get('login_requested') or a.get('login_attempt','')!=args.get('login_attempt',''):
                    raise PermissionError('登录状态不属于此执行连接')
                a['login_message']=text(args.get('message'),'登录状态',500)
            return {'saved':True}
        if action=='login_result':
            with c.transaction() as (_,s):
                a=c.owned(s['accounts'],owner,args['account_id'])
                if a.get('login_host')!=hid or not a.get('login_requested') or a.get('login_attempt','')!=args.get('login_attempt',''):
                    raise PermissionError('登录核验不属于此执行连接')
            with c.transaction() as (db,s):
                a=c.owned(s['accounts'],owner,args['account_id'])
                if a.get('login_host')!=hid or not a.get('login_requested') or a.get('login_attempt','')!=args.get('login_attempt','') or a['identity']!=args['identity'] or (a['tenant'] and a['tenant']!=args['tenant']) or not set(a['roles'])<=set(args.get('roles',[])):
                    raise Conflict('登录身份、租户或执行机已改变')
                tenant=text(args.get('tenant'),'已核验租户',160)
                from .orchestration import strings
                roles=strings(args.get('roles',[]),'已核验角色')
                if not roles:raise Conflict('登录角色尚未识别，不能分配账号')
                a.update(tenant=a['tenant'] or tenant,roles=a['roles'] or roles)
                a.update(login_requested=False,session_host=hid,verified_identity=True,state='ready',login_message='登录身份已由系统核验')
                c.audit(db,owner,'account.verified',a['id'])
            return {'verified':True}
        l,n,t,s=self.lease(owner,hid,args['lease_id'],active=not auth.get('native_record') and action not in {'operation_result','settle','read','recover_begin','recover_finish','transition','operations','isolate','restore','request'},history_action=action,operation_id=args.get('operation_id'),
            include_baseline=action in {'read','asset_content','reference','requirements','save_requirements','dependency','record','cases','assets','publish'})
        if action=='asset_content':
            from .ui_asset_withdrawals import require_visible
            require_visible(self.store, owner, args.get('asset_id'))
            project=self.report_project(owner,n,t)
            eid=project.get('ui_execution_id')
            record=ui_records.load(self.store,owner,project['id'],eid) if eid else {'assets':[]}
            asset=next((a for a in record['assets'] if a['id']==args.get('asset_id')),None)
            if not asset:raise PermissionError('测试文件不属于当前任务记录')
            content=(ui_records.root_for(self.store,owner,project['id'],eid)/asset['id']).read_bytes()
            return {'filename':asset['filename'],'content_type':asset['content_type'],
                    'content_base64':base64.b64encode(content).decode()}
        if action=='save_checkpoint':
            with c.transaction() as (_,current):current['nodes'][n['id']]['checkpoint']=copy.deepcopy(args['checkpoint'])
            return {'saved':True}
        if action=='request_resources':
            return c.request_resources(owner,l['id'],args)
        if action=='account_credentials':
            # Both routes log in themselves using only the assigned identity.
            # Shared leases additionally carry the previously verified session policy.
            with c.transaction() as (db,current):
                lease=current['leases'].get(args['lease_id'])
                if not lease or lease['runner_id']!=hid or lease['revoked']:
                    raise PermissionError('只有当前有效执行者可以取用已分配账号密码')
                if lease['mode']=='shared' and not lease.get('native_browser'):
                    policy=current['policies'].get(lease.get('policy_id'),{})
                    if not policy.get('enabled') or not policy.get('session_compatible',policy.get('login_compatible',False)):
                        raise Conflict('共享会话策略已失效，等待独占资源；不重新索要账号')
                node=c.owned(current['nodes'],owner,lease['node_id'])
                if (node['state']!='running' or current['tasks'][node['task_id']]['intent']!='run'
                        or (not lease.get('native_browser') and lease['epoch']!=current['epoch']) or lease['revision']!=node['revision']
                        or (not lease.get('native_browser') and c.clock()-current['runners'][hid]['heartbeat']>60)):
                    raise Conflict('账号执行授权已失效')
                aid=args.get('account_id')
                if aid not in lease['account_ids']:raise PermissionError('账号未分配给此执行者')
                account=c.owned(current['accounts'],owner,aid)
                c.audit(db,owner,'account.credentials.used',aid)
                return {'account_id':aid,'username':account['identity'],
                        'password':self.store._cipher.decrypt(account['credential'].encode()).decode() if account.get('credential') else '',
                        'login_url':account.get('login',{}).get('url') or account['target']}
        if action=='exploration_session':
            # Host-only: never expose storage_state through an executing model tool.
            with c.transaction() as (_,current):
                lease=current['leases'].get(args['lease_id'])
                if (not lease or lease['runner_id']!=hid or lease.get('revoked')
                        or lease.get('mode')!='shared' or args.get('account_id') not in lease['account_ids']):
                    raise PermissionError('只有当前共享浏览器可以取得本批次登录态')
                node=c.owned(current['nodes'],owner,lease['node_id'])
                account=current['accounts'][args['account_id']]
                policy=current['policies'].get(lease.get('policy_id'),{})
                if (not policy.get('enabled') or not policy.get('session_compatible')
                        or policy.get('session_strategy')!='verified_storage_copy'
                        or policy.get('session_batch_id')!=lease.get('exploration_batch_id')
                        or policy.get('auth_generation')!=account.get('auth_generation','')
                        or lease['epoch']!=current['epoch'] or lease['revision']!=node['revision']
                        or current['tasks'][node['task_id']]['intent']!='run'
                        or node.get('control_intent','run')!='run'
                        or c.clock()-current['runners'][hid]['heartbeat']>60):
                    raise Conflict('本批次登录态已失效，沿原队列独占续接')
                return {'storage_state':json.loads(self.store._cipher.decrypt(policy['session_seed'].encode()))}
        if action=='read':
            # Retirement must work even after the user removes its report directory.
            missing = not c.sessions.available(owner,t['project_id']) or (
                n.get('record_project_id') and not c.sessions.available(owner,n['record_project_id']))
            if missing:
                if not l['revoked']:
                    raise Conflict('会话已删除，等待原执行通道停止；不能继续业务操作')
                return {'lease':l,'node':{k:v for k,v in n.items() if k!='case_history'},
                        'task':{k:v for k,v in t.items() if k!='baseline'},
                        'project':{'id':n.get('record_project_id') or t['project_id']},
                        'record':{},'document':'','accounts':[], 'settlement_only':True}
            from .account_projects import resource_project
            from .ui_dependencies import EXECUTION_PRACTICE
            project=self.report_project(owner,n,t)
            parent=self.store.get_project(owner,t['project_id'])
            doc=(self.store.project_dir(owner,project['id'])/project['document_file']).read_text()
            baseline=t.get('baseline') or {}
            target=origin(parent['ui_target_url']) if parent.get('ui_target_url') else (n['requirements'][0]['target'] if n['requirements'] else '')
            host=s['runners'].get(hid,{})
            context={'lease':l,'node':{k:v for k,v in n.items() if k!='case_history'},'task':{k:v for k,v in t.items() if k!='baseline'},
                'accounts':[{**{k:v for k,v in s['accounts'][aid].items() if k not in {'credential','identity_key'}},'has_password':bool(s['accounts'][aid].get('credential'))} for aid in l['account_ids']],
                'available_identities':[{'target':a['target'],'environment':a['environment'],'tenant':a['tenant'],'role':role}
                    for a in s['accounts'].values() if a['owner']==owner and resource_project(n) in a['projects'] and a['target']==target for role in a['roles']],
                'project':project,'document':doc,'baseline':baseline.get('cases',{}).get(n['key'],[]),
                'shared_policy':copy.deepcopy({k:v for k,v in s['policies'].get(l.get('policy_id'),{}).items() if k!='session_seed'}),
                'exploration_modules':[{'title':other['title'],'scope':other.get('scope','')}
                    for other in s['nodes'].values() if other['task_id']==n['task_id'] and not other.get('child_ids')],
                'exploration_guidance':('平台自动接入实时探索；用户仅配置账号，执行者不能自行登记规则批准共享。'
                    'session_strategy=verified_storage_copy 且 exploration_bootstrap=true 时，先在原浏览器正常登录并等待真实页面就绪；'
                    '然后从 navigation_links 选择 exploration_modules 对应的本轮实际入口，使用 browser 的 prepare_exploration 动作，parameters={entry_urls:[实际URL,...]} 一次交给平台。'
                    '这是平台自动核验准备，不是业务用例通过；不要提前编辑业务表单或提交业务写入。平台独占核验复制会话、重复页面和请求后自动开放共享，无需用户配置选择器或规则。'
                    '共享成员的登录态由平台在已核验批次内注入，各自浏览器独立；直接 navigate 到 shared_policy.entry_urls 中对应模块，不重新登录，不导出或复制 Cookie。'
                    'session_strategy=independent_login 时沿已分配账号正常登录，exploration_bootstrap=true 等待正常页面初始化回执。'
                    'continue_exploration=true 时保留被拦请求对应的未验证分支，继续其余已核验页面与本地表单探索；不把拦截当作业务失败或通过。'
                    '完成可共享的探索和设计后，使用原 request_resources 在真实边界转独占；未完成探索可用 exclusive_exploration=true，不能跳过持续探索和补充用例。'
                    if s['policies'].get(l.get('policy_id'),{}).get('automatic_profile') else ''),
                'execution_permission':copy.deepcopy(parent.get('ui_execution_permission',{'key':'full'})),
                'scene_retention':copy.deepcopy(parent.get('ui_scene_retention',{'key':'none'})),
                'dispatch':next((e for e in sorted(s['outbox'].values(),key=lambda e:e['created'],reverse=True) if e['lease_id']==l['id'] and e['kind']=='start'),None),
                'case_id_prefix':('M'+n['id'][:12]+'-') if project.get('managed_node_id') and t.get('session_workflow') else '',
                'record':ui_records.load(self.store,owner,project['id'],project['ui_execution_id']) if project.get('ui_execution_id') else None,
                'skill':(self.static/'skills/web-exploratory-testing/SKILL.md').read_text(),
                'guidance':EXECUTION_PRACTICE+'\n'+(self.static/'skills/web-exploratory-testing/references/coverage-design.md').read_text(),
                'execution_guidance':EXECUTION_PRACTICE,
                'execution_host':{'provider':'platform' if host.get('platform_managed') else 'paired',
                    'auxiliary_channels':bool(host.get('evidence',{}).get('auxiliary_channels')),
                    'browser_batch':bool(host.get('evidence',{}).get('browser_batch')),
                    'case_execution':bool(host.get('evidence',{}).get('case_execution')),
                    'default_known_flow':{'browser_action':'batch','parameters':{'plan_id':'stable-plan-id',
                        'cases':[{'case_id':'original-case-id','steps':[], 'checkpoints':{'original-checkpoint-id':['check-step-id']}}]},
                        'result_persistence':'each_case_before_next','on_no_progress':'end_turn'},
                    'browser_batch_guidance':'browser_batch=true 时可把已知顺序动作作为 batch 的 steps=[{id,action,parameters}] 一次提交；沿用已有业务授权，每步有独立操作回执，异常或断言失败停止后续步骤。未知结果不重放。check 使用 selector 与 expect（visible/enabled/text/value/count）逐项判定；保留每条用例、检查点和证据。交互中间步骤可用 response=summary，最后动作默认返回完整页面；有待判断的分支先观察再决定，不能提前编造后续动作。',
                    'guidance':('浏览器由平台服务器提供，使用本租约的 browser 工具及上传文件内容/asset_id；本机路径和本机辅助浏览器不属于服务器租约。无需安装、配对执行机或提供模型凭据。'
                        if host.get('platform_managed') else '沿原配对执行连接使用受控浏览器。')},
                'prior_operations':[o for o in select_records(s['operations'],node_id=n['id'],state=('unknown','pending')) if o['lease_id']!=l['id']],
                'record_tool_contracts':[x for x in json.loads((self.static/'agent-tools.json').read_text())['tools']
                    if x['name'] in {'save_ui_test_cases','upload_ui_test_assets','publish_ui_test_report','record_ui_dependency_check','save_requirement_design'}]}
            if l.get('native_browser'):
                from .native_state import browser_launch_policy
                launch_policy = browser_launch_policy(l.get('native_context_binding'))
                context.update(
                    execution_host={'provider':'codex_desktop', 'browser_tool':launch_policy.get('browser_tool', 'cua_repl'),
                                    'action_transport':'native', 'stop_method':'desktop_manual_s1',
                                    'browser_launch':launch_policy,
                                    'guidance':'直接使用当前 Codex 的原生浏览器工具连续执行已知步骤；平台不接收浏览器动作，不需要 Runner、心跳或动作轮询。'},
                    exploration_guidance=('当前账号允许共享探索，由 Skill 约束操作；未做逐请求拦截或会话兼容保证。需要写入或独占时只在资源边界调用 request_resources。'
                                          if l['mode']=='shared' else ''),
                    shared_policy={}, prior_operations=[], dispatch=None,
                    native_execution=(self.static/'skills/web-exploratory-testing/references/native-codex.md').read_text(),
                )
            return context
        if action=='ack':
            e=s['outbox'].get(args['event_id'])
            if not e or e['lease_id']!=l['id']:
                raise PermissionError('派发不属于此租约')
            if args.get('recovery_id'):
                with c.transaction() as (_,current):
                    node=current['nodes'][n['id']]
                    recovery=current['budgets'][node['budget_group']]['active'].get(args['recovery_id'])
                    if not recovery or recovery['node_id']!=node['id'] or node.get('thread_id') not in {None,args['thread_id']}:
                        raise Conflict('恢复轮次必须对应同一模块、原线程和有效恢复预算')
                    event_id=c.event(current,'start',node,hid,l['id'])
                c.acknowledge_start(owner,event_id,thread_id=args['thread_id'],turn_id=args['turn_id'])
            else:
                event_id=e['id']
                c.acknowledge_start(owner,event_id,thread_id=args['thread_id'],turn_id=args['turn_id'])
            return {'acknowledged':True,'event_id':event_id}
        if action=='request':
            allowed=self.request_allowed(owner,hid,args)
            request_id=text(args.get('request_id'),'request_id',160)
            with c.transaction() as (_,current):
                lease=current['leases'].get(l['id'])
                if not lease or (lease['revoked'] and not lease.get('human_mode')):raise Conflict('租约已撤销')
                if request_id in current['operations']:raise Conflict('请求标识已消费，禁止重发')
                current['operations'][request_id]={'id':request_id,'lease_id':l['id'],'node_id':n['id'],
                    'action':'network','effect':allowed['effect'],'state':'pending','created':time.time(),
                    'target':origin(args['url'])+urlsplit(args['url']).path,'method':args['method']}
                if allowed['effect'] not in {'verified_read','local'}:lease['may_write']=True
            return allowed
        if action=='restore':
            with c.transaction() as (_,current):
                lease=current['leases'][l['id']];node=current['nodes'][n['id']]
                if current['tasks'][t['id']]['intent']!='run' or node['state']!='isolated' or not node['reason'].startswith('执行连接失联'):
                    raise Conflict('此隔离状态不允许自动恢复')
                if bool(select_records(current['operations'],lease_id=l['id'],state=('pending','unknown'))):
                    raise Conflict('原操作结果未核实')
                if l['mode']=='shared' and not current['policies'].get(l['policy_id'],{}).get('enabled'):
                    raise Conflict('共享策略已失效')
                if not args.get('executor_fenced'):raise Conflict('必须先停止原执行者')
                lease.update(revoked=False,revision=node['revision'],epoch=current['epoch'])
                node.update(state='starting',reason='原执行者已停止，续接原线程与操作记录')
            return {'restored':True}
        if action=='operations':
            return {'operations':select_records(s['operations'],lease_id=l['id'])}
        if action=='release_ready':
            if not args.get('executor_fenced'):raise Conflict('必须先封住执行工具')
            with c.transaction() as (_,current):
                if not bool(select_records(current['operations'],lease_id=l['id'],state=('pending','unknown'))):
                    current['leases'][l['id']]['release_ready']=True
            return {'recorded':True}
        if action=='transition':return self.transition(owner,hid,args)
        if action=='isolate':
            with c.transaction() as (_,current):
                current['leases'][l['id']]['revoked']=True
                current['leases'][l['id']]['executor_fenced']=bool(args.get('executor_fenced'))
                current['nodes'][n['id']].update(state='isolated',reason=text(args.get('reason'),'reason'))
            return {'isolated':True}
        if action=='fixture':return c.fixture(owner,n['id'],args)
        if action=='shared_policy':
            raise Conflict('执行者不能自行批准共享规则；沿 context.exploration_guidance 使用受控 prepare_exploration，由平台实际核验并生成')

        if action=='authorize':
            parameters=args.get('parameters',{})
            aid=parameters.get('account_id')
            if aid not in l['account_ids']:raise PermissionError('操作账号不属于租约')
            if args['action']=='navigate':
                allowed={origin(s['accounts'][aid]['target']),*s['accounts'][aid].get('login',{}).get('allowed_origins',[])}
                if origin(parameters.get('url','')) not in allowed:raise PermissionError('导航目标越出授权域；不允许 file/javascript/data 等旁路')
            return c.authorize_operation(owner,l['id'],args['operation_id'],args['action'],args.get('parameters',{}),adapter='playwright',epoch=l['epoch'],revision=l['revision'])
        if action=='operation_result':
            op=s['operations'].get(args['operation_id'])
            if not op or op['lease_id']!=l['id']:
                raise PermissionError('操作不属于此租约')
            c.operation_result(owner,args['operation_id'],state=args['state'],result=args.get('result',{}));return {'recorded':True}
        if action=='recover_begin':
            if l['revoked'] or n.get('control_intent','run')!='run' or t['intent']!='run':
                raise Conflict('旧执行已撤权，不能再次启动恢复')
            return c.begin_recovery(owner,n['id'],args['recovery_id'],args['fault_id'])
        if action=='recover_finish':
            c.finish_recovery(owner,n['id'],args['recovery_id'],recovered=args['recovered']);return {'recorded':True}
        if action in {'reference','requirements','save_requirements','dependency','cases','assets','publish','record'}:
            return self.record_call(owner,l,n,t,s,action,args)
        if action=='settle':
            # The worker, not Codex, supplies fence/operation completion evidence.
            if args.get('wait_reason'):
                with c.transaction() as (_,current):current['leases'][l['id']]['executor_fenced']=True
                c.wait_human(owner,l['id'],checkpoint=args.get('checkpoint',{}),retained=args.get('retained',False),reason=args['wait_reason'])
                return {'waiting':True}
            c.release(owner,l['id'],checkpoint=args.get('checkpoint',{}),safety=args['safety'],next_phase=args.get('next_phase'),
                completed=args.get('completed',False),result=args.get('result','not_run'),coverage_complete=args.get('coverage_complete',False))
            self.notify_final_report(owner,n['id'])
            return {'released':True}
        raise ValueError('未知执行连接操作')

    def record_call(self, owner, l, n, t, s, action, args, *, write_state=None):
        """Shared persistence path; l=None means report-only after proven exit."""
        c=self.controller
        project=self.report_project(owner,n,t)
        eid=project.get('ui_execution_id','')
        if action=='reference':
            name=args.get('name','')
            paths={p.name:p for p in (self.static/'skills/web-exploratory-testing/references').glob('*.md')}
            if name not in paths:raise ValueError('参考资料不存在')
            return {'text':paths[name].read_text()}
        if action in {'requirements','save_requirements'}:
            from . import requirement_design
            if action=='requirements':return requirement_design.load(self.store,owner,project['id'])
            return requirement_design.save(self.store,owner,project['id'],args['revision'],args.get('requirements'),args.get('questions'))
        if action=='dependency':
            from . import ui_dependencies
            return ui_dependencies.record_check(self.store,owner,project['id'],eid,args['revision'],args['dependency_id'],args['status'],args['observed'],args['method'])
        record=ui_records.load(self.store,owner,project['id'],eid) if eid and action in {'record','cases'} else None
        if action=='record':
            from . import ui_dependencies
            return {**record, 'execution_plan': ui_dependencies.plan(record, recovery=ui_dependencies.cached_recovery(project, record))} if record else {'cases':[],'revision':0,'assets':[]}
        if action=='cases':
            if args.get('assets') is not None and (not isinstance(args['assets'], list) or len(args['assets']) > 50):
                raise ValueError('结果同批证据最多 50 项，可分批增量保存')
            if args.get('project_id') is not None and args['project_id']!=project['id']:
                raise Conflict('保存结果的 project_id 与原租约绑定不一致')
            if args.get('execution_id') is not None and args['execution_id']!=eid:
                raise Conflict('保存结果的 execution_id 与原轮不一致；保留观察，先核对原记录')
            if project.get('managed_node_id') and t.get('session_workflow'):
                prefix='M'+n['id'][:12]+'-'
                known={x['case_id'] for x in (record or {}).get('cases',[])}
                known.update(x['case_id'] for x in (t.get('baseline') or {}).get('cases',{}).get(n['key'],[]))
                if any(not x.get('case_id','').startswith(prefix) and x.get('case_id') not in known for x in args.get('cases',[])):
                    raise ValueError('新模块用例 ID 使用 context.case_id_prefix 前缀，避免总报告串并其他模块用例；既有 ID 保持不变')
            if (t['mode']=='design' or (l is not None and not l.get('native_browser') and not l.get('simple_dispatch') and n['phase']=='exploration')) and any(x.get('status','not_run') in {'passed','failed','partial'} for x in args.get('cases',[])):
                raise PermissionError('探索与设计阶段不接受正式执行结论；请先保存基线并交接执行阶段')
            if record:
                incoming={case.get('case_id'):case for case in args.get('cases',[]) if isinstance(case,dict)}
                changed=[copy.deepcopy(case) for case in record['cases'] if case['case_id'] in incoming and
                         any(case.get(k)!=v for k,v in incoming[case['case_id']].items())]
                if changed:
                    with (nullcontext((None, write_state)) if write_state is not None else c.transaction(node_ids=[n['id']])) as (_,current):
                        history=current['nodes'][n['id']].setdefault('case_history',{}).setdefault(str(record['revision']),
                            {'revision':record['revision'],'cases':[],'saved_at':time.time()})
                        history['cases']=list({case['case_id']:case for case in [*history['cases'],*changed]}.values())
            saved=ui_records.save_cases(self.store,owner,project['id'],args.get('cases',[]),eid,args.get('revision',0),
                coverage=args.get('coverage'),review_notes=args.get('review_notes'),scene_result=args.get('scene_outcome'),
                experiment=args.get('experiment'), staged_assets=args.get('assets'),
                refresh_report=l is not None, response=args.get('response','full'), include_saved_design=args.get('include_saved_design') is True)
            with (nullcontext((None, write_state)) if write_state is not None else c.transaction(node_ids=[n['id']])) as (_,current):
                saved_at=c.clock()
                current['nodes'][n['id']].update(record_project_id=project['id'],record_execution_id=saved['execution_id'],
                                               last_case_saved_at=saved_at)
                if l is not None:
                    current['nodes'][n['id']]['actor_seen']=saved_at
                elif current['nodes'][n['id']]['state']=='completed':
                    from .managed_workflow import correct_completed_result
                    counts=saved.get('execution_plan',{}).get('execution_summary',{}).get('status_counts',{})
                    if counts:
                        correct_completed_result(current['nodes'][n['id']],saved['execution_id'],saved['revision'],counts,saved_at)
                if l is not None and l['id'] in current['leases']:
                    current['leases'][l['id']]['progress_at']=saved_at
                    if args.get('scene_outcome',{}).get('status')=='cleaned':
                        current['leases'][l['id']]['scene_recorded_at']=time.time()
                if l is not None and l.get('native_browser') and any(case.get('status') in {'passed','failed','partial'} for case in args.get('cases',[])):
                    current['nodes'][n['id']].setdefault('business_started_at',c.clock())
                    current['nodes'][n['id']]['native_last_case_saved_at']=c.clock()
            from .mcp_progress import record_case_progress
            record_case_progress(self.store,owner,project['id'],saved, reporting=l is None)
            saved['scheduling_hint']='还有任务排队，完成当前业务步骤后可主动交还账号，让排队任务接上。' if l is not None and any(x['state']=='queued' and x['id']!=n['id'] for x in s['nodes'].values()) else ''
            return saved
        if not eid:
            raise Conflict('先保存具体用例，再关联证据或发布')
        if action=='assets':
            return ui_records.add_assets(self.store,owner,project['id'],eid,args['assets'])
        return ui_records.publish(self.store,owner,project,eid,args.get('title',n['title']),args.get('summary',''))

    def transition(self, owner, hid, args):
        """Atomic stage handoff: either keep the same lease/context or release safely."""
        c=self.controller;lid=args['lease_id']
        l,n,t,s=self.lease(owner,hid,lid,active=False,include_baseline=True)
        project=self.report_project(owner,n,t)
        record=ui_records.load(self.store,owner,project['id'],project['ui_execution_id']) if project.get('ui_execution_id') else {}
        requirements=args.get('requirements')
        children=args.get('children')
        if n.get('resource_planning') and not args.get('checkpoint_only') and requirements is None and t['intent']=='run' and not l['revoked']:
            raise Conflict('先根据测试目标形成身份需求计划，不能跳过规划直接执行')
        if requirements is not None and (children or args.get('completed')):
            raise ValueError('资源交接不能同时拆分或完成模块')
        if children:
            if not isinstance(children,list) or not 1<=len(children)<=100:raise ValueError('拆分模块格式错误')
            for child in children:
                text(child.get('title'),'模块名称',200);text(child.get('scope'),'模块范围',5000)
            if n.get('parent_id') or n['phase']!='exploration' or record.get('cases') or t.get('_baseline_present', t.get('baseline')):
                raise Conflict('已有用例或回归基线须保留原模块；不能通过拆分丢失原用例与关联')
            if args.get('completed') or args.get('next_phase'):raise ValueError('拆分交接不能同时完成或进入执行')
        if args.get('checkpoint_only'):
            with c.transaction() as (_,current):
                if requirements is not None:c.validate_requirements(current,current['nodes'][n['id']],requirements)
                current['nodes'][n['id']]['checkpoint']=copy.deepcopy(args.get('checkpoint',{}))
            return {'saved':True}
        args={**args,'checkpoint':{**args.get('checkpoint',{}),'account_ids':l['account_ids'],'context_id':l['context_id']}}
        safety=args.get('safety',{})
        if not safety.get('executor_fenced') or not safety.get('inflight_reconciled'):
            raise Conflict('执行连接必须先停轮次并核实在途操作')
        completed=args.get('completed',False)
        cases=ui_records.active_cases(record.get('cases',[]))
        complete=bool(cases) and all(x['status'] in {'passed','failed'} and
            all(p.get('status') in {'passed','failed'} for p in x.get('checkpoints',[])) for x in cases)
        result='not_run' if t['mode']=='design' or not completed else (
            'failed' if any(x['status']=='failed' for x in cases) else 'passed' if complete else
            'partial' if any(x['status'] in {'passed','partial'} for x in cases) else 'blocked')
        if completed and not cases and t['intent']=='run':
            raise Conflict('未保存实际用例，不能完成模块')
        scene=record.get('scene_outcome',{})
        with c.transaction() as (db,current):
            lease=current['leases'].get(lid)
            if not lease:raise Conflict('租约已改变')
            node=current['nodes'][n['id']];task=current['tasks'][t['id']]
            lease['executor_fenced']=True
            if bool(select_records(current['operations'],lease_id=lid,state=('pending','unknown'))):
                raise Conflict('仍有未知或在途操作')
            older=any(x['state']=='queued' and x['id']!=n['id'] and (x['protected'] or queue_key(x)<queue_key(node))
                      and any(c.needs_account(x,current['accounts'][aid]) for aid in l['account_ids'])
                      for x in current['nodes'].values())
            other=any(x['id']!=lid and set(x['account_ids']) & set(l['account_ids']) for x in current['leases'].values())
            if args.get('exclusive_exploration'):node['exclusive_exploration']=True
            next_phase=args.get('next_phase')
            if next_phase not in {None,'exploration','execution','report'}:raise ValueError('阶段错误')
            if next_phase=='execution' and t['mode']=='design':raise PermissionError('仅设计任务不能执行')
            if args.get('resume_scene') and lease.get('resolution_requested') and lease.get('human_scene_evidence') and node['state'] in {'waiting_human','retained'} and task['intent']=='run' and not completed and not older and not other:
                lease.update(revoked=False,human_mode=False,resolution_requested=False,mode='exclusive',policy_id='',release_ready=False,executor_fenced=False)
                node.update(state='starting',revision=node['revision']+1,reason='原现场已核实，续接原线程')
                lease['revision']=node['revision']
                event=c.event(current,'start',node,hid,lid)
                return {'continued':True,'event_id':event}
            # The last explorer can promote without a release/reacquire race.
            if not completed and task['intent']=='run' and not lease['revoked'] and not older and not other and next_phase and not children and requirements is None:
                node.update(phase=next_phase,revision=node['revision']+1,state='starting',checkpoint=copy.deepcopy(args.get('checkpoint',{})))
                lease.update(mode='exclusive',policy_id='',revision=node['revision'],release_ready=False,executor_fenced=False)
                for aid in l['account_ids']:current['accounts'][aid]['pool']='execution'
                event=c.event(current,'start',node,hid,lid)
                c.audit(db,owner,'lease.phase_handoff',lid)
                return {'continued':True,'event_id':event}
            subsequent_write=any(o['lease_id']==lid and o.get('effect') not in {None,'verified_read','local'} and o['created']>lease.get('scene_recorded_at',0) and o['state']!='not_sent' for o in current['operations'].values())
            if result=='passed' and any(case['status']=='failed' for saved in node.get('case_history',{}).values() for case in saved.get('cases',[])) and not any(h['result']=='failed' for h in node['outcome_history']):
                node['outcome_history'].append({'result':'failed','coverage_complete':False,'at':time.time(),'source':'preserved_case_history'})
            scene_safe=bool(lease.get('human_scene_evidence')) or (scene.get('status')=='cleaned' and not subsequent_write) or not lease.get('may_write',False)
        if not scene_safe:
            c.wait_human(owner,lid,checkpoint=args.get('checkpoint',{}),retained=True,reason='现场有变更，尚未完成清理或明确交接；保留账号等待核实')
            return {'waiting':True}
        c.release(owner,lid,checkpoint=args.get('checkpoint',{}),safety={**safety,'scene_verified':True},
                  next_phase=args.get('next_phase'),completed=completed,result=result,coverage_complete=complete,blocked_reason=args.get('halt_reason'),children=children,requirements=requirements)
        self.notify_final_report(owner,n['id'])
        return {'released':True}

    def resolve(self, owner, lid, data):
        """Human decision records evidence; only the host can attest process fencing."""
        self.console.assert_idle(owner,lid)
        evidence=text(data.get('evidence'),'核实依据',6000)
        with self.controller.transaction() as (db,s):
            l=s['leases'].get(lid)
            if not l:raise Conflict('租约不存在')
            n=self.controller.owned(s['nodes'],owner,l['node_id'])
            if not l['revoked']:raise Conflict('请先暂停任务，避免核实期间产生新操作')
            for oid, outcome in data.get('operations',{}).items():
                op=s['operations'].get(oid)
                if not op or op['lease_id']!=lid or outcome not in {'confirmed','not_sent'}:
                    raise ValueError('仅核实此租约的明确操作结果')
                if op['state'] in {'pending','unknown'}:op.update(state=outcome,result={'human_evidence':evidence},finished=time.time())
            if data.get('scene_verified'):
                l['human_scene_evidence']=evidence
            held=bool(l.get('resource_hold'))
            if not held:
                l['human_mode']=False
                l['resolution_requested']=True
                l['resolution_revision']=l.get('resolution_revision',0)+1
            self.controller.audit(db,owner,'lease.human_reconciled',lid,evidence)
        if held:
            result=self.controller.resolve_resource_hold(owner,lid,evidence,release=bool(data.get('scene_verified')))
            if result.get('released'):self.controller.schedule()
            return result
        return {'recorded':True,'message':'已登记核实依据，仍由原执行机核实撤权后交还资源'}

    def human_mode(self,owner,lid):
        with self.controller.transaction() as (db,s):
            l=s['leases'].get(lid)
            if not l:raise Conflict('租约不存在')
            n=self.controller.owned(s['nodes'],owner,l['node_id'])
            if n['state'] not in {'waiting_human','retained','isolated'} or s['tasks'][n['task_id']]['intent']!='run' or not l.get('executor_fenced'):
                raise Conflict('须由原执行机确认已停止模型，且任务处于人工等待、保留或隔离状态')
            if any(x['id']!=lid and set(x['account_ids'])&set(l['account_ids']) for x in s['leases'].values()):
                raise Conflict('当前仍共享账号，须等其他探索者交还后才可人工操作')
            l.update(human_mode=True,mode='exclusive',policy_id='')
            self.controller.audit(db,owner,'lease.human_mode',lid)
        return {'enabled':True,'message':'仅允许原浏览器现场人工操作，Codex 工具仍保持撤权；完成后填写核实依据'}
