import base64
import unittest
from datetime import datetime, timezone

from dorasuper.helper.yeta_media import (
    YetaError, clamp_seconds, is_private_chat, parse_error, parse_image_response,
    parse_video_job, remaining_videos, sanitize_error, vn_date_str,
)


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
        s = sanitize_error("bad SECRET123 Bearer abc <x>", "SECRET123")
        self.assertNotIn("SECRET123", s)
        self.assertNotIn("abc", s)
        self.assertIn("&lt;x&gt;", s)


if __name__ == "__main__":
    unittest.main()
