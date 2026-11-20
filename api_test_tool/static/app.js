'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names = {READY:'可执行',NEEDS_RULE:'待完善或核对',QUARANTINED:'已隔离',UNSUPPORTED:'暂不支持',PASS:'通过',FAIL:'失败',BROKEN:'执行异常',BLOCKED:'未执行'};
const state = {stage:1, bootstrap:null, project:null, contract:null, bundle:null, template:null, mode:'mcp', job:null, selected:new Set(), supplement:'', customBaseUrl:''};
const REVIEW_CODEX_GOAL='只检查接口文档：核对参数、响应、示例与描述的一致性，列出问题和建议，输出中文可视化报告，不发送接口请求。';
const DEFAULT_CODEX_GOAL='按接口文档完成测试：先完整设计并保存每个接口的正向、逆向、边界、安全及业务扩展用例，再核对并执行所有具备条件的用例，修正可解决的执行问题，最后输出真实执行结果、问题分析和未执行原因的中文可视化报告；完整设计在独立用例页查看，逐条请求与断言在执行报告查看，不在任务报告中重复展开。';
const stages = {
  1:['导入接口文档','把接口资料变成一份可以执行、可以追溯的测试方案。','解析文档中的接口、参数与响应描述，保留每条规则的原文位置。导入时不会向测试接口发送请求。'],
  2:['准备测试用例','导入自己的用例，或使用 AI 设计与补充，再核对执行预期。','可导入自己的用例、直接生成，或将两种来源合并。核对请求与预期后执行；用户用例和 AI 用例保留来源标记。'],
  3:['执行测试用例','确认已保存的测试地址，让每一条用例留下真实执行证据。','只执行状态为「可执行」的用例。场景间隔离会话与测试数据，按方案完成清理；其他用例也会进入报告并解释未执行原因。'],
  4:['查看测试报告','从结果回到请求、断言和原文，找到下一次改进的方向。','报告保存每次运行的用例快照、请求与响应、断言依据及清理结果。通过率以本轮所有用例为分母，未执行用例不会被算成通过。']
};
let toastTimer, mcpCopyTimer, pollTimer, renderedJobId;
let projectRequest=0;
const jobLogOpen = new Map();
function toast(message, error=false){ clearTimeout(toastTimer); $('toast').textContent=message; $('toast').className=error?'error':''; $('toast').hidden=false; toastTimer=setTimeout(()=>$('toast').hidden=true,error?10000:4000); }
function mcpCopyFeedback(message='',error=false){
  clearTimeout(mcpCopyTimer);
  const feedback=$('mcp-copy-feedback');
  feedback.textContent=message;
  feedback.classList.toggle('error',error);
  if(message)mcpCopyTimer=setTimeout(()=>{feedback.textContent='';feedback.classList.remove('error');},error?10000:4000);
}
async function api(path, method='GET', body){
  const options={method,headers:{}};
  if(method!=='GET'){options.headers['X-CSRF-Token']=state.bootstrap?.csrf||''; options.headers['Content-Type']='application/json'; if(body!==undefined) options.body=JSON.stringify(body);}
  let response; try{response=await fetch(path,options);}catch{throw new Error('连接中断，请检查网络后重试。');}
  if(response.status===401){location.href='/login?next='+encodeURIComponent(location.pathname+location.search+location.hash);const error=new Error('请重新登录');error.status=401;throw error;}
  const data=await response.json().catch(()=>({detail:'服务器响应格式异常'}));
  if(!response.ok){const error=new Error(typeof data.detail==='string'?data.detail:'提交内容格式不正确');error.status=response.status;throw error;}
  return data;
}
const uiWorkspace = location.pathname === '/ui-testing';
const workspaceProjects = projects => projects.filter(p => (p.test_kind === 'ui') === uiWorkspace
  && (!uiWorkspace || !p.regression_source && !p.managed_parent_project_id));
const usesCodex=()=>state.mode==='mcp'&&state.project?.case_workflow!=='own';
const busy=()=>state.job&&['queued','running'].includes(state.job.status);
const badge = status => `<span class="status-badge ${esc(status)}">${esc(names[status]||status)}</span>`;
const artifact = name => `/api/projects/${encodeURIComponent(state.project.id)}/artifacts/${name}`;
const caseReport = () => `/api/projects/${encodeURIComponent(state.project.id)}/case-report`;
const empty = (title,description,button,stage) => `<div class="panel empty-state"><span class="empty-icon">◇</span><h2>${esc(title)}</h2><p>${esc(description)}</p><button class="primary" data-stage="${stage}">${esc(button)} →</button></div>`;
function countCases(){const out={};for(const c of state.bundle?.cases||[])out[c.state]=(out[c.state]||0)+1;return out;}
function renderNavigation(){
  $('current-title').textContent=state.project?.title||'新建测试会话';
  $('project-count').textContent=state.bootstrap.projects.length;
  $('project-list').innerHTML=state.bootstrap.projects.length?state.bootstrap.projects.map(p=>`<div class="session-row" data-session-row="${esc(p.id)}"><button data-project="${esc(p.id)}" class="${p.id===state.project?.id?'current':''}" title="${esc(p.title)}">${esc(p.title)}<small>${esc(({imported:"待生成",generated:"待执行",executed:"有报告",reported:"有报告"})[p.status]||"进行中")} · ${esc(date(p.updated_at))}</small></button><button class="session-more" data-session-menu="${esc(p.id)}" aria-label="管理会话：${esc(p.title)}" aria-haspopup="menu">⋯</button></div>`).join(''):'<p class="sidebar-hint">导入第一份文档，开始测试。</p>';
  const model=state.stage===5?state.bootstrap.model:sessionModel();
  const codex=usesCodex()&&state.stage<5, progress=CodexProgress.describe(state.project,state.mcpConnection);
  $('model-label').textContent=codex?'Codex · '+progress.status:model.has_key?model.model:'接入你的模型';
  const connectionButton=$('workspace-connection');
  connectionButton.classList.toggle('model-open',!codex);
  connectionButton.title=codex?'查看 Codex 连接与授权':'管理模型 API';
  connectionButton.querySelector('.connection-dot').classList.toggle('connected',codex?progress.connected:model.has_key);
  connectionButton.querySelector('.connection-dot').classList.toggle('executing',codex&&progress.active);
  document.querySelectorAll('.sidebar-management .model-open .connection-dot').forEach(dot=>dot.classList.toggle('connected',state.bootstrap.model.has_key));
  renderCodexProgress();
  document.querySelectorAll('.sidebar-management .model-open').forEach(button=>{button.classList.toggle('active',state.stage===5);if(state.stage===5)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
  document.querySelectorAll('.sidebar-management .integration-link').forEach(button=>{if(Number(button.dataset.stage)===state.stage)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
  document.querySelectorAll('[data-stage]').forEach(button=>{const n=Number(button.dataset.stage);button.classList.toggle('active',n===state.stage);if(button.closest('.stepper'))button.disabled=!canEnterStage(n);button.classList.toggle('complete',Boolean(n===1&&state.project||n===2&&state.bundle||n===3&&(state.project?.last_run||state.project?.last_analysis)));});
  document.querySelectorAll('.stepper button[data-stage]').forEach(button=>{const n=Number(button.dataset.stage), labels=usesCodex()?[['文档资料','已保存原文'],['任务目标','由 Codex 推进'],['执行与检查','根据目标按需执行'],['结果报告','结论与真实证据']]:[['导入文档','识别接口与参数'],['准备用例','导入、生成与核对'],['执行测试','发送真实请求'],['测试报告','结果、依据与证据']];button.querySelector('span').innerHTML=labels[n-1][0]+'<small>'+labels[n-1][1]+'</small>';});
  $('project-facts').innerHTML=state.project?`<div><span>文档接口</span><strong>${Object.keys(state.contract?.operations||{}).length} 个</strong></div><div><span>测试用例</span><strong>${state.bundle?.cases.length||0} 条</strong></div><div><span>历史运行</span><strong>${state.project.runs?.length||0} 次</strong></div>`:'';
  if(uiWorkspace)UIWorkflow.renderNavigation();
}
function goStage(n){
  n=uiWorkspace?UIWorkflow.stage(n):Number(n);
  if(![5,6,7,8].includes(n)&&!canEnterStage(n)){toast('请先完成当前会话的前一步。');return;}

  $('welcome-panel').hidden=Number(n)!==1||Boolean(state.project);
  $('api-management').hidden=Number(n)!==5;
  $('session-progress').hidden=Number(n)>=5;
  $('load-management').hidden=Number(n)!==6;
  $('pingcode-management').hidden=Number(n)!==7;
  $('wecom-management').hidden=Number(n)!==8;
  $('workflow-content').hidden=Number(n)>=5;
  document.querySelector('.stepper').hidden=Number(n)>=5;
  if(Number(n)===5){state.stage=5;location.hash='apis';$('stage-title').textContent='API 管理';$('stage-description').textContent='统一配置模型服务，在生成用例时选择使用。';$('stage-count').textContent='MODEL API';renderNavigation();renderAPIManager();return;}
  if(n===6){state.stage=6;location.hash='load';$('stage-title').textContent='压测';$('stage-description').textContent='独立选择测试会话和用例，按需运行压测。Codex 完成测试后也可从这里发起。';$('stage-count').textContent='LOAD TEST';renderNavigation();renderLoadWorkspace();return;}
  if([7,8].includes(n)){WorkspaceIntegrations.enter(n);state.stage=n;location.hash=n===7?'integrations':'wecom';$('stage-title').textContent=n===7?'集成管理':'企微机器人';$('stage-description').textContent=n===7?'配置 PingCode 连接、默认项目与缺陷类型。':'配置企业微信群机器人，选择自动或手动推送报告。';$('stage-count').textContent=n===7?'PINGCODE':'WECOM';renderNavigation();return;}
  if(['#apis','#load','#integrations','#wecom'].includes(location.hash))history.replaceState(null,'',location.pathname+location.search);

  state.stage=Number(n);const [title,description,explanation]=stages[n];
  $('stage-title').textContent=usesCodex()?(n===2?'Codex 执行任务':n===4?'查看任务报告':title):title;$('stage-description').textContent=usesCodex()&&n===4?'查看分析结论、检查发现以及关联的真实执行证据。':n===2&&usesCodex()?'说明目标，Codex 按需分析文档、准备与执行测试，直到输出报告。':description;$('stage-explanation').textContent=usesCodex()?(n===2?'Codex 根据任务目标选择所需流程。文档检查可直接形成报告；需要真实测试时，自行准备、核对、执行并汇总。部分缺口会写入报告，不影响完成其他检查。':n===4?'报告保存任务结论、检查发现与建议。实际执行统计只引用已保存的运行记录，文档分析与接口测试结果分别说明。':explanation):explanation;$('stage-count').textContent=`STEP 0${n} / 04`;
  for(let i=1;i<=4;i++)$('stage-'+i).hidden=i!==state.stage;
  renderNavigation();renderCLI();
  if(n===2)renderGeneration();if(n===3)renderExecution();if(n===4)renderReports();
  if(uiWorkspace)UIWorkflow.renderStage(n);
}
function generationMode(mode){return mode==='model'?'model':'mcp';}
function renderCLI(){
  if(uiWorkspace){UIWorkflow.renderContext();return;}
  state.mode=generationMode(state.mode);
  if(state.mode==='mcp'&&state.stage===4&&state.project?.last_analysis){$('cli-command').textContent='在 Codex 中读取任务报告\nget_test_report(project_id="'+state.project.id+'")';$('cli-note').textContent='分析报告可直接下载报告 JSON；关联的接口执行记录保留完整请求与断言证据。';$('asset-links').innerHTML=`<a href="${artifact('document')}">${state.project.interfaces_modified?'当前文档':'原文档'} ↓</a><a href="${esc(state.project.last_analysis.report_url.replace('index.html','report.json'))}">报告 JSON ↓</a>`;return;}
  if(state.mode==='mcp'&&state.stage===2&&state.project?.case_workflow!=='own'){$('cli-command').textContent='Codex 按目标调用 MCP\n\n文档检查：\nget_test_document → publish_task_report\n\n接口测试：\nget_test_context → submit_test_cases\n→ review_test_cases → execute_tests\n→ get_test_job → publish_task_report';$('cli-note').textContent='Codex 负责推进任务。文档检查可直接出报告；真实接口测试沿用现有执行引擎与证据。';$('asset-links').innerHTML=state.project?`<a href="${artifact('document')}">${state.project.interfaces_modified?'当前文档':'原文档'} ↓</a><a href="${artifact('contract.json')}">契约 JSON ↓</a>${state.bundle?`<a href="${caseReport()}">用例报告 →</a><a href="${artifact('bundle.json')}">用例 JSON ↓</a>`:''}`:'';return;}
  let command,note='在项目源码目录执行。网页导入完成后，可下载契约继续使用 CLI。';
  if(state.stage===1){command='api-test import \\\n  --document document.yaml \\\n  --output contract.json';note='先下载原文档并命名为 document.yaml；Markdown 文件请改为 document.md。';}
  if(state.stage===2){
    if(state.project?.case_workflow==='own'){command='api-test validate --bundle bundle.json\n\napi-test run --bundle bundle.json --env environment.json --output runs/my-run';note='先在网页导入并核对自己的用例，再下载用例 JSON 和环境 JSON，沿用相同链路从 CLI 执行。';}
    else if(state.mode==='model'){command='api-test draft \\\n  --contract contract.json \\\n  --mode model \\\n  --model-config model.json \\\n  --out candidates.json\n\napi-test approve \\\n  --bundle candidates.json \\\n  --case-ids AI-001 \\\n  --out bundle.json';note='model.json 使用 api_key_env 指定 Key 的环境变量名。将 AI-001 替换为你核对过的用例编号；配置示例见部署说明。';}
  }
  if(state.stage===3){command='api-test validate \\\n  --bundle bundle.json\n\napi-test run \\\n  --bundle bundle.json \\\n  --env environment.json \\\n  --output runs/my-run';note='下载用例与环境配置。每次使用新的运行目录，并确认运行 CLI 的电脑可以访问测试地址。';}
  if(state.stage===4){command='api-test report \\\n  --run runs/my-run \\\n  --output runs/my-run/index.html';note='将同一次运行的 result.json 与 bundle.json 放进 runs/my-run。报告可以离线重新生成。';}
  if(state.stage===1&&state.project?.interfaces_modified){command='api-test import --document current-interfaces.json --output contract.json';note='下载当前文档 current-interfaces.json，包含接口管理后的接口范围。';}
  $('cli-command').textContent=command;$('cli-note').textContent=note;
  $('asset-links').innerHTML=state.project?`<a href="${artifact('document')}">${state.project.interfaces_modified?'当前文档':'原文档'} ↓</a><a href="${artifact('contract.json')}">契约 JSON ↓</a>${state.bundle?`<a href="${caseReport()}">用例报告 →</a><a href="${artifact('bundle.json')}">用例 JSON ↓</a><a href="${artifact('environment.json')}">环境 JSON ↓</a>`:''}`:'';
}
let targetPreviewRevision=0, targetPreviewTimer;
function resetTargetDraft(project=null){
  targetPreviewRevision++;clearTimeout(targetPreviewTimer);
  state.targetDraft=project?.task?.base_url??project?.last_run?.environment?.base_url??'';
  state.targetManual=false;state.targetCandidates=project?.document_targets?.candidates||[];
  state.targetNotes=project?.document_targets?.notes||[];state.targetLoading=false;
  state.customBaseUrl=state.targetDraft;
}
function renderDocumentTarget(){
  $('document-base-url').value=state.targetDraft||'';
  const managed=Boolean(state.project?.template);
  $('document-base-url').disabled=managed||Boolean(busy());
  $('save-document-target').hidden=!state.project||managed;
  $('save-document-target').disabled=Boolean(busy());
  $('import-actions').hidden=Boolean(state.project);
  const candidates=state.targetCandidates||[];
  $('document-target-hint').textContent=state.targetLoading?'正在识别文档中的服务地址…':managed?'示例使用配套测试服务，地址已随会话保存。':state.targetNotes?.length?state.targetNotes.join(' '):candidates.length>1?'识别到多个地址，请选择本次允许测试的服务，也可手动修改。':candidates.length?'已从文档识别地址，请核对；可修改后随文档保存。':'未识别到完整 Base URL，可手动补充。只检查文档可以留空。';
  $('document-target-candidates').innerHTML=!managed&&candidates.length>1?`<label>文档中的地址<select id="document-target-select"><option value="">选择地址</option>${candidates.map(c=>`<option value="${esc(c.url)}" ${c.url===state.targetDraft?'selected':''}>${esc(c.description?c.description+' · ':'')}${esc(c.url)}</option>`).join('')}</select></label>`:'';
}
async function previewDocumentTarget(){
  const revision=++targetPreviewRevision;
  const filename=$('document-name').value,content=$('document-content').value;
  if(state.project)return;
  state.targetLoading=true;renderDocumentTarget();
  try{
    const result=content.trim()?await api('/api/document-targets','POST',{filename,content,template:state.template}):{candidates:[],notes:[]};
    if(revision!==targetPreviewRevision||state.project)return;
    state.targetCandidates=result.candidates||[];state.targetNotes=result.notes||[];
    if(!state.targetManual)state.targetDraft=state.targetCandidates[0]?.url||'';
  }catch(error){if(revision!==targetPreviewRevision)return;state.targetNotes=['地址识别未完成，可手动填写。'+error.message];}
  finally{if(revision===targetPreviewRevision){state.targetLoading=false;renderDocumentTarget();}}
}
function scheduleTargetPreview(){targetPreviewRevision++;clearTimeout(targetPreviewTimer);targetPreviewTimer=setTimeout(()=>previewDocumentTarget(),450);}
function savedTarget(){return state.project?.task?.base_url??state.customBaseUrl??'';}
function renderContract(){
  if(uiWorkspace){UIWorkflow.renderDocument();return;}
  renderDocumentTarget();
  $('document-panel').hidden=Boolean(state.project);
  if(!state.contract){$('contract-preview').innerHTML='';return;}
  const operations=Object.values(state.contract.operations||{}),issues=state.contract.issues||[];
  $('contract-preview').innerHTML=`<div class="panel"><div class="panel-heading"><h2>接口管理 <span class="hint">${operations.length} 个接口</span></h2><button id="add-interface" class="primary" ${busy()?'disabled':''}>＋ 新增接口</button></div><div class="operation-list"><table><thead><tr><th>方法</th><th>接口路径</th><th>描述</th><th class="operation-action">操作</th></tr></thead><tbody>${operations.map(op=>`<tr><td><span class="method">${esc(op.method)}</span></td><td><code>${esc(op.path)}</code></td><td>${esc(op.summary||op.title||op.id||'—')}</td><td class="operation-action"><button class="text-button" data-edit-operation="${esc(op.id)}" ${busy()?'disabled':''}>编辑</button><button class="text-button danger-text" data-delete-operation="${esc(op.id)}" ${busy()?'disabled':''}>删除</button></td></tr>`).join('')}</tbody></table></div>${issues.length?`<details class="warning-box"><summary>查看 ${issues.length} 条文档解析提示</summary><pre>${esc(JSON.stringify(issues,null,2))}</pre></details>`:''}${!operations.length?'<div class="warning-box">自动解析暂未识别出可执行接口。原文已保存，Codex 仍可阅读并检查文档，按任务需要给出结果或说明缺口。</div>':''}<div class="panel-footer"><span class="hint">${state.project.interfaces_modified?'接口范围已更新，请重新生成用例。历史报告保留。':'原文与解析结果已保存。可在此补充或移除接口。'}</span><button class="primary" data-stage="2">交给 Codex 完成任务 →</button></div></div>`;
}
async function refreshProject(){
  if(!state.project)return;
  const id=state.project.id,request=projectRequest;
  const data=await api(`/api/projects/${id}`);
  if(request!==projectRequest||state.project?.id!==id)return;
  Object.assign(state,data);
  state.bootstrap.projects=state.bootstrap.projects.filter(p=>p.id!==data.project.id);state.bootstrap.projects.unshift(data.project);
  renderNavigation();renderContract();renderCLI();
}
async function loadProject(id,{stage:preferredStage}={}){
  const keepLoadPage=state.stage===6;
  if(busy()||state.managementBusy)throw new Error('请等待当前操作完成后切换会话。');
  closeManagementDialogs();
  const request=++projectRequest;
  const data=await api(`/api/projects/${id}`);
  if(request!==projectRequest)return;
  const documentText=await fetch(`/api/projects/${encodeURIComponent(id)}/artifacts/document`).then(r=>r.text());
  if(request!==projectRequest)return;
  if(uiWorkspace)UIWorkflow.resetResultView();
  Object.assign(state,data);state.selected.clear();state.supplement='';state.customBaseUrl=data.project.task?.base_url??data.project.last_run?.environment?.base_url??'';state.template=data.project.template;state.mode=generationMode(data.project.generation_mode);state.codexGoal=data.project.task?.goal||DEFAULT_CODEX_GOAL;
  $('project-title').value=data.project.title;$('document-name').value=data.project.filename;
  resetTargetDraft(data.project);
  $('document-content').value=documentText;updateDocumentSize();
  state.job=data.project.last_job||null;renderContract();renderJob();goStage(preferredStage??(keepLoadPage?6:data.project.status==='reported'&&data.project.last_analysis||data.project.status==='executed'&&data.project.last_run?4:2));
  if(busy())pollJob();scheduleMCPSync();
}
function resetProject(){
  if(state.managementBusy)return;
  if(busy()){toast('请等待当前任务完成后新建会话。',true);return;}
  projectRequest++;
  if(uiWorkspace)UIWorkflow.resetResultView();
  closeManagementDialogs();clearTimeout(mcpSyncTimer);clearTimeout(pollTimer);
  Object.assign(state,{project:null,contract:null,bundle:null,template:null,mode:'mcp',job:null,supplement:'',customBaseUrl:''});state.selected.clear();
  resetTargetDraft();
  if(uiWorkspace)$('ui-document-panel').innerHTML='';
  state.codexGoal=DEFAULT_CODEX_GOAL;$('project-title').value='';$('document-name').value='openapi.yaml';$('document-content').value='';$('document-file').value='';updateDocumentSize();renderContract();renderJob();goStage(1);scheduleMCPSync();
}
function updateDocumentSize(){const size=new TextEncoder().encode($('document-content').value).length;$('document-size').textContent=size?`${(size/1024).toFixed(1)} KB`:'也可以直接粘贴';document.querySelectorAll('[data-template]').forEach(el=>el.classList.toggle('selected',el.dataset.template===state.template));}
function documentLimit(){return state.bootstrap?.max_document_bytes||50000000;}
function checkDocumentSize(size){if(size>documentLimit())throw new Error(`单份文档不能超过 ${documentLimit()/1000000} MB。`);}
async function loadFile(file){if(!file)return;checkDocumentSize(file.size);if(!/\.(json|ya?ml|md|markdown)$/i.test(file.name))throw new Error('请选择 JSON、YAML 或 Markdown 文档。');state.template=null;$('document-name').value=file.name;$('project-title').value=file.name.replace(/\.[^.]+$/,'');$('document-content').value=await file.text();updateDocumentSize();state.targetManual=false;await previewDocumentTarget();}
function renderGeneration(){
  if(uiWorkspace){UIWorkflow.renderPreparation();return;}
  state.mode=generationMode(state.mode);
  if(!state.project){$('generation-panel').innerHTML=empty('先导入一份接口文档','导入后，可使用自己的用例，或交给 AI 设计测试方案。','去导入文档',1);$('cases-panel').innerHTML='';return;}
  if(state.project.case_workflow==='own'||sourceActions().awaitingImport){$('generation-panel').innerHTML=renderSourcePanel();renderCases();return;}
  $('generation-panel').innerHTML=renderSourcePanel()+`<div class="panel"><div class="panel-heading"><h2>AI 接入方式</h2><span class="quiet-tag">${Object.keys(state.contract.operations).length} 个接口</span></div><div class="mode-options"><button class="mode-option ${state.mode==='mcp'?'selected':''}" data-mode="mcp" aria-pressed="${state.mode==='mcp'}"><strong>使用 Codex · MCP</strong><small>根据目标自主推进<br>直接交付可视化报告</small></button><button class="mode-option ${state.mode==='model'?'selected':''}" data-mode="model" aria-pressed="${state.mode==='model'}"><strong>使用我的模型</strong><small>调用你配置的模型 API<br>扩展候选测试场景</small></button></div>${state.mode==='mcp'?renderMCPTaskFields():''}${state.mode==='model'?`<label style="margin-top:20px">用于本次生成的 API<select id="generation-api" ${busy()?'disabled':''}>${apiOptions()}</select></label><label class="supplement-label">补充业务规则（可选）<textarea id="supplement" maxlength="12000" rows="3" placeholder="例如：未登录时查询用户信息应返回 401。请写入已确认的规则。">${esc(state.supplement)}</textarea></label><p class="hint" style="margin-top:10px">${sessionModel().has_key?`当前模型：${esc(sessionModel().model)}。文档与补充规则将发送给该模型服务。`:'尚未配置模型。'} <button class="text-button model-open" style="padding:0;font-size:12px;color:var(--blue)">管理 API ↗</button></p>`:''}<div class="panel-footer"><span class="hint">${state.mode==='mcp'?'Codex 按目标完成任务，报告会自动同步到本会话。':state.bundle?(state.project.case_workflow==='import_ai'||state.project.case_workflow==='ai_import'||state.bundle.cases.some(c=>c.web?.source==='user')?'新增场景会追加，保留已有用例与核对状态。':'重新生成会替换当前用例方案，历史报告仍可查看。'):'先生成用例，再查看测试步骤和预期。'}</span><button class="primary" id="generate-button" ${busy()||state.mode!=='mcp'&&!Object.keys(state.contract.operations).length?'disabled':''}>${busy()?'正在处理…':state.mode==='mcp'?'交给 Codex 完成任务 →':'生成测试用例 →'}</button></div></div>`;
  renderCases();
}
function isRuleDemo(c){return state.bundle?.web?.experience&&c.id==='DEMO-NEEDS_RULE'&&c.state==='NEEDS_RULE';}
function ruleHelp(c){
  if(c.state!=='NEEDS_RULE')return '';
  if(isRuleDemo(c))return '<div class="warning-box"><strong>这是演示项，不需要你补充</strong><p>这里故意留了一条没有判断标准的用例，让你了解：不知道正确结果时，会跳过这条，继续执行其他可执行用例。</p><p>例如：批量创建 3 条数据，其中 1 条不合法，是全部不创建，还是只创建合法的 2 条？文档没有说明，所以这条没有发送请求。</p></div>';
  if(c.web?.approval_eligible)return '<div class="warning-box"><strong>已有建议的判断标准，等你确认</strong><p>请核对下方测试步骤和应该返回的结果。符合已确认的业务规则后，勾选这条用例，再点击「确认所选判断标准」；确认后才可执行。</p></div>';
  return '<div class="warning-box"><strong>这条用例尚未具备执行条件</strong><p>请查看具体原因：可能是测试步骤、预期依据、环境、鉴权或清理能力需要补齐。已保存的设计会保留，补齐后可继续执行。</p><p>怎么补：把下方具体原因交给 Codex，补齐相应的环境配置、步骤或依据，再更新本会话。你不需要自己写 JSON。</p></div>';
}
function renderCases(){
  if(!state.bundle){$('cases-panel').innerHTML=deletedCasePanel();return;}
  const counts=countCases(),cases=state.bundle.cases,eligible=cases.filter(c=>c.web?.approval_eligible&&c.state==='NEEDS_RULE'),rules=new Map((state.bundle.rules||[]).map(r=>[r.id,r]));
  $('cases-panel').innerHTML=`<div class="panel"><div class="panel-heading"><h2>测试用例 <span style="color:#91a0b7;font-weight:400">${cases.length}</span></h2><span class="report-actions"><a class="hint" href="${caseReport()}">打开用例报告 →</a><a class="hint" href="${artifact('bundle.json')}">下载 JSON ↓</a></span></div><div class="count-row">${Object.entries(counts).map(([s,n])=>`<span>${badge(s)} ${n}</span>`).join('')}</div>${eligible.length?`<div class="case-tools"><label><input type="checkbox" id="select-eligible" ${eligible.every(c=>state.selected.has(c.id))?'checked':''}> 全选待确认用例（${eligible.length}）</label><button id="approve-button" ${busy()||!state.selected.size?'disabled':''}>确认所选判断标准${state.selected.size?' · '+state.selected.size:''}</button></div><p class="hint" style="margin-bottom:12px">先核对每条用例的测试步骤、应该返回的结果和文档依据。确认判断标准不会发送测试请求。</p>`:''}${deletedCasePanel()}${cases.map(c=>`<div class="case-item"><details><summary>${c.web?.approval_eligible&&c.state==='NEEDS_RULE'?`<input type="checkbox" data-case="${esc(c.id)}" aria-label="选择 ${esc(c.id)}" ${state.selected.has(c.id)?'checked':''}>`:''}<span class="case-info"><strong>${esc(c.title)}</strong><small>${esc(c.id)} · ${esc(c.operation_id)}${c.web?.source==='user'?' · 用户用例':c.web?.source==='ai'?' · AI 用例':c.web?.source==='rules'?' · 规则用例':''}</small></span>${c.state==='NEEDS_RULE'?`<span class="status-badge NEEDS_RULE">${isRuleDemo(c)?'演示：缺少判断标准':c.web?.approval_eligible?'待核对':'执行条件待完善'}</span>`:badge(c.state)}</summary><div class="case-body">${chainControl(c)}${ruleHelp(c)}${caseReasons(c)}${c.design?`<h3>完整用例设计</h3>${Object.entries(c.design).map(([key,value])=>`<p><strong>${esc(({category:"类别",preconditions:"前置条件",inputs:"输入",procedure:"测试步骤",expected:"预期结果",basis:"预期依据",postconditions:"后置验证",cleanup:"清理安排",execution_gap:"未执行原因"})[key]||key)}</strong></p><pre>${esc(value)}</pre>`).join('')}`:''}${c.steps?.length?`<details><summary>查看测试步骤和判断标准（技术详情）</summary><pre>${esc(JSON.stringify({variables:c.variables,steps:c.steps,cleanup_steps:c.cleanup_steps},null,2))}</pre></details>`:'<p class="hint">这条尚未配置测试步骤，没有发送请求。</p>'}${c.rule_ids?.length?'<h3>判断标准来自哪里</h3>':''}${(c.rule_ids||[]).map(id=>{const rule=rules.get(id)||{};return `<p>${esc(rule.description||id)}</p>${(rule.source_ids||[]).map(sid=>{const source=state.bundle.contract.sources[sid]||{};return `<details><summary>${esc(source.path||sid)} · ${esc(source.location||'')}</summary><pre>${esc(source.excerpt||'')}</pre></details>`}).join('')}`}).join('')}</div></details></div>`).join('')}<div class="panel-footer"><span class="hint">${counts.READY||0} 条可执行，其余状态会如实写入报告。</span><button class="primary" data-stage="3" ${busy()?'disabled':''}>去执行测试 →</button></div></div>`;
}
function renderExecution(){
  if(uiWorkspace){UIWorkflow.renderExecution();return;}
  if(!state.bundle){$('execution-panel').innerHTML=empty('先生成一份测试用例','执行前需要一份包含步骤和预期断言的测试方案。','去生成用例',2);return;}
  const experience=Boolean(state.project.experience&&state.bundle.web?.experience);
  const counts=countCases(),target=savedTarget();
  const targetHint=experience?'演示服务会在运行时创建并在结束后销毁。':target?'直接使用文档中保存的地址；如需更换，请返回导入文档修改。':'尚未填写 Base URL；只检查文档无需地址，发送请求前请返回导入文档补充。';
  $('execution-panel').innerHTML=`<div class="panel"><div class="panel-heading"><h2>确认测试地址</h2><span class="quiet-tag">真实 HTTP 请求</span></div><div class="execution-target"><p>本次测试将访问</p><code>${experience?'专用临时演示服务（运行时创建，结束后销毁）':esc(target||'尚未填写 Base URL')}</code></div>${!experience?'<button data-stage="1">返回导入文档，核对或修改地址 →</button>':''}<div class="count-row">${Object.entries(counts).map(([s,n])=>`<span>${badge(s)} ${n}</span>`).join('')}</div><ul class="execution-list"><li><span>✓</span> 独立用例适度并发，依赖步骤顺序执行，保留请求与断言证据</li><li><span>✓</span> 用例独立会话与数据命名空间，按方案清理测试数据</li><li><span>✓</span> 单条失败保留证据，继续其他独立用例；依赖失败的步骤不再发送</li></ul>${!counts.READY?'<div class="warning-box">当前用例均待确认，尚未发送请求。可交给 Codex 继续检查文档并输出缺口报告；有依据的用例采纳后即可执行。</div>':''}<div class="panel-footer"><span class="hint">${targetHint}</span><button class="primary" id="run-button" ${busy()||!counts.READY||(!experience&&!target)?'disabled':''}>${busy()?'测试执行中…':'开始执行 '+(counts.READY||0)+' 条用例 →'}</button></div></div>${state.project.last_run?'<div class="panel"><div class="panel-heading" style="margin:0"><h3>本会话已有执行报告</h3><button data-stage="4">查看上次报告 →</button></div></div>':''}`;
  $('execution-panel').innerHTML+='<div class="panel"><h3>需要额外压测？</h3><p class="hint">压测已独立，可在普通测试或 Codex 任务完成后自行发起。</p><button data-stage="6">前往压测 →</button></div>';
}
function date(value){const d=new Date(typeof value==='number'?value*1000:value);return isNaN(d)?String(value||''):d.toLocaleString('zh-CN',{hour12:false});}
function renderReports(){
  renderLoadResults();
  if(uiWorkspace&&UIWorkflow.reuseResultPanel())return;
  const analysis=state.project?.last_analysis;
  if(analysis&&(!state.project.last_run||analysis.created_at>=state.project.last_run.created_at)){renderTaskReport(analysis);return;}
  const run=state.project?.last_run;if(!run){$('report-panel').innerHTML=empty('报告会在测试执行后生成','请求响应、断言结果与清理记录会保存在同一份报告中。','去执行测试',3);return;}
  const s=run.summary,failed=(s.FAIL||0)+(s.BROKEN||0),notrun=(s.BLOCKED||0)+(s.QUARANTINED||0)+(s.UNSUPPORTED||0),cleanFailed=run.cleanup?.status==='FAIL'||run.http_cleanup?.FAIL,good=Boolean(s.complete)&&!failed&&!notrun&&!cleanFailed,base=run.report_url.replace('index.html','');
  $('report-panel').innerHTML=`<div class="panel"><div class="report-title"><span style="${good?'':'background:#fff3e5;color:#bd863e'}">${good?'✓':'↗'}</span><div><h2>${good?'本轮已全部通过':'本轮执行已完成，部分用例需关注'}</h2><p>${esc(date(run.created_at))} · ${esc(run.environment.name)}</p></div></div><div class="stats"><div class="stat"><strong>${s.total}</strong><span>全部用例</span></div><div class="stat pass"><strong>${s.PASS||0}</strong><span>测试通过</span></div><div class="stat fail"><strong>${failed}</strong><span>失败 / 异常</span></div><div class="stat"><strong>${notrun}</strong><span>未执行 / 隔离</span></div></div><div class="count-row">${Object.keys(names).filter(k=>s[k]).map(k=>`<span>${badge(k)} ${s[k]}</span>`).join('')}</div><p class="hint">共发送 ${run.requests_sent} 次请求 · 通过率 ${s.total?Math.round((s.PASS||0)/s.total*100):0}% · 清理细节见完整报告</p>${cleanFailed?'<div class="warning-box">本轮数据清理失败。请先查看报告中的清理证据，处理后再运行。</div>':''}${run.experience?'<div class="warning-box">这是可控故障演示：包含通过、失败、异常及未执行场景。打开完整报告，选择失败项，点击「提交到 PingCode」审核体验。临时服务已销毁，可重新体验或执行以复测。</div>':''}<div class="report-actions"><a class="primary" href="${esc(run.report_url)}">打开完整测试报告 →</a><a href="${esc(base)}result.json" download="result.json">执行证据 JSON ↓</a><a href="${esc(base)}bundle.json" download="bundle.json">本轮用例快照 ↓</a></div><p class="hint" style="margin-top:18px">通过代表已声明的断言满足预期，不代表所有接口行为都已覆盖。</p></div><div class="panel"><div class="panel-heading"><h2>历史运行</h2><span class="quiet-tag">最近 30 次</span></div>${(state.project.runs||[]).map(r=>`<div class="run-row"><div><strong>${esc(date(r.created_at))}</strong><small>${esc(r.run_id.slice(0,12))} · ${esc(r.environment.name)}</small></div><span>${r.summary.PASS||0} / ${r.summary.total} 通过</span><a href="${esc(r.report_url)}">查看 →</a></div>`).join('')}<div class="panel-footer"><span class="hint">调整用例后，可再次执行并保留新的报告。</span><button data-stage="2">返回修改用例 →</button></div></div>`;
}
function renderJob(){
  $('import-button').disabled=Boolean(busy());
  const panel=$('job-status'), previousDetails=panel.querySelector('details');
  // Read the live toggle before polling replaces the markup, including when switching sessions.
  if(previousDetails)jobLogOpen.set(renderedJobId,previousDetails.open);
  const j=state.job;panel.hidden=!j?.status;if(!j?.status)return;
  renderedJobId=j.id;
  const logsOpen=jobLogOpen.has(j.id)?jobLogOpen.get(j.id):Boolean(busy());
  $('job-status').className='job-status '+j.status;
  $('job-status').innerHTML=`${busy()?'<span class="spinner"></span>':`<span>${j.status==='failed'?'!':'✓'}</span>`}<div><strong>${esc(j.status==='failed'?j.error:j.message)}</strong>${j.logs?.length?`<details ${logsOpen?'open':''}><summary>执行过程</summary><ul>${j.logs.map(l=>`<li>${esc(date(l.at))} · ${esc(l.message)}</li>`).join('')}</ul></details>`:''}</div>`;
  ['import-button','generate-button','run-button','approve-button'].forEach(id=>{if($(id)&&busy())$(id).disabled=true;});
}
async function startJob(path,data){state.job=await api(path,'POST',data);renderJob();goStage(state.stage);pollJob();}
async function pollJob(){
  clearTimeout(pollTimer);if(!busy())return;
  try{
    state.job=await api(`/api/jobs/${state.job.id}`);renderJob();if(state.stage===6)renderLoadWorkspace();
    if(busy()){pollTimer=setTimeout(pollJob,900);return;}
    if(state.job.project_id){await refreshProject();if(state.stage===6)renderLoadWorkspace();if(state.stage<5){if(state.job.status==='completed')goStage(['run','load'].includes(state.job.kind)?4:2);else goStage(state.stage);}}
    else if(state.job.kind==='model_test'){$('model-test-result').textContent=state.job.status==='completed'?`连接成功 · ${state.job.result.model} · ${state.job.result.elapsed_ms} ms`:state.job.error;$('test-model').disabled=false;if(state.stage===5)renderAPIManager();}
    if(state.job.status==='failed')toast(state.job.error,true);
  }catch(error){toast(error.message,true);if(error.status===404){state.job={...state.job,status:'failed',error:'任务已中断，请重新执行。已保存的项目和报告仍可查看。'};renderJob();goStage(state.stage);}else pollTimer=setTimeout(pollJob,4000);}
}
function openModel(profileId=null){
  state.editingAPI=profileId;
  const existing=(state.bootstrap.apis?.items||[]).find(x=>x.id===profileId);
  const m=existing||{provider:'openai',protocol:'openai_responses',base_url:'https://api.openai.com/v1',model:'',has_key:false,max_tokens:null,timeout:90};
  $('api-profile-name').value=existing?.name||'';
  $('model-provider').innerHTML=state.bootstrap.providers.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  $('model-provider').value=m.provider;$('model-protocol').value=m.protocol;$('model-base-url').value=m.base_url;$('model-id').value=m.model;$('model-key').value='';$('model-max-tokens').value=m.max_tokens??'';renderTokenHint();$('model-timeout').value=m.timeout;
  $('key-state').textContent=m.has_key?'已保存 · 留空保留当前 Key':'尚未配置';$('model-key').placeholder=m.has_key?'留空保留；更换地址请重新填写':'粘贴当前服务的 API Key';
  $('transport-hint').hidden=location.protocol==='https:'||['localhost','127.0.0.1'].includes(location.hostname);$('model-test-result').textContent='';$('test-model').disabled=busy();$('model-dialog').showModal();
}
function readOutputTokens(){const value=$('model-max-tokens').value.trim();if(value==='')return null;const n=Number(value);if(!Number.isSafeInteger(n)||n<=0)throw new Error('请填写有效正整数，或留空使用自动额度。');return n;}
function outputBudgetLabel(m){if(m.max_tokens!=null)return `单次输出额度 ${Number(m.max_tokens).toLocaleString()} Token`;const known=state.bootstrap?.auto_output_tokens?.[m.model];return known?`自动额度 ${Number(known).toLocaleString()} Token`:m.protocol==='anthropic'?'自动读取模型输出额度':'自动：使用服务默认额度';}
function renderTokenHint(){const value=$('model-max-tokens').value.trim();const m={model:$('model-id').value.trim(),protocol:$('model-protocol').value,max_tokens:value===''?null:Number(value)};$('model-budget-hint').textContent=outputBudgetLabel(m)+'。这是可用上限，不要求模型输出满额；实际用量以服务商统计为准。';}
async function saveModel(){
  if(!$('model-form').reportValidity())return false;
  const m={provider:$('model-provider').value,protocol:$('model-protocol').value,base_url:$('model-base-url').value.trim(),model:$('model-id').value.trim(),api_key:$('model-key').value.trim(),max_tokens:readOutputTokens(),timeout:Number($('model-timeout').value)};
  m.name=$('api-profile-name').value.trim();
  const previous=new Set(state.bootstrap.apis.items.map(x=>x.id));
  state.bootstrap.apis=await api(state.editingAPI?'/api/apis/'+state.editingAPI:'/api/apis',state.editingAPI?'PUT':'POST',m);
  if(!state.editingAPI)state.editingAPI=state.bootstrap.apis.items.find(x=>!previous.has(x.id))?.id;
  syncSelectedAPI();renderAPIManager();$('model-key').value='';$('key-state').textContent='已保存 · 留空保留当前 Key';renderNavigation();return true;
}
async function handleClick(event){
  const button=event.target.closest('button');if(!button||button.disabled)return;
  if(await handleWorkflowClick(button))return;
  if(await handleManagementClick(button))return;
  if(button.id==='auto-model-tokens'){$('model-max-tokens').value='';renderTokenHint();return;}
  if(button.id==='add-api'){openModel();return;}
  if(button.dataset.editApi){openModel(button.dataset.editApi);return;}
  if(button.dataset.selectApi){await chooseAPI(button.dataset.selectApi);return;}
  if(button.dataset.deleteApi){state.bootstrap.apis=await api('/api/apis/'+button.dataset.deleteApi,'DELETE');syncSelectedAPI();renderAPIManager();renderNavigation();toast('配置已删除；历史报告保留。');return;}
  if(button.dataset.stage){goStage(Number(button.dataset.stage));return;}
  if(button.dataset.project){await loadProject(button.dataset.project);return;}
  if(button.dataset.mode){state.mode=generationMode(button.dataset.mode);goStage(2);scheduleMCPSync();return;}
  if(button.dataset.codexGoal){state.codexGoal=button.dataset.codexGoal==='review'?REVIEW_CODEX_GOAL:DEFAULT_CODEX_GOAL;renderGeneration();return;}
  if(button.id==='workspace-connection'&&usesCodex()&&state.stage<5){await openMCP(uiWorkspace&&state.project?.id&&state.project.filename?'session':'workspace');return;}
  if(button.classList.contains('model-open')){goStage(5);return;}
  if(button.id==='open-mcp'){await openMCP();return;}
  if(button.id==='close-mcp'){$('mcp-dialog').close();return;}
  if(button.id==='pair-mcp'){await pairMCP();return;}
  if(button.id==='copy-mcp'){
    try{
      if(!mcpView?.code||mcpView.expiresAt<=Date.now())await pairMCP();
      await copyText($('mcp-prompt').value);
      scheduleMCPSync();
      mcpCopyFeedback('复制成功，请发给 Codex。');
    }catch(error){mcpCopyFeedback('复制失败：'+error.message,true);}
    return;
  }
  if(button.id==='revoke-mcp'){const view=mcpView;state.mcpConnection=await api('/api/mcp/pair','DELETE');renderNavigation();if(mcpView!==view)return;view.code=null;renderMCP(false);$('mcp-status').textContent='已断开，旧凭据和连接码已失效。';return;}
  if(button.id==='refresh-mcp'){const view=mcpView;const info=await api('/api/mcp/status');state.mcpConnection=info;renderNavigation();if(mcpView!==view)return;renderMCP(info.connected);toast('连接状态已刷新。');return;}
  if(button.id==='refresh-mcp-project'){await refreshCodexProgress();toast('执行进度已刷新：'+CodexProgress.describe(state.project,state.mcpConnection).label);return;}
  if(button.id==='new-project'){resetProject();return;}
  if(button.id==='close-model'){$('model-dialog').close();return;}
  if(button.id==='save-document-target'){
    button.disabled=true;
    try{state.project=await api('/api/projects/'+state.project.id+'/task','PUT',{...state.project.task,base_url:state.targetDraft||''});resetTargetDraft(state.project);renderDocumentTarget();toast('测试地址已保存，网页、Codex 和 CLI 将共用此地址。');}finally{button.disabled=false;}return;
  }
  if(button.id==='import-button'){
    button.disabled=true;try{clearTimeout(targetPreviewTimer);await previewDocumentTarget();checkDocumentSize(new TextEncoder().encode($('document-content').value).length);const data=await api('/api/projects','POST',{title:$('project-title').value,filename:$('document-name').value,content:$('document-content').value,template:state.template,allow_unparsed:true,task:{goal:DEFAULT_CODEX_GOAL,base_url:state.targetDraft||''}});Object.assign(state,data,{bundle:null,job:null});state.selected.clear();state.supplement='';state.customBaseUrl=data.project.task?.base_url??data.project.last_run?.environment?.base_url??'';state.template=data.project.template;state.mode='mcp';state.codexGoal=data.project.task?.goal||DEFAULT_CODEX_GOAL;resetTargetDraft(data.project);state.bootstrap.projects.unshift(state.project);renderContract();renderNavigation();renderJob();goStage(1);scheduleMCPSync();toast('文档已保存，可在接口管理中新增或删除接口。');}finally{button.disabled=false;}return;
  }
  if(button.id==='ui-handoff'){await UIWorkflow.handoff();return;}
  if(button.id==='generate-button'){
    if(sourceActions().awaitingImport)throw Error('请先导入自己的用例，再让 AI 补充。');
    if(state.mode==='mcp'){state.project=await api('/api/projects/'+state.project.id+'/task','PUT',{goal:[state.codexGoal||DEFAULT_CODEX_GOAL,sourceGoal()].filter(Boolean).join('\n'),base_url:savedTarget(),restart_progress:true});renderNavigation();await openMCP('session');scheduleMCPSync();return;}
    if(state.mode==='model'&&!sessionModel().has_key){goStage(5);toast('先在 API 管理中添加并选择配置。');return;}
    state.selected.clear();await startJob(`/api/projects/${state.project.id}/generate`,{mode:state.mode,supplement:$('supplement')?.value||''});return;
  }
  if(button.id==='approve-button'){const result=await api(`/api/projects/${state.project.id}/approve`,'POST',{case_ids:[...state.selected]});state.bundle=result.bundle;state.selected.clear();await refreshProject();renderCases();toast('已采纳 '+result.accepted_case_ids.length+' 条'+(result.skipped_cases.length?'，'+result.skipped_cases.length+' 条待确认，其他用例可继续执行。':'，可以继续执行测试。'));return;}
  if(button.id==='run-button'){await startJob(`/api/projects/${state.project.id}/run`,{base_url:savedTarget()});return;}
  if(button.id==='test-model'){if(!await saveModel())return;button.disabled=true;$('model-test-result').textContent='正在发送一次短请求…';try{await startJob('/api/apis/'+state.editingAPI+'/test');}catch(e){button.disabled=false;throw e;}return;}
  if(button.id==='clear-model'){$('model-dialog').close();return;}
  if(button.id==='copy-cli'){const text=$('cli-command').textContent;if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(text);else{const input=document.createElement('textarea');input.value=text;input.style.position='fixed';input.style.opacity='0';(document.querySelector('dialog[open]')||document.body).append(input);input.select();const copied=document.execCommand('copy');input.remove();if(!copied)throw new Error('浏览器限制复制，请直接选中 CLI 命令复制。');}toast('CLI 命令已复制。');}
}
// Preserve each handler's disabled state; prevent duplicate clicks while its promise is pending.
const pendingButtons = new WeakSet();
async function withButtonFeedback(button, action) {
  if (!button || button.disabled || pendingButtons.has(button)) return;
  pendingButtons.add(button);
  button.setAttribute('aria-busy', 'true');
  try { return await action(); }
  finally { pendingButtons.delete(button); button.removeAttribute('aria-busy'); }
}
document.addEventListener('click', e => {
  const button=e.target.closest('button');
  // Submit buttons are handled by their forms, including Enter-key submission.
  if (!button || button.form && button.type==='submit') return;
  withButtonFeedback(button,()=>handleClick(e)).catch(error=>toast(error.message,true));
});
document.addEventListener('input',e=>{if(e.target.id==='document-base-url'){state.targetDraft=e.target.value;state.targetManual=true;}if(e.target.id==='codex-goal'){state.codexGoal=e.target.value;document.querySelectorAll('[data-codex-goal]').forEach(b=>b.setAttribute('aria-pressed',String(e.target.value===(b.dataset.codexGoal==='review'?REVIEW_CODEX_GOAL:DEFAULT_CODEX_GOAL))));}if(e.target.id==='supplement')state.supplement=e.target.value;if(e.target.id==='custom-base-url')state.customBaseUrl=e.target.value;});
document.addEventListener('input',e=>{if(['model-max-tokens','model-id'].includes(e.target.id))renderTokenHint();});
document.addEventListener('change',e=>{
  if(e.target.dataset.case){e.target.checked?state.selected.add(e.target.dataset.case):state.selected.delete(e.target.dataset.case);$('approve-button').disabled=!state.selected.size;$('approve-button').textContent='确认所选判断标准'+(state.selected.size?' · '+state.selected.size:'');}
  if(e.target.id==='select-eligible'){state.selected.clear();if(e.target.checked)state.bundle.cases.filter(c=>c.web?.approval_eligible&&c.state==='NEEDS_RULE').forEach(c=>state.selected.add(c.id));renderCases();}
  if(e.target.id==='generation-api')chooseSessionAPI(e.target.value).catch(error=>toast(error.message,true));
  if(['model-max-tokens','model-id','model-protocol'].includes(e.target.id))renderTokenHint();
  if(e.target.id==='model-provider'){const p=state.bootstrap.providers.find(p=>p.id===e.target.value);$('model-protocol').value=p.protocol;$('model-base-url').value=p.base_url;$('model-id').value='';$('model-id').placeholder=p.model_hint;$('model-key').value='';$('key-state').textContent='更换服务时请填写对应的 Key';$('model-max-tokens').value='';renderTokenHint();}
});
document.addEventListener('click',e=>{if(e.target.matches('[data-case]'))e.stopPropagation();},true);
$('document-content').addEventListener('input',()=>{state.template=null;updateDocumentSize();scheduleTargetPreview();});
$('document-name').addEventListener('input',scheduleTargetPreview);
document.addEventListener('change',e=>{if(e.target.id==='document-target-select'&&e.target.value){state.targetDraft=e.target.value;state.targetManual=true;renderDocumentTarget();}});
$('document-file').addEventListener('change',e=>loadFile(e.target.files[0]).catch(error=>toast(error.message,true)));
['dragenter','dragover'].forEach(name=>$('dropzone').addEventListener(name,e=>{e.preventDefault();$('dropzone').classList.add('dragging');}));
['dragleave','drop'].forEach(name=>$('dropzone').addEventListener(name,e=>{e.preventDefault();$('dropzone').classList.remove('dragging');if(name==='drop')loadFile(e.dataTransfer.files[0]).catch(error=>toast(error.message,true));}));
$('model-form').addEventListener('submit',async e=>{e.preventDefault();await withButtonFeedback(e.submitter||$('model-form').querySelector('[type=submit]'),async()=>{try{if(await saveModel()){$('model-dialog').close();if(state.stage===2)renderGeneration();toast('模型 API 配置已保存。');}}catch(error){toast(error.message,true);}});});
let mcpView = null;
function mcpSessionTarget(){
  const operations=Object.keys(state.contract?.operations||{}).length;
  if(!state.project?.id||!state.project.filename)throw new Error('请先保存接口文档，再交给 Codex 完成任务。');
  return {id:state.project.id,title:state.project.title,ui_target_url:state.project.ui_target_url,ui_execution_permission:state.project.ui_execution_permission,ui_scene_retention:state.project.ui_scene_retention,regression_round:state.project.regression_round?JSON.parse(JSON.stringify(state.project.regression_round)):null,test_kind:state.project.test_kind,filename:state.project.effective_filename||state.project.filename,operations,task:state.project.task||{goal:DEFAULT_CODEX_GOAL}};
}
function mcpMessage(target,code){
  if(uiWorkspace)return UIWorkflow.message(target,code);
  const entry='测试台地址：'+location.origin+'\n接入与执行说明：'+location.origin+'/static/agent-guide.md\n接口测试 Skill：'+location.origin+'/static/skills/api-test-workspace/SKILL.md\n先读取此 Skill。设计或执行时，每个接口至少实际展开正向、逆向、边界和安全四类具体场景，再根据业务分支、状态、依赖、数据影响和风险自行扩充。不要把四类理解成固定四条用例，也不需要填写机械的维度表；用例数量和深度由接口复杂度决定。最终报告说明真实覆盖、执行证据和剩余缺口。\n工具格式：'+location.origin+'/static/agent-tools.json\n如果当前已加载此地址的 api-test-workspace MCP，使用它；否则先通过本机网络读取接入说明，下载免安装 Python 客户端，直接调用同一套工具完成当前任务。不要因为未安装 MCP 就停止，也不需要下载项目源码、SSH 到服务器或让我安装依赖。后续可按说明注册为 MCP。\n';
  const connect=code?'请使用 api-test-workspace MCP 的 connect_workspace 连接我的测试台，连接码：'+code+'。\n':'';
  if(!target)return entry+connect+'连接成功后在当前 Codex 聊天按 '+location.origin+'/static/workspace-usage.json 的 chat_reply 主动给出通用使用指导和两个可复制短语。指导与话术不带任何具体项目地址、项目名或业务模块，不沿用历史测试目标，不把测试台地址当作被测地址。只在聊天中说明，不增加网页操作、不要求填写模板或先选择设置，不主动追问地址和目标。权限与现场保留均为可选，用户已给出任务时直接承接。本次仅授权连接，展示指导后等待我提供任务，不要自行选择历史会话或开始测试。后续我直接给测试目标、页面地址或接口文档时，使用 start_test_workflow 自动创建对应会话；只追问工具返回的 required_inputs，不要让我先回网页建会话或填写计划。若我指定已有会话，通过 list_test_sessions 核对，名称有歧义时再确认；用 get_workflow_status 恢复进度。按我提供的目标完成所需流程，并将最终中文可视化报告保存到对应会话。';
  return entry+connect+'请使用 api-test-workspace MCP 完成下面的任务，并交付最终中文可视化报告。\n会话名称：'+target.title+'\n会话 ID：'+target.id+'\n文档名称：'+target.filename+'\n任务目标：'+target.task.goal+'\n本次测试地址：'+(target.task.base_url||'未填写（只检查文档无需地址）')+'\n先用 get_test_document 读取原文，再按目标决定是否需要用例和真实请求。只做文档检查时直接分析并用 publish_task_report 输出结果，无需构造可执行用例；地址为空时不要发送请求。需要真实测试时，直接使用会话中保存的本次测试地址，不要选择或切换其他地址；先完整保存具体用例（包括暂不可执行项的 design），再按同一 ID 补充步骤、核对、采纳、执行和回查。不得把执行条件缺口当作删减设计的理由，也不要停在生成用例后让我回网页推进。可从现有上下文解决的问题自行处理，部分接口缺条件时继续完成其他检查，把具体缺口写入最终报告。最终报告只写结论、问题和缺口，不重复展开完整用例设计或逐条请求/断言；使用真实执行记录作为测试结论依据；完成后给我报告链接。';
}
function renderMCP(connected){
  if(!mcpView)return;
  const target=mcpView.target;
  const compact=target?.test_kind==='ui';
  $('mcp-dialog').classList.toggle('ui-session-handoff',compact);
  if(compact)$('mcp-task-details').open=false;
  $('copy-mcp').classList.toggle('primary',compact);
  if(mcpView.expiresAt<=Date.now())mcpView.code=null;
  $('mcp-title').textContent=compact?'把测试任务发给 Codex':target?'交给 Codex 完成任务':'授权 Codex 访问测试台';
  $('mcp-intro').textContent=target?'Codex 将根据目标自主完成所需流程，最终报告保存在这个会话。':'允许 Codex 访问当前账号下的测试会话和报告。授权连接不会开始测试，也不会自动选中网页当前会话。';
  $('mcp-authorization-help').hidden=Boolean(target);
  $('mcp-target').hidden=!target;
  $('mcp-target').innerHTML=target?`<strong>${esc(target.title)}</strong><p>${target.test_kind==='ui'?'目标页面：'+esc(target.ui_target_url||'未填写'):'文档：'+esc(target.filename)+' · '+target.operations+' 个接口'}</p><p class="hint">会话 ID：${esc(target.id)}</p><p>任务目标：${esc(target.task.goal)}</p>`:'';
  $('mcp-status').textContent=mcpView.code?'接入信息已就绪，连接码 10 分钟内有效。':connected?'此工作空间有已授权连接，可生成新消息给当前 Codex。':'连接码已过期或撤销，请重新生成。';
  $('mcp-next').textContent=target?'复制下面这段完整消息给能访问内网的 Codex。它会读取本会话文档、按目标处理并把报告写回这里。':'先复制下方授权消息给 Codex，连接成功后，再按上面的任一方式提供任务。';
  $('pair-mcp').hidden=false;
  $('pair-mcp').textContent=connected||mcpView.code?'重新生成连接码':'生成连接码';
  $('revoke-mcp').hidden=Boolean(target);
  $('revoke-mcp').textContent='撤销所有 Codex 连接和连接码';
  $('mcp-prompt-label').textContent=target?'把本会话任务发给 Codex':'把连接消息发给 Codex';
  $('mcp-prompt').value=mcpView.code?mcpMessage(target,mcpView.code):'';
  $('mcp-message').hidden=!$('mcp-prompt').value;
}
async function openMCP(scope='workspace'){
  mcpCopyFeedback();
  const view={target:scope==='session'?mcpSessionTarget():null,code:null,expiresAt:0};
  mcpView=view;
  const info=await api('/api/mcp/status');state.mcpConnection=info;renderNavigation();
  if(mcpView!==view)return;
  renderMCP(info.connected);$('mcp-dialog').showModal();await pairMCP();
}
async function pairMCP(){
  mcpCopyFeedback();
  const view=mcpView;
  $('pair-mcp').disabled=true;
  try{
    const pair=await api('/api/mcp/pair','POST');
    if(mcpView!==view||!$('mcp-dialog').open)return;
    view.code=pair.code;view.expiresAt=Date.now()+pair.expires_in*1000;
    renderMCP(false);$('mcp-prompt').select();
  }finally{$('pair-mcp').disabled=false;}
}
async function copyText(text){
  if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text);return;}
  const input=document.createElement('textarea');input.value=text;input.style.position='fixed';input.style.opacity='0';(document.querySelector('dialog[open]')||document.body).append(input);input.select();const copied=document.execCommand('copy');input.remove();
  if(!copied)throw new Error('浏览器限制复制，请直接选中消息复制。');
}
$('mcp-dialog').addEventListener('close',()=>{if(!$('mcp-dialog').open){mcpView=null;$('mcp-prompt').value='';mcpCopyFeedback();}});
async function init(){const openAPIs=location.hash==='#apis',openLoad=location.hash==='#load',openIntegration=WorkspaceIntegrations.stageForHash(location.hash);state.bootstrap=await api('/api/bootstrap'+(uiWorkspace?'?test_kind=ui':''));if(uiWorkspace)UIWorkflow.setup();const version=document.querySelector?.('.version'),footer=document.querySelector?.('.page-footer>span');if(version)version.textContent='v'+state.bootstrap.version;if(footer)footer.textContent='探真 VERIQ · 内网版 '+state.bootstrap.version;goStage(1);if(openAPIs)goStage(5);else if(state.bootstrap.projects.length){const requested=new URLSearchParams(location.search).get('project');const selected=state.bootstrap.projects.find(p=>p.id===requested)||state.bootstrap.projects[0];await loadProject(selected.id);}if(openLoad&&!uiWorkspace)goStage(6);if(openIntegration)goStage(openIntegration);if(location.hash==='#chain-demo')await handleWorkflowClick({dataset:{wf:'chain-demo'}});scheduleMCPSync();}


function syncSelectedAPI(){
  const chosen=state.bootstrap.apis.items.find(x=>x.id===state.bootstrap.apis.active_id);
  state.bootstrap.model=chosen||{has_key:false,model:''};
}
function apiOptions(){
  const apis=state.bootstrap.apis||{items:[],active_id:null};
  const selected=state.project?.api_profile_id||apis.active_id;
  return `<option value="" disabled ${!apis.items.some(a=>a.id===selected)?'selected':''}>请选择模型 API</option>`+apis.items.map(a=>`<option value="${esc(a.id)}" ${a.id===selected?'selected':''}>${esc(a.name)} · ${esc(a.model)}</option>`).join('');
}
function sessionModel(){
  const selected=state.project?.api_profile_id;
  if(selected)return state.bootstrap.apis.items.find(a=>a.id===selected)||{has_key:false,model:''};
  return state.bootstrap.model;
}
function canEnterStage(n){if(uiWorkspace&&n===4)return Boolean(state.project);if(uiWorkspace&&n===3)return Boolean(state.project&&!state.project.ui_import_filename);return n===1||[5,7,8].includes(n)||n===2&&Boolean(state.project)||n===3&&Boolean(state.bundle)||n===4&&Boolean(state.project?.last_run||state.project?.last_analysis||state.project?.last_load);}
async function chooseSessionAPI(id){
  state.project=await api('/api/projects/'+state.project.id+'/api','PUT',{api_profile_id:id});renderNavigation();renderGeneration();
}
async function chooseAPI(id){
  state.bootstrap.apis=await api('/api/apis/'+id+'/select','POST');syncSelectedAPI();if(state.project)state.project=await api('/api/projects/'+state.project.id+'/api','PUT',{api_profile_id:id});renderNavigation();
  if(state.stage===5)renderAPIManager();if(state.stage===2)renderGeneration();
  toast('已选择 '+state.bootstrap.model.name);
}
function renderAPIManager(){
  const apis=state.bootstrap.apis||{items:[],active_id:null};
  $('api-management').innerHTML=`<div class="panel"><div class="panel-heading"><div><h2>我的模型 API <span class="hint">${apis.items.length} / 30</span></h2><p class="hint">配置名称方便区分用途；每个测试会话可独立选择 API。</p></div><button class="primary" id="add-api" ${busy()?'disabled':''}>＋ 添加 API</button></div>${apis.items.length?apis.items.map(a=>`<div class="api-entry"><div><h3>${esc(a.name)} ${a.id===apis.active_id?'<span class="status-badge READY">默认配置</span>':''}</h3><p>${esc(a.model)} · ${esc(state.bootstrap.providers.find(p=>p.id===a.provider)?.name||a.provider)}</p><code>${esc(a.base_url)}</code><p class="hint">${a.has_key?'Key 已加密保存':'未配置 Key'} · ${esc(outputBudgetLabel(a))} · 连续 ${a.timeout} 秒无响应才停止</p></div><div class="api-actions"><button data-select-api="${esc(a.id)}" ${busy()||(a.id===apis.active_id&&(!state.project||state.project.api_profile_id===a.id))?'disabled':''}>选择使用</button><button data-edit-api="${esc(a.id)}" ${busy()?'disabled':''}>编辑 / 测试</button><details><summary>删除</summary><p class="hint">删除这套配置后，需重新填写 Key。</p><button data-delete-api="${esc(a.id)}" ${busy()?'disabled':''}>确认删除配置</button></details></div></div>`).join(''):'<div class="empty-state"><h2>添加第一套模型 API</h2><p>可分别保存 DeepSeek、Claude、自有网关等配置，按会话需要切换。</p></div>'}<div class="panel-footer"><span class="hint">切换或保存配置不会调用模型。只有测试连接和模型生成会发送请求。</span><button data-stage="${state.project?2:1}">${state.project?"返回当前会话":"新建测试会话"} →</button></div></div>`;
}


function renderMCPTaskFields(){
  const task=state.project.task||{},target=savedTarget();
  const files=state.project.ui_requirement_attachments||[];
  const attachments=files.length?`<section><h3>已保存的任务附件 · ${files.length}</h3><ul>${files.map(file=>`<li><a href="${esc(file.url)}">${esc(file.filename)} ↓</a> <span class="hint">${Math.max(1,Math.ceil(file.size/1000))} KB</span></li>`).join('')}</ul></section>`:'';
  return `<div class="mcp-context"><strong>文档：${esc(state.project.effective_filename||state.project.filename)}</strong><p>${Object.keys(state.contract.operations).length} 个接口；Codex 按当前接口范围处理文档。</p>${attachments}<label style="margin-top:16px">你希望 Codex 完成什么<textarea id="codex-goal" rows="4" maxlength="12000">${esc(state.codexGoal||task.goal||DEFAULT_CODEX_GOAL)}</textarea></label><div class="task-presets"><button data-codex-goal="full" aria-pressed="${(state.codexGoal||task.goal||DEFAULT_CODEX_GOAL)===DEFAULT_CODEX_GOAL}">完整测试并出报告</button><button data-codex-goal="review" aria-pressed="${(state.codexGoal||task.goal||DEFAULT_CODEX_GOAL)===REVIEW_CODEX_GOAL}">只检查接口文档</button></div><div class="execution-target"><p>文档中保存的测试地址</p><code>${esc(target||'尚未填写；只检查文档无需地址')}</code><button class="text-button" data-stage="1">修改测试地址</button></div><p>需要真实请求时，Codex 直接使用上面的地址，不选择或切换其他地址。只检查文档时无需地址，也不会发送请求。</p></div>`;
}
function renderTaskReport(report){
  const history=state.project.analysis_reports||[];
  const wecomPath=report.report_url.replace(/\/index\.html$/,'/wecom');
  $('report-panel').innerHTML=`<div class="panel"><div class="report-title"><span>✓</span><div><h2>${esc(uiWorkspace?state.project.title+' · 总报告':report.title)}</h2><p>${esc(date(report.created_at))} · ${uiWorkspace?'UI 测试结果':report.kind==='analysis'?'文档与任务分析':'执行与分析汇总'}</p></div></div><p style="margin-top:20px">任务报告已保存，可查看结果并审核提交缺陷。</p><p class="hint">${uiWorkspace?'测试状态以报告中的实际结果为准；未执行与阻塞项不会计为通过。':report.kind==='analysis'?'本报告未关联接口执行记录，文档分析结果不代表接口测试通过。':`关联 ${report.requests_sent} 次真实请求。`}</p><div class="report-actions"><a class="primary" href="${esc(uiWorkspace?`/api/projects/${state.project.id}/reports/total/index.html`:report.report_url)}">${uiWorkspace?'打开总报告':'打开完整报告'} →</a>${uiWorkspace?`<a href="${esc(report.report_url)}">最新阶段报告 →</a>`:''}<button data-wecom-path="${esc(wecomPath)}">推送到企微</button><span data-wecom-status role="status"></span>${uiWorkspace?'':`<a href="${esc(report.report_url.replace('index.html','report.json'))}" download>报告 JSON ↓</a>`}</div></div><div class="panel"><h2>任务报告记录</h2>${history.map(r=>`<div class="run-row"><div><strong>${esc(r.title)}</strong><small>${esc(date(r.created_at))}</small></div><a href="${esc(r.report_url)}">查看 →</a></div>`).join('')}${(state.project.runs||[]).map(r=>`<div class="run-row"><div><strong>接口执行证据</strong><small>${esc(date(r.created_at))}</small></div><a href="${esc(r.report_url)}">查看 →</a></div>`).join('')}${uiWorkspace?'':'<div class="panel-footer"><button data-stage="2">调整任务目标 →</button></div>'}</div>`;
}
function renderCodexProgress(){
  const panel=$('codex-progress-panel');
  panel.hidden=!usesCodex()||!state.project||state.stage>=5||(uiWorkspace&&(state.stage!==2||(!state.project.mcp_progress&&!busy())||(state.project.ui_import_filename&&!state.project.regression_round)));
  if(panel.hidden)return;
  const info=CodexProgress.describe(state.project,state.mcpConnection);
  const history=state.project.mcp_progress?.history||[];
  const historyOpen=panel.querySelector('[data-progress-history]')?.open;
  const related=state.project.mcp_progress?.related_history;
  const relatedOpen=panel.querySelector('[data-related-progress]')?.open;
  const relatedView=related?.modules?.length?`<details data-related-progress ${relatedOpen?'open':''}><summary>${esc(related.label)}</summary><p>${esc(related.message)}</p><ol>${related.modules.map(item=>`<li><a href="${esc(item.report_url)}">${esc(item.title)}</a> · ${esc(item.label)}</li>`).join('')}</ol></details>`:'';
  const progress=state.project.mcp_progress;
  const recorded=progress?.source==='execution_records';
  const stages=new Map();
  for(const module of progress?.modules||[]){const label=module.label||module.phase;stages.set(label,(stages.get(label)||0)+1);}
  const stageView=recorded&&stages.size?`<div class="codex-progress-stages">${[...stages].map(([label,count])=>`<span>${esc(label)}<strong>${count} 个模块</strong></span>`).join('')}</div>`:`<h3>${esc(info.label)}</h3>`;
  const message=info.message||(!progress&&!state.project.last_analysis?'将任务消息发给 Codex，接手后这里自动更新。':info.phase==='completed'?'最终报告已保存，可在结果报告中查看。':'按平台保存的执行状态显示进展。');
  const messageOpen=panel.querySelector('[data-progress-message]')?.open;
  panel.innerHTML=`<div class="codex-progress-heading"><div><span class="connection-dot ${info.connected?'connected':''} ${info.active?'executing':''}"></span><strong>Codex 执行进度</strong><span class="quiet-tag">${esc(info.status)}</span></div><button id="refresh-mcp-project">刷新执行进度</button></div>${stageView}${recorded?`${CodexProgress.renderCounts(progress)}<p class="case-metrics-note">报告保存不代表覆盖通过。</p>`:`<p>${esc(message)}</p>`}<small class="codex-progress-times">${info.lastCaseSavedAt?'最近保存用例：'+esc(date(info.lastCaseSavedAt))+' · ':''}${info.updatedAt?'最近进展：'+esc(date(info.updatedAt))+' · ':''}${info.stale?'暂未收到新进展，等待 Codex 更新。':'每 6 秒自动刷新'}</small>${recorded?`<details data-progress-message ${messageOpen?'open':''}><summary>查看进展说明</summary><p>${esc(message)}</p></details>`:''}${relatedView}${history.length?`<details data-progress-history ${historyOpen?'open':''}><summary>查看会话阶段记录</summary><ol>${history.map(item=>`<li><span>${esc(date(item.updated_at))}</span> <strong>${esc(item.label)}</strong>${item.message?' · '+esc(item.message):''}</li>`).join('')}</ol></details>`:''}`;
}
let mcpSyncTimer, progressRefresh;
async function refreshCodexProgress({fresh=false}={}){
  if(fresh&&progressRefresh){try{await progressRefresh.promise;}catch{}return refreshCodexProgress();}
  const id=state.project?.id;
  const request=projectRequest;
  if(progressRefresh&&progressRefresh.id===id&&progressRefresh.request===request)return progressRefresh.promise;
  const pending={id,request};
  progressRefresh=pending;
  pending.promise=readCodexProgress(id,request).finally(()=>{if(progressRefresh===pending)progressRefresh=null;});
  return pending.promise;
}
async function readCodexProgress(id,request){
  let connection,data,managed;
  if(id&&uiWorkspace){
    const response=await api('/api/projects/'+id+'/progress');
    connection=response.connection;managed=response.managed;
    data={project:{...state.project,...response.project}};
    // History was loaded on navigation; live polling only updates this round.
    if(data.project.mcp_progress&&state.project?.mcp_progress?.related_history)
      data.project.mcp_progress={...data.project.mcp_progress,related_history:state.project.mcp_progress.related_history};
  }else [connection,data]=await Promise.all([api('/api/mcp/status'),id?api('/api/projects/'+id):Promise.resolve(null)]);
  if(state.project?.id!==id||projectRequest!==request)return;
  state.mcpConnection=connection;
  if(data&&state.project?.id===id&&!state.managementBusy){
    const priorReport=state.project.last_analysis?.id, priorBundle=state.bundle_revision;
    Object.assign(state,data);state.job=data.project.last_job||null;
    state.bootstrap.projects=state.bootstrap.projects.map(p=>p.id===id?data.project:p);
    renderJob();
    if(state.mode==='mcp'&&$('generate-button'))$('generate-button').disabled=Boolean(busy());
    if(!uiWorkspace&&state.stage===2&&data.bundle_revision!==priorBundle)renderCases();
    if(state.stage===6&&data.bundle_revision!==priorBundle)renderLoadWorkspace();
    if(data.project.last_analysis?.id&&data.project.last_analysis.id!==priorReport){
      if($('mcp-dialog').open&&mcpView?.target?.id===id)$('mcp-dialog').close();
      if(state.stage<5){goStage(4);toast('Codex 任务报告已同步。');}
    }
    if(uiWorkspace){UIWorkflow.refreshRequirements();UIWorkflow.refreshResultIfChanged();}
    if(managed)globalThis.ManagedWorkflow?.applyProgress(managed);
    // Keep the current page and unsaved goal/address inputs during progress refresh.
  }
  renderNavigation();
}
function scheduleMCPSync(){
  clearTimeout(mcpSyncTimer);
  const id=state.project?.id,request=projectRequest;
  mcpSyncTimer=setTimeout(async()=>{
    try{
      if(document.hidden||state.managementBusy)return;
      if(state.project&&usesCodex())await refreshCodexProgress();
      else{state.mcpConnection=await api('/api/mcp/status');renderNavigation();}
    }catch(error){
      if(state.project?.id!==id||projectRequest!==request)return;
      if(uiWorkspace&&[401,403].includes(error.status))UIWorkflow.resetResultView();
      if(error.status===404&&state.project?.id===id&&!state.managementBusy){state.bootstrap.projects=state.bootstrap.projects.filter(p=>p.id!==id);state.job=null;clearHandoff(id);resetProject();toast('该会话已删除，可在回收站恢复。');}
      else{state.mcpConnection={};renderNavigation();const note=$('codex-progress-panel').querySelector('small');if(note)note.textContent='进度同步失败，请检查网络或点击刷新重试。';}
    }finally{scheduleMCPSync();}
  },6000);
}
let sessionMenuId=null, renameSessionId=null, interfaceEdit=null;
let trashProjects=[], purgeIds=[];
const trashSelected=new Set();
function closeSessionMenu(){ $('session-menu').hidden=true;sessionMenuId=null; }
function closeManagementDialogs(){
  closeSessionMenu();
  for(const id of ['rename-dialog','interface-dialog','delete-interface-dialog','trash-dialog','purge-dialog'])if($(id).open)$(id).close();
  interfaceEdit=null;
}
function openSessionMenu(id,x,y){
  sessionMenuId=id;
  const menu=$('session-menu');menu.hidden=false;
  menu.style.left=Math.max(8,Math.min(x,window.innerWidth-menu.offsetWidth-8))+'px';
  menu.style.top=Math.max(8,Math.min(y,window.innerHeight-menu.offsetHeight-8))+'px';
  const disabled=Boolean(busy()||state.managementBusy);
  $('rename-session').disabled=disabled;
  $('delete-session').disabled=disabled;
  $('rename-session').focus();
}
function openRenameDialog(id){
  const project=state.bootstrap.projects.find(p=>p.id===id);
  if(!project||busy()||state.managementBusy)return;
  renameSessionId=id;
  $('rename-input').value=project.title;
  $('rename-error').hidden=true;
  $('rename-dialog').showModal();
  $('rename-input').focus();
  $('rename-input').select();
}
async function saveSessionName(){
  const id=renameSessionId;
  const title=$('rename-input').value.trim();
  if(!id||state.managementBusy)return;
  if(!title||title.length>120)throw new Error('会话名称须为 1–120 个字符');
  const existing=state.bootstrap.projects.find(p=>p.id===id);
  if(!existing)throw new Error('会话已变更，请刷新后重试');
  if(title===existing.title){$('rename-dialog').close();renameSessionId=null;return;}
  state.managementBusy=true;
  try{
    const {project}=await api('/api/projects/'+encodeURIComponent(id)+'/title','PATCH',{title});
    state.bootstrap.projects=state.bootstrap.projects.map(p=>p.id===id?{...p,title:project.title,updated_at:project.updated_at}:p)
      .sort((a,b)=>b.updated_at.localeCompare(a.updated_at));
    if(state.project?.id===id)Object.assign(state.project,{title:project.title,updated_at:project.updated_at});
    $('rename-dialog').close();renameSessionId=null;
    renderNavigation();toast('会话已重命名。');
  }finally{state.managementBusy=false;}
}
$('rename-dialog').addEventListener('cancel',event=>{if(state.managementBusy)event.preventDefault();});
$('rename-dialog').addEventListener('close',()=>{renameSessionId=null;});
$('rename-form').addEventListener('submit',event=>{
  event.preventDefault();
  withManagementButton($('confirm-rename'),'rename-error',saveSessionName);
});
async function renderTrash(){
  const data=await api('/api/deleted-projects');
  trashProjects=workspaceProjects(data.projects);trashSelected.clear();
  $('trash-list').innerHTML=trashProjects.length?trashProjects.map(p=>`<div class="trash-entry"><label><input type="checkbox" data-trash-select="${esc(p.id)}" aria-label="选择会话：${esc(p.title)}"><span><strong>${esc(p.title)}</strong><small>删除于 ${esc(date(p.deleted_at))}</small>${p.cleanup?.desktop_stop?.manual_stop_required?'<small>平台已停止调度，桌面会话仍需人工停止并核实退出</small>':p.cleanup?.stopping?'<small>正在停止执行并回收资源</small>':''}${p.cleanup?.resource_holds?`<small>仍有 ${esc(p.cleanup.resource_holds)} 项资源待核实：${esc((p.cleanup.reasons||[]).join('；'))}。恢复会话可查看处理。</small>`:''}</span></label><div class="trash-actions"><button data-restore-project="${esc(p.id)}">恢复</button><button class="danger-text" data-purge-project="${esc(p.id)}">彻底删除</button></div>${globalThis.ManagedWorkflow?.renderDesktopStop(p.cleanup?.desktop_stop)||''}</div>`).join(''):'<div class="empty-state"><p>回收站是空的</p></div>';
  updateTrashSelection();
}
function updateTrashSelection(){
  $('trash-selection-count').textContent=`已选 ${trashSelected.size} / ${trashProjects.length} 个`;
  $('trash-select-all').disabled=!trashProjects.length;
  $('trash-select-all').checked=Boolean(trashProjects.length&&trashSelected.size===trashProjects.length);
  $('trash-select-all').indeterminate=trashSelected.size>0&&trashSelected.size<trashProjects.length;
  $('purge-selected').disabled=!trashSelected.size;
  $('empty-trash').disabled=!trashProjects.length;
}
function confirmTrashPurge(ids){
  if(state.managementBusy||!ids.length)return;
  purgeIds=[...ids];
  $('purge-summary').textContent=`即将彻底删除 ${purgeIds.length} 个会话：`;
  $('purge-names').innerHTML=trashProjects.filter(p=>purgeIds.includes(p.id)).map(p=>`<li>${esc(p.title)}</li>`).join('');
  $('purge-error').hidden=true;$('confirm-purge').textContent=`彻底删除 ${purgeIds.length} 个会话`;
  $('purge-dialog').showModal();
  $('purge-dialog').querySelector('[data-close-dialog]').focus();
}
async function purgeTrash(){
  if(state.managementBusy||!purgeIds.length)return;
  state.managementBusy=true;
  try{
    const result=await api('/api/deleted-projects/purge','POST',{project_ids:purgeIds,confirm:true});
    for(const id of result.deleted_ids)clearHandoff(id);
    purgeIds=[];$('purge-dialog').close();
    await renderTrash();toast(`已彻底删除 ${result.deleted_ids.length} 个会话。`);
  }finally{state.managementBusy=false;}
}
document.addEventListener('change',event=>{
  const input=event.target;
  if(input.id==='trash-select-all'){
    trashSelected.clear();
    document.querySelectorAll('[data-trash-select]').forEach(box=>{box.checked=input.checked;if(input.checked)trashSelected.add(box.dataset.trashSelect);});
  }else if(input.dataset.trashSelect){
    if(input.checked)trashSelected.add(input.dataset.trashSelect);else trashSelected.delete(input.dataset.trashSelect);
  }else return;
  updateTrashSelection();
});
$('purge-dialog').addEventListener('cancel',event=>{if(state.managementBusy)event.preventDefault();});
function clearHandoff(id){if(mcpView?.target?.id===id){mcpView=null;$('mcp-dialog').close();$('mcp-prompt').value='';}}
async function deleteSession(id){
  if(!id||state.managementBusy)return;
  state.managementBusy=true;
  try{
    const result=await api('/api/projects/'+id,'DELETE');
    state.bootstrap.projects=workspaceProjects(result.projects);clearHandoff(id);
    if(state.project?.id===id){state.job=null;state.managementBusy=false;resetProject();}
    else renderNavigation();
    toast(result.cleanup?.desktop_stop?.manual_stop_required?'会话已移入回收站，平台调度已停止。请在回收站打开停止清单，停止桌面 Codex 会话。':result.cleanup?.stopping?'会话已移入回收站，正在停止执行并回收资源。':result.cleanup?.resource_holds?'会话已移入回收站，仍有资源待核实，可在回收站查看。':'会话已删除，可在回收站恢复。');
  }finally{state.managementBusy=false;}
}
function openInterfaceEditor(deleteId=null,editId=null){
  if(!state.project||busy()||state.managementBusy)return;
  interfaceEdit={projectId:state.project.id,revision:state.contract_revision,deleteId,editId};
  if(deleteId){
    const op=state.contract.operations[deleteId];if(!op)return;
    $('delete-interface-name').textContent=op.method+' '+op.path+' · '+(op.summary||op.title||op.id);
    $('delete-interface-error').hidden=true;$('delete-interface-dialog').showModal();
  }else{
    $('interface-form').reset();$('interface-error').hidden=true;
    $('interface-title').textContent=editId?'编辑接口':'新增接口';
    $('save-interface').textContent=editId?'保存修改':'保存接口';
    $('interface-edit-hint').hidden=!editId;
    if(editId){
      const op=state.contract.operations[editId];if(!op)return;
      $('interface-name').value=op.summary||op.title||op.id;
      $('interface-method').value=op.method;$('interface-path').value=op.path;
      $('interface-description').value=op.business_rules||'';
      const statuses=Object.keys(op.responses||{}),primary=statuses.find(k=>k.startsWith('2'))||(statuses.length===1?statuses[0]:'');
      $('interface-status').value=primary;
      for(const [id,value] of [['interface-request',op.has_request_example||op.has_request_body||Object.keys(op.request_schema||{}).length||(op.request_example!=null&&JSON.stringify(op.request_example)!=='{}')?op.request_example:undefined],['interface-schema',op.request_schema],['interface-parameters',op.parameters],['interface-response',op.response_examples?.[0]]]){
        $(id).value=value===undefined?'':JSON.stringify(value,null,2);
      }
      interfaceEdit.initial=readInterfaceForm();
    }
    $('interface-dialog').showModal();
  }
}
function readInterfaceForm(){
  const operation={title:$('interface-name').value.trim(),method:$('interface-method').value,path:$('interface-path').value.trim(),description:$('interface-description').value.trim()};
  for(const [id,key,label] of [['interface-request','request_example','请求体示例'],['interface-response','response_example','预期响应示例'],['interface-parameters','parameters','参数'],['interface-schema','request_schema','请求体 Schema']]){
    const raw=$(id).value.trim();if(raw){try{operation[key]=JSON.parse(raw);}catch{throw new Error(label+'不是有效的 JSON，请检查引号和逗号。');}}
  }
  if($('interface-status').value.trim())operation.response_status=Number($('interface-status').value);
  return operation;
}
async function saveInterfaceEdit(operation){
  const target=interfaceEdit;if(!target||state.managementBusy)return;
  if(state.project?.id!==target.projectId)throw new Error('会话已切换，请重新打开接口管理。');
  state.managementBusy=true;
  try{
    const operationId=target.deleteId||target.editId;
    const url='/api/projects/'+target.projectId+'/operations'+(operationId?'/'+encodeURIComponent(operationId):'');
    if(target.editId){
      const changes={},clear=[];
      for(const key of new Set([...Object.keys(target.initial),...Object.keys(operation)])){
        if(JSON.stringify(target.initial[key])===JSON.stringify(operation[key]))continue;
        if(!(key in operation))clear.push(key);else changes[key]=operation[key];
      }
      if(clear.length)changes._clear=clear;operation=changes;
    }
    const data=await api(url,target.deleteId?'DELETE':target.editId?'PATCH':'POST',{revision:target.revision,operation});
    Object.assign(state,data);state.job=null;state.selected.clear();
    if(state.mode==='baseline')state.mode='mcp';
    state.bootstrap.projects=state.bootstrap.projects.map(p=>p.id===data.project.id?data.project:p);
    clearHandoff(target.projectId);closeManagementDialogs();renderContract();renderJob();goStage(1);scheduleMCPSync();
    toast(target.deleteId?'接口已删除，后续测试使用新的接口范围。':target.editId?'接口修改已保存。':'接口已添加。');
  }finally{state.managementBusy=false;}
}
async function withManagementButton(button,errorId,action){
  button.disabled=true;$(errorId).hidden=true;
  try{await action();}catch(error){$(errorId).textContent=error.message;$(errorId).hidden=false;}
  finally{button.disabled=false;}
}
async function handleManagementClick(button){
  if(button.dataset.closeDialog){if(!state.managementBusy)$(button.dataset.closeDialog).close();return true;}
  if(button.dataset.sessionMenu){const rect=button.getBoundingClientRect();openSessionMenu(button.dataset.sessionMenu,rect.right,rect.bottom);return true;}
  if(button.id==='rename-session'){const id=sessionMenuId;closeSessionMenu();openRenameDialog(id);return true;}
  if(button.id==='delete-session'){const id=sessionMenuId;closeSessionMenu();await deleteSession(id);return true;}
  if(button.id==='open-trash'){$('trash-error').hidden=true;await renderTrash();$('trash-dialog').showModal();return true;}
  if(button.dataset.purgeProject){confirmTrashPurge([button.dataset.purgeProject]);return true;}
  if(button.id==='purge-selected'){confirmTrashPurge([...trashSelected]);return true;}
  if(button.id==='empty-trash'){confirmTrashPurge(trashProjects.map(p=>p.id));return true;}
  if(button.id==='confirm-purge'){await withManagementButton(button,'purge-error',purgeTrash);return true;}
  if(button.dataset.restoreProject){
    await withManagementButton(button,'trash-error',async()=>{
      const project=await api('/api/projects/'+button.dataset.restoreProject+'/restore','POST');
      state.bootstrap.projects=state.bootstrap.projects.filter(p=>p.id!==project.id);state.bootstrap.projects.unshift(project);
      renderNavigation();await renderTrash();toast('会话已恢复到历史会话，测试不会自动继续。');
    });return true;
  }
  if(button.id==='add-interface'){openInterfaceEditor();return true;}
  if(button.dataset.deleteOperation){openInterfaceEditor(button.dataset.deleteOperation);return true;}
  if(button.dataset.editOperation){openInterfaceEditor(null,button.dataset.editOperation);return true;}
  if(button.id==='confirm-delete-interface'){await withManagementButton(button,'delete-interface-error',()=>saveInterfaceEdit());return true;}
  return false;
}
document.addEventListener('contextmenu',event=>{
  const row=event.target.closest('[data-session-row]');if(!row)return;
  event.preventDefault();openSessionMenu(row.dataset.sessionRow,event.clientX,event.clientY);
});
document.addEventListener('pointerdown',event=>{if(!event.target.closest('#session-menu')&&!event.target.closest('[data-session-menu]'))closeSessionMenu();});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'){closeSessionMenu();return;}
  if(event.key==='ContextMenu'||event.shiftKey&&event.key==='F10'){
    const row=event.target.closest('[data-session-row]');if(!row)return;
    event.preventDefault();const rect=row.getBoundingClientRect();openSessionMenu(row.dataset.sessionRow,rect.right,rect.bottom);
  }
});
$('interface-form').addEventListener('submit',event=>{
  event.preventDefault();withButtonFeedback($('save-interface'),()=>withManagementButton($('save-interface'),'interface-error',()=>saveInterfaceEdit(readInterfaceForm())));
});

init().then(()=>{
  document.body.classList.remove('workspace-loading');
  $('workspace-loading')?.remove();
}).catch(error=>{
  const message=$('workspace-loading-message');
  if(message)message.textContent='页面加载失败：'+error.message+' 请刷新页面重试。';
  toast(error.message,true);
});
