from pathlib import Path
from time import time
from secrets import token_urlsafe
import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
KOMGA_URL = os.getenv("KOMGA_URL", "").rstrip("/")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
ALLOWED_ORIGINS = set(os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(","))
COOKIE_NAME = "komgaread_session"
SESSION_SECONDS = 8 * 60 * 60

app = FastAPI(title="KomgaRead API")
# 学习阶段用内存保存会话。重启会退出登录；只运行一个 worker。
sessions: dict[str, tuple[str, float]] = {}


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=4096)


@app.middleware("http")
async def protect_requests(request: Request, call_next):
    # 防止其他网站利用浏览器 Cookie 发起登录或退出请求。
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") not in ALLOWED_ORIGINS:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "请求来源未获允许"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


async def komga_request(method: str, path: str, **kwargs) -> httpx.Response:
    if not KOMGA_URL:
        raise HTTPException(503, "请先在后端配置 KOMGA_URL")
    try:
        # 每次独立客户端，避免不同用户之间共享 Komga Cookie。
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.request(method, f"{KOMGA_URL}{path}", **kwargs)
    except httpx.RequestError:
        raise HTTPException(502, "无法连接 Komga，请检查地址或网络") from None
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
    entry = sessions.get(session_id)
    if not entry or entry[1] <= time():
        sessions.pop(session_id, None)
        raise HTTPException(401, "请先登录")
    return entry[0]


@app.post("/api/auth/login")
async def login(data: LoginInput, request: Request, response: Response):
    # 密码仅用于此次验证，不写入磁盘或会话。
    upstream = await komga_request("GET", "/api/v2/users/me", auth=httpx.BasicAuth(data.username, data.password), headers={"X-Auth-Token": ""})
    user = public_user(upstream)
    token = upstream.headers.get("X-Auth-Token")
    if not token:
        raise HTTPException(502, "Komga 未返回会话，请检查服务或反向代理配置")
    now = time()
    for key in list(sessions):
        if sessions[key][1] <= now:
            sessions.pop(key, None)
    sessions.pop(request.cookies.get(COOKIE_NAME, ""), None)
    session_id = token_urlsafe(32)
    sessions[session_id] = (token, now + SESSION_SECONDS)
    response.set_cookie(COOKIE_NAME, session_id, max_age=SESSION_SECONDS, httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/api")
    return user


@app.get("/api/auth/me")
async def me(request: Request):
    token = current_token(request)
    try:
        return public_user(await komga_request("GET", "/api/v2/users/me", headers={"X-Auth-Token": token}))
    except HTTPException as exc:
        if exc.status_code == 401:
            sessions.pop(request.cookies.get(COOKIE_NAME, ""), None)
        raise


@app.post("/api/auth/logout", status_code=204)
async def logout(request: Request):
    # 先撤销本站会话，即使 Komga 暂时离线也能退出。
    entry = sessions.pop(request.cookies.get(COOKIE_NAME, ""), None)
    if entry:
        try:
            await komga_request("POST", "/api/logout", headers={"X-Auth-Token": entry[0]})
        except HTTPException:
            pass
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/api", secure=COOKIE_SECURE, httponly=True, samesite="lax")
    return response

# 随机抽取索引，再只读取对应系列，不将整个书库下载到网站。
async def select_recommendations(request: Request):
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
    indices = sample(range(total), min(4, total))
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
                    "booksCount": series.get("booksCount", 0),
                    "thumbnailUrl": f"/api/series/{quote(series_id, safe='')}/thumbnail",
                })
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(502, "Komga 系列信息格式不正确") from None
    return result


@app.get("/api/series/recommendations")
async def recommendations(request: Request):
    from . import daily
    from urllib.parse import quote
    token = current_token(request)
    headers = {"X-Auth-Token": token}
    user = public_user(await komga_request("GET", "/api/v2/users/me", headers=headers))
    async with daily.lock:
        day = daily.china_day()
        items = daily.read(user["id"], day)
        if items is None:
            items = await select_recommendations(request)
            daily.write(user["id"], day, items)
    # 每次仍检查权限，避免已删除或被撤销权限的系列继续展示。
    visible = []
    for item in items:
        try:
            await komga_request("GET", f"/api/v1/series/{quote(item['id'], safe='')}", headers=headers)
            visible.append(item)
        except HTTPException as exc:
            if exc.status_code not in {403, 404}:
                raise
    return visible

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
    from urllib.parse import quote

    token = current_token(request)
    upstream = await komga_request(
        "POST", "/api/v1/series/list", headers={"X-Auth-Token": token},
        params={"page": 0, "size": 4, "sort": "createdDate,desc"}, json={},
    )
    try:
        content = upstream.json()["content"]
        if not isinstance(content, list):
            raise ValueError
        result = []
        for series in content[:4]:
            series_id = series["id"]
            if not isinstance(series_id, str):
                raise ValueError
            result.append({
                "id": series_id,
                "title": series.get("metadata", {}).get("title") or series.get("name") or "未命名系列",
                "booksCount": series.get("booksCount", 0),
                "thumbnailUrl": f"/api/series/{quote(series_id, safe='')}/thumbnail",
            })
        return result
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
    if not KOMGA_URL:
        raise HTTPException(503, "请先配置 Komga")
    client = httpx.AsyncClient(timeout=30, follow_redirects=False)
    try:
        upstream = await client.send(client.build_request("GET", f"{KOMGA_URL}/api/v1/books/{quote(book_id, safe='')}/{suffix}", headers={"X-Auth-Token": token, "Accept": "image/jpeg"}, params=params), stream=True)
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
