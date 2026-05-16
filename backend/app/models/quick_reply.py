from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.mixins import TimestampMixin


class QuickReply(Base, TimestampMixin):
    """Canned chat reply ("话术") an operator can insert into the
    customer chat with one click.

    Two visibility modes:
      - is_public=True: shared across the org/tenant; only admins (and
        in future, merchants for their own scope) can edit.
      - is_public=False: personal — only the (actor_kind, actor_id) that
        owns the row can see / edit / delete it.

    `category` is a free-form tag (e.g. "开场白", "促单", "拒绝退款") so
    the UI can group them in the script panel.
    """

    __tablename__ = "quick_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Personal-script owner (only set when is_public=False).
    actor_kind: Mapped[str | None] = mapped_column(String(32), index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, index=True)
    # Optional tenant scope so a public script can belong only to one
    # merchant's universe (admins can still create global ones with this
    # set to NULL).
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
