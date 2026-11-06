import asyncio
import io
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.types import Message

from database.media_gen_db import add_video_used, get_video_used
from dorasuper import app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.emoji import E_ERROR, E_MOVIE, E_SUCCESS, E_WAIT, E_WARN
from dorasuper.helper.grok_imagine import (
    GrokImagineClient, GrokVideoError, friendly_grok_message, sanitize_error,
)
from dorasuper.helper.yeta_media import VIDEO_DAILY_LIMIT, is_private_chat, remaining_videos
from dorasuper.vars import (
    AI_API_KEY, COMMAND_HANDLER, GROK_VIDEO_DURATION, GROK_VIDEO_MODEL, GROK_VIDEO_RESOLUTION,
)

LOGGER = getLogger("DoraSuper")

__MODULE__ = "TạoVideo"
__HELP__ = f"""
{E_MOVIE} <b>Tạo video bằng Grok Imagine</b> (chỉ dùng khi nhắn riêng với bot)

/taovideo nội dung cần tạo – Tạo video ngắn từ mô tả.

{E_WARN} Mỗi người được tạo tối đa {VIDEO_DAILY_LIMIT} video mỗi ngày (tính theo giờ Việt Nam).
"""

_video_locks: set[int] = set()
_PM_ONLY = f"{E_WARN} Lệnh này chỉ dùng được khi anh/chị nhắn riêng với bot. Anh/chị vui lòng mở chat riêng với bot rồi thử lại nhé."
_NOT_CONFIGURED = f"{E_WARN} Tính năng tạo video chưa được thiết lập. Anh/chị vui lòng liên hệ quản trị viên bot nhé."
_IMAGE_REMOVED = f"{E_WARN} Lệnh tạo ảnh đã tắt. Anh/chị dùng <code>/taovideo nội dung cần tạo</code> để tạo video nhé."


def _client():
    return GrokImagineClient(AI_API_KEY)


def _prompt(ctx: Message) -> str:
    parts = (ctx.text or "").split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""


async def _precheck(ctx: Message, usage: str):
    if not is_private_chat(ctx.chat.type):
        await ctx.reply_msg(_PM_ONLY, quote=True, parse_mode=enums.ParseMode.HTML)
        return None
    if not AI_API_KEY:
        await ctx.reply_msg(_NOT_CONFIGURED, quote=True, parse_mode=enums.ParseMode.HTML)
        return None
    prompt = _prompt(ctx)
    if not prompt:
        await ctx.reply_msg(
            f"{E_WARN} Anh/chị vui lòng nhập nội dung muốn tạo.\nCách dùng: <code>{usage} nội dung cần tạo</code>",
            quote=True, parse_mode=enums.ParseMode.HTML)
        return None
    return prompt


def _err(e) -> str:
    raw = friendly_grok_message(e) if isinstance(e, GrokVideoError) else getattr(e, "message", e)
    return (
        f"{E_ERROR} Rất tiếc, chưa tạo được video: "
        f"<i>{sanitize_error(raw, AI_API_KEY)}</i>"
    )


@app.on_message(filters.command(["taoanh"], COMMAND_HANDLER))
@capture_err
async def taoanh_removed(_, ctx: Message):
    if not is_private_chat(ctx.chat.type):
        return await ctx.reply_msg(_PM_ONLY, quote=True, parse_mode=enums.ParseMode.HTML)
    await ctx.reply_msg(_IMAGE_REMOVED, quote=True, parse_mode=enums.ParseMode.HTML)


@app.on_message(filters.command(["taovideo"], COMMAND_HANDLER))
@capture_err
async def taovideo_cmd(_, ctx: Message):
    prompt = await _precheck(ctx, "/taovideo")
    if not prompt:
        return
    uid = ctx.from_user.id
    if uid in _video_locks:
        return await ctx.reply_msg(f"{E_WAIT} Anh/chị đang có một video đang tạo, vui lòng đợi video đó xong rồi tạo tiếp nhé.", quote=True, parse_mode=enums.ParseMode.HTML)
    _video_locks.add(uid)
    try:
        used = await get_video_used(uid)
        if remaining_videos(used) <= 0:
            return await ctx.reply_msg(
                f"{E_WARN} Hôm nay anh/chị đã dùng hết {VIDEO_DAILY_LIMIT} lượt tạo video. Anh/chị có thể thử lại sau 0 giờ (giờ Việt Nam) nhé.",
                quote=True, parse_mode=enums.ParseMode.HTML)
        msg = await ctx.reply_msg(f"{E_WAIT} Đang gửi yêu cầu tạo video...", quote=True, parse_mode=enums.ParseMode.HTML)
        client = _client()
        try:
            job = await client.submit_video(
                GROK_VIDEO_MODEL, prompt, GROK_VIDEO_DURATION, GROK_VIDEO_RESOLUTION)
        except Exception as e:
            LOGGER.warning("taovideo submit failed: %s", type(e).__name__)
            return await msg.edit_msg(_err(e if isinstance(e, GrokVideoError) else "Không kết nối được máy chủ."), parse_mode=enums.ParseMode.HTML)
        used = await add_video_used(uid)  # tính lượt khi job đã được nhận
        left = remaining_videos(used)
        await msg.edit_msg(
            f"{E_MOVIE} Đang tạo video bằng Grok Imagine, thường mất 1–5 phút. Anh/chị chờ em nhé...\nLượt còn lại hôm nay: <b>{left}/{VIDEO_DAILY_LIMIT}</b>",
            parse_mode=enums.ParseMode.HTML)
        try:
            done = await client.wait_video(job["id"])
        except asyncio.TimeoutError:
            return await msg.edit_msg(f"{E_WARN} Video tạo lâu hơn dự kiến nên em tạm dừng chờ. Anh/chị thử lại sau nhé.", parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            return await msg.edit_msg(_err(e if isinstance(e, GrokVideoError) else "Mất kết nối khi chờ video."), parse_mode=enums.ParseMode.HTML)
        cap = f"{E_SUCCESS} Video của anh/chị đã xong! Lượt còn lại hôm nay: {left}/{VIDEO_DAILY_LIMIT}"
        try:
            data = await client.download_url(done["url"])
            f = io.BytesIO(data)
            f.name = "taovideo.mp4"
            await ctx.reply_video(f, caption=cap, quote=True, parse_mode=enums.ParseMode.HTML)
        except Exception:
            if not done.get("url"):
                return await msg.edit_msg(_err("Không tải được video."), parse_mode=enums.ParseMode.HTML)
            try:
                await ctx.reply_video(done["url"], caption=cap, quote=True, parse_mode=enums.ParseMode.HTML)
            except Exception:
                return await msg.edit_msg(
                    f"{E_SUCCESS} Video đã xong, anh/chị tải tại đây (link tạm thời): {done['url']}",
                    parse_mode=enums.ParseMode.HTML)
        await msg.delete()
    finally:
        _video_locks.discard(uid)
