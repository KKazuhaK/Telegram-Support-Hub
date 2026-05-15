from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.account import Account, AccountGroupMember
from backend.app.models.campaign import Campaign
from backend.app.models.message import MessageRecord
from backend.app.models.template import MessageTemplate
from backend.app.services.template_engine import render_message


def _accounts_for_groups(db: Session, group_ids: list[int]) -> list[Account]:
    if not group_ids:
        return list(
            db.scalars(select(Account).where(Account.enabled.is_(True), Account.status.in_(["active", "imported"])))
        )
    member_subq = select(AccountGroupMember.account_id).where(AccountGroupMember.group_id.in_(group_ids))
    return list(
        db.scalars(
            select(Account).where(
                Account.enabled.is_(True),
                Account.status.in_(["active", "imported"]),
                Account.id.in_(member_subq),
            )
        )
    )


def _render(body: str, name: str | None, phone: str | None, source: str):
    return render_message(body, {"name": name, "phone": phone, "source": source})


def build_imported_target_records(
    db: Session,
    campaign: Campaign,
    template: MessageTemplate,
    account_group_ids: list[int],
    targets: Iterable[dict],
    *,
    source: str = "imported",
) -> int:
    """Create MessageRecord rows for an ad-hoc import (phone or @username).

    `targets` is an iterable of dicts with at least one of `phone`, `username`,
    optionally `name`. Round-robin distributes across eligible accounts in the
    selected groups. Returns count of records created.
    """
    accounts = _accounts_for_groups(db, account_group_ids)
    if not accounts:
        return 0

    now_iso = datetime.now(UTC).isoformat()
    cursor = 0
    created = 0
    for raw in targets:
        phone = (raw.get("phone") or "").strip() or None
        username = (raw.get("username") or "").strip() or None
        name = raw.get("name")
        if not phone and not username:
            continue
        account = accounts[cursor % len(accounts)]
        cursor += 1
        rendered = _render(template.body, name, phone, source)
        db.add(MessageRecord(
            campaign_id=campaign.id,
            account_id=account.id,
            phone=phone,
            target_tg_user_id=username,
            body_snapshot=rendered.text,
            entities=rendered.entities or None,
            status="queued",
            next_run_at=now_iso,
        ))
        created += 1
    return created
