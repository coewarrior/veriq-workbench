# 新接口只补资料与配置：Items 示例

本例通过通用 `parse_document → generate_bundle → run_bundle` 接入一个与五子棋不同的接口：
申请 Token、创建资源、提取 ID、查询资源、校验归属与内容、重复提交、删除并确认资源不存在。
测试侧新增的接入内容全部位于本目录；没有为 Items 修改解析器、执行器或通用 pytest 入口。
`tests/fixtures/items_server.py` 是被测服务的独立实现，用于提供可重置环境。

| 文件 | 用途 |
|---|---|
| `openapi.yaml` | 4 个操作及参数类型、边界、枚举、响应、Bearer 鉴权契约 |
| `requirements.md` | 明确状态码与业务预期、数据隔离和清理要求 |
| `rules.yaml` | 预期与资料位置的映射，以及 Token、提取、依赖、清理的声明式配置 |
| `environment.yaml` | 只允许 `127.0.0.1:18082` 的受控运行环境 |

在仓库根目录、依赖安装完成后，先在一个终端启动本地服务：

```bash
.venv/bin/python tests/fixtures/items_server.py --port 18082
```

在另一个终端导入资料、生成测试资产、预检并执行：

```bash
.venv/bin/python -m api_test_tool import --document examples/items/openapi.yaml --output work/items-contract.json
.venv/bin/python -m api_test_tool generate --contract work/items-contract.json --rules examples/items/rules.yaml --output work/items-bundle.json
.venv/bin/python -m api_test_tool validate --bundle work/items-bundle.json
.venv/bin/python -m api_test_tool run --bundle work/items-bundle.json --env examples/items/environment.yaml --output work/items-pass
```

预期生成 **19 条用例**：正常流程、数量合法上下界、缺参、null、空字符串、类型错误、
布尔值作为整数、数量越界、字符串过长、非法枚举和缺失 Token。正常环境执行 **47 次请求**，
19 条全部通过；3 个成功创建的资源均通过 DELETE 清理，再 GET 验证为 404。
运行目录包含冻结资产、JSON 证据和 HTML 报告。每个用例使用新的 owner，故可重复运行：

```bash
.venv/bin/python -m api_test_tool replay --run work/items-pass --env examples/items/environment.yaml --output work/items-replay
```

按 Ctrl+C 停止服务会清空所有内存数据；重新启动即完成环境重置。测试 Token 只在本轮内存中使用，
报告对 Token 脱敏，保存的变量模板和 schema 仍可用于重跑。

## 验证工具确实能检出错误

停止正常服务，然后用相同端口启动故障版本：

```bash
.venv/bin/python tests/fixtures/items_server.py --port 18082 --fault wrong_owner
```

使用同一份冻结资产执行正常流程，不更改规则：

```bash
.venv/bin/python -m api_test_tool run --bundle work/items-bundle.json --env examples/items/environment.yaml --case ITEM-FLOW-001 --output work/items-wrong-owner
```

预期命令返回失败退出码。查询仍返回 HTTP 200 且 schema 合法，但 `owner` 为 `another_user`，
跨步骤相等断言会检出不一致，报告保留预期 owner、实际值和请求响应，清理仍成功。

其他本地故障开关：

| `--fault` | 预期检出结果 |
|---|---|
| `wrong_type` | quantity 从整数变为字符串，schema 和相等断言失败 |
| `missing_field` | 响应缺少 name，必填字段和相等断言失败 |
| `non_json` | HTTP 200 返回文本，JSON 断言失败并保存原始正文 |
| `server_error` | 查询返回 503，后续业务用例被阻断，当前用例仍尝试清理 |
| `cleanup_error` | 业务断言通过，DELETE 返回 500，清理失败且整轮未完成 |

自动化集成验证不需要手动启动服务，每项测试绑定随机本地端口并在结束时销毁环境：

```bash
.venv/bin/python -m pytest tests/unit/test_items_integration.py -q -o addopts=''
```

这组测试验证本地 HTTP 全流程、冻结资产再次执行、新数据命名空间、Token 脱敏，以及上述六种故障。
它证明工具能依据已明确的契约执行测试；真实五子棋业务的预期仍应来自其自己的资料与已确认规则。
