from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.core.crypto import decrypt_secret
from backend.app.models.account import Account
from backend.app.models.proxy import ProxyEndpoint


@dataclass
class TelegramSendResult:
    ok: bool
    external_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class TelegramAdapter:
    def __init__(self, api_id: str, api_hash: str) -> None:
        self.api_id = api_id
        self.api_hash = api_hash

    def build_proxy_config(self, proxy: ProxyEndpoint | None) -> tuple | None:
        if not proxy:
            return None
        password = decrypt_secret(proxy.password_encrypted)
        if proxy.protocol == "socks5":
            return ("socks5", proxy.host, proxy.port, True, proxy.username, password)
        if proxy.protocol in {"http", "https"}:
            return (proxy.protocol, proxy.host, proxy.port, True, proxy.username, password)
        return None

    async def validate_session(self, account: Account, proxy: ProxyEndpoint | None = None) -> bool:
        session_path = Path(account.session_path)
        if not session_path.exists():
            return False
        # Telethon connection will be added after API credentials are confirmed.
        _ = self.build_proxy_config(proxy)
        return True

    async def send_message(self, account: Account, target: str, body: str, proxy: ProxyEndpoint | None = None) -> TelegramSendResult:
        _ = account, target, body, proxy
        return TelegramSendResult(
            ok=False,
            error_code="not_implemented",
            error_message="Telegram sending is not implemented yet.",
        )

    async def listen_incoming(self, account: Account, proxy: ProxyEndpoint | None = None) -> Any:
        _ = account, proxy
        raise NotImplementedError("Incoming message listener is not implemented yet.")
