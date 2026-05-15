from datetime import UTC, datetime

from sqlalchemy import select

from backend.app.core.database import SessionLocal
from backend.app.models.proxy import ProxyEndpoint
from backend.app.services.proxy_checker import check_tcp
from backend.app.workers.celery_app import celery_app


@celery_app.task(name="backend.app.workers.account_tasks.check_all_proxies")
def check_all_proxies() -> dict:
    checked = 0
    with SessionLocal() as db:
        proxies = list(db.scalars(select(ProxyEndpoint).where(ProxyEndpoint.status != "disabled")))
        for proxy in proxies:
            result = check_tcp(proxy.host, proxy.port)
            proxy.status = "active" if result.ok else "error"
            proxy.latency_ms = result.latency_ms
            proxy.last_error = result.error
            proxy.last_checked_at = datetime.now(UTC).isoformat()
            checked += 1
        db.commit()
    return {"checked": checked}


@celery_app.task(name="backend.app.workers.account_tasks.validate_all_sessions")
def validate_all_sessions() -> dict:
    # Real Telethon validation will be implemented in TelegramAdapter.
    return {"validated": 0, "status": "not_implemented"}
