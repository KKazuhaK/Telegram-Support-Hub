from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.deps import CurrentUserDep, DbSession
from backend.app.models.customer import Customer
from backend.app.services import translator
from backend.app.services.tenant_scope import can_access_row

router = APIRouter()


class TranslatePayload(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    target: str | None = None  # default zh-CN; pass 'auto' + customer_id
    customer_id: int | None = None  # when target='auto', use this customer's last_source_lang


@router.post("")
def translate_text(
    payload: TranslatePayload, db: DbSession, user: CurrentUserDep,
) -> dict:
    """Translate `text` into `target` (default Chinese).

    Special target='auto' resolves to the customer's last detected
    source language so an operator can type Chinese and translate to
    e.g. English before sending. Requires `customer_id` and the customer
    must be accessible to the caller (tenant scope honoured).
    """
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="翻译内容不能为空")

    target = payload.target or translator.DEFAULT_TARGET
    if target == "auto":
        if not payload.customer_id:
            raise HTTPException(
                status_code=400,
                detail="target=auto 需要 customer_id 才能定位客户语言",
            )
        cust = db.get(Customer, payload.customer_id)
        if not cust or not can_access_row(user, db, cust):
            raise HTTPException(status_code=404, detail="客户不存在")
        target = cust.last_source_lang or "en"  # fallback for new customers

    try:
        translated, source = translator._google_translate(text, target)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"翻译服务暂时不可用：{exc}") from exc

    # Side-effect: if the operator translated INTO Chinese (default flow),
    # the detected source IS the customer's language — cache it so the
    # next outbound auto-translate doesn't need a round-trip detect.
    if (
        source
        and target == translator.DEFAULT_TARGET
        and payload.customer_id
    ):
        cust = db.get(Customer, payload.customer_id)
        if cust and can_access_row(user, db, cust) and cust.last_source_lang != source:
            cust.last_source_lang = source
            db.commit()

    return {
        "translated_text": translated,
        "source_lang": source,
        "target_lang": target,
    }
