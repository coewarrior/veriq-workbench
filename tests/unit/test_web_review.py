"""Read-only review probes: no real network and no production changes."""
import json
import time

from fastapi.testclient import TestClient

from api_test_tool.web import create_app


def test_cookie_csrf_and_cross_session_access(tmp_path):
    app = create_app(tmp_path / 'data', start_fixture=False, testing=True)
    with TestClient(app) as first, TestClient(app) as other:
        a = first.get('/api/bootstrap')
        b = other.get('/api/bootstrap')
        assert a.status_code == b.status_code == 200
        acsrf, bcsrf = a.json()['csrf'], b.json()['csrf']
        assert acsrf != bcsrf
        assert 'HttpOnly' in a.headers['set-cookie']
        assert 'SameSite=strict' in a.headers['set-cookie']
        assert first.get('/api/bootstrap').json()['csrf'] == acsrf
        assert first.post('/api/projects', json={}).status_code == 403
        assert first.post('/api/projects', json={}, headers={'x-csrf-token':bcsrf}).status_code == 403
        assert first.post('/api/projects', json={}, headers={'x-csrf-token':acsrf,'origin':'https://evil.example'}).status_code == 403
        template = first.get('/api/templates/items').json()
        result = first.post('/api/projects', headers={'x-csrf-token':acsrf}, json={
            'title':'Review project', 'filename':template['filename'], 'content':template['content'], 'template':'items'})
        assert result.status_code == 200, result.text
        pid = result.json()['project']['id']
        assert other.get('/api/projects/' + pid).status_code == 404
        assert other.get(f'/api/projects/{pid}/artifacts/document').status_code == 404
        assert other.post(f'/api/projects/{pid}/generate', json={'mode':'baseline'},headers={'x-csrf-token':bcsrf}).status_code == 404
        started = first.post(f'/api/projects/{pid}/generate', json={'mode':'baseline'}, headers={'x-csrf-token':acsrf})
        assert started.status_code == 200, started.text
        jid = started.json()['id']
        assert other.get('/api/jobs/' + jid).status_code == 404
        for _ in range(100):
            job = first.get('/api/jobs/' + jid).json()
            if job['status'] in {'completed','failed'}:
                break
            time.sleep(.02)
        assert job['status'] == 'completed', job
        report = first.get(f'/api/projects/{pid}/case-report')
        assert report.status_code == 200
        assert '测试用例设计报告' in report.text
        assert other.get(f'/api/projects/{pid}/case-report').status_code == 404


def test_refs_and_oversized_documents_rejected_without_project_creation(tmp_path):
    app = create_app(tmp_path / 'data', start_fixture=False, testing=True)
    with TestClient(app) as client:
        csrf = client.get('/api/bootstrap').json()['csrf']
        headers = {'x-csrf-token':csrf}
        for reference in ('../../master.key', 'file:///etc/passwd', 'https://example.org/api.json', '//etc/passwd'):
            doc = {'openapi':'3.0.3','paths':{'/x':{'$ref':reference}}}
            result = client.post('/api/projects',headers=headers,json={'filename':'doc.json','content':json.dumps(doc)})
            assert result.status_code == 400, result.text
        result = client.post('/api/projects',headers=headers,json={'filename':'doc.md','content':'a'*50_000_001})
        assert result.status_code == 400
        assert client.get('/api/bootstrap').json()['projects'] == []


def test_untrusted_host_rejected(tmp_path):
    app = create_app(tmp_path / 'data', start_fixture=False, testing=True)
    with TestClient(app, base_url='http://evil.example') as client:
        assert client.get('/api/bootstrap').status_code == 400
