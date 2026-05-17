from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from backend.app.core.database import SessionLocal
from backend.app.core.redis_client import get_redis
from backend.app.core.security import decode_token
from backend.app.models.agent import SupportAgent
from backend.app.models.tenant import BusinessAgent, Merchant
from backend.app.services.permissions import (
    load_business_agent_user, load_current_user, load_merchant_user,
)
from backend.app.services.reply_bus import REPLY_CHANNEL

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_user(token: str):
    """Decode the JWT and load the matching actor. Mirrors the HTTP
    deps.get_current_user dispatch so business_agent / merchant tokens
    work on WebSocket too (the old code only handled support_agent
    and returned None for everyone else → close 1008 → HTTP 403)."""
    payload = decode_token(token)
    actor_kind = payload.get("actor_kind", "support_agent")
    actor_id = payload.get("actor_id") or payload.get("agent_id")
    with SessionLocal() as db:
        if actor_kind == "business_agent":
            ba = db.get(BusinessAgent, actor_id) if actor_id else None
            if not ba or not ba.status:
                return None
            return load_business_agent_user(ba.name, ba.id)
        if actor_kind == "merchant":
            m = db.get(Merchant, actor_id) if actor_id else None
            if not m or not m.status:
                return None
            return load_merchant_user(m.name, m.id)
        agent_id = payload.get("agent_id")
        agent = db.get(SupportAgent, agent_id) if agent_id else None
        if not agent or agent.status != "enabled":
            return None
        return load_current_user(db, agent)


@router.websocket("/replies")
async def replies_stream(ws: WebSocket, token: str = "") -> None:
    """Subscribe to incoming replies. Pass JWT via `?token=...` query param.
    Non-admins receive only events for accounts in their visible groups —
    enforced by filtering payload account_id against pre-loaded membership.
    """
    if not token:
        logger.warning("WS /replies rejected: no token")
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        user = _resolve_user(token)
    except Exception:
        logger.exception("WS /replies _resolve_user raised")
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if user is None:
        logger.warning("WS /replies rejected: _resolve_user returned None for token starting %s...", token[:20])
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    visible_account_ids: set[int] | None = None
    if not user.is_admin:
        from sqlalchemy import select

        from backend.app.models.account import AccountGroupMember

        with SessionLocal() as db:
            visible_account_ids = {
                row.account_id for row in db.scalars(
                    select(AccountGroupMember).where(
                        AccountGroupMember.group_id.in_(user.visible_group_ids() or [-1])
                    )
                )
            }

    await ws.accept()

    redis = get_redis()
    pubsub = redis.pubsub()
    try:
        pubsub.subscribe(REPLY_CHANNEL)
    except Exception:
        await ws.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    try:
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                # heartbeat: gives a chance to detect client disconnect
                try:
                    await ws.send_text('{"type":"ping"}')
                except WebSocketDisconnect:
                    break
                await asyncio.sleep(0)
                continue

            data = message.get("data")
            if not data:
                continue
            try:
                payload = json.loads(data)
            except (TypeError, ValueError):
                continue

            if visible_account_ids is not None:
                if payload.get("account_id") not in visible_account_ids:
                    continue

            try:
                await ws.send_text(json.dumps({"type": "reply", "payload": payload}, ensure_ascii=False))
            except WebSocketDisconnect:
                break
    finally:
        try:
            pubsub.close()
        except Exception:
            pass
