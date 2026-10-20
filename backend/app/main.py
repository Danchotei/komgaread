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
