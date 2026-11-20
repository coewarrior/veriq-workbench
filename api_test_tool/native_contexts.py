"""Reported native login contexts, reserved in the existing account transaction.

These are executor reports of public browser capabilities, not server-created
browsers. Tabs, chats and display session names never create login capacity.
"""
from __future__ import annotations

import copy
import hashlib
import json
from urllib.parse import urlsplit

from .resource_projection import copy_node


def origin(value):
    invalid = '浏览器环境 origin 必须是无凭据的有效 HTTP/HTTPS 来源'
    if not isinstance(value, str):
        raise ValueError(invalid)
    try:
        parsed = urlsplit(value or '')
        hostname, port = parsed.hostname, parsed.port
    except ValueError:
        raise ValueError(invalid) from None
    if parsed.scheme not in {'http', 'https'} or not hostname or parsed.username or parsed.password:
        raise ValueError(invalid)
    hostname = hostname.lower()
    # Explicit default ports identify the same browser origin and cannot add
    # login capacity. Keep IPv6 brackets and actual non-default ports.
    authority = '[' + hostname + ']' if ':' in hostname else hostname
    if port is not None and port != {'http': 80, 'https': 443}[parsed.scheme]:
        authority += ':' + str(port)
    return f'{parsed.scheme}://{authority}'


def canonical_browser(value):
    name = _text(value, 'browser').lower()
    aliases = {'iab': 'iab', 'in-app-browser': 'iab', 'in_app_browser': 'iab',
               'in-app browser': 'iab', 'in app browser': 'iab',
               'codex-iab': 'iab', 'codex in-app browser': 'iab',
               'chrome': 'chrome', 'google chrome': 'chrome',
               'edge': 'edge', 'microsoft edge': 'edge', 'dot': 'dot', 'chromium': 'chromium'}
    if name not in aliases:
        raise ValueError('browser 必须是 iab/chrome/edge/dot/chromium 公开浏览器类型，不能使用每聊天数字 browserId 或自造别名')
    return aliases[name]


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' 必须来自实际公开浏览器环境')
    return value.strip()


def requires_context(node):
    return bool(node.get('native_context_protocol') or node.get('native_environment'))


def register_environment(state, node, owner, value):
    """Register an actual capability report; allocation and login remain separate."""
    from .orchestration import Conflict
    if node.get('owner') != owner:
        raise PermissionError('浏览器环境不属于当前任务')
    if not isinstance(value, dict):
        raise ValueError('browser_environment 必须是实际浏览器环境对象')
    host = _text(value.get('host_id'), 'host_id')
    browser = canonical_browser(value.get('browser'))
    target = origin(value.get('origin'))
    isolation = value.get('isolation')
    if isolation not in {'shared_profile', 'isolated'}:
        raise ValueError('isolation 必须明确 shared_profile 或有真实能力依据的 isolated')
    if browser == 'chromium' and isolation != 'isolated':
        raise ValueError('直接 Chromium 入口须使用实际新建的独立 BrowserContext')
    evidence = _text(value.get('evidence'), '浏览器环境依据')
    capability = None
    if isolation == 'shared_profile':
        # Every hidden tab and chat sees the same profile. Ignore invented IDs.
        context_id = 'shared-profile'
    else:
        context_id = _text(value.get('context_id'), '实际独立 context_id')
        capability = value.get('capability_evidence')
        if (not isinstance(capability, dict)
                or capability.get('source') != 'public_tool'
                or capability.get('capability') != 'isolated_login_context'
                or capability.get('context_id') != context_id
                or not isinstance(capability.get('reference'), str)
                or not capability['reference'].strip()):
            raise ValueError('独立登录上下文必须附公开工具能力及真实 context_id 依据；标签或 sessionName 不表示隔离')
        capability = {key: capability[key] for key in ('source', 'capability', 'context_id', 'reference')}
    canonical = [owner, host, browser, target, isolation, context_id]
    key = 'native-context:' + hashlib.sha256(json.dumps(canonical, ensure_ascii=False).encode()).hexdigest()
    generation = value.get('browser_generation', 0)
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise ValueError('browser_generation 必须为实际浏览器进程代际')
    exited_generation = node.get('native_exited_environment_generations', {}).get(key, 0)
    # Older clients report a real registration without process generations.
    # Keep their existing lifecycle/explicit-replacement path; unknown is not
    # evidence of a stale process. New complete evidence can fence old copies.
    if (browser == 'chromium' and generation > 0 and exited_generation > 0
            and key in node.get('native_exited_environment_keys', []) and generation <= exited_generation):
        raise Conflict('原 Chromium 环境已确认退出；需真实准备新环境，不能重报旧 context_id 冒充有效')
    report = dict(environment_key=key, owner=owner, host_id=host, browser=browser,
                  origin=target, isolation=isolation, context_id=context_id,
                  evidence=evidence, evidence_source='executor_reported', browser_generation=generation)
    if capability is not None:
        report['capability_evidence'] = capability
    for lease in state['leases'].values():
        if lease['node_id'] != node['id']:
            continue
        binding = lease.get('native_context_binding')
        if not binding:
            raise Conflict('在途旧租约保留原现场；先沿原退出流程交还，不能改写未知登录环境')
        keys = {row['environment_key'] for row in (binding or {}).get('contexts', [])}
        if binding and key not in keys:
            raise Conflict('活动租约仍绑定原浏览器上下文；先沿原退出流程交还，不能热迁移')
    state.setdefault('native_browser_environments', {})[key] = copy.deepcopy(report)
    node['native_environment'] = copy.deepcopy(report)
    keys = node.setdefault('native_environment_keys', [])
    if key not in keys:
        keys.append(key)
    node.setdefault('native_environment_generations', {})[key] = generation
    node['native_context_protocol'] = 1
    # This records actual creation/registration, never repairs an old revision.
    node['native_environment_lifecycle'] = {'state': 'ready',
        'dispatch_id': (node.get('executor_dispatch') or node.get('dispatch_offer') or {}).get('dispatch_id')
                       or (node.get('dispatch_offer') or {}).get('id'),
        'holder_id': (node.get('executor_dispatch') or node.get('dispatch_offer') or {}).get('holder_id')}
    node['native_environment_revision'] = node.get('revision')
    return copy.deepcopy(report)


def _occupied(state, node, environment, ignore_lease):
    for lease in state['leases'].values():
        if lease['id'] == ignore_lease or not lease.get('native_browser'):
            continue
        other = state['nodes'].get(lease['node_id'], {})
        if other.get('owner') != node.get('owner'):
            continue
        binding = lease.get('native_context_binding')
        if binding:
            contexts = binding.get('contexts') or [binding]
            if any(item.get('environment_key') == environment['environment_key'] for item in contexts):
                return True
            continue
        # A freshly created independent Context cannot inherit a legacy tab's
        # cookies. An unmapped old browser must not serialize every new context
        # on the same site. Account ownership/fairness still runs separately.
        if environment['isolation'] == 'isolated':
            continue
        # A legacy active browser has no attested profile mapping. Keep it
        # running, but don't reuse an unknown shared profile over its scene.
        old_environment = other.get('native_environment') or {}
        old_host = old_environment.get('host_id')
        if old_host and old_host != environment['host_id']:
            continue
        targets = [state['accounts'][aid].get('target', '') for aid in lease.get('account_ids', [])
                   if aid in state['accounts']]
        try:
            overlapping = not targets or any(origin(target) == environment['origin'] for target in targets)
        except (ValueError, TypeError, AttributeError):
            # Unknown legacy location cannot become extra browser capacity or
            # abort the scheduler for unrelated well-formed projects.
            overlapping = True
        if overlapping:
            return True
    return False


def choose_context(state, node, account_ids, ignore_lease=None):
    """Return the complete available context set, None for a real resource wait.

    Empty dict keeps already running legacy protocol leases compatible; every
    new public claim opts into the context protocol before scheduling.
    """
    isolated_default = state['tasks'][node['task_id']].get('native_browser_policy') == 'direct_isolated'
    if (not requires_context(node) and not isolated_default) or not account_ids:
        return {}
    task = state['tasks'][node['task_id']]
    if (task.get('intent') != 'run' or node.get('control_intent', 'run') != 'run'
            or task.get('account_project_deleted') or node.get('session_removed')):
        return None
    lifecycle = node.get('native_environment_lifecycle')
    binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
    if lifecycle:
        if (lifecycle.get('state') != 'ready'
                or (lifecycle.get('dispatch_id') and lifecycle['dispatch_id'] != (binding.get('dispatch_id') or binding.get('id')))
                or (lifecycle.get('holder_id') and lifecycle['holder_id'] != binding.get('holder_id'))):
            return None
    elif node.get('native_environment_revision') != node.get('revision') or node.get('native_browser_stopped'):
        # Legacy unknown scenes keep their original fence; a real registration
        # or exited-environment preparation is required, never a revision edit.
        return None
    registry = state.get('native_browser_environments', {})
    keys = node.get('native_environment_keys', [])
    if not keys and node.get('native_environment'):
        keys = [node['native_environment'].get('environment_key')]
    environments = [registry[key] for key in keys if key in registry and registry[key].get('owner') == node['owner']]
    if isolated_default:
        environments = [item for item in environments if item.get('isolation') == 'isolated']
    contexts = []
    taken = set()
    for account_id in account_ids:
        account = state['accounts'].get(account_id)
        if not account or account.get('owner') != node['owner']:
            return None
        target = origin(account['target'])
        environment = next((item for item in environments
                            if item['origin'] == target and item['environment_key'] not in taken
                            and not _occupied(state, node, item, ignore_lease)), None)
        if environment is None:
            return None
        taken.add(environment['environment_key'])
        contexts.append({**copy.deepcopy(environment), 'account_id': account_id})
    return {**copy.deepcopy(contexts[0]), 'account_ids': list(account_ids), 'contexts': contexts,
            'login_state': 'unverified', 'context_reserved': True}


def lease_context_fields(state, node, account_ids, ignore_lease=None):
    binding = choose_context(state, node, account_ids, ignore_lease)
    if binding is None:
        return None
    if not binding:
        return {}
    return {'native_context_binding': binding, 'context_id': binding['context_id'],
            'browser_units': len(binding['contexts'])}


def can_prepare_for_wake(state, node, account_ids):
    """A closed isolated executor can prepare again after a resource wake.

    This is notification eligibility only, never live browser capacity. Claims
    still require current real environments through choose_context/grant.
    """
    task = state['tasks'][node['task_id']]
    if (task.get('native_browser_policy') != 'direct_isolated'
            or task.get('execution_route') != 'native_browser'
            or task.get('intent') != 'run' or node.get('control_intent', 'run') != 'run'
            or node.get('state') != 'queued'
            or any(lease['node_id'] == node['id'] for lease in state['leases'].values())):
        return False
    capability_source = node
    # A formal continuation has a new dispatch and deliberately no live browser.
    # Follow its exact source only for preparation capability, never copy the old
    # context into the new node or make it available to claim/grant.
    if not node.get('native_environment_keys') and not node.get('native_environment'):
        from .native_identity import same_executor_ref
        seen = {node['id']}
        while not capability_source.get('native_environment_keys'):
            link = capability_source.get('continuation_source') or {}
            previous = state['nodes'].get(link.get('source_node_id'), {})
            previous_task = state['tasks'].get(previous.get('task_id'), {})
            current_binding = capability_source.get('executor_dispatch') or {}
            previous_binding = previous.get('executor_dispatch') or {}
            if (not previous or previous['id'] in seen
                    or previous.get('owner') != node['owner']
                    or previous.get('task_id') != link.get('source_task_id')
                    or previous_task.get('intent') != 'run'
                    or previous.get('control_intent', 'run') != 'run'
                    or previous.get('session_removed') or previous_task.get('account_project_deleted')
                    or previous.get('record_successor_node_id') != capability_source['id']
                    or previous.get('state') not in {'completed', 'blocked'}
                    or any(previous.get('record_' + field) != link.get(field)
                           or capability_source.get('record_' + field) != link.get(field)
                           for field in ('project_id', 'execution_id'))
                    or not current_binding.get('holder_id')
                    or current_binding['holder_id'] != previous_binding.get('holder_id')
                    or not current_binding.get('executor_ref')
                    or not same_executor_ref(current_binding['executor_ref'], previous_binding.get('executor_ref'))
                    or previous.get('native_browser_stopped') is not True
                    or not previous_binding.get('exit_acknowledged_at')
                    or any(lease['node_id'] == previous['id'] for lease in state['leases'].values())):
                return False
            seen.add(previous['id'])
            capability_source = previous
    from .deployment_activity import resumed_node_exit
    source_exit = ((capability_source.get('executor_dispatch') or {}).get('exit_acknowledged_at')
                   or resumed_node_exit(capability_source))
    if capability_source.get('native_browser_stopped') is not True or not source_exit:
        return False
    registry = state.get('native_browser_environments', {})
    available = []
    for key in capability_source.get('native_environment_keys', []):
        environment = registry.get(key, {})
        capability = environment.get('capability_evidence') or {}
        if (environment.get('owner') == node['owner'] and environment.get('isolation') == 'isolated'
                and environment.get('browser') == 'chromium'
                and capability.get('source') == 'public_tool'
                and capability.get('capability') == 'isolated_login_context'
                and capability.get('context_id') == environment.get('context_id')):
            available.append(environment['origin'])
    for account_id in account_ids:
        account = state['accounts'].get(account_id, {})
        if account.get('owner') != node['owner']:
            return False
        target = origin(account['target'])
        if target not in available:
            return False
        # A verified isolated runtime can create the next stage's larger set
        # after its actual exit. This grants no accounts or existing capacity.
        if not node.get('checkpoint', {}).get('work_plan'):
            available.remove(target)
    return bool(account_ids)


def wait_reason(node):
    if not node.get('native_environment'):
        return '尚未登记实际浏览器登录环境；平台等待可用环境，不是账号不一致'
    return '等待真实浏览器登录上下文交还或补齐；隐藏标签不增加登录容量，不中断已运行模块'


def replace_exited_environment(state, node, lease, owner, value, now):
    """Explicit lifecycle repair of the same binding, never an action permission.

    The executor attests actual exit. Keep the account set, queue position,
    execution record, case IDs and original holder; do not wake any worker.
    """
    from .orchestration import Conflict
    task = state['tasks'][node['task_id']]
    if lease.get('revoked') or node.get('state') != 'running' or task.get('intent') != 'run' or node.get('control_intent', 'run') != 'run':
        raise Conflict('已停止的任务不能通过环境替换恢复')
    if not isinstance(value, dict) or value.get('browser_stopped') is not True:
        raise ValueError('替换环境需要原浏览器真实退出依据')
    reason = _text(value.get('reason'), '原环境退出依据')
    from .cleanup_capabilities import blockers
    if blockers(state, lease, replacing=True):
        raise Conflict('原对象操作或物理现场仍待核实，不能替换环境')
    old = lease.get('native_context_binding') or {}
    original_ids = value.get('previous_context_ids')
    environments = value.get('browser_environments')
    if not isinstance(environments, list) or len(environments) != len(lease.get('account_ids', [])) or not environments:
        raise ValueError('新环境必须覆盖原账号集合，不能改变并发或账号分配')
    audit = lease.get('native_environment_replacement')
    if audit and audit.get('request') == value:
        return copy.deepcopy(audit)  # Lost receipt: idempotent, no second mutation.
    if not isinstance(original_ids, list) or sorted(original_ids) != sorted(row['context_id'] for row in old.get('contexts', [])):
        raise Conflict('原环境已变化，不能覆盖现有绑定')
    candidate_node = copy_node(node)
    candidate_node['native_environment_keys'] = []
    candidate_state = {**state, 'leases': {}, 'native_browser_environments': copy.deepcopy(state.get('native_browser_environments', {}))}
    reports = [register_environment(candidate_state, candidate_node, owner, item) for item in environments]
    if any(item['isolation'] != 'isolated' for item in reports) or len({item['environment_key'] for item in reports}) != len(reports):
        raise ValueError('必须使用彼此独立的实际浏览器环境')
    if any(item['context_id'] in original_ids or _occupied(state, node, item, lease['id']) for item in reports):
        raise Conflict('不能替换为原环境或其他执行者占用的环境')
    candidate_state['leases'] = state['leases']
    binding = choose_context(candidate_state, candidate_node, lease['account_ids'], lease['id'])
    if not binding:
        raise Conflict('新环境与原账号目标不匹配')
    audit = {'request': copy.deepcopy(value), 'previous_binding': copy.deepcopy(old), 'at': now, 'reason': reason}
    node['native_exited_environment_keys'] = list(dict.fromkeys([
        *node.get('native_exited_environment_keys', []),
        *(item['environment_key'] for item in old.get('contexts', []))]))
    exited = node.setdefault('native_exited_environment_generations', {})
    for item in old.get('contexts', []):
        key = item['environment_key']
        exited[key] = max(exited.get(key, 0), node.get('native_environment_generations', {}).get(key, item.get('browser_generation', 0)))
    lease.setdefault('native_environment_history', []).append(copy.deepcopy(audit))
    lease.update(native_context_binding=binding, context_id=binding['context_id'], browser_units=len(binding['contexts']),
                 native_environment_replacement=copy.deepcopy(audit))
    for key in ('native_environment', 'native_environment_keys', 'native_environment_generations', 'native_context_protocol', 'native_environment_revision', 'native_environment_lifecycle'):
        node[key] = copy.deepcopy(candidate_node[key])
    state['native_browser_environments'] = candidate_state['native_browser_environments']
    return audit


def invalidate(node, state, now):
    if state == 'exited':
        node['native_exited_environment_keys'] = list(dict.fromkeys([
            *node.get('native_exited_environment_keys', []), *node.get('native_environment_keys', [])]))
        exited = node.setdefault('native_exited_environment_generations', {})
        for key in node.get('native_environment_keys', []):
            exited[key] = max(exited.get(key, 0), node.get('native_environment_generations', {}).get(key, 0))
    lifecycle = node.get('native_environment_lifecycle')
    if lifecycle:
        node['native_environment_lifecycle'] = {**lifecycle, 'state': state, 'changed_at': now}
