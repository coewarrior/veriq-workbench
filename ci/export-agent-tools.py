"""Synchronize the no-install client's manifest with the actual MCP schemas."""
import asyncio
import hashlib
import json
from pathlib import Path

from api_test_tool.mcp_server import WorkspaceClient, create_server


async def main():
    root = Path(__file__).resolve().parents[1] / 'api_test_tool' / 'static'
    # One implementation for installed MCP and the self-contained download.
    client_path = root / 'api-test-client.py'
    source = client_path.read_text()
    start, end = '# BEGIN GENERATED DIRECT WAIT', '# END GENERATED DIRECT WAIT'
    helper = (root.parent / 'direct_wait.py').read_text()
    helper = helper.replace('from .direct_batch import batch_path, client_capabilities, compatible_batch, save_batch',
                            (root.parent / 'direct_batch.py').read_text())
    before, rest = source.split(start, 1)
    _, after = rest.split(end, 1)
    source = before + start + '\n' + helper + '\n' + end + after
    start, end = '# BEGIN GENERATED NATIVE HANDOFF', '# END GENERATED NATIVE HANDOFF'
    helper = (root.parent / 'native_client.py').read_text()
    helper += '\n' + (root.parent / 'checkpoint_results.py').read_text()
    helper += '\n' + (root.parent / 'native_identity.py').read_text()
    helper += '\n' + (root.parent / 'ui_case_scope.py').read_text()
    helper += '\n' + (root.parent / 'ui_payload_validation.py').read_text()
    helper += '\n' + (root.parent / 'cleanup_contract.py').read_text()
    helper += '\n' + (root.parent / 'testing_policy.py').read_text()
    helper += '\n' + (root.parent / 'native_lifecycle.py').read_text().replace(
        'from api_test_tool.native_identity import same_executor_ref, native_thread_target\n', '').replace(
        'from api_test_tool.checkpoint_results import reconcile_checkpoint_results, preserve_checkpoint_status_source\n', '').replace(
        'from api_test_tool.ui_case_scope import active_cases, is_superseded\n', '').replace(
        'from api_test_tool.ui_payload_validation import require_ui_payload_shape\n', '').replace(
        'from api_test_tool.testing_policy import case_excluded\n', '').replace(
        '        from api_test_tool.testing_policy import annotate_unexecuted\n', '')
    helper += '\n' + (root.parent / 'native_runtime.py').read_text()
    helper += '\n' + (root.parent / 'native_audit.py').read_text().replace(
        'from api_test_tool.ui_case_scope import active_cases, is_superseded\n', '')
    helper += '\n' + (root.parent / 'native_observation_receiver.py').read_text()
    helper += '\nNATIVE_CYCLE_TEMPLATE = ' + repr((root / 'native-cycle-exec.js').read_text()) + '\n'
    helper += '\nNATIVE_CONTROL_TEMPLATE = ' + repr((root / 'native-control-read.js').read_text()) + '\n'
    helper += '\nNATIVE_DELIVERY_TEMPLATE = ' + repr((root / 'native-delivery-exec.js').read_text()) + '\n'
    helper += '\nNATIVE_BROWSER_TEMPLATE = ' + repr((root / 'native-browser-case.js').read_text()) + '\n'
    helper += '\nNATIVE_ISOLATED_BROWSER_TEMPLATE = ' + repr((root / 'native-isolated-browser.mjs').read_text()) + '\n'
    helper += '\nNATIVE_OBSERVATION_SEND_TEMPLATE = ' + repr((root / 'native-observation-send.js').read_text()) + '\n'
    helper += '\nNATIVE_HANDOFF_TEMPLATE = ' + repr((root / 'native-handoff-exec.js').read_text()) + '\n'
    helper += '\nNATIVE_COORDINATOR_TEMPLATE = ' + repr((root / 'native-coordinator-wait.js').read_text()) + '\n'
    before, rest = source.split(start, 1)
    _, after = rest.split(end, 1)
    client_path.write_text(before + start + '\n' + helper + '\n' + end + after)
    path = root / 'agent-tools.json'
    manifest = json.loads(path.read_text())
    manifest['actions'].update({
        'withdraw_ui_test_asset': 'ui_asset_withdraw',
        'direct_test_session':'direct_session','list_account_projects':'managed_projects','bind_session_account_project':'managed_bind_project',
        'start_session_test':'managed_start','schedule_managed_test':'managed_create','get_managed_test':'managed_status',
        'control_managed_test':'managed_control','split_managed_test_module':'managed_split',
        'get_managed_test_report':'managed_report',
        'get_ui_design_reference': 'ui_design_reference',
        'get_requirement_design': 'requirement_design', 'save_requirement_design': 'save_requirement_design',
        'resolve_rule_question': 'resolve_rule_question', 'record_test_checkpoint': 'record_checkpoint',
        'resume_requirement_test': 'resume_requirement_test', 'get_test_capabilities': 'test_capabilities',
        'save_test_capabilities': 'save_test_capabilities', 'run_test_capability': 'run_test_capability',
        'get_test_experiment': 'test_experiment', 'coordinate_ui_resources': 'ui_resources',
    })
    server = create_server(WorkspaceClient('http://127.0.0.1:1'))
    manifest['instructions'] = server.instructions
    manifest['tools'] = [t.model_dump(mode='json', exclude_none=True) for t in await server.list_tools()]
    assert set(manifest['actions']) == {t['name'] for t in manifest['tools']}
    manifest['client_sha256'] = hashlib.sha256((root / 'api-test-client.py').read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    asyncio.run(main())
