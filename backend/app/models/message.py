from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.mixins import TimestampMixin


class MessageRecord(Base, TimestampMixin):
    __tablename__ = "message_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    friend_id: Mapped[int | None] = mapped_column(ForeignKey("friends.id"), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    body_snapshot: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    sent_at: Mapped[str | None] = mapped_column(String(64))
    read_at: Mapped[str | None] = mapped_column(String(64))
    replied_at: Mapped[str | None] = mapped_column(String(64))
    reply_text: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    next_run_at: Mapped[str | None] = mapped_column(String(64), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_by: Mapped[str | None] = mapped_column(String(120))
    locked_at: Mapped[str | None] = mapped_column(String(64))
    external_message_id: Mapped[str | None] = mapped_column(String(64), index=True)
    target_tg_user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    entities: Mapped[list | None] = mapped_column(JSON)
