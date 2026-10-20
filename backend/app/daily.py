import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

STORE = Path(__file__).resolve().parents[1] / 'data' / 'daily.sqlite3'
lock = asyncio.Lock()


def china_day():
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def read(user, day):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(STORE) as db:
        db.execute('CREATE TABLE IF NOT EXISTS daily (user TEXT, day TEXT, items TEXT, PRIMARY KEY(user, day))')
        row = db.execute('SELECT items FROM daily WHERE user=? AND day=?', (user, day)).fetchone()
        return json.loads(row[0]) if row else None


def write(user, day, items):
    with sqlite3.connect(STORE) as db:
        db.execute('INSERT OR REPLACE INTO daily VALUES (?, ?, ?)', (user, day, json.dumps(items)))
        db.execute('DELETE FROM daily WHERE day < ?', (day,))
