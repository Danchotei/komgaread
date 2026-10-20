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
编辑 .env：SETUP_KEY 和 KOMGA_URL 均可留空。
启动后访问网页，首次配置页输入初始化密钥和 Komga 公网地址。
点击“测试连接”检查 API；“测试并保存”会再次检查，连接成功才保存。
测试检查 API 可达性，实际账号和权限仍需登录验证。
地址必须能从容器访问；localhost 是容器自己，不是 NAS。
未指定 SETUP_KEY 时，首次启动自动生成随机密钥，保存到 /data/setup.key。
在 NAS 容器日志或 docker logs komgaread 中查找“初始化密钥”，复制到网页。
未初始化前重启会继续使用同一密钥，并在启动日志重新显示；初始化后不再输出。
也可选择手动设置至少 16 位的 SETUP_KEY 覆盖自动密钥，无需同时使用两种方式。
密钥不会通过公开接口返回或自动填入网页，不要把密钥文件或含密钥的日志公开。
ALLOWED_ORIGINS=* 默认允许任意有效 HTTP/HTTPS 来源，并支持 CORS 预检与凭据响应。
不再比较 Origin 与内部 Host/协议，因此多层反向代理无需逐一添加域名。
这会放宽跨站访问限制；如需限制来源，可填写明确的来源列表，多个来源以英文逗号分隔。

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
COOKIE_SECURE 只控制 Cookie 是否仅经 HTTPS 发送，不再参与来源校验。
当前网页仍通过同域 /api 请求，Cookie 保持 SameSite=Lax；跨站 Cookie 仍受浏览器策略限制。

## 更新、回退与数据

推送代码后等待 Actions 发布成功，再在 NAS 执行上述 pull、up 命令。
GHCR 自动发布不代表 NAS 自动更新。前后端随同一镜像一起更新。
需要回退时，把 IMAGE_TAG 改为之前成功版本的 sha-完整提交SHA，再 pull、up。

每日推荐 SQLite 保存在 /data/daily.sqlite3，Compose 将 manga-data 命名卷挂载到 /data。
启动地址配置保存在 /data/komga.json，只保存地址；自动初始化密钥单独存放在 /data/setup.key。
Komga 密码不写入这些文件。
应用的 /app/backend/data 是指向 /data 的符号链接，代码和依赖目录无需挂载。
使用 NAS 目录时可改为 /你的NAS目录/komgaread/data:/data，并允许 UID 10001 写入。
已有部署只需将原数据卷或原 NAS 目录的容器目标改成 /data，保留原数据来源及文件。
此修改必须配合新版镜像，旧镜像仍使用旧路径。更新容器会保留数据，不要使用 down -v 删除它。
阅读进度保存在 Komga。登录会话在内存，后端重启需要重新登录，只能运行单 worker / 单容器副本。

## 初始化与地址配置

初始化完成后，公开配置接口关闭，不提供未登录修改地址的入口。
保存的配置优先于环境变量；已有 KOMGA_URL 环境变量且没有配置文件时，保持原先部署行为，直接进入登录页。
想使用首次配置页时，需清空 KOMGA_URL 并重新创建容器。
API 和图片请求统一使用保存的单个公网地址，连接失败时直接提示错误。
已有双地址配置文件仍读取 primary_url，首次读取时自动从文件移除旧备用字段；如需更换地址，请按下面步骤重新配置。

需要重新配置时，管理员先停止容器，备份后移走数据目录中的 komga.json，
清空旧地址环境变量后再启动，继续使用 setup.key 中的密钥；如需更换自动密钥，
停机时一并移走 setup.key，下次启动会重新生成。每日推荐数据库 daily.sqlite3 无须删除。
配置文件损坏时会显示错误，不会自动开放初始化。NAS 目录需允许 UID 10001 写入。

## 可选：本机测试构建

启动 Docker Desktop（Linux containers），在项目根目录 PowerShell 执行：

```powershell
Copy-Item deploy/.env.example .env
docker compose config --quiet
docker compose up -d --build
```

访问 http://localhost:8080 测试。配置校验不等于容器已成功运行；
发布以 Actions / Packages 结果为准，实际部署需验证登录、阅读和持久化。
