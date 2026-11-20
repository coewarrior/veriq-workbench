# 工作区按钮

参考 ThreeUI [按钮集合](https://threeui.com/buttons)中的 [Star Portal](https://threeui.com/buttons/star-portal/star-portal)。
使用注册来源 `https://threeui.com/source-code/star-portal.json` 中 `imaginie-starfield.html` 的柔和三色渐变、轻微上浮与悬停光晕作为主操作参考；其 SHA-256 为 `002199215e124a85177585fc5cb84333f471562176f94c8d8e4456c79d721295`。
这次是现有按钮的 CSS 主题调整，不是嵌入整个 ThreeUI 展示组件。

- 保存、继续、执行等主操作：浅色渐变胶囊，悬停柔光和轻微缩放。
- 普通操作：深色半透明、细边框；导航和小操作保持较低视觉权重。
- 选中：青色边框及背景；危险操作：暗红色底和红色文字。
- 禁用不发光、不位移；加载保持原进度状态；键盘聚焦清晰；减少动态效果设置禁用位移动画。

改动集中在 `api_test_tool/static/controls.css`，会话、API 管理、集成管理、报告沿用原按钮结构与事件。首页通过 `#home-water` 排除，登录注册不加载此文件。没有增加 WebGL、定时器或额外网络依赖。
