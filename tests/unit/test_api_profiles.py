import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from api_test_tool.web import create_app
from api_test_tool.web_storage import Store


def config(name='First', key='test-key-alpha'):
    return dict(name=name, provider='custom', protocol='openai_chat', base_url='https://example.com/v1', model='model-a', api_key=key, max_tokens=6000, timeout=90)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, start_fixture=False, testing=True)) as c:
        boot = c.get('/api/bootstrap').json()
        c.headers['X-CSRF-Token'] = boot['csrf']
        yield c


def add(c, name='First', key='test-key-alpha'):
    result = c.post('/api/apis', json=config(name, key))
    assert result.status_code == 200, result.text
    assert key not in result.text and 'key_ciphertext' not in result.text
    return next(a['id'] for a in result.json()['items'] if a['name'] == name)


def test_multiple_profiles_select_edit_delete_isolated(client):
    first = add(client)
    second = add(client, 'Second', 'test-key-beta')
    assert client.get('/api/apis').json()['active_id'] == first
    assert client.post(f'/api/apis/{second}/select').status_code == 200
    changed = config('Renamed', '')
    changed['model'] = 'model-b'
    response = client.put(f'/api/apis/{second}', json=changed)
    assert response.status_code == 200
    assert response.json()['active_id'] == second
    assert next(a for a in response.json()['items'] if a['id'] == second)['has_key']
    changed['base_url'] = 'https://another.example/v1'
    assert client.put(f'/api/apis/{second}', json=changed).status_code == 400
    assert client.delete(f'/api/apis/{second}').json()['active_id'] is None
    assert len(client.get('/api/apis').json()['items']) == 1
    assert client.post(f'/api/apis/{second}/select').status_code == 404
    assert client.get('/api/bootstrap').json()['model']['has_key'] is False
    with TestClient(client.app) as stranger:
        stranger.headers['X-CSRF-Token'] = stranger.get('/api/bootstrap').json()['csrf']
        assert stranger.get('/api/apis').json()['items'] == []
        assert stranger.put(f'/api/apis/{first}', json=config()).status_code == 404
        assert stranger.delete(f'/api/apis/{first}').status_code == 404
        assert stranger.post(f'/api/apis/{first}/test').status_code == 404


def test_session_api_choices_survive_global_switch(client):
    first = add(client)
    second = add(client, 'Second', 'test-key-beta')
    data = client.get('/api/templates/items').json()
    project = client.post('/api/projects', json={**data, 'template':'items'}).json()['project']
    assert project['api_profile_id'] == first
    client.post(f'/api/apis/{second}/select')
    details = client.get('/api/projects/'+project['id']).json()
    assert details['project']['api_profile_id'] == first
    response = client.put('/api/projects/'+project['id']+'/api', json={'api_profile_id':second})
    assert response.status_code == 200 and response.json()['api_profile_id'] == second
    assert client.put('/api/projects/'+project['id']+'/api', json={'api_profile_id':'not-owned'}).status_code == 404
    client.delete(f'/api/apis/{second}')
    # No silent fallback to a different provider after deletion.
    result = client.post('/api/projects/'+project['id']+'/generate',json={'mode':'model'})
    assert result.status_code == 404
    assert client.get('/api/projects/'+project['id']).status_code == 200


def test_legacy_key_migrates_once_without_plaintext_or_loss(tmp_path):
    store = Store(tmp_path)
    session, _ = store.session(None)
    owner = session['id']
    secret = 'old-provider-key-private'
    original = config()
    original.pop('name'); original.pop('api_key')
    original['key_ciphertext'] = store._cipher.encrypt(secret.encode()).decode()
    legacy = store._owner_dir(owner) / 'model.json'
    store._write(legacy, original)
    catalog = store.list_profiles(owner)
    assert len(catalog['items']) == 1
    assert not legacy.exists()
    assert secret not in json.dumps(catalog)
    assert secret not in (store._owner_dir(owner)/'apis.json').read_text()
    restarted = Store(tmp_path)
    assert restarted.list_profiles(owner) == catalog
    assert restarted.get_model(owner, include_secret=True)['api_key'] == secret
    restarted.delete_profile(owner,catalog['active_id'])
    assert restarted.list_profiles(owner)['items'] == []


def test_new_profile_never_inherits_existing_key(client):
    add(client)
    assert client.post('/api/apis',json=config('Second','')).status_code == 400
    assert len(client.get('/api/apis').json()['items']) == 1
