/* Shared online report presentation. Frozen evidence and draft origins stay intact. */
(function(root){
'use strict';
const labels={passed:'通过',failed:'不通过',broken:'执行异常',blocked:'阻塞',not_run:'未执行',skipped:'跳过',partial:'验证未完成',pending_rule:'待确认规则',pending_action:'待用户确认',other:'其他',quarantined:'隔离',unsupported:'不支持'};
const lifecycleLabels={result_corrected:'结果已更正',pending_submission:'待提交',submitted:'已提交',rejected:'已拒绝',deferred:'暂缓',pending_regression:'待回归',regression_passed:'回归通过',regression_failed:'回归失败',check:'待核对'};
const lifecycleDescriptions={
 result_corrected:'同轮重测或结果更正后的历史记录，不是回归通过，不计入当前缺陷。以用例当前实际结果为准。',
 pending_submission:'尚未推送到 PingCode，可继续审核、修改并提交。',
 submitted:'已经推送到 PingCode，后续根据处理结果进入回归。',
 rejected:'确认不作为缺陷处理；必须填写理由，后续 AI 按理由复核，避免重复提交。',
 deferred:'确认问题但暂不处理；必须填写原因，后续回归保留该风险。',
 pending_regression:'问题已处理或具备复测条件，下一轮优先回归。',
 regression_passed:'旧轮次已确认失败的用例，在独立的新轮次实际复测通过。同轮重测、误判更正均不能计入。',
 regression_failed:'旧轮次已确认失败的用例，在独立的新轮次实际复测仍不通过。',
 check:'提交结果或内容状态不确定，需要人工核对后再处理。'
};
const statusKey=value=>({PASS:'passed',FAIL:'failed',BROKEN:'broken',BLOCKED:'blocked',QUARANTINED:'quarantined',UNSUPPORTED:'unsupported'})[value]||value||'other';
function casePriority(value){
 const text=String(value||'').trim();return /^p[0-3]$/i.test(text)?text.toUpperCase():text||'未设置';
}
function caseExecutor(value){return String(value||'').trim()||'未设置';}
function displayTitle(value){
 return String(value||'').replace(/^\[(dev|test|pre|prod|uat|staging|qa|local|待补充环境)\](?=\s*【)/i,'【$1】');
}
function cleanActual(value){
 return String(value||'').replace(/\s*缺陷标题\s*[：:][\s\S]*$/,'').replace(/(?:现场)?截图已关联\s*[。；;]?/g,'').replace(/并已先截图/g,'').replace(/([。！？；])\s*\1+/g,'$1').trim();
}
function observationExcerpt(value){
 const text=String(value||'').trim(),line=text.split(/\r?\n/).find(part=>part.trim())||'';
 return line.length>280?line.slice(0,280)+'…':line.trim();
}
function summarize(cases){
 const out={total:cases.length};for(const c of cases){const key=statusKey(c.status);out[key]=(out[key]||0)+1;}
 out.executed=(out.passed||0)+(out.failed||0)+(out.broken||0)+(out.partial||0);return out;
}
function durationInfo(timing){
 if(!timing?.startedAt||!timing?.finishedAt)return null;
 const start=Date.parse(timing.startedAt),finish=Date.parse(timing.finishedAt);
 if(!Number.isFinite(start)||!Number.isFinite(finish)||finish<start)return null;
 const seconds=Math.floor((finish-start)/1000),minutes=Math.floor(seconds/60);
 const days=Math.floor(minutes/1440),hours=Math.floor(minutes%1440/60),remaining=minutes%60;
 const label=[days&&`${days} 天`,hours&&`${hours} 小时`,remaining&&`${remaining} 分钟`,(seconds%60||!minutes)&&`${seconds%60} 秒`].filter(Boolean).join(' ');
 return {label,start,finish,basis:timing.basis||'',title:timing.label||'执行窗口历时'};
}
function summaryInfo(cases,text,structured=false){
 const raw=String(text||'').trim();
 if(cases.length){
  const counts=summarize(cases),parts=Object.entries(labels).filter(([key])=>counts[key]).map(([key,label])=>`${label} ${counts[key]} 条`);
  return {headline:`共 ${counts.total} 条用例${parts.length?'：'+parts.join('，'):''}。`,notes:raw};
 }
 const first=raw.split(/\r?\n/).find(line=>line.trim())||'';
 const headline=first.length>240?first.slice(0,240)+'…':first;
 return {headline:headline||(structured?'尚未登记用例，无法给出测试结果。':''),notes:raw===headline?'':raw};
}
function experimentInfo(experiment,publishedAt){
 if(!experiment||typeof experiment!=='object')return null;
 const rows=[],details=[],text=key=>typeof experiment[key]==='string'?experiment[key].trim():'';
 const group=[text('experiment_id'),text('variant')].filter(Boolean).join(' · ');
 if(group)rows.push({label:'实验组',value:group});
 const model=[text('model'),text('reasoning_effort')].filter(Boolean).join(' / ');
 const source={requested:'任务指定',reported:'执行端报告',verified:'执行端标记已核实'}[experiment.model_source];
 if(model||source)rows.push({label:'模型与强度',value:[model,source||'来源未记录'].filter(Boolean).join(' · ')});
 if(text('model_source_detail'))details.push('模型来源说明：'+text('model_source_detail'));
 function window(label,startValue,finishValue){
  if(!startValue||!finishValue)return;
  const start=Date.parse(startValue),finish=Date.parse(finishValue);
  if(!Number.isFinite(start)||!Number.isFinite(finish)||finish<start)return;
  const seconds=Math.round((finish-start)/100)/10;
  rows.push({label,value:seconds<60?`${seconds} 秒`:`${Math.floor(seconds/60)} 分 ${Math.round(seconds%60*10)/10} 秒`});
 }
 window('准备及执行窗口',experiment.started_at,experiment.execution_finished_at);
 window('准备窗口',experiment.started_at,experiment.execution_started_at);
 window('执行窗口',experiment.execution_started_at,experiment.execution_finished_at);
 for(const [key,label] of [['tool_calls','工具调用'],['tool_errors','工具异常']]){
  if(Number.isSafeInteger(experiment[key])&&experiment[key]>=0)rows.push({label,value:String(experiment[key])});
 }
 for(const [key,label] of [['started_at','实验开始'],['execution_started_at','执行开始'],['execution_finished_at','执行结束']]){
  if(text(key))details.push(`${label}：${text(key)}`);
 }
 if(experiment.started_at&&!experiment.execution_finished_at)details.push('执行结束时间未记录，不能用报告发布时间代替。');
 return rows.length||details.length?{rows,details}:null;
}
function createExperimentCallout(doc,experiment,publishedAt){
 const info=experimentInfo(experiment,publishedAt);if(!info)return null;
 const section=doc.createElement('section');section.className='rr-scene rr-experiment';section.setAttribute('aria-label','本阶段实验记录');
 const heading=doc.createElement('strong');heading.textContent='本阶段实验记录';
 const note=doc.createElement('span');note.textContent='时间与计数由执行端记录；模型来源由执行端声明。历时不是模型推理耗时。';
 const list=doc.createElement('dl');
 for(const row of info.rows){const item=doc.createElement('div'),label=doc.createElement('dt'),value=doc.createElement('dd');label.textContent=row.label;value.textContent=row.value;item.append(label,value);list.append(item);}
 section.append(heading,note,list);
 if(info.details.length){
  const details=doc.createElement('details'),summary=doc.createElement('summary'),items=doc.createElement('ul');summary.textContent='查看记录时间与来源';
  for(const text of info.details){const item=doc.createElement('li');item.textContent=text;items.append(item);}
  details.append(summary,items);section.append(details);
 }
 return section;
}
const caseAction=caseItem=>caseItem?.required_action&&['authorization','manual_step'].includes(caseItem.required_action.type)?caseItem.required_action:null;
function sections(text){
 const parts=[],pattern=/^【([^\n】]+)】([^\n]*)\n?/gm;let match,last=0;
 while((match=pattern.exec(text))){if(/^(dev|test|pre|prod|uat|staging|qa|local|待补充环境)$/i.test(match[1])&&/^\s*【/.test(match[2]))continue;if(parts.length)parts[parts.length-1].value+=text.slice(last,match.index);else if(match.index)parts.push({name:'补充说明',value:text.slice(0,match.index)});parts.push({name:match[1],value:match[2].trimStart()});last=pattern.lastIndex;}
 if(parts.length)parts[parts.length-1].value+=text.slice(last);else parts.push({name:'问题描述',value:text});
 return parts.map(p=>({...p,value:p.value.trim()}));
}
const serialize=parts=>parts.map(p=>`【${p.name}】\n${p.value}`).join('\n\n');
function recordGroup(record){
 if(record?.description_error||record?.screenshot_error||['pending','unknown','unavailable','loading'].includes(record?.status))return 'check';
 return record?.triage_status||(record?.status==='submitted'?'submitted':'pending_submission');
}
function notRunReason(c){
 if(!['not_run','skipped'].includes(statusKey(c.status)))return '';
 return String(c.not_run_reason||c.evidence||c.actual||'').trim()||'未记录本轮未执行原因（不能据此认定上轮通过）';
}
function fixturePurpose(asset,cases){
 const scenario=cases.find(item=>item.case_id===asset.case_id)?.scenario;
 return scenario?`用于${scenario}`:'测试输入文件';
}
function createAnalysisCallout(doc,caseItem){
 const text=caseItem&&!caseItem.wording_corrected_at?String(caseItem.ai_analysis||'').trim():'';
 if(!text)return null;
 const section=doc.createElement('section');section.className='rr-case-analysis';section.setAttribute('aria-label','AI 解读');
 const heading=doc.createElement('strong');heading.textContent='AI 解读';
 const content=doc.createElement('p');content.textContent=text;section.append(heading,content);
 return section;
}
const helpers={summarize,durationInfo,summaryInfo,experimentInfo,createExperimentCallout,sections,serialize,recordGroup,notRunReason,lifecycleLabels,lifecycleDescriptions,caseAction,cleanActual,fixturePurpose,createAnalysisCallout,displayTitle};
if(typeof module!=='undefined'&&module.exports){module.exports=helpers;return;}
const $=id=>document.getElementById(id),esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dataNode=$('report-review-data');if(!dataNode)return;
if(root.ReportFirstPaint?.canMount()===false)return;
const originalNodes=Array.from(document.body.children).filter(node=>['HEADER','MAIN'].includes(node.tagName));
try{
const data=JSON.parse(dataNode.textContent),bridge=window.PingCodeReview;
const rejectedFindingIds=new Set(data.rejectedFindingIds||[]);
const assets=Array.isArray(data.assets)?data.assets:[];
const access=document.querySelector('meta[name="api-test-public-report"]')?.content||'';
const oldHeader=document.querySelector('body > header,main > header');
const back=oldHeader?.querySelector('a[href="/ui-testing"],a[href="/api-testing"]')?.getAttribute('href')||'/api-testing';
const apiCases=Array.from(document.querySelectorAll('article.case'));
const cases=(data.imported?data.cases:apiCases.map(node=>({case_id:node.querySelector('.case-top code')?.textContent||'',scenario:node.querySelector('h3')?.textContent||'',status:statusKey(node.dataset.status),evidence:node.querySelector('summary p')?.textContent||'',node}))).map(item=>({...item,rawEvidence:String(item.evidence||item.actual||''),evidence:cleanActual(item.evidence),actual:cleanActual(item.actual)}));
const priorityOptions=[...new Set(['P0','P1','P2','P3','未设置',...cases.map(c=>casePriority(c.priority))])];
const executorOptions=[...new Set(['AI','人工','AI或人工','未设置',...cases.map(c=>caseExecutor(c.executor))])];
const filterOption=value=>`<option value="${esc(value)}">${esc(value)}</option>`;
let correctionRevision=Number(data.correctionRevision)||0;
const dataCases=()=>cases.filter(item=>String(item.test_data||'').trim()||assets.some(asset=>asset.kind==='fixture'&&asset.case_id===item.case_id));
const fixtures=assets.filter(asset=>asset.kind==='fixture');
const entries=Array.from(document.querySelectorAll('.copy-defect')).map(copy=>{
 const field=$(copy.dataset.draft),draft=field.closest('.defect-draft'),article=draft.closest('article');
 const parts=sections(field.value).map(part=>part.name==='标题'?{...part,value:displayTitle(part.value)}:/实际结果|依据与复核线索|问题描述/.test(part.name)?{...part,value:cleanActual(part.value)}:part),title=displayTitle(parts.find(p=>p.name==='标题')?.value||article?.querySelector('h3')?.textContent||draft.querySelector('strong')?.textContent||'检查发现');
 field.value=serialize(parts);
 return {id:copy.dataset.draft,title,field,copy,draft,article,parts};
});
const original=document.createElement('div');original.id='rr-original';original.hidden=true;
for(const node of originalNodes)original.append(node);
const shell=document.createElement('div');shell.className='rr-shell';shell.setAttribute('data-rr-enhanced','');
shell.innerHTML=`<div class="rr-top"><a class="rr-back" href="${back}">← 返回测试台</a><span class="rr-separator">/</span><span>${data.reportType==='total'?'总报告':data.totalReport?'阶段报告':'测试报告'}</span><div id="rr-account"></div></div>
 <div class="rr-heading"><div><p class="rr-eyebrow">TEST REPORT</p><h1>${esc(document.title)}</h1><p class="rr-source">${esc(data.aggregate?'汇总同项目各会话，审核结果保存到原始记录':data.uiExecution?'用例与数据保存在本会话':data.source?'来源文件：'+data.source:(back==='/ui-testing'?'UI 测试报告':'API 测试报告'))}</p></div><div class="rr-heading-actions"><button id="rr-refresh" type="button">刷新提交状态</button></div></div>
 <div id="rr-stats" class="rr-stats"></div>
 <div class="rr-tabs" role="tablist" aria-label="报告内容"><button type="button" role="tab" data-rr-tab="review" aria-selected="true">${data.uiExecution?'缺陷与回归':'缺陷审核'} <span>${entries.length}</span></button><button type="button" role="tab" data-rr-tab="cases" aria-selected="false">全部用例 <span>${cases.length||'—'}</span></button>${data.uiExecution?`<button type="button" role="tab" data-rr-tab="data" aria-selected="false">测试数据 <span>${dataCases().length}</span></button>`:''}${data.imported?'':'<button type="button" role="tab" data-rr-tab="evidence" aria-selected="false">执行明细</button>'}</div>
 <div id="rr-review" class="rr-review" role="tabpanel"><div class="rr-inbox"><div class="rr-inbox-tools"><div class="rr-filter-row"><input id="rr-search" type="search" aria-label="搜索缺陷" placeholder="搜索用例编号或缺陷标题"><div id="rr-filter-picker" class="rr-status-filter"><button id="rr-filter" type="button" aria-label="按缺陷处理状态筛选" aria-haspopup="listbox" aria-controls="rr-filter-menu" aria-expanded="false"><span>全部状态</span><b>${entries.length}</b></button><div id="rr-filter-menu" class="rr-status-filter-menu" role="listbox" aria-label="缺陷处理状态" hidden><button type="button" role="option" data-filter-value="all" aria-selected="true"><span>全部状态</span><b>${entries.length}</b></button>${Object.entries(lifecycleLabels).filter(([key])=>!data.uiExecution||key!=='result_corrected').map(([key,label])=>`<button type="button" role="option" data-filter-value="${key}" aria-selected="false"><span>${label}</span><b>0</b></button>`).join('')}</div></div><button id="rr-status-help" type="button" aria-haspopup="dialog">状态说明</button></div></div><div id="rr-batch"></div><div id="rr-list" class="rr-list"></div><p id="rr-empty-list" class="rr-empty" hidden>没有匹配的缺陷。</p><p class="rr-list-note">选择左侧问题，在右侧核对正文与截图；处理状态在上方统一修改。</p></div><div class="rr-review-side"><div class="rr-editor-heading"><h2 id="rr-detail-title">缺陷详情</h2><div class="rr-editor-actions"><button type="button" id="rr-expand" aria-haspopup="dialog" aria-controls="rr-detail-dialog" aria-expanded="false">展开查看</button><button type="button" id="rr-prev" aria-label="上一条缺陷">← 上一条</button><button type="button" id="rr-next" aria-label="下一条缺陷">下一条 →</button></div></div><div id="rr-decision-reason" class="rr-decision-reason" hidden><strong>拒绝原因</strong><p></p></div><div id="rr-review-dock" role="region" aria-label="缺陷详情正文" tabindex="0"><div class="rr-empty"><span class="rr-empty-symbol">✓</span><h3>${entries.length?'选择一条缺陷开始审核':'本报告没有缺陷草稿'}</h3><p>${entries.length?'核对复现步骤、实际结果和附件，再提交到 PingCode。':'可以切换到全部用例查看测试结果。'}</p></div></div></div></div>
 <div id="rr-cases" class="rr-case-panel" role="tabpanel" hidden><div class="rr-case-tools"><input type="search" id="rr-case-search" placeholder="搜索用例编号、模块或标题" aria-label="搜索结果用例"><select id="rr-case-priority-filter" aria-label="按优先级筛选"><option value="">全部优先级</option>${priorityOptions.map(filterOption).join('')}</select><select id="rr-case-executor-filter" aria-label="按执行方式筛选"><option value="">全部执行方式</option>${executorOptions.map(filterOption).join('')}</select><select id="rr-case-filter" aria-label="按结果筛选"><option value="all">全部结果</option>${Object.entries(labels).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select><span id="rr-case-count"></span></div>${data.retestBase?'<details id="rr-retest-shared" hidden><summary><strong>共用测试数据</strong><span id="rr-retest-shared-count"></span><span>展开填写</span></summary><section id="rr-retest-groups" aria-label="共同阻塞问题" hidden></section></details><section id="rr-retest-batch" aria-label="用例补测操作"></section>':''}<div class="rr-table-wrap"><table class="rr-table"><thead><tr><th>${data.retestBase?'<input type="checkbox" id="rr-retest-select-all" aria-label="跨页选择当前筛选的全部可补测用例"> ':''}用例编号</th><th>标题 / 场景</th><th>优先级</th><th>模块</th><th>执行方式</th><th>结果</th>${data.retestBase?'<th>补测准备状态</th>':''}<th>实际结果 / 未执行原因</th><th></th></tr></thead><tbody id="rr-case-rows"></tbody></table></div><div class="rr-pagination"><button id="rr-case-prev" type="button">上一页</button><span id="rr-case-page"></span><button id="rr-case-next" type="button">下一页</button></div></div>
 <div id="rr-data" class="rr-data-panel" role="tabpanel" hidden><div class="rr-data-head"><div><h2>测试数据</h2><p>测试输入和执行用文件集中保存在本报告中。</p></div><div class="rr-data-actions"><a href="test-data.zip" download>下载测试数据包</a><a href="cases.html">查看完整用例与数据</a></div></div><div id="rr-fixtures" class="rr-data-section"></div><div id="rr-text-data" class="rr-data-section"></div></div>`;
document.body.prepend(shell);shell.append(original);document.body.classList.add('rr-page');shell.classList.toggle('rr-with-retest',!!data.retestBase);document.body.id='report-review-page';
root.ReportSelects?.upgrade(shell.querySelector('.rr-case-tools'));
if(data.totalReport||data.projectTotal){
 const navigation=document.createElement('nav');navigation.className='rr-report-navigation';navigation.setAttribute('aria-label','报告类型');
 navigation.innerHTML=(data.projectTotal?`<a href="${esc(data.projectTotal.report_url)}">${esc(data.projectTotal.title)} · 项目总报告</a>`:'')+(data.reportType==='total'?'<strong aria-current="page">总报告</strong>':data.totalReport?`<a class="rr-total-report" href="${esc(data.totalReport?.report_url||'#')}">查看总报告</a><strong aria-current="page">当前阶段报告</strong>`:'<strong aria-current="page">当前报告</strong>')+(data.stageReports?.length?`<details><summary>阶段报告 · ${data.stageReports.length} 份</summary><ul>${data.stageReports.map(stage=>`<li><a href="${esc(stage.report_url)}">${esc(stage.title)}</a><small>${esc(new Date(stage.created_at).toLocaleString())}</small></li>`).join('')}</ul></details>`:'');
 shell.querySelector('.rr-heading').before(navigation);
}
const reviewSide=shell.querySelector('.rr-review-side'),detailDialog=document.createElement('dialog'),detailPlaceholder=document.createElement('div');
detailPlaceholder.setAttribute('aria-hidden','true');
detailDialog.id='rr-detail-dialog';detailDialog.className='rr-detail-dialog';detailDialog.setAttribute('aria-labelledby','rr-detail-title');shell.append(detailDialog);
function fitEditorFields(){
 for(const input of document.querySelectorAll('#rr-fields textarea')){
  if(!input.clientWidth)continue;
  input.style.height='auto';input.style.height=(input.scrollHeight+input.offsetHeight-input.clientHeight)+'px';
 }
}
const dockObserver=new ResizeObserver(()=>{const width=$('rr-review-dock').clientWidth;if(width!==dockObserver.width){dockObserver.width=width;fitEditorFields()}});
dockObserver.observe($('rr-review-dock'));
$('rr-expand').onclick=()=>{
 if(detailDialog.open){detailDialog.close();return;}
 const scrollTop=$('rr-review-dock').scrollTop;
 detailPlaceholder.style.height=reviewSide.offsetHeight+'px';reviewSide.replaceWith(detailPlaceholder);
 detailDialog.append(reviewSide);document.body.classList.add('rr-detail-expanded');
 $('rr-expand').textContent='收起窗口';$('rr-expand').setAttribute('aria-expanded','true');detailDialog.showModal();
 fitEditorFields();$('rr-review-dock').scrollTop=scrollTop;$('rr-expand').focus();
};
// The docked PingCode dialog must stay open when Escape closes the expanded view.
detailDialog.addEventListener('keydown',event=>{
 if(event.key==='Escape'&&!event.defaultPrevented){event.preventDefault();detailDialog.close();}
});
detailDialog.addEventListener('close',()=>{
 const scrollTop=$('rr-review-dock').scrollTop;
 detailPlaceholder.replaceWith(reviewSide);document.body.classList.remove('rr-detail-expanded');
 $('rr-expand').textContent='展开查看';$('rr-expand').setAttribute('aria-expanded','false');
 fitEditorFields();$('rr-review-dock').scrollTop=scrollTop;$('rr-expand').focus({preventScroll:true});
});
const statusHelp=document.createElement('dialog');statusHelp.id='rr-status-help-dialog';statusHelp.className='rr-case-dialog rr-status-help-dialog';
statusHelp.innerHTML=`<button type="button" class="rr-case-close" aria-label="关闭状态说明">✕</button><h2>缺陷状态说明</h2><p>状态用于记录缺陷处理结论，并作为后续 AI 回归的上下文。</p><dl>${Object.entries(lifecycleDescriptions).filter(([key])=>!data.uiExecution||key!=='result_corrected').map(([key,description])=>`<div><dt><span class="rr-row-state ${key}">${esc(lifecycleLabels[key])}</span></dt><dd>${esc(description)}</dd></div>`).join('')}</dl>`;
document.body.append(statusHelp);statusHelp.querySelector('button').onclick=()=>statusHelp.close();
$('rr-status-help').onclick=()=>statusHelp.showModal();
// An earlier collaboration response may already have mounted in the initial frame.
const collaboration=document.querySelector('.rr-collaboration');if(collaboration)shell.prepend(collaboration);
const wecomActions=document.querySelector('.wecom-report-actions');if(wecomActions)shell.querySelector('.rr-heading-actions').prepend(wecomActions);
function moveAccount(){const account=document.querySelector('.account-bar');if(account){account.classList.remove('account-bar-floating');$('rr-account').append(account);return true}return false}
if(!moveAccount()){const observer=new MutationObserver(()=>{if(moveAccount())observer.disconnect()});observer.observe(document.body,{childList:true});}
if(data.imported){const link=document.createElement('a');link.href='cases.xlsx';link.textContent='导出 XLSX';shell.querySelector('.rr-heading-actions').prepend(link);}
if(data.uiExecution){const link=document.createElement('button');link.type='button';link.id='rr-data-shortcut';link.textContent=`测试数据 ${dataCases().length}`;link.onclick=()=>tab('data');shell.querySelector('.rr-heading-actions').prepend(link);}
if(data.hasCoverage){const link=document.createElement('a');link.href='cases.html';link.textContent='覆盖清单与回查';shell.querySelector('.rr-case-tools').prepend(link);}
const summary=document.createElement('div');summary.id='rr-summary';shell.querySelector('.rr-heading').after(summary);
updateSummary(data.summary);
if(data.reportType!=='total'){
 const experiment=createExperimentCallout(document,data.experiment,data.experimentPublishedAt);
 if(experiment){const details=document.createElement('details'),heading=document.createElement('summary');details.className='rr-report-notes';heading.textContent='实验记录与时间来源';details.append(heading,experiment);summary.after(details);}
}
if(data.sceneRetention){
 const outcome=data.sceneOutcome||{},items=Array.isArray(outcome.items)?outcome.items:[];
 const status={cleaned:'已核实清理',retained:'已核实保留',partial:'部分完成',unverified:'未核实'}[outcome.status]||'未记录收尾结果';
 const scene=document.createElement('div');scene.className='rr-scene';
 scene.innerHTML=`<strong>测试现场</strong><span>${esc(data.sceneRetention.label||'不保留测试现场')} · ${esc(status)}</span>${outcome.note||items.length?`<details><summary>查看收尾记录${items.length?' · '+items.length+' 个对象':''}</summary>${outcome.note?`<p>${esc(outcome.note)}</p>`:''}<ul>${items.map(item=>`<li>${esc(item.name)}${item.case_id?'（'+esc(item.case_id)+'）':''} · ${esc({retained:'保留',cleaned:'清理',unverified:'未核实'}[item.state]||'未核实')}${item.reason?' · '+esc(item.reason):''}</li>`).join('')}</ul></details>`:''}`;
 summary.after(scene);
}
function updateSummary(text){
 data.summary=text;
 const info=summaryInfo(cases,text,data.imported||data.uiExecution);
 summary.innerHTML=`${info.headline?`<p class="rr-overview-text">${esc(info.headline)}</p>`:''}${info.notes?`<details class="rr-report-notes"><summary>查看原始报告说明</summary><p class="rr-notes-hint">发布时保存的说明；当前统计以用例结果为准。</p><div class="rr-notes-content">${esc(info.notes)}</div></details>`:''}`;
 summary.hidden=!info.headline&&!info.notes;
}
const formatSize=value=>value<1024?`${value} B`:value<1024*1024?`${(value/1024).toFixed(1)} KB`:`${(value/1024/1024).toFixed(1)} MB`;
function showEvidence(entry){
 $('rr-evidence')?.remove();const holder=document.createElement('div');holder.id='rr-evidence';
 const media=document.createElement('div');media.className='rr-evidence-media';holder.append(media);
 const inlineScreenshots=new Set(bridge?.screenshotAssets?.()||[]);
 for(const node of entry.article?.children||[]){
  if(node.classList.contains('defect-draft'))continue;
  const imageSource=node.dataset.imageSrc||node.getAttribute('href')||'';
  if(node.matches('.report-image-preview,a')&&inlineScreenshots.has(imageSource.match(/(?:^|\/)asset-([^/?#]+)/)?.[1]))continue;
  if(node.matches('details,.report-image-preview')||(node.matches('a')&&node.querySelector('img,video')))media.append(node.cloneNode(true));
 }
 const caseId=entry.article?.dataset.caseId||entry.title.match(/^\[([^\]]+)\]/)?.[1]||'';
 const currentCase=cases.find(item=>item.case_id===caseId);
 if(currentCase&&statusKey(currentCase.status)!=='failed'){
  const note=document.createElement('p');note.className='rr-history-note';
  note.textContent=`该用例当前为“${labels[statusKey(currentCase.status)]||'待核对'}”。关联回归记录不重复计入当前不通过用例。`;
  holder.prepend(note);
 }
 const hasScreenshot=assets.some(asset=>asset.kind==='screenshot'&&asset.case_id===caseId)||holder.querySelector('img');
 if(!hasScreenshot){const note=document.createElement('p');note.className='rr-no-screenshot';note.textContent='本缺陷未关联截图证据';media.append(note);}
 media.hidden=!media.children.length;
 if(data.uiExecution&&caseId)holder.insertAdjacentHTML('beforeend',relatedDataMarkup(caseId));
 $('rr-review-dock').append(holder);
}
function relatedDataMarkup(caseId){
 const related=fixtures.filter(asset=>asset.case_id===caseId);
 return `<section class="rr-related-data" aria-label="关联测试数据"><h3>关联测试数据 <span>${related.length}</span></h3>${related.length?`<ul>${related.map(asset=>`<li><div><strong>${esc(asset.filename)}</strong><small>${formatSize(Number(asset.size)||0)}${asset.step?' · '+esc(asset.step):''}</small></div><a href="${esc(asset.url||'asset-'+encodeURIComponent(asset.id))}" download aria-label="下载 ${esc(asset.filename)}">下载</a></li>`).join('')}</ul>`:'<p class="rr-data-empty">此用例尚未关联可下载的测试文件；正文中的文件名不代表文件已上传。</p>'}</section>`;
}
function renderData(){
 $('rr-fixtures').innerHTML=`<h3>文件型测试数据 <span>${fixtures.length}</span></h3>`+(fixtures.length?`<div class="rr-data-list">${fixtures.map(asset=>`<div><div><strong>${esc(asset.filename)}</strong><small>${esc(asset.case_id||'未关联')} · ${esc(fixturePurpose(asset,cases))} · ${formatSize(Number(asset.size)||0)}</small></div><a href="${esc(asset.url||'asset-'+encodeURIComponent(asset.id))}" download>下载</a></div>`).join('')}</div>`:'<p class="rr-data-empty">本报告没有文件型测试数据。</p>');
 const textCases=dataCases().filter(item=>String(item.test_data||'').trim());
 $('rr-text-data').innerHTML=`<h3>文本测试数据 <span>${textCases.length}</span></h3>`+(textCases.length?textCases.map(item=>`<details><summary><strong>${esc(item.case_id)}</strong> ${esc(item.scenario||'')}</summary><pre>${esc(item.test_data)}</pre></details>`).join(''):'<p class="rr-data-empty">本报告没有文本测试数据。</p>');
}
function renderStats(){
const stats=summarize(cases);
if(cases.length){
 const values=[['total','全部用例',''],['passed','通过','green'],['failed','不通过','red'],['blocked','阻塞','amber']];
 for(const key of ['partial','pending_action','pending_rule','broken','not_run','skipped','quarantined','unsupported','other'])if(stats[key])values.push([key,labels[key],'muted']);
 const timing=durationInfo(data.timing),timeFormat=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
 const duration=timing?`<div class="rr-duration" title="${esc(timing.basis)}"><b>${esc(timing.label)}</b><span>${esc(timing.title)}</span><small>${esc(timeFormat.format(timing.start))} — ${esc(timeFormat.format(timing.finish))}（北京时间）<br>${esc(timing.basis)}</small></div>`:data.timingNotice?`<div class="rr-duration rr-duration-unknown"><b>未记录</b><span>执行耗时</span><small>${esc(data.timingNotice)}</small></div>`:'';
 $('rr-stats').innerHTML=values.map(([key,label,color])=>`<button type="button" class="rr-stat ${color}" data-rr-stat="${key}" aria-label="查看${label==='全部用例'?label:label+'用例'}，${stats[key]||0}条"><b>${stats[key]||0}</b><span>${label}</span></button>`).join('')+duration+`<div class="rr-progress"><div><span>已执行 ${stats.executed} / ${stats.total}</span><b>${Math.round(stats.executed/stats.total*100)}%</b></div><div class="rr-track" role="progressbar" aria-label="已执行用例比例" aria-valuemin="0" aria-valuemax="${stats.total}" aria-valuenow="${stats.executed}"><i style="width:${(stats.passed||0)/stats.total*100}%"></i><i class="rr-failed-segment" style="width:${((stats.failed||0)+(stats.broken||0)+(stats.partial||0))/stats.total*100}%"></i></div><small>用例执行比例，不代表功能覆盖率；阻塞及未执行不计入</small></div>`;
}else $('rr-stats').innerHTML=`<div class="rr-stat"><b>${entries.length}</b><span>检查发现</span></div><p>未提供逐条执行统计。</p>`;
}
renderStats();
let selected=null,filter='all',quickFilter='',page=0,visible=[];
function rejectedFinding(entry,record){
 return record?.triage_status?record.triage_status==='rejected':rejectedFindingIds.has(entry.id);
}
function currentFinding(entry,record){
 if(!data.uiExecution)return true;
 const c=cases.find(c=>c.case_id===entry.article?.dataset.caseId);
 return c?.status==='failed'&&!rejectedFinding(entry,record);
}
function reportFinding(entry,record){
 if(!data.uiExecution)return true;
 const c=cases.find(c=>c.case_id===entry.article?.dataset.caseId);
 if(!c||rejectedFinding(entry,record))return false;
 // Audited withdrawal is not a real retest. Keep stable draft IDs internally.
 if(c.status_before_correction==='failed'&&c.status!=='failed')return false;
 return currentFinding(entry,record)||['pending_regression','regression_passed','regression_failed'].includes(entry.article?.dataset.regressionStatus);
}
function findingGroup(entry,record){
 const c=cases.find(c=>c.case_id===entry.article?.dataset.caseId);
 const group=recordGroup(record);
 if(data.uiExecution&&c&&c.status!=='failed'&&(!entry.article?.dataset.regressionStatus||['result_corrected','pending_submission'].includes(entry.article.dataset.regressionStatus))&&!['check','rejected','deferred'].includes(group))return 'result_corrected';
 return group;
}
const batchLabels={titles:'修改标题属性',accept:'验收并同步 PingCode',reopen:'重新打开原缺陷',__submit__:'提交到 PingCode',pending_regression:'标记待回归',rejected:'拒绝缺陷',deferred:'暂缓处理',restore:'恢复处理','retry-content':'补交正文与截图',refresh:'刷新同步状态',regression_passed:'更正为回归通过',regression_failed:'更正为回归失败'};
let showBatchResult=()=>{},showBackgroundJobs=()=>{},showBatchConnection=()=>{};
const triage=root.PingCodeTriage;
const matchesQuick=record=>!quickFilter||(quickFilter==='accept'||quickFilter==='reopen'?triage.batchEligibility(record,quickFilter).kind==='ready':!!record?.remote_sync&&record.remote_sync.status!=='success'||recordGroup(record)==='check');
const rows=new Map();
for(const entry of entries){
 const row=document.createElement('div');row.className='rr-defect-row';row.dataset.id=entry.id;
 const actual=entry.parts.find(p=>/实际结果|依据与复核线索|问题描述/.test(p.name))?.value||'打开详情，核对测试步骤与结果。';
 const caseId=entry.article?.dataset.caseId||entry.title.match(/^\[([^\]]+)\]/)?.[1]||entry.article?.querySelector('.case-top code')?.textContent||String(rows.size+1).padStart(2,'0');
 row.innerHTML=`<div class="rr-row-top"><div class="rr-checkbox"></div><span class="rr-case-id">${esc(caseId)}</span><span class="rr-row-state"></span></div><button class="rr-row-open" type="button"><strong>${esc(entry.title)}</strong><span>${esc(actual.slice(0,190))}</span></button><p class="rr-row-sync"></p><p class="rr-row-reason" hidden></p><div class="rr-row-bottom"><span class="rr-row-link"></span><button class="rr-detail" type="button">查看详情 →</button></div>`;
 const box=bridge?.selections.get(entry.id);if(box)row.querySelector('.rr-checkbox').append(box);
 row.querySelector('.rr-row-open').onclick=row.querySelector('.rr-detail').onclick=()=>select(entry.id);
 rows.set(entry.id,row);$('rr-list').append(row);
}
const toolbar=document.querySelector('.pc-batch-toolbar');if(toolbar)$('rr-batch').append(toolbar);
let syncBatchStatus=()=>{},syncBatchTitles=()=>{};
if(toolbar&&!access&&back==='/ui-testing'){
 const button=document.createElement('button');button.type='button';button.textContent='批量修改标题';button.id='rr-title-batch-open';button.hidden=true;toolbar.append(button);
 const feedback=document.createElement('span');feedback.className='pc-inline-state';feedback.setAttribute('role','status');toolbar.append(feedback);
 syncBatchTitles=()=>{const count=Array.from(bridge.selections.values()).filter(box=>box.checked&&!box.disabled).length;button.disabled=!count||bridge.isSending();button.title=count?'修改所选缺陷的标题属性':'请先勾选要修改的缺陷';};
 button.onclick=()=>{
  const ids=Array.from(bridge.selections).filter(([,box])=>box.checked&&!box.disabled).map(([id])=>id);
  let panel=$('rr-title-batch');if(panel)panel.remove();
  panel=document.createElement('dialog');panel.id='rr-title-batch';panel.className='pc-dialog';
  panel.innerHTML=`<h2>批量修改标题（${ids.length} 条）</h2><p>修改会保存到共享报告，保留各条问题描述，不修改 PingCode 原单标题。未填写的属性保持原值。</p><form><label>环境<select name="environment"><option value="">保持原值</option>${['dev','test','pre','prod','uat','staging','qa','local'].map(v=>`<option>${v}</option>`).join('')}</select></label><label>业务端<select name="client"><option value="">保持原值</option><option>B端</option><option>C端</option></select></label><label>功能/模块<input name="module" maxlength="60" placeholder="留空保持各条原模块"></label><p role="status"></p><div class="pc-actions"><button type="button">取消</button><button type="submit" ${ids.length?'':'disabled'}>应用到所选缺陷</button></div></form>`;
  document.body.append(panel);panel.querySelector('button[type="button"]').onclick=()=>panel.close();panel.addEventListener('cancel',event=>{if(panel.dataset.busy)event.preventDefault()});
  if(!ids.length)panel.querySelector('[role="status"]').textContent='请先勾选要修改的缺陷。';
  panel.querySelector('form').onsubmit=async event=>{event.preventDefault();const form=event.currentTarget,save=form.querySelector('[type="submit"]'),cancel=form.querySelector('[type="button"]'),values=Object.fromEntries(new FormData(form)),status=panel.querySelector('[role="status"]');save.disabled=cancel.disabled=true;panel.dataset.busy='true';status.textContent='正在保存…';try{const count=await bridge.editTitles(ids.filter(id=>bridge.selections.get(id)?.checked),values);feedback.textContent=`已创建 ${count} 条标题修改后台任务`;panel.close();update()}catch(error){status.textContent=error.message}finally{delete panel.dataset.busy;save.disabled=cancel.disabled=false;bridge.selectionChanged()}};
  root.ReportSelects?.upgrade(panel);panel.showModal();
 };
}
if(toolbar&&!access&&bridge?.runBatch){
 const submit=$('pc-batch-start'),actions=document.createElement('div');actions.className='rr-batch-actions';
 const clear=document.createElement('button');clear.type='button';clear.textContent='清空选择';clear.id='rr-clear-selection';clear.onclick=()=>{bridge.clearSelection();update()};toolbar.insertBefore(clear,submit);
 const save=document.createElement('button');save.id='rr-batch-status-save';save.type='button';save.className='pc-primary';
 const picker=document.createElement('select');picker.id='rr-batch-status';picker.setAttribute('aria-label','更多批量操作');
 actions.append(save,picker);toolbar.insertBefore(actions,submit);submit.hidden=true;
 const note=document.createElement('div');note.id='rr-batch-message';note.setAttribute('role','status');note.setAttribute('aria-live','polite');
 const resultDetails=document.createElement('details');resultDetails.id='rr-batch-results';resultDetails.hidden=true;
 const retry=document.createElement('button');retry.type='button';retry.textContent='重试失败项';retry.hidden=true;
 $('rr-batch').append(note,retry,resultDetails);
 const taskPanel=document.createElement('section');taskPanel.id='rr-background-tasks';taskPanel.setAttribute('aria-label','后台批量任务');taskPanel.hidden=true;
 const connection=document.createElement('p');connection.className='rr-batch-connection';connection.hidden=true;connection.setAttribute('role','status');
 const taskList=document.createElement('div'),history=document.createElement('details');history.className='rr-task-history';history.innerHTML='<summary>历史批次</summary>';taskPanel.append(connection,taskList,history);$('rr-batch').after(taskPanel);
 showBatchConnection=ok=>{connection.hidden=ok;if(!ok)taskPanel.hidden=false;connection.textContent='暂时无法读取进度，后台任务仍由服务端执行；连接恢复后自动更新。'};
 const outcomeLabels={success:'成功',failed:'失败',unknown:'待核对',remaining:'未执行',skipped:'已排除',noop:'无需变更'};
 const taskNodes=new Map();
 showBackgroundJobs=jobs=>{
  const shown=jobs;taskPanel.hidden=!shown.length&&connection.hidden;history.hidden=!jobs.some(job=>!job.active&&job!==jobs[0]);
  for(const job of shown){
   let node=taskNodes.get(job.id);if(!node){node=document.createElement('div');node.className='rr-background-task';node.innerHTML='<p class="rr-task-summary" role="status"></p><div class="rr-task-actions"><button type="button" data-task-stop>停止后续执行</button><button type="button" data-task-retry hidden>重试失败项</button></div><details><summary>查看逐条进度与结果</summary><div class="rr-task-items"></div></details>';taskNodes.set(job.id,node);taskList.append(node)}
   const parent=job.active||job===jobs[0]?taskList:history;if(node.parentNode!==parent)parent.append(node);
   const finished=job.items.filter(item=>!['queued','running'].includes(item.outcome)).length,success=job.items.filter(item=>item.outcome==='success').length,failed=job.items.filter(item=>item.outcome==='failed').length,unknown=job.items.filter(item=>item.outcome==='unknown').length;
   node.querySelector('.rr-task-summary').textContent=`${batchLabels[job.action]||'批量操作'} · ${job.active?'后台处理中':job.status==='stopped'?'已停止':'已完成'} ${finished} / ${job.items.length} · 成功 ${success} · 失败 ${failed}${unknown?' · 待核对 '+unknown:''}${job.stop_requested&&job.active?' · 当前请求结束后停止':''}`;
   const stop=node.querySelector('[data-task-stop]');stop.hidden=!job.active;stop.disabled=job.stop_requested;stop.onclick=async()=>{stop.disabled=true;try{await bridge.stopBackgroundJob(job.id)}catch(error){connection.hidden=false;connection.textContent=error.message;stop.disabled=false}};
   const retryJob=node.querySelector('[data-task-retry]');retryJob.hidden=job.active||!job.items.some(item=>['failed','remaining'].includes(item.outcome)&&item.id);retryJob.textContent='处理失败 / 未执行项';retryJob.onclick=()=>{const ids=job.items.filter(item=>['failed','remaining'].includes(item.outcome)&&item.id&&!bridge.isBusy(item.id)).map(item=>item.id);bridge.clearSelection();for(const id of ids)bridge.selections.get(id).checked=true;update();launch(job.action,ids)};
   const list=node.querySelector('.rr-task-items');list.replaceChildren();
   for(const item of job.items){const line=document.createElement('p');const status=item.outcome==='queued'?'等待处理':item.outcome==='running'?'正在处理，等待响应':outcomeLabels[item.outcome];const since=item.started_at&&!item.finished_at?`（已等待 ${Math.max(0,Math.floor((Date.now()-Date.parse(item.started_at))/1000))} 秒）`:'';line.textContent=`${rows.get(item.id)?.querySelector('.rr-case-id')?.textContent||item.label} · ${status}${since} · ${item.message}`;if(item.id){const view=document.createElement('button');view.type='button';view.textContent='查看详情';view.onclick=()=>select(item.id);line.append(' ',view)}list.append(line);}
  }
  for(const [id,node]of taskNodes)node.hidden=!shown.some(job=>job.id===id);
 };
 showBackgroundJobs(bridge.backgroundJobs());

 const hint=document.createElement('span');hint.className='rr-selection-hint';hint.textContent='勾选后可批量验收、重新打开或修改';toolbar.append(hint);
 const chosen=()=>Array.from(bridge.selections).filter(([id,box])=>box.checked&&!bridge.isBusy(id)).map(([id])=>id);
 let primary='',lastResult=null;
 showBatchResult=result=>{
  lastResult=result;const counts={};for(const item of result.items)counts[item.outcome]=(counts[item.outcome]||0)+1;
  note.textContent=`${batchLabels[result.action]||'批量操作'}：`+Object.entries(outcomeLabels).filter(([key])=>counts[key]).map(([key,label])=>`${label} ${counts[key]} 条`).join('，')+'。成功项已取消勾选。';
  resultDetails.hidden=false;resultDetails.innerHTML='<summary>查看逐条处理结果</summary>';
  for(const item of result.items){const line=document.createElement('p'),entry=entries.find(e=>e.id===item.id);line.textContent=`${rows.get(item.id)?.querySelector('.rr-case-id')?.textContent||item.id} · ${outcomeLabels[item.outcome]} · ${item.message}`;const button=document.createElement('button');button.type='button';button.textContent='查看详情';button.onclick=()=>select(item.id);line.append(' ',button);resultDetails.append(line);}
  retry.hidden=!result.items.some(item=>item.outcome==='failed');retry.textContent=result.action==='__submit__'?'重新审核失败项':'重试失败项';
 };
 retry.onclick=()=>{const ids=lastResult.items.filter(item=>item.outcome==='failed').map(item=>item.id);bridge.clearSelection();for(const id of ids)if(bridge.selections.has(id))bridge.selections.get(id).checked=true;update();launch(lastResult.action,ids)};
 const confirmDialog=document.createElement('dialog');confirmDialog.id='rr-batch-confirm';confirmDialog.className='pc-dialog rr-batch-confirm';
 document.body.append(confirmDialog);confirmDialog.addEventListener('cancel',event=>{if(bridge.isSending()||confirmDialog.dataset.submitting)event.preventDefault()});
 async function launch(action,ids=chosen()){
  const reportIds=values=>values.filter(id=>{const entry=entries.find(e=>e.id===id);return entry&&reportFinding(entry,bridge.records.get(id));});
  ids=reportIds(ids);
  if(!ids.length||bridge.isSending())return;
  if(action==='titles'){$('rr-title-batch-open')?.click();return;}
  if(action==='__submit__'){submit.click();return;}
  const plan=bridge.batchPlan(ids,action),versions=Object.fromEntries(plan.map(item=>[item.id,item.record?.updated_at||'']));
  const eligible=plan.filter(item=>item.kind==='ready'),excluded=plan.filter(item=>item.kind==='skip');
  const needsReason=['rejected','deferred','regression_passed','regression_failed'].includes(action);
  confirmDialog.innerHTML=`<h2>${esc(batchLabels[action])}</h2><p>已选 ${ids.length} 条，可执行 ${eligible.length} 条${excluded.length?`，排除 ${excluded.length} 条`:''}。${['accept','reopen','retry-content'].includes(action)?'更新已关联的原 PingCode 缺陷，不创建新缺陷。':action==='refresh'?'读取并核对同步结果，不改变测试结论。':'仅更新报告中的处理状态，保留原始测试证据。'}</p><div class="rr-batch-preview"></div>${needsReason?'<label>操作原因 / 更正依据<textarea id="rr-batch-reason-input" maxlength="4000" rows="3" required></textarea></label>':''}<p class="rr-batch-progress" role="status"></p><div class="pc-actions"><button type="button" data-cancel>取消</button><button type="button" data-stop hidden>停止后续执行</button><button type="button" class="pc-primary" data-confirm>${excluded.length?'仅处理符合条件的':'确认处理'} ${eligible.length} 条</button></div>`;
  const list=confirmDialog.querySelector('.rr-batch-preview');
  for(const item of plan){const row=document.createElement('p');row.textContent=`${rows.get(item.id)?.querySelector('.rr-case-id')?.textContent||item.id} · ${item.record?.item?.identifier||'缺陷草稿'}${item.record?.target?.project_id?' · 项目 '+item.record.target.project_id:''} · ${rows.get(item.id)?.querySelector('.rr-row-open strong')?.textContent||''} · ${item.kind==='ready'?'可执行':item.reason}`;list.append(row);}
  const cancel=confirmDialog.querySelector('[data-cancel]'),confirm=confirmDialog.querySelector('[data-confirm]'),stop=confirmDialog.querySelector('[data-stop]'),progress=confirmDialog.querySelector('.rr-batch-progress');
  cancel.onclick=()=>confirmDialog.close();stop.onclick=()=>{bridge.stopBatch();stop.disabled=true;progress.textContent='当前请求结束后停止，已成功的操作保留。'};
  confirm.disabled=!eligible.length&&!plan.some(item=>item.kind==='noop');
  if(!eligible.length&&plan.some(item=>item.kind==='noop'))confirm.textContent='清除无需变更项';
  confirm.onclick=async()=>{
   ids=reportIds(ids);
   if(!ids.length){confirmDialog.close();update();return;}
   const reason=confirmDialog.querySelector('textarea')?.value.trim()||'';
   if(needsReason&&!reason){progress.textContent='请填写操作原因或更正依据';confirmDialog.querySelector('textarea').focus();return;}
   confirm.disabled=cancel.disabled=true;confirmDialog.dataset.submitting='true';stop.hidden=true;progress.textContent='正在保存后台任务…';
   try{await bridge.runBatch(ids,action,reason,()=>{},versions);confirmDialog.close();}
   catch(error){progress.textContent=error.message;}
   finally{delete confirmDialog.dataset.submitting;confirm.disabled=cancel.disabled=false;stop.hidden=true;update();}
  };
  confirmDialog.showModal();
 }
 const groups=[['缺陷处理',['accept','reopen','__submit__','pending_regression','deferred','rejected','restore']],['同步维护',['retry-content','refresh']],['内容编辑',['titles']],['人工更正（需填写依据）',['regression_passed','regression_failed']]];
 const sync=()=>{
  const ids=chosen(),busy=bridge.isSending();actions.hidden=!ids.length;hint.hidden=!!ids.length;clear.hidden=!ids.length;clear.disabled=busy;retry.disabled=busy;
  $('rr-search').disabled=busy;$('rr-filter').disabled=busy;$('rr-refresh').disabled=busy;
  for(const button of document.querySelectorAll('[data-quick-filter]'))button.disabled=busy;
  primary=['accept','reopen','__submit__'].find(action=>ids.length&&ids.every(id=>bridge.eligibility(id,action).kind==='ready'))||'';
  save.hidden=!primary;save.disabled=busy;save.textContent=primary?`${batchLabels[primary]}（${ids.length}）`:'';
  picker.innerHTML='<option value="">'+(primary?'更多操作':'批量操作')+'</option>';
  for(const [label,values]of groups){const group=document.createElement('optgroup');group.label=label;for(const action of values){if(action==='titles'&&!$('rr-title-batch-open'))continue;const option=document.createElement('option');option.value=action;const count=action==='titles'?ids.length:ids.filter(id=>bridge.eligibility(id,action).kind!=='skip').length;option.textContent=`${batchLabels[action]||'修改标题属性'}（${count}）`;option.disabled=!count;group.append(option)}picker.append(group);}
  picker.disabled=busy;root.ReportSelects?.sync?.(actions);
 };
 save.onclick=()=>launch(primary);picker.onchange=()=>{const action=picker.value;if(action)launch(action);picker.value='';root.ReportSelects?.sync?.(actions)};
 syncBatchStatus=sync;root.ReportSelects?.upgrade(actions);sync();
 const shortcuts=document.createElement('div');shortcuts.className='rr-quick-filters';
 for(const [value,label]of [['accept','待验收'],['reopen','待重新打开'],['issues','同步异常']]){const button=document.createElement('button');button.type='button';button.dataset.quickFilter=value;button.textContent=label;button.setAttribute('aria-pressed','false');button.onclick=()=>{if(bridge.isSending())return;bridge.clearSelection();quickFilter=quickFilter===value?'':value;filter='all';update()};shortcuts.append(button)}
 shell.querySelector('.rr-inbox-tools').append(shortcuts);
}
const copyButton=document.createElement('button');copyButton.type='button';copyButton.textContent='复制描述';
document.querySelector('.rr-editor-heading>div').prepend(copyButton);
copyButton.onclick=async()=>{
 const entry=entries.find(e=>e.id===selected);if(!entry)return;
 const text=access?entry.field.value:bridge.content()||entry.field.value;
 let copied=false;try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text);copied=true}}catch{}
 if(!copied){const helper=document.createElement('textarea');helper.value=text;helper.style.cssText='position:fixed;opacity:0;left:0;top:0';(detailDialog.open?detailDialog:document.body).append(helper);helper.select();try{copied=document.execCommand('copy')}finally{helper.remove()}}
 copyButton.textContent=copied?'已复制':'复制失败';setTimeout(()=>copyButton.textContent='复制描述',2000);
};
function update(){
 const q=$('rr-search').value.toLowerCase(),counts={all:0,result_corrected:0,pending_submission:0,submitted:0,rejected:0,deferred:0,pending_regression:0,regression_passed:0,regression_failed:0,check:0};visible=[];
 for(const entry of entries){
  const record=bridge?.records.get(entry.id),group=findingGroup(entry,record),row=rows.get(entry.id);
  const inScope=reportFinding(entry,record);
  if(data.uiExecution&&entry.article)entry.article.hidden=!inScope;
  if(!inScope){const box=bridge?.selections.get(entry.id);if(box)box.checked=false;}
  if(inScope){counts.all++;counts[group]=(counts[group]||0)+1;}
  const corrected=cases.find(c=>c.case_id===entry.article?.dataset.caseId)?.defect_title;
  const title=displayTitle(bridge?.edits.get(entry.id)?.title||corrected||(record?.status==='submitted'?record.payload?.title:'')||entry.title);
  row.querySelector('.rr-row-open strong').textContent=title;
  row.hidden=!(inScope&&(title+' '+row.querySelector('.rr-case-id').textContent).toLowerCase().includes(q)&&(filter==='all'||filter===group)&&matchesQuick(record));if(!row.hidden)visible.push(entry);
  row.classList.toggle('processing',!!bridge?.isBusy(entry.id));row.classList.toggle('selected',entry.id===selected);row.classList.toggle('checked',!!bridge?.selections.get(entry.id)?.checked);
  const remote=row.querySelector('.rr-row-sync'),sync=record?.remote_sync;
  remote.textContent=sync&&['pending','unknown'].includes(sync.status)?'PingCode · 同步结果待核对':sync?.status==='failed'?'PingCode · 同步失败，可重试':record?.remote_state?'PingCode · '+(record.remote_state.name||'已同步'):group==='regression_passed'&&record?.item?'PingCode · 待同步验收':group==='regression_failed'&&record?.lineage&&record?.item?'PingCode · 待重新打开':'';remote.hidden=!remote.textContent;
  const state=row.querySelector('.rr-row-state');state.className='rr-row-state '+group;
  const currentCase=cases.find(c=>c.case_id===entry.article?.dataset.caseId);
  state.title=currentCase?'当前用例结果：'+(labels[statusKey(currentCase.status)]||currentCase.status):'';
  state.textContent=access?'只读':bridge?.isBusy(entry.id)?'后台处理中':record?.status==='loading'?'读取状态中':record?.status==='unavailable'?'读取失败，需刷新':group==='check'?'待核对':group==='result_corrected'&&currentCase?'当前'+(labels[statusKey(currentCase.status)]||currentCase.status):record?.status==='failed'&&group==='pending_submission'?'提交失败，可重试':lifecycleLabels[group]||'待提交';
  const reason=row.querySelector('.rr-row-reason');reason.hidden=group!=='rejected';reason.textContent=group==='rejected'?'拒绝原因：'+(record?.triage_reason||'未记录'):'';
  const link=row.querySelector('.rr-row-link');link.textContent=record?.item?.identifier||'缺陷草稿';
  if(record?.item?.url&&/^https?:\/\//i.test(record.item.url)){const a=document.createElement('a');a.href=record.item.url;a.rel='noopener';a.target='_blank';a.textContent=record.item.identifier+' ↗';link.replaceChildren(a);}
 }
 if(data.uiExecution){
  const current=entries.filter(e=>currentFinding(e,bridge?.records.get(e.id))).length;
  shell.querySelector('[data-rr-tab="review"] span').textContent=counts.all;
  let note=$('rr-count-basis');if(!note){note=document.createElement('p');note.id='rr-count-basis';note.className='rr-list-note';$('rr-review').before(note)}
  note.textContent=`当前缺陷 ${current} 条，另有 ${counts.all-current} 条回归记录。用例统计以当前判定为准；回归记录不重复计入当前缺陷。`;
 }
 for(const option of document.querySelectorAll('#rr-filter-menu [data-filter-value]')){const key=option.dataset.filterValue;option.querySelector('b').textContent=counts[key];option.setAttribute('aria-selected',String(key===filter));}
 const filterLabel=filter==='all'?'全部状态':lifecycleLabels[filter],filterCount=counts[filter];
 $('rr-filter').querySelector('span').textContent=filterLabel;$('rr-filter').querySelector('b').textContent=filterCount;$('rr-filter').setAttribute('aria-label',`按缺陷处理状态筛选，当前${filterLabel}，${filterCount}条`);
 const selectedEntry=entries.find(entry=>entry.id===selected);
 if(selectedEntry&&!reportFinding(selectedEntry,bridge?.records.get(selected))){
  selected=null;if(detailDialog.open)detailDialog.close();reviewSide.hidden=true;
 }
 const selectedRecord=bridge?.records.get(selected),decision=$('rr-decision-reason');decision.hidden=recordGroup(selectedRecord)!=='rejected';decision.querySelector('p').textContent=decision.hidden?'':selectedRecord?.triage_reason||'未记录拒绝原因';
 bridge?.setSelectionScope?.(visible.map(entry=>entry.id));
 for(const button of document.querySelectorAll('[data-quick-filter]'))button.setAttribute('aria-pressed',String(button.dataset.quickFilter===quickFilter));
 syncBatchStatus();
 syncBatchTitles();
 $('rr-empty-list').hidden=!!visible.length;$('rr-empty-list').textContent=quickFilter==='accept'?'当前待验收项已全部处理，可切换筛选查看已验收记录。':'没有匹配的缺陷。';
 let outside=$('rr-outside-filter');if(!outside){outside=document.createElement('p');outside.id='rr-outside-filter';$('rr-review-dock').before(outside)}outside.hidden=!selected||visible.some(entry=>entry.id===selected);outside.textContent='当前查看的记录不再属于此筛选，详情仍保留。';
 const index=visible.findIndex(e=>e.id===selected);$('rr-prev').disabled=index<=0;$('rr-next').disabled=index<0||index>=visible.length-1;
}
function showDefectAnalysis(entry){
 $('rr-defect-analysis')?.remove();
 const caseId=entry?.article?.dataset.caseId||entry?.article?.querySelector('.case-top code')?.textContent||'';
 const analysis=createAnalysisCallout(document,caseId?cases.find(c=>c.case_id===caseId):null);
 if(analysis){analysis.id='rr-defect-analysis';$('rr-review-dock').prepend(analysis);}
}
function select(id,reveal=true){
 if(bridge?.isSending())return;
 const entry=entries.find(e=>e.id===id);
 if(!entry||!reportFinding(entry,bridge?.records.get(id)))return;
 selected=id;reviewSide.hidden=false;update();
 $('rr-review-dock').scrollTop=0;
 if(reveal&&!detailDialog.open)reviewSide.scrollIntoView({block:'nearest'});
 if(!access){bridge.open(id);showDefectAnalysis(entry);showEvidence(entry);return;}
 const dock=$('rr-review-dock');dock.innerHTML=`<div class="rr-readonly"><span class="rr-readonly-note">${access==='login-required'?'登录任意平台账号后可协作修改和审核提交':'当前账号仅可查看报告'}</span><h3>${esc(entry.title)}</h3>${entry.parts.filter(p=>p.name!=='标题').map(p=>`<div class="rr-readonly-field"><h4>${esc(p.name)}</h4><pre>${esc(p.value)}</pre></div>`).join('')}</div>`;
 showDefectAnalysis(entry);showEvidence(entry);
}
function editorReady(){
 const field=$('pc-description'),single=$('pc-single');if(!field||!single||single.hidden)return;
 $('rr-fields')?.remove();
 const parts=sections(field.value).filter(p=>p.name!=='标题');
 // Keep API-specific evidence and free-form sections rather than guessing missing fields.
 const group=document.createElement('div');group.id='rr-fields';
 for(const part of parts){const label=document.createElement('label');label.textContent=part.name;const input=document.createElement('textarea');input.value=part.value;input.rows=3;input.setAttribute('aria-label',part.name);input.oninput=()=>{fitEditorFields();part.value=input.value;field.value=serialize(parts);field.dispatchEvent(new Event('input',{bubbles:true}));};label.append(input);group.append(label);}
 field.parentElement.hidden=true;field.parentElement.after(group);
 fitEditorFields();
 if(!$('rr-draft-save')){const save=document.createElement('button');save.id='rr-draft-save';save.type='button';save.className='pc-secondary';save.textContent='暂存草稿';save.onclick=bridge.save;$('pc-submit').before(save);}
}
function tab(name){
 if(bridge?.isSending())return;
 for(const button of shell.querySelectorAll('[data-rr-tab]'))button.setAttribute('aria-selected',String(button.dataset.rrTab===name));
 if(name==='review'){filter='all';quickFilter='';bridge?.clearSelection?.();update();if(visible.length)select(visible[0].id,false);}
 $('rr-review').hidden=name!=='review';$('rr-cases').hidden=name!=='cases';$('rr-data').hidden=name!=='data';original.hidden=name!=='evidence';
 if(name==='cases')renderCases();if(name==='data')renderData();
}
function filteredCases(){
 const query=$('rr-case-search').value.toLowerCase(),status=$('rr-case-filter').value;
 const priority=$('rr-case-priority-filter').value,executor=$('rr-case-executor-filter').value;
 return cases.filter(c=>(!priority||casePriority(c.priority)===priority)&&(!executor||caseExecutor(c.executor)===executor)&&(status==='all'||statusKey(c.status)===status)&&[c.case_id,c.display_case_id,c.scenario,c.module,c.executor,c.source_report?.session_title,c.scope_label].join(' ').toLowerCase().includes(query)&&(!root.ReportRetest||root.ReportRetest.matchesFilter(c)));
}
function actionContextMarkup(action){
 const context=action.context||{};
 if(action.type!=='manual_step'&&!Object.keys(context).length)return '';
 let pageUrl='';
 try{const url=new URL(context.page_url);if(['http:','https:'].includes(url.protocol)&&!url.username&&!url.password)pageUrl=url.href;}catch{}
 const rows=[['page_title','操作页面'],['step','暂停步骤'],['object','操作对象'],['browser','原浏览器'],['tab_id','原标签'],['success_condition','完成后应看到'],['resume_hint','返回现场']].filter(([key])=>context[key]);
 return `<div class="rr-action-context">${pageUrl?`<a class="rr-action-page" href="${esc(pageUrl)}" target="_blank" rel="noopener noreferrer">打开待操作页面 ↗</a>`:''}${rows.map(([key,label])=>`<p><strong>${label}：</strong>${esc(context[key])}</p>`).join('')}${!pageUrl&&!context.tab_id?'<p class="rr-action-missing">这条记录尚未保存操作页面或原标签，请补充实际现场后继续。</p>':'<p>优先在保留的原标签完成操作；打开链接不会自动继承原浏览器的登录状态。完成后保存确认，再勾选发起补测；执行端核对成功状态后接着执行。</p>'}</div>`;
}
function renderCases(resetPage=false){
 if(resetPage)page=0;
 const filtered=filteredCases();
 page=Math.max(0,Math.min(page,Math.ceil(filtered.length/25)-1));
 $('rr-case-count').textContent=`${filtered.length} / ${cases.length} 条`;
 $('rr-case-rows').innerHTML=filtered.slice(page*25,page*25+25).map(c=>{const index=cases.indexOf(c),action=caseAction(c),resultText=notRunReason(c)?'本轮未执行原因：'+notRunReason(c):c.evidence||'未记录';return `<tr><td>${data.retestBase&&!c.policy_excluded&&c.execution_disposition!=='multi_account_excluded'&&statusKey(c.status)!=='passed'?`<input type="checkbox" data-retest-select="${esc(c.case_id)}" aria-label="选择补测 ${esc(c.case_id)}"> `:''}${esc(c.display_case_id||c.case_id)}${data.aggregate?`<small>${esc(c.source_report?.session_title||'')} · ${esc(c.scope_label||'')}</small>`:''}</td><td>${esc(c.scenario)}</td><td><span class="rr-priority ${/^P[0-3]$/.test(casePriority(c.priority))?casePriority(c.priority).toLowerCase():'unset'}">${esc(casePriority(c.priority))}</span></td><td>${esc(c.module||'—')}</td><td>${esc(c.executor||'—')}</td><td><span class="rr-status ${esc(statusKey(c.status))}">${esc(c.execution_disposition==='multi_account_excluded'?'不测':labels[statusKey(c.status)]||c.result||'其他')}</span></td>${data.retestBase?`<td data-retest-state="${esc(c.case_id)}">${root.ReportRetest?.caseDataMarkup(c)||(statusKey(c.status)!=='passed'?'读取中…':'无需补充')}</td>`:''}<td>${esc(resultText.slice(0,180))}${action?`<div class="rr-required-action"><strong>需要你操作：</strong>${esc(action.prompt)}${actionContextMarkup(action)}</div>`:''}</td><td><div class="rr-case-actions">${action&&data.actionBase?`<button class="rr-action-confirm" type="button" data-case-action-index="${index}">${root.ReportRetest?.actionLabel(c)||(action.type==='authorization'?'确认授权':'确认已完成操作')}</button>`:''}${data.retestBase&&!c.policy_excluded&&c.execution_disposition!=='multi_account_excluded'&&statusKey(c.status)!=='passed'?`<button type="button" data-retest-index="${index}">补充测试数据</button>`:''}${statusKey(c.status)==='pending_rule'&&data.ruleBase?`<button class="rr-action-confirm" type="button" data-case-index="${index}">填写规则结论</button>`:''}<button type="button" data-case-index="${index}">详情</button></div></td></tr>`;}).join('')||`<tr><td colspan="${data.retestBase?9:8}" class="rr-empty">没有匹配的用例。</td></tr>`;
 $('rr-case-page').textContent=`${page+1} / ${Math.max(1,Math.ceil(filtered.length/25))}`;
 $('rr-case-prev').disabled=page===0;$('rr-case-next').disabled=(page+1)*25>=filtered.length;
 root.ReportRetest?.decorateRows();
}
for(const button of shell.querySelectorAll('[data-rr-tab]'))button.onclick=()=>tab(button.dataset.rrTab);
$('rr-stats').onclick=event=>{
 const button=event.target.closest('[data-rr-stat]');if(!button||bridge?.isSending())return;
 $('rr-case-search').value='';$('rr-case-filter').value=button.dataset.rrStat==='total'?'all':button.dataset.rrStat;
 $('rr-case-priority-filter').value='';$('rr-case-executor-filter').value='';
 root.ReportSelects?.sync(shell.querySelector('.rr-case-tools'));
 $('rr-case-filter').dispatchEvent(new Event('change',{bubbles:true}));
 page=0;tab('cases');$('rr-cases').scrollIntoView({block:'start'});
};
$('rr-filter-picker').hidden=!!access;$('rr-status-help').hidden=!!access;
const filterMenu=$('rr-filter-menu'),filterPicker=$('rr-filter-picker'),filterOptions=Array.from(filterMenu.querySelectorAll('[data-filter-value]'));
const closeFilter=focus=>{filterMenu.hidden=true;$('rr-filter').setAttribute('aria-expanded','false');if(focus)$('rr-filter').focus()};
const openFilter=()=>{filterMenu.hidden=false;$('rr-filter').setAttribute('aria-expanded','true');(filterOptions.find(option=>option.dataset.filterValue===filter)||filterOptions[0]).focus()};
$('rr-filter').onclick=()=>filterMenu.hidden?openFilter():closeFilter(false);
for(const option of filterOptions)option.onclick=()=>{if(bridge?.isSending())return;bridge?.clearSelection?.();quickFilter='';filter=option.dataset.filterValue;closeFilter(true);update()};
filterPicker.addEventListener('keydown',event=>{
 if(event.key==='Escape'){event.preventDefault();closeFilter(true);return}
 if(event.target===$('rr-filter')&&['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();openFilter();return}
 if(!filterOptions.includes(event.target))return;
 const index=filterOptions.indexOf(event.target);
 if(event.key==='ArrowDown'){event.preventDefault();filterOptions[(index+1)%filterOptions.length].focus()}
 if(event.key==='ArrowUp'){event.preventDefault();filterOptions[(index-1+filterOptions.length)%filterOptions.length].focus()}
 if(event.key==='Home'){event.preventDefault();filterOptions[0].focus()}
 if(event.key==='End'){event.preventDefault();filterOptions.at(-1).focus()}
});
document.addEventListener('click',event=>{if(!filterPicker.contains(event.target))closeFilter(false)});
$('rr-search').oninput=()=>{bridge?.clearSelection?.();update()};
$('rr-prev').onclick=()=>{const i=visible.findIndex(e=>e.id===selected);if(i>0)select(visible[i-1].id)};
$('rr-next').onclick=()=>{const i=visible.findIndex(e=>e.id===selected);if(i>=0&&i+1<visible.length)select(visible[i+1].id)};
$('rr-refresh').hidden=!!access&&data.reportType!=='total';
if(data.reportType==='total')$('rr-refresh').textContent='刷新报告';
$('rr-refresh').onclick=async()=>{if(data.reportType==='total'){location.reload();return;}const button=$('rr-refresh');button.disabled=true;try{await bridge.refresh()}finally{button.disabled=false}};
$('rr-case-search').oninput=$('rr-case-filter').onchange=$('rr-case-priority-filter').onchange=$('rr-case-executor-filter').onchange=()=>{page=0;renderCases()};
$('rr-case-prev').onclick=()=>{page--;renderCases()};$('rr-case-next').onclick=()=>{page++;renderCases()};
$('rr-case-rows').onclick=event=>{
 const actionButton=event.target.closest('[data-case-action-index]');
 if(actionButton){confirmCaseAction(actionButton,cases[Number(actionButton.dataset.caseActionIndex)]);return;}
 const button=event.target.closest('[data-case-index]');if(!button)return;const c=cases[Number(button.dataset.caseIndex)];
 if(c.node){tab('evidence');c.node.classList.remove('hidden');c.node.querySelector('details').open=true;c.node.scrollIntoView({block:'start'});return;}
 let detail=$('rr-case-dialog');if(!detail){detail=document.createElement('dialog');detail.id='rr-case-dialog';detail.className='rr-case-dialog';document.body.append(detail);}
 showCaseDetail(detail,c);
 detail.showModal();
};
const correctionFields=[['scenario','用例名称'],['module','模块'],['executor','执行方式'],['precondition','前置条件'],['test_data','测试数据'],['steps','测试步骤'],['expected','预期结果'],['evidence','实际结果'],['conclusion','测试结论'],['not_run_reason','本轮未执行原因']];
const correctionStatuses=['passed','failed','partial','blocked','not_run','pending_rule','pending_action'];
function observationMarkup(value){
 const text=String(value||'').trim(),excerpt=observationExcerpt(text);
 if(!text)return '<p class="rr-observation-empty">尚未记录实际观察。</p>';
 return `<p class="rr-observation-summary">${esc(excerpt)}</p>${text!==excerpt?`<details class="rr-observation-raw"><summary>展开完整观察记录</summary><pre>${esc(text)}</pre></details>`:''}`;
}
function actualResultsMarkup(c){
 // Manual corrections take precedence over the original checkpoint wording.
 const points=c.observations_corrected_at?[]:(c.checkpoints||[]);
 if(!points.length)return observationMarkup(c.rawEvidence||c.evidence||c.actual);
 return `<div class="rr-observation-list">${points.map((point,index)=>`<section class="rr-observation-point"><div class="rr-observation-heading"><h4>${index+1}. ${esc(point.title||'检查点')}</h4><span class="rr-status ${esc(statusKey(point.status))}">${esc(labels[statusKey(point.status)]||'其他')}</span></div>${point.expected?`<div class="rr-observation-expected"><strong>预期</strong><p>${esc(point.expected)}</p></div>`:''}<div class="rr-observation-actual"><strong>实际观察${String(point.actual||'').includes('\n')||String(point.actual||'').length>280?'（摘要）':''}</strong>${observationMarkup(point.actual)}</div></section>`).join('')}</div>`;
}
function stepQualityIssue(c){
 if(c.steps_issue)return c.steps_issue;
 const steps=String(c.steps||'').trim(),pre=String(c.precondition||''),dataText=String(c.test_data||'');
 if(!steps)return '未记录测试步骤';
 const gaps=[];
 if(/https?:\/\//i.test(pre)&&! /https?:\/\//i.test(steps))gaps.push('步骤未写真实入口 URL；开发无法确认从哪个页面开始');
 if(/(?:沿用|当前|已有|保持).{0,12}(?:已登录|登录账号|登录态|会话)|当前测试账号已登录/i.test(pre)&&!/(?:确认|检查|核对|验证).{0,20}(?:登录|账号|用户名|头像|账户|会话)/i.test(steps))gaps.push('前置条件提到已登录账号，但步骤未写如何确认登录账号或登录状态');
 if(!/(?:点击|单击|打开|进入|切换|选择|勾选|取消|清空|输入|上传|下载|刷新|展开|关闭|发送|提交|保存|删除|返回)/i.test(steps))gaps.push('步骤未写具体控件动作');
 if(!/(?:等待|显示|看到|核对|检查|观察|提示|保持|变为|出现|消失|字段|列表|弹窗|页面|结果|状态|内容)/i.test(steps))gaps.push('步骤未写等待完成条件和观察位置');
 if(/选择[^\n。；]{0,30}刷新检查|刷新检查当前值|核对相关结果|沿用已登录账号/.test(steps))gaps.push('步骤把多个动作合并成一句，需拆成选择、等待/刷新、核对三步并写明对象和观察位置');
 if(dataText&&/2\.pdf|文件|简历|对象|输入/i.test(dataText)&&!/(2\.pdf|文件|简历|对象|输入)/i.test(steps))gaps.push('测试数据未在步骤中明确指出实际对象或输入值');
 return [...new Set(gaps)].join('；');
}
function showCaseDetail(detail,c){
 detail.ruleCase=c;
 detail.innerHTML=`<button class="rr-case-close" type="button" aria-label="关闭用例详情">×</button><h2>${esc((c.display_case_id||c.case_id)+' · '+c.scenario)}</h2>${c.ai_analysis&&!c.wording_corrected_at?`<section class="rr-case-analysis" aria-label="AI 解读"><strong>AI 解读</strong><p>${esc(c.ai_analysis)}</p></section>`:''}${c.source_report?`<p class="rr-case-source">结果来源：<a href="${esc(c.source_report.report_url)}">${esc(c.source_report.title)}</a>${data.aggregate?` · ${esc(c.scope_label)} · <a href="${esc(c.source_report.report_url)}">进入来源报告补测 / 查看原始执行证据</a>`:''}</p>`:''}<p class="rr-case-priority">优先级：${esc(casePriority(c.priority))}</p><h3>执行结果</h3><div class="rr-case-outcome"><span class="rr-status ${esc(statusKey(c.status))}">${esc(c.execution_disposition==='multi_account_excluded'?'不测':labels[statusKey(c.status)]||c.result||'其他')}</span>${c.conclusion?`<p>${esc(c.conclusion)}</p>`:''}</div>${[['executor','执行方式'],['precondition','前置条件'],['test_data','测试数据'],['steps','测试步骤'],['expected','预期结果']].map(([key,label])=>`<h3>${label}</h3><pre>${esc(c[key]||'未填写')}</pre>${key==='steps'&&stepQualityIssue(c)?`<p class=\"rr-steps-warning\"><strong>步骤待补充：</strong>${esc(stepQualityIssue(c))}</p>`:''}`).join('')}<h3>实际结果</h3>${actualResultsMarkup(c)}`;
 if(data.uiExecution)detail.insertAdjacentHTML('beforeend',relatedDataMarkup(c.case_id));
 const action=caseAction(c);
 if(action){
  const section=document.createElement('section');section.className='rr-required-action';
  section.innerHTML=`<strong>需要你操作：</strong><p>${esc(action.prompt)}</p>${actionContextMarkup(action)}`;
  if(data.actionBase){const button=document.createElement('button');button.type='button';button.className='rr-action-confirm';button.textContent=root.ReportRetest?.actionLabel(c)||(action.type==='authorization'?'确认授权':'确认已完成操作');button.disabled=!!root.ReportRetest?.actionConfirmed(c);button.onclick=()=>confirmCaseAction(button,c);section.append(button);}
  detail.querySelector('.rr-case-outcome').after(section);
 }
 if(notRunReason(c))detail.insertAdjacentHTML('beforeend',`<h3>本轮未执行原因</h3><pre>${esc(notRunReason(c))}</pre>`);
 if(data.correctionBase&&data.uiExecution&&(!data.aggregate||c.source_report?.editable)){const edit=document.createElement('button');edit.type='button';edit.className='rr-case-edit';edit.textContent='修正用例';edit.onclick=()=>showCaseEditor(detail,c);detail.append(edit);}
 detail.querySelector('.rr-case-close').onclick=()=>detail.close();
 root.ReportRules?.attach(detail,c);
 root.ReportRetest?.attach(detail,c);
}
function showCaseEditor(detail,c){
 const current=statusKey(c.status),choices=correctionStatuses.includes(current)?correctionStatuses:[...correctionStatuses,current];
 detail.innerHTML=`<button class="rr-case-close" type="button" aria-label="关闭用例详情">×</button><h2>修正 ${esc(c.display_case_id||c.case_id)}</h2><p class="rr-correction-note">人工修正会更新报告与导出；原始执行记录和证据保留，不代表重新测试。</p><form id="rr-case-edit-form"><label>执行结果<select name="status">${choices.map(key=>`<option value="${key}" ${key===current?'selected':''}>${esc(labels[key]||key)}</option>`).join('')}</select></label>${correctionFields.map(([key,label])=>`<label>${label}${['scenario','module','executor'].includes(key)?`<input name="${key}" value="${esc(c[key]||'')}">`:`<textarea name="${key}" rows="4">${esc(c[key]||'')}</textarea>`}</label>`).join('')}<p class="rr-case-edit-error" role="alert" hidden></p><div class="rr-case-edit-actions"><button type="button" class="rr-case-edit-cancel">取消</button><button type="submit">保存更正</button></div></form>`;
 root.ReportSelects?.upgrade(detail);
 detail.querySelector('.rr-case-close').onclick=()=>detail.close();
 detail.querySelector('.rr-case-edit-cancel').onclick=()=>showCaseDetail(detail,c);
 detail.querySelector('form').onsubmit=async event=>{
  event.preventDefault();const form=event.currentTarget,save=form.querySelector('[type="submit"]'),errorNode=form.querySelector('.rr-case-edit-error');
  save.disabled=true;errorNode.hidden=true;
  try{
   if(!actionCsrf){const bootstrap=await fetch('/api/bootstrap');if(!bootstrap.ok)throw Error('会话已失效，请重新登录');actionCsrf=(await bootstrap.json()).csrf;}
   const fields=Object.fromEntries(new FormData(form));
   const response=await fetch(`${data.correctionBase}/${encodeURIComponent(c.case_id)}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':actionCsrf,...(root.ReportAggregateHeaders?.()||{})},body:JSON.stringify({fields,revision:data.reportType==='total'?c.source_report.correction_revision:correctionRevision,source_report:c.source_report})});
   let result={};try{result=await response.json()}catch{}
   if(!response.ok)throw Error(result.detail||'无法保存用例说明');
   // Reload the effective report so its printable body and online view agree.
   location.reload();return;
  }catch(error){errorNode.textContent=error.message;errorNode.hidden=false;save.disabled=false;}
 };
}
let actionCsrf='';
async function confirmCaseAction(button,c){
 const action=caseAction(c);if(!action||!data.actionBase||root.ReportRetest?.actionConfirmed(c))return;
 button.disabled=true;const original=button.textContent;button.textContent='正在保存确认…';
 try{
  if(!actionCsrf){const bootstrap=await fetch('/api/bootstrap');if(!bootstrap.ok)throw Error('会话已失效，请重新登录');actionCsrf=(await bootstrap.json()).csrf;}
  const response=await fetch(`${data.actionBase}/${encodeURIComponent(c.case_id)}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':actionCsrf,...(root.ReportAggregateHeaders?.()||{})},body:JSON.stringify({decision:action.type==='authorization'?'authorized':'completed',expected_action:action,source_report:c.source_report,save_only:true})});
  let result={};try{result=await response.json()}catch{}
  if(!response.ok)throw Error(result.detail||'无法保存确认状态');
  button.textContent='已确认，待统一补测';button.disabled=true;
  if(root.ReportRetest)await root.ReportRetest.refresh();
  const detail=button.closest('dialog');if(detail?.open)showCaseDetail(detail,c);
 }catch(error){button.disabled=false;button.textContent=original;window.alert(error.message);}
}
function titlesSaved(source,result){
 if(data.correctionBase===source+'/case-corrections'){correctionRevision=result.revision;data.correctionRevision=result.revision;}
 for(const c of cases)if(c.source_report&&source===`/api/projects/${c.source_report.project_id}/reports/${c.source_report.id}`)c.source_report.correction_revision=result.revision;
}
root.ReportReview={backgroundJobs:jobs=>showBackgroundJobs(jobs),batchConnection:ok=>showBatchConnection(ok),batchResult:result=>showBatchResult(result),update,editorReady,displayTitle,data,cases,filteredCases,renderCases,showCaseDetail,titlesSaved,refreshEvidence:()=>{const entry=entries.find(item=>item.id===selected);if(entry)showEvidence(entry)}};update();
update();if(visible.length)select(visible[0].id,false);
if(root.ReportFirstPaint)root.ReportFirstPaint.complete();
else{
 for(const id of ['rr-first-paint','rr-first-paint-fallback'])$(id)?.remove();
 document.body.classList.remove('rr-pending');
}
}catch(error){
 if(document.body.classList.contains('rr-pending')){
  // Keep references even if construction failed before the new shell mounted.
  for(const node of originalNodes)document.body.append(node);
  document.querySelector('[data-rr-enhanced]')?.remove();
  const status=$('rr-first-paint-status');
  if(status)status.textContent='报告交互视图未能载入，请展开下方报告正文查看结果与证据。';
  $('rr-first-paint')?.setAttribute('aria-busy','false');
 }
 root.ReportFirstPaint?.failed();
 throw error;
}
})(globalThis);
