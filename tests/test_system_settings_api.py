"""Admin-configurable translator settings."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.core.security import hash_password
from backend.app.main import app
from backend.app.models.agent import SupportAgent
from backend.app.models.system_setting import SystemSetting


client = TestClient(app)


def _bootstrap_admin():
    client.post("/api/auth/bootstrap-admin",
                json={"username": "root", "password": "admin1234"})
    r = client.post("/api/auth/login",
                    json={"username": "root", "password": "admin1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class TranslatorSettingsApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        for model in (SystemSetting, SupportAgent):
            for row in self.db.query(model).all():
                self.db.delete(row)
        self.db.commit()
        self.auth = _bootstrap_admin()

    def tearDown(self) -> None:
        self.db.close()

    def test_get_returns_defaults_when_unconfigured(self) -> None:
        r = client.get("/api/system/translator", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["provider"], "google_free")
        self.assertFalse(body["has_api_key"])
        self.assertIn("google_free", body["supported_providers"])
        self.assertIn("openai", body["supported_providers"])
        self.assertIn("deepl", body["supported_providers"])

    def test_patch_persists_provider_and_proxy(self) -> None:
        r = client.patch("/api/system/translator",
                         json={"provider": "google_free",
                               "proxy_url": "http://127.0.0.1:7890"},
                         headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["provider"], "google_free")
        self.assertEqual(body["proxy_url"], "http://127.0.0.1:7890")

    def test_patch_encrypts_api_key_and_masks_in_get(self) -> None:
        client.patch("/api/system/translator",
                     json={"provider": "openai",
                           "api_key": "sk-supersecretkey12345"},
                     headers=self.auth)
        # GET must NOT echo the real key.
        r = client.get("/api/system/translator", headers=self.auth)
        body = r.json()
        self.assertTrue(body["has_api_key"])
        self.assertEqual(body["api_key_masked"], "sk-s***45")
        self.assertNotIn("api_key", body)  # never the plain key

        # And it must be stored encrypted in the DB.
        with SessionLocal() as db:
            row = db.get(SystemSetting, "translator")
            self.assertIsNotNone(row.encrypted_value)
            self.assertNotIn("supersecret", row.encrypted_value or "")

    def test_patch_clears_api_key_with_empty_string(self) -> None:
        client.patch("/api/system/translator",
                     json={"api_key": "sk-original"}, headers=self.auth)
        client.patch("/api/system/translator",
                     json={"api_key": ""}, headers=self.auth)
        with SessionLocal() as db:
            row = db.get(SystemSetting, "translator")
            self.assertIsNone(row.encrypted_value)

    def test_rejects_unknown_provider(self) -> None:
        r = client.patch("/api/system/translator",
                         json={"provider": "babylonfish"},
                         headers=self.auth)
        self.assertEqual(r.status_code, 400, r.text)

    def test_endpoint_requires_admin(self) -> None:
        agent = SupportAgent(
            username="staff", nickname="s",
            password_hash=hash_password("staffpwd1"),
            role="agent", status="enabled",
        )
        self.db.add(agent)
        self.db.commit()
        tok = client.post("/api/auth/login",
                          json={"username": "staff", "password": "staffpwd1"}).json()["access_token"]
        r = client.get("/api/system/translator",
                       headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r.status_code, 403, r.text)
        r = client.patch("/api/system/translator", json={"provider": "openai"},
                         headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r.status_code, 403, r.text)


class TelegramHealthApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        for row in self.db.query(SupportAgent).all():
            self.db.delete(row)
        self.db.commit()
        self.auth = _bootstrap_admin()

    def tearDown(self) -> None:
        self.db.close()

    def test_returns_unconfigured_when_env_missing(self) -> None:
        from backend.app.services import telegram_health
        from backend.app.core.config import settings as cfg
        old_id, old_hash = cfg.telegram_api_id, cfg.telegram_api_hash
        cfg.telegram_api_id = ""
        cfg.telegram_api_hash = ""
        try:
            r = client.get("/api/system/telegram-health", headers=self.auth)
        finally:
            cfg.telegram_api_id, cfg.telegram_api_hash = old_id, old_hash
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertFalse(body["configured"])
        self.assertFalse(body["reachable"])
        self.assertIn("未在 .env", body["error"])

    def test_returns_reachable_true_when_probe_succeeds(self) -> None:
        from backend.app.services import telegram_health
        from backend.app.core.config import settings as cfg

        cfg.telegram_api_id = "12345"
        cfg.telegram_api_hash = "abc123"
        # Replace _probe_dc with an async function directly (patch.object
        # with side_effect= an async fn ends up wrapping it in a MagicMock
        # whose call result isn't the awaited coroutine).
        original = telegram_health._probe_dc

        async def fake_probe(api_id, api_hash):
            return True
        telegram_health._probe_dc = fake_probe
        telegram_health._have_telethon = lambda: True
        try:
            r = client.get("/api/system/telegram-health", headers=self.auth)
        finally:
            telegram_health._probe_dc = original
            cfg.telegram_api_id = ""
            cfg.telegram_api_hash = ""
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["configured"])
        self.assertTrue(body["reachable"])
        self.assertIsNone(body["error"])

    def test_returns_error_when_probe_raises(self) -> None:
        from backend.app.services import telegram_health
        from backend.app.core.config import settings as cfg

        cfg.telegram_api_id = "12345"
        cfg.telegram_api_hash = "abc123"
        original = telegram_health._probe_dc

        async def boom(api_id, api_hash):
            raise ConnectionError("network unreachable")
        telegram_health._probe_dc = boom
        telegram_health._have_telethon = lambda: True
        try:
            r = client.get("/api/system/telegram-health", headers=self.auth)
        finally:
            telegram_health._probe_dc = original
            cfg.telegram_api_id = ""
            cfg.telegram_api_hash = ""
        body = r.json()
        self.assertTrue(body["configured"])
        self.assertFalse(body["reachable"])
        self.assertIn("network unreachable", body["error"])

    def test_endpoint_requires_admin(self) -> None:
        agent = SupportAgent(
            username="staffH", nickname="s",
            password_hash=hash_password("staffpwd1"),
            role="agent", status="enabled",
        )
        self.db.add(agent)
        self.db.commit()
        tok = client.post("/api/auth/login",
                          json={"username": "staffH", "password": "staffpwd1"}).json()["access_token"]
        r = client.get("/api/system/telegram-health",
                       headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r.status_code, 403, r.text)


class TranslatorDispatcherTestCase(unittest.TestCase):
    """The high-level `translate()` reads provider from system_settings
    and dispatches to the matching backend."""

    def setUp(self) -> None:
        self.db = SessionLocal()
        for row in self.db.query(SystemSetting).all():
            self.db.delete(row)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_default_dispatches_to_google(self) -> None:
        from backend.app.services import translator
        with patch.object(translator, "_google_translate",
                          return_value=("你好", "en")) as mock_g:
            text, src = translator.translate("Hello")
        mock_g.assert_called_once()
        self.assertEqual(text, "你好")

    def test_settings_switch_to_openai(self) -> None:
        from backend.app.core.crypto import encrypt_secret
        self.db.add(SystemSetting(
            key="translator",
            value={"provider": "openai", "model": "gpt-4o-mini"},
            encrypted_value=encrypt_secret("sk-test"),
        ))
        self.db.commit()
        from backend.app.services import translator
        with patch.object(translator, "_openai_translate",
                          return_value=("Hi", None)) as mock_o, \
             patch.object(translator, "_google_translate") as mock_g:
            translator.translate("你好", target="en")
        mock_o.assert_called_once()
        mock_g.assert_not_called()


if __name__ == "__main__":
    unittest.main()
