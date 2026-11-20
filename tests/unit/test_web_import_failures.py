"""Rejected documents must not become broken projects selected on next visit."""
import json

import pytest
from fastapi.testclient import TestClient

from api_test_tool.web import create_app


@pytest.mark.parametrize("filename,content", [
    ("old-openapi.json", json.dumps({"swagger": "2.0", "info": {"title": "old"}, "paths": {}})),
    ("not-openapi.yaml", "project: My ordinary configuration\nfeatures: [one, two]\n"),
])
def test_parse_rejection_does_not_leave_an_unopenable_project(tmp_path, filename, content):
    app = create_app(tmp_path / "app", start_fixture=False, testing=True)
    with TestClient(app) as browser:
        bootstrap = browser.get("/api/bootstrap")
        browser.headers["x-csrf-token"] = bootstrap.json()["csrf"]
        rejected = browser.post("/api/projects", json={"filename": filename, "content": content})
        assert rejected.status_code == 400, rejected.text
        after = browser.get("/api/bootstrap").json()
        assert after["projects"] == [], "Failed parsing left a project whose contract cannot be read"
        assert list((tmp_path / "app").glob("sessions/*/projects/*/metadata.json")) == []


def test_zero_operation_markdown_keeps_visible_diagnostics_in_an_openable_project(tmp_path):
    app = create_app(tmp_path / "app", start_fixture=False, testing=True)
    with TestClient(app) as browser:
        browser.headers["x-csrf-token"] = browser.get("/api/bootstrap").json()["csrf"]
        imported = browser.post("/api/projects", json={"filename": "empty.md",
            "content": "# User API\n\nThis is prose without supported interface tables.\n"})
        assert imported.status_code == 200
        pid = imported.json()["project"]["id"]
        reopened = browser.get(f"/api/projects/{pid}")
        assert reopened.status_code == 200
        assert reopened.json()["contract"]["operations"] == {}
        assert any(issue["code"] == "NO_OPERATIONS" for issue in reopened.json()["contract"]["issues"])
