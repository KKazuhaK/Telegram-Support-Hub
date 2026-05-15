from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.audit import AuditLog
from backend.app.services.permissions import CurrentUser


def write_audit(
    db: Session,
    *,
    actor: CurrentUser | None,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
    note: str | None = None,
) -> AuditLog:
    log = AuditLog(
        actor_id=actor.agent_id if actor else None,
        actor_username=actor.username if actor else None,
        actor_role=actor.role if actor else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=detail,
        ip=ip,
        note=note,
    )
    db.add(log)
    return log
