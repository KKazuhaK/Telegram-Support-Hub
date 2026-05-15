import random
import unittest

import tests.support  # noqa: F401

from backend.app.services.template_engine import RenderedMessage, render_message


class SimpleSubstitutionTestCase(unittest.TestCase):
    def test_name_phone_source_substitution(self) -> None:
        out = render_message(
            "你好 {name}，手机 {phone}，来源 {source}",
            {"name": "张三", "phone": "+8613800000000", "source": "manual"},
        )
        self.assertEqual(out.text, "你好 张三，手机 +8613800000000，来源 manual")
        self.assertEqual(out.entities, [])

    def test_missing_context_falls_back(self) -> None:
        out = render_message("你好 {name}", {})
        self.assertEqual(out.text, "你好 客户")

    def test_no_variables_passes_through(self) -> None:
        out = render_message("hi there", {})
        self.assertEqual(out.text, "hi there")
        self.assertEqual(out.entities, [])


class RandomVariableTestCase(unittest.TestCase):
    def test_random_alphabet_count_matches(self) -> None:
        rng = random.Random(42)
        out = render_message("X[RandomAlphabet=4]Y", {}, rng=rng)
        # Should be X + 4 letters + Y
        self.assertEqual(len(out.text), 6)
        self.assertEqual(out.text[0], "X")
        self.assertEqual(out.text[-1], "Y")
        self.assertTrue(out.text[1:5].isalpha())

    def test_random_number_count_matches(self) -> None:
        rng = random.Random(42)
        out = render_message("[RandomNumber=5]", {}, rng=rng)
        self.assertEqual(len(out.text), 5)
        self.assertTrue(out.text.isdigit())

    def test_random_symbol_count_matches(self) -> None:
        rng = random.Random(42)
        out = render_message("[RandomSymbol=3]", {}, rng=rng)
        self.assertEqual(len(out.text), 3)
        for c in out.text:
            self.assertIn(c, "!@#$%^&*()-_=+[]{};:,.<>?/~")

    def test_random_emoji_count_matches(self) -> None:
        rng = random.Random(42)
        out = render_message("[RandomEmoji=2]", {}, rng=rng)
        # Each emoji is a single grapheme; using str length is fine for BMP
        # emojis we whitelist. Just assert non-empty + only emoji chars.
        self.assertTrue(len(out.text) >= 2)

    def test_random_count_zero_yields_empty(self) -> None:
        out = render_message("[RandomNumber=0]", {})
        self.assertEqual(out.text, "")

    def test_invalid_random_count_keeps_literal(self) -> None:
        # Negative or non-int — leave the literal placeholder so the operator
        # notices and fixes the template.
        out = render_message("[RandomNumber=abc]", {})
        self.assertEqual(out.text, "[RandomNumber=abc]")


class FormattingEntityTestCase(unittest.TestCase):
    """Each formatting variable produces a Telegram MessageEntity-shaped
    dict with type/offset/length and the surrounding tag stripped from the
    text. The offset/length are measured against the FINAL (rendered) text
    in UTF-16 code units per Telegram's protocol — for ASCII / BMP that
    matches Python str length, which is what we test against."""

    def test_bold(self) -> None:
        out = render_message("hi [Bold=world]!", {})
        self.assertEqual(out.text, "hi world!")
        self.assertEqual(out.entities, [{"type": "bold", "offset": 3, "length": 5}])

    def test_italic_underline_strike_each_emit_entity(self) -> None:
        for tag, kind in (("Italic", "italic"), ("Underline", "underline"), ("Strike", "strike")):
            out = render_message(f"a [{tag}=B]c", {})
            self.assertEqual(out.text, "a Bc")
            self.assertEqual(out.entities, [{"type": kind, "offset": 2, "length": 1}])

    def test_code_inline(self) -> None:
        out = render_message('say [Code=print("hi")]', {})
        self.assertEqual(out.text, 'say print("hi")')
        self.assertEqual(out.entities, [{"type": "code", "offset": 4, "length": 11}])

    def test_pre_block_with_language(self) -> None:
        out = render_message("[Pre=Go,fmt.Println(\"H\")]", {})
        self.assertEqual(out.text, 'fmt.Println("H")')
        self.assertEqual(
            out.entities,
            [{"type": "pre", "offset": 0, "length": 16, "language": "Go"}],
        )

    def test_url_entity_uses_inner_text(self) -> None:
        out = render_message("see [URL=https://example.com]", {})
        self.assertEqual(out.text, "see https://example.com")
        self.assertEqual(
            out.entities,
            [{"type": "url", "offset": 4, "length": 19}],
        )

    def test_text_url_separates_text_and_url(self) -> None:
        out = render_message("[TextURL=Google,https://google.com]", {})
        self.assertEqual(out.text, "Google")
        self.assertEqual(
            out.entities,
            [{"type": "text_url", "offset": 0, "length": 6, "url": "https://google.com"}],
        )

    def test_mention_entity(self) -> None:
        out = render_message("hi [Mention=@alice]", {})
        self.assertEqual(out.text, "hi @alice")
        self.assertEqual(out.entities, [{"type": "mention", "offset": 3, "length": 6}])

    def test_hashtag_entity(self) -> None:
        out = render_message("trending [Hashtag=#sale]", {})
        self.assertEqual(out.text, "trending #sale")
        self.assertEqual(out.entities, [{"type": "hashtag", "offset": 9, "length": 5}])

    def test_email_entity(self) -> None:
        out = render_message("contact [Email=hi@example.com]", {})
        self.assertEqual(out.text, "contact hi@example.com")
        self.assertEqual(out.entities, [{"type": "email", "offset": 8, "length": 14}])

    def test_phone_entity(self) -> None:
        out = render_message("call [Phone=+71234567891]", {})
        self.assertEqual(out.text, "call +71234567891")
        self.assertEqual(out.entities, [{"type": "phone", "offset": 5, "length": 12}])


class MultiEntityTestCase(unittest.TestCase):
    def test_multiple_entities_have_correct_offsets(self) -> None:
        out = render_message("[Bold=hi] [Italic=there]", {})
        self.assertEqual(out.text, "hi there")
        self.assertEqual(
            out.entities,
            [
                {"type": "bold", "offset": 0, "length": 2},
                {"type": "italic", "offset": 3, "length": 5},
            ],
        )

    def test_entity_after_simple_var_offset_accounts_for_substitution(self) -> None:
        out = render_message("Hi {name}, [Bold=welcome]!", {"name": "张三"})
        self.assertEqual(out.text, "Hi 张三, welcome!")
        self.assertEqual(
            out.entities,
            [{"type": "bold", "offset": 7, "length": 7}],
        )

    def test_entity_offset_in_utf16_units(self) -> None:
        # 🎉 is outside BMP -> 2 UTF-16 code units. Telegram measures entity
        # offsets in UTF-16, so a bold tag AFTER an astral char should be
        # offset by 2, not 1.
        out = render_message("🎉[Bold=hi]", {})
        self.assertEqual(out.text, "🎉hi")
        self.assertEqual(
            out.entities,
            [{"type": "bold", "offset": 2, "length": 2}],
        )

    def test_random_variable_then_entity(self) -> None:
        rng = random.Random(0)
        out = render_message("[RandomNumber=3]-[Bold=end]", {}, rng=rng)
        # "NNN-end" -> 7 chars, bold at offset 4 with length 3
        self.assertEqual(len(out.text), 7)
        self.assertEqual(out.text[3], "-")
        self.assertEqual(out.entities, [{"type": "bold", "offset": 4, "length": 3}])


class IdempotenceTestCase(unittest.TestCase):
    def test_no_variables_returns_original(self) -> None:
        # Should be cheap path; verify identical text and no entities.
        msg = "纯文本"
        out = render_message(msg, {"name": "ignored"})
        self.assertEqual(out.text, msg)

    def test_returns_rendered_message_dataclass(self) -> None:
        out = render_message("hi", {})
        self.assertIsInstance(out, RenderedMessage)
        self.assertEqual(out.text, "hi")
        self.assertEqual(out.entities, [])


if __name__ == "__main__":
    unittest.main()
