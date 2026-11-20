from api_test_tool.defect_triage import assess_defect


def test_authored_severity_and_independent_priority():
    result = assess_defect('文案不正确', severity='严重', priority='低')
    assert result['severity'] == 'high'
    assert result['priority'] == 'low'
    assert result['source'] == 'report'


def test_legacy_demo_levels_and_unknown_impact():
    assert assess_defect('示例', severity='演示 · 高')['severity'] == 'high'
    assert assess_defect('空密码仍可登录')['severity'] == 'high'
    assert assess_defect('未确定原因的响应差异')['severity'] == 'medium'
    assert '缺少已确认' in assess_defect('未确定原因的响应差异')['reason']
