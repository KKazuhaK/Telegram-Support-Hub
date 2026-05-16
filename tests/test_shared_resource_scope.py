"""Tenant scope on the 'shared resource' models (R1 extension).

Templates, MaterialGroups, PhoneGroups belong to a merchant. Proxies
remain a shared admin pool (deliberately not scoped per PRD's
infrastructure-resource semantics).
"""
from __future__ import annotations

import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.core.security import hash_password
from backend.app.main import app
from backend.app.models.agent import SupportAgent
from backend.app.models.data_groups import MaterialGroup, PhoneGroup
from backend.app.models.template import MessageTemplate
from backend.app.models.tenant import BusinessAgent, Merchant


client = TestClient(app)


def _wipe(db, *models):
    for model in models:
        for row in db.query(model).all():
            db.delete(row)
    db.commit()


def _seed(db):
    ba = BusinessAgent(name="ba-sh", password_hash=hash_password("pw"), status=True)
    db.add(ba)
    db.flush()
    m1 = Merchant(name="m-sh1", password_hash=hash_password("pw"), status=True,
                  business_agent_id=ba.id)
    m2 = Merchant(name="m-sh2", password_hash=hash_password("pw"), status=True,
                  business_agent_id=ba.id)
    db.add_all([m1, m2])
    db.commit()
    return m1, m2


def _login(path, username, password):
    r = client.post(path, json={"username": username, "password": password})
    return r.json()["access_token"]


class TemplateScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, MessageTemplate, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_sees_only_own_templates(self) -> None:
        m1, m2 = _seed(self.db)
        t1 = MessageTemplate(name="m1-greet", body="hi from m1", enabled=True,
                             merchant_id=m1.id)
        t2 = MessageTemplate(name="m2-greet", body="hi from m2", enabled=True,
                             merchant_id=m2.id)
        self.db.add_all([t1, t2])
        self.db.commit()

        token = _login("/api/auth/merchant-login", "m-sh1", "pw")
        r = client.get("/api/message-templates", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        names = {row["name"] for row in r.json()}
        self.assertEqual(names, {"m1-greet"})

    def test_merchant_template_create_auto_fills_merchant_id(self) -> None:
        m1, _ = _seed(self.db)
        token = _login("/api/auth/merchant-login", "m-sh1", "pw")
        r = client.post("/api/message-templates",
                        json={"name": "m1-fresh", "body": "hello",
                              "enabled": True},
                        headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        with SessionLocal() as db:
            row = db.query(MessageTemplate).filter(
                MessageTemplate.name == "m1-fresh"
            ).one()
            self.assertEqual(row.merchant_id, m1.id)


class MaterialGroupScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, MaterialGroup, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_sees_only_own_material_groups(self) -> None:
        m1, m2 = _seed(self.db)
        g1 = MaterialGroup(name="m1-pics", kind="image", merchant_id=m1.id)
        g2 = MaterialGroup(name="m2-pics", kind="image", merchant_id=m2.id)
        self.db.add_all([g1, g2])
        self.db.commit()

        token = _login("/api/auth/merchant-login", "m-sh1", "pw")
        r = client.get("/api/material-groups?kind=image",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        names = {row["name"] for row in r.json()}
        self.assertEqual(names, {"m1-pics"})


class PhoneGroupScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, PhoneGroup, SupportAgent, Merchant, BusinessAgent)

    def tearDown(self) -> None:
        self.db.close()

    def test_merchant_sees_only_own_phone_groups(self) -> None:
        m1, m2 = _seed(self.db)
        g1 = PhoneGroup(name="m1-uk", country="GB", merchant_id=m1.id)
        g2 = PhoneGroup(name="m2-uk", country="GB", merchant_id=m2.id)
        self.db.add_all([g1, g2])
        self.db.commit()

        token = _login("/api/auth/merchant-login", "m-sh1", "pw")
        r = client.get("/api/phone-groups",
                       headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        names = {row["name"] for row in r.json()}
        self.assertEqual(names, {"m1-uk"})


if __name__ == "__main__":
    unittest.main()
