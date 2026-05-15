import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.agent import SupportAgent
from backend.app.models.audit import AuditLog


class AuditLogsFilterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (AuditLog, SupportAgent):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        bootstrap = self.client.post(
            "/api/auth/bootstrap-admin",
            json={"username": "root", "password": "12345678"},
        )
        self.auth = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}

        with SessionLocal() as db:
            for action in (
                "auth.login",
                "customer.import",
                "customer.update",
                "export.customers",
                "export.campaign_messages",
                "account.import_zip",
                "campaign.create",
            ):
                db.add(AuditLog(action=action, actor_username="root", actor_role="admin"))
            db.commit()

    def test_exact_action_filter_still_works(self) -> None:
        rows = self.client.get(
            "/api/audit-logs?action=auth.login", headers=self.auth,
        ).json()
        # bootstrap-admin also writes an audit log of its own
        actions = {r["action"] for r in rows}
        self.assertEqual(actions, {"auth.login"})

    def test_action_prefix_filter_matches_import(self) -> None:
        rows = self.client.get(
            "/api/audit-logs?action_prefix=customer.import", headers=self.auth,
        ).json()
        self.assertTrue(all(r["action"].startswith("customer.import") for r in rows))
        # Picks up customer.import but not customer.update
        self.assertIn("customer.import", {r["action"] for r in rows})
        self.assertNotIn("customer.update", {r["action"] for r in rows})

    def test_action_prefix_for_export_category(self) -> None:
        rows = self.client.get(
            "/api/audit-logs?action_prefix=export.", headers=self.auth,
        ).json()
        actions = {r["action"] for r in rows}
        self.assertEqual(actions, {"export.customers", "export.campaign_messages"})

    def test_action_prefix_supports_pipe_separated_alternatives(self) -> None:
        # PRD section 10.2 "导入导出" lumps imports + exports together
        rows = self.client.get(
            "/api/audit-logs?action_prefix=customer.import|export.",
            headers=self.auth,
        ).json()
        actions = {r["action"] for r in rows}
        self.assertIn("customer.import", actions)
        self.assertIn("export.customers", actions)
        self.assertIn("export.campaign_messages", actions)
        self.assertNotIn("auth.login", actions)


if __name__ == "__main__":
    unittest.main()
