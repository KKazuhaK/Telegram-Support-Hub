from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import or_, select

from backend.app.api.deps import AdminDep, DbSession
from backend.app.models.audit import AuditLog
from backend.app.services.serializers import list_dict

router = APIRouter()


@router.get("")
def list_audit_logs(
    db: DbSession,
    _: AdminDep,
    action: str | None = None,
    action_prefix: str | None = None,
    target_type: str | None = None,
    actor_username: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """List audit log entries.

    `action` is an exact match. `action_prefix` is a LIKE-prefix filter
    that also accepts pipe-separated alternatives so callers can ask for
    e.g. all import + export actions in one shot:
        action_prefix=customer.import|export.
    """
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if action_prefix:
        prefixes = [p.strip() for p in action_prefix.split("|") if p.strip()]
        if prefixes:
            stmt = stmt.where(or_(*[AuditLog.action.like(f"{p}%") for p in prefixes]))
    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if actor_username:
        stmt = stmt.where(AuditLog.actor_username == actor_username)
    rows = list(db.scalars(stmt.offset(offset).limit(limit)))
    return list_dict(rows)
