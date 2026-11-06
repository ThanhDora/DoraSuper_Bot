"""Offline tests for AI emoji post-processing."""
import os
import unittest
os.environ['DORASUPER_OFFLINE'] = '1'
import ast
import re
import types
import unicodedata
from pathlib import Path
from dorasuper import emoji as _emoji_mod

# Plugin ai.py cần app/Mongo khi import — chỉ nạp phần xử lý emoji (từ _skip tới trước SYSTEM_PROMPT)
_src = (Path(__file__).resolve().parents[1] / "dorasuper/plugins/ai.py").read_text(encoding="utf-8")
_tree = ast.parse(_src)
_body, _on = [], False
for _n in _tree.body:
    _names = [t.id for t in getattr(_n, "targets", []) if isinstance(t, ast.Name)]
    if "_skip" in _names:
        _on = True
    if "SYSTEM_PROMPT" in _names:
        break
    if _on and not isinstance(_n, (ast.Import, ast.ImportFrom, ast.AsyncFunctionDef)):
        _body.append(_n)
ai = types.SimpleNamespace()
_ns = {"re": re, "unicodedata": unicodedata, "_emoji_mod": _emoji_mod, **{k: v for k, v in vars(_emoji_mod).items() if k.startswith("E_")}}
exec(compile(ast.Module(body=_body, type_ignores=[]), "ai_emoji", "exec"), _ns)
ai.__dict__.update(_ns)


class AiEmojiTest(unittest.TestCase):
    def test_bare_words_untouched(self):
        s = "Anh chờ em một chút, em cười nói với anh rồi chạy đi hát."
        self.assertEqual(ai._normalize_ai_answer(s), s)

    def test_starred_action(self):
        out = ai._normalize_ai_answer("Hihi *cười* nè")
        self.assertNotIn("cười", out)
        self.assertIn(dict((p.strip(), e) for p, e in ai._ACTION_PHRASES)["cười"], out)

    def test_common_word_names_not_replaced(self):
        s = "NOTE: please WAIT, STAR FIRE PARTY"
        self.assertEqual(ai._replace_standalone_emoji_names(s), s)


class AiPromptTest(unittest.TestCase):
    def test_no_emoji_spam_rule(self):
        self.assertNotIn("10–15", _src)
        self.assertNotIn("RẤT NHIỀU emoji", _src)


if __name__ == '__main__':
    unittest.main()
