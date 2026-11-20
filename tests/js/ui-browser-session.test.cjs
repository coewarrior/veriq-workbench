'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const source = path.resolve(__dirname, '../../api_test_tool/static/skills/web-exploratory-testing/scripts/browser-session.cjs');
const {actAndWait, createJobs} = require(source);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(read) {
  for (let i = 0; i < 100; i++) { if (await read()) return; await sleep(20); }
  throw Error('local fixture did not become ready');
}

test('response rejects before click settles without losing the process or replaying action', async () => {
  let clicks = 0, finished = false;
  await assert.rejects(actAndWait(
    () => new Promise((_, reject) => setTimeout(() => reject(Error('response timeout')), 5)),
    async () => { clicks++; await sleep(30); finished = true; }
  ), /response timeout/);
  assert.equal(finished, true);
  assert.equal(clicks, 1);
  await assert.rejects(actAndWait(
    () => new Promise((_, reject) => setTimeout(() => reject(Error('late event')), 5)),
    () => { throw Error('click failed'); }
  ), /click failed/);
});

test('job errors preserve uncertain outcomes, reject concurrency and never replay IDs', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ui-jobs-'));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  let release;
  const state = {count: 0, gate: new Promise(resolve => { release = resolve; })};
  const jobs = createJobs(dir, state);
  const code = 's.count++; await s.gate; throw Error("private-secret");';
  jobs.submit('one', code);
  assert.throws(() => jobs.submit('two', 'return 2'), /busy/);
  jobs.submit('one', code);
  assert.throws(() => jobs.submit('one', 'return 3'), /conflict/);
  release();
  await until(() => !jobs.active);
  assert.equal(jobs.read('one').status, 'uncertain');
  assert.equal(JSON.stringify(jobs.read('one')).includes('private-secret'), false);
  jobs.submit('one', code);
  assert.equal(state.count, 1);
  jobs.submit('two', 'return {count:s.count};');
  await until(() => !jobs.active);
  assert.equal(jobs.read('two').result.count, 1);
  assert.equal(fs.statSync(path.join(dir, 'one.json')).mode & 0o777, 0o600);
});

test('controller handshakes with closed stdin and isolates authenticated local commands', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ui-session-'));
  const sessionDir = path.join(dir, 'session');
  const moduleFile = path.join(dir, 'fake-browser.cjs');
  // Transport fixture only: never launches a real browser or accesses a site.
  fs.writeFileSync(moduleFile, `exports.chromium={launch:async()=>{
    let connected=true;return {isConnected:()=>connected,close:async()=>{connected=false},
    newContext:async()=>({newPage:async()=>({setDefaultTimeout(){},setDefaultNavigationTimeout(){}})})};}};`);
  const runtime = path.join(dir, 'runtime.json');
  fs.writeFileSync(runtime, JSON.stringify({module: moduleFile}));
  const child = spawn(process.execPath, [source, 'serve', sessionDir, runtime], {stdio: 'ignore'});
  t.after(() => { child.kill(); fs.rmSync(dir, {recursive: true, force: true}); });
  const file = path.join(sessionDir, 'session.json');
  await until(() => fs.existsSync(file));
  const session = JSON.parse(fs.readFileSync(file, 'utf8'));
  const url = 'http://127.0.0.1:' + session.port;
  const headers = {Authorization: 'Bearer ' + session.token};
  assert.equal((await fetch(url + '/status')).status, 403);
  assert.equal((await fetch(url + '/status', {headers: {...headers, Origin: 'http://example.invalid'}})).status, 403);
  assert.equal((await (await fetch(url + '/status', {headers})).json()).ready, true);
  await fetch(url + '/run', {method: 'POST', headers, body: JSON.stringify({id: 'a', code: 'throw Error("secret");'})});
  await until(async () => !(await (await fetch(url + '/status', {headers})).json()).active);
  assert.equal((await (await fetch(url + '/result?id=a', {headers})).json()).status, 'uncertain');
  await fetch(url + '/close', {method: 'POST', headers});
  await until(() => child.exitCode !== null);
  assert.equal(child.exitCode, 0);
  assert.equal(fs.existsSync(file), false);
  assert.equal(JSON.parse(fs.readFileSync(path.join(sessionDir, 'closed.json'))).browserClosed, true);
});
