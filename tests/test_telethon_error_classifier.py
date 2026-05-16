"""Adapter exception classification.

When `_run_operation` catches an exception, the worker needs a stable
error_code so it can decide retry policy (FloodWait → wait then retry;
auth_invalid → mark account error; password_invalid → permanent).
The classifier maps Telethon exception classes (and a few stdlib ones)
to a fixed code vocabulary.

These tests don't require Telethon to be installed — they exercise the
fallback paths (stdlib errors + generic Exception).
"""
import unittest

import tests.support as support

support.install_sqlite_session()

from backend.app.telegram.adapter import _classify_telethon_error


class ClassifierTestCase(unittest.TestCase):
    def test_connection_error_yields_network_code(self) -> None:
        r = _classify_telethon_error(ConnectionError("connection reset"))
        self.assertFalse(r.ok)
        self.assertEqual(r.error_code, "network")

    def test_timeout_error_yields_network_code(self) -> None:
        r = _classify_telethon_error(TimeoutError("timed out"))
        self.assertEqual(r.error_code, "network")

    def test_oserror_yields_network_code(self) -> None:
        r = _classify_telethon_error(OSError(110, "ETIMEDOUT"))
        self.assertEqual(r.error_code, "network")

    def test_unknown_exception_keeps_class_name(self) -> None:
        class WeirdProblem(Exception):
            pass
        r = _classify_telethon_error(WeirdProblem("???"))
        self.assertEqual(r.error_code, "WeirdProblem")
        self.assertEqual(r.error_message, "???")


if __name__ == "__main__":
    unittest.main()
