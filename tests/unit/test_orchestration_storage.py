"""Storage-only upgrade/rollback and no-history-amplification checks."""
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from api_test_tool.orchestration import Controller
from api_test_tool.web_storage import Store
from api_test_tool import database, storage_migrate
from pg_support import full_state, observe


def test_point_reads_and_filtered_history_include_transaction_changes(tmp_path):
    from api_test_tool.orchestration_storage import select_records
    c=Controller(Store(tmp_path))
    with c.transaction() as (_,state):
        for key in ('first','second','unrelated'):
            state['operations'][key]={'id':key,'lease_id':'other' if key=='unrelated' else 'lease',
                'state':'pending','result':{'snapshot':'x'*10000}}
    with c.transaction() as (_,state):
        history=state['operations']
        history['first']['state']='confirmed'
        assert set(history.records)=={'first'} and not history['first'].loaded
        del history['second']
        history['new']={'id':'new','lease_id':'lease','state':'pending'}
        assert [x['id'] for x in select_records(history,lease_id='lease',state='pending')]==['new']
        assert 'unrelated' not in history.records and not history.fully_loaded
    with c.transaction() as (_,state):
        assert {x['id'] for x in select_records(state['operations'],lease_id='lease')}=={'first','new'}


def read(c):
    with c.connect() as db:
        return full_state(db)


def legacy_source(root, original):
    with sqlite3.connect(root / 'orchestration.sqlite3') as db:
        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
        db.execute('INSERT INTO state VALUES(1,?)', (json.dumps(original),))
    with sqlite3.connect(root / 'accounts.sqlite3') as db:
        db.execute('CREATE TABLE accounts(username TEXT PRIMARY KEY,owner TEXT UNIQUE NOT NULL,salt TEXT NOT NULL,password_hash TEXT NOT NULL)')
        db.execute('CREATE TABLE logins(digest TEXT PRIMARY KEY,username TEXT NOT NULL,expires REAL NOT NULL)')


def test_upgrade_rollback_compatibility_and_all_result_types(tmp_path, postgres_database):
    store = Store(tmp_path)
    results = [None, {}, [], False, 3, 'text', {'snapshot': '中文' * 10000}]
    original = {'version': 1, 'epoch': 'same', 'leases': {}, 'operations': {
        f'node:punctuation."[{i}]': {'id': str(i), 'state': 'confirmed', 'result': value}
        for i, value in enumerate(results)}, 'direct_commands': {}}
    original['operations']['absent'] = {'state': 'pending'}
    legacy_source(tmp_path, original)
    source_bytes = (tmp_path / 'orchestration.sqlite3').read_bytes()
    postgres_database.reset(tmp_path, initialize=False)
    receipt = storage_migrate.import_sqlite(tmp_path)
    assert receipt['activation'] == 'ready' and receipt['verified']
    assert storage_migrate.verify()['migration_receipt']['sha256'] == receipt['sha256']
    storage_migrate.activate('1' * 40)
    c = Controller(store)
    assert read(c) == original
    assert (tmp_path / 'orchestration.sqlite3').read_bytes() == source_bytes
    with c.transaction() as (_, state):
        state['operations']['absent']['result'] = {'new': 'receipt'}
        state['operations']['node:punctuation."[6]']['result']['added'] = True
        del state['operations']['node:punctuation."[0]']['result']
    current = read(c)
    assert current['operations']['absent']['result'] == {'new': 'receipt'}
    assert current['operations']['node:punctuation."[6]']['result']['added'] is True
    assert 'result' not in current['operations']['node:punctuation."[0]']
    # Once activated, a retry/rollback must retain the latest PG writes and
    # must never reimport the still-readable legacy database over them.
    with c.transaction() as (_, state):
        state['operations']['late'] = {'state': 'unknown', 'result': None}
    current['operations']['late'] = {'state': 'unknown', 'result': None}
    assert storage_migrate.import_sqlite(tmp_path)['action'] == 'kept_active_postgresql'
    assert read(Controller(store)) == current
    assert (tmp_path / 'orchestration.sqlite3').read_bytes() == source_bytes
    with c.transaction() as (_, state):
        assert state['operations']['late']['result'] is None
        assert state['operations']['absent']['result'] == {'new': 'receipt'}


def test_history_untouched_by_heartbeat_and_transaction_rollback(tmp_path):
    c=Controller(Store(tmp_path))
    with c.transaction() as (_,state):
        state['operations']['large']={'state':'confirmed','result':{'snapshot':'x'*1000000}}
    with c.connect() as db:
        db.execute("CREATE FUNCTION forbid_history_update() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'unrelated history rewritten'; END $$")
        db.execute('CREATE TRIGGER forbid_history_update BEFORE UPDATE ON state_history FOR EACH ROW EXECUTE FUNCTION forbid_history_update()')
    with c.transaction() as (_,state):
        state['epoch']='new'
        # Scanning state for uncertain operations must not load payloads either.
        assert all(record['state']=='confirmed' for record in state['operations'].values())
        assert not state['operations']['large'].loaded
    before=read(c)
    with pytest.raises(RuntimeError):
        with c.transaction() as (_,state):
            state['epoch']='not committed'
            state['operations']['new']={'state':'pending'}
            raise RuntimeError('abort')
    assert read(c)==before


def test_serialized_concurrent_updates_and_whole_map_replacement(tmp_path):
    c=Controller(Store(tmp_path))
    def change(i):
        with c.transaction() as (_,state):
            state['operations'][str(i)]={'state':'pending','result':{'i':i}}
            state['counter']=state.get('counter',0)+1
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(change,range(20)))
    assert read(c)['counter']==20
    assert len(read(c)['operations'])==20
    with c.transaction() as (_,state):
        state['operations']={'only':{'state':'confirmed','result':False}}
    assert read(c)['operations']=={'only':{'state':'confirmed','result':False}}


def test_snapshot_preserves_scope_without_loading_unrelated_receipts(tmp_path,monkeypatch):
    store=Store(tmp_path);c=Controller(store)
    owner=store.session(None)[0]['id'];other=store.session(None)[0]['id']
    task_ids=[];node_ids=[]
    for index,who in enumerate([owner,owner,other]):
        project=store.create_project(who,'scope','fixture.md','snapshot scope')
        store.update_project(who,project['id'],{'ui_target_url':'https://fixture.test/login'})
        task=c.create_task(who,{'project_id':project['id'],'goal':'snapshot scope','request_id':str(index),
                              'modules':[{'key':'one','title':'one','requirements':[]}]})['task_id']
        task_ids.append(task);node_ids.append(c.snapshot(who,task)['nodes'][0]['id'])
    with c.transaction() as (_,state):
        for key,node,status,historical in [('pending',node_ids[0],'pending',False),
                ('unknown',node_ids[0],'unknown',False),('confirmed',node_ids[0],'confirmed',False),
                ('historical',node_ids[0],'unknown',True),('same-owner-other-task',node_ids[1],'unknown',False),
                ('other-owner',node_ids[2],'unknown',False)]:
            state['operations'][key]={'id':key,'node_id':node,'state':status,'historical':historical,
                                      'result':{'evidence':key,'snapshot':'x'*1000000 if status=='confirmed' else ''}}
        state['nodes'][node_ids[0]]['case_history']=[{'kept':'original'}]
        state['direct_commands']['old-image']={'state':'completed','result':{'image':'x'*1000000}}
        state['policies']['policy']={'id':'policy','owner':owner,'session_seed':'must-not-leak','rules':[]}
    from api_test_tool.orchestration_storage import Record
    loaded=[];get=Record.__getitem__;connect=c.connect
    def item(record,key):
        if key=='result':loaded.append(record.key)
        return get(record,key)
    def guarded_connect():
        def normalized_only(statement):
            assert not re.search(r'\b(?:FROM|JOIN)\s+(?:state|state_metadata)\b', statement, re.I)
        return observe(connect(), normalized_only)
    monkeypatch.setattr(Record,'__getitem__',item)
    monkeypatch.setattr(c,'connect',guarded_connect)
    snapshot=c.snapshot(owner,task_ids[0])
    assert [t['id'] for t in snapshot['tasks']]==task_ids[:1]
    assert [n['id'] for n in snapshot['nodes']]==node_ids[:1]
    assert {o['id'] for o in snapshot['operations']}=={'pending','unknown'}
    assert all(o['result']['evidence']==o['id'] for o in snapshot['operations'])
    assert set(loaded)=={'pending','unknown'}
    assert 'case_history' not in snapshot['nodes'][0]
    assert 'session_seed' not in snapshot['policies'][0]
    assert c.snapshot(owner,task_ids[0],include_history=True)['nodes'][0]['case_history']==[{'kept':'original'}]
    assert {o['id'] for o in c.snapshot(owner)['operations']}=={'pending','unknown','same-owner-other-task'}
    with pytest.raises(PermissionError):c.snapshot(owner,task_ids[2])


def test_existing_history_adds_owner_node_and_state_indexes_without_changing_data(tmp_path):
    c = Controller(Store(tmp_path))
    with c.transaction() as (_, state):
        for key, owner, node in [('wanted', 'owner', 'node'), ('other-owner', 'else', 'node'),
                                  ('other-node', 'owner', 'else')]:
            state['direct_commands'][key] = {'owner': owner, 'node_id': node, 'state': 'completed'}
        state['operations']['open'] = {'node_id': 'node', 'state': 'pending'}
        state['operations']['done'] = {'node_id': 'node', 'state': 'confirmed'}
    before = read(c)
    owner_query = ("SELECT key FROM state_history WHERE kind='direct_commands' "
                   "AND meta::json->>'owner'=%s AND meta::json->>'node_id' IN (%s)")
    state_query = ("SELECT key FROM state_history WHERE kind=%s "
                   "AND meta::json->>'state' IN (%s,%s)")
    with c.connect() as db:
        db.execute('DROP INDEX state_history_owner_node')
        db.execute('DROP INDEX state_history_kind_state')
        db.execute('SET LOCAL enable_seqscan=off')
        old_plan = json.dumps(db.execute('EXPLAIN (FORMAT JSON) ' + owner_query, ('owner', 'node')).fetchone()[0])
        assert 'state_history_owner_node' not in old_plan
        # The same idempotent DDL used by the explicit migration must only add
        # the missing indexes, without rewriting any existing receipt rows.
        row_versions = list(db.execute('SELECT kind,key,xmin::text FROM state_history ORDER BY kind,key'))
        for _ in range(2):
            for statement in storage_migrate.DDL:
                db.execute(statement)
        assert list(db.execute('SELECT kind,key,xmin::text FROM state_history ORDER BY kind,key')) == row_versions
        owner_plan = json.dumps(db.execute('EXPLAIN (FORMAT JSON) ' + owner_query, ('owner', 'node')).fetchone()[0])
        assert 'state_history_owner_node' in owner_plan and 'Index Cond' in owner_plan
        pending_plan = json.dumps(db.execute('EXPLAIN (FORMAT JSON) ' + state_query,
                                             ('operations', 'unknown', 'pending')).fetchone()[0])
        assert 'state_history_kind_state' in pending_plan and 'Index Cond' in pending_plan
        assert [r[0] for r in db.execute(owner_query, ('owner', 'node'))] == ['wanted']
        assert [r[0] for r in db.execute(state_query, ('operations', 'unknown', 'pending'))] == ['open']
    assert read(c) == before
    # Whole-map replacement still updates the indexed record metadata.
    before['direct_commands']['wanted']['owner'] = 'changed'
    with c.transaction() as (_, state):
        state['direct_commands'] = before['direct_commands']
    with c.connect() as db:
        assert list(db.execute(owner_query, ('owner', 'node'))) == []
        assert [r[0] for r in db.execute(owner_query, ('changed', 'node'))] == ['wanted']
    assert read(c) == before


@pytest.mark.parametrize('already_migrated', [False, True])
def test_index_creation_failure_rolls_back_entire_initialize(tmp_path, already_migrated, postgres_database, monkeypatch):
    original = {'version': 1, 'operations': {'one': {'state': 'pending'}}, 'direct_commands': {}}
    legacy_source(tmp_path, original)
    source_bytes = (tmp_path / 'orchestration.sqlite3').read_bytes()
    postgres_database.reset(tmp_path, initialize=False)
    if already_migrated:
        storage_migrate.import_sqlite(tmp_path)
        with postgres_database.connect() as db:
            db.execute('DROP INDEX state_history_owner_node')
            db.execute('DROP INDEX state_history_kind_state')
    connect = storage_migrate.connect
    def reject_second_index(statement):
        if statement.startswith('CREATE INDEX IF NOT EXISTS state_history_kind_state'):
            raise database.OperationalError('injected index failure')
    with monkeypatch.context() as patch:
        patch.setattr(storage_migrate, 'connect', lambda **kwargs: observe(connect(**kwargs), reject_second_index))
        with pytest.raises(database.OperationalError, match='injected'):
            storage_migrate.import_sqlite(tmp_path)
    assert (tmp_path / 'orchestration.sqlite3').read_bytes() == source_bytes
    with postgres_database.connect(readonly=True) as db:
        assert db.execute("SELECT to_regclass('public.state_history_owner_node')").fetchone()[0] is None
        if already_migrated:
            assert database.storage_status(db)['activation'] == 'ready'
            assert full_state(db) == original
        else:
            assert db.execute("SELECT to_regclass('public.platform_storage')").fetchone()[0] is None
