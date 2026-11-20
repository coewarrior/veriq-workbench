"""Private, per-browser storage for the web application.

Only the opaque session cookie crosses the browser boundary. Model credentials are
encrypted at rest and must be requested explicitly by trusted server code.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken

from . import database
from .document_limits import MAX_DOCUMENT_BYTES, DOCUMENT_LIMIT_LABEL


_OWNER_RE = re.compile(r"[0-9a-f]{64}\Z")
_COOKIE_RE = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_MAX_PROJECTS_PER_OWNER = 100
_MODEL_DEFAULTS = {
    "provider": "openai", "protocol": "openai_responses",
    "base_url": "https://api.openai.com/v1", "model": "",
    "max_tokens": None, "timeout": 90,
}
_SECRET_NAMES = {"api_key", "apikey", "authorization", "password", "secret", "key_ciphertext"}
_IMMUTABLE_METADATA = {"id", "filename", "document_file", "created_at", "updated_at", "owner"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """One Store instance should be shared by all application request threads."""

    def __init__(self, root: Path):
        self.root = Path(root).absolute()
        self._lock = threading.RLock()
        self._mkdir(self.root)
        self._mkdir(self.root / "sessions")
        key_path = self.root / "master.key"
        if key_path.is_symlink():
            raise ValueError("Invalid storage key path")
        with self._lock:
            try:
                fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                os.chmod(key_path, 0o600)
                key = key_path.read_bytes()
            else:
                key = Fernet.generate_key()
                with os.fdopen(fd, "wb") as handle:
                    handle.write(key)
                    handle.flush()
                    os.fsync(handle.fileno())
            self._cipher = Fernet(key)

    @staticmethod
    def _mkdir(path: Path) -> None:
        if path.is_symlink():
            raise ValueError("Invalid storage directory")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)

    @staticmethod
    def _read(path: Path) -> dict:
        if path.is_symlink():
            raise ValueError("Invalid storage file")
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError("Invalid stored data")
        return value

    @staticmethod
    def _write(path: Path, value: Any) -> None:
        # Prepare serialization before creating a temporary file, so malformed
        # updates can never replace a previously valid document.
        body = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        Store._write_text(path, body)

    @staticmethod
    def _write_text(path: Path, value: str) -> None:
        if path.is_symlink():
            raise ValueError("Invalid storage file")
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)

    def session(self, cookie_token: str | None) -> tuple[dict, str | None]:
        with self._lock:
            if isinstance(cookie_token, str) and _COOKIE_RE.fullmatch(cookie_token):
                owner = hashlib.sha256(cookie_token.encode("ascii")).hexdigest()
                location = self.root / "sessions" / owner
                if location.is_symlink():
                    raise ValueError("Invalid session directory")
                path = location / "session.json"
                if path.is_file():
                    stored = self._read(path)
                    if stored.get("id") == owner and isinstance(stored.get("csrf"), str):
                        return {"id": owner, "csrf": stored["csrf"]}, None
            token = secrets.token_urlsafe(32)
            owner = hashlib.sha256(token.encode("ascii")).hexdigest()
            location = self.root / "sessions" / owner
            self._mkdir(location)
            self._mkdir(location / "projects")
            session = {"id": owner, "csrf": secrets.token_urlsafe(32)}
            self._write(location / "session.json", {**session, "created_at": _now()})
            return session, token

    def _owner_dir(self, owner: str) -> Path:
        if not isinstance(owner, str) or not _OWNER_RE.fullmatch(owner):
            raise ValueError("Invalid session id")
        location = self.root / "sessions" / owner
        if location.is_symlink():
            raise ValueError("Invalid session directory")
        session_file = location / "session.json"
        if not session_file.is_file():
            raise PermissionError("Session does not exist")
        if self._read(session_file).get("id") != owner:
            raise PermissionError("Session does not exist")
        return location

    def _catalog(self, owner):
        path = self._owner_dir(owner) / "apis.json"
        if path.exists():
            catalog = self._read(path)
            if catalog.get("token_settings_version") != 2:
                self._migrate_output_settings(catalog)
                self._write(path, catalog)
            return catalog
        legacy = self._owner_dir(owner) / "model.json"
        old = self._read(legacy) if legacy.exists() else {}
        catalog = {"active_id": None, "items": {}}
        if old:
            pid = str(uuid4())
            catalog["active_id"] = pid
            catalog["items"][pid] = {**old, "name": old.get("model") or "原有 API 配置"}
        self._migrate_output_settings(catalog)
        self._write(path, catalog)
        legacy.unlink(missing_ok=True)
        return catalog

    @staticmethod
    def _migrate_output_settings(catalog):
        # The old UI forced these small budgets; preserve the prior number for rollback.
        for item in catalog["items"].values():
            value = item.get("max_tokens")
            if type(value) is int and 0 < value <= 16384:
                item["previous_max_tokens"] = value
                item["max_tokens"] = None
        catalog["token_settings_version"] = 2

    def _model(self, owner: str, profile_id=None) -> dict:
        catalog = self._catalog(owner)
        pid = profile_id or catalog["active_id"]
        if profile_id and pid not in catalog["items"]:
            raise FileNotFoundError("API 配置不存在")
        return catalog["items"].get(pid, {})

    def list_profiles(self, owner):
        with self._lock:
            catalog = self._catalog(owner)
            return {"active_id": catalog["active_id"], "items": [
                {"id": pid, "name": item["name"], **self._public_model(item)}
                for pid, item in catalog["items"].items()]}

    def select_profile(self, owner, pid):
        with self._lock:
            catalog = self._catalog(owner)
            if pid not in catalog["items"]:
                raise FileNotFoundError("API 配置不存在")
            catalog["active_id"] = pid
            self._write(self._owner_dir(owner) / "apis.json", catalog)
            return self.list_profiles(owner)

    def delete_profile(self, owner, pid):
        with self._lock:
            catalog = self._catalog(owner)
            if pid not in catalog["items"]:
                raise FileNotFoundError("API 配置不存在")
            del catalog["items"][pid]
            if catalog["active_id"] == pid:
                catalog["active_id"] = None
            self._write(self._owner_dir(owner) / "apis.json", catalog)
            return self.list_profiles(owner)

    def _public_model(self, stored: dict) -> dict:
        return {**{name: stored.get(name, default) for name, default in _MODEL_DEFAULTS.items()},
                "has_key": bool(stored.get("key_ciphertext"))}

    def get_model(self, owner: str, include_secret: bool = False, profile_id=None) -> dict:
        with self._lock:
            stored = self._model(owner, profile_id)
            result = self._public_model(stored)
            if include_secret:
                encrypted = stored.get("key_ciphertext")
                try:
                    result["api_key"] = self._cipher.decrypt(encrypted.encode("ascii")).decode("utf-8") if encrypted else ""
                except (InvalidToken, UnicodeError, AttributeError) as exc:
                    raise ValueError("Stored model credential cannot be decrypted") from exc
            return result

    def save_model(self, owner: str, config: dict, profile_id=None, name=None, create=False) -> dict:
        if not isinstance(config, dict):
            raise ValueError("Model configuration must be an object")
        display_name = name
        allowed = set(_MODEL_DEFAULTS) | {"api_key", "has_key"}
        if set(config) - allowed:
            raise ValueError("Unknown model configuration fields")
        with self._lock:
            stored = {} if create else self._model(owner, profile_id)
            merged = {name: config.get(name, stored.get(name, default)) for name, default in _MODEL_DEFAULTS.items()}
            for name in ("provider", "protocol", "base_url", "model"):
                value = merged[name]
                if not isinstance(value, str) or len(value) > 4096 or "\x00" in value:
                    raise ValueError(f"Invalid model {name}")
            tokens = merged["max_tokens"]
            if tokens is not None and (type(tokens) is not int or tokens <= 0):
                raise ValueError("max_tokens must be a positive integer or null (automatic)")
            timeout = merged["timeout"]
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 600:
                raise ValueError("Invalid model timeout")
            key = config.get("api_key", "")
            if not isinstance(key, str) or len(key) > 65536 or "\x00" in key:
                raise ValueError("Invalid API key")
            merged["key_ciphertext"] = self._cipher.encrypt(key.encode("utf-8")).decode("ascii") if key else stored.get("key_ciphertext", "")
            catalog = self._catalog(owner)
            if create and len(catalog["items"]) >= 30:
                raise ValueError("最多保存30套API配置")
            pid = str(uuid4()) if create else (profile_id or catalog["active_id"] or str(uuid4()))
            label = display_name if display_name is not None else stored.get("name", merged["model"] or "API 配置")
            if not isinstance(label, str) or not label.strip() or len(label) > 80:
                raise ValueError("配置名称需为1–80个字符")
            merged["name"] = label.strip()
            catalog["items"][pid] = merged
            if not catalog["active_id"] and len(catalog["items"]) == 1:
                catalog["active_id"] = pid
            self._write(self._owner_dir(owner) / "apis.json", catalog)
            return self._public_model(merged)

    def clear_model(self, owner: str) -> None:
        with self._lock:
            catalog = self._catalog(owner)
            if catalog["active_id"]:
                self.delete_profile(owner, catalog["active_id"])

    @staticmethod
    def _project_id(pid: str) -> str:
        if not isinstance(pid, str):
            raise ValueError("Invalid project id")
        try:
            parsed = UUID(pid)
        except (ValueError, AttributeError) as exc:
            raise ValueError("Invalid project id") from exc
        if str(parsed) != pid or parsed.version != 4:
            raise ValueError("Invalid project id")
        return pid

    def project_dir(self, owner: str, pid: str, *, include_deleted: bool = False) -> Path:
        with self._lock:
            parent = self._owner_dir(owner) / "projects"
            if parent.is_symlink():
                raise ValueError("Invalid projects directory")
            location = parent / self._project_id(pid)
            if location.is_symlink():
                raise ValueError("Invalid project directory")
            if not (location / "metadata.json").is_file():
                raise FileNotFoundError("Project does not exist")
            if not include_deleted and self._read(location / "metadata.json").get("deleted_at"):
                raise FileNotFoundError("Project is in the recycle bin")
            return location

    def is_account_owner(self, owner: str) -> bool:
        """Use the existing account directory, not a browser cookie or ID shape."""
        with database.connect(readonly=True) as db:
            return db.execute('SELECT 1 FROM accounts WHERE owner=%s', (owner,)).fetchone() is not None

    def _project_limit_reached(self, owner: str) -> bool:
        # This is the original anonymous-browser quota, not a cap on an
        # account's persistent history. Child rounds keep their own exemption.
        return (not self.is_account_owner(owner)
                and sum(not p.get('execution_round') for p in self.list_projects(owner)) >= _MAX_PROJECTS_PER_OWNER)

    def create_project(self, owner: str, title: str, filename: str, document_text: str, template: str | None = None, *, round_parent_id: str | None = None, aggregate: bool = False, _before_create=None) -> dict:
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError("Project title must contain 1–200 characters")
        if (not isinstance(filename, str) or not filename or len(filename) > 255
                or any(character in filename for character in ("/", "\\", "\x00"))
                or filename in (".", "..")):
            raise ValueError("Invalid document filename")
        extension = Path(filename).suffix.lower()
        if extension not in {".md", ".markdown", ".yaml", ".yml", ".json"}:
            raise ValueError("Document must be Markdown, YAML or JSON")
        if not isinstance(document_text, str) or not document_text.strip():
            raise ValueError("Document must not be empty")
        if len(document_text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise ValueError(f"单份文档不能超过 {DOCUMENT_LIMIT_LABEL}")
        if template is not None and (not isinstance(template, str) or len(template) > 100):
            raise ValueError("Invalid template")
        with self._lock:
            parent = self._owner_dir(owner) / "projects"
            if parent.is_symlink():
                raise ValueError("Invalid projects directory")
            if round_parent_id and self.get_project(owner, round_parent_id).get('test_kind') != 'ui':
                raise ValueError('独立轮次必须属于现有 UI 会话')
            if not aggregate and not round_parent_id and self._project_limit_reached(owner):
                raise ValueError(f"A browser session may contain at most {_MAX_PROJECTS_PER_OWNER} projects")
            pid = str(uuid4())
            location = parent / pid
            # Only the initiating server request supplies this callback. Persist
            # its idempotency marker after rejection checks, before any creation.
            if _before_create is not None:
                _before_create()
            self._mkdir(location)
            self._mkdir(location / "inputs")
            self._mkdir(location / "runs")
            relative_document = f"inputs/document{extension}"
            self._write_text(location / relative_document, document_text)
            timestamp = _now()
            metadata = {"id": pid, "title": title.strip(), "filename": filename,
                        "template": template, "created_at": timestamp, "updated_at": timestamp,
                        "status": "imported", "document_file": relative_document}
            if aggregate:
                metadata['business_project'] = True
            if round_parent_id:
                metadata['execution_round'] = {'parent_project_id': round_parent_id}
            self._write(location / "metadata.json", metadata)
            return metadata

    def get_project(self, owner: str, pid: str) -> dict:
        with self._lock:
            # Validate the owner/path normally, then use one current metadata
            # read for both deletion authority and the returned document.
            # Scheduling checks every linked session while holding its write
            # transaction; avoid duplicate file work without caching authority.
            location = self.project_dir(owner, pid, include_deleted=True)
            project = self._read(location / "metadata.json")
            if project.get("deleted_at"):
                raise FileNotFoundError("Project is in the recycle bin")
            return project

    def has_saved_report(self, owner: str, pid: str, rid: str, *, kind: str = 'analyses') -> bool:
        """History navigation is bounded; saved report ownership is not its list index."""
        if kind not in {'analyses', 'runs'}:
            return False
        try:
            rid = self._project_id(rid)
        except ValueError:
            return False
        root = self.project_dir(owner, pid) / kind
        folder = root / rid
        path = folder / ('report.json' if kind == 'analyses' else 'result.json')
        return not any(p.is_symlink() for p in (root, folder, path)) and path.is_file()

    def find_project_owner(self, pid: str) -> str:
        """Locate historical report storage; callers enforce report-scoped access."""
        project_id = self._project_id(pid)
        matches = []
        with self._lock:
            sessions = self.root / "sessions"
            for owner_dir in sessions.iterdir():
                if owner_dir.is_symlink() or not owner_dir.is_dir() or not _OWNER_RE.fullmatch(owner_dir.name):
                    continue
                metadata = owner_dir / "projects" / project_id / "metadata.json"
                if metadata.is_symlink() or not metadata.is_file():
                    continue
                project = self._read(metadata)
                if project.get("id") == project_id and not project.get("deleted_at"):
                    matches.append(owner_dir.name)
            if len(matches) != 1:
                raise FileNotFoundError("Project does not exist")
            return matches[0]

    def list_projects(self, owner: str, *, deleted: bool = False, include_business: bool = False) -> list:
        with self._lock:
            parent = self._owner_dir(owner) / "projects"
            if parent.is_symlink():
                raise ValueError("Invalid projects directory")
            projects = []
            for location in parent.iterdir():
                if location.is_symlink():
                    raise ValueError("Invalid project directory")
                if location.is_dir():
                    self._project_id(location.name)
                    path = location / "metadata.json"
                    if path.is_file():
                        project = self._read(path)
                        if bool(project.get("deleted_at")) == deleted and (include_business or not project.get("business_project")):
                            projects.append(project)
            return sorted(projects, key=lambda project: project["created_at"], reverse=True)

    def recycle_project(self, owner: str, pid: str, *, restore: bool = False) -> dict:
        with self._lock:
            location = self.project_dir(owner, pid, include_deleted=True)
            project = self._read(location / "metadata.json")
            if restore:
                if (project.get("deleted_at") and not project.get("execution_round") and not project.get('business_project')
                        and self._project_limit_reached(owner)):
                    raise ValueError("当前会话数量已达上限，请先删除一个会话再恢复")
                project.pop("deleted_at", None)
            else:
                project["deleted_at"] = _now()
            project["updated_at"] = _now()
            self._write(location / "metadata.json", project)
            return project

    def purge_projects(self, owner: str, project_ids: list[str]) -> list[str]:
        """Remove only explicitly selected recycled projects belonging to this owner."""
        if not isinstance(project_ids, list) or not project_ids or len(project_ids) > 1000:
            raise ValueError("请选择 1–1000 个回收站会话")
        with self._lock:
            locations = {}
            # Validate the entire selection before deleting anything. A restored
            # project or a foreign ID must not turn a stale selection into data loss.
            for pid in project_ids:
                location = self.project_dir(owner, pid, include_deleted=True)
                if not self._read(location / "metadata.json").get("deleted_at"):
                    raise ValueError("只能彻底删除回收站中的会话，请刷新后重试")
                locations[pid] = location
            for location in locations.values():
                shutil.rmtree(location)
            return list(locations)

    def invalidate_cases(self, owner: str, pid: str) -> None:
        with self._lock:
            location = self.project_dir(owner, pid)
            for name in ("bundle", "mcp-candidates"):
                path = location / self._asset_name(name)
                if path.exists():
                    if path.is_symlink():
                        raise ValueError("Invalid asset file")
                    path.replace(location / (name + ".previous.json"))

    @staticmethod
    def _safe_metadata(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str) or key.lower() in _SECRET_NAMES or key.startswith("_"):
                    raise ValueError("Metadata contains an unsupported field")
                if (key.endswith("_path") or key.endswith("_file")) and isinstance(child, str):
                    if Path(child).is_absolute() or ".." in Path(child).parts or "\\" in child:
                        raise ValueError("Metadata paths must be relative")
                Store._safe_metadata(child)
        elif isinstance(value, list):
            for child in value:
                Store._safe_metadata(child)
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("Metadata must be JSON serializable")

    def update_project(self, owner: str, pid: str, updates: dict) -> dict:
        if not isinstance(updates, dict) or set(updates) & _IMMUTABLE_METADATA:
            raise ValueError("Project identity fields cannot be changed")
        self._safe_metadata(updates)
        if "title" in updates and (not isinstance(updates["title"], str) or not updates["title"].strip() or len(updates["title"]) > 200):
            raise ValueError("Invalid project title")
        with self._lock:
            location = self.project_dir(owner, pid)
            metadata = self._read(location / "metadata.json")
            metadata.update(updates)
            metadata["updated_at"] = _now()
            self._write(location / "metadata.json", metadata)
            return metadata

    @staticmethod
    def _asset_name(name: str) -> str:
        if name not in ("contract", "bundle", "mcp-candidates", "model-plan", "deleted-cases", "requirement-design", "test-capabilities"):
            raise ValueError("Asset name must be contract or bundle")
        return name + ".json"

    def save_asset(self, owner: str, pid: str, name: str, value: dict) -> None:
        if not isinstance(value, dict):
            raise ValueError("Asset must be an object")
        filename = self._asset_name(name)
        with self._lock:
            self._write(self.project_dir(owner, pid) / filename, value)

    def load_asset(self, owner: str, pid: str, name: str) -> dict:
        filename = self._asset_name(name)
        with self._lock:
            return self._read(self.project_dir(owner, pid) / filename)
