import unittest

from backend.app.core.crypto import decrypt_secret, encrypt_secret


class CryptoTestCase(unittest.TestCase):
    def test_secret_round_trip(self) -> None:
        encrypted = encrypt_secret("secret-value")

        self.assertIsNotNone(encrypted)
        self.assertNotEqual(encrypted, "secret-value")
        self.assertEqual(decrypt_secret(encrypted), "secret-value")

    def test_empty_secret_returns_none(self) -> None:
        self.assertIsNone(encrypt_secret(None))
        self.assertIsNone(encrypt_secret(""))
        self.assertIsNone(decrypt_secret(None))
        self.assertIsNone(decrypt_secret(""))


if __name__ == "__main__":
    unittest.main()
