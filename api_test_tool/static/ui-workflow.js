'use strict';
// UI supplies only its source and execution panels. The API workspace owns
// navigation, sessions, authorization, progress, trash and report rendering.
globalThis.UIWorkflow = (() => {
  const stages = {
    1: ['提交测试资料', '选择所属项目，按需补充测试目标或需求资料。', '资料只需提交一次，后续用例设计、执行和报告由 Codex 推进。'],
    2: ['开始测试', '在同一页查看任务进展，需要补充的条件会集中显示。', '点击开始测试后自动分配资源，模块进展与结果会同步到本会话。'],
    4: ['查看测试结果', '先看结论和待处理事项，再按需查看完整报告与证据。', '补齐条件后可继续未完成项，历史结果保留。']
  };
  const labels = {1:['提交资料','目标与文档'],2:['开始测试','进度与待办'],4:['查看结果','结论与证据']};
  const stage = n => Number(n)===3?2:Number(n);
  let saving = false;
  let attachmentDraft = [];
  let attachmentProject = '';
  // Only the current session's result view is retained, in page memory.
  let resultView = null;
  let unavailableResultVersion = null;
  function hasSavedResults(){
    const p=state.project;
    return Boolean(p?.last_analysis||p?.ui_execution_id||p?.mcp_progress?.modules?.some(m=>m.execution_id));
  }
  function resultVersion(){
    const p=state.project;
    return JSON.stringify([p?.id,p?.title,p?.last_analysis,p?.analysis_reports,p?.last_run,p?.runs,
      p?.ui_execution_id,p?.ui_execution_revision,p?.ui_details_version,p?.mcp_progress?.scope,
      p?.mcp_progress?.modules?.map(m=>[m.project_id,m.task_id,m.node_id,m.execution_id,m.revision,m.correction_revision,m.phase,m.report_saved])]);
  }
  function reuseResultPanel(){
    return Boolean(resultView&&resultView.pid===state.project?.id&&resultView.version===resultVersion()&&resultView.main.isConnected);
  }
  function resetResultView(){resultView=null;unavailableResultVersion=null;$('report-panel').replaceChildren();}
  function refreshResultIfChanged(){
    if(state.stage!==4||reuseResultPanel()||resultVersion()===unavailableResultVersion||(!hasSavedResults()&&!resultView))return;
    renderReports();renderStage(4);
  }
  const attachmentExtensions = ['png','jpg','jpeg','gif','webp','pdf','doc','docx','xls','xlsx','ppt','pptx','txt','md','markdown','csv','tsv','json','yaml','yml','rtf'];
  const attachmentLimit = 50_000_000;
  const fileSize = size => size < 1_000_000 ? `${Math.max(1,Math.ceil(size/1000))} KB` : `${(size/1_000_000).toFixed(1)} MB`;
  function attachmentInput(compact=false) {
    if(compact)return `<div class="ui-attachment-toolbar"><label class="ui-attachment-button">添加附件<input id="test-requirement-files" data-ui-attachment-input type="file" multiple accept="${attachmentExtensions.map(ext=>'.'+ext).join(',')}" aria-describedby="ui-attachment-hint"></label><span id="ui-attachment-hint" class="hint">可拖入文档或粘贴截图 · 最多 10 个 / 50 MB</span></div><ul id="ui-attachment-draft" class="ui-attachment-list" aria-live="polite"></ul>`;
    return `<div class="ui-attachment-section"><div class="ui-attachment-dropzone"><label>需求文档或图片（可选）<input id="test-requirement-files" data-ui-attachment-input type="file" multiple accept="${attachmentExtensions.map(ext=>'.'+ext).join(',')}" aria-describedby="ui-attachment-hint"></label><p id="ui-attachment-hint" class="hint">可选择或拖入图片、PDF、Word、Excel、PPT 和文本文件，也可在测试要求中粘贴截图。最多 10 个，共 50 MB。Markdown / OpenAPI 文档会自动识别。</p></div><ul id="ui-attachment-draft" class="ui-attachment-list" aria-live="polite"></ul></div>`;
  }
  function savedAttachments() {
    const files=state.project?.ui_requirement_attachments||[];
    if(!files.length)return '';
    return `<h3>已保存的任务附件 · ${files.length}</h3><ul class="ui-attachment-list">${files.map(file=>`<li>${file.kind==='image'?`<a href="${esc(file.url)}?preview=true" target="_blank" rel="noopener"><img src="${esc(file.url)}?preview=true" alt="${esc(file.filename)}" loading="lazy"></a>`:'<span class="ui-attachment-icon" aria-hidden="true">文档</span>'}<div><a href="${esc(file.url)}">${esc(file.filename)} ↓</a><small>${fileSize(file.size)}</small></div><button type="button" data-ui-attachment-delete="${esc(file.id)}" aria-label="移除 ${esc(file.filename)}">移除</button></li>`).join('')}</ul>`;
  }
  function resetAttachments() {
    for(const item of attachmentDraft)if(item.preview)URL.revokeObjectURL(item.preview);
    attachmentDraft=[];
  }
  function renderAttachmentDraft() {
    const list=$('ui-attachment-draft');if(!list)return;
    list.innerHTML=attachmentDraft.map((item,index)=>`<li>${item.preview?`<img src="${esc(item.preview)}" alt="${esc(item.file.name)}">`:'<span class="ui-attachment-icon" aria-hidden="true">文档</span>'}<div><span>${esc(item.file.name)}</span><small>${fileSize(item.file.size)}</small></div><button type="button" data-ui-attachment-remove="${index}" aria-label="移除 ${esc(item.file.name)}">移除</button></li>`).join('');
  }
  function addAttachments(files) {
    if(saving)return;
    const saved=state.project?.ui_requirement_attachments||[];
    const added=Array.from(files||[]);
    if(added.length+attachmentDraft.length+saved.length>10)throw Error('测试要求附件最多 10 个。');
    let total=saved.reduce((sum,file)=>sum+file.size,0)+attachmentDraft.reduce((sum,item)=>sum+item.file.size,0);
    for(const file of added) {
      if(!attachmentExtensions.includes(file.name.split('.').pop().toLowerCase()))throw Error('请选择支持的图片或文档格式。');
      if(!file.size)throw Error('测试要求附件不能为空。');
      total+=file.size;
      if(total>attachmentLimit)throw Error('测试要求附件总大小不能超过 50 MB。');
    }
    for(const file of added)attachmentDraft.push({file,preview:/\.(png|jpe?g|gif|webp)$/i.test(file.name)?URL.createObjectURL(file):''});
    renderAttachmentDraft();
  }
  function requiredTarget(value){
    const target=typeof value==='string'?value.trim():'';
    try{
      const parsed=new globalThis.URL(target);
      if(!['http:','https:'].includes(parsed.protocol)||!parsed.hostname||parsed.username||parsed.password||/[\x00-\x1f]/.test(value))throw Error();
    }catch{throw Error('请填写完整的 HTTP(S) 测试地址。');}
    return target;
  }
  async function encodedAttachments(excludedFile=null) {
    const files=[];
    for(const {file} of attachmentDraft) {
      if(file===excludedFile)continue;
      const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',',2)[1]||'');reader.onerror=()=>reject(Error('读取附件失败，请重新选择文件。'));reader.readAsDataURL(file);});
      files.push({filename:file.name,content_base64:content});
    }
    return files;
  }
  const permissionChoices=[
    ['safe','安全测试权限','只执行不产生持久业务影响的操作'],
    ['full','完整功能测试权限','允许合成数据增删改、上传、模型调用、重复与并发；高影响真实业务另行确认'],
    ['maximum','最大权限','允许目标系统和当前账号/租户内的全部测试操作，无需逐项再次确认']
  ];
  const permissionField=(selected='full')=>`<label>执行权限范围<select name="execution_permission" required>${permissionChoices.map(([key,label,detail])=>`<option value="${key}"${key===selected?' selected':''}>${label} — ${detail}</option>`).join('')}</select></label><p class="hint">“最大权限”包含创建、修改、删除、上传、模型调用、并发、外发、发布、付款、启动真实业务和不可逆操作；仍不能凭空提供缺失的账号、真机、屏幕阅读器或系统能力。</p>`;
  const sceneChoices=[['none','不保留测试现场'],['defects','仅保留缺陷现场'],['test_data','保留数据并恢复配置'],['full','保留完整测试现场']];
  function sceneControl({newRound=false}={}){
    const projectId=state.project?.id||'';
    if(!newRound&&state.sceneRetentionProject!==projectId){state.sceneRetentionProject=projectId;state.sceneRetentionDraft=state.project?.ui_scene_retention?.key||'none';}
    const value=newRound?'none':state.sceneRetentionDraft||'none';
    const locked=!newRound&&Boolean(state.project?.ui_execution_id);
    return `<div class="ui-scene-control"><label>测试现场保留<select name="scene_retention" data-scene-retention-scope${locked?' disabled':''}>${sceneChoices.map(([key,label])=>`<option value="${key}"${value===key?' selected':''}>${label}</option>`).join('')}</select></label><p class="hint">${locked?'本轮已开始，下一轮可调整。':'默认清理本轮可核实归属的测试数据；报告和截图始终保留。'}</p></div>`;
  }
  function selectedScene(form){
    return form.querySelector('[data-scene-retention-scope]')?.value||'none';
  }
  function setup() {
    document.title = '需求与页面测试 · 探真 VERIQ';
    globalThis.ProjectAccounts?.setup();
    document.body.classList.add('ui-workspace');
    const stepper=document.querySelector('.stepper');
    stepper.setAttribute('aria-label','测试流程');
    const obsolete=stepper.querySelector('[data-stage="3"]');
    obsolete.hidden=true;obsolete.previousElementSibling.hidden=true;
    const context=document.querySelector('.context-column');
    const details=document.createElement('details');details.className='ui-session-details';
    details.innerHTML='<summary>资料与历史信息</summary>';
    while(context.firstChild)details.append(context.firstChild);
    context.append(details);
    document.querySelector('.brand small').textContent = 'VERIQ · 需求与页面测试';
    document.querySelector('.page-title .eyebrow').textContent = 'UI TEST WORKSPACE';
    document.querySelector('.sidebar-management [data-stage="6"]').hidden = true;
    document.querySelector('.workspace-note p').textContent = '每轮报告保留测试结果与证据，方便修复后回归对比。';
    document.querySelector('.cli-heading strong').textContent = '测试资料';
    document.querySelector('.cli-heading .quiet-tag').hidden = true;
    document.querySelector('.cli-card > p').textContent = '测试目标、执行进度和结果保存在同一会话。';
    document.querySelector('.cli-card .terminal').hidden = true;
    document.querySelector('.cli-setup').hidden = true;
    renderDocument();
    document.addEventListener('submit', submit);
    document.addEventListener('input',event=>{if(event.target.id==='codex-goal')updateAction();});
    document.addEventListener('change', event=>{
      if(event.target.matches('[data-resume-case]')){
        updateAction();
      }else if(event.target.name==='execution_permission'){
        const hint=event.target.closest('.ui-options')?.querySelector('summary .hint');
        if(hint)hint.textContent='权限：'+permissionChoices.find(([key])=>key===event.target.value)?.[1];
      }else if(event.target.matches('[data-ui-attachment-input]')){
        try{addAttachments(event.target.files);}catch(error){toast(error.message,true);}
        event.target.value='';
      } else if(event.target.matches('[data-scene-retention-scope]')&&!event.target.closest('#ui-regression-form'))state.sceneRetentionDraft=event.target.value;
    });
    for(const type of ['dragover','dragleave','drop'])document.addEventListener(type,event=>{
      const zone=event.target.closest('.ui-attachment-dropzone');if(!zone)return;
      event.preventDefault();zone.classList.toggle('dragging',type==='dragover');
      if(type==='drop')try{addAttachments(event.dataTransfer.files);}catch(error){toast(error.message,true);}
    });
    document.addEventListener('paste',event=>{
      if(!['test-goal','codex-goal'].includes(event.target.id)&&!event.target.closest('.ui-attachment-section'))return;
      const files=Array.from(event.clipboardData?.files||[]);if(!files.length)return;
      event.preventDefault();try{addAttachments(files);}catch(error){toast(error.message,true);}
    });
    document.addEventListener('click', event => {
      const remove=event.target.closest('[data-ui-attachment-remove]');
      if(remove){if(saving)return;const [item]=attachmentDraft.splice(Number(remove.dataset.uiAttachmentRemove),1);if(item?.preview)URL.revokeObjectURL(item.preview);renderAttachmentDraft();return;}
      const saved=event.target.closest('[data-ui-attachment-delete]');
      if(saved&&state.project){
        if(saving)return;saving=true;saved.disabled=true;state.managementBusy=true;
        api('/api/ui-tests/'+state.project.id+'/attachments/'+encodeURIComponent(saved.dataset.uiAttachmentDelete),'DELETE').then(result=>{
          state.project=result.project;const list=$('ui-saved-attachments');if(list)list.innerHTML=savedAttachments();toast('附件已移除。');
        }).catch(error=>toast(error.message,true)).finally(()=>{saving=false;state.managementBusy=false;saved.disabled=false;});
        return;
      }
      const cancel=event.target.closest('[data-ui-cancel-regression],[data-ui-cancel-continue]');
      if(cancel){closeTestOptions(cancel.hasAttribute('data-ui-cancel-regression')?'regression':'continue');return;}
      const button=event.target.closest('[data-ui-regression],[data-ui-continue]');
      if(!button||button.disabled||!state.project)return;
      toggleTestOptions(button.hasAttribute('data-ui-regression')?'regression':'continue');
    });
  }
  function renderNavigation() {
    if(!state.bootstrap.projects.length)$('project-list').innerHTML='<p class="sidebar-hint">填写测试资料，开始测试。</p>';
    if(state.project?.ui_import_filename&&!state.project.regression_round)$('model-label').textContent='Codex 授权';
    document.querySelectorAll('.stepper button[data-stage]').forEach(button => {
      const n=Number(button.dataset.stage), label=labels[n];
      if(!label)return;
      button.querySelector('b').textContent=n===4?'3':String(n);
      button.querySelector('span').innerHTML=label[0]+'<small>'+label[1]+'</small>';
      button.classList.toggle('complete',Boolean(n===1&&state.project || n===2&&state.project?.last_analysis));
    });
    updateAction();
    $('project-facts').innerHTML = state.project ? `<div><span>测试类型</span><strong>需求与页面测试</strong></div><div><span>资料来源</span><strong>${state.project.ui_import_filename?'XLSX':state.project.document_kind==='requirements'?'需求文档':'页面目标'}</strong></div><div><span>历史报告</span><strong>${state.project.analysis_reports?.length||0} 份</strong></div>` : '';
  }
  function renderStage(n) {
    $('welcome-panel').hidden = true;
    n=stage(n);if(!stages[n])return;
    $('stage-count').textContent=`${n===4?3:n} / 3`;
    const [title, description, explanation] = stages[n];
    $('stage-title').textContent = title;
    $('stage-description').textContent = description;
    $('stage-explanation').textContent = explanation;
    if(n===1)renderDocument();
    if(n===4&&state.project){
      if(hasSavedResults())renderResultDetails({baseReady:true});
      else{resultView=null;if(!state.project.last_run)$('report-panel').innerHTML='<div class="panel"><h2>暂无测试结果</h2><p class="hint">保存用例或执行结果后，可在这里查看，无需等待最终报告。</p></div>';}
    }
    $('asset-links').innerHTML=n===1&&state.project?`<a href="${artifact('document')}">原始测试资料 ↓</a>`:'';
  }
  async function renderResultDetails({baseReady=false}={}){
    const pid=state.project?.id,report=state.project?.last_analysis,panel=$('report-panel');
    if(!pid||!hasSavedResults())return;
    unavailableResultVersion=null;
    if(!baseReady&&!reuseResultPanel())renderReports();
    if(!report&&!reuseResultPanel())panel.innerHTML=`<div class="panel"><div class="report-title"><span>↗</span><div><h2>${esc(state.project.title)} · 本轮测试结果</h2><p>显示已保存的执行记录，阶段报告尚未发布。</p></div></div><div class="report-actions"></div></div>`;
    const cards=panel.querySelectorAll(':scope > .panel');
    if(cards.length>1&&!cards[1].classList.contains('ui-report-history')){
      const history=cards[1],footer=history.querySelector('.panel-footer');
      footer?.remove();
      const details=document.createElement('details');details.className='panel ui-report-history';
      details.innerHTML=`<summary>阶段报告 · ${state.project.analysis_reports?.length||0} 份</summary>`;
      history.querySelector('h2')?.remove();
      while(history.firstChild)details.append(history.firstChild);
      history.replaceWith(details);
    }
    const main=panel.querySelector('.panel');if(!main)return;
    if(!reuseResultPanel())resultView={pid,version:resultVersion(),main,hasData:false,pending:null,content:null};
    const view=resultView;
    if(view.pending)return view.pending;
    const current=()=>resultView===view&&reuseResultPanel();
    const note=main.querySelector('.ui-result-sync')||document.createElement('p');
    note.className='hint ui-result-sync';note.setAttribute('role','status');
    note.textContent=view.hasData?'已显示上次读取的结果，正在核对更新…':'正在读取整体测试概况…';main.append(note);
    // Always revalidate on entry/manual refresh: corrections can change without
    // changing report IDs or execution revisions. Concurrent reads are shared.
    view.pending=(async()=>{
      try{
        let data;
        try{data=await api(`/api/projects/${pid}/reports/total/report.json`);}
        catch(error){
          // A standalone execution can have saved cases before any stage report.
          if(error.status!==404||report||!state.project?.ui_execution_id||!current())throw error;
          const cache=await globalThis.RequirementsWorkflow.load(pid);
          data={ui_snapshot:cache.records,summary:'当前已保存的执行结果，阶段报告尚未发布。'};
        }
        if(!current())return;
        let records=data.ui_snapshot;
        if(records&&data.imported_results?.cases)records={...records,cases:data.imported_results.cases};
        if(!records&&data.imported_results)records={cases:data.imported_results.cases||[]};
        const content=JSON.stringify([data.summary,records,data.id]);
        if(content!==view.content){
          const summary=main.querySelector('.ui-report-summary')||document.createElement('p');summary.className='ui-report-summary';summary.textContent=data.summary||'报告已保存，完整结论与证据可在报告中查看。';
          main.querySelector('.report-title')?.after(summary);
          if(!report)main.querySelector('.report-actions').innerHTML=data.report_url?`<a class="primary" href="${esc(data.report_url)}">打开本轮完整结果 →</a>`:'';
          if(records){
            records={...records,report_id:data.id};
            const design=records.requirement_design||{};
            const traceability=(design.requirements||[]).map(r=>({...r,case_ids:records.cases.filter(c=>c.requirement_ids?.includes(r.id)).map(c=>c.case_id)}));
            const applied=await globalThis.RequirementsWorkflow?.render(panel,{design:{...design,traceability,requirements_without_cases:traceability.filter(r=>!r.case_ids.length)},records,capabilities:{items:[]},readonly:true});
            if(!current())return;
            if(!applied)throw Error('整体测试概况未能显示，请重试。');
          }else panel.querySelector('[data-requirements-slot]')?.remove();
          view.content=content;view.hasData=true;
        }
        note.textContent='结果已核对更新。';
      }catch(error){
        if(!current())return;
        if([401,403,404].includes(error.status)){
          resetResultView();
          unavailableResultVersion=view.version;
          const card=document.createElement('div');card.className='panel';panel.append(card);card.append(note);
          note.textContent='结果已不可用：'+error.message;
        }else note.textContent=(view.hasData?'更新失败，当前仍显示上次读取的结果：':'概况暂时无法读取：')+error.message;
        const retry=document.createElement('button');retry.type='button';retry.className='text-button';retry.dataset.requirementsRefresh='';retry.textContent='重新读取';note.append(' ',retry);
      }finally{view.pending=null;}
    })();
    return view.pending;
  }
  function renderContext() {
    $('cli-note').textContent = state.project?.ui_import_filename&&!state.project.regression_round ? '已导入执行结果，可以直接查看报告并审核缺陷。' : '先保存测试资料，再点击开始测试。平台自动调度，进度与报告保存在当前会话。';
    $('asset-links').innerHTML=state.stage===1&&state.project?`<a href="${artifact('document')}">原始测试资料 ↓</a>`:'';
  }
  function renderDocument() {
    for(const id of ['document-panel', 'document-target-panel', 'contract-preview'])$(id).hidden = true;
    const panel = $('ui-document-panel');panel.hidden = false;
    const projectId=state.project?.id||'';
    if(attachmentProject!==projectId){resetAttachments();attachmentProject=projectId;panel.innerHTML='';}
    if(state.project) {
      if(panel.querySelector('#ui-information-form')){const list=$('ui-saved-attachments');if(list)list.innerHTML=savedAttachments();const conditions=$('ui-information-conditions');if(!conditions?.querySelector('details[open]'))globalThis.RequirementsWorkflow?.renderInformation(conditions);return;}
      panel.innerHTML = `<div class="panel ui-source-summary"><div class="panel-heading"><h2>${esc(state.project.title)}</h2><span class="quiet-tag">资料已保存</span></div><p class="hint">${state.project.ui_import_filename?'来源：'+esc(state.project.ui_import_filename):'测试地址：'+esc(state.project.ui_target_url||'缺少测试地址')}</p></div><div class="panel"><h2 id="ui-information-heading">补充测试信息</h2><form id="ui-information-form"><label for="codex-goal">测试目标</label><div class="ui-requirements-editor ui-attachment-section ui-attachment-dropzone"><textarea id="codex-goal" name="goal" required maxlength="12000" rows="4">${esc(state.codexGoal??state.project.task?.goal??'')}</textarea>${attachmentInput(true)}</div><label>补充说明（可选）<textarea name="requirements" rows="3" maxlength="30000" placeholder="补充业务规则、验收条件或测试所需信息">${esc(state.project.task?.requirements||'')}</textarea></label><div id="ui-saved-attachments">${savedAttachments()}</div><div class="panel-footer"><button type="submit" class="primary">保存测试信息</button></div></form><div id="ui-information-conditions"></div></div>`;
      renderAttachmentDraft();
      globalThis.RequirementsWorkflow?.renderInformation($('ui-information-conditions'));
      return;
    }
    // Preserve input values when navigating or refreshing connection status.
    if(panel.querySelector('#ui-test-form'))return;
    state.sceneRetentionProject='';state.sceneRetentionDraft='none';
    panel.innerHTML = `<div class="panel ui-start-card"><div class="panel-heading ui-start-meta"><span class="quiet-tag">资料只填一次</span></div><form id="ui-test-form"><label for="test-goal">测试要求（可选）</label><div class="ui-requirements-editor ui-attachment-section ui-attachment-dropzone"><textarea id="test-goal" maxlength="30000" rows="5" placeholder="填写测试目标，或直接粘贴需求原文、业务规则和验收条件。不填则开展完整功能探索测试。"></textarea>${attachmentInput(true)}</div>${sceneControl()}<details class="ui-options"><summary>补充设置 <span class="hint">默认：完整功能测试权限</span></summary><label>会话名称（可选）<input id="test-title" maxlength="200" placeholder="自动使用文件名或测试目标"></label>${permissionField()}</details><div class="panel-footer"><span class="hint">保存后，在“开始测试”中统一发起测试。</span><button class="primary" type="submit">保存测试资料</button></div></form></div><details class="panel ui-import-results"><summary>已有测试结果？导入 XLSX</summary><form id="xlsx-import-form"><label>测试结果文件<input id="xlsx-file" type="file" accept=".xlsx" required></label><details class="ui-options"><summary>报告信息（可选）</summary><div class="form-row"><label>报告名称<input id="xlsx-title" maxlength="200" placeholder="默认使用文件名"></label><label>目标页面<input id="xlsx-target-url" type="url" maxlength="4000" placeholder="https://test.example.com/page"></label></div><div class="form-row"><label>测试环境<select id="xlsx-environment"><option value="">待补充</option>${["dev","test","pre","prod","uat","staging","qa","local"].map(v=>`<option value="${v}">${v}</option>`).join("")}</select></label><label>业务端<select id="xlsx-client"><option value="">待补充</option><option>B端</option><option>C端</option></select></label></div></details><div class="panel-footer"><button type="submit">导入并查看结果 →</button></div></form></details>`;
    globalThis.ProjectAccounts?.mount($('ui-test-form')).catch(error=>toast(error.message,true));

  }
  function updateAction(records){
    if(!state.project)return;
    const progress=CodexProgress.describe(state.project,state.mcpConnection);
    if(records&&state.stage===2)renderScope(records);
    const locked=Boolean(saving||progress.active);
    for(const selector of ['[data-ui-continue]']){
      document.querySelectorAll('#generation-panel '+selector).forEach(action=>{action.disabled=locked&&action.getAttribute('aria-expanded')!=='true';});
    }
    document.querySelectorAll('#ui-test-scope input').forEach(input=>{input.disabled=locked;});
    document.querySelectorAll('[data-ui-regression],#ui-regression-form button,#ui-regression-form input,#ui-regression-form select').forEach(input=>{input.disabled=saving;});
    const button=$('ui-handoff');if(!button)return;
    const current=records||globalThis.RequirementsWorkflow?.current(state.project.id)?.records;
    const reportTime=Date.parse(state.project.last_analysis?.created_at||'')/1000;
    const pendingTask=progress.phase!=='completed'&&progress.updatedAt>reportTime;
    const changedGoal=Boolean(state.codexGoal&&state.codexGoal!==state.project.task?.goal);
    const complete=Boolean(!pendingTask&&!changedGoal&&current?.cases?.length&&current.cases.every(c=>c.status==='passed')&&current.report_id);
    const selected=scopeSelection().selected.length;
    const toggle=$('ui-continue-toggle');if(toggle)toggle.textContent=current?.cases?.length?'继续测试':'开始测试';
    button.disabled=Boolean(locked||(complete&&!selected));
    button.textContent=progress.active?'测试进行中…':selected?'执行所选范围 →':complete?'本轮测试已完成':current?.cases?.length?'确认并继续 →':'开始测试 →';
  }
  let requirementsSync={};
  function refreshRequirements(){
    if(!state.project||state.stage!==2)return;
    const project=state.project;
    const key=JSON.stringify([project.ui_execution_id,project.ui_execution_revision,project.ui_details_version,
      project.mcp_progress?.modules?.map(m=>[m.project_id,m.execution_id,m.revision])]);
    const pid=state.project.id;
    if(requirementsSync.pid!==pid)requirementsSync={pid};
    const sync=requirementsSync;
    if(sync.key===key||sync.pending)return;
    sync.pending=globalThis.RequirementsWorkflow?.load(pid);
    sync.pending?.then(cache=>{
      if(state.project?.id!==pid||requirementsSync!==sync)return;
      sync.key=key;updateAction(cache.records);
    }).catch(error=>{
      if(state.project?.id===pid&&state.stage===2)toast(error.message,true);
    }).finally(()=>{sync.pending=null;});
  }
  function renderPreparation() {
    $('cases-panel').innerHTML='';
    if(!state.project){$('generation-panel').innerHTML=empty('先提交测试资料','上传文档或说明测试目标。','提交资料',1);return;}
    const imported=state.project.ui_import_filename&&!state.project.regression_round;
    $('generation-panel').innerHTML=`<div class="panel ui-test-actions"><h2>测试操作</h2><div class="ui-next-actions ui-action-toggles">${imported?'':'<button type="button" class="ui-action-toggle" id="ui-continue-toggle" data-ui-continue aria-expanded="false" aria-controls="ui-continuation-options">继续测试</button>'}${regressionButton()}</div>${imported?'':'<section id="ui-continuation-options" class="ui-action-options" aria-labelledby="ui-continue-toggle" hidden><div id="ui-test-scope"></div><div class="panel-footer"><button type="button" data-ui-cancel-continue>取消</button><button type="button" class="primary" id="ui-handoff">开始测试 →</button></div></section>'}</div>`;
    requirementsSync={pid:state.project.id};
    if(!imported)refreshRequirements();
    globalThis.ManagedWorkflow?.mount($('generation-panel'));
    updateAction();
  }
  function renderScope(records){
    const slot=$('ui-test-scope'),expanded=$('ui-continuation-options')?.hidden===false;
    if(!slot||(expanded&&slot.querySelector('[data-resume-case]')))return;
    const {selected,reason}=scopeSelection();
    slot.innerHTML=records?.id&&records.cases?.length?`<p class="hint">默认继续未完成项，沿用原订单和已完成步骤；勾选后执行所选用例。</p><div class="ui-case-selection" role="group" aria-label="测试范围">${records.cases.map(c=>`<label><input type="checkbox" data-resume-case="${esc(c.case_id)}"${selected.includes(c.case_id)?' checked':''}> ${esc(c.case_id)} ${esc(c.scenario)}</label>`).join('')}</div><label>本轮备注（可选）<input id="ui-scope-reason" maxlength="4000" value="${esc(reason)}"></label>`:'<p class="hint">根据“提交资料”中已保存的测试地址与目标开展测试。</p>';
  }
  function scopeSelection(){return {selected:[...document.querySelectorAll('#ui-test-scope [data-resume-case]:checked')].map(input=>input.dataset.resumeCase),reason:$('ui-scope-reason')?.value||''};}
  function regressionButton(){return '<button type="button" class="ui-action-toggle" id="ui-regression-toggle" data-ui-regression aria-expanded="false" aria-controls="ui-regression-form">回归测试</button>';}
  function closeTestOptions(kind){
    const panel=$(kind==='continue'?'ui-continuation-options':'ui-regression-form');if(panel)panel.hidden=true;
    $(kind==='continue'?'ui-continue-toggle':'ui-regression-toggle')?.setAttribute('aria-expanded','false');
  }
  function toggleTestOptions(kind){
    const id=kind==='continue'?'ui-continuation-options':'ui-regression-form';
    let panel=document.getElementById(id);
    if(panel&&!panel.hidden){closeTestOptions(kind);return;}
    if(saving||(kind==='continue'&&CodexProgress.describe(state.project,state.mcpConnection).active)){toast('当前测试正在进行，请等待本轮完成。',true);return;}
    closeTestOptions(kind==='continue'?'regression':'continue');
    if(!panel){
      $('ui-regression-toggle').closest('.panel').insertAdjacentHTML('beforeend', `<form id="ui-regression-form" class="ui-action-options" aria-labelledby="ui-regression-toggle" hidden><p class="hint">使用“提交资料”中已保存的测试地址与目标。</p><label>回归范围（可选）<select name="regression_scope"><option value="all">整体回归（全部用例）</option><option value="failed">仅回归错误用例（不通过）</option></select></label>${permissionField(state.project.ui_execution_permission?.key||'full')}${sceneControl({newRound:true})}<p class="hint">建立独立回归轮次，不打断当前探索；报告汇总到原会话。共享账号或浏览器操作会协调占用。</p><div class="panel-footer"><button type="button" data-ui-cancel-regression>取消</button><button type="submit" class="primary">开始回归测试 →</button></div></form>`);
      panel=$(id);
    }
    const current=globalThis.RequirementsWorkflow?.current(state.project.id)?.records;
    if(kind==='continue'&&current)renderScope(current);
    panel.hidden=false;
    $(kind==='continue'?'ui-continue-toggle':'ui-regression-toggle').setAttribute('aria-expanded','true');
    updateAction();panel.scrollIntoView({block:'nearest'});
  }
  function renderExecution(){renderPreparation();}
  async function handoff({prepareContinuation=true}={}) {
    if(saving)return;
    requiredTarget(state.project?.ui_target_url);
    if(CodexProgress.describe(state.project,state.mcpConnection).active)throw Error('当前测试正在进行，请等待本轮完成后再继续。');
    await globalThis.ManagedWorkflow.assertIdle();
    const id=state.project.id, goal=(state.codexGoal||state.project.task?.goal||'').trim();
    if(!goal)throw Error('请填写本轮测试目标。');
    const {selected,reason}=scopeSelection();
    saving=true;state.managementBusy=true;
    updateAction();
    try {
      if(prepareContinuation)await globalThis.RequirementsWorkflow?.prepareContinuation({automatic:!selected.length,selected,reason});
      state.project=await api('/api/projects/'+id+'/task','PUT',{goal,restart_progress:true,scene_retention:state.sceneRetentionDraft||state.project.ui_scene_retention?.key||'none'});
      // Start the saved session without sending users into a separate task workflow.
      if(state.stage===1)goStage(2);
      await globalThis.ManagedWorkflow.start();scheduleMCPSync();
    } finally {saving=false;state.managementBusy=false;updateAction();}
  }
  function message(target, code) {
    const native=(target?.ui_execution_route||target?.execution_route||'native_browser')==='native_browser';
    let entry=`测试台地址：${location.origin}\n接入与执行说明：${location.origin}/static/agent-guide.md\n工具格式：${location.origin}/static/agent-tools.json\n如果当前已加载此地址的 api-test-workspace MCP，使用它；否则读取接入说明，使用免安装 Python 客户端调用同一套工具。\n请使用 connect_workspace 连接，连接码：${code}\n`;
    if(!target)return entry+'连接成功后在当前 Codex 聊天按 '+location.origin+'/static/workspace-usage.json 的 chat_reply 主动给出通用使用指导和两个可复制短语。指导与话术不带任何具体项目地址、项目名或业务模块，不沿用历史测试目标，不把测试台地址当作被测地址。只在聊天中说明，不增加网页操作、不要求填写模板或先选择设置，不主动追问地址和目标。权限与现场保留均为可选，用户已给出任务时直接承接。本次仅授权连接，展示指导后等待我提供任务，不要自行选择历史会话或开始测试。后续我直接给目标页面和测试要求时，使用 start_test_workflow（execution_route=native_browser）创建 UI 会话，由当前聊天中的 Codex 执行，只追问 required_inputs，不要让我先回平台建会话。';
    requiredTarget(target.ui_target_url);
    entry+=`当前聊天角色：coordinator（协调者）。请调用 get_test_document(role="coordinator") 读取平台随包 web-exploratory-testing Skill，按当前会话完整资料协调；不用本机同名旧版替代。\n会话名称：${target.title}\n会话 ID：${target.id}\n目标页面：${target.ui_target_url}\n测试目标：${target.task.goal}\n`;
    entry+=`执行权限：${target.ui_execution_permission?.label||'完整功能测试权限'}（${target.ui_execution_permission?.key||'full'}）\n授权说明：${target.ui_execution_permission?.description||''}\n`;
    const scene=target.ui_scene_retention;
    entry+=`现场保留：${scene?`${scene.label}（${scene.key}）`:'以 get_test_document.scene_retention 为准'}。按本轮已保存设置执行，不擅自降为默认权限或清理方式。\n`;
    const attachments=target.ui_requirement_attachments||[];
    entry+=`测试资料：${attachments.length?attachments.map(file=>file.filename).join('、'):'读取当前会话资料清单'}。读取相关完整原文及表格，不能用文件名或摘要代替原件。\n`;
    entry+='聊天选择（仅 Codex 直接执行路线）：新独立测试（含明确新回归）首次派发使用本轮新建的协调聊天和每模块独立聊天；当前聊天已为本轮新建时直接协调，不递归另建。同轮续测、恢复或重复复制同一 MCP 消息沿本轮真实绑定和检查点继续，不重复创建执行者。具体依据见 references/coordinator.md。\n';
    entry+=native?'执行路径：native_browser。由本轮绑定的各模块独立 Codex 聊天使用执行包的真实隔离浏览器；协调者不领取业务账号。保持原生后端、模型及提速路径。\n':'执行路径：沿当前任务已配置的执行路线和已有绑定，不另起第二个执行者。\n';
    const regression=target.regression_round;
    if(regression?.scope)entry+=`本轮回归范围：${regression.scope_label}。${regression.scope==='failed'?`只重测以下历史不通过用例：${regression.case_ids.join('、')}；包含必要前置和副作用。`:'重测全部基线用例，不只验证历史失败项。'}按 get_test_document.regression_round 执行。\n`;
    entry+=native?'按协调参考区分新独立测试、同轮续测、指定回归和仅设计任务；核对全部目标内范围，不把历史通过算作本轮通过。将 dispatch 返回的每模块 worker_packet 分别交给本轮绑定的执行者，包含原资料、模型、权限和现场设置。\n':'按 Skill 区分新独立测试、同轮续测、指定回归和仅设计任务；保留全部目标内设计，不把历史通过算作本轮通过。沿原执行路线和绑定安排，不切换浏览器后端。\n';
    entry+=native?'读取 references/coordinator.md：一模块一独立 Codex 会话，登记真实 thread ID 后分发独立 worker_packet；派发后在原协调回合执行 coordinator_wait_script 工具内事件等待，只有实际交接/异常才处理。释放者直接通知后继为主，协调者核对未落实的原事件；sent 不等于实际领取，unknown 不重发。已有用例续测使用 continuation_modules/source_node_id 和 resume_record，不覆盖原基线。\n':'协调只在启动、首批设计、真实阻塞/资源事件、收尾纠偏，不逐动作审批或群发催促。旧 local_browser/managed 沿 references/runner-compatibility.md 和原派发说明，不使用 native worker_packet 或 coordinator_wait_script。\n';
    return entry+'范围、判定、证据、授权、S1 停止和收尾统一按 Skill 与本轮配置执行。保存真实结果后返回原报告链接，不自动提交 PingCode 或推送企微。';
  }
  async function submit(event) {
    if(!['ui-test-form','xlsx-import-form','ui-regression-form','ui-information-form'].includes(event.target.id))return;
    event.preventDefault();if(saving)return;
    const button=event.submitter;button.disabled=true;saving=true;state.managementBusy=true;
    const originStage=state.stage;
    try {
      let result;
      if(event.target.id==='ui-information-form') {
        const fields=Object.fromEntries(new FormData(event.target));
        fields.goal=fields.goal.trim();
        if(!fields.goal)throw Error('请填写测试目标。');
        result=await api('/api/ui-tests/'+state.project.id+'/materials','PUT',{...fields,attachments:await encodedAttachments()});
        resetAttachments();
        $('ui-document-panel').innerHTML='';
      } else if(event.target.id==='ui-regression-form') {
        result=await api('/api/ui-tests/'+state.project.id+'/regressions','POST',{...Object.fromEntries(new FormData(event.target)),target_url:requiredTarget(state.project.ui_target_url),scene_retention:selectedScene(event.target)});
        $('ui-document-panel').innerHTML='';
      } else if(event.target.id==='ui-test-form') {
        if(!new FormData(event.target).get('account_project_id'))throw Error('请选择测试所属项目；暂无项目时请先添加项目。');
        const source=attachmentDraft.find(({file})=>/\.(md|markdown|json|ya?ml)$/i.test(file.name))?.file;
        const goal=$('test-goal').value.trim();
        const title=$('test-title').value.trim()||source?.name.replace(/\.[^.]+$/,'')||attachmentDraft[0]?.file.name.replace(/\.[^.]+$/,'')||goal.slice(0,60)||'页面探索测试';
        const common={title,goal,account_project_id:new FormData(event.target).get('account_project_id')||'',execution_permission:new FormData(event.target).get('execution_permission'),scene_retention:selectedScene(event.target),attachments:await encodedAttachments(source)};
        if(source||goal){
          const content=source?await source.text():goal;
          if(!content.trim())throw Error('需求文档不能为空。');
          result=await api('/api/requirement-tests','POST',{...common,filename:source?.name||'requirements.md',content});
          if(result.document_kind==='api'){location.href=result.workspace_url+'?project='+encodeURIComponent(result.project.id);return;}
        }else{
          result=await api('/api/ui-tests','POST',common);
        }
        resetAttachments();
      } else {
        const file=$('xlsx-file').files[0];
        if(!file||!file.name.toLowerCase().endsWith('.xlsx'))throw Error('请选择 .xlsx 文件。');
        if(file.size>10*1024*1024)throw Error('XLSX 文件不能超过 10 MB。');
        const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',',2)[1]||'');reader.onerror=()=>reject(Error('读取 XLSX 文件失败。'));reader.readAsDataURL(file);});
        result=await api('/api/ui-tests/import-results','POST',{filename:file.name,content_base64:content,title:$('xlsx-title').value,target_url:$('xlsx-target-url').value,environment:$('xlsx-environment').value,client:$('xlsx-client').value});
      }
      const existing=state.bootstrap.projects.findIndex(project=>project.id===result.project.id);
      if(existing>=0)state.bootstrap.projects.splice(existing,1);
      state.bootstrap.projects.unshift(result.project);
      state.managementBusy=false;
      if(['ui-test-form','ui-regression-form'].includes(event.target.id)){state.sceneRetentionProject=result.project.id;state.sceneRetentionDraft=result.project.ui_scene_retention?.key||'none';}
      await loadProject(result.project.id,{stage:['ui-regression-form','ui-information-form'].includes(event.target.id)?originStage:undefined});
      if(result.report)goStage(4);
      if(event.target.id==='ui-regression-form'){
        saving=false;state.managementBusy=false;
        try{await handoff({prepareContinuation:false});}catch(error){toast('资料已保存，任务消息未生成：'+error.message,true);return;}
      }
      toast(event.target.id==='ui-information-form'?'测试信息已保存。':result.report?`已导入 ${result.counts.total} 条用例。`:result.regression_round?'已建立独立回归轮次，当前探索保持原状。':'测试资料已保存。');
    } catch(error) {toast(error.message,true);}
    finally {saving=false;state.managementBusy=false;button.disabled=false;}
  }
  return {setup,stage,renderNavigation,renderStage,renderContext,renderDocument,renderPreparation,renderExecution,updateAction,refreshRequirements,renderResultDetails,reuseResultPanel,resetResultView,refreshResultIfChanged,handoff,message};
})();
