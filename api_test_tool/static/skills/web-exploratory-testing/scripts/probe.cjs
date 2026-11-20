// A capability test, not an exact-version gate. No target site is contacted.
const {chromium} = require(process.argv[2]);
const fs = require('node:fs/promises'), os = require('node:os'), path = require('node:path');
(async () => {
  let browser, context, directory;
  try {
    browser = await chromium.launch({headless:true, ...(process.argv[3] ? {channel:process.argv[3]} : {})});
    if(process.argv[4] === 'video') directory = await fs.mkdtemp(path.join(os.tmpdir(), 'ui-video-probe-'));
    context = await browser.newContext(directory ? {recordVideo:{dir:directory}} : {});
    const page = await context.newPage();
    await page.setContent('<input aria-label="probe"><button onclick="document.body.dataset.done=document.querySelector(\'input\').value">Check</button>');
    await page.locator('input').fill('ready');
    await page.locator('button').click();
    if(await page.locator('body').getAttribute('data-done') !== 'ready') throw Error('interaction probe failed');
    await page.screenshot();
    const video=page.video();
    await context.close();context=null;
    if(video && !(await fs.stat(await video.path())).size) throw Error('video probe failed');
    console.log(JSON.stringify({ok:true, browser:browser.version()}));
  } finally { try { if(context) await context.close(); } finally { if(browser) await browser.close(); if(directory) await fs.rm(directory,{recursive:true,force:true}); } }
})().catch(error => {console.error(error.message); process.exitCode=1;});
