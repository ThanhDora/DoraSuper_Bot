# Gửi vào LOG_CHANNEL khi user dùng lệnh (/, !) hoặc gửi video/ảnh — User và Chat mỗi cái 1 dòng

import html
from logging import getLogger

from pyrogram import filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import BadRequest

from dorasuper import app
from dorasuper.emoji import E_MSG, E_USER
from dorasuper.vars import LOG_CHANNEL, COMMAND_HANDLER, SUDO

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


@app.on_message(
    filters.incoming
    & ~filters.service
    & (filters.private | filters.group),
    group=1,
)
async def log_user_message_to_admin(_, message):
    """Gửi vào LOG_CHANNEL khi user dùng lệnh hoặc gửi video/ảnh. User và Chat mỗi cái 1 dòng."""
    if not message.from_user or getattr(message.from_user, "is_bot", False):
        return
    if message.from_user.id == getattr(app.me, "id", None):
        return
    if message.from_user.id in SUDO:
        return
    text = (message.text or message.caption or "").strip()
    is_cmd = _is_command_message(text)
    is_media = bool(message.photo or message.video)
    if not is_cmd and not is_media:
        return
    try:
        # Thông tin người gửi và nơi gửi (User và Chat luôn 1 dòng)
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

        # Ảnh/Video trong nhóm: copy media sang LOG_CHANNEL (kèm caption User/Chat)
        if is_media and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
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
            try:
                await message.copy(LOG_CHANNEL, caption=cap, parse_mode=ParseMode.HTML)
            except BadRequest:
                # Fallback: copy không caption nếu Telegram/pyrogram từ chối caption
                await message.copy(LOG_CHANNEL)
            return

        if is_cmd:
            content = html.escape(text) if text else "(không có nội dung)"
        else:
            if message.video:
                content = "🎬 Video"
            else:
                content = "📷 Ảnh"
            if text:
                content += "\n" + html.escape(text)

        body = (
            f"{E_USER} <b>User:</b> {name} | {username} | <code>{uid}</code>\n"
            f"{E_MSG} <b>Chat:</b> {chat_info}\n\n"
            f"<blockquote>{content}</blockquote>"
        )
        await app.send_message(
            LOG_CHANNEL,
            body,
            parse_mode=ParseMode.HTML,
        )
    except BadRequest as e:
        # MessageIdInvalid có thể xảy ra nếu tin đã bị xóa (vd: delete_command_msg) trước khi gửi
        if "MESSAGE_ID_INVALID" not in str(e):
            LOGGER.warning("admin_log_messages BadRequest: %s", e)
    except Exception as e:
        LOGGER.exception("admin_log_messages: %s", e)
