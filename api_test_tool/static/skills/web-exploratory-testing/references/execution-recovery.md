# 原排队链路的结束后续接与清理

账号领取、完整集合、公平顺位、共享探索及独占仍沿原队列。只执行自己的模块，不把工作转给其他账号持有者。普通逐条保存和未知回执恢复保持原流程，不增加写权限请求或每步核验。

## 阶段登记与结束后续接

使用原 run kit 的 `input={action:"work_plan",plan_file:原阶段JSON路径}`。固定客户端调用独立的 work_plan 控制动作，阶段登记不再要求已结束的旧 lease 仍然有效。原请求丢响应时按同一私有控制回执核对/重取，不请求旧 lease context，也不重新执行用例或保存。

活动模块只更新自己的阶段。原模块已经真实退出且报告收尾完成、还有同轮未完成工作时，服务端直接把原节点更新为排队，沿原账号队列续测；节点 ID、原记录、用例、结果和历史回执保持，不再创建同名续接节点。当前调用返回 `continuation_binding_file` 和 `continuation_run_kit`，在原聊天中执行其原生准备/资源就绪/环境脚本，后续使用该新 kit 和目录。它复用原记录，不能复用已失效旧租约、旧浏览器身份或旧目录。需要先核对前置条件时使用返回的原节点当前绑定修订计划，不擅自重放已完成断言。

只有报告整理时继续使用原 `native-publish-saved` / record_after_release，原绑定已能补保存和发布，不领取账号、不创建续接。不用工作阶段登记代替报告发布。停止或暂停任务仍须沿原明确继续授权与 S1 退出检查，登记阶段不能恢复停止任务。

## 清理能力与真实对象

固定客户端支持 `input={action:"cleanup",events_file:原证据事件JSON数组路径}`；一次调用可带最多 100 个本轮已有事实。也可使用 native-cleanup CLI。平台只登记和核对，不替执行者调用业务 API。清理指令必须来自本轮既有权限，不能从方法存在推导出删除授权。

清理结果及证据充分性由 Codex 判断。描述文本按原样保存，不要求选择固定业务描述，也不按关键词或 HTTP 诊断覆盖显式结论。`observation.business_completed` 明确原业务清理是否完成；原尝试已核实但未完成时，同时写 `business_completed:false,original_operation_resolved:true`，如实保留遗留。`reconcile` 必须核对原操作并声明 `original_operation_resolved:true`，不能用另一条新操作或保留意图消除未知。原账号、对象 scope、尝试 ID、修订和真实退出校验不变。

- capability：事件使用 `command:"capability"`，数据放在 `capability` 对象内；方法使用 `methods:[{kind:"ui"或"api",entry,evidence_ref}]`，不能用 action、method/channel 替代。给出原 account_id、object_type、entry_source、实际方法及证据，service_version 仅填写已知版本。origin/environment/tenant/role 字段直接放在 capability 内，不嵌套 scope；可以省略，由服务端沿原租约账号推导，tenant/role 未识别时保存为空字符串，不能编造 HR/prod 或要求用户配置内部角色。显式填写的范围必须与可信账号一致。未知租户或角色的能力按账号隔离；相同有效 scope 复用，不逐对象重探，失败方法需要新的验证依据才可恢复。
- register：对象必须为本轮创建，带原 case/checkpoint、object_id、creation_evidence_ref、account_id、kind 和 scope。已有保留授权可直接登记；没有合法清理能力时，提供准确 residual.reason 及原 observation，不伪造删除成功。
- acquire_dependency / release_dependency：消费者为原模块的 source_node_id/case_id/checkpoint_id。消费者未交还时不能删除。
- prepare_cleanup：依据已核实能力返回 cleanup_attempt_id 和方法；只有明确取得本次尝试后才执行一次业务清理。complete_cleanup 回填同一次尝试的真实 observation，包含 evidence_ref、准确 object_scope 和显式 business_completed。未知只用 reconcile 核实原操作并声明 original_operation_resolved，不能再次删除。
- residual / retain：按真实对象状态及既有授权登记；不能消除 unknown。必须保留物理现场时明确 retain_scene；释放现场另给原 scene_release_evidence_ref，不把关浏览器当业务结果核实。

以下为 `events_file` 数组的完整形状示例。占位值必须替换为本轮已有回执与实际证据；示例不表示已经获得清理授权或已发现该入口。`register` 的业务字段放在 `object` 内；引用本批能力时可沿用其账号及 scope，不能把字段平铺到事件上。

```json
[
  {
    "command": "capability",
    "capability_id": "本轮能力ID",
    "capability": {
      "account_id": "原租约账号ID",
      "object_type": "实际对象类型",
      "entry_source": "本轮已观察的页面入口",
      "evidence_ref": "原入口证据引用",
      "methods": [{"kind": "ui", "entry": "实际删除控件路径", "evidence_ref": "原方法适用证据引用"}]
    }
  },
  {
    "command": "register",
    "responsibility_id": "本轮对象责任ID",
    "object": {
      "capability_id": "本轮能力ID",
      "case_id": "原用例ID",
      "object_id": "实际创建的对象ID",
      "creation_evidence_ref": "原创建证据引用",
      "ownership": "created_this_round",
      "kind": "test_data"
    }
  }
]
```

已有保留授权或准确遗留的对象可不登记 capability，但 `object` 必须明确原 account_id 与实际 object_type。观察的 `object_scope` 从原责任回执精确选取 origin/environment/tenant/object_type/object_id/account_id，未知 tenant 保留 `""`，不能省略成另一个 scope。`complete_cleanup` 和普通 `reconcile` 同时带回原 cleanup_attempt_id；它们不代表再次执行删除。客户端与服务端共用格式校验，一次列出本批错误路径，整批不部分写入；参数错误为 400，真实 scope 拒绝为 403，原状态或尝试冲突为 409。按具体原因修正原请求，不因错误分类而换账号或扩大目标。

代理白名单 404 只说明入口不支持该请求，不能证明对象不存在。只有适用当前对象类型与 scope 的已验证备用入口可用，不猜另一产品对象的删除 API。普通 404 还需区别路由/权限与有权核实的对象缺失；409 保留真实前置条件/冲突，未证实副作用不自动重试。

清理工作可作为原 work_plan 的 `purpose:"cleanup"` 单元，引用本轮原 case/checkpoint 和明确 `cleanup_responsibility_ids`，沿相同完整账号队列执行。原操作结算只结束该清理单元，不把原失败断言改成通过。已核实未清理、已知遗留或合法保留不等于继续占号，也不阻塞无关工作；未知实际操作、在途控制或明确要求保留的物理现场继续沿原租约保护、退出核实和交还处理。最终清理/遗留结论仍由 Codex 用原保存入口按真实事实填写。

HTTP 400/404/409 只是失败响应，不能单凭状态码推断结果未保存：报告刷新可能在结果落盘后才失败。当前客户端在失败后或显式 resume 时只读核对原记录；原精确下一修订及载荷一致则确认已保存，原修订未变化才确认未保存。其他情况保留未知回执，不重复发送业务动作。旧 rejected 回执也沿此标准入口核实，不手工删除回执或 pending 文件。
