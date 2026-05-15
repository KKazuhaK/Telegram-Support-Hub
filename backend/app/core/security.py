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


def issue_token(subject: str, role: str, agent_id: int, ttl_minutes: int | None = None) -> str:
    minutes = ttl_minutes if ttl_minutes is not None else settings.app_jwt_ttl_minutes
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "agent_id": agent_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.app_jwt_secret, algorithm=_JWT_ALGO)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.app_jwt_secret, algorithms=[_JWT_ALGO])
