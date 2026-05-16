"""Tenant view of audit logs.

A merchant can see audit entries they themselves wrote (filtered by
actor_kind + actor_id). Admin sees everything. Cross-tenant entries are
hidden from a tenant. Used so a 商户 can audit their own actions
without exposing competitors' activity.
"""
from __future__ import annotations

import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.core.security import hash_password
from backend.app.main import app
from backend.app.models.agent import SupportAgent
from backend.app.models.audit import AuditLog
from backend.app.models.customer import Customer
from backend.app.models.tenant import BusinessAgent, Merchant


client = TestClient(app)


def _wipe(db, *models):
    for model in models:
        for row in db.query(model).all():
            db.delete(row)
    db.commit()


def _seed(db):
    ba = BusinessAgent(name="ba-au", password_hash=hash_password("pw"), status=True)
    db.add(ba)
    db.flush()
    m1 = Merchant(name="m-au1", password_hash=hash_password("pw"), status=True,
                  business_agent_id=ba.id)
    m2 = Merchant(name="m-au2", password_hash=hash_password("pw"), status=True,
                  business_agent_id=ba.id)
    db.add_all([m1, m2])
    db.commit()
    return ba, m1, m2


def _login(path, username, password):
    r = client.post(path, json={"username": username, "password": password})
    return r.json()["access_token"]


class AuditTenantViewTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AuditLog, Customer, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_audit_action_is_visible_to_self(self) -> None:
        ba, m1, m2 = _seed(self.db)
        token = _login("/api/auth/merchant-login", "m-au1", "pw")
        # Trigger a tenant-side action that writes audit.
        r = client.post(
            "/api/customers/import",
            json={"text": "+19990001111,Alice", "assume_consent": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r.status_code, 200, r.text)

        # Merchant calls /api/audit-logs and sees only their own audit row.
        r = client.get("/api/audit-logs",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        rows = r.json()
        actions = [row["action"] for row in rows]
        self.assertIn("customer.import", actions)

        # All visible rows must be authored by this merchant — no leakage.
        for row in rows:
            self.assertEqual(row.get("actor_kind"), "merchant")
            self.assertEqual(row.get("actor_id"), m1.id)

    def test_merchant_cannot_see_admin_or_other_tenant_audit(self) -> None:
        ba, m1, m2 = _seed(self.db)
        admin = SupportAgent(
            username="admin", nickname="admin",
            password_hash=hash_password("admin1234"),
            role="admin", status="enabled",
        )
        self.db.add(admin)
        self.db.flush()
        # Hand-write two foreign audit rows so we don't depend on
        # specific mutation paths to populate them.
        self.db.add(AuditLog(
            actor_id=admin.id, actor_username="admin", actor_role="admin",
            actor_kind="support_agent", action="account.import_zip",
        ))
        self.db.add(AuditLog(
            actor_id=m2.id, actor_username="m-au2", actor_role="merchant",
            actor_kind="merchant", action="customer.import",
        ))
        self.db.commit()

        token = _login("/api/auth/merchant-login", "m-au1", "pw")
        r = client.get("/api/audit-logs",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        for row in r.json():
            self.assertEqual(row.get("actor_kind"), "merchant")
            self.assertEqual(row.get("actor_id"), m1.id)

    def test_admin_sees_everything(self) -> None:
        ba, m1, m2 = _seed(self.db)
        admin = SupportAgent(
            username="admin", nickname="admin",
            password_hash=hash_password("admin1234"),
            role="admin", status="enabled",
        )
        self.db.add(admin)
        self.db.commit()

        # Seed a merchant-authored row and an admin-authored row.
        self.db.add(AuditLog(
            actor_id=m1.id, actor_username="m-au1", actor_role="merchant",
            actor_kind="merchant", action="customer.import",
        ))
        self.db.add(AuditLog(
            actor_id=admin.id, actor_username="admin", actor_role="admin",
            actor_kind="support_agent", action="account.import_zip",
        ))
        self.db.commit()

        token = _login("/api/auth/login", "admin", "admin1234")
        r = client.get("/api/audit-logs",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        actions = {row["action"] for row in r.json()}
        self.assertIn("customer.import", actions)
        self.assertIn("account.import_zip", actions)


if __name__ == "__main__":
    unittest.main()
