import asyncio
import json
import re
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, select

from backend.app.api.deps import AdminDep, CurrentUserDep, DbSession
from backend.app.core.config import settings
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.message import MessageRecord
from backend.app.models.proxy import AccountProxyLog, ProxyEndpoint
from backend.app.services.audit import write_audit
from backend.app.services.port_quota import (
    QuotaError, check_quota_for_activation, recompute_merchant_ports,
)
from backend.app.services.proxy_pool import PoolError, auto_assign_proxy
from backend.app.services.serializers import list_dict, to_dict
from backend.app.services.tdata_converter import convert_tdata_zip_entry, is_tdata_layout
from backend.app.services.tenant_scope import apply_merchant_scope, sanitize_account_for_tenant

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


# Anything looking like 7-15 digits (optionally with leading +) is almost
# certainly a phone number, NOT a Telegram user id (real user ids are
# also numeric but operators using subfolder layout pick short non-phone
# names like '1001'). 7 is the minimum E.164 national number length.
_PHONE_BASENAME_RE = re.compile(r"^\+?\d{7,15}$")


def _stem_from_zip_entry(filename: str) -> tuple[str | None, bool]:
    """Resolve a zip entry path to (basename_stem, is_subfolder).

    A. `<id>/<anything>.session`  -> (id, True)   (subfolder convention)
    B. `<id>.session`             -> (id, False)  (flat layout)

    Returns (None, False) for paths that match neither shape.
    """
    parts = [p for p in Path(filename.replace("\\", "/")).parts if p not in {"/", "."}]
    if not parts:
        return None, False
    if len(parts) >= 2:
        return safe_part(parts[0]), True
    base = parts[0]
    if base.lower().endswith(".session"):
        return safe_part(base[: -len(".session")]), False
    return None, False


def _resolve_account_identity(stem: str, is_subfolder: bool, meta: dict) -> tuple[str, str | None]:
    """Decide the (tg_user_id, phone) to persist for a freshly-imported
    session, given the basename stem and the optional sidecar metadata.

    Rules:
      1. Sidecar carries a non-empty `user_id` -> use it verbatim;
         phone comes from sidecar `phone` (or stem if phone-shaped).
      2. Sidecar carries a non-empty `phone` (no real user_id) -> the
         basename is the phone; tg_user_id is a `pending:<phone>`
         placeholder that validate_session will overwrite once Telethon
         returns the real numeric id.
      3. Flat layout, phone-shaped basename, no useful sidecar -> same
         placeholder, phone derived from the basename.
      4. Otherwise (subfolder layout with a hand-picked id, or any flat
         entry whose basename doesn't look phone-shaped) -> trust the
         stem as the tg_user_id; phone left to whatever sidecar said
         (commonly None).
    """
    sidecar_user_id = str(meta.get("user_id") or "").strip()
    sidecar_phone = _normalize_phone(meta.get("phone"))

    if sidecar_user_id:
        # Rule 1.
        phone = sidecar_phone or (
            _normalize_phone(stem) if _PHONE_BASENAME_RE.match(stem) else None
        )
        return sidecar_user_id, phone

    # Rule 2 + 3 (phone-derived placeholder).
    phone = sidecar_phone
    if phone is None and not is_subfolder and _PHONE_BASENAME_RE.match(stem):
        phone = _normalize_phone(stem)
    if phone:
        return f"pending:{phone}", phone

    # Rule 4.
    return stem, sidecar_phone


def _normalize_phone(raw: str | None) -> str | None:
    """Accept '12792412211' / '+12792412211' / '+1 (279) 241-2211' and
    return E.164-ish `+digits`. Returns None for empty / non-digit input."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    return f"+{digits}" if digits else None


def _parse_sidecar_metadata(raw: bytes) -> dict | None:
    """Parse the optional `<user_id>.json` metadata file that ships with
    common session exports (tdesktop, telethon dumpers). Returns None on
    malformed JSON — callers ignore the metadata in that case rather
    than blocking the session import."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def ensure_default_group(db: DbSession) -> AccountGroup:
    group = db.scalar(select(AccountGroup).where(AccountGroup.code == "ungrouped"))
    if group:
        return group
    group = AccountGroup(name="未分组", code="ungrouped", daily_limit=0, remark="默认分组，账号需分配到正式分组后再使用")
    db.add(group)
    db.flush()
    return group


def _filter_account_query(stmt, user, db=None):
    # Multi-tenant scope first (merchant / business_agent only see their own).
    if db is not None:
        stmt = apply_merchant_scope(stmt, user, db, Account)
    if user.is_admin or user.actor_kind != "support_agent":
        # Tenant actors don't go through the per-group permission system —
        # the merchant_id filter is the boundary.
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
    stmt = _filter_account_query(stmt, user, db)
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
    # TG inventory is back-office only — tenants (merchant /
    # business_agent) get an empty list regardless of scope matches.
    # Don't expose how many TGs exist, their state, or even existence.
    if user.actor_kind != "support_agent":
        return []
    return list_dict(list(db.scalars(stmt.offset(offset).limit(limit))))


@router.post("/import-zip")
async def import_zip(
    db: DbSession, admin: AdminDep,
    sessions: UploadFile = File(...),
    group_id: int = Form(...),
) -> dict:
    if not sessions.filename or not sessions.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 后缀的 session 压缩包")
    # Group is required: previously the import silently dropped new
    # accounts into the legacy `未分组` bucket, leaving them invisible
    # to every agent until an admin moved them. Forcing the choice up
    # front mirrors the simpler '一组一客服' workflow the operator asked
    # for. Legacy ungrouped accounts are untouched.
    target_group = db.get(AccountGroup, group_id)
    if not target_group:
        raise HTTPException(
            status_code=400,
            detail=f"账号分组 #{group_id} 不存在，请先在「账号分组」页创建",
        )

    content = await sessions.read()
    imported: list[dict] = []
    skipped: list[dict] = []

    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="ZIP 文件损坏或格式不正确") from exc

    def _persist_session(stem: str, is_subfolder: bool, meta: dict,
                         filename: str, session_bytes: bytes,
                         source_label: str) -> None:
        """Common path: write session bytes under session_dir, upsert
        Account + AccountGroupMember, append to `imported` log."""
        tg_user_id, phone = _resolve_account_identity(stem, is_subfolder, meta)
        safe_filename = safe_part(filename)
        account_dir = settings.session_dir / stem
        account_dir.mkdir(parents=True, exist_ok=True)
        session_path = account_dir / safe_filename
        session_path.write_bytes(session_bytes)

        account = db.scalar(select(Account).where(Account.tg_user_id == tg_user_id))
        if not account and phone:
            account = db.scalar(select(Account).where(Account.phone == phone))
        if not account:
            account = Account(
                tg_user_id=tg_user_id, session_path=str(session_path),
                status="imported", phone=phone,
            )
            db.add(account)
            db.flush()
            db.add(AccountGroupMember(
                account_id=account.id, group_id=target_group.id, is_primary=True,
            ))
        else:
            account.session_path = str(session_path)
            if account.status == "error":
                account.status = "imported"
            if phone and not account.phone:
                account.phone = phone
        imported.append({"user_id": tg_user_id, "file": source_label})

    # ---- 1) Telegram Desktop tdata layout ----
    # Each <phone>/tdata/* folder is converted to a single .session file
    # via opentele. Offload to the default threadpool because
    # convert_tdata_zip_entry calls asyncio.run() internally, which
    # can't nest in this request's already-running event loop.
    import asyncio as _asyncio
    import logging as _logging
    import traceback as _traceback
    _log = _logging.getLogger(__name__)
    tdata_stems = is_tdata_layout(zf)
    for stem in tdata_stems:
        try:
            session_bytes = await _asyncio.to_thread(
                convert_tdata_zip_entry, zf, stem,
            )
        except BaseException as exc:  # noqa: BLE001 — catch broader than Exception
            # Log full traceback in the container so operators can dig
            # past the surfaced one-line reason. Catch BaseException so
            # weird stuff (e.g. opentele asserting, Qt SystemExit) also
            # falls through to skipped rather than 500-ing the request.
            tb = _traceback.format_exc()
            _log.error("tdata convert failed for %s:\n%s", stem, tb)
            skipped.append({
                "file": f"{stem}/tdata",
                "reason": f"tdata 转换失败 ({type(exc).__name__}): {exc}",
            })
            continue
        _persist_session(
            stem=stem, is_subfolder=False, meta={},
            filename=f"{stem}.session",
            session_bytes=session_bytes,
            source_label=f"{stem}/tdata",
        )

    # ---- 2) Plain .session layouts (flat <stem>.session OR subfolder) ----
    # Pre-index optional sidecar JSON files by their basename stem so a
    # `<user_id>.session` entry can pick up its `<user_id>.json` metadata
    # in one pass. Subfolder layouts don't have sidecars; legacy callers
    # are unaffected.
    sidecars: dict[str, dict] = {}
    for info in zf.infolist():
        if info.is_dir() or not info.filename.lower().endswith(".json"):
            continue
        parts = [p for p in Path(info.filename.replace("\\", "/")).parts if p not in {"/", "."}]
        if len(parts) != 1:
            continue  # nested JSON — unrelated to our sidecar convention
        meta = _parse_sidecar_metadata(zf.read(info))
        if meta is None:
            continue
        stem = safe_part(parts[0][: -len(".json")])
        sidecars[stem] = meta

    for info in zf.infolist():
        if info.is_dir() or not info.filename.lower().endswith(".session"):
            continue
        stem, is_subfolder = _stem_from_zip_entry(info.filename)
        if stem is None:
            skipped.append({"file": info.filename, "reason": "path must be <user_id>.session or <user_id>/*.session"})
            continue
        # Skip stems already handled by the tdata pass to avoid double-import.
        if stem in tdata_stems:
            continue
        _persist_session(
            stem=stem,
            is_subfolder=is_subfolder,
            meta=sidecars.get(stem) or {},
            filename=Path(info.filename.replace("\\", "/")).name,
            session_bytes=zf.read(info),
            source_label=info.filename,
        )

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

    # R2: enforce port quota when activating accounts under a merchant.
    # Group the to-be-activated rows by merchant_id and check each merchant
    # can accommodate the delta before mutating anything.
    if payload.status == "active":
        per_merchant_delta: dict[int, int] = {}
        for acc in rows:
            if acc.merchant_id and acc.status != "active":
                per_merchant_delta[acc.merchant_id] = per_merchant_delta.get(acc.merchant_id, 0) + 1
        for merchant_id, delta in per_merchant_delta.items():
            try:
                check_quota_for_activation(db, merchant_id, additional=delta)
            except QuotaError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

    affected_merchants: set[int] = set()
    for acc in rows:
        if payload.status is not None and acc.merchant_id and acc.status != payload.status:
            affected_merchants.add(acc.merchant_id)
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
    # Sync ports_used for any merchant whose active count just changed
    # *inside* the same transaction so audit + status + ports_used commit
    # atomically (one of them failing rolls back the others). Flush first
    # so the recompute SELECT sees the just-mutated account.status values
    # — the session runs with autoflush=False.
    if affected_merchants:
        db.flush()
        for merchant_id in affected_merchants:
            recompute_merchant_ports(db, merchant_id)

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


class TestSendPayload(BaseModel):
    target: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=4000)
    # 'phone' (E.164-ish, defaults to phone when omitted because most
    # ad-hoc test targets are phone numbers) or 'tg_user_id'.
    target_kind: str = "phone"


@router.post("/{account_id}/test-send")
def test_send(
    account_id: int, payload: TestSendPayload,
    db: DbSession, admin: AdminDep,
) -> dict:
    """Admin smoke-test: send a single message via this TG account to an
    arbitrary phone / tg_user_id without going through campaigns.

    Persists a MessageRecord (campaign_id=None, direction='outbound')
    so the operator can see the attempt + its result in chat history
    and audit logs.
    """
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="TG 账号不存在")
    if account.status != "active" or not account.enabled:
        raise HTTPException(
            status_code=400,
            detail=f"TG 账号未启用或不在线（status={account.status}, enabled={account.enabled}）",
        )
    if payload.target_kind not in ("phone", "tg_user_id"):
        raise HTTPException(
            status_code=400,
            detail="target_kind 必须是 'phone' 或 'tg_user_id'",
        )

    target_phone = payload.target if payload.target_kind == "phone" else None
    target_uid = payload.target if payload.target_kind == "tg_user_id" else None

    proxy = db.get(ProxyEndpoint, account.proxy_id) if account.proxy_id else None

    record = MessageRecord(
        account_id=account.id,
        phone=target_phone,
        target_tg_user_id=target_uid,
        body_snapshot=payload.text,
        direction="outbound",
        status="sending",
    )
    record.created_at = datetime.now(UTC)
    db.add(record)
    db.flush()

    # Late import so the adapter (and patched get_adapter in tests) is
    # resolved at call time.
    from backend.app.telegram import adapter as adapter_module
    adapter = adapter_module.get_adapter()

    # Adapter resolves the target string to a Telegram entity via
    # client.get_entity — accepts phone or @username or numeric id.
    # Pass positionally to dodge the bound-method-vs-kwarg collision
    # when tests substitute a stub class attribute.
    try:
        result = asyncio.run(adapter.send_message(
            account, payload.target, payload.text, proxy=proxy,
        ))
    except Exception as exc:  # noqa: BLE001 — surface to admin below
        record.status = "failed"
        record.error_code = type(exc).__name__
        record.error_message = str(exc)[:500]
        db.commit()
        raise HTTPException(status_code=502, detail=f"Telegram 发送失败：{exc}") from exc

    if result.ok:
        record.status = "sent"
        record.sent_at = datetime.now(UTC).isoformat()
        record.external_message_id = result.external_message_id
        if result.target_tg_user_id:
            record.target_tg_user_id = result.target_tg_user_id
    else:
        record.status = "failed"
        record.error_code = result.error_code
        record.error_message = (result.error_message or "")[:500]

    write_audit(
        db, actor=admin, action="account.test_send",
        target_type="account", target_id=account.id,
        detail={"target": payload.target, "kind": payload.target_kind,
                "ok": result.ok, "error_code": result.error_code},
    )
    db.commit()
    db.refresh(record)

    if not result.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Telegram 发送失败：{result.error_message or result.error_code}",
        )
    return to_dict(record)


@router.post("/{account_id}/validate")
def validate_now(account_id: int, db: DbSession, admin: AdminDep) -> dict:
    """Synchronously validate a single account's session. Updates
    `status` / `last_login_at` / `last_error` and promotes any
    `pending:<phone>` placeholder to the real numeric tg_user_id
    just like the periodic validate_all_sessions beat task does.

    Returns {ok, status, tg_user_id, error_message} for the UI to
    display immediately. Admin-only.
    """
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="TG 账号不存在")

    proxy = db.get(ProxyEndpoint, account.proxy_id) if account.proxy_id else None

    # Late import + isolated function so worker tests can patch
    # account_tasks.get_adapter without us bypassing them via a direct
    # backend.app.telegram.adapter import here.
    from backend.app.workers import account_tasks
    from datetime import UTC, datetime as _dt

    adapter = account_tasks.get_adapter()
    if not getattr(adapter, "configured", False):
        raise HTTPException(
            status_code=502,
            detail="Telegram adapter 未配置（TELEGRAM_API_ID / API_HASH 未设置或 telethon 未安装）",
        )

    try:
        result = asyncio.run(adapter.validate_session(account, proxy))
    except Exception as exc:  # noqa: BLE001 — surface to admin
        account.status = "error"
        account.last_error = str(exc)[:500]
        db.commit()
        raise HTTPException(status_code=502, detail=f"验证失败：{exc}") from exc

    if result.ok:
        account.status = "active"
        account.last_login_at = _dt.now(UTC).isoformat()
        account.last_error = None
        if (
            result.tg_user_id
            and account.tg_user_id
            and account.tg_user_id.startswith("pending:")
        ):
            account.tg_user_id = result.tg_user_id
    else:
        account.status = "error"
        account.last_error = result.error_message or result.error_code

    write_audit(db, actor=admin, action="account.validate_now",
                target_type="account", target_id=account.id,
                detail={"ok": result.ok, "error_code": result.error_code})
    db.commit()
    db.refresh(account)
    return {
        "ok": result.ok,
        "status": account.status,
        "tg_user_id": account.tg_user_id,
        "error_message": result.error_message,
        "error_code": result.error_code,
    }


@router.post("/validate-all")
def validate_all_now(_admin: AdminDep) -> dict:
    """Trigger the validate-all-sessions beat task right now instead of
    waiting for the next 15-minute tick. Returns the Celery task id.
    Useful right after a bulk import."""
    from backend.app.workers.account_tasks import validate_all_sessions
    task = validate_all_sessions.delay()
    return {"task_id": task.id}


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
