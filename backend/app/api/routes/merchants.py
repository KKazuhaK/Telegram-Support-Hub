from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.app.api.deps import AdminDep, CurrentUserDep, DbSession
from backend.app.core.security import hash_password
from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission
from backend.app.models.tenant import BusinessAgent, Merchant
from backend.app.services.audit import write_audit
from backend.app.services.serializers import to_dict

router = APIRouter()


class MerchantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    nickname: str | None = None
    password: str = Field(min_length=6, max_length=200)
    business_agent_id: int | None = None
    status: bool = True
    statistic_time: str | None = "09:00"
    remark: str | None = None
    ports_total: int = 0
    ports_expires_at: str | None = None
    ports_reset_cycle_hours: int = 24


class MerchantUpdate(BaseModel):
    nickname: str | None = None
    password: str | None = Field(default=None, min_length=6, max_length=200)
    business_agent_id: int | None = None
    status: bool | None = None
    statistic_time: str | None = None
    remark: str | None = None
    ports_total: int | None = None
    ports_expires_at: str | None = None
    ports_reset_cycle_hours: int | None = None


class MerchantBatch(BaseModel):
    ids: list[int] = Field(min_length=1)
    status: bool | None = None


class MerchantBatchPermissions(BaseModel):
    """Bulk-grant a permission profile to a cartesian product of agents
    and account-groups, scoped under merchants for audit/grouping purposes
    (the actual permission table is the same global one)."""
    merchant_ids: list[int] = Field(default_factory=list)
    agent_ids: list[int] = Field(min_length=1)
    account_group_ids: list[int] = Field(min_length=1)
    permissions: dict


def _public(row: Merchant) -> dict:
    data = to_dict(row)
    data.pop("password_hash", None)
    return data


@router.get("")
def list_merchants(
    db: DbSession,
    _: CurrentUserDep,
    business_agent_id: int | None = None,
    q: str | None = None,
    status: bool | None = None,
    online_status: str | None = None,
) -> list[dict]:
    stmt = select(Merchant).order_by(Merchant.id.desc())
    if business_agent_id is not None:
        stmt = stmt.where(Merchant.business_agent_id == business_agent_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Merchant.name.like(like)) | (Merchant.nickname.like(like)))
    if status is not None:
        stmt = stmt.where(Merchant.status.is_(status))
    if online_status:
        stmt = stmt.where(Merchant.online_status == online_status)
    rows = list(db.scalars(stmt))
    return [_public(r) for r in rows]


@router.post("")
def create_merchant(payload: MerchantCreate, db: DbSession, admin: AdminDep) -> dict:
    if db.scalar(select(Merchant).where(Merchant.name == payload.name)):
        raise HTTPException(status_code=409, detail="该商户名称已被占用")
    if payload.business_agent_id is not None:
        if not db.get(BusinessAgent, payload.business_agent_id):
            raise HTTPException(status_code=400, detail="所选商务代理不存在")
    data = payload.model_dump(exclude={"password"})
    row = Merchant(**data, password_hash=hash_password(payload.password))
    db.add(row)
    db.flush()
    write_audit(db, actor=admin, action="merchant.create",
                target_type="merchant", target_id=row.id,
                detail={"name": payload.name, "business_agent_id": payload.business_agent_id,
                        "ports_total": payload.ports_total})
    db.commit()
    db.refresh(row)
    return _public(row)


@router.patch("/{merchant_id}")
def update_merchant(merchant_id: int, payload: MerchantUpdate, db: DbSession, admin: AdminDep) -> dict:
    row = db.get(Merchant, merchant_id)
    if not row:
        raise HTTPException(status_code=404, detail="商户不存在")
    values = payload.model_dump(exclude_unset=True)
    if "password" in values:
        plain = values.pop("password")
        if plain:
            row.password_hash = hash_password(plain)
    if "business_agent_id" in values and values["business_agent_id"] is not None:
        if not db.get(BusinessAgent, values["business_agent_id"]):
            raise HTTPException(status_code=400, detail="所选商务代理不存在")
    for k, v in values.items():
        setattr(row, k, v)
    write_audit(db, actor=admin, action="merchant.update",
                target_type="merchant", target_id=row.id,
                detail={k: v for k, v in values.items() if k != "password"})
    db.commit()
    db.refresh(row)
    return _public(row)


@router.delete("/{merchant_id}")
def delete_merchant(merchant_id: int, db: DbSession, admin: AdminDep) -> dict:
    row = db.get(Merchant, merchant_id)
    if not row:
        raise HTTPException(status_code=404, detail="商户不存在")
    db.delete(row)
    write_audit(db, actor=admin, action="merchant.delete",
                target_type="merchant", target_id=merchant_id)
    db.commit()
    return {"deleted": True}


@router.post("/batch-permissions")
def batch_permissions(payload: MerchantBatchPermissions, db: DbSession, admin: AdminDep) -> dict:
    """For each (agent_id × account_group_id) pair, upsert the permission
    row with the supplied flag values. PRD section 7.1's
    『批量修改客服权限』 button drives this."""
    allowed = {
        "can_view_friends", "can_view_chats", "can_send_message",
        "can_broadcast", "can_edit_profile", "can_delete_friend",
        "can_clear_chat", "can_export_data",
    }
    perms = {k: bool(v) for k, v in payload.permissions.items() if k in allowed}
    if not perms:
        raise HTTPException(status_code=400, detail="permissions 至少需要一个有效字段")

    created = 0
    updated = 0
    for agent_id in payload.agent_ids:
        for group_id in payload.account_group_ids:
            existing = db.scalar(select(SupportAgentGroupPermission).where(
                SupportAgentGroupPermission.agent_id == agent_id,
                SupportAgentGroupPermission.account_group_id == group_id,
            ))
            if existing:
                for k, v in perms.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(SupportAgentGroupPermission(
                    agent_id=agent_id, account_group_id=group_id, **perms,
                ))
                created += 1

    write_audit(db, actor=admin, action="merchant.batch_permissions",
                detail={
                    "merchants": payload.merchant_ids,
                    "agents": payload.agent_ids,
                    "groups": payload.account_group_ids,
                    "permissions": perms,
                    "created": created, "updated": updated,
                })
    db.commit()
    return {"created": created, "updated": updated}


@router.post("/batch")
def batch_update(payload: MerchantBatch, db: DbSession, admin: AdminDep) -> dict:
    rows = list(db.scalars(select(Merchant).where(Merchant.id.in_(payload.ids))))
    for r in rows:
        if payload.status is not None:
            r.status = payload.status
    write_audit(db, actor=admin, action="merchant.batch_update",
                detail={"ids": payload.ids, "status": payload.status})
    db.commit()
    return {"updated": len(rows)}
