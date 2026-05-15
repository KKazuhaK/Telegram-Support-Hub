from fastapi import APIRouter
from sqlalchemy import func, select

from backend.app.api.deps import DbSession
from backend.app.models.account import Account, AccountGroup
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


@router.get("/dashboard")
def dashboard(db: DbSession) -> dict:
    return {
        "accounts": {
            "total": count(db, Account),
            "active": count(db, Account, Account.status == "active", Account.enabled.is_(True)),
            "error": count(db, Account, Account.status.in_(["error", "limited", "proxy_error"])),
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
            "replied": count(db, Customer, Customer.status == "replied"),
        },
        "friends": {"total": count(db, Friend)},
        "campaigns": {
            "total": count(db, Campaign),
            "running": count(db, Campaign, Campaign.status == "running"),
        },
        "messages": {
            "queued": count(db, MessageRecord, MessageRecord.status == "queued"),
            "sent": count(db, MessageRecord, MessageRecord.status == "sent"),
            "failed": count(db, MessageRecord, MessageRecord.status.in_(["failed", "failed_permanent"])),
        },
    }
