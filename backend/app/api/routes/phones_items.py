from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from backend.app.api.deps import AdminDep, CurrentUserDep, DbSession
from backend.app.models.data_groups import Phone
from backend.app.services.serializers import list_dict

router = APIRouter()


@router.get("")
def list_phones(
    db: DbSession, _: CurrentUserDep,
    group_id: int | None = None, used: bool | None = None,
    limit: int = 200, offset: int = 0,
) -> list[dict]:
    stmt = select(Phone).order_by(Phone.id.desc())
    if group_id is not None:
        stmt = stmt.where(Phone.group_id == group_id)
    if used is not None:
        stmt = stmt.where(Phone.used.is_(used))
    return list_dict(list(db.scalars(stmt.offset(offset).limit(limit))))


@router.delete("/{phone_id}")
def delete_phone(phone_id: int, db: DbSession, _: AdminDep) -> dict:
    row = db.get(Phone, phone_id)
    if not row:
        raise HTTPException(status_code=404, detail="号码不存在")
    db.delete(row)
    db.commit()
    return {"deleted": True}
