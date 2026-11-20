const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const childProcess = require('node:child_process');
const {syncBuiltinESMExports} = require('node:module');
const {pathToFileURL} = require('node:url');

// Only the OS process command is substituted. Receipts, ownership decisions,
// lifecycle code and deadlines run unchanged; no real browser is started.
async function fixture(t, processQuery, runtimeSource = '', spawnProcess) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'native-process-'));
  const profile = path.join(root, 'private-profile'); await fs.mkdir(profile);
  const runtime = path.join(root, 'runtime.cjs');
  await fs.writeFile(runtime, runtimeSource || 'exports.chromium={executablePath:()=>process.execPath};');
  const identity = {task_id:'task',node_id:'node',holder_id:'holder',executor_ref:'executor'};
  const assignment = path.join(root, 'assignment.json');
  await fs.writeFile(assignment, JSON.stringify({...identity,direct_browser:{playwright_module:runtime,host_id:'fixture'}}));
  const slot = {context_id:'ctx',generation:1,pid:1234,profile,entered:true,target_id:'original'};
  const receipt = {schema:2,identity,origin:'https://example.test',host_id:'fixture',state:'open',slots:[slot],
    environments:[{context_id:'ctx',browser:'chromium',host_id:'fixture',origin:'https://example.test',isolation:'isolated'}]};
  const file = path.join(root, 'browser-environment.json');
  await fs.writeFile(file, JSON.stringify(receipt));
  const original = childProcess.execFile, originalSpawn = childProcess.spawn;
  if (spawnProcess) childProcess.spawn = (...args)=>spawnProcess(...args);
  childProcess.execFile = (command,args,options,callback) => {
    Promise.resolve().then(() => processQuery({command,args,options,slot})).then(stdout => callback(null,stdout,''), error => callback(error,'',''));
  };
  childProcess.execFile[require('node:util').promisify.custom] = async (command,args,options) => ({stdout: await processQuery({command,args,options,slot}), stderr:''});
  syncBuiltinESMExports();
  const module = await import(pathToFileURL(process.env.NATIVE_BROWSER_MODULE || path.resolve(__dirname, '../../api_test_tool/static/native-isolated-browser.mjs')).href+'?test='+Math.random());
  childProcess.execFile = original; syncBuiltinESMExports();
  if(spawnProcess)t.after(()=>{childProcess.spawn=originalSpawn;syncBuiltinESMExports();});
  t.after(() => fs.rm(root,{recursive:true,force:true}));
  return {root,profile,runtime,slot,receipt,file,module,options:{assignment_file:assignment,directory:root,origin:receipt.origin}};
}
const row = (slot, command = '--user-data-dir='+slot.profile+' --remote-debugging-port=0') =>
  `1234 Sun Oct 25 12:34:56 2026 chromium ${command}\n`;

test('saved PID is verified directly without implying CDP control', async t => {
  let calls = 0;
  const f = await fixture(t, ({args,options,slot}) => {
    calls++; assert.ok(args.includes('-p'), 'must avoid the slow full process table');
    assert.ok(args.includes('1234')); assert.ok(options.timeout > 0 && options.timeout <= 5000);
    return row(slot);
  });
  const result = await f.module.diagnose(f.options);
  assert.equal(calls,1);
  assert.equal(result.slots[0].process_state,'present');
  assert.equal(result.slots[0].process_query,'saved_pid');
  assert.equal(result.slots[0].process_started_at,'Sun Oct 25 12:34:56 2026');
  assert.equal(result.slots[0].cdp_control_state,'not_checked');
  assert.ok(result.slots[0].process_elapsed_ms >= 0);
});

test('a reused PID with another profile remains unknown without scanning or reconnecting', async t => {
  const f = await fixture(t, ({args,slot}) => {
    assert.ok(args.includes('-p')); return row(slot,'--user-data-dir=/another/profile --remote-debugging-port=0');
  }, `exports.chromium={executablePath:()=>process.execPath,connectOverCDP:async()=>{require('node:fs').writeFileSync(__dirname+'/unexpected-connect','');throw Error('foreign browser')}};`);
  const result = await f.module.diagnose(f.options);
  assert.equal(result.slots[0].process_state,'unknown');
  assert.equal(result.slots[0].process_reason,'saved_pid_not_owned');
  await assert.rejects(f.module.reconnect(f.options), /unknown/);
  await assert.rejects(f.module.closeOwned(f.options), /unknown/);
  await assert.rejects(fs.access(path.join(f.root,'unexpected-connect')), {code:'ENOENT'});
  // close may add diagnostic evidence, but cannot close or replace the scene.
  const saved = JSON.parse(await fs.readFile(f.file));
  assert.equal(saved.slots[0].profile,f.profile);
  assert.equal(saved.slots[0].generation,1);
  delete saved.close_started_at; delete saved.slots[0].close_process_evidence;
  assert.deepEqual(saved,f.receipt);
});

test('failed targeted lookup stays unknown and never falls back to absent', async t => {
  const f = await fixture(t, () => { throw Object.assign(new Error('synthetic timeout'), {code:'ETIMEDOUT',killed:true}); });
  const result = await f.module.diagnose(f.options);
  assert.equal(result.slots[0].process_state,'unknown');
  assert.equal(result.slots[0].process_reason,'query_failed');
  await assert.rejects(f.module.confirmExit(f.root), /unknown/);
  assert.equal(JSON.parse(await fs.readFile(f.file)).state,'open');
});

test('legacy receipts use bounded discovery and prepare/close refuse unknown ownership', async t => {
  const f = await fixture(t, ({options}) => {
    assert.ok(options.timeout > 0 && options.timeout <= 5000,'all process discovery must be bounded');
    throw Object.assign(new Error('synthetic timeout'), {code:'ETIMEDOUT'});
  });
  delete f.receipt.slots[0].pid;
  await fs.writeFile(f.file,JSON.stringify(f.receipt));
  await assert.rejects(f.module.prepare(f.options), /unknown/);
  await assert.rejects(f.module.closeOwned(f.options), /unknown|unconfirmed/);
  assert.equal(JSON.parse(await fs.readFile(f.file)).state,'open');
});

test('CDP initialization failure leaves the original profile, target and generation intact', async t => {
  const f = await fixture(t, ({slot}) => row(slot), `exports.chromium={executablePath:()=>process.execPath,
    connectOverCDP:async()=>{throw Error('synthetic CDP initialization failed')}};`);
  const server = require('node:http').createServer((_,response)=>response.end('{}'));
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(()=>new Promise(resolve=>{ server.closeAllConnections(); server.close(resolve); }));
  await fs.writeFile(path.join(f.profile,'DevToolsActivePort'),server.address().port+'\n/devtools/browser/original');
  const diagnosis = await f.module.diagnose(f.options);
  assert.equal(diagnosis.slots[0].endpoint_state,'reachable');
  assert.equal(diagnosis.slots[0].cdp_control_state,'not_checked');
  await assert.rejects(f.module.reconnect(f.options), /CDP initialization failed/);
  const saved = JSON.parse(await fs.readFile(f.file));
  assert.equal(saved.slots[0].profile,f.profile);
  assert.equal(saved.slots[0].target_id,'original');
  assert.equal(saved.slots[0].generation,1);
  assert.equal(saved.slots[0].entered,true);
  assert.equal(saved.slots[0].connection_evidence.stage,'cdp_connect');
  assert.equal(saved.slots[0].connection_evidence.cdp_control_state,'failed');
  assert.ok(saved.slots[0].connection_evidence.elapsed_ms >= 0);
  const names = await fs.readdir(f.root);
  const recovery = JSON.parse(await fs.readFile(path.join(f.root,names.find(name=>name.startsWith('browser-reconnect-')))));
  assert.equal(recovery.state,'failed');
  assert.equal(recovery.cdp_control_state,'failed');
  assert.ok(recovery.elapsed_ms >= 0);
});

test('matching profile on a different saved process generation cannot be reattached or closed', async t => {
  const f = await fixture(t, ({slot}) => row(slot));
  f.receipt.slots[0].process_started_at = 'Sun Oct 25 11:22:33 2026';
  await fs.writeFile(f.file,JSON.stringify(f.receipt));
  const result = await f.module.diagnose(f.options);
  assert.equal(result.slots[0].process_state,'unknown');
  assert.equal(result.slots[0].process_reason,'saved_pid_generation_changed');
  await assert.rejects(f.module.closeOwned(f.options), /unknown/);
  assert.equal(JSON.parse(await fs.readFile(f.file)).state,'open');
});

test('a definitely absent PID falls back once within the same discovery budget', async t => {
  const queries = [];
  const f = await fixture(t, ({args,options}) => {
    queries.push({targeted:args.includes('-p'),timeout:options.timeout});
    if (args.includes('-p')) throw Object.assign(new Error('no matching PID'),{code:1,stdout:'',stderr:''});
    return '';
  });
  const result = await f.module.diagnose(f.options);
  assert.equal(result.slots[0].process_state,'absent');
  assert.equal(result.slots[0].process_query,'saved_pid_absent_profile_scan');
  assert.deepEqual(queries.map(q=>q.targeted),[true,false]);
  assert.ok(queries[1].timeout <= queries[0].timeout);
});

test('legacy profile discovery accepts only roots with the exact profile and debugging arguments', async t => {
  const f = await fixture(t, ({slot}) => row(slot,'--user-data-dir='+slot.profile+'-foreign --remote-debugging-port=0')+
    row(slot,'--user-data-dir='+slot.profile+' --remote-debugging-port=0 --type=renderer'));
  delete f.receipt.slots[0].pid;
  await fs.writeFile(f.file,JSON.stringify(f.receipt));
  assert.equal((await f.module.diagnose(f.options)).slots[0].process_state,'absent');
});

test('CDP initialization that ignores its timeout is bounded and never replaces the original scene', {timeout:20000}, async t => {
  const f = await fixture(t, ({slot}) => row(slot), `exports.chromium={executablePath:()=>process.execPath,
    connectOverCDP:()=>new Promise(()=>{})};`);
  await fs.writeFile(path.join(f.profile,'DevToolsActivePort'),'45678\n/devtools/browser/original');
  const started = Date.now();
  await assert.rejects(f.module.reconnect(f.options), /CDP connect deadline exceeded/);
  assert.ok(Date.now()-started < 20000);
  assert.equal(JSON.parse(await fs.readFile(f.file)).slots[0].generation,1);
});

test('process verification works when the node_repl host exposes no process global', async t => {
  const f = await fixture(t, ({slot})=>row(slot));
  const hostProcess = globalThis.process;
  let result;
  try {
    delete globalThis.process;
    result = await f.module.diagnose(f.options);
  } finally { globalThis.process = hostProcess; }
  assert.equal(result.slots[0].process_state,'present');
});

test('cleanup still closes an owned slot when another saved PID has unknown ownership', async t => {
  let f;
  f = await fixture(t, ({args,slot}) => {
    if (args.includes('1234')) return row(slot,'--user-data-dir=/foreign --remote-debugging-port=0');
    if (args.includes('2345') && !require('node:fs').existsSync(path.join(f.root,'owned-close')))
      return `2345 Sun Oct 25 12:34:56 2026 chromium --user-data-dir=${f.profile}-second --remote-debugging-port=0\n`;
    return '';
  }, `exports.chromium={executablePath:()=>__filename,connectOverCDP:async()=>({isConnected:()=>false,
    newBrowserCDPSession:async()=>({send:async()=>{require('node:fs').writeFileSync(__dirname+'/owned-close','')}})})};`);
  const second = {...f.slot,context_id:'second',pid:2345,profile:f.profile+'-second'};
  await fs.mkdir(second.profile);
  await fs.writeFile(path.join(second.profile,'DevToolsActivePort'),'45678\n/devtools/browser/second');
  f.receipt.slots.push(second);
  await fs.writeFile(f.file,JSON.stringify(f.receipt));
  await assert.rejects(f.module.closeOwned(f.options), /unknown|unconfirmed/);
  await fs.access(path.join(f.root,'owned-close'));
  assert.equal(JSON.parse(await fs.readFile(f.file)).state,'open');
});

test('fallback discovery cannot silently replace a known process generation', async t => {
  const f = await fixture(t, ({args,slot}) => args.includes('-p') ? '' :
    `2345 Sun Oct 25 12:34:56 2026 chromium --user-data-dir=${slot.profile} --remote-debugging-port=0\n`);
  f.receipt.slots[0].process_started_at = 'Sun Oct 25 11:22:33 2026';
  await fs.writeFile(f.file,JSON.stringify(f.receipt));
  const result = await f.module.diagnose(f.options);
  assert.equal(result.slots[0].process_state,'unknown');
  assert.equal(result.slots[0].process_reason,'profile_process_generation_changed');
  await assert.rejects(f.module.prepare({...f.options,restart_exited:true}), /unknown/);
  assert.equal(JSON.parse(await fs.readFile(f.file)).slots[0].generation,1);
});

const syntheticRuntime = `const fs=require('node:fs');exports.chromium={executablePath:()=>__filename,
  connectOverCDP:async()=>{const saved=JSON.parse(fs.readFileSync(__dirname+'/browser-environment.json'));
    if(!saved.slots[0].process_started_at)throw Error('CDP opened before generation verified');
    const page={isClosed:()=>false};return {isConnected:()=>true,close:async()=>{},contexts:()=>[{
      pages:()=>[page],newCDPSession:async()=>({send:async()=>({targetInfo:{targetId:'original'}}),detach:async()=>{}})
    }]};}};`;
function fakeSpawn(profile, onSpawn = ()=>{}) {
  const child = new (require('node:events').EventEmitter)(); child.pid=1234; child.unref=()=>{};
  require('node:fs').writeFileSync(path.join(profile,'DevToolsActivePort'),'45678\n/devtools/browser/original');
  queueMicrotask(()=>{onSpawn();child.emit('spawn');}); return child;
}

for(const initialGeneration of [0,1])test('newly spawned generation persists its verified birth before opening CDP (initial '+initialGeneration+')', async t => {
  let spawned=false;
  const f=await fixture(t,({args,slot})=>spawned ? (assert.ok(args.includes('-p')),row(slot)) : '',syntheticRuntime,
    (_executable,args)=>fakeSpawn(args.find(arg=>arg.startsWith('--user-data-dir=')).slice('--user-data-dir='.length),()=>{spawned=true;}));
  f.receipt.slots[0].generation=initialGeneration; delete f.receipt.slots[0].pid;
  await fs.writeFile(f.file,JSON.stringify(f.receipt));
  await f.module.prepare({...f.options,restart_exited:initialGeneration>0});
  const saved=JSON.parse(await fs.readFile(f.file));
  assert.equal(saved.slots[0].process_started_at,'Sun Oct 25 12:34:56 2026');
  assert.equal(saved.slots[0].process_identity_required,true);
  assert.equal(saved.slots[0].generation,initialGeneration+1);
});

test('failed spawn verification remains unknown and a replacement cannot inherit its generation', async t => {
  let phase='absent';
  const f=await fixture(t,({args,slot})=>{
    if(phase==='absent')return '';
    if(phase==='verification')throw Object.assign(new Error('synthetic timeout'),{code:'ETIMEDOUT'});
    return args.includes('-p') ? '' : `2345 Sun Oct 25 13:00:00 2026 chromium --user-data-dir=${slot.profile} --remote-debugging-port=0\n`;
  },syntheticRuntime,(_executable,args)=>fakeSpawn(args.find(arg=>arg.startsWith('--user-data-dir=')).slice('--user-data-dir='.length),()=>{phase='verification';}));
  f.receipt.slots[0].generation=0; delete f.receipt.slots[0].pid;
  await fs.writeFile(f.file,JSON.stringify(f.receipt));
  await assert.rejects(f.module.prepare(f.options),/unknown/);
  const partial=JSON.parse(await fs.readFile(f.file));
  assert.equal(partial.slots[0].process_identity_required,true);
  assert.equal(partial.slots[0].process_evidence.process_state,'unknown');
  assert.equal(partial.state,'creating');
  phase='replacement';
  const diagnosis=await f.module.diagnose(f.options);
  assert.equal(diagnosis.slots[0].process_state,'unknown');
  assert.equal(diagnosis.slots[0].process_reason,'process_generation_unverified');
  await assert.rejects(f.module.prepare({...f.options,restart_exited:true}),/unknown/);
  await assert.rejects(f.module.confirmExit(f.root),/unknown/);
  assert.equal(JSON.parse(await fs.readFile(f.file)).slots[0].generation,1);
});

test('a crash receipt marked as a new unverified generation cannot use legacy PID discovery', async t => {
  const f=await fixture(t,({slot})=>row(slot),syntheticRuntime);
  delete f.receipt.slots[0].pid;
  f.receipt.slots[0].process_identity_required=true;
  f.receipt.state='creating';
  await fs.writeFile(f.file,JSON.stringify(f.receipt));
  const diagnosis=await f.module.diagnose(f.options);
  assert.equal(diagnosis.slots[0].process_state,'unknown');
  assert.equal(diagnosis.slots[0].process_reason,'process_generation_unverified');
  await assert.rejects(f.module.prepare({...f.options,restart_exited:true}),/unknown/);
  assert.equal(JSON.parse(await fs.readFile(f.file)).slots[0].generation,1);
});
