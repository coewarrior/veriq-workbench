"""Platform PostgreSQL connections. SQLite is only a migration input.

Read snapshots use MVCC and never acquire the scheduler advisory gate. Secrets
are read from a mounted file, not placed in a URL, command line, or diagnostics.
"""
import hashlib
import os
from pathlib import Path

import psycopg
from psycopg import DatabaseError, IntegrityError, OperationalError
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row, tuple_row

SCHEMA_VERSION = 1
SCHEDULER_LOCK = 623428196074941022
MIGRATION_LOCK = 623428196074941023


def connect(*, readonly=False, rows=False):
    host = os.environ.get('API_TEST_DB_HOST')
    secret = os.environ.get('API_TEST_DB_PASSWORD_FILE')
    if not host or not secret:
        raise RuntimeError('PostgreSQL configuration is required; SQLite fallback is disabled')
    password = Path(secret).read_text().rstrip('\r\n')
    if not password:
        raise RuntimeError('PostgreSQL password file is empty')
    db = psycopg.connect(host=host, port=int(os.environ.get('API_TEST_DB_PORT', '5432')),
        dbname=os.environ.get('API_TEST_DB_NAME', 'veriq'), user=os.environ.get('API_TEST_DB_USER', 'veriq'),
        password=password, connect_timeout=10, application_name='veriq',
        row_factory=dict_row if rows else tuple_row)
    db.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    db.read_only = readonly
    return db


def storage_status(db=None):
    if db is None:
        with connect(readonly=True) as current:
            return storage_status(current)
    row = db.execute('SELECT schema_version,migration_id,activation,revision,verified FROM platform_storage WHERE id=1').fetchone()
    if isinstance(row, dict):
        row = tuple(row[key] for key in ('schema_version', 'migration_id', 'activation', 'revision', 'verified'))
    if not row or row[0] != SCHEMA_VERSION:
        raise RuntimeError('PostgreSQL storage schema is missing or incompatible')
    return dict(backend='postgresql', schema=row[0], migration_id=row[1], activation=row[2], revision=row[3], verified=row[4])


def ensure_schema():
    status = storage_status()
    if not status['verified']:
        raise RuntimeError('PostgreSQL migration has not passed integrity verification')
    return status


def require_active(db):
    status = storage_status(db)
    if not status['verified'] or status['activation'] != 'active':
        raise RuntimeError('PostgreSQL cutover is not active; writes are paused')
    return status


def begin_write(db, *, node_ids=None):
    # READ COMMITTED is deliberate: waiting for the gate must precede the
    # authoritative snapshot, including when another writer commits meanwhile.
    db.execute('BEGIN ISOLATION LEVEL READ COMMITTED READ WRITE')
    if node_ids is None:
        db.execute('SELECT pg_advisory_xact_lock(%s)', (SCHEDULER_LOCK,))
    else:
        if not node_ids or any(not isinstance(key, str) or not key for key in node_ids):
            raise ValueError('Node transaction requires explicit node IDs')
        db.execute('SELECT pg_advisory_xact_lock_shared(%s)', (SCHEDULER_LOCK,))
        for key in sorted(set(node_ids)):
            # Hash collisions serialize two nodes; they never weaken exclusion.
            lock = int.from_bytes(hashlib.sha256(('veriq-node:' + key).encode()).digest()[:8], 'big', signed=True)
            db.execute('SELECT pg_advisory_xact_lock(%s)', (lock,))
    require_active(db)


def in_transaction(db):
    return db.info.transaction_status != TransactionStatus.IDLE
