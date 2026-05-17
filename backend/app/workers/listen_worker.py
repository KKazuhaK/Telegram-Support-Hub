from __future__ import annotations

import asyncio
import logging
import signal
from datetime import UTC, datetime

from sqlalchemy import select

from backend.app.core.database import SessionLocal
from backend.app.models.account import Account
from backend.app.models.campaign import Campaign
from backend.app.models.customer import Customer, Friend
from backend.app.models.message import MessageRecord
from backend.app.models.proxy import ProxyEndpoint
from backend.app.services.reply_bus import publish_reply
from backend.app.telegram.adapter import get_adapter

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _persist_reply(payload: dict) -> None:
    """Persist an incoming Telegram message and update related entities."""
    text = (payload.get("text") or "")[:4000]
    tg_user_id = payload.get("tg_user_id")
    phone = payload.get("phone")
    account_id = payload.get("account_id")
    received_at = payload.get("date") or _now_iso()

    with SessionLocal() as db:
        # 1. Friend match (by tg_user_id within account scope)
        if tg_user_id and account_id:
            friend = db.scalar(
                select(Friend).where(Friend.account_id == account_id, Friend.tg_user_id == tg_user_id)
            )
            if friend:
                friend.last_message_at = received_at
                friend.last_reply_at = received_at
                friend.status = "replied"

        # 2. Customer match: first by real phone, then by the placeholder
        # phone `tg:<sender_tg_user_id>` that the 'promote orphan thread'
        # flow assigns when the sender has no phone visible. Without the
        # second lookup every new inbound from the same orphan-promoted
        # contact lands back in the orphan bucket instead of the
        # promoted customer's conversation.
        customer = None
        if phone:
            customer = db.scalar(select(Customer).where(Customer.phone == phone))
        if customer is None and tg_user_id:
            customer = db.scalar(
                select(Customer).where(Customer.phone == f"tg:{tg_user_id}")
            )
        if customer:
            customer.last_reply_at = received_at
            customer.last_reply_text = text
            customer.last_message_at = received_at
            customer.status = "replied"

        # 3. Persist the inbound message as its own MessageRecord row so
        # the chat-history endpoint can render a real conversation
        # (out, in, out, in, ...) rather than only showing campaigns.
        # Photo / image-document messages carry attachment_path +
        # attachment_mime so the bubble can render the <img> the same
        # way it does for outbound chat-uploads.
        attachment_path = payload.get("attachment_path")
        attachment_mime = payload.get("attachment_mime")
        body_for_row = text
        if attachment_path and not body_for_row:
            # Empty caption → show a placeholder so the row isn't blank
            # in plain-text views (audit / export). The chat UI sees the
            # attachment_path and renders the image regardless.
            body_for_row = "[图片]"
        inbound = MessageRecord(
            account_id=account_id,
            customer_id=customer.id if customer else None,
            phone=phone,
            target_tg_user_id=tg_user_id,
            body_snapshot=body_for_row,
            direction="inbound",
            status="received",
            sent_at=received_at,
            attachment_path=attachment_path,
            attachment_mime=attachment_mime,
        )
        db.add(inbound)

        # 4. ALSO bind the reply to the most recent outbound row in this
        # conversation (legacy behavior — campaign reply_count + UI rely
        # on the outbound row's replied_at/reply_text).
        match_q = (
            select(MessageRecord)
            .where(MessageRecord.account_id == account_id)
            .where(MessageRecord.direction == "outbound")
        )
        if tg_user_id:
            match_q = match_q.where(MessageRecord.target_tg_user_id == tg_user_id)
        elif phone:
            match_q = match_q.where(MessageRecord.phone == phone)
        else:
            match_q = match_q.where(MessageRecord.id == -1)
        match_q = match_q.order_by(MessageRecord.id.desc()).limit(1)
        record = db.scalar(match_q)
        if record:
            record.replied_at = received_at
            record.reply_text = text
            if record.status in {"sent", "read"}:
                record.status = "replied"
            if record.campaign_id:
                campaign = db.get(Campaign, record.campaign_id)
                if campaign:
                    campaign.reply_count = (campaign.reply_count or 0) + 1
            account = db.get(Account, account_id) if account_id else None
            if account:
                account.total_replies = (account.total_replies or 0) + 1

        db.commit()

    publish_reply({
        "account_id": account_id,
        "tg_user_id": tg_user_id,
        "phone": phone,
        "text": text,
        "received_at": received_at,
    })


async def _run_account(account_id: int, stop_event: asyncio.Event) -> None:
    adapter = get_adapter()
    if not adapter.configured:
        logger.warning("Telethon not configured, listen worker idle for account %s", account_id)
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            with SessionLocal() as db:
                account = db.get(Account, account_id)
                if not account:
                    return
                proxy = db.get(ProxyEndpoint, account.proxy_id) if account.proxy_id else None
                # detach for use outside session
                db.expunge(account)
                if proxy:
                    db.expunge(proxy)
            await adapter.listen_incoming(
                account=account,
                proxy=proxy,
                on_message=_persist_reply,
                stop_event=stop_event,
            )
        except Exception:
            logger.exception("listen loop crashed for account %s, retrying in 30s", account_id)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass


async def _supervise(stop_event: asyncio.Event, refresh_seconds: int = 60) -> None:
    tasks: dict[int, asyncio.Task] = {}
    try:
        while not stop_event.is_set():
            with SessionLocal() as db:
                rows = list(
                    db.scalars(
                        select(Account).where(
                            Account.enabled.is_(True),
                            Account.status.in_(["active", "imported"]),
                        )
                    )
                )
                wanted = {acc.id for acc in rows}

            for account_id in wanted - tasks.keys():
                logger.info("starting listener for account %s", account_id)
                tasks[account_id] = asyncio.create_task(_run_account(account_id, stop_event))

            for account_id in list(tasks.keys() - wanted):
                logger.info("stopping listener for account %s", account_id)
                tasks[account_id].cancel()
                tasks.pop(account_id, None)

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=refresh_seconds)
            except asyncio.TimeoutError:
                continue
    finally:
        for task in tasks.values():
            task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop_event = asyncio.Event()

    def _stop(*_args):
        logger.info("listen worker received stop signal")
        stop_event.set()

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, _stop)
            except (ValueError, OSError):
                pass

    asyncio.run(_supervise(stop_event))


if __name__ == "__main__":
    main()
