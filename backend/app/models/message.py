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
    # 'outbound' = sent by an operator/campaign; 'inbound' = received from
    # the customer/friend (recorded by listen_worker for chat-history use).
    direction: Mapped[str] = mapped_column(String(16), default="outbound", index=True)
    # Companion text in the other language:
    #   inbound row  -> Chinese translation of body_snapshot (cached
    #                   the first time the chat UI sees the message)
    #   outbound row -> original Chinese the operator typed, when the
    #                   message was sent with auto_translate=True
    # NULL when no translation has been performed.
    translation: Mapped[str | None] = mapped_column(Text)
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
    # Outbound image attachment uploaded via the chat box. Stored on the
    # backend filesystem under settings.session_dir / 'chat_attachments';
    # the path is relative to that dir so a future move of the storage
    # root only needs a config tweak. mime is what the UI uses to decide
    # how to render the bubble (img vs generic file link, later).
    attachment_path: Mapped[str | None] = mapped_column(String(255))
    attachment_mime: Mapped[str | None] = mapped_column(String(120))
