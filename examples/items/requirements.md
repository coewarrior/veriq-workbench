# Items 示例的明确业务规则

本目录是新增接口通过资料与配置接入的独立证明样本，并非五子棋业务。
以下需求与 OpenAPI 共同构成预期来源；测试服务实现和实际 HTTP 返回不能修改预期。

## 会话

`POST /session` 接收非空字符串 `owner`，返回 HTTP 200 和非空字符串 `token`。
其他请求以 `Authorization: Bearer <token>` 鉴权。缺失或未知 Token 返回 HTTP 401，
JSON 正文为 `{"error":"unauthorized"}`。每个用例申请独立 owner；会话随服务重启销毁。

## 创建与查询

`POST /items` 的 JSON 仅有三个必填字段：`name` 是长度 1–24 的字符串，
`quantity` 是 1–5 的整数（JSON 布尔值不属于整数），`kind` 只能是 `book` 或 `tool`。
合法请求返回 HTTP 201，返回正整数 `id`、原样保存的三个输入字段和当前会话的 `owner`。
同一 owner 的同名资源再次创建返回 HTTP 409，JSON 正文为 `{"error":"duplicate_name"}`，
已有资源不变。不同 owner 的资源互相隔离。

必填字段缺失、null、空 name、字段类型错误、非法枚举、上下边界外的值，或额外字段，
均返回 HTTP 422，JSON 正文为 `{"error":"invalid_item"}`，且不创建资源。

`GET /items/{id}` 返回 HTTP 200，结构与创建结果一致。`id`、`name`、`quantity`、
`kind` 和 `owner` 必须与本用例创建的数据一致，不能只检查字段存在。

## 清理

`DELETE /items/{id}` 删除本 owner 的资源，返回 HTTP 204 和空正文。
查询或删除已不存在的资源返回 HTTP 404，JSON 正文为 `{"error":"not_found"}`。
每个成功创建资源的用例都声明清理步骤；即使业务断言失败，执行器仍应尝试受控清理。
清理失败必须体现在报告中。服务退出销毁全部内存数据，下一次启动是全新环境。

## 故障注入

本地服务支持 `wrong_owner`、`wrong_type`、`missing_field`、`server_error`、`non_json`
和 `cleanup_error`。这些开关故意违反上述需求，仅用于证明断言和失败报告有效。
5xx 会触发本轮后续业务请求停测；任何故障都不能引起预期放宽。
