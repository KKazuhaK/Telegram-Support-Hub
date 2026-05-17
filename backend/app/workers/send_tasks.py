from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.core.redis_client import account_send_lock
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.campaign import Campaign
from backend.app.models.message import MessageRecord
from backend.app.models.proxy import ProxyEndpoint
from backend.app.services.scheduling import (
    SendSettingsView,
    in_quiet_hours,
    lock_ttl_seconds,
    next_run_after_failure,
    next_run_after_success,
)
from backend.app.telegram.adapter import TelegramSendResult, get_adapter
from backend.app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _account_group(db, account_id: int) -> AccountGroup | None:
    member = db.scalar(
        select(AccountGroupMember).where(AccountGroupMember.account_id == account_id, AccountGroupMember.is_primary.is_(True))
    )
    if not member:
        return None
    return db.get(AccountGroup, member.group_id)


def _resolve_target(message: MessageRecord) -> str | None:
    return message.target_tg_user_id or message.phone


def _send_via_adapter(
    account: Account, proxy: ProxyEndpoint | None,
    target: str, body: str, entities: list | None = None,
) -> TelegramSendResult:
    adapter = get_adapter()
    return asyncio.run(adapter.send_message(
        account=account, target=target, body=body, proxy=proxy, entities=entities,
    ))


@celery_app.task(name="backend.app.workers.send_tasks.dispatch_send_queue")
def dispatch_send_queue(limit: int | None = None) -> dict:
    """Pump the message-record queue for broadcast tasks.

    Note: batch_op / modify_info campaigns (R5) create no MessageRecord rows
    so they are naturally skipped here. Their execution path will arrive
    as a separate Celery task family in R5.execute (TODO).
    """
    limit = int(limit or settings.dispatch_batch_size)
    processed = 0
    sent_ok = 0
    failed = 0
    skipped_locked = 0
    now = datetime.now(UTC)
    now_iso = now.isoformat()

    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(MessageRecord)
                .where(
                    MessageRecord.status.in_(["queued", "retry"]),
                    (MessageRecord.next_run_at.is_(None)) | (MessageRecord.next_run_at <= now_iso),
                )
                .order_by(MessageRecord.id.asc())
                .limit(limit)
            )
        )

        for message in rows:
            campaign = db.get(Campaign, message.campaign_id) if message.campaign_id else None
            if not campaign or campaign.status not in {"running", "queued"}:
                continue
            if campaign.status == "queued":
                # auto promote to running on first dispatch tick
                campaign.status = "running"
                campaign.started_at = campaign.started_at or now_iso

            account = db.get(Account, message.account_id) if message.account_id else None
            if not account or not account.enabled or account.status not in {"active", "imported"}:
                message.status = "failed"
                message.error_code = "account_unavailable"
                message.error_message = "no active account assigned"
                campaign.failed_count += 1
                failed += 1
                continue

            view = SendSettingsView.from_dict(campaign.send_settings)

            if in_quiet_hours(now, view.quiet_hours_start, view.quiet_hours_end):
                # postpone until end of quiet window check on next tick
                message.next_run_at = next_run_after_failure(now, view).isoformat()
                continue

            group = _account_group(db, account.id)
            if group and not group.enabled:
                message.next_run_at = next_run_after_failure(now, view).isoformat()
                continue
            if group and group.daily_limit and group.sent_today >= group.daily_limit:
                message.next_run_at = next_run_after_failure(now, view).isoformat()
                continue

            if account.daily_limit and account.sent_today >= account.daily_limit:
                message.next_run_at = next_run_after_failure(now, view).isoformat()
                continue

            target = _resolve_target(message)
            if not target:
                message.status = "failed_permanent"
                message.error_code = "no_target"
                message.error_message = "missing target_tg_user_id and phone"
                campaign.failed_count += 1
                failed += 1
                continue

            ttl = lock_ttl_seconds(view, padding=settings.dispatch_lock_ttl_padding)
            with account_send_lock(account.id, ttl) as got_lock:
                if not got_lock:
                    skipped_locked += 1
                    continue

                message.status = "sending"
                message.locked_by = f"celery:{account.id}"
                message.locked_at = now_iso
                message.attempt_count = (message.attempt_count or 0) + 1
                db.flush()

                proxy = db.get(ProxyEndpoint, account.proxy_id) if account.proxy_id else None

                try:
                    result = _send_via_adapter(
                        account, proxy, target, message.body_snapshot,
                        entities=message.entities,
                    )
                except Exception as exc:  # adapter framework error
                    logger.exception("dispatch send failed for message %s", message.id)
                    result = TelegramSendResult(
                        ok=False, error_code=type(exc).__name__, error_message=str(exc)
                    )

                if result.ok:
                    message.status = "sent"
                    message.sent_at = now_iso
                    message.error_code = None
                    message.error_message = None
                    message.external_message_id = result.external_message_id
                    message.target_tg_user_id = result.target_tg_user_id or message.target_tg_user_id
                    message.next_run_at = next_run_after_success(now, view).isoformat()
                    account.sent_today = (account.sent_today or 0) + 1
                    account.total_sent = (account.total_sent or 0) + 1
                    if group:
                        group.sent_today = (group.sent_today or 0) + 1
                    campaign.sent_count += 1
                    sent_ok += 1
                else:
                    message.error_code = result.error_code
                    message.error_message = result.error_message
                    message.next_run_at = next_run_after_failure(now, view).isoformat()
                    if message.attempt_count >= settings.max_failed_attempts:
                        message.status = "failed_permanent"
                        campaign.failed_count += 1
                        failed += 1
                        if result.error_code in {"session_unauthorized", "session_missing"}:
                            account.status = "error"
                            account.last_error = result.error_message
                    else:
                        message.status = "retry"
                        if result.error_code == "flood_wait":
                            account.status = "limited"
                            account.last_error = result.error_message

            processed += 1

        # Mark campaigns whose queue is exhausted as terminal. Scan ALL
        # running campaigns, not just the ones touched this tick — if
        # the last message of a campaign was processed in a prior tick
        # (and no further messages exist), restricting to active_ids
        # leaves the campaign stuck on 'running' forever.
        db.flush()  # make the just-mutated row statuses visible to the next select
        running_campaigns = list(db.scalars(
            select(Campaign).where(Campaign.status == "running")
        ))
        for cmp in running_campaigns:
            has_pending = db.scalar(
                select(MessageRecord.id)
                .where(
                    MessageRecord.campaign_id == cmp.id,
                    MessageRecord.status.in_(["queued", "retry", "sending"]),
                )
                .limit(1)
            )
            if has_pending is not None:
                continue
            sent_n = cmp.sent_count or 0
            failed_n = cmp.failed_count or 0
            if failed_n and not sent_n:
                cmp.status = "failed"          # 100% failure
            elif failed_n:
                cmp.status = "partially_failed"
            else:
                cmp.status = "completed"
            cmp.completed_at = now_iso

        db.commit()

    return {"processed": processed, "sent": sent_ok, "failed": failed, "skipped_locked": skipped_locked}


@celery_app.task(name="backend.app.workers.send_tasks.reset_daily_quota")
def reset_daily_quota() -> dict:
    with SessionLocal() as db:
        accounts = list(db.scalars(select(Account)))
        for account in accounts:
            account.sent_today = 0
        groups = list(db.scalars(select(AccountGroup)))
        for group in groups:
            group.sent_today = 0
        db.commit()
    return {"accounts_reset": len(accounts), "groups_reset": len(groups)}
