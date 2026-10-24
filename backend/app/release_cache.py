"""发行日期缓存：启动重建，SSE 失联时不使用旧数据，网络与磁盘均不阻塞事件循环。"""
import asyncio
import json
import logging
import sqlite3
from contextlib import closing, suppress
from pathlib import Path
from threading import Lock

import httpx
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger("uvicorn.error")
service = None


def failure_reason(exc):
    # HTTP 日志仅记录接口路径，不输出密钥、请求头、查询参数或响应正文。
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} {exc.request.method} {exc.request.url.path}"
    if isinstance(exc, httpx.RequestError):
        try:
            request = exc.request
        except RuntimeError:
            return type(exc).__name__
        return f"{type(exc).__name__} {request.method} {request.url.path}"
    return f"{type(exc).__name__}: {exc}"


class ReleaseCache:
    def __init__(self, path, get_credentials):
        self.path = Path(path)
        self.get_credentials = get_credentials
        self.dates = {}
        self.connected = False
        self.revision = 0
        self.epoch = 0
        self.versions = {}
        self.locks = [asyncio.Lock() for _ in range(64)]
        self.limit = asyncio.Semaphore(3)
        self.client = None
        self.url = ""
        self.write_lock = Lock()

    def store(self, series_id=None, date=None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 线程池中的不同系列共用一个数据库，写入先排队，避免相互抢 SQLite 写锁。
        with self.write_lock, closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS release_dates (series_id TEXT PRIMARY KEY, release_date TEXT)")
            if series_id is None:
                db.execute("DELETE FROM release_dates")
            else:
                db.execute("INSERT OR REPLACE INTO release_dates VALUES (?,?)", (series_id, date))

    def invalidate(self, series_id=None):
        self.revision += 1
        if series_id is None:
            self.epoch += 1
            self.dates.clear()
            self.versions.clear()
        else:
            self.dates.pop(series_id, None)
            self.versions[series_id] = self.versions.get(series_id, 0) + 1

    async def refresh(self, series_id, force=False):
        async with self.locks[hash(series_id) % len(self.locks)]:
            if not force and series_id in self.dates:
                return self.dates[series_id]
            generation = self.epoch, self.versions.get(series_id, 0)
            async with self.limit:
                response = await self.client.post(f"{self.url}/api/v1/books/list",
                    params={"page": 0, "size": 1, "sort": "metadata.numberSort,desc"},
                    json={"condition": {"seriesId": {"operator": "is", "value": series_id}}})
                response.raise_for_status()
                content = response.json()["content"]
                date = content[0].get("metadata", {}).get("releaseDate") if content else None
                if date is not None and not isinstance(date, str):
                    raise ValueError("Invalid release date")
            # 不让事件发生前已发出的请求，将旧结果重新填回缓存。
            if self.connected and generation == (self.epoch, self.versions.get(series_id, 0)):
                await run_in_threadpool(self.store, series_id, date)
                if self.connected and generation == (self.epoch, self.versions.get(series_id, 0)):
                    self.dates[series_id] = date
            return date

    async def full_refresh(self):
        page = 0
        count = 0
        while True:
            response = await self.client.post(f"{self.url}/api/v1/series/list",
                params={"page": page, "size": 200, "sort": "metadata.titleSort,asc"}, json={})
            response.raise_for_status()
            data = response.json()
            tasks = [asyncio.create_task(self.refresh(item["id"], force=True)) for item in data["content"]]
            try:
                await asyncio.gather(*tasks)
            finally:
                # 某项失败或服务退出时，收完本批任务，避免旧任务跨重连继续写缓存。
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            count += len(data["content"])
            if data["last"]:
                break
            page += 1
        logger.info("Release date cache rebuilt: %s series", count)

    async def warm_until_success(self):
        while True:
            try:
                await self.full_refresh()
                return
            except (httpx.HTTPError, ValueError, KeyError, TypeError, sqlite3.Error, OSError) as exc:
                logger.warning("Release date rebuild interrupted; retrying in 60 seconds (%s)", failure_reason(exc))
                await asyncio.sleep(60)

    async def event(self, name, data):
        if name in {"BookAdded", "BookChanged", "BookDeleted", "SeriesAdded", "SeriesChanged", "SeriesDeleted"}:
            series_id = data.get("seriesId")
            if not isinstance(series_id, str) or not series_id:
                raise ValueError("Missing seriesId in event")
            self.invalidate(series_id)
            if name == "SeriesDeleted":
                # 已失效的持久化行只用于诊断；启动时统一清空重建。
                await run_in_threadpool(self.delete, series_id)
            else:
                await self.refresh(series_id)
        elif name in {"LibraryAdded", "LibraryChanged", "LibraryDeleted"}:
            # 库事件可能改变权限或移动大量系列；重连并全量校准。
            raise ValueError("Library changed")

    def delete(self, series_id):
        with self.write_lock, closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("DELETE FROM release_dates WHERE series_id=?", (series_id,))

    async def listen(self, response):
        name, lines = "", []
        async for line in response.aiter_lines():
            if not line:
                if name and lines:
                    await self.event(name, json.loads("\n".join(lines)))
                name, lines = "", []
            elif line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                lines.append(line[5:].lstrip())

    async def run(self):
        delay = 5
        while True:
            warm = None
            try:
                url, key = self.get_credentials()
                if not url or not key:
                    await asyncio.sleep(5)
                    continue
                self.url = url.rstrip("/")
                async with httpx.AsyncClient(headers={"X-API-Key": key}, timeout=20, follow_redirects=False) as client:
                    self.client = client
                    # SSE 使用独立长连接，不占用普通 API 请求连接。
                    async with httpx.AsyncClient(headers={"X-API-Key": key}, timeout=httpx.Timeout(45, connect=10), follow_redirects=False) as stream:
                        async with stream.stream("GET", f"{self.url}/sse/v1/events", headers={"Accept": "text/event-stream"}) as response:
                            response.raise_for_status()
                            if "text/event-stream" not in response.headers.get("content-type", ""):
                                raise ValueError("Not an SSE response")
                            await run_in_threadpool(self.store)
                            self.invalidate()
                            self.connected = True
                            logger.info("Komga event stream connected; rebuilding release date cache")
                            warm = asyncio.create_task(self.warm_until_success())
                            delay = 5
                            await self.listen(response)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, sqlite3.Error, OSError) as exc:
                logger.warning("Komga date cache listener unavailable; retrying in %ss (dates use live queries; %s)", delay, failure_reason(exc))
            finally:
                if self.connected or self.dates:
                    self.invalidate()
                self.connected = False
                if warm:
                    warm.cancel()
                    with suppress(asyncio.CancelledError):
                        await warm
                self.client = None
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
