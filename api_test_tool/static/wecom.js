(()=>{'use strict';
const endpoint='/api/integrations/wecom';
let csrf;
async function call(url,method='GET',body){
 if(method!=='GET'&&!csrf){const r=await fetch('/api/bootstrap');if(!r.ok)throw Error('请先登录测试平台');csrf=(await r.json()).csrf;}
 const r=await fetch(url,{method,headers:{'Content-Type':'application/json',...(csrf?{'x-csrf-token':csrf}:{})},...(body?{body:JSON.stringify(body)}:{})});
 const data=await r.json();if(!r.ok)throw Error(data.detail||'操作失败，请重试');return data;
}
async function busy(button,status,action){button.disabled=true;status.textContent='处理中…';try{await action();}catch(e){status.textContent=e.message;}finally{button.disabled=false;}}
function pushControl(path){
 const bar=document.createElement('div');bar.className='wecom-report-actions';
 const button=document.createElement('button');button.className='pc-secondary';button.textContent='推送到企微';button.type='button';
 const status=document.createElement('span');status.setAttribute('role','status');
 button.onclick=()=>busy(button,status,async()=>{const result=await call(path,'POST');status.textContent=result.message||'已推送';});
 bar.append(button,status);return bar;
}
const mountedForms=new WeakSet();
function mountSettings(){
 const form=document.getElementById('wecom-config');
 if(!form||mountedForms.has(form))return;
 mountedForms.add(form);
 const status=document.getElementById('wecom-status'),test=document.getElementById('wecom-test');
 async function load(){const c=await call(endpoint);form.elements.report_base_url.value=c.report_base_url||location.origin;form.elements.webhook.value='';form.elements.auto_push.checked=c.auto_push===true;test.disabled=!c.configured;status.textContent=c.configured?'已配置 · '+(c.auto_push?'自动推送':'手动推送'):'尚未配置';}
 form.onsubmit=e=>{e.preventDefault();busy(e.submitter,status,async()=>{await call(endpoint,'PUT',{...Object.fromEntries(new FormData(form)),auto_push:form.elements.auto_push.checked});await load();status.textContent='已保存 · '+(form.elements.auto_push.checked?'自动推送':'手动推送');});};
 test.onclick=()=>busy(test,status,async()=>{await call(endpoint+'/test','POST');status.textContent='测试消息已发送，请在群里查看';});
 document.getElementById('wecom-clear').onclick=e=>{if(confirm('清除当前账号的企微机器人配置？'))busy(e.target,status,async()=>{await call(endpoint,'DELETE');await load();});};
 load().catch(e=>{status.textContent=e.message;});
}
window.WeComSettings={mount:mountSettings};
mountSettings();
const match=location.pathname.match(/^\/api\/projects\/([a-f0-9-]+)\/(reports|load-reports)\/([a-f0-9-]+)\/index.html$/);
if(match&&!document.querySelector('meta[name="api-test-public-report"]')){
 const main=document.querySelector('main')||document.body;
 const bar=pushControl(`/api/projects/${match[1]}/${match[2]}/${match[3]}/wecom`);
 const actions=document.querySelector('.rr-heading-actions');
 if(actions)actions.prepend(bar);else{bar.style.cssText='display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:8px 0;font-size:13px';const overview=main.querySelector('.report-overview,header');if(overview)overview.before(bar);else main.prepend(bar);}
}
document.addEventListener('click',event=>{
 const button=event.target.closest('[data-wecom-path]');if(!button)return;
 const status=button.parentElement.querySelector('[data-wecom-status]')||document.createElement('span');
 if(!status.isConnected){status.dataset.wecomStatus='';status.setAttribute('role','status');button.after(status);}
 busy(button,status,async()=>{const result=await call(button.dataset.wecomPath,'POST');status.textContent=result.message||'已推送';});
});
})();
