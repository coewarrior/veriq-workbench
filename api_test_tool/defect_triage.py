"""Conservative, explainable defaults for reports without an authored triage."""
import re


def level(value, kind='severity'):
    text = str(value or '').lower().strip()
    groups = [
        ('critical', r'致命|阻断|紧急|最高|highest|critical|blocker|urgent|\bp0\b|\bs1\b'),
        ('high', r'严重|高|high|major|\bp1\b|\bs2\b'),
        ('medium', r'一般|普通|中|medium|normal|moderate|\bp2\b|\bs3\b'),
        ('low', r'轻微|低|建议|low|minor|trivial|\bp3\b|\bp4\b|\bs4\b'),
    ]
    for result, pattern in groups:
        if re.search(pattern, text):
            return result
    return None


def assess_defect(title, severity='', priority=''):
    """Authored levels win. Fallback only inspects the issue title, never request secrets."""
    impact = level(severity)
    reason = '采用报告中已给出的严重程度。' if impact else ''
    if not impact:
        for value, pattern, explanation in (
            ('critical', r'数据丢失|数据泄露|全站不可用|服务整体不可用', '描述涉及数据安全或整体服务不可用。'),
            ('high', r'越权|绕过.*(认证|鉴权)|空密码.*(登录成功|可登录)|无法登录|无法支付|重复扣款', '描述涉及安全控制或核心业务受阻。'),
            ('low', r'错别字|文案|样式|对齐|显示.*截断', '描述主要涉及展示问题。'),
        ):
            if re.search(pattern, title):
                impact, reason = value, explanation
                break
    if not impact:
        impact, reason = 'medium', '缺少已确认的影响范围，暂按一般功能问题评估。'
    urgency = level(priority, 'priority')
    reason += '优先级采用报告建议。' if urgency else '优先级按影响初评；上线时限、影响人数和可替代方案需审核时考虑。'
    return dict(severity=impact, priority=urgency or impact, reason=reason,
                source='report' if level(severity) or level(priority) else 'heuristic')
