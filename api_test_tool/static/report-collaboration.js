/* Shared report revisions; never reload a collaborator's unsaved form. */
(function(root){
'use strict';
const base=document.querySelector('meta[name="report-collaboration-base"]')?.content;
if(!base)return;
let revision=null;
const notice=document.createElement('aside');notice.className='rr-collaboration';
notice.setAttribute('aria-live','polite');notice.style.cssText='padding:12px 16px;margin:12px 0;border:1px solid #9aa9c5;border-radius:12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap';
const label=document.createElement('span');label.textContent='共享报告 · 所有已登录账号可协作修改，原始执行证据保留。';
const refresh=document.createElement('button');refresh.type='button';refresh.textContent='刷新共同修改';refresh.hidden=true;
refresh.onclick=()=>{if(!document.querySelector('dialog[open], [data-editing="true"]')||window.confirm('刷新会关闭当前窗口并丢弃尚未保存的修改，是否继续？'))location.reload();};
notice.append(label,refresh);
const reportBase=base.replace(/\/collaboration$/,'');
if(!/\/reports\/total$/.test(reportBase)){
 const edit=document.createElement('button');edit.type='button';edit.textContent='修改报告说明';notice.append(edit);
 edit.onclick=async()=>{
  edit.disabled=true;
  try{
   const response=await fetch(reportBase+'/report.json');if(!response.ok)throw Error('无法读取报告，请重新登录或刷新');
   const saved=await response.json();
   const dialog=document.createElement('dialog');dialog.className='rr-case-dialog';
   dialog.innerHTML='<h2>修改报告说明</h2><p>所有协作者共用这份修改，原始报告保留。总报告结论仍按最新阶段用例汇总。</p><form><label>报告标题<input name="title" required maxlength="200"></label><label>报告总结<textarea name="summary" rows="8" maxlength="30000"></textarea></label><p role="alert"></p><div><button type="button" data-cancel>取消</button><button type="submit">保存共同修改</button></div></form>';
   const form=dialog.querySelector('form'),title=form.elements.title,summary=form.elements.summary;
   title.value=saved.title||'';summary.value=saved.summary||'';
   const dirty=()=>title.value!==(saved.title||'')||summary.value!==(saved.summary||'');
   const cancel=()=>{if(!dirty()||window.confirm('放弃尚未保存的报告说明？'))dialog.close();};
   dialog.querySelector('[data-cancel]').onclick=cancel;
   dialog.addEventListener('cancel',event=>{event.preventDefault();cancel();});
   dialog.addEventListener('close',()=>dialog.remove(),{once:true});
   form.onsubmit=async event=>{
    event.preventDefault();const button=form.querySelector('[type=submit]'),message=form.querySelector('[role=alert]');button.disabled=true;
    try{
     const authResponse=await fetch('/api/auth/me');const auth=await authResponse.json();
     const result=await fetch(reportBase+'/report-corrections',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':auth.csrf},body:JSON.stringify({revision:saved.case_corrections?.revision||0,fields:{title:title.value,summary:summary.value}})});
     const body=await result.json();if(!result.ok)throw Error(body.detail||'保存失败');location.reload();
    }catch(error){message.textContent=error.message;button.disabled=false;}
   };
   document.body.append(dialog);dialog.showModal();
  }catch(error){window.alert(error.message);}finally{edit.disabled=false;}
 };
}
async function check(){
 if(document.hidden)return;
 try{
  const response=await fetch(base);if(!response.ok)return;
  const state=await response.json();
  if(revision!==null&&state.revision!==revision){const last=state.history.at(-1);label.textContent=`报告已有共同修改${last?.actor?' · '+last.actor:''}，刷新后查看最新状态；当前输入保留。`;refresh.hidden=false;}
  if(revision===null){revision=state.revision;(document.querySelector('.rr-shell')||document.querySelector('main')||document.body).prepend(notice);}
 }catch{}
}
async function handoff(button,result={},instruction='请读取 get_test_document 和当前待确认操作的持久化结论，读取 action_context 并优先回到原浏览器标签或操作链接，核对原对象的人工操作成功状态后从暂停位置继续指定用例；保留前序观察，不从首页重跑，不重复创建订单或付款。保存真实结果及证据。'){
 const response=await fetch('/api/auth/me');if(!response.ok)throw Error('请先登录');
 const auth=await response.json();
 const pairResponse=await fetch(base+'/pair',{method:'POST',headers:{'X-CSRF-Token':auth.csrf}});
 const pair=await pairResponse.json();if(!pairResponse.ok)throw Error(pair.detail||'无法生成协作连接');
 const projectId=result.project?.id||(await (await fetch(base)).json()).project_id;
 const message=code=>`测试台地址：${location.origin}\n接入与执行说明：${location.origin}/static/agent-guide.md\n工具格式：${location.origin}/static/agent-tools.json\n连接码：${code}\n会话 ID：${projectId}\n${instruction}连接仅授权当前报告关联会话。保留原报告，在同一会话发布新的阶段报告；不得自动提交缺陷或发送通知。`;
 let prompt=message(pair.code);
 function openMessage(){
  const dialog=document.createElement('dialog');dialog.className='rr-case-dialog rr-mcp-dialog';dialog.setAttribute('aria-labelledby','rr-mcp-title');
  dialog.innerHTML='<button class="rr-case-close" type="button" aria-label="关闭连接窗口">×</button><h2 id="rr-mcp-title">把测试任务发给 Codex</h2><p>复制完整消息发给 Codex，继续当前报告对应的测试任务。</p><p class="rr-mcp-hint">连接仅授权当前报告关联会话，连接码 10 分钟内有效、仅可用一次，请勿公开。</p><details><summary>查看完整任务消息</summary><textarea readonly rows="8" aria-label="报告协作继续测试消息"></textarea></details><div class="rr-mcp-actions"><button type="button" class="rr-retest-primary" data-copy>复制消息</button><button type="button" data-renew>重新生成连接码</button><span role="status" aria-live="polite"></span></div>';
  const field=dialog.querySelector('textarea'),feedback=dialog.querySelector('[role=status]');field.value=prompt;
  dialog.querySelector('.rr-case-close').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{dialog.remove();if(button.isConnected)button.focus();},{once:true});
  dialog.querySelector('[data-copy]').onclick=async()=>{
   let copied=false;
   try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(field.value);copied=true;}}catch{}
   if(!copied){
    const helper=document.createElement('textarea');helper.value=field.value;helper.style.cssText='position:fixed;opacity:0;left:0;top:0';dialog.append(helper);helper.select();
    try{copied=document.execCommand('copy');}catch{}finally{helper.remove();}
   }
   feedback.textContent=copied?'已复制，请发给 Codex。':'浏览器限制复制，请选中完整消息手动复制。';
   if(!copied){dialog.querySelector('details').open=true;field.focus();field.select();}
  };
  const renew=dialog.querySelector('[data-renew]');
  renew.onclick=async()=>{
   renew.disabled=true;feedback.textContent='正在生成连接码…';
   try{
    const response=await fetch(base+'/pair',{method:'POST',headers:{'X-CSRF-Token':auth.csrf}});
    const next=await response.json();if(!response.ok)throw Error(next.detail||'无法生成协作连接');
    prompt=message(next.code);field.value=prompt;feedback.textContent='连接码已更新，请重新复制消息。';
   }catch(error){feedback.textContent=error.message;}finally{renew.disabled=false;}
  };
  document.body.append(dialog);dialog.showModal();dialog.querySelector('[data-copy]').focus();
 }
 // Reopening the message must not submit the already-saved confirmation again.
 button.disabled=false;
 button.onclick=event=>{event.stopPropagation();openMessage();};
 openMessage();
}
root.ReportCollaboration={handoff};
check();setInterval(check,15000);document.addEventListener('visibilitychange',check);
})(globalThis);
