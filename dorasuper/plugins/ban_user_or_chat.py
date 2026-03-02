import logging
from logging import getLogger

from pyrogram import Client, enums, filters
from pyrogram.errors import ChannelPrivate, PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from database.users_chats_db import db
from dorasuper import app, BOT_USERNAME
from dorasuper.helper.emoji_fmt import EMOJI_FMT
from dorasuper.helper.localization import use_chat_lang
from dorasuper.vars import COMMAND_HANDLER, LOG_CHANNEL, SUDO, SUPPORT_CHAT
from dorasuper.emoji import (
    E_ERROR,
    E_GROUP,
    E_INFO,
    E_LIMIT,
    E_SUCCESS,
    E_TIP,
    E_USER,
    E_WARN,
    E_WELCOME,
    E_WELCOME1,
    E_RIGHT_ARROW,
)

LOGGER = getLogger("DoraSuper")

@app.on_message(filters.incoming & filters.private, group=-5)
async def ban_reply(_, ctx: Message):
    if not ctx.from_user:
        return
    isban, alesan = await db.get_ban_status(ctx.from_user.id)
    if isban:
        reason = (alesan or {}).get("reason", "Không nêu") if alesan else "Không nêu"
        await ctx.reply_msg(
            f"{E_ERROR} Tôi rất tiếc, bạn bị cấm sử dụng tôi.\n<b>Lý do:</b> {reason}",
            parse_mode=enums.ParseMode.HTML,
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
            return
        r_j = ctx.from_user.mention if ctx.from_user else "Anonymous"
        try:
            await db.add_chat(ctx.chat.id, ctx.chat.title)
        except Exception as e:
            LOGGER.warning("add_chat failed %s: %s", ctx.chat.id, e)
        # Chỉ gửi tin chào mừng lần đầu; mời lại nhiều lần không chào nữa
        already_welcomed = await db.is_welcomed(ctx.chat.id)
        if not already_welcomed:
            welcome_msg = (
                f"{E_WELCOME} Xin chào cả nhóm! {E_WELCOME1}\n\n"
                f"{E_RIGHT_ARROW} Cảm ơn đã thêm bot vào nhóm. Bot đã sẵn sàng hoạt động.\n"
                "Gửi <code>/help</code> hoặc bấm nút bên dưới để xem danh sách lệnh."
            )
            welcome_keyb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Xem các lệnh", url=f"https://t.me/{BOT_USERNAME}?start=help")]
            ])
            try:
                await ctx.reply(welcome_msg, parse_mode=enums.ParseMode.HTML, reply_markup=welcome_keyb)
                await db.set_welcomed(ctx.chat.id)
            except Exception as e:
                LOGGER.warning("Không gửi được tin chào nhóm %s: %s", ctx.chat.id, e)
        # Lấy link nhóm để gửi vào nhóm thông báo (public = t.me/username, private = export invite)
        group_link = "—"
        raw_link = ""
        if getattr(ctx.chat, "username", None):
            raw_link = f"https://t.me/{ctx.chat.username}"
            group_link = f'<a href="{raw_link}">{raw_link}</a>'
        else:
            try:
                raw_link = await self.export_chat_invite_link(ctx.chat.id)
                group_link = f'<a href="{raw_link}">Link nhóm (invite)</a>' if raw_link.startswith("http") else raw_link
            except Exception:
                group_link = "— (cần quyền tạo link)"
        try:
            await self.send_message(
                LOG_CHANNEL,
                strings("log_bot_added", context="grup_tools").format(
                    ttl=ctx.chat.title, cid=ctx.chat.id, tot=total, r_j=r_j, link=group_link, **EMOJI_FMT
                ),
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception as e:
            LOGGER.warning("Không gửi được tin lên LOG: %s", e)
        return
    chck = await db.get_chat(ctx.chat.id)
    if chck and chck.get("is_disabled"):
        buttons = [
            [InlineKeyboardButton("Liên hệ hỗ trợ", url=f"https://t.me/{SUPPORT_CHAT}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        reason = (chck or {}).get("reason") or "Không nêu"
        try:
            k = await ctx.reply_msg(
                f"{E_LIMIT} <b>KHÔNG ĐƯỢC PHÉP TRÒ CHUYỆN</b>\n\nChủ sở hữu của tôi đã hạn chế tôi làm việc ở đây!\n<b>Lý do:</b> <code>{reason}</code>.",
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
            )
            await k.pin()
        except Exception:
            pass
        # Không xóa nhóm khỏi DB — giữ trong danh sách đen để lần sau mời lại vẫn từ chối
        try:
            await self.leave_chat(ctx.chat.id)
        except Exception:
            pass
        await ctx.stop_propagation()


@app.on_message(filters.command("banuser", COMMAND_HANDLER) & filters.user(SUDO))
async def ban_a_user(bot, message):
    if len(message.command) == 1:
        return await message.reply(f"{E_TIP} Đưa cho tôi user id / username", parse_mode=enums.ParseMode.HTML)
    r = message.text.split(None)
    if len(r) > 2:
        reason = message.text.split(None, 2)[2]
        chat = message.text.split(None, 2)[1]
    else:
        chat = message.command[1]
        reason = "Không có lý do nào được cung cấp"
    try:
        chat = int(chat)
    except (ValueError, TypeError):
        pass
    try:
        k = await bot.get_users(chat)
    except PeerIdInvalid:
        return await message.reply(
            f"{E_USER} Đây là người dùng không hợp lệ, hãy đảm bảo rằng tôi đã gặp họ trước đây.",
            parse_mode=enums.ParseMode.HTML,
        )
    except IndexError:
        return await message.reply(f"{E_WARN} Đây có thể là một kênh, hãy đảm bảo đó là một người dùng.", parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        return await message.reply(f"{E_ERROR} Error - {e}", parse_mode=enums.ParseMode.HTML)
    else:
        isban, alesan = await db.get_ban_status(k.id)
        if isban:
            reason_show = (alesan or {}).get("reason", "Không nêu") if alesan else "Không nêu"
            return await message.reply(
                f"{E_LIMIT} {k.mention} đã bị cấm rồi\n<b>Lý do:</b> {reason_show}",
                parse_mode=enums.ParseMode.HTML,
            )
        await db.ban_user(k.id, reason)
        await message.reply(
            f"{E_SUCCESS} Đã cấm người dùng thành công {k.mention}!!\n<b>Lý do:</b> {reason}",
            parse_mode=enums.ParseMode.HTML,
        )


@app.on_message(filters.command("unbanuser", COMMAND_HANDLER) & filters.user(SUDO))
async def unban_a_user(bot, message):
    if len(message.command) == 1:
        return await message.reply(f"{E_TIP} Đưa cho tôi user id / username", parse_mode=enums.ParseMode.HTML)
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
            f"{E_USER} Đây là một người dùng không hợp lệ, hãy chắc chắn rằng tôi đã gặp anh ấy trước đây.",
            parse_mode=enums.ParseMode.HTML,
        )
    except IndexError:
        return await message.reply(f"{E_WARN} Đây có thể là một kênh, hãy chắc chắn rằng đó là một người dùng.", parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        return await message.reply(f"{E_ERROR} Lỗi - {e}", parse_mode=enums.ParseMode.HTML)
    
    is_banned, user_data = await db.get_ban_status(k.id)
    if not is_banned or not user_data:
        return await message.reply(f"{E_INFO} {k.mention} chưa bị cấm.", parse_mode=enums.ParseMode.HTML)

    await db.remove_ban(user_data["_id"])
    await message.reply(f"{E_SUCCESS} Người dùng đã bỏ cấm thành công {k.mention}!!!", parse_mode=enums.ParseMode.HTML)


@app.on_message(filters.command("disablechat", COMMAND_HANDLER) & filters.user(SUDO))
async def disable_chat(bot, message):
    if len(message.command) == 1:
        return await message.reply(f"{E_TIP} Cho tôi một ID trò chuyện", parse_mode=enums.ParseMode.HTML)
    r = message.text.split(None)
    if len(r) > 2:
        reason = message.text.split(None, 2)[2]
        chat = message.text.split(None, 2)[1]
    else:
        chat = message.command[1]
        reason = "Không có lý do được cung cấp"
    try:
        chat_ = int(chat)
    except ValueError:
        return await message.reply(f"{E_WARN} Cho Tôi Một ID Trò Chuyện Hợp Lệ", parse_mode=enums.ParseMode.HTML)
    cha_t = await db.get_chat(chat_)
    if not cha_t:
        return await message.reply(f"{E_GROUP} Không Tìm Thấy Cuộc Trò Chuyện Trong DB", parse_mode=enums.ParseMode.HTML)
    if cha_t["is_disabled"]:
        return await message.reply(
            f"{E_INFO} Cuộc trò chuyện này đã bị vô hiệu hóa rồi:\nLý do: <code>{cha_t['reason']}</code>",
            parse_mode=enums.ParseMode.HTML,
        )
    await db.disable_chat(chat_, reason)
    await message.reply(f"{E_SUCCESS} Trò chuyện bị vô hiệu hóa thành công", parse_mode=enums.ParseMode.HTML)
    # Gửi tin tạm biệt + rời nhóm; nếu PEER_ID_INVALID (ID sai / bot đã bị kick) thì chỉ log, không báo lỗi cho user
    try:
        buttons = [
            [InlineKeyboardButton("Support", url=f"https://t.me/{SUPPORT_CHAT}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await bot.send_message(
            chat_id=chat_,
            text=f"{E_WELCOME} <b>Xin chào các bạn,</b>\nChủ sở hữu của tôi đã bảo tôi rời khỏi nhóm nên tôi đi! Nếu bạn muốn thêm tôi một lần nữa hãy liên hệ với Chủ sở hữu của tôi.\n{E_INFO} <b>Lý do:</b> <code>{reason}</code>",
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        LOGGER.warning("disablechat send_message %s: %s", chat_, e)
    # Không xóa nhóm khỏi DB — giữ is_disabled=True để khi mời lại bot vẫn từ chối và rời
    try:
        await bot.leave_chat(chat_)
    except Exception as e:
        LOGGER.warning("disablechat leave_chat %s: %s", chat_, e)


@app.on_message(filters.command("enablechat", COMMAND_HANDLER) & filters.user(SUDO))
async def re_enable_chat(_, ctx: Message):
    if len(ctx.command) == 1:
        return await ctx.reply_msg(f"{E_TIP} Cho tôi một ID trò chuyện", parse_mode=enums.ParseMode.HTML)
    chat = ctx.command[1]
    try:
        chat_ = int(chat)
    except ValueError:
        return await ctx.reply_msg(f"{E_WARN} Cho Tôi Một ID Trò Chuyện Hợp Lệ", parse_mode=enums.ParseMode.HTML)
    sts = await db.get_chat(chat_)
    if not sts:
        return await ctx.reply_msg(f"{E_GROUP} Không Tìm Thấy Cuộc Trò Chuyện Trong DB !", parse_mode=enums.ParseMode.HTML)
    if not sts.get("is_disabled"):
        return await ctx.reply_msg(
            f"{E_INFO} Cuộc trò chuyện này đang được phép hoạt động rồi, không cần bật lại.",
            parse_mode=enums.ParseMode.HTML,
        )
    await db.re_enable_chat(chat_)
    await ctx.reply_msg(f"{E_SUCCESS} Trò chuyện được kích hoạt lại thành công", parse_mode=enums.ParseMode.HTML)
