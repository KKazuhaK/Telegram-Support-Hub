from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.account import Account, AccountGroupMember
from backend.app.models.customer import Customer

ELIGIBLE_ACCOUNT_STATUS = {"active", "imported"}


def _accounts_in_groups(db: Session, group_ids: list[int] | None) -> list[Account]:
    stmt = select(Account).where(Account.enabled.is_(True), Account.status.in_(ELIGIBLE_ACCOUNT_STATUS))
    if group_ids:
        member_subq = select(AccountGroupMember.account_id).where(AccountGroupMember.group_id.in_(group_ids))
        stmt = stmt.where(Account.id.in_(member_subq))
    return list(db.scalars(stmt))


def _current_load(db: Session, account_ids: Iterable[int]) -> dict[int, int]:
    if not account_ids:
        return {}
    rows = db.execute(
        select(Customer.assigned_account_id, func.count(Customer.id))
        .where(Customer.assigned_account_id.in_(list(account_ids)))
        .group_by(Customer.assigned_account_id)
    ).all()
    return {int(row[0]): int(row[1]) for row in rows if row[0] is not None}


def assign_customers(
    db: Session,
    *,
    customer_ids: list[int] | None = None,
    account_group_ids: list[int] | None = None,
    max_per_account: int | None = None,
    only_unassigned: bool = True,
) -> dict:
    """Round-robin assignment with optional per-account cap.

    - Filters accounts to those in `account_group_ids` (None = all eligible).
    - Skips accounts that are not enabled or whose status is not active/imported.
    - If `customer_ids` is omitted, assigns all consented + unassigned customers.
    """
    accounts = _accounts_in_groups(db, account_group_ids)
    if not accounts:
        return {"assigned": 0, "skipped": 0, "reason": "no_eligible_accounts"}

    customer_q = select(Customer).where(Customer.consent.is_(True))
    if only_unassigned:
        customer_q = customer_q.where(Customer.assigned_account_id.is_(None))
    if customer_ids:
        customer_q = customer_q.where(Customer.id.in_(customer_ids))
    customers = list(db.scalars(customer_q.order_by(Customer.id.asc())))

    if not customers:
        return {"assigned": 0, "skipped": 0, "reason": "no_eligible_customers"}

    load = _current_load(db, [acc.id for acc in accounts])
    per_account: dict[int, list[int]] = defaultdict(list)
    cursor = 0
    assigned = 0
    skipped = 0

    for customer in customers:
        attempts = 0
        placed = False
        while attempts < len(accounts):
            account = accounts[cursor % len(accounts)]
            cursor += 1
            attempts += 1
            current = load.get(account.id, 0) + len(per_account[account.id])
            if max_per_account is not None and current >= max_per_account:
                continue
            customer.assigned_account_id = account.id
            customer.status = "assigned"
            per_account[account.id].append(customer.id)
            assigned += 1
            placed = True
            break
        if not placed:
            skipped += 1

    db.flush()
    return {
        "assigned": assigned,
        "skipped": skipped,
        "per_account": {acc_id: len(ids) for acc_id, ids in per_account.items()},
    }
