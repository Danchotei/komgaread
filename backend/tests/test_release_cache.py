import asyncio
import sqlite3
from contextlib import closing

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, release_cache, search_snapshots
from app.release_cache import ReleaseCache
from app.search import fill_last_release


def test_full_rebuild_persists_last_number_date_and_missing_date(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/series/list'):
            return httpx.Response(200, json={'content': [{'id': 'a'}, {'id': 'b'}], 'last': True})
        import json
        sid = json.loads(request.content)['condition']['seriesId']['value']
        assert request.url.params['sort'] == 'metadata.numberSort,desc'
        assert request.url.params['size'] == '1'
        return httpx.Response(200, json={'content': [{'metadata': {'releaseDate': '2026-01-02'}}] if sid == 'a' else []})
    cache = ReleaseCache(tmp_path / 'metadata.sqlite3', lambda: ('', ''))
    async def run():
        await asyncio.to_thread(cache.store)
        cache.connected = True
        cache.url = 'https://komga.test'
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            cache.client = client
            await cache.full_refresh()
            assert await cache.refresh('a') == '2026-01-02'
            assert await cache.refresh('b') is None
    asyncio.run(run())
    assert len(calls) == 3  # 缓存包括“没有日期”，重复读取不再发请求。
    with closing(sqlite3.connect(cache.path)) as db:
        assert dict(db.execute('SELECT * FROM release_dates')) == {'a': '2026-01-02', 'b': None}


def test_book_events_only_refresh_affected_series_and_delete(tmp_path):
    cache = ReleaseCache(tmp_path / 'metadata.sqlite3', lambda: ('', ''))
    async def run():
        await asyncio.to_thread(cache.store)
        cache.dates = {'a': 'old', 'b': 'unchanged'}
        cache.connected = True
        cache.url = 'https://komga.test'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'content': [{'metadata': {'releaseDate': 'new'}}]}))) as client:
            cache.client = client
            for event in ('BookAdded', 'BookChanged', 'BookDeleted'):
                await cache.event(event, {'seriesId': 'a'})
                assert cache.dates == {'a': 'new', 'b': 'unchanged'}
            await cache.event('SeriesDeleted', {'seriesId': 'a'})
            assert cache.dates == {'b': 'unchanged'}
    asyncio.run(run())


def test_concurrent_misses_coalesce_and_late_response_cannot_restore_invalidated_date(tmp_path):
    cache = ReleaseCache(tmp_path / 'metadata.sqlite3', lambda: ('', ''))
    calls = []
    async def run():
        started, finish = asyncio.Event(), asyncio.Event()
        async def handler(request):
            calls.append(request)
            started.set()
            await finish.wait()
            return httpx.Response(200, json={'content': [{'metadata': {'releaseDate': 'old'}}]})
        await asyncio.to_thread(cache.store)
        cache.connected = True
        cache.url = 'https://komga.test'
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            cache.client = client
            task = asyncio.create_task(cache.refresh('a'))
            await started.wait()
            cache.invalidate('a')
            finish.set()
            await task
            assert 'a' not in cache.dates
            calls.clear()
            await asyncio.gather(*(cache.refresh('a') for _ in range(8)))
            assert len(calls) == 1
    asyncio.run(run())


def test_sse_parsing_and_disconnect_fallback(monkeypatch, tmp_path):
    cache = ReleaseCache(tmp_path / 'metadata.sqlite3', lambda: ('', ''))
    received = []
    async def event(name, data):
        received.append((name, data))
    monkeypatch.setattr(cache, 'event', event)
    async def run():
        await cache.listen(httpx.Response(200, text=': heartbeat\n\nevent: BookAdded\ndata: {"seriesId":"a"}\n\n'))
        assert received == [('BookAdded', {'seriesId': 'a'})]
        cache.connected = False
        cache.dates['a'] = 'stale'
        monkeypatch.setattr(release_cache, 'service', cache)
        async def live(*args, **kwargs):
            return httpx.Response(200, json={'content': [{'metadata': {'releaseDate': 'live'}}]})
        items = [{'id': 'a'}]
        await fill_last_release(items, live, {}, lambda response: response.json(), asyncio.Semaphore(3))
        assert items[0]['lastReleaseDate'] == 'live'
    asyncio.run(run())


def test_search_second_page_reuses_sort_and_checks_permission(monkeypatch):
    search_snapshots.snapshots.clear()
    monkeypatch.setattr(release_cache, 'service', None)
    main.sessions.update({'a': ('a-token', main.time() + 100), 'b': ('b-token', main.time() + 100)})
    calls = []
    permission = ['reader']
    async def upstream(method, path, **kwargs):
        calls.append(path)
        if path == '/api/v2/users/me':
            return httpx.Response(200, json={'id': kwargs['headers']['X-Auth-Token'], 'roles': permission[:]})
        if path == '/api/v1/books/list':
            index = int(kwargs['json']['condition']['seriesId']['value'])
            return httpx.Response(200, json={'content': [{'metadata': {'releaseDate': f'2026-01-{index+1:02}'}}]})
        assert path == '/api/v1/series/list'
        return httpx.Response(200, json={'content': [{'id': str(i)} for i in range(24)], 'totalElements': 24, 'last': True})
    monkeypatch.setattr(main, 'komga_request', upstream)
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, 'a')
    params = {'q': 'sample', 'type': 'title', 'order': 'desc', 'snapshot': 'new'}
    first = client.get('/api/search', params=params).json()
    assert [item['id'] for item in first['items']] == [str(i) for i in range(23, 7, -1)]
    calls.clear()
    params.update(page=1, snapshot=first['snapshot'])
    second = client.get('/api/search', params=params)
    assert [item['id'] for item in second.json()['items']] == [str(i) for i in range(7, -1, -1)]
    assert calls == ['/api/v2/users/me']
    client.cookies.set(main.COOKIE_NAME, 'b')
    assert client.get('/api/search', params=params).status_code == 409
    client.cookies.set(main.COOKIE_NAME, 'a')
    permission.append('changed')
    assert client.get('/api/search', params=params).status_code == 409
    search_snapshots.snapshots.clear()


def test_snapshot_expires_is_bounded_and_invalidates_on_event(monkeypatch):
    search_snapshots.snapshots.clear()
    monkeypatch.setattr(search_snapshots, 'MAX_SNAPSHOTS', 2)
    clock = [1.0]
    monkeypatch.setattr(search_snapshots, 'monotonic', lambda: clock[0])
    first = search_snapshots.save('a', ('q',), 1, [{'id': 'a'}])
    search_snapshots.save('a', ('q',), 1, [])
    latest = search_snapshots.save('a', ('q',), 1, [])
    with pytest.raises(Exception) as error:
        search_snapshots.read(first, 'a', ('q',), 1)
    assert error.value.status_code == 409
    with pytest.raises(Exception):
        search_snapshots.read(latest, 'a', ('q',), 2)
    clock[0] += search_snapshots.LIFETIME + 1
    with pytest.raises(Exception):
        search_snapshots.read(latest, 'a', ('q',), 1)
    assert latest not in search_snapshots.snapshots
    search_snapshots.snapshots.clear()


def test_failed_rebuild_cancels_remaining_requests(tmp_path):
    cache = ReleaseCache(tmp_path / 'metadata.sqlite3', lambda: ('', ''))
    async def run():
        waiting = asyncio.Event()
        cancelled = asyncio.Event()
        async def handler(request):
            return httpx.Response(200, json={'content': [{'id': 'slow'}, {'id': 'failed'}], 'last': True})
        async def refresh(series_id, force=False):
            if series_id == 'failed':
                await waiting.wait()
                raise ValueError('bad response')
            waiting.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        cache.refresh = refresh
        cache.url = 'https://komga.test'
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            cache.client = client
            with pytest.raises(ValueError):
                await cache.full_refresh()
        assert cancelled.is_set()
    asyncio.run(run())
