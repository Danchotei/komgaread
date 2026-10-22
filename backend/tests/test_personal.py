import sqlite3
from concurrent.futures import ThreadPoolExecutor

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
        if path == "/api/v1/books/list":
            return httpx.Response(200, json={"content": [{"metadata": {"releaseDate": "2026-10-01"}}]})
        if path.endswith("/blocked"):
            raise HTTPException(404, "不可访问")
        if path == "/api/v2/users/me":
            user = kwargs["headers"]["X-Auth-Token"]
            return httpx.Response(200, json={"id": user, "email": f"{user}@example.com"})
        return httpx.Response(200, json={"id": path.split('/')[-1], "metadata": {"title": "系列标题", "genres": ["全彩"]}, "booksCount": 2})

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


def test_read_lists_while_another_connection_is_writing():
    personal.record_visit("a", "saved")
    reactions.reaction_state("a", "saved", "favorite", True)
    personal.profile_name("a", "reader")
    # 未提交的写事务占用写锁，但不能阻止其他连接读取已提交的数据。
    with sqlite3.connect(reactions.STORE) as writer:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO browsing_history VALUES ('a','pending',999)")
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: (
                ids("history"), ids("favorites"), personal.favorite_series_ids("a"),
                personal.profile_name("a"), reactions.reaction_state("a", "saved"),
            ))
            try:
                history, favorites, favorite_ids, name, state = future.result(timeout=2)
                assert history == favorites == favorite_ids == ["saved"]
                assert name == "reader" and state["favorited"]
            finally:
                writer.rollback()


def test_read_connection_rejects_accidental_writes():
    with reactions.open_store() as db:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("DELETE FROM browsing_history")


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
    assert result["items"][0]["genres"] == ["全彩"]
    assert result["items"][0]["lastReleaseDate"] == "2026-10-01"
    a.patch("/api/series/4/reactions", headers=ORIGIN, json={"kind": "favorite", "selected": True})
    assert a.get("/api/me/favorites").json()["items"][0]["id"] == "4"
    assert b.get("/api/me/favorites").json()["items"] == []
    assert a.get("/api/me/history?page=-1").status_code == 422


def test_display_name_default_save_persist_and_isolation():
    anonymous = TestClient(main.app)
    assert anonymous.get("/api/me/profile").status_code == 401
    assert anonymous.patch("/api/me/profile", headers=ORIGIN, json={"display_name": "名字"}).status_code == 401
    a, b = client_for("a"), client_for("b")
    assert a.get("/api/me/profile").json() == {"displayName": "a@example.com"}
    assert a.patch("/api/me/profile", headers=ORIGIN, json={"display_name": "  我的昵称  "}).json() == {"displayName": "我的昵称"}
    assert client_for("a").get("/api/me/profile").json() == {"displayName": "我的昵称"}
    assert b.get("/api/me/profile").json() == {"displayName": "b@example.com"}
    assert a.get("/api/auth/me").json()["email"] == "a@example.com"
    for name in ["", "   ", "长" * 41, "名字\n换行"]:
        assert a.patch("/api/me/profile", headers=ORIGIN, json={"display_name": name}).status_code == 422
    assert a.patch("/api/me/profile", headers=ORIGIN, json={"display_name": "冒充", "user_id": "b"}).status_code == 422
    assert a.get("/api/me/profile").json() == {"displayName": "我的昵称"}
