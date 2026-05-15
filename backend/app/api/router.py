from fastapi import APIRouter

from backend.app.api.routes import (
    account_groups,
    accounts,
    agents,
    audit,
    auth,
    campaigns,
    customers,
    export,
    files,
    proxies,
    stats,
    templates,
    ws,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
api_router.include_router(account_groups.router, prefix="/account-groups", tags=["account-groups"])
api_router.include_router(proxies.router, prefix="/proxies", tags=["proxies"])
api_router.include_router(agents.router, prefix="/support-agents", tags=["support-agents"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(templates.router, prefix="/message-templates", tags=["message-templates"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(stats.router, prefix="/statistics", tags=["statistics"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["audit-logs"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(ws.router, prefix="/ws", tags=["ws"])
