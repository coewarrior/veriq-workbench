// Local, task-owned Playwright controller. No stdin transport or automatic replay.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const {actAndWait} = require('./execution-guard.cjs');
const {bindLease} = require('./lease-channel.cjs');

function writePrivate(file, data) {
  const temporary = file + '.' + crypto.randomUUID() + '.tmp';
  try {
    fs.writeFileSync(temporary, JSON.stringify(data), {mode: 0o600, flag: 'wx'});
    fs.renameSync(temporary, file);
  } finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
}

// Persist IDs before invoking a job. A lost HTTP response can only be reconciled,
// never turn into an implicit second click/upload. Results are private local data.
function createJobs(directory, state) {
  let active = null;
  const file = id => {
    if (typeof id !== 'string' || !/^[a-zA-Z0-9_-]{1,100}$/.test(id)) throw Error('invalid_job_id');
    return path.join(directory, id + '.json');
  };
  return {
    get active() { return active; },
    read(id) { return JSON.parse(fs.readFileSync(file(id), 'utf8')); },
    submit(id, code) {
      const destination = file(id);
      if (typeof code !== 'string' || !code.trim()) throw Error('empty_job');
      const fingerprint = crypto.createHash('sha256').update(code).digest('hex');
      if (fs.existsSync(destination)) {
        const previous = this.read(id);
        if (previous.fingerprint !== fingerprint) throw Error('job_id_conflict');
        return {id, status: previous.status, replayed: false};
      }
      if (active) throw Error('session_busy');
      const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
      const execute = new AsyncFunction('s', code); // Only authenticated local task scripts.
      writePrivate(destination, {id, fingerprint, status: 'running', startedAt: Date.now()});
      active = id;
      if (state.onProgress) state.onProgress();
      Promise.resolve().then(() => execute(state)).then(result => {
        writePrivate(destination, {id, fingerprint, status: 'completed', completedAt: Date.now(), result});
      }).catch(error => {
        // Do not serialize exception text: browser errors may contain entered secrets.
        writePrivate(destination, {id, fingerprint, status: 'uncertain', completedAt: Date.now(),
          error: {type: error instanceof TypeError ? 'TypeError' : 'CommandError',
            message: 'Inspect the bound page and reconcile this job before any retry.'}});
      }).catch(() => {
        // Preserve the durable running marker if writing the outcome failed.
      }).finally(() => { active = null; if (state.onProgress) state.onProgress(); });
      return {id, status: 'running', replayed: false};
    },
  };
}

async function serve(runtimeFile, directory) {
  directory = path.resolve(directory);
  // A new directory is an ownership boundary. Never overwrite another session.
  fs.mkdirSync(directory, {mode: 0o700});
  const jobsDir = path.join(directory, 'jobs');
  fs.mkdirSync(jobsDir, {mode: 0o700});
  let browser, server, lease, close;
  try {
    const runtime = JSON.parse(fs.readFileSync(runtimeFile, 'utf8'));
    const {chromium} = require(runtime.module);
    browser = await chromium.launch({headless: true, ...(runtime.channel ? {channel: runtime.channel} : {})});
    const context = await browser.newContext();
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.setDefaultNavigationTimeout(30000);
    const state = {browser, context, page, directory, actAndWait, fs, path, data: {}};
    const jobs = createJobs(jobsDir, state);
    const token = crypto.randomBytes(32).toString('hex');
    let closing = false;
    let retained = false;
    close = async (retain = false) => {
      if (closing && !(retained && !retain)) return;
      closing = true;
      if (retain) {
        retained = true;
        if (lease) lease.fenced();
        // Preserve the page while fencing subsequent traffic. The original host
        // retains the account and owns the process until explicit resolution.
        await context.route('**/*', route => route.abort());
        await context.setOffline(true);
        if (server) server.close();
        writePrivate(path.join(directory, 'retained.json'), {retainedAt: Date.now(), accountReleased: false});
        return;
      }
      await browser.close();
      // Persist physical exit before any network ACK can time out.
      writePrivate(path.join(directory, 'closed.json'), {closedAt: Date.now(), browserClosed: true});
      if (lease) await lease.closed();
      if (fs.existsSync(path.join(directory, 'session.json'))) fs.unlinkSync(path.join(directory, 'session.json'));
      if (server) server.close();
    };
    lease = await bindLease(runtime.lease_binding, directory, close, writePrivate);
    if (lease) state.onProgress = () => lease.progress();
    server = http.createServer(async (req, res) => {
      const reply = (status, value) => {
        res.writeHead(status, {'Content-Type': 'application/json', Connection: 'close'});
        res.end(JSON.stringify(value));
      };
      if (req.headers.origin || req.headers.authorization !== 'Bearer ' + token) return reply(403, {error: 'unauthorized'});
      try {
        const url = new URL(req.url, 'http://127.0.0.1');
        if (req.method === 'GET' && url.pathname === '/status') {
          return reply(200, {ready: !closing && browser.isConnected() && (!lease || lease.ready), active: jobs.active, leaseBound: !!lease});
        }
        if (req.method === 'GET' && url.pathname === '/result') {
          return reply(200, jobs.read(url.searchParams.get('id')));
        }
        if (req.method === 'POST' && url.pathname === '/close') {
          if (jobs.active) return reply(409, {error: 'session_busy'});
          await close();
          return reply(200, {closed: true});
        }
        if (req.method !== 'POST' || url.pathname !== '/run' || closing) return reply(404, {error: 'not_available'});
        if (lease && !lease.ready) return reply(409, {error: 'lease_not_ready'});
        let size = 0, chunks = [];
        for await (const chunk of req) {
          size += chunk.length;
          if (size > 1024 * 1024) return reply(413, {error: 'job_too_large'});
          chunks.push(chunk);
        }
        const job = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        reply(202, jobs.submit(job.id, job.code));
      } catch (error) {
        const known = ['invalid_job_id', 'empty_job', 'job_id_conflict', 'session_busy'];
        reply(409, {error: known.includes(error.message) ? error.message : 'request_failed'});
      }
    });
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
    writePrivate(path.join(directory, 'session.json'), {port: server.address().port, token, pid: process.pid});
    // Handshake contains no token, login data or browser content.
    console.log(JSON.stringify({ready: !lease || lease.ready, directory, leaseBound: !!lease}));
    process.once('SIGTERM', () => { close().catch(() => { process.exitCode = 1; }); });
    process.once('SIGINT', () => { close().catch(() => { process.exitCode = 1; }); });
    return {server, jobs, close};
  } catch (error) {
    if (close) await close().catch(() => {});
    else if (browser) await browser.close().catch(() => {});
    writePrivate(path.join(directory, 'startup-error.json'), {
      stage: 'startup', error_type: error.name, occurredAt: Date.now(),
      browserClosed: fs.existsSync(path.join(directory, 'closed.json')),
    });
    if (server) server.close();
    throw error;
  }
}

async function main(argv) {
  const [command, directory, ...rest] = argv;
  if (!directory || !['serve', 'run', 'result', 'status', 'close'].includes(command)) {
    throw Error('usage');
  }
  if (command === 'serve') {
    if (rest.length !== 1) throw Error('usage');
    return serve(rest[0], directory);
  }
  const session = JSON.parse(fs.readFileSync(path.join(directory, 'session.json'), 'utf8'));
  if (!Number.isInteger(session.port) || session.port < 1 || session.port > 65535 ||
      !/^[a-f0-9]{64}$/.test(session.token)) throw Error('invalid_session');
  const [id, file] = rest;
  if (['run', 'result'].includes(command) && (!id || !file)) throw Error('usage');
  const body = command === 'run' ? JSON.stringify({id, code: fs.readFileSync(file, 'utf8')}) : undefined;
  const response = await fetch('http://127.0.0.1:' + session.port +
    (command === 'result' ? '/result?id=' + encodeURIComponent(id) : '/' + command), {
    method: ['run', 'close'].includes(command) ? 'POST' : 'GET',
    headers: {Authorization: 'Bearer ' + session.token}, body, signal: AbortSignal.timeout(10000), redirect: 'error',
  });
  const result = await response.json();
  if (!response.ok) throw Error(result.error);
  if (command === 'result') {
    if (fs.existsSync(file) && fs.lstatSync(file).isSymbolicLink()) throw Error('unsafe_output');
    writePrivate(path.resolve(file), result);
    console.log(JSON.stringify({id, status: result.status, saved: path.resolve(file)}));
  } else console.log(JSON.stringify(result));
}

module.exports = {actAndWait, createJobs, serve};
if (require.main === module) main(process.argv.slice(2)).catch(error => {
  console.error(JSON.stringify({error_type: error.name, command: process.argv[2],
    instruction: process.argv[2] === 'serve' ? 'Read startup-error.json and startup-failure.json; no helper business job was started.' :
      'Read status/result for the same job ID; do not replay uncertain actions.'}));
  process.exitCode = 1;
});
