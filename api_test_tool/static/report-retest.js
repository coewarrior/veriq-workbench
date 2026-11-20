/* Collaborative input editing and focused retest handoff on the current report. */
(function(root){
'use strict';
const review=root.ReportReview;
if(!review?.data.retestBase)return;
const {data,cases}=review, base=data.retestBase;
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const eligible=c=>c.status!=='passed'&&!c.policy_excluded&&c.execution_disposition!=='multi_account_excluded'&&saved?.readiness?.[c.case_id]?.excluded!==true;
const statusLabels={failed:'失败',partial:'验证未完成',blocked:'阻塞',not_run:'未执行',pending_action:'待用户确认',pending_rule:'待确认规则',skipped:'跳过',other:'其他',broken:'执行异常',quarantined:'隔离',unsupported:'不支持'};
const selected=new Set();
let saved=null, csrf='', loadingError='', batchDialog=null, dataFilter='all';
const panels=new Set();
async function api(path, method='GET', body){
 if(method!=='GET'&&!csrf){const response=await fetch('/api/bootstrap');if(!response.ok)throw Error('请登录任意平台账号后再操作');csrf=(await response.json()).csrf;}
 const response=await fetch(path,{method,headers:method==='GET'?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},...(body?{body:JSON.stringify(body)}:{})});
 let result={};try{result=await response.json()}catch{}
 if(!response.ok)throw Error(result.detail||'操作失败，请重试');return result;
}
const bound=id=>saved?.inputs[saved.bindings[id]];
const groupOf=panel=>saved?.groups.find(g=>g.id===panel.dataset.groupId);
const groupsFor=ids=>(saved?.groups||[]).filter(g=>ids.every(id=>g.affected_case_ids.includes(id)));
const inputOf=panel=>groupOf(panel)?saved.inputs[groupOf(panel).input_id]:bound(JSON.parse(panel.dataset.caseIds)[0]);
const secretLabel=input=>({mail_authorization_code:'邮箱授权码',personal_access_token:'个人授权令牌',access_token:'授权令牌'})[input.account.credential_type]||'密码';
const currentInputs=id=>saved?.case_input_ids?.[id]||[];
const dataState=id=>saved?.case_data_status?.[id]?.status||'loading';
const isReady=id=>saved?.readiness?.[id]?.ready===true;
const actionConfirmed=c=>!!saved?.readiness?.[c.case_id]?.confirmation;
const actionLabel=c=>actionConfirmed(c)?'已确认，待统一补测':c.required_action?.type==='authorization'?'确认授权':'确认已完成操作';
const waitingReason=id=>{
 const reasons=[...(saved?.readiness?.[id]?.reasons||[])];
 const missing=(saved?.case_data_status?.[id]?.missing_group_ids||[]).map(key=>saved.groups.find(g=>g.id===key)).filter(Boolean).map(groupTitle);
 if(missing.length)reasons.push('缺少：'+missing.join('、'));
 return reasons.join('；');
};
const statusSummary=list=>Object.entries(statusLabels).map(([key,label])=>{const n=list.filter(c=>c.status===key).length;return n?`${label} ${n} 条`:'';}).filter(Boolean).join('、');
const caseList=ids=>`<ul class="rr-retest-related-cases">${ids.map(id=>{const c=cases.find(c=>c.case_id===id);return `<li><b>${esc(id)}</b> · ${esc(statusLabels[c?.status]||c?.status)} · ${esc(c?.scenario||'')}<p>${esc(isReady(id)?'可发起补测':waitingReason(id)||'正在读取准备状态')}</p></li>`;}).join('')}</ul>`;
const filteredEligible=()=>review.filteredCases().filter(eligible);
function matchesFilter(c){return dataFilter==='all'||eligible(c)&&(dataFilter==='saved'?isReady(c.case_id):!isReady(c.case_id));}
function caseDataMarkup(c){
 if(!eligible(c))return '<span class="rr-input-state none">无需补充</span>';
 const ready=isReady(c.case_id),status=ready?'saved':'missing';
 const label=!saved?'读取中…':ready?(actionConfirmed(c)?'操作已确认 · 可补测':dataState(c.case_id)==='saved'?'数据已填 · 可补测':'可发起补测'):'待准备';
 return `<span class="rr-input-state ${status}">${esc(label)}</span>${!ready?`<small>${esc(waitingReason(c.case_id))}</small>`:''}${taskLabel(c.case_id)?`<small>${esc(taskLabel(c.case_id))}</small>`:''}`;
}
const taskMatches=id=>JSON.stringify(saved?.task?.case_input_ids?.[id]||[saved?.task?.input_ids?.[id]])===JSON.stringify(currentInputs(id))
 &&JSON.stringify(saved?.task?.confirmations?.[id]||null)===JSON.stringify(saved?.readiness?.[id]?.confirmation||null)
 &&JSON.stringify(saved?.task?.resolved_questions?.[id]||[])===JSON.stringify(saved?.readiness?.[id]?.resolved_questions||[]);
const accountResources=[
 {pattern:/(?:^|[^a-z0-9])second-account(?=$|[^a-z0-9])/i,title:'另一个被测系统测试账号'},
 {pattern:/(?:^|[^a-z0-9])qq(?=$|[^a-z0-9])/i,title:'QQ 邮箱'},
 {pattern:/(?:^|[^a-z0-9])tencent(?=$|[^a-z0-9])/i,title:'腾讯文档'},
 {pattern:/(?:^|[^a-z0-9])atlassian(?=$|[^a-z0-9])/i,title:'Jira / Confluence'}
];
const relatedCases=g=>g.affected_case_ids.map(id=>cases.find(c=>c.case_id===id)).filter(Boolean);
function groupTitle(g){
 if(!['account','permission'].includes(g.kind))return g.title;
 const resource=accountResources.find(item=>item.pattern.test(g.title))||accountResources.find(item=>item.pattern.test(g.key||''));
 const scenarios=relatedCases(g).map(c=>c.scenario||'').join(' ');
 if(resource?.title==='QQ 邮箱'&&!/QQ\s*邮箱|邮箱授权码/.test(scenarios+' '+JSON.stringify(g.input_fields||[])))return g.title;
 if(resource?.title==='腾讯文档'&&!/腾讯文档/.test(scenarios))return g.title;
 return resource?.title||g.title;
}
function groupHelpMarkup(g){
 const fields=g.input_fields||[];
 const requirements=fields.map(field=>field.label+'（必填）');
 const check=g.check||{};
 const reason=check.observed||(check.status==='ready'?'前置条件已通过，补测时按原流程核对':'报告未记录前置检查结果，补测前请先核对该条件');
 const reasonLabel=check.status==='blocked'?'当前阻塞原因':'共用数据说明';
 const note=fields.some(field=>field.label==='邮箱授权码')?'填写邮箱授权码，不填登录密码。':fields.some(field=>field.label==='登录账号')?'原报告未记录登录账号是手机号、邮箱还是用户名。':'';
 return `<div class="rr-retest-explanation"><b>${fields.length?'可补充的账号信息':check.status==='blocked'?'补充阻塞相关数据':'共用测试数据'}</b><p>${reasonLabel}：${esc(reason)}</p>${requirements.length?`<ul>${requirements.map(value=>`<li>${esc(value)}</li>`).join('')}</ul>`:'<p>可补充已有业务数据、专有文件或解除阻塞的说明。合成测试数据仍由 AI 按原流程准备，关联用例中的测试输入不是要求你提供的清单。</p>'}${note?`<p>${esc(note)}</p>`:''}</div>`;
}
function groupContext(g){
 const environment={prod:'生产环境（prod）',pre:'预发布环境（pre）',test:'测试环境（test）',dev:'开发环境（dev）',local:'本地环境（local）'}[g.environment]||g.environment;
 return [environment&&'环境：'+environment,g.tenant&&'账号范围 / 企业：'+g.tenant,g.role&&'角色：'+g.role].filter(Boolean).join(' · ');
}
function groupCasesMarkup(g){
 return `<ul class="rr-retest-related-cases">${g.affected_case_ids.map(id=>{const c=cases.find(item=>item.case_id===id);return `<li><b>${esc(id)}</b> ${esc(c?.scenario||'未记录场景')}${c?.precondition?`<p>前置条件：${esc(c.precondition)}</p>`:''}${c?.test_data?`<p>所需测试数据：${esc(c.test_data)}</p>`:''}</li>`;}).join('')}</ul>`;
}
function chooseDefaultScope(panel){
 const ids=JSON.parse(panel.dataset.caseIds),groups=groupsFor(ids);
 if(!ids.some(id=>saved?.case_overrides.includes(id))&&groups.length)panel.dataset.groupId=groups.find(g=>!g.input_id)?.id||groups[0].id;
}
function scopeMarkup(panel){
 if(panel.dataset.launch==='true')return '';
 const original=JSON.parse(panel.dataset.caseIds),groups=groupsFor(original),group=groupOf(panel);
 if(!groups.length)return '';
 return `<div class="rr-retest-shared"><label>数据应用范围<select data-retest-scope aria-label="数据应用范围">${groups.map(g=>`<option value="${esc(g.id)}" ${g.id===group?.id?'selected':''}>共同阻塞：${esc(groupTitle(g))} · ${g.affected_case_ids.length} 条用例</option>`).join('')}<option value="" ${group?'':'selected'}>${original.length===1?'仅此用例（单独数据）':'仅所选用例（单独数据）'}</option></select></label><p data-retest-scope-note>${scopeNote(panel)}</p><div data-retest-scope-help>${group?groupHelpMarkup(group):''}</div><details><summary>查看关联用例与数据要求</summary><div data-retest-scope-ids>${group?groupCasesMarkup(group):idsOf(panel).map(esc).join('、')}</div></details></div>`;
}
function scopeNote(panel){
 const g=groupOf(panel);return g?`${esc(groupContext(g))}。保存一次同步 ${g.affected_case_ids.length} 条；以后修改这份共用数据也会同步。${g.override_case_ids.length?'本次同步将包含之前单独设置数据的 '+g.override_case_ids.length+' 条用例。':''}`:'本次仅修改所选用例，其他关联用例继续使用共用数据。';
}
function bindScope(panel,onChange){
 panel.querySelector('[data-retest-scope]')?.addEventListener('change',event=>{
  panel.dataset.groupId=event.target.value;panel.querySelector('[data-retest-scope-note]').innerHTML=scopeNote(panel);
  const group=groupOf(panel);
  panel.querySelector('[data-retest-scope-help]').innerHTML=group?groupHelpMarkup(group):'';
  panel.querySelector('[data-retest-scope-ids]').innerHTML=group?groupCasesMarkup(group):idsOf(panel).map(esc).join('、');onChange();
 });
}
function renderGroups(){
 let area=$('rr-retest-groups');if(!area){area=document.createElement('section');area.id='rr-retest-groups';area.setAttribute('aria-label','共用测试数据');$('rr-retest-batch').before(area);}
 const groups=saved?.groups||[];area.hidden=!groups.length;
 const shared=$('rr-retest-shared');if(shared){shared.hidden=!groups.length;const filled=groups.filter(g=>g.input_id).length;$('rr-retest-shared-count').textContent=`${groups.length} 项 · 已填 ${filled} 项 · 待填 ${groups.length-filled} 项`;}
 const key=JSON.stringify([groups,groups.map(g=>g.affected_case_ids.map(isReady))]);if(area.dataset.key===key)return;area.dataset.key=key;
 area.innerHTML=`<div class="rr-retest-groups-heading"><h3>共用测试数据</h3><p>相同前置数据按组填写一次，下面列出会同步使用这份数据的用例；补测仍按原流程检查执行条件。</p></div>${groups.map(g=>{const check=g.check||{};const reason=check.observed||'报告未记录前置检查结果，补测前请先核对该条件';const method=check.method||'尚未记录检查方法';return `<article><div><strong>${esc(groupTitle(g))}</strong><span>${g.affected_case_ids.length} 条用例受影响</span><p>${esc(groupContext(g))}${g.input_ref?' · 单独设置的数据':''}</p>${groupHelpMarkup(g)}<details><summary>查看测试场景和阻塞原因</summary><p><b>${check.status==='blocked'?'本轮阻塞原因':'共用数据条件'}：</b>${esc(reason)}</p>${groupCasesMarkup(g)}<p>原始条件名称：${esc(g.title)}</p><p>检查方法：${esc(method)}${check.status==='blocked'?'；原报告前置检查未通过，关联业务步骤已跳过。':'；本轮尚未记录该条件的前置检查。'}</p></details></div><div class="rr-retest-group-actions"><span>${g.input_id?'共用数据已补充，待检查':'待补充共用数据'}</span><button type="button" data-retest-group="${esc(g.id)}">${g.input_id?'修改共用数据':'补充一次，同步 '+g.affected_case_ids.length+' 条'}</button>${g.input_id?`<button type="button" class="rr-retest-primary" data-retest-group-start="${esc(g.id)}" ${g.affected_case_ids.some(isReady)?'':'disabled'}>补测已就绪的 ${g.affected_case_ids.filter(isReady).length} 条${g.affected_case_ids.every(isReady)?'':'（仍有用例待准备）'}</button>`:''}</div></article>`}).join('')}`;
}
function taskLabel(id){
 const task=saved?.task;if(!task?.case_ids.includes(id)||!taskMatches(id))return '';
 if(task.report_url)return '补测报告已生成';
 const phase=task.progress?.phase;
 return phase==='waiting'?'待发送给 Codex':phase==='failed'?'补测执行异常':phase==='completed'?'正在同步补测报告':'补测进行中';
}
function renderToolbar(){
 const bar=$('rr-retest-batch');if(!bar)return;
 if(!bar.dataset.initialized){
  bar.dataset.initialized='true';
  bar.innerHTML='<div class="rr-retest-toolbar-head"><h3>用例补测</h3><span data-retest-counts role="status">正在读取补测准备状态…</span><label>补测准备状态<select id="rr-retest-data-filter" aria-label="按补测准备状态筛选"><option value="all">全部用例</option><option value="missing">待补数据 / 待确认</option><option value="saved">已就绪，可发起</option></select></label></div><div class="rr-retest-toolbar-actions"><button type="button" data-retest-select-filtered>全选当前筛选</button><button type="button" data-retest-select-saved>只选已就绪</button><button type="button" data-retest-clear>清空选择</button><button type="button" data-retest-bulk>批量补充数据</button><button type="button" data-retest-bulk-start>补测所选就绪用例</button><button type="button" class="rr-retest-primary" data-retest-all-saved>补测全部就绪用例</button></div><p class="rr-retest-toolbar-note" data-retest-selection role="status" hidden></p><p class="rr-retest-batch-message" role="status"></p>';
  root.ReportSelects?.upgrade(bar);
  $('rr-retest-data-filter').onchange=event=>{dataFilter=event.target.value;review.renderCases(true);};
 }
 const all=cases.filter(eligible),filled=all.filter(c=>isReady(c.case_id)),chosen=[...selected],ready=chosen.filter(isReady),missing=all.length-filled.length;
 bar.querySelector('[data-retest-counts]').textContent=saved?`本报告未完全通过 ${all.length} 条可选 · 已就绪 ${filled.length} 条 · 待准备 ${missing} 条（全报告范围）`:(loadingError||'正在读取补测准备状态…');
 let inventory=bar.querySelector('[data-retest-inventory]');if(!inventory){inventory=document.createElement('details');inventory.dataset.retestInventory='';bar.append(inventory);}
 inventory.innerHTML=`<summary>查看补测包含哪些用例：${esc(statusSummary(all))}</summary><p>只排除完全通过用例。已就绪表示可以发起任务，执行时仍需核对条件；保存确认或数据不会改写原报告结果。当前表格筛选 ${filteredEligible().length} 条，全部就绪按钮使用全报告范围。</p>${caseList(all.map(c=>c.case_id))}`;
 const selectionNote=bar.querySelector('[data-retest-selection]');
 selectionNote.hidden=!chosen.length;
 selectionNote.textContent=chosen.length?`已选 ${chosen.length} 条 · 已就绪 ${ready.length} 条 · 待准备 ${chosen.length-ready.length} 条；跨页保留选择`:'';
 bar.querySelector('[data-retest-all-saved]').textContent=`补测全部就绪用例（${filled.length}）`;
 bar.querySelector('[data-retest-all-saved]').disabled=!saved||!filled.length;
 bar.querySelector('[data-retest-bulk-start]').textContent=`补测所选就绪用例（${ready.length}）`;
 bar.querySelector('[data-retest-bulk-start]').disabled=!saved||!chosen.length;
 bar.querySelector('[data-retest-bulk]').disabled=!saved||!chosen.length;
 bar.querySelector('[data-retest-clear]').disabled=!chosen.length;
 bar.querySelector('[data-retest-select-filtered]').disabled=!saved||!filteredEligible().length;
 bar.querySelector('[data-retest-select-saved]').disabled=!saved||!filteredEligible().some(c=>isReady(c.case_id));
}
function decorateRows(){
 const ids=new Set(cases.filter(eligible).map(c=>c.case_id));for(const id of selected)if(!ids.has(id))selected.delete(id);
 for(const box of document.querySelectorAll('[data-retest-select]'))box.checked=selected.has(box.dataset.retestSelect);
 for(const button of document.querySelectorAll('[data-case-action-index]')){const c=cases[Number(button.dataset.caseActionIndex)];button.textContent=actionLabel(c);button.disabled=actionConfirmed(c);}
 for(const node of document.querySelectorAll('[data-retest-state]')){const c=cases.find(c=>c.case_id===node.dataset.retestState);if(c)node.innerHTML=caseDataMarkup(c);}
 const all=$('rr-retest-select-all'),available=filteredEligible(),chosen=available.filter(c=>selected.has(c.case_id));
 if(all){all.disabled=!saved||!available.length;all.checked=!!available.length&&chosen.length===available.length;all.indeterminate=!!chosen.length&&chosen.length<available.length;}
 renderToolbar();
}

const panelKey=panel=>JSON.stringify([idsOf(panel).map(id=>[currentInputs(id),saved?.readiness?.[id]]),saved?.revision,saved?.task?.task_id,saved?.task?.progress?.phase,saved?.task?.report_url]);
async function refresh(){
 saved=await api(base+'/retest-inputs');loadingError='';review.renderCases();renderGroups();
 for(const panel of panels){if(!panel.isConnected){panels.delete(panel);continue;}if(!panel.dataset.editing&&panel._summaryKey!==panelKey(panel)&&(!panel.querySelector('.rr-retest-handoff')||saved.task?.report_url))renderSummary(panel);}
}
function attach(detail,c){
 if(!eligible(c))return;
 const section=document.createElement('section');section.className='rr-retest-section';section.dataset.caseIds=JSON.stringify([c.case_id]);
 chooseDefaultScope(section);
 detail.querySelector('h2').after(section);
 const reason=document.createElement('p');reason.className='rr-retest-blocker';reason.textContent='原报告结果说明：'+(c.not_run_reason||c.evidence||c.actual||'补测前核对该用例的执行条件');section.before(reason);
 panels.add(section);renderSummary(section);
}
function idsOf(panel){return groupOf(panel)?.affected_case_ids||JSON.parse(panel.dataset.caseIds);}
function renderSummary(panel,message=''){
 delete panel.dataset.editing;
 panel._summaryKey=panelKey(panel);
 const ids=idsOf(panel),input=inputOf(panel),ready=!!ids.length&&ids.every(isReady);
 const title=panel.dataset.launch==='true'?`统一补测 ${ids.length} 条已就绪用例`:groupOf(panel)?'共同阻塞 · '+groupTitle(groupOf(panel)):ids.length===1?'补充测试数据':`为 ${ids.length} 条用例补充数据`;
 const task=saved?.task,linked=task?.case_ids.some(id=>ids.includes(id)&&taskMatches(id));
 panel.innerHTML=`<div class="rr-retest-heading"><div><h3>${esc(title)}</h3><p>${ready?'核对本次清单后一次发起；原报告结论保留。':'可继续补充数据、确认操作或明确规则，然后统一发起。'}</p></div><span class="rr-retest-state">${ready?'已就绪':'待准备'}</span></div>${input?`<div class="rr-retest-saved">${esc(input.account_mode==='credentials'?`${input.account.role||'测试账号'}${input.account.username?' · '+input.account.username:''} · ${secretLabel(input)}已保存`:input.account_mode==='existing_session'?'复用已有登录态':'业务数据 / 测试文件')}${input.files.length?`<span>关联文件 ${input.files.length} 个</span>`:''}</div>`:''}<div class="rr-retest-actions"><button type="button" data-retest-edit ${saved&&ids.length?'':'disabled'}>${input?'修改补充数据':'补充测试数据（按需）'}</button><button type="button" class="rr-retest-primary" data-retest-start ${ready?'':'disabled'}>${ids.length===1?'补测此用例':'补测所选用例'}</button></div><p class="rr-retest-message" role="status">${esc(message||loadingError||(!saved?'正在读取补充数据…':''))}</p>${linked?`<div class="rr-retest-task"><strong>${esc(taskLabel(ids.find(id=>task.case_ids.includes(id))))}</strong>${task.report_url?`<a href="${esc(task.report_url)}" target="_blank" rel="noopener">查看新补测报告 ↗</a>`:'<button type="button" data-retest-prompt>查看 / 复制 Codex 任务</button>'}</div>`:''}`;
 const excluded=JSON.parse(panel.dataset.excludedIds||'[]');
 panel.querySelector('.rr-retest-heading').insertAdjacentHTML('afterend',`<p class="rr-retest-scope">本次准备执行 ${ids.length} 条；条件未就绪 ${excluded.length} 条暂不执行，保留原报告状态。</p><details open class="rr-retest-included"><summary>本次执行清单（${ids.length} 条）</summary>${caseList(ids)}</details>${excluded.length?`<details class="rr-retest-excluded"><summary>查看未纳入的 ${excluded.length} 条用例</summary>${caseList(excluded)}</details>`:''}`+scopeMarkup(panel));
 root.ReportSelects?.upgrade(panel);
 if(groupOf(panel))panel.querySelector('[data-retest-start]').textContent=`补测关联的 ${ids.length} 条用例`;
 bindScope(panel,()=>renderSummary(panel));
 panel.querySelector('[data-retest-edit]').onclick=()=>renderEditor(panel);
 panel.querySelector('[data-retest-start]').onclick=()=>start(panel);
 if(linked&&!task.report_url&&ids.length===task.case_ids.length&&ids.every(id=>task.case_ids.includes(id)&&taskMatches(id))){
  const startButton=panel.querySelector('[data-retest-start]');startButton.disabled=true;startButton.textContent='补测任务已准备';
 }
 panel.querySelector('[data-retest-prompt]')?.addEventListener('click',()=>handoff(panel));
}
function renderEditor(panel, reuse){
 panel.dataset.editing='true';
 const ids=idsOf(panel),group=groupOf(panel);
 let input=reuse===null?null:reuse||inputOf(panel);
 const account=input?.account||{role:group?.role||'',tenant:group?.tenant||''},mode=input?.account_mode||(group&&['file','data','service','other'].includes(group.kind)?'none':'credentials');
 let files=[...(input?.files||[])],dirty=false;
 const profileKeys=new Set();
 const profiles=[...(input?[input]:[]),...saved.profiles.slice().reverse()].filter(p=>{
  if(group&&['account','permission'].includes(group.kind)&&(p.account_mode==='none'||p.account.role!==group.role||p.account.tenant!==group.tenant))return false;
  if(group&&!['account','permission'].includes(group.kind)&&p.account_mode!=='none')return false;
  const expected=group?.input_fields?.find(field=>field.name==='password')?.credential_type;if(expected&&p.account_mode==='credentials'&&p.account.credential_type!==expected&&p.id!==input?.id)return false;
  const key=JSON.stringify([p.account_mode,p.account.credential_type,p.account.role,p.account.tenant,p.account.username,p.files.map(f=>f.filename)]);
  if(profileKeys.has(key))return false;profileKeys.add(key);return true;
 });
 panel.innerHTML=`<div class="rr-retest-heading"><div><h3>${ids.length===1?'补充测试数据':`批量补充 · ${ids.length} 条用例`}</h3><p>保存后留在当前页面，补测需单独发起。</p></div></div><form class="rr-retest-form">${profiles.length?`<label>复用已保存的数据<select name="reuse"><option value="">填写新数据</option>${profiles.map(p=>`<option value="${esc(p.id)}" ${input?.id===p.id?'selected':''}>${esc(p.account_mode==='none'?'数据 / 文件 · '+(p.files.map(f=>f.filename).join('、')||p.business_data.slice(0,24)):(p.account.role||'测试账号')+' · '+(p.account_mode==='credentials'?(p.account.username||secretLabel(p)+'已保存'):'已有登录态'))}</option>`).join('')}</select></label>`:''}<fieldset class="rr-retest-modes"><legend>登录方式</legend>${[['credentials','账号密码'],['existing_session','已有登录态'],['none','无需登录信息']].map(([key,label])=>`<label><input type="radio" name="account_mode" value="${key}" ${mode===key?'checked':''}>${label}</label>`).join('')}</fieldset><div class="rr-retest-account"><div class="rr-retest-grid"><label>账号角色<input name="role" maxlength="500" value="${esc(account.role||'')}" placeholder="例如：HR 管理员"></label><label>租户 / 企业（可选）<input name="tenant" maxlength="500" value="${esc(account.tenant||'')}" placeholder="账号所属租户"></label></div><div class="rr-retest-grid rr-retest-credentials"><label><span data-retest-username-label>登录账号</span><input name="username" maxlength="500" autocomplete="off" value="${esc(account.username||'')}" placeholder="填写测试账号"></label><label><span data-retest-password-label>登录密码</span><input name="password" type="password" maxlength="4000" autocomplete="new-password" placeholder="${account.has_password?'已保存，留空保留':'填写密码'}"></label></div><p class="rr-retest-help">密码独立加密保存，不进入报告；已有登录态仍需执行时核对。</p></div><label>业务数据 / 补充说明<textarea name="business_data" rows="3" maxlength="30000" placeholder="例如：测试订单编号、需要准备的数据、阻塞解除条件。账号密码请填在上方。">${esc(input?.business_data||'')}</textarea></label><div class="rr-retest-files"><label class="rr-retest-file-pick">添加测试文件<input type="file" multiple aria-label="添加测试文件"></label><span>最多 5 个，单个 10 MB，总计 20 MB</span><ul></ul></div><p class="rr-retest-message" role="status"></p><div class="rr-retest-actions"><button type="button" data-retest-cancel>取消</button><button type="submit" class="rr-retest-primary">保存数据</button></div></form>`;
 const form=panel.querySelector('form'),message=panel.querySelector('.rr-retest-message');
 if(group)panel.querySelector('h3').textContent=`${groupTitle(group)} · ${ids.length} 条用例`;
 form.insertAdjacentHTML('afterbegin',scopeMarkup(panel));
 root.ReportSelects?.upgrade(panel);
 const applyGroupAccount=()=>{
  const g=groupOf(panel),shared=g&&['account','permission'].includes(g.kind),dataOnly=g&&!shared;
  const sourceGroups=groupsFor(JSON.parse(panel.dataset.caseIds)).filter(item=>item.input_fields?.length);
  const fields=g?.input_fields||(sourceGroups.length===1?sourceGroups[0].input_fields:[])||[];
  const username=fields.find(field=>field.name==='username'),secret=fields.find(field=>field.name==='password'),tokenOnly=!!fields.length&&!username;
  panel.dataset.tokenOnly=String(tokenOnly);
  form.querySelector('.rr-retest-credentials').classList.toggle('rr-retest-token-only',tokenOnly);
  form.querySelector('.rr-retest-account>.rr-retest-grid').hidden=!!shared;
  form.querySelector('[name=account_mode][value=none]').closest('label').hidden=!!shared;
  form.querySelector('[data-retest-username-label]').textContent=username?.label||'登录账号';
  form.querySelector('[data-retest-password-label]').textContent=secret?.label||'登录密码';
  form.elements.username.closest('label').hidden=tokenOnly;
  form.elements.username.placeholder=username?.label==='邮箱地址'?'例如：name@qq.com':username?.label==='账号邮箱'?'填写 Jira / Confluence 账号邮箱':'填写登录账号';
  form.elements.password.placeholder=account.has_password?'已保存，留空保留':'填写'+(secret?.label||'登录密码');
  form.querySelector('.rr-retest-modes label').lastChild.textContent=secret?.label==='邮箱授权码'?'邮箱地址和授权码':secret?.label==='个人授权令牌'?'账号邮箱和个人授权令牌':tokenOnly?'填写授权令牌':'账号密码';
  form.querySelector('.rr-retest-help').textContent=secret?.label==='邮箱授权码'?'填写邮箱生成的授权码，不填登录密码。授权码加密保存。':secret?.label==='个人授权令牌'?'填写个人授权令牌，不填 Atlassian 登录密码。令牌加密保存。':tokenOnly?'只需授权令牌，无需填写账号或密码。令牌加密保存。':'密码加密保存；已有登录态会在执行时核对。';
  form.querySelector('.rr-retest-modes').hidden=!!dataOnly;
  if(dataOnly)form.elements.account_mode.value='none';
  for(const key of ['role','tenant']){form.elements[key].readOnly=!!shared;if(shared)form.elements[key].value=g[key];}
 };

 applyGroupAccount();
 bindScope(panel,()=>{dirty=true;applyGroupAccount();showMode();});
 const renderFiles=()=>{panel.querySelector('.rr-retest-files ul').innerHTML=files.map((f,i)=>`<li><span>${esc(f.filename)} <small>${f.size<1024?f.size+' B':(f.size/1024).toFixed(1)+' KB'}</small></span><button type="button" data-file-remove="${i}" aria-label="移除 ${esc(f.filename)}">×</button></li>`).join('');};
 const showMode=()=>{const current=form.elements.account_mode.value;panel.querySelector('.rr-retest-account').hidden=current==='none';panel.querySelector('.rr-retest-credentials').hidden=current!=='credentials';form.elements.username.required=current==='credentials'&&panel.dataset.tokenOnly!=='true';if(panel.dataset.tokenOnly==='true')form.elements.username.value='';};
 showMode();renderFiles();
 form.oninput=()=>{dirty=true;};
 form.onchange=event=>{dirty=true;if(event.target.name==='account_mode')showMode();if(event.target.name==='reuse'){const value=saved.profiles.find(p=>p.id===event.target.value);renderEditor(panel,value||null);}};
 form.querySelector('[type=file]').onchange=event=>{files.push(...[...event.target.files].map(file=>({filename:file.name,size:file.size,file})));event.target.value='';dirty=true;renderFiles();};
 panel.querySelector('.rr-retest-files ul').onclick=event=>{const button=event.target.closest('[data-file-remove]');if(button){files.splice(Number(button.dataset.fileRemove),1);dirty=true;renderFiles();}};
 panel.querySelector('[data-retest-cancel]').onclick=()=>{if(!dirty||window.confirm('放弃本次尚未保存的数据？'))renderSummary(panel);};
 const dialog=panel.closest('dialog');
 dialog._retestDirty=()=>dirty&&panel.isConnected&&panel.dataset.editing;
 form.onsubmit=async event=>{
  event.preventDefault();message.textContent='';const save=form.querySelector('[type=submit]');save.disabled=true;
  try{
   if(files.length>5||files.some(f=>f.size>10*1024*1024)||files.reduce((n,f)=>n+f.size,0)>20*1024*1024)throw Error('最多 5 个文件，单个 10 MB，总计 20 MB');
   const uploads=await Promise.all(files.map(async f=>f.id?{id:f.id}:{filename:f.filename,content_base64:await readFile(f.file)}));
   const values=Object.fromEntries(new FormData(form));
   saved=await api(base+'/retest-inputs','PUT',{revision:saved.revision,case_ids:JSON.parse(panel.dataset.caseIds),group_id:panel.dataset.groupId||'',reuse_id:input?.id||'',account_mode:values.account_mode,account:{role:values.role,tenant:values.tenant,username:values.username,password:values.password},business_data:values.business_data,files:uploads});
   form.elements.password.value='';dirty=false;renderSummary(panel,groupOf(panel)?`共用数据已保存，已同步 ${idsOf(panel).length} 条用例。补测先检查前置条件，仍阻塞的业务步骤将跳过。`:'数据已保存。准备好后点击补测。');decorateRows();renderGroups();
  }catch(error){message.textContent=error.message;message.classList.add('rr-retest-error');save.disabled=false;}
 };
 form.querySelector('[name=role]')?.focus({preventScroll:true});
}
function readFile(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]||'');reader.onerror=()=>reject(Error('文件读取失败，请重新选择'));reader.readAsDataURL(file);});}
function bindDialog(dialog){
 dialog.oncancel=event=>{if(dialog._retestDirty?.()&&!window.confirm('放弃本次尚未保存的数据？'))event.preventDefault();};
 const close=dialog.querySelector('.rr-case-close');
 if(close)close.onclick=()=>{if(!dialog._retestDirty?.()||window.confirm('放弃本次尚未保存的数据？'))dialog.close();};
}
function openCase(c,edit=false){
 let dialog=$('rr-case-dialog');if(!dialog){dialog=document.createElement('dialog');dialog.id='rr-case-dialog';dialog.className='rr-case-dialog';document.body.append(dialog);}
 review.showCaseDetail(dialog,c);bindDialog(dialog);if(!dialog.open)dialog.showModal();
 if(edit){const panel=dialog.querySelector('.rr-retest-section');if(saved)renderEditor(panel);else panel.querySelector('.rr-retest-message').textContent=loadingError||'正在读取数据，请稍后重试';}
}
function openBatch(groupId='',edit=true,requestedIds=null,excludedIds=[]){
 if(!batchDialog){batchDialog=document.createElement('dialog');batchDialog.className='rr-case-dialog rr-retest-batch-dialog';batchDialog.id='rr-retest-batch-dialog';document.body.append(batchDialog);}
 const group=saved?.groups.find(g=>g.id===groupId),ids=group?group.affected_case_ids:requestedIds||[...selected];
 batchDialog.innerHTML=`<button type="button" class="rr-case-close" aria-label="关闭补测窗口">×</button><h2>${edit?(group?'补充共同阻塞数据':'批量补充测试数据'):'发起补测'}</h2><p class="rr-retest-scope">本次关联 ${ids.length} 条：${ids.map(esc).join('、')}</p><section class="rr-retest-section"></section>`;
 const panel=batchDialog.querySelector('section');panel.dataset.caseIds=JSON.stringify(ids);panel.dataset.excludedIds=JSON.stringify(excludedIds);panel.dataset.launch=String(!edit);if(group)panel.dataset.groupId=group.id;else if(edit)chooseDefaultScope(panel);panels.add(panel);renderSummary(panel);batchDialog._retestBound=false;bindDialog(batchDialog);batchDialog.showModal();if(saved&&edit)renderEditor(panel);return panel;
}
function requestId(){const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;const hex=[...bytes].map(b=>b.toString(16).padStart(2,'0')).join('');return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;}
async function start(panel){
 const button=panel.querySelector('[data-retest-start]'),message=panel.querySelector('.rr-retest-message');button.disabled=true;message.textContent='正在准备补测任务…';
 try{
  const ids=idsOf(panel);panel._requestId=saved?.task?.report_url?requestId():panel._requestId||requestId();
  const prepared=await api(base+'/retests','POST',{case_ids:ids,excluded_case_ids:JSON.parse(panel.dataset.excludedIds||'[]'),revision:saved.revision,request_id:panel._requestId});
  panel._task=prepared.task;
  await refresh();renderSummary(panel);await handoff(panel);
 }catch(error){message.textContent=error.message;button.disabled=false;}
}
async function handoff(panel){
 let holder=panel.querySelector('.rr-retest-handoff');if(holder){holder.scrollIntoView({block:'nearest'});return;}
 holder=document.createElement('div');holder.className='rr-retest-handoff';holder.innerHTML='<h4>交给 Codex 补测</h4><p>复制任务消息发给 Codex 后开始执行，报告页面可以继续查看。</p><p class="rr-retest-message" role="status">正在生成任务消息…</p>';panel.append(holder);
 try{
  const pair=await api(base+'/collaboration/pair','POST'),task=panel._task||saved.task;
  const prompt=`测试台地址：${location.origin}\n接入与执行说明：${location.origin}/static/agent-guide.md\n工具格式：${location.origin}/static/agent-tools.json\n连接码：${pair.code}\n请连接同一测试台，读取下方独立轮次的补测任务与平台 Skill，不使用原探索轮次的执行 ID。业务操作前按 get_test_document.parallel_execution_guidance 使用 coordinate_ui_resources 占用真实账号和浏览器资源；仅共享资源串行，独立工作可并行。\n会话 ID：${task.project_id}\n补测任务 ID：${task.task_id}\n条件尚未就绪、未纳入本轮的用例：${(task.excluded_case_ids||[]).join('、')||'无'}；这些用例保留原报告状态，不执行、不记为通过。\n仅补测用例：${task.case_ids.join('、')}\n先读取 get_test_document，核对补测任务 ID 和已保存的操作确认、规则结论，不重复索要相同确认。保留原订单等业务关联及已完成步骤，不重复提交或付款；规则变化先修订预期及依据再验证。再用 get_ui_retest_inputs 携带 task_id 读取专用数据，检查绑定目标和账号权限。用 get_ui_retest_file 获取已关联文件。用 get_ui_test_cases 直接读取平台已准备的本轮基线、execution_id 和 revision，不重写整份用例；共同前置条件轻量检查一次，用 record_ui_dependency_check 保存真实方法和结果。按 execution_plan 跳过仍然阻塞的关联业务步骤，不重复登录、上传或等待；条件恢复后才继续业务断言。已明确的同组动作放在一次浏览器调用内连续执行，使用随包 scripts/execution-batch.cjs 保留结果队列和续跑位置；只有差异或未知分支才返回判断。结果按批次只提交 case_id 与变化字段，不重传设计全文。凭据不得输出到聊天、日志、用例或报告。复用原用例编号，在同一会话保存新的独立补测报告，保留原报告；执行前读取 get_test_document.scene_retention，以本轮持久化选择为准，按该选择收尾并核对本轮数据和浏览器资源。不要自动提交 PingCode 或发送通知。`;
  holder.innerHTML='<h4>交给 Codex 补测</h4><p>复制下面的任务消息发给 Codex 后开始执行。</p><textarea readonly rows="5" aria-label="Codex 补测任务消息"></textarea><div class="rr-retest-actions"><button type="button" class="rr-retest-primary">复制补测任务</button></div><p class="rr-retest-message" role="status"></p>';
  const field=holder.querySelector('textarea');field.value=prompt;
  holder.querySelector('button').onclick=async()=>{try{if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(field.value);else{field.focus();field.select();if(!document.execCommand('copy'))throw Error('请选中消息手动复制');}holder.querySelector('[role=status]').textContent='已复制，请发给 Codex。';}catch(error){holder.querySelector('[role=status]').textContent=error.message;}};
 }catch(error){holder.querySelector('[role=status]').textContent=error.message;const retry=document.createElement('button');retry.textContent='重新获取任务消息';retry.type='button';retry.onclick=()=>{holder.remove();handoff(panel);};holder.append(retry);}
}
function startSaved(candidates){
 const ids=candidates.filter(c=>isReady(c.case_id)).map(c=>c.case_id),excluded=candidates.filter(c=>!isReady(c.case_id)).map(c=>c.case_id);
 if(!candidates.length)return;
 const panel=openBatch('',false,ids,excluded),task=saved.task;
 if(task&&!task.report_url&&task.case_ids.length===ids.length&&ids.every(id=>task.case_ids.includes(id)&&taskMatches(id))&&JSON.stringify(task.excluded_case_ids||[])===JSON.stringify(excluded))handoff(panel);

}
document.addEventListener('change',event=>{
 if(event.target.matches('[data-retest-select]')){const id=event.target.dataset.retestSelect;event.target.checked?selected.add(id):selected.delete(id);decorateRows();}
 if(event.target.id==='rr-retest-select-all'){for(const c of filteredEligible())event.target.checked?selected.add(c.case_id):selected.delete(c.case_id);decorateRows();}
});
document.addEventListener('click',event=>{
 const button=event.target.closest('button');if(!button)return;
 if(button.dataset.retestIndex!==undefined)openCase(cases[Number(button.dataset.retestIndex)],true);
 if(button.hasAttribute('data-retest-group'))openBatch(button.dataset.retestGroup);
 if(button.hasAttribute('data-retest-group-start')){
  const group=saved?.groups.find(g=>g.id===button.dataset.retestGroupStart);
  if(group)startSaved(cases.filter(c=>eligible(c)&&group.affected_case_ids.includes(c.case_id)));
 }

 if(button.hasAttribute('data-retest-bulk'))openBatch();
 if(button.hasAttribute('data-retest-clear')){selected.clear();decorateRows();}
 if(button.hasAttribute('data-retest-select-filtered')){for(const c of filteredEligible())selected.add(c.case_id);decorateRows();}
 if(button.hasAttribute('data-retest-select-saved')){selected.clear();for(const c of filteredEligible())if(isReady(c.case_id))selected.add(c.case_id);decorateRows();}
 if(button.hasAttribute('data-retest-bulk-start'))startSaved(cases.filter(c=>selected.has(c.case_id)&&eligible(c)));
 if(button.hasAttribute('data-retest-all-saved'))startSaved(cases.filter(eligible));
});
root.ReportRetest={matchesFilter,caseDataMarkup,refresh,actionLabel,actionConfirmed,eligible,attach:(detail,c)=>{attach(detail,c);detail._retestBound=false;bindDialog(detail);},decorateRows};
decorateRows();
refresh().then(()=>{const id=new URLSearchParams(location.hash.slice(1)).get('inputs'),c=cases.find(c=>c.case_id===id&&eligible(c));if(c){document.querySelector('[data-rr-tab="cases"]').click();openCase(c,true);}}).catch(error=>{loadingError=error.message;decorateRows();for(const panel of panels)renderSummary(panel);});
setInterval(()=>{if(saved?.task&&!saved.task.report_url&&!document.hidden)refresh().catch(()=>{});},8000);
})(globalThis);
