"""话术 (quick reply) CRUD with personal vs public scope."""
from __future__ import annotations

import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.core.security import hash_password
from backend.app.main import app
from backend.app.models.agent import SupportAgent
from backend.app.models.quick_reply import QuickReply
from backend.app.models.tenant import BusinessAgent, Merchant


client = TestClient(app)


def _wipe(db, *models):
    for model in models:
        for row in db.query(model).all():
            db.delete(row)
    db.commit()


def _bootstrap_admin():
    client.post("/api/auth/bootstrap-admin",
                json={"username": "root", "password": "admin1234"})
    r = client.post("/api/auth/login",
                    json={"username": "root", "password": "admin1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["actor_id"]


class QuickReplyApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, QuickReply, SupportAgent, Merchant, BusinessAgent)
        self.auth, self.admin_id = _bootstrap_admin()

    def tearDown(self) -> None:
        self.db.close()

    def test_create_personal_script_and_list(self) -> None:
        r = client.post("/api/quick-replies",
                        json={"text": "你好，请问您是？", "category": "开场白"},
                        headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["text"], "你好，请问您是？")
        self.assertEqual(body["is_public"], False)
        self.assertEqual(body["actor_kind"], "support_agent")

        r = client.get("/api/quick-replies", headers=self.auth)
        self.assertEqual(r.status_code, 200)
        items = r.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "你好，请问您是？")

    def test_admin_can_create_public_script(self) -> None:
        r = client.post("/api/quick-replies",
                        json={"text": "促单话术", "category": "促单",
                              "is_public": True},
                        headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["is_public"], True)

    def test_non_admin_cannot_create_public_script(self) -> None:
        # Create a plain agent
        agent = SupportAgent(
            username="staff", nickname="staff",
            password_hash=hash_password("staffpass"),
            role="agent", status="enabled",
        )
        self.db.add(agent)
        self.db.commit()
        r = client.post("/api/auth/login",
                        json={"username": "staff", "password": "staffpass"})
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = client.post("/api/quick-replies",
                        json={"text": "x", "is_public": True},
                        headers=headers)
        self.assertEqual(r.status_code, 403, r.text)

    def test_list_returns_own_personal_plus_all_public(self) -> None:
        # Admin creates one public.
        client.post("/api/quick-replies",
                    json={"text": "公共-1", "is_public": True},
                    headers=self.auth)
        # Agent A creates personal-A.
        agentA = SupportAgent(
            username="aa", nickname="A",
            password_hash=hash_password("aaaaaaa1"),
            role="agent", status="enabled",
        )
        # Agent B creates personal-B.
        agentB = SupportAgent(
            username="bb", nickname="B",
            password_hash=hash_password("bbbbbbb1"),
            role="agent", status="enabled",
        )
        self.db.add_all([agentA, agentB])
        self.db.commit()

        a_tok = client.post("/api/auth/login",
                            json={"username": "aa", "password": "aaaaaaa1"}).json()["access_token"]
        b_tok = client.post("/api/auth/login",
                            json={"username": "bb", "password": "bbbbbbb1"}).json()["access_token"]

        client.post("/api/quick-replies", json={"text": "personal-A"},
                    headers={"Authorization": f"Bearer {a_tok}"})
        client.post("/api/quick-replies", json={"text": "personal-B"},
                    headers={"Authorization": f"Bearer {b_tok}"})

        # Agent A sees: their own personal-A + the public "公共-1". Not personal-B.
        r = client.get("/api/quick-replies",
                       headers={"Authorization": f"Bearer {a_tok}"})
        texts = {row["text"] for row in r.json()}
        self.assertEqual(texts, {"personal-A", "公共-1"})

    def test_list_scope_filter(self) -> None:
        client.post("/api/quick-replies",
                    json={"text": "公共", "is_public": True}, headers=self.auth)
        client.post("/api/quick-replies",
                    json={"text": "私人"}, headers=self.auth)

        r = client.get("/api/quick-replies?scope=personal", headers=self.auth)
        self.assertEqual({row["text"] for row in r.json()}, {"私人"})
        r = client.get("/api/quick-replies?scope=public", headers=self.auth)
        self.assertEqual({row["text"] for row in r.json()}, {"公共"})

    def test_owner_can_patch_and_delete_personal(self) -> None:
        r = client.post("/api/quick-replies", json={"text": "原"}, headers=self.auth)
        qid = r.json()["id"]
        r = client.patch(f"/api/quick-replies/{qid}",
                         json={"text": "改"}, headers=self.auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["text"], "改")
        r = client.delete(f"/api/quick-replies/{qid}", headers=self.auth)
        self.assertEqual(r.status_code, 200)

    def test_non_owner_cannot_patch_personal(self) -> None:
        # Admin owns a personal script.
        r = client.post("/api/quick-replies", json={"text": "私"}, headers=self.auth)
        qid = r.json()["id"]
        # Agent B logs in.
        b = SupportAgent(username="other", nickname="other",
                         password_hash=hash_password("otherpwd"),
                         role="agent", status="enabled")
        self.db.add(b)
        self.db.commit()
        b_tok = client.post("/api/auth/login",
                            json={"username": "other", "password": "otherpwd"}).json()["access_token"]
        r = client.patch(f"/api/quick-replies/{qid}", json={"text": "黑客"},
                         headers={"Authorization": f"Bearer {b_tok}"})
        self.assertEqual(r.status_code, 404, r.text)


if __name__ == "__main__":
    unittest.main()
