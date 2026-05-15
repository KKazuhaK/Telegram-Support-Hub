from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.api.deps import DbSession
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
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
def list_groups(db: DbSession) -> list[dict]:
    return list_dict(list(db.scalars(select(AccountGroup).order_by(AccountGroup.id.desc()))))


@router.post("")
def create_group(payload: AccountGroupCreate, db: DbSession) -> dict:
    group = AccountGroup(name=payload.name, code=payload.code, daily_limit=payload.daily_limit, remark=payload.remark)
    db.add(group)
    db.commit()
    db.refresh(group)
    return to_dict(group)


@router.patch("/{group_id}")
def update_group(group_id: int, payload: AccountGroupUpdate, db: DbSession) -> dict:
    group = db.get(AccountGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="account group not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    db.commit()
    db.refresh(group)
    return to_dict(group)


@router.post("/{group_id}/members")
def add_group_member(group_id: int, payload: AccountGroupMemberCreate, db: DbSession) -> dict:
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
    db.commit()
    db.refresh(member)
    return to_dict(member)
