# 首页 Water 背景

原始注册包：https://threeui.com/source-code/elemental-water.json ，版本 `7a6871fe99fa`。
三份注册文件在 `vendor/threeui` 中完整保存，每次构建验证 SHA-256。
本地包将作者导出的 `ElementsBackground` 别名导出为配置示例中的 `ElementsCollection`，不重写组件。
`Scene.tsx` 保留指定的 water 和所有数值属性。作者使用的内嵌 Canvas / WebGL2 文档随 JS 打包，没有嵌入文档网站。

按用户要求，`adapt-source.mjs` 在构建时做以下集成：
- 用现有 `api_test_tool/static/brand-orbit.svg` 的实际图像生成水中图标的距离场；原水波、粒子和折射 shader 不变。
- 在桌面左侧、窄屏上方为图标留出空间，避免被入口卡片遮挡。
- 转发首页指针到作者的事件处理器，背景不拦截按钮、链接或滚动。

组件保留可见性暂停、响应式和减少动态效果行为。共享 CSS 依赖的 Fragment Mono 来自仓库已有 ThreeUI 字体，许可证随静态资源发布。
只在首页加载，登录注册、测试会话页沿用现有页面。

构建：`npm ci --ignore-scripts && npm run build`。发布流水线自动核验、构建并检查静态资源可访问。
