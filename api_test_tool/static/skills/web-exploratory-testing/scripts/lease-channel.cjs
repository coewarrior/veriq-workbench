'use strict';
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');

// Only the optional auxiliary helper uses this channel. Ordinary browser calls,
// their batching and the existing tool-internal wait path are untouched.
async function bindLease(binding, directory, close, writePrivate) {
  if (!binding) return null; // Existing non-platform browser sessions.
  const base = new URL(binding.url);
  if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password ||
      base.pathname !== '/' || base.search || base.hash) throw Error('invalid_platform_origin');
  const url = base.origin;
  const digest = crypto.createHash('sha256').update(url).digest('hex').slice(0, 16);
  const credentialFile = binding.credential_file || path.join(os.homedir(), '.local/state/api-test-mcp', digest + '.json');
  const credential = JSON.parse(fs.readFileSync(credentialFile, 'utf8'));
  if (credential.url !== url || !credential.token || !binding.lease_id || !binding.holder_id) throw Error('invalid_lease_binding');
  const channelId = crypto.randomUUID();
  let lastContact = Date.now(), progress = 0, stopped = false, timer, watchdog, retainScene = false;
  writePrivate(path.join(directory, 'lease-binding.json'), {
    lease_id: binding.lease_id, channel_id: channelId, pid: process.pid,
    process_started: Date.now() / 1000 - process.uptime(),
  });
  const call = async event => {
    const response = await fetch(url + '/api/mcp/call', {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(10000),
      headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + credential.token},
      body: JSON.stringify({action: 'direct_session', arguments: {
        action: 'channel', holder_id: binding.holder_id, lease_id: binding.lease_id,
        arguments: {event, channel_id: channelId, directory, pid: process.pid, progress},
      }}),
    });
    if (!response.ok) throw Error('lease_channel_unavailable');
    const result = await response.json(); lastContact = Date.now(); return result;
  };
  let result;
  try {
    result = await call('register');
  } catch (error) {
    // The server may commit registration after the HTTP caller times out.
    // Close the browser and durably prove that fact before this process exits;
    // the original Runner can then settle the late registration safely.
    await close();
    writePrivate(path.join(directory, 'startup-failure.json'), {
      channel_id: channelId, stage: 'register', error_type: error.name,
      browserClosed: true, occurredAt: Date.now(),
    });
    try { await call('closed'); } catch (_) { /* Runner reads closed.json. */ }
    throw error;
  }
  if (result.revoked) throw Error('lease_revoked');
  let ready = result.allowed;
  const pulse = async () => {
    if (stopped) return;
    try {
      const state = await call('heartbeat');
      ready = state.allowed;
      retainScene = !!state.retain_scene;
      if (state.revoked || state.closed) { await close(retainScene && !state.closed); return; }
    } catch (_) { ready = false; }
    if (!stopped) timer = setTimeout(pulse, 3000);
  };
  watchdog = setInterval(() => {
    if (!stopped && Date.now() - lastContact > 40000) close(retainScene).catch(() => {});
  }, 1000);
  timer = setTimeout(pulse, 0);
  return {
    get ready() { return ready && !stopped; },
    progress() { progress += 1; },
    fenced() { stopped = true; ready = false; clearTimeout(timer); clearInterval(watchdog); },
    async closed() {
      stopped = true; ready = false; clearTimeout(timer); clearInterval(watchdog);
      writePrivate(path.join(directory, 'lease-return.json'), {channel_id: channelId, state: 'returning'});
      // Retry only the exit receipt; never a browser action. The original host
      // also proves process exit before releasing a crashed helper's account.
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const receipt = await call('closed');
          writePrivate(path.join(directory, 'lease-return.json'), {channel_id: channelId, state: 'settled', receipt});
          return;
        } catch (_) { if (attempt < 2) await new Promise(resolve => setTimeout(resolve, 1000)); }
      }
    },
  };
}
module.exports = {bindLease};
