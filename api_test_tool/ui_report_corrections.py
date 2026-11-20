"""Audited corrections for published UI reports.

The published report and execution snapshot stay unchanged on disk. Readers see
the latest correction, while the original remains available for audit.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from collections import Counter
from functools import wraps
import re

from .execution import Redactor
from .ui_records import LABELS
from .defect_results import normalize_report


EDITABLE_FIELDS = ('scenario', 'module', 'executor', 'precondition', 'test_data', 'steps',
                   'expected', 'evidence', 'conclusion', 'not_run_reason')


def correction_path(store, owner, project_id, report_id):
    return store.project_dir(owner, project_id) / 'analyses' / report_id / 'case-corrections.json'


def load(store, owner, project_id, report_id):
    path = correction_path(store, owner, project_id, report_id)
    record = store._read(path) if path.exists() else {'revision': 0, 'cases': {}, 'history': []}
    supplements = path.with_name('fixture-supplements.json')
    if supplements.exists():
        record['fixture_supplements'] = store._read(supplements)['assets']
    return record


def progress_record(store, owner, project_id, record):
    """Overlay audited statuses on the matching compact execution summary.

    Keep execution facts and lifecycle timestamps untouched. Most progress reads
    need no report body; only status corrections need its original snapshot.
    """
    rid = record.get('report_id')
    if not rid:
        return record
    path = correction_path(store, owner, project_id, rid)
    if not path.exists():
        return record
    corrections = store._read(path)
    effective = {**record, 'correction_revision': corrections.get('revision', 0)}
    statuses = {cid: value['fields']['status']
                for cid, value in corrections.get('cases', {}).items()
                if 'status' in value.get('fields', {})}
    if not statuses:
        return effective
    try:
        report = store._read(path.with_name('report.json'))
    except FileNotFoundError:
        return effective
    snapshot = report.get('ui_snapshot', {})
    if (snapshot.get('id') != record.get('execution_id') or
            snapshot.get('revision') != record.get('revision')):
        return effective
    imported = {case.get('case_id') for case in report.get('imported_results', {}).get('cases', [])}
    counts = Counter(record.get('counts', {}))
    for case in snapshot.get('cases', []):
        cid = case.get('case_id')
        if cid in statuses and cid in imported:
            counts[case.get('status', 'not_run')] -= 1
            counts[statuses[cid]] += 1
    return {**effective, 'counts': dict(+counts)}


def locked(fn):
    @wraps(fn)
    def wrapped(store, *args, **kwargs):
        with store._lock:
            return fn(store, *args, **kwargs)
    return wrapped


@locked
def advance_execution(store, owner, project_id, report_id, previous, current):
    """New observations supersede obsolete corrections, retaining their audit trail."""
    record = load(store, owner, project_id, report_id)
    originals = {c['case_id']: c for c in previous.get('cases', [])}
    changed = []
    for case in current['cases']:
        cid = case['case_id']
        correction = record['cases'].get(cid)
        if not correction:
            continue
        old = originals.get(cid, {})
        fields = correction['fields']
        obsolete = {key for key in fields if case.get('actual' if key == 'evidence' else key) != old.get('actual' if key == 'evidence' else key)}
        if any(case.get(key) != old.get(key) for key in ('status', 'actual')):
            obsolete |= {'status', 'evidence', 'conclusion'} & fields.keys()
        if not obsolete:
            continue
        changed.append({'case_id': cid, 'previous': deepcopy(correction), 'fields': sorted(obsolete)})
        correction['fields'] = {key: value for key, value in fields.items() if key not in obsolete}
        if not correction['fields']:
            del record['cases'][cid]
    if current['revision'] != previous.get('revision') and 'summary' in record.get('report', {}).get('fields', {}):
        changed.append({'scope': 'report', 'previous': deepcopy(record['report'])})
        record['report']['fields'].pop('summary')
    if changed:
        record['revision'] += 1
        record['history'].append({'scope': 'continuation', 'revision': record['revision'],
                                  'execution_revision': current['revision'], 'superseded': changed,
                                  'updated_at': datetime.now(timezone.utc).isoformat()})
        store._write(correction_path(store, owner, project_id, report_id),
                     {k: v for k, v in record.items() if k != 'fixture_supplements'})


@locked
def save(store, owner, project_id, report_id, report, case_id, fields, revision, *, actor=''):
    if not report.get('ui_snapshot') or not report.get('imported_results'):
        raise ValueError('这份报告没有可更正的 UI 测试用例')
    source_case = next((case for case in report['imported_results']['cases'] if case.get('case_id') == case_id), None)
    if source_case is None:
        raise ValueError('用例不存在')
    if not isinstance(fields, dict) or not fields or not set(fields) <= set(EDITABLE_FIELDS) | {'status', 'action_context'}:
        raise ValueError('用例更正字段无效')
    cleaned = {}
    for key in set(fields) & set(EDITABLE_FIELDS):
        value = fields[key]
        if not isinstance(value, str) or len(value) > 20000:
            raise ValueError(f'{key} 必须是文本，最多 20000 字符')
        cleaned[key] = value.strip()
    if 'action_context' in fields:
        from .ui_action_context import normalize
        cleaned['action_context'] = normalize(fields['action_context'])
    if 'status' in fields:
        if fields['status'] not in set(LABELS) | {source_case.get('status')}:
            raise ValueError('执行结果无效')
        cleaned['status'] = fields['status']
    record = load(store, owner, project_id, report_id)
    if type(revision) is not int or revision != record['revision']:
        raise ValueError('用例说明已被更新，请刷新报告后重试')
    updated_at = datetime.now(timezone.utc).isoformat()
    previous = record['cases'].get(case_id)
    record['revision'] += 1
    merged = {**(previous or {}).get('fields', {}), **cleaned}
    record['cases'][case_id] = {'fields': Redactor().snapshot(merged),
                                'updated_at': updated_at, 'revision': record['revision']}
    record['history'].append({'scope': 'case', 'case_id': case_id, 'revision': record['revision'],
                              'updated_at': updated_at, 'previous': previous, 'actor': actor})
    store._write(correction_path(store, owner, project_id, report_id),
                 {key: value for key, value in record.items() if key != 'fixture_supplements'})
    return record


@locked
def save_report(store, owner, project_id, report_id, report, fields, revision, *, actor=''):
    if not report.get('ui_snapshot') or not report.get('imported_results'):
        raise ValueError('这份报告没有可更正的 UI 测试结果')
    if not isinstance(fields, dict) or set(fields) != {'title', 'summary'}:
        raise ValueError('报告更正字段无效')
    title, summary = fields['title'], fields['summary']
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError('报告标题不能为空且最多 200 字符')
    if not isinstance(summary, str) or len(summary) > 30000:
        raise ValueError('报告总结最多 30000 字符')
    record = load(store, owner, project_id, report_id)
    if type(revision) is not int or revision != record['revision']:
        raise ValueError('报告已被更新，请刷新后重试')
    updated_at = datetime.now(timezone.utc).isoformat()
    previous = record.get('report')
    record['revision'] += 1
    record['report'] = {'fields': Redactor().snapshot({'title': title.strip(), 'summary': summary.strip()}),
                        'updated_at': updated_at, 'revision': record['revision']}
    record['history'].append({'scope': 'report', 'revision': record['revision'],
                              'updated_at': updated_at, 'previous': previous, 'actor': actor})
    store._write(correction_path(store, owner, project_id, report_id),
                 {key: value for key, value in record.items() if key != 'fixture_supplements'})
    return record


@locked
def save_titles(store, owner, project_id, report_id, report, draft_ids, fields, revision, *, actor=''):
    """Save a whole title batch atomically, independently of submission status."""
    from .defect_title import ENVIRONMENTS, CLIENTS, normalize_title
    if not report.get('ui_snapshot') or not report.get('imported_results'):
        raise ValueError('这份报告没有可修改的 UI 缺陷标题')
    if (not isinstance(draft_ids, list) or not 1 <= len(draft_ids) <= 200
            or any(not isinstance(did, str) or not re.fullmatch(r'finding-\d{1,5}', did) for did in draft_ids)
            or len(set(draft_ids)) != len(draft_ids)):
        raise ValueError('请选择有效且不重复的缺陷，单批最多 200 条')
    if not isinstance(fields, dict) or not fields or not set(fields) <= {'environment', 'client', 'module'}:
        raise ValueError('标题属性无效')
    if any(not isinstance(value, str) for value in fields.values()):
        raise ValueError('标题属性必须是文本')
    fields = {key: value.strip() for key, value in fields.items() if value.strip()}
    if not fields:
        raise ValueError('请至少选择或填写一个属性')
    if fields.get('environment', '') not in ('', *ENVIRONMENTS) or fields.get('client', '') not in ('', *CLIENTS):
        raise ValueError('请选择有效的环境和业务端')
    module = fields.get('module', '')
    if len(module) > 60 or re.search(r'[\[\]【】\r\n]', module) or module in {'同上', '无', '未标注模块', '待补充模块'}:
        raise ValueError('功能/模块最多 60 字符，不能包含括号或换行')
    record = load(store, owner, project_id, report_id)
    if type(revision) is not int or revision != record['revision']:
        raise ValueError('报告已被其他协作者更新，请刷新报告后重试')
    effective = apply(report, record)
    case_ids = {case['case_id'] for case in effective['imported_results']['cases']}
    values = []
    for did in draft_ids:
        index = int(did.split('-')[1])
        if index >= len(effective.get('findings', [])):
            raise ValueError('缺陷不存在，请刷新报告后重试')
        finding = effective['findings'][index]
        if finding.get('case_id') not in case_ids:
            raise ValueError('缺陷没有关联可修改的测试用例')
        title = normalize_title(finding['title'], **fields)
        if len(title) > 300:
            raise ValueError('修改后的标题不能超过 300 个字符')
        values.append({'draft_id': did, 'case_id': finding['case_id'], 'title': title})
    updated_at = datetime.now(timezone.utc).isoformat()
    record['revision'] += 1
    for value in values:
        cid = value['case_id']
        previous = record['cases'].get(cid)
        merged = {**(previous or {}).get('fields', {}), 'defect_title': value['title']}
        record['cases'][cid] = {'fields': Redactor().snapshot(merged),
                                'updated_at': updated_at, 'revision': record['revision']}
        record['history'].append({'scope': 'title', 'case_id': cid, 'revision': record['revision'],
                                  'updated_at': updated_at, 'previous': previous, 'actor': actor})
    store._write(correction_path(store, owner, project_id, report_id),
                 {key: value for key, value in record.items() if key != 'fixture_supplements'})
    return {'revision': record['revision'], 'values': values}


def apply(report, corrections, *, store=None, owner=None):
    if not corrections.get('cases') and not corrections.get('report') and not corrections.get('fixture_supplements'):
        return normalize_report(report, store, owner)
    effective = deepcopy(report)
    if corrections.get('fixture_supplements'):
        known = {a['id'] for a in effective['ui_snapshot']['assets']}
        effective['ui_snapshot']['assets'].extend(
            deepcopy(a) for a in corrections['fixture_supplements'] if a['id'] not in known)
        effective['fixture_supplements'] = deepcopy(corrections['fixture_supplements'])
    report_fields = corrections.get('report', {}).get('fields', {})
    effective.update(report_fields)
    cases = {case.get('case_id'): case for case in effective['imported_results']['cases']}
    snapshots = {case.get('case_id'): case for case in effective.get('ui_snapshot', {}).get('cases', [])}
    status_changed = []
    for case_id, correction in corrections.get('cases', {}).items():
        case = cases.get(case_id)
        if not case:
            continue
        fields = correction['fields']
        original_status = case.get('status')
        if any(key in fields and fields[key] != case.get(key) for key in ('status', 'evidence')):
            case['observations_corrected_at'] = correction['updated_at']
        case.update(fields)
        if 'status' in fields:
            case['status_before_correction'] = original_status
            case['result'] = LABELS.get(fields['status'], case.get('result', fields['status']))
            if fields['status'] != original_status:
                status_changed.append(case_id)
        snapshot = snapshots.get(case_id)
        if snapshot:
            snapshot.update({key: value for key, value in fields.items() if key != 'evidence'})
            if 'evidence' in fields:
                snapshot['actual'] = fields['evidence']
        for finding in effective.get('findings', []):
            if finding.get('case_id') == case_id:
                if 'defect_title' in fields:
                    finding['title'] = fields['defect_title']
                finding.update({key: fields[key] for key in ('precondition', 'test_data', 'steps', 'expected')
                                if key in fields})
                if 'evidence' in fields:
                    finding['actual'] = finding['evidence'] = fields['evidence']
        if set(fields) - {'defect_title'}:
            case['wording_corrected_at'] = correction['updated_at']
        if 'defect_title' in fields:
            case['title_corrected_at'] = correction['updated_at']
    if status_changed:
        counts = Counter(case.get('status') for case in effective['imported_results']['cases'])
        effective['imported_results']['counts'] = {
            **{key: counts.get(key, 0) for key in set(LABELS) | set(report['imported_results'].get('counts', {})) | set(counts)
               if key != 'total'},
            'total': len(cases),
        }
        if 'summary' not in report_fields:
            results = '、'.join(f'{LABELS.get(status, status)}{count}'
                               for status, count in counts.items() if count)
            effective['summary'] = f'共{len(cases)}条，{results}。'
    effective['case_corrections'] = {'revision': corrections['revision'],
                                     'cases': {case_id: {'updated_at': value['updated_at']}
                                               for case_id, value in corrections.get('cases', {}).items()},
                                     'report': {'updated_at': corrections['report']['updated_at']}
                                     if corrections.get('report') else {}}
    return normalize_report(effective, store, owner)
