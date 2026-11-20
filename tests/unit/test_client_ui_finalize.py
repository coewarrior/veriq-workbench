"""Offline checks of the client transport; no workspace or business requests."""
import importlib.util
from contextlib import redirect_stdout
import io
import json
from pathlib import Path

import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).parents[2] / 'api_test_tool/static/api-test-client.py'
spec = importlib.util.spec_from_file_location('finalize_client', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LocalClient(module.Client):
    def __init__(self, fail=None):
        super().__init__('http://127.0.0.1:18089')
        self.calls = []
        self.fail = fail


    def call(self, name, args):
        self.calls.append((name, args))
        if self.fail == name:
            raise ValueError('request outcome unknown')
        if name == 'save_ui_test_cases':
            return {'execution_id': 'round', 'revision': args['revision'] + 1,
                    'coverage_check': {'failed_without_screenshot': ['C1']}}
        assert name == 'finish_test_workflow'
        return {'report': {'id': 'report'}, 'total_report': {'report_url': '/total'},
                'revision':args['revision']+1, 'coverage_check':{'failed_without_screenshot':['C1']}}


def final_input():
    return {'summary': '真实剩余缺口', 'review_notes': '保留未执行设计',
            'cases': [{'case_id': 'C1', 'status': 'blocked', 'actual': '仍缺独立角色'}],
            'scene_outcome': {'status': 'partial', 'items': [
                {'case_id': 'C1', 'name': 'repro', 'kind': 'data', 'state': 'retained', 'reason': '复现'}]}}


class FinalizationChecks(unittest.TestCase):
    def test_finalize_reports_existing_shape_errors_together(self):
        client = LocalClient()
        payload = {'cases': [{'case_id': 'C1', 'status': 'failed', 'actual': '差异', 'action_required': '人工处理'}],
            'coverage': [{'coverage_id': 'same', 'feature': ''}, {'coverage_id': 'same', 'feature': '区域'}],
            'review_notes': {'not': 'text'}}
        with self.assertRaises(ValueError) as raised:
            client.finalize_ui_test_round('project', 'round', 4, payload, self.path)
        message = str(raised.exception)
        for field in ('coverage[0].feature', 'coverage[1].coverage_id', 'review_notes'):
            self.assertIn(field, message)
        self.assertEqual(client.calls, [])
        self.assertEqual(payload['cases'][0]['status'], 'failed')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'receipt.json'

    def test_one_save_then_publish_and_completed_receipt_reuse(self):
        client = LocalClient()
        payload = final_input()
        result = client.finalize_ui_test_round('project', 'round', 4, payload, self.path)
        self.assertEqual([name for name, _ in client.calls], ['finish_test_workflow'])
        self.assertEqual({k:client.calls[0][1][k] for k in ('project_id','execution_id','revision','cases','review_notes','scene_outcome')}, {
            'project_id': 'project', 'execution_id': 'round', 'revision': 4,
            **{k: payload[k] for k in ('cases', 'review_notes', 'scene_outcome')}})
        self.assertEqual(result['revision'], 5)
        self.assertEqual(result['publication']['coverage_check']['failed_without_screenshot'], ['C1'])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(client.finalize_ui_test_round('project', 'round', 4, payload, self.path), result)
        self.assertEqual(len(client.calls), 1)

        with self.assertRaisesRegex(ValueError, '不同输入'):
            client.finalize_ui_test_round('project', 'round', 5, payload, self.path)
        self.assertEqual(len(client.calls), 1)

    def test_file_preflight_collects_errors_before_any_encode_or_write(self):
        fixture = Path(self.temp.name) / 'data.txt'
        fixture.write_text('synthetic fixture', encoding='utf-8')
        entries = [{'file': str(fixture), 'case_id': 'C1', 'step': 'input', 'kind': 'fixture'},
                   {'file': str(fixture.with_name('missing.txt')), 'case_id': 'absent', 'step': 'input'}]
        cases = [{'case_id': 'C1', 'test_data': 'different.txt'}]
        checked = module.check_file_manifest(entries, cases)
        self.assertEqual({i['code'] for i in checked['issues']},
                         {'file_not_readable', 'unknown_case_id'})
        client = LocalClient()
        with patch.object(client, 'asset_from_file', side_effect=AssertionError('must not encode')):
            with self.assertRaisesRegex(ValueError, '尚未上传'):
                client.upload_assets_from_files('project', 'round', entries, cases)
        self.assertEqual(client.calls, [])
        cases[0]['test_data'] = 'Use DATA.TXT as input'
        self.assertTrue(module.check_file_manifest(entries[:1], cases)['valid'])

    def test_uncertain_save_or_publish_never_retries(self):
        for failure, phase, revision, count in [
                ('finish_test_workflow', 'publish_unverified', 4, 1)]:
            with self.subTest(failure=failure):
                path = self.path.with_name(failure + '.json')
                client = LocalClient(failure)
                with self.assertRaisesRegex(ValueError, 'unknown'):
                    client.finalize_ui_test_round('project', 'round', 4, final_input(), path)
                receipt = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual((receipt['phase'], receipt['revision']), (phase, revision))
                with self.assertRaisesRegex(ValueError, '只读核对'):
                    client.finalize_ui_test_round('project', 'round', 4, final_input(), path)
                self.assertEqual(len(client.calls), count)

    def test_no_changes_publishes_without_rewriting(self):
        client = LocalClient()
        client.finalize_ui_test_round('project', 'round', 4, {'summary': '保留真实缺口'}, self.path)
        self.assertEqual([name for name, _ in client.calls], ['finish_test_workflow'])

    def test_composite_failure_status_alone_cannot_prove_no_save(self):
        client = LocalClient()
        with patch.object(client, 'call', side_effect=module.ClientHTTPError(400, 'synthetic rejection')):
            with self.assertRaises(module.ClientHTTPError):
                client.finalize_ui_test_round('project', 'round', 4, final_input(), self.path)
        receipt = json.loads(self.path.read_text())
        self.assertEqual(receipt['phase'], 'publish_unverified')

    def test_experiment_only_finalization_preserves_unknowns_and_exact_end_time(self):
        client = LocalClient()
        experiment = {'execution_finished_at': '2026-10-11T08:02:00Z', 'tool_errors': 0, 'tool_calls': None}
        client.finalize_ui_test_round('project', 'round', 4,
                                     {'summary': '发布发生在执行结束之后', 'experiment': experiment}, self.path)
        self.assertEqual([name for name, _ in client.calls], ['finish_test_workflow'])
        self.assertEqual(client.calls[0][1]['experiment'], experiment)
        self.assertEqual(client.calls[0][1]['cases'], [])

    def test_invalid_input_never_invents_a_fix_or_writes(self):
        for change in [
                {'cases': [{'case_id': 'C1'}, {'case_id': ' C1 '}]},
                {'scene_outcome': {'status': 'cleaned', 'items': 'invalid-shape'}},
                {'summary': None}]:
            with self.subTest(change=change):
                client = LocalClient()
                with self.assertRaises(ValueError):
                    client.finalize_ui_test_round('project', 'round', 4, {**final_input(), **change}, self.path)
                self.assertEqual(client.calls, [])
                self.assertFalse(self.path.exists())

    def test_utf8_stdin_and_bom_ignore_ascii_locale(self):
        content = '\ufeff{"summary":"中文收尾"}'.encode('utf-8')
        stdin = io.TextIOWrapper(io.BytesIO(content), encoding='ascii')
        with patch.object(module.sys, 'stdin', stdin):
            self.assertEqual(json.loads(module.read_utf8('-'))['summary'], '中文收尾')
        self.path.write_bytes(content)
        self.assertEqual(json.loads(module.read_utf8(self.path))['summary'], '中文收尾')

    def test_duplicate_updates_fail_before_request(self):
        client = module.Client('http://127.0.0.1:18089', self.path)
        client.manifest = {'tools': [{'name': 'save_ui_test_cases', 'inputSchema': {
            'required': ['project_id', 'cases'], 'properties': {}}}], 'actions': {}}
        with self.assertRaisesRegex(ValueError, '第 1、2 项'):
            client.call('save_ui_test_cases', {'project_id': 'project', 'cases': [
                {'case_id': 'C1'}, {'case_id': 'C1'}]})

    def test_receipt_symlink_rejected_before_request(self):
        self.path.symlink_to(self.path.with_name('other.json'))
        client = LocalClient()
        with self.assertRaisesRegex(ValueError, '符号链接'):
            client.finalize_ui_test_round('project', 'round', 4, final_input(), self.path)
        self.assertEqual(client.calls, [])

    def test_corrupt_receipt_stops_without_overwrite(self):
        self.path.write_text('[]', encoding='utf-8')
        client = LocalClient()
        with self.assertRaisesRegex(ValueError, '回执格式无效'):
            client.finalize_ui_test_round('project', 'round', 4, final_input(), self.path)
        self.assertEqual(client.calls, [])
        self.assertEqual(self.path.read_text(), '[]')

    def test_optional_cli_summary_preserves_receipt_requests_and_default_output(self):
        payload = final_input()
        input_file = self.path.with_name('finalization.json')
        input_file.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        client = LocalClient()
        args = ['client', '--url', client.url, 'finalize-ui', '--project', 'project',
                '--execution', 'round', '--revision', '4', '--input-file', str(input_file),
                '--receipt-file', str(self.path)]
        output = io.StringIO()
        with patch.object(module, 'Client', return_value=client), patch.object(module.sys, 'argv', args), redirect_stdout(output):
            module.main()
        receipt_bytes = self.path.read_bytes()
        full_result = json.loads(receipt_bytes)['result']
        self.assertEqual(output.getvalue(), json.dumps(full_result, ensure_ascii=False, indent=2) + '\n')
        calls = list(client.calls)

        output = io.StringIO()
        with patch.object(module, 'Client', return_value=client), patch.object(module.sys, 'argv', args + ['--summary']), redirect_stdout(output):
            module.main()
        brief = json.loads(output.getvalue())
        self.assertEqual(client.calls, calls)
        self.assertEqual(self.path.read_bytes(), receipt_bytes)
        self.assertEqual(brief['revision'], full_result['revision'])
        self.assertEqual(brief['report'], full_result['publication']['report'])
        self.assertEqual(brief['receipt_file'], str(self.path.absolute()))
        self.assertIn('不作质量判定', brief['notice'])
        self.assertIn('blocked', json.dumps(client.calls, ensure_ascii=False))

        # Starting with summary selected must also keep the full saved receipt.
        first_summary_path = self.path.with_name('first-summary.json')
        first_summary_client = LocalClient()
        summary_args = args[:-1] + [str(first_summary_path), '--summary']
        with patch.object(module, 'Client', return_value=first_summary_client), patch.object(module.sys, 'argv', summary_args), redirect_stdout(io.StringIO()):
            module.main()
        self.assertEqual(first_summary_path.read_bytes(), receipt_bytes)
        self.assertEqual(first_summary_client.calls, calls)

    def test_summary_keeps_different_and_unknown_checks_and_exact_sources(self):
        checks = {'failed_without_screenshot': ['C1'], 'future_check': {'status': 'not_run'},
                  'guidance': '保留实际缺口，不能推导通过'}
        result = {'execution_id': 'round', 'revision': 5,
                  'future_result': {'status': 'failed'},
                  'save_result': {'execution_id': 'round', 'revision': 5,
                                  'coverage_check': checks, 'future_warning': False,
                                  'scene_outcome': {'status': 'partial', 'items': [{'state': 'unverified'}]}},
                  'publication': {'report': {'report_url': '/report'}, 'coverage_check': dict(checks),
                                  'future_warning': 0, 'summary': '仍有未执行'}}
        original = json.dumps(result, ensure_ascii=False)
        brief = module.summarize_ui_finalization(result, self.path)
        reminders = [item for item in brief['details'] if item['field'] == 'coverage_check']
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]['sources'], ['publication.coverage_check', 'save_result.coverage_check'])
        self.assertEqual(reminders[0]['value'], checks)
        self.assertEqual(brief['sources']['revision'], ['revision', 'save_result.revision'])
        self.assertEqual(len([item for item in brief['details'] if item['field'] == 'future_warning']), 2)
        self.assertIn({'field': 'future_result', 'sources': ['future_result'], 'value': {'status': 'failed'}}, brief['details'])
        self.assertEqual(json.dumps(result, ensure_ascii=False), original)

        result['publication']['coverage_check'] = {**checks, 'future_check': {'status': 'blocked'}}
        brief = module.summarize_ui_finalization(result, self.path)
        self.assertEqual(len([item for item in brief['details'] if item['field'] == 'coverage_check']), 2)

    def test_summary_cli_keeps_uncertain_receipt_recovery_behavior(self):
        input_file = self.path.with_name('finalization.json')
        input_file.write_text(json.dumps(final_input()), encoding='utf-8')
        client = LocalClient('finish_test_workflow')
        args = ['client', '--url', client.url, 'finalize-ui', '--project', 'project',
                '--execution', 'round', '--revision', '4', '--input-file', str(input_file),
                '--receipt-file', str(self.path), '--summary']
        for expected in ('unknown', '只读核对'):
            error = io.StringIO()
            with patch.object(module, 'Client', return_value=client), patch.object(module.sys, 'argv', args), patch.object(module.sys, 'stderr', error):
                with self.assertRaises(SystemExit):
                    module.main()
            self.assertIn(expected, error.getvalue())
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(json.loads(self.path.read_text())['phase'], 'publish_unverified')


if __name__ == '__main__':
    unittest.main()
