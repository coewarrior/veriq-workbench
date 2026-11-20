/* Explicit business-rule answers shared by report cases and later regression. */
(function(root){
'use strict';
const review=root.ReportReview,data=review?.data;
if(!data?.ruleBase)return;
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state={revision:0,questions:[]},loading,csrf='';
const section=document.createElement('section');section.id='rr-rule-questions';section.className='rr-rule-questions';section.hidden=true;
document.querySelector('#rr-cases .rr-case-tools')?.after(section);
function presentation(question){
 const affected=review.cases.filter(c=>question.affected_case_ids.includes(c.case_id));
 const legacy=Array.isArray(question.report_case_ids);
 const analysis=affected.map(c=>c.wording_corrected_at?c.conclusion:c.ai_analysis||c.conclusion).filter(Boolean).join('\n');
 const scenario=affected.map(c=>c.scenario||'').join(' ');
 // Translate this recorded ambiguity into a question, never choose its answer.
 if(legacy&&/恶意指令/.test(scenario)&&/拒绝/.test(analysis)&&/转述|引用/.test(analysis)&&/是否.*禁止/.test(analysis)){
  return {observation:'记录显示：AI 拒绝了文件里的恶意指令，但回答中仍引用了那段指令。',
   question:'AI 拒绝执行恶意指令后，回答里可以引用它吗，还是必须完全隐藏？',
   placeholder:'例如：允许引用，但不能执行；或者：回答中也不允许出现恶意指令。请按实际产品要求填写。',
   raw:[analysis,question.detail].filter(Boolean).join('\n\n')};
 }
 return {observation:legacy?(analysis||'这条用例还缺少明确的判断标准，暂时无法确认结果。'):'',
  question:legacy?`请说明“${question.title}”在这个场景下应该怎样处理。`:(question.detail||question.title),
  placeholder:'写清这个场景下允许什么、禁止什么，或应该出现什么结果。',
  raw:legacy?question.detail:''};
}
function markup(questions){
 return questions.map(q=>{
  const copy=presentation(q);
  return `<article class="rr-rule-card" data-rule-id="${esc(q.id)}"><div class="rr-rule-heading"><strong>${esc(q.title)}</strong><span>${q.status==='resolved'?'规则已明确':'待你确认'} · ${q.affected_case_ids.length} 条用例</span><button type="button" data-rule-open>${q.status==='resolved'?'修改规则':'填写答案'}</button></div>${copy.observation?`<div class="rr-rule-observation"><strong>目前测到的情况</strong><p>${esc(copy.observation)}</p></div>`:''}<div class="rr-rule-question"><strong>需要你确认的问题</strong><p>${esc(copy.question)}</p></div>${q.status==='resolved'?`<p class="rr-rule-answer">你的答案：${esc(q.resolution)}</p><p>依据：${esc(q.basis)}</p>`:''}<form class="rr-rule-form" hidden><label>你的答案<textarea name="resolution" required maxlength="10000" rows="3" placeholder="${esc(copy.placeholder)}">${esc(q.resolution||'')}</textarea></label><label>依据<input name="basis" required maxlength="4000" placeholder="例如：需求文档第几条，或产品负责人确认" value="${esc(q.basis||'')}"></label><p class="rr-rule-note">保存后回到 UI 测试台发起回归，AI 将按你的答案重新验证这条用例。</p><p class="rr-rule-error" role="alert" hidden></p><div class="rr-rule-actions"><button type="button" data-rule-cancel>取消</button><button type="submit">保存答案</button></div></form>${copy.raw?`<details class="rr-rule-raw"><summary>查看原始记录</summary><pre>${esc(copy.raw)}</pre></details>`:''}<details><summary>查看关联用例</summary><p>${esc(q.affected_case_ids.join('、'))}</p></details></article>`;
 }).join('');
}
function render(){
 section.hidden=!state.questions.length;
 section.innerHTML=`<h3>需要明确的业务规则</h3><p>每个规则填写一次，关联用例在回归时共用你的结论和依据。</p>${markup(state.questions)}`;
 const detail=document.getElementById('rr-case-dialog');
 if(detail?.open&&detail.ruleCase)attach(detail,detail.ruleCase);
}
async function read(){
 if(loading)return loading;
 loading=(async()=>{
  const response=await fetch(data.ruleBase);let result={};try{result=await response.json()}catch{}
  if(!response.ok)throw Error(result.detail||'无法读取规则问题，请刷新报告后重试');
  state=result;return state;
 })();
 try{return await loading}finally{loading=null}
}
function bind(container){
 container.addEventListener('click',event=>{
  const button=event.target.closest('[data-rule-open],[data-rule-cancel]');if(!button)return;
  const form=button.closest('[data-rule-id]').querySelector('form');
  form.hidden=button.hasAttribute('data-rule-cancel');
  if(!form.hidden)form.elements.resolution.focus();
 });
 container.addEventListener('submit',async event=>{
  const form=event.target.closest('.rr-rule-form');if(!form)return;
  event.preventDefault();const button=form.querySelector('[type="submit"]'),error=form.querySelector('.rr-rule-error');
  if(button.disabled)return;button.disabled=true;error.hidden=true;
  try{
   if(!csrf){const response=await fetch('/api/bootstrap');if(!response.ok)throw Error('会话已失效，请重新登录');csrf=(await response.json()).csrf;}
   const questionId=form.closest('[data-rule-id]').dataset.ruleId,fields=Object.fromEntries(new FormData(form));
   const response=await fetch(`${data.ruleBase}/${encodeURIComponent(questionId)}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({...fields,revision:state.revision})});
   let result={};try{result=await response.json()}catch{}
   if(!response.ok){
    if(response.status===400&&String(result.detail).includes('已更新'))try{
     await read();const current=state.questions.find(q=>q.id===questionId);
     result.detail+='；你的输入已保留。当前保存的结论：'+(current?.resolution||'尚未明确')+'。请核对后重新保存。';
    }catch{}
    throw Error(result.detail||'规则结论未保存，请重试');
   }
   state=result;render();
   await root.ReportRetest?.refresh();
   function savedNotice(){
    const notice=document.createElement('p');notice.className='rr-rule-saved';notice.setAttribute('role','status');notice.textContent='规则结论已保存。';
    notice.textContent='规则结论已保存。可继续确认其他规则，再到“用例补测”统一选择并发起。保存不会执行测试或改变原报告结果。';
    return notice;
   }
   section.prepend(savedNotice());
   const detail=document.getElementById('rr-case-dialog');if(detail?.open)detail.querySelector('.rr-case-rules')?.prepend(savedNotice());
  }catch(problem){error.textContent=problem.message;error.hidden=false;}
  finally{button.disabled=false;}
 });
}
function attach(detail,caseItem){
 detail.ruleCase=caseItem;
 let slot=detail.querySelector('.rr-case-rules');if(!slot){
  slot=document.createElement('section');slot.className='rr-case-rules';
  detail.querySelector('h2')?.after(slot);bind(slot);
 }
 const questions=state.questions.filter(q=>q.affected_case_ids.includes(caseItem.case_id));
 const analysis=detail.querySelector('.rr-case-analysis');
 if(analysis)analysis.hidden=questions.some(q=>Array.isArray(q.report_case_ids));
 slot.hidden=!questions.length;
 slot.innerHTML=markup(questions);
 if(caseItem.status==='pending_rule'){const form=slot.querySelector('form');if(form)form.hidden=false;}
}
root.ReportRules={attach};bind(section);
read().then(render).catch(error=>{
 section.hidden=false;
 section.innerHTML='<h3>业务规则</h3><p role="alert"></p><button type="button">重新读取规则</button>';
 section.querySelector('p').textContent=error.message;
 section.querySelector('button').onclick=()=>read().then(render).catch(problem=>{section.querySelector('p').textContent=problem.message});
});
})(window);
