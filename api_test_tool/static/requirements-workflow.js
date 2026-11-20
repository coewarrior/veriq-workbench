'use strict';
// Keep execution detail available without making it part of the normal input flow.
globalThis.RequirementsWorkflow=(()=>{
  const statusLabels={not_run:'未执行',passed:'通过',failed:'不通过',partial:'部分验证',blocked:'条件缺失',pending_rule:'待明确规则',pending_action:'待人工操作'};
  const modeLabels={real:'真实环境',sandbox:'沙箱通道',mock:'模拟环境',design:'仅设计'};
  const caches=new Map(),informationCaches=new Map();
  function pointHTML(point,caseId='',frozen=false){
    const gaps=(point.gaps||[]).map(g=>`<li>${esc(g.title)}：${esc(g.reason)}</li>`).join('');
    const correlation=Object.entries(point.correlation||{}).map(([k,v])=>`${k}: ${v}`).join(' · ');
    return `<li><div class="requirement-point-title"><strong>${esc(point.title)}</strong><span class="quiet-tag">${esc(statusLabels[point.status]||point.status)} · ${esc(modeLabels[point.verification_mode]||point.verification_mode)}</span></div><p>预期：${esc(point.expected)}</p>${point.actual?`<p>观察：${esc(point.actual)}</p>`:''}${gaps?`<ul class="hint">${gaps}</ul>`:''}${point.action_required&&point.status==='pending_action'?`<p class="hint">下一步：${esc(point.action_required)}</p>`:''}${correlation?`<p class="hint">原业务关联：${esc(correlation)}</p>`:''}${point.inherited_from?.execution_id?'<p class="hint">前序步骤沿用原轮次观察，本轮未重复执行。</p>':''}${point.status==='pending_action'&&point.kind==='manual'&&!frozen?`<form data-manual-checkpoint="${esc(point.id)}" data-case-id="${esc(caseId)}"><label>已完成的操作与观察结果<input name="actual" required maxlength="4000" placeholder="填写实际操作及观察，后续仍需核对业务结果"></label><button type="submit">记录操作结果</button></form>`:''}</li>`;
  }
  function continuationCases(records,mode='continue',selected=[]){
    return (records?.cases||[]).filter(c=>selected.length?selected.includes(c.case_id):mode==='continue'&&c.status!=='passed').map(c=>c.case_id);
  }
  function content(design,records,capabilities,{readonly=false,overviewTitle='实时测试概况'}={}){
    const cases=records.cases||[],trace=design.traceability||[],questions=(design.questions||[]).map(q=>({...q,affected_case_ids:q.affected_case_ids||cases.filter(c=>c.question_ids?.includes(q.id)||c.checkpoints?.some(p=>p.question_ids?.includes(q.id))).map(c=>c.case_id)}));
    if(!cases.length&&!trace.length&&!questions.length&&!capabilities.items?.length)return '';
    const passed=cases.filter(c=>c.status==='passed').length,failed=cases.filter(c=>c.status==='failed').length;
    const pending=cases.length-passed-failed;
    const unresolved=questions.filter(q=>q.status!=='resolved');
    const reqs=trace.map(r=>`<tr><td>${esc(r.title)}</td><td>${esc(r.case_ids.join('、')||'待设计具体用例')}</td></tr>`).join('');
    const questionHTML=q=>`<details><summary>${esc(q.title)} · ${q.status==='resolved'?'已明确':'待明确'} · ${q.affected_case_ids.length} 条用例</summary><p>${esc(q.detail)}</p>${q.status==='resolved'?`<p>${esc(q.resolution)}</p><p class="hint">依据：${esc(q.basis)}</p>`:''}</details>`;
    const manual=cases.flatMap(c=>(c.checkpoints||[]).filter(p=>p.status==='pending_action'&&p.kind==='manual').map(p=>({c,p})));
    const gaps=new Map();
    for(const c of cases)for(const p of c.checkpoints||[])for(const g of p.gaps||[]){if(g.kind!=='dependency'||g.status!=='blocked')continue;const key=g.id||g.title;const item=gaps.get(key)||{title:g.title,reason:g.reason,cases:new Set()};item.cases.add(c.case_id);gaps.set(key,item);}
    const todo=unresolved.length+manual.length+gaps.size;
    const details=cases.map(c=>`<details><summary><span>${esc(c.case_id)} ${esc(c.scenario)}</span><span class="quiet-tag">${esc(statusLabels[c.status]||c.status)}</span></summary>${c.checkpoints?.length?`<ol class="requirement-points">${c.checkpoints.map(p=>pointHTML(p,c.case_id,true)).join('')}</ol>`:`<p class="hint">${esc(c.not_run_reason||c.actual||'具体用例设计已保存')}</p>`}</details>`).join('');
    return `<div class="panel requirement-panel"><div class="panel-heading"><h2>${cases.length?esc(overviewTitle):'资料已就绪'}</h2><button type="button" class="text-button" data-requirements-refresh>刷新</button></div>${cases.length?`<div class="stats ui-result-counts"><div class="stat"><strong>${cases.length}</strong><span>全部用例</span></div><div class="stat pass"><strong>${passed}</strong><span>通过</span></div><div class="stat fail"><strong>${failed}</strong><span>不通过</span></div><div class="stat"><strong>${pending}</strong><span>待完成</span></div></div>`:'<p class="hint">Codex 将根据资料设计完整用例，执行具备条件的部分。</p>'}${todo?`<section class="ui-pending"><h3>需要补充 · ${todo} 项</h3><p class="hint">这些条件只影响对应场景，其他测试继续。</p>${unresolved.map(questionHTML).join('')}${manual.map(({c,p})=>`<details><summary>${esc(p.title)} · ${esc(c.case_id)}</summary><ol class="requirement-points">${pointHTML(p,c.case_id,true)}</ol></details>`).join('')}${gaps.size?`<ul>${[...gaps.values()].map(g=>`<li><strong>${esc(g.title)}</strong>：${esc(g.reason)} <span class="hint">影响 ${g.cases.size} 条用例</span></li>`).join('')}</ul>`:''}</section>`:''}<details class="ui-detail-group"><summary>查看用例与执行细节${cases.length?' · '+cases.length+' 条':''}</summary><div class="requirement-cases">${details||'<p class="hint">具体用例尚未保存。</p>'}</div></details>${reqs?`<details class="ui-detail-group"><summary>需求覆盖 · ${trace.length} 项${design.requirements_without_cases?.length?' · '+design.requirements_without_cases.length+' 项待关联':''}</summary><div class="requirement-table"><table><thead><tr><th>需求 / 验收条件</th><th>具体用例</th></tr></thead><tbody>${reqs}</tbody></table></div></details>`:''}${questions.some(q=>q.status==='resolved')?`<details class="ui-detail-group"><summary>已确认的业务规则</summary>${questions.filter(q=>q.status==='resolved').map(questionHTML).join('')}</details>`:''}${capabilities.items?.length?`<details class="ui-detail-group"><summary>业务查询与测试能力 · ${capabilities.items.length} 项</summary><ul>${capabilities.items.map(c=>`<li>${esc(c.title)} · ${esc(c.environment)} · ${esc(modeLabels[c.verification_mode])}</li>`).join('')}</ul></details>`:''}</div>`;
  }
  async function read(pid,includeCapabilities=true){
    const [design,capabilities]=await Promise.all([api(`/api/ui-tests/${pid}/requirements`),includeCapabilities?api(`/api/ui-tests/${pid}/capabilities`):Promise.resolve({items:[]})]);
    let records={cases:[]};
    if(design.execution_id){let offset=0;do{
      const page=await api(`/api/ui-tests/${pid}/executions/${design.execution_id}/inventory?offset=${offset}&limit=200`);
      records={...page,cases:[...records.cases,...page.cases]};offset=page.next_offset;
    }while(offset!==null);}
    return {design,records,capabilities};
  }
  async function load(pid){
    const cache=await read(pid,false);
    caches.set(pid,cache);
    return cache;
  }
  async function render(panel,snapshot=null){
    const pid=state.project?.id;if(!pid)return;
    let slot=panel.querySelector('[data-requirements-slot]');
    if(!slot){
      const markup='<div data-requirements-slot aria-live="polite">正在读取测试状态…</div>';
      // Preparation shows the overview before task settings; reports follow the result summary.
      const summary=panel.id==='report-panel'?panel.querySelector(':scope > .panel'):null;
      if(summary)summary.insertAdjacentHTML('afterend',markup);
      else panel.insertAdjacentHTML(panel.id==='generation-panel'?'afterbegin':'beforeend',markup);
      slot=panel.querySelector('[data-requirements-slot]');
    }
    // Navigation/polling may request this panel again before the first fetch completes.
    const request=Symbol();slot.requirementsRequest=request;
    try{
      const cache=snapshot||await read(pid);
      if(state.project?.id!==pid||!slot.isConnected||slot.requirementsRequest!==request)return;
      caches.set(pid,cache);slot.innerHTML=content(cache.design,cache.records,cache.capabilities,{readonly:cache.readonly,overviewTitle:panel.id==='report-panel'?'整体测试概况':'实时测试概况'});
      globalThis.UIWorkflow?.updateAction(cache.records);
      return true;
    }catch(error){if(slot.isConnected&&slot.requirementsRequest===request)slot.textContent=error.message;}
  }
  function informationContent(design,records){
    const questions=(design.questions||[]).filter(q=>q.status!=='resolved');
    const manual=(records.report_id?[]:records.cases||[]).flatMap(c=>(c.checkpoints||[]).filter(p=>p.status==='pending_action'&&p.kind==='manual').map(p=>({c,p})));
    if(!questions.length&&!manual.length)return '';
    return `<section class="ui-pending"><h3>待补充条件</h3>${questions.map(q=>`<details><summary>${esc(q.title)}</summary><p>${esc(q.detail)}</p><form data-rule-form="${esc(q.id)}"><label>规则结论<textarea name="resolution" required maxlength="10000" rows="2">${esc(q.resolution||'')}</textarea></label><label>确认依据<input name="basis" required maxlength="4000" value="${esc(q.basis||'')}"></label><button type="submit">保存规则结论</button></form></details>`).join('')}${manual.map(({c,p})=>`<details><summary>${esc(c.case_id)} ${esc(p.title)}</summary><ol class="requirement-points">${pointHTML(p,c.case_id,false)}</ol></details>`).join('')}</section>`;
  }
  async function renderInformation(slot){
    const pid=state.project?.id;if(!pid||!slot)return;
    const request=Symbol();slot.informationRequest=request;
    try{
      const cache=await read(pid,false);
      if(state.project?.id!==pid||!slot.isConnected||slot.informationRequest!==request)return;
      informationCaches.set(pid,cache);slot.innerHTML=informationContent(cache.design,cache.records);
    }catch(error){if(slot.isConnected&&slot.informationRequest===request)slot.textContent=error.message;}
  }
  async function prepareContinuation({automatic=false,mode='continue',selected=[],reason=''}={}){
    const pid=state.project?.id;if(!pid)return false;
    const wasBusy=state.managementBusy;state.managementBusy=true;
    try{
      const cache=await read(pid,false),records=cache.records;
      if(automatic&&!records.report_id&&!records.cases.some(c=>['failed','partial','blocked','pending_rule','pending_action'].includes(c.status)))return false;
      const case_ids=continuationCases(records,mode,selected);
      if(!case_ids.length){if(automatic)return false;throw Error(mode==='retest'?'请勾选需要重新验证的用例。':'当前没有未完成用例。');}
      await api(`/api/ui-tests/${pid}/resume`,'POST',{mode,reason:reason.trim()||(mode==='retest'?'用户重新验证所选用例':'补充条件后继续未完成项，保留原业务关联'),case_ids,execution_id:records.id,revision:records.revision});
      const data=await api(`/api/projects/${pid}`);
      Object.assign(state,data);state.bootstrap.projects=state.bootstrap.projects.map(p=>p.id===pid?data.project:p);
      return true;
    }finally{state.managementBusy=wasBusy;}
  }
  document.addEventListener('click',async event=>{
    const refresh=event.target.closest('[data-requirements-refresh]');
    if(refresh){if(state.stage===4)await globalThis.UIWorkflow?.renderResultDetails();else await render(refresh.closest('[data-requirements-slot]').parentElement);return;}
  });
  document.addEventListener('submit',async event=>{
    const form=event.target,rule=form.dataset?.ruleForm,manual=form.dataset?.manualCheckpoint;
    if(!rule&&!manual)return;
    event.preventDefault();const pid=state.project?.id;if(!pid)return;
    const button=event.submitter;if(button?.disabled)return;if(button)button.disabled=true;
    try{
      const fields=Object.fromEntries(new FormData(form)),cache=informationCaches.get(pid)||caches.get(pid);
      if(manual){
        const cid=form.dataset.caseId,point=cache?.records.cases.find(c=>c.case_id===cid)?.checkpoints.find(p=>p.id===manual);
        if(!point)throw Error('步骤已变化，请刷新后重试。');
        await api(`/api/ui-tests/${pid}/executions/${cache.records.id}/checkpoints/${encodeURIComponent(cid)}/${encodeURIComponent(manual)}`,'POST',{revision:cache.records.revision,result:{status:'passed',actual:fields.actual,method:'用户填写实际人工操作结果',verification_mode:point.verification_mode==='design'?'real':point.verification_mode,correlation:point.correlation}});
        toast('操作已记录，仍需继续核对业务结果。');await renderInformation(form.closest('#ui-information-conditions'));
      }else if(rule){
        await api(`/api/ui-tests/${pid}/questions/${encodeURIComponent(rule)}`,'POST',{...fields,revision:cache.design.revision});
        toast('规则已保存，可继续未完成测试。');await renderInformation(form.closest('#ui-information-conditions'));
      }
    }catch(error){toast(error.message,true);}finally{if(button)button.disabled=false;}
  });
  return {render,load,renderInformation,informationContent,pointHTML,content,continuationCases,prepareContinuation,current:pid=>caches.get(pid)};
})();
