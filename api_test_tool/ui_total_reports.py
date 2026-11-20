"""A live session report derived from immutable, corrected stage reports."""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from . import ui_report_corrections, ui_dependencies
from .ui_case_scope import active_cases, is_superseded
from .xlsx_results import result_findings


def entry(project):
    return {'id': 'total', 'title': project['title'] + ' · 总报告',
            'report_type': 'total',
            'report_url': f"/api/projects/{project['id']}/reports/total/index.html"}


def canonical_project(store, owner, project):
    seen = set()
    while project.get('regression_source', {}).get('project_id') and project['id'] not in seen:
        seen.add(project['id'])
        project = store.get_project(owner, project['regression_source']['project_id'])
    return project


def build(store, owner, project):
    if project.get('business_project'):
        group = store.project_reports.get(owner, project['id'])
        return store.project_reports.cached(owner, group)
    from .ui_round_report import build as build_current_round
    current = build_current_round(store, owner, project)
    if current is not None:
        return current
    project = canonical_project(store, owner, project)
    if project.get('test_kind') != 'ui':
        raise ValueError('总报告仅用于 UI 测试会话')
    stages = []
    candidates = [p for p in store.list_projects(owner) if p.get('test_kind') == 'ui']
    independent = {p['id'] for p in candidates if p.get('execution_round') or p.get('managed_node_id')}
    related = {project['id']}
    while True:
        expanded = related | {p['id'] for p in candidates
            if p.get('regression_source', {}).get('project_id') in related or p.get('managed_parent_project_id') in related}
        if expanded == related:
            break
        related = expanded
    for candidate in candidates:
        if candidate['id'] not in related:
            continue
        # The navigation history is capped; the total must include older saved stages.
        root = store.project_dir(owner, candidate['id']) / 'analyses'
        for path in root.glob('*/report.json'):
            report = store._read(path)
            if report.get('report_type') == 'total' or report.get('consolidated_into'):
                continue
            report = ui_report_corrections.apply(report, ui_report_corrections.load(
                store, owner, candidate['id'], path.parent.name), store=store, owner=owner)
            stages.append((candidate['id'], report))
    stages.sort(key=lambda pair: (pair[1].get('created_at', ''), pair[1]['id']))
    if not stages:
        raise FileNotFoundError('尚无已发布的阶段报告')
    selected, origins = {}, {}
    history = []
    for pid, report in stages:
        base = f"/api/projects/{pid}/reports/{report['id']}"
        source = {'id': report['id'], 'project_id': pid, 'title': report['title'],
                  'created_at': report['created_at'], 'report_url': base + '/index.html',
                  'correction_revision': report.get('case_corrections', {}).get('revision', 0)}
        history.append(source)
        parsed = report.get('imported_results', {})
        for case in [*parsed.get('cases', []), *parsed.get('superseded_cases', [])]:
            cid = case['case_id']
            previous = selected.get(cid)
            if previous and (pid in independent or previous[1]['project_id'] in independent):
                # Parallel rounds can publish out of order. Compare server-saved
                # per-case changes, not when the whole report happened to finish.
                def changed_at(value, fallback):
                    try:
                        return datetime.fromisoformat(value.get('updated_at') or fallback).timestamp()
                    except (ValueError, TypeError):
                        return datetime.fromisoformat(fallback).timestamp()
                if changed_at(case, source['created_at']) < changed_at(previous[0], previous[1]['created_at']):
                    continue
            # Copy only the final selected value, not each overwritten stage.
            selected[cid] = (case, source)
            origins[cid] = (pid, report)
    cases = [{**deepcopy(case), 'source_report': source}
             for case, source in selected.values()]
    superseded = [c for c in cases if is_superseded(c)]
    cases = active_cases(cases)
    counts = {**Counter(c.get('status', 'not_run') for c in cases), 'total': len(cases)}
    latest = stages[-1][1]
    assets = []
    asset_indexes = {}
    for cid, (pid, report) in origins.items():
        source_key = (pid, report['id'])
        if source_key not in asset_indexes:
            index = defaultdict(list)
            for asset in report.get('ui_snapshot', {}).get('assets', []):
                index[asset['case_id']].append(asset)
            asset_indexes[source_key] = index
        for asset in asset_indexes[source_key].get(cid, []):
            assets.append({**asset, 'source_project_id': pid,
                'source_execution_id': report['ui_snapshot']['id'],
                'url': f"/api/projects/{pid}/reports/{report['id']}/asset-{asset['id']}"})
    labels = {'passed': '通过', 'failed': '不通过', 'partial': '验证未完成', 'blocked': '阻塞',
              'not_run': '未执行', 'pending_rule': '待确认规则', 'pending_action': '待用户确认',
              'skipped': '跳过', 'other': '其他'}
    summary = f"共 {len(cases)} 条用例，" + '，'.join(
        f"{labels.get(key, key)} {value} 条" for key, value in counts.items() if key != 'total') + '。'
    if not cases:
        summary = latest.get('summary', '')
    blocking = ui_dependencies.merge_blocking_summaries(
        (origins[c['case_id']][0], {**origins[c['case_id']][1].get('ui_snapshot', {}), 'cases': [c]})
        for c in cases)
    parsed = {'filename': '各阶段最新用例结果', 'sheet_name': '测试用例',
              'counts': counts, 'quality': {}, 'cases': cases, 'superseded_cases': superseded, 'blocking_summary': blocking}
    # These large collections are replaced by the merged values below.
    snapshot = deepcopy({key: value for key, value in latest.get('ui_snapshot', {}).items()
                         if key not in {'cases', 'assets', 'id', 'experiment'}})
    # A mixed-round total has no single experiment or executor timing window.
    inherited = deepcopy({key: value for key, value in latest.items()
                          if key not in {'ui_snapshot', 'imported_results', 'findings', 'regression_links'}})
    findings = result_findings(parsed, maximum=len(cases)) if cases else deepcopy(latest.get('findings', []))
    # A passing case still owns its historical defect and regression decision.
    # Keep it in the defect inbox, with the selected stage's original draft ID.
    finding_ids = {finding.get('case_id') for finding in findings}
    regression_by_case = {}
    for cid, (pid, stage) in origins.items():
        link = next((item for item in stage.get('regression_links', [])
                     if item.get('case_id') == cid), None)
        if not link:
            continue
        original = next((item for item in stage.get('findings', [])
                         if item.get('case_id') == cid), None)
        if original is None:
            continue
        regression_by_case[cid] = link
        if cid not in finding_ids:
            findings.append(deepcopy(original))
            finding_ids.add(cid)
    # Total finding indexes are presentation-only. Edits and lifecycle records
    # must address the selected case's original stage draft, including regressions.
    for finding in findings:
        origin = origins.get(finding.get('case_id'))
        if not origin:
            continue
        pid, stage = origin
        index = next((i for i, item in enumerate(stage.get('findings', []))
                      if item.get('case_id') == finding['case_id']), None)
        if index is not None:
            case = selected[finding['case_id']][0]
            if case.get('defect_title'):
                finding['title'] = case['defect_title']
            finding['draft_source'] = {'project_id': pid, 'report_id': stage['id'], 'draft_id': f'finding-{index}'}
    regression_links = [{**deepcopy(regression_by_case[finding['case_id']]),
                         'draft_id': f'finding-{index}'}
                        for index, finding in enumerate(findings)
                        if finding.get('case_id') in regression_by_case]
    return {**inherited, **entry(project), 'project_id': project['id'],
            'summary': summary, 'stage_reports': history[::-1], 'imported_results': parsed,
            'findings': findings,
            'regression_links': regression_links,
            'ui_snapshot': {**snapshot, 'id': '',
                            'cases': cases + superseded, 'assets': assets},
            'report_type': 'total'}


def export_test_data(store, owner, report):
    """Resolve each fixture in the execution that actually owns it."""
    import json
    import re
    from .ui_records import root_for
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('测试数据.json', json.dumps({
            'cases': [{k: c.get(k, '') for k in ('case_id', 'scenario', 'precondition',
                       'test_data', 'steps', 'expected', 'source_report')}
                      for c in report['imported_results']['cases']],
            'stage_reports': report['stage_reports']}, ensure_ascii=False, indent=2))
        seen = set()
        for asset in report['ui_snapshot']['assets']:
            identity = (asset['source_project_id'], asset['source_execution_id'], asset['id'])
            if identity in seen:
                continue
            seen.add(identity)
            if asset['kind'] != 'fixture':
                continue
            path = root_for(store, owner, asset['source_project_id'],
                            asset['source_execution_id']) / asset['id']
            if not path.is_file():
                raise FileNotFoundError('来源测试文件不可用，请核对原报告')
            if path.is_file():
                name = re.sub(r'[^0-9A-Za-z._\-\u4e00-\u9fff]+', '_', asset['filename'])
                prefix = f"{asset['source_project_id']}/{asset['source_execution_id']}/" if report.get('aggregate') else ""
                archive.writestr(f"文件/{prefix}{asset['id']}/{name}", path.read_bytes())
    return output.getvalue()
