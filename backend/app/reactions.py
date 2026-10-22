"""按 Komga 用户与系列持久化点赞、收藏，并统计全体用户总数。"""
import asyncio
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from threading import Lock
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

STORE = Path(__file__).resolve().parents[1] / "data" / "reactions.sqlite3"


_initialization_lock = Lock()
_initialized_path = None


def initialize_store():
    """每个数据库路径仅初始化一次；保留旧数据的迁移，在事务成功后标记完成。"""
    global _initialized_path
    path = STORE.resolve()
    if _initialized_path == path:
        return
    with _initialization_lock:
        if _initialized_path == path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS reactions (user_id TEXT NOT NULL, series_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('like','favorite')), sort_order INTEGER NOT NULL, PRIMARY KEY(user_id,series_id,kind))")
            columns = {row[1] for row in db.execute("PRAGMA table_info(reactions)")}
            if "sort_order" not in columns:
                # 重建表，将原顺序转为序号，并真正移除旧时间字段。
                ordering = "created_at,rowid" if "created_at" in columns else "rowid"
                db.execute("CREATE TABLE reactions_new (user_id TEXT NOT NULL, series_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('like','favorite')), sort_order INTEGER NOT NULL, PRIMARY KEY(user_id,series_id,kind))")
                db.execute(f"INSERT INTO reactions_new SELECT user_id,series_id,kind,ROW_NUMBER() OVER (ORDER BY {ordering}) FROM reactions")
                db.execute("DROP TABLE reactions")
                db.execute("ALTER TABLE reactions_new RENAME TO reactions")
            db.execute("CREATE INDEX IF NOT EXISTS reactions_series ON reactions(series_id,kind)")
            db.execute("CREATE INDEX IF NOT EXISTS reactions_personal ON reactions(user_id,kind,sort_order DESC)")
            db.execute("CREATE TABLE IF NOT EXISTS browsing_history (user_id TEXT NOT NULL, series_id TEXT NOT NULL, sort_order INTEGER NOT NULL, PRIMARY KEY(user_id,series_id))")
            if "sort_order" not in {row[1] for row in db.execute("PRAGMA table_info(browsing_history)")}:
                db.execute("CREATE TABLE browsing_history_new (user_id TEXT NOT NULL, series_id TEXT NOT NULL, sort_order INTEGER NOT NULL, PRIMARY KEY(user_id,series_id))")
                db.execute("INSERT INTO browsing_history_new SELECT user_id,series_id,ROW_NUMBER() OVER (ORDER BY visited_at,rowid) FROM browsing_history")
                db.execute("DROP TABLE browsing_history")
                db.execute("ALTER TABLE browsing_history_new RENAME TO browsing_history")
            db.execute("CREATE INDEX IF NOT EXISTS history_personal ON browsing_history(user_id,sort_order DESC)")
            db.execute("CREATE TABLE IF NOT EXISTS user_profiles (user_id TEXT PRIMARY KEY, display_name TEXT NOT NULL)")
        _initialized_path = path


@contextmanager
def open_store(*, write=False):
    initialize_store()
    with closing(sqlite3.connect(STORE, timeout=10)) as db, db:
        if not write:
            db.execute("PRAGMA query_only=ON")
        # 读取使用普通快照事务；只有修改数据时才预先取得写锁。
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield db


def reaction_state(user_id, series_id, kind=None, selected=None):
    with open_store(write=kind is not None) as db:
        # 显式设置状态而非翻转，重复请求、快速双击不会重复计数。
        if kind:
            if selected:
                next_order = db.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM reactions WHERE user_id=? AND kind=?", (user_id, kind)).fetchone()[0]
                db.execute("INSERT OR IGNORE INTO reactions(user_id,series_id,kind,sort_order) VALUES (?,?,?,?)", (user_id, series_id, kind, next_order))
            else:
                db.execute("DELETE FROM reactions WHERE user_id=? AND series_id=? AND kind=?", (user_id, series_id, kind))
        counts = dict(db.execute("SELECT kind,COUNT(*) FROM reactions WHERE series_id=? GROUP BY kind", (series_id,)))
        own = {row[0] for row in db.execute("SELECT kind FROM reactions WHERE user_id=? AND series_id=?", (user_id, series_id))}
        return {"liked": "like" in own, "favorited": "favorite" in own, "likesCount": counts.get("like", 0), "favoritesCount": counts.get("favorite", 0)}


class ReactionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["like", "favorite"]
    selected: bool = Field(strict=True)


def create_reactions_router(komga_request, current_token, public_user):
    router = APIRouter(prefix="/api/series", tags=["reactions"])

    async def user_for_series(request, series_id):
        headers = {"X-Auth-Token": current_token(request)}
        user, _ = await asyncio.gather(
            komga_request("GET", "/api/v2/users/me", headers=headers),
            komga_request("GET", f"/api/v1/series/{quote(series_id, safe='')}", headers=headers),
        )
        return public_user(user)["id"]

    async def state(request, series_id, kind=None, selected=None):
        user_id = await user_for_series(request, series_id)
        try:
            return await run_in_threadpool(reaction_state, user_id, series_id, kind, selected)
        except (sqlite3.Error, OSError):
            raise HTTPException(503, "点赞和收藏暂时不可用，请稍后重试") from None

    @router.get("/{series_id}/reactions")
    async def get_reactions(series_id: str, request: Request):
        return await state(request, series_id)

    @router.patch("/{series_id}/reactions")
    async def set_reaction(series_id: str, data: ReactionInput, request: Request):
        return await state(request, series_id, data.kind, data.selected)

    return router
