import unittest
from datetime import UTC, datetime
from unittest.mock import patch

import tests.support as support

SessionLocal = support.install_sqlite_session()

from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.campaign import Campaign
from backend.app.models.message import MessageRecord
from backend.app.telegram.adapter import TelegramSendResult
from backend.app.workers import send_tasks


class _NopLock:
    def __enter__(self):
        return True

    def __exit__(self, *args):
        return False


def _seed(db):
    group = AccountGroup(name="g", code="g", enabled=True, daily_limit=1000)
    db.add(group)
    db.flush()
    account = Account(
        tg_user_id="u1",
        session_path="/tmp/u1.session",
        status="active",
        enabled=True,
        daily_limit=10,
        sent_today=0,
    )
    db.add(account)
    db.flush()
    db.add(AccountGroupMember(account_id=account.id, group_id=group.id, is_primary=True))

    campaign = Campaign(name="c1", template_id=None, status="running",
                        send_settings={"success_interval_seconds": 10, "failure_interval_seconds": 20,
                                       "random_min_seconds": 0, "random_max_seconds": 0})
    db.add(campaign)
    db.flush()

    msg = MessageRecord(
        campaign_id=campaign.id,
        account_id=account.id,
        target_tg_user_id="100200300",
        body_snapshot="hello",
        status="queued",
        next_run_at=datetime.now(UTC).isoformat(),
    )
    db.add(msg)
    db.commit()
    return account, campaign, msg


class SendWorkerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        for model in (MessageRecord, Campaign, AccountGroupMember, Account, AccountGroup):
            for row in self.db.query(model).all():
                self.db.delete(row)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_successful_send_marks_message_and_increments_counters(self) -> None:
        account, campaign, msg = _seed(self.db)

        def fake_send(account, proxy, target, body, entities=None):
            return TelegramSendResult(ok=True, external_message_id="mid-1", target_tg_user_id="100200300")

        with patch.object(send_tasks, "_send_via_adapter", side_effect=fake_send), \
             patch.object(send_tasks, "account_send_lock", lambda aid, ttl: _NopLock()):
            result = send_tasks.dispatch_send_queue(limit=10)

        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["failed"], 0)
        with SessionLocal() as db:
            stored = db.get(MessageRecord, msg.id)
            self.assertEqual(stored.status, "sent")
            self.assertEqual(stored.external_message_id, "mid-1")
            acc = db.get(Account, account.id)
            self.assertEqual(acc.sent_today, 1)
            self.assertEqual(acc.total_sent, 1)
            cmp = db.get(Campaign, campaign.id)
            self.assertEqual(cmp.sent_count, 1)
            # campaign auto-completes when queue empty
            self.assertIn(cmp.status, {"completed", "running"})

    def test_failure_below_threshold_goes_to_retry(self) -> None:
        _, _, msg = _seed(self.db)

        def fake_send(*_a, **_kw):
            return TelegramSendResult(ok=False, error_code="boom", error_message="nope")

        with patch.object(send_tasks, "_send_via_adapter", side_effect=fake_send), \
             patch.object(send_tasks, "account_send_lock", lambda aid, ttl: _NopLock()):
            send_tasks.dispatch_send_queue(limit=10)

        with SessionLocal() as db:
            stored = db.get(MessageRecord, msg.id)
            self.assertEqual(stored.status, "retry")
            self.assertEqual(stored.error_code, "boom")
            self.assertEqual(stored.attempt_count, 1)

    def test_failure_at_threshold_goes_to_failed_permanent(self) -> None:
        _, _, msg = _seed(self.db)
        # bump attempt_count so next failure crosses MAX_FAILED_ATTEMPTS
        with SessionLocal() as db:
            stored = db.get(MessageRecord, msg.id)
            stored.attempt_count = 2  # MAX_FAILED_ATTEMPTS default = 3
            db.commit()

        def fake_send(*_a, **_kw):
            return TelegramSendResult(ok=False, error_code="session_unauthorized", error_message="x")

        with patch.object(send_tasks, "_send_via_adapter", side_effect=fake_send), \
             patch.object(send_tasks, "account_send_lock", lambda aid, ttl: _NopLock()):
            send_tasks.dispatch_send_queue(limit=10)

        with SessionLocal() as db:
            stored = db.get(MessageRecord, msg.id)
            self.assertEqual(stored.status, "failed_permanent")
            acc = db.query(Account).first()
            self.assertEqual(acc.status, "error")

    def test_locked_account_is_skipped(self) -> None:
        _, _, msg = _seed(self.db)

        class _Lock:
            def __enter__(self):
                return False

            def __exit__(self, *args):
                return False

        with patch.object(send_tasks, "account_send_lock", lambda aid, ttl: _Lock()):
            result = send_tasks.dispatch_send_queue(limit=10)

        self.assertEqual(result["skipped_locked"], 1)
        with SessionLocal() as db:
            stored = db.get(MessageRecord, msg.id)
            self.assertEqual(stored.status, "queued")

    def test_quota_exhausted_postpones(self) -> None:
        account, _, msg = _seed(self.db)
        with SessionLocal() as db:
            acc = db.get(Account, account.id)
            acc.sent_today = acc.daily_limit
            db.commit()

        with patch.object(send_tasks, "account_send_lock", lambda aid, ttl: _NopLock()):
            send_tasks.dispatch_send_queue(limit=10)

        with SessionLocal() as db:
            stored = db.get(MessageRecord, msg.id)
            self.assertIn(stored.status, {"queued", "retry"})
            self.assertIsNotNone(stored.next_run_at)

    def test_hourly_limit_postpones_when_exceeded(self) -> None:
        # Seeded account has daily_limit=10 and no hourly_limit. Set
        # hourly_limit=2 and pre-stamp 2 sent rows in the last hour;
        # the next dispatch tick should postpone instead of sending.
        from datetime import UTC, datetime, timedelta
        account, campaign, msg = _seed(self.db)
        recent = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        with SessionLocal() as db:
            acc = db.get(Account, account.id)
            acc.hourly_limit = 2
            for i in range(2):
                db.add(MessageRecord(
                    campaign_id=campaign.id, account_id=acc.id,
                    target_tg_user_id=f"prev{i}", body_snapshot="x",
                    direction="outbound", status="sent", sent_at=recent,
                ))
            db.commit()

        def fake_send(*_a, **_kw):
            return TelegramSendResult(ok=True, external_message_id="m", target_tg_user_id="t")

        with patch.object(send_tasks, "_send_via_adapter", side_effect=fake_send), \
             patch.object(send_tasks, "account_send_lock", lambda aid, ttl: _NopLock()):
            result = send_tasks.dispatch_send_queue(limit=10)

        # Send was NOT issued — postponed because hourly cap reached.
        self.assertEqual(result["sent"], 0)
        with SessionLocal() as db:
            stored = db.get(MessageRecord, msg.id)
            self.assertEqual(stored.status, "queued")
            self.assertIsNotNone(stored.next_run_at)

    def test_peer_flood_error_kills_account_immediately(self) -> None:
        # Telegram's anti-spam flag. Continued sends escalate toward a
        # permaban, so the account must be disabled on the spot — no
        # retry loop, no waiting until attempt_count == max.
        _, _, msg = _seed(self.db)

        def fake_send(*_a, **_kw):
            return TelegramSendResult(
                ok=False, error_code="PeerFloodError",
                error_message="Too many requests (caused by SendMessageRequest)",
            )

        with patch.object(send_tasks, "_send_via_adapter", side_effect=fake_send), \
             patch.object(send_tasks, "account_send_lock", lambda aid, ttl: _NopLock()):
            send_tasks.dispatch_send_queue(limit=10)

        with SessionLocal() as db:
            stored = db.get(MessageRecord, msg.id)
            # No retry — straight to terminal.
            self.assertEqual(stored.status, "failed_permanent")
            self.assertEqual(stored.attempt_count, 1)
            acc = db.query(Account).first()
            self.assertFalse(acc.enabled)
            self.assertEqual(acc.status, "limited")
            self.assertIn("PeerFloodError", acc.last_error or "")

    def test_campaign_with_only_failures_transitions_to_failed(self) -> None:
        # All-failure broadcast must end in 'failed', not 'partially_failed'
        # — the latter implied at least one success, which is misleading.
        _, campaign, msg = _seed(self.db)
        with SessionLocal() as db:
            stored = db.get(MessageRecord, msg.id)
            stored.attempt_count = 2
            db.commit()

        def fake_send(*_a, **_kw):
            return TelegramSendResult(ok=False, error_code="x", error_message="y")

        with patch.object(send_tasks, "_send_via_adapter", side_effect=fake_send), \
             patch.object(send_tasks, "account_send_lock", lambda aid, ttl: _NopLock()):
            send_tasks.dispatch_send_queue(limit=10)

        with SessionLocal() as db:
            cmp = db.get(Campaign, campaign.id)
            self.assertEqual(cmp.status, "failed")
            self.assertIsNotNone(cmp.completed_at)

    def test_stuck_running_campaign_recovered_on_idle_tick(self) -> None:
        # Reproduce the bug: the last message was marked failed_permanent
        # on a previous tick. Today's tick has no rows for this campaign,
        # so the old per-batch sweep never re-checked it. The new full
        # scan should now transition it on the next idle tick.
        _, campaign, msg = _seed(self.db)
        with SessionLocal() as db:
            stored = db.get(MessageRecord, msg.id)
            stored.status = "failed_permanent"
            stored.attempt_count = 3
            cmp = db.get(Campaign, campaign.id)
            cmp.failed_count = 1
            db.commit()

        # Idle tick — no queued/retry rows exist.
        with patch.object(send_tasks, "account_send_lock", lambda aid, ttl: _NopLock()):
            send_tasks.dispatch_send_queue(limit=10)

        with SessionLocal() as db:
            cmp = db.get(Campaign, campaign.id)
            self.assertEqual(cmp.status, "failed")
            self.assertIsNotNone(cmp.completed_at)

    def test_reset_daily_quota_zeros_counters(self) -> None:
        account, _, _ = _seed(self.db)
        with SessionLocal() as db:
            acc = db.get(Account, account.id)
            acc.sent_today = 5
            grp = db.query(AccountGroup).first()
            grp.sent_today = 7
            db.commit()

        result = send_tasks.reset_daily_quota()
        self.assertEqual(result["accounts_reset"], 1)
        self.assertEqual(result["groups_reset"], 1)
        with SessionLocal() as db:
            self.assertEqual(db.get(Account, account.id).sent_today, 0)
            self.assertEqual(db.query(AccountGroup).first().sent_today, 0)


if __name__ == "__main__":
    unittest.main()
