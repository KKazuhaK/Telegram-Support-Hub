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
from backend.app.models.data_groups import Material, MaterialGroup


class MaterialUploadApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tg-material-test-"))
        self._original_upload_dir = config_module.settings.upload_dir
        config_module.settings.upload_dir = self.tmp

        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (Material, MaterialGroup, SupportAgent):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        bootstrap = self.client.post(
            "/api/auth/bootstrap-admin",
            json={"username": "root", "password": "12345678"},
        )
        self.auth = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}

        # Two groups: an image bucket and a voice bucket
        img = self.client.post(
            "/api/material-groups",
            json={"name": "avatars", "kind": "image"},
            headers=self.auth,
        ).json()
        self.image_group_id = img["id"]
        voice = self.client.post(
            "/api/material-groups",
            json={"name": "greetings", "kind": "voice"},
            headers=self.auth,
        ).json()
        self.voice_group_id = voice["id"]

    def tearDown(self) -> None:
        config_module.settings.upload_dir = self._original_upload_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_upload_creates_material_with_file_path(self) -> None:
        body = b"fake-png-bytes"
        resp = self.client.post(
            f"/api/material-groups/{self.image_group_id}/upload",
            files={"file": ("logo.png", io.BytesIO(body), "image/png")},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body_resp = resp.json()
        self.assertIsNotNone(body_resp.get("file_path"))
        self.assertEqual(body_resp["group_id"], self.image_group_id)

        # File is actually on disk
        with SessionLocal() as db:
            m = db.query(Material).first()
            self.assertIsNotNone(m.file_path)
            stored = Path(m.file_path)
            self.assertTrue(stored.exists())
            self.assertEqual(stored.read_bytes(), body)

    def test_upload_sanitises_filename(self) -> None:
        resp = self.client.post(
            f"/api/material-groups/{self.image_group_id}/upload",
            files={"file": ("../../../etc/passwd", io.BytesIO(b"x"), "text/plain")},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        with SessionLocal() as db:
            m = db.query(Material).first()
            stored = Path(m.file_path)
            # Must land under our tmp upload dir
            self.assertIn(self.tmp.resolve(), stored.resolve().parents)
            self.assertNotIn("..", stored.name)

    def test_upload_rejects_for_text_group(self) -> None:
        text_group = self.client.post(
            "/api/material-groups",
            json={"name": "snippets", "kind": "text"},
            headers=self.auth,
        ).json()
        resp = self.client.post(
            f"/api/material-groups/{text_group['id']}/upload",
            files={"file": ("a.png", io.BytesIO(b"x"), "image/png")},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("文本", resp.json()["detail"])

    def test_upload_unknown_group_404(self) -> None:
        resp = self.client.post(
            "/api/material-groups/9999/upload",
            files={"file": ("a.png", io.BytesIO(b"x"), "image/png")},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 404)

    def test_download_returns_bytes(self) -> None:
        body = b"fake-voice-bytes"
        meta = self.client.post(
            f"/api/material-groups/{self.voice_group_id}/upload",
            files={"file": ("hi.ogg", io.BytesIO(body), "audio/ogg")},
            headers=self.auth,
        ).json()
        resp = self.client.get(f"/api/materials/{meta['id']}/download", headers=self.auth)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.content, body)

    def test_download_404_for_text_material(self) -> None:
        text_group = self.client.post(
            "/api/material-groups",
            json={"name": "snippets", "kind": "text"},
            headers=self.auth,
        ).json()
        self.client.post(
            f"/api/material-groups/{text_group['id']}/materials",
            json={"items": ["hello"]},
            headers=self.auth,
        )
        with SessionLocal() as db:
            text_mat = db.query(Material).filter_by(group_id=text_group["id"]).first()
            text_id = text_mat.id
        resp = self.client.get(f"/api/materials/{text_id}/download", headers=self.auth)
        self.assertEqual(resp.status_code, 404)

    def test_delete_material_also_removes_file(self) -> None:
        meta = self.client.post(
            f"/api/material-groups/{self.image_group_id}/upload",
            files={"file": ("a.png", io.BytesIO(b"data"), "image/png")},
            headers=self.auth,
        ).json()
        stored = Path(meta["file_path"])
        self.assertTrue(stored.exists())
        resp = self.client.delete(f"/api/materials/{meta['id']}", headers=self.auth)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(stored.exists())


if __name__ == "__main__":
    unittest.main()
