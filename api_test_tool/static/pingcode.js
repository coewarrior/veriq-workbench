/* Shared by the integration page and online reports. */
(() => {
'use strict';
const $=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let csrf='',config=null;
async function call(url,method='GET',body){if(!csrf){const b=await fetch('/api/bootstrap');if(!b.ok)throw Error('会话失效，请返回测试台重新打开报告');csrf=(await b.json()).csrf;}const r=await fetch(url,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,...(window.ReportAggregateHeaders?.()||{})},body:body===undefined?undefined:JSON.stringify(body)});let data;try{data=await r.json()}catch{throw Error('服务器响应无效，请刷新状态后核对。')}if(!r.ok){const error=Error(data.detail||'请求失败');error.httpStatus=r.status;throw error;}return data;}
const endpoint='/api/integrations/pingcode';
function message(id,text,error=false){$(id).textContent=text;$(id).classList.toggle('pc-error',error);}
function options(node,values,selected='',empty='请选择'){node.innerHTML=`<option value="">${esc(empty)}</option>`+values.map(v=>`<option value="${esc(v.id)}">${esc(v.name||v.display_name||v.id)}</option>`).join('');node.value=selected;}
async function busy(button,work,id){if(button.disabled)return;button.disabled=true;button.setAttribute('aria-busy','true');try{await work()}catch(e){message(id,e.message,true)}finally{button.disabled=false;button.removeAttribute('aria-busy')}}
function authFields(){const mode=$('pc-config-form').elements.auth_mode.value;document.querySelectorAll('[data-client]').forEach(x=>x.hidden=mode!=='client_credentials');document.querySelector('[data-token]').hidden=mode!=='token';}
async function configPage(){
 const form=$('pc-config-form');
 async function load(){config=await call(endpoint);for(const [k,v]of Object.entries(config))if(form.elements[k])form.elements[k].value=v;$('pc-config-status').textContent=config.configured?'已保存授权 · 待测试':'未配置';$('pc-scope').textContent=config.shared?'当前使用管理员共享配置。保存个人配置需自行填写凭据；只影响当前账号。':'个人配置仅用于当前账号。管理员也可配置全员共用的连接。';authFields();}
 async function types(){const pid=$('pc-default-project').value;if(!pid){options($('pc-default-type'),[]);return}const m=await call(endpoint+'/metadata?project_id='+encodeURIComponent(pid));options($('pc-default-type'),m.types,m.type_id);}
 async function projects(){const p=await call(endpoint+'/projects');options($('pc-default-project'),p.values,config.default_project_id);message('pc-default-message',`连接成功，读取到 ${p.values.length} 个项目。读取成功不代表具有创建权限。`);$('pc-config-status').textContent='项目读取成功';await types();}
 form.elements.auth_mode.onchange=authFields;
 form.onsubmit=e=>{e.preventDefault();busy(e.submitter,async()=>{config=await call(endpoint,'PUT',Object.fromEntries(new FormData(form)));form.elements.client_secret.value='';form.elements.access_token.value='';message('pc-config-message','配置已保存，正在读取项目…');await projects();message('pc-config-message','配置已保存并连接成功。');},'pc-config-message')};
 $('pc-refresh').onclick=e=>busy(e.target,projects,'pc-default-message');
 $('pc-default-project').onchange=()=>types().catch(e=>message('pc-default-message',e.message,true));
 $('pc-save-default').onclick=e=>busy(e.target,async()=>{if(!$('pc-default-project').value||!$('pc-default-type').value)throw Error('请选择项目与缺陷类型');if(config.shared)throw Error('管理员共享配置请在服务器修改默认值，或先保存个人配置。');config=await call(endpoint,'PUT',{default_project_id:$('pc-default-project').value,default_type_id:$('pc-default-type').value});message('pc-default-message','默认项目与类型已保存。');},'pc-default-message');
 $('pc-clear').onclick=e=>busy(e.target,async()=>{if(!confirm('清除当前账号的 PingCode 配置？历史提交记录会保留。'))return;await call(endpoint,'DELETE');await load();options($('pc-default-project'),[]);options($('pc-default-type'),[]);message('pc-config-message','个人配置已清除。');},'pc-config-message');
 await load();
}
const reportPath=location.pathname.match(/^\/api\/projects\/([a-f0-9-]+)\/reports\/(total|[a-f0-9-]+)\/index.html$/);
const publicReport=document.querySelector('meta[name="api-test-public-report"]')?.content||'';
const triage=window.PingCodeTriage;
let dialog,route,currentButton,meta=null,sequence=0,opening=0,currentDraft=null,batchEntries=null,sending=false,stopRequested=false,screenshots=[];
const maxScreenshots=3,maxScreenshotBytes=5*1024*1024,allowedScreenshotTypes=new Set(['image/png','image/jpeg','image/webp']);
const buttons=new Map(), selections=new Map(), records=new Map();
const edits=new Map();let batchExcluded=[];
const backgroundJobs=new Map(),busyDrafts=new Set(),appliedBatchItems=new Map();let batchPollTimer=null,batchPolling=false;
const isBusy=id=>busyDrafts.has(id);
const newJobId=()=>typeof crypto.randomUUID==='function'?crypto.randomUUID():'10000000-1000-4000-8000-100000000000'.replace(/[018]/g,c=>(Number(c)^crypto.getRandomValues(new Uint8Array(1))[0]&15>>Number(c)/4).toString(16));
const lifecycleLabels={result_corrected:'结果已更正',pending_submission:'待提交',submitted:'已提交',rejected:'已拒绝',deferred:'暂缓',pending_regression:'待回归',regression_passed:'回归通过',regression_failed:'回归失败'};
function rememberReview(){
 if(!dialog||!currentButton||batchEntries||!currentDraft||!triage.canSubmit(currentDraft.record)||records.get(currentButton.dataset.draft)?.status==='submitted')return;
 edits.set(currentButton.dataset.draft,{title:$('pc-title').value,description:$('pc-description').value,screenshots:screenshots.slice()});
 window.ReportReview?.update();
}
function presentReview(batch){
 if(dialog.open)dialog.close();
 const dock=!batch&&$('rr-review-dock');
 (dock||document.body).append(dialog);dialog.classList.toggle('pc-docked',!!dock);
 if(dock){dock.querySelector('.rr-empty')?.remove();dialog.show();}else dialog.showModal();
}
const contentWarning=record=>record?.description_error||record?.screenshot_error||'';
const draftProject=id=>{
 const source=$(id)?.closest('[data-pingcode-project]')?.dataset.pingcodeProject;
 return source&&/^[a-f0-9-]+$/.test(source)?source:reportPath[1];
};
const draftReport=id=>{
 const source=$(id)?.closest('[data-pingcode-report]')?.dataset.pingcodeReport;
 return source&&/^[a-f0-9-]+$/.test(source)?source:reportPath[2];
};
const draftSourceId=id=>{
 const source=$(id)?.closest('[data-pingcode-draft]')?.dataset.pingcodeDraft;
 return source&&/^(defect|finding)-\d{1,5}$/.test(source)?source:id;
};
const draftRoute=id=>`/api/projects/${draftProject(id)}/reports/${draftReport(id)}/pingcode/${draftSourceId(id)}`;
function updateSubmitState(){$('pc-submit').disabled=!meta||sending||(!batchEntries&&isBusy(currentButton?.dataset.draft))||!!batchEntries&&!batchEntries.some(entry=>triage.canSubmit(entry.record));}
function clearReviewHint(){
 $('pc-reviewed').removeAttribute('aria-invalid');$('pc-review-confirmation').classList.remove('pc-review-required');$('pc-review-hint').hidden=true;$('pc-review-hint').textContent='';
}
function requestReview(){
 const review=$('pc-reviewed');
 review.setAttribute('aria-invalid','true');$('pc-review-confirmation').classList.add('pc-review-required');
 message('pc-review-hint','请先勾选审核确认，再点击确认并推送。',true);$('pc-review-hint').hidden=false;
 review.focus({preventScroll:true});
 $('pc-review-confirmation').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});
}
function reviewBeforeSubmit(e){if(!$('pc-reviewed').checked){e.preventDefault();requestReview();}}
function resetReview(){if($('pc-reviewed')){$('pc-reviewed').checked=false;clearReviewHint();updateSubmitState();}}
function renderScreenshots(){
 const list=$('pc-screenshot-list');if(!list)return;
 list.innerHTML='';screenshots.forEach((shot,index)=>{const figure=document.createElement('figure');const image=document.createElement('img');image.src=shot.preview;image.alt=`已粘贴截图 ${index+1}`;const preview=document.createElement('button');preview.type='button';preview.className='report-image-preview';preview.setAttribute('data-image-src',shot.preview);preview.setAttribute('aria-label',`放大预览：截图 ${index+1}`);preview.title='点击放大';preview.append(image);const remove=document.createElement('button');remove.type='button';remove.className='pc-secondary';remove.textContent='删除';remove.setAttribute('aria-label',`删除截图 ${index+1}`);remove.onclick=()=>{if(!confirm(`确定删除第 ${index+1} 张截图？取消将保留该截图。`))return;screenshots.splice(index,1);renderScreenshots();resetReview()};figure.append(preview,remove);list.append(figure)});
 window.ReportReview?.refreshEvidence();
 $('pc-screenshot-hint').textContent=screenshots.length?`已粘贴 ${screenshots.length} 张截图，可继续粘贴或删除。`:'截图后直接在这里或缺陷描述框按 Ctrl+V / ⌘V。';
}
function readScreenshot(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',',2)[1]||'');reader.onerror=()=>reject(Error('读取剪贴板截图失败'));reader.readAsDataURL(file)})}
async function pasteScreenshot(event){
 if(batchEntries||sending)return;
 const files=Array.from(event.clipboardData?.items||[]).filter(item=>item.kind==='file'&&item.type.startsWith('image/')).map(item=>item.getAsFile()).filter(Boolean);
 if(!files.length)return;
 event.preventDefault();
 try{
  for(const file of files){
   if(screenshots.length>=maxScreenshots)throw Error(`每条缺陷最多粘贴 ${maxScreenshots} 张截图`);
   if(!allowedScreenshotTypes.has(file.type))throw Error('截图仅支持 PNG、JPEG 或 WebP 图片');
   if(file.size>maxScreenshotBytes)throw Error('单张截图不能超过 5 MB');
   const content_base64=await readScreenshot(file);screenshots.push({content_type:file.type,content_base64,preview:`data:${file.type};base64,${content_base64}`});
  }
  renderScreenshots();resetReview();message('pc-review-message','截图已加入缺陷描述，提交后将在 PingCode 中显示。');
 }catch(error){showError(error)}
}
let selectionScope=null,lastBatch=null;
function scopeIds(){return Array.from(selections.keys()).filter(id=>!selectionScope||selectionScope.has(id));}
function updateSelection(){
 if(!$('pc-batch-start'))return;
 const available=scopeIds().filter(id=>records.get(id)?.status!=='loading'&&!isBusy(id));
 const selected=Array.from(selections).filter(([,box])=>box.checked).map(([id])=>id);
 for(const [id,box] of selections)box.disabled=sending||isBusy(id)||records.get(id)?.status==='loading';
 const bar=document.querySelector('.pc-batch-toolbar');if(bar)bar.hidden=!selections.size;
 $('pc-batch-count').textContent=`已选 ${selected.length} 条 / 当前筛选 ${available.length} 条`;
 $('pc-batch-start').disabled=sending||!selected.some(id=>!isBusy(id)&&triage.canSubmit(records.get(id)));
 $('pc-select-all').disabled=sending||!available.length;
 $('pc-select-all').checked=!!available.length&&available.every(id=>selections.get(id).checked);
 $('pc-select-all').indeterminate=available.some(id=>selections.get(id).checked)&&!$('pc-select-all').checked;
}
function settleSelection(id,outcome){const box=selections.get(id);if(box)box.checked=triage.keepBatchSelection(outcome);}
function clearSelection(){if(sending)return;for(const box of selections.values())box.checked=false;updateSelection();}
function publishBatch(result){lastBatch=result;updateSelection();window.ReportReview?.batchResult?.(result);window.ReportReview?.update();}
function updateRecord(id,record){records.set(id,record);const button=buttons.get(id),lifecycle=triage.lifecycleStatus(record);if(button)button.textContent=record?.lineage&&record?.item?(lifecycleLabels[lifecycle]||'历史缺陷')+' · '+(record.item.identifier||''):record?.status==='submitted'?(contentWarning(record)?'已创建，内容待核对 · ':'已提交 · ')+(record.item?.identifier||''):['pending','unknown'].includes(record?.status)?'提交待核对':record?.status==='unavailable'?'重新读取状态':lifecycle!=='pending_submission'?lifecycleLabels[lifecycle]:'提交到 PingCode';const box=selections.get(id);if(box){box.disabled=sending||isBusy(id)||record?.status==='loading';}updateSelection();window.ReportReview?.update();}
function ensureDialog(){
 if(dialog)return;
 dialog=document.createElement('dialog');dialog.className='pc-dialog';dialog.setAttribute('aria-labelledby','pc-review-title');
 dialog.innerHTML=`<button class="pc-secondary pc-close" id="pc-close" type="button" aria-label="关闭审核窗口">✕</button><h2 id="pc-review-title">审核并提交缺陷</h2><p class="pc-muted">自动给出分级建议，审核时可修改。严重程度表示影响，优先级表示处理紧迫性。</p><p><a href="/integrations/pingcode" target="_blank" rel="noopener">集成管理 · PingCode ↗</a> <button class="pc-secondary" id="pc-reload">重新读取连接</button></p><section id="pc-lifecycle" class="pc-lifecycle"><div><label>处理状态<select id="pc-lifecycle-status">${Object.entries(lifecycleLabels).map(([value,label])=>`<option value="${value}">${label}</option>`).join('')}</select></label><label id="pc-lifecycle-reason-label">状态说明<textarea id="pc-lifecycle-reason" maxlength="4000" rows="2" placeholder="选填，拒绝和暂缓时必填"></textarea></label><button id="pc-lifecycle-save" class="pc-secondary" type="button">保存状态</button></div><p id="pc-lifecycle-message" class="pc-message" role="status"></p></section><div id="pc-record" class="pc-record" hidden></div><p id="pc-review-message" class="pc-message" role="status"></p><form id="pc-review-form"><fieldset id="pc-edit-fields"><div id="pc-single"><label>缺陷标题<input id="pc-title" maxlength="300" required></label><label>缺陷描述<textarea id="pc-description" required maxlength="150000"></textarea></label><section id="pc-screenshot-zone" class="pc-screenshot-zone" tabindex="0" aria-label="粘贴截图"><strong>粘贴截图</strong><p id="pc-screenshot-hint">截图后直接在这里或缺陷描述框按 Ctrl+V / ⌘V。</p><div id="pc-screenshot-list" class="pc-screenshot-list"></div></section></div><div class="pc-grid"><label>目标项目<select id="pc-project" required></select></label><label>缺陷类型<select id="pc-type" required></select></label><label><span id="pc-priority-label">优先级</span><select id="pc-priority"></select></label><label>负责人（批量时应用到全部）<select id="pc-assignee"></select></label><label><span id="pc-severity-label">严重程度</span><select id="pc-severity"></select></label></div><p id="pc-triage-note" class="pc-muted"></p><div id="pc-fields" class="pc-grid pc-fields"></div><div id="pc-batch-list"></div><div id="pc-review-confirmation" class="pc-review-confirmation"><label class="pc-review-label"><input type="checkbox" id="pc-reviewed" required aria-describedby="pc-review-hint"><span id="pc-review-consent">我已审核缺陷内容、分级和目标项目，确认提交。</span></label><p id="pc-review-hint" class="pc-message" role="alert" hidden></p></div></fieldset><div class="pc-actions"><button id="pc-close-footer" class="pc-secondary" type="button">关闭窗口</button><button id="pc-stop" class="pc-secondary" type="button" hidden>停止后续提交</button><button id="pc-submit" class="pc-primary" type="submit" disabled>确认并推送</button></div></form>`;
 document.body.appendChild(dialog);
 $('pc-close').onclick=$('pc-close-footer').onclick=()=>{if(!sending&&!dialog.dataset.submitting){++opening;++sequence;dialog.close()}};
 dialog.addEventListener('cancel',e=>{if(sending||dialog.dataset.submitting)e.preventDefault();else{++opening;++sequence;}});
 $('pc-stop').onclick=()=>{stopRequested=true;$('pc-stop').disabled=true;message('pc-review-message','当前请求结束后停止，已提交的缺陷会保留。')};
 $('pc-reload').onclick=e=>busy(e.target,loadProjects,'pc-review-message');
 $('pc-lifecycle-status').onchange=syncLifecycleFields;
 $('pc-lifecycle-save').onclick=e=>busy(e.target,saveLifecycle,'pc-lifecycle-message');
 $('pc-project').onchange=()=>loadMeta().catch(showError);
 $('pc-type').onchange=()=>loadMeta($('pc-type').value).catch(showError);
 $('pc-priority').onchange=()=>{if(batchEntries&&$('pc-priority').value)for(const entry of batchEntries)if(triage.canSubmit(entry.record))entry.priority.value=$('pc-priority').value;};
 $('pc-severity').onchange=()=>{if(batchEntries&&$('pc-severity').value)for(const entry of batchEntries)if(triage.canSubmit(entry.record))entry.severity.value=$('pc-severity').value;};
 $('pc-review-form').oninput=e=>{if(e.target.id!=='pc-reviewed'){resetReview();rememberReview()}};
 $('pc-review-form').onchange=e=>{if(e.target.id==='pc-reviewed'){clearReviewHint();updateSubmitState()}else resetReview()};
 // Guide consent before native validation can focus an earlier required field.
 $('pc-submit').onclick=reviewBeforeSubmit;
 $('pc-reviewed').oninvalid=e=>{e.preventDefault();requestReview()};
 $('pc-review-form').onsubmit=submit;
 dialog.addEventListener('paste',pasteScreenshot);
 $('pc-screenshot-zone').onclick=()=>{$('pc-screenshot-zone').focus()};
}
function showError(e){message('pc-review-message',e.message,true)}
function syncLifecycleFields(){
 const status=$('pc-lifecycle-status').value,required=['rejected','deferred'].includes(status),submitted=currentDraft?.record?.status==='submitted';
 $('pc-lifecycle-reason-label').firstChild.textContent=status==='rejected'?'拒绝理由':status==='deferred'?'暂缓原因':'状态说明';
 $('pc-lifecycle-reason').required=required;$('pc-lifecycle-reason').placeholder=required?'必填，后续回归会读取此说明':'选填';
 for(const option of $('pc-lifecycle-status').options)if(option.value==='submitted')option.disabled=!submitted;
}
function renderLifecycle(record){
 if(!$('pc-lifecycle-status'))return;
 $('pc-lifecycle-status').value=triage.lifecycleStatus(record);$('pc-lifecycle-reason').value=record?.triage_reason||'';
 message('pc-lifecycle-message',record?.triage_reason?`已记录：${record.triage_reason}`:'');syncLifecycleFields();
}
async function saveLifecycle(){
 const status=$('pc-lifecycle-status').value,reason=$('pc-lifecycle-reason').value.trim();
 if(['rejected','deferred'].includes(status)&&!reason)throw Error('请填写拒绝或暂缓原因');
 const result=await call(route+'/lifecycle','PATCH',{status,reason,expected_updated_at:currentDraft.record?.updated_at||''});currentDraft.record=result;renderRecord(result);
 message('pc-lifecycle-message','状态已保存，后续回归会读取该记录。');
 if(triage.canSubmit(result)&&!meta)await loadProjects();
}
function titleAttributes(input, enabled){
 input.prefixControls?.remove();
 if(!enabled)return;
 const envs=['dev','test','pre','prod','uat','staging','qa','local'];
 const split=()=>input.value.match(/^【([^】]*)】\s*【([^】]*)】\s*【([^】]*)】\s*(.*)$/s)||input.value.match(/^\[([^\]]*)\]\s*【([^】]*)】\s*【([^】]*)】\s*(.*)$/s);
 const initial=split();
 const box=document.createElement('div');box.className='pc-grid pc-title-attributes';
 const fields=[];
 for(const [i,label,options] of [[1,'环境',envs],[2,'业务端',['B端','C端']],[3,'功能/模块',null]]){
  const holder=document.createElement('label');holder.textContent=label;
  const field=document.createElement(options?'select':'input');field.setAttribute('aria-label',label);
  if(options){for(const value of ['',...options]){const option=document.createElement('option');option.value=value;option.textContent=value||'待补充';field.append(option)}}
  else field.maxLength=60;
  field.value=options?(options.includes(initial?.[i])?initial[i]:''):(initial?.[i]?.startsWith('待补充')?'':initial?.[i]||'');
  holder.append(field);box.append(holder);fields.push(field);
 }
 const sync=()=>{const parts=split();input.value=`【${fields[0].value||'待补充环境'}】【${fields[1].value||'待补充端'}】【${fields[2].value.trim()||'待补充模块'}】 ${parts?parts[4]:input.value}`;input.dispatchEvent(new Event('input',{bubbles:true}));};
 for(const field of fields)field.addEventListener('change',sync);
 input.parentElement.after(box);input.prefixControls=box;
}
function renderRecord(record){renderLifecycle(record);$('pc-record').hidden=!record;if(!record){updateRecord(currentButton.dataset.draft,null);return;}const status={draft:'尚未提交到 PingCode',submitted:'已提交到 PingCode',failed:'提交未成功，可以修改后重新审核',pending:'上次提交结果待核对',unknown:'上次提交结果待核对'}[record.status]||record.status;$('pc-record').replaceChildren(document.createTextNode(status+(record.item?' · '+record.item.identifier:'')+(record.error?'\n'+record.error:'')+(contentWarning(record)?'\n缺陷已创建，但'+contentWarning(record):'')));updateRecord(currentButton.dataset.draft,record);
 if(record.remote_sync?.status&&record.remote_sync.status!=='success'){
  const note=document.createElement('p');note.textContent=record.remote_sync.error||'同步结果待核对';$('pc-record').append(note);
  const refresh=document.createElement('button');refresh.type='button';refresh.textContent='核对同步结果';refresh.onclick=()=>runBatch([currentButton.dataset.draft],'refresh');$('pc-record').append(refresh);
 }
 const locked=!triage.canSubmit(record);
 if(record.item?.url){const a=document.createElement('a');a.href=record.item.url;a.target='_blank';a.rel='noopener';a.textContent='在 PingCode 查看 ↗';$('pc-record').append(document.createElement('br'),a)}
 if(record.status==='submitted'&&record.item&&contentWarning(record)){
  const retry=document.createElement('button');retry.type='button';retry.className='pc-secondary';retry.textContent='重试正文与截图';
  retry.onclick=()=>busy(retry,async()=>{const updated=await call(route+'/retry-content','POST',{});currentDraft.record=updated;renderRecord(updated);message('pc-review-message',contentWarning(updated)||'正文与截图已补交并通过回读核验。',!!contentWarning(updated))},'pc-review-message');
  $('pc-record').append(document.createElement('br'),retry);
 }
 if(record.status==='submitted'&&record.item&&(record.triage_status==='regression_passed'||(record.lineage&&record.triage_status==='regression_failed'))){
  const accepted=record.triage_status==='regression_passed',action=accepted?'accept':'reopen';
  const synced=!!record.remote_state&&(record.remote_state_action===action||(!record.remote_state_action&&!accepted));
  const button=document.createElement('button');button.type='button';button.className='pc-secondary';
  button.textContent=accepted?(synced?'已验收 · 已同步':'验收并同步 PingCode'):(synced?'原缺陷已重新打开':'重新打开原缺陷');button.disabled=synced;
  button.disabled=synced||['pending','unknown'].includes(record.remote_sync?.status);button.onclick=()=>busy(button,async()=>{const result=await runBatch([currentButton.dataset.draft],action);message('pc-review-message',result.items[0]?.message||'已处理')},'pc-review-message');
  $('pc-record').append(document.createElement('br'),button);
 }
 if(locked){const payload=record.payload||(currentDraft?{title:currentDraft.title,description:currentDraft.description}:null);if(payload){const detail=document.createElement('section');detail.className='pc-record-detail';const heading=document.createElement('h3');heading.textContent=record.payload?'缺陷详情':'报告中的缺陷草稿';const title=document.createElement('p');title.className='pc-record-title';const reportTitle=edits.get(currentButton?.dataset.draft)?.title||(currentDraft?.title_corrected?currentDraft.title:'')||payload.title;title.textContent=window.ReportReview?.displayTitle?.(reportTitle)||reportTitle||'未填写标题';const description=document.createElement('pre');description.textContent=payload.description||'未填写描述';detail.append(heading,title,description);$('pc-record').append(detail);}}
 // The report review panel already shows these images as evidence previews below the record.
 if(record.screenshots?.length&&document.body.id!=='report-review-page'){const list=document.createElement('div');list.className='pc-screenshot-list';for(const shot of record.screenshots){if(!/^https?:\/\//i.test(shot.url||''))continue;const link=document.createElement('a');link.href=shot.url;link.target='_blank';link.rel='noopener';link.textContent=shot.title||'查看已提交截图';list.append(link)}$('pc-record').append(list);}
 $('pc-review-form').hidden=locked;window.ReportReview?.refreshEvidence();
 if(['pending','unknown'].includes(record.status)){const p=document.createElement('p');p.textContent='请按缺陷标题核查 PingCode，再关联已有缺陷。';$('pc-record').append(p);
 const input=document.createElement('input');input.placeholder='已创建的工作项 ID（非显示编号）';input.setAttribute('aria-label','已创建的工作项 ID');$('pc-record').append(input);const resolve=document.createElement('button');resolve.className='pc-secondary';resolve.textContent='核对并关联已有缺陷';resolve.onclick=()=>busy(resolve,async()=>{const r=await call(route+'/resolve','POST',{item_id:input.value});renderRecord(r)},'pc-review-message');const absent=document.createElement('button');absent.className='pc-secondary';absent.textContent='已人工核对未创建';absent.onclick=()=>busy(absent,async()=>{if(!confirm('确认已在 PingCode 核查，未创建此缺陷？之后重新提交会创建新工作项。'))return;renderRecord(await call(route+'/resolve','POST',{confirmed_absent:true}));await loadProjects()},'pc-review-message');$('pc-record').append(resolve,absent);}}
async function loadProjects(){
 const opened=opening;meta=null;resetReview();config=await call(endpoint);
 if(opened!==opening)return;
 if(!config.configured)throw Error('尚未配置 PingCode。请打开上方“集成管理”，保存授权后点击“重新读取连接”。');
 const p=await call(endpoint+'/projects');if(opened!==opening)return;
 options($('pc-project'),p.values,config.default_project_id);message('pc-review-message','请选择目标项目，分级将自动匹配该项目的选项。');
 if($('pc-project').value)await loadMeta();
}
function setTriageFields(priority,severity,assessment){
 options(priority,meta.priorities,triage.matchOption(meta.priorities,assessment.priority),'请选择优先级');priority.required=meta.priorities.length>0;
 options(severity,triage.severityOptions(meta),triage.severityDefault(meta,assessment.severity),'请选择严重程度');severity.required=true;
}
function renderBatch(){
 const list=$('pc-batch-list');list.innerHTML='';
 for(const entry of batchEntries){
  const card=document.createElement('section');card.className='pc-batch-entry';
  const number=document.createElement('h3');number.textContent=`缺陷 ${entry.index+1}`;card.append(number);
  const titleLabel=document.createElement('label');titleLabel.textContent='缺陷标题';const title=document.createElement('input');title.value=entry.titleValue;title.required=true;title.maxLength=300;titleLabel.append(title);card.append(titleLabel);entry.title=title;
  const grid=document.createElement('div');grid.className='pc-grid';
  for(const [key,label]of [['priority','优先级'],['severity','严重程度']]){const holder=document.createElement('label');holder.textContent=label;const select=document.createElement('select');select.setAttribute('aria-label',`缺陷 ${entry.index+1} ${label}`);holder.append(select);grid.append(holder);entry[key]=select;}card.append(grid);
  setTriageFields(entry.priority,entry.severity,entry.assessment);
  const reason=document.createElement('p');reason.className='pc-muted';reason.textContent='自动判断：'+entry.assessment.reason;card.append(reason);
  const details=document.createElement('details');details.open=true;const summary=document.createElement('summary');summary.textContent='审核复现步骤与证据';const description=document.createElement('textarea');description.value=entry.descriptionValue;description.required=true;description.maxLength=150000;description.setAttribute('aria-label',`缺陷 ${entry.index+1} 描述`);details.append(summary,description);card.append(details);entry.description=description;
  const status=document.createElement('p');status.className='pc-message';status.setAttribute('role','status');entry.status=status;card.append(status);list.append(card);entry.card=card;
  const keep=()=>{entry.titleValue=title.value;entry.descriptionValue=description.value;edits.set(entry.id,{title:title.value,description:description.value,screenshots:entry.screenshots||[]});window.ReportReview?.update()};title.oninput=keep;description.oninput=keep;
  titleAttributes(title,entry.ui_title);
  if(!triage.canSubmit(entry.record))setEntryResult(entry,entry.record);else status.textContent='待审核';
 }
}
async function loadMeta(type=''){
 const n=++sequence,opened=opening;meta=null;resetReview();$('pc-fields').innerHTML='';const pid=$('pc-project').value;
 options($('pc-type'),[]);options($('pc-priority'),[]);options($('pc-assignee'),[]);options($('pc-severity'),[]);
 if(!pid)return;
 message('pc-review-message','正在读取项目字段…');
 const m=await call(endpoint+'/metadata?project_id='+encodeURIComponent(pid)+'&type_id='+encodeURIComponent(type));if(n!==sequence||opened!==opening)return;
 meta=m;options($('pc-type'),m.types,m.type_id);options($('pc-assignee'),m.members.map(x=>({...x,name:x.display_name||x.name})),'','暂不指派');
 const severityProp=triage.severityProperty(m);
 if(batchEntries){options($('pc-priority'),m.priorities,'','保留每条分级');options($('pc-severity'),triage.severityOptions(m),'','保留每条分级');$('pc-priority').required=false;$('pc-severity').required=false;renderBatch();}
 else setTriageFields($('pc-priority'),$('pc-severity'),currentDraft.assessment);
 $('pc-triage-note').textContent=(batchEntries?'每条缺陷单独创建一张 PingCode 单，不会合并；下方可分别修改内容和分级。':'自动判断：'+currentDraft.assessment.reason)+(severityProp?' 严重程度将写入项目字段「'+severityProp.name+'」。':' 项目未提供可匹配的严重程度选项，将把级别写入缺陷描述。')+' 无法唯一匹配的选项请手动选择。';
 const builtins=new Set(['id','identifier','title','description','project_id','type_id','state','state_id','assignee','assignee_id','priority','priority_id','created_at','created_by','updated_at','updated_by']);
 for(const p of m.properties){
  if(builtins.has(p.id)||p.id===severityProp?.id||p.readonly||p.read_only||p.is_readonly)continue;
  const label=document.createElement('label');label.textContent=p.name+(p.required||p.is_required?' *':'');let field;const opts=Array.isArray(p.options)?p.options:[];
  if(opts.length){field=document.createElement('select');field.multiple=['multi_select','multiple_select','multiselect'].includes(p.type);options(field,opts.map(o=>({id:o._id||o.id,name:o.text||o.name})));}
  else if(['text','string','number','integer','float'].includes(p.type)){field=document.createElement('input');if(['number','integer','float'].includes(p.type)){field.type='number';field.step=p.type==='integer'?'1':'any';}}
  else{field=document.createElement('textarea');field.className='pc-json';field.placeholder='填写 JSON 值；不需要时留空';field.dataset.json='true';}
  field.dataset.property=p.id;field.required=Boolean(p.required||p.is_required);label.append(field);$('pc-fields').append(label);
 }
 message('pc-review-message','已自动填写分级建议，请审核内容后勾选确认。');updateSubmitState();
}
function commonProperties(){const properties={};for(const el of $('pc-fields').querySelectorAll('[data-property]')){if(!el.value)continue;let value=el.multiple?Array.from(el.selectedOptions,o=>o.value):el.type==='number'?Number(el.value):el.value;if(el.dataset.json){try{value=JSON.parse(el.value)}catch{throw Error('字段 '+el.closest('label').firstChild.textContent+' 需要合法 JSON 值')}}properties[el.dataset.property]=value;}return properties;}
function makePayload(title,description,priority,severity,properties){
 const props={...properties},severityProp=triage.severityProperty(meta);
 if(!severity.value||meta.priorities.length&&!priority.value)throw Error('请补充未匹配的优先级与严重程度');
 if(severityProp)props[severityProp.id]=severity.value;
 const payload={project_id:$('pc-project').value,type_id:$('pc-type').value,title,description,properties:props};
 if(priority.value)payload.priority_id=priority.value;
 if($('pc-assignee').value)payload.assignee_id=$('pc-assignee').value;
 return payload;
}
function setEntryResult(entry,result){
 entry.record=result;settleSelection(entry.id,triage.batchOutcome(result,'__submit__'));updateRecord(entry.id,result);
 const labels={submitted:'已提交',failed:'失败，可修改后重新审核',unknown:'结果待核对，请用单条入口核对',pending:'正在提交或待核对'};
 entry.status.textContent=(labels[result.status]||result.status)+(result.item?' · '+result.item.identifier:'')+(result.error?'：'+result.error:'')+(contentWarning(result)?'：'+contentWarning(result):'');entry.status.classList.toggle('pc-error',result.status!=='submitted'||!!contentWarning(result));
 const locked=!triage.canSubmit(result);for(const el of entry.card.querySelectorAll('input,select,textarea'))el.disabled=locked;
 if(result.item?.url){const a=document.createElement('a');a.href=result.item.url;a.target='_blank';a.rel='noopener';a.textContent='打开缺陷 ↗';entry.status.append(' ',a);}
}
async function submit(e){
 e.preventDefault();if(!meta||sending)return;
 if(!$('pc-reviewed').checked){requestReview();return;}
 let queue;
 try{const properties=commonProperties();queue=batchEntries?batchEntries.filter(entry=>triage.canSubmit(entry.record)).map(entry=>({entry,route:draftRoute(entry.id),payload:makePayload(entry.title.value,entry.description.value,entry.priority,entry.severity,properties),screenshots:(entry.screenshots||[]).map(({content_type,content_base64})=>({content_type,content_base64}))})):[{route,payload:makePayload($('pc-title').value,$('pc-description').value,$('pc-priority'),$('pc-severity'),properties),screenshots:screenshots.map(({content_type,content_base64})=>({content_type,content_base64}))}];}catch(err){showError(err);resetReview();return;}
 if(!queue.length)return;
 if(batchEntries){
  const save=$('pc-submit');save.disabled=true;$('pc-edit-fields').disabled=true;dialog.dataset.submitting='true';$('pc-close').disabled=$('pc-close-footer').disabled=true;
  try{
   message('pc-review-message','正在保存后台任务…');
   const inputs=new Map();for(const item of queue)inputs.set(item.entry.id,{reviewed:true,payload:item.payload,screenshots:item.screenshots||[]});
   await enqueueBatch(queue.map(item=>item.entry.id),'__submit__','',null,inputs);
   for(const item of batchExcluded)settleSelection(item.id,'skipped');
   dialog.close();
  }catch(error){showError(error)}finally{delete dialog.dataset.submitting;$('pc-edit-fields').disabled=false;$('pc-close').disabled=$('pc-close-footer').disabled=false;resetReview();}
  return;
 }
 sending=true;stopRequested=false;$('pc-edit-fields').disabled=true;$('pc-close').disabled=$('pc-close-footer').disabled=true;$('pc-reload').disabled=true;$('pc-submit').disabled=true;$('pc-stop').hidden=!batchEntries;$('pc-stop').disabled=false;
 let completed=0;const results=batchEntries?batchExcluded.map(item=>({...item})):[];updateSelection();window.ReportReview?.update();
 message('pc-review-message',`正在提交 0 / ${queue.length}，请等待结果…`);
 try{
  await triage.sendQueue(queue,async item=>{
   // A local HTTP rejection is definitive. A lost response stays uncertain until refreshed.
   try{return await call(item.route,'POST',{reviewed:true,payload:item.payload,screenshots:item.screenshots||[]})}catch(error){
    try{const latest=await call(item.route);if(latest.record)return latest.record;if(error.httpStatus)return {status:'failed',error:error.message};}catch{}
    return {status:'unknown',error:error.message};
   }
  },(item,result)=>{completed++;results.push({id:item.entry?.id||currentButton.dataset.draft,outcome:triage.batchOutcome(result,'__submit__'),message:result.error||contentWarning(result)||'已提交'});if(item.entry)setEntryResult(item.entry,result);else{updateRecord(currentButton.dataset.draft,result);renderRecord(result);}message('pc-review-message',`已处理 ${completed} / ${queue.length}`);},()=>stopRequested);
  if(batchEntries){const success=batchEntries.filter(x=>x.record?.status==='submitted'&&!contentWarning(x.record)).length,failed=batchEntries.filter(x=>x.record?.status==='failed').length,unknown=batchEntries.filter(x=>['pending','unknown'].includes(x.record?.status)||contentWarning(x.record)).length,remaining=batchEntries.filter(x=>!x.record).length;message('pc-review-message',`本批次：成功 ${success} 条，失败 ${failed} 条，待核对 ${unknown} 条，未提交 ${remaining} 条。失败项修改后可重新审核；已创建项不会重复提交。`,!!failed||!!unknown);}
  else {const record=records.get(currentButton.dataset.draft);message('pc-review-message',contentWarning(record)|| (record?.status==='submitted'?'提交成功。':'请核对上方提交状态。'),!!contentWarning(record));}
 }finally{sending=false;for(const item of queue.slice(completed))results.push({id:item.entry?.id||currentButton.dataset.draft,outcome:'remaining',message:'尚未提交'});for(const item of results)settleSelection(item.id,item.outcome);publishBatch({action:'__submit__',items:results});$('pc-edit-fields').disabled=false;$('pc-close').disabled=$('pc-close-footer').disabled=false;$('pc-reload').disabled=false;$('pc-stop').hidden=true;resetReview();}
}
async function openReview(button,id){
 if(sending)return;
 rememberReview();
 ensureDialog();const opened=++opening;++sequence;currentButton=button;route=draftRoute(id);batchEntries=null;currentDraft=null;
 resetDialog(false);presentReview(false);message('pc-review-message','正在读取缺陷…');
 try{if(draftReport(id)==='total')throw Error('该结果没有对应的来源阶段缺陷草稿，无法保存缺陷处理状态；可在全部用例中查看或修正结果。');const d=await call(route);if(opened!==opening)return;currentDraft=d;const edit=edits.get(id);$('pc-title').value=edit?.title??d.title;$('pc-description').value=triage.withReportReference(edit?.description??triage.reviewDescription($(id),d),d);titleAttributes($('pc-title'),d.ui_title);screenshots=(edit?.screenshots??d.screenshots??[]).slice();renderScreenshots();$('pc-description').dataset.marker=d.marker;updateRecord(id,d.record);renderRecord(d.record);syncEditorBusy();window.ReportReview?.editorReady();if(triage.canSubmit(d.record))await loadProjects();else message('pc-review-message','提交记录已读取。');}catch(e){if(opened===opening)showError(e)}
}
function resetDialog(batch){
 $('rr-fields')?.remove();
 if($('rr-draft-save'))$('rr-draft-save').hidden=batch;
 if($('pc-description'))$('pc-description').parentElement.hidden=false;
 screenshots=[];
 $('pc-review-form').reset();$('pc-review-form').hidden=false;$('pc-lifecycle').hidden=batch;$('pc-edit-fields').disabled=false;$('pc-record').hidden=true;$('pc-fields').innerHTML='';$('pc-batch-list').innerHTML='';$('pc-triage-note').textContent='';meta=null;resetReview();options($('pc-project'),[]);
 $('pc-single').hidden=batch;$('pc-title').disabled=batch;$('pc-description').disabled=batch;
 renderScreenshots();
 $('pc-review-title').textContent=batch?'批量审核并提交缺陷':'审核并提交缺陷';$('pc-submit').textContent=batch?'确认并批量推送':'确认并推送';$('pc-review-consent').textContent=batch?'我已审核下方所有待提交缺陷的内容、分级和目标项目，确认批量提交。':'我已审核缺陷内容、分级和目标项目，确认提交。';$('pc-priority-label').textContent=batch?'统一设置优先级（可选）':'优先级';$('pc-severity-label').textContent=batch?'统一设置严重程度（可选）':'严重程度';
}
async function openBatch(){
 if(sending)return;
 rememberReview();
 const ids=Array.from(selections).filter(([,box])=>box.checked&&!box.disabled).map(([id])=>id);if(!ids.length)return;
 ensureDialog();const opened=++opening;++sequence;batchEntries=[];batchExcluded=[];resetDialog(true);presentReview(true);message('pc-review-message','正在读取选中的缺陷…');
 try{for(const id of ids){const d=await call(draftRoute(id));if(opened!==opening)return;updateRecord(id,d.record);if(!triage.canSubmit(d.record)){batchExcluded.push({id,outcome:'skipped',message:'已提交或当前状态不可提交'});continue;}const edit=edits.get(id);batchEntries.push({...d,id,index:batchEntries.length,titleValue:edit?.title??d.title,descriptionValue:triage.withReportReference(edit?.description??triage.reviewDescription($(id),d),d),screenshots:edit?.screenshots??d.screenshots??[]});}
 if(!batchEntries.length){message('pc-review-message','所选缺陷已提交或待核对，请回到单条入口查看。');return;}
 $('pc-review-title').textContent=`批量审核 ${batchEntries.length} 条缺陷`;await loadProjects();if(batchExcluded.length)message('pc-review-message',`已选 ${ids.length} 条，将提交 ${batchEntries.length} 条；排除 ${batchExcluded.length} 条已提交或不可提交的记录。`);
 }catch(e){showError(e)}
}
if($('pc-config-form'))configPage().catch(e=>message('pc-config-message',e.message,true));
if(reportPath&&publicReport){
 const loginRequired=publicReport==='login-required';
 const returnTo=location.pathname+(location.search||'')+(location.hash||'');
 const login=()=>{location.href='/login?next='+encodeURIComponent(returnTo)};
 const copies=Array.from(document.querySelectorAll('.copy-defect'));
 for(const copy of copies){
  const button=document.createElement('button');button.type='button';button.className='pc-push';
  button.textContent=loginRequired?'登录后提交到 PingCode':'此报告仅供查看';
  if(loginRequired)button.onclick=login;else{button.disabled=true;button.title='请进入源阶段报告处理缺陷';}
  copy.after(button);
 }
 if(copies.length){
  const bar=document.createElement('aside');bar.className='pc-batch-toolbar';
  const note=document.createElement('span');note.textContent=loginRequired?'登录后可选择多条缺陷，逐条审核并批量推送。':'当前账号只能查看这份报告。';
  const action=document.createElement('button');action.type='button';action.className='pc-primary';action.textContent=loginRequired?'登录后批量提缺陷':'此报告仅供查看';
  if(loginRequired)action.onclick=login;else action.disabled=true;
  bar.append(note,action);(document.querySelector('main')||document.body).prepend(bar);
 }
}
if(reportPath&&!publicReport){
 document.querySelectorAll('.copy-defect').forEach(copy=>{
  const id=copy.dataset.draft,b=document.createElement('button');b.type='button';b.className='pc-push';b.textContent='提交到 PingCode';b.onclick=()=>openReview(b,id);copy.after(b);b.dataset.draft=id;buttons.set(id,b);
  records.set(id,{status:'loading'});
  const label=document.createElement('label');label.className='pc-select-label';const box=document.createElement('input');box.type='checkbox';box.disabled=true;box.setAttribute('aria-label','选择缺陷 '+(buttons.size));box.onchange=()=>{updateSelection();window.ReportReview?.update()};label.append(box,'选择');copy.before(label);selections.set(id,box);
 });
 if(buttons.size){const bar=document.createElement('aside');bar.className='pc-batch-toolbar';bar.innerHTML='<label><input id="pc-select-all" type="checkbox"> 全选当前筛选结果</label><span id="pc-batch-count"></span><button id="pc-batch-start" class="pc-primary" disabled>批量提交</button>';const overview=document.querySelector('.report-overview');if(overview)overview.after(bar);else (document.querySelector('main')||document.body).prepend(bar);$('pc-select-all').onchange=e=>{for(const id of scopeIds()){const box=selections.get(id);if(!box.disabled)box.checked=e.target.checked};updateSelection();window.ReportReview?.update()};$('pc-batch-start').onclick=openBatch;updateSelection();}
 refreshRecords().then(pollBatchJobs);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)pollBatchJobs()});
 window.addEventListener('focus',pollBatchJobs);
}
async function refreshRecords(){
 if(sending)return;
 const groups=new Map();
 for(const id of buttons.keys()){
  if(draftReport(id)==='total'){updateRecord(id,{status:'unavailable'});continue;}
  const source=`/api/projects/${draftProject(id)}/reports/${draftReport(id)}/pingcode`;
  if(!groups.has(source))groups.set(source,[]);groups.get(source).push(id);
 }
 for(const [source,ids] of groups){
  for(const id of ids)updateRecord(id,{status:'loading'});
  try{const data=await call(source);
   for(const id of ids)updateRecord(id,data.values.find(record=>draftSourceId(id)===record.draft_id)||null);
  }catch{for(const id of ids)updateRecord(id,{status:'unavailable'});}
 }
}
async function editTitles(ids,values){
 if(!ids.length)throw Error('请先勾选要修改的缺陷');
 if(!Object.values(values).some(v=>v.trim()))throw Error('请至少选择或填写一个属性');
 if(/[\[\]【】\r\n]/.test(values.module||''))throw Error('功能/模块不能包含括号或换行');
 const inputs=new Map();
 for(const id of ids){const draft=await call(draftRoute(id));if(!draft.ui_title)throw Error('所选缺陷不是 UI 测试缺陷');inputs.set(id,{attributes:values,revision:draft.correction_revision});}
 await enqueueBatch(ids,'titles','',null,inputs);return ids.length;
}
async function setLifecycles(ids,status,reason=''){return runBatch(ids,status,reason);}
function eligibility(id,action){return isBusy(id)?{kind:'skip',reason:'后台处理中，完成后可继续操作'}:triage.batchEligibility(records.get(id),action);}
function batchPlan(ids,action){return ids.map(id=>({id,record:records.get(id),...eligibility(id,action)}));}
const batchBase=()=>`/api/projects/${reportPath[1]}/reports/${reportPath[2]}/pingcode/batches`;
const jobBase=job=>`/api/projects/${job.project_id}/reports/${job.run_id}/pingcode/batches/jobs/${job.id}`;
function matchingDraft(item){return Array.from(buttons.keys()).find(id=>draftProject(id)===item.project_id&&draftReport(id)===item.run_id&&draftSourceId(id)===item.draft_id);}
function jobView(job){return {...job,items:job.items.map(item=>({...item,id:matchingDraft(item)||'',label:item.draft_id})),active:['queued','running'].includes(job.status)};}
function syncEditorBusy(){
 if(!dialog||batchEntries||!currentButton)return;
 const busy=isBusy(currentButton.dataset.draft);
 let hint=$('pc-background-hint');if(!hint){hint=document.createElement('p');hint.id='pc-background-hint';hint.setAttribute('role','status');$('pc-record').before(hint)}
 hint.hidden=!busy;hint.textContent='此缺陷正在后台处理，可以查看详情；完成后可继续修改。';
 $('pc-edit-fields').disabled=busy||sending;$('pc-lifecycle-save').disabled=busy||sending;
 for(const button of $('pc-record').querySelectorAll('button')){if(busy){if(button.dataset.batchDisabled===undefined)button.dataset.batchDisabled=String(button.disabled);button.disabled=true}else if(button.dataset.batchDisabled!==undefined){button.disabled=button.dataset.batchDisabled==='true';delete button.dataset.batchDisabled;}}
 updateSubmitState();
}
function acceptJobUpdates(values){
 busyDrafts.clear();
 for(const job of values){const previous=backgroundJobs.get(job.id);if(!previous||job.updated_at>=previous.updated_at)backgroundJobs.set(job.id,job);}
 const jobs=Array.from(backgroundJobs.values()).sort((a,b)=>b.created_at.localeCompare(a.created_at));
 for(const job of jobs)if(['queued','running'].includes(job.status))for(const item of job.items)if(['queued','running'].includes(item.outcome)){const id=matchingDraft(item);if(id)busyDrafts.add(id)}
 const newest=new Set();let currentChanged=false;
 for(const job of jobs){
  const active=['queued','running'].includes(job.status);
  for(const item of job.items){
   const id=matchingDraft(item);if(!id||newest.has(id))continue;newest.add(id);
   const signature=job.id+':'+item.outcome+':'+(item.finished_at||'');if(appliedBatchItems.get(id)===signature)continue;
   appliedBatchItems.set(id,signature);
   if(['queued','running'].includes(item.outcome))continue;
   const local=records.get(id),fresh=!local?.updated_at||!item.record?.updated_at||item.record.updated_at>=local.updated_at;
   if(fresh&&item.record)records.set(id,item.record);
   if(fresh)settleSelection(id,item.outcome);
   const source=`/api/projects/${item.project_id}/reports/${item.run_id}`,review=window.ReportReview;
   const loadedRevision=review?.data?.correctionBase===source+'/case-corrections'?review.data.correctionRevision:review?.cases?.find(c=>c.source_report?.project_id===item.project_id&&c.source_report?.id===item.run_id)?.source_report?.correction_revision||0;
   if(item.title&&fresh&&item.correction_revision>=loadedRevision){if(id===currentButton?.dataset.draft&&!batchEntries&&$('pc-title')){$('pc-title').value=item.title;resetReview()}const prior=edits.get(id)||{};edits.set(id,{...prior,title:item.title});const field=$(id);if(field)field.value=field.value.replace(/^【标题】[^\n]*/,()=> '【标题】'+item.title);window.ReportReview?.titlesSaved(`/api/projects/${item.project_id}/reports/${item.run_id}`,{revision:item.correction_revision});}
   if(id===currentButton?.dataset.draft&&fresh)currentChanged=true;
  }
 }
 if(currentChanged&&currentDraft&&!batchEntries){currentDraft.record=records.get(currentButton.dataset.draft);renderRecord(currentDraft.record);}
 updateSelection();syncEditorBusy();window.ReportReview?.update();
 window.ReportReview?.backgroundJobs?.(jobs.map(jobView));
}
async function pollBatchJobs(){
 if(batchPolling||!reportPath||publicReport)return;
 batchPolling=true;clearTimeout(batchPollTimer);
 try{const data=await call(batchBase()+'/jobs');acceptJobUpdates(data.values);window.ReportReview?.batchConnection?.(true)}
 catch{window.ReportReview?.batchConnection?.(false)}
 finally{batchPolling=false;batchPollTimer=setTimeout(pollBatchJobs,document.hidden?10000:backgroundJobs.size&&Array.from(backgroundJobs.values()).some(job=>['queued','running'].includes(job.status))?2000:10000)}
}
async function enqueueBatch(ids,action,reason='',versions=null,inputs=new Map()){
 const snapshot=[...new Set(ids)];
 if(snapshot.some(isBusy))throw Error('所选缺陷正在后台处理中，请选择其他记录');
 if(['rejected','deferred','regression_passed','regression_failed'].includes(action)&&!reason.trim())throw Error('请填写操作原因或更正依据');
 const requestId=newJobId(),items=[];
 // Save large reviewed content one item at a time using the original per-item request limits.
 for(const id of snapshot){
  const item={project_id:draftProject(id),run_id:draftReport(id),draft_id:draftSourceId(id),expected_updated_at:versions?versions[id]:records.get(id)?.updated_at||''};
  if(inputs.has(id)){item.input_id=newJobId();await call(batchBase()+'/inputs/'+item.input_id,'POST',inputs.get(id));}
  items.push(item);
 }
 const observations=['accept','reopen'].includes(action)?Array.from(buttons.keys(),id=>({project_id:draftProject(id),run_id:draftReport(id),draft_id:draftSourceId(id)})):[];
 const body={id:requestId,action,reason,items,observations};let job;
 try{job=await call(batchBase()+'/jobs','POST',body)}
 catch(error){try{job=await call(batchBase()+'/jobs/'+requestId)}catch{pollBatchJobs();throw Error(error.message+'；可刷新页面恢复已创建的任务，请勿重复点击。')}}
 acceptJobUpdates([job]);pollBatchJobs();return jobView(job);
}
async function runBatch(ids,action,reason='',progress=()=>{},versions=null){return enqueueBatch(ids,action,reason,versions);}
async function stopBackgroundJob(id){const job=backgroundJobs.get(id);if(!job)return;const value=await call(jobBase(job)+'/stop','POST',{});acceptJobUpdates([value]);}
window.PingCodeReview={isBusy,eligibility,stopBackgroundJob,backgroundJobs:()=>Array.from(backgroundJobs.values()).map(jobView),pollBatchJobs,syncEditorBusy,runBatch,batchPlan,clearSelection,setSelectionScope:ids=>{selectionScope=new Set(ids);updateSelection()},stopBatch:()=>{stopRequested=true},lastBatch:()=>lastBatch,buttons,selections,records,edits,editTitles,open:id=>openReview(buttons.get(id),id),refresh:refreshRecords,
 screenshotAssets:()=>dialog?.open&&!$('pc-review-form').hidden&&!$('pc-single').hidden?screenshots.map(shot=>shot.asset_id).filter(Boolean):[],
 content:()=>records.get(currentButton?.dataset.draft)?.payload?.description||currentDraft?.record?.payload?.description||$('pc-description')?.value||'',
 isSending:()=>sending,save:()=>{if(isBusy(currentButton?.dataset.draft))return;rememberReview();message('pc-review-message','草稿已暂存在当前页面，切换缺陷后仍可继续编辑；刷新页面后不保留。')},
 setLifecycles,selectionChanged:()=>{updateSelection();window.ReportReview?.update()},current:()=>currentButton?.dataset.draft};
})();
