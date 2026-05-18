import io
import unittest
import zipfile

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.main import app
from sqlalchemy import select

from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission
from backend.app.models.proxy import AccountProxyLog


def _make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


_grp_counter = [0]


def _make_group(name: str = "imp") -> int:
    """import-zip now requires a target group. Tests create a throw-away
    group and pass its id in the form payload. The counter suffix avoids
    AccountGroup.name/code unique-constraint clashes when a single test
    invokes the helper more than once."""
    _grp_counter[0] += 1
    slug = f"{name}-{_grp_counter[0]}"
    with SessionLocal() as db:
        grp = AccountGroup(name=slug, code=slug, enabled=True, daily_limit=1000)
        db.add(grp); db.commit()
        return grp.id


class AccountsBatchApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (
                AccountProxyLog, AccountGroupMember, Account, AccountGroup,
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

        zip_bytes = _make_zip({
            "1001/acc.session": b"fake-session-bytes",
            "1002/acc.session": b"fake-session-bytes",
            "1003/acc.session": b"fake-session-bytes",
        })
        self.client.post(
            "/api/accounts/import-zip",
            files={"sessions": ("sessions.zip", zip_bytes, "application/zip")},
            data={"group_id": str(_make_group())},
            headers=self.auth,
        )

    def _ids(self) -> list[int]:
        with SessionLocal() as db:
            return [a.id for a in db.query(Account).order_by(Account.id.asc())]

    def test_list_filter_by_status(self) -> None:
        all_ids = self._ids()
        # Mark one as archived
        with SessionLocal() as db:
            db.get(Account, all_ids[0]).status = "archived"
            db.commit()

        active = self.client.get("/api/accounts?status=active", headers=self.auth).json()
        archived = self.client.get("/api/accounts?status=archived", headers=self.auth).json()
        # `imported` is the default new state; "active" filter only matches active rows
        imported = self.client.get("/api/accounts?status=imported", headers=self.auth).json()

        self.assertEqual([a["id"] for a in archived], [all_ids[0]])
        self.assertEqual({a["id"] for a in imported}, set(all_ids[1:]))
        self.assertEqual(active, [])

    def test_batch_set_enabled_false(self) -> None:
        ids = self._ids()
        resp = self.client.post(
            "/api/accounts/batch",
            json={"ids": ids, "enabled": False},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json(), {"updated": len(ids)})
        with SessionLocal() as db:
            for a in db.query(Account).all():
                self.assertFalse(a.enabled)

    def test_batch_archive_status(self) -> None:
        ids = self._ids()[:2]
        resp = self.client.post(
            "/api/accounts/batch",
            json={"ids": ids, "status": "archived"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        with SessionLocal() as db:
            archived = [a for a in db.query(Account).all() if a.status == "archived"]
            self.assertEqual({a.id for a in archived}, set(ids))

    def test_batch_status_must_be_in_allowlist(self) -> None:
        ids = self._ids()
        resp = self.client.post(
            "/api/accounts/batch",
            json={"ids": ids, "status": "weird"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 400)

    def test_batch_delete_removes_rows_and_members(self) -> None:
        ids = self._ids()[:2]
        # Put first id into a group so we can confirm cascade-ish cleanup
        with SessionLocal() as db:
            group = AccountGroup(name="g", code="g", enabled=True)
            db.add(group)
            db.flush()
            db.add(AccountGroupMember(account_id=ids[0], group_id=group.id, is_primary=True))
            db.commit()

        resp = self.client.request(
            "DELETE",
            "/api/accounts/batch",
            json={"ids": ids},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json(), {"deleted": len(ids)})
        with SessionLocal() as db:
            self.assertEqual(db.query(Account).count(), 1)
            # AccountGroupMember row referencing the deleted account must be gone
            self.assertEqual(
                db.query(AccountGroupMember).filter_by(account_id=ids[0]).count(),
                0,
            )

    def test_batch_bind_proxy(self) -> None:
        ids = self._ids()[:2]
        with SessionLocal() as db:
            from backend.app.models.proxy import ProxyEndpoint
            p = ProxyEndpoint(name="p1", protocol="socks5", host="1.1.1.1", port=1080, status="active")
            db.add(p)
            db.commit()
            pid = p.id

        resp = self.client.post(
            "/api/accounts/batch",
            json={"ids": ids, "proxy_id": pid},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        with SessionLocal() as db:
            for aid in ids:
                self.assertEqual(db.get(Account, aid).proxy_id, pid)
            # AccountProxyLog rows recorded
            self.assertGreaterEqual(db.query(AccountProxyLog).count(), 2)

    def test_batch_unbind_proxy(self) -> None:
        ids = self._ids()[:2]
        with SessionLocal() as db:
            from backend.app.models.proxy import ProxyEndpoint
            p = ProxyEndpoint(name="p1", protocol="socks5", host="1.1.1.1", port=1080)
            db.add(p)
            db.commit()
            for a in db.query(Account).filter(Account.id.in_(ids)).all():
                a.proxy_id = p.id
            db.commit()

        resp = self.client.post(
            "/api/accounts/batch",
            json={"ids": ids, "proxy_id": None, "clear_proxy": True},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        with SessionLocal() as db:
            for aid in ids:
                self.assertIsNone(db.get(Account, aid).proxy_id)

    def test_batch_move_group(self) -> None:
        ids = self._ids()[:2]
        with SessionLocal() as db:
            g1 = AccountGroup(name="g1", code="g1", enabled=True)
            g2 = AccountGroup(name="g2", code="g2", enabled=True)
            db.add(g1); db.add(g2)
            db.flush()
            for aid in ids:
                db.add(AccountGroupMember(account_id=aid, group_id=g1.id, is_primary=True))
            db.commit()
            g2_id = g2.id

        resp = self.client.post(
            "/api/accounts/batch",
            json={"ids": ids, "move_to_group_id": g2_id},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        with SessionLocal() as db:
            for aid in ids:
                members = list(db.query(AccountGroupMember).filter_by(account_id=aid).all())
                self.assertEqual([m.group_id for m in members], [g2_id])
                self.assertTrue(members[0].is_primary)

    def test_list_filter_by_nickname_country(self) -> None:
        with SessionLocal() as db:
            ids = self._ids()
            db.get(Account, ids[0]).nickname = "Alice"
            db.get(Account, ids[0]).country = "US"
            db.get(Account, ids[1]).nickname = "Bob"
            db.get(Account, ids[1]).country = "CN"
            db.commit()

        rows_us = self.client.get("/api/accounts?country=US", headers=self.auth).json()
        self.assertEqual([r["country"] for r in rows_us], ["US"])

        rows_alice = self.client.get("/api/accounts?nickname=Alice", headers=self.auth).json()
        self.assertEqual([r["nickname"] for r in rows_alice], ["Alice"])

    def test_batch_endpoints_require_admin(self) -> None:
        # Create a non-admin agent and login as them
        with SessionLocal() as db:
            from backend.app.core.security import hash_password
            db.add(SupportAgent(
                username="staff", role="agent", status="enabled",
                password_hash=hash_password("12345678"),
            ))
            db.commit()
        login = self.client.post("/api/auth/login",
                                 json={"username": "staff", "password": "12345678"})
        staff_auth = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = self.client.post(
            "/api/accounts/batch",
            json={"ids": self._ids(), "enabled": False},
            headers=staff_auth,
        )
        self.assertEqual(resp.status_code, 403)


class ImportZipFlatLayoutTestCase(unittest.TestCase):
    """import-zip should accept the flat layout produced by common
    session-export tools (tdesktop, telethon helpers):

        <user_id>.session
        <user_id>.json         (optional metadata: phone, twofa, ...)

    In addition to the existing `<user_id>/file.session` subfolder form.
    """

    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (
                AccountProxyLog, AccountGroupMember, Account, AccountGroup,
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

    def _upload(self, entries: dict[str, bytes]) -> dict:
        zip_bytes = _make_zip(entries)
        return self.client.post(
            "/api/accounts/import-zip",
            files={"sessions": ("sessions.zip", zip_bytes, "application/zip")},
            data={"group_id": str(_make_group("flat"))},
            headers=self.auth,
        ).json()

    def test_import_zip_requires_group_id(self) -> None:
        # Operator must pick the target account group up front. Without
        # one the upload returns 422 (FastAPI validation) and nothing is
        # written. Verifies the behavior the UI dialog now enforces.
        zip_bytes = _make_zip({"12792412211.session": b"x"})
        r = self.client.post(
            "/api/accounts/import-zip",
            files={"sessions": ("sessions.zip", zip_bytes, "application/zip")},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 422)
        with SessionLocal() as db:
            self.assertEqual(db.query(Account).count(), 0)

    def test_import_zip_rejects_unknown_group_id(self) -> None:
        zip_bytes = _make_zip({"12792412211.session": b"x"})
        r = self.client.post(
            "/api/accounts/import-zip",
            files={"sessions": ("sessions.zip", zip_bytes, "application/zip")},
            data={"group_id": "99999"},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("不存在", r.json()["detail"])

    def test_import_zip_auto_assigns_proxy_from_chosen_group(self) -> None:
        # Operator passes proxy_group_id + max_accounts_per_proxy at
        # import time. New accounts should round-robin across the
        # group's proxies, respecting the cap.
        from backend.app.models.proxy import ProxyEndpoint
        from backend.app.models.data_groups import ProxyGroup
        with SessionLocal() as db:
            pgroup = ProxyGroup(name="pg", remark="")
            db.add(pgroup); db.flush()
            for i in range(2):
                db.add(ProxyEndpoint(
                    name=f"px{i}", protocol="socks5", host=f"10.0.0.{i+1}",
                    port=1080, status="active", group_id=pgroup.id,
                ))
            db.commit()
            pg_id = pgroup.id

        gid = _make_group("ap")
        zip_bytes = _make_zip({
            "1001.session": b"x",
            "1002.session": b"x",
            "1003.session": b"x",
        })
        r = self.client.post(
            "/api/accounts/import-zip",
            files={"sessions": ("s.zip", zip_bytes, "application/zip")},
            data={
                "group_id": str(gid),
                "proxy_group_id": str(pg_id),
                "max_accounts_per_proxy": "2",
            },
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        # 3 accounts, cap 2 per proxy, 2 proxies → 2 proxies fully used.
        # round-robin (least-loaded first): 1st acct → proxy A, 2nd →
        # proxy B, 3rd → proxy A (now both full).
        self.assertEqual(body["proxy_assigned"], 3)
        self.assertEqual(body["proxy_no_pool"], 0)
        with SessionLocal() as db:
            from sqlalchemy import func
            loads = dict(db.execute(
                select(Account.proxy_id, func.count(Account.id))
                .where(Account.proxy_id.isnot(None))
                .group_by(Account.proxy_id)
            ).all())
            self.assertEqual(sum(loads.values()), 3)
            # Each proxy got at most 2 accounts (the cap).
            self.assertTrue(all(v <= 2 for v in loads.values()))

    def test_import_zip_reports_no_pool_when_proxies_exhausted(self) -> None:
        # If every proxy in the chosen group is already at cap, new
        # accounts come in without a proxy and the count surfaces.
        from backend.app.models.proxy import ProxyEndpoint
        from backend.app.models.data_groups import ProxyGroup
        with SessionLocal() as db:
            pgroup = ProxyGroup(name="pg2", remark="")
            db.add(pgroup); db.flush()
            db.add(ProxyEndpoint(
                name="px", protocol="socks5", host="10.0.0.99",
                port=1080, status="active", group_id=pgroup.id,
                max_accounts=1,
            ))
            db.commit()
            pg_id = pgroup.id

        gid = _make_group("ap2")
        zip_bytes = _make_zip({
            "2001.session": b"x", "2002.session": b"x",
        })
        r = self.client.post(
            "/api/accounts/import-zip",
            files={"sessions": ("s.zip", zip_bytes, "application/zip")},
            data={"group_id": str(gid), "proxy_group_id": str(pg_id)},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["proxy_assigned"], 1)
        self.assertEqual(body["proxy_no_pool"], 1)

    def test_import_zip_places_account_in_chosen_group(self) -> None:
        # Selected group is what new accounts join — verify the membership
        # row points at it (not the legacy `未分组` default).
        gid = _make_group("target")
        zip_bytes = _make_zip({"12792412211.session": b"x"})
        r = self.client.post(
            "/api/accounts/import-zip",
            files={"sessions": ("sessions.zip", zip_bytes, "application/zip")},
            data={"group_id": str(gid)},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.text)
        with SessionLocal() as db:
            membership = db.query(AccountGroupMember).one()
            self.assertEqual(membership.group_id, gid)

    def test_flat_layout_imported(self) -> None:
        body = self._upload({
            "12792412211.session": b"fake-session-bytes",
        })
        self.assertEqual(len(body["imported"]), 1, body)
        # Phone-shaped basename is treated as the phone, not the TG user_id.
        # The real numeric user_id gets filled in later by validate_session.
        with SessionLocal() as db:
            acc = db.query(Account).filter(Account.phone == "+12792412211").one()
            self.assertEqual(acc.tg_user_id, "pending:+12792412211")
            self.assertTrue(acc.session_path.endswith("12792412211.session"))

    def test_flat_layout_with_json_sidecar_populates_phone(self) -> None:
        # When the JSON sidecar's user_id is empty (common for tdesktop-
        # style exports), the basename is the phone — not a real TG user
        # id. Account should land with a 'pending:<phone>' placeholder so
        # downstream code knows the real tg_user_id needs to be resolved
        # at session-validate time.
        sidecar = (
            b'{"phone": "12792412211", "twofa": "qq1122", '
            b'"api_id": 2040, "user_id": ""}'
        )
        body = self._upload({
            "12792412211.session": b"fake-session-bytes",
            "12792412211.json": sidecar,
        })
        self.assertEqual(len(body["imported"]), 1, body)
        with SessionLocal() as db:
            acc = db.query(Account).filter(Account.phone == "+12792412211").one()
            self.assertEqual(acc.tg_user_id, "pending:+12792412211")

    def test_flat_layout_uses_sidecar_user_id_when_present(self) -> None:
        # When the sidecar carries a real numeric user_id, prefer it over
        # the phone-derived placeholder.
        sidecar = b'{"phone": "12792412211", "user_id": "5876543210"}'
        body = self._upload({
            "12792412211.session": b"fake-session-bytes",
            "12792412211.json": sidecar,
        })
        self.assertEqual(len(body["imported"]), 1, body)
        with SessionLocal() as db:
            acc = db.query(Account).filter(Account.phone == "+12792412211").one()
            self.assertEqual(acc.tg_user_id, "5876543210")

    def test_flat_layout_without_sidecar_uses_phone_placeholder(self) -> None:
        # Phone-shaped basename + no sidecar — still phone, still placeholder.
        body = self._upload({"12792412211.session": b"fake-session-bytes"})
        self.assertEqual(len(body["imported"]), 1, body)
        with SessionLocal() as db:
            acc = db.query(Account).filter(Account.phone == "+12792412211").one()
            self.assertEqual(acc.tg_user_id, "pending:+12792412211")

    def test_subfolder_layout_still_works(self) -> None:
        body = self._upload({
            "1001/acc.session": b"fake-session-bytes",
        })
        self.assertEqual(len(body["imported"]), 1, body)
        self.assertEqual(body["imported"][0]["user_id"], "1001")

    def test_malformed_json_sidecar_is_ignored(self) -> None:
        # A broken JSON sidecar should not block the session itself from
        # importing — silently skip the metadata. The phone is still
        # derivable from the basename (which is itself phone-shaped),
        # so the account still ends up with the right phone + placeholder.
        body = self._upload({
            "12792412211.session": b"fake-session-bytes",
            "12792412211.json": b"{this is not valid json",
        })
        self.assertEqual(len(body["imported"]), 1, body)
        with SessionLocal() as db:
            acc = db.query(Account).filter(
                Account.tg_user_id == "pending:+12792412211"
            ).one()
            self.assertEqual(acc.phone, "+12792412211")

    def test_orphan_json_without_session_is_skipped(self) -> None:
        # JSON sidecar with no matching .session should not create an account.
        body = self._upload({"12792412211.json": b'{"phone": "12792412211"}'})
        self.assertEqual(body["imported"], [])


class ImportZipTdataLayoutTestCase(unittest.TestCase):
    """tdata zips (Telegram Desktop session export):

        <phone>/2Fa.txt
        <phone>/tdata/key_datas
        <phone>/tdata/D877F783D5D3EF8C/maps
        <phone>/tdata/D877F783D5D3EF8Cs

    Detection looks for any '<stem>/tdata/key_datas' entry. The actual
    binary conversion goes through opentele in production; tests mock
    convert_tdata_zip_entry to return synthetic session bytes so the
    suite doesn't need the C extension installed.
    """

    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (
                AccountProxyLog, AccountGroupMember, Account, AccountGroup,
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

    def _make_tdata_zip(self, *phones: str, with_2fa: bool = True) -> bytes:
        entries: dict[str, bytes] = {}
        for phone in phones:
            if with_2fa:
                entries[f"{phone}/2Fa.txt"] = b"qq1122"
            entries[f"{phone}/tdata/key_datas"] = b"\x00" * 388
            entries[f"{phone}/tdata/D877F783D5D3EF8C/maps"] = b"\x00" * 68
            entries[f"{phone}/tdata/D877F783D5D3EF8Cs"] = b"\x00" * 348
        return _make_zip(entries)

    def test_tdata_zip_is_detected_and_converted(self) -> None:
        from unittest.mock import patch
        from backend.app.api.routes import accounts as accounts_route

        # Fake converter returns deterministic per-phone bytes so we can
        # verify _persist_session wrote the right file.
        def fake_convert(zf, stem):
            return f"FAKE-SESSION-{stem}".encode()

        with patch.object(accounts_route, "convert_tdata_zip_entry",
                          side_effect=fake_convert):
            zip_bytes = self._make_tdata_zip("256753693406", "26775232571")
            r = self.client.post(
                "/api/accounts/import-zip",
                files={"sessions": ("td.zip", zip_bytes, "application/zip")},
                data={"group_id": str(_make_group("td"))},
                headers=self.auth,
            )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body["imported"]), 2, body)

        with SessionLocal() as db:
            phones = {a.phone for a in db.query(Account).all()}
            # 12-digit basenames look phone-shaped → recognized as phones.
            self.assertEqual(phones, {"+256753693406", "+26775232571"})
            # tg_user_id is the pending placeholder until validate_session.
            for acc in db.query(Account).all():
                self.assertTrue(acc.tg_user_id.startswith("pending:+"))

    def test_tdata_conversion_failure_skips_that_phone(self) -> None:
        from unittest.mock import patch
        from backend.app.api.routes import accounts as accounts_route

        # First phone fails, second succeeds — partial import still
        # completes; failed phone goes to `skipped`.
        def flaky_convert(zf, stem):
            if stem == "256753693406":
                raise RuntimeError("bad tdata magic")
            return b"OK"

        with patch.object(accounts_route, "convert_tdata_zip_entry",
                          side_effect=flaky_convert):
            zip_bytes = self._make_tdata_zip("256753693406", "26775232571")
            r = self.client.post(
                "/api/accounts/import-zip",
                files={"sessions": ("td.zip", zip_bytes, "application/zip")},
                data={"group_id": str(_make_group("td"))},
                headers=self.auth,
            )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body["imported"]), 1)
        self.assertEqual(len(body["skipped"]), 1)
        self.assertIn("bad tdata magic", body["skipped"][0]["reason"])

    def test_mixed_zip_with_tdata_and_flat_session_both_import(self) -> None:
        # Some operators have mixed zips. Both paths should fire and
        # no entry should be processed twice.
        from unittest.mock import patch
        from backend.app.api.routes import accounts as accounts_route

        with patch.object(accounts_route, "convert_tdata_zip_entry",
                          return_value=b"FAKE-TDATA"):
            entries = {
                # tdata-style for one phone
                "111111111111/2Fa.txt": b"x",
                "111111111111/tdata/key_datas": b"\x00",
                "111111111111/tdata/D877F783D5D3EF8C/maps": b"\x00",
                "111111111111/tdata/D877F783D5D3EF8Cs": b"\x00",
                # flat-layout .session for another
                "222222222222.session": b"flat-bytes",
            }
            r = self.client.post(
                "/api/accounts/import-zip",
                files={"sessions": ("mixed.zip", _make_zip(entries), "application/zip")},
                data={"group_id": str(_make_group("mixed"))},
                headers=self.auth,
            )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body["imported"]), 2, body)
        with SessionLocal() as db:
            phones = {a.phone for a in db.query(Account).all()}
            self.assertEqual(phones, {"+111111111111", "+222222222222"})


class ValidateSessionPromotesPendingIdTestCase(unittest.TestCase):
    """When validate_session succeeds on an account whose tg_user_id is
    still a `pending:<phone>` placeholder, the worker should overwrite
    it with the real numeric id returned by Telethon. Otherwise the
    placeholder would live forever and downstream features that join on
    tg_user_id (Friend, MessageRecord) wouldn't see the real account."""

    def setUp(self) -> None:
        with SessionLocal() as db:
            for model in (AccountGroupMember, Account, AccountGroup):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()

    def test_pending_placeholder_replaced_with_real_id(self) -> None:
        from unittest.mock import patch
        from backend.app.telegram.adapter import TelegramValidateResult
        from backend.app.workers import account_tasks

        with SessionLocal() as db:
            acc = Account(
                tg_user_id="pending:+12792412211",
                phone="+12792412211",
                session_path="/tmp/fake.session",
                status="imported",
                enabled=True,
            )
            db.add(acc)
            db.commit()
            acc_id = acc.id

        async def fake_validate(account, proxy):
            return TelegramValidateResult(
                ok=True, tg_user_id="5876543210", phone="12792412211",
            )

        # Stub adapter and force it to look configured.
        adapter_stub = type("Stub", (), {
            "configured": True,
            "validate_session": staticmethod(fake_validate),
        })()
        with patch.object(account_tasks, "get_adapter", return_value=adapter_stub):
            result = account_tasks.validate_all_sessions()

        self.assertEqual(result["validated"], 1)
        with SessionLocal() as db:
            updated = db.get(Account, acc_id)
            self.assertEqual(updated.tg_user_id, "5876543210")
            self.assertEqual(updated.status, "active")

    def test_real_id_not_overwritten(self) -> None:
        # If tg_user_id already looks like a real id (no `pending:` prefix),
        # validate_session must not overwrite it even if Telethon returns
        # a different value — operator data wins.
        from unittest.mock import patch
        from backend.app.telegram.adapter import TelegramValidateResult
        from backend.app.workers import account_tasks

        with SessionLocal() as db:
            acc = Account(
                tg_user_id="111111",  # operator-set, real-looking
                phone="+12792412211",
                session_path="/tmp/fake.session",
                status="imported",
                enabled=True,
            )
            db.add(acc)
            db.commit()
            acc_id = acc.id

        async def fake_validate(account, proxy):
            return TelegramValidateResult(
                ok=True, tg_user_id="999999", phone="12792412211",
            )

        adapter_stub = type("Stub", (), {
            "configured": True,
            "validate_session": staticmethod(fake_validate),
        })()
        with patch.object(account_tasks, "get_adapter", return_value=adapter_stub):
            account_tasks.validate_all_sessions()

        with SessionLocal() as db:
            self.assertEqual(db.get(Account, acc_id).tg_user_id, "111111")


if __name__ == "__main__":
    unittest.main()
