"""Admin-only single-shot test send: POST /api/accounts/{id}/test-send.

Used to verify a TG account can actually reach a target without
setting up a campaign. Persists a MessageRecord with no campaign_id
so the audit trail captures the attempt.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.core.security import hash_password
from backend.app.main import app
from backend.app.models.account import Account
from backend.app.models.agent import SupportAgent
from backend.app.models.message import MessageRecord
from backend.app.telegram.adapter import TelegramSendResult


client = TestClient(app)


def _bootstrap_admin():
    client.post("/api/auth/bootstrap-admin",
                json={"username": "root", "password": "admin1234"})
    r = client.post("/api/auth/login",
                    json={"username": "root", "password": "admin1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _stubbed_send(*, ok=True, error_message=None):
    async def fake(account, target, body, proxy=None, entities=None):
        return TelegramSendResult(
            ok=ok,
            external_message_id="t-msg-9" if ok else None,
            target_tg_user_id="555" if ok else None,
            error_code=None if ok else "rpc_error",
            error_message=error_message,
        )
    return fake


class TestSendApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        for model in (MessageRecord, Account, SupportAgent):
            for row in self.db.query(model).all():
                self.db.delete(row)
        self.db.commit()
        self.auth = _bootstrap_admin()
        acc = Account(
            tg_user_id="acc-1", phone="+10000000001",
            session_path="/tmp/acc-1.session",
            status="active", enabled=True,
        )
        self.db.add(acc)
        self.db.commit()
        self.account_id = acc.id

    def tearDown(self) -> None:
        self.db.close()

    def test_test_send_to_phone_creates_message_record(self) -> None:
        from backend.app.telegram import adapter as adapter_module

        with patch.object(adapter_module, "get_adapter") as get_adapter_mock:
            stub = type("Stub", (), {
                "configured": True,
                "send_message": staticmethod(_stubbed_send()),
            })()
            get_adapter_mock.return_value = stub

            r = client.post(
                f"/api/accounts/{self.account_id}/test-send",
                json={"target": "+12345678901", "text": "Test 你好"},
                headers=self.auth,
            )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "sent")
        self.assertEqual(body["phone"], "+12345678901")
        self.assertEqual(body["body_snapshot"], "Test 你好")
        self.assertIsNone(body.get("campaign_id"))

        with SessionLocal() as db:
            rec = db.get(MessageRecord, body["id"])
            self.assertEqual(rec.status, "sent")
            self.assertEqual(rec.account_id, self.account_id)
            self.assertEqual(rec.direction, "outbound")
            self.assertIsNone(rec.campaign_id)

    def test_test_send_to_tg_user_id_uses_target_field(self) -> None:
        from backend.app.telegram import adapter as adapter_module

        captured = {}
        async def fake(account, target, body, proxy=None, entities=None):
            captured.update({"target": target, "body": body})
            return TelegramSendResult(ok=True, external_message_id="x", target_tg_user_id="7777")

        with patch.object(adapter_module, "get_adapter") as get_adapter_mock:
            stub = type("Stub", (), {
                "configured": True, "send_message": staticmethod(fake),
            })()
            get_adapter_mock.return_value = stub
            r = client.post(
                f"/api/accounts/{self.account_id}/test-send",
                json={"target": "7777777", "target_kind": "tg_user_id",
                      "text": "hi"},
                headers=self.auth,
            )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(captured["target"], "7777777")
        self.assertEqual(captured["body"], "hi")

    def test_test_send_failure_persists_failed_row_and_502(self) -> None:
        from backend.app.telegram import adapter as adapter_module

        with patch.object(adapter_module, "get_adapter") as get_adapter_mock:
            stub = type("Stub", (), {
                "configured": True,
                "send_message": staticmethod(_stubbed_send(ok=False, error_message="upstream rejected")),
            })()
            get_adapter_mock.return_value = stub
            r = client.post(
                f"/api/accounts/{self.account_id}/test-send",
                json={"target": "+12345678901", "text": "x"},
                headers=self.auth,
            )
        self.assertEqual(r.status_code, 502, r.text)
        self.assertIn("upstream rejected", r.json()["detail"])
        with SessionLocal() as db:
            rows = list(db.query(MessageRecord).all())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].status, "failed")

    def test_test_send_rejects_disabled_account(self) -> None:
        with SessionLocal() as db:
            db.get(Account, self.account_id).enabled = False
            db.commit()
        r = client.post(
            f"/api/accounts/{self.account_id}/test-send",
            json={"target": "+12345678901", "text": "x"},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 400, r.text)

    def test_test_send_requires_admin(self) -> None:
        agent = SupportAgent(
            username="staff", nickname="s",
            password_hash=hash_password("staffpwd1"),
            role="agent", status="enabled",
        )
        self.db.add(agent)
        self.db.commit()
        tok = client.post("/api/auth/login",
                          json={"username": "staff", "password": "staffpwd1"}).json()["access_token"]
        r = client.post(
            f"/api/accounts/{self.account_id}/test-send",
            json={"target": "+12345678901", "text": "x"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        self.assertEqual(r.status_code, 403, r.text)


if __name__ == "__main__":
    unittest.main()
