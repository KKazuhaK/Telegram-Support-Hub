from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.app.api.deps import DbSession
from backend.app.models.campaign import Campaign
from backend.app.models.customer import Customer
from backend.app.models.message import MessageRecord
from backend.app.models.template import MessageTemplate
from backend.app.services.serializers import list_dict, to_dict
from backend.app.services.template_renderer import render_template

router = APIRouter()


class SendSettings(BaseModel):
    success_interval_seconds: int = Field(default=60, ge=1)
    failure_interval_seconds: int = Field(default=120, ge=1)
    random_min_seconds: int = Field(default=0, ge=0)
    random_max_seconds: int = Field(default=30, ge=0)
    per_account_concurrency: int = Field(default=1, ge=1)
    task_concurrency: int = Field(default=5, ge=1)
    max_per_account: int | None = None
    max_per_day: int | None = None


class CampaignCreate(BaseModel):
    name: str
    template_id: int
    target_type: str = "customer_broadcast"
    account_group_ids: list[int] = Field(default_factory=list)
    send_settings: SendSettings = Field(default_factory=SendSettings)
    created_by: str | None = None


@router.get("")
def list_campaigns(db: DbSession, limit: int = 100, offset: int = 0) -> list[dict]:
    rows = list(db.scalars(select(Campaign).order_by(Campaign.id.desc()).offset(offset).limit(limit)))
    return list_dict(rows)


@router.post("")
def create_campaign(payload: CampaignCreate, db: DbSession) -> dict:
    template = db.get(MessageTemplate, payload.template_id)
    if not template or not template.enabled:
        raise HTTPException(status_code=400, detail="template not found or disabled")

    customers = list(
        db.scalars(
            select(Customer).where(
                Customer.consent.is_(True),
                Customer.status.in_(["new", "assigned", "failed"]),
            )
        )
    )
    if not customers:
        raise HTTPException(status_code=400, detail="no eligible consented customers")

    campaign = Campaign(
        name=payload.name,
        template_id=template.id,
        status="queued",
        target_type=payload.target_type,
        account_group_ids=payload.account_group_ids,
        send_settings=payload.send_settings.model_dump(),
        target_count=len(customers),
        queued_count=len(customers),
        created_by=payload.created_by,
    )
    db.add(campaign)
    db.flush()

    now = datetime.now(UTC).isoformat()
    for customer in customers:
        db.add(
            MessageRecord(
                campaign_id=campaign.id,
                account_id=customer.assigned_account_id,
                customer_id=customer.id,
                phone=customer.phone,
                body_snapshot=render_template(template.body, customer),
                status="queued",
                next_run_at=now,
            )
        )
        customer.status = "queued"

    db.commit()
    db.refresh(campaign)
    return to_dict(campaign)


@router.post("/{campaign_id}/start")
def start_campaign(campaign_id: int, db: DbSession) -> dict:
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")
    campaign.status = "running"
    campaign.started_at = datetime.now(UTC).isoformat()
    db.commit()
    db.refresh(campaign)
    return to_dict(campaign)


@router.post("/{campaign_id}/pause")
def pause_campaign(campaign_id: int, db: DbSession) -> dict:
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")
    campaign.status = "paused"
    campaign.paused_at = datetime.now(UTC).isoformat()
    db.commit()
    db.refresh(campaign)
    return to_dict(campaign)


@router.post("/{campaign_id}/resume")
def resume_campaign(campaign_id: int, db: DbSession) -> dict:
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")
    campaign.status = "running"
    db.commit()
    db.refresh(campaign)
    return to_dict(campaign)


@router.post("/{campaign_id}/cancel")
def cancel_campaign(campaign_id: int, db: DbSession) -> dict:
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")
    campaign.status = "cancelled"
    db.commit()
    db.refresh(campaign)
    return to_dict(campaign)


@router.get("/{campaign_id}/messages")
def list_campaign_messages(campaign_id: int, db: DbSession, limit: int = 100, offset: int = 0) -> list[dict]:
    rows = list(
        db.scalars(
            select(MessageRecord)
            .where(MessageRecord.campaign_id == campaign_id)
            .order_by(MessageRecord.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return list_dict(rows)
