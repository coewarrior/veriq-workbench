const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const vm=require('node:vm');

function harness(){
  const elements=new Map(),listeners={},requests=[],messages=[],revoked=[];
  const element=id=>{
    if(!elements.has(id))elements.set(id,{id,value:'',innerHTML:'',disabled:false,hidden:false,checked:false,
      textContent:'',dataset:{},matches(){return false;},closest(){return null;},
      setAttribute(){},append(){},scrollIntoView(){},previousElementSibling:{},remove(){},classList:{toggle(){},add(){}},insertAdjacentHTML(where,html){this.inserted=html;},
      querySelector(selector){
        if(selector==='[data-scene-retention-scope]')return element(id+'-scene-scope');
        return ['pre','.panel-footer','[data-stage="3"]'].includes(selector)?element(id+selector):null;
      }});
    return elements.get(id);
  };
  const projects=new Map();
  const context=vm.createContext({
    state:{project:null,bootstrap:{projects:[]}},$:element,CodexProgress:{describe:()=>({active:false})},
    document:{body:element('body'),getElementById:id=>elements.get(id)||null,createElement:element,querySelector:element,querySelectorAll:()=>[],addEventListener(type,fn){(listeners[type]||=[]).push(fn);}},
    esc:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    URL:class extends URL{static createObjectURL(file){return 'blob:'+file.name;}static revokeObjectURL(url){revoked.push(url);}},
    FormData:class{
      get(){return 'full';}
      *[Symbol.iterator](){yield ['target_url',context.state.project.ui_target_url];yield ['goal','回归测试'];yield ['execution_permission','full'];}
    },
    FileReader:class{readAsDataURL(file){this.result='data:application/octet-stream;base64,'+Buffer.from(file.content||'requirement').toString('base64');this.onload();}},
    toast:(message,error)=>messages.push({message,error}),
    api:async(path,method,body)=>{
      requests.push({path,method,body});
      const project={...(path.endsWith('/task')?context.state.project:{}),id:'saved',
        ui_target_url:body.target_url||context.state.project?.ui_target_url,
        ui_scene_retention:{key:body.scene_retention||'none'},task:{goal:body.goal||'按资料测试'}};
      projects.set(project.id,project);
      return path.endsWith('/task')?project:{project};
    },
    loadProject:async id=>{context.state.project=projects.get(id);context.state.codexGoal=context.state.project.task.goal;vm.runInContext('UIWorkflow.renderPreparation()',context);},goStage(){},openMCP:async()=>{},scheduleMCPSync(){}
  });
  vm.runInContext(readFileSync(new URL('../../api_test_tool/static/ui-workflow.js',`file://${__filename}`),'utf8'),context);
  vm.runInContext('UIWorkflow.setup()',context);
  return {element,requests,messages,revoked,evaluate:code=>vm.runInContext(code,context),
    async emit(type,event){for(const listener of listeners[type]||[])await listener(event);},
    async choose(files){await this.emit('change',{target:{files,value:'picked',matches:s=>s==='[data-ui-attachment-input]'}});},
    async selectScene(value,formId='ui-test-form'){
      const form=element(formId),scope=element(formId+'-scene-scope');
      scope.matches=choice=>choice==='[data-scene-retention-scope]';
      scope.closest=choice=>choice==='form'||choice==='#'+formId?form:null;
      scope.value=value;
      await this.emit('change',{target:scope});
    },
    async submit(formId='ui-test-form'){await this.emit('submit',{target:element(formId),submitter:element('submit'),preventDefault(){}});}
  };
}

test('image and document requirements save without mandatory text and reset thumbnails',async()=>{
  const page=harness();
  page.element('test-title').value='多附件要求';page.element('target-url').value='https://example.test';
  await page.choose([{name:'示意图.png',size:100,content:'image'}, {name:'详细要求.pdf',size:200,content:'document'}]);
  assert.match(page.element('ui-attachment-draft').innerHTML,/blob:示意图.png/);
  assert.match(page.element('ui-attachment-draft').innerHTML,/详细要求.pdf/);
  await page.submit();
  assert.equal(page.requests.length,1);
  assert.doesNotMatch(JSON.stringify(page.requests),/\/task/);
  assert.equal(page.requests[0].path,'/api/ui-tests');
  assert.equal(page.requests[0].body.goal,'');
  assert.deepEqual(Array.from(page.requests[0].body.attachments,item=>item.filename),['示意图.png','详细要求.pdf']);
  assert.equal(Buffer.from(page.requests[0].body.attachments[1].content_base64,'base64').toString(),'document');
  assert.deepEqual(page.revoked,['blob:示意图.png']);
  assert.equal(page.element('submit').disabled,false);
});

test('paste screenshots, drag documents and remove drafts use the same validated selection',async()=>{
  const page=harness();let prevented=0;
  await page.emit('paste',{target:{id:'test-goal'},clipboardData:{files:[{name:'截图.png',size:100}]},preventDefault(){prevented++;}});
  await page.emit('drop',{target:{closest:()=>({classList:{toggle(){}}})},dataTransfer:{files:[{name:'说明.docx',size:100}]},preventDefault(){prevented++;}});
  const remove={dataset:{uiAttachmentRemove:'0'}};
  await page.emit('click',{target:{closest:selector=>selector==='[data-ui-attachment-remove]'?remove:null}});
  assert.equal(prevented,2);
  assert.doesNotMatch(page.element('ui-attachment-draft').innerHTML,/截图.png/);
  assert.match(page.element('ui-attachment-draft').innerHTML,/说明.docx/);
  assert.deepEqual(page.revoked,['blob:截图.png']);
});

test('invalid or oversized batches preserve previous drafts and missing target does not submit',async()=>{
  const page=harness();
  await page.submit();assert.equal(page.requests.length,0);
  await page.choose([{name:'保留.txt',size:10}]);
  await page.choose([{name:'other.txt',size:10},{name:'bad.html',size:1}]);
  assert.match(page.messages.at(-1).message,/支持/);
  assert.doesNotMatch(page.element('ui-attachment-draft').innerHTML,/other.txt/);
  await page.choose([{name:'大文件.pdf',size:50_000_000}]);
  assert.match(page.messages.at(-1).message,/50 MB/);
  assert.match(page.element('ui-attachment-draft').innerHTML,/保留.txt/);
  await page.choose(Array.from({length:10},(_,index)=>({name:index+'.txt',size:1})));
  assert.match(page.messages.at(-1).message,/10 个/);
});

test('failed saves preserve files for retry and session changes release unrelated drafts',async()=>{
  const page=harness();
  await page.choose([{name:'要求.png',size:10}]);
  page.element('target-url').value='https://example.test';
  page.evaluate("api=async()=>{throw Error('保存失败')}");
  await page.submit();
  assert.match(page.messages.at(-1).message,/保存失败/);
  assert.match(page.element('ui-attachment-draft').innerHTML,/要求.png/);
  assert.equal(page.revoked.length,0);
  page.evaluate("state.project={id:'other',title:'另一个会话',task:{goal:'测试'}};UIWorkflow.renderDocument()");
  assert.deepEqual(page.revoked,['blob:要求.png']);
});


test('one uploaded Markdown document is auto-routed without requiring a title or duplicating its attachment',async()=>{
  const page=harness();
  page.element('target-url').value='https://example.test/pay';
  await page.choose([{name:'付款需求.md',size:40,text:async()=> '# 验收\n- 权益到账后完成付款。'}]);
  await page.submit();
  assert.equal(page.requests[0].path,'/api/requirement-tests');
  assert.equal(page.requests[0].body.title,'付款需求');
  assert.match(page.requests[0].body.content,/权益到账/);
  assert.equal(page.requests[0].body.attachments.length,0);
  assert.doesNotMatch(JSON.stringify(page.requests),/\/task/);
});


test('address-only exploration saves without starting execution on the source page',async()=>{
  const page=harness();
  page.element('target-url').value='https://example.test/page';
  await page.submit();
  assert.equal(page.requests.length,1);
  assert.equal(page.requests[0].path,'/api/ui-tests');
  assert.equal(page.requests[0].body.target_url,'https://example.test/page');
  assert.equal(page.requests[0].body.title,'页面探索测试');
  assert.equal(page.requests[0].body.attachments.length,0);
  assert.equal(page.messages.some(m=>m.error),false);
});

test('scene retention is visible on the initial form before optional settings',()=>{
  const page=harness();
  const html=page.element('ui-document-panel').innerHTML;
  const main=html.slice(html.indexOf('<form id="ui-test-form">'),html.indexOf('<details class="ui-options">'));
  assert.match(main,/<select name="scene_retention" data-scene-retention-scope/);
  assert.match(main,/测试现场保留/);
  assert.match(main,/value="defects"/);
  assert.match(main,/value="test_data"/);
  assert.match(main,/value="full"/);
  assert.match(main,/<option value="none" selected>不保留测试现场/);
  assert.doesNotMatch(main,/data-scene-retention-toggle/);
});

test('page, pasted requirements and Markdown uploads retain the selection when execution starts separately',async()=>{
  for(const mode of ['page','pasted','upload'])for(const value of ['none','defects','test_data','full']){
    const page=harness();page.element('target-url').value='https://example.test';
    if(mode==='pasted')page.element('test-goal').value='保留付款后的订单以便复测';
    if(mode==='upload')await page.choose([{name:'requirements.md',size:40,text:async()=> '# 需求\n订单完成后权益到账。'}]);
    await page.selectScene(value);
    assert.equal(page.element('ui-test-form-scene-scope').hidden,false);
    await page.submit();
    assert.equal(page.requests[0].body.scene_retention,value,`${mode} creation`);
    assert.equal(page.requests.length,1);
    await page.evaluate('UIWorkflow.handoff()');
    assert.equal(page.requests[1].body.scene_retention,value,`${mode} handoff`);
    assert.equal(page.messages.some(message=>message.error),false);
  }
});

test('regression selects its own retention and never hands off a stale policy from the prior round',async()=>{
  for(const value of ['none','defects','test_data','full']){
    const page=harness();
    page.evaluate("state.project={id:'saved',title:'原测试',ui_target_url:'https://example.test',ui_scene_retention:{key:'full'},task:{goal:'原目标'}};state.sceneRetentionProject='saved';state.sceneRetentionDraft='full'");
    const toggle=page.element('ui-regression-toggle');toggle.closest=()=>page.element('report-panel');
    toggle.hasAttribute=name=>name==='data-ui-regression';
    await page.emit('click',{target:{closest:selector=>selector==='[data-ui-regression],[data-ui-continue]'?toggle:null}});
    assert.match(page.element('report-panel').inserted,/<select name="scene_retention" data-scene-retention-scope/);
    assert.match(page.element('report-panel').inserted,/<option value="none" selected>不保留测试现场/);
    assert.doesNotMatch(page.element('report-panel').inserted,/data-scene-retention-toggle/);
    await page.selectScene(value,'ui-regression-form');
    await page.submit('ui-regression-form');
    assert.equal(page.requests[0].path,'/api/ui-tests/saved/regressions');
    assert.equal(page.requests[0].body.scene_retention,value,'regression creation');
    assert.equal(page.requests[1].body.scene_retention,value,'regression handoff');
    assert.equal(page.messages.some(message=>message.error),false);
  }
});

test('missing or invalid target blocks upload routing and legacy task handoff before any write',async()=>{
  const page=harness();
  await page.choose([{name:'付款需求.md',size:40,text:async()=> '# 验收\n- 权益到账后完成付款。'}]);
  for(const target of ['', '  ', 'javascript:alert(1)', 'https://user:secret@example.test']){
    page.element('target-url').value=target;
    await page.submit();
    assert.equal(page.requests.length,0);
    assert.match(page.messages.at(-1).message,/HTTP\(S\).*测试地址/);
  }
  page.evaluate("state.project={id:'legacy',task:{goal:'页面测试'}}");
  await assert.rejects(page.evaluate('UIWorkflow.handoff()'),/测试地址/);
  assert.equal(page.requests.length,0);
  assert.match(page.element('ui-attachment-draft').innerHTML,/付款需求.md/);
});
