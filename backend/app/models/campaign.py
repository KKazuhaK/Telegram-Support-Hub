from sqlalchemy import ForeignKey, JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.mixins import TimestampMixin


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    template_id: Mapped[int | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    # Task family. Existing rows default to "broadcast" to stay backwards
    # compatible with the campaigns / friend / imported flows.
    task_kind: Mapped[str] = mapped_column(String(32), default="broadcast", index=True)
    # The specific action within the family — for broadcast this is the
    # message target (customer_broadcast / friend_broadcast / etc.); for
    # batch_op it is delete_friend / leave_group / etc.; for modify_info it
    # is modify_password / modify_avatar / etc.
    operation_target: Mapped[str] = mapped_column(String(40), default="customer_broadcast")
    # Backwards-compat alias kept for code that still reads target_type.
    target_type: Mapped[str] = mapped_column(String(40), default="customer_broadcast")
    account_group_ids: Mapped[list | None] = mapped_column(JSON)
    customer_group_id: Mapped[int | None] = mapped_column(index=True)
    friend_filter: Mapped[dict | None] = mapped_column(JSON)
    send_settings: Mapped[dict | None] = mapped_column(JSON)
    # Free-form per-action parameters: file_group_id, old_password, new
    # nickname/username/bio value, etc. Schema is defined at the API layer.
    extra_params: Mapped[dict | None] = mapped_column(JSON)
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    queued_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    read_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[str | None] = mapped_column(String(64))
    paused_at: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[str | None] = mapped_column(String(64))
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id"), index=True)
