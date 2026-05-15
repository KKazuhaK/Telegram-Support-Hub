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


@dataclass
class OperationResult:
    """Outcome of a single per-account operation (delete_friend, etc.)."""
    ok: bool
    detail: str | None = None
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


def _to_telethon_entities(entities: list[dict] | None, _text: str) -> list | None:
    """Convert our portable {type/offset/length/...} dicts into Telethon
    MessageEntity* objects. Unknown types are silently skipped — they will
    still appear in the message body as plain text."""
    if not entities or not TELETHON_AVAILABLE:
        return None
    try:
        from telethon.tl import types as tl
    except Exception:
        return None

    out: list = []
    for ent in entities:
        kind = ent.get("type")
        off = int(ent.get("offset", 0))
        length = int(ent.get("length", 0))
        try:
            if kind == "bold":
                out.append(tl.MessageEntityBold(offset=off, length=length))
            elif kind == "italic":
                out.append(tl.MessageEntityItalic(offset=off, length=length))
            elif kind == "underline":
                out.append(tl.MessageEntityUnderline(offset=off, length=length))
            elif kind == "strike":
                out.append(tl.MessageEntityStrike(offset=off, length=length))
            elif kind == "code":
                out.append(tl.MessageEntityCode(offset=off, length=length))
            elif kind == "pre":
                out.append(tl.MessageEntityPre(offset=off, length=length, language=ent.get("language", "")))
            elif kind == "url":
                out.append(tl.MessageEntityUrl(offset=off, length=length))
            elif kind == "text_url":
                out.append(tl.MessageEntityTextUrl(offset=off, length=length, url=ent.get("url", "")))
            elif kind == "email":
                out.append(tl.MessageEntityEmail(offset=off, length=length))
            elif kind == "mention":
                out.append(tl.MessageEntityMention(offset=off, length=length))
            elif kind == "hashtag":
                out.append(tl.MessageEntityHashtag(offset=off, length=length))
            elif kind == "phone":
                out.append(tl.MessageEntityPhone(offset=off, length=length))
        except Exception:
            # Telethon may version-bump entity constructors; falling through
            # leaves the plaintext intact rather than failing the whole send.
            continue
    return out or None


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
        entities: list[dict] | None = None,
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
            formatting = _to_telethon_entities(entities, body) if entities else None
            if formatting:
                sent = await client.send_message(entity, body, formatting_entities=formatting)
            else:
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

    async def run_operation(
        self,
        account: Account,
        operation: str,
        params: dict,
        proxy: ProxyEndpoint | None = None,
    ) -> OperationResult:
        """Run a single non-message operation against `account`.

        Supported operations:
          delete_friend          — remove all contacts (clears the friend list)
          leave_other_devices    — kick all other authorised sessions
          modify_nickname        — UpdateProfileRequest first_name=new_value
          modify_signature       — UpdateProfileRequest about=new_value
          modify_username        — UpdateUsernameRequest

        Returns OperationResult so the worker can branch on .ok without
        exception handling. Telethon errors are caught and surfaced via
        error_code/error_message; an unconfigured adapter (no
        TELEGRAM_API_ID) returns ok=False with `telegram_not_configured`.
        """
        if not self.configured:
            return OperationResult(
                ok=False, error_code="telegram_not_configured",
                error_message="Telethon not installed or TELEGRAM_API_ID/HASH not set",
            )
        try:
            client = self._build_client(account, proxy)
        except FileNotFoundError as exc:
            return OperationResult(ok=False, error_code="session_missing", error_message=str(exc))

        try:
            await client.connect()
            if not await client.is_user_authorized():
                return OperationResult(
                    ok=False, error_code="session_unauthorized",
                    error_message="session not authorized",
                )
            return await self._dispatch_operation(client, operation, params)
        except Exception as exc:
            logger.exception("run_operation failed for account %s op %s",
                             account.id, operation)
            return OperationResult(
                ok=False, error_code=type(exc).__name__, error_message=str(exc),
            )
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def _dispatch_operation(self, client: Any, operation: str, params: dict) -> OperationResult:
        from telethon.tl import functions, types  # local import keeps test envs without telethon happy

        if operation == "delete_friend":
            contacts = await client(functions.contacts.GetContactsRequest(hash=0))
            users = getattr(contacts, "users", []) or []
            if not users:
                return OperationResult(ok=True, detail="no contacts to delete")
            await client(functions.contacts.DeleteContactsRequest(id=[u.id for u in users]))
            return OperationResult(ok=True, detail=f"removed {len(users)} contacts")

        if operation == "leave_other_devices":
            await client(functions.auth.ResetAuthorizationsRequest())
            return OperationResult(ok=True, detail="other sessions reset")

        if operation == "modify_nickname":
            new = (params.get("new_value") or "").strip()
            await client(functions.account.UpdateProfileRequest(first_name=new))
            return OperationResult(ok=True, detail=f"nickname -> {new}")

        if operation == "modify_signature":
            new = (params.get("new_value") or "").strip()
            await client(functions.account.UpdateProfileRequest(about=new))
            return OperationResult(ok=True, detail=f"about -> {new}")

        if operation == "modify_username":
            new = (params.get("new_value") or "").strip().lstrip("@")
            await client(functions.account.UpdateUsernameRequest(username=new))
            return OperationResult(ok=True, detail=f"username -> {new}")

        # Operations not yet implemented: leave_group, detect_mutual,
        # appeal_mutual, modify_password, modify_avatar.
        return OperationResult(
            ok=False, error_code="not_implemented",
            error_message=f"operation '{operation}' not implemented yet",
        )

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
