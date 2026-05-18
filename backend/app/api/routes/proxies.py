from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.app.api.deps import AdminDep, DbSession
from backend.app.core.crypto import encrypt_secret
from backend.app.models.proxy import ProxyEndpoint
from backend.app.services.audit import write_audit
from backend.app.services.proxy_checker import check_tcp
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


class ProxyCreate(BaseModel):
    name: str = Field(max_length=120)
    protocol: str = "socks5"
    host: str = Field(max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=500)
    country: str | None = Field(default=None, max_length=80)
    max_accounts: int | None = Field(default=None, ge=1, le=10000)
    remark: str | None = Field(default=None, max_length=2000)
    group_id: int | None = None


class ProxyUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    protocol: str | None = None
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=500)
    country: str | None = Field(default=None, max_length=80)
    status: str | None = None
    max_accounts: int | None = Field(default=None, ge=1, le=10000)
    remark: str | None = Field(default=None, max_length=2000)
    group_id: int | None = None


@router.get("")
def list_proxies(db: DbSession, _: AdminDep, group_id: int | None = None) -> list[dict]:
    stmt = select(ProxyEndpoint).order_by(ProxyEndpoint.id.desc())
    if group_id is not None:
        stmt = stmt.where(ProxyEndpoint.group_id == group_id)
    return list_dict(list(db.scalars(stmt)))


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
        group_id=payload.group_id,
    )
    db.add(proxy)
    db.flush()
    write_audit(db, actor=admin, action="proxy.create", target_type="proxy",
                target_id=proxy.id, detail={"host": proxy.host, "port": proxy.port, "protocol": proxy.protocol})
    db.commit()
    db.refresh(proxy)
    return to_dict(proxy)


ALLOWED_PROXY_STATUSES = {"unchecked", "active", "error", "disabled"}
ALLOWED_PROXY_PROTOCOLS = {"socks5", "socks4", "http", "https"}


@router.patch("/{proxy_id}")
def update_proxy(proxy_id: int, payload: ProxyUpdate, db: DbSession, admin: AdminDep) -> dict:
    proxy = db.get(ProxyEndpoint, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="代理不存在")
    values = payload.model_dump(exclude_unset=True)
    if "status" in values and values["status"] not in ALLOWED_PROXY_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status 必须是 {sorted(ALLOWED_PROXY_STATUSES)} 之一",
        )
    if "protocol" in values and values["protocol"] not in ALLOWED_PROXY_PROTOCOLS:
        raise HTTPException(
            status_code=400,
            detail=f"protocol 必须是 {sorted(ALLOWED_PROXY_PROTOCOLS)} 之一",
        )
    if "port" in values and values["port"] is not None and not (1 <= values["port"] <= 65535):
        raise HTTPException(status_code=400, detail="port 必须在 1-65535 之间")
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


class ProxyBulkImport(BaseModel):
    text: str = Field(max_length=200_000)  # ~3-4k proxy lines is plenty
    protocol: str = "socks5"
    group_id: int | None = None


def _parse_proxy_line(line: str) -> dict | None:
    """Parse one `host:port[:user[:pass]]` line. Returns None for
    malformed lines so the caller can collect them as 'skipped' rather
    than aborting the whole batch."""
    parts = [p.strip() for p in line.strip().split(":")]
    if len(parts) < 2:
        return None
    host = parts[0]
    if not host:
        return None
    try:
        port = int(parts[1])
    except (ValueError, TypeError):
        return None
    if not (1 <= port <= 65535):
        return None
    username = parts[2] if len(parts) >= 3 else None
    password = parts[3] if len(parts) >= 4 else None
    return {"host": host, "port": port, "username": username, "password": password}


@router.post("/import-text")
def import_proxies_text(
    payload: ProxyBulkImport, db: DbSession, admin: AdminDep,
) -> dict:
    """Paste a batch of `host:port:user:pass` lines, create one
    ProxyEndpoint per parsed line. Existing (host, port, username)
    triples are skipped so re-importing the same list is idempotent."""
    created: list[dict] = []
    skipped: list[dict] = []
    duplicated: list[str] = []
    seen_in_batch: set[tuple] = set()
    for raw in payload.text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parsed = _parse_proxy_line(line)
        if not parsed:
            skipped.append({"line": line, "reason": "格式错误，期望 host:port 或 host:port:user:pass"})
            continue
        key = (parsed["host"], parsed["port"], parsed["username"] or "")
        if key in seen_in_batch:
            duplicated.append(line)
            continue
        seen_in_batch.add(key)
        # Persistent dedup against existing rows.
        existing_q = select(ProxyEndpoint).where(
            ProxyEndpoint.host == parsed["host"],
            ProxyEndpoint.port == parsed["port"],
        )
        if parsed["username"]:
            existing_q = existing_q.where(ProxyEndpoint.username == parsed["username"])
        else:
            existing_q = existing_q.where(ProxyEndpoint.username.is_(None))
        if db.scalar(existing_q):
            duplicated.append(line)
            continue
        proxy = ProxyEndpoint(
            name=f"{parsed['host']}:{parsed['port']}",
            protocol=payload.protocol,
            host=parsed["host"],
            port=parsed["port"],
            username=parsed["username"],
            password_encrypted=encrypt_secret(parsed["password"]),
            group_id=payload.group_id,
        )
        db.add(proxy)
        db.flush()
        created.append(to_dict(proxy))
    write_audit(db, actor=admin, action="proxy.import_text",
                target_type="proxy",
                detail={"created": len(created), "duplicated": len(duplicated),
                        "skipped": len(skipped), "protocol": payload.protocol})
    db.commit()
    return {
        "created": created,
        "duplicated_count": len(duplicated),
        "skipped": skipped,
    }


class ProxyBatchUpdate(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)
    status: str | None = None    # active / error / disabled
    group_id: int | None = None  # null = clear group


class ProxyBatchDelete(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)


@router.post("/batch")
def batch_update_proxies(
    payload: ProxyBatchUpdate, db: DbSession, admin: AdminDep,
) -> dict:
    """Bulk-apply status / group changes. Either field is optional —
    e.g. only status to enable/disable a selection without touching
    grouping. group_id may be explicitly null to un-group."""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    fields = payload.model_dump(exclude_unset=True, exclude={"ids"})
    if not fields:
        raise HTTPException(status_code=400, detail="无可更新字段")
    updated = db.query(ProxyEndpoint).filter(
        ProxyEndpoint.id.in_(payload.ids)
    ).update(fields, synchronize_session=False)
    write_audit(db, actor=admin, action="proxy.batch_update",
                target_type="proxy",
                detail={"ids": payload.ids, "fields": fields})
    db.commit()
    return {"updated": int(updated or 0)}


@router.post("/batch/delete")
def batch_delete_proxies(
    payload: ProxyBatchDelete, db: DbSession, admin: AdminDep,
) -> dict:
    """Hard-delete a selection. Proxies bound to accounts are skipped
    (would orphan the account.proxy_id FK); the caller gets a count
    of how many actually went away vs. were protected."""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    from backend.app.models.account import Account
    protected = {
        row[0] for row in db.execute(
            select(Account.proxy_id).where(Account.proxy_id.in_(payload.ids))
        ).all()
        if row[0] is not None
    }
    deletable = [i for i in payload.ids if i not in protected]
    deleted = 0
    if deletable:
        # AccountProxyLog.{old,new}_proxy_id FKs into us with no
        # cascade — old audit rows would block the delete with an
        # IntegrityError → 500. Null them out first; the log row
        # keeps its account_id + reason + timestamp, just loses the
        # proxy pointer (which is fine, the proxy is gone anyway).
        from backend.app.models.proxy import AccountProxyLog
        db.query(AccountProxyLog).filter(
            AccountProxyLog.old_proxy_id.in_(deletable)
        ).update({"old_proxy_id": None}, synchronize_session=False)
        db.query(AccountProxyLog).filter(
            AccountProxyLog.new_proxy_id.in_(deletable)
        ).update({"new_proxy_id": None}, synchronize_session=False)
        deleted = db.query(ProxyEndpoint).filter(
            ProxyEndpoint.id.in_(deletable)
        ).delete(synchronize_session=False)
    write_audit(db, actor=admin, action="proxy.batch_delete",
                target_type="proxy",
                detail={"requested": len(payload.ids),
                        "deleted": int(deleted or 0),
                        "protected_in_use": sorted(protected)})
    db.commit()
    return {
        "deleted": int(deleted or 0),
        "protected_in_use": sorted(protected),
    }


@router.post("/batch/check")
def batch_check_proxies(
    payload: ProxyBatchDelete, db: DbSession, admin: AdminDep,
) -> dict:
    """Run a TCP probe against each selected proxy and update its
    status/latency. Synchronous — keep batches modest (UI uses <=200)."""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    rows = list(db.scalars(
        select(ProxyEndpoint).where(ProxyEndpoint.id.in_(payload.ids))
    ))
    ok_count = 0
    fail_count = 0
    now_iso = datetime.now(UTC).isoformat()
    for proxy in rows:
        result = check_tcp(proxy.host, proxy.port)
        proxy.status = "active" if result.ok else "error"
        proxy.latency_ms = result.latency_ms
        proxy.last_error = result.error
        proxy.last_checked_at = now_iso
        if result.ok:
            ok_count += 1
        else:
            fail_count += 1
    db.commit()
    return {"ok": ok_count, "failed": fail_count, "total": len(rows)}


@router.post("/{proxy_id}/check")
def check_proxy(proxy_id: int, db: DbSession, _: AdminDep) -> dict:
    proxy = db.get(ProxyEndpoint, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="代理不存在")

    result = check_tcp(proxy.host, proxy.port)
    proxy.status = "active" if result.ok else "error"
    proxy.latency_ms = result.latency_ms
    proxy.last_error = result.error
    proxy.last_checked_at = datetime.now(UTC).isoformat()
    db.commit()
    db.refresh(proxy)
    return to_dict(proxy)
