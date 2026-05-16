"""Tenant scope helpers (R1).

Centralizes the visibility rules so list endpoints stay declarative:

    stmt = apply_merchant_scope(stmt, user, db, Account)

Returns the statement unchanged for support_agent actors (admin sees all
data, including legacy rows where `merchant_id IS NULL`). For merchant /
business_agent actors, applies a `merchant_id IN (...)` filter.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.tenant import Merchant


def visible_merchant_ids(user, db: Session) -> list[int] | None:
    """Return the list of merchant_ids this actor may see, or None for
    "see everything" (admin scope)."""
    if user.actor_kind == "support_agent":
        return None
    if user.actor_kind == "merchant":
        return [user.actor_id]
    if user.actor_kind == "business_agent":
        ids = list(
            db.scalars(
                select(Merchant.id).where(Merchant.business_agent_id == user.actor_id)
            )
        )
        return ids
    return []


def apply_merchant_scope(stmt, user, db: Session, model):
    ids = visible_merchant_ids(user, db)
    if ids is None:
        return stmt
    if not ids:
        return stmt.where(model.id == -1)
    return stmt.where(model.merchant_id.in_(ids))


def default_merchant_id(user) -> int | None:
    """Return the `merchant_id` to stamp on rows that this actor creates.

    - support_agent (admin / supervisor / agent): None (legacy bucket;
      admin can later re-assign via batch edit if needed).
    - merchant: own actor_id — the row belongs to the caller's tenant.
    - business_agent: None — BAs don't own data, they oversee merchants.
      A future create-on-behalf-of-merchant flow would pass merchant_id
      explicitly, not via this auto-fill helper.
    """
    return user.actor_id if user.actor_kind == "merchant" else None


def can_write_tenant_data(user) -> bool:
    """Whether this actor may create / mutate tenant-scoped rows
    (customers, campaigns) on its own merchant. Decoupled from the
    per-group `can_broadcast` permission used inside the support_agent
    scope, because tenant actors don't go through that permission table."""
    if user.actor_kind == "merchant":
        return True
    if user.actor_kind == "support_agent":
        return user.is_admin or user.can("can_broadcast")
    # business_agent reads but doesn't write tenant data.
    return False


# Operational health fields the tenant (merchant / business_agent) is
# deliberately not allowed to see — knowing which TG accounts are dead
# or when the platform is back-filling inventory would expose internal
# operations. Strip these from any account-shaped dict before returning
# to a non-support_agent caller.
TG_HEALTH_FIELDS = frozenset({
    "status", "last_error", "last_login_at", "enabled", "avatar_status",
})


def sanitize_account_for_tenant(user, data: dict) -> dict:
    """Drop TG health fields when the caller is not a support_agent.
    Operates on plain dicts (post-`to_dict`) so it's cheap to apply to
    list responses without touching ORM state."""
    if user.actor_kind == "support_agent":
        return data
    return {k: v for k, v in data.items() if k not in TG_HEALTH_FIELDS}


def can_access_row(user, db: Session, row) -> bool:
    """Return True if `user` is allowed to read/mutate `row`. Used by
    PATCH/DELETE/lifecycle endpoints to block cross-tenant IDOR.

    A row is accessible when:
      - the caller is a support_agent (admin tool scope), OR
      - the row has no `merchant_id` (legacy / admin-managed), AND the
        caller is a support_agent — for tenant actors a NULL row is NOT
        theirs and must be hidden, OR
      - the row's `merchant_id` is in the caller's visible merchant set.
    """
    if user.actor_kind == "support_agent":
        return True
    row_merchant_id = getattr(row, "merchant_id", None)
    if row_merchant_id is None:
        return False
    ids = visible_merchant_ids(user, db) or []
    return row_merchant_id in ids
