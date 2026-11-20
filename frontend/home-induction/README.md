# 首页 Induction 入口

完整注册源： https://threeui.com/source-code/induction-button.json ，修订 `6f56c4f91814`。
三份注册文件完整保存在 `vendor/threeui`，每次构建按注册 SHA-256 校验，原文件不修改。
入口包按注册导出的 `InductionButton` 映射为 `ShaderButtons`，只接受注册的 `induction-button`。
Scene 使用指定的 dark / hue=0 / saturation=1 / brightness=1。
未注册的其他变体 raw 导入在构建时置空，它们不被本地入口导出或调用。

`adapt-source.mjs` 是应用适配层：
- API 与 UI 入口复用同一个按钮组件，按入口设置中文标签，宽度适配卡片；原生链接负责跳转、键盘及无脚本回退。
- 通过校验来源的 postMessage 转发悬停、聚焦、点击到原始事件处理器。
- 按用户反馈开启 WebGL alpha，并用原始距离场分离按钮内部与外侧电弧；外侧移除黑色底值，用发光强度作为透明度合成；删除黑底，保留原来的电弧计算、内部配色及闪光。
- 关闭组件展示页的环境背景，沿用首页 Water；不展示原示例导航或介绍文字。
- GSAP、Iconify 和 Tailwind 使用仓库已有、校验哈希的原版本本地镜像。隐藏导航图标不发网络请求，中文标签使用系统字体。
- 共享 CSS 与首页 Water 的注册 CSS 哈希相同，页面复用已加载的 Water 样式。

构建：`npm ci --ignore-scripts && npm run build`。Jenkins 校验、构建并冒烟检查生成文件。

浏览器验证：桌面 1440×960、窄屏 390×844，无横向溢出；原始 u_arcs 从静止 2.4 平滑升至悬停 5.7，移开回落至 2.5，聚焦再次升至 5.7；点击 u_flash 从 0 升至 0.84；Enter 正确进入 /api-testing。透明外侧与卡片融合。登录注册未改。
