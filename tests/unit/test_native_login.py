"""Real-context evidence and public allocation, without business/model calls."""
import pytest

from api_test_tool.managed_service import ManagedService
from api_test_tool.orchestration import Conflict
from test_native_execution import STATIC, ready
from test_native_scheduler import setup


def test_public_claim_without_environment_waits_without_allocating(tmp_path):
    c, owner, _, _, tid = setup(tmp_path)
    s = ManagedService(c, STATIC)
    result = s.direct.call(owner, {'action': 'claim', 'holder_id': 'worker',
        'executor_ref': 'thread:worker', 'task_id': tid})
    assert result['state'] == 'queued' and not result['lease_id']
    assert not c.snapshot(owner)['leases']
    assert '环境' in result['reason'] and result['login_state'] == 'unverified'


def login_fixture(tmp_path):
    c, s, owner, _, _, args = ready(tmp_path)
    current = s.direct.call(owner, {**args, 'action': 'context'})
    context = current['native_context_binding']['contexts'][0]
    with c.transaction() as (_, state):
        state['accounts'][context['account_id']]['identity'] = 'allocated@example.com'
    evidence = {key: context[key] for key in ('environment_key', 'account_id')}
    evidence.update(state='verified', method='visible_identity', evidence='个人资料可见身份')
    return c, s, owner, args, evidence


@pytest.mark.parametrize('observed,claimed,expected', [
    ('a***d@example.com', 'mismatch', 'unverified'),
    ('10000000000', 'mismatch', 'unverified'),
    ('allocated@example.com', 'verified', 'verified'),
    ('different@example.com', 'verified', 'mismatch'),
])
def test_identity_only_compares_complete_same_kind(tmp_path, observed, claimed, expected):
    c, s, owner, args, evidence = login_fixture(tmp_path)
    result = s.direct.call(owner, {**args, 'action': 'checkpoint', 'checkpoint': {
        'native_login': {**evidence, 'state': claimed, 'observed_identity': observed}}})
    assert result['login_state'] == expected
    assert result['browser_ready'] == (expected == 'verified')
    assert c.snapshot(owner)['leases'][0]['native_context_binding']['login_state'] == expected


def test_assigned_ui_login_can_verify_masked_profile_but_not_allocation_alone(tmp_path):
    _, s, owner, args, evidence = login_fixture(tmp_path)
    initial = s.direct.call(owner, {**args, 'action': 'claim'})
    assert initial['context_reserved'] and not initial['browser_ready']
    proof = {**evidence, 'method': 'assigned_credentials_login', 'observed_identity': 'a***d@example.com'}
    incomplete = s.direct.call(owner, {**args, 'action': 'checkpoint', 'checkpoint': {'native_login': proof}})
    assert incomplete['login_state'] == 'unverified'
    result = s.direct.call(owner, {**args, 'action': 'checkpoint', 'checkpoint': {
        'native_login': {**proof, 'login_succeeded': True, 'evidence': '本租约分配账号已填写并提交，成功进入企业页面'}}})
    assert result['browser_ready'] and result['native_context_binding']['login_state'] == 'verified'


def test_evidence_cannot_rebind_other_account_or_context(tmp_path):
    _, s, owner, args, evidence = login_fixture(tmp_path)
    for patch in ({'account_id': 'other'}, {'environment_key': 'another-tab'}):
        with pytest.raises(Conflict, match='绑定'):
            s.direct.call(owner, {**args, 'action': 'checkpoint', 'checkpoint': {'native_login': {**evidence, **patch}}})
