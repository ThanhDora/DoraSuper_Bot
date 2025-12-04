import logging
from logging import getLogger

from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    ChatJoinRequest,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import dbname
from tiensiteo import app
from tiensiteo.core.decorator.permissions import adminsOnly, member_permissions
from tiensiteo.vars import COMMAND_HANDLER, SUDO

approvaldb = dbname["autoapprove"]

LOGGER = getLogger("TienSiTeo")

# For /help menu
__MODULE__ = "TựĐộngChấpNhận"
__HELP__ = """
<blockquote>autoapprove

Mô-đun này giúp tự động chấp nhận yêu cầu tham gia trò chuyện được gửi bởi người dùng thông qua liên kết lời mời của nhóm bạn.</blockquote>
"""


@app.on_message(filters.command("autoapprove", COMMAND_HANDLER) & filters.group)
@adminsOnly("can_change_info")
async def approval_command(_, message: Message):
    chat_id = message.chat.id
    if (await approvaldb.count_documents({"chat_id": chat_id})) > 0:
        keyboard_OFF = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Turn OFF", callback_data="approval_off")]]
        )
        await message.reply(
            "**Tự động phê duyệt cho cuộc trò chuyện này: Đã bật.**",
            reply_markup=keyboard_OFF,
        )
    else:
        keyboard_ON = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Turn ON", callback_data="approval_on")]]
        )
        await message.reply(
            "**Tự động phê duyệt cho cuộc trò chuyện này: Đã tắt.**",
            reply_markup=keyboard_ON,
        )


@app.on_callback_query(filters.regex("approval(.*)"))
async def approval_cb(_, cb: CallbackQuery):
    chat_id = cb.message.chat.id
    from_user = cb.from_user

    permissions = await member_permissions(chat_id, from_user.id)
    permission = "can_restrict_members"
    if permission not in permissions:
        if from_user.id not in SUDO:
            return await cb.answer(
                f"Bạn không có quyền cần thiết.\n Quyền yêu cầu: {permission}",
                show_alert=True,
            )

    command_parts = cb.data.split("_", 1)
    option = command_parts[1]

    if option == "on":
        if await approvaldb.count_documents({"chat_id": chat_id}) == 0:
            approvaldb.insert_one({"chat_id": chat_id})
            keyboard_off = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Tắt", callback_data="approval_off")]]
            )
            await cb.edit_message_text(
                "**Tự động phê duyệt cho cuộc trò chuyện này: Đã bật.**",
                reply_markup=keyboard_off,
            )
    elif option == "off":
        if await approvaldb.count_documents({"chat_id": chat_id}) > 0:
            approvaldb.delete_one({"chat_id": chat_id})
            keyboard_on = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Bật", callback_data="approval_on")]]
            )
            await cb.edit_message_text(
                "**Tự động phê duyệt cho cuộc trò chuyện này: Đã tắt.**",
                reply_markup=keyboard_on,
            )
    return await cb.answer()


@app.on_chat_join_request(filters.group)
async def accept(_, message: ChatJoinRequest):
    chat = message.chat
    user = message.from_user
    if (await approvaldb.count_documents({"chat_id": chat.id})) > 0:
        await app.approve_chat_join_request(chat_id=chat.id, user_id=user.id)
