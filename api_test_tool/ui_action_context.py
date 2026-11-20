"""Durable, non-secret page references for a human step and its continuation."""
from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from .execution import Redactor, SECRET

FIELDS = ('page_url', 'page_title', 'browser', 'tab_id', 'step', 'object',
          'success_condition', 'resume_hint')
GUIDANCE = (
    '人工介入（扫码、登录等）前保存 action_context：page_url 为实际操作页的无凭据 HTTP(S) 链接，'
    'page_title、browser、tab_id 标识应保留的原标签，step 为暂停步骤，object 为原业务对象，'
    'success_condition 为完成判据，resume_hint 为返回原现场和继续路径。不要用首页代替操作页。'
    '不要关闭或清理仍用于待操作的标签、临时会话、订单和数据；只暂停依赖人工步骤的链路，独立用例继续。'
    '完成后优先绑定原标签并核对 URL、对象、账号与成功状态；标签失效才通过原链接恢复同一对象。'
    '扫码过期时在原页面刷新二维码，不重复创建订单或付款；不能把用户点击已完成直接记成测试通过。'
    '成功后从暂停检查点继续，保留前序观察及来源；无法恢复就如实更新待操作原因。'
    '链接不得包含密码、Cookie、授权码、Token 或签名；敏感临时链接只保留原标签引用及安全到达路径。'
    '旧记录缺现场时明确说明，不猜测 URL，不因未填新字段阻止旧报告保存或发布。'
)


def public_url(value):
    if not value:
        return ''
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password
                or any(ord(c) < 32 for c in value) or '<redacted>' in value or '\\' in value):
            return ''
        for name in re.findall(r'(?:^|[?&#;])([^=?&#;]+)=', unquote(value)):
            if SECRET.search(name) or re.search(r'^(?:code|sign|signature|ticket|auth)$', name, re.I):
                return ''
        return value
    except ValueError:
        return ''


def normalize(value):
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - set(FIELDS):
        raise ValueError('action_context 需为操作页面、原标签、暂停步骤及完成判据对象')
    result = {}
    for key, text in value.items():
        if not isinstance(text, str) or len(text) > 4000:
            raise ValueError('action_context.' + key + ' 必须是文本，最多 4000 字符')
        result[key] = text.strip()
    if result.get('page_url') and not public_url(result['page_url']):
        result['page_url'] = ''
        result['resume_hint'] = (result.get('resume_hint', '') + '\n操作链接含敏感信息或不可直接打开，请使用保留的原标签或安全到达路径。').strip()
    return Redactor().snapshot(result)
