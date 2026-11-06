# Gửi vào LOG_CHANNEL khi user dùng lệnh (/, !) hoặc gửi video/ảnh — User và Chat mỗi cái 1 dòng

import html
import os
from logging import getLogger

from pyrogram import filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import BadRequest, Forbidden

from dorasuper import app
from dorasuper.emoji import E_MSG, E_USER
from dorasuper.vars import LOG_CHANNEL, COMMAND_HANDLER, SUDO
from dorasuper.log_topics import topic_id

LOGGER = getLogger("DoraSuper")
__MODULE__ = "LogAdmin"
__HELP__ = """[Nội bộ] Gửi lệnh (/, !) hoặc video/ảnh → log vào LOG_CHANNEL (User + Chat mỗi cái 1 dòng)."""


def _is_command_message(text: str) -> bool:
    """True nếu tin nhắn là lệnh (bắt đầu bằng prefix / hoặc ! và có tên lệnh)."""
    if not text or not text.strip():
        return False
    t = text.strip()
    prefixes = tuple(COMMAND_HANDLER) if COMMAND_HANDLER else ("/", "!")
    if not t.startswith(prefixes):
        return False
    # Có ít nhất 1 ký tự sau prefix (tên lệnh)
    return len(t) > 1 and (t[1].isalnum() or t[1] in ("_",))


def _is_media_message(message) -> bool:
    """True nếu tin có ảnh / video / video_note cần chuyển file thật vào log."""
    return bool(getattr(message, "photo", None) or getattr(message, "video", None) or getattr(message, "video_note", None))


def _media_topic_key(message) -> str:
    """photos | videos — video_note đi vào tab video."""
    if getattr(message, "video", None) or getattr(message, "video_note", None):
        return "videos"
    return "photos"


def _build_user_chat_caption(message, text: str) -> str:
    """Caption HTML User + Chat (+ caption gốc nếu còn chỗ). Giới hạn ~1024."""
    user = message.from_user
    name = (user.first_name or "") + (" " + (user.last_name or "")).strip()
    name = html.escape(name) or "N/A"
    username = (user.username and f"@{user.username}") or "—"
    uid = user.id

    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        chat_name = html.escape(message.chat.title or "Nhóm")
        chat_info = f"{chat_name} (<code>{message.chat.id}</code>)"
    else:
        chat_info = "Riêng tư (PM)"

    cap = (
        f"{E_USER} <b>User:</b> {name} | {username} | <code>{uid}</code>\n"
        f"{E_MSG} <b>Chat:</b> {chat_info}"
    )
    if text:
        # Caption media giới hạn 1024; giữ an toàn bằng cách cắt ngắn
        extra = html.escape(text)
        remaining = 950 - len(cap)
        if remaining > 20:
            extra = extra[:remaining]
            cap += f"\n\n<blockquote>{extra}</blockquote>"
    # Soft cap for Telegram caption limit
    if len(cap) > 1024:
        cap = cap[:1021] + "..."
    return cap


async def _send_media_to_log(message, cap: str) -> None:
    """Gửi ảnh/video thật vào LOG_CHANNEL topic phù hợp.

    Thứ tự: message.copy → send_photo/send_video(file_id) → download + upload.
    Không bao giờ thay media bằng text-only "📷 Ảnh" / "🎬 Video".
    """
    _thread = topic_id(_media_topic_key(message))
    send_errs: list[str] = []

    # 1) Prefer copy (giữ nguyên file, kèm caption)
    try:
        await message.copy(
            LOG_CHANNEL,
            caption=cap,
            parse_mode=ParseMode.HTML,
            message_thread_id=_thread,
        )
        return
    except (BadRequest, Forbidden) as e:
        send_errs.append(f"copy+caption: {e}")
        try:
            await message.copy(LOG_CHANNEL, message_thread_id=_thread)
            return
        except (BadRequest, Forbidden) as e2:
            send_errs.append(f"copy: {e2}")

    # 2) Same-bot file_id reuse
    try:
        if message.photo:
            file_id = message.photo.file_id
            await app.send_photo(
                LOG_CHANNEL,
                photo=file_id,
                caption=cap,
                parse_mode=ParseMode.HTML,
                message_thread_id=_thread,
            )
            return
        if message.video:
            file_id = message.video.file_id
            await app.send_video(
                LOG_CHANNEL,
                video=file_id,
                caption=cap,
                parse_mode=ParseMode.HTML,
                message_thread_id=_thread,
            )
            return
        if message.video_note:
            # video_note không có caption trên Telegram; gửi note rồi caption riêng nếu cần
            await app.send_video_note(
                LOG_CHANNEL,
                video_note=message.video_note.file_id,
                message_thread_id=_thread,
            )
            if cap:
                try:
                    await app.send_message(
                        LOG_CHANNEL,
                        cap,
                        parse_mode=ParseMode.HTML,
                        message_thread_id=_thread,
                    )
                except (BadRequest, Forbidden):
                    pass
            return
    except (BadRequest, Forbidden) as e:
        send_errs.append(f"file_id: {e}")

    # 3) Last resort: download then upload
    path = None
    try:
        path = await message.download()
        if not path:
            raise RuntimeError("download returned empty path")
        if message.photo:
            await app.send_photo(
                LOG_CHANNEL,
                photo=path,
                caption=cap,
                parse_mode=ParseMode.HTML,
                message_thread_id=_thread,
            )
        elif message.video:
            await app.send_video(
                LOG_CHANNEL,
                video=path,
                caption=cap,
                parse_mode=ParseMode.HTML,
                message_thread_id=_thread,
            )
        elif message.video_note:
            await app.send_video_note(
                LOG_CHANNEL,
                video_note=path,
                message_thread_id=_thread,
            )
            if cap:
                try:
                    await app.send_message(
                        LOG_CHANNEL,
                        cap,
                        parse_mode=ParseMode.HTML,
                        message_thread_id=_thread,
                    )
                except (BadRequest, Forbidden):
                    pass
        else:
            raise RuntimeError("no photo/video/video_note after download")
        return
    except Exception as e:
        send_errs.append(f"download_upload: {e}")
        LOGGER.warning(
            "admin_log_messages: failed to deliver media to LOG_CHANNEL (%s)",
            " | ".join(send_errs),
        )
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


@app.on_message(
    filters.incoming
    & ~filters.service
    & (filters.private | filters.group),
    group=1,
)
async def log_user_message_to_admin(_, message):
    """Gửi vào LOG_CHANNEL khi user dùng lệnh hoặc gửi video/ảnh. User và Chat mỗi cái 1 dòng."""
    if not LOG_CHANNEL:
        return
    if message.chat and message.chat.id == LOG_CHANNEL:
        return
    if not message.from_user or getattr(message.from_user, "is_bot", False):
        return
    if message.from_user.id == getattr(app.me, "id", None):
        return
    if message.from_user.id in SUDO:
        return
    text = (message.text or message.caption or "").strip()
    is_cmd = _is_command_message(text)
    is_media = _is_media_message(message)
    if not is_cmd and not is_media:
        return
    try:
        if is_media:
            cap = _build_user_chat_caption(message, text)
            await _send_media_to_log(message, cap)
            return

        # Chỉ còn lệnh không kèm media → text vào tab commands
        content = html.escape(text) if text else "(không có nội dung)"
        user = message.from_user
        name = (user.first_name or "") + (" " + (user.last_name or "")).strip()
        name = html.escape(name) or "N/A"
        username = (user.username and f"@{user.username}") or "—"
        uid = user.id
        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            chat_name = html.escape(message.chat.title or "Nhóm")
            chat_info = f"{chat_name} (<code>{message.chat.id}</code>)"
        else:
            chat_info = "Riêng tư (PM)"

        body = (
            f"{E_USER} <b>User:</b> {name} | {username} | <code>{uid}</code>\n"
            f"{E_MSG} <b>Chat:</b> {chat_info}\n\n"
            f"<blockquote>{content}</blockquote>"
        )
        await app.send_message(
            LOG_CHANNEL,
            body,
            parse_mode=ParseMode.HTML,
            message_thread_id=topic_id("commands"),
        )
    except (BadRequest, Forbidden) as e:
        # MessageIdInvalid có thể xảy ra nếu tin đã bị xóa (vd: delete_command_msg) trước khi gửi
        if "MESSAGE_ID_INVALID" not in str(e):
            LOGGER.warning("admin_log_messages BadRequest/Forbidden: %s", e)
    except Exception as e:
        LOGGER.exception("admin_log_messages: %s", e)
