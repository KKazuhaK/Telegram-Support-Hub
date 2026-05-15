from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission

ADMIN_ROLES = {"admin", "supervisor"}

# Map machine-readable permission attrs to user-facing Chinese labels.
PERM_LABELS = {
    "can_view_friends": "查看好友",
    "can_view_chats": "查看聊天",
    "can_send_message": "发送消息",
    "can_broadcast": "发起群发任务",
    "can_edit_profile": "修改账号资料",
    "can_delete_friend": "删除好友",
    "can_clear_chat": "清理聊天记录",
    "can_export_data": "导出数据",
}

ROLE_LABELS = {"admin": "管理员", "supervisor": "主管", "agent": "客服"}


def permission_denied_detail(attr: str) -> str:
    label = PERM_LABELS.get(attr, attr)
    return f"当前账号缺少『{label}』权限，请联系管理员升级"


@dataclass
class CurrentUser:
    agent_id: int
    username: str
    role: str
    account_group_ids: list[int] = field(default_factory=list)
    permissions: list[SupportAgentGroupPermission] = field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        return self.role in ADMIN_ROLES

    def can(self, attr: str) -> bool:
        if self.is_admin:
            return True
        return any(getattr(perm, attr, False) for perm in self.permissions)

    def can_in_group(self, group_id: int, attr: str) -> bool:
        if self.is_admin:
            return True
        for perm in self.permissions:
            if perm.account_group_id == group_id and getattr(perm, attr, False):
                return True
        return False

    def visible_group_ids(self) -> list[int]:
        return list(self.account_group_ids)


def load_current_user(db: Session, agent: SupportAgent) -> CurrentUser:
    perms = list(
        db.scalars(
            select(SupportAgentGroupPermission).where(SupportAgentGroupPermission.agent_id == agent.id)
        )
    )
    group_ids = [p.account_group_id for p in perms]
    return CurrentUser(
        agent_id=agent.id,
        username=agent.username,
        role=agent.role or "agent",
        account_group_ids=group_ids,
        permissions=perms,
    )
