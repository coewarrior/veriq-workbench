// Used by Codex-authored local test scripts. Does not execute a test on import.
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');

async function runCase(runtime, {caseId, directory, recordVideo=false, headed=false}, test) {
  const {chromium} = require(runtime.module);
  const root = path.resolve(directory, crypto.randomUUID());
  await fs.mkdir(root, {recursive:true, mode:0o700});
  const browser = await chromium.launch({headless:!headed, ...(runtime.channel ? {channel:runtime.channel} : {})});
  let context, page, video, result, failure;
  const assets = [];
  const started_at = new Date().toISOString();
  const capture = async step => {
    const file = path.join(root, crypto.randomUUID() + '.png');
    const captured_at = new Date().toISOString();
    await page.screenshot({path:file});
    assets.push({case_id:caseId,step,kind:'screenshot',captured_at,path:file});
    return file;
  };
  try {
    context = await browser.newContext(recordVideo ? {recordVideo:{dir:root}} : {});
    page = await context.newPage();
    video = page.video();
    // Call capture immediately on observed discrepancy, before recovery/retry.
    // The catch below captures only the state at assertion failure, not a past instant.
    result = await test({page,context,capture});
  } catch(error) {
    failure = error;
    if(page && !page.isClosed()) {
      try { await capture('断言失败时的页面（不代表最早故障帧）'); } catch {}
    }
  } finally {
    try { if(context) await context.close(); }
    finally { await browser.close(); }
    if(video) assets.push({case_id:caseId,step:'本用例执行过程',kind:'video',captured_at:started_at,path:await video.path()});
    await fs.writeFile(path.join(root, 'evidence.json'), JSON.stringify({case_id:caseId,assets},null,2),{mode:0o600});
  }
  if(failure) {failure.evidence=assets; throw failure;}
  return {result,assets};
}
module.exports = {runCase};
