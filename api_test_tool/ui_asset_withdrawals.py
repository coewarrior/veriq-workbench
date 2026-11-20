"""Audited delivery withdrawal; original evidence and case results stay immutable."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

from .orchestration import Conflict


def path(store, owner):
    return store._owner_dir(owner) / 'ui-asset-withdrawals.json'


def load(store, owner):
    location = path(store, owner)
    return store._read(location) if location.exists() else {'assets': {}, 'requests': {}}


def require_visible(store, owner, asset_id):
    if asset_id in load(store, owner)['assets']:
        from fastapi import HTTPException
        raise HTTPException(410, '该证据已撤下；原文件与操作审计保留')


def record_view(store, owner, record):
    withdrawn = load(store, owner)['assets']
    if not withdrawn:
        return record
    return {**record, 'assets': [a for a in record.get('assets', []) if a['id'] not in withdrawn]}


def report_view(store, owner, report):
    withdrawn = load(store, owner)['assets']
    if not withdrawn or not report.get('ui_snapshot'):
        return report
    result = deepcopy(report)
    result['ui_snapshot']['assets'] = [a for a in result['ui_snapshot'].get('assets', []) if a['id'] not in withdrawn]
    if 'fixture_supplements' in result:
        result['fixture_supplements'] = [a for a in result['fixture_supplements'] if a['id'] not in withdrawn]
    return result


def withdraw(store, owner, project_id, execution_id, asset_id, case_id, sha256,
             reason, request_id, *, actor):
    from . import ui_records
    for name, value, limit in [('reason', reason, 1000), ('request_id', request_id, 160), ('actor', actor, 300)]:
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f'{name} 必须是非空文本且不超过 {limit} 字符')
    fingerprint = hashlib.sha256(json.dumps([project_id, execution_id, asset_id, case_id, sha256, reason, actor],
                                            ensure_ascii=False).encode()).hexdigest()
    with store._lock:
        # Always authorize the exact project/execution/asset, even for a retry.
        record = ui_records.load(store, owner, project_id, execution_id)
        asset = next((a for a in record['assets'] if a['id'] == asset_id), None)
        if not asset or asset['case_id'] != case_id or asset['sha256'] != sha256:
            raise ValueError('证据的执行记录、用例或 SHA256 不匹配；未撤下')
        ledger = load(store, owner)
        previous = ledger['requests'].get(request_id)
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise Conflict('withdrawal_request_conflict: 同一 request_id 不能改变撤下参数')
            return previous['receipt']
        if asset_id not in ledger['assets']:
            ledger['assets'][asset_id] = {'project_id': project_id, 'execution_id': execution_id,
                'asset': deepcopy(asset), 'actor': actor, 'reason': reason, 'request_id': request_id,
                'withdrawn_at': datetime.now(timezone.utc).isoformat()}
        receipt = {'withdrawn': True, 'original_preserved': True,
                   'withdrawal': deepcopy(ledger['assets'][asset_id])}
        ledger['requests'][request_id] = {'fingerprint': fingerprint, 'receipt': receipt}
        store._write(path(store, owner), ledger)
        return receipt
