import re
import logging
from logging import getLogger
from datetime import datetime, timedelta

from pyrogram import filters
from pyrogram.errors import ChatAdminRequired
from pyrogram.types import ChatPermissions

from database.blacklist_db import (
    delete_blacklist_filter,
    get_blacklisted_words,
    save_blacklist_filter,
)
from tiensiteo import app
from tiensiteo.core.decorator.errors import capture_err
from tiensiteo.core.decorator.permissions import adminsOnly, list_admins
from tiensiteo.vars import SUDO

LOGGER = getLogger("TienSiTeo")

__MODULE__ = "DanhSáchĐen"
__HELP__ = """
<blockquote>/xemdsden - Lấy tất cả các từ bị cấm trong cuộc trò chuyện.
/dsden [TỪ|CÂU] - Cấm một từ hoặc một câu.
/dstrang [TỪ|CÂU] - Cho phép một từ hoặc một câu.</blockquote>
"""

@app.on_message(filters.command("dsden") & ~filters.private)
@adminsOnly("can_restrict_members")
async def save_filters(_, message):
    if len(message.command) < 2:
        return await message.reply_text("Cách sử dụng:\n/dsden [TỪ|CÂU]")
    word = message.text.split(None, 1)[1].strip()
    if not word:
        return await message.reply_text("**Cách sử dụng**\n__/dsden [TỪ|CÂU]__")
    chat_id = message.chat.id
    await save_blacklist_filter(chat_id, word)
    await message.reply_text(f"__**Đã cấm {word}.**__")

@app.on_message(filters.command("xemdsden") & ~filters.private)
@capture_err
async def get_filterss(_, message):
    data = await get_blacklisted_words(message.chat.id)
    if not data:
        await message.reply_text("**Không có từ nào bị cấm trong cuộc trò chuyện này.**")
    else:
        msg = f"Danh sách các từ bị cấm trong {message.chat.title} :\n"
        for word in data:
            msg += f"**-** `{word}`\n"
        await message.reply_text(msg)

@app.on_message(filters.command("dstrang") & ~filters.private)
@adminsOnly("can_restrict_members")
async def del_filter(_, message):
    if len(message.command) < 2:
        return await message.reply_text("Cách sử dụng:\n/dstrang [TỪ|CÂU]")
    word = message.text.split(None, 1)[1].strip()
    if not word:
        return await message.reply_text("Cách sử dụng:\n/dstrang [TỪ|CÂU]")
    chat_id = message.chat.id
    deleted = await delete_blacklist_filter(chat_id, word)
    if deleted:
        return await message.reply_text(f"**Đã cho phép {word}.**")
    await message.reply_text("**Không có bộ lọc cấm nào như vậy.**")

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
    if user.id in SUDO:
        return
    list_of_filters = await get_blacklisted_words(chat_id)
    for word in list_of_filters:
        pattern = r"( |^|[^\w])" + re.escape(word) + r"( |$|[^\w])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            if user.id in await list_admins(chat_id):
                return
            try:
                await message.delete_msg()
                await message.chat.restrict_member(
                    user.id,
                    ChatPermissions(all_perms=False),
                    until_date=datetime.now() + timedelta(hours=1),
                )
            except ChatAdminRequired:
                return await message.reply(
                    "Vui lòng cấp quyền quản trị viên cho tôi để cấm người dùng", quote=False
                )
            except Exception as err:
                self.log.info(f"LỖI Danh Sách Đen Cuộc Trò Chuyện: ID = {chat_id}, LỖI = {err}")
                return
            await app.send_message(
                chat_id,
                f"Đã tắt tiếng {user.mention} [`{user.id}`] trong 1 giờ "
                + f"do vi phạm danh sách đen với {word}.",
            )