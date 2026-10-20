import httpx
import pytest
from fastapi.testclient import TestClient
from app import main


@pytest.mark.parametrize("total", [0, 2, 4, 100])
def test_random_recommendations(monkeypatch, total):
    calls = []

    async def upstream(method, path, **kwargs):
        assert kwargs["headers"]["X-Auth-Token"] == "user-token"
        assert method == "POST" and path == "/api/v1/series/list"
        page = kwargs["params"]["page"]
        calls.append(page)
        content = [{"id": str(page), "metadata": {"title": f"Series {page}"}, "booksCount": 12}] if total else []
        return httpx.Response(200, json={"totalElements": total, "content": content})

    monkeypatch.setattr(main, "komga_request", upstream)
    monkeypatch.setattr(main, "sessions", {"test": ("user-token", main.time() + 60)})
    client = TestClient(main.app)
    assert client.get("/api/series/recommendations").status_code == 401
    client.cookies.set(main.COOKIE_NAME, "test")
    result = client.get("/api/series/recommendations")
    assert result.status_code == 200
    items = result.json()
    assert len(items) == min(total, 4)
    assert len({item["id"] for item in items}) == len(items)
    assert all(0 <= int(item["id"]) < total for item in items)
    assert len(calls) <= 5
    assert all(item["thumbnailUrl"].startswith("/api/series/") for item in items)


def test_cover_requires_own_session(monkeypatch):
    async def upstream(method, path, **kwargs):
        assert kwargs["headers"]["X-Auth-Token"] == "cover-token"
        assert path == "/api/v1/series/123/thumbnail"
        return httpx.Response(200, content=b"fake-jpeg", headers={"Content-Type": "image/jpeg"})
    monkeypatch.setattr(main, "komga_request", upstream)
    monkeypatch.setattr(main, "sessions", {"test": ("cover-token", main.time() + 60)})
    client = TestClient(main.app)
    assert client.get("/api/series/123/thumbnail").status_code == 401
    client.cookies.set(main.COOKIE_NAME, "test")
    response = client.get("/api/series/123/thumbnail")
    assert response.status_code == 200
    assert response.content == b"fake-jpeg"
    assert response.headers["content-type"] == "image/jpeg"


def test_bad_upstream_and_expired_session(monkeypatch):
    async def upstream(*args, **kwargs):
        return httpx.Response(200, text="not json")
    monkeypatch.setattr(main, "komga_request", upstream)
    monkeypatch.setattr(main, "sessions", {"test": ("token", main.time() + 60)})
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, "test")
    assert client.get("/api/series/recommendations").status_code == 502
    main.sessions["test"] = ("token", 0)
    assert client.get("/api/series/recommendations").status_code == 401


@pytest.mark.parametrize("total", [0, 2, 4])
def test_recent_series_order_and_permissions(monkeypatch, total):
    async def upstream(method, path, **kwargs):
        assert method == "POST" and path == "/api/v1/series/list"
        assert kwargs["headers"]["X-Auth-Token"] == "recent-token"
        assert kwargs["params"] == {"page": 0, "size": 4, "sort": "createdDate,desc"}
        return httpx.Response(200, json={"content": [{"id": str(i), "metadata": {"title": f"Recent {i}"}, "booksCount": i} for i in range(total)]})
    monkeypatch.setattr(main, "komga_request", upstream)
    monkeypatch.setattr(main, "sessions", {"test": ("recent-token", main.time() + 60)})
    client = TestClient(main.app)
    assert client.get("/api/series/recent").status_code == 401
    client.cookies.set(main.COOKIE_NAME, "test")
    response = client.get("/api/series/recent")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(i) for i in range(total)]
    assert all(item["thumbnailUrl"].startswith("/api/series/") for item in response.json())
