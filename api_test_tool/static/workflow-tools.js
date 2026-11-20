/* Session case sources, a real chain preview/editor, and opt-in load testing. */
let chainDraft=null, chainRevision=null, chainOriginal=null, chainDemo=false;
const loadDrafts=new Map();
const workflowModes={own:['执行自己的用例','导入 → 核对 → 执行'],ai:['直接 AI 生成','接口文档 → AI 设计 → 核对'],import_ai:['导入后 AI 补充','保留原用例，让 AI 查漏补缺'],ai_import:['AI 生成后自己补充','AI 设计 → 导入或手动追加自己的用例']};
function sourceActions(){
 const mode=state.project?.case_workflow||'ai',cases=state.bundle?.cases||[];
 const hasUser=cases.some(c=>c.web?.source==='user');
 const hasGenerated=cases.some(c=>['ai','rules'].includes(c.web?.source));
 return {mode,hasUser,hasGenerated,import:mode==='own'||mode==='import_ai'||mode==='ai_import'&&hasGenerated,
  manual:mode==='own'||mode==='ai_import'&&hasGenerated,awaitingImport:mode==='import_ai'&&!hasUser};
}
function renderSourcePanel(){
 const actions=sourceActions(),mode=actions.mode;
 const hint=mode==='own'?'导入或手动添加自己的用例，核对后执行，不新增 AI 用例。':mode==='import_ai'?(actions.hasUser?'已导入自己的用例。下一步让 AI 查漏补缺，保留原内容与核对状态。':'第一步：导入自己的用例。导入完成后显示 AI 补充入口。'):mode==='ai_import'?(actions.hasGenerated?'已生成用例。现在可以导入或手动追加自己的用例，再核对执行。':'第一步：生成用例。生成完成后显示导入和手动补充入口。'):'使用 Codex 或配置的模型设计用例，核对后执行。需要追加自己的用例时，请选择「AI 生成后自己补充」。';
 const buttons=[actions.import?`<button data-wf="import" ${busy()?'disabled':''}>${mode==='ai_import'?'导入补充用例':'导入自己的用例'}</button>`:'',actions.manual?`<button data-wf="new-case" ${busy()?'disabled':''}>＋ ${mode==='own'?'手动添加用例':'手动补充用例'}</button>`:'',state.bundle?'<button data-wf="export-cases">导出可导入 JSON</button>':''].join('');
 return `<div class="panel"><div class="panel-heading"><h2>本次用例从哪里来</h2></div><div class="source-options">${Object.entries(workflowModes).map(([id,[title,description]])=>`<button class="source-option ${mode===id?'selected':''}" data-wf="source" data-value="${id}" aria-pressed="${mode===id}" ${busy()?'disabled':''}><strong>${esc(title)}</strong><small>${esc(description)}</small></button>`).join('')}</div><p class="hint">${hint} 切换方式会保留当前用例。</p>${buttons?`<div class="workflow-actions">${buttons}</div>`:''}</div>`;
}
function chainControl(caseItem){return `<p><span class="source-tag">${caseItem.web?.source==='user'?'用户用例':caseItem.web?.source==='ai'?'AI 用例':caseItem.web?.source==='rules'?'规则用例':'已有用例'}</span> <button data-wf="chain" data-value="${esc(caseItem.id)}">编辑用例（高级） →</button> <button class="danger-text" data-wf="delete-case" data-value="${esc(caseItem.id)}" ${busy()?'disabled':''}>删除用例</button></p>`;}
function sourceGoal(){const mode=state.project?.case_workflow;return mode==='own'?'仅执行本会话已有用户用例，不新增测试设计。':mode==='import_ai'?'先读取并保留本会话已有用户用例，只追加遗漏场景，禁止覆盖用户预期。':mode==='ai_import'?'本次只生成并保存完整测试用例，不自动执行。返回网页等待用户补充自己的用例，再由用户开始执行。':'';}
function downloadCaseFile(name,text){const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url);}
function newCaseTemplate(){const [oid,op]=Object.entries(state.contract?.operations||{})[0]||[];if(!oid)throw Error('先导入接口文档或添加接口。');return{id:'USER-'+Date.now(),title:'我的测试用例',operation_id:oid,variables:{},steps:[{id:'request',title:'发送请求',operation_id:oid,request:{method:op.method,path:op.path,...(op.has_request_example?{json:op.request_example}:{})},assertions:[],extract:[]}],cleanup_steps:[],notes:'请填写明确预期；写入数据的用例需要清理步骤。'};}
function demoChain(){return{id:'CHAIN-DEMO',title:'登录 → 创建资源 → 查询 → 清理',operation_id:'create',variables:{name:{kind:'unique',prefix:'test_'}},steps:[{id:'login',title:'前置：登录并提取 Token',request:{method:'POST',path:'/login',json:{username:'测试账号',password:'示例密码'}},extract:[{name:'token',from:'json',pointer:'/token'}],assertions:[{kind:'json_exists',pointer:'/token'}]},{id:'create',title:'创建资源，保存返回的 ID',request:{method:'POST',path:'/items',headers:{Authorization:'Bearer ${token}'},json:{name:'${name}'}},extract:[{name:'item_id',from:'json',pointer:'/id'}],assertions:[{kind:'status',expected:201}]},{id:'read',title:'查询刚创建的资源',request:{method:'GET',path:'/items/${item_id}',headers:{Authorization:'Bearer ${token}'}},assertions:[{kind:'equals_variable',pointer:'/id',variable:'item_id'}]}],cleanup_steps:[{id:'delete',title:'后置：删除本次资源',request:{method:'DELETE',path:'/items/${item_id}',headers:{Authorization:'Bearer ${token}'}},assertions:[{kind:'status',expected:204}]}]};}
function chainChanges(before,after,path=[]){
 if(Object.is(before,after))return [];
 const object=x=>x!==null&&typeof x==='object';
 if(object(before)&&object(after)&&Array.isArray(before)===Array.isArray(after)){
  return [...new Set([...Object.keys(before),...Object.keys(after)])].flatMap(key=>chainChanges(before[key],after[key],[...path,key]));
 }
 return [{path,before,after}];
}
function chainChangeLabel(path){
 const names={title:'名称',id:'编号',operation_id:'关联接口',variables:'初始变量',request:'请求',method:'方法',path:'路径',json:'请求体',params:'查询参数',headers:'请求头',assertions:'断言',extract:'变量提取',cleanup_policy:'清理策略',notes:'备注'};
 return path.map(key=>key==='steps'?'步骤':key==='cleanup_steps'?'清理步骤':/^\d+$/.test(key)?String(Number(key)+1):names[key]||key).join(' → ')||'整条用例';
}
function previewChain(){
 try{
  const next=JSON.parse($('chain-json').value);
  if(!next||typeof next!=='object'||Array.isArray(next)||!Array.isArray(next.steps))throw Error('用例必须是包含 steps 步骤数组的 JSON 对象。');
  if(next.cleanup_steps!==undefined&&!Array.isArray(next.cleanup_steps))throw Error('cleanup_steps 必须是数组。');
  for(const step of [...next.steps,...(next.cleanup_steps||[])]){
   if(!step||typeof step!=='object'||Array.isArray(step))throw Error('每个步骤必须是 JSON 对象。');
   for(const field of ['assertions','extract'])if(step[field]!==undefined&&!Array.isArray(step[field]))throw Error(field+' 必须是数组。');
  }
  const changes=chainChanges(chainDraft,next);chainDraft=next;renderChain(changes);
  $('chain-preview-status').scrollIntoView?.({block:'start',behavior:'smooth'});
 }catch(error){$('chain-preview-status').innerHTML='';$('chain-error').textContent='预览失败：'+error.message;$('chain-error').scrollIntoView?.({block:'nearest'});}
}
function renderChain(changes=null){
 const c=chainDraft;$('chain-title').textContent=c.title||'业务链路';$('chain-intro').textContent=chainDemo?'交互示例：点击各步骤查看输入与变量。这里只演示关系，不发送请求、不保存到会话。':'这是本条用例真实的执行顺序。前置准备也是步骤；前一步失败时，后续业务步骤停止，已配置的清理仍会尝试执行。';
 const card=(step,index,cleanup=false)=>{const changed=changes?.some(x=>x.path[0]===(cleanup?'cleanup_steps':'steps')&&(x.path.length===1||x.path[1]===String(index))),req=step.request||{},refs=[...new Set((JSON.stringify(req).match(/\$\{[^}]+\}/g)||[]))];return `<article class="chain-node ${changed?'chain-changed':''} ${cleanup?'chain-cleanup':''}"><h3><span class="chain-number">${cleanup?'✓':index+1}</span>${esc(step.title||step.id)}${changed?'<span class="chain-change-tag">已更新</span>':''}</h3><p><code>${esc(req.method||'')} ${esc(req.path||'')}</code></p>${refs.length?`<p class="chain-transfer">使用前序变量：${refs.map(esc).join(' · ')}</p>`:''}${step.extract?.length?`<p class="chain-transfer">提取：${step.extract.map(x=>`${esc(x.from)} ${esc(x.pointer||x.key)} → <b>${esc(x.name)}</b>`).join('；')}</p>`:''}<details ${changed?'open':''}><summary>查看请求与断言</summary><pre>${esc(JSON.stringify({request:req,assertions:step.assertions||[],extract:step.extract||[]},null,2))}</pre></details>${!chainDemo&&!cleanup&&c.steps.length>1?`<div class="chain-tools"><button data-wf="move-step" data-value="${index}" data-direction="-1" ${index===0?'disabled':''}>上移</button><button data-wf="move-step" data-value="${index}" data-direction="1" ${index===c.steps.length-1?'disabled':''}>下移</button></div>`:''}</article>`;};
 $('chain-view').innerHTML=`<p class="hint">初始变量：${Object.keys(c.variables||{}).map(esc).join('、')||'无'} · 同一链路自动保留 Cookie</p><div class="chain-track">${(c.steps||[]).map((s,i)=>`${i?'<div class="chain-arrow">↓ 上一步成功后继续</div>':''}${card(s,i)}`).join('')}${(c.cleanup_steps||[]).length?'<div class="chain-arrow">↓ 后置清理：业务失败时也尝试执行</div>':''}${(c.cleanup_steps||[]).map((s,i)=>card(s,i,true)).join('')}${!c.cleanup_steps?.length?`<p class="hint">清理：${esc(c.cleanup_policy?.reason||'未配置 HTTP 清理；执行条件以测试台核对结果为准。')}</p>`:''}</div>`;
 const showValue=value=>value===undefined?'（不存在）':JSON.stringify(value,null,2);
 $('chain-preview-status').innerHTML=changes===null?'':changes.length?`<div class="chain-preview-feedback"><strong>预览已更新</strong><p>以下内容相较上次预览有变化；尚未保存，也没有发送请求。</p><ul class="chain-change-list">${changes.map(change=>`<li><strong>${esc(chainChangeLabel(change.path))}</strong><div class="chain-change-values"><div><small>修改前</small><pre>${esc(showValue(change.before))}</pre></div><div><small>修改后</small><pre>${esc(showValue(change.after))}</pre></div></div></li>`).join('')}</ul><p>变化位置见上方对照；有变化的现有步骤已标出并展开。</p></div>`:'<div class="chain-preview-feedback"><strong>没有修改</strong><p>内容与当前预览一致。修改下方用例 JSON 后，再点击「预览修改」。</p></div>';
 $('chain-editor').hidden=chainDemo;$('chain-json').value=JSON.stringify(c,null,2);$('chain-error').textContent='';
}
async function openChain(id){chainDemo=false;chainOriginal=id||null;if(id){const data=await api(`/api/projects/${state.project.id}/editable-cases`);chainDraft=data.cases.find(c=>c.id===id);chainRevision=data.revision;if(!chainDraft)throw Error('用例已不存在，请刷新。');}else{await refreshProject();chainRevision=state.bundle_revision;chainDraft=newCaseTemplate();}renderChain();$('chain-dialog').showModal();}
function loadDraft(){const id=state.project?.id;if(!loadDrafts.has(id))loadDrafts.set(id,{enabled:false,engine:state.bootstrap.jmeter?.available?'jmeter':'builtin',virtual_users:5,duration_seconds:30,ramp_up_seconds:5,think_time_ms:200,max_rounds:1000,case_ids:[]});return loadDrafts.get(id);}
function renderLoadPanel(){const d=loadDraft(),jm=d.engine==='jmeter',maxUsers=jm?(state.bootstrap.jmeter?.max_virtual_users||10000):20,disabled=busy()||state.project.experience,ready=(state.bundle?.cases||[]).filter(c=>c.state==='READY'),hasTarget=Boolean(savedTarget());return `<div class="panel"><div class="panel-heading"><h2>压测（可选）</h2><span class="quiet-tag">${jm?'Apache JMeter 5.6.3':'内置链路回放'}</span></div><label>执行引擎<select id="load-engine" ${disabled?'disabled':''}><option value="jmeter" ${jm?'selected':''} ${state.bootstrap.jmeter?.available?'':'disabled'}>Apache JMeter · 独立 Java 进程</option><option value="builtin" ${!jm?'selected':''}>内置链路回放 · 兼容已有方案</option></select></label><label class="load-toggle"><input id="load-enabled" type="checkbox" ${d.enabled?'checked':''} ${disabled?'disabled':''}> 我要额外运行压测</label><p class="hint">普通功能测试照常执行。压测会重复运行你明确选择的用例链路，每轮使用独立会话，unique 变量重新生成；固定账号和资源会按原用例重复使用。</p><div class="load-options" ${d.enabled?'':'hidden'}>${jm?`<label>升压时间 / 秒<input id="load-ramp" type="number" min="0" max="${d.duration_seconds}" value="${d.ramp_up_seconds}" ${disabled?'disabled':''}></label><p class="hint">JMeter 在升压时间内逐步启动目标用户数。此时间包含在持续时间内；每轮独立维护变量和 Cookie。</p>`:''}<div class="form-row"><label>虚拟用户数<input id="load-users" type="number" min="1" max="${maxUsers}" value="${d.virtual_users}" ${disabled?'disabled':''}></label><label>持续时长 / 秒<input id="load-duration" type="number" min="1" max="${jm?86400:300}" value="${d.duration_seconds}" ${disabled?'disabled':''}></label></div><div class="form-row"><label>每轮间隔 / 毫秒<input id="load-think" type="number" min="0" max="60000" value="${d.think_time_ms}" ${disabled?'disabled':''}></label><label>最多轮次（所有用户合计）<input id="load-rounds" type="number" min="1" max="${jm?10000000:10000}" value="${d.max_rounds}" ${disabled?'disabled':''}></label></div><p class="hint">选择压测用例，不默认选中全部。每个虚拟用户按下方用例顺序循环；用例内步骤仍按顺序执行。</p><div class="load-cases">${ready.map(c=>`<label><input type="checkbox" data-load-case="${esc(c.id)}" ${d.case_ids.includes(c.id)?'checked':''} ${disabled?'disabled':''}>${esc(c.title)} <small>${esc(c.id)}</small></label>`).join('')||'暂无可执行用例，先核对用例。'}</div><p class="hint">${jm?`由服务器上的 JMeter 执行，网页不发送压测请求。当前节点允许配置至 ${maxUsers.toLocaleString()} 个用户；这不是保证吞吐量，实际以运行结果为准。先检查前置数据、共享账号和清理方式；停止后等待在途链路清理。`:'内置引擎最多 20 个虚拟用户、300 秒、5 万次计划请求。需要更大规模时选择 JMeter。'}</p><div class="workflow-actions"><button class="primary" data-wf="start-load" ${disabled||!d.case_ids.length||!hasTarget?'disabled':''}>执行所选用例压测</button></div></div>${state.job?.kind==='load'&&busy()?'<button data-wf="stop-load">停止新增压测轮次</button>':''}${state.project.experience?'<p class="hint">可控故障演示不作为压测目标，请使用自己的测试会话。</p>':''}</div>`;}
function renderLoadResults(target='load-results'){const node=$(target);if(!node)return;const runs=state.project?.load_runs||[];node.innerHTML=runs.length?`<div class="panel"><h2>可选压测报告</h2>${runs.map(r=>`<div class="load-results-row"><div><strong>${esc(date(r.created_at))} · ${r.engine==='jmeter'?'JMeter':'内置引擎'}</strong>${r.engine_status==='failed'?'<p class="danger-text">引擎执行未完成，请查看报告原因</p>':''}<p class="hint">${r.requests_sent} 次请求 · 平均 ${r.requests_per_second} RPS · 未通过 ${(r.error_rate*100).toFixed(2)}%</p></div><div><a href="${esc(r.report_url)}">查看压测报告 →</a>${r.engine==='jmeter'?`<p><a href="/api/projects/${esc(state.project.id)}/jmeter-artifacts/${esc(r.id)}/plan.zip">下载 JMeter 计划</a> · <a href="/api/projects/${esc(state.project.id)}/jmeter-artifacts/${esc(r.id)}/samples.jtl">下载 JTL 结果</a></p>`:''}</div></div>`).join('')}</div>`:'';}
async function handleWorkflowClick(button){
 const action=button.dataset.wf;if(!action)return false;
 if(await handleManualCaseClick(button))return true;
 if(action.startsWith('close-')){$(action==='close-chain'?'chain-dialog':'case-import-dialog').close();return true;}
 if(action==='chain-demo'){chainDemo=true;chainDraft=demoChain();renderChain();$('chain-dialog').showModal();return true;}
 if(action==='source'){const result=await api(`/api/projects/${state.project.id}/case-workflow`,'PUT',{mode:button.dataset.value});Object.assign(state,result);goStage(2);scheduleMCPSync();return true;}
 if((action==='import'&&!sourceActions().import)||(action==='new-case'&&!sourceActions().manual))throw Error('当前流程尚未开放此入口，请按页面步骤操作。');
 if(action==='new-case'){await openManualCase();return true;}
 if(action==='chain'){await openChain(button.dataset.value);return true;}
 if(action==='move-step'){const i=Number(button.dataset.value),j=i+Number(button.dataset.direction);[chainDraft.steps[i],chainDraft.steps[j]]=[chainDraft.steps[j],chainDraft.steps[i]];renderChain();return true;}
 if(action==='preview-chain'){previewChain();return true;}
 if(action==='import'){await refreshProject();$('case-import-error').textContent='';$('case-import-dialog').showModal();return true;}
 if(action==='template-json'){const c=newCaseTemplate();downloadCaseFile('cases-template.json',JSON.stringify({schema_version:'1.0',cases:[c]},null,2));return true;}
 if(action==='template-csv'){const op=Object.values(state.contract.operations)[0];downloadCaseFile('cases-template.csv','\ufeffid,title,method,path,expected_status,json,params,headers,assertions\nUSER-001,请填写用例名称,'+(op?.method||'GET')+','+(op?.path||'/health')+',,,,,\n');return true;}
 if(action==='export-cases'){const data=await api(`/api/projects/${state.project.id}/editable-cases`);downloadCaseFile('cases.json',JSON.stringify({schema_version:'1.0',cases:data.cases},null,2));return true;}
 if(action==='save-import'||action==='save-chain'){
  const edit=action==='save-chain';try{const data=await api(`/api/projects/${state.project.id}/import-cases`,'POST',{filename:edit?'edited-case.json':$('case-import-name').value,content:edit?JSON.stringify({cases:[JSON.parse($('chain-json').value)]}):$('case-import-content').value,revision:edit?chainRevision:state.bundle_revision,...(edit&&chainOriginal?{replace_id:chainOriginal}:{})});Object.assign(state,data);state.bootstrap.projects=[state.project,...state.bootstrap.projects.filter(p=>p.id!==state.project.id)];$(edit?'chain-dialog':'case-import-dialog').close();state.selected.clear();goStage(2);toast(`已保存 ${data.imported_count} 条用例，核对后可执行。`);}catch(e){$(edit?'chain-error':'case-import-error').textContent=e.message;}return true;
 }
 if(action==='start-load'){const d=loadDraft();await startJob(`/api/projects/${state.project.id}/load-test`,{base_url:savedTarget(),case_ids:d.case_ids,load:d});return true;}
 if(action==='stop-load'){await api(`/api/jobs/${state.job.id}/stop-load`,'POST',{});toast('已停止新增轮次，等待在途链路与清理完成。');return true;}
 return false;
}
document.addEventListener('change',async e=>{const el=e.target;try{if(el.id==='load-project'){await loadProject(el.value);goStage(6);return;}if(el.id==='case-import-file'){const file=el.files?.[0];if(!file)return;if(file.size>4*1024*1024)throw Error('用例文件最多 4 MB');$('case-import-name').value=file.name;$('case-import-content').value=await file.text();return;}if(el.id==='load-engine'){loadDraft().engine=el.value;renderLoadWorkspace();return;}if(el.id==='load-enabled'){loadDraft().enabled=el.checked;renderLoadWorkspace();return;}const fields={'load-ramp':'ramp_up_seconds','load-users':'virtual_users','load-duration':'duration_seconds','load-think':'think_time_ms','load-rounds':'max_rounds'};if(fields[el.id])loadDraft()[fields[el.id]]=Number(el.value);if(el.dataset.loadCase){const d=loadDraft();d.case_ids=el.checked?[...new Set([...d.case_ids,el.dataset.loadCase])]:d.case_ids.filter(id=>id!==el.dataset.loadCase);renderLoadWorkspace();}}catch(error){toast(error.message,true);}});

function renderLoadWorkspace(){
 const projects=state.bootstrap.projects||[],project=state.project;
 const selector=`<div class="panel"><label>选择测试会话<select id="load-project" ${busy()?'disabled':''}><option value="" disabled ${!project?'selected':''}>请选择会话</option>${projects.map(p=>`<option value="${esc(p.id)}" ${p.id===project?.id?'selected':''}>${esc(p.title)} · ${esc(date(p.updated_at))}</option>`).join('')}</select></label><p class="hint">这里使用该会话已经保存的用例，包括 Codex 生成的用例。不会重复生成，也不会自动开始压测。</p></div>`;
 if(!project){$('load-management').innerHTML=selector+empty('先选择一个测试会话','没有会话时，先导入接口文档并准备用例。','导入接口文档',1);return;}
 const d=loadDraft(),ready=new Set((state.bundle?.cases||[]).filter(c=>c.state==='READY').map(c=>c.id));d.case_ids=d.case_ids.filter(id=>ready.has(id));
 const target=savedTarget();
 const job=state.job?.kind==='load'?state.job:null;
 const engineFailed=job?.result?.engine_status==='failed';
 const progress=job?`<div class="panel" role="status"><h3>${busy()?'压测进行中':engineFailed?'JMeter 执行未完成':job.status==='completed'?'压测已结束':'压测未完成'}</h3><p>${esc(job.error||(engineFailed?job.result.stop_reason:job.message)||'正在执行')}</p></div>`:'';
 $('load-management').innerHTML=selector+`<div class="panel"><h3>测试地址</h3><p><code>${esc(target||'尚未设置')}</code></p><button data-stage="1">修改测试地址</button><p class="hint">${ready.size} 条用例可执行。${state.bundle?.cases?.length||0} 条用例已保存。</p>${!ready.size?'<button data-stage="2">返回准备用例，核对执行条件 →</button>':''}</div>`+progress+renderLoadPanel()+'<div id="load-workspace-results"></div>';
 renderLoadResults('load-workspace-results');
}
