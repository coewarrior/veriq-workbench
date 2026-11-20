"""The platform stores model verdicts; descriptions are not execution gates."""
import base64
import pytest

from api_test_tool import ui_records, ui_uploads
from test_native_finalization import prepare


@pytest.mark.parametrize('fields', [
    {'scenario': '损坏 PDF 与上传解析错误区分', 'expected': '明确格式/读取失败',
     'status': 'passed', 'actual': '解析失败', 'conclusion': '预期拒绝，验证通过'},
    {'status': 'passed', 'actual': ''},
    {'status': 'passed', 'actual': '并已先截图。截图已关联。缺陷标题：保留原文'},
    {'status': 'pending_action', 'action_type': 'authorization', 'actual': '模型需要确认'},
    {'status': 'blocked', 'actual': 'Chrome 扩展不能读取本地文件'},
    {'status': 'failed', 'actual': '模型结论', 'checkpoints': [
        {'id': 'point', 'title': '独立检查', 'expected': '由模型判断', 'status': 'passed',
         'verification_mode': 'design', 'actual': '', 'assertions': [
             {'kind': 'http_status', 'expected': 400, 'source_quote': '不要求字面匹配资料'}]}]},
])
def test_model_verdict_and_text_survive_save_and_publish(tmp_path, fields):
    c, _, owner, project, _, saved = prepare(tmp_path)
    case = {'case_id': 'A', 'scenario': '模型独立判定', **fields}
    result = ui_records.save_cases(c.store, owner, project['id'], [case],
        execution_id=saved['execution_id'], revision=saved['revision'])
    record = ui_records.load(c.store, owner, project['id'], result['execution_id'])
    actual = next(item for item in record['cases'] if item['case_id'] == 'A')
    assert actual['status'] == case['status']
    assert actual['actual'] == case['actual']
    published = ui_records.publish(c.store, owner, project, result['execution_id'], 'Model report', 'Original verdict')
    assert published['report']['id']
    assert ui_records.load(c.store, owner, project['id'], result['execution_id'])['cases'] == record['cases']


def test_fixture_uses_explicit_case_link_not_filename_in_prose(tmp_path):
    c, _, owner, project, _, saved = prepare(tmp_path)
    result = ui_records.add_assets(c.store, owner, project['id'], saved['execution_id'], [{
        'case_id': 'A', 'filename': 'arbitrary-sample.txt', 'kind': 'fixture',
        'content_type': 'text/plain', 'data_base64': base64.b64encode(b'synthetic').decode()}])
    record = ui_records.load(c.store, owner, project['id'], saved['execution_id'])
    assert record['assets'][0]['case_id'] == 'A'
    assert ui_records.publish(c.store, owner, project, saved['execution_id'], 'Fixture', 'Explicit link')['report']['id']


def test_upload_channels_and_scene_conclusion_are_executor_observations():
    attempts = [{'channel': 'native_cua', 'outcome': 'unsupported_here', 'detail': 'Original observation'}] * 4
    assert ui_uploads.normalize(attempts) == attempts
    result = {'status': 'cleaned', 'items': [{'name': 'draft', 'state': 'unverified'}], 'note': 'Model conclusion'}
    assert ui_records.scene_outcome(result)['status'] == 'cleaned'


def test_explicit_work_stage_is_not_vetoed_by_business_prerequisite_diagnostics():
    from api_test_tool import execution_work_plan as work, ui_dependencies
    dep = ui_dependencies.normalize([{'key': 'sample', 'kind': 'data', 'title': 'sample',
        'environment': 'test', 'account_id': 'account'}], {}, 'https://fixture.test')[0]
    record = {'id': 'run', 'revision': 1, 'cases': [
        {'case_id': 'before', 'scenario': 'before', 'status': 'failed'},
        {'case_id': 'next', 'scenario': 'next', 'status': 'not_run', 'dependencies': [dep]}],
        'dependency_checks': {dep['id']: {'status': 'blocked', 'observed': 'original diagnostic'}}}
    units = [{'id': cid, 'case_ids': [cid], 'depends_on': ['before'] if cid == 'next' else [],
        'requires': {'phase': 'execution', 'account_ids': ['account'], 'account_selection': 'required'}}
        for cid in ('before', 'next')]
    plan = work.normalize_work_plan({'schema_version': 1, 'project_id': 'project', 'execution_id': 'run', 'units': units}, record)
    selected = work.select_next_work(record, plan, {'account_ids': ['account'], 'mode': 'exclusive', 'locks': []})
    assert selected['runnable_case_ids'] == ['next']


def test_claimed_business_success_cannot_hide_an_explicitly_pending_operation(tmp_path):
    from test_cleanup_event_contract import fixture, capability, register, scope
    c, service, owner, project, claim, aid, send = fixture(tmp_path)
    c.store.update_project(owner, project['id'], {'ui_execution_permission': {'key': 'full'}})
    send([capability(aid), register(aid)])
    obj = send([{'command': 'prepare_cleanup', 'responsibility_id': 'object-a'}])['results'][0]['responsibility']
    observation = {'evidence_ref': 'asset:operation-still-running', 'object_scope': scope(aid),
        'business_completed': True, 'original_operation_resolved': False,
        'effect_state': 'unknown', 'object_state': 'absent',
        'object_identity_verified': True, 'principal_verified': True}
    result = send([{'command': 'complete_cleanup', 'responsibility_id': 'object-a',
        'cleanup_attempt_id': obj['cleanup_attempt_id'], 'observation': observation}])
    assert result['results'][0]['responsibility']['state'] == 'unknown'
    assert result['results'][0]['responsibility']['last_observation'] == observation
    ended = service.direct.call(owner, {'action': 'finish', 'holder_id': 'original-holder',
        'lease_id': claim['lease_id'], 'arguments': {'browser_stopped': True, 'reason': 'Synthetic pages exited'}})
    assert not ended['released'] and len(c.snapshot(owner)['leases']) == 1
