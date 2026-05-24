"""resolve_target() exception wrapping.

When ImportContactsRequest fails inside resolve_target, the adapter
must keep the Chinese-friendly user message AND make the underlying
Telethon exception class observable to the worker, so account-level
kill-switches (PeerFloodError, FloodError, ...) can fire instead of
seeing a generic "ValueError".

Background: prior to this change, every failure was wrapped as a plain
ValueError and the inner class only appeared in the message string.
The worker matched error_code="ValueError" → fail_fast for the message
but never disabled the underlying account, so the next campaign would
pick the same flood-blocked account and waste another import.
"""
import asyncio
import unittest

import tests.support as support

support.install_sqlite_session()

from backend.app.telegram.adapter import (
    ResolveTargetError,
    TelegramAdapter,
)

# resolve_target imports telethon.tl.functions.contacts inside the
# phone-fallback branch, so the runtime path can't be exercised without
# Telethon installed. The kill-switch behavior we care about is exercised
# end-to-end in test_send_worker.test_flood_error_from_import_path_kills_account
# regardless of the import path; this file pins the contract of the
# ResolveTargetError class (inner_code carries Telethon class name, is-a
# ValueError) which only requires telethon when the live path runs.
try:
    import telethon  # noqa: F401
    _HAS_TELETHON = True
except ImportError:
    _HAS_TELETHON = False


class _FakeImportError(Exception):
    """Stand-in for telethon.errors.PeerFloodError / FloodError /
    FloodWaitError — the class name is what the worker matches on."""


def _rename(cls_name: str):
    """Return an instance of a fake exception whose __class__.__name__ is
    `cls_name`, so the adapter sees the same class name Telethon would
    raise. Keeps the test independent of Telethon being installed."""
    new_cls = type(cls_name, (Exception,), {})
    return new_cls("server says no")


class _StubClient:
    """Minimal async client double. get_entity always raises (forces the
    phone-import fallback); the __call__ side handles ImportContactsRequest.
    """

    def __init__(self, import_exc: Exception | None):
        self._import_exc = import_exc

    async def get_entity(self, target):
        raise ValueError(f"Cannot find any entity corresponding to '{target}'")

    async def __call__(self, request):
        if self._import_exc is not None:
            raise self._import_exc
        # Empty users path — handled separately by adapter, not exercised here.
        class _R:
            users = []
        return _R()


@unittest.skipUnless(
    _HAS_TELETHON,
    "telethon not installed locally; live resolve_target path skipped (same "
    "convention as test_telethon_error_classifier — kill-switch behavior is "
    "verified end-to-end in test_send_worker without telethon)",
)
class ResolveTargetErrorTestCase(unittest.TestCase):
    def test_carries_inner_code_for_peer_flood(self) -> None:
        adapter = TelegramAdapter()
        client = _StubClient(import_exc=_rename("PeerFloodError"))
        with self.assertRaises(ResolveTargetError) as ctx:
            asyncio.run(adapter.resolve_target(client, "+18187654321"))
        # The Chinese message must still be present for operators.
        self.assertIn("无法解析", str(ctx.exception))
        self.assertIn("PeerFloodError", str(ctx.exception))
        # And the class name must be observable as an attribute so the
        # worker can match ACCOUNT_KILL_CODES without parsing the string.
        self.assertEqual(ctx.exception.inner_code, "PeerFloodError")

    def test_carries_inner_code_for_generic_flood(self) -> None:
        # The case the operator hit in the field: tooltip showed
        # "(FloodError)". This is the Telethon base class, raised when
        # the RPC error code doesn't match a more specific subclass.
        adapter = TelegramAdapter()
        client = _StubClient(import_exc=_rename("FloodError"))
        with self.assertRaises(ResolveTargetError) as ctx:
            asyncio.run(adapter.resolve_target(client, "+18187654321"))
        self.assertEqual(ctx.exception.inner_code, "FloodError")

    def test_is_a_valueerror_for_backward_compat(self) -> None:
        # Existing catch-sites (worker fail-fast list, callers that
        # expect ValueError for "target not on TG") must keep working.
        adapter = TelegramAdapter()
        client = _StubClient(import_exc=_rename("FloodError"))
        with self.assertRaises(ValueError):
            asyncio.run(adapter.resolve_target(client, "+18187654321"))

    def test_chains_original_exception(self) -> None:
        # __cause__ should point at the original Telethon exception so
        # full stack traces survive in logs.
        adapter = TelegramAdapter()
        original = _rename("PeerFloodError")
        client = _StubClient(import_exc=original)
        try:
            asyncio.run(adapter.resolve_target(client, "+18187654321"))
            self.fail("expected ResolveTargetError")
        except ResolveTargetError as exc:
            self.assertIs(exc.__cause__, original)


if __name__ == "__main__":
    unittest.main()
