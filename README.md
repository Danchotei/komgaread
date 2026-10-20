# KomgaRead

基于 Vue 3、TypeScript 和 Vite 的手机端漫画阅读网页，按小步骤逐步实现。

## 当前范围

已完成前端项目初始化及手机端登录界面，支持必填检查、密码显示切换和提交提示。尚未接入后端，提交不会验证账号，也不会保存或发送密码。

## 环境

- Node.js 24 LTS（项目通过 Node.js 24.19.0 验证）
- npm（随 Node.js 提供）
- Git

若 `node --version` 显示 v20.17.0，请先安装 Node.js 24 LTS，重新打开终端后再运行以下命令。
官方下载：https://nodejs.org/

## 本地运行

在 PowerShell 中进入项目文件夹：

```powershell
cd D:\manga\komgaread
npm.cmd install
npm.cmd run dev
```

打开终端显示的本地地址，通常为 http://localhost:5173 。按 Ctrl+C 停止服务。
修改页面并保存后，浏览器会自动更新。

## 文件结构与学习顺序

```text
index.html          网页入口，包含挂载 Vue 的 app 容器
src/main.ts         创建 Vue 应用，导入样式并挂载根组件
src/App.vue         根组件，展示登录组件
src/components/LoginView.vue 登录界面及表单交互
src/style.css       全局样式和手机端布局
vite.config.ts      Vite 配置，启用 Vue 文件支持
tsconfig*.json      TypeScript 检查规则
package.json        项目依赖和运行命令
package-lock.json   锁定依赖版本，需提交到 Git
```

建议先从 App.vue 的文字入手，修改后观察页面变化，再阅读 style.css。

## 构建与预览

```powershell
npm.cmd run build
npm.cmd run preview
```

build 先执行 TypeScript 检查，再生成 dist 文件夹。preview 用来检查构建结果，不用于正式部署。

## GitHub

仓库：https://github.com/Danchotei/komgaread

后续每完成一步，可以检查改动后提交：

```powershell
git status
git add .
git commit -m "Describe the change"
git push origin main
```

node_modules 和 dist 不上传，由依赖安装和构建命令重新生成。
.env 文件已忽略；不要将 Komga 密码、API Key 或其他凭据提交到公开仓库。前端的 VITE_ 环境变量会被打包到浏览器，不能用于存放秘密。

## 后续方向

1. 编写登录界面。
2. 新建 FastAPI 后端并连接 Komga。
3. 读取书库和同步各用户的阅读进度。
4. 加入 SQLite，保存个人收藏。

## 第二步：理解登录表单

- `ref` 定义会变化的数据，例如账号、密码和提示消息。
- `v-model` 将输入框和数据关联起来；账号使用 `.trim` 去掉首尾空格，密码保持原样。
- `:type` 根据状态切换密码框的显示方式。
- `@click` 监听点击，`@submit.prevent` 处理提交并阻止浏览器刷新页面。
- `required` 使用浏览器自带的必填验证。
- `v-if` 让提交提示仅在有消息时出现。

体验步骤：空表单提交会提示必填；输入任意测试账号和密码后可切换显示密码；提交后会明确提示尚未连接 Komga，不会跳转到书架。
