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


if __name__ == "__main__":
    unittest.main()
