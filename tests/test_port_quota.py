"""R2 — port quota consumption + expiry check.

When an account is activated under a merchant, the merchant's
`ports_used` counter must reflect the number of active accounts and the
operation must fail if it would exceed `ports_total` or if
`ports_expires_at` is in the past.
"""
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.core.security import hash_password
from backend.app.main import app
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.agent import SupportAgent
from backend.app.models.tenant import BusinessAgent, Merchant
from backend.app.services.port_quota import (
    QuotaError,
    check_quota_for_activation,
    recompute_merchant_ports,
)


client = TestClient(app)


def _wipe(db, *models):
    for model in models:
        for row in db.query(model).all():
            db.delete(row)
    db.commit()


def _make_merchant(db, *, ports_total=2, expires_at=None):
    m = Merchant(
        name=f"m-{datetime.now(UTC).timestamp()}",
        password_hash=hash_password("pw"),
        status=True,
        ports_total=ports_total,
        ports_used=0,
        ports_expires_at=expires_at,
    )
    db.add(m)
    db.commit()
    return m


def _make_account(db, *, merchant_id, status="paused", suffix="x"):
    a = Account(
        tg_user_id=f"acc-{merchant_id}-{suffix}",
        session_path=f"/tmp/{suffix}.session",
        status=status,
        enabled=True,
        merchant_id=merchant_id,
    )
    db.add(a)
    db.commit()
    return a


class RecomputePortsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_counts_only_active_accounts(self) -> None:
        m = _make_merchant(self.db, ports_total=10)
        _make_account(self.db, merchant_id=m.id, status="active", suffix="a")
        _make_account(self.db, merchant_id=m.id, status="active", suffix="b")
        _make_account(self.db, merchant_id=m.id, status="paused", suffix="c")
        _make_account(self.db, merchant_id=m.id, status="error", suffix="d")

        used = recompute_merchant_ports(self.db, m.id)
        self.assertEqual(used, 2)
        self.db.refresh(m)
        self.assertEqual(m.ports_used, 2)


class CheckQuotaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_allows_when_under_quota(self) -> None:
        m = _make_merchant(self.db, ports_total=3)
        _make_account(self.db, merchant_id=m.id, status="active", suffix="a")
        # Activating one more (now 2 of 3) — fine.
        check_quota_for_activation(self.db, m.id, additional=1)

    def test_rejects_when_quota_exceeded(self) -> None:
        m = _make_merchant(self.db, ports_total=2)
        _make_account(self.db, merchant_id=m.id, status="active", suffix="a")
        _make_account(self.db, merchant_id=m.id, status="active", suffix="b")
        with self.assertRaises(QuotaError):
            check_quota_for_activation(self.db, m.id, additional=1)

    def test_rejects_when_expired(self) -> None:
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        m = _make_merchant(self.db, ports_total=10, expires_at=past)
        with self.assertRaises(QuotaError):
            check_quota_for_activation(self.db, m.id, additional=1)

    def test_no_op_for_account_without_merchant(self) -> None:
        # Legacy / admin-managed accounts have merchant_id=None: passing
        # None should short-circuit to allow.
        check_quota_for_activation(self.db, None, additional=5)

    def test_admin_account_with_unlimited_total_zero_means_unlimited(self) -> None:
        # ports_total=0 used to mean "uninitialized" — treat as unlimited so
        # legacy merchants without configured quota don't get locked out.
        m = _make_merchant(self.db, ports_total=0)
        check_quota_for_activation(self.db, m.id, additional=10)


class BatchActivateQuotaTestCase(unittest.TestCase):
    """Account batch endpoint must refuse to activate accounts when the
    merchant quota would be exceeded, and recompute ports_used otherwise."""

    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, AccountGroupMember, Account, AccountGroup,
              SupportAgent, Merchant, BusinessAgent)
        self.admin = SupportAgent(
            username="admin", nickname="admin",
            password_hash=hash_password("admin1234"),
            role="admin", status="enabled",
        )
        self.db.add(self.admin)
        self.db.commit()
        r = client.post("/api/auth/login",
                        json={"username": "admin", "password": "admin1234"})
        self.token = r.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self) -> None:
        self.db.close()

    def test_batch_activate_within_quota_recomputes_used(self) -> None:
        m = _make_merchant(self.db, ports_total=5)
        a = _make_account(self.db, merchant_id=m.id, status="paused", suffix="x")
        m_id = m.id

        r = client.post("/api/accounts/batch",
                        json={"ids": [a.id], "status": "active"},
                        headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        with SessionLocal() as db:
            self.assertEqual(db.get(Merchant, m_id).ports_used, 1)

    def test_batch_activate_over_quota_returns_409(self) -> None:
        m = _make_merchant(self.db, ports_total=1)
        # Already one active.
        _make_account(self.db, merchant_id=m.id, status="active", suffix="a")
        # Try to activate a second.
        a2 = _make_account(self.db, merchant_id=m.id, status="paused", suffix="b")

        r = client.post("/api/accounts/batch",
                        json={"ids": [a2.id], "status": "active"},
                        headers=self.headers)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("端口", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
