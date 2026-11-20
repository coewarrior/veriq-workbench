import hashlib

from fastapi.testclient import TestClient
from api_test_tool.web import create_app
from api_test_tool.task_reports import save_task_report


def client(app):
    return TestClient(app)


def enter(c, name='alice', password='example-password', action='register'):
    csrf = c.get('/api/auth/me').json()['csrf']
    return c.post('/api/auth/' + action, json={'username': name, 'password': password}, headers={'x-csrf-token': csrf})


def test_login_required_and_csrf(tmp_path):
    app = create_app(tmp_path, testing=True, start_fixture=False, auth_enabled=True)
    with client(app) as c:
        assert c.get('/', follow_redirects=False).status_code == 303
        api_entry = c.get('/api-testing', follow_redirects=False)
        assert api_entry.status_code == 303
        assert api_entry.headers['location'] == '/login?next=%2Fapi-testing'
        ui_entry = c.get('/ui-testing', follow_redirects=False)
        assert ui_entry.status_code == 303
        assert ui_entry.headers['location'] == '/login?next=%2Fui-testing'
        assert c.get('/api/bootstrap').status_code == 401
        assert c.get('/integrations/pingcode', follow_redirects=False).status_code == 303
        assert c.post('/api/auth/register', json={'username':'alice','password':'abcdef'}).status_code == 403
        csrf = c.get('/api/auth/me').json()['csrf']
        assert c.post('/api/auth/register', json={'username':'alice','password':'abcdef'}, headers={'x-csrf-token':csrf,'origin':'https://evil.example'}).status_code == 403
        assert enter(c).status_code == 200
        assert c.get('/').status_code == 200
        assert c.get('/api-testing').status_code == 200
        assert c.get('/ui-testing').status_code == 200
        assert c.get('/api/bootstrap').status_code == 200
        assert c.get('/api/auth/me').json()['user'] == {'username':'alice'}
        assert c.post('/api/auth/logout', json={}, headers={'x-csrf-token':csrf}).status_code == 403


def test_home_and_api_entry_keep_account_sessions(tmp_path):
    app = create_app(tmp_path, testing=True, start_fixture=False, auth_enabled=True)
    with client(app) as c:
        assert enter(c).status_code == 200
        csrf = c.get('/api/bootstrap').json()['csrf']
        template = c.get('/api/templates/items').json()
        created = c.post('/api/projects', json={
            'filename': template['filename'], 'content': template['content'],
        }, headers={'x-csrf-token': csrf}).json()['project']
        home = c.get('/')
        assert 'href="/api-testing"' in home.text
        assert '页面测试' in home.text and 'href="/ui-testing"' in home.text
        assert '暂未开放' not in home.text
        assert home.text.count('class="type-action induction-action"') == 2
        assert 'data-induction-label="进入 API 测试"' in home.text
        assert 'data-induction-label="进入页面测试"' in home.text
        assert 'id="project-list"' not in home.text
        workspace = c.get('/api-testing')
        assert 'id="project-list"' in workspace.text
        assert '← 全部测试' in workspace.text
        assert c.get('/api/bootstrap').json()['projects'][0]['id'] == created['id']
        assert c.get('/api/projects/' + created['id']).status_code == 200


def test_legacy_claim_same_account_on_second_browser_and_isolation(tmp_path, monkeypatch):
    app = create_app(tmp_path, testing=True, start_fixture=False, auth_enabled=True)
    # This checks account ownership migration, not public DNS availability.
    monkeypatch.setattr('api_test_tool.pingcode.check_public_endpoint', lambda *args: None)
    with client(app) as first, client(app) as second, client(app) as other:
        first.get('/api/auth/me')
        owner = hashlib.sha256(first.cookies['api_test_session'].encode()).hexdigest()
        store = app.state.store
        p = store.create_project(owner, '旧会话', 'demo.md', '# Demo')
        report = save_task_report(store, owner, p, {'title':'旧报告','summary':'保留内容'})
        url = report['report']['report_url']
        app.state.pingcode.save(owner, {'client_id':'example','client_secret':'private-secret'})
        from api_test_tool.mcp_access import MCPAccess
        mcp = MCPAccess(store)
        token = mcp.redeem(mcp.issue(owner)['code'])['token']
        assert first.get('/api/auth/me').json()['legacy_projects'] == 1
        assert enter(first).status_code == 200
        owned_report = first.get(url)
        assert owned_report.status_code == 200
        assert 'name="api-test-public-report"' not in owned_report.text
        assert enter(second, action='login').status_code == 200
        assert second.get(url).status_code == 200
        assert second.get('/api/bootstrap').json()['projects'][0]['id'] == p['id']
        cfg = second.get('/api/integrations/pingcode').json()
        assert cfg['configured'] and 'private-secret' not in str(cfg)
        assert enter(other, name='bob').status_code == 200
        assert other.get('/api/bootstrap').json()['projects'] == []
        shared = other.get(url)
        assert shared.status_code == 200
        assert 'name="api-test-public-report" content="read-only"' not in shared.text
        assert other.get(url.replace('index.html', 'report.json')).status_code == 200
        assert not other.get('/api/integrations/pingcode').json()['configured']
        assert mcp.authenticate(token) == owner
        csrf = first.get('/api/auth/me').json()['csrf']
        assert first.post('/api/auth/logout', json={}, headers={'x-csrf-token':csrf}).status_code == 200
        logged_out_report = first.get(url, follow_redirects=False)
        assert logged_out_report.status_code == 200
        assert 'name="api-test-public-report" content="login-required"' in logged_out_report.text
        assert '/static/pingcode.js?v=' in logged_out_report.text
        assert '/static/report-review.js?v=' in logged_out_report.text
        assert first.get(url.replace('index.html', 'report.json')).status_code == 401
        assert second.get(url).status_code == 200
        assert enter(first, action='login').status_code == 200
        assert first.get(url).status_code == 200
        with app.state.accounts.db(readonly=True) as db:
            stored = db.execute('SELECT username,owner,salt,password_hash FROM accounts').fetchall()
        assert stored and all('example-password' not in str(row) for row in stored)
        assert all(row['salt'] and row['password_hash'] != 'example-password' for row in stored)


def test_wrong_password_duplicate_and_revoked_cookie(tmp_path):
    app = create_app(tmp_path, testing=True, start_fixture=False, auth_enabled=True)
    with client(app) as first, client(app) as other:
        assert enter(first).status_code == 200
        assert enter(other).status_code == 409
        assert enter(other, password='incorrect', action='login').status_code == 401
        assert enter(other, password='tiny', action='login').status_code == 400
        assert enter(other, action='login').status_code == 200
        token = other.cookies['api_test_auth']
        csrf = other.get('/api/auth/me').json()['csrf']
        other.post('/api/auth/logout', json={}, headers={'x-csrf-token':csrf})
        other.cookies.set('api_test_auth', token)
        assert other.get('/api/bootstrap').status_code == 401
        other.cookies.clear()
        # Knowledge of the legacy browser cookie cannot claim a second account.
        other.cookies.set('api_test_session', first.cookies['api_test_session'])
        assert enter(other, name='eve').status_code == 409


def test_accounts_survive_restart(tmp_path):
    with client(create_app(tmp_path, testing=True, start_fixture=False, auth_enabled=True)) as c:
        assert enter(c).status_code == 200
    with client(create_app(tmp_path, testing=True, start_fixture=False, auth_enabled=True)) as c:
        assert enter(c, action='login').status_code == 200


def test_login_scene_loads_without_login_but_workspace_stays_private(tmp_path):
    app = create_app(tmp_path, testing=True, start_fixture=False, auth_enabled=True)
    with client(app) as c:
        assert c.get('/login').status_code == 200
        scene = c.get('/landing-pages/inner-green-3d.html')
        assert scene.status_code == 200
        assert hashlib.sha256(scene.content).hexdigest() == '69c3694bd63f44ef9f007ebe4dac57a83e4402e0cdf6b54dd10b96dd4f05e197'
        assert c.get('/landing-pages/inner-green-assets/three.min.js').status_code == 200
        assert c.get('/landing-pages/accounts.sqlite3').status_code == 404
        assert c.get('/api/bootstrap').status_code == 401
        assert c.get('/', follow_redirects=False).status_code == 303
