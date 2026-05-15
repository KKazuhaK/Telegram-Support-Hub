"""Execute non-message-sending campaign tasks (R5.execute).

Broadcasts (`task_kind="broadcast"`) keep flowing through send_worker via
MessageRecord rows. The other two task kinds — `batch_op` and
`modify_info` — operate per-account and don't need a per-target queue.
For each eligible account in the chosen groups we call into the
TelegramAdapter once and tally the campaign-level success/failure
counters.

Failure handling is deliberately simple at this stage:
- one attempt per account per dispatch
- task_concurrency from send_settings is honoured by Celery worker
  pool sizing, not enforced here
- per-account failure threshold not yet wired (would mark the account
  as paused on repeated failure)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from backend.app.core.database import SessionLocal
from backend.app.models.account import Account, AccountGroupMember
from backend.app.models.campaign import Campaign
from backend.app.models.data_groups import Material
from backend.app.models.proxy import ProxyEndpoint
from backend.app.services.audit import write_audit
from backend.app.telegram.adapter import OperationResult, get_adapter
from backend.app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _eligible_accounts(db, group_ids: list[int]) -> list[Account]:
    if not group_ids:
        return []
    member_subq = select(AccountGroupMember.account_id).where(
        AccountGroupMember.group_id.in_(group_ids)
    )
    return list(db.scalars(
        select(Account)
        .where(Account.enabled.is_(True))
        .where(Account.status.in_(["active", "imported"]))
        .where(Account.id.in_(member_subq))
        .order_by(Account.id.asc())
    ))


def _run_operation(account: Account, proxy: ProxyEndpoint | None,
                   operation: str, params: dict | None) -> OperationResult:
    """Single-shot Telegram operation. Wraps the async adapter call so the
    Celery prefork worker can stay synchronous. Tests patch this function
    so they don't need a real Telethon client."""
    adapter = get_adapter()
    return asyncio.run(adapter.run_operation(account, operation, params or {}, proxy=proxy))


@celery_app.task(name="backend.app.workers.execute_operation.execute_operation_campaign")
def execute_operation_campaign(campaign_id: int) -> dict:
    """Run a batch_op / modify_info campaign once.

    For broadcast campaigns the task is a no-op (send_worker handles
    them); we keep the early-return so accidental dispatch doesn't
    double-count.
    """
    with SessionLocal() as db:
        campaign = db.get(Campaign, campaign_id)
        if not campaign:
            return {"status": "skipped", "reason": "campaign_not_found"}
        if campaign.task_kind == "broadcast":
            return {"status": "skipped", "reason": "broadcast_handled_by_send_worker"}

        operation = campaign.operation_target
        params = dict(campaign.extra_params or {})
        group_ids = campaign.account_group_ids or []

        # modify_avatar needs the actual file path on disk. Resolve it
        # once up front so every account in the loop uses the same file
        # and we can fail the whole campaign cleanly if the material is
        # gone.
        avatar_resolve_error: str | None = None
        if operation == "modify_avatar":
            mid = params.get("material_id")
            material = db.get(Material, mid) if mid else None
            if not material or not material.file_path:
                avatar_resolve_error = f"找不到 material_id={mid} 或该资料没有可用文件"
            else:
                params["file_path"] = material.file_path
        accounts = _eligible_accounts(db, group_ids)
        if not accounts:
            campaign.status = "completed"
            campaign.completed_at = datetime.now(UTC).isoformat()
            db.commit()
            return {"status": "completed", "ok_count": 0, "failed_count": 0,
                    "reason": "no_eligible_accounts"}

        ok_count = 0
        failed_count = 0
        for account in accounts:
            if avatar_resolve_error:
                result = OperationResult(
                    ok=False, error_code="material_missing",
                    error_message=avatar_resolve_error,
                )
            else:
                proxy = db.get(ProxyEndpoint, account.proxy_id) if account.proxy_id else None
                try:
                    result = _run_operation(account, proxy, operation, params)
                except Exception as exc:
                    logger.exception("execute_operation crash for account %s op %s",
                                     account.id, operation)
                    result = OperationResult(
                        ok=False, error_code=type(exc).__name__, error_message=str(exc),
                    )
            if result.ok:
                ok_count += 1
            else:
                failed_count += 1
                # Surface the most recent error on the account row so the
                # operator can debug from the account list.
                if result.error_message:
                    account.last_error = result.error_message[:500]
            write_audit(
                db, actor=None,
                action=f"campaign.{campaign.task_kind}.{operation}",
                target_type="account", target_id=account.id,
                detail={
                    "campaign_id": campaign.id, "ok": result.ok,
                    "error_code": result.error_code,
                    "error_message": (result.error_message or "")[:200],
                },
            )

        campaign.sent_count = (campaign.sent_count or 0) + ok_count
        campaign.failed_count = (campaign.failed_count or 0) + failed_count
        campaign.completed_at = datetime.now(UTC).isoformat()
        if failed_count == 0:
            campaign.status = "completed"
        elif ok_count == 0:
            campaign.status = "partially_failed"
        else:
            campaign.status = "partially_failed"

        db.commit()
        return {
            "status": campaign.status, "ok_count": ok_count,
            "failed_count": failed_count,
        }
