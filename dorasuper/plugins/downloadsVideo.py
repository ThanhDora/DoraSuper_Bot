# Tải video/ảnh từ TikTok và các mạng xã hội khác (yt-dlp)
# Bot tự nhận diện link trong tin nhắn, không cần lệnh

import asyncio
import html
import os
import re
import tempfile
from logging import getLogger

import yt_dlp
from pyrogram import enums, filters
from pyrogram.enums import ChatType
from pyrogram.types import Message

from dorasuper import app
from dorasuper.core.decorator import capture_err, new_task
from dorasuper.core.decorator.permissions import require_admin
from database.autodl_db import toggle_autodl
from dorasuper.emoji import E_ERROR, E_HEART, E_LINK, E_LOADING, E_MUSIC, E_SUCCESS, E_TIP, E_USER
from dorasuper.helper.pyro_progress import humanbytes
from dorasuper.vars import COMMAND_HANDLER, ROOT_DIR

LOGGER = getLogger("DoraSuper")

__MODULE__ = "TảiVideo"
__HELP__ = """
<blockquote>Gửi link TikTok - Bot tự tải và gửi video/ảnh.

Lệnh:
/autodl - Bật/tắt tự động tải link trong nhóm (admin)
/dl [link] - Tải ngay (dùng khi autodl tắt hoặc cần tải thủ công)</blockquote>
"""

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Regex theo từng nền tảng (dễ mở rộng thêm Instagram, YouTube, ...)
URL_PATTERNS = {
    "tiktok": re.compile(
        r"(?:https?://)?(?:www\.|vm\.|vt\.|m\.|t\.)?(?:tiktok\.com|tiktokv\.com)/[^\s]+",
        re.IGNORECASE,
    ),
    # Thêm sau: "instagram": ..., "youtube": ...
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


def _download_sync(url: str, out_dir: str) -> tuple[str | None, str | None, dict | None]:
    """Tải bằng yt-dlp. Returns (filepath, error, info_dict)."""
    out_tpl = os.path.join(out_dir, "%(id)s.%(ext)s")
    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": out_tpl,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None, "Không lấy được thông tin.", None
            filepath = ydl.prepare_filename(info)
            if os.path.exists(filepath):
                return filepath, None, info
            base = os.path.splitext(filepath)[0]
            for ext in (".mp4", ".webm", ".mkv", ".mov", ".m4a", ".jpg", ".jpeg", ".png", ".webp", ".gif"):
                p = base + ext
                if os.path.exists(p):
                    return p, None, info
            return None, "Không tìm thấy file tải về.", None
    except yt_dlp.utils.DownloadError as e:
        err = _strip_ansi(str(e))
        if "private" in err.lower():
            return None, "Video riêng tư, không tải được.", None
        if "region" in err.lower() or "blocked" in err.lower():
            return None, "Video bị giới hạn theo khu vực.", None
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
    """Tạo caption: tên tài khoản, user (copy), số tim, số view, link TikTok (blockquote)."""
    lines = []
    if info:
        # Tên tài khoản TikTok
        uploader = (info.get("uploader") or info.get("creator") or "").strip()
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
            lines.append(f"<b>Số view:</b> {_fmt_count(views)}")
    # Link TikTok
    link = (info or {}).get("webpage_url") or (info or {}).get("url", "")
    if link:
        lines.append(f'<b>Link:</b> <a href="{html.escape(link)}">{html.escape(link)}</a>')
    if shared_by:
        lines.append(f"{E_USER} Chia sẻ bởi: {shared_by}")
    content = "\n".join(l for l in lines if l)
    return f"<blockquote>{content}</blockquote>" if content else ""


async def _process_download(ctx: Message, url: str, platform: str):
    """Xử lý tải và gửi media."""
    m = await ctx.reply_msg(f"{E_LOADING} Đang tải từ {platform}...", quote=True)
    dl_root = ROOT_DIR / "downloads"
    dl_root.mkdir(parents=True, exist_ok=True)
    out_dir = tempfile.mkdtemp(prefix=f"{platform}_", dir=str(dl_root))
    try:
        filepath, err, info = await asyncio.to_thread(_download_sync, url, out_dir)
        if err:
            return await m.edit_msg(f"{E_ERROR} {err}")

        if not filepath or not os.path.exists(filepath):
            return await m.edit_msg(f"{E_ERROR} Tải thất bại.")

        size = os.path.getsize(filepath)
        if size > MAX_FILE_SIZE:
            try:
                os.remove(filepath)
            except OSError:
                pass
            return await m.edit_msg(
                f"{E_ERROR} File quá lớn ({humanbytes(size)}). Giới hạn {humanbytes(MAX_FILE_SIZE)}."
            )

        ext = os.path.splitext(filepath)[1].lower()
        is_image = ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")
        is_video = ext in (".mp4", ".webm", ".mkv", ".mov")

        await m.edit_msg(f"{E_LOADING} Đang gửi...")

        shared_by = ""
        if ctx.from_user:
            shared_by = ctx.from_user.mention or (f"@{ctx.from_user.username}" if ctx.from_user.username else ctx.from_user.first_name or "")
        caption = _build_caption(info, size, platform, shared_by) or f"{E_SUCCESS} Tải từ {platform.title()}"
        if is_image:
            await ctx.reply_photo(photo=filepath, caption=caption, parse_mode=enums.ParseMode.HTML)
        elif is_video:
            await ctx.reply_video(video=filepath, caption=caption, parse_mode=enums.ParseMode.HTML)
        else:
            await ctx.reply_document(document=filepath, caption=caption, parse_mode=enums.ParseMode.HTML)
        await m.delete()
        # Xóa tin nhắn chứa link (chỉ trong nhóm, cần quyền xóa tin nhắn)
        if ctx.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            try:
                await ctx.delete()
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
            f"{E_ERROR} Gửi link hoặc trả lời tin có link.\nVí dụ: <code>/dl https://vm.tiktok.com/xxx</code>",
            parse_mode=enums.ParseMode.HTML,
        )
    await _process_download(ctx, url, platform)
