'use strict';
// Account configuration only. Task controls live in the normal test session.
globalThis.ProjectAccountEditor=(()=>{
  const field=(name,label,value='',required=false,type='text')=>`<label>${esc(label)}<input name="${name}" type="${type}" value="${esc(value)}"${required?' required':''}${type==='password'?' autocomplete="new-password"':''}></label>`;
  async function mount(root,pid=''){
    const token=Symbol();root.accountEditor=token;let closed=false,timer,busy=false;
    const current=()=>!closed&&root.isConnected&&root.accountEditor===token;
    function dispose(){closed=true;clearInterval(timer);}
    root.closest('dialog')?.addEventListener('close',dispose,{once:true});
    async function action(button,fn){if(busy||!current())return;busy=true;button.disabled=true;try{await fn();if(current())await render();}catch(e){toast(e.message,true);}finally{busy=false;if(button.isConnected)button.disabled=false;}}
    async function render(){
      const [projects,snap]=await Promise.all([api('/api/account-projects'),api('/api/orchestration')]);if(!current())return;
      const project=projects.projects.find(p=>p.id===pid);
      if(pid&&!project){root.textContent='此项目已删除，请重新选择项目。';return;}
      const accounts=pid?snap.accounts.filter(a=>a.projects.includes(pid)):snap.accounts,available=pid?snap.accounts.filter(a=>!a.projects.includes(pid)&&project.login_url&&(a.login?.url||a.target)===project.login_url):[];
      root.innerHTML=`<div class="project-account-heading"><h3>${pid?'项目账号':'全部账号'} <span class="project-account-count">${accounts.length}</span></h3><div class="managed-buttons">${pid?'<button type="button" class="primary" data-add aria-expanded="false">添加账号</button>':''}<button type="button" data-refresh>刷新账号</button></div></div><div data-accounts></div>${pid?`<section class="project-account-form" data-add-form hidden aria-label="添加账号"><h4>添加账号</h4><form><div class="project-account-grid">${field('identity','账号','',true)}${field('credential','密码','',false,'password')}</div><p class="hint">使用扫码或验证码登录时，密码可留空。</p><div class="managed-buttons"><button type="submit" class="primary">保存账号</button><button type="button" data-cancel-add>取消</button></div></form></section>`:''}${available.length?'<section class="project-existing-accounts"><button type="button" data-bind-toggle aria-expanded="false">绑定已登记的账号</button><div data-existing hidden></div></section>':''}<p class="hint">登录地址由项目统一维护，账号密码可选。编辑和彻底删除影响所有绑定项目；测试身份与共享规则由系统匹配。</p>`;
      root.querySelector('[data-refresh]').onclick=e=>action(e.currentTarget,async()=>{});
      if(pid){
        const add=root.querySelector('[data-add-form]'),button=root.querySelector('[data-add]');
        const toggle=visible=>{add.hidden=!visible;button.setAttribute('aria-expanded',String(visible));if(visible)add.querySelector('input').focus();};
        add.hidden=!!accounts.length;button.setAttribute('aria-expanded',String(!add.hidden));
        button.onclick=()=>toggle(add.hidden);root.querySelector('[data-cancel-add]').onclick=()=>{add.querySelector('form').reset();toggle(false);};
        add.querySelector('form').onsubmit=e=>{e.preventDefault();action(e.submitter,async()=>{const data=Object.fromEntries(new FormData(e.target));await api('/api/orchestration/accounts','POST',{...data,account_project_id:pid});e.target.elements.credential.value='';toast('账号已添加。');});};
      }
      const list=root.querySelector('[data-accounts]');
      if(!accounts.length)list.innerHTML=`<p class="hint">${pid?'未登记账号也可以测试：Codex 优先使用本地已有登录态，没有可用登录态时再询问。':'暂无账号，请在项目中添加账号。'}</p>`;
      for(const a of accounts){
        const bindings=a.projects.map(id=>projects.projects.find(p=>p.id===id)?.name||`历史会话 ${id.slice(-6)}`);
        const bound=bindings.length?bindings.join('、'):'未绑定项目';
        const card=document.createElement('article');card.className='project-account-card';card.dataset.accountId=a.id;
        card.innerHTML=`<div class="project-account-heading"><strong>${esc(a.identity)}</strong></div><p class="hint">${esc([a.tenant,a.roles.join('、')].filter(Boolean).join(' · '))}</p><p class="hint">绑定项目：${esc(bound)}</p><div class="managed-buttons"><button type="button" data-edit>编辑账号</button>${pid?'<button type="button" data-remove>从此项目移除</button>':''}<button type="button" class="project-danger" data-delete>彻底删除账号</button></div><form data-edit-form hidden><div class="project-account-grid">${field('identity','账号',a.identity,true)}${field('credential','新密码（留空保留原密码）','',false,'password')}</div><label class="project-account-choice"><input type="checkbox" name="clear_password">清除已保存密码，改用扫码或验证码登录</label><p class="hint">本次修改影响：${esc(bound)}。执行 Codex 将使用新凭据自行登录。密码不会回显。</p><div class="managed-buttons"><button type="submit">保存修改</button><button type="button" data-cancel-edit>取消</button></div></form>`;
        const form=card.querySelector('[data-edit-form]');
        card.querySelector('[data-edit]').onclick=()=>{form.hidden=false;form.elements.credential.focus();};
        card.querySelector('[data-cancel-edit]').onclick=()=>{form.reset();form.hidden=true;form.elements.credential.disabled=false;};
        form.elements.clear_password.onchange=()=>{form.elements.credential.disabled=form.elements.clear_password.checked;if(form.elements.clear_password.checked)form.elements.credential.value='';};
        form.onsubmit=e=>{e.preventDefault();action(e.submitter,async()=>{const data=Object.fromEntries(new FormData(form));await api(`/api/orchestration/accounts/${a.id}`,'PATCH',{...data,clear_password:form.elements.clear_password.checked,revision:a.revision||1});form.elements.credential.value='';toast('账号已更新。');});};
        if(pid)card.querySelector('[data-remove]').onclick=async e=>{const b=e.currentTarget;if(busy)return;if(await ProjectAccounts.confirmRemoval('移除项目账号',`确定将账号“${a.identity}”从“${project.name}”移除？账号登记和其他项目的绑定保留，需要时可以重新绑定。`,'从此项目移除'))action(b,async()=>{await api(`/api/account-projects/${pid}/accounts/${a.id}`,'DELETE');toast('账号已从当前项目移除。');});};
        card.querySelector('[data-delete]').onclick=async e=>{const b=e.currentTarget;if(busy)return;if(await ProjectAccounts.confirmRemoval('彻底删除账号',`确定彻底删除账号“${a.identity}”？影响项目：${bound}。账号登记、保存的密码和所有项目绑定将被删除，旧登录授权失效；执行机联网后清理该账号的登录缓存。历史测试报告保留。此操作不可撤销。`,'彻底删除账号'))action(b,async()=>{await api(`/api/orchestration/accounts/${a.id}`,'DELETE',{revision:a.revision||1});toast('账号已彻底删除，历史测试报告保留。');});};
        list.append(card);
      }
      const bindToggle=root.querySelector('[data-bind-toggle]');if(bindToggle)bindToggle.onclick=()=>{const box=root.querySelector('[data-existing]');box.hidden=!box.hidden;bindToggle.setAttribute('aria-expanded',String(!box.hidden));};
      for(const a of available){const row=document.createElement('div');row.className='project-account-heading';const label=document.createElement('span');label.textContent=a.identity;const b=document.createElement('button');b.type='button';b.textContent='绑定';b.onclick=()=>action(b,()=>api('/api/orchestration/accounts','POST',{account_project_id:pid,label:a.label,identity:a.identity,environment:a.environment,tenant:a.tenant,roles:a.roles}));row.append(label,b);root.querySelector('[data-existing]').append(row);}
    }
    root.innerHTML='<p class="hint">正在读取账号…</p>';
    try{await render();}catch(e){if(current())root.textContent=e.message;}
    timer=setInterval(async()=>{if(!current()){dispose();return;}if(busy||document.hidden)return;try{const snap=await api('/api/orchestration');if(!current())return;for(const card of root.querySelectorAll('[data-account-id]')){const a=snap.accounts.find(a=>a.id===card.dataset.accountId);if(!a){card.remove();continue;}}}catch{}},5000);
    return dispose;
  }
  async function openInventory(afterClose){
    const d=document.createElement('dialog');d.className='managed-dialog project-accounts-dialog';d.innerHTML='<div class="managed-heading"><h2>全部账号管理</h2><button type="button" data-close>关闭</button></div><div data-body></div>';d.querySelector('[data-close]').onclick=()=>d.close();d.addEventListener('close',()=>{d.remove();afterClose?.();},{once:true});document.body.append(d);d.showModal();await mount(d.querySelector('[data-body]'));
  }
  return {mount,openInventory};
})();
