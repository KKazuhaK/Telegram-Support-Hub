from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from backend.app.api.deps import CurrentUserDep, DbSession
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.agent import SupportAgent
from backend.app.models.campaign import Campaign
from backend.app.models.customer import Customer, Friend
from backend.app.models.message import MessageRecord
from backend.app.models.proxy import ProxyEndpoint

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
    agents = list(db.scalars(select(SupportAgent).order_by(SupportAgent.id.asc())))
    out = []
    for agent in agents:
        recent_login = agent.last_login_at and agent.last_login_at >= seven_days_ago
        out.append({
            "agent_id": agent.id,
            "username": agent.username,
            "nickname": agent.nickname,
            "role": agent.role,
            "status": agent.status,
            "online_status": agent.online_status,
            "last_login_at": agent.last_login_at,
            "active_last_7d": bool(recent_login),
        })
    return out
