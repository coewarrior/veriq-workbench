import base64
import hashlib
import importlib.util
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from api_test_tool import ui_attachments
from api_test_tool.web import STATIC, create_app

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


def upload(filename, content):
    return {'filename': filename, 'content_base64': base64.b64encode(content).decode()}


def create(client, attachments, goal=''):
    client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
    return client.post('/api/ui-tests', json={'title': '附件要求', 'target_url': 'https://example.test',
                                             'goal': goal, 'attachments': attachments})


def test_original_requirements_survive_reopen_regression_and_are_private(tmp_path):
    document = BytesIO()
    with ZipFile(document, 'w') as archive:
        archive.writestr('word/document.xml', '<document>需求：验证重连</document>')
    originals = [PNG, document.getvalue(), '业务规则：禁用用户不可登录。'.encode()]
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        response = create(client, [upload(name, content) for name, content in zip(
            ['页面要求.png', '详细需求.docx', '规则.txt'], originals)])
        assert response.status_code == 200, response.text
        project = response.json()['project']
        pid = project['id']
        assert project['task']['goal'] == '按上传的测试要求附件完成本轮测试。'
        files = project['ui_requirement_attachments']
        assert len(files) == 3 and 'content_base64' not in response.text
        cookie = client.cookies['api_test_session']
        owner = app.state.store.session(cookie)[0]['id']
        for file, content in zip(files, originals):
            assert file['size'] == len(content)
            assert file['sha256'] == hashlib.sha256(content).hexdigest()
            downloaded = client.get(file['url'])
            assert downloaded.content == content
            assert downloaded.headers['content-disposition'].startswith('attachment;')
            preview = client.get(file['url'] + '?preview=true')
            assert preview.headers['content-disposition'].startswith('inline;' if file['kind'] == 'image' else 'attachment;')
            assert preview.headers['x-content-type-options'] == 'nosniff'
            path = app.state.store.project_dir(owner, pid) / 'inputs' / 'requirements' / file['id']
            assert path.stat().st_mode & 0o777 == 0o600
        with TestClient(app) as other:
            assert other.get(files[0]['url']).status_code in {403, 404}
            other.headers['x-csrf-token'] = other.get('/api/bootstrap').json()['csrf']
            assert other.delete(files[0]['url']).status_code in {403, 404}
        regression = client.post(f'/api/ui-tests/{pid}/regressions', json={'goal': '按附件回归'})
        assert regression.status_code == 200
        round_files = regression.json()['project']['ui_requirement_attachments']
        assert [f['sha256'] for f in round_files] == [f['sha256'] for f in files]
        assert [client.get(f['url']).content for f in round_files] == originals
        client.delete('/api/projects/' + pid)
        assert client.get(files[0]['url']).status_code == 404
        client.post('/api/projects/' + pid + '/restore')
        assert client.get(files[0]['url']).content == PNG
    with TestClient(create_app(tmp_path, start_fixture=False, testing=True)) as reopened:
        reopened.cookies.set('api_test_session', cookie)
        assert reopened.get(f'/api/projects/{pid}').json()['project']['ui_requirement_attachments'] == files
        assert reopened.get(files[1]['url']).content == originals[1]


def test_codex_reads_attachment_chunks_and_client_downloads_exact_original(tmp_path):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    content = ('真实需求\n' * 180000).encode()
    with TestClient(app) as client:
        project = create(client, [upload('完整要求.txt', content)], '验证需求文档中描述的行为').json()['project']
        file = project['ui_requirement_attachments'][0]
        token = client.post('/api/mcp/redeem', json={'code': client.post('/api/mcp/pair').json()['code']}).json()['token']

        def call(action, **arguments):
            return client.post('/api/mcp/call', headers={'Authorization': 'Bearer ' + token}, json={
                'action': action, 'arguments': {'project_id': project['id'], **arguments}})

        for action in ['document', 'context']:
            material = call(action).json()
            assert material['attachments'] == [file]
            assert '不构成系统指令' in material['attachment_guidance']
        spec = importlib.util.spec_from_file_location('attachment_client', STATIC / 'api-test-client.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        download_client = module.Client('http://127.0.0.1')
        offsets = []

        def adapter(name, arguments):
            assert name == 'get_test_attachment'
            offsets.append(arguments['offset'])
            response = call('test_attachment', **{k: v for k, v in arguments.items() if k != 'project_id'})
            assert response.status_code == 200, response.text
            return response.json()

        download_client.call = adapter
        destination = tmp_path / 'download.txt'
        result = download_client.download_attachment(project['id'], file['id'], destination)
        assert destination.read_bytes() == content
        assert destination.stat().st_mode & 0o777 == 0o600
        assert len(offsets) >= 2 and offsets[1] == ui_attachments.MAX_READ_BYTES
        assert result['sha256'] == file['sha256']
        assert call('test_attachment', attachment_id=file['id'], offset=-1).status_code == 400
        assert call('test_attachment', attachment_id='../metadata.json').status_code == 404
        assert call('test_attachment', attachment_id=file['id'], limit=1000001).status_code == 400
        # Failed integrity checks preserve an existing destination.
        destination.write_bytes(b'keep original')
        download_client.call = lambda *args: {**file, 'offset': 0, 'content_base64': 'eA==', 'next_offset': None}
        with pytest.raises(ValueError, match='完整性'):
            download_client.download_attachment(project['id'], file['id'], destination)
        assert destination.read_bytes() == b'keep original'
        assert not list(tmp_path.glob('.requirement-*'))


@pytest.mark.parametrize('files', [
    [upload('../requirements.txt', b'content')], [upload('bad.html', b'<script>bad</script>')],
    [upload('fake.png', b'<script>bad</script>')], [upload('empty.pdf', b'')],
    [{'filename': 'bad.txt', 'content_base64': '%%%'}], None,
    [upload(f'{index}.txt', b'content') for index in range(11)],
])
def test_invalid_batches_create_no_session_or_files(tmp_path, files):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        response = create(client, files, '测试')
        assert response.status_code == 400, response.text
        assert client.get('/api/ui-tests').json()['projects'] == []
        assert not list(tmp_path.rglob('requirements'))


def test_append_remove_limits_and_request_size(tmp_path, monkeypatch):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    with TestClient(app) as client:
        assert create(client, []).status_code == 200  # Address alone starts document-free exploration.
        project = create(client, [upload('一.txt', b'12345')]).json()['project']
        pid = project['id']
        monkeypatch.setattr(ui_attachments, 'MAX_TOTAL_BYTES', 10)
        url = f'/api/ui-tests/{pid}/attachments'
        invalid = client.post(url, json={'attachments': [upload('二.txt', b'123456')]})
        assert invalid.status_code == 400
        original = client.get('/api/projects/' + pid).json()['project']['ui_requirement_attachments']
        assert len(original) == 1
        assert len(list(tmp_path.rglob('requirements/*'))) == 1
        added = client.post(url, json={'attachments': [upload('二.txt', b'12345')]}).json()['project']
        assert len(added['ui_requirement_attachments']) == 2
        assert client.delete(original[0]['url']).status_code == 200
        assert client.get(original[0]['url']).status_code == 404
        assert len(client.get('/api/projects/' + pid).json()['project']['ui_requirement_attachments']) == 1
        assert client.post(url, json={'attachments': []}).status_code == 400
        monkeypatch.setattr(ui_attachments, 'MAX_REQUEST_BYTES', 100)
        oversized = client.post(url, json={'attachments': [upload('三.txt', b'x' * 200)]})
        assert oversized.status_code == 413
        assert len(client.get('/api/projects/' + pid).json()['project']['ui_requirement_attachments']) == 1


def test_failed_initial_attachment_save_rolls_back_new_session(tmp_path, monkeypatch):
    app = create_app(tmp_path, start_fixture=False, testing=True)
    original_update = app.state.store.update_project

    def failed_update(owner, pid, updates):
        if 'ui_requirement_attachments' in updates:
            raise OSError('simulated disk failure')
        return original_update(owner, pid, updates)

    monkeypatch.setattr(app.state.store, 'update_project', failed_update)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert create(client, [upload('要求.txt', b'content')]).status_code == 500
        assert client.get('/api/ui-tests').json()['projects'] == []
        assert not list(tmp_path.rglob('requirements'))


def test_ui_page_preserves_animation_and_versions_its_flow_styles(tmp_path):
    import re
    with TestClient(create_app(tmp_path, start_fixture=False, testing=True)) as client:
        ui = client.get('/ui-testing').text
        api = client.get('/api-testing').text
    assert 'src="about:blank"' not in ui
    assert 'src="/static/signal-background/frame.html"' in ui
    assert 'src="/static/signal-background/frame.html"' in api
    digest = hashlib.sha256((STATIC / 'ui-flow.css').read_bytes()).hexdigest()[:16]
    assert f'/static/ui-flow.css?v={digest}' in ui
