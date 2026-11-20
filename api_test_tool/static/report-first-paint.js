/* Hand off only when the current report has synchronously finished mounting. */
(function(root){
'use strict';
let ready=false,stylesUnavailable=false;
function failed(){
 if(ready)return;
 const original=document.getElementById('rr-original');
 if(original){
  for(const node of Array.from(original.children)){
   if(node.tagName==='HEADER'||node.tagName==='MAIN')document.body.append(node);
  }
 }
 const incomplete=document.querySelector('[data-rr-enhanced]');
 if(incomplete)incomplete.remove();
 const status=document.getElementById('rr-first-paint-status');
 if(status)status.textContent='报告交互视图未能载入，请展开下方报告正文查看结果与证据。';
 const initial=document.getElementById('rr-first-paint');
 if(initial)initial.setAttribute('aria-busy','false');
}
function assetError(event){
 const target=event.target,url=target&&(target.src||target.href)||event.filename||'';
 if(/\/report-review\.css(?:[?#]|$)/.test(url))stylesUnavailable=true;
 if(/\/report-review\.(?:js|css)(?:[?#]|$)/.test(url))failed();
}
function complete(){
 ready=true;
 for(const id of ['rr-first-paint','rr-first-paint-fallback']){
  const node=document.getElementById(id);if(node)node.remove();
 }
 document.body.classList.remove('rr-pending');
 root.removeEventListener('error',assetError,true);
}
root.ReportFirstPaint={complete,failed,canMount:()=>!stylesUnavailable};
root.addEventListener('error',assetError,true);
document.addEventListener('DOMContentLoaded',function(){if(!ready)failed();},{once:true});
})(globalThis);
