# Gửi vào LOG_CHANNEL chỉ khi user dùng lệnh của bot (tin bắt đầu bằng / hoặc !)

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
__HELP__ = """[Nội bộ] Chỉ khi user gửi lệnh (/, !) thì tin đó mới được gửi vào LOG_CHANNEL."""


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
    """Chỉ gửi vào LOG_CHANNEL khi user dùng lệnh (ví dụ /ai, /dl, !start)."""
    if not message.from_user or getattr(message.from_user, "is_bot", False):
        return
    if message.from_user.id == getattr(app.me, "id", None):
        return
    if message.from_user.id in SUDO:
        return
    text = (message.text or message.caption or "").strip()
    if not _is_command_message(text):
        return
    try:
        # Thông tin người gửi và nơi gửi
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

        # Gộp User + Chat + nội dung lệnh vào 1 tin nhắn (User và Chat mỗi cái 1 dòng)
        content = html.escape(text) if text else "(không có nội dung)"
        body = (
            f"{E_USER} <b>User:</b> {name} | {username} | <code>{uid}</code>\n\n"
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
