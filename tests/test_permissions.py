import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from backend.app.models.account import AccountGroup
from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission
from backend.app.services.permissions import (
    PERM_LABELS,
    ROLE_LABELS,
    load_current_user,
    permission_denied_detail,
)


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


class PermissionLabelsTestCase(unittest.TestCase):
    def test_permission_denied_uses_chinese_label(self) -> None:
        msg = permission_denied_detail("can_broadcast")
        self.assertIn("发起群发任务", msg)
        self.assertIn("管理员", msg)

    def test_unknown_attr_falls_back_to_attr(self) -> None:
        msg = permission_denied_detail("unknown_attr")
        self.assertIn("unknown_attr", msg)

    def test_role_labels_cover_known_roles(self) -> None:
        self.assertEqual(ROLE_LABELS["admin"], "管理员")
        self.assertEqual(ROLE_LABELS["agent"], "客服")
        self.assertEqual(ROLE_LABELS["supervisor"], "主管")

    def test_perm_labels_cover_every_supportagent_field(self) -> None:
        for attr in (
            "can_view_friends", "can_view_chats", "can_send_message",
            "can_broadcast", "can_edit_profile", "can_delete_friend",
            "can_clear_chat", "can_export_data",
        ):
            self.assertIn(attr, PERM_LABELS)


if __name__ == "__main__":
    unittest.main()
