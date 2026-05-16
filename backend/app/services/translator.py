"""Pluggable text translator.

Provider, optional proxy, and (if needed) API key are read from the
`system_settings` row keyed 'translator' so an admin can switch
providers from the web UI without redeploying. Default = Google's
free web endpoint, no key needed; fine for low-volume customer chat.

Supported providers:
  - google_free  — translate.googleapis.com/translate_a/single (no key)
  - openai       — chat.completions with a short system prompt
  - deepl        — api-free.deepl.com/v2/translate (or api.deepl.com paid)

Adding a new provider: implement `_provider_xxx(text, target, cfg) ->
(translated, source_lang)` and register it in `_PROVIDERS`.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import httpx

from backend.app.core.crypto import decrypt_secret

logger = logging.getLogger(__name__)

DEFAULT_TARGET = "zh-CN"
DEFAULT_PROVIDER = "google_free"
_TIMEOUT_SEC = 10.0


# --------- Google free web endpoint (no API key) ---------

_GOOGLE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"


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


def _http_client(cfg: dict) -> httpx.Client:
    """httpx client honoring the configured proxy (used e.g. when the
    backend runs in China and needs a HTTP/SOCKS5 proxy to reach Google)."""
    proxy = (cfg or {}).get("proxy_url") or None
    return httpx.Client(timeout=_TIMEOUT_SEC, proxy=proxy) if proxy else httpx.Client(timeout=_TIMEOUT_SEC)


def _google_translate(text: str, target: str, source: str = "auto",
                      cfg: dict | None = None) -> tuple[str, str | None]:
    params = {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
    try:
        with _http_client(cfg or {}) as cli:
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


# --------- OpenAI gpt-4o-mini (or any chat model) ---------

def _openai_translate(text: str, target: str, source: str = "auto",
                      cfg: dict | None = None) -> tuple[str, str | None]:
    cfg = cfg or {}
    api_key = cfg.get("_api_key") or ""
    if not api_key:
        raise RuntimeError("openai provider needs api_key (config it in 系统设置)")
    model = cfg.get("model") or "gpt-4o-mini"
    base_url = cfg.get("base_url") or "https://api.openai.com/v1"

    prompt = (
        f"Translate the following text into {target}. "
        "Reply with only the translation, no quotes, no commentary."
    )
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
    }
    try:
        with _http_client(cfg) as cli:
            resp = cli.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"openai http error: {exc}") from exc

    try:
        translated = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"openai response shape: {data}") from exc
    # OpenAI doesn't report source lang; leave None.
    return translated, None


# --------- DeepL ---------

def _deepl_translate(text: str, target: str, source: str = "auto",
                     cfg: dict | None = None) -> tuple[str, str | None]:
    cfg = cfg or {}
    api_key = cfg.get("_api_key") or ""
    if not api_key:
        raise RuntimeError("deepl provider needs api_key (config it in 系统设置)")
    base_url = cfg.get("base_url") or (
        "https://api-free.deepl.com/v2/translate"
        if api_key.endswith(":fx")
        else "https://api.deepl.com/v2/translate"
    )
    # DeepL uses ZH for Chinese, not zh-CN.
    target_dl = target.split("-")[0].upper() if target.lower().startswith("zh") else target.upper()
    data = {"text": text, "target_lang": target_dl}
    if source and source != "auto":
        data["source_lang"] = source.upper()

    try:
        with _http_client(cfg) as cli:
            resp = cli.post(
                base_url, data=data,
                headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"deepl http error: {exc}") from exc

    try:
        item = payload["translations"][0]
        return item["text"], (item.get("detected_source_language") or "").lower() or None
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"deepl response shape: {payload}") from exc


# Provider -> module-attribute name. Resolve lazily at translate() time
# so unittest.patch.object(translator, "_google_translate", ...) actually
# wins (a dict of function references is frozen at import time).
_PROVIDERS: dict[str, str] = {
    "google_free": "_google_translate",
    "openai": "_openai_translate",
    "deepl": "_deepl_translate",
}


# --------- Settings loader ---------

def _load_settings() -> dict:
    """Read the 'translator' row from system_settings. Returns plaintext
    `value` dict plus a decrypted `_api_key` field. Empty dict when the
    row doesn't exist yet (= default Google free)."""
    try:
        # Late import so tests that monkey-patch SessionLocal pick it up.
        from backend.app.core.database import SessionLocal
        from backend.app.models.system_setting import SystemSetting
    except Exception:
        return {}

    try:
        with SessionLocal() as db:
            row = db.get(SystemSetting, "translator")
            if not row:
                return {}
            cfg = dict(row.value or {})
            if row.encrypted_value:
                cfg["_api_key"] = decrypt_secret(row.encrypted_value) or ""
            return cfg
    except Exception as exc:
        # Don't fail translation just because the settings table isn't
        # there yet (e.g. brand-new DB before first migration).
        logger.warning("translator settings load failed: %s", exc)
        return {}


def translate(text: str, target: str = DEFAULT_TARGET,
              cfg: dict | None = None) -> tuple[str, str | None]:
    """Public entry: dispatches to the configured provider."""
    text = (text or "").strip()
    if not text:
        return "", None
    if cfg is None:
        cfg = _load_settings()
    provider = (cfg or {}).get("provider") or DEFAULT_PROVIDER
    attr = _PROVIDERS.get(provider)
    if attr is None:
        raise RuntimeError(f"unknown translator provider: {provider}")
    import sys
    fn = getattr(sys.modules[__name__], attr)
    return fn(text, target, "auto", cfg)


# Backwards-compat shim — older callers still reference _google_translate
# directly (tests and routes). Keep it as a thin wrapper over the
# dispatcher so swapping providers in settings actually takes effect.
def _google_translate_compat(text: str, target: str, source: str = "auto"):
    return translate(text, target)


# Tests patch this symbol; keep the public name as a re-export.
# (Modules still importing _google_translate get the old behavior when
#  no SystemSetting row exists — same default.)
