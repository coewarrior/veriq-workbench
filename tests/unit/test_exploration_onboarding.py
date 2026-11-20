"""Current project login behavior wins over historical origin adapters."""
import copy
import pytest
from api_test_tool.exploration_learning import PROFILE
from api_test_tool.exploration_profiles import provision


def account(target):
    return dict(id='account', owner='owner', projects=['project'], target=target,
                identity='fixture-user', auth_generation='generation')


@pytest.mark.parametrize('target', ['https://aihire.succaiss.com', 'https://different.example'])
def test_every_project_requires_live_session_evidence(target):
    state = dict(policies={}, leases={})
    current = account(target)
    policy = provision(state, current)
    assert policy['automatic_profile'] == PROFILE
    assert policy['preparation'] == 'pending'
    assert policy['session_strategy'] == 'verified_storage_copy'
    assert not policy['session_compatible'] and policy['rules'] == []
    assert provision(state, current) is policy


def test_legacy_adapter_migrates_only_after_its_last_lease_exits():
    current = account('https://aihire.succaiss.com')
    current['policy_id'] = 'legacy'
    legacy = dict(id='legacy', automatic_profile='aihire-b-20261018-v1', enabled=True)
    state = dict(policies={'legacy': legacy}, leases={'running': {'policy_id': 'legacy'}})
    assert provision(state, current) is legacy
    assert current['policy_id'] == 'legacy'
    state['leases'].clear()
    migrated = provision(state, current)
    assert migrated['automatic_profile'] == PROFILE
    assert current['policy_id'] == migrated['id'] != 'legacy'
    assert state['policies']['legacy'] == legacy


@pytest.mark.parametrize('policy', [
    dict(id='explicit', enabled=True),
    dict(id='revoked', enabled=False, automatic_profile='aihire-b-20261018-v1'),
])
def test_onboarding_keeps_explicit_configuration_and_revocation(policy):
    current = account('https://aihire.succaiss.com'); current['policy_id'] = policy['id']
    state = dict(policies={policy['id']: copy.deepcopy(policy)}, leases={})
    assert provision(state, current) == policy
    assert current['policy_id'] == policy['id']
