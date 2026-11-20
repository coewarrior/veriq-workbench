"""Step-sized execution, evidence and continuation for requirements-driven tests.

Browser/manual observations are supplied by the executor. HTTP observations use
the capability runner. Neither dependency readiness nor a simulated payment is
an assertion about the target application's order or entitlement state.
"""
from __future__ import annotations

import copy

from .execution import Redactor
from . import ui_dependencies, ui_action_context
from .checkpoint_results import checkpoint_point_gaps as point_gaps, reconcile_checkpoint_results as reconcile, preserve_checkpoint_status_source, checkpoint_has_blocker_provenance

KINDS = {'browser', 'http', 'observation', 'manual', 'prepare', 'cleanup', 'payment', 'concurrency'}
MODES = {'real', 'sandbox', 'mock', 'design'}
STATUSES = {'not_run', 'passed', 'failed', 'partial', 'blocked', 'pending_rule', 'pending_action'}
DONE = {'passed', 'failed'}


def text(value, name, maximum=4000, required=False):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValueError(f'{name} 必须是文本，最多 {maximum} 字符' + ('且不能为空' if required else ''))
    return value.strip()


def ids(values, name):
    if not isinstance(values, list) or len(values) > 200 or any(
            not isinstance(v, str) or not v.strip() or len(v) > 200 for v in values):
        raise ValueError(name + ' 必须是 ID 数组，每批最多 200 项')
    if len(set(values)) != len(values):
        raise ValueError(name + ' 不能重复')
    return values


def normalize(case, old, target):
    """Preserve structured designs on ordinary case updates; validate a DAG."""
    result = {}
    for field in ('requirement_ids', 'question_ids'):
        result[field] = ids(case.get(field, old.get(field, [])), field)
    values = case.get('checkpoints', old.get('checkpoints', []))
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError('checkpoints 必须是最多 100 项的检查点数组')
    points, seen = [], set()
    for value in values:
        if not isinstance(value, dict):
            raise ValueError('检查点必须为对象')
        item = {k: text(value.get(k, ''), k, required=k in {'id', 'title', 'expected'})
                for k in ('id', 'title', 'expected', 'basis', 'actual', 'method', 'action_required', 'capability_key')}
        if item['id'] in seen:
            raise ValueError('检查点 ID 不能重复')
        # Edges only point backward: a stable, explicit execution order, no cycles.
        item['depends_on'] = ids(value.get('depends_on', []), 'depends_on')
        if not set(item['depends_on']) <= seen:
            raise ValueError('depends_on 只能引用本用例中位于前面的检查点')
        seen.add(item['id'])
        item['kind'] = value.get('kind', 'browser')
        item['status'] = value.get('status', 'not_run')
        item['verification_mode'] = value.get('verification_mode', 'design')
        if (not all(isinstance(item[k], str) for k in ('kind', 'status', 'verification_mode')) or
                item['kind'] not in KINDS or item['status'] not in STATUSES or item['verification_mode'] not in MODES):
            raise ValueError('检查点 kind、status 或 verification_mode 无效')
        old_context = next((p.get('action_context', {}) for p in old.get('checkpoints', []) if p['id'] == item['id']), {})
        item['action_context'] = ui_action_context.normalize(value.get('action_context', old_context))
        item['question_ids'] = ids(value.get('question_ids', []), 'question_ids')
        item['dependencies'] = ui_dependencies.normalize(value.get('dependencies', []), case, target)
        assertions = value.get('assertions', [])
        if not isinstance(assertions, list) or len(assertions) > 50:
            raise ValueError('assertions 每个检查点最多 50 项')
        checked_assertions = []
        for assertion in assertions:
            if (not isinstance(assertion, dict) or not isinstance(assertion.get('kind'), str) or
                    assertion['kind'] not in {'equal', 'delta', 'length', 'http_status'} or 'expected' not in assertion):
                raise ValueError('检查点比较需有 kind 和明确 expected')
            a = {k: text(assertion.get(k, ''), k) for k in ('pointer', 'source_quote', 'baseline_checkpoint_id')}
            if assertion['kind'] != 'http_status' and not a['pointer'].startswith('/'):
                raise ValueError('业务比较需有 JSON pointer')
            if assertion['kind'] == 'delta' and a['baseline_checkpoint_id'] not in seen - {item['id']}:
                raise ValueError('delta 需引用本用例先前保存的观察检查点')
            checked_assertions.append({**a, 'kind': assertion['kind'], 'expected': assertion['expected']})
        item['assertions'] = checked_assertions
        old_point = next((p for p in old.get('checkpoints', []) if p['id'] == item['id']), {})
        preserve_checkpoint_status_source(item, old_point)
        if old_point.get('rule_updates'):
            changed = any(item.get(k) != old_point.get(k) for k in ('expected', 'basis', 'assertions'))
            item['rule_updates'] = [] if changed else old_point['rule_updates']
        elif value.get('rule_updates'):
            item['rule_updates'] = ids(value['rule_updates'], 'rule_updates')
        for key in ('evidence', 'correlation', 'inherited_from'):
            val = value.get(key, old_point.get('correlation', {}) if key == 'correlation' else {} if key != 'evidence' else [])
            if key == 'evidence':
                if not isinstance(val, list) or len(val) > 30 or any(not isinstance(e, dict) for e in val):
                    raise ValueError('检查点 evidence 必须为最多 30 项的证据对象数组')
            elif not isinstance(val, dict):
                raise ValueError(key + ' 必须是对象')
            if key == 'inherited_from' and val:
                text(val.get('execution_id'), 'inherited_from.execution_id', 100, True)
            if key == 'correlation':
                for stable in ('order_id', 'payer_id', 'provider_transaction_id'):
                    original = next((p['correlation'][stable] for p in old.get('checkpoints', [])
                                     if stable in p.get('correlation', {})), None)
                    if original is not None and stable in val and val[stable] != original:
                        raise ValueError('续跑关联必须保留原订单：' + stable)
                    if stable in old_point.get('correlation', {}) and stable not in val:
                        raise ValueError('不能清除原订单关联；重新建立初态请使用 retest')
            if len(str(val)) > (9 * 1024 * 1024 if key == 'evidence' else 20000):
                raise ValueError('检查点证据或关联数据过大')
            item[key] = Redactor().snapshot(val)
        points.append(item)
    result['checkpoints'] = points
    return result


def apply_updates(case, old):
    """Patch observations by stable ID without resending or dropping the design."""
    updates = case.get('checkpoint_updates')
    if updates is None:
        return case
    if 'checkpoints' in case:
        raise ValueError('checkpoints 与 checkpoint_updates 二选一')
    if not isinstance(updates, list) or len(updates) > 100:
        raise ValueError('checkpoint_updates 必须是检查点结果数组')
    allowed = {'id', 'status', 'actual', 'method', 'verification_mode', 'evidence',
               'correlation', 'action_required', 'action_context'}
    points = {p['id']: dict(p) for p in old.get('checkpoints', [])}
    seen = set()
    for update in updates:
        if not isinstance(update, dict) or set(update) - allowed:
            raise ValueError('checkpoint_updates 只接受检查点 ID 和实际观察字段')
        key = update.get('id')
        if not isinstance(key, str) or key not in points or key in seen:
            raise ValueError('checkpoint_updates 的 ID 必须存在且不重复')
        seen.add(key)
        points[key].update(update)
    return {**case, 'checkpoints': list(points.values())}


def plan(record):
    from .ui_case_scope import active_cases
    record = {**record, 'cases': active_cases(record['cases'])}
    from .testing_policy import case_excluded, REASON
    runnable, waiting, done, excluded = [], [], [], []
    for case in record['cases']:
        for point in case.get('checkpoints', []):
            ref = {'case_id': case['case_id'], 'checkpoint_id': point['id'], 'title': point['title'],
                   'kind': point['kind'], 'capability_key': point.get('capability_key', '')}
            if case_excluded(case) and point['status'] not in DONE:
                excluded.append({**ref, 'reason': REASON})
                continue
            if point['status'] in DONE:
                done.append({**ref, 'status': point['status'], 'inherited_from': point.get('inherited_from', {})})
            elif point['status'] == 'pending_action':
                waiting.append({**ref, 'status': point['status'], 'action_required': point['action_required'],
                                'correlation': point.get('correlation', {}), 'action_context': point.get('action_context', {})})
            else:
                gaps = point_gaps(record, case, point)
                if point['status'] == 'blocked' and not checkpoint_has_blocker_provenance(point):
                    waiting.append({**ref, 'status': 'blocked', 'gaps': gaps,
                                    'reason': point.get('actual') or '原阻塞事实尚未复核，不能根据其他条件恢复推断已解除。'})
                elif gaps:
                    waiting.append({**ref, 'status': point['status'], 'gaps': gaps, 'business_steps_executed': False})
                else:
                    runnable.append(ref)
    return {'runnable_checkpoints': runnable, 'waiting_checkpoints': waiting, 'completed_checkpoints': done,
            'excluded_checkpoints': excluded}


def current(store, owner, pid, execution_id, revision):
    from . import ui_records
    project = ui_records.ui_project(store, owner, pid)
    record = ui_records.load(store, owner, pid, execution_id)
    if project.get('ui_execution_id') != execution_id:
        raise ValueError('只能更新当前任务的执行记录')
    if type(revision) is not int or revision != record['revision']:
        raise ValueError('用例已更新，请读取最新 revision 后重试')
    return project, record


def write(store, owner, pid, record):
    from . import ui_records
    path = ui_records.root_for(store, owner, pid, record['id']) / 'cases.json'
    previous = {c['case_id']: c for c in store._read(path)['cases']} if path.exists() else {}
    reconcile(record)
    for case in record['cases']:
        if case != previous.get(case['case_id']):
            case['updated_at'] = ui_records.now()
    record['revision'] += 1
    store._write(ui_records.root_for(store, owner, pid, record['id']) / 'cases.json', record)
    progress = ui_dependencies.progress_record(store, owner, pid, record)
    store.update_project(owner, pid, {'ui_execution_revision': record['revision'], 'ui_progress_record': progress})
    ui_records.sync_regression_results(store, owner, ui_records.ui_project(store, owner, pid), record)
    publication = ui_records.refresh_published(store, owner, pid, record)
    return {'execution_id': record['id'], 'revision': record['revision'],
            **publication,
            'execution_plan': ui_dependencies.plan(record, recovery=progress['recovery']), 'checkpoint_plan': plan(record)}


def record_result(store, owner, pid, execution_id, revision, case_id, checkpoint_id, result):
    from . import ui_retests
    with store._lock:
        project, record = current(store, owner, pid, execution_id, revision)
        case = next((c for c in record['cases'] if c['case_id'] == case_id), None)
        point = next((p for p in (case or {}).get('checkpoints', []) if p['id'] == checkpoint_id), None)
        if not point:
            raise ValueError('检查点不存在')
        # A checkpoint is an observation, not a replacement for its design.
        keys = {'status', 'actual', 'method', 'verification_mode', 'evidence', 'correlation', 'action_required', 'action_context'}
        if not isinstance(result, dict) or set(result) - keys:
            raise ValueError('检查点结果只能更新状态、观察、证据、验证方式与续跑关联数据')
        previous = copy.deepcopy(point)
        for key in ('order_id', 'payer_id', 'provider_transaction_id'):
            original = next((p['correlation'][key] for p in case['checkpoints'] if key in p.get('correlation', {})), None)
            if original is not None and key in result.get('correlation', {}) and result['correlation'][key] != original:
                raise ValueError('人工续跑和后续观察必须关联原订单：' + key)
        updated = {**point, **result, 'inherited_from': {}}
        # Normalize the full DAG to validate the updated point's fields.
        points = [updated if p['id'] == checkpoint_id else p for p in case['checkpoints']]
        checked = normalize({**case, 'checkpoints': points}, case, project.get('ui_target_url', ''))
        case.update(ui_retests.redact(store, owner, pid, checked))
        record.setdefault('checkpoint_history', []).append({'case_id': case_id, 'checkpoint_id': checkpoint_id,
            'before': previous, 'result': next(p for p in case['checkpoints'] if p['id'] == checkpoint_id)})
        return write(store, owner, pid, record)
