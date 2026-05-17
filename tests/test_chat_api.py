"""WeChat-style 1-on-1 chat for customers.

POST /api/customers/{id}/messages   — send a reply via a chosen TG account
GET  /api/customers/{id}/messages   — full conversation history (both directions)

Outbound calls go through a stubbed adapter so the tests don't need a
live Telegram client.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.core.security import hash_password
from backend.app.main import app
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission
from backend.app.models.customer import Customer
from backend.app.models.message import MessageRecord
from backend.app.models.tenant import BusinessAgent, Merchant
from backend.app.telegram.adapter import TelegramSendResult


client = TestClient(app)


def _wipe(db, *models):
    for model in models:
        for row in db.query(model).all():
            db.delete(row)
    db.commit()


def _bootstrap_admin():
    client.post("/api/auth/bootstrap-admin",
                json={"username": "root", "password": "admin1234"})
    r = client.post("/api/auth/login",
                    json={"username": "root", "password": "admin1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class CustomerChatTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        _wipe(self.db, MessageRecord, Customer, AccountGroupMember,
              Account, AccountGroup, SupportAgentGroupPermission,
              SupportAgent, Merchant, BusinessAgent)
        self.auth = _bootstrap_admin()

        acc = Account(
            tg_user_id="5876543210",
            phone="+12792412211",
            session_path="/tmp/fake.session",
            status="active",
            enabled=True,
        )
        self.db.add(acc)
        self.db.flush()
        self.account_id = acc.id

        cust = Customer(phone="+19990001111", name="Alice", status="assigned",
                        assigned_account_id=acc.id)
        self.db.add(cust)
        self.db.commit()
        self.customer_id = cust.id

    def tearDown(self) -> None:
        self.db.close()

    def _stubbed_send(self, *, ok=True, error_message=None):
        # Match adapter.send_message(account, target, body, proxy=, entities=).
        async def fake(account, target, body, proxy=None, entities=None):
            return TelegramSendResult(
                ok=ok,
                external_message_id="msg-42" if ok else None,
                target_tg_user_id="999" if ok else None,
                error_code=None if ok else "rpc_error",
                error_message=error_message,
            )
        return fake

    def _stubbed_send_file(self, *, ok=True, error_message=None):
        async def fake(account, target, file_path, caption=None, proxy=None):
            # Record the file path so the test can assert it exists.
            self._last_send_file = file_path
            return TelegramSendResult(
                ok=ok,
                external_message_id="img-7" if ok else None,
                target_tg_user_id="999" if ok else None,
                error_code=None if ok else "rpc_error",
                error_message=error_message,
            )
        return fake

    def test_post_message_file_uploads_and_sends_image(self) -> None:
        from backend.app.telegram import adapter as adapter_module
        from pathlib import Path as _Path
        # 1x1 transparent PNG
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
        )
        with patch.object(adapter_module, "get_adapter") as ga:
            stub = type("Stub", (), {
                "configured": True,
                "send_file": staticmethod(self._stubbed_send_file()),
            })()
            ga.return_value = stub
            r = client.post(
                f"/api/customers/{self.customer_id}/messages/file",
                data={"account_id": str(self.account_id), "caption": "看图"},
                files={"file": ("a.png", png, "image/png")},
                headers=self.auth,
            )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "sent")
        self.assertEqual(body["body_snapshot"], "看图")
        self.assertEqual(body["attachment_mime"], "image/png")
        self.assertTrue(body["attachment_path"].startswith("chat/"))
        # File written to upload_dir; adapter called with the on-disk path.
        self.assertTrue(_Path(self._last_send_file).is_file())

        # And the attachment-serve route returns the bytes back.
        gr = client.get(
            f"/api/customers/{self.customer_id}/messages/{body['id']}/attachment",
            headers=self.auth,
        )
        self.assertEqual(gr.status_code, 200)
        self.assertEqual(gr.headers["content-type"], "image/png")
        self.assertEqual(gr.content, png)

    def test_post_message_file_rejects_non_image_mime(self) -> None:
        r = client.post(
            f"/api/customers/{self.customer_id}/messages/file",
            data={"account_id": str(self.account_id), "caption": ""},
            files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("图片", r.json()["detail"])

    def test_post_message_sends_and_persists_outbound_row(self) -> None:
        from backend.app.telegram import adapter as adapter_module

        with patch.object(adapter_module, "get_adapter") as get_adapter_mock:
            stub = type("Stub", (), {
                "configured": True,
                # staticmethod so Python doesn't auto-bind `self` to the
                # stub instance when the route calls adapter.send_message().
                "send_message": staticmethod(self._stubbed_send()),
            })()
            get_adapter_mock.return_value = stub

            r = client.post(
                f"/api/customers/{self.customer_id}/messages",
                json={"account_id": self.account_id, "text": "你好 Alice"},
                headers=self.auth,
            )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["direction"], "outbound")
        self.assertEqual(body["status"], "sent")
        self.assertEqual(body["body_snapshot"], "你好 Alice")

        with SessionLocal() as db:
            row = db.get(MessageRecord, body["id"])
            self.assertEqual(row.direction, "outbound")
            self.assertEqual(row.customer_id, self.customer_id)
            self.assertEqual(row.account_id, self.account_id)
            self.assertEqual(row.phone, "+19990001111")

    def test_post_message_failure_persists_failed_row(self) -> None:
        from backend.app.telegram import adapter as adapter_module

        with patch.object(adapter_module, "get_adapter") as get_adapter_mock:
            stub = type("Stub", (), {
                "configured": True,
                "send_message": staticmethod(self._stubbed_send(ok=False, error_message="boom")),
            })()
            get_adapter_mock.return_value = stub

            r = client.post(
                f"/api/customers/{self.customer_id}/messages",
                json={"account_id": self.account_id, "text": "hi"},
                headers=self.auth,
            )
        # 502 = upstream Telegram error; client should surface it
        self.assertEqual(r.status_code, 502, r.text)

        with SessionLocal() as db:
            # Failure still leaves an audit trail row so the operator can
            # see what they tried to send.
            rows = list(db.query(MessageRecord).filter(
                MessageRecord.customer_id == self.customer_id,
                MessageRecord.direction == "outbound",
            ))
            self.assertEqual(len(rows), 1)
            self.assertIn(rows[0].status, ("failed", "failed_permanent"))

    def test_get_messages_returns_history_in_chronological_order(self) -> None:
        from datetime import UTC, datetime, timedelta
        base = datetime.now(UTC)

        # Hand-seed a mixed conversation: out, in, out, in.
        for i, (direction, text, status) in enumerate([
            ("outbound", "hi",       "sent"),
            ("inbound",  "hey",      "received"),
            ("outbound", "how are u","sent"),
            ("inbound",  "good",     "received"),
        ]):
            rec = MessageRecord(
                account_id=self.account_id,
                customer_id=self.customer_id,
                phone="+19990001111",
                body_snapshot=text,
                direction=direction,
                status=status,
            )
            # Stagger created_at so ordering is deterministic.
            rec.created_at = base + timedelta(seconds=i)
            self.db.add(rec)
        self.db.commit()

        r = client.get(
            f"/api/customers/{self.customer_id}/messages",
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.text)
        rows = r.json()
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            [(row["direction"], row["body_snapshot"]) for row in rows],
            [("outbound", "hi"), ("inbound", "hey"),
             ("outbound", "how are u"), ("inbound", "good")],
        )

    def test_get_messages_orders_by_sent_at_not_created_at(self) -> None:
        # Simulates a listen_worker reconnect burst: real Telegram send
        # times (sent_at) are 1s apart but DB persistence (created_at)
        # is reversed because the catch-up landed them in inverse order.
        # The endpoint must order by sent_at so the chronological view
        # matches what the user actually sent.
        from datetime import UTC, datetime, timedelta
        sent_base = datetime(2026, 5, 16, 20, 30, tzinfo=UTC)
        persist_base = datetime(2026, 5, 16, 21, 5, tzinfo=UTC)
        texts = ["one", "two", "three"]
        # Inverse persistence order: 'three' lands first, 'one' last.
        for i, text in enumerate(texts):
            rec = MessageRecord(
                account_id=self.account_id,
                customer_id=self.customer_id,
                phone="+19990001111",
                body_snapshot=text,
                direction="inbound",
                status="received",
                sent_at=(sent_base + timedelta(minutes=i)).isoformat(),
            )
            rec.created_at = persist_base + timedelta(seconds=len(texts) - i)
            self.db.add(rec)
        self.db.commit()

        r = client.get(
            f"/api/customers/{self.customer_id}/messages",
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.text)
        rows = r.json()
        self.assertEqual([row["body_snapshot"] for row in rows], texts)

    def test_post_message_rejects_empty_text(self) -> None:
        r = client.post(
            f"/api/customers/{self.customer_id}/messages",
            json={"account_id": self.account_id, "text": "   "},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 400, r.text)

    def test_post_message_with_auto_translate_stores_both(self) -> None:
        # auto_translate=true: server translates draft into customer's
        # last_source_lang, stores translated as body_snapshot and the
        # original Chinese as translation. Both visible in the UI.
        with SessionLocal() as db:
            cust = db.get(Customer, self.customer_id)
            cust.last_source_lang = "en"
            db.commit()

        from backend.app.telegram import adapter as adapter_module
        from backend.app.services import translator

        with patch.object(adapter_module, "get_adapter") as get_adapter_mock, \
             patch.object(translator, "_google_translate",
                          return_value=("Hello Alice", "zh-CN")):
            stub = type("Stub", (), {
                "configured": True,
                "send_message": staticmethod(self._stubbed_send()),
            })()
            get_adapter_mock.return_value = stub

            r = client.post(
                f"/api/customers/{self.customer_id}/messages",
                json={
                    "account_id": self.account_id,
                    "text": "你好 Alice",
                    "auto_translate": True,
                },
                headers=self.auth,
            )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        # body_snapshot is what was actually sent (English).
        self.assertEqual(body["body_snapshot"], "Hello Alice")
        # translation keeps the operator's original Chinese for reference.
        self.assertEqual(body["translation"], "你好 Alice")

    def test_translate_cache_endpoint_persists_translation_on_inbound(self) -> None:
        # Existing inbound row without translation — POST the cache
        # endpoint to translate + store + return it. Second call returns
        # the cached value without hitting the provider again.
        with SessionLocal() as db:
            rec = MessageRecord(
                account_id=self.account_id,
                customer_id=self.customer_id,
                phone="+19990001111",
                body_snapshot="Hello there",
                direction="inbound",
                status="received",
            )
            db.add(rec)
            db.commit()
            msg_id = rec.id

        from backend.app.services import translator
        with patch.object(translator, "_google_translate",
                          return_value=("你好", "en")) as mock_call:
            r = client.post(
                f"/api/customers/{self.customer_id}/messages/{msg_id}/translate",
                headers=self.auth,
            )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["translation"], "你好")
        with SessionLocal() as db:
            self.assertEqual(db.get(MessageRecord, msg_id).translation, "你好")

        # Second call: cached, no provider hit.
        with patch.object(translator, "_google_translate",
                          side_effect=AssertionError("should be cached")):
            r2 = client.post(
                f"/api/customers/{self.customer_id}/messages/{msg_id}/translate",
                headers=self.auth,
            )
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertEqual(r2.json()["translation"], "你好")

    def test_post_message_rejects_account_in_wrong_tenant(self) -> None:
        # An account belonging to another merchant must not be usable.
        ba = BusinessAgent(name="ba-x", password_hash=hash_password("p"), status=True)
        self.db.add(ba)
        self.db.flush()
        other_m = Merchant(name="m-x", password_hash=hash_password("p"),
                           status=True, business_agent_id=ba.id)
        self.db.add(other_m)
        self.db.flush()
        other_acc = Account(tg_user_id="other", session_path="/tmp/other.session",
                            status="active", enabled=True, merchant_id=other_m.id)
        self.db.add(other_acc)
        self.db.commit()

        # Log in as the other merchant; their account_id is other_acc.id,
        # but our customer (self.customer_id) belongs to admin scope.
        r = client.post("/api/auth/merchant-login",
                        json={"username": "m-x", "password": "p"})
        token = r.json()["access_token"]

        r = client.post(
            f"/api/customers/{self.customer_id}/messages",
            json={"account_id": other_acc.id, "text": "hi"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Cross-tenant customer → 404 (hide existence)
        self.assertEqual(r.status_code, 404, r.text)


if __name__ == "__main__":
    unittest.main()
