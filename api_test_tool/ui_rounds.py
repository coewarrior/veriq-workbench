"""Independent UI rounds and durable, cooperative leases for shared test resources."""
from __future__ import annotations

import copy
import hashlib
import re
import shutil
from uuid import UUID


GUIDANCE = ('模块协调统一见同源 /static/skills/web-exploratory-testing/references/coordinator.md；只在启动、首批设计、真实阻塞/资源事件、收尾四类节点介入。'
            '免安装客户端每次调用使用本聊天独立 --credential-file，避免覆盖其他聊天的连接。'
            '探索与回归使用各自 project_id、execution_id、revision 和专用本地目录，禁止把其他聊天的当前执行当作本轮。'
            '新回归/补测返回独立 project_id，后续所有读写、证据、进度及发布必须使用该 ID；报告仍汇总至原会话。'
            '新轮默认 native_browser：native-run-kit 自动生成独立浏览器环境入口，执行者创建后沿 direct_test_session 取得账号并直接操作 Playwright Page，无需用户配置；'
            '不重复 coordinate_ui_resources 占号、不逐动作轮询；未取得账号就结束当前回合并保留队列。'
            '以下 coordinate_ui_resources 规则仅用于显式旧外部浏览器任务：'
            '开始业务操作前 acquire 原子占用所需资源，holder_id 使用本聊天固定 UUID。'
            '资源 key 必须来自真实稳定身份：account:<目标origin>:<租户/账号ID>、tab:<主机>:<浏览器>:<标签ID>，'
            '使用原生点击、键盘或文件选择框时还需 native:<主机>；不含密码、令牌或随机轮次后缀。'
            '同一账号的准备、修改、读取断言和清理必须处于同一次占用内；不同账号/独立上下文可以并行。'
            '未获得全部资源时不操作、不标业务失败，继续无关设计或等待后重试；不能反复抢焦点。'
            '完成操作链和清理/保留核对后 release，异常先核对无操作在途再释放，不因超时自动抢占。'
            '保留现场不等于允许另一轮删除；只清理本轮创建且归属明确的数据和标签。'
            '此机制协调接入协议的执行器，无法拦截外部浏览器点击；已运行的旧聊天须先保存现场再读取新版约定。')


def create(store, owner, source, kind, *, execution_route=None, _before_create=None):
    """Copy input snapshots, never another round's results or current execution pointer."""
    from .ui_total_reports import canonical_project
    root = canonical_project(store, owner, source)
    label = {'regression': '回归', 'retest': '补测'}[kind]
    content = (store.project_dir(owner, source['id']) / source['document_file']).read_text()
    with store._lock:
        number = 1 + sum(p.get('execution_round', {}).get('parent_project_id') == root['id']
                         and p.get('execution_round', {}).get('kind') == kind for p in store.list_projects(owner))
        child = store.create_project(owner, f"{root['title'][:160]} · {label}第 {number} 轮", 'round.md', content,
                                     round_parent_id=root['id'], _before_create=_before_create)
        original = store.project_dir(owner, source['id'])
        destination = store.project_dir(owner, child['id'])
        try:
            for name in ('inputs', 'retest-files'):
                if (original / name).is_dir():
                    shutil.copytree(original / name, destination / name, dirs_exist_ok=True)
            for name in ('contract.json', 'requirement-design.json', 'test-capabilities.json', 'ui-retest-inputs.json'):
                if (original / name).is_file():
                    shutil.copyfile(original / name, destination / name)
            # create_project owns document_file; inputs may contain a historical
            # round.md, so write our exact selected snapshot after copying.
            store._write_text(destination / child['document_file'], content)
            updates = {key: copy.deepcopy(source[key]) for key in (
                'test_kind', 'ui_target_url', 'ui_execution_permission', 'ui_scene_retention',
                'ui_requirement_attachments', 'task', 'action_continuation') if key in source}
            if source.get('test_kind')=='ui':updates['execution_route']=execution_route or 'native_browser'
            for item in updates.get('ui_requirement_attachments', []):
                item['url'] = f'/api/ui-tests/{child["id"]}/attachments/{item["id"]}'
            updates.update(regression_source={'project_id': root['id']},
                           execution_round={'kind': kind, 'parent_project_id': root['id'],
                                            'source_project_id': source['id']})
            return store.update_project(owner, child['id'], updates)
        except Exception:
            shutil.rmtree(destination)
            raise


def discard(store, owner, child):
    """Only used to roll back a newly created, unpublished round."""
    shutil.rmtree(store.project_dir(owner, child['id']))


def related_access(store, owner, pid, allowed):
    if pid in allowed:
        return True
    project = store.get_project(owner, pid)
    return project.get('execution_round', {}).get('parent_project_id') in allowed


def coordinate(store, owner, pid, holder_id, operation, resources):
    """All-or-none acquisition; never steal resources on a timer or partial release."""
    store.get_project(owner, pid)
    try:
        UUID(holder_id)
    except (ValueError, TypeError, AttributeError):
        raise ValueError('holder_id 必须为本聊天固定 UUID') from None
    if operation not in {'acquire', 'release', 'status'}:
        raise ValueError('资源操作仅支持 acquire/release/status')
    if not isinstance(resources, list) or not resources or any(
            not isinstance(key, str) or not re.fullmatch(r'(account|tab|native):[^\r\n\x00]{1,1000}', key)
            for key in resources):
        raise ValueError('请提供真实 account/tab/native 资源标识，不得包含凭据')
    keys = sorted({hashlib.sha256(key.strip().encode()).hexdigest() for key in resources})
    path = store.root / 'ui-resource-leases.json'
    identity = {'owner': owner, 'project_id': pid, 'holder_id': holder_id}
    with store._lock:
        state = store._read(path) if path.exists() else {}
        conflicts = [key for key in keys if key in state and state[key] != identity]
        # No owner IDs or account identifiers are exposed to other users.
        if operation == 'acquire' and not conflicts:
            state.update({key: identity for key in keys})
            store._write(path, state)
        if operation == 'release':
            if conflicts:
                raise ValueError('不能释放其他任务占用的资源')
            for key in keys:
                state.pop(key, None)
            store._write(path, state)
        return {'acquired': operation != 'release' and all(state.get(key) == identity for key in keys),
                'released': operation == 'release', 'conflict_count': len(conflicts),
                'message': '资源由其他任务使用；等待或继续独立工作，不执行共享资源操作。' if conflicts else '资源协调已完成。'}
