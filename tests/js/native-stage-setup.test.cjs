const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const {pathToFileURL}=require('node:url');

test('stage browser setup refuses missing or mismatched preflight before runtime discovery',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'stage-setup-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const a={task_id:'t',node_id:'n',holder_id:'h',dispatch_id:'d',executor_ref:'thread:worker',
    direct_browser:{playwright_module:path.join(root,'nonexistent-fixture-runtime.cjs')},
    claim_arguments:{account_ids:['A','B'],work_token:{work_unit_id:'ab',plan_revision:2,requirements_digest:'digest'}}};
  const file=path.join(root,'assignment.json');await fs.writeFile(file,JSON.stringify(a));
  const mod=await import(pathToFileURL(path.resolve(__dirname,'../../api_test_tool/static/native-isolated-browser.mjs')).href);
  const options={assignment_file:file,directory:root,origin:'https://fixture.test'};
  await assert.rejects(mod.prepare(options),/stage.*preflight/i);
  await fs.writeFile(path.join(root,'stage-ready.json'),JSON.stringify({stage_ready:true,identity:a,
    work_token:{...a.claim_arguments.work_token,plan_revision:1},required_context_count:2,account_ids:['A','B']}));
  await assert.rejects(mod.prepare(options),/stage.*preflight/i);
  assert.equal((await fs.readdir(root)).some(name=>name.startsWith('browser-profile-')),false);
});
