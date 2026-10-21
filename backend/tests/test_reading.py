import httpx
import pytest
from fastapi.testclient import TestClient
from app import main


@pytest.fixture
def client(monkeypatch):
    main.sessions.update({"reader": ("reader-token", main.time() + 60)})
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, "reader")
    return client


def test_series_book_list_and_details(client, monkeypatch):
    async def upstream(method, path, **kwargs):
        assert kwargs["headers"]["X-Auth-Token"] == "reader-token"
        if path == "/api/v1/series/s1":
            return httpx.Response(200, json={"id": "s1", "metadata": {"title": "Series", "summary": "Summary"}, "booksCount": 1})
        if path == "/api/v1/books/list":
            assert kwargs["json"] == {"condition": {"seriesId": {"operator": "is", "value": "s1"}}}
            assert kwargs["params"] == {"page": 1, "size": 48, "sort": "metadata.numberSort,asc"}
            return httpx.Response(200, json={"content": [{"id": "b1", "metadata": {"title": "Book"}, "media": {"pagesCount": 10}}], "last": True})
        assert path == "/api/v1/books/b1"
        return httpx.Response(200, json={"id": "b1", "seriesId": "s1", "metadata": {"title": "Book"}, "media": {"pagesCount": 10}})
    monkeypatch.setattr(main, "komga_request", upstream)
    assert client.get("/api/series/s1").json()["summary"] == "Summary"
    data = client.get("/api/series/s1/books?page=1").json()
    assert data["last"] is True
    assert data["items"][0]["thumbnailUrl"] == "/api/books/b1/thumbnail"
    assert client.get("/api/books/b1").json()["pagesCount"] == 10
    assert client.get("/api/series/s1/books?page=-1").status_code == 422


@pytest.mark.parametrize("path", ["/api/series/s1", "/api/series/s1/books", "/api/books/b1", "/api/books/b1/thumbnail", "/api/books/b1/pages/1"])
def test_read_endpoints_require_login(path):
    assert TestClient(main.app).get(path).status_code == 401


@pytest.mark.parametrize("status, media, expected", [(200, "image/jpeg", 200), (403, "application/json", 403), (404, "application/json", 404), (200, "text/html", 502)])
def test_image_stream_auth_and_errors(client, monkeypatch, status, media, expected):
    original_client = httpx.AsyncClient
    def handler(request):
        assert request.headers["X-Auth-Token"] == "reader-token"
        assert request.url.path == "/api/v1/books/b1/pages/2"
        assert request.url.params["zero_based"] == "false"
        assert request.url.params["convert"] == "jpeg"
        return httpx.Response(status, content=b"image-bytes", headers={"Content-Type": media})
    monkeypatch.setattr(main, "KOMGA_URL", "https://komga.example")
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    response = client.get("/api/books/b1/pages/2")
    assert response.status_code == expected
    if expected == 200:
        assert response.content == b"image-bytes"
        assert response.headers["content-type"] == "image/jpeg"
    assert client.get("/api/books/b1/pages/0").status_code == 422

@pytest.mark.parametrize('order', ['asc', 'desc'])
def test_book_sort_and_komga_progress(client, monkeypatch, order):
    async def upstream(method, path, **kwargs):
        assert kwargs['params']['sort'] == f'metadata.numberSort,{order}'
        assert kwargs['headers']['X-Auth-Token'] == 'reader-token'
        return httpx.Response(200, json={'content': [
            {'id': 'unread', 'readProgress': None},
            {'id': 'reading', 'readProgress': {'page': 12, 'completed': False}},
            {'id': 'done', 'readProgress': {'page': 26, 'completed': True}},
        ], 'last': True})
    monkeypatch.setattr(main, 'komga_request', upstream)
    response = client.get(f'/api/series/s1/books?order={order}')
    assert response.status_code == 200
    items = response.json()['items']
    assert items[0]['readProgress'] is None
    assert items[1]['readProgress']['page'] == 12
    assert items[2]['readProgress']['completed'] is True
    assert client.get('/api/series/s1/books?order=invalid').status_code == 422

@pytest.mark.parametrize('page,old_completed,expected', [(5, False, False), (10, False, True), (2, True, True)])
def test_save_progress(client, monkeypatch, page, old_completed, expected):
    calls = []
    async def upstream(method, path, **kwargs):
        assert kwargs['headers']['X-Auth-Token'] == 'reader-token'
        if method == 'GET':
            return httpx.Response(200, json={'media': {'pagesCount': 10}, 'readProgress': {'completed': old_completed}})
        calls.append((path, kwargs['json']))
        return httpx.Response(204)
    monkeypatch.setattr(main, 'komga_request', upstream)
    headers = {'Origin': 'http://127.0.0.1:5173'}
    response = client.patch('/api/books/b1/progress', json={'page': page}, headers=headers)
    assert response.status_code == 204
    assert calls == [('/api/v1/books/b1/read-progress', {'page': page, 'completed': expected})]
    for invalid in [0, -1, 11, 1.5, True]:
        assert client.patch('/api/books/b1/progress', json={'page': invalid}, headers=headers).status_code == 422
    assert TestClient(main.app).patch('/api/books/b1/progress', json={'page': 1}, headers=headers).status_code == 401
