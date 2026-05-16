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
