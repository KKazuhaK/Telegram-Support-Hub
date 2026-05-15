from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from backend.app.api.deps import AdminDep, DbSession
from backend.app.core.security import hash_password
from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission
from backend.app.services.audit import write_audit
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


class SupportAgentCreate(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    nickname: str | None = None
    password: str = Field(min_length=8, max_length=200)
    role: str = "agent"


class SupportAgentUpdate(BaseModel):
    nickname: str | None = None
    status: str | None = None
    online_status: str | None = None
    role: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


class GroupPermissionInput(BaseModel):
    account_group_id: int
    can_view_friends: bool = True
    can_view_chats: bool = True
    can_send_message: bool = True
    can_broadcast: bool = False
    can_edit_profile: bool = False
    can_delete_friend: bool = False
    can_clear_chat: bool = False
    can_export_data: bool = False
    chat_scope: dict | None = Field(default_factory=lambda: {"all": True})


@router.get("")
def list_agents(db: DbSession, _: AdminDep) -> list[dict]:
    return list_dict(list(db.scalars(select(SupportAgent).order_by(SupportAgent.id.desc()))))


@router.post("")
def create_agent(payload: SupportAgentCreate, db: DbSession, admin: AdminDep) -> dict:
    if db.scalar(select(SupportAgent).where(SupportAgent.username == payload.username)):
        raise HTTPException(status_code=409, detail="该用户名已被占用")

    agent = SupportAgent(
        username=payload.username,
        nickname=payload.nickname,
        role=payload.role,
        password_hash=hash_password(payload.password),
    )
    db.add(agent)
    db.flush()
    write_audit(db, actor=admin, action="agent.create",
                target_type="support_agent", target_id=agent.id,
                detail={"username": agent.username, "role": agent.role})
    db.commit()
    db.refresh(agent)
    return to_dict(agent)


@router.patch("/{agent_id}")
def update_agent(agent_id: int, payload: SupportAgentUpdate, db: DbSession, admin: AdminDep) -> dict:
    agent = db.get(SupportAgent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="客服账号不存在")
    values = payload.model_dump(exclude_unset=True)
    if "password" in values:
        plain = values.pop("password")
        if plain:
            agent.password_hash = hash_password(plain)
    for key, value in values.items():
        setattr(agent, key, value)
    write_audit(db, actor=admin, action="agent.update",
                target_type="support_agent", target_id=agent.id,
                detail={k: v for k, v in values.items() if k != "password_hash"})
    db.commit()
    db.refresh(agent)
    return to_dict(agent)


@router.get("/{agent_id}/account-group-permissions")
def list_group_permissions(agent_id: int, db: DbSession, _: AdminDep) -> list[dict]:
    if not db.get(SupportAgent, agent_id):
        raise HTTPException(status_code=404, detail="客服账号不存在")
    rows = list(
        db.scalars(
            select(SupportAgentGroupPermission)
            .where(SupportAgentGroupPermission.agent_id == agent_id)
            .order_by(SupportAgentGroupPermission.id.desc())
        )
    )
    return list_dict(rows)


@router.put("/{agent_id}/account-group-permissions")
def replace_group_permissions(agent_id: int, payload: list[GroupPermissionInput], db: DbSession, admin: AdminDep) -> list[dict]:
    if not db.get(SupportAgent, agent_id):
        raise HTTPException(status_code=404, detail="客服账号不存在")
    db.execute(delete(SupportAgentGroupPermission).where(SupportAgentGroupPermission.agent_id == agent_id))
    rows: list[SupportAgentGroupPermission] = []
    for item in payload:
        row = SupportAgentGroupPermission(agent_id=agent_id, **item.model_dump())
        db.add(row)
        rows.append(row)
    write_audit(db, actor=admin, action="agent.replace_permissions",
                target_type="support_agent", target_id=agent_id,
                detail={"groups": [item.account_group_id for item in payload]})
    db.commit()
    for row in rows:
        db.refresh(row)
    return list_dict(rows)
