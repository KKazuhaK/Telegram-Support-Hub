from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.api.deps import CurrentUserDep, DbSession
from backend.app.models.campaign import Campaign
from backend.app.services.audit import write_audit
from backend.app.services.export import customers_csv_rows, messages_csv_rows, to_csv_stream
from backend.app.services.permissions import permission_denied_detail

router = APIRouter()


def _require_export(user) -> None:
    if not (user.is_admin or user.can("can_export_data")):
        raise HTTPException(status_code=403, detail=permission_denied_detail("can_export_data"))


@router.get("/customers.csv")
def export_customers(db: DbSession, user: CurrentUserDep, status: str | None = None):
    _require_export(user)
    write_audit(db, actor=user, action="export.customers", detail={"status": status})
    db.commit()
    rows = customers_csv_rows(db, status=status)
    return StreamingResponse(
        to_csv_stream(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=customers.csv"},
    )


@router.get("/campaigns/{campaign_id}/messages.csv")
def export_campaign_messages(campaign_id: int, db: DbSession, user: CurrentUserDep):
    _require_export(user)
    if not db.get(Campaign, campaign_id):
        raise HTTPException(status_code=404, detail="群发任务不存在")
    write_audit(db, actor=user, action="export.campaign_messages",
                target_type="campaign", target_id=campaign_id)
    db.commit()
    rows = messages_csv_rows(db, campaign_id=campaign_id)
    return StreamingResponse(
        to_csv_stream(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=campaign-{campaign_id}-messages.csv"},
    )
