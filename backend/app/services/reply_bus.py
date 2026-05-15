from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

REPLY_CHANNEL = "tg_support_hub:replies"


def publish_reply(payload: dict[str, Any]) -> None:
    try:
        client = get_redis()
        client.publish(REPLY_CHANNEL, json.dumps(payload, ensure_ascii=False))
    except Exception:
        logger.exception("publish_reply failed")
