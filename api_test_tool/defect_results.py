"""Keep same-round corrections separate from prior-round defect regression."""


def round_id(project):
    return project.get('managed_parent_project_id') or project['id']


def current_outcome(case):
    return 'pending_submission' if case.get('status') == 'failed' else 'result_corrected'


def prior_failure(store, owner, project_id, link, *, _reports=None):
    """A different report/revision or sibling module is not a different round."""
    source_id = link.get('source_project_id')
    if not source_id or round_id(store.get_project(owner, source_id)) == round_id(store.get_project(owner, project_id)):
        return False
    from .report_reads import _ReportBatch
    reports = _reports if _reports is not None else _ReportBatch(store)
    rid = link.get('source_report_id', '')
    source = reports.report(owner, source_id, rid)
    draft_id = link.get('source_draft_id', '')
    if not draft_id.startswith('finding-') or not draft_id[8:].isdigit():
        return False
    index = int(draft_id[8:])
    findings = source.get('findings', [])
    if index >= len(findings) or findings[index].get('case_id') != link.get('case_id'):
        return False
    import hashlib
    path = store.project_dir(owner, source_id) / 'pingcode' / (hashlib.sha256((rid + ':' + draft_id).encode()).hexdigest() + '.json')
    if path.exists() and store._read(path).get('triage_status') == 'rejected':
        return False
    return any(c.get('case_id') == link.get('case_id') and c.get('status') == 'failed'
               and c.get('status_before_correction') in (None, 'failed')
               for c in source.get('imported_results', {}).get('cases', []))


def normalize_report(report, store=None, owner=None):
    """Repair legacy self-regression labels on read, preserving stored history/IDs."""
    if not report.get('regression_links'):
        return report
    effective = {**report, 'regression_links': [dict(link) for link in report['regression_links']]}
    cases = {c['case_id']: c for c in effective.get('imported_results', {}).get('cases', [])}
    for link in effective['regression_links']:
        case = cases.get(link.get('case_id'), {})
        same_round = link.get('source_project_id') == report.get('project_id')
        if store and link.get('source_project_id') and report.get('project_id'):
            same_round = round_id(store.get_project(owner, link['source_project_id'])) == round_id(store.get_project(owner, report['project_id']))
        if (same_round
                or case.get('status_before_correction') not in (None, case.get('status'))):
            link['outcome'] = current_outcome(case)
    return effective
