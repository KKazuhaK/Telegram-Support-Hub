from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.account import Account
from backend.app.models.proxy import ProxyEndpoint


class PoolError(RuntimeError):
    """Raised when no proxy in the pool can be assigned."""


_PHONE_COUNTRY_PREFIX: dict[str, str] = {
    "+1": "US",
    "+7": "RU",
    "+33": "FR",
    "+44": "GB",
    "+49": "DE",
    "+81": "JP",
    "+82": "KR",
    "+86": "CN",
    "+852": "HK",
    "+853": "MO",
    "+886": "TW",
    "+91": "IN",
    "+92": "PK",
    "+62": "ID",
    "+63": "PH",
    "+65": "SG",
    "+66": "TH",
    "+84": "VN",
    "+971": "AE",
}


def country_from_phone(phone: str | None) -> str | None:
    if not phone or not phone.startswith("+"):
        return None
    for prefix in sorted(_PHONE_COUNTRY_PREFIX, key=len, reverse=True):
        if phone.startswith(prefix):
            return _PHONE_COUNTRY_PREFIX[prefix]
    return None


def _proxy_load(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Account.proxy_id, func.count(Account.id))
        .where(Account.proxy_id.isnot(None))
        .group_by(Account.proxy_id)
    ).all()
    return {int(r[0]): int(r[1]) for r in rows}


def _candidates(db: Session, group_id: int | None = None) -> list[ProxyEndpoint]:
    stmt = select(ProxyEndpoint).where(ProxyEndpoint.status == "active")
    if group_id is not None:
        stmt = stmt.where(ProxyEndpoint.group_id == group_id)
    return list(db.scalars(stmt.order_by(ProxyEndpoint.id.asc())))


def pick_proxy_for_account(
    db: Session, account: Account, *,
    prefer_country: str | None = None,
    group_id: int | None = None,
    max_per_proxy_override: int | None = None,
) -> ProxyEndpoint:
    """Return the best proxy for `account`. Selection order:

    1. status == active
    2. respects `max_accounts` cap (or `max_per_proxy_override` if set —
       useful for batch-import where the operator wants a tighter cap
       than each proxy's permanent `max_accounts` value)
    3. only proxies in `group_id` if provided (otherwise whole pool)
    4. matches `prefer_country` (if provided), else inferred from `account.phone`
    5. lowest current load (round-robin tie-break)
    """
    candidates = _candidates(db, group_id=group_id)
    if not candidates:
        raise PoolError("代理池中没有可用代理")

    load = _proxy_load(db)

    def _cap(p: ProxyEndpoint) -> int | None:
        if max_per_proxy_override is not None:
            # Take the stricter of (override, proxy's own cap) if both set.
            if p.max_accounts is not None:
                return min(max_per_proxy_override, p.max_accounts)
            return max_per_proxy_override
        return p.max_accounts

    available = [
        p for p in candidates
        if _cap(p) is None or load.get(p.id, 0) < _cap(p)
    ]
    if not available:
        raise PoolError("可用代理均已达到绑定上限")

    desired_country = prefer_country or country_from_phone(account.phone)
    if desired_country:
        country_match = [p for p in available if (p.country or "").upper() == desired_country.upper()]
        if country_match:
            available = country_match

    available.sort(key=lambda p: (load.get(p.id, 0), p.id))
    return available[0]


def auto_assign_proxy(
    db: Session, account: Account, *,
    prefer_country: str | None = None,
    group_id: int | None = None,
    max_per_proxy_override: int | None = None,
) -> ProxyEndpoint:
    """Pick + bind in one call. Returns the bound proxy."""
    proxy = pick_proxy_for_account(
        db, account, prefer_country=prefer_country,
        group_id=group_id, max_per_proxy_override=max_per_proxy_override,
    )
    account.proxy_id = proxy.id
    db.flush()
    return proxy
