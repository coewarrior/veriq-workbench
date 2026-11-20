/* Same report UI and source actions; no aggregate-owned defect state. */
(()=>{
'use strict';
const node=document.getElementById('report-review-data');
if(!node)return;
const data=JSON.parse(node.textContent),a=data.aggregate;
if(!a)return;
window.ReportAggregateHeaders=()=>({'X-Project-Report':a.id,'X-Project-Revision':a.revision||''});
function mount(){
 const target=document.querySelector('.rr-heading');if(!target)return;
 const section=document.createElement('section');section.className='rr-scene';section.setAttribute('aria-label','项目汇总范围');
 const title=document.createElement('strong');title.textContent='项目自动汇总 · '+({ready:'已更新',updating:'正在更新',queued:'等待后台汇总',failed:'更新失败，自动重试'}[a.status]||a.status);
 const message=document.createElement('p');message.textContent=a.message||'后台增量更新；每项审核仍保存到原报告。'+(a.generated_at?' 最近汇总：'+new Date(a.generated_at).toLocaleString():'');
 const refresh=document.createElement('button');refresh.type='button';refresh.textContent='刷新总报告';refresh.onclick=()=>location.reload();
 section.append(title,message,refresh);
 if(a.notices?.length){const list=document.createElement('ul');for(const text of a.notices){const item=document.createElement('li');item.textContent=text;list.append(item);}section.append(list);}
 const ranges=document.createElement('details'),summary=document.createElement('summary');summary.textContent='会话、版本与环境范围';ranges.append(summary);
 for(const m of a.members||[]){const p=document.createElement('p');p.textContent=m.title+' · '+(m.test_kind||'')+' · '+(m.status==='missing'?'来源不可用':m.status==='reported'||m.status==='executed'?'已有结果':'待完成');ranges.append(p);}
 for(const [scope,counts] of Object.entries(a.scopes||{})){const p=document.createElement('p');p.textContent=scope+'：'+counts.total+' 条，通过 '+(counts.passed||0)+'，失败 '+(counts.failed||0)+'，其余 '+(counts.total-(counts.passed||0)-(counts.failed||0));ranges.append(p);}
 for(const item of a.analysis||[]){const p=document.createElement('p');p.textContent=item.title+'：'+item.content;ranges.append(p);}
 section.append(ranges);target.after(section);
 if(a.status!=='ready'||!(data.cases||[]).length){const empty=document.querySelector('.rr-empty h3');if(empty&&!(data.cases||[]).length)empty.textContent='后台尚未形成完整汇总';}
}
// This script runs before report-review so headers exist for every review client.
if(document.readyState!=='complete')document.addEventListener('DOMContentLoaded',mount,{once:true});else queueMicrotask(mount);
})();
