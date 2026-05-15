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


def _candidates(db: Session) -> list[ProxyEndpoint]:
    return list(db.scalars(select(ProxyEndpoint).where(ProxyEndpoint.status == "active").order_by(ProxyEndpoint.id.asc())))


def pick_proxy_for_account(
    db: Session, account: Account, *, prefer_country: str | None = None
) -> ProxyEndpoint:
    """Return the best proxy for `account`. Selection order:

    1. status == active
    2. respects `max_accounts` cap
    3. matches `prefer_country` (if provided), else inferred from `account.phone`
    4. lowest current load (round-robin tie-break)
    """
    candidates = _candidates(db)
    if not candidates:
        raise PoolError("no active proxies in pool")

    load = _proxy_load(db)
    available = [
        p for p in candidates
        if p.max_accounts is None or load.get(p.id, 0) < p.max_accounts
    ]
    if not available:
        raise PoolError("all active proxies at capacity")

    desired_country = prefer_country or country_from_phone(account.phone)
    if desired_country:
        country_match = [p for p in available if (p.country or "").upper() == desired_country.upper()]
        if country_match:
            available = country_match

    available.sort(key=lambda p: (load.get(p.id, 0), p.id))
    return available[0]


def auto_assign_proxy(db: Session, account: Account, *, prefer_country: str | None = None) -> ProxyEndpoint:
    """Pick + bind in one call. Returns the bound proxy."""
    proxy = pick_proxy_for_account(db, account, prefer_country=prefer_country)
    account.proxy_id = proxy.id
    db.flush()
    return proxy
