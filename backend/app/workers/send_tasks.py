from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.core.redis_client import account_send_lock
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.campaign import Campaign
from backend.app.models.message import MessageRecord
from backend.app.models.proxy import ProxyEndpoint
from backend.app.services.scheduling import (
    SendSettingsView,
    backoff_after_send_failure,
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


def _find_alternate_account(
    db, campaign: Campaign, exclude_account_id: int | None,
) -> Account | None:
    """Pick another eligible account from the campaign's groups, or
    None. Used to reroute messages off an account that got disabled
    mid-campaign (e.g. PeerFloodError auto-kill) so a single bad
    account doesn't bury half the campaign as 'account_unavailable'.
    Prefers the least-loaded account so a wave of redirects doesn't
    pile up on one survivor."""
    group_ids = campaign.account_group_ids or []
    if not group_ids:
        return None
    member_subq = select(AccountGroupMember.account_id).where(
        AccountGroupMember.group_id.in_(group_ids)
    )
    return db.scalar(
        select(Account)
        .where(Account.enabled.is_(True))
        .where(Account.status.in_(["active", "imported"]))
        .where(Account.id.in_(member_subq))
        .where(Account.id != exclude_account_id)
        .order_by(Account.sent_today.asc(), Account.id.asc())
        .limit(1)
    )


# Send errors that won't resolve through retry. Wasting attempts on
# these costs the sending account ImportContacts / search quota — TG
# will flood-wait us for trying. ValueError is what adapter.send_message
# raises when our import-contact fallback can't resolve the phone
# (number not on TG or privacy-hidden).
FAIL_FAST_ERROR_CODES = {
    "ValueError",
    "PhoneNotOccupiedError",
    "UsernameInvalidError",
    "UsernameNotOccupiedError",
    "PhoneNumberInvalidError",
    "PhoneNumberBannedError",
}


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

    # Per-tick caches to kill N+1 queries inside the message loop.
    # _account_group was 2 queries per message; hourly_limit COUNT was
    # 1 query per message. With these tables of size ~tens of accounts,
    # caching at the start of the tick saves O(batch_size) round-trips.
    group_cache: dict[int, AccountGroup | None] = {}
    hourly_count_cache: dict[int, int] = {}

    def _account_group_cached(db, account_id: int) -> AccountGroup | None:
        if account_id not in group_cache:
            group_cache[account_id] = _account_group(db, account_id)
        return group_cache[account_id]

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
                # Flush so the alternate-account lookup sees any
                # account.enabled=False writes from earlier iterations
                # of THIS tick (otherwise a freshly-killed account is
                # still visible to the candidate query → reroute picks
                # the just-disabled survivor).
                db.flush()
                alt = _find_alternate_account(db, campaign, message.account_id)
                if alt:
                    message.account_id = alt.id
                    message.error_code = None
                    message.error_message = None
                    continue
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

            group = _account_group_cached(db, account.id)
            if group and not group.enabled:
                message.next_run_at = next_run_after_failure(now, view).isoformat()
                continue
            if group and group.daily_limit and group.sent_today >= group.daily_limit:
                message.next_run_at = next_run_after_failure(now, view).isoformat()
                continue

            if account.daily_limit and account.sent_today >= account.daily_limit:
                message.next_run_at = next_run_after_failure(now, view).isoformat()
                continue

            # Hourly throttle. Counts actually-sent rows in the last
            # hour for this account, cached per-tick to avoid N COUNT
            # queries per batch. None means uncapped.
            if account.hourly_limit:
                if account.id not in hourly_count_cache:
                    from datetime import timedelta as _td
                    hour_ago = (now - _td(hours=1)).isoformat()
                    hourly_count_cache[account.id] = db.scalar(
                        select(func.count(MessageRecord.id))
                        .where(MessageRecord.account_id == account.id)
                        .where(MessageRecord.direction == "outbound")
                        .where(MessageRecord.sent_at.isnot(None))
                        .where(MessageRecord.sent_at >= hour_ago)
                    ) or 0
                if hourly_count_cache[account.id] >= account.hourly_limit:
                    message.next_run_at = next_run_after_failure(now, view).isoformat()
                    continue
                # Reserve the slot inside this tick so subsequent
                # messages on the same account see the bumped count.
                hourly_count_cache[account.id] += 1

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
                    # Bump next_run_at so the next tick doesn't re-pick
                    # this row immediately. Without this the same hot
                    # account spins the worker → redis QPS spike + log
                    # spam of "skipped_locked".
                    message.next_run_at = next_run_after_failure(now, view).isoformat()
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
                    # Exponential backoff per attempt — a transient
                    # 5xx-ish failure shouldn't have us retry the same
                    # message every 2 minutes for 6 minutes flat. Use
                    # the post-increment attempt_count we already set
                    # above so attempt 1 = 1×base, attempt 2 = 2×base.
                    message.next_run_at = backoff_after_send_failure(
                        now, view, message.attempt_count,
                    ).isoformat()
                    # Account-level kill-switches: PeerFloodError means
                    # Telegram has flagged this account as a spammer —
                    # retrying just escalates toward a permaban. Same
                    # for UserDeactivated (account terminated). Disable
                    # the account immediately so the supervisor stops
                    # feeding it new messages, and mark this message as
                    # terminal (no retry).
                    ACCOUNT_KILL_CODES = {
                        "PeerFloodError",
                        "UserDeactivatedError",
                        "UserDeactivatedBanError",
                    }
                    if result.error_code in ACCOUNT_KILL_CODES:
                        account.status = "limited"
                        account.enabled = False
                        account.last_error = (
                            f"{result.error_code}: {result.error_message or ''} "
                            f"(auto-disabled by send_worker)"
                        )[:500]
                        message.status = "failed_permanent"
                        campaign.failed_count += 1
                        failed += 1
                    elif result.error_code in FAIL_FAST_ERROR_CODES:
                        # No-recover errors: target isn't on TG / phone
                        # invalid / username taken back / etc. Retrying
                        # burns ImportContacts/search quota for nothing
                        # and risks our own account hitting a flood-wait.
                        message.status = "failed_permanent"
                        campaign.failed_count += 1
                        failed += 1
                    elif message.attempt_count >= settings.max_failed_attempts:
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

                # Commit BEFORE releasing the lock so a crash between
                # release and the end-of-batch commit can't leave the
                # message visible-as-queued in another worker's snapshot
                # — that worker would re-pick + double-send. With the
                # commit inside the with-block, by the time the lock is
                # free, the row's terminal state is already durable.
                db.commit()

            processed += 1

        # Mark BROADCAST campaigns whose queue is exhausted as terminal.
        # Scan all running broadcast campaigns (not just ones touched
        # this tick) so a campaign that ran out of messages in a prior
        # tick still transitions. batch_op / modify_info kinds are
        # excluded — they never queue MessageRecord rows, so the
        # has_pending=None check would flip them to 'completed'
        # prematurely (execute_operation_campaign handles their state
        # itself).
        db.flush()  # make the just-mutated row statuses visible to the next select
        running_campaigns = list(db.scalars(
            select(Campaign)
            .where(Campaign.status == "running")
            .where(Campaign.task_kind == "broadcast")
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
