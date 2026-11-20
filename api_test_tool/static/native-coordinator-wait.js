// Runs only inside the original coordinator's active functions.exec call.
// Actual desktop end receipts are persisted; no resource claims or chat restarts.
async function waitNativeCoordinator(callNative, waitThreads, sendMessage, config) {
  const started = Date.now(), cursors = {...(config.cursors || {})}, snapshots = new Map();
  const seen = new Set(config.seen_attention || []);
  const seenRecovery = {...(config.seen_recovery || {})};
  const observed = new Set(config.observed_turns || []);
  let windowMs;
  let views = [], calls = 0, waits = 0;
  const unpack = result => {
    if (result?.isError) return {errors: [{reason: 'desktop_wait_tool_error',
      message:(result.content || []).filter(item => item.type === 'text').map(item => item.text).join('\n').slice(0,1000)}]};
    if (result?.structuredContent) return result.structuredContent;
    for (const item of result?.content || []) if (item.type === 'text') {
      try { return JSON.parse(item.text); } catch (_) {}
    }
    return result;
  };
  const signature = item => JSON.stringify([item.task_id,item.node_id,item.event_id,item.notice_id,
    item.attention_reason,item.delivery_state,item.failure_stage,item.claim_received_at]);
  const observation = () => views.flatMap(view => view.coordination_plan?.handoff_observation?.events || []);
  const desktopEvidence = events => [...new Set(events.map(event => event.target_thread_id))]
    .map(id => snapshots.get(id)).filter(Boolean).map(item =>
      ({cursor:item.cursor,revision:item.revision,thread:item.thread,latestTurn:item.latestTurn}));
  const response = (reason, extra = {}) => ({reason, role: 'coordinator',
    task_ids:config.task_ids,
    elapsed_seconds: (Date.now() - started) / 1000, dispatch_reads: calls, desktop_waits: waits,
    cursors, seen_attention: [...seen], seen_recovery: {...seenRecovery}, observation: observation(),
    observed_turns:[...observed], closeout:views.map(view => ({task_id:view.task_id,...view.closeout})),
    active_tool_wait: false, background_monitor: false,
    ...extra});
  const read = async () => {
    views = [];
    for (const task_id of config.task_ids) {
      calls++;
      views.push(await callNative({action:'dispatch', task_id, holder_id:config.holder_id,
        coordinator_ref:config.coordinator_ref, arguments:{observe:true}}));
    }
  };
  try { await read(); }
  catch (_) { return response('platform_observation_unavailable', {action:'reconcile_original_tasks_no_restart'}); }
  config = {observation_seconds:views[0]?.coordination_plan?.handoff_observation?.observation_seconds || 120,...config};
  config.window_seconds ??= config.observation_seconds * 10;
  windowMs = config.window_seconds * 1000;
  let first = true;
  while (true) {
    const modules = views.flatMap(view => view.modules || []);
    const events = observation();
    const controls = views.flatMap(view => view.coordination_plan?.worker_actions || []);
    const issues = views.flatMap(view => view.coordination_plan?.coordinator_only || []).filter(item =>
      ['model_unavailable','blocked','isolated','retained','waiting_human','stopping'].includes(item.state));
    const freshIssues = [...controls,...issues].filter(item => !seen.has(JSON.stringify(item)));
    if (freshIssues.length) {
      freshIssues.forEach(item => seen.add(JSON.stringify(item)));
      return response('original_task_attention', {attention:freshIssues,
        action:'handle_original_control_or_blocker_only_keep_other_workers_running'});
    }
    // Saved condition changes wake this existing finite wait; no automatic
    // resend, case verdict rewrite or background recovery is started here.
    const recoveryAttention = [], pendingRecovery = [];
    for (const view of views) {
      if (view.intent !== 'run' || view.closeout?.disposition === 'ended') continue;
      for (const recovery of view.coordination_plan?.case_recovery || []) {
        if (recovery.pending_refs?.length) pendingRecovery.push({task_id:view.task_id,...recovery});
        for (const ref of recovery.pending_refs || []) {
          if (!ref.condition_signature) continue;
          const key = JSON.stringify([view.task_id,recovery.node_id,recovery.execution_id,
            recovery.dispatch_id,recovery.executor_ref,
            ref.case_id,ref.checkpoint_id || null]);
          const previous = seenRecovery[key];
          const available = (ref.conditions || []).filter(condition =>
            ['ready','resolved','passed','confirmed'].includes(condition.status) ||
            ['supplied_input','rule_update'].includes(condition.kind))
            .map(condition => condition.fact_signature || JSON.stringify(condition));
          seenRecovery[key] = {condition_signature:ref.condition_signature,available_conditions:available,
            ready_for_review:ref.ready_for_review};
          const newFacts = previous && available.some(fact => !(previous.available_conditions || []).includes(fact));
          if (newFacts || (ref.ready_for_review && !previous?.ready_for_review))
            recoveryAttention.push({task_id:view.task_id,node_id:recovery.node_id,
              execution_id:recovery.execution_id,source_revision:recovery.source_revision,
              executor_ref:recovery.executor_ref,dispatch_id:recovery.dispatch_id,...ref,
              attention_reason:previous ? 'original_condition_changed' : 'original_remaining_review'});
        }
      }
    }
    if (recoveryAttention.length) return response('case_recovery_attention', {
      attention:recoveryAttention,
      action:'review_original_remaining_conditions_then_resume_original_executor'});
    // A report-completed module can still contain original unfinished points.
    // Review their changed conditions before treating all modules as settled.
    if (!pendingRecovery.length && views.every(view => view.intent !== 'run' || view.closeout?.disposition === 'ended' ||
      (view.modules || []).every(module => ['completed','blocked','stopped'].includes(module.state) && !module.has_lease)))
      return response('original_tasks_ended_or_stopped', {action:'verify_original_exit_and_reports',
        tasks:views.map(view => ({task_id:view.task_id,intent:view.intent,modules:view.modules}))});
    const attention = events.filter(event => event.attention_reason && !seen.has(signature(event)));
    if (attention.length && (!first || attention.some(event =>
        ['pending_delivery','coordinator_event_pending'].includes(event.phase)))) {
      // Consume only genuinely pending original events. The existing ACK chain
      // rechecks bindings/resources and fences every real desktop send.
      const pending = attention.filter(event => event.current_binding &&
        ['pending_delivery','coordinator_event_pending'].includes(event.phase));
      const consumed = new Set(), receipts = [];
      for (const event of pending) {
        const key = event.task_id + ':' + event.event_id;
        if (consumed.has(key)) continue;
        consumed.add(key);
        try {
          const receipt = await completeNativeHandoff(callNative, {
            action:'dispatch', holder_id:config.holder_id, coordinator_ref:config.coordinator_ref,
            task_id:event.task_id, request_id:'coordinator-wait:' + event.event_id,
            arguments:{handoff_ack:{task_id:event.task_id,node_id:event.node_id,event_id:event.event_id}}}, sendMessage);
          receipts.push({event_id:event.event_id, needs_handoff:receipt.needs_handoff,
            handoff_failures:receipt.handoff_failures});
        } catch (_) { receipts.push({event_id:event.event_id, reason:'original_handoff_ack_unconfirmed'}); }
      }
      if (consumed.size) {
        try { await read(); } catch (_) { return response('platform_observation_unavailable', {receipts}); }
        const remaining = observation().filter(event => event.attention_reason && !seen.has(signature(event)));
        if (!remaining.length && receipts.every(receipt => !receipt.needs_handoff && !receipt.reason)) continue;
        if (first && remaining.length && remaining.every(event =>
            !['pending_delivery','coordinator_event_pending'].includes(event.phase))) continue;
      }
      const current = observation().filter(event => event.attention_reason && !seen.has(signature(event)));
      current.forEach(event => seen.add(signature(event)));
      return response('handoff_attention', {attention:current, receipts,desktop_evidence:desktopEvidence(current),
        action:'inspect_only_original_target_evidence_no_unknown_resend'});
    }
    if (Date.now() - started >= windowMs)
      return response(pendingRecovery.length ? 'continue_waiting_for_original_conditions' : 'observation_window_ended', {unchanged:true,
        pending_recovery:pendingRecovery,
        continuation:{...config,cursors,seen_attention:[...seen],seen_recovery:{...seenRecovery},observed_turns:[...observed]},
        instruction:'本次工具内等待已结束；正常无变化不代表失败。若继续观察须保持原协调回合并重新等待；回合退出后不会后台执行。'});
    if (typeof waitThreads !== 'function') return response('desktop_wait_tool_unavailable');
    const targets = [];
    for (const module of modules) {
      const binding = module.binding || {}, ref = (binding.executor_ref || '').replace(/^thread:/, '');
      const awaitingCondition = pendingRecovery.some(item => item.node_id === module.id && item.task_id === module.task_id);
      if (!ref || ref === config.coordinator_ref.replace(/^thread:/,'') ||
          (['completed','stopped','blocked'].includes(module.state) && !awaitingCondition)) continue;
      const target = (config.targets || []).find(item => item.threadId === ref) || {threadId:ref};
      if (!targets.some(item => item.threadId === ref && item.hostId === target.hostId))
        targets.push({...target, ...(cursors[ref] ? {afterCursor:cursors[ref]} : {})});
    }
    if (!targets.length) return response(pendingRecovery.length ? 'continue_waiting_for_original_conditions' : 'no_bound_desktop_targets', {
      pending_recovery:pendingRecovery,
      continuation:{...config,cursors,seen_attention:[...seen],seen_recovery:{...seenRecovery},observed_turns:[...observed]},
      action:'retain_original_coordinator_and_conditions_no_restart',
      instruction:'没有可等待的原桌面目标时保留原条件，等待真实新事实；不结束为已全部处理，不紧循环重试或另建监听。'});
    // More than eight is a batching concern, never a module concurrency cap.
    const groups = [];
    for (let index=0; index<targets.length; index+=8) groups.push(targets.slice(index,index+8));
    for (const group of groups) {
      const timeoutMs = first ? 0 : Math.max(0, Math.min(50000,
        config.observation_seconds * 1000 / groups.length, windowMs - (Date.now() - started)));
      let result;
      const waitStarted = Date.now();
      try { waits++; result = unpack(await waitThreads({targets:group,timeoutMs})); }
      catch (_) { return response('desktop_host_unreachable', {targets:group,action:'preserve_original_binding'}); }
      if (!result || typeof result !== 'object') return response('desktop_wait_receipt_unrecognized');
      if (result.interrupted || result.reason === 'user_input' || result.status === 'interrupted' || result.userInput ||
          (result.message === 'Wait interrupted by new input.' && result.timedOut === false && !result.errors) ||
          /user.?input|interrupt/i.test(result.wake?.reason || ''))
        return response('user_input', {action:'apply_latest_user_instruction_before_any_continuation'});
      if (result.errors && Object.keys(result.errors).length) return response('desktop_target_errors', {errors:result.errors,
        action:'inspect_original_host_or_target_no_restart'});
      const updates = result.polls;
      if (!Array.isArray(updates)) return response('desktop_wait_receipt_unrecognized',
        {receipt:result,action:'inspect_public_wait_receipt_no_state_inference'});
      for (const item of updates) {
        const id = item.thread?.id;
        if (!group.some(target => target.threadId === id)) continue;
        if (item.cursor) cursors[id] = item.cursor;
        snapshots.set(id,item);
      }
      try { await read(); }
      catch (_) { return response('platform_observation_unavailable'); }
      const issues = [];
      for (const item of snapshots.values()) {
        const id = item.thread?.id, status = item.latestTurn?.status;
        const module = views.flatMap(view => view.modules || []).find(value =>
          (value.binding?.executor_ref || '').replace(/^thread:/,'') === id &&
          !['completed','blocked','stopped'].includes(value.state));
        if (!module || ['completed','blocked','stopped'].includes(module.state)) continue;
        const unclaimed = observation().filter(event => event.target_thread_id === id && event.current_binding &&
          ['sent_awaiting_claim','sending_unconfirmed','unknown','pending_delivery'].includes(event.phase));
        const endedValue = item.latestTurn?.completedAt;
        // Public desktop timestamps are epoch seconds; durationMs is separate.
        const ended = typeof endedValue === 'number' ? endedValue * 1000 :
          typeof endedValue === 'string' ? Date.parse(endedValue) : NaN;
        const afterSend = unclaimed.some(event => Number.isFinite(ended) &&
          ended >= (event.delivery_started_at || event.created_at) * 1000);
        const bindingAt = Math.max(module.binding?.created_at || 0, module.binding?.received_at || 0,
          module.binding?.last_seen_at || 0) * 1000;
        const currentTurn = bindingAt > 0 && Number.isFinite(ended) && ended >= bindingAt;
        const endedTurn = currentTurn && ['completed','failed','error','interrupted'].includes(status);
        const dispatchId = module.binding?.dispatch_id || module.binding?.id;
        const receiptKey = JSON.stringify([module.task_id,module.id,dispatchId,item.latestTurn?.id,status,ended]);
        if (endedTurn && dispatchId && item.latestTurn?.id && !observed.has(receiptKey)) {
          try {
            const receipt = await callNative({action:'dispatch',task_id:module.task_id,
              holder_id:config.holder_id,coordinator_ref:config.coordinator_ref,
              request_id:'desktop-observed:' + module.id + ':' + dispatchId + ':' + item.latestTurn.id + ':' + status,
              arguments:{desktop_observations:[{node_id:module.id,dispatch_id:dispatchId,
                executor_ref:module.binding.executor_ref,turn_id:item.latestTurn.id,status,completed_at:ended/1000}]}});
            if (!receipt?.accepted) return response('desktop_receipt_unconfirmed', {action:'reconcile_original_binding'});
            observed.add(receiptKey);
          } catch (_) { return response('desktop_receipt_unconfirmed', {action:'reconcile_original_binding'}); }
        }
        const actualError = item.latestTurn?.error && currentTurn && (!unclaimed.length || afterSend);
        const needsAttention = item.thread?.status?.type === 'needsAttention';
        const desktopBinding = [module.task_id,module.id,module.binding?.holder_id,
          module.binding?.dispatch_id || module.binding?.id];
        // Carry this state in seen_attention across calls. Once attention has
        // cleared, the same turn may legitimately need attention again.
        if (!needsAttention) for (const key of seen) {
          try {
            const previous = JSON.parse(key);
            if (previous[0] === 'desktop' && previous[8] === true &&
                JSON.stringify(previous.slice(1,5)) === JSON.stringify(desktopBinding)) seen.delete(key);
          } catch (_) { /* Other saved signatures are not desktop attention. */ }
        }
        const desktopKey = JSON.stringify(['desktop',...desktopBinding,item.latestTurn?.id,status,item.latestTurn?.error,
          needsAttention,unclaimed.map(event => event.notice_id),
          needsAttention ? item.latestToolMarkerId || item.latestToolMarker?.id || null : null]);
        if (seen.has(desktopKey)) continue;
        if (actualError || needsAttention || (endedTurn && (module.has_lease || status !== 'completed')) ||
            (!module.has_lease && ['completed','failed','error','interrupted'].includes(status) && afterSend)) {
          seen.add(desktopKey);
          issues.push({task_id:module.task_id,node_id:module.id,thread_id:id,desktop_status:status,
            original_handoffs:unclaimed, binding:module.binding,
            desktop_evidence:{cursor:item.cursor,revision:item.revision,thread:item.thread,latestTurn:item.latestTurn,
              latestToolMarkerId:item.latestToolMarkerId,latestToolMarker:item.latestToolMarker},
            reason:actualError ? 'desktop_turn_error' : needsAttention ? 'desktop_needs_attention' :
              module.has_lease ? 'desktop_turn_ended_with_lease' : status !== 'completed' ?
                'desktop_turn_failed_or_interrupted' : 'desktop_ended_before_actual_claim'});
        }
      }
      if (issues.length) return response('desktop_attention', {attention:issues,
        action:'reconcile_original_exit_or_error_from_actual_receipt_no_model_switch'});
      if (result.wake?.reason && !['inactiveStatus','completed','needsAttention','timeout'].includes(result.wake.reason))
        return response('desktop_wake', {wake:result.wake,action:'inspect_original_wake_before_continuation'});
      if (!first && observation().some(event => event.attention_reason && !seen.has(signature(event)))) break;
      if (Date.now() - started >= windowMs) break;
      // Some inactive desktop statuses return immediately even with a cursor.
      // Do not turn that into a rapid dispatch/read loop. This delay is inside
      // this finite tool invocation, never a model wake or persistent timer.
      if (timeoutMs && Date.now() - waitStarted < timeoutMs)
        await new Promise(resolve => setTimeout(resolve, Math.min(timeoutMs - (Date.now() - waitStarted),
          windowMs - (Date.now() - started))));
    }
    first = false;
  }
}
