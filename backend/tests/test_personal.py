import sqlite3

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main, personal, reactions

ORIGIN = {"Origin": "http://127.0.0.1:5173"}


@pytest.fixture(autouse=True)
def storage(monkeypatch, tmp_path):
    monkeypatch.setattr(reactions, "STORE", tmp_path / "reactions.sqlite3")
    main.sessions.clear()

    async def upstream(method, path, **kwargs):
        if path.endswith("/blocked"):
            raise HTTPException(404, "不可访问")
        if path == "/api/v2/users/me":
            user = kwargs["headers"]["X-Auth-Token"]
            return httpx.Response(200, json={"id": user, "email": f"{user}@example.com"})
        return httpx.Response(200, json={"id": path.split('/')[-1], "metadata": {"title": "系列标题"}, "booksCount": 2})

    monkeypatch.setattr(main, "komga_request", upstream)
    yield
    main.sessions.clear()


def client_for(user):
    client = TestClient(main.app)
    main.sessions[user] = (user, main.time() + 60)
    client.cookies.set(main.COOKIE_NAME, user)
    return client


def ids(kind, user="a"):
    result, last = personal.stored_list(user, kind, 0)
    return result


def test_history_moves_duplicates_to_front_and_limits_per_user():
    for item in "14564":
        personal.record_visit("a", item)
    assert ids("history") == list("4651")
    personal.record_visit("b", "other")
    for item in range(60):
        personal.record_visit("a", str(item))
    rows = []
    for page in range(4):
        result, last = personal.stored_list("a", "history", page)
        rows.extend(result)
    assert rows == [str(item) for item in range(59, 9, -1)]
    assert len(rows) == 50 and last
    assert ids("history", "b") == ["other"]


def test_favorites_readd_moves_front_but_duplicate_request_does_not():
    for item in "1456":
        reactions.reaction_state("a", item, "favorite", True)
    reactions.reaction_state("a", "4", "favorite", True)
    assert ids("favorites") == list("6541")
    reactions.reaction_state("a", "4", "favorite", False)
    assert ids("favorites") == list("651")
    reactions.reaction_state("a", "4", "favorite", True)
    assert ids("favorites") == list("4651")
    assert ids("favorites", "b") == []


def test_old_reactions_migrate_without_losing_counts():
    with sqlite3.connect(reactions.STORE) as db:
        db.execute("CREATE TABLE reactions (user_id TEXT, series_id TEXT, kind TEXT, PRIMARY KEY(user_id,series_id,kind))")
        db.executemany("INSERT INTO reactions VALUES (?,?,?)", [("a", "1", "favorite"), ("a", "2", "favorite"), ("b", "1", "like")])
    assert ids("favorites") == ["2", "1"]
    assert reactions.reaction_state("a", "1") == {"liked": False, "favorited": True, "likesCount": 1, "favoritesCount": 1}
    assert ids("favorites") == ["2", "1"]


def test_timestamp_migration_removes_fields_and_preserves_order():
    with sqlite3.connect(reactions.STORE) as db:
        db.execute("CREATE TABLE reactions (user_id TEXT, series_id TEXT, kind TEXT, created_at INTEGER, PRIMARY KEY(user_id,series_id,kind))")
        db.executemany("INSERT INTO reactions VALUES (?,?,?,?)", [("a", "1", "favorite", 900), ("a", "2", "favorite", 500), ("a", "3", "favorite", 900)])
        db.execute("CREATE TABLE browsing_history (user_id TEXT, series_id TEXT, visited_at INTEGER, PRIMARY KEY(user_id,series_id))")
        db.executemany("INSERT INTO browsing_history VALUES (?,?,?)", [("a", "1", 1000), ("a", "2", 3000), ("a", "3", 2000)])
    assert ids("favorites") == ["3", "1", "2"]
    assert ids("history") == ["2", "3", "1"]
    with reactions.open_store() as db:
        for table in ("reactions", "browsing_history"):
            columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
            assert "sort_order" in columns and not {"created_at", "visited_at"} & columns
            assert db.execute(f"SELECT MAX(sort_order) FROM {table}").fetchone()[0] == 3
    personal.record_visit("a", "1")
    reactions.reaction_state("a", "2", "favorite", False)
    reactions.reaction_state("a", "2", "favorite", True)
    assert ids("history") == ["1", "2", "3"]
    assert ids("favorites") == ["2", "3", "1"]


def test_endpoints_auth_order_permissions_and_isolation():
    anonymous = TestClient(main.app)
    assert anonymous.get("/api/me/history").status_code == 401
    assert anonymous.post("/api/series/s/visit", headers=ORIGIN).status_code == 401
    a, b = client_for("a"), client_for("b")
    for item in "14564":
        assert a.post(f"/api/series/{item}/visit", headers=ORIGIN).status_code == 204
    assert [item["id"] for item in a.get("/api/me/history").json()["items"]] == list("4651")
    assert b.get("/api/me/history").json() == {"items": [], "last": True}
    assert a.post("/api/series/blocked/visit", headers=ORIGIN).status_code == 404
    personal.record_visit("a", "blocked")
    result = a.get("/api/me/history").json()
    assert [item["id"] for item in result["items"]] == list("4651")
    assert result["items"][0]["title"] == "系列标题"
    a.patch("/api/series/4/reactions", headers=ORIGIN, json={"kind": "favorite", "selected": True})
    assert a.get("/api/me/favorites").json()["items"][0]["id"] == "4"
    assert b.get("/api/me/favorites").json()["items"] == []
    assert a.get("/api/me/history?page=-1").status_code == 422
