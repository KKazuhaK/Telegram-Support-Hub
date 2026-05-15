from __future__ import annotations

import csv
import io
from typing import Iterable, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.customer import Customer
from backend.app.models.message import MessageRecord


def _bool_str(value) -> str:
    if value is None:
        return ""
    return "true" if bool(value) else "false"


def customers_csv_rows(db: Session, *, status: str | None = None) -> Iterator[list[str]]:
    yield ["id", "phone", "name", "tags", "source", "consent", "status", "assigned_account_id", "last_reply_at"]
    stmt = select(Customer).order_by(Customer.id.asc())
    if status:
        stmt = stmt.where(Customer.status == status)
    for c in db.scalars(stmt):
        yield [
            str(c.id),
            c.phone or "",
            c.name or "",
            "|".join(c.tags or []),
            c.source or "",
            _bool_str(c.consent),
            c.status or "",
            str(c.assigned_account_id or ""),
            c.last_reply_at or "",
        ]


def messages_csv_rows(db: Session, *, campaign_id: int | None = None) -> Iterator[list[str]]:
    yield ["id", "campaign_id", "account_id", "customer_id", "friend_id", "phone", "status", "sent_at", "replied_at", "error_code", "error_message"]
    stmt = select(MessageRecord).order_by(MessageRecord.id.asc())
    if campaign_id is not None:
        stmt = stmt.where(MessageRecord.campaign_id == campaign_id)
    for m in db.scalars(stmt):
        yield [
            str(m.id),
            str(m.campaign_id or ""),
            str(m.account_id or ""),
            str(m.customer_id or ""),
            str(m.friend_id or ""),
            m.phone or "",
            m.status or "",
            m.sent_at or "",
            m.replied_at or "",
            m.error_code or "",
            (m.error_message or "").replace("\n", " "),
        ]


def to_csv_stream(rows: Iterable[list[str]]) -> Iterator[bytes]:
    """Yield UTF-8 BOM + CSV chunks for streaming response. The BOM helps
    Excel detect the encoding."""
    yield b"\xef\xbb\xbf"
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
        chunk = buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        yield chunk.encode("utf-8")
