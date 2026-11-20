"""Human-reviewed PingCode publishing. No model calls and no MCP publishing action."""
from __future__ import annotations

import base64
import binascii
import fcntl
import hashlib
import html
import json
import os
import re
from io import BytesIO
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit

import requests
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from .defect_drafts import case_defect_draft, finding_draft
from .execution import Redactor
from .defect_triage import assess_defect
from .report_reads import _ReportBatch
from .network_transport import pinned_session
from .web_security import check_public_endpoint

DEFAULTS = dict(base_url="https://open.pingcode.com", api_version="pjm", auth_mode="client_credentials",
                client_id="", default_project_id="", default_type_id="")
SECRETS = {"client_secret", "access_token"}
ID = re.compile(r"[A-Za-z0-9_-]{1,160}\Z")
MAX_SCREENSHOTS = 3
MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
MAX_DESCRIPTION_CHARS = 65536
MAX_SCREENSHOT_REQUEST_BYTES = MAX_SCREENSHOTS * MAX_SCREENSHOT_BYTES * 4 // 3 + 1_000_000
SCREENSHOT_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
TRIAGE_STATUSES = {
    'pending_submission', 'submitted', 'rejected', 'deferred',
    'pending_regression', 'regression_passed', 'regression_failed', 'result_corrected',
}
TRIAGE_REASON_REQUIRED = {'rejected', 'deferred', 'regression_passed', 'regression_failed'}


def description_html(text, images=(), *, report_url=''):
    """The editor consumes HTML blocks; keep reviewed input literal, not Markdown."""
    parsed = urlsplit(report_url)
    linkable = parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username and not parsed.password
    lines = []
    for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        content = html.escape(line) or '<br>'
        if linkable and line == report_url:
            content = '<a href="' + html.escape(report_url, quote=True) + '" target="_blank" rel="noopener noreferrer">' + content + '</a>'
        lines.append('<p>' + content + '</p>')
    result = ''.join(lines)
    if images:
        result += '<p>【截图证据】</p>'
        for image in images:
            result += '<p><img src="' + html.escape(image['url'], quote=True) + '" alt="' + html.escape(image['title'], quote=True) + '"></p>'
    return result


def checked_description(value):
    # Count UTF-16 units as well, so emoji cannot exceed the remote limit.
    if len(value.encode('utf-16-le')) // 2 > MAX_DESCRIPTION_CHARS:
        raise ValueError('缺陷正文超过 PingCode 的 65536 字符上限，请精简正文后重试')
    return value


def screenshot_previews(description, screenshots, *, report_url=''):
    images = [{'title': shot['title'], 'url': ''} for shot in screenshots]
    shell = checked_description(description_html(description, images, report_url=report_url))
    remaining = MAX_DESCRIPTION_CHARS - len(shell.encode('utf-16-le')) // 2
    for index, shot in enumerate(screenshots):
        budget = remaining // (len(screenshots) - index)
        url = 'data:' + shot['content_type'] + ';base64,' + base64.b64encode(shot['content']).decode('ascii')
        if len(url) > budget:
            from PIL import Image, ImageOps, UnidentifiedImageError
            prefix = 'data:image/webp;base64,'
            byte_budget = (budget - len(prefix)) // 4 * 3
            if byte_budget < 2048:
                raise ValueError('正文剩余空间不足以显示截图，请精简正文后重试；原图不会被截断')
            try:
                with Image.open(BytesIO(shot['content'])) as source:
                    if source.width * source.height > 24_000_000:
                        raise ValueError('截图尺寸过大，请使用不超过 2400 万像素的截图')
                    preview = ImageOps.exif_transpose(source).convert('RGB')
                preview.thumbnail((1600, 1600))
                while True:
                    for quality in (85, 70, 55):
                        output = BytesIO()
                        preview.save(output, format='WEBP', quality=quality, method=4)
                        if output.tell() <= byte_budget:
                            url = prefix + base64.b64encode(output.getvalue()).decode('ascii')
                            break
                    else:
                        if max(preview.size) <= 320:
                            raise ValueError('截图无法在正文上限内生成预览，请精简正文或减少截图后重试')
                        preview.thumbnail((max(1, int(preview.width * .8)), max(1, int(preview.height * .8))))
                        continue
                    break
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                raise ValueError('截图无法解码，请重新选择有效图片') from exc
        images[index]['url'] = url
        remaining -= len(url)
    checked_description(description_html(description, images, report_url=report_url))
    return images


def with_report_reference(text, reference):
    """Keep manual wording; append the server-owned source link only once."""
    if reference['url'] in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        return text
    return text + '\n\n' + reference['text']


class DescriptionContent(HTMLParser):
    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.images = []
        self.links = []
        self.feed(value)

    def handle_data(self, data):
        self.text.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            self.images.append(dict(attrs).get('src', ''))
        if tag == 'a':
            self.links.append(dict(attrs).get('href', ''))


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("PingCode 标识格式无效")
    return value


class PingCodeError(ValueError):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


class PingCode:
    def __init__(self, store):
        self.store = store
        self.trusted = tuple(x.strip().rstrip('/') for x in os.environ.get('PINGCODE_ALLOWED_ORIGINS', '').split(',') if x.strip())

    def config(self, owner, private=False):
        path = self.store._owner_dir(owner) / 'pingcode.json'
        value = self.store._read(path) if path.exists() else {}
        shared = False
        if not value and os.environ.get('PINGCODE_CONFIG_FILE'):
            value = self.store._read(Path(os.environ['PINGCODE_CONFIG_FILE']))
            shared = True
        result = {**DEFAULTS, **{k: v for k, v in value.items() if k in DEFAULTS}}
        for key in SECRETS:
            secret = value.get(key, '') if shared else (
                self.store._cipher.decrypt(value[key + '_ciphertext'].encode()).decode() if value.get(key + '_ciphertext') else '')
            result['has_' + key] = bool(secret)
            if private:
                result[key] = secret
        result['shared'] = shared
        result['configured'] = bool(result['has_access_token'] if result['auth_mode'] == 'token' else result['client_id'] and result['has_client_secret'])
        return result

    def save(self, owner, data):
        if set(data) - (set(DEFAULTS) | SECRETS):
            raise ValueError('存在不支持的配置字段')
        with self.store._lock:
            old = self.config(owner, True)
            # Shared credentials cannot be copied into a personal configuration.
            if old['shared']:
                old = {**DEFAULTS, **{k: '' for k in SECRETS}}
            cfg = {k: data.get(k, old.get(k, '')) for k in DEFAULTS}
            if any(not isinstance(v, str) or len(v) > 2048 for v in cfg.values()):
                raise ValueError('配置字段格式无效')
            cfg['base_url'] = cfg['base_url'].strip().rstrip('/')
            check_public_endpoint(cfg['base_url'], self.trusted)
            if cfg['api_version'] not in {'pjm', 'project'} or cfg['auth_mode'] not in {'client_credentials', 'token'}:
                raise ValueError('请选择支持的接口版本与授权方式')
            changed = any(cfg[k] != old.get(k) for k in ('base_url', 'auth_mode', 'client_id'))
            for key in SECRETS:
                secret = data.get(key, '')
                if not isinstance(secret, str) or len(secret) > 16384 or any(ord(c) < 32 for c in secret):
                    raise ValueError('凭据格式无效')
                secret = secret or ('' if changed else old.get(key, ''))
                cfg[key + '_ciphertext'] = self.store._cipher.encrypt(secret.encode()).decode() if secret else ''
            self.store._write(self.store._owner_dir(owner) / 'pingcode.json', cfg)
        return self.config(owner)

    def request(self, cfg, method, path, *, token='', params=None, body=None, form=None, files=None):
        check_public_endpoint(cfg['base_url'], self.trusted)
        try:
            with pinned_session(cfg['base_url'], self.trusted) as session:
                with session.request(method, cfg['base_url'] + path, params=params, json=body,
                                     data=form, files=files,
                                     headers={'Authorization': 'Bearer ' + token} if token else {},
                                     timeout=(10, 30), stream=True) as response:
                    # Inline screenshots can make a work item larger than ordinary metadata.
                    response_limit = (MAX_SCREENSHOT_REQUEST_BYTES + 2_000_000
                                      if re.fullmatch(r'/v1/(?:pjm/workitems|project/work_items)/[A-Za-z0-9_-]+', path)
                                      and method in {'GET', 'PATCH'} else 2_000_000)
                    content = bytearray()
                    for chunk in response.iter_content(65536):
                        content.extend(chunk)
                        if len(content) > response_limit:
                            raise PingCodeError('PingCode 返回内容过大，请核对服务地址。', method in {'POST', 'PATCH'})
                    try:
                        data = json.loads(content)
                    except (ValueError, UnicodeError):
                        raise PingCodeError('PingCode 未返回有效 JSON，请核对 API 地址与版本。', method in {'POST', 'PATCH'}) from None
                    if not 200 <= response.status_code < 300:
                        message = data.get('message') or data.get('error_description') or data.get('error') or '' if isinstance(data, dict) else ''
                        message = str(Redactor().clean(message))[:400]
                        for key in SECRETS | {'client_id'}:
                            if cfg.get(key):
                                message = message.replace(cfg[key], '<redacted>')
                        if token:
                            message = message.replace(token, '<redacted>')
                        hint = {401: '授权已失效，请更新凭据', 403: '无项目访问或创建权限', 404: '地址、接口版本或项目不存在',
                                429: '请求频率超限，请稍后重试'}.get(response.status_code, '请核对字段与项目配置')
                        raise PingCodeError(f'PingCode HTTP {response.status_code}：{hint}。{message}', method in {'POST', 'PATCH'} and response.status_code >= 500)
                    if not isinstance(data, dict):
                        raise PingCodeError('PingCode 响应格式不正确。', method in {'POST', 'PATCH'})
                    return data
        except requests.RequestException:
            raise PingCodeError('无法取得 PingCode 响应，请检查服务地址、网络或 TLS 证书。', method in {'POST', 'PATCH'}) from None

    def token(self, cfg):
        if not cfg['configured']:
            raise ValueError('请先在集成管理配置 PingCode 授权')
        if cfg['auth_mode'] == 'token':
            return cfg['access_token']
        data = self.request(cfg, 'GET', '/v1/auth/token', params={
            'grant_type': 'client_credentials', 'client_id': cfg['client_id'], 'client_secret': cfg['client_secret']})
        if not isinstance(data.get('access_token'), str) or not data['access_token']:
            raise ValueError('PingCode 未返回访问令牌，请检查应用凭据')
        return data['access_token']

    def collection(self, cfg, token, path, params=None):
        values = []
        for page in range(100):
            data = self.request(cfg, 'GET', path, token=token, params={**(params or {}), 'page_index': page, 'page_size': 100})
            batch = data.get('values')
            if not isinstance(batch, list) or any(not isinstance(x, dict) for x in batch):
                raise ValueError('PingCode 列表格式不正确，请核对 API 版本')
            values.extend(batch)
            if not batch or len(values) >= data.get('total', len(values)):
                return values
        raise ValueError('PingCode 列表超过 100 页，请缩小应用授权范围')

    def projects(self, cfg, token):
        return [dict(id=p['id'], name=p['name']) for p in self.collection(cfg, token, '/v1/' + cfg['api_version'] + '/projects')
                if not p.get('is_deleted') and not p.get('is_archived')]

    def metadata(self, cfg, token, pid, type_id=''):
        identifier(pid)
        root = '/v1/' + cfg['api_version']
        noun = '/workitem' if cfg['api_version'] == 'pjm' else '/work_item'
        types = self.collection(cfg, token, root + noun + '/types', {'project_id': pid})
        types = [t for t in types if t.get('group') == 'bug' or t['id'] == 'bug']
        if type_id:
            identifier(type_id)
            if type_id not in {t['id'] for t in types}:
                raise ValueError('请选择当前项目的缺陷类型')
        else:
            type_id = next((t['id'] for t in types if t['id'] == cfg['default_type_id']), types[0]['id'] if types else '')
        if not type_id:
            raise ValueError('当前项目未提供缺陷类型，请在 PingCode 配置后再提交')
        priorities = self.collection(cfg, token, root + ('/workitem/priorities' if cfg['api_version'] == 'pjm' else '/priorities'), {'project_id': pid})
        members = self.collection(cfg, token, root + '/projects/' + pid + '/members')
        properties = self.collection(cfg, token, root + noun + '/properties', {'project_id': pid,
            ('workitem_type_id' if cfg['api_version'] == 'pjm' else 'work_item_type_id'): type_id})
        return dict(types=types, type_id=type_id, priorities=priorities,
                    members=[m['user'] for m in members if m.get('type') == 'user' and m.get('user')], properties=properties)

    def analysis_report(self, owner, pid, rid, *, _reports=None):
        reports = _reports if _reports is not None else _ReportBatch(self.store)
        return reports.report(owner, pid, rid, normalize=True)

    def has_analysis_report(self, owner, project, rid):
        if rid in {r['id'] for r in project.get('analysis_reports', [])}:
            return True
        return self.store.has_saved_report(owner, project['id'], rid)

    def source(self, owner, pid, rid, draft_id, *, _reports=None):
        project = self.store.get_project(owner, pid)
        root = self.store.project_dir(owner, pid)
        match = re.fullmatch(r'(defect|finding)-(\d{1,5})', draft_id)
        if not match:
            raise ValueError('缺陷来源无效')
        kind, index = match[1], int(match[2])
        if kind == 'finding' and self.has_analysis_report(owner, project, rid):
            report = self.analysis_report(owner, pid, rid, _reports=_reports)
            if index >= len(report['findings']):
                raise ValueError('检查发现不存在')
            text = finding_draft(report, report['findings'][index])
        elif kind == 'defect' and (rid in {r['id'] for r in project.get('runs', [])}
                                 or self.store.has_saved_report(owner, pid, rid, kind='runs')):
            result = self.store._read(root / 'runs' / rid / 'result.json')
            bundle = self.store._read(root / 'runs' / rid / 'bundle.json')
            if index >= len(result['cases']):
                raise ValueError('用例不存在')
            draft = case_defect_draft(result, bundle, result['cases'][index])
            if not draft:
                raise ValueError('当前用例没有缺陷或异常记录')
            text = draft[1]
        else:
            raise FileNotFoundError('报告不存在')
        key = hashlib.sha256((rid + ':' + draft_id).encode()).hexdigest()
        directory = root / 'pingcode'
        self.store._mkdir(directory)
        return text, key, directory / (key + '.json')

    def report_reference(self, request, pid, rid, draft_id):
        # Called only after source() validates ownership, report and draft identity.
        root = self.store.project_dir(request.state.owner, pid)
        kind, index = draft_id.split('-')
        if kind == 'finding':
            source = self.store._read(root / 'analyses' / rid / 'report.json')['findings'][int(index)]
            case_id = source.get('case_id', '')
        else:
            source = self.store._read(root / 'runs' / rid / 'result.json')['cases'][int(index)]
            case_id = source['id']
        url = str(request.url_for('report', project_id=pid, run_id=rid, filename='index.html'))
        lines = ['【平台报告】', url]
        if case_id:
            lines.append('用例编号：' + str(case_id))
        lines.append('打开报告查看测试数据、复现步骤和执行证据；可下载的测试文件在报告中获取。')
        return {'url': url, 'case_id': case_id, 'text': '\n'.join(lines)}

    @staticmethod
    def triage_status(record):
        if not record:
            return 'pending_submission'
        value = record.get('triage_status')
        if value in TRIAGE_STATUSES:
            return value
        return 'submitted' if record.get('status') == 'submitted' else 'pending_submission'

    def effective_record(self, owner, record, *, _reports=None):
        if not record or self.triage_status(record) in {'rejected', 'deferred'}:
            return record
        source = record.get('source', {})
        if not source.get('draft_id', '').startswith('finding-'):
            return record
        reports = _reports if _reports is not None else _ReportBatch(self.store)
        report = self.analysis_report(owner, source['project_id'], source['run_id'], _reports=reports)
        if not report.get('ui_snapshot'):
            return record
        finding = report['findings'][int(source['draft_id'].split('-')[1])]
        case = next((c for c in report.get('imported_results', {}).get('cases', [])
                     if c.get('case_id') == finding.get('case_id')), {})
        link = next((l for l in report.get('regression_links', []) if l.get('draft_id') == source['draft_id']), None)
        # Original defects can receive a valid result from a later round.
        result = record.get('regression_result', {})
        result_is_later = result.get('project_id') and result['project_id'] != source['project_id']
        from .defect_results import current_outcome, prior_failure, round_id
        if result_is_later:
            result_is_later = round_id(self.store.get_project(owner, result['project_id'])) != round_id(self.store.get_project(owner, source['project_id']))
            if result_is_later:
                later = self.analysis_report(owner, result['project_id'], result['report_id'], _reports=reports)
                result_is_later = any(l.get('case_id') == finding.get('case_id') and l.get('outcome') == record.get('triage_status')
                    and prior_failure(self.store, owner, result['project_id'], l, _reports=reports) for l in later.get('regression_links', []))
        if self.triage_status(record) == 'pending_regression' and case.get('status') == 'failed':
            return record
        corrected = case.get('status_before_correction') not in (None, case.get('status'))
        invalid_link = link and not prior_failure(self.store, owner, source['project_id'], link, _reports=reports)
        unsupported_result = not link and self.triage_status(record) in {'regression_passed', 'regression_failed'}
        no_current_failure = case and case.get('status') != 'failed' and not link
        if corrected or not result_is_later and (invalid_link or unsupported_result or no_current_failure):
            outcome = current_outcome(case)
            if outcome == 'pending_submission' and record.get('status') == 'submitted':
                outcome = 'submitted'
            return {**record, 'triage_status': outcome}
        return record

    @classmethod
    def record_summary(cls, record):
        return dict(
            draft_id=record['source']['draft_id'], status=record.get('status', 'draft'),
            triage_status=cls.triage_status(record), triage_reason=record.get('triage_reason', ''),
            item=record.get('item'), description_error=record.get('description_error'),
            screenshot_error=record.get('screenshot_error'), updated_at=record.get('updated_at', ''),
            lineage=record.get('lineage'), remote_state=record.get('remote_state'),
            remote_state_action=record.get('remote_state_action'), remote_sync=record.get('remote_sync'),
            target=record.get('target'),
        )

    def reopen_item(self, owner, record):
        return self.sync_regression_state(owner, record)

    def sync_regression_state(self, owner, record, *, accepted=False, before_write=None):
        if record.get('status') != 'submitted' or not record.get('item') or (not accepted and not record.get('lineage')):
            raise ValueError('当前记录没有可同步状态的 PingCode 缺陷')
        source_owner = self.store.find_project_owner(record['source']['project_id']) if record.get('source', {}).get('project_id') else owner
        record = self.effective_record(source_owner, record)
        expected = 'regression_passed' if accepted else 'regression_failed'
        if self.triage_status(record) != expected:
            raise ValueError('只有回归通过的缺陷可以验收' if accepted else '只有回归失败的历史缺陷可以重新打开')
        cfg = self.config(owner, True)
        target = record.get('target', {})
        if any(cfg.get(key) != target.get(key) for key in ('base_url', 'api_version')):
            raise ValueError('请切回原缺陷对应的 PingCode 连接后重试')
        token = self.token(cfg)
        pid = identifier(target.get('project_id'))
        type_id = identifier(record.get('payload', {}).get('type_id'))
        root = '/v1/' + cfg['api_version']
        noun = '/workitem' if cfg['api_version'] == 'pjm' else '/work_item'
        states = self.collection(cfg, token, root + noun + '/states', {
            'project_id': pid,
            ('workitem_type_id' if cfg['api_version'] == 'pjm' else 'work_item_type_id'): type_id})
        exact_names = ('已验收',) if accepted else ('重新打开', '重新开启', '重开', '待处理', '打开', '新建')
        state = next((item for name in exact_names for item in states if item.get('name') == name), None)
        if state is None and not accepted:
            pending = [item for item in states if item.get('type') == 'pending']
            state = pending[0] if len(pending) == 1 else None
        if accepted and len([item for item in states if item.get('name') == '已验收']) != 1:
            raise ValueError('未能唯一识别 PingCode 的已验收状态，请在原缺陷中手动调整')
        if not state or not isinstance(state.get('id'), str):
            raise ValueError('未能唯一识别 PingCode 的目标状态，请在原缺陷中手动调整')
        noun_plural = 'workitems' if cfg['api_version'] == 'pjm' else 'work_items'
        item_path = f'{root}/{noun_plural}/{identifier(record["item"]["id"])}'
        target_state = {'id': state['id'], 'name': state.get('name', '重新打开')}
        if before_write:
            remote = self.request(cfg, 'GET', item_path, token=token)
            if self.remote_state_id(remote) == state['id']:
                return target_state
            before_write(target_state)
        self.request(cfg, 'PATCH', item_path, token=token, body={'state_id': state['id']})
        if before_write:
            try:
                remote = self.request(cfg, 'GET', item_path, token=token)
                if self.remote_state_id(remote) != state['id']:
                    raise ValueError('状态不一致')
            except Exception:
                raise PingCodeError('状态写入后未通过回读核验，请刷新同步状态核对', uncertain=True) from None
        return target_state

    @staticmethod
    def remote_state_id(remote):
        return remote.get('state_id') or (remote.get('state') or {}).get('id')

    def read_remote_state(self, owner, record):
        cfg = self.config(owner, True)
        if any(cfg.get(k) != record.get('target', {}).get(k) for k in ('base_url', 'api_version')):
            raise ValueError('请切回原缺陷对应的 PingCode 连接后核对')
        noun = 'workitems' if cfg['api_version'] == 'pjm' else 'work_items'
        remote = self.request(cfg, 'GET', f'/v1/{cfg["api_version"]}/{noun}/{identifier(record["item"]["id"])}', token=self.token(cfg))
        state_id = self.remote_state_id(remote)
        if not state_id:
            raise ValueError('未能读取 PingCode 当前状态，请在原缺陷中核对')
        return {'id': state_id, 'name': (remote.get('state') or {}).get('name', '')}

    def lifecycle_for_report(self, owner, project_id, run_id, *, _reports=None):
        reports = _reports if _reports is not None else _ReportBatch(self.store)
        root = self.store.project_dir(owner, project_id) / 'pingcode'
        values = []
        for path in root.glob('*.json'):
            record = self.store._read(path)
            if record.get('source', {}).get('run_id') == run_id:
                values.append(self.record_summary(self.effective_record(owner, record, _reports=reports)))
        return sorted(values, key=lambda item: item['draft_id'])

    def rejected_report_findings(self, owner, report):
        """Public presentation IDs only; never expose integration records."""
        rejected, roots = [], {}
        for index, finding in enumerate(report.get('findings', [])):
            source = finding.get('draft_source') or {
                'project_id': report.get('project_id'), 'report_id': report.get('id'),
                'draft_id': f'finding-{index}'}
            pid, rid, draft = (source.get(key) for key in ('project_id', 'report_id', 'draft_id'))
            if not pid or not rid or not re.fullmatch(r'(finding|defect)-\d{1,5}', draft or ''):
                continue
            if pid not in roots:
                try:
                    roots[pid] = self.store.project_dir(owner, pid) / 'pingcode'
                except (FileNotFoundError, PermissionError, ValueError):
                    roots[pid] = None
            if roots[pid] is None:
                continue
            path = roots[pid] / (hashlib.sha256((rid + ':' + draft).encode()).hexdigest() + '.json')
            record = self.store._read(path) if path.is_file() else {}
            if self.triage_status(record) == 'rejected':
                rejected.append(f'finding-{index}')
        return rejected

    def sync_regression_sources(self, owner, project_id, run_id, links, cases, *, _reports=None):
        """Update the original local defect lifecycle, including unsubmitted drafts.

        No remote API calls: PingCode work item transitions retain their existing
        explicit review workflow. Rejected/deferred human decisions take priority.
        """
        reports = _reports if _reports is not None else _ReportBatch(self.store)
        observations = {c['case_id']: c for c in cases}
        for link in links:
            case = observations.get(link['case_id'], {})
            if case.get('status') == 'not_run' or not (case.get('actual') or case.get('not_run_reason')):
                continue
            origin = {key: link[key] for key in ('source_project_id', 'source_report_id', 'source_draft_id')}
            seen = set()
            while origin:
                identity = tuple(origin[key] for key in ('source_project_id', 'source_report_id', 'source_draft_id'))
                if identity in seen:
                    break
                seen.add(identity)
                _, _, path = self.source(owner, *identity, _reports=reports)
                with self.record_lock(path):
                    record = self.store._read(path) if path.exists() else {}
                    lineage = record.get('lineage')
                    previous_result = record.get('regression_result', {})
                    observed_at = case.get('updated_at') or now()
                    if self.triage_status(record) not in {'rejected', 'deferred'} and observed_at >= previous_result.get('observed_at', ''):
                        result = dict(outcome=link['outcome'], project_id=project_id,
                                      report_id=run_id, observed_at=observed_at)
                        if result != previous_result:
                            record.setdefault('source', dict(project_id=identity[0], run_id=identity[1], draft_id=identity[2]))
                            record.setdefault('status', 'draft')
                            record.setdefault('created_at', now())
                            if self.triage_status(record) != link['outcome']:
                                for key in ('remote_state', 'remote_state_action'):
                                    record.pop(key, None)
                                if record.get('remote_sync', {}).get('status') not in {'pending', 'unknown'}:
                                    record.pop('remote_sync', None)
                            record.update(triage_status=link['outcome'], updated_at=now(), regression_result=result)
                            record.setdefault('history', []).append(dict(at=now(), action='regression_result',
                                value=link['outcome'], project_id=project_id, report_id=run_id, observed_at=observed_at))
                            self.store._write(path, record)
                origin = lineage

    def inherit_regression(self, owner, project_id, run_id, links, cases=None):
        """Seed this report with the prior defect identity; never create a second work item."""
        reports = _ReportBatch(self.store)
        for link in links:
            _, _, source_path = self.source(owner, link['source_project_id'], link['source_report_id'],
                                             link['source_draft_id'], _reports=reports)
            previous = self.store._read(source_path) if source_path.exists() else {}
            _, _, target_path = self.source(owner, project_id, run_id, link['draft_id'], _reports=reports)
            prior_triage = self.triage_status(previous)
            has_remote_item = previous.get('status') == 'submitted' and previous.get('item')
            existing = self.store._read(target_path) if target_path.exists() else {}
            human = self.triage_status(existing)
            triage = (human if human in {'rejected', 'deferred'} else
                      prior_triage if prior_triage in {'rejected', 'deferred'} else link['outcome'])
            if triage == 'pending_submission' and (has_remote_item or existing.get('status') == 'submitted'):
                triage = 'submitted'
            record = {key: previous[key] for key in (
                'target', 'payload', 'item', 'screenshots', 'description_verified') if key in previous}
            record.update(existing)
            record.update(status=existing.get('status') or ('submitted' if has_remote_item else 'draft'), triage_status=triage,
                          triage_reason=existing.get('triage_reason', previous.get('triage_reason', '')),
                          created_at=existing.get('created_at') or now(), updated_at=now(),
                          source=dict(project_id=project_id, run_id=run_id, draft_id=link['draft_id']),
                          lineage={key: link[key] for key in ('case_id', 'source_project_id',
                                   'source_report_id', 'source_draft_id')},
                          history=list(existing.get('history', previous.get('history', []))))
            if not existing or existing.get('triage_status') != triage:
                for key in ('remote_state', 'remote_state_action'):
                    record.pop(key, None)
                if record.get('remote_sync', {}).get('status') not in {'pending', 'unknown'}:
                    record.pop('remote_sync', None)
                record['history'].append(dict(at=now(), action='regression_result', value=link['outcome'],
                                              source_report_id=link['source_report_id']))
            self.store._write(target_path, record)
        if cases is not None:
            self.sync_regression_sources(owner, project_id, run_id, links, cases, _reports=reports)

    @contextmanager
    def record_lock(self, path):
        with path.with_suffix('.lock').open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise HTTPException(409, '该缺陷正在提交，请稍后刷新状态') from None
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    @staticmethod
    def item(data):
        if not isinstance(data.get('id'), str) or not data['id']:
            raise PingCodeError('未取得缺陷编号，提交结果待核对。', True)
        link = data.get('html_url', '')
        parsed = urlsplit(link)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            link = ''
        return dict(id=data['id'], identifier=data.get('identifier', data['id']), url=link)

    @staticmethod
    def screenshots(values):
        if values in (None, []):
            return []
        if not isinstance(values, list) or len(values) > MAX_SCREENSHOTS:
            raise ValueError(f'每条缺陷最多粘贴 {MAX_SCREENSHOTS} 张截图')
        result = []
        for index, value in enumerate(values, 1):
            if not isinstance(value, dict) or set(value) - {'content_type', 'content_base64'}:
                raise ValueError('截图内容格式无效')
            content_type = value.get('content_type')
            if content_type not in SCREENSHOT_TYPES or not isinstance(value.get('content_base64'), str):
                raise ValueError('截图仅支持 PNG、JPEG 或 WebP 图片')
            try:
                content = base64.b64decode(value['content_base64'], validate=True)
            except (binascii.Error, ValueError):
                raise ValueError('截图内容格式无效') from None
            if not content or len(content) > MAX_SCREENSHOT_BYTES:
                raise ValueError('单张截图不能超过 5 MB')
            signatures = {
                'image/png': content.startswith(b'\x89PNG\r\n\x1a\n'),
                'image/jpeg': content.startswith(b'\xff\xd8\xff'),
                'image/webp': content.startswith(b'RIFF') and content[8:12] == b'WEBP',
            }
            if not signatures[content_type]:
                raise ValueError('截图文件内容与图片类型不一致')
            result.append(dict(title=f'截图-{index}.{SCREENSHOT_TYPES[content_type]}',
                               content_type=content_type, content=content))
        return result

    def add_screenshots(self, cfg, token, item_id, description, screenshots, *, report_url='',
                        uploaded=None, on_upload=None):
        principal_type = 'workitem' if cfg['api_version'] == 'pjm' else 'work_item'
        previews = screenshot_previews(description, screenshots, report_url=report_url)
        uploaded = uploaded if uploaded is not None else []
        for index, screenshot in enumerate(screenshots):
            if index < len(uploaded) and uploaded[index].get('id'):
                uploaded[index]['url'] = previews[index]['url']
                continue
            data = self.request(cfg, 'POST', '/v1/attachments', token=token,
                                params={'principal_type': principal_type, 'principal_id': item_id},
                                form={'title': screenshot['title']},
                                files={'file': (screenshot['title'], screenshot['content'], screenshot['content_type'])})
            uploaded.append({'id': data.get('id', ''), **previews[index]})
            if on_upload:
                on_upload()
        enriched = checked_description(description_html(description, previews, report_url=report_url))
        noun = 'workitems' if cfg['api_version'] == 'pjm' else 'work_items'
        self.request(cfg, 'PATCH', f'/v1/{cfg["api_version"]}/{noun}/{identifier(item_id)}',
                     token=token, body={'description': enriched})
        return enriched, uploaded

    def verify_description(self, cfg, token, item_id, expected):
        noun = 'workitems' if cfg['api_version'] == 'pjm' else 'work_items'
        result = self.request(cfg, 'GET', f'/v1/{cfg["api_version"]}/{noun}/{identifier(item_id)}', token=token)
        actual = result.get('description')
        if not isinstance(actual, str):
            raise PingCodeError('未能读取已保存的描述，请在 PingCode 核对。')
        wanted, saved = DescriptionContent(expected), DescriptionContent(actual)
        normalize = lambda parts: re.sub(r'\s+', '', ''.join(parts)).replace('\ufeff', '')
        if (normalize(wanted.text) != normalize(saved.text)
                or any(url not in saved.images for url in wanted.images)
                or any(url not in saved.links for url in wanted.links)):
            raise PingCodeError('描述或截图回读与提交内容不一致，请在 PingCode 核对；请勿重复创建缺陷。')


def install_pingcode(app, store, static):
    service = PingCode(store)
    app.state.pingcode = service

    @app.get('/integrations/pingcode')
    def page():
        return FileResponse(static / 'pingcode.html', media_type='text/html')

    @app.get('/api/integrations/pingcode')
    def config(request: Request):
        return service.config(request.state.owner)

    @app.put('/api/integrations/pingcode')
    def save(request: Request, data: dict):
        return service.save(request.state.owner, data)

    @app.delete('/api/integrations/pingcode')
    def clear(request: Request):
        (store._owner_dir(request.state.owner) / 'pingcode.json').unlink(missing_ok=True)
        return service.config(request.state.owner)

    @app.get('/api/integrations/pingcode/projects')
    def projects(request: Request):
        cfg = service.config(request.state.owner, True)
        return dict(values=service.projects(cfg, service.token(cfg)))

    @app.get('/api/integrations/pingcode/metadata')
    def metadata(request: Request, project_id: str, type_id: str = ''):
        cfg = service.config(request.state.owner, True)
        return service.metadata(cfg, service.token(cfg), project_id, type_id)

    @app.get('/api/projects/{project_id}/reports/{run_id}/pingcode')
    def records(request: Request, project_id: str, run_id: str):
        project = store.get_project(request.state.owner, project_id)
        if run_id not in {r['id'] for r in project.get('runs', [])} and not service.has_analysis_report(request.state.owner, project, run_id):
            raise FileNotFoundError('报告不存在')
        return dict(values=service.lifecycle_for_report(request.state.owner, project_id, run_id))

    route = '/api/projects/{project_id}/reports/{run_id}/pingcode/{draft_id}'

    @app.patch(route + '/lifecycle')
    def lifecycle(request: Request, project_id: str, run_id: str, draft_id: str, data: dict):
        batches.assert_available(request, project_id, run_id, draft_id)
        owner = request.state.owner
        _, _, path = service.source(owner, project_id, run_id, draft_id)
        status = data.get('status')
        reason = data.get('reason', '')
        if status not in TRIAGE_STATUSES:
            raise ValueError('请选择有效的缺陷状态')
        if not isinstance(reason, str) or len(reason) > 4000:
            raise ValueError('状态说明不能超过 4000 个字符')
        reason = reason.strip()
        if status in TRIAGE_REASON_REQUIRED and not reason:
            raise ValueError('拒绝、暂缓或更正回归结论时必须填写原因或实测依据')
        with service.record_lock(path):
            previous = store._read(path) if path.exists() else {}
            if (getattr(request.state, 'report_scope', None) or 'expected_updated_at' in data):
                if data.get('expected_updated_at') != previous.get('updated_at', ''):
                    raise HTTPException(409, '缺陷状态已被其他协作者更新，请刷新后重试')
            if status == 'submitted' and previous.get('status') != 'submitted':
                raise ValueError('只有实际提交成功的缺陷才能标记为已提交')
            if status in {'regression_passed', 'regression_failed'}:
                from .defect_results import prior_failure
                report = service.analysis_report(owner, project_id, run_id)
                link = next((l for l in report.get('regression_links', []) if l.get('draft_id') == draft_id), None)
                if not link or not prior_failure(store, owner, project_id, link):
                    raise ValueError('只有复测旧轮次的真实失败用例才能记录回归结论；同轮复测或误判更正不属于回归')
                case = next((c for c in report.get('imported_results', {}).get('cases', []) if c.get('case_id') == link['case_id']), {})
                expected_status = 'passed' if status == 'regression_passed' else 'failed'
                if case.get('status') != expected_status or case.get('status_before_correction') not in (None, case.get('status')):
                    raise ValueError('回归结论必须与本轮实际执行结果一致，人工更正结果不能代替回归执行')
            old_status = service.triage_status(previous)
            record = {
                **previous,
                'status': previous.get('status', 'draft'),
                'created_at': previous.get('created_at', now()),
                'updated_at': now(),
                'source': previous.get('source', dict(project_id=project_id, run_id=run_id, draft_id=draft_id)),
                'triage_status': status,
                'triage_reason': reason,
                'history': previous.get('history', []),
            }
            if previous.get('remote_sync', {}).get('status') in {'pending', 'unknown'}:
                raise HTTPException(409, '同步结果待核对，请先刷新同步状态')
            if old_status != status:
                record.pop('remote_sync', None)
                record.pop('remote_state', None)
                record.pop('remote_state_action', None)
            record['history'].append(dict(at=now(), action='triage_status', previous=old_status,
                                          value=status, reason=reason,
                                          actor=(request.state.user or {}).get('username', '')))
            store._write(path, record)
            return record

    @app.get(route)
    def draft(request: Request, project_id: str, run_id: str, draft_id: str):
        text, key, path = service.source(request.state.owner, project_id, run_id, draft_id)
        reference = service.report_reference(request, project_id, run_id, draft_id)
        text = with_report_reference(text, reference)
        record = service.effective_record(request.state.owner, store._read(path)) if path.exists() else None
        authored = {}
        correction_revision = 0
        title_corrected = False
        imported_finding = False
        screenshots = []
        if draft_id.startswith('finding-'):
            saved = service.analysis_report(request.state.owner, project_id, run_id)
            correction_revision = saved.get('case_corrections', {}).get('revision', 0)
            authored = saved['findings'][int(draft_id.split('-')[1])]
            title_corrected = any(case.get('defect_title') for case in saved.get('imported_results', {}).get('cases', [])
                                  if case.get('case_id') == authored.get('case_id'))
            imported_finding = bool(saved.get('imported_results'))
            snapshot = saved.get('ui_snapshot', {})
            for asset in snapshot.get('assets', []):
                if asset['kind'] != 'screenshot' or asset['case_id'] != authored.get('case_id'):
                    continue
                if len(screenshots) >= MAX_SCREENSHOTS:
                    break
                from .ui_records import root_for
                content = (root_for(store, request.state.owner, project_id, snapshot['id']) / asset['id']).read_bytes()
                encoded = base64.b64encode(content).decode()
                screenshots.append({'asset_id': asset['id'], 'content_type': asset['content_type'], 'content_base64': encoded,
                                    'preview': 'data:' + asset['content_type'] + ';base64,' + encoded})
        title = authored.get('title', '') if imported_finding else text.splitlines()[0].removeprefix('【标题】')
        ui_title = store.get_project(request.state.owner, project_id).get('test_kind') == 'ui'
        if ui_title:
            from .defect_title import normalize_title
            title = normalize_title(title)
        assessment = assess_defect(title, authored.get('severity', ''), authored.get('priority', ''))
        return dict(description=text, title=title, ui_title=ui_title, title_corrected=title_corrected,
                    correction_revision=correction_revision,
                    record=record, marker='api-test:' + key,
                    assessment=assessment, screenshots=screenshots, report_reference=reference)

    def sync_remote(request, project_id, run_id, draft_id, action, data):
        batches.assert_available(request, project_id, run_id, draft_id)
        owner = request.state.owner
        _, _, path = service.source(owner, project_id, run_id, draft_id)
        with service.record_lock(path):
            if not path.exists():
                raise ValueError('当前报告没有关联 PingCode 缺陷')
            record = store._read(path)
            expected = 'regression_passed' if action == 'accept' else 'regression_failed'
            if service.triage_status(service.effective_record(owner, record)) != expected:
                raise ValueError('只有回归通过的缺陷可以验收' if action == 'accept' else '只有回归失败的缺陷可以重新打开')
            if record.get('remote_sync', {}).get('status') in {'pending', 'unknown'}:
                raise HTTPException(409, '上次同步结果待核对，请先刷新同步状态')
            if record.get('remote_state') and (record.get('remote_state_action') == action or
                    (action == 'reopen' and not record.get('remote_state_action'))):
                return record
            if 'expected_updated_at' in data and data['expected_updated_at'] != record.get('updated_at', ''):
                raise HTTPException(409, '缺陷已被其他协作者更新，请刷新后重试')
            previous = record.get('remote_state')
            def before_write(target):
                record['remote_sync'] = dict(action=action, status='pending', target=target)
                record['updated_at'] = now()
                store._write(path, record)
            try:
                state = service.sync_regression_state(getattr(request.state, 'actor_owner', owner), record,
                                                      accepted=action == 'accept', before_write=before_write)
                record.update(remote_state=state, remote_state_action=action,
                              remote_sync=dict(action=action, status='success', target=state))
            except Exception as exc:
                # Once a write has started, a lost response must never enable blind replay.
                writing = record.get('remote_sync', {}).get('status') == 'pending'
                uncertain = writing and (not isinstance(exc, (ValueError, PingCodeError)) or
                                          isinstance(exc, PingCodeError) and exc.uncertain)
                record['remote_sync'] = {**record.get('remote_sync', {}), 'action': action,
                    'status': 'unknown' if uncertain else 'failed',
                    'error': str(exc) if isinstance(exc, (ValueError, PingCodeError)) else '同步响应中断，请刷新同步状态核对'}
            record['updated_at'] = now()
            record.setdefault('history', []).append(dict(at=now(), action='remote_' + action,
                previous=previous, value=record.get('remote_state'), result=record['remote_sync']['status'],
                actor=(request.state.user or {}).get('username', '')))
            store._write(path, record)
            return record

    @app.post(route + '/reopen')
    def reopen(request: Request, project_id: str, run_id: str, draft_id: str, data: dict = None):
        return sync_remote(request, project_id, run_id, draft_id, 'reopen', data or {})

    @app.post(route + '/accept')
    def accept(request: Request, project_id: str, run_id: str, draft_id: str, data: dict = None):
        return sync_remote(request, project_id, run_id, draft_id, 'accept', data or {})

    @app.post(route + '/refresh-state')
    def refresh_state(request: Request, project_id: str, run_id: str, draft_id: str):
        batches.assert_available(request, project_id, run_id, draft_id)
        owner = request.state.owner
        _, _, path = service.source(owner, project_id, run_id, draft_id)
        with service.record_lock(path):
            if not path.exists():
                return None
            record = store._read(path)
            if not record.get('item'):
                return record
            state = service.read_remote_state(getattr(request.state, 'actor_owner', owner), record)
            sync = record.get('remote_sync', {})
            target = sync.get('target') or record.get('remote_state')
            if target and target.get('id') == state['id']:
                record['remote_state'] = {**target, **{k: v for k, v in state.items() if v}}
                record['remote_state_action'] = sync.get('action') or record.get('remote_state_action')
                record['remote_sync'] = dict(action=record['remote_state_action'], status='success', target=target)
            elif target:
                record.pop('remote_state', None)
                record.pop('remote_state_action', None)
                record['remote_sync'] = dict(action=sync.get('action'), status='failed', target=target,
                    error='已核对远端尚未处于目标状态，可重新审核后重试')
            record['updated_at'] = now()
            record.setdefault('history', []).append(dict(at=now(), action='remote_refresh', value=state,
                actor=(request.state.user or {}).get('username', '')))
            store._write(path, record)
            return record

    @app.post(route + '/retry-content')
    def retry_content(request: Request, project_id: str, run_id: str, draft_id: str):
        batches.assert_available(request, project_id, run_id, draft_id)
        owner = request.state.owner
        _, _, path = service.source(owner, project_id, run_id, draft_id)
        with service.record_lock(path):
            record = store._read(path)
            if record.get('status') != 'submitted' or not record.get('item'):
                raise ValueError('只有已创建的缺陷可以补交正文与截图')
            if not (record.get('screenshot_error') or record.get('description_error')):
                return record
            cfg = service.config(getattr(request.state, 'actor_owner', owner), True)
            if any(cfg.get(k) != record['target'].get(k) for k in ('base_url', 'api_version')):
                raise ValueError('请切回原缺陷对应的 PingCode 连接后重试')
            token = service.token(cfg)
            item_id = identifier(record['item']['id'])
            noun = 'workitems' if cfg['api_version'] == 'pjm' else 'work_items'
            remote = service.request(cfg, 'GET', f'/v1/{cfg["api_version"]}/{noun}/{item_id}', token=token)
            description = record['payload']['description']
            report_url = record['source'].get('report_url', '')
            expected = description_html(description, report_url=report_url)
            normalize = lambda text: re.sub(r'\s+', '', ''.join(DescriptionContent(text).text)).replace('\ufeff', '')
            actual_text = normalize(remote.get('description', ''))
            if actual_text not in (normalize(expected), normalize(expected) + '【截图证据】'):
                raise ValueError('PingCode 正文已被修改，请先核对，避免覆盖他人的内容')
            inputs = record.get('screenshot_inputs')
            if inputs is None:
                inputs = [{k: shot[k] for k in ('content_type', 'content_base64')}
                          for shot in draft(request, project_id, run_id, draft_id)['screenshots']]
            shots = service.screenshots(inputs)
            if record.get('screenshot_error') and not shots:
                raise ValueError('未找到原截图，请在原缺陷中补充截图；不会重复创建缺陷')
            uploaded = record.setdefault('screenshots', [])
            # Older length-limit failures happened after all original files were uploaded.
            # Reuse those attachments only when title and byte size uniquely match.
            if shots and not uploaded and not record.get('screenshot_inputs'):
                attachments = service.collection(cfg, token, '/v1/attachments', {
                    'principal_type': 'workitem' if cfg['api_version'] == 'pjm' else 'work_item',
                    'principal_id': item_id})
                for shot in shots:
                    matches = [a for a in attachments if a.get('title') == shot['title']
                               and a.get('size') == len(shot['content'])]
                    if len(matches) != 1:
                        break
                    uploaded.append({'id': matches[0]['id'], 'title': shot['title'], 'url': ''})
            record['screenshot_inputs'] = inputs
            store._write(path, record)
            try:
                if shots:
                    expected, uploaded = service.add_screenshots(cfg, token, item_id, description, shots,
                        report_url=report_url, uploaded=uploaded, on_upload=lambda: store._write(path, record))
                else:
                    service.request(cfg, 'PATCH', f'/v1/{cfg["api_version"]}/{noun}/{item_id}',
                                    token=token, body={'description': checked_description(expected)})
                service.verify_description(cfg, token, item_id, expected)
                record['description_verified'] = True
                for key in ('description_error', 'screenshot_error', 'screenshot_inputs'):
                    record.pop(key, None)
                record.setdefault('history', []).append(dict(at=now(), action='retry_content',
                    actor=(request.state.user or {}).get('username', '')))
            except (ValueError, PingCodeError) as exc:
                record['description_verified'] = False
                record['screenshot_error'] = str(exc)
            record['updated_at'] = now()
            store._write(path, record)
            return record

    @app.post(route)
    def submit(request: Request, project_id: str, run_id: str, draft_id: str, data: dict):
        batches.assert_available(request, project_id, run_id, draft_id)
        owner = request.state.owner
        _, key, path = service.source(owner, project_id, run_id, draft_id)
        if data.get('reviewed') is not True:
            raise ValueError('请先人工审核，再确认提交')
        with service.record_lock(path):
            previous = store._read(path) if path.exists() else {}
            effective_previous = service.effective_record(owner, previous)
            if draft_id.startswith('finding-'):
                source_report = service.analysis_report(owner, project_id, run_id)
                if source_report.get('ui_snapshot'):
                    finding = source_report['findings'][int(draft_id.split('-')[1])]
                    if not any(c.get('case_id') == finding.get('case_id') and c.get('status') == 'failed' for c in source_report.get('imported_results', {}).get('cases', [])):
                        raise ValueError('当前用例不是不通过，不能把历史或更正记录作为当前缺陷提交')
            if service.triage_status(effective_previous) in {'rejected', 'deferred', 'pending_regression',
                                                   'regression_passed', 'regression_failed', 'result_corrected'}:
                raise ValueError('请先把缺陷状态改为待提交，再推送到 PingCode')
            if previous.get('status') == 'submitted':
                return previous
            if previous.get('status') in {'pending', 'unknown'}:
                raise HTTPException(409, '上次提交结果待核对，请先在 PingCode 核查，勿重复提交')
            payload = data.get('payload')
            screenshots = service.screenshots(data.get('screenshots'))
            allowed = {'project_id', 'type_id', 'title', 'description', 'priority_id', 'assignee_id', 'properties'}
            if not isinstance(payload, dict) or set(payload) - allowed:
                raise ValueError('缺陷内容格式无效')
            reference = service.report_reference(request, project_id, run_id, draft_id)
            if isinstance(payload.get('description'), str) and payload['description'].strip():
                payload = {**payload, 'description': with_report_reference(payload['description'], reference)}
            for field, limit in [('title', 300), ('description', 150000)]:
                if not isinstance(payload.get(field), str) or not payload[field].strip() or len(payload[field]) > limit:
                    raise ValueError(f'{field} 不能为空且不能超过 {limit} 个字符')
            if store.get_project(owner, project_id).get('test_kind') == 'ui':
                from .defect_title import validate_title
                validate_title(payload['title'])
            cfg = service.config(getattr(request.state, 'actor_owner', owner), True)
            token = service.token(cfg)
            pid = identifier(payload.get('project_id'))
            if pid not in {p['id'] for p in service.projects(cfg, token)}:
                raise ValueError('目标项目不可用')
            meta = service.metadata(cfg, token, pid, identifier(payload.get('type_id')))
            for field, choices in [('priority_id', meta['priorities']), ('assignee_id', meta['members'])]:
                if payload.get(field) and payload[field] not in {c['id'] for c in choices}:
                    raise ValueError('负责人或优先级不属于当前项目')
            props = payload.get('properties', {})
            if not isinstance(props, dict) or set(props) - {p['id'] for p in meta['properties']}:
                raise ValueError('自定义字段不属于当前缺陷类型')
            for prop in meta['properties']:
                value = payload.get(prop['id'], props.get(prop['id']))
                if (prop.get('required') or prop.get('is_required')) and value in (None, '', []):
                    raise ValueError('请填写必填字段：' + prop['name'])
            # Select IDs must belong to the selected project's current property options.
            for prop in meta['properties']:
                value = props.get(prop['id'])
                choices = prop.get('options')
                if value is not None and isinstance(choices, list) and choices:
                    valid = {o.get('_id', o.get('id')) for o in choices}
                    selected = value if isinstance(value, list) else [value]
                    if any(not isinstance(v, str) or v not in valid for v in selected):
                        raise ValueError('字段选项不属于当前项目：' + prop['name'])
            payload = Redactor().clean(payload)
            checked_description(description_html(payload['description'], report_url=reference['url']))
            screenshot_previews(payload['description'], screenshots, report_url=reference['url'])
            record = dict(status='pending', triage_status='pending_submission',
                          triage_reason=previous.get('triage_reason', ''),
                          created_at=previous.get('created_at', now()), updated_at=now(),
                          reviewer_session=getattr(request.state, 'actor_owner', owner)[:12],
                          reviewer=(request.state.user or {}).get('username', ''),
                          source=dict(project_id=project_id, run_id=run_id, draft_id=draft_id,
                                      report_url=reference['url'], case_id=reference['case_id']),
                          target=dict(base_url=cfg['base_url'], api_version=cfg['api_version'], project_id=pid),
                          screenshot_inputs=data.get('screenshots', []),
                          payload=payload, attempts=previous.get('attempts', 0) + 1,
                          history=previous.get('history', []))
            store._write(path, record)
            try:
                noun = 'workitems' if cfg['api_version'] == 'pjm' else 'work_items'
                expected_html = description_html(payload['description'], report_url=reference['url'])
                result = service.request(cfg, 'POST', '/v1/' + cfg['api_version'] + '/' + noun,
                                         token=token, body={**payload, 'description': expected_html})
                item = service.item(result)
                record.update(status='submitted', triage_status='submitted', triage_reason='', item=item,
                              description_error='正文与截图尚未完成核验，可重试补交')
                store._write(path, record)
                # The work item is already known at this point. Screenshot failures must
                # never cause a second defect to be created on retry.
                if screenshots:
                    try:
                        uploaded = record.setdefault('screenshots', [])
                        description, uploaded = service.add_screenshots(
                            cfg, token, item['id'], payload['description'], screenshots, report_url=reference['url'],
                            uploaded=uploaded, on_upload=lambda: store._write(path, record))
                        expected_html = description
                        record['screenshots'] = uploaded
                    except Exception as exc:
                        record['screenshot_error'] = str(exc) if isinstance(exc, PingCodeError) else '截图写入失败，请在 PingCode 中核对。'
                try:
                    service.verify_description(cfg, token, item['id'], expected_html)
                    record['description_verified'] = True
                    record.pop('description_error', None)
                except Exception:
                    record['description_verified'] = False
                    record['description_error'] = '描述或截图未通过保存后核验，请在 PingCode 核对；缺陷已创建，请勿重复提交。'
            except PingCodeError as exc:
                record.update(status='unknown' if exc.uncertain else 'failed', error=str(exc))
            except Exception:
                # A crash after sending cannot prove that the remote create failed.
                record.update(status='unknown', error='提交结果待核对，请先在 PingCode 按标题查询。')
            if record.get('status') == 'submitted' and not (record.get('screenshot_error') or record.get('description_error')):
                record.pop('screenshot_inputs', None)
            record['updated_at'] = now()
            store._write(path, record)
            return record

    @app.post(route + '/resolve')
    def resolve(request: Request, project_id: str, run_id: str, draft_id: str, data: dict):
        batches.assert_available(request, project_id, run_id, draft_id)
        _, key, path = service.source(request.state.owner, project_id, run_id, draft_id)
        with service.record_lock(path):
            record = store._read(path)
            if record['status'] not in {'pending', 'unknown'}:
                raise ValueError('当前记录无需核对')
            if data.get('confirmed_absent') is True:
                record.setdefault('history', []).append(dict(at=now(), action='human_confirmed_absent', attempt=record['attempts']))
                record.update(status='failed', error='人工已核对未创建，可重新审核提交', updated_at=now())
            else:
                cfg = service.config(getattr(request.state, 'actor_owner', request.state.owner), True)
                if any(cfg[k] != record['target'][k] for k in ('base_url', 'api_version')):
                    raise ValueError('请切回原提交目标的 PingCode 配置后核对')
                noun = 'workitems' if cfg['api_version'] == 'pjm' else 'work_items'
                result = service.request(cfg, 'GET', '/v1/' + cfg['api_version'] + '/' + noun + '/' + identifier(data.get('item_id')), token=service.token(cfg))
                legacy_match = 'api-test:' + key in str(result.get('description', ''))
                remote_project = result.get('project_id') or (result.get('project') or {}).get('id')
                content_match = (remote_project == record['target']['project_id']
                                 and result.get('title') == record['payload']['title']
                                 and result.get('description') == description_html(
                                     record['payload']['description'], report_url=record['source'].get('report_url', '')))
                if not (legacy_match or content_match):
                    raise ValueError('该工作项与本次提交的项目、标题或正文不一致，不能关联')
                record.update(status='submitted', triage_status='submitted', triage_reason='',
                              item=service.item(result), updated_at=now())
            store._write(path, record)
            return record

    # Reuse the same reviewed single-item operations in a durable background queue.
    from .pingcode_batches import DefectBatches, eligibility

    def execute_batch(request, job, item):
        pid, rid, did = item['project_id'], item['run_id'], item['draft_id']
        action = job['action']
        if action != 'refresh' and getattr(request.state, 'aggregate_context', None):
            store.project_reports.validate_item(request.state.owner, request.state.aggregate_context, item)
        if request.state.report_scope:
            request.state.report_scope = {**request.state.report_scope, 'project_id': pid, 'report_id': rid}
        _, _, path = service.source(request.state.owner, pid, rid, did)
        record = store._read(path) if path.exists() else None
        if action not in {'refresh', 'titles'} and item.get('expected_updated_at') is not None and item['expected_updated_at'] != (record or {}).get('updated_at', ''):
            return dict(outcome='failed', message='记录已变化，请重新审核后再操作')
        kind, explanation = eligibility(service.effective_record(request.state.owner, record), action)
        if action != 'titles' and kind != 'ready':
            return dict(outcome=kind, message=explanation,
                        record=service.record_summary(service.effective_record(request.state.owner, record)) if record else None)
        body = (batches.read_input(request.state.owner, item['input_id'], request.state.actor_owner)
                if item.get('input_id') else {})
        extra = {}
        if action in {'accept', 'reopen'}:
            record = sync_remote(request, pid, rid, did, action,
                                 {'expected_updated_at': (record or {}).get('updated_at', '')})
        elif action == 'refresh':
            record = refresh_state(request, pid, rid, did)
        elif action == 'retry-content':
            record = retry_content(request, pid, rid, did)
        elif action == '__submit__':
            record = submit(request, pid, rid, did, body)
        elif action == 'titles':
            from . import ui_retests, ui_report_corrections
            project = store.get_project(request.state.owner, pid)
            ui_retests.report(store, request.state.owner, project, rid)
            report = store._read(store.project_dir(request.state.owner, pid) / 'analyses' / rid / 'report.json')
            group = [member for member in job['items'] if member['outcome'] == 'running'
                     and (member['project_id'], member['run_id']) == (pid, rid)]
            # Preserve the existing atomic title update within each source report.
            for member in group:
                reviewed = batches.read_input(request.state.owner, member['input_id'], request.state.actor_owner)
                if reviewed != body:
                    raise ValueError('同一报告的标题属性或审核版本不一致，请重新审核')
            result = ui_report_corrections.save_titles(store, request.state.owner, pid, rid, report,
                [member['draft_id'] for member in group], body.get('attributes'), body.get('revision'),
                actor=(request.state.user or {}).get('username', ''))
            extra = dict(titles={value['draft_id']: value['title'] for value in result['values']},
                         correction_revision=result['revision'])
            record = None
        else:
            status = ('pending_regression' if record and record.get('item') else 'pending_submission') if action == 'restore' else action
            record = lifecycle(request, pid, rid, did,
                               dict(status=status, reason=job['reason'], expected_updated_at=(record or {}).get('updated_at', '')))
        outcome = 'success'
        message = {'accept': '已验收并同步', 'reopen': '原缺陷已重新打开', 'refresh': '已刷新同步状态',
                   'retry-content': '正文与截图已补交', '__submit__': '已提交', 'titles': '标题属性已保存'}.get(action, '处理状态已更新')
        if record:
            sync = record.get('remote_sync') or {}
            if record.get('status') in {'pending', 'unknown'} or sync.get('status') in {'pending', 'unknown'}:
                outcome, message = 'unknown', sync.get('error') or record.get('error') or '结果待核对'
            elif action in {'accept', 'reopen'} and (sync.get('status') == 'failed' or sync.get('action') != action):
                outcome, message = 'failed', sync.get('error') or '同步失败，请核对'
            elif action == '__submit__' and record.get('status') != 'submitted':
                outcome, message = 'failed', record.get('error') or '提交失败'
            elif action in {'__submit__', 'retry-content'} and (record.get('description_error') or record.get('screenshot_error')):
                outcome = 'unknown' if action == '__submit__' else 'failed'
                message = record.get('description_error') or record.get('screenshot_error')
        if request.state.report_scope:
            from . import report_collaboration
            report_collaboration.record(store, request.state.report_scope, (request.state.user or {}).get('username', ''))
        return dict(outcome=outcome, message=message,
                    record=service.record_summary(service.effective_record(request.state.owner, record)) if record else None, **extra)

    batches = DefectBatches(app, store, service, execute_batch)
    app.state.defect_batches = batches
    service.batches = batches
    batch_route = '/api/projects/{project_id}/reports/{run_id}/pingcode/batches'

    def validate_batch_report(request, project_id, run_id):
        project = store.get_project(request.state.owner, project_id)
        if (run_id != 'total' and run_id not in {r['id'] for r in project.get('runs', [])}
                and not store.has_saved_report(request.state.owner, project_id, run_id, kind='runs')
                and not service.has_analysis_report(request.state.owner, project, run_id)):
            raise FileNotFoundError('报告不存在')
        return request.state.owner

    @app.post(batch_route + '/inputs/{input_id}')
    def stage_batch_input(request: Request, project_id: str, run_id: str, input_id: str, data: dict):
        validate_batch_report(request, project_id, run_id)
        return batches.stage(request, input_id, data)

    @app.post(batch_route + '/jobs', status_code=202)
    def create_batch(request: Request, project_id: str, run_id: str, data: dict):
        validate_batch_report(request, project_id, run_id)
        return batches.create(request, project_id, run_id, data)

    @app.get(batch_route + '/jobs')
    def list_batches(request: Request, project_id: str, run_id: str):
        owner = validate_batch_report(request, project_id, run_id)
        return {'values': batches.list(owner, project_id, run_id)}

    @app.get(batch_route + '/jobs/{job_id}')
    def get_batch(request: Request, project_id: str, run_id: str, job_id: str):
        owner = validate_batch_report(request, project_id, run_id)
        return batches.get(owner, project_id, run_id, job_id)

    @app.post(batch_route + '/jobs/{job_id}/stop')
    def stop_batch(request: Request, project_id: str, run_id: str, job_id: str):
        owner = validate_batch_report(request, project_id, run_id)
        return batches.stop(owner, project_id, run_id, job_id)
