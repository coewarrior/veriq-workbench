'use strict';
// One persistent business project, many independent test sessions.
globalThis.ProjectAccounts = (()=>{
  function modal(title){const d=document.createElement('dialog');d.className='managed-dialog';d.innerHTML=`<div class="managed-heading"><h2>${esc(title)}</h2><button type="button" data-close>关闭</button></div><div data-body></div>`;d.querySelector('[data-close]').onclick=()=>d.close();d.onclose=()=>d.remove();document.body.append(d);d.showModal();return d;}
  async function picker(root,selected='',name='account_project_id'){
    const data=await api('/api/account-projects');if(!root.isConnected)return;
    root.replaceChildren();
    for(const p of data.projects){const label=document.createElement('label');label.className='project-account-choice';const input=document.createElement('input');input.type='radio';input.name=name;input.required=true;input.value=p.id;input.checked=p.id===selected;label.append(input,document.createTextNode(data.projects.filter(x=>x.name===p.name).length>1?p.name+' · '+p.id.slice(-6):p.name));root.append(label);}
    if(!data.projects.length){const p=document.createElement('p');p.className='hint';p.textContent='暂无项目，请先添加项目并填写产品登录地址；账号密码可不提供。';root.append(p);}
  }
  async function mount(form){
    if(!form||form.querySelector('[data-project-picker]'))return;
    const field=document.createElement('fieldset');field.className='project-account-picker';field.innerHTML='<legend>所属项目</legend><p class="hint">测试地址自动使用所选项目的产品地址。未提供账号密码时，优先使用本地已有登录态。</p><div data-project-picker></div><button type="button" data-manage>配置项目</button>';form.prepend(field);
    const root=field.querySelector('[data-project-picker]');
    const refresh=()=>picker(root,root.querySelector('input:checked')?.value||'');
    field.querySelector('[data-manage]').onclick=()=>open(root.querySelector('input:checked')?.value||'');
    await refresh();
  }
  function confirmRemoval(title,message,label){
    return new Promise(resolve=>{const d=modal(title);d.classList.add('project-accounts-dialog');let accepted=false;
      d.querySelector('[data-body]').innerHTML=`<p>${esc(message)}</p><div class="managed-buttons"><button type="button" data-cancel>取消</button><button type="button" class="project-danger" data-confirm>${esc(label)}</button></div>`;
      d.querySelector('[data-cancel]').onclick=()=>d.close();d.querySelector('[data-confirm]').onclick=()=>{accepted=true;d.close();};d.addEventListener('close',()=>resolve(accepted),{once:true});d.querySelector('[data-cancel]').focus();
    });
  }
  async function open(selected='',afterClose){
    const d=modal('配置项目');d.classList.add('project-accounts-dialog','project-manager-dialog');
    d.addEventListener('close',()=>{afterClose?.();document.querySelectorAll('#ui-test-form [data-project-picker]').forEach(root=>picker(root,root.querySelector('input:checked')?.value||'').catch(e=>toast(e.message,true)));});
    const body=d.querySelector('[data-body]');
    body.innerHTML='<p class="hint project-manager-intro">一个项目对应一个产品，统一维护登录地址和可选账号。</p><div class="project-manager-layout"><aside class="project-manager-sidebar"><div class="project-section-heading"><h3>项目列表</h3><button type="button" class="primary" data-create>新建项目</button></div><nav data-projects aria-label="选择项目"></nav></aside><section class="project-manager-detail" aria-label="当前项目"><div data-project-info></div><div data-resources></div></section></div>';
    let busy=false,editorDispose,view=0,projects=[];
    const list=body.querySelector('[data-projects]'),resources=body.querySelector('[data-resources]'),info=body.querySelector('[data-project-info]');
    d.addEventListener('close',()=>{view++;editorDispose?.();},{once:true});
    async function show(id){
      const current=++view;selected=id;editorDispose?.();resources.accountEditor=null;resources.replaceChildren();
      for(const button of list.querySelectorAll('[data-project-id]')){const active=button.dataset.projectId===id;button.classList.toggle('is-selected',active);button.setAttribute('aria-pressed',String(active));}
      const p=projects.find(p=>p.id===id);
      if(!p){info.innerHTML='<div class="project-empty"><h3>添加第一个项目</h3><p class="hint">点击左侧“新建项目”，填写产品名称和登录地址即可。账号密码可稍后添加，也可以不提供。</p></div>';return;}
      info.innerHTML=`<header class="project-detail-header"><h3>${esc(p.name)}</h3><div class="managed-buttons"><button type="button" data-total-report>项目总报告</button><button type="button" data-edit>编辑项目</button><button type="button" class="project-danger" data-delete>删除项目</button></div></header><p class="project-login-address" title="${esc(p.login_url||'')}"><span>登录地址</span><span class="project-login-value">${esc(p.login_url||(p.login_conflict?'历史登录地址不一致，请编辑项目统一地址。':'请编辑项目补充登录地址。'))}</span></p>`;
      info.querySelector('[data-total-report]').onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{const result=await api(`/api/account-projects/${id}/total-report`);location.href=result.report_url;}catch(error){toast(error.message,true);b.disabled=false;}};
      info.querySelector('[data-edit]').onclick=()=>editProject(p);
      info.querySelector('[data-delete]').onclick=async e=>{const b=e.currentTarget;if(busy)return;if(await confirmRemoval('删除项目',`确定删除“${p.name}”？项目账号绑定和会话归属将解除，历史会话与报告保留。已停止的旧任务不能继续；需要测试时可重新选择项目开始新一轮。账号登记保留，其他项目的绑定不受影响。`,'删除项目'))change(b,async()=>{await api(`/api/account-projects/${p.id}`,'DELETE');toast('项目已删除，历史会话与报告已保留。');});};
      const dispose=await ProjectAccountEditor.mount(resources,id);if(current===view&&d.isConnected)editorDispose=dispose;else dispose?.();
    }
    async function refresh(){
      const data=await api('/api/account-projects');if(!d.isConnected)return;projects=data.projects;
      if(!projects.some(p=>p.id===selected))selected=projects[0]?.id||'';
      list.replaceChildren();
      if(!projects.length)list.innerHTML='<p class="hint">暂无项目</p>';
      for(const p of projects){const button=document.createElement('button');button.type='button';button.className='project-list-item';button.dataset.projectId=p.id;button.textContent=projects.filter(x=>x.name===p.name).length>1?p.name+' · '+p.id.slice(-6):p.name;button.onclick=()=>show(p.id).catch(e=>toast(e.message,true));list.append(button);}
      await show(selected);
    }
    async function change(button,fn){if(busy)return;busy=true;button.disabled=true;try{await fn();await refresh();}catch(e){toast(e.message,true);}finally{busy=false;if(button.isConnected)button.disabled=false;}}
    function editProject(project=null){
      const editor=modal(project?'编辑项目':'新建项目');editor.classList.add('project-accounts-dialog','project-form-dialog');
      editor.querySelector('[data-body]').innerHTML=`<form><label>项目名称<input name="name" required maxlength="200" value="${esc(project?.name||'')}" placeholder="例如：招聘平台"></label><label>产品登录地址<input name="login_url" type="url" required value="${esc(project?.login_url||'')}" placeholder="https://example.com/login"></label><p class="hint">该项目的测试会话自动使用此地址，账号无需重复填写。</p><div class="managed-buttons"><button type="submit" class="primary">${project?'保存项目':'创建项目'}</button><button type="button" data-cancel>取消</button></div></form>`;
      const form=editor.querySelector('form');let request=null,saving=false;
      editor.querySelector('[data-cancel]').onclick=()=>editor.close();
      form.onsubmit=async e=>{e.preventDefault();if(saving)return;saving=true;e.submitter.disabled=true;try{const values=new FormData(form),name=values.get('name').trim(),login_url=values.get('login_url').trim();if(!request||request.name!==name||request.login_url!==login_url)request={name,login_url,request_id:Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('')};const p=await api(project?`/api/account-projects/${project.id}`:'/api/account-projects',project?'PATCH':'POST',request);selected=p.id;editor.close();await refresh();toast(project?'项目信息已更新。':'项目已创建。');}catch(error){toast(error.message,true);}finally{saving=false;if(e.submitter.isConnected)e.submitter.disabled=false;}};
      form.elements.name.focus();
    }
    body.querySelector('[data-create]').onclick=()=>editProject();
    try{await refresh();}catch(e){toast(e.message,true);}
  }
  async function session(){
    const pid=state.project?.id;if(!pid)return;
    const d=modal('会话所属项目'),body=d.querySelector('[data-body]');
    try{
      const {project}=await api(`/api/projects/${pid}/account-project`);
      body.innerHTML='<p>一个项目代表一个产品，统一维护登录地址。账号密码可不提供，Codex 会先复用本地已有登录态，确实缺少登录时再询问。</p><form><div data-projects></div><button type="submit">保存所属项目</button></form><button type="button" data-manage>配置项目</button>';
      const root=body.querySelector('[data-projects]');await picker(root,project?.id||'');
      body.querySelector('[data-manage]').onclick=()=>open(root.querySelector('input:checked')?.value||'',()=>picker(root,root.querySelector('input:checked')?.value||'').catch(e=>toast(e.message,true)));
      body.querySelector('form').onsubmit=async e=>{e.preventDefault();const id=root.querySelector('input:checked')?.value;if(!id){toast('请选择所属项目。',true);return;}e.submitter.disabled=true;try{await api(`/api/projects/${pid}/account-project`,'POST',{account_project_id:id});d.close();await globalThis.ManagedWorkflow?.refresh();toast('所属项目已保存。');}catch(error){toast(error.message,true);}finally{e.submitter.disabled=false;}};
    }catch(e){body.textContent=e.message;}
  }
  function setup(){
    if(document.getElementById('open-project-accounts'))return;
    const b=document.createElement('button');b.id='open-project-accounts';b.className='sidebar-action';b.innerHTML='<svg class="sidebar-action-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h7l2 2h9v12H3z"/></svg><span class="sidebar-action-label">配置项目</span><span class="sidebar-action-trailing">›</span>';b.onclick=()=>open();document.querySelector('.sidebar-management').prepend(b);
  }
  return {setup,mount,open,session,confirmRemoval};
})();
