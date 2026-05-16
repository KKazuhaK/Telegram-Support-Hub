from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.mixins import TimestampMixin


class SystemSetting(Base, TimestampMixin):
    """Single-row-per-key configuration store written from the admin UI.

    `value`           — plain JSON (provider id, proxy URL, model name, ...)
    `encrypted_value` — Fernet-encrypted secret (API keys, ...) kept off
                        the regular value blob so it's never accidentally
                        echoed back in a GET response.

    Keys in use:
      - 'translator': {provider, proxy_url, model, ...} + encrypted api_key
    """

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSON)
    encrypted_value: Mapped[str | None] = mapped_column(Text)
