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


def test_origin_and_validation(monkeypatch):
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", {"http://127.0.0.1:5173"})
    client = TestClient(main.app)
    assert client.post("/api/auth/login", json={"username": "a", "password": "b"}, headers={"Origin": "https://other.example"}).status_code == 403
    assert client.post("/api/auth/login", json={"username": "", "password": ""}, headers=ORIGIN).status_code == 422


@pytest.mark.parametrize("host,origin,secure,expected", [
    ("192.168.0.209:8777", "http://192.168.0.209:8777", False, 422),
    ("reader.example", "https://reader.example", True, 422),
    ("another.example", "https://another.example", True, 422),
    ("reader.example:443", "https://reader.example", True, 422),
    ("[::1]:8777", "http://[::1]:8777", False, 422),
    ("reader.example", "https://other.example", True, 422),
    ("reader.example:8777", "http://reader.example:8778", False, 422),
    ("reader.example", "http://reader.example", True, 422),
    ("reader.example", "null", False, 403),
    ("reader.example", "http://reader.example/path", False, 403),
    ("reader.example", "http://user@reader.example", False, 403),
    ("reader.example", "http://reader.example:bad", False, 403),
])
def test_cross_origin_policy(monkeypatch, host, origin, secure, expected):
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", {"*"})
    monkeypatch.setattr(main, "COOKIE_SECURE", secure)
    response = TestClient(main.app).post("/api/auth/login", json={"username": "", "password": ""},
                                         headers={"Host": host, "Origin": origin})
    # 422 表明来源校验已通过，之后才被空账号的输入校验拦截；无需真实密码或 Komga。
    assert response.status_code == expected


def test_cors_preflight_and_credentials(monkeypatch):
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", {"*"})
    client = TestClient(main.app)
    origin = "https://public-reader.example"
    preflight = client.options("/api/auth/login", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    })
    assert preflight.status_code == 200
    for response in (preflight, client.get("/api/auth/me", headers={"Origin": origin})):
        assert response.headers["Access-Control-Allow-Origin"] == origin
        assert response.headers["Access-Control-Allow-Credentials"] == "true"
        assert "Origin" in response.headers["Vary"]
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", {"https://only.example"})
    rejected = client.options("/api/auth/login", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
    assert rejected.status_code == 400
    assert "Access-Control-Allow-Origin" not in rejected.headers


def test_missing_origin_and_spoofed_forwarded_host(monkeypatch):
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", set())
    client = TestClient(main.app)
    assert client.post("/api/auth/login", json={}).status_code == 403
    assert client.post("/api/auth/login", json={}, headers={
        "Origin": "http://evil.example", "X-Forwarded-Host": "evil.example",
    }).status_code == 403


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
