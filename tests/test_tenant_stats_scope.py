"""Statistics endpoints must respect tenant scope (R1 finish line).

A merchant calling /api/statistics/* must only see counts and rows from
its own accounts / customers / campaigns / message-records. Admin sees
everything (unchanged).
"""
from __future__ import annotations

import unittest
from datetime import UTC, datetime

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.core.security import hash_password
from backend.app.main import app
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.agent import SupportAgent
from backend.app.models.campaign import Campaign
from backend.app.models.customer import Customer, Friend
from backend.app.models.message import MessageRecord
from backend.app.models.tenant import BusinessAgent, Merchant


client = TestClient(app)


def _wipe(db, *models):
    for model in models:
        for row in db.query(model).all():
            db.delete(row)
    db.commit()


def _seed_two_tenants_with_data(db):
    ba = BusinessAgent(name="ba-s", password_hash=hash_password("pw"), status=True)
    db.add(ba)
    db.flush()
    m1 = Merchant(name="m-s1", password_hash=hash_password("pw"), status=True,
                  business_agent_id=ba.id, ports_total=10)
    m2 = Merchant(name="m-s2", password_hash=hash_password("pw"), status=True,
                  business_agent_id=ba.id, ports_total=10)
    db.add_all([m1, m2])
    db.flush()

    today = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")

    a1 = Account(tg_user_id="a-s1", session_path="/tmp/as1.session",
                 status="active", enabled=True, merchant_id=m1.id)
    a2 = Account(tg_user_id="a-s2", session_path="/tmp/as2.session",
                 status="active", enabled=True, merchant_id=m2.id)
    db.add_all([a1, a2])
    db.flush()

    g1 = AccountGroup(name="g-s1", code="gs1", enabled=True, merchant_id=m1.id)
    g2 = AccountGroup(name="g-s2", code="gs2", enabled=True, merchant_id=m2.id)
    db.add_all([g1, g2])
    db.flush()

    c1 = Customer(phone="+1000000001", merchant_id=m1.id)
    c2 = Customer(phone="+1000000002", merchant_id=m2.id)
    db.add_all([c1, c2])

    # 1 sent record for m1, 2 for m2.
    db.add(MessageRecord(account_id=a1.id, body_snapshot="hi", status="sent",
                         sent_at=today))
    db.add(MessageRecord(account_id=a2.id, body_snapshot="hi", status="sent",
                         sent_at=today))
    db.add(MessageRecord(account_id=a2.id, body_snapshot="hi", status="sent",
                         sent_at=today))
    db.commit()
    return m1, m2


def _login(path, username, password):
    r = client.post(path, json={"username": username, "password": password})
    return r.json()["access_token"]


class DashboardScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, MessageRecord, AccountGroupMember, Account, AccountGroup,
              Customer, Friend, Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_dashboard_excludes_other_tenants(self) -> None:
        m1, m2 = _seed_two_tenants_with_data(self.db)
        token = _login("/api/auth/merchant-login", "m-s1", "pw")
        r = client.get("/api/statistics/dashboard",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["accounts"]["total"], 1)
        self.assertEqual(body["customers"]["total"], 1)
        # m1 has 1 sent record (a-s1).
        self.assertEqual(body["messages"]["sent"], 1)

    def test_admin_dashboard_sees_everything(self) -> None:
        m1, m2 = _seed_two_tenants_with_data(self.db)
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
        body = r.json()
        self.assertEqual(body["accounts"]["total"], 2)
        self.assertEqual(body["customers"]["total"], 2)
        self.assertEqual(body["messages"]["sent"], 3)


class PerAccountStatsScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, MessageRecord, AccountGroupMember, Account, AccountGroup,
              Customer, Friend, Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_sees_only_own_accounts(self) -> None:
        m1, m2 = _seed_two_tenants_with_data(self.db)
        token = _login("/api/auth/merchant-login", "m-s1", "pw")
        r = client.get("/api/statistics/accounts",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        tg_ids = {row["tg_user_id"] for row in r.json()}
        self.assertEqual(tg_ids, {"a-s1"})


class PerGroupStatsScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, MessageRecord, AccountGroupMember, Account, AccountGroup,
              Customer, Friend, Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_sees_only_own_groups(self) -> None:
        m1, m2 = _seed_two_tenants_with_data(self.db)
        token = _login("/api/auth/merchant-login", "m-s1", "pw")
        r = client.get("/api/statistics/account-groups",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        names = {row["name"] for row in r.json()}
        self.assertEqual(names, {"g-s1"})


class TimeseriesScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, MessageRecord, AccountGroupMember, Account, AccountGroup,
              Customer, Friend, Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_timeseries_counts_own_messages_only(self) -> None:
        m1, m2 = _seed_two_tenants_with_data(self.db)
        token = _login("/api/auth/merchant-login", "m-s2", "pw")
        r = client.get("/api/statistics/timeseries",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        # m2 has 2 sent records; m1's 1 sent must not bleed in.
        self.assertEqual(r.json()["totals"]["sent"], 2)


class MessageDetailsScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, MessageRecord, AccountGroupMember, Account, AccountGroup,
              Customer, Friend, Campaign, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_message_details_excludes_other_tenants(self) -> None:
        m1, m2 = _seed_two_tenants_with_data(self.db)
        token = _login("/api/auth/merchant-login", "m-s1", "pw")
        r = client.get("/api/statistics/message-details",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        # m1 has 1 message record.
        self.assertEqual(len(r.json()), 1)


if __name__ == "__main__":
    unittest.main()
