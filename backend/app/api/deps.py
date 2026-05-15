from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import decode_token
from backend.app.models.agent import SupportAgent
from backend.app.services.permissions import CurrentUser, load_current_user

DbSession = Annotated[Session, Depends(get_db)]


def _extract_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(
    db: DbSession, authorization: str | None = Header(default=None)
) -> CurrentUser:
    token = _extract_token(authorization)
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc

    agent_id = payload.get("agent_id")
    agent = db.get(SupportAgent, agent_id) if agent_id else None
    if not agent or agent.status != "enabled":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="agent disabled or missing")
    return load_current_user(db, agent)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_admin(user: CurrentUserDep) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return user


AdminDep = Annotated[CurrentUser, Depends(require_admin)]


def require_permission(attr: str):
    def _checker(user: CurrentUserDep) -> CurrentUser:
        if not user.can(attr):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"missing {attr}")
        return user

    return _checker
