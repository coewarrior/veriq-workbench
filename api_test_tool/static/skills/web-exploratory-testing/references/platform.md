# 平台执行约定

资源等待遵循 [共同前置与原节点阶段安排](work-stages.md)：先做当前合法可做的原场景，资源边界用完整阶段令牌，真实退出后明确 yield；原用例、覆盖、顺位与未知写入保护保持。

**默认路径：** [原生 Codex 执行](native-codex.md)。当前桌面 Codex 默认在持久 node_repl 直接使用隔离 Playwright Context，执行包自动发现依赖，不要求用户配置；旧在途保留原浏览器。平台调用止于账号分配、结果/证据同步和 S1 停止。下文标为旧 Runner 的接口只供原任务兼容，不得混入原生步骤。

## 从 Codex 同步任务附件

用户通过 Codex 下达 UI、需求或接口测试任务时，相关附件必须同步到同一个平台会话。创建时使用 `start_test_workflow.attachments`，已建会话或后续补充使用 `save_test_materials.attachments`；格式均为 `[{filename,content_base64}]`。保留原文件名和完整原始字节，不能用摘要、原文引用或本地路径冒充原文件。解析需求正文不替代附件存档；PDF/Office/图片还需读取实际内容，将有用的提取文本及来源文件名保存到 `requirements`。

已有终端时优先复用当前配对凭据和经哈希核验的免安装客户端，在本地编码，避免把 Base64 写进聊天：

```sh
python3 /绝对路径/api-test-client.py --url 测试台origin upload-attachments --project-id 会话ID --file /本次任务/需求.docx --file /本次任务/页面.png
```

`--file` 可重复指定；仅上传用户为本次任务提供的相关原文件，不扫描无关目录，不上传凭据文件。每会话最多 10 个附件、合计 50 MB，支持图片、PDF、Office 和文本。同文件名且 SHA-256 相同的文件重复同步会复用；同名但内容不同的文件分别保留。创建/补充返回附件元数据，核对文件名、字节数和 SHA-256 后再继续设计或测试；CLI 自动核对这些回执。同步失败、原件不可读取或超出限制时，明确指出未同步的文件和原因，不静默省略或声称完整存档。后续补充、回归继续使用原会话，不另建无关任务。已有会话附件可通过 `get_test_document.attachments` 或 `get_workflow_status.attachments` 回查。

本文件只说明如何把测试成果保存到平台，不重新规定测试方法。按 SKILL.md 自主开展任务；用户仅要设计时交付设计，要求测试时保留完整设计及实际执行结果。cases 同时容纳未执行设计与已执行结果，不是仅收集点击记录。工具、账号或时间不足时，适用场景仍以具体用例保存；coverage.gap 是解释缺口，不替代已经能写出的测试设计。平台接入、属性填写和证据上传不应反过来缩小业务范围。

测试开始前读取 `get_test_document.execution_permission` 或 `get_test_context.execution_permission`。`safe`、`full`、`maximum` 是用户预先选择并持久化的本轮授权。`maximum` 表示目标系统和当前授权账号/租户内所有完成测试所需的操作均已获授权，包括创建、修改、删除、上传、下载、模型调用、重复/并发、对外发送、正式发布、付款、启动真实业务和不可逆操作；不得再逐项询问，也不得仅以生产环境、风险或减少测试数据为由标未执行。仍应核对对象与目标，禁止越出目标系统/当前账号或操作无关数据。缺少账号、真机、屏幕阅读器或系统能力属于客观条件缺失，权限选择不会凭空补齐这些资源。

同时读取 `scene_retention`：`none` 为默认清理，`defects` 仅保留缺陷复现现场，`test_data` 保留本轮新建数据，`full` 完整保留本轮可控现场。以 `get_test_document.scene_retention` 的本轮持久化值为准；交接消息缺失或与它冲突时，先指出差异，不能默认为 `none` 并清理。`defects` 包括复现失败用例所需的前置数据和状态，即使此前置步骤自身通过；只清理与缺陷复现无关的本轮对象。它只影响执行收尾，不限制用例设计或测试执行；报告、截图、录屏和报告内夹具始终保留。回归轮次默认重新设为 `none`，不继承上轮选择。Codex 根据实际对象归属执行，不能把选择的意图写成已完成的清理结果。

AI 整理 UI 缺陷时必须主动确定并填写 environment、client、module，标题统一为 [环境]【B端/C端】【功能/模块】 问题描述。environment 仅为 dev/test/pre/prod/uat/staging/qa/local；client 仅为 B端/C端，表示企业业务端或个人用户端；module 是实际功能模块。先复用用户明确指定的值，再依据测试目标地址、页面角色和业务上下文确认；同一范围批量复用已确认的环境与业务端，逐条确定模块。浏览器、操作系统、桌面/移动设备写入 test_environment（例如 macOS Chrome桌面），在缺陷描述的【测试环境】中自动展示；版本、视口及真机/模拟信息仅填写实际已知值，禁止写入 client；禁止用“同上”、地址或说明句替代属性。直接使用保存回执，修正 title_attribute_gaps 中可由现有证据确定的值，无需再次读取全量用例，再统一发布，不把已知属性留给用户逐条修改。确实无法判断时保留缺失值并集中说明一次，仍生成完整报告，不猜测、不阻止生成。

## 进度与批量回写

补测任务由平台直接准备新基线；`get_test_document.retest_task` 返回任务与执行记录归属，用 `get_ui_test_cases` 获取具体设计和最新 revision。已有用例允许只保存 case_id 和变化字段，未传字段沿用本轮已保存内容，明确空值才清空。平台准备基线不代表已执行，前置检查和逐条真实判断仍由执行端完成。

必要的保存、执行和报告发布调用会自动记录进展。`update_task_progress` 只在阶段变化或新的阻塞/异常且没有这些调用记录时使用；不另加每分钟、每次点击或配合网页每 6 秒刷新的心跳。网页读取已有记录，测试概况随保存批次更新。

持续将真实观察写入本地工作记录，每条用例完成独立判定后，立即把该条变化及 `cases[].checkpoints` 用 `save_ui_test_cases` 增量保存，不等待整组完成；每批最多 200 条，沿用 execution_id 和最新 revision。单项 `record_test_checkpoint` 用于需要立即持久化的暂停/续跑边界；人工付款暂停前保存原订单关联。`run_test_capability` 已持久化的结果不重复回写。阶段切换、请求人工补充、异常中断及退出前保存待回写内容；所有前置检查、逐条判定、证据和现场保留规则继续适用。

## 从用户目标直接开始

不要求用户先在网页建立会话。新任务使用 `start_test_workflow(goal,test_kind,target_url,...)`；平台会创建正确类型的会话并返回 `project_id`、就绪状态和下一步。UI/需求任务选择所属项目后，默认使用项目已配置的登录地址作为测试入口，无需用户重复填写 target_url；仅项目未配置地址时提示编辑项目补齐，不创建无入口的会话。探索性测试无需需求文档：先侦察实际页面、形成具体用例，再执行并保存证据。已有明确会话使用 `get_workflow_status` 恢复进度；只有用户按名称指向历史任务时才用 `list_test_sessions` 查找，多个同名项不能擅自选择。

后续补充的非敏感目标、规则和测试数据可用 `save_test_materials` 一次保存。密码、令牌、Cookie 和真实个人秘密不写入该工具；登录态优先复用受控浏览器，必须人工输入的秘密只在当次登录环节处理。`start_regression_test` 建立不覆盖历史的新一轮，同时返回原用例的未执行基线和缺陷处理依据；已有依据不再额外调用 `get_defect_decisions` 重读。`finish_test_workflow` 可一次保存最后变化、等待原执行资源交还、发布最终报告并按已有设置推送；不替代真实执行与清理，不提交 PingCode。

## 需求、检查点与定向续跑

业务 PRD 使用 start_test_workflow 的 requirements 模式并提供 account_project_id、filename、content、goal，target_url 默认使用项目地址，或让 auto 依据文档结构识别；不要为了导入业务需求杜撰接口契约。通读原文后用 save_requirement_design 保存角色、规则、状态、验收条件和风险，保留准确 source_quote。自动 source_index 只是原文定位，不能当作完整设计。完整具体用例通过 requirement_ids 关联，逐项核对 traceability 和 requirements_without_cases；总用例数由业务决定。

用例中的 checkpoints 分别描述 browser/http/observation/manual/prepare/cleanup/payment/concurrency。每项至少有 id、title、kind、expected、basis；depends_on 只能指向前面的检查点，dependencies 只关联真正需要的资源。缺少权益查询接口时，Codex 判断权益观察受到的影响，页面检查和独立负向场景继续。共同资源做一次真实轻量检查，runnable_checkpoints、waiting_checkpoints 和 gaps 仅作诊断，ready 只说明条件恢复。真实观察及 real/sandbox/mock 方式随 cases[].checkpoints 批量保存，需要立即持久化的暂停/续跑边界使用 record_test_checkpoint。Codex 根据目标和全部真实证据判断父用例，并显式提交 status、actual、conclusion、ai_analysis；检查点保存只更新该检查点，平台不按检查点集合自动改判或清空父用例，不以依赖台账拒收结果或阻断资源候选。

用户要求模型或执行策略对照实验时，可在 `save_ui_test_cases` 或客户端 `finalize-ui` 中附可选 `experiment`，记录 `experiment_id`、`variant`、`model`、`reasoning_effort`、`model_source`（requested/reported/verified）、`model_source_detail`、`started_at`、`execution_started_at`、`execution_finished_at`、`tool_calls`、`tool_errors`。全部字段均可省略；仅记录计时时不需要模型字段。时间使用真实的带时区 ISO 8601 值，未取得计数不填0；省略保留旧值，单字段 null 清除该值。平台只保存执行端声明，不独立核实模型或推断质量。阶段报告展示时间来源及窗口，总报告不把单轮数据当作多轮统计。仅更新指标不改变用例、覆盖回查或执行阶段；已发布任务继续增量更新同一份阶段报告，原记录留存审计历史。实验设计和可比性见 [质量与耗时对照实验](experiments.md)。

未知规则先保存 questions，再通过 case 或 checkpoint 的 question_ids 精确关联。Codex 从用户、产品或核实后的权威规范确认规则，不能把当前表现猜成预期。resolve_rule_question 保存结论、依据和影响关联，保留已有观察与结果；Codex 判断是否修订受影响预期或结论，再用 resume_requirement_test 选择需要继续的原用例。独立观察保留；已发布任务继续使用同一 execution_id 和阶段报告，保留未涉及的结果与历史证据，不因续测另建报告。continue 保留已完成步骤及来源，显式 retest 清空所选初态和关联。报告必须说明沿用观察没有在本轮重新执行。

通过 get_test_capabilities 探查订单、收款、权益、埋点、准备和清理接口。缺少能力时给对应检查点保存 capability/observation/payment 依赖和真实检查结果，不猜接口，不删用例。save_test_capabilities 只保存有资料依据的目标内 HTTP 适配器；认证头加密保存。run_test_capability 的业务比较来自预先保存的 assertions，缺少响应、基线或比较规则保持部分验证。并发仅释放 2–8 路受控竞争，仍需独立查询真实业务增量。

支付模拟需被测系统在开发/测试环境接入 payment_control，平台只控制模拟通道事件，应用自己的订单和权益逻辑照常运行。取消、未知、延迟、重复、乱序和权益失败均标明 mock；不能证明真实微信通道通过。执行前保存唯一 invocation_id，响应不确定时通过 get_test_experiment 查询原记录，不重发。人工操作前先保存原 order_id、payer_id、已知交易 ID 和 pending_action；用户完成动作后只核对原订单，不能再次付款，人工完成也不等于收款或权益到账。

## 无新增用户步骤

资料中的 testing_skill.files 是本平台完整 Skill 文件清单，含 SHA256。必要文件从同一平台 origin 下载到任务临时目录，保持 scripts/ 和 references/ 相对结构并校验摘要。读完 SKILL.md；涉及 AI 会话/记忆/RAG 时读 ai-testing.md。不得要求用户事先安装 Skill。平台负责储存，Codex 负责执行，不代表网页服务器具备用户浏览器的登录态。

同轮和续测复用已读取、摘要一致的文件及客户端，只下载本次需要且缺失或变化的文件；testing_skill.content 已含 SKILL.md 时直接读取，不再请求同一正文。保留运行状态、结果队列和资源清单，恢复时读取变化及未完成项，不重复输出全部设计和已上传资产。

实际执行浏览器测试时，先按 [浏览器控制约定](browser-control.md) 检查工具并绑定目标标签。已有能力可完成任务就直接复用；支持交互工具时按其文档运行，不为使用本包而启动第二套浏览器。明确选择兼容路线、没有可用浏览器工具且任务允许准备依赖时运行 `python3 scripts/bootstrap.py`（Windows `py -3`），内部执行，不给用户增加环境报告或确认步骤。纯设计任务不准备浏览器依赖。Python 3.9+ 可复用执行端提供的运行时；若执行端连终端或 Python 都没有，不能假装下载成功，记录明确阻塞并完成其余工作。

文件上传先使用绑定标签的工具所公开的文件输入能力。默认原生路线不为上传擅自更换浏览器后端；以下独立 Playwright 回退只适用于用户已选择的兼容路线，原生工具确实缺失能力时保留具体缺口并继续可执行分支。若明确返回 `Not allowed` 或缺少文件输入能力，优先使用支持 `locator.setInputFiles` 的 Playwright 独立上下文；没有可用上下文时按需使用 bootstrap 准备。该上下文不继承用户 Chrome 登录态，需要登录时复用本轮同一持久上下文，不为每条用例重复登录。

原生文件选择框仅在浏览器控制约定允许前台操作且已有应用级/系统级能力时使用：先真实生成并核验夹具，点击本轮目标窗口的上传控件，用原生界面树确认文件选择框确实出现，再通过路径定位选择文件，回到已绑定页面核对已选文件、上传、解析和索引结果。macOS 可在已打开的选择框中使用 `super+shift+g`，向可编辑的路径字段写入夹具绝对路径，返回主选择框后核对文件名再点击“打开”；不要在未识别到选择框时盲发按键。首次系统自动化/辅助功能授权只能由用户在系统提示中确认；已有能力则不新增用户步骤。不要把 Chrome 的“允许访问文件网址”开关当作通用解法，也不要用文本编辑器打开文件传输 Base64。仅在目标产品本身要验证接口上传时才用服务端 API；UI 上传用例不能用直调接口冒充页面验证。上传通道失败只影响执行状态，不删除或合并已有文件用例。

上传能力检查随用例保存为 `upload_attempts`：每项为 `{channel,outcome,detail}`，三项均为文本，按实际通道、结果与依据填写，不限固定三通道或条数。`file_input`、`native_dialog`、`playwright` 及 `failed`、`unavailable`、`succeeded` 只是可沿用的描述。detail 不含凭据，不能照抄文档当作实测。有通道成功即继续业务链路，不再检查剩余回退；不可用通道只记录依据，不盲目调用或循环安装。前台控制不符合 browser-control.md 时，记录该具体限制，不抢占窗口。同一登录、环境和工具条件下可复用本轮真实检查，条件变化后重新核实。省略该字段保留已保存值，显式 [] 清空。

浏览器文件输入限制的描述不触发保存或发布门槛，不要求填满固定通道。Codex 根据已授权路线和公开能力决定必要检查，记录真实受限范围和判断依据；平台原样保存，不按关键词判断阻塞是否成立。系统授权或独立窗口登录确需用户完成时，用 pending_action/manual_step 写明实际动作。已有历史报告保留真实缺口。


脚本检查现有 Node、当前项目/全局/常用 npx 缓存的 Playwright、浏览器启动、输入、点击、截图与关闭。版本号不同不会触发升级；能力可用立即返回。额外安装位置可用 `UI_TEST_PLAYWRIGHT_MODULE` 指定，不扫描整个磁盘。

仅在缺失时准备依赖：优先补现有包对应的 Chromium；仍不可用才在用户 api-test-ui 缓存准备后备 Playwright。Node 缺失时下载官方 Node 22 发行包并校验 SHA256。锁避免并发重复安装，浏览器复用 Playwright 官方缓存；再次执行先探测，已有包不因后备版本变化强制更新。不改全局依赖、不使用 Docker、不执行 sudo。网络/系统库/权限问题如实记录，不能循环重装。临时目录中的 Skill 文件很小，不是重新下载浏览器。

bootstrap 输出给 Codex 的 JSON 为 `{node,module,channel,browser,reused,video}`，不是用户交付物。需要录屏时加 `--video` 验证真实录制，必要时只补 FFmpeg；网络受限则截图继续可用，记录瞬态证据缺口。用返回的 node 运行任务脚本；`require(runtime.module)` 提供标准 Playwright API。需要脚本化取证时 `require('./scripts/evidence.cjs').runCase(runtime,{caseId,directory,recordVideo:true},async({page,capture})=>{ ... })`。选择可见浏览器用 headed:true；新上下文无用户 Chrome 登录态，不读取用户 Cookie，确需登录时请用户在该窗口完成。

## 先保存设计基线，再执行并持续补充

用例 priority 使用 P0/P1/P2/P3：P0 为核心关键流程或重大业务/数据安全风险，P1 为重要功能和高影响风险，P2 为常规功能及一般风险，P3 为低影响细节。按目标、需求和实际功能判断，与缺陷严重程度分开；信息不足保留空值，不按通过/失败自动定级，不改变覆盖范围、执行顺序或保存/发布权限。历史未设置等级不自动补写。

平台阶段是导航与进展展示，不要求用户逐项确认。Codex 可先侦察页面认识真实功能；已有用例基线直接复用；新任务先保存本批必要具体设计及执行方式，准备完成立即执行 AI 可完成的部分，不等待无关准备或反复扩写计划。完整目标范围继续维护。执行中的新发现随时补入同一轮，不因已有基线停止扩展。

1. `get_test_document`/`get_test_context` 读取当前目标及完整资料，分页读完需要的内容。旧报告仅是回归基线，不是本轮实际结果。
2. `save_ui_test_cases(project_id,cases,coverage,review_notes)` 分批保存设计基线，返回 execution_id 和 revision。基线用例填写具体前置条件、数据、步骤、预期和 executor，状态先用 not_run；不能提前填通过。每批最多 200 条仅是传输分页大小，不是目标条数。页面侦察仍无法确认的细节如实标注待核对，不编造规则。保存基线后即可执行，不需要用户审批；发现新场景时随时追加或细化，数量由业务行为和风险决定。每条用例完成立即回写同一 revision 链，不为每次点击单独保存；长任务在阶段边界、异常前后和退出前落盘。
3. 后续保存携带同一 execution_id 和最新 revision，完整更新同一 case_id。冲突先重新读取；超时先用 `get_ui_test_cases` 核查是否已经保存，不能盲目另建一轮。如实记录规则不明/阻塞和清理结果。收尾后用同一工具回写 `scene_outcome`：`status` 为 `cleaned`/`retained`/`partial`/`unverified`，`note` 简述事实，`items` 为本轮对象数组，每项包含 `case_id,name,kind,state,reason`，state 为 `retained`/`cleaned`/`unverified`。逐条 `cleanup` 或报告 `summary` 不能替代此可选结构化现场记录；必须依据本轮真实对象及核验结果填写，不自动从文字推断。可用 `cases:[]` 单独更新；结果未回写时报告显示“未记录收尾结果”，不会默认算已清理，不新增发布门槛。
4. 将脱敏截图/短 WebM 录屏/实体测试夹具关联同一 execution_id、case_id、step、captured_at。多个文件优先使用 `upload_ui_test_assets` 或配套 `upload-batch.py`，一次传输最多 50 个且可继续追加；只有单个文件时使用 `upload_ui_test_asset` 或 `upload.py`。批量方式逐项使用相同的数据格式、大小和真实用例 ID 关联校验，整批校验通过后才保存，只减少网络与存储初始化，不改变证据内容和用例关联。case_id、step 明确资产归属；Codex 判断资料与用例的业务关联，并为读者说明实际用途。平台不要求文件名再次出现在用例文案，也不据此拒绝上传、用例更新或发布。多个用例真实共用一份资料时，分别显式关联即可复用。无实体文件则 test_data 直接包含可复制输入、边界值、数据建立方法。脚本直接读取本地文件，不把大段 Base64 放进聊天。客户端从同一平台 `/static/api-test-client.py` 获取并按 agent-tools.json 的 client_sha256 校验，凭据复用当前配对连接。语法见脚本 `--help`。
5. 回查可穿插在探索与执行中，重要且可执行的遗漏继续验证。完成约定目标或确有范围/执行限制需要交付时，使用 `publish_ui_test_report` 创建或更新本任务唯一的阶段报告；review_notes 保留实际扩展及剩余风险，不要求特定顺序或句式。summary 写真实覆盖、未完成及清理结果，不把一次发布称为全量测试完成。报告默认展示总结和缺陷；完整数据另有“用例与数据/导出 XLSX”。发布后续测仍使用当前 execution_id/revision，变化增量追加到同一报告；未涉及的用例保持，原结果与证据留存审计。相同数据重复发布幂等，不重复推送。

实际执行还应读取 [高效执行与等价取证](execution-optimization.md)：一次预检后把用例按共享初态、资源冲突和依赖关系分组；事件等待代替固定等待；独立分支可安全并发，有状态链路保持串行；测试数据批量准备，失败时再加强取证。优化不能删用例、减断言、伪造通过或降低清理标准。

### 共同前置诊断与独立判断

保存设计基线时，为真实共用的前置条件写入 `cases[].dependencies`。这是 AI 记录的关联，不要求用户重复填写。示例：

```json
{"case_id":"AUTH-01","dependencies":[{"key":"hr-admin-login","title":"HR 管理员账号不可用","kind":"account","environment":"test","tenant":"测试企业 A","role":"HR 管理员"}]}
```

同一必需资源复用相同 key；kind 支持 account/permission/file/data/service/observation/payment/capability/other。目标页面、环境、租户、角色、kind 和 key 共同确定分组；账号/权限必须明确租户和角色（确无租户写“无租户”）。不同格式的测试文件、不同服务入口或不同故障条件使用不同 key，不因错误码或措辞相似就归为共同阻塞。只有某项确实是本用例必要前置条件时才关联；预期验证登录失败、权限拒绝、损坏文件等逆向用例不能关联“登录成功/文件有效”为必须条件。

阻塞继续按原有执行逻辑判断：AI 可安全构造的数据先实际准备并核验；只在真实执行条件无法满足时记录客观阻塞。报告的数据补充入口仅用于补充确实缺少的现有资源，不改变阻塞范围、结果语义或原有自动生成能力，也不能把用例 test_data 清单整体转成用户准备任务。

save/get 返回 `dependency_groups` 和整个轮次的 `execution_plan`。按 `dependencies_to_check` 对共同条件做一次轻量真实检查，用 `record_ui_dependency_check(project_id,execution_id,revision,dependency_id,status,observed,method)` 保存，status 为 blocked/ready。缺少账号只核对是否有该角色的可用凭据或登录态；登录/权限检查使用真实页面；服务故障先只读确认现状，不再次上传或触发相同生成请求来检查同一个故障。

blocked 保存共同条件的真实检查，`skipped_cases` 等计划字段是诊断建议。平台不自动修改关联用例或检查点状态，也不以该台账阻断资源候选。Codex 结合实际条件判断哪些业务步骤不能推进，显式保存相应用例结果并继续独立分支；复用相同条件下的检查，不逐条重登、重复上传、等待或制造重复失败。每次写入使用返回的最新 revision。

条件改变（补充/修改数据、服务恢复、角色/租户/目标改变）后，对相应共同条件重新检查一次并记录。ready 只更新条件诊断，不自动清空旧阻塞、观察或把用例改为 not_run/通过。Codex 核对变化对原业务的影响，显式保存需要修改的结果；已经判定 passed/failed 的用例不因诊断变化自动重做。新轮次不继承上轮检查结论。可缓存同一 dependency.id 的真实检查并在条件变化时刷新，但不要用脚本固定状态分支代替 Codex 判断；检查结果仍沿原入口写入平台。

发布后报告保留共同阻塞检查和完整用例。报告内补充一次共用数据即可同步到同组受影响用例，以后修改也同步；不同阻塞条件可以分别保存账号和文件，执行端按 case_inputs 和 dependency_inputs 读取各自数据。特殊用例可以选择“仅此用例”使用单独数据。补测任务只执行选定的原编号，保存独立新报告。老报告没有结构化依赖时，不根据自由文本臆造自动关联，可继续手动批量补充；后续真实检查时建立明确关联。

发布前读取本轮资产清单，逐条检查 failed 用例的现场截图。缺陷仍可见且工具支持截图时，必须先 capture 并上传为 screenshot；没有截图时在 actual 中写明无法取证的客观原因。不要把“忘记截图”当作限制，也不要用恢复后的正常页面补拍冒充故障现场。

### 覆盖思考的保存方式

工具完整契约见同源 [agent-tools.json](../../../agent-tools.json)。cases 的字段为文本：case_id、scenario、module、environment、client、test_environment、priority、executor、precondition、test_data、steps、expected、actual、conclusion、ai_analysis、recommendation、status、rule_basis、method、cleanup、executed_at、action_type、action_required；多步/多轮内容使用换行，不需增加用户填写步骤。`ai_analysis` 是报告顶部给非测试人员看的解读，由 AI 写入和更新，不是新的用户填写项；按 [报告规则](reporting.md)及保存/读取结果的 `coverage_check.ai_analysis_guidance` 写清功能结果、影响和未知部分，技术细节留在详细记录。平台原样保存，不按关键词替换或猜测历史报告的原因。executor 由 AI 填写“AI”“人工”或“AI/人工均可”；标人工时在 precondition 或 method 中说明需要的角色、设备或判断条件。未执行时 actual、executed_at 留空，未知环境/业务端留空，不用说明句代替属性。预期、实测和结论各以一句明确判断开头；结论指向本用例约定的成功标准，同时说清后续链路失败是否让业务目标无法完成。实际差异、复现次数、影响和复测情况就近记入 actual；actual 不写“截图已关联”“已截图”“缺陷标题”等提交或证据管理元数据。截图、视频和数据文件通过资产工具关联，缺陷标题由环境、业务端、模块和问题描述生成，不虚构证据字段。失败草稿由保存的用例生成。

coverage 是可增量保存的数组，每项由 AI 自主确定功能、规则或风险粒度，不要求五类配额或固定场景列表：

```json
{"coverage_id":"upload-retry","feature":"解析失败后的重试","entry":"资料列表 / 失败状态","considerations":"根据页面重试提示验证恢复和重复条目副作用；结合异常恢复与状态迁移思考","case_ids":["UPLOAD-RETRY"],"gap":""}
```

按 coverage_id 合并，省略 coverage 不改变已有笔记；同项更新提交完整字段。尚未设计时 case_ids 可为空，gap 写具体遗漏或缺条件。coverage 可以先存、与用例同存或探索后补存，也可以 cases:[] 只更新笔记。先依据原资料列出已知功能范围，再分批展开具体用例；不要求开测前写完全部设计，也不只用已写用例反推范围。完整规则见 [覆盖设计](coverage-design.md)。

状态表达事实：passed 是该场景的必要断言均已验证；failed 是已观察到有依据的预期差异；partial 是只验证了其中一部分、没有已确认差异；blocked/not_run/pending_rule 分别保留用户无法就地解决的客观阻塞、未执行与规则不明。只要下一步是要用户做决定或完成人工步骤，就使用 pending_action，并填写 action_type=authorization|manual_step 与 action_required；报告操作按钮只保存确认，不立即创建或执行单条续测；可集中确认后，在补测区选择未完全通过用例，一次发起同会话批量补测。执行端读取本批次 confirmations 和 resolved_questions，沿用已确认范围及原业务对象，不重复索要相同确认或重复付款；确认不等于测试通过。不得既写“需用户确认”又标 blocked，也不得只写 actual 而不提供可操作状态。失败和未测不要混成一个含糊结论。平台仅从 failed 生成缺陷草稿。

save/get 返回的 coverage_check 只提示无对应设计、引用不存在、缺少复现内容、剩余状态和回查记录是否过时。它不设固定用例数、不判定语义覆盖、不拦截真实结果发布。AI 根据实际需求处理提示：补充、复核或说明真实缺口，不为消除提示而凑数。review_notes 写发现和补充的具体场景、依据及剩余风险；之后更新用例/清单会提示重新回查。旧记录仍可读取发布，不伪造历史覆盖。

测试数据与用例按中文名称就近关联，完整输入、轮次、边界单位、创建与重建方法保持可查；实体夹具上传到对应用例，成为报告内可查看或下载的测试数据。AI 能安全构造的空文件、未知扩展名、截断/损坏内容、边界大小等数据应先真实生成和核验，再上传并执行，不能只保存文件名后跳过。精确格式/大小/编码需要真实文件或可验证生成器。标识按运行隔离，未知初态先检查，不清空共享数据。交付前检查输入索引、夹具链接、步骤、预期和证据可读可复现；展示精简不删除这些数据。上传失败保留恢复信息；收尾仅清理本次有归属的临时数据。

业务边界文件超过平台夹具上传上限时，保留实际测试大小；可上传小型确定性生成脚本，或在 test_data 写明完整可重建配方、编码、精确字节数及校验方法。执行时核验生成文件，未生成则如实标明；不缩小业务边界迁就平台上限，也不把仅设计的配方冒充已测文件。

## 截图时机与限制

- 取证与上传分开处理。优先用当前工具文档支持的文件输出或资源导出，再由 upload.py 读取上传；脚本化 Playwright 使用 screenshot({path: ...})。浏览器控制返回内存图片不等于无法上传：若当前 JavaScript/Node REPL 的 `tab.screenshot()` 或 `target.getScreenshot({emit:false})` 返回 `Uint8Array`，就在同一次 REPL 会话中用 `node:fs/promises.writeFile` 写入权限为 `0600` 的任务临时 PNG，再立即调用 `upload.py` 关联当前用例；上传后删除该临时文件。示例：`const bytes=await tab.getScreenshot({emit:false}); const fs=await import('node:fs/promises'); await fs.writeFile(file,bytes,{mode:0o600});`（增强浏览器使用 `await tab.screenshot()`）。不需要用户保存截图，不把 Base64 写进聊天或文本编辑器。只有内存字节也无法写入临时文件、截图 API 失败或页面现场已消失时，才记录具体证据缺口并继续其他验证；上传受阻不等于产品失败，不重开未登录浏览器冒充原现场。
- 每个关键操作后检查断言；发现差异立即 capture，先取证再恢复或重试。截图描述写采集时的状态。
- 瞬态弹窗、跳转、短暂黑屏等在触发前启用短录屏；结束 context 后视频才完整。录屏不是逐帧无损采集，不能保证任意瞬间都捕获。必要时从真实视频提取对应帧并写明时刻；没有捕获到就说明缺口。
- evidence.cjs 在失败时自动截图，并在 finally 关闭本次上下文和浏览器；捕获的是断言失败时，不把它称为精确报错瞬间。浏览器崩溃时可能无法截图，以已有记录为证。
- 截图 5 MB、测试文件 100 MiB、短 WebM 20 MB 是传输限制。长视频按本用例分段或截取真实故障区间，不丢失时间关系。只上传必要证据，禁止上传账号密码、令牌、Cookie、无关真实个人信息或未脱敏 trace。
- 报告内图片自动带入 PingCode 审核框，沿用现有截图数量限制；可手动调整后提交。视频仅报告内查看，不伪装成图片。
- 上传确认后清理本次临时材料；上传失败保留本次专属临时目录供恢复，报告中不要留下不可访问的本地路径作为唯一证据。

实现参考：[Playwright Library](https://playwright.dev/docs/library)、[Videos](https://playwright.dev/docs/videos)。
未执行说明：先按 SKILL.md 回查并执行所有仍可推进的用例及关联步骤，不能用填写理由代替执行。发布前每条 not_run 必须填写 not_run_reason，具体说明已核实的限制、检查路径及本轮为何无法继续；设计基线阶段可暂空。若写“上轮通过，本轮未选入回归”，必须核对并注明真实的上轮报告/轮次、用例编号及本轮范围依据，不自动推断上轮通过，不把上轮结果计作本轮通过。缺失原因时明确标为未记录，不阻止报告生成。

- 文件超过 10 MiB 也应上传实体测试文件；单文件最多 100 MiB。大文件逐个上传，避免合并后超过请求总量限制。上传失败必须明确标注附件缺失，不得只留下文字说明却声称数据完整。已发布报告可通过原 execution_id 补存 fixture，独立记录补存时间；原始报告、执行记录、截图和视频保持不变。

## 阶段报告与总报告

一个任务只有一份阶段报告。首次 `publish_ui_test_report` 创建，续测复用同一 project_id、execution_id 和最新 revision；save_ui_test_cases、检查点和证据的增量保存会自动刷新已发布报告，后续发布仍返回相同 report.id/URL，不拆成多个阶段。未涉及的用例、原缺陷身份和全部历史证据保留，原报告版本留在审计存档。明确新建回归/补测任务使用其独立 project_id，拥有自己的唯一阶段报告。返回 `report` 和固定入口的 `total_report`。总报告由平台自动汇总同一会话已发布阶段，按用例 ID 采用最新保存的结果及其完整检查点，并关联原阶段证据；未在新阶段出现的用例保留已有结果。它不是一次新的执行，不把跨阶段统计称为本轮通过。续测增量保存后阶段报告和总报告自动更新。保存真实回归结果后，平台自动把原缺陷同步为回归通过/回归失败，包括未提交 PingCode 的缺陷；未执行和不完整验证不能判通过，人工拒绝/暂缓决定优先保留。无需执行者另行修改状态，也不会自动向 PingCode 写入。交付时先给总报告链接，再给本次阶段报告链接；不为生成总报告重复保存用例或重新测试。

整理失败用例时先按 [可独立复现的缺陷步骤](defect-reproduction.md) 将 steps 补成实际操作路径，再保存结果；保存、读取和发布返回的 `coverage_check.reproduction_guidance` 提醒同一要求。 同时回查 `coverage_check.reproduction_gaps`，逐条把 steps 补成测试和开发均可执行的路径；不能带着“沿用已登录账号”等简写发布。缺陷草稿直接沿用 steps，不会替执行者猜补点击、输入或焦点。用户要求更正已发布报告时，可用 `correct_ui_test_case` 更新说明并保留审计记录；它不会重新执行测试或提交缺陷。

人工介入前保存可选 `action_context`（用例或 checkpoint）：`page_url,page_title,browser,tab_id,step,object,success_condition,resume_hint`，均为文本。保留原页面和必要会话，完成后从暂停位置核对并继续；完整约定见 [人工操作与原现场续测](manual-action-resume.md)。保存/读取/发布的 `coverage_check.manual_action_guidance` 和缺失现场提示保持同一要求。旧报告仍可读取，不自动猜测或补造链接。


### 缺陷正文中的解读与建议

缺陷正文只增加“AI 解读”和“建议优化”两部分：ai_analysis 说明现象、影响及原因，区分现场事实、已核实的代码或日志依据、推测与未验证边界，根因未查明时明确说明，不另设原因分析栏目；recommendation 按条写针对该问题的修复方向、交互改进和回归关注点，不能把建议当成已实现或已验证。两项均为文本，随描述展示、复制并供人工审核后提交 PingCode，不新增生成按钮或自动模型调用；不为补分析擅自扩大测试或排查范围。
旧报告缺失的分析明确标为未记录，不猜测补写；原始证据、状态和人工编辑保留。


## 探索与回归并行

同一测试会话允许探索和历史用例回归并行。发起回归或报告补测会返回独立轮次的 project_id；所有资料、execution_id、revision、进度、现场设置、证据和发布读写均绑定该 ID，不再用原探索会话的当前执行。新轮次作为原会话的关联轮次展示，报告仍汇总到原总报告；各轮历史证据不覆盖。MCP 整体回归和定向补测都复用已准备的原用例，不手写重建基线；所选编号直接传 case_ids。探索仍边执行边补充真实发现。

每个聊天使用固定 UUID 作为 holder_id，并使用独立本地工作目录。免安装客户端在 connect 及后续每次调用都显式使用同一个本轮 --credential-file /本轮私有目录/credential.json，避免重新配对覆盖其他聊天的默认凭据文件；禁止把凭据目录放进 Git。旧独立浏览器任务需要协调共享资源时，调用 coordinate_ui_resources(operation="acquire") 一次申请整段操作所需的全部资源；新原生任务的已分配账号沿原账号入口管理，不重复申请同一账号，不逐动作调用。资源标识如下：
- account:<目标origin>:<稳定租户/账号ID>：包括准备、读写、断言和清理的整个业务链。即使不同标签，共用账号也必须共用这个 key；真正独立的账号可并行。
- tab:<主机>:<浏览器>:<真实标签ID>：绑定明确标签或页面；独立上下文不要复用他人的驱动、目录或标签。
- native:<主机>：调用原生点击、键盘、切焦点、系统文件框前必须占用，同一主机不因分窗口而省略。

key 只含稳定非秘密身份，不含密码、令牌，不用随机后缀伪装隔离。账号身份尚不明确时不能猜一个独立 key；先在已绑定页面只读确认，无法确认则串行处理对应共享账号。acquired=false 时没有获得资源，不执行该操作链、不报业务失败；继续独立设计/工作或在对方释放后重试，不反复抢焦点。获得资源后核对前置数据，结束并确认没有在途操作后用相同 holder_id/resources 调用 release。异常也先核对动作停止，再释放；不能释放别人的占用，系统不靠超时自动抢占。

仅清理本轮创建并可确认归属的对象。现场保留策略仍以本轮 get_test_document.scene_retention 为准。完整保留的另一轮数据不可删除；同一数据的断言必须在自己占用期间重新读取。平台资源占用是执行器协作协议，不能拦截绕过协议的外部浏览器工具。已运行旧任务不热迁移、不自动抢占：先保存旧现场，再按新版交接明确轮次和资源后继续。

**旧 Runner 路线的共享探索兼容说明（不作为默认原生浏览器的开测步骤）：** 共享探索由平台自动接入实时服务，用户只配置项目账号，不填写规则、会话兼容标记或选择器。遵循 `context.exploration_guidance`：有已审阅适配时复用；否则 `exploration_bootstrap=true` 的首成员先正常登录，在页面就绪后从 `navigation_links` 选择 `context.exploration_modules` 对应的本轮实际入口，调用 `prepare_exploration`（当前聊天为 `browser_action=prepare_exploration`，后台为 browser 的 action），传 `parameters={entry_urls:[实际URL,...]}`。没有直接链接的入口先在原浏览器正常打开，使用已观察地址。平台在独占账号下自动核验真实页面、请求和并行会话，生成本批次请求规则；执行者不自行提交规则批准共享，不要求用户进行技术配置。此自动核验接受用户已确认的剩余副作用误判风险，不作为业务用例通过证据。共享成员的登录态由平台按批次注入独立浏览器，直接导航到 `shared_policy.entry_urls` 对应模块，不重复登录或导出 Cookie。已审阅适配的 independent_login 沿原正常登录方式执行。准备只在用户已启动的任务中进行；停止或禁止业务测试时不得运行。`continue_exploration=true` 的回执保留真实快照和待独占分支，继续其他可共享探索和设计；未完成的分支不记失败或通过。共享探索设计完成后在真实阶段边界用原 `request_resources` 转独占；仍需独占才能继续探索时用 `exclusive_exploration=true`，保留持续探索、增量补充和逐条判定。普通独占账号保持连续执行，平台负责会话和资源交接，不增加用户设置或逐步远程核验。 默认原生路线不调用 prepare_exploration，不导出/注入 Cookie，也不把未经验证的原生浏览器说成已受 Runner 请求策略保护；用户已允许原生探索共享账号、由 Skill 约束并接受无逐请求拦截风险；共享成员在需要写入或进入执行阶段时申请独占，账号共享与转独占以平台实际分配为准，不在每个动作前请求平台。

严格遵守模块分工：用户已列出具体模块时，沿现有模块登记入口保存完整模块树；每个独立叶子创建或续用自己的 Codex 会话，不使用子 agent 合并业务模块，不要求用户手工另开聊天。大目标按实际页面和业务独立性拆分，拆分不缩减模块内覆盖；登记结构仍为 `{key,title,scope,depends_on,locks}`，依赖引用模块 key，实际共享对象保留原业务锁。实际会话能力不足单独说明，不把子 agent 槽位上限当模块并发上限，也不默默改成串行并称为并发。协调者不占业务账号；每个执行者使用稳定 holder_id、明确 node_id、实际 executor_ref 和独立本地目录，只写自己的 project_id/case_id_prefix，父聊天汇总。默认按 [原生 Codex 执行](native-codex.md) 取得账号后直接用原生浏览器工具；无账号保存位置并结束回合，不轮询、不宣称业务已开始。收到已核实的资源变化且具备实际会话唤醒能力时才续用原会话，否则如实说明待唤醒，不自建定时模型轮询。依赖仅约束真正相关的业务链，共享前置按消费者生命周期回收；原设计、结果、证据不因拆分丢弃或重跑。停止采用已选 S1：平台停止调度，用户在桌面停止对应会话，再确认本任务浏览器动作已结束后交还账号；不得把平台已停止说成全部桌面会话已取消。旧 Runner 的派发/退出协议仅对原 Runner 任务继续适用；后台路线须用户明确选择。

## 正常会话的原生执行入口

新任务默认 `execution_route=native_browser`，使用现有 `direct_test_session` 的 `claim/context/credentials/record/finish` 管理账号与结果；先执行 native-run-kit 默认生成的 environment_setup，再沿原准备分配账号，随后直接使用持久 Playwright Page，不调用 `browser/result/channel`，不启动 Runner 或心跳/领取轮询。`context` 和已读取资料复用，不每动作重读。用户已允许原生探索共享账号，仅由 Skill 约束操作，并接受失去逐请求拦截后的剩余风险。账号分配仍由平台处理；共享成员只执行探索约定内的操作，需要写入或进入执行阶段时在该真实边界申请独占，不为每个动作查询平台。不要把 Skill 约束说成旧 Runner 请求拦截仍然生效。

结束浏览器控制后，原生 `finish` 使用 `arguments={browser_stopped:true,reason:真实核对依据}`；该字段来自执行者报告或用户实际确认，不代表平台观测/强杀了桌面会话。需要 S1 人工停止时列出 pending 的实际会话，在桌面停止并核实原浏览器动作结束后再确认，未确认不伪造释放。具体步骤见 [原生 Codex 执行](native-codex.md)。

## 旧 Runner 会话的兼容入口

本节仅适用于原 `local_browser`/`managed` Runner 任务。不能为了复用旧协议把 `native_browser` 转回这一路。

连接和读取资料不启动测试。用户给出目标后，原 Runner 任务使用 execution_route=local_browser。当前 Codex 使用 direct_test_session：claim 领取同一平台队列的任务与账号；context 读取原目标、Skill、证据及分配账号；credentials 只取所分账号用于自行登录；browser 发起无界面浏览器操作，result 按同一 request_id 查询回执。浏览器运行在平台自动提供的执行机或已有配对执行机，来源见 context.execution_host；用户无需为平台执行机安装或配对。当前聊天是执行者，不另启动后台 Codex，也不占后台模型额度。无账号或浏览器容量时明确排队原因，保存已有准备和续测位置后结束当前轮次，由协调者在资源可分配后唤醒，不自动改走后台。账号密码不写入说明、用例或报告。操作响应丢失沿用原 ID 查询；未知业务提交先读页面核实，reconcile 保存依据，不盲重试。用 record 保存原有具体用例与证据，按 checkpoint 保存进度；需要人工时 wait 保存原因并保留浏览器，在当前聊天提出问题，用户回答后 continue。结束调用 finish，等待确认浏览器退出后回收账号和生成最终报告；失败、阻塞、验证未完成如实保留。只有明确要求后台时选 managed，当前聊天只查询后台任务，不建立第二个执行者。两条路线共用账号租约、排队、业务资源锁与历史，保留完整探索、持续增补、范围、独立判定、现场保留和既有报告规则。


一个项目代表一个产品，只维护一个 `login_url`，项目下多个账号共用该地址；创建测试会话时自动使用该地址，无需重复输入。业务项目 `account_project_id` 与测试会话 `project_id` 不同：用 `list_account_projects` 定位用户指定项目，创建会话时必须传入；没有项目时提醒用户在项目管理中添加产品与登录地址，不猜测归属。账号密码可不提供。已有会话可用 `bind_session_account_project` 关联；子轮次继承归属，原用例与报告范围不变。

后台执行且已提供账号密码时，平台先独占分配项目账号，由执行 Codex 使用专用 `account_credentials` 工具取用该账号凭据并在绑定浏览器中自行登录。`needs_login`、未识别租户或角色不构成人工登录前置要求；不要让用户为了解锁排队而先手动登录。仅在执行者实际遇到验证码、扫码、二次认证或凭据错误等无法自动完成的情况时请求必要协助。身份与权限在实际执行中核对，未观察到的租户、角色不得编造。凭据不进入公开状态、用例、报告或截图；账号独占、任务停止与未知操作隔离仍然生效。

直接执行收尾：阶段报告仍用 publish_ui_test_report 保存或更新；本轮确实结束时调用 finish_test_workflow（可传本轮 execution_id 核对），即使有失败、阻塞、未执行或未验证项也提交真实最终报告。finalize-ui 客户端收尾同样使用此结束入口。仅保存阶段报告不触发直接执行的自动推送；结束后按既有自动开关推送，结果相同的重试不重复发送。人工介入仍在当前 Codex 聊天提出，保留原页面、对象和步骤，收到答复后核对现场再继续。


### 原设计与结果复用；旧 Runner 回执兼容

严格遵守：已有设计只读一次并复用，不为报告重跑业务或重写整份设计。`start_regression_test.prepared_execution.result_template` 已提供本轮结果填写结构；CLI `call start_regression_test --output-file start.json` 会直接落下 `design.json`、`results.json`、`browser.json` 并返回路径。`browser.json` 可用于原 `direct_test_session --base-args-file`；排队仍按原回执续接，不另建任务。重复启动回执不会覆盖已填写结果。

结果仅提交 `case_id` 和发生变化的实际字段。已有检查点用 `checkpoint_updates=[{id,status,actual,verification_mode}]`，未更新检查点和原预期/依赖保持原样；验证方式仍由实际执行决定。不要为了格式复制整份 checkpoint，也不把工具成功当业务通过。

最终 `finish_test_workflow` 或 `finalize-ui` 可以省略 summary/title，由平台按真实结果、未完成检查点和 scene_outcome 生成总结。仅旧 Runner 已有直接浏览器回执使用 `evidence_refs=[{case_id,lease_id,request_id,step}]`：平台从本轮已保存回执生成 JSON 观察证据，和最后结果一起保存；无需下载再打包上传、改测试输入引用或再查询 revision。它不执行任何浏览器操作，不补造断言，不把截图字节当文本证据；确需的原截图仍沿原截图入口保存。

本地外部 JSON 观察证据使用 `kind=observation`，不再冒充 `fixture`。fixture 用于真实测试输入，通过 case_id、step 显式关联，由 Codex 核对用途，不要求文件名出现在用例文案中。清理仍按真实现场执行，不能自动标为成功；记录保留对象和失败原因后直接结束，不为补写总结再次查页面。


### 已有记录的续测模块登记

网页可能先创建只有 `session` 节点的新任务，再由协调者收到具体模块目标。已有用例时仍沿当前任务的 `start_session_test(modules=...)` 登记，不另建竞争任务，也不用新回归入口绕过冲突。此登记仅适用于原占位尚未领取、没有执行尝试或租约且任务仍允许运行的情况；已领取、暂停、停止或有在途执行者时，继续原安全交还和控制流程。

续接既有模块的条目在原 `{key,title,scope,depends_on,locks}` 上可加 `source_node_id`。ID 从原 `get_managed_test` 的节点或当前返回的 `dispatch_view.continuation_modules` 只读候选取得；网页先创建且未传 `modules` 时也会提供候选，由协调者完成映射，不要求用户配置。省略 ID 时仅按同 owner、同会话 project 下已确定来源任务内唯一的稳定 `key` 自动匹配，不能按标题猜测或跨任务混配。无法明确映射仍返回 409；从原入口的 continuation_modules 读取候选 ID，核对来源后补齐正确 `source_node_id` 再登记，不能反复提交同一失败参数或改走全量重测。

成功登记的新叶通过 `continuation_source` 绑定原 project、execution 和 case ID；领取与本地准备使用平台返回的新节点绑定及 `assignment.resume_record`。旧模块项目的 managed 归属不改，旧任务记录仍可查询；不复制用例、不清空状态或证据。继任绑定后，旧已退出 holder 的补报告写权限失效，不能由两个代际继续写同一记录。沿原轮推进未完成断言及新增授权范围，历史通过保留原事实，不重跑、不改算本次新通过。用户明确要求新回归时仍走原独立新轮入口，不使用此续测绑定。原 owner、父子归属、未决操作、修订、账号与停止边界，以及报告待补和完整覆盖规则继续有效。

### 模块派发与退出回执

模块分工与四类纠偏节点统一见 [协调职责](coordinator.md)。先创建或续用真实独立会话取得实际 ID，再沿 `direct_test_session(action="dispatch")` 登记原节点、`dispatch_id`、`holder_id`、`executor_ref`，最后把正式执行包发到该会话；登记成功不能代替实际发送。原退出与交接回执沿现有原生链路处理，不另加逐动作检查。

平台验收首先核对原约定的链路；探索池、派发或停止出现平台故障时停止受影响验收，保存平台错误和未验证内容，不靠继续跑业务替代平台验收。用户明确停止业务测试时不恢复。

排队未分配租约（lease_id=null）时，保留原 task_id/node_id/holder_id/dispatch_id 和顺位，停止本地领取循环并结束当前回合。原生路线收到 `resource_wait.end_turn=true` 就直接结束回合，不再调用旧单节点 pause/resume，也不轮询；实际资源可用且存在已核实的唤醒入口时才唤醒原会话领取。只有旧 Runner 路线继续原单节点暂停、核实与恢复约定。旧路线 action=wait 只用于已有租约的原浏览器等待人工操作，不是排队等待；不要因此反复报缺少租约或重新创建任务。

原生资源交还后的 `finish` 响应中的 `handoff` 按 [原生 Codex 执行](native-codex.md#账号交还后的持久交接) 处理：有效 `pending` 返回现有 `send_message_to_thread` 及完整 `message_arguments`，执行者只在真实生命周期边界通知一次，明确成功后补记 `handoff_notification`；未知响应不自动重发。协调者沿原 `dispatch` 的 `arguments.handoff_ack={task_id,node_id,event_id}` 消费，可省略 `modules`，再按原节点、顺位和范围续接。消费与后续 `claim` 获得账号分别保存；普通无协调绑定单模块不制造事件，有派发但无真实绑定为 `unbound`，不把本地回执或账号释放当成通知送达。
