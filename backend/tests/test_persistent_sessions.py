import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.session_store import SessionStore

ORIGIN = {"Origin": "http://127.0.0.1:5173"}
USER = {"id": "reader", "email": "reader@example.com"}


def network(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(main, "KOMGA_URL", "https://komga.example")
    monkeypatch.setattr(main, "komga_url", lambda: "https://komga.example")


def test_persistence_cookie_sliding_expiry_and_no_password(monkeypatch):
    now = [1_000_000.0]
    monkeypatch.setattr(main, "time", lambda: now[0])
    def handler(request):
        if "authorization" in request.headers:
            assert request.url.params["remember-me"] == "true"
            return httpx.Response(200, json=USER, headers={"X-Auth-Token": "upstream-token", "Set-Cookie": "komga-remember-me=long-secret; Max-Age=31536000; Path=/; HttpOnly"})
        assert request.headers["X-Auth-Token"] == "upstream-token"
        return httpx.Response(200, json=USER)
    network(monkeypatch, handler)
    client = TestClient(main.app)
    response = client.post("/api/auth/login", headers=ORIGIN, json={"username": USER["email"], "password": "do-not-store-password"})
    assert response.status_code == 200
    assert "Max-Age=1209600" in response.headers["set-cookie"]
    assert "long-secret" not in response.text + response.headers["set-cookie"]
    session_id = response.cookies[main.COOKIE_NAME]
    db_path = main.sessions.path
    row = main.sessions.details(session_id)
    assert row["remember"] == "long-secret" and row["remember_expires"] == now[0] + 31536000
    assert "do-not-store-password" not in str(row)
    # 换成全新存储对象模拟后端重启，不复制任何内存状态。
    monkeypatch.setattr(main, "sessions", SessionStore(db_path))
    now[0] += 13 * 86400
    assert client.get("/api/auth/me").status_code == 200
    assert main.sessions.details(session_id)["expires"] == now[0] + main.SESSION_SECONDS
    now[0] += 14 * 86400 + 1
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert session_id not in main.sessions
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_ordinary_session_recovers_and_updates_credentials(monkeypatch):
    calls = []
    def handler(request):
        calls.append(dict(request.headers))
        if request.headers.get("cookie"):
            assert request.headers["cookie"] == "komga-remember-me=remember-a"
            assert request.headers["X-Auth-Token"] == ""
            return httpx.Response(200, json=USER, headers={"X-Auth-Token": "new-token", "Set-Cookie": "komga-remember-me=rotated; Max-Age=31536000"})
        if request.headers.get("X-Auth-Token") == "expired-token":
            return httpx.Response(401)
        assert request.headers["X-Auth-Token"] == "new-token"
        return httpx.Response(200, json=USER)
    network(monkeypatch, handler)
    main.sessions.create("local", "expired-token", main.time() + 100, "remember-a", main.time() + 31536000, "https://komga.example", USER["id"])
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, "local")
    response = client.get("/api/auth/me")
    assert response.status_code == 200 and response.json() == USER
    assert len(calls) == 3
    assert main.sessions.details("local")["token"] == "new-token"
    assert main.sessions.details("local")["remember"] == "rotated"


@pytest.mark.parametrize("failure,status,retained", [("rejected", 401, False), ("offline", 502, True), ("other-user", 401, False), ("missing-token", 502, True)])
def test_recovery_failures_do_not_restore_wrong_identity(monkeypatch, failure, status, retained):
    def handler(request):
        if not request.headers.get("cookie"):
            return httpx.Response(401)
        if failure == "offline":
            raise httpx.ConnectError("offline", request=request)
        if failure == "rejected":
            return httpx.Response(401)
        return httpx.Response(200, json={**USER, "id": "someone-else"} if failure == "other-user" else USER, headers={} if failure == "missing-token" else {"X-Auth-Token": "new"})
    network(monkeypatch, handler)
    main.sessions.create("local", "old", main.time() + 100, "remember", main.time() + 1000, "https://komga.example", USER["id"])
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, "local")
    assert client.get("/api/auth/me").status_code == status
    assert ("local" in main.sessions) is retained


def test_expired_remember_and_server_change_require_login(monkeypatch):
    calls = []
    network(monkeypatch, lambda request: calls.append(request) or httpx.Response(401))
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, "local")
    main.sessions.create("local", "old", main.time() + 100, "remember", main.time() - 1, "https://komga.example", USER["id"])
    assert client.get("/api/auth/me").status_code == 401 and len(calls) == 1
    main.sessions.create("local", "old", main.time() + 100, "remember", main.time() + 1000, "https://another.example", USER["id"])
    client.cookies.set(main.COOKIE_NAME, "local")
    assert client.get("/api/auth/me").status_code == 401 and len(calls) == 1


def test_concurrent_recovery_only_authenticates_once(monkeypatch):
    restored = []
    async def handler(request):
        if request.headers.get("cookie"):
            restored.append(1)
            await asyncio.sleep(0.01)
            return httpx.Response(200, json=USER, headers={"X-Auth-Token": "new-token"})
        return httpx.Response(200, json=USER) if request.headers["X-Auth-Token"] == "new-token" else httpx.Response(401)
    network(monkeypatch, handler)
    monkeypatch.setattr(main, "recovery_locks", [asyncio.Lock() for _ in range(32)])
    main.sessions.create("local", "old", main.time() + 100, "remember", main.time() + 1000, "https://komga.example", USER["id"])
    async def run():
        context = main.session_context.set("local")
        try:
            return await asyncio.gather(*(main.komga_request("GET", "/api/v2/users/me", headers={"X-Auth-Token": "old"}) for _ in range(8)))
        finally:
            main.session_context.reset(context)
    assert all(response.status_code == 200 for response in asyncio.run(run()))
    assert len(restored) == 1


def test_logout_does_not_revive_after_restart(monkeypatch):
    network(monkeypatch, lambda request: httpx.Response(204))
    main.sessions.create("local", "old", main.time() + 100, "remember", main.time() + 1000)
    path = main.sessions.path
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, "local")
    assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 204
    assert "local" not in SessionStore(path)


def test_image_stream_recovers_without_leaking_cookie(monkeypatch):
    def handler(request):
        if request.url.path == "/api/v2/users/me":
            assert request.headers["cookie"] == "komga-remember-me=remember"
            return httpx.Response(200, json=USER, headers={"X-Auth-Token": "new"})
        if request.headers["X-Auth-Token"] == "old":
            return httpx.Response(401)
        return httpx.Response(200, content=b"image-bytes", headers={"Content-Type": "image/jpeg"})
    network(monkeypatch, handler)
    main.sessions.create("local", "old", main.time() + 100, "remember", main.time() + 1000, "https://komga.example", USER["id"])
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, "local")
    response = client.get("/api/books/b1/pages/1")
    assert response.status_code == 200 and response.content == b"image-bytes"
    assert "remember" not in response.headers["set-cookie"]
    assert main.sessions.details("local")["token"] == "new"
