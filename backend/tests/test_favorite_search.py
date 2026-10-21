import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, reactions


@pytest.fixture(autouse=True)
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(reactions, "STORE", tmp_path / "reactions.sqlite3")
    main.sessions.update({"a": ("a", main.time() + 60), "b": ("b", main.time() + 60)})


def client_for(user):
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, user)
    return client


@pytest.mark.parametrize("keyword", ["学生", "學生"])
def test_favorite_scope_combined_variants_order_and_pagination(monkeypatch, keyword):
    for index in range(20):
        reactions.reaction_state("a", f"s{index}", "favorite", True)
    reactions.reaction_state("b", "other-user-only", "favorite", True)
    conditions = []

    async def upstream(method, path, **kwargs):
        if path == "/api/v2/users/me":
            return httpx.Response(200, json={"id": kwargs["headers"]["X-Auth-Token"]})
        if method == "GET":
            return httpx.Response(200, json={"content": [{"name": "學生", "role": "writer"}] if path.endswith("authors") else ["學生"]})
        assert kwargs["params"]["unpaged"] == "true"
        conditions.append(kwargs["json"]["condition"])
        return httpx.Response(200, json={"content": [{"id": "other-user-only"}, {"id": "not-favorited"}] + [{"id": f"s{index}"} for index in range(20)], "totalElements": 22, "last": True})

    monkeypatch.setattr(main, "komga_request", upstream)
    client = client_for("a")
    first = client.get("/api/search", params={"q": keyword, "favorites": True}).json()
    assert first["total"] == 20 and first["last"] is False
    assert [item["id"] for item in first["items"]] == [f"s{index}" for index in range(19, 3, -1)]
    second = client.get("/api/search", params={"q": keyword, "favorites": True, "page": 1}).json()
    assert second["last"] is True
    assert [item["id"] for item in second["items"]] == ["s3", "s2", "s1", "s0"]
    fields = {next(iter(condition)) for condition in conditions[0]["anyOf"]}
    assert fields == {"title", "author", "genre", "tag"}
    titles = {condition["title"]["value"] for condition in conditions[0]["anyOf"] if "title" in condition}
    assert {"学生", "學生"} <= titles
    other = client_for("b").get("/api/search", params={"q": keyword, "favorites": True}).json()
    assert [item["id"] for item in other["items"]] == ["other-user-only"]


def test_empty_favorites_skip_search_and_require_auth(monkeypatch):
    async def upstream(method, path, **kwargs):
        assert path == "/api/v2/users/me"
        return httpx.Response(200, json={"id": "a"})
    monkeypatch.setattr(main, "komga_request", upstream)
    assert TestClient(main.app).get("/api/search?q=test&favorites=true").status_code == 401
    assert client_for("a").get("/api/search?q=test&favorites=true").json() == {"items": [], "last": True, "total": 0}
