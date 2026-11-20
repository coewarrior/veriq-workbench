# 执行记录

Ruling: 用户明确否定SQLite，之前实现全部未提交/未合并/未上线；停止SQLite兼容视图方案，保留按记录加载与写回思路，数据库换为独立PostgreSQL。
Ruling: 用户禁止额外回归优先于skill TDD要求；仅静态与标准发布必要验证，不擅自测试。
Pre-flight: 存储、调用方、迁移、发布共用backend/schema/激活状态契约；只读快照不得获取调度门锁，避免Store→DB读路径与DB→Store写路径反转死锁。
Audit: 旧方案评审发现SQLite特殊key路径回查不可靠；PostgreSQL迁移须以Python解码/参数化逐行插入和完整摘要核验，不能沿用该触发器。

Review: 独立存储审查补齐关联只读快照和跨库排序摘要；原始 SQL TEXT 无法无损表示时整笔失败，原库保留，CLI 不打印含用户数据的驱动异常。
Review: 发布审查补齐同镜像 ready 激活恢复、SCRAM 角色初始化防明文语句日志、显式 full 入口的隔离 PostgreSQL 前置，以及兼容 PG 回滚后的版本凭据一致性。
Scope: 既有 full 回归文件仅适配数据库替换，未新增业务检查、未执行 pytest 或全量回归；默认 DEPLOY=true 仍只跑标准构建、隔离启动和健康核对。
Review: 最终调用链审查发现 task.baseline 仍嵌入大历史，补独立按需基线存储；保留完整基线与原调度行为，不允许带着该遗漏上线。
Completed: task.baseline 已拆出，普通调度不解析/编码其正文；需要报告基线的调用在同一快照补读当前 task 的 cases/sources，完整历史和映射顺序参与导入指纹。独立审查未发现未解决的调用方越界写或连接关闭后 lazy 值逃逸。
Verification: 最终改动 Python AST、shell 语法、Compose YAML、diff 检查通过；既有测试适配保留 162 个原测试函数，无删除/跳过/新增业务用例。未运行额外回归。GitLab main 集成基线 f861991bc5c3c8fc63a87a6874e2eb045e0af4cc。

Release: 用户明确要求强杀残留后，以原状态比较交换终止旧轮 3 个无租约排队节点、清除 1 项残留收尾，未改变用例/报告。原发布探针 rounds/channels/finalizations/acknowledgements 均为 0；未采用发布豁免参数或修改活动保护。
Failure: #574 的生产迁移容器 2 GiB OOM（Docker oom + exit 137），自动回滚旧服务成功。修复限定迁移内存：流式同字节摘要、源写入后释放、短时核对容器 8 GiB；完整数据/顺序/类型校验不变。静态审查与标准发布，不新增业务或全量测试。
