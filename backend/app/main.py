from pathlib import Path
from time import time
from secrets import token_urlsafe
import os
from urllib.parse import urlsplit
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from http.cookies import SimpleCookie
from email.utils import parsedate_to_datetime
import asyncio

from jmcomic import JmOption

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from .session_store import SessionStore

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
KOMGA_URL = os.getenv("KOMGA_URL", "").rstrip("/")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
ALLOWED_ORIGINS = {value.strip() for value in (os.getenv("ALLOWED_ORIGINS") or "*").split(",") if value.strip()}
COOKIE_NAME = "komgaread_session"
SESSION_SECONDS = 14 * 24 * 60 * 60
REMEMBER_COOKIE = "komga-remember-me"
session_context = ContextVar("session_id", default="")
recovery_locks = [asyncio.Lock() for _ in range(32)]

@asynccontextmanager
async def lifespan(app):
    from .reactions import initialize_store
    from .setup import prepare_setup
    from . import release_cache
    from .setup import configured_values
    prepare_setup(komga_url)
    await run_in_threadpool(initialize_store)
    sessions.prune(time())
    async def cleanup_sessions():
        while True:
            await asyncio.sleep(3600)
            await run_in_threadpool(sessions.prune, time())
    cleanup = asyncio.create_task(cleanup_sessions())
    release_cache.service = release_cache.ReleaseCache(
        Path(__file__).resolve().parents[1] / "data" / "metadata.sqlite3",
        lambda: (komga_url(), configured_values().api_key),
    )
    date_worker = asyncio.create_task(release_cache.service.run())
    try:
        yield
    finally:
        cleanup.cancel()
        date_worker.cancel()
        with suppress(asyncio.CancelledError):
            await date_worker
        release_cache.service = None
        with suppress(asyncio.CancelledError):
            await cleanup
        sessions.close()


app = FastAPI(title="KomgaRead API", lifespan=lifespan)

# 初始化校验错误不回显输入，避免 API 密钥出现在响应和诊断记录中。


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    if request.url.path == "/api/auth/register":
        return JSONResponse({"detail": "请填写有效邮箱和邀请码，密码至少 8 个字符且不超过 72 字节，两次密码须一致"}, status_code=422)
    if request.url.path.startswith("/api/setup"):
        return JSONResponse({"detail": "请检查初始化密钥、Komga 地址、API 密钥和注册邀请码是否填写完整且格式正确"}, status_code=422)
    return await request_validation_exception_handler(request, exc)
# 凭据保存在 /data 映射下，更新容器、后端重启后仍可使用。
sessions = SessionStore(Path(__file__).resolve().parents[1] / "data" / "sessions.sqlite3")


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=4096)


def origin_key(value: str):
    """只接受 HTTP(S) 来源，统一默认端口；拒绝路径、用户信息等异常格式。"""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None or parsed.path or parsed.query or parsed.fragment:
            return None
        return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None


def allowed_origin(value: str) -> bool:
    origin = origin_key(value)
    if origin is None:
        return False
    return "*" in ALLOWED_ORIGINS or any(origin == origin_key(item) for item in ALLOWED_ORIGINS)


@app.middleware("http")
async def protect_requests(request: Request, call_next):
    # 来源策略与 CORS 保持一致；默认允许任意有效 HTTP(S) Origin。
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not allowed_origin(request.headers.get("origin", "")):
            return JSONResponse({"detail": "请求来源未获允许"}, status_code=403)
    session_id = request.cookies.get(COOKIE_NAME, "")
    context = session_context.set(session_id)
    try:
        response = await call_next(request)
    finally:
        session_context.reset(context)
    if response.status_code == 401 and session_id and session_id not in sessions:
        response.delete_cookie(COOKIE_NAME, path="/api", secure=COOKIE_SECURE, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return response


class OriginCORSMiddleware(CORSMiddleware):
    def is_allowed_origin(self, origin: str) -> bool:
        return allowed_origin(origin)


# 放在外层，使来源拒绝等错误响应也带有正确的 CORS 头。
# 带凭据时返回具体 Origin，不使用 Access-Control-Allow-Origin: *。
app.add_middleware(OriginCORSMiddleware, allow_credentials=True,
                   allow_methods=["GET", "HEAD", "POST", "PATCH", "OPTIONS"],
                   allow_headers=["Content-Type"])


def komga_url():
    from .setup import configured_url
    return configured_url(KOMGA_URL)


def set_session_cookie(response, session_id):
    response.set_cookie(COOKIE_NAME, session_id, max_age=SESSION_SECONDS, httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/api")


def remember_credentials(response):
    for header in response.headers.get_list("set-cookie"):
        cookie = SimpleCookie()
        cookie.load(header)
        if REMEMBER_COOKIE in cookie:
            value = cookie[REMEMBER_COOKIE]
            expires = 0
            try:
                if value["max-age"]:
                    expires = time() + int(value["max-age"])
                elif value["expires"]:
                    expires = parsedate_to_datetime(value["expires"]).timestamp()
            except (ValueError, TypeError, OverflowError):
                pass
            return value.value, expires
    return None, None


async def send_komga(method: str, path: str, **kwargs):
    url = komga_url()
    if not url:
        raise HTTPException(503, "请先在启动页面配置 Komga 地址")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.request(method, f"{url}{path}", **kwargs)
    except httpx.RequestError:
        raise HTTPException(502, "无法连接 Komga，请检查地址或网络") from None
    return response


async def recover_komga_session(session_id, failed_token):
    async with recovery_locks[hash(session_id) % len(recovery_locks)]:
        entry = sessions.details(session_id)
        if not entry or entry["expires"] <= time() or (entry["origin"] and entry["origin"] != komga_url()):
            sessions.pop(session_id, None)
            raise HTTPException(401, "登录已过期，请重新登录")
        if entry["token"] != failed_token:
            return entry["token"]
        if not entry["remember"] or (entry["remember_expires"] and entry["remember_expires"] <= time()):
            sessions.pop(session_id, None)
            raise HTTPException(401, "登录已过期，请重新登录")
        cookie = SimpleCookie()
        cookie[REMEMBER_COOKIE] = entry["remember"]
        response = await send_komga("GET", "/api/v2/users/me", headers={"X-Auth-Token": "", "Cookie": cookie.output(header="").strip()})
        if response.status_code == 401:
            sessions.pop(session_id, None)
            raise HTTPException(401, "长期登录凭据已失效，请重新登录")
        if not response.is_success:
            raise HTTPException(502, "Komga 登录恢复暂时失败，请稍后重试")
        user = public_user(response)
        if entry["user_id"] and entry["user_id"] != user["id"]:
            sessions.pop(session_id, None)
            raise HTTPException(401, "登录身份发生变化，请重新登录")
        token = response.headers.get("X-Auth-Token")
        if not token:
            raise HTTPException(502, "Komga 未返回恢复后的会话")
        remember, expires = remember_credentials(response)
        sessions.credentials(session_id, token, remember, expires)
        if session_id not in sessions:
            raise HTTPException(401, "登录已退出")
        return token


async def komga_request(method: str, path: str, **kwargs) -> httpx.Response:
    session_id = session_context.get()
    token = kwargs.get("headers", {}).get("X-Auth-Token")
    entry = sessions.details(session_id) if session_id and token and "auth" not in kwargs and path != "/api/logout" else None
    if entry:
        kwargs["headers"] = {**kwargs["headers"], "X-Auth-Token": entry["token"]}
        token = entry["token"]
    response = await send_komga(method, path, **kwargs)
    if response.status_code == 401 and entry:
        token = await recover_komga_session(session_id, token)
        kwargs["headers"] = {**kwargs["headers"], "X-Auth-Token": token}
        response = await send_komga(method, path, **kwargs)
        if response.status_code == 401:
            sessions.pop(session_id, None)
    if response.status_code == 401:
        raise HTTPException(401, "账号或密码错误，或登录已过期")
    if response.status_code == 404:
        raise HTTPException(404, "漫画不存在或当前账号无法访问")
    if response.status_code == 403:
        raise HTTPException(403, "Komga 拒绝访问，请检查账号权限")
    if not response.is_success:
        raise HTTPException(502, "Komga 返回异常，请检查服务地址及版本")
    return response


def public_user(response: httpx.Response) -> dict:
    try:
        data = response.json()
        if not isinstance(data["id"], str) or not isinstance(data["email"], str):
            raise ValueError
        return {"id": data["id"], "email": data["email"]}
    except (ValueError, KeyError, TypeError):
        raise HTTPException(502, "Komga 用户信息格式不正确") from None


def current_token(request: Request) -> str:
    session_id = request.cookies.get(COOKIE_NAME, "")
    entry = sessions.details(session_id)
    if not entry or entry["expires"] <= time():
        sessions.pop(session_id, None)
        raise HTTPException(401, "请先登录")
    if entry["origin"] and entry["origin"] != komga_url():
        sessions.pop(session_id, None)
        raise HTTPException(401, "漫画服务器已更换，请重新登录")
    return entry["token"]


class ResourceLookupInput(BaseModel):
    jmid: str = Field(pattern=r"^[0-9]{1,20}$")


@app.post("/api/resource/lookup", status_code=204)
async def lookup_resource(data: ResourceLookupInput, request: Request):
    current_token(request)
    jmid = data.jmid
    client = JmOption.default().new_jm_client()
    cover_dir = Path(__file__).resolve().parents[1] / 'data' / 'jm'
    cover_dir.mkdir(parents=True, exist_ok=True)
    cover_path = cover_dir / f'{jmid}.png'
    client.download_album_cover(jmid, str(cover_path))
    return Response(status_code=204)


@app.post("/api/auth/login")
async def login(data: LoginInput, request: Request, response: Response):
    # 密码仅用于此次验证，不写入磁盘或会话。
    upstream = await komga_request("GET", "/api/v2/users/me", auth=httpx.BasicAuth(data.username, data.password), headers={"X-Auth-Token": ""}, params={"remember-me": "true"})
    user = public_user(upstream)
    token = upstream.headers.get("X-Auth-Token")
    if not token:
        raise HTTPException(502, "Komga 未返回会话，请检查服务或反向代理配置")
    now = time()
    sessions.prune(now)
    sessions.pop(request.cookies.get(COOKIE_NAME, ""), None)
    session_id = token_urlsafe(32)
    remember, remember_expires = remember_credentials(upstream)
    sessions.create(session_id, token, now + SESSION_SECONDS, remember or "", remember_expires or 0, komga_url(), user["id"])
    set_session_cookie(response, session_id)
    return user


@app.get("/api/auth/me")
async def me(request: Request, response: Response):
    token = current_token(request)
    try:
        user = public_user(await komga_request("GET", "/api/v2/users/me", headers={"X-Auth-Token": token}))
        # 前端仅在网站启动／刷新时调用；普通 API 和图片不延长本站会话。
        session_id = request.cookies.get(COOKIE_NAME, "")
        now = time()
        if not await run_in_threadpool(sessions.touch, session_id, now, now + SESSION_SECONDS):
            raise HTTPException(401, "登录已过期，请重新登录")
        set_session_cookie(response, session_id)
        return user
    except HTTPException as exc:
        if exc.status_code == 401:
            sessions.pop(request.cookies.get(COOKIE_NAME, ""), None)
        raise


@app.post("/api/auth/logout", status_code=204)
async def logout(request: Request):
    # 先撤销本站会话，即使 Komga 暂时离线也能退出。
    session_id = request.cookies.get(COOKIE_NAME, "")
    details = sessions.details(session_id)
    entry = sessions.pop(session_id, None)
    if entry:
        try:
            if not details["origin"] or details["origin"] == komga_url():
                headers = {"X-Auth-Token": entry[0]}
                if details["remember"]:
                    cookie = SimpleCookie()
                    cookie[REMEMBER_COOKIE] = details["remember"]
                    headers["Cookie"] = cookie.output(header="").strip()
                await komga_request("POST", "/api/logout", headers=headers)
        except HTTPException:
            pass
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/api", secure=COOKIE_SECURE, httponly=True, samesite="lax")
    return response

# 随机抽取索引，再只读取对应系列，不将整个书库下载到网站。
async def select_recommendations(request: Request, count: int = 4):
    import asyncio
    from random import sample
    from urllib.parse import quote

    token = current_token(request)
    headers = {"X-Auth-Token": token}

    async def read_page(index: int):
        upstream = await komga_request(
            "POST", "/api/v1/series/list", headers=headers,
            params={"page": index, "size": 1, "sort": "metadata.titleSort,asc"}, json={},
        )
        try:
            page = upstream.json()
            if not isinstance(page["content"], list) or not isinstance(page["totalElements"], int) or page["totalElements"] < 0:
                raise ValueError
            return page
        except (ValueError, KeyError, TypeError):
            raise HTTPException(502, "Komga 系列列表格式不正确") from None

    first = await read_page(0)
    total = first["totalElements"]
    indices = sample(range(total), min(count, total))
    pages = await asyncio.gather(*(read_page(index) if index else asyncio.sleep(0, result=first) for index in indices))
    result = []
    seen = set()
    try:
        for page in pages:
            for series in page["content"]:
                series_id = series["id"]
                if not isinstance(series_id, str):
                    raise ValueError
                if series_id in seen:
                    continue
                seen.add(series_id)
                result.append({
                    "id": series_id,
                    "title": series.get("metadata", {}).get("title") or series.get("name") or "未命名系列",
                    "genres": series.get("metadata", {}).get("genres") or [],
                    "booksCount": series.get("booksCount", 0),
                    "thumbnailUrl": f"/api/series/{quote(series_id, safe='')}/thumbnail",
                })
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(502, "Komga 系列信息格式不正确") from None
    return result


@app.get("/api/series/recommendations")
async def recommendations(request: Request):
    import asyncio
    from .search import fill_last_release
    from . import daily
    from urllib.parse import quote
    token = current_token(request)
    headers = {"X-Auth-Token": token}
    user = public_user(await komga_request("GET", "/api/v2/users/me", headers=headers))
    async with daily.generation_lock(user["id"]):
        day = daily.china_day()
        items = await run_in_threadpool(daily.read, user["id"], day, count=8)
        if items is None:
            items = await select_recommendations(request, count=8)
            await run_in_threadpool(daily.write, user["id"], day, items, count=8)
    # 每次仍检查权限，避免已删除或被撤销权限的系列继续展示。
    visible = []
    for item in items:
        try:
            data = read_json(await komga_request("GET", f"/api/v1/series/{quote(item['id'], safe='')}", headers=headers))
            visible.append({**item, "genres": data.get("metadata", {}).get("genres") or []})
        except HTTPException as exc:
            if exc.status_code not in {403, 404}:
                raise
    return await fill_last_release(visible, komga_request, headers, read_json, asyncio.Semaphore(3))

@app.get("/api/series/{series_id}/thumbnail")
async def series_thumbnail(series_id: str, request: Request):
    from urllib.parse import quote

    token = current_token(request)
    upstream = await komga_request("GET", f"/api/v1/series/{quote(series_id, safe='')}/thumbnail", headers={"X-Auth-Token": token})
    media_type = upstream.headers.get("content-type", "").split(";")[0]
    if media_type not in {"image/jpeg", "image/png", "image/webp", "image/avif", "image/gif"}:
        raise HTTPException(502, "Komga 返回的封面格式不正确")
    return Response(upstream.content, media_type=media_type, headers={"X-Content-Type-Options": "nosniff"})

@app.get("/api/series/recent")
async def recent_series(request: Request):
    import asyncio
    from .search import fill_last_release
    from urllib.parse import quote

    token = current_token(request)
    upstream = await komga_request(
        "POST", "/api/v1/series/list", headers={"X-Auth-Token": token},
        params={"page": 0, "size": 8, "sort": "createdDate,desc"}, json={},
    )
    try:
        content = upstream.json()["content"]
        if not isinstance(content, list):
            raise ValueError
        result = []
        for series in content[:8]:
            series_id = series["id"]
            if not isinstance(series_id, str):
                raise ValueError
            result.append({
                "id": series_id,
                "title": series.get("metadata", {}).get("title") or series.get("name") or "未命名系列",
                "genres": series.get("metadata", {}).get("genres") or [],
                "booksCount": series.get("booksCount", 0),
                "thumbnailUrl": f"/api/series/{quote(series_id, safe='')}/thumbnail",
            })
        return await fill_last_release(result, komga_request, {"X-Auth-Token": token}, read_json, asyncio.Semaphore(3))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(502, "Komga 最近添加列表格式不正确") from None

# 阅读接口：每个请求都使用当前用户的会话，由 Komga 检查书库权限。
def read_json(upstream: httpx.Response):
    try:
        return upstream.json()
    except ValueError:
        raise HTTPException(502, "Komga 返回的数据格式不正确") from None


@app.get("/api/series/{series_id}")
async def series_details(series_id: str, request: Request):
    from urllib.parse import quote
    data = read_json(await komga_request("GET", f"/api/v1/series/{quote(series_id, safe='')}", headers={"X-Auth-Token": current_token(request)}))
    metadata = data.get("metadata", {})
    book_metadata = data.get("booksMetadata") or {}
    contributors = book_metadata.get("authors") or []
    # 优先显示编剧／作者，缺少此角色时再显示其他贡献者。
    writers = [author for author in contributors if author.get("role", "").lower() == "writer"]
    authors = list(dict.fromkeys(author["name"] for author in (writers or contributors) if author.get("name")))
    tags = sorted(set((metadata.get("tags") or []) + (book_metadata.get("tags") or [])))
    return {
        "id": data["id"], "title": metadata.get("title") or data.get("name"),
        "summary": metadata.get("summary") or book_metadata.get("summary") or "",
        "booksCount": data.get("booksCount", 0), "publisher": metadata.get("publisher") or "",
        "authors": authors, "genres": metadata.get("genres") or [], "tags": tags,
        "thumbnailUrl": f"/api/series/{quote(series_id, safe='')}/thumbnail",
    }


@app.get("/api/series/{series_id}/books")
async def series_books(series_id: str, request: Request, page: int = 0, order: str = "asc"):
    from urllib.parse import quote
    if order not in {"asc", "desc"}:
        raise HTTPException(422, "排序方式必须为 asc 或 desc")
    if page < 0:
        raise HTTPException(422, "页码不能为负数")
    data = read_json(await komga_request("POST", "/api/v1/books/list", headers={"X-Auth-Token": current_token(request)}, params={"page": page, "size": 48, "sort": f"metadata.numberSort,{order}"}, json={"condition": {"seriesId": {"operator": "is", "value": series_id}}}))
    return {"items": [{"id": book["id"], "title": book.get("metadata", {}).get("title") or book.get("name") or "未命名书籍", "pagesCount": book.get("media", {}).get("pagesCount", 0), "readProgress": book.get("readProgress"), "thumbnailUrl": f"/api/books/{quote(book['id'], safe='')}/thumbnail"} for book in data["content"]], "last": data["last"]}


@app.get("/api/books/{book_id}")
async def book_details(book_id: str, request: Request):
    from urllib.parse import quote
    data = read_json(await komga_request("GET", f"/api/v1/books/{quote(book_id, safe='')}", headers={"X-Auth-Token": current_token(request)}))
    return {"id": data["id"], "seriesId": data["seriesId"], "title": data.get("metadata", {}).get("title") or data.get("name"), "pagesCount": data.get("media", {}).get("pagesCount", 0), "readProgress": data.get("readProgress")}


async def book_image(book_id: str, request: Request, suffix: str, params=None):
    from urllib.parse import quote
    from fastapi.responses import StreamingResponse
    from starlette.background import BackgroundTask
    token = current_token(request)
    url = komga_url()
    if not url:
        raise HTTPException(503, "请先配置 Komga")
    client = httpx.AsyncClient(timeout=30, follow_redirects=False)
    try:
        upstream = await client.send(client.build_request("GET", f"{url}/api/v1/books/{quote(book_id, safe='')}/{suffix}", headers={"X-Auth-Token": token, "Accept": "image/jpeg"}, params=params), stream=True)
        if upstream.status_code == 401:
            await upstream.aclose()
            token = await recover_komga_session(request.cookies.get(COOKIE_NAME, ""), token)
            upstream = await client.send(client.build_request("GET", f"{url}/api/v1/books/{quote(book_id, safe='')}/{suffix}", headers={"X-Auth-Token": token, "Accept": "image/jpeg"}, params=params), stream=True)
            if upstream.status_code == 401:
                sessions.pop(request.cookies.get(COOKIE_NAME, ""), None)
    except HTTPException:
        await client.aclose()
        raise
    except httpx.RequestError:
        await client.aclose()
        raise HTTPException(502, "漫画图片连接失败") from None
    media_type = upstream.headers.get("content-type", "").split(";")[0]
    if not upstream.is_success or media_type not in {"image/jpeg", "image/png", "image/webp", "image/avif", "image/gif"}:
        status = upstream.status_code if upstream.status_code in {401, 403, 404} else 502
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status, "图片不可用，请检查权限、页码或 Komga 状态")
    async def close():
        await upstream.aclose()
        await client.aclose()
    return StreamingResponse(upstream.aiter_bytes(), media_type=media_type, background=BackgroundTask(close), headers={"X-Content-Type-Options": "nosniff"})


@app.get("/api/books/{book_id}/thumbnail")
async def book_thumbnail(book_id: str, request: Request):
    return await book_image(book_id, request, "thumbnail")


@app.get("/api/books/{book_id}/pages/{page_number}")
async def book_page(book_id: str, page_number: int, request: Request):
    if page_number < 1:
        raise HTTPException(422, "页码从 1 开始")
    return await book_image(book_id, request, f"pages/{page_number}", {"convert": "jpeg", "zero_based": "false"})


class ProgressInput(BaseModel):
    page: int = Field(ge=1, strict=True)


@app.patch("/api/books/{book_id}/progress", status_code=204)
async def save_book_progress(book_id: str, data: ProgressInput, request: Request):
    from urllib.parse import quote
    token = current_token(request)
    path = f"/api/v1/books/{quote(book_id, safe='')}"
    headers = {"X-Auth-Token": token}
    book = read_json(await komga_request("GET", path, headers=headers))
    total = book.get("media", {}).get("pagesCount", 0)
    if data.page > total:
        raise HTTPException(422, "页码超过书籍总页数")
    # 已读完后回看前面的页面不撤销完成标记。
    completed = bool((book.get("readProgress") or {}).get("completed")) or data.page == total
    await komga_request("PATCH", f"{path}/read-progress", headers=headers, json={"page": data.page, "completed": completed})
    return Response(status_code=204)

# 组合独立搜索路由，外部地址保持 /api/search。
from .search import create_search_router

app.include_router(create_search_router(
    lambda *args, **kwargs: komga_request(*args, **kwargs),
    current_token,
    read_json,
))

from .setup import create_setup_router

app.include_router(create_setup_router(komga_url))

from .registration import create_registration_router

app.include_router(create_registration_router(komga_url))

from .reactions import create_reactions_router

app.include_router(create_reactions_router(
    lambda *args, **kwargs: komga_request(*args, **kwargs), current_token, public_user,
))

from .personal import create_personal_router

app.include_router(create_personal_router(
    lambda *args, **kwargs: komga_request(*args, **kwargs), current_token, public_user, read_json,
))

from .browse import create_browse_router

app.include_router(create_browse_router(
    lambda *args, **kwargs: komga_request(*args, **kwargs), current_token, read_json,
    lambda request: select_recommendations(request, 12),
))
