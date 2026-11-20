import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { spawn, execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { startFixture } from './fixture.mjs';
import { executeScenario } from './executor.mjs';
import { makeReport } from './report.mjs';
import { grade } from './grader.mjs';

const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../..');
const protocol=JSON.parse(readFileSync(path.join(here,'protocol.json')));
const out=path.resolve(process.argv[2]||path.join(root,'output/playwright/execution-benchmark',new Date().toISOString().replaceAll(':','-')));
const repeats=Number(process.env.BENCH_REPEATS||protocol.repeats);
if(!Number.isInteger(repeats)||repeats<1||repeats>20)throw Error('repeats must be 1..20');
if(!process.env.PLAYWRIGHT_MODULE)throw Error('Set PLAYWRIGHT_MODULE to an installed playwright/index.mjs (see README).');
mkdirSync(path.dirname(out),{recursive:true});mkdirSync(out);
const plan=JSON.parse(execFileSync(process.env.BENCH_PYTHON||'python3',[path.join(here,'planner.py')],{cwd:root,encoding:'utf8'}));
writeFileSync(path.join(out,'planner.json'),JSON.stringify(plan,null,2));
const fingerprint=Object.fromEntries(['protocol.json','executor.mjs','fixture.mjs','fixture.html','planner.py','run.mjs','resume-worker.mjs','report.mjs','grader.mjs','scheduler.mjs'].map(f=>[f,createHash('sha256').update(readFileSync(path.join(here,f))).digest('hex')]));
const manifest={startedAt:new Date().toISOString(),revision:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),fingerprint,protocol,repeats,node:process.version,planner:plan.sha256,modelCalls:0,comparison:protocol.comparison};
writeFileSync(path.join(out,'manifest.json'),JSON.stringify(manifest,null,2));
const {chromium}=await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const fixture=await startFixture();let browser;const results=[];
const child=async(args)=>new Promise((resolve,reject)=>{
  const p=spawn(process.execPath,[path.join(here,'resume-worker.mjs'),...args],{env:process.env,stdio:['ignore','pipe','pipe']});
  let stderr='';p.stderr.on('data',d=>{stderr+=d});p.on('error',reject);
  const timer=setTimeout(()=>p.kill('SIGTERM'),30000);
  p.on('close',code=>{clearTimeout(timer);if(![0,75].includes(code))reject(Error(`resume worker exit ${code}: ${stderr.slice(-2000)}`));else resolve(code)});
});
try{
  browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'chrome'});
  manifest.browser=await browser.version();
  for(let repeat=0;repeat<repeats;repeat++){
    // Alternate order to reduce one-arm warm-up advantage. No shared UI/account state.
    const arms=['baseline','corrected','stateful'];
    for(let rotate=0;rotate<repeat%3;rotate++)arms.push(arms.shift());
    for(const scenario of protocol.scenarios)for(const arm of arms){
      const id=`${repeat}-${scenario.id}-${arm}`,dir=path.join(out,id);mkdirSync(dir,{recursive:true});
      fixture.add(id,{...scenario.config,delay:30+repeat*17});
      let run;const start=performance.now();
      if(scenario.kind==='resume'){
        const first=await child([fixture.origin,id,arm,dir,'1']);
        if(first!==75)throw Error('Fault injection did not stop process before commit');
        const second=await child([fixture.origin,id,arm,dir,'2']);if(second!==0)throw Error('Recovery failed');
        const phase1=JSON.parse(readFileSync(path.join(dir,'phase-1.json'))),phase2=JSON.parse(readFileSync(path.join(dir,'phase-2.json')));
        run={...phase2,commands:phase1.commands+phase2.commands,ms:performance.now()-start};
      }else{
        const context=await browser.newContext({viewport:{width:1200,height:850}});
        await context.route('**/*',route=>new URL(route.request().url()).origin===fixture.origin?route.continue():route.abort());
        await context.tracing.start({screenshots:true,snapshots:true});
        try{
          const page=await context.newPage();page.setDefaultTimeout(2000);
          await page.goto(`${fixture.origin}/?run=${id}`);await page.waitForFunction(()=>document.body.dataset.revision!==undefined);
          run=await executeScenario({page,scenario,arm,dir,plan,budget:protocol.prefix_budget});
          await page.screenshot({path:path.join(dir,'final.png'),fullPage:true});
        }finally{await context.tracing.stop({path:path.join(dir,'trace.zip')});await context.close()}
      }
      const state=fixture.get(id),truth={...state};delete truth.timers;
      writeFileSync(path.join(dir,'truth.json'),JSON.stringify(truth,null,2));
      const judged=grade(scenario,run,truth);
      const result={...run,...judged,repeat,cohort:scenario.cohort,title:scenario.title,artifact:path.relative(out,dir),writes:state.events.filter(e=>e.action==='upload').length};
      results.push(result);writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2));
      console.log(JSON.stringify({repeat,scenario:scenario.id,arm,coverage:`${judged.verified}/${judged.total}`,falseBlocks:judged.falseBlocks,ms:Math.round(run.ms)}));
    }
  }
  manifest.finishedAt=new Date().toISOString();writeFileSync(path.join(out,'manifest.json'),JSON.stringify(manifest,null,2));
  const summary=makeReport({out,manifest,results,plan});
  console.log(JSON.stringify({report:path.join(out,'index.html'),summary}));
}finally{await browser?.close();await fixture.close()}
