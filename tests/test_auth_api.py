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


if __name__ == "__main__":
    unittest.main()
