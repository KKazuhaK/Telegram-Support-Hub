from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.deps import CurrentUserDep
from backend.app.services import translator

router = APIRouter()


class TranslatePayload(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    target: str | None = None  # default zh-CN


@router.post("")
def translate_text(payload: TranslatePayload, _: CurrentUserDep) -> dict:
    """Translate `text` into `target` (default Chinese). Used by the chat
    page so operators can read foreign-language customer replies."""
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="翻译内容不能为空")
    target = payload.target or translator.DEFAULT_TARGET
    try:
        translated, source = translator._google_translate(text, target)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"翻译服务暂时不可用：{exc}") from exc
    return {
        "translated_text": translated,
        "source_lang": source,
        "target_lang": target,
    }
