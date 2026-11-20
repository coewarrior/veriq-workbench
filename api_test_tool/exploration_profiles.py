"""Platform-owned exploration contracts and generic browser prerequisites.

Product request shapes are data, not branches in the browser or scheduler.
Unknown projects use exclusive live verification under the user's revised D01
evidence rule. Provisioning itself never calls the target service.
"""
from __future__ import annotations
import copy
from functools import lru_cache
import json
from pathlib import Path
import re
from .browser_policy import origin

ADAPTER_SCHEMA = 3


@lru_cache(maxsize=1)
def profiles():
    document = json.loads((Path(__file__).parent/'static/exploration-profiles.json').read_text())
    if document.get('schema') != ADAPTER_SCHEMA:
        raise ValueError('平台探索接入协议版本不兼容')
    identifiers = set()
    targets = set()
    for profile in document['profiles']:
        if (not profile.get('id') or profile['id'] in identifiers
                or profile.get('session_strategy') != 'independent_login'
                or not profile.get('origins') or not profile.get('evidence')):
            raise ValueError('平台探索接入定义不完整或版本重复')
        identifiers.add(profile['id'])
        for target in profile['origins']:
            if origin(target) != target or target in targets:
                raise ValueError('平台探索接入目标不明确或冲突')
            targets.add(target)
        checks = profile.get('observations', [])
        keys = [check.get('key') for check in checks]
        if not keys or not all(keys) or 'profile' in keys or len(set(keys)) != len(keys):
            raise ValueError('平台探索准备条件必须明确且互不重复')
        for check in checks:
            if not check.get('body_equals') and not check.get('body_types'):
                raise ValueError('响应成功本身不是完成准备的证据')
            for kind in check.get('body_types', {}).values():
                if kind not in {'object','array','string','boolean','number','null'}:
                    raise ValueError('平台探索响应条件类型无效')
            for path in [*check.get('body_equals', {}), *check.get('body_types', {})]:
                if not path.startswith('/'):
                    raise ValueError('平台探索响应条件必须使用 JSON pointer')
        if not profile.get('rules'):
            raise ValueError('平台探索接入缺少经核验的请求集合')
        for item in [*profile['rules'], *checks]:
            if (item.get('origin') not in ['$target', *profile['origins']]
                    or not item.get('path','').startswith('/') or not item.get('method')):
                raise ValueError('平台探索请求条件无效')
        for rule in profile['rules']:
            if rule.get('effect') not in {'verified_read','isolated_write','isolated_session','prepared_read'}:
                raise ValueError('平台探索请求效果未核验')
            if rule['effect'] == 'isolated_write' and not rule.get('namespace_field'):
                raise ValueError('平台探索隔离写入缺少对象约束')
            for section in ('body', 'query'):
                for binding in rule.get(section+'_bindings', {}).values():
                    if (binding.get('field') not in {'identity','target','environment','tenant'}
                            or binding.get('format','literal') not in {'literal','optional_cn_phone_prefix'}):
                        raise ValueError('平台探索账号字段绑定无效')
                for pattern in [*rule.get(section+'_patterns', {}).values(),
                                *rule.get('optional_'+section+'_patterns', {}).values()]:
                    re.compile(pattern)
            if rule.get('credential_fields'):
                if (rule['effect'] != 'isolated_session'
                        or any(value not in {'username','password'} for value in rule['credential_fields'].values())):
                    raise ValueError('平台探索登录凭据绑定无效')
    return document['profiles']


def profile_for(account):
    try:
        target = origin(account['target'])
    except (KeyError, ValueError):
        return None
    if not account.get('identity'):
        return None
    return next((p for p in profiles() if target in p['origins']), None)


def supported(account):
    return profile_for(account) is not None


def builtin(policy, account):
    from .exploration_learning import PROFILE
    if policy.get('automatic_profile') == PROFILE:
        return (policy.get('adapter_schema') == ADAPTER_SCHEMA
                and policy.get('target_origin') == origin(account['target'])
                and policy.get('auth_generation') == account.get('auth_generation', ''))
    profile = profile_for(account)
    return bool(profile and policy.get('automatic_profile') == profile['id']
                and policy.get('adapter_schema') == ADAPTER_SCHEMA)


def bound_pattern(account, binding):
    value = str(account[binding['field']]).strip()
    if binding.get('format') == 'optional_cn_phone_prefix':
        phone = re.sub(r'[\s()-]', '', value)
        if re.fullmatch(r'(?:\+?86)?1[0-9]{10}', phone):
            return r'(?:\+?86)?' + phone[-11:]
    elif binding.get('format', 'literal') != 'literal':
        raise ValueError('未知账号字段格式，不能扩大请求范围')
    return re.escape(value)


def provision(state, account):
    """Use the same live onboarding for every project, including known origins.

    Historical source adapters remain readable for active leases, but cannot
    replace verification against the project's current login and page behavior.
    """
    return provision_observed(state, account)


def provision_observed(state, account):
    """Every configured project can enter exclusive live preparation."""
    from .exploration_learning import PROFILE
    from .orchestration import digest
    target = origin(account['target'])
    previous = state['policies'].get(account.get('policy_id'))
    if previous and (not previous.get('automatic_profile')
                     or (not previous.get('enabled') and not previous.get('automatic_fault'))):
        return previous
    generation = account.get('auth_generation', '')
    if (previous and previous.get('automatic_profile') == PROFILE
            and builtin(previous, account) and previous.get('projects') == account['projects']
            and not previous.get('automatic_fault')):
        return previous
    # Never replace a failed batch's contract while any member still holds it.
    if previous and any(l.get('policy_id') == previous['id'] for l in state['leases'].values()):
        return previous
    pid = 'auto-' + digest([ADAPTER_SCHEMA, PROFILE, account['id'], generation, account['projects']])[:32]
    policy = dict(id=pid, owner=account['owner'], projects=list(account['projects']),
                  project_id=account['projects'][0], version=PROFILE, automatic_profile=PROFILE,
                  adapter_schema=ADAPTER_SCHEMA, target_origin=target, enabled=True,
                  session_compatible=False, session_strategy='verified_storage_copy',
                  auth_generation=generation, operations={}, rules=[], observations=[], preparation='pending')
    state['policies'][pid] = policy
    account['policy_id'] = pid
    return policy


def accept_observed(controller, state, lease, node, verification, seed):
    """Only a broker operation receipt can activate an empirically checked set."""
    from .exploration_learning import PROFILE, candidate, rule_key
    from .orchestration import digest
    from .resource_scheduler import pending_operations, ResourceScheduler
    if not isinstance(verification, dict) or verification.get('profile') != PROFILE:
        return False
    policy = state['policies'].get(lease.get('policy_id'), {})
    account = state['accounts'][lease['account_ids'][0]]
    evidence = verification.get('evidence', {})
    if (not lease.get('exploration_bootstrap') or lease.get('mode') != 'exclusive'
            or not builtin(policy, account) or not policy.get('enabled')
            or policy.get('automatic_profile') != PROFILE or lease.get('revoked')
            or account.get('policy_id') != policy.get('id') or lease.get('browser_units',1) < 2
            or lease['epoch'] != state['epoch'] or lease['revision'] != node['revision']
            or node['state'] != 'running' or node.get('phase') != 'exploration'
            or node.get('exclusive_exploration') or node.get('exploration_complete') or node.get('locks')
            or node.get('control_intent','run') != 'run' or state['tasks'][node['task_id']]['intent'] != 'run'
            or lease.get('auxiliary_channels') or pending_operations(state,lease['id'])
            or ResourceScheduler(controller,state,controller.clock()).holders(account['id'],lease['id'])
            or state['runners'][lease['runner_id']].get('evidence',{}).get('automatic_exploration',0) < ADAPTER_SCHEMA
            or evidence.get('kind') != 'live_empirical' or evidence.get('comparisons_per_entry') != 2
            or evidence.get('session_copy_checked') is not True or evidence.get('source_session_checked') is not True
            or evidence.get('concurrent_session_checked') is not True
            or not isinstance(seed,dict) or not (seed.get('cookies') or seed.get('origins')
                                                or any(seed.get('session_storage',{}).values()))):
        return False
    rules = verification.get('rules')
    entries = verification.get('entry_urls')
    if not isinstance(rules,list) or not rules or not isinstance(entries,list) or not entries:
        raise ValueError('实时核验没有可复用的入口及请求')
    for rule in rules:
        if (not isinstance(rule,dict) or rule.get('effect') != 'observed_read'
                or rule.get('method') not in {'GET','POST'} or origin(rule['origin']) != rule['origin']
                or rule.get('path_pattern') != re.escape(rule.get('path',''))
                or not rule.get('path','').startswith('/')
                or not re.fullmatch(r'[a-f0-9]{64}',rule.get('query_hash',''))
                or not re.fullmatch(r'[a-f0-9]{64}',rule.get('body_hash',''))
                or set(rule)-{'origin','path','path_pattern','method','effect','query_hash','body_hash'}):
            raise ValueError('实时核验只能提交实际比较过的精确读取请求')
    known = {rule_key(rule) for rule in rules}
    for url in entries:
        rule = candidate(url,'GET',None,'document',policy['target_origin'])
        if not rule or origin(url) != policy['target_origin'] or rule_key(rule) not in known:
            raise ValueError('实时核验入口未关联实际读取规则')
    version = PROFILE+'-'+digest([rules,entries,lease['id']])[:24]
    assets = verification.get('asset_fingerprints',{})
    if not isinstance(assets,dict) or any(not re.fullmatch(r'[a-f0-9]{64}',k) or not re.fullmatch(r'[a-f0-9]{64}',v) for k,v in assets.items()):
        raise ValueError('页面版本指纹无效')
    policy.update(version=version, rules=copy.deepcopy(rules), entry_urls=list(entries),
                  asset_fingerprints=dict(assets),
                  session_compatible=True, preparation='verified', approved_by='platform-live-verification',
                  evidence={**evidence,'verified_at':controller.clock(),'lease_id':lease['id']},
                  session_seed=controller.store._cipher.encrypt(json.dumps(seed).encode()).decode())
    lease['exploration_live_verified'] = version
    return promote(controller,state,lease,node,{'profile':PROFILE,'verified_version':version})


def report_fault(state, lease, reason):
    """Stop new shared requests; members retain evidence and use normal handoff."""
    policy = state['policies'].get(lease.get('policy_id'), {})
    if not policy.get('automatic_profile') or lease.get('mode') != 'shared':return
    policy.update(enabled=False, automatic_fault=True, preparation='failed', preparation_reason=reason)
    for member in state['leases'].values():
        if member.get('policy_id') != policy.get('id') or member.get('mode') != 'shared':continue
        member['exploration_fault'] = reason
        state['nodes'][member['node_id']]['reason'] = reason+'；保存已有设计，沿原队列转独占继续'
    for aid in lease['account_ids']:
        batch = state['accounts'][aid].get('exploration_batch')
        if batch:batch.update(state='draining',reason=reason)


def pointer(payload, path):
    """Read a JSON pointer without evaluating expressions from a contract."""
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('响应条件必须使用 JSON pointer')
    current = payload
    for component in path[1:].split('/'):
        key = component.replace('~1', '/').replace('~0', '~')
        if isinstance(current, dict):
            current = current[key]
        elif isinstance(current, list) and component.isdecimal():
            current = current[int(component)]
        else:
            raise KeyError(path)
    return current


def observation_matches(check, payload):
    types = {'object':dict, 'array':list, 'string':str, 'boolean':bool,
             'number':(int, float), 'null':type(None)}
    try:
        return (all(pointer(payload, path) == value for path, value in check.get('body_equals', {}).items())
                and all(type(pointer(payload, path)) in (types[kind] if isinstance(types[kind], tuple) else (types[kind],))
                        for path, kind in check.get('body_types', {}).items()))
    except (KeyError, IndexError, ValueError, TypeError):
        return False


def promote(controller, state, lease, node, observations):
    """Existing browser completion receipt opens a prepared batch atomically."""
    from .resource_scheduler import pending_operations
    from .orchestration import uid
    if not lease.get('exploration_bootstrap'):
        return False
    policy = state['policies'].get(lease.get('policy_id'), {})
    account = state['accounts'][lease['account_ids'][0]]
    required = {check['key'] for check in policy.get('observations', [])}
    expected = {'profile':policy.get('automatic_profile'), **dict.fromkeys(required, True)}
    from .exploration_learning import PROFILE
    empirical = policy.get('automatic_profile') == PROFILE
    if empirical:
        expected = {'profile':PROFILE,'verified_version':policy.get('version')}
        required = lease.get('exploration_live_verified') == policy.get('version') and policy.get('preparation') == 'verified'
    if (not builtin(policy, account) or not policy.get('enabled') or not required
            or policy.get('auth_generation') != account.get('auth_generation', '')
            or account.get('policy_id') != policy.get('id')
            or lease.get('revoked') or lease['epoch'] != state['epoch']
            or lease['revision'] != node['revision'] or node.get('phase') != 'exploration'
            or node.get('exclusive_exploration') or node.get('exploration_complete')
            or node.get('locks') or node['state'] != 'running'
            or node.get('control_intent','run') != 'run' or lease.get('auxiliary_channels')
            or state['runners'].get(lease['runner_id'],{}).get('evidence',{}).get('automatic_exploration', 0) < ADAPTER_SCHEMA
            or state['tasks'][node['task_id']]['intent'] != 'run'
            or observations != expected or pending_operations(state, lease['id'])):
        return False
    batch = dict(id=uid(), state='open', policy_id=policy['id'], created=controller.clock(),
                 revision=1, target_node=None, reason='', members=[node['id']], prepared=True)
    account.update(exploration_batch=batch, pool='exploration')
    lease.update(mode='shared', exploration_bootstrap=False, exploration_batch_id=batch['id'],
                 resource_version=lease.get('resource_version', 1)+1)
    if empirical:
        lease['browser_units'] = len(lease['account_ids'])
        policy['session_batch_id'] = batch['id']
    node['reason'] = '账号实时准备完成，共享探索已开放；各模块使用独立浏览器上下文'
    return True
