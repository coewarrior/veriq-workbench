"""Browser-authorized, revocable credentials for the MCP workflow only."""
import hashlib
import re
import secrets
import time


class MCPAccess:
    def __init__(self, store):
        self.store = store

    def _path(self, owner):
        return self.store._owner_dir(owner) / "mcp-access.json"

    def _read(self, owner):
        path = self._path(owner)
        return self.store._read(path) if path.exists() else {}

    @staticmethod
    def _digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def issue(self, owner, *, project_ids=None, actor=''):
        with self.store._lock:
            data = self._read(owner)
            code = owner + "." + secrets.token_urlsafe(32)
            if project_ids is None:
                data.update(pair_digest=self._digest(code), pair_expires=time.time() + 600)
            else:
                for pid in project_ids:
                    self.store.get_project(owner, pid)
                pairs = [r for r in data.get('pairs', []) if r['expires'] > time.time()]
                data['pairs'] = pairs[-29:] + [{'digest': self._digest(code), 'expires': time.time() + 600,
                                               'project_ids': project_ids, 'actor': actor}]
            self.store._write(self._path(owner), data)
            return {"code": code, "expires_in": 600}

    def _resolve(self, value, purpose):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}\.[A-Za-z0-9_-]{43}", value):
            raise PermissionError("MCP 凭据无效，请在网页重新连接 Codex")
        owner = value.split(".")[0]
        try:
            data = self._read(owner)
        except (FileNotFoundError, PermissionError):
            raise PermissionError("MCP 凭据无效，请在网页重新连接 Codex") from None
        records = ([{"digest": data.get("token_digest", ""), "expires": data.get("token_expires", 0)}]
                   + data.get("tokens", [])) if purpose == "token" else [
                       {"digest": data.get("pair_digest", ""), "expires": data.get("pair_expires", 0)},
                       *data.get('pairs', [])]
        record = next((r for r in records if r['expires'] > time.time()
                       and secrets.compare_digest(r['digest'], self._digest(value))), None)
        if record is None:
            raise PermissionError("MCP 凭据过期或已撤销，请在网页重新连接 Codex")
        return owner, data, record

    def redeem(self, code):
        with self.store._lock:
            owner, data, pair = self._resolve(code, "pair")
            records = [r for r in data.get("tokens", []) if r["expires"] > time.time()]
            if data.get("token_expires", 0) > time.time():
                records.append({"digest": data["token_digest"], "expires": data["token_expires"]})
            if len(records) >= 30:
                raise ValueError("此工作空间已有 30 个连接，请先在连接管理撤销旧连接")
            token = owner + "." + secrets.token_urlsafe(32)
            if 'project_ids' in pair:
                data['pairs'] = [r for r in data.get('pairs', []) if r['digest'] != pair['digest']]
            else:
                data.pop("pair_digest", None)
                data.pop("pair_expires", None)
            data.pop("token_digest", None)
            data.pop("token_expires", None)
            scope = {key: pair[key] for key in ('project_ids', 'actor') if key in pair}
            data["tokens"] = records + [{"digest": self._digest(token), "expires": time.time() + 180 * 86400, **scope}]
            data["last_seen_at"] = time.time()
            self.store._write(self._path(owner), data)
            return {"token": token}

    def authenticate(self, token):
        return self.authentication(token)['owner']

    def authentication(self, token):
        with self.store._lock:
            owner, data, record = self._resolve(token, "token")
            data["last_seen_at"] = time.time()
            self.store._write(self._path(owner), data)
            return {'owner': owner, **{key: record[key] for key in ('project_ids', 'actor') if key in record}}

    def status(self, owner):
        with self.store._lock:
            data = self._read(owner)
            connected = data.get("token_expires", 0) > time.time() or any(r["expires"] > time.time() for r in data.get("tokens", []))
            last_seen = data.get("last_seen_at", 0)
            return {"connected": connected, "active": bool(connected and time.time() - last_seen < 120),
                    "last_seen_at": last_seen if connected else None}

    def revoke(self, owner):
        with self.store._lock:
            self.store._write(self._path(owner), {})
        return {"connected": False}
