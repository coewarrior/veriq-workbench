# Codex 直接操作独立浏览器环境
## 当前平台全局范围（2026-10-26）

当前平台全局范围：多账号、双账号、跨账号及跨租户对照/隔离业务场景一律不测（用户明确排除多账号场景）。保留具体设计和已有真实结果；未执行项使用 not_run，not_run_reason 填写上述原因；UI cases.account_scope、API design.account_scope 使用 multi_account/cross_account/cross_tenant 明确范围。不算通过，不申请第二账号、不等待账号集合、不为其创建执行会话或续接，不另做替代测试。普通继续测试/重测不解除此规则。不同模块各用一个账号并发仍允许；单账号权限、匿名及其他适用风险覆盖保持。已有真实对象责任的必要清理和无需账号的报告仍按原授权及回收协议处理，不扩展业务测试。

此明确范围变更优先于下文历史多账号示例；既有隔离、授权、清理及回收协议仍保护历史现场，不授权发起新多账号业务。


0.17.71 的公共执行边界：Codex 观察 → 公开浏览器工具返回结果 → Codex 判断下一步。平台管理账号、真实隔离环境、原并发、记录和明确结束后的交还；不包装点击、不增加动作授权、强制防卡关闭、后台模型或 Runner。

每个账号槽位使用一个独立 Chromium 进程和新建的私有 profile。Codex 通过 Playwright `chromium.connectOverCDP` 直接取得该进程的默认持久 Context 和 Page。浏览器独立于 REPL 连接；不用会随连接销毁的临时 `browser.newContext()` 承载任务现场。多个标签、隐藏窗口或无痕窗口名称不代表账号隔离；禁止使用用户已有 profile 或复制 Cookie。

## 默认入口

1. 平台原 start_session_test/dispatch 返回 `browser_assignment`，协调者合入原 assignment，保留 task/node/holder/executor、全部账号数、私有目录和设计。`native-run-kit` 默认生成隔离入口，用户无需配置路径、模式、主机或并发。
2. 先阅读当前 node_repl/Playwright 公开说明，使用返回的 `environment_tool_arguments` 执行环境入口。它自动查找本机 Playwright 和 Chromium/Chrome，仅创建或连接本任务环境。每个 profile、进程 PID、页面标识和创建时间保存在权限受限的 `browser-environment.json`；该目录及 profile 不入 Git 或报告。缺少运行时明确报告能力缺口，不回退共享 IAB。
3. 沿原 `native-cycle.js` prepare 一次分配账号、取得上下文、复用原基线并取得接收器真实就绪。实际排队才结束回合，原资源事件后 resume；不新增账号授权链路或轮询。
4. ready 后 `await nativeBrowserEnvironment.enter(entry_url)` 返回原 Page；首次核对账号与 Context 绑定一次。多账号使用 `pagesByAccount.get(account_id)`，其他账号按实际业务导航。凭据沿原 credentials 取得，通过真实 UI 登录；原 native_login 区分未核实、匹配、不匹配，不能将掩码或未核实当不匹配。
5. Codex 直接使用原 Page API 自行观察和操作。已知步骤、局部观察、逐项断言可同次调用；未知页面变化返回判断。缓存函数按源码摘要及 API 复用，修改定位无需重写公共函数。保留原探索、独立用例、全部断言和证据，不套用历史通过。

## 普通错误与保存

`nativeBrowserCase` 仅为可选记录辅助函数，不是动作控制器。`j.step` 记录起止、耗时和具体失败步骤；普通异常返回 `interrupted`、原 `observation`、`failed_step`，不自动添加业务失败断言、不自动执行 recover/close、不提交最终判定。公共加载器将中断草稿保存在本轮私有文件。Codex 读取真实现场、修正定位后用 `observation:原草稿` 继续未完成部分，或自行决定保存真实 partial/blocked；不要自动重演结果未知的提交。

真实用例判定后通过原 emit/record 立即保存。接收器收到保存错误仍保留原绑定；未知写入的 pending 回执仍阻止后续用例。nativeEmit 等待预算结束仅返回 pending 和 request_id，使用 `nativeReceipt(request_id)` 读取原回执；明确未发送或 HTTP 拒绝可由 Codex 修正原观察后补交；未知 POST 用 `nativeReceipt(request_id,{reconcile:true})` 只读核对原记录，只有原 execution/case/status/actual 和修订匹配才解除该保存的不确定状态。不重发未知 POST、不自动关闭浏览器、不将保存错误判为业务失败。每个请求回执单独保留，不能把另一条成功当作本条已保存。普通错误不向正常模块发送协调消息。

工具调用 timeout_ms 按本次明确操作、实际等待和保存预算留返回余量；该预算限制当前工具调用，不代表任务生命周期。页面动作没有平台统一超时代理。等待真实页面条件，匹配不到旧结构时返回 Codex 重新观察，不固定 sleep 或盲等旧目标。

## 连接恢复和明确结束

点击、等待或截图超时首先是具体操作中断；`node_repl` 的 kernel reset 是执行工具重置，不是被测接口缺陷。保留错误原文、发生时间、阶段、用例/对象和未知提交状态。只有有证据的被测响应差异才判业务失败；HTTP 400、工具超时和未知底层根因分别记录。

执行包提供 `environment_recovery_tool_arguments`：在重置后的原 node_repl 重新阅读工具说明，再执行该入口。它先只读核对本任务进程及本地调试端点，将每个阶段写入私有 `browser-diagnostic-*.json`，随后仅断开旧 CDP 连接并连接原 profile/页面，保存 `browser-reconnect-*.json`。成功只表示连接恢复；再取得原 Page、加载同版函数、观察现场并核实未知提交，才能继续未完成步骤。不要复用已丢失的 Promise 或变量，不自动刷新/导航/重放 POST。诊断文件不得进入公开报告、Git 或聊天；报告仅引用不含秘密的阶段、错误名、时间及恢复结论。

进程核验优先核对原回执中的 PID、根浏览器参数、私有 profile 和进程代次；端点 HTTP200 仅证明本地端点可达，不能替代控制连接成功。诊断应保留阶段和耗时，区分本机进程查询、端点发现、CDP 初始化与业务响应，不能将本机控制超时统一归为网络故障。进程查询异常仍为未知，不以其推断进程死亡、重启或释放账号。

恢复入口自身超时或再次 kernel reset 表示恢复未确认，不等于原环境不可恢复；读取最后持久阶段，区分进程查询失败、进程退出、调试端点不可达和原页面未恢复，继续针对该故障定位。调用 `nativeIsolatedModule.diagnose({assignment_file:原文件,directory:原目录})` 可单独取得只读诊断，不创建浏览器或提交业务。真实进程退出才按下方原显式重启规则处理。无法继续时写清已尝试操作、结果、仍未知原因和受影响用例，交付部分结果；明确停止/取消直接执行原关闭与交还，不因恢复流程延迟停止。

- REPL 重置或连接断开：优先使用本包 `environment_recovery_tool_arguments`，连接原私有 profile 和原页面并留下诊断/恢复回执；旧包没有恢复入口时沿原 environment_setup 兼容接续。重新加载同版缓存函数一次。已进入的页面不会重新 goto，不重置账号、用例或记录。原页面已关闭时，观察 `contexts[index].pages()` 后由 Codex 显式 `selectPage(index,page)`，不自动新建业务现场。
- 真实浏览器进程退出：由 Codex 核对原观察/未知写入后显式使用 `prepare({...原参数,restart_exited:true})`，在原 profile、原逻辑 context_id 上重启；新版按真实新进程递增 browser_generation，原账号绑定不变，已交还后登记拒绝已确认退出的同/更旧已知代际；旧无代际包保留原真实登记/显式替换兼容路径。重新核实页面与登录，业务不自动重放。`confirmExit(directory)` 仅在所有归属进程均已退出时出具退出依据，绝不强杀。部分启动失败或仅部分进程死亡时，可显式 `closeOwned({assignment_file,directory,runtime_context})` 只连接并关闭存活归属进程，无需先重启死亡进程。
- 旧版确已退出、需要换新 profile：原执行者在 assignment 的 `replace_exited_environment` 提供 `{browser_stopped:true,reason:真实依据,previous_context_ids:[原ID]}`。原 prepare 通过同一 checkpoint 原子替换环境绑定；保留账号集合、原任务、用例和证据。重复请求返回原替换回执，不重新排队，不影响其他执行者。不能热迁移正常旧环境；旧版无进程资料时须沿原执行者的真实退出证据核对，不编造。
- 仅明确结束或取消任务时清理本任务对象，显式 `await nativeFinish(()=>nativeBrowserEnvironment.close())` 关闭全部归属进程并保存退出依据。随后立即使用原生命周期 `input={action:'closeout',from_observation:true}` 交还、定向通知、发布原记录；协调者收到后先核对并 ACK，再整理报告。非缓存入口可直接调用 `nativeFinishTask({close,directory})`。
- `record` 只保存；只有明确 `finish_task:true` 且真实 `browser_stopped/reason` 才允许合并保存和交还。关闭失败保留现场，不能声明退出。若已确实退出但保存仍未知，只交还并保留未确认记录，不发布完整成功报告。

保留原并发、共享探索/独占账号规则、增量保存、代码缓存、报告汇总和交接确认。正常旧执行包不被覆盖或唤醒；新包用于后续派发或原任务明确恢复边界。平台上线不等于已验证真实业务或多账号链路。模型与测试范围仍以用户授权为准。

## 平台请求的瞬态网络故障

免安装客户端只对明确只读的平台查询做请求内有限重试，最多首次后的两次，并受原请求等待预算约束；遵守服务端 Retry-After，超过剩余预算不提前重发。401/403/409、证书错误和普通参数错误不按瞬断重试。并非所有 get 名称或 MCP POST 都可重试，写入/执行/复合动作不进入读取白名单。

浏览器业务动作不经过这层自动重试；提交后超时沿原对象和回执核对，不能因网络恢复重发业务。首次故障、后续恢复及真实断言分别记录；断网就是被测条件时，不得用恢复成功覆盖首次结果。平台保存丢响应继续沿原 nativeReceipt(request_id,{reconcile:true}) 和持久观察只读对账，不再发送保存 POST；未发送和明确拒绝按原流程修正补交。平台不可达时保存本地观察与原检查点，不能宣称远端已保存、账号已释放或擅自新增业务；恢复后核对原任务仍有授权且未停止。

本兜底不更换账号、模型、代理、网络出口或浏览器，不跳过 TLS，不后台定时唤醒模型，也不改变原并发。仍无法恢复时保留具体失败层、未知操作和关联用例，沿原停止/保留现场规则处理。
