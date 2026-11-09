# Gửi vào LOG_CHANNEL khi user dùng lệnh, gửi ảnh/video, nhắn PM, hoặc gửi file trong nhóm.
# User + Chat mỗi cái 1 dòng. Không chặn handler khác (group=1, không StopPropagation).

import asyncio
import html
import os
from logging import getLogger

from pyrogram import filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import BadRequest, FloodWait, Forbidden

from dorasuper import app
from dorasuper.emoji import E_MSG, E_USER
from dorasuper.vars import COMMAND_HANDLER, LOG_CHANNEL, SUDO, UP_CHANNEL
from dorasuper.log_topics import topic_id

LOGGER = getLogger("DoraSuper")
__MODULE__ = "LogAdmin"
__HELP__ = (
    "[Nội bộ] Lệnh / ảnh / video → tab tương ứng; PM (mọi loại) → Tin nhắn riêng; "
    "file/audio/voice (PM + nhóm) → File; PM text/khác → Tin nhắn riêng."
)


def _is_command_message(text: str) -> bool:
    """True nếu tin nhắn là lệnh (bắt đầu bằng prefix / hoặc ! và có tên lệnh)."""
    if not text or not text.strip():
        return False
    t = text.strip()
    prefixes = tuple(COMMAND_HANDLER) if COMMAND_HANDLER else ("/", "!")
    if not t.startswith(prefixes):
        return False
    return len(t) > 1 and (t[1].isalnum() or t[1] in ("_",))


def _is_media_message(message) -> bool:
    """True nếu tin có ảnh / video / video_note (đã có tab riêng — tránh trùng)."""
    return bool(
        getattr(message, "photo", None)
        or getattr(message, "video", None)
        or getattr(message, "video_note", None)
    )


def _is_file_message(message) -> bool:
    """True nếu tin có document / audio / voice (file nhóm → tab File)."""
    return bool(
        getattr(message, "document", None)
        or getattr(message, "audio", None)
        or getattr(message, "voice", None)
    )


def _has_copyable_payload(message) -> bool:
    """True nếu tin mang media/file có thể copy sang LOG (không chỉ text)."""
    return bool(
        getattr(message, "photo", None)
        or getattr(message, "video", None)
        or getattr(message, "video_note", None)
        or getattr(message, "document", None)
        or getattr(message, "audio", None)
        or getattr(message, "voice", None)
        or getattr(message, "animation", None)
        or getattr(message, "sticker", None)
        or getattr(message, "video_note", None)
    )


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
        extra = html.escape(text)
        remaining = 950 - len(cap)
        if remaining > 20:
            extra = extra[:remaining]
            cap += f"\n\n<blockquote>{extra}</blockquote>"
    if len(cap) > 1024:
        cap = cap[:1021] + "..."
    return cap


def _build_text_log_body(message, text: str) -> str:
    """Body HTML đầy đủ cho tin text-only (hoặc fallback khi không copy được media)."""
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
    content = html.escape(text) if text else "(không có nội dung)"
    body = (
        f"{E_USER} <b>User:</b> {name} | {username} | <code>{uid}</code>\n"
        f"{E_MSG} <b>Chat:</b> {chat_info}\n\n"
        f"<blockquote>{content}</blockquote>"
    )
    if len(body) > 4000:
        body = body[:3997] + "..."
    return body


async def _resolve_up_channel_id():
    """Kênh đích /up — bỏ qua log từ đó. Ưu tiên DB, fallback UP_CHANNEL env."""
    try:
        from database.up_channel_db import get_up_channel
        saved = await get_up_channel()
        if saved is not None:
            return int(saved)
    except Exception:
        pass
    if UP_CHANNEL is None:
        return None
    try:
        return int(UP_CHANNEL)
    except (TypeError, ValueError):
        return None


async def _send_with_floodwait(coro_factory, *, attempts: int = 3):
    """Chạy coroutine; tôn trọng FloodWait ngắn, không để exception lan ra handler khác."""
    last = None
    for _ in range(attempts):
        try:
            return await coro_factory()
        except FloodWait as e:
            last = e
            wait = int(getattr(e, "value", 1) or 1)
            await asyncio.sleep(min(wait, 25) + 1)
    if last:
        raise last


async def _send_media_to_log(message, cap: str, topic_key: str | None = None) -> None:
    """Gửi media/file thật vào LOG_CHANNEL topic phù hợp.

    Thứ tự: message.copy → send_* (file_id) → download + upload.
    topic_key mặc định theo ảnh/video; truyền 'files' / 'pm' khi cần.
    """
    key = topic_key or _media_topic_key(message)
    _thread = topic_id(key)
    LOGGER.info("admin_log_messages: send key=%s thread_id=%s chat=%s", key, _thread, getattr(message.chat, "id", None))
    send_errs: list[str] = []

    # 1) Prefer copy
    try:
        await _send_with_floodwait(
            lambda: message.copy(
                LOG_CHANNEL,
                caption=cap,
                parse_mode=ParseMode.HTML,
                message_thread_id=_thread,
            )
        )
        return
    except (BadRequest, Forbidden) as e:
        send_errs.append(f"copy+caption: {e}")
        try:
            await _send_with_floodwait(
                lambda: message.copy(LOG_CHANNEL, message_thread_id=_thread)
            )
            return
        except (BadRequest, Forbidden) as e2:
            send_errs.append(f"copy: {e2}")
    except FloodWait as e:
        send_errs.append(f"copy FloodWait: {e}")

    # 2) Same-bot file_id reuse
    try:
        if message.photo:
            await _send_with_floodwait(
                lambda: app.send_photo(
                    LOG_CHANNEL,
                    photo=message.photo.file_id,
                    caption=cap,
                    parse_mode=ParseMode.HTML,
                    message_thread_id=_thread,
                )
            )
            return
        if message.video:
            await _send_with_floodwait(
                lambda: app.send_video(
                    LOG_CHANNEL,
                    video=message.video.file_id,
                    caption=cap,
                    parse_mode=ParseMode.HTML,
                    message_thread_id=_thread,
                )
            )
            return
        if message.video_note:
            await _send_with_floodwait(
                lambda: app.send_video_note(
                    LOG_CHANNEL,
                    video_note=message.video_note.file_id,
                    message_thread_id=_thread,
                )
            )
            if cap:
                try:
                    await _send_with_floodwait(
                        lambda: app.send_message(
                            LOG_CHANNEL,
                            cap,
                            parse_mode=ParseMode.HTML,
                            message_thread_id=_thread,
                        )
                    )
                except (BadRequest, Forbidden, FloodWait):
                    pass
            return
        if message.document:
            await _send_with_floodwait(
                lambda: app.send_document(
                    LOG_CHANNEL,
                    document=message.document.file_id,
                    caption=cap,
                    parse_mode=ParseMode.HTML,
                    message_thread_id=_thread,
                )
            )
            return
        if message.audio:
            await _send_with_floodwait(
                lambda: app.send_audio(
                    LOG_CHANNEL,
                    audio=message.audio.file_id,
                    caption=cap,
                    parse_mode=ParseMode.HTML,
                    message_thread_id=_thread,
                )
            )
            return
        if message.voice:
            await _send_with_floodwait(
                lambda: app.send_voice(
                    LOG_CHANNEL,
                    voice=message.voice.file_id,
                    caption=cap,
                    parse_mode=ParseMode.HTML,
                    message_thread_id=_thread,
                )
            )
            return
        if message.animation:
            await _send_with_floodwait(
                lambda: app.send_animation(
                    LOG_CHANNEL,
                    animation=message.animation.file_id,
                    caption=cap,
                    parse_mode=ParseMode.HTML,
                    message_thread_id=_thread,
                )
            )
            return
        if message.sticker:
            await _send_with_floodwait(
                lambda: app.send_sticker(
                    LOG_CHANNEL,
                    sticker=message.sticker.file_id,
                    message_thread_id=_thread,
                )
            )
            if cap:
                try:
                    await _send_with_floodwait(
                        lambda: app.send_message(
                            LOG_CHANNEL,
                            cap,
                            parse_mode=ParseMode.HTML,
                            message_thread_id=_thread,
                        )
                    )
                except (BadRequest, Forbidden, FloodWait):
                    pass
            return
    except (BadRequest, Forbidden) as e:
        send_errs.append(f"file_id: {e}")
    except FloodWait as e:
        send_errs.append(f"file_id FloodWait: {e}")

    # 3) Last resort: download then upload (chỉ các loại phổ biến)
    path = None
    try:
        path = await message.download()
        if not path:
            raise RuntimeError("download returned empty path")
        if message.photo:
            await app.send_photo(
                LOG_CHANNEL, photo=path, caption=cap,
                parse_mode=ParseMode.HTML, message_thread_id=_thread,
            )
        elif message.video:
            await app.send_video(
                LOG_CHANNEL, video=path, caption=cap,
                parse_mode=ParseMode.HTML, message_thread_id=_thread,
            )
        elif message.video_note:
            await app.send_video_note(
                LOG_CHANNEL, video_note=path, message_thread_id=_thread,
            )
            if cap:
                try:
                    await app.send_message(
                        LOG_CHANNEL, cap, parse_mode=ParseMode.HTML,
                        message_thread_id=_thread,
                    )
                except (BadRequest, Forbidden):
                    pass
        elif message.document:
            await app.send_document(
                LOG_CHANNEL, document=path, caption=cap,
                parse_mode=ParseMode.HTML, message_thread_id=_thread,
            )
        elif message.audio:
            await app.send_audio(
                LOG_CHANNEL, audio=path, caption=cap,
                parse_mode=ParseMode.HTML, message_thread_id=_thread,
            )
        elif message.voice:
            await app.send_voice(
                LOG_CHANNEL, voice=path, caption=cap,
                parse_mode=ParseMode.HTML, message_thread_id=_thread,
            )
        elif message.animation:
            await app.send_animation(
                LOG_CHANNEL, animation=path, caption=cap,
                parse_mode=ParseMode.HTML, message_thread_id=_thread,
            )
        elif message.sticker:
            await app.send_sticker(
                LOG_CHANNEL, sticker=path, message_thread_id=_thread,
            )
            if cap:
                try:
                    await app.send_message(
                        LOG_CHANNEL, cap, parse_mode=ParseMode.HTML,
                        message_thread_id=_thread,
                    )
                except (BadRequest, Forbidden):
                    pass
        else:
            raise RuntimeError("no supported media after download")
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


async def _send_payload_to_topic(message, topic_key: str, text: str) -> None:
    """Gửi tin (media hoặc text) vào topic đã chọn."""
    LOGGER.info(
        "admin_log_messages: payload→%s thread_id=%s has_media=%s",
        topic_key, topic_id(topic_key), _has_copyable_payload(message),
    )
    if _has_copyable_payload(message):
        cap = _build_user_chat_caption(message, text)
        await _send_media_to_log(message, cap, topic_key=topic_key)
        return
    body = _build_text_log_body(message, text)
    await _send_with_floodwait(
        lambda: app.send_message(
            LOG_CHANNEL,
            body,
            parse_mode=ParseMode.HTML,
            message_thread_id=topic_id(topic_key),
        )
    )


@app.on_message(
    filters.incoming
    & ~filters.service
    & (filters.private | filters.group),
    group=1,
)
async def log_user_message_to_admin(_, message):
    """Log lệnh / ảnh-video / PM / file nhóm vào LOG_CHANNEL. Không StopPropagation."""
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

    try:
        up_id = await _resolve_up_channel_id()
        if up_id is not None and message.chat and message.chat.id == up_id:
            return
    except Exception:
        pass

    text = (message.text or message.caption or "").strip()
    is_cmd = _is_command_message(text)
    is_photo_video = _is_media_message(message)
    is_file = _is_file_message(message)
    is_private = bool(message.chat and message.chat.type == ChatType.PRIVATE)

    try:
        # 1) Ảnh / video / video_note → tab photos|videos (PM + nhóm)
        if is_photo_video:
            cap = _build_user_chat_caption(message, text)
            await _send_media_to_log(message, cap)
            return

        # 2) Document / audio / voice → tab File (PM + nhóm). Không đẩy file PM vào tab pm
        #    (pm chưa có topic → trước đây rơi General — anh báo "gửi vào tin nhắn chung").
        if is_file:
            await _send_payload_to_topic(message, "files", text)
            return

        # 3) Lệnh text → tab commands (PM + nhóm)
        if is_cmd:
            body = _build_text_log_body(message, text)
            await _send_with_floodwait(
                lambda: app.send_message(
                    LOG_CHANNEL,
                    body,
                    parse_mode=ParseMode.HTML,
                    message_thread_id=topic_id("commands"),
                )
            )
            return

        # 4) PM còn lại (text thường, sticker, …) → Tin nhắn riêng
        if is_private:
            await _send_payload_to_topic(message, "pm", text)
            return
    except (BadRequest, Forbidden) as e:
        if "MESSAGE_ID_INVALID" not in str(e):
            LOGGER.warning("admin_log_messages BadRequest/Forbidden: %s", e)
    except FloodWait as e:
        LOGGER.warning("admin_log_messages FloodWait: %ss", getattr(e, "value", "?"))
    except Exception as e:
        LOGGER.exception("admin_log_messages: %s", e)
