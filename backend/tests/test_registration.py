import itertools
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, registration, setup

ORIGIN = {"Origin": "http://127.0.0.1:5173"}
KEY = "test-admin-only-key"
BODY = {"email": "reader@example.com", "password": "reader-pass-123", "confirm_password": "reader-pass-123", "invite_code": "test-invite"}
clock = itertools.count(1000, 100)


@pytest.fixture(autouse=True)
def config(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "CONFIG_FILE", tmp_path / "komga.json")
    monkeypatch.setattr(main, "KOMGA_URL", "")
    monkeypatch.setattr(registration, "monotonic", lambda: next(clock))
    setup.write_config("https://komga.example", KEY, "test-invite")


def network(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def test_creates_streaming_only_user_without_leaking_secrets(monkeypatch):
    calls = []

    def handler(request):
        assert str(request.url) == "https://komga.example/api/v2/users"
        assert request.headers["X-API-Key"] == KEY
        body = json.loads(request.content)
        assert body == {"email": BODY["email"], "password": BODY["password"], "roles": ["PAGE_STREAMING"], "sharedLibraries": {"all": True, "libraryIds": []}}
        calls.append(body)
        return httpx.Response(201, json={"id": "new-user", "email": BODY["email"]})

    network(monkeypatch, handler)
    client = TestClient(main.app)
    assert client.get("/api/auth/registration").json() == {"enabled": True}
    response = client.post("/api/auth/register", headers=ORIGIN, json=BODY)
    assert response.status_code == 201 and len(calls) == 1
    assert KEY not in response.text and BODY["password"] not in response.text
    assert not response.cookies


def test_legacy_config_disables_registration():
    setup.write_config("https://komga.example")
    client = TestClient(main.app)
    assert client.get("/api/auth/registration").json() == {"enabled": False}
    assert client.post("/api/auth/register", headers=ORIGIN, json=BODY).status_code == 503


@pytest.mark.parametrize("changes", [
    {"email": "not-an-email"}, {"email": "a@b"},
    {"password": "short"}, {"confirm_password": "different-password"},
    {"password": "密" * 30, "confirm_password": "密" * 30},
    {"roles": ["ADMIN"]}, {"sharedLibraries": {"all": True}},
])
def test_invalid_input_never_reaches_komga(monkeypatch, changes):
    network(monkeypatch, lambda request: pytest.fail("invalid input reached Komga"))
    response = TestClient(main.app).post("/api/auth/register", headers=ORIGIN, json={**BODY, **changes})
    assert response.status_code == 422
    assert BODY["password"] not in response.text


@pytest.mark.parametrize("upstream,expected", [(400, 409), (409, 409), (401, 503), (403, 503), (500, 502)])
def test_upstream_errors_redacted(monkeypatch, upstream, expected):
    network(monkeypatch, lambda request: httpx.Response(upstream, text=KEY + BODY["password"]))
    response = TestClient(main.app).post("/api/auth/register", headers=ORIGIN, json=BODY)
    assert response.status_code == expected
    assert KEY not in response.text and BODY["password"] not in response.text


def test_registration_rate_limit(monkeypatch):
    now = next(clock)
    monkeypatch.setattr(registration, "monotonic", lambda: now)
    network(monkeypatch, lambda request: httpx.Response(201))
    client = TestClient(main.app)
    for _ in range(10):
        assert client.post("/api/auth/register", headers=ORIGIN, json=BODY).status_code == 201
    assert client.post("/api/auth/register", headers=ORIGIN, json=BODY).status_code == 429
    now += 61
    assert client.post("/api/auth/register", headers=ORIGIN, json=BODY).status_code == 201


@pytest.mark.parametrize("invite", ["wrong", "TEST-INVITE", " "])
def test_wrong_invitation_never_reaches_komga(monkeypatch, invite):
    network(monkeypatch, lambda request: pytest.fail("invalid invitation reached Komga"))
    response = TestClient(main.app).post("/api/auth/register", headers=ORIGIN, json={**BODY, "invite_code": invite})
    assert response.status_code == 403
    assert "test-invite" not in response.text


def test_missing_invitation_and_legacy_config(monkeypatch):
    client = TestClient(main.app)
    body = {key: value for key, value in BODY.items() if key != "invite_code"}
    assert client.post("/api/auth/register", headers=ORIGIN, json=body).status_code == 422
    setup.write_config("https://komga.example", KEY)
    assert client.get("/api/auth/registration").json() == {"enabled": False}
    assert client.post("/api/auth/register", headers=ORIGIN, json=BODY).status_code == 503
