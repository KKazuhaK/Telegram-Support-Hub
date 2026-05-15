from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.api.deps import AdminDep, DbSession
from backend.app.core.crypto import encrypt_secret
from backend.app.models.proxy import ProxyEndpoint
from backend.app.services.audit import write_audit
from backend.app.services.proxy_checker import check_tcp
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


class ProxyCreate(BaseModel):
    name: str
    protocol: str = "socks5"
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    country: str | None = None
    max_accounts: int | None = None
    remark: str | None = None


class ProxyUpdate(BaseModel):
    name: str | None = None
    protocol: str | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    country: str | None = None
    status: str | None = None
    max_accounts: int | None = None
    remark: str | None = None


@router.get("")
def list_proxies(db: DbSession, _: AdminDep) -> list[dict]:
    return list_dict(list(db.scalars(select(ProxyEndpoint).order_by(ProxyEndpoint.id.desc()))))


@router.post("")
def create_proxy(payload: ProxyCreate, db: DbSession, admin: AdminDep) -> dict:
    proxy = ProxyEndpoint(
        name=payload.name,
        protocol=payload.protocol,
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password_encrypted=encrypt_secret(payload.password),
        country=payload.country,
        max_accounts=payload.max_accounts,
        remark=payload.remark,
    )
    db.add(proxy)
    db.flush()
    write_audit(db, actor=admin, action="proxy.create", target_type="proxy",
                target_id=proxy.id, detail={"host": proxy.host, "port": proxy.port, "protocol": proxy.protocol})
    db.commit()
    db.refresh(proxy)
    return to_dict(proxy)


@router.patch("/{proxy_id}")
def update_proxy(proxy_id: int, payload: ProxyUpdate, db: DbSession, admin: AdminDep) -> dict:
    proxy = db.get(ProxyEndpoint, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="proxy not found")
    values = payload.model_dump(exclude_unset=True)
    if "password" in values:
        values["password_encrypted"] = encrypt_secret(values.pop("password"))
    for key, value in values.items():
        setattr(proxy, key, value)
    safe_detail = {k: ("***" if k == "password_encrypted" else v) for k, v in values.items()}
    write_audit(db, actor=admin, action="proxy.update", target_type="proxy",
                target_id=proxy.id, detail=safe_detail)
    db.commit()
    db.refresh(proxy)
    return to_dict(proxy)


@router.post("/{proxy_id}/check")
def check_proxy(proxy_id: int, db: DbSession, _: AdminDep) -> dict:
    proxy = db.get(ProxyEndpoint, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="proxy not found")

    result = check_tcp(proxy.host, proxy.port)
    proxy.status = "active" if result.ok else "error"
    proxy.latency_ms = result.latency_ms
    proxy.last_error = result.error
    proxy.last_checked_at = datetime.now(UTC).isoformat()
    db.commit()
    db.refresh(proxy)
    return to_dict(proxy)
