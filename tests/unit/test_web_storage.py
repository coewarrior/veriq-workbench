import hashlib
import json
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

try:
    from api_test_tool.web_storage import Store
except ModuleNotFoundError:
    from web_storage import Store


@pytest.fixture
def storage(tmp_path):
    store = Store(tmp_path / "data")
    session, token = store.session(None)
    return store, session["id"], token


def project(store, owner):
    return store.create_project(owner, "Example API", "example.yaml", "openapi: 3.0.3\n", "openapi")


def test_session_round_trip_without_raw_cookie_on_disk(storage):
    store, owner, token = storage
    first, refreshed = store.session(token)
    assert refreshed is None
    assert first["id"] == owner == hashlib.sha256(token.encode()).hexdigest()
    restored, refreshed = Store(store.root).session(token)
    assert restored == first and refreshed is None
    assert len(token) == 43 and first["csrf"] != token
    for path in store.root.rglob("*"):
        if path.is_file():
            assert token not in path.read_text()


@pytest.mark.parametrize("cookie", [None, "", "../x", "a" * 43, 12])
def test_unknown_cookie_is_replaced(storage, cookie):
    store, owner, _ = storage
    session, replacement = store.session(cookie)
    assert replacement is not None
    assert replacement != cookie and session["id"] != owner


def test_model_is_encrypted_and_public_view_never_returns_secret(storage):
    store, owner, _ = storage
    key = "a-demo-model-key-that-must-never-be-stored-in-plaintext"
    public = store.save_model(owner, {"model": "demo-model", "api_key": key})
    assert public["has_key"] is True
    assert "api_key" not in public and "key_ciphertext" not in public
    assert key not in json.dumps(public)
    assert store.get_model(owner) == public
    assert store.get_model(owner, include_secret=True)["api_key"] == key
    for path in store.root.rglob("*"):
        if path.is_file():
            assert key not in path.read_text()
    assert Store(store.root).get_model(owner, include_secret=True)["api_key"] == key
    assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
    assert stat.S_IMODE((store.root / "master.key").stat().st_mode) == 0o600


def test_empty_key_preserves_credential_and_clear_removes_it(storage):
    store, owner, _ = storage
    store.save_model(owner, {"api_key": "demo-key", "model": "first"})
    store.save_model(owner, {"api_key": "", "model": "second"})
    assert store.get_model(owner, True)["api_key"] == "demo-key"
    assert store.get_model(owner)["model"] == "second"
    store.clear_model(owner)
    assert not store.get_model(owner)["has_key"]
    assert store.get_model(owner, True)["api_key"] == ""


def test_model_configuration_validation_and_session_isolation(storage):
    store, owner, _ = storage
    second, _ = store.session(None)
    store.save_model(owner, {"api_key": "private-demo-key"})
    assert store.get_model(second["id"], True)["api_key"] == ""
    for invalid in ({"api_key": 12}, {"max_tokens": True}, {"timeout": -1}, {"max_tokens": 2.5}, {"model": []}, {"command": "exec"}):
        with pytest.raises(ValueError):
            store.save_model(owner, invalid)
    assert store.get_model(owner, True)["api_key"] == "private-demo-key"


def test_project_round_trip_with_confined_paths(storage):
    store, owner, _ = storage
    item = project(store, owner)
    directory = store.project_dir(owner, item["id"])
    assert item["document_file"] == "inputs/document.yaml"
    assert not Path(item["document_file"]).is_absolute()
    assert (directory / item["document_file"]).read_text() == "openapi: 3.0.3\n"
    assert store.get_project(owner, item["id"]) == item
    assert store.list_projects(owner) == [item]
    assert str(store.root) not in json.dumps(item)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE((directory / "metadata.json").stat().st_mode) == 0o600
    contract = {"operations": {"get_items": {"path": "/items"}}}
    store.save_asset(owner, item["id"], "contract", contract)
    assert store.load_asset(owner, item["id"], "contract") == contract


def test_cross_session_project_reads_and_writes_are_rejected(storage):
    store, owner, _ = storage
    item = project(store, owner)
    other, _ = store.session(None)
    for call in (
        lambda: store.get_project(other["id"], item["id"]),
        lambda: store.project_dir(other["id"], item["id"]),
        lambda: store.update_project(other["id"], item["id"], {"status": "wrong"}),
        lambda: store.save_asset(other["id"], item["id"], "bundle", {}),
        lambda: store.load_asset(other["id"], item["id"], "contract"),
    ):
        with pytest.raises(FileNotFoundError):
            call()
    assert store.list_projects(other["id"]) == []
    assert store.get_project(owner, item["id"])["status"] == "imported"


def test_project_read_checks_current_metadata_once_without_caching_authority(storage, monkeypatch):
    store, owner, _ = storage
    item = project(store, owner)
    directory = store.project_dir(owner, item["id"])
    original_read = store._read
    reads = []

    def read(path):
        reads.append(path)
        return original_read(path)

    monkeypatch.setattr(store, "_read", read)
    assert store.get_project(owner, item["id"]) == item
    assert reads.count(directory / "metadata.json") == 1
    assert reads.count(directory.parent.parent / "session.json") == 1

    # Both deletion and restoration must take effect on the next call, even
    # when this Store has just returned the prior document.
    store.recycle_project(owner, item["id"])
    reads.clear()
    with pytest.raises(FileNotFoundError, match="recycle bin"):
        store.get_project(owner, item["id"])
    assert reads.count(directory / "metadata.json") == 1
    store.recycle_project(owner, item["id"], restore=True)
    assert store.get_project(owner, item["id"])["id"] == item["id"]
    session_file = directory.parent.parent / "session.json"
    store._write(session_file, {"id": "different-owner"})
    with pytest.raises(PermissionError, match="Session does not exist"):
        store.get_project(owner, item["id"])


@pytest.mark.parametrize("body", ["{broken", "[]"])
def test_project_read_rejects_corrupted_metadata_after_success(storage, body):
    store, owner, _ = storage
    item = project(store, owner)
    directory = store.project_dir(owner, item["id"])
    assert store.get_project(owner, item["id"]) == item
    (directory / "metadata.json").write_text(body)
    with pytest.raises(ValueError):
        store.get_project(owner, item["id"])


def test_project_read_rejects_metadata_symlink(storage, tmp_path):
    store, owner, _ = storage
    item = project(store, owner)
    directory = store.project_dir(owner, item["id"])
    metadata = directory / "metadata.json"
    external = tmp_path / "external-metadata.json"
    external.write_text(json.dumps(item))
    metadata.unlink()
    metadata.symlink_to(external)
    with pytest.raises(ValueError, match="Invalid storage file"):
        store.get_project(owner, item["id"])


@pytest.mark.parametrize("bad", ["../escape.yaml", "/tmp/file.md", "..\\file.json", "doc.exe", "doc\x00.md"])
def test_document_filename_injection_is_rejected(storage, bad):
    store, owner, _ = storage
    with pytest.raises(ValueError):
        store.create_project(owner, "test", bad, "content")
    assert store.list_projects(owner) == []


def test_owner_project_asset_path_injection_and_immutable_metadata(storage):
    store, owner, _ = storage
    item = project(store, owner)
    for bad in ("../other", "/tmp/other", "..\\other", "x" * 64):
        with pytest.raises(ValueError):
            store.list_projects(bad)
        with pytest.raises(ValueError):
            store.project_dir(owner, bad)
        with pytest.raises(ValueError):
            store.load_asset(owner, item["id"], bad)
    with pytest.raises(PermissionError):
        store.list_projects("f" * 64)
    with pytest.raises(FileNotFoundError):
        store.get_project(owner, str(uuid4()))
    for update in ({"id": str(uuid4())}, {"document_file": "evil"}, {"owner": "evil"},
                   {"api_key": "secret"}, {"config": {"Authorization": "secret"}},
                   {"report_file": "/etc/passwd"}, {"_private": True}):
        with pytest.raises(ValueError):
            store.update_project(owner, item["id"], update)
    assert store.get_project(owner, item["id"]) == item


def test_atomic_updates_preserve_concurrent_distinct_fields(storage):
    store, owner, _ = storage
    item = project(store, owner)

    def update(number):
        store.update_project(owner, item["id"], {f"summary_{number}": number})
        # Every read must observe a complete JSON document, including while
        # other threads are replacing it.
        raw = (store.project_dir(owner, item["id"]) / "metadata.json").read_text()
        assert json.loads(raw)["id"] == item["id"]

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(update, range(60)))
    saved = store.get_project(owner, item["id"])
    assert all(saved[f"summary_{number}"] == number for number in range(60))
    with pytest.raises(ValueError):
        store.update_project(owner, item["id"], {"count": float("nan")})
    assert store.get_project(owner, item["id"]) == saved
    assert not list(store.root.rglob(".pending-*"))


def test_project_limit_is_atomic_under_concurrent_creation(storage):
    store, owner, _ = storage

    def create(number):
        try:
            return store.create_project(owner, f"API {number}", "doc.md", "# API")
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=12) as pool:
        values = list(pool.map(create, range(56)))
    assert sum(value is not None for value in values) == 50
    assert len(store.list_projects(owner)) == 50


def test_symlink_project_cannot_escape_storage(storage, tmp_path):
    store, owner, _ = storage
    external = tmp_path / "external"
    external.mkdir()
    (external / "metadata.json").write_text('{}')
    pid = str(uuid4())
    location = store.root / "sessions" / owner / "projects" / pid
    location.symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError):
        store.project_dir(owner, pid)
