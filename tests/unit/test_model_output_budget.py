"""Output budgets use provider capacity/defaults instead of an application token cap."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from api_test_tool.models import ModelConfig, ModelConfigError, _request, generate_text, validate_config
from api_test_tool.web_storage import Store
from api_test_tool.web import create_app

KEY = 'budget-fixture-not-a-real-key'


def config(protocol='openai_chat', model='private-model', tokens=None, base='https://example.com/v1'):
    return ModelConfig('custom', protocol, base, model, KEY, max_tokens=tokens)


@pytest.mark.parametrize('tokens', [32768, 128000, 384000, 1048576, 2000000])
@pytest.mark.parametrize('protocol,field', [('openai_chat','max_tokens'),('openai_responses','max_output_tokens'),('anthropic','max_tokens'),('gemini','maxOutputTokens')])
def test_manual_budget_is_sent_unchanged_above_old_limit(protocol, field, tokens):
    cfg = config(protocol, tokens=tokens)
    validate_config(cfg)
    payload = _request(cfg, 'system', 'user')[2]
    assert (payload['generationConfig'] if protocol == 'gemini' else payload)[field] == tokens


@pytest.mark.parametrize('name', ['deepseek-v4-flash','deepseek-v4-pro'])
def test_deepseek_auto_uses_published_capacity_instead_of_small_default(name):
    cfg = config(model=name)
    validate_config(cfg)
    assert _request(cfg, 'system', 'user')[2]['max_tokens'] == 384000
    assert _request(config(model=name, tokens=50000), 'system', 'user')[2]['max_tokens'] == 50000


@pytest.mark.parametrize('protocol,field', [('openai_chat','max_tokens'),('openai_responses','max_output_tokens'),('gemini','maxOutputTokens')])
def test_unknown_optional_budget_is_delegated_to_provider(protocol, field):
    payload = _request(config(protocol), 'system', 'user')[2]
    assert field not in (payload['generationConfig'] if protocol == 'gemini' else payload)


@pytest.mark.parametrize('tokens', [0,-1,True,'auto',1.5])
def test_invalid_manual_budget_is_rejected(tokens):
    with pytest.raises(ModelConfigError):
        validate_config(config(tokens=tokens))


@pytest.fixture
def provider():
    class Handler(BaseHTTPRequestHandler):
        def respond(self, data):
            raw = json.dumps(data).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self.server.calls.append(('GET', self.path))
            assert self.headers['x-api-key'] == KEY
            self.respond({'id':'private-model', 'max_tokens': self.server.capacity})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.calls.append(('POST', body))
            self.respond({'content':[{'type':'text', 'text':'OK'}], 'stop_reason':'end_turn'})

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    server.calls, server.capacity = [], 128000
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown(); server.server_close(); thread.join(2)


def test_anthropic_auto_discovers_required_max_tokens(provider):
    cfg = config('anthropic', base=f'http://127.0.0.1:{provider.server_port}/v1')
    assert generate_text(cfg,'system','user')['text'] == 'OK'
    assert provider.calls[0] == ('GET','/v1/models/private-model')
    assert provider.calls[1][1]['max_tokens'] == 128000
    assert len(provider.calls) == 2


def test_anthropic_missing_capacity_does_not_guess_or_send_paid_generation(provider):
    provider.capacity = None
    cfg = config('anthropic', base=f'http://127.0.0.1:{provider.server_port}/v1')
    with pytest.raises(ModelConfigError, match='手动填写'):
        generate_text(cfg,'system','user')
    assert len(provider.calls) == 1


def test_old_forced_budgets_migrate_once_without_changing_keys_or_profile_ids(tmp_path):
    store = Store(tmp_path)
    owner = store.session(None)[0]['id']
    saved = store.save_model(owner, {'provider':'deepseek','protocol':'openai_chat',
        'base_url':'https://api.deepseek.com/v1','model':'deepseek-v4-flash','api_key':KEY,'max_tokens':16384})
    path = store._owner_dir(owner)/'apis.json'
    old = store._read(path)
    profile_id = old['active_id']
    encrypted = old['items'][profile_id]['key_ciphertext']
    old.pop('token_settings_version')
    store._write(path,old)
    migrated = store.list_profiles(owner)
    assert migrated['active_id'] == profile_id
    assert migrated['items'][0]['max_tokens'] is None
    after = store._read(path)
    assert after['items'][profile_id]['key_ciphertext'] == encrypted
    assert after['items'][profile_id]['previous_max_tokens'] == 16384
    assert KEY not in path.read_text() and KEY not in json.dumps(migrated)
    # Explicit small budgets selected after the upgrade remain manual.
    store.save_model(owner, {'max_tokens':256},profile_id=profile_id)
    assert Store(tmp_path).get_model(owner)['max_tokens'] == 256
    assert store.get_model(owner,include_secret=True)['api_key'] == KEY


def test_web_profiles_save_automatic_and_large_manual_budgets(tmp_path):
    with TestClient(create_app(tmp_path,start_fixture=False,testing=True)) as client:
        client.headers['x-csrf-token'] = client.get('/api/bootstrap').json()['csrf']
        data = {'name':'Auto DeepSeek','provider':'deepseek','protocol':'openai_chat',
            'base_url':'https://api.deepseek.com/v1','model':'deepseek-v4-flash','api_key':KEY,'max_tokens':None}
        r = client.post('/api/apis',json=data)
        assert r.status_code == 200,r.text
        item = r.json()['items'][0]
        assert item['max_tokens'] is None and item['has_key']
        r = client.put('/api/apis/'+item['id'],json={**data,'api_key':'','max_tokens':2000000})
        assert r.status_code == 200,r.text
        assert r.json()['items'][0]['max_tokens'] == 2000000
        assert KEY not in r.text
        data['api_key'] = ''
        assert client.put('/api/apis/'+item['id'],json=data).json()['items'][0]['max_tokens'] is None
