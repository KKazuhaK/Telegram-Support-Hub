"""Inbound messages whose sender doesn't match any Customer row.

When listen_worker captures an inbound Telegram message and can't
find a Customer by phone, it still persists the MessageRecord with
`customer_id=NULL`. The main 回复管理 page filters by customer, so
these reach the DB but never reach the operator — exactly the
'我测试发了消息但收不到回复' scenario.

This module exposes:
  GET  /api/orphan-threads          — list distinct senders
  GET  /api/orphan-threads/messages — full history for one sender
  POST /api/orphan-threads/promote  — turn the sender into a Customer

Admin-only for now: these are operational diagnostics, not for tenant
self-service.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from backend.app.api.deps import AdminDep, DbSession
from backend.app.models.account import Account
from backend.app.models.customer import Customer
from backend.app.models.message import MessageRecord
from backend.app.services.audit import write_audit
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


def _rescan_and_retag_promoted(db) -> int:
    """Catch-up scan: any orphan message whose target_tg_user_id matches
    an existing Customer whose phone is the `tg:<id>` placeholder gets
    retagged to that customer. Closes the window where the listen_worker
    matched only by real phone and dropped messages from a
    promoted-from-orphan sender back into the orphan bucket. Returns
    the number of rows retagged."""
    # Find orphan inbound rows that have a numeric target_tg_user_id and
    # whose `tg:<id>` placeholder matches a real customer row.
    orphans = list(db.scalars(
        select(MessageRecord)
        .where(MessageRecord.customer_id.is_(None))
        .where(MessageRecord.direction == "inbound")
        .where(MessageRecord.target_tg_user_id.isnot(None))
    ))
    if not orphans:
        return 0
    # Build a (placeholder_phone -> customer_id) lookup in one query.
    placeholders = {f"tg:{m.target_tg_user_id}" for m in orphans}
    matched = {
        c.phone: c.id for c in db.scalars(
            select(Customer).where(Customer.phone.in_(placeholders))
        )
    }
    retagged = 0
    for m in orphans:
        cid = matched.get(f"tg:{m.target_tg_user_id}")
        if cid:
            m.customer_id = cid
            retagged += 1
    if retagged:
        db.commit()
    return retagged


@router.get("")
def list_orphan_threads(db: DbSession, _: AdminDep, limit: int = 200) -> list[dict]:
    """One row per distinct (account_id, sender) thread, latest first.
    Sender identity = COALESCE(target_tg_user_id, phone). The UI uses
    these as the left-sidebar entries when the operator switches to
    the 未匹配 tab.

    Side-effect: opportunistic rescan that retags any orphan whose
    sender tg_user_id matches an existing promoted-from-orphan
    customer. Cheap and self-healing.
    """
    _rescan_and_retag_promoted(db)
    # Build sub-aggregation: per (account_id, target_tg_user_id, phone),
    # max sent_at + count + last message text.
    aggregated = (
        select(
            MessageRecord.account_id,
            MessageRecord.target_tg_user_id,
            MessageRecord.phone,
            func.max(MessageRecord.sent_at).label("last_at"),
            func.count(MessageRecord.id).label("msg_count"),
        )
        .where(
            MessageRecord.direction == "inbound",
            MessageRecord.customer_id.is_(None),
        )
        .group_by(
            MessageRecord.account_id,
            MessageRecord.target_tg_user_id,
            MessageRecord.phone,
        )
        .order_by(desc("last_at"))
        .limit(limit)
        .subquery()
    )
    rows = list(db.execute(select(aggregated)).all())
    # Fetch the latest message text per group (simpler than window funcs).
    out: list[dict] = []
    for r in rows:
        latest = db.scalar(
            select(MessageRecord)
            .where(
                MessageRecord.direction == "inbound",
                MessageRecord.customer_id.is_(None),
                MessageRecord.account_id == r.account_id,
                MessageRecord.target_tg_user_id == r.target_tg_user_id,
                MessageRecord.phone == r.phone,
            )
            .order_by(MessageRecord.id.desc())
            .limit(1)
        )
        out.append({
            "account_id": r.account_id,
            "target_tg_user_id": r.target_tg_user_id,
            "phone": r.phone,
            "last_at": r.last_at,
            "msg_count": int(r.msg_count or 0),
            "last_snippet": (latest.body_snapshot or "")[:200] if latest else "",
        })
    return out


@router.get("/messages")
def list_orphan_messages(
    db: DbSession, _: AdminDep,
    account_id: int,
    target_tg_user_id: str | None = None,
    phone: str | None = None,
    limit: int = 200, offset: int = 0,
) -> list[dict]:
    """Conversation history for one orphan thread. Must specify
    `account_id` plus at least one of `target_tg_user_id` / `phone`.
    Returns both directions ordered chronologically — same shape as
    /customers/{id}/messages."""
    if not target_tg_user_id and not phone:
        raise HTTPException(
            status_code=400,
            detail="必须提供 target_tg_user_id 或 phone",
        )
    stmt = (
        select(MessageRecord)
        .where(MessageRecord.account_id == account_id)
        .where(MessageRecord.customer_id.is_(None))
    )
    if target_tg_user_id:
        stmt = stmt.where(MessageRecord.target_tg_user_id == target_tg_user_id)
    if phone:
        stmt = stmt.where(MessageRecord.phone == phone)
    stmt = stmt.order_by(MessageRecord.created_at.asc(), MessageRecord.id.asc())
    rows = list(db.scalars(stmt.offset(offset).limit(limit)))
    return list_dict(rows)


class PromotePayload(BaseModel):
    account_id: int
    phone: str | None = None
    target_tg_user_id: str | None = None
    name: str | None = None  # display name to put on the new Customer


@router.post("/promote")
def promote_to_customer(
    payload: PromotePayload, db: DbSession, admin: AdminDep,
) -> dict:
    """One-click 'turn this orphan conversation into a Customer'.
    Creates a Customer row (consent=true; admin is taking responsibility)
    and re-tags all matching orphan MessageRecord rows so the thread
    moves into the regular 客户 tab.
    """
    if not payload.phone and not payload.target_tg_user_id:
        raise HTTPException(
            status_code=400,
            detail="必须提供 phone 或 target_tg_user_id",
        )

    # Phone is the Customer's unique key, so we need *something* — fall
    # back to a placeholder like 'tg:<id>' when the sender only gave us
    # a numeric tg_user_id (no phone visible).
    phone = payload.phone or f"tg:{payload.target_tg_user_id}"
    if db.scalar(select(Customer).where(Customer.phone == phone)):
        raise HTTPException(
            status_code=409,
            detail=f"客户 {phone} 已存在，无需重复创建",
        )

    cust = Customer(
        phone=phone,
        name=payload.name or phone,
        consent=True,
        status="assigned",
        assigned_account_id=payload.account_id,
        source="promoted_from_orphan",
    )
    db.add(cust)
    db.flush()

    # Re-tag the orphan messages.
    matches = list(db.scalars(
        select(MessageRecord)
        .where(MessageRecord.account_id == payload.account_id)
        .where(MessageRecord.customer_id.is_(None))
        .where(
            (MessageRecord.target_tg_user_id == payload.target_tg_user_id)
            if payload.target_tg_user_id else
            (MessageRecord.phone == payload.phone)
        )
    ))
    for m in matches:
        m.customer_id = cust.id

    write_audit(
        db, actor=admin, action="orphan_thread.promote",
        target_type="customer", target_id=cust.id,
        detail={"account_id": payload.account_id, "phone": payload.phone,
                "target_tg_user_id": payload.target_tg_user_id,
                "messages_retagged": len(matches)},
    )
    db.commit()
    db.refresh(cust)
    return {"customer": to_dict(cust), "messages_retagged": len(matches)}
