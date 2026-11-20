'use strict';
const assert=require('node:assert/strict');
const test=require('node:test');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function workflow(){
  const context={document:{addEventListener(){}},esc:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../../api_test_tool/static/requirements-workflow.js'),'utf8'),context);
  return context.RequirementsWorkflow;
}

test('checkpoint observations and original order data cannot inject markup',()=>{
  const html=workflow().pointHTML({id:'scan',title:'<img src=x onerror=alert(1)>',status:'passed',kind:'manual',verification_mode:'mock',
    expected:'保留原订单',actual:'<script>private()</script>',correlation:{order_id:'<b>original</b>'},action_required:'已完成的旧指令'});
  assert.ok(!html.includes('<img')&&!html.includes('<script>')&&!html.includes('<b>original'));
  assert.match(html,/&lt;script&gt;/);
  assert.match(html,/模拟环境/);
  assert.ok(!html.includes('下一步：')&&!html.includes('data-manual-checkpoint'));
});

test('published manual checkpoints show original order but no mutable completion form',()=>{
  const point={id:'scan',title:'完成模拟人工步骤',status:'pending_action',kind:'manual',verification_mode:'mock',expected:'继续原订单',
    action_required:'完成模拟动作',correlation:{order_id:'original-order'}};
  assert.match(workflow().pointHTML(point,'CASE',false),/data-manual-checkpoint="scan"/);
  const frozen=workflow().pointHTML(point,'CASE',true);
  assert.match(frozen,/original-order/);
  assert.ok(!frozen.includes('<form'));
});

test('case details only display observations; selection belongs to execution controls',()=>{
  const html=workflow().content({traceability:[],questions:[],requirements_without_cases:[]},
    {cases:[{case_id:'PAY',scenario:'页面与账本分别核对',status:'partial',checkpoints:[]}]},{items:[]});
  assert.doesNotMatch(html,/data-resume-case|requirement-resume-form|data-rule-form|data-manual-checkpoint/);
  assert.match(html,/<span>PAY 页面与账本分别核对<\/span>/);
  assert.ok(!html.includes('<summary><label>'));
  assert.match(html,/部分验证/);
});


test('automatic continuation selects unfinished cases and never replays completed payment cases',()=>{
  const flow=workflow(),records={cases:[{case_id:'paid',status:'passed'}, {case_id:'pending',status:'pending_action'}, {case_id:'partial',status:'partial'}, {case_id:'failed',status:'failed'}, {case_id:'new',status:'not_run'}]};
  assert.deepEqual(Array.from(flow.continuationCases(records)),['pending','partial','failed','new']);
  assert.deepEqual(Array.from(flow.continuationCases(records,'retest')),[]);
  assert.deepEqual(Array.from(flow.continuationCases(records,'retest',['paid'])),['paid']);
});

test('shared missing conditions are shown once while checkpoint evidence remains in details',()=>{
  const html=workflow().content({traceability:[],questions:[],requirements_without_cases:[]},{cases:['A','B'].map(case_id=>({case_id,scenario:'观察结果',status:'blocked',checkpoints:[{id:'read',title:'查询权益',status:'blocked',verification_mode:'real',expected:'到账',gaps:[{id:'rights',kind:'dependency',status:'blocked',title:'权益查询',reason:'缺少查询入口'}]}]}))},{items:[]});
  assert.match(html,/需要补充 · 1 项/);
  assert.match(html,/影响 2 条用例/);
  assert.match(html,/<details class="ui-detail-group"><summary>查看用例与执行细节/);
  assert.doesNotMatch(html,/name="reason" required/);
});


test('published rule questions derive affected cases from the immutable snapshot without live-view fields',()=>{
  const html=workflow().content({traceability:[],questions:[{id:'amount',title:'金额单位',status:'open',detail:'待产品明确'}]},
    {id:'source',report_id:'published',cases:[{case_id:'A',scenario:'下单',status:'pending_rule',question_ids:['amount'],checkpoints:[]},{case_id:'B',scenario:'到账',status:'pending_rule',checkpoints:[{id:'rights',title:'权益',status:'pending_rule',verification_mode:'design',expected:'到账',question_ids:['amount']}]}]},
    {items:[]},{readonly:true});
  assert.match(html,/金额单位 · 待明确 · 2 条用例/);
  assert.doesNotMatch(html,/data-stage=|data-requirements-continue/);
  assert.doesNotMatch(html,/data-rule-form|data-manual-checkpoint|data-resume-case|requirement-resume-form|<form/);
});
