"""Explicit project-scoped single-account stages must not wait for a preference."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from api_test_tool.execution_work_plan import normalize_work_plan, project_work_candidates
from api_test_tool.resource_scheduler import ResourceScheduler


def setup_stage():
    record = {'id': 'run', 'project_id': 'project', 'revision': 1,
              'cases': [{'case_id': 'A', 'scenario': '独立单账号场景', 'account_scope': 'single_account', 'status': 'not_run'}]}
    plan = {'schema_version': 1, 'project_id': 'project', 'execution_id': 'run', 'units': [{
        'id': 'independent', 'case_ids': ['A'], 'requires': {'phase': 'execution',
        'account_scope': 'single_account', 'account_selection': 'preferred', 'account_ids': ['busy'],
        'requirements': []}}]}
    return record, plan


def test_declared_single_account_preference_can_select_free_same_project_account():
    record, plan = setup_stage()
    normalized = normalize_work_plan(plan, record)
    node = {'id': 'node', 'owner': 'owner', 'project_id': 'project', 'account_project_id': 'pool',
            'requires_account': True, 'checkpoint': {'work_plan': normalized}}
    projected = project_work_candidates(node, record)[0]['projected_node']
    assert projected['requested_account_ids'] == []
    accounts = {key: {'id': key, 'owner': 'owner', 'projects': [pool], 'target': target,
        'environment': target, 'identity': key, 'state': 'needs_login'}
        for key, pool, target in [('busy', 'pool', 'https://example.test'), ('free', 'pool', 'https://example.test'),
                                   ('foreign', 'other', 'https://example.test'), ('wrong-target', 'pool', 'https://other.test')]}
    state = {'accounts': accounts, 'nodes': {'node': projected}, 'leases': {
        'held': {'id': 'held', 'account_ids': ['busy']}}, 'policies': {}}
    controller = SimpleNamespace(store=SimpleNamespace(get_project=lambda *_: {'ui_target_url': 'https://example.test'}))
    assert ResourceScheduler(controller, state, 0).candidate_sets(projected) == [['free']]
    # A real object-dependent hard binding retains its original wait.
    hard = deepcopy(plan)
    hard['units'][0]['requires']['account_selection'] = 'required'
    node['checkpoint']['work_plan'] = normalize_work_plan(hard, record)
    bound = project_work_candidates(node, record)[0]['projected_node']
    assert ResourceScheduler(controller, state, 0).candidate_sets(bound) == [[]]


@pytest.mark.parametrize('change', ['unknown', 'multiple', 'case_scope', 'resume'])
def test_single_account_scope_does_not_infer_unknown_or_drop_original_scene_binding(change):
    record, plan = setup_stage()
    req = plan['units'][0]['requires']
    if change == 'unknown': req.pop('account_scope')
    if change == 'multiple': req['account_ids'].append('second')
    if change == 'case_scope': record['cases'][0].pop('account_scope')
    if change == 'resume': plan['units'][0]['resume_ref'] = 'original-object-scene'
    with pytest.raises(ValueError):
        normalize_work_plan(plan, record)


def test_case_scope_correction_to_excluded_does_not_break_existing_plan():
    record, plan = setup_stage()
    saved = normalize_work_plan(plan, record)
    record['cases'][0]['account_scope'] = 'cross_account'
    candidate = project_work_candidates({'checkpoint': {'work_plan': saved}}, record)[0]
    assert candidate['eligibility'] == 'excluded'
    assert candidate['case_ids'] == []
