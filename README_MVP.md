# 探真 VERIQ · 资料驱动接口测试 CLI

这一版已打通：**Markdown / OpenAPI → 带原文依据的规则 → 冻结用例 → 前置与鉴权 → 严格断言 → 清理 → HTML / JSON / Allure 报告 → 按编号重放**。

入口是命令行，HTML 是可离线查看的执行报告。生成器为 `rules-v1`，不调用模型，不需要 API Key。本文介绍规则生成 CLI；平台网页及 Codex 接入见 [README.md](README.md)。

## 安装与本地验证

需要 Python 3.11+。依赖由平台的 `pyproject.toml` 和锁定文件管理。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-mvp.lock
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python -m pytest
```

Windows 将 `.venv/bin/python` 替换为 `.venv\Scripts\python`。默认测试仅使用 localhost 或请求模拟，不访问任何共享服务。示例通过下述平台通用入口执行；独立手写测试工程已与平台分离。

## 五子棋：从文档到报告

独立测试服务已经部署在 `http://192.0.2.20:18081`。本配置需要能连接该私网地址，并可用 `~/.ssh/veriq_demo` 登录目标主机以清理本轮测试账号。数据库是新建的 `gomoku_api_test`，不是旧线上数据。请保留已有部署说明中的数据库基线。

```bash
.venv/bin/python -m api_test_tool import \
  --document examples/gomoku/evidence/接口文档.md --output reports/gomoku-contract.json
.venv/bin/python -m api_test_tool generate \
  --contract reports/gomoku-contract.json --rules examples/gomoku/rules.yaml \
  --seed 42 --output reports/gomoku-bundle.json
.venv/bin/python -m api_test_tool validate --bundle reports/gomoku-bundle.json
.venv/bin/python -m api_test_tool run \
  --bundle reports/gomoku-bundle.json --env examples/gomoku/environment.yaml \
  --output reports/gomoku-run-1
```

打开 `reports/gomoku-run-1/index.html`。每个输出目录必须为空，避免覆盖已有证据。前三个命令不发 HTTP 请求。`validate` 检查规则引用、断言、变量和请求结构；运行时另检查环境允许列表与预算。

默认配置生成 52 条候选：26 条可执行、20 条待补规则/执行条件、5 条危险 SSID 隔离、1 条并发场景暂不支持。可执行集需要 40 次业务请求。已有无冲突文档和确定测试资产构成演示基线，**不是新获得的业务审批**。空格/单字符用户名需要独占重置，不能用加后缀的方式冒充边界测试；连续错误登录默认保留待补专项规则。

常规账号每轮使用新的 `mvp_` 命名空间。结束时经 SSH 精确删除本轮生成的用户名，并核对剩余数为 0；不清空整库、不重启服务。会话由服务自己的超时机制释放。固定用户名、其他用户记录均不在清理范围内。

## 按用例重放

```bash
.venv/bin/python -m api_test_tool replay \
  --run reports/gomoku-run-1 --env examples/gomoku/environment.yaml \
  --case TC-FLOW-001 --output reports/gomoku-replay-1
```

回放读取 `bundle.json` 中冻结的规则和用例，创建新数据命名空间；不会重新生成预期或从响应学习。正常口令与鉴权值运行时生成并脱敏，公开负向测试输入保留语义。若自己提供的静态凭据在快照中被标成 `<redacted>`，预检会拒绝执行，需要通过受控配置重新提供，不能直接复用脱敏文本。

## 新接口接入与故障演示

见 [examples/items/README.md](examples/items/README.md)。这是独立编写的本地资源 API：登录获取 Token、创建、按 ID 查询、重复冲突、删除及删除后 404。规则依据是 [requirements.md](examples/items/requirements.md) 与 OpenAPI，夹具不读取生成器输出。

只增加 OpenAPI、规则/流程、环境配置，就用同一个解析器、生成器、执行器和 pytest 入口跑 19 条用例；涉及数值边界、枚举、必填、类型、嵌套 JSON、Token、跨步骤身份关联与 HTTP 清理。加 `--fault wrong_owner` 后，查询即使返回 HTTP 200、结构合法，也会在 `equals_variable` 断言失败。

## pytest 与 Allure

```bash
.venv/bin/python -m pytest tests/test_generated.py \
  --api-bundle reports/gomoku-bundle.json \
  --api-environment examples/gomoku/environment.yaml \
  --api-output reports/gomoku-pytest-1 \
  --alluredir=reports/gomoku-allure-1
```

仍生成 HTML/JSON，同时给每条 pytest 用例附上脱敏证据。可以使用 `-k TC-FLOW-001`；执行器仅运行 pytest 选中的用例。`--collect-only` 不发请求。Allure 原始文件可交给已有的 Allure CLI 查看，MVP HTML 本身无外部依赖。

CLI 退出码：`0` 全部已选用例通过且清理无失败；`1` 断言/执行/清理失败；`2` 存在待补、隔离或不支持的未执行用例；`3` 输入或静态配置错误。pytest 对已声明未执行场景显示 skip，并以非零退出码标记不完整；运行时前置/环境错误不会伪装成 skip 成功。JSON 中 `summary.complete` 表示执行完整，不能单独作为业务通过条件，需结合失败计数。

## 支持边界

- OpenAPI 3.0/3.1 常用 JSON 子集，支持本地引用；外部网络引用、循环引用、复杂组合及特殊序列化明确标为暂不支持。Markdown 支持当前仓库表格/列表/JSON 样例结构，不承诺理解任意自由叙述。
- 场景生成：正常、缺必填、空、null、类型、枚举/数值/长度边界、重复及鉴权缺失。是否可执行由有来源的规则与具体流程决定；没有唯一预期不会自动补成通过断言。
- 有限断言：状态码、严格 JSON 值、JSON Schema、JSON Pointer 存在、Header、Cookie 和输入变量关系；不执行 YAML 内的任意 Python/JS/SQL。
- 串行、每场景独立 Session、关闭代理继承与重定向、无重试、请求预算/超时/响应大小限制。遇到 5xx、连接异常或清理失败停止后续业务请求。
- 新业务仍需补充可审阅规则和前置/清理流程；本版不是任意文档上传即完全自动化。自由文本 AI 适配、规则版本差异界面、凭据管理、通用数据库清理和并发调度为后续范围。

## 工程结构

| 路径 | 职责 |
| --- | --- |
| `api_test_tool/parsers.py` | 文档契约和原文定位/哈希 |
| `api_test_tool/generation.py` | 规则、场景派生、冻结用例 |
| `api_test_tool/execution.py` / `assertions.py` | 请求、变量、严格断言、隔离和证据 |
| `api_test_tool/cleanup.py` | 已授权独立五子棋库的精确清理适配器 |
| `api_test_tool/reporting.py` | 独立 HTML、筛选和来源展开 |
| `api_test_tool/pytest_plugin.py` | 所有接口共享的 pytest / Allure 入口 |
| `examples/gomoku/` / `examples/items/` | 两个资料包与环境配置 |
| `tests/unit/` / `tests/fixtures/` | 工具验证、独立本地 API 和故障注入 |

接口文档和规则的来源原文会进入冻结资产，报告会脱敏凭据。资料包不应包含真实业务数据或生产口令；建议使用模板变量和运行时生成的测试凭据。
