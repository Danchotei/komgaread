import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, setup, registration

ORIGIN = {"Origin": "http://127.0.0.1:5173"}
KEY = "test-initialization-key-12345"
API_KEY = "test-komga-admin-key"
BODY = {"setup_key": KEY, "primary_url": "https://public.example/komga/", "api_key": API_KEY, "invite_code": "test-invite"}


def test_cached_config_avoids_disk_reads_and_manual_edits_need_reload(monkeypatch):
    setup.write_config("https://first.example", API_KEY, "first-invite")
    setup.reset_config_cache()
    assert main.komga_url() == "https://first.example"
    setup.CONFIG_FILE.write_text(json.dumps({"primary_url": "https://second.example", "api_key": "second", "invite_code": "second-invite"}))
    with monkeypatch.context() as patch:
        patch.setattr(type(setup.CONFIG_FILE), "read_text", lambda *a, **k: pytest.fail("缓存命中时不应读盘"))
        patch.setattr(type(setup.CONFIG_FILE), "exists", lambda *a, **k: pytest.fail("缓存命中时不应检查文件"))
        assert main.komga_url() == "https://first.example"
        assert registration.registration_credentials() == (API_KEY, "first-invite")
    setup.reset_config_cache()
    assert main.komga_url() == "https://second.example"
    assert registration.registration_credentials() == ("second", "second-invite")


def test_save_refreshes_cache_only_after_success(monkeypatch):
    setup.write_config("https://first.example", API_KEY, "first-invite")
    setup.write_config("https://second.example", "second", "second-invite")
    assert main.komga_url() == "https://second.example"
    def fail(*args, **kwargs):
        raise OSError("write failed")
    monkeypatch.setattr(type(setup.CONFIG_FILE), "replace", fail)
    with pytest.raises(main.HTTPException):
        setup.write_config("https://third.example", "third", "third-invite")
    assert main.komga_url() == "https://second.example"
    assert registration.registration_credentials() == ("second", "second-invite")


def test_missing_file_is_cached_until_setup_saves(monkeypatch):
    assert main.komga_url() == ""
    with monkeypatch.context() as patch:
        patch.setattr(type(setup.CONFIG_FILE), "read_text", lambda *a, **k: pytest.fail("未配置状态也应缓存"))
        assert main.komga_url() == ""
        assert registration.registration_credentials() == ("", "")
    setup.write_config("https://new.example", API_KEY, "test-invite")
    assert main.komga_url() == "https://new.example"


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "CONFIG_FILE", tmp_path / "data" / "komga.json")
    monkeypatch.setattr(main, "KOMGA_URL", "")
    monkeypatch.setenv("SETUP_KEY", KEY)
    main.sessions.clear()
    yield
    main.sessions.clear()


def admin_response(request):
    assert request.headers.get("X-API-Key") == API_KEY
    if request.url.path.endswith("/users"):
        return httpx.Response(200, json=[])
    return httpx.Response(200, json={"id": "admin", "email": "admin@example.com"})


def mock_network(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def test_save_persist_and_close_setup(monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return admin_response(request)

    mock_network(monkeypatch, handler)
    client = TestClient(main.app)
    assert client.get("/api/setup").json() == {"configured": False}
    assert client.post("/api/setup/test", headers=ORIGIN, json=BODY).status_code == 200
    assert not setup.CONFIG_FILE.exists()
    response = client.post("/api/setup", headers=ORIGIN, json=BODY)
    assert response.status_code == 200
    assert all(item["reachable"] for item in response.json()["checks"])
    saved = json.loads(setup.CONFIG_FILE.read_text())
    assert saved == {"primary_url": "https://public.example/komga", "api_key": API_KEY, "invite_code": "test-invite"}
    assert API_KEY not in response.text
    assert API_KEY not in client.get("/api/setup").text
    assert "test-invite" not in response.text
    assert "test-invite" not in client.get("/api/setup").text
    assert KEY not in setup.CONFIG_FILE.read_text()
    # 新客户端复用已保存的配置；清空缓存模拟重启后仍可读取落盘数据。
    assert TestClient(main.app).get("/api/setup").json()["configured"] is True
    setup.reset_config_cache()
    assert main.komga_url() == saved["primary_url"]
    count = len(calls)
    assert client.post("/api/setup", headers=ORIGIN, json=BODY).status_code == 409
    assert client.post("/api/setup/test", headers=ORIGIN, json=BODY).status_code == 409
    assert len(calls) == count


def test_setup_key_and_origin_before_network(monkeypatch):
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", {"http://127.0.0.1:5173"})
    def unexpected(request):
        pytest.fail("未授权请求不应访问上游")
    mock_network(monkeypatch, unexpected)
    client = TestClient(main.app)
    assert client.post("/api/setup", headers=ORIGIN, json={**BODY, "setup_key": "wrong"}).status_code == 403
    assert client.post("/api/setup", headers={"Origin": "https://evil.example"}, json=BODY).status_code == 403
    monkeypatch.delenv("SETUP_KEY")
    assert client.get("/api/setup").json() == {"configured": False}
    assert client.post("/api/setup", headers=ORIGIN, json=BODY).status_code == 403
    assert not setup.CONFIG_FILE.exists()


def test_automatic_key_persist_login_and_no_public_leak(monkeypatch, caplog):
    monkeypatch.delenv("SETUP_KEY")
    mock_network(monkeypatch, admin_response)
    with TestClient(main.app) as client:
        key_file = setup.CONFIG_FILE.parent / "setup.key"
        key = key_file.read_text()
        assert len(key) >= 32 and key in caplog.text
        assert setup.setup_key() == key
        assert key not in client.get("/api/setup").text
        response = client.post("/api/setup", headers=ORIGIN, json={**BODY, "setup_key": key})
        assert response.status_code == 200
        assert key not in setup.CONFIG_FILE.read_text()
    caplog.clear()
    # 已初始化后，不再输出密钥；磁盘上的密钥保持不变。
    with TestClient(main.app) as client:
        assert client.get("/api/setup").json() == {"configured": True}
        assert key not in caplog.text
    assert key_file.read_text() == key


def test_manual_key_precedence_and_short_key(monkeypatch):
    assert setup.setup_key() == KEY
    assert not (setup.CONFIG_FILE.parent / "setup.key").exists()
    monkeypatch.setenv("SETUP_KEY", "short")
    assert TestClient(main.app).get("/api/setup").status_code == 503


def test_invalid_automatic_key_not_silently_replaced(monkeypatch):
    monkeypatch.delenv("SETUP_KEY")
    setup.CONFIG_FILE.parent.mkdir()
    key_file = setup.CONFIG_FILE.parent / "setup.key"
    key_file.write_text("bad")
    assert TestClient(main.app).get("/api/setup").status_code == 503
    assert key_file.read_text() == "bad"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://host", "http://user:pass@host", "http://host?key=secret", "http://host#fragment", "http://host:99999", "   "])
def test_invalid_addresses(monkeypatch, url):
    assert TestClient(main.app).post("/api/setup", headers=ORIGIN, json={**BODY, "primary_url": url}).status_code == 422


def test_connection_failure_not_saved(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("offline", request=request)
    mock_network(monkeypatch, handler)
    response = TestClient(main.app).post("/api/setup", headers=ORIGIN, json=BODY)
    assert response.status_code == 422
    assert not setup.CONFIG_FILE.exists()


@pytest.mark.parametrize("status", [200, 302, 403, 404, 500])
def test_unusable_addresses_not_saved(monkeypatch, status):
    mock_network(monkeypatch, lambda request: httpx.Response(status, text="not a Komga API"))
    assert TestClient(main.app).post("/api/setup", headers=ORIGIN, json=BODY).status_code == 422
    assert not setup.CONFIG_FILE.exists()


def test_legacy_env_and_corrupt_config(monkeypatch):
    monkeypatch.setattr(main, "KOMGA_URL", "https://legacy.example")
    client = TestClient(main.app)
    assert client.get("/api/setup").json()["configured"] is True
    assert client.post("/api/setup", headers=ORIGIN, json=BODY).status_code == 409
    setup.CONFIG_FILE.parent.mkdir()
    setup.CONFIG_FILE.write_text("broken")
    setup.reset_config_cache()  # 手动修改文件在下次启动重新加载。
    assert client.get("/api/setup").status_code == 503


def test_storage_error(monkeypatch):
    mock_network(monkeypatch, admin_response)
    setup.CONFIG_FILE.parent.write_text("not a directory")
    assert TestClient(main.app).post("/api/setup", headers=ORIGIN, json=BODY).status_code == 503


@pytest.mark.parametrize("failure,expected", [("connect", 502), ("auth", 401), ("timeout", 502)])
def test_single_address_errors(monkeypatch, failure, expected):
    monkeypatch.setattr(main, "KOMGA_URL", "https://primary.example")
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if failure == "connect":
            raise httpx.ConnectError("offline", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("read timeout", request=request)
        return httpx.Response(401)

    mock_network(monkeypatch, handler)
    response = TestClient(main.app).post("/api/auth/login", headers=ORIGIN, json={"username": "u", "password": "p"})
    assert response.status_code == expected
    assert calls == ["primary.example"]


@pytest.mark.parametrize("api_key", ["", API_KEY])
def test_old_config_uses_only_primary(monkeypatch, api_key):
    monkeypatch.setattr(main, "KOMGA_URL", "https://primary.example")
    # 已有双地址配置无需重新初始化，但只使用原先的主要地址。
    setup.CONFIG_FILE.parent.mkdir()
    setup.CONFIG_FILE.write_text(json.dumps({"primary_url": "https://public.example", "backup_url": "http://unused.example", "api_key": api_key, "invite_code": "preserved-invite"}))
    calls = []

    def handler(request):
        calls.append(request.url.host)
        assert request.headers["X-Auth-Token"] == "reader-token"
        return httpx.Response(200, content=b"image", headers={"Content-Type": "image/jpeg"})

    mock_network(monkeypatch, handler)
    main.sessions["reader"] = ("reader-token", main.time() + 60)
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, "reader")
    response = client.get("/api/books/b1/pages/1")
    assert response.status_code == 200 and response.content == b"image"
    assert calls == ["public.example"]
    expected = {"primary_url": "https://public.example", "invite_code": "preserved-invite"}
    if api_key:
        expected["api_key"] = api_key
    assert json.loads(setup.CONFIG_FILE.read_text()) == expected


@pytest.mark.parametrize("status", [401, 403])
def test_invalid_or_non_admin_key_not_saved(monkeypatch, status):
    def handler(request):
        assert request.headers["X-API-Key"] == API_KEY
        if status == 403 and request.url.path.endswith("/me"):
            return admin_response(request)
        return httpx.Response(status)
    mock_network(monkeypatch, handler)
    client = TestClient(main.app)
    result = client.post("/api/setup/test", headers=ORIGIN, json=BODY)
    assert result.json()["checks"][0]["reachable"] is False
    assert API_KEY not in result.text
    assert client.post("/api/setup", headers=ORIGIN, json=BODY).status_code == 422
    assert not setup.CONFIG_FILE.exists()


@pytest.mark.parametrize("api_key", [None, "", "   ", "secret with spaces", "s" * 4097])
def test_api_key_required_and_validation_redacted(api_key):
    body = {**BODY, "api_key": api_key}
    if api_key is None:
        del body["api_key"]
    response = TestClient(main.app).post("/api/setup", headers=ORIGIN, json=body)
    assert response.status_code == 422
    assert "input" not in response.json()
    if api_key and api_key.strip():
        assert api_key not in response.text
    assert not setup.CONFIG_FILE.exists()
