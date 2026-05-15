from __future__ import annotations

import contextlib
import uuid
from typing import Iterator

import redis

from backend.app.core.config import settings


_pool: redis.ConnectionPool | None = None


def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    return redis.Redis(connection_pool=_pool)


@contextlib.contextmanager
def account_send_lock(account_id: int, ttl_seconds: int) -> Iterator[bool]:
    """Try to acquire `send_lock:{account_id}`. Yields True if acquired.
    Releases (best-effort) on exit only when the token still matches.
    """
    client = get_redis()
    key = f"send_lock:{account_id}"
    token = uuid.uuid4().hex
    acquired = bool(client.set(key, token, nx=True, ex=max(1, ttl_seconds)))
    try:
        yield acquired
    finally:
        if acquired:
            # release only if we still own it
            lua = (
                "if redis.call('get', KEYS[1]) == ARGV[1] "
                "then return redis.call('del', KEYS[1]) else return 0 end"
            )
            try:
                client.eval(lua, 1, key, token)
            except Exception:
                pass
