const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const source=fs.readFileSync(require('node:path').join(__dirname,'../../api_test_tool/static/native-delivery-exec.js'),'utf8');
const AF=Object.getPrototypeOf(async function(){}).constructor;
async function run(input,ackFails=false){
 const actions=[];let result,error;
 const tools={exec_command:async({cmd})=>{
  if(cmd.includes('native-ack-script')){actions.push('generate');return {exit_code:0,output:JSON.stringify({script:ackFails?'throw new Error("unknown ACK");':'text({accepted:true,handoff_complete:true});'})};}
  actions.push('audit');return {exit_code:0,output:JSON.stringify({summary:{total_to_report_seconds:12,case_statuses:{c:'failed'},warnings:['actual warning']}})};
 },apply_patch:async patch=>{actions.push('persist_ack');assert.match(patch,/accepted/);}};
 try{await new AF('config','input','tools','text','ALL_TOOLS',source)({command:['python','client'],task_id:'t',node_id:'n',assignment_file:'/run/a.json',directory:'/run'},input,tools,v=>{result=v},[]);}catch(e){error=e;}
 return {actions,result,error};
}
test('one invocation persists actual ACK before auditing, retains failed cases and warnings',async()=>{
 const r=await run({task_id:'t',node_id:'n',event_id:'e'});
 assert.deepEqual(r.actions,['generate','persist_ack','audit']);assert.equal(r.result.summary.case_statuses.c,'failed');assert.deepEqual(r.result.summary.warnings,['actual warning']);
});
test('foreign event never starts acknowledgement',async()=>{
 const r=await run({task_id:'foreign',node_id:'n',event_id:'e'});assert.ok(r.error);assert.deepEqual(r.actions,[]);
});
test('unknown acknowledgement stops without audit or replay',async()=>{
 const r=await run({task_id:'t',node_id:'n',event_id:'e'},true);assert.ok(r.error);assert.deepEqual(r.actions,['generate']);
});
