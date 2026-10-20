# Docker / GHCR 部署

## 自动发布

自行将 Dockerfile、.dockerignore、deploy 目录、compose.yaml、
.github/workflows/publish-images.yml 和应用源代码提交并推送到 main。
每次 push 到 main 会自动构建并发布 amd64 / arm64 镜像；普通本地 commit 不会触发。
仓库 Actions → Publish Docker image 可查看日志，也可手动 Run workflow（仅 main 发布）。
使用 GitHub 自动提供的 GITHUB_TOKEN，不需要填写账号密码或自行添加发布 Token。

成功后生成：

- ghcr.io/danchotei/komgaread:latest

另有 sha-完整提交SHA 标签，可锁定版本或回退。首次发布后，在个人主页 Packages
的 Package settings 将 komgaread 包设为 Public，NAS 即可免登录拉取。
代码仓库公开不代表 GHCR 包自动公开。
如果重命名仓库，以工作流生成的镜像名为准，同步修改 compose.yaml。

## 架构和文件

一个镜像、一个 manga 容器，内部由 Supervisor 管理 Nginx 与 FastAPI 两个进程。
浏览器 → NAS:8080 的 Nginx → 容器内 127.0.0.1:8000 的 FastAPI → Komga。
Dockerfile 使用 Node 24 构建 Vue 静态文件，只将产物复制到最终镜像，不运行 Vite。
FastAPI 使用 uv.lock 安装生产依赖。仅暴露 8080，前端和 API 使用同一个来源。
Supervisor 负责进程重启和退出信号；健康检查同时检查前端和后端，日志使用 docker compose logs。
.dockerignore 排除本地 .env、日志、数据库和依赖，真实环境配置不打进镜像。

## NAS 启动

新建部署文件夹，放入 compose.yaml，将 deploy/.env.example 复制为同级 .env。
直接拉镜像无须上传 Dockerfile、源码和 nginx.conf（已包含在镜像内）。
编辑 .env：KOMGA_URL 填容器可访问的 Komga 地址；localhost 是容器自己，不是 NAS。
ALLOWED_ORIGINS 通常留空：后端按 Origin 的协议、域名、端口与请求入口自动校验同源。
NAS 的每层反向代理都必须保留浏览器的原始 Host（含非默认端口），容器内 Nginx 已配置。
仅刻意使用不同来源访问 API 时才填写额外白名单；多个来源以英文逗号分隔。

```sh
docker compose pull
docker compose up -d --no-build
docker compose ps
docker compose logs --tail=100
```

然后访问 http://NAS内网IP:8080，验证登录、搜索、阅读、保存进度。
若拉取 denied，确认 GHCR 包已公开；私有包需用 read:packages 凭据登录 GHCR。

HTTPS 上线时，NAS 反向代理将网页域名转发到 NAS:8080，再配置：

```dotenv
COOKIE_SECURE=true
```

重新执行 docker compose up -d --no-build 使环境变量生效。
COOKIE_SECURE=true 同时声明外部入口使用 HTTPS，即使 NAS 到容器之间使用 HTTP 也能校验。
后端不会直接使用 X-Forwarded-Host 放行请求；外层反代须保留 Host。

## 更新、回退与数据

推送代码后等待 Actions 发布成功，再在 NAS 执行上述 pull、up 命令。
GHCR 自动发布不代表 NAS 自动更新。前后端随同一镜像一起更新。
需要回退时，把 IMAGE_TAG 改为之前成功版本的 sha-完整提交SHA，再 pull、up。

每日推荐 SQLite 保存在 manga-data 命名卷，更新容器保留；不要使用 down -v 删除它。
阅读进度保存在 Komga。登录会话在内存，后端重启需要重新登录，只能运行单 worker / 单容器副本。

## 可选：本机测试构建

启动 Docker Desktop（Linux containers），在项目根目录 PowerShell 执行：

```powershell
Copy-Item deploy/.env.example .env
docker compose config --quiet
docker compose up -d --build
```

访问 http://localhost:8080 测试。配置校验不等于容器已成功运行；
发布以 Actions / Packages 结果为准，实际部署需验证登录、阅读和持久化。
