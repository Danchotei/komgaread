"""测试会话使用临时数据库，绝不清除开发环境的真实登录。"""
import pytest

from app import main, setup
from app.session_store import SessionStore


@pytest.fixture(autouse=True)
def isolated_config_cache():
    setup.reset_config_cache()
    yield
    setup.reset_config_cache()


@pytest.fixture(autouse=True)
def isolated_sessions(monkeypatch, tmp_path):
    store = SessionStore(tmp_path / "sessions.sqlite3")
    monkeypatch.setattr(main, "sessions", store)
    yield
    main.sessions.close()
    store.close()
