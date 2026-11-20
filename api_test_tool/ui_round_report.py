"""Current-round projections from recorded nodes, including unfinished modules.

Legacy session/project history remains a separate view. Reading a report never
creates a test record, invokes an executor, or changes the business result.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone

from . import database, ui_records, ui_report_corrections
from .orchestration_storage import read_nodes, read_sections
from .ui_case_results import annotate, active_cases, is_superseded


def task_records(store, owner, snapshot):
    task = snapshot['tasks'][0]
    projects = {p['id']: p for p in store.list_projects(owner)}
    by_node = {p.get('managed_node_id'): p for p in projects.values() if p.get('managed_node_id')}
    modules = []
    node_ids = {n['id'] for n in snapshot['nodes']}
    for node in snapshot['nodes']:
        if node.get('record_successor_node_id') in node_ids:
            continue
        project = projects.get(node.get('record_project_id')) or by_node.get(node['id'])
        if not project and task.get('session_workflow') and len(task['node_ids']) == 1:
            project = projects.get(task['project_id'])
        eid = node.get('record_execution_id') or (project or {}).get('ui_execution_id')
        record = ui_records.load(store, owner, project['id'], eid) if project and eid else {'cases': [], 'assets': []}
        # A split parent keeps already recorded facts, but is not an executor.
        if node.get('child_ids') and not record.get('cases'):
            continue
        record = deepcopy(record)
        record['cases'] = [annotate(c, record, node) for c in record.get('cases', [])]
        modules.append({'node_id': node['id'], 'parent_id': node.get('parent_id', ''),
            'title': node['title'], 'scope': node.get('scope', ''), 'state': node['state'],
            'reason': ('执行已结束，账号已交还；报告未发布' if node.get('native_report_pending') else node.get('reason', '')),
            'report_pending': bool(node.get('native_report_pending')), 'fact_only': bool(node.get('child_ids')),
            'project_id': project['id'] if project else '', 'execution_id': eid or '',
            'record': record, 'attempts': node.get('outcome_history', []),
            'case_history': node.get('case_history', {}),
            'report_url': '/api/projects/%s/reports/%s/index.html' % (project['id'], record['report_id'])
                          if project and record.get('report_id') else None})
    return modules


def current_task(store, owner, project):
    with database.connect(readonly=True) as db:
        db.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        state = read_sections(db, ('tasks',), include_baseline=False)
        tasks = [t for t in state.get('tasks', {}).values() if t.get('owner') == owner and
                 (t.get('id') == project.get('managed_task_id') or t.get('project_id') == project['id'])]
        if not tasks:
            return None
        task = max(tasks, key=lambda t: t.get('created', 0))
        nodes = read_nodes(db, task_ids={task['id']}, include_history=True)
    return {'tasks': [task], 'nodes': [n for n in nodes.values()
        if n.get('task_id') == task['id'] and n.get('owner') == owner]}


def build(store, owner, project, snapshot=None):
    snapshot = snapshot or current_task(store, owner, project)
    if snapshot:
        task = snapshot['tasks'][0]
        root = store.get_project(owner, task['project_id'])
        modules = task_records(store, owner, snapshot)
    elif project.get('execution_round'):
        root, task = project, None
        eid = project.get('ui_execution_id')
        record = ui_records.load(store, owner, project['id'], eid) if eid else {'cases': [], 'assets': []}
        modules = [{'node_id': '', 'title': project['title'], 'state': 'completed' if project.get('ui_final_report') else 'unverified',
            'reason': '' if project.get('ui_final_report') else '尚未登记执行者终态', 'project_id': project['id'], 'execution_id': eid or '',
            'record': record, 'fact_only': False}]
    else:
        return None
    cases, assets, stages, findings, links = {}, [], {}, [], []
    latest = {}
    selected_records = {}
    for module in modules:
        record = module['record']; pid = module['project_id']; eid = module['execution_id']
        from .ui_asset_withdrawals import record_view
        record = record_view(store, owner, record)
        rid = record.get('report_id')
        saved = None
        if rid:
            saved = store._read(store.project_dir(owner, pid) / 'analyses' / rid / 'report.json')
            saved = ui_report_corrections.apply(saved, ui_report_corrections.load(store, owner, pid, rid), store=store, owner=owner)
            latest = saved if not latest or saved.get('updated_at', saved.get('created_at', '')) >= latest.get('updated_at', latest.get('created_at', '')) else latest
            base = '/api/projects/%s/reports/%s' % (pid, rid)
            source = {'id': rid, 'project_id': pid, 'title': saved['title'],
                      'created_at': saved['created_at'], 'report_url': base + '/index.html'}
            stages[(pid, rid)] = source
            # Corrections apply only to the same saved execution revision.
            corrected = {c['case_id']: c for c in saved.get('imported_results', {}).get('cases', [])}
            if saved.get('ui_snapshot', {}).get('revision') == record.get('revision'):
                record = {**record, 'cases': [{**c, **corrected.get(c['case_id'], {})} for c in record['cases']]}
            for index, finding in enumerate(saved.get('findings', [])):
                findings.append({**deepcopy(finding), 'draft_source': {'project_id': pid, 'report_id': rid, 'draft_id': 'finding-%s' % index}})
            for link in saved.get('regression_links', []):
                index = next((i for i, f in enumerate(findings) if f.get('case_id') == link.get('case_id') and f.get('draft_source', {}).get('project_id') == pid), None)
                if index is not None:
                    links.append({**deepcopy(link), 'draft_id': 'finding-%s' % index})
        else:
            base = '/api/ui-tests/%s/executions/%s' % (pid, eid)
            source = {'id': '', 'project_id': pid, 'title': module['title'],
                      'created_at': record.get('created_at', root.get('created_at', '')),
                      'report_url': base + '/cases.html' if eid else '/ui-testing?project=' + root['id'],
                      'publication_pending': True}
        for case in record.get('cases', []):
            # Registered IDs retain their identity through a split/continuation.
            # Do not add the same parent observation twice to the denominator.
            previous = cases.get(case['case_id'])
            if previous and previous.get('updated_at', '') > case.get('updated_at', ''):
                continue
            selected_records[case['case_id']] = (pid, {**record, 'cases': [case]})
            cases[case['case_id']] = {**deepcopy(case), 'result': ui_records.LABELS.get(case.get('status'), case.get('status', '')),
                'evidence': case.get('evidence') or case.get('actual', ''),
                'criterion': case.get('criterion') or case.get('method', ''),
                'source_report': source, 'source_node_id': module['node_id']}
        for asset in record.get('assets', []):
            # A saved report can lag the current record. Newly attached evidence
            # already exists in the execution even before its final publication.
            asset_base = '/api/ui-tests/%s/executions/%s' % (pid, eid)
            assets.append({**deepcopy(asset), 'source_project_id': pid, 'source_execution_id': eid,
                           'url': asset_base + '/asset-' + asset['id']})
    superseded = [c for c in cases.values() if is_superseded(c)]
    values = active_cases(cases.values())
    counts = {**Counter(c.get('status', 'not_run') for c in values), 'total': len(values)}
    blocking_summary = ui_records.ui_dependencies.merge_blocking_summaries(selected_records.values())
    leaf_modules = [m for m in modules if not m['fact_only']]
    unfinished = [m for m in leaf_modules if m.get('report_pending') or m['state'] not in {'completed', 'blocked', 'stopped', 'retained', 'isolated'}]
    module_text = '\n'.join('%s：%s%s' % (m['title'], m['state'], '；' + m['reason'] if m.get('reason') else '') for m in leaf_modules)
    title = root['title'] + ' · 本轮总报告'
    summary = '本轮 %s 个执行模块，%s 个尚未结束；已登记 %s 条用例。未登记用例的模块仍保留，不沿用历史通过。' % (len(leaf_modules), len(unfinished), len(values))
    metadata = deepcopy({k: v for k, v in latest.items() if k not in {'ui_snapshot', 'imported_results', 'findings', 'regression_links', 'experiment'}})
    complete = sum(c.get('coverage_complete', c.get('status') in {'passed', 'failed'} and all(p.get('status') in {'passed', 'failed'} for p in c.get('checkpoints', []))) for c in values)
    return {**metadata, 'id': 'total', 'project_id': root['id'], 'title': title,
        'report_type': 'total', 'test_kind': 'ui', 'runs': [], 'requests_sent': 0,
        'revision': task.get('revision', 1) if task else 1,
        'document': latest.get('document', {'filename': root.get('filename', ''), 'sha256': ''}),
        'created_at': latest.get('created_at') or root.get('created_at') or datetime.now(timezone.utc).isoformat(),
        'report_url': '/api/projects/%s/reports/total/index.html' % root['id'],
        'goal': task.get('goal', '') if task else root.get('task', {}).get('goal', ''),
        'summary': summary, 'sections': [{'title': '本轮全部模块', 'content': module_text}],
        'stage_reports': list(stages.values()), 'modules': [{k: v for k, v in m.items() if k != 'record'} for m in modules],
        'task_id': task['id'] if task else '', 'round_project_id': root['id'],
        'findings': findings, 'regression_links': links,
        'imported_results': {'filename': '本轮已保存用例', 'sheet_name': '测试用例', 'counts': counts, 'quality': {}, 'cases': values, 'superseded_cases': superseded, 'blocking_summary': blocking_summary},
        'ui_snapshot': {'id': '', 'cases': values + superseded, 'assets': assets, 'coverage': [],
            'coverage_complete': complete, 'scope_frozen': bool(task and task.get('_baseline_present', task.get('baseline'))),
            'coverage_basis': '已登记用例的验证完整度；动态探索范围未冻结时不代表全部业务覆盖率'}}
