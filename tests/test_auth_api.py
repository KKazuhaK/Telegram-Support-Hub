import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.agent import SupportAgent


class AuthApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for row in db.query(SupportAgent).all():
                db.delete(row)
            db.commit()

    def test_bootstrap_admin_creates_first_admin(self) -> None:
        resp = self.client.post("/api/auth/bootstrap-admin",
                                json={"username": "root", "password": "12345678"})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["role"], "admin")
        self.assertTrue(body["access_token"])

    def test_bootstrap_admin_rejected_when_admin_exists(self) -> None:
        self.client.post("/api/auth/bootstrap-admin",
                         json={"username": "root", "password": "12345678"})
        resp = self.client.post("/api/auth/bootstrap-admin",
                                json={"username": "other", "password": "12345678"})
        self.assertEqual(resp.status_code, 409)

    def test_login_then_call_me(self) -> None:
        self.client.post("/api/auth/bootstrap-admin",
                         json={"username": "root", "password": "12345678"})
        login = self.client.post("/api/auth/login",
                                 json={"username": "root", "password": "12345678"})
        self.assertEqual(login.status_code, 200)
        token = login.json()["access_token"]
        me = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["username"], "root")
        self.assertTrue(me.json()["is_admin"])

    def test_login_with_wrong_password_rejected(self) -> None:
        self.client.post("/api/auth/bootstrap-admin",
                         json={"username": "root", "password": "12345678"})
        resp = self.client.post("/api/auth/login",
                                json={"username": "root", "password": "BAD"})
        self.assertEqual(resp.status_code, 401)

    def test_protected_endpoint_without_token_rejected(self) -> None:
        resp = self.client.get("/api/customers")
        self.assertEqual(resp.status_code, 401)
        # User-facing error must be Chinese, not raw English token wording
        self.assertIn("登录", resp.json()["detail"])

    def test_login_wrong_password_message_is_chinese(self) -> None:
        self.client.post("/api/auth/bootstrap-admin",
                         json={"username": "root", "password": "12345678"})
        resp = self.client.post("/api/auth/login",
                                json={"username": "root", "password": "WRONGPASS"})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("用户名或密码", resp.json()["detail"])

    def test_has_admin_endpoint_reflects_state(self) -> None:
        empty = self.client.get("/api/auth/has-admin")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json(), {"has_admin": False})

        self.client.post("/api/auth/bootstrap-admin",
                         json={"username": "root", "password": "12345678"})

        after = self.client.get("/api/auth/has-admin")
        self.assertEqual(after.json(), {"has_admin": True})

    def test_bootstrap_after_admin_exists_returns_chinese(self) -> None:
        self.client.post("/api/auth/bootstrap-admin",
                         json={"username": "root", "password": "12345678"})
        resp = self.client.post("/api/auth/bootstrap-admin",
                                json={"username": "other", "password": "12345678"})
        self.assertEqual(resp.status_code, 409)
        self.assertIn("管理员", resp.json()["detail"])


if __name__ == "__main__":
    unittest.main()
