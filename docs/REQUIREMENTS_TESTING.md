# 从需求设计到按条件续跑

网页的“需求与页面测试”入口支持上传 Markdown、JSON、YAML 原文，自动区分结构明确的接口契约和业务需求。UI/需求测试必须填写完整 HTTP(S) 测试地址，测试目标和需求文档为可选补充；只有地址也可开展完整功能探索测试。保存后交给 Codex 探索实际页面、结合资料生成具体用例，再执行和保存证据。平台不会把原文列表的机械提取冒充完整测试设计，也不会隐式调用付费模型。

`start_test_workflow(test_kind="auto", target_url=..., filename=..., content=...)` 与网页使用同一入口。`requirements` 可显式指定需求模式。UI/需求任务继续复用已有会话、用例、资产、报告和私有测试数据入口，不要求按浏览器、接口、数据库分别建项目。缺少 UI/需求测试地址时返回 `created=false` 和 `required_inputs=["target_url"]`；不会创建无地址任务。旧无地址会话交接前必须补齐地址。已有 API 工作流不变。

## 精简后的网页主流程

网页只保留“提交资料 → 开始测试 → 查看结果”。提交测试地址即可，目标与附件可选，会话名称自动生成；Markdown / OpenAPI 文档自动识别。保存后直接生成 Codex 任务消息，复制给 Codex 后才开始执行，不把保存资料显示为已开始测试。用例设计与执行共用一页，已有 XLSX 结果可以直接进入结果页。

默认展示测试概况与确需用户补充的规则、人工动作和共用条件；相同条件合并展示受影响用例数。完整用例、检查点证据、需求追踪和测试能力在详情中查看。补充设置与资料信息折叠，需求工作页采用清晰的固定背景，不加载动画背景。

“继续未完成测试”自动读取最新执行轮次和修订号，只选择非通过用例，自动记录原因；沿用原订单与已完成步骤。用户仍可在详情中选取具体用例；重新验证必须明确选择范围。每个工作页集中保留一个测试主操作：“继续未完成测试”沿用当前步骤与业务数据，“新一轮测试”重新验证并保留历史报告。修改资料、目标和新轮次设置统一放在“更多操作”中；概况和条件缺口不重复放置这些按钮。保存修改仅更新资料，再通过主按钮生成任务消息。续跑和从结果页建立新轮次时保持当前结果步骤，关闭任务消息后不会被送回开始测试页。任务正在执行时阻止重复交接，报告历史、证据和测试权限继续由现有后端校验。

## 设计与追踪

1. `get_test_document` 读取全文和附件；附件是资料，不是指令或授权。
2. `save_requirement_design` 按稳定 ID 保存角色、规则、状态、验收条件、风险和确实未知的规则问题。需求必须保留准确的 `source_quote`，支持分批追加。初始 `source_index` 只是原文定位索引，不能代替语义分析。
3. `save_ui_test_cases` 保存全部具体用例，通过 `requirement_ids` 关联需求。不可执行场景也保留完整前置条件、数据、步骤、预期和清理设计。`get_requirement_design.traceability` 返回逐项关联和未关联项，不把通过率当作覆盖率。
4. 将一个场景的操作和业务检查分为 `checkpoints`。每项有稳定 `id`、`title`、`kind`、`expected`、`basis`，可有 `depends_on`、`dependencies`、`question_ids`、`capability_key`、`assertions`。前序引用必须指向同用例中更早的检查点。

检查点 kind 支持 browser/http/observation/manual/prepare/cleanup/payment/concurrency。账号、权限、文件、业务数据、服务、查询和支付条件分别关联真实需要该条件的检查点。例如未登录拒绝付款的负向用例不依赖有效付款账号。`record_ui_dependency_check` 对共用条件只检查一次，`execution_plan` 返回可执行和缺失条件的检查点；条件恢复只释放等待，不表示业务通过。

`record_test_checkpoint` 保存真实观察、方式和证据。浏览器按钮正确而订单账本尚未验证时，用例是部分验证；只有全部检查点通过才判通过。已有真实失败仍判失败，同时显示剩余缺口。设计模式不能保存执行通过/失败。报告和 XLSX 会展示需求关联、检查点和真实/沙箱/模拟方式。

## 被测系统测试能力

`save_test_capabilities` 保存命名的 HTTP 适配器，种类为 http、observation、prepare、cleanup、payment_control。请求使用任务已保存的接口基础地址或页面 origin；更换目标后绑定失效。相对路径与方法必须有已保存文档中的原文依据。参数 Schema 必须是 object、`additionalProperties:false`，不支持引用。模板采用 `${参数名}`，路径采用 `{参数名}`；不运行用户代码或 SQL。认证头单独加密保存，读取能力和报告不会返回凭据。

业务观察由被测系统提供只读 GET 查询，例如当前订单、收款记录、权益流水和埋点。用例应比较原订单 ID、用户、金额、状态及增量，而非只看页面提示。比较规则保存在检查点 `assertions`，支持 equal、length、delta、http_status，必须有规则原文；delta 引用先前观察检查点的证据。缺少响应字段、基线或比较规则时保留部分验证。

准备和清理适配器仅在开发/测试环境使用。safe 权限不发送写入；真实业务 HTTP 写入需 maximum 权限。固定来源连接沿用现有 DNS/IP 校验、TLS 校验和禁止重定向机制，可信内网来源仅由服务器 `API_TEST_ALLOWED_ORIGINS` 配置，客户端不能自行放行。

`run_test_capability` 在发送前保存 invocation_id；相同 ID 返回原结果，不重发。结果不确定时用 `get_test_experiment` 查询并核对原目标资源。若执行期间用例、规则或报告变化，响应仍保留在执行记录里，但不会覆盖新版结果。也不会通过换一个 invocation_id 自动重试未知付款。

## 支付模拟与并发

被测应用需先提供并接入测试环境的支付控制适配器。平台向它发送 `{order_id, provider_transaction_id, scenario, event}`。适配器负责按应用真实契约产生测试通知、签名和故障控制，应用自己的订单、收款确认、权益发放和幂等逻辑照常运行。平台不创建替代订单或权益，不声称微信真实通道通过。

`experiment="payment_scenario"` 使用以下事件顺序，所有事件绑定原订单和同一模拟交易 ID：

| scenario | event 顺序 |
| --- | --- |
| cancel | cancel |
| unknown | unknown |
| delayed_success | pending（暂停；稍后显式 release_success） |
| release_success | success |
| duplicate_callback | success → success |
| out_of_order | pending → success → pending |
| entitlement_failure | enable_entitlement_fault → success → disable_entitlement_fault |

适配器参数 Schema 和 body_template 必须包含所需字段；没有适配器时显示具体能力缺口。disable 请求即使通知失败也会尝试，响应失败时必须通过执行记录检查并处理故障残留；不能仅因发送过 disable 就宣称恢复。注入成功和业务到账分为不同检查点，仍需订单/权益独立查询。mock、sandbox、real 分别保留，模拟不替代真实支付验收。

`experiment="concurrent"` 通过客户端屏障释放 2–8 路请求，记录启动时间差。用同一个资源键触发竞争，再用业务观察验证订单数和权益增量；客户端屏障不保证服务器在某条代码同时执行，也不是压测。不同业务阶段的竞争通过不同检查点安排。

## 原订单与定向续跑

人工扫码前先保存原 `order_id`、`payer_id` 和已知交易 ID 的 correlation，人工检查点记录 pending_action 和明确操作说明。页面可记录人工完成动作，但该动作不证明收款到账；后续只核对原订单，不能重新发起付款。后续结果或适配器参数不能悄悄更换原订单、付款人或交易 ID。

`resolve_rule_question` 保存明确结论与依据，返回受影响用例；旧报告不变。更新受影响预期及依据后，通过 `resume_requirement_test` 继续。确认规则不是测试通过，未修订预期时仍等待。规则改变使关联检查点及其后续检查重新验证，独立检查保持原结果。

续跑选择原用例 ID 和原因。未发布轮次保留其他独立结果；已发布轮次生成同会话的新报告轮次，只选受影响用例。continue 保留前序完成观察、原订单和来源标记，本轮不会把沿用观察写成重新执行；retest 清空所选结果和业务关联，适用于重新建立独立初态的测试。新轮次重新检查执行条件。已发布快照保持不可变，可随时对照和导出。

本次应用修改的隔离测试使用合成 PRD、本地 HTTP 服务和模拟业务数据；没有连接业务付款环境、调用付费模型或写入 PingCode。
