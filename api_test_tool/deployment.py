"""Deployment closes new allocations while preserving original writes/exit ACKs.

These exemptions never grant access: normal endpoint authentication, ownership,
scope, revision and lease checks still run.
"""
import re


def dispatch_receipt(args):
    """Only existing coordination receipts, never new modules or send grants."""
    values = args.get('arguments')
    if not isinstance(values, dict):
        return False
    if set(values) == {'observe'}:
        return values['observe'] is True
    if set(values) in ({'coordinator_closeout'}, {'desktop_observations'}, {'executor_status'}):
        return True
    if (values.get('modules') or values.get('continuation_group') is not None
            or set(values) - {'modules', 'handoff_ack', 'handoff_delivery'}
            or not isinstance(values.get('handoff_ack'), dict)):
        return False
    receipt = values.get('handoff_delivery')
    return receipt is None or (isinstance(receipt, dict) and receipt.get('state') in {'sent', 'unknown', 'blocked'})


def continuation(method, path, payload=None):
    if method in {'GET', 'HEAD', 'OPTIONS'} or path == '/api/managed-host/call':
        return True
    if path == '/api/mcp/call' and isinstance(payload, dict):
        action, args = payload.get('action'), payload.get('arguments', {})
        if not isinstance(args, dict):
            return False
        if action == 'direct_session':
            if args.get('action') == 'dispatch':
                return dispatch_receipt(args)
            values = args.get('arguments')
            receipt = values.get('handoff_delivery') if isinstance(values, dict) else None
            if (args.get('action') == 'finish' and isinstance(receipt, dict)
                    and receipt.get('state') == 'sending'):
                return False
            return args.get('action') in {
                'context', 'result', 'record', 'checkpoint', 'cleanup',
                'finish', 'reconcile', 'browser', 'credentials', 'wait', 'continue',
                'channel'}
        if action == 'managed_control':
            return args.get('action') in {'stop', 'pause', 'confirm_native_exit'}
        if action in {'managed_status', 'managed_report', 'managed_projects', 'managed_split',
                      'workspace', 'list_sessions', 'job'}:
            return True
        return bool(args.get('project_id')) and action in {
            'context', 'document', 'report', 'workflow_status', 'test_attachment',
            'ui_read', 'ui_design_reference', 'ui_cases', 'ui_asset', 'ui_assets', 'ui_publish', 'ui_correct',
            'progress', 'finish_workflow', 'task_report', 'save_materials',
            'ui_dependency_check', 'ui_retest_inputs', 'ui_retest_file', 'ui_resources',
            'requirement_design', 'save_requirement_design', 'resolve_rule_question',
            'record_checkpoint', 'test_capabilities', 'save_test_capabilities',
            'run_test_capability', 'test_experiment', 'defect_decisions'}
    if re.fullmatch(r'/api/orchestration/tasks/[^/]+/control', path):
        return isinstance(payload, dict) and payload.get('action') in {'stop', 'pause', 'confirm_native_exit'}
    if method == 'DELETE' and re.fullmatch(r'/api/projects/[^/]+', path):
        return True
    return bool(re.fullmatch(
        r'/api/orchestration/(?:nodes/[^/]+/split|leases/[^/]+/(?:resolve|human-mode)|console(?:/[^/]+/(?:command|close))?)'
        r'|/api/(?:projects|ui-tests)/[^/]+/attachments(?:/[^/]+)?'
        r'|/api/ui-tests/[^/]+/(?:requirements|materials|capabilities|questions/[^/]+|executions/[^/]+/checkpoints/[^/]+/[^/]+)'
        r'|/api/projects/[^/]+/reports/[^/]+/(?:rule-questions/[^/]+|retest-inputs|ui-actions/[^/]+|case-corrections/[^/]+|report-corrections|title-corrections|pingcode/batches/jobs/[^/]+/stop)'
        r'|/api/jobs/[^/]+/stop-load', path))
