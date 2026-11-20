const {test}=require('node:test');
const assert=require('node:assert/strict');
const {notRunReason,summarize}=require('../../api_test_tool/static/report-review.js');
test('unexecuted cases explain this round without inventing a previous pass',()=>{
 assert.equal(notRunReason({status:'not_run',not_run_reason:'上轮报告 R1 用例 A 通过；本轮仅回归失败项'}),'上轮报告 R1 用例 A 通过；本轮仅回归失败项');
 assert.equal(notRunReason({status:'not_run',evidence:'缺少设备'}),'缺少设备');
 assert.match(notRunReason({status:'not_run'}),/未记录本轮未执行原因/);
 assert.equal(notRunReason({status:'passed',not_run_reason:'旧原因'}),'');
 assert.equal(summarize([{status:'not_run',not_run_reason:'上轮通过'}]).executed,0);
});
