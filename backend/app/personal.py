"""用户浏览历史和收藏列表，与点赞收藏共用持久化数据目录。"""
import asyncio
import sqlite3
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from .reactions import open_store
from .search import fill_last_release

PAGE_SIZE = 16


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=40)


def profile_name(user_id, name=None):
    with open_store(write=name is not None) as db:
        if name is not None:
            db.execute("INSERT INTO user_profiles VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET display_name=excluded.display_name", (user_id, name))
        row = db.execute("SELECT display_name FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
        return row[0] if row else None


def favorite_series_ids(user_id):
    with open_store() as db:
        return [row[0] for row in db.execute("SELECT series_id FROM reactions WHERE user_id=? AND kind='favorite' ORDER BY sort_order DESC", (user_id,))]


def record_visit(user_id, series_id):
    with open_store(write=True) as db:
        next_order = db.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM browsing_history WHERE user_id=?", (user_id,)).fetchone()[0]
        db.execute("INSERT INTO browsing_history VALUES (?,?,?) ON CONFLICT(user_id,series_id) DO UPDATE SET sort_order=excluded.sort_order", (user_id, series_id, next_order))
        db.execute("DELETE FROM browsing_history WHERE user_id=? AND series_id NOT IN (SELECT series_id FROM browsing_history WHERE user_id=? ORDER BY sort_order DESC LIMIT 50)", (user_id, user_id))


def stored_list(user_id, kind, page):
    with open_store() as db:
        if kind == "history":
            rows = db.execute("SELECT series_id FROM browsing_history WHERE user_id=? ORDER BY sort_order DESC LIMIT ? OFFSET ?", (user_id, PAGE_SIZE + 1, page * PAGE_SIZE)).fetchall()
        else:
            rows = db.execute("SELECT series_id FROM reactions WHERE user_id=? AND kind='favorite' ORDER BY sort_order DESC LIMIT ? OFFSET ?", (user_id, PAGE_SIZE + 1, page * PAGE_SIZE)).fetchall()
        return [row[0] for row in rows[:PAGE_SIZE]], len(rows) <= PAGE_SIZE


def create_personal_router(komga_request, current_token, public_user, read_json):
    router = APIRouter(tags=["personal"])

    async def identity(request):
        headers = {"X-Auth-Token": current_token(request)}
        user = public_user(await komga_request("GET", "/api/v2/users/me", headers=headers))
        return user["id"], headers

    async def storage(function, *args):
        try:
            return await run_in_threadpool(function, *args)
        except (sqlite3.Error, OSError):
            raise HTTPException(503, "个人记录暂时不可用，请重试") from None

    @router.get("/api/me/profile")
    async def profile(request: Request):
        headers = {"X-Auth-Token": current_token(request)}
        user = public_user(await komga_request("GET", "/api/v2/users/me", headers=headers))
        name = await storage(profile_name, user["id"])
        return {"displayName": name or user["email"]}

    @router.patch("/api/me/profile")
    async def update_profile(data: ProfileInput, request: Request):
        name = data.display_name.strip()
        if not name or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise HTTPException(422, "名字应为 1–40 个字符，不能包含换行或控制字符")
        user_id, _ = await identity(request)
        return {"displayName": await storage(profile_name, user_id, name)}

    @router.post("/api/series/{series_id}/visit", status_code=204)
    async def visit(series_id: str, request: Request):
        user_id, headers = await identity(request)
        await komga_request("GET", f"/api/v1/series/{quote(series_id, safe='')}", headers=headers)
        await storage(record_visit, user_id, series_id)

    @router.get("/api/me/{kind}")
    async def list_series(kind: Literal["history", "favorites"], request: Request, page: int = Query(default=0, ge=0)):
        user_id, headers = await identity(request)
        ids, last = await storage(stored_list, user_id, kind, page)
        semaphore = asyncio.Semaphore(4)

        async def item(series_id):
            async with semaphore:
                try:
                    data = read_json(await komga_request("GET", f"/api/v1/series/{quote(series_id, safe='')}", headers=headers))
                except HTTPException as exc:
                    if exc.status_code in {403, 404}:
                        return None  # 已删除或无访问权限的系列不显示，也不清除原记录。
                    raise
                return {"id": series_id, "title": data.get("metadata", {}).get("title") or data.get("name") or "未命名系列", "genres": data.get("metadata", {}).get("genres") or [], "booksCount": data.get("booksCount", 0), "thumbnailUrl": f"/api/series/{quote(series_id, safe='')}/thumbnail"}

        items = await asyncio.gather(*(item(series_id) for series_id in ids))
        visible = [item for item in items if item is not None]
        await fill_last_release(visible, komga_request, headers, read_json, semaphore)
        return {"items": visible, "last": last}

    return router
