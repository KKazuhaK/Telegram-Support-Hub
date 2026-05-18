from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.app.api.deps import CurrentUserDep, DbSession
from backend.app.models.account import AccountGroupMember
from backend.app.models.campaign import Campaign
from backend.app.models.customer import Customer, Friend
from backend.app.models.message import MessageRecord
from backend.app.models.template import MessageTemplate
from backend.app.services.audit import write_audit
from backend.app.services.imported_target import build_imported_target_records
from backend.app.services.permissions import permission_denied_detail
from backend.app.services.serializers import list_dict, to_dict
from backend.app.services.template_engine import render_message
from backend.app.services.template_renderer import render_template
from backend.app.services.tenant_scope import (
    apply_merchant_scope, can_access_row, can_write_tenant_data, default_merchant_id,
)

router = APIRouter()

# Operation target whitelists per task_kind. Keeps the schema strict so a
# typo or stale UI field gets a useful 400 instead of being silently saved.
ALLOWED_OPS = {
    "broadcast": {"customer_broadcast", "friend_broadcast", "imported_target_broadcast"},
    "batch_op": {
        "delete_friend", "leave_group", "detect_mutual",
        "leave_other_devices", "appeal_mutual",
    },
    "modify_info": {
        "modify_password", "modify_avatar", "modify_nickname",
        "modify_username", "modify_signature",
    },
}
# Legacy alias.
ALLOWED_TARGET_TYPES = ALLOWED_OPS["broadcast"]

# Per-operation required keys in extra_params. modify_avatar will later need
# file_group_id once file groups land; today the validator only enforces the
# "needs a new value" set.
EXTRA_PARAMS_REQUIRED = {
    "modify_nickname": ("new_value",),
    "modify_username": ("new_value",),
    "modify_signature": ("new_value",),
}


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
    # template_id is optional now: batch_op / modify_info do not need one.
    template_id: int | None = None
    # task_kind defaults to broadcast for backwards-compat with pre-R5 callers.
    task_kind: str = "broadcast"
    # operation_target / target_type are dual-spelled — accept either; we
    # mirror them on save.
    operation_target: str | None = None
    target_type: str = "customer_broadcast"
    account_group_ids: list[int] = Field(default_factory=list)
    customer_ids: list[int] | None = None
    friend_ids: list[int] | None = None
    imported_targets: list[dict] | None = None
    extra_params: dict | None = None
    send_settings: SendSettings = Field(default_factory=SendSettings)
    # Opt-in flag for follow-up / second-touch sends. When True, the
    # customer_broadcast eligibility gate skips the status whitelist so
    # already-sent / read / replied / contacted customers are included
    # again. consent=True is still required regardless — that's the
    # compliance hard line, not a UX one.
    force_resend: bool = False


def _require_broadcast(user) -> None:
    if not can_write_tenant_data(user):
        raise HTTPException(status_code=403, detail=permission_denied_detail("can_broadcast"))


def _scope_groups(user, requested: list[int]) -> list[int]:
    if user.is_admin or user.actor_kind in ("business_agent", "merchant"):
        # Tenant actors are already filtered by merchant_id at query time;
        # don't intersect with support_agent group permissions (which
        # would always be empty for them).
        return requested
    visible = set(user.visible_group_ids())
    if not requested:
        return list(visible)
    invalid = [g for g in requested if g not in visible]
    if invalid:
        raise HTTPException(
            status_code=403,
            detail=f"以下账号分组不在你的权限范围内：{invalid}",
        )
    return requested


def _build_customer_records(db, campaign: Campaign, template: MessageTemplate,
                            customer_ids: list[int] | None, now_iso: str,
                            force_resend: bool = False) -> int:
    # Two-pass with diagnostics so a 0-result tells the operator WHICH
    # condition failed (consent / status / unassigned), not just "0
    # targets". Stored on Campaign.extra_params for the UI to surface.
    base = select(Customer)
    if customer_ids:
        base = base.where(Customer.id.in_(customer_ids))
    all_pool = list(db.scalars(base))

    ok_status = ("new", "assigned", "failed", "queued")

    def _status_ok(c: Customer) -> bool:
        return force_resend or c.status in ok_status

    no_consent = [c for c in all_pool if not c.consent]
    wrong_status = [c for c in all_pool
                    if c.consent and not _status_ok(c)]
    unassigned = [c for c in all_pool
                  if c.consent and _status_ok(c) and not c.assigned_account_id]
    eligible = [c for c in all_pool
                if c.consent and _status_ok(c) and c.assigned_account_id]

    for customer in eligible:
        rendered = render_message(template.body, {
            "name": customer.name, "phone": customer.phone, "source": customer.source,
        })
        db.add(MessageRecord(
            campaign_id=campaign.id,
            account_id=customer.assigned_account_id,
            customer_id=customer.id,
            phone=customer.phone,
            body_snapshot=rendered.text,
            entities=rendered.entities or None,
            status="queued",
            next_run_at=now_iso,
        ))
        customer.status = "queued"

    if not eligible:
        # Surface diagnostics to the caller so the 400 detail can be
        # specific. Stashed via a custom attribute the route reads.
        campaign._eligibility_diag = {  # type: ignore[attr-defined]
            "total": len(all_pool),
            "no_consent": len(no_consent),
            "wrong_status": len(wrong_status),
            "unassigned": len(unassigned),
        }
    return len(eligible)


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
        rendered = render_message(body, {
            "name": friend.nickname or friend.username or "好友",
            "phone": friend.phone or "",
            "source": "friend",
        })
        db.add(MessageRecord(
            campaign_id=campaign.id,
            account_id=friend.account_id,
            friend_id=friend.id,
            target_tg_user_id=friend.tg_user_id,
            phone=friend.phone,
            body_snapshot=rendered.text,
            entities=rendered.entities or None,
            status="queued",
            next_run_at=now_iso,
        ))
        if friend.status == "new":
            friend.status = "contacted"
    return len(friends)


@router.get("")
def list_campaigns(
    db: DbSession, user: CurrentUserDep,
    task_kind: str | None = None,
    limit: int = 100, offset: int = 0,
) -> list[dict]:
    stmt = select(Campaign).order_by(Campaign.id.desc())
    stmt = apply_merchant_scope(stmt, user, db, Campaign)
    if task_kind:
        stmt = stmt.where(Campaign.task_kind == task_kind)
    return list_dict(list(db.scalars(stmt.offset(offset).limit(limit))))


def _resolve_operation_target(payload: CampaignCreate) -> str:
    """Both new (operation_target) and legacy (target_type) shapes are
    accepted. Returns the canonical op string after consistency check."""
    op = payload.operation_target or payload.target_type
    if payload.task_kind not in ALLOWED_OPS:
        raise HTTPException(
            status_code=400,
            detail=f"task_kind 必须是 {sorted(ALLOWED_OPS)} 之一",
        )
    allowed = ALLOWED_OPS[payload.task_kind]
    if op not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"{payload.task_kind} 的 operation_target 必须是 {sorted(allowed)} 之一",
        )
    return op


def _validate_extra_params(op: str, extra: dict | None) -> None:
    required = EXTRA_PARAMS_REQUIRED.get(op)
    if not required:
        return
    extra = extra or {}
    missing = [k for k in required if not extra.get(k)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"{op} 缺少必填参数：{missing}",
        )


def _eligible_account_count(db: DbSession, group_ids: list[int]) -> int:
    """How many enabled+active accounts live in the chosen groups —
    used as `target_count` for batch_op / modify_info kinds where we don't
    queue per-customer message rows."""
    from backend.app.models.account import Account, AccountGroupMember
    if not group_ids:
        return 0
    member_subq = select(AccountGroupMember.account_id).where(AccountGroupMember.group_id.in_(group_ids))
    stmt = (
        select(Account)
        .where(Account.enabled.is_(True))
        .where(Account.status.in_(["active", "imported"]))
        .where(Account.id.in_(member_subq))
    )
    return len(list(db.scalars(stmt)))


@router.post("")
def create_campaign(payload: CampaignCreate, db: DbSession, user: CurrentUserDep) -> dict:
    _require_broadcast(user)
    op = _resolve_operation_target(payload)
    _validate_extra_params(op, payload.extra_params)
    group_ids = _scope_groups(user, payload.account_group_ids)

    template: MessageTemplate | None = None
    if payload.task_kind == "broadcast":
        if payload.template_id is None:
            raise HTTPException(status_code=400, detail="群发任务必须选择模板")
        template = db.get(MessageTemplate, payload.template_id)
        if not template or not template.enabled:
            raise HTTPException(status_code=400, detail="模板不存在或已禁用")

    campaign = Campaign(
        name=payload.name,
        template_id=template.id if template else None,
        status="queued",
        task_kind=payload.task_kind,
        operation_target=op,
        target_type=op,
        account_group_ids=group_ids,
        send_settings=payload.send_settings.model_dump(),
        extra_params=payload.extra_params or None,
        target_count=0,
        queued_count=0,
        created_by=user.username,
        merchant_id=default_merchant_id(user),
    )
    db.add(campaign)
    db.flush()

    now_iso = datetime.now(UTC).isoformat()
    if payload.task_kind == "broadcast":
        if op == "customer_broadcast":
            count = _build_customer_records(
                db, campaign, template, payload.customer_ids, now_iso,
                force_resend=payload.force_resend,
            )
        elif op == "friend_broadcast":
            count = _build_friend_records(db, campaign, template, group_ids, payload.friend_ids, now_iso)
        else:  # imported_target_broadcast
            count = build_imported_target_records(db, campaign, template, group_ids, payload.imported_targets or [])
        if count == 0:
            diag = getattr(campaign, "_eligibility_diag", None)
            db.rollback()
            if diag:
                # Tailored message for customer_broadcast so the operator
                # doesn't have to guess WHICH gate cut them off.
                parts = [f"共筛选到 {diag['total']} 个客户"]
                if diag["no_consent"]:
                    parts.append(f"{diag['no_consent']} 个 consent=false（导入时未勾「假设已同意」）")
                if diag["wrong_status"]:
                    parts.append(f"{diag['wrong_status']} 个状态不在 new/assigned/failed/queued")
                if diag["unassigned"]:
                    parts.append(f"{diag['unassigned']} 个未分配 TG 账号（去客户管理点「分配」）")
                raise HTTPException(
                    status_code=400,
                    detail="；".join(parts) + " — 没有满足全部条件的目标",
                )
            raise HTTPException(status_code=400, detail="没有满足条件的目标，请检查授权状态/分配/好友列表")
    else:
        # batch_op / modify_info: no per-target message rows queued today.
        # Execution will iterate the eligible accounts directly. Record the
        # count up-front so the UI shows the expected size.
        count = _eligible_account_count(db, group_ids)
        if count == 0:
            db.rollback()
            raise HTTPException(status_code=400, detail="所选分组下没有可用账号")

    campaign.target_count = count
    campaign.queued_count = count if payload.task_kind == "broadcast" else 0
    write_audit(db, actor=user, action="campaign.create", target_type="campaign",
                target_id=campaign.id, detail={
                    "task_kind": payload.task_kind, "operation_target": op,
                    "groups": group_ids, "target_count": count,
                })
    db.commit()
    db.refresh(campaign)
    return to_dict(campaign)


def _get_campaign_with_perm(db: DbSession, user, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    # Hide cross-tenant rows behind 404 to avoid leaking their existence
    # to a tenant that isn't supposed to see them. Check *before* the
    # permission gate so an attacker can't probe campaign ids by toggling
    # role flags either.
    if not campaign or not can_access_row(user, db, campaign):
        raise HTTPException(status_code=404, detail="群发任务不存在")
    if user.actor_kind == "support_agent" and not user.is_admin:
        if not (user.can("can_broadcast") or user.can("can_send_message")):
            raise HTTPException(
                status_code=403,
                detail="当前账号没有操作群发任务的权限，请联系管理员升级",
            )
    return campaign


@router.post("/{campaign_id}/start")
def start_campaign(campaign_id: int, db: DbSession, user: CurrentUserDep) -> dict:
    campaign = _get_campaign_with_perm(db, user, campaign_id)
    campaign.status = "running"
    campaign.started_at = datetime.now(UTC).isoformat()
    write_audit(db, actor=user, action="campaign.start", target_type="campaign", target_id=campaign.id)
    db.commit()
    db.refresh(campaign)

    # broadcast tasks pump through send_worker via existing MessageRecord
    # rows; batch_op / modify_info need an explicit worker dispatch.
    if campaign.task_kind in ("batch_op", "modify_info"):
        from backend.app.workers.execute_operation import execute_operation_campaign
        execute_operation_campaign.delay(campaign.id)

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


class PreflightPayload(BaseModel):
    task_kind: str = "broadcast"
    target_type: str = "customer_broadcast"
    account_group_ids: list[int] = Field(default_factory=list)
    customer_ids: list[int] | None = None
    imported_targets_count: int = 0


@router.post("/preflight")
def preflight(payload: PreflightPayload, db: DbSession, user: CurrentUserDep) -> dict:
    """Estimate eligible-account count + per-account average for a
    pending broadcast, so the create dialog can warn before submit
    when the per-account load is dangerously high (TG anti-spam +
    PeerFloodError ground)."""
    from backend.app.models.account import Account, AccountGroupMember

    group_ids = _scope_groups(user, payload.account_group_ids)
    # Eligible = enabled + active/imported + in the chosen groups.
    eligible_accounts = 0
    if group_ids:
        member_subq = select(AccountGroupMember.account_id).where(
            AccountGroupMember.group_id.in_(group_ids)
        )
        eligible_accounts = db.scalar(
            select(func.count(Account.id))
            .where(Account.enabled.is_(True))
            .where(Account.status.in_(["active", "imported"]))
            .where(Account.id.in_(member_subq))
        ) or 0

    # Estimate target count per task type. Customer/friend broadcasts
    # count actual eligible rows; imported uses what the form passed.
    target_count = 0
    if payload.target_type == "imported_target_broadcast":
        target_count = max(0, int(payload.imported_targets_count))
    elif payload.target_type == "customer_broadcast":
        q = select(func.count(Customer.id)).where(Customer.consent.is_(True))
        if payload.customer_ids:
            q = q.where(Customer.id.in_(payload.customer_ids))
        target_count = db.scalar(q) or 0
    elif payload.target_type == "friend_broadcast" and group_ids:
        friend_member_subq = select(AccountGroupMember.account_id).where(
            AccountGroupMember.group_id.in_(group_ids)
        )
        target_count = db.scalar(
            select(func.count(Friend.id))
            .where(Friend.account_id.in_(friend_member_subq))
            .where(Friend.opted_out.is_(False))
        ) or 0

    per_account = (target_count / eligible_accounts) if eligible_accounts else None
    # Heuristic thresholds: 15+ is yellow zone, 25+ is red zone. Tuned
    # so a 1 day default daily_limit of 20 lines up with the red.
    if per_account is None:
        severity = "no_accounts"
    elif per_account >= 25:
        severity = "danger"
    elif per_account >= 15:
        severity = "warning"
    else:
        severity = "ok"

    return {
        "target_count": target_count,
        "eligible_accounts": eligible_accounts,
        "per_account_avg": round(per_account, 1) if per_account is not None else None,
        "severity": severity,
    }


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


RECOVERABLE_ERROR_CODES = {
    "account_unavailable",   # auto-reroute will pick another account
    "flood_wait",            # account cooled down, send_worker tries again
    "no_target",             # transient — message data may have been fixed
}


@router.post("/{campaign_id}/requeue-failed")
def requeue_failed(
    campaign_id: int, db: DbSession, user: CurrentUserDep,
) -> dict:
    """Re-queue messages in this campaign that failed for a recoverable
    reason — the user gives them another shot via the worker's normal
    flow (now including auto-reroute). Fatal errors (ValueError /
    PhoneNotOccupied / etc., i.e. target really isn't on TG) are left
    alone so the operator doesn't pay ImportContacts quota to retry
    something that will never work."""
    if not can_write_tenant_data(user):
        raise HTTPException(status_code=403, detail=permission_denied_detail("can_broadcast"))
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="任务不存在")
    rows = list(db.scalars(
        select(MessageRecord)
        .where(MessageRecord.campaign_id == campaign_id)
        .where(MessageRecord.status.in_(["failed", "failed_permanent"]))
        .where(MessageRecord.error_code.in_(RECOVERABLE_ERROR_CODES))
    ))
    if not rows:
        return {"requeued": 0, "reason": "no recoverable failures"}
    for m in rows:
        m.status = "queued"
        m.error_code = None
        m.error_message = None
        m.next_run_at = None
        m.attempt_count = 0
    # Counters need to be rolled back so the campaign's failed_count
    # doesn't include the re-queued rows. If they fail again, the
    # worker will re-increment.
    campaign.failed_count = max(0, (campaign.failed_count or 0) - len(rows))
    # The campaign may have transitioned to a terminal state (failed /
    # partially_failed / completed). Flip it back to running so the
    # supervisor scans it again.
    if campaign.status in {"failed", "partially_failed", "completed"}:
        campaign.status = "running"
        campaign.completed_at = None
    write_audit(db, actor=user, action="campaign.requeue_failed",
                target_type="campaign", target_id=campaign_id,
                detail={"count": len(rows)})
    db.commit()
    return {"requeued": len(rows)}


@router.get("/{campaign_id}/operation-runs")
def list_operation_runs(
    campaign_id: int, db: DbSession, _: CurrentUserDep,
    limit: int = 500, offset: int = 0,
) -> list[dict]:
    """Per-account run results for a batch_op / modify_info campaign.
    Broadcast campaigns expose per-target rows via /messages; the
    non-message kinds don't queue MessageRecord rows, so execute_operation
    drops the outcome into audit_logs with action
    `campaign.{task_kind}.{operation}` and detail
    `{campaign_id, ok, error_code, error_message}`. We re-surface those
    rows here so the operator can see why a batch failed without
    drilling into the raw audit-log page."""
    from backend.app.models.account import Account
    from backend.app.models.audit import AuditLog

    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="任务不存在")
    rows = list(db.scalars(
        select(AuditLog)
        .where(AuditLog.target_type == "account")
        .where(AuditLog.action.like(f"campaign.{campaign.task_kind}.%"))
        .where(AuditLog.detail["campaign_id"].as_integer() == campaign_id)
        .order_by(AuditLog.id.desc())
        .offset(offset).limit(limit)
    ))
    if not rows:
        return []
    # Bulk-resolve account meta so the dialog can show phone/username
    # instead of opaque ids.
    acc_ids = {int(r.target_id) for r in rows if r.target_id and r.target_id.isdigit()}
    acc_map: dict[int, Account] = {}
    if acc_ids:
        for a in db.scalars(select(Account).where(Account.id.in_(acc_ids))):
            acc_map[a.id] = a
    out: list[dict] = []
    for r in rows:
        d = r.detail or {}
        try:
            aid = int(r.target_id) if r.target_id else None
        except (TypeError, ValueError):
            aid = None
        acc = acc_map.get(aid) if aid else None
        out.append({
            "id": r.id,
            "account_id": aid,
            "account_phone": acc.phone if acc else None,
            "account_nickname": acc.nickname if acc else None,
            "account_tg_user_id": acc.tg_user_id if acc else None,
            "ok": bool(d.get("ok")),
            "error_code": d.get("error_code"),
            "error_message": d.get("error_message"),
            "ran_at": r.created_at,
        })
    return out
