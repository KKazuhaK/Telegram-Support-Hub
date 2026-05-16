"""Multi-tenant write paths (R1 — make tenants actually usable).

Until now tenant actors saw an empty system because no row got a
`merchant_id`. These tests pin down the auto-fill behavior on the
endpoints a merchant actually uses: customer import / mutation,
campaign create, friend list (scoped via Account JOIN).
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
from backend.app.models.customer import Customer, Friend
from backend.app.models.tenant import BusinessAgent, Merchant


client = TestClient(app)


def _wipe(db, *models):
    for model in models:
        for row in db.query(model).all():
            db.delete(row)
    db.commit()


def _seed(db):
    ba = BusinessAgent(name="ba-w", password_hash=hash_password("pw"), status=True)
    db.add(ba)
    db.flush()
    m1 = Merchant(name="m-w1", password_hash=hash_password("pw"), status=True,
                  business_agent_id=ba.id, ports_total=10)
    m2 = Merchant(name="m-w2", password_hash=hash_password("pw"), status=True,
                  business_agent_id=ba.id, ports_total=10)
    db.add_all([m1, m2])
    db.commit()
    return ba, m1, m2


def _login(path, username, password):
    r = client.post(path, json={"username": username, "password": password})
    return r.json()["access_token"]


class CustomerImportAutoFillTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup, Customer,
              Friend, Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_import_auto_sets_merchant_id(self) -> None:
        ba, m1, m2 = _seed(self.db)
        token = _login("/api/auth/merchant-login", "m-w1", "pw")

        r = client.post(
            "/api/customers/import",
            json={"text": "+11111110000,Alice", "assume_consent": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r.status_code, 200, r.text)

        with SessionLocal() as db:
            row = db.query(Customer).filter(Customer.phone == "+11111110000").one()
            self.assertEqual(row.merchant_id, m1.id)

        # And the merchant can immediately see it in their own list.
        r = client.get("/api/customers", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200)
        phones = {row["phone"] for row in r.json()}
        self.assertIn("+11111110000", phones)

    def test_admin_import_leaves_merchant_id_null(self) -> None:
        # Admin imports without a merchant context — the row stays
        # unscoped (admin-managed legacy bucket).
        admin = SupportAgent(
            username="admin", nickname="admin",
            password_hash=hash_password("admin1234"),
            role="admin", status="enabled",
        )
        self.db.add(admin)
        self.db.commit()
        token = _login("/api/auth/login", "admin", "admin1234")

        r = client.post(
            "/api/customers/import",
            json={"text": "+12222220000,Bob", "assume_consent": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        with SessionLocal() as db:
            row = db.query(Customer).filter(Customer.phone == "+12222220000").one()
            self.assertIsNone(row.merchant_id)


class CampaignCreateAutoFillTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup, Customer,
              Friend, Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_creates_campaign_with_own_merchant_id(self) -> None:
        ba, m1, m2 = _seed(self.db)
        # Merchant owns an account-group + an active account so the
        # eligible-account count > 0.
        g = AccountGroup(name="m1-g", code="m1g", enabled=True, merchant_id=m1.id)
        self.db.add(g)
        self.db.flush()
        a = Account(tg_user_id="m1a", session_path="/tmp/m1a.session",
                    status="active", enabled=True, merchant_id=m1.id)
        self.db.add(a)
        self.db.flush()
        self.db.add(AccountGroupMember(account_id=a.id, group_id=g.id, is_primary=True))
        self.db.commit()
        gid = g.id

        token = _login("/api/auth/merchant-login", "m-w1", "pw")
        r = client.post(
            "/api/campaigns",
            json={
                "name": "merchant-only-op",
                "task_kind": "batch_op",
                "operation_target": "detect_mutual",
                "target_type": "detect_mutual",
                "account_group_ids": [gid],
                "send_settings": {},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        cid = r.json()["id"]

        with SessionLocal() as db:
            row = db.get(Campaign, cid)
            self.assertEqual(row.merchant_id, m1.id)
            self.assertEqual(row.created_by, "m-w1")


class FriendListJoinScopeTestCase(unittest.TestCase):
    """Friend has no merchant_id column of its own — it inherits scope
    via Friend.account_id → Account.merchant_id. /api/customers/friends
    must JOIN so a merchant only sees friends of their own accounts."""

    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup, Customer,
              Friend, Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_sees_only_friends_of_own_accounts(self) -> None:
        ba, m1, m2 = _seed(self.db)
        a1 = Account(tg_user_id="a-m1", session_path="/tmp/a1.session",
                     status="active", enabled=True, merchant_id=m1.id)
        a2 = Account(tg_user_id="a-m2", session_path="/tmp/a2.session",
                     status="active", enabled=True, merchant_id=m2.id)
        self.db.add_all([a1, a2])
        self.db.flush()

        f1 = Friend(account_id=a1.id, tg_user_id="friend-of-m1", status="new")
        f2 = Friend(account_id=a2.id, tg_user_id="friend-of-m2", status="new")
        self.db.add_all([f1, f2])
        self.db.commit()

        token = _login("/api/auth/merchant-login", "m-w1", "pw")
        r = client.get("/api/customers/friends",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        ids = {row["tg_user_id"] for row in r.json()}
        self.assertEqual(ids, {"friend-of-m1"})


if __name__ == "__main__":
    unittest.main()
