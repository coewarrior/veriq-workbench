"""PostgreSQL row storage and detached MVCC projections.

Browser receipts and archived cases are loaded only when explicitly requested.
Only changed records are written; legacy SQLite import lives in storage_migrate.
"""
from collections.abc import MutableMapping
import copy
import json
from functools import wraps
from .orchestration_rows import encode, Metadata
from .database import in_transaction

KINDS = ('operations', 'direct_commands')


class Record(MutableMapping):
    """Metadata is cheap; nested result mutations are tracked after lazy loading."""
    def __init__(self, db, kind, key, meta, has_result):
        self.db, self.kind, self.key = db, kind, key
        self.meta = json.loads(meta)
        self.original_meta = encode(self.meta)
        self.has_result = has_result
        self.loaded = False
        self.original_result = None

    def __getitem__(self, key):
        if key == 'result' and self.has_result:
            if not self.loaded:
                raw = self.db.execute('SELECT result FROM state_history WHERE kind=%s AND key=%s', (self.kind, self.key)).fetchone()[0]
                self.result = json.loads(raw)
                self.original_result = encode(self.result)
                self.loaded = True
            return self.result
        return self.meta[key]

    def __setitem__(self, key, value):
        if key == 'result':
            # Load the old value only when replacing/reading this one receipt.
            if self.has_result and not self.loaded:
                self['result']
            self.result, self.has_result, self.loaded = value, True, True
        else:
            self.meta[key] = value

    def __delitem__(self, key):
        if key == 'result' and self.has_result:
            self['result']
            self.has_result = False
        else:
            del self.meta[key]

    def __iter__(self):
        yield from self.meta
        if self.has_result:
            yield 'result'

    def __len__(self):
        return len(self.meta) + int(self.has_result)

    def __deepcopy__(self, memo):
        return copy.deepcopy(dict(self), memo)


class History(MutableMapping):
    def __init__(self, db, kind):
        self.db, self.kind = db, kind
        self.records = {}
        self.fully_loaded = False
        self.missing = set()
        self.deleted = set()

    def load(self):
        if not self.fully_loaded:
            for key, meta, has_result in self.db.execute(
                    'SELECT key,meta,result IS NOT NULL FROM state_history WHERE kind=%s', (self.kind,)):
                if key not in self.records and key not in self.deleted:
                    self.records[key] = Record(self.db, self.kind, key, meta, has_result)
            self.fully_loaded = True
        return self.records

    def __getitem__(self, key):
        if key in self.records:
            return self.records[key]
        if self.fully_loaded or key in self.deleted or key in self.missing:
            raise KeyError(key)
        row = self.db.execute('SELECT meta,result IS NOT NULL FROM state_history WHERE kind=%s AND key=%s',
                              (self.kind, key)).fetchone()
        if row is None:
            self.missing.add(key)
            raise KeyError(key)
        self.records[key] = Record(self.db, self.kind, key, *row)
        return self.records[key]

    def __setitem__(self, key, value):
        self.records[key] = value
        self.deleted.discard(key)
        self.missing.discard(key)

    def __delitem__(self, key):
        self[key]
        del self.records[key]
        self.deleted.add(key)

    def __iter__(self):
        return iter(self.load())

    def __len__(self):
        return len(self.load())

    def select(self, **filters):
        # Indexed metadata selection plus the transaction's in-memory changes.
        # Never load result bodies or forget a freshly inserted/changed record.
        if any(k not in {'lease_id', 'node_id', 'state'} for k in filters):
            raise ValueError('Unsupported history selection')
        where = ['kind=%s']; args = [self.kind]
        for field, values in filters.items():
            values = values if isinstance(values, (list, tuple, set)) else [values]
            if not values:
                return []
            where.append("(meta::json->>'" + field + "') IN (" + ','.join('%s' for _ in values) + ')')
            args.extend(values)
        for key, meta, has_result in self.db.execute(
                'SELECT key,meta,result IS NOT NULL FROM state_history WHERE ' + ' AND '.join(where), args):
            if key not in self.records and key not in self.deleted:
                self.records[key] = Record(self.db, self.kind, key, meta, has_result)
        return [record for record in self.records.values() if matches(record, filters)]

    def flush(self):
        if self.records is None:
            return
        for key in self.deleted:
            self.db.execute('DELETE FROM state_history WHERE kind=%s AND key=%s', (self.kind, key))
        for key, record in self.records.items():
            if isinstance(record, Record):
                meta = encode(record.meta)
                if meta != record.original_meta:
                    self.db.execute('UPDATE state_history SET meta=%s WHERE kind=%s AND key=%s', (meta, self.kind, key))
                if record.loaded:
                    result = encode(record.result) if record.has_result else None
                    if result != record.original_result:
                        self.db.execute('UPDATE state_history SET result=%s WHERE kind=%s AND key=%s', (result, self.kind, key))
            else:
                meta = {k:v for k,v in record.items() if k != 'result'}
                result = encode(record['result']) if 'result' in record else None
                self.db.execute('INSERT INTO state_history VALUES(%s,%s,%s,%s) ON CONFLICT(kind,key) DO UPDATE SET meta=excluded.meta,result=excluded.result', (self.kind, key, encode(meta), result))


def consistent_read(function):
    """Keep formerly single-statement projections atomic after normalization.

    Join an existing caller snapshot/write transaction; otherwise own only this
    read's snapshot and release it before returning detached values.
    """
    @wraps(function)
    def read(db, *args, **kwargs):
        own_snapshot = not in_transaction(db)
        if own_snapshot:
            db.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        try:
            return function(db, *args, **kwargs)
        finally:
            if own_snapshot:
                db.rollback()
    return read


@consistent_read
def read_metadata(db):
    return copy.deepcopy(dict(Metadata(db)))


@consistent_read
def read_entries(db, section, *, keys=None, include_history=False,
                 include_baseline=False, baseline_fields=None):
    """Detached rows; task projections retain exact baseline presence separately.

    A selected baseline field projection is for known cases/sources consumers,
    never a replacement to persist as the task's complete frozen baseline.
    """
    if keys is not None and not keys:
        return {}
    where, args = ['section=%s'], [section]
    if keys is not None:
        where.append('key=ANY(%s)')
        args.append(list(keys))
    result = {}
    presence = ('EXISTS(SELECT 1 FROM state_task_baseline AS baseline WHERE baseline.task_key=entry.key)'
                if section == 'tasks' else 'FALSE')
    for key, raw, history, baseline_present in db.execute(
            'SELECT key,meta,history,' + presence + ' FROM state_entries AS entry WHERE ' +
            ' AND '.join(where) + ' ORDER BY ordinal', args):
        value = json.loads(raw)
        if section == 'nodes':
            if include_history and history:
                value['case_history'] = {k: json.loads(v) for k, v in db.execute(
                    'SELECT key,value FROM state_case_history WHERE node_key=%s ORDER BY ordinal', (key,))}
            elif not include_history and isinstance(value, dict):
                value.pop('case_history', None)
        elif section == 'tasks' and isinstance(value, dict):
            baseline_present = baseline_present if history else bool(value.get('baseline'))
            if include_baseline and history:
                filters, parameters = ['task_key=%s'], [key]
                if baseline_fields is not None:
                    filters.append('key=ANY(%s)')
                    parameters.append(list(baseline_fields))
                value['baseline'] = {k: json.loads(v) for k, v in db.execute(
                    'SELECT key,value FROM state_task_baseline WHERE ' + ' AND '.join(filters) +
                    ' ORDER BY ordinal', parameters)}
            elif not include_baseline:
                value.pop('baseline', None)
            if not include_baseline or baseline_fields is not None:
                value['_baseline_present'] = baseline_present
        result[key] = value
    return result


@consistent_read
def read_nodes(db, *, task_ids=None, include_history=False):
    if task_ids is None:
        return read_entries(db, 'nodes', include_history=include_history)
    if not task_ids:
        return {}
    keys = [r[0] for r in db.execute("SELECT key FROM state_entries WHERE section='nodes' "
        "AND (meta::json->>'task_id')=ANY(%s) ORDER BY ordinal", (list(task_ids),))]
    return read_entries(db, 'nodes', keys=keys, include_history=include_history)


@consistent_read
def read_node_fields(db, fields, *, states=None, node_id=None):
    """Small current bindings, never a replacement for authoritative write state."""
    if states is not None and not states:
        return {}
    where, args = ["section='nodes'"], []
    if states is not None:
        where.append("(meta::json->>'state')=ANY(%s)")
        args.append(list(states))
    if node_id is not None:
        where.append('key=%s')
        args.append(node_id)
    result = {}
    for key, raw in db.execute('SELECT key,meta FROM state_entries WHERE ' + ' AND '.join(where) + ' ORDER BY ordinal', args):
        value = json.loads(raw)
        result[key] = {field: value.get(field) for field in fields}
    return result


@consistent_read
def read_metadata_without_history(db):
    """Small snapshot without case/baseline bodies; never persist as write state."""
    state = {}
    for key, raw in db.execute('SELECT key,value FROM state_sections ORDER BY ordinal'):
        state[key] = read_entries(db, key) if raw is None else json.loads(raw)
    return state


@consistent_read
def read_snapshot_metadata(db, owner, task_id=None, *, include_history=False):
    state = read_sections(db, ('accounts', 'leases', 'runners', 'notices', 'budgets', 'policies'))
    rows = db.execute("""SELECT key FROM state_entries WHERE section='tasks'
        AND (meta::json->>'owner')=%s AND (%s::text IS NULL OR (meta::json->>'id')=%s) ORDER BY ordinal""",
        (owner, task_id or None, task_id))
    state['tasks'] = read_entries(db, 'tasks', keys=[row[0] for row in rows])
    state['nodes'] = read_nodes(db, task_ids={t['id'] for t in state['tasks'].values()}, include_history=include_history)
    return state


@consistent_read
def read_sections(db, keys, *, include_baseline=True):
    """Detached section values. Explicit whole-section reads include history."""
    row = db.execute("SELECT value FROM state_sections WHERE key='version'").fetchone()
    if not row or json.loads(row[0]) != 1:
        raise ValueError('调度数据版本不兼容，拒绝读取')
    result = {}
    for key in keys:
        row = db.execute('SELECT value FROM state_sections WHERE key=%s', (key,)).fetchone()
        result[key] = {} if row is None else (read_entries(db, key, include_history=True,
            include_baseline=include_baseline) if row[0] is None else json.loads(row[0]))
    return result


def read_record(db, kind, key):
    row = db.execute('SELECT meta,result FROM state_history WHERE kind=%s AND key=%s', (kind, key)).fetchone()
    if row is None:
        return None
    value = json.loads(row[0])
    if row[1] is not None:
        value['result'] = json.loads(row[1])
    return value


def matches(record, filters):
    return all(record.get(field) in (values if isinstance(values, (list, tuple, set)) else [values])
               for field, values in filters.items())


def select_records(records, **filters):
    if isinstance(records, History):
        return records.select(**filters)
    return [record for record in records.values() if matches(record, filters)]
