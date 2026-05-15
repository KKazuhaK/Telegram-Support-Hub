from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from backend.app.api.deps import AdminDep, CurrentUserDep, DbSession, FlexibleUserDep
from backend.app.core.config import settings
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


@router.get("/{material_id}/download")
def download_material(material_id: int, db: DbSession, _: FlexibleUserDep) -> FileResponse:
    row = db.get(Material, material_id)
    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")
    if not row.file_path:
        raise HTTPException(status_code=404, detail="该资料没有可下载的文件（文本类）")
    path = Path(row.file_path).resolve()
    # Guard against rows whose stored path escapes UPLOAD_DIR (would only
    # happen if someone hand-edited the DB).
    if settings.upload_dir.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail="非法文件路径")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件已丢失")
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=row.content or path.name,
    )


@router.delete("/{material_id}")
def delete_material(material_id: int, db: DbSession, _: AdminDep) -> dict:
    row = db.get(Material, material_id)
    if not row:
        raise HTTPException(status_code=404, detail="文本不存在")
    # Remove the backing file too if this is an uploaded asset. We swallow
    # FS errors so a stale row never blocks the SQL delete.
    if row.file_path:
        try:
            path = Path(row.file_path)
            if path.is_file():
                path.unlink()
        except OSError:
            pass
    db.delete(row)
    db.commit()
    return {"deleted": True}
