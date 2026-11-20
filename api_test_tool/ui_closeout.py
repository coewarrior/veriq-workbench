"""Mechanical preparation/evidence packaging on the existing UI record path.

No model calls, browser actions or inferred business outcomes.
"""
import base64
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone

from .execution import Redactor
from .orchestration_storage import read_record


def result_template(cases):
    result = []
    for case in cases:
        item = {'case_id': case['case_id']}
        if case.get('checkpoints'):
            item['checkpoint_updates'] = [
                {'id': p['id']}
                for p in case['checkpoints']]
        result.append(item)
    return {'cases': result, 'evidence_refs': []}


def receipt_assets(service, owner, pid, refs):
    if not isinstance(refs, list) or len(refs) > 200:
        raise ValueError('evidence_refs 为最多 200 项的已有回执引用')
    if not refs:
        return []
    nodes = {n['id'] for n in service.controller.snapshot(owner)['nodes']
             if (n.get('record_project_id') or n['project_id']) == pid}
    assets, seen = [], set()
    with service.controller.connect() as db:
        db.execute('BEGIN')
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) - {'case_id', 'lease_id', 'request_id', 'step'}:
                raise ValueError('evidence_refs 使用 case_id、lease_id、request_id 和可选 step')
            if any(not isinstance(ref.get(k), str) or not ref[k] or len(ref[k]) > 160
                   for k in ('case_id', 'lease_id', 'request_id')):
                raise ValueError('证据引用需有本轮用例 ID、租约 ID 和原操作 request_id')
            key = ref['lease_id'] + ':' + ref['request_id']
            cmd = read_record(db, 'direct_commands', key)
            if not cmd or cmd.get('owner') != owner or cmd.get('node_id') not in nodes:
                raise PermissionError('证据回执不属于本轮任务')
            if cmd['state'] in {'queued', 'running'} or 'result' not in cmd:
                raise ValueError('原操作尚未返回回执，不能当作已取得的证据；不重发业务')
            step = ref.get('step', '')
            if not isinstance(step, str) or len(step) > 300:
                raise ValueError('证据 step 必须是最多 300 字符的文本')
            identity = (ref['case_id'], key, step)
            if identity in seen:
                continue
            seen.add(identity)

            def without_images(value):
                if isinstance(value, dict):
                    return {k: without_images(v) for k, v in value.items() if k != '_image_url'}
                if isinstance(value, list):
                    return [without_images(v) for v in value]
                return value

            content = Redactor().snapshot({
                'source': 'direct_test_session', 'request_id': cmd['id'],
                'state': cmd['state'], 'browser_action': cmd.get('browser_action'),
                'created': cmd['created'], 'completed': cmd.get('completed'),
                'result': without_images(cmd['result']),
                'note': '原操作回执，不代表业务通过；截图沿原截图证据入口保存。'})
            captured = (datetime.fromtimestamp(cmd['completed'], timezone.utc).isoformat()
                        if cmd.get('completed') is not None else '')
            assets.append({'case_id': ref['case_id'], 'step': step,
                'filename': 'receipt-' + hashlib.sha256(key.encode()).hexdigest()[:24] + '.json',
                'content_type': 'application/json', 'kind': 'observation', 'captured_at': captured,
                'content_base64': base64.b64encode(json.dumps(content, ensure_ascii=False).encode()).decode()})
    return assets


def summary(record):
    from .ui_records import LABELS, active_cases
    record = {**record, 'cases': active_cases(record['cases'])}
    counts = Counter(c['status'] for c in record['cases'])
    lines = ['本轮共 %s 条：%s。' % (len(record['cases']), '，'.join(
        f'{LABELS.get(k, k)} {v}' for k, v in counts.items()))]
    # Observations already live beside their cases/checkpoints. Copying them
    # here duplicates raw DOM, tool errors and superseded intermediate findings.
    unfinished = sum(point['status'] not in {'passed', 'failed'}
                     for case in record['cases'] for point in case.get('checkpoints', []))
    if unfinished:
        lines.append(f'尚有 {unfinished} 个检查点未完成验证，具体原因见对应用例。')
    scene = record.get('scene_outcome') or {}
    remaining = sum(item.get('state') != 'cleaned' for item in scene.get('items', []))
    if remaining:
        lines.append(f'另有 {remaining} 个保留或未核实清理的现场对象，详见收尾记录。')
    return '\n'.join(lines)
