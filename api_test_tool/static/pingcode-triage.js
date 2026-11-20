/* Project option IDs are resolved from their labels, never guessed or positional. */
(function(root){
'use strict';
const levels=[{id:'critical',name:'致命'},{id:'high',name:'严重'},{id:'medium',name:'一般'},{id:'low',name:'轻微'}];
function optionLevel(label){
 const s=String(label||'').trim().toLowerCase();
 for(const [level,re] of [['critical',/致命|阻断|紧急|最高|highest|critical|blocker|urgent|\bp0\b|\bs1\b/],['high',/严重|高|high|major|\bp1\b|\bs2\b/],['medium',/一般|普通|中|medium|normal|moderate|\bp2\b|\bs3\b/],['low',/轻微|低|建议|low|minor|trivial|\bp3\b|\bp4\b|\bs4\b/]])if(re.test(s))return level;
 return null;
}
function matchOption(values,level){
 let matches=values.filter(v=>optionLevel(v.name||v.text||v.display_name)===level);
 // On five-tier projects, a low-impact issue defaults to 较低; 最低 remains a manual choice.
 // Resolve this semantic distinction explicitly, without depending on returned option order.
 if(level==='low'&&matches.some(v=>/^(低|较低|low|minor|轻微)$/i.test(v.name||v.text||v.display_name||'')))matches=matches.filter(v=>!/^(最低|lowest|p4)$/i.test(v.name||v.text||v.display_name||''));
 return matches.length===1?String(matches[0].id||matches[0]._id):'';
}
function severityProperty(meta){return meta.properties.find(p=>!p.readonly&&!p.read_only&&!p.is_readonly&&(/^(severity|severity_id)$/i.test(p.id)||/严重程度|严重性|severity/i.test(p.name))&&Array.isArray(p.options)&&p.options.length&&!['multi_select','multiple_select','multiselect'].includes(p.type));}
function severityOptions(meta){const p=severityProperty(meta);return p?p.options.map(o=>({id:String(o._id||o.id),name:o.text||o.name||o.id})):levels;}
function severityDefault(meta,level){return severityProperty(meta)?matchOption(severityOptions(meta),level):level;}
// Refresh generated text in old reports without discarding the user's edits.
function withReportReference(text,draft){
 const reference=draft?.report_reference;
 if(!reference?.url||!reference.text||String(text).replace(/\r\n?/g,'\n').split('\n').includes(reference.url))return text;
 return String(text)+'\n\n'+reference.text;
}
function reviewDescription(field,draft){
 if(!field||field.value===field.defaultValue)return withReportReference(draft.description,draft);
 const lines=field.value.split('\n');
 if(lines[0]===field.defaultValue.split('\n')[0])lines[0]='【标题】'+draft.title;
 return withReportReference(lines.join('\n'),draft);
}
function lifecycleStatus(record){return record?.triage_status||(record?.status==='submitted'?'submitted':'pending_submission');}
function canSubmit(record){return !record||(['draft','failed'].includes(record.status)&&lifecycleStatus(record)==='pending_submission');}
// Batch actions share eligibility and completion semantics across reports and dialogs.
function batchEligibility(record,action){
 const state=lifecycleStatus(record),sync=record?.remote_sync;
 if(action==='refresh')return {kind:'ready'};
 if(['loading','unavailable','pending','unknown'].includes(record?.status)||['pending','unknown'].includes(sync?.status))return {kind:'skip',reason:'结果待核对，请先刷新同步状态'};
 const ready={kind:'ready'},noop={kind:'noop',reason:'已经是目标状态，无需变更'};
 if(action==='__submit__')return canSubmit(record)?ready:{kind:'skip',reason:'已提交或当前状态不可提交'};
 if(['accept','reopen'].includes(action)){
  if(record?.status!=='submitted'||!record?.item)return {kind:'skip',reason:'未关联已提交的 PingCode 缺陷'};
  if(state!==(action==='accept'?'regression_passed':'regression_failed'))return {kind:'skip',reason:action==='accept'?'尚未回归通过':'不是回归失败'};
  if(action==='reopen'&&!record.lineage)return {kind:'skip',reason:'没有可重新打开的历史缺陷'};
  if(record.description_error||record.screenshot_error)return {kind:'skip',reason:'正文或截图需要先核对'};
  if(record.remote_state&&(record.remote_state_action===action||(!record.remote_state_action&&action==='reopen')))return noop;
  return ready;
 }
 if(action==='retry-content')return record?.status==='submitted'&&(record.description_error||record.screenshot_error)?ready:{kind:'skip',reason:'无需补交正文与截图'};
 if(action==='restore')return ['rejected','deferred'].includes(state)?ready:{kind:'skip',reason:'只有已拒绝或暂缓的问题可以恢复'};
 if(action==='pending_submission'&&record?.item)return {kind:'skip',reason:'已有原缺陷，不可恢复为新建草稿'};
 if(['pending_submission','pending_regression','rejected','deferred','regression_passed','regression_failed'].includes(action))return state===action?noop:ready;
 return {kind:'skip',reason:'不支持的操作'};
}
function batchOutcome(record,action){
 if(['pending','unknown'].includes(record?.remote_sync?.status)||['pending','unknown'].includes(record?.status))return 'unknown';
 if(['accept','reopen'].includes(action)&&record?.remote_sync&&(record.remote_sync.status==='failed'||record.remote_sync.action!==action))return 'failed';
 if(action==='__submit__')return record?.status==='submitted'?(record.description_error||record.screenshot_error?'unknown':'success'):'failed';
 if(action==='retry-content'&&(record?.description_error||record?.screenshot_error))return 'failed';
 return 'success';
}
const keepBatchSelection=outcome=>['failed','remaining'].includes(outcome);
function remoteIdentity(record){return record?.item?.id?JSON.stringify([record.target?.base_url||'',record.target?.api_version||'',record.target?.project_id||'',record.item.id]):'';}
async function sendQueue(entries,send,update,shouldStop=()=>false){const results=[];for(const entry of entries){if(shouldStop())break;let result;try{result=await send(entry)}catch(error){result={status:'unknown',error:error.message||'响应中断，请核对状态'}}results.push(result);update(entry,result);}return results;}
const api={batchEligibility,batchOutcome,keepBatchSelection,remoteIdentity,reviewDescription,withReportReference,levels,optionLevel,matchOption,severityProperty,severityOptions,severityDefault,lifecycleStatus,canSubmit,sendQueue};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.PingCodeTriage=api;
})(typeof window==='undefined'?{}:window);
