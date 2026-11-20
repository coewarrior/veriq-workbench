const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {spawn} = require('node:child_process');
const {once} = require('node:events');

test('reconnect drops only the old CDP connection and selects the original target without navigation', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'native-reconnect-'));
  let child;
  try {
    const module = await import(pathToFileURL(path.resolve(__dirname, '../../api_test_tool/static/native-isolated-browser.mjs')));
    const profile = path.join(root, 'profile'); await fs.mkdir(profile);
    // Local synthetic endpoint, no browser or business service involved.
    child = spawn(process.execPath, ['-e', `const http=require('node:http'),fs=require('node:fs');
      const server=http.createServer((q,r)=>r.end('{}')).listen(0,'127.0.0.1',()=>{
        fs.writeFileSync(${JSON.stringify(path.join(profile,'DevToolsActivePort'))},server.address().port+'\\n/devtools/browser/fixture');
        process.stdout.write('ready\\n');});`, '--', '--user-data-dir='+profile, '--remote-debugging-port=0'], {stdio:['ignore','pipe','pipe']});
    await once(child.stdout, 'data');
    const runtime = path.join(root,'runtime.cjs');
    await fs.writeFile(runtime, `let connects=0,disconnects=0;
      exports.stats=()=>({connects,disconnects});
      exports.chromium={executablePath:()=>process.execPath,connectOverCDP:async()=>{
        connects++;let connected=true;
        const page={isClosed:()=>false,goto:()=>{throw Error('must not navigate')}};
        const context={pages:()=>[page],newCDPSession:async()=>({send:async()=>({targetInfo:{targetId:'original'}}),detach:async()=>{}})};
        return {isConnected:()=>connected,contexts:()=>[context],close:async()=>{connected=false;disconnects++}};
      }};`);
    const identity={task_id:'t',node_id:'n',holder_id:'h',executor_ref:'worker'};
    const assignment=path.join(root,'assignment.json');
    await fs.writeFile(assignment,JSON.stringify({...identity,direct_browser:{playwright_module:runtime,host_id:'fixture'}}));
    const env={context_id:'ctx',host_id:'fixture',browser:'chromium',origin:'https://example.test',isolation:'isolated'};
    await fs.writeFile(path.join(root,'browser-environment.json'),JSON.stringify({schema:2,identity,origin:env.origin,host_id:'fixture',state:'open',
      slots:[{context_id:'ctx',generation:1,profile,entered:true,target_id:'original'}],environments:[env]}));
    await fs.writeFile(path.join(root,'binding.json'),JSON.stringify({...identity,lease_id:'lease',account_ids:['account'],native_context_binding:{contexts:[{...env,account_id:'account'}]}}));
    const options={assignment_file:assignment,directory:root,origin:env.origin};
    const original=await module.prepare(options);
    await assert.rejects(module.reconnect({...options,origin:'https://foreign.test'}), /assignment|scope/);
    assert.equal(original.browser.isConnected(),true, 'invalid recovery must not disconnect the working session');
    for (const changed of [{host_id:'foreign'}, {context_count:2}]) {
      await fs.writeFile(assignment,JSON.stringify({...identity,direct_browser:{playwright_module:runtime,host_id:'fixture',...changed}}));
      await assert.rejects(module.reconnect(options), /assignment|scope/);
      assert.equal(original.browser.isConnected(),true);
    }
    await fs.writeFile(assignment,JSON.stringify({...identity,direct_browser:{playwright_module:runtime,host_id:'fixture'}}));
    const recovered=await module.reconnect(options);
    assert.notEqual(recovered,original);
    assert.equal(original.browser.isConnected(),false);
    assert.equal(recovered.browser.isConnected(),true);
    assert.equal(await recovered.enter(env.origin),recovered.pages[0]);
    assert.deepEqual(require(runtime).stats(),{connects:2,disconnects:1});
    const receipt=JSON.parse(await fs.readFile(recovered.recovery_receipt_file));
    assert.equal(receipt.state,'connected');
    assert.equal(JSON.parse(await fs.readFile(path.join(root,'browser-environment.json'))).slots[0].generation,1);
  } finally {
    if(child && child.exitCode===null){child.kill();await once(child,'exit');}
    await fs.rm(root,{recursive:true,force:true});
  }
});

test('recovery diagnosis preserves exited scene and cannot silently replace it', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'native-recovery-'));
  try {
    const module = await import(pathToFileURL(path.resolve(__dirname, '../../api_test_tool/static/native-isolated-browser.mjs')));
    assert.equal(typeof module.diagnose, 'function');
    const identity = {task_id:'t', node_id:'n', holder_id:'h', executor_ref:'worker'};
    const assignment = path.join(root, 'assignment.json');
    await fs.writeFile(assignment, JSON.stringify(identity));
    const receipt = {schema:2, identity, origin:'https://example.test', host_id:os.hostname(), state:'open', slots:[{context_id:'ctx', generation:1, profile:path.join(root,'private-profile')}], environments:[]};
    await fs.writeFile(path.join(root, 'browser-environment.json'), JSON.stringify(receipt));
    const result = await module.diagnose({assignment_file:assignment, directory:root});
    assert.equal(result.slots[0].process_state, 'absent');
    assert.equal(result.slots[0].endpoint_state, 'not_checked');
    assert.equal(result.business_result, 'unknown');
    assert.deepEqual(JSON.parse(await fs.readFile(path.join(root,'browser-environment.json'))), receipt);
    await assert.rejects(module.reconnect({assignment_file:assignment,directory:root,origin:'https://example.test'}), /exited/);
    receipt.state = 'closed';
    await fs.writeFile(path.join(root, 'browser-environment.json'), JSON.stringify(receipt));
    await assert.rejects(module.reconnect({assignment_file:assignment,directory:root,origin:'https://example.test'}), /closed/);
    await fs.writeFile(assignment, JSON.stringify({...identity,holder_id:'foreign'}));
    await assert.rejects(module.diagnose({assignment_file:assignment,directory:root}), /Original owned/);
  } finally { await fs.rm(root, {recursive:true,force:true}); }
});

test('owned cleanup accepts the same chat UUID alias, rejects another chat or holder', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'native-identity-'));
  try {
    const {closeOwned} = await import(pathToFileURL(path.resolve(__dirname, '../../api_test_tool/static/native-isolated-browser.mjs')));
    const id = '01a17111-5ac7-79d0-9ac8-48eaaddc22b8';
    const identity = {task_id:'task', node_id:'node', holder_id:'worker', executor_ref:id};
    // No browser has been launched: clean up a partial-start receipt using
    // real local IO. The runtime stub only avoids requiring Chromium.
    const runtime = path.join(root, 'runtime.cjs');
    await fs.writeFile(runtime, 'exports.chromium={executablePath:()=>process.execPath};');
    const assignment = path.join(root, 'assignment.json');
    const receipt = path.join(root, 'browser-environment.json');
    const saveAssignment = value => fs.writeFile(assignment, JSON.stringify({...value, direct_browser:{playwright_module:runtime}}));
    await fs.writeFile(receipt, JSON.stringify({schema:2, identity, slots:[], environments:[], state:'creating'}));
    await saveAssignment({...identity, executor_ref:'thread:01a17111-6d87-7b83-968e-5f6c2a107a77'});
    await assert.rejects(closeOwned({assignment_file:assignment, directory:root}), /Original owned/);
    await saveAssignment({...identity, holder_id:'foreign', executor_ref:'thread:'+id});
    await assert.rejects(closeOwned({assignment_file:assignment, directory:root}), /Original owned/);
    await saveAssignment({...identity, executor_ref:'thread:'+id.toUpperCase()});
    const result = await closeOwned({assignment_file:assignment, directory:root});
    assert.equal(result.browser_stopped, true);
    assert.equal(JSON.parse(await fs.readFile(receipt)).state, 'closed');
  } finally { await fs.rm(root, {recursive:true, force:true}); }
});
