"""Business projects own account grants; sessions retain their own reports and scope."""
from __future__ import annotations
import copy
from urllib.parse import urlsplit
from .orchestration import Conflict, digest, text, uid
from .session_lifecycle import active_nodes, legacy_progress_active


def resource_project(node):
    return node.get('account_project_id') or node['project_id']


class AccountProjects:
    def __init__(self, controller):
        self.controller = controller
        self.store = controller.store

    @staticmethod
    def validate_login(value):
        value = text(value, '项目登录地址', 2000)
        u = urlsplit(value)
        if u.scheme not in {'http', 'https'} or not u.hostname or u.username or u.password:
            raise ValueError('项目登录地址必须是无内嵌凭据的 HTTP(S) 地址')
        return value

    def view(self, s, project):
        result = copy.deepcopy(project)
        if not result.get('login_url'):
            urls = {a.get('login', {}).get('url') or a['target'] for a in s['accounts'].values()
                    if a['owner'] == project['owner'] and project['id'] in a['projects']}
            if len(urls) == 1:
                result['login_url'] = next(iter(urls))
                project['login_url'] = result['login_url']
            else:
                result['login_url'] = ''
                result['login_conflict'] = len(urls) > 1
        return result

    def login(self, s, owner, project_id):
        project = self.controller.owned(s.get('account_projects', {}), owner, project_id)
        value = self.view(s, project).get('login_url')
        if not value:
            raise Conflict('请先在项目上填写唯一的产品登录地址；账号不单独配置地址')
        return value

    def get(self, owner, project_id):
        with self.controller.transaction() as (_, s):
            return self.view(s, self.controller.owned(s.get('account_projects', {}), owner, project_id))

    def list(self, owner):
        with self.controller.transaction() as (_, s):
            return [self.view(s, p) for p in s.get('account_projects', {}).values() if p['owner'] == owner]

    def create(self, owner, data):
        name = text(data.get('name'), '项目名称', 200)
        login_url = self.validate_login(data.get('login_url'))
        def create(db, s):
            projects = s.setdefault('account_projects', {})
            project = dict(id='ap_' + uid(), owner=owner, name=name, login_url=login_url, configuration={}, created=self.controller.clock())
            projects[project['id']] = project
            self.controller.audit(db, owner, 'account_project.created', project['id'])
            return copy.deepcopy(project)
        return self.controller.request(owner, data.get('request_id') or uid(),
                                       {'action': 'create_account_project', 'name': name, 'login_url': login_url}, create)

    def lineage(self, owner, pid):
        ids = []
        while pid and pid not in ids:
            try:
                p = self.store.get_project(owner, pid)
            except FileNotFoundError:
                if not ids:raise
                break  # Historical source removed; never guess another project.
            ids.append(pid)
            pid = (p.get('execution_round', {}).get('parent_project_id') or
                   p.get('managed_parent_project_id') or p.get('regression_source', {}).get('project_id'))
        return ids

    def rename(self, owner, project_id, data):
        name = text(data.get('name'), '项目名称', 200)
        sessions = self.store.list_projects(owner)
        with self.controller.transaction() as (db, s):
            self.controller.sessions.reconcile(db, s)
            project = self.controller.owned(s.get('account_projects', {}), owner, project_id)
            old_url = self.view(s, project).get('login_url', '')
            login_url = self.validate_login(data.get('login_url', old_url))
            if login_url != old_url:
                self._assert_removable(s, owner, project_id, sessions)
                accounts = [a for a in s['accounts'].values() if a['owner'] == owner and project_id in a['projects']]
                target = urlsplit(login_url)
                origin = f'{target.scheme}://{target.netloc.lower()}'
                for account in accounts:
                    if any(account['id'] in l['account_ids'] for l in s['leases'].values()):
                        raise Conflict('项目账号仍在使用，完成现场核实后再修改登录地址')
                    for other_id in account['projects']:
                        if other_id != project_id and other_id in s.get('account_projects', {}):
                            if self.login(s, owner, other_id) != login_url:
                                raise Conflict('账号还绑定了其他登录地址的项目，请先解除当前项目中的共用绑定再修改产品地址')
                    if any(a['id'] != account['id'] and a['target'].lower() == origin.lower() and a['identity'] == account['identity'] for a in s['accounts'].values()):
                        raise Conflict('新地址已有相同账号登记，请先从本项目移除旧账号，再绑定已有账号')
                for account in accounts:
                    if account['target'] != origin:
                        account.update(target=origin, environment=origin, tenant='', roles=[], policy_id='', pool='execution', login={})
                    account['identity_key'] = digest([origin.lower(), account['environment'], account['identity']])
                    account.setdefault('login', {})['url'] = login_url
                    self.controller.account_management._invalidate(s, account)
                    account['revision'] = account.get('revision', 1) + 1
                project['configuration'] = {}
            project.update(name=name, login_url=login_url)
            self.controller.audit(db, owner, 'account_project.updated', project_id)
            return self.view(s, project)

    def _assert_removable(self, s, owner, project_id, sessions):
        bound={pid for pid,ap in s.get('session_account_projects',{}).items() if ap==project_id}
        while True:
            children={p['id'] for p in sessions if (p.get('execution_round',{}).get('parent_project_id') or p.get('regression_source',{}).get('project_id')) in bound}
            if children<=bound:break
            bound.update(children)
        if any(p['id'] in bound and legacy_progress_active(s, p) for p in sessions):
            raise Conflict('所属项目仍有正在执行的浏览器会话，请完成本轮后再修改地址或移除项目资源')
        nodes = [n for n in s['nodes'].values() if n['owner'] == owner and resource_project(n) == project_id]
        busy = active_nodes(s, nodes)
        if busy:
            detail = '；'.join(n['title'] + '：' + (n.get('reason') or n['state']) for n in busy[:3])
            raise Conflict('项目仍有任务或资源未回收：' + detail)
        nids = {n['id'] for n in nodes}
        if any(l['node_id'] in nids for l in s['leases'].values()):
            raise Conflict('账号仍被任务占用或保留浏览器现场，请完成现场核实后再移除')
        if any(o['node_id'] in nids and o['state'] in {'unknown', 'pending'} and not o.get('historical') for o in s['operations'].values()):
            raise Conflict('项目仍有待核实操作，请先在测试会话中完成核实')

    def remove_account(self, owner, project_id, account_id):
        sessions = self.store.list_projects(owner)
        with self.controller.transaction() as (db, s):
            self.controller.sessions.reconcile(db, s)
            self.view(s, self.controller.owned(s.get('account_projects', {}), owner, project_id))
            account = self.controller.owned(s['accounts'], owner, account_id)
            if project_id in account['projects']:
                self._assert_removable(s, owner, project_id, sessions)
                account['projects'].remove(project_id)
                account['revision'] = account.get('revision', 1) + 1
                s['account_projects'][project_id]['configuration'] = {}
                self.controller.audit(db, owner, 'account.ungranted', account_id, project_id)
            return {'removed': True}

    def delete(self, owner, project_id):
        sessions = self.store.list_projects(owner)
        with self.controller.transaction() as (db, s):
            self.controller.sessions.reconcile(db, s)
            project = self.controller.owned(s.get('account_projects', {}), owner, project_id)
            accounts = [a for a in s['accounts'].values() if a['owner'] == owner and project_id in a['projects']]
            self._assert_removable(s, owner, project_id, sessions)
            for account in accounts:
                account['projects'].remove(project_id)
                account['revision'] = account.get('revision', 1) + 1
            for policy in s['policies'].values():
                if policy['owner'] == owner and project_id in policy.get('projects', [policy['project_id']]):
                    policy['projects'] = [p for p in policy.get('projects', [policy['project_id']]) if p != project_id]
            bindings = s.setdefault('session_account_projects', {})
            for pid in list(bindings):
                if bindings[pid] == project_id:
                    del bindings[pid]
            for task in s['tasks'].values():
                if task['owner'] == owner and task.get('account_project_id') == project_id:
                    task['account_project_deleted'] = project['name']
                    task['revision'] += 1
            del s['account_projects'][project_id]
            self.controller.audit(db, owner, 'account_project.deleted', project_id)
            return {'deleted': True}

    def resolve(self, owner, lineage, s):
        for pid in lineage:
            binding = s.get('session_account_projects', {}).get(pid)
            if binding:
                self.controller.owned(s.get('account_projects', {}), owner, binding)
                return binding
        return ''

    def binding(self, owner, pid):
        lineage = self.lineage(owner, pid)
        with self.controller.transaction() as (_, s):
            key = self.resolve(owner, lineage, s)
            return self.view(s, s['account_projects'][key]) if key else None

    def bind(self, owner, pid, account_project_id):
        lineage = self.lineage(owner, pid)
        related = {pid}
        projects = self.store.list_projects(owner)
        while True:
            children = {p['id'] for p in projects if (p.get('execution_round', {}).get('parent_project_id') or
                        p.get('managed_parent_project_id') or p.get('regression_source', {}).get('project_id')) in related}
            if children <= related:break
            related.update(children)
        with self.controller.transaction() as (db, s):
            self.controller.sessions.reconcile(db, s)
            project = self.controller.owned(s.get('account_projects', {}), owner, account_project_id)
            current = self.resolve(owner, lineage, s)
            if current == account_project_id:
                return self.view(s, project)
            if any(p['id'] in related and legacy_progress_active(s, p) for p in projects):
                raise Conflict('本会话或关联轮次正在执行，不能切换所属项目')
            # A round belongs to its source project. Never change identity beneath a live task.
            if len(lineage) > 1:
                raise Conflict('关联轮次沿用原会话所属项目，请在原会话设置所属项目')
            if active_nodes(s, [n for n in s['nodes'].values() if n['owner'] == owner and n['project_id'] in related
                                and not s['tasks'][n['task_id']].get('account_project_deleted')]):
                raise Conflict('该会话或关联轮次仍有未结束任务，不能切换所属项目')
            s.setdefault('session_account_projects', {})[pid] = account_project_id
            self.controller.audit(db, owner, 'session.account_project', pid, account_project_id)
            return copy.deepcopy(project)

    def configure(self, owner, project_id, data):
        requirements = data.get('requirements', [])
        if not isinstance(requirements, list) or not requirements:
            raise ValueError('请选择项目默认测试环境、租户与所需角色')
        with self.controller.transaction() as (db, s):
            project = self.controller.owned(s.get('account_projects', {}), owner, project_id)
            for r in requirements:
                if not isinstance(r, dict) or not all(isinstance(r.get(k), str) and r[k] for k in ('target', 'environment', 'tenant', 'role')):
                    raise ValueError('身份需求不完整')
                if not any(a['owner'] == owner and project_id in a['projects'] and
                           all(a[k] == r[k] for k in ('target', 'environment', 'tenant')) and
                           r['role'] in a['roles'] for a in s['accounts'].values()):
                    raise ValueError('所选身份没有绑定到此项目的账号')
            policy = data.get('shared_policy', '')
            if policy:
                p = self.controller.owned(s['policies'], owner, policy)
                if not p['enabled'] or project_id not in p.get('projects', [p['project_id']]):
                    raise ValueError('共享规则未获核验或不属于此项目')
            project['configuration'] = copy.deepcopy(dict(requirements=requirements, shared_policy=policy))
            self.controller.audit(db, owner, 'account_project.configured', project_id)
            return copy.deepcopy(project['configuration'])
