"""R1 slice 2 — tenant scope filtering on list APIs.

Each scoped row carries `merchant_id`. Visibility rules:
  - support_agent (admin/supervisor/agent): unchanged — see all (subject
    to per-group permissions which already exist).
  - merchant actor: only rows where `merchant_id == self.actor_id`.
  - business_agent actor: rows where `merchant_id` belongs to a merchant
    owned by this business agent.
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
from backend.app.models.customer import Customer
from backend.app.models.tenant import BusinessAgent, Merchant


client = TestClient(app)


def _wipe(db, *models):
    for model in models:
        for row in db.query(model).all():
            db.delete(row)
    db.commit()


def _seed_two_merchants(db):
    ba = BusinessAgent(name="ba-1", password_hash=hash_password("pw"), status=True)
    db.add(ba)
    db.flush()
    other_ba = BusinessAgent(name="ba-2", password_hash=hash_password("pw"), status=True)
    db.add(other_ba)
    db.flush()
    m1 = Merchant(name="m-1", password_hash=hash_password("pw"), status=True,
                  business_agent_id=ba.id)
    m2 = Merchant(name="m-2", password_hash=hash_password("pw"), status=True,
                  business_agent_id=other_ba.id)
    db.add_all([m1, m2])
    db.commit()
    return ba, other_ba, m1, m2


class AccountTenantScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, Customer, AccountGroupMember, Account, AccountGroup,
              SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def _login(self, path, username, password) -> str:
        r = client.post(path, json={"username": username, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["access_token"]

    def test_merchant_sees_no_accounts(self) -> None:
        # TG account list is back-office only — tenants get [] regardless
        # of merchant_id matches. Override the older "see only own" rule
        # because the operator decided TG inventory is fully hidden.
        ba, other_ba, m1, m2 = _seed_two_merchants(self.db)
        a1 = Account(tg_user_id="m1-acc", session_path="/tmp/m1.session",
                     status="active", enabled=True, merchant_id=m1.id)
        a2 = Account(tg_user_id="m2-acc", session_path="/tmp/m2.session",
                     status="active", enabled=True, merchant_id=m2.id)
        self.db.add_all([a1, a2])
        self.db.commit()

        token = self._login("/api/auth/merchant-login", "m-1", "pw")
        r = client.get("/api/accounts", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), [])

    def test_business_agent_sees_no_accounts(self) -> None:
        # Same blanket invisibility for business_agent. They oversee the
        # commercial relationship; TG infra is platform admin's concern.
        ba, other_ba, m1, m2 = _seed_two_merchants(self.db)
        m3 = Merchant(name="m-3", password_hash=hash_password("pw"), status=True,
                      business_agent_id=ba.id)
        self.db.add(m3)
        self.db.flush()
        for tg, mid in [("m1-acc", m1.id), ("m2-acc", m2.id), ("m3-acc", m3.id)]:
            self.db.add(Account(
                tg_user_id=tg, session_path=f"/tmp/{tg}.session",
                status="active", enabled=True, merchant_id=mid,
            ))
        self.db.commit()

        token = self._login("/api/auth/business-login", "ba-1", "pw")
        r = client.get("/api/accounts", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), [])

    def test_admin_sees_all_accounts_including_unscoped(self) -> None:
        ba, other_ba, m1, m2 = _seed_two_merchants(self.db)
        admin = SupportAgent(
            username="admin", nickname="admin",
            password_hash=hash_password("admin1234"),
            role="admin", status="enabled",
        )
        self.db.add(admin)
        # Unscoped account (merchant_id=None) — represents legacy data.
        unscoped = Account(tg_user_id="legacy-acc", session_path="/tmp/x.session",
                           status="active", enabled=True)
        scoped = Account(tg_user_id="m1-acc", session_path="/tmp/m1.session",
                         status="active", enabled=True, merchant_id=m1.id)
        self.db.add_all([unscoped, scoped])
        self.db.commit()

        token = self._login("/api/auth/login", "admin", "admin1234")
        r = client.get("/api/accounts", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        ids = {row["tg_user_id"] for row in r.json()}
        self.assertIn("legacy-acc", ids)
        self.assertIn("m1-acc", ids)


class CustomerTenantScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, Customer, AccountGroupMember, Account, AccountGroup,
              SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_sees_only_own_customers(self) -> None:
        ba = BusinessAgent(name="ba-c", password_hash=hash_password("pw"), status=True)
        self.db.add(ba)
        self.db.flush()
        m1 = Merchant(name="mc-1", password_hash=hash_password("pw"), status=True,
                      business_agent_id=ba.id)
        m2 = Merchant(name="mc-2", password_hash=hash_password("pw"), status=True,
                      business_agent_id=ba.id)
        self.db.add_all([m1, m2])
        self.db.commit()

        c1 = Customer(phone="+10000001", merchant_id=m1.id)
        c2 = Customer(phone="+10000002", merchant_id=m2.id)
        self.db.add_all([c1, c2])
        self.db.commit()

        r = client.post("/api/auth/merchant-login",
                        json={"username": "mc-1", "password": "pw"})
        token = r.json()["access_token"]
        r = client.get("/api/customers", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        items = body if isinstance(body, list) else body.get("items", [])
        phones = {row["phone"] for row in items}
        self.assertEqual(phones, {"+10000001"})


if __name__ == "__main__":
    unittest.main()
