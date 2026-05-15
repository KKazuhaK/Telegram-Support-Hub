import unittest
from dataclasses import dataclass
from unittest.mock import patch

import tests.support as support

SessionLocal = support.install_sqlite_session()

from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.campaign import Campaign
from backend.app.workers import execute_operation


@dataclass
class _FakeOpResult:
    """Drop-in replacement for adapter.OperationResult so the test doesn't
    have to depend on Telethon being installed."""
    ok: bool
    detail: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def _seed(db, n_accounts=2):
    group = AccountGroup(name="g", code="g", enabled=True, daily_limit=1000)
    db.add(group)
    db.flush()
    accs = []
    for i in range(n_accounts):
        acc = Account(
            tg_user_id=f"acc{i}", session_path=f"/tmp/acc{i}.session",
            status="active", enabled=True,
        )
        db.add(acc)
        db.flush()
        db.add(AccountGroupMember(account_id=acc.id, group_id=group.id, is_primary=True))
        accs.append(acc)
    db.commit()
    return group, accs


def _make_campaign(db, group_id, *, task_kind, operation_target, extra=None):
    c = Campaign(
        name=f"t-{operation_target}",
        status="running",
        task_kind=task_kind,
        operation_target=operation_target,
        target_type=operation_target,
        account_group_ids=[group_id],
        send_settings={
            "failure_interval_seconds": 1,
            "random_max_seconds": 0,
            "task_concurrency": 5,
            "max_per_account": 3,
        },
        extra_params=extra,
        target_count=2,
        queued_count=0,
    )
    db.add(c)
    db.commit()
    return c


class ExecuteBatchOpTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        from backend.app.models.data_groups import Material, MaterialGroup
        from backend.app.models.message import MessageRecord
        for model in (MessageRecord, Campaign, Material, MaterialGroup,
                      AccountGroupMember, Account, AccountGroup):
            for row in self.db.query(model).all():
                self.db.delete(row)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_delete_friend_runs_per_account_and_counts(self) -> None:
        group, accs = _seed(self.db)
        cmp = _make_campaign(self.db, group.id, task_kind="batch_op",
                             operation_target="delete_friend")

        calls = []

        def fake_op(account, proxy, operation, params):
            calls.append((account.id, operation))
            return _FakeOpResult(ok=True, detail=f"{operation} done")

        with patch.object(execute_operation, "_run_operation", side_effect=fake_op):
            result = execute_operation.execute_operation_campaign(cmp.id)

        self.assertEqual(result["ok_count"], 2)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual({c[1] for c in calls}, {"delete_friend"})
        self.assertEqual({c[0] for c in calls}, {a.id for a in accs})

        with SessionLocal() as db:
            updated = db.get(Campaign, cmp.id)
            self.assertEqual(updated.sent_count, 2)
            self.assertEqual(updated.status, "completed")

    def test_failure_marks_campaign_partially_failed(self) -> None:
        group, accs = _seed(self.db)
        cmp = _make_campaign(self.db, group.id, task_kind="batch_op",
                             operation_target="leave_other_devices")

        def half_fail(account, proxy, operation, params):
            ok = account.id == accs[0].id
            return _FakeOpResult(
                ok=ok, error_code=None if ok else "boom",
                error_message=None if ok else "API rejected",
            )

        with patch.object(execute_operation, "_run_operation", side_effect=half_fail):
            result = execute_operation.execute_operation_campaign(cmp.id)

        self.assertEqual(result["ok_count"], 1)
        self.assertEqual(result["failed_count"], 1)
        with SessionLocal() as db:
            updated = db.get(Campaign, cmp.id)
            self.assertEqual(updated.failed_count, 1)
            self.assertEqual(updated.status, "partially_failed")

    def test_modify_nickname_passes_extra_params(self) -> None:
        group, accs = _seed(self.db, n_accounts=1)
        cmp = _make_campaign(self.db, group.id, task_kind="modify_info",
                             operation_target="modify_nickname",
                             extra={"new_value": "Brand New"})

        captured = {}

        def fake_op(account, proxy, operation, params):
            captured["op"] = operation
            captured["params"] = params
            return _FakeOpResult(ok=True)

        with patch.object(execute_operation, "_run_operation", side_effect=fake_op):
            execute_operation.execute_operation_campaign(cmp.id)

        self.assertEqual(captured["op"], "modify_nickname")
        self.assertEqual(captured["params"], {"new_value": "Brand New"})

    def test_skipped_when_kind_is_broadcast(self) -> None:
        group, _ = _seed(self.db)
        cmp = _make_campaign(self.db, group.id, task_kind="broadcast",
                             operation_target="customer_broadcast")

        # Should be a no-op (broadcasts go through the send_worker, not here).
        result = execute_operation.execute_operation_campaign(cmp.id)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "broadcast_handled_by_send_worker")

    def test_modify_avatar_passes_material_file_path(self) -> None:
        # modify_avatar should resolve the supplied material_id to its
        # stored file_path before calling the adapter; if the material is
        # missing or has no file the call must fail loudly so a typo'd
        # campaign doesn't silently no-op every account.
        from backend.app.models.data_groups import Material, MaterialGroup
        with SessionLocal() as db:
            g = MaterialGroup(name="avatars", kind="image")
            db.add(g)
            db.flush()
            m = Material(group_id=g.id, content="logo.png", file_path="/tmp/fake-logo.png")
            db.add(m)
            db.commit()
            material_id = m.id

        group, accs = _seed(self.db, n_accounts=1)
        cmp = _make_campaign(self.db, group.id, task_kind="modify_info",
                             operation_target="modify_avatar",
                             extra={"material_id": material_id})

        captured = {}

        def fake_op(account, proxy, operation, params):
            captured["op"] = operation
            captured["params"] = params
            return _FakeOpResult(ok=True)

        with patch.object(execute_operation, "_run_operation", side_effect=fake_op):
            execute_operation.execute_operation_campaign(cmp.id)

        self.assertEqual(captured["op"], "modify_avatar")
        # Worker enriches extra_params with the resolved path so the
        # adapter doesn't need to touch the DB.
        self.assertEqual(captured["params"]["material_id"], material_id)
        self.assertEqual(captured["params"]["file_path"], "/tmp/fake-logo.png")

    def test_modify_avatar_fails_when_material_missing(self) -> None:
        group, _ = _seed(self.db, n_accounts=1)
        cmp = _make_campaign(self.db, group.id, task_kind="modify_info",
                             operation_target="modify_avatar",
                             extra={"material_id": 99999})

        # _run_operation should not even be called because the worker
        # short-circuits with a per-account failure when the material
        # can't be resolved.
        def boom(*_args, **_kwargs):
            raise AssertionError("_run_operation should not be invoked")

        with patch.object(execute_operation, "_run_operation", side_effect=boom):
            result = execute_operation.execute_operation_campaign(cmp.id)

        self.assertEqual(result["ok_count"], 0)
        self.assertEqual(result["failed_count"], 1)

    def test_disabled_or_inactive_accounts_excluded(self) -> None:
        group, accs = _seed(self.db, n_accounts=3)
        # Disable account 0; mark account 1 as error
        with SessionLocal() as db:
            db.get(Account, accs[0].id).enabled = False
            db.get(Account, accs[1].id).status = "error"
            db.commit()

        cmp = _make_campaign(self.db, group.id, task_kind="batch_op",
                             operation_target="delete_friend")

        called_ids = []

        def fake_op(account, proxy, operation, params):
            called_ids.append(account.id)
            return _FakeOpResult(ok=True)

        with patch.object(execute_operation, "_run_operation", side_effect=fake_op):
            execute_operation.execute_operation_campaign(cmp.id)

        # Only the third (enabled + active) account ran.
        self.assertEqual(called_ids, [accs[2].id])


if __name__ == "__main__":
    unittest.main()
