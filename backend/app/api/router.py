from fastapi import APIRouter

from backend.app.api.routes import (
    account_groups,
    accounts,
    agents,
    audit,
    auth,
    business_agents,
    campaigns,
    customers,
    export,
    files,
    materials,
    materials_items,
    merchants,
    phones,
    phones_items,
    proxies,
    proxy_groups,
    stats,
    templates,
    ws,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
api_router.include_router(account_groups.router, prefix="/account-groups", tags=["account-groups"])
api_router.include_router(proxies.router, prefix="/proxies", tags=["proxies"])
api_router.include_router(proxy_groups.router, prefix="/proxy-groups", tags=["proxy-groups"])
api_router.include_router(agents.router, prefix="/support-agents", tags=["support-agents"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(templates.router, prefix="/message-templates", tags=["message-templates"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(stats.router, prefix="/statistics", tags=["statistics"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["audit-logs"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(phones.router, prefix="/phone-groups", tags=["phone-groups"])
api_router.include_router(phones_items.router, prefix="/phones", tags=["phones"])
api_router.include_router(materials.router, prefix="/material-groups", tags=["material-groups"])
api_router.include_router(materials_items.router, prefix="/materials", tags=["materials"])
api_router.include_router(business_agents.router, prefix="/business-agents", tags=["business-agents"])
api_router.include_router(merchants.router, prefix="/merchants", tags=["merchants"])
api_router.include_router(ws.router, prefix="/ws", tags=["ws"])
