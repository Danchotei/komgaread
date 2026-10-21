"""系列搜索路由。共享能力由入口传入，不反向导入 main，避免循环引用。"""
import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool


def create_search_router(
    komga_request: Callable[..., Awaitable[httpx.Response]],
    current_token: Callable[[Request], str],
    read_json: Callable[[httpx.Response], Any],
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["搜索"])
    limiter = asyncio.Semaphore(3)

    @router.get("/search")
    async def search_series(request: Request, q: str = "", type: str = "all", page: int = 0, order: str | None = None, exact: bool = False, favorites: bool = False):
        from urllib.parse import quote
        if type not in {"all", "title", "author", "genre", "tag"} or page < 0 or not q.strip() or len(q) > 200:
            raise HTTPException(422, "请选择搜索类型并输入 1–200 字的关键词")
        if order not in {None, "asc", "desc"}:
            raise HTTPException(422, "排序方式必须为 asc 或 desc")
        headers = {"X-Auth-Token": current_token(request)}
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
            async def last_release(item):
                async with limiter:
                    chapters = read_json(await komga_request("POST", "/api/v1/books/list", headers=headers,
                        params={"page": 0, "size": 1, "sort": "metadata.numberSort,desc"},
                        json={"condition": {"seriesId": {"operator": "is", "value": item["id"]}}}))
                content = chapters["content"]
                item["lastReleaseDate"] = (content[0].get("metadata", {}).get("releaseDate") if content else None)
                return item
            # 全部匹配系列先排序，再切分页，不能只对当前 16 项排序。
            checked = await asyncio.gather(*(last_release(item) for item in data["content"]), return_exceptions=True)
            for item in checked:
                if isinstance(item, BaseException):
                    raise item
            known = [item for item in checked if item["lastReleaseDate"]]
            unknown = [item for item in checked if not item["lastReleaseDate"]]
            known.sort(key=lambda item: item["lastReleaseDate"], reverse=order == "desc")
            ordered = known + unknown
            data = {"content": ordered[page * 16:(page + 1) * 16], "totalElements": len(ordered), "last": (page + 1) * 16 >= len(ordered)}
        return {"items": [{"id": item["id"], "title": item.get("metadata", {}).get("title") or item.get("name") or "未命名系列", "booksCount": item.get("booksCount", 0), "genres": item.get("metadata", {}).get("genres") or [], "lastReleaseDate": item.get("lastReleaseDate"), "thumbnailUrl": f"/api/series/{quote(item['id'], safe='')}/thumbnail"} for item in data["content"]], "last": data["last"], "total": data["totalElements"]}

    return router
