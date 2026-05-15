from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.app.api.deps import CurrentUserDep, DbSession
from backend.app.models.account import AccountGroupMember
from backend.app.models.campaign import Campaign
from backend.app.models.customer import Customer, Friend
from backend.app.models.message import MessageRecord
from backend.app.models.template import MessageTemplate
from backend.app.services.audit import write_audit
from backend.app.services.imported_target import build_imported_target_records
from backend.app.services.serializers import list_dict, to_dict
from backend.app.services.template_renderer import render_template

router = APIRouter()

ALLOWED_TARGET_TYPES = {"customer_broadcast", "friend_broadcast", "imported_target_broadcast"}


class SendSettings(BaseModel):
    success_interval_seconds: int = Field(default=60, ge=1)
    failure_interval_seconds: int = Field(default=120, ge=1)
    random_min_seconds: int = Field(default=0, ge=0)
    random_max_seconds: int = Field(default=30, ge=0)
    per_account_concurrency: int = Field(default=1, ge=1)
    task_concurrency: int = Field(default=5, ge=1)
    max_per_account: int | None = None
    max_per_day: int | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None


class CampaignCreate(BaseModel):
    name: str
    template_id: int
    target_type: str = "customer_broadcast"
    account_group_ids: list[int] = Field(default_factory=list)
    customer_ids: list[int] | None = None
    friend_ids: list[int] | None = None
    imported_targets: list[dict] | None = None
    send_settings: SendSettings = Field(default_factory=SendSettings)


def _require_broadcast(user) -> None:
    if not (user.is_admin or user.can("can_broadcast")):
        raise HTTPException(status_code=403, detail="missing can_broadcast")


def _scope_groups(user, requested: list[int]) -> list[int]:
    if user.is_admin:
        return requested
    visible = set(user.visible_group_ids())
    if not requested:
        return list(visible)
    invalid = [g for g in requested if g not in visible]
    if invalid:
        raise HTTPException(status_code=403, detail=f"groups outside permission: {invalid}")
    return requested


def _build_customer_records(db, campaign: Campaign, template: MessageTemplate, customer_ids: list[int] | None, now_iso: str) -> int:
    stmt = select(Customer).where(Customer.consent.is_(True), Customer.status.in_(["new", "assigned", "failed", "queued"]))
    if customer_ids:
        stmt = stmt.where(Customer.id.in_(customer_ids))
    customers = list(db.scalars(stmt))
    for customer in customers:
        if not customer.assigned_account_id:
            continue
        db.add(MessageRecord(
            campaign_id=campaign.id,
            account_id=customer.assigned_account_id,
            customer_id=customer.id,
            phone=customer.phone,
            body_snapshot=render_template(template.body, customer),
            status="queued",
            next_run_at=now_iso,
        ))
        customer.status = "queued"
    return len([c for c in customers if c.assigned_account_id])


def _build_friend_records(db, campaign: Campaign, template: MessageTemplate, group_ids: list[int],
                          friend_ids: list[int] | None, now_iso: str) -> int:
    stmt = select(Friend).where(Friend.opted_out.is_(False))
    if friend_ids:
        stmt = stmt.where(Friend.id.in_(friend_ids))
    if group_ids:
        member_subq = select(AccountGroupMember.account_id).where(AccountGroupMember.group_id.in_(group_ids))
        stmt = stmt.where(Friend.account_id.in_(member_subq))
    friends = list(db.scalars(stmt))
    body = template.body
    for friend in friends:
        rendered = (
            body.replace("{name}", friend.nickname or friend.username or "好友")
            .replace("{phone}", friend.phone or "")
            .replace("{source}", "friend")
        )
        db.add(MessageRecord(
            campaign_id=campaign.id,
            account_id=friend.account_id,
            friend_id=friend.id,
            target_tg_user_id=friend.tg_user_id,
            phone=friend.phone,
            body_snapshot=rendered,
            status="queued",
            next_run_at=now_iso,
        ))
        if friend.status == "new":
            friend.status = "contacted"
    return len(friends)


@router.get("")
def list_campaigns(db: DbSession, user: CurrentUserDep, limit: int = 100, offset: int = 0) -> list[dict]:
    stmt = select(Campaign).order_by(Campaign.id.desc()).offset(offset).limit(limit)
    return list_dict(list(db.scalars(stmt)))


@router.post("")
def create_campaign(payload: CampaignCreate, db: DbSession, user: CurrentUserDep) -> dict:
    _require_broadcast(user)
    if payload.target_type not in ALLOWED_TARGET_TYPES:
        raise HTTPException(status_code=400, detail=f"target_type must be one of {sorted(ALLOWED_TARGET_TYPES)}")

    template = db.get(MessageTemplate, payload.template_id)
    if not template or not template.enabled:
        raise HTTPException(status_code=400, detail="template not found or disabled")

    group_ids = _scope_groups(user, payload.account_group_ids)

    campaign = Campaign(
        name=payload.name,
        template_id=template.id,
        status="queued",
        target_type=payload.target_type,
        account_group_ids=group_ids,
        send_settings=payload.send_settings.model_dump(),
        target_count=0,
        queued_count=0,
        created_by=user.username,
    )
    db.add(campaign)
    db.flush()

    now_iso = datetime.now(UTC).isoformat()
    if payload.target_type == "customer_broadcast":
        count = _build_customer_records(db, campaign, template, payload.customer_ids, now_iso)
    elif payload.target_type == "friend_broadcast":
        count = _build_friend_records(db, campaign, template, group_ids, payload.friend_ids, now_iso)
    else:  # imported_target_broadcast
        count = build_imported_target_records(db, campaign, template, group_ids, payload.imported_targets or [])

    if count == 0:
        db.rollback()
        raise HTTPException(status_code=400, detail="no eligible targets for this campaign")

    campaign.target_count = count
    campaign.queued_count = count
    write_audit(db, actor=user, action="campaign.create", target_type="campaign",
                target_id=campaign.id, detail={"target_type": payload.target_type, "queued": count, "groups": group_ids})
    db.commit()
    db.refresh(campaign)
    return to_dict(campaign)


def _get_campaign_with_perm(db: DbSession, user, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")
    if not user.is_admin:
        if not (user.can("can_broadcast") or user.can("can_send_message")):
            raise HTTPException(status_code=403, detail="missing permission")
    return campaign


@router.post("/{campaign_id}/start")
def start_campaign(campaign_id: int, db: DbSession, user: CurrentUserDep) -> dict:
    campaign = _get_campaign_with_perm(db, user, campaign_id)
    campaign.status = "running"
    campaign.started_at = datetime.now(UTC).isoformat()
    write_audit(db, actor=user, action="campaign.start", target_type="campaign", target_id=campaign.id)
    db.commit()
    db.refresh(campaign)
    return to_dict(campaign)


@router.post("/{campaign_id}/pause")
def pause_campaign(campaign_id: int, db: DbSession, user: CurrentUserDep) -> dict:
    campaign = _get_campaign_with_perm(db, user, campaign_id)
    campaign.status = "paused"
    campaign.paused_at = datetime.now(UTC).isoformat()
    write_audit(db, actor=user, action="campaign.pause", target_type="campaign", target_id=campaign.id)
    db.commit()
    db.refresh(campaign)
    return to_dict(campaign)


@router.post("/{campaign_id}/resume")
def resume_campaign(campaign_id: int, db: DbSession, user: CurrentUserDep) -> dict:
    campaign = _get_campaign_with_perm(db, user, campaign_id)
    campaign.status = "running"
    write_audit(db, actor=user, action="campaign.resume", target_type="campaign", target_id=campaign.id)
    db.commit()
    db.refresh(campaign)
    return to_dict(campaign)


@router.post("/{campaign_id}/cancel")
def cancel_campaign(campaign_id: int, db: DbSession, user: CurrentUserDep) -> dict:
    campaign = _get_campaign_with_perm(db, user, campaign_id)
    campaign.status = "cancelled"
    write_audit(db, actor=user, action="campaign.cancel", target_type="campaign", target_id=campaign.id)
    db.commit()
    db.refresh(campaign)
    return to_dict(campaign)


@router.get("/{campaign_id}/messages")
def list_campaign_messages(campaign_id: int, db: DbSession, _: CurrentUserDep, limit: int = 100, offset: int = 0) -> list[dict]:
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
