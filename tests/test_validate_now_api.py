"""POST /api/accounts/{id}/validate — admin-triggered session check
that runs synchronously and returns the updated row immediately so
the operator doesn't have to wait for the 15-minute beat tick.

POST /api/accounts/validate-all — dispatches the existing
validate_all_sessions Celery task. Returns task_id for the UI.
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
from backend.app.telegram.adapter import TelegramValidateResult


client = TestClient(app)


def _bootstrap_admin():
    client.post("/api/auth/bootstrap-admin",
                json={"username": "root", "password": "admin1234"})
    r = client.post("/api/auth/login",
                    json={"username": "root", "password": "admin1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class ValidateNowApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        for model in (Account, SupportAgent):
            for row in self.db.query(model).all():
                self.db.delete(row)
        self.db.commit()
        self.auth = _bootstrap_admin()
        acc = Account(
            tg_user_id="pending:+12345",
            phone="+12345",
            session_path="/tmp/fake.session",
            status="imported", enabled=True,
        )
        self.db.add(acc)
        self.db.commit()
        self.account_id = acc.id

    def tearDown(self) -> None:
        self.db.close()

    def test_validate_success_flips_to_active_and_promotes_id(self) -> None:
        from backend.app.workers import account_tasks

        async def fake(account, proxy):
            return TelegramValidateResult(
                ok=True, tg_user_id="9876543210", phone="12345",
            )
        stub = type("Stub", (), {
            "configured": True,
            "validate_session": staticmethod(fake),
        })()
        with patch.object(account_tasks, "get_adapter", return_value=stub):
            r = client.post(f"/api/accounts/{self.account_id}/validate",
                            headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["ok"], True)
        with SessionLocal() as db:
            row = db.get(Account, self.account_id)
            self.assertEqual(row.status, "active")
            self.assertEqual(row.tg_user_id, "9876543210")

    def test_validate_failure_marks_error(self) -> None:
        from backend.app.workers import account_tasks

        async def fake(account, proxy):
            return TelegramValidateResult(
                ok=False, error_code="auth_invalid", error_message="session expired",
            )
        stub = type("Stub", (), {
            "configured": True,
            "validate_session": staticmethod(fake),
        })()
        with patch.object(account_tasks, "get_adapter", return_value=stub):
            r = client.post(f"/api/accounts/{self.account_id}/validate",
                            headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["ok"], False)
        self.assertIn("session expired", body["error_message"])
        with SessionLocal() as db:
            row = db.get(Account, self.account_id)
            self.assertEqual(row.status, "error")

    def test_validate_404_when_account_missing(self) -> None:
        r = client.post("/api/accounts/99999/validate", headers=self.auth)
        self.assertEqual(r.status_code, 404, r.text)

    def test_validate_requires_admin(self) -> None:
        agent = SupportAgent(
            username="staff", nickname="s",
            password_hash=hash_password("staffpwd1"),
            role="agent", status="enabled",
        )
        self.db.add(agent)
        self.db.commit()
        tok = client.post("/api/auth/login",
                          json={"username": "staff", "password": "staffpwd1"}).json()["access_token"]
        r = client.post(f"/api/accounts/{self.account_id}/validate",
                        headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r.status_code, 403, r.text)


if __name__ == "__main__":
    unittest.main()
