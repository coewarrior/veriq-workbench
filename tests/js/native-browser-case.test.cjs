const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname,'../../api_test_tool/static/native-browser-case.js'),'utf8');
const runCase = new Function(source + ';return nativeBrowserCase')();
test('one call preserves values and exports without closing',async()=>{
  let saved, reads=0, closed=0;
  const r=await runCase({case_id:'A',run:async j=>{
    const state=await j.step('ready',()=>j.until(async()=>++reads,v=>v===2));
    j.check('count',2,state,state===2);
  },close:async()=>{closed++;return {browser_stopped:true,reason:'own tab absent'};},emit:async v=>{saved=v;}});
  assert.equal(r.status,'passed');assert.equal(reads,2);assert.equal(closed,0);
  assert.equal(saved.checks[0].observed,2);assert.ok(saved.steps[0].finished_at);
});
test('exception returns the draft to Codex without recovery, close or final verdict',async()=>{
  let clicked=0,later=0,recovered=0,closed=0,saved;
  const result=await runCase({case_id:'B',run:async j=>{
    await j.step('business',async()=>{clicked++;throw new Error('timeout after action');});later++;
  },recover:async()=>{recovered++;return 'actual current state';},close:async()=>{closed++;return {browser_stopped:true,reason:'absent'};},emit:async v=>{saved=v;}});
  assert.deepEqual([clicked,later,recovered,closed],[1,0,0,0]);
  assert.equal(saved,undefined);assert.equal(result.status,'interrupted');
  assert.equal(result.observation.checks.length,0);assert.equal(result.failed_step.name,'business');
});
test('bounded read-only wait cannot replay business or continue after timeout',async()=>{
  let clicks=0,reads=0,saved;
  const result=await runCase({case_id:'C',run:async j=>{clicks++;await j.until(async()=>++reads,()=>false,{max_reads:2,timeout_ms:20});clicks++;},emit:async v=>{saved=v;}});
  assert.equal(clicks,1);assert.equal(reads,2);assert.equal(saved,undefined);assert.equal(result.status,'interrupted');
});
test('fast reads retain a final readiness check instead of exhausting the budget immediately',async()=>{
  let clicks=0,reads=0;const began=Date.now();
  const r=await runCase({case_id:'E',run:async j=>{
    clicks++;
    const ready=await j.until(async()=>{reads++;return Date.now()-began>=25;},v=>v,{max_reads:3,timeout_ms:40});
    j.check('settled',true,ready,ready);
  },emit:async()=>{}});
  assert.equal(r.status,'passed');assert.equal(clicks,1);assert.ok(reads<=3);assert.ok(Date.now()-began>=25);
});
test('failed assertion remains failed without running an unsolicited close callback',async()=>{
  let saved;
  const r=await runCase({case_id:'D',run:async j=>j.check('value',1,2,false),close:async()=>{throw new Error('close failed');},emit:async v=>{saved=v;}});
  assert.equal(r.status,'failed');assert.equal(r.browser_stopped,false);assert.equal(saved.close_error,undefined);
});
