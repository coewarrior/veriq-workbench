"""Offline CLI help checks; no credentials, business calls or network requests."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).parents[2] / 'api_test_tool/static/api-test-client.py'
spec = importlib.util.spec_from_file_location('tool_help_client', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CATALOG = json.loads(SOURCE.with_name('agent-tools.json').read_text(encoding='utf-8'))


class ToolHelpTests(unittest.TestCase):
    def run_cli(self, catalog, *arguments):
        client = module.Client('http://127.0.0.1:18089')
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(module, 'Client', return_value=client), \
                patch.object(client, 'request', return_value=catalog) as request, \
                patch.object(client, 'call') as call, \
                patch.object(module.sys, 'argv', ['client', '--url', client.url, 'tools', *arguments]), \
                redirect_stdout(output), redirect_stderr(errors):
            exit_code = 0
            try:
                module.main()
            except SystemExit as error:
                exit_code = error.code
            self.assertIs(client.tools(), catalog)
            request.assert_called_once_with('/static/agent-tools.json')
            call.assert_not_called()
        return exit_code, output.getvalue(), errors.getvalue()

    def test_default_output_is_unchanged_complete_json(self):
        code, output, errors = self.run_cli(CATALOG)
        self.assertEqual((code, errors), (0, ''))
        self.assertEqual(output, json.dumps(CATALOG, ensure_ascii=False, indent=2) + '\n')

    def test_each_real_tool_is_complete_and_global_fields_are_retained(self):
        original = copy.deepcopy(CATALOG)
        for tool in CATALOG['tools']:
            with self.subTest(name=tool['name']):
                code, output, errors = self.run_cli(CATALOG, '--name', tool['name'])
                self.assertEqual((code, errors), (0, ''))
                result = json.loads(output)
                self.assertEqual(result['tools'], [tool])
                self.assertEqual(result['actions'], {tool['name']: CATALOG['actions'][tool['name']]})
                for key in CATALOG.keys() - {'tools', 'actions'}:
                    self.assertEqual(result[key], CATALOG[key])
        self.assertEqual(CATALOG, original)

    def test_unknown_fields_definitions_and_annotations_survive(self):
        catalog = copy.deepcopy(CATALOG)
        tool = catalog['tools'][0]
        tool['future_tool_field'] = {'opaque': [False, 0, None, '中文']}
        tool['annotations']['future_annotation'] = {'nested': True}
        tool['inputSchema']['$defs'] = {'Future': {'type': 'string', 'future_schema_field': 7}}
        tool['inputSchema']['properties']['future_argument'] = {'$ref': '#/$defs/Future'}
        catalog['future_global_field'] = {'requirements': ['保留全局说明']}
        catalog['$defs'] = {'RootDefinition': {'enum': ['a', 'b']}}
        catalog['actions'][tool['name']] = {'route': '/future', 'future_action_field': None}
        original = copy.deepcopy(catalog)
        code, output, errors = self.run_cli(catalog, '--name', tool['name'])
        self.assertEqual((code, errors), (0, ''))
        result = json.loads(output)
        self.assertEqual(result['tools'], [tool])
        self.assertEqual(result['actions'][tool['name']], catalog['actions'][tool['name']])
        for key in catalog.keys() - {'tools', 'actions'}:
            self.assertEqual(result[key], catalog[key])
        self.assertEqual(catalog, original)

    def test_name_is_exact_and_unknown_names_have_no_business_call(self):
        for name in ('save_ui_test', 'SAVE_UI_TEST_CASES', '', 'does_not_exist'):
            with self.subTest(name=name):
                code, output, errors = self.run_cli(CATALOG, '--name', name)
                self.assertEqual((code, output), (1, ''))
                self.assertIn('未知工具名称：' + name, errors)
                self.assertIn('tools', errors)

    def test_missing_name_value_is_an_argument_error(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(module, 'Client') as client, \
                patch.object(module.sys, 'argv', ['client', '--url', 'http://127.0.0.1:18089', 'tools', '--name']), \
                redirect_stdout(output), redirect_stderr(errors), \
                self.assertRaises(SystemExit) as stopped:
            module.main()
        self.assertEqual(stopped.exception.code, 2)
        self.assertEqual(output.getvalue(), '')
        self.assertIn('--name', errors.getvalue())
        client.assert_not_called()


if __name__ == '__main__':
    unittest.main()
