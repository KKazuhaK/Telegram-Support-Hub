from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from backend.app.api.deps import CurrentUserDep, DbSession
from backend.app.models.quick_reply import QuickReply
from backend.app.services.audit import write_audit
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


class QuickReplyCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    category: str | None = None
    is_public: bool = False
    sort_order: int = 0


class QuickReplyUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=4000)
    category: str | None = None
    is_public: bool | None = None
    sort_order: int | None = None


def _can_manage_public(user) -> bool:
    # Only support_agent admin/supervisor can curate the shared library.
    # Merchants & business_agents only manage their own personal scripts.
    return user.actor_kind == "support_agent" and user.is_admin


def _visible_filter(user):
    """Build the WHERE clause: (own personal) OR (any public)."""
    return or_(
        QuickReply.is_public.is_(True),
        (QuickReply.actor_kind == user.actor_kind)
        & (QuickReply.actor_id == user.actor_id)
        & (QuickReply.is_public.is_(False)),
    )


@router.get("")
def list_quick_replies(
    db: DbSession, user: CurrentUserDep,
    scope: str | None = None,  # 'personal' | 'public' | None (=both)
    category: str | None = None,
) -> list[dict]:
    stmt = select(QuickReply)
    if scope == "personal":
        stmt = stmt.where(
            QuickReply.is_public.is_(False),
            QuickReply.actor_kind == user.actor_kind,
            QuickReply.actor_id == user.actor_id,
        )
    elif scope == "public":
        stmt = stmt.where(QuickReply.is_public.is_(True))
    else:
        stmt = stmt.where(_visible_filter(user))

    if category:
        stmt = stmt.where(QuickReply.category == category)

    stmt = stmt.order_by(QuickReply.sort_order.asc(), QuickReply.id.desc())
    return list_dict(list(db.scalars(stmt)))


@router.post("")
def create_quick_reply(
    payload: QuickReplyCreate, db: DbSession, user: CurrentUserDep,
) -> dict:
    if payload.is_public and not _can_manage_public(user):
        raise HTTPException(
            status_code=403,
            detail="只有管理员可以创建公共话术",
        )
    row = QuickReply(
        text=payload.text,
        category=payload.category,
        is_public=payload.is_public,
        sort_order=payload.sort_order,
        actor_kind=None if payload.is_public else user.actor_kind,
        actor_id=None if payload.is_public else user.actor_id,
    )
    db.add(row)
    db.flush()
    write_audit(db, actor=user, action="quick_reply.create",
                target_type="quick_reply", target_id=row.id,
                detail={"is_public": row.is_public, "category": row.category})
    db.commit()
    db.refresh(row)
    return to_dict(row)


def _get_owned(db: DbSession, user, qid: int) -> QuickReply:
    row = db.get(QuickReply, qid)
    if not row:
        # Hide existence — 404 not 403.
        raise HTTPException(status_code=404, detail="话术不存在")
    if row.is_public:
        if not _can_manage_public(user):
            raise HTTPException(status_code=404, detail="话术不存在")
    else:
        if row.actor_kind != user.actor_kind or row.actor_id != user.actor_id:
            raise HTTPException(status_code=404, detail="话术不存在")
    return row


@router.patch("/{qid}")
def update_quick_reply(
    qid: int, payload: QuickReplyUpdate, db: DbSession, user: CurrentUserDep,
) -> dict:
    row = _get_owned(db, user, qid)
    values = payload.model_dump(exclude_unset=True)
    # Disallow flipping is_public via patch unless caller could create it
    # in that mode — keeps the audit trail honest.
    if "is_public" in values and values["is_public"] and not _can_manage_public(user):
        raise HTTPException(status_code=403, detail="只有管理员可以发布公共话术")
    for k, v in values.items():
        setattr(row, k, v)
    write_audit(db, actor=user, action="quick_reply.update",
                target_type="quick_reply", target_id=row.id, detail=values)
    db.commit()
    db.refresh(row)
    return to_dict(row)


@router.delete("/{qid}")
def delete_quick_reply(qid: int, db: DbSession, user: CurrentUserDep) -> dict:
    row = _get_owned(db, user, qid)
    db.delete(row)
    write_audit(db, actor=user, action="quick_reply.delete",
                target_type="quick_reply", target_id=qid)
    db.commit()
    return {"deleted": True}
