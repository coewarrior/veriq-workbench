// State regressions over the actual browser script; no browser or dependency.
// Run: node --test work/web-components/test_web_ui_state.mjs
// Override API_TEST_APP_JS when placing this test elsewhere.
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';

const appPath = process.env.API_TEST_APP_JS || new URL('../../api_test_tool/static/app.js', import.meta.url);
const source = readFileSync(appPath, 'utf8').replace(/\ninit\(\)\.catch[\s\S]*$/, '');
const uiWorkflowSource = readFileSync(new URL('../../api_test_tool/static/ui-workflow.js', import.meta.url), 'utf8');

function harness(connected=false, pathname="/api-testing") {
  const requests=[];
  const copied=[];
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      id, hidden: false, disabled: false, textContent: '', value: '', dataset: {},
      _html: '', details: null, open:false,
      reset() {}, showModal() { this.open=true; }, close() { this.open=false; }, select() {}, focus() {},
      get innerHTML() { return this._html; },
      set innerHTML(html) {
        this._html=html;
        const tag=html.match(/<details\b([^>]*)>/);
        this.details=tag ? {open: /\bopen\b/.test(tag[1])} : null;
      },
      querySelector(selector) { return selector==='details' ? this.details : selector==='.connection-dot' ? element(id+'-dot') : null; },
      classList: {toggle() {}, add() {}, remove() {}, contains() { return false; }}, addEventListener() {},
    });
    return elements.get(id);
  };
  const context = vm.createContext({
    document: {getElementById: element, querySelector: element, querySelectorAll: () => [], addEventListener() {}},
    fetch: async (path, options) => {
      requests.push({path,method:options.method});
      const data=path==='/api/mcp/status'?{connected}:path==='/api/mcp/pair'?{code:'sample-pair-code',expires_in:600}:{};
      return {ok:true,json:async()=>data};
    },
    TextEncoder, URL, URLSearchParams, setTimeout() { return 1; }, clearTimeout() {},
    navigator: {clipboard: {writeText: async text => {copied.push(text);}}},
    window: {isSecureContext: true},
    location: {protocol: 'https:', hostname: 'localhost', origin:'https://localhost', pathname},
    history: {replaceState() {}},
  });
  vm.runInContext(readFileSync(new URL('../../api_test_tool/static/codex-progress.js', import.meta.url),'utf8'), context);
  vm.runInContext(readFileSync(new URL('../../api_test_tool/static/ui-workflow.js', import.meta.url),'utf8'), context);
  vm.runInContext(source, context);
  vm.runInContext(readFileSync(new URL('../../api_test_tool/static/workflow-tools.js', import.meta.url),'utf8'), context);
  vm.runInContext(readFileSync(new URL('../../api_test_tool/static/manual-cases.js', import.meta.url),'utf8'), context);
  vm.runInContext("state.bootstrap={projects:[],environments:[],model:{},apis:{items:[]}}",context);
  return {requests, copied, elements, element, evaluate: text => vm.runInContext(text, context)};
}

test('session rename pre-fills the selected name and refreshes the active heading', async () => {
  const page=harness(false,'/ui-testing');
  page.evaluate("state.bootstrap.projects=[{id:'ui',title:'原名称',test_kind:'ui',updated_at:'2026-10-08T00:00:00Z'}];state.project={...state.bootstrap.projects[0]};openRenameDialog('ui')");
  assert.equal(page.element('rename-dialog').open,true);
  assert.equal(page.element('rename-input').value,'原名称');
  page.element('rename-input').value='新名称';
  page.evaluate("fetch=async (path, options)=>({ok:true,json:async()=>({project:{id:'ui',title:'新名称',updated_at:'2026-10-08T01:00:00Z'}})})");
  await page.evaluate('saveSessionName()');
  assert.equal(page.element('rename-dialog').open,false);
  assert.equal(page.element('current-title').textContent,'新名称');
  assert.match(page.element('project-list').innerHTML,/新名称/);
  assert.equal(page.evaluate('state.project.title'),'新名称');
});

test('finishing a background job restores import for the next project', () => {
  const page = harness();
  page.evaluate("state.job={status:'running',message:'running',logs:[]};renderJob()");
  assert.equal(page.element('import-button').disabled, true);
  page.evaluate("state.job={status:'completed',message:'done',logs:[]};renderJob()");
  assert.equal(page.element('import-button').disabled, false);
});

test('clearing the current job does not leave new-project import disabled', () => {
  const page = harness();
  page.evaluate("state.job={status:'running',message:'running',logs:[]};renderJob()");
  page.evaluate("state.job=null;renderJob()");
  assert.equal(page.element('import-button').disabled, false);
});

test('incomplete run cannot be described as all passed when business assertions passed', () => {
  const page = harness();
  page.evaluate(`state.project={
    runs:[], last_run:{
      created_at:'2026-09-09T10:00:00Z',environment:{name:'local'},
      report_url:'/api/projects/p/reports/r/index.html',requests_sent:2,
      cleanup:{status:'NOT_CONFIGURED'},
      summary:{total:1,PASS:1,FAIL:0,BROKEN:0,BLOCKED:0,QUARANTINED:0,UNSUPPORTED:0,complete:false}
    }
  };renderReports()`);
  assert.equal(page.element('report-panel').innerHTML.includes('本轮已全部通过'), false);
  assert.equal(page.element('report-panel').innerHTML.includes('部分用例需关注'), true);
  assert.equal(page.element('report-panel').innerHTML.includes('target="_blank"'), false);
  assert.match(page.element('report-panel').innerHTML, /打开完整测试报告 →/);
});

test('session workflow blocks future steps until their inputs exist', () => {
  const page=harness();
  assert.equal(page.evaluate('canEnterStage(2)'),false);
  assert.equal(page.evaluate('canEnterStage(3)'),false);
  assert.equal(page.evaluate('canEnterStage(4)'),false);
  page.evaluate('state.project={};state.contract={operations:{read:{}}}');
  assert.equal(page.evaluate('canEnterStage(2)'),true);
  assert.equal(page.evaluate('canEnterStage(3)'),false);
  page.evaluate('state.bundle={cases:[]}');
  assert.equal(page.evaluate('canEnterStage(3)'),true);
  page.evaluate('state.project.last_run={id:"run"}');
  assert.equal(page.evaluate('canEnterStage(4)'),true);
});

test('generated cases expose a same-tab readable case report', () => {
  const page=harness();
  page.evaluate(`state.project={id:'11111111-1111-4111-8111-111111111111'};state.contract={operations:{register:{}}};state.bundle={rules:[],contract:{sources:{}},cases:[{id:'REG-001',title:'注册',operation_id:'register',scenario:'normal',state:'READY',steps:[],cleanup_steps:[]}]};renderGeneration();renderCLI()`);
  const html=page.element('cases-panel').innerHTML;
  assert.match(html,/打开用例报告 →/);
  assert.match(html,/\/api\/projects\/11111111-1111-4111-8111-111111111111\/case-report/);
  assert.equal(html.includes('target="_blank"'),false);
  assert.match(page.element('asset-links').innerHTML,/用例报告 →/);
});

test('UI preparation and execution point to one information form on the source page', () => {
  const page=harness(false,'/ui-testing');
  page.evaluate("state.project={id:'ui',title:'官网测试',ui_target_url:'https://example.com',task:{goal:'完整测试'}};state.codexGoal='完整测试';UIWorkflow.renderPreparation();UIWorkflow.renderExecution()");
  assert.equal(page.evaluate('UIWorkflow.stage(3)'),2);
  assert.equal(page.element('execution-panel').innerHTML,'');
  const html=page.element('generation-panel').innerHTML;
  assert.match(html,/ui-test-actions/);
  assert.match(html,/id="ui-handoff"/);
  assert.doesNotMatch(html,/<form|<textarea|官网测试|https:\/\/example.com|data-ui-materials|data-scene-retention|更多操作/);
  page.evaluate('UIWorkflow.renderDocument()');
  const information=page.element('ui-document-panel').innerHTML;
  assert.match(information,/<form id="ui-information-form">/);
  assert.match(information,/<textarea[^>]*name="goal"[^>]*>完整测试<\/textarea>/);
  assert.match(information,/name="requirements"/);
  assert.match(information,/data-ui-attachment-input/);
  assert.match(information,/保存测试信息/);
  assert.doesNotMatch(information,/ui-attachments-form|requirement-materials-form|查看或补充附件/);
});

test('completed UI cases do not prevent handing off a changed goal or a newly prepared round',()=>{
  const page=harness(false,'/ui-testing');
  page.evaluate("state.project={id:'ui',title:'测试',task:{goal:'原目标'},last_analysis:{created_at:'2026-10-09T00:00:00Z'}};state.codexGoal='原目标';UIWorkflow.renderPreparation();UIWorkflow.updateAction({cases:[{status:'passed'}],report_id:'report'})");
  assert.equal(page.element('ui-handoff').disabled,true);
  page.evaluate("state.codexGoal='新的测试目标';UIWorkflow.updateAction({cases:[{status:'passed'}],report_id:'report'})");
  assert.equal(page.element('ui-handoff').disabled,false);
  page.evaluate("state.codexGoal='原目标';state.project.mcp_progress={phase:'waiting',updated_at:Date.parse('2026-10-09T00:01:00Z')/1000};UIWorkflow.updateAction({cases:[{status:'passed'}],report_id:'report'})");
  assert.equal(page.element('ui-handoff').disabled,false);
});

test('UI handoff tells the executor to close only its own browser resources', () => {
  const page=harness(false,'/ui-testing');
  const prompt=page.evaluate("UIWorkflow.message({id:'ui',title:'官网测试',ui_target_url:'https://example.com',task:{goal:'完整测试'}},'example-code')");
  assert.match(prompt,/结束前对照启动时的窗口和标签状态/);
  assert.match(prompt,/关闭并核实本轮创建的标签、独立浏览器、文件选择框和驱动进程/);
  assert.match(prompt,/不关闭用户原有窗口或其他测试任务的资源/);
  assert.match(prompt,/异常退出也要收尾/);
  assert.match(prompt,/交接消息未提供，以 get_test_document.scene_retention 为准/);
  assert.doesNotMatch(prompt,/不保留测试现场（none）/);
  const connectOnly=page.evaluate("UIWorkflow.message(null,'example-code')");
  assert.doesNotMatch(connectOnly,/关闭并核实本轮创建的标签/);
});

test('UI handoff carries the selected scene policy without changing the testing goal', () => {
  const page=harness(false,'/ui-testing');
  page.evaluate("state.project={id:'ui',title:'资料测试',filename:'ui-test.md',test_kind:'ui',ui_target_url:'https://example.test',ui_scene_retention:{key:'defects',label:'仅保留缺陷现场'},task:{goal:'完整探索'}}");
  const prompt=page.evaluate("mcpMessage(mcpSessionTarget(),'example-code')");
  assert.match(prompt,/仅保留缺陷现场（defects）/);
  assert.match(prompt,/scene_outcome/);
  assert.match(prompt,/完整探索/);
});

test('a regression from imported results points to the same information form', () => {
  const page=harness(false,'/ui-testing');
  page.evaluate("state.project={id:'ui',title:'回归',ui_target_url:'https://example.test',ui_import_filename:'baseline.xlsx',regression_round:{report_id:'old'},task:{goal:'复测'}};UIWorkflow.renderPreparation()");
  assert.match(page.element('generation-panel').innerHTML,/ui-test-actions/);
  assert.doesNotMatch(page.element('generation-panel').innerHTML,/<textarea|data-ui-materials|data-scene-retention-toggle|已导入测试结果/);
  page.evaluate('UIWorkflow.renderDocument()');
  assert.match(page.element('ui-document-panel').innerHTML,/<textarea[^>]*name="goal"[^>]*>复测<\/textarea>/);
});

test('a session uses its own API instead of a newly selected global default', () => {
  const page=harness();
  page.evaluate(`state.bootstrap={model:{id:'b',model:'B'},apis:{active_id:'b',items:[{id:'a',model:'A',name:'A',has_key:true},{id:'b',model:'B',name:'B',has_key:true}]}};state.project={api_profile_id:'a'}`);
  assert.equal(page.evaluate('sessionModel().model'),'A');
  assert.match(page.evaluate('apiOptions()'), /value="a" selected/);
  page.evaluate("state.bootstrap.apis.items=state.bootstrap.apis.items.filter(a=>a.id!=='a')");
  assert.equal(page.evaluate('sessionModel().has_key'),false);
});


test('empty output budget stays automatic and large manual values survive', () => {
  const page=harness();
  assert.equal(page.evaluate('readOutputTokens()'),null);
  page.element('model-max-tokens').value='384000';
  assert.equal(page.evaluate('readOutputTokens()'),384000);
  page.evaluate("state.bootstrap={auto_output_tokens:{'deepseek-v4-flash':384000}}");
  assert.match(page.evaluate("outputBudgetLabel({model:'deepseek-v4-flash',max_tokens:null})"),/384,000/);
  page.element('model-max-tokens').value='0';
  assert.throws(()=>page.evaluate('readOutputTokens()'));
});


test('execution log keeps the user toggle across polling, completion and session switches', () => {
  const page=harness(), panel=page.element('job-status');
  page.evaluate("state.job={id:'a',status:'running',message:'working',logs:[{at:1,message:'first'}]};renderJob()");
  assert.equal(panel.details.open,true);
  panel.details.open=false;
  page.evaluate("state.job.logs.push({at:2,message:'second'});renderJob();renderJob()");
  assert.equal(panel.details.open,false);
  assert.match(panel.innerHTML,/second/);
  page.evaluate("state.job.status='completed';renderJob()");
  assert.equal(panel.details.open,false);
  page.evaluate("state.job={...state.job,id:'b',status:'running'};renderJob()");
  assert.equal(panel.details.open,true);
  page.evaluate("state.job={...state.job,id:'a',status:'completed'};renderJob()");
  assert.equal(panel.details.open,false);
  panel.details.open=true;
  page.evaluate('renderJob();renderJob()');
  assert.equal(panel.details.open,true);
});


test('global Codex connection never includes the remembered project, including API management', async () => {
  const page=harness();
  page.evaluate("state.stage=5;state.project={id:'previous-project',title:'旧会话',filename:'old.yaml'};state.contract={operations:{read:{}}}");
  await page.evaluate('openMCP()');
  await page.evaluate('pairMCP()');
  assert.equal(page.element('mcp-title').textContent,'授权 Codex 访问测试台');
  assert.equal(page.element('mcp-target').hidden,true);
  assert.match(page.element('mcp-prompt').value,/本次仅授权连接测试台/);
  assert.doesNotMatch(page.element('mcp-prompt').value,/previous-project|old.yaml|旧会话/);
  assert.equal(page.evaluate('state.stage'),5);
});

test('copy confirmation stays next to the Codex action instead of using the page toast', async () => {
  const page=harness();
  await page.evaluate('openMCP()');
  page.element('toast').hidden=true;
  await page.evaluate("handleClick({target:{closest:()=>document.getElementById('copy-mcp')}})");
  assert.equal(page.copied.length,1);
  assert.equal(page.copied[0],page.element('mcp-prompt').value);
  assert.match(page.element('mcp-copy-feedback').textContent,/复制成功/);
  assert.equal(page.element('toast').hidden,true);
  page.evaluate("mcpCopyFeedback()");
  assert.equal(page.element('mcp-copy-feedback').textContent,'');
});

test('a blocked clipboard write reports the error inside the Codex dialog', async () => {
  const page=harness();
  await page.evaluate('openMCP()');
  page.element('toast').hidden=true;
  page.evaluate("navigator.clipboard.writeText=async()=>{throw Error('浏览器拒绝复制')}");
  await page.evaluate("handleClick({target:{closest:()=>document.getElementById('copy-mcp')}})");
  assert.match(page.element('mcp-copy-feedback').textContent,/浏览器拒绝复制/);
  assert.equal(page.element('toast').hidden,true);
});

test('session handoff requires a saved document but not parsed operations', async () => {
  const page=harness();
  await assert.rejects(page.evaluate("openMCP('session')"),/请先保存接口文档/);
  page.evaluate("state.project={id:'p',filename:'empty.yaml'};state.contract={operations:{}}");
  await page.evaluate("openMCP('session')");
  assert.match(page.element('mcp-target').innerHTML,/empty.yaml/);
  assert.equal(page.requests.length,2);
});

test('session handoff includes a fresh code even when another Codex is already connected', async () => {
  const page=harness(true);
  page.evaluate("state.project={id:'session-a',title:'用户中心',filename:'users.yaml'};state.contract={operations:{read:{}}}");
  await page.evaluate("openMCP('session')");
  assert.match(page.element('mcp-prompt').value,/session-a/);
  assert.match(page.element('mcp-prompt').value,/users.yaml/);
  assert.match(page.element('mcp-prompt').value,/交付最终中文可视化报告/);
  assert.match(page.element('mcp-prompt').value,/正向、逆向、边界和安全/);
  assert.doesNotMatch(page.element('mcp-prompt').value,/全部 22 个维度/);
  assert.doesNotMatch(page.element('mcp-prompt').value,/等待我选择测试环境后再执行|本次任务到生成和校验用例为止/);
  assert.equal(page.element('pair-mcp').hidden,false);
  assert.match(page.element('mcp-prompt').value,/sample-pair-code/);
  assert.match(page.element('mcp-prompt').value,/https:\/\/localhost\/static\/agent-guide.md/);
  assert.equal(page.requests.length,2);
  assert.equal(page.requests[0].path,'/api/mcp/status');
});

test('switching sessions clears the old code and task; workspace pairing stays separate', async () => {
  const page=harness();
  page.evaluate("state.project={id:'a',title:'<img src=x>',filename:'a.yaml'};state.contract={operations:{read:{}}}");
  await page.evaluate("openMCP('session')");
  assert.match(page.element('mcp-target').innerHTML,/&lt;img/);
  await page.evaluate('pairMCP()');
  assert.match(page.element('mcp-prompt').value,/会话 ID：a/);
  page.evaluate("state.project={id:'b',title:'乙',filename:'b.yaml'}");
  await page.evaluate("openMCP('session')");
  assert.match(page.element('mcp-prompt').value,/sample-pair-code/);
  await page.evaluate('pairMCP()');
  assert.match(page.element('mcp-prompt').value,/会话 ID：b/);
  assert.doesNotMatch(page.element('mcp-prompt').value,/a.yaml/);
  await page.evaluate('openMCP()');
  assert.match(page.element('mcp-prompt').value,/sample-pair-code/);
  await page.evaluate('pairMCP()');
  assert.doesNotMatch(page.element('mcp-prompt').value,/会话 ID|b.yaml/);
});

test('Codex generation points to the imported document and has a session refresh action', () => {
  const page=harness();
  page.evaluate("state.bootstrap={environments:[]};state.mode='mcp';state.project={id:'p',title:'资源管理',filename:'items.yaml'};state.contract={operations:{read:{}}};renderGeneration()");
  assert.match(page.element('generation-panel').innerHTML,/文档：items.yaml/);
  assert.match(page.element('generation-panel').innerHTML,/交给 Codex 完成任务/);
  assert.doesNotMatch(page.element('generation-panel').innerHTML,/codex-environment|测试环境|五子棋/);
  assert.match(page.element('generation-panel').innerHTML,/文档中保存的测试地址/);
  page.evaluate('renderCodexProgress()');
  assert.match(page.element('codex-progress-panel').innerHTML,/refresh-mcp-project/);
  assert.match(page.element('generation-panel').innerHTML,/修改测试地址/);
});


test('document analysis report is reachable without any executable cases', () => {
  const page=harness();
  page.evaluate("state.project={id:'doc',last_analysis:{id:'r',title:'文档检查',kind:'analysis',created_at:'2026-09-10',report_url:'/api/projects/doc/reports/r/index.html'},analysis_reports:[]};state.contract={operations:{}};state.bundle=null");
  assert.equal(page.evaluate('canEnterStage(2)'),true);
  assert.equal(page.evaluate('canEnterStage(4)'),true);
  page.evaluate('renderReports()');
  assert.match(page.element('report-panel').innerHTML,/打开完整报告/);
  assert.match(page.element('report-panel').innerHTML,/文档分析结果不代表接口测试通过/);
  assert.doesNotMatch(page.element('report-panel').innerHTML,/target="_blank"/);
});

test('a document-only goal is carried intact in the autonomous task message', async () => {
  const page=harness(true);
  page.evaluate("state.project={id:'doc',title:'文档',filename:'notes.md',task:{goal:'只检查接口文档，不发送请求',environment:'auto'}};state.contract={operations:{}}");
  await page.evaluate("openMCP('session')");
  assert.match(page.element('mcp-prompt').value,/任务目标：只检查接口文档，不发送请求/);
  assert.match(page.element('mcp-prompt').value,/无需构造可执行用例/);
});

test('interface management remains available for an empty imported scope', () => {
  const page=harness();page.evaluate("state.project={id:'session',interfaces_modified:true};state.contract={operations:{},issues:[]};renderContract()");
  assert.match(page.element('contract-preview').innerHTML,/id="add-interface"/);
  assert.match(page.element('contract-preview').innerHTML,/接口管理/);
  assert.match(page.element('contract-preview').innerHTML,/历史报告保留/);
});

test('interface form preserves explicit JSON examples and omits unknown expectations', () => {
  const page=harness();
  page.element('interface-name').value='新增用户';page.element('interface-method').value='POST';page.element('interface-path').value='/users';
  page.element('interface-request').value='{}';
  const value=JSON.parse(page.evaluate('JSON.stringify(readInterfaceForm())'));
  assert.deepEqual(value.request_example,{});
  assert.equal('response_status' in value,false);
  assert.equal('response_example' in value,false);
  page.element('interface-parameters').value='[{bad}]';
  assert.throws(()=>page.evaluate('readInterfaceForm()'),/参数不是有效的 JSON/);
});

test('Codex handoff names the current document after interface edits', () => {
  const page=harness();page.evaluate("state.project={id:'session',title:'接口测试',filename:'original.md',effective_filename:'current-interfaces.json',task:{goal:'检查文档'}};state.contract={operations:{}};");
  assert.equal(page.evaluate('mcpSessionTarget().filename'),'current-interfaces.json');
});


test('editing an interface fills saved configuration without discarding multiple responses', () => {
  const page=harness();
  page.evaluate(`state.project={id:'session'};state.contract_revision='v1';state.contract={operations:{read:{id:'read',method:'POST',path:'/users',summary:'创建用户',parameters:[],request_schema:{type:'object'},request_example:{name:'测试'},responses:{'201':{},'401':{}},response_examples:[{ok:true}]}}};openInterfaceEditor(null,'read');`);
  assert.equal(page.element('interface-title').textContent,'编辑接口');
  assert.equal(page.element('save-interface').textContent,'保存修改');
  assert.equal(page.element('interface-name').value,'创建用户');
  assert.equal(page.element('interface-status').value,'201');
  assert.deepEqual(JSON.parse(page.element('interface-request').value),{name:'测试'});
  assert.equal(page.evaluate('interfaceEdit.editId'),'read');
  assert.equal(page.evaluate('Object.keys(state.contract.operations.read.responses).length'),2);
});


test('file upload accepts 50 MB and rejects larger files before reading', async () => {
  const page = harness();
  await page.evaluate("loadFile({size:50000000,name:'large.md',text:async()=> '# large document'})");
  assert.equal(page.element('document-content').value, '# large document');
  await assert.rejects(page.evaluate("loadFile({size:50000001,name:'too-large.md',text:async()=>{throw Error('must not read')}})"), /50 MB/);
  assert.equal(page.element('document-content').value, '# large document');
});

test('pasted content is checked using UTF-8 bytes and server limit', () => {
  const page = harness();
  page.evaluate('state.bootstrap={max_document_bytes:3}');
  page.evaluate("checkDocumentSize(new TextEncoder().encode('中').length)");
  assert.throws(()=>page.evaluate("checkDocumentSize(new TextEncoder().encode('中文').length)"), /单份文档不能超过/);
});

test('document target preview never overwrites a manual edit or another session', async () => {
  const page=harness();
  page.element('document-name').value='openapi.yaml';page.element('document-content').value='openapi: 3.0.3';
  page.evaluate(`state.targetManual=true;state.targetDraft='https://manual.example.com/v1'`);
  await page.evaluate('previewDocumentTarget()');
  assert.equal(page.element('document-base-url').value,'https://manual.example.com/v1');
  page.evaluate(`state.targetManual=false;pending=previewDocumentTarget();resetTargetDraft({task:{base_url:'https://next.example.com'}})`);
  await page.evaluate('pending');
  assert.equal(page.evaluate('state.targetDraft'),'https://next.example.com');
});

test('execution displays the saved document target instead of a second input', () => {
  const page=harness();
  page.evaluate(`state.bootstrap={environments:[]};state.project={task:{base_url:'https://api.example.com/v1'}};state.bundle={cases:[{state:'READY'}]};state.environment='custom';state.targetDraft='https://unsaved.example.com';renderExecution()`);
  const html=page.element('execution-panel').innerHTML;
  assert.ok(html.includes('https://api.example.com/v1'));
  assert.ok(!html.includes('custom-base-url'));
  assert.ok(!html.includes('environment-select'));
  assert.ok(!html.includes('测试环境'));
  assert.ok(!html.includes('https://unsaved.example.com'));
  assert.ok(html.includes('返回导入文档'));
});

test('pending actions reject duplicate clicks and clear busy state after failure', async () => {
  const page=harness();
  page.evaluate(`globalThis.actionButton={disabled:false,attrs:{},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]}};
    globalThis.calls=0;globalThis.rejectAction=null;
    globalThis.firstAction=withButtonFeedback(actionButton,()=>{calls++;return new Promise((resolve,reject)=>{rejectAction=reject})});`);
  assert.equal(page.evaluate("actionButton.attrs['aria-busy']"),'true');
  await page.evaluate('withButtonFeedback(actionButton,()=>{calls++})');
  assert.equal(page.evaluate('calls'),1);
  const first=page.evaluate('firstAction');
  page.evaluate("rejectAction(new Error('network failure'))");
  await assert.rejects(first,/network failure/);
  assert.equal(page.evaluate("actionButton.attrs['aria-busy']"),undefined);
  await page.evaluate('withButtonFeedback(actionButton,()=>{calls++})');
  assert.equal(page.evaluate('calls'),2);
});

test('feedback does not unlock a control that its running job disables', async () => {
  const page=harness();
  await page.evaluate(`globalThis.actionButton={disabled:false,setAttribute(){},removeAttribute(){}};
    withButtonFeedback(actionButton,()=>{actionButton.disabled=true})`);
  assert.equal(page.evaluate('actionButton.disabled'),true);
});

test('missing-rule help distinguishes demo, missing rules and reviewable suggestions',()=>{
  const page=harness();
  page.evaluate("state.bundle={web:{experience:true}};");
  const demo=page.evaluate("ruleHelp({id:'DEMO-NEEDS_RULE',state:'NEEDS_RULE'})");
  assert.match(demo,/不需要你补充/);
  assert.match(demo,/只创建合法的 2 条/);
  const missing=page.evaluate("ruleHelp({id:'REAL',state:'NEEDS_RULE'})");
  assert.match(missing,/怎么补/);assert.match(missing,/你不需要自己写 JSON/);
  assert.doesNotMatch(missing,/这是演示项/);
  const review=page.evaluate("ruleHelp({id:'REAL',state:'NEEDS_RULE',web:{approval_eligible:true}})");
  assert.match(review,/已有建议/);assert.match(review,/确认所选判断标准/);
  assert.equal(page.evaluate("ruleHelp({state:'READY'})"),'');
});


function navigationHarness() {
  const page=harness();
  page.evaluate(`renderNavigation=()=>{};renderCLI=()=>{};renderAPIManager=()=>{};
    renderGeneration=()=>{};renderReports=()=>{};
    state.project={id:'p'};state.contract={operations:{}};`);
  return page;
}

test('API management hides session progress through updates and restores it on return', () => {
  const page=navigationHarness();
  page.evaluate("state.job={id:'job',status:'running',logs:[{at:1,message:'working'}]};renderJob();goStage(2)");
  page.element('job-status').details.open=false;
  page.evaluate('goStage(5)');
  assert.equal(page.element('session-progress').hidden,true);
  page.evaluate("state.job.status='completed';state.job.message='任务完成';renderJob()");
  assert.equal(page.element('session-progress').hidden,true);
  assert.equal(page.evaluate('state.job.status'),'completed');
  page.evaluate('goStage(2)');
  assert.equal(page.element('session-progress').hidden,false);
  assert.match(page.element('job-status').innerHTML,/任务完成/);
  assert.equal(page.element('job-status').details.open,false);
});

test('background job completion keeps API management open', async () => {
  const page=navigationHarness();
  page.evaluate(`goStage(5);state.job={id:'job',project_id:'p',status:'running'};
    api=async()=>({id:'job',project_id:'p',status:'completed',kind:'run'});
    refreshProject=async()=>{};`);
  await page.evaluate('pollJob()');
  assert.equal(page.evaluate('state.stage'),5);
  assert.equal(page.element('session-progress').hidden,true);
});

test('a newly synced Codex report does not leave API management', async () => {
  const page=navigationHarness();
  page.evaluate(`goStage(5);state.mode='mcp';api=async path=>path==='/api/mcp/status'?{}:
    {project:{id:'p',last_analysis:{id:'report'},last_job:{id:'job',status:'completed',message:'任务完成'}}};`);
  await page.evaluate('refreshCodexProgress()');
  assert.equal(page.evaluate('state.stage'),5);
  assert.equal(page.evaluate('state.project.last_analysis.id'),'report');
  assert.equal(page.element('session-progress').hidden,true);
});

test('own cases hide AI generation, while four source choices remain available', () => {
 const page=harness();page.evaluate("state.stage=2;state.project={id:'p',case_workflow:'own'};state.contract={operations:{read:{}}};renderGeneration();renderCLI()");
 const html=page.element('generation-panel').innerHTML;
 for(const name of ['执行自己的用例','直接 AI 生成','导入后 AI 补充','AI 生成后自己补充'])assert.ok(html.includes(name));
 assert.ok(!html.includes('id="generate-button"'));assert.match(html,/导入自己的用例/);
 assert.match(page.element('cli-command').textContent,/api-test run/);
});

test('chain demo expands dependencies without making network requests', async () => {
 const page=harness();await page.evaluate("handleWorkflowClick({dataset:{wf:'chain-demo'}})");
 assert.equal(page.requests.length,0);assert.equal(page.element('chain-dialog').open,true);
 assert.equal(page.element('chain-editor').hidden,true);
 const html=page.element('chain-view').innerHTML;
 for(const text of ['/login','/items/${item_id}','token','后置清理'])assert.ok(html.includes(text));
 assert.match(page.element('chain-intro').textContent,/不发送请求/);
});

test('load opt-in and selected cases stay isolated between sessions', () => {
 const page=harness();page.evaluate("state.project={id:'a'};state.bundle={cases:[{id:'X',title:'读取',state:'READY'}]}");
 assert.equal(page.evaluate('loadDraft().enabled'),false);
 assert.equal(page.evaluate('loadDraft().case_ids.length'),0);
 page.evaluate("loadDraft().enabled=true;loadDraft().case_ids=['X'];state.project={id:'b'}");
 assert.equal(page.evaluate('loadDraft().enabled'),false);
 assert.equal(page.evaluate('loadDraft().case_ids.length'),0);
 page.evaluate("state.project={id:'a'}");assert.equal(page.evaluate('loadDraft().enabled'),true);
});

test('load-only report has a reachable same-tab report stage', () => {
 const page=harness();page.evaluate("state.project={last_load:{id:'l'},load_runs:[{report_url:'/load-report',created_at:1,requests_sent:6,requests_per_second:2,error_rate:0}]};renderReports()");
 assert.equal(page.evaluate('canEnterStage(4)'),true);
 assert.match(page.element('load-results').innerHTML,/查看压测报告/);
 assert.ok(!page.element('load-results').innerHTML.includes('_blank'));
});

test('case source actions follow workflow order and survive switching without changing cases', () => {
 const page=harness();page.evaluate("state.project={id:'p',case_workflow:'ai'};state.contract={operations:{read:{}}};state.mode='auto'");
 const render=()=>{page.evaluate('renderGeneration()');return page.element('generation-panel').innerHTML;};
 let html=render();assert.doesNotMatch(html,/data-wf="(?:import|new-case)"/);assert.match(html,/id="generate-button"/);
 page.evaluate("state.project.case_workflow='import_ai'");html=render();
 assert.match(html,/data-wf="import"/);assert.doesNotMatch(html,/data-wf="new-case"|id="generate-button"/);
 page.evaluate("state.bundle={cases:[{id:'USER',title:'自己的用例',state:'READY',web:{source:'user'}}]}");html=render();assert.match(html,/id="generate-button"/);
 page.evaluate("state.project.case_workflow='ai_import'");html=render();assert.doesNotMatch(html,/data-wf="(?:import|new-case)"/);
 page.evaluate("state.bundle.cases.push({id:'AI',title:'生成用例',state:'READY',web:{source:'ai'}})");html=render();
 assert.match(html,/data-wf="import"/);assert.match(html,/data-wf="new-case"/);
 page.evaluate("state.project.case_workflow='ai'");html=render();assert.doesNotMatch(html,/data-wf="(?:import|new-case)"/);
 assert.equal(page.evaluate('state.bundle.cases.length'),2);
 page.evaluate("state.project.case_workflow='own'");html=render();assert.match(html,/data-wf="import"/);assert.match(html,/手动添加用例/);assert.doesNotMatch(html,/id="generate-button"/);
});

test('single-step chain hides sorting while multi-step chains keep ordering controls', () => {
 const page=harness();page.evaluate("chainDemo=false;chainDraft={steps:[{id:'one',request:{method:'POST',path:'/reg'}}]};renderChain()");
 assert.doesNotMatch(page.element('chain-view').innerHTML,/data-wf="move-step"/);
 page.evaluate("chainDraft.steps.push({id:'two',request:{method:'POST',path:'/login'}});renderChain()");
 assert.match(page.element('chain-view').innerHTML,/data-wf="move-step"/);
});

test('preview reports semantic changes, expands affected steps, and does not save or execute', async () => {
 const page=harness();page.evaluate("chainDemo=false;chainDraft={title:'用例',steps:[{id:'one',request:{method:'POST',path:'/reg',json:{name:'old'}}}]};renderChain()");
 await page.evaluate("handleWorkflowClick({dataset:{wf:'preview-chain'}})");
 assert.match(page.element('chain-preview-status').innerHTML,/没有修改/);
 page.evaluate("$('chain-json').value=JSON.stringify({steps:chainDraft.steps,title:'用例'})");
 await page.evaluate("handleWorkflowClick({dataset:{wf:'preview-chain'}})");
 assert.match(page.element('chain-preview-status').innerHTML,/没有修改/);
 page.evaluate("const draft=JSON.parse($('chain-json').value);draft.steps[0].request.json.name='new';draft.notes='新增备注';$('chain-json').value=JSON.stringify(draft)");
 await page.evaluate("handleWorkflowClick({dataset:{wf:'preview-chain'}})");
 const message=page.element('chain-preview-status').innerHTML;
 for(const text of ['预览已更新','步骤 → 1 → 请求 → 请求体 → name','old','new','备注','新增备注'])assert.ok(message.includes(text));
 assert.match(page.element('chain-view').innerHTML,/chain-changed/);assert.match(page.element('chain-view').innerHTML,/<details open>/);
 assert.equal(page.requests.length,0);
 await page.evaluate("handleWorkflowClick({dataset:{wf:'preview-chain'}})");assert.match(page.element('chain-preview-status').innerHTML,/没有修改/);
});

test('invalid preview preserves the last good draft and shows an actionable error', async () => {
 const page=harness();page.evaluate("chainDraft={steps:[{id:'one',request:{path:'/reg'}}]};renderChain()");
 const original=page.element('chain-view').innerHTML;
 for(const value of ['{','null','{"steps":{}}','{"steps":[{"extract":{}}]}']){
  page.element('chain-json').value=value;await page.evaluate("handleWorkflowClick({dataset:{wf:'preview-chain'}})");
  assert.match(page.element('chain-error').textContent,/预览失败/);assert.equal(page.element('chain-view').innerHTML,original);
  assert.equal(page.evaluate('chainDraft.steps[0].request.path'),'/reg');
 }
 assert.equal(page.requests.length,0);
});

test('manual form starts with explicit choices and compiles typed parameters and expectations', () => {
 const page=harness();
 page.evaluate(`state.contract={operations:{reg:{method:'POST',path:'/reg'}}};
  var input={operation:'',title:'',path:'/reg',bodyMode:'json',body:[{key:'username',value:'alice',type:'string'}],params:[],headers:[],expected:[],status:'',notes:'',cleanup:'environment',cleanupReason:''};`);
 assert.throws(()=>page.evaluate('manualCandidate(input,state.contract)'),/选择.*接口/);
 page.evaluate("input.operation='reg'");assert.throws(()=>page.evaluate('manualCandidate(input,state.contract)'),/用例名称/);
 page.evaluate("input.title='重复用户名注册失败'");assert.throws(()=>page.evaluate('manualCandidate(input,state.contract)'),/至少填写一个预期/);
 page.evaluate("input.status='409';input.expected=[{key:'success',type:'boolean',value:'false'},{key:'/data/id',type:'exists',value:''}]");
 const candidate=JSON.parse(page.evaluate('JSON.stringify(manualCandidate(input,state.contract))'));
 assert.equal(candidate.steps[0].title,'重复用户名注册失败');assert.deepEqual(candidate.steps[0].request.json,{username:'alice'});
 assert.deepEqual(candidate.steps[0].assertions,[{kind:'status',expected:409},{kind:'json_equal',pointer:'/success',expected:false},{kind:'json_exists',pointer:'/data/id'}]);
 assert.equal(page.requests.length,0);
 page.evaluate("input.bodyMode='form'");const form=JSON.parse(page.evaluate('JSON.stringify(manualCandidate(input,state.contract))'));
 assert.equal(form.steps[0].request.raw_body,'username=alice');assert.equal(form.steps[0].request.headers['Content-Type'],'application/x-www-form-urlencoded');
 page.evaluate("input.cleanup='none'");assert.throws(()=>page.evaluate('manualCandidate(input,state.contract)'),/说明/);
});

test('duplicate reason and blockers render once while distinct reasons remain visible', () => {
 const page=harness();const html=page.evaluate("caseReasons({reason:'缺少预期；缺少清理',web:{blockers:['缺少预期','缺少清理','参数无效']}})");
 assert.equal(html.match(/缺少预期/g).length,1);assert.equal(html.match(/缺少清理/g).length,1);assert.match(html,/参数无效/);
});

test('load testing opens independently and uses saved Codex cases without entering execution stage', () => {
 const page=harness();page.evaluate(`state.bootstrap.environments=[];state.project={id:'p',title:'Codex 会话',task:{base_url:'https://example.test'}};state.bootstrap.projects=[state.project];state.mode='mcp';state.bundle={cases:[{id:'A',title:'查询',state:'READY'}]};goStage(6)`);
 assert.equal(page.evaluate('state.stage'),6);assert.equal(page.element('workflow-content').hidden,true);assert.equal(page.element('session-progress').hidden,true);assert.equal(page.element('load-management').hidden,false);
 const html=page.element('load-management').innerHTML;assert.match(html,/Codex 会话/);assert.match(html,/查询/);assert.match(html,/load-enabled/);assert.equal(page.requests.length,0);
 assert.equal(page.evaluate('loadDraft().enabled'),false);
});

test('Codex report synchronization and load job completion preserve the independent load page', async () => {
 const page=navigationHarness();page.evaluate(`state.bootstrap.environments=[];state.project={id:'p',task:{base_url:'https://example.test'}};state.bundle={cases:[]};state.mode='mcp';goStage(6);api=async path=>path==='/api/mcp/status'?{}:{project:{id:'p',last_analysis:{id:'new-report'}},bundle:{cases:[]},bundle_revision:'new'};`);
 await page.evaluate('refreshCodexProgress()');assert.equal(page.evaluate('state.stage'),6);
 page.evaluate(`state.job={id:'load',project_id:'p',kind:'load',status:'running'};api=async()=>({...state.job,status:'completed'});refreshProject=async()=>{};`);
 await page.evaluate('pollJob()');assert.equal(page.evaluate('state.stage'),6);assert.match(page.element('load-management').innerHTML,/压测已结束/);
});

test('JMeter controls use node capability and expose engine artifacts without launching a task',()=>{
 const page=harness();page.evaluate(`state.bootstrap.jmeter={available:true,max_virtual_users:10000};state.bootstrap.environments=[];state.project={id:'p',task:{base_url:'https://example.test'},load_runs:[{id:'r',engine:'jmeter',engine_status:'completed',created_at:'2026-09-14',requests_sent:192,requests_per_second:50,error_rate:0,report_url:'/report'}]};state.bundle={cases:[{id:'A',title:'查询',state:'READY'}]};goStage(6);`);
 assert.equal(page.evaluate('loadDraft().engine'),'jmeter');assert.equal(page.evaluate('loadDraft().enabled'),false);
 assert.match(page.element('load-management').innerHTML,/load-ramp/);assert.match(page.element('load-management').innerHTML,/max="10000"/);
 assert.match(page.element('load-workspace-results').innerHTML,/jmeter-artifacts\/r\/plan.zip/);
 assert.equal(page.requests.length,0);
});


test('legacy generation modes return to AI choices without regenerating saved cases', () => {
 const page=harness();
 page.evaluate("state.project={id:'legacy',generation_mode:'baseline',template:'gomoku'};state.contract={operations:{read:{}}};state.bundle={cases:[]}");
 for(const mode of ['baseline','auto',undefined]){
  page.evaluate(`state.mode=${JSON.stringify(mode)};renderGeneration();state.stage=2;renderCLI()`);
  assert.equal(page.evaluate('state.mode'),'mcp');
  const html=page.element('generation-panel').innerHTML;
  assert.doesNotMatch(html,/内置示例方案|按文档规则生成|data-mode="(?:auto|baseline)"|业务链路示例/);
  assert.match(html,/data-mode="mcp"/);assert.match(html,/data-mode="model"/);
  assert.match(page.element('cli-command').textContent,/Codex/);
  assert.equal(page.evaluate('state.project.generation_mode'),'baseline');
  assert.equal(page.requests.length,0);
 }
 page.evaluate("state.mode='model';renderGeneration();renderCLI()");
 assert.equal(page.evaluate('state.mode'),'model');
 assert.match(page.element('cli-command').textContent,/--mode model/);
 const index=readFileSync(new URL('../../api_test_tool/static/index.html',import.meta.url),'utf8');
 assert.doesNotMatch(index,/start-demo|data-template|体验完整流程/);
});


test('UI uses shared steps without requiring an HTTP bundle; imported results skip execution', () => {
  const page=harness(false, '/ui-testing');
  page.evaluate('UIWorkflow.renderDocument()');
  assert.match(page.element('ui-document-panel').innerHTML, /name="execution_permission"/);
  assert.match(page.element('ui-document-panel').innerHTML, /id="target-url" type="url" required/);
  assert.doesNotMatch(page.element('ui-document-panel').innerHTML, /可稍后补充/);
  assert.match(page.element('ui-document-panel').innerHTML, /value="maximum"/);
  assert.equal(page.evaluate('canEnterStage(3)'), false);
  page.evaluate("state.project={test_kind:'ui',id:'ui-1',filename:'ui-test.md',ui_target_url:'https://example.test/login',ui_execution_permission:{key:'maximum',label:'最大权限',description:'允许全部目标系统操作'},task:{goal:'测试登录'}}");
  assert.equal(page.evaluate('canEnterStage(3)'), true);
  const message=page.evaluate("mcpMessage(mcpSessionTarget(),'test-code')");
  assert.match(message, /web-exploratory-testing/);
  assert.match(message, /https:\/\/example.test\/login/);
  assert.match(message, /免安装 Python 客户端/);
  assert.match(message, /归属明确的合成对象/);
  assert.match(message, /最大权限（maximum）/);
  assert.match(message, /不得再次要求逐项确认/);
  assert.match(message, /内存字节/);
  assert.doesNotMatch(message, /接口测试 Skill/);
  page.evaluate("state.project.ui_import_filename='results.xlsx';state.project.last_analysis={report_url:'/report'}");
  assert.equal(page.evaluate('canEnterStage(3)'), false);
  assert.equal(page.evaluate('canEnterStage(4)'), true);
  page.evaluate('renderGeneration()');
  assert.match(page.element('generation-panel').innerHTML, /已导入测试结果/);
  assert.doesNotMatch(page.element('generation-panel').innerHTML, /id="ui-handoff"/);
  assert.match(page.element('generation-panel').innerHTML, /data-ui-regression/);
  assert.match(page.element('generation-panel').innerHTML, /class="primary" data-stage="4"/);
  assert.match(page.element('generation-panel').innerHTML, /class="panel-footer"/);
  assert.match(page.element('generation-panel').innerHTML, /回归测试/);
  assert.match(uiWorkflowSource, /复用当前会话和用例/);
  assert.doesNotMatch(uiWorkflowSource, /保留原报告，另建回归会话/);
  page.evaluate("state.bootstrap.projects=workspaceProjects([{id:'source',test_kind:'ui'},{id:'legacy',test_kind:'ui',regression_source:{project_id:'source'}}])");
  assert.equal(page.evaluate('state.bootstrap.projects.map(project=>project.id).join()'), 'source');
});

test('UI report history uses common renderer without API execution claims or raw JSON links', () => {
  const page=harness(false, '/ui-testing');
  page.evaluate("state.project={test_kind:'ui',analysis_reports:[{title:'旧报告',report_url:'/old'}]};renderTaskReport({title:'UI 回归',kind:'analysis',report_url:'/api/projects/p/reports/r/index.html'})");
  const html=page.element('report-panel').innerHTML;
  assert.match(html, /UI 测试结果/);
  assert.match(html, /旧报告/);
  assert.match(html, /data-wecom-path="\/api\/projects\/p\/reports\/r\/wecom"/);
  assert.match(html, /推送到企微/);
  assert.doesNotMatch(html, /结论、发现和执行证据/);
  assert.doesNotMatch(html, /文档分析结果|report.json/);
});

test('session mutation responses remain filtered to the current test workspace', () => {
  for(const pathname of ['/api-testing','/ui-testing']) {
    const page=harness(false, pathname);
    const ids=page.evaluate("workspaceProjects([{id:'api'},{id:'ui',test_kind:'ui'}]).map(p=>p.id).join(',')");
    assert.equal(ids, pathname==='/ui-testing'?'ui':'api');
  }
});


test('UI session header reopens its task message without restarting a queued round', async () => {
  const page=harness(true,'/ui-testing');
  page.evaluate("state.stage=2;state.mode='mcp';state.project={id:'pending-session',title:'五模块',filename:'requirements.md',test_kind:'ui',ui_target_url:'https://target.test',task:{goal:'测试五个模块'}}");
  await page.evaluate("handleClick({target:{closest:()=>document.getElementById('workspace-connection')}})");
  assert.equal(page.element('mcp-title').textContent,'把测试任务发给 Codex');
  assert.match(page.element('mcp-prompt').value,/pending-session/);
  assert.match(page.element('mcp-prompt').value,/测试五个模块/);
  assert.deepEqual(page.requests.map(x=>x.path),['/api/mcp/status','/api/mcp/pair']);
});
