# 模型 API 兼容说明

核对日期：2026-09-09。这里的“兼容”表示已按官方接口格式实现协议适配，并通过本地 HTTP mock 验证；没有使用真实供应商账号调用模型，不能视为所有型号、所有区域或所有套餐的实测证明。

## 四种协议

| 协议 ID | 请求 | 鉴权 | 文本提取 |
|---|---|---|---|
| `openai_responses` | `POST /responses`，`instructions` + `input`，`max_output_tokens` | Bearer | `output[].content[].text`，仅 `output_text` 项 |
| `openai_chat` | `POST /chat/completions`，`messages` | Bearer | 第一条 `choices[].message.content` |
| `anthropic` | `POST /messages`，`system` + `messages`，`max_tokens` | `x-api-key` + `anthropic-version: 2023-06-01` | `content[]` 中的文本块 |
| `gemini` | `POST /models/{model}:generateContent`，`systemInstruction` + `contents`，`generationConfig.maxOutputTokens` | `x-goog-api-key`，Key 不放在 URL | 第一条 candidate 的文本 parts，排除 thought |

根地址自动补默认版本路径：前三种 `/v1`，Gemini `/v1beta`；已经带版本或厂商前缀时保留前缀。支持填完整且匹配协议的接口路径，避免重复拼接；不匹配时请求前报错。

OpenAI Chat 和 MiniMax 使用 `max_completion_tokens`，其他兼容 Chat 预设使用 `max_tokens`。MiniMax 发送 `reasoning_split=true`，把推理内容与最终文本分开。没有默认发送 temperature、JSON Schema、工具调用或推理强度等容易因型号不同而不兼容的选项。生成测试用例所需的 JSON 由应用提示词要求，再由应用解析与校验。

## 供应商预设

模型名称 由使用者填写，不绑定一个可能失效的“最新模型”。地址也可编辑，便于匹配账户区域、套餐和自有网关。

| 供应商 | 默认协议 | 默认 Base URL | 已读取的官方依据 |
|---|---|---|---|
| OpenAI | Responses | `https://api.openai.com/v1` | [Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)、[Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) |
| DeepSeek | Chat | `https://api.deepseek.com/v1` | [首次 API 调用](https://api-docs.deepseek.com/) |
| 通义千问 Qwen | Chat | `https://dashscope.aliyuncs.com/compatible-mode/v1` | [OpenAI 兼容接口](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)、[区域与 Base URL](https://help.aliyun.com/en/model-studio/base-url) |
| 智谱 GLM | Chat | `https://open.bigmodel.cn/api/paas/v4` | [OpenAI API 兼容](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction) |
| Kimi | Chat | `https://api.moonshot.cn/v1` | [快速开始](https://platform.kimi.com/docs/get-api-key)、[OpenAI 兼容](https://platform.kimi.ai/docs/guide/migrating-from-openai-to-kimi) |
| 豆包 / 火山方舟 | Chat | `https://ark.cn-beijing.volces.com/api/v3` | [方舟官方 SDK 的 Chat 请求实现](https://github.com/volcengine/volcengine-python-sdk/blob/master/volcenginesdkarkruntime/resources/chat/completions.py)、[参数定义](https://github.com/volcengine/volcengine-python-sdk/blob/master/volcenginesdkarkruntime/types/chat/completion_create_params.py) |
| MiniMax | Chat | `https://api.minimaxi.com/v1` | [中文 OpenAI 兼容接口](https://platform.minimaxi.com/docs/api-reference/text-openai-api)、[国际站兼容接口](https://platform.minimax.io/docs/api-reference/text-openai-api) |
| Anthropic Claude | Messages | `https://api.anthropic.com/v1` | [Messages API](https://platform.claude.com/docs/en/api/http/messages/create) |
| Google Gemini | generateContent | `https://generativelanguage.googleapis.com/v1beta` | [generateContent API](https://ai.google.dev/api/generate-content)、[文本生成与 Header 鉴权示例](https://ai.google.dev/gemini-api/docs/generate-content/text-generation?hl=en) |
| 自定义 | Chat（可切换） | 使用者填写 | 所选协议的参考格式 |

阿里云预设是北京地区按量付费共享域名；官方目前仍提供该地址，也建议生产使用业务空间专属域名。地区 API Key 不能随意混用。MiniMax 国际账号可把域名改为 `api.minimax.io`。Kimi 的原文档站点已跳转至 `platform.kimi.com` / `platform.kimi.ai`。火山方舟文档正文在本次抓取中只返回动态页面外壳，因此 Chat 参数与路径以官方 SDK 源码交叉核对，不引用社区文章。

## 本版边界

- 只支持单轮、非流式纯文本生成。多模态、工具调用、批量请求、服务端会话续接、Azure 部署式接口、Vertex AI OAuth、AWS Bedrock 签名鉴权及厂商专用 Token Plan 鉴权不在本版范围。
- “测试连接”也是一次真实模型请求，输出上限取配置值与 256 的较小者。推理模型可能把这部分预算用于内部推理，导致输出被截断；会明确报错，不会据此声称 API Key 无效。
- 输出额度支持自动或手动正整数，不设统一 Token 上限；提示词合计最多 256 KiB，响应接收保护阈值 128 MiB，用例文本/JSON 解析保护阈值 16 MiB；连接超时最多 10 秒，读取等待取配置值，仅约束连续无数据时间；不按累计生成耗时中断。该限制不是供应商计费承诺，供应商可能另计推理 Tokens。
- 不自动重试，不自动切换供应商，不跟随重定向，不继承系统代理或 `.netrc`，避免无感重复调用和凭据送往另一个地址。
- URL 必须 HTTPS；HTTP 仅允许 loopback 本地 mock。URL 不接受 userinfo、query、fragment、控制字符和编码路径。对公共服务的 DNS / 内网地址访问策略由 Web 层另行控制。
- API Key 不出现在 dataclass repr、错误信息或返回对象中；HTTP 错误只保留状态码和固定诊断，不回传原始错误体。返回 usage 只包含白名单数字，响应回显本次 Key 会被替换。
- 截断、拒答、内容过滤、工具调用、空文本或非 JSON 协议响应均视为生成失败；不会把半截用例当成成功生成。

## 可复现验证

```bash
python -m pytest -q test_model_adapters.py
```

测试仅向临时 `127.0.0.1` 服务发送 mock 凭据。覆盖四协议的请求/响应、路径拼接、参数和 Key 校验、状态码与错误体脱敏、拒绝重定向、无自动重试、不继承代理、提示词/响应限额、截断处理、Token 计数归一化及连接测试预算。Web 应用整合后可将测试导入改为 `from api_test_tool import models as adapters`。


### 流式接收（v0.3.1）

四种协议均请求 SSE 流式响应。仅保存最终文本、数值用量和处理阶段；推理原文不落盘。读取可用数据后立即解析，不等待固定缓冲区填满。正常心跳持续保持连接；断流、截断、服务商错误不作为成功结果。原 `timeout` 字段兼容已有配置，现在含义为连续无数据的等待秒数。

协议依据：[OpenAI 流式响应](https://developers.openai.com/api/docs/guides/streaming-responses)、[DeepSeek 心跳机制](https://api-docs.deepseek.com/quick_start/rate_limit/)、[Claude 流式事件](https://platform.claude.com/docs/en/build-with-claude/streaming)、[Gemini 流式生成](https://ai.google.dev/api/generate-content#method:-models.streamgeneratecontent)。验证使用本地模拟模型服务，不表示已调用这些厂商的真实模型。


### 输出额度（v0.3.2）

- `max_tokens: null` 或省略：DeepSeek V4 三个已收录名称使用 384,000；Anthropic 在同一个已校验来源查询 Models API 的 `max_tokens` 能力字段；其他模型省略可选输出额度，由服务商采用默认值。
- 手动正整数原样发送，不设统一 16,384 上限，也不静默向下截断。服务是否接受此值由模型/网关决定。
- 能力查询不重定向，不自动更换来源；能力缺失的 Anthropic 兼容服务需手填，避免猜值造成截断。保存配置不会访问模型服务。
- 既有网页配置的旧小额度一次性迁移为自动；保留加密 Key、配置 ID 与会话引用。CLI 显式数值保留。
- 依据：[DeepSeek 模型容量](https://api-docs.deepseek.com/quick_start/pricing/)、[Anthropic 模型能力字段](https://platform.claude.com/docs/en/api/models/retrieve)。已收录 DeepSeek 容量于 2026-09-10 核对，网关可使用手动值覆盖。
