import importlib.util
import pathlib
import sys
import types
import unittest

try:
    import httpx  # noqa: F401
except ImportError:
    _h = types.ModuleType("httpx")
    _h.HTTPError = Exception
    sys.modules["httpx"] = _h

_P = pathlib.Path(__file__).resolve().parents[1] / "dorasuper" / "helper" / "grok_imagine.py"
_spec = importlib.util.spec_from_file_location("grok_imagine_test", _P)
gi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gi)


class T(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(gi.clamp_duration(0), 1)
        self.assertEqual(gi.clamp_duration(5), 5)
        self.assertEqual(gi.clamp_duration(99), 15)

    def test_submit(self):
        self.assertEqual(gi.parse_submit({"request_id": "abc"})["id"], "abc")
        with self.assertRaises(gi.GrokVideoError):
            gi.parse_submit({})

    def test_status(self):
        j = gi.parse_status({"status": "done", "video": {"url": "http://v", "duration": 5}})
        self.assertEqual((j["status"], j["url"]), ("done", "http://v"))
        j = gi.parse_status({"status": "failed", "error": {"code": "invalid_argument", "message": "bad"}})
        self.assertEqual((j["status"], j["error"], j["code"]), ("failed", "bad", "invalid_argument"))

    def test_errors(self):
        e = gi.parse_error(401, {"error": {"message": "Incorrect API key", "type": "invalid_request_error"}})
        self.assertEqual(e.status, 401)
        self.assertIn("key", gi.friendly_grok_message(e).lower())
        e = gi.parse_error(402, {"error": {"message": "Insufficient credits"}})
        self.assertIn("hạn mức", gi.friendly_grok_message(e))
        s = gi.sanitize_error("bad xai-ABCDEFGH1234 Bearer tok <x>", "tok")
        self.assertNotIn("ABCDEFGH1234", s)
        self.assertNotIn("tok", s)
        self.assertIn("&lt;x&gt;", s)


if __name__ == "__main__":
    unittest.main()
