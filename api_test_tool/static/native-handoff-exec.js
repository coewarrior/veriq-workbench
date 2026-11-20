// Runs inside functions.exec, with callNative supplied by the current client.
// The only desktop mutation is the existing send_message_to_thread tool.
function nativeHandoffEvents(result, action) {
  return result.handoff_route === 'direct_successors'
    ? [...(result.continuations || []), ...(result.handoff?.delivery_required ? [result.handoff] : [])]
    : action === 'dispatch'
    ? (result.continuations || (result.continuation ? [result.continuation] : []))
    : (result.handoff ? [result.handoff] : []);
}
function nativeHandoffBinding(event) {
  return JSON.stringify([event?.task_id,event?.node_id,event?.task_revision,event?.node_revision,
    event?.coordinator_ref,event?.claim_arguments?.holder_id,event?.claim_arguments?.dispatch_id,
    event?.claim_arguments?.executor_ref]);
}
function nativeHandoffResult(result, action, failures = result.handoff_failures || []) {
  const source = result.handoff;
  const receipts = [source,...(result.continuations || (result.continuation ? [result.continuation] : []))].filter(Boolean);
  for (const failure of failures) {
    if (failure.resolved || !source || source.id !== failure.event_id ||
        nativeHandoffBinding(source) !== failure.source_binding) continue;
    const notice = receipts.find(item => item.id === failure.notice_id &&
      nativeHandoffBinding(item) === failure.target_binding);
    // An invalidated original source also invalidates its omitted notices.
    // A different event or binding can never settle this attempt's history.
    const evidence = source.delivery_state === 'obsolete' ? source : notice;
    if (evidence && (['received','obsolete'].includes(evidence.delivery_state) || evidence.claim_received_at)) {
      failure.resolved = true;
      failure.resolution = {event_id:source.id,notice_id:evidence.id,
        delivery_state:evidence.delivery_state,claim_received_at:evidence.claim_received_at};
    }
  }
  const pending = Boolean(result.handoff_error) || failures.some(item => !item.resolved) || nativeHandoffEvents(result, action).some(item =>
    ['pending','sending','unknown','blocked','unbound'].includes(item.delivery_state));
  return {...result, ...(failures.length ? {handoff_failures:failures} : {}),
    needs_handoff:pending,handoff_complete:!pending};
}
async function completeNativeHandoff(callNative, initialArguments, sendMessage, initialResult) {
  const timing = [];
  const measured = async (stage, call) => {
    const item = {stage, started_at: new Date().toISOString()};
    timing.push(item);
    try {
      const result = await call();
      if (result?.server_processing_timing) item.server_processing_timing = result.server_processing_timing;
      if (result?.client_wait) item.client_wait = result.client_wait;
      return result;
    }
    finally { item.finished_at = new Date().toISOString(); }
  };
  const measuredCall = args => measured(args.arguments?.handoff_delivery ? 'delivery_' + args.arguments.handoff_delivery.state :
    args.arguments?.handoff_ack ? 'coordinator_ack' : args.record_action === 'publish' ? 'publication_after_handoff' : 'release_publish',
    () => callNative(args));
  const measuredSend = typeof sendMessage === 'function' ? args => measured('desktop_send', () => sendMessage(args)) : sendMessage;
  const publicationBinding = initialArguments.arguments?.publication_binding;
  const defer = !initialResult && initialArguments.action === 'finish' && initialArguments.arguments?.publish_saved === true
    && publicationBinding?.project_id && publicationBinding?.execution_id && Number.isInteger(publicationBinding?.revision);
  const releaseArguments = defer ? {...initialArguments, arguments: {...initialArguments.arguments,
    publish_saved: false, report_pending: true}} : initialArguments;
  let result = await completeNativeHandoffSteps(measuredCall, releaseArguments, measuredSend, initialResult);
  // Account return and actual successor delivery complete before report work.
  // Use the existing released-holder record endpoint; no new claim or protocol.
  if (defer && result.released === true) {
    let published;
    try {
      published = await measuredCall({action: 'record', record_action: 'publish',
        ...Object.fromEntries(['holder_id','task_id','node_id','lease_id','dispatch_id','executor_ref']
          .filter(key => key in initialArguments).map(key => [key, initialArguments[key]])),
        arguments: publicationBinding});
      result = {...result, ...published};
    } catch (_) {
      result = {...result, publication: {phase: 'unknown', pending: true,
        message: '账号已交还，后继通知按原回执保留；报告发布未确认，沿原绑定核对，不重跑业务。'}};
    }
    if (published?.handoff || published?.continuations) {
      try {
        const final = await completeNativeHandoffSteps(measuredCall, releaseArguments, measuredSend, published);
        const failures = [...(result.handoff_failures || []),...(final.handoff_failures || [])];
        result = {...result, ...final, ...(failures.length ? {handoff_failures:failures} : {})};
      } catch (_) {
        // Publication is already confirmed. A later delivery failure cannot
        // turn it into a failed report or justify another publication.
        result = {...result, needs_handoff: true, handoff_error: 'post_publication_delivery_unconfirmed'};
      }
    }
  }
  result = nativeHandoffResult(result, initialArguments.action);
  if (initialArguments.action === 'finish') {
    const compact = event => event && Object.fromEntries(
      ['id','task_id','node_id','source_event_id','kind','delivery_state','delivery_required',
       'sent_at','received_at','claim_received_at','claimed_at','failure_stage'].filter(key => key in event).map(key => [key,event[key]]));
    result = {...result, handoff: compact(result.handoff),
      continuations: (result.continuations || []).map(compact), continuation: compact(result.continuation)};
    delete result.coordination_plan;
    delete result.handoff_observation;
  }
  return {...result, handoff_timing: timing};
}
async function completeNativeHandoffSteps(callNative, initialArguments, sendMessage, initialResult) {
  let result = initialResult ?? await callNative(initialArguments);
  const publication = result.publication;
  const handled = new Set(), failures = [];
  const failure = (event, stage, state, persisted = false) => {
    const item = {event_id: result.handoff?.id || event.source_event_id || event.id,
      source_task_id: result.handoff?.task_id || initialArguments.task_id,
      source_node_id: result.handoff?.node_id || initialArguments.node_id,
      notice_id: event.id, target_task_id: event.task_id, target_node_id: event.node_id,
      target_thread_id: event.message_arguments?.threadId || event.coordinator_ref || null,
      source_binding:nativeHandoffBinding(result.handoff),target_binding:nativeHandoffBinding(event),
      failure_stage: stage, observed_delivery_state: state, failure_persisted: persisted};
    failures.push(item);
    return item;
  };
  const finish = () => nativeHandoffResult({...result, ...(publication ? {publication} : {})},
    initialArguments.action, failures);
  while (true) {
    const direct = result.handoff_route === "direct_successors";
    const events = nativeHandoffEvents(result, initialArguments.action);
    const event = events.find(item => item.delivery_state === "pending" && !handled.has(item.id));
    if (!event) return finish();
    handled.add(event.id);
    const attempt = event.id + ":desktop-exec-v1";
    const notificationArguments = {...(initialArguments.arguments || {})};
    for (const key of ['modules','continuation_group','final_report','publish_saved','publication_binding',
      'save_unconfirmed','report_pending']) delete notificationArguments[key];
    const update = (state, failure_stage) => ({...initialArguments, arguments: {
      ...notificationArguments, handoff_delivery: {event_id: event.id,
        thread_id: event.message_arguments?.threadId || event.coordinator_ref,
        attempt_id: attempt, state, ...(failure_stage ? {failure_stage} : {})}}});
    const preflight = event.message_tool !== "send_message_to_thread" || !event.message_arguments?.threadId
      ? 'message_target' : typeof sendMessage !== 'function' ? 'message_tool' : null;
    if (preflight) {
      const item = failure(event, preflight, 'blocked');
      try { result = await callNative(update('blocked', preflight)); item.failure_persisted = true; }
      catch (_) { item.reconciliation = 'original_event_receipt_unconfirmed'; }
      // The persisted worker failure makes the SAME coordinator event sendable.
      // A missing desktop tool also prevents that send; report both facts.
      if (direct) continue;
      return finish();
    }
    let begin;
    try { begin = await callNative(update("sending")); }
    catch (_) {
      const item = failure(event, 'delivery_begin', 'unknown');
      // No message was sent. A lost begin may have installed the original fence.
      // Reconcile that exact attempt once, never repeat the sending begin.
      try { result = await callNative(update('unknown', 'delivery_begin')); item.failure_persisted = true; }
      catch (_) { item.reconciliation = 'original_event_receipt_unconfirmed'; }
      if (direct) continue;
      return finish();
    }
    const authorized = direct || initialArguments.action === "dispatch"
      ? begin.send_authorized : begin.handoff?.send_authorized;
    if (authorized !== true) {
      result = begin;
      if (!direct) return finish();
      continue;
    }
    let state = "unknown";
    try {
      const sent = await sendMessage(event.message_arguments);
      const values = [sent, sent?.structuredContent];
      for (const item of sent?.content || []) {
        if (item.type === "text") { try { values.push(JSON.parse(item.text)); } catch (_) {} }
      }
      if (sent?.isError === true || values.some(value => value && (
        value.success === false || value.sent === false ||
        ["blocked", "denied", "rejected", "failed", "needs_approval"].includes(value.status)))) state = "blocked";
      else if (values.some(value => value && (value.error ||
        ["unknown", "pending", "sending", "needs_confirmation"].includes(value.status)))) state = "unknown";
      else if (values.some(value => value && (value.sent === true || value.success === true ||
        (value.threadId === event.message_arguments.threadId && Object.keys(value).length === 1) ||
        ["sent", "queued", "started", "success", "submitted"].includes(value.status)))) state = "sent";
    } catch (_) { /* An accepted desktop message can lose its response. */ }
    let issue = state !== 'sent' ? failure(event, 'desktop_send', state) : null;
    try {
      result = await callNative(update(state, issue?.failure_stage));
      if (issue) issue.failure_persisted = true;
    } catch (_) {
      issue = issue || failure(event, 'delivery_receipt', state);
      // Repeating the exact result ACK cannot send or replay business. A single
      // read/write reconciliation also exposes the coordinator fault route.
      try {
        result = await callNative(update(state, 'delivery_receipt'));
        issue.failure_persisted = true;
        issue.resolved = state === 'sent';
      }
      catch (_) { result = begin; issue.reconciliation = 'original_event_receipt_unconfirmed'; }
    }
    if (state !== 'sent' && !direct) return finish();
  }
}
