"""Per-account WeCom robot configuration and manual/automatic report delivery."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import requests
from fastapi import Request
from fastapi.responses import FileResponse

from . import database
from .network_transport import pinned_session
from .orchestration_storage import read_nodes, read_sections


class WeCom:
    def __init__(self, store):
        self.store = store

    def config(self, owner, private=False):
        path = self.store._owner_dir(owner) / 'wecom.json'
        saved = self.store._read(path) if path.exists() else {}
        result = {'configured': bool(saved.get('webhook_ciphertext')),
                  'auto_push': saved.get('auto_push', False) is True,
                  'report_base_url': saved.get('report_base_url', '')}
        if private:
            result['webhook'] = (self.store._cipher.decrypt(saved['webhook_ciphertext'].encode()).decode()
                                 if result['configured'] else '')
        return result

    def save(self, owner, data):
        if 'auto_push' in data and not isinstance(data['auto_push'], bool):
            raise ValueError('自动推送开关必须为开启或关闭')
        webhook = data.get('webhook', '')
        base = data.get('report_base_url', '')
        if not isinstance(webhook, str) or not isinstance(base, str):
            raise ValueError('请填写有效的 Webhook 和平台地址')
        webhook, base = webhook.strip(), base.strip().rstrip('/')
        if webhook:
            p = urlsplit(webhook)
            query = parse_qs(p.query)
            if (p.scheme != 'https' or p.netloc != 'qyapi.weixin.qq.com'
                    or p.path != '/cgi-bin/webhook/send' or p.fragment
                    or set(query) != {'key'} or len(query['key']) != 1
                    or len(webhook) > 2048 or any(c.isspace() for c in webhook)):
                raise ValueError('请填写企业微信群机器人的 HTTPS Webhook 地址')
        p = urlsplit(base)
        if (p.scheme not in {'http', 'https'} or not p.hostname or p.username or p.password
                or p.path or p.query or p.fragment or len(base) > 500
                or any(c.isspace() or c in '<>()[]' for c in base)):
            raise ValueError('请填写平台内网地址，例如 http://192.0.2.20:18089')
        with self.store._lock:
            old = self.config(owner, True)
            webhook = webhook or old['webhook']
            if not webhook:
                raise ValueError('请先填写机器人 Webhook')
            self.store._write(self.store._owner_dir(owner) / 'wecom.json', {
                'webhook_ciphertext': self.store._cipher.encrypt(webhook.encode()).decode(),
                'auto_push': data.get('auto_push', old['auto_push']),
                'report_base_url': base})
        return self.config(owner)

    def send(self, owner, content):
        return self._send_payload(owner, {'msgtype': 'markdown', 'markdown': {'content': content}})

    def _send_payload(self, owner, payload):
        cfg = self.config(owner, True)
        if not cfg['configured']:
            raise ValueError('请先在集成管理中配置企微机器人')
        try:
            with pinned_session('https://qyapi.weixin.qq.com', ()) as session:
                with session.post(cfg['webhook'], json=payload,
                                  timeout=(5, 15), allow_redirects=False, stream=True) as response:
                    raw = bytearray()
                    for chunk in response.iter_content(4096):
                        raw.extend(chunk)
                        if len(raw) > 65536:
                            raise ValueError('企微响应异常，请检查群消息后再重试')
                    data = json.loads(raw)
                    if response.status_code != 200 or not isinstance(data, dict) or data.get('errcode') != 0:
                        raise ValueError('企微未接受消息，请检查 Webhook 是否有效或稍后重试')
        except requests.RequestException:
            raise ValueError('企微连接失败或超时，请检查群消息后再重试，避免重复发送') from None
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError('企微响应异常，请检查群消息后再重试') from None
        return {'sent': True}

    def _ui_final(self, owner, project, snapshot):
        """Use executor settlement or an explicit direct finish for this revision."""
        final = project.get('ui_final_report') or {}
        intent = project.get('ui_finish_request') or {}
        if intent.get('execution_id') == snapshot.get('id') and (
                intent.get('revision') != snapshot.get('revision') or
                final.get('execution_id') != snapshot.get('id') or
                final.get('revision') != snapshot.get('revision')):
            return False
        with database.connect(readonly=True) as db:
            db.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            state = read_sections(db, ('leases',))
            state['nodes'] = read_nodes(db)
        held={l['node_id'] for l in state.get('leases',{}).values() if l.get('resource_hold') and l.get('executor_stopped')}
        if project.get('execution_route')=='local_browser' and any(n.get('owner')==owner and n.get('project_id')==project['id'] and not n.get('child_ids') and n['state'] not in {'completed','blocked','stopped'} and n['id'] not in held for n in state.get('nodes',{}).values()):return False
        nodes = [n for n in state.get('nodes', {}).values() if n.get('owner') == owner and
                 (n['id'] == project.get('managed_node_id') or
                  (n.get('record_project_id') == project['id'] and
                   n.get('record_execution_id') == snapshot.get('id')))]
        if nodes:
            return all(n.get('record_execution_id') == snapshot.get('id') and
                       (n['state'] in {'completed', 'blocked', 'stopped'} or n['id'] in held) for n in nodes)
        if project.get('managed_node_id'):
            return False
        if final:
            return (final.get('execution_id') == snapshot.get('id') and
                    final.get('revision') == snapshot.get('revision'))
        if project.get('execution_route')=='local_browser':return False
        cases = snapshot.get('cases', [])
        return bool(cases) and all(c.get('status') in {'passed', 'failed'} and
            all(p.get('status') in {'passed', 'failed'} for p in c.get('checkpoints', [])) for c in cases)

    def auto_report(self, owner, pid, rid, kind):
        """Only settled reports are delivered; intermediate saves stay local."""
        try:
            cfg = self.config(owner)
            if not cfg['configured'] or not cfg['auto_push']:
                return {'status': 'disabled'}
            project, saved = self._saved_report(owner, pid, rid, kind)
            snapshot = saved.get('ui_snapshot') or {}
            # API/load reports are saved by their finished execution. UI reports
            # are also saved during execution, so require the existing end signal.
            final = (self._ui_final(owner, project, snapshot) if snapshot
                     else project.get('test_kind') != 'ui')
            if not final:
                return {'status': 'skipped', 'reason': '任务尚未结束，不推送中间报告。'}
            delivery_id = rid
            if snapshot:
                # Exclude report revision, timestamps and defect editorial changes.
                # Resuming the same execution with new actual results gets a new final.
                results = [{k: c.get(k) for k in ('case_id', 'status', 'actual', 'not_run_reason')} |
                           {'checkpoints': [{k: p.get(k) for k in ('id', 'status', 'actual')}
                                            for p in c.get('checkpoints', [])]}
                           for c in snapshot.get('cases', [])]
                fingerprint = hashlib.sha256(json.dumps(
                    {'execution_id': snapshot.get('id'), 'cases': results},
                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                delivery_id += '-final-' + fingerprint
            path = self.store.project_dir(owner, pid) / 'wecom-deliveries' / f'{delivery_id}.json'
            metadata = {'report_id': rid, 'report_revision': saved.get('revision'),
                        'phase': 'final',
                        'created_at': datetime.now(timezone.utc).isoformat()}
            with self.store._lock:
                if path.exists():
                    return {**self.store._read(path), 'deduplicated': True}
                self.store._mkdir(path.parent)
                self.store._write(path, {**metadata, 'status': 'pending'})
            try:
                delivered = self.report(owner, pid, rid, kind)
                result = {'status': 'sent', **delivered}
            except Exception:
                # Do not retry uncertain delivery or expose webhook/remote errors.
                result = {'status': 'failed', 'message': '自动推送未确认成功，请核对群消息后手动推送。'}
            result = {**metadata, **result}
            self.store._write(path, result)
            return result
        except Exception:
            # Notification storage/config errors must not invalidate a saved report.
            return {'status': 'failed', 'message': '自动推送未完成，请核对配置和报告。'}

    def _saved_report(self, owner, pid, rid, kind):
        project = self.store.get_project(owner, pid)
        key = 'load_runs' if kind == 'load-reports' else 'analysis_reports'
        analysis = kind == 'reports' and rid in {r['id'] for r in project.get(key, [])}
        entries = project.get('analysis_reports', []) + project.get('runs', []) if kind == 'reports' else project.get('load_runs', [])
        if rid not in {r['id'] for r in entries}:
            raise FileNotFoundError('报告不存在')
        root = self.store.project_dir(owner, pid) / ('analyses' if analysis else 'runs') / rid
        saved = self.store._read(root / ('report.json' if analysis else 'result.json'))
        return project, saved

    def _report_card(self, owner, pid, rid, kind):
        project, saved = self._saved_report(owner, pid, rid, kind)
        title = str(saved.get('title') or project.get('title') or '测试报告')[:100]
        # Only display concise report labels, never the agent's task instructions.
        def literal(value, limit):
            return ' '.join(''.join(c for c in str(value) if c not in '[]()<>*`#').split())[:limit]
        title = literal(title, 100)
        title = re.sub(r'\s*[·|｜-]\s*\d{4}-\d{2}-\d{2}$', '', title) or '测试报告'
        counts = saved.get('imported_results', {}).get('counts') or saved.get('summary')
        if isinstance(counts, dict) and saved.get('imported_results', {}).get('counts'):
            counts = dict(counts)
            for key, alias in (('passed', 'PASS'), ('failed', 'FAIL')):
                if key not in counts and alias not in counts:
                    counts[key] = 0
        status, color, complete = '报告已生成', 'comment', False
        if isinstance(counts, dict):
            labels = [(('total',), '共'), (('passed', 'PASS'), '通过'), (('failed', 'FAIL'), '失败'),
                      (('partial',), '验证未完成'), (('blocked', 'BLOCKED'), '阻塞'), (('not_run',), '未执行'),
                      (('pending_rule',), '待确认规则'), (('pending_action',), '待人工操作'),
                      (('BROKEN',), '异常'), (('SKIP', 'skipped'), '跳过'),
                      (('QUARANTINED',), '隔离未执行'), (('UNSUPPORTED',), '不支持执行')]
            values = {label: next((counts[k] for k in keys if type(counts.get(k)) is int), None)
                      for keys, label in labels}
            complete = bool(values['共'] and sum(values[k] or 0 for k in ('通过', '失败')) == values['共']
                            and not any(v for k, v in values.items() if k not in {'共', '通过', '失败'}))
            summary = '，'.join(f'{label} {value}' + (' 条' if label == '共' else '')
                                for label, value in values.items()
                                if value is not None and (value or label in {'共', '通过', '失败'}))
            if values['失败'] and values['失败'] > 0:
                status, color = f"仍有 {values['失败']} 项失败", 'warning'
            elif values['异常'] and values['异常'] > 0:
                status, color = f"仍有 {values['异常']} 项异常", 'warning'
            elif (values['共'] and values['通过'] == values['共']
                  and not any(v for k, v in values.items() if k not in {'共', '通过'})):
                status, color = f"{values['共']} 项全部通过", 'info'
            elif any(v for k, v in values.items() if k not in {'共', '通过', '失败', '异常'}):
                status, color = '验证尚未完成', 'warning'
        else:
            summary = literal(counts or '报告已生成，请打开查看结果。', 300)
        pending_points = sum(p.get('status') not in {'passed', 'failed'}
                             for c in saved.get('ui_snapshot', {}).get('cases', [])
                             for p in c.get('checkpoints', []))
        if pending_points:
            complete = False
            summary += f'，另有 {pending_points} 个检查点未验证完成'
            if color == 'info':
                status, color = '验证尚未完成', 'warning'
        summary = summary or '报告已生成，请打开查看结果。'
        parts = re.split(r'\s*[·|｜]\s*', title, maxsplit=1)
        scope = parts[-1]
        scope = re.sub(r'(?:补测收尾|专项回归|缺陷回归|补测|回归|验收)(?:完成|收尾)?$', '', scope).strip()
        scope = scope or parts[-1]
        if len(parts) > 1 and re.search(r'回归|补测', parts[-1]):
            label = '缺陷回归' if '缺陷' in parts[-1] else '专项回归'
            title = f'{parts[0]} · {label}'
        recorded_at = saved.get('finished_at') or saved.get('updated_at') or saved.get('created_at')
        time_label = '完成时间' if saved.get('finished_at') or complete else '报告时间'
        try:
            instant = datetime.fromisoformat(recorded_at.replace('Z', '+00:00'))
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=timezone.utc)
        except (AttributeError, TypeError, ValueError):
            instant, time_label = datetime.now(timezone.utc), '推送时间'
        time_text = instant.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
        cases = saved.get('imported_results', {}).get('cases', [])
        environments = {c.get('environment') for c in cases if c.get('environment')}
        environment = next(iter(environments)) if len(environments) == 1 else ''
        environment_labels = {'test': '测试环境', 'prod': '生产环境', 'dev': '开发环境',
                              'pre': '预发环境', 'uat': 'UAT 环境', 'staging': '预发环境',
                              'qa': '测试环境', 'local': '本地环境'}
        context = environment_labels.get(environment, '')
        return {'title': title, 'status': status, 'color': color, 'scope': scope,
                'summary': summary, 'time_label': time_label, 'time_text': time_text,
                'context': context}

    def report(self, owner, pid, rid, kind, *, sender=None):
        card = self._report_card(owner, pid, rid, kind)
        sender = sender or owner
        base = self.config(sender)['report_base_url']
        url = f'{base}/api/projects/{pid}/{kind}/{rid}/index.html'
        # A single native text card keeps its report entry directly clickable.
        return self._send_payload(sender, {'msgtype': 'template_card', 'template_card': {
            'card_type': 'text_notice',
            'main_title': {'title': card['title']},
            'emphasis_content': {'title': card['status'], 'desc': card['context']},
            'quote_area': {'type': 0, 'quote_text': (
                f"测试范围：{card['scope']}\n执行结果：{card['summary']}\n"
                f"{card['time_label']}：{card['time_text']}（北京时间）")},
            'jump_list': [{'type': 1, 'title': '查看结果与复现步骤 →', 'url': url}],
            'card_action': {'type': 1, 'url': url}}})


def install_wecom(app, store, static):
    service = WeCom(store)
    app.state.wecom = service

    @app.get('/integrations/wecom')
    def page():
        return FileResponse(static / 'wecom.html', media_type='text/html')

    @app.get('/api/integrations/wecom')
    def config(request: Request):
        return service.config(request.state.owner)

    @app.put('/api/integrations/wecom')
    def save(request: Request, data: dict):
        return service.save(request.state.owner, data)

    @app.delete('/api/integrations/wecom')
    def clear(request: Request):
        with store._lock:
            (store._owner_dir(request.state.owner) / 'wecom.json').unlink(missing_ok=True)
        return service.config(request.state.owner)

    @app.post('/api/integrations/wecom/test')
    def test(request: Request):
        return service.send(request.state.owner, '### 测试平台通知\n企微机器人连接成功。')

    @app.post('/api/projects/{pid}/reports/{rid}/wecom')
    def push(request: Request, pid: str, rid: str):
        return service.report(request.state.owner, pid, rid, 'reports', sender=request.state.actor_owner)

    @app.post('/api/projects/{pid}/load-reports/{rid}/wecom')
    def push_load(request: Request, pid: str, rid: str):
        return service.report(request.state.owner, pid, rid, 'load-reports', sender=request.state.actor_owner)
