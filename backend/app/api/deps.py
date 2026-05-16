from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import decode_token
from backend.app.models.agent import SupportAgent
from backend.app.models.tenant import BusinessAgent, Merchant
from backend.app.services.permissions import (
    CurrentUser,
    load_business_agent_user,
    load_current_user,
    load_merchant_user,
    permission_denied_detail,
)

DbSession = Annotated[Session, Depends(get_db)]


def _extract_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(
    db: DbSession, authorization: str | None = Header(default=None)
) -> CurrentUser:
    token = _extract_token(authorization)
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
        ) from exc

    actor_kind = payload.get("actor_kind", "support_agent")
    actor_id = payload.get("actor_id") or payload.get("agent_id")

    if actor_kind == "business_agent":
        ba = db.get(BusinessAgent, actor_id) if actor_id else None
        if not ba or not ba.status:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="账号已被禁用或不存在",
            )
        return load_business_agent_user(ba.name, ba.id)

    if actor_kind == "merchant":
        m = db.get(Merchant, actor_id) if actor_id else None
        if not m or not m.status:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="账号已被禁用或不存在",
            )
        return load_merchant_user(m.name, m.id)

    # Default: support_agent (admin / supervisor / agent).
    agent_id = payload.get("agent_id")
    agent = db.get(SupportAgent, agent_id) if agent_id else None
    if not agent or agent.status != "enabled":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号已被禁用或不存在",
        )
    return load_current_user(db, agent)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def get_current_user_flexible(
    db: DbSession,
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> CurrentUser:
    """Like `get_current_user` but also accepts the token via ?token=... so
    browser-rendered <img>/<audio>/<a download> tags that can't add an
    Authorization header still authenticate. Used by file/material download
    routes only."""
    if authorization:
        return get_current_user(db=db, authorization=authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return get_current_user(db=db, authorization=f"Bearer {token}")


FlexibleUserDep = Annotated[CurrentUser, Depends(get_current_user_flexible)]


def require_admin(user: CurrentUserDep) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该操作需要管理员权限",
        )
    return user


AdminDep = Annotated[CurrentUser, Depends(require_admin)]


def require_permission(attr: str):
    def _checker(user: CurrentUserDep) -> CurrentUser:
        if not user.can(attr):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=permission_denied_detail(attr),
            )
        return user

    return _checker
