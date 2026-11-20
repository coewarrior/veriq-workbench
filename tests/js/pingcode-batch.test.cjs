const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const triage=require('../../api_test_tool/static/pingcode-triage.js');
const record=(id,status='regression_passed')=>({status:'submitted',triage_status:status,item:{id},target:{base_url:'https://example.test',project_id:'p',api_version:'pjm'},updated_at:'v1',lineage:{source_draft_id:'finding-0'}});
function harness(values){
 const records=new Map(values),checks=new Map(values.map(([id])=>[id,true])),writes=[];
 const source=fs.readFileSync(require.resolve('../../api_test_tool/static/pingcode.js'),'utf8');
 const code=source.slice(source.indexOf('async function setLifecycles('),source.indexOf('window.PingCodeReview='));
 const context=vm.createContext({records,triage,sending:false,currentDraft:null,currentButton:null,batchEntries:null,dialog:null,
  backgroundJobs:new Map(),busyDrafts:new Set(),appliedBatchItems:new Map(),batchPolling:false,publicReport:false,batchPollTimer:null,
  reportPath:['','p','r'],buttons:new Map(values),isBusy:id=>context.busyDrafts.has(id),newJobId:()=> 'job',
  window:{},document:{hidden:false},setTimeout(){},clearTimeout(){},updateSelection(){},
  draftProject:()=> 'p',draftReport:()=> 'r',draftSourceId:id=>id,
  settleSelection:(id,result)=>checks.set(id,triage.keepBatchSelection(result)),
  call:async(url,method,body)=>{if(!method)return {values:[]};writes.push({url,body});return {...body,owner:'owner',project_id:'p',run_id:'r',status:'queued',created_at:'1',updated_at:'1',items:body.items.map(item=>({...item,outcome:'queued'}))};}
 });vm.runInContext(code,context);return {context,checks,writes};
}
function complete(h,job,outcomes){h.context.acceptJobUpdates([{...job,status:'completed',updated_at:'2',items:job.items.map((item,i)=>({...item,outcome:outcomes[i],finished_at:'2',record:h.context.records.get(item.draft_id)}))}]);}
test('accept/reopen preserve regression eligibility and never treat failed regression as acceptable',()=>{
 assert.equal(triage.batchEligibility(record('a'),'accept').kind,'ready');
 assert.equal(triage.batchEligibility(record('a','regression_failed'),'accept').kind,'skip');
 assert.equal(triage.batchEligibility(record('a','regression_failed'),'reopen').kind,'ready');
 assert.equal(triage.batchEligibility({...record('a'),remote_sync:{status:'unknown'}},'accept').kind,'skip');
 assert.equal(triage.batchEligibility({...record('a'),remote_sync:{status:'unknown'}},'refresh').kind,'ready');
 assert.equal(triage.batchEligibility({...record('a'),remote_state:{id:'accepted'},remote_state_action:'accept'},'accept').kind,'noop');
});
test('partial completion clears success and unknown but retains definite failures, without changing regression results',async()=>{
 const h=harness(['ok','fail','unknown'].map(id=>[id,record(id)]));
 const result=await h.context.runBatch(['ok','fail','unknown'],'accept');
 assert.equal(result.status,'queued');assert.equal(h.context.sending,false);
 assert.deepEqual([...h.checks.values()],[true,true,true]);
 complete(h,result,['success','failed','unknown']);
 assert.deepEqual([...h.checks.values()],[false,true,false]);
 assert.equal(h.context.records.get('fail').triage_status,'regression_passed');
});
test('frozen preview revisions are passed to the worker and rejected items remain selected',async()=>{
 const h=harness([['a',record('a')]]);
 const result=await h.context.runBatch(['a'],'accept','',()=>{},{a:'old'});
 assert.equal(h.writes.length,1);assert.equal(h.writes[0].body.items[0].expected_updated_at,'old');
 complete(h,result,['failed']);assert.equal(h.checks.get('a'),true);
});
test('stop retains unexecuted items and conflicting observations are sent for server validation',async()=>{
 const h=harness([['a',record('a')],['b',record('b')]]);
 const result=await h.context.runBatch(['a','b'],'accept');
 complete(h,result,['success','remaining']);assert.deepEqual([...h.checks.values()],[false,true]);
 const conflict=harness([['a',record('same')],['b',record('same','regression_failed')]]);
 const pending=await conflict.context.runBatch(['a'],'accept');
 assert.deepEqual(Array.from(conflict.writes[0].body.observations,item=>item.draft_id),['a','b']);
 complete(conflict,pending,['failed']);assert.equal(conflict.checks.get('a'),true);
});
test('selection settlement is consistent for all terminal outcomes',()=>{
 for(const outcome of ['success','noop','skipped','unknown'])assert.equal(triage.keepBatchSelection(outcome),false);
 for(const outcome of ['failed','remaining'])assert.equal(triage.keepBatchSelection(outcome),true);
});

test('a concurrent opposite transition cannot be reported as the requested success',()=>{
 assert.equal(triage.batchOutcome({...record('a'),remote_sync:{action:'accept',status:'success'}},'reopen'),'failed');
 assert.equal(triage.batchOutcome({...record('a'),remote_sync:{action:'reopen',status:'success'}},'accept'),'failed');
});
