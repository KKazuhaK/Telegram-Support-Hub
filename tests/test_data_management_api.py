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


if __name__ == "__main__":
    unittest.main()
