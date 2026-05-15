from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.app.api.deps import AdminDep, DbSession
from backend.app.core.config import settings
from backend.app.services.audit import write_audit

router = APIRouter()

# Conservative whitelist: letters, digits, underscore, hyphen, dot. Anything
# else (including separators, traversal sequences, and non-ASCII) is collapsed
# into `_`. We also strip leading dots to keep "..xxx" from leaking up.
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitise(name: str) -> str:
    raw = name.replace("\\", "/").split("/")[-1].strip()
    cleaned = _SAFE_NAME.sub("_", raw).lstrip(".") or "file"
    return cleaned[:200]


def _file_meta(path: Path) -> dict:
    stat = path.stat()
    return {
        "name": path.name,
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
    }


@router.get("")
def list_files(_: AdminDep) -> list[dict]:
    settings.ensure_directories()
    return [
        _file_meta(p)
        for p in sorted(settings.upload_dir.iterdir(), key=lambda x: x.name)
        if p.is_file()
    ]


@router.post("")
async def upload_file(
    db: DbSession,
    admin: AdminDep,
    file: UploadFile = File(...),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    settings.ensure_directories()
    safe = _sanitise(file.filename)
    target = settings.upload_dir / safe
    # Prevent overwrite-by-collision: append a numeric suffix if the name
    # already exists.
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        for i in range(1, 1000):
            candidate = settings.upload_dir / f"{stem}-{i}{suffix}"
            if not candidate.exists():
                target = candidate
                safe = target.name
                break

    content = await file.read()
    target.write_bytes(content)
    write_audit(
        db, actor=admin, action="file.upload",
        detail={"name": safe, "size": len(content)},
    )
    db.commit()
    return _file_meta(target)


@router.delete("/{name}")
def delete_file(name: str, db: DbSession, admin: AdminDep) -> dict:
    # Reject any traversal attempt before touching the filesystem.
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="非法文件名")
    settings.ensure_directories()
    target = settings.upload_dir / name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    # Belt-and-suspenders: ensure resolved path is still inside upload_dir
    if settings.upload_dir.resolve() not in target.resolve().parents:
        raise HTTPException(status_code=400, detail="非法文件路径")
    target.unlink()
    write_audit(db, actor=admin, action="file.delete", detail={"name": name})
    db.commit()
    return {"deleted": name}
