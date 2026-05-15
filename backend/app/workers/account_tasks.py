from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from backend.app.core.database import SessionLocal
from backend.app.models.account import Account, AccountGroupMember
from backend.app.models.customer import Friend
from backend.app.models.proxy import ProxyEndpoint
from backend.app.services.proxy_checker import check_tcp
from backend.app.telegram.adapter import get_adapter
from backend.app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@celery_app.task(name="backend.app.workers.account_tasks.check_all_proxies")
def check_all_proxies() -> dict:
    checked = 0
    with SessionLocal() as db:
        proxies = list(db.scalars(select(ProxyEndpoint).where(ProxyEndpoint.status != "disabled")))
        for proxy in proxies:
            result = check_tcp(proxy.host, proxy.port)
            proxy.status = "active" if result.ok else "error"
            proxy.latency_ms = result.latency_ms
            proxy.last_error = result.error
            proxy.last_checked_at = _now_iso()
            checked += 1
        db.commit()
    return {"checked": checked}


@celery_app.task(name="backend.app.workers.account_tasks.validate_all_sessions")
def validate_all_sessions() -> dict:
    adapter = get_adapter()
    if not adapter.configured:
        return {"validated": 0, "status": "telegram_not_configured"}

    validated = 0
    failed = 0
    with SessionLocal() as db:
        accounts = list(db.scalars(select(Account).where(Account.enabled.is_(True))))
        for account in accounts:
            proxy = db.get(ProxyEndpoint, account.proxy_id) if account.proxy_id else None
            try:
                result = asyncio.run(adapter.validate_session(account, proxy))
            except Exception as exc:
                logger.exception("validate failed for account %s", account.id)
                account.status = "error"
                account.last_error = str(exc)
                failed += 1
                continue

            if result.ok:
                account.status = "active"
                account.last_login_at = _now_iso()
                account.last_error = None
                validated += 1
            else:
                account.status = "error"
                account.last_error = result.error_message
                failed += 1
        db.commit()
    return {"validated": validated, "failed": failed}


async def _sync_account_friends(account_id: int) -> int:
    adapter = get_adapter()
    if not adapter.configured:
        return 0

    from telethon import TelegramClient  # noqa: F401  ensure telethon present

    with SessionLocal() as db:
        account = db.get(Account, account_id)
        if not account:
            return 0
        proxy = db.get(ProxyEndpoint, account.proxy_id) if account.proxy_id else None
        primary_member = db.scalar(
            select(AccountGroupMember).where(
                AccountGroupMember.account_id == account_id, AccountGroupMember.is_primary.is_(True)
            )
        )
        primary_group_id = primary_member.group_id if primary_member else None
        db.expunge(account)
        if proxy:
            db.expunge(proxy)

    client = adapter._build_client(account, proxy)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return 0

    upserted = 0
    try:
        with SessionLocal() as db:
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                if entity is None or not hasattr(entity, "id"):
                    continue
                if getattr(entity, "bot", False):
                    continue
                tg_user_id = str(entity.id)
                friend = db.scalar(
                    select(Friend).where(
                        Friend.account_id == account_id,
                        Friend.tg_user_id == tg_user_id,
                    )
                )
                payload = {
                    "username": getattr(entity, "username", None),
                    "phone": (f"+{entity.phone}" if getattr(entity, "phone", None) else None),
                    "nickname": getattr(entity, "first_name", None) or dialog.name,
                    "last_message_at": dialog.date.isoformat() if dialog.date else None,
                }
                if friend:
                    for k, v in payload.items():
                        if v is not None:
                            setattr(friend, k, v)
                else:
                    db.add(
                        Friend(
                            account_id=account_id,
                            account_group_id=primary_group_id,
                            tg_user_id=tg_user_id,
                            status="new",
                            **payload,
                        )
                    )
                upserted += 1
            db.commit()
    finally:
        await client.disconnect()

    return upserted


@celery_app.task(name="backend.app.workers.account_tasks.sync_account_friends")
def sync_account_friends(account_id: int) -> dict:
    upserted = asyncio.run(_sync_account_friends(account_id))
    return {"account_id": account_id, "upserted": upserted}
