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

    def test_operation_runs_endpoint_surfaces_per_account_audit(self) -> None:
        # batch_op campaigns don't queue MessageRecord rows — execute_operation
        # writes per-account outcomes to audit_logs. The /operation-runs
        # endpoint should re-surface those so the UI 详情 dialog can show
        # why specific accounts failed.
        from backend.app.models.audit import AuditLog
        with SessionLocal() as db:
            group, _ = _seed_group_and_template(db)
            # Two more accounts in the group.
            acc2 = Account(tg_user_id="acc2", session_path="/tmp/acc2.session",
                           status="active", enabled=True, phone="+999",
                           nickname="b")
            acc3 = Account(tg_user_id="acc3", session_path="/tmp/acc3.session",
                           status="active", enabled=True, phone="+888")
            db.add(acc2); db.add(acc3)
            db.flush()
            db.add(AccountGroupMember(account_id=acc2.id, group_id=group.id))
            db.add(AccountGroupMember(account_id=acc3.id, group_id=group.id))
            camp = Campaign(name="ops", task_kind="batch_op",
                            operation_target="delete_friend",
                            account_group_ids=[group.id])
            db.add(camp)
            db.flush()
            camp_id = camp.id
            for acc, ok, code, msg in [
                (acc2, True, None, None),
                (acc3, False, "FloodWait", "wait 60s"),
            ]:
                db.add(AuditLog(
                    actor_kind="system",
                    action="campaign.batch_op.delete_friend",
                    target_type="account", target_id=str(acc.id),
                    detail={"campaign_id": camp_id, "ok": ok,
                            "error_code": code, "error_message": msg},
                ))
            db.commit()

        r = self.client.get(f"/api/campaigns/{camp_id}/operation-runs", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        rows = r.json()
        self.assertEqual(len(rows), 2)
        by_phone = {row["account_phone"]: row for row in rows}
        self.assertTrue(by_phone["+999"]["ok"])
        self.assertFalse(by_phone["+888"]["ok"])
        self.assertEqual(by_phone["+888"]["error_code"], "FloodWait")
        self.assertEqual(by_phone["+888"]["error_message"], "wait 60s")
        self.assertEqual(by_phone["+999"]["account_nickname"], "b")

    def test_operation_runs_endpoint_404_for_unknown_campaign(self) -> None:
        r = self.client.get("/api/campaigns/99999/operation-runs", headers=self.auth)
        self.assertEqual(r.status_code, 404)

    def test_preflight_returns_severity_and_counts(self) -> None:
        # Regression for a NameError: preflight uses func.count() but the
        # `func` import was missing → endpoint 500'd on every form change.
        with SessionLocal() as db:
            group, _ = _seed_group_and_template(db)
            group_id = group.id
        r = self.client.post(
            "/api/campaigns/preflight",
            json={
                "task_kind": "broadcast",
                "target_type": "imported_target_broadcast",
                "account_group_ids": [group_id],
                "imported_targets_count": 50,
            },
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["target_count"], 50)
        self.assertEqual(body["eligible_accounts"], 1)
        self.assertEqual(body["per_account_avg"], 50.0)
        # 50 / 1 = 50 per-account avg → red zone (≥25).
        self.assertEqual(body["severity"], "danger")

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

    def test_customer_broadcast_force_resend_bypasses_status_gate(self) -> None:
        # Customer already in a post-send state (replied) is blocked by
        # the default status whitelist; with force_resend=true the gate
        # is skipped so the same customer is queued again.
        from backend.app.models.customer import Customer
        from backend.app.models.account import Account as Acc
        with SessionLocal() as db:
            group, tpl = _seed_group_and_template(db)
            account = db.query(Acc).first()
            cust = Customer(phone="+8613800000099", consent=True,
                            assigned_account_id=account.id, status="replied")
            db.add(cust); db.commit()
            template_id = tpl.id
            group_id = group.id
            cust_id = cust.id

        # Without the flag — 400 with the eligibility breakdown.
        r = self.client.post(
            "/api/campaigns",
            json={"name": "f1", "template_id": template_id,
                  "target_type": "customer_broadcast",
                  "account_group_ids": [group_id],
                  "customer_ids": [cust_id], "send_settings": {}},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("状态不在", r.json()["detail"])

        # With force_resend — succeeds, status flipped to queued.
        r = self.client.post(
            "/api/campaigns",
            json={"name": "f2", "template_id": template_id,
                  "target_type": "customer_broadcast",
                  "account_group_ids": [group_id],
                  "customer_ids": [cust_id], "force_resend": True,
                  "send_settings": {}},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.text)
        with SessionLocal() as db:
            self.assertEqual(db.get(Customer, cust_id).status, "queued")

    def test_customer_broadcast_force_resend_still_blocks_no_consent(self) -> None:
        # force_resend opens the status gate only — consent is the
        # compliance hard line and must stay enforced.
        from backend.app.models.customer import Customer
        from backend.app.models.account import Account as Acc
        with SessionLocal() as db:
            group, tpl = _seed_group_and_template(db)
            account = db.query(Acc).first()
            cust = Customer(phone="+8613800000098", consent=False,
                            assigned_account_id=account.id, status="replied")
            db.add(cust); db.commit()
            template_id = tpl.id
            group_id = group.id
            cust_id = cust.id

        r = self.client.post(
            "/api/campaigns",
            json={"name": "fc", "template_id": template_id,
                  "target_type": "customer_broadcast",
                  "account_group_ids": [group_id],
                  "customer_ids": [cust_id], "force_resend": True,
                  "send_settings": {}},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("consent=false", r.json()["detail"])

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
