"""Orphan-thread (unmatched inbound) listing + messages + promote."""
from __future__ import annotations

import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.core.security import hash_password
from backend.app.main import app
from backend.app.models.account import Account
from backend.app.models.agent import SupportAgent
from backend.app.models.customer import Customer
from backend.app.models.message import MessageRecord


client = TestClient(app)


def _bootstrap_admin():
    client.post("/api/auth/bootstrap-admin",
                json={"username": "root", "password": "admin1234"})
    r = client.post("/api/auth/login",
                    json={"username": "root", "password": "admin1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class OrphanThreadsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        for model in (MessageRecord, Customer, Account, SupportAgent):
            for row in self.db.query(model).all():
                self.db.delete(row)
        self.db.commit()
        self.auth = _bootstrap_admin()

        # Account that received the inbound messages.
        acc = Account(
            tg_user_id="acc-rx", session_path="/tmp/x.session",
            status="active", enabled=True,
        )
        self.db.add(acc)
        self.db.flush()
        self.account_id = acc.id

        # Two orphan inbound senders + one bound-to-customer (should NOT
        # appear in the orphan list).
        cust = Customer(phone="+10000000001", consent=True, status="assigned",
                        assigned_account_id=acc.id)
        self.db.add(cust)
        self.db.flush()
        self.customer_id = cust.id

        self.db.add(MessageRecord(
            account_id=acc.id, customer_id=cust.id, phone="+10000000001",
            body_snapshot="bound to customer", direction="inbound",
            status="received", sent_at="2026-05-17T01:00:00",
        ))
        # Orphan #1 from +234, two messages.
        for i, text in enumerate(["你好", "在吗"]):
            self.db.add(MessageRecord(
                account_id=acc.id, customer_id=None, phone="+2340000000",
                target_tg_user_id="234001", body_snapshot=text,
                direction="inbound", status="received",
                sent_at=f"2026-05-17T01:0{i+1}:00",
            ))
        # Orphan #2 from +999, one message.
        self.db.add(MessageRecord(
            account_id=acc.id, customer_id=None, phone="+9990000000",
            target_tg_user_id="999001", body_snapshot="hello",
            direction="inbound", status="received", sent_at="2026-05-17T00:30:00",
        ))
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_list_drains_bucket_via_auto_promote(self) -> None:
        # The list endpoint now runs auto_promote as a side-effect, so a
        # request always returns an empty list — every orphan sender
        # gets a fresh Customer + retag instead of waiting for a manual
        # click. Aggregation logic still lives in case auto-promote
        # fails for some sender (e.g. missing account_id); it's
        # exercised by the per-sender test below.
        r = client.get("/api/orphan-threads", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), [])
        with SessionLocal() as db:
            promoted = {c.phone for c in db.scalars(
                select(Customer).where(Customer.source == "auto_promoted_from_inbound")
            )}
            self.assertEqual(promoted, {"tg:234001", "tg:999001"})

    def test_messages_endpoint_returns_thread_history(self) -> None:
        r = client.get(
            "/api/orphan-threads/messages",
            params={"account_id": self.account_id, "target_tg_user_id": "234001"},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.text)
        msgs = r.json()
        self.assertEqual([m["body_snapshot"] for m in msgs], ["你好", "在吗"])

    def test_messages_endpoint_requires_target_or_phone(self) -> None:
        r = client.get(
            "/api/orphan-threads/messages",
            params={"account_id": self.account_id},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 400, r.text)

    def test_promote_creates_customer_and_retags_messages(self) -> None:
        r = client.post(
            "/api/orphan-threads/promote",
            json={
                "account_id": self.account_id,
                "phone": "+2340000000",
                "target_tg_user_id": "234001",
                "name": "Loan",
            },
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["messages_retagged"], 2)
        self.assertEqual(body["customer"]["phone"], "+2340000000")

        # Orphan list now empty: the +234 sender was explicit-promoted,
        # the +999 sender is auto-promoted by the list-endpoint sweep.
        r = client.get("/api/orphan-threads", headers=self.auth)
        self.assertEqual(r.json(), [])

    def test_list_auto_promotes_remaining_orphan_senders(self) -> None:
        # Historical orphans (no matching Customer in the db) should be
        # auto-promoted on the next /orphan-threads load so the operator
        # doesn't have to click 转为客户 on every row. The 234001 and
        # 999001 senders seeded in setUp both lack a Customer; after the
        # GET, both should have Customers + the orphan list shrinks to
        # zero.
        r = client.get("/api/orphan-threads", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        # Auto-promotion happened — list now empty.
        self.assertEqual(r.json(), [])
        with SessionLocal() as db:
            created = {c.phone: c for c in db.scalars(
                select(Customer).where(Customer.source == "auto_promoted_from_inbound")
            )}
            self.assertIn("tg:234001", created)
            self.assertIn("tg:999001", created)
            self.assertEqual(created["tg:234001"].assigned_account_id, self.account_id)
            # All historical inbound rows for these senders got retagged.
            still_orphan = db.query(MessageRecord).filter(
                MessageRecord.customer_id.is_(None),
                MessageRecord.direction == "inbound",
                MessageRecord.target_tg_user_id.in_(["234001", "999001"]),
            ).count()
            self.assertEqual(still_orphan, 0)

    def test_list_retags_orphans_matching_tg_placeholder_customer(self) -> None:
        # Simulate the bug window: an inbound row from a sender whose
        # tg_user_id matches a `tg:<id>` promoted customer is still
        # sitting in the orphan bucket (because listen_worker matched
        # only by real phone before the fix). The list endpoint runs an
        # opportunistic rescan and should retag it on read.
        promoted = Customer(phone="tg:234001", name="prev-promoted",
                            consent=True, status="assigned",
                            assigned_account_id=self.account_id)
        self.db.add(promoted)
        self.db.commit()

        r = client.get("/api/orphan-threads", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        # Phase 1 retags 234001 messages to the pre-existing Customer;
        # Phase 2 auto-creates a Customer for 999001 → both buckets
        # drained → list is empty.
        self.assertEqual(r.json(), [])

        with SessionLocal() as db:
            retagged = db.query(MessageRecord).filter_by(
                target_tg_user_id="234001"
            ).all()
            self.assertTrue(retagged)
            for m in retagged:
                # Phase 1 binding wins — the pre-existing Customer, not
                # a freshly auto-promoted one.
                self.assertEqual(m.customer_id, promoted.id)

    def test_promote_rejects_duplicate_phone(self) -> None:
        client.post(
            "/api/orphan-threads/promote",
            json={"account_id": self.account_id, "phone": "+2340000000",
                  "target_tg_user_id": "234001"},
            headers=self.auth,
        )
        r = client.post(
            "/api/orphan-threads/promote",
            json={"account_id": self.account_id, "phone": "+2340000000",
                  "target_tg_user_id": "234001"},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 409, r.text)


if __name__ == "__main__":
    unittest.main()
