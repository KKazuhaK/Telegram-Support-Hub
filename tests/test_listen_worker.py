import asyncio
import unittest
from unittest.mock import patch

import tests.support as support

SessionLocal = support.install_sqlite_session()

from sqlalchemy import select

from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.campaign import Campaign
from backend.app.models.customer import Customer, Friend
from backend.app.models.message import MessageRecord
from backend.app.workers.listen_worker import _persist_reply


def _seed_full(db):
    group = AccountGroup(name="g", code="g", enabled=True, daily_limit=1000)
    db.add(group)
    db.flush()
    account = Account(tg_user_id="u1", session_path="/tmp/u1.session", status="active", enabled=True)
    db.add(account)
    db.flush()
    db.add(AccountGroupMember(account_id=account.id, group_id=group.id, is_primary=True))
    customer = Customer(phone="+8613800000000", name="客户A", consent=True)
    db.add(customer)
    friend = Friend(account_id=account.id, account_group_id=group.id,
                    tg_user_id="999", username="alice", phone="+8613800000000",
                    nickname="Alice", status="contacted")
    db.add(friend)
    campaign = Campaign(name="c", template_id=None, status="running")
    db.add(campaign)
    db.flush()

    msg = MessageRecord(
        campaign_id=campaign.id,
        account_id=account.id,
        target_tg_user_id="999",
        phone="+8613800000000",
        body_snapshot="hi",
        status="sent",
    )
    db.add(msg)
    db.commit()
    return account, customer, friend, campaign, msg


class ListenWorkerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        for model in (MessageRecord, Campaign, Friend, Customer, AccountGroupMember, Account, AccountGroup):
            for row in self.db.query(model).all():
                self.db.delete(row)
        self.db.commit()
        # Unit tests should not require a live Redis. Stub out the publish call
        # so the real reply_bus is exercised separately (test_reply_bus.py).
        self._publish_patch = patch("backend.app.workers.listen_worker.publish_reply")
        self._publish_mock = self._publish_patch.start()

    def tearDown(self) -> None:
        self._publish_patch.stop()
        self.db.close()

    def test_reply_updates_customer_friend_message_and_campaign(self) -> None:
        account, customer, friend, campaign, msg = _seed_full(self.db)

        payload = {
            "account_id": account.id,
            "tg_user_id": "999",
            "phone": "+8613800000000",
            "text": "thanks!",
            "date": "2026-05-15T12:00:00+00:00",
        }
        asyncio.run(_persist_reply(payload))

        with SessionLocal() as db:
            cust = db.get(Customer, customer.id)
            self.assertEqual(cust.status, "replied")
            self.assertEqual(cust.last_reply_text, "thanks!")
            f = db.get(Friend, friend.id)
            self.assertEqual(f.status, "replied")
            m = db.get(MessageRecord, msg.id)
            self.assertEqual(m.status, "replied")
            self.assertEqual(m.reply_text, "thanks!")
            cmp = db.get(Campaign, campaign.id)
            self.assertEqual(cmp.reply_count, 1)
            acc = db.get(Account, account.id)
            self.assertEqual(acc.total_replies, 1)

    def test_publish_reply_is_called_once(self) -> None:
        account, *_ = _seed_full(self.db)
        payload = {
            "account_id": account.id, "tg_user_id": "999", "phone": "+8613800000000",
            "text": "ping", "date": "2026-05-15T12:00:00+00:00",
        }
        asyncio.run(_persist_reply(payload))
        self.assertEqual(self._publish_mock.call_count, 1)
        published = self._publish_mock.call_args.args[0]
        self.assertEqual(published["account_id"], account.id)
        self.assertEqual(published["text"], "ping")

    def test_reply_matches_customer_by_tg_placeholder_phone(self) -> None:
        # Promoted-from-orphan customers carry a placeholder phone like
        # `tg:<sender_id>`. listen_worker must fall back to this when the
        # inbound payload's `phone` doesn't directly match.
        account, *_ = _seed_full(self.db)
        promoted = Customer(phone="tg:7332000121", name="Loan tester",
                            consent=True, status="assigned")
        self.db.add(promoted)
        self.db.commit()

        payload = {
            "account_id": account.id,
            "tg_user_id": "7332000121",
            "phone": None,
            "text": "你好",
            "date": "2026-05-16T01:00:00+00:00",
        }
        asyncio.run(_persist_reply(payload))

        with SessionLocal() as db:
            cust = db.get(Customer, promoted.id)
            self.assertEqual(cust.status, "replied")
            self.assertEqual(cust.last_reply_text, "你好")
            inbound = db.query(MessageRecord).filter_by(
                direction="inbound", target_tg_user_id="7332000121"
            ).one()
            self.assertEqual(inbound.customer_id, promoted.id)

    def test_unknown_sender_is_auto_promoted_to_customer(self) -> None:
        # User asked for inbounds from unknown senders to go straight
        # into the 客户 list instead of piling up in 未匹配. Verify a
        # fresh sender ends up with a Customer (consent=True, placeholder
        # phone, assigned to the receiving account) and the inbound
        # MessageRecord is bound to it.
        account, *_ = _seed_full(self.db)
        payload = {
            "account_id": account.id,
            "tg_user_id": "5555000999",
            "username": "rando",
            "phone": None,
            "text": "hi",
            "date": "2026-05-17T03:00:00+00:00",
        }
        asyncio.run(_persist_reply(payload))
        with SessionLocal() as db:
            cust = db.scalar(
                select(Customer).where(Customer.phone == "tg:5555000999")
            )
            self.assertIsNotNone(cust)
            self.assertTrue(cust.consent)
            self.assertEqual(cust.assigned_account_id, account.id)
            self.assertEqual(cust.source, "auto_promoted_from_inbound")
            inbound = db.query(MessageRecord).filter_by(
                direction="inbound", target_tg_user_id="5555000999",
            ).one()
            self.assertEqual(inbound.customer_id, cust.id)

    def test_reply_with_attachment_persists_image_columns(self) -> None:
        # Telethon photo / image-document path: adapter passes
        # attachment_path + attachment_mime in the payload; the inbound
        # MessageRecord must carry them through so the chat UI can
        # render <img>. Empty text falls back to '[图片]' so plain-text
        # views still show something.
        account, customer, *_ = _seed_full(self.db)
        payload = {
            "account_id": account.id, "tg_user_id": "999",
            "phone": "+8613800000000", "text": "",
            "date": "2026-05-17T01:00:00+00:00",
            "attachment_path": "chat/abc123.jpg",
            "attachment_mime": "image/jpeg",
        }
        asyncio.run(_persist_reply(payload))
        with SessionLocal() as db:
            inbound = db.query(MessageRecord).filter_by(
                direction="inbound", customer_id=customer.id,
            ).one()
            self.assertEqual(inbound.attachment_path, "chat/abc123.jpg")
            self.assertEqual(inbound.attachment_mime, "image/jpeg")
            self.assertEqual(inbound.body_snapshot, "[图片]")

    def test_reply_without_match_is_silent(self) -> None:
        # no seed
        payload = {
            "account_id": 999,
            "tg_user_id": "no-such",
            "phone": None,
            "text": "anyone home?",
            "date": "2026-05-15T12:00:00+00:00",
        }
        # should not raise
        asyncio.run(_persist_reply(payload))


if __name__ == "__main__":
    unittest.main()
