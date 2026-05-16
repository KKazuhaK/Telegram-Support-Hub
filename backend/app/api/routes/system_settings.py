from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.api.deps import AdminDep, DbSession
from backend.app.core.crypto import encrypt_secret
from backend.app.models.system_setting import SystemSetting
from backend.app.services import translator
from backend.app.services.audit import write_audit

router = APIRouter()


# ---------- translator ----------

class TranslatorConfigPayload(BaseModel):
    provider: str | None = None    # 'google_free' | 'openai' | 'deepl'
    proxy_url: str | None = None   # optional HTTP/SOCKS5, e.g. http://127.0.0.1:7890
    model: str | None = None       # only meaningful for openai
    base_url: str | None = None    # optional override (openai-compat endpoints, deepl pro)
    api_key: str | None = None     # plain text; we encrypt before persisting


SUPPORTED_PROVIDERS = list(translator._PROVIDERS.keys())


def _mask_key(plain: str | None) -> str:
    if not plain:
        return ""
    if len(plain) <= 8:
        return "***"
    return f"{plain[:4]}***{plain[-2:]}"


@router.get("/translator")
def get_translator_config(db: DbSession, _: AdminDep) -> dict:
    row = db.get(SystemSetting, "translator")
    cfg = dict(row.value or {}) if row else {}
    # Surface the masked key so the UI can show "已配置" hint without
    # ever sending the real secret back to the browser.
    plain_key = ""
    if row and row.encrypted_value:
        from backend.app.core.crypto import decrypt_secret
        plain_key = decrypt_secret(row.encrypted_value) or ""
    cfg["api_key_masked"] = _mask_key(plain_key)
    cfg["has_api_key"] = bool(plain_key)
    cfg.setdefault("provider", translator.DEFAULT_PROVIDER)
    cfg["supported_providers"] = SUPPORTED_PROVIDERS
    return cfg


@router.patch("/translator")
def update_translator_config(
    payload: TranslatorConfigPayload, db: DbSession, admin: AdminDep,
) -> dict:
    if payload.provider and payload.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"provider 必须是 {SUPPORTED_PROVIDERS} 之一",
        )

    row = db.get(SystemSetting, "translator")
    if row is None:
        row = SystemSetting(key="translator", value={})
        db.add(row)

    value = dict(row.value or {})
    # Only touch fields the caller actually sent (None = leave alone),
    # but allow empty string to explicitly clear a field (proxy_url='').
    incoming = payload.model_dump(exclude_unset=True)
    for k in ("provider", "proxy_url", "model", "base_url"):
        if k in incoming:
            v = incoming[k]
            if v in ("", None):
                value.pop(k, None)
            else:
                value[k] = v
    row.value = value

    if "api_key" in incoming:
        new_key = incoming["api_key"] or ""
        # Empty string explicitly clears; non-empty re-encrypts.
        row.encrypted_value = encrypt_secret(new_key) if new_key else None

    write_audit(
        db, actor=admin, action="system_setting.update",
        target_type="system_setting", target_id="translator",
        # Never log the actual key — only that it changed.
        detail={"keys_changed": list(incoming.keys()),
                "provider": value.get("provider")},
    )
    db.commit()
    return get_translator_config(db, admin)
