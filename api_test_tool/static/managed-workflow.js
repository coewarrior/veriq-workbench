'use strict';
// Scheduling is part of the existing session, never a second task-creation flow.
globalThis.ManagedWorkflow = (()=>{
  const labels={queued:'等待资源',starting:'正在启动',running:'正在执行',stopping:'正在安全停止',isolated:'等待执行器回收',stopped:'已停止',paused:'已暂停',completed:'已完成',container:'已拆分',waiting_human:'等待人工',retained:'保留现场',blocked:'待处理',exploration:'探索与设计',execution:'执行',report:'报告'};
  const ids=new Map(), activityCache=new Map();
  let activityProject;
  const executorLabel=n=>n.child_ids?.length?'协调汇总':n.executor?.executor_ref?'模块 Codex 会话':n.executor?'已接单，会话标识未登记':['completed','stopped','blocked'].includes(n.state)?'执行已结束':'等待模块会话接单';
  function threadLink(ref,label='打开 Codex 会话'){
    const id=String(ref||'').trim().replace(/^thread:/,'');
    return /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(id)
      ?`<a href="codex://threads/${encodeURIComponent(id)}">${esc(label)}</a>`:'';
  }
  function sessionLinks(rows){
    const refs=new Map();
    for(const row of rows)for(const [key,label] of [['executor_ref','执行会话'],['coordinator_ref','协调会话']]){
      const ref=String(row[key]||'').trim().replace(/^thread:/,'').toLowerCase();
      if(!threadLink(ref))continue;
      if(!refs.has(ref))refs.set(ref,new Set());
      refs.get(ref).add(label);
    }
    const links=[...refs].map(([ref,roles])=>threadLink(ref,[...roles].join(' / ')));
    return links.length?`<p class="hint managed-session-links">${links.join(' · ')}</p>`:'';
  }
  function nativeHandoffDetail(n){
    const handoff=n.native_handoff;
    if(handoff?.kind==='resource_change')return `<p class="hint">资源变化：${handoff.delivery_state==='received'?'已接收，实际领取待确认':'待原桌面工具处理，平台无后台送达连接'}</p>`;
    const directMessage={successors_selected:'账号已交还，原会话接续领取待确认',waiting_resources:'账号已交还，等待资源或依赖',attention_required:'接续待协调，未知通知不重发',group_finished:'授权组已结束，待协调汇总'}[handoff?.direct_dispatch?.state];
    const message=handoff?.delivery_state!=='obsolete'&&directMessage||{pending:'账号已交还，待通知协调会话',sending:'通知发送中，送达待核实',unknown:'通知结果未知，不自动重发',blocked:'通知受阻，交接未完成',sent:'通知已发送，待接收',received:'交接已接收，账号领取待确认',unbound:'账号已交还，协调会话未绑定',obsolete:'交接已失效，不恢复旧任务'}[handoff?.delivery_state];
    if(!message)return '';
    const pending=(handoff.continuations||[]).filter(item=>['pending','sending','unknown','blocked','unbound'].includes(item.delivery_state)).length;
    return `<p class="hint">${esc(message)}${pending?` · ${pending} 个后继通知待完成`:''}</p>`;
  }
  function moduleMetrics(node,task,progress){
    const record=progress?.modules?.find(item=>item.node_id===node.id&&item.task_id===task.id);
    return CodexProgress.renderCounts(record,{compact:true});
  }
  function moduleDetails(node,task,content){
    const refs={executor_ref:node.executor?.executor_ref,coordinator_ref:node.native_handoff?.coordinator_ref};
    return `<details class="managed-module-details" data-managed-detail="${esc(task.id+':'+node.id)}" data-activity-task="${esc(task.id)}" data-activity-node="${esc(node.id)}" data-executor-ref="${esc(refs.executor_ref||'')}" data-coordinator-ref="${esc(refs.coordinator_ref||'')}"><summary>会话与交接详情</summary>${content}<div data-activity-content>${activityMarkup(task.id,node.id,refs)}</div></details>`;
  }
  function activityMarkup(taskId,nodeId='',refs={}){
    const entry=activityCache.get(taskId);
    const refresh=`<button type="button" data-activity-refresh="${esc(taskId)}">刷新待处理事项</button>`;
    const fallbackLinks=sessionLinks([refs]);
    if(!entry)return fallbackLinks;
    if(entry.error)return `${fallbackLinks}<p class="hint">${esc(entry.error)}</p>${refresh}`;
    if(!entry.data)return `${fallbackLinks}<p class="hint">正在核对状态…</p>`;
    const labels={blockers:'活动或待核实',waiting:'等待条件',reports:'报告待整理',residuals:'旧标记待清理'};
    const groups=new Map();
    for(const [key,label] of Object.entries(labels))for(const row of entry.data[key]||[]){
      if(nodeId&&row.node_id!==nodeId)continue;
      const id=row.node_id||'';
      if(!groups.has(id))groups.set(id,[]);
      groups.get(id).push({...row,key,label});
    }
    const sections=[...groups].map(([id,rows])=>{
      const summary=Object.entries(labels).filter(([key])=>rows.some(row=>row.key===key)).map(([key,label])=>{
        const count=rows.filter(row=>row.key===key).length;
        return esc(label)+(count>1?` ${count} 项`:'');
      }).join(' · ');
      const warnings=[...new Set(rows.filter(row=>row.key==='blockers').map(row=>row.reason))];
      const diagnostics=rows.map(row=>`<p class="hint"><strong>${esc(row.label)}</strong> · ${esc(row.reason)}<br>${esc(row.next_action)}</p>`).join('');
      return `${!nodeId?`<p class="hint"><strong>${esc(rows[0].title||'本轮任务')}</strong></p>`:''}${sessionLinks([...(nodeId?[refs]:[]),...rows])}<p class="hint">${summary}</p>${warnings.map(reason=>`<p class="hint">${esc(reason)}</p>`).join('')}<details class="managed-activity-diagnostics" data-managed-detail="${esc(taskId+':'+nodeId+':diagnostics:'+id)}"><summary>诊断详情</summary>${diagnostics}</details>`;
    });
    return (sections.join('')||`${fallbackLinks}<p class="hint">暂无待处理事项。</p>`)+refresh;
  }
  async function loadActivity(taskId,force=false){
    const pid=state.project?.id;
    let entry=activityCache.get(taskId);
    if(!force&&entry){if(entry.promise)await entry.promise;return;}
    entry={};activityCache.set(taskId,entry);
    const paint=()=>{if(state.project?.id===pid)for(const el of document.querySelectorAll('[data-activity-task]')){
      if(el.dataset.activityTask===taskId)el.querySelector('[data-activity-content]').innerHTML=activityMarkup(taskId,el.dataset.activityNode,{executor_ref:el.dataset.executorRef,coordinator_ref:el.dataset.coordinatorRef});
    }};
    paint();
    entry.promise=(async()=>{try{const value=await api(`/api/orchestration?task_id=${encodeURIComponent(taskId)}&activity=true`);entry.data=value.activity;}
      catch(error){entry.error='状态核对未完成：'+error.message;}finally{delete entry.promise;paint();}})();
    await entry.promise;
  }
  function renderDesktopStop(stop,task={},nodes=[],progress){
    if(!stop?.platform_scheduling_stopped)return '';
    const sessions=stop.required_sessions||[];
    const nodeById=new Map(nodes.map(n=>[n.id,n]));
    return `<section class="managed-desktop-stop" aria-label="桌面会话停止状态"><strong>平台已停止后续调度</strong><p class="hint">${stop.manual_stop_required?'请打开以下 Codex 会话，点击桌面的停止按钮，并核实本任务浏览器已停止。网页不能代替桌面取消模型回合。':'已登记会话的退出与账号交还状态如下。'}</p>${sessions.map(s=>{
      const node=nodeById.get(s.node_id);
      const handoff=node?nativeHandoffDetail(node):'';
      return `<div class="managed-desktop-stop-item${node?' managed-module':''}"><strong>${esc(s.title||'模块会话')}</strong>${node?moduleMetrics(node,task,progress):''}${node?.reason?`<p class="hint">${esc(node.reason)}</p>`:''}<p>${threadLink(s.executor_ref)||'<span>未登记可打开的会话 ID，请在原协调聊天核对。</span>'}</p><p class="hint">执行者退出：${s.executor_exit_confirmed===true?'已确认':'待核实'} · 浏览器退出：${s.browser_stopped===true?'已确认':'待核实'} · 账号交还：${s.accounts_released===true?'已交还':'待核实'}</p>${handoff?moduleDetails(node,task,handoff):''}${task.id&&s.node_id&&(s.executor_exit_confirmed!==true||s.browser_stopped!==true||s.accounts_released!==true)?`<button type="button" data-native-exit="${esc(s.node_id)}" data-task="${esc(task.id)}" data-revision="${Number(task.revision)}">已在桌面停止并关闭测试浏览器</button>`:''}</div>`;
    }).join('')}${sessions.length?'':'<p class="hint">没有需要处理的已登记桌面会话。</p>'}</section>`;
  }
  function nativeModuleState(n,t){
    if(t.execution_route!=='native_browser')return labels[n.state]||n.state;
    if(n.native_report_pending&&['completed','blocked','stopped','paused'].includes(n.state))return '执行已结束 · 账号已交还';
    if(t.desktop_stop?.platform_scheduling_stopped)return '平台已停止调度';
    if(n.state==='completed')return n.coverage_complete===true?'本轮执行结束 · 覆盖已确认':'本轮执行结束';
    if(n.state==='isolated'&&n.execution_ended)return '执行已结束 · 等待原操作核实';
    if(['isolated','retained','stopping','stopped','paused'].includes(n.state))return labels[n.state]||n.state;
    if(n.native_executor_status?.state==='unavailable')return '模型不可用';
    if(n.state==='queued'&&n.resource_wait?.resources_available===true)return '资源可用，等待原会话实际领取';
    if(n.state==='queued'&&n.resource_wait?.kind==='native_environment_unavailable')return '等待浏览器环境';
    if(n.state==='queued'&&n.resource_wait?.kind==='dependency_unavailable')return '等待前置任务';
    if(n.state==='queued'&&n.resource_wait?.kind==='business_resource_busy')return '等待业务资源';
    if(n.state==='queued'&&n.resource_wait?.kind==='account_configuration_missing')return '账号配置不满足当前需求';
    if(n.state==='queued'&&n.resource_wait?.kind==='account_busy'&&n.requested_account_ids?.length)return '等待指定账号';
    return labels[n.state]||n.state;
  }
  function currentModuleNodes(nodes){
    const byId=new Map(nodes.map(node=>[node.id,node])), rendered=new Set();
    // Keep the original module position, but use its current same-task record
    // owner so that the card and progress counts refer to the same node.
    return nodes.map(source=>{
      let node=source;
      const visited=new Set();
      while(byId.has(node.record_successor_node_id)&&!visited.has(node.id)){
        visited.add(node.id);
        node=byId.get(node.record_successor_node_id);
      }
      return node;
    }).filter(node=>{
      if(rendered.has(node.id))return false;
      rendered.add(node.id);return true;
    });
  }
  function renderTask(t,data){
    const native=t.execution_route==='native_browser';
    const direct=native||t.execution_route==='local_browser';
    const taskNodes=data.nodes.filter(n=>n.task_id===t.id&&!n.child_ids?.length);
    const nodes=currentModuleNodes(taskNodes);
    const stopNodes=new Set(t.desktop_stop?.platform_scheduling_stopped?(t.desktop_stop.required_sessions||[]).map(s=>s.node_id):[]);
    const modules=nodes.filter(n=>!stopNodes.has(n.id)).map(n=>{
      const executor=native?(n.executor_exit_confirmed?'执行者已回报退出':n.executor?.executor_ref?'桌面 Codex 会话':'桌面会话尚未登记'):direct?executorLabel(n):'后台执行';
      const model=n.native_executor_status;
      const modelDetail=model?`<p class="hint">模型状态：${esc(model.state==='unavailable'?'不可用':'原会话已恢复')} · ${esc(model.model||'原模型')} · 来源 ${esc(model.source)}（已登记来源）</p><p class="hint">${esc(model.reason||'')}</p>`:'';
      const details=`${modelDetail}${!n.executor?.executor_ref||n.executor_exit_confirmed?`<p class="hint">${esc(executor)}</p>`:''}${native?nativeHandoffDetail(n):data.leases.filter(l=>l.node_id===n.id).map(l=>`<div class="managed-buttons">${l.account_ids.map(a=>`<button type="button" data-managed-scene="${esc(a)}" data-lease="${esc(l.id)}">查看浏览器现场</button>`).join('')}</div>`).join('')}`;
      return `<div class="managed-module"><div class="managed-module-heading"><strong>${esc(n.title)}</strong><span class="managed-module-state" data-state="${esc(n.state)}">${esc(nativeModuleState(n,t))}</span></div>${moduleMetrics(n,t,data.progress)}${n.reason?`<p class="hint">${esc(n.reason)}</p>`:''}${moduleDetails(n,t,details)}</div>`;
    }).join('');
    return `<article class="managed-task"><h3>${esc(t.goal.split('\n')[0])}</h3><p class="hint managed-round-caption">最新一轮 · ${nodes.length} 个模块 · 模块状态与用例结果分别显示</p><details data-managed-detail="${esc(t.id)}:" data-activity-task="${esc(t.id)}" data-activity-node=""><summary>运行与收尾待处理事项</summary><div data-activity-content>${activityMarkup(t.id)}</div></details><div class="managed-module-list">${modules}</div>${renderDesktopStop(t.desktop_stop,t,taskNodes,data.progress)}<div class="managed-buttons">${t.account_project_deleted?'<p class="hint">所属项目已删除，本轮仅保留历史记录；可重新选择项目开始新一轮测试。</p>':''}${(t.account_project_deleted?[]:[['pause','暂停'],['stop',native?'停止调度并查看桌面停止清单':'停止']]).map(([a,l])=>`<button type="button" data-managed-control="${a}" data-task="${esc(t.id)}" data-revision="${t.revision}">${l}</button>`).join('')}<button type="button" data-managed-report="${esc(t.id)}">查看本轮汇总</button></div></article>`;
  }
  function mount(panel){
    if(!state.project||panel.querySelector('[data-managed-session]'))return;
    const section=document.createElement('section');section.className='panel managed-session';section.dataset.managedSession=state.project.id;
    section.innerHTML='<div class="managed-heading"><h2>测试进展</h2><button type="button" data-managed-settings>会话所属项目</button></div><p class="hint" data-managed-message>正在读取任务状态…</p><button type="button" data-managed-handoff hidden>复制 MCP 任务消息</button><div data-managed-tasks></div><details class="managed-connection-settings"><summary>执行连接设置</summary><button type="button" data-managed-connection>查看执行连接</button></details>';
    panel.append(section);section.querySelector('[data-managed-settings]').onclick=()=>settings();section.querySelector('[data-managed-connection]').onclick=()=>connection();
    section.querySelector('[data-managed-handoff]').onclick=async e=>{
      const button=e.currentTarget;button.disabled=true;
      try{await openMCP('session');}catch(error){toast('任务消息未生成：'+error.message,true);}finally{button.disabled=false;}
    };
    refresh(false).catch(e=>{section.querySelector('[data-managed-message]').textContent=e.message;});
  }
  function refresh(fresh=true){return refreshCodexProgress({fresh});}
  function applyProgress(data){
    const pid=state.project?.id,roots=[...document.querySelectorAll('[data-managed-session]')].filter(x=>x.dataset.managedSession===pid&&x.isConnected);
    if(!roots.length)return;
    if(activityProject!==pid){activityCache.clear();activityProject=pid;}
      const current=data.tasks.find(t=>data.progress?.scope?.kind==='task'&&t.id===data.progress.scope.task_id)
        ||data.tasks.reduce((latest,t)=>!latest||Number(t.created||0)>Number(latest.created||0)?t:latest,null);
      const mode=current?.execution_route||data.execution_mode;
      for(const root of roots){
        root.querySelector('[data-managed-handoff]').hidden=!['local_browser','native_browser'].includes(mode);
        root.querySelector('[data-managed-message]').textContent=mode==='native_browser'?'本轮使用现有桌面 Codex 账号与原生浏览器工具，各模块使用独立会话。平台负责账号和结果；停止时先停止平台调度，再按清单在桌面停止会话。':mode==='local_browser'?'本轮由 Codex 协调聊天安排，各模块使用独立 Codex 会话；账号与浏览器由平台统一调度，人工问题回到协调聊天。':data.tasks.length?'任务沿用本会话的资料和测试范围。账号不足时自动等待，满足条件后继续。':data.execution_ready?'执行连接已就绪。点击正常“开始测试”，平台会根据账号与机器资源分配模块。':'执行连接尚未就绪，已登记的任务会保留并等待连接恢复。';
        root.querySelector('[data-managed-settings]').textContent=data.account_project?'所属项目：'+data.account_project.name:'选择所属项目';
        const box=root.querySelector('[data-managed-tasks]');
        const openDetails=new Set([...box.querySelectorAll('[data-managed-detail][open]')].map(detail=>detail.dataset.managedDetail));
        const focused=box.contains(document.activeElement)?document.activeElement:null;
        const focusedDetail=focused?.closest('[data-managed-detail]')?.dataset.managedDetail;
        const focusedAction=focused?.matches('button')?Object.entries(focused.dataset):[];
        box.innerHTML=current?renderTask(current,data):'';
        for(const detail of box.querySelectorAll('[data-managed-detail]')){
          detail.open=openDetails.has(detail.dataset.managedDetail);
          detail.ontoggle=()=>{if(detail.open&&detail.dataset.activityTask)loadActivity(detail.dataset.activityTask);};
          if(detail.dataset.managedDetail===focusedDetail){
            const target=focused.matches('summary')?detail.querySelector('summary'):
              focused.matches('a[href]')?[...detail.querySelectorAll('a[href]')].find(link=>link.getAttribute('href')===focused.getAttribute('href')):
              focusedAction.length?[...detail.querySelectorAll('button:not(:disabled)')].find(button=>focusedAction.every(([key,value])=>button.dataset[key]===value)):null;
            target?.focus({preventScroll:true});
          }
        }
        box.onclick=async e=>{const b=e.target.closest('button');if(!b)return;b.disabled=true;try{
          if(b.dataset.activityRefresh){await loadActivity(b.dataset.activityRefresh,true);return;}
          if(b.dataset.managedControl){
            await api(`/api/orchestration/tasks/${b.dataset.task}/control`,'POST',{action:b.dataset.managedControl,revision:Number(b.dataset.revision),request_id:requestId()});
            activityCache.delete(b.dataset.task);
            if(b.dataset.managedControl==='stop'&&data.tasks.some(t=>t.id===b.dataset.task&&t.execution_route==='native_browser'))toast('平台后续调度已停止。请按清单在桌面停止对应 Codex 会话。');
          }
          if(b.dataset.nativeExit){await confirmNativeExit(b.dataset.task,b.dataset.nativeExit,Number(b.dataset.revision));activityCache.delete(b.dataset.task);}
          if(b.dataset.managedScene)await BrowserConsole.open({account_id:b.dataset.managedScene,lease_id:b.dataset.lease});
          if(b.dataset.managedReport)await report(b.dataset.managedReport);
          await refresh();
        }catch(error){toast(error.message,true);}finally{b.disabled=false;}};
      }
  }
  const requestId=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
  async function start(){
    const pid=state.project.id;if(!ids.has(pid))ids.set(pid,requestId());
    const r=await api(`/api/projects/${pid}/managed/start`,'POST',{request_id:ids.get(pid)});
    if(r.scheduled){ids.delete(pid);toast(r.message||'测试已安排，当前会话将显示模块进展。');}
    else if(['local_browser','native_browser'].includes(r.mode)){
      ids.delete(pid);toast(r.message||'任务已登记，请复制任务消息交给 Codex。');
      try{await openMCP('session');}catch(error){toast('任务已登记，消息未生成：'+error.message+'。可在测试进展中重新打开“复制 MCP 任务消息”。',true);}
    }
    else{toast(r.message,true);if(r.required_inputs?.includes('account_project_id'))settings();else ProjectAccounts.open();}
    await refresh();return r;
  }
  function dialog(title){const d=document.createElement('dialog');d.className='managed-dialog';d.innerHTML=`<div class="managed-heading"><h2>${esc(title)}</h2><button type="button" data-close>关闭</button></div><div data-body></div>`;d.querySelector('[data-close]').onclick=()=>d.close();d.onclose=()=>d.remove();document.body.append(d);d.showModal();return d;}
  async function confirmNativeExit(taskId,nodeId,revision){
    const d=dialog('确认已在桌面停止'),body=d.querySelector('[data-body]');
    body.innerHTML='<p>请先在对应 Codex 会话点击停止，并确认本任务的浏览器操作已停止、测试浏览器已关闭。</p><p class="hint">下方按钮只记录你的人工确认并交还本模块账号，不会替你取消桌面会话。未完成上述操作时请关闭此窗口。</p><button type="button" data-confirm-native-exit>已确认停止，交还本模块账号</button><p class="hint" role="status" data-confirm-result></p>';
    body.querySelector('[data-confirm-native-exit]').onclick=async e=>{
      const button=e.currentTarget;button.disabled=true;
      try{
        await api(`/api/orchestration/tasks/${taskId}/control`,'POST',{action:'confirm_native_exit',node_ids:[nodeId],revision,executor_stopped:true,browser_stopped:true,reason:'用户确认已在桌面停止该会话并关闭本任务测试浏览器',request_id:requestId()});
        d.close();await refresh();toast('已记录人工退出确认，账号交还状态以平台回执为准。');
      }catch(error){body.querySelector('[data-confirm-result]').textContent=error.message;button.disabled=false;}
    };
  }
  async function connection(){
    const mode=state.project?.ui_execution_route||state.project?.execution_route||'native_browser';
    if(mode==='native_browser'){
      const d=dialog('原生浏览器执行');
      d.querySelector('[data-body]').innerHTML='<p>使用你当前桌面 Codex 账号和原生浏览器工具直接执行。平台负责项目账号、结果同步和停止调度，不需要配对执行机。</p><p class="hint">每个模块使用自己的 Codex 会话和明确浏览器标签。没有可用账号时结束当前回合；平台停止后，需要按停止清单在桌面停止对应会话。</p>';
      return;
    }
    const d=dialog('旧执行连接已停用');
    d.querySelector('[data-body]').textContent='旧 Runner 服务和配对入口已关闭。历史记录保留，新的测试使用原生 Codex 执行流程。';
  }
  function settings(){return globalThis.ProjectAccounts?.session();}
  async function report(tid){const r=await api(`/api/orchestration/tasks/${tid}/report`),d=dialog('本轮测试汇总');d.querySelector('[data-body]').innerHTML=`<p>用例 ${r.total} · 通过 ${r.counts.passed} · 重试后通过 ${r.counts.retry_passed} · 不通过 ${r.counts.failed} · 验证未完成 ${r.counts.partial} · 未执行 ${r.counts.not_run} · 阻塞 ${r.counts.blocked} · 待规则 ${r.counts.pending_rule} · 待人工 ${r.counts.pending_action}</p>${r.modules.map(m=>`<section><h3>${esc(m.title)}</h3><p>${esc(m.reason||labels[m.state]||m.state)}</p>${m.report_url?`<a href="${esc(m.report_url)}" target="_blank" rel="noopener">完整模块报告与证据 →</a>`:''}<table><thead><tr><th>用例</th><th>结果</th><th>实际观察</th></tr></thead><tbody>${m.record.cases.map(c=>`<tr><td>${esc(c.case_id)} ${esc(c.scenario)}</td><td>${esc(c.managed_status==='retry_passed'?'重试后通过':({passed:'通过',failed:'不通过',partial:'验证未完成',blocked:'阻塞',not_run:'未执行',pending_rule:'待规则',pending_action:'待人工'})[c.status]||c.status)}</td><td>${esc(c.actual||c.not_run_reason||'尚无实际观察')}</td></tr>`).join('')}</tbody></table></section>`).join('')}`;}
  async function assertIdle(){const data=await api(`/api/projects/${state.project.id}/managed`);if(data.nodes.some(n=>!n.child_ids?.length&&n.state!=='completed'))throw Error('本会话已有测试任务，请在测试进展中暂停、停止或继续；不会重复创建任务。');}
  return {mount,start,refresh,applyProgress,assertIdle,renderDesktopStop};
})();
