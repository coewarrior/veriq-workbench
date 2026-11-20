import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { resumeUpload } from './executor.mjs';

const [origin,run,arm,dir,phase] = process.argv.slice(2);
if(new URL(origin).hostname!=='127.0.0.1')throw Error('Only loopback fixtures allowed');
const {chromium}=await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'chrome'});
mkdirSync(dir,{recursive:true});
try{
  const context=await browser.newContext();
  await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
  const page=await context.newPage();page.setDefaultTimeout(2000);
  await page.goto(`${origin}/?run=${run}`);await page.waitForFunction(()=>document.body.dataset.revision!==undefined);
  const result=await resumeUpload({page,arm,dir,phase:Number(phase)});
  await page.screenshot({path:path.join(dir,`phase-${phase}.png`),fullPage:true});
  writeFileSync(path.join(dir,`phase-${phase}.json`),JSON.stringify(result,null,2));
  process.exitCode=result.crash?75:0;
}finally{await browser.close()}
