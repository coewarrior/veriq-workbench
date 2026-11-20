# 参与贡献

请在 Issue 中说明 VERIQ 版本、Python 版本和运行系统，并附上最短的本地复现步骤、预期结果和实际结果。优先使用 `examples/items/` 或自行构造的样本。分享截图、日志、配置或报告前，请去掉账号、密钥、会话令牌和业务数据。

开发环境可用 `python -m pip install -e ".[mcp]"` 安装。提交 PR 时请描述改动影响及验证结果。接口链路可运行：

```bash
python -m pytest tests/unit/test_items_integration.py
```

其他改动请补跑相关测试。浏览器、数据库和部署相关检查按各自文档配置。
