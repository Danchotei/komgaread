# KomgaRead

Vue 3 + TypeScript + Vite 前端，Python + FastAPI 后端的手机端漫画阅读网站。漫画来自现有 Komga 服务，按步骤开发和学习。

## 当前功能

- 使用 Komga 账号登录，每位用户独立会话；主动登录成功后进入首页。
- 首页最近添加及每日推荐各显示最多 4 个系列。推荐按中国时间每日 00:00 更新，本地 SQLite 保存当天结果。
- 底部主页、分类、我导航；个人页提供退出登录。
- 系列详情展示封面、作者、分类、标签及章节；章节支持序号升序／倒序及阅读状态显示。
- Webtoon 连续纵向阅读，图片懒加载、失败重试、继续上次进度；轻点显示／隐藏上下工具栏。
- 图片成功加载且进入阅读位置后保存 Komga 进度，最后一页标记读完；保存失败可重试。
- 综合搜索标题、作者、分类、标签；OpenCC 提供简繁及台港字形扩展。结果只显示系列。
- 搜索可按系列最后一章（序号最大）的发行日期排序，缺失日期排最后；全部匹配结果排序后分页。
- 搜索状态及滚动位置在当前页面运行期间保留，刷新或退出登录后清空。
- 页面层级返回、500ms 水平滑动动画及手机安全区域适配。

个人收藏、点击标签直达搜索、自动跳转下一章尚未实现。

## 环境与启动

需要 Node.js 24 LTS、npm、Git、Python 3.12+ 和 uv。
Windows PowerShell 使用 npm.cmd，避免 npm.ps1 执行策略问题。

首次配置后端（已有 .env 时不要覆盖）：

```powershell
Copy-Item backend/.env.example backend/.env
```

编辑 backend/.env 中的 KOMGA_URL。不要填账号或密码。

在项目根目录启动后端：

```powershell
uv sync --directory backend
uv run --directory backend uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```powershell
cd D:\manga\komgaread
npm.cmd install
npm.cmd run dev
```

访问 http://127.0.0.1:5173 。保持两个服务运行，Ctrl+C 停止。
后端接口文档：http://127.0.0.1:8000/docs 。
Vite 开发代理把 /api 转发到 127.0.0.1:8000，浏览器不直接访问 Komga。

当前不使用 --reload：Windows 上曾出现热更新停滞。修改后端代码、配置或依赖后，手动重启并检查运行中的接口。重启会清空内存会话，需要重新登录。

## 代码入口

```text
src/App.vue                  登录状态、页面层级和导航动画
src/components/LoginView.vue 登录表单
src/components/HomeView.vue  最近添加、每日推荐
src/components/SearchView.vue 搜索、排序和结果分页
src/components/SeriesView.vue 系列详情、章节列表
src/components/ReaderView.vue Webtoon 阅读与进度保存
src/components/BottomNav.vue 底部导航图标
src/api/                     前端接口请求及进度写入队列
src/searchState.ts           当前登录期间的搜索内存快照
src/style.css                响应式布局和动画
backend/app/main.py          应用入口、认证、系列及阅读接口
backend/app/search.py        独立搜索接口，由 main.py 注册
backend/app/translate.py     OpenCC 关键词转换
backend/app/daily.py         每日推荐存储及中国日期计算
backend/tests/              后端自动化测试
```

search.py 接收共用的请求、认证和 JSON 解析函数，不反向导入 main.py。
books 在 Komga 接口中表示书籍，本项目产品概念中对应章节。

## 验证

```powershell
uv run --directory backend python -m pytest -q
npm.cmd run build
```

测试使用模拟 Komga。真实账号需要在网页验收：登录 → 搜索 → 系列 → 阅读 → 保存进度 → 返回，检查排序和滚动恢复。
构建输出为 dist；npm.cmd run preview 可预览构建结果，不用于正式部署。

## 响应式与正式部署

CSS 负责按窗口自动适配，不需要为不同手机部署多份网站。
首页 Grid 和 Flex 分配可用高度，cqh 根据书架高度计算封面宽度；矮屏允许纵向滚动。
搜索页独立滚动；手机安全区域通过 viewport-fit=cover 和 env(safe-area-inset-*) 留白。

正式部署时，将 dist 放入 NAS 的静态网站服务，并将同域名 /api 反向代理到 FastAPI。
设置 COOKIE_SECURE=true、ALLOWED_ORIGINS 为实际 HTTPS 网页来源。Vite 开发代理不会出现在正式构建中。

## 数据与限制

- 会话仅在内存保存，8 小时过期，后端重启需要重新登录；当前只运行单 worker。
- 每日推荐数据保存在 backend/data，部署时应保留该目录。
- 搜索日期排序需要读取每个匹配系列的末章日期，匹配较多时会增加等待；并发限制为 3。
- 简繁转换不保证覆盖所有混写组合、同义词和日文异体字。
- 图片不做额外压缩或后端缓存，沿用 Komga 返回内容。
- .env、.venv、node_modules、dist、本地数据与日志均不提交。VITE_ 变量会暴露给浏览器，不存放秘密。
- 用户手动提交 Git；代理不自动提交或推送。

仓库：https://github.com/Danchotei/komgaread
