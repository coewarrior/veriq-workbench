const {test}=require('node:test');
const assert=require('node:assert/strict');
const t=require('../../api_test_tool/static/pingcode-triage.js');
test('maps labels rather than arbitrary IDs or ordering',()=>{
 assert.equal(t.matchOption([{id:'x9',name:'低'},{id:'x3',name:'高'}],'high'),'x3');
 assert.equal(t.matchOption([{id:'high',name:'自定义业务级别'}],'high'),'');
 assert.equal(t.matchOption([{id:'a',name:'高'},{id:'b',name:'高'}],'high'),'');
 assert.equal(t.optionLevel('P0 / 紧急'),'critical');
});
test('severity field may have a custom property ID',()=>{
 const m={properties:[{id:'field-8',name:'严重程度',options:[{_id:'s9',text:'严重'},{_id:'s10',text:'一般'}]}]};
 assert.equal(t.severityProperty(m).id,'field-8');
 assert.equal(t.severityDefault(m,'high'),'s9');
 assert.equal(t.severityDefault({properties:[]},'low'),'low');
});
test('does not pick read-only or multi-select severity',()=>{
 assert.equal(t.severityProperty({properties:[{id:'severity',readonly:true,options:[{id:'x',name:'高'}]}]}),undefined);
});
test('batch continues after a definite rejection and preserves unknown results',async()=>{
 const updates=[];
 const results=await t.sendQueue([1,2,3],async n=>{if(n===1)return{status:'failed'};if(n===2)throw Error('断线');return{status:'submitted'};},(n,r)=>updates.push([n,r.status]));
 assert.deepEqual(updates,[[1,'failed'],[2,'unknown'],[3,'submitted']]);
 assert.equal(results.length,3);assert.equal(t.canSubmit(results[0]),true);assert.equal(t.canSubmit(results[1]),false);assert.equal(t.canSubmit(results[2]),false);
});
test('lifecycle decisions control submission independently from transport status',()=>{
 assert.equal(t.canSubmit({status:'draft',triage_status:'pending_submission'}),true);
 assert.equal(t.canSubmit({status:'failed',triage_status:'pending_submission'}),true);
 assert.equal(t.canSubmit({status:'draft',triage_status:'rejected'}),false);
 assert.equal(t.canSubmit({status:'submitted',triage_status:'pending_regression'}),false);
 assert.equal(t.lifecycleStatus({status:'submitted'}),'submitted');
});
test('stop only prevents subsequent items',async()=>{
 let stop=false;const sent=[];
 await t.sendQueue([1,2,3],async n=>{sent.push(n);return{status:'submitted'};},()=>{stop=true},()=>stop);
 assert.deepEqual(sent,[1]);
});

test('maps the real five-tier PingCode priority scale',()=>{
 const options=[{id:'a',name:'最高'},{id:'b',name:'较高'},{id:'c',name:'普通'},{id:'d',name:'较低'},{id:'e',name:'最低'}];
 assert.equal(t.matchOption(options,'critical'),'a');
 assert.equal(t.matchOption(options,'high'),'b');
 assert.equal(t.matchOption(options,'medium'),'c');
 assert.equal(t.matchOption(options,'low'),'d');
 assert.equal(t.matchOption([...options].reverse(),'low'),'d');
});

test('old report draft refreshes while manual edits survive',()=>{
 const draft={title:'查询归属错误',description:'【标题】查询归属错误\n新版描述'};
 const old='【标题】接口断言未通过：GET /items/4 · 查询归属错误\n原描述';
 assert.equal(t.reviewDescription({value:old,defaultValue:old},draft),draft.description);
 assert.equal(t.reviewDescription({value:old.replace('原描述','人工补充'),defaultValue:old},draft),'【标题】查询归属错误\n人工补充');
 assert.equal(t.reviewDescription({value:'【标题】人工标题\n人工内容',defaultValue:old},draft),'【标题】人工标题\n人工内容');
});

test('reviewed descriptions retain edits and gain one server-owned report reference',()=>{
 const reference={url:'https://workspace.test/api/projects/p/reports/old/index.html',text:'【平台报告】\nhttps://workspace.test/api/projects/p/reports/old/index.html\n用例编号：UPLOAD-06'};
 const draft={title:'处理文件失败',description:'新版正文\n\n'+reference.text,report_reference:reference};
 assert.equal(t.reviewDescription(null,draft),draft.description);
 const edited=t.reviewDescription({value:'人工补充复现步骤',defaultValue:'旧正文'},draft);
 assert.equal(edited,'人工补充复现步骤\n\n'+reference.text);
 assert.equal(t.withReportReference(edited,draft),edited);
 assert.equal(t.withReportReference('人工正文\r\n'+reference.text,draft),'人工正文\r\n'+reference.text);
});

test('batch entries preserve each original report reference',async()=>{
 const drafts=['old-a','old-b'].map(id=>({report_reference:{url:'https://workspace.test/'+id,text:'【平台报告】\nhttps://workspace.test/'+id}}));
 const entries=drafts.map((draft,index)=>({description:t.withReportReference('人工正文 '+index,draft)}));
 const sent=[];
 await t.sendQueue(entries,async entry=>{sent.push(entry.description);return {status:'submitted'};},()=>{});
 assert.match(sent[0],/old-a$/);
 assert.match(sent[1],/old-b$/);
 assert.ok(!sent[0].includes('old-b')&&!sent[1].includes('old-a'));
});
