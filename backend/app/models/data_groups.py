from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.mixins import TimestampMixin


class PhoneGroup(Base, TimestampMixin):
    __tablename__ = "phone_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    # `name` is no longer globally unique — two merchants may both have a
    # group called "EU"; uniqueness is enforced per-merchant at the app
    # layer instead.
    name: Mapped[str] = mapped_column(String(120), index=True)
    country: Mapped[str | None] = mapped_column(String(8), index=True)
    remark: Mapped[str | None] = mapped_column(Text)
    daily_limit: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id"), index=True)


class Phone(Base, TimestampMixin):
    __tablename__ = "phones"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("phone_groups.id"), index=True)
    number: Mapped[str] = mapped_column(String(40), index=True)
    used: Mapped[bool] = mapped_column(default=False, index=True)
    fmt: Mapped[str | None] = mapped_column(String(40))
    remark: Mapped[str | None] = mapped_column(Text)


class MaterialGroup(Base, TimestampMixin):
    __tablename__ = "material_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Per-merchant uniqueness; see PhoneGroup note above.
    name: Mapped[str] = mapped_column(String(120), index=True)
    # 'text' | 'image' | 'voice'
    kind: Mapped[str] = mapped_column(String(32), default="text", index=True)
    remark: Mapped[str | None] = mapped_column(Text)
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id"), index=True)


class Material(Base, TimestampMixin):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("material_groups.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    # For non-text materials, store the uploaded file's relative path; null for text.
    file_path: Mapped[str | None] = mapped_column(String(500))
    remark: Mapped[str | None] = mapped_column(Text)


class ProxyGroup(Base, TimestampMixin):
    __tablename__ = "proxy_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    remark: Mapped[str | None] = mapped_column(Text)
