"""Platform-wide scope exclusions, separate from resource availability and verdicts."""
import re

POLICY_ID = 'multi_account_excluded'
REASON = '不测（用户明确排除多账号场景）'
GUIDANCE = (
    '当前平台全局范围：多账号、双账号、跨账号及跨租户对照/隔离业务场景一律'
    + REASON + '。保留具体设计和已有真实结果；未执行项使用 not_run，'
    'not_run_reason 填写上述原因；UI cases.account_scope、API design.account_scope 使用 multi_account/cross_account/cross_tenant 明确范围。'
    '不算通过，不申请第二账号、不等待账号集合、'
    '不为其创建执行会话或续接，不另做替代测试。普通继续测试/重测不解除此规则。'
    '不同模块各用一个账号并发仍允许；单账号权限、匿名及其他适用风险覆盖保持。'
    '已有真实对象责任的必要清理和无需账号的报告仍按原授权及回收协议处理，不扩展业务测试。'
)

_MULTI = re.compile(
    r'(?:多|双|跨|两|两个|2个)[\s_-]*(?:账|帐)号|(?:跨|不同|多个|两个)[\s_-]*租户'
    r'|\b(?:multi|dual|cross|two)[\s_-]*accounts?\b|\bcross[\s_-]*tenant\b', re.I)


def snapshot():
    return {'id': POLICY_ID, 'multi_account_testing': False, 'reason': REASON,
            'guidance': GUIDANCE, 'independent_single_account_modules': True}


def resource_excluded(value, state=None):
    """Preferred account IDs are alternatives, not simultaneous requirements."""
    if value.get('requires_account') is False or value.get('phase') == 'report' or cleanup_allowed(state, value):
        return False
    required = value.get('requested_account_ids', value.get('account_ids', [])) or []
    if value.get('account_selection') == 'preferred':
        required = []
    return len(set(required)) > 1 or len(value.get('requirements') or []) > 1


def case_excluded(case):
    # Only the case's declared purpose/scope is used, not evidence, arbitrary
    # documents, module names, or dependency descriptions mentioning exclusions.
    design = case.get('design') or {}
    if not isinstance(design, dict):
        design = {}
    scope = case.get('account_scope') or design.get('account_scope')
    declared_multi = scope in {'multi_account', 'cross_account', 'cross_tenant'} or any(
        _MULTI.search(str(v or '')) for v in
        (case.get('scenario'), case.get('title'), design.get('title'), design.get('objective')))
    if declared_multi:
        return True
    if scope == 'single_account':
        return False  # A corrected design outranks a derived, stale exclusion marker.
    return case.get('execution_disposition') == POLICY_ID or case.get('not_run_reason') == REASON


def has_observations(case):
    return (case.get('status') in {'passed', 'failed', 'partial'} or bool(case.get('executed_at'))
            or any(p.get('status') in {'passed', 'failed', 'partial'} or p.get('actual') or p.get('observed')
                   for p in case.get('checkpoints', [])))


def annotate_unexecuted(case):
    """Normalize new saves or a detached report projection; retain real observations."""
    if has_observations(case):
        return False
    if case_excluded(case):
        case.update(status='not_run', not_run_reason=REASON,
                    execution_disposition=POLICY_ID, blocked_by=[], executed_at='')
        return True
    if case.get('execution_disposition') == POLICY_ID:
        case['execution_disposition'] = ''
        if case.get('not_run_reason') == REASON:
            case['not_run_reason'] = '已纠正为单账号场景，业务尚未验证。'
        return True
    return False


def excluded_response(**extra):
    return {'state': 'not_tested', 'excluded': True, 'reason': REASON,
            'testing_policy': snapshot(), 'account_ready': False,
            'stage_ready': False, 'continued': False, 'release_required': False,
            'account_ids': [], 'required_context_count': 0,
            'next_action': 'skip_excluded_scenario', 'end_turn': False, **extra}


def cleanup_allowed(state, node):
    """Only original, server-recorded cleanup responsibilities may use old resources."""
    if not state or not node.get('policy_cleanup_unit_id'):
        return False
    unit = next((u for u in node.get('checkpoint', {}).get('work_plan', {}).get('units', [])
                 if u['id'] == node['policy_cleanup_unit_id'] and u.get('purpose') == 'cleanup'), None)
    if not unit or not unit.get('cleanup_responsibility_ids'):
        return False
    from .cleanup_capabilities import continuation_sources
    sources = {node['id']} | continuation_sources(state, node)
    case_ids = set(unit['case_ids']) | {p['case_id'] for p in unit['checkpoint_refs']}
    objects = [state.get('cleanup_objects', {}).get(key) for key in unit['cleanup_responsibility_ids']]
    if not all(obj and obj['owner'] == node['owner'] and obj['task_id'] == node['task_id']
               and obj['source_node_id'] in sources and obj['case_id'] in case_ids for obj in objects):
        return False
    if all(obj['state'] in {'cleaned', 'retained', 'residual'} and not obj.get('consumers')
           and not obj.get('retain_scene') for obj in objects):
        return False
    req = unit['requires']
    if node.get('phase') != req['phase'] or node.get('requirements', []) != req['requirements']:
        return False
    requested = set(node.get('requested_account_ids', []))
    declared = set(req['account_ids']) if req['account_selection'] == 'required' else set()
    return requested == declared or not declared and requested <= {obj['account_id'] for obj in objects}


def node_excluded(node, state=None):
    if node.get('phase') == 'report' or cleanup_allowed(state, node):
        return False
    if node.get('checkpoint', {}).get('work_plan'):
        from .native_work_plan import record_view
        from .execution_work_plan import project_work_candidates
        record = record_view(state, node) if state else None
        if record is None:
            return False  # Unreadable evidence never converts a legitimate pending stage.
        try:
            candidates = project_work_candidates(node, record)
        except ValueError:
            return False  # Let the existing per-node invalid-plan path explain it.
        return (any(c['eligibility'] == 'excluded' for c in candidates)
                and all(c['eligibility'] in {'completed', 'excluded'} for c in candidates))
    return (node.get('execution_disposition') == POLICY_ID or case_excluded({'title': node.get('title')})
            or resource_excluded(node, state))


def exclude_unallocated_node(node, state=None):
    if node.get('state') == 'queued' and node_excluded(node, state):
        node.update(state='blocked', reason=REASON, result='not_run',
                    execution_disposition=POLICY_ID, reservation=None, protected=False)
        node.pop('resource_wait', None)
        return True
    return False
