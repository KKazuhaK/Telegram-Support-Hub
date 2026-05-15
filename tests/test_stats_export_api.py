import csv
import io
import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.agent import SupportAgent
from backend.app.models.campaign import Campaign
from backend.app.models.message import MessageRecord


class StatsExportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (MessageRecord, Campaign, SupportAgent):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        self.auth = {"Authorization": f"Bearer {self.client.post(
            '/api/auth/bootstrap-admin',
            json={'username': 'root', 'password': '12345678'},
        ).json()['access_token']}"}

        with SessionLocal() as db:
            cmp = Campaign(name="c", status="running", task_kind="broadcast",
                           operation_target="customer_broadcast",
                           target_type="customer_broadcast")
            db.add(cmp)
            db.flush()
            for st, sent in [
                ("sent", "2026-05-14T10:00:00+00:00"),
                ("replied", "2026-05-14T11:00:00+00:00"),
                ("sent", "2026-05-15T10:00:00+00:00"),
            ]:
                db.add(MessageRecord(campaign_id=cmp.id, body_snapshot="x",
                                     status=st, sent_at=sent))
            db.commit()

    def test_export_timeseries_csv(self) -> None:
        resp = self.client.get(
            "/api/statistics/timeseries.csv?from=2026-05-14&to=2026-05-15",
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn("text/csv", resp.headers["content-type"])
        # Strip BOM if present then parse.
        text = resp.text.lstrip("﻿")
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[0], ["date", "sent", "read", "replied", "failed"])
        dates = [r[0] for r in rows[1:]]
        self.assertIn("2026-05-14", dates)
        self.assertIn("2026-05-15", dates)


if __name__ == "__main__":
    unittest.main()
