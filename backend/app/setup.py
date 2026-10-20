"""首次初始化入口；配置写入数据目录，初始化完成后禁止公开覆盖。"""
import asyncio
import json
import logging
import os
from pathlib import Path
from secrets import compare_digest, token_urlsafe
import tempfile
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

CONFIG_FILE = Path(__file__).resolve().parents[1] / "data" / "komga.json"
setup_lock = asyncio.Lock()


def setup_key() -> str:
    explicit = os.getenv("SETUP_KEY", "")
    if explicit:
        if len(explicit) < 16:
            raise HTTPException(503, "手动设置的 SETUP_KEY 至少需要 16 位；留空可自动生成")
        return explicit
    key_file = CONFIG_FILE.parent / "setup.key"
    try:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(token_urlsafe(32))
        key = key_file.read_text(encoding="utf-8").strip()
        if len(key) < 16:
            raise HTTPException(503, "初始化密钥文件无效，请管理员检查数据目录中的 setup.key")
        return key
    except OSError:
        raise HTTPException(503, "无法生成或读取初始化密钥，请检查数据目录写入权限（容器 UID 10001）") from None


def prepare_setup(get_url):
    if get_url():
        return
    key = setup_key()
    if not os.getenv("SETUP_KEY", ""):
        logging.getLogger("uvicorn.error").warning("KomgaRead initialization key / 初始化密钥: %s", key)


def normalize_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    try:
        url = urlsplit(value)
        if (url.scheme not in {"http", "https"} or not url.hostname
                or url.username is not None or url.password is not None
                or url.query or url.fragment or any(char.isspace() for char in value)):
            raise ValueError
        if url.port is not None and url.port < 1:
            raise ValueError
    except ValueError:
        raise ValueError("请填写完整的 HTTP/HTTPS 地址，不含账号密码、查询参数或片段") from None
    return value


def configured_url(legacy_primary: str) -> str:
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            primary = normalize_url(config["primary_url"])
            if not primary:
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(503, "Komga 配置文件无法读取，请管理员检查数据目录") from None
        # 迁移旧配置：不仅忽略备用地址，也从持久化文件中移除该字段。
        if "backup_url" in config:
            write_config(primary)
    else:
        primary = legacy_primary.strip().rstrip("/")
    return primary


class SetupInput(BaseModel):
    setup_key: str = Field(max_length=1024, repr=False)
    primary_url: str = Field(min_length=1, max_length=2048)

    @field_validator("primary_url")
    @classmethod
    def valid_url(cls, value):
        return normalize_url(value)

    @field_validator("primary_url")
    @classmethod
    def required_primary(cls, value):
        if not value:
            raise ValueError("请填写 Komga 公网地址")
        return value


async def probe(url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.get(f"{url}/api/v2/users/me")
        # 未登录的 Komga 通常返回 401；这里只测 API 可达性，账号仍需登录验证。
        reachable = response.status_code == 401
        if response.status_code == 200:
            try:
                data = response.json()
                reachable = isinstance(data, dict) and isinstance(data.get("id"), str) and isinstance(data.get("email"), str)
            except ValueError:
                pass
        return {"reachable": reachable, "message": "API 可连接，登录后验证账号" if reachable else f"API 返回 HTTP {response.status_code}，请检查地址或反向代理"}
    except httpx.RequestError:
        return {"reachable": False, "message": "连接失败，请确认容器可以访问此地址"}


def write_config(primary_url: str):
    temporary = None
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=CONFIG_FILE.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"primary_url": primary_url}, stream, ensure_ascii=False)
        temporary.chmod(0o600)
        temporary.replace(CONFIG_FILE)
    except OSError:
        raise HTTPException(503, "保存失败，请检查数据目录写入权限（容器 UID 10001）") from None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)


def create_setup_router(get_url):
    router = APIRouter(prefix="/api/setup", tags=["setup"])

    def require_setup(data: SetupInput):
        if get_url():
            raise HTTPException(409, "已完成初始化，不能通过此入口修改")
        key = setup_key()
        if not compare_digest(data.setup_key.encode(), key.encode()):
            raise HTTPException(403, "初始化密钥不正确")

    async def check_addresses(data):
        return [{"address": "primary", **await probe(data.primary_url)}]

    @router.get("")
    async def status():
        configured = bool(get_url())
        if not configured:
            setup_key()
        return {"configured": configured}

    @router.post("/test")
    async def test(data: SetupInput):
        require_setup(data)
        return {"checks": await check_addresses(data)}

    @router.post("")
    async def configure(data: SetupInput):
        async with setup_lock:
            require_setup(data)
            checks = await check_addresses(data)
            if not any(check["reachable"] for check in checks):
                raise HTTPException(422, "无法连接 Komga API，请先测试并检查公网地址")
            write_config(data.primary_url)
        return {"configured": True, "checks": checks}

    return router
