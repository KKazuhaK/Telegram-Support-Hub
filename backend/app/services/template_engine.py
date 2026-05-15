"""Template variable engine.

Renders a message body into final text + Telegram MessageEntity-style
metadata. Two layers of substitution:

1. ``{name}`` / ``{phone}`` / ``{source}`` — context placeholders pulled
   from the caller-supplied dict.
2. ``[Tag=value]`` / ``[Tag=count]`` — formatting and randomisation
   tokens listed in the PRD (Bold/Italic/Underline/Strike/Code/Pre/URL/
   TextURL/Mention/Hashtag/Email/Phone, RandomEmoji/RandomAlphabet/
   RandomNumber/RandomSymbol).

Entity offsets/lengths are measured in **UTF-16 code units** so the
output can be passed to Telegram's API as-is.
"""

from __future__ import annotations

import random
import re
import string
from dataclasses import dataclass, field

_DEFAULT_NAME = "客户"


@dataclass
class RenderedMessage:
    text: str
    entities: list[dict] = field(default_factory=list)


# Tags that produce entities. value -> entity metadata.
_FORMATTING_TAGS = {
    "Bold": "bold",
    "Italic": "italic",
    "Underline": "underline",
    "Strike": "strike",
    "Code": "code",
    "URL": "url",
    "Email": "email",
    "Mention": "mention",
    "Hashtag": "hashtag",
    "Phone": "phone",
}

_RANDOM_POOLS = {
    "RandomAlphabet": string.ascii_letters,
    "RandomNumber": string.digits,
    "RandomSymbol": "!@#$%^&*()-_=+[]{};:,.<>?/~",
}

_EMOJI_POOL = (
    "😀😃😄😁😆😅😂🙂😉😊😍😘😎🤔🤩🥰😴😇🤗🙃"
    "👍👌👏🙏🎉🎊✨🔥💯⭐🌟💪💡📌📣🚀🌈"
)

# Master regex for [Tag=value]. Value is non-greedy and may contain commas
# (used by Pre and TextURL). We strip outer whitespace from value at parse
# time.
_TAG_RE = re.compile(r"\[(?P<tag>[A-Za-z]+)=(?P<value>.*?)\]")

# Context placeholders. We do them first so subsequent tag offsets are
# computed against the post-substitution string.
_CTX_PLACEHOLDERS = {"{name}", "{phone}", "{source}"}


def _utf16_len(s: str) -> int:
    """Length in UTF-16 code units (the unit Telegram uses for entity
    offset/length)."""
    return len(s.encode("utf-16-le")) // 2


def _apply_context(body: str, context: dict) -> str:
    name = context.get("name") or _DEFAULT_NAME
    phone = context.get("phone") or ""
    source = context.get("source") or ""
    return (
        body.replace("{name}", str(name))
        .replace("{phone}", str(phone))
        .replace("{source}", str(source))
    )


def _expand_random(tag: str, raw_count: str, rng: random.Random) -> str | None:
    """Return the random expansion for a [Random*=N] tag, or None if the
    count is invalid (leave the literal placeholder in place)."""
    try:
        count = int(raw_count.strip())
    except ValueError:
        return None
    if count < 0:
        return None
    if count == 0:
        return ""
    if tag == "RandomEmoji":
        return "".join(rng.choice(_EMOJI_POOL) for _ in range(count))
    pool = _RANDOM_POOLS.get(tag)
    if pool is None:
        return None
    return "".join(rng.choice(pool) for _ in range(count))


def _expand_pre(value: str) -> tuple[str, str]:
    """[Pre=Lang,code] -> (rendered_text, language). Language defaults to
    empty string if no comma."""
    if "," in value:
        lang, _, body = value.partition(",")
        return body, lang.strip()
    return value, ""


def _expand_text_url(value: str) -> tuple[str, str]:
    """[TextURL=text,url] -> (rendered_text, url). If no comma, treat as
    plain URL."""
    if "," in value:
        text, _, url = value.partition(",")
        return text, url.strip()
    return value, value


def render_message(
    body: str,
    context: dict | None = None,
    rng: random.Random | None = None,
) -> RenderedMessage:
    context = context or {}
    rng = rng or random.Random()
    intermediate = _apply_context(body, context)

    pieces: list[str] = []
    entities: list[dict] = []
    cursor = 0
    # Running offset in UTF-16 code units against the FINAL output. Updated
    # after each piece is appended.
    out_utf16_offset = 0

    for match in _TAG_RE.finditer(intermediate):
        start, end = match.start(), match.end()
        # Append text between previous match and this tag.
        before = intermediate[cursor:start]
        pieces.append(before)
        out_utf16_offset += _utf16_len(before)

        tag = match.group("tag")
        value = match.group("value")

        # 1. Random expansions: pure text, no entity.
        if tag in {"RandomEmoji", "RandomAlphabet", "RandomNumber", "RandomSymbol"}:
            expansion = _expand_random(tag, value, rng)
            if expansion is None:
                pieces.append(match.group(0))  # keep literal
                out_utf16_offset += _utf16_len(match.group(0))
            else:
                pieces.append(expansion)
                out_utf16_offset += _utf16_len(expansion)
            cursor = end
            continue

        # 2. Pre code block.
        if tag == "Pre":
            inner, language = _expand_pre(value)
            length_u16 = _utf16_len(inner)
            entity = {"type": "pre", "offset": out_utf16_offset, "length": length_u16}
            if language:
                entity["language"] = language
            pieces.append(inner)
            entities.append(entity)
            out_utf16_offset += length_u16
            cursor = end
            continue

        # 3. TextURL: separate text and URL.
        if tag == "TextURL":
            text, url = _expand_text_url(value)
            length_u16 = _utf16_len(text)
            entities.append({
                "type": "text_url", "offset": out_utf16_offset,
                "length": length_u16, "url": url,
            })
            pieces.append(text)
            out_utf16_offset += length_u16
            cursor = end
            continue

        # 4. Simple formatting/recognition tags: text is the value as-is.
        entity_kind = _FORMATTING_TAGS.get(tag)
        if entity_kind is not None:
            length_u16 = _utf16_len(value)
            entities.append({"type": entity_kind, "offset": out_utf16_offset, "length": length_u16})
            pieces.append(value)
            out_utf16_offset += length_u16
            cursor = end
            continue

        # 5. Unknown tag — keep literal.
        pieces.append(match.group(0))
        out_utf16_offset += _utf16_len(match.group(0))
        cursor = end

    # Tail after last tag.
    pieces.append(intermediate[cursor:])
    return RenderedMessage(text="".join(pieces), entities=entities)


# ---------------------------------------------------------------------------
# Backwards-compat shim for the old `render_template(body, customer) -> str`
# helper used by the campaign builder. We resolve {name}/{phone}/{source}
# from the customer model attributes and return the rendered text only.
# ---------------------------------------------------------------------------


def render_template_compat(body: str, customer) -> str:
    """Plain-text rendering compatible with the legacy template_renderer."""
    context = {
        "name": getattr(customer, "name", None),
        "phone": getattr(customer, "phone", None),
        "source": getattr(customer, "source", None),
    }
    return render_message(body, context).text
