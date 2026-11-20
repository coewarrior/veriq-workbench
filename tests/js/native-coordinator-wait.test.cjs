const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({setTimeout});
vm.runInContext(fs.readFileSync('api_test_tool/static/native-coordinator-wait.js','utf8'),context);
const run = wait => context.waitNativeCoordinator(async()=>({intent:'run',modules:[{id:'n',state:'running',binding:{executor_ref:'thread:worker'}}]}),
  async()=>wait, ()=>{throw Error('must not send');},{task_ids:['t'],holder_id:'h',coordinator_ref:'thread:coordinator',window_seconds:5});
test('public message interruption is normal new user input',async()=>{
  const result=await run({message:'Wait interrupted by new input.',timedOut:false});
  assert.equal(result.reason,'user_input');
  assert.equal(result.dispatch_reads,1);
});
test('actual tool error is preserved even with interruption prose',async()=>{
  const result=await run({isError:true,content:[{type:'text',text:'Wait interrupted by new input.'}]});
  assert.equal(result.reason,'desktop_target_errors');
});
test('actual ended turn with outstanding lease is persisted and returned to coordinator', async()=>{
  const writes=[];
  const view={task_id:'t',intent:'run',closeout:{cleanup_responsibilities:[{id:'draft'}]},
    modules:[{task_id:'t',id:'n',state:'running',has_lease:true,
      binding:{dispatch_id:'d',received_at:100,executor_ref:'thread:worker'}}]};
  const result=await context.waitNativeCoordinator(async args=>{
    if(args.arguments.desktop_observations) { writes.push(args); return {accepted:true}; }
    return view;
  },async()=>({polls:[{thread:{id:'worker',status:{type:'idle'}},
    latestTurn:{id:'turn',status:'completed',completedAt:101}}]}),()=>{},
    {task_ids:['t'],holder_id:'h',coordinator_ref:'thread:coordinator',window_seconds:0.01});
  assert.equal(writes.length,1);
  assert.equal(writes[0].arguments.desktop_observations[0].dispatch_id,'d');
  assert.equal(result.attention[0].reason,'desktop_turn_ended_with_lease');
  assert.equal(result.closeout[0].cleanup_responsibilities[0].id,'draft');
});
for(const status of ['failed','error','interrupted','completed']) {
  test('unleased '+status+' is distinguished from ordinary sleeping', async()=>{
    const writes=[];
    const result=await context.waitNativeCoordinator(async args=>{
      if(args.arguments.desktop_observations) { writes.push(args); return {accepted:true}; }
      return {task_id:'t',intent:'run',modules:[{task_id:'t',id:'n',state:'queued',has_lease:false,
        binding:{dispatch_id:'d',received_at:100,executor_ref:'thread:worker'}}]};
    },async()=>({polls:[{thread:{id:'worker',status:{type:'idle'}},
      latestTurn:{id:'turn',status,completedAt:101}}]}),()=>{},
      {task_ids:['t'],holder_id:'h',coordinator_ref:'thread:coordinator',window_seconds:0.01});
    assert.equal(writes.length,1);
    if(status==='completed') assert.equal(result.reason,'observation_window_ended');
    else assert.equal(result.attention[0].reason,'desktop_turn_failed_or_interrupted');
  });
}
