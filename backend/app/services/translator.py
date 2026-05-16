"""Pluggable text translator.

Default provider is Google Translate's free web endpoint (the same one
the gtranslate browser bar uses). It needs no API key but is unofficial
and rate-limited; suitable for the customer-service volume this app
targets. To swap providers, replace `translate()` body with a call to
DeepL / OpenAI / Microsoft using the corresponding API key env var.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TARGET = "zh-CN"
_GOOGLE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
_TIMEOUT_SEC = 10.0


def _parse_google_response(payload: Any) -> tuple[str, str | None]:
    """Extract `(translated_text, detected_source_lang)` from Google's
    nested-array response. Returns ('', None) for any shape we don't
    recognise so the caller can decide to error rather than crash."""
    try:
        segments = payload[0] or []
        text = "".join(
            seg[0] for seg in segments
            if isinstance(seg, list) and seg and isinstance(seg[0], str)
        )
        source_lang = payload[2] if len(payload) > 2 else None
        if not isinstance(source_lang, str):
            source_lang = None
        return text, source_lang
    except (TypeError, IndexError, KeyError):
        return "", None


def _google_translate(text: str, target: str, source: str = "auto") -> tuple[str, str | None]:
    """Hit the free Google web endpoint. Returns (translated, src_lang).
    Raises RuntimeError on transport / parse failure so the caller can
    surface a 502 to the operator."""
    params = {
        "client": "gtx",
        "sl": source,
        "tl": target,
        "dt": "t",
        "q": text,
    }
    try:
        with httpx.Client(timeout=_TIMEOUT_SEC) as cli:
            resp = cli.get(_GOOGLE_ENDPOINT, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"translator http error: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"translator response not json: {exc}") from exc

    translated, src = _parse_google_response(data)
    if not translated:
        raise RuntimeError("translator returned empty result")
    return translated, src


def translate(text: str, target: str = DEFAULT_TARGET) -> tuple[str, str | None]:
    """Public entry point. Returns (translated_text, detected_source_lang).

    Single-strategy for now (Google web endpoint). Swap providers here
    when you wire up DeepL/OpenAI/Microsoft via an API key env var.
    """
    text = (text or "").strip()
    if not text:
        return "", None
    return _google_translate(text, target)
