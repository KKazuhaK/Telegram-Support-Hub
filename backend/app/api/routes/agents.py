from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from backend.app.api.deps import DbSession
from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


class SupportAgentCreate(BaseModel):
    username: str
    nickname: str | None = None


class SupportAgentUpdate(BaseModel):
    nickname: str | None = None
    status: str | None = None
    online_status: str | None = None


class GroupPermissionInput(BaseModel):
    account_group_id: int
    can_view_friends: bool = True
    can_view_chats: bool = True
    can_send_message: bool = True
    can_broadcast: bool = False
    can_edit_profile: bool = False
    can_delete_friend: bool = False
    can_clear_chat: bool = False
    chat_scope: dict | None = Field(default_factory=lambda: {"all": True})


@router.get("")
def list_agents(db: DbSession) -> list[dict]:
    return list_dict(list(db.scalars(select(SupportAgent).order_by(SupportAgent.id.desc()))))


@router.post("")
def create_agent(payload: SupportAgentCreate, db: DbSession) -> dict:
    agent = SupportAgent(username=payload.username, nickname=payload.nickname)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return to_dict(agent)


@router.patch("/{agent_id}")
def update_agent(agent_id: int, payload: SupportAgentUpdate, db: DbSession) -> dict:
    agent = db.get(SupportAgent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="support agent not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, key, value)
    db.commit()
    db.refresh(agent)
    return to_dict(agent)


@router.get("/{agent_id}/account-group-permissions")
def list_group_permissions(agent_id: int, db: DbSession) -> list[dict]:
    if not db.get(SupportAgent, agent_id):
        raise HTTPException(status_code=404, detail="support agent not found")
    rows = list(
        db.scalars(
            select(SupportAgentGroupPermission)
            .where(SupportAgentGroupPermission.agent_id == agent_id)
            .order_by(SupportAgentGroupPermission.id.desc())
        )
    )
    return list_dict(rows)


@router.put("/{agent_id}/account-group-permissions")
def replace_group_permissions(agent_id: int, payload: list[GroupPermissionInput], db: DbSession) -> list[dict]:
    if not db.get(SupportAgent, agent_id):
        raise HTTPException(status_code=404, detail="support agent not found")
    db.execute(delete(SupportAgentGroupPermission).where(SupportAgentGroupPermission.agent_id == agent_id))
    rows: list[SupportAgentGroupPermission] = []
    for item in payload:
        row = SupportAgentGroupPermission(agent_id=agent_id, **item.model_dump())
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return list_dict(rows)
