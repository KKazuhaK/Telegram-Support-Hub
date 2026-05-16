from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from backend.app.core.config import settings

_JWT_ALGO = "HS256"
_BCRYPT_MAX_BYTES = 72


def _bcrypt_safe_bytes(plain: str) -> bytes:
    raw = plain.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        raw = raw[:_BCRYPT_MAX_BYTES]
    return raw


def hash_password(plain: str) -> str:
    digest = bcrypt.hashpw(_bcrypt_safe_bytes(plain), bcrypt.gensalt())
    return digest.decode("utf-8")


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_bcrypt_safe_bytes(plain), hashed.encode("utf-8"))
    except Exception:
        return False


def issue_token(
    subject: str,
    role: str,
    agent_id: int,
    *,
    actor_kind: str = "support_agent",
    actor_id: int | None = None,
    ttl_minutes: int | None = None,
) -> str:
    """Issue a JWT.

    `actor_kind` discriminates support_agent / business_agent / merchant
    so request handlers can apply the right tenant scope. `agent_id` and
    `role` are kept for backward compat with the existing CurrentUser
    plumbing — for non-support_agent actors `agent_id` is 0 and `role`
    mirrors the kind.
    """
    minutes = ttl_minutes if ttl_minutes is not None else settings.app_jwt_ttl_minutes
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "agent_id": agent_id,
        "actor_kind": actor_kind,
        "actor_id": actor_id if actor_id is not None else agent_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.app_jwt_secret, algorithm=_JWT_ALGO)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.app_jwt_secret, algorithms=[_JWT_ALGO])
