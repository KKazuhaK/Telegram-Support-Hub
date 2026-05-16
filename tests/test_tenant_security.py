"""Security tests for multi-tenant isolation (R1 fixes).

These tests pin down the rules the audit revealed were missing:

  - merchant list / business-agent list must scope to the calling actor
    (a merchant can only see itself; a business_agent only its merchants)
  - campaigns / account-groups / statistics lists must scope by
    merchant_id
  - mutation endpoints (customers PATCH/DELETE, campaign lifecycle)
    must refuse to touch rows belonging to another tenant (IDOR)
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
from backend.app.models.campaign import Campaign
from backend.app.models.customer import Customer
from backend.app.models.tenant import BusinessAgent, Merchant


client = TestClient(app)


def _wipe(db, *models):
    for model in models:
        for row in db.query(model).all():
            db.delete(row)
    db.commit()


def _seed_two_tenants(db):
    ba1 = BusinessAgent(name="ba-1", password_hash=hash_password("pw"), status=True)
    ba2 = BusinessAgent(name="ba-2", password_hash=hash_password("pw"), status=True)
    db.add_all([ba1, ba2])
    db.flush()
    m1 = Merchant(name="m-1", password_hash=hash_password("pw"), status=True,
                  business_agent_id=ba1.id, ports_total=10)
    m2 = Merchant(name="m-2", password_hash=hash_password("pw"), status=True,
                  business_agent_id=ba2.id, ports_total=10)
    db.add_all([m1, m2])
    db.commit()
    return ba1, ba2, m1, m2


def _login(path, username, password):
    r = client.post(path, json={"username": username, "password": password})
    return r.json()["access_token"]


class MerchantListScopeTestCase(unittest.TestCase):
    """A merchant must only see itself in /api/merchants. A business_agent
    must only see merchants it owns."""

    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup, Customer,
              Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_only_sees_self(self) -> None:
        ba1, ba2, m1, m2 = _seed_two_tenants(self.db)
        token = _login("/api/auth/merchant-login", "m-1", "pw")
        r = client.get("/api/merchants", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        names = {row["name"] for row in r.json()}
        self.assertEqual(names, {"m-1"})

    def test_business_agent_only_sees_own_merchants(self) -> None:
        ba1, ba2, m1, m2 = _seed_two_tenants(self.db)
        token = _login("/api/auth/business-login", "ba-1", "pw")
        r = client.get("/api/merchants", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        names = {row["name"] for row in r.json()}
        self.assertEqual(names, {"m-1"})


class BusinessAgentListScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup, Customer,
              Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_cannot_enumerate_business_agents(self) -> None:
        # A merchant has no business listing other tenants' resellers.
        ba1, ba2, m1, m2 = _seed_two_tenants(self.db)
        token = _login("/api/auth/merchant-login", "m-1", "pw")
        r = client.get("/api/business-agents", headers={"Authorization": f"Bearer {token}"})
        # Must be either 403 (forbidden) or 200 with an empty list — both
        # block the leak. We accept either to keep the contract flexible.
        if r.status_code == 200:
            self.assertEqual(r.json(), [])
        else:
            self.assertEqual(r.status_code, 403)

    def test_business_agent_only_sees_self(self) -> None:
        ba1, ba2, m1, m2 = _seed_two_tenants(self.db)
        token = _login("/api/auth/business-login", "ba-1", "pw")
        r = client.get("/api/business-agents", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        names = {row["name"] for row in r.json()}
        self.assertEqual(names, {"ba-1"})


class CampaignListScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup, Customer,
              Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_sees_only_own_campaigns(self) -> None:
        ba1, ba2, m1, m2 = _seed_two_tenants(self.db)
        c1 = Campaign(name="m1-broadcast", status="draft", merchant_id=m1.id)
        c2 = Campaign(name="m2-broadcast", status="draft", merchant_id=m2.id)
        self.db.add_all([c1, c2])
        self.db.commit()

        token = _login("/api/auth/merchant-login", "m-1", "pw")
        r = client.get("/api/campaigns", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        items = body if isinstance(body, list) else body.get("items", [])
        names = {row["name"] for row in items}
        self.assertEqual(names, {"m1-broadcast"})


class AccountGroupListScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup, Customer,
              Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_sees_only_own_groups(self) -> None:
        ba1, ba2, m1, m2 = _seed_two_tenants(self.db)
        g1 = AccountGroup(name="m1-grp", code="m1g", enabled=True, merchant_id=m1.id)
        g2 = AccountGroup(name="m2-grp", code="m2g", enabled=True, merchant_id=m2.id)
        self.db.add_all([g1, g2])
        self.db.commit()

        token = _login("/api/auth/merchant-login", "m-1", "pw")
        r = client.get("/api/account-groups", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        names = {row["name"] for row in r.json()}
        self.assertEqual(names, {"m1-grp"})


class CustomerMutationIDORTestCase(unittest.TestCase):
    """PATCH / DELETE /api/customers/{id} must refuse to touch a customer
    owned by another tenant."""

    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup, Customer,
              Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_cannot_patch_other_tenants_customer(self) -> None:
        ba1, ba2, m1, m2 = _seed_two_tenants(self.db)
        other = Customer(phone="+19999999", merchant_id=m2.id)
        self.db.add(other)
        self.db.commit()
        other_id = other.id

        token = _login("/api/auth/merchant-login", "m-1", "pw")
        r = client.patch(f"/api/customers/{other_id}",
                         json={"name": "hijacked"},
                         headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 404, r.text)
        # Original row untouched.
        with SessionLocal() as db:
            self.assertNotEqual(db.get(Customer, other_id).name, "hijacked")

    def test_merchant_cannot_delete_other_tenants_customer(self) -> None:
        ba1, ba2, m1, m2 = _seed_two_tenants(self.db)
        other = Customer(phone="+18888888", merchant_id=m2.id)
        self.db.add(other)
        self.db.commit()
        other_id = other.id

        token = _login("/api/auth/merchant-login", "m-1", "pw")
        r = client.delete(f"/api/customers/{other_id}",
                          headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 404, r.text)
        with SessionLocal() as db:
            self.assertIsNotNone(db.get(Customer, other_id))


class CampaignLifecycleIDORTestCase(unittest.TestCase):
    """start / pause / resume / cancel must refuse to touch a foreign
    tenant's campaign."""

    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup, Customer,
              Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_cannot_cancel_other_tenants_campaign(self) -> None:
        ba1, ba2, m1, m2 = _seed_two_tenants(self.db)
        c = Campaign(name="m2-secret", status="running", merchant_id=m2.id,
                     task_kind="broadcast", operation_target="customer_broadcast",
                     target_type="customer_broadcast")
        self.db.add(c)
        self.db.commit()
        cid = c.id

        token = _login("/api/auth/merchant-login", "m-1", "pw")
        r = client.post(f"/api/campaigns/{cid}/cancel",
                        headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 404, r.text)
        with SessionLocal() as db:
            # Status not changed by the IDOR attempt.
            self.assertEqual(db.get(Campaign, cid).status, "running")


if __name__ == "__main__":
    unittest.main()
