# 接口测试规则与部分执行（0.10.0）

本版取消模型/MCP 候选 40 条、网页方案 200 条、网页运行 180 次请求的固定总数限制，同时取消单条候选的固定步骤/断言数限制。单次 JSON 仍有 16 MiB 和嵌套深度的解析保护，请按稳定 ID 分批提交；读取候选支持分页，不代表会话总数受限。

## 用例与报告

- 不再强制每个步骤有 HTTP 状态码断言。有文档依据的业务字段、Schema、Cookie 等断言也可核对执行。完全没有预期或来源的场景保留为待确认。
- 网页/MCP 的批量采纳逐条处理，返回 accepted_case_ids 与 skipped_cases。缺口不会阻止其他用例被采纳。
- MCP 分批提交只重置新增/修改项的采纳状态。文档变化会使原采纳失效；未修改的用例不需反复采纳。
- 单例预检失败仅阻止该用例；非法全局结构、未授权目标等全局问题仍阻止请求。
- 默认在单条 5xx、网络错误和清理失败后继续其他独立用例。同一用例内的依赖步骤仍在前置失败后停止，清理仍在 finally 执行并记录成败。
- 结果分类保持真实：待确认不计为通过，清理失败使报告不完整；没有状态码断言的用例收到意外 5xx 也不能只凭字段相符判为通过。
- MCP execute_tests 可指定 case_ids，只复测相关用例。没有任何可执行用例时，可以直接发布文档/缺口分析报告，无需制造执行记录。

## 数据与运行配置

测试请求预算默认按冻结方案的业务步骤加清理步骤计算，测试请求无自动重试。CLI 用户显式设置 max_requests 时仍遵守该预算。stop_on_5xx、stop_on_network_error、stop_on_cleanup_failure 默认 false，可显式设 true 使用遇错即停模式；网页导出的环境使用新默认值。

cleanup_policy={strategy:"none",reason:"具体无持久副作用依据"} 用于只建立当前会话的登录、查询型 POST、明确拒绝且无持久数据变化的场景。它必须经过与断言相同的核对流程，并写入采纳快照。有资源变化的场景仍需独立清理或服务端提供的清理能力。

同一用例 Session 保存 Cookie，extract 将登录返回的 token 或资源 ID 传到后续步骤。测试账号与资源使用 unique 变量隔离；当前执行器不支持隐式跨用例依赖。

## Skill 分发

规范源文件为 api_test_tool/static/skills/api-test-workspace/SKILL.md，基于 Jeffallan/test-master 适配并保留 MIT 许可。按需引用 test-design.md 与 mcp-execution.md。

- MCP 工作空间与上下文直接返回 Skill 内容。
- 网页复制给 Codex 的任务消息包含 Skill URL；免安装客户端与原 MCP 使用相同工具格式。
- /static/mcp-guide.html 可查看规则，或下载 /static/api-test-workspace-skill.zip。解压后的 api-test-workspace 目录放到用户 Codex skills 目录即可。
- 本机已安装的 Skill 在后续会话可发现；当前任务也能立即通过服务端返回的规则执行，无需等待注册。

## 验证

回归覆盖真实本地 HTTP 批量执行、240 条可执行与 1 条待确认混合、保留未修改项采纳状态、业务断言无状态码、登录与提取变量、清理、单例校验/网络/5xx 故障继续、原显式遇错即停配置，以及只检查文档不发送请求的 MCP 路径。验证过程不调用外部模型 API 或推送 PingCode。
