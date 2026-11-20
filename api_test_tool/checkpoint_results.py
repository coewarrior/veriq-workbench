"""Pure checkpoint result derivation shared by storage and receipt verification."""

CHECKPOINT_DONE = {'passed', 'failed'}


def checkpoint_point_gaps(record, case, point):
    checks = record.get('dependency_checks', {})
    gaps = []
    for qid in point.get('rule_updates', []):
        gaps.append({'kind': 'rule', 'id': qid, 'title': '更新本检查点预期及依据',
                     'reason': '规则已明确或变化，需要先修订受影响预期和依据，再重新验证', 'status': 'pending_rule'})
    for dep in [*case.get('dependencies', []), *point.get('dependencies', [])]:
        check = checks.get(dep['id'])
        if not check or check.get('status') != 'ready':
            gaps.append({'kind': 'dependency', 'id': dep['id'], 'title': dep['title'],
                         'reason': (check or {}).get('observed') or '尚未检查执行条件',
                         'status': (check or {}).get('status', 'unchecked')})
    questions = {q['id']: q for q in record.get('requirement_design', {}).get('questions', [])}
    for qid in [*case.get('question_ids', []), *point.get('question_ids', [])]:
        q = questions.get(qid)
        if not q or q.get('status') != 'resolved':
            gaps.append({'kind': 'rule', 'id': qid, 'title': (q or {}).get('title', qid),
                         'reason': '需要明确预期规则', 'status': 'pending_rule'})
    by_id = {p['id']: p for p in case.get('checkpoints', [])}
    for sid in point.get('depends_on', []):
        if by_id[sid]['status'] != 'passed':
            gaps.append({'kind': 'step', 'id': sid, 'title': by_id[sid]['title'],
                         'reason': '前序步骤尚未成功完成', 'status': by_id[sid]['status']})
    return gaps



def checkpoint_has_blocker_provenance(point):
    """Old persisted structured gaps are evidence; prose or empty gaps are not."""
    if point.get('status_source') == 'unstructured_blocker':
        return False
    return point.get('status_source') == 'prerequisite_check' or any(
        gap.get('kind') in {'dependency', 'step'} and gap.get('id') and
        gap.get('status') in {'blocked', 'failed', 'pending_action'}
        for gap in point.get('gaps', []) if isinstance(gap, dict))


def preserve_checkpoint_status_source(point, previous):
    """Only server-saved automatic provenance survives an unchanged blocked state."""
    point.pop('status_source', None)
    if point.get('status') == previous.get('status') == 'blocked':
        point['status_source'] = ('prerequisite_check' if checkpoint_has_blocker_provenance(previous)
                                  else 'unstructured_blocker')
    return point


def reconcile_checkpoint_results(record):
    """Attach prerequisite diagnostics without changing the executor's verdicts."""
    for case in record['cases']:
        for point in case.get('checkpoints', []):
            point['gaps'] = checkpoint_point_gaps(record, case, point)
    return record
