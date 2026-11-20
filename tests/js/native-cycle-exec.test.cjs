const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../api_test_tool/static/native-cycle-exec.js'), 'utf8');
const AF = Object.getPrototypeOf(async function() {}).constructor;
test('new cycle uses a private receipt after truncated mutation output',async()=>{
  let result;const calls=[];
  const helper=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/native-control-read.js'),'utf8');
  const tools={exec_command:async({cmd})=>{calls.push(cmd);
    if(!cmd.includes('native-control-read'))return {exit_code:0,output:'Warning: terminal truncated...'};
    const file=cmd.match(/'--file' '([^']+)'/)[1],text='{"stage_ready":true}';
    return {exit_code:0,output:'NATIVE_CONTROL_PART:'+JSON.stringify({file,offset:0,next:text.length,text,eof:true})};
  },apply_patch:async()=>{}};
  await new AF('config','tools','text','ALL_TOOLS','input',helper+'\n'+source)(
    {command:['python','client'],directory:'/run',assignment_file:'/a',control_receipts:true},tools,v=>result=v,[],{action:'stage_ready'});
  assert.equal(result.result.stage_ready,true);assert.equal(calls.length,2);
  assert.match(calls[0],/--control-result-file/);
});
test('yield is explicit and does not use deferred terminal report release',async()=>{
  const result=await run({action:'yield',browser_stopped:true,reason:'original stage boundary'});
  assert.equal(result.error,undefined);
  assert.match(result.calls[0],/'--outcome' 'yield'/);
  assert.doesNotMatch(result.calls[0],/--defer-report/);
});
async function run(input, failSave = false) {
  const calls = [], logs = [], output = [];
  const tools = {
    exec_command: async args => {
      calls.push(args.cmd);
      if (args.cmd.includes('native-observe')) return {exit_code: failSave ? 1 : 0, output: failSave ? 'unknown save' : '{"saved":true}'};
      if (args.cmd.includes('native-closeout-script')) return {exit_code: 0, output: JSON.stringify({script: 'text({released:true})'})};
      return {exit_code: 0, output: '{"ready":true}'};
    },
    apply_patch: async value => { logs.push(value); }
  };
  let error;
  try { await new AF('config','tools','text','ALL_TOOLS','input',source)(
    {command:['python3',"/a b/client'$.py"],directory:'/private/run',assignment_file:'/a',design_file:'/d',entry_url:'https://target.test/path'},
    tools,v=>output.push(v),[],input); } catch(e) { error=e; }
  return {calls,logs,output,error};
}
test('prepare is one invocation and returns the direct entry', async()=> {
  const r=await run({action:'prepare',resume:true});
  assert.equal(r.calls.length,1);
  assert.match(r.calls[0], /--resume/);
  assert.equal(r.output[0].result.entry_url,'https://target.test/path');
  assert.equal(r.output[0].stages.length,1);
});
test('record and actual final exit save then release without another model turn',async()=>{
  const r=await run({action:'record',observation:{case_id:'case',checks:[]},finish_task:true,browser_stopped:true,reason:'closed'});
  assert.equal(r.calls.length,2);
  assert.match(r.calls[0],/native-observe/);
  assert.match(r.calls[1],/native-closeout-script/);
  assert.equal(r.output[0].result.closeout.released,true);
});
test('failed save never retries; genuinely closed resource still releases as unconfirmed',async()=>{
  const r=await run({action:'record',observation:{case_id:'case'},finish_task:true,browser_stopped:true,reason:'closed'},true);
  assert.equal(r.calls.length,2);
  assert.match(r.calls[1],/--save-unconfirmed/);
  assert.ok(r.error);
  assert.equal(r.output[0].result.save_unconfirmed,true);
  assert.ok(r.logs[0].includes('unknown save'));
});
test('failed save cannot claim an unclosed browser has exited',async()=>{
  const r=await run({action:'record',observation:{case_id:'case'}},true);
  assert.equal(r.calls.length,1);
  assert.ok(r.error);
});
test('file goes directly to save and release without retyping checks',async()=>{
  const r=await run({action:'record',observation_file:'/private/run/observation-native.json',finish_task:true,browser_stopped:true,reason:'absent'});
  assert.equal(r.calls.length,2);assert.match(r.calls[0],/--source-file/);
  assert.doesNotMatch(r.calls[0],/--observation-json/);assert.equal(r.output[0].result.closeout.released,true);
});
test('foreign observation export rejected before save',async()=>{
  const r=await run({action:'record',observation_file:'/another-run/observation-native.json'});
  assert.equal(r.calls.length,0);assert.ok(r.error);
});
test('prepare returns ready from its live receiver without launching another process',async()=>{
  let executions=0,polls=0,result;
  const tools={exec_command:async()=>{executions++;return {session_id:42,output:'{"receiver_ready":'};},
    write_stdin:async()=>{polls++;return {session_id:42,output:'true,"fifo":"/run/fifo","prepared":{"ready":true,"cases":[{"case_id":"real"}]}}'};},
    apply_patch:async()=>{}};
  await new AF('config','tools','text','ALL_TOOLS','input',source)(
    {command:['python3','client'],directory:'/run',assignment_file:'/a',design_file:'/d',entry_url:'https://target.test',observation_stream:true},
    tools,v=>result=v,[],{action:'prepare'});
  assert.equal(executions,1);assert.equal(polls,1);
  assert.equal(result.result.observation_receiver.session_id,42);
  assert.equal(result.result.cases[0].case_id,'real');
});
test('closeout takes actual saved exit without model-generated arguments',async()=>{
  const r=await run({action:'closeout',from_observation:true});
  assert.equal(r.calls.length,1);assert.match(r.calls[0],/--observed-exit/);
  assert.doesNotMatch(r.calls[0],/--browser-stopped|--reason/);
  assert.equal(r.output[0].result.released,true);
});
test('finite preparation returns child readiness without polling the terminal',async()=>{
  let result;
  const tools={exec_command:async args=>{
    assert.equal(args.yield_time_ms,10000);
    return {exit_code:0,output:JSON.stringify({ready:true,observation_receiver:{pid:123,fifo:'/run/fifo'}})};
  },write_stdin:async()=>{throw Error('must not poll completed preparation');},apply_patch:async()=>{}};
  await new AF('config','tools','text','ALL_TOOLS','input',source)(
    {command:['python3','client'],directory:'/run',assignment_file:'/a',design_file:'/d',entry_url:'https://target.test',observation_stream:true},
    tools,v=>result=v,[],{action:'prepare'});
  assert.equal(result.result.observation_receiver.pid,123);
});
test('compact display preserves dynamic warnings and the complete original receipt',async()=>{
  let result, artifact;
  const receipt={ready:true,baseline_receipt:{title_guidance:'static known prose',
    warnings:['actual changed precondition'],execution_plan:{next:'case-2'},
    coverage_check:{not_run_guidance:'static repeated execution contract',
      guidance:'static coverage contract',remaining_cases:[{case_id:'case-2',status:'not_run'}],
      incomplete_designs:[{case_id:'case-2',missing:['test_data']}],
      upload_fallback_gaps:[{case_id:'case-2',reason:'actual missing upload'}],
      new_guidance:'unrecognized dynamic guidance'}}};
  const tools={exec_command:async()=>({exit_code:0,output:JSON.stringify(receipt)}),
    apply_patch:async text=>{artifact=text;}};
  await new AF('config','tools','text','ALL_TOOLS','input',source)(
    {command:['python3','client'],directory:'/run',assignment_file:'/a',design_file:'/d',entry_url:'https://target.test'},
    tools,v=>result=v,[],{action:'prepare'});
  assert.equal(result.result.baseline_receipt.title_guidance,undefined);
  assert.deepEqual(result.result.baseline_receipt.warnings,['actual changed precondition']);
  assert.equal(result.result.baseline_receipt.execution_plan.next,'case-2');
  assert.equal(result.result.baseline_receipt.coverage_check.not_run_guidance,undefined);
  assert.equal(result.result.baseline_receipt.coverage_check.guidance,undefined);
  assert.deepEqual(result.result.baseline_receipt.coverage_check.remaining_cases,receipt.baseline_receipt.coverage_check.remaining_cases);
  assert.deepEqual(result.result.baseline_receipt.coverage_check.incomplete_designs,receipt.baseline_receipt.coverage_check.incomplete_designs);
  assert.deepEqual(result.result.baseline_receipt.coverage_check.upload_fallback_gaps,receipt.baseline_receipt.coverage_check.upload_fallback_gaps);
  assert.equal(result.result.baseline_receipt.coverage_check.new_guidance,'unrecognized dynamic guidance');
  assert.match(result.full_receipt_file,/^\/run\/cycle-prepare-\d+\.json$/);
  assert.match(artifact,/static known prose/);
  assert.match(artifact,/static repeated execution contract/);
});
