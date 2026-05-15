import re
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.api.deps import DbSession
from backend.app.core.config import settings
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.proxy import AccountProxyLog
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


class AccountUpdate(BaseModel):
    enabled: bool | None = None
    status: str | None = None
    daily_limit: int | None = None
    phone: str | None = None


class AccountProxyBind(BaseModel):
    proxy_id: int
    reason: str | None = None


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


@router.get("")
def list_accounts(db: DbSession) -> list[dict]:
    accounts = list(db.scalars(select(Account).order_by(Account.id.desc())))
    return list_dict(accounts)


@router.post("/import-zip")
async def import_zip(db: DbSession, sessions: UploadFile = File(...)) -> dict:
    if not sessions.filename or not sessions.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="zip file required")

    content = await sessions.read()
    default_group = ensure_default_group(db)
    imported: list[dict] = []
    skipped: list[dict] = []

    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="invalid zip file") from exc

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

    db.commit()
    return {"imported": imported, "skipped": skipped}


@router.patch("/{account_id}")
def update_account(account_id: int, payload: AccountUpdate, db: DbSession) -> dict:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, key, value)
    db.commit()
    db.refresh(account)
    return to_dict(account)


@router.post("/{account_id}/proxy")
def bind_proxy(account_id: int, payload: AccountProxyBind, db: DbSession) -> dict:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    old_proxy_id = account.proxy_id
    account.proxy_id = payload.proxy_id
    db.add(
        AccountProxyLog(
            account_id=account.id,
            old_proxy_id=old_proxy_id,
            new_proxy_id=payload.proxy_id,
            action="bind" if old_proxy_id is None else "switch",
            reason=payload.reason,
        )
    )
    db.commit()
    db.refresh(account)
    return to_dict(account)


@router.delete("/{account_id}/proxy")
def unbind_proxy(account_id: int, db: DbSession) -> dict:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    old_proxy_id = account.proxy_id
    account.proxy_id = None
    db.add(AccountProxyLog(account_id=account.id, old_proxy_id=old_proxy_id, action="unbind"))
    db.commit()
    db.refresh(account)
    return to_dict(account)
