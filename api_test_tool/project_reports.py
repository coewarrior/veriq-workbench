"""Background project projections. Source reports remain the only writable authority.

Membership is durable work intent; file fingerprints are the incremental cursor.
A single independent worker resumes it after restart, never on a test request.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import logging
import re
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from . import ui_report_corrections
from .orchestration_storage import read_sections
from .ui_records import LABELS

LOG = logging.getLogger(__name__)
SCHEMA = 1
STATUSES = {'PASS': 'passed', 'FAIL': 'failed', 'BROKEN': 'broken', 'BLOCKED': 'blocked',
            'QUARANTINED': 'quarantined', 'UNSUPPORTED': 'unsupported'}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc).timestamp() if parsed.tzinfo is None else parsed.timestamp()
    except (ValueError, TypeError, AttributeError):
        return 0


def stamp(path):
    if path.is_symlink():
        raise ValueError('汇总来源路径无效')
    try:
        stat = path.stat()
        return [stat.st_mtime_ns, stat.st_size, stat.st_ino]
    except FileNotFoundError:
        return None


def lineage(project, projects):
    seen = set()
    while project.get('regression_source', {}).get('project_id'):
        if project['id'] in seen:
            raise ValueError('回归来源存在循环')
        seen.add(project['id'])
        parent = project['regression_source']['project_id']
        if parent not in projects:
            break
        project = projects[parent]
    return project['id']


class ProjectReports:
    def __init__(self, store, controller):
        self.store = store
        self.controller = controller
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.worker_lock = threading.Lock()
        self.leader = None

    def start(self):
        if self.thread:
            return
        self.leader = (self.store.root / 'project-reports.lock').open('a')
        try:
            fcntl.flock(self.leader, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.leader.close()
            self.leader = None
            return
        self.thread = threading.Thread(target=self._loop, name='project-report-projection', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=5)
        if self.leader and (not self.thread or not self.thread.is_alive()):
            self.leader.close()
            self.leader = None

    def _loop(self):
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:
                # Never log report bodies, filenames or credentials.
                LOG.warning('Project report scan failed; retrying')
            self.wake.wait(3)
            self.wake.clear()

    def catalog(self, owner):
        # Read only the project registry, without acquiring the execution transaction
        # or loading accounts, credentials, active tasks or browser state.
        with self.controller.connect() as db:
            db.execute('BEGIN')
            state = read_sections(db, ('account_projects', 'session_account_projects'))
        return ({key: value for key, value in state['account_projects'].items()
                 if value['owner'] == owner}, state['session_account_projects'])

    def group(self, owner, account_id):
        catalog, bindings = self.catalog(owner)
        if account_id not in catalog:
            raise FileNotFoundError('业务项目不存在')
        product = catalog[account_id]
        sessions = {p['id']: p for p in self.store.list_projects(owner)}
        members = [{'project_id': pid, 'version': sessions.get(pid, {}).get('test_version', ''),
                    'environment': sessions.get(pid, {}).get('test_environment', '')}
                   for pid, aid in sorted(bindings.items()) if aid == account_id]
        # A holder supplies the existing report URL/permission model, not a second
        # business project. It is never exposed as a test session or execution target.
        with self.store._lock:
            holder = next((p for p in self.store.list_projects(owner, include_business=True)
                           if p.get('aggregate_account_project_id') == account_id), None)
            if not holder:
                holder = self.store.create_project(owner, product['name'], 'project.md', '# 项目总报告\n',
                                                   aggregate=True)
            signature = digest([product['name'], product.get('login_url'), members])
            if holder.get('membership_revision') != signature:
                holder = self.store.update_project(owner, holder['id'], {
                    'business_project': True, 'test_kind': 'ui', 'title': product['name'],
                    'aggregate_account_project_id': account_id, 'members': members,
                    'membership_revision': signature})
        return holder

    def session_link(self, owner, project_id):
        catalog, bindings = self.catalog(owner)
        seen = set()
        while project_id and project_id not in seen:
            seen.add(project_id)
            account_id = bindings.get(project_id)
            if account_id in catalog:
                group = self.group(owner, account_id)
                return {'title': group['title'], 'report_url': f"/api/projects/{group['id']}/reports/total/index.html"}
            project = self.store.get_project(owner, project_id)
            project_id = (project.get('regression_source', {}).get('project_id')
                          or project.get('execution_round', {}).get('parent_project_id')
                          or project.get('managed_parent_project_id'))
        return None

    def groups(self, owner):
        catalog, _ = self.catalog(owner)
        return [self.group(owner, key) for key in catalog]

    def get(self, owner, pid):
        value = self.store.get_project(owner, pid)
        if not value.get('business_project'):
            raise FileNotFoundError('业务项目不存在')
        return self.group(owner, value['aggregate_account_project_id'])

    def root(self, owner, pid):
        root = self.store.project_dir(owner, pid) / 'project-total'
        self.store._mkdir(root)
        return root

    def inventory(self, owner, group):
        """Only stat source files; unchanged report JSON is not reparsed."""
        projects = {p['id']: p for p in self.store.list_projects(owner)}
        members = {m['project_id']: m for m in group['members']}
        related = {pid: pid for pid in members if pid in projects}
        for _ in range(len(projects)):
            added = False
            for pid, project in projects.items():
                parent = (project.get('regression_source', {}).get('project_id')
                          or project.get('managed_parent_project_id'))
                if pid not in related and parent in related:
                    related[pid] = related[parent]
                    added = True
            if not added:
                break
        sources, members_state = {}, []
        for mid, member in members.items():
            if mid not in projects:
                members_state.append({**member, 'title': '来源会话不可用', 'status': 'missing'})
        for pid, mid in sorted(related.items()):
            project = projects[pid]
            root = self.store.project_dir(owner, pid)
            member = {**members[mid], 'session_id': pid, 'title': project['title'],
                      'status': project.get('status', ''), 'test_kind': project.get('test_kind', 'api'),
                      'lineage': lineage(project, projects)}
            members_state.append(member)
            for directory, filename in (('analyses', 'report.json'), ('runs', 'result.json')):
                parent = root / directory
                if parent.is_symlink():
                    raise ValueError('报告目录无效')
                for path in sorted(parent.glob('*/' + filename)):
                    rid = path.parent.name
                    self.store._project_id(rid)
                    key = pid + '/' + directory + '/' + rid
                    files = [path, path.with_name('case-corrections.json')]
                    if directory == 'analyses':
                        files.append(path.with_name('fixture-supplements.json'))
                    if directory == 'runs':
                        files.append(path.with_name('bundle.json'))
                    sources[key] = {'member': member, 'project_id': pid, 'report_id': rid,
                        'kind': directory, 'load_only': rid in {r['id'] for r in project.get('load_runs', [])}, 'files': {str(p.relative_to(root)): stamp(p) for p in files}}
        return {'schema': SCHEMA, 'membership_revision': group['membership_revision'],
                'title': group['title'], 'members': members_state, 'sources': sources}

    def _read_source(self, owner, source):
        pid, rid, kind = source['project_id'], source['report_id'], source['kind']
        root = self.store.project_dir(owner, pid) / kind / rid
        saved = self.store._read(root / ('report.json' if kind == 'analyses' else 'result.json'))
        if kind == 'analyses':
            saved = ui_report_corrections.apply(saved, ui_report_corrections.load(self.store, owner, pid, rid))
            saved = {key: value for key, value in saved.items() if key in {
                'id', 'title', 'created_at', 'updated_at', 'target_url', 'test_kind', 'test_version',
                'imported_results', 'findings', 'regression_links', 'summary', 'case_corrections',
                'ui_snapshot', 'consolidated_into', 'report_type'}}
            if 'ui_snapshot' in saved:
                saved['ui_snapshot'] = {key: value for key, value in saved['ui_snapshot'].items() if key in {'id', 'assets'}}
            return saved
        # Load testing remains separate from functional case statistics.
        if source.get('load_only') or not isinstance(saved.get('cases'), list):
            return {'id': rid, 'title': '压测报告', 'created_at': saved.get('started_at', ''),
                    'load_only': True, 'findings': [], 'runs': []}
        bundle = self.store._read(root / 'bundle.json')
        designs = {c['id']: c for c in bundle.get('cases', [])}
        cases, findings = [], []
        from .defect_drafts import case_defect_draft
        for index, value in enumerate(saved['cases']):
            design = designs.get(value['id'], {})
            definition = design.get('design', {})
            case = {'case_id': value['id'], 'status': STATUSES.get(value.get('status'), 'other'),
                'scenario': design.get('title') or value.get('title') or value['id'],
                'executor': 'API', 'module': design.get('operation_id', ''),
                'environment': saved.get('environment', {}).get('name', ''),
                'precondition': str(definition.get('precondition', '')),
                'steps': str(definition.get('steps', '')), 'expected': str(definition.get('expected', '')),
                'evidence': str(value.get('reason') or value.get('error') or value.get('status', '')),
                'test_data': '', 'source_row': index + 2}
            cases.append(case)
            draft = case_defect_draft(saved, bundle, value)
            if draft:
                findings.append({'case_id': value['id'], 'title': case['scenario'],
                    'detail': draft[1], 'evidence': case['evidence'], 'severity': '', 'recommendation': '',
                    'draft_source': {'project_id': pid, 'report_id': rid, 'draft_id': f'defect-{index}'}})
        return {'id': rid, 'title': '接口执行报告', 'created_at': saved.get('finished_at') or saved.get('started_at', ''),
            'target_url': saved.get('environment', {}).get('base_url', ''), 'test_kind': 'api',
            'test_version': saved.get('test_version', ''),
            'imported_results': {'cases': cases}, 'findings': findings, 'runs': []}

    def tick(self):
        if not self.worker_lock.acquire(blocking=False):
            return
        try:
            with self.controller.connect() as db:
                db.execute('BEGIN')
                state = read_sections(db, ('account_projects',))
            owners = {p['owner'] for p in state['account_projects'].values()}
            for owner in sorted(owners):
                if self.stop.is_set():
                    return
                try:
                    groups = self.groups(owner)
                except (FileNotFoundError, PermissionError, ValueError):
                    continue
                for group in groups:
                    try:
                        self.refresh(owner, group)
                    except Exception:
                        root = self.root(owner, group['id'])
                        self.store._write(root / 'status.json', {'status': 'failed', 'at': now(),
                            'message': '汇总更新失败，将自动重试；可继续查看原会话报告。'})
        finally:
            self.worker_lock.release()

    def refresh(self, owner, group):
        root = self.root(owner, group['id'])
        inventory = self.inventory(owner, group)
        revision = digest(inventory)
        prior = self.store._read(root / 'current.json') if (root / 'current.json').exists() else {}
        if prior.get('revision') == revision:
            status_path = root / 'status.json'
            if status_path.exists() and self.store._read(status_path).get('status') != 'ready':
                self.store._write(status_path, {'status': 'ready', 'at': now()})
            return
        self.store._write(root / 'status.json', {'status': 'updating', 'at': now()})
        chunks = root / 'sources'
        self.store._mkdir(chunks)
        reports = []
        for key, source in inventory['sources'].items():
            if self.stop.is_set():
                return
            location = chunks / (digest(key) + '.json')
            cached = self.store._read(location) if location.exists() else {}
            signature = digest([SCHEMA, source['files']])
            if cached.get('signature') != signature:
                cached = {'signature': signature, 'report': self._read_source(owner, source)}
                self.store._write(location, cached)
            reports.append((source, cached['report']))
        report = assemble(group, inventory, reports, revision)
        same_membership = prior.get('inventory', {}).get('membership_revision') == inventory['membership_revision']
        removed = ((set(prior.get('inventory', {}).get('sources', {})) | set(prior.get('missing_sources', []))) - set(inventory['sources'])) if same_membership else set()
        if removed:
            report['aggregate']['notices'].append(f'{len(removed)} 份原来源已不可用，汇总不完整，不能视为通过。')
        # A mutation during IO must never publish a mixed revision. Retry later.
        fresh = self.get(owner, group['id'])
        if digest(self.inventory(owner, fresh)) != revision:
            return
        self.store._write(root / 'current.json', {'revision': revision, 'inventory': inventory, 'report': report, 'missing_sources': sorted(removed)})
        self.store._write(root / 'status.json', {'status': 'ready', 'at': now()})
        active = {digest(key) + '.json' for key in inventory['sources']}
        for path in chunks.glob('*.json'):
            if path.name not in active:
                path.unlink()

    def cached(self, owner, group):
        root = self.root(owner, group['id'])
        path = root / 'current.json'
        state = self.store._read(root / 'status.json') if (root / 'status.json').exists() else {'status': 'queued'}
        if path.exists():
            value = self.store._read(path)
            report = value['report']
            # Immediately invalidate removed sources, including before the worker's next poll.
            for source in value['inventory']['sources'].values():
                try:
                    self.store.get_project(owner, source['project_id'])
                except FileNotFoundError:
                    report = empty(group)
                    report['aggregate']['notices'] = ['来源会话不可用，正在重新汇总；旧结果不作为当前结论。']
                    state = {'status': 'updating'}
                    break
            # Cheap membership check prevents removed sources leaking from old cache.
            if value['inventory']['membership_revision'] != group['membership_revision']:
                report = empty(group)
                state = {'status': 'updating'}
        else:
            report = empty(group)
        report['aggregate']['status'] = state['status']
        report['aggregate']['message'] = state.get('message', '')
        report['aggregate']['checked_at'] = state.get('at', '')
        from .ui_asset_withdrawals import report_view
        return report_view(self.store, owner, report)

    def source_token(self, owner, pid, rid):
        root = self.store.project_dir(owner, pid)
        return digest({str(p.relative_to(root)): stamp(p) for p in (
            root / 'analyses' / rid / 'report.json', root / 'analyses' / rid / 'case-corrections.json',
            root / 'runs' / rid / 'result.json', root / 'runs' / rid / 'bundle.json')})

    def family_token(self, owner, context, pid, rid):
        group = self.get(owner, context['project_id'])
        inventory = self.inventory(owner, group)
        source = next((v for v in inventory['sources'].values()
                       if (v['project_id'], v['report_id']) == (pid, rid)), None)
        if not source:
            raise HTTPException(409, '来源报告已移出此项目，请重新审核')
        family = source['member']['lineage']
        return digest({k: v for k, v in inventory['sources'].items() if v['member']['lineage'] == family})

    def validate_item(self, owner, context, item):
        if not context:
            return
        group = self.get(owner, context['project_id'])
        if group['membership_revision'] != context['membership_revision']:
            raise HTTPException(409, '项目归属已变化，请重新审核')
        if (self.source_token(owner, item['project_id'], item['run_id']) != item.get('source_token')
                or item.get('family_token') and self.family_token(owner, context, item['project_id'], item['run_id']) != item['family_token']):
            raise HTTPException(409, '来源报告已更新，请重新审核后操作')

    def validate(self, owner, pid, revision):
        group = self.get(owner, pid)
        path = self.root(owner, pid) / 'current.json'
        if not path.exists():
            raise HTTPException(409, '项目总报告正在更新，请稍后刷新')
        value = self.store._read(path)
        if not revision or value['revision'] != revision or digest(self.inventory(owner, group)) != revision:
            self.wake.set()
            raise HTTPException(409, '来源结果或项目范围已变化，请刷新总报告后重新审核')
        return value


def empty(group):
    return {'id': 'total', 'project_id': group['id'], 'test_kind': 'ui', 'report_type': 'total',
        'title': group['title'] + ' · 项目总报告', 'created_at': now(), 'summary': '后台正在汇总，测试任务不受影响。',
        'goal': '', 'runs': [], 'findings': [], 'sections': [], 'stage_reports': [],
        'imported_results': {'filename': '项目所属会话', 'sheet_name': '测试用例', 'cases': [], 'counts': {'total': 0}},
        'ui_snapshot': {'id': '', 'cases': [], 'assets': []},
        'aggregate': {'id': group['id'], 'revision': '', 'status': 'queued', 'members': [], 'notices': []}}


def assemble(group, inventory, reports, revision):
    result = empty(group)
    selected, stages, extras, assets_by_key, findings_by_key = {}, [], [], {}, {}
    seen_reports = set()
    defect_roots = {}
    defect_assets = []
    observed = Counter()
    for source, report in sorted(reports, key=lambda pair: (timestamp(pair[1].get('created_at')), pair[0]['report_id'])):
        if report.get('consolidated_into') or report.get('report_type') == 'total':
            continue
        pid, rid, member = source['project_id'], source['report_id'], source['member']
        seen_reports.add(pid)
        base = f'/api/projects/{pid}/reports/{rid}'
        stage = {'project_id': pid, 'id': rid, 'title': member['title'] + ' · ' + report['title'],
            'created_at': report.get('created_at', ''), 'report_url': base + '/index.html',
            'correction_revision': report.get('case_corrections', {}).get('revision', 0),
            'session_title': member['title'], 'kind': source['kind']}
        if report.get('load_only'):
            stage['report_url'] = f'/api/projects/{pid}/load-reports/{rid}/index.html'
        stages.append(stage)
        cases = report.get('imported_results', {}).get('cases', [])
        case_keys = {}
        for case in cases:
            cid = case['case_id']
            scope = {'version': report.get('test_version') or '未标注版本',
                'environment': case.get('environment') or member['environment'] or '未标注环境',
                'target': report.get('target_url', ''), 'client': case.get('client', ''),
                'role': case.get('role', ''), 'kind': report.get('test_kind') or member['test_kind']}
            identity = [member['lineage'], cid, scope]
            uid = digest(identity)
            case_keys[cid] = uid
            origin = {**stage, 'case_id': cid, 'scope': scope,
                      'editable': source['kind'] == 'analyses' and bool(report.get('ui_snapshot'))}
            # Server case updated_at is authoritative for parallel out-of-order publication.
            changed = timestamp(case.get('updated_at') or report.get('created_at'))
            previous = selected.get(uid)
            if previous and previous[0] > changed:
                continue
            selected[uid] = (changed, {**copy.deepcopy(case), 'case_id': uid, 'display_case_id': cid,
                'source_report': origin, 'result': LABELS.get(case.get('status'), case.get('status', 'other')), 'scope_label': ' · '.join([scope['version'], scope['environment'], scope['kind']])})
            if previous and previous[0] == changed and previous[1]['source_report']['project_id'] != pid and previous[1]['status'] != case.get('status'):
                current = selected[uid][1]
                current.update(status='other', result='结果冲突', evidence='并行轮次存在相互冲突的结果，请核对来源后重新发布。',
                               conflicting_sources=[previous[1]['source_report'], origin])
                current['source_report']['editable'] = False
            assets_by_key[uid] = [{**copy.deepcopy(a), 'case_id': uid,
                'source_project_id': pid, 'source_execution_id': report['ui_snapshot']['id'],
                'url': f'{base}/asset-{a["id"]}'} for a in report.get('ui_snapshot', {}).get('assets', []) if a['case_id'] == cid]
            findings_by_key.setdefault(uid, {})
            for index, finding in enumerate(report.get('findings', [])):
                if finding.get('case_id') != cid:
                    continue
                ds = finding.get('draft_source') or {'project_id': pid, 'report_id': rid, 'draft_id': f'finding-{index}'}
                own_key = digest(ds)
                link = next((v for v in report.get('regression_links', []) if v.get('draft_id') == f'finding-{index}'), None)
                old_key = digest({'project_id': link['source_project_id'], 'report_id': link['source_report_id'],
                                  'draft_id': link['source_draft_id']}) if link else own_key
                root_key = defect_roots.get(old_key, old_key)
                defect_roots[own_key] = root_key
                evidence_key = digest([pid, rid, cid, 'evidence'])
                findings_by_key[uid][root_key] = {**copy.deepcopy(finding), 'case_id': uid,
                    'evidence_case_id': evidence_key, 'draft_source': ds,
                    'regression_outcome': link.get('outcome', '') if link else ''}
                defect_assets.extend({**a, 'case_id': evidence_key} for a in assets_by_key[uid] if a.get('kind') != 'fixture')
            observed[uid] += 1
        # Unstructured analysis/requirements and load reports remain visible, never counted as passing cases.
        if not cases:
            extras.append({'title': stage['title'], 'content': report.get('summary', '无结构化用例结果；请查看来源报告。')})
            for index, finding in enumerate(report.get('findings', [])):
                key = digest([pid, rid, 'finding', index])
                findings_by_key[key] = {key: {**copy.deepcopy(finding), 'case_id': key,
                    'draft_source': {'project_id': pid, 'report_id': rid, 'draft_id': f'finding-{index}'}}}
    cases = [item[1] for item in selected.values()]
    if len(cases) > 100000:
        raise ValueError('项目汇总超过 100000 条，请按版本拆分项目范围')
    notices = []
    if not inventory['members']:
        notices.append('此项目尚无已归属的测试会话，不能形成测试结论。')
    elif not stages:
        notices.append('尚无已发布报告，不能形成测试结论。')
    for member in inventory['members']:
        if member.get('status') == 'missing':
            notices.append('有来源会话已删除或不可用，汇总不完整。')
        elif member.get('session_id') not in seen_reports:
            notices.append(member['title'] + '：尚无已发布报告。')
        elif member.get('status') not in {'reported', 'executed'}:
            notices.append(member['title'] + '：仍有未完成任务，已发布结果不代表本轮完成。')
    if any(c.get('conflicting_sources') for c in cases):
        notices.append('存在并行结果冲突，不能认定通过；请核对各来源轮次。')
    if any(c['source_report']['scope']['version'] == '未标注版本' for c in cases):
        notices.append('部分来源未标注版本，不能据此认定当前版本通过。')
    counts = {**Counter(c.get('status', 'other') for c in cases), 'total': len(cases)}
    scopes = {}
    for case in cases:
        label = case['scope_label']
        bucket = scopes.setdefault(label, Counter())
        bucket[case.get('status', 'other')] += 1
        bucket['total'] += 1
    if any(len(values) > 1 for values in findings_by_key.values()):
        notices.append('同一用例存在多份未明确关联的缺陷记录，请审核是否重复；未按标题自动合并。')
    findings = [f for values in findings_by_key.values() for f in values.values()]
    # Keep every actual defect identity, including multiple defects attached to one case.
    unique = {digest(f['draft_source']): {**{k: '' for k in ('severity', 'detail', 'evidence', 'recommendation')}, **f} for f in findings}
    for c in cases:
        c['source_session'] = c['source_report']['session_title']
        c['source_url'] = c['source_report']['report_url']
    result.update(summary=f'项目汇总 {len(cases)} 条唯一用例；通过 {counts.get("passed", 0)}，失败 {counts.get("failed", 0)}。'
                          + (' 存在未完成或待核对范围。' if notices else ''),
        findings=list(unique.values()), stage_reports=stages[::-1], sections=extras,
        imported_results={'filename': '项目所属会话的原始报告', 'sheet_name': '测试用例', 'cases': cases, 'counts': counts},
        ui_snapshot={'id': '', 'cases': cases, 'assets': [a for values in assets_by_key.values() for a in values] + defect_assets},
        regression_links=[{'draft_id': f'finding-{i}', 'outcome': f['regression_outcome']}
                          for i, f in enumerate(unique.values()) if f.get('regression_outcome')],
        aggregate={'id': group['id'], 'revision': revision, 'status': 'ready', 'generated_at': now(),
            'members': inventory['members'], 'notices': notices, 'scopes': scopes, 'analysis': extras})
    return result
