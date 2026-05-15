import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.agent import SupportAgent
from backend.app.models.tenant import BusinessAgent, Merchant


def _bootstrap(client):
    return client.post("/api/auth/bootstrap-admin",
                       json={"username": "root", "password": "12345678"})


class BusinessAgentApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (Merchant, BusinessAgent, SupportAgent):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        self.auth = {"Authorization": f"Bearer {_bootstrap(self.client).json()['access_token']}"}

    def test_create_then_list(self) -> None:
        resp = self.client.post(
            "/api/business-agents",
            json={
                "name": "zymght", "nickname": "ae111",
                "password": "12345678",
                "platform_name": "qwe",
                "domains": "example.com",
            },
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["name"], "zymght")
        self.assertNotIn("password_hash", body)  # never leak

        listing = self.client.get("/api/business-agents", headers=self.auth).json()
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["nickname"], "ae111")

    def test_duplicate_name_rejected(self) -> None:
        payload = {"name": "z", "nickname": "x", "password": "12345678", "platform_name": "p"}
        self.client.post("/api/business-agents", json=payload, headers=self.auth)
        dup = self.client.post("/api/business-agents", json=payload, headers=self.auth)
        self.assertEqual(dup.status_code, 409)

    def test_update_changes_status_and_password(self) -> None:
        created = self.client.post(
            "/api/business-agents",
            json={"name": "z", "nickname": "x", "password": "12345678", "platform_name": "p"},
            headers=self.auth,
        ).json()
        resp = self.client.patch(
            f"/api/business-agents/{created['id']}",
            json={"status": False, "password": "newpassword123"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        with SessionLocal() as db:
            row = db.get(BusinessAgent, created["id"])
            self.assertFalse(row.status)
            # password hashed, not equal to plaintext
            self.assertIsNotNone(row.password_hash)
            self.assertNotEqual(row.password_hash, "newpassword123")

    def test_delete(self) -> None:
        created = self.client.post(
            "/api/business-agents",
            json={"name": "z", "nickname": "x", "password": "12345678", "platform_name": "p"},
            headers=self.auth,
        ).json()
        resp = self.client.delete(f"/api/business-agents/{created['id']}", headers=self.auth)
        self.assertEqual(resp.status_code, 200)
        with SessionLocal() as db:
            self.assertEqual(db.query(BusinessAgent).count(), 0)


class MerchantApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (Merchant, BusinessAgent, SupportAgent):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        self.auth = {"Authorization": f"Bearer {_bootstrap(self.client).json()['access_token']}"}

        agent = self.client.post(
            "/api/business-agents",
            json={"name": "z", "nickname": "x", "password": "12345678", "platform_name": "p"},
            headers=self.auth,
        ).json()
        self.agent_id = agent["id"]

    def test_create_merchant_with_ports(self) -> None:
        resp = self.client.post(
            "/api/merchants",
            json={
                "name": "shop", "nickname": "shop-nick", "password": "12345678",
                "business_agent_id": self.agent_id,
                "ports_total": 100,
                "ports_expires_at": "2026-06-14T14:59:59",
                "statistic_time": "09:00",
            },
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["ports_total"], 100)
        self.assertEqual(body["ports_used"], 0)
        self.assertNotIn("password_hash", body)

    def test_list_filters_by_business_agent(self) -> None:
        other = self.client.post(
            "/api/business-agents",
            json={"name": "other", "nickname": "o", "password": "12345678", "platform_name": "p"},
            headers=self.auth,
        ).json()
        for n, agent_id in [("a", self.agent_id), ("b", self.agent_id), ("c", other["id"])]:
            self.client.post(
                "/api/merchants",
                json={"name": n, "nickname": n, "password": "12345678",
                      "business_agent_id": agent_id, "ports_total": 1},
                headers=self.auth,
            )
        rows = self.client.get(
            f"/api/merchants?business_agent_id={self.agent_id}",
            headers=self.auth,
        ).json()
        self.assertEqual({r["name"] for r in rows}, {"a", "b"})

    def test_batch_update_status(self) -> None:
        ids = []
        for n in ("a", "b", "c"):
            r = self.client.post(
                "/api/merchants",
                json={"name": n, "nickname": n, "password": "12345678",
                      "business_agent_id": self.agent_id, "ports_total": 0},
                headers=self.auth,
            ).json()
            ids.append(r["id"])

        resp = self.client.post(
            "/api/merchants/batch",
            json={"ids": ids, "status": False},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["updated"], 3)
        with SessionLocal() as db:
            for m in db.query(Merchant).all():
                self.assertFalse(m.status)


if __name__ == "__main__":
    unittest.main()
