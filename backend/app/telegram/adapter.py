from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.core.config import settings
from backend.app.core.crypto import decrypt_secret
from backend.app.models.account import Account
from backend.app.models.proxy import ProxyEndpoint

logger = logging.getLogger(__name__)

try:
    from telethon import TelegramClient, errors as telethon_errors
    from telethon.tl.types import User as TelethonUser

    TELETHON_AVAILABLE = True
except Exception:  # pragma: no cover - optional at runtime
    TelegramClient = None  # type: ignore[assignment]
    telethon_errors = None  # type: ignore[assignment]
    TelethonUser = None  # type: ignore[assignment]
    TELETHON_AVAILABLE = False


@dataclass
class TelegramSendResult:
    ok: bool
    external_message_id: str | None = None
    target_tg_user_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class TelegramValidateResult:
    ok: bool
    tg_user_id: str | None = None
    phone: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def _proxy_to_telethon(proxy: ProxyEndpoint | None) -> tuple | None:
    if not proxy:
        return None
    password = decrypt_secret(proxy.password_encrypted)
    if proxy.protocol == "socks5":
        # (proxy_type, host, port, rdns, username, password)
        return ("socks5", proxy.host, proxy.port, True, proxy.username, password)
    if proxy.protocol in {"http", "https"}:
        return (proxy.protocol, proxy.host, proxy.port, True, proxy.username, password)
    return None


def _strip_session_suffix(path: str) -> str:
    return path[:-8] if path.endswith(".session") else path


class TelegramAdapter:
    """Wraps Telethon. Falls back to a no-op stub when Telethon is unavailable
    or `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` are not configured.
    """

    def __init__(
        self,
        api_id: str | None = None,
        api_hash: str | None = None,
        connect_timeout: float = 15.0,
    ) -> None:
        self.api_id = api_id or settings.telegram_api_id
        self.api_hash = api_hash or settings.telegram_api_hash
        self.connect_timeout = connect_timeout

    @property
    def configured(self) -> bool:
        return TELETHON_AVAILABLE and bool(self.api_id) and bool(self.api_hash)

    def build_proxy_config(self, proxy: ProxyEndpoint | None) -> tuple | None:
        return _proxy_to_telethon(proxy)

    def _build_client(self, account: Account, proxy: ProxyEndpoint | None) -> Any:
        session_path = _strip_session_suffix(account.session_path)
        if not Path(account.session_path).exists():
            raise FileNotFoundError(account.session_path)
        proxy_cfg = _proxy_to_telethon(proxy)
        return TelegramClient(
            session_path,
            int(self.api_id),
            self.api_hash,
            proxy=proxy_cfg,
            connection_retries=2,
            timeout=self.connect_timeout,
        )

    async def validate_session(
        self, account: Account, proxy: ProxyEndpoint | None = None
    ) -> TelegramValidateResult:
        if not self.configured:
            ok = Path(account.session_path).exists()
            return TelegramValidateResult(
                ok=ok,
                error_code=None if ok else "session_missing",
                error_message=None if ok else "session file not found",
            )

        try:
            client = self._build_client(account, proxy)
        except FileNotFoundError as exc:
            return TelegramValidateResult(ok=False, error_code="session_missing", error_message=str(exc))

        try:
            await client.connect()
            if not await client.is_user_authorized():
                return TelegramValidateResult(
                    ok=False,
                    error_code="session_unauthorized",
                    error_message="session is not authorized",
                )
            me = await client.get_me()
            return TelegramValidateResult(
                ok=True,
                tg_user_id=str(getattr(me, "id", "")) or None,
                phone=getattr(me, "phone", None),
            )
        except Exception as exc:  # broad: Telethon raises many concrete classes
            logger.exception("validate_session failed for account %s", account.id)
            return TelegramValidateResult(
                ok=False,
                error_code=type(exc).__name__,
                error_message=str(exc),
            )
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def resolve_target(self, client: Any, target: str) -> Any:
        """Resolve a phone or @username to a Telegram entity."""
        return await client.get_entity(target)

    async def send_message(
        self,
        account: Account,
        target: str,
        body: str,
        proxy: ProxyEndpoint | None = None,
    ) -> TelegramSendResult:
        if not self.configured:
            return TelegramSendResult(
                ok=False,
                error_code="telegram_not_configured",
                error_message="Telethon not installed or TELEGRAM_API_ID/HASH not set",
            )

        try:
            client = self._build_client(account, proxy)
        except FileNotFoundError as exc:
            return TelegramSendResult(ok=False, error_code="session_missing", error_message=str(exc))

        try:
            await client.connect()
            if not await client.is_user_authorized():
                return TelegramSendResult(
                    ok=False, error_code="session_unauthorized", error_message="session not authorized"
                )
            entity = await self.resolve_target(client, target)
            tg_user_id = str(getattr(entity, "id", "")) or None
            sent = await client.send_message(entity, body)
            return TelegramSendResult(
                ok=True,
                external_message_id=str(getattr(sent, "id", "")) or None,
                target_tg_user_id=tg_user_id,
            )
        except Exception as exc:
            code = type(exc).__name__
            # Telethon flood errors carry seconds attribute
            if telethon_errors is not None and isinstance(exc, telethon_errors.FloodWaitError):
                return TelegramSendResult(
                    ok=False,
                    error_code="flood_wait",
                    error_message=f"flood wait {getattr(exc, 'seconds', '?')}s",
                )
            logger.exception("send_message failed for account %s -> %s", account.id, target)
            return TelegramSendResult(ok=False, error_code=code, error_message=str(exc))
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def listen_incoming(
        self,
        account: Account,
        proxy: ProxyEndpoint | None,
        on_message,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Connect once and run forever, calling `on_message(event_dict)` per
        incoming private message. `stop_event.set()` to exit gracefully.
        """
        if not self.configured:
            raise RuntimeError("Telethon not configured; cannot listen.")

        from telethon import events  # local import to avoid hard dep

        client = self._build_client(account, proxy)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError(f"account {account.id} session not authorized")

        @client.on(events.NewMessage(incoming=True))
        async def handler(event):  # pragma: no cover - exercised in integration
            try:
                sender = await event.get_sender()
                payload = {
                    "account_id": account.id,
                    "tg_user_id": str(getattr(sender, "id", "")) or None,
                    "username": getattr(sender, "username", None),
                    "phone": getattr(sender, "phone", None),
                    "message_id": str(getattr(event.message, "id", "")) or None,
                    "text": event.raw_text,
                    "date": event.message.date.isoformat() if event.message.date else None,
                }
                await on_message(payload)
            except Exception:
                logger.exception("listen handler failed for account %s", account.id)

        try:
            if stop_event is None:
                await client.run_until_disconnected()
            else:
                disconnect_task = asyncio.create_task(client.run_until_disconnected())
                stop_task = asyncio.create_task(stop_event.wait())
                done, pending = await asyncio.wait(
                    {disconnect_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass


_default_adapter: TelegramAdapter | None = None


def get_adapter() -> TelegramAdapter:
    global _default_adapter
    if _default_adapter is None:
        _default_adapter = TelegramAdapter()
    return _default_adapter
