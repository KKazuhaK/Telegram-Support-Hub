import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission
from backend.app.models.customer import Customer


def _seed_group_with_accounts(db, count=2, group_name="g"):
    group = AccountGroup(name=group_name, code=group_name, enabled=True, daily_limit=1000)
    db.add(group)
    db.flush()
    for i in range(count):
        acc = Account(
            tg_user_id=f"{group_name}-acc{i}",
            session_path=f"/tmp/{group_name}-acc{i}.session",
            status="active",
            enabled=True,
        )
        db.add(acc)
        db.flush()
        db.add(AccountGroupMember(account_id=acc.id, group_id=group.id, is_primary=True))
    db.commit()
    return group


class CustomerImportApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (
                Customer, AccountGroupMember, Account, AccountGroup,
                SupportAgentGroupPermission, SupportAgent,
            ):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()

        bootstrap = self.client.post(
            "/api/auth/bootstrap-admin",
            json={"username": "root", "password": "12345678"},
        )
        self.token = bootstrap.json()["access_token"]
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def test_import_without_group_does_not_assign(self) -> None:
        resp = self.client.post(
            "/api/customers/import",
            json={"text": "+8613800000001\n+8613800000002", "assume_consent": True},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(len(body["created"]), 2)
        self.assertEqual(body.get("assignment"), None)
        with SessionLocal() as db:
            for c in db.query(Customer).all():
                self.assertIsNone(c.assigned_account_id)

    def test_import_with_group_assigns_in_same_call(self) -> None:
        with SessionLocal() as db:
            group = _seed_group_with_accounts(db, count=2)
            group_id = group.id

        resp = self.client.post(
            "/api/customers/import",
            json={
                "text": "+8613800000001\n+8613800000002\n+8613800000003\n+8613800000004",
                "assume_consent": True,
                "account_group_ids": [group_id],
            },
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(len(body["created"]), 4)
        self.assertIsNotNone(body.get("assignment"))
        self.assertEqual(body["assignment"]["assigned"], 4)

        with SessionLocal() as db:
            assigned = [c for c in db.query(Customer).all() if c.assigned_account_id is not None]
            self.assertEqual(len(assigned), 4)
            self.assertEqual({c.status for c in assigned}, {"assigned"})

    def test_import_with_group_only_assigns_new_consented_rows(self) -> None:
        with SessionLocal() as db:
            existing = Customer(phone="+8613800000001", consent=True)
            db.add(existing)
            group = _seed_group_with_accounts(db, count=1)
            group_id = group.id

        # The duplicate phone is silently skipped; only the second one is new
        resp = self.client.post(
            "/api/customers/import",
            json={
                "text": "+8613800000001\n+8613800000002",
                "assume_consent": True,
                "account_group_ids": [group_id],
            },
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(len(body["created"]), 1)
        self.assertEqual(len(body["duplicated"]), 1)
        self.assertEqual(body["assignment"]["assigned"], 1)


class CustomerAssignApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (
                Customer, AccountGroupMember, Account, AccountGroup,
                SupportAgentGroupPermission, SupportAgent,
            ):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()

        bootstrap = self.client.post(
            "/api/auth/bootstrap-admin",
            json={"username": "root", "password": "12345678"},
        )
        self.auth = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}

    def test_assign_only_selected_customer_ids(self) -> None:
        with SessionLocal() as db:
            group = _seed_group_with_accounts(db, count=2)
            group_id = group.id
            ids = []
            for i in range(4):
                c = Customer(phone=f"+860000000{i:04d}", consent=True)
                db.add(c)
                db.flush()
                ids.append(c.id)
            db.commit()
            chosen = ids[:2]

        resp = self.client.post(
            "/api/customers/assign",
            json={"customer_ids": chosen, "account_group_ids": [group_id]},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["assigned"], 2)

        with SessionLocal() as db:
            assigned_ids = [
                c.id for c in db.query(Customer).all() if c.assigned_account_id is not None
            ]
            self.assertEqual(set(assigned_ids), set(chosen))


if __name__ == "__main__":
    unittest.main()
