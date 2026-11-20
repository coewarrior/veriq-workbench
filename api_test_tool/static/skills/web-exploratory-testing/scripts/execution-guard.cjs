// Browser-independent helpers. Callbacks must use the bound, authorized page and
// verify real state; a successful delete request alone is not proof of cleanup.
'use strict';

function createCleanupGuard({timeoutMs = Infinity, now = () => performance.now()} = {}) {
  if (typeof now !== 'function' || !(timeoutMs === Infinity ||
      (Number.isFinite(timeoutMs) && timeoutMs > 0))) {
    throw new TypeError('A positive cleanup timeout and clock are required');
  }
  const deadline = now() + timeoutMs;
  const groups = new Map();
  let stopped = '';
  return {
    remainingMs() { return Math.max(0, deadline - now()); },
    reason(group) {
      if (!stopped && this.remainingMs() <= 0) {
        stopped = 'Cleanup deadline reached; record remaining owned items and publish partial cleanup';
      }
      return stopped || groups.get(group)?.stopped || '';
    },
    stopAll(reason) {
      if (!reason) throw new TypeError('A verified stopping reason is required');
      stopped = reason;
    },
    pause(group, reason) {
      groups.set(group, {stopped: reason || 'Cleanup state could not be verified'});
    },
    failure(group, key, reason) {
      if (!group || !key) throw new TypeError('A cleanup group and failure signature are required');
      if (this.reason(group)) return;
      const previous = groups.get(group);
      const count = previous?.key === key ? previous.count + 1 : 1;
      groups.set(group, {key, count, stopped: reason || key});
    },
    success(group) { if (!this.reason(group)) groups.delete(group); },
    reset(group, changedCondition) {
      if (!changedCondition?.trim()) throw new TypeError('Explain the changed condition before retrying');
      groups.delete(group);
    },
  };
}

async function cleanupBatch(items, attempt, guard = createCleanupGuard()) {
  if (!Array.isArray(items) || items.some(item => !item || !item.group)) {
    throw new TypeError('Each owned cleanup item needs an operation/context group');
  }
  if (typeof attempt !== 'function') throw new TypeError('A verified cleanup callback is required');
  const results = [];
  let attempts = 0;
  for (const item of items) {
    let result;
    let itemAttempts = 0;
    while (!guard.reason(item.group) && itemAttempts < 1) {
      itemAttempts++;
      attempts++;
      // The callback must bound its own calls. Never race a mutation against a
      // timer and start a replacement while its outcome is still unknown.
      try { result = await attempt(item, {remainingMs: guard.remainingMs?.() ?? Infinity}); }
      catch {
        // The request may have committed. Do not blindly repeat a mutation.
        result = {state: 'unverified', reason: 'Cleanup call did not return a verifiable result'};
      }
      if (result?.state === 'cleaned') {
        guard.success(item.group);
        break;
      }
      if (result?.state !== 'unverified' || !result.reason) {
        result = {state: 'unverified', reason: 'Cleanup callback did not verify the resulting state'};
      }
      if (result.confirmedFailure === true && result.failureKey) {
        guard.failure(item.group, result.failureKey, result.reason);
      } else {
        guard.pause(item.group, result.reason);
      }
    }
    results.push({...item, ...result, attempts: itemAttempts,
      state: result?.state === 'cleaned' ? 'cleaned' : 'unverified',
      reason: result?.reason || guard.reason(item.group)});
  }
  return {attempts, cleaned: results.filter(item => item.state === 'cleaned').length,
    unverified: results.filter(item => item.state === 'unverified').length, items: results};
}

async function waitForState(read, {timeoutMs, intervalMs = 1000,
  now = () => performance.now(), delay = ms => new Promise(resolve => setTimeout(resolve, ms))} = {}) {
  if (typeof read !== 'function' || !Number.isFinite(timeoutMs) || timeoutMs <= 0 ||
      !Number.isFinite(intervalMs) || intervalMs <= 0) {
    throw new TypeError('A read callback, finite timeout and positive polling interval are required');
  }
  const deadline = now() + timeoutMs;
  let polls = 0;
  let last;
  while (now() < deadline) {
    // Set each browser read's own timeout to remainingMs when the API supports it.
    last = await read({remainingMs: Math.max(0, deadline - now())});
    polls++;
    if (last?.blocked) return {status: 'blocked', polls, last};
    if (last?.done) return {status: 'completed', polls, last};
    const remaining = deadline - now();
    if (remaining <= 0) break;
    await delay(Math.min(intervalMs, remaining));
  }
  return {status: 'timeout', polls, last};
}

// Dependency IDs come from the platform's scoped inventory. Never build a group
// from an error message alone. One guard belongs to one execution round.
function createDependencyGuard() {
  const checks = new Map();
  const inFlight = new Map();
  return {
    async check(dependency, probe) {
      if (!dependency?.id || typeof probe !== 'function') throw new TypeError('A scoped dependency and real check are required');
      if (checks.has(dependency.id)) return checks.get(dependency.id);
      if (!inFlight.has(dependency.id)) {
        const promise = (async () => {
          const result = await probe(dependency);
          if (!['ready', 'blocked'].includes(result?.status) || typeof result.observed !== 'string' || typeof result.method !== 'string') {
            throw new TypeError('A real prerequisite check needs status, observed and method');
          }
          const checked = {...result, dependency_id: dependency.id};
          checks.set(dependency.id, checked);
          return checked;
        })();
        inFlight.set(dependency.id, promise);
      }
      try { return await inFlight.get(dependency.id); }
      finally { inFlight.delete(dependency.id); }
    },
    reset(dependencyId, changedCondition) {
      if (inFlight.has(dependencyId)) throw new TypeError('Wait for the running check to finish');
      checks.delete(dependencyId);
    },
    async run(caseDesign, probe, execute) {
      if (!caseDesign?.case_id || typeof execute !== 'function' || !Array.isArray(caseDesign.dependencies || [])) {
        throw new TypeError('A case design and business execution callback are required');
      }
      const dependencyChecks = [];
      for (const dependency of caseDesign.dependencies || []) {
        dependencyChecks.push(await this.check(dependency, probe));
      }
      // The caller decides what these observations mean for this case.
      return execute(caseDesign, dependencyChecks);
    },
  };
}

// Register both rejection handlers in the same turn, before awaiting the click.
// A faster event timeout must never become an unhandled rejection while the
// action is still waiting. Wait for both to settle; do not retry uncertain writes.
async function actAndWait(wait, act) {
  if (typeof wait !== 'function' || typeof act !== 'function') throw new TypeError('Provide wait and action callbacks');
  const settle = callback => {
    try { return Promise.resolve(callback()).then(value => ({ok: true, value}), error => ({ok: false, error})); }
    catch (error) { return Promise.resolve({ok: false, error}); }
  };
  const waiting = settle(wait);
  const acting = settle(act);
  const [event, action] = await Promise.all([waiting, acting]);
  if (!action.ok) throw action.error;
  if (!event.ok) throw event.error;
  return event.value;
}

module.exports = {createCleanupGuard, cleanupBatch, waitForState, createDependencyGuard, actAndWait};
