from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from backend.app.api.deps import AdminDep, CurrentUserDep, DbSession
from backend.app.models.data_groups import Material
from backend.app.services.serializers import list_dict

router = APIRouter()


@router.get("")
def list_materials(
    db: DbSession, _: CurrentUserDep,
    group_id: int | None = None, q: str | None = None,
    limit: int = 200, offset: int = 0,
) -> list[dict]:
    stmt = select(Material).order_by(Material.id.desc())
    if group_id is not None:
        stmt = stmt.where(Material.group_id == group_id)
    if q:
        stmt = stmt.where(Material.content.like(f"%{q}%"))
    return list_dict(list(db.scalars(stmt.offset(offset).limit(limit))))


@router.delete("/{material_id}")
def delete_material(material_id: int, db: DbSession, _: AdminDep) -> dict:
    row = db.get(Material, material_id)
    if not row:
        raise HTTPException(status_code=404, detail="文本不存在")
    db.delete(row)
    db.commit()
    return {"deleted": True}
