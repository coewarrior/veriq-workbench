"""Offline work selection: independent case identities and actual result facts."""
import copy
import importlib
import pytest

from api_test_tool import ui_dependencies


def helpers():
    try:
        return importlib.import_module('api_test_tool.execution_work_plan')
    except ModuleNotFoundError:
        pytest.fail('work-stage selection is not implemented')


def record():
    return {'id': 'run', 'project_id': 'project', 'revision': 1, 'cases': [
        {'case_id': cid, 'status': 'not_run', 'scenario': cid} for cid in ('A1', 'A2', 'AB')]}


def unit(uid, ids, accounts, **updates):
    return {'id': uid, 'case_ids': ids, 'requires': {'phase': 'execution',
        'account_ids': accounts, 'account_selection': 'required', 'requirements': [], 'locks': []}, **updates}


def plan():
    return {'schema_version': 1, 'project_id': 'project', 'execution_id': 'run', 'units': [
        unit('a', ['A1', 'A2'], ['A']), unit('ab', ['AB'], ['B'])]}


def test_result_revision_does_not_invalidate_plan():
    h = helpers()
    r = record()
    saved = h.normalize_work_plan(plan(), r)
    r['revision'] = 3
    r['cases'][0]['status'] = 'passed'
    latest = h.normalize_work_plan(saved, r, saved)
    assert latest['plan_revision'] == saved['plan_revision'] == 1
    assert latest['validated_record_revision'] == 3
    picked = h.select_next_work(r, latest, {'account_ids': ['A'], 'mode': 'exclusive', 'locks': []})
    assert picked['runnable_case_ids'] == ['A2']
    assert picked['waiting_resource_unit_ids'] == ['ab']
    assert r['cases'][0]['status'] == 'passed'


def test_dependency_scope_and_discovery():
    h = helpers()
    r = record()
    dep = ui_dependencies.normalize([{'key': 'samples', 'kind': 'data', 'title': '样本',
        'environment': 'test', 'account_id': 'A', 'state_ref': 'empty-v1'}], {}, 'https://fixture.test')[0]
    r['cases'][0]['dependencies'] = [dep]
    r['dependency_checks'] = {dep['id']: {'status': 'blocked', 'observed': 'A无样本'}}
    p = h.normalize_work_plan(plan(), r)
    r['cases'].append({'case_id': 'new', 'status': 'not_run', 'scenario': 'new'})
    expanded = copy.deepcopy(p)
    expanded['units'].insert(0, unit('new-stage', ['new'], ['A']))
    latest = h.normalize_work_plan(expanded, r, p)
    assert [u['id'] for u in latest['units']] == ['a', 'ab', 'new-stage']
    picked = h.select_next_work(r, latest, {'account_ids': ['A'], 'mode': 'exclusive', 'locks': []})
    assert picked['runnable_case_ids'] == ['A1', 'A2', 'new']
    assert latest['plan_revision'] == 2
    assert p['units'][0]['case_ids'] == ['A1', 'A2']


@pytest.mark.parametrize('mutation', ['foreign', 'cycle', 'duplicate', 'unknown_resources'])
def test_bad_work_references_are_rejected(mutation):
    h = helpers()
    p = plan()
    if mutation == 'foreign': p['units'][0]['case_ids'] = ['outside']
    if mutation == 'cycle':
        p['units'][0]['depends_on'] = ['ab']
        p['units'][1]['depends_on'] = ['a']
    if mutation == 'duplicate': p['units'][1]['case_ids'] = ['A1']
    if mutation == 'unknown_resources': p['units'][0]['requires'] = {}
    with pytest.raises(ValueError): h.normalize_work_plan(p, record())


def test_phase_dependency_orders_completed_work_without_judging_business_success():
    h = helpers()
    r = record()
    p = plan()
    p['units'][1]['depends_on'] = ['a']
    r['cases'][0]['status'] = r['cases'][1]['status'] = 'failed'
    p = h.normalize_work_plan(p, r)
    picked = h.select_next_work(r, p, {'account_ids': ['A', 'B'], 'mode': 'exclusive', 'locks': []})
    assert picked['runnable_case_ids'] == ['AB']
    assert picked['waiting_prerequisite_unit_ids'] == []


def test_shared_lease_cannot_execute_exclusive_branch():
    h = helpers()
    p = plan()
    p['units'][0]['requires']['phase'] = 'exploration'
    p = h.normalize_work_plan(p, record())
    before = copy.deepcopy(p)
    selected = h.select_next_work(record(), p, {'account_ids': ['A', 'B'], 'mode': 'shared', 'locks': []})
    assert selected['runnable_case_ids'] == ['A1', 'A2']
    assert selected['waiting_resource_unit_ids'] == ['ab']
    assert p == before


def test_dependency_identity_is_account_and_state_scoped():
    base = {'key': 'samples', 'kind': 'data', 'title': '样本', 'environment': 'test'}
    values = [ui_dependencies.normalize([{**base, 'account_id': a, 'state_ref': s}], {}, 'https://fixture.test')[0]
              for a, s in [('A', 'v1'), ('B', 'v1'), ('A', 'v2')]]
    assert len({v['id'] for v in values}) == 3


def test_readback_keeps_server_eligibility_plan():
    from api_test_tool.native_lifecycle import native_save_readback
    r = {**record(), 'revision': 2, 'execution_plan': {'runnable_case_ids': ['A1', 'A2', 'AB'],
        'runnable_checkpoints': [], 'dependencies_to_check': [], 'execution_summary': {'status_counts': {'not_run': 3}}}}
    receipt = {'binding': {'execution_id': 'run'}, 'revision_before': 1, 'payload': {'cases': []}}
    result = native_save_readback(receipt, r)
    assert result['execution_plan']['runnable_case_ids'] == ['A1', 'A2', 'AB']
    assert result['execution_plan']['source_revision'] == 2
