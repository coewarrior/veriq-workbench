import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {grade} from './grader.mjs';
import {Journal} from './executor.mjs';
import {schedule} from './scheduler.mjs';

const state=()=>({docs:[],events:[],feedback:'',answer:'',history:[],denied:false});
const run=(observations=[],claims=[])=>({scenario:'x',observations,claims});

test('fabricated success does not count as coverage and is an incorrect pass',()=>{
  const g=grade({kind:'staged',goals:['uploaded']},run([{id:'uploaded',pass:true}]),state());
  assert.equal(g.verified,0);assert.equal(g.falsePasses,1);
});
test('unexecuted failure cannot inflate coverage',()=>{
  const g=grade({kind:'empty-defect',goals:['empty-feedback']},run([{id:'empty-feedback',pass:false}]),state());
  assert.equal(g.verified,0);
});
test('actual product failure counts as verified while remaining failed',()=>{
  const s=state();s.events=[{action:'upload',bytes:0}];
  const g=grade({kind:'empty-defect',goals:['empty-feedback']},run([{id:'empty-feedback',pass:false}],[{status:'failed'}]),s);
  assert.equal(g.verified,1);assert.equal(g.defectDetected,true);assert.equal(g.falsePasses,0);
});
test('permission-negative control cannot be bypassed by marking it passed',()=>{
  const s=state();s.denied=true;
  const absent=grade({kind:'denied',goals:['legitimate-block']},run(),s);assert.equal(absent.verified,0);
  const genuine=grade({kind:'denied',goals:['legitimate-block']},run([],[{status:'blocked'}]),s);
  assert.equal(genuine.verified,1);assert.equal(genuine.falseBlocks,0);
});
test('unknown rule is excluded from independent-block count but retained',()=>{
  const g=grade({kind:'rules',goals:['feedback','original-intact']},run([],[{status:'pending_rule',checkpoints:['feedback','original-intact','policy']}]),state());
  assert.equal(g.falseBlocks,2);assert.equal(g.retainedUnknown,true);
});
test('SQLite intent survives closing and reopening; evidence remains separate',()=>{
  const dir=mkdtempSync(path.join(tmpdir(),'execution-benchmark-'));
  try{let j=new Journal(path.join(dir,'events.sqlite'));j.write('intent',{action:'upload',name:'resume.txt'});j.close();
    j=new Journal(path.join(dir,'events.sqlite'));assert.deepEqual(j.read('intent'),[{action:'upload',name:'resume.txt'}]);assert.equal(j.read('result').length,0);j.close();
  }finally{rmSync(dir,{recursive:true,force:true})}
});
test('priority never skips a prerequisite and the scheduler preserves all nodes',()=>{
  const graph=[{id:'setup',priority:0},{id:'format',priority:1,dependsOn:['setup']},{id:'core',priority:3,dependsOn:['setup']}];
  assert.deepEqual(schedule(graph,'stateful').map(x=>x.id),['setup','core','format']);
  assert.deepEqual(schedule(graph,'baseline').map(x=>x.id),['setup','format','core']);
  assert.throws(()=>schedule([{id:'a',dependsOn:['b']},{id:'b',dependsOn:['a']}],'stateful'),/Cyclic/);
});
