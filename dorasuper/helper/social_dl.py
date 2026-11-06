"""Nhận diện link mạng xã hội cho bộ tải ảnh/video (không phụ thuộc Telegram).

- extract_social_url(text, manual=False) -> (url, platform) | None
  * autodl / mention (manual=False): chỉ nhận domain mạng xã hội đã biết,
    hoặc URL mà yt-dlp có extractor riêng (không phải "generic"), hoặc gallery-dl nhận.
  * /dl (manual=True): thêm fallback — bất kỳ URL http(s) nào cũng được thử.
"""
from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import urlparse

_TAIL = r"/[^\s<>\"']*"


def _p(hosts: str, path: str = _TAIL) -> re.Pattern:
    return re.compile(
        rf"(?:https?://)?(?:[a-z0-9-]+\.)*(?:{hosts})(?::\d+)?{path}",
        re.IGNORECASE,
    )


# Thứ tự quan trọng: pattern cụ thể trước.
URL_PATTERNS: dict[str, re.Pattern] = {
    "tiktok": _p(r"tiktok\.com|tiktokv\.com|kktiktok\.com"),
    "douyin": _p(r"douyin\.com|iesdouyin\.com"),
    "facebook": _p(r"facebook\.com|fb\.com|fb\.watch|fb\.me|fb\.gg"),
    "instagram": _p(r"instagram\.com|instagr\.am|ddinstagram\.com"),
    "threads": _p(r"threads\.net|threads\.com"),
    "x": _p(r"twitter\.com|x\.com|fxtwitter\.com|vxtwitter\.com|fixupx\.com"),
    "youtube": _p(r"youtube\.com|youtu\.be|youtube-nocookie\.com"),
    "reddit": _p(r"reddit\.com|redd\.it"),
    "pinterest": _p(r"pinterest\.(?:com|[a-z]{2,3})(?:\.[a-z]{2})?|pin\.it"),
    "xiaohongshu": _p(r"xiaohongshu\.com|xhslink\.com|rednote\.com"),
    "bilibili": _p(r"bilibili\.com|bilibili\.tv|b23\.tv"),
    "capcut": _p(r"capcut\.com|capcut\.net"),
    "kuaishou": _p(r"kuaishou\.com|kwai\.com|chenzhongtech\.com"),
    "soundcloud": _p(r"soundcloud\.com|snd\.sc|on\.soundcloud\.com"),
    "twitch": _p(r"twitch\.tv"),
    "vimeo": _p(r"vimeo\.com"),
    "dailymotion": _p(r"dailymotion\.com|dai\.ly"),
    "rumble": _p(r"rumble\.com"),
    "streamable": _p(r"streamable\.com"),
    "imgur": _p(r"imgur\.com"),
    "tumblr": _p(r"tumblr\.com"),
    "bluesky": _p(r"bsky\.app"),
    "snapchat": _p(r"snapchat\.com"),
    "linkedin": _p(r"linkedin\.com"),
    "vk": _p(r"vk\.com|vk\.ru|vkvideo\.ru"),
    "okru": _p(r"ok\.ru"),
    "weibo": _p(r"weibo\.com|weibo\.cn"),
    "likee": _p(r"likee\.video|likee\.com|l\.likee\.video"),
    "lemon8": _p(r"lemon8-app\.com"),
    "mixcloud": _p(r"mixcloud\.com"),
    "bandcamp": _p(r"bandcamp\.com"),
    "youku": _p(r"youku\.com"),
    "ixigua": _p(r"ixigua\.com"),
    "kick": _p(r"kick\.com"),
    "9gag": _p(r"9gag\.com"),
    "telegram": _p(r"t\.me"),
    "deviantart": _p(r"deviantart\.com"),
    "artstation": _p(r"artstation\.com"),
    "pixiv": _p(r"pixiv\.net"),
    "flickr": _p(r"flickr\.com|flic\.kr"),
    "giphy": _p(r"giphy\.com"),
    "tenor": _p(r"tenor\.com"),
    "imdb": _p(r"imdb\.com/video"),
    "zingmp3": _p(r"zingmp3\.vn"),
    "nhaccuatui": _p(r"nhaccuatui\.com"),
    "zalo": _p(r"zalo\.video|zingnews\.vn/video"),
    "mastodon": _p(r"mastodon\.social|mstdn\.social"),
    "truthsocial": _p(r"truthsocial\.com"),
    "gettr": _p(r"gettr\.com"),
    "triller": _p(r"triller\.co"),
    "coub": _p(r"coub\.com"),
    "ted": _p(r"ted\.com"),
    "archive": _p(r"archive\.org"),
    "niconico": _p(r"nicovideo\.jp|nico\.ms"),
    "naver": _p(r"tv\.naver\.com|naver\.me"),
    "afreecatv": _p(r"afreecatv\.com|sooplive\.co\.kr"),
}

# Rút gọn chung — không tự động tải trừ khi extractor nhận URL gốc
SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
    "cutt.ly", "rb.gy", "shorturl.at", "s.id", "rebrand.ly", "lnkd.in",
}

# Dịch vụ DRM/thuê bao — không cố hỗ trợ
BLOCKED_HOSTS = {
    "netflix.com", "disneyplus.com", "spotify.com", "open.spotify.com", "primevideo.com",
    "hulu.com", "max.com", "hbomax.com", "music.apple.com", "tv.apple.com",
}

_ANY_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAIL = ".,;:!?)]}>»\u201d\u2019'\""


def _clean(url: str) -> str:
    return url.strip().rstrip(_TRAIL)


def host_of(url: str) -> str:
    u = url if re.match(r"^https?://", url, re.I) else "https://" + url
    try:
        h = (urlparse(u).hostname or "").lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def _host_in(host: str, domains: set[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def infer_platform(url: str) -> str:
    """Nhãn nền tảng cho caption từ hostname."""
    for name, pat in URL_PATTERNS.items():
        m = pat.match(url) or pat.match("https://" + url.split("://", 1)[-1])
        if m:
            return name
    host = host_of(url)
    if not host:
        return "web"
    parts = host.split(".")
    label = parts[-2] if len(parts) >= 2 else parts[0]
    return label[:20] or "web"


@lru_cache(maxsize=1)
def _ydl_extractors():
    try:
        from yt_dlp.extractor import gen_extractor_classes
        return [ie for ie in gen_extractor_classes() if ie.ie_key() != "Generic"]
    except Exception:
        return []


def ytdlp_suitable(url: str) -> str | None:
    """Tên extractor yt-dlp (không phải generic) phù hợp với URL, hoặc None."""
    for ie in _ydl_extractors():
        try:
            if ie.suitable(url) and ie.working():
                return ie.ie_key()
        except Exception:
            continue
    return None


def gallerydl_suitable(url: str) -> bool:
    try:
        from gallery_dl import extractor as gex
    except Exception:
        return False
    try:
        ex = gex.find(url)
    except Exception:
        return False
    if not ex:
        return False
    cat = (getattr(ex, "category", "") or "").lower()
    return cat not in ("directlink", "generic", "noop", "recursive", "")


def extract_social_url(text: str, manual: bool = False, use_extractors: bool = True) -> tuple[str, str] | None:
    """Trích URL tải được đầu tiên. Returns (url, platform) hoặc None."""
    if not text or not text.strip():
        return None
    # 1. URL đầy đủ có scheme
    full = [_clean(m.group(0)) for m in _ANY_URL.finditer(text)]
    for url in full:
        host = host_of(url)
        if not host or _host_in(host, BLOCKED_HOSTS):
            continue
        for name, pat in URL_PATTERNS.items():
            if pat.fullmatch(url) or pat.match(url):
                return url, name
    # 2. Link mạng xã hội đã biết nhưng không có scheme (vd "vm.tiktok.com/xxx")
    for name, pat in URL_PATTERNS.items():
        for m in pat.finditer(text):
            s = m.start()
            if s > 0 and (text[s - 1].isalnum() or text[s - 1] in "/.@-_"):
                continue
            url = _clean(m.group(0))
            return url, name
    # 3. Extractor yt-dlp / gallery-dl nhận URL gốc
    if use_extractors:
        for url in full:
            host = host_of(url)
            if not host or _host_in(host, BLOCKED_HOSTS) or _host_in(host, SHORTENERS):
                continue
            if ytdlp_suitable(url) or gallerydl_suitable(url):
                return url, infer_platform(url)
    # 4. /dl thủ công: thử mọi URL http(s)
    if manual:
        for url in full:
            if host_of(url):
                return url, infer_platform(url)
    return None
