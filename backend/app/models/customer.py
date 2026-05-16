from sqlalchemy import Boolean, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.mixins import TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    tags: Mapped[list | None] = mapped_column(JSON)
    source: Mapped[str | None] = mapped_column(String(120))
    consent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    assigned_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    last_message_at: Mapped[str | None] = mapped_column(String(64))
    last_read_at: Mapped[str | None] = mapped_column(String(64))
    last_reply_at: Mapped[str | None] = mapped_column(String(64))
    last_reply_text: Mapped[str | None] = mapped_column(Text)
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id"), index=True)


class Friend(Base, TimestampMixin):
    __tablename__ = "friends"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    account_group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), index=True)
    tg_user_id: Mapped[str | None] = mapped_column(String(128), index=True)
    username: Mapped[str | None] = mapped_column(String(120), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    nickname: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    last_message_at: Mapped[str | None] = mapped_column(String(64))
    last_read_at: Mapped[str | None] = mapped_column(String(64))
    last_reply_at: Mapped[str | None] = mapped_column(String(64))
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
