# KomgaRead

Vue 3 + TypeScript + Vite 前端，FastAPI 后端。按步骤学习并搭建手机端漫画阅读网站。

## 已完成

- 登录页：必填检查、显示密码、提交状态及错误提示。
- 后端通过 Komga 验证账号，返回当前用户；刷新页面检查会话。
- 简单的登录成功页面及退出登录。

- 首页随机推荐最多 4 个可访问的系列，展示封面、名称和书籍数量，支持换一批。

尚未实现系列详情、阅读器及个人收藏。

## 环境

- Node.js 24 LTS、npm、Git。
- Python 3.12 或以上、uv（Python 依赖管理工具）。

Windows PowerShell 使用 npm.cmd，避免 npm.ps1 被执行策略阻止。

## 启动后端

在项目根目录执行：

```powershell
Copy-Item backend/.env.example backend/.env
```

首次配置时复制即可；已有 .env 时不要覆盖。编辑 backend/.env，将 KOMGA_URL 改成开发电脑能访问的 Komga 地址，可以包含反向代理的子路径。不要填账号或密码。

```powershell
uv sync --directory backend
uv run --directory backend uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

后端接口文档：http://127.0.0.1:8000/docs 。登录和退出接口要求允许的 Origin，正常操作请使用前端页面。

## 启动前端

另开一个终端：

```powershell
cd D:\manga\komgaread
npm.cmd install
npm.cmd run dev
```

打开 http://127.0.0.1:5173 。两个终端都需要保持运行，Ctrl+C 停止对应服务。
Vite 将 /api 请求转发给 127.0.0.1:8000，浏览器不需要直接跨域访问 Komga。

## 本步代码与请求流程

1. src/components/LoginView.vue：v-model 收集输入，提交时 await 登录请求，通过 emit 通知父组件。
2. src/api/auth.ts：统一使用 fetch 请求本站接口及处理错误。
3. src/App.vue：保存当前用户，决定显示登录页还是登录成功页面，刷新时请求 /me。
4. backend/app/main.py：接收登录请求，通过 Basic Auth 请求 Komga /api/v2/users/me，取得用户及 Komga 会话。
5. 后端仅在内存保存 Komga 会话。浏览器保存 HttpOnly 的本站会话 Cookie，不在 localStorage 存放密码或令牌。
6. 退出时清除本站会话，并尝试撤销 Komga 会话。

前后端字段通过 User 类型及 LoginInput 对应。账号和密码只在用户提交时发送，后端不保存密码。

## 验证

```powershell
uv run --directory backend python -m pytest -q
npm.cmd run build
```

自动化测试使用模拟 Komga，覆盖用户会话隔离、刷新检查、过期会话、来源检查、认证失败和退出。
真实环境请在页面中验证：正确账号登录、刷新保持登录、退出、错误密码提示。开发者没有你的凭据，不会代替你执行真实账号登录。

## 当前限制

学习阶段会话存储在单个后端进程中，8 小时后过期；后端重启或代码热重载需要重新登录。不要使用多个 worker。
正式部署时还需配置 HTTPS、COOKIE_SECURE=true、ALLOWED_ORIGINS 为实际网页来源，以及反向代理 /api。当前 Vite 代理只用于开发。

.env、.venv、node_modules、dist 均已忽略。VITE_ 变量会暴露给浏览器，不要用于保存秘密。

## 后续

读取书库 → 漫画详情和阅读器 → 同步阅读进度 → SQLite 个人收藏。

仓库：https://github.com/Danchotei/komgaread

## 第四步：首页随机推荐

- `src/components/HomeView.vue`：首页组件，onMounted 时加载推荐，v-for 渲染卡片。
- `GET /api/series/recommendations`：使用当前用户的 Komga 会话，先查询系列总数，再随机选择最多 4 个不同的位置读取。不会一次下载整个书库。
- `GET /api/series/{id}/thumbnail`：后端用当前用户权限读取封面，浏览器只携带本站 Cookie。
- 换一批会重新随机抽取，可能与上一批有重复。书库不足 4 部时显示全部；书库在抽样过程中变更时，结果可能少于 4 部。
- 当前卡片仅展示信息，点击进入详情将在后续实现。

验收：登录后看到推荐；刷新或换一批可重新随机；窄屏两列、宽屏四列；空书库和接口失败有提示，封面失败显示占位。
