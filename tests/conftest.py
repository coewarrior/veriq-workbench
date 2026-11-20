"""Storage tests use only the full-check runner's disposable PostgreSQL server."""
import pytest

from pg_support import PostgresDatabases


@pytest.fixture(autouse=True)
def postgres_database(monkeypatch, tmp_path):
    databases = PostgresDatabases(monkeypatch, tmp_path)
    databases.install()
    try:
        yield databases
    finally:
        databases.close()
