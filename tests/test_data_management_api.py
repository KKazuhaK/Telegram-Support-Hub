import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.agent import SupportAgent
from backend.app.models.data_groups import (
    Material,
    MaterialGroup,
    Phone,
    PhoneGroup,
    ProxyGroup,
)
from backend.app.models.proxy import ProxyEndpoint


def _bootstrap_admin(client):
    return client.post(
        "/api/auth/bootstrap-admin",
        json={"username": "root", "password": "12345678"},
    )


class PhoneGroupsApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (Phone, PhoneGroup, SupportAgent):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        self.auth = {"Authorization": f"Bearer {_bootstrap_admin(self.client).json()['access_token']}"}

    def test_create_and_list_groups(self) -> None:
        resp = self.client.post(
            "/api/phone-groups",
            json={"name": "CN-leads", "country": "CN", "remark": "from event"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["name"], "CN-leads")
        self.assertEqual(body["country"], "CN")

        listing = self.client.get("/api/phone-groups", headers=self.auth).json()
        self.assertEqual(len(listing), 1)

    def test_duplicate_group_name_rejected(self) -> None:
        self.client.post(
            "/api/phone-groups",
            json={"name": "g1", "country": "CN"},
            headers=self.auth,
        )
        dup = self.client.post(
            "/api/phone-groups",
            json={"name": "g1", "country": "CN"},
            headers=self.auth,
        )
        self.assertEqual(dup.status_code, 409)

    def test_add_phones_to_group_and_filter(self) -> None:
        g = self.client.post(
            "/api/phone-groups",
            json={"name": "g", "country": "CN"},
            headers=self.auth,
        ).json()
        resp = self.client.post(
            f"/api/phone-groups/{g['id']}/phones",
            json={"numbers": ["+8613800000001", "+8613800000002", "invalid"]},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["created"], 2)
        self.assertEqual(body["rejected"], ["invalid"])

        rows = self.client.get(f"/api/phones?group_id={g['id']}", headers=self.auth).json()
        self.assertEqual(len(rows), 2)

    def test_group_counts_aggregate(self) -> None:
        g = self.client.post("/api/phone-groups",
                             json={"name": "g", "country": "US"},
                             headers=self.auth).json()
        self.client.post(
            f"/api/phone-groups/{g['id']}/phones",
            json={"numbers": ["+11111111111", "+12222222222"]},
            headers=self.auth,
        )
        listing = self.client.get("/api/phone-groups", headers=self.auth).json()
        self.assertEqual(listing[0]["count"], 2)
        self.assertEqual(listing[0]["remaining"], 2)

    def test_delete_group_cascades_phones(self) -> None:
        g = self.client.post("/api/phone-groups",
                             json={"name": "g", "country": "CN"},
                             headers=self.auth).json()
        self.client.post(
            f"/api/phone-groups/{g['id']}/phones",
            json={"numbers": ["+8613800000001"]},
            headers=self.auth,
        )
        resp = self.client.delete(f"/api/phone-groups/{g['id']}", headers=self.auth)
        self.assertEqual(resp.status_code, 200, resp.text)
        with SessionLocal() as db:
            self.assertEqual(db.query(PhoneGroup).count(), 0)
            self.assertEqual(db.query(Phone).count(), 0)


class MaterialGroupsApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (Material, MaterialGroup, SupportAgent):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        self.auth = {"Authorization": f"Bearer {_bootstrap_admin(self.client).json()['access_token']}"}

    def test_create_group_and_add_text(self) -> None:
        g = self.client.post(
            "/api/material-groups",
            json={"name": "greetings", "kind": "text"},
            headers=self.auth,
        ).json()
        self.assertEqual(g["kind"], "text")

        added = self.client.post(
            f"/api/material-groups/{g['id']}/materials",
            json={"items": ["你好 {name}", "Hi {name}"]},
            headers=self.auth,
        )
        self.assertEqual(added.status_code, 200)
        self.assertEqual(added.json()["created"], 2)

        rows = self.client.get(f"/api/materials?group_id={g['id']}", headers=self.auth).json()
        self.assertEqual(len(rows), 2)

    def test_kind_must_be_in_allowlist(self) -> None:
        resp = self.client.post(
            "/api/material-groups",
            json={"name": "weird", "kind": "spam"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 400)


class ProxyGroupsApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (ProxyEndpoint, ProxyGroup, SupportAgent):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        self.auth = {"Authorization": f"Bearer {_bootstrap_admin(self.client).json()['access_token']}"}

    def test_group_lists_count_of_proxies(self) -> None:
        g = self.client.post(
            "/api/proxy-groups",
            json={"name": "main", "remark": ""},
            headers=self.auth,
        ).json()
        # create two proxies under this group
        for i in range(2):
            r = self.client.post(
                "/api/proxies",
                json={
                    "name": f"p{i}", "protocol": "socks5",
                    "host": "1.1.1.1", "port": 1080 + i,
                    "group_id": g["id"],
                },
                headers=self.auth,
            )
            self.assertEqual(r.status_code, 200, r.text)

        listing = self.client.get("/api/proxy-groups", headers=self.auth).json()
        self.assertEqual(listing[0]["count"], 2)


    def test_import_text_parses_host_port_user_pass(self) -> None:
        text = (
            "207.228.46.141:1337:user1:pw1\n"
            "107.180.175.124:1337:user1:pw1\n"
            "\n"  # blank line skipped
            "10.0.0.1:8080\n"  # 2-field form
            "garbage\n"  # malformed
            "207.228.46.141:1337:user1:pw1\n"  # dup within batch
        )
        r = self.client.post(
            "/api/proxies/import-text",
            json={"text": text, "protocol": "socks5"},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body["created"]), 3)
        self.assertEqual(body["duplicated_count"], 1)
        self.assertEqual(len(body["skipped"]), 1)
        self.assertIn("格式错误", body["skipped"][0]["reason"])
        # Hosts saved correctly + 2-field row has null user/no creds.
        with SessionLocal() as db:
            rows = {p.host: p for p in db.query(ProxyEndpoint).all()}
            self.assertEqual(rows["10.0.0.1"].port, 8080)
            self.assertIsNone(rows["10.0.0.1"].username)
            self.assertEqual(rows["207.228.46.141"].username, "user1")

    def test_batch_update_status_and_group(self) -> None:
        g = self.client.post("/api/proxy-groups",
                             json={"name": "g1", "remark": ""},
                             headers=self.auth).json()
        ids = []
        for i in range(3):
            r = self.client.post("/api/proxies", json={
                "name": f"p{i}", "protocol": "socks5",
                "host": "9.9.9.9", "port": 1100 + i,
            }, headers=self.auth)
            ids.append(r.json()["id"])

        # Move them all into g1 + set status=disabled in one shot.
        r = self.client.post("/api/proxies/batch", json={
            "ids": ids, "status": "disabled", "group_id": g["id"],
        }, headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["updated"], 3)

        listing = self.client.get(f"/api/proxies?group_id={g['id']}", headers=self.auth).json()
        self.assertEqual(len(listing), 3)
        for p in listing:
            self.assertEqual(p["status"], "disabled")

    def test_batch_delete_handles_account_proxy_log_fk(self) -> None:
        # AccountProxyLog rows referencing a deleted proxy used to 500
        # the batch delete (FK constraint, no cascade). Verify the
        # log's FK gets nulled and the proxy actually goes away.
        from backend.app.models.account import Account
        from backend.app.models.proxy import AccountProxyLog
        p = self.client.post("/api/proxies", json={
            "name": "p", "protocol": "socks5", "host": "8.8.8.8", "port": 1080,
        }, headers=self.auth).json()
        with SessionLocal() as db:
            acc = Account(tg_user_id="logacc", session_path="/tmp/logacc.session",
                          status="active", enabled=True)
            db.add(acc); db.flush()
            db.add(AccountProxyLog(
                account_id=acc.id, old_proxy_id=None,
                new_proxy_id=p["id"], action="bind", reason="initial",
            ))
            db.add(AccountProxyLog(
                account_id=acc.id, old_proxy_id=p["id"],
                new_proxy_id=None, action="unbind", reason="cleanup",
            ))
            db.commit()

        r = self.client.post("/api/proxies/batch/delete",
                             json={"ids": [p["id"]]},
                             headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["deleted"], 1)
        with SessionLocal() as db:
            self.assertIsNone(db.get(ProxyEndpoint, p["id"]))
            # Log rows survive but their proxy refs are NULL.
            logs = db.query(AccountProxyLog).all()
            self.assertEqual(len(logs), 2)
            for log in logs:
                self.assertIsNone(log.old_proxy_id)
                self.assertIsNone(log.new_proxy_id)

    def test_batch_delete_skips_proxies_bound_to_accounts(self) -> None:
        # A proxy with an Account.proxy_id pointing at it can't be
        # hard-deleted without orphaning the FK. Endpoint should return
        # which ids were protected so the UI can surface it.
        from backend.app.models.account import Account
        p1 = self.client.post("/api/proxies", json={
            "name": "p1", "protocol": "socks5", "host": "1.1.1.1", "port": 9001,
        }, headers=self.auth).json()
        p2 = self.client.post("/api/proxies", json={
            "name": "p2", "protocol": "socks5", "host": "1.1.1.1", "port": 9002,
        }, headers=self.auth).json()
        with SessionLocal() as db:
            acc = Account(tg_user_id="X", session_path="/tmp/x.session",
                          status="active", enabled=True, proxy_id=p1["id"])
            db.add(acc); db.commit()

        r = self.client.post("/api/proxies/batch/delete",
                             json={"ids": [p1["id"], p2["id"]]},
                             headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["deleted"], 1)
        self.assertEqual(body["protected_in_use"], [p1["id"]])
        with SessionLocal() as db:
            self.assertIsNotNone(db.get(ProxyEndpoint, p1["id"]))
            self.assertIsNone(db.get(ProxyEndpoint, p2["id"]))

    def test_import_text_skips_existing_host_port_user(self) -> None:
        # Re-importing the same list should be a no-op (idempotent).
        text = "1.2.3.4:1080:u:p"
        for _ in range(2):
            r = self.client.post(
                "/api/proxies/import-text",
                json={"text": text},
                headers=self.auth,
            )
            self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["created"]), 0)
        self.assertEqual(body["duplicated_count"], 1)
        with SessionLocal() as db:
            self.assertEqual(db.query(ProxyEndpoint).count(), 1)


if __name__ == "__main__":
    unittest.main()
