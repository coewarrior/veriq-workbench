"""Cleanup evidence and ownership metadata; never performs business requests.

The caller supplies server-read project policy in state['_cleanup_authority'],
keyed by source node. Never copy that projection from client arguments. Calls
run inside the existing control transaction, including boundary batches.
"""
import copy
from urllib.parse import urlsplit

from .orchestration import Conflict, uid, text
from .cleanup_contract import CleanupScopeError, validate_cleanup_events


SCOPE = ('origin', 'environment', 'tenant', 'role', 'object_type')
CAP_SCOPE = (*SCOPE, 'entry_source', 'service_version')
OBJECT_SCOPE = ('origin', 'environment', 'tenant', 'object_type', 'object_id')
UNCERTAIN = {'creating', 'cleaning', 'unknown'}
KNOWN_NO_EFFECT = {'not_sent', 'rejected', 'not_applied'}


def _origin(value):
    parsed = urlsplit(text(value, 'origin', 2000))
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
            or parsed.username or parsed.password or parsed.path not in {'', '/'}
            or parsed.query or parsed.fragment):
        raise ValueError('来源必须是无凭据、路径或查询参数的 HTTP origin')
    return parsed.scheme.lower() + '://' + parsed.netloc.lower()


def _scope(state, lease, node, account_id, spec):
    account = _account(state, lease, node, account_id)
    roles = account.get('roles') or []
    result = {'origin': _origin(account['target']),
              'environment': account.get('environment') or account['target'],
              'tenant': account.get('tenant') or '',
              'role': roles[0] if len(roles) == 1 else '',
              'object_type': text(spec.get('object_type'), 'object_type', 2000),
              'account_id': account_id}
    for key in ('origin', 'environment', 'tenant', 'role'):
        if key in spec:
            result[key] = _origin(spec[key]) if key == 'origin' else spec[key].strip()
    _account(state, lease, node, account_id, result)
    return result


def _same(left, right, fields):
    return all(left.get(key, '') == right.get(key, '') for key in fields)


def _same_scope(left, right, fields):
    # Unknown tenant/role is an honest fact, never a shared authority wildcard.
    if any(not row.get(key) for row in (left, right) for key in ('tenant', 'role')):
        fields = (*fields, 'account_id')
    return _same(left, right, fields)


def _authority(state, node):
    value = state.get('_cleanup_authority', {}).get(node['id']) or {}
    task = state['tasks'][node['task_id']]
    if (value.get('owner') != node['owner'] or value.get('task_id') != task['id']
            or value.get('source_node_id') != node['id']
            or value.get('project_id') != task['project_id']):
        raise Conflict('缺少本轮服务端读取的现场及执行授权；不能从请求文字推定授权')
    return value


def _account(state, lease, node, account_id, scope=None):
    from .account_projects import resource_project
    account = state['accounts'].get(account_id)
    if (not account or account.get('owner') != node['owner']
            or account_id not in lease['account_ids']):
        raise CleanupScopeError('清理 account_id 不属于当前原租约的账号范围')
    if resource_project(node) not in account.get('projects', []):
        raise CleanupScopeError('清理 account_id 不属于原任务的 project 授权范围')
    if scope is not None:
        expected = {'origin': _origin(account['target']),
                    'environment': account.get('environment') or account['target'],
                    'tenant': account.get('tenant') or ''}
        for key, value in expected.items():
            if scope.get(key) != value:
                raise CleanupScopeError('清理 ' + key + ' 与原账号的可信范围不一致')
        if scope.get('role') not in (account.get('roles') or ['']):
            raise CleanupScopeError('清理 role 与原账号的可信范围不一致；未知角色不得推定')
    return account


def _node_locks(node):
    return list(dict.fromkeys([*node.get('inherited_locks', []), *node.get('locks', [])]))



def _resource_context(lease, account_id):
    contexts = (lease.get('native_context_binding') or {}).get('contexts', [])
    fields = ('account_id', 'context_id', 'environment_key', 'host_id', 'origin',
              'browser', 'browser_generation', 'isolation')
    return {'lease_id': lease['id'], 'lease_revision': lease.get('revision'),
        'contexts': [{key: copy.deepcopy(row[key]) for key in fields if key in row}
                     for row in contexts if row.get('account_id') == account_id]}



def _case_scope(state, node, case_id, checkpoint_id=''):
    text(case_id, 'case_id', 2000)
    record = _authority(state, node).get('record') or {}
    case = next((c for c in record.get('cases', []) if c.get('case_id') == case_id), None)
    if not case or checkpoint_id and not any(p.get('id') == checkpoint_id for p in case.get('checkpoints', [])):
        raise CleanupScopeError('Object responsibility must reference this original case/checkpoint')



def _consumer(state, value, node):
    if not isinstance(value, dict) or value.get('source_node_id') != node['id']:
        raise CleanupScopeError('Consumer must belong to the original module')
    _case_scope(state, node, value.get('case_id'), value.get('checkpoint_id', ''))
    result = {key: value[key] for key in ('source_node_id', 'case_id', 'checkpoint_id', 'work_unit_id') if value.get(key)}
    if result.get('work_unit_id') and not any(u['id'] == result['work_unit_id'] for u in node.get('checkpoint', {}).get('work_plan', {}).get('units', [])):
        raise CleanupScopeError('Consumer work unit is outside the original plan')
    return result



def _explicit(authority, field, obj):
    """Only server-projected existing user decisions override round policy."""
    return next((row for row in authority.get(field, []) if isinstance(row, dict)
                 and row.get('authorized') is True and row.get('evidence_ref')
                 and row.get('source_node_id') == obj['source_node_id']
                 and _same(row.get('object_scope') or {}, obj, (*OBJECT_SCOPE, 'account_id'))), None)


def _retention(authority, obj):
    explicit = _explicit(authority, 'retention_authorizations', obj)
    if explicit:
        return {'kind': 'explicit', 'evidence_ref': explicit['evidence_ref']}
    policy = (authority.get('scene_retention') or {}).get('key', 'none')
    permitted = policy == 'full' or (policy == 'test_data' and obj.get('kind') in {'test_data', 'file'})
    if policy == 'defects':
        cases = (authority.get('record') or {}).get('cases', [])
        failed = {case['case_id'] for case in cases if case.get('status') == 'failed'}
        permitted = bool(obj.get('defect_case_ids') and obj.get('retention_evidence_ref')
                         and set(obj['defect_case_ids']) <= failed)
    return {'kind': 'scene_retention', 'key': policy, 'project_id': authority['project_id']} if permitted else None


def _cleanup_allowed(authority, obj):
    explicit = _explicit(authority, 'cleanup_authorizations', obj)
    if not explicit and (authority.get('execution_permission') or {}).get('key') not in {'full', 'maximum'}:
        raise CleanupScopeError('当前原授权不包含持久对象清理；保留实际待办')
    if _retention(authority, obj) and not explicit:
        raise Conflict('原持久化设置要求保留此对象，不能以清理能力覆盖保留授权')
    return copy.deepcopy(explicit) if explicit else {'kind': 'execution_permission',
        'key': authority['execution_permission']['key'], 'project_id': authority['project_id']}


def classify(observation):
    """HTTP failure is not proof that a mutating request had no effect."""
    if observation.get('effect_state') in {'pending', 'unknown'}:
        return 'unknown'
    status = observation.get('status')
    detail = str(observation.get('detail') or (observation.get('problem') or {}).get('detail', ''))
    if status == 404 and any(v in detail.lower() for v in ('白名单', 'whitelist', 'not allowed by proxy')):
        return 'proxy_rejected'
    if status == 405:
        return 'method_unsupported'
    if status in {401, 403}:
        return 'permission_denied'
    if status == 404:
        if (observation.get('object_identity_verified') is True
                and observation.get('principal_verified') is True
                and observation.get('absence_contract_ref') and observation.get('evidence_ref')):
            return 'object_absent'
        return 'route_or_permission_unknown'
    if (observation.get('business_completed') is True and observation.get('evidence_ref')
            and (status is None or type(status) is int and 200 <= status < 300)):
        return 'confirmed'
    if observation.get('effect_state') in KNOWN_NO_EFFECT and observation.get('evidence_ref'):
        return 'known_failure'
    return 'unknown'


def _observation(obj, observation):
    if not isinstance(observation, dict):
        raise ValueError('原观察必须为对象')
    text(observation.get('evidence_ref'), '实际观察证据', 2000)
    scope = observation.get('object_scope') or {}
    if not isinstance(scope, dict) or not _same(scope, obj, (*OBJECT_SCOPE, 'account_id')):
        raise CleanupScopeError('观察的对象、账号、企业或环境与原责任不一致')
    return classify(observation)


def _result_state(classification, observation):
    # The executor owns the business conclusion. Description strings and HTTP
    # diagnostics must not overturn explicit original-operation facts.
    if observation.get('original_operation_resolved') is False:
        return 'unknown'
    if observation.get('business_completed') is True:
        return 'cleaned'
    if (observation.get('original_operation_resolved') is True
            and observation.get('business_completed') is False):
        return 'residual'
    if 'business_completed' in observation or 'original_operation_resolved' in observation:
        return 'unknown'
    # Compatibility for receipts written before explicit completion facts.
    if classification in {'confirmed', 'object_absent'}:
        return 'cleaned'
    if observation.get('effect_state') in KNOWN_NO_EFFECT:
        return 'residual'
    if classification == 'proxy_rejected':
        return 'residual'  # Explicit front-door rejection never reached the handler.
    return 'unknown'


def _capability(state, lease, node, values, now):
    caps = state.setdefault('cleanup_capabilities', {})
    spec = values.get('capability') or {}
    scope = _scope(state, lease, node, spec.get('account_id'), spec)
    scope.update(entry_source=text(spec.get('entry_source'), 'entry_source', 2000),
                 service_version=str(spec.get('service_version') or ''))
    evidence = text(spec.get('evidence_ref'), '能力契约或真实入口依据', 2000)
    methods = spec.get('methods')
    if not isinstance(methods, list) or not methods:
        raise ValueError('能力登记需要具体有证据的方法；仅授权保留直接登记对象即可')
    for method in methods:
        if not isinstance(method, dict) or method.get('kind') not in {'ui', 'api'}:
            raise ValueError('清理方法必须为真实 UI 或 API 入口')
        text(method.get('entry'), '清理入口', 2000)
        text(method.get('evidence_ref'), '方法适用证据', 2000)
        if method['kind'] == 'api':
            parsed = urlsplit(method['entry'])
            if parsed.username or parsed.password or parsed.fragment or (parsed.netloc and
                    parsed.scheme.lower() + '://' + parsed.netloc.lower() != scope['origin']):
                raise CleanupScopeError('清理 API 不能超出能力的目标 origin')
            if not parsed.netloc and not method['entry'].startswith('/'):
                raise ValueError('清理 API 使用已有契约中的绝对路径或同源 URL')
    old = caps.get(values.get('capability_id'))
    if old and (old['owner'] != node['owner'] or old['task_id'] != node['task_id'] or not _same_scope(old, scope, CAP_SCOPE)):
        raise Conflict('能力 ID 的有效 scope 不可替换；不同 scope 使用独立能力')
    previous = old or next((c for c in caps.values() if c['owner'] == node['owner']
        and c['task_id'] == node['task_id'] and _same_scope(c, scope, CAP_SCOPE)), None)
    if (previous and previous['state'] == 'available' and previous['methods'] == methods
            and not spec.get('revalidation_evidence_ref')):
        return {'capability': copy.deepcopy(previous), 'reused': True, 'business_action_performed': False}
    if previous and (previous['state'] != 'available' or 'needs_verification' in previous.get('method_states', [])):
        text(spec.get('revalidation_evidence_ref'), '失败后本 scope 的重新核实依据', 2000)
    cid = previous['id'] if previous else values.get('capability_id') or uid()
    history = copy.deepcopy(previous.get('history', [])) if previous else []
    if previous:
        history.append({key: copy.deepcopy(previous[key]) for key in
                        ('revision', 'state', 'methods', 'evidence_ref', 'verified_at')})
    caps[cid] = {**scope, 'id': cid, 'owner': node['owner'], 'task_id': node['task_id'],
        'account_id': spec['account_id'], 'methods': copy.deepcopy(methods), 'evidence_ref': evidence,
        'state': 'available', 'method_states': ['available'] * len(methods),
        'verified_at': now, 'revision': previous['revision'] + 1 if previous else 1,
        'history': history, 'revalidation_evidence_ref': spec.get('revalidation_evidence_ref', ''),
        'verification_resource_context': _resource_context(lease, spec['account_id'])}
    return {'capability': copy.deepcopy(caps[cid]), 'business_action_performed': False}


def apply(state, lease, node, values, now):
    validate_cleanup_events(values)
    command = values.get('command')
    if lease['node_id'] != node['id'] or not lease.get('native_browser'):
        raise CleanupScopeError('Cleanup must use the original module lease')
    if command == 'capability':
        return _capability(state, lease, node, values, now)
    caps = state.setdefault('cleanup_capabilities', {})
    objects = state.setdefault('cleanup_objects', {})
    if command == 'register':
        spec = values.get('object') or {}
        _case_scope(state, node, spec.get('case_id'), spec.get('checkpoint_id', ''))
        for key in ('object_id', 'creation_evidence_ref'):
            text(spec.get(key), key, 2000)
        cap = caps.get(spec.get('capability_id'))
        account_id = spec.get('account_id') or (cap or {}).get('account_id')
        scope = _scope(state, lease, node, account_id, {**(cap or {}), **spec})
        if spec.get('ownership') != 'created_this_round':
            raise CleanupScopeError('仅登记本轮创建且有真实创建依据的对象，不认领既有或归属不明数据')
        if spec.get('kind') not in {'test_data', 'file', 'shared_configuration', 'business_scene'}:
            raise ValueError('明确对象 kind：test_data/file/shared_configuration/business_scene')
        if (not isinstance(spec.get('defect_case_ids', []), list)
                or any(not isinstance(cid, str) or not cid for cid in spec.get('defect_case_ids', []))):
            raise ValueError('defect_case_ids 必须为真实缺陷用例 ID 数组')
        obj = {**scope, 'object_id': spec['object_id'], 'account_id': account_id,
            'owner': node['owner'], 'task_id': node['task_id'], 'source_node_id': node['id'],
            'lease_id': lease['id'], 'creation_lease_id': lease['id'], 'case_id': spec['case_id'],
            'checkpoint_id': spec.get('checkpoint_id', ''), 'creation_evidence_ref': spec['creation_evidence_ref'],
            'ownership': 'created_this_round', 'kind': spec['kind'],
            'defect_case_ids': copy.deepcopy(spec.get('defect_case_ids', [])),
            'retention_evidence_ref': spec.get('retention_evidence_ref', ''),
            'retain_scene': spec.get('retain_scene') is True}
        previous = objects.get(values.get('responsibility_id'))
        duplicate = next((o for o in objects.values() if o['owner'] == node['owner']
            and o['task_id'] == node['task_id'] and _same_scope(o, obj, OBJECT_SCOPE)), None)
        if previous or duplicate:
            previous = previous or duplicate
            if (not _same(previous, obj, (*OBJECT_SCOPE, 'account_id', 'source_node_id'))
                    or previous['owner'] != node['owner'] or previous['task_id'] != node['task_id']):
                raise Conflict('对象身份已登记给其他责任范围，不覆盖消费者或原未知事实')
            return {'responsibility': copy.deepcopy(previous), 'reused': True, 'business_action_performed': False}
        obj['locks'] = _node_locks(node)
        obj['creation_resource_context'] = _resource_context(lease, account_id)
        authority = _authority(state, node)
        retention = _retention(authority, obj)
        if cap and (cap['owner'] != node['owner'] or cap['task_id'] != node['task_id'] or not _same_scope(cap, scope, SCOPE)):
            raise CleanupScopeError('清理能力不适用于该对象的授权 scope')
        residual = spec.get('residual')
        if residual is not None:
            if not isinstance(residual, dict):
                raise ValueError('实际遗留必须包含准确原因和原观察')
            observation = residual.get('observation') or {}
            _observation(obj, observation)
            obj.update(residual_reason=text(residual.get('reason'), '遗留原因', 4000),
                       last_observation=copy.deepcopy(observation), observed_at=now)
        if not retention and not residual and (not cap or cap['state'] != 'available'):
            raise Conflict('登记清理能力、已有保留授权或准确遗留；不伪造已清理')
        if not retention and not residual:
            _cleanup_allowed(authority, obj)
        consumers = spec.get('consumers', [])
        if not isinstance(consumers, list):
            raise ValueError('消费者必须为结构化引用数组')
        obj.update(id=values.get('responsibility_id') or uid(),
                   state='retained' if retention else 'residual' if residual else 'present',
                   consumers=[], created_at=now, history=[])
        for value in consumers:
            consumer = _consumer(state, value, node)
            if consumer not in obj['consumers']:
                obj['consumers'].append(consumer)
        if cap:
            obj.update(capability_id=cap['id'], capability_scope={k: cap[k] for k in CAP_SCOPE})
        if retention:
            obj['retention_basis'] = retention
        objects[obj['id']] = obj
        return {'responsibility': copy.deepcopy(obj), 'business_action_performed': False}
    obj = objects.get(values.get('responsibility_id'))
    if not obj or obj['owner'] != node['owner'] or obj['task_id'] != node['task_id']:
        raise CleanupScopeError('对象责任不属于当前授权轮次')
    dependency = command in {'acquire_dependency', 'release_dependency'}
    continued = obj['source_node_id'] in continuation_sources(state, node)
    if not dependency:
        _account(state, lease, node, obj['account_id'], obj)
        if obj['source_node_id'] != node['id'] and not continued:
            raise CleanupScopeError('清理仅属于原模块或明确获授此对象责任的接续委托')
        if not continued:
            _case_scope(state, node, obj['case_id'], obj.get('checkpoint_id', ''))
    if dependency:
        consumer = _consumer(state, values.get('consumer'), node)
        if obj['state'] in UNCERTAIN | {'cleaned'}:
            raise Conflict('对象清理中、已清理或状态未知，不能变更消费者')
        if command == 'acquire_dependency' and consumer not in obj['consumers']:
            obj['consumers'].append(consumer)
        elif command == 'release_dependency':
            obj['consumers'] = [c for c in obj['consumers'] if c != consumer]
    elif command == 'prepare_cleanup':
        if obj['state'] == 'cleaning' and obj.get('cleanup_lease_id') == lease['id']:
            return {'responsibility': copy.deepcopy(obj), 'business_action_performed': False}
        if obj['consumers'] or obj['state'] not in {'present', 'residual', 'retained'} or obj.get('retain_scene'):
            raise Conflict('仍有消费者、未核实操作或真实保留现场，不得删除')
        source = state['nodes'][obj['source_node_id']]
        authorization = _cleanup_allowed(_authority(state, source), obj)
        cap = caps.get(values.get('capability_id') or obj.get('capability_id'))
        method_index = values.get('method_index', 0)
        if (not cap or cap['owner'] != node['owner'] or cap['task_id'] != node['task_id']
                or not _same_scope(cap, obj, SCOPE) or cap['state'] != 'available'
                or type(method_index) is not int or not 0 <= method_index < len(cap['methods'])
                or cap.get('method_states', ['available'] * len(cap['methods']))[method_index] != 'available'):
            raise Conflict('清理能力未核实或 scope 不匹配；不重复已失败入口')
        obj.update(state='cleaning', cleanup_attempt_id=uid(), cleanup_lease_id=lease['id'],
            capability_id=cap['id'], capability_scope={k: cap[k] for k in CAP_SCOPE},
            cleanup_capability_revision=cap['revision'], cleanup_method_index=method_index,
            cleanup_method=copy.deepcopy(cap['methods'][method_index]),
            cleanup_authorization=authorization, cleanup_started_at=now, lease_id=lease['id'],
            locks=list(dict.fromkeys([*obj.get('locks', []), *_node_locks(node)])),
            cleanup_resource_context=_resource_context(lease, obj['account_id']))
    elif command == 'reconcile' and values.get('scene_only') is True:
        from .resource_scheduler import pending_operations
        if obj['state'] not in {'present', 'residual', 'retained', 'cleaned'}:
            raise Conflict('现场核实不能清除未知或在途业务结果')
        observation = values.get('observation') or {}
        _observation(obj, observation)
        if (observation.get('scene_release_verified') is not True
                or not observation.get('scene_release_evidence_ref')
                or pending_operations(state, lease['id'])):
            raise Conflict('缺少原现场解除证据或仍有未知/在途业务操作')
        obj.update(retain_scene=False, scene_release_evidence_ref=observation['scene_release_evidence_ref'],
                   scene_observation=copy.deepcopy(observation), scene_observed_at=now)
    elif command in {'complete_cleanup', 'reconcile'}:
        if (not obj.get('cleanup_attempt_id') or obj['cleanup_attempt_id'] != values.get('cleanup_attempt_id')
                or (obj.get('cleanup_lease_id') != lease['id'] and not continued)):
            raise Conflict('观察不属于原清理尝试；接续者必须有该对象的明确核实授权')
        if obj['state'] in {'cleaned', 'residual'} and obj.get('last_observation') == values.get('observation'):
            return {'responsibility': copy.deepcopy(obj), 'reused': True, 'business_action_performed': False}
        if command == 'complete_cleanup' and obj['state'] != 'cleaning':
            raise Conflict('原清理已结算或未知；未知仅可核实原尝试，不重发清理')
        if command == 'reconcile' and obj['state'] not in {'unknown', 'cleaning'}:
            raise Conflict('该对象没有待核实的原清理尝试')
        observation = values.get('observation') or {}
        classification = _observation(obj, observation)
        if command == 'reconcile' and observation.get('original_operation_resolved') is not True:
            raise Conflict('核实必须针对原操作结果，不能用新探路或保留设置消除未知')
        target_state = _result_state(classification, observation)
        obj.update(last_observation=copy.deepcopy(observation), classification=classification,
                   state=target_state, observed_at=now)
        if observation.get('scene_release_verified') is True and observation.get('scene_release_evidence_ref') and target_state != 'unknown':
            obj.update(retain_scene=False, scene_release_evidence_ref=observation['scene_release_evidence_ref'])
        cap = caps.get(obj.get('capability_id'))
        if (cap and cap['revision'] == obj.get('cleanup_capability_revision') and classification in
                {'proxy_rejected', 'route_or_permission_unknown', 'method_unsupported', 'permission_denied'}):
            method_states = cap.setdefault('method_states', ['available'] * len(cap['methods']))
            method_states[obj['cleanup_method_index']] = 'needs_verification'
            cap.update(state='available' if 'available' in method_states else 'needs_verification',
                       failure=classification, failure_at=now,
                       failure_evidence_ref=observation['evidence_ref'])
    elif command == 'residual':
        if obj['state'] not in {'present', 'residual', 'retained'}:
            raise Conflict('未知/在途操作不能登记为已知遗留，先核实原尝试')
        observation = values.get('observation') or {}
        _observation(obj, observation)
        obj.update(state='residual', residual_reason=text(values.get('reason'), '遗留原因', 4000),
                   last_observation=copy.deepcopy(observation), observed_at=now)
    elif command == 'retain':
        if obj['state'] not in {'present', 'residual', 'retained'}:
            raise Conflict('保留授权不能消除未知、在途或已完成事实')
        retention = _retention(_authority(state, state['nodes'][obj['source_node_id']]), obj)
        if not retention:
            raise CleanupScopeError('原本轮持久化设置或已有明确授权未允许保留此对象')
        if values.get('retain_scene') is True:
            if obj.get('retain_scene') and obj['lease_id'] != lease['id']:
                raise Conflict('原物理现场仍受保护，不能仅凭另一持有者声明转移现场')
            obj.update(lease_id=lease['id'],
                locks=list(dict.fromkeys([*obj.get('locks', []), *_node_locks(node)])),
                retained_resource_context=_resource_context(lease, obj['account_id']))
        obj.update(state='retained', retention_basis=retention,
                   retain_scene=obj.get('retain_scene', False) or values.get('retain_scene') is True)
    else:
        raise ValueError('未知对象责任操作')
    history_context = (obj.get('cleanup_resource_context')
        if command in {'prepare_cleanup', 'complete_cleanup'} or command == 'reconcile' and not values.get('scene_only')
        else obj.get('retained_resource_context') or obj.get('creation_resource_context'))
    obj.setdefault('history', []).append({'command': command, 'lease_id': lease['id'], 'at': now,
        'state': obj['state'], 'cleanup_attempt_id': obj.get('cleanup_attempt_id'),
        'capability_revision': obj.get('cleanup_capability_revision'),
        'resource_context': copy.deepcopy(history_context),
        'observation': copy.deepcopy(values.get('observation'))})
    return {'responsibility': copy.deepcopy(obj), 'business_action_performed': False}


def continuation_sources(state, node):
    sources, current = set(), node
    while current.get('continuation_source'):
        previous = state['nodes'].get(current['continuation_source']['source_node_id'])
        if (not previous or previous['id'] in sources or previous['owner'] != node['owner']
                or previous['task_id'] != node['task_id']
                or previous.get('record_project_id') != node.get('record_project_id')
                or previous.get('record_execution_id') != node.get('record_execution_id')):
            break
        sources.add(previous['id'])
        current = previous
    return sources


def blockers(state, lease, *, replacing=False):
    return [obj['id'] for obj in state.get('cleanup_objects', {}).values()
            if obj['lease_id'] == lease['id'] and
            (obj['state'] in UNCERTAIN or obj.get('retain_scene') or
             not replacing and obj['state'] not in {'cleaned', 'retained', 'residual'})]


def reconcile_saved_observations(controller, db, state, lease):
    """Correct a derived unknown from authenticated stored facts, never observe anew."""
    node = state['nodes'][lease['node_id']]
    changed = False
    for obj in state.get('cleanup_objects', {}).values():
        if (obj.get('state') != 'unknown' or obj.get('lease_id') != lease['id']
                or obj.get('cleanup_lease_id') != lease['id']
                or obj.get('owner') != node['owner'] or obj.get('task_id') != node['task_id']
                or obj.get('source_node_id') not in {node['id']} | continuation_sources(state, node)):
            continue
        observation = obj.get('last_observation') or {}
        history = obj.get('history') or []
        original = history[-1] if history else {}
        if (original.get('command') not in {'complete_cleanup', 'reconcile'}
                or not obj.get('cleanup_attempt_id')
                or original.get('cleanup_attempt_id') != obj['cleanup_attempt_id']
                or original.get('lease_id') != lease['id']
                or original.get('observation') != observation
                or original.get('at') != obj.get('observed_at')
                or not obj.get('cleanup_resource_context')
                or original.get('resource_context') != obj['cleanup_resource_context']
                or original['resource_context'].get('lease_id') != lease['id']
                or observation.get('original_operation_resolved') is not True
                or type(observation.get('business_completed')) is not bool):
            continue
        try:
            _account(state, lease, node, obj['account_id'], obj)
            classification = _observation(obj, observation)
        except (ValueError, PermissionError, Conflict):
            continue
        target = _result_state(classification, observation)
        previous = obj.get('classification')
        obj.update(state=target, classification=classification)
        changed = True
        if observation.get('scene_release_verified') is True and observation.get('scene_release_evidence_ref'):
            obj.update(retain_scene=False, scene_release_evidence_ref=observation['scene_release_evidence_ref'])
        controller.audit(db, node['owner'], 'cleanup.observation_reclassified', obj['id'],
            'Original attempt %s / lease %s / observation %s: unknown (%s) -> %s; '
            'stored executor completion facts supersede description classification' % (
                obj['cleanup_attempt_id'], lease['id'], original['at'], previous, target))
    if changed:
        settle_units(state, node, controller.clock())


def owns_plan_responsibility(state, node, obj, sources=None):
    """Creation and cleanup may be different cases in the same original record."""
    sources = {node['id']} | continuation_sources(state, node) if sources is None else sources
    if (not obj or obj['owner'] != node['owner'] or obj['task_id'] != node['task_id']
            or obj['source_node_id'] not in sources):
        return False
    source = state['nodes'].get(obj['source_node_id'], {})
    return all(node.get(key) and node[key] == source.get(key)
               for key in ('record_project_id', 'record_execution_id'))


def settle_units(state, node, now):
    """Resolve only named cleanup responsibilities, never assertion outcomes."""
    from .execution_work_plan import _digest
    sources = {node['id']} | continuation_sources(state, node)
    for unit in node.get('checkpoint', {}).get('work_plan', {}).get('units', []):
        ids = unit.get('cleanup_responsibility_ids', [])
        objects = [state.get('cleanup_objects', {}).get(key) for key in ids]
        if unit.get('purpose') == 'cleanup' and ids and all(owns_plan_responsibility(state, node, obj, sources)
                and obj['state'] in {'cleaned', 'retained', 'residual'} and not obj.get('consumers')
                and not obj.get('retain_scene') for obj in objects):
            node.setdefault('work_unit_receipts', {})[unit['id']] = {
                'unit_digest': _digest(unit), 'completed': True, 'at': now,
                'responsibility_ids': ids}
        elif unit.get('purpose') == 'cleanup':
            previous = node.get('work_unit_receipts', {}).get(unit['id'])
            if previous and previous.get('completed'):
                previous.update(completed=False, invalidated_at=now)
