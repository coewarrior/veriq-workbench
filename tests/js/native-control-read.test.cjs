const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const scope = vm.createContext({});
vm.runInContext(fs.readFileSync('api_test_tool/static/native-control-read.js','utf8'),scope);
test('reads exact private control result despite warning, truncation and chunk boundaries',async()=>{
  const record={script:'x'.repeat(22000),warning:'保留真实告警',revision:3};
  const data=JSON.stringify(record);let calls=0;
  const result=await scope.nativeReadControl({exec_command:async({cmd})=>{
    calls++;const offset=Number(cmd.match(/'--offset' '(\d+)'/)[1]);
    const text=data.slice(offset,offset+3000);
    return {exit_code:0,output:'Warning: unrelated stdout\nNATIVE_CONTROL_PART:'+JSON.stringify({file:'/private/result.json',offset,text,next:offset+text.length,eof:offset+text.length===data.length})+'\n'};
  }},['python','client'],'/private/result.json');
  assert.equal(result.script,record.script);assert.equal(result.warning,record.warning);assert.ok(calls>1);
});
test('missing or stale receipt cannot manufacture success or replay',async()=>{
  let calls=0;
  await assert.rejects(scope.nativeReadControl({exec_command:async()=>{calls++;return {exit_code:0,output:'truncated'};}},['python','client'],'/private/result.json'),/frame/);
  assert.equal(calls,1);
});
