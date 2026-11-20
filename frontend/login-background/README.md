# Sylva 登录页

来源：<https://threeui.com/source-code/sylva-hero.json>，revision `05f359ce157a`。

`vendor/threeui` 保留用户指定的全部 7 份注册源文件和 3 份二进制素材。每次构建验证 SHA-256。其他 Sylva 变体所需的作者实现取自官方 `sylva-living-world.json` 源码包，Fragment Mono 来自现有已核验 ThreeUI 依赖。未使用文档网站或根据截图重绘。

构建：

```sh
cd frontend/login-background
npm ci
npm run build
```

构建入口直接选取 `LandingPages.tsx` 中完整的 Sylva 段落（所有变体、组件函数原样保留），不打入其他无关页面。源文件不改写。`mount.tsx` 使用指定的 `SylvaHero` 属性，通过作者提供的 `applyScene` 在运行时隐藏原站导航和营销卡片，保留背景画布与指针交互。

canonical HTML 和本地 Three.js、图片、字体从 `/landing-pages/` 提供；登录前可读取。业务页面与 API 继续要求登录。生成的静态文件已提交，Python/Docker 部署不需要在线安装 npm 依赖。

登录按钮的 CSS 和五遍 WebGL2 液态金属渲染函数直接从 canonical HTML 提取。外部容器只调整按钮尺寸与布局。无 WebGL2 时保留普通 HTML 登录按钮，不影响认证。登录、注册、CSRF、跳转仍使用现有 login.js。

验证：登录页真实浏览器桌面/移动布局、注册切换、错误密码反馈、正确密码跳转；匿名素材访问与业务鉴权隔离回归测试。测试账号只在临时本地数据目录创建。
