const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {summarize,durationInfo,experimentInfo,createExperimentCallout,sections,serialize,recordGroup,lifecycleLabels,lifecycleDescriptions,caseAction,cleanActual,fixturePurpose,createAnalysisCallout,displayTitle}=require('../../api_test_tool/static/report-review.js');

test('fixture purpose follows its own case instead of stale upload notes',()=>{
 const cases=[{case_id:'A',scenario:'空文件处理'},{case_id:'B',scenario:'32 MiB 上传边界'}];
 const asset={case_id:'B',step:'实体文件超过平台10MB夹具上限',size:2301};
 assert.equal(fixturePurpose(asset,cases),'用于32 MiB 上传边界');
 assert.equal(fixturePurpose({...asset,case_id:'A'},cases),'用于空文件处理');
 assert.equal(fixturePurpose({...asset,case_id:'missing'},cases),'测试输入文件');
});

test('execution duration preserves seconds and rejects missing or inverted ranges',()=>{
 assert.equal(durationInfo({startedAt:'2026-09-24T08:00:00Z',finishedAt:'2026-09-24T10:31:00Z'}).label,'2 小时 31 分钟');
 assert.equal(durationInfo({startedAt:'2026-09-24T08:00:00Z',finishedAt:'2026-09-24T08:00:20Z'}).label,'20 秒');
 assert.equal(durationInfo({startedAt:'',finishedAt:'2026-09-24T10:31:00Z'}),null);
 assert.equal(durationInfo({startedAt:'2026-09-24T10:31:00Z',finishedAt:'2026-09-24T08:00:00Z'}),null);
});

test('rejected defects show their persisted reason in list and details',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.js'),'utf8');
 assert.match(source,/class="rr-row-reason" hidden/);
 assert.match(source,/拒绝原因：.*record\?\.triage_reason/);
 assert.match(source,/id="rr-decision-reason"/);
 assert.match(source,/selectedRecord\?\.triage_reason/);
});

test('blocked cases do not inflate executed progress',()=>{
 const cases=[...Array(7).fill({status:'passed'}),...Array(2).fill({status:'failed'}),...Array(110).fill({status:'blocked'})];
 assert.deepEqual(summarize(cases),{total:119,passed:7,failed:2,blocked:110,executed:9});
 assert.equal(summarize([{status:'PASS'},{status:'BROKEN'},{status:'QUARANTINED'},{status:'UNSUPPORTED'}]).executed,2);
});
test('imported UI statuses remain distinct in summary and case filters',()=>{
 const statuses=['passed','failed','partial','blocked','not_run','pending_rule','pending_action','skipped','other'];
 const cases=statuses.map((status,index)=>({case_id:`SYNTHETIC-${index}`,scenario:'合成存储记录',status}));
 assert.deepEqual(summarize(cases),{total:9,...Object.fromEntries(statuses.map(status=>[status,1])),executed:3});
 const source=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.js'),'utf8');
 const statusCode=source.slice(source.indexOf('const statusKey='),source.indexOf('function displayTitle('));
 const filterCode=source.slice(source.indexOf('function filteredCases(){'),source.indexOf('function renderCases('));
 const search={value:''},filter={value:'all'};
 const context=vm.createContext({cases,root:{},$:id=>id==='rr-case-search'?search:filter});
 vm.runInContext(statusCode+filterCode,context);
 assert.equal(context.filteredCases().length,9);
 for(const status of statuses){
  filter.value=status;
  assert.deepEqual(Array.from(context.filteredCases(),c=>c.status),[status]);
 }
});
test('actionable cases remain unexecuted and expose only structured actions',()=>{
 const action={status:'pending_action',required_action:{type:'authorization',prompt:'确认删除共享记录'}};
 assert.deepEqual(summarize([action]),{total:1,pending_action:1,executed:0});
 assert.deepEqual(caseAction(action),action.required_action);
 assert.equal(caseAction({status:'blocked',actual:'请用户确认'}),null);
});
test('section editor preserves API evidence and multiline reproduction details',()=>{
 const source='【测试步骤】\n1. 登录\n2. 重新加载\n\n【实际结果】\n连接断开\n\n【代码依据】\nmain.py:25\n原始证据 <response>';
 assert.equal(serialize(sections(source)),source);
 assert.deepEqual(sections('无结构的原始证据'),[{name:'问题描述',value:'无结构的原始证据'}]);
});
test('uncertain and partial submissions stay out of the pending queue',()=>{
 for(const status of ['loading','unavailable','pending','unknown'])assert.equal(recordGroup({status}),'check');
 assert.equal(recordGroup({status:'submitted',screenshot_error:'upload failed'}),'check');
 assert.equal(recordGroup({status:'submitted'}),'submitted');
 assert.equal(recordGroup({status:'failed'}),'pending_submission');
 assert.equal(recordGroup(null),'pending_submission');
 assert.equal(recordGroup({status:'draft',triage_status:'rejected'}),'rejected');
 assert.equal(recordGroup({status:'submitted',triage_status:'pending_regression'}),'pending_regression');
});
test('every selectable defect status has a human-readable regression explanation',()=>{
 assert.deepEqual(Object.keys(lifecycleDescriptions).sort(),Object.keys(lifecycleLabels).sort());
 assert.match(lifecycleDescriptions.rejected,/理由.*AI|AI.*理由/);
 assert.match(lifecycleDescriptions.pending_regression,/优先回归/);
});
test('report exposes contextual batch actions with one frozen confirmation and persistent results',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.js'),'utf8');
 assert.ok(source.indexOf('id="rr-search"')<source.indexOf('id="rr-filter"'));
 assert.match(source,/bridge\.batchPlan\(ids,action\)/);
 assert.match(source,/bridge\.runBatch\(ids,action,reason/);
 assert.match(source,/resultDetails\.id='rr-batch-results'/);
 assert.match(source,/root\.ReportSelects\?\.upgrade\(actions\)/);
 assert.match(source,/bridge\?\.setSelectionScope/);
});

test('defect status filter uses a custom menu anchored directly below its trigger',()=>{
 const css=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.css'),'utf8');
 assert.match(css,/\.rr-status-filter\{position:relative;width:166px/);
 assert.match(css,/\.rr-status-filter-menu\{position:absolute;[^}]*top:calc\(100% \+ 6px\);left:0;width:100%/);
 assert.match(css,/\.rr-inbox\{overflow:visible\}/);
});

test('single defect editor hides lifecycle controls on report pages',()=>{
 const css=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.css'),'utf8');
 assert.match(css,/\.pc-dialog\.pc-docked \.pc-lifecycle\{display:none\}/);
});
test('submitted defect descriptions wrap within the review pane',()=>{
 const css=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.css'),'utf8');
 assert.match(css,/\.pc-record pre\{[^}]*max-width:100%;white-space:pre-wrap;overflow-wrap:anywhere\}/);
});
test('summary counters open the matching case results without changing their visual layout',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.js'),'utf8');
 const css=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.css'),'utf8');
 assert.match(source,/<button type="button" class="rr-stat \$\{color\}" data-rr-stat="\$\{key\}"/);
 assert.match(source,/\$\('rr-case-filter'\)\.value=button\.dataset\.rrStat==='total'\?'all':button\.dataset\.rrStat/);
 assert.match(source,/page=0;tab\('cases'\);\$\('rr-cases'\)\.scrollIntoView/);
 assert.match(css,/button\.rr-stat\{[^}]*min-height:0;[^}]*background:transparent/);
});
test('case corrections expose explicit not-passed status and keep select content on one row',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.js'),'utf8');
 const css=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.css'),'utf8');
 assert.match(source,/failed:'不通过'/);
 assert.match(source,/correctionStatuses=\['passed','failed','partial'/);
 assert.doesNotMatch(source,/修正报告|reportCorrectionBase|rr-report-edit-dialog/);
 assert.match(css,/#rr-case-edit-form select\{appearance:none;display:block;height:44px/);
 assert.match(css,/background:#f8f9fc url\("data:image\/svg\+xml/);
});
test('actual result hides screenshot and defect coordination metadata',()=>{
 assert.equal(cleanActual('观察到错误，复现2/2。现场截图已关联。缺陷标题：[prod]【B端】【模块】问题'),'观察到错误，复现2/2。');
 assert.equal(cleanActual('现场复现1/1并已先截图。影响：按钮仍可点击。'),'现场复现1/1。影响：按钮仍可点击。');
 assert.equal(cleanActual('截图显示错误提示内容发生变化。'),'截图显示错误提示内容发生变化。');
});
test('case detail presents only saved AI explanation in a compact callout',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.js'),'utf8');
 const css=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.css'),'utf8');
 assert.match(source,/c\.ai_analysis&&!c\.wording_corrected_at/);
 assert.match(source,/class="rr-case-analysis" aria-label="AI 解读"/);
 assert.match(source,/esc\(c\.ai_analysis\)/);
 assert.match(css,/\.rr-case-analysis\{[^}]*overflow-wrap:anywhere/);
});

const analysisDocument=()=>({createElement:tag=>({tag,children:[],attributes:{},
 setAttribute(name,value){this.attributes[name]=value},append(...children){this.children.push(...children)}})});

test('executor timing ends at execution completion rather than a later publication',()=>{
 const experiment={experiment_id:'synthetic',variant:'A',model:'example-model',reasoning_effort:'example-effort',model_source:'requested',
  started_at:'2026-10-11T16:00:00+08:00',execution_started_at:'2026-10-11T08:01:00Z',execution_finished_at:'2026-10-11T08:02:00Z',tool_errors:0};
 const info=experimentInfo(experiment,'2026-10-12T08:00:00Z');
 const values=Object.fromEntries(info.rows.map(row=>[row.label,row.value]));
 assert.equal(values['准备及执行窗口'],'2 分 0 秒');
 assert.equal(values['准备窗口'],'1 分 0 秒');
 assert.equal(values['执行窗口'],'1 分 0 秒');
 assert.equal(values['模型与强度'],'example-model / example-effort · 任务指定');
 assert.equal(values['工具异常'],'0');
 assert.equal(values['工具调用'],undefined);
 assert.equal(values['含准备总历时（至报告发布）'],undefined);
});

test('missing experiment values are not inferred from a model name, count or publication',()=>{
 assert.equal(experimentInfo(undefined,'2026-10-11T08:00:00Z'),null);
 assert.equal(experimentInfo({},'2026-10-11T08:00:00Z'),null);
 assert.deepEqual(experimentInfo({model:'example-model'},'2026-10-11T08:00:00Z').rows,
  [{label:'模型与强度',value:'example-model · 来源未记录'}]);
 const info=experimentInfo({started_at:'2026-10-11T08:00:00Z',tool_calls:null},'2026-10-11T08:00:03Z');
 assert.deepEqual(info.rows,[]);
 assert.ok(info.details.includes('执行结束时间未记录，不能用报告发布时间代替。'));
 assert.deepEqual(experimentInfo({execution_started_at:'2026-10-11T08:03:00Z',execution_finished_at:'2026-10-11T08:02:00Z'},'').rows,[]);
});

test('experiment labels and provenance render as read-only text, including markup',()=>{
 const text='<img src=x onerror=alert(1)>',doc=analysisDocument();
 const section=createExperimentCallout(doc,{variant:text,model_source:'verified',model_source_detail:text},'');
 assert.equal(section.attributes['aria-label'],'本阶段实验记录');
 assert.equal(section.children[2].children[0].children[1].textContent,text);
 assert.equal(section.children[2].children[1].children[1].textContent,'执行端标记已核实');
 assert.equal(section.children[3].children[1].children[0].textContent,'模型来源说明：'+text);
 const visit=node=>{assert.equal(node.innerHTML,undefined);for(const child of node.children||[])visit(child)};
 visit(section);
 assert.equal(createExperimentCallout(doc,{},''),null);
});

test('defect AI interpretation uses the saved explanation as safe, read-only text',()=>{
 const text='文件保存了，但解析失败，因此不能用来回答问题。<img src=x onerror=alert(1)>';
 const section=createAnalysisCallout(analysisDocument(),{ai_analysis:text});
 assert.equal(section.attributes['aria-label'],'AI 解读');
 assert.equal(section.children[0].textContent,'AI 解读');
 assert.equal(section.children[1].tag,'p');
 assert.equal(section.children[1].textContent,text);
 assert.equal(section.innerHTML,undefined);
 assert.equal(section.children[1].innerHTML,undefined);
});

test('missing or stale AI interpretation is not invented or displayed',()=>{
 for(const caseItem of [null,{}, {ai_analysis:'  '}, {ai_analysis:'旧结果',wording_corrected_at:'2026-10-08'}]){
  assert.equal(createAnalysisCallout(analysisDocument(),caseItem),null);
 }
});

test('switching defects updates the matching interpretation and clears missing or corrected ones',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.js'),'utf8');
 const render=source.slice(source.indexOf('function showDefectAnalysis(entry){'),source.indexOf('function select(id,reveal=true){'));
 const doc=analysisDocument(),dock={children:[],prepend(node){this.children.unshift(node);node.remove=()=>{this.children=this.children.filter(child=>child!==node)}}};
 const cases=[{case_id:'PDF',ai_analysis:'PDF解析失败，不能检索。'},
  {case_id:'HISTORY',ai_analysis:'删除失败，历史仍保留。'}, {case_id:'EMPTY'},
  {case_id:'CORRECTED',ai_analysis:'旧结果',wording_corrected_at:'2026-10-08'}];
 const context=vm.createContext({document:doc,cases,createAnalysisCallout,
  $:id=>id==='rr-review-dock'?dock:dock.children.find(child=>child.id===id)});
 vm.runInContext(render,context);
 const select=id=>context.showDefectAnalysis({article:{dataset:{caseId:id}}});
 select('PDF');assert.equal(dock.children[0].children[1].textContent,cases[0].ai_analysis);
 select('HISTORY');assert.equal(dock.children.length,1);assert.equal(dock.children[0].children[1].textContent,cases[1].ai_analysis);
 select('EMPTY');assert.equal(dock.children.length,0);
 select('PDF');select('CORRECTED');assert.equal(dock.children.length,0);
 select('PDF');select('UNKNOWN');assert.equal(dock.children.length,0);
});


test('inline screenshot attachments remove only the matching duplicate evidence',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/report-review.js'),'utf8');
 const render=source.slice(source.indexOf('function showEvidence(entry){'),source.indexOf('function renderData(){'));
 const create=()=>({children:[],append(...items){this.children.push(...items)},querySelector(){return null}});
 const dock=create();let inline=['one'];
 const media=(id,type='image')=>({dataset:{imageSrc:type==='image'?`asset-${id}`:''},
  classList:{contains(){return false}},getAttribute(){return ''},
  matches(selector){return type==='image'?selector.includes('.report-image-preview'):selector.includes('details')},cloneNode(){return {id}}});
 const entry={article:{dataset:{caseId:'CASE'},children:[media('one'),media('two'),media('recording','video')]}};
 const context=vm.createContext({document:{createElement:create},$:id=>id==='rr-review-dock'?dock:null,
  data:{},cases:[],bridge:{screenshotAssets:()=>inline},assets:[{kind:'screenshot',case_id:'CASE'}],fixtures:[]});
 vm.runInContext(render,context);
 context.showEvidence(entry);
 assert.deepEqual(dock.children[0].children[0].children.map(node=>node.id),['two','recording']);
 inline=[];context.showEvidence(entry);
 assert.deepEqual(dock.children[1].children[0].children.map(node=>node.id),['one','two','recording']);
});


test('environment brackets update old titles without treating their prefix as a section',()=>{
 const title='【prod】【B端】【企业知识库】 PDF解析失败 [32MB]';
 assert.equal(displayTitle('[prod]【B端】【企业知识库】 PDF解析失败 [32MB]'),title);
 assert.equal(displayTitle(title),title);
 assert.equal(displayTitle('[GET] /api/files'), '[GET] /api/files');
 const parts=[{name:'标题',value:title},{name:'测试步骤',value:'1.上传资料'},{name:'实际结果',value:'解析失败'}];
 assert.deepEqual(sections(serialize(parts)),parts);
});


test('title attribute editing accepts old and new brackets and writes the canonical format',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/pingcode.js'),'utf8');
 const render=source.slice(source.indexOf('function titleAttributes(input, enabled){'),source.indexOf('function renderRecord(record){'));
 for(const prefix of ['[prod]','【prod】']){
  let box;
  const node=()=>({children:[],listeners:{},append(...items){this.children.push(...items)},setAttribute(){},
   addEventListener(name,callback){this.listeners[name]=callback}});
  const input={value:prefix+'【B端】【企业知识库】 解析失败 [32MB]',parentElement:{after(value){box=value}},dispatchEvent(){}};
  const context=vm.createContext({document:{createElement:node},Event:class{}});
  vm.runInContext(render,context);context.titleAttributes(input,true);
  const fields=box.children.map(label=>label.children[0]);
  assert.deepEqual(fields.map(field=>field.value),['prod','B端','企业知识库']);
  fields[0].value='test';fields[0].listeners.change();
  assert.equal(input.value,'【test】【B端】【企业知识库】 解析失败 [32MB]');
 }
});
