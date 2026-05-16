import io
import unittest
import zipfile

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission
from backend.app.models.proxy import AccountProxyLog


def _make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


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
            headers=self.auth,
        ).json()

    def test_flat_layout_imported(self) -> None:
        body = self._upload({
            "12792412211.session": b"fake-session-bytes",
        })
        self.assertEqual(len(body["imported"]), 1, body)
        self.assertEqual(body["imported"][0]["user_id"], "12792412211")
        with SessionLocal() as db:
            acc = db.query(Account).filter(Account.tg_user_id == "12792412211").one()
            self.assertTrue(acc.session_path.endswith("12792412211.session"))

    def test_flat_layout_with_json_sidecar_populates_phone(self) -> None:
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
            acc = db.query(Account).filter(Account.tg_user_id == "12792412211").one()
            self.assertEqual(acc.phone, "+12792412211")

    def test_subfolder_layout_still_works(self) -> None:
        body = self._upload({
            "1001/acc.session": b"fake-session-bytes",
        })
        self.assertEqual(len(body["imported"]), 1, body)
        self.assertEqual(body["imported"][0]["user_id"], "1001")

    def test_malformed_json_sidecar_is_ignored(self) -> None:
        # A broken JSON sidecar should not block the session itself
        # from importing — silently skip the metadata.
        body = self._upload({
            "12792412211.session": b"fake-session-bytes",
            "12792412211.json": b"{this is not valid json",
        })
        self.assertEqual(len(body["imported"]), 1, body)
        with SessionLocal() as db:
            acc = db.query(Account).filter(Account.tg_user_id == "12792412211").one()
            self.assertIsNone(acc.phone)

    def test_orphan_json_without_session_is_skipped(self) -> None:
        # JSON sidecar with no matching .session should not create an account.
        body = self._upload({"12792412211.json": b'{"phone": "12792412211"}'})
        self.assertEqual(body["imported"], [])


if __name__ == "__main__":
    unittest.main()
