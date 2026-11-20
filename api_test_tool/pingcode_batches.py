"""Durable report operations; HTTP requests enqueue work, never own its lifetime."""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import threading
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from starlette.requests import Request


def now():
    return datetime.now(timezone.utc).isoformat()


ACTIVE = {'queued', 'running'}
ACTIONS = {'accept', 'reopen', 'refresh', 'retry-content', '__submit__', 'titles',
           'pending_submission', 'pending_regression', 'rejected', 'deferred',
           'restore', 'regression_passed', 'regression_failed'}


def eligibility(record, action):
    record = record or {}
    state = record.get('triage_status') or ('submitted' if record.get('status') == 'submitted' else 'pending_submission')
    if action == 'refresh':
        return 'ready', ''
    if record.get('status') in {'pending', 'unknown', 'loading', 'unavailable'} or record.get('remote_sync', {}).get('status') in {'pending', 'unknown'}:
        return 'skipped', '结果待核对，请先刷新同步状态'
    if action in {'accept', 'reopen'}:
        if record.get('status') != 'submitted' or not record.get('item'):
            return 'skipped', '未关联已提交的 PingCode 缺陷'
        if state != ('regression_passed' if action == 'accept' else 'regression_failed'):
            return 'skipped', '当前回归结论不适用于此操作'
        if action == 'reopen' and not record.get('lineage'):
            return 'skipped', '没有可重新打开的历史缺陷'
        if record.get('description_error') or record.get('screenshot_error'):
            return 'skipped', '正文或截图需要先核对'
        if record.get('remote_state') and (record.get('remote_state_action') == action or
                action == 'reopen' and not record.get('remote_state_action')):
            return 'noop', '已经是目标状态，无需变更'
    elif action == '__submit__':
        if record and not (record.get('status') in {'draft', 'failed'} and state == 'pending_submission'):
            return 'skipped', '已提交或当前状态不可提交'
    elif action == 'retry-content':
        if record.get('status') != 'submitted' or not (record.get('description_error') or record.get('screenshot_error')):
            return 'skipped', '无需补交正文与截图'
    elif action == 'restore' and state not in {'rejected', 'deferred'}:
        return 'skipped', '只有已拒绝或暂缓的问题可以恢复'
    elif action == 'pending_submission' and record.get('item'):
        return 'skipped', '已有原缺陷，不可恢复为新建草稿'
    elif state == action:
        return 'noop', '已经是目标状态，无需变更'
    return 'ready', ''


class DefectBatches:
    def __init__(self, app, store, service, execute):
        self.app, self.store, self.service, self.execute = app, store, service, execute
        self.root = store.root / 'defect-batches'
        store._mkdir(self.root)
        self.lock = threading.RLock()
        self.wake, self.closing = threading.Event(), threading.Event()
        self.thread = None
        self.lease = None
        self.jobs = {path.stem: store._read(path) for path in self.root.glob('*.json')}

    def save(self, job):
        job['updated_at'] = now()
        self.store._write(self.root / (job['id'] + '.json'), job)
        self.jobs[job['id']] = job

    def snapshot(self, job):
        return copy.deepcopy({k: v for k, v in job.items() if k not in {'context', 'reason', 'digest', 'title_revisions'}})

    @staticmethod
    def identity(item):
        return (item['project_id'], item['run_id'], item['draft_id'])

    def assert_available(self, request, project_id, run_id, draft_id):
        own = getattr(request.state, 'batch_job_id', None)
        with self.lock:
            for job in self.jobs.values():
                if job['owner'] == request.state.owner and job['id'] != own and job['status'] in ACTIVE:
                    if any(self.identity(item) == (project_id, run_id, draft_id) and item['outcome'] in ACTIVE for item in job['items']):
                        raise HTTPException(409, '该缺陷正在后台处理中，完成后可继续操作')

    def stage(self, request, input_id, data):
        input_id = str(UUID(input_id))
        root = self.root / 'inputs' / request.state.owner
        self.store._mkdir(root)
        path = root / (input_id + '.json')
        value = dict(actor=getattr(request.state, 'actor_owner', request.state.owner), data=data)
        encrypted = self.store._cipher.encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()
        with self.lock:
            if path.exists():
                previous = self.read_input(request.state.owner, input_id, value['actor'])
                if previous != data:
                    raise HTTPException(409, '同一保存编号对应的内容已变化，请重新提交')
            else:
                self.store._write(path, {'ciphertext': encrypted})
        return {'id': input_id}

    def read_input(self, owner, input_id, actor):
        path = self.root / 'inputs' / owner / (str(UUID(input_id)) + '.json')
        value = json.loads(self.store._cipher.decrypt(self.store._read(path)['ciphertext'].encode()))
        if value['actor'] != actor:
            raise HTTPException(403, '无法使用其他账号的审核内容')
        return value['data']

    def create(self, request, pid, rid, data):
        job_id = str(UUID(data.get('id', '')))
        action, entries = data.get('action'), data.get('items')
        reason = data.get('reason', '')
        if action not in ACTIONS or not isinstance(entries, list) or not entries:
            raise ValueError('请选择有效的批量操作和缺陷')
        if not isinstance(reason, str) or len(reason) > 4000:
            raise ValueError('操作原因不能超过 4000 字符')
        if action in {'rejected', 'deferred', 'regression_passed', 'regression_failed'} and not reason.strip():
            raise ValueError('请填写操作原因或更正依据')
        owner = request.state.owner
        actor = getattr(request.state, 'actor_owner', owner)
        digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        with self.lock:
            existing = self.jobs.get(job_id)
            if existing:
                self.authorize(existing, owner, pid, rid)
                if existing['digest'] != digest or existing['context']['actor_owner'] != actor:
                    raise HTTPException(409, '该任务编号已用于其他操作')
                return self.snapshot(existing)
            items, seen = [], set()
            for entry in entries:
                item = {k: entry[k] for k in ('project_id', 'run_id', 'draft_id')}
                identity = self.identity(item)
                if identity in seen:
                    continue
                seen.add(identity)
                self.service.source(owner, *identity)
                self.assert_available(request, *identity)
                if entry.get('input_id'):
                    self.read_input(owner, entry['input_id'], actor)
                    item['input_id'] = str(UUID(entry['input_id']))
                if action in {'__submit__', 'titles'} and not item.get('input_id'):
                    raise ValueError('尚未保存已审核的内容')
                if getattr(request.state, 'aggregate_context', None):
                    item['source_token'] = self.store.project_reports.source_token(owner, item['project_id'], item['run_id'])
                    item['family_token'] = self.store.project_reports.family_token(owner, request.state.aggregate_context, item['project_id'], item['run_id'])
                item.update(outcome='queued', message='等待处理', expected_updated_at=entry.get('expected_updated_at'))
                items.append(item)
            # Detect conflicting observations without making remote requests in the enqueue request.
            observations = {}
            if action in {'accept', 'reopen'}:
                observed = {self.identity(item): item for item in items}
                for source in data.get('observations', []):
                    identity = (source['project_id'], source['run_id'], source['draft_id'])
                    if identity not in observed:
                        self.service.source(owner, *identity)
                        observed[identity] = dict(source)
                for item in observed.values():
                    _, _, path = self.service.source(owner, *self.identity(item))
                    record = self.store._read(path) if path.exists() else {}
                    remote = (record.get('item') or {}).get('id')
                    if remote:
                        key = json.dumps([record.get('target'), remote], sort_keys=True)
                        observations.setdefault(key, []).append((item, record.get('triage_status')))
                for group in observations.values():
                    if {'regression_passed', 'regression_failed'} <= {state for _, state in group}:
                        for item, _ in group:
                            if self.identity(item) not in seen:
                                continue
                            item.update(outcome='failed', message='同一原缺陷存在相互冲突的回归结论，请核对')
            context = dict(owner=owner, actor_owner=actor,
                user={'username': (request.state.user or {}).get('username', '')},
                report_scope=getattr(request.state, 'report_scope', None), mcp_scope=None,
                aggregate_context=getattr(request.state, 'aggregate_context', None),
                scheme=request.url.scheme, server=list(request.scope.get('server') or ('localhost', 80)),
                host=request.headers.get('host', 'localhost'), root_path=request.scope.get('root_path', ''))
            job = dict(id=job_id, owner=owner, project_id=pid, run_id=rid, action=action, reason=reason,
                       context=context, digest=digest, status='queued', items=items, created_at=now(), stop_requested=False)
            self.save(job)
            self.wake.set()
            return self.snapshot(job)

    @staticmethod
    def authorize(job, owner, pid, rid):
        if (job['owner'], job['project_id'], job['run_id']) != (owner, pid, rid):
            raise HTTPException(404, '后台任务不存在')

    def list(self, owner, pid, rid):
        with self.lock:
            return [self.snapshot(job) for job in sorted(self.jobs.values(), key=lambda j: j['created_at'], reverse=True)
                    if job['owner'] == owner and ((job['project_id'], job['run_id']) == (pid, rid) or
                        any((item['project_id'], item['run_id']) == (pid, rid) for item in job['items']))]

    def get(self, owner, pid, rid, job_id):
        with self.lock:
            job = self.jobs.get(str(UUID(job_id)))
            if not job:
                raise HTTPException(404, '后台任务不存在')
            self.authorize(job, owner, pid, rid)
            return self.snapshot(job)

    def stop(self, owner, pid, rid, job_id):
        job_id = str(UUID(job_id))
        with self.lock:
            self.get(owner, pid, rid, job_id)
            job = self.jobs[job_id]
            if job['status'] in ACTIVE:
                job['stop_requested'] = True
                self.save(job)
            self.wake.set()
            return self.snapshot(job)

    def request(self, job):
        context = job['context']
        state = {k: context[k] for k in ('owner', 'actor_owner', 'user', 'report_scope', 'mcp_scope')}
        state['batch_job_id'] = job['id']
        state['aggregate_context'] = context.get('aggregate_context')
        return Request({'type': 'http', 'method': 'POST', 'scheme': context['scheme'],
            'server': tuple(context['server']), 'root_path': context['root_path'], 'path': '/',
            'headers': [(b'host', context['host'].encode())], 'query_string': b'',
            'app': self.app, 'router': self.app.router, 'state': state})

    def active_count(self):
        with self.lock:
            return sum(job['status'] in ACTIVE for job in self.jobs.values())

    def start(self):
        if self.thread:
            return
        self.lease = (self.root / 'worker.lock').open('a')
        fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with self.lock:
            for job in self.jobs.values():
                if job['status'] in ACTIVE:
                    for item in job['items']:
                        if item['outcome'] == 'running':
                            # A process exit cannot prove whether the last external write completed.
                            outcome, message = 'unknown', '服务重启前结果未返回，请刷新同步状态核对'
                            try:
                                _, _, path = self.service.source(job['owner'], *self.identity(item))
                                record = self.store._read(path) if path.exists() else None
                                sync = (record or {}).get('remote_sync') or {}
                                if (job['action'] in {'accept', 'reopen'} and sync.get('action') == job['action'] and sync.get('status') == 'success' or
                                        job['action'] == '__submit__' and (record or {}).get('status') == 'submitted' and
                                        not record.get('description_error') and not record.get('screenshot_error')):
                                    outcome, message = 'success', '已从保存的操作结果恢复'
                                if record:
                                    item['record'] = self.service.record_summary(record)
                            except (ValueError, FileNotFoundError):
                                pass
                            item.update(outcome=outcome, message=message, finished_at=now())
                    job['status'] = 'queued'
                    self.save(job)
        self.thread = threading.Thread(target=self.work, name='defect-batches', daemon=True)
        self.thread.start()

    def close(self):
        self.closing.set()
        self.wake.set()
        if self.thread:
            self.thread.join()
        if self.lease:
            self.lease.close()

    def work(self):
        while not self.closing.is_set():
            with self.lock:
                pending = [j for j in self.jobs.values() if j['status'] in ACTIVE]
            if not pending:
                self.wake.wait(1)
                self.wake.clear()
                continue
            # One item per job per pass lets separate batches continue fairly.
            for job in pending:
                if self.closing.is_set():
                    break
                with self.lock:
                    queued = [i for i in job['items'] if i['outcome'] == 'queued']
                    if job['stop_requested']:
                        for item in queued:
                            item.update(outcome='remaining', message='已停止，尚未执行')
                        queued = []
                    if not queued:
                        job.update(status='stopped' if job['stop_requested'] else 'completed', completed_at=now())
                        self.save(job)
                        continue
                    item = queued[0]
                    group = ([i for i in queued if (i['project_id'], i['run_id']) == (item['project_id'], item['run_id'])]
                             if job['action'] == 'titles' else [item])
                    job['status'] = 'running'
                    for member in group:
                        member.update(outcome='running', message='正在处理，等待操作结果', started_at=now())
                    self.save(job)
                try:
                    result = self.execute(self.request(job), job, copy.deepcopy(item))
                except (ValueError, FileNotFoundError, HTTPException) as exc:
                    result = dict(outcome='failed', message=str(getattr(exc, 'detail', exc)))
                except Exception:
                    result = dict(outcome='unknown', message='操作响应中断，请核对状态；不会自动重复写入')
                with self.lock:
                    titles = result.pop('titles', {})
                    for member in group:
                        member.update(result, finished_at=now())
                        if member['draft_id'] in titles:
                            member['title'] = titles[member['draft_id']]
                    self.save(job)
