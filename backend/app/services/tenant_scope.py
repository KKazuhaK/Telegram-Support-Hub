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
