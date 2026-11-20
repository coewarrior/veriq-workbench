const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

test('report review omits duplicate submitted screenshot links but keeps them on legacy reports',()=>{
 const source=fs.readFileSync(require.resolve('../../api_test_tool/static/pingcode.js'),'utf8');
 const render=source.slice(source.indexOf('function renderRecord(record){'),source.indexOf('async function loadProjects(){'));
 const makeNode=()=>({children:[],append(...nodes){this.children.push(...nodes)},replaceChildren(...nodes){this.children=nodes}});
 for(const [pageId,expectedLinks] of [['report-review-page',0],['legacy-report-page',1]]){
  const recordNode=makeNode(),form=makeNode();
  const context={window:{},document:{body:{id:pageId},createElement:()=>makeNode(),createTextNode:text=>({text})},
   $:id=>id==='pc-record'?recordNode:form,
   renderLifecycle(){},updateRecord(){},contentWarning:()=>'',
   triage:{canSubmit:()=>false},edits:new Map(),currentButton:{dataset:{draft:'defect-1'}},currentDraft:null};
  vm.runInNewContext(`${render};renderRecord({status:'submitted',screenshots:[{url:'https://example.test/screenshot.png',title:'截图-1.jpg'}]})`,context);
  assert.equal(recordNode.children.filter(child=>child.className==='pc-screenshot-list').length,expectedLinks);
 }
});

test('merged cards keep original draft routes and independent submission histories',async()=>{
 const elements=new Map(), requests=[];
 const node=()=>({dataset:{},disabled:false,checked:false,textContent:'',append(){},prepend(){},after(){},closest(){return null},setAttribute(){},classList:{toggle(){}}});
 for(const id of ['pc-select-all','pc-batch-count','pc-batch-start'])elements.set(id,node());
 const copies=['defect-1','defect-2','finding-0'].map((id,index)=>{
  const element=node();element.closest=selector=>index===2?null:{dataset:{pingcodeReport:index===0?'aaaa':'bbbb',pingcodeDraft:'defect-1'}};
  elements.set(id,element);
  const copy=node();copy.dataset.draft=id;copy.after=button=>element.button=button;copy.before=()=>{};return copy;
 });
 const context=vm.createContext({setTimeout(){},clearTimeout(){},window:{addEventListener(){},PingCodeTriage:require('../../api_test_tool/static/pingcode-triage.js')},
  location:{pathname:'/api/projects/cccc/reports/dddd/index.html'},
  document:{addEventListener(){},getElementById:id=>elements.get(id),querySelectorAll:()=>copies,createElement:node,
   querySelector:selector=>selector==='meta[name="api-test-public-report"]'?null:node()},
  fetch:async url=>{requests.push(url);const values=url.includes('/aaaa/')?[{draft_id:'defect-1',status:'submitted',item:{identifier:'OLD-1'}}]:url.includes('/bbbb/')?[{draft_id:'defect-1',status:'unknown'}]:[];
   return{ok:true,json:async()=>url==='/api/bootstrap'?{csrf:'local-test'}:{values}};}
 });
 const source=fs.readFileSync(require.resolve('../../api_test_tool/static/pingcode.js'),'utf8');
 vm.runInContext(source.replace(/\}\)\(\);\s*$/, 'globalThis.draftRouteForTest=draftRoute;})();'),context);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(context.draftRouteForTest('defect-1'),'/api/projects/cccc/reports/aaaa/pingcode/defect-1');
 assert.equal(context.draftRouteForTest('defect-2'),'/api/projects/cccc/reports/bbbb/pingcode/defect-1');
 assert.equal(context.draftRouteForTest('finding-0'),'/api/projects/cccc/reports/dddd/pingcode/finding-0');
 assert.equal(elements.get('defect-1').button.textContent,'已提交 · OLD-1');
 assert.equal(elements.get('defect-2').button.textContent,'提交待核对');
 assert.ok(requests.includes('/api/projects/cccc/reports/aaaa/pingcode'));
 assert.ok(requests.includes('/api/projects/cccc/reports/bbbb/pingcode'));
});

test('signed-out shared reports show login-first PingCode controls without calling private APIs',async()=>{
 const added=[], prepended=[];
 const copy={dataset:{draft:'defect-1'},after(button){added.push(button)},before(){}};
 const node=()=>({append(...children){this.children=children},prepend(){},setAttribute(){}});
 const context=vm.createContext({setTimeout(){},clearTimeout(){},window:{addEventListener(){},PingCodeTriage:require('../../api_test_tool/static/pingcode-triage.js')},
  location:{pathname:'/api/projects/cccc/reports/dddd/index.html',search:'',hash:'',href:''},
  document:{addEventListener(){},getElementById:()=>undefined,querySelectorAll:()=>[copy],createElement:node,
   querySelector:selector=>selector==='meta[name="api-test-public-report"]'?{content:'login-required'}:{prepend(value){prepended.push(value)}},
   body:{prepend(value){prepended.push(value)}}},
  fetch:async()=>{throw new Error('signed-out report must not call private PingCode APIs')}
 });
 const source=fs.readFileSync(require.resolve('../../api_test_tool/static/pingcode.js'),'utf8');
 vm.runInContext(source,context);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(added.length,1);
 assert.equal(added[0].textContent,'登录后提交到 PingCode');
 added[0].onclick();
 assert.equal(context.location.href,'/login?next=%2Fapi%2Fprojects%2Fcccc%2Freports%2Fdddd%2Findex.html');
 assert.equal(prepended.length,1);
 assert.equal(prepended[0].children[1].textContent,'登录后批量提缺陷');
});

test('read-only report surfaces explain that submission is unavailable',async()=>{
 const added=[];
 const copy={after(button){added.push(button)}};
 const node=()=>({append(){},prepend(){},setAttribute(){}});
 const context=vm.createContext({setTimeout(){},clearTimeout(){},window:{addEventListener(){},PingCodeTriage:require('../../api_test_tool/static/pingcode-triage.js')},
  location:{pathname:'/api/projects/cccc/reports/dddd/index.html',search:'',hash:'',href:''},
  document:{addEventListener(){},getElementById:()=>undefined,querySelectorAll:()=>[copy],createElement:node,
   querySelector:selector=>selector==='meta[name="api-test-public-report"]'?{content:'read-only'}:node(),body:node()},
  fetch:async()=>{throw new Error('read-only report must not call PingCode APIs')}
 });
 vm.runInContext(fs.readFileSync(require.resolve('../../api_test_tool/static/pingcode.js'),'utf8'),context);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(added[0].textContent,'此报告仅供查看');
 assert.equal(added[0].disabled,true);
});

test('batch title edits persist regression defects without submitting or changing lifecycle',async()=>{
 const source=fs.readFileSync(require.resolve('../../api_test_tool/static/pingcode.js'),'utf8');
 const code=source.slice(source.indexOf('async function editTitles('),source.indexOf('async function setLifecycles('));
 const requests=[],queued=[],edits=new Map(),fields=new Map(['finding-0','finding-1'].map(id=>[id,{value:'【标题】旧标题\n【实际结果】原始观察'}]));
 const context=vm.createContext({sending:false,rememberReview(){},settleSelection(){},publishBatch(){},edits,currentButton:null,
  enqueueBatch:async(ids,action,reason,versions,inputs)=>queued.push({ids,action,inputs}),
  draftRoute:id=>'/api/projects/p/reports/r/pingcode/'+id,draftProject:()=> 'p',draftReport:()=> 'r',draftSourceId:id=>id,
  $:id=>fields.get(id),triage:{canSubmit:()=>false,reviewDescription:field=>field.value},
  window:{ReportReview:{titlesSaved(){},update(){}}},
  call:async(url,method,body)=>{
   requests.push({url,method,body});
   if(method==='POST')return {revision:1,values:body.draft_ids.map(id=>({draft_id:id,title:'【prod】【B端】【记忆】 '+id}))};
   return {ui_title:true,correction_revision:0,title:'旧标题',record:{status:'draft',triage_status:'regression_failed'}};
  }});
 vm.runInContext(code,context);
 assert.equal(await context.editTitles(['finding-0','finding-1'],{environment:'prod',client:'',module:''}),2);
 const writes=requests.filter(request=>request.method==='POST');
 assert.equal(writes.length,0);assert.equal(queued.length,1);
 assert.equal(queued[0].action,'titles');
 assert.deepEqual(Array.from(queued[0].ids),['finding-0','finding-1']);
 assert.equal(queued[0].inputs.get('finding-0').attributes.environment,'prod');
 assert.equal(queued[0].inputs.get('finding-0').revision,0);
 assert.equal(edits.size,0);
 assert.equal(fields.get('finding-0').value,'【标题】旧标题\n【实际结果】原始观察');
});
