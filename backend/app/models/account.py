from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base
from backend.app.models.mixins import TimestampMixin


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    session_path: Mapped[str] = mapped_column(String(500))
    proxy_id: Mapped[int | None] = mapped_column(ForeignKey("proxy_endpoints.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="imported", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_limit: Mapped[int] = mapped_column(Integer, default=40)
    sent_today: Mapped[int] = mapped_column(Integer, default=0)
    total_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_replies: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)
    nickname: Mapped[str | None] = mapped_column(String(120), index=True)
    country: Mapped[str | None] = mapped_column(String(8), index=True)
    remark: Mapped[str | None] = mapped_column(Text)
    avatar_status: Mapped[str | None] = mapped_column(String(32), index=True)
    # Multi-tenant scope (R1). Null = legacy / admin-managed account.
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id"), index=True)

    proxy = relationship("ProxyEndpoint", back_populates="accounts")
    groups = relationship("AccountGroupMember", back_populates="account", cascade="all, delete-orphan")


class AccountGroup(Base, TimestampMixin):
    __tablename__ = "account_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    code: Mapped[str | None] = mapped_column(String(80), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_limit: Mapped[int] = mapped_column(Integer, default=1000)
    sent_today: Mapped[int] = mapped_column(Integer, default=0)
    remark: Mapped[str | None] = mapped_column(Text)
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id"), index=True)

    members = relationship("AccountGroupMember", back_populates="group", cascade="all, delete-orphan")


class AccountGroupMember(Base, TimestampMixin):
    __tablename__ = "account_group_members"
    __table_args__ = (UniqueConstraint("account_id", "group_id", name="uq_account_group_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("account_groups.id"), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)

    account = relationship("Account", back_populates="groups")
    group = relationship("AccountGroup", back_populates="members")
