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
启动后访问网页，首次配置页输入初始化密钥、Komga 公网地址、管理员账号生成的 Komga API 密钥和注册邀请码。
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
点赞、收藏和浏览记录保存在 /data/reactions.sqlite3，按 Komga 用户和系列去重；沿用同一个 /data 映射，无需增加挂载。备份数据目录时应包含此文件。
个人页的浏览记录和收藏使用递增序号排序，不记录准确时间。浏览记录最多保留 50 个系列，重复浏览移到最前；收藏取消再添加移到最前。旧数据自动按现有排序转换为序号并移除时间字段，记录和顺序均保留。
“我的收藏”支持标题、作者、分类和标签关键词搜索，沿用全局搜索的简繁体扩展；仅返回当前账号收藏的系列，按收藏先后排序，清除关键词后恢复完整列表。
个人页用户名默认显示 Komga 账号邮箱，可修改为 1–40 个字符的本站昵称，保存到同一 reactions.sqlite3 的 user_profiles 表；不改变 Komga 登录账号，不新增时间记录。
首页、搜索、浏览和个人页共用系列卡片，统一显示两行标题、分类、章数及最后一章发行日期；个人记录的排序仍只使用序号，展示的发行日期来自 Komga 漫画元数据。
首页最近添加与每日推荐各展示最多 8 个系列，左右滑动查看更多。旧每日推荐缓存按新数量自动更新，之后继续按中国时间每日 00:00 更新。
每日推荐列表在浏览器标签页内按账号和中国日期缓存，切换页面或刷新时复用当天数据；跨天重新请求，退出登录清除缓存。封面请求仍由后端验证当前权限。
分类页提供“最近更新”（按系列最后一章发行日期倒序，最多 30 个，缺失日期排末尾）、“随机本子”（每次从入口进入抽取最多 12 个系列）和“浏览所有”（按名称排序、每页 16 个、下滑自动加载）。卡片统一显示分类和最后一章发行日期；浏览所有加载后续页后提供返回顶部按钮，回到顶部自动隐藏。列表始终使用当前用户的 Komga 权限。
启动配置保存在 /data/komga.json，包含 primary_url、api_key 和 invite_code；文件权限设为 0600，API 密钥和邀请码不会由公开接口返回。请保护此文件及其备份。
自动初始化密钥单独存放在 /data/setup.key，与 Komga API 密钥用途不同。
Komga 密码不写入这些文件。
应用的 /app/backend/data 是指向 /data 的符号链接，代码和依赖目录无需挂载。
使用 NAS 目录时可改为 /你的NAS目录/komgaread/data:/data，并允许 UID 10001 写入。
已有部署只需将原数据卷或原 NAS 目录的容器目标改成 /data，保留原数据来源及文件。
此修改必须配合新版镜像，旧镜像仍使用旧路径。更新容器会保留数据，不要使用 down -v 删除它。
阅读进度保存在 Komga。登录会话保存在 /data/sessions.sqlite3，沿用现有数据映射；后端或容器重启后仍保留。文件权限为 0600，包含 Komga 会话与“记住我”凭据，须保护数据目录及备份，不向前端返回凭据、不保存密码。仍只运行单 worker / 单容器副本。

## 长期登录

- KomgaRead 按最后一次成功的已认证请求续期 14 天，同时刷新 HttpOnly Cookie；连续 14 天不访问后必须重新登录，即使 Komga 长期凭据仍有效也不会自动恢复。
- 会话数据库连接在单 worker 内复用，续期写盘在线程池执行，避免每张图片重复初始化数据库或同步写盘阻塞异步请求；每次续期仍提交到磁盘。
- 登录时请求 Komga 的 remember-me，并保存其 Cookie 与到期时间。普通会话失效时使用它恢复、保存新令牌、重试请求；图片请求也支持恢复。同账号并发恢复合并处理。
- 在 **Komga 容器**设置 `SERVER_SERVLET_SESSION_TIMEOUT=14d`，并在 Komga「服务器设置」把 Remember Me duration 设为 **365 天**。365 天由 Komga 决定，KomgaRead 不擅自延长其凭据有效期。
- 网络故障保留本地会话以便稍后重试；长期凭据到期、被撤销、密码变更导致失效时需重新登录。退出会删除本站记录并请求 Komga 注销；更换 Komga 地址后旧凭据不可继续使用。
- 由旧版内存会话升级时需要重新登录一次，之后的有效会话可跨重启保留。启动时、每小时及登录时清理过期记录。

## 初始化与地址配置

初始化完成后，公开配置接口关闭，不提供未登录修改地址的入口。
首次配置会通过 X-API-Key 验证账号和管理员权限，失败时不保存。配置管理员密钥和邀请码后登录页开放注册，邮箱作为账号，密码至少 8 个字符且 UTF-8 不超过 72 字节。
注册须填写管理员提供的共享邀请码；可重复使用、区分大小写、忽略首尾空格。缺少邀请码的旧配置暂不开放注册，登录阅读不受影响；补填按下方重新配置步骤操作。
新注册账号可访问全部漫画库，仅授予 PAGE_STREAMING 在线阅读权限，不授予管理员或文件下载权限。注册成功后手动登录；没有邮箱验证步骤。单实例每分钟最多向 Komga 发起 10 次注册请求。
已有不含 api_key 的配置继续用于登录和阅读，不会强制重置；需要补填密钥及邀请码时按下方重新配置步骤操作。
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
