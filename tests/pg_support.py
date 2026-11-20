"""PostgreSQL fixtures only; never a runtime SQLite compatibility backend."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import copy
import os
from pathlib import Path
import threading
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row, tuple_row


class ObservedConnection:
    """Observe SQL structure without logging bound credentials or result bodies."""
    def __init__(self, connection, observe):
        self.connection, self.observe = connection, observe

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def execute(self, statement, *args, **kwargs):
        self.observe(statement)
        return self.connection.execute(statement, *args, **kwargs)


def observe(connection, callback):
    return ObservedConnection(connection, callback)


def full_state(connection):
    """Detached complete state, including explicit receipt bodies, in one snapshot."""
    from api_test_tool.database import in_transaction
    from api_test_tool.orchestration_rows import Metadata
    from api_test_tool.orchestration_storage import History, KINDS
    own = not in_transaction(connection)
    if own:
        connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
    try:
        state = copy.deepcopy(dict(Metadata(connection)))
        state.update({kind: copy.deepcopy(dict(History(connection, kind))) for kind in KINDS})
        return state
    finally:
        if own:
            connection.rollback()


class PostgresDatabases:
    """One owned database per test/Store root, shared across its request threads.

    The full-check runner supplies an isolated server and a CREATEDB role. No
    server is started here and no existing database is reset, truncated or dropped.
    Lazy allocation keeps tests without platform storage independent of a server.
    """
    def __init__(self, monkeypatch, default_root):
        self.monkeypatch = monkeypatch
        self.default_root = Path(default_root).resolve()
        self.scope = ContextVar('veriq_test_database', default=None)
        self.names, self.created = {}, set()
        self.lock = threading.RLock()
        self.configuration = {key: os.environ.get(key) for key in (
            'API_TEST_DB_HOST', 'API_TEST_DB_PORT', 'API_TEST_DB_NAME',
            'API_TEST_DB_USER', 'API_TEST_DB_PASSWORD_FILE')}

    def remember(self, root):
        root = Path(root).resolve()
        with self.lock:
            self.names.setdefault(root, 'veriq_test_' + uuid4().hex)
            self.default_root = root
            # Standalone release-probe subprocesses inherit the same database.
            self.monkeypatch.setenv('API_TEST_DB_NAME', self.names[root])
        return root

    @contextmanager
    def using(self, root):
        token = self.scope.set(Path(root).resolve())
        try:
            yield
        finally:
            self.scope.reset(token)

    def raw_connect(self, name, *, autocommit=False, rows=False):
        config = self.configuration
        if not config['API_TEST_DB_HOST'] or not config['API_TEST_DB_PASSWORD_FILE']:
            raise RuntimeError('Platform tests require the isolated PostgreSQL API_TEST_DB_* configuration')
        return psycopg.connect(host=config['API_TEST_DB_HOST'],
            port=int(config['API_TEST_DB_PORT'] or '5432'), dbname=name,
            user=config['API_TEST_DB_USER'] or 'veriq',
            password=Path(config['API_TEST_DB_PASSWORD_FILE']).read_text().rstrip('\r\n'),
            autocommit=autocommit, connect_timeout=10,
            options='-c statement_timeout=20000 -c lock_timeout=20000',
            row_factory=dict_row if rows else tuple_row)

    def admin(self):
        return self.raw_connect(self.configuration['API_TEST_DB_NAME'] or 'veriq', autocommit=True)

    def ensure(self, root, *, initialize=True):
        root = Path(root).resolve()
        with self.lock:
            if root not in self.names:
                self.remember(root)
            name = self.names[root]
            if name not in self.created:
                with self.admin() as admin:
                    admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
                self.created.add(name)
                if initialize:
                    from api_test_tool.storage_migrate import DDL, initial_metadata
                    from api_test_tool.orchestration_rows import Metadata
                    with self.raw_connect(name) as connection:
                        for statement in DDL:
                            connection.execute(statement)
                        state = Metadata(connection)
                        state.update(initial_metadata())
                        state.flush()
                        connection.execute("INSERT INTO platform_storage VALUES(1,1,%s,'active',%s,true,'{}')",
                                           (uuid4().hex, '0' * 40))
            return name

    def connect(self, *, readonly=False, rows=False, root=None):
        root = Path(root or self.scope.get() or self.default_root).resolve()
        connection = self.raw_connect(self.ensure(root), rows=rows)
        connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        connection.read_only = readonly
        return connection

    def reset(self, root, *, initialize=True):
        root = self.remember(root)
        name = self.names[root]
        with self.lock:
            if name in self.created:
                self.drop(name)
            return self.ensure(root, initialize=initialize)

    def drop(self, name):
        if name not in self.created or not name.startswith('veriq_test_'):
            raise AssertionError('Refusing to drop a database not owned by this test')
        with self.admin() as admin:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        self.created.remove(name)

    def close(self):
        for name in tuple(self.created):
            self.drop(name)

    def replace_state(self, root, state, history=()):
        """Seed the release probe's original synthetic state without a Controller."""
        self.remember(root)
        from api_test_tool.orchestration_rows import Metadata, encode
        with self.connect(root=root) as connection:
            metadata = Metadata(connection)
            metadata.clear()
            metadata.update(copy.deepcopy(state))
            metadata.flush()
            connection.execute('DELETE FROM state_history')
            with connection.cursor() as cursor:
                cursor.executemany('INSERT INTO state_history VALUES(%s,%s,%s,%s)', [
                    (kind, str(index), encode(meta), '{"large_result":"must stay unread"}')
                    for index, (kind, meta) in enumerate(history)])

    def contents(self, root):
        from api_test_tool.storage_migrate import current_payload
        with self.connect(root=root, readonly=True) as connection:
            return current_payload(connection)

    def install(self):
        from api_test_tool import accounts, database, orchestration, storage_migrate, ui_round_report, web_storage, wecom
        patch = self.monkeypatch
        patch.setattr(database, 'connect', self.connect)
        # storage_migrate imports connect by value, so bind that reference too.
        patch.setattr(storage_migrate, 'connect', self.connect)
        original_store_init = web_storage.Store.__init__
        @wraps(original_store_init)
        def store_init(store, root):
            original_store_init(store, root)
            self.remember(store.root)
        patch.setattr(web_storage.Store, '__init__', store_init)
        patch.setattr(orchestration.Controller, 'connect', lambda controller: self.connect(root=controller.store.root))

        def scoped(function, root_for):
            @wraps(function)
            def call(*args, **kwargs):
                with self.using(root_for(*args, **kwargs)):
                    return function(*args, **kwargs)
            return call
        for cls in (orchestration.Controller, accounts.Accounts):
            patch.setattr(cls, '__init__', scoped(cls.__init__, lambda instance, store, *a, **k: store.root))
        patch.setattr(web_storage.Store, 'is_account_owner', scoped(web_storage.Store.is_account_owner,
            lambda store, *a, **k: store.root))
        original_accounts_db = accounts.Accounts.db
        @contextmanager
        def account_db(instance, **kwargs):
            with self.using(instance.store.root), original_accounts_db(instance, **kwargs) as connection:
                yield connection
        patch.setattr(accounts.Accounts, 'db', account_db)
        patch.setattr(ui_round_report, 'current_task', scoped(ui_round_report.current_task,
            lambda store, *a, **k: store.root))
        patch.setattr(wecom.WeCom, '_ui_final', scoped(wecom.WeCom._ui_final,
            lambda instance, *a, **k: instance.store.root))
