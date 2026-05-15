from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, func, select

from backend.app.api.deps import AdminDep, CurrentUserDep, DbSession
from backend.app.models.data_groups import Phone, PhoneGroup
from backend.app.services.audit import write_audit
from backend.app.services.parsers import normalize_phone
from backend.app.services.serializers import to_dict

router = APIRouter()


class PhoneGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    country: str | None = None
    remark: str | None = None
    daily_limit: int = 0


class PhoneGroupUpdate(BaseModel):
    name: str | None = None
    country: str | None = None
    remark: str | None = None
    daily_limit: int | None = None


class PhonesAdd(BaseModel):
    numbers: list[str] = Field(min_length=1)


@router.get("")
def list_phone_groups(db: DbSession, _: CurrentUserDep) -> list[dict]:
    rows = list(db.scalars(select(PhoneGroup).order_by(PhoneGroup.id.desc())))
    # Aggregate counts in a single query so the response stays O(1) round-trips.
    counts = dict(db.execute(
        select(Phone.group_id, func.count(Phone.id)).group_by(Phone.group_id)
    ).all())
    remaining = dict(db.execute(
        select(Phone.group_id, func.count(Phone.id)).where(Phone.used.is_(False)).group_by(Phone.group_id)
    ).all())
    out = []
    for g in rows:
        data = to_dict(g)
        data["count"] = int(counts.get(g.id, 0))
        data["remaining"] = int(remaining.get(g.id, 0))
        out.append(data)
    return out


@router.post("")
def create_phone_group(payload: PhoneGroupCreate, db: DbSession, admin: AdminDep) -> dict:
    if db.scalar(select(PhoneGroup).where(PhoneGroup.name == payload.name)):
        raise HTTPException(status_code=409, detail="同名分组已存在")
    g = PhoneGroup(**payload.model_dump())
    db.add(g)
    db.flush()
    write_audit(db, actor=admin, action="phone_group.create",
                target_type="phone_group", target_id=g.id, detail=payload.model_dump())
    db.commit()
    db.refresh(g)
    return to_dict(g)


@router.patch("/{group_id}")
def update_phone_group(group_id: int, payload: PhoneGroupUpdate, db: DbSession, admin: AdminDep) -> dict:
    g = db.get(PhoneGroup, group_id)
    if not g:
        raise HTTPException(status_code=404, detail="号码分组不存在")
    values = payload.model_dump(exclude_unset=True)
    for k, v in values.items():
        setattr(g, k, v)
    write_audit(db, actor=admin, action="phone_group.update",
                target_type="phone_group", target_id=g.id, detail=values)
    db.commit()
    db.refresh(g)
    return to_dict(g)


@router.delete("/{group_id}")
def delete_phone_group(group_id: int, db: DbSession, admin: AdminDep) -> dict:
    g = db.get(PhoneGroup, group_id)
    if not g:
        raise HTTPException(status_code=404, detail="号码分组不存在")
    db.execute(sa_delete(Phone).where(Phone.group_id == group_id))
    db.delete(g)
    write_audit(db, actor=admin, action="phone_group.delete",
                target_type="phone_group", target_id=group_id)
    db.commit()
    return {"deleted": True}


@router.post("/{group_id}/phones")
def add_phones(group_id: int, payload: PhonesAdd, db: DbSession, admin: AdminDep) -> dict:
    g = db.get(PhoneGroup, group_id)
    if not g:
        raise HTTPException(status_code=404, detail="号码分组不存在")
    created = 0
    duplicated: list[str] = []
    rejected: list[str] = []
    for raw in payload.numbers:
        normalised = normalize_phone(raw)
        if not normalised:
            rejected.append(raw)
            continue
        if db.scalar(select(Phone).where(Phone.group_id == group_id, Phone.number == normalised)):
            duplicated.append(normalised)
            continue
        db.add(Phone(group_id=group_id, number=normalised))
        created += 1
    write_audit(db, actor=admin, action="phone.batch_add",
                target_type="phone_group", target_id=group_id,
                detail={"created": created, "duplicated": len(duplicated), "rejected": len(rejected)})
    db.commit()
    return {"created": created, "duplicated": duplicated, "rejected": rejected}
