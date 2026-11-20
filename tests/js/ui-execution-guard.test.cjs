const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createCleanupGuard, cleanupBatch, waitForState, createDependencyGuard} = require(
  '../../api_test_tool/static/skills/web-exploratory-testing/scripts/execution-guard.cjs');
const items = (count, group = 'history/delete/member') =>
  Array.from({length: count}, (_, i) => ({name: `synthetic-${i}`, group}));
const failure = {state: 'unverified', confirmedFailure: true,
  failureKey: 'DELETE_FAILED', reason: 'Deletion failed and the owned item still exists'};

test('confirmed common failure stops forty-item cleanup after one confirmed attempt', async () => {
  const visited = [];
  const result = await cleanupBatch(items(40), async item => {
    visited.push(item.name);
    return failure;
  });
  assert.deepEqual(visited, ['synthetic-0']);
  assert.equal(result.attempts, 1);
  assert.equal(result.cleaned, 0);
  assert.equal(result.unverified, 40);
  assert.equal(result.items[1].attempts, 0);
  assert.equal(result.items[39].name, 'synthetic-39');
  assert.equal(result.items[39].reason, failure.reason);
});

test('failed history cleanup does not prevent independent document cleanup', async () => {
  const result = await cleanupBatch([...items(3), ...items(2, 'document/delete/member')],
    async item => item.group.startsWith('history/') ? failure :
      {state: 'cleaned', reason: 'Refreshed list confirms the owned document is absent'});
  assert.equal(result.attempts, 3);
  assert.equal(result.cleaned, 2);
  assert.equal(result.unverified, 3);
});

test('failure already reproduced during testing is reused without further mutations', async () => {
  const guard = createCleanupGuard();
  guard.failure('history/delete/member', failure.failureKey, failure.reason);
  const result = await cleanupBatch(items(40), () => { throw Error('Must not dispatch'); }, guard);
  assert.equal(result.attempts, 0);
  assert.equal(result.unverified, 40);
});

test('uncertain mutation response is not retried or repeated on equivalent objects', async () => {
  const result = await cleanupBatch(items(10), async () => { throw Error('Transport timeout'); });
  assert.equal(result.attempts, 1);
  assert.equal(result.unverified, 10);
});

test('persistent loading is unverified and stops equivalent mutations', async () => {
  const result = await cleanupBatch(items(10), async () =>
    ({state: 'unverified', reason: 'Request still loading; final state is unknown'}));
  assert.equal(result.attempts, 1);
  assert.equal(result.unverified, 10);
});

test('request acknowledgment does not count as verified cleanup', async () => {
  const result = await cleanupBatch(items(4), async () => ({ok: true}));
  assert.equal(result.attempts, 1);
  assert.equal(result.cleaned, 0);
  assert.equal(result.unverified, 4);
});

test('different failure signatures are not conflated', () => {
  const guard = createCleanupGuard();
  guard.failure('same-path', 'FORBIDDEN', 'Role mismatch');
  guard.failure('same-path', 'UNAVAILABLE', 'Service unavailable');
  assert.equal(guard.reason('same-path'), 'Role mismatch');
  guard.reset('same-path', 'Role configuration corrected; independent service condition changed');
  guard.failure('same-path', 'UNAVAILABLE', 'Service unavailable');
  assert.equal(guard.reason('same-path'), 'Service unavailable');
});

test('retrying a stopped group requires an explicitly changed condition', () => {
  const guard = createCleanupGuard();
  guard.pause('history/delete/member', 'Failed');
  assert.throws(() => guard.reset('history/delete/member', ''), TypeError);
  guard.reset('history/delete/member', 'Service recovered; read-only health check succeeded');
  assert.equal(guard.reason('history/delete/member'), '');
});

test('device block stops all remaining operations regardless of group', async () => {
  const guard = createCleanupGuard();
  const result = await cleanupBatch([...items(2), ...items(2, 'document/delete/member')], async () => {
    guard.stopAll('Device locked and recovery failed');
    return {state: 'unverified', reason: 'Device locked and recovery failed'};
  }, guard);
  assert.equal(result.attempts, 1);
  assert.equal(result.unverified, 4);
});

test('invalid group is rejected before the first mutation', async () => {
  let calls = 0;
  await assert.rejects(cleanupBatch([...items(1), {name: 'missing-group'}], () => calls++), TypeError);
  assert.equal(calls, 0);
});

const clock = () => {
  let elapsed = 0;
  return {now: () => elapsed, delay: async ms => { elapsed += ms; }};
};

test('state waiting returns completion within one bounded call', async () => {
  let reads = 0;
  const result = await waitForState(async () => ({done: ++reads === 3, value: reads}),
    {timeoutMs: 500, intervalMs: 50, ...clock()});
  assert.equal(result.status, 'completed');
  assert.equal(result.polls, 3);
  assert.equal(result.last.value, 3);
});

test('unchanged state reaches the deadline without a new polling loop', async () => {
  const result = await waitForState(async () => ({done: false}),
    {timeoutMs: 150, intervalMs: 50, ...clock()});
  assert.equal(result.status, 'timeout');
  assert.equal(result.polls, 3);
});

test('known device block exits immediately instead of waiting for the deadline', async () => {
  const result = await waitForState(async () => ({blocked: 'Device locked'}),
    {timeoutMs: 300000, ...clock()});
  assert.equal(result.status, 'blocked');
  assert.equal(result.polls, 1);
});

test('unbounded waits are rejected', async () => {
  for (const timeoutMs of [undefined, 0, -1, Infinity, NaN]) {
    await assert.rejects(waitForState(async () => ({done: true}), {timeoutMs}), TypeError);
  }
});
test('prerequisite observations are shared while the executor owns whether to run', async () => {
  const guard = createDependencyGuard();
  let probes = 0, business = 0;
  const probe = async () => {probes++;return {status:'blocked',observed:'HR account missing',method:'Read credentials and session'};};
  const execute = async (design, checks) => {business++;assert.ok(Array.isArray(checks));return {case_id:design.case_id,status:'passed'};};
  for (let i=0;i<40;i++) {
    const result = await guard.run({case_id:`HR-${i}`,dependencies:[{id:'dep-test-tenant-hr'}]},probe,execute);
    assert.equal(result.status,'passed');
  }
  await guard.run({case_id:'PUBLIC',dependencies:[]},probe,execute);
  assert.equal(probes,1);assert.equal(business,41);
  guard.reset('dep-test-tenant-hr','New HR credentials saved');
  const result = await guard.run({case_id:'HR-0',dependencies:[{id:'dep-test-tenant-hr'}]},
    async () => {probes++;return {status:'ready',observed:'Correct role and tenant verified',method:'Login and read permissions'};},execute);
  assert.equal(result.status,'passed');assert.equal(probes,2);assert.equal(business,42);
});

test('parallel linked cases share one probe and different scoped dependencies are checked separately', async () => {
  const guard = createDependencyGuard();let probes=0,business=0;
  const probe=async dep=>{probes++;await Promise.resolve();return {status:dep.id==='hr'?'blocked':'ready',observed:dep.id,method:'Scoped lightweight check'};};
  const execute=async()=>{business++;return {status:'passed'};};
  const results=await Promise.all(Array.from({length:12},(_,i)=>guard.run({case_id:`HR-${i}`,dependencies:[{id:'hr'}]},probe,execute)));
  assert.ok(results.every(result=>result.status==='passed'));
  assert.equal(probes,1);assert.equal(business,12);
  await guard.run({case_id:'STAFF',dependencies:[{id:'staff-other-tenant'}]},probe,execute);
  assert.equal(probes,2);assert.equal(business,13);
});
