/* Derive display state from recorded activity, never from model API configuration. */
(function(root){
  function describe(project, connection={}, now=Date.now()/1000){
    const progress=project?.mcp_progress;
    const job=project?.last_job;
    let phase=progress?.phase||'waiting', label=progress?.label||'等待 Codex 接手', message=progress?.message||'';
    if(progress?.source==='execution_records'){
      const active=progress.active===true;
      const status={completed:'报告已保存',blocked:'执行受阻',waiting:'等待资源或执行者',paused:'已暂停',stopped:'已停止',
        settling:'正在收尾',preparing:'正在准备',failed:'执行异常',awaiting_report:'执行已结束，报告未发布'}[phase]||(active?'正在执行':label);
      return {phase,label,message,active,stale:false,connected:Boolean(connection.connected),updatedAt:progress.updated_at,
        lastCaseSavedAt:progress.last_case_saved_at,status};
    }
    const jobTime=Math.max(job?.finished_at||0,job?.started_at||0,job?.created_at||0,...(job?.logs||[]).map(log=>log.at));
    const jobCurrent=job && (!progress || jobTime>=progress.updated_at || phase==='executing');
    const running=Boolean(jobCurrent && ['queued','running'].includes(job.status));
    if(running){phase='executing';label=job.status==='queued'?'等待执行资源':'执行接口测试';}
    else if(jobCurrent && job.status==='failed'){phase='failed';label='执行异常';message=job.error||message;}
    else if(jobCurrent && job.status==='completed' && ['executing','designing'].includes(phase)){phase='reporting';label='分析结果与整理报告';}
    if(!progress && project?.last_analysis){phase='completed';label='任务已完成';}
    const recent=Boolean(progress && now-progress.updated_at<120);
    const active=Boolean(connection.connected && (running || recent && !['waiting','failed','completed'].includes(phase)));
    const stale=Boolean(progress && !active && !['waiting','failed','completed'].includes(phase));
    return {phase,label,message,active,stale,connected:Boolean(connection.connected),updatedAt:progress?.updated_at,
      status:phase==='completed'?'已完成':phase==='failed'?'执行异常':active?'正在执行':stale?'等待更新':connection.connected?'已连接':'未连接'};
  }
  function renderCounts(progress,{compact=false}={}){
    const escape=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
    const counts=progress?.case_counts;
    const entries=Object.entries(counts||{}).filter(([,value])=>Number.isInteger(value)&&value>=0);
    const complete=progress?.case_counts_complete===true;
    const recorded=progress?.execution_id&&progress.revision!=null||progress?.modules?.some(m=>m.execution_id&&m.revision!=null);
    const available=Boolean(counts&&(entries.length||complete&&recorded));
    const values=new Map(entries);
    const value=status=>values.has(status)?values.get(status):available&&complete?0:'—';
    const total=available?entries.reduce((sum,[,count])=>sum+count,0):'—';
    const main=[['total',available&&!complete?'已载入部分':compact?'用例':'已保存用例',total],['passed','通过',value('passed')],['failed','不通过',value('failed')],['not_run','未执行',value('not_run')]];
    const labels={partial:'验证未完成',pending_action:'待用户确认',pending_rule:'待确认规则',blocked:'阻塞',retry_passed:'重试后通过'};
    const other=[...Object.keys(labels),...entries.map(([key])=>key).filter(key=>!(key in labels)&&!['passed','failed','not_run'].includes(key))]
      .filter(key=>compact?values.get(key)>0:key==='retry_passed'?values.has(key):true);
    const note=!available?(complete&&!progress.execution_id&&!progress.modules?.some(m=>m.execution_id)?'尚无已保存用例':'用例计数尚未载入'):!complete?'仅显示已载入的部分计数，完整结果请查看原记录。':'';
    return `<div class="case-metrics${compact?' case-metrics-compact':''}"><dl class="case-metrics-grid">${main.map(([key,label,count])=>`<div class="case-metric case-metric-${key}"><dt>${label}</dt><dd${count===0||count==='—'?' class="case-metric-muted"':''}>${count}</dd></div>`).join('')}</dl>${other.length?`<div class="case-metrics-statuses" aria-label="其他用例状态">${other.map(key=>`<span>${escape(labels[key]||key)}<b>${value(key)}</b></span>`).join('')}</div>`:''}${note?`<p class="case-metrics-note">${note}</p>`:''}</div>`;
  }
  if(typeof module!=='undefined')module.exports={describe,renderCounts};else root.CodexProgress={describe,renderCounts};
})(globalThis);
