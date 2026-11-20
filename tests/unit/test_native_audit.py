"""The delivery audit is deterministic and never retries business operations."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def audit(tmp_path):
    path = Path(__file__).parents[2] / 'api_test_tool/native_audit.py'
    spec = importlib.util.spec_from_file_location('native_audit_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 21, 8, 0, 30, tzinfo=timezone.utc)
    module.Path, module.json, module.datetime = Path, json, Clock
    module.read_utf8 = lambda p: Path(p).read_text(encoding='utf-8')
    module.write_private_json = lambda p, v: Path(p).write_text(json.dumps(v), encoding='utf-8')
    return module.audit_native_cycle


def write(root, name, value):
    (root / name).write_text(json.dumps(value), encoding='utf-8')


def stamp(seconds):
    return '2026-10-21T08:00:%02d+00:00' % seconds


def interval(name, a, b):
    return {'stage': name, 'started_at': stamp(a), 'finished_at': stamp(b)}


class Current:
    url = 'https://workspace.test'
    def __init__(self, status='passed'):
        self.calls = []
        self.status = status
    def call(self, tool, args):
        self.calls.append(tool)
        if tool == 'get_managed_test':
            return {'nodes': [{'id': 'n', 'state': 'completed', 'result': self.status}], 'leases': []}
        assert tool == 'get_ui_test_cases'
        return {'cases': [{'case_id': 'one', 'status': self.status}]}


def seed(root):
    write(root, 'binding.json', {'workspace_url': Current.url, 'task_id': 't', 'node_id': 'n',
                                'lease_id': 'l', 'project_id': 'p', 'execution_id': 'e'})
    write(root, 'run-ledger.json', {'task_id': 't', 'node_id': 'n', 'started_at': stamp(0),
                                    'kit_started_at': stamp(1), 'start_basis': '协调准备开始'})
    write(root, 'native-receiver.json', {'state': 'stopped'})
    write(root, 'native-receiver-response.json', {'saved': True, 'timing': {
        'save_started_at': stamp(10), 'save_finished_at': stamp(11)}})
    write(root, 'ack.json', {'handoff_complete': True, 'handoff': {
        'id': 'l', 'task_id': 't', 'node_id': 'n', 'delivery_state': 'received'},
        'handoff_timing': [interval('coordinator_ack', 18, 22)]})
    write(root, 'native-call-timing.json', {'started_at': stamp(8), 'finished_at': stamp(11)})
    write(root, 'observation-inbox-one.json', {'case_id': 'one', 'status': 'passed',
        'checks': [{'name': 'visible', 'expected': True, 'observed': True, 'ok': True}],
        'timing': {'started_at': stamp(8), 'last_assertion_at': stamp(9), 'browser_closed_at': stamp(10)}})
    write(root, 'cycle-prepare-1.json', {'action': 'prepare', 'stages': [interval('prepare', 2, 5)], 'result': {}})
    write(root, 'closeout-result.json', {'publication': {'phase': 'published', 'url': '/reports/one'}})


def test_complete_summary_partitions_parallel_ack_without_double_counting(audit, tmp_path):
    seed(tmp_path)
    write(tmp_path, 'cycle-closeout-2.json', {'action': 'closeout',
        'stages': [interval('closeout_generate', 13, 14), interval('release_publish_handoff', 14, 20)],
        'result': {'publication': {'phase': 'published'}, 'warnings': ['保留动态告警']}})
    client = Current()
    out = audit(client, tmp_path/'binding.json', tmp_path/'audit.json', tmp_path/'ack.json')
    summary = out['summary']
    assert client.calls == ['get_managed_test', 'get_ui_test_cases']
    assert summary['total_to_report_seconds'] == 30
    assert sum(row['seconds'] for row in summary['timeline']) == 30
    assert any(row['seconds'] == 2 and '并行' in row['stage'] for row in summary['timeline'])
    assert summary['passed_cases'] == summary['case_count'] == 1
    assert summary['check_count'] == summary['passed_checks'] == 1
    assert summary['remaining'] == []
    assert any('保留动态告警' in item['value'] for item in summary['warnings'])
    page = (tmp_path/'audit.html').read_text()
    assert '30.0 秒' in page and '完整顶层时间轴' in page and '保留动态告警' in page
    assert json.loads((tmp_path/'audit.json').read_text())['summary'] == summary


def test_fast_ack_uses_saved_publication_without_waiting_for_worker_log(audit, tmp_path):
    seed(tmp_path)
    out = audit(Current(), tmp_path/'binding.json', tmp_path/'audit.json', tmp_path/'ack.json')
    assert out['checks']['report_published'] is True
    assert any(item['stage'] == 'closeout' for item in out['summary']['unknown'])
    assert not (tmp_path/'cycle-closeout-2.json').exists()


def test_missing_timing_and_failed_assertions_stay_visible_even_when_lifecycle_settled(audit, tmp_path):
    seed(tmp_path)
    (tmp_path/'run-ledger.json').unlink()
    (tmp_path/'native-call-timing.json').unlink()
    write(tmp_path, 'observation-inbox-one.json', {'case_id': 'one', 'status': 'failed',
        'checks': [{'name': '<script>', 'expected': 'yes', 'observed': 'no', 'ok': False}],
        'error': '真实页面不一致'})
    out = audit(Current('failed'), tmp_path/'binding.json', tmp_path/'audit.json', tmp_path/'ack.json')
    summary = out['summary']
    assert summary['total_to_report_seconds'] is None
    assert summary['timeline'] == []
    assert summary['failed_cases'] == ['one']
    assert summary['failed_assertions'][0]['observed'] == 'no'
    assert summary['remaining'] == []  # settled lifecycle is not a business pass
    assert summary['errors'] and summary['unknown']
    page = (tmp_path/'audit.html').read_text()
    assert '<script>' not in page and '&lt;script&gt;' in page


def test_foreign_run_ledger_and_existing_html_are_not_overwritten(audit, tmp_path):
    seed(tmp_path)
    write(tmp_path, 'run-ledger.json', {'task_id': 'foreign', 'node_id': 'n', 'started_at': stamp(0)})
    client = Current()
    with pytest.raises(ValueError, match='台账'):
        audit(client, tmp_path/'binding.json', tmp_path/'audit.json', tmp_path/'ack.json')
    assert client.calls == []
    (tmp_path/'audit.html').write_text('prior evidence')
    with pytest.raises(ValueError, match='不能覆盖'):
        audit(client, tmp_path/'binding.json', tmp_path/'audit.json', tmp_path/'ack.json')
    assert (tmp_path/'audit.html').read_text() == 'prior evidence'


def test_coordinator_stages_and_server_wait_evidence_are_preserved(audit, tmp_path):
    seed(tmp_path)
    ledger = json.loads((tmp_path/'run-ledger.json').read_text())
    ledger['stages'] = [interval('客户端核验与派发', 0, 2)]
    write(tmp_path, 'run-ledger.json', ledger)
    processing = [{'stage': 'schedule', 'seconds': 0.42}]
    wait = {'http_calls': 1, 'elapsed_seconds': 0.75}
    handoff = {**interval('release_publish', 13, 17),
               'server_processing_timing': processing, 'client_wait': wait}
    write(tmp_path, 'cycle-closeout-2.json', {'action': 'closeout',
        'stages': [interval('release_publish_handoff', 13, 20)],
        'result': {'handoff_timing': [handoff]}})
    ack = json.loads((tmp_path/'ack.json').read_text())
    ack['handoff_timing'][0].update(server_processing_timing=processing, client_wait=wait)
    write(tmp_path, 'ack.json', ack)
    out = audit(Current(), tmp_path/'binding.json', tmp_path/'audit.json', tmp_path/'ack.json')
    timeline = out['summary']['timeline']
    assert timeline[0]['stage'] == '客户端核验与派发'
    assert timeline[0]['seconds'] == 2
    evidence = json.loads((tmp_path/'audit.json').read_text())['stages']
    for name in ('release_publish', 'coordinator_ack'):
        item = next(s for s in evidence if s['stage'] == name)
        assert item['server_processing_timing'] == processing
        assert item['client_wait'] == wait
    page = (tmp_path/'audit.html').read_text()
    assert '平台处理与客户端等待实测' in page and 'elapsed_seconds' in page


def test_report_endpoint_is_sampled_after_complete_html_is_written(audit, tmp_path):
    seed(tmp_path)
    class WrittenClock(datetime):
        @classmethod
        def now(cls, tz=None):
            # Simulate one second spent rendering/writing the actual report.
            return cls(2026, 10, 21, 8, 0, 31 if (tmp_path/'audit.html').exists() else 30,
                       tzinfo=timezone.utc)
    audit.__globals__['datetime'] = WrittenClock
    out = audit(Current(), tmp_path/'binding.json', tmp_path/'audit.json', tmp_path/'ack.json')
    summary = out['summary']
    assert summary['report_ready_at'] == stamp(31)
    assert summary['total_to_report_seconds'] == 31
    assert sum(row['seconds'] for row in summary['timeline']) == 31
    assert summary['timeline'][-1]['stage'] == '当前状态核验与报告整理'
    assert summary['timeline'][-1]['seconds'] == 1
    assert '31.0 秒' in (tmp_path/'audit.html').read_text()
    assert json.loads((tmp_path/'audit.json').read_text())['summary'] == summary


def test_multiple_native_calls_and_observations_remain_independent(audit, tmp_path):
    seed(tmp_path)
    (tmp_path/'native-call-timing.json').unlink()
    write(tmp_path, 'native-call-timing-100-a.json', {
        'case_id': 'one', 'started_at': stamp(8), 'finished_at': stamp(10)})
    write(tmp_path, 'native-call-timing-200-b.json', {
        'case_id': 'two', 'started_at': stamp(11), 'finished_at': stamp(13)})
    write(tmp_path, 'observation-inbox-two.json', {'case_id': 'two', 'status': 'passed',
        'checks': [{'name': 'second independent check', 'expected': 2, 'observed': 2, 'ok': True}],
        'timing': {'started_at': stamp(11), 'last_assertion_at': stamp(12), 'browser_closed_at': stamp(13)}})
    class TwoCases(Current):
        def call(self, tool, args):
            result = super().call(tool, args)
            if tool == 'get_ui_test_cases':
                result['cases'].append({'case_id': 'two', 'status': 'passed'})
            return result
    out = audit(TwoCases(), tmp_path/'binding.json', tmp_path/'audit.json', tmp_path/'ack.json')
    summary = out['summary']
    native_intervals = [s for s in summary['timeline'] if s['stage'] == '原生开页、完整检查、关页与保存']
    assert len(native_intervals) == 2
    assert sum(s['seconds'] for s in native_intervals) == 4
    data = json.loads((tmp_path/'audit.json').read_text())
    assert {s['case_id'] for s in data['stages'] if s['stage'] == 'native_call'} == {'one', 'two'}
    assert len(data['observations']) == 2
    assert summary['case_count'] == summary['check_count'] == summary['passed_checks'] == 2
    assert not any(s.get('stage') == 'native_call' for s in summary['unknown'])
