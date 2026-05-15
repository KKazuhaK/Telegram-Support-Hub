import io
import shutil
import tempfile
import unittest
from pathlib import Path

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.core import config as config_module
from backend.app.main import app
from backend.app.models.agent import SupportAgent


class FilesApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # Redirect upload dir to a temp folder so the test doesn't touch real
        # data; restore on tearDown.
        self.tmp = Path(tempfile.mkdtemp(prefix="tg-files-test-"))
        self._original_upload_dir = config_module.settings.upload_dir
        config_module.settings.upload_dir = self.tmp

        self.client = TestClient(app)
        with SessionLocal() as db:
            for row in db.query(SupportAgent).all():
                db.delete(row)
            db.commit()
        bootstrap = self.client.post(
            "/api/auth/bootstrap-admin",
            json={"username": "root", "password": "12345678"},
        )
        self.auth = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}

    def tearDown(self) -> None:
        config_module.settings.upload_dir = self._original_upload_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_upload_then_list_then_delete(self) -> None:
        # Upload
        body = b"hello world"
        resp = self.client.post(
            "/api/files",
            files={"file": ("hello.txt", io.BytesIO(body), "text/plain")},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        meta = resp.json()
        self.assertEqual(meta["name"], "hello.txt")
        self.assertEqual(meta["size"], len(body))

        # List
        listing = self.client.get("/api/files", headers=self.auth).json()
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["name"], "hello.txt")

        # File actually exists on disk in the redirected dir
        self.assertTrue((self.tmp / "hello.txt").exists())

        # Delete
        resp = self.client.delete("/api/files/hello.txt", headers=self.auth)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse((self.tmp / "hello.txt").exists())
        self.assertEqual(self.client.get("/api/files", headers=self.auth).json(), [])

    def test_upload_sanitises_filename(self) -> None:
        resp = self.client.post(
            "/api/files",
            files={"file": ("../../etc/passwd", io.BytesIO(b"x"), "text/plain")},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        name = resp.json()["name"]
        self.assertNotIn("/", name)
        self.assertNotIn("..", name)
        # File must land inside the upload dir
        stored = self.tmp / name
        self.assertTrue(stored.exists())

    def test_delete_rejects_path_traversal(self) -> None:
        # The router may either normalise the traversal (-> 404) or reach our
        # handler which rejects with 400; either way the file must not be
        # touched and the upload dir must stay intact.
        resp = self.client.delete("/api/files/..%2F..%2Fetc%2Fpasswd", headers=self.auth)
        self.assertIn(resp.status_code, (400, 404))

    def test_delete_missing_file_returns_404(self) -> None:
        resp = self.client.delete("/api/files/does-not-exist.bin", headers=self.auth)
        self.assertEqual(resp.status_code, 404)

    def test_endpoints_require_admin(self) -> None:
        with SessionLocal() as db:
            from backend.app.core.security import hash_password
            db.add(SupportAgent(
                username="staff", role="agent", status="enabled",
                password_hash=hash_password("12345678"),
            ))
            db.commit()
        login = self.client.post("/api/auth/login",
                                 json={"username": "staff", "password": "12345678"})
        staff = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = self.client.get("/api/files", headers=staff)
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
