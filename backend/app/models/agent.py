from sqlalchemy import Boolean, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.mixins import TimestampMixin


class SupportAgent(Base, TimestampMixin):
    __tablename__ = "support_agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    nickname: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), default="enabled")
    online_status: Mapped[str] = mapped_column(String(32), default="offline")
    last_login_at: Mapped[str | None] = mapped_column(String(64))


class SupportAgentGroupPermission(Base, TimestampMixin):
    __tablename__ = "support_agent_group_permissions"
    __table_args__ = (UniqueConstraint("agent_id", "account_group_id", name="uq_agent_account_group"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("support_agents.id"), index=True)
    account_group_id: Mapped[int] = mapped_column(ForeignKey("account_groups.id"), index=True)
    can_view_friends: Mapped[bool] = mapped_column(Boolean, default=True)
    can_view_chats: Mapped[bool] = mapped_column(Boolean, default=True)
    can_send_message: Mapped[bool] = mapped_column(Boolean, default=True)
    can_broadcast: Mapped[bool] = mapped_column(Boolean, default=False)
    can_edit_profile: Mapped[bool] = mapped_column(Boolean, default=False)
    can_delete_friend: Mapped[bool] = mapped_column(Boolean, default=False)
    can_clear_chat: Mapped[bool] = mapped_column(Boolean, default=False)
    chat_scope: Mapped[dict | None] = mapped_column(JSON)
