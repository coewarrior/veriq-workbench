"""Preserve observations during the existing batched save, without extra I/O."""
from copy import deepcopy
from .ui_case_scope import active_cases, is_superseded

RESULT_FIELDS = ('status', 'actual', 'conclusion', 'not_run_reason', 'checkpoints',
                 'environment', 'client', 'action_context', 'executed_at', 'blocked_by',
                 'execution_disposition', 'superseded_by')


def preserve_history(previous, current):
    """One immutable before-image per changed case/revision, across all callers."""
    original = {case['case_id']: case for case in previous.get('cases', [])}
    history = dict(previous.get('case_history', {}))
    for case in current.get('cases', []):
        old = original.get(case['case_id'])
        if not old or not any(old.get(k) != case.get(k) for k in RESULT_FIELDS):
            continue
        key = str(previous.get('revision', 0))
        if key not in history:
            history[key] = {'revision': previous.get('revision', 0), 'cases': []}
        elif history[key] is previous.get('case_history', {}).get(key):
            history[key] = {**history[key], 'cases': list(history[key]['cases'])}
        entry = history[key]
        if not any(c['case_id'] == old['case_id'] for c in entry['cases']):
            entry['cases'].append(deepcopy(old))
    if history:
        current['case_history'] = history
    return current


def annotate(case, record, node=None):
    history = [*record.get('case_history', {}).values(),
               *(node or {}).get('case_history', {}).values()]
    failed = case['case_id'] in (node or {}).get('continuation_failed_case_ids', []) or any(
                 old.get('case_id') == case['case_id'] and old.get('status') == 'failed'
                 for entry in history for old in entry.get('cases', []))
    result = deepcopy(case)
    result['had_confirmed_failure'] = failed
    result['managed_status'] = 'retry_passed' if failed and case.get('status') == 'passed' else case.get('status', 'not_run')
    result['coverage_complete'] = case.get('status') in {'passed', 'failed'} and all(
        point.get('status') in {'passed', 'failed'} for point in case.get('checkpoints', []))
    if failed and case.get('status') not in {'passed', 'failed'}:
        result['result_note'] = '本轮已有确认失败，当前复测尚未完成；保留原失败证据。'
    return result


def validate_supersession(previous, cases):
    by_id = {case['case_id']: case for case in cases}
    old = {case['case_id']: case for case in previous.get('cases', [])}
    history = [c for entry in previous.get('case_history', {}).values() for c in entry.get('cases', [])]
    for case in cases:
        refs = case.get('superseded_by', [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            raise ValueError('superseded_by 必须为明确的替代用例 ID 数组')
        if len(refs) != len(set(refs)) or any(ref == case['case_id'] or ref not in by_id for ref in refs):
            raise ValueError('superseded_by 不能重复、引用自身或不存在的用例')
        if not refs:
            continue
        prior = [old[case['case_id']]] if case['case_id'] in old else []
        prior += [c for c in history if c['case_id'] == case['case_id']]
        if not is_superseded(case) or any(c.get('status') not in {'not_run', 'blocked'} or c.get('executed_at') or
                any(p.get('status') not in {'not_run', 'blocked'} for p in c.get('checkpoints', [])) for c in prior):
            raise ValueError('只能关联未执行的 not_run/blocked 聚合；不能隐藏已有执行事实或历史')
    visiting, done = set(), set()
    def visit(cid):
        if cid in visiting:
            raise ValueError('superseded_by 不能形成循环引用')
        if cid in done:
            return
        visiting.add(cid)
        for ref in by_id[cid].get('superseded_by', []):
            visit(ref)
        visiting.remove(cid)
        done.add(cid)
    for cid in by_id:
        visit(cid)


def active_coverage_refs(record):
    """Resolve explicit replacement chains for coverage projection, preserving input."""
    by_id = {c['case_id']: c for c in record.get('cases', [])}
    def resolve(cid, seen):
        case = by_id.get(cid, {})
        if cid in seen or not is_superseded(case):
            return {cid}
        return {leaf for ref in case['superseded_by'] for leaf in resolve(ref, seen | {cid})}
    return {leaf for area in record.get('coverage', []) for cid in area['case_ids'] for leaf in resolve(cid, set())}
