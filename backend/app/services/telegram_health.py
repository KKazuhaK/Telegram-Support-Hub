"""Pre-flight check for Telegram API access.

Two concerns rolled into one report:
  1. Are TELEGRAM_API_ID / TELEGRAM_API_HASH actually configured?
  2. Can this host reach a Telegram MTProto DC right now? (network /
     proxy / firewall sanity)

We open a Telethon client with a throwaway in-memory session, connect
(NO login, NO account state mutated), then disconnect. The handshake
goes through to the DC, so a successful connect proves both that the
api_id is valid format *and* that the network path works.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_SEC = 10.0


def _have_telethon() -> bool:
    try:
        import telethon  # noqa: F401
        return True
    except Exception:
        return False


def check_telegram_health() -> dict:
    """Synchronous wrapper; safe to call from FastAPI request handlers."""
    api_id = settings.telegram_api_id
    api_hash = settings.telegram_api_hash
    report = {
        "configured": bool(api_id and api_hash),
        "reachable": False,
        "error": None,
    }
    if not report["configured"]:
        report["error"] = "TELEGRAM_API_ID / TELEGRAM_API_HASH 未在 .env 中配置"
        return report
    if not _have_telethon():
        report["error"] = "未安装 telethon（pip install telethon）"
        return report
    try:
        report["reachable"] = asyncio.run(_probe_dc(int(api_id), api_hash))
    except ValueError as exc:
        report["error"] = f"TELEGRAM_API_ID 不是数字：{exc}"
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"无法连接 Telegram 服务器：{exc}"
    return report


async def _probe_dc(api_id: int, api_hash: str) -> bool:
    """Open a Telethon client against a fresh session file, connect to
    Telegram's nearest DC, disconnect. Returns True iff the MTProto
    handshake completes. No account is touched.
    """
    from telethon import TelegramClient

    with tempfile.TemporaryDirectory() as tmp:
        # SQLite session file (Telethon's default) lives only for this call.
        session_path = Path(tmp) / "probe"
        client = TelegramClient(str(session_path), api_id, api_hash,
                                timeout=_CONNECT_TIMEOUT_SEC)
        try:
            await asyncio.wait_for(client.connect(), timeout=_CONNECT_TIMEOUT_SEC)
            return bool(client.is_connected())
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
