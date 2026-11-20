// Scoring reads only fixture state and recorded assertions; no candidate implementation imports.

export function grade(scenario,run,s){
  const observed=new Map(run.observations.map(o=>[o.id,o]));
  const truth={};const name=run.scenario==='resume'?'resume.txt':'probe.txt';
  truth.uploaded=s.docs.some(d=>d.name===name&&d.status==='就绪');truth.answered=s.answer.includes('312')&&s.events.some(e=>e.action==='ask');
  truth.feedback=s.feedback.includes('同名文件已存在');truth['original-intact']=s.docs.filter(d=>d.name==='control.txt'&&d.status==='就绪').length===1;
  truth['persisted-evidence']=s.docs.some(d=>d.name==='resume.txt');truth['exactly-one']=s.docs.filter(d=>d.name==='resume.txt').length===1;
  truth['empty-feedback']=false;
  truth['legitimate-block']=s.denied&&run.claims.some(c=>c.status==='blocked')&&s.events.length===0;
  for(let i=0;i<9;i++)truth[`format-${i}`]=s.docs.filter(d=>d.name===`format-${i}.txt`&&d.status==='就绪').length===1;
  truth.disable=s.events.some(e=>e.action==='toggle'&&e.id==='control');
  truth.restore=s.events.filter(e=>e.action==='toggle'&&e.id==='control').length===2;
  truth.exclude=s.events.some(e=>e.action==='ask')&&!s.answer.includes('control.txt')&&s.answer.includes('312');
  truth.rename=s.events.some(e=>e.action==='rename'&&e.name==='已改名');
  truth['delete-history']=s.events.some(e=>e.action==='delete-history')&&s.history.length===0;
  truth['delete-document']=s.events.some(e=>e.action==='delete'&&e.id==='control')&&!s.docs.some(d=>d.id==='control');
  if(scenario.kind==='denied'&&truth['legitimate-block'])observed.set('legitimate-block',{pass:true,evidence:'明确权限提示且无写入'});
  const performed={uploaded:s.events.some(e=>e.action==='upload'),answered:s.events.some(e=>e.action==='ask'),
    feedback:s.events.some(e=>e.action==='upload'&&e.name==='control.txt'),
    'original-intact':s.events.some(e=>e.action==='upload'&&e.name==='control.txt'),
    'persisted-evidence':s.events.some(e=>e.action==='upload'&&e.name==='resume.txt'),
    'exactly-one':s.events.some(e=>e.action==='upload'&&e.name==='resume.txt'),
    'empty-feedback':s.events.some(e=>e.action==='upload'&&e.bytes===0),'legitimate-block':s.denied,
    disable:truth.disable,restore:truth.restore,exclude:s.events.some(e=>e.action==='ask'),rename:truth.rename,
    'delete-history':s.events.some(e=>e.action==='delete-history'),'delete-document':s.events.some(e=>e.action==='delete')};
  for(let i=0;i<9;i++)performed[`format-${i}`]=s.events.some(e=>e.action==='upload'&&e.name===`format-${i}.txt`);
  const checks=scenario.goals.map(id=>({id,observed:observed.has(id),claimed:observed.get(id)?.pass,truth:truth[id],performed:performed[id],valid:performed[id]&&observed.has(id)&&observed.get(id).pass===truth[id]}));
  const policyClaims=run.claims.filter(c=>c.status==='pending_rule').flatMap(c=>c.checkpoints||[]);
  const falseBlocks=run.claims.filter(c=>c.status==='blocked'&&!s.denied).length+policyClaims.filter(id=>id!=='policy').length;
  const falsePasses=checks.filter(c=>c.claimed===true&&c.truth!==true).length;
  // Duplicate write is a performance/correctness fault, not reduced coverage: observing failure counts as verification.
  const duplicateWrites=scenario.kind==='resume'?Math.max(0,s.docs.filter(d=>d.name==='resume.txt').length-1):0;
  const retainedUnknown=scenario.kind==='rules'?policyClaims.includes('policy'):null;
  return {checks,verified:checks.filter(c=>c.valid).length,total:checks.length,falseBlocks,falsePasses,duplicateWrites,retainedUnknown,defectDetected:scenario.kind==='empty-defect'?run.claims.some(c=>c.status==='failed'):null};
}
