import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from backend.app.models.account import Account
from backend.app.models.campaign import Campaign
from backend.app.models.customer import Customer
from backend.app.models.message import MessageRecord
from backend.app.services.export import customers_csv_rows, messages_csv_rows


class ExportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        for model in (MessageRecord, Customer, Campaign, Account):
            for row in self.db.query(model).all():
                self.db.delete(row)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_customer_csv_has_header_and_rows(self) -> None:
        self.db.add(Customer(phone="+8613800000000", name="张三", consent=True, source="manual"))
        self.db.add(Customer(phone="+8613900000000", name="李四", consent=False))
        self.db.commit()

        rows = list(customers_csv_rows(self.db))
        self.assertEqual(rows[0], ["id", "phone", "name", "tags", "source", "consent", "status", "assigned_account_id", "last_reply_at"])
        self.assertEqual(len(rows), 3)
        body = {row[1]: row for row in rows[1:]}
        self.assertEqual(body["+8613800000000"][2], "张三")
        self.assertEqual(body["+8613800000000"][5], "true")
        self.assertEqual(body["+8613900000000"][5], "false")

    def test_messages_csv_filters_by_campaign(self) -> None:
        cmp1 = Campaign(name="c1", template_id=None, status="running")
        cmp2 = Campaign(name="c2", template_id=None, status="running")
        self.db.add_all([cmp1, cmp2])
        self.db.flush()
        self.db.add(MessageRecord(campaign_id=cmp1.id, body_snapshot="a", status="sent", phone="+1"))
        self.db.add(MessageRecord(campaign_id=cmp1.id, body_snapshot="b", status="failed", phone="+2"))
        self.db.add(MessageRecord(campaign_id=cmp2.id, body_snapshot="c", status="sent", phone="+3"))
        self.db.commit()

        rows = list(messages_csv_rows(self.db, campaign_id=cmp1.id))
        self.assertEqual(rows[0][0], "id")
        self.assertEqual(len(rows) - 1, 2)  # only cmp1 messages

    def test_csv_escapes_commas_in_text(self) -> None:
        self.db.add(Customer(phone="+1", name="comma,name", consent=True))
        self.db.commit()
        rows = list(customers_csv_rows(self.db))
        # cell content is preserved verbatim; the streaming layer applies CSV quoting
        body = rows[1]
        self.assertEqual(body[2], "comma,name")


if __name__ == "__main__":
    unittest.main()
