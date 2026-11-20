const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const sourcePath=path.resolve(__dirname,'../../api_test_tool/static/native-observation-send.js');
const clientPath=path.resolve(__dirname,'../../api_test_tool/static/api-test-client.py');
async function fixture(fail=false) {
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'native-observe-test-'));
  await fs.writeFile(path.join(root,'design.json'),JSON.stringify({cases:[{case_id:'A'},{case_id:'B'}]}));
  await fs.writeFile(path.join(root,'preparation.json'),'{"state":"ready"}');
  const code=`import importlib.util,sys,json\nfrom pathlib import Path\ns=importlib.util.spec_from_file_location('client',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\nclass Client:\n def native_record(self,binding,payload,receipt):\n  with open(Path(binding).parent/'calls.jsonl','a') as f:f.write(json.dumps(payload)+'\\n')\n  if sys.argv[3]=='fail':m.write_private_json(receipt,{'state':'unknown','payload':payload});raise OSError('unknown POST')\n  m.write_private_json(receipt,{'saved':True,'revision':2});return {'saved':True,'revision':2}\nm.receive_native_observations(Client(),Path(sys.argv[2])/'binding.json')\n`;
  const child=spawn('python3',['-u','-c',code,clientPath,root,fail?'fail':'ok']);
  const ended=once(child,'exit');let stderr='';child.stderr.on('data',v=>stderr+=v);
  const [ready]=await once(child.stdout,'data');assert.match(String(ready),/receiver_ready/);
  const modulePath=path.join(root,'sender.mjs');await fs.writeFile(modulePath,await fs.readFile(sourcePath,'utf8')+'\nexport {nativeSendObservation};');
  const {nativeSendObservation}=await import('file://'+modulePath);
  return {root,child,ended,send:o=>nativeSendObservation(root,o),stderr:()=>stderr};
}
function obs(case_id,last=false){return {case_id,status:'passed',checks:[{name:'large observed value',expected:'retained',observed:'x'.repeat(100000),ok:true}],...(last?{exit:{browser_stopped:true,reason:'own tab absent'}}:{})};}
test('real file events save two observations in order, preserve large evidence, then exit only on explicit stop', {timeout:10000},async()=>{
  const f=await fixture();try {
    const first=await f.send(obs('A'));assert.equal(first.saved,true);
    const second=await f.send(obs('B',true));assert.equal(second.saved,true);
    await fs.writeFile(path.join(f.root,'native-observations.fifo'),'{"stop":true}\n');
    const [exit]=await f.ended;assert.equal(exit,0,f.stderr());
    assert.equal((await fs.readFile(path.join(f.root,'calls.jsonl'),'utf8')).trim().split('\n').length,2);
    assert.equal(JSON.parse(await fs.readFile(path.join(f.root,'native-receiver.json'))).state,'stopped');
    await assert.rejects(fs.stat(path.join(f.root,'native-observations.fifo')),{code:'ENOENT'});
  } finally {f.child.kill();await fs.rm(f.root,{recursive:true,force:true});}
});
test('unknown save returns its receipt, preserves pending observation and stays available for reconciliation',{timeout:10000},async()=>{
  const f=await fixture(true);try{
    const result=await f.send(obs('A',true));assert.equal(result.saved,false);assert.equal(f.child.exitCode,null);
    assert.equal((await fs.readFile(path.join(f.root,'calls.jsonl'),'utf8')).trim().split('\n').length,1);
    assert.equal(JSON.parse(await fs.readFile(path.join(f.root,'observation-pending.json'))).case_id,'A');
  }finally{f.child.kill();await fs.rm(f.root,{recursive:true,force:true});}
});
test('actual closeout can stop a receiver with no observation, without a platform write',{timeout:10000},async()=>{
  const f=await fixture();try{
    await fs.writeFile(path.join(f.root,'native-observations.fifo'),'{"stop":true}\n');
    const [exit]=await f.ended;assert.equal(exit,0,f.stderr());
    await assert.rejects(fs.stat(path.join(f.root,'calls.jsonl')),{code:'ENOENT'});
  }finally{f.child.kill();await fs.rm(f.root,{recursive:true,force:true});}
});
test('missing receiver returns not_sent and retains the observation without claiming exit',{timeout:10000},async()=>{
  const f=await fixture();try{
    await fs.writeFile(path.join(f.root,'native-observations.fifo'),'{"stop":true}\n');await f.ended;
    const result=await f.send(obs('A',true));assert.equal(result.state,'not_sent');
    const saved=JSON.parse(await fs.readFile(path.join(f.root,'observation-inbox-'+result.request_id+'.json')));
    assert.equal(saved.case_id,'A');await assert.rejects(fs.stat(path.join(f.root,'native-explicit-exit.json')),{code:'ENOENT'});
    await assert.rejects(fs.stat(path.join(f.root,'calls.jsonl')),{code:'ENOENT'});
  }finally{f.child.kill();await fs.rm(f.root,{recursive:true,force:true});}
});
