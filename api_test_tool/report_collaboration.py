"""Resolve published reports without granting access to a creator's workspace."""
import re
import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException


ROUTE = re.compile(r'^/api/projects/([^/]+)/(reports|load-reports)/([^/]+)/(.+)$')
OPERATIONS = {'case-corrections', 'report-corrections', 'title-corrections', 'ui-actions', 'rule-questions',
              'retest-inputs', 'retests', 'pingcode', 'collaboration'}


def scope(store, path):
    match = ROUTE.fullmatch(path)
    if not match:
        return None
    pid, kind, rid, operation = match.groups()
    owner = store.find_project_owner(pid)
    project = store.get_project(owner, pid)
    if rid == 'total':
        if kind != 'reports' or project.get('test_kind') != 'ui':
            raise HTTPException(404, '报告不存在')
        if project.get('business_project'):
            if not re.fullmatch(r'pingcode/batches/jobs/[^/]+/stop', operation):
                store.project_reports.get(owner, pid)
        else:
            from .ui_total_reports import build
            build(store, owner, project)
    else:
        store._project_id(rid)
        entries = project.get('load_runs' if kind == 'load-reports' else 'runs', [])
        entries = entries + (project.get('analysis_reports', []) if kind == 'reports' else [])
        historical = (store.has_saved_report(owner, pid, rid, kind='runs')
                      or kind == 'reports' and store.has_saved_report(owner, pid, rid))
        if rid not in {entry['id'] for entry in entries} and not historical:
            raise HTTPException(404, '报告不存在')
    if operation.split('/')[0] not in OPERATIONS and '/' in operation:
        raise HTTPException(404, '报告操作不存在')
    return {'owner': owner, 'project_id': pid, 'report_id': rid, 'operation': operation}


def state(store, owner, pid):
    path = store.project_dir(owner, pid) / 'report-collaboration.json'
    return store._read(path) if path.exists() else {'revision': 0, 'history': []}


def record(store, context, actor):
    with store._lock:
        data = state(store, context['owner'], context['project_id'])
        data['revision'] += 1
        data['history'].append({'revision': data['revision'], 'actor': actor,
            'at': datetime.now(timezone.utc).isoformat(), 'report_id': context['report_id'],
            'operation': context['operation']})
        store._write(store.project_dir(context['owner'], context['project_id']) /
                     'report-collaboration.json', data)


def view(store, owner, project):
    if project.get('business_project'):
        group = store.project_reports.get(owner, project['id'])
        cached = store.project_reports.cached(owner, group)
        return {'project_id': group['id'], 'revision': cached['aggregate']['revision'], 'history': []}
    from .ui_total_reports import canonical_project
    with store._lock:
        root = canonical_project(store, owner, project)['id']
        versions, history = [], []
        for candidate in store.list_projects(owner):
            if candidate.get('test_kind') != 'ui' or canonical_project(store, owner, candidate)['id'] != root:
                continue
            data = state(store, owner, candidate['id'])
            versions.append((candidate['id'], data['revision']))
            history.extend(data['history'])
        return {'project_id': root, 'revision': hashlib.sha256(json.dumps(sorted(versions)).encode()).hexdigest(),
                'history': sorted(history, key=lambda event: event['at'])[-20:]}
