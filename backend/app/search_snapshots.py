"""有界的搜索快照；按会话与权限隔离，翻页复用排序，重启或事件变更后失效。"""
from collections import OrderedDict
from secrets import token_urlsafe
from time import monotonic

from fastapi import HTTPException

snapshots = OrderedDict()
MAX_ITEMS = 100_000
MAX_SNAPSHOTS = 128
LIFETIME = 30 * 60


def save(scope, signature, revision, items):
    # 总条目数也设上限，避免少数大书库占用无界内存。
    if len(items) > MAX_ITEMS:
        raise HTTPException(503, "匹配结果过多，请缩小搜索范围")
    now = monotonic()
    for key in list(snapshots):
        if snapshots[key][0] <= now:
            del snapshots[key]
    while snapshots and (len(snapshots) >= MAX_SNAPSHOTS or sum(len(value[4]) for value in snapshots.values()) + len(items) > MAX_ITEMS):
        snapshots.popitem(last=False)
    key = token_urlsafe(24)
    snapshots[key] = (now + LIFETIME, scope, signature, revision, items)
    return key


def read(key, scope, signature, revision):
    value = snapshots.get(key)
    if value and value[0] <= monotonic():
        del snapshots[key]
        value = None
    if not value or value[1:4] != (scope, signature, revision):
        raise HTTPException(409, "搜索结果已更新或过期，请重新搜索")
    snapshots.move_to_end(key)
    return value[4]
