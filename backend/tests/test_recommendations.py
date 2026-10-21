import httpx
import pytest
import sqlite3
from fastapi.testclient import TestClient
from app import main


def test_old_daily_cache_upgrades_to_eight_without_repeated_draws(monkeypatch, tmp_path):
    from app import daily
    monkeypatch.setattr(daily, "STORE", tmp_path / "daily.sqlite3")
    with sqlite3.connect(daily.STORE) as db:
        db.execute("CREATE TABLE daily (user TEXT, day TEXT, items TEXT, PRIMARY KEY(user,day))")
        db.execute("INSERT INTO daily VALUES ('u','2026-10-21','[]')")
    assert daily.read("u", "2026-10-21", count=8) is None
    small_library = [{"id": "only-one"}]
    daily.write("u", "2026-10-21", small_library, count=8)
    assert daily.read("u", "2026-10-21", count=8) == small_library


@pytest.mark.parametrize("total", [0, 2, 8, 100])
def test_random_recommendations(monkeypatch, total, tmp_path):
    from app import daily
    monkeypatch.setattr(daily, "STORE", tmp_path / "daily.sqlite3")
    calls = []

    async def upstream(method, path, **kwargs):
        assert kwargs["headers"]["X-Auth-Token"] == "user-token"
        if path == "/api/v2/users/me":
            return httpx.Response(200, json={"id": "u1", "email": "u@example.com"})
        if path == "/api/v1/books/list":
            return httpx.Response(200, json={"content": [{"metadata": {"releaseDate": "2026-10-21"}}]})
        if method == "GET":
            return httpx.Response(200, json={"id": path.split("/")[-1], "metadata": {"genres": ["同人"]}})
        assert method == "POST" and path == "/api/v1/series/list"
        page = kwargs["params"]["page"]
        calls.append(page)
        content = [{"id": str(page), "metadata": {"title": f"Series {page}"}, "booksCount": 12}] if total else []
        return httpx.Response(200, json={"totalElements": total, "content": content})

    monkeypatch.setattr(main, "komga_request", upstream)
    main.sessions.update({"test": ("user-token", main.time() + 60)})
    client = TestClient(main.app)
    assert client.get("/api/series/recommendations").status_code == 401
    client.cookies.set(main.COOKIE_NAME, "test")
    result = client.get("/api/series/recommendations")
    assert result.status_code == 200
    items = result.json()
    assert len(items) == min(total, 8)
    assert len({item["id"] for item in items}) == len(items)
    assert all(item["genres"] == ["同人"] and item["lastReleaseDate"] == "2026-10-21" for item in items)
    assert all(0 <= int(item["id"]) < total for item in items)
    assert len(calls) <= 9
    previous_calls = len(calls)
    assert client.get("/api/series/recommendations").json() == items
    assert len(calls) == previous_calls
    monkeypatch.setattr(daily, "china_day", lambda: "2099-01-01")
    assert client.get("/api/series/recommendations").status_code == 200
    assert len(calls) > previous_calls
    assert all(item["thumbnailUrl"].startswith("/api/series/") for item in items)


def test_cover_requires_own_session(monkeypatch):
    async def upstream(method, path, **kwargs):
        assert kwargs["headers"]["X-Auth-Token"] == "cover-token"
        assert path == "/api/v1/series/123/thumbnail"
        return httpx.Response(200, content=b"fake-jpeg", headers={"Content-Type": "image/jpeg"})
    monkeypatch.setattr(main, "komga_request", upstream)
    main.sessions.update({"test": ("cover-token", main.time() + 60)})
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
    main.sessions.update({"test": ("token", main.time() + 60)})
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, "test")
    assert client.get("/api/series/recommendations").status_code == 502
    main.sessions["test"] = ("token", 0)
    assert client.get("/api/series/recommendations").status_code == 401


@pytest.mark.parametrize("total", [0, 2, 8])
def test_recent_series_order_and_permissions(monkeypatch, total):
    async def upstream(method, path, **kwargs):
        if path == "/api/v1/books/list":
            return httpx.Response(200, json={"content": [{"metadata": {"releaseDate": "2026-09-01"}}]})
        if path == "/api/v2/users/me":
            return httpx.Response(200, json={"id": "u1", "email": "u@example.com"})
        if method == "GET":
            return httpx.Response(200, json={"id": path.split("/")[-1]})
        assert method == "POST" and path == "/api/v1/series/list"
        assert kwargs["headers"]["X-Auth-Token"] == "recent-token"
        assert kwargs["params"] == {"page": 0, "size": 8, "sort": "createdDate,desc"}
        return httpx.Response(200, json={"content": [{"id": str(i), "metadata": {"title": f"Recent {i}"}, "booksCount": i} for i in range(total)]})
    monkeypatch.setattr(main, "komga_request", upstream)
    main.sessions.update({"test": ("recent-token", main.time() + 60)})
    client = TestClient(main.app)
    assert client.get("/api/series/recent").status_code == 401
    client.cookies.set(main.COOKIE_NAME, "test")
    response = client.get("/api/series/recent")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(i) for i in range(total)]
    assert all(item["thumbnailUrl"].startswith("/api/series/") for item in response.json())
    assert all(item["lastReleaseDate"] == "2026-09-01" and "genres" in item for item in response.json())
