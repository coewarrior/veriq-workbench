// Execute in functions.exec with tools/text/ALL_TOOLS/input explicitly supplied.
// Browser actions stay in the supported native browser tool, never a proxy.
const quote = s => "'" + String(s).replace(/'/g, "'\\''") + "'";
const now = () => new Date().toISOString();
const stages = [];
async function command(args, stage, awaitReceiver = false) {
  const started_at = now();
  const controlFile = config.control_receipts ? config.directory + '/control-' + stage + '-' + Date.now() + '-' + stages.length + '.json' : null;
  if (controlFile) args = [...args, '--control-result-file', controlFile];
  let r = await tools.exec_command({cmd: [...config.command, ...args].map(quote).join(' '),
    max_output_tokens: 16000, yield_time_ms: 10000});
  let output = r.output;
  while (r.session_id && r.exit_code == null) {
    if (awaitReceiver) {
      let packet;
      try { packet = JSON.parse(output); } catch (_) { /* stdout can arrive in chunks */ }
      if (packet?.receiver_ready === true && packet.prepared?.ready === true) {
        stages.push({stage, started_at, finished_at: now(), receiver_ready: true});
        return {...packet.prepared, observation_receiver: {session_id: r.session_id, fifo: packet.fifo}};
      }
    }
    r = await tools.write_stdin({session_id: r.session_id, chars: '', yield_time_ms: 1000, max_output_tokens: 16000});
    output += r.output;
  }
  stages.push({stage, started_at, finished_at: now(), exit_code: r.exit_code});
  if (r.exit_code !== 0) throw new Error(output.slice(-3000));
  if (controlFile) return await nativeReadControl(tools, config.command, controlFile);
  return JSON.parse(output);
}
const binding = config.directory + '/binding.json';
async function closeout(saveUnconfirmed = false, deferReport = false, outcome = 'completed') {
  if (input.from_observation !== true && (input.browser_stopped !== true || typeof input.reason !== 'string' || !input.reason.trim()))
    throw new Error('Actual browser exit and reason required');
  const generated = await command(['native-closeout-script', '--binding-file', binding,
    '--outcome', outcome,
    ...(saveUnconfirmed ? ['--save-unconfirmed'] : []),
    ...(deferReport ? ['--defer-report'] : []),
    ...(input.from_observation === true ? ['--observed-exit'] :
      ['--browser-stopped', '--reason', input.reason])], 'closeout_generate');
  let receipt;
  const started_at = now();
  const AF = Object.getPrototypeOf(async function() {}).constructor;
  await new AF('tools', 'text', 'ALL_TOOLS', generated.script)(tools, v => { receipt = v; }, ALL_TOOLS);
  stages.push({stage: deferReport ? 'release_handoff' : 'release_publish_handoff', started_at, finished_at: now()});
  return {...receipt, ...(generated.review_state ? {review_state: generated.review_state} : {})};
}
async function publishSaved() {
  const result = await command(['native-publish-saved', '--binding-file', binding,
    '--receipt-file', config.directory + '/publication-result.json'], 'publish_saved');
  if (result.handoff_script) {
    const started_at = now();
    const AF = Object.getPrototypeOf(async function() {}).constructor;
    let handoff;
    await new AF('tools', 'text', 'ALL_TOOLS', result.handoff_script)(tools, v => { handoff = v; }, ALL_TOOLS);
    stages.push({stage: 'report_handoff', started_at, finished_at: now()});
    delete result.handoff_script;
    result.handoff = handoff;
  }
  return result;
}
let result, failure;
try {
  if (input.action === 'work_plan') {
    if (typeof input.plan_file !== 'string') throw new Error('Explicit work plan file required');
    result = await command(['native-work-plan','--binding-file',binding,'--plan-file',input.plan_file,
      '--entry-url', config.entry_url], 'work_plan');
  } else if (input.action === 'cleanup') {
    if (typeof input.events_file !== 'string') throw new Error('Original cleanup evidence file required');
    result = await command(['native-cleanup','--binding-file',binding,'--events-file',input.events_file], 'cleanup');
  } else if (input.action === 'work') {
    if (typeof input.unit_id !== 'string') throw new Error('Original work unit id required');
    result = await command(['native-work-boundary','--binding-file',binding,'--unit-id',input.unit_id], 'work_boundary');
  } else if (input.action === 'resume') {
    if (!input.notification || typeof input.notification !== 'object') throw new Error('Original resume notification required');
    result = await command(['native-resume', '--assignment-file', config.assignment_file,
      '--directory', config.directory, '--notification-json', JSON.stringify(input.notification)], 'resume');
  } else if (input.action === 'stage_ready') {
    result = await command(['native-stage-ready', '--assignment-file', config.assignment_file,
      '--directory', config.directory], 'stage_ready');
  } else if (input.action === 'prepare') {
    result = await command(['native-prepare', '--summary', '--assignment-file', config.assignment_file,
      '--design-file', config.design_file, '--directory', config.directory,
      ...(input.resume === true ? ['--resume'] : []),
      ...(config.observation_stream === true ? ['--receive-observations'] : [])], 'prepare', config.observation_stream === true);
    result.entry_url = config.entry_url;
    if (result.ready && config.observation_stream === true && !result.observation_receiver)
      throw new Error('Observation receiver not ready; stop before browser business');
  } else if (input.action === 'record') {
    // Persist the exact observation before attempting the POST, including failures.
    const fromFile = input.observation_file !== undefined;
    if (fromFile && input.observation) throw new Error('Ambiguous observation source');
    if (fromFile && input.observation_file !== config.directory + '/observation-native.json')
      throw new Error('Observation must come from this run export');
    if (!fromFile && (!input.observation || typeof input.observation.case_id !== 'string')) throw new Error('Missing observation');
    const key = fromFile ? 'native' : encodeURIComponent(input.observation.case_id);
    const observationFile = config.directory + '/observation-' + key + '.json';
    const receiptFile = config.directory + '/receipt-' + key + '.json';
    result = await command(['native-observe', '--binding-file', binding,
      ...(fromFile ? ['--source-file', input.observation_file] : ['--observation-json', JSON.stringify(input.observation)]), '--observation-file', observationFile,
      '--receipt-file', receiptFile], 'save');
    if (input.finish_task === true && input.browser_stopped === true) result = {saved: result, closeout: await closeout()};
  } else if (input.action === 'review' || input.action === 'complete') {
    const finishing = input.action === 'review' && input.finish_task === true && input.browser_stopped === true;
    if (finishing) {
      result = {closeout: await closeout(false, true)};
      if (result.closeout.released !== true) throw new Error('Resource release not confirmed; preserve the original receipt');
    }
    // After explicit release, no account is required for original-record changes.
    // No changes means publish the already saved record without another save.
    if (input.action === 'complete' && input.input_file === undefined) {
      result = {publication: await publishSaved()};
    } else {
      if (typeof input.input_file !== 'string' || typeof input.receipt_file !== 'string')
        throw new Error('Review requires existing changes and a private receipt path');
      const saved = await command(['native-record', '--binding-file', binding, '--final-review',
        '--input-file', input.input_file, '--receipt-file', input.receipt_file], 'review_save');
      result = finishing || input.action === 'complete' ? {...result, saved} : saved;
      if (finishing || input.action === 'complete') result.publication = await publishSaved();
    }
  } else if (input.action === 'yield') result = await closeout(input.save_unconfirmed === true, false, 'yield');
  else if (input.action === 'release') result = await closeout(input.save_unconfirmed === true, true);
  else if (input.action === 'closeout') result = await closeout(input.save_unconfirmed === true);
  else throw new Error('Unknown cycle action');
} catch (error) {
  failure = String(error);
  // Only an explicitly requested finish may release a genuinely closed browser; a save error alone never ends a task.
  // Never retry the save or publish an incomplete observation as a successful report.
  if (['record', 'review'].includes(input.action) && input.finish_task === true && input.browser_stopped === true && !stages.some(s => s.stage === 'closeout_generate')) {
    try { result = {save_unconfirmed: true, closeout: await closeout(true)}; }
    catch (cleanupError) { result = {save_unconfirmed: true, cleanup_error: String(cleanupError)}; }
  }
}
const record = {action: input.action, result, ...(failure ? {error: failure} : {}), stages};
// Every invocation has its own artifact: no shared append race or overwritten failure receipt.
const log = config.directory + '/cycle-' + input.action + '-' + Date.now() + '.json';
await tools.apply_patch('*** Begin Patch\n*** Add File: ' + log + '\n+' + JSON.stringify(record, null, 2).replace(/\n/g, '\n+') + '\n*** End Patch');
// Keep the complete original receipt above. Omit only already-known static
// instructions from model display; dynamic warnings/plans/results stay intact.
const display = JSON.parse(JSON.stringify(record));
if (display.result?.baseline_receipt) delete display.result.baseline_receipt.title_guidance;
if (display.result?.execution_client) delete display.result.execution_client.handoff_guidance;
// These are invariant documentation strings repeated by every baseline save.
// Keep every case, runtime gap, plan, warning and unknown field in the response;
// the complete source receipt above remains available without another API call.
const baselineCoverage = display.result?.baseline_receipt?.coverage_check;
if (baselineCoverage) {
  for (const key of ['ai_analysis_guidance', 'requirement_basis_guidance',
    'reproduction_guidance', 'manual_action_guidance', 'upload_fallback_guidance',
    'not_run_guidance', 'guidance']) delete baselineCoverage[key];
}
display.full_receipt_file = log;
text(display);
if (failure) throw new Error(failure);
