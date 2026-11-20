"""Platform account directory. Workspace files retain their original owner IDs."""
import hashlib
import hmac
import re
import secrets
import time
from contextlib import contextmanager

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from . import database


class Accounts:
    def __init__(self, store):
        self.store = store
        database.ensure_schema()
        self.attempts = {}

    @contextmanager
    def db(self, *, readonly=False):
        with database.connect(readonly=readonly, rows=True) as db:
            if not readonly:
                # Concurrent expired-login cleanup and logout must not turn a
                # completed row deletion into a repeatable-read write conflict.
                db.execute('BEGIN ISOLATION LEVEL READ COMMITTED READ WRITE')
                database.require_active(db)
            yield db

    @staticmethod
    def hash_password(password, salt):
        return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def authenticate(self, token):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            return None
        with self.db(readonly=True) as db:
            row = db.execute('SELECT a.username,a.owner FROM logins l JOIN accounts a USING(username) WHERE l.digest=%s AND l.expires>%s', (self.digest(token), time.time())).fetchone()
        return dict(row) if row else None

    def claimed(self, owner):
        return self.store.is_account_owner(owner)

    def enter(self, username, password, owner, register=False):
        if not isinstance(username, str) or not isinstance(password, str):
            raise HTTPException(400, '请填写账号和密码')
        username = username.strip().lower()
        if not re.fullmatch(r'[a-z0-9_.-]{3,32}', username) or not 6 <= len(password) <= 128:
            raise HTTPException(400, '账号为 3–32 位字母、数字、点、横线或下划线；密码为 6–128 位')
        with self.db() as db:
            if register:
                salt = secrets.token_hex(16)
                hashed = self.hash_password(password, salt)
                try:
                    db.execute('INSERT INTO accounts (username,owner,salt,password_hash) VALUES (%s,%s,%s,%s)', (username, owner, salt, hashed))
                except database.IntegrityError:
                    raise HTTPException(409, '账号已存在，或当前工作空间已绑定账号；请登录') from None
            else:
                row = db.execute('SELECT * FROM accounts WHERE username=%s', (username,)).fetchone()
                salt = row['salt'] if row else '00' * 16
                hashed = self.hash_password(password, salt)
                if not row or not hmac.compare_digest(hashed, row['password_hash']):
                    raise HTTPException(401, '账号或密码不正确')
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM logins WHERE expires<=%s', (time.time(),))
            db.execute('INSERT INTO logins (digest,username,expires) VALUES (%s,%s,%s)', (self.digest(token), username, time.time() + 30 * 86400))
        return token, username

    def logout(self, token):
        if token:
            with self.db() as db:
                db.execute('DELETE FROM logins WHERE digest=%s', (self.digest(token),))


def install_accounts(app, store, static, enabled):
    accounts = Accounts(store)
    app.state.accounts = accounts

    @app.get('/login')
    def login_page():
        return FileResponse(static / 'login.html', media_type='text/html')

    @app.get('/api/auth/me')
    def me(request: Request):
        user = request.state.user
        legacy = request.state.browser_owner
        return {'enabled': enabled, 'user': {'username': user['username']} if user else None,
                'csrf': request.state.csrf,
                'legacy_projects': len(store.list_projects(legacy)) if not user and not accounts.claimed(legacy) else 0}

    @app.post('/api/auth/{action}')
    def auth_action(request: Request, action: str, data: dict):
        if action == 'logout':
            accounts.logout(request.cookies.get('api_test_auth'))
            response = JSONResponse({'ok': True})
            response.delete_cookie('api_test_auth')
            response.delete_cookie('api_test_session')
            return response
        if action not in {'login', 'register'}:
            raise HTTPException(404, '操作不存在')
        if request.state.user:
            raise HTTPException(409, '请先退出当前账号')
        # A small per-client throttle, not an account lockout.
        client = request.client.host if request.client else 'unknown'
        with store._lock:
            attempts = [t for t in accounts.attempts.get(client, []) if t > time.time() - 300]
            if len(attempts) >= 20:
                raise HTTPException(429, '尝试次数较多，请 5 分钟后重试')
            accounts.attempts[client] = attempts + [time.time()]
        token, username = accounts.enter(data.get('username'), data.get('password'), request.state.browser_owner, action == 'register')
        with store._lock:
            accounts.attempts.pop(client, None)
        # Rotate this browser's CSRF token after changing identity.
        with store._lock:
            path = store._owner_dir(request.state.browser_owner) / 'session.json'
            session = store._read(path)
            session['csrf'] = secrets.token_urlsafe(32)
            store._write(path, session)
        response = JSONResponse({'ok': True, 'username': username})
        response.set_cookie('api_test_auth', token, httponly=True, samesite='strict', secure=request.url.scheme == 'https', max_age=30 * 86400)
        return response
    return accounts
