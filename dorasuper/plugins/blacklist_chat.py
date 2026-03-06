import re
import logging
from logging import getLogger
from datetime import datetime, timedelta

from pyrogram import filters
from pyrogram.errors import ChatAdminRequired
from pyrogram.types import ChatPermissions
from pyrogram.enums import ParseMode

from database.blacklist_db import (
    delete_blacklist_filter,
    get_blacklisted_words,
    save_blacklist_filter,
)
from dorasuper import app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.core.decorator.permissions import adminsOnly, list_admins
from dorasuper.emoji import E_CROSS, E_LIMIT, E_LIST, E_LOCK, E_SUCCESS, E_WARN
from dorasuper.helper.safe_reply import emoji_to_unicode, reply_safe
from dorasuper.vars import COMMAND_HANDLER, SUDO

LOGGER = getLogger("DoraSuper")

__MODULE__ = "DanhSáchĐen"
__HELP__ = """
<blockquote>/xemdsden - Lấy tất cả các từ bị cấm trong cuộc trò chuyện.
/dsden [TỪ|CÂU] - Cấm một từ hoặc một câu.
/dstrang [TỪ|CÂU] - Cho phép một từ hoặc một câu.</blockquote>
"""

@app.on_message(filters.command("dsden", COMMAND_HANDLER) & ~filters.private, group=-1)
@adminsOnly("can_restrict_members")
async def save_filters(_, message):
    if len(message.command) < 2:
        return await reply_safe(message, f"{E_WARN} Cách sử dụng:\n<code>/dsden [TỪ|CÂU]</code>")
    word = message.text.split(None, 1)[1].strip()
    if not word:
        return await reply_safe(message, f"{E_WARN} Cách sử dụng:\n<code>/dsden [TỪ|CÂU]</code>")
    chat_id = message.chat.id
    await save_blacklist_filter(chat_id, word)
    await reply_safe(message, f"{E_SUCCESS} <b>Đã cấm</b> <code>{word}</code>.")

@app.on_message(filters.command("xemdsden", COMMAND_HANDLER) & ~filters.private, group=-1)
@capture_err
async def get_filterss(_, message):
    data = await get_blacklisted_words(message.chat.id)
    if not data:
        await reply_safe(message, f"{E_LIST} Không có từ nào bị cấm trong cuộc trò chuyện này.")
    else:
        msg = f"{E_LIST} <b>Danh sách từ bị cấm</b> trong {message.chat.title}:\n\n"
        for word in data:
            msg += f"• <code>{word}</code>\n"
        await reply_safe(message, msg)

@app.on_message(filters.command("dstrang", COMMAND_HANDLER) & ~filters.private, group=-1)
@adminsOnly("can_restrict_members")
async def del_filter(_, message):
    if len(message.command) < 2:
        return await reply_safe(message, f"{E_WARN} Cách sử dụng:\n<code>/dstrang [TỪ|CÂU]</code>")
    word = message.text.split(None, 1)[1].strip()
    if not word:
        return await reply_safe(message, f"{E_WARN} Cách sử dụng:\n<code>/dstrang [TỪ|CÂU]</code>")
    chat_id = message.chat.id
    deleted = await delete_blacklist_filter(chat_id, word)
    if deleted:
        return await reply_safe(message, f"{E_SUCCESS} <b>Đã cho phép</b> <code>{word}</code>.")
    await reply_safe(message, f"{E_CROSS} Không có từ/câu cấm nào như vậy.")

@app.on_message(filters.text & ~filters.private, group=8)
@capture_err
async def blacklist_filters_re(self, message):
    text = message.text.lower().strip()
    if not text:
        return
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return
    if user.id in (SUDO or ()):
        return
    list_of_filters = await get_blacklisted_words(chat_id)
    for word in list_of_filters:
        pattern = r"( |^|[^\w])" + re.escape(word) + r"( |$|[^\w])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            admins = await list_admins(chat_id)
            if user.id in (admins or ()):
                return
            try:
                await message.delete_msg()
                await message.chat.restrict_member(
                    user.id,
                    ChatPermissions(all_perms=False),
                    until_date=datetime.now() + timedelta(hours=1),
                )
            except ChatAdminRequired:
                return await reply_safe(message, f"{E_WARN} Vui lòng cấp quyền quản trị viên cho tôi để cấm người dùng.")
            except Exception as err:
                LOGGER.info("LỖI Danh Sách Đen Cuộc Trò Chuyện: ID = %s, LỖI = %s", chat_id, err)
                return
            notify_text = (
                f"{E_LOCK} Đã tắt tiếng {user.mention} trong 1 giờ "
                f"do vi phạm danh sách đen với <code>{word}</code>."
            )
            try:
                await app.send_message(chat_id, notify_text, parse_mode=ParseMode.HTML)
            except Exception:
                await app.send_message(chat_id, emoji_to_unicode(notify_text), parse_mode=ParseMode.HTML)