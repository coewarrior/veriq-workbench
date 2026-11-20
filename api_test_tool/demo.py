"""Deterministic fault scenarios for the disposable full-flow experience."""
from copy import deepcopy


def experience_bundle(baseline):
    bundle = deepcopy(baseline)
    bundle['title'] = '【演示】完整流程体验：成功、缺陷与未执行场景'
    bundle.setdefault('web', {})['experience'] = True
    original = next(c for c in bundle['cases'] if c['id'] == 'ITEM-FLOW-001')

    def scenario(identifier, title):
        case = deepcopy(original)
        case.update(id=identifier, title='【演示】' + title)
        bundle['cases'].append(case)
        return case

    for fault, title in [('wrong_owner', '查询返回了错误的资源归属'),
                         ('wrong_type', '查询将数量返回为字符串'),
                         ('missing_field', '查询缺少必填的资源名称')]:
        case = scenario('DEMO-' + fault.upper(), title)
        next(s for s in case['steps'] if s['id'] == 'read')['request']['headers']['X-Demo-Fault'] = fault
    for state, title, reason in [
        ('NEEDS_RULE', '批量创建规则待确认', '演示项，无需补充：批量创建中有一条不合法时，应全部失败还是允许部分成功？示例文档未说明，因此跳过这条，其他可执行用例继续。'),
        ('QUARANTINED', '批量删除场景已隔离', '演示隔离：批量删除可能影响其他资源，本体验不执行破坏性操作。'),
        ('UNSUPPORTED', '实时资源推送暂不支持', '演示能力边界：当前 HTTP 执行器不支持 WebSocket，未建立连接。'),
    ]:
        case = scenario('DEMO-' + state, title)
        case.update(state=state, reason=reason, steps=[], cleanup_steps=[], variables={}, rule_ids=[])
    case = scenario('DEMO-SERVICE-ERROR', '查询时连接中断，产生执行异常')
    next(s for s in case['steps'] if s['id'] == 'read')['request']['headers']['X-Demo-Fault'] = 'disconnect'
    scenario('DEMO-AFTER-ERROR', '其他用例异常后，独立流程仍可完成')
    return bundle
