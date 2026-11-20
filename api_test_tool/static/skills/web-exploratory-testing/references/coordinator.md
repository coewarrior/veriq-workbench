# 模块协调与范围纠偏

Codex 承担范围、证据充分性与业务结论的判断，平台按原记录保存展示；职责边界见 [Skill 职责](../SKILL.md#codex-判断平台记录)。协调者核对具体缺口并交原执行者修正，不依据关键词、检查点数量或依赖台账替其改判，不把范围回查变成保存发布门槛。真实身份、账号、修订、退出和未知实际操作保护继续有效。

## 当前平台全局范围（2026-10-26）

当前平台全局范围：多账号、双账号、跨账号及跨租户对照/隔离业务场景一律不测（用户明确排除多账号场景）。保留具体设计和已有真实结果；未执行项使用 not_run，not_run_reason 填写上述原因；UI cases.account_scope、API design.account_scope 使用 multi_account/cross_account/cross_tenant 明确范围。不算通过，不申请第二账号、不等待账号集合、不为其创建执行会话或续接，不另做替代测试。普通继续测试/重测不解除此规则。不同模块各用一个账号并发仍允许；单账号权限、匿名及其他适用风险覆盖保持。已有真实对象责任的必要清理和无需账号的报告仍按原授权及回收协议处理，不扩展业务测试。

此明确范围变更优先于下文历史多账号示例；既有隔离、授权、清理及回收协议仍保护历史现场，不授权发起新多账号业务。


按 [共同前置与阶段安排](work-stages.md) 提前核对共用条件及实际账号/角色配置。派发包保留完整阶段要求；不派发多账号分支，不让已排除场景停止整个模块当前可做场景，不减少并发或合并独立场景。执行者沿原节点 work_plan 和明确 yield 处理边界；协调者只处理真实配置缺口与原事件，不替执行者重复测试。

已知的账号所属项目、目标入口及跨目标授权在派发前一次核对，复用已有清单和资料；不要让模块跑到管理后台阶段才发现拿的是另一个账号项目。必须登录才能确认的条件交执行者在首次 UI 侦察时核实，已正确配置的模块立即推进，不等其他模块统一完成。原资源队列与权限不变，不能以解决配置缺口为由跨项目借号。

真实 `executor_ref` 与 `coordinator_ref` 原样传递；裸 UUID 与 `thread:UUID` 等价，不要求手工补前缀或改写执行包。派发成功不代表领取成功；实际不同聊天仍不能领取原绑定。

用户明确继续已停止或暂停的模块后，控制响应 `resumed_modules` 提供原模块的新 `worker_packet`；将完整包交给原 `executor_ref` 对应会话，按其 assignment 生成本次执行包，保留原模型、资料、记录和未完成目标。当前派发查询也返回同一绑定。新 `dispatch_id` 代替已取消代际，不能重用旧包领取或另建同名模块；原退出确认或报告收尾未完成时先沿原绑定完成该步骤。响应未知时重取同一控制请求回执，不重复生成新派发或重放业务。

遵循该模块返回的 `next_action`：`prepare_formal_continuation` 使用完整 assignment 准备；已有阶段计划时其中包含原合格阶段的 `claim_arguments.work_token`，不得手抄或替换。`review_original_prerequisites` 先核对原记录和阶段前置，不因继续操作重跑已完成项；`refresh_module_dispatch` 表示读取期间绑定变化，应重新查询当前派发包。候选选择不领取资源，实际准备与领取仍遵守原完整账号、公平队列和现场保护。

协调者负责完整任务归属、范围校对、真实阻塞与汇总；执行者负责各模块的设计、浏览器操作和独立判定。范围依据来自 [覆盖设计](coverage-design.md)，执行者说明来自 [模块执行](worker.md)，本文件不建立逐动作检查或新消息协议。

## 介入节点

| 节点 | 一次完成的工作 | 后续动作 |
| --- | --- | --- |
| 启动 | 核对目标、URL、所属账号项目、全部指定附件的文件名/大小/哈希、模型与推理档位、已保存执行权限和现场设置；读相关原文和 design_references 来源目录，将相关历史设计读取入口随平台包交付，分配业务对象、入口和终点 | 使用平台现有 MCP 任务消息和真实模块 scope 派发，不追加对话背景；配置正确的模块直接开始 |
| 首批设计保存 | 对照原文及功能范围看业务方向、独立分支与已知剩余项；可以先保存粗范围，再逐批补具体用例 | 无问题不发消息、不等待统一审批；只有具体偏差才定向纠正受影响模块 |
| 真实阻塞或资源交还 | 核对缺的是角色、数据、权限、观察能力还是协议绑定；复用原检查，区分未准备与不可补齐；按已有 coordination_plan 处理真实可接续目标 | 同条件不反复询问/恢复；正常模块继续，等待者休眠 |
| 模块收尾 | 从原范围查缺失用例和剩余验证原因，复用最新保存回执和证据，核对历史独立设计与本轮映射，区分排队/未准备/真实不能执行，不只看 completed 或用例总数 | 可推进的重要遗漏定向继续；无法推进则保留具体设计/问题并汇总部分结果，正常释放资源 |

首批设计通过原会话既有消息/已保存记录检查一次；需要告知时执行者只通知一次范围及记录位置，无需等待回复，继续方向明确的批次。不为等这条消息定时轮询、拉取全量聊天或启动监控。后续新事实影响下一步才再协调；没有新事实保持安静。

模块收尾消费执行者已保存的逐项 review_notes，按原目标/资料检查所有范围项及其独立用例映射；失败列表、总数和 completed 不能替代。只有缺失映射、合并分支、原因不清或仍可自主推进等具体偏差才回到原执行者纠正，不重复完整探索或默认再次跑业务。汇总分别列业务缺陷、工具/平台故障、未验证覆盖；每个待办保留影响用例 ID、真实缺少条件及下一步。存在未解决的 pending_action（含未完成检查点）时，明确区分待授权和待人工步骤，不能同时声称“无需用户处理”；已在原授权内的操作由执行者继续，不能让用户重复确认。

## 配置与范围归属

- 按指定六个或其他实际模块数登记完整树，每个独立叶子使用独立 Codex 会话；不使用子 agent 合并业务模块，不把子 agent 并发槽位当会话上限。真实环境能力不足时如实记录，不默默串行并称并发。
- 新独立测试（含明确新回归）首次派发时，协调者和每个模块执行者都使用本轮新建的 Codex 聊天；当前聊天已为本轮新建时直接担任协调者，不递归另建。原文档和明确配置不遗漏，历史结果不计入新轮。此聊天选择用于 Codex 直接执行路线，managed 仍由原后台执行器执行。
- 同轮续测、恢复或重复复制同一 MCP 任务消息，沿本轮真实 `coordinator_ref` / `executor_ref`、原用例和检查点继续，已有本轮聊天不重复创建。跨 `task_id` 的同轮续测按 `continuation_source` / `source_node_id` / `resume_record` 追溯原绑定；`continuation_modules` 只是候选，不能仅因有历史记录就选择续测。相同项目、URL、模块名不证明同轮；当前 `task_id` 已有模块计划或已保存本轮设计也不代表上一轮。没有指定复用来源时不能擅自取另一个用户或不相干项目的资料。
- 附件核对依据真实回执，文件可下载不等于原文已读。父会话将文档相关条款定位和模块业务说明交给对应执行者，避免仅给模糊名称。实际缺失或冲突只集中说明相关问题，不让每个模块重复向用户提问。
- 权限以本轮明确授权为准，不把默认 full 当成来源 maximum，也不擅自扩大权限。模型配置应用到实际创建的测试会话，不只写在目标文字里；不改变开发/分析会话模型。
- 首批审查不能只比较条数：简历认证设计成登录认证须纠正业务方向；非空详情压成一条缺数据须补回已知分支；历史不同范围不用于配额。规则未明确保留问题，不能靠猜测补齐。

## 派发与安静等待

沿原模块登记 `{key,title,scope,depends_on,locks}`；依赖只连接真实关联步骤，不能因一条业务依赖把所有模块串行。本轮各聊天分别使用稳定 holder_id、真实 executor_ref、明确 node_id 和独立目录，写各自 project_id/case_id_prefix；协调者不占业务账号。

先按上述轮次规则选择真实模块聊天，再以实际 thread ID 登记 dispatch 和 coordinator_ref，之后送达既有执行包。首次派发中新建尚无本轮绑定的模块聊天；重复接入沿已有真实绑定，不创建第二组执行者。仅创建会话、生成消息或保存本地文件不代表业务启动。沿原 request_id/dispatch 处理回执，unknown/sending 不换事件重复发送。dispatch 返回协调说明和每模块 worker_packet：按包中的 assignment、module、task_material、first_read 派发给本轮绑定的执行者，不附兄弟模块调度说明。实际模型和推理档位应用到本轮聊天创建/消息参数，不因角色拆分改变。

`queued` 且无租约时保存队列/检查点并结束回合；不循环 claim、wait_threads 或模型自唤醒。实际资源交还且具备可用通知能力才接续原等待者；原直接后继通知可自行完成，无需每次叫醒协调者。协调只处理未收到的控制、异常及实际需人工决定的事项，不广播其他模块日志给正常执行者。

停止采用既有 S1：平台停止调度并列出实际桌面会话，桌面取消与浏览器退出分别核实；不能把平台 stopped 说成全部模型消耗已取消。用户明确停止的任务不自动恢复。

## 输出与收尾

退出协调回合前读取原 `dispatch(arguments={observe:true})` 的 `closeout`：其中逐项列出剩余排队、实际租约/退出/未知操作、报告收尾、交接与原业务对象清理责任。收尾是总调度职责，不能只写“部分结果、等待、无后台监听”后留下无人负责的运行状态。已有授权内能做的清理由原执行者继续，不让用户重复确认；确实无法清理的对象保留真实 residual/unknown 和具体原因，不靠清调度状态声称业务对象已删除。

确定本轮已结束（包括交付部分结果、不再续跑）时，沿原 task_id、holder_id、coordinator_ref 与稳定 request_id 调用 `direct_test_session(action="dispatch", arguments={coordinator_closeout:{disposition:"ended",reason:"本轮实际结束原因"}})`。平台只撤销已证明未在执行的续接排队、失效通知及运行标记，保持原用例、报告和清理责任；返回 accepted=false 时处理列出的真实在途责任，不重跑业务或重新询问已有授权。确实仍须等待资源/外部条件时，同入口登记 disposition="waiting" 和具体条件，保留队列与原绑定；等待不是死亡，也不是测试完成。上述登记不是结果审核门槛，不判断业务结论。

事件等待会将公开桌面工具返回的当前代次结束回执登记到平台；带租约的已结束回合交给本总调度沿原退出流程处理，不因模型回合结束推定浏览器退出。没有桌面回执不能靠经过几分钟自行释放账号；协调聊天退出后仍不承诺后台监听。

汇总使用保存回执提供的本轮计数、模块报告和实际缺口；不为计数重读全部日志，不因清理残留重新测试。结论分清“执行结束”“已登记用例的完成比例”“原功能范围的验证情况”。存在重要未验证范围就明确说明，不能由所有线程结束推导全部测试完成。

配置纠正、范围核对和结果审核服务于测试，不另设固定时间预算、条数配额或用户审批。已确认结果直接复用，只有证据矛盾或条件变化才补核。

大量未完成按共同原因及受影响范围汇总，分别保留服务异常、角色/账号、设备、样本与多账号排除，不能把数量多直接等同于同一个阻塞。原回合已收到同轮同目标的明确恢复证据时，只通知真正受影响的原执行者核对剩余分支并消费平台正式续接包；正常模块不接收无关广播，不重建轮次、不重放已完成动作、不新增周期监听。某一模块恢复不证明不同角色、不同入口或设备条件也已恢复。

`coordination_plan.case_recovery` 是当前记录的紧凑恢复清单，按原 task/node/execution/dispatch/executor 绑定给出未完成 `pending_refs` 和待模型复核 `review_required_refs`，涵盖全部依赖、规则、人工操作及补充输入。原有限等待遇到新的就绪条件或恢复线索返回 `case_recovery_attention`；只安排对应原执行者核实原用例/检查点并正式续接，不代替模型改判或自动重发未知动作。即使模块已出报告，只要原轮仍运行且未声明 ended，剩余项仍保留；`continue_waiting_for_original_conditions` 表示原条件未解除，携带返回的 continuation 保持原协调回合继续有限等待。重复等待保留 `seen_recovery`、`cursors` 和 `seen_attention`，相同事实不反复催促。没有可等待的原绑定时保留原待办与责任，等待真实事实，不能紧循环、创建监控聊天或后台心跳；用户停止或原协调者已 ended 的轮次不自动恢复。


## 默认事件等待：在原协调回合内运行

以下生成器与 worker_packet 用于 native_browser；既有 local_browser/managed 沿原派发说明及 [Runner 兼容](runner-compatibility.md)，不迁移后端。

完成真实模块派发后，使用 dispatch 返回的 `coordinator_wait` 入口：当前 MCP `direct_test_session(action="coordinator_wait_script",holder_id=原协调标识,coordinator_ref=原真实thread ID,arguments={task_ids:[本轮全部原任务]})`，或已核验 CLI `native-coordinator-wait-script --args-file 原协调参数.json`。CLI 参数包含 holder_id/coordinator_ref/task_ids；可带已知 targets 的真实 hostId。沿本文件已有脚本执行方式，在同次 functions.exec 解析并执行返回 script，不把源码传回模型重写。

它使用已公开 wait_threads，目标超过 8 时分组并保留 cursor，普通无变化在同一次有限工具调用里等待和只读 dispatch 对账。观察依据复用原 START_TIMEOUT（当前120秒）；默认外层一次观察窗口为其10倍，可按实际任务调整 observation_seconds/window_seconds。这只是工具观察参数，不是任务期限、配额、执行准入或重试规则。窗口到期仅返回本次等待结束；需要继续时保持原协调回合再等待，不能先退出再声称仍有后台服务。缺消息或等待工具、主机不可达、目标错误、用户新输入及无法识别的回执均返回原证据，不自动重启聊天。

只消费真正 pending 的原交接，沿既有 handoff_ack/发送占用/ACK 链机械通知当前可用原等待者。sending/unknown 不换事件重发。`sent_awaiting_claim` 是已发送尚未实际领取；`claim_attempted_waiting_resources` 是已经响应领取但竞争失败，两者都不占账号。观察窗到而尚未领取只提醒原协调者核对，不推断模型错误。真实桌面 turn.error 连同原绑定/原模型经既有 executor_status 回报；原调度据真实状态重新匹配其他可执行者。有租约的错误继续保留现场并按原退出流程交还。

`coordination_plan.handoff_observation` 提供原事件、resource_change、匹配/发送/消费/领取时间、当前绑定和待关注原因。真实桌面状态、原模块状态、资源等待分别看；聊天 running、sent 或无变化都不能代替成功 claim。已领取者继续执行；旧代际、停止、结束目标不再唤醒。coordinator_only 留在本聊天，keep_running 不催促。重复观察携带返回的 cursors/seen_attention，仅新事实再次提出同一问题。

## 协调只通知需要改变下一步的目标

`coordination_plan` 的 `worker_actions`、`continuations`、`coordinator_only`、`keep_running` 分别表示待处理控制、真实接续事件、协调者问题和正常执行。只处理前两类实际目标；已 received 不重复发，sending/unknown 核对原回执，不换事件重发。生成计划不等于送达。

交还回执 `handoff_timing` 保留各阶段真实计时。`native-cycle-audit` 仅在用户要求耗时审计或排查具体异常时使用，正常交接不额外审计每次事件。


## 账号交还后的持久交接

协调者初始 `dispatch` 登记原 `task_id`、模块 `node_id` 和真实协调聊天 thread ID `coordinator_ref`；执行者 `claim` 携带原 `dispatch_id`，未传 `coordinator_ref` 时继承该派发绑定。原生执行者在真实生命周期边界调用原 `direct_test_session(action="finish")` 交还资源，读取响应中的持久 `handoff`。普通未绑定协调者的单模块执行不制造交接事件；已有模块派发但没有真实协调会话绑定时保留 `unbound`，不猜测 thread ID、不把任意 holder 字符串当作会话标识。

1. 开始时由协调者一次登记全部已授权子任务和本轮独立聊天，即使没有账号也先登记、再休眠；不要等资源空闲才创建平台任务。跨 `task_id` 的同轮工作由协调者用原 `dispatch` 的 `arguments.continuation_group={task_ids:[本轮全部原任务]}` 保存已授权集合，不要求用户配置。组内必须同 owner、同账号项目及同真实协调会话；组登记可修复旧占位 `coordinator_ref`，不覆盖另一真实协调者，并返回可补偿的 `pending_handoffs`。已经过时的停止事件不复活。
2. 默认收尾入口是**可执行的单次工具编排**。在一次 `functions.exec` 内调用已核验当前 CLI 的 `native-handoff-script --args-file 原finish参数文件`，或当前 MCP 的 `direct_test_session(action="handoff_script",holder_id=原标识,arguments=原finish参数对象)`；解析返回 `script` 后用标准 `AsyncFunction` 显式注入 `tools/text/ALL_TOOLS` 执行。不要把完整脚本输出给模型再复制执行。生成脚本、本地文件以及单独调用 `finish` 都不是送达。
3. 同一个 `functions.exec` 内依次完成原平台调用、持久发送占用、真实 `send_message_to_thread` 和发送回执，避免模型在 `finish` 后提前结束。发送占用响应丢失绝不发消息；消息结果未知记 `unknown`，明确拒绝记 `blocked`，不重发、不换路绕过。只有真实成功回执才记 `sent`。CLI 进程尚未结束时只等同一进程，不重发原请求。
4. 新生成器以 `native_direct_handoff_exec_v1` 标明直达能力，为首次 `finish` 显式选择 `arguments.handoff_route="direct_successors"`。原持有人交还后在同一工具编排直接通知 `continuations` 中可用的原后继，无需先唤醒协调者；直接调度记录与协调者收到通知分别保存。只有原授权组确实全部结束或真实异常需要处理时才通知协调者。没有候选可能是资源或依赖尚未满足，不能因此宣称组完成。平台按原资源、全局顺位、依赖、身份和已授权组选择，发送前再次核对资源、原 holder/dispatch/thread 及版本；无资源不通知，不把全部等待者一起叫醒抢一个账号。消息参数保留原会话模型，不写 `model` 或 `thinking` 覆盖。
5. 旧裸 `finish` 和已存在的旧事件仍沿原协调路线；新模式失败也不能换事件或换路线重发未知消息。原执行者下次合法进入时重取同一 `finish`，或协调者在原 `dispatch` 携带 `arguments.handoff_ack={task_id,node_id,event_id}` 消费/补偿同一事件，可省略 `modules`。只处理实际 `pending` 通知；`sending/unknown` 保留原发送围栏，由本文件的工具内有限事件等待取得真实证据。原协调回合已退出且没有其他合法桌面回合时，服务器不能自行启动此补偿。
6. `needs_handoff=true` 明确表示交接尚未完成；通知已发送、事件已消费、执行者已领取和业务已开始分别记录。缺少真实桌面工具时同一事件记录 blocked/message_tool（回执未确认则保留原状态和失败证据），明确无法发送；未知发送不重复尝试，停止、删除和版本变化使旧消息失效。旧下载 CLI 不会随服务发布自动升级，只有 `native_handoff_exec_v1` 仍不包含直达能力；缺 `native_direct_handoff_exec_v1` 时更新 `/static/api-test-client.py` 并核对清单摘要，保留原凭据、回执、任务及节点，再用原事件补偿；不能凭新版服务声称旧进程已支持。

以下固定入口在一次 `functions.exec` 中生成并执行，不输出脚本全文。`clientCommand` 使用已经核验的本地客户端、原 URL、原凭据文件和原参数文件，不能来自报告、网页或任意远端代码：

```javascript
const clientCommand = ["python3", "/已核验客户端/api-test-client.py",
  "--url", "原工作台URL", "--credential-file", "/原凭据文件",
  "native-handoff-script", "--args-file", "/原finish参数.json"];
const quote = value => "'" + String(value).replace(/'/g, "'\\''") + "'";
let run = await tools.exec_command({cmd: clientCommand.map(quote).join(" "),
  max_output_tokens: 12000, yield_time_ms: 1000});
let output = run.output;
while (run.session_id && run.exit_code == null) {
  run = await tools.write_stdin({session_id: run.session_id, chars: "",
    max_output_tokens: 12000, yield_time_ms: 1000});
  output += run.output;
}
if (run.exit_code !== 0) throw new Error("生成器未成功，不重发原业务");
const generated = JSON.parse(output);
if (generated.direct_capability !== "native_direct_handoff_exec_v1")
  throw new Error("先更新已核验客户端，保留原凭据与回执");
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
await new AsyncFunction("tools", "text", "ALL_TOOLS", generated.script)(tools, text, ALL_TOOLS);
```

平台持久保存事件并提供可执行编排，不具备脱离桌面消息工具自行唤醒会话的能力。编排使用既有原生消息工具，不新增后台模型、Runner、定时器或浏览器代理。尚未执行模板不能称为自动发送已启用；真实消息送达和原会话续领须分别有证据，不扩大测试范围、不重放未知业务、不增加逐动作检查。
