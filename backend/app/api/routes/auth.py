from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.app.api.deps import CurrentUserDep, DbSession
from backend.app.core.security import hash_password, issue_token, verify_password
from backend.app.models.agent import SupportAgent
from backend.app.services.audit import write_audit

router = APIRouter()


class LoginPayload(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    agent_id: int


class BootstrapAdminPayload(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    nickname: str | None = None


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginPayload, db: DbSession) -> TokenResponse:
    agent = db.scalar(select(SupportAgent).where(SupportAgent.username == payload.username))
    if not agent or agent.status != "enabled" or not verify_password(payload.password, agent.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    agent.last_login_at = datetime.now(UTC).isoformat()
    agent.online_status = "online"
    write_audit(db, actor=None, action="auth.login",
                target_type="support_agent", target_id=agent.id,
                detail={"username": agent.username})
    db.commit()

    token = issue_token(subject=agent.username, role=agent.role or "agent", agent_id=agent.id)
    return TokenResponse(access_token=token, role=agent.role or "agent", agent_id=agent.id)


@router.post("/bootstrap-admin", response_model=TokenResponse)
def bootstrap_admin(payload: BootstrapAdminPayload, db: DbSession) -> TokenResponse:
    """Create the first admin. Allowed only when no admin exists yet."""
    has_admin = db.scalar(select(func.count()).select_from(SupportAgent).where(SupportAgent.role == "admin"))
    if has_admin and int(has_admin) > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="admin already exists")

    agent = SupportAgent(
        username=payload.username,
        nickname=payload.nickname or payload.username,
        password_hash=hash_password(payload.password),
        role="admin",
        status="enabled",
    )
    db.add(agent)
    db.flush()
    write_audit(db, actor=None, action="auth.bootstrap_admin",
                target_type="support_agent", target_id=agent.id,
                detail={"username": agent.username})
    db.commit()
    db.refresh(agent)

    token = issue_token(subject=agent.username, role="admin", agent_id=agent.id)
    return TokenResponse(access_token=token, role="admin", agent_id=agent.id)


@router.get("/me")
def me(user: CurrentUserDep) -> dict:
    return {
        "agent_id": user.agent_id,
        "username": user.username,
        "role": user.role,
        "account_group_ids": user.account_group_ids,
        "is_admin": user.is_admin,
    }
