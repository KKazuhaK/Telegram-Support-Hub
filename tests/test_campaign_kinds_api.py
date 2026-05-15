import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.agent import SupportAgent
from backend.app.models.campaign import Campaign
from backend.app.models.template import MessageTemplate


def _bootstrap(client):
    return client.post(
        "/api/auth/bootstrap-admin",
        json={"username": "root", "password": "12345678"},
    )


def _seed_group_and_template(db):
    group = AccountGroup(name="g", code="g", enabled=True)
    db.add(group)
    db.flush()
    acc = Account(tg_user_id="acc1", session_path="/tmp/acc1.session",
                  status="active", enabled=True)
    db.add(acc)
    db.flush()
    db.add(AccountGroupMember(account_id=acc.id, group_id=group.id, is_primary=True))
    tpl = MessageTemplate(name="t", body="hi")
    db.add(tpl)
    db.commit()
    return group, tpl


class BatchOperationCampaignTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        from backend.app.models.customer import Customer
        from backend.app.models.message import MessageRecord
        with SessionLocal() as db:
            for m in (MessageRecord, Customer, Campaign, MessageTemplate,
                      AccountGroupMember, Account, AccountGroup, SupportAgent):
                for row in db.query(m).all():
                    db.delete(row)
            db.commit()
        self.auth = {"Authorization": f"Bearer {_bootstrap(self.client).json()['access_token']}"}

    def test_create_batch_op_delete_friend(self) -> None:
        with SessionLocal() as db:
            group, _ = _seed_group_and_template(db)
            group_id = group.id
        resp = self.client.post(
            "/api/campaigns",
            json={
                "name": "清理好友 - 2026",
                "task_kind": "batch_op",
                "operation_target": "delete_friend",
                "account_group_ids": [group_id],
                "send_settings": {"failure_interval_seconds": 120, "random_max_seconds": 30,
                                   "task_concurrency": 100},
                "extra_params": {},
            },
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["task_kind"], "batch_op")
        self.assertEqual(body["operation_target"], "delete_friend")
        # batch ops don't queue MessageRecord rows yet — target_count is the
        # number of eligible accounts in the chosen groups.
        self.assertEqual(body["target_count"], 1)

    def test_modify_info_requires_extra_params(self) -> None:
        with SessionLocal() as db:
            group, _ = _seed_group_and_template(db)
            group_id = group.id
        # modify_nickname needs a new_value in extra_params
        resp_bad = self.client.post(
            "/api/campaigns",
            json={
                "name": "改昵称",
                "task_kind": "modify_info",
                "operation_target": "modify_nickname",
                "account_group_ids": [group_id],
                "send_settings": {},
                "extra_params": {},  # missing new_value
            },
            headers=self.auth,
        )
        self.assertEqual(resp_bad.status_code, 400)

        resp_ok = self.client.post(
            "/api/campaigns",
            json={
                "name": "改昵称",
                "task_kind": "modify_info",
                "operation_target": "modify_nickname",
                "account_group_ids": [group_id],
                "send_settings": {},
                "extra_params": {"new_value": "Brand New"},
            },
            headers=self.auth,
        )
        self.assertEqual(resp_ok.status_code, 200, resp_ok.text)

    def test_unknown_operation_target_rejected(self) -> None:
        with SessionLocal() as db:
            group, _ = _seed_group_and_template(db)
            group_id = group.id
        resp = self.client.post(
            "/api/campaigns",
            json={
                "name": "bad",
                "task_kind": "batch_op",
                "operation_target": "make_coffee",
                "account_group_ids": [group_id],
                "send_settings": {},
            },
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 400)

    def test_list_filter_by_task_kind(self) -> None:
        with SessionLocal() as db:
            group, tpl = _seed_group_and_template(db)
            group_id = group.id
        # Create one of each
        self.client.post("/api/campaigns", json={
            "name": "b1", "task_kind": "batch_op", "operation_target": "delete_friend",
            "account_group_ids": [group_id], "send_settings": {},
        }, headers=self.auth)
        self.client.post("/api/campaigns", json={
            "name": "m1", "task_kind": "modify_info", "operation_target": "modify_nickname",
            "account_group_ids": [group_id], "send_settings": {}, "extra_params": {"new_value": "n"},
        }, headers=self.auth)
        # Broadcast still works via the old shape (no task_kind defaults to broadcast)
        with SessionLocal() as db:
            from backend.app.models.customer import Customer
            db.add(Customer(phone="+8613800000001", consent=True, status="assigned"))
            db.commit()
        # Need account assignment, skip broadcast creation; just verify filter
        bo = self.client.get("/api/campaigns?task_kind=batch_op", headers=self.auth).json()
        mi = self.client.get("/api/campaigns?task_kind=modify_info", headers=self.auth).json()
        self.assertEqual([c["name"] for c in bo], ["b1"])
        self.assertEqual([c["name"] for c in mi], ["m1"])

    def test_broadcast_still_works_without_task_kind(self) -> None:
        # Backwards-compat: omitting task_kind should default to broadcast
        # and behave like before R5.
        with SessionLocal() as db:
            group, tpl = _seed_group_and_template(db)
            from backend.app.models.customer import Customer
            from backend.app.models.account import Account as Acc
            account = db.query(Acc).first()
            cust = Customer(phone="+8613800000001", consent=True,
                            assigned_account_id=account.id, status="assigned")
            db.add(cust)
            db.commit()
            template_id = tpl.id
            group_id = group.id

        resp = self.client.post(
            "/api/campaigns",
            json={
                "name": "old-style",
                "template_id": template_id,
                "target_type": "customer_broadcast",
                "account_group_ids": [group_id],
                "send_settings": {},
            },
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["task_kind"], "broadcast")


if __name__ == "__main__":
    unittest.main()
