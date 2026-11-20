"""C02 bookkeeping inside the original fixture transaction, without business calls."""
from copy import deepcopy
from .orchestration import Conflict, text, uid


def apply_fixture(controller, db, state, owner, node, data):
    fid = data.get('id') or uid()
    fixture = state['fixtures'].get(fid)
    action = data.get('action', 'acquire')
    if not fixture:
        if action != 'acquire':
            raise ValueError('共享前置尚未登记，不能结束或清理不存在的记录')
        fixture = {'id': fid, 'owner': owner, 'project_id': node['project_id'],
            'task_id': node['task_id'], 'created_by_node_id': node['id'],
            'cleanup_owner_node_id': node['id'], 'object_id': text(data.get('object_id'), 'object_id'),
            'version': text(data.get('version'), 'version'), 'state': 'available',
            'business_state': str(data.get('business_state', '')),
            'environment': str(data.get('environment', '')),
            'account_id': str(data.get('account_id', '')),
            'consumers': [], 'consumer_requirements': {},
            'cleanup_authorized': bool(data.get('cleanup_authorized', False)),
            'cleanup_authorization': str(data.get('cleanup_authorization', '')),
            'history': []}
        state['fixtures'][fid] = fixture
    if fixture['owner'] != owner or fixture['project_id'] != node['project_id']:
        raise PermissionError('共享前置不属于当前项目')
    if data.get('object_id') and data['object_id'] != fixture['object_id']:
        raise Conflict('共享前置身份不同，不能用同一记录替换业务对象')
    if action == 'acquire':
        if fixture['state'] != 'available' or fixture['version'] != data.get('version'):
            raise Conflict('前置已进入清理或状态版本不兼容')
        required = str(data.get('required_state', fixture.get('business_state', '')))
        if required and fixture.get('business_state') and required != fixture['business_state']:
            raise Conflict('消费者要求的业务状态与前置不兼容，保留各自真实条件')
        if node['id'] not in fixture['consumers']:
            fixture['consumers'].append(node['id'])
        fixture.setdefault('consumer_requirements', {})[node['id']] = {
            'state': required, 'version': data['version'], 'registered_at': controller.clock()}
    elif action == 'release':
        if node['id'] in fixture['consumers']:
            fixture['consumers'].remove(node['id'])
        fixture.setdefault('consumer_requirements', {}).pop(node['id'], None)
    elif action == 'transfer':
        target = controller.owned(state['nodes'], owner, data.get('cleanup_owner_node_id'))
        if target['project_id'] != node['project_id']:
            raise PermissionError('收尾责任只能移交给同一会话内的任务')
        fixture['cleanup_owner_node_id'] = target['id']
    elif action == 'prepare_cleanup':
        if fixture['state'] == 'cleaning' and fixture.get('cleanup_owner_node_id') == node['id']:
            return deepcopy(fixture)
        if fixture['consumers']:
            raise Conflict('仍有消费者依赖此对象，不能开始清理')
        if fixture.get('cleanup_owner_node_id', fixture.get('created_by_node_id')) != node['id']:
            raise PermissionError('清理由已登记的收尾负责人处理')
        if not fixture.get('cleanup_authorized'):
            raise Conflict('原任务未记录此对象的收尾授权；保留待办，不自行扩权')
        evidence = text(data.get('evidence'), '在途操作与现场保留核实依据')
        fixture.update(state='cleaning', cleanup_started_at=controller.clock(), cleanup_evidence=evidence)
    elif action == 'complete_cleanup':
        if fixture.get('cleanup_owner_node_id') != node['id'] or fixture['state'] not in {'cleaning', 'cleaned'}:
            raise Conflict('仅原收尾负责人可提交已开始清理的实际结果')
        evidence = text(data.get('evidence'), '实际收尾结果依据')
        succeeded = data.get('succeeded') is True
        fixture.update(state='cleaned' if succeeded else 'available', cleanup_evidence=evidence,
                       cleanup_completed_at=controller.clock() if succeeded else None,
                       cleanup_error='' if succeeded else evidence)
    else:
        raise ValueError('共享前置动作仅支持 acquire/release/transfer/prepare_cleanup/complete_cleanup')
    fixture['cleanup_ready'] = not fixture['consumers'] and fixture['state'] == 'available' and bool(fixture.get('cleanup_authorized'))
    fixture['cleanup_pending'] = not fixture['consumers'] and fixture['state'] != 'cleaned'
    fixture.setdefault('history', []).append({'action': action, 'node_id': node['id'], 'at': controller.clock(),
        'state': fixture['state'], 'consumer_count': len(fixture['consumers'])})
    controller.audit(db, owner, 'fixture.' + action, fid)
    return deepcopy(fixture)
