# Tải video/ảnh từ TikTok và các mạng xã hội khác (Cobalt / yt-dlp / gallery-dl)
# Bot tự nhận diện link trong tin nhắn, không cần lệnh

import asyncio
import html
import io
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from logging import getLogger

import aiohttp
import yt_dlp
from PIL import Image
from pyrogram import enums, filters
from pyrogram.enums import ChatType
from pyrogram.types import InputMediaPhoto, Message

from dorasuper import app
from dorasuper.core.decorator import capture_err, new_task
from dorasuper.core.decorator.permissions import require_admin
from database.autodl_db import toggle_autodl
from dorasuper.emoji import E_ERROR, E_HEART, E_LINK, E_MSG, E_VIEW, E_LOADING, E_MUSIC, E_SUCCESS, E_TIP, E_USER, E_SHOUT, E_UPD
from dorasuper.helper.pyro_progress import humanbytes
from dorasuper.vars import (
    COMMAND_HANDLER,
    LOG_CHANNEL,
    ROOT_DIR,
    SUDO,
    COBALT_URL,
    YT_DLP_COOKIES_FILE,
    YT_DLP_COOKIES_FROM_BROWSER,
    INSTAGRAM_USERNAME,
    INSTAGRAM_PASSWORD,
    INSTAGRAM_SESSION,
)

LOGGER = getLogger("DoraSuper")

__MODULE__ = "TảiVideo"
__HELP__ = """
<blockquote>Gửi link TikTok, X (Twitter), Facebook hoặc Instagram - Bot tự tải và gửi video/ảnh.
• TikTok: video + ảnh/album (gallery-dl, TikWM, Cobalt)
• X (Twitter): video/ảnh (x.com, twitter.com)
• Facebook: video và ảnh (fb.com, fb.watch, facebook.com)
• Instagram: video/Reels (instagram.com)

Lệnh:
/autodl - Bật/tắt tự động tải link trong nhóm (admin)
/dl [link] - Tải ngay (dùng khi autodl tắt hoặc cần tải thủ công)</blockquote>
"""

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_ALBUM_PHOTOS = 10  # Telegram giới hạn media group tối đa 10 ảnh

# Regex theo từng nền tảng (dễ mở rộng thêm YouTube, ...)
URL_PATTERNS = {
    "tiktok": re.compile(
        r"(?:https?://)?(?:www\.|vm\.|vt\.|m\.|t\.)?(?:tiktok\.com|tiktokv\.com|kktiktok\.com)/[^\s]+",
        re.IGNORECASE,
    ),
    "facebook": re.compile(
        r"(?:https?://)?(?:www\.|m\.|mbasic\.|fb\.)?(?:facebook\.com|fb\.com|fb\.watch|fb\.me)/[^\s]+",
        re.IGNORECASE,
    ),
    "instagram": re.compile(
        r"(?:https?://)?(?:www\.|m\.)?(?:instagram\.com|instagr\.am)/[^\s]+",
        re.IGNORECASE,
    ),
    "x": re.compile(
        r"(?:https?://)?(?:www\.|mobile\.)?(?:twitter\.com|x\.com)/[^\s]+",
        re.IGNORECASE,
    ),
}


def _strip_ansi(text: str) -> str:
    ansi_escape = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text or "")


def _extract_supported_url(text: str) -> tuple[str, str] | None:
    """Trích URL đầu tiên được hỗ trợ. Returns (url, platform) hoặc None."""
    if not text or not text.strip():
        return None
    for platform, pattern in URL_PATTERNS.items():
        match = pattern.search(text)
        if match:
            return (match.group(0).strip(), platform)
    return None


def _is_command_message(text: str) -> bool:
    """Tin nhắn có phải là lệnh (bắt đầu bằng prefix + tên lệnh) không."""
    if not text:
        return False
    stripped = text.strip()
    for prefix in (COMMAND_HANDLER or ["/", "!"]):
        if prefix and stripped.startswith(prefix):
            return True
    return False


# Định dạng ưu tiên: video mp4/webm trước, sau đó ảnh (TikTok ảnh/album)
_FORMAT = "best[ext=mp4]/best[ext=webm]/best[ext=mp4]/best[ext=jpg]/best[ext=jpeg]/best[ext=png]/best[ext=webp]/best"
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
_VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".mov")


def _is_valid_image_bytes(raw: bytes) -> bool:
    """True nếu raw trông giống dữ liệu ảnh (magic bytes). Tránh gửi HTML/ corrupt."""
    if not raw or len(raw) < 12:
        return False
    if raw[:1] == b"<" or raw[:2] == b"\x1b[":
        return False  # HTML hoặc ANSI
    if raw[:3] == b"\xff\xd8\xff":
        return True  # JPEG
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return True  # PNG
    if raw[:4] == b"RIFF" and len(raw) >= 12 and raw[8:12] == b"WEBP":
        return True  # WebP
    return False


def _image_to_jpeg_sync(path: str) -> bytes | None:
    """Mở ảnh bằng PIL, chuyển sang JPEG (tránh IMAGE_PROCESS_FAILED). Trả về bytes hoặc None."""
    if not path or not os.path.isfile(path) or os.path.getsize(path) == 0:
        return None
    try:
        with open(path, "rb") as f:
            return _image_bytes_to_jpeg_sync(f.read())
    except Exception:
        return None


def _image_bytes_to_jpeg_sync(raw: bytes) -> bytes | None:
    """Chuyển bytes ảnh (PNG/WebP/JPEG) sang JPEG. Tránh PHOTO_EXT_INVALID khi gửi file gốc."""
    if not raw or len(raw) < 12:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.mode in ("RGBA", "P", "LA", "PA"):
                img = img.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92, optimize=True)
            return buf.getvalue()
    except Exception:
        return None


class _YDLLogger:
    """Logger cho yt-dlp: chuyển ERROR xuống DEBUG để tránh in ra terminal (bot đã trả lỗi thân thiện cho user)."""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        LOGGER.debug("yt-dlp: %s", msg)


def _download_sync(url: str, out_dir: str) -> tuple[list[str] | None, str | None, dict | None]:
    """Tải bằng yt-dlp. Returns (danh sách filepath, error, info_dict). Hỗ trợ video và ảnh/album TikTok."""
    # Dùng playlist_index để album ảnh ra nhiều file (id_1.jpg, id_2.jpg...); bài đơn vẫn ra 1 file
    out_tpl = os.path.join(out_dir, "%(id)s_%(playlist_index)s.%(ext)s")
    ydl_opts = {
        "format": _FORMAT,
        "outtmpl": out_tpl,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "noplaylist": True,  # Chỉ lấy đúng 1 mục từ URL (tránh link ảnh FB lại tải bài khác)
        "logger": _YDLLogger(),
    }
    # Cookie: file hoặc browser (Facebook, Instagram, ...)
    if YT_DLP_COOKIES_FROM_BROWSER:
        browser = YT_DLP_COOKIES_FROM_BROWSER.strip().lower()
        if browser:
            ydl_opts["cookiesfrombrowser"] = (browser,)
    elif YT_DLP_COOKIES_FILE:
        cookiefile_path = (
            YT_DLP_COOKIES_FILE
            if os.path.isabs(YT_DLP_COOKIES_FILE)
            else os.path.join(ROOT_DIR, YT_DLP_COOKIES_FILE)
        )
        if os.path.isfile(cookiefile_path):
            ydl_opts["cookiefile"] = cookiefile_path
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None, "Không lấy được thông tin.", None
            # Thu thập mọi file đã tải (1 video/ảnh hoặc nhiều ảnh trong album)
            collected: list[str] = []
            entries = info.get("entries") or [info]
            for ent in entries:
                if not ent:
                    continue
                filepath = ydl.prepare_filename(ent)
                if os.path.exists(filepath):
                    collected.append(filepath)
                    continue
                base = os.path.splitext(filepath)[0]
                for ext in (*_VIDEO_EXTS, ".m4a", *_IMAGE_EXTS):
                    p = base + ext
                    if os.path.exists(p):
                        collected.append(p)
                        break
            if not collected:
                # Fallback: quét thư mục (trường hợp template khác)
                for f in sorted(os.listdir(out_dir)):
                    p = os.path.join(out_dir, f)
                    if os.path.isfile(p):
                        collected.append(p)
            if not collected:
                return None, "Không tìm thấy file tải về.", None
            return collected, None, info
    except yt_dlp.utils.DownloadError as e:
        err = _strip_ansi(str(e))
        low = err.lower()
        if "private" in low:
            return None, "Video riêng tư, không tải được.", None
        if "region" in low or "blocked" in low:
            return None, "Video bị giới hạn theo khu vực.", None
        if "unsupported url" in low or "unsupported" in low and "url" in low:
            return None, "Link TikTok ảnh (photo) chưa được hỗ trợ. Chỉ tải được link video TikTok.", None
        if (
            "only available for registered users" in low
            or ("cookies" in low and "authentic" in low)
            or "fresh cookies" in low
            or ("cookies" in low and "needed" in low)
        ):
            msg = (
                "Facebook/Instagram cần cookie. config.env: YT_DLP_COOKIES_FROM_BROWSER=chrome hoặc YT_DLP_COOKIES_FILE=... Sau đó khởi động lại bot."
            )
            return None, msg, None
        return None, err[:200] if len(err) > 200 else err, None
    except Exception as e:
        return None, _strip_ansi(str(e))[:200], None


def _fmt_count(n: int | float, decimal: bool = False) -> str:
    """Format số: >= 1M -> Xm, >= 1k -> Xk. decimal=True: >= 10k thì 3 số (15.2k, 151k, 1.51m)."""
    n = int(n)
    if n >= 1_000_000:
        if decimal:
            val = int(n / 10_000) / 100  # 1.512345m -> 1.51m (3 số)
            return f"{val:.2f}".rstrip("0").rstrip(".") + "m"
        return f"{n // 1_000_000}m"
    if n >= 1_000:
        if decimal:
            if n >= 100_000:
                return f"{n // 1_000}k"  # 151k (3 số)
            if n >= 10_000:
                val = int(n / 100) / 10  # 15.2k (3 số)
                return f"{val:.1f}".rstrip("0").rstrip(".") + "k"
            val = int(n / 100) / 10  # 5.6k (dưới 10k: 1 thập phân)
            return f"{val:.1f}".rstrip("0").rstrip(".") + "k"
        return f"{n // 1_000}k"
    return f"{n:,}"


def _build_caption(info: dict | None, file_size: int, platform: str, shared_by: str) -> str:
    """Tạo caption: tiêu đề, tên tài khoản, số tim, số view, link (blockquote)."""
    lines = []
    if info:
        # Tiêu đề — X (Twitter) dùng "description" cho nội dung tweet
        title = (info.get("title") or info.get("description") or "").strip()
        if platform == "x" and not title:
            title = (info.get("fulltitle") or "").strip()
        if title:
            lines.append(f"<b>Tiêu đề:</b> {html.escape(title[:300])}")
        # Tên tài khoản — X thường dùng uploader_id (screen name)
        uploader = (info.get("uploader") or info.get("creator") or "").strip()
        if platform == "x" and not uploader and info.get("uploader_id"):
            uploader = ("@" + str(info.get("uploader_id")).strip()).strip()
        if not uploader and platform == "x":
            uploader = (info.get("uploader_id") or "").strip()
            if uploader and not uploader.startswith("@"):
                uploader = "@" + uploader
        if uploader:
            lines.append(f"<b>Tên tài khoản:</b> {html.escape(uploader)}")
        # User (có thể copy)
        # uid = (info.get("uploader_id") or "").strip()
        # if uid:
        #     lines.append(f"<b>User:</b> <code>@{uid}</code>")
        # Số tim (1 số thập phân)
        likes = info.get("like_count") or info.get("play_count")
        if likes is not None:
            lines.append(f"<b>Số tim:</b> {E_HEART} {_fmt_count(likes, decimal=True)}")
        # Số view
        views = info.get("view_count") or info.get("play_count")
        if views is not None:
            lines.append(f"<b>Số view:</b> {E_VIEW} {_fmt_count(views)}")
    # Link: rút gọn hiển thị theo nền tảng
    link = (info or {}).get("webpage_url") or (info or {}).get("url", "")
    if link:
        link_display = link
        if platform == "tiktok" or "@" in link:
            at_pos = link.find("@")
            if at_pos != -1:
                slash_after = link.find("/", at_pos)
                link_display = link[:slash_after] if slash_after != -1 else link
        elif platform == "x" and ("x.com" in link or "twitter.com" in link):
            # x.com/user/status/123 → x.com/@user
            try:
                parts = link.replace("twitter.com", "x.com").split("/")
                if "x.com" in parts and len(parts) > 2:
                    link_display = "x.com/" + parts[parts.index("x.com") + 1]
            except Exception:
                pass
        elif platform == "instagram" and "instagram.com" in link:
            # Giữ dạng ngắn: instagram.com/p/XXX hoặc instagram.com/reel/XXX
            for sep in ("/p/", "/reel/", "/tv/"):
                if sep in link:
                    i = link.find(sep)
                    end = link.find("/", i + len(sep) + 1)
                    link_display = link[:end] if end != -1 else link
                    break
        lines.append(f'<b>Link:</b> <a href="{html.escape(link)}">{html.escape(link_display)}</a>')
    if shared_by:
        lines.append(f"{E_USER} <b>Chia sẻ bởi:</b> {shared_by}")
    content = "\n".join(l for l in lines if l)
    return f"<blockquote>{content}</blockquote>" if content else ""


def _paths_by_type(paths: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Chia danh sách đường dẫn thành ảnh, video, còn lại."""
    images, videos, other = [], [], []
    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        if ext in _IMAGE_EXTS:
            images.append(p)
        elif ext in _VIDEO_EXTS:
            videos.append(p)
        else:
            other.append(p)
    return images, videos, other


# Header giống trình duyệt/mobile để TikTok trả HTML có og:image / JSON
_TIKTOK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
}


async def _resolve_tiktok_photo(url: str) -> tuple[bool, str | None]:
    """(True, final_url) nếu URL sau redirect là link TikTok /photo/; (False, final_url) nếu không phải."""
    if not url.strip():
        return False, None
    u = url.strip()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(u, allow_redirects=True, headers=_TIKTOK_HEADERS) as resp:
                final = str(resp.url)
                return "/photo/" in final, final
    except Exception:
        return False, None


def _normalize_image_url(u: str) -> str:
    """Chuẩn hóa URL ảnh (bỏ fragment, có thể giữ query)."""
    u = (u or "").strip().split("#")[0]
    return u


def _extract_photo_urls_from_html(html_text: str) -> list[str]:
    """Chỉ trích ảnh thuộc bài post: og:image (ảnh đại diện bài). Không quét avatar/thumbnail khác."""
    urls: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        u = _normalize_image_url(u)
        if not u or u in seen:
            return
        if not u.startswith("http"):
            return
        seen.add(u)
        urls.append(u)

    # Chỉ lấy og:image — đây là ảnh TikTok đặt cho bài post, không phải avatar/icon
    for pattern in (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'property=["\']og:image["\'][^>]*content=["\'](https?://[^"\']+)["\']',
    ):
        for m in re.finditer(pattern, html_text, re.I):
            add(m.group(1))
            break  # chỉ cần 1 og:image
        if urls:
            break

    return urls[:MAX_ALBUM_PHOTOS] if urls else []


def _instagram_media_to_info(media: object, url: str) -> dict:
    """Chuyển Media instagrapi sang dict dùng cho _build_caption (title, uploader, like_count, webpage_url)."""
    info = {}
    if url:
        info["webpage_url"] = url
    try:
        cap = getattr(media, "caption", None) or (media.dict().get("caption") if hasattr(media, "dict") else None)
        if cap and isinstance(cap, str) and cap.strip():
            info["title"] = cap.strip()[:500]
        user = getattr(media, "user", None)
        if user is not None:
            uname = getattr(user, "username", None) or (user.get("username") if isinstance(user, dict) else None)
            if uname:
                info["uploader"] = str(uname)
        elif hasattr(media, "dict"):
            u = media.dict().get("user") or {}
            if isinstance(u, dict) and u.get("username"):
                info["uploader"] = str(u["username"])
        lk = getattr(media, "like_count", None) or (media.dict().get("like_count") if hasattr(media, "dict") else None)
        if lk is not None:
            info["like_count"] = int(lk)
    except Exception:
        pass
    return info


def _download_instagram_instagrapi_sync(url: str, out_dir: str) -> tuple[list[str] | None, str | None, dict | None]:
    """Tải ảnh/video bài post Instagram bằng instagrapi (cần đăng nhập). Trả về (paths, None, info) hoặc (None, lỗi, None)."""
    if not INSTAGRAM_USERNAME or not (INSTAGRAM_PASSWORD or INSTAGRAM_SESSION):
        return None, "Chưa cấu hình INSTAGRAM_USERNAME và INSTAGRAM_PASSWORD (hoặc INSTAGRAM_SESSION) trong config.env.", None
    u = (url or "").strip()
    if not u.startswith("http"):
        u = "https://" + u
    if "instagram.com" not in u.lower():
        return None, "URL không phải Instagram.", None
    try:
        from instagrapi import Client

        cl = Client()
        if INSTAGRAM_SESSION:
            cl.login_by_sessionid(INSTAGRAM_SESSION)
        else:
            cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        out_path = Path(os.path.abspath(out_dir))
        media_pk = cl.media_pk_from_url(u)
        media_info = cl.media_info(media_pk)
        media_type = getattr(media_info, "media_type", None) or (media_info.dict().get("media_type") if hasattr(media_info, "dict") else None)
        paths: list[str] = []
        if media_type == 1:
            p = cl.photo_download(media_pk, folder=out_path)
            if p and os.path.isfile(p):
                paths.append(str(p))
        elif media_type == 8:
            downloaded = cl.album_download(media_pk, folder=out_path)
            if isinstance(downloaded, list):
                for x in downloaded:
                    if x and os.path.isfile(x):
                        paths.append(str(x))
            elif downloaded and os.path.isfile(downloaded):
                paths.append(str(downloaded))
        else:
            try:
                p = cl.video_download(media_pk, folder=out_path)
                if p and os.path.isfile(p):
                    paths.append(str(p))
            except Exception:
                try:
                    p = cl.clip_download(media_pk, folder=out_path)
                    if p and os.path.isfile(p):
                        paths.append(str(p))
                except Exception:
                    pass
        if not paths:
            return None, "instagrapi không tải được file.", None
        info_dict = _instagram_media_to_info(media_info, u)
        return paths[:MAX_ALBUM_PHOTOS], None, info_dict
    except ImportError:
        return None, "Chưa cài instagrapi (pip install instagrapi).", None
    except Exception as e:
        msg = _strip_ansi(str(e))[:200]
        if "login" in msg.lower() or "challenge" in msg.lower():
            msg = "Đăng nhập Instagram thất bại hoặc cần xác minh. Thử đổi mật khẩu hoặc dùng sessionid."
        return None, msg, None


def _download_images_gallery_dl_sync(url: str, out_dir: str) -> tuple[list[str] | None, str | None]:
    """Tải ảnh bằng gallery-dl (TikTok, Instagram, nhiều gallery...). Trả về (danh sách path ảnh, None) hoặc (None, lỗi)."""
    gdl = shutil.which("gallery-dl")
    if not gdl:
        return None, "Chưa cài gallery-dl (pip install gallery-dl)."
    u = (url or "").strip()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        out_dir = os.path.abspath(out_dir)
        proc = subprocess.run(
            [gdl, "-d", out_dir, "--no-mtime", u],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "")[:200]
            return None, err.strip() or f"gallery-dl exit {proc.returncode}"
        collected: list[str] = []
        for root, _, files in os.walk(out_dir):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in _IMAGE_EXTS:
                    collected.append(os.path.join(root, f))
        collected.sort()
        if not collected:
            return None, "gallery-dl không tải được ảnh."
        return collected[:MAX_ALBUM_PHOTOS], None
    except subprocess.TimeoutExpired:
        return None, "gallery-dl quá thời gian."
    except Exception as e:
        return None, _strip_ansi(str(e))[:150]


def _download_x_gallery_dl_sync(url: str, out_dir: str) -> tuple[list[str] | None, str | None]:
    """Tải ảnh/video từ X (Twitter) bằng gallery-dl. Trả về (danh sách path, None) hoặc (None, lỗi)."""
    gdl = shutil.which("gallery-dl")
    if not gdl:
        return None, "Chưa cài gallery-dl (pip install gallery-dl)."
    u = (url or "").strip()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        out_dir = os.path.abspath(out_dir)
        proc = subprocess.run(
            [gdl, "-d", out_dir, "--no-mtime", u],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "")[:200]
            return None, err.strip() or f"gallery-dl exit {proc.returncode}"
        collected: list[str] = []
        for root, _, files in os.walk(out_dir):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in _IMAGE_EXTS or ext in _VIDEO_EXTS:
                    collected.append(os.path.join(root, f))
        collected.sort()
        if not collected:
            return None, "gallery-dl không tải được media."
        # Ảnh tối đa MAX_ALBUM_PHOTOS; video giữ 1; nếu có cả hai thì ưu tiên gom đủ
        return collected, None
    except subprocess.TimeoutExpired:
        return None, "gallery-dl quá thời gian."
    except Exception as e:
        return None, _strip_ansi(str(e))[:150]


def _extract_x_metadata_sync(url: str) -> dict:
    """Lấy metadata tweet X (title, uploader, webpage_url) bằng yt-dlp extract_info(download=False). Trả về {} nếu lỗi."""
    u = (url or "").strip()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "logger": _YDLLogger(),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(u, download=False)
        if not info:
            return {}
        title = (info.get("title") or info.get("description") or info.get("fulltitle") or "").strip()
        uploader = (info.get("uploader") or info.get("creator") or "").strip()
        if not uploader and info.get("uploader_id"):
            uploader = "@" + str(info.get("uploader_id")).strip()
        return {
            "title": title or None,
            "uploader": uploader or None,
            "like_count": info.get("like_count"),
            "view_count": info.get("view_count"),
            "webpage_url": info.get("webpage_url") or info.get("url") or u,
        }
    except Exception:
        return {}


def _fetch_x_metadata_from_html_sync(url: str) -> dict:
    """Lấy metadata X từ HTML (og:title, og:description) khi yt-dlp thất bại (tweet chỉ ảnh). Trả về {} nếu lỗi."""
    u = (url or "").strip()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        import urllib.request
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        info = {"webpage_url": u}
        for prop, key in (("og:title", "title"), ("og:description", "description")):
            for pattern in (
                rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']',
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']',
            ):
                m = re.search(pattern, html, re.I)
                if m:
                    val = m.group(1).strip()
                    if val:
                        info[key] = val[:500]
                    break
        # og:title trên X thường là "Name (@handle) / X" hoặc tweet text
        if info.get("title") and "(" in info["title"] and ")" in info["title"]:
            match = re.search(r"\(@([^)]+)\)", info["title"])
            if match:
                info["uploader"] = "@" + match.group(1)
        if not info.get("title") and info.get("description"):
            info["title"] = info["description"]
        return info
    except Exception:
        return {}


async def _download_tiktok_photo(url: str, out_dir: str) -> tuple[list[str] | None, str | None]:
    """Tải ảnh từ link TikTok /photo/: fetch HTML (thử 2 User-Agent), trích og:image, tải về file."""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        image_urls = []
        for headers in (
            _TIKTOK_HEADERS,
            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"},
        ):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            continue
                        html_text = await resp.text()
                image_urls = _extract_photo_urls_from_html(html_text)
                if image_urls:
                    break
            except Exception:
                continue
        if not image_urls:
            return None, "Không tìm thấy ảnh trong trang. Thử lại sau."
        paths = []
        for i, img_url in enumerate(image_urls[:20]):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(img_url, headers=_TIKTOK_HEADERS) as r:
                        if r.status != 200:
                            continue
                        raw = await r.read()
                if not _is_valid_image_bytes(raw):
                    continue
                ext = ".jpg"
                if raw[:3] == b"\xff\xd8\xff":
                    ext = ".jpg"
                elif raw[:8] == b"\x89PNG\r\n\x1a\n":
                    ext = ".png"
                elif raw[:4] == b"RIFF" and len(raw) >= 12 and raw[8:12] == b"WEBP":
                    ext = ".webp"
                path = os.path.join(out_dir, f"photo_{i:02d}{ext}")
                with open(path, "wb") as f:
                    f.write(raw)
                if os.path.getsize(path) > 0:
                    paths.append(path)
            except Exception:
                continue
        if not paths:
            return None, "Tải ảnh thất bại."
        return paths, None
    except asyncio.TimeoutError:
        return None, "Trang TikTok phản hồi quá chậm."
    except Exception as e:
        LOGGER.exception("_download_tiktok_photo: %s", e)
        return None, _strip_ansi(str(e))[:150]


# TikWM API (fallback TikTok) — theo logic ytttins_dl
TIKWM_API = "https://www.tikwm.com/api/"


async def _fetch_cobalt_tiktok(url: str) -> dict | None:
    """Gọi Cobalt API cho TikTok. Trả về response JSON nếu thành công, None nếu lỗi."""
    if not COBALT_URL or not url.strip():
        return None
    u = url.strip()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{COBALT_URL}/",
                json={
                    "url": u,
                    "videoQuality": "1080",
                    "downloadMode": "auto",
                    "subtitleLang": "vi",
                },
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except Exception as e:
        LOGGER.warning("Cobalt TikTok: %s", e)
        return None


async def _fetch_tikwm_tiktok(url: str) -> dict | None:
    """TikWM API (fallback TikTok): GET tikwm.com/api/?url=...&hd=1. Trả về data hoặc None."""
    u = (url or "").strip()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        headers = {"User-Agent": _TIKTOK_HEADERS["User-Agent"], "Accept": "application/json"}
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Thử GET trước, không được thì POST
            for method, kwargs in (
                ("GET", {"params": {"url": u, "hd": 1}}),
                ("POST", {"data": {"url": u, "hd": 1}}),
            ):
                try:
                    if method == "GET":
                        resp = await session.get(TIKWM_API, headers=headers, **kwargs)
                    else:
                        resp = await session.post(TIKWM_API, headers=headers, **kwargs)
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    if data.get("code") != 0:
                        LOGGER.info("TikWM %s code=%s msg=%s", method, data.get("code"), data.get("msg"))
                        continue
                    return data.get("data") or {}
                except Exception:
                    continue
        return None
    except Exception as e:
        LOGGER.warning("TikWM TikTok: %s", e)
        return None


def _normalize_tikwm_images(data: dict) -> list[str]:
    """Lấy danh sách URL ảnh từ response TikWM (nhiều dạng: list string, list dict có url)."""
    images = data.get("images") or data.get("image_post") or data.get("album") or []
    if not isinstance(images, list):
        images = [images] if images else []
    urls = []
    for x in images:
        if isinstance(x, str) and x.strip().startswith("http"):
            urls.append(x.strip())
        elif isinstance(x, dict):
            u = (x.get("url") or x.get("image_url") or x.get("src") or "").strip()
            if u.startswith("http"):
                urls.append(u)
    return urls


async def _download_tiktok_via_tikwm(url: str, out_dir: str) -> tuple[list[str] | None, dict | None, str | None]:
    """Tải TikTok qua TikWM API (video hoặc ảnh slideshow). Returns (paths, metadata, error)."""
    data = await _fetch_tikwm_tiktok(url)
    if not data:
        return None, None, "TikWM không lấy được dữ liệu."
    # Video: hdplay hoặc play
    video_url = (data.get("hdplay") or data.get("play") or "").strip()
    images = _normalize_tikwm_images(data)
    author = (data.get("author") or {})
    if isinstance(author, dict):
        author = author.get("unique_id") or author.get("nickname") or "TikTok"
    else:
        author = str(author)
    title = (data.get("title") or "TikTok").strip()[:200]
    meta = {
        "uploader": author,
        "title": title,
        "webpage_url": url,
        "like_count": data.get("digg_count") or data.get("like_count"),
        "view_count": data.get("play_count") or data.get("view_count"),
    }

    if video_url:
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(video_url, headers=_TIKTOK_HEADERS) as r:
                    if r.status != 200:
                        return None, None, f"Tải video thất bại (HTTP {r.status})"
                    raw = await r.read()
            if len(raw) > MAX_FILE_SIZE:
                return None, None, f"Video quá lớn ({humanbytes(len(raw))})."
            path = os.path.join(out_dir, "tikwm_video.mp4")
            with open(path, "wb") as f:
                f.write(raw)
            return [path], meta, None
        except Exception as e:
            return None, None, _strip_ansi(str(e))[:150]

    # Nếu không có mảng images, thử dùng cover/thumbnail (ít nhất 1 ảnh)
    if not images:
        for key in ("origin_cover", "cover", "thumbnail", "cover_url"):
            u = (data.get(key) or "").strip()
            if isinstance(u, str) and u.startswith("http"):
                images = [u]
                break
    if not images:
        return None, None, "Không có ảnh trong phản hồi TikWM."

    paths = []
    for i, img_url in enumerate((images or [])[:MAX_ALBUM_PHOTOS]):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(img_url, headers=_TIKTOK_HEADERS) as r:
                    if r.status != 200:
                        continue
                    raw = await r.read()
            if not _is_valid_image_bytes(raw):
                continue
            path = os.path.join(out_dir, f"tikwm_{i:02d}.jpg")
            with open(path, "wb") as f:
                f.write(raw)
            jpeg = await asyncio.to_thread(_image_to_jpeg_sync, path)
            if jpeg:
                jpath = os.path.join(out_dir, f"tikwm_{i:02d}_o.jpg")
                with open(jpath, "wb") as f:
                    f.write(jpeg)
                paths.append(jpath)
            elif os.path.getsize(path) > 0:
                paths.append(path)
        except Exception:
            continue
    if not paths:
        return None, None, "Tải ảnh TikWM thất bại."
    return paths, meta, None


def _normalize_tiktok_url(url: str) -> str:
    """kktiktok.com → tiktok.com (bỏ 'kk' là ra link gốc)."""
    if not url or "kktiktok" not in url.lower():
        return url
    return re.sub(r"kktiktok\.com", "tiktok.com", url, flags=re.IGNORECASE)


async def _send_result_to_log_channel(ctx: Message, platform: str, caption: str, images: list, videos: list, other: list):
    """Gửi bản sao kết quả tải (video/ảnh) vào LOG_CHANNEL — cả khi user tải trong PM hoặc trong nhóm. SUDO không gửi."""
    u = ctx.from_user
    if not u:
        return
    if u.id in SUDO:
        return
    if ctx.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        chat_label = html.escape(ctx.chat.title or "Nhóm")
        prefix = f"{E_MSG} {E_USER} Nhóm <b>{chat_label}</b> — {u.first_name or 'User'} (id: <code>{u.id}</code>) | {platform}\n\n"
    else:
        prefix = f"{E_MSG} {E_USER} PM từ {u.first_name or 'User'} (id: <code>{u.id}</code>) | {platform}\n\n"
    cap = prefix + (caption or "")
    try:
        if len(images) > 1:
            jpeg_list: list[bytes] = []
            for p in images[:MAX_ALBUM_PHOTOS]:
                b = await asyncio.to_thread(_image_to_jpeg_sync, p)
                if b and len(b) <= MAX_FILE_SIZE:
                    jpeg_list.append(b)
            if jpeg_list:
                media_list = [
                    InputMediaPhoto(media=io.BytesIO(jpeg_list[0]), caption=cap, parse_mode=enums.ParseMode.HTML),
                    *[InputMediaPhoto(media=io.BytesIO(b)) for b in jpeg_list[1:]],
                ]
                await app.send_media_group(LOG_CHANNEL, media=media_list)
        elif len(images) == 1:
            jpeg_bytes = await asyncio.to_thread(_image_to_jpeg_sync, images[0])
            if jpeg_bytes and len(jpeg_bytes) <= MAX_FILE_SIZE:
                await app.send_photo(LOG_CHANNEL, photo=io.BytesIO(jpeg_bytes), caption=cap, parse_mode=enums.ParseMode.HTML)
            else:
                await app.send_photo(LOG_CHANNEL, photo=images[0], caption=cap, parse_mode=enums.ParseMode.HTML)
        elif videos:
            await app.send_video(LOG_CHANNEL, video=videos[0], caption=cap, parse_mode=enums.ParseMode.HTML)
        elif other:
            await app.send_document(LOG_CHANNEL, document=other[0], caption=cap, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        LOGGER.warning("send_result_to_log_channel: %s", e)


async def _process_download(ctx: Message, url: str, platform: str):
    """Xử lý tải và gửi media (video, ảnh đơn hoặc album ảnh TikTok)."""
    if platform == "tiktok":
        url = _normalize_tiktok_url(url)
    m = await ctx.reply_msg(f"{E_SHOUT}Đang tải từ {platform}{E_LOADING}", quote=True)

    # TikTok: ưu tiên Cobalt (redirect/tunnel/picker — theo ytttins_dl)
    if platform == "tiktok" and COBALT_URL:
        data = await _fetch_cobalt_tiktok(url)
        if data and data.get("status") == "picker":
            picker = data.get("picker") or []
            if picker:
                try:
                    out_dir = tempfile.mkdtemp(prefix="cobalt_picker_", dir=str(ROOT_DIR / "downloads"))
                    collected: list[str] = []
                    for idx, item in enumerate(picker[:MAX_ALBUM_PHOTOS]):
                        u = (item.get("url") or "").strip()
                        if not u:
                            continue
                        try:
                            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                                async with session.get(u) as r:
                                    if r.status != 200:
                                        continue
                                    raw = await r.read()
                            if len(raw) > MAX_FILE_SIZE:
                                continue
                            ext = ".jpg"
                            ct = (item.get("mime") or item.get("type") or "").lower()
                            if "png" in ct:
                                ext = ".png"
                            elif "webp" in ct:
                                ext = ".webp"
                            elif "mp4" in ct or "video" in ct:
                                ext = ".mp4"
                            path = os.path.join(out_dir, f"p_{idx}{ext}")
                            with open(path, "wb") as f:
                                f.write(raw)
                            if os.path.getsize(path) > 0:
                                collected.append(path)
                        except Exception:
                            continue
                    if collected:
                        shared_by = (ctx.from_user.mention or (f"@{ctx.from_user.username}" if ctx.from_user and ctx.from_user.username else (ctx.from_user.first_name or ""))) if ctx.from_user else ""
                        fake_info = {"webpage_url": url}
                        caption = _build_caption(fake_info, 0, "tiktok", shared_by) or f"{E_SUCCESS} Tải từ TikTok"
                        await m.edit_msg(f"{E_UPD} Đang gửi{E_LOADING}")
                        imgs = [p for p in collected if p.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
                        videos = [p for p in collected if p.lower().endswith((".mp4", ".mov", ".webm"))]
                        if len(imgs) > 1:
                            jpegs = []
                            for p in imgs[:MAX_ALBUM_PHOTOS]:
                                b = await asyncio.to_thread(_image_to_jpeg_sync, p)
                                if b:
                                    jpegs.append(b)
                            if jpegs:
                                media_list = [
                                    InputMediaPhoto(media=io.BytesIO(jpegs[0]), caption=caption, parse_mode=enums.ParseMode.HTML),
                                    *[InputMediaPhoto(media=io.BytesIO(b)) for b in jpegs[1:]],
                                ]
                                await app.send_media_group(chat_id=ctx.chat.id, media=media_list, reply_to_message_id=ctx.id)
                        elif imgs:
                            b = await asyncio.to_thread(_image_to_jpeg_sync, imgs[0])
                            await ctx.reply_photo(photo=io.BytesIO(b) if b else imgs[0], caption=caption, parse_mode=enums.ParseMode.HTML)
                        elif videos:
                            await ctx.reply_video(video=videos[0], caption=caption, parse_mode=enums.ParseMode.HTML)
                        await m.delete()
                        if ctx.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                            try:
                                await app.delete_messages(ctx.chat.id, ctx.id)
                            except Exception:
                                pass
                        try:
                            for f in os.listdir(out_dir):
                                p = os.path.join(out_dir, f)
                                if os.path.isfile(p):
                                    os.remove(p)
                            os.rmdir(out_dir)
                        except OSError:
                            pass
                        return
                except Exception as e:
                    LOGGER.warning("Cobalt picker: %s", e)
        if data and data.get("status") in ("tunnel", "redirect"):
            download_url = (data.get("url") or "").strip()
            if download_url:
                shared_by = ""
                if ctx.from_user:
                    shared_by = ctx.from_user.mention or (f"@{ctx.from_user.username}" if ctx.from_user.username else ctx.from_user.first_name or "")
                fake_info = {"webpage_url": url}
                caption = _build_caption(fake_info, 0, "tiktok", shared_by) or f"{E_SUCCESS} Tải từ TikTok"
                try:
                    if download_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        await ctx.reply_photo(
                            photo=download_url,
                            caption=caption,
                            parse_mode=enums.ParseMode.HTML,
                        )
                    else:
                        timeout = aiohttp.ClientTimeout(total=60)
                        async with aiohttp.ClientSession(timeout=timeout) as session:
                            async with session.get(download_url) as resp_file:
                                if resp_file.status != 200:
                                    raise ValueError(f"HTTP {resp_file.status}")
                                file_bytes = await resp_file.read()
                        if len(file_bytes) > MAX_FILE_SIZE:
                            await m.edit_msg(
                                f"{E_ERROR} File quá lớn ({humanbytes(len(file_bytes))}). Giới hạn {humanbytes(MAX_FILE_SIZE)}."
                            )
                            return
                        await m.edit_msg(f"{E_UPD} Đang gửi{E_LOADING}")
                        await ctx.reply_video(
                            video=io.BytesIO(file_bytes),
                            caption=caption,
                            parse_mode=enums.ParseMode.HTML,
                            supports_streaming=True,
                        )
                    await m.delete()
                    if ctx.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                        try:
                            await app.delete_messages(ctx.chat.id, ctx.id)
                        except Exception:
                            pass
                    return
                except Exception as e:
                    LOGGER.warning("Cobalt send media: %s", e)
                    # Fall through to yt-dlp / scrape

    is_photo, final_url = await _resolve_tiktok_photo(url)
    if platform == "tiktok" and is_photo and final_url:
        # Tải ảnh TikTok: ưu tiên gallery-dl → TikWM → scrape og:image
        dl_root = ROOT_DIR / "downloads"
        dl_root.mkdir(parents=True, exist_ok=True)
        out_dir = tempfile.mkdtemp(prefix="tiktok_photo_", dir=str(dl_root))
        try:
            paths, err = None, None
            photo_meta = None  # metadata cho caption (giống video: title, author, like, view)
            paths_gd, err_gd = await asyncio.to_thread(_download_images_gallery_dl_sync, url, out_dir)
            if paths_gd:
                paths = paths_gd
            if not paths:
                paths_tikwm, meta_tikwm, err_tikwm = await _download_tiktok_via_tikwm(url, out_dir)
                if paths_tikwm:
                    paths = paths_tikwm
                    photo_meta = meta_tikwm
            if not paths:
                paths, err = await _download_tiktok_photo(final_url, out_dir)
            if err:
                return await m.edit_msg(f"{E_ERROR} {err}")
            if not paths:
                return await m.edit_msg(f"{E_ERROR} Không tải được ảnh.")
            total_size = sum(os.path.getsize(p) for p in paths)
            if total_size > MAX_FILE_SIZE:
                for p in paths:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
                return await m.edit_msg(
                    f"{E_ERROR} Tổng dung lượng quá lớn ({humanbytes(total_size)}). Giới hạn {humanbytes(MAX_FILE_SIZE)}."
                )
            await m.edit_msg(f"{E_UPD} Đang gửi{E_LOADING}")
            shared_by = ""
            if ctx.from_user:
                shared_by = ctx.from_user.mention or (f"@{ctx.from_user.username}" if ctx.from_user.username else ctx.from_user.first_name or "")
            # Caption đầy đủ như video: tiêu đề, tài khoản, số tim, số view, link
            if not photo_meta:
                data_tikwm = await _fetch_tikwm_tiktok(url)
                if data_tikwm:
                    author = data_tikwm.get("author") or {}
                    uploader = author.get("unique_id") or author.get("nickname") or "TikTok" if isinstance(author, dict) else str(author)
                    photo_meta = {
                        "title": (data_tikwm.get("title") or "").strip()[:200],
                        "uploader": uploader,
                        "webpage_url": url,
                        "like_count": data_tikwm.get("digg_count") or data_tikwm.get("like_count"),
                        "view_count": data_tikwm.get("play_count") or data_tikwm.get("view_count"),
                    }
            info = photo_meta if photo_meta else ({"webpage_url": final_url} if final_url else None)
            caption = _build_caption(info, os.path.getsize(paths[0]), "tiktok", shared_by) or f"{E_SUCCESS} Tải từ TikTok"
            # Chuyển sang JPEG trước khi gửi để tránh Telegram IMAGE_PROCESS_FAILED
            jpeg_list: list[bytes] = []
            for p in paths[:MAX_ALBUM_PHOTOS]:  # Telegram tối đa 10 ảnh/album
                b = await asyncio.to_thread(_image_to_jpeg_sync, p)
                if b and len(b) <= MAX_FILE_SIZE:
                    jpeg_list.append(b)
            if not jpeg_list and paths:
                one = await asyncio.to_thread(_image_to_jpeg_sync, paths[0])
                if one and len(one) <= MAX_FILE_SIZE:
                    jpeg_list = [one]
            # Fallback: đọc file gốc rồi convert sang JPEG (tránh PHOTO_EXT_INVALID khi nội dung là WebP/PNG)
            if not jpeg_list and paths:
                for p in paths[:MAX_ALBUM_PHOTOS]:
                    if not os.path.isfile(p) or os.path.getsize(p) == 0:
                        continue
                    try:
                        with open(p, "rb") as f:
                            raw = f.read()
                        b = await asyncio.to_thread(_image_bytes_to_jpeg_sync, raw)
                        if b and len(b) <= MAX_FILE_SIZE:
                            jpeg_list.append(b)
                    except Exception:
                        continue
            if not jpeg_list and paths:
                one_raw = None
                try:
                    with open(paths[0], "rb") as f:
                        one_raw = f.read()
                    if one_raw:
                        one = await asyncio.to_thread(_image_bytes_to_jpeg_sync, one_raw)
                        if one and len(one) <= MAX_FILE_SIZE:
                            jpeg_list = [one]
                except Exception:
                    pass
            if not jpeg_list:
                return await m.edit_msg(f"{E_ERROR} Ảnh không hợp lệ hoặc không xử lý được.")
            if len(jpeg_list) > 1:
                jpeg_list = jpeg_list[:MAX_ALBUM_PHOTOS]
                media_list = [
                    InputMediaPhoto(media=io.BytesIO(jpeg_list[0]), caption=caption, parse_mode=enums.ParseMode.HTML),
                    *[InputMediaPhoto(media=io.BytesIO(b)) for b in jpeg_list[1:]],
                ]
                await app.send_media_group(chat_id=ctx.chat.id, media=media_list, reply_to_message_id=ctx.id)
            else:
                await ctx.reply_photo(photo=io.BytesIO(jpeg_list[0]), caption=caption, parse_mode=enums.ParseMode.HTML)
            await m.delete()
            if ctx.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                try:
                    await app.delete_messages(ctx.chat.id, ctx.id)
                except Exception:
                    pass
        except Exception as e:
            LOGGER.exception("downloadsVideo photo: %s", e)
            await m.edit_msg(f"{E_ERROR} Lỗi: {_strip_ansi(str(e))[:150]}")
        finally:
            try:
                for f in os.listdir(out_dir):
                    p = os.path.join(out_dir, f)
                    if os.path.isfile(p):
                        os.remove(p)
                os.rmdir(out_dir)
            except OSError:
                pass
        return
    dl_root = ROOT_DIR / "downloads"
    dl_root.mkdir(parents=True, exist_ok=True)
    out_dir = tempfile.mkdtemp(prefix=f"{platform}_", dir=str(dl_root))
    try:
        paths, err, info = await asyncio.to_thread(_download_sync, url, out_dir)
        # TikTok: fallback TikWM khi yt-dlp thất bại (theo ytttins_dl)
        if (err or not paths) and platform == "tiktok":
            paths_tikwm, info_tikwm, err_tikwm = await _download_tiktok_via_tikwm(url, out_dir)
            if paths_tikwm and not err_tikwm:
                paths, err, info = paths_tikwm, None, info_tikwm or info
        # X (Twitter): tweet chỉ ảnh thì yt-dlp báo "No video could be found" — fallback gallery-dl
        if (err or not paths) and platform == "x":
            try:
                for f in os.listdir(out_dir):
                    p = os.path.join(out_dir, f)
                    if os.path.isfile(p):
                        os.remove(p)
            except OSError:
                pass
            paths_gd, err_gd = await asyncio.to_thread(_download_x_gallery_dl_sync, url, out_dir)
            if paths_gd:
                info_x = await asyncio.to_thread(_extract_x_metadata_sync, url)
                if not info_x or (not info_x.get("title") and not info_x.get("uploader")):
                    info_x = await asyncio.to_thread(_fetch_x_metadata_from_html_sync, url)
                info = info_x or {}
                if not info.get("webpage_url"):
                    info["webpage_url"] = url if (url or "").strip().startswith("http") else "https://" + (url or "").strip()
                paths, err = paths_gd, None
            elif err:
                err = f"X: {err[:150]}"
        # Instagram: thử instagrapi (đăng nhập) rồi gallery-dl
        if (err or not paths) and platform == "instagram":
            paths_ig, err_ig, info_ig = await asyncio.to_thread(_download_instagram_instagrapi_sync, url, out_dir)
            if paths_ig:
                paths, err, info = paths_ig, None, (info_ig or {})
            else:
                paths_gd, err_gd = await asyncio.to_thread(_download_images_gallery_dl_sync, url, out_dir)
                if paths_gd:
                    paths, err, info = paths_gd, None, {}
                else:
                    err = f"Instagram: {err_gd or err_ig or err}"
        if err:
            return await m.edit_msg(f"{E_ERROR} {err}")

        if not paths:
            return await m.edit_msg(f"{E_ERROR} Tải thất bại.")

        total_size = sum(os.path.getsize(p) for p in paths if os.path.isfile(p))
        if total_size > MAX_FILE_SIZE:
            for p in paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
            return await m.edit_msg(
                f"{E_ERROR} Tổng dung lượng quá lớn ({humanbytes(total_size)}). Giới hạn {humanbytes(MAX_FILE_SIZE)}."
            )

        images, videos, other = _paths_by_type(paths)
        await m.edit_msg(f"{E_UPD} Đang gửi{E_LOADING}")

        shared_by = ""
        if ctx.from_user:
            shared_by = ctx.from_user.mention or (f"@{ctx.from_user.username}" if ctx.from_user.username else ctx.from_user.first_name or "")
        first_size = os.path.getsize(paths[0]) if paths else 0
        caption = _build_caption(info, first_size, platform, shared_by) or f"{E_SUCCESS} Tải từ {platform.title()}"

        # Nhiều ảnh → gửi album (media group, tối đa 10 ảnh). Chuyển sang JPEG tránh PHOTO_EXT_INVALID (WebP/PNG).
        if len(images) > 1:
            images = images[:MAX_ALBUM_PHOTOS]
            jpeg_list: list[bytes] = []
            for p in images:
                b = await asyncio.to_thread(_image_to_jpeg_sync, p)
                if b and len(b) <= MAX_FILE_SIZE:
                    jpeg_list.append(b)
                elif os.path.isfile(p) and os.path.getsize(p) > 0:
                    try:
                        with open(p, "rb") as f:
                            raw = f.read()
                        b = await asyncio.to_thread(_image_bytes_to_jpeg_sync, raw)
                        if b and len(b) <= MAX_FILE_SIZE:
                            jpeg_list.append(b)
                    except Exception:
                        pass
            if not jpeg_list and images:
                one = await asyncio.to_thread(_image_to_jpeg_sync, images[0])
                if one and len(one) <= MAX_FILE_SIZE:
                    jpeg_list.append(one)
            if jpeg_list:
                media_list = [
                    InputMediaPhoto(media=io.BytesIO(jpeg_list[0]), caption=caption, parse_mode=enums.ParseMode.HTML),
                    *[InputMediaPhoto(media=io.BytesIO(b)) for b in jpeg_list[1:]],
                ]
                await app.send_media_group(
                    chat_id=ctx.chat.id,
                    media=media_list,
                    reply_to_message_id=ctx.id,
                )
            else:
                # Fallback: gửi ảnh đầu dưới dạng document nếu convert thất bại
                await ctx.reply_document(document=images[0], caption=caption, parse_mode=enums.ParseMode.HTML)
        # Một ảnh — chuyển sang JPEG tránh PHOTO_EXT_INVALID
        elif len(images) == 1:
            p = images[0]
            jpeg_bytes = await asyncio.to_thread(_image_to_jpeg_sync, p)
            if not jpeg_bytes and os.path.isfile(p) and os.path.getsize(p) > 0:
                try:
                    with open(p, "rb") as f:
                        jpeg_bytes = await asyncio.to_thread(_image_bytes_to_jpeg_sync, f.read())
                except Exception:
                    pass
            if jpeg_bytes and len(jpeg_bytes) <= MAX_FILE_SIZE:
                await ctx.reply_photo(photo=io.BytesIO(jpeg_bytes), caption=caption, parse_mode=enums.ParseMode.HTML)
            else:
                await ctx.reply_photo(photo=p, caption=caption, parse_mode=enums.ParseMode.HTML)
        # Một video (ưu tiên nếu có cả video và ảnh)
        elif videos:
            await ctx.reply_video(video=videos[0], caption=caption, parse_mode=enums.ParseMode.HTML)
        # File khác (document)
        elif other:
            await ctx.reply_document(document=other[0], caption=caption, parse_mode=enums.ParseMode.HTML)
        else:
            await m.edit_msg(f"{E_ERROR} Không có file media hợp lệ.")
            return

        await m.delete()
        # Khi user nhắn riêng (PM): gửi bản sao kết quả vào LOG_CHANNEL để admin xem
        await _send_result_to_log_channel(ctx, platform, caption, images, videos, other)
        # Xóa tin nhắn chứa link sau khi bot đã gửi media thành công
        if ctx.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            try:
                await app.delete_messages(ctx.chat.id, ctx.id)
            except Exception:
                pass
    except Exception as e:
        LOGGER.exception("downloadsVideo error: %s", e)
        await m.edit_msg(f"{E_ERROR} Lỗi: {_strip_ansi(str(e))[:150]}")
    finally:
        try:
            for f in os.listdir(out_dir):
                p = os.path.join(out_dir, f)
                if os.path.isfile(p):
                    os.remove(p)
            os.rmdir(out_dir)
        except OSError:
            pass


# --- Tự động nhận diện link (không cần lệnh) ---
def _has_supported_link(_, __, msg: Message) -> bool:
    if msg.from_user and getattr(msg.from_user, "is_bot", False):
        return False
    text = (msg.text or msg.caption or "").strip()
    if not text or _is_command_message(text):
        return False
    return _extract_supported_url(text) is not None


filters_has_link = filters.create(_has_supported_link)


# Khi mention bot + link: luôn xử lý (hoạt động cả khi Group Privacy bật)
@app.on_message((filters.text | filters.caption) & filters.mentioned & filters_has_link, group=0)
@capture_err
@new_task
async def auto_download_mentioned(_, ctx: Message):
    """Khi user @mention bot kèm link - luôn tải (không cần autodl)."""
    text = (ctx.text or ctx.caption or "").strip()
    result = _extract_supported_url(text)
    if not result:
        return
    url, platform = result
    await _process_download(ctx, url, platform)


@app.on_message(
    (filters.text | filters.caption) & filters_has_link & (filters.group | filters.private),
    group=-1,
)
@capture_err
@new_task
async def auto_download_link(_, ctx: Message):
    """Tự động tải khi tin nhắn chứa link."""
    text = (ctx.text or ctx.caption or "").strip()
    result = _extract_supported_url(text)
    if not result:
        return
    url, platform = result
    LOGGER.info("auto_download_link: chat=%s url=%s", ctx.chat.id, url[:60])
    await _process_download(ctx, url, platform)


# --- Bật/tắt tự động nhận link trong nhóm ---
@app.on_message(filters.command("autodl", COMMAND_HANDLER) & filters.group)
@require_admin()
@capture_err
async def cmd_autodl_toggle(_, ctx: Message):
    """Bật/tắt tự động tải link trong nhóm."""
    enabled = await toggle_autodl(ctx.chat.id)
    status = "bật" if enabled else "tắt"
    msg = f"{E_SUCCESS} Đã {status} tự động nhận link trong nhóm này."
    if enabled:
        msg += (
            "\n\n{E_TIP} Nếu gửi link mà bot không phản hồi:\n"
            "• Cấp quyền Admin cho bot trong nhóm (bot admin sẽ nhận mọi tin nhắn)\n"
            "• Hoặc dùng <code>/dl</code> + link hoặc @mention bot + link"
        )
    await ctx.reply_msg(msg.format(E_TIP=E_TIP), parse_mode=enums.ParseMode.HTML)


# --- Lệnh (tùy chọn) ---
@app.on_message(
    filters.command(["dl", "tt", "tiktok"], COMMAND_HANDLER)
    & (filters.reply | filters.text)
)
@capture_err
@new_task
async def cmd_download(_, ctx: Message):
    """Lệnh /dl, /tt, /tiktok [link] hoặc trả lời tin có link."""
    url, platform = None, None
    if ctx.reply_to_message:
        text = ctx.reply_to_message.text or ctx.reply_to_message.caption or ""
        result = _extract_supported_url(text)
        if result:
            url, platform = result
    if not url and ctx.text:
        parts = ctx.text.split(maxsplit=1)
        if len(parts) >= 2:
            result = _extract_supported_url(parts[1])
            if result:
                url, platform = result

    if not url:
        return await ctx.reply_msg(
            f"{E_ERROR} Gửi link hoặc trả lời tin có link.\nVí dụ: <code>/dl https://vm.tiktok.com/xxx</code> hoặc link X/Facebook/Instagram.",
            parse_mode=enums.ParseMode.HTML,
        )
    await _process_download(ctx, url, platform)
