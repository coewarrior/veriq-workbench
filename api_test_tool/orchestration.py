"""Durable control plane. No browser/network/model execution in this module.

PostgreSQL scheduling locks serialize grants across request threads/processes. A new,
additive database leaves legacy project/report files untouched. Execution adapters
use the existing operation authority; native desktop execution uses account and
result lifecycle calls without platform mediation of browser actions.
"""
from __future__ import annotations
from .orchestration_storage import select_records

from contextlib import contextmanager
import copy
import hashlib
import json
import os
import time
import threading
from urllib.parse import urlsplit
from uuid import uuid4

DEFAULTS = dict(recovery_attempts=6, recovery_seconds=1200, fault_attempts=2,
                reservation_seconds=120, reservation_expirations=2,
                resource_review_seconds=600, login_reminder_seconds=600,
                login_review_seconds=1800, retention_review_seconds=7200,
                retention_repeat_seconds=86400)
TERMINAL = {'completed', 'stopped'}
ACTIVE = {'starting', 'running', 'stopping', 'isolated'}


def uid():
    return uuid4().hex


def text(value, name, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{name} 不能为空且不能超过 {limit} 字符')
    return value.strip()


def strings(value, name, maximum=100):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f'{name} 必须为列表，最多 {maximum} 项')
    out = [text(v, name, 160) for v in value]
    if len(set(out)) != len(out):
        raise ValueError(f'{name} 不允许重复项')
    return out


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def queue_key(n):
    return (n['queued'],n.get('queue_sequence',0),n['id'])

def public_account(a):
    return {k: v for k, v in a.items() if k not in {'credential', 'identity_key'}}


class Conflict(ValueError):
    pass


class Controller:
    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock
        self._stop = threading.Event()
        self._thread = None
        self.last_error = ''
        self._leader=None;self.settlement_callback=lambda:None
        from .account_projects import AccountProjects
        self.account_projects = AccountProjects(self)
        from .session_lifecycle import SessionLifecycle
        self.sessions = SessionLifecycle(self)
        from .account_management import AccountManagement
        self.account_management = AccountManagement(self)
        self.draining = lambda: False
        self.admission_lock = threading.RLock()
        self._background_jobs = {}
        self.report_worker_node_ids = lambda: []
        self.report_activity = lambda: {'count': 0, 'node_ids': []}
        from .database import ensure_schema
        ensure_schema()

    @contextmanager
    def background_job(self, kind):
        """Admit real work before DB/Store locks; retain it through commit."""
        with self.admission_lock:
            admitted = not self.draining()
            if admitted:
                self._background_jobs[kind] = self._background_jobs.get(kind, 0) + 1
        try:
            yield admitted
        finally:
            if admitted:
                with self.admission_lock:
                    self._background_jobs[kind] -= 1
                    if not self._background_jobs[kind]:
                        del self._background_jobs[kind]

    def background_activity(self):
        with self.admission_lock:
            return dict(self._background_jobs)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        import fcntl
        self._leader=open(self.store.root/'orchestration.scheduler.lock','a')
        try:fcntl.flock(self._leader,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self._leader.close();self._leader=None;return
        self._stop.clear()
        def tick():
            while not self._stop.is_set():
                try:
                    self.schedule()
                    self.settlement_callback()
                    self.last_error = ''
                except Exception as exc:
                    # No raw task, credential or adapter content in diagnostics.
                    self.last_error = type(exc).__name__
                self._stop.wait(5)
        self._thread = threading.Thread(target=tick, name='managed-task-controller', daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=25)
        if self._leader and (not self._thread or not self._thread.is_alive()):
            self._leader.close();self._leader=None

    def connect(self):
        from .database import connect
        return connect()

    @contextmanager
    def transaction(self, *, work_records=False, node_ids=None):
        from .native_work_plan import load_record_views
        views = load_record_views(self) if work_records else {}
        db = self.connect()
        try:
            from .database import begin_write
            begin_write(db, node_ids=node_ids)
            from .orchestration_storage import History, KINDS, Metadata
            s = Metadata(db)
            s.excluded = set(KINDS) | {'_work_record_views'}
            histories = {kind: History(db, kind) for kind in KINDS}
            s.update(histories)
            if work_records:
                s['_work_record_views'] = views
            if s.get('version') != 1:
                raise Conflict('调度数据版本不兼容，拒绝写入；需按迁移方案恢复')
            yield db, s
            for kind, history in histories.items():
                if s.get(kind) is not history:
                    # Preserve whole-map replacement used by administrative code.
                    replacement = copy.deepcopy(dict(s.get(kind, {})))
                    history.clear()
                    history.update(replacement)
                history.flush()
            s.flush()
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def heartbeat_transaction(self):
        """Same scheduling authority, limited to host liveness/progress maps."""
        from .orchestration_storage import Metadata
        with self.connect() as db:
            from .database import begin_write
            begin_write(db)
            state = Metadata(db, keys=('runners', 'leases'))
            yield state
            state.flush()

    def audit(self, db, owner, kind, subject, detail=''):
        db.execute('INSERT INTO audit(owner,at,kind,subject,detail) VALUES(%s,%s,%s,%s,%s)',
                   (owner, self.clock(), kind, subject, detail))

    def owned(self, records, owner, key):
        obj = records.get(key)
        if not obj or obj.get('owner') != owner:
            raise PermissionError('资源不存在或无权访问')
        return obj

    def project(self, owner, pid):
        return self.store.get_project(owner, pid)

    def request(self, owner, key, payload, action, *, work_records=False):
        key = text(key, 'request_id', 160)
        h = digest(payload)
        with self.transaction(work_records=work_records) as (db, s):
            old = db.execute('SELECT hash,value FROM receipts WHERE owner=%s AND key=%s', (owner, key)).fetchone()
            if old:
                if old[0] != h:
                    raise Conflict('request_id 已用于不同内容，请读取原任务或使用新标识')
                return json.loads(old[1])
            result = copy.deepcopy(action(db, s))
            db.execute('INSERT INTO receipts VALUES(%s,%s,%s,%s)', (owner, key, h, json.dumps(result)))
            return result

    def add_account(self, owner, data):
        pid = text(data.get('account_project_id') or data.get('project_id'), 'account_project_id', 100)
        if data.get('account_project_id'):
            self.account_projects.get(owner, pid)
        else:
            self.project(owner, pid)
        if data.get('account_project_id'):
            with self.transaction() as (_, s):
                login_url = self.account_projects.login(s, owner, pid)
            if data.get('target') and data['target'].rstrip('/') != login_url.rstrip('/'):
                raise ValueError('账号登录地址由所属项目统一维护，不能为账号填写不同地址')
        else:
            login_url = text(data.get('target'), '登录地址', 2000)
        u = urlsplit(login_url)
        if u.scheme not in {'https', 'http'} or not u.hostname or u.username or u.password:
            raise ValueError('登录地址必须是无内嵌凭据的 HTTP(S) 地址')
        target = f'{u.scheme}://{u.netloc.lower()}'
        identity = text(data.get('identity'), '账号', 200)
        environment = text(data['environment'], 'environment', 80) if data.get('environment') else ''
        tenant = text(data['tenant'], 'tenant', 160) if data.get('tenant') else ''
        roles = strings(data.get('roles', []), 'roles')
        # Origin defines the environment when the ordinary form omits a label.
        # Tenant and roles remain unknown until the trusted login adapter sees them.
        secret = data.get('credential', '')
        if not isinstance(secret, str) or len(secret) > 16000:
            raise ValueError('凭据格式错误')
        with self.transaction() as (db, s):
            if data.get('account_project_id'):
                if self.account_projects.login(s, owner, pid) != login_url:
                    raise Conflict('项目登录地址已变化，请刷新后重新保存账号')
            matches=[a for a in s['accounts'].values() if a['target'].lower()==target.lower() and a['identity']==identity
                     ]
            if len(matches)>1:
                raise Conflict('该账号有多份历史登记，请从已登记账号列表绑定，避免新增重复容量')
            old=matches[0] if matches else None
            environment=environment or (old['environment'] if old else target)
            ikey = digest([target.lower(), environment, identity])
            if old:
                if old['owner'] != owner:
                    raise Conflict('该真实账号已登记，请联系账号资源负责人授权；不重复创建容量')
                if (environment and old['environment']!=environment) or (tenant and old['tenant']!=tenant) or (roles and old['roles']!=roles):
                    raise Conflict('同一真实账号不可通过不同角色或租户登记增加容量；请核对原账号配置')
                if data.get('account_project_id'):
                    for other_id in old['projects']:
                        if other_id != pid and other_id in s.get('account_projects', {}) and self.account_projects.login(s, owner, other_id) != login_url:
                            raise Conflict('已有账号绑定了不同登录地址的项目，请统一产品登录地址后再绑定')
                changed_url=old.get('login',{}).get('url',old['target'])!=login_url
                if changed_url:
                    if any(old['id'] in lease['account_ids'] for lease in s['leases'].values()) or old.get('login_requested'):
                        raise Conflict('账号正在使用或登录中，暂不能更换产品登录入口')
                    self.account_management._invalidate(s,old)
                changed = bool(secret) or changed_url or pid not in old['projects']
                if secret:
                    if any(old['id'] in lease['account_ids'] for lease in s['leases'].values()) or old.get('login_requested'):
                        raise Conflict('账号正在使用或登录中，暂不能更新密码')
                    old['credential']=self.store._cipher.encrypt(secret.encode()).decode()
                    self.account_management._invalidate(s, old)
                if pid not in old['projects']:
                    old['projects'].append(pid)
                old.setdefault('login', {})['url'] = login_url
                if changed:old['revision'] = old.get('revision', 1) + 1
                self.audit(db, owner, 'account.grant', old['id'], pid)
                return public_account(old)
            aid = uid()
            a = dict(id=aid, owner=owner, identity_key=ikey, label=text(data.get('label', identity), 'label', 200),
                     target=target, environment=environment, identity=identity, tenant=tenant, roles=roles,
                     pool=data.get('pool', 'execution') if data.get('pool', 'execution') in {'execution', 'exploration'} else 'execution', state='needs_login', projects=[pid], created=self.clock(),
                     credential=self.store._cipher.encrypt(secret.encode()).decode() if secret else '',
                     policy_id='', verified_identity=False, login={'url':login_url})
            s['accounts'][aid] = a
            self.audit(db, owner, 'account.created', aid)
            return public_account(a)

    def create_task(self, owner, data, *, initial_plan=None):
        pid = text(data.get('project_id'), 'project_id', 100)
        self.project(owner, pid)
        goal = text(data.get('goal'), 'goal', 30000)
        modules = data.get('modules')
        if not isinstance(modules, list) or not 1 <= len(modules) <= 100:
            raise ValueError('modules 需为 1–100 个用户范围模块；该上限不是并发上限')
        normalized = []
        keys = set()
        for m in modules:
            if not isinstance(m, dict):
                raise ValueError('模块必须为对象')
            key = text(m.get('key'), '模块 key', 160)
            if key in keys:
                raise ValueError('模块 key 重复')
            keys.add(key)
            requirements = m.get('requirements', [])
            if not isinstance(requirements, list) or len(requirements) > 16:
                raise ValueError('requirements 最多 16 个阶段身份需求')
            reqs = []
            for r in requirements:
                if not isinstance(r, dict):
                    raise ValueError('账号需求必须为对象')
                reqs.append({k: text(r.get(k), k, 500) for k in ('target', 'environment', 'tenant', 'role')})
            normalized.append(dict(key=key, title=text(m.get('title'), '模块名称', 200),
                requirements=reqs, resource_planning=bool(m.get('resource_planning')), depends_on=strings(m.get('depends_on', []), 'depends_on'),
                locks=strings(m.get('locks', []), '业务资源锁'),
                shared_policy=m.get('shared_policy', ''), requires_account=m.get('requires_account', True), scope=text(m.get('scope', m.get('title')), '模块范围', 5000)))
        graph = {m['key']: m['depends_on'] for m in normalized}
        visited, visiting = set(), set()
        def visit(k):
            if k not in graph:
                raise ValueError('模块依赖不存在')
            if k in visiting:
                raise ValueError('模块依赖不能成环')
            if k in visited:
                return
            visiting.add(k)
            for dep in graph[k]:
                visit(dep)
            visiting.remove(k)
            visited.add(k)
        for k in graph:
            visit(k)
        mode = data.get('mode', 'execute')
        if mode not in {'execute', 'design'}:
            raise ValueError('mode 必须为 execute/design')
        lineage = self.account_projects.lineage(owner, pid)
        def create(db, s):
            self.store.get_project(owner, pid)  # Recheck after acquiring the task transaction.
            account_pid = self.account_projects.resolve(owner, lineage, s)
            if 'account_project_id' in data and (data['account_project_id'] or '') != account_pid:
                raise Conflict('会话所属项目已变化，请刷新后重新启动')
            if data.get('session_start'):
                existing=next((t for t in s['tasks'].values() if t['owner']==owner and t['project_id']==pid and not t.get('account_project_deleted') and
                    any(s['nodes'][nid]['state']!='completed' for nid in t['node_ids'] if not s['nodes'][nid].get('child_ids'))),None)
                if existing:return dict(task_id=existing['id'],revision=existing['revision'],status='existing',report_url='/ui-testing?project='+pid)
            source = data.get('source_task_id', '')
            baseline = None
            if source:
                src = self.owned(s['tasks'], owner, source)
                if src['project_id'] != pid:
                    raise ValueError('历史回归必须属于同一项目')
                baseline = copy.deepcopy(dict(task={k:v for k,v in src.items() if k!='baseline'}, nodes=[n for n in s['nodes'].values() if n['task_id'] == source]))
            if baseline is not None:
                from . import ui_records
                baseline['cases']={}
                baseline['sources']={}
                projects=self.store.list_projects(owner)
                for node in baseline['nodes']:
                    if node.get('child_ids'):continue
                    project=next((p for p in projects if p['id']==node.get('record_project_id') or p.get('managed_node_id')==node['id']),None)
                    if not project and src.get('session_workflow') and len(src['node_ids'])==1:project=self.store.get_project(owner,src['project_id'])
                    eid=node.get('record_execution_id') or (project or {}).get('ui_execution_id')
                    if project and eid:
                        record=ui_records.load(self.store,owner,project['id'],eid)
                        baseline['cases'][node['key']]=copy.deepcopy(record['cases'])
                        baseline['sources'][node['key']]={'project':copy.deepcopy(project),'document':(self.store.project_dir(owner,project['id'])/project['document_file']).read_text(),'requirements':copy.deepcopy(record.get('requirement_design',{}))}
            tid, now = uid(), self.clock()
            mapping = {m['key']: uid() for m in normalized}
            task = dict(id=tid, owner=owner, project_id=pid, account_project_id=account_pid, goal=goal, mode=mode, revision=1,
                        created=now, intent='run', execution_route=data.get('execution_route','managed'), session_workflow=bool(data.get('session_workflow')), source_task_id=source, baseline=baseline, node_ids=list(mapping.values()))
            if data.get('independent_module_records'):
                task['independent_module_records'] = True
            if task['execution_route'] == 'native_browser':
                # New tasks require real independent login contexts. Existing
                # tasks are not migrated and keep their original scene.
                task['native_browser_policy'] = 'direct_isolated'
            s['tasks'][tid] = task
            if data.get('explicit_module_plan'):
                task['initial_module_plan_hash']=digest(modules)
            for m in normalized:
                nid = mapping[m['key']]
                s['next_queue_sequence'] = s.get('next_queue_sequence', 0) + 1
                s['nodes'][nid] = dict(m, id=nid, owner=owner, project_id=pid, account_project_id=account_pid, task_id=tid,
                    parent_id='', budget_group=nid, depends_on=[mapping[k] for k in m['depends_on']],
                    automatic_configuration=bool(m.get('resource_planning')), phase='exploration', state='queued',
                    reason='等待桌面 Codex 会话领取账号' if task['execution_route']=='native_browser' else '等待已核验的执行连接程序',
                    revision=1, queued=now, queue_sequence=s['next_queue_sequence'], created=now, protected=False, checkpoint={},
                    attempts=[], result='not_run', coverage_complete=False, outcome_history=[],
                    reservation=None, reservation_expirations=0, waiting_since=now)
                from .testing_policy import exclude_unallocated_node
                exclude_unallocated_node(s['nodes'][nid], s)
                s['budgets'][nid] = dict(attempts=0, seconds=0, faults={}, active={}, recovery_ids={})
            self.audit(db, owner, 'task.created', tid)
            return dict(task_id=tid, revision=1, status='queued', report_url='/ui-testing?project='+pid)
        def create_planned(db, s):
            result = create(db, s)
            if initial_plan is not None:
                from .module_dispatch import apply_initial_plan_in_transaction
                apply_initial_plan_in_transaction(self, db, s, owner, result['task_id'], initial_plan)
                result['revision'] = s['tasks'][result['task_id']]['revision']
            return result
        payload = {'action':'create', **data}
        if initial_plan is not None:
            payload['initial_module_plan'] = initial_plan
        # The receipt and schedulable tree commit only after source validation
        # and binding succeed; a rejected plan cannot leave a queued placeholder.
        return self.request(owner, data.get('request_id'), payload, create_planned)

    def control(self, owner, tid, data):
        action = data.get('action')
        if action == 'archive_superseded':
            from .module_archive import archive
            return self.request(owner, data.get('request_id'), {'task_id': tid, **data},
                                lambda db, state: archive(self, db, state, owner, tid, data))
        if action not in {'stop', 'pause', 'resume'}:
            raise ValueError('action 必须为 stop/pause/resume')
        instruction = text(data['instruction'], '续测要求', 30000) if data.get('instruction') else ''
        return self.request(owner, data.get('request_id'), {'task_id':tid, **data},
                            lambda db, s: self._control(db, s, owner, tid, data, action, instruction))

    def _control(self, db, s, owner, tid, data, action, instruction=''):
        t = self.owned(s['tasks'], owner, tid)
        if action == 'resume' and t.get('account_project_deleted'):
            raise Conflict('所属项目已删除，本轮仅保留历史记录；请重新选择项目并开始新一轮测试')
        if data.get('revision') != t['revision']:
            raise Conflict('任务版本已变化，请刷新后再操作')
        selected = data.get('node_ids')
        if selected is not None:
            selected = strings(selected, 'node_ids', 100)
            if not selected or any(nid not in t['node_ids'] for nid in selected):
                raise ValueError('指定模块不属于当前任务')
            selected = set(selected)
            while True:
                descendants = {cid for nid in selected for cid in s['nodes'][nid].get('child_ids', [])}
                if descendants <= selected: break
                selected.update(descendants)
        if action == 'resume':
            targets = selected if selected is not None else t['node_ids']
            current_targets = set()
            for nid in targets:
                seen = set()
                while s['nodes'][nid].get('record_successor_node_id'):
                    successor = s['nodes'].get(s['nodes'][nid]['record_successor_node_id'])
                    if (nid in seen or not successor or successor['task_id'] != tid
                            or successor['id'] not in t['node_ids'] or successor['owner'] != owner):
                        raise Conflict('原记录已有其他续测任务或续接链无效；不能恢复第二个写入者')
                    seen.add(nid)
                    nid = successor['id']
                current_targets.add(nid)
            selected = targets = current_targets
            self.sessions.assert_available(s, t, list(targets))
            if t.get('execution_route') == 'native_browser':
                for nid in targets:
                    node = s['nodes'][nid]
                    if node.get('child_ids'):
                        continue
                    leases = [lease for lease in s['leases'].values() if lease['node_id'] == nid]
                    pending = [control for control in node.get('executor_controls', {}).values()
                               if control.get('state') not in {'exited', 'obsolete'}]
                    if (any(not lease.get('executor_stopped') or not lease.get('browser_stopped')
                            for lease in leases)
                            or (node.get('control_intent', t['intent']) in {'stop', 'pause'} and pending)):
                        raise Conflict('此模块的桌面会话或浏览器尚未确认退出；先按 S1 停止清单点击桌面停止并确认，再继续该模块。其他已退出模块可单独继续。')
        t['revision'] += 1
        intent = {'stop':'stop','pause':'pause','resume':'run'}[action]
        if selected is None or action == 'resume':
            t['intent'] = intent
        resumed = []
        for nid in t['node_ids']:
            if selected is not None and nid not in selected: continue
            n = s['nodes'][nid]
            if n.get('child_ids') or (n['state'] == 'completed' and
                    (action != 'resume' or n.get('coverage_complete'))):
                continue
            n['control_intent'] = intent
            from .module_dispatch import command
            command(s, n, action, self.clock())
            if action == 'resume' and instruction:
                n['checkpoint'] = {**n.get('checkpoint', {}), 'user_continuation': instruction}
            if n['state'] == 'completed':
                # Continue the unfinished assertions in the same thread and
                # record; the previous outcome remains historical evidence.
                s['next_queue_sequence'] = s.get('next_queue_sequence', 0) + 1
                n.update(queued=self.clock(), queue_sequence=s['next_queue_sequence'])
            n['revision'] += 1
            leases = [l for l in s['leases'].values() if l['node_id'] == nid]
            if action != 'resume':
                if t.get('execution_route') == 'native_browser':
                    from .native_contexts import invalidate
                    invalidate(n, 'revoked', self.clock())
                n['reservation'] = None
                n.pop('resource_wait', None)
                n.pop('native_claim_pending', None)
                for lease in leases: lease.pop('resource_request', None)
                for lease in list(leases):
                    starts=[e for e in s['outbox'].values() if e['lease_id']==lease['id'] and e['kind']=='start']
                    if starts and all(e['status']=='pending' and 'delivered_at' not in e for e in starts):
                        for event in starts:
                            event['status']='cancelled'
                        n.setdefault('undelivered_leases', []).append(lease['id'])
                        del s['leases'][lease['id']]
                        leases.remove(lease)
                if leases:
                    n.update(state='stopping', reason='正在结束执行进程并回收账号')
                    for l in leases:
                        l['revoked'] = True
                        l['human_mode'] = False
                        if l.get('resource_hold'):
                            n.update(state='isolated' if l.get('hold', {}).get('pending_operation_ids') else 'retained',
                                     reason=l.get('hold', {}).get('reason', '资源待核实'))
                        elif l.get('native_browser'):
                            n['reason'] = '平台已停止调度；请在所列桌面 Codex 会话点击停止，并确认测试浏览器停止后交还账号'
                        else:
                            self.event(s, 'interrupt', n, l['runner_id'], l['id'])
                else:
                    n.pop('direct_holder', None)
                    n.pop('actor_seen', None)
                    n.update(state='stopped' if action == 'stop' else 'paused', reason='用户已停止' if action == 'stop' else '用户已暂停')
                    if action == 'stop': n['finalization_pending'] = True
            elif leases:
                if all(l.get('resource_hold') and l.get('executor_stopped') for l in leases):
                    n.update(state='isolated', execution_ended=True,
                             reason='执行已退出；正在核对原操作与现场保留条件，符合条件后自动交还资源')
                else:
                    n.pop('execution_ended', None)
                    n.update(state='stopping', reason='等待原执行进程退出后继续')
                for lease in leases:lease['revoked']=True
            else:
                n.pop('execution_ended', None)
                n.update(state='queued', reason='等待资源', waiting_since=self.clock())
                from .module_dispatch import resume_cancelled_dispatch
                if resume_cancelled_dispatch(s, n, self.clock()):
                    resumed.append(nid)
        if action != 'resume':
            affected = {nid for nid in t['node_ids'] if selected is None or nid in selected}
            for cmd in select_records(s.get('direct_commands', {}), state='queued'):
                lease = s['leases'].get(cmd['lease_id'])
                if lease and lease['node_id'] in affected and cmd['state'] == 'queued':
                    cmd.update(state='cancelled', completed=self.clock())
                    cmd.pop('payload', None)
        from .session_lifecycle import settle_containers
        settle_containers(s)
        if t.get('execution_route') == 'native_browser':
            from .native_handoff import refresh
            for nid in t['node_ids']:
                node = s['nodes'][nid]
                for handoff in node.get('native_handoffs', {}).values():
                    refresh(s, node, handoff, self.clock())
        self.audit(db, owner, 'task.'+action, tid, json.dumps({'instruction': instruction}, ensure_ascii=False) if instruction else '')
        result = dict(task_id=tid, revision=t['revision'], intent=t['intent'])
        if resumed:
            from .module_dispatch import resume_packet
            project = self.store.get_project(owner, t['project_id'])
            result['resumed_modules'] = [{'node_id': nid, **resume_packet(self, s, t, s['nodes'][nid], project)}
                                         for nid in resumed]
        if t.get('execution_route') == 'native_browser':
            from .native_state import desktop_stop_view
            result['desktop_stop'] = desktop_stop_view(s, owner=owner, task_id=tid)
        return result

    def event(self, s, kind, n, runner_id, lease_id):
        eid = uid()
        s['outbox'][eid] = dict(id=eid, kind=kind, node_id=n['id'], task_id=n['task_id'],
            runner_id=runner_id, lease_id=lease_id, epoch=s['epoch'], revision=n['revision'], status='pending', created=self.clock())
        return eid

    @staticmethod
    def matching(a, r, pid):
        return (pid in a['projects'] and a.get('state') not in {'disabled', 'quarantined', 'isolated'}
                and all(a[k].rstrip('/') == r[k].rstrip('/') for k in ('target', 'environment', 'tenant'))
                and r['role'] in a['roles'])

    def needs_account(self, n, account):
        from .account_projects import resource_project
        if n['owner']!=account['owner']:return False
        if n.get('credential_execution') and not n['requirements']:
            project=self.store.get_project(n['owner'],n['project_id'])
            u=urlsplit(project.get('ui_target_url',''))
            return resource_project(n) in account['projects'] and account['target']==f'{u.scheme}://{u.netloc.lower()}'
        return any(self.matching(account,r,resource_project(n)) for r in n['requirements'])

    def bundle(self, s, n, shared=False, execution_only=False, runner_id=None):
        from .resource_scheduler import ResourceScheduler
        scheduler = ResourceScheduler(self, s, self.clock())
        result = scheduler.bundle(n, shared=shared, runner=s['runners'].get(runner_id))
        if execution_only and result and any(s['accounts'][aid]['pool'] != 'execution' for aid in result):
            return None
        return result

    def notice(self, s, n, kind, detail):
        key = n['id']+':'+kind
        if key not in s['notices']:
            s['notices'][key] = dict(id=key, owner=n['owner'], task_id=n['task_id'], node_id=n['id'],
                kind=kind, detail=detail, created=self.clock(), state='open')

    def schedule(self, *, native_handoff_source=None):
        """Decide complete resources, admission and dispatch in one transaction."""
        from .resource_holds import settle
        with self.background_job('scheduler') as admitted:
            if not admitted:
                return []
            settle(self)
            with self.transaction(work_records=True) as (db, state):
                return self._schedule_in_transaction(db, state, native_handoff_source=native_handoff_source)

    def _schedule_in_transaction(self, db, state, *, native_handoff_source=None):
        """Shared decision body; caller owns the single SQL transaction."""
        # HTTP callers are already counted at admission; the background caller
        # stays counted until its transaction commits. Do not take the admission
        # lock under the DB lock or revoke existing leases merely for deployment.
        if self.draining():
            return []
        from .resource_scheduler import ResourceScheduler
        from .direct_execution import expire_leases
        from .module_dispatch import expire_dispatches
        now = self.clock()
        self.sessions.reconcile(db, state)
        expire_leases(state, now)
        expire_dispatches(state, now)
        scheduler = ResourceScheduler(self, state, now)
        for lease in list(state['leases'].values()):
            if lease.get('resource_request') and not lease.get('revoked'):
                self._request_resources(db, state, lease, lease['resource_request'])
        return scheduler.schedule(db, native_handoff_source=native_handoff_source)

    def return_account(self, owner, host_id, data):
        """Record process exit once; preserve only actual unresolved resource holds."""
        from .resource_scheduler import pending_operations, retention_conditions
        lid = text(data.get('lease_id'), 'lease_id', 160)
        if data.get('executor_stopped') is not True:
            raise Conflict('执行进程尚未退出，不能重复分配账号')
        outcome = data.get('outcome', 'yield')
        if outcome not in {'yield', 'completed', 'blocked'}:
            raise ValueError('任务结束状态错误')
        def change(db, state):
            lease = state['leases'].get(lid)
            if not lease or lease['runner_id'] != host_id:
                raise PermissionError('账号不属于当前执行器')
            node = self.owned(state['nodes'], owner, lease['node_id'])
            task = state['tasks'][node['task_id']]
            if lease.get('native_browser') and data.get('browser_stopped') is not True:
                raise Conflict('请先确认本任务原生浏览器操作已停止；不能仅停止平台调度就交还账号')
            if lease.get('native_browser') and data.get('native_exit_source'):
                source = data['native_exit_source']
                if source not in {'executor_reported', 'user_confirmation'}:
                    raise ValueError('未知原生退出来源')
                if data.get('holder_id') != node.get('direct_holder'):
                    raise PermissionError('原生退出回执不属于本模块执行者')
                if source == 'user_confirmation' and (
                        task['revision'] != data.get('control_revision') or
                        node.get('control_intent', task['intent']) not in {'stop', 'pause'}):
                    raise Conflict('停止清单已变化，请重新核对当前桌面会话')
                from .module_dispatch import observe_control
                node['native_exit_evidence'] = {
                    'source': source, 'reason': data.get('reason', ''), 'at': self.clock()}
                node['native_browser_stopped'] = True
                from .native_contexts import invalidate
                invalidate(node, 'exited', self.clock())
                lease['browser_stopped'] = True
                observe_control(node, data['holder_id'], self.clock(), exited=True)
            if data.get('automatic_hold_resolution'):
                from .resource_holds import releasable
                if not releasable(state, lease):
                    raise Conflict('原隔离仍缺少完整核实或退出证据')
                self.audit(db, owner, 'resource_hold.auto_resolved', lid,
                           '原操作账本已核实、主辅助通道均退出且无业务现场保留条件')
            channels=lease.get('auxiliary_channels',{})
            for cid in data.get('auxiliary_stopped',[]):
                if cid in channels:channels[cid].update(state='exited',exited_at=self.clock(),exit_source='original_host_process_fence')
            if not data.get('scene_retained') and any(channel['state']!='exited' for channel in channels.values()):
                raise Conflict('辅助浏览器尚未确认退出，不能仅凭主浏览器结束释放账号')
            for item in data.get('auxiliary_uncertain',[]):
                key=node['id']+':aux:'+text(item.get('id'),'辅助动作标识',300)
                state['operations'].setdefault(key,{'id':key,'node_id':node['id'],'lease_id':lid,
                    'hash':item.get('hash',''),'action':'auxiliary_batch','state':'unknown',
                    'owner':owner,'runner_id':host_id,'created':self.clock()})
            checkpoint = copy.deepcopy(data.get('checkpoint') or node.get('checkpoint', {}))
            if lease.get('native_browser') and data.get('browser_stopped') is True:
                # A closed browser cannot remain held by an old page-retention
                # flag. Actual business-scene/resource conditions still apply.
                checkpoint.pop('retain_browser', None)
            if node.get('checkpoint', {}).get('user_continuation'):
                checkpoint['user_continuation'] = node['checkpoint']['user_continuation']
            if node.get('session_removed'):
                checkpoint.pop('retain_browser', None)
                checkpoint.pop('retain_scene', None)
            checkpoint.update(account_ids=lease['account_ids'], context_id=lease['context_id'])
            node['checkpoint'] = checkpoint
            for command in select_records(state.get('direct_commands', {}), lease_id=lid, state=('queued', 'running')):
                if command['state'] in {'queued', 'running'}:
                    command['state'] = 'cancelled' if command['state'] == 'queued' else 'unknown'
            for operation in select_records(state['operations'], lease_id=lid):
                if operation.get('lease_id') == lid and operation['state'] == 'pending':
                    operation['state'] = 'unknown'
            unresolved = pending_operations(state, lid)
            retained = retention_conditions(node, lease)
            scene_retained = bool(data.get('scene_retained') or checkpoint.get('retain_browser') or checkpoint.get('retain_scene'))
            if lease.get('resource_release_evidence'):
                retained = []; scene_retained = False
            from .cleanup_capabilities import blockers as cleanup_blockers
            cleanup_pending = cleanup_blockers(state, lease)
            # Browser exit does not prove that a server-side submission has stopped
            # or that a protected business condition can be reused by another task.
            if unresolved or retained or scene_retained or cleanup_pending:
                actual_scene = retained or scene_retained or any(
                    state['cleanup_objects'][oid].get('retain_scene') for oid in cleanup_pending)
                reason = ('业务操作结果未知，执行进程已退出；账号隔离待原动作核实' if unresolved
                          else '执行已退出，已登记业务现场仍需保留；账号不重新分配' if actual_scene
                          else '执行已结束；原清理操作尚未确认结束，等待原责任核实')
                lease.update(revoked=True, executor_stopped=True, executor_fenced=True, resource_hold=True,
                             browser_stopped=data.get('browser_stopped', not scene_retained),
                             browser_units=lease.get('browser_units', 1) if data.get('browser_stopped') is False else 0,
                             hold={'reason': reason, 'pending_operation_ids': [o['id'] for o in unresolved],
                                   'retained_conditions': retained, 'cleanup_responsibility_ids': cleanup_pending,
                                   'recorded_at': self.clock()})
                if node.get('session_removed') and not lease.get('browser_stopped'):
                    lease['close_browser_requested'] = True
                lease['return_outcome'] = outcome
                lease['return_record'] = {key: copy.deepcopy(data[key]) for key in ('outcome','result','coverage_complete','reason','children') if key in data}
                node.update(state='isolated' if unresolved or cleanup_pending and not actual_scene else 'retained',
                            reason=reason, finalization_pending=True, execution_ended=True)
                self.notice(state, node, 'resource_hold', reason)
                self.audit(db, owner, 'account.held', lid, reason)
                return {'released': False, 'retained': True, 'state': node['state'], 'node_id': node['id']}
            children = data.get('children')
            split_error = ''
            if children:
                try:
                    self._validate_children(children)
                except (ValueError, TypeError) as exc:
                    split_error = str(exc)
                    children = None
            node['revision'] += 1
            node.setdefault('context_affinity', {})[','.join(sorted(lease['account_ids']))] = lease['context_id']
            for operation in select_records(state['operations'], lease_id=lid):
                if operation.get('lease_id') == lid:
                    operation['historical'] = True
            for event in state['outbox'].values():
                if event['lease_id'] == lid and event['status'] == 'pending':
                    event['status'] = 'cancelled'
            del state['leases'][lid]
            if lease.get('native_browser'):
                node['native_browser_stopped'] = True
                node.pop('native_claim_pending', None)
            intent = node.get('control_intent', task['intent'])
            final_outcome = 'blocked' if lease.get('timeout_reason') or split_error else outcome
            if intent != 'run':
                node.update(state='stopped' if intent == 'stop' else 'paused', reason='执行已结束，账号已回收')
            elif final_outcome == 'completed':
                result = data.get('result', 'partial')
                if result not in {'passed', 'failed', 'partial', 'blocked', 'not_run'}:
                    result = 'partial'
                if result == 'passed' and not data.get('coverage_complete'):
                    result = 'partial'
                node['outcome_history'].append(dict(result=result, coverage_complete=bool(data.get('coverage_complete')), at=self.clock()))
                had_failure = any(h['result'] == 'failed' for h in node['outcome_history'])
                node.update(state='completed', reason='', result='retry_passed' if result == 'passed' and had_failure else result,
                            coverage_complete=bool(data.get('coverage_complete')))
            elif final_outcome == 'blocked':
                node.update(state='blocked', reason=split_error or lease.get('timeout_reason') or data.get('reason') or '任务受阻，账号已回收')
            else:
                state['next_queue_sequence'] = state.get('next_queue_sequence', 0) + 1
                # An explicit ordinary yield gives the next waiter its turn. A
                # resource-dependency yield preserves the waiting protection.
                node.setdefault('wait_history', []).append({'queued': node['queued'], 'released': self.clock()})
                node.update(state='queued', reason='已交还账号，按队列继续')
                if not lease.get('resource_request'):
                    node.update(queued=self.clock(), queue_sequence=state['next_queue_sequence'])
                if lease.get('resource_request'):
                    self._apply_resource_request(node, lease['resource_request'])
            if lease.get('direct'):
                state.setdefault('direct_settlements', {})[lid] = {'owner': owner, 'holder_id': node.get('direct_holder'),
                                                                  'node_id': node['id'], 'state': node['state']}
                if lease.get('native_browser'):
                    state['direct_settlements'][lid].update(native_browser=True, ack_required=False)
                    # Report completion never needs to retain a browser/account.
                    # Keep the original record and generation, not a new lease.
                    state['direct_settlements'][lid]['report_binding'] = {
                        'task_id': task['id'], 'node_revision': node['revision'],
                        'dispatch_id': (node.get('executor_dispatch') or {}).get('dispatch_id') or
                                       (node.get('dispatch_offer') or {}).get('id'),
                        'executor_ref': (node.get('executor_dispatch') or node.get('dispatch_offer') or {}).get('executor_ref'),
                        'project_id': node.get('record_project_id'),
                        'execution_id': node.get('record_execution_id')}
                    if data.get('report_pending') is True:
                        node['native_report_pending'] = {'lease_id': lid, 'since': self.clock()}
                    else:
                        node.pop('native_report_pending', None)
                node.pop('direct_holder', None); node.pop('actor_seen', None)
            if children and intent == 'run':
                self._split(db, state, owner, node, children)
            for parent in state['nodes'].values():
                if parent['state'] == 'container' and all(state['nodes'][cid]['state'] in {'completed', 'blocked', 'stopped'} for cid in parent['child_ids']):
                    parent['state'] = 'completed'; parent['finalization_pending'] = True
            if node['state'] in {'completed', 'blocked', 'stopped'}:
                node['finalization_pending'] = True
            self.audit(db, owner, 'account.returned', lid, final_outcome)
            result = {'released': True, 'state': node['state'], 'node_id': node['id']}
            if lease.get('native_browser'):
                from .native_handoff import released
                handoff = released(state, node, lid, self.clock(), lease['account_ids'])
                if handoff:
                    result['handoff'] = handoff
            if split_error:
                result['plan_error'] = split_error
            return result
        # An intentionally resolved resource hold has a separate durable return
        # receipt; lost ordinary return responses still use their original key.
        suffix = ':resolved' if data.get('resource_resolution') else ''
        return self.request(owner, 'return:' + host_id + ':' + lid + suffix, data, change)

    @staticmethod
    def _apply_resource_request(node, request):
        from .resource_scheduler import apply_request
        apply_request(node, request)

    def _request_resources(self, db, state, lease, request):
        if self.draining():
            raise Conflict('测试台正在发布更新，暂不分配新阶段资源；原租约和已保存进度保留，请稍后沿原绑定继续')
        from .resource_scheduler import request_resources
        return request_resources(self, db, state, lease, request)

    def request_resources(self, owner, lease_id, request):
        with self.transaction(work_records=True) as (db, state):
            lease = state['leases'].get(lease_id)
            if not lease:
                raise Conflict('原租约已结束，请读取原任务状态')
            self.owned(state['nodes'], owner, lease['node_id'])
            return self._request_resources(db, state, lease, request)

    def resolve_resource_hold(self, owner, lease_id, evidence, release=True):
        from .resource_scheduler import pending_operations
        evidence = text(evidence, '资源交还依据', 6000)
        with self.transaction() as (db, state):
            lease = state['leases'].get(lease_id)
            if not lease or not lease.get('resource_hold'):
                raise Conflict('原资源保留已结束或不存在')
            node = self.owned(state['nodes'], owner, lease['node_id'])
            if not release:
                lease.setdefault('resource_observations', []).append({'evidence': evidence, 'at': self.clock()})
                self.audit(db, owner, 'resource_hold.observed', lease_id, evidence)
                return {'released': False, 'close_required': False, 'node_id': node['id']}
            if pending_operations(state, lease_id):
                raise Conflict('原业务操作仍未核实，不能把资源标为空闲；先记录原动作结果')
            lease['resource_release_evidence'] = evidence
            lease['resolution_requested'] = True
            self.audit(db, owner, 'resource_hold.resolved', lease_id, evidence)
            if lease.get('browser_stopped') is False:
                return {'released': False, 'close_required': True, 'node_id': node['id']}
            host_id = lease['runner_id']
            request = {**lease.get('return_record', {}), 'lease_id': lease_id, 'executor_stopped': True, 'browser_stopped': True,
                       'scene_retained': False, 'resource_resolution': True,
                       'outcome': lease.get('return_outcome', 'blocked'),
                       'reason': '原操作和现场已核实，保留结果并完成资源交还'}
        return self.return_account(owner, host_id, request)

    @staticmethod
    def _validate_children(children):
        if not isinstance(children, list) or not 1 <= len(children) <= 100:
            raise ValueError('子任务格式错误')
        if any(not isinstance(c, dict) for c in children):
            raise ValueError('子任务必须为对象')
        keys = [str(c.get('key', i)) for i, c in enumerate(children)]
        if len(keys) != len(set(keys)):
            raise ValueError('子任务 key 不能重复')
        graph = {}
        for key, child in zip(keys, children):
            text(child.get('title'), 'title', 200); text(child.get('scope'), 'scope', 5000)
            strings(child.get('locks', []), '业务资源锁')
            graph[key] = strings(child.get('depends_on', []), 'depends_on')
        visiting, visited = set(), set()
        def visit(key):
            if key not in graph: raise ValueError('子任务依赖不存在')
            if key in visiting: raise ValueError('子任务依赖不能成环')
            if key in visited: return
            visiting.add(key)
            for dep in graph[key]: visit(dep)
            visiting.remove(key); visited.add(key)
        for key in keys: visit(key)
        return keys, graph

    def split(self, owner, nid, data):
        children = data.get('children')
        if not isinstance(children,list) or not 1 <= len(children) <= 100:
            raise ValueError('children 需为 1–100 项')
        with self.transaction() as (db,s):
            n=self.owned(s['nodes'],owner,nid)
            if n['state']!='queued' or n['revision']!=data.get('revision'):
                # Nested expansion needs an explicit reviewed resource/plan update.
                raise Conflict('只能在未派发检查点拆分原始模块；已拆分节点需先更新计划')
            if any(l['node_id']==nid for l in s['leases'].values()):
                raise Conflict('只能在未派发检查点按当前版本拆分')
            return self._split(db,s,owner,n,children)

    def _split(self,db,s,owner,n,children):
        from .resource_projection import copy_node
        self._validate_children(children)
        nid=n['id']
        keys=[str(c.get('key',i)) for i,c in enumerate(children)]
        if len(set(keys))!=len(keys):raise ValueError('子任务 key 不能重复')
        graph={key:list(c.get('depends_on',[])) for key,c in zip(keys,children)}
        visited=set();visiting=set()
        def visit(key):
            if key not in graph:raise ValueError('子任务依赖不存在')
            if key in visiting:raise ValueError('子任务依赖不能成环')
            if key in visited:return
            visiting.add(key)
            for dep in graph[key]:visit(dep)
            visiting.remove(key);visited.add(key)
        for key in keys:visit(key)
        mapping={key:uid() for key in keys}
        ids=[]
        for key,c in zip(keys,children):
            child=copy_node(n)
            cid=mapping[key]
            s['next_queue_sequence']=s.get('next_queue_sequence',0)+1
            child.update(state='queued',queued=n['queued'],queue_sequence=s['next_queue_sequence'],protected=bool(n.get('protected')) and not ids,id=cid,parent_id=nid,key=n['key'][:120]+'-'+cid,title=text(c.get('title'),'title',200),
                scope=text(c.get('scope'),'scope',5000),depends_on=list(n['depends_on'])+[mapping[d] for d in graph[key]], attempts=[])
            # Scope and budget stay inherited. Session children plan phase
            # identities against the same project grants before using browsers.
            if s['tasks'][n['task_id']].get('session_workflow'):
                child.update(requirements=[],resource_planning=False,automatic_configuration=True,shared_policy='')
            child.pop('requested_account_ids',None)
            child['locks']=list(dict.fromkeys([*n.get('locks',[]),*strings(c.get('locks',[]),'业务资源锁')]))
            child['inherited_locks']=list(child['locks'])
            child.pop('direct_holder',None)
            child.pop('actor_seen',None)
            child['scope_boundary']=n.get('scope_boundary', n['scope'])
            for field in ('thread_id','turn_id','thread_host','context_affinity','record_project_id','record_execution_id'):
                child.pop(field,None)
            child['checkpoint']={'parent_observations':copy.deepcopy(n.get('checkpoint',{}))}
            child.update(case_history={},outcome_history=[],result='not_run',coverage_complete=False)
            child.pop('finalization_pending',None)
            child.pop('worker',None)
            for field in ('executor_dispatch','executor_controls','business_started_at','business_completed_at','resource_wait','browser_ready_at','executor_dispatch_history','execution_ended','native_handoffs'):
                child.pop(field,None)
            child.pop('reservation',None)
            from .testing_policy import exclude_unallocated_node
            exclude_unallocated_node(child, s)
            s['nodes'][cid]=child
            ids.append(cid)
        n.update(state='container', child_ids=ids, revision=n['revision']+1,protected=False)
        s['tasks'][n['task_id']]['node_ids'].extend(ids)
        s['tasks'][n['task_id']]['revision']+=1
        self.audit(db,owner,'node.split',nid)
        return dict(parent_id=nid, child_ids=ids, revision=n['revision'])

    def snapshot(self, owner, task_id=None, *, include_history=False):
        with self.connect() as db:
            # Keep one consistent read without rebuilding every historical
            # browser receipt and screenshot through the rollback view.
            db.execute('BEGIN')
            from .orchestration_storage import History, read_snapshot_metadata
            s=read_snapshot_metadata(db,owner,task_id,include_history=include_history)
            tasks=[t for t in s['tasks'].values() if t['owner']==owner and (not task_id or t['id']==task_id)]
            if task_id and not tasks:
                raise PermissionError('任务不存在或无权访问')
            tids={t['id'] for t in tasks}
            ids={n['id'] for n in s['nodes'].values() if n['task_id'] in tids}
            operations=[dict(o) for o in History(db,'operations').select(state=('unknown','pending'))
                        if o['node_id'] in ids and not o.get('historical')]
        nodes=[{k:v for k,v in n.items() if include_history or k!='case_history'} for n in s['nodes'].values()
               if n['task_id'] in tids and (include_history or not n.get('module_archive'))]
        if not include_history:
            from .module_archive import current_task_nodes
            nodes = current_task_nodes(nodes, tasks)
        from .module_dispatch import node_dispatch
        for node in nodes:node.update(node_dispatch(node))
        leaves=[n for n in nodes if not n.get('child_ids') and
                s['nodes'].get(n.get('record_successor_node_id'), {}).get('task_id') != n['task_id']]
        counts={key:sum(n['result']==key for n in leaves) for key in ('not_run','passed','retry_passed','failed','partial','blocked')}
        from .native_state import desktop_stop_view
        return dict(tasks=[{k:v for k,v in t.items() if k!='baseline'} for t in tasks],nodes=nodes,
            accounts=[public_account(a) for a in s['accounts'].values() if a['owner']==owner],
            leases=[l for l in s['leases'].values() if l['node_id'] in ids],
            runners=[{k:v for k,v in r.items() if k!='secret' and
                     not (k=='model_slots' and tasks and all(t.get('execution_route')=='native_browser' for t in tasks))} for r in s['runners'].values() if r['owner']==owner],
            notices=[x for x in s['notices'].values() if x['owner']==owner and x['task_id'] in tids],
            operations=operations,
            budgets={k:v for k,v in s['budgets'].items() if any(n['budget_group']==k for n in nodes)},
            policies=[{k:v for k,v in p.items() if k!='session_seed'} for p in s['policies'].values() if p['owner']==owner],
            parameters=DEFAULTS, controller_error=self.last_error, summary=dict(total=len(leaves), results=counts,
                coverage_complete=sum(n['coverage_complete'] for n in leaves),
                completed=sum(n['state']=='completed' for n in leaves), unit='执行叶子模块；不等同于用例通过率'),
            execution_ready=any(r['owner']==owner and r['enabled'] and r['enforcement_verified'] and self.clock()-r['heartbeat']<=60 for r in s['runners'].values()),
            desktop_stop=desktop_stop_view(s, owner=owner, task_id=task_id),
            platform_execution={'enabled':False,'ready':False,'retired':True})

    def active_count(self):
        from .orchestration_storage import read_sections
        with self.connect() as db:
            s=read_sections(db, ('leases',))
        return sum(not (lease.get('resource_hold') and lease.get('executor_stopped'))
                   for lease in s['leases'].values())

    # The following host methods are intentionally NOT browser/MCP owner APIs.
    # Only the verified execution adapter can attest identity, capacity and safety.
    def register_host(self, owner, runner_id, *, enforcement_evidence, browser_slots, model_slots):
        self.store._owner_dir(owner)
        if not isinstance(enforcement_evidence, dict) or not all(enforcement_evidence.get(k) for k in (
                'network_isolation', 'credential_isolation', 'tool_gate', 'browser_context_isolation', 'version')):
            raise ValueError('执行连接程序尚未完成隔离与受控入口验收')
        for value in (browser_slots,model_slots):
            if type(value) is not int or not 0 <= value <= 1024:
                raise ValueError('容量必须是实测的非负整数')
        with self.transaction() as (db,s):
            old=s['runners'].get(runner_id)
            if old and old['owner']!=owner:
                raise PermissionError('执行连接归属不一致')
            if old and old.get('evidence',{}).get('machine_id') and old['evidence']['machine_id']!=enforcement_evidence.get('machine_id'):
                raise Conflict('执行机本地身份不一致，不能将旧租约交给另一台机器')
            s['runners'][runner_id]=dict(id=runner_id,owner=owner,enabled=True,enforcement_verified=True,
                evidence=copy.deepcopy(enforcement_evidence),browser_slots=browser_slots,model_slots=model_slots,
                heartbeat=self.clock())
            self.audit(db,owner,'host.registered',runner_id)

    def host_heartbeat(self, owner, runner_id, browser_slots, model_slots, progress=None):
        if any(type(v) is not int or not 0<=v<=1024 for v in (browser_slots,model_slots)):
            raise ValueError('容量格式错误')
        with self.heartbeat_transaction() as s:
            r=self.owned(s['runners'],owner,runner_id)
            r.update(heartbeat=self.clock(),browser_slots=browser_slots,model_slots=model_slots)
            for lid,sequence in (progress or {}).items():
                lease=s['leases'].get(lid)
                if lease and lease['runner_id']==runner_id and lease.get('progress_sequence')!=sequence:
                    lease.update(progress_sequence=sequence,progress_at=self.clock())
        return self.schedule()

    def verify_account(self, owner, aid, *, identity, tenant):
        with self.transaction() as (db,s):
            a=self.owned(s['accounts'],owner,aid)
            if a['identity']!=identity or a['tenant']!=tenant:
                raise Conflict('实际登录身份/租户与登记不一致')
            a.update(verified_identity=True,state='ready')
            self.audit(db,owner,'account.verified',aid)

    def approve_policy(self, owner, pid, account_id, *, version, operations, evidence):
        self.project(owner,pid)
        if not evidence or not isinstance(operations,dict) or not operations:
            raise ValueError('共享策略必须包含已核验的适配操作及证据')
        for spec in operations.values():
            if spec.get('effect') not in {'verified_read','local','isolated_write'} or not spec.get('adapter'):
                raise ValueError('未知效果不能进入共享操作集合')
        with self.transaction() as (db,s):
            a=self.owned(s['accounts'],owner,account_id)
            if pid not in a['projects']:
                raise PermissionError('账号未授权此项目')
            policy_id=uid()
            s['policies'][policy_id]=dict(id=policy_id,owner=owner,project_id=pid,version=version,
                operations=copy.deepcopy(operations),evidence=evidence,enabled=True)
            a['policy_id']=policy_id
            self.audit(db,owner,'policy.approved',policy_id)
            return policy_id

    def revoke_policy(self, owner, policy_id):
        with self.transaction() as (db,s):
            p=self.owned(s['policies'],owner,policy_id)
            p['enabled']=False
            p['automatic_fault']=False  # Explicit revocation must never auto-rearm.
            for l in s['leases'].values():
                if l['policy_id']==policy_id:
                    l['revoked']=True
                    n=s['nodes'][l['node_id']]
                    n.update(state='isolated',reason='共享操作策略已撤销，等待现场核实')
                    self.event(s,'interrupt',n,l['runner_id'],l['id'])
            self.audit(db,owner,'policy.revoked',policy_id)

    def pending_events(self, owner, runner_id):
        from .orchestration_storage import read_sections
        with self.connect() as db:
            state = read_sections(db, ('runners', 'outbox'))
        self.owned(state['runners'], owner, runner_id)
        if not any(e['runner_id'] == runner_id and e['status'] == 'pending'
                   for e in state['outbox'].values()):
            return []
        # If there is work, recheck and mark delivery under the original writer.
        with self.transaction() as (_,s):
            self.owned(s['runners'],owner,runner_id)
            result=[]
            for e in s['outbox'].values():
                if e['runner_id']!=runner_id or e['status']!='pending':
                    continue
                n=s['nodes'][e['node_id']]
                l=s['leases'].get(e['lease_id'])
                if e['kind']=='start' and (not l or l['revoked'] or e['epoch']!=s['epoch'] or e['revision']!=n['revision']):
                    e['status']='cancelled'
                    continue
                e['delivered_at']=e.get('delivered_at',self.clock())
                result.append(copy.deepcopy(e))
            return result

    def acknowledge_start(self, owner, event_id, *, thread_id, turn_id):
        with self.transaction() as (db,s):
            e=s['outbox'].get(event_id)
            if not e:
                raise Conflict('派发不存在')
            n=self.owned(s['nodes'],owner,e['node_id'])
            l=s['leases'].get(e['lease_id'])
            if e['kind']!='start' or not l or l['revoked'] or e['epoch']!=s['epoch'] or e['revision']!=n['revision']:
                raise Conflict('派发已撤销；迟到启动回执不能重新获得权限')
            if e['status']=='acknowledged':
                if (e['thread_id'],e['turn_id'])!=(thread_id,turn_id):
                    raise Conflict('同一派发不能创建第二个执行者')
                return
            e.update(status='acknowledged',thread_id=text(thread_id,'thread_id'),turn_id=text(turn_id,'turn_id'))
            n.update(state='running',reason='',thread_id=thread_id,turn_id=turn_id,thread_host=e['runner_id'])
            self.audit(db,owner,'dispatch.acknowledged',event_id)

    def authorize_operation(self, owner, lease_id, operation_id, action, parameters, *, adapter, epoch, revision):
        """Record before dispatch. Repeated/unknown operation IDs never authorize replay."""
        operation_id=text(operation_id,'operation_id',160)
        with self.transaction() as (db,s):
            l=s['leases'].get(lease_id)
            if not l:
                raise Conflict('租约不存在')
            n=self.owned(s['nodes'],owner,l['node_id'])
            if l['revoked'] or epoch!=s['epoch'] or epoch!=l['epoch'] or revision!=n['revision'] or n['state']!='running' or s['tasks'][n['task_id']]['intent']!='run':
                raise Conflict('执行授权已失效')
            payload=digest([lease_id,action,parameters,adapter])
            op=s['operations'].get(operation_id)
            if op:
                if op['hash']!=payload:
                    raise Conflict('operation_id 内容冲突')
                return dict(dispatch=False,state=op['state'],result=op.get('result'))
            if l['mode']=='shared':
                p=s['policies'].get(l['policy_id'])
                spec=p['operations'].get(action) if p and p['enabled'] else None
                if not spec or spec['adapter']!=adapter:
                    raise PermissionError('共享探索未核验此操作，需申请独占探索')
            # Adapter must independently validate target, parameters, business scope,
            # request channels, and isolation before it actually sends anything.
            s['operations'][operation_id]=dict(id=operation_id,node_id=n['id'],lease_id=lease_id,
                hash=payload,state='pending',action=action,adapter=adapter,created=self.clock())
            self.audit(db,owner,'operation.authorized',operation_id)
            return dict(dispatch=True,state='pending')

    def operation_result(self, owner, operation_id, *, state, result):
        if state not in {'confirmed','not_sent','unknown'}:
            raise ValueError('操作状态错误')
        with self.transaction() as (db,s):
            op=s['operations'].get(operation_id)
            if not op:
                raise Conflict('操作不存在')
            n=self.owned(s['nodes'],owner,op['node_id'])
            if op['state'] in {'confirmed','not_sent'}:
                if op['state']!=state or op['result']!=result:
                    raise Conflict('已确认操作结果不可覆盖')
                return
            op.update(state=state,result=result,finished=self.clock())
            if state=='unknown':
                n.update(state='isolated',reason='业务操作结果未知，禁止重放与释放')
                s['leases'][op['lease_id']]['revoked']=True
            self.audit(db,owner,'operation.'+state,operation_id)

    def validate_requirements(self,s,n,requirements):
        from .account_projects import resource_project
        from .managed_service import origin
        if not isinstance(requirements,list) or not 1 <= len(requirements) <= 16:
            raise ValueError('需要 1–16 个下一阶段身份需求')
        project=self.store.get_project(n['owner'],n['project_id'])
        targets={origin(project['ui_target_url'])} if project.get('ui_target_url') else {r['target'] for r in n['requirements']}
        normalized=[]
        for r in requirements:
            if not isinstance(r,dict):raise ValueError('身份需求必须为对象')
            r={k:text(r.get(k),k,500) for k in ('target','environment','tenant','role')}
            if r['target'] not in targets or not any(a['owner']==n['owner'] and resource_project(n) in a['projects']
                    and all(a[k]==r[k] for k in ('target','environment','tenant')) and r['role'] in a['roles'] for a in s['accounts'].values()):
                raise PermissionError('身份必须来自当前项目授权且匹配测试目标的账号')
            normalized.append(r)
        return normalized

    def release(self, owner, lease_id, *, checkpoint, safety, next_phase=None, completed=False, result='not_run', coverage_complete=False, blocked_reason=None, children=None, requirements=None):
        """Only host attestation, never a model's 'safe=true'. Keep held on uncertainty."""
        if not isinstance(safety,dict) or not all(safety.get(k) for k in ('executor_fenced','inflight_reconciled','scene_verified')):
            raise Conflict('缺少执行者撤权、在途核实或现场核实证据')
        if result not in {'not_run','passed','failed','partial','blocked'}:
            raise ValueError('结果格式错误')
        if result=='passed' and not coverage_complete:
            raise ValueError('必要检查点未完整，不能判定通过')
        with self.transaction() as (db,s):
            l=s['leases'].get(lease_id)
            if not l:
                raise Conflict('租约不存在，请读取最新状态')
            n=self.owned(s['nodes'],owner,l['node_id'])
            if bool(select_records(s['operations'],lease_id=lease_id,state=('pending','unknown'))):
                raise Conflict('尚有未知或在途操作，不能释放')
            if next_phase not in {None,'exploration','design','execution','report'}:
                raise ValueError('阶段错误')
            task=s['tasks'][n['task_id']]
            if task['mode']=='design' and next_phase=='execution':
                raise PermissionError('仅设计任务不能自动进入执行')
            if requirements is not None:
                if l['revoked'] or task['intent']!='run':
                    raise Conflict('已撤权的任务不能修改资源计划')
                normalized=self.validate_requirements(s,n,requirements)
                n.update(requirements=normalized,resource_planning=False,shared_policy='')
                # A different identity must not inherit an old browser checkpoint.
                n.pop('context_affinity',None)
                self.audit(db,owner,'resources.planned',n['id'])
            n['checkpoint']=copy.deepcopy(checkpoint)
            if requirements is None:
                n.setdefault('context_affinity',{})[','.join(sorted(l['account_ids']))]=l['context_id']
            if result!='not_run':
                n['outcome_history'].append(dict(result=result,coverage_complete=bool(coverage_complete),at=self.clock()))
                had_failure=any(h['result']=='failed' for h in n['outcome_history'])
                n['result']=('retry_passed' if had_failure else 'passed') if result=='passed' else ('failed' if had_failure else result)
                n['coverage_complete']=bool(coverage_complete)
            n['revision']+=1
            if task['intent']!='run':
                n.update(state='stopped' if task['intent']=='stop' else 'paused',reason='用户控制请求已完成')
            elif blocked_reason:
                n.update(state='blocked',reason=text(blocked_reason,'停止恢复原因'))
            elif completed:
                n.update(state='completed',reason='')
            else:
                n.update(state='queued',phase=next_phase or n['phase'],reason='等待下一安全阶段资源',waiting_since=self.clock())
            del s['leases'][lease_id]
            for e in s['outbox'].values():
                if e['lease_id']==lease_id and e['status']=='pending':
                    e['status']='cancelled'
            # Preserve the older queue's next opportunity at exploration handoff.
            for older in s['nodes'].values():
                if older['state']=='queued' and queue_key(older)<queue_key(n):
                    older['protected']=True
            if l['mode']=='shared' and not any(set(l['account_ids']) & set(x['account_ids']) for x in s['leases'].values()):
                for aid in l['account_ids']:
                    s['accounts'][aid]['pool']='execution'
            for parent in s['nodes'].values():
                if parent['state']=='container' and all(s['nodes'][cid]['state']=='completed' for cid in parent['child_ids']):
                    parent['state']='completed'
            if children and task['intent']=='run':
                if n.get('parent_id') or n['phase']!='exploration':raise Conflict('仅原始模块的探索检查点可拆分')
                self._split(db,s,owner,n,children)
            self.audit(db,owner,'lease.released',lease_id)

    def wait_human(self, owner, lease_id, *, checkpoint, retained=False, reason):
        with self.transaction() as (db,s):
            l=s['leases'].get(lease_id)
            if not l:
                raise Conflict('租约不存在')
            n=self.owned(s['nodes'],owner,l['node_id'])
            l['revoked']=True
            n.update(state='retained' if retained else 'waiting_human',reason=text(reason,'等待原因'),
                waiting_since=self.clock(),checkpoint=copy.deepcopy(checkpoint),reservation=None,
                review_at=self.clock()+DEFAULTS['retention_review_seconds'])
            self.event(s,'interrupt',n,l['runner_id'],l['id'])
            self.audit(db,owner,'node.waiting',n['id'])

    def begin_recovery(self, owner, nid, recovery_id, fault_id):
        with self.transaction() as (db,s):
            n=self.owned(s['nodes'],owner,nid)
            if s['tasks'][n['task_id']]['intent']!='run':
                raise Conflict('已停止/暂停任务不能自动恢复')
            b=s['budgets'][n['budget_group']]
            if recovery_id in b['recovery_ids']:
                return dict(start=False,attempt=b['recovery_ids'][recovery_id])
            if bool(select_records(s['operations'],node_id=nid,state=('pending','unknown'))):
                raise Conflict('未知业务操作先核实，不适用自动重试')
            elapsed=b['seconds']+sum(max(0,self.clock()-x['started']) for x in b['active'].values())
            if b['attempts']>=DEFAULTS['recovery_attempts'] or elapsed>=DEFAULTS['recovery_seconds'] or b['faults'].get(fault_id,0)>=DEFAULTS['fault_attempts']:
                raise Conflict('自动恢复预算已用尽，需负责人处理')
            b['attempts']+=1
            b['faults'][fault_id]=b['faults'].get(fault_id,0)+1
            attempt=dict(node_id=nid,fault_id=fault_id,started=self.clock(),state='running')
            b['active'][recovery_id]=attempt
            b['recovery_ids'][recovery_id]=copy.deepcopy(attempt)
            self.audit(db,owner,'recovery.started',nid)
            return dict(start=True,remaining_seconds=DEFAULTS['recovery_seconds']-elapsed,
                        delay_seconds=15 if b['faults'][fault_id]==1 else 60)

    def finish_recovery(self, owner, nid, recovery_id, *, recovered):
        with self.transaction() as (db,s):
            n=self.owned(s['nodes'],owner,nid)
            b=s['budgets'][n['budget_group']]
            a=b['active'].get(recovery_id)
            if not a:
                if recovery_id in b['recovery_ids']:
                    return
                raise Conflict('恢复记录不存在')
            if a['node_id']!=nid:
                raise Conflict('恢复记录归属不一致')
            b['seconds']+=max(0,self.clock()-a['started'])
            b['recovery_ids'][recovery_id].update(state='recovered' if recovered else 'failed',finished=self.clock())
            del b['active'][recovery_id]
            self.audit(db,owner,'recovery.finished',nid)

    def reserve(self, owner, nid, account_ids, *, release_evidence):
        """Host supplies observed short release signal, not an AI duration guess."""
        from .account_projects import resource_project
        with self.transaction() as (db,s):
            n=self.owned(s['nodes'],owner,nid)
            if n['state']!='queued' or not n['protected'] or not n['requirements'] or s['tasks'][n['task_id']]['intent']!='run':
                raise Conflict('当前任务不符合公平预留条件')
            if n['reservation']:
                return n['reservation']  # never extend the original deadline
            if n['reservation_expirations']>=DEFAULTS['reservation_expirations']:
                raise Conflict('连续预留超期，转资源协调')
            if not release_evidence or release_evidence==n.get('last_reservation_evidence'):
                raise Conflict('没有新的可信释放信号，不能立即重新预留')
            if any(s['nodes'][d]['state']!='completed' for d in n['depends_on']):
                raise Conflict('依赖未就绪，不预留账号')
            busy={a for l in s['leases'].values() for a in l['account_ids']}
            busy.update(a for x in s['nodes'].values() if x.get('reservation') for a in x['reservation']['accounts'])
            aids=strings(account_ids,'account_ids',16)
            if not aids or len(aids)>=len(n['requirements']):
                raise ValueError('仅预留下一阶段资源集合的严格子集')
            for aid in aids:
                a=self.owned(s['accounts'],owner,aid)
                if aid in busy or not any(self.matching(a,r,resource_project(n)) for r in n['requirements']):
                    raise Conflict('预留账号已占用或身份不匹配')
            n['reservation']=dict(accounts=aids,until=self.clock()+DEFAULTS['reservation_seconds'])
            n['last_reservation_evidence']=release_evidence
            self.audit(db,owner,'resources.reserved',nid)
            return copy.deepcopy(n['reservation'])

    def fixture(self, owner, nid, data):
        from .shared_fixtures import apply_fixture
        with self.transaction() as (db, state):
            node = self.owned(state['nodes'], owner, nid)
            return apply_fixture(self, db, state, owner, node, data)
