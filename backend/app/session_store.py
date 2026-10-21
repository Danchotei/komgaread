"""持久化登录凭据；密码永不落盘，数据文件须与 /data 一同保护。"""
import os
import sqlite3
from collections.abc import MutableMapping
from contextlib import closing, contextmanager
from pathlib import Path


class SessionStore(MutableMapping):
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        self.path.chmod(0o600)
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, token TEXT NOT NULL, expires REAL NOT NULL, remember TEXT NOT NULL, remember_expires REAL NOT NULL, origin TEXT NOT NULL, user_id TEXT NOT NULL)")
            yield db

    def details(self, key):
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (key,)).fetchone()
            return dict(row) if row else None

    def create(self, key, token, expires, remember="", remember_expires=0, origin="", user_id=""):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?)", (key, token, expires, remember, remember_expires, origin, user_id))

    def credentials(self, key, token, remember=None, remember_expires=None):
        with self.connect() as db:
            if remember is None:
                db.execute("UPDATE sessions SET token=? WHERE id=?", (token, key))
            else:
                db.execute("UPDATE sessions SET token=?,remember=?,remember_expires=? WHERE id=?", (token, remember, remember_expires, key))

    def touch(self, key, now, expires):
        with self.connect() as db:
            return db.execute("UPDATE sessions SET expires=MAX(expires,?) WHERE id=? AND expires>?", (expires, key, now)).rowcount > 0

    def prune(self, now):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires<=?", (now,))

    def pop(self, key, default=None):
        with self.connect() as db:
            row = db.execute("DELETE FROM sessions WHERE id=? RETURNING token,expires", (key,)).fetchone()
            return (row[0], row[1]) if row else default

    def __getitem__(self, key):
        row = self.details(key)
        if row is None:
            raise KeyError(key)
        return row["token"], row["expires"]

    def __setitem__(self, key, value):
        self.create(key, value[0], value[1])

    def __delitem__(self, key):
        with self.connect() as db:
            if not db.execute("DELETE FROM sessions WHERE id=?", (key,)).rowcount:
                raise KeyError(key)

    def __iter__(self):
        with self.connect() as db:
            return iter([row[0] for row in db.execute("SELECT id FROM sessions")])

    def __len__(self):
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    def clear(self):
        with self.connect() as db:
            db.execute("DELETE FROM sessions")
