const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function reviewFixture({metadata={},batch=null,reducedMotion=false}={}){
 const actions=[],requests=[],elements=new Map();
 const node=()=>({
  checked:false,hidden:false,disabled:false,attributes:{},classes:new Set(),
  setAttribute(name,value){this.attributes[name]=value},
  removeAttribute(name){delete this.attributes[name]},
  focus(options){actions.push({kind:'focus',options})},
  scrollIntoView(options){actions.push({kind:'scroll',options})},
  classList:{
   add(name){elements.get('pc-review-confirmation').classes.add(name)},
   remove(name){elements.get('pc-review-confirmation').classes.delete(name)},
   toggle(){}
  }
 });
 for(const id of ['pc-reviewed','pc-review-confirmation','pc-review-hint','pc-submit'])elements.set(id,node());
 const context=vm.createContext({
  window:{PingCodeTriage:{canSubmit:record=>!record||record.status==='failed'},matchMedia:()=>({matches:reducedMotion})},
  location:{pathname:'/'},
  document:{getElementById:id=>elements.get(id),querySelector:()=>null},
  fetch:async(...args)=>{requests.push(args);throw Error('Unexpected request')}
 });
 const source=fs.readFileSync(require.resolve('../../api_test_tool/static/pingcode.js'),'utf8');
 vm.runInContext(source.replace(/\}\)\(\);\s*$/,
  'globalThis.reviewTest={reviewBeforeSubmit,resetReview,submit,updateSubmitState,configure(m,b,s=false){meta=m;batchEntries=b;sending=s}};})();'),context);
 context.reviewTest.configure(metadata,batch);
 const event=()=>({prevented:false,preventDefault(){this.prevented=true}});
 return{api:context.reviewTest,actions,requests,elements,event};
}

test('unchecked push scrolls to and focuses the review checkbox without checking or publishing',async()=>{
 const f=reviewFixture(),click=f.event();
 f.api.updateSubmitState();
 assert.equal(f.elements.get('pc-submit').disabled,false);
 f.api.reviewBeforeSubmit(click);
 assert.equal(click.prevented,true);
 assert.equal(f.elements.get('pc-reviewed').checked,false);
 assert.equal(f.elements.get('pc-reviewed').attributes['aria-invalid'],'true');
 assert.equal(f.elements.get('pc-review-hint').hidden,false);
 assert.match(f.elements.get('pc-review-hint').textContent,/请先勾选/);
 assert.ok(f.elements.get('pc-review-confirmation').classes.has('pc-review-required'));
 assert.deepEqual(f.actions.map(action=>action.kind),['focus','scroll']);
 assert.equal(f.actions[1].options.block,'center');
 const submit=f.event();await f.api.submit(submit);
 assert.equal(submit.prevented,true);
 assert.equal(f.requests.length,0);
});

test('reviewed push proceeds, while editing clears consent and allows another reminder',()=>{
 const f=reviewFixture();
 f.elements.get('pc-reviewed').checked=true;
 const click=f.event();f.api.reviewBeforeSubmit(click);
 assert.equal(click.prevented,false);
 assert.equal(f.actions.length,0);
 f.api.resetReview();
 assert.equal(f.elements.get('pc-reviewed').checked,false);
 assert.equal(f.elements.get('pc-submit').disabled,false);
 const retry=f.event();f.api.reviewBeforeSubmit(retry);
 assert.equal(retry.prevented,true);
 f.api.resetReview();
 assert.equal(f.elements.get('pc-reviewed').attributes['aria-invalid'],undefined);
 assert.equal(f.elements.get('pc-review-hint').hidden,true);
 assert.equal(f.elements.get('pc-review-hint').textContent,'');
 assert.equal(f.elements.get('pc-review-confirmation').classes.size,0);
});

test('loading, active submission and completed batches keep push unavailable',()=>{
 const f=reviewFixture();
 for(const [meta,batch,sending,disabled] of [
  [null,null,false,true],[{},null,true,true],[{},[],false,true],
  [{},[{record:{status:'submitted'}}],false,true],
  [{},[{record:{status:'submitted'}},{record:{status:'failed'}}],false,false]
 ]){
  f.api.configure(meta,batch,sending);f.api.resetReview();
  assert.equal(f.elements.get('pc-submit').disabled,disabled);
 }
});

test('review reminder respects reduced motion',()=>{
 const f=reviewFixture({reducedMotion:true});
 f.api.reviewBeforeSubmit(f.event());
 assert.equal(f.actions.find(action=>action.kind==='scroll').options.behavior,'auto');
});
