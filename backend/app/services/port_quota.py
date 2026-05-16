"""Port quota enforcement (R2).

PRD 15.1-15.2: each merchant has `ports_total` (allocation), `ports_used`
(live count of active accounts) and `ports_expires_at`. Activating an
account consumes a port; exceeding the quota or operating past expiry
must be rejected.

`ports_total = 0` is treated as **unlimited** so legacy merchants without
configured quota don't get locked out — the field starts at 0 by default.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.account import Account
from backend.app.models.tenant import Merchant


class QuotaError(Exception):
    """Raised when an activation would breach the merchant's port quota
    or the merchant's allocation has expired."""

    def __init__(self, message: str, *, code: str = "quota_exceeded") -> None:
        super().__init__(message)
        self.code = code


def _count_active(db: Session, merchant_id: int) -> int:
    n = db.scalar(
        select(func.count())
        .select_from(Account)
        .where(Account.merchant_id == merchant_id, Account.status == "active")
    )
    return int(n or 0)


def recompute_merchant_ports(db: Session, merchant_id: int) -> int:
    """Set `ports_used` to the live active-account count and return it."""
    used = _count_active(db, merchant_id)
    m = db.get(Merchant, merchant_id)
    if m is not None:
        m.ports_used = used
        db.commit()
    return used


def check_quota_for_activation(
    db: Session, merchant_id: int | None, *, additional: int = 1
) -> None:
    """Raise QuotaError if activating `additional` more accounts would
    exceed the merchant's quota or fall past expiry. No-op when
    merchant_id is None (admin-managed accounts)."""
    if not merchant_id:
        return
    m = db.get(Merchant, merchant_id)
    if m is None:
        return

    if m.ports_expires_at:
        try:
            expires = datetime.fromisoformat(m.ports_expires_at)
        except ValueError:
            expires = None
        if expires is not None and expires < datetime.now(UTC):
            raise QuotaError(
                f"商户『{m.name}』的端口配额已过期（{m.ports_expires_at}），请续期后再启用账号",
                code="quota_expired",
            )

    if m.ports_total <= 0:
        return  # unlimited

    used = _count_active(db, merchant_id)
    if used + additional > m.ports_total:
        raise QuotaError(
            f"商户『{m.name}』端口配额不足：已使用 {used}/{m.ports_total}，"
            f"无法再启用 {additional} 个账号",
            code="quota_exceeded",
        )
