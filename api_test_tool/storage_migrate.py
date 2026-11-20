"""Explicit, transactional SQLite -> PostgreSQL cutover used only by Jenkins.

The old application must already be drained and stopped. Inputs are read-only;
source databases and all report/asset files remain untouched. Nothing here runs
business tests, regenerates identifiers, or changes a case conclusion.
"""
import argparse
import copy
import gc
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

from .database import connect, storage_status, MIGRATION_LOCK, SCHEDULER_LOCK
from .orchestration_rows import Metadata, encode, write_entry

DDL = (
    'CREATE TABLE IF NOT EXISTS platform_storage(id INTEGER PRIMARY KEY CHECK(id=1),schema_version INTEGER NOT NULL,migration_id TEXT NOT NULL,activation TEXT NOT NULL,revision TEXT NOT NULL,verified BOOLEAN NOT NULL,manifest TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS state_sections(key TEXT PRIMARY KEY,ordinal BIGINT NOT NULL,value TEXT)',
    'CREATE TABLE IF NOT EXISTS state_entries(section TEXT NOT NULL,key TEXT NOT NULL,ordinal BIGINT NOT NULL,meta TEXT NOT NULL,history INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(section,key))',
    'CREATE TABLE IF NOT EXISTS state_case_history(node_key TEXT NOT NULL,key TEXT NOT NULL,ordinal BIGINT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(node_key,key))',
    'CREATE TABLE IF NOT EXISTS state_task_baseline(task_key TEXT NOT NULL,key TEXT NOT NULL,ordinal BIGINT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(task_key,key))',
    'CREATE TABLE IF NOT EXISTS state_history(kind TEXT NOT NULL,key TEXT NOT NULL,meta TEXT NOT NULL,result TEXT,PRIMARY KEY(kind,key))',
    'CREATE TABLE IF NOT EXISTS receipts(owner TEXT,key TEXT,hash TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(owner,key))',
    'CREATE TABLE IF NOT EXISTS audit(seq BIGSERIAL PRIMARY KEY,owner TEXT,at DOUBLE PRECISION,kind TEXT,subject TEXT,detail TEXT)',
    'CREATE TABLE IF NOT EXISTS accounts(username TEXT PRIMARY KEY,owner TEXT UNIQUE NOT NULL,salt TEXT NOT NULL,password_hash TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS logins(digest TEXT PRIMARY KEY,username TEXT NOT NULL,expires DOUBLE PRECISION NOT NULL)',
    'CREATE INDEX IF NOT EXISTS state_entries_order ON state_entries(section,ordinal)',
    "CREATE INDEX IF NOT EXISTS state_entries_task ON state_entries(section,(meta::json->>'task_id'),ordinal)",
    "CREATE INDEX IF NOT EXISTS state_entries_owner ON state_entries(section,(meta::json->>'owner'),ordinal)",
    'CREATE INDEX IF NOT EXISTS state_case_history_order ON state_case_history(node_key,ordinal)',
    'CREATE INDEX IF NOT EXISTS state_task_baseline_order ON state_task_baseline(task_key,ordinal)',
    "CREATE INDEX IF NOT EXISTS state_history_dispatch ON state_history(kind,(meta::json->>'lease_id'),(meta::json->>'state'))",
    "CREATE INDEX IF NOT EXISTS state_history_owner_node ON state_history(kind,(meta::json->>'owner'),(meta::json->>'node_id'))",
    "CREATE INDEX IF NOT EXISTS state_history_kind_state ON state_history(kind,(meta::json->>'state'))",
)
TABLES = ('state_case_history', 'state_task_baseline', 'state_entries', 'state_sections', 'state_history', 'receipts', 'audit', 'logins', 'accounts')
COLUMNS = {
    'history': ('state_history', 'kind,key,meta,result', 'kind,key'),
    'receipts': ('receipts', 'owner,key,hash,value', 'owner,key'),
    'audit': ('audit', 'seq,owner,at,kind,subject,detail', 'seq'),
    'accounts': ('accounts', 'username,owner,salt,password_hash', 'username'),
    'logins': ('logins', 'digest,username,expires', 'digest'),
}


def digest(value):
    # No sort_keys: insertion order, boolean/null and numerical types are part
    # of the fidelity check, not merely Python's permissive value equality.
    checksum = hashlib.sha256()
    # Preserve the exact compact JSON bytes without allocating another complete
    # multi-hundred-MB string and UTF-8 copy beside the source payload.
    for chunk in json.JSONEncoder(ensure_ascii=False, separators=(',', ':')).iterencode(value):
        checksum.update(chunk.encode('utf-8'))
    return checksum.hexdigest()


def initial_metadata():
    return dict(version=1, epoch=uuid4().hex, accounts={}, tasks={}, nodes={}, leases={},
                runners={}, outbox={}, fixtures={}, policies={}, notices={}, budgets={}, last_project='')


def sqlite_read(path):
    if path.is_symlink():
        raise ValueError('Refusing symlink migration source')
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    db.execute('BEGIN')
    return db


def ordered_rows(key, rows):
    # SQL text collations differ across engines/locales. Table row order is not
    # state-map order: normalize it in Python before cross-engine comparison.
    if key == 'audit':
        return sorted(rows, key=lambda row: row[0])
    count = len(COLUMNS[key][2].split(','))
    return sorted(rows, key=lambda row: tuple((value is not None, value or '') for value in row[:count]))


def source_payload(root):
    payload = {'metadata': None, **{key: [] for key in COLUMNS}}
    path = root / 'orchestration.sqlite3'
    if path.exists():
        db = sqlite_read(path)
        try:
            names = {row[0] for row in db.execute('SELECT name FROM sqlite_master')}
            if 'state_metadata' in names:
                payload['metadata'] = json.loads(db.execute('SELECT value FROM state_metadata WHERE id=1').fetchone()[0])
                payload['history'] = list(db.execute('SELECT kind,key,meta,result FROM state_history ORDER BY kind,key'))
            else:
                state = json.loads(db.execute('SELECT value FROM state WHERE id=1').fetchone()[0])
                for kind in ('operations', 'direct_commands'):
                    for key, record in state.pop(kind, {}).items():
                        payload['history'].append((kind, key, encode({k: v for k, v in record.items() if k != 'result'}),
                                                   encode(record['result']) if 'result' in record else None))
                payload['history'].sort(key=lambda item: item[:2])
                payload['metadata'] = state
            for key in ('receipts', 'audit'):
                table, columns, order = COLUMNS[key]
                if table in names:
                    payload[key] = list(db.execute(f'SELECT {columns} FROM {table} ORDER BY {order}'))
        finally:
            db.close()
    else:
        payload['metadata'] = initial_metadata()
    if payload['metadata'].get('version') != 1:
        raise ValueError('Unsupported source orchestration version')
    path = root / 'accounts.sqlite3'
    if path.exists():
        db = sqlite_read(path)
        try:
            for key in ('accounts', 'logins'):
                table, columns, order = COLUMNS[key]
                payload[key] = list(db.execute(f'SELECT {columns} FROM {table} ORDER BY {order}'))
        finally:
            db.close()
    for key in COLUMNS:
        payload[key] = ordered_rows(key, payload[key])
    return payload


def current_payload(db):
    payload = {'metadata': copy.deepcopy(dict(Metadata(db)))}
    for key, (table, columns, order) in COLUMNS.items():
        payload[key] = ordered_rows(key, list(db.execute(f'SELECT {columns} FROM {table} ORDER BY {order}')))
    return payload


def validate_source_text(payload):
    """Fail before import if a raw SQL TEXT value cannot be stored losslessly.

    JSON bodies are encoded (including escaped control characters); map keys
    and the legacy tables' raw TEXT columns must also be valid PostgreSQL TEXT.
    Never include a key, receipt, account or report value in the error output.
    """
    def check(value):
        if not isinstance(value, str):
            return
        if '\x00' in value:
            raise ValueError('Migration source contains a NUL in a raw TEXT column; source retained')
        try:
            value.encode('utf-8')
        except UnicodeEncodeError:
            raise ValueError('Migration source contains invalid Unicode in a raw TEXT column; source retained') from None

    for section, value in payload['metadata'].items():
        check(section)
        if isinstance(value, dict):
            for key, entry in value.items():
                check(key)
                if section == 'nodes' and isinstance(entry, dict) and isinstance(entry.get('case_history'), dict):
                    for revision in entry['case_history']:
                        check(revision)
                if section == 'tasks' and isinstance(entry, dict) and isinstance(entry.get('baseline'), dict):
                    for field in entry['baseline']:
                        check(field)
    for table in COLUMNS:
        for row in payload[table]:
            for value in row:
                check(value)


def summary(payload):
    metadata = payload['metadata']
    return {'sha256': digest(payload), 'counts': {**{key: len(payload[key]) for key in COLUMNS},
        'sections': len(metadata), 'entries': sum(len(v) for v in metadata.values() if isinstance(v, dict)),
        'case_revisions': sum(len(n.get('case_history', {})) for n in metadata.get('nodes', {}).values()
                              if isinstance(n, dict) and isinstance(n.get('case_history'), dict)),
        'baseline_fields': sum(len(t.get('baseline', {})) for t in metadata.get('tasks', {}).values()
                               if isinstance(t, dict) and isinstance(t.get('baseline'), dict))}}


def import_sqlite(root, *, allow_empty=False, legacy_accounts_only=False):
    with connect() as db:
        db.execute('BEGIN ISOLATION LEVEL READ COMMITTED READ WRITE')
        db.execute('SELECT pg_advisory_xact_lock(%s)', (MIGRATION_LOCK,))
        db.execute('SELECT pg_advisory_xact_lock(%s)', (SCHEDULER_LOCK,))
        exists = db.execute("SELECT to_regclass('public.platform_storage')").fetchone()[0]
        old = db.execute('SELECT activation,manifest FROM platform_storage WHERE id=1').fetchone() if exists else None
        if old and old[0] == 'active':
            # Never treat the retained SQLite source as authoritative again.
            return {**storage_status(db), 'action': 'kept_active_postgresql'}
        if old and old[0] != 'ready':
            raise RuntimeError('Unknown PostgreSQL cutover phase; refusing to overwrite data')
        if legacy_accounts_only and (not (root / 'accounts.sqlite3').is_file()
                                     or (root / 'orchestration.sqlite3').exists()):
            raise RuntimeError('Legacy accounts-only upgrade requires accounts and no orchestration source')
        if not (allow_empty or legacy_accounts_only) and not all((root / name).is_file() for name in ('orchestration.sqlite3', 'accounts.sqlite3')):
            raise RuntimeError('Expected both legacy databases; refusing empty production migration')
        for statement in DDL:
            db.execute(statement)
        source = source_payload(root)
        validate_source_text(source)
        receipt = summary(source)
        if old:
            # An unactivated import has no application writers. A new attempt
            # after a legacy-image rollback may legitimately have a newer source.
            for table in TABLES:
                db.execute('DELETE FROM ' + table)
        else:
            if any(db.execute('SELECT EXISTS(SELECT 1 FROM ' + table + ')').fetchone()[0] for table in TABLES):
                raise RuntimeError('Unidentified PostgreSQL data exists; refusing to overwrite it')
        for ordinal, (section, value) in enumerate(source['metadata'].items()):
            db.execute('INSERT INTO state_sections VALUES(%s,%s,%s)',
                       (section, ordinal, None if isinstance(value, dict) else encode(value)))
            if isinstance(value, dict):
                for position, (key, entry) in enumerate(value.items()):
                    write_entry(db, section, key, position, entry)
        for key, (table, columns, _) in COLUMNS.items():
            placeholders = ','.join('%s' for _ in columns.split(','))
            with db.cursor() as cursor:
                cursor.executemany(f'INSERT INTO {table}({columns}) VALUES({placeholders})', source[key])
        maximum = db.execute('SELECT MAX(seq) FROM audit').fetchone()[0]
        db.execute("SELECT setval(pg_get_serial_sequence('audit','seq'),%s,%s)", (maximum or 1, maximum is not None))
        # The source has been fully inserted and its digest/counts retained.
        # Release it before reconstructing the independent destination check.
        del source
        gc.collect()
        actual = summary(current_payload(db))
        if actual != receipt:
            raise RuntimeError('PostgreSQL import integrity mismatch; entire import rolled back')
        migration_id = uuid4().hex
        db.execute("""INSERT INTO platform_storage VALUES(1,1,%s,'ready','',true,%s)
            ON CONFLICT(id) DO UPDATE SET schema_version=1,migration_id=excluded.migration_id,
            activation='ready',revision='',verified=true,manifest=excluded.manifest""", (migration_id, encode(receipt)))
        return {**storage_status(db), **receipt, 'action': 'imported_and_verified'}


def verify():
    with connect(readonly=True) as db:
        status = storage_status(db)
        expected = json.loads(db.execute('SELECT manifest FROM platform_storage WHERE id=1').fetchone()[0])
        if status['activation'] == 'ready':
            actual = summary(current_payload(db))
            if actual != expected:
                raise RuntimeError('Unactivated PostgreSQL contents differ from the verified migration')
        if not status['verified']:
            raise RuntimeError('PostgreSQL migration is not verified')
        return {**status, 'migration_receipt': expected}


def activate(revision):
    import re
    if not re.fullmatch('[a-f0-9]{40}', revision):
        raise ValueError('Activation requires the full verified release SHA')
    with connect() as db:
        db.execute('BEGIN ISOLATION LEVEL READ COMMITTED READ WRITE')
        db.execute('SELECT pg_advisory_xact_lock(%s)', (MIGRATION_LOCK,))
        db.execute('SELECT pg_advisory_xact_lock(%s)', (SCHEDULER_LOCK,))
        status = storage_status(db)
        if not status['verified']:
            raise RuntimeError('Cannot activate unverified storage')
        if status['activation'] == 'ready':
            expected = json.loads(db.execute('SELECT manifest FROM platform_storage WHERE id=1').fetchone()[0])
            if summary(current_payload(db)) != expected:
                raise RuntimeError('Storage changed before activation; refusing cutover')
        db.execute("UPDATE platform_storage SET activation='active',revision=%s WHERE id=1", (revision,))
        return storage_status(db)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect', 'import-sqlite', 'verify', 'activate'))
    parser.add_argument('--source', type=Path, default=Path(os.environ.get('API_TEST_DATA_DIR', '/data')))
    parser.add_argument('--revision')
    parser.add_argument('--allow-empty', action='store_true', help='Explicit new-install/isolated startup bootstrap only')
    parser.add_argument('--legacy-accounts-only', action='store_true',
                        help='Explicit pre-orchestration legacy upgrade; preserve and verify existing accounts/logins')
    args = parser.parse_args()
    if args.action == 'import-sqlite':
        result = import_sqlite(args.source, allow_empty=args.allow_empty, legacy_accounts_only=args.legacy_accounts_only)
    elif args.action == 'activate':
        result = activate(args.revision or '')
    elif args.action == 'verify':
        result = verify()
    else:
        result = storage_status()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Driver errors may embed SQL parameters and legacy report contents.
        # Jenkins gets only the category, never a raw database traceback.
        print('Storage migration failed (' + type(error).__name__ + '); no unverified data was activated.', file=sys.stderr)
        sys.exit(1)
