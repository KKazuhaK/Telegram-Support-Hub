import unittest

import tests.support  # noqa: F401  configures env

from backend.app.core.security import decode_token, hash_password, issue_token, verify_password


class SecurityTestCase(unittest.TestCase):
    def test_password_hash_round_trip(self) -> None:
        hashed = hash_password("super-secret-1234")
        self.assertNotEqual(hashed, "super-secret-1234")
        self.assertTrue(verify_password("super-secret-1234", hashed))
        self.assertFalse(verify_password("wrong-password", hashed))
        self.assertFalse(verify_password("super-secret-1234", None))

    def test_jwt_round_trip(self) -> None:
        token = issue_token(subject="alice", role="admin", agent_id=1)
        payload = decode_token(token)
        self.assertEqual(payload["sub"], "alice")
        self.assertEqual(payload["role"], "admin")
        self.assertEqual(payload["agent_id"], 1)

    def test_jwt_rejects_tampered_token(self) -> None:
        token = issue_token(subject="alice", role="admin", agent_id=1)
        tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
        with self.assertRaises(Exception):
            decode_token(tampered)


if __name__ == "__main__":
    unittest.main()
