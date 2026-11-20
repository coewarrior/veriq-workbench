"""Role-specific task material; routing is not a tool permission boundary."""
import copy
from pathlib import Path
from . import testing_policy, ui_design_references


ROOT = Path(__file__).parent / 'static/skills/web-exploratory-testing'


def resolve_role(project, role=''):
    if role in {'coordinator', 'worker', 'single'}:
        return role
    return 'worker' if project.get('managed_node_id') else 'single'


def role_skill(role):
    reference = 'coordinator.md' if role == 'coordinator' else 'worker.md'
    return {'role': role, 'source': 'platform_bundle', 'testing_policy': testing_policy.snapshot(),
            'path': '/static/skills/web-exploratory-testing/SKILL.md',
            'content': (ROOT / 'SKILL.md').read_text(),
            'role_reference': '/static/skills/web-exploratory-testing/references/' + reference,
            'role_guidance': (ROOT / 'references' / reference).read_text(),
            'tool_permissions_changed': False}


def worker_packet(task, node, project, design_references=None):
    """One leaf only. Preserve originals and explicit model settings verbatim."""
    binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
    material = {key: copy.deepcopy(value) for key, value in project.items()
                if key in {'task', 'title', 'ui_target_url', 'ui_requirement_attachments',
                    'ui_execution_permission', 'ui_scene_retention', 'regression_round',
                    'ui_retest_round', 'execution_round', 'model', 'thinking', 'reasoning_effort',
                    'model_config', 'codex_model', 'codex_reasoning_effort'}}
    assignment = {'task_id': task['id'], 'node_id': node['id'],
        'task_revision': task['revision'], 'node_revision': node['revision'],
        'holder_id': binding.get('holder_id'),
        'dispatch_id': binding.get('dispatch_id') or binding.get('id'),
        'executor_ref': binding.get('executor_ref'), 'coordinator_ref': binding.get('coordinator_ref'),
        'project_id': node.get('record_project_id') or task['project_id'],
        'source_project_id': task['project_id'], 'scope': copy.deepcopy(node.get('scope'))}
    assignment['account_project_id'] = task.get('account_project_id') or task['project_id']
    from .module_dispatch import browser_assignment, record_assignment
    assignment.update(browser_assignment(task, node))
    assignment.update(record_assignment(node))
    return {'role': 'worker', 'assignment': assignment, 'testing_policy': testing_policy.snapshot(),
        'module': {key: copy.deepcopy(node.get(key)) for key in
                   ('key', 'title', 'scope', 'depends_on', 'locks', 'requirements')},
        'task_material': material, 'design_references': copy.deepcopy(design_references or []),
        'design_reference_guidance': ui_design_references.GUIDANCE,
        'testing_skill': {key: value for key, value in role_skill('worker').items()
            if key in {'role', 'source', 'path', 'role_reference', 'tool_permissions_changed'}},
        'first_read': {'tool': 'get_test_document', 'arguments': {
            'project_id': task['project_id'], 'role': 'worker'}},
        'instruction': testing_policy.GUIDANCE + '你只负责此模块的探索、设计、执行、逐条保存及真实交还。'
            '业务结论、证据充分性和通过失败由你按真实观察判断，平台如实保存展示；显式提交父用例 status/actual/conclusion/ai_analysis，检查点更新不自动改判父用例。'
            '依赖台账和 gaps 仅供诊断，不改结果或阻断资源候选；原 work_unit.depends_on 保留前置阶段已完成 passed/failed 的顺序，不要求业务通过。'
            '保留完整覆盖、持续探索和自查，不把自查变成平台保存发布门槛；真实身份、账号归属、CAS、退出和未知实际操作保护不变。'
            '领取前复用资料核对已知账号项目/目标和样本条件；登录后首次侦察即核实 UI 才能确认的共同前置，不等逐条执行到受阻。'
            '共同故障按实际条件和受影响用例关联：登录服务异常不能替代管理端角色、设备或样本缺口的依据。未操作的下游不伪写逐条失败；独立可执行分支继续。收到同轮明确恢复证据后复核对应原阻塞，沿正式续接完成剩余项，不把旧故障当永久结论、不自动重跑已完成动作。'
            '按随包 work-stages.md 保存实际用例与依赖并登记原用例资源阶段；depends_on 只连接必要检查点，不能把整批前序用例都通过当作独立阶段前提。'
            '多账号场景不测；测不了跳过不包括普通排队或尚未准备样本。独占等待先继续当前合法可做用例，安全边界用 yield，模块仍待执行；恢复通知由 native-resume 完整接入，不手抄阶段令牌。'
            '租约结束后的正式续接和清理按 execution-recovery.md；使用返回的新私有 run kit 沿原队列准备，不重用旧 lease 或跨模块委托。'
            '读取 first_read 的完整相关资料；assignment 合入原执行包，保留明确模型、权限、现场和范围。'
            '不创建或调度其他模块；收尾生成器机械通知原后继，无需你规划其他模块。'}
