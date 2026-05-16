"""R1 slice 1 — multi-actor login + JWT shape.

Three actor kinds need to log in and receive JWTs that downstream code can
discriminate on:
  - support_agent (admin / supervisor / agent — existing login)
  - business_agent (resellers — PRD section 6)
  - merchant (商户 — PRD section 7)

The JWT must carry `actor_kind` + `actor_id` so middleware can scope queries.
The legacy `agent_id` + `role` fields stay for backward compat.
"""
from __future__ import annotations

import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.core.security import decode_token, hash_password
from backend.app.main import app
from backend.app.models.agent import SupportAgent
from backend.app.models.tenant import BusinessAgent, Merchant


client = TestClient(app)


def _wipe(db, *models):
    for model in models:
        for row in db.query(model).all():
            db.delete(row)
    db.commit()


class MultiTenantLoginTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_support_agent_login_keeps_legacy_shape(self) -> None:
        # Admin login still works exactly as before; new fields are added
        # rather than replacing.
        admin = SupportAgent(
            username="admin",
            nickname="admin",
            password_hash=hash_password("admin1234"),
            role="admin",
            status="enabled",
        )
        self.db.add(admin)
        self.db.commit()

        r = client.post("/api/auth/login", json={"username": "admin", "password": "admin1234"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["role"], "admin")
        self.assertEqual(body["agent_id"], admin.id)
        # New discriminator fields exposed at the top level.
        self.assertEqual(body["actor_kind"], "support_agent")
        self.assertEqual(body["actor_id"], admin.id)

        payload = decode_token(body["access_token"])
        self.assertEqual(payload["actor_kind"], "support_agent")
        self.assertEqual(payload["actor_id"], admin.id)

    def test_business_agent_login(self) -> None:
        ba = BusinessAgent(
            name="reseller-A",
            nickname="代理 A",
            password_hash=hash_password("reseller-pass"),
            status=True,
        )
        self.db.add(ba)
        self.db.commit()

        r = client.post(
            "/api/auth/business-login",
            json={"username": "reseller-A", "password": "reseller-pass"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["actor_kind"], "business_agent")
        self.assertEqual(body["actor_id"], ba.id)

        payload = decode_token(body["access_token"])
        self.assertEqual(payload["actor_kind"], "business_agent")
        self.assertEqual(payload["actor_id"], ba.id)

    def test_merchant_login(self) -> None:
        m = Merchant(
            name="merchant-1",
            password_hash=hash_password("merchant-pass"),
            status=True,
        )
        self.db.add(m)
        self.db.commit()

        r = client.post(
            "/api/auth/merchant-login",
            json={"username": "merchant-1", "password": "merchant-pass"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["actor_kind"], "merchant")
        self.assertEqual(body["actor_id"], m.id)

    def test_business_agent_login_rejects_wrong_password(self) -> None:
        ba = BusinessAgent(
            name="reseller-B",
            password_hash=hash_password("right-pass"),
            status=True,
        )
        self.db.add(ba)
        self.db.commit()

        r = client.post(
            "/api/auth/business-login",
            json={"username": "reseller-B", "password": "wrong"},
        )
        self.assertEqual(r.status_code, 401)

    def test_merchant_login_rejects_disabled_account(self) -> None:
        m = Merchant(
            name="merchant-disabled",
            password_hash=hash_password("ok"),
            status=False,
        )
        self.db.add(m)
        self.db.commit()

        r = client.post(
            "/api/auth/merchant-login",
            json={"username": "merchant-disabled", "password": "ok"},
        )
        self.assertEqual(r.status_code, 401)


class TenantScopedMeTestCase(unittest.TestCase):
    """`/api/auth/me` should return the actor_kind + actor_id so the frontend
    can show different navigation per tenant kind."""

    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def _login_business_agent(self) -> tuple[str, int]:
        ba = BusinessAgent(
            name="reseller-me",
            password_hash=hash_password("pass"),
            status=True,
        )
        self.db.add(ba)
        self.db.commit()
        r = client.post(
            "/api/auth/business-login",
            json={"username": "reseller-me", "password": "pass"},
        )
        return r.json()["access_token"], ba.id

    def test_me_returns_business_agent_scope(self) -> None:
        token, ba_id = self._login_business_agent()
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["actor_kind"], "business_agent")
        self.assertEqual(body["actor_id"], ba_id)


if __name__ == "__main__":
    unittest.main()
