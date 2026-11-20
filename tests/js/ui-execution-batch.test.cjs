'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {createExecutionBatch} = require('../../api_test_tool/static/skills/web-exploratory-testing/scripts/execution-batch.cjs');
const clone = value => JSON.parse(JSON.stringify(value));
const passed = actual => ({status: 'passed', actual});

test('ES module entry is standalone and keeps the exact CommonJS implementation', async () => {
  const fs = require('node:fs/promises');
  const path = require('node:path');
  const directory = path.resolve(__dirname, '../../api_test_tool/static/skills/web-exploratory-testing/scripts');
  const common = await fs.readFile(path.join(directory, 'execution-batch.cjs'), 'utf8');
  const esm = await fs.readFile(path.join(directory, 'execution-batch.mjs'), 'utf8');
  assert.equal(esm, common.replace('module.exports = {createExecutionBatch};', 'export {createExecutionBatch};'));
  // Import only this source, without a CJS loader or sibling files, as in a
  // persistent agent session that supports standalone ES module imports.
  const {createExecutionBatch: createEsmBatch} = await import('data:text/javascript;base64,' + Buffer.from(esm).toString('base64'));
  assert.equal(createEsmBatch.toString(), createExecutionBatch.toString());
  let writes = 0, next = 0;
  const steps = [
    {case_id: 'WRITE', run: async () => {writes++; throw Error('response lost');}},
    {case_id: 'NEXT', run: async () => {next++; return passed('independent');}},
  ];
  const batch = createEsmBatch();
  await batch.run(steps);
  const restored = createEsmBatch({initialState: batch.snapshot()});
  await restored.run(steps);
  assert.equal(writes, 1);
  restored.resolveInterruption(passed('read-back confirmed'));
  await restored.run(steps);
  assert.equal(writes, 1);
  assert.equal(next, 1);
});

test('slow pre-action persistence exhausts the budget without dispatch and remains resumable', async () => {
  let time = 0, calls = 0, saved;
  const batch = createExecutionBatch({now: () => time});
  const steps = [{case_id: 'WRITE', run: async () => {calls++; return passed('synthetic write');}}];
  const first = await batch.run(steps, {budgetMs: 10, checkpoint: async state => {
    saved = clone(state);
    time += 12;
  }});
  assert.equal(calls, 0);
  assert.equal(first.completed, 0);
  assert.deepEqual(first.remaining, ['WRITE']);
  assert.equal(saved.active_case_id, null);
  assert.equal(saved.paused, null);
  assert.deepEqual(saved.updates, []);
  const restored = createExecutionBatch({now: () => time, initialState: saved});
  const final = await restored.run(steps, {budgetMs: 10});
  assert.equal(calls, 1);
  assert.equal(final.completed, 1);
});

test('reconciled non-passing observations keep the existing review boundary before independent continuation', async () => {
  for (const status of ['failed', 'partial', 'blocked', 'pending_rule', 'pending_action', 'not_run']) {
    let writes = 0, next = 0;
    const steps = [
      {case_id: 'UNCERTAIN', run: async () => {writes++; throw Error('interrupted');}},
      {case_id: 'NEXT', run: async () => {next++; return passed('independent after review');}},
    ];
    const batch = createExecutionBatch();
    await batch.run(steps);
    const observation = status === 'not_run' ? {status, not_run_reason: 'read-back confirms no operation occurred'} :
      {status, actual: 'read-back confirms this non-passing observation'};
    batch.resolveInterruption(observation);
    const saved = batch.snapshot();
    assert.deepEqual(saved.paused, {kind: 'difference', case_id: 'UNCERTAIN', status});
    const restored = createExecutionBatch({initialState: saved});
    await restored.run(steps);
    assert.equal(next, 0, status);
    assert.equal(writes, 1, status);
    assert.equal(restored.updates()[0].status, status);
    restored.continueAfterReview('NEXT is independent; preserve the reconciled result');
    await restored.run(steps);
    assert.equal(next, 1, status);
    assert.equal(writes, 1, status);
  }
});

test('remaining budget is measured after checkpoint while an already dispatched action is never raced', async () => {
  let time = 0, received, calls = 0;
  const batch = createExecutionBatch({now: () => time});
  const result = await batch.run([
    {case_id: 'ACTIVE', run: async ({remainingMs}) => {received = remainingMs; calls++; time += 20; return passed('finished once');}},
    {case_id: 'NEXT', run: async () => {calls++; return passed('not due yet');}},
  ], {budgetMs: 10, checkpoint: async () => {time += 3;}});
  assert.equal(received, 7);
  assert.equal(calls, 1);
  assert.equal(result.completed, 1);
  assert.deepEqual(result.remaining, ['NEXT']);
  assert.equal(batch.updates()[0].status, 'passed');
});

test('last durable checkpoint retains current-batch time and restoration does not double count it', async () => {
  let time = 0, saved;
  const steps = [
    {case_id: 'A', run: async () => {time += 37; return passed('A observed');}},
    {case_id: 'B', run: async () => {time += 13; return passed('B observed');}},
  ];
  const batch = createExecutionBatch({now: () => time});
  const first = await batch.run(steps, {budgetMs: 30, checkpoint: async s => {saved = clone(s);}});
  assert.equal(first.executionMs, 37);
  assert.equal(saved.execution_ms, 37);
  const restored = createExecutionBatch({now: () => time, initialState: saved});
  assert.equal(restored.snapshot().execution_ms, 37);
  const final = await restored.run(steps, {checkpoint: async s => {saved = clone(s);}});
  assert.equal(final.executionMs, 50);
  assert.equal(saved.execution_ms, 50);
  assert.equal(restored.snapshot().execution_ms, 50);
});

test('live snapshots retain execution time separately from between-batch gaps', async () => {
  let time = 0, saved;
  const batch = createExecutionBatch({now: () => time});
  const steps = [
    {case_id: 'A', run: async () => {time += 10; return passed('A');}},
    {case_id: 'B', run: async () => {time += 5; return passed('B');}},
  ];
  await batch.run(steps, {budgetMs: 10, checkpoint: async s => {saved = clone(s);}});
  time += 100;
  const final = await batch.run(steps, {checkpoint: async s => {saved = clone(s);}});
  assert.equal(final.executionMs, 15);
  assert.equal(final.betweenBatchesMs, 100);
  assert.equal(saved.execution_ms, 15);
  assert.equal(saved.between_batches_ms, 100);
});

test('committed action with a lost response is reconciled before independent continuation without replay', async () => {
  let writes = 0, reads = 0, time = 0, saved;
  const steps = [
    {case_id: 'WRITE', run: async () => {writes++; time += 9; throw Error('synthetic response loss');}},
    {case_id: 'READ', run: async () => {reads++; return passed('independent read');}},
  ];
  const batch = createExecutionBatch({now: () => time});
  await batch.run(steps, {checkpoint: async s => {saved = clone(s);}});
  assert.equal(saved.execution_ms, 9);
  const restored = createExecutionBatch({now: () => time, initialState: saved});
  await restored.run(steps);
  assert.equal(writes, 1);
  assert.equal(reads, 0);
  restored.resolveInterruption(passed('read-back confirms the write happened once'));
  await restored.run(steps);
  assert.equal(writes, 1);
  assert.equal(reads, 1);
});

test('failed persistence after a mutation recovers from the active snapshot without automatic resend', async () => {
  let writes = 0, checkpointCalls = 0, saved;
  const steps = [{case_id: 'WRITE', run: async () => {writes++; return passed('committed');}}];
  const batch = createExecutionBatch();
  await assert.rejects(batch.run(steps, {checkpoint: async s => {
    if (++checkpointCalls === 2) throw Error('synthetic disk error');
    saved = clone(s);
  }}), /synthetic disk error/);
  const restored = createExecutionBatch({initialState: saved});
  const result = await restored.run(steps);
  assert.equal(result.paused.kind, 'uncertain');
  assert.equal(writes, 1);
  restored.resolveInterruption(passed('read-only state confirms committed write'));
  await restored.run(steps);
  assert.equal(writes, 1);
});

test('reviewed failed result stays failed while independent work proceeds and only acknowledged results leave the queue', async () => {
  const batch = createExecutionBatch();
  const steps = [
    {case_id: 'FAIL', run: async () => ({status: 'failed', actual: 'synthetic mismatch'})},
    {case_id: 'NEXT', run: async () => passed('independent result')},
  ];
  assert.equal((await batch.run(steps)).paused.kind, 'difference');
  batch.continueAfterReview('NEXT does not depend on FAIL');
  await batch.run(steps);
  assert.deepEqual(batch.updates().map(r => [r.case_id, r.status]), [['FAIL', 'failed'], ['NEXT', 'passed']]);
  batch.acknowledge(['NEXT']);
  assert.deepEqual(batch.updates().map(r => r.case_id), ['FAIL']);
});

test('each independent result is persisted before the next case executes', async () => {
  const events = [];
  const batch = createExecutionBatch();
  await batch.run(['A', 'B'].map(case_id => ({case_id, run: async () => {
    events.push('run:' + case_id); return passed(case_id);
  }})), {persistCase: async value => {events.push('save:' + value.case_id);}});
  assert.deepEqual(events, ['run:A', 'save:A', 'run:B', 'save:B']);
  assert.deepEqual(batch.updates(), []);
});

test('save failure preserves completed case and resumes without replaying the browser', async () => {
  const events = []; let saved;
  const batch = createExecutionBatch();
  const steps = ['A', 'B'].map(case_id => ({case_id, run: async () => {
    events.push('run:' + case_id); return passed(case_id);
  }}));
  await assert.rejects(batch.run(steps, {
    checkpoint: async value => {saved = clone(value);},
    persistCase: async () => {throw new Error('save failed');},
  }), /save failed/);
  assert.equal(saved.cursor, 1);
  assert.equal(saved.active_case_id, null);
  const restored = createExecutionBatch({initialState: saved});
  await restored.run(steps, {persistCase: async value => {events.push('save:' + value.case_id);}});
  assert.deepEqual(events, ['run:A', 'save:A', 'run:B', 'save:B']);
});
