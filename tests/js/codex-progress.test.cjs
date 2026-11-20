const {test}=require('node:test');
const assert=require('node:assert/strict');
const {describe}=require('../../api_test_tool/static/codex-progress.js');
const progress=(phase,updated_at=1000)=>({phase,label:phase,updated_at});
test('ended execution without a report is visibly idle',()=>{
 const p={mcp_progress:{source:'execution_records',phase:'awaiting_report',label:'执行已结束，报告未发布',active:false}};
 const view=describe(p,{connected:true});
 assert.equal(view.active,false);assert.equal(view.stale,false);
 assert.equal(view.status,'执行已结束，报告未发布');
});
test('connection and current task activity are distinct',()=>{
 assert.equal(describe({}, {connected:true},1001).status,'已连接');
 assert.equal(describe({mcp_progress:progress('reading')},{connected:true},1001).active,true);
 assert.equal(describe({mcp_progress:progress('reading')},{connected:false},1001).active,false);
 assert.equal(describe({mcp_progress:progress('reading')},{connected:true},1121).status,'等待更新');
 assert.equal(describe({last_analysis:{}},{connected:true},1001).status,'已完成');
});
test('server execution remains active and failure supersedes prior progress',()=>{
 const p={mcp_progress:progress('executing'),last_job:{created_at:999,status:'running'}};
 assert.equal(describe(p,{connected:true},2000).active,true);
 p.last_job={...p.last_job,status:'failed',finished_at:1500,error:'执行失败'};
 assert.equal(describe(p,{connected:true},2000).status,'执行异常');
 p.last_job.status='completed';
 assert.equal(describe(p,{connected:true},2000).phase,'reporting');
});
test('new task does not inherit old completion or old job failure',()=>{
 const p={last_analysis:{},last_job:{created_at:800,finished_at:900,status:'failed'},mcp_progress:progress('waiting')};
 assert.equal(describe(p,{connected:true},1001).phase,'waiting');
 assert.equal(describe({mcp_progress:progress('completed')},{connected:true},1001).active,false);
});
test('authoritative execution survives stale connection and preserves waiting/closeout facts',()=>{
 const p={last_job:{status:'failed',finished_at:9999},mcp_progress:{source:'execution_records',
   phase:'executing',label:'执行页面测试',updated_at:1,active:true,last_case_saved_at:900}};
 assert.equal(describe(p,{connected:false},2000).active,true);
 assert.equal(describe(p,{},2000).phase,'executing');
 assert.equal(describe(p,{},2000).lastCaseSavedAt,900);
 p.mcp_progress={...p.mcp_progress,phase:'waiting',active:false};
 assert.equal(describe(p,{},2000).status,'等待资源或执行者');
 p.mcp_progress={...p.mcp_progress,phase:'settling',active:true};
 assert.equal(describe(p,{},2000).status,'正在收尾');
 p.mcp_progress={...p.mcp_progress,phase:'completed',active:false};
 assert.equal(describe(p,{},2000).status,'报告已保存');
});
