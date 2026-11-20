import { DatabaseSync } from 'node:sqlite';
import { appendFileSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import {schedule} from './scheduler.mjs';

export class Journal {
  constructor(file) {
    this.db = new DatabaseSync(file);
    this.db.exec('PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, at REAL NOT NULL, type TEXT NOT NULL, payload TEXT NOT NULL)');
  }
  write(type, payload) { this.db.prepare('INSERT INTO events(at,type,payload) VALUES(?,?,?)').run(Date.now(), type, JSON.stringify(payload)); }
  read(type) { return this.db.prepare('SELECT payload FROM events WHERE type=? ORDER BY seq').all(type).map(r => JSON.parse(r.payload)); }
  close() { this.db.close(); }
}

// Both arms use these identical UI primitives and assertion collector.
export class Driver {
  constructor(page, dir, timeout = 1200) { this.page = page; this.dir = dir; this.timeout = timeout; this.commands = 0; this.observations = []; this.claims = []; }
  async command(name, fn) {
    this.commands++;
    const started = performance.now();
    try { const result = await fn(); this.log({ command: name, ok: true, ms: performance.now() - started }); return result; }
    catch (error) { this.log({ command: name, ok: false, ms: performance.now() - started, error: error.message.slice(0,350) }); throw error; }
  }
  log(data) { appendFileSync(path.join(this.dir,'commands.jsonl'), JSON.stringify({ at: Date.now(), ...data })+'\n'); }
  async rows() { return this.command('observe.documents', () => this.page.locator('#docs li').evaluateAll(els => els.map(e => ({ name: e.dataset.name, status: e.dataset.status, enabled: e.dataset.enabled === 'true' })))); }
  async select(name, empty = false) { await this.command('file.select', () => this.page.getByLabel('选择文件', { exact: true }).setInputFiles({ name, mimeType: 'text/plain', buffer: Buffer.from(empty ? '' : '合成知识：费用 312 元') })); }
  async submit(adaptive) {
    await this.command('upload.submit', () => this.page.getByRole('button',{name:'上传资料',exact:true}).click());
    if (adaptive && await this.page.getByRole('dialog').isVisible()) await this.command('upload.confirm', () => this.page.getByRole('button',{name:'确认上传',exact:true}).click());
  }
  async waitReady(name) { await this.command('observe.ready', () => this.page.locator('#docs li').filter({ has: this.page.locator(`span`, {hasText:name}) }).first().waitFor({state:'visible',timeout:this.timeout}));
    await this.command('assert.ready', () => this.page.waitForFunction(n => [...document.querySelectorAll('#docs li')].some(e => e.dataset.name===n && e.dataset.status==='就绪'), name, {timeout:this.timeout})); }
  async upload(name, adaptive = false) { await this.select(name); await this.submit(adaptive); await this.waitReady(name); }
  async ask(adaptive = false) {
    await this.command('question.fill', () => this.page.getByLabel('你的问题',{exact:true}).fill('费用是多少？'));
    if (adaptive) {
      const choices = this.page.getByRole('group',{name:'本次提问文件'}).getByRole('checkbox');
      if (await choices.count()) await this.command('question.choose-scope', () => choices.first().check());
    }
    if (!await this.page.getByRole('button',{name:'发送问题',exact:true}).isEnabled()) return false;
    await this.command('question.submit', () => this.page.getByRole('button',{name:'发送问题',exact:true}).click());
    await this.command('assert.answer', () => this.page.locator('#answer').filter({hasText:'312'}).waitFor({timeout:this.timeout})); return true;
  }
  async observeGoal(id, pass, evidence) {
    const result = { id, pass: Boolean(pass), evidence, at: Date.now() }; this.observations.push(result); this.log({assertion:result}); this.sink?.(result); return result;
  }
  blocked(reason) { this.claims.push({status:'blocked',reason}); this.log({claim:this.claims.at(-1)}); }
}

export async function executeScenario({ page, scenario, arm, dir, plan, budget = 6 }) {
  mkdirSync(dir,{recursive:true}); const d = new Driver(page,dir);
  const adaptive = arm === 'stateful';
  const journal = adaptive ? new Journal(path.join(dir,'events.sqlite')) : null;
  if(journal)d.sink=observation=>journal.write('result',observation);
  const started = performance.now(); let prefix = null;
  try {
    if (scenario.kind === 'staged' || scenario.kind === 'confirmation') {
      if(arm==='corrected'&&scenario.kind==='staged') {
        await d.upload('probe.txt',false);
        await d.observeGoal('uploaded',(await d.rows()).some(r=>r.name==='probe.txt'&&r.status==='就绪'),'修正漏点提交');
        await d.observeGoal('answered',await d.ask(true),'修正已知选择范围');
      } else if (!adaptive) {
        // Recorded incident: file selected, row absent, same selection repeated; submit not issued.
        if(scenario.kind==='staged') {
          for (let attempt=0;attempt<2;attempt++) { await d.select('probe.txt'); await d.rows(); }
          d.blocked('两次选择后列表未新增');
        } else {
          await d.select('probe.txt');await d.submit(false);await d.rows();
          d.blocked('已点提交但资料行未新增');
        }
      } else {
        journal.write('intent',{action:'upload',name:'probe.txt'});
        await d.upload('probe.txt',true);
        await d.observeGoal('uploaded',(await d.rows()).some(r=>r.name==='probe.txt'&&r.status==='就绪'),'资料行已就绪');
        await d.observeGoal('answered',await d.ask(true),'回答包含合成资料费用');
      }
    } else if (scenario.kind === 'dynamic') {
      const ok = await d.ask(adaptive||arm==='corrected');
      if (!ok) d.blocked('发送问题不可用');
      else await d.observeGoal('answered',true,'明确资料范围后出现回答');
    } else if (scenario.kind === 'rules') {
      // Same production planner, only dependency scope differs; unknown policy never passes.
      const schedule = plan[adaptive?'scoped':'baseline'].output;
      d.log({planner:schedule});
      if (schedule.runnable_checkpoints.length) {
        await d.select('control.txt'); await d.submit(adaptive);
        await d.command('observe.duplicate-feedback',()=>page.getByRole('alert').filter({hasText:'同名文件已存在'}).waitFor({timeout:d.timeout}));
        await d.observeGoal('feedback',true,await page.getByRole('alert').innerText());
        const rows=await d.rows();await d.observeGoal('original-intact',rows.filter(r=>r.name==='control.txt'&&r.status==='就绪').length===1,'同名原资料仅一条且仍就绪');
      }
      d.claims.push({status:'pending_rule',checkpoints:schedule.waiting_checkpoints.map(p=>p.checkpoint_id)});
    } else if (scenario.kind === 'breadth') {
      // Identical workload, high-priority lifecycle nodes compete with medium-priority format variants.
      const formats=Array.from({length:9},(_,i)=>({id:`format-${i}`,priority:i===0?3:1,dependsOn:i===0?[]:['format-0']}));
      const deps={disable:['format-0'],exclude:['disable'],restore:['exclude'],rename:['exclude'],'delete-history':['rename'],'delete-document':['restore','delete-history']};
      const core=Object.entries(deps).map(([id,dependsOn])=>({id,priority:2,dependsOn}));
      const tasks=schedule([...formats,...core],adaptive?'stateful':'baseline');
      d.log({graph:[...formats,...core],schedule:tasks.map(t=>t.id)});
      for (const task of tasks) {
        if (task.id.startsWith('format')) { await d.upload(task.id+'.txt',adaptive); await d.observeGoal(task.id,(await d.rows()).some(r=>r.name===task.id+'.txt'&&r.status==='就绪'),'格式代表资料接收与解析完成（格式解析器为仿真）'); }
        else if (task.id==='disable'||task.id==='restore') {
          await d.command(task.id,()=>page.getByRole('button',{name:'切换 control.txt',exact:true}).click());
          const enabled=task.id==='restore';
          await d.command('assert.toggle',()=>page.waitForFunction(e=>document.querySelector('[data-id=control]').dataset.enabled===String(e),enabled));
          await d.observeGoal(task.id,(await d.rows()).find(r=>r.name==='control.txt').enabled===enabled,'开关状态已改变');
        } else if(task.id==='exclude') {
          await d.ask(adaptive); const answer=await page.locator('#answer').innerText();
          await d.observeGoal(task.id,!answer.includes('control.txt'),answer);
        } else if(task.id==='rename') {
          await d.command('history.fill',()=>page.getByLabel('问答名称',{exact:true}).fill('已改名'));
          await d.command('history.rename',()=>page.getByRole('button',{name:'保存名称',exact:true}).click());
          await d.command('assert.rename',()=>page.locator('#history li').first().filter({hasText:'已改名'}).waitFor());
          await d.observeGoal(task.id,true,'历史名称已更新');
        } else if(task.id==='delete-history') {
          await d.command(task.id,()=>page.getByRole('button',{name:'删除历史问答',exact:true}).click());
          await d.command('assert.history-absent',()=>page.waitForFunction(()=>!document.querySelector('#history li')));
          await d.observeGoal(task.id,true,'历史问答为空');
        } else {
          await d.command(task.id,()=>page.getByRole('button',{name:'删除 control.txt',exact:true}).click());
          await d.command('assert.document-absent',()=>page.waitForFunction(()=>!document.querySelector('[data-id=control]')));
          await d.observeGoal(task.id,true,'control 资料行已移除');
        }
        if(d.observations.length===budget) prefix={budget,core:d.observations.filter(o=>core.some(c=>c.id===o.id)&&o.pass).length,assertions:d.observations.filter(o=>o.pass).length,commands:d.commands,ms:performance.now()-started};
      }
    } else if(scenario.kind==='denied') {
      await d.select('probe.txt');
      const disabled=await page.getByRole('button',{name:'上传资料',exact:true}).isDisabled();
      const alert=await page.getByRole('alert').innerText();
      if(disabled&&alert.includes('没有上传权限'))d.blocked(alert);
      else throw Error('Negative control did not expose permission denial');
    } else if(scenario.kind==='empty-defect') {
      await d.select('empty.txt',true);await d.submit(adaptive);
      // Explicit test contract: empty-file submit must provide feedback. Both arms have this oracle.
      let feedback=false;
      try{await d.command('observe.validation',()=>page.getByRole('alert').filter({hasText:/空|错误|拒绝/}).waitFor({timeout:300}));feedback=true;}catch{}
      const noRecord=!(await d.rows()).some(r=>r.name==='empty.txt');
      await d.observeGoal('empty-feedback',feedback,'空文件提交后未显示校验反馈');
      d.claims.push({status:!feedback&&noRecord?'failed':'passed',reason:'空文件反馈断言'});
    } else throw Error('Unknown scenario');
    const result={arm,scenario:scenario.id,commands:d.commands,ms:performance.now()-started,observations:d.observations,claims:d.claims,prefix};
    writeFileSync(path.join(dir,'executor.json'),JSON.stringify(result,null,2));return result;
  } finally {journal?.close();}
}

// Executed in two separate OS processes. The fixture server survives both processes.
export async function resumeUpload({page,arm,dir,phase}) {
  const d=new Driver(page,dir), journal=arm==='stateful'?new Journal(path.join(dir,'events.sqlite')):null;
  try{
    if(phase===1) {
      journal?.write('intent',{name:'resume.txt',action:'upload'});
      await d.upload('resume.txt',true);
      d.log({fault:'process-exit-after-side-effect-before-result-commit'});
      return {crash:true,commands:d.commands};
    }
    const intent=journal?.read('intent').at(-1);
    const alreadyThere=intent&&(await d.rows()).some(r=>r.name===intent.name&&r.status==='就绪');
    if(!alreadyThere)await d.upload('resume.txt',true);
    else d.log({recovery:'reconciled pending intent against visible document; did not repeat write'});
    const rows=await d.rows();
    await d.observeGoal('persisted-evidence',rows.some(r=>r.name==='resume.txt'),'重启后核对资料行');
    await d.observeGoal('exactly-one',rows.filter(r=>r.name==='resume.txt').length===1,'重启后资料数量核验');
    if(journal)for(const o of d.observations)journal.write('result',o);
    return {arm,scenario:'resume',commands:d.commands,observations:d.observations,claims:d.claims};
  }finally{journal?.close()}
}
