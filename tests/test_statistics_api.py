import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.agent import SupportAgent
from backend.app.models.campaign import Campaign
from backend.app.models.message import MessageRecord


def _bootstrap(client):
    return client.post(
        "/api/auth/bootstrap-admin",
        json={"username": "root", "password": "12345678"},
    )


def _msg(campaign_id, status, sent_at=None, replied_at=None, read_at=None, account_id=1):
    """Convenience to instantiate a MessageRecord with ISO-format dates."""
    return MessageRecord(
        campaign_id=campaign_id,
        account_id=account_id,
        body_snapshot="x",
        status=status,
        sent_at=sent_at,
        read_at=read_at,
        replied_at=replied_at,
    )


class TimeseriesApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (MessageRecord, Campaign, SupportAgent):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        self.auth = {"Authorization": f"Bearer {_bootstrap(self.client).json()['access_token']}"}

        with SessionLocal() as db:
            cmp = Campaign(name="c1", status="running", task_kind="broadcast",
                           operation_target="customer_broadcast",
                           target_type="customer_broadcast")
            db.add(cmp)
            db.flush()
            self.cmp_id = cmp.id
            # Two messages on 2026-05-14, one on 2026-05-15
            db.add(_msg(cmp.id, "sent", sent_at="2026-05-14T10:00:00+00:00"))
            db.add(_msg(cmp.id, "replied",
                        sent_at="2026-05-14T11:00:00+00:00",
                        replied_at="2026-05-14T12:00:00+00:00"))
            db.add(_msg(cmp.id, "sent",
                        sent_at="2026-05-15T10:00:00+00:00",
                        read_at="2026-05-15T10:30:00+00:00"))
            db.add(_msg(cmp.id, "failed_permanent",
                        sent_at="2026-05-15T11:00:00+00:00"))
            db.commit()

    def test_buckets_grouped_by_day(self) -> None:
        resp = self.client.get("/api/statistics/timeseries", headers=self.auth)
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        buckets = {b["date"]: b for b in data["buckets"]}
        self.assertIn("2026-05-14", buckets)
        self.assertIn("2026-05-15", buckets)
        self.assertEqual(buckets["2026-05-14"]["sent"], 2)
        self.assertEqual(buckets["2026-05-14"]["replied"], 1)
        self.assertEqual(buckets["2026-05-15"]["sent"], 2)
        self.assertEqual(buckets["2026-05-15"]["read"], 1)
        self.assertEqual(buckets["2026-05-15"]["failed"], 1)

    def test_totals_with_rates(self) -> None:
        data = self.client.get("/api/statistics/timeseries", headers=self.auth).json()
        t = data["totals"]
        self.assertEqual(t["sent"], 4)
        self.assertEqual(t["read"], 1)
        self.assertEqual(t["replied"], 1)
        self.assertEqual(t["failed"], 1)
        self.assertAlmostEqual(t["read_rate"], 0.25)
        self.assertAlmostEqual(t["reply_rate"], 0.25)

    def test_date_range_filter(self) -> None:
        data = self.client.get(
            "/api/statistics/timeseries?from=2026-05-15&to=2026-05-15",
            headers=self.auth,
        ).json()
        dates = [b["date"] for b in data["buckets"]]
        self.assertEqual(dates, ["2026-05-15"])
        self.assertEqual(data["totals"]["sent"], 2)

    def test_empty_returns_zero_totals(self) -> None:
        with SessionLocal() as db:
            for row in db.query(MessageRecord).all():
                db.delete(row)
            db.commit()
        data = self.client.get("/api/statistics/timeseries", headers=self.auth).json()
        self.assertEqual(data["buckets"], [])
        self.assertEqual(data["totals"]["sent"], 0)
        self.assertEqual(data["totals"]["read_rate"], 0)


class MessageDetailsApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (MessageRecord, Campaign, SupportAgent):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        self.auth = {"Authorization": f"Bearer {_bootstrap(self.client).json()['access_token']}"}

        with SessionLocal() as db:
            cmp = Campaign(name="c1", status="running", task_kind="broadcast",
                           operation_target="customer_broadcast",
                           target_type="customer_broadcast")
            db.add(cmp)
            db.flush()
            self.cmp_id = cmp.id
            for i, st in enumerate(["sent", "failed", "replied", "queued"]):
                db.add(_msg(cmp.id, st,
                            sent_at=f"2026-05-{14 + (i % 2):02d}T10:00:00+00:00"))
            db.commit()

    def test_default_lists_all(self) -> None:
        resp = self.client.get("/api/statistics/message-details", headers=self.auth)
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()
        self.assertEqual(len(rows), 4)

    def test_filter_by_status(self) -> None:
        rows = self.client.get(
            "/api/statistics/message-details?status=failed", headers=self.auth,
        ).json()
        self.assertEqual([r["status"] for r in rows], ["failed"])

    def test_filter_by_task_id(self) -> None:
        rows = self.client.get(
            f"/api/statistics/message-details?task_id={self.cmp_id}",
            headers=self.auth,
        ).json()
        self.assertEqual(len(rows), 4)
        rows = self.client.get(
            "/api/statistics/message-details?task_id=99999",
            headers=self.auth,
        ).json()
        self.assertEqual(rows, [])

    def test_pagination(self) -> None:
        page1 = self.client.get(
            "/api/statistics/message-details?limit=2&offset=0",
            headers=self.auth,
        ).json()
        page2 = self.client.get(
            "/api/statistics/message-details?limit=2&offset=2",
            headers=self.auth,
        ).json()
        self.assertEqual(len(page1), 2)
        self.assertEqual(len(page2), 2)
        self.assertNotEqual({r["id"] for r in page1}, {r["id"] for r in page2})


if __name__ == "__main__":
    unittest.main()
