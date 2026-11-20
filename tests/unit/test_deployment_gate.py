import threading
from fastapi.testclient import TestClient
from api_test_tool.web import create_app


def test_deployment_blocks_new_mutations_but_preserves_reads(tmp_path, monkeypatch):
    drain = tmp_path / 'drain'
    monkeypatch.setenv('API_TEST_DRAIN_FILE', str(drain))
    app = create_app(tmp_path / 'data', start_fixture=False, testing=True)
    with TestClient(app) as client:
        boot = client.get('/api/bootstrap').json()
        client.headers['x-csrf-token'] = boot['csrf']
        drain.touch()
        response = client.post('/api/projects', json={'filename': 'sample.md', 'content': '# Sample'})
        assert response.status_code == 503
        assert response.headers['retry-after'] == '30'
        assert client.get('/api/bootstrap').status_code == 200
        status = client.get('/healthz').json()['deployment']
        assert status == {'draining': True, 'active_writes': 0, 'active_jobs': 0}
        drain.unlink()
        assert client.post('/api/projects', json={'filename': 'sample.md', 'content': '# Sample'}).status_code != 503


def test_deployment_waits_for_inflight_write(tmp_path, monkeypatch):
    monkeypatch.setenv('API_TEST_DRAIN_FILE', str(tmp_path / 'drain'))
    app = create_app(tmp_path / 'data', start_fixture=False, testing=True)
    entered, finish = threading.Event(), threading.Event()
    @app.post('/api/test-long-write')
    def long_write():
        entered.set()
        assert finish.wait(5)
        return {'ok': True}
    with TestClient(app) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        response = []
        worker = threading.Thread(target=lambda: response.append(client.post('/api/test-long-write')))
        worker.start()
        try:
            assert entered.wait(5)
            (tmp_path / 'drain').touch()
            assert client.get('/healthz').json()['deployment']['active_writes'] == 1
        finally:
            finish.set()
            worker.join(5)
        assert response[0].status_code == 200
        assert client.get('/healthz').json()['deployment']['active_writes'] == 0
