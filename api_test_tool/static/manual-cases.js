/* Plain form for user cases; advanced chain editing remains available separately. */
let manualCaseRevision=null,caseRemoval=null;
function manualValue(value,type){
 if(type==='null')return null;
 if(type==='number'){if(!String(value).trim()||!Number.isFinite(Number(value)))throw Error('数值字段请填写有效数字。');return Number(value);}
 if(type==='boolean'){if(!['true','false'].includes(value))throw Error('布尔值请填写 true 或 false。');return value==='true';}
 if(type==='json'){try{return JSON.parse(value);}catch{throw Error('对象或数组字段不是有效 JSON。');}}
 return value;
}
function manualMap(rows,typed=false){
 const result=Object.create(null);
 for(const row of rows){const key=row.key.trim();if(!key&&!row.value)continue;if(!key)throw Error('请填写参数名称。');if(Object.hasOwn(result,key))throw Error('参数名称重复：'+key);result[key]=typed?manualValue(row.value,row.type):row.value;}
 return result;
}
function manualCandidate(values,contract){
 const operation=contract.operations[values.operation];if(!operation)throw Error('请先选择要测试的接口。');
 if(!values.title.trim())throw Error('请填写用例名称，例如「密码错误时登录失败」。');
 const request={method:operation.method,path:values.path.trim()||operation.path};
 const params=manualMap(values.params),headers=manualMap(values.headers);
 if(Object.keys(params).length)request.params=params;
 if(values.bodyMode==='json')request.json=manualMap(values.body,true);
 if(values.bodyMode==='form'){request.raw_body=new URLSearchParams(manualMap(values.body)).toString();if(!Object.keys(headers).some(k=>k.toLowerCase()==='content-type'))headers['Content-Type']='application/x-www-form-urlencoded';}
 if(values.bodyMode==='raw')request.raw_body=values.raw;
 if(Object.keys(headers).length)request.headers=headers;
 const assertions=[];
 if(values.status.trim()){
  const status=Number(values.status);if(!Number.isInteger(status)||status<100||status>599)throw Error('预期 HTTP 状态码应为 100～599 的整数。');
  assertions.push({kind:'status',expected:status});
 }
 for(const row of values.expected){
  const name=row.key.trim();if(!name&&!row.value)continue;if(!name)throw Error('请填写要检查的响应字段。');
  const pointer=name.startsWith('/')?name:'/'+name.replace(/~/g,'~0').replace(/\//g,'~1');
  assertions.push(row.type==='exists'?{kind:'json_exists',pointer}:{kind:'json_equal',pointer,expected:manualValue(row.value,row.type)});
 }
 if(!assertions.length)throw Error('请至少填写一个预期：HTTP 状态码或响应字段。');
 const candidate={id:'USER-'+Date.now()+'-'+Math.random().toString(16).slice(2,8),title:values.title.trim(),operation_id:values.operation,scenario:values.auth==='auth_missing'?'auth_missing':'custom',
  steps:[{id:'request',title:values.title.trim(),operation_id:values.operation,request,assertions,extract:[]}],cleanup_steps:[],notes:values.notes.trim()};
 if(values.cleanup==='none'){if(!values.cleanupReason.trim())throw Error('请选择环境清理，或说明为什么不会产生需要清理的数据。');candidate.cleanup_policy={strategy:'none',reason:values.cleanupReason.trim()};}
 return candidate;
}
function manualRow(group,row={}){
 const typed=group==='body'||group==='expected',types=[['string','文本'],['number','数字'],['boolean','布尔值'],['null','空值 null'],['json','对象 / 数组'],...(group==='expected'?[['exists','只检查存在']]:[])];
 return `<div class="manual-row" data-manual-row><input data-field="key" aria-label="${group==='expected'?'响应字段':'参数名称'}" placeholder="${group==='expected'?'如 message 或 /data/id':'参数名称，如 username'}" value="${esc(row.key||'')}"><input data-field="value" aria-label="${group==='expected'?'预期值':'参数值'}" placeholder="${group==='expected'?'应该返回的值':'参数值（允许留空）'}" value="${esc(row.value??'')}">${typed?`<select data-field="type" aria-label="值类型">${types.map(([value,label])=>`<option value="${value}" ${row.type===value?'selected':''}>${label}</option>`).join('')}</select>`:''}<button type="button" data-wf="manual-remove-row" aria-label="移除此参数">×</button></div>`;
}
function manualRows(group){return [...$('manual-'+group).querySelectorAll('[data-manual-row]')].map(row=>({key:row.querySelector('[data-field="key"]').value,value:row.querySelector('[data-field="value"]').value,type:row.querySelector('[data-field="type"]')?.value||'string'}));}
async function openManualCase(){
 await refreshProject();manualCaseRevision=state.bundle_revision;
 $('manual-case-form').reset();
 $('manual-operation').innerHTML='<option value="">请选择要测试的接口</option>'+Object.entries(state.contract.operations).map(([id,op])=>`<option value="${esc(id)}">${esc(op.method+' '+op.path+(op.summary?' · '+op.summary:''))}</option>`).join('');
 $('manual-method').textContent='选择接口后显示请求方法';
 for(const group of ['body','params','headers','expected'])$('manual-'+group).innerHTML=manualRow(group);
 $('manual-error').textContent='';$('manual-body-fields').hidden=true;$('manual-raw-fields').hidden=true;$('manual-cleanup-reason-field').hidden=true;
 $('manual-case-dialog').showModal();
}
function caseReasons(caseItem){
 if(isRuleDemo(caseItem))return '';
 const reasons=[...new Set([caseItem.reason,...(caseItem.web?.blockers||[])].filter(Boolean).flatMap(text=>String(text).split(/[；;]/)).map(text=>text.trim()).filter(Boolean))];
 return reasons.length?`<ul class="case-reasons">${reasons.map(reason=>`<li>${esc(reason)}</li>`).join('')}</ul>`:'';
}
function deletedCasePanel(){const items=state.deleted_cases||[];return items.length?`<details class="deleted-case-list"><summary>已删除用例（${items.length}）</summary>${items.map(item=>`<div class="deleted-case-row"><span>${esc(item.title)}</span><button data-wf="restore-case" data-value="${esc(item.id)}" ${busy()?'disabled':''}>恢复用例</button></div>`).join('')}</details>`:'';}
function applyCaseUpdate(data){Object.assign(state,data);state.selected.clear();state.bootstrap.projects=[state.project,...state.bootstrap.projects.filter(p=>p.id!==state.project.id)];goStage(2);}
async function handleManualCaseClick(button){
 const action=button.dataset.wf;
 if(action==='close-manual'){$('manual-case-dialog').close();return true;}
 if(action==='manual-add-row'){$('manual-'+button.dataset.group).insertAdjacentHTML('beforeend',manualRow(button.dataset.group));return true;}
 if(action==='manual-remove-row'){button.closest('[data-manual-row]').remove();return true;}
 if(action==='save-manual'){
  try{
   const candidate=manualCandidate({operation:$('manual-operation').value,title:$('manual-title').value,path:$('manual-path').value,bodyMode:$('manual-body-mode').value,raw:$('manual-raw').value,
    params:manualRows('params'),headers:manualRows('headers'),body:manualRows('body'),expected:manualRows('expected'),status:$('manual-status').value,notes:$('manual-notes').value,
    auth:$('manual-auth').value,cleanup:$('manual-cleanup').value,cleanupReason:$('manual-cleanup-reason').value},state.contract);
   const data=await api(`/api/projects/${state.project.id}/import-cases`,'POST',{filename:'手动添加用例.json',content:JSON.stringify({cases:[candidate]}),revision:manualCaseRevision});
   $('manual-case-dialog').close();applyCaseUpdate(data);toast('用例已添加，核对预期后可执行。');
  }catch(error){$('manual-error').textContent=error.message;$('manual-error').scrollIntoView?.({block:'nearest'});}return true;
 }
 if(action==='delete-case'){
  await refreshProject();const item=state.bundle?.cases.find(c=>c.id===button.dataset.value);if(!item)throw Error('用例已不存在，请刷新。');
  caseRemoval={case_id:item.id,revision:state.bundle_revision};$('remove-case-title').textContent='删除「'+item.title+'」？';$('remove-case-error').textContent='';$('remove-case-dialog').showModal();return true;
 }
 if(action==='close-remove-case'){$('remove-case-dialog').close();return true;}
 if(action==='confirm-remove-case'){
  try{const data=await api(`/api/projects/${state.project.id}/cases/remove`,'POST',caseRemoval);$('remove-case-dialog').close();applyCaseUpdate(data);toast('已删除，可在「已删除用例」中恢复。');}catch(error){$('remove-case-error').textContent=error.message;}return true;
 }
 if(action==='restore-case'){await refreshProject();const data=await api(`/api/projects/${state.project.id}/cases/restore`,'POST',{id:button.dataset.value,revision:state.bundle_revision});applyCaseUpdate(data);toast('用例已恢复。');return true;}
 return false;
}
document.addEventListener('change',event=>{
 const el=event.target;
 if(el.id==='manual-operation'){const op=state.contract.operations[el.value];$('manual-method').textContent=op?.method||'选择接口后显示请求方法';$('manual-path').value=op?.path||'';}
 if(el.id==='manual-body-mode'){$('manual-body-fields').hidden=!['json','form'].includes(el.value);$('manual-raw-fields').hidden=el.value!=='raw';}
 if(el.id==='manual-cleanup')$('manual-cleanup-reason-field').hidden=el.value!=='none';
});

document.addEventListener('submit',event=>{if(event.target.id==='manual-case-form')event.preventDefault();});
