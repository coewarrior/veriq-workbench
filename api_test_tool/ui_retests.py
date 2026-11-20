"""Private inputs and focused UI retest rounds; frozen reports stay intact."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from .execution import Redactor
from . import ui_report_corrections, ui_dependencies, testing_policy

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
ELIGIBLE = {'blocked', 'not_run', 'failed', 'partial', 'pending_action', 'pending_rule', 'skipped', 'other', 'broken', 'quarantined', 'unsupported'}


def now():
    return datetime.now(timezone.utc).isoformat()


def report(store, owner, project, report_id):
    if report_id == 'total':
        from .ui_total_reports import build
        return build(store, owner, project)
    historical = (isinstance(report_id, str) and re.fullmatch(r'[a-f0-9-]{36}', report_id)
                  and (store.project_dir(owner, project['id']) / 'analyses' / report_id / 'report.json').is_file())
    if project.get('test_kind') != 'ui' or (report_id not in {r['id'] for r in project.get('analysis_reports', [])} and not historical):
        raise FileNotFoundError('UI 报告不存在')
    root = store.project_dir(owner, project['id']) / 'analyses' / report_id
    saved = store._read(root / 'report.json')
    return ui_report_corrections.apply(saved, ui_report_corrections.load(store, owner, project['id'], report_id))


def selection(saved, ids):
    if not isinstance(ids, list) or not 1 <= len(ids) <= 10000 or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('请选择本报告中不同的未完全通过用例，最多 10000 条')
    by_id = {c['case_id']: c for c in _report_cases(saved)}
    if any(i not in by_id or by_id[i].get('status') not in ELIGIBLE for i in ids):
        raise ValueError('只能为本报告中未完全通过的用例补充数据和补测')
    if any(testing_policy.case_excluded(by_id[i]) for i in ids):
        raise ValueError(testing_policy.REASON + '；普通补测不解除平台范围限制')
    return [by_id[i] for i in ids]


def _state(store, owner, pid):
    path = store.project_dir(owner, pid) / 'ui-retest-inputs.json'
    return path, store._read(path) if path.exists() else {'revision': 0, 'records': {}, 'bindings': {}}


def _decode(store, state, input_id):
    if input_id not in state['records']:
        raise ValueError('已保存的数据不存在，请刷新后重试')
    return json.loads(store._cipher.decrypt(state['records'][input_id].encode()).decode())


def _public(value):
    result = copy.deepcopy(value)
    password = result['account'].pop('password', '')
    result['account']['has_password'] = bool(password)
    for file in result['files']:
        file.pop('content_base64', None)
    return result


def _report_cases(saved):
    """Keep dependency provenance available for reports created before import copying."""
    imported = saved.get('imported_results', {}).get('cases', [])
    snapshot = {c.get('case_id'): c for c in saved.get('ui_snapshot', {}).get('cases', [])}
    result = []
    for case in imported:
        source = snapshot.get(case.get('case_id'), {})
        merged = {**source, **case}
        for key in ('dependencies', 'checkpoints'):
            if not merged.get(key) and source.get(key):
                merged[key] = copy.deepcopy(source[key])
        result.append(merged)
    # Older reports have no structured dependencies but often retain the exact
    # repeated precondition. Preserve that explicit shared context as a stable
    # data dependency so one saved input can be reused by its related cases.
    target_url = saved.get('target_url') or saved.get('ui_snapshot', {}).get('ui_target_url', '')
    buckets = {}
    for case in result:
        if ui_dependencies.case_dependencies(case) or case.get('status') not in {'blocked', 'not_run', 'skipped'}:
            continue
        precondition = str(case.get('precondition') or '').strip()
        if not precondition or not target_url or not case.get('environment'):
            continue
        identity = {'target_url': target_url, 'environment': case.get('environment', ''),
                    'client': case.get('client', ''), 'module': case.get('module', ''),
                    'precondition': precondition}
        bucket_id = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        buckets.setdefault(bucket_id, (identity, []))[1].append(case)
    for bucket_id, (identity, members) in buckets.items():
        if len(members) < 2:
            continue
        dependency = ui_dependencies.normalize([{
            'key': 'legacy-shared-' + bucket_id,
            'title': f"{identity['module'] or '当前模块'}相同前置数据",
            'kind': 'data', 'environment': identity['environment'], 'tenant': '', 'role': '',
        }], members[0], target_url)[0]
        for case in members:
            case['dependencies'] = [dependency]
    return result


def report_groups(saved):
    cases = [c for c in _report_cases(saved) if not testing_policy.case_excluded(c)]
    checks = saved.get('ui_snapshot', {}).get('dependency_checks', {})
    result = ui_dependencies.groups(cases, checks)
    by_id = {c['case_id']: c for c in cases}
    for group in result:
        check = group.get('check') or {}
        # A blocked check is authoritative. For legacy reports that have the
        # dependency in the immutable snapshot but no check ledger, expose the
        # same explicit group for blocked/not-run cases so shared data is still
        # entered once. Do not infer links from similar prose or force inputs
        # onto already executed failed/partial cases.
        if check.get('status') == 'blocked':
            eligible = ELIGIBLE
        elif not check:
            eligible = {'blocked', 'not_run', 'skipped'}
        else:
            eligible = set()
        group['affected_case_ids'] = [cid for cid in group['case_ids'] if by_id[cid].get('status') in eligible]
        group['input_fields'] = credential_fields([by_id[cid] for cid in group['case_ids']]) if group['kind'] in {'account', 'permission'} else []
    return [g for g in result if g['affected_case_ids']]


def credential_fields(cases):
    """Use the report's recorded field names, never infer credentials from a provider code."""
    text = '\n'.join(case.get('test_data', '') for case in cases)
    if '邮箱地址' in text and '邮箱授权码' in text:
        return [{'name': 'username', 'label': '邮箱地址'},
                {'name': 'password', 'label': '邮箱授权码', 'credential_type': 'mail_authorization_code'}]
    if '账号邮箱' in text and '个人授权令牌' in text:
        return [{'name': 'username', 'label': '账号邮箱'},
                {'name': 'password', 'label': '个人授权令牌', 'credential_type': 'personal_access_token'}]
    if any(case.get('test_data', '').startswith('授权令牌（必填）') for case in cases):
        return [{'name': 'password', 'label': '授权令牌', 'credential_type': 'access_token'}]
    return [{'name': 'username', 'label': '登录账号'}, {'name': 'password', 'label': '登录密码', 'credential_type': 'password'}]


def case_input_ids(state, report_id, cases):
    bindings = state['bindings'].get(report_id, {})
    groups = {**state.get('group_bindings', {}).get(report_id, {}), **state.get('shared_bindings', {})}
    overrides = state.get('case_overrides', {}).get(report_id, [])
    result = {}
    for case in cases:
        cid = case['case_id']
        ids = [] if cid in overrides else [groups[d['id']] for d in ui_dependencies.case_dependencies(case) if d['id'] in groups]
        if not ids and bindings.get(cid):
            ids.append(bindings[cid])
        result[cid] = list(dict.fromkeys(ids))
    return result


def case_data_status(state, report_id, saved, cases, inputs):
    """Saved data must cover every blocked shared condition, not just one of them."""
    resolved = case_input_ids(state, report_id, cases)
    bindings = {**state.get('group_bindings', {}).get(report_id, {}), **state.get('shared_bindings', {})}
    overrides = set(state.get('case_overrides', {}).get(report_id, []))
    required = {}
    for group in report_groups(saved):
        for cid in group['affected_case_ids']:
            required.setdefault(cid, []).append(group)

    def supplied(group, value):
        if not value:
            return False
        if group['kind'] in {'account', 'permission'}:
            if value['account_mode'] == 'existing_session':
                return True
            if value['account_mode'] != 'credentials':
                return False
            expected = next((f.get('credential_type') for f in group.get('input_fields', []) if f['name'] == 'password'), None)
            return not expected or value['account'].get('credential_type', expected) == expected
        if group['kind'] == 'file':
            return bool(value['files'])
        return bool(value['business_data'] or value['files'])

    result = {}
    for case in cases:
        cid = case['case_id']
        missing = [group['id'] for group in required.get(cid, []) if not (
            any(supplied(group, inputs.get(i)) for i in resolved[cid]) if cid in overrides
            else supplied(group, inputs.get(bindings.get(group['id']))))]
        result[cid] = {'status': 'saved' if resolved[cid] and not missing else 'partial' if resolved[cid] else 'missing',
                       'missing_group_ids': missing}
    return result


def action_confirmation(state, source, report_id, case):
    from .ui_records import required_action
    action = required_action(case)
    origin_id = (case.get('source_report') or {}).get('id') or report_id
    value = state.get('confirmations', {}).get(origin_id, {}).get(case['case_id'])
    if value and value.get('action') == action and value.get('target_url') == source.get('ui_target_url'):
        return value
    # Decisions saved by the old single-case handoff remain usable.
    old = source.get('action_continuation') or {}
    if (action and old.get('report_id') == origin_id and old.get('case_id') == case['case_id']
            and old.get('decision') == ('authorized' if action['type'] == 'authorization' else 'completed')):
        return {**old, 'action': action, 'target_url': source.get('ui_target_url')}
    return None


def confirm_action(store, owner, source, report_id, case, action, decision, actor):
    """Save a report decision without creating or replacing an execution round."""
    with store._lock:
        path, state = _state(store, owner, source['id'])
        value = {'action': action, 'decision': decision, 'decided_at': now(), 'actor': actor,
                 'target_url': source.get('ui_target_url')}
        confirmations = state.setdefault('confirmations', {}).setdefault(report_id, {})
        previous = confirmations.get(case['case_id'])
        if previous and all(previous.get(key) == value.get(key) for key in ('action', 'decision', 'target_url')):
            ui_dependencies.refresh_recovery_summary(store, owner, source['id'], input_state=state)
            return {'decision': decision, 'confirmation': previous, 'saved_only': True, 'reused': True}
        confirmations[case['case_id']] = value
        state['revision'] += 1
        store._write(path, state)
        ui_dependencies.refresh_recovery_summary(store, owner, source['id'], input_state=state)
    return {'decision': decision, 'confirmation': value, 'saved_only': True}


def readiness(store, owner, source, report_id, saved, state, cases, values):
    from . import requirement_design, ui_records
    statuses = case_data_status(state, report_id, saved, cases, values)
    questions = requirement_design.report_questions(store, owner, source['id'], saved)
    result = {}
    for case in cases:
        cid = case['case_id']
        if testing_policy.case_excluded(case):
            result[cid] = {'ready': False, 'excluded': True, 'reasons': [testing_policy.REASON],
                           'confirmation': None, 'resolved_questions': []}
            continue
        related = [q for q in questions['questions'] if cid in q['affected_case_ids']]
        confirmation = action_confirmation(state, source, report_id, case)
        reasons = []
        if ui_records.required_action(case) and not confirmation:
            reasons.append('待确认操作或完成人工步骤')
        if any(q['status'] != 'resolved' for q in related) or (case['status'] == 'pending_rule' and not related):
            reasons.append('待明确规则结论及依据')
        # Existing blocked/not-run input requirements remain; newly selectable
        # failures and partial results need no invented mandatory input.
        needs_data = bool(statuses[cid]['missing_group_ids']) or (
            case['status'] in {'blocked', 'not_run'} and not ui_records.required_action(case))
        if needs_data and statuses[cid]['status'] != 'saved':
            reasons.append('待补充缺失数据或解除阻塞的说明')
        result[cid] = {'ready': case['status'] in ELIGIBLE and not reasons,
                       'reasons': reasons, 'confirmation': confirmation,
                       'resolved_questions': [q for q in related if q['status'] == 'resolved']}
    return result


def view(store, owner, source, report_id, saved=None):
    _, state = _state(store, owner, source['id'])
    saved = saved or report(store, owner, source, report_id)
    cases = _report_cases(saved)
    bindings = state['bindings'].get(report_id, {})
    dep_ids = {d['id'] for c in cases for d in ui_dependencies.case_dependencies(c)}
    group_bindings = {gid: input_id for gid, input_id in
                      {**state.get('group_bindings', {}).get(report_id, {}), **state.get('shared_bindings', {})}.items() if gid in dep_ids}
    resolved = case_input_ids(state, report_id, cases)
    bindings = {**bindings, **{cid: values[-1] for cid, values in resolved.items() if values}}
    ids = set(bindings.values()) | set(group_bindings.values())
    values = {i: _public(_decode(store, state, i)) for i in ids}
    # Profiles may be reused in later reports, only within the same target.
    profiles = [_public(_decode(store, state, i)) for i in state['records']]
    profiles = [p for p in profiles if p['target_url'] == source.get('ui_target_url')][-30:]
    rounds = [p for p in store.list_projects(owner)
              if p.get('execution_round', {}).get('parent_project_id') == source['id']
              and (p.get('ui_retest_round') or {}).get('report_id') == report_id]
    task_source = max(rounds, key=lambda p: p['created_at']) if rounds else source
    task = task_source.get('ui_retest_round') or {}
    task = task if task.get('report_id') == report_id else {}
    latest = next((r for r in task_source.get('analysis_reports', []) if r.get('retest_task_id') == task.get('task_id')), None)
    groups = report_groups(saved)
    overrides = state.get('case_overrides', {}).get(report_id, [])
    for group in groups:
        group['input_id'] = group_bindings.get(group['id'], '')
        group['override_case_ids'] = [cid for cid in group['affected_case_ids'] if cid in overrides]
    return {'revision': state['revision'], 'bindings': bindings, 'group_bindings': group_bindings,
            'groups': groups, 'case_overrides': overrides,
            'case_input_ids': resolved,
            'case_data_status': case_data_status(state, report_id, saved, cases, values),
            'readiness': readiness(store, owner, source, report_id, saved, state, cases, values),
            'inputs': values, 'profiles': profiles,
            'target_url': source.get('ui_target_url', ''), 'task': {**task, 'progress': task_source.get('mcp_progress'),
                                                                 'report_url': latest.get('report_url') if latest else None} if task else None}


def _text(data, key, maximum=500):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f'{key} 必须是文本，最多 {maximum} 字符')
    return value.strip()


def save(store, owner, source, report_id, saved, data):
    ids = data.get('case_ids')
    selection(saved, ids)
    group = next((g for g in report_groups(saved) if g['id'] == data.get('group_id')), None)
    if data.get('group_id'):
        if not group or not set(ids) <= set(group['affected_case_ids']):
            raise ValueError('共同阻塞关联已变更，请刷新后重试')
        ids = group['affected_case_ids']
    with store._lock:
        source = store.get_project(owner, source['id'])
        path, state = _state(store, owner, source['id'])
        if type(data.get('revision')) is not int or data['revision'] != state['revision']:
            raise ValueError('测试数据已更新，请刷新后重试；当前输入不会自动覆盖他人修改')
        old = _decode(store, state, data['reuse_id']) if data.get('reuse_id') else None
        target = source.get('ui_target_url', '')
        if group and group['target_url'] != target:
            raise ValueError('报告中的共同阻塞目标已变更，请在新目标重新检查前置条件')
        if old and old['target_url'] != target:
            raise ValueError('目标页面已变更，请重新填写该目标的测试账号')
        account = data.get('account', {})
        if not isinstance(account, dict):
            raise ValueError('账号信息无效')
        mode = data.get('account_mode', 'none')
        if mode not in {'none', 'credentials', 'existing_session'}:
            raise ValueError('请选择有效的登录方式')
        if group and group['kind'] not in {'account', 'permission'} and mode != 'none':
            raise ValueError('文件、业务数据和服务条件单独共用；账号请补充到账号阻塞或选择仅此用例')
        checked = {k: _text(account, k) for k in ('role', 'username', 'tenant')}
        fields = group['input_fields'] if group and group.get('input_fields') else credential_fields(selection(saved, ids))
        secret_field = next(field for field in fields if field['name'] == 'password')
        credential_type = secret_field['credential_type']
        token_only = not any(field['name'] == 'username' for field in fields)
        if group and group['kind'] in {'account', 'permission'}:
            if mode == 'none' or checked['role'] != group['role'] or checked['tenant'] != group['tenant']:
                raise ValueError('共同账号数据必须与关联用例的角色和租户一致；特殊账号请选择仅此用例')
        password = account.get('password', '')
        if not isinstance(password, str) or len(password) > 4000:
            raise ValueError('密码格式无效')
        if mode == 'credentials':
            if token_only:
                checked['username'] = ''
            elif not checked['username']:
                raise ValueError('请填写登录账号')
            same = old and old['account_mode'] == mode and old['account']['username'] == checked['username'] and old['account']['tenant'] == checked['tenant'] and old['account'].get('credential_type', credential_type) == credential_type
            password = password or (old['account'].get('password', '') if same else '')
            if not password:
                raise ValueError('请填写' + secret_field['label'] + '；更换账号或租户后需重新填写')
        else:
            password = ''
            checked['username'] = ''
            if mode == 'none':
                checked = {k: '' for k in checked}
        files = data.get('files', [])
        if not isinstance(files, list) or len(files) > 5:
            raise ValueError('最多上传 5 个测试文件')
        checked_files, total, uploads = [], 0, []
        for item in files:
            if not isinstance(item, dict):
                raise ValueError('测试文件无效')
            if item.get('id'):
                file = next((f for f in (old or {}).get('files', []) if f['id'] == item['id']), None)
                if not file:
                    raise ValueError('已保存的文件不存在，请重新选择')
                file = copy.deepcopy(file)
            else:
                name = _text(item, 'filename', 200)
                if not name or any(c in name for c in ('/', '\\', '\x00', '\n', '\r')) or name in {'.', '..'}:
                    raise ValueError('测试文件名称无效')
                encoded = item.get('content_base64', '')
                if not isinstance(encoded, str) or len(encoded) > MAX_FILE_BYTES * 4 // 3 + 4:
                    raise ValueError('单个测试文件上限为 10 MB')
                try:
                    content = base64.b64decode(encoded, validate=True)
                except ValueError:
                    raise ValueError('测试文件内容无效') from None
                if len(content) > MAX_FILE_BYTES:
                    raise ValueError('单个测试文件上限为 10 MB')
                file = {'id': str(uuid4()), 'filename': name, 'size': len(content)}
                uploads.append((file['id'], store._cipher.encrypt(content).decode()))
            total += file['size']
            checked_files.append(file)
        if total > MAX_TOTAL_BYTES:
            raise ValueError('测试文件总大小上限为 20 MB')
        if len({f['filename'] for f in checked_files}) != len(checked_files):
            raise ValueError('文件名不能重复，请移除重复的测试文件')
        business = _text(data, 'business_data', 30000)
        if mode == 'none' and not business and not checked_files:
            raise ValueError('请补充登录信息、业务数据或测试文件中的至少一项')
        input_id = str(uuid4())
        value = {'id': input_id, 'target_url': target, 'account_mode': mode,
                 'account': {**checked, 'password': password, 'credential_type': credential_type}, 'business_data': business,
                 'files': checked_files, 'updated_at': now()}
        file_root = store.project_dir(owner, source['id']) / 'retest-files'
        store._mkdir(file_root)
        for file_id, ciphertext in uploads:
            store._write(file_root / file_id, {'ciphertext': ciphertext})
        state['records'][input_id] = store._cipher.encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()
        state['bindings'].setdefault(report_id, {}).update({i: input_id for i in ids})
        overrides = set(state.setdefault('case_overrides', {}).get(report_id, []))
        if group:
            state.setdefault('group_bindings', {}).setdefault(report_id, {})[group['id']] = input_id
            state.setdefault('shared_bindings', {})[group['id']] = input_id
            if not group.get('input_ref') or not set(ids) <= overrides:
                state['shared_bindings'][group.get('resource_id', group['id'])] = input_id
            overrides.difference_update(ids)
        else:
            overrides.update(ids)
        state['case_overrides'][report_id] = sorted(overrides)
        state['revision'] += 1
        store._write(path, state)
        ui_dependencies.refresh_recovery_summary(store, owner, source['id'], input_state=state)
    return view(store, owner, source, report_id, saved)


def unstarted_continuation(store, owner, source, report_project, report_id, ids, record):
    """Recognize a prepared handoff without treating saved execution as idle."""
    continuation = record.get('continuation') or {}
    resume = source.get('requirements_resume') or {}
    if (source['id'] != report_project['id'] or continuation.get('source_report_id') != report_id
            or continuation.get('mode') != 'continue' or resume.get('execution_id') != record['id']
            or not set(ids) <= set(continuation.get('case_ids', []))
            or (source.get('mcp_progress') or {}).get('phase') not in {None, '', 'waiting', 'reading', 'designing', 'reviewing'}):
        return False
    # resume() writes once when it creates the record, then once per preparation
    # event. Any case edit, prerequisite check, checkpoint or added asset adds a
    # separate revision, so even older records can be recognized conservatively.
    if record.get('revision') != 1 + len(record.get('continuation_history', [])):
        return False
    if any(record.get(key) for key in ('report_id', 'dependency_checks', 'dependency_check_history',
                                      'checkpoint_history', 'scene_outcome')):
        return False
    if any(asset.get('inherited_from') != continuation.get('source_execution_id')
           for asset in record.get('assets', [])):
        return False
    # Original business correlations must remain available to a step continuation.
    if any(point.get('correlation') for case in record.get('cases', []) for point in case.get('checkpoints', [])):
        return False
    from .ui_records import root_for
    experiments = root_for(store, owner, source['id'], record['id']) / 'experiments.json'
    return not experiments.exists() or not store._read(experiments).get('items')


def unstarted_retest(store, owner, source, report_project, report_id, record):
    task = source.get('ui_retest_round') or {}
    untouched = (task.get('execution_id') == record['id'] and task.get('report_id') == report_id
            and task.get('report_project_id') == report_project['id']
            and task.get('baseline_revision') == record.get('revision')
            and (source.get('mcp_progress') or {}).get('phase') in {'waiting', 'reading', 'designing', 'reviewing'}
            and not any(record.get(k) for k in ('report_id', 'dependency_checks', 'dependency_check_history',
                                              'checkpoint_history', 'scene_outcome'))
            and all(asset.get('inherited_from') for asset in record.get('assets', []))
            and all(c['status'] == task.get('prepared_case_statuses', {}).get(c['case_id'], 'not_run') for c in record['cases']))
    if not untouched:
        return False
    from .ui_records import root_for
    experiments = root_for(store, owner, source['id'], record['id']) / 'experiments.json'
    return not experiments.exists() or not store._read(experiments).get('items')


def prepare(store, owner, source, report_project, report_id, saved, data):
    from . import ui_rounds
    with store._lock:
        for candidate in store.list_projects(owner):
            info = candidate.get('execution_round', {})
            task = candidate.get('ui_retest_round') or {}
            if (info.get('parent_project_id') == source['id'] and info.get('kind') == 'retest'
                    and task.get('request_id') == data.get('request_id') and task.get('report_id') == report_id
                    and task.get('report_project_id') == report_project['id']):
                if task.get('case_ids') != data.get('case_ids') or task.get('excluded_case_ids', []) != data.get('excluded_case_ids', []):
                    raise ValueError('该补测任务标识已用于其他选项，请重新发起')
                return task
        child = ui_rounds.create(store, owner, source, 'retest')
        try:
            return _prepare(store, owner, child, report_project, report_id, saved, data)
        except Exception:
            ui_rounds.discard(store, owner, child)
            raise


def _prepare(store, owner, source, report_project, report_id, saved, data):
    chosen = selection(saved, data.get('case_ids'))
    with store._lock:
        source = store.get_project(owner, source['id'])
        state_path, state = _state(store, owner, source['id'])
        if type(data.get('revision')) is not int or data['revision'] != state['revision']:
            raise ValueError('测试数据已更新，请刷新后重新发起补测')
        resolved = case_input_ids(state, report_id, chosen)
        values = {i: _public(_decode(store, state, i)) for ids_for_case in resolved.values() for i in ids_for_case}
        statuses = readiness(store, owner, source, report_id, saved, state, chosen, values)
        waiting = [c['case_id'] + '：' + '、'.join(statuses[c['case_id']]['reasons']) for c in chosen if not statuses[c['case_id']]['ready']]
        if waiting:
            raise ValueError('所选用例尚未就绪：' + '；'.join(waiting))
        ids = [c['case_id'] for c in chosen]
        excluded_ids = data.get('excluded_case_ids', [])
        if not isinstance(excluded_ids, list):
            raise ValueError('未纳入补测的用例编号必须是数组')
        excluded = selection(saved, excluded_ids) if excluded_ids else []
        excluded_values = {i: _public(_decode(store, state, i))
                           for ids_for_case in case_input_ids(state, report_id, excluded).values() for i in ids_for_case}
        excluded_statuses = readiness(store, owner, source, report_id, saved, state, excluded, excluded_values)
        if set(ids) & set(excluded_ids) or any(excluded_statuses[c['case_id']]['ready'] for c in excluded):
            raise ValueError('未就绪用例的条件已变化，请刷新后重新发起补测')
        input_ids = {i: resolved[i][-1] for i in ids if resolved[i]}
        for i in {v for values in resolved.values() for v in values}:
            if _decode(store, state, i)['target_url'] != source.get('ui_target_url'):
                raise ValueError('目标页面已变更，请先重新保存测试数据')
        previous = source.get('ui_retest_round') or {}
        if (previous.get('request_id') == data.get('request_id') and previous.get('report_id') == report_id
                and previous.get('case_ids') == ids and previous.get('case_input_ids') == resolved
                and previous.get('excluded_case_ids', []) == excluded_ids
                and previous.get('confirmations', {}) == {cid: statuses[cid]['confirmation'] for cid in ids if statuses[cid]['confirmation']}
                and previous.get('resolved_questions', {}) == {cid: statuses[cid]['resolved_questions'] for cid in ids if statuses[cid]['resolved_questions']}):
            return previous
        if not isinstance(data.get('request_id'), str) or len(data['request_id']) != 36:
            raise ValueError('补测任务标识无效')
        execution_id = source.get('ui_execution_id')
        superseded_execution_id = ''
        if execution_id:
            from .ui_records import root_for
            active_path = root_for(store, owner, source['id'], execution_id) / 'cases.json'
            if active_path.exists():
                active = store._read(active_path)
                if not active.get('report_id'):
                    if not (unstarted_continuation(store, owner, source, report_project, report_id, ids, active)
                            or unstarted_retest(store, owner, source, report_project, report_id, active)):
                        raise ValueError('当前会话仍有未完成的执行，请完成后再发起补测')
                    superseded_execution_id = execution_id
        phase = (source.get('mcp_progress') or {}).get('phase')
        # Document/context reads can leave advisory design progress after a report.
        # Actual unfinished records are protected above; progress alone only
        # blocks an explicitly executing/reporting handoff.
        if phase in {'executing', 'reporting'}:
            raise ValueError('当前会话仍在执行，请完成后再发起补测')
        task = {'task_id': str(uuid4()), 'project_id': source['id'], 'request_id': data['request_id'], 'report_id': report_id,
                'report_project_id': report_project['id'], 'case_ids': ids, 'input_ids': input_ids,
                'case_input_ids': resolved,
                'confirmations': {cid: statuses[cid]['confirmation'] for cid in ids if statuses[cid]['confirmation']},
                'resolved_questions': {cid: statuses[cid]['resolved_questions'] for cid in ids if statuses[cid]['resolved_questions']},
                'excluded_case_ids': excluded_ids,
                'case_overrides': [cid for cid in ids if cid in state.get('case_overrides', {}).get(report_id, [])],
                'dependency_inputs': {},
                'case_dependencies': {c['case_id']: c.get('dependencies', []) for c in chosen}, 'created_at': now()}
        if superseded_execution_id:
            # Keep the prepared record and its inherited evidence intact.
            task['superseded_execution_id'] = superseded_execution_id
        # Older single-case confirmations lived in action_continuation, which
        # batch preparation clears. Retain that explicit decision before switching.
        migrated = False
        for case in chosen:
            confirmation = task['confirmations'].get(case['case_id'])
            origin_id = (case.get('source_report') or {}).get('id') or report_id
            if confirmation:
                decisions = state.setdefault('confirmations', {}).setdefault(origin_id, {})
                if decisions.get(case['case_id']) != confirmation:
                    decisions[case['case_id']] = confirmation
                    migrated = True
        if migrated:
            state['revision'] += 1
            store._write(state_path, state)
        # A deliberately different account/file must not reuse another case's
        # prerequisite check, even when role and tenant labels are identical.
        for case in chosen:
            scoped = []
            for dep in case.get('dependencies', []):
                value = dict(dep)
                if dep['kind'] in {'account', 'permission', 'file', 'data'} and (
                        case['case_id'] in task['case_overrides'] or dep.get('input_ref')) and resolved[case['case_id']]:
                    candidates = [_decode(store, state, i) for i in resolved[case['case_id']]]
                    matching = [v for v in candidates if (v['account_mode'] != 'none' if dep['kind'] in {'account', 'permission'} else bool(v['files']) if dep['kind'] == 'file' else bool(v['business_data']))]
                    value['input_ref'] = (matching or candidates)[-1]['id']
                scoped.extend(ui_dependencies.normalize([value], case, source['ui_target_url']))
            task['case_dependencies'][case['case_id']] = scoped
            for dep in scoped:
                task['dependency_inputs'][dep['id']] = dep.get('input_ref') or state.get('shared_bindings', {}).get(dep['id']) or state.get('group_bindings', {}).get(report_id, {}).get(dep['id'], '')
        baseline = [{**c, 'status': 'not_run', 'actual': '', 'evidence': '', 'executed_at': '',
                     'conclusion': '', 'ai_analysis': '', 'cause_analysis': '', 'recommendation': '', 'cleanup': '', 'action_type': '', 'action_required': '',
                     'rule_basis': c.get('rule_basis') or c.get('code_basis', ''),
                     'method': c.get('method') or c.get('criterion', ''),
                     'not_run_reason': '', 'required_action': None, 'blocked_by': [], 'execution_disposition': '',
                     'dependencies': task['case_dependencies'][c['case_id']],
                     'checkpoints': [{**p, 'status': 'not_run', 'verification_mode': 'design', 'actual': '',
                                      'action_required': '', 'evidence': [], 'correlation': p.get('correlation', {}) if (c['status'] in {'partial', 'pending_action', 'pending_rule'} or any(p.get('status') == 'pending_action' for p in c.get('checkpoints', []))) else {}, 'inherited_from': {}}
                                     for p in c.get('checkpoints', [])]} for c in chosen]
        from . import requirement_design
        for case in baseline:
            for question in statuses[case['case_id']]['resolved_questions']:
                requirement_design.reset_points(case, None if question.get('report_case_ids') else question['id'])
        baseline = redact(store, owner, source['id'], baseline)
        document = (f"# 所选用例统一补测\n\n补测任务 ID：{task['task_id']}\n目标页面：{source['ui_target_url']}\n来源报告：{report_id}\n"
                    f"补测用例：{', '.join(ids)}\n"
                    f"条件尚未就绪、未纳入本轮的用例：{', '.join(excluded_ids) or '无'}。这些用例保留原报告状态，不执行、不记为通过。\n\n"
                    "仅执行所选用例及必要的登录、数据准备和清理步骤；"
                    "复用原用例编号，不执行其他历史用例。核对用户消息中的补测任务 ID，过期任务不得执行；"
                    "先用 get_ui_retest_inputs 携带 task_id 读取专用补充数据，"
                    "核对绑定目标，验证登录与权限。密码不得写入消息、日志、用例、报告或截图。"
                    "用例或检查点带 action_context 时先定位保留的原操作页和业务对象，核对人工操作是否已成功；"
                    "不要仅打开首页或重复创建原对象，现场失效时按已保存的 resume_hint 恢复并说明变化。"
                    "平台已复制并保存本轮未执行基线；用 get_ui_test_cases 直接读取，不重写整份用例。"
                    "保留 cases.dependencies 中的共同前置关联，按 execution_plan 执行。"
                    "每个共同前置条件只轻量检查一次，用 record_ui_dependency_check 记录真实方法与 blocked/ready 结果。"
                    "同一条件仍阻塞时，平台自动标记受影响未执行用例，跳过其业务步骤，不重复登录、上传或触发请求。"
                    "不复用上轮检查结论；数据、目标、角色或租户改变后重新检查，ready 仅放行业务测试，不能记为用例通过。"
                    "测试文件用 get_ui_retest_file 读取并保存到本轮临时文件；原报告已关联的文件仍可复用。"
                    "缺失信息继续记录具体阻塞原因；不得将保存数据当作测试通过。"
                    "完成后在同一会话发布新的补测报告，各轮独立统计，保留原报告。\n\n"
                    "已明确的同组操作在一次浏览器调用中连续执行，异常或未知分支才返回判断；"
                    "使用随包 scripts/execution-batch.cjs 保留结果队列与续跑位置。"
                    "用 save_ui_test_cases 批量提交 case_id 与变化的结果字段，未提供的设计字段自动保留。\n")
        document += ('\n## 已保存的操作确认与规则\n\n'
                     + json.dumps(redact(store, owner, source['id'], {
                         'confirmations': task['confirmations'], 'resolved_questions': task['resolved_questions']}), ensure_ascii=False)
                     + '\n这些确认只说明用户已完成操作或明确规则，不代表测试通过。不得重复索要相同确认；'
                     '先核对原对象与登录状态，保留原订单等关联，不重复提交或付款。'
                     '规则变化先修订对应预期及依据，再验证。验证未完成及待操作用例沿原业务对象继续，'
                     '已完成检查点标注为原轮次继承，不计作本轮重新执行。\n')
        document_path = store.project_dir(owner, source['id']) / 'inputs/current-retest.md'
        previous_document = document_path.read_text() if document_path.exists() else None
        store._write_text(document_path, document)
        updates = {
            'ui_retest_round': task, 'effective_document_file': 'inputs/current-retest.md',
            'effective_filename': 'ui-retest.md', 'ui_execution_id': '', 'action_continuation': {},
            'requirements_resume': {},
            'regression_round': {'source_project_id': source['id'], 'report_id': report_id,
                                 'report_project_id': report_project['id'],
                                 **({'case_sources': {c['case_id']: {'project_id': c['source_report']['project_id'],
                                      'report_id': c['source_report']['id']} for c in chosen}} if report_id == 'total' else {})},
            'task': {'goal': f"仅补测用例 {', '.join(ids)}，检查补充数据并保存独立补测报告。", 'environment': 'auto', 'base_url': ''},
            'status': 'imported', 'last_job': {}}
        store.update_project(owner, source['id'], updates)
        from . import ui_records
        execution_id, revision = '', 0
        try:
            for offset in range(0, len(baseline), 200):
                result = ui_records.save_cases(store, owner, source['id'], baseline[offset:offset + 200], execution_id, revision)
                execution_id, revision = result['execution_id'], result['revision']
            # Continue completed steps only for unfinished business flows. Keep
            # provenance and their real assets, as requirement_design.resume does.
            continuing = {c['case_id']: c for c in chosen if (c['status'] in {'partial', 'pending_action', 'pending_rule'} or any(p.get('status') == 'pending_action' for p in c.get('checkpoints', [])))
                          and any(p['status'] != 'passed' for p in c.get('checkpoints', []))}
            if continuing:
                import shutil
                from . import test_checkpoints
                record = ui_records.load(store, owner, source['id'], execution_id)
                inherited_ids = set()
                for case in record['cases']:
                    original = continuing.get(case['case_id'])
                    if not original:
                        continue
                    origin = original.get('source_report') or {'project_id': report_project['id'], 'id': report_id}
                    historical = saved if report_id != 'total' else report(store, owner, store.get_project(owner, origin['project_id']), origin['id'])
                    old_id = historical.get('ui_snapshot', {}).get('id', '')
                    original_points = {p['id']: p for p in original['checkpoints']}
                    changed = set()
                    questions = statuses[case['case_id']]['resolved_questions']
                    for point in case['checkpoints']:
                        old = original_points[point['id']]
                        affected = any(q.get('report_case_ids') or q['id'] in case.get('question_ids', [])
                                       or q['id'] in point.get('question_ids', []) for q in questions)
                        if affected or set(point.get('depends_on', [])) & changed:
                            changed.add(point['id'])
                        elif old['status'] == 'passed' and old_id:
                            point.update(copy.deepcopy(old))
                            point['inherited_from'] = {'execution_id': old_id, 'report_id': origin['id'],
                                                      'note': '同一业务对象的已完成步骤；本轮没有重复执行'}
                            inherited_ids.add(case['case_id'])
                        elif old['status'] == 'pending_action' and not statuses[case['case_id']]['confirmation']:
                            point.update(copy.deepcopy(old))
                    if case['case_id'] in inherited_ids:
                        old_root = ui_records.root_for(store, owner, origin['project_id'], old_id)
                        new_root = ui_records.root_for(store, owner, source['id'], execution_id)
                        for asset in historical.get('ui_snapshot', {}).get('assets', []):
                            if asset['case_id'] == case['case_id'] and (old_root / asset['id']).is_file():
                                shutil.copyfile(old_root / asset['id'], new_root / asset['id'])
                                record['assets'].append({**asset, 'inherited_from': old_id})
                result = test_checkpoints.write(store, owner, source['id'], record)
                revision = result['revision']
        except Exception:
            store.update_project(owner, source['id'], {k: source.get(k) for k in updates})
            if previous_document is None:
                document_path.unlink(missing_ok=True)
            else:
                store._write_text(document_path, previous_document)
            raise
        task['execution_id'] = execution_id
        task['baseline_revision'] = revision
        task['prepared_case_statuses'] = {c['case_id']: c['status'] for c in ui_records.load(store, owner, source['id'], execution_id)['cases']}
        store.update_project(owner, source['id'], {'ui_retest_round': task})
        from .mcp_progress import record_progress
        record_progress(store, owner, source['id'], 'waiting', '补测任务已准备，等待发送给 Codex')
        return task


def inherit_inputs(store, owner, project, report_id, cases):
    """Carry current retest references into its new report, including exceptions."""
    task = project.get('ui_retest_round') or {}
    if not task:
        return
    with store._lock:
        path, state = _state(store, owner, project['id'])
        state['bindings'][report_id] = task['input_ids']
        group_bindings = {gid: i for gid, i in task.get('dependency_inputs', {}).items() if i}
        resolved = task.get('case_input_ids') or {cid: [i] for cid, i in task['input_ids'].items()}
        # Legacy reports had no dependency metadata. An executor may discover
        # the associations during this round; preserve the supplied account
        # under its actual role/tenant before another group adds file inputs.
        for case in cases:
            candidates = [_decode(store, state, i) for i in resolved.get(case['case_id'], [])]
            for dep in case.get('dependencies', []):
                if dep['id'] in group_bindings or dep['kind'] not in {'account', 'permission'}:
                    continue
                matching = [v for v in candidates if v['account_mode'] != 'none'
                            and v['account']['role'] == dep['role'] and v['account']['tenant'] == dep['tenant']]
                if matching:
                    group_bindings[dep['id']] = matching[-1]['id']
        state.setdefault('group_bindings', {})[report_id] = group_bindings
        state.setdefault('case_overrides', {})[report_id] = task.get('case_overrides', [])
        state['revision'] += 1
        store._write(path, state)
        parent_id = project.get('execution_round', {}).get('parent_project_id')
        if parent_id:
            # Keep report-specific input lineage discoverable from the shared
            # total report, without replacing the parent's current bindings.
            import shutil
            parent_path, parent = _state(store, owner, parent_id)
            used = {i for values in resolved.values() for i in values}
            for input_id in used:
                parent['records'].setdefault(input_id, state['records'][input_id])
                for file in _decode(store, state, input_id)['files']:
                    destination = store.project_dir(owner, parent_id) / 'retest-files' / file['id']
                    if not destination.exists():
                        store._mkdir(destination.parent)
                        shutil.copyfile(store.project_dir(owner, project['id']) / 'retest-files' / file['id'], destination)
            parent['bindings'][report_id] = task['input_ids']
            parent.setdefault('group_bindings', {})[report_id] = group_bindings
            parent.setdefault('case_overrides', {})[report_id] = task.get('case_overrides', [])
            parent['revision'] += 1
            store._write(parent_path, parent)


def execution_inputs(store, owner, project, task_id):
    task = project.get('ui_retest_round') or {}
    if not task_id or task_id != task.get('task_id'):
        raise ValueError('补测任务不存在或已变更，请使用最新的任务消息')
    _, state = _state(store, owner, project['id'])
    resolved = task.get('case_input_ids') or {cid: [i] for cid, i in task.get('input_ids', {}).items()}
    inputs = {i: _decode(store, state, i) for values in resolved.values() for i in values}
    if any(v['target_url'] != project.get('ui_target_url') for v in inputs.values()):
        raise ValueError('目标页面已变更，请重新补充数据并发起补测')
    for value in inputs.values():
        for file in value['files']:
            file.pop('content_base64', None)
    return {'target_url': project.get('ui_target_url'), 'case_inputs': resolved,
            'dependency_inputs': task.get('dependency_inputs', {}), 'inputs': inputs,
            'confirmations': task.get('confirmations', {}), 'resolved_questions': task.get('resolved_questions', {})}


def file_content(store, owner, project, input_id, file_id, task_id):
    task = project.get('ui_retest_round') or {}
    if not task_id or task_id != task.get('task_id'):
        raise ValueError('补测任务不存在或已变更，请使用最新的任务消息')
    resolved = task.get('case_input_ids') or {cid: [i] for cid, i in task.get('input_ids', {}).items()}
    if input_id not in {i for values in resolved.values() for i in values}:
        raise FileNotFoundError('本轮未关联该测试数据')
    _, state = _state(store, owner, project['id'])
    value = _decode(store, state, input_id)
    if value['target_url'] != project.get('ui_target_url'):
        raise ValueError('目标页面已变更，请重新补充数据并发起补测')
    file = next((f for f in value['files'] if f['id'] == file_id), None)
    if not file:
        raise FileNotFoundError('测试文件不存在')
    ciphertext = store._read(store.project_dir(owner, project['id']) / 'retest-files' / file_id)['ciphertext']
    return {**file, 'content_base64': base64.b64encode(store._cipher.decrypt(ciphertext.encode())).decode()}


def redact(store, owner, pid, value):
    _, state = _state(store, owner, pid)
    redactor = Redactor()
    for input_id in state['records']:
        record = _decode(store, state, input_id)
        if record['account'].get('password'):
            redactor.add_secret(record['account']['password'])
        redactor.remember(record.get('business_data', ''))
    return redactor.clean(value)
