// Helpers in the original native browser call. No platform proxy or credentials.
async function nativeBrowserCase({case_id, run, emit, observation: previous, preserve}) {
  let receipt;
  const observation = previous || {case_id, status: 'partial', checks: [], steps: [], timing: {started_at: new Date().toISOString()}};
  if (observation.case_id !== case_id) throw new Error('Cannot resume another case journal');
  delete observation.error;
  observation.status = 'partial';
  const stamp = () => new Date().toISOString();
  const journal = {
    check(name, expected, observed, ok) {
      if (typeof ok !== 'boolean') throw new Error('Assertion must be boolean');
      observation.checks.push({name, expected, observed, ok});
      observation.timing.last_assertion_at = stamp();
      return ok;
    },
    async step(name, action) {
      const began = Date.now();
      const step = {name, started_at: stamp()};
      observation.steps.push(step);
      try { const value = await action(); step.completed = true; return value; }
      catch (error) { step.error = String(error); throw error; }
      finally { step.finished_at = stamp(); step.duration_ms = Date.now() - began; }
    },
    // Only the read is repeated. Never replay a click, submit or navigation on timeout.
    async until(read, ready, {timeout_ms = 10000, max_reads = 12} = {}) {
      if (!(timeout_ms > 0 && timeout_ms <= 30000 && max_reads > 0 && max_reads <= 30))
        throw new Error('Invalid bounded observation wait');
      const began = Date.now(), deadline = began + timeout_ms;
      for (let i = 0; i < max_reads; i++) {
        // Spread read-only probes across the existing budget, with quick early
        // checks and a final check at its boundary. Fast reads must not exhaust
        // the count before the page has had its allowed time to settle.
        if (i) {
          const nextAt = began + timeout_ms * (i / (max_reads - 1)) ** 2;
          const delay = Math.max(0, Math.min(nextAt, deadline) - Date.now());
          if (delay) await new Promise(resolve => setTimeout(resolve, delay));
        }
        const state = await read();
        if (ready(state)) return state;
        if (Date.now() >= deadline) break;
      }
      throw new Error('Observed state did not reach the expected condition');
    }
  };
  try {
    await run(journal);
    if (!observation.checks.length) throw new Error('No actual assertions');
    observation.status = observation.checks.every(c => c.ok) ? 'passed' : 'failed';
  } catch (error) {
    observation.error = String(error);
    observation.timing.interrupted_at = stamp();
    if (preserve) {
      try { await preserve(observation); } catch (error) { observation.preservation_error = String(error); }
    }
    // A tool/locator error is evidence for Codex's next decision, not a business
    // assertion, a final case verdict, or permission to close/release anything.
    return {case_id, status: 'interrupted', observation,
      failed_step: [...observation.steps].reverse().find(step => step.error) || null,
      browser_stopped: false, saved: false, error: String(error)};
  }
  observation.timing.finished_at = stamp();
  if (emit) {
    try { receipt = await emit(observation); }
    catch (error) { receipt = {saved: false, error: String(error)}; }
  }
  return {case_id, status: observation.status, checks: observation.checks.length,
    browser_stopped: false, save_receipt: receipt,
    // Preserve a draft on missing/unknown save; don't require model reconstruction.
    ...(!receipt?.saved ? {observation} : {})};
}

// Capture one already-observed state. No navigation, business replay, polling or retry.
// A locator-only crop cannot establish the object's context. The default is the
// current viewport; an optional detail is supplemental, never its replacement.
async function nativeCaptureEvidence({page, case_id, step, directory, detail, preview}) {
  if (!case_id || typeof step !== 'string' || !step.trim()) throw new Error('Original case and evidence step required');
  const fs=await import('node:fs/promises'), path=await import('node:path'), crypto=await import('node:crypto');
  if (!path.isAbsolute(directory)) throw new Error('Private absolute evidence directory required');
  const root=path.join(directory,'evidence');
  await fs.mkdir(root,{recursive:true,mode:0o700});
  const assets=[], result={assets,semantic_review_complete:false};
  const capture=async (target,label,options)=>{
    const file=path.join(root,crypto.randomUUID()+'.png'),captured_at=new Date().toISOString();
    const bytes=await target.screenshot({...options,path:file});
    await fs.chmod(file,0o600);
    assets.push({file,case_id,step:label,kind:'screenshot',captured_at});
    // Display the same captured bytes; do not take a second screenshot to inspect it.
    if (preview) await preview(bytes);
  };
  try {
    await capture(page,step,{fullPage:false});
    if (detail) await capture(detail,step+'（补充特写）',{});
  } catch (error) {result.capture_error=String(error);}
  return result;
}

// Explicit final lifecycle boundary. Ordinary run/step errors never call this.
// Recording a verdict and closing a task are separate decisions.
async function nativeFinishTask({close, directory}) {
  const proof = await close();
  if (!proof || proof.browser_stopped !== true || typeof proof.reason !== 'string' || !proof.reason.trim())
    throw new Error('Actual exit proof required');
  const fs = await import('node:fs/promises');
  const binding = JSON.parse(await fs.readFile(directory + '/binding.json', 'utf8'));
  await fs.writeFile(directory + '/native-explicit-exit.json', JSON.stringify({exit: proof,
    binding: Object.fromEntries(['task_id','node_id','holder_id','lease_id'].map(key => [key,binding[key]])),
    finished_at: new Date().toISOString()}), {encoding: 'utf8', mode: 0o600});
  return proof;
}
