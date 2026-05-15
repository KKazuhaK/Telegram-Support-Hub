from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base
from backend.app.models.mixins import TimestampMixin


class ProxyEndpoint(Base, TimestampMixin):
    __tablename__ = "proxy_endpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    protocol: Mapped[str] = mapped_column(String(20), default="socks5")
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    username: Mapped[str | None] = mapped_column(String(255))
    password_encrypted: Mapped[str | None] = mapped_column(String(1000))
    country: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), default="unchecked", index=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    last_checked_at: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)
    max_accounts: Mapped[int | None] = mapped_column(Integer)
    remark: Mapped[str | None] = mapped_column(Text)

    accounts = relationship("Account", back_populates="proxy")


class AccountProxyLog(Base, TimestampMixin):
    __tablename__ = "account_proxy_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    old_proxy_id: Mapped[int | None] = mapped_column(ForeignKey("proxy_endpoints.id"))
    new_proxy_id: Mapped[int | None] = mapped_column(ForeignKey("proxy_endpoints.id"))
    action: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(120))
