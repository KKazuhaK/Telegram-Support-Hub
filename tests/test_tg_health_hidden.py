"""TG account health is operator-only visibility (PRD compliance).

Merchants and business_agents must not see whether individual TG
accounts are alive — that's the support team's operational concern.
Specifically we hide: status, last_error, last_login_at, enabled,
avatar_status. Aggregate counts also collapse to just total + available
(active + imported) so the tenant can't infer how many are 'broken' or
when we're back-filling.

support_agent (admin / supervisor / agent) sees everything as before.
"""
from __future__ import annotations

import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.core.security import hash_password
from backend.app.main import app
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.agent import SupportAgent
from backend.app.models.tenant import BusinessAgent, Merchant


client = TestClient(app)


def _wipe(db, *models):
    for model in models:
        for row in db.query(model).all():
            db.delete(row)
    db.commit()


def _seed(db):
    ba = BusinessAgent(name="ba-h", password_hash=hash_password("pw"), status=True)
    db.add(ba)
    db.flush()
    m1 = Merchant(name="m-h1", password_hash=hash_password("pw"), status=True,
                  business_agent_id=ba.id, ports_total=10)
    db.add(m1)
    db.flush()
    # Mix of statuses so the breakdown / sanitization rules have signal.
    for tg, status, enabled in [
        ("acc-act-1", "active",   True),
        ("acc-act-2", "active",   True),
        ("acc-err",   "error",    True),
        ("acc-imp",   "imported", True),
        ("acc-disb",  "active",   False),
    ]:
        db.add(Account(
            tg_user_id=tg, session_path=f"/tmp/{tg}.session",
            status=status, enabled=enabled, last_login_at="2026-05-15T00:00:00+00:00",
            last_error="boom" if status == "error" else None,
            merchant_id=m1.id,
        ))
    db.commit()
    return m1


def _login(path, username, password):
    r = client.post(path, json={"username": username, "password": password})
    return r.json()["access_token"]


HEALTH_FIELDS = {"status", "last_error", "last_login_at", "enabled", "avatar_status"}


class AccountListHealthHiddenTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup,
              SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_account_list_strips_health_fields(self) -> None:
        _seed(self.db)
        token = _login("/api/auth/merchant-login", "m-h1", "pw")
        r = client.get("/api/accounts",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        rows = r.json()
        self.assertTrue(rows, "merchant should still see its own accounts (sanitized)")
        for row in rows:
            for field in HEALTH_FIELDS:
                self.assertNotIn(
                    field, row,
                    f"merchant must not see health field '{field}', got {row}",
                )

    def test_business_agent_account_list_strips_health_fields(self) -> None:
        _seed(self.db)
        token = _login("/api/auth/business-login", "ba-h", "pw")
        r = client.get("/api/accounts",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        for row in r.json():
            for field in HEALTH_FIELDS:
                self.assertNotIn(field, row)

    def test_admin_still_sees_health_fields(self) -> None:
        _seed(self.db)
        admin = SupportAgent(
            username="admin", nickname="admin",
            password_hash=hash_password("admin1234"),
            role="admin", status="enabled",
        )
        self.db.add(admin)
        self.db.commit()
        token = _login("/api/auth/login", "admin", "admin1234")
        r = client.get("/api/accounts",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        for row in r.json():
            self.assertIn("status", row)
            self.assertIn("enabled", row)


class DashboardAccountsBreakdownHiddenTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup,
              SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_dashboard_shows_total_and_available_only(self) -> None:
        _seed(self.db)
        token = _login("/api/auth/merchant-login", "m-h1", "pw")
        r = client.get("/api/statistics/dashboard",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        accs = r.json()["accounts"]
        # Only 'total' and 'available' should appear; no error/limited/imported
        # breakdown leaking inventory state.
        self.assertEqual(set(accs.keys()), {"total", "available"})
        self.assertEqual(accs["total"], 5)
        # available = active + imported, disabled excluded. We seeded
        # 2 active + 1 imported + 1 error + 1 (active but disabled) = 3.
        self.assertEqual(accs["available"], 3)

    def test_admin_dashboard_still_shows_status_breakdown(self) -> None:
        _seed(self.db)
        admin = SupportAgent(
            username="admin", nickname="admin",
            password_hash=hash_password("admin1234"),
            role="admin", status="enabled",
        )
        self.db.add(admin)
        self.db.commit()
        token = _login("/api/auth/login", "admin", "admin1234")
        r = client.get("/api/statistics/dashboard",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        accs = r.json()["accounts"]
        # Admin still sees the operational breakdown.
        self.assertIn("active", accs)
        self.assertIn("error", accs)
        self.assertIn("imported_pending", accs)


class PerAccountStatsHealthHiddenTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup,
              SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_per_account_stats_strips_health_fields(self) -> None:
        _seed(self.db)
        token = _login("/api/auth/merchant-login", "m-h1", "pw")
        r = client.get("/api/statistics/accounts",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        for row in r.json():
            for field in HEALTH_FIELDS:
                self.assertNotIn(field, row)


if __name__ == "__main__":
    unittest.main()
