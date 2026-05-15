from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from backend.app.api.deps import CurrentUserDep, DbSession
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission
from backend.app.models.campaign import Campaign
from backend.app.models.customer import Customer, Friend
from backend.app.models.message import MessageRecord
from backend.app.models.proxy import ProxyEndpoint
from backend.app.services.export import to_csv_stream
from backend.app.services.serializers import list_dict

router = APIRouter()


def count(db: DbSession, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    if where:
        stmt = stmt.where(*where)
    return int(db.scalar(stmt) or 0)


def _today_iso_prefix() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


@router.get("/dashboard")
def dashboard(db: DbSession, _: CurrentUserDep) -> dict:
    today = _today_iso_prefix()
    return {
        "accounts": {
            "total": count(db, Account),
            "active": count(db, Account, Account.status == "active", Account.enabled.is_(True)),
            "limited": count(db, Account, Account.status == "limited"),
            "error": count(db, Account, Account.status.in_(["error", "proxy_error"])),
            "imported_pending": count(db, Account, Account.status == "imported"),
        },
        "account_groups": {"total": count(db, AccountGroup)},
        "proxies": {
            "total": count(db, ProxyEndpoint),
            "active": count(db, ProxyEndpoint, ProxyEndpoint.status == "active"),
            "error": count(db, ProxyEndpoint, ProxyEndpoint.status == "error"),
        },
        "customers": {
            "total": count(db, Customer),
            "consented": count(db, Customer, Customer.consent.is_(True)),
            "assigned": count(db, Customer, Customer.status == "assigned"),
            "queued": count(db, Customer, Customer.status == "queued"),
            "replied": count(db, Customer, Customer.status == "replied"),
            "failed": count(db, Customer, Customer.status == "failed"),
        },
        "friends": {
            "total": count(db, Friend),
            "replied": count(db, Friend, Friend.status == "replied"),
            "opted_out": count(db, Friend, Friend.opted_out.is_(True)),
        },
        "campaigns": {
            "total": count(db, Campaign),
            "running": count(db, Campaign, Campaign.status == "running"),
            "paused": count(db, Campaign, Campaign.status == "paused"),
            "completed": count(db, Campaign, Campaign.status == "completed"),
        },
        "messages": {
            "queued": count(db, MessageRecord, MessageRecord.status.in_(["queued", "retry"])),
            "sending": count(db, MessageRecord, MessageRecord.status == "sending"),
            "sent": count(db, MessageRecord, MessageRecord.status == "sent"),
            "replied": count(db, MessageRecord, MessageRecord.status == "replied"),
            "failed": count(db, MessageRecord, MessageRecord.status.in_(["failed", "failed_permanent"])),
            "sent_today": count(db, MessageRecord, MessageRecord.sent_at.like(f"{today}%")),
        },
    }


@router.get("/accounts")
def per_account_stats(db: DbSession, _: CurrentUserDep) -> list[dict]:
    rows = list(db.scalars(select(Account).order_by(Account.id.asc())))
    out = []
    for acc in rows:
        sent = count(db, MessageRecord, MessageRecord.account_id == acc.id, MessageRecord.status == "sent")
        replied = count(db, MessageRecord, MessageRecord.account_id == acc.id, MessageRecord.status == "replied")
        failed = count(db, MessageRecord, MessageRecord.account_id == acc.id,
                       MessageRecord.status.in_(["failed", "failed_permanent"]))
        out.append({
            "account_id": acc.id,
            "tg_user_id": acc.tg_user_id,
            "phone": acc.phone,
            "status": acc.status,
            "enabled": acc.enabled,
            "daily_limit": acc.daily_limit,
            "sent_today": acc.sent_today,
            "total_sent": acc.total_sent,
            "total_replies": acc.total_replies,
            "msg_sent": sent,
            "msg_replied": replied,
            "msg_failed": failed,
            "reply_rate": (replied / sent) if sent else 0.0,
        })
    return out


@router.get("/account-groups")
def per_group_stats(db: DbSession, _: CurrentUserDep) -> list[dict]:
    groups = list(db.scalars(select(AccountGroup).order_by(AccountGroup.id.asc())))
    out = []
    for g in groups:
        member_ids = [m.account_id for m in db.scalars(
            select(AccountGroupMember).where(AccountGroupMember.group_id == g.id)
        )]
        if member_ids:
            sent = count(db, MessageRecord, MessageRecord.account_id.in_(member_ids),
                         MessageRecord.status == "sent")
            replied = count(db, MessageRecord, MessageRecord.account_id.in_(member_ids),
                            MessageRecord.status == "replied")
            failed = count(db, MessageRecord, MessageRecord.account_id.in_(member_ids),
                           MessageRecord.status.in_(["failed", "failed_permanent"]))
        else:
            sent = replied = failed = 0
        out.append({
            "group_id": g.id,
            "name": g.name,
            "code": g.code,
            "enabled": g.enabled,
            "daily_limit": g.daily_limit,
            "sent_today": g.sent_today,
            "account_count": len(member_ids),
            "msg_sent": sent,
            "msg_replied": replied,
            "msg_failed": failed,
            "reply_rate": (replied / sent) if sent else 0.0,
        })
    return out


@router.get("/support-agents")
def per_agent_stats(db: DbSession, _: CurrentUserDep) -> list[dict]:
    seven_days_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    today_prefix = _today_iso_prefix()
    agents = list(db.scalars(select(SupportAgent).order_by(SupportAgent.id.asc())))

    # Pre-load (agent_id, account_ids) so we don't issue 1+N queries.
    perm_rows = list(db.scalars(select(SupportAgentGroupPermission)))
    group_to_accounts: dict[int, list[int]] = {}
    for gid, in db.execute(select(AccountGroupMember.group_id).distinct()).all():
        group_to_accounts[gid] = [m.account_id for m in db.scalars(
            select(AccountGroupMember).where(AccountGroupMember.group_id == gid)
        )]
    agent_accounts: dict[int, set[int]] = {}
    for p in perm_rows:
        bucket = agent_accounts.setdefault(p.agent_id, set())
        bucket.update(group_to_accounts.get(p.account_group_id, []))

    out = []
    for agent in agents:
        recent_login = agent.last_login_at and agent.last_login_at >= seven_days_ago
        acc_ids = agent_accounts.get(agent.id, set())
        if acc_ids:
            today_sent = count(
                db, MessageRecord,
                MessageRecord.account_id.in_(acc_ids),
                MessageRecord.sent_at.like(f"{today_prefix}%"),
            )
            today_replied = count(
                db, MessageRecord,
                MessageRecord.account_id.in_(acc_ids),
                MessageRecord.replied_at.like(f"{today_prefix}%"),
            )
            today_read = count(
                db, MessageRecord,
                MessageRecord.account_id.in_(acc_ids),
                MessageRecord.read_at.like(f"{today_prefix}%"),
            )
        else:
            today_sent = today_replied = today_read = 0
        out.append({
            "agent_id": agent.id,
            "username": agent.username,
            "nickname": agent.nickname,
            "role": agent.role,
            "status": agent.status,
            "online_status": agent.online_status,
            "last_login_at": agent.last_login_at,
            "active_last_7d": bool(recent_login),
            "today_sent": today_sent,
            "today_replied": today_replied,
            "today_read": today_read,
            "today_reply_rate": (today_replied / today_sent) if today_sent else 0.0,
            "today_read_rate": (today_read / today_sent) if today_sent else 0.0,
        })
    return out


def _bucket_for(iso_str: str | None, bucket: str) -> str | None:
    """Return the date-bucket key for an ISO timestamp string.

    bucket=day  -> YYYY-MM-DD
    bucket=week -> YYYY-Www (ISO week)
    bucket=month -> YYYY-MM
    """
    if not iso_str or len(iso_str) < 10:
        return None
    if bucket == "month":
        return iso_str[:7]
    if bucket == "week":
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        except ValueError:
            return None
        year, week, _ = dt.isocalendar()
        return f"{year}-W{week:02d}"
    return iso_str[:10]


@router.get("/timeseries")
def timeseries(
    db: DbSession, _: CurrentUserDep,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    bucket: str = "day",
) -> dict:
    """Time-bucketed totals from message_records. `from` / `to` are inclusive
    YYYY-MM-DD strings; bucket is day | week | month.

    Counts are derived from the timestamps on each record:
    - sent: any record with sent_at in the window
    - read / replied: records with read_at / replied_at in the window
    - failed: records whose status is failed/failed_permanent dated by
      created_at (failed sends often lack a sent_at)
    """
    rows = list(db.scalars(select(MessageRecord)))
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"sent": 0, "read": 0, "replied": 0, "failed": 0}
    )

    def _in_range(key: str) -> bool:
        if from_date and key < from_date:
            return False
        if to_date and key > to_date:
            return False
        return True

    for r in rows:
        if r.sent_at:
            k = _bucket_for(r.sent_at, bucket)
            if k and _in_range(k):
                buckets[k]["sent"] += 1
        if r.read_at:
            k = _bucket_for(r.read_at, bucket)
            if k and _in_range(k):
                buckets[k]["read"] += 1
        if r.replied_at:
            k = _bucket_for(r.replied_at, bucket)
            if k and _in_range(k):
                buckets[k]["replied"] += 1
        if r.status in ("failed", "failed_permanent"):
            ref = r.sent_at or (r.created_at.isoformat() if r.created_at else None)
            k = _bucket_for(ref, bucket)
            if k and _in_range(k):
                buckets[k]["failed"] += 1

    bucket_list = [{"date": k, **buckets[k]} for k in sorted(buckets.keys())]
    totals = {
        "sent": sum(b["sent"] for b in bucket_list),
        "read": sum(b["read"] for b in bucket_list),
        "replied": sum(b["replied"] for b in bucket_list),
        "failed": sum(b["failed"] for b in bucket_list),
    }
    totals["read_rate"] = (totals["read"] / totals["sent"]) if totals["sent"] else 0
    totals["reply_rate"] = (totals["replied"] / totals["sent"]) if totals["sent"] else 0
    return {"buckets": bucket_list, "totals": totals}


@router.get("/message-details")
def message_details(
    db: DbSession, _: CurrentUserDep,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    status: str | None = None,
    task_id: int | None = None,
    account_id: int | None = None,
    limit: int = 100, offset: int = 0,
) -> list[dict]:
    stmt = select(MessageRecord).order_by(MessageRecord.id.desc())
    if status:
        stmt = stmt.where(MessageRecord.status == status)
    if task_id:
        stmt = stmt.where(MessageRecord.campaign_id == task_id)
    if account_id:
        stmt = stmt.where(MessageRecord.account_id == account_id)
    if from_date:
        stmt = stmt.where(MessageRecord.sent_at >= from_date)
    if to_date:
        # Treat to_date as inclusive end-of-day.
        stmt = stmt.where(MessageRecord.sent_at < f"{to_date}T23:59:60")
    return list_dict(list(db.scalars(stmt.offset(offset).limit(limit))))


def _timeseries_rows(buckets):
    yield ["date", "sent", "read", "replied", "failed"]
    for b in buckets:
        yield [str(b["date"]), str(b["sent"]), str(b["read"]),
               str(b["replied"]), str(b["failed"])]


@router.get("/timeseries.csv")
def export_timeseries(
    db: DbSession, _: CurrentUserDep,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    bucket: str = "day",
) -> StreamingResponse:
    """CSV equivalent of /api/statistics/timeseries — same buckets, no
    totals (totals are easy to compute downstream)."""
    data = timeseries(db, _, from_date=from_date, to_date=to_date, bucket=bucket)
    return StreamingResponse(
        to_csv_stream(_timeseries_rows(data["buckets"])),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=timeseries.csv"},
    )
