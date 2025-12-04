import logging
from logging import getLogger

from curses.ascii import isblank

from pyrogram import Client, filters
from pyrogram.errors import ChannelPrivate, PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from database.users_chats_db import db
from tiensiteo import app
from tiensiteo.helper.localization import use_chat_lang
from tiensiteo.vars import COMMAND_HANDLER, LOG_CHANNEL, SUDO, SUPPORT_CHAT

LOGGER = getLogger("TienSiTeo")

@app.on_message(filters.incoming & filters.private, group=-5)
async def ban_reply(_, ctx: Message):
    if not ctx.from_user:
        return
    isban, alesan = await db.get_ban_status(ctx.from_user.id)
    if isban:
        await ctx.reply_msg(
            f'Tôi rất tiếc, Bạn bị cấm sử dụng Tôi. \nLý do: {alesan["reason"]}'
        )
        await ctx.stop_propagation()


@app.on_message(filters.group & filters.incoming, group=-2)
@use_chat_lang()
async def grp_bd(self: Client, ctx: Message, strings):
    if not ctx.from_user:
        return
    if not await db.is_chat_exist(ctx.chat.id):
        try:
            total = await self.get_chat_members_count(ctx.chat.id)
        except ChannelPrivate:
            await ctx.stop_propagation()
        r_j = ctx.from_user.mention if ctx.from_user else "Anonymous"
        await self.send_message(
            LOG_CHANNEL,
            strings("log_bot_added", context="grup_tools").format(
                ttl=ctx.chat.title, cid=ctx.chat.id, tot=total, r_j=r_j
            ),
        )
        await db.add_chat(ctx.chat.id, ctx.chat.title)
    chck = await db.get_chat(ctx.chat.id)
    if chck["is_disabled"]:
        buttons = [
            [InlineKeyboardButton("Liên hệ hỗ trợ", url=f"https://t.me/{SUPPORT_CHAT}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        vazha = await db.get_chat(ctx.chat.id)
        try:
            k = await ctx.reply_msg(
                f"KHÔNG ĐƯỢC PHÉP TRÒ CHUYỆN 🐞\n\nChủ sở hữu của tôi đã hạn chế tôi làm việc ở đây!\nLý do : <code>{vazha['reason']}</code>.",
                reply_markup=reply_markup,
            )
            await k.pin()
        except:
            pass
        try:
            await self.leave_chat(ctx.chat.id)
        except:
            pass
        await ctx.stop_propagation()


@app.on_message(filters.command("banuser", COMMAND_HANDLER) & filters.user(SUDO))
async def ban_a_user(bot, message):
    if len(message.command) == 1:
        return await message.reply("Đưa cho tôi user id / username")
    r = message.text.split(None)
    if len(r) > 2:
        reason = message.text.split(None, 2)[2]
        chat = message.text.split(None, 2)[1]
    else:
        chat = message.command[1]
        reason = "Không có lý do nào được cung cấp"
    try:
        chat = int(chat)
    except:
        pass
    try:
        k = await bot.get_users(chat)
    except PeerIdInvalid:
        return await message.reply(
            "Đây là người dùng không hợp lệ, hãy đảm bảo rằng tôi đã gặp họ trước đây."
        )
    except IndexError:
        return await message.reply("Đây có thể là một kênh, hãy đảm bảo đó là một người dùng.")
    except Exception as e:
        return await message.reply(f"Error - {e}")
    else:
        isban, alesan = await db.get_ban_status(k.id)
        if isban:
            return await message.reply(
                f"{k.mention} đã bị cấm rồi \n<b>Lý do:</b> {alesan['reason']}"
            )
        await db.ban_user(k.id, reason)
        await message.reply(
            f"Đã cấm người dùng thành công {k.mention}!!\n<b>Lý do:</b> {reason}"
        )


@app.on_message(filters.command("unbanuser", COMMAND_HANDLER) & filters.user(SUDO))
async def unban_a_user(bot, message):
    if len(message.command) == 1:
        return await message.reply("Đưa cho tôi user id / username")
    r = message.text.split(None)
    chat = message.text.split(None, 2)[1] if len(r) > 2 else message.command[1]
    try:
        chat = int(chat)
    except ValueError:
        pass

    try:
        k = await bot.get_users(chat)
    except PeerIdInvalid:
        return await message.reply(
            "Đây là một người dùng không hợp lệ, hãy chắc chắn rằng tôi đã gặp anh ấy trước đây."
        )
    except IndexError:
        return await message.reply("Đây có thể là một kênh, hãy chắc chắn rằng đó là một người dùng.")
    except Exception as e:
        return await message.reply(f"Lỗi - {e}")
    
    is_banned, user_data = await db.get_ban_status(k.id)
    if not is_banned:
        return await message.reply(f"{k.mention} chưa bị cấm.")
    
    await db.remove_ban(user_data["_id"])  # Thay k.id bằng user_data["_id"]
    await message.reply(f"Người dùng đã bỏ cấm thành công {k.mention}!!!")


@app.on_message(filters.command("disablechat", COMMAND_HANDLER) & filters.user(SUDO))
async def disable_chat(bot, message):
    if len(message.command) == 1:
        return await message.reply("Cho tôi một ID trò chuyện")
    r = message.text.split(None)
    if len(r) > 2:
        reason = message.text.split(None, 2)[2]
        chat = message.text.split(None, 2)[1]
    else:
        chat = message.command[1]
        reason = "Không có lý do được cung cấp"
    try:
        chat_ = int(chat)
    except:
        return await message.reply("Cho Tôi Một ID Trò Chuyện Hợp Lệ")
    cha_t = await db.get_chat(chat_)
    if not cha_t:
        return await message.reply("Không Tìm Thấy Cuộc Trò Chuyện Trong DB")
    if cha_t["is_disabled"]:
        return await message.reply(
            f"Cuộc trò chuyện này đã bị vô hiệu hóa rồi:\nLý do-<code> {cha_t['reason']} </code>"
        )
    await db.disable_chat(chat_, reason)
    await message.reply("Trò chuyện bị vô hiệu hóa thành công")
    try:
        buttons = [
            [InlineKeyboardButton("Support", url=f"https://t.me/{SUPPORT_CHAT}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await bot.send_message(
            chat_id=chat_,
            text=f"<b>Xin chào các bạn, \nChủ sở hữu của tôi đã bảo tôi rời khỏi nhóm nên tôi đi! Nếu bạn muốn thêm tôi một lần nữa hãy liên hệ với Chủ sở hữu của tôi.</b> \nLý do : <code>{reason}</code>",
            reply_markup=reply_markup,
        )
        await bot.leave_chat(chat_)
    except Exception as e:
        await message.reply(f"Lỗi - {e}")


@app.on_message(filters.command("enablechat", COMMAND_HANDLER) & filters.user(SUDO))
async def re_enable_chat(_, ctx: Message):
    if len(ctx.command) == 1:
        return await ctx.reply("Cho tôi một ID trò chuyện")
    chat = ctx.command[1]
    try:
        chat_ = int(chat)
    except:
        return await ctx.reply("Cho Tôi Một ID Trò Chuyện Hợp Lệ")
    sts = await db.get_chat(int(chat))
    if not sts:
        return await ctx.reply("Không Tìm Thấy Cuộc Trò Chuyện Trong DB !")
    if not sts.get("is_disabled"):
        return await ctx.reply("Cuộc trò chuyện này chưa bị vô hiệu hóa.")
    await db.re_enable_chat(chat_)
    await ctx.reply("Trò chuyện được kích hoạt lại thành công")
