"""系列搜索路由。共享能力由入口传入，不反向导入 main，避免循环引用。"""
import asyncio
import sqlite3
import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from . import release_cache, search_snapshots


def series_card(item):
    return {"id": item["id"], "title": item.get("metadata", {}).get("title") or item.get("name") or "未命名系列", "booksCount": item.get("booksCount", 0), "genres": item.get("metadata", {}).get("genres") or [], "lastReleaseDate": item.get("lastReleaseDate"), "thumbnailUrl": f"/api/series/{quote(item['id'], safe='')}/thumbnail"}


async def fill_last_release(items, komga_request, headers, read_json, limiter):
    async def last_release(item):
        cache = release_cache.service
        if cache is not None and cache.connected:
            try:
                item["lastReleaseDate"] = await cache.refresh(item["id"])
                return item
            except (httpx.HTTPError, ValueError, KeyError, TypeError, sqlite3.Error, OSError):
                # 管理连接故障时仍按当前用户权限查询，不让缓存故障中断阅读。
                pass
        async with limiter:
            chapters = read_json(await komga_request("POST", "/api/v1/books/list", headers=headers,
                params={"page": 0, "size": 1, "sort": "metadata.numberSort,desc"},
                json={"condition": {"seriesId": {"operator": "is", "value": item["id"]}}}))
        content = chapters["content"]
        item["lastReleaseDate"] = content[0].get("metadata", {}).get("releaseDate") if content else None
        return item
    checked = await asyncio.gather(*(last_release(item) for item in items), return_exceptions=True)
    for item in checked:
        if isinstance(item, BaseException):
            raise item
    return checked


async def order_by_last_release(items, order, komga_request, headers, read_json, limiter):
    checked = await fill_last_release(items, komga_request, headers, read_json, limiter)
    known = [item for item in checked if item["lastReleaseDate"]]
    unknown = [item for item in checked if not item["lastReleaseDate"]]
    known.sort(key=lambda item: item["lastReleaseDate"], reverse=order == "desc")
    return known + unknown


def create_search_router(
    komga_request: Callable[..., Awaitable[httpx.Response]],
    current_token: Callable[[Request], str],
    read_json: Callable[[httpx.Response], Any],
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["搜索"])
    limiter = asyncio.Semaphore(3)

    @router.get("/search")
    async def search_series(request: Request, q: str = "", type: str = "all", page: int = 0, order: str | None = None, exact: bool = False, favorites: bool = False, snapshot: str = ""):
        if type not in {"all", "title", "author", "genre", "tag"} or page < 0 or not q.strip() or len(q) > 200:
            raise HTTPException(422, "请选择搜索类型并输入 1–200 字的关键词")
        if order not in {None, "asc", "desc"}:
            raise HTTPException(422, "排序方式必须为 asc 或 desc")
        headers = {"X-Auth-Token": current_token(request)}
        cache = release_cache.service
        revision = cache.revision if cache else 0
        signature = (q.strip(), type, order, exact, favorites)
        scope = None
        if snapshot:
            if not order or len(snapshot) > 128 or (snapshot == "new" and page != 0):
                raise HTTPException(422, "搜索快照参数不正确")
            # 每页验证实际 Komga 身份及当前权限，防止权限撤销后继续使用旧快照。
            identity = read_json(await komga_request("GET", "/api/v2/users/me", headers=headers))
            scope = hashlib.sha256((request.cookies.get("komgaread_session", headers["X-Auth-Token"]) + json.dumps(identity, sort_keys=True)).encode()).hexdigest()
        favorite_ids = None
        if favorites:
            from .personal import favorite_series_ids
            user = read_json(await komga_request("GET", "/api/v2/users/me", headers=headers))
            if not isinstance(user, dict) or not isinstance(user.get("id"), str):
                raise HTTPException(502, "Komga 用户信息格式不正确")
            try:
                favorite_ids = await run_in_threadpool(favorite_series_ids, user["id"])
            except (sqlite3.Error, OSError):
                raise HTTPException(503, "收藏暂时不可用，请重试") from None
            if not favorite_ids:
                return {"items": [], "last": True, "total": 0}
        if favorites:
            signature += (tuple(favorite_ids),)
        if snapshot and snapshot != "new":
            items = search_snapshots.read(snapshot, scope, signature, revision)
            return {"items": items[page * 16:(page + 1) * 16], "total": len(items), "last": (page + 1) * 16 >= len(items), "snapshot": snapshot}
        keyword = q.strip()
        from .translate import keyword_variants
        variants = keyword_variants(keyword)
        conditions = []
        if type in {"all", "title"}:
            conditions.extend({"title": {"operator": "contains", "value": value}} for value in variants)

        async def lookup(kind, variant):
            resource = {"author": "authors", "genre": "genres", "tag": "tags"}[kind]
            params = {"search": variant, "unpaged": "true"}
            if kind == "tag":
                params["include"] = "BOTH"
            async with limiter:
                matches = read_json(await komga_request("GET", f"/api/v2/{resource}", headers=headers, params=params))
            return kind, matches["content"]

        kinds = ["author", "genre", "tag"] if type == "all" else ([] if type == "title" else [type])
        # 查询名称并行执行，共享限流器保证整个进程最多同时查询 3 个名称请求。
        matches = await asyncio.gather(*(lookup(kind, variant) for kind in kinds for variant in variants), return_exceptions=True)
        seen = set()
        for match in matches:
            if isinstance(match, BaseException):
                raise match
            kind, values = match
            for value in values:
                if exact and (value.get("name") if kind == "author" else value) not in variants:
                    continue
                if kind == "author":
                    value = {"name": value["name"], "role": value["role"]}
                    key = (kind, value["name"], value["role"])
                else:
                    key = (kind, value)
                if key not in seen:
                    seen.add(key)
                    conditions.append({kind: {"operator": "is", "value": value}})
        if not conditions:
            return {"items": [], "last": True, "total": 0}
        # 合并条件后只查询一次系列，由 Komga 统一去重及分页。
        condition = conditions[0] if type == "title" and len(conditions) == 1 else {"anyOf": conditions}
        params = {"page": page, "size": 16, "sort": "metadata.titleSort,asc"}
        if order or favorites:
            params = {"unpaged": "true", "sort": "metadata.titleSort,asc"}
        data = read_json(await komga_request("POST", "/api/v1/series/list", headers=headers, params=params, json={"condition": condition}))
        if favorite_ids is not None:
            # Komga 的系列条件不支持按系列 ID 过滤：先匹配，再与本账号收藏取交集，最后分页。
            ranks = {series_id: index for index, series_id in enumerate(favorite_ids)}
            content = [item for item in data["content"] if item["id"] in ranks]
            content.sort(key=lambda item: ranks[item["id"]])
            data = {"content": content, "totalElements": len(content), "last": True}
            if not order:
                data["content"] = content[page * 16:(page + 1) * 16]
                data["last"] = (page + 1) * 16 >= len(content)
        if order:
            # 全部匹配系列先排序，再切分页，不能只对当前 16 项排序。
            ordered = await order_by_last_release(data["content"], order, komga_request, headers, read_json, limiter)
            if snapshot == "new":
                if revision != (cache.revision if cache else 0):
                    raise HTTPException(409, "书库正在更新，请重新搜索")
                items = [series_card(item) for item in ordered]
                key = search_snapshots.save(scope, signature, revision, items)
                return {"items": items[:16], "total": len(items), "last": len(items) <= 16, "snapshot": key}
            data = {"content": ordered[page * 16:(page + 1) * 16], "totalElements": len(ordered), "last": (page + 1) * 16 >= len(ordered)}
        return {"items": [series_card(item) for item in data["content"]], "last": data["last"], "total": data["totalElements"]}

    return router
