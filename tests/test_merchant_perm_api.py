import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.account import AccountGroup
from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission
from backend.app.models.tenant import BusinessAgent, Merchant


class MerchantBatchPermTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (SupportAgentGroupPermission, SupportAgent,
                          Merchant, BusinessAgent, AccountGroup):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        bootstrap = self.client.post(
            "/api/auth/bootstrap-admin",
            json={"username": "root", "password": "12345678"},
        )
        self.auth = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}

        with SessionLocal() as db:
            from backend.app.core.security import hash_password
            ba = BusinessAgent(name="biz", nickname="b", password_hash=hash_password("12345678"))
            db.add(ba)
            db.flush()
            self.ba_id = ba.id
            for n in ("m1", "m2"):
                db.add(Merchant(name=n, nickname=n,
                                password_hash=hash_password("12345678"),
                                business_agent_id=ba.id))
            for n in ("svc1", "svc2"):
                db.add(SupportAgent(username=n, role="agent", status="enabled",
                                    password_hash=hash_password("12345678")))
            for n in ("g1", "g2"):
                db.add(AccountGroup(name=n, code=n, enabled=True))
            db.commit()
            self.merchant_ids = [m.id for m in db.query(Merchant).all()]
            self.agent_ids = [a.id for a in db.query(SupportAgent).filter_by(role="agent").all()]
            self.group_ids = [g.id for g in db.query(AccountGroup).all()]

    def test_batch_grant_permissions_to_agents(self) -> None:
        # Grant svc1+svc2 send-message + view-friends on g1+g2 in one shot.
        resp = self.client.post(
            "/api/merchants/batch-permissions",
            json={
                "merchant_ids": self.merchant_ids,
                "agent_ids": self.agent_ids,
                "account_group_ids": self.group_ids,
                "permissions": {
                    "can_view_friends": True,
                    "can_view_chats": True,
                    "can_send_message": True,
                    "can_broadcast": False,
                },
            },
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        # 2 agents × 2 groups = 4 permission rows created
        self.assertEqual(body["created"], 4)
        with SessionLocal() as db:
            rows = list(db.scalars(SupportAgentGroupPermission.__table__.select()))
            self.assertEqual(len(rows), 4)

    def test_batch_overwrites_existing_permission(self) -> None:
        # Pre-seed one permission row with the wrong flag set
        with SessionLocal() as db:
            db.add(SupportAgentGroupPermission(
                agent_id=self.agent_ids[0],
                account_group_id=self.group_ids[0],
                can_send_message=False,
            ))
            db.commit()

        self.client.post(
            "/api/merchants/batch-permissions",
            json={
                "merchant_ids": self.merchant_ids,
                "agent_ids": [self.agent_ids[0]],
                "account_group_ids": [self.group_ids[0]],
                "permissions": {"can_send_message": True},
            },
            headers=self.auth,
        )
        with SessionLocal() as db:
            row = db.query(SupportAgentGroupPermission).filter_by(
                agent_id=self.agent_ids[0], account_group_id=self.group_ids[0],
            ).one()
            self.assertTrue(row.can_send_message)

    def test_validation_rejects_empty_inputs(self) -> None:
        for payload in (
            {"agent_ids": [], "account_group_ids": [self.group_ids[0]],
             "permissions": {"can_send_message": True}, "merchant_ids": [1]},
            {"agent_ids": [self.agent_ids[0]], "account_group_ids": [],
             "permissions": {"can_send_message": True}, "merchant_ids": [1]},
        ):
            r = self.client.post("/api/merchants/batch-permissions",
                                 json=payload, headers=self.auth)
            self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
