"""Local synthetic records only: blocker facts and explicit split history."""
from copy import deepcopy
import pytest
from api_test_tool import ui_dependencies, ui_records
from test_ui_dependencies import case, dependency, check
from fastapi.testclient import TestClient
from api_test_tool.web import create_app


@pytest.fixture
def workspace(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        bootstrap = client.get('/api/bootstrap').json()
        client.headers['x-csrf-token'] = bootstrap['csrf']
        store = app.state.store
        owner = store.session(client.cookies.get('api_test_session'))[0]['id']
        token = client.post('/api/mcp/redeem', json={'code': client.post('/api/mcp/pair').json()['code']}).json()['token']
        project = store.create_project(owner, '合成阻塞记录', 'ui-test.md', '# 合成记录')
        pid = project['id']
        store.update_project(owner, pid, {'test_kind': 'ui', 'ui_target_url': 'https://demo.example.test/account'})
        def call(action, **arguments):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token},
                json={'action': action, 'arguments': {'project_id': pid, **arguments}})
        yield client, store, owner, pid, call


def tool(scope='browser-instance-a', **updates):
    return dependency(**{'kind': 'tool', 'key': 'cdp-down', 'title': 'CDP 初始化失败', 'scope': scope, 'role': '', 'tenant': '', **updates})


def test_tool_network_scopes_are_explicit_and_distinct():
    values = ui_dependencies.normalize([tool(), tool('browser-instance-b'), tool(kind='network')], case('A'), 'https://demo.test')
    assert len(values) == 3
    assert {v['scope'] for v in values} == {'browser-instance-a', 'browser-instance-b'}
    with pytest.raises(ValueError, match='scope'):
        ui_dependencies.normalize([tool('')], case('A'), 'https://demo.test')


def test_recovery_preserves_history_other_blockers_and_executed_facts(workspace):
    _, store, owner, pid, call = workspace
    saved = call('ui_cases', cases=[case('A', [tool(), dependency()]), case('B', [tool()]),
        case('PARTIAL', [tool()], status='partial', actual='已观察一部分事实'),
        case('LEGACY', [], status='blocked', actual='原无结构化工具故障')]).json()
    assert 'dependency_groups' in saved, saved
    gids = {g['kind']: g['id'] for g in saved['dependency_groups']}
    for gid in gids.values():
        saved = check(call, saved, gid).json()
    summary = saved['blocking_summary']
    assert summary['reason_count'] == 2
    assert summary['affected_case_count'] == 3
    assert summary['unstructured_blocked_case_count'] == 1
    previous = ui_records.load(store, owner, pid, saved['execution_id'])
    saved = check(call, saved, gids['tool'], 'ready').json()
    record = ui_records.load(store, owner, pid, saved['execution_id'])
    by_id = {c['case_id']: c for c in record['cases']}
    assert by_id['A']['status'] == 'not_run' and not by_id['A'].get('blocked_by')
    assert by_id['B']['status'] == 'not_run'
    assert by_id['PARTIAL']['actual'] == '已观察一部分事实' and by_id['PARTIAL']['status'] == 'partial'
    assert by_id['LEGACY']['actual'] == '原无结构化工具故障'
    assert record['cases'] == previous['cases']
    assert record.get('case_history', {}) == previous.get('case_history', {})
    assert record['dependency_check_history'][:-1] == previous['dependency_check_history']
    assert previous['dependency_checks'][gids['tool']]['status'] == 'blocked'
    assert record['dependency_checks'][gids['account']]['status'] == 'blocked'


def test_explicit_split_keeps_original_and_excludes_activity_and_report(workspace):
    client, store, owner, pid, call = workspace
    saved = call('ui_cases', cases=[case('OLD', [], status='blocked', actual='未执行的聚合'), case('A', []), case('B', [])]).json()
    saved = call('ui_cases', execution_id=saved['execution_id'], revision=saved['revision'],
                 cases=[{'case_id': 'OLD', 'superseded_by': ['A', 'B']}]).json()
    assert saved['total'] == 2
    record = ui_records.load(store, owner, pid, saved['execution_id'])
    assert len(record['cases']) == 3 and record['cases'][0]['superseded_by'] == ['A', 'B']
    assert record['case_history']
    assert saved['execution_plan']['waiting_case_ids'] == []
    assert saved['execution_plan']['execution_summary']['designed_cases'] == 2
    read = call('ui_read', limit=1).json()
    assert read['total'] == 2 and read['next_offset'] == 1 and read['cases'][0]['case_id'] == 'A'
    assert read['superseded_cases'][0]['case_id'] == 'OLD'
    parsed = ui_records.as_results(record)
    assert parsed['counts']['total'] == 2 and [c['case_id'] for c in parsed['cases']] == ['A', 'B']
    assert parsed['superseded_cases'][0]['actual'] == '未执行的聚合'
    assert store.get_project(owner, pid)['ui_progress_record']['counts'] == {'not_run': 2}


@pytest.mark.parametrize('status', ['passed', 'failed', 'partial'])
def test_split_never_hides_executed_result_or_history(workspace, status):
    _, store, owner, pid, call = workspace
    saved = call('ui_cases', cases=[case('OLD', [], status=status, actual='已执行事实'), case('A', [])]).json()
    response = call('ui_cases', execution_id=saved['execution_id'], revision=saved['revision'],
                    cases=[{'case_id': 'OLD', 'status': 'not_run', 'actual': '', 'superseded_by': ['A']}])
    assert response.status_code == 400
    record = ui_records.load(store, owner, pid, saved['execution_id'])
    assert record['cases'][0]['status'] == status


@pytest.mark.parametrize('replacements', [['MISSING'], ['OLD'], ['A', 'A']])
def test_split_requires_valid_distinct_replacement_ids(workspace, replacements):
    _, _, _, _, call = workspace
    saved = call('ui_cases', cases=[case('OLD', []), case('A', [])]).json()
    response = call('ui_cases', execution_id=saved['execution_id'], revision=saved['revision'],
                    cases=[{'case_id': 'OLD', 'superseded_by': replacements}])
    assert response.status_code == 400


def test_replacement_chains_coverage_and_readback_preserve_all_facts():
    from api_test_tool.ui_case_results import validate_supersession, active_coverage_refs
    from api_test_tool.native_lifecycle import native_save_readback
    old = case('OLD', [], superseded_by=['A'])
    intermediate = case('A', [], superseded_by=['B'])
    final = case('B', [])
    record = {'id': 'execution', 'revision': 2, 'cases': [final], 'superseded_cases': [old, intermediate],
              'coverage': [{'coverage_id': 'area', 'case_ids': ['OLD']}]}
    full = {**record, 'cases': [old, intermediate, final]}
    validate_supersession({}, full['cases'])
    assert active_coverage_refs(full) == {'B'}
    with pytest.raises(ValueError, match='循环'):
        validate_supersession({}, [old, {**intermediate, 'superseded_by': ['OLD']}, final])
    receipt = {'binding': {'execution_id': 'execution'}, 'revision_before': 1,
               'payload': {'cases': [{'case_id': 'OLD', 'superseded_by': ['A']}]}}
    confirmed = native_save_readback(receipt, record)
    assert {c['case_id'] for c in confirmed['saved_cases']} == {'OLD', 'A', 'B'}
    assert confirmed['execution_plan']['execution_summary']['status_counts'] == {'not_run': 1}


def test_checkpoint_plan_omits_explicit_aggregate_and_keeps_raw_record():
    from api_test_tool import test_checkpoints
    old = case('OLD', [], superseded_by=['A'], checkpoints=[{
        'id': 'point', 'title': '聚合观察', 'kind': 'browser', 'status': 'not_run', 'dependencies': []}])
    record = {'cases': [old, case('A', [])]}
    assert test_checkpoints.plan(record)['runnable_checkpoints'] == []
    assert record['cases'][0]['checkpoints'][0]['status'] == 'not_run'


def test_history_cannot_be_hidden_after_intervening_not_run():
    from api_test_tool.ui_case_results import validate_supersession
    previous = {'cases': [case('OLD', [])], 'case_history': {'1': {'cases': [case('OLD', [], status='failed')]}}}
    with pytest.raises(ValueError, match='历史'):
        validate_supersession(previous, [case('OLD', [], superseded_by=['A']), case('A', [])])


def test_checkpoint_recovery_keeps_before_image(workspace):
    _, store, owner, pid, call = workspace
    point = {'id': 'p', 'title': '页面观察', 'expected': '可见', 'kind': 'browser'}
    saved = call('ui_cases', cases=[case('A', [tool()], checkpoints=[point])]).json()
    gid = saved['dependency_groups'][0]['id']
    saved = check(call, saved, gid).json()
    previous = ui_records.load(store, owner, pid, saved['execution_id'])
    saved = check(call, saved, gid, 'ready').json()
    record = ui_records.load(store, owner, pid, saved['execution_id'])
    assert record['cases'][0]['status'] == 'not_run'
    old_point = record['case_history'][str(previous['revision'])]['cases'][0]['checkpoints'][0]
    assert old_point['status'] == 'not_run'
    assert old_point['gaps'][0]['status'] == 'blocked'


def test_unrelated_save_does_not_erase_original_split_or_block_history(workspace):
    _, store, owner, pid, call = workspace
    saved = call('ui_cases', cases=[case('OLD', []), case('A', []), case('B', [])]).json()
    saved = call('ui_cases', execution_id=saved['execution_id'], revision=saved['revision'],
                 cases=[{'case_id': 'OLD', 'superseded_by': ['A', 'B']}]).json()
    saved = call('ui_cases', execution_id=saved['execution_id'], revision=saved['revision'],
                 cases=[{'case_id': 'OLD', 'scenario': '原聚合说明修订'}]).json()
    assert saved['total'] == 2
    saved = call('ui_cases', execution_id=saved['execution_id'], revision=saved['revision'],
                 cases=[{'case_id': 'OLD', 'superseded_by': []}]).json()
    assert saved['total'] == 3
    record = ui_records.load(store, owner, pid, saved['execution_id'])
    assert record['cases'][0]['status'] == 'not_run'
    assert any(c.get('superseded_by') == ['A', 'B'] for entry in record['case_history'].values() for c in entry['cases'])


def test_report_views_share_active_counts_and_keep_split_source(workspace):
    from api_test_tool import ui_total_reports, ui_round_report, ui_closeout
    _, store, owner, pid, call = workspace
    saved = call('ui_cases', cases=[case('OLD', [], status='blocked', actual='原工具故障'), case('A', []), case('B', [])]).json()
    # A frozen earlier stage must not restore the original aggregate in totals.
    first = call('ui_publish', execution_id=saved['execution_id'], title='拆分前', summary='合成').json()['report']
    first_record = store._read(store.project_dir(owner, pid) / 'analyses' / first['id'] / 'report.json')
    first_record['id'] = 'synthetic-earlier-stage'
    earlier_path = store.project_dir(owner, pid) / 'analyses' / first_record['id'] / 'report.json'
    earlier_path.parent.mkdir(parents=True)
    first_record['created_at'] = '2000-01-01T00:00:00+00:00'
    store._write(earlier_path, first_record)
    saved = call('ui_cases', execution_id=saved['execution_id'], revision=saved['revision'],
                 cases=[{'case_id': 'OLD', 'superseded_by': ['A', 'B']}]).json()
    record = ui_records.load(store, owner, pid, saved['execution_id'])
    assert '本轮共 2 条' in ui_closeout.summary(record)
    total = ui_total_reports.build(store, owner, store.get_project(owner, pid))
    assert total['imported_results']['counts']['total'] == 2
    assert total['imported_results']['superseded_cases'][0]['case_id'] == 'OLD'
    assert '原工具故障' in ui_records.superseded_html(total)
    project = store.get_project(owner, pid)
    total = ui_round_report.build(store, owner, {**project, 'execution_round': {'id': 'synthetic-round'}})
    assert total['imported_results']['counts']['total'] == 2
    assert total['ui_snapshot']['cases'][-1]['case_id'] == 'OLD'
    assert total['imported_results']['blocking_summary']['unstructured_blocked_case_count'] == 0


def test_blocker_summaries_deduplicate_same_record_and_keep_distinct_scopes():
    from api_test_tool.ui_dependencies import merge_blocking_summaries
    dep = ui_dependencies.normalize([tool()], case('A'), 'https://demo.test')[0]
    record = {'id': 'round-a', 'cases': [case('A', [dep]), case('B', [dep])],
              'dependency_checks': {dep['id']: {'status': 'blocked'}}}
    other = {**record, 'id': 'round-b', 'cases': [case('C', [dep])]}
    result = merge_blocking_summaries([('project', record), ('project', record), ('project', other)])
    assert result == {'reason_count': 2, 'affected_case_count': 3, 'unstructured_blocked_case_count': 0}


@pytest.mark.parametrize('scenario,reverse,total,passed,failed,not_run,complete,ratio', [
    ('split', False, 2, 2, 0, 0, 2, 1),
    ('split', True, 2, 2, 0, 0, 2, 1),
    ('newer_failure', False, 3, 2, 1, 0, 3, 1),
    ('newer_failure', True, 3, 2, 1, 0, 3, 1),
    ('undated', False, 3, 3, 0, 0, 3, 1),
    ('undated', True, 3, 2, 0, 1, 2, 2 / 3),
])
def test_managed_report_selects_latest_case_before_split_filter(
        monkeypatch, scenario, reverse, total, passed, failed, not_run, complete, ratio):
    from types import SimpleNamespace
    from api_test_tool import ui_round_report
    from api_test_tool.managed_service import ManagedService
    from api_test_tool.ui_case_results import annotate

    parent = case('A', [], updated_at='2026-10-25T01:00:00+00:00')
    child = case('A', [], updated_at='2026-10-25T02:00:00+00:00', superseded_by=['B', 'C'])
    if scenario == 'newer_failure':
        parent.update(status='failed', actual='较新的真实失败', updated_at='2026-10-25T03:00:00+00:00')
    elif scenario == 'undated':
        parent.pop('updated_at')
        child = case('A', [], status='passed', actual='后续真实通过')
    modules = []
    for node_id, cases in [('parent', [parent]), ('child', [child, case('B', [], status='passed'), case('C', [], status='passed')])]:
        history = {'1': {'cases': [case('A', [], actual='原始设计事实')]}}
        record = {'cases': cases, 'case_history': history}
        record['cases'] = [annotate(c, record) for c in cases]
        modules.append({'node_id': node_id, 'parent_id': '' if node_id == 'parent' else 'parent',
                        'record': record, 'case_history': deepcopy(history), 'fact_only': node_id == 'parent'})
    if reverse:
        modules.reverse()
    original = deepcopy(modules)
    snapshot = {'tasks': [{'id': 'synthetic-task'}], 'notices': []}
    service = SimpleNamespace(store=None, controller=SimpleNamespace(snapshot=lambda *args, **kwargs: snapshot))
    # Record loading is outside this unit; the production aggregation and views run unchanged.
    monkeypatch.setattr(ui_round_report, 'task_records', lambda *args: modules)

    result = ManagedService.report(service, 'synthetic-owner', 'synthetic-task')

    assert result['total'] == total
    assert {status: result['counts'][status] for status in ('passed', 'failed', 'not_run')} == {
        'passed': passed, 'failed': failed, 'not_run': not_run}
    assert result['coverage_complete'] == complete
    assert result['coverage_ratio'] == ratio
    assert result['complete_pass_ratio'] == passed / total
    assert modules == original
    for view, source in zip(result['modules'], original):
        assert view['case_history'] == source['case_history']
        assert view['record']['case_history'] == source['record']['case_history']
        assert view['record']['cases'] + view['record']['superseded_cases'] == (
            source['record']['cases'] if source['node_id'] == 'parent' or scenario == 'undated'
            else source['record']['cases'][1:] + source['record']['cases'][:1])


def checkpoint(pid, status='not_run', **updates):
    return {'id': pid, 'title': pid, 'kind': 'browser', 'status': status, 'expected': '可见',
            'actual': '', 'verification_mode': 'design', 'dependencies': [], **updates}


def test_unrelated_dependency_checks_preserve_legacy_checkpoint_blocker():
    point = checkpoint('legacy', 'blocked', actual='原工具故障尚未复核')
    legacy = case('LEGACY', [], status='blocked', actual='原故障事实',
                  not_run_reason='原工具不可用', conclusion='原待核对结论', checkpoints=[point])
    dep = ui_dependencies.normalize([tool()], case('A'), 'https://demo.test')[0]
    record = {'cases': [legacy, case('A', [dep])], 'dependency_checks': {dep['id']: {'status': 'ready'}}}
    ui_dependencies.apply_checks(record)
    assert point['status'] == 'blocked'
    assert legacy['status'] == 'blocked' and legacy['actual'] == '原故障事实'
    assert legacy['not_run_reason'] == '原工具不可用' and legacy['conclusion'] == '原待核对结论'
    plan = ui_dependencies.plan(record)
    assert not any(p['case_id'] == 'LEGACY' for p in plan['runnable_checkpoints'])
    assert plan['blocking_summary']['unstructured_blocked_case_count'] == 1


def test_checkpoint_blocking_summary_uses_only_remaining_point_dependencies():
    dep = ui_dependencies.normalize([tool()], case('A'), 'https://demo.test')[0]
    completed = checkpoint('done', 'passed', actual='已通过', verification_mode='real', dependencies=[dep])
    remaining = checkpoint('remaining')
    c = case('A', [], status='partial', actual='局部观察', checkpoints=[completed, remaining])
    record = {'cases': [c], 'dependency_checks': {dep['id']: {'status': 'blocked', 'observed': '已完成之后断开'}}}
    assert ui_dependencies.blocking_summary(record)['reason_count'] == 0
    assert ui_dependencies.blocking_summary(record)['affected_case_count'] == 0
    assert ui_dependencies.plan(record)['runnable_checkpoints'][0]['checkpoint_id'] == 'remaining'
    c['dependencies'] = [dep]
    assert ui_dependencies.blocking_summary(record)['affected_case_count'] == 1


def test_checkpoint_dependency_diagnostics_survive_save_and_readback_without_changing_status(workspace):
    from api_test_tool.native_lifecycle import native_save_readback
    _, store, owner, pid, call = workspace
    saved = call('ui_cases', cases=[case('A', [tool()], checkpoints=[checkpoint('p')])]).json()
    gid = saved['dependency_groups'][0]['id']
    saved = check(call, saved, gid).json()
    before = ui_records.load(store, owner, pid, saved['execution_id'])
    assert before['cases'][0]['checkpoints'][0]['status'] == 'not_run'
    assert before['cases'][0]['checkpoints'][0]['gaps'][0]['status'] == 'blocked'
    assert 'status_source' not in before['cases'][0]['checkpoints'][0]
    submitted = {'case_id': 'A', 'checkpoints': deepcopy(before['cases'][0]['checkpoints'])}
    saved = call('ui_cases', execution_id=saved['execution_id'], revision=saved['revision'], cases=[submitted]).json()
    record = ui_records.load(store, owner, pid, saved['execution_id'])
    assert record['cases'][0]['checkpoints'][0]['status'] == 'not_run'
    assert record['cases'][0]['checkpoints'][0]['gaps'][0]['status'] == 'blocked'
    receipt = {'binding': {'execution_id': saved['execution_id']}, 'revision_before': before['revision'],
               'payload': {'cases': [submitted]}, 'case_baselines': {'A': before['cases'][0]}}
    assert native_save_readback(receipt, record)['revision'] == record['revision']
    saved = check(call, saved, gid, 'ready').json()
    record = ui_records.load(store, owner, pid, saved['execution_id'])
    assert record['cases'][0]['checkpoints'][0]['status'] == 'not_run'
    assert 'status_source' not in record['cases'][0]['checkpoints'][0]


def test_ready_dependency_does_not_override_legacy_checkpoint_verdict():
    dep = ui_dependencies.normalize([tool()], case('A'), 'https://demo.test')[0]
    point = checkpoint('p', 'blocked', dependencies=[dep], gaps=[{
        'kind': 'dependency', 'id': dep['id'], 'status': 'blocked', 'reason': '原已核实共同条件'}])
    record = {'cases': [case('A', [], status='blocked', checkpoints=[point])],
              'dependency_checks': {dep['id']: {'status': 'ready'}}}
    ui_dependencies.apply_checks(record)
    assert point['status'] == 'blocked' and point['gaps'] == []
    assert record['cases'][0]['status'] == 'blocked'


def test_legacy_checkpoint_prose_and_new_sibling_observation_are_both_visible():
    legacy = checkpoint('legacy', 'blocked', actual='原工具故障')
    other = checkpoint('other')
    c = case('A', [], status='blocked', actual='原现场观察', conclusion='原结论',
             not_run_reason='原未执行原因', checkpoints=[legacy, other])
    record = {'cases': [c]}
    ui_dependencies.apply_checks(record)
    other.update(status='failed', actual='新检查点实际失败', verification_mode='real')
    ui_dependencies.apply_checks(record)
    assert c['status'] == 'blocked'
    assert c['actual'] == '原现场观察'
    assert c['conclusion'] == '原结论'
    assert c['not_run_reason'] == '原未执行原因'
    assert c['checkpoints'][1]['actual'] == '新检查点实际失败'
    assert c['checkpoints'][1]['status'] == 'failed'
    before = deepcopy(c)
    ui_dependencies.apply_checks(record)
    assert c == before


def test_unstructured_checkpoint_cannot_be_adopted_by_later_structured_failure():
    dep = ui_dependencies.normalize([tool()], case('A'), 'https://demo.test')[0]
    point = checkpoint('p', 'blocked', actual='独立的原未知阻塞', dependencies=[dep])
    record = {'cases': [case('A', [], status='blocked', actual='原观察', checkpoints=[point])],
              'dependency_checks': {dep['id']: {'status': 'blocked', 'observed': '后来的网络故障'}}}
    ui_dependencies.apply_checks(record)
    record['dependency_checks'][dep['id']]['status'] = 'ready'
    ui_dependencies.apply_checks(record)
    assert point['status'] == 'blocked' and record['cases'][0]['actual'] == '原观察'
