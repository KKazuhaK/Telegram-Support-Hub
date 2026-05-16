"""POST /api/translate — pluggable translator with default Google web
endpoint. Tests mock the HTTP layer so they don't depend on the network.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.core.security import hash_password
from backend.app.main import app
from backend.app.models.agent import SupportAgent


client = TestClient(app)


def _bootstrap_admin():
    client.post("/api/auth/bootstrap-admin",
                json={"username": "root", "password": "admin1234"})
    r = client.post("/api/auth/login",
                    json={"username": "root", "password": "admin1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class TranslateApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        with SessionLocal() as db:
            for row in db.query(SupportAgent).all():
                db.delete(row)
            db.commit()
        self.auth = _bootstrap_admin()

    def test_translate_calls_provider_and_returns_text(self) -> None:
        from backend.app.services import translator
        # Patch the underlying provider call so we don't hit the network.
        with patch.object(translator, "_google_translate",
                          return_value=("你好", "en")) as mock_call:
            r = client.post("/api/translate",
                            json={"text": "Hello"},
                            headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["translated_text"], "你好")
        self.assertEqual(body["source_lang"], "en")
        mock_call.assert_called_once()

    def test_translate_rejects_empty_text(self) -> None:
        r = client.post("/api/translate",
                        json={"text": "   "},
                        headers=self.auth)
        self.assertEqual(r.status_code, 400, r.text)

    def test_translate_provider_failure_returns_502(self) -> None:
        from backend.app.services import translator
        with patch.object(translator, "_google_translate",
                          side_effect=RuntimeError("network down")):
            r = client.post("/api/translate",
                            json={"text": "Hello"},
                            headers=self.auth)
        self.assertEqual(r.status_code, 502, r.text)
        self.assertIn("翻译", r.json()["detail"])

    def test_translate_requires_auth(self) -> None:
        r = client.post("/api/translate", json={"text": "Hello"})
        self.assertEqual(r.status_code, 401, r.text)

    def test_translate_target_lang_passed_through(self) -> None:
        from backend.app.services import translator
        with patch.object(translator, "_google_translate",
                          return_value=("Hello", "zh-CN")) as mock_call:
            client.post("/api/translate",
                        json={"text": "你好", "target": "en"},
                        headers=self.auth)
        # Second positional arg is the target language.
        args, _ = mock_call.call_args
        self.assertEqual(args[1], "en")


class TranslatorParserTestCase(unittest.TestCase):
    """Parse the Google web endpoint's slightly weird nested-array JSON
    response shape without hitting the network."""

    def test_parses_typical_response(self) -> None:
        from backend.app.services.translator import _parse_google_response
        # Real example: [[["你好","Hello",null,null,10]],null,"en",...]
        text, src = _parse_google_response(
            [[["你好", "Hello", None, None, 10]], None, "en"]
        )
        self.assertEqual(text, "你好")
        self.assertEqual(src, "en")

    def test_handles_multi_segment_response(self) -> None:
        from backend.app.services.translator import _parse_google_response
        # Long input is broken into multiple segments by Google.
        text, src = _parse_google_response(
            [
                [["你好", "Hello", None, None, 0],
                 ["，世界", ", world", None, None, 0]],
                None, "en"
            ]
        )
        self.assertEqual(text, "你好，世界")
        self.assertEqual(src, "en")

    def test_returns_empty_on_malformed(self) -> None:
        from backend.app.services.translator import _parse_google_response
        text, src = _parse_google_response(["unexpected"])
        self.assertEqual(text, "")
        self.assertIsNone(src)


if __name__ == "__main__":
    unittest.main()
