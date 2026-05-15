import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.campaign import Campaign
from backend.app.models.message import MessageRecord
from backend.app.models.template import MessageTemplate
from backend.app.services.imported_target import build_imported_target_records


def _seed(db):
    group = AccountGroup(name="g", code="g", enabled=True)
    db.add(group)
    db.flush()
    accounts = []
    for i in range(2):
        acc = Account(tg_user_id=f"acc{i}", session_path=f"/tmp/{i}.session", status="active", enabled=True)
        db.add(acc)
        db.flush()
        db.add(AccountGroupMember(account_id=acc.id, group_id=group.id, is_primary=True))
        accounts.append(acc)
    template = MessageTemplate(name="t", body="hi {name}")
    db.add(template)
    cmp = Campaign(name="c", template_id=None, status="queued", target_type="imported_target_broadcast",
                   account_group_ids=[group.id], send_settings={})
    db.add(cmp)
    db.flush()
    return cmp, template, group


class ImportedTargetTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        for model in (MessageRecord, Campaign, MessageTemplate, AccountGroupMember, Account, AccountGroup):
            for row in self.db.query(model).all():
                self.db.delete(row)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_phone_targets_round_robin_to_accounts(self) -> None:
        cmp, template, group = _seed(self.db)
        self.db.commit()
        targets = [
            {"phone": "+8613800000001", "name": "A"},
            {"phone": "+8613800000002", "name": "B"},
            {"phone": "+8613800000003"},
            {"phone": "+8613800000004"},
        ]
        count = build_imported_target_records(self.db, cmp, template, [group.id], targets)
        self.db.commit()
        self.assertEqual(count, 4)
        recs = self.db.query(MessageRecord).all()
        self.assertEqual({r.phone for r in recs}, {t["phone"] for t in targets})
        # Each account should hold 2 records (round-robin across 2 accts, 4 targets)
        per_acc = {}
        for r in recs:
            per_acc[r.account_id] = per_acc.get(r.account_id, 0) + 1
        self.assertEqual(set(per_acc.values()), {2})
        # Body rendered with name fallback
        rec = next(r for r in recs if r.phone == "+8613800000001")
        self.assertEqual(rec.body_snapshot, "hi A")
        rec3 = next(r for r in recs if r.phone == "+8613800000003")
        self.assertEqual(rec3.body_snapshot, "hi 客户")

    def test_username_targets_use_target_tg_user_id(self) -> None:
        cmp, template, group = _seed(self.db)
        self.db.commit()
        targets = [{"username": "@alice", "name": "Alice"}]
        count = build_imported_target_records(self.db, cmp, template, [group.id], targets)
        self.db.commit()
        self.assertEqual(count, 1)
        rec = self.db.query(MessageRecord).first()
        # username stored in target_tg_user_id (Telethon resolves @user just fine)
        self.assertEqual(rec.target_tg_user_id, "@alice")

    def test_invalid_targets_skipped(self) -> None:
        cmp, template, group = _seed(self.db)
        self.db.commit()
        targets = [{"name": "no contact"}, {"phone": ""}, {"phone": "+8613800000001"}]
        count = build_imported_target_records(self.db, cmp, template, [group.id], targets)
        self.db.commit()
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
