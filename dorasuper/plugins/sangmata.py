import asyncio
import re
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.types import Message

from database.sangmata_db import (
    add_userdata,
    cek_userdata,
    get_userdata,
    is_sangmata_on,
    sangmata_off,
    sangmata_on,
)
from dorasuper import app
from dorasuper.core.decorator.permissions import adminsOnly
from dorasuper.helper.emoji_fmt import EMOJI_FMT
from dorasuper.helper.localization import use_chat_lang
from dorasuper.vars import COMMAND_HANDLER
from dorasuper.emoji import E_SEARCH, E_USER, E_RIGHT_ARROW

from dorasuper.helper.safe_reply import reply_safe

LOGGER = getLogger("DoraSuper")

__MODULE__ = "KiểmTraĐổiTên"
__HELP__ = """
<blockquote>Tính năng này được lấy cảm hứng từ Bot SangMata. Tôi đã tạo một hệ thống phát hiện đơn giản để kiểm tra dữ liệu người dùng bao gồm tên người dùng, first_name và last_name. Nó sẽ giúp bạn có thể biết ai đó đã đổi tên của họ gần đây.
/sangmata_set [on/off] - Bật/tắt sangmata trong các nhóm.</blockquote>
"""


# Check user that change first_name, last_name and usernaname
@app.on_message(
    filters.group & ~filters.bot & ~filters.via_bot,
    group=5,
)
@use_chat_lang()
async def cek_mataa(_, ctx: Message, strings):
    if ctx.sender_chat or not await is_sangmata_on(ctx.chat.id):
        return
    if not await cek_userdata(ctx.from_user.id):
        return await add_userdata(
            ctx.from_user.id,
            ctx.from_user.username,
            ctx.from_user.first_name,
            ctx.from_user.last_name,
        )
    usernamebefore, first_name, lastname_before = await get_userdata(ctx.from_user.id)
    # Chuẩn hóa None và "" để tránh báo đổi tên sai khi chỉ khác kiểu trống
    uname_b = (usernamebefore or "").strip()
    uname_cur = (ctx.from_user.username or "").strip()
    fname_b = (first_name or "").strip()
    fname_cur = (ctx.from_user.first_name or "").strip()
    lname_b = (lastname_before or "").strip()
    lname_cur = (ctx.from_user.last_name or "").strip()
    msg = ""
    if uname_b != uname_cur or fname_b != fname_cur or lname_b != lname_cur:
        msg += f"{E_SEARCH} <b>DoraSuper Check</b>\n\n{E_USER} Người dùng: {ctx.from_user.mention}\n"
    if uname_b != uname_cur:
        usernamebefore = f"@{usernamebefore}" if usernamebefore else strings("no_uname").format(**EMOJI_FMT)
        usernameafter = (
            f"@{ctx.from_user.username}"
            if ctx.from_user.username
            else strings("no_uname").format(**EMOJI_FMT)
        )
        msg += strings("uname_change_msg").format(bef=usernamebefore, aft=usernameafter, **EMOJI_FMT)
        await add_userdata(
            ctx.from_user.id,
            ctx.from_user.username,
            ctx.from_user.first_name,
            ctx.from_user.last_name,
        )
    if fname_b != fname_cur:
        msg += strings("firstname_change_msg").format(
            bef=fname_b or strings("no_first_name").format(**EMOJI_FMT),
            aft=fname_cur or strings("no_first_name").format(**EMOJI_FMT),
            **EMOJI_FMT,
        )
        await add_userdata(
            ctx.from_user.id,
            ctx.from_user.username,
            ctx.from_user.first_name,
            ctx.from_user.last_name,
        )
    if lname_b != lname_cur:
        lastname_before_disp = lname_b or strings("no_last_name").format(**EMOJI_FMT)
        lastname_after_disp = lname_cur or strings("no_last_name").format(**EMOJI_FMT)
        msg += strings("lastname_change_msg").format(
            bef=lastname_before_disp, aft=lastname_after_disp, **EMOJI_FMT
        )
        await add_userdata(
            ctx.from_user.id,
            ctx.from_user.username,
            ctx.from_user.first_name,
            ctx.from_user.last_name,
        )
    if msg != "":
        await reply_safe(ctx, msg, quote=False)


@app.on_message(
    filters.group
    & filters.command("sangmata_set", COMMAND_HANDLER)
    & ~filters.bot
    & ~filters.via_bot,
    group=-1,
)
@adminsOnly("can_change_info")
@use_chat_lang()
async def set_mataa(_, ctx: Message, strings):
    if len(ctx.command) == 1:
        return await reply_safe(
            ctx,
            strings("set_sangmata_help").format(cmd=ctx.command[0], **EMOJI_FMT),
            del_in=6,
        )
    if ctx.command[1] == "on":
        cekset = await is_sangmata_on(ctx.chat.id)
        if cekset:
            await reply_safe(ctx, strings("sangmata_already_on").format(**EMOJI_FMT))
        else:
            await sangmata_on(ctx.chat.id)
            await reply_safe(ctx, strings("sangmata_enabled").format(**EMOJI_FMT))
    elif ctx.command[1] == "off":
        cekset = await is_sangmata_on(ctx.chat.id)
        if not cekset:
            await reply_safe(ctx, strings("sangmata_already_off").format(**EMOJI_FMT))
        else:
            await sangmata_off(ctx.chat.id)
            await reply_safe(ctx, strings("sangmata_disabled").format(**EMOJI_FMT))
    else:
        await reply_safe(
            ctx,
            strings("wrong_param").format(**EMOJI_FMT),
            del_in=6,
        )
