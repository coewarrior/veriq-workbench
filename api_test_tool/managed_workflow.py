"""Select desktop native execution or an explicitly retained legacy execution route."""
from __future__ import annotations
import copy
from .orchestration import Conflict
from .module_dispatch import apply_initial_plan, dispatch_view


def correct_completed_result(node, eid, revision, counts, now):
    """Keep report corrections consistent without changing execution lifecycle."""
    result=('failed' if counts.get('failed') else 'passed' if counts.get('passed') and
            sum(counts.values())==counts['passed'] else 'partial')
    if result=='passed' and any(h.get('result')=='failed' for h in node.get('outcome_history',[])):
        result='retry_passed'
    if node.get('result')!=result:
        node.setdefault('result_corrections',[]).append({'execution_id':eid,'revision':revision,
            'previous':node.get('result'),'result':result,'saved_at':now,'source':'saved_case_revision'})
    # Status counts cannot certify the module's unexplored scope.
    node.update(result=result,coverage_complete=False,record_revision=revision,last_case_saved_at=now)


class ManagedWorkflow:
    def __init__(self, service):
        self.service=service;self.controller=service.controller;self.store=service.store

    def status(self,owner,pid):
        project=self.store.get_project(owner,pid)
        snap=self.controller.snapshot(owner)
        progress=self.progress(owner,project,snapshot=snap)
        tids={t['id'] for t in snap['tasks'] if t['project_id']==pid}
        snap['tasks']=[t for t in snap['tasks'] if t['id'] in tids]
        snap['nodes']=[n for n in snap['nodes'] if n['task_id'] in tids]
        nids={n['id'] for n in snap['nodes']}
        snap['leases']=[l for l in snap['leases'] if l['node_id'] in nids]
        snap['operations']=[o for o in snap['operations'] if o['node_id'] in nids]
        snap['notices']=[n for n in snap['notices'] if n['task_id'] in tids]
        # The project page must not show another task's desktop stop receipts.
        # Reuse this snapshot: observing S1 never contacts the desktop or runner.
        from .native_state import desktop_stop_view
        state={key:{item['id']:item for item in snap[key]} for key in ('tasks','nodes','leases')}
        snap['desktop_stop']=desktop_stop_view(state,owner=owner)
        for task in snap['tasks']:
            if task.get('execution_route')=='native_browser':
                task['desktop_stop']=desktop_stop_view(state,owner=owner,task_id=task['id'])
        account_project=self.controller.account_projects.binding(owner,pid)
        resource_pid=account_project['id'] if account_project else pid
        snap['account_project']=account_project
        snap['accounts']=[a for a in snap['accounts'] if resource_pid in a['projects']]
        snap['policies']=[p for p in snap['policies'] if resource_pid in p.get('projects',[p['project_id']])]
        snap['configuration']=account_project.get('configuration',{}) if account_project else project.get('managed_configuration',{})
        if account_project and project.get('managed_configuration_account_project_id')==resource_pid:
            snap['configuration']=project.get('managed_configuration',{})
        archived={t['id'] for t in snap['tasks'] if t.get('account_project_deleted')}
        active=any(n['state']!='completed' and not n.get('child_ids') for n in snap['nodes'] if n['task_id'] not in archived)
        snap['execution_mode']=next((t.get('execution_route','managed') for t in reversed(snap['tasks']) if any(n['task_id']==t['id'] and n['state']!='completed' for n in snap['nodes'])),project.get('execution_route','native_browser'))
        snap['progress']=progress
        return snap

    def assert_idle(self,owner,pid):
        snap=self.status(owner,pid)
        archived={t['id'] for t in snap['tasks'] if t.get('account_project_deleted')}
        if any(n['state']!='completed' for n in snap['nodes'] if not n.get('child_ids') and n['task_id'] not in archived):
            raise Conflict('本会话已有测试任务，请使用当前任务的暂停、停止或继续；不能替换执行资料和基线')

    def summary(self,owner,pid):
        snap=self.status(owner,pid)
        return {key:snap[key] for key in ('tasks','nodes','notices','account_project','execution_mode','progress')}

    def progress(self,owner,project,*,snapshot=None,projects=None,record_cache=None):
        from .mcp_progress import project_progress
        if snapshot is None:snapshot=self.controller.snapshot(owner)
        if projects is None:projects=self.store.list_projects(owner)
        tasks=[t for t in snapshot.get('tasks',[]) if t['project_id']==project['id'] and not t.get('account_project_deleted')]
        current=max(tasks,key=lambda t:t.get('created',0),default=None)
        return project_progress(self.store,owner,project,snapshot,projects,record_cache,
                                task_scope=current['id'] if current else None)

    def record_activity(self,owner,pid,saved):
        """Attach a confirmed case save to its current node, without a heartbeat."""
        project=self.store.get_project(owner,pid)
        eid=saved.get('execution_id')
        if not eid or eid!=project.get('ui_execution_id') or saved.get('revision')!=project.get('ui_execution_revision'):
            return
        counts=saved.get('execution_plan',{}).get('execution_summary',{}).get('status_counts',{})
        with self.controller.transaction() as (_,state):
            for node in state['nodes'].values():
                if node['owner']!=owner or node.get('child_ids') or node.get('record_successor_node_id') or node.get('state') not in {'running','starting','queued','completed'}:
                    continue
                task=state['tasks'][node['task_id']]
                matches=(node.get('record_project_id')==pid or project.get('managed_node_id')==node['id'] or
                         (task['project_id']==pid and len(task.get('node_ids',[]))==1))
                if not matches or (node.get('record_execution_id') and node['record_execution_id']!=eid):
                    continue
                if node.get('record_revision', 0) >= saved['revision']:
                    continue
                now=self.controller.clock()
                if node['state']=='completed':
                    # A report correction changes the current result, not the
                    # historical release/exit receipt or scheduler lifecycle.
                    if node.get('record_execution_id')!=eid or any(l['node_id']==node['id'] for l in state['leases'].values()) or not counts:
                        continue
                    correct_completed_result(node,eid,saved['revision'],counts,now)
                    continue
                node.update(record_project_id=pid,record_execution_id=eid,record_revision=saved['revision'],last_case_saved_at=now)
                if any(counts.get(key,0) for key in ('passed','failed','partial')):
                    node.setdefault('business_started_at',now)
                for lease in state['leases'].values():
                    if lease['node_id']==node['id']:
                        lease['progress_at']=now
                # No executor last_seen/exit acknowledgement is inferred from
                # a report collaborator's successful save.

    def inherit_round(self,owner,project):
        parent_id=project.get('execution_round',{}).get('parent_project_id')
        if not parent_id:return project
        parent=self.store.get_project(owner,parent_id)
        account_project=self.controller.account_projects.binding(owner,project['id'])
        if account_project:
            if not project.get('managed_configuration') and parent.get('managed_configuration_account_project_id')==account_project['id']:
                return self.store.update_project(owner,project['id'],{k:copy.deepcopy(parent[k]) for k in ('managed_configuration','managed_configuration_account_project_id')})
            return project
        # A regression is an authorized child of the same project, not a new
        # identity. Share the pool and the exact maintained policy, no duplication.
        with self.controller.transaction() as (_,s):
            for a in s['accounts'].values():
                if a['owner']==owner and parent_id in a['projects'] and project['id'] not in a['projects']:a['projects'].append(project['id'])
            for policy in s['policies'].values():
                if policy['owner']==owner and policy['project_id']==parent_id:
                    grants=policy.setdefault('projects',[parent_id])
                    if project['id'] not in grants:grants.append(project['id'])
        if not project.get('managed_configuration') and parent.get('managed_configuration'):
            project=self.store.update_project(owner,project['id'],{'managed_configuration':copy.deepcopy(parent['managed_configuration'])})
        return project

    def configure(self,owner,pid,data):
        self.store.get_project(owner,pid)
        account_project=self.controller.account_projects.binding(owner,pid)
        resource_pid=account_project['id'] if account_project else pid
        requirements=data.get('requirements',[])
        if not isinstance(requirements,list) or not requirements:raise ValueError('请选择测试环境、租户与所需角色')
        snap=self.controller.snapshot(owner)
        for r in requirements:
            if not isinstance(r,dict) or not all(isinstance(r.get(k),str) and r[k] for k in ('target','environment','tenant','role')):raise ValueError('身份需求不完整')
            if not any(resource_pid in a['projects'] and all(a[k]==r[k] for k in ('target','environment','tenant')) and r['role'] in a['roles'] for a in snap['accounts']):raise ValueError('所选身份没有授权给当前会话的账号')
        policy=data.get('shared_policy','')
        if policy and not any(p['id']==policy and resource_pid in p.get('projects',[p['project_id']]) and p['enabled'] for p in snap['policies']):raise ValueError('共享规则未获核验或已失效')
        value={'requirements':copy.deepcopy(requirements),'shared_policy':policy}
        self.store.update_project(owner,pid,{'managed_configuration':value,'managed_configuration_account_project_id':resource_pid})
        return value

    def start(self,owner,pid,data):
        if data.get('modules') is not None and (not isinstance(data['modules'],list) or not data['modules']):
            raise ValueError('modules 必须是非空模块数组')
        p=self.inherit_round(owner,self.store.get_project(owner,pid))
        if p.get('test_kind')!='ui':raise ValueError('此入口用于页面测试会话')
        route=data.get('execution_route') or 'native_browser'
        if route not in {'native_browser','local_browser','managed'}:
            raise ValueError('execution_route 仅支持 native_browser/local_browser/managed')
        snap=self.status(owner,pid)
        for t in reversed(snap['tasks']):
            if t.get('account_project_deleted'):continue
            nodes=[n for n in snap['nodes'] if n['task_id']==t['id'] and not n.get('child_ids')]
            if nodes and any(n['state']!='completed' for n in nodes):
                if data.get('modules') is not None:
                    apply_initial_plan(self,owner,t['id'],data['modules'])
                return {'scheduled':t.get('execution_route','managed')=='managed','mode':t.get('execution_route','managed'),'task_id':t['id'],'existing':True,'intent':t['intent'],'next_action':'direct_test_session' if t.get('execution_route') in {'native_browser','local_browser'} else 'get_managed_test','message':'沿用当前测试任务；已暂停或停止时请使用继续，不重复创建。',**dispatch_view(self.controller,owner,t['id'])}
        if not snap['account_project']:
            return {'scheduled':False,'required_inputs':['account_project_id'],
                    'message':'请选择测试所属项目；暂无项目时请先添加项目并填写产品登录地址。'}
        if not snap['account_project'].get('login_url'):
            return {'scheduled':False,'required_inputs':['project_login_url'],
                    'message':'请在项目管理中填写唯一的产品登录地址。'}
        goal=p.get('task',{}).get('goal','').strip()
        if not goal:raise ValueError('请先保存测试目标')
        # Original direct sessions are never silently taken over while executing.
        progress=p.get('mcp_progress') or {}
        if (not snap['tasks'] or p.get('execution_route') in {'native_browser','local_browser'}) and progress.get('phase') in {'executing','reporting'}:
            raise Conflict('原测试仍在执行；请先完成原轮或按既有流程停止，不能创建第二个执行者')
        # The planner derives phase identities from the saved goal and granted
        # project resources. Legacy UI defaults are context, not startup gates.
        config={'requirements':[], 'shared_policy':''}
        bind_existing=bool(data.get('modules') and (p.get('ui_execution_id') or
            any(n.get('record_execution_id') for n in snap['nodes']) or
            any(m.get('source_node_id') for m in data['modules'] if isinstance(m,dict))))
        modules=(data.get('modules') if not bind_existing else None) or [{'key':'session','title':p['title'][:200],
            'scope':'按本会话完整目标与已保存资料探索、设计和执行；指定补测或回归沿用原用例范围。', 'resource_planning':True, **config}]
        result=self.controller.create_task(owner,{'project_id':pid,'account_project_id':(snap['account_project'] or {}).get('id',''),'request_id':data.get('request_id'),
            'goal':goal,'modules':modules,'explicit_module_plan':data.get('modules') is not None and not bind_existing,'mode':data.get('mode','execute'),'session_workflow':True,'session_start':True,'execution_route':route},initial_plan=data['modules'] if bind_existing else None)
        if data.get('modules') is not None and result.get('status')=='existing' and not bind_existing:
            apply_initial_plan(self,owner,result['task_id'],data['modules'])
        self.store.update_project(owner,pid,{'execution_route':route})
        return {'scheduled':route=='managed','mode':route,'next_action':'direct_test_session' if route in {'native_browser','local_browser'} else 'get_managed_test',**result,**dispatch_view(self.controller,owner,result['task_id'])}
