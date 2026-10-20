import httpx
import pytest
from fastapi.testclient import TestClient
from app import main


@pytest.mark.parametrize('kind', ['title', 'author', 'genre', 'tag'])
def test_search_series_only(monkeypatch, kind):
    monkeypatch.setattr(main, 'sessions', {'test': ('token', main.time() + 60)})
    async def upstream(method, path, **kwargs):
        assert kwargs['headers']['X-Auth-Token'] == 'token'
        if method == 'GET':
            assert kwargs['params']['search'] == 'keyword'
            return httpx.Response(200, json={'content': [{'name': 'keyword', 'role': 'writer'}] if kind == 'author' else ['keyword']})
        assert path == '/api/v1/series/list'
        assert kwargs['params']['page'] == 2
        condition = kwargs['json']['condition']
        if kind == 'title':
            assert condition == {'title': {'operator': 'contains', 'value': 'keyword'}}
        else:
            expected = {'name': 'keyword', 'role': 'writer'} if kind == 'author' else 'keyword'
            assert condition == {'anyOf': [{kind: {'operator': 'is', 'value': expected}}]}
        return httpx.Response(200, json={'content': [{'id': 's1', 'metadata': {'title': 'Series'}, 'booksCount': 3}], 'last': True, 'totalElements': 1})
    monkeypatch.setattr(main, 'komga_request', upstream)
    client = TestClient(main.app)
    assert client.get('/api/search?q=keyword').status_code == 401
    client.cookies.set(main.COOKIE_NAME, 'test')
    result = client.get(f'/api/search?q=keyword&type={kind}&page=2')
    assert result.status_code == 200
    assert result.json()['items'][0]['id'] == 's1'
    assert result.json()['items'][0]['thumbnailUrl'] == '/api/series/s1/thumbnail'
    assert client.get('/api/search?q=keyword&type=invalid').status_code == 422
    assert client.get('/api/search?q=keyword&page=-1').status_code == 422
    assert client.get('/api/search?q=   ').status_code == 422


def test_empty_author_search(monkeypatch):
    monkeypatch.setattr(main, 'sessions', {'test': ('token', main.time() + 60)})
    async def upstream(*args, **kwargs):
        return httpx.Response(200, json={'content': []})
    monkeypatch.setattr(main, 'komga_request', upstream)
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, 'test')
    assert client.get('/api/search?q=missing&type=author').json() == {'items': [], 'last': True, 'total': 0}

@pytest.mark.parametrize('keyword', ['学生', '學生'])
@pytest.mark.parametrize('kind', ['title', 'author', 'genre', 'tag'])
def test_chinese_variants(monkeypatch, keyword, kind):
    from app.translate import keyword_variants
    variants = keyword_variants(keyword)
    assert {'学生', '學生'} <= set(variants)
    assert len(variants) == len(set(variants))
    monkeypatch.setattr(main, 'sessions', {'test': ('token', main.time() + 60)})
    names = []
    async def upstream(method, path, **kwargs):
        if method == 'GET':
            names.append(kwargs['params']['search'])
            return httpx.Response(200, json={'content': [{'name': '學生', 'role': 'writer'}] if kind == 'author' else ['學生']})
        condition = kwargs['json']['condition']
        if kind == 'title':
            assert {item['title']['value'] for item in condition['anyOf']} >= {'学生', '學生'}
        else:
            # 多个写法命中同一名称，最终条件只保留一次。
            assert len(condition['anyOf']) == 1
        return httpx.Response(200, json={'content': [], 'totalElements': 0, 'last': True})
    monkeypatch.setattr(main, 'komga_request', upstream)
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, 'test')
    assert client.get('/api/search', params={'q': keyword, 'type': kind}).status_code == 200
    if kind != 'title':
        assert set(names) >= {'学生', '學生'}


def test_combined_search_and_concurrency(monkeypatch):
    import asyncio
    monkeypatch.setattr(main, 'sessions', {'test': ('token', main.time() + 60)})
    active = 0
    peak = 0
    queries = []
    async def upstream(method, path, **kwargs):
        nonlocal active, peak
        if method == 'GET':
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.001)
            active -= 1
            return httpx.Response(200, json={'content': [{'name': '學生', 'role': 'writer'}] if path.endswith('authors') else ['學生']})
        queries.append(kwargs)
        fields = [next(iter(item)) for item in kwargs['json']['condition']['anyOf']]
        assert set(fields) == {'title', 'author', 'genre', 'tag'}
        assert fields.count('author') == fields.count('genre') == fields.count('tag') == 1
        return httpx.Response(200, json={'content': [{'id': 's1'}], 'totalElements': 1, 'last': True})
    monkeypatch.setattr(main, 'komga_request', upstream)
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, 'test')
    response = client.get('/api/search', params={'q': '学生'})
    assert response.status_code == 200
    assert len(queries) == 1
    assert 1 < peak <= 3


def test_combined_search_fails_explicitly(monkeypatch):
    monkeypatch.setattr(main, 'sessions', {'test': ('token', main.time() + 60)})
    async def upstream(method, path, **kwargs):
        if path.endswith('authors'):
            raise main.HTTPException(502, 'Komga unavailable')
        assert method == 'GET'
        return httpx.Response(200, json={'content': []})
    monkeypatch.setattr(main, 'komga_request', upstream)
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, 'test')
    assert client.get('/api/search?q=test').status_code == 502

@pytest.mark.parametrize('direction', ['asc', 'desc'])
def test_sort_last_chapter_release_date(monkeypatch, direction):
    monkeypatch.setattr(main, 'sessions', {'test': ('token', main.time() + 60)})
    async def upstream(method, path, **kwargs):
        if path == '/api/v1/series/list':
            assert kwargs['params']['unpaged'] == 'true'
            return httpx.Response(200, json={'content': [{'id': str(i)} for i in range(26)]})
        assert path == '/api/v1/books/list'
        assert kwargs['params']['sort'] == 'metadata.numberSort,desc'
        assert kwargs['params']['size'] == 1
        index = int(kwargs['json']['condition']['seriesId']['value'])
        date = f'2025-01-{index + 1:02d}' if index < 25 else None
        return httpx.Response(200, json={'content': [{'metadata': {'releaseDate': date}}]})
    monkeypatch.setattr(main, 'komga_request', upstream)
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, 'test')
    first = client.get('/api/search', params={'q': 'test', 'type': 'title', 'order': direction}).json()
    second = client.get('/api/search', params={'q': 'test', 'type': 'title', 'order': direction, 'page': 1}).json()
    ids = [item['id'] for item in first['items'] + second['items']]
    assert ids == [str(i) for i in (range(25) if direction == 'asc' else range(24, -1, -1))] + ['25']
    assert first['last'] is False and second['last'] is True
    assert first['total'] == 26
    assert second['items'][-1]['lastReleaseDate'] is None
