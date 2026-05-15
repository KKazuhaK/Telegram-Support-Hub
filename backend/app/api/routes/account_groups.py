from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.api.deps import AdminDep, CurrentUserDep, DbSession
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.services.audit import write_audit
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


class AccountGroupCreate(BaseModel):
    name: str
    code: str | None = None
    daily_limit: int = 1000
    remark: str | None = None


class AccountGroupUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    daily_limit: int | None = None
    remark: str | None = None


class AccountGroupMemberCreate(BaseModel):
    account_id: int
    is_primary: bool = True


@router.get("")
def list_groups(db: DbSession, user: CurrentUserDep) -> list[dict]:
    stmt = select(AccountGroup).order_by(AccountGroup.id.desc())
    if not user.is_admin:
        stmt = stmt.where(AccountGroup.id.in_(user.visible_group_ids() or [-1]))
    return list_dict(list(db.scalars(stmt)))


@router.post("")
def create_group(payload: AccountGroupCreate, db: DbSession, admin: AdminDep) -> dict:
    group = AccountGroup(name=payload.name, code=payload.code, daily_limit=payload.daily_limit, remark=payload.remark)
    db.add(group)
    db.flush()
    write_audit(db, actor=admin, action="account_group.create",
                target_type="account_group", target_id=group.id,
                detail={"name": group.name, "code": group.code})
    db.commit()
    db.refresh(group)
    return to_dict(group)


@router.patch("/{group_id}")
def update_group(group_id: int, payload: AccountGroupUpdate, db: DbSession, admin: AdminDep) -> dict:
    group = db.get(AccountGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="account group not found")
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(group, key, value)
    write_audit(db, actor=admin, action="account_group.update",
                target_type="account_group", target_id=group.id, detail=values)
    db.commit()
    db.refresh(group)
    return to_dict(group)


@router.post("/{group_id}/members")
def add_group_member(group_id: int, payload: AccountGroupMemberCreate, db: DbSession, admin: AdminDep) -> dict:
    if not db.get(AccountGroup, group_id):
        raise HTTPException(status_code=404, detail="account group not found")
    if not db.get(Account, payload.account_id):
        raise HTTPException(status_code=404, detail="account not found")

    existing = db.scalar(
        select(AccountGroupMember).where(
            AccountGroupMember.group_id == group_id,
            AccountGroupMember.account_id == payload.account_id,
        )
    )
    if existing:
        return to_dict(existing)

    member = AccountGroupMember(account_id=payload.account_id, group_id=group_id, is_primary=payload.is_primary)
    db.add(member)
    write_audit(db, actor=admin, action="account_group.add_member",
                target_type="account_group", target_id=group_id,
                detail={"account_id": payload.account_id, "is_primary": payload.is_primary})
    db.commit()
    db.refresh(member)
    return to_dict(member)


@router.delete("/{group_id}/members/{account_id}")
def remove_group_member(group_id: int, account_id: int, db: DbSession, admin: AdminDep) -> dict:
    member = db.scalar(
        select(AccountGroupMember).where(
            AccountGroupMember.group_id == group_id,
            AccountGroupMember.account_id == account_id,
        )
    )
    if not member:
        raise HTTPException(status_code=404, detail="member not found")
    db.delete(member)
    write_audit(db, actor=admin, action="account_group.remove_member",
                target_type="account_group", target_id=group_id,
                detail={"account_id": account_id})
    db.commit()
    return {"deleted": True}
