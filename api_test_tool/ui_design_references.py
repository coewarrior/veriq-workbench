"""Read-only discovery of relevant historical designs, never execution baselines."""
import copy
from urllib.parse import urlsplit

from . import ui_records
from .ui_case_scope import active_cases

GUIDANCE = ('历史设计仅供查漏，不是本轮范围或执行结果。先按当前原目标、附件及模块范围选择来源，'
            '用 get_ui_design_reference 分页读完相关设计；逐项复用、修订或说明不适用，'
            '在本轮 coverage/review_notes 保留来源 project_id/source_case_id 与新 case_id 对应。'
            '不同输入、状态、边界和独立判断不合并；缺样本不删设计；旧数量不是配额，旧结果不计入本轮。')
CASE_FIELDS = ('scenario', 'module', 'precondition', 'test_data', 'steps', 'expected',
               'priority', 'rule_basis', 'method', 'account_scope')
POINT_FIELDS = ('id', 'title', 'kind', 'expected', 'basis', 'depends_on')


def _origin(url):
    u = urlsplit(url or '')
    return (u.scheme.lower(), u.netloc.lower()) if u.scheme in {'http', 'https'} and u.netloc else None


def _documents(project):
    attachments = project.get('ui_requirement_attachments') or []
    hashes = [a.get('sha256') for a in attachments]
    return tuple(sorted(hashes)) if hashes and all(isinstance(h, str) and len(h) == 64 for h in hashes) else None


def catalog(controller, owner, project):
    """Metadata only; no historical case reads on dispatch or progress polling."""
    store = controller.store
    try:
        project = store.get_project(owner, project['id'])
        root_id = project.get('managed_parent_project_id') or project['id']
        root = store.get_project(owner, root_id)
    except FileNotFoundError:
        return []
    fingerprint, target = _documents(root), _origin(root.get('ui_target_url'))
    if not fingerprint or not target:
        return []
    snapshot = controller.snapshot(owner)
    tasks = snapshot['tasks']
    current = max((t for t in tasks if t['project_id'] == root_id),
                  key=lambda t: t['created'], default=None)
    if not current:
        return []
    projects = {p['id']: p for p in store.list_projects(owner)}
    prior = {t['id']: t for t in tasks if t['project_id'] != root_id
             and (t.get('account_project_id') or t['project_id']) == (current.get('account_project_id') or root_id)
             and t['created'] < current['created'] and t['project_id'] in projects
             and _origin(projects[t['project_id']].get('ui_target_url')) == target
             and _documents(projects[t['project_id']]) == fingerprint}
    nodes = {n.get('record_project_id'): n for n in snapshot['nodes'] if n.get('record_project_id')}
    result = []
    for source in projects.values():
        if (not source.get('ui_execution_id') or source['id'] == project['id']
                or _documents(source) != fingerprint or _origin(source.get('ui_target_url')) != target):
            continue
        task = prior.get(source.get('managed_task_id'))
        if task is None and not source.get('managed_node_id'):
            task = max((t for t in prior.values() if t['project_id'] == source['id']),
                       key=lambda t: t['created'], default=None)
        if task is None:
            continue
        node = nodes.get(source['id'], {})
        result.append({'project_id': source['id'], 'execution_id': source['ui_execution_id'],
            'task_id': task['id'], 'title': source['title'], 'scope': node.get('scope', ''),
            'source_session_id': task['project_id'],
            'created_at': source['created_at'],
            'case_count': sum(source.get('ui_progress_record', {}).get('counts', {}).values()),
            'read': {'tool': 'get_ui_design_reference', 'arguments': {
                'project_id': project['id'], 'source_project_id': source['id']}}})
    return sorted(result, key=lambda item: item['created_at'], reverse=True)


def read(controller, owner, project, source_project_id, offset=0, limit=100):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('offset 需为非负整数，limit 需为 1–200；读取分页不限制设计总数')
    source = next((s for s in catalog(controller, owner, project) if s['project_id'] == source_project_id), None)
    if source is None:
        raise ValueError('来源不是当前账号项目、目标与原附件匹配的历史设计')
    record = ui_records.load(controller.store, owner, source_project_id, source['execution_id'])
    cases = active_cases(record['cases'])
    projected = []
    for case in cases[offset:offset + limit]:
        projected.append({'source_case_id': case['case_id'],
            **{k: copy.deepcopy(case[k]) for k in CASE_FIELDS if k in case},
            'checkpoints': [{k: copy.deepcopy(p[k]) for k in POINT_FIELDS if k in p}
                            for p in case.get('checkpoints', [])]})
    source = {**source, 'source_goal': controller.store.get_project(owner, source['source_session_id']).get('task', {}).get('goal', '')}
    return {'source': source, 'source_revision': record['revision'], 'design_only': True,
            'cases': projected, 'total': len(cases),
            'next_offset': offset + limit if offset + limit < len(cases) else None,
            'instruction': GUIDANCE}
