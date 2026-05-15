import unittest

from backend.app.services.parsers import normalize_phone, parse_customer_text


class CustomerParserTestCase(unittest.TestCase):
    def test_normalize_phone_adds_plus_and_removes_spaces(self) -> None:
        self.assertEqual(normalize_phone(" 86 138-0000-0000 "), "+8613800000000")

    def test_normalize_phone_rejects_invalid_value(self) -> None:
        self.assertEqual(normalize_phone("abc"), "")

    def test_parse_customer_text_with_header(self) -> None:
        imported, rejected = parse_customer_text(
            "phone,name,tags,consent\n+8613800000000,张三,VIP|售后,yes\nbad,李四,,yes",
            source="manual",
            assume_consent=False,
        )

        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0]["phone"], "+8613800000000")
        self.assertEqual(imported[0]["name"], "张三")
        self.assertEqual(imported[0]["tags"], ["VIP", "售后"])
        self.assertTrue(imported[0]["consent"])
        self.assertEqual(len(rejected), 1)

    def test_parse_customer_text_uses_assumed_consent_without_header(self) -> None:
        imported, rejected = parse_customer_text("+8613800000000,张三", source=None, assume_consent=True)

        self.assertEqual(len(imported), 1)
        self.assertEqual(rejected, [])
        self.assertTrue(imported[0]["consent"])
        self.assertEqual(imported[0]["source"], "manual")


if __name__ == "__main__":
    unittest.main()
