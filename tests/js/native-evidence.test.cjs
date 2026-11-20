const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
test('evidence keeps context, previews the captured bytes once, never replays business',async()=>{
  const directory=await fs.mkdtemp(path.join(os.tmpdir(),'evidence-fixture-'));
  try {
    const source=await fs.readFile('api_test_tool/static/native-browser-case.js','utf8');
    await fs.writeFile(path.join(directory,'helper.mjs'),source+'\nexport {nativeCaptureEvidence};');
    const {nativeCaptureEvidence}=await import(pathToFileURL(path.join(directory,'helper.mjs')).href);
    const calls=[];let previews=0;
    const page={screenshot:async args=>{calls.push(args);await fs.writeFile(args.path,'fixture image');return Buffer.from('fixture image');}};
    const result=await nativeCaptureEvidence({page,case_id:'original-case',step:'最终地点仍为不限',directory,
      preview:async bytes=>{previews++;assert.equal(bytes.toString(),'fixture image');}});
    assert.equal(calls.length,1);assert.equal(previews,1);
    assert.equal(calls[0].fullPage,false);assert.equal(calls[0].clip,undefined);
    assert.equal(result.assets[0].case_id,'original-case');assert.equal(result.assets[0].step,'最终地点仍为不限');
    assert.ok(result.assets[0].captured_at);assert.equal(result.semantic_review_complete,false);
    assert.equal((await fs.stat(result.assets[0].file)).mode&0o777,0o600);
  } finally {await fs.rm(directory,{recursive:true,force:true});}
});
test('failed capture is recorded once without retry, login or navigation',async()=>{
  const directory=await fs.mkdtemp(path.join(os.tmpdir(),'evidence-fixture-'));
  try {
    const source=await fs.readFile('api_test_tool/static/native-browser-case.js','utf8');
    await fs.writeFile(path.join(directory,'helper.mjs'),source+'\nexport {nativeCaptureEvidence};');
    const {nativeCaptureEvidence}=await import(pathToFileURL(path.join(directory,'helper.mjs')).href);
    let calls=0;
    const result=await nativeCaptureEvidence({page:{screenshot:async()=>{calls++;throw Error('capture interrupted');}},
      case_id:'original-case',step:'错误仍可见',directory});
    assert.equal(calls,1);assert.equal(result.assets.length,0);assert.match(result.capture_error,/capture interrupted/);
  } finally {await fs.rm(directory,{recursive:true,force:true});}
});
