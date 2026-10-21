from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main, reactions

ORIGIN = {"Origin": "http://127.0.0.1:5173"}


@pytest.fixture(autouse=True)
def storage(monkeypatch, tmp_path):
    monkeypatch.setattr(reactions, "STORE", tmp_path / "reactions.sqlite3")
    main.sessions.clear()

    async def upstream(method, path, **kwargs):
        if path.endswith("/blocked"):
            raise HTTPException(404, "无权访问")
        if path == "/api/v2/users/me":
            user = kwargs["headers"]["X-Auth-Token"]
            return httpx.Response(200, json={"id": user, "email": f"{user}@example.com"})
        return httpx.Response(200, json={"id": "series"})

    monkeypatch.setattr(main, "komga_request", upstream)
    yield
    main.sessions.clear()


def client_for(user):
    client = TestClient(main.app)
    main.sessions[user] = (user, main.time() + 60)
    client.cookies.set(main.COOKIE_NAME, user)
    return client


def test_users_counts_cancellation_and_persistence():
    a, b = client_for("a"), client_for("b")
    path = "/api/series/s1/reactions"
    initial = {"liked": False, "favorited": False, "likesCount": 0, "favoritesCount": 0}
    assert a.get(path).json() == initial
    for _ in range(2):
        result = a.patch(path, headers=ORIGIN, json={"kind": "like", "selected": True})
        assert result.json()["likesCount"] == 1
    b.patch(path, headers=ORIGIN, json={"kind": "like", "selected": True})
    result = a.patch(path, headers=ORIGIN, json={"kind": "favorite", "selected": True}).json()
    assert result == {"liked": True, "favorited": True, "likesCount": 2, "favoritesCount": 1}
    assert b.get(path).json()["favorited"] is False
    assert client_for("a").get(path).json() == result
    for _ in range(2):
        result = a.patch(path, headers=ORIGIN, json={"kind": "like", "selected": False}).json()
        assert result["likesCount"] == 1 and result["liked"] is False
    result = a.patch(path, headers=ORIGIN, json={"kind": "favorite", "selected": False}).json()
    assert result["favoritesCount"] == 0
    assert a.get("/api/series/s2/reactions").json() == initial


def test_auth_permissions_and_input():
    client = TestClient(main.app)
    assert client.get("/api/series/s1/reactions").status_code == 401
    assert client.patch("/api/series/s1/reactions", headers=ORIGIN, json={"kind": "like", "selected": True}).status_code == 401
    client = client_for("a")
    for method in ["get", "patch"]:
        options = {"headers": ORIGIN, "json": {"kind": "like", "selected": True}} if method == "patch" else {}
        assert getattr(client, method)("/api/series/blocked/reactions", **options).status_code == 404
    for body in [{"kind": "other", "selected": True}, {"kind": "like", "selected": "true"}, {"kind": "like", "selected": True, "user_id": "b"}]:
        assert client.patch("/api/series/s1/reactions", headers=ORIGIN, json=body).status_code == 422
    assert not reactions.STORE.exists()


def test_concurrent_same_user_never_double_counts():
    reactions.reaction_state("a", "s")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: reactions.reaction_state("a", "s", "like", True), range(24)))
    assert reactions.reaction_state("a", "s")["likesCount"] == 1
