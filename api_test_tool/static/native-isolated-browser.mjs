// Imported once in Codex node_repl, never in restricted cua or a Runner.
// Only browser lifecycle and local metadata live here. Page actions are direct
// Playwright calls; this module has no platform client, transport or heartbeat.
import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {homedir, hostname, platform} from 'node:os';
import {createRequire} from 'node:module';
import {spawn, execFile} from 'node:child_process';
import {promisify} from 'node:util';
const execute = promisify(execFile);

async function exists(file) {
  try { await fs.access(file); return true; } catch (error) {
    if (error.code === 'ENOENT') return false;
    throw error;
  }
}
async function installedRuntime(options, assignmentFile, runtimeContext) {
  // Resolve only on the actual executor, once per created environment. No
  // coordinator-machine paths, npm downloads or launch/probe round trips.
  let modulePath = options.playwright_module;
  const runtimeHome = runtimeContext.homeDir || homedir();
  const runtimeCwd = runtimeContext.cwd || path.dirname(path.resolve(assignmentFile));
  const packageRequire = createRequire(path.resolve(assignmentFile));
  if (modulePath && !path.isAbsolute(modulePath)) throw new Error('Explicit Playwright module path must be absolute');
  if (!modulePath) {
    for (const base of [path.resolve(assignmentFile), path.join(runtimeCwd, 'package.json'),
      path.join(runtimeHome, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/package.json')]) {
      try { modulePath = createRequire(base).resolve('playwright'); break; }
      catch (error) { if (error.code !== 'MODULE_NOT_FOUND') throw error; }
    }
  }
  if (!modulePath) throw new Error('Executor has no installed Playwright runtime; report capability gap, never use shared IAB or Runner');
  // Playwright's resolved entry is CommonJS. The REPL's ESM file loader
  // does not supply module/exports; keep this package in Node's native loader.
  const imported = packageRequire(modulePath);
  const chromium = imported.chromium || imported.default?.chromium;
  if (!chromium) throw new Error('Installed runtime does not expose Chromium');
  const launch = {headless: true};
  if (options.channel && options.channel !== 'chrome') throw new Error('Unsupported installed browser channel');
  if (options.channel || !await exists(chromium.executablePath())) {
    const candidates = platform() === 'darwin' ? ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      path.join(runtimeHome, 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome')] :
      platform() === 'win32' ? [path.join(path.parse(runtimeHome).root, 'Program Files'),
        path.join(path.parse(runtimeHome).root, 'Program Files (x86)'), path.join(runtimeHome, 'AppData/Local')]
        .map(base => path.join(base, 'Google/Chrome/Application/chrome.exe')) :
        ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
    for (const candidate of candidates) {
      if (await exists(candidate)) { launch.executablePath = candidate; break; }
    }
    if (!launch.executablePath) throw new Error('Executor has no installed Chromium/Chrome; report capability gap, never use a shared browser profile');
  }
  return {chromium, executable: launch.executablePath || chromium.executablePath()};
}

const environments = new Map();
const inflight = new Map();
const identityKeys = ['task_id', 'node_id', 'holder_id', 'executor_ref'];
const executorIdentity = value => {
  if (typeof value !== 'string') return value;
  const id = value.replace(/^thread:/, '');
  return /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(id) ? id.toLowerCase() : value;
};
const sameIdentity = (left, right) => identityKeys.every(key => key === 'executor_ref'
  ? executorIdentity(left?.[key]) === executorIdentity(right?.[key]) : left?.[key] === right?.[key]);
const now = () => new Date().toISOString();
async function persist(file, value) {
  const temporary = file + '.' + randomUUID() + '.tmp';
  await fs.writeFile(temporary, JSON.stringify(value), {encoding: 'utf8', mode: 0o600});
  await fs.rename(temporary, file);
}

// The browser process and its private profile outlive the REPL connection.
// Default persistent contexts survive CDP disconnect; newContext() does not.
const PROCESS_TIMEOUT = 5000;
async function processRows(pid, timeout) {
  const options = {maxBuffer: 8 * 1024 * 1024, timeout: Math.max(1, timeout), killSignal: 'SIGKILL'};
  if (platform() === 'win32') {
    const filter = pid ? ' -Filter "ProcessId = ' + pid + '"' : '';
    const {stdout} = await execute('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
      'Get-CimInstance Win32_Process' + filter + ' | Select-Object ProcessId,CommandLine,CreationDate | ConvertTo-Json -Compress'], options);
    const parsed = JSON.parse(stdout || '[]');
    return (Array.isArray(parsed) ? parsed : [parsed]).filter(Boolean)
      .map(row => ({pid: Number(row.ProcessId), command: row.CommandLine || '', started_at: row.CreationDate || null}));
  }
  let stdout;
  try {
    ({stdout} = await execute('ps', ['-ww', ...(pid ? ['-p', String(pid)] : ['-ax']), '-o', 'pid=,lstart=,command='], {...options, env: {LC_ALL: 'C'}}));
  } catch (error) {
    // ps returns 1 with no rows for a PID that genuinely no longer exists.
    // Any timeout, signal, stderr or other failure leaves ownership unknown.
    if (pid && error.code === 1 && !error.killed && !error.signal && !String(error.stdout || '').trim() && !String(error.stderr || '').trim()) return [];
    throw error;
  }
  return stdout.split('\n').filter(line => line.trim()).map(line => {
    const match = line.match(/^\s*(\d+)\s+(\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4})\s+(.*)$/);
    if (!match) throw new Error('Invalid process query response');
    return {pid: Number(match[1]), started_at: match[2].replace(/\s+/g, ' '), command: match[3]};
  });
}
function ownsProcess(row, profile) {
  // Require complete argument boundaries, including profiles containing spaces.
  // A PID alone, a substring of another profile, or a Chromium child is not proof.
  const escaped = profile.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const argument = new RegExp('(?:^|\\s)(?:"--user-data-dir=' + escaped + '"|--user-data-dir="' + escaped + '"|--user-data-dir=' + escaped + ')(?=\\s|$)');
  return argument.test(row.command) && /(?:^|\s)--remote-debugging-port=0(?=\s|$)/.test(row.command)
    && !/(?:^|\s)--type=/.test(row.command);
}
async function ownedProcesses(slot, timeout = PROCESS_TIMEOUT, verifyLaunched = false) {
  const started = Date.now(), deadline = started + Math.max(1, timeout);
  const evidence = {process_state: 'unknown', process_query: Number.isSafeInteger(slot.pid) && slot.pid > 0 ? 'saved_pid' : 'profile_scan'};
  try {
    let rows;
    if (verifyLaunched && evidence.process_query !== 'saved_pid') { evidence.process_reason = 'launched_process_unverified'; return evidence; }
    if (evidence.process_query === 'saved_pid') {
      rows = await processRows(slot.pid, deadline - Date.now());
      if (rows.length) {
        if (rows.length !== 1 || rows[0].pid !== slot.pid || !ownsProcess(rows[0], slot.profile)) {
          evidence.process_reason = 'saved_pid_not_owned'; return evidence;
        }
        if (slot.process_started_at && rows[0].started_at !== slot.process_started_at) {
          evidence.process_reason = 'saved_pid_generation_changed'; return evidence;
        }
      } else {
        // A just-spawned PID must be verified directly; discovery cannot replace it.
        if (verifyLaunched) { evidence.process_reason = 'launched_process_unverified'; return evidence; }
        evidence.process_query = 'saved_pid_absent_profile_scan';
      }
    }
    if (!rows?.length) {
      if (Date.now() >= deadline) throw Object.assign(new Error('Process discovery deadline exceeded'), {code: 'ETIMEDOUT'});
      rows = (await processRows(null, deadline - Date.now())).filter(row => ownsProcess(row, slot.profile));
      if (rows.length === 1 && slot.process_started_at && (rows[0].started_at !== slot.process_started_at || rows[0].pid !== slot.pid)) {
        evidence.process_reason = 'profile_process_generation_changed'; return evidence;
      }
    }
    if (rows.length && slot.process_identity_required && !slot.process_started_at && !verifyLaunched) {
      evidence.process_reason = 'process_generation_unverified'; return evidence;
    }
    if (verifyLaunched && (rows.length !== 1 || !rows[0].started_at)) {
      evidence.process_reason = 'launched_process_unverified'; return evidence;
    }
    evidence.process_state = !rows.length ? 'absent' : rows.length === 1 ? 'present' : 'ambiguous';
    evidence.pids = rows.map(row => row.pid);
    if (rows.length === 1) { evidence.pid = rows[0].pid; evidence.process_started_at = rows[0].started_at; }
    return evidence;
  } catch (error) {
    evidence.process_reason = 'query_failed'; evidence.error_name = error.name;
    evidence.error_code = error.code || error.cause?.code || null;
    return evidence;
  } finally { evidence.process_elapsed_ms = Date.now() - started; }
}
function requireKnownProcess(evidence) {
  if (!['present', 'absent'].includes(evidence.process_state))
    throw Object.assign(new Error('Owned process state unknown or ambiguous; preserve original environment'), {process_evidence: evidence});
  return evidence.pids;
}
async function bounded(operation, timeout, stage, lateCleanup) {
  let timer, expired = false;
  const pending = Promise.resolve().then(operation);
  pending.then(value => { if (expired) return Promise.resolve().then(() => lateCleanup?.(value)); }).catch(() => {});
  try {
    return await Promise.race([pending, new Promise((_, reject) => {
      timer = setTimeout(() => { expired = true; reject(Object.assign(new Error(stage + ' deadline exceeded; preserve original environment'), {code: 'ETIMEDOUT'})); }, Math.max(1, timeout));
    })]);
  } finally { clearTimeout(timer); }
}
async function endpoint(slot) {
  const [port, route] = (await fs.readFile(path.join(slot.profile, 'DevToolsActivePort'), 'utf8')).trim().split('\n');
  if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535 || !route?.startsWith('/devtools/browser/'))
    throw new Error('Invalid owned browser endpoint');
  return 'ws://127.0.0.1:' + port + route;
}
async function targetId(context, page) {
  const deadline = Date.now() + 15000;
  const cdp = await bounded(() => context.newCDPSession(page), 15000, 'CDP target session', session => session.detach());
  try { return (await bounded(() => cdp.send('Target.getTargetInfo'), deadline - Date.now(), 'CDP target identity')).targetInfo.targetId; }
  finally { await bounded(() => cdp.detach(), Math.max(1, deadline - Date.now()), 'CDP target detach'); }
}

// Explicit, read-only fault evidence. Never inspect page content, credentials,
// or unrelated browsers. Endpoint availability is not business success.
export async function diagnose({assignment_file, directory}) {
  const root = path.resolve(directory);
  const receipt = JSON.parse(await fs.readFile(path.join(root, 'browser-environment.json'), 'utf8'));
  const assignment = JSON.parse(await fs.readFile(assignment_file, 'utf8'));
  if (receipt.schema !== 2 || !sameIdentity(receipt.identity, assignment))
    throw new Error('Original owned environment receipt required');
  const started = Date.now();
  const result = {started_at: now(), environment_state: receipt.state, business_result: 'unknown', slots: []};
  const file = path.join(root, 'browser-diagnostic-' + randomUUID() + '.json');
  for (const slot of receipt.slots) {
    const slotStarted = Date.now();
    const item = {context_id: slot.context_id, generation: slot.generation,
      process_state: 'unknown', endpoint_state: 'not_checked', cdp_control_state: 'not_checked', stage: 'process_discovery'};
    result.slots.push(item);
    await persist(file, result);
    try {
      const evidence = await ownedProcesses(slot);
      Object.assign(item, evidence);
      if (evidence.process_state === 'present') {
        item.stage = 'endpoint_file'; await persist(file, result);
        const ws = new URL(await endpoint(slot));
        item.stage = 'endpoint_probe'; await persist(file, result);
        const response = await fetch('http://127.0.0.1:' + ws.port + '/json/version',
          {signal: AbortSignal.timeout(3000), redirect: 'error'});
        item.http_status = response.status;
        item.endpoint_state = response.ok ? 'reachable' : 'http_error';
        await response.body?.cancel();
      }
    } catch (error) {
      item.error_name = error.name;
      item.error_code = error.code || error.cause?.code || null;
      if (item.stage !== 'process_discovery') item.endpoint_state = 'unavailable';
    }
    item.elapsed_ms = Date.now() - slotStarted; item.finished_at = now(); await persist(file, result);
  }
  result.elapsed_ms = Date.now() - started; result.finished_at = now(); await persist(file, result);
  return {...result, diagnostic_file: file};
}

function assignmentScope(assignment, target, existing) {
  const options = assignment.direct_browser || {};
  const hostId = options.host_id || hostname();
  const url = new URL(target);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password)
    throw new Error('Expected original HTTP(S) target without credentials');
  const identity = Object.fromEntries(identityKeys.map(key => [key, assignment[key]]));
  if (identityKeys.some(key => typeof identity[key] !== 'string' || !identity[key])) throw new Error('Original identity required');
  const count = options.context_count ?? assignment.claim_arguments?.account_ids?.length ?? 1;
  if (!Number.isSafeInteger(count) || count < 1) throw new Error('Invalid account context count');
  const signature = JSON.stringify([{...identity, executor_ref:executorIdentity(identity.executor_ref)}, url.origin, hostId, count]);
  if (existing && !existing.closed && existing.signature !== signature) throw new Error('Environment belongs to another assignment');
  return {options, hostId, url, identity, count, signature};
}
function receiptScope(receipt, {identity, url, hostId, count}) {
  if (receipt && !sameIdentity(receipt.identity, identity)) throw new Error('Receipt belongs to another executor');
  if (receipt && receipt.state !== 'closed' && receipt.schema !== 2)
    throw new Error('Legacy live environment: keep original scene; only upgrade after its actual exit is confirmed');
  if (receipt?.schema === 2 && (receipt.origin !== url.origin || receipt.host_id !== hostId || (receipt.state !== 'closed' && receipt.slots.length !== count)))
    throw new Error('Original environment scope changed');
}

// Deliberate connection recovery, including a connected-but-unresponsive REPL
// handle. Disconnect CDP only; do not close Chrome, navigate, or restart it.
export async function reconnect(options) {
  const root = path.resolve(options.directory);
  if (inflight.has(root)) throw new Error('Environment preparation in progress; preserve original operation');
  const assignment = JSON.parse(await fs.readFile(options.assignment_file, 'utf8'));
  const receipt = JSON.parse(await fs.readFile(path.join(root, 'browser-environment.json'), 'utf8'));
  const scope = assignmentScope(assignment, options.origin, environments.get(root));
  receiptScope(receipt, scope);
  const diagnosis = await diagnose(options);
  if (diagnosis.environment_state === 'closed') throw new Error('Original environment is closed; cannot reconnect');
  if (diagnosis.slots.some(slot => slot.process_state === 'absent'))
    throw new Error('Owned browser exited; inspect diagnostic receipt before explicit restart_exited:true');
  if (diagnosis.slots.some(slot => slot.process_state !== 'present'))
    throw new Error('Owned process state unknown or ambiguous; inspect diagnostic receipt');
  const file = path.join(root, 'browser-reconnect-' + randomUUID() + '.json');
  const started = Date.now();
  const attempt = {started_at: now(), diagnostic_file: diagnosis.diagnostic_file, stage: 'disconnect', state: 'pending', cdp_control_state: 'not_checked', stages: []};
  await persist(file, attempt);
  try {
    const existing = environments.get(root);
    if (existing) for (const browser of existing.browsers) await bounded(() => browser.close(), 5000, 'CDP disconnect'); // CDP disconnect only.
    attempt.stages.push({stage: 'disconnect', elapsed_ms: Date.now() - started});
    attempt.stage = 'connect_original'; await persist(file, attempt);
    const session = await prepare({...options, restart_exited: false});
    attempt.stages.push({stage: 'connect_original', elapsed_ms: Date.now() - started - attempt.stages[0].elapsed_ms});
    attempt.state = 'connected'; attempt.cdp_control_state = 'connected'; attempt.elapsed_ms = Date.now() - started; attempt.finished_at = now(); await persist(file, attempt);
    session.recovery_receipt_file = file;
    return session;
  } catch (error) {
    attempt.state = 'failed'; attempt.cdp_control_state = 'failed'; attempt.error_name = error.name; attempt.error_code = error.code || null;
    attempt.elapsed_ms = Date.now() - started; attempt.finished_at = now();
    await persist(file, attempt);
    throw error;
  }
}
export async function prepare({assignment_file, directory, origin, runtime_context = {}, restart_exited = false}) {
  const root = path.resolve(directory);
  if (inflight.has(root)) {
    const pending = inflight.get(root);
    if (pending.assignment_file !== assignment_file || pending.origin !== origin || pending.restart_exited !== restart_exited)
      throw new Error('Another environment request owns this directory');
    return pending.operation;
  }
  const operation = create(assignment_file, root, origin, runtime_context, restart_exited);
  inflight.set(root, {assignment_file, origin, restart_exited, operation});
  try { return await operation; } finally { inflight.delete(root); }
}
async function create(assignmentFile, root, target, runtimeContext, restartExited) {
  const assignment = JSON.parse(await fs.readFile(assignmentFile, 'utf8'));
  const existing = environments.get(root);
  const token = assignment.claim_arguments?.work_token;
  if (token && (!existing || existing.closed)) {
    let ready;
    try { ready = JSON.parse(await fs.readFile(path.join(root, 'stage-ready.json'), 'utf8')); }
    catch (_) { throw new Error('Work stage preflight missing; do not create browser'); }
    if (ready.stage_ready !== true || !sameIdentity(ready.identity, assignment) ||
        ['work_unit_id','plan_revision','requirements_digest'].some(k => ready.work_token?.[k] !== token[k]) ||
        JSON.stringify(ready.account_ids) !== JSON.stringify(assignment.claim_arguments.account_ids) ||
        ready.required_context_count !== assignment.claim_arguments.account_ids?.length ||
        (assignment.direct_browser?.context_count ?? ready.required_context_count) !== ready.required_context_count)
      throw new Error('Work stage preflight mismatched; do not create browser');
  }
  const {options, hostId, url, identity, count, signature} = assignmentScope(assignment, target, existing);
  if (existing && !existing.closed && existing.browsers.every(browser => browser.isConnected())) return existing;
  await fs.mkdir(root, {recursive: true, mode: 0o700});
  const receiptFile = path.join(root, 'browser-environment.json');
  let receipt;
  try { receipt = JSON.parse(await fs.readFile(receiptFile, 'utf8')); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  receiptScope(receipt, {identity, url, hostId, count});
  if (!receipt || receipt.state === 'closed') {
    const previous = receipt;
    const slots = [];
    for (let i = 0; i < count; i++) slots.push({context_id: randomUUID(), profile: await fs.mkdtemp(path.join(root, 'browser-profile-')), generation: 0});
    receipt = {schema: 2, identity, host_id: hostId, origin: url.origin, state: 'creating', browser_tool: 'node_repl',
      started_at: now(), slots, environments: slots.map(slot => ({host_id: hostId, browser: 'chromium', origin: url.origin,
        isolation: 'isolated', context_id: slot.context_id, evidence: 'Dedicated Chromium process and private persistent profile; direct local CDP connection',
        capability_evidence: {source: 'public_tool', capability: 'isolated_login_context', context_id: slot.context_id,
          reference: 'Chromium --user-data-dir isolation; Playwright chromium.connectOverCDP default persistent context'}})),
      ...(previous ? {previous_environment: {environments: previous.environments, closed_at: previous.closed_at}} : {})};
    await persist(receiptFile, receipt);
  }
  const {chromium, executable} = await installedRuntime(options, assignmentFile, runtimeContext);
  const browsers = [], contexts = [], pages = [];
  for (const slot of receipt.slots) {
    const evidence = await ownedProcesses(slot);
    slot.process_evidence = evidence;
    await persist(receiptFile, receipt);
    const pids = requireKnownProcess(evidence);
    if (!pids.length) {
      if (slot.generation && !restartExited)
        throw new Error('Owned browser exited; inspect original receipts, then explicitly prepare with restart_exited:true. No business replay.');
      if (slot.generation) {
        // Keep the logical context/profile for an active lease's reconnect;
        // the new real process gets a distinct reported browser generation.
        const previousId = slot.context_id;
        const environment = receipt.environments.find(item => item.context_id === previousId);
        if (!environment) throw new Error('Original environment evidence missing; preserve receipt for inspection');
        receipt.exited_environments ||= [];
        receipt.exited_environments.push({context_id: previousId, generation: slot.generation,
          exited_observed_at: now(), evidence: 'Owned profile has no live Chromium process before explicit restart'});
      }
      // Remove only this owned stale endpoint. Chrome still enforces its profile lock.
      await fs.rm(path.join(slot.profile, 'DevToolsActivePort'), {force: true});
      slot.generation += 1; slot.entered = false; delete slot.target_id; delete slot.process_started_at; delete slot.pid;
      // Persist before spawn, so a crash cannot downgrade this generation to
      // legacy discovery merely because its PID/birth receipt is incomplete.
      slot.process_identity_required = true;
      receipt.state = 'creating';
      receipt.environments.find(item => item.context_id === slot.context_id).browser_generation = slot.generation;
      await persist(receiptFile, receipt);
      const child = spawn(executable, ['--user-data-dir=' + slot.profile, '--remote-debugging-address=127.0.0.1',
        '--remote-debugging-port=0', '--headless=new', '--no-first-run', '--no-default-browser-check',
        '--disable-background-networking', 'about:blank'], {detached: true, stdio: 'ignore'});
      await new Promise((resolve, reject) => { child.once('spawn', resolve); child.once('error', reject); });
      child.unref(); slot.pid = child.pid; slot.launched_at = now();
      await persist(receiptFile, receipt);
      const launchedEvidence = await ownedProcesses(slot, PROCESS_TIMEOUT, true);
      slot.process_evidence = launchedEvidence;
      if (launchedEvidence.process_state === 'present') slot.process_started_at = launchedEvidence.process_started_at;
      await persist(receiptFile, receipt);
      requireKnownProcess(launchedEvidence);
    } else {
      slot.pid = evidence.pid; slot.process_started_at = evidence.process_started_at;
      await persist(receiptFile, receipt);
    }
    // Startup wait is only for the owned endpoint, never a page-action wrapper.
    const connectionStarted = Date.now();
    const connection = slot.connection_evidence = {started_at: now(), stage: 'endpoint_file', cdp_control_state: 'not_checked', stages: []};
    let browser;
    try {
      await persist(receiptFile, receipt);
      const deadline = Date.now() + 15000;
      let ws;
      while (!ws) {
        try { ws = await endpoint(slot); }
        catch (error) {
          if (error.code !== 'ENOENT' || Date.now() >= deadline) throw error;
          await new Promise(resolve => setTimeout(resolve, 100));
        }
      }
      connection.stages.push({stage: 'endpoint_file', elapsed_ms: Date.now() - connectionStarted});
      connection.stage = 'cdp_connect'; await persist(receiptFile, receipt);
      const connectStarted = Date.now();
      browser = await bounded(() => chromium.connectOverCDP(ws, {timeout: 15000}), 15000, 'CDP connect', late => late.close());
      connection.stages.push({stage: 'cdp_connect', elapsed_ms: Date.now() - connectStarted});
      connection.stage = 'target_selection'; await persist(receiptFile, receipt);
      const selectionStarted = Date.now();
      const context = browser.contexts()[0];
      if (!context) throw new Error('Owned persistent browser context unavailable');
      let page;
      for (const candidate of context.pages()) {
        if (slot.target_id && await targetId(context, candidate) === slot.target_id) { page = candidate; break; }
      }
      if (page || !slot.target_id) {
        page ||= context.pages()[0] || await bounded(() => context.newPage(), 15000, 'Owned blank page creation');
        slot.target_id = await targetId(context, page);
      }
      // A closed business tab is reported as null, never recreated or navigated.
      browsers.push(browser); contexts.push(context); pages.push(page || null);
      connection.stages.push({stage: 'target_selection', elapsed_ms: Date.now() - selectionStarted});
      connection.cdp_control_state = 'connected'; connection.stage = 'ready';
      connection.elapsed_ms = Date.now() - connectionStarted; connection.finished_at = now();
      await persist(receiptFile, receipt);
    } catch (error) {
      connection.cdp_control_state = connection.stage === 'endpoint_file' ? 'not_checked' : 'failed';
      connection.error_name = error.name; connection.error_code = error.code || null;
      connection.elapsed_ms = Date.now() - connectionStarted; connection.finished_at = now();
      await persist(receiptFile, receipt);
      // Disconnect only connections created by this failed attempt. The browser
      // processes, profiles and original business pages remain untouched.
      await Promise.all([...new Set([...browsers, browser].filter(Boolean))].map(connected =>
        bounded(() => connected.close(), 5000, 'Failed preparation CDP disconnect').catch(() => {})));
      throw error;
    }
  }
  receipt.state = 'open'; receipt.ready_at ||= now(); receipt.connected_at = now();
  await persist(receiptFile, receipt);
  let bound = false, activeIndex = 0, closePromise;
  const pagesByAccount = new Map(), accountSlots = new Map();
  const session = {signature, browsers, browser: browsers[0], contexts, pages, pagesByAccount, closed: false,
    async enter(entryUrl) {
      if (session.closed || browsers.some(browser => !browser.isConnected())) throw new Error('Connection lost; rerun environment_setup to reconnect original browser');
      if (!bound) {
        const binding = JSON.parse(await fs.readFile(path.join(root, 'binding.json'), 'utf8'));
        const assigned = binding.native_context_binding?.contexts || [];
        if (!sameIdentity(binding, identity) || !binding.lease_id ||
            assigned.length !== (binding.account_ids || []).length || assigned.length > pages.length ||
            new Set(assigned.map(row => row.account_id)).size !== assigned.length ||
            new Set(assigned.map(row => row.context_id)).size !== assigned.length)
          throw new Error('Original account/environment assignment does not match');
        for (const row of assigned) {
          const index = receipt.environments.findIndex(item => item.context_id === row.context_id && item.origin === row.origin &&
            item.host_id === row.host_id && item.browser === row.browser && row.isolation === 'isolated');
          if (index < 0 || !binding.account_ids.includes(row.account_id)) throw new Error('Context not owned by this executor');
          pagesByAccount.set(row.account_id, pages[index]); accountSlots.set(row.account_id, index);
          if (row === assigned[0]) activeIndex = index;
        }
        bound = true;
      }
      const page = pages[activeIndex], slot = receipt.slots[activeIndex];
      if (!page || page.isClosed()) throw new Error('Original tab closed; inspect context.pages() and explicitly select a page with selectPage()');
      if (!slot.entered) {
        const entry = new URL(entryUrl);
        if (entry.origin !== url.origin || entry.username || entry.password) throw new Error('Entry target changed');
        slot.entered = true;
        await persist(receiptFile, receipt); // Unknown navigation is never replayed.
        await page.goto(entry.href, {waitUntil: 'domcontentloaded', timeout: 15000});
      }
      return page;
    },
    async selectPage(index, page) {
      if (!contexts[index]?.pages().includes(page)) throw new Error('Page is not in this owned context');
      pages[index] = page;
      for (const [account, slot] of accountSlots) if (slot === index) pagesByAccount.set(account, page);
      receipt.slots[index].target_id = await targetId(contexts[index], page);
      receipt.slots[index].entered = true;
      await persist(receiptFile, receipt);
      return page;
    },
    async close() {
      if (!closePromise) closePromise = closeOwned({assignment_file: assignmentFile, directory: root,
        runtime_context: runtimeContext}).then(proof => { session.closed = true; return proof; })
        .catch(error => { closePromise = undefined; throw error; });
      return closePromise;
    }
  };
  environments.set(root, session);
  return session;
}

// For a genuinely exited browser, including partial startup. This only checks
// owned processes and records evidence; it never kills or restarts a browser.
export async function confirmExit(directory) {
  const root = path.resolve(directory), file = path.join(root, 'browser-environment.json');
  const receipt = JSON.parse(await fs.readFile(file, 'utf8'));
  if (receipt.schema !== 2) throw new Error('Legacy exit requires the original executor evidence');
  const evidence = await Promise.all(receipt.slots.map(slot => ownedProcesses(slot)));
  if (evidence.some(item => requireKnownProcess(item).length)) throw new Error('Owned browser still running; no exit confirmed');
  return recordExit(root, file, receipt, evidence);
}
async function recordExit(root, file, receipt, evidence) {
  receipt.exit_process_evidence = evidence;
  receipt.state = 'closed'; receipt.closed_at = now();
  await persist(file, receipt);
  const session = environments.get(root); if (session) session.closed = true;
  return {browser_stopped: true, reason: 'All original private-profile browser processes confirmed absent',
    context_ids: receipt.environments.map(row => row.context_id)};
}

// Explicit cleanup also works after partial startup or a lost REPL. It connects
// only living owned profiles, never starts a dead slot or replays any business.
export async function closeOwned({assignment_file, directory, runtime_context = {}}) {
  const root = path.resolve(directory), file = path.join(root, 'browser-environment.json');
  const receipt = JSON.parse(await fs.readFile(file, 'utf8'));
  const assignment = JSON.parse(await fs.readFile(assignment_file, 'utf8'));
  if (receipt.schema !== 2 || !sameIdentity(receipt.identity, assignment))
    throw new Error('Original owned environment receipt required');
  const {chromium} = await installedRuntime(assignment.direct_browser || {}, assignment_file, runtime_context);
  receipt.close_started_at = now(); await persist(file, receipt);
  const errors = [];
  for (const slot of receipt.slots) {
    const evidence = await ownedProcesses(slot);
    slot.close_process_evidence = evidence;
    await persist(file, receipt);
    if (!['present', 'absent'].includes(evidence.process_state)) {
      errors.push('Owned process state unknown or ambiguous; preserve original slot'); continue;
    }
    const pids = evidence.pids;
    if (!pids.length) continue;
    let browser;
    try {
      const deadline = Date.now() + 5000;
      const ws = await endpoint(slot);
      browser = await bounded(() => chromium.connectOverCDP(ws, {timeout: 5000}), deadline - Date.now(), 'Cleanup CDP connect', late => late.close());
      const cdp = await bounded(() => browser.newBrowserCDPSession(), deadline - Date.now(), 'Cleanup CDP session', late => late.detach());
      await bounded(() => cdp.send('Browser.close'), deadline - Date.now(), 'Owned browser close');
    } catch (error) { errors.push(String(error)); }
    finally { if (browser?.isConnected()) await bounded(() => browser.close(), 5000, 'Cleanup CDP disconnect').catch(() => {}); } // CDP disconnect only.
  }
  const deadline = Date.now() + 5000;
  while (true) {
    const evidence = await Promise.all(receipt.slots.map(slot => ownedProcesses(slot, deadline - Date.now())));
    const states = evidence.map(item => requireKnownProcess(item));
    if (states.every(pids => !pids.length)) return recordExit(root, file, receipt, evidence);
    if (Date.now() >= deadline) throw new Error('Owned browser exit unconfirmed; preserve binding. ' + errors.join('; '));
    await new Promise(resolve => setTimeout(resolve, Math.min(100, deadline - Date.now())));
  }
}
