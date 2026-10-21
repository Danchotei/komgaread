"""测试会话使用临时数据库，绝不清除开发环境的真实登录。"""
import pytest

from app import main
from app.session_store import SessionStore


@pytest.fixture(autouse=True)
def isolated_sessions(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "sessions", SessionStore(tmp_path / "sessions.sqlite3"))
