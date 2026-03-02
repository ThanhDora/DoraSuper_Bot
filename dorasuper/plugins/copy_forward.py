import logging
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.errors import UserIsBlocked, UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from dorasuper import BOT_USERNAME, app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.emoji import E_MSG, E_SUCCESS, E_TIP, E_WARN
from dorasuper.vars import COMMAND_HANDLER

LOGGER = getLogger("DoraSuper")

@app.on_message(filters.command(["saochep"], COMMAND_HANDLER))
async def copymsg(_, message):
    if len(message.command) == 1:
        if not message.reply_to_message:
            return await message.reply(f"{E_TIP} Vui lòng trả lời tin nhắn bạn muốn sao chép.")
        try:
            await message.reply_to_message.copy(
                message.from_user.id,
                caption_entities=message.reply_to_message.entities,
                reply_markup=message.reply_to_message.reply_markup,
            )
            return await message.reply_text(f"{E_SUCCESS} Tin nhắn đã được gửi thành công..")
        except UserIsBlocked:
            return await message.reply(
                f"{E_MSG} Vui lòng cho chủ nhân của tôi sao chép tin nhắn vào một cuộc trò chuyện riêng tư.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text="Trò chuyện với tôi",
                                url=f"https://t.me/{BOT_USERNAME}",
                            )
                        ]
                    ]
                ),
            )
        except Exception as e:
            return await message.reply(f"{E_WARN} Lỗi: {str(e)}")

@app.on_message(filters.command(["chuyentiep"], COMMAND_HANDLER))
@capture_err
async def forwardmsg(_, message):
    if len(message.command) == 1:
        if not message.reply_to_message:
            return await message.reply(f"{E_TIP} Vui lòng trả lời tin nhắn bạn muốn chuyển tiếp.")
        try:
            await message.reply_to_message.forward(message.from_user.id)
            return await message.reply_text(f"{E_SUCCESS} Tin nhắn đã được gửi thành công..")
        except UserIsBlocked:
            return await message.reply(
                f"{E_MSG} Vui lòng chuyển tiếp tin nhắn đến cuộc trò chuyện riêng tư của tôi..",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text="Trò chuyện với tôi",
                                url=f"https://t.me/{BOT_USERNAME}",
                            )
                        ]
                    ]
                ),
            )
        except Exception as e:
            return await message.reply(f"{E_WARN} Lỗi: {str(e)}")
