"""Deterministic native preparation and closeout, without browser automation.

Embedded in the downloadable client. Receipts, not model-written glue scripts,
carry identity/revision between steps. Unknown writes are never replayed.
"""
import copy
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from api_test_tool.ui_case_scope import active_cases, is_superseded
from api_test_tool.checkpoint_results import reconcile_checkpoint_results, preserve_checkpoint_status_source
from api_test_tool.native_identity import same_executor_ref, native_thread_target
from api_test_tool.ui_payload_validation import require_ui_payload_shape
from api_test_tool.testing_policy import case_excluded


def native_checkpoint_observations(cases, known):
    """Patch/append result observations; explicit designs retain replacement."""
    result = copy.deepcopy(cases)
    observations = {'id', 'status', 'actual', 'method', 'verification_mode', 'evidence',
                    'correlation', 'action_required', 'action_context'}
    for case in result:
        points = case.get('checkpoints')
        old = {p['id']: p for p in known.get(case['case_id'], {}).get('checkpoints', [])}
        if (not isinstance(points, list) or not points or not old
                or 'checkpoint_updates' in case
                or set(case) - {'case_id', 'status', 'actual', 'conclusion', 'ai_analysis', 'checkpoints', 'executed_at', 'not_run_reason'}
                or any(not isinstance(p, dict) or not isinstance(p.get('id'), str)
                       or not {'status', 'actual', 'verification_mode'} <= set(p)
                       or p['status'] == 'not_run' or p['verification_mode'] == 'design'
                       or (p['id'] not in old and not {'title', 'expected'} <= set(p))
                       or (p['id'] in old and any(old[p['id']].get(k) != v
                           for k, v in p.items() if k not in observations))
                       for p in points)):
            continue
        if len({p['id'] for p in points}) != len(points):
            continue  # Keep the server's duplicate-ID rejection authoritative.
        updates = {p['id']: {k: v for k, v in p.items() if k in observations}
                   for p in points if p['id'] in old}
        added = [p for p in points if p['id'] not in old]
        if added:
            case['checkpoints'] = [{**p, **updates.get(pid, {})} for pid, p in old.items()] + added
        else:
            case['checkpoint_updates'] = list(updates.values())
            del case['checkpoints']
    return result


def native_save_readback(receipt, record, known=None):
    """Confirm only an exact next revision and every submitted field; no replay."""
    bound = receipt['binding']
    if (not isinstance(record, dict) or record.get('id') != bound['execution_id']
            or type(record.get('revision')) is not int
            or record['revision'] != receipt['revision_before'] + 1):
        raise ValueError('只读记录未确认原执行 ID 与精确下一修订；原保存仍未知，不重发')
    submitted = receipt.get('request', {}).get('arguments', receipt['payload'])
    if submitted.get('assets'):
        raise ValueError('证据上传需核对原文件回执；不能仅凭用例读回确认保存')

    def matches(expected, actual):
        if isinstance(expected, dict):
            return isinstance(actual, dict) and all(k in actual and matches(v, actual[k]) for k, v in expected.items())
        if isinstance(expected, list):
            return isinstance(actual, list) and len(expected) == len(actual) and all(matches(a, b) for a, b in zip(expected, actual))
        return type(expected) is type(actual) and expected == actual

    # Paged public views retain explicit split originals outside the active list.
    all_cases = list({c['case_id']: c for c in [*record.get('superseded_cases', []),
                                              *record.get('cases', [])]}.values())
    saved = {c['case_id']: c for c in all_cases}
    baselines = receipt.get('case_baselines', known or {})
    for case in submitted.get('cases', []):
        actual = saved.get(case['case_id'], {})
        baseline = baselines.get(case['case_id'], {})
        points = copy.deepcopy(case.get('checkpoints', baseline.get('checkpoints', [])))
        updates = case.get('checkpoint_updates', [])
        if updates:
            by_id = {p['id']: p for p in points}
            if any(p['id'] not in by_id for p in updates):
                raise ValueError('缺少原检查点基线，无法核实局部保存；原保存仍未知')
            for update in updates:
                by_id[update['id']].update(update)
        expected = {k: v for k, v in case.items() if k != 'checkpoint_updates'}
        if points:
            # Storage adds prerequisite diagnostics, never rewrites the model's
            # submitted parent verdict. Compare the complete checkpoint payload.
            original_points = {p['id']: p for p in baseline.get('checkpoints', [])}
            for point in points:
                preserve_checkpoint_status_source(point, original_points.get(point['id'], {}))
                for key, default in (('status', 'not_run'), ('actual', ''), ('verification_mode', 'design'), ('action_required', '')):
                    point.setdefault(key, default)
            candidate = {**copy.deepcopy(baseline), **copy.deepcopy(expected), 'checkpoints': points}
            derived = reconcile_checkpoint_results({
                'cases': [candidate], 'dependency_checks': record.get('dependency_checks', {}),
                'requirement_design': record.get('requirement_design', {})})['cases'][0]
            expected['checkpoints'] = derived['checkpoints']
        elif actual.get('checkpoints') and 'checkpoints' not in case:
            raise ValueError('缺少原检查点基线，无法核实保存结果；原保存仍未知')
        from api_test_tool.testing_policy import annotate_unexecuted
        normalized = {**copy.deepcopy(baseline), **copy.deepcopy(expected)}
        if annotate_unexecuted(normalized):
            expected.update({key: normalized[key] for key in
                             ('status', 'not_run_reason', 'execution_disposition', 'blocked_by', 'executed_at') if key in normalized})
        if not matches(expected, actual):
            raise ValueError('只读记录与提交用例或完整检查点结果不一致；原保存仍未知，不重发')
    coverage = {area['coverage_id']: area for area in record.get('coverage', [])}
    for area in submitted.get('coverage') or []:
        if not matches(area, coverage.get(area['coverage_id'])):
            raise ValueError('只读记录与提交覆盖字段不一致；原保存仍未知，不重发')
    for key in ('review_notes', 'scene_outcome', 'experiment'):
        if key in submitted and submitted[key] is not None and not matches(submitted[key], record.get(key)):
            raise ValueError('只读记录与提交元数据不一致；原保存仍未知，不重发')
    counts = {}
    for case in active_cases(all_cases):
        counts[case['status']] = counts.get(case['status'], 0) + 1
    return {'execution_id': record['id'], 'revision': record['revision'],
            'saved_cases': copy.deepcopy(all_cases), 'coverage': copy.deepcopy(record.get('coverage', [])),
            'execution_plan': {**copy.deepcopy(record.get('execution_plan') or {
                'execution_summary': {'status_counts': counts}, 'refresh_at_resource_boundary': True}),
                'source_revision': record['revision']},
            'confirmation_source': 'platform_record_readback'}


def native_design(source, *, allow_results=False):
    cases = copy.deepcopy(source.get('cases') if isinstance(source, dict) else source)
    if not isinstance(cases, list) or not cases:
        raise ValueError('准备需要明确选定的非空 cases 设计，不能默默缩减范围')
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError('用例必须是对象')
        cid = case.get('case_id')
        if not isinstance(cid, str) or not cid.strip() or cid in seen:
            raise ValueError('用例需要不同的文本 case_id')
        seen.add(cid)
        if 'title' in case:
            if case.get('scenario') and case['scenario'] != case['title']:
                raise ValueError('title 与 scenario 不一致，先核对设计')
            case['scenario'] = case.pop('title')
        for field in ('scenario', 'steps', 'expected'):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError('用例缺少 ' + field)
        if not allow_results and (case.get('status', 'not_run') != 'not_run' or case.get('actual')):
            raise ValueError('新轮准备只接受未执行设计；不可继承历史结果')
        case.setdefault('status', 'not_run')
    return cases


def native_isolated_options(assignment, directory):
    """Automatic for new kits; don't silently migrate a recorded live surface."""
    if assignment.get('browser_mode') == 'cua':
        return None  # Explicit legacy surface; new server tasks reject shared claims.
    if 'direct_browser' in assignment or assignment.get('browser_mode') == 'isolated':
        options = assignment.get('direct_browser') or {}
        if not isinstance(options, dict):
            raise ValueError('direct_browser 必须为环境选项对象')
        return options
    binding_file = Path(directory) / 'binding.json'
    if binding_file.exists():
        binding = json.loads(read_utf8(binding_file))
        if (binding.get('lease_id') and binding.get('account_ids') != []
                and (binding.get('native_context_binding') or {}).get('browser') != 'chromium'):
            return None
    return {}


def native_claim_configuration(assignment):
    """Accept both published claim shapes; never silently choose conflicting facts."""
    outer = assignment.get('claim_arguments') or {}
    if not isinstance(outer, dict) or not isinstance(outer.get('arguments', {}), dict):
        raise ValueError('claim_arguments 及其 arguments 必须为对象')
    for key in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref'):
        if key in outer and (not same_executor_ref(outer[key], assignment.get(key)) if key == 'executor_ref'
                             else outer[key] != assignment.get(key)):
            raise ValueError('领取通知的 %s 与原 assignment 不一致' % key)
    result = {k: copy.deepcopy(v) for k, v in outer.items() if k != 'arguments'}
    for key, value in outer.get('arguments', {}).items():
        if key in result and result[key] != value:
            raise ValueError('领取通知 %s 的内外层值冲突' % key)
        result[key] = copy.deepcopy(value)
    if 'work_token' in assignment:
        if 'work_token' in result and result['work_token'] != assignment['work_token']:
            raise ValueError('领取通知 work_token 与 assignment 阶段冲突')
        result['work_token'] = copy.deepcopy(assignment['work_token'])
    return result


def native_resume(client, assignment_file, directory, notice):
    """Consume the actual notice before environment setup; no model-transcribed token."""
    assignment = json.loads(read_utf8(assignment_file))
    if assignment.get('workspace_url', client.url) != client.url:
        raise ValueError('恢复通知不属于当前测试台')
    if not isinstance(notice, dict):
        raise ValueError('恢复入口需要原通知 claim_arguments 对象')
    claim = notice.get('claim_arguments', notice)
    if not isinstance(claim, dict) or claim.get('action') != 'claim':
        raise ValueError('恢复通知缺少原 claim_arguments')
    for key in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref'):
        if not claim.get(key) or (not same_executor_ref(claim[key], assignment.get(key)) if key == 'executor_ref'
                                 else claim[key] != assignment.get(key)):
            raise ValueError('恢复通知的 %s 与原执行绑定不一致' % key)
    candidate = copy.deepcopy(assignment)
    candidate.pop('work_token', None)
    candidate['claim_arguments'] = claim
    normalized = native_claim_configuration(candidate)
    # Only phase/resource facts come from a notification, never browser metadata.
    candidate['claim_arguments'] = {k: normalized[k] for k in ('work_token', 'account_ids', 'account_selection') if k in normalized}
    ready_path = Path(directory) / 'stage-ready.json'
    ready_path.unlink(missing_ok=True)
    if normalized.get('work_token'):
        result = native_stage_ready(client, assignment_file, directory, assignment=candidate)
    else:
        binding_path = Path(directory) / 'binding.json'
        previous = json.loads(read_utf8(binding_path)) if binding_path.exists() else {}
        if native_claim_configuration(assignment).get('work_token') or previous.get('work_plan'):
            raise ValueError('work_token_missing: 阶段恢复通知缺少 work_token；保留原记录')
        identity = {k: candidate[k] for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')}
        status = client.call('direct_test_session', {**identity, 'action': 'context', 'arguments': {'resume_notice': True}})
        if (status.get('task_id') != identity['task_id'] or status.get('node_id') != identity['node_id']
                or status.get('state') not in {'queued', 'running'} or status.get('authority_revoked')):
            raise ValueError('resume_not_runnable: 原任务已停止、暂停或执行绑定变化')
        available = status.get('state') == 'running' or (status.get('resource_wait') or {}).get('resources_available') is True
        accounts = normalized.get('account_ids') or status.get('account_ids') or []
        if available and accounts:
            candidate.setdefault('direct_browser', {})['context_count'] = len(accounts)
        if available:
            write_private_json(assignment_file, candidate)
        result = {'stage_ready': available, 'end_turn': not available, 'status': status}
    if result.get('excluded'):
        return result
    return {**result, 'next_action': 'environment_setup' if result['stage_ready'] else 'wait_for_resource_event'}


def native_stage_ready(client, assignment_file, directory, *, assignment=None):
    """Check a notified stage once before browser creation, never poll or claim."""
    assignment = copy.deepcopy(assignment) if assignment is not None else json.loads(read_utf8(assignment_file))
    configuration = native_claim_configuration(assignment)
    token = configuration.get('work_token')
    if not token:
        raise ValueError('缺少原阶段通知，不能猜测资源集合')
    identity = {k: assignment[k] for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')}
    path = Path(directory) / 'stage-ready.json'
    if path.exists():
        path.unlink()  # A failed new check cannot leave a usable old allowance.
    result = client.call('direct_test_session', {**identity, 'action': 'context', 'arguments': {'work_token': token}})
    if result.get('work_token') != token:
        raise ValueError('阶段核对回执不属于原通知')
    write_private_json(path, {**result, 'identity': identity})
    if result.get('stage_ready'):
        accounts = result.get('account_ids')
        if not isinstance(accounts, list) or not accounts or result.get('required_context_count') != len(accounts):
            path.unlink()
            raise ValueError('阶段回执没有完整账号集合及环境数量')
        assignment['claim_arguments'] = {**configuration, 'work_token': token, 'account_ids': accounts}
        assignment.setdefault('direct_browser', {})['context_count'] = len(accounts)
        write_private_json(assignment_file, assignment)
    return result


def reconcile_native_prepare(client, binding, *, status=None, claim_configuration=None, claim_request=None):
    """Read the original allocation and full context; never repeat a claim."""
    identity = {k: binding[k] for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref') if binding.get(k)}
    calls = 1
    if status is None:
        calls += 1
        try:
            status = client.call('direct_test_session', {**identity, 'action': 'context'})
        except Exception as error:
            raise ValueError('原领取只读核对未成功，后续步骤已停止；保留原回执，不重放') from error
    changed = bool(binding.get('lease_id') and binding['lease_id'] != status.get('lease_id'))
    if (status.get('task_id') != identity.get('task_id') or status.get('node_id') != identity.get('node_id')
            or status.get('state') != 'running' or not status.get('lease_id') or status.get('authority_revoked')
            or changed and not claim_request):
        raise ValueError('原领取结果尚未确认或已撤权，后续步骤已停止；保留原事实，不重领')
    if claim_request:
        if (claim_request.get('action') != 'claim'
                or any(claim_request.get(k) != identity.get(k) for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id'))
                or not same_executor_ref(claim_request.get('executor_ref'), identity.get('executor_ref'))):
            raise ValueError('原领取请求身份无法确认；保留原回执，不重放')
        original_configuration = {**(claim_request.get('arguments') or {}),
            **({'account_ids': claim_request['account_ids']} if 'account_ids' in claim_request else {})}
        if any(original_configuration.get(k) != (claim_configuration or {}).get(k) for k in
                ('account_ids', 'work_token', 'browser_environment', 'browser_environments', 'native_environment_replacement')):
            raise ValueError('未确认领取的请求条件已变化；先核对原请求，不接入另一组资源或浏览器')
        claim_configuration = original_configuration
    context = client.call('direct_test_session', {**identity, 'action': 'context', 'lease_id': status['lease_id'],
        **({'arguments': {'reconcile_from_lease_id': binding['lease_id']}} if changed else {})})
    node, lease = context.get('node') or {}, context.get('lease') or {}
    dispatch = node.get('executor_dispatch') or {}
    if (node.get('id') != identity['node_id'] or node.get('task_id') != identity['task_id']
            or lease.get('id') != status['lease_id'] or lease.get('node_id') != identity['node_id']
            or lease.get('revoked') or context.get('prior_operations')
            or any(dispatch.get(k) != identity.get(k) for k in ('holder_id', 'dispatch_id'))
            or not same_executor_ref(dispatch.get('executor_ref'), identity['executor_ref'])):
        raise ValueError('原领取绑定/代次/在途操作无法确认，后续步骤已停止，不重放')
    old_context = binding.get('native_context_binding') or {}
    current_context = context.get('native_context_binding') or lease.get('native_context_binding') or {}
    if not changed and old_context and any(old_context.get(k) != current_context.get(k) for k in ('context_id', 'environment_key')):
        raise ValueError('原浏览器环境绑定已变化，后续步骤已停止；先核对原环境')
    claim_configuration = claim_configuration or {}
    token = claim_configuration.get('work_token')
    if token and any((node.get('work_selection') or {}).get(k) != token.get(k)
                     for k in ('work_unit_id', 'plan_revision', 'requirements_digest')):
        raise ValueError('阶段通知与原活动租约不一致；保留原绑定，不重领或继续旧阶段')
    accounts = claim_configuration.get('account_ids')
    if accounts is not None and set(accounts) != set(lease.get('account_ids', [])):
        raise ValueError('阶段完整账号集合与原活动租约不一致；在原资源边界核对')
    if changed:
        project, record = context.get('project') or {}, context.get('record') or {}
        if (context.get('reconciled_from_lease_id') != binding['lease_id']
                or not binding.get('project_id') or not binding.get('execution_id')
                or project.get('id') != binding['project_id'] or record.get('id') != binding['execution_id']
                or project.get('ui_execution_id') != binding['execution_id']):
            raise ValueError('重新领取的原交还与报告绑定未确认；保留旧回执')
        expected = claim_configuration.get('browser_environments')
        if expected is None:
            expected = [claim_configuration['browser_environment']] if claim_configuration.get('browser_environment') else []
        actual = current_context.get('contexts') or ([current_context] if current_context else [])
        # These are the persisted original claim facts, never a later assignment.
        def environment_identity(value):
            from urllib.parse import urlsplit
            url = urlsplit(value.get('origin', ''))
            port = url.port
            target = (url.scheme.lower(), (url.hostname or '').lower(), port if port != {'http': 80, 'https': 443}.get(url.scheme) else None)
            browser = value.get('browser', '').strip().lower()
            browser = {'google chrome': 'chrome', 'microsoft edge': 'edge', 'in-app-browser': 'iab',
                'in_app_browser': 'iab', 'in-app browser': 'iab', 'in app browser': 'iab',
                'codex-iab': 'iab', 'codex in-app browser': 'iab'}.get(browser, browser)
            return (value.get('host_id'), browser, target, value.get('isolation'),
                'shared-profile' if value.get('isolation') == 'shared_profile' else value.get('context_id'),
                value.get('browser_generation', 0))
        if (not expected or len(actual) != len(lease.get('account_ids', []))
                or len({environment_identity(row) for row in actual}) != len(actual)
                or not {environment_identity(row) for row in actual} <= {environment_identity(row) for row in expected}):
            raise ValueError('重新领取的浏览器环境与原请求不一致；保留原回执，不继续业务')
    return {'claim': status, 'context': context, 'http_calls': calls}


def prepare_native(client, assignment, source, directory, *, resume=False):
    cases = native_design(source, allow_results=resume)  # Validate local shape before claiming.
    inventory = copy.deepcopy(source.get('coverage')) if isinstance(source, dict) else None
    if inventory is not None and not isinstance(inventory, list):
        raise ValueError('coverage 必须为功能覆盖清单')
    require_ui_payload_shape({'cases': cases, 'coverage': inventory})
    required = ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')
    if not isinstance(assignment, dict) or any(not assignment.get(k) for k in required):
        raise ValueError('assignment 缺少原任务、节点或执行会话绑定')
    if assignment.get('workspace_url', client.url) != client.url:
        raise ValueError('assignment 不属于当前测试台')
    assignment = {**assignment, 'claim_arguments': native_claim_configuration(assignment)}
    identity = {k: assignment[k] for k in (*required, 'coordinator_ref') if k in assignment}
    fingerprint = hashlib.sha256(json.dumps([client.url, identity, cases, inventory], sort_keys=True,
                                           ensure_ascii=False).encode()).hexdigest()
    root = Path(directory).absolute()
    if root.is_symlink():
        raise ValueError('准备目录不能为符号链接')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    environment = None
    if native_isolated_options(assignment, root) is not None:
        # Only the direct browser helper writes this after creating real
        # contexts. Loading metadata does not launch or proxy a browser.
        environment = json.loads(read_utf8(root / 'browser-environment.json'))
        if (environment.get('state') != 'open' or environment.get('browser_tool') != 'node_repl'
                or any(environment.get('identity', {}).get(k) != identity[k]
                       for k in ('task_id', 'node_id', 'holder_id'))
                or not same_executor_ref(environment.get('identity', {}).get('executor_ref'), identity['executor_ref'])
                or not environment.get('environments')):
            raise ValueError('直接浏览器尚未创建或不属于原执行者；不领取账号、不继续后续步骤')
        assignment = copy.deepcopy(assignment)
        claim_configuration = assignment.setdefault('claim_arguments', {})
        claim_configuration.pop('browser_environment', None)
        claim_configuration['browser_environments'] = environment['environments']
        assignment.pop('browser_environment', None)
    ledger = root / 'preparation.json'
    with batch_lock(ledger):
        binding_file = root / 'binding.json'
        previous = json.loads(read_utf8(binding_file)) if binding_file.exists() else {}
        reconciliation_calls = 0
        if resume:
            if previous and (any(previous.get(k) != identity[k] for k in
                                ('task_id', 'node_id', 'holder_id'))
                             or not same_executor_ref(previous.get('executor_ref'), identity['executor_ref'])):
                raise ValueError('恢复必须沿原任务、节点、持有人及执行会话绑定')
            if previous.get('workspace_url', client.url) != client.url:
                raise ValueError('原绑定不属于当前测试台')
            anchor = assignment.get('resume_record') or {}
            if previous.get('execution_id') and any(anchor.get(k, previous.get(k)) != previous.get(k)
                                                   for k in ('project_id', 'execution_id')):
                raise ValueError('恢复指定记录与原绑定不一致')
            review_receipt = (previous.get('final_review') or {}).get('receipt_file')
            known_receipts = {Path(review_receipt).resolve()} if isinstance(review_receipt, str) and review_receipt else set()
            receipt_paths = {p.resolve() for p in root.glob('*.json')} | known_receipts
            for receipt_path in sorted(receipt_paths):
                known_receipt = receipt_path.name.startswith('receipt') or receipt_path.resolve() in known_receipts
                try:
                    receipt = json.loads(read_utf8(receipt_path))
                except (ValueError, OSError):
                    if known_receipt:
                        raise ValueError('原保存回执无法读取：%s；核对原回执，不重放业务' % receipt_path.name) from None
                    # The private directory also holds fixtures, reports and
                    # shell stdout files (created empty before prepare starts).
                    # These are not evidence of an uncertain platform write.
                    continue
                if (isinstance(receipt, dict) and receipt.get('state') in {'pending', 'unknown', 'rejected'}
                        and (known_receipt
                             or ('binding' in receipt and 'payload' in receipt))):
                    if not isinstance(receipt.get('payload'), dict) or not receipt.get('fingerprint'):
                        raise ValueError('原观察保存未确认；核对原回执，不重放业务或继续准备')
                    reconciled = client.native_record(binding_file, receipt['payload'], receipt_path)
                    reconciliation_calls += reconciled.get('client_timing', {}).get('http_calls', 0)
                    previous = json.loads(read_utf8(binding_file))
            marker = root / 'observation-pending.json'
            clear_rejected_native_observation(root, previous)
            if marker.exists():
                observation = json.loads(read_utf8(marker))
                path = observation.get('receipt_file')
                receipt = json.loads(read_utf8(path)) if path and Path(path).exists() else {}
                if not native_pending_receipt_matches(observation, receipt, previous, client=client):
                    raise ValueError('原观察保存未确认；核对原回执，不重放业务或继续准备')
                marker.unlink()
        state = json.loads(read_utf8(ledger)) if ledger.exists() else {
            'fingerprint': fingerprint, 'state': 'new', 'stages': {}}
        legacy_fingerprint = hashlib.sha256(json.dumps([client.url, identity, cases], sort_keys=True,
            ensure_ascii=False).encode()).hexdigest() if inventory is None else None
        if state.get('fingerprint') not in {fingerprint, legacy_fingerprint} and not (resume and previous):
            raise ValueError('准备目录属于其他任务或设计；不能覆盖原观察')
        recovered = {}
        expected_claim = {**(assignment.get('claim_arguments') or {})}
        if 'work_token' in assignment and 'work_token' not in expected_claim:
            expected_claim['work_token'] = assignment['work_token']
        if state['state'] == 'ready' and resume and previous.get('work_plan'):
            status = client.call('direct_test_session', {**identity, 'action':'context'})
            reconciliation_calls += 1
            if status.get('lease_id'):
                recovered = reconcile_native_prepare(client, {**identity, **previous}, status=status,
                                                     claim_configuration=expected_claim)
                reconciliation_calls += recovered['http_calls']
        if state['state'] in {'pending', 'failed'} and state.get('claim_outcome') == 'rejected' and state.get('stage') == 'claim' and resume:
            state.setdefault('recovery_history', []).append({'stage': 'claim', 'original_state': state['state'],
                'outcome': 'rejected', 'at': datetime.now(timezone.utc).isoformat()})
            state['state'] = 'new'
        if state['state'] in {'pending', 'failed'}:
            if not resume:
                raise ValueError('准备在 %s 未成功，后续步骤已停止；保留原回执，核对原状态，不重放写入' % state.get('stage'))
            recovered = reconcile_native_prepare(client, {**identity, **previous}, claim_configuration=expected_claim,
                claim_request=state.get('stages', {}).get('claim', {}).get('request')
                if state.get('stage') == 'claim' and state.get('claim_outcome') == 'unknown' else None)
            reconciliation_calls += recovered['http_calls']
            recovered_record = recovered['context'].get('record')
            if state.get('stage') == 'baseline':
                payload = state['stages']['baseline'].get('request')
                baseline = state['stages']['baseline']
                failed_response = (state.get('baseline_outcome') == 'rejected'
                    or type(baseline.get('http_status')) is int and 400 <= baseline['http_status'] < 500)
                absent = ('record' in recovered['context'] and recovered_record is None
                          and not recovered['context']['project'].get('ui_execution_id'))
                if (not payload or recovered['context']['project']['id'] != payload.get('project_id')
                        or not recovered_record and not (failed_response and absent)):
                    raise ValueError('原基线保存仍未知，后续步骤已停止；不重发基线')
                if recovered_record:
                    confirmed = native_save_readback({'binding': {'execution_id': recovered_record['id']},
                        'revision_before': 0, 'payload': payload}, recovered_record)
                    previous.update(project_id=recovered['context']['project']['id'],
                                    execution_id=confirmed['execution_id'], revision=confirmed['revision'])
                    state['baseline_outcome'] = 'confirmed'
                else:
                    state['baseline_outcome'] = 'rejected'
                    baseline['rejection_confirmed'] = {'source': 'original_context_readback',
                        'project_id': recovered['context']['project']['id'], 'record_absent': True,
                        'checked_at': datetime.now(timezone.utc).isoformat()}
            state.setdefault('recovery_history', []).append({'stage': state.get('stage'),
                'original_state': state['state'], 'lease_id': recovered['claim']['lease_id'],
                **({'outcome': 'rejected', 'request': copy.deepcopy(payload),
                    'http_status': state['stages']['baseline'].get('http_status')}
                   if state.get('stage') == 'baseline' and state.get('baseline_outcome') == 'rejected' else {}),
                'at': datetime.now(timezone.utc).isoformat()})
            write_private_json(ledger, state)
        def reused_ready(calls):
            # The preparation receipt describes the original baseline. The
            # successful result receipt owns current revision/checkpoints.
            binding = json.loads(read_utf8(root / 'binding.json'))
            known = binding.get('case_results') or {}
            ready = state['ready']
            return {**ready, 'revision': binding['revision'], 'reused': True, 'http_calls': calls,
                    'coverage': copy.deepcopy(binding.get('coverage', ready.get('coverage', []))),
                    **({'native_context_binding': binding['native_context_binding']}
                       if binding.get('native_context_binding') else {}),
                    'cases': [*[{**case, **known.get(case['case_id'], {})} for case in ready['cases']],
                              *[case for cid, case in known.items() if cid not in {c['case_id'] for c in ready['cases']}]]}
        # One explicit lifecycle repair after verified exit. Ordinary reconnects
        # retain the profile/context ID and do not call the platform at all.
        replacement_calls = 0
        replacement = assignment.get('replace_exited_environment')
        if replacement and previous.get('lease_id'):
            if environment is None:
                raise ValueError('环境替换只用于原节点的真实隔离环境')
            if not isinstance(replacement, dict):
                raise ValueError('replace_exited_environment 必须为原退出依据')
            request = {**replacement, 'browser_environments': environment['environments']}
            if resume:
                # The claim transaction distinguishes an active original lease
                # from an ended lease; never checkpoint the ended one first.
                assignment.setdefault('claim_arguments', {})['native_environment_replacement'] = {
                    **request, 'lease_id': previous['lease_id']}
            else:
                repair = client.call('direct_test_session', {**identity, 'action': 'checkpoint',
                    'lease_id': previous['lease_id'], 'checkpoint': {'native_environment_replacement': request}})
                replacement_calls = 1
                previous['native_context_binding'] = repair['native_context_binding']
                write_private_json(binding_file, previous)
                write_private_json(root / 'environment-replacement.json', repair)
        if state['state'] == 'ready' and not resume:
            return reused_ready(replacement_calls + reconciliation_calls)
        if state['state'] == 'waiting' and not resume:
            return {'state': 'waiting', 'ready': False, 'end_turn': True, 'http_calls': 0}
        if state['state'] == 'stopped' and not resume:
            return {'state': 'stopped', 'ready': False, 'end_turn': True, 'http_calls': 0}
        started = time.monotonic()
        calls = reconciliation_calls

        def step(name, tool, args):
            nonlocal calls
            if name in recovered:
                response = recovered[name]
                write_private_json(root / (name + '.json'), response)
                return response
            state.update(state='pending', stage=name)
            if name in {'claim', 'baseline'}:
                state[name + '_outcome'] = 'unknown'
            state['stages'][name] = {'started_at': datetime.now(timezone.utc).isoformat(), 'request': copy.deepcopy(args)}
            write_private_json(ledger, state)
            begin = time.monotonic()
            try:
                calls += 1
                response = client.call(tool, args)
                write_private_json(root / (name + '.json'), response)
            except Exception as error:
                state.update(state='failed', error_type=type(error).__name__, error=str(error))
                if name in {'claim', 'baseline'} and getattr(error, 'status', None) in {400, 401, 403, 404, 409, 422}:
                    # Baseline persistence has post-write reporting work. A
                    # failed HTTP response alone cannot establish no write.
                    state[name + '_outcome'] = 'rejected' if name == 'claim' else 'unknown'
                    state['stages'][name]['http_status'] = error.status
                write_private_json(ledger, state)
                raise
            if name in {'claim', 'baseline'}:
                state[name + '_outcome'] = 'confirmed'
            state['stages'][name].update(finished_at=datetime.now(timezone.utc).isoformat(),
                                         seconds=round(time.monotonic() - begin, 3))
            return response

        claim_args = {**identity, 'action': 'claim'}
        claim_configuration = assignment.get('claim_arguments') or {}
        account_ids = claim_configuration.get('account_ids')
        if account_ids is not None:
            claim_args['account_ids'] = account_ids
        environments = {key: copy.deepcopy(claim_configuration.get(key, assignment.get(key)))
                        for key in ('browser_environment', 'browser_environments', 'native_environment_replacement', 'account_selection', 'work_token')
                        if key in claim_configuration or key in assignment}
        if environments:
            claim_args['arguments'] = environments
        claim = step('claim', 'direct_test_session', claim_args)
        if not claim.get('lease_id') or claim.get('state') != 'running':
            waiting = claim.get('state') in {'queued', 'waiting'}
            state['state'] = 'waiting' if waiting else 'stopped'
            write_private_json(ledger, state)
            return {'state': state['state'], 'ready': False, 'end_turn': True,
                    'http_calls': calls, 'receipt_file': str(root / 'claim.json')}
        changed_lease = bool(previous.get('lease_id') and previous['lease_id'] != claim['lease_id'])
        if changed_lease and not resume:
            raise ValueError('续接租约已变化；保留原准备和观察，先核对原任务')
        binding = {**({} if changed_lease else previous), **identity,
                   'workspace_url': client.url, 'lease_id': claim['lease_id']}
        if 'account_ids' in claim:
            binding['account_ids'] = list(claim['account_ids'])
        if claim.get('native_context_binding'):
            binding['native_context_binding'] = copy.deepcopy(claim['native_context_binding'])
        if claim_configuration.get('work_token'):
            binding['work_token'] = copy.deepcopy(claim_configuration['work_token'])
        recovered_node = (recovered.get('context') or {}).get('node') or {}
        if recovered_node.get('checkpoint', {}).get('work_plan'):
            binding['work_plan'] = copy.deepcopy(recovered_node['checkpoint']['work_plan'])
            selection = recovered_node.get('work_selection')
            if selection:
                binding['work_token'] = {k: selection[k] for k in ('work_unit_id', 'plan_revision', 'requirements_digest')}
        if changed_lease:
            binding['previous_bindings'] = [*previous.get('previous_bindings', []),
                {k: copy.deepcopy(v) for k, v in previous.items() if k != 'previous_bindings'}]
        write_private_json(binding_file, binding)  # Cleanup remains possible after any later failure.
        if state.get('ready') and not changed_lease:
            state['state'] = 'ready'
            write_private_json(ledger, state)
            return reused_ready(calls)
        context = step('context', 'direct_test_session', {**identity, 'action': 'context', 'lease_id': claim['lease_id']})
        if context.get('mode') != 'native_browser' or not (context.get('project') or {}).get('id'):
            raise ValueError('当前上下文不可执行；后续基线和业务已停止')
        if context.get('native_context_binding'):
            binding['native_context_binding'] = copy.deepcopy(context['native_context_binding'])
        if (context.get('node') or {}).get('checkpoint', {}).get('work_plan'):
            binding['work_plan'] = copy.deepcopy(context['node']['checkpoint']['work_plan'])
        if context.get('record') and resume:
            anchor = assignment.get('resume_record') or previous
            project, record = context['project'], context['record']
            node, lease = context.get('node') or {}, context.get('lease') or {}
            dispatch = node.get('executor_dispatch') or {}
            if (not anchor.get('project_id') or not anchor.get('execution_id')
                    or project['id'] != anchor['project_id']
                    or record.get('id') != anchor['execution_id']
                    or project.get('ui_execution_id') != anchor['execution_id']
                    or node.get('id') != identity['node_id'] or node.get('task_id') != identity['task_id']
                    or lease.get('id') != claim['lease_id'] or lease.get('node_id') != identity['node_id']
                    or any(dispatch.get(k) != identity[k] for k in ('holder_id', 'dispatch_id'))
                    or not same_executor_ref(dispatch.get('executor_ref'), identity['executor_ref'])
                    or type(record.get('revision')) is not int or record['revision'] < 1):
                raise ValueError('恢复上下文与原任务、执行会话或执行记录不一致；不能接入其他记录')
            if context.get('prior_operations'):
                raise ValueError('原操作仍有未知或待确认结果；先核对原操作，不重放业务')
            prepared = native_design({'cases': record.get('cases')}, allow_results=True)
            counts = {}
            for case in active_cases(prepared):
                counts[case['status']] = counts.get(case['status'], 0) + 1
            binding.update(project_id=project['id'], execution_id=record['id'], revision=record['revision'],
                           case_counts=counts, case_results={c['case_id']: c for c in prepared},
                           coverage=copy.deepcopy(record.get('coverage', [])))
            write_private_json(binding_file, binding)
            if (root / 'design.json').exists():
                history = state.setdefault('resume_history', [])
                history.append({'ready': copy.deepcopy(state.get('ready')),
                                'design': json.loads(read_utf8(root / 'design.json'))})
            write_private_json(root / 'design.json', {'cases': prepared,
                **{key: copy.deepcopy(record[key]) for key in
                   ('coverage', 'review_notes', 'review_revision', 'requirement_design') if key in record},
                'resumed_execution_id': record['id']})
            ready = {'state': 'ready', 'ready': True, 'resumed': True, 'binding_file': str(binding_file),
                     'design_file': str(root / 'design.json'), 'project_id': project['id'],
                     'execution_id': record['id'], 'revision': record['revision'], 'cases': prepared,
                     'coverage': binding['coverage'],
                     **({'native_context_binding': binding['native_context_binding']}
                        if binding.get('native_context_binding') else {}),
                     'accounts': [{key: account.get(key) for key in ('id', 'label', 'identity', 'tenant')}
                                  for account in context.get('accounts', [])],
                     'http_calls': calls, 'seconds': round(time.monotonic() - started, 3)}
            state.update(state='ready', ready=ready, fingerprint=fingerprint)
            write_private_json(ledger, state)
            return ready
        if context.get('record'):
            raise ValueError('已有执行记录，不能以新基线覆盖；沿原回执恢复')
        if resume and (assignment.get('resume_record') or previous.get('execution_id')):
            raise ValueError('原执行记录不可用；不能以新基线代替原轮次')
        pid = context['project']['id']
        prefix = context['case_id_prefix']
        id_map = {case['case_id']: prefix + str(index + 1).zfill(3) for index, case in enumerate(cases)}
        # Keep dependency structures intact. Rewrite only exact selected case IDs.
        def remap(value):
            if isinstance(value, dict): return {k: remap(v) for k, v in value.items()}
            if isinstance(value, list): return [remap(v) for v in value]
            return id_map.get(value, value) if isinstance(value, str) else value
        prepared = remap(cases)
        for case in prepared:
            check_case_batch([case])
        prepared_inventory = remap(inventory) if inventory is not None else []
        saved = step('baseline', 'save_ui_test_cases', {'project_id': pid, 'cases': prepared,
            **({'coverage': prepared_inventory} if inventory is not None else {}), 'response': 'summary'})
        if not saved.get('execution_id') or type(saved.get('revision')) is not int:
            raise ValueError('基线未返回有效执行记录；不生成可执行业务状态')
        binding.update(project_id=pid, execution_id=saved['execution_id'], revision=saved['revision'],
                       coverage=prepared_inventory, case_results={c['case_id']: c for c in prepared},
                       coverage_check=saved.get('coverage_check', {}))
        write_private_json(binding_file, binding)
        write_private_json(root / 'design.json', {'cases': prepared, 'coverage': prepared_inventory, 'source_case_ids': id_map})
        ready = {'state': 'ready', 'ready': True, 'binding_file': str(binding_file),
                 'design_file': str(root / 'design.json'), 'project_id': pid,
                 'execution_id': saved['execution_id'], 'revision': saved['revision'],
                 **({'native_context_binding': binding['native_context_binding']}
                    if binding.get('native_context_binding') else {}),
                 'accounts': [{key: account.get(key) for key in ('id', 'label', 'identity', 'tenant')}
                              for account in context.get('accounts', [])],
                 'cases': prepared, 'coverage': prepared_inventory,
                 'baseline_receipt': saved, 'http_calls': calls, 'seconds': round(time.monotonic() - started, 3)}
        state.update(state='ready', ready=ready)
        write_private_json(ledger, state)
        return ready


def native_pending_receipt_matches(pending, receipt, binding, *, request_id=None, client=None):
    fields = ('task_id', 'node_id', 'holder_id', 'lease_id', 'project_id', 'execution_id')
    if request_id is not None and pending.get('request_id', request_id) != request_id:
        return False
    if any(receipt.get('binding', {}).get(key) != binding.get(key) for key in fields):
        return False
    if pending.get('binding') and any(pending['binding'].get(key) != binding.get(key) for key in fields):
        return False
    expected = pending.get('payload') or {'cases': [{key: pending.get(key) for key in ('case_id', 'status', 'actual')}]}
    if 'asset_files' in expected:
        if client is None:
            return False
        try:
            expected = {**expected, 'assets': [client.asset_from_file(**{key: item[key] for key in
                ('file', 'case_id', 'step', 'kind', 'captured_at', 'filename', 'content_type') if key in item})
                for item in expected['asset_files']]}
            expected.pop('asset_files')
        except (ValueError, OSError):
            return False
    result = receipt.get('result') or {}
    before = receipt.get('revision_before')
    return (receipt.get('state') == 'saved' and receipt.get('payload') == expected
            and type(before) is int and type(result.get('revision')) is int
            and result['revision'] == before + 1 and result.get('execution_id') == binding.get('execution_id')
            and result['revision'] <= binding.get('revision', 0))


def native_rejection_proof_matches(proof, binding, fingerprint):
    return (isinstance(proof, dict) and proof.get('source') == 'platform_record_readback'
            and proof.get('fingerprint') == fingerprint and bool(fingerprint)
            and proof.get('execution_id') == binding.get('execution_id')
            and type(proof.get('revision')) is int and type(binding.get('revision')) is int
            and proof['revision'] <= binding['revision'])


def native_rejection_confirmed(receipt, binding):
    """Only an authenticated unchanged revision proves a failed POST did not save."""
    try:
        identity = {k: receipt[k] for k in ('workspace_url', 'binding', 'payload')}
        fields = ('holder_id', 'task_id', 'node_id', 'lease_id', 'project_id', 'execution_id')
        proof = receipt.get('rejection_confirmed')
        return (receipt.get('state') == 'rejected'
            and type(receipt.get('http_status')) is int and 400 <= receipt['http_status'] < 500
            and identity['workspace_url'] == binding.get('workspace_url')
            and all(receipt['binding'].get(k) == binding.get(k) for k in fields)
            and receipt.get('fingerprint') == hashlib.sha256(json.dumps(
                identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            and native_rejection_proof_matches(proof, binding, receipt['fingerprint'])
            and proof['revision'] == receipt.get('revision_before'))
    except (KeyError, TypeError, ValueError):
        return False


def native_final_review_unconfirmed(binding):
    review = binding.get('final_review') or {}
    return (review.get('state') in {'pending', 'unknown'}
        or review.get('state') == 'rejected' and not native_rejection_proof_matches(
            review.get('rejection_confirmed'), binding, review.get('fingerprint')))


def native_observation_settled(root, response, binding):
    if response.get('saved') is True or response.get('state') == 'not_sent':
        return True
    if response.get('state') != 'rejected' or not response.get('record_receipt_file'):
        return False
    try:
        receipt = json.loads(read_utf8(Path(response['record_receipt_file'])))
    except (ValueError, OSError):
        return False
    return native_rejection_confirmed(receipt, binding)


def clear_rejected_native_observation(root, binding):
    """A proved rejected request did not write; retain its receipt, clear only its fence."""
    marker = Path(root) / 'observation-pending.json'
    if not marker.exists():
        return False
    try:
        pending = json.loads(read_utf8(marker))
        receipt = json.loads(read_utf8(Path(pending['receipt_file'])))
        cases = receipt['payload'].get('cases', [])
        if (not native_rejection_confirmed(receipt, binding)
                or not any(all(case.get(k) == pending.get(k) for k in ('case_id', 'status', 'actual')) for case in cases)):
            return False
    except (KeyError, TypeError, ValueError, OSError):
        return False
    marker.unlink()
    return True


def observed_native(client, binding_file, case_id, status, actual, receipt_file, *, details=None, asset_files=None, request_id=None):
    if status not in {'passed', 'failed', 'partial', 'blocked', 'pending_action', 'pending_rule'}:
        raise ValueError('必须提供真实判定，不从动作成功猜测通过')
    if not isinstance(actual, str):
        raise ValueError('实际观察必须为文本')
    design = json.loads(read_utf8(Path(binding_file).parent / 'design.json'))
    if case_id not in {c['case_id'] for c in design['cases']}:
        raise ValueError('结果不属于本轮已准备设计')
    state = json.loads(read_utf8(Path(binding_file).parent / 'preparation.json'))
    if state.get('state') != 'ready':
        raise ValueError('准备未完成，不能继续保存业务结果')
    marker = Path(binding_file).parent / 'observation-pending.json'
    binding = json.loads(read_utf8(binding_file))
    clear_rejected_native_observation(marker.parent, binding)
    if details is not None and (not isinstance(details, dict) or {'case_id', 'status', 'actual'} & set(details)):
        raise ValueError('case_changes 仅包含本条用例的显式变化，身份、判定及实际观察沿用原观察')
    changes = {**(details or {}), 'case_id': case_id, 'status': status, 'actual': actual}
    content = {'cases': [changes], **({'asset_files': asset_files} if asset_files is not None else {})}
    current = {'case_id': case_id, 'status': status, 'actual': actual,
               'receipt_file': str(Path(receipt_file).absolute())}
    if request_id is not None:
        current['request_id'] = request_id
    if details or asset_files is not None:
        current['payload'] = content
    if marker.exists() and json.loads(read_utf8(marker)) != current:
        raise ValueError('前条结果未确认保存，后续步骤已停止；先核对原回执')
    write_private_json(marker, current)
    # Preserve supplied steps/checkpoints/evidence at the observation boundary.
    # The normal case and asset validators remain authoritative.
    try:
        result = client.native_record(binding_file, content, receipt_file)
        if result.get('saved') is False:
            raise ValueError('原请求已核实未保存；保留拒绝回执，修正后使用新回执补交，不重跑业务')
    except Exception as error:
        if clear_rejected_native_observation(marker.parent, binding):
            error.native_receipt_state = 'rejected'
            error.native_receipt_file = str(receipt_file)
        elif (type(error) is ValueError and not Path(receipt_file).exists()
                and json.loads(read_utf8(marker)) == current):
            marker.unlink()
            error.native_receipt_state = 'not_sent'
        raise
    marker.unlink()
    return result


def observation_actual(observation):
    """Render observations captured at the assertion boundary, without an LLM rewrite."""
    if not isinstance(observation, dict):
        raise ValueError('观察必须为对象')
    checks = observation.get('checks')
    if not isinstance(checks, list) or not checks:
        raise ValueError('缺少实际逐项观察 checks')
    lines = []
    for check in checks:
        if (not isinstance(check, dict) or not isinstance(check.get('name'), str)
                or not check['name'].strip() or 'expected' not in check or 'observed' not in check
                or type(check.get('ok')) is not bool):
            raise ValueError('检查项需要 name/expected/observed/ok；不猜测判定')
        lines.append(json.dumps(check, ensure_ascii=False, allow_nan=False))
    return '\n'.join(lines)


def observed_native_json(client, binding_file, observation, observation_file, receipt_file, *, request_id=None):
    # An incomplete case can later advance. Keep each real observation immutable;
    # equal observations retain their original receipt, unknown saves still fence the next one.
    payload = json.dumps(observation, sort_keys=True, ensure_ascii=False, allow_nan=False)
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    source, receipt = Path(observation_file), Path(receipt_file)
    protected = {Path(binding_file).resolve(), *(Path(binding_file).parent.joinpath(name).resolve()
                  for name in ('design.json', 'preparation.json', 'observation-pending.json'))}
    if source.resolve() in protected or receipt.resolve() in protected or source.resolve() == receipt.resolve():
        raise ValueError('观察与回执不能覆盖原绑定、设计或相互覆盖')
    source = source.with_name(source.stem + '-' + digest + source.suffix)
    receipt = receipt.with_name(receipt.stem + '-' + digest + receipt.suffix)
    if source.exists() and json.loads(read_utf8(source)) != observation:
        raise ValueError('已有不同观察，不覆盖或重跑')
    write_private_json(source, observation)
    actual = observation_actual(observation)
    result = observed_native(client, binding_file, observation.get('case_id'), observation.get('status'), actual, receipt,
        details=observation.get('case_changes'), asset_files=observation.get('asset_files'), request_id=request_id)
    return {**result, 'observation_file': str(source), 'receipt_file': str(receipt)}


def native_closeout_arguments(binding, *, browser_stopped, reason, save_unconfirmed=False, defer_report=False, outcome='completed'):
    if outcome not in {'completed', 'yield'}:
        raise ValueError('收尾 outcome 必须为 completed 或 yield')
    if browser_stopped is not True or not isinstance(reason, str) or not reason.strip():
        raise ValueError('必须在实际关闭本任务页面后明确 browser-stopped 和退出依据')
    fields = ('holder_id', 'task_id', 'node_id', 'lease_id')
    if any(not isinstance(binding.get(k), str) or not binding[k] for k in fields):
        raise ValueError('缺少原领取绑定，不能构造交还请求')
    save_unconfirmed = save_unconfirmed or native_final_review_unconfirmed(binding)
    counts = binding.get('case_counts') or {}
    result = ('partial' if save_unconfirmed else 'failed' if counts.get('failed') else 'passed' if counts.get('passed') and
              sum(counts.values()) == counts['passed'] else 'partial')
    publish = outcome == 'completed' and not (save_unconfirmed or defer_report)
    return {**{k: binding[k] for k in (*fields, 'dispatch_id', 'executor_ref') if k in binding},
            'action': 'finish', 'outcome': outcome,
            'reason': reason, 'arguments': {'browser_stopped': True, 'result': result,
                                           # Passing the registered cases does not prove all module branches were explored.
                                           'coverage_complete': False, 'publish_saved': publish,
                                           **({'publication_binding': {key: binding[key] for key in
                                                ('project_id', 'execution_id', 'revision')}}
                                              if publish and all(key in binding for key in
                                                ('project_id', 'execution_id', 'revision')) else {}),
                                           **({'report_pending': True} if defer_report and outcome == 'completed' else {}),
                                           **({'save_unconfirmed': True} if save_unconfirmed else {})}}


def native_review_state(binding_file):
    """Reuse saved receipts, without another platform read or invented review."""
    binding_file = Path(binding_file)
    binding = json.loads(read_utf8(binding_file))
    design_file = binding_file.parent / 'design.json'
    design = json.loads(read_utf8(design_file)) if design_file.exists() else {}
    cases = list(binding.get('case_results', {}).values()) if 'case_results' in binding else design.get('cases', [])
    remaining = {}
    pending_actions = []
    for case in active_cases(cases):
        points = [p for p in case.get('checkpoints', []) if p.get('status') == 'pending_action']
        # Saved checkpoints use manual_step semantics, not an action_type
        # field. The parent action is derived from the first pending point.
        for item in points or [case]:
            if item.get('status') == 'pending_action':
                pending_actions.append({'case_id': case['case_id'],
                    **({'checkpoint_id': item['id']} if item is not case else {}),
                    'action_type': 'manual_step' if item is not case else item.get('action_type') or 'unspecified',
                    'action_required': item.get('action_required') or ''})
        status = case.get('status', 'not_run')
        if status in {'passed', 'failed'}:
            continue
        category = (case.get('action_type') or 'pending_action_unspecified') if status == 'pending_action' else status
        remaining.setdefault(category, []).append(case['case_id'])
    by_id = {c['case_id']: c for c in active_cases(cases)}
    unfinished = []
    plan = binding.get('work_plan') or {}
    if all(plan.get(k) == binding.get(k) for k in ('project_id', 'execution_id')):
        for unit in plan.get('units', []):
            if unit.get('purpose') == 'cleanup':
                # Business assertions do not settle cleanup. The local cache has no
                # authoritative work_unit_receipts; reconcile existing proof only.
                unfinished.append({'unit_id': unit['id'],
                    'case_ids': list(dict.fromkeys([*unit.get('case_ids', []),
                        *(p['case_id'] for p in unit.get('checkpoint_refs', []))])),
                    'completion_requires_receipt': True})
                continue
            pending = []
            for cid in unit.get('case_ids', []):
                case = by_id.get(cid, {})
                if case and case.get('status') not in {'passed', 'failed'} and not case_excluded(case):
                    pending.append(cid)
            for ref in unit.get('checkpoint_refs', []):
                case = by_id.get(ref.get('case_id'), {})
                point = next((p for p in case.get('checkpoints', []) if p['id'] == ref.get('checkpoint_id')), {})
                if point and point.get('status') not in {'passed', 'failed'} and not case_excluded(case):
                    pending.append(ref['case_id'])
            if pending:
                unfinished.append({'unit_id': unit['id'], 'case_ids': list(dict.fromkeys(pending))})
    boundary = None
    boundary_file = binding_file.parent / 'work-boundary.json'
    if boundary_file.exists():
        saved = json.loads(read_utf8(boundary_file))
        if all(saved.get('request', {}).get(k) == binding.get(k) for k in ('task_id', 'node_id', 'lease_id')):
            boundary = saved.get('result')
    # Local material, not a semantic verdict. Keep every source area, including
    # areas without cases, and every case (not just failures). No platform read.
    review_file = binding_file.parent / 'scope-review.json'
    write_private_json(review_file, {
        'execution_id': binding.get('execution_id'), 'revision': binding.get('revision'),
        'coverage': binding.get('coverage', design.get('coverage', [])),
        'requirement_design': design.get('requirement_design', {}), 'cases': cases,
        'remaining_by_status': remaining, 'semantic_review_complete': False,
        'pending_actions': pending_actions, 'unfinished_work_units': unfinished, 'resource_boundary': boundary,
        'instruction': '对照本轮 get_test_document 原目标和附件逐项核对；本材料不是范围完整证明。'
            'review_notes 记录来源/独立分支/用例ID/证据/缺口及下一步；缺失来源必须补读，不能从用例标题反推。'
            '授权、人工步骤、规则、依赖和未准备分开核实；分组只沿已保存状态，不代表原因已确认。'
            'unfinished_work_units 是原计划仍需核对的工作；completion_requires_receipt=true 的清理阶段须核对原结算凭据，不能由业务通过推定完成，也不要求重跑清理。resource_boundary 是原租约最近保存的边界回执，不是当前资源授权。'
            '普通资源等待、共享转独占和可准备样本不能解释为测不了；在当前可做项结束后按原 yield 临时交还并等原事件。'
            '测不了就跳过/别问我不等于取消这些可续接阶段，也不要求只读样本必须本轮创建；Codex 逐分支判断真实缺口。'})
    return {'execution_id': binding.get('execution_id'), 'revision': binding.get('revision'),
            'counts': binding.get('case_counts', {}), 'coverage_check': binding.get('coverage_check', {}),
            'cases_file': str(binding_file.parent / 'design.json'),
            'scope_review_file': str(review_file), 'unfinished_work_units': unfinished,
            'resource_boundary': boundary,
            'binding_file': str(binding_file), 'final_review': binding.get('final_review', {}),
            'observation_pending': (binding_file.parent / 'observation-pending.json').exists(),
            'notice': '复用已存设计、结果和动态缺口；只补真实变化。统计不代表已完成覆盖回查。'}


def native_correction_scope(binding):
    """Pin confirmation to the current original identity, generation and revision."""
    return {key: binding[key] for key in ('workspace_url', 'holder_id', 'task_id', 'node_id',
        'lease_id', 'project_id', 'execution_id', 'revision', 'account_id', 'account_ids',
        'dispatch_id', 'executor_ref', 'coordinator_ref', 'native_context_binding') if key in binding}


def native_correction_evidence(root, request_id, binding, correction_file, *, confirmed_revision=None):
    """Validate explicit original/correction evidence without reading the platform."""
    import re
    if not isinstance(request_id, str) or not re.fullmatch(r'[0-9]+-[a-f0-9]+', request_id):
        raise ValueError('纠正关联缺少原观察 request_id')
    root = Path(root).resolve()
    paths = {'observation': root / ('observation-inbox-' + request_id + '.json'),
             'response': root / ('native-receiver-response-' + request_id + '.json'),
             'correction': Path(correction_file).absolute()}

    def load(path):
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
            raise ValueError('纠正关联仅使用原普通证据文件')
        return json.loads(read_utf8(path))

    response = load(paths['response'])
    if response.get('request_id') != request_id or response.get('state') != 'unknown' or response.get('saved') is not False:
        raise ValueError('纠正关联仅处理原请求的未知保存，不改原回执')
    paths['original'] = Path(response['record_receipt_file']).absolute()
    if paths['original'].resolve().parent != root or paths['original'].resolve() == paths['correction'].resolve():
        raise ValueError('独立纠正回执不能替换原未知保存')
    original, correction = load(paths['original']), load(paths['correction'])
    fields = ('holder_id', 'task_id', 'node_id', 'lease_id', 'project_id', 'execution_id')
    for receipt in (original, correction):
        identity = {key: receipt[key] for key in ('workspace_url', 'binding', 'payload')}
        if (receipt['workspace_url'] != binding.get('workspace_url') or any(
                receipt['binding'].get(key) != binding.get(key) for key in fields)
                or any(receipt['binding'].get(key) != binding.get(key) for key in ('account_id',)
                       if key in receipt['binding'] or key in binding)
                or receipt.get('fingerprint') != hashlib.sha256(json.dumps(
                    identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()):
            raise ValueError('纠正关联的原绑定、账号、测试台或指纹不一致')
        before, request = receipt.get('revision_before'), receipt.get('request') or {}
        arguments = request.get('arguments') or {}
        expected = {**receipt['payload'], 'project_id': binding['project_id'],
                    'execution_id': binding['execution_id'], 'revision': before,
                    'response': 'summary', 'include_saved_design': True}
        if 'cases' in expected:
            expected['cases'] = native_checkpoint_observations(expected['cases'], receipt.get('case_baselines', {}))
        if (type(before) is not int or before < 1 or arguments != expected
                or request.get('action') != 'record' or request.get('record_action') != 'cases'
                or any(request.get(key) != binding.get(key) for key in (*fields[:4], 'account_id'))):
            raise ValueError('纠正关联的原保存请求、载荷或修订不一致')
    observation = load(paths['observation'])
    expected_original = {'cases': [{**(observation.get('case_changes') or {}),
        'case_id': observation.get('case_id'), 'status': observation.get('status'),
        'actual': observation_actual(observation)}]}
    if original.get('state') != 'unknown' or original['payload'] != expected_original:
        raise ValueError('原观察与完整未知保存载荷不一致；资产须沿原证据入口核对')

    def contains(expected, actual):
        if isinstance(expected, dict):
            return isinstance(actual, dict) and all(k in actual and contains(v, actual[k]) for k, v in expected.items())
        return type(expected) is type(actual) and expected == actual

    old_case = expected_original['cases'][0]
    corrected_cases = correction['payload'].get('cases', [])
    if not any(contains(old_case, case) for case in corrected_cases):
        raise ValueError('独立纠正没有完整保留原用例的全部提交字段')
    result, before = correction.get('result') or {}, correction['revision_before']
    if (correction.get('state') != 'saved' or type(result.get('revision')) is not int
            or result['revision'] != before + 1
            or result['revision'] != (binding.get('revision') if confirmed_revision is None else confirmed_revision)
            or result.get('execution_id') != binding['execution_id'] or before < original['revision_before']):
        raise ValueError('纠正保存须为当前原记录的精确下一修订')
    try:
        old_end = datetime.fromisoformat(original['client_timing']['finished_at'].replace('Z', '+00:00'))
        new_start = datetime.fromisoformat(correction['started_at'].replace('Z', '+00:00'))
        new_end = datetime.fromisoformat(correction['client_timing']['finished_at'].replace('Z', '+00:00'))
        if old_end.tzinfo is None or new_start.tzinfo is None or new_end.tzinfo is None or not old_end < new_start <= new_end:
            raise ValueError('保存时序不一致')
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('独立纠正必须晚于原未知保存结束') from error
    evidence = {key: {'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                for key, path in paths.items()}
    return original, correction, evidence


def native_observation_correction(root, request_id, binding):
    """Revalidate a durable explicit resolution; no authority cache or network."""
    try:
        root = Path(root)
        path = root / ('native-observation-correction-' + str(request_id) + '.json')
        if path.is_symlink() or not path.is_file():
            return False
        proof = json.loads(read_utf8(path))
        original, correction, evidence = native_correction_evidence(
            root, request_id, binding, proof['evidence']['correction']['file'], confirmed_revision=proof['revision'])
        scope = native_correction_scope(binding)
        confirmed_scope = proof.get('binding') or {}
        if (proof.get('resolution') != 'corrected_by_saved_receipt' or proof.get('request_id') != request_id
                or {k:v for k,v in confirmed_scope.items() if k != 'revision'} != {k:v for k,v in scope.items() if k != 'revision'}
                or confirmed_scope.get('revision') != proof['revision']
                or type(binding.get('revision')) is not int or binding['revision'] < proof['revision']
                or proof.get('evidence') != evidence
                or proof.get('original_revision_before') != original['revision_before']
                or proof.get('revision') != correction['result']['revision']):
            return False
        native_save_readback(correction, proof['record'], correction.get('case_baselines', {}))
        return True
    except (KeyError, TypeError, ValueError, OSError):
        return False


def native_observation_corrected(root, request_id, binding, receipt):
    response = root / ('native-receiver-response-' + str(request_id) + '.json')
    observation = root / ('observation-inbox-' + str(request_id) + '.json')
    if not response.exists() or not observation.exists():
        return False
    saved = json.loads(read_utf8(response))
    if saved.get('request_id') != request_id or saved.get('state') not in {'not_sent', 'rejected'}:
        return False
    try:
        rejected_at = datetime.fromisoformat(saved['timing']['save_finished_at'].replace('Z', '+00:00'))
        corrected_at = datetime.fromisoformat(receipt['started_at'].replace('Z', '+00:00'))
        if corrected_at <= rejected_at:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    case_id = json.loads(read_utf8(observation)).get('case_id')
    return (receipt.get('state') == 'saved' and all(receipt.get('binding', {}).get(key) == binding.get(key)
            for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'project_id', 'execution_id'))
            and any(case.get('case_id') == case_id and 'status' in case and 'actual' in case
                    for case in receipt.get('payload', {}).get('cases', [])))


def remember_native_observation_corrections(binding_file, binding, receipt_file, receipt):
    root = Path(binding_file).parent
    for name in ('native-observation-awaiting.json', 'native-last-observation.json'):
        pointer = root / name
        if pointer.exists():
            request_id = json.loads(read_utf8(pointer)).get('request_id')
            if native_observation_corrected(root, request_id, binding, receipt):
                binding.setdefault('observation_corrections', {})[request_id] = str(receipt_file)


def native_publication_ready(binding_file, binding):
    """Confirm actual saves, including requests queued before a POST marker."""
    root = Path(binding_file).parent
    clear_rejected_native_observation(root, binding)
    if (root / 'observation-pending.json').exists() or native_final_review_unconfirmed(binding):
        return False
    checked = set()
    for name in ('native-observation-awaiting.json', 'native-last-observation.json'):
        pointer = root / name
        if not pointer.exists():
            continue
        request_id = json.loads(read_utf8(pointer)).get('request_id')
        if request_id in checked:
            continue
        checked.add(request_id)
        response = root / ('native-receiver-response-' + str(request_id) + '.json')
        saved = json.loads(read_utf8(response)) if response.exists() else {}
        if saved.get('request_id') == request_id and native_observation_settled(root, saved, binding):
            continue
        if native_observation_correction(root, request_id, binding):
            continue
        return False
    return True


def native_work_plan(client, binding_file, plan):
    """Register original stages without requiring an ended execution lease."""
    binding_file = Path(binding_file)
    with batch_lock(binding_file):
        binding = json.loads(read_utf8(binding_file))
        if binding.get('workspace_url', client.url) != client.url or not isinstance(plan, dict):
            raise ValueError('Work plan does not belong to the original binding')
        if not native_publication_ready(binding_file, binding):
            raise ValueError('Confirm original observations before a work-plan boundary')
        for key in ('project_id', 'execution_id'):
            if key in plan and plan[key] != binding[key]:
                raise ValueError('Work plan cannot replace the original execution record')
        plan = {'schema_version': 1, 'project_id': binding['project_id'], 'execution_id': binding['execution_id'],
                'units': copy.deepcopy(plan.get('units'))}
        request = {key: binding[key] for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'dispatch_id', 'executor_ref') if key in binding}
        revision = (binding.get('work_plan') or {}).get('plan_revision', 0)
        request.update(action='work_plan', arguments={'work_plan': plan, 'expected_plan_revision': revision})
        prior = binding.get('work_plan_request') or {}
        if (prior.get('action') == 'work_plan' and (prior.get('arguments') or {}).get('work_plan') == plan
                and binding.get('work_plan_request_revision') == revision):
            request = prior
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        receipt_file = binding_file.parent / ('work-plan-' + fingerprint + '.json')
        receipt = json.loads(read_utf8(receipt_file)) if receipt_file.exists() else None
        # A saved response describes the previous boundary, not the node's
        # current lifecycle. Every explicit call obtains one authoritative
        # response; pending/unknown recovery still uses the identical request.
        if receipt:
            request = receipt['request']
        receipt = {'state': 'pending', 'request': request}
        write_private_json(receipt_file, receipt)
        result = client.call('direct_test_session', request)
        if result.get('saved') is not True or not isinstance(result.get('work_plan'), dict):
            raise ValueError('Original work-plan receipt is not confirmed')
        receipt.update(state='saved', result=result)
        write_private_json(receipt_file, receipt)
        binding['work_plan'] = receipt['result']['work_plan']
        binding.update(work_plan_request=request, work_plan_request_revision=binding['work_plan']['plan_revision'],
                       work_plan_receipt_file=str(receipt_file))
        write_private_json(binding_file, binding)
        return {**receipt['result'], 'receipt_file': str(receipt_file)}


def native_continuation_kit(client, binding_file, result, command, entry_url=None):
    """Use the original queued run kit in a private formal-generation directory."""
    packet = result.get('continuation_packet')
    if not packet:
        return result
    root = Path(binding_file).absolute().parent
    assignment = packet['assignment']
    node_id = assignment['node_id']
    if not isinstance(node_id, str) or not node_id or any(c not in '0123456789abcdef' for c in node_id):
        raise ValueError('正式续接节点格式不正确')
    target = root / ('continuation-' + node_id)
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.is_symlink():
        raise ValueError('正式续接目录不能为符号链接')
    old_assignment = root / 'assignment.json'
    old = json.loads(read_utf8(old_assignment)) if old_assignment.exists() else {}
    options = {key: copy.deepcopy(old[key]) for key in (
        'direct_browser', 'browser_mode', 'local_artifact_io', 'local_observation_stream',
        'browser_routine_file', 'browser_call_file', 'browser_routine_api') if key in old}
    assignment = {**options, **assignment}
    record = result['source_record']
    assignment_path, design_path, next_binding = target / 'assignment.json', target / 'design.json', target / 'binding.json'
    if not assignment_path.exists():
        write_private_json(assignment_path, assignment)
        write_private_json(design_path, {'cases': record.get('cases', []), 'coverage': record.get('coverage', [])})
        write_private_json(next_binding, {**assignment, 'lease_id': '', 'workspace_url': client.url,
            'project_id': record['project_id'], 'execution_id': record['id'], 'revision': record['revision'],
            'case_results': {c['case_id']: c for c in record.get('cases', [])},
            'coverage': record.get('coverage', []), 'work_plan': result['work_plan']})
    elif json.loads(read_utf8(assignment_path)).get('node_id') != node_id:
        raise ValueError('不能覆盖其他模块的准备目录')
    stop_native_observation_receiver(binding_file)
    result.update(continuation_binding_file=str(next_binding), continuation_assignment_file=str(assignment_path))
    if result['next_action'] == 'prepare_formal_continuation':
        url = entry_url or packet.get('task_material', {}).get('ui_target_url')
        result['continuation_run_kit'] = native_run_kit(command, assignment_path, design_path, target, url)
    return result


def native_work_boundary(client, binding_file, unit_id):
    binding_file = Path(binding_file)
    with batch_lock(binding_file):
        binding = json.loads(read_utf8(binding_file))
        plan = binding.get('work_plan') or {}
        unit = next((u for u in plan.get('units', []) if u['id'] == unit_id), None)
        if not unit or any(plan.get(k) != binding.get(k) for k in ('project_id','execution_id')):
            raise ValueError('先保存原用例的完整阶段计划，不能推测资源要求')
        digest = hashlib.sha256(json.dumps(unit['requires'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        token = {'work_unit_id':unit_id, 'plan_revision':plan['plan_revision'], 'requirements_digest':digest}
        request = {key:binding[key] for key in ('holder_id','task_id','node_id','lease_id')}
        result = client.call('direct_test_session', {**request, 'action':'request_resources', 'arguments':{'work_token':token}})
        write_private_json(binding_file.parent / 'work-boundary.json', {'request':request,'work_token':token,'result':result})
        return result


def native_run_kit(command, assignment_file, design_file, directory, entry_url):
    """Prepare transport once at dispatch; the worker only supplies real observations."""
    from urllib.parse import urlsplit
    import shlex
    if urlsplit(entry_url).scheme not in {'https', 'http'} or not urlsplit(entry_url).netloc:
        raise ValueError('entry-url 必须为已核对的实际业务入口')
    assignment = json.loads(read_utf8(assignment_file))
    resume_existing = bool(assignment.get('resume_record'))
    selected_cases = native_design(json.loads(read_utf8(design_file)), allow_results=resume_existing)
    options = native_isolated_options(assignment, directory)
    isolated = options is not None
    if isolated:
        if options.get('playwright_module') and not Path(options['playwright_module']).is_absolute():
            raise ValueError('显式 Playwright 模块必须为绝对路径；省略则由执行主机自动发现')
        if (assignment.get('browser_routine_file') or assignment.get('browser_call_file')) and assignment.get('browser_routine_api') != 'playwright':
            raise ValueError('独立环境的业务例程须声明 browser_routine_api=playwright；不把旧 cua 控件 API 当作 Playwright Page')
    executor_ref = assignment.get('executor_ref', '')
    target_thread = native_thread_target(executor_ref)
    if not target_thread:
        raise ValueError('缺少原独立执行会话，不能生成派发消息')
    root = Path(directory).absolute()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    ledger_path = root / 'run-ledger.json'
    kit_started = datetime.now(timezone.utc).isoformat()
    if ledger_path.exists():
        ledger = json.loads(read_utf8(ledger_path))
        if any(ledger.get(k) != assignment.get(k) for k in ('task_id', 'node_id')):
            raise ValueError('计时账本属于其他任务，不能覆盖')
    else:
        started_at = assignment.get('lifecycle_started_at') or kit_started
        if datetime.fromisoformat(started_at.replace('Z', '+00:00')).tzinfo is None:
            raise ValueError('链路起点必须带实际时区')
        write_private_json(ledger_path, {'started_at': started_at,
            'start_basis': assignment.get('lifecycle_start_basis') or '执行包生成开始；不包含更早协调准备',
            'task_id': assignment['task_id'], 'node_id': assignment['node_id'], 'kit_started_at': kit_started})
    config = {'command': command, 'assignment_file': str(Path(assignment_file).absolute()),
              'design_file': str(Path(design_file).absolute()), 'directory': str(root), 'entry_url': entry_url}
    if assignment.get('local_observation_stream') is True:
        if assignment.get('local_artifact_io') is not True:
            raise ValueError('本地观察接收需要已核验的原生文件读写能力')
        config['observation_stream'] = True
    path = root / 'native-cycle.js'
    config['control_receipts'] = True
    source = 'const config = ' + json.dumps(config, ensure_ascii=False) + ';\n' + NATIVE_CONTROL_TEMPLATE + '\n' + NATIVE_CYCLE_TEMPLATE
    if path.exists() and read_utf8(path) != source:
        raise ValueError('已有不同执行包，不能覆盖原轮次')
    path.write_text(source, encoding='utf-8')
    path.chmod(0o600)
    browser_path = root / 'native-browser-case.js'
    if browser_path.exists() and read_utf8(browser_path) != NATIVE_BROWSER_TEMPLATE:
        raise ValueError('已有不同浏览器执行包，不能覆盖原轮次')
    browser_path.write_text(NATIVE_BROWSER_TEMPLATE, encoding='utf-8')
    browser_path.chmod(0o600)
    launch = ('const s=await tools.exec_command({cmd:' + json.dumps('cat ' + shlex.quote(str(path))) + ',max_output_tokens:12000});\n'
              'if(s.exit_code!==0)throw new Error("kit unavailable");\n'
              'store(' + json.dumps(str(path)) + ',s.output);\n'
              'const AF=Object.getPrototypeOf(async function(){}).constructor;\n'
              'await new AF("tools","text","ALL_TOOLS","input",s.output)(tools,text,ALL_TOOLS,{action:"prepare"'
              + (',resume:true' if resume_existing else '') + '});')
    # Capability is supplied only after this native environment's ordinary artifact IO
    # has been verified. Do not make every worker rediscover it or retype the helper.
    browser_bootstrap = None
    if assignment.get('local_artifact_io') is True:
        browser_bootstrap = (
            'var nativeArtifactFs=await import("node:fs/promises");\n'
            'var nativeEmit=async observation=>{await nativeArtifactFs.writeFile('
            + json.dumps(str(root / 'observation-native.json'))
            + ',JSON.stringify(observation),{encoding:"utf8",mode:0o600});};\n'
            + NATIVE_BROWSER_TEMPLATE)
    if config.get('observation_stream'):
        browser_bootstrap = (NATIVE_OBSERVATION_SEND_TEMPLATE + '\n'
            + 'var nativeEmit=observation=>nativeSendObservation(' + json.dumps(str(root)) + ',observation);\n'
            + NATIVE_BROWSER_TEMPLATE)
    prompt = (('沿原任务和原执行记录恢复已授权范围；保留全部用例、已执行结果和证据，不重建基线、不重复已完成业务。'
               if resume_existing else '执行本轮已授权范围；复用已有设计和客户端。')
              + '首个工作调用直接执行下列 functions.exec：\n'
              + launch + '\n等待即结束回合，原事件后复用同脚本 input={action:"prepare",resume:true}。'
              'ready 后直接在 entry_url 创建隐藏 IAB，不先开 about:blank；复用返回设计、账号、步骤和预期。'
              '会话首次初始化或重置后的入口须单独执行并阅读工具文档；返回的初始页面状态就是当前证据，不再单独重复 getAXState。'
              '首批设计不是完整模块的范围上限：完整探索需按实际页面补齐成功终点、状态变化、边界和关联链；'
              '明确选定用例的任务仍限原选例范围。复用公共函数，按新观察增量增加设计、coverage 和独立检查点，不重写整个执行脚本。'
              '复用已核验执行包中的纯函数 ' + str(browser_path) + '；它不连平台、不代理浏览器。\n'
              + (('本轮协调者已核验原生环境支持普通本地文件读写；直接使用以下静态函数和导出代码，'
                  '禁止 eval/new Function/动态加载函数；不要无实际失败就回退重抄观察。emit 使用 nativeEmit。\n'
                  + browser_bootstrap) if browser_bootstrap else NATIVE_BROWSER_TEMPLATE) + '\n'
              '可选用 nativeBrowserCase 记录已知步骤和完整逐项 j.check，也可由 Codex 直接观察和操作页面；'
              'j.step 记录耗时和失败位置，j.until 只等待真实状态，禁止重复提交。普通异常返回 interrupted 和原 observation，由 Codex 读取现场、修正定位后继续；'
              '不自动运行 recover/close，不新增失败断言，不因定位失败结束任务。仅决定结束任务时显式关闭并核实真实退出。'
              'emit 使用当前环境已经支持的本地文件输出把原观察直接导出至 ' + str(root / 'observation-native.json') + '，'
              '不在 cua 读取凭据、调用平台或导入平台客户端；若环境不支持文件输出，直接输出原观察并使用既有 JSON 保存。'
              '文件已输出后立即复用生命周期脚本 input={action:"record",observation_file:'
              + json.dumps(str(root / 'observation-native.json')) + '}；'
              '不重抄 checks、不重读文件核对、不再写总结、不中途截图输出整段 base64。原文件包含完整逐项断言和步骤时间。'
              '生命周期源码已在 functions.store 缓存；后续在 functions.exec 使用 load('
              + json.dumps(str(path)) + ') 交给同一 AsyncFunction，不再 cat 脚本。若执行上下文重置才重新读取。'
              '浏览器仅使用当前工具公开 API，未知分支才返回判断；已知操作、真实等待和逐项断言合并，完整状态勿用增量快照猜测。'
              '仅不支持本地导出时，断言现场输出 {case_id,status,checks:[{name,expected,observed,ok}],timing:{last_assertion_at,browser_closed_at}}，'
              '使用真实读取值、布尔比较和实际时间；随即复用上面脚本 input={action:"record",observation:原观察}，'
              '保存成功才做下一条；详细证据与检查点仍按原记录入口保存，不减少断言。'
              '仅在 Codex 明确决定结束任务时，实际清理关页，再给 record 输入 finish_task:true、browser_stopped:true 和真实 reason，'
              '脚本连续保存、交还、通知后继、发布，无需再拼参数或总结；未关页不能声明退出。'
              '未知保存不重发、不重跑，真实阻塞和未探索分支保留缺口；不越过用户授权范围，不另发通知。')
    if config.get('observation_stream'):
        manual_start = prompt.index('emit 使用当前环境已经支持的本地文件输出')
        manual_end = prompt.index('生命周期源码已在 functions.store 缓存', manual_start)
        prompt = prompt[:manual_start] + prompt[manual_end:]
        fallback_start = prompt.index('仅不支持本地导出时，断言现场输出')
        prompt = prompt[:fallback_start] + '未知保存不重发、不重跑，真实阻塞和未探索分支保留缺口；不越过用户授权范围，不另发通知。'
        prompt += ('\n本轮启用已核验本地观察接收器：prepare 已在工具进程中启动原绑定接收器，'
            'nativeEmit 仅通过普通本地文件和命名管道交付观察，并等待真实保存回执；没有网络、凭据、浏览器代理或后台模型。'
            '此模式不要再次调用 record、重抄结果或再保存文件。'
            '每条完成后 emit 在同次原生调用取得真实 save_receipt；saved=true 才允许下一条。'
            '保存失败或响应未知只暂停跨用例推进，保留浏览器和观察。读取原 request_id 的回执核实，不重发、不自动关页或判业务失败。'
            '最后立即执行缓存生命周期代码 input={action:"closeout",browser_stopped:实际关页结果,'
            'reason:真实退出依据,save_unconfirmed:save_receipt.saved!==true}，沿原工具编排交还发布通知。'
            '不要输出全部检查项，返回 case_id/status/检查数/save_receipt 的保存结果和时间；详细原观察已经保存。'
            '本地接收器沿原绑定复用，普通保存错误不退出，只有明确 closeout 才发送停止标记；未知写入仍由原 pending 回执防止重放。')
    review_guidance = ('\n最终回查只提交变化：复用生命周期脚本 input={action:"review",input_file:本地变化JSON绝对路径,receipt_file:本次私有回执绝对路径}。'
        'JSON 可只含 coverage/review_notes/scene_outcome，或 cases 变化批次与 asset_files 本地文件清单；原绑定锁下一次提交并自动更新 revision。'
        '逐条真实结果仍立即保存，不积到收尾。独立初态、输入、边界和预期分支分别使用独立 case_id；同一场景的连续断言才用检查点。'
        '回查从原目标/资料逐项映射独立分支、用例ID、本轮证据、缺口及下一步，写入现有 review_notes；不能仅统计失败或从用例标题反推范围。'
        '授权不足、人工步骤、规则未知、客观依赖、尚未准备与工具中断分开记录，不能混写为权限不足；缺样本或未验证分支保留非通过状态。'
        '保存成功后继续已授权业务或真实清理；明确结束且已核实浏览器退出时可同次带 finish_task:true、browser_stopped:true、reason。'
        '没有变化就直接 closeout；已存数据自动生成报告摘要，不重抄全量用例、不并行 upload-files 和裸 record/finish、不手写修订。'
        '校验失败保留原回执，按一次返回的具体问题修正已有观察，不读取未生成的成功回执、不重跑浏览器动作。')
    review_guidance += ('\n每条 observation 可带 case_changes（原记录字段，如 steps/test_data/checkpoints/action_context）和 asset_files；'
        '把本次已知的真实复现路径、输入、检查点及证据同次保存，不留到最后重写，不重新运行已完成业务。'
        '保存回执已返回动态缺口，原绑定缓存 coverage_check 和 design.json，最终回查直接复用，不为计数再读全量平台记录。'
        '浏览器实际退出后若仍需整理报告，立即调用 input={action:"release",from_observation:true}（或 browser_stopped:true、真实 reason）；'
        '它先交还并通知后继，返回原记录回查信息及本地 scope_review_file，报告保持待补；该材料不是原文核对结论。无需账号或新任务就可沿原绑定补保存。'
        '整理完成只调用 input={action:"complete",input_file:确实变化的JSON路径,receipt_file:本次回执路径}，同次保存变化并发布；'
        '没有变化则 input={action:"complete"} 直接发布。不要重新 claim、重抄汇总、重读全量结果或重复发送交接。'
        'review 带 finish_task:true 且已实际退出时也先交还再保存发布。普通 review 或定位错误仍不结束任务。')
    if assignment.get('browser_call_file'):
        call_source = read_utf8(assignment['browser_call_file'])
        prompt += ('\n以下是协调者按当前选定用例及已核验页面准备的静态调用；先核对与本轮范围一致。'
            '会话首次初始化并读完工具文档后直接复用这些已知步骤，不重新编写公共函数或结果整理逻辑。'
            'nativeCaseId 用本次 prepare 返回的真实编号，nativeTab 用本次专用标签；页面与前置条件变化则保留观察并停止相关步骤，'
            '不能据旧证据直接通过。仍需本次全部真实断言与证据；其他未知新用例继续探索设计，不要求提前编写全部模块脚本。\n'
            + call_source)
    runtime = None
    if assignment.get('browser_routine_file') or config.get('observation_stream'):
        if not config.get('observation_stream'):
            raise ValueError('已加载函数的短调用沿用已核验本地观察入口')
        routine = assignment.get('browser_routine_file') or assignment.get('browser_call_file')
        library = not routine
        call_source = (read_utf8(routine) if routine else
                       'return {run:args=>nativeBrowserCase({...args,preserve:async observation=>{const fs=await import("node:fs/promises");await fs.writeFile(directory+"/native-draft-"+encodeURIComponent(observation.case_id)+".json",JSON.stringify(observation),{encoding:"utf8",mode:0o600});}}),emit:observation=>nativeSendObservation(directory,observation),finish:close=>nativeFinishTask({close,directory}),receipt:(id,options)=>nativeReadObservationReceipt(directory,id,options)};')
        if assignment.get('browser_call_file') and not assignment.get('browser_routine_file'):
            call_source += '\nreturn typeof nativeSummary === "undefined" ? {executed:true} : nativeSummary;'
        receipt_file = assignment.get('browser_runtime_receipt')
        if not receipt_file:
            cache = Path.home() / '.cache' / 'api-test-workspace' / 'native-runtimes'
            cache.mkdir(mode=0o700, parents=True, exist_ok=True)
            identity = hashlib.sha256((executor_ref + NATIVE_BROWSER_TEMPLATE + NATIVE_OBSERVATION_SEND_TEMPLATE + call_source).encode()).hexdigest()
            receipt_file = cache / (identity + '.json')
        runtime = native_runtime_package(call_source, executor_ref, receipt_file,
                                         browser_mode='isolated' if isolated else 'cua')
        receipt_path = Path(runtime['receipt_file'])
        try:
            receipt = json.loads(read_utf8(receipt_path)) if receipt_path.exists() else {}
        except (OSError, ValueError):
            receipt = {}
        if not isinstance(receipt, dict):
            receipt = {}
        loaded = receipt.get('key') == runtime['key'] and same_executor_ref(receipt.get('executor_ref'), executor_ref)
        combined_entry = loaded and not library
        call = native_runtime_call(runtime['key'], root, library=library,
                                   entry_url=entry_url if combined_entry or isolated else None,
                                   browser_mode='isolated' if isolated else 'cua')
        runtime['kind'] = 'library' if library else 'routine'
        runtime['call_source'] = call
        runtime['loaded_receipt'] = loaded
        runtime['combined_entry'] = combined_entry
        if combined_entry and len(selected_cases) == 1:
            write_private_json(root / 'prepared-call.json', {'source': call, 'runtime_key': runtime['key'],
                'binding': {k: assignment[k] for k in ('task_id', 'node_id', 'holder_id', 'dispatch_id', 'executor_ref')}})
        else:
            (root / 'prepared-call.json').unlink(missing_ok=True)
        prompt = ('执行本轮已授权具体设计，首个工作调用直接执行以下 functions.exec：\n' + launch
            + '\n未获资源立即结束，只有原资源事件后 resume:true。ready 后用实际 case_id 设置 nativeCaseId，'
            + ('下面短调用已经包含创建本任务隐藏标签和调用已加载函数，作为一次原生调用执行；'
               '不在它前面另开标签、重复读取或外置原函数已有检查。'
               if combined_entry else '直接在 entry_url 创建本任务隐藏标签 nativeTab；首次初始化单独调用并阅读文档。')
            + '会话首次初始化或实际重置时仍严格遵循原生工具的单入口及文档要求；'
            '平台准备与原生函数加载分开计时；已有设计、账号、清单、步骤直接复用。'
            + ('以下函数已由本执行会话加载并有对应代码摘要回执，不输出、复制或重新定义函数；只执行下面短调用。'
               if loaded else '本原生会话尚无对应加载回执；先在原生工具中静态定义以下函数一次，不执行浏览器业务；首次加载耗时必须列出。\n'
               + runtime['registration_source'])
            + ('\nprepare 返回 native_call 已填入本轮实际 case_id；下一个原生调用直接执行它，不重新拼代码。' if combined_entry and len(selected_cases) == 1 else '\n' + call)
            + ('\n上面的短调用取得本轮公共函数；随后可选用 nativeBrowserCase({case_id:nativeCaseId,run,emit:nativeEmit})，或直接操作公开 Page API；它只是记录辅助函数。'
               '只编写本模块实际业务步骤和完整逐项断言，不重新输出公共函数。run(j) 用 j.step/j.check；j.until 只等待真实状态，不重复提交。'
               '普通操作错误返回 interrupted、observation 和 failed_step，不执行 recover/close、不自动保存失败结论。Codex 观察后决定继续，传 observation:原草稿复用断言与步骤；不重演未知提交。'
               '未知新模块仍侦察实际页面、保存具体设计并边执行边增补，首版不是封闭清单，不能套用其他模块的断言或历史通过。'
               if library else '')
            + '\n使用本次真实页面、账号和完整逐项断言，不复制历史通过；已知步骤连续，未知新范围仍探索增补。'
            '已加载用例内包含的账号、前置条件和结果检查直接在原函数内执行，不在短调用前再执行一遍；'
            '初始页面实际显示登录或其他变化时仅处理必要差异，恢复正常即回到原函数，不另加重复整页读取与账号菜单检查。'
            '保存回执成功才开始下一用例；未知保存先用 nativeReceipt(request_id) 读原回执；实际未知 POST 用 nativeReceipt(request_id,{reconcile:true}) 只读核对原平台记录，保留现场、不重发。函数仅保存代码，不捕获旧标签、账号或保存目录。'
            + ('若原生会话实际重置，使用 environment_recovery_tool_arguments 连接原浏览器并加载同版函数一次，保留旧观察，不重跑已完成业务。'
               '仅明确决定结束任务时，先显式 nativeFinish(()=>nativeBrowserEnvironment.close()) 保存真实退出依据，再在 functions.exec 复用 load('
               if isolated else '旧 cua 会话重置时按公开工具说明重取原标签并加载同版函数；不创建替代浏览器。'
               '仅明确结束时调用 nativeFinish(关闭本任务原标签并核实退出的函数)，保存真实依据，再在 functions.exec 复用 load(') + json.dumps(str(path))
            + ') 的生命周期代码，input={action:"closeout",from_observation:true}；'
            '它读取本轮真实观察回执的退出依据，不另写摘要或拼结果。已保存的完整检查保留。')
    if runtime is None:
        (root / 'prepared-call.json').unlink(missing_ok=True)
    # Both cached-runtime and plain native paths must expose the same review
    # operation. The cached-runtime prompt above replaces the initial prompt.
    prompt += ('\n准备/恢复返回 coverage 与原用例；完整模块按实际页面增补成功终点、状态变化、边界和关联，'
               '首批设计不是范围上限；明确选例仍限原授权范围。' + review_guidance)
    if resume_existing:
        prompt = ('沿原任务、节点和执行记录恢复；prepare 的服务端原记录是当前全部用例及结果，'
                  '保留 case_id、已执行结果和证据，不重建基线、不重跑已完成业务，未知保存先核实。\n' + prompt)
    environment_setup = None
    prompt += ('\n截图仅在关键结果或缺陷仍在时取证，优先 nativeCaptureEvidence({page,case_id,step,directory,preview})，'
        '保留控件与必要上下文，特写仅补充。preview 使用当前工具公开图片展示能力显示同一截图字节，就地看一次是否证明当前缺陷；'
        '不逐动作截图，不重复业务检查，不循环补图，已有证据够用就复用；失败或现场丢失写明缺口。')
    prompt += ('\n领取前复用原资料核对已知目标/账号项目/样本条件；首次登录侦察立即核实 UI 共同前置，不等执行阻塞后才核对。'
        '首版具体用例仍在实际侦察后保存，随后按随包 references/work-stages.md 保存原节点阶段计划；depends_on 只连接必要检查点，不挂无关整批通过条件：'
        '原生命周期 input={action:"work_plan",plan_file:绝对路径}。设计实质扩充时更新同一计划，不合并独立场景。'
        '跨账号/独占边界用 input={action:"work",unit_id:原阶段ID}；continue_current_work 就执行回执中的原场景，'
        '只有 release_required=true 且已真实退出才 input={action:"yield",from_observation:true}，不能冒用 completed/release。'
        '实际模块结束仍用原 release/complete，报告整理不重新占号。')
    environment_recovery = None
    stage_ready_script = None
    if native_claim_configuration(assignment).get('work_token'):
        stage_ready_script = launch.replace('{action:"prepare"' + (',resume:true' if resume_existing else '') + '}', '{action:"stage_ready"}')
    if isolated:
        digest = hashlib.sha256(NATIVE_ISOLATED_BROWSER_TEMPLATE.encode()).hexdigest()[:16]
        helper_path = root / ('native-isolated-browser-' + digest + '.mjs')
        helper_path.write_text(NATIVE_ISOLATED_BROWSER_TEMPLATE, encoding='utf-8')
        helper_path.chmod(0o600)
        environment_setup = ('var nativeIsolatedModule=await import(' + json.dumps(helper_path.as_uri()) + ');\n'
            'var nativeBrowserEnvironment=await nativeIsolatedModule.prepare(' + json.dumps({
                'assignment_file': str(Path(assignment_file).absolute()), 'directory': str(root), 'origin': entry_url})[:-1]
            + ',runtime_context:{cwd:nodeRepl.cwd,homeDir:nodeRepl.homeDir}});\n'
            'nodeRepl.write({environment_ready:true,receipt_file:' + json.dumps(str(root / 'browser-environment.json')) + '});')
        environment_recovery = environment_setup.replace('nativeIsolatedModule.prepare(', 'nativeIsolatedModule.reconnect(').replace(
            'environment_ready:true,receipt_file:',
            'environment_ready:true,recovery_receipt_file:nativeBrowserEnvironment.recovery_receipt_file,receipt_file:')
        # Replace only browser acquisition/exit wording. The existing cached
        # prepare/save/receiver/closeout/handoff instructions remain identical.
        prompt = prompt.replace('ready 后直接在 entry_url 创建隐藏 IAB，不先开 about:blank；',
            'ready 后使用 nativeBrowserEnvironment.enter(entry_url) 取得本任务 Playwright Page；')
        prompt = prompt.replace('直接在 entry_url 创建本任务隐藏标签 nativeTab；首次初始化单独调用并阅读文档。',
            '复用已创建的独立环境；下面短调用取得并复用 nativeTab（真实 Playwright Page）。')
        prompt = prompt.replace('下面短调用已经包含创建本任务隐藏标签和调用已加载函数',
            '下面短调用已经包含取得独立环境页面和调用已加载函数')
        prompt = prompt.replace('在原生 cua 同次调用', '在 node_repl 同次调用')
        prompt += ('\n普通定位失败、页面状态变化先返回 Codex 判断；不串联未知分支。外层工具 timeout_ms 应覆盖本次明确操作和保存预算并留返回余量；'
                   '不使用统一强制防卡计时器、不自动重试或关闭。准备入口给出 environment_tool_arguments；长业务分支按真实观察边界返回。')
        prompt += ('\n点击/截图超时或 REPL 重置后，先保留原始错误、阶段、时间、用例和未保存观察；使用执行包 environment_recovery_tool_arguments 显式重连原环境，'
            '读取本地 browser-diagnostic-*/browser-reconnect-* 回执，再重新取得原 Page、加载同版函数并核实未知提交结果。'
            '重连调用自己超时只表示恢复未确认，不能写成已证明不可恢复；记录最后阶段并继续针对故障排查。'
            '工具层、浏览器进程/连接层、被测接口响应分别报告；业务400不能当连接故障，进程或CDP可达不能当页面恢复或业务通过。'
            '不为恢复另建任务/账号/profile，不自动刷新或重放未知POST；明确停止立即走原收尾，不为了恢复延迟停止。')
        prompt = ('本轮由 Codex 使用原始 Playwright Page API 自己观察和操作；每个账号独立浏览器进程及私有 profile，默认持久上下文不会随 REPL 连接断开销毁。'
            '先阅读当前 node_repl 及 Playwright 公开使用说明，再在持久 node_repl 执行一次下面环境入口；'
            '这是账号 prepare 前的环境创建或连接入口，重复准备连接原 profile 和原页面，不登录、不重放导航或业务。\n'
            + environment_setup + '\n环境成功后继续以下原生命周期包，失败不领取账号；'
            '账号由原 prepare 分配，首次 enter 从原 binding.json 核对一次账号与环境，后续动作直接使用 Page，'
            '没有逐动作授权、HTTP 转发、Runner、心跳或登录前审批。多账号页面在 nativeBrowserEnvironment.pagesByAccount；'
            '凭据沿原 credentials 入口取得并用于实际 UI 登录，原 native_login 证据和状态语义不变。'
            '保留已加载代码、观察接收器、逐条保存、交还确认与计时；普通定位失败不改变任务/用例状态、不关闭浏览器、不交还账号；'
            '若没有启用短调用，ready 后执行 var nativeTab=await nativeBrowserEnvironment.enter('
            + json.dumps(entry_url) + ')，随后执行原用例。等待资源时保留该空环境，原事件续接；部分启动失败或连接丢失需要取消时，可显式 nativeIsolatedModule.closeOwned({assignment_file:原文件,directory:原目录}) 仅关闭存活归属进程，不必先重启死亡进程；'
            '明确取消或结束时才关闭本任务环境。REPL 重置重新连接原进程及 profile；真实进程退出才显式 restart_exited:true，'
            '保留原逻辑 context_id、账号与用例，实际新进程递增 browser_generation 证据；重新读取现场和核实登录，不自动重放业务。旧版确实退出后的替换使用原 assignment.replace_exited_environment 与 checkpoint 原子替换原绑定，不重新排队或新建任务。\n' + prompt)
    role_context = {key: assignment.get(key) for key in ('task_id', 'node_id', 'scope', 'source_project_id', 'project_id')}
    if stage_ready_script:
        prompt = ('首个工作调用先用 functions.exec 执行下列阶段核对；excluded=true 时标记不测且不等资源；其他 stage_ready=false 才结束回合等真实事件，'
                  'stage_ready=true 才执行后文环境准备。不得省略核对或用单账号代替完整集合。\n'
                  + stage_ready_script + '\n' + prompt)
    prompt = ('当前角色worker：仅负责原assignment的本模块。原绑定与资料归属：'
              + json.dumps(role_context, ensure_ascii=False) + '。使用平台随包references/worker.md；'
              '资料从get_test_document(role=worker)读取，保留原目标、附件、模型、权限、现场与范围。'
              '收尾生成器机械通知后继，不承担兄弟模块调度。\n' + prompt)
    delivery_path = root / 'native-delivery.js'
    delivery_config = {'command': command, 'assignment_file': str(Path(assignment_file).absolute()),
        'directory': str(root), 'task_id': assignment['task_id'], 'node_id': assignment['node_id'],
        'output_file': assignment.get('delivery_output_file')}
    delivery_path.write_text('const config = ' + json.dumps(delivery_config, ensure_ascii=False)
                            + ';\n' + NATIVE_DELIVERY_TEMPLATE, encoding='utf-8')
    delivery_path.chmod(0o600)
    return {'script_file': str(path), 'delivery_script_file': str(delivery_path),
            'entry_url': entry_url, 'first_action': 'stage_ready' if stage_ready_script else 'environment_setup' if isolated else 'prepare',
            'stage_ready_script': stage_ready_script,
            'runtime': runtime, 'environment_setup': environment_setup,
            'environment_recovery_tool_arguments': ({'code': environment_recovery, 'timeout_ms': max(60000, 45000 * (options.get('context_count') or len((assignment.get('claim_arguments') or {}).get('account_ids') or []) or 1))} if isolated else None),
            'environment_tool_arguments': ({'code': environment_setup, 'timeout_ms': max(60000, 35000 * (options.get('context_count') or len((assignment.get('claim_arguments') or {}).get('account_ids') or []) or 1))} if isolated else None),
            'browser_bootstrap': None if runtime else browser_bootstrap,
            'browser_helper_file': str(browser_path), 'observation_file': str(root / 'observation-native.json'),
            'message_arguments': {'threadId': target_thread, 'prompt': prompt},
            'instructions': (('先 stage_ready；就绪后才 environment_setup 和 prepare；' if stage_ready_script else
                             '先在持久 node_repl 执行 environment_setup，成功后沿原 prepare；' if isolated else '首个工作调用 prepare；')
                + ('保存复用本轮接收器，不再次 record。实际关页后立即 closeout；加载回执匹配时只调用已加载函数，收到交接核对后先确认再整理。' if config.get('observation_stream') else '等待时结束，原事件后 resume:true。真实观察立即 record；实际关页后立即交还并发布。'))}


def native_ack_arguments(assignment, binding, event):
    """Typed original-event ACK; never infer receipt from a completed case."""
    for key in ('task_id', 'node_id'):
        if not event.get(key) or event[key] != assignment.get(key) or event[key] != binding.get(key):
            raise ValueError('交接事件与原任务绑定不一致')
    if not event.get('event_id') or event['event_id'] != binding.get('lease_id'):
        raise ValueError('交接事件与原领取事件不一致')
    reference = assignment.get('coordinator_ref')
    if not native_thread_target(reference):
        raise ValueError('缺少原协调会话，不能代确认')
    if not same_executor_ref(binding.get('coordinator_ref'), reference):
        raise ValueError('原协调会话绑定已变化')
    return {'action': 'dispatch', 'task_id': event['task_id'],
        'holder_id': assignment.get('coordinator_holder_id') or reference,
        'coordinator_ref': reference, 'request_id': 'native-ack-' + event['event_id'],
        'arguments': {'handoff_ack': {k: event[k] for k in ('task_id', 'node_id', 'event_id')}}}


def native_prepared_summary(directory, prepared):
    """Keep full observations off the terminal transport without losing design."""
    import time
    root = Path(directory).absolute()
    receipt = root / ('prepared-result-%s.json' % time.time_ns())
    write_private_json(receipt, prepared)
    # Resource-wait replies carry their original continuation command/reason.
    if not prepared.get('ready'):
        return {**prepared, 'full_receipt_file': str(receipt)}
    counts = {}
    for case in active_cases(prepared.get('cases', [])):
        status = case.get('status', 'not_run')
        counts[status] = counts.get(status, 0) + 1
    result = {key: prepared[key] for key in (
        'state', 'ready', 'resumed', 'reused', 'binding_file', 'design_file',
        'project_id', 'execution_id', 'revision', 'http_calls', 'seconds',
        'observation_receiver') if key in prepared}
    result.update(case_count=sum(counts.values()), case_counts=counts,
        full_receipt_file=str(receipt), detail_fields=sorted(prepared),
        details_notice='完整用例、检查点、覆盖缺口和账号环境均保留在私有回执及原设计；按当前用例读取，不重新请求或重放准备。统计不代表覆盖完成。')
    if prepared.get('native_call'):
        if len(prepared['native_call']) <= 8000:
            result['native_call'] = prepared['native_call']
        else:
            result['native_call_field'] = 'full_receipt_file.native_call'
    return result


def native_prepared_call(directory, prepared):
    """Supply the already-written call with this preparation's actual case ID."""
    path = Path(directory) / 'prepared-call.json'
    cases = prepared.get('cases') or []
    if not prepared.get('ready') or not path.exists() or len(cases) != 1:
        return None
    call = json.loads(read_utf8(path))
    binding = json.loads(read_utf8(Path(directory) / 'binding.json'))
    if not call.get('binding') or any(binding.get(k) != v for k, v in call['binding'].items()):
        raise ValueError('预制调用不属于本轮准备绑定')
    if cases[0].get('status', 'not_run') != 'not_run':
        return None
    return 'var nativeCaseId=' + json.dumps(cases[0]['case_id']) + ';\n' + call['source']
