"""PostgreSQL metadata rows and independent historical revisions.

The caller owns the appropriate scheduling/node locks. Lazy maps track nested
edits without loading unrelated records; ordinals preserve scheduling order.
"""
from collections.abc import Mapping, MutableMapping
import copy
import json


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                      default=lambda obj: dict(obj) if isinstance(obj, Mapping) else _unsupported(obj))


def _unsupported(obj):
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')


def write_entry(db, section, key, ordinal, entry):
    field, archive = archived_field(section)
    history = isinstance(entry, dict) and field is not None and isinstance(entry.get(field), Mapping)
    meta = {k: {} if k == field else v for k, v in entry.items()} if history else entry
    db.execute('INSERT INTO state_entries(section,key,ordinal,meta,history) VALUES(%s,%s,%s,%s,%s) '
               'ON CONFLICT(section,key) DO UPDATE SET ordinal=excluded.ordinal,meta=excluded.meta,history=excluded.history',
               (section, key, ordinal, encode(meta), int(history)))
    if archive is not None:
        db.execute(f'DELETE FROM {archive.table} WHERE {archive.owner_column}=%s', (key,))
        if history:
            db.cursor().executemany(f'INSERT INTO {archive.table} VALUES(%s,%s,%s,%s)',
                           ((key, k, pos, encode(v)) for pos, (k, v) in enumerate(entry[field].items())))


class OrderedRows(MutableMapping):
    """Keys/ordinals are cheap, while values are loaded only when accessed."""
    def __init__(self, db, scope):
        self.db, self.scope = db, scope
        self.records, self.original, self.deleted, self.added = {}, {}, set(), {}
        self._keys = None
        self._fully_loaded = False

    def persisted_keys(self):
        raise NotImplementedError

    def keys_in_order(self):
        if self._keys is None:
            self._keys = dict.fromkeys(self.persisted_keys())
        return self._keys

    def __iter__(self):
        yield from (k for k in self.keys_in_order() if k not in self.deleted and k not in self.added)
        yield from self.added

    def __len__(self):
        return sum(1 for _ in self)

    def __getitem__(self, key):
        if key in self.records:
            return self.records[key]
        if key in self.deleted:
            raise KeyError(key)
        value, original = self.read(key)
        self.records[key], self.original[key] = value, original
        return value

    def __setitem__(self, key, value):
        if key not in self.added and (key in self.deleted or key not in self.keys_in_order()):
            self.added[key] = None
        self.records[key] = value

    def __delitem__(self, key):
        # Membership does not require reading a potentially large value.
        if key not in self.added and (key in self.deleted or key not in self.keys_in_order()):
            raise KeyError(key)
        self.records.pop(key, None)
        self.added.pop(key, None)
        self.deleted.add(key)

    def values(self):
        self.load_all()
        return super().values()

    def items(self):
        self.load_all()
        return super().items()

    def load_all(self):
        raise NotImplementedError

    def __deepcopy__(self, memo):
        self.load_all()
        return copy.deepcopy(dict(self), memo)


class CaseHistory(OrderedRows):
    table = 'state_case_history'
    owner_column = 'node_key'

    def persisted_keys(self):
        return (r[0] for r in self.db.execute(f'SELECT key FROM {self.table} WHERE {self.owner_column}=%s ORDER BY ordinal', (self.scope,)))

    def load_all(self):
        if self._fully_loaded:
            return
        rows = list(self.db.execute(f'SELECT key,value FROM {self.table} WHERE {self.owner_column}=%s ORDER BY ordinal', (self.scope,)))
        if self._keys is None:
            self._keys = dict.fromkeys(key for key, _ in rows)
        for key, raw in rows:
            if key not in self.records and key not in self.deleted:
                value = json.loads(raw)
                self.records[key], self.original[key] = value, encode(value)
        self._fully_loaded = True

    def read(self, key):
        row = self.db.execute(f'SELECT value FROM {self.table} WHERE {self.owner_column}=%s AND key=%s', (self.scope, key)).fetchone()
        if row is None:
            raise KeyError(key)
        value = json.loads(row[0])
        return value, encode(value)

    def flush(self):
        for key in self.deleted:
            self.db.execute(f'DELETE FROM {self.table} WHERE {self.owner_column}=%s AND key=%s', (self.scope, key))
        position = None
        for key, value in self.records.items():
            encoded = encode(value)
            if key in self.added:
                if position is None:
                    position = self.db.execute(f'SELECT COALESCE(MAX(ordinal),-1)+1 FROM {self.table} WHERE {self.owner_column}=%s', (self.scope,)).fetchone()[0]
                self.db.execute(f'INSERT INTO {self.table} VALUES(%s,%s,%s,%s)', (self.scope, key, position, encoded))
                position += 1
            elif encoded != self.original.get(key):
                self.db.execute(f'UPDATE {self.table} SET value=%s WHERE {self.owner_column}=%s AND key=%s', (encoded, self.scope, key))


class TaskBaseline(CaseHistory):
    """Frozen task/cases/sources stay separate from scheduling metadata."""
    table = 'state_task_baseline'
    owner_column = 'task_key'


def archived_field(section):
    # Only these two existing payloads are split; all other metadata is ordinary JSON.
    if section == 'nodes':
        return 'case_history', CaseHistory
    if section == 'tasks':
        return 'baseline', TaskBaseline
    return None, None


class EntryMap(OrderedRows):
    def __init__(self, db, section):
        super().__init__(db, section)
        self.histories = {}
        self.field, self.archive = archived_field(section)

    def persisted_keys(self):
        return (r[0] for r in self.db.execute('SELECT key FROM state_entries WHERE section=%s ORDER BY ordinal', (self.scope,)))

    def __setitem__(self, key, value):
        if key not in self.deleted and key in self.keys_in_order() and key not in self.original:
            # Capture only old metadata/flags; replacing a node must also remove
            # its stored history even if that node was never read by the caller.
            self[key]
        super().__setitem__(key, value)

    def load_all(self):
        if self._fully_loaded:
            return
        # Scheduling naturally scans maps. Fetch compact metadata once instead
        # of issuing one network round trip per node/account; history stays lazy.
        rows = list(self.db.execute('SELECT key,meta,history FROM state_entries WHERE section=%s ORDER BY ordinal', (self.scope,)))
        if self._keys is None:
            self._keys = dict.fromkeys(key for key, _, _ in rows)
        for key, meta, history in rows:
            if key not in self.records and key not in self.deleted:
                self.records[key], self.original[key] = self.decode(key, meta, history)
        self._fully_loaded = True

    def decode(self, key, raw, history):
        value = json.loads(raw)
        original = (encode(value), history)
        if history and self.archive is not None:
            value[self.field] = self.histories[key] = self.archive(self.db, key)
        return value, original

    def read(self, key):
        row = self.db.execute('SELECT meta,history FROM state_entries WHERE section=%s AND key=%s', (self.scope, key)).fetchone()
        if row is None:
            raise KeyError(key)
        return self.decode(key, *row)

    def flush(self):
        replacements = {}
        for key, value in self.records.items():
            history = value.get(self.field) if self.field is not None and isinstance(value, dict) else None
            if isinstance(history, Mapping) and (key in self.added or history is not self.histories.get(key)):
                replacements[key] = copy.deepcopy(history)
        for key in self.deleted:
            self.db.execute('DELETE FROM state_entries WHERE section=%s AND key=%s', (self.scope, key))
            if self.archive is not None:
                self.db.execute(f'DELETE FROM {self.archive.table} WHERE {self.archive.owner_column}=%s', (key,))
        position = None
        for key, value in self.records.items():
            # New entries and replacements may carry a lazy history from another
            # node. Detach before clearing its source rows (including same-key replace).
            history = value.get(self.field) if self.field is not None and isinstance(value, dict) else None
            split = isinstance(history, Mapping)
            encoded = encode({k: {} if k == self.field else v for k, v in value.items()} if split else value)
            if key in self.added:
                if position is None:
                    position = self.db.execute('SELECT COALESCE(MAX(ordinal),-1)+1 FROM state_entries WHERE section=%s', (self.scope,)).fetchone()[0]
                detached = dict(value) if key in replacements else value
                if key in replacements:
                    detached[self.field] = replacements[key]
                write_entry(self.db, self.scope, key, position, detached)
                position += 1
                continue
            if (encoded, int(split)) != self.original.get(key):
                self.db.execute('UPDATE state_entries SET meta=%s,history=%s WHERE section=%s AND key=%s', (encoded, int(split), self.scope, key))
            if self.archive is not None:
                if isinstance(history, self.archive) and history is self.histories.get(key):
                    history.flush()
                elif key in self.histories or split or (self.original.get(key) or (None, 0))[1]:
                    detached = replacements.get(key, {}) if split else {}
                    self.db.execute(f'DELETE FROM {self.archive.table} WHERE {self.archive.owner_column}=%s', (key,))
                    self.db.cursor().executemany(f'INSERT INTO {self.archive.table} VALUES(%s,%s,%s,%s)',
                                       ((key, k, pos, encode(v)) for pos, (k, v) in enumerate(detached.items())))


class Metadata(dict):
    def __init__(self, db, keys=None):
        self.db, self.original = db, {}
        self.complete = keys is None
        rows = db.execute('SELECT key,value FROM state_sections ORDER BY ordinal')
        for key, raw in rows:
            if keys is None or key in keys:
                value = EntryMap(db, key) if raw is None else json.loads(raw)
                self[key] = value
                self.original[key] = value if raw is None else encode(value)
        self.excluded = set()  # transaction-only records, not metadata sections

    def flush(self):
        final_keys = [key for key in self if key not in self.excluded]
        reorder = self.complete and final_keys != list(self.original)
        # Materialize only explicit section replacements, before any source rows
        # disappear. This also preserves ordinary dict pop/rename/swap semantics.
        replacements = {key: copy.deepcopy(dict(value)) for key, value in self.items()
                        if key not in self.excluded and isinstance(value, Mapping)
                        and value is not self.original.get(key)}
        for key in self.original.keys() - self.keys():
            self._clear(key)
            self.db.execute('DELETE FROM state_sections WHERE key=%s', (key,))
        position = None
        for key, value in self.items():
            if key in self.excluded:
                continue
            previous = self.original.get(key)
            if isinstance(value, EntryMap) and previous is value:
                value.flush()
                continue
            is_map = isinstance(value, Mapping)
            encoded = None if is_map else encode(value)
            if not is_map and encoded == previous:
                continue
            detached = replacements[key] if is_map else None
            self._clear(key)
            if key in self.original:
                self.db.execute('UPDATE state_sections SET value=%s WHERE key=%s', (encoded, key))
            else:
                if position is None:
                    position = self.db.execute('SELECT COALESCE(MAX(ordinal),-1)+1 FROM state_sections').fetchone()[0]
                self.db.execute('INSERT INTO state_sections VALUES(%s,%s,%s)', (key, position, encoded))
                position += 1
            if is_map:
                for ordinal, (entry_key, entry) in enumerate(detached.items()):
                    write_entry(self.db, key, entry_key, ordinal, entry)
        if reorder:
            # Section ordering is observable too; a dict delete/reinsert moves
            # the section to the end even when its value has not changed.
            self.db.cursor().executemany('UPDATE state_sections SET ordinal=%s WHERE key=%s',
                               ((ordinal, key) for ordinal, key in enumerate(final_keys)))

    def _clear(self, key):
        _, archive = archived_field(key)
        if archive is not None:
            self.db.execute(f'DELETE FROM {archive.table}')
        self.db.execute('DELETE FROM state_entries WHERE section=%s', (key,))
