const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {bindLease} = require('../../api_test_tool/static/skills/web-exploratory-testing/scripts/lease-channel.cjs');

test('lost registration response closes and records proof before the exit ACK', async () => {
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'lease-startup-test-'));
  const credential=path.join(directory,'credential.json');
  fs.writeFileSync(credential,JSON.stringify({url:'http://localhost:1',token:'isolated-fixture'}));
  const original=global.fetch; const events=[];
  global.fetch=async (_url,options) => {
    const event=JSON.parse(options.body).arguments.arguments.event;
    events.push(event);
    if(event==='register') throw new DOMException('fixture','TimeoutError');
    assert.equal(JSON.parse(fs.readFileSync(path.join(directory,'closed.json'))).browserClosed,true);
    return {ok:true,json:async()=>({closed:true})};
  };
  try {
    await assert.rejects(bindLease({url:'http://localhost:1',holder_id:'h',lease_id:'l',credential_file:credential},
      directory,async()=>{events.push('close');fs.writeFileSync(path.join(directory,'closed.json'),JSON.stringify({browserClosed:true}));},
      (file,value)=>fs.writeFileSync(file,JSON.stringify(value))),{name:'TimeoutError'});
    assert.deepEqual(events,['register','close','closed']);
    assert.equal(JSON.parse(fs.readFileSync(path.join(directory,'startup-failure.json'))).stage,'register');
  } finally {global.fetch=original;fs.rmSync(directory,{recursive:true,force:true});}
});
