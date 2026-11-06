"""Offline tests cho nhận diện link mạng xã hội (dorasuper/helper/social_dl.py)."""
import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "social_dl", Path(__file__).resolve().parents[1] / "dorasuper/helper/social_dl.py"
)
sd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sd)

OLD = {
    "https://vm.tiktok.com/ZMabc123/": "tiktok",
    "https://www.facebook.com/reel/123456": "facebook",
    "https://fb.watch/abcDEF/": "facebook",
    "https://www.facebook.com/share/r/1AbCd/": "facebook",
    "https://www.instagram.com/reel/Cxyz/": "instagram",
    "https://www.instagram.com/stories/user/123/": "instagram",
    "https://x.com/user/status/123": "x",
    "https://mobile.twitter.com/user/status/123": "x",
    "https://youtube.com/shorts/abcdefghijk": "youtube",
    "https://music.youtube.com/watch?v=abcdefghijk": "youtube",
    "https://www.youtube.com/live/abcdefghijk": "youtube",
    "https://youtu.be/abcdefghijk": "youtube",
    "https://www.reddit.com/r/pics/comments/abc/x/": "reddit",
    "https://v.redd.it/abc123": "reddit",
    "https://redd.it/abc123": "reddit",
    "https://pin.it/abc": "pinterest",
    "https://www.pinterest.com/pin/123/": "pinterest",
    "https://www.threads.net/@user/post/abc": "threads",
    "https://v.douyin.com/abc/": "douyin",
    "https://xhslink.com/abc": "xiaohongshu",
    "https://www.xiaohongshu.com/explore/abc": "xiaohongshu",
    "https://b23.tv/abc": "bilibili",
    "https://www.bilibili.com/video/BV1xx": "bilibili",
    "https://www.capcut.com/t/abc": "capcut",
    "https://v.kuaishou.com/abc": "kuaishou",
    "https://soundcloud.com/a/b": "soundcloud",
}
NEW = {
    "https://clips.twitch.tv/SomeClip": "twitch",
    "https://www.twitch.tv/videos/123": "twitch",
    "https://vimeo.com/123": "vimeo",
    "https://www.dailymotion.com/video/x8abc": "dailymotion",
    "https://rumble.com/v123-abc.html": "rumble",
    "https://streamable.com/abc": "streamable",
    "https://imgur.com/gallery/abc": "imgur",
    "https://someone.tumblr.com/post/123": "tumblr",
    "https://bsky.app/profile/a.bsky.social/post/abc": "bluesky",
    "https://www.snapchat.com/spotlight/abc": "snapchat",
    "https://www.linkedin.com/posts/abc": "linkedin",
    "https://vk.com/video-1_2": "vk",
    "https://ok.ru/video/123": "okru",
    "https://weibo.com/123/abc": "weibo",
    "https://likee.video/@u/video/1": "likee",
    "https://www.lemon8-app.com/@u/123": "lemon8",
    "https://www.mixcloud.com/u/mix/": "mixcloud",
    "https://artist.bandcamp.com/track/x": "bandcamp",
    "https://v.youku.com/v_show/id_abc.html": "youku",
    "https://www.ixigua.com/123": "ixigua",
}


class TestSocialUrl(unittest.TestCase):
    def test_known(self):
        for url, plat in {**OLD, **NEW}.items():
            with self.subTest(url=url):
                self.assertEqual(sd.extract_social_url(f"xem nè {url} hay", use_extractors=False), (url, plat))

    def test_no_scheme(self):
        self.assertEqual(sd.extract_social_url("vm.tiktok.com/ZMabc/", use_extractors=False)[1], "tiktok")

    def test_trailing_punct(self):
        self.assertEqual(sd.extract_social_url("(https://x.com/a/status/1).", use_extractors=False)[0], "https://x.com/a/status/1")

    def test_random_not_autodl(self):
        for t in ("https://example.com/foo", "https://bit.ly/abc", "https://fix.com/a", "hello world", "https://open.spotify.com/track/1"):
            with self.subTest(t=t):
                self.assertIsNone(sd.extract_social_url(t, use_extractors=False))

    def test_manual_generic(self):
        self.assertEqual(sd.extract_social_url("https://example.com/foo", manual=True, use_extractors=False),
                         ("https://example.com/foo", "example"))

    def test_infer_platform(self):
        self.assertEqual(sd.infer_platform("https://bsky.app/x/y"), "bluesky")
        self.assertEqual(sd.infer_platform("https://media.foo.co/x"), "foo")

    def test_extractors_offline_no_false_positive(self):
        # yt-dlp/gallery-dl suitable() chỉ dùng regex, không cần mạng
        for t in ("https://example.com/foo", "https://www.google.com/", "https://bit.ly/abc"):
            with self.subTest(t=t):
                self.assertIsNone(sd.extract_social_url(t))


if __name__ == "__main__":
    unittest.main()
