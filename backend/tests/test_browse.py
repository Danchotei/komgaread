import httpx
import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(monkeypatch):
    main.sessions.update({"test": ("token", main.time() + 60)})
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, "test")
    return client


def test_all_name_order_and_pagination(monkeypatch, client):
    async def upstream(method, path, **kwargs):
        assert kwargs["headers"]["X-Auth-Token"] == "token"
        if path == "/api/v1/books/list":
            return httpx.Response(200, json={"content": [{"metadata": {"releaseDate": "2026-10-01"}}]})
        assert path == "/api/v1/series/list"
        assert kwargs["params"] == {"page": 2, "size": 16, "sort": "metadata.titleSort,asc"}
        return httpx.Response(200, json={"content": [{"id": "s", "metadata": {"title": "标题", "genres": ["全彩"]}}], "last": False})
    monkeypatch.setattr(main, "komga_request", upstream)
    data = client.get("/api/browse/all?page=2").json()
    assert data["items"][0]["title"] == "标题" and data["last"] is False
    assert data["items"][0]["genres"] == ["全彩"]
    assert data["items"][0]["lastReleaseDate"] == "2026-10-01"
    assert TestClient(main.app).get("/api/browse/all").status_code == 401
    assert client.get("/api/browse/all?page=-1").status_code == 422


def test_latest_publication_sort_and_limit(monkeypatch, client):
    async def upstream(method, path, **kwargs):
        if path.endswith("series/list"):
            assert kwargs["params"]["unpaged"] == "true"
            return httpx.Response(200, json={"content": [{"id": str(i)} for i in range(35)]})
        assert kwargs["params"]["sort"] == "metadata.numberSort,desc"
        index = int(kwargs["json"]["condition"]["seriesId"]["value"])
        return httpx.Response(200, json={"content": [{"metadata": {"releaseDate": f"2026-{index // 28 + 1:02d}-{index % 28 + 1:02d}"}}]})
    monkeypatch.setattr(main, "komga_request", upstream)
    data = client.get("/api/browse/latest").json()
    assert len(data["items"]) == 30 and data["last"] is True
    assert [item["id"] for item in data["items"]] == [str(i) for i in range(34, 4, -1)]


def test_random_twelve_unique_and_redraw(monkeypatch, client):
    async def upstream(method, path, **kwargs):
        if path == "/api/v1/books/list":
            return httpx.Response(200, json={"content": [{"metadata": {"releaseDate": "2026-09-01"}}]})
        params = kwargs["params"]
        assert params["size"] == 1
        return httpx.Response(200, json={"content": [{"id": str(params["page"]), "metadata": {"genres": ["同人"]}}], "totalElements": 100})
    monkeypatch.setattr(main, "komga_request", upstream)
    first = client.get("/api/browse/random").json()
    assert len(first["items"]) == 12
    assert len({item["id"] for item in first["items"]}) == 12
    assert all(item["genres"] == ["同人"] and item["lastReleaseDate"] == "2026-09-01" for item in first["items"])
    calls = []
    async def draw(request, count=4):
        calls.append(count)
        return [{"id": str(i)} for i in range(count)]
    monkeypatch.setattr(main, "select_recommendations", draw)
    for _ in range(2):
        assert len(client.get("/api/browse/random").json()["items"]) == 12
    assert calls == [12, 12]
