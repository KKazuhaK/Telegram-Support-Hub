import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.customer import Customer
from backend.app.services.assignment import assign_customers


def _seed_accounts(db, group_id, count=3):
    accounts = []
    for i in range(count):
        acc = Account(tg_user_id=f"acc{i}", session_path=f"/tmp/acc{i}.session", status="active", enabled=True)
        db.add(acc)
        db.flush()
        db.add(AccountGroupMember(account_id=acc.id, group_id=group_id, is_primary=True))
        accounts.append(acc)
    return accounts


def _seed_customers(db, count, *, consent=True, assigned=False):
    out = []
    for i in range(count):
        c = Customer(
            phone=f"+12345678{i:03d}",
            name=f"c{i}",
            consent=consent,
            assigned_account_id=1 if assigned else None,
        )
        db.add(c)
        out.append(c)
    db.flush()
    return out


class AssignmentTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        # clean tables before each test
        for model in (Customer, AccountGroupMember, Account, AccountGroup):
            for row in self.db.query(model).all():
                self.db.delete(row)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_round_robin_distribution(self) -> None:
        group = AccountGroup(name="g1", code="g1")
        self.db.add(group)
        self.db.flush()
        accounts = _seed_accounts(self.db, group.id, count=3)
        _seed_customers(self.db, 9)
        self.db.commit()

        result = assign_customers(self.db, account_group_ids=[group.id])
        self.assertEqual(result["assigned"], 9)
        for acc in accounts:
            self.assertEqual(result["per_account"].get(acc.id, 0), 3)

    def test_max_per_account_caps(self) -> None:
        group = AccountGroup(name="g2", code="g2")
        self.db.add(group)
        self.db.flush()
        _seed_accounts(self.db, group.id, count=2)
        _seed_customers(self.db, 10)
        self.db.commit()

        result = assign_customers(self.db, account_group_ids=[group.id], max_per_account=3)
        self.assertEqual(result["assigned"], 6)
        self.assertEqual(result["skipped"], 4)
        for n in result["per_account"].values():
            self.assertLessEqual(n, 3)

    def test_skips_unconsented_customers(self) -> None:
        group = AccountGroup(name="g3", code="g3")
        self.db.add(group)
        self.db.flush()
        _seed_accounts(self.db, group.id, count=1)
        _seed_customers(self.db, 3, consent=False)
        self.db.commit()

        result = assign_customers(self.db, account_group_ids=[group.id])
        self.assertEqual(result["assigned"], 0)
        self.assertEqual(result["reason"], "no_eligible_customers")

    def test_returns_no_eligible_when_no_accounts(self) -> None:
        _seed_customers(self.db, 3)
        self.db.commit()
        result = assign_customers(self.db, account_group_ids=[999])
        self.assertEqual(result["reason"], "no_eligible_accounts")


if __name__ == "__main__":
    unittest.main()
