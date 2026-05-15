from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission

ADMIN_ROLES = {"admin", "supervisor"}


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
