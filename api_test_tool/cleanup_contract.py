"""Pure cleanup event validation, shared with the exported native client.

Only shapes and explicit values are checked here. Account authority, object
ownership, user permission and state transitions remain server decisions.
"""
from urllib.parse import urlsplit


COMMANDS = {'capability', 'register', 'acquire_dependency', 'release_dependency',
            'prepare_cleanup', 'complete_cleanup', 'reconcile', 'residual', 'retain'}


class CleanupValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('清理事件格式错误：' + '; '.join(
            item['path'] + ' ' + item['message'] for item in errors))


class CleanupScopeError(PermissionError):
    """Only fixed safe cleanup reasons may be exposed over HTTP."""


def validate_cleanup_events(values):
    """Validate one event or an events envelope; return the original event list.

    Never resolves identifiers, mutates arguments, or performs I/O. Errors carry
    paths and fixed guidance, never input values, credentials or object details.
    """
    errors = []

    def fail(path, message):
        errors.append({'path': path, 'message': message})

    def obj(value, path):
        if not isinstance(value, dict):
            fail(path, '必须为对象')
            return None
        return value

    def string(value, key, path, *, required=True, blank=False, limit=2000):
        if key not in value and not required:
            return
        item = value.get(key)
        if not isinstance(item, str) or (not blank and not item.strip()) or len(item) > limit:
            fail(path + '.' + key, '必须为' + ('可空' if blank else '非空') + f'字符串，最多 {limit} 字符')

    def boolean(value, key, path):
        if key in value and type(value[key]) is not bool:
            fail(path + '.' + key, '必须为布尔值')

    def scoped(value, path, *, object_identity=False):
        if 'scope' in value:
            fail(path + '.scope', 'scope 字段直接放在 capability/object 内，不嵌套 scope')
        for key in ('origin', 'environment', 'tenant', 'role'):
            string(value, key, path, required=object_identity and key != 'role', blank=key != 'origin')
        if value.get('origin') and isinstance(value['origin'], str):
            try:
                parsed = urlsplit(value['origin'])
                valid = (parsed.scheme in {'http', 'https'} and parsed.hostname
                         and not parsed.username and not parsed.password and parsed.path in {'', '/'}
                         and not parsed.query and not parsed.fragment)
                parsed.port
            except ValueError:
                valid = False
            if not valid:
                fail(path + '.origin', '必须为无凭据、路径或查询参数的 HTTP origin')
        if object_identity:
            for key in ('object_type', 'object_id', 'account_id'):
                string(value, key, path)

    def consumer(value, path):
        if obj(value, path) is None:
            return
        for key in ('source_node_id', 'case_id'):
            string(value, key, path)
        for key in ('checkpoint_id', 'work_unit_id'):
            string(value, key, path, required=False, blank=True)

    def observation(value, path):
        if obj(value, path) is None:
            return
        string(value, 'evidence_ref', path)
        if obj(value.get('object_scope'), path + '.object_scope') is not None:
            scoped(value['object_scope'], path + '.object_scope', object_identity=True)
        if 'status' in value and value['status'] is not None and type(value['status']) is not int:
            fail(path + '.status', '必须为 HTTP 状态整数或 null')
        for key in ('business_completed', 'object_identity_verified', 'principal_verified',
                    'original_operation_resolved', 'scene_release_verified'):
            boolean(value, key, path)
        for key in ('effect_state', 'object_state', 'absence_contract_ref', 'scene_release_evidence_ref'):
            string(value, key, path, required=False, blank=True)

    if obj(values, 'arguments') is None:
        raise CleanupValidationError(errors)
    events = values.get('events', [values])
    if not isinstance(events, list) or not 1 <= len(events) <= 100:
        fail('events', '必须为 1–100 个已有证据事件的数组')
        raise CleanupValidationError(errors)
    for index, event in enumerate(events):
        path = f'events[{index}]'
        if obj(event, path) is None:
            continue
        command = event.get('command')
        if not isinstance(command, str) or command not in COMMANDS:
            fail(path + '.command', '使用 command 指定 capability/register/acquire_dependency/release_dependency/prepare_cleanup/complete_cleanup/reconcile/residual/retain')
            continue
        if 'action' in event:
            fail(path + '.action', '事件使用 command，不使用 action')
        for key in ('capability_id', 'responsibility_id', 'cleanup_attempt_id'):
            string(event, key, path, required=False)
        for key in ('scene_only', 'retain_scene'):
            boolean(event, key, path)
        if command in {'capability', 'register'}:
            name = 'capability' if command == 'capability' else 'object'
            spec = obj(event.get(name), path + '.' + name)
            if spec is None:
                continue
            sp = path + '.' + name
            scoped(spec, sp)
            for key in ('account_id', 'object_type'):
                string(spec, key, sp, required=command == 'capability' or not spec.get('capability_id'))
            if command == 'capability':
                for key in ('entry_source', 'evidence_ref'):
                    string(spec, key, sp)
                string(spec, 'revalidation_evidence_ref', sp, required=False, blank=True)
                methods = spec.get('methods')
                if not isinstance(methods, list) or not methods:
                    fail(sp + '.methods', '必须为有真实依据的方法数组')
                else:
                    for mi, method in enumerate(methods):
                        mp = sp + f'.methods[{mi}]'
                        if obj(method, mp) is None:
                            continue
                        if method.get('kind') not in ('ui', 'api'):
                            fail(mp + '.kind', '使用 kind: ui 或 api，不使用 method/channel 代替')
                        for key in ('entry', 'evidence_ref'):
                            string(method, key, mp)
            else:
                for key in ('case_id', 'object_id', 'creation_evidence_ref', 'ownership'):
                    string(spec, key, sp)
                string(spec, 'checkpoint_id', sp, required=False, blank=True)
                string(spec, 'capability_id', sp, required=False)
                string(spec, 'retention_evidence_ref', sp, required=False, blank=True)
                if spec.get('kind') not in ('test_data', 'file', 'shared_configuration', 'business_scene'):
                    fail(sp + '.kind', '使用 test_data/file/shared_configuration/business_scene')
                boolean(spec, 'retain_scene', sp)
                ids = spec.get('defect_case_ids', [])
                if not isinstance(ids, list) or any(not isinstance(cid, str) or not cid.strip() for cid in ids):
                    fail(sp + '.defect_case_ids', '必须为非空用例 ID 字符串数组')
                consumers = spec.get('consumers', [])
                if not isinstance(consumers, list):
                    fail(sp + '.consumers', '必须为消费者数组')
                else:
                    for ci, item in enumerate(consumers):
                        consumer(item, sp + f'.consumers[{ci}]')
                if spec.get('residual') is not None and obj(spec['residual'], sp + '.residual') is not None:
                    string(spec['residual'], 'reason', sp + '.residual', limit=4000)
                    observation(spec['residual'].get('observation'), sp + '.residual.observation')
        else:
            if 'responsibility_id' not in event:
                string(event, 'responsibility_id', path)
            if command in {'acquire_dependency', 'release_dependency'}:
                consumer(event.get('consumer'), path + '.consumer')
            if command == 'prepare_cleanup' and 'method_index' in event and (
                    type(event['method_index']) is not int or event['method_index'] < 0):
                fail(path + '.method_index', '必须为非负整数')
            if command in {'complete_cleanup', 'reconcile', 'residual'}:
                observation(event.get('observation'), path + '.observation')
            if command == 'complete_cleanup' or command == 'reconcile' and event.get('scene_only') is not True:
                if 'cleanup_attempt_id' not in event:
                    string(event, 'cleanup_attempt_id', path)
            if command == 'residual':
                string(event, 'reason', path, limit=4000)
    if errors:
        raise CleanupValidationError(errors)
    return events
