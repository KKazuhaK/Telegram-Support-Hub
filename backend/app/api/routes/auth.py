from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.app.api.deps import CurrentUserDep, DbSession
from backend.app.core.security import hash_password, issue_token, verify_password
from backend.app.models.agent import SupportAgent
from backend.app.models.tenant import BusinessAgent, Merchant
from backend.app.services.audit import write_audit
from backend.app.services.permissions import ROLE_LABELS

router = APIRouter()


class LoginPayload(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    agent_id: int
    actor_kind: str = "support_agent"
    actor_id: int = 0


class BootstrapAdminPayload(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    nickname: str | None = None


def _admin_count(db) -> int:
    n = db.scalar(
        select(func.count()).select_from(SupportAgent).where(SupportAgent.role == "admin")
    )
    return int(n or 0)


@router.get("/has-admin")
def has_admin(db: DbSession) -> dict:
    """Public probe so the login page can hide the bootstrap tab once an
    admin exists. Returns no sensitive data."""
    return {"has_admin": _admin_count(db) > 0}


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginPayload, db: DbSession) -> TokenResponse:
    agent = db.scalar(select(SupportAgent).where(SupportAgent.username == payload.username))
    if not agent or agent.status != "enabled" or not verify_password(payload.password, agent.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    agent.last_login_at = datetime.now(UTC).isoformat()
    agent.online_status = "online"
    write_audit(db, actor=None, action="auth.login",
                target_type="support_agent", target_id=agent.id,
                detail={"username": agent.username})
    db.commit()

    token = issue_token(
        subject=agent.username, role=agent.role or "agent", agent_id=agent.id,
        actor_kind="support_agent", actor_id=agent.id,
    )
    return TokenResponse(
        access_token=token, role=agent.role or "agent", agent_id=agent.id,
        actor_kind="support_agent", actor_id=agent.id,
    )


@router.post("/bootstrap-admin", response_model=TokenResponse)
def bootstrap_admin(payload: BootstrapAdminPayload, db: DbSession) -> TokenResponse:
    """Create the first admin. Allowed only when no admin exists yet."""
    if _admin_count(db) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="系统已存在管理员账号，请直接登录",
        )

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

    token = issue_token(
        subject=agent.username, role="admin", agent_id=agent.id,
        actor_kind="support_agent", actor_id=agent.id,
    )
    return TokenResponse(
        access_token=token, role="admin", agent_id=agent.id,
        actor_kind="support_agent", actor_id=agent.id,
    )


@router.post("/business-login", response_model=TokenResponse)
def business_login(payload: LoginPayload, db: DbSession) -> TokenResponse:
    """Login for 商务代理 (resellers). Looks up by `name`."""
    ba = db.scalar(select(BusinessAgent).where(BusinessAgent.name == payload.username))
    if not ba or not ba.status or not verify_password(payload.password, ba.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    ba.last_login_at = datetime.now(UTC).isoformat()
    ba.online_status = "online"
    write_audit(db, actor=None, action="auth.business_login",
                target_type="business_agent", target_id=ba.id,
                detail={"name": ba.name})
    db.commit()

    token = issue_token(
        subject=ba.name, role="business_agent", agent_id=0,
        actor_kind="business_agent", actor_id=ba.id,
    )
    return TokenResponse(
        access_token=token, role="business_agent", agent_id=0,
        actor_kind="business_agent", actor_id=ba.id,
    )


@router.post("/merchant-login", response_model=TokenResponse)
def merchant_login(payload: LoginPayload, db: DbSession) -> TokenResponse:
    """Login for 商户 (merchants)."""
    m = db.scalar(select(Merchant).where(Merchant.name == payload.username))
    if not m or not m.status or not verify_password(payload.password, m.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    m.last_login_at = datetime.now(UTC).isoformat()
    m.online_status = "online"
    write_audit(db, actor=None, action="auth.merchant_login",
                target_type="merchant", target_id=m.id,
                detail={"name": m.name})
    db.commit()

    token = issue_token(
        subject=m.name, role="merchant", agent_id=0,
        actor_kind="merchant", actor_id=m.id,
    )
    return TokenResponse(
        access_token=token, role="merchant", agent_id=0,
        actor_kind="merchant", actor_id=m.id,
    )


@router.get("/me")
def me(user: CurrentUserDep) -> dict:
    return {
        "agent_id": user.agent_id,
        "username": user.username,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
        "account_group_ids": user.account_group_ids,
        "is_admin": user.is_admin,
        "actor_kind": user.actor_kind,
        "actor_id": user.actor_id,
    }
