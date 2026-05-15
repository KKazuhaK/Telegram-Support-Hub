import re
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, select

from backend.app.api.deps import AdminDep, CurrentUserDep, DbSession
from backend.app.core.config import settings
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.proxy import AccountProxyLog
from backend.app.services.audit import write_audit
from backend.app.services.proxy_pool import PoolError, auto_assign_proxy
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


class AccountUpdate(BaseModel):
    enabled: bool | None = None
    status: str | None = None
    daily_limit: int | None = None
    phone: str | None = None
    nickname: str | None = None
    country: str | None = None
    remark: str | None = None
    avatar_status: str | None = None


class AccountProxyBind(BaseModel):
    proxy_id: int
    reason: str | None = None


# Whitelist of statuses an admin can set via the batch endpoint.
BATCH_ALLOWED_STATUSES = {"active", "paused", "limited", "error", "imported", "archived"}


class AccountBatch(BaseModel):
    ids: list[int] = Field(min_length=1)
    enabled: bool | None = None
    status: str | None = None
    # Bulk-bind / unbind proxy. proxy_id=null + clear_proxy=true → unbind.
    proxy_id: int | None = None
    clear_proxy: bool = False
    # Move accounts to a new primary group (removes all existing primary
    # memberships for those accounts and inserts one new is_primary=True
    # row per account in the target group).
    move_to_group_id: int | None = None


class AccountBatchDelete(BaseModel):
    ids: list[int] = Field(min_length=1)


def safe_part(value: str) -> str:
    part = re.sub(r"[^a-zA-Z0-9_.-]", "_", value.strip())
    return part[:100] or "unknown"


def ensure_default_group(db: DbSession) -> AccountGroup:
    group = db.scalar(select(AccountGroup).where(AccountGroup.code == "ungrouped"))
    if group:
        return group
    group = AccountGroup(name="未分组", code="ungrouped", daily_limit=0, remark="默认分组，账号需分配到正式分组后再使用")
    db.add(group)
    db.flush()
    return group


def _filter_account_query(stmt, user):
    if user.is_admin:
        return stmt
    group_ids = user.visible_group_ids()
    if not group_ids:
        return stmt.where(Account.id == -1)
    member_subq = select(AccountGroupMember.account_id).where(AccountGroupMember.group_id.in_(group_ids))
    return stmt.where(Account.id.in_(member_subq))


def _ensure_account_visible(db, user, account: Account) -> None:
    if user.is_admin:
        return
    member_ids = [m.group_id for m in db.scalars(
        select(AccountGroupMember).where(AccountGroupMember.account_id == account.id)
    )]
    if not set(member_ids).intersection(user.visible_group_ids()):
        raise HTTPException(status_code=403, detail="该 TG 账号不在你授权的账号分组内")


@router.get("")
def list_accounts(
    db: DbSession,
    user: CurrentUserDep,
    status: str | None = None,
    enabled: bool | None = None,
    phone: str | None = None,
    group_id: int | None = None,
    nickname: str | None = None,
    country: str | None = None,
    avatar_status: str | None = None,
    has_proxy: bool | None = None,
    remark: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    stmt = select(Account).order_by(Account.id.desc())
    stmt = _filter_account_query(stmt, user)
    if status:
        stmt = stmt.where(Account.status == status)
    if enabled is not None:
        stmt = stmt.where(Account.enabled.is_(enabled))
    if phone:
        stmt = stmt.where(Account.phone.like(f"%{phone}%"))
    if nickname:
        stmt = stmt.where(Account.nickname.like(f"%{nickname}%"))
    if country:
        stmt = stmt.where(Account.country == country)
    if avatar_status:
        stmt = stmt.where(Account.avatar_status == avatar_status)
    if remark:
        stmt = stmt.where(Account.remark.like(f"%{remark}%"))
    if has_proxy is True:
        stmt = stmt.where(Account.proxy_id.isnot(None))
    elif has_proxy is False:
        stmt = stmt.where(Account.proxy_id.is_(None))
    if from_date:
        stmt = stmt.where(Account.last_login_at >= from_date)
    if to_date:
        stmt = stmt.where(Account.last_login_at < f"{to_date}T23:59:60")
    if group_id:
        stmt = stmt.where(Account.id.in_(
            select(AccountGroupMember.account_id).where(AccountGroupMember.group_id == group_id)
        ))
    return list_dict(list(db.scalars(stmt.offset(offset).limit(limit))))


@router.post("/import-zip")
async def import_zip(db: DbSession, admin: AdminDep, sessions: UploadFile = File(...)) -> dict:
    if not sessions.filename or not sessions.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 后缀的 session 压缩包")

    content = await sessions.read()
    default_group = ensure_default_group(db)
    imported: list[dict] = []
    skipped: list[dict] = []

    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="ZIP 文件损坏或格式不正确") from exc

    for info in zf.infolist():
        if info.is_dir() or not info.filename.lower().endswith(".session"):
            continue
        parts = [part for part in Path(info.filename.replace("\\", "/")).parts if part not in {"/", "."}]
        if len(parts) < 2:
            skipped.append({"file": info.filename, "reason": "path must be userid/*.session"})
            continue
        user_id = safe_part(parts[0])
        filename = safe_part(parts[-1])
        account_dir = settings.session_dir / user_id
        account_dir.mkdir(parents=True, exist_ok=True)
        session_path = account_dir / filename
        session_path.write_bytes(zf.read(info))

        account = db.scalar(select(Account).where(Account.tg_user_id == user_id))
        if not account:
            account = Account(tg_user_id=user_id, session_path=str(session_path), status="imported")
            db.add(account)
            db.flush()
            db.add(AccountGroupMember(account_id=account.id, group_id=default_group.id, is_primary=True))
        else:
            account.session_path = str(session_path)
            if account.status == "error":
                account.status = "imported"
        imported.append({"user_id": user_id, "file": info.filename})

    write_audit(db, actor=admin, action="account.import_zip",
                detail={"imported": len(imported), "skipped": len(skipped)})
    db.commit()
    return {"imported": imported, "skipped": skipped}


@router.post("/batch")
def batch_update_accounts(payload: AccountBatch, db: DbSession, admin: AdminDep) -> dict:
    if payload.status is not None and payload.status not in BATCH_ALLOWED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status 必须是 {sorted(BATCH_ALLOWED_STATUSES)} 之一",
        )
    if payload.move_to_group_id is not None:
        if not db.get(AccountGroup, payload.move_to_group_id):
            raise HTTPException(status_code=400, detail="目标账号分组不存在")

    rows = list(db.scalars(select(Account).where(Account.id.in_(payload.ids))))
    for acc in rows:
        if payload.enabled is not None:
            acc.enabled = payload.enabled
        if payload.status is not None:
            acc.status = payload.status
        # Bind / unbind proxy in bulk. Log each change via AccountProxyLog
        # so the proxy audit trail stays consistent with single-account ops.
        new_proxy_id = payload.proxy_id if payload.proxy_id is not None else (
            None if payload.clear_proxy else "__unchanged__"
        )
        if new_proxy_id != "__unchanged__" and acc.proxy_id != new_proxy_id:
            old = acc.proxy_id
            acc.proxy_id = new_proxy_id
            db.add(AccountProxyLog(
                account_id=acc.id, old_proxy_id=old, new_proxy_id=new_proxy_id,
                action="bind" if old is None and new_proxy_id is not None
                else "unbind" if new_proxy_id is None
                else "switch",
                reason="batch",
                created_by=admin.username,
            ))

    if payload.move_to_group_id is not None:
        # Remove all existing primary memberships for these accounts, then
        # insert one new primary row per account in the destination group.
        db.execute(sa_delete(AccountGroupMember).where(
            AccountGroupMember.account_id.in_(payload.ids),
            AccountGroupMember.is_primary.is_(True),
        ))
        for acc in rows:
            db.add(AccountGroupMember(
                account_id=acc.id, group_id=payload.move_to_group_id, is_primary=True,
            ))

    write_audit(
        db, actor=admin, action="account.batch_update",
        detail={
            "ids": payload.ids, "enabled": payload.enabled, "status": payload.status,
            "proxy_id": payload.proxy_id, "clear_proxy": payload.clear_proxy,
            "move_to_group_id": payload.move_to_group_id,
        },
    )
    db.commit()
    return {"updated": len(rows)}


@router.delete("/batch")
def batch_delete_accounts(payload: AccountBatchDelete = Body(...), *, db: DbSession, admin: AdminDep) -> dict:
    rows = list(db.scalars(select(Account).where(Account.id.in_(payload.ids))))
    if not rows:
        return {"deleted": 0}
    db.execute(sa_delete(AccountGroupMember).where(AccountGroupMember.account_id.in_(payload.ids)))
    for acc in rows:
        db.delete(acc)
    write_audit(
        db, actor=admin, action="account.batch_delete",
        detail={"ids": payload.ids, "count": len(rows)},
    )
    db.commit()
    return {"deleted": len(rows)}


@router.patch("/{account_id}")
def update_account(account_id: int, payload: AccountUpdate, db: DbSession, admin: AdminDep) -> dict:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="TG 账号不存在")
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(account, key, value)
    write_audit(db, actor=admin, action="account.update",
                target_type="account", target_id=account.id, detail=values)
    db.commit()
    db.refresh(account)
    return to_dict(account)


@router.post("/{account_id}/proxy")
def bind_proxy(account_id: int, payload: AccountProxyBind, db: DbSession, admin: AdminDep) -> dict:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="TG 账号不存在")
    old_proxy_id = account.proxy_id
    account.proxy_id = payload.proxy_id
    db.add(
        AccountProxyLog(
            account_id=account.id,
            old_proxy_id=old_proxy_id,
            new_proxy_id=payload.proxy_id,
            action="bind" if old_proxy_id is None else "switch",
            reason=payload.reason,
            created_by=admin.username,
        )
    )
    write_audit(db, actor=admin, action="account.proxy_bind",
                target_type="account", target_id=account.id,
                detail={"old": old_proxy_id, "new": payload.proxy_id, "reason": payload.reason})
    db.commit()
    db.refresh(account)
    return to_dict(account)


@router.post("/{account_id}/proxy/auto")
def auto_bind_proxy(account_id: int, db: DbSession, admin: AdminDep, prefer_country: str | None = None) -> dict:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="TG 账号不存在")
    old_proxy_id = account.proxy_id
    try:
        proxy = auto_assign_proxy(db, account, prefer_country=prefer_country)
    except PoolError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add(AccountProxyLog(
        account_id=account.id, old_proxy_id=old_proxy_id, new_proxy_id=proxy.id,
        action="bind" if old_proxy_id is None else "switch",
        reason="auto", created_by=admin.username,
    ))
    write_audit(db, actor=admin, action="account.proxy_auto_bind",
                target_type="account", target_id=account.id,
                detail={"old": old_proxy_id, "new": proxy.id, "prefer_country": prefer_country})
    db.commit()
    db.refresh(account)
    return to_dict(account)


@router.delete("/{account_id}/proxy")
def unbind_proxy(account_id: int, db: DbSession, admin: AdminDep) -> dict:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="TG 账号不存在")
    old_proxy_id = account.proxy_id
    account.proxy_id = None
    db.add(AccountProxyLog(account_id=account.id, old_proxy_id=old_proxy_id, action="unbind", created_by=admin.username))
    write_audit(db, actor=admin, action="account.proxy_unbind",
                target_type="account", target_id=account.id, detail={"old": old_proxy_id})
    db.commit()
    db.refresh(account)
    return to_dict(account)
