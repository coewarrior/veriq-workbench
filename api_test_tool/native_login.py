"""Account evidence belongs to an allocated real context, never to a tab name."""
import copy
import re


def identity(value):
    value = str(value or '').strip().lower()
    if not value or any(mark in value for mark in ('*', '•', '…')):
        return None
    if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        return 'email', value
    if re.fullmatch(r'\+?[\d ()-]{6,}', value):
        return 'phone', re.sub(r'[^\d]', '', value)
    return None


def record_login(state, node, lease, value, now):
    from .orchestration import Conflict
    if not isinstance(value, dict):
        raise ValueError('native_login 必须是实际登录观察对象')
    if lease.get('revoked') or node['state'] != 'running':
        raise Conflict('原租约已停止，不能更新登录授权；原观察仍可保存')
    binding = lease.get('native_context_binding') or {}
    contexts = binding.get('contexts') or []
    account_id = value.get('account_id')
    context = next((row for row in contexts if row.get('account_id') == account_id
                    and row.get('environment_key') == value.get('environment_key')), None)
    if context is None:
        raise Conflict('登录观察必须属于当前租约已绑定的账号和真实浏览器上下文')
    requested, method = value.get('state'), value.get('method')
    if requested not in {'verified', 'unverified', 'mismatch'}:
        raise ValueError('登录状态必须是 verified/unverified/mismatch')
    evidence = value.get('evidence')
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError('请保留实际 UI 登录或身份核对依据')
    expected = identity(state['accounts'][account_id].get('identity'))
    observed = identity(value.get('observed_identity'))
    comparable = bool(expected and observed and expected[0] == observed[0])
    verified_login = (method == 'assigned_credentials_login'
                      and value.get('login_succeeded') is True and requested == 'verified')
    if comparable and expected != observed:
        status = 'mismatch'
    elif verified_login or (method == 'visible_identity' and comparable and expected == observed):
        status = 'verified'
    else:
        status = 'unverified'
    result = {'account_id': account_id, 'lease_id': lease['id'], 'environment_key': context['environment_key'],
              'state': status, 'method': method, 'evidence': evidence.strip(),
              'source': 'executor_reported', 'observed_at': now}
    context['login'] = copy.deepcopy(result)
    statuses = [row.get('login', {}).get('state', 'unverified') for row in contexts]
    binding['login_state'] = ('mismatch' if 'mismatch' in statuses else
                              'verified' if all(s == 'verified' for s in statuses) else 'unverified')
    node['native_login'] = copy.deepcopy(result)
    return result
