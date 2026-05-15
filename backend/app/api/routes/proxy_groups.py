from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update as sa_update

from backend.app.api.deps import AdminDep, CurrentUserDep, DbSession
from backend.app.models.data_groups import ProxyGroup
from backend.app.models.proxy import ProxyEndpoint
from backend.app.services.audit import write_audit
from backend.app.services.serializers import to_dict

router = APIRouter()


class ProxyGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    remark: str | None = None


class ProxyGroupUpdate(BaseModel):
    name: str | None = None
    remark: str | None = None


@router.get("")
def list_groups(db: DbSession, _: CurrentUserDep) -> list[dict]:
    rows = list(db.scalars(select(ProxyGroup).order_by(ProxyGroup.id.desc())))
    counts = dict(db.execute(
        select(ProxyEndpoint.group_id, func.count(ProxyEndpoint.id))
        .where(ProxyEndpoint.group_id.isnot(None))
        .group_by(ProxyEndpoint.group_id)
    ).all())
    out = []
    for g in rows:
        data = to_dict(g)
        data["count"] = int(counts.get(g.id, 0))
        out.append(data)
    return out


@router.post("")
def create_group(payload: ProxyGroupCreate, db: DbSession, admin: AdminDep) -> dict:
    if db.scalar(select(ProxyGroup).where(ProxyGroup.name == payload.name)):
        raise HTTPException(status_code=409, detail="同名分组已存在")
    g = ProxyGroup(**payload.model_dump())
    db.add(g)
    db.flush()
    write_audit(db, actor=admin, action="proxy_group.create",
                target_type="proxy_group", target_id=g.id, detail=payload.model_dump())
    db.commit()
    db.refresh(g)
    return to_dict(g)


@router.patch("/{group_id}")
def update_group(group_id: int, payload: ProxyGroupUpdate, db: DbSession, admin: AdminDep) -> dict:
    g = db.get(ProxyGroup, group_id)
    if not g:
        raise HTTPException(status_code=404, detail="代理分组不存在")
    values = payload.model_dump(exclude_unset=True)
    for k, v in values.items():
        setattr(g, k, v)
    write_audit(db, actor=admin, action="proxy_group.update",
                target_type="proxy_group", target_id=g.id, detail=values)
    db.commit()
    db.refresh(g)
    return to_dict(g)


@router.delete("/{group_id}")
def delete_group(group_id: int, db: DbSession, admin: AdminDep) -> dict:
    g = db.get(ProxyGroup, group_id)
    if not g:
        raise HTTPException(status_code=404, detail="代理分组不存在")
    # Detach proxies from this group, but keep the proxy rows so existing
    # account bindings stay intact.
    db.execute(sa_update(ProxyEndpoint).where(ProxyEndpoint.group_id == group_id).values(group_id=None))
    db.delete(g)
    write_audit(db, actor=admin, action="proxy_group.delete",
                target_type="proxy_group", target_id=group_id)
    db.commit()
    return {"deleted": True}
