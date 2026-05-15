"""Tests for the merchant port-reset beat task (R14 / R2).

Each merchant has a `ports_reset_cycle_hours` window. When the cycle has
elapsed since the recorded `ports_reset_at`, `ports_used` should be zeroed
and `ports_reset_at` advanced. Merchants whose cycle hasn't elapsed yet
should be left untouched.
"""
import unittest
from datetime import UTC, datetime, timedelta

import tests.support as support

SessionLocal = support.install_sqlite_session()

from backend.app.models.tenant import Merchant
from backend.app.workers import account_tasks


def _make(db, *, name, used, cycle_h, last_reset_at):
    m = Merchant(
        name=name,
        ports_total=10,
        ports_used=used,
        ports_reset_cycle_hours=cycle_h,
        ports_reset_at=last_reset_at,
    )
    db.add(m)
    db.commit()
    return m


class ResetMerchantPortsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        for row in self.db.query(Merchant).all():
            self.db.delete(row)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_resets_when_cycle_elapsed(self) -> None:
        long_ago = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        m = _make(self.db, name="m-elapsed", used=7, cycle_h=24, last_reset_at=long_ago)

        result = account_tasks.reset_merchant_ports()

        self.assertEqual(result["reset"], 1)
        with SessionLocal() as db:
            updated = db.get(Merchant, m.id)
            self.assertEqual(updated.ports_used, 0)
            self.assertNotEqual(updated.ports_reset_at, long_ago)

    def test_skips_when_cycle_not_elapsed(self) -> None:
        recent = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        m = _make(self.db, name="m-recent", used=3, cycle_h=24, last_reset_at=recent)

        result = account_tasks.reset_merchant_ports()

        self.assertEqual(result["reset"], 0)
        with SessionLocal() as db:
            updated = db.get(Merchant, m.id)
            self.assertEqual(updated.ports_used, 3)
            self.assertEqual(updated.ports_reset_at, recent)

    def test_first_run_initializes_reset_at(self) -> None:
        # Merchant with no ports_reset_at recorded — task should initialize
        # the timestamp without zeroing the counter, so the cycle starts
        # from "now" rather than firing immediately.
        m = _make(self.db, name="m-fresh", used=4, cycle_h=24, last_reset_at=None)

        result = account_tasks.reset_merchant_ports()

        self.assertEqual(result["reset"], 0)
        self.assertEqual(result["initialized"], 1)
        with SessionLocal() as db:
            updated = db.get(Merchant, m.id)
            self.assertEqual(updated.ports_used, 4)
            self.assertIsNotNone(updated.ports_reset_at)

    def test_zero_or_negative_cycle_is_ignored(self) -> None:
        # A merchant configured with cycle_hours <= 0 should be skipped
        # rather than resetting on every tick.
        long_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        m = _make(self.db, name="m-nocycle", used=5, cycle_h=0, last_reset_at=long_ago)

        result = account_tasks.reset_merchant_ports()

        self.assertEqual(result["reset"], 0)
        with SessionLocal() as db:
            updated = db.get(Merchant, m.id)
            self.assertEqual(updated.ports_used, 5)


if __name__ == "__main__":
    unittest.main()
