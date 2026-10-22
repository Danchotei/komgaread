"""分类页的最近发行、随机系列和名称浏览。"""
import asyncio
from typing import Literal

from fastapi import APIRouter, Query, Request

from .search import order_by_last_release, series_card


def create_browse_router(komga_request, current_token, read_json, random_series):
    router = APIRouter(prefix="/api/browse", tags=["browse"])
    limiter = asyncio.Semaphore(3)

    @router.get("/{kind}")
    async def browse(kind: Literal["latest", "random", "all"], request: Request, page: int = Query(default=0, ge=0)):
        headers = {"X-Auth-Token": current_token(request)}
        if kind == "random":
            items = await random_series(request) if page == 0 else []
            # 补齐日期，保留原抽样顺序。
            await order_by_last_release(items, "desc", komga_request, headers, read_json, limiter)
            return {"items": items, "last": True}
        params = {"page": page, "size": 16, "sort": "metadata.titleSort,asc"}
        if kind == "latest":
            if page > 0:
                return {"items": [], "last": True}
            params = {"unpaged": "true", "sort": "metadata.titleSort,asc"}
        data = read_json(await komga_request("POST", "/api/v1/series/list", headers=headers, params=params, json={}))
        content = data["content"]
        if kind == "latest":
            content = (await order_by_last_release(content, "desc", komga_request, headers, read_json, limiter))[:30]
        else:
            # 只补齐当前页日期，不改变按名称排列的顺序。
            await order_by_last_release(content, "desc", komga_request, headers, read_json, limiter)
        return {"items": [series_card(item) for item in content], "last": True if kind == "latest" else data["last"]}

    return router
