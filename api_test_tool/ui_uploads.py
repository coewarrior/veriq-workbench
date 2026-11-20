"""Store upload observations and provide non-blocking fallback guidance."""
from __future__ import annotations

import re

CHANNELS = ('file_input', 'native_dialog', 'playwright')
GUIDANCE = (
    'Chrome 扩展或当前浏览器工具不能读取本地文件，只说明该通道受限。'
    '先生成并核验测试文件。默认 native_browser 路线先使用当前 cua 已公开的原生上传能力，'
    '按工具文档修正实际参数或页面绑定；不能因一次调用失败擅自切到 Playwright、Runner 或其他后端。'
    '只有用户明确选择的旧兼容路线，才按原约定检查绑定标签的文件输入并优先回退到独立 Playwright；'
    '原生文件选择框仅在 browser-control.md 允许前台操作时使用，否则记录不可用依据。'
    '按工具公开能力操作，不盲发按键、不读取用户 Cookie。'
    '已有登录会话优先复用；独立上下文缺登录时使用本轮已有授权账号，'
    '确需用户登录或系统授权则用 pending_action/manual_step 写明具体动作。'
    '用 upload_attempts 保存实际尝试的 channel、outcome、detail；通道名与结果由执行者记录。'
    '同一条件可复用已核实的观察；缺口是否影响后续步骤由 Codex 判断，不要求遍历固定通道清单。'
    '不为填写记录新增浏览器、重复已知失败或虚构尝试。UI 上传不得用直接调用业务接口代替。'
)

_BROWSER = re.compile(r'Chrome|浏览器|扩展|browser|set_?input_?files|文件输入', re.I)
_LIMIT = re.compile(
    r'(?:不允许|不支持|不能|无法|禁止|拒绝|无权|没有权限).{0,24}(?:读取|访问|上传|选择|输入).{0,16}(?:本地)?文件'
    r'|(?:本地文件|文件输入).{0,24}(?:受限|不可用|禁止|拒绝|Not allowed|permission denied)'
    r'|(?:set_?input_?files|file.?input).{0,60}(?:Not allowed|permission denied|not supported)'
    r'|(?:cannot|unable to|not allowed to).{0,24}(?:read|access|upload).{0,16}(?:local )?files?', re.I)


def needs_fallback_checks(case):
    if case.get('status') not in {'blocked', 'not_run', 'partial', 'pending_action'}:
        return False
    # Inspect the stated result, never hypothetical limitations in the design.
    reason = '\n'.join(str(case.get(key, '')) for key in
                       ('actual', 'conclusion', 'not_run_reason', 'action_required'))
    return bool(_BROWSER.search(reason) and _LIMIT.search(reason))


def normalize(value):
    if not isinstance(value, list):
        raise ValueError('upload_attempts 必须为通道检查数组')
    result = []
    for attempt in value:
        if not isinstance(attempt, dict):
            raise ValueError('upload_attempts 每项必须为对象')
        channel, outcome, detail = (attempt.get(key) for key in ('channel', 'outcome', 'detail'))
        if any(not isinstance(item, str) for item in (channel, outcome, detail)):
            raise ValueError('上传检查 channel/outcome/detail 必须是文本')
        result.append({'channel': channel, 'outcome': outcome, 'detail': detail.strip()})
    return result


def missing_checks(case):
    if not needs_fallback_checks(case):
        return []
    if any(a.get('outcome') == 'succeeded' for a in case.get('upload_attempts', [])):
        return []
    checked = {a['channel'] for a in case.get('upload_attempts', [])}
    return [channel for channel in CHANNELS if channel not in checked]
