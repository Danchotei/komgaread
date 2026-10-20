import httpx
import pytest
from fastapi.testclient import TestClient
from app import main

ORIGIN = {"Origin": "http://127.0.0.1:5173"}


@pytest.fixture(autouse=True)
def reset_sessions():
    main.sessions.clear()
    yield
    main.sessions.clear()


def test_login_isolation_refresh_and_logout(monkeypatch):
    tokens = {}

    async def mock_request(method, path, **kwargs):
        if "auth" in kwargs:
            token = f"token-{len(tokens)}"
            user = {"id": token, "email": f"user-{len(tokens)}@example.com"}
            tokens[token] = user
            return httpx.Response(200, json=user, headers={"X-Auth-Token": token})
        token = kwargs["headers"]["X-Auth-Token"]
        if path == "/api/logout":
            tokens.pop(token)
            return httpx.Response(204)
        return httpx.Response(200, json=tokens[token])

    monkeypatch.setattr(main, "komga_request", mock_request)
    a, b = TestClient(main.app), TestClient(main.app)
    assert a.get("/api/auth/me").status_code == 401
    first = a.post("/api/auth/login", json={"username": "a", "password": "secret-a"}, headers=ORIGIN)
    second = b.post("/api/auth/login", json={"username": "b", "password": "secret-b"}, headers=ORIGIN)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] != second.json()["id"]
    assert "HttpOnly" in first.headers["set-cookie"]
    assert "secret-a" not in str(main.sessions)
    assert a.get("/api/auth/me").json() == first.json()
    assert b.get("/api/auth/me").json() == second.json()
    assert a.post("/api/auth/logout", headers=ORIGIN).status_code == 204
    assert a.get("/api/auth/me").status_code == 401
    assert b.get("/api/auth/me").status_code == 200


def test_origin_and_validation():
    client = TestClient(main.app)
    assert client.post("/api/auth/login", json={"username": "a", "password": "b"}, headers={"Origin": "https://other.example"}).status_code == 403
    assert client.post("/api/auth/login", json={"username": "", "password": ""}, headers=ORIGIN).status_code == 422


def test_expired_session():
    main.sessions["expired"] = ("token", 0)
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, "expired")
    assert client.get("/api/auth/me").status_code == 401
    assert "expired" not in main.sessions


def test_upstream_error_and_no_shared_cookies(monkeypatch):
    clients = []

    class FakeClient:
        def __init__(self, **kwargs):
            clients.append(self)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def request(self, *args, **kwargs):
            return httpx.Response(401)

    monkeypatch.setattr(main.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(main, "KOMGA_URL", "https://komga.example")
    client = TestClient(main.app)
    for _ in range(2):
        result = client.post("/api/auth/login", json={"username": "a", "password": "bad"}, headers=ORIGIN)
        assert result.status_code == 401
        assert main.COOKIE_NAME not in result.cookies
    assert len(clients) == 2 and clients[0] is not clients[1]


def test_logout_when_komga_is_offline(monkeypatch):
    async def offline(*args, **kwargs):
        raise main.HTTPException(502, "offline")
    monkeypatch.setattr(main, "komga_request", offline)
    main.sessions["local"] = ("token", main.time() + 60)
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, "local")
    assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 204
    assert not main.sessions



def test_missing_upstream_session(monkeypatch):
    async def missing_token(*args, **kwargs):
        return httpx.Response(200, json={"id": "a", "email": "a@example.com"})
    monkeypatch.setattr(main, "komga_request", missing_token)
    client = TestClient(main.app)
    result = client.post("/api/auth/login", json={"username": "a", "password": "b"}, headers=ORIGIN)
    assert result.status_code == 502
    assert not main.sessions
