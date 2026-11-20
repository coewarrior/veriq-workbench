import {writeFileSync} from 'node:fs';
import path from 'node:path';
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const median=values=>{const a=[...values].sort((x,y)=>x-y);return a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2};
const sum=(rs,key)=>rs.reduce((n,r)=>n+r[key],0);
const labels={baseline:'故障片段回放',corrected:'仅修正操作',stateful:'状态执行器'};
export function makeReport({out,manifest,results,plan}){
  const summary={};
  for(const arm of ['baseline','corrected','stateful']){
    const rs=results.filter(r=>r.arm===arm),inc=rs.filter(r=>r.cohort==='incident'),breadth=rs.filter(r=>r.scenario==='breadth');
    summary[arm]={incidentVerified:sum(inc,'verified'),incidentTotal:sum(inc,'total'),falseBlocks:sum(rs,'falseBlocks'),falsePasses:sum(rs,'falsePasses'),duplicateWrites:sum(rs,'duplicateWrites'),earlyCore:median(breadth.map(r=>r.prefix.core)),breadthMs:median(breadth.map(r=>r.ms)),breadthCommands:median(breadth.map(r=>r.commands)),defectDetected:rs.filter(r=>r.defectDetected).length,trueBlocks:rs.filter(r=>r.scenario==='permission-denied'&&r.verified===1).length};
  }
  const b=summary.baseline,n=summary.stateful;
  const speed=(b.breadthMs-n.breadthMs)/b.breadthMs*100;
  const summaryNote=`故障片段回放覆盖 ${b.incidentVerified}/${b.incidentTotal} → ${n.incidentVerified}/${n.incidentTotal}；误阻塞项 ${b.falseBlocks} → ${n.falseBlocks}；前6项内核心状态覆盖 ${b.earlyCore}/6 → ${n.earlyCore}/6；相同15项完整工作负载耗时变化 ${speed.toFixed(1)}%（正数为缩短，不含浏览器启动）。`;
  writeFileSync(path.join(out,'summary.json'),JSON.stringify({summary,speed,summaryNote},null,2));
  const cards=[['故障片段中的有效验证',`${b.incidentVerified}/${b.incidentTotal} → ${n.incidentVerified}/${n.incidentTotal}`,'4组真实问题的缩约回放；不是业务系统总覆盖'],['误阻塞项',`${b.falseBlocks} → ${n.falseBlocks}`,'累计错误blocked事件＋被未知规则误挂起的独立断言'],['前6项中的核心覆盖',`${b.earlyCore}/6 → ${n.earlyCore}/6`,'相同15项最终都执行；比较核心功能被拖延的程度'],['完整工作负载耗时',`${(b.breadthMs/1000).toFixed(2)}s → ${(n.breadthMs/1000).toFixed(2)}s`,'同为15项；5次默认重复取中位数，不包含模型推理']];
  const rows=manifest.protocol.scenarios.map(s=>{
    const arms=['baseline','corrected','stateful'].map(a=>results.filter(r=>r.arm===a&&r.scenario===s.id));
    const cell=rs=>`${sum(rs,'verified')}/${sum(rs,'total')}<small>误阻塞 ${sum(rs,'falseBlocks')} · 错误通过 ${sum(rs,'falsePasses')}<br>记录动作/等待中位 ${median(rs.map(r=>r.commands))} · ${(median(rs.map(r=>r.ms))/1000).toFixed(2)}s</small>`;
    const evidence=arms.flat().map(r=>`<li>${r.repeat+1} · ${labels[r.arm]}：<a href="${r.artifact}/${s.kind==='resume'?'phase-2.png':'final.png'}">截图</a> · <a href="${r.artifact}/commands.jsonl">动作记录</a> · <a href="${r.artifact}/truth.json">独立状态</a>${s.kind==='resume'?'':` · <a href="${r.artifact}/trace.zip">Playwright trace</a>`}<details><summary>逐项判定</summary><pre>${escape(JSON.stringify(r.checks,null,2))}</pre></details></li>`).join('');
    return `<tr><td><strong>${escape(s.title)}</strong><small>${escape(s.cohort)} · ${s.goals.length}项</small><details><summary>来源与证据</summary><p>${escape(s.source)}</p><ul>${evidence}</ul></details></td>${arms.map(rs=>`<td>${cell(rs)}</td>`).join('')}</tr>`;
  }).join('');
  const html=`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>执行架构独立对照 · 实测报告</title><style>
  :root{color-scheme:light}body{font:15px/1.7 system-ui,sans-serif;margin:0;background:#f2f5fa;color:#202d43}main{max-width:1200px;margin:40px auto;padding:0 24px}h1{font-size:30px;margin:10px 0}h2{font-size:20px}small{display:block;color:#63728a;font-size:12px}a{color:#2852b7}section,.card{background:#fff;border:1px solid #dce3ef;border-radius:12px;padding:22px;margin:18px 0}.banner{background:#fff7e4;border-left:4px solid #b98212}.cards{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.card{margin:0}.number{font-size:28px;font-weight:700;color:#24498b}table{border-collapse:collapse;width:100%}th,td{text-align:left;vertical-align:top;padding:14px;border-bottom:1px solid #e2e7f0}th{background:#f3f6fb}td:first-child{width:44%}summary{cursor:pointer;color:#3857a0}pre{white-space:pre-wrap;word-break:break-all;font-size:12px;background:#f4f6fa;padding:12px}.tag{font-size:12px;letter-spacing:2px;color:#536b93}@media(max-width:720px){.cards{grid-template-columns:1fr}main{padding:0 10px}td,th{padding:8px}}
  </style><main><div class="tag">LOCAL CONTROLLED EXPERIMENT · PROTOCOL ${manifest.protocol.version}</div><h1>执行架构独立对照：哪些问题确实改善了</h1><p>真实浏览器 · 独立初态 · ${manifest.repeats}次重复 · 三组循环轮换执行顺序 · 零付费模型调用 · 无业务环境写入</p>
  <section class="banner"><strong>这是机制实验，不是模型能力 A/B。</strong><br>基线冻结这轮已观察到的失误片段和执行顺序；当前任务后来已纠正部分问题。候选使用状态转换、局部依赖与持久化意图。两组共享页面、动作适配器、目标断言与评分器。不能据此声称真实业务整体覆盖或端到端速度提高。合成变体预先公开，不是盲测。</section>
  <div class="cards">${cards.map(([title,value,note])=>`<div class="card"><strong>${title}</strong><div class="number">${value}</div><small>${note}</small></div>`).join('')}</div>
  <section><h2>结论与没有证明的部分</h2><p>${escape(summaryNote)}</p><p>恢复注入后的重复写入：${b.duplicateWrites} → ${n.duplicateWrites}；错误通过：${b.falsePasses} → ${n.falsePasses}。真实权限阻塞正确保留：${b.trueBlocks}/${manifest.repeats} 与 ${n.trueBlocks}/${manifest.repeats}；空文件产品缺陷检出：${b.defectDetected}/${manifest.repeats} 与 ${n.defectDetected}/${manifest.repeats}。</p><p><strong>规则实验的收益来自依赖建模改善。</strong>两组调用同一个现有平台规划函数；没有改生产 planner。状态执行器没有自动发现任意业务模型，没有证明换框架会提升模型探索能力，也没有证明所有网站的上传恢复都能唯一识别对象。</p><p>效率只在“breadth”相同15项全部完成时横向比较。其他场景基线提前错误停止，耗时较短不代表更高效；恢复场景的时间包含两个浏览器进程启动，不能与普通场景合并求提速率。</p></section>
  <section><h2>消融对照：只修正操作能解决多少</h2><p>仅修正漏点提交和资料选择、不改变调度和回写机制时，故障片段有效验证为 ${summary.corrected.incidentVerified}/${summary.corrected.incidentTotal}，误阻塞 ${summary.corrected.falseBlocks}，重复写入 ${summary.corrected.duplicateWrites}，前6项核心覆盖 ${summary.corrected.earlyCore}/6。对应完整15项耗时中位 ${(summary.corrected.breadthMs/1000).toFixed(2)}s。</p><p>因此不能把所有提升归功于新架构：上传和动态选择的收益来自执行正确动作；局部规则来自依赖建模；核心覆盖时机来自排序；重启去重来自持久化意图与结果核查。三组仍为确定性程序，没有证明模型能可靠生成这些结构。</p></section>
  <section><h2>逐场景结果与原始证据</h2><table><thead><tr><th>场景</th><th>故障片段回放</th><th>仅修正操作</th><th>状态执行器</th></tr></thead><tbody>${rows}</tbody></table></section>
  <section><h2>评价口径</h2><ul><li>有效验证 = 执行器确实记录该断言，且结论与独立仿真系统状态一致。发现真实失败也计入验证覆盖。</li><li>覆盖分母在运行前固定；未知的重复处理政策不计入可判定分母，但必须保持待规则。</li><li>误阻塞按错误阻塞事件与独立断言误挂起数计数，不与真实缺权限混为一谈。</li><li>记录动作/等待是 commands.jsonl 中显式记录的浏览器操作，不是模型工具调用数或完整CDP请求数。</li><li>格式任务是相同工作负载的调度代理，未运行实际PDF/OCR/模型解析；不报告格式能力覆盖。</li><li>5次短程测量仅报告中位数、原始数据；不足以得出统计显著性或生产性能结论。</li></ul></section>
  <section><h2>复现与审计</h2><p><a href="manifest.json">协议与源码指纹</a> · <a href="results.json">全部逐次结果</a> · <a href="summary.json">统计数据</a> · <a href="planner.json">当前规划器原始输入输出</a></p><p>源码基线 ${escape(manifest.revision)}；实际实验源码由 manifest 中SHA-256固定。浏览器 ${escape(manifest.browser)}；Node ${escape(manifest.node)}；完成 ${escape(manifest.finishedAt)}。</p><details><summary>规划器对照</summary><pre>${escape(JSON.stringify(plan,null,2))}</pre></details></section></main></html>`;
  writeFileSync(path.join(out,'index.html'),html);return summary;
}
