"""Shared, pure preflight for existing UI payload shape rules. No business verdicts."""
def validate_ui_payload(payload):
    issues = []
    def issue(path, message):
        issues.append({'path': path, 'message': message})
    if not isinstance(payload, dict):
        return [{'path': '$', 'message': '保存内容必须是对象'}]
    coverage = payload.get('coverage')
    if coverage is not None:
        if not isinstance(coverage, list) or len(coverage) > 200:
            issue('coverage', 'coverage 每批最多 200 项，可分批追加')
        else:
            seen = set()
            for index, area in enumerate(coverage):
                prefix = f'coverage[{index}]'
                if not isinstance(area, dict):
                    issue(prefix, 'coverage 项必须是对象')
                    continue
                for key in ('coverage_id', 'feature', 'entry', 'considerations', 'gap'):
                    value = area.get(key, '')
                    if not isinstance(value, str) or len(value) > 20000:
                        issue(prefix + '.' + key, 'coverage 文本字段无效')
                    elif key in {'coverage_id', 'feature'} and not value.strip():
                        issue(prefix + '.' + key, '填写 coverage_id 与 feature，同批 ID 不得重复')
                cid = area.get('coverage_id')
                if isinstance(cid, str):
                    if cid.strip() in seen:
                        issue(prefix + '.coverage_id', '填写 coverage_id 与 feature，同批 ID 不得重复')
                    seen.add(cid.strip())
                ids = area.get('case_ids', [])
                if not isinstance(ids, list) or any(not isinstance(cid, str) or not cid.strip() or len(cid) > 20000 for cid in ids):
                    issue(prefix + '.case_ids', 'coverage.case_ids 必须为用例 ID 数组')
    notes = payload.get('review_notes')
    if notes is not None and (not isinstance(notes, str) or len(notes) > 20000):
        issue('review_notes', 'review_notes 必须是文本，最多 20000 字符')
    return issues


def require_ui_payload_shape(payload):
    issues = validate_ui_payload(payload)
    if issues:
        raise ValueError('；'.join(item['path'] + ': ' + item['message'] for item in issues))
