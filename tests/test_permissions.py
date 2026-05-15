import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from backend.app.models.account import AccountGroup
from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission
from backend.app.services.permissions import load_current_user


class PermissionsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()

    def tearDown(self) -> None:
        # cleanup
        for model in (SupportAgentGroupPermission, SupportAgent, AccountGroup):
            for row in self.db.query(model).all():
                self.db.delete(row)
        self.db.commit()
        self.db.close()

    def _make_agent(self, role="agent"):
        agent = SupportAgent(username=f"u-{role}", role=role, status="enabled", password_hash="x")
        self.db.add(agent)
        self.db.flush()
        return agent

    def test_admin_has_all_permissions(self) -> None:
        admin = self._make_agent(role="admin")
        self.db.commit()
        user = load_current_user(self.db, admin)
        self.assertTrue(user.is_admin)
        self.assertTrue(user.can("can_broadcast"))
        self.assertTrue(user.can_in_group(123, "can_send_message"))

    def test_agent_inherits_per_group_permissions(self) -> None:
        agent = self._make_agent(role="agent")
        group = AccountGroup(name="sales", code="sales")
        self.db.add(group)
        self.db.flush()
        self.db.add(SupportAgentGroupPermission(
            agent_id=agent.id, account_group_id=group.id,
            can_send_message=True, can_broadcast=False,
        ))
        self.db.commit()

        user = load_current_user(self.db, agent)
        self.assertFalse(user.is_admin)
        self.assertTrue(user.can("can_send_message"))
        self.assertFalse(user.can("can_broadcast"))
        self.assertTrue(user.can_in_group(group.id, "can_send_message"))
        self.assertFalse(user.can_in_group(group.id, "can_broadcast"))
        self.assertEqual(user.visible_group_ids(), [group.id])

    def test_agent_without_permissions_sees_nothing(self) -> None:
        agent = self._make_agent(role="agent")
        self.db.commit()
        user = load_current_user(self.db, agent)
        self.assertEqual(user.visible_group_ids(), [])
        self.assertFalse(user.can("can_send_message"))


if __name__ == "__main__":
    unittest.main()
