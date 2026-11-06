import base64
import unittest
from datetime import datetime, timezone

import importlib.util
import pathlib
import sys
import types

try:
    import httpx  # noqa: F401
except ImportError:  # môi trường test không có httpx
    _h = types.ModuleType("httpx")
    _h.HTTPError = Exception
    sys.modules["httpx"] = _h

_P = pathlib.Path(__file__).resolve().parents[1] / "dorasuper" / "helper" / "yeta_media.py"
_spec = importlib.util.spec_from_file_location("yeta_media_test", _P)
ym = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ym)
YetaError, clamp_seconds, is_private_chat = ym.YetaError, ym.clamp_seconds, ym.is_private_chat
parse_error, parse_image_response, parse_video_job = ym.parse_error, ym.parse_image_response, ym.parse_video_job
friendly_yeta_message = ym.friendly_yeta_message
remaining_videos, sanitize_error, vn_date_str = ym.remaining_videos, ym.sanitize_error, ym.vn_date_str


class T(unittest.TestCase):
    def test_date_rollover(self):
        self.assertEqual(vn_date_str(datetime(2026, 11, 6, 16, 59, tzinfo=timezone.utc)), "2026-11-06")
        self.assertEqual(vn_date_str(datetime(2026, 11, 6, 17, 0, tzinfo=timezone.utc)), "2026-11-07")

    def test_remaining(self):
        self.assertEqual(remaining_videos(0), 2)
        self.assertEqual(remaining_videos(2), 0)
        self.assertEqual(remaining_videos(5), 0)

    def test_private(self):
        class E: value = "private"
        self.assertTrue(is_private_chat(E()))
        self.assertFalse(is_private_chat("supergroup"))

    def test_image(self):
        b = base64.b64encode(b"img").decode()
        self.assertEqual(parse_image_response({"data": [{"b64_json": b}]}), ("bytes", b"img"))
        self.assertEqual(parse_image_response({"data": [{"url": "u"}]}), ("url", "u"))
        with self.assertRaises(YetaError):
            parse_image_response({"data": []})

    def test_video(self):
        self.assertEqual(parse_video_job({"task_id": "t1", "status": "queued"})["id"], "t1")
        j = parse_video_job({"id": "t", "status": "completed", "url": "http://v"})
        self.assertEqual((j["status"], j["url"]), ("completed", "http://v"))
        self.assertEqual(clamp_seconds(1), 4)
        self.assertEqual(clamp_seconds(99), 15)

    def test_errors(self):
        e = parse_error(503, {"error": {"code": "model_not_found", "message": "No available channel"}})
        self.assertTrue(e.model_not_found)
        e = parse_error(401, {"code": "fail_to_fetch_task", "message": "AuthenticationError"})
        self.assertFalse(e.model_not_found)
        self.assertTrue(e.upstream_auth)
        nested = '{"error":{"code":"AuthenticationError","message":"The API key doesn\'t exist."}}'
        e = parse_error(401, {"code": "fail_to_fetch_task", "message": nested})
        self.assertTrue(e.upstream_auth)
        self.assertIn("doesn't exist", e.message.lower())
        detail = (
            '{"status":402,"title":"Insufficient balance",'
            '"detail":"Insufficient balance to complete this request. '
            'Required: 200000 amount (20.0 credits), Available: 67500 amount (6.75 credits)"}'
        )
        e = parse_error(402, {"code": "fail_to_fetch_task", "message": detail})
        self.assertTrue(e.insufficient_credits)
        tip = friendly_yeta_message(e)
        self.assertIn("20", tip)
        self.assertIn("6.75", tip)
        s = sanitize_error("bad SECRET123 Bearer abc <x>", "SECRET123")
        self.assertNotIn("SECRET123", s)
        self.assertNotIn("abc", s)
        self.assertIn("&lt;x&gt;", s)


if __name__ == "__main__":
    unittest.main()
