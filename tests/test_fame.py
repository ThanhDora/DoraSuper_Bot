import importlib.util
import pathlib
import unittest

_P = pathlib.Path(__file__).resolve().parents[1] / "dorasuper" / "helper" / "fame.py"
_spec = importlib.util.spec_from_file_location("fame_test", _P)
fame = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fame)


class T(unittest.TestCase):
    def test_upvote(self):
        for text in ("👍", " 👍 ", "cảm ơn", "Anh cảm ơn nhiều", "CẢM ƠN", "+", "++", "+1", "thanks", "thank you", "like", "tks"):
            self.assertTrue(fame.is_upvote(text), text)
        for text in ("+84", "hello", "unlike", "👎", "-", ""):
            self.assertFalse(fame.is_upvote(text), text)

    def test_downvote(self):
        for text in ("👎", "unlike", "-", "--", "-1", "không thích", "dislike"):
            self.assertTrue(fame.is_downvote(text), text)
        for text in ("👍", "+", "cảm ơn", "hello"):
            self.assertFalse(fame.is_downvote(text), text)

    def test_old_emoji_gap(self):
        # standalone emoji must count; the previous \\b...\\b pattern missed these
        self.assertTrue(fame.is_upvote("👍"))
        self.assertTrue(fame.is_downvote("👎"))

    def test_mention_html(self):
        self.assertEqual(
            fame.mention_html(123, "A <B>"),
            '<a href="tg://user?id=123">A &lt;B&gt;</a>',
        )


if __name__ == "__main__":
    unittest.main()
