import asyncio
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from weakref import WeakValueDictionary

STORE = Path(__file__).resolve().parents[1] / 'data' / 'daily.sqlite3'
_locks = WeakValueDictionary()


def generation_lock(user):
    # 只合并同一账号的生成任务；无人使用的锁自动回收。
    lock = _locks.get(user)
    if lock is None:
        lock = asyncio.Lock()
        _locks[user] = lock
    return lock


def china_day():
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def read(user, day, count=4):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(STORE)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS daily (user TEXT, day TEXT, items TEXT, requested_count INTEGER NOT NULL DEFAULT 4, PRIMARY KEY(user, day))')
        if 'requested_count' not in {row[1] for row in db.execute('PRAGMA table_info(daily)')}:
            db.execute('ALTER TABLE daily ADD COLUMN requested_count INTEGER NOT NULL DEFAULT 4')
        # 目标数量变化时更新当天缓存；小书库不足 8 个也不会每次重新抽取。
        row = db.execute('SELECT items FROM daily WHERE user=? AND day=? AND requested_count=?', (user, day, count)).fetchone()
        return json.loads(row[0]) if row else None


def write(user, day, items, count=4):
    with closing(sqlite3.connect(STORE)) as db, db:
        db.execute('INSERT OR REPLACE INTO daily(user,day,items,requested_count) VALUES (?, ?, ?, ?)', (user, day, json.dumps(items), count))
        db.execute('DELETE FROM daily WHERE day < ?', (day,))
