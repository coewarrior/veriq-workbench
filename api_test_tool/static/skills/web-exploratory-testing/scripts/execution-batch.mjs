// Keep a known browser flow inside one tool call. Callbacks use only documented
// APIs on the bound page; this runner neither controls a browser nor retries it.
'use strict';

const statuses = new Set(['passed', 'failed', 'partial', 'blocked', 'pending_rule', 'pending_action', 'not_run']);

function createExecutionBatch({now = () => performance.now(), timestamp = () => new Date().toISOString(), initialState} = {}) {
  const updates = new Map();
  let ids, cursor = 0, paused = null, running = false, lastEnded, activeCaseId = null, activeStarted;
  let executionMs = 0, betweenBatchesMs = 0, batches = 0;

  function result(caseId, value) {
    if (!value || !statuses.has(value.status) || (value.case_id && value.case_id !== caseId) ||
        !((value.status === 'not_run' ? value.not_run_reason : value.actual) || '').trim()) {
      throw new TypeError('Each case needs its own supported status and real observation or not-run reason');
    }
    return {...value, case_id: caseId};
  }

  function snapshot() {
    // A recovery checkpoint is taken before run() returns. Include time already
    // observed in this batch, without adding it twice to the accumulated total.
    const observedExecutionMs = executionMs + (running ? Math.max(0, now() - activeStarted) : 0);
    return {case_ids: ids || [], cursor, paused, active_case_id: activeCaseId, batches, execution_ms: observedExecutionMs,
      between_batches_ms: betweenBatchesMs, updates: [...updates.values()]};
  }

  if (initialState) {
    if (!Array.isArray(initialState.case_ids) || initialState.case_ids.some(id => typeof id !== 'string' || !id) ||
        new Set(initialState.case_ids).size !== initialState.case_ids.length ||
        !Number.isInteger(initialState.cursor) || initialState.cursor < 0 || initialState.cursor > initialState.case_ids.length ||
        !Array.isArray(initialState.updates)) throw new TypeError('Restore a local batch snapshot');
    ids = [...initialState.case_ids];
    cursor = initialState.cursor;
    paused = initialState.paused || (initialState.active_case_id ? {kind: 'uncertain', case_id: initialState.active_case_id,
      reason: 'Reconcile the operation that was active when the previous process stopped'} : null);
    for (const value of initialState.updates) updates.set(value.case_id, result(value.case_id, value));
    batches = initialState.batches || 0;
    executionMs = initialState.execution_ms || 0;
    betweenBatchesMs = initialState.between_batches_ms || 0;
  }

  return {
    snapshot,
    updates() { return [...updates.values()]; },
    acknowledge(caseIds) {
      if (!Array.isArray(caseIds)) throw new TypeError('Acknowledge only IDs successfully saved to the platform');
      for (const id of caseIds) updates.delete(id);
    },
    resolveInterruption(observation) {
      if (running || paused?.kind !== 'uncertain') throw new TypeError('No interrupted operation to reconcile');
      const value = result(paused.case_id, observation);
      updates.set(paused.case_id, value);
      cursor++;
      paused = value.status === 'passed' ? null : {kind: 'difference', case_id: value.case_id, status: value.status};
    },
    continueAfterReview(reason) {
      if (running || paused?.kind !== 'difference' || !reason?.trim()) throw new TypeError('Review the difference before continuing');
      paused = null;
    },
    async run(steps, {budgetMs = 20000, checkpoint = async () => {}, persistCase} = {}) {
      if (running || !Array.isArray(steps) || !steps.length || !Number.isFinite(budgetMs) || budgetMs <= 0 ||
          typeof checkpoint !== 'function' || (persistCase !== undefined && typeof persistCase !== 'function') || steps.some(s => !s?.case_id || typeof s.case_id !== 'string' || typeof s.run !== 'function')) {
        throw new TypeError('Provide known case callbacks, a positive call budget and a local checkpoint callback');
      }
      const incoming = steps.map(s => s.case_id);
      if (new Set(incoming).size !== incoming.length ||
          (ids && (incoming.length < ids.length || ids.some((id, index) => incoming[index] !== id)))) {
        throw new TypeError('Preserve existing ordered case IDs; append new discoveries without replaying completed cases');
      }
      ids = incoming;
      // Save a completed verdict before starting another case. A failed save
      // never rewinds the browser cursor or repeats its business actions.
      const flush = async () => {
        if (!persistCase) return;
        for (const value of [...updates.values()]) {
          await persistCase({...value});
          updates.delete(value.case_id);
          await checkpoint(snapshot());
        }
      };
      await flush();
      if (paused) return {completed: cursor, remaining: ids.slice(cursor), paused, batches, executionMs, betweenBatchesMs};
      const started = now();
      if (lastEnded !== undefined) betweenBatchesMs += Math.max(0, started - lastEnded);
      running = true;
      activeStarted = started;
      batches++;
      try {
        while (cursor < steps.length && now() - started < budgetMs) {
          const step = steps[cursor];
          let value;
          try {
            activeCaseId = step.case_id;
            await checkpoint(snapshot());
            const remainingMs = Math.max(0, budgetMs - (now() - started));
            if (remainingMs === 0) {
              // Persistence can consume the budget. No action was dispatched;
              // keep this same step resumable instead of recording uncertainty.
              activeCaseId = null;
              await checkpoint(snapshot());
              break;
            }
            // Callbacks set each read/action's own timeout from remainingMs.
            // A call already sent may have committed: never race or retry it.
            value = result(step.case_id, await step.run({remainingMs}));
          } catch {
            activeCaseId = null;
            paused = {kind: 'uncertain', case_id: step.case_id,
              reason: 'Interrupted operation; reconcile the actual page state before continuing'};
            await checkpoint(snapshot());
            break;
          }
          activeCaseId = null;
          updates.set(step.case_id, {executed_at: timestamp(), ...value});
          cursor++;
          if (value.status !== 'passed') paused = {kind: 'difference', case_id: step.case_id, status: value.status};
          // Local persistence keeps completed work if a later locator fails.
          await checkpoint(snapshot());
          await flush();
          if (paused) break;
        }
      } finally {
        lastEnded = now();
        executionMs += Math.max(0, lastEnded - started);
        running = false;
      }
      return {completed: cursor, remaining: ids.slice(cursor), paused, batches, executionMs, betweenBatchesMs,
        changed: [...updates.values()].map(v => ({case_id: v.case_id, status: v.status}))};
    },
  };
}

export {createExecutionBatch};
