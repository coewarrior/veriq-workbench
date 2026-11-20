# 五子棋数据库空闲连接修复

2026-09-10 12:20（北京时间）的执行报告中，11 条用例在注册步骤失败。同期服务日志明确记录：`The client was disconnected by the server because of inactivity`，随后持续出现 `Lost connection to MySQL server during query`。MySQL 的 `wait_timeout` 为 28800 秒。原程序只在启动时建立连接，无恢复逻辑，又将插入数据库失败统一显示为“用户名已被占用”，登录查询失败统一显示为“账号/密码错误”。

12:21 重启后的旧版本已恢复注册和登录，12:22 重跑为 26 条通过、0 条失败。20 条规则待补充、5 条隔离和1 条暂不支持属于测试范围状态，不是数据库连接故障。

## 补丁

`idle-connection.patch` 适用于 `work/gomoku-deployment` 的 `33a90e4-env1` 部署源码，以 `source/` 为相对路径应用：

```sh
patch --dry-run -p1 < idle-connection.patch
patch -p1 < idle-connection.patch
docker build -f deploy/Dockerfile -t ai-api-gomoku:33a90e4-env2 .
```

修改内容：

- 在已有互斥锁内、发送 SQL 前检查连接，失效时重新连接，并重新设置字符集。
- 修正连接释放条件；连接失败时释放句柄；数据库连接与读写等待各设为 5 秒。
- 不自动重放已发送失败的 SQL，避免数据库已提交但响应丢失时重复写入。
- 数据库故障返回 HTTP 503；真实重复账号、错误密码仍保留原业务响应。

服务器 `/home/veriq/apps/ai-api-gomoku/compose.yaml` 的镜像更新为 `ai-api-gomoku:33a90e4-env2`。只更新 API 容器，数据库、原账号和历史报告均保留。更新前的源码和 compose 备份保存在同目录 `backups/before-idle-fix-*.tar.gz`；旧镜像保留，可将镜像改回 `33a90e4-env1` 后仅重建 API 容器回滚。

## 验证

在部署服务器执行 `python3 deploy/verify_recovery.py`。脚本使用临时 API 容器，凭据从现有容器传入，不打印。它只断开临时容器的数据库连接和网络，不中断正式 API 或数据库服务。

已通过 14 项 HTTP 检查及1项数据清理检查：正常注册、登录、本人信息；数据库连接中断后首次登录和注册自动恢复；重复账号及错误密码仍正确拒绝；数据库不可达时三个接口均返回 503；网络恢复后无需重启即可恢复注册、登录和本人信息。只删除本轮随机账号，清理后剩余0条。

随后在正式测试环境中，使用用户原会话的冻结用例通过工作台执行入口重新运行，另存新报告，不修改原报告的失败证据。该过程不调用模型 API。

修复部署后 12:31 的正式回归：52 条用例中26条通过、0条失败、0条执行异常，发送40次真实请求；20条待补充、5条隔离、1条暂不支持保持原状态。创建的11个账号全部清理完成。

[修复后报告](http://192.0.2.20:18089/api/projects/ce09ccc7-8e05-4788-91c9-8aa871741a85/reports/f14941ae-a2b5-44d4-913b-1e7b38899c6d/index.html)
