// Local artifacts only. No browser control, platform credentials or model loop.
async function nativeReadObservationReceipt(directory, request_id, {reconcile = false} = {}) {
  if (!/^[0-9]+-[a-f0-9]+$/.test(request_id)) throw new Error('Invalid observation request ID');
  if (reconcile) {
    const fs = await import('node:fs/promises');
    const {constants} = await import('node:fs');
    const abort = new AbortController(), events = fs.watch(directory, {signal: abort.signal});
    let timer;
    try {
      const changed = events.next().catch(() => ({done:true}));
      const fifo = await fs.open(directory + '/native-observations.fifo', constants.O_WRONLY | constants.O_NONBLOCK);
      try { await fifo.writeFile(JSON.stringify({request_id,reconcile:true}) + '\n'); } finally { await fifo.close(); }
      await Promise.race([changed, new Promise(resolve => {timer = setTimeout(resolve, 10000);})]);
    } finally {clearTimeout(timer);abort.abort();await events.return();}
  }
  const fs = await import('node:fs/promises');
  for (const file of [directory + '/native-receiver-response-' + request_id + '.json', directory + '/native-receiver-response.json']) {
    try { const value = JSON.parse(await fs.readFile(file, 'utf8'));
      if (value.request_id === request_id) return value;
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  return {request_id, saved: false, pending: true};
}
async function nativeSendObservation(directory, observation, {wait_ms = 10000} = {}) {
  const fs = await import('node:fs/promises');
  const {constants} = await import('node:fs');
  const awaiting = directory + '/native-observation-awaiting.json';
  try {
    const previous = JSON.parse(await fs.readFile(awaiting, 'utf8'));
    const result = await nativeReadObservationReceipt(directory, previous.request_id);
    if (result.saved !== true && !['not_sent','rejected'].includes(result.state)) return {...result, new_observation_sent: false};
    await fs.unlink(awaiting);
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (!Number.isFinite(wait_ms) || wait_ms < 0 || wait_ms > 20000) throw new Error('Invalid receipt observation budget');
  const request_id = String(Date.now()) + '-' + Math.random().toString(16).slice(2);
  const abort = new AbortController();
  const events = fs.watch(directory, {signal: abort.signal});
  const next = () => events.next().catch(error => ({done:true,error}));
  let changed = next(), timer;
  const deadline = new Promise(resolve => { timer = setTimeout(() => resolve({done:true}), wait_ms); });
  try {
    await fs.writeFile(directory + '/observation-inbox-' + request_id + '.json', JSON.stringify(observation), {encoding:'utf8',mode:0o600,flag:'wx'});
    await fs.writeFile(directory + '/native-last-observation.json', JSON.stringify({request_id}), {encoding:'utf8',mode:0o600});
    await fs.writeFile(awaiting, JSON.stringify({request_id}), {encoding:'utf8',mode:0o600,flag:'wx'});
    let inbox;
    try { inbox = await fs.open(directory + '/native-observations.fifo', constants.O_WRONLY | constants.O_NONBLOCK); }
    catch (error) {
      if (!['ENOENT','ENXIO'].includes(error.code)) throw error;
      const result = {request_id, saved:false, state:'not_sent', error:String(error)};
      await fs.writeFile(directory + '/native-receiver-response-' + request_id + '.json', JSON.stringify(result), {encoding:'utf8',mode:0o600});
      await fs.unlink(awaiting);
      return result; // No notification reached a receiver; Codex can repair it.
    }
    try { await inbox.writeFile(JSON.stringify({request_id}) + '\n'); }
    finally { await inbox.close(); }
    let result = await nativeReadObservationReceipt(directory, request_id);
    while (result.pending) {
      const event = await Promise.race([changed, deadline]);
      result = await nativeReadObservationReceipt(directory, request_id);
      if (event.done) break;
      changed = next();
    }
    if (result.saved === true || ['not_sent','rejected'].includes(result.state)) await fs.unlink(awaiting);
    // Deadline means the save is still unknown. Keep the browser, journal and
    // original request; read this receipt later, never send the business again.
    return result;
  } finally { clearTimeout(timer); abort.abort(); await events.return(); }
}
