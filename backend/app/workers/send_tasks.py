from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.app.core.database import SessionLocal
from backend.app.models.account import Account
from backend.app.models.campaign import Campaign
from backend.app.models.message import MessageRecord
from backend.app.workers.celery_app import celery_app


@celery_app.task(name="backend.app.workers.send_tasks.dispatch_send_queue")
def dispatch_send_queue(limit: int = 100) -> dict:
    processed = 0
    now = datetime.now(UTC)

    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(MessageRecord)
                .where(
                    MessageRecord.status == "queued",
                    MessageRecord.next_run_at <= now.isoformat(),
                )
                .order_by(MessageRecord.id.asc())
                .limit(limit)
            )
        )

        for message in rows:
            campaign = db.get(Campaign, message.campaign_id) if message.campaign_id else None
            if not campaign or campaign.status != "running":
                continue

            account = db.get(Account, message.account_id) if message.account_id else None
            if not account or not account.enabled or account.status not in {"active", "imported"}:
                message.status = "failed"
                message.error_code = "account_unavailable"
                message.error_message = "No active account is assigned to this message."
                campaign.failed_count += 1
                processed += 1
                continue

            settings = campaign.send_settings or {}
            interval = int(settings.get("success_interval_seconds", 60))

            # This is intentionally a placeholder. The real send path must call
            # TelegramAdapter with the account session and proxy configuration.
            message.status = "queued"
            message.next_run_at = (now + timedelta(seconds=interval)).isoformat()
            message.error_code = "telegram_adapter_not_connected"
            message.error_message = "Send worker is wired, but Telegram sending is not enabled yet."
            processed += 1

        db.commit()

    return {"processed": processed}
