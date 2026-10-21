"""使用后端管理员 API 密钥创建普通 Komga 用户。"""
import json
import re
from collections import deque
from secrets import compare_digest
from time import monotonic

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from . import setup


def registration_credentials() -> tuple[str, str]:
    if not setup.CONFIG_FILE.exists():
        return "", ""
    try:
        config = json.loads(setup.CONFIG_FILE.read_text(encoding="utf-8"))
        key = config.get("api_key", "")
        invite = config.get("invite_code", "")
        if not isinstance(key, str) or not isinstance(invite, str):
            raise ValueError
        return key, invite
    except (OSError, ValueError, AttributeError):
        raise HTTPException(503, "无法读取注册配置，请联系管理员") from None


class RegisterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=8, max_length=72)
    confirm_password: SecretStr = Field(min_length=8, max_length=72)
    invite_code: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip()
        if not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", value):
            raise ValueError("请输入有效邮箱")
        return value

    @model_validator(mode="after")
    def valid_password(self):
        password = self.password.get_secret_value()
        if not password.strip() or len(password.encode("utf-8")) > 72:
            raise ValueError("密码至少 8 个字符，UTF-8 编码不超过 72 字节")
        if password != self.confirm_password.get_secret_value():
            raise ValueError("两次密码不一致")
        return self


def create_registration_router(get_url):
    router = APIRouter(prefix="/api/auth", tags=["registration"])
    attempts = deque()

    @router.get("/registration")
    async def status():
        key, invite = registration_credentials()
        return {"enabled": bool(key and invite and get_url())}

    @router.post("/register", status_code=201)
    async def register(data: RegisterInput):
        key, invite = registration_credentials()
        url = get_url()
        if not key or not invite or not url:
            raise HTTPException(503, "注册暂未开放，请联系管理员配置 API 密钥和邀请码")
        now = monotonic()
        while attempts and attempts[0] <= now - 60:
            attempts.popleft()
        # 单实例限制总创建请求，不依赖可伪造的转发 IP。
        if len(attempts) >= 10:
            raise HTTPException(429, "注册请求过于频繁，请一分钟后重试")
        attempts.append(now)
        if not compare_digest(data.invite_code.get_secret_value().strip().encode("utf-8"), invite.encode("utf-8")):
            raise HTTPException(403, "邀请码不正确")
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                response = await client.post(f"{url}/api/v2/users", headers={"X-API-Key": key}, json={
                    "email": data.email,
                    "password": data.password.get_secret_value(),
                    "roles": ["PAGE_STREAMING"],
                    "sharedLibraries": {"all": True, "libraryIds": []},
                })
        except httpx.RequestError:
            raise HTTPException(502, "无法连接 Komga，注册结果尚未确认，请先尝试登录再重试") from None
        if response.status_code in {400, 409}:
            raise HTTPException(409, "邮箱已被使用或 Komga 不接受该邮箱、密码，请检查后重试")
        if response.status_code in {401, 403}:
            raise HTTPException(503, "注册服务的管理员密钥无效或权限不足，请联系管理员")
        if response.status_code not in {200, 201, 204}:
            raise HTTPException(502, "Komga 注册响应异常，请先尝试登录再重试")
        return {"message": "注册成功，请使用邮箱和密码登录"}

    return router
