import json
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
import requests
from fastapi.testclient import TestClient

from api_test_tool.web import create_app


WEBHOOK = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-only-key'
BASE = 'http://192.0.2.20:18089'


@pytest.fixture
def setup(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        bootstrap = client.get('/api/bootstrap').json()
        client.headers['x-csrf-token'] = bootstrap['csrf']
        owner = app.state.store.session(client.cookies['api_test_session'])[0]['id']
        yield app, client, owner


def test_config_encrypted_retained_and_isolated(setup):
    app, client, owner = setup
    endpoint = '/api/integrations/wecom'
    assert client.put(endpoint, json={'webhook': WEBHOOK, 'report_base_url': BASE}).json()['configured']
    path = app.state.store._owner_dir(owner) / 'wecom.json'
    assert 'test-only-key' not in path.read_text()
    assert WEBHOOK not in client.get(endpoint).text
    assert client.put(endpoint, json={'webhook': '', 'report_base_url': BASE}).status_code == 200
    assert app.state.wecom.config(owner, True)['webhook'] == WEBHOOK
    with TestClient(app) as other:
        assert not other.get(endpoint).json()['configured']
    assert client.delete(endpoint).json()['configured'] is False
    assert client.post(endpoint+'/test').status_code == 400


@pytest.mark.parametrize('url', ['http://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x',
    'https://qyapi.weixin.qq.com.evil.test/cgi-bin/webhook/send?key=x',
    'https://127.0.0.1/send?key=x', 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key='])
def test_invalid_webhook_and_csrf(setup, url):
    _, client, _ = setup
    assert client.put('/api/integrations/wecom', json={'webhook':url,'report_base_url':BASE}).status_code == 400
    client.headers.pop('x-csrf-token')
    assert client.post('/api/integrations/wecom/test').status_code == 403


def test_delivery_and_errors_are_sanitized(setup, monkeypatch):
    app, client, owner = setup
    app.state.wecom.save(owner, {'webhook': WEBHOOK, 'report_base_url': BASE})
    session = MagicMock()
    response = session.post.return_value.__enter__.return_value
    response.status_code = 200
    response.iter_content.return_value = [b'{"errcode":0}']
    @contextmanager
    def fake(*args):
        yield session
    monkeypatch.setattr('api_test_tool.wecom.pinned_session', fake)
    assert client.post('/api/integrations/wecom/test').json() == {'sent': True}
    assert session.post.call_args.kwargs['allow_redirects'] is False
    response.iter_content.return_value = [json.dumps({'errcode':93000,'errmsg':WEBHOOK}).encode()]
    failed = client.post('/api/integrations/wecom/test')
    assert failed.status_code == 400 and WEBHOOK not in failed.text
    session.post.side_effect = requests.Timeout(WEBHOOK)
    failed = client.post('/api/integrations/wecom/test')
    assert failed.status_code == 400 and 'test-only-key' not in failed.text


@pytest.mark.parametrize('kind,collection,folder,filename', [
    ('reports','analysis_reports','analyses','report.json'),
    ('reports','runs','runs','result.json'),
    ('load-reports','load_runs','runs','result.json')])
def test_report_push_uses_owned_saved_report(setup, monkeypatch, kind, collection, folder, filename):
    app, client, owner = setup
    store = app.state.store
    app.state.wecom.save(owner, {'webhook':WEBHOOK,'report_base_url':BASE})
    project = store.create_project(owner, '报告测试', 'test.md', '# test')
    pid, rid = project['id'], '11111111-1111-4111-8111-111111111111'
    store.update_project(owner, pid, {collection:[{'id':rid}]})
    root = store.project_dir(owner, pid) / folder / rid
    root.mkdir(parents=True)
    store._write(root / filename, {'title':'测试报告', 'summary':{'total':3,'PASS':2,'FAIL':1},
        **({'imported_results':{'counts':{'total':3,'passed':2,'failed':1}}} if collection=='analysis_reports' else {})})
    sent = []
    monkeypatch.setattr(app.state.wecom, '_send_payload', lambda owner, payload: sent.append(payload) or {'sent':True})
    path = f'/api/projects/{pid}/{kind}/{rid}/wecom'
    assert client.post(path).status_code == 200
    assert sent[0]['msgtype'] == 'template_card'
    card = sent[0]['template_card']
    assert card['card_type'] == 'text_notice'
    text = card['quote_area']['quote_text']
    assert '共 3 条' in text and '通过 2' in text and '失败 1' in text
    assert card['card_action']['url'] == f'{BASE}/api/projects/{pid}/{kind}/{rid}/index.html'
    assert card['jump_list'][0]['url'] == card['card_action']['url']
    with TestClient(app) as other:
        other.headers['x-csrf-token'] = other.get('/api/bootstrap').json()['csrf']
        assert other.post(path).status_code in {403,404}
    assert len(sent) == 1
    assert client.post(path.replace(rid, 'missing')).status_code == 404


def test_entries(setup):
    _, client, _ = setup
    page = client.get('/integrations/wecom').text
    assert 'wecom-config' in page
    assert 'id="wecom-back" data-integration-back href="/">← 返回上一页</a>' in page
    assert 'href="/integrations/pingcode">PingCode</a>' not in page
    assert '/integrations/wecom' in client.get('/ui-testing').text
    assert 'name="auto_push" type="checkbox" role="switch"' in page


def test_auto_push_config_is_boolean_persisted_and_defaults_to_manual(setup):
    app, client, owner = setup
    endpoint = '/api/integrations/wecom'
    assert client.get(endpoint).json()['auto_push'] is False
    data = {'webhook': WEBHOOK, 'report_base_url': BASE, 'auto_push': True}
    assert client.put(endpoint, json=data).json()['auto_push'] is True
    assert client.get(endpoint).json()['auto_push'] is True
    assert client.put(endpoint, json={'report_base_url': BASE}).json()['auto_push'] is True
    for value in ['false', 1, None]:
        assert client.put(endpoint, json={**data, 'auto_push': value}).status_code == 400
    with TestClient(app) as other:
        assert other.get(endpoint).json()['auto_push'] is False
    assert client.put(endpoint, json={**data, 'auto_push': False}).json()['auto_push'] is False


@pytest.mark.parametrize('kind,collection,folder,filename', [
    ('reports','analysis_reports','analyses','report.json'),
    ('reports','runs','runs','result.json'),
    ('load-reports','load_runs','runs','result.json')])
def test_automatic_delivery_once_manual_still_available(setup, monkeypatch, kind, collection, folder, filename):
    app, client, owner = setup
    service, store = app.state.wecom, app.state.store
    service.save(owner, {'webhook': WEBHOOK, 'report_base_url': BASE})
    project = store.create_project(owner, '报告', 'test.md', '# test')
    pid, rid = project['id'], '11111111-1111-4111-8111-111111111111'
    root = store.project_dir(owner, pid) / folder / rid
    root.mkdir(parents=True)
    store._write(root / filename, {'summary': {'PASS': 1}})
    store.update_project(owner, pid, {collection: [{'id': rid}]})
    sent = []
    monkeypatch.setattr(service, '_send_payload', lambda owner, payload: sent.append(payload) or {'sent': True})
    service.auto_report(owner, pid, rid, kind)
    assert sent == []
    service.save(owner, {'report_base_url': BASE, 'auto_push': True})
    assert sent == []  # Switching modes never sends old reports.
    service.auto_report(owner, pid, rid, kind)
    service.auto_report(owner, pid, rid, kind)
    assert len(sent) == 1
    assert client.post(f'/api/projects/{pid}/{kind}/{rid}/wecom').status_code == 200
    assert len(sent) == 2


def test_generated_report_triggers_auto_and_failure_does_not_fail_report(setup, monkeypatch):
    from api_test_tool.task_reports import save_task_report
    from api_test_tool.wecom import WeCom
    app, _, owner = setup
    store = app.state.store
    app.state.wecom.save(owner, {'webhook': WEBHOOK, 'report_base_url': BASE, 'auto_push': True})
    project = store.create_project(owner, '报告', 'test.md', '# test')
    calls = []
    def fail(self, owner, text):
        calls.append(text)
        raise requests.Timeout(WEBHOOK)
    monkeypatch.setattr(WeCom, '_send_payload', fail)
    result = save_task_report(store, owner, project, {'title': '报告', 'summary': '检查完成', 'sections': [], 'findings': []})
    rid = result['report']['id']
    root = store.project_dir(owner, project['id'])
    assert (root / 'analyses' / rid / 'index.html').exists()
    delivery = (root / 'wecom-deliveries' / f'{rid}.json').read_text()
    assert 'failed' in delivery and WEBHOOK not in delivery
    app.state.wecom.auto_report(owner, project['id'], rid, 'reports')
    assert len(calls) == 1
