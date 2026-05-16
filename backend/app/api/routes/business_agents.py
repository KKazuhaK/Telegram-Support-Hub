from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.app.api.deps import AdminDep, CurrentUserDep, DbSession
from backend.app.core.security import hash_password
from backend.app.models.tenant import BusinessAgent
from backend.app.services.audit import write_audit
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


class BusinessAgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    nickname: str | None = None
    password: str = Field(min_length=6, max_length=200)
    platform_name: str | None = None
    logo_url: str | None = None
    custom_image_url: str | None = None
    domains: str | None = None
    status: bool = True
    remark: str | None = None


class BusinessAgentUpdate(BaseModel):
    nickname: str | None = None
    password: str | None = Field(default=None, min_length=6, max_length=200)
    platform_name: str | None = None
    logo_url: str | None = None
    custom_image_url: str | None = None
    domains: str | None = None
    status: bool | None = None
    remark: str | None = None


def _public(row: BusinessAgent) -> dict:
    data = to_dict(row)
    data.pop("password_hash", None)
    return data


@router.get("")
def list_agents(
    db: DbSession,
    user: CurrentUserDep,
    q: str | None = None,
    status: bool | None = None,
    online_status: str | None = None,
) -> list[dict]:
    stmt = select(BusinessAgent).order_by(BusinessAgent.id.desc())

    # Tenant scope:
    # - support_agent: all (admin tool)
    # - business_agent: only itself
    # - merchant: empty (no business listing other resellers)
    if user.actor_kind == "business_agent":
        stmt = stmt.where(BusinessAgent.id == user.actor_id)
    elif user.actor_kind == "merchant":
        stmt = stmt.where(BusinessAgent.id == -1)

    if q:
        like = f"%{q}%"
        stmt = stmt.where((BusinessAgent.name.like(like)) | (BusinessAgent.nickname.like(like)))
    if status is not None:
        stmt = stmt.where(BusinessAgent.status.is_(status))
    if online_status:
        stmt = stmt.where(BusinessAgent.online_status == online_status)
    rows = list(db.scalars(stmt))
    return [_public(r) for r in rows]


@router.post("")
def create_agent(payload: BusinessAgentCreate, db: DbSession, admin: AdminDep) -> dict:
    if db.scalar(select(BusinessAgent).where(BusinessAgent.name == payload.name)):
        raise HTTPException(status_code=409, detail="该商务代理名称已被占用")
    row = BusinessAgent(
        name=payload.name,
        nickname=payload.nickname,
        password_hash=hash_password(payload.password),
        platform_name=payload.platform_name,
        logo_url=payload.logo_url,
        custom_image_url=payload.custom_image_url,
        domains=payload.domains,
        status=payload.status,
        remark=payload.remark,
    )
    db.add(row)
    db.flush()
    write_audit(db, actor=admin, action="business_agent.create",
                target_type="business_agent", target_id=row.id,
                detail={"name": payload.name, "nickname": payload.nickname})
    db.commit()
    db.refresh(row)
    return _public(row)


@router.patch("/{agent_id}")
def update_agent(agent_id: int, payload: BusinessAgentUpdate, db: DbSession, admin: AdminDep) -> dict:
    row = db.get(BusinessAgent, agent_id)
    if not row:
        raise HTTPException(status_code=404, detail="商务代理不存在")
    values = payload.model_dump(exclude_unset=True)
    if "password" in values:
        plain = values.pop("password")
        if plain:
            row.password_hash = hash_password(plain)
    for k, v in values.items():
        setattr(row, k, v)
    safe_detail = {k: v for k, v in values.items() if k != "password"}
    write_audit(db, actor=admin, action="business_agent.update",
                target_type="business_agent", target_id=row.id, detail=safe_detail)
    db.commit()
    db.refresh(row)
    return _public(row)


@router.delete("/{agent_id}")
def delete_agent(agent_id: int, db: DbSession, admin: AdminDep) -> dict:
    row = db.get(BusinessAgent, agent_id)
    if not row:
        raise HTTPException(status_code=404, detail="商务代理不存在")
    db.delete(row)
    write_audit(db, actor=admin, action="business_agent.delete",
                target_type="business_agent", target_id=agent_id)
    db.commit()
    return {"deleted": True}
