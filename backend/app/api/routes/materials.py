from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, func, select

from backend.app.api.deps import AdminDep, CurrentUserDep, DbSession
from backend.app.models.data_groups import Material, MaterialGroup
from backend.app.services.audit import write_audit
from backend.app.services.serializers import to_dict

router = APIRouter()

MATERIAL_KINDS = {"text", "image", "voice"}


class MaterialGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = "text"
    remark: str | None = None


class MaterialGroupUpdate(BaseModel):
    name: str | None = None
    remark: str | None = None


class MaterialsAdd(BaseModel):
    items: list[str] = Field(min_length=1)


@router.get("")
def list_groups(db: DbSession, _: CurrentUserDep, kind: str | None = None) -> list[dict]:
    stmt = select(MaterialGroup).order_by(MaterialGroup.id.desc())
    if kind:
        stmt = stmt.where(MaterialGroup.kind == kind)
    rows = list(db.scalars(stmt))
    counts = dict(db.execute(
        select(Material.group_id, func.count(Material.id)).group_by(Material.group_id)
    ).all())
    out = []
    for g in rows:
        data = to_dict(g)
        data["count"] = int(counts.get(g.id, 0))
        out.append(data)
    return out


@router.post("")
def create_group(payload: MaterialGroupCreate, db: DbSession, admin: AdminDep) -> dict:
    if payload.kind not in MATERIAL_KINDS:
        raise HTTPException(status_code=400, detail=f"类型必须是 {sorted(MATERIAL_KINDS)} 之一")
    if db.scalar(select(MaterialGroup).where(MaterialGroup.name == payload.name)):
        raise HTTPException(status_code=409, detail="同名分组已存在")
    g = MaterialGroup(**payload.model_dump())
    db.add(g)
    db.flush()
    write_audit(db, actor=admin, action="material_group.create",
                target_type="material_group", target_id=g.id, detail=payload.model_dump())
    db.commit()
    db.refresh(g)
    return to_dict(g)


@router.patch("/{group_id}")
def update_group(group_id: int, payload: MaterialGroupUpdate, db: DbSession, admin: AdminDep) -> dict:
    g = db.get(MaterialGroup, group_id)
    if not g:
        raise HTTPException(status_code=404, detail="文本分组不存在")
    values = payload.model_dump(exclude_unset=True)
    for k, v in values.items():
        setattr(g, k, v)
    write_audit(db, actor=admin, action="material_group.update",
                target_type="material_group", target_id=g.id, detail=values)
    db.commit()
    db.refresh(g)
    return to_dict(g)


@router.delete("/{group_id}")
def delete_group(group_id: int, db: DbSession, admin: AdminDep) -> dict:
    g = db.get(MaterialGroup, group_id)
    if not g:
        raise HTTPException(status_code=404, detail="文本分组不存在")
    db.execute(sa_delete(Material).where(Material.group_id == group_id))
    db.delete(g)
    write_audit(db, actor=admin, action="material_group.delete",
                target_type="material_group", target_id=group_id)
    db.commit()
    return {"deleted": True}


@router.post("/{group_id}/materials")
def add_materials(group_id: int, payload: MaterialsAdd, db: DbSession, admin: AdminDep) -> dict:
    g = db.get(MaterialGroup, group_id)
    if not g:
        raise HTTPException(status_code=404, detail="文本分组不存在")
    created = 0
    for content in payload.items:
        text = (content or "").strip()
        if not text:
            continue
        db.add(Material(group_id=group_id, content=text))
        created += 1
    write_audit(db, actor=admin, action="material.batch_add",
                target_type="material_group", target_id=group_id,
                detail={"created": created})
    db.commit()
    return {"created": created}
