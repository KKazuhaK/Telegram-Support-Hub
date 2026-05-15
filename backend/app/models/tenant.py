from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.mixins import TimestampMixin


class BusinessAgent(Base, TimestampMixin):
    """商务代理 (PRD section 6).

    A business agent represents a reseller/partner that manages multiple
    merchants. Stored credentials (`password_hash`) allow a business agent
    to log in to a scoped view. For now we only persist the entity; full
    multi-tenant filtering will arrive in a later milestone.
    """

    __tablename__ = "business_agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    nickname: Mapped[str | None] = mapped_column(String(120))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    platform_name: Mapped[str | None] = mapped_column(String(120))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    custom_image_url: Mapped[str | None] = mapped_column(String(500))
    domains: Mapped[str | None] = mapped_column(Text)
    status: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    online_status: Mapped[str] = mapped_column(String(32), default="offline")
    last_login_at: Mapped[str | None] = mapped_column(String(64))
    remark: Mapped[str | None] = mapped_column(Text)


class Merchant(Base, TimestampMixin):
    """商户 (PRD section 7).

    A merchant ("商家账号") belongs to a business agent and consumes ports.
    Port resource semantics (PRD section 15.1-15.2): total ports allocated,
    expiry date, and a reset cycle that zeroes `ports_used` periodically.
    Reset bookkeeping is handled by a beat task; this model just records
    the current counters.
    """

    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_agent_id: Mapped[int | None] = mapped_column(ForeignKey("business_agents.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    nickname: Mapped[str | None] = mapped_column(String(120))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    online_status: Mapped[str] = mapped_column(String(32), default="offline")
    statistic_time: Mapped[str | None] = mapped_column(String(8), default="09:00")
    last_login_at: Mapped[str | None] = mapped_column(String(64))
    remark: Mapped[str | None] = mapped_column(Text)

    # Port allocation
    ports_total: Mapped[int] = mapped_column(Integer, default=0)
    ports_used: Mapped[int] = mapped_column(Integer, default=0)
    ports_expires_at: Mapped[str | None] = mapped_column(String(64))
    ports_reset_cycle_hours: Mapped[int] = mapped_column(Integer, default=24)
    ports_reset_at: Mapped[str | None] = mapped_column(String(64))
